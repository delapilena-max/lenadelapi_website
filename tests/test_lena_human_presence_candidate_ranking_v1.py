from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_candidate_ranking_v1 as ranking
from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


def _compiled_plan() -> dict:
    contract = lena_profile.build_lena_presence_contract()
    return plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")


def _observation_from_plan(plan: dict) -> dict[str, str]:
    def join_terms(section: str) -> str:
        return " ".join(plan[section]["selector_terms"])

    return {
        "lane": join_terms("viewer_relationship"),
        "scene_action": join_terms("temporal_beats"),
        "activity": f"{join_terms('viewer_relationship')} {join_terms('temporal_beats')}".strip(),
        "reference_mode": " ".join(
            plan["body_presentation"]["selector_terms"][:2] + plan["viewer_relationship"]["selector_terms"][:2]
        ),
        "camera_text": " ".join(plan["viewer_relationship"]["selector_terms"] + plan["movement_dynamics"]["selector_terms"]),
        "lighting_text": " ".join(plan["sensual_presence"]["selector_terms"]),
        "environment_id": "env_v008",
        "environment_name": " ".join(plan["viewer_relationship"]["selector_terms"]),
        "expression_gaze_id": " ".join(plan["gaze_arc"]["selector_terms"][:3]),
        "expression_gaze_label": " ".join(plan["gaze_arc"]["selector_terms"]),
        "expression_text": " ".join(plan["expression_arc"]["selector_terms"]),
        "pose_body_language_id": " ".join(plan["performance_actions"]["selector_terms"]),
        "pose_body_language_label": " ".join(plan["movement_dynamics"]["selector_terms"]),
        "wardrobe_silhouette_class": " ".join(plan["body_presentation"]["selector_terms"]),
        "effective_wardrobe_silhouette_class": " ".join(plan["sensual_presence"]["selector_terms"]),
        "framing_text": " ".join(plan["body_presentation"]["selector_terms"]),
        "caption_seed": " ".join(plan["temporal_beats"]["selector_terms"]),
    }


def test_presence_ranker_source_is_generic_and_contains_no_lena_specific_identifiers() -> None:
    source = Path(ranking.__file__).read_text(encoding="utf-8")
    forbidden = (
        "Lena",
        "hcr_",
        "mirror outfit check",
        "env_v008",
        "wc_p050",
        "fit_check_mirror_getting_ready",
    )
    assert not any(term in source for term in forbidden)


def test_presence_alignment_is_deterministic_and_rewarded_by_structured_metadata() -> None:
    plan = _compiled_plan()
    observation = _observation_from_plan(plan)

    first = ranking.score_candidate_presence_alignment(plan, observation)
    second = ranking.score_candidate_presence_alignment(copy.deepcopy(plan), copy.deepcopy(observation))

    assert first == second
    assert first["plan_fingerprint_sha256"] == ranking.plan_fingerprint_sha256(plan)
    assert first["total_bonus"] > 0
    assert all(0 <= value <= ranking.MAX_BONUS_PER_DIMENSION for value in first["dimension_bonuses"].values())
    assert all(result["bonus"] <= ranking.MAX_BONUS_PER_DIMENSION for result in first["dimension_results"].values())


def test_prompt_text_noise_does_not_change_structured_presence_scoring() -> None:
    plan = _compiled_plan()
    observation = _observation_from_plan(plan)
    baseline = ranking.score_candidate_presence_alignment(plan, observation)
    noisy = ranking.score_candidate_presence_alignment(
        plan,
        dict(observation, image_prompt="Presence prompt text should be ignored by structured scoring."),
    )

    assert noisy["total_bonus"] == baseline["total_bonus"]
    assert noisy["dimension_bonuses"] == baseline["dimension_bonuses"]
    assert noisy["matched_selector_terms"] == baseline["matched_selector_terms"]


def test_missing_alignment_remains_zero_without_excluding_the_candidate() -> None:
    plan = _compiled_plan()
    score = ranking.score_candidate_presence_alignment(plan, {})

    assert score["total_bonus"] == 0
    assert score["dimension_bonuses"] == {
        "viewer_relationship": 0,
        "gaze_arc": 0,
        "expression_arc": 0,
        "performance_actions": 0,
        "movement_dynamics": 0,
        "sensual_presence": 0,
        "body_presentation": 0,
        "temporal_beats": 0,
    }
    assert score["matched_selector_terms"] == []
    assert all(result["bonus"] == 0 for result in score["dimension_results"].values())


def test_invalid_plan_schema_fails_closed() -> None:
    plan = _compiled_plan()
    plan["schema_version"] = "not_the_plan_schema"

    with pytest.raises(ranking.HumanPresenceCandidateRankingError) as error:
        ranking.plan_fingerprint_sha256(plan)

    assert error.value.code == "invalid_presence_plan"
