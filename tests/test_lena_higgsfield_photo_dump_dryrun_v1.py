from __future__ import annotations

import pytest

from pipeline.prompting import lena_prompt_brain as prompt_brain
from pipeline.prompting.lena_prompt_brain import (
    HIGGSFIELD_BODY_SILHOUETTE_ANCHOR,
    HIGGSFIELD_FRAMING_LINE,
    ControlledProofLaneError,
)
from tools.diagnostics import lena_higgsfield_photo_dump_dryrun as photo_dump
from tools.diagnostics import lena_higgsfield_prompt_library_dryrun as prompt_library
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


DATE = "2026-07-15"


def _base_package(prompt: str) -> dict:
    return {
        "image_prompt": prompt,
        "negative_prompt_enabled": False,
        "photo_dump_low_hook_terms_found": [],
        "photo_dump_hook_terms_found": ["hook"],
        "photo_dump_mood_hook_terms_found": [],
        "photo_dump_hook_pass": True,
        "photo_dump_pose_scene_match_pass": True,
        "photo_dump_pose_scene_mismatch_terms_found": [],
    }


def _canonical_prompt(extra_tail: str = "") -> str:
    return (
        f"{HIGGSFIELD_FRAMING_LINE} "
        f"{HIGGSFIELD_BODY_SILHOUETTE_ANCHOR} "
        "Scene: neutral studio-adjacent realism. "
        "Wardrobe: tailored dress. "
        "Pose: balanced stance. "
        "Expression: calm direct gaze. "
        "Camera: 50mm lifestyle portrait. "
        "Lighting: soft natural light. "
        f"Mood: candid and realistic.{extra_tail}"
    )


def test_canonical_anchor_does_not_trip_heavy_overcorrection() -> None:
    validation = photo_dump._validate_image(_base_package(_canonical_prompt()))

    assert validation["heavy_overcorrection_free"] is True
    assert validation["heavy_overcorrection_terms_found"] == []


def test_genuine_overcorrection_prompt_is_still_excluded() -> None:
    validation = photo_dump._validate_image(
        _base_package(_canonical_prompt(" fuller thighs beyond the canonical anchor."))
    )

    assert validation["heavy_overcorrection_free"] is False
    assert "fuller thighs" in validation["heavy_overcorrection_terms_found"]


def test_laundromat_prompt_remains_hard_excluded() -> None:
    pack = photo_dump.build_report(DATE, "lenagate20260715085620d1-pack000", 10)
    laundromat_image = pack["images"][5]
    assert laundromat_image["lane"] == "laundry day"
    assert "laundromat" in laundromat_image["image_prompt"].lower()
    assert "laundromat" in laundromat_image["validation"]["low_hook_terms_found"]

    reasons = prompt_library._hard_exclude_reasons(laundromat_image)

    assert any("laundromat" in reason for reason in reasons)


def test_curator_can_select_a_valid_prompt_and_keep_laundromat_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prompt_library,
        "compute_higgsfield_failure_memory",
        lambda: {
            "pattern_counts": {},
            "hard_excluded_patterns": [],
            "soft_flagged_patterns": [],
            "skipped": [],
        },
    )

    library = prompt_library.build_library_report(DATE, "lenagate20260715085620d1", 1, 10)
    curation = prompt_library.curate_top_prompts(library, 1)

    assert len(curation["selected"]) == 1
    assert curation["selected"][0]["image"]["slot_id"].startswith("lenagate20260715085620d1-pack000")
    assert curation["candidate_count"] > 0


def test_prompt_library_threads_presence_contract_through_the_dry_run_report() -> None:
    contract = lena_profile.build_lena_presence_contract()
    library = prompt_library.build_library_report(
        DATE,
        "lenagate20260715085620d1",
        1,
        10,
        presence_contract=contract,
    )

    assert library["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"
    assert library["pack_reports"][0]["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"
    assert library["pack_reports"][0]["images"][0]["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"


def test_ordinary_photo_dump_pack_output_remains_unchanged_from_main() -> None:
    pack = photo_dump.build_report(DATE, "lenagate20260715085620d1-pack000", 10)

    assert [image["lane"] for image in pack["images"]] == [
        "wine bar patio",
        "wine bar patio",
        "wine bar patio",
        "brunch patio",
        "rooftop sunset",
        "laundry day",
        "morning apartment",
        "brunch patio",
        "lobby cocktail bar",
        "sidewalk dinner",
    ]


def test_controlled_recipe_request_admits_the_mirror_lane_with_authoritative_metadata() -> None:
    pack = prompt_brain.generate_higgsfield_photo_dump_pack(
        DATE,
        "lenagate20260715085620d1-pack000",
        10,
        required_recipe_id="hcr_012",
    )

    first_image = pack["images"][0]
    assert first_image["lane"] == "mirror outfit check"
    assert first_image["environment_id"] == "env_v008"
    assert first_image["wardrobe_outfit_id"] == "wc_p050"
    assert any(
        image["lane"] == "mirror outfit check"
        and image["environment_id"] == "env_v008"
        and image["wardrobe_outfit_id"] == "wc_p050"
        for image in pack["images"]
    )


def test_motorcycle_photo_dump_preserves_selected_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expression_text = "bank-selected calm sideward gaze"
    source_prompt = (
        "Scene: standing beside a real parked motorcycle. "
        f"Pose: {prompt_brain.HIGGSFIELD_POSE_REINFORCEMENT_LINE}. "
        f"Expression: {expression_text}. Camera: editorial portrait."
    )

    def fake_package(*args, **kwargs):
        return {
            "lane": prompt_brain.HIGGSFIELD_MOTO_LANE,
            "wardrobe_silhouette_class": "moto_editorial_test",
            "scene_action": "standing beside a real parked motorcycle",
            "pose_body_language_id": "pose_test",
            "expression_gaze_id": "exp_test",
            "expression_gaze_label": "test_expression",
            "expression_text": expression_text,
            "image_prompt": source_prompt,
            "prompt": source_prompt,
            "positive_prompt": source_prompt,
        }

    monkeypatch.setattr(prompt_brain, "generate_higgsfield_prompt_package", fake_package)

    pack = prompt_brain.generate_higgsfield_photo_dump_pack(
        DATE,
        "lenagate-expression-regression-pack000",
        8,
    )

    for image in pack["images"]:
        assert image["expression_text"] == expression_text
        assert "photo_dump_expression_variant" not in image
        for prompt_key in ("image_prompt", "prompt", "positive_prompt"):
            assert f"Expression: {expression_text}." in image[prompt_key]


def test_unknown_or_non_controlled_required_recipe_fails_closed() -> None:
    with pytest.raises(ControlledProofLaneError) as unknown:
        photo_dump.build_report(
            DATE,
            "lenagate20260715085620d1-pack000",
            10,
            required_recipe_id="hcr_unknown",
        )
    assert unknown.value.code == "controlled_proof_lane_recipe_unknown"

    with pytest.raises(ControlledProofLaneError) as not_controlled:
        photo_dump.build_report(
            DATE,
            "lenagate20260715085620d1-pack000",
            10,
            required_recipe_id="hcr_011",
        )
    assert not_controlled.value.code == "controlled_proof_lane_recipe_not_controlled"
