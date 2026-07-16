from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pipeline.presence import human_presence_contract_v1 as hpe
from pipeline.presence import human_presence_prompt_plan_v1 as plan
from pipeline.prompting import lena_prompt_brain as prompt_brain
from tools.diagnostics import lena_higgsfield_photo_dump_dryrun as photo_dump
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


DATE = "2026-07-15"
SLOT_ID = "hpe2a-slot-00-photo"


def test_generic_prompt_plan_module_contains_no_lena_specific_identity_language() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    lowered = source.lower()
    assert "lena" not in lowered
    assert "mirror outfit check" not in lowered
    assert "hcr_012" not in lowered
    assert "fuller thighs" not in lowered

    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    assert "tools.strategy.lena_human_presence_profile_v1" not in imported_modules


def test_valid_lena_contract_compiles_deterministically_for_still_image() -> None:
    contract = lena_profile.build_lena_presence_contract()
    plan_one = plan.compile_human_presence_prompt_plan(contract, medium="still_image")
    plan_two = plan.compile_human_presence_prompt_plan(contract, medium="still_image")

    assert plan_one == plan_two
    assert plan_one["schema_version"] == "human_presence_prompt_plan_v1"
    assert plan_one["medium_interpretation"] == "still_image"
    assert plan_one["selector_weight_adjustments_changed"] is True
    assert "silent pre-response beat" in plan_one["speech_behavior"]["directive"]
    assert "dialogue" in plan_one["speech_behavior"]["directive"].lower()


def test_invalid_or_stale_doctrine_provenance_fails_closed() -> None:
    contract = lena_profile.build_lena_presence_contract()
    contract["character_doctrine_provenance"]["source_doctrine_artifact_sha256"] = "0" * 64

    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        plan.compile_human_presence_prompt_plan(contract, medium="still_image")

    assert exc_info.value.code == "doctrine_provenance_stale"


def test_unknown_enum_value_fails_closed() -> None:
    contract = lena_profile.build_lena_presence_contract()
    contract["viewer_relationship"]["awareness"] = "broadcast_everywhere"

    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        plan.compile_human_presence_prompt_plan(contract, medium="still_image")

    assert exc_info.value.code == "unknown_enum_value"


def test_no_presence_keeps_higgsfield_prompt_package_unchanged() -> None:
    base_package = prompt_brain.generate_higgsfield_prompt_package(
        DATE,
        SLOT_ID,
        "photo",
    )
    explicit_none_package = prompt_brain.generate_higgsfield_prompt_package(
        DATE,
        SLOT_ID,
        "photo",
        presence_contract=None,
    )

    assert base_package == explicit_none_package
    assert "human_presence" not in base_package
    assert base_package["negative_prompt_enabled"] is False
    assert base_package["negative_prompt"] == ""


def test_presence_enabled_prompt_package_emits_metadata_and_keeps_controlled_lane_state() -> None:
    contract = lena_profile.build_lena_presence_contract()
    package = prompt_brain.generate_higgsfield_prompt_package(
        DATE,
        SLOT_ID,
        "photo",
        required_recipe_id="hcr_012",
        presence_contract=contract,
    )

    assert package["lane"] == "mirror outfit check"
    assert package["environment_id"] == "env_v008"
    assert package["wardrobe_outfit_id"] == "wc_p050"
    assert package["negative_prompt_enabled"] is False
    assert package["negative_prompt"] == ""
    assert "Presence direction:" in package["image_prompt"]
    assert package["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"
    assert package["human_presence"]["medium_interpretation"] == "still_image"
    assert package["human_presence"]["selector_weight_adjustments_changed"] is True
    assert "silent pre-response beat" in package["human_presence"]["speech_behavior"]["directive"]


def test_still_image_presence_plan_is_performance_driven_and_preserves_anatomy_continuity() -> None:
    contract = lena_profile.build_lena_presence_contract()
    compiled = plan.compile_human_presence_prompt_plan(contract, medium="still_image")

    sensual_terms = " ".join(compiled["sensual_presence"]["selector_terms"])
    assert "exposure" not in sensual_terms
    assert "gaze" in sensual_terms
    assert "movement" in sensual_terms
    assert "confidence" in sensual_terms
    assert "timing" in sensual_terms
    assert compiled["body_presentation"]["contract"]["anatomy_continuity_required"] is True
    assert compiled["body_presentation"]["contract"]["gravity_and_soft_tissue_realism"] is True


def test_presence_report_survives_through_dry_run_report() -> None:
    contract = lena_profile.build_lena_presence_contract()
    report = photo_dump.build_report(
        DATE,
        "lenagate20260715085620d1-pack000",
        1,
        required_recipe_id="hcr_012",
        presence_contract=contract,
    )

    assert report["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"
    assert report["human_presence"]["medium_interpretation"] == "still_image"
    assert report["images"][0]["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"
    assert "Presence direction:" in report["images"][0]["image_prompt"]
    assert report["images"][0]["lane"] == "mirror outfit check"
    assert report["images"][0]["environment_id"] == "env_v008"
    assert report["images"][0]["wardrobe_outfit_id"] == "wc_p050"
