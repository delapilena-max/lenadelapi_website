from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from pipeline.media_properties.interstitial_travel_bureau.validation import validate_episode_root
from tests.itb_helpers import (
    PACKAGE_ROOT,
    copy_pilot,
    error_codes,
    read_json,
    refresh_authority_hashes,
    write_json,
)


CATALOG = read_json(PACKAGE_ROOT / "fixtures" / "invalid" / "invalid_cases_v1.json")


def _mutate(root: Path, case_id: str) -> None:
    if case_id == "generic_world_descriptions":
        path = root / "bureau_world_dossier_v1.json"
        value = read_json(path)
        value["summary"] = "Creepy strange futuristic alien cinematic spaces remain creepy, strange, futuristic, alien, and cinematic without observable mechanics or material rules."
        value["specificity_markers"] = ["vague"]
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "repeated_recent_world_genome":
        path = root / "bureau_continuity_ledger_v1.json"
        value = read_json(path)
        template = value["entries"][0]
        for episode_id in ("itb_ep_998", "itb_ep_999"):
            prior = deepcopy(template)
            prior["episode_id"] = episode_id
            prior["future_lockouts"] = [f"unrelated_lockout_{episode_id[-3:]}"]
            value["entries"].append(prior)
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "fewer_than_seven_shots":
        path = root / "bureau_visual_sequence_v1.json"
        value = read_json(path)
        value["sequence_profile"] = "standard_short"
        value["shots"] = value["shots"][:6]
        write_json(path, value)
    elif case_id == "visually_repetitive_shots":
        path = root / "bureau_visual_sequence_v1.json"
        value = read_json(path)
        for shot in value["shots"]:
            shot["environment"] = "mirror_customs_hall"
            shot["scale"] = "human"
            shot["camera"] = "locked_symmetrical_push"
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "missing_bureau_framing":
        path = root / "bureau_episode_script_v1.json"
        value = read_json(path)
        value["bureau_sign_off"] = "A general traveler-safety notice."
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "narration_too_long":
        path = root / "bureau_episode_script_v1.json"
        value = read_json(path)
        value["narration_segments"][0]["text"] += " " + "word " * 250
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "conflicting_entity_rule":
        path = root / "bureau_visual_sequence_v1.json"
        value = read_json(path)
        value["shots"][0]["entity_state"] = "hostile_unbounded_state"
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "missing_upstream_hash":
        path = root / "bureau_episode_script_v1.json"
        value = read_json(path)
        del value["upstream_artifacts"][0]["sha256"]
        write_json(path, value)
    elif case_id == "stale_compiled_request":
        path = root / "bureau_generation_plan_v1.json"
        value = read_json(path)
        value["capability_requirements"].append("changed_after_compilation")
        write_json(path, value)
    elif case_id == "excessive_generation_attempts":
        path = root / "bureau_generation_plan_v1.json"
        value = read_json(path)
        value["attempt_ceiling_per_asset"] = 6
        write_json(path, value)
    elif case_id == "missing_cost_ceiling":
        path = root / "bureau_generation_plan_v1.json"
        value = read_json(path)
        del value["cost_ceiling_cents"]
        write_json(path, value)
    elif case_id == "commercial_without_disclosure":
        path = root / "bureau_concept_card_v1.json"
        value = read_json(path)
        value["business_intent"]["commercial"] = True
        write_json(path, value)
        refresh_authority_hashes(root)
    elif case_id == "compiled_before_validation":
        path = root / "bureau_generation_plan_v1.json"
        value = read_json(path)
        value["validation_status"] = "provisional"
        write_json(path, value)
    elif case_id == "imitation_or_copied_concept":
        path = root / "bureau_concept_card_v1.json"
        value = read_json(path)
        value["episode_concept"] = "Create a copy in the style of a named creator while preserving the Bureau wrapper."
        write_json(path, value)
        refresh_authority_hashes(root)
    else:
        raise AssertionError(f"unknown invalid fixture case: {case_id}")


@pytest.mark.parametrize("fixture", CATALOG["cases"], ids=lambda item: item["case_id"])
def test_invalid_fixture_is_rejected_with_expected_error(tmp_path: Path, fixture: dict):
    root = copy_pilot(tmp_path)
    _mutate(root, fixture["case_id"])
    report = validate_episode_root(root)
    assert report["ok"] is False
    assert fixture["expected_error"] in error_codes(report)


def test_fixture_catalog_covers_all_required_negative_cases():
    assert len(CATALOG["cases"]) == 14
    assert len({item["case_id"] for item in CATALOG["cases"]}) == 14


def test_user_lock_tampering_fails_even_with_refreshed_hashes(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_episode_script_v1.json"
    value = read_json(path)
    value["selected_hook"] = value["hook_options"][1]
    write_json(path, value)
    refresh_authority_hashes(root)
    assert "user_lock_changed" in error_codes(validate_episode_root(root))


def test_provider_name_leak_in_neutral_plan_fails(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_generation_plan_v1.json"
    value = read_json(path)
    value["shot_requests"][0]["prompt_components"]["environment"] = "Higgsfield-specific mirror preset"
    write_json(path, value)
    refresh_authority_hashes(root)
    assert "provider_neutrality_violation" in error_codes(validate_episode_root(root))


def test_shot_duration_mismatch_fails(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_visual_sequence_v1.json"
    value = read_json(path)
    value["shots"][0]["duration_ms"] += 1000
    write_json(path, value)
    refresh_authority_hashes(root)
    assert "shot_duration_fit_failed" in error_codes(validate_episode_root(root))
