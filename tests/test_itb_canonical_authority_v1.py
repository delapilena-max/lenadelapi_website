from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.media_properties.interstitial_travel_bureau.artifacts import EpisodeStore, validate_cross_artifact_authority
from pipeline.media_properties.interstitial_travel_bureau.contracts import ITBContractError, canonical_json_bytes, canonical_sha256
from pipeline.media_properties.interstitial_travel_bureau.validation import validate_episode_root
from tests.itb_helpers import copy_pilot, error_codes, read_json, refresh_authority_hashes, write_json


def test_canonical_hash_ignores_key_order_and_whitespace():
    first = {"b": [2, 3], "a": "line\nvalue"}
    second = {"a": "line\nvalue", "b": [2, 3]}
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_sha256(first) == canonical_sha256(second)


def test_authoritative_change_changes_hash():
    first = {"value": 1}
    second = {"value": 2}
    assert canonical_sha256(first) != canonical_sha256(second)


def test_float_is_forbidden_by_canonical_contract():
    with pytest.raises(ITBContractError) as error:
        canonical_json_bytes({"value": 0.5})
    assert error.value.issues[0].code == "canonical_float_forbidden"


def test_formatting_and_line_endings_do_not_change_artifact_hash(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_canon_v1.json"
    value = read_json(path)
    before = canonical_sha256(value)
    path.write_text(__import__("json").dumps(value, separators=(",", ":")).replace("\n", "\r\n"), encoding="utf-8")
    assert EpisodeStore(root).load("bureau_canon_v1").sha256 == before


def test_stale_downstream_hash_fails_after_upstream_change(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_generation_plan_v1.json"
    value = read_json(path)
    value["capability_requirements"].append("new_authoritative_requirement")
    write_json(path, value)
    report = validate_episode_root(root)
    assert not report["ok"]
    assert "upstream_sha256_mismatch" in error_codes(report)


def test_circular_reference_is_detected(tmp_path: Path):
    root = copy_pilot(tmp_path)
    artifacts = EpisodeStore(root).load_all()
    canon = artifacts["bureau_canon_v1"]
    learning = artifacts["bureau_episode_learning_v1"]
    canon.data["upstream_artifacts"].append({"artifact_id": learning.artifact_id, "sha256": learning.sha256})
    issues = validate_cross_artifact_authority(artifacts)
    assert "circular_artifact_reference" in {item.code for item in issues}


def test_downstream_timestamp_cannot_precede_upstream(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_concept_card_v1.json"
    value = read_json(path)
    value["created_at"] = "2026-08-01T23:59:00Z"
    write_json(path, value)
    refresh_authority_hashes(root)
    assert "upstream_created_after_downstream" in error_codes(validate_episode_root(root))
