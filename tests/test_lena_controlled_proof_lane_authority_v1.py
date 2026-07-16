from __future__ import annotations

import json
from pathlib import Path

import tools.strategy.lena_audit_autonomous_generation_readiness_v1 as audit
import tools.strategy.lena_build_autonomous_generation_queue_dryrun_v1 as queue_builder
import tools.strategy.lena_build_content_batch_dryrun_v1 as batch
import tools.strategy.lena_build_world_state_v1 as world
import tools.strategy.lena_pre_generation_candidate_gate_v1 as gate
import tools.strategy.lena_recommend_next_generation_step_v1 as recommend
import tools.strategy.lena_run_strategy_autonomy_prep_v1 as prep


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "pipeline" / "prompt_banks" / "lena"
SCENES = PROMPTS / "lena_photo_scene_bank_v1.json"
RECIPES = PROMPTS / "lena_high_caliber_prompt_recipe_bank_v1.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _image(*, slot_id: str, lane: str, outfit_id: str, environment_id: str, prompt: str) -> dict:
    return {
        "slot_id": slot_id,
        "lane": lane,
        "wardrobe_outfit_id": outfit_id,
        "pose_body_language_id": "pose_test",
        "pose_body_language_label": "relaxed candid pose",
        "effective_wardrobe_silhouette_class": "fitted_daywear",
        "soul_name": "Lena",
        "soul_version": "Soul 2.0",
        "soul_selection_mode": "provider_config_not_prompt_text",
        "camera_text": "50mm candid vertical",
        "lighting_text": "soft natural light",
        "image_prompt": prompt,
        "environment_id": environment_id,
        "validation": {
            "framing_present": True,
            "wardrobe_casual_free": True,
            "scene_action_conflict_free": True,
            "soul_anchor_absent": True,
            "negative_prompt_disabled": True,
            "heavy_overcorrection_free": True,
            "pose_scene_match_pass": True,
            "low_hook_terms_found": [],
        },
    }


def _curator(image: dict, *, total_score: int = 91) -> dict:
    return {"image": image, "total_score": total_score, "failure_memory_flag": None}


def _authorities() -> dict:
    return gate.load_authorities()


def test_controlled_proof_lane_metadata_keeps_hcr_011_warm_and_marks_hcr_012_controlled() -> None:
    recipes = read_json(RECIPES)["recipes"]
    hcr_011 = next(item for item in recipes if item["id"] == "hcr_011")
    hcr_012 = next(item for item in recipes if item["id"] == "hcr_012")
    scene_bank = read_json(SCENES)
    mirror_scene = next(item for item in scene_bank["scenes"] if item["lane"] == "mirror outfit check")

    assert hcr_011["creative_temperature"] == "warm"
    assert hcr_011.get("controlled_proof_lane", False) is False
    assert hcr_012["creative_temperature"] == "glamorous"
    assert hcr_012["controlled_proof_lane"] is True
    assert mirror_scene["creative_temperature"] == "glamorous"
    assert "mirror outfit check" in scene_bank["production_blocked_lanes"]


def test_controlled_proof_lane_is_first_in_prep_recommendation_queue_and_run_inputs() -> None:
    recipes = read_json(RECIPES)

    assert audit.default_priority_recipes()[0] == "hcr_012"
    assert prep.default_recipe_ids()[0] == "hcr_012"
    assert batch.default_recipe_ids(recipes)[0] == "hcr_012"
    assert world.active_recipes(recipes)[0]["id"] == "hcr_012"
    assert recommend.face_priority_proof_sequence()[:2] == ["hcr_012", "hcr_011"]
    assert recommend.select_next_face_proof_lane("hcr_012")[0] == "hcr_011"
    assert recommend.select_next_face_proof_lane("hcr_011", prefer_controlled_lane=True)[0] == "hcr_012"

    queue = queue_builder.build_queue(
        {
            "memory_progress": {
                "wins_logged": 0,
                "face_skin_wins_logged": 0,
                "garment_stability_wins_logged": 0,
            },
            "lanes": [
                {
                    "recipe_id": "hcr_011",
                    "title": "Face proof",
                    "scene_type": "mirror",
                    "autonomy_grade": "ready",
                    "payload_headroom": 140,
                    "outfit_used": "wc_p020",
                    "environment_used": "env_v008",
                    "autonomy_reasons": ["ready lane"],
                    "packet_path": f"pipeline/strategy/lena/content_packets/2026-07-15/hcr_011.json",
                },
                {
                    "recipe_id": "hcr_012",
                    "title": "Controlled face proof",
                    "scene_type": "mirror",
                    "autonomy_grade": "ready",
                    "payload_headroom": 140,
                    "outfit_used": "wc_p050",
                    "environment_used": "env_v008",
                    "autonomy_reasons": ["ready lane"],
                    "packet_path": f"pipeline/strategy/lena/content_packets/2026-07-15/hcr_012.json",
                },
            ],
        },
        "2026-07-15",
        limit=2,
    )
    assert [row["recipe_id"] for row in queue] == ["hcr_012", "hcr_011"]


def test_glamorous_mirror_scene_prefers_hcr_012_and_rejects_incompatible_required_recipe() -> None:
    authorities = _authorities()
    scene = authorities["scenes"]["mirror outfit check"]
    recipes = authorities["recipes"]
    recipe_011 = next(item for item in recipes if item["id"] == "hcr_011")
    recipe_012 = next(item for item in recipes if item["id"] == "hcr_012")
    selected_recipe = gate._best_recipe(scene, [recipe_011, recipe_012])

    assert selected_recipe is not None
    assert selected_recipe["id"] == "hcr_012"

    candidate = _curator(
        _image(
            slot_id="gate-pack000-00-photo",
            lane="mirror outfit check",
            outfit_id=recipe_012["wardrobe_outfit_id"],
            environment_id=recipe_012["environment_id"],
            prompt="Lena in a bedroom mirror outfit check with a relaxed candid pose and warm home light.",
        )
    )

    selected, reasons, saw_required = gate.select_candidate(
        authorities,
        [candidate],
        {"records": []},
    )

    assert selected is None
    assert saw_required is True
    assert "blocked_scene" in {item["reason"] for item in reasons}

    selected, reasons, saw_required = gate.select_candidate(
        authorities,
        [candidate],
        {"records": []},
        required_recipe_id="hcr_012",
    )

    assert saw_required is True
    assert selected is not None
    assert selected["recipe_id"] == "hcr_012"

    selected, reasons, saw_required = gate.select_candidate(
        authorities,
        [candidate],
        {"records": []},
        required_recipe_id="hcr_011",
    )

    assert selected is None
    assert saw_required is False
    assert "required_recipe_candidate_missing" in {item["reason"] for item in reasons}
