from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def test_legacy_video_prompt_package_path_remains_hpe_free(monkeypatch: pytest.MonkeyPatch) -> None:
    scene = {
        "lane": "night out",
        "action": "walking home",
        "camera": "steady mid shot",
        "lighting": "warm city lights",
        "caption": "night walk",
    }
    environment_entry = {
        "environment_id": "env_test",
        "name": "city street",
        "production_lane": "urban_night",
    }
    wardrobe_entry = {
        "outfit_id": "wc_test",
        "name": "black jacket",
        "style_lane": "going_out",
    }
    expression_entry = {
        "expression_gaze_id": "exp_test",
        "label": "soft smile",
    }
    pose_entry = {
        "pose_body_language_id": "pose_test",
        "label": "weight shift and settle",
        "hand_risk": "low",
        "compatibility_tags": ["standing", "walking"],
    }
    frame_logic = {
        "frame_action": "frame",
        "frame_evidence_objects": ["street"],
        "frame_forbidden_objects": [],
        "camera_intent": "mid shot",
        "scene_coherence_note": "coherent",
    }

    monkeypatch.setattr(prompt_brain, "validate_saved_prompt_sources", lambda: None)
    monkeypatch.setattr(prompt_brain, "get_production_scene_pool", lambda: ([scene], {"version": "test-bank", "source": "test-source"}))
    monkeypatch.setattr(prompt_brain, "choose_scene_production", lambda scene_pool, rng: scene_pool[0])
    monkeypatch.setattr(prompt_brain, "choose_environment_production", lambda scene, rng: environment_entry)
    monkeypatch.setattr(prompt_brain, "build_environment_prompt_parts", lambda scene, environment_entry: ("city street at night", "wet pavement"))
    monkeypatch.setattr(prompt_brain, "choose_reference_mode", lambda media_type, scene: "video_body")
    monkeypatch.setattr(prompt_brain, "pick_catalog_outfit_production", lambda lane, reference_mode, rng: wardrobe_entry)
    monkeypatch.setattr(prompt_brain, "format_catalog_wardrobe_override", lambda entry: "black jacket and dark jeans")
    monkeypatch.setattr(prompt_brain, "build_negative_prompt_for_catalog", lambda entry: "no blur")
    monkeypatch.setattr(prompt_brain, "build_public_lane_negative_prompt", lambda entry, lane, negative: negative)
    monkeypatch.setattr(prompt_brain, "choose_expression_gaze_production", lambda rng, lane=None: expression_entry)
    monkeypatch.setattr(prompt_brain, "format_expression_gaze_line", lambda entry: "Expression: soft smile.")
    monkeypatch.setattr(prompt_brain, "choose_frame_logic", lambda lane: frame_logic)
    monkeypatch.setattr(prompt_brain, "format_frame_logic_paragraph", lambda frame_logic, reference_mode: "Frame logic paragraph.")
    monkeypatch.setattr(prompt_brain, "choose_pose_body_language_production", lambda rng, lane=None, reference_mode=None, exclude_tags=None: pose_entry)
    monkeypatch.setattr(prompt_brain, "format_pose_body_language_line", lambda entry: "Pose: weight shift and settle.")
    monkeypatch.setattr(prompt_brain, "reference_policy_for_mode", lambda mode: "Reference policy.")
    monkeypatch.setattr(prompt_brain, "framing_policy_for_mode", lambda mode: "Framing policy.")
    monkeypatch.setattr(prompt_brain, "public_capture_lock", lambda lane: "Capture lock.")
    monkeypatch.setattr(prompt_brain, "public_wardrobe_continuity_lock", lambda wardrobe_entry, lane: "Wardrobe lock.")
    monkeypatch.setattr(prompt_brain, "build_body_visibility_rule", lambda reference_mode, frame_logic: "Body visibility rule.")
    monkeypatch.setattr(prompt_brain, "catalog_outfit_silhouette_class", lambda entry: "structured")
    monkeypatch.setattr(prompt_brain, "reference_priority_for_mode", lambda mode: "priority")
    monkeypatch.setattr(prompt_brain, "VIDEO_MOTIONS", ("steady handheld drift",))
    monkeypatch.setattr(prompt_brain, "_clean_public_text", lambda text: text)
    monkeypatch.setattr(prompt_brain, "_hashtags", lambda rng, lane, count: "#one #two #three")
    monkeypatch.setattr(prompt_brain, "SCENE_EVIDENCE_CONTRACTS", {})

    package = prompt_brain.generate_prompt_package(DATE, "legacy-video-slot", "video", sequence_index=0)

    expected_video_prompt = (
        "steady handheld drift. "
        "The scene is night out: walking home. "
        "Maintain realistic facial movement, natural blinking, stable identity, believable body motion, "
        "cinematic but restrained movement, no sudden cuts, no exaggerated gestures."
    )

    assert package["media_type"] == "video"
    assert package["lane"] == "night out"
    assert package["image_prompt"].startswith("Lena Delapi")
    assert package["video_prompt"] == expected_video_prompt
    assert package["motion_prompt"] == expected_video_prompt
    assert package["seed_image_prompt"] == package["image_prompt"]
    assert package["prompt_brain_version"] == "lena_prompt_brain_v1_9_frame_logic"
    assert package["duration_seconds"] == 7
    assert "Presence direction:" not in package["video_prompt"]
    assert "human_presence" not in package


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
    assert package["image_prompt"].count("Presence direction:") == 1
    assert package["human_presence"]["prompt_text"] in package["image_prompt"]
    assert package["human_presence_public_text"] == package["human_presence"]["prompt_text"]
    assert package["human_presence_public_text"] in package["image_prompt"]
    assert package["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"
    assert package["human_presence"]["medium_interpretation"] == "still_image"
    assert package["human_presence"]["selector_weight_adjustments_changed"] is True
    assert "silent pre-response beat" in package["human_presence"]["speech_behavior"]["directive"]

    no_presence_package = prompt_brain.generate_higgsfield_prompt_package(
        DATE,
        SLOT_ID,
        "photo",
        required_recipe_id="hcr_012",
    )
    assert no_presence_package["image_prompt"].count("Presence direction:") == 0
    assert "human_presence" not in no_presence_package
    assert "human_presence_public_text" not in no_presence_package


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
