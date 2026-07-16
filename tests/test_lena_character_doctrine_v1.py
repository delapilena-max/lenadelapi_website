from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest


MODULE = importlib.import_module("pipeline.identity.lena_character_doctrine_validate_v1")
ROOT = Path(__file__).resolve().parents[1]
DOCTRINE_PATH = ROOT / "pipeline" / "identity" / "lena_character_doctrine_v1.json"


def _load_real_payload() -> dict:
    return json.loads(DOCTRINE_PATH.read_text(encoding="utf-8-sig"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# The real, tracked artifact loads and validates cleanly.
# ---------------------------------------------------------------------------


def test_real_doctrine_artifact_loads_and_validates() -> None:
    payload = MODULE.load_doctrine()
    assert payload["schema_version"] == "lena_character_doctrine_v1"
    assert payload["authority_id"] == "lena_character_doctrine_v1"
    assert payload["influencer_id"] == "lena"


def test_real_doctrine_encodes_every_required_defining_quality() -> None:
    payload = MODULE.load_doctrine()
    qualities = set(payload["character_definition"]["defining_qualities"])
    assert qualities == set(MODULE.REQUIRED_DEFINING_QUALITIES)
    for quality in (
        "warm",
        "playful",
        "confident",
        "flirtatious",
        "naturally_sensual",
        "expressive",
        "approachable",
        "directly_connected_to_one_viewer",
        "physically_alive_rather_than_editorially_static",
        "strongly_consistent_in_face_body_and_personality",
    ):
        assert quality in qualities


def test_real_doctrine_encodes_every_required_safety_hard_failure() -> None:
    payload = MODULE.load_doctrine()
    hard_failures = set(payload["safety_boundaries"]["hard_failures"])
    assert hard_failures == set(MODULE.REQUIRED_SAFETY_HARD_FAILURES)


def test_real_doctrine_encodes_the_sensuality_never_overrides_safety_rules() -> None:
    payload = MODULE.load_doctrine()
    overriding_rules = set(payload["safety_boundaries"]["overriding_rules"])
    for rule in MODULE.REQUIRED_SAFETY_OVERRIDING_RULES:
        assert rule in overriding_rules
    assert "sensuality_never_overrides_identity" in overriding_rules
    assert "sensuality_never_overrides_anatomy" in overriding_rules
    assert "sensuality_never_overrides_adult_presentation" in overriding_rules
    assert "sensuality_never_overrides_exposure_limits" in overriding_rules
    assert "sensuality_never_overrides_platform_safety" in overriding_rules
    assert "harmless_imperfection_is_not_a_hard_failure" in overriding_rules
    assert "technical_perfection_must_not_be_used_to_suppress_strong_character" in overriding_rules


def test_real_doctrine_encodes_the_originality_boundary() -> None:
    payload = MODULE.load_doctrine()
    rules = set(payload["originality_boundary"]["rules"])
    for rule in MODULE.REQUIRED_ORIGINALITY_RULES:
        assert rule in rules


def test_real_doctrine_wardrobe_classification_distinguishes_three_tiers() -> None:
    payload = MODULE.load_doctrine()
    classification = payload["wardrobe_and_sensuality"]["classification"]
    assert classification["normal_anatomy_through_fabric"]["is_a_defect"] is False
    assert classification["suggestive_but_platform_appropriate_styling"]["is_a_defect"] is False
    assert classification["explicit_exposure_or_prohibited_sexual_content"]["is_a_defect"] is True


def test_real_doctrine_requires_human_signoff_for_change() -> None:
    payload = MODULE.load_doctrine()
    assert payload["owner"]["human_signoff_required_for_change"] is True


def test_real_doctrine_references_identity_authority_without_replacing_it() -> None:
    payload = MODULE.load_doctrine()
    assert (
        payload["hard_identity_continuity"]["authority_reference"]
        == "pipeline/identity/lena_visual_reference_authority_v1.json"
    )


def test_real_doctrine_has_no_leaked_absolute_local_path() -> None:
    source = DOCTRINE_PATH.read_text(encoding="utf-8")
    assert "C:\\" not in source
    assert "C:/Users" not in source
    assert "/home/" not in source


# ---------------------------------------------------------------------------
# Fail-closed behavior: missing file, malformed JSON, missing/wrong sections.
# ---------------------------------------------------------------------------


def test_missing_doctrine_file_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(missing)
    assert exc_info.value.code == "doctrine_missing"


def test_malformed_json_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(bad)
    assert exc_info.value.code == "doctrine_malformed"


def test_non_object_json_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "list.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(bad)
    assert exc_info.value.code == "doctrine_malformed"


@pytest.mark.parametrize(
    "section_name",
    list(MODULE.REQUIRED_TOP_LEVEL_SECTIONS),
)
def test_missing_required_section_fails_closed(tmp_path: Path, section_name: str) -> None:
    payload = copy.deepcopy(_load_real_payload())
    del payload[section_name]
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"
    assert section_name in exc_info.value.detail


def test_missing_a_defining_quality_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["character_definition"]["defining_qualities"].remove("flirtatious")
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_missing_a_safety_hard_failure_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["safety_boundaries"]["hard_failures"].remove("explicit_exposure")
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_missing_an_overriding_rule_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["safety_boundaries"]["overriding_rules"].remove(
        "sensuality_never_overrides_identity"
    )
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_flipping_explicit_exposure_to_not_a_defect_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["wardrobe_and_sensuality"]["classification"][
        "explicit_exposure_or_prohibited_sexual_content"
    ]["is_a_defect"] = False
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_flipping_normal_anatomy_to_a_defect_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["wardrobe_and_sensuality"]["classification"][
        "normal_anatomy_through_fabric"
    ]["is_a_defect"] = True
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_removing_human_signoff_requirement_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["owner"]["human_signoff_required_for_change"] = False
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_wrong_schema_version_fails_closed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["schema_version"] = "some_other_schema_v1"
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


@pytest.mark.parametrize(
    "bad_value",
    [
        "not-a-real-sha",
        "94DA3C3D9A8722EF53C1CB9A3C0241799E74DAF6",  # uppercase is rejected
        "94da3c3d9a8722ef53c1cb9a3c0241799e74daf",  # 39 chars
        "94da3c3d9a8722ef53c1cb9a3c0241799e74daf60",  # 41 chars
        "",
        None,
        12345,
    ],
)
def test_authored_against_repository_revision_must_be_a_valid_lowercase_git_sha(
    tmp_path: Path, bad_value: object
) -> None:
    payload = copy.deepcopy(_load_real_payload())
    payload["authored_against_repository_revision"] = bad_value
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    with pytest.raises(MODULE.CharacterDoctrineError) as exc_info:
        MODULE.load_doctrine(path)
    assert exc_info.value.code == "doctrine_invalid"


def test_authored_against_repository_revision_is_never_claimed_to_contain_the_doctrine() -> None:
    """The field name and doctrine's own change-control text must not imply
    the referenced commit contains this artifact -- only that the doctrine
    was authored against that repository state."""
    payload = _load_real_payload()
    assert "authority_commit" not in payload
    assert MODULE._is_valid_git_sha(payload["authored_against_repository_revision"])
    change_control_text = " ".join(payload["change_control"]["rules"])
    assert "never claimed to be a commit that contains this artifact" in change_control_text or (
        "authored_against_repository_revision records what repository state" in change_control_text
    )


# ---------------------------------------------------------------------------
# Provenance / SHA-binding contract (for future consumers, not wired here).
# ---------------------------------------------------------------------------


def test_doctrine_sha256_matches_real_file_bytes() -> None:
    expected = hashlib.sha256(DOCTRINE_PATH.read_bytes()).hexdigest()
    assert MODULE.doctrine_sha256() == expected


def test_doctrine_sha256_changes_if_bytes_change(tmp_path: Path) -> None:
    path = tmp_path / "doctrine.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    first = MODULE.doctrine_sha256(path)
    path.write_text('{"a": 2}', encoding="utf-8")
    second = MODULE.doctrine_sha256(path)
    assert first != second


def test_doctrine_provenance_binds_path_sha_version_and_authored_against_revision() -> None:
    provenance = MODULE.doctrine_provenance()
    assert provenance["source_doctrine_artifact_path"] == "pipeline/identity/lena_character_doctrine_v1.json"
    assert provenance["source_doctrine_artifact_sha256"] == MODULE.doctrine_sha256()
    assert provenance["doctrine_version"] == "v1.0.0"
    assert MODULE._is_valid_git_sha(provenance["doctrine_authored_against_repository_revision"])
    assert "doctrine_authority_commit" not in provenance


def test_doctrine_sha256_is_the_primary_binding_and_changes_on_nonsemantic_edits(
    tmp_path: Path,
) -> None:
    """A pure formatting change (added whitespace, no semantic content change)
    still changes the file's sha256, so any downstream binding keyed on the
    old sha256 is correctly invalidated rather than silently treated as
    still matching."""
    payload = _load_real_payload()
    path = tmp_path / "doctrine.json"
    _write(path, payload)
    original_sha = MODULE.doctrine_sha256(path)

    # Re-serialize with different (but semantically identical) formatting.
    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
    reformatted_sha = MODULE.doctrine_sha256(path)

    assert reformatted_sha != original_sha


def test_doctrine_summary_reports_ready_and_defining_qualities() -> None:
    summary = MODULE.doctrine_summary()
    assert summary["doctrine_status"] == "ready"
    assert set(summary["defining_qualities"]) == set(MODULE.REQUIRED_DEFINING_QUALITIES)


# ---------------------------------------------------------------------------
# This is a report-only authority module: no live execution/approval/publish
# import, and it must not depend on any dirty/local workspace path.
# ---------------------------------------------------------------------------


def test_validator_module_is_report_only_and_touches_no_live_surfaces() -> None:
    source = Path(MODULE.__file__).read_text(encoding="utf-8")
    assert "C:\\projects\\ai\\content_bot" not in source

    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    blocked_prefixes = (
        "requests",
        "httpx",
        "urllib.request",
        "subprocess",
        "boto3",
        "pipeline.higgsfield_lena_api_executor",
        "tools.lena_higgsfield_generation_approval_v1",
        "tools.lena_build_approved_publish_queue_v2_8",
        "tools.strategy.lena_build_next_live_image_handoff_v1",
        "tools.strategy.lena_record_generation_reconciliation_decision_v1",
        "tools.strategy.lena_reconciliation_contract_v1",
    )
    for module in imported_modules:
        assert not any(module.startswith(prefix) for prefix in blocked_prefixes), module


def test_canonical_brain_assets_module_is_untouched_in_behavior_besides_new_entry() -> None:
    """PR1 must only add a registry entry, not change any existing behavior."""
    brain_assets = importlib.import_module(
        "pipeline.influencer_nodes.lena.canonical_brain_assets"
    )
    report = brain_assets.load_canonical_brain_assets()
    assets = {asset["asset_id"]: asset for asset in report["assets"]}
    assert "character_doctrine" in assets
    doctrine_asset = assets["character_doctrine"]
    assert doctrine_asset["required"] is True
    assert doctrine_asset["category"] == "identity"
    assert doctrine_asset["exists"] is True
    assert doctrine_asset["sha256"] == MODULE.doctrine_sha256()
