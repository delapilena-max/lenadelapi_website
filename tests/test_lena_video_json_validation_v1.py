from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from pipeline.media_properties.lena.video.artifacts import (
    VideoArtifactStore,
    validate_cross_artifact_authority,
)
from pipeline.media_properties.lena.video.contracts import canonical_sha256
from pipeline.media_properties.lena.video.validation import (
    validate_loaded_video,
    validate_source_for_compilation,
    validate_video_root,
)
from tests.lena_video_json_test_support import (
    PILOT_ROOT,
    copy_pilot,
    issue_codes,
    mutated_loaded,
    read_artifact,
    write_artifact,
)


def _codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def test_real_spacex_pilot_validates_with_zero_activity() -> None:
    report = validate_video_root(PILOT_ROOT)

    assert report["ok"] is True
    assert report["artifacts_validated"] == 14
    assert report["errors"] == []
    assert set(report["counters"].values()) == {0}


def test_upstream_change_invalidates_stale_downstream_artifacts(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    character = read_artifact(root, "lena_video_character_authority_v1")
    character["face_authority"] += " Preserve one additional stable facial landmark."
    write_artifact(root, "lena_video_character_authority_v1", character)

    report = validate_video_root(root)

    assert report["ok"] is False
    assert "upstream_sha256_mismatch" in issue_codes(report)
    assert "generation_plan_not_deterministic_output" in issue_codes(report)


def test_character_element_uuid_is_exact_schema_authority(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    character = read_artifact(root, "lena_video_character_authority_v1")
    character["character_element_uuid"] = "00000000-0000-0000-0000-000000000000"
    write_artifact(root, "lena_video_character_authority_v1", character)

    report = validate_video_root(root)

    assert report["ok"] is False
    assert "schema_const_mismatch" in issue_codes(report)


def test_missing_hpe_segment_is_rejected_by_schema(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    hpe = read_artifact(root, "lena_video_hpe_v1")
    hpe["timeline"].pop()
    write_artifact(root, "lena_video_hpe_v1", hpe)

    report = validate_video_root(root)

    assert "schema_array_too_short" in issue_codes(report)


def test_hpe_overlap_is_rejected(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    hpe = read_artifact(root, "lena_video_hpe_v1")
    hpe["timeline"][1]["start_ms"] = 1500
    write_artifact(root, "lena_video_hpe_v1", hpe)

    assert "hpe_timeline_overlap" in issue_codes(validate_video_root(root))


def test_hpe_must_cover_exactly_eight_seconds(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    hpe = read_artifact(root, "lena_video_hpe_v1")
    hpe["timeline"][-1]["end_ms"] = 7900
    write_artifact(root, "lena_video_hpe_v1", hpe)

    assert "hpe_timeline_duration_mismatch" in issue_codes(validate_video_root(root))


def test_static_performance_and_incomplete_gesture_are_rejected() -> None:
    def mutate(value):
        for segment in value["timeline"]:
            segment["meaningful_displacement_cm"] = 0
            segment["expression"] = "frozen_smile"
            segment["gesture_completion"] = "none"

    artifacts = mutated_loaded(PILOT_ROOT, "lena_video_hpe_v1", mutate)
    codes = _codes(validate_source_for_compilation(artifacts))

    assert {
        "hpe_meaningful_displacement_missing",
        "hpe_expression_progression_missing",
        "hpe_gesture_completion_missing",
    }.issubset(codes)


def test_dialogue_must_fit_the_eight_second_window() -> None:
    def mutate(value):
        value["dialogue_mode"] = "spoken"
        value["dialogue_text"] = " ".join(["word"] * 21)
        value["voice_authority_required"] = True
        value["lip_sync_required"] = True

    artifacts = mutated_loaded(PILOT_ROOT, "lena_video_audio_plan_v1", mutate)

    assert "dialogue_duration_fit_failed" in _codes(
        validate_source_for_compilation(artifacts)
    )


@pytest.mark.parametrize(
    ("artifact_type", "mutate", "expected_code"),
    [
        (
            "lena_video_wardrobe_v1",
            lambda value: value["garments"][0].__setitem__("continuity", "partial_video"),
            "wardrobe_continuity_violation",
        ),
        (
            "lena_video_environment_v1",
            lambda value: value.__setitem__("specificity_markers", value["specificity_markers"][:4]),
            "environment_too_generic",
        ),
        (
            "lena_video_environment_v1",
            lambda value: value["access_context"].__setitem__("restricted_access", True),
            "restricted_access_implication",
        ),
        (
            "lena_video_camera_v1",
            lambda value: value.__setitem__("camera_holder", "self"),
            "camera_holder_contract_violation",
        ),
        (
            "lena_video_camera_v1",
            lambda value: value.__setitem__("selfie", True),
            "camera_holder_contract_violation",
        ),
        (
            "lena_video_camera_v1",
            lambda value: value.__setitem__("camera_movement", "impossible_orbit"),
            "camera_motion_unrealistic",
        ),
        (
            "lena_video_business_intent_v1",
            lambda value: value.__setitem__("space_x_affiliation", "sponsored"),
            "implied_sponsorship_or_affiliation",
        ),
        (
            "lena_video_business_intent_v1",
            lambda value: value.__setitem__("paid_partnership", True),
            "commercial_disclosure_missing",
        ),
        (
            "lena_video_spec_v1",
            lambda value: value.__setitem__(
                "provider_prompt_cue", value["provider_prompt_cue"] + " Higgsfield."
            ),
            "provider_prompt_cue_not_neutral",
        ),
    ],
)
def test_domain_contracts_fail_closed(
    artifact_type: str,
    mutate,
    expected_code: str,
) -> None:
    artifacts = mutated_loaded(PILOT_ROOT, artifact_type, mutate)

    assert expected_code in _codes(validate_source_for_compilation(artifacts))


def test_user_locked_concept_cannot_change_silently() -> None:
    artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_spec_v1",
        lambda value: value.__setitem__("concept", "A different unlocked concept."),
    )

    assert "user_lock_changed" in _codes(validate_source_for_compilation(artifacts))


def test_spec_cost_ceiling_must_match_policy() -> None:
    artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_spec_v1",
        lambda value: value.__setitem__("cost_ceiling_credits", 35),
    )

    assert "spec_cost_ceiling_mismatch" in _codes(
        validate_source_for_compilation(artifacts)
    )


def test_property_and_video_ids_must_match_across_artifacts() -> None:
    artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_audio_plan_v1",
        lambda value: value.__setitem__(
            "video_id", "lena_video_2026-08-03_different_video"
        ),
    )

    assert "video_id_mismatch" in _codes(validate_cross_artifact_authority(artifacts))


def test_circular_authority_is_rejected() -> None:
    artifacts = VideoArtifactStore(PILOT_ROOT).load_sources()
    spec = artifacts["lena_video_spec_v1"]
    hpe = artifacts["lena_video_hpe_v1"]
    data = deepcopy(spec.data)
    data["upstream_artifacts"].append(
        {"artifact_id": hpe.artifact_id, "sha256": hpe.sha256}
    )
    artifacts["lena_video_spec_v1"] = replace(
        spec,
        data=data,
        sha256=canonical_sha256(data),
    )

    assert "circular_artifact_reference" in _codes(
        validate_cross_artifact_authority(artifacts)
    )


def test_duplicate_daily_final_video_is_rejected() -> None:
    artifacts = VideoArtifactStore(PILOT_ROOT).load_all()
    existing = [
        {"governed_date": "2026-08-03", "lifecycle_state": "final"},
        {"governed_date": "2026-08-03", "lifecycle_state": "published"},
    ]

    assert "duplicate_daily_final_video" in _codes(
        validate_loaded_video(artifacts, existing_final_manifests=existing)
    )


def test_manifest_cannot_exceed_zero_attempt_authority() -> None:
    artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_manifest_v1",
        lambda value: value.__setitem__("attempts", 1),
        load_all=True,
    )

    assert "manifest_attempt_authority_exceeded" in _codes(
        validate_loaded_video(artifacts)
    )


def test_pre_generation_manifest_cannot_claim_provider_output() -> None:
    def mutate(value):
        value["provider_job_id"] = "job_not_authorized"
        value["actual_spend_credits"] = 1

    artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_manifest_v1",
        mutate,
        load_all=True,
    )

    codes = _codes(validate_loaded_video(artifacts))
    assert "pre_generation_manifest_claims_output" in codes
    assert "manifest_attempt_authority_exceeded" not in codes


def test_pre_generation_qa_and_learning_cannot_claim_success() -> None:
    qa_artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_qa_v1",
        lambda value: (
            value.__setitem__("overall_quality", "premium_pass"),
            value.__setitem__("publish_disposition", "approved"),
        ),
        load_all=True,
    )
    learning_artifacts = mutated_loaded(
        PILOT_ROOT,
        "lena_video_learning_v1",
        lambda value: value.__setitem__("confidence_basis_points", 5000),
        load_all=True,
    )

    assert "pre_generation_qa_claim_invalid" in _codes(
        validate_loaded_video(qa_artifacts)
    )
    assert "pre_generation_learning_claim_invalid" in _codes(
        validate_loaded_video(learning_artifacts)
    )


def test_quality_disposition_contains_explicit_premium_reject_conditions() -> None:
    qa = VideoArtifactStore(PILOT_ROOT).load("lena_video_qa_v1").data
    joined = " ".join(qa["reject_conditions"]).lower()

    for term in (
        "identity",
        "static posing",
        "rocket",
        "selfie",
        "wardrobe leakage",
        "sponsorship",
        "provider demo",
        "premium",
    ):
        assert term in joined
    assert qa["overall_quality"] == "not_assessable_pre_generation"
    assert qa["publish_disposition"] == "not_authorized"
