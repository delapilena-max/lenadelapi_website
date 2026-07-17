from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_output_qa_v1 as qa_module
from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from pipeline.prompting import lena_prompt_brain as prompt_brain
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


DATE = "2026-07-17"
SLOT_ID = "hpe-closure-slot"
RECIPE_ID = "hcr_012"


def _mutate(contract: dict[str, object], path: tuple[str, ...], value: object) -> dict[str, object]:
    clone = deepcopy(contract)
    cursor: dict[str, object] = clone
    for key in path[:-1]:
        cursor = cursor[key]  # type: ignore[index]
    cursor[path[-1]] = value
    return clone


def _build(contract: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    plan = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")
    package = prompt_brain.generate_higgsfield_prompt_package(
        DATE,
        SLOT_ID,
        "photo",
        required_recipe_id=RECIPE_ID,
        presence_contract=contract,
    )
    return plan, package


def _base_contract() -> dict[str, object]:
    return lena_profile.build_lena_presence_contract()


@pytest.mark.parametrize(
    "item_id, path, value, section",
    [
        ("pose_prompt_influence", ("performance_actions", "primary_action"), "turn_toward_camera", "performance_actions"),
        ("gaze_prompt_influence", ("gaze_arc", "start_focus"), "already_on_camera", "gaze_arc"),
        ("expression_prompt_influence", ("expression_arc", "peak_state"), "warm_smile", "expression_arc"),
        ("body_language_prompt_influence", ("movement_dynamics", "weight_transfer"), "step_and_settle", "movement_dynamics"),
        ("object_interaction_prompt_influence", ("performance_actions", "object_interaction"), "drink_or_cup", "performance_actions"),
        ("viewer_relationship_prompt_influence", ("viewer_relationship", "awareness"), "half_aware_glancing", "viewer_relationship"),
        ("sensual_presence_prompt_influence", ("sensual_presence", "tier"), "understated_confidence", "sensual_presence"),
    ],
)
def test_each_supported_dimension_changes_expected_prompt_region(
    item_id: str,
    path: tuple[str, ...],
    value: object,
    section: str,
) -> None:
    base_contract = _base_contract()
    mutated_contract = _mutate(base_contract, path, value)

    base_plan, base_package = _build(base_contract)
    mutated_plan, mutated_package = _build(mutated_contract)

    assert base_plan["prompt_text"] != mutated_plan["prompt_text"]
    assert base_package["human_presence_public_text"] != mutated_package["human_presence_public_text"]
    assert base_package["human_presence"] == base_plan
    assert mutated_package["human_presence"] == mutated_plan
    assert base_package["human_presence_public_text"] == base_plan["prompt_text"]
    assert mutated_package["human_presence_public_text"] == mutated_plan["prompt_text"]
    assert base_package["lane"] == mutated_package["lane"] == "mirror outfit check"
    assert base_package["soul_name"] == mutated_package["soul_name"] == "Lena"
    assert base_package["soul_selection_mode"] == mutated_package["soul_selection_mode"] == "provider_config_not_prompt_text"
    assert base_package["negative_prompt"] == mutated_package["negative_prompt"]
    assert base_package["image_prompt"].count("Presence direction:") == 1
    assert mutated_package["image_prompt"].count("Presence direction:") == 1
    assert base_plan[section]["directive"] != mutated_plan[section]["directive"]
    assert base_package["human_presence_public_text"] in base_package["image_prompt"]
    assert mutated_package["human_presence_public_text"] in mutated_package["image_prompt"]


def test_environment_interaction_is_classified_as_temporal_only_for_still_image() -> None:
    contract = _base_contract()
    plan, package = _build(contract)

    assert plan["temporal_beats"]["directive"]
    assert plan["temporal_beats"]["selector_terms"]
    assert package["human_presence_public_text"] == plan["prompt_text"]
    assert plan["temporal_beats"]["directive"] in package["human_presence_public_text"]
    assert "multi-frame" not in package["human_presence_public_text"].lower()


def test_failure_indicators_are_qa_only_and_not_prompt_influence() -> None:
    contract = _base_contract()
    plan, package = _build(contract)

    assert plan["failure_indicators"]
    assert set(plan["failure_indicators"]).issubset(
        {
            "dead_or_unfocused_eyes",
            "frozen_expression",
            "mannequin_pose",
            "unmotivated_movement",
            "continuous_camera_stare",
            "robotic_dialogue",
            "repeated_gesture_loop",
            "abrupt_motion_start_or_stop",
            "face_body_emotion_mismatch",
            "no_viewer_recognition_event",
            "sexual_styling_without_personality",
        }
    )
    assert "failure_indicators" not in package["human_presence_public_text"]
    assert "failure_indicators.dead_or_unfocused_eyes" in qa_module._STILL_IMAGE_PLAN_FIELD_ALLOWLIST
    assert "failure_indicators.mannequin_pose" in qa_module._STILL_IMAGE_PLAN_FIELD_ALLOWLIST
    assert qa_module._SEMANTIC_FINDING_TO_PLAN_REF["dead_eye_presence"] == "failure_indicators.dead_or_unfocused_eyes"
    assert qa_module._SEMANTIC_FINDING_TO_PLAN_REF["frozen_expression_presence"] == "failure_indicators.frozen_expression"
    assert qa_module._SEMANTIC_FINDING_TO_PLAN_REF["mannequin_pose_presence"] == "failure_indicators.mannequin_pose"
