from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import tools.strategy.lena_build_world_state_v1 as world_state


DATE = "2026-07-14"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _recipe_bank() -> dict:
    return {
        "recipes": [
            {
                "id": "hcr_001",
                "title": "Mirror proof",
                "scene_type": "mirror selfie",
                "content_pillar": "trust",
                "proof_priority": 1,
                "production_proof_mode": True,
                "production_status": "active",
                "wardrobe_outfit_id": "wc_001",
                "environment_id": "env_001",
            },
            {
                "id": "hcr_002",
                "title": "City night",
                "scene_type": "night out",
                "content_pillar": "identity",
                "proof_priority": 4,
                "production_proof_mode": False,
                "production_status": "active",
                "wardrobe_outfit_id": "wc_002",
                "environment_id": "env_002",
            },
            {
                "id": "hcr_003",
                "title": "Gym routine",
                "scene_type": "workout",
                "content_pillar": "reach",
                "proof_priority": 5,
                "production_proof_mode": False,
                "production_status": "active",
                "wardrobe_outfit_id": "wc_003",
                "environment_id": "env_003",
            },
        ]
    }


def _wardrobe_catalog() -> dict:
    return {
        "outfits": [
            {"outfit_id": "wc_001", "name": "Mirror Set", "style_lane": "mirror_fitcheck", "occasion": "home", "status": "approved"},
            {"outfit_id": "wc_002", "name": "Night Dress", "style_lane": "night_out", "occasion": "public", "status": "approved"},
            {"outfit_id": "wc_003", "name": "Gym Set", "style_lane": "fitness", "occasion": "fitness", "status": "approved"},
        ]
    }


def _environment_catalog() -> dict:
    return {
        "environments": [
            {"environment_id": "env_001", "name": "Apartment Mirror", "production_lane": "mirror_fitcheck", "prompt_fragment": "mirror apartment", "status": "approved"},
            {"environment_id": "env_002", "name": "City Rooftop", "production_lane": "public_world", "prompt_fragment": "city rooftop venue", "status": "approved"},
            {"environment_id": "env_003", "name": "Gym Floor", "production_lane": "fitness", "prompt_fragment": "gym floor", "status": "approved"},
        ]
    }


def _continuity_policy() -> dict:
    return {
        "state_path": "pipeline/state/lena_world_state_v1.json",
        "recent_memory_window": 10,
        "balance_window": 8,
        "rotation_preview_limit": 3,
        "anti_repetition": {
            "avoid_back_to_back_same_recipe": True,
            "avoid_back_to_back_same_scene_type": True,
            "avoid_back_to_back_same_environment_id": True,
            "avoid_back_to_back_same_outfit_id": True,
            "soft_caps": {
                "same_recipe_in_recent_window": 1,
                "same_scene_type_in_recent_window": 2,
                "same_environment_id_in_recent_window": 1,
                "same_outfit_id_in_recent_window": 1,
                "same_environment_lane_in_recent_window": 2,
                "same_style_lane_in_recent_window": 2,
                "same_content_pillar_in_recent_window": 3,
                "mirror_lane_in_balance_window": 2,
                "proof_mode_in_balance_window": 2,
            },
        },
        "context_mix_targets": {
            "max_home_share_in_balance_window": 0.5,
            "min_public_or_fitness_share_in_balance_window": 0.375,
        },
        "candidate_scoring": {
            "public_balance_bonus": 18,
            "fresh_content_pillar_bonus": 8,
            "fresh_style_lane_bonus": 6,
            "non_proof_rotation_bonus": 10,
            "proof_priority_bonus_ceiling": 8,
            "home_overuse_penalty": 18,
            "proof_mode_overuse_penalty": 22,
            "same_recipe_penalty": 30,
            "same_scene_type_penalty": 24,
            "same_environment_penalty": 20,
            "same_outfit_penalty": 18,
            "same_environment_lane_penalty": 14,
            "same_style_lane_penalty": 10,
            "same_content_pillar_penalty": 8,
            "mirror_lane_penalty": 22,
        },
        "queue_rotation_policy": {
            "deprioritize_if_score_below": 86,
            "prefer_top_n": 2,
        },
    }


def test_continuity_alerts_trigger_on_home_overuse_public_gap_and_proof_overuse() -> None:
    policy = _continuity_policy()
    recent = [
        {"context_class": "home", "production_proof_mode": True, "environment_lane": "mirror_fitcheck"},
        {"context_class": "home", "production_proof_mode": True, "environment_lane": "mirror_fitcheck"},
        {"context_class": "home", "production_proof_mode": True, "environment_lane": "mirror_fitcheck"},
        {"context_class": "public", "production_proof_mode": False, "environment_lane": "public_world"},
    ]
    summary = {
        "home_share": 0.75,
        "public_or_fitness_share": 0.25,
        "environment_lane_counts": {"mirror_fitcheck": 3},
    }

    alerts = world_state.continuity_alerts(summary, policy, recent)
    assert len(alerts) == 4
    assert any("Home-coded scenes are overrepresented" in alert for alert in alerts)
    assert any("outside-life proof" in alert for alert in alerts)
    assert any("Mirror-fitcheck usage is too concentrated" in alert for alert in alerts)
    assert any("Proof-mode lanes are crowding" in alert for alert in alerts)


def test_candidate_row_respects_recommendation_binding_and_orders_broader_candidates() -> None:
    policy = _continuity_policy()
    summary = {
        "recipe_counts": {"hcr_001": 1},
        "scene_type_counts": {"mirror selfie": 2},
        "outfit_counts": {"wc_001": 2},
        "environment_counts": {"env_001": 2},
        "environment_lane_counts": {"mirror_fitcheck": 3},
        "style_lane_counts": {"mirror_fitcheck": 3},
        "content_pillar_counts": {"trust": 4},
        "home_share": 0.75,
        "public_or_fitness_share": 0.25,
    }
    recent = [
        {
            "recipe_id": "hcr_001",
            "scene_type": "mirror selfie",
            "outfit_id": "wc_001",
            "environment_id": "env_001",
            "environment_lane": "mirror_fitcheck",
            "style_lane": "mirror_fitcheck",
            "content_pillar": "trust",
            "production_proof_mode": True,
        }
    ] * 3

    proof_row = world_state.candidate_row(
        _recipe_bank()["recipes"][0],
        _wardrobe_catalog()["outfits"][0],
        _environment_catalog()["environments"][0],
        recent,
        summary,
        policy,
        "hcr_001",
    )
    city_row = world_state.candidate_row(
        _recipe_bank()["recipes"][1],
        _wardrobe_catalog()["outfits"][1],
        _environment_catalog()["environments"][1],
        recent,
        summary,
        policy,
        "hcr_001",
    )
    gym_row = world_state.candidate_row(
        _recipe_bank()["recipes"][2],
        _wardrobe_catalog()["outfits"][2],
        _environment_catalog()["environments"][2],
        recent,
        summary,
        policy,
        "hcr_001",
    )

    assert "currently locked as the immediate proof/debug lane" in proof_row["reasons"]
    assert proof_row["blocked"] is True
    assert city_row["blocked"] is False
    assert gym_row["blocked"] is False
    ordered = sorted(
        [city_row, gym_row],
        key=lambda row: (-row["score"], row["proof_priority"] is None, row["proof_priority"] or 999, row["recipe_id"]),
    )
    assert [row["recipe_id"] for row in ordered] == ["hcr_002", "hcr_003"]


def test_canonical_state_payload_is_stable() -> None:
    payload = world_state.canonical_state_payload(
        {
            "generated_at": "2026-07-14T12:00:00+00:00",
            "date": DATE,
            "calendar": {"season": "summer"},
            "continuity_alerts": ["outside-life proof"],
            "continuity_snapshot": {
                "last_recipe_id": "hcr_001",
                "last_outfit_id": "wc_001",
                "last_environment_id": "env_001",
                "recent_counts": {"home_share": 0.5},
            },
            "queue_rotation_controls": {
                "blocked_recipe_ids": ["hcr_001"],
                "deprioritized_recipe_ids": ["hcr_003"],
                "prefer_recipe_ids": ["hcr_002"],
            },
        },
        Path("pipeline/state/lena_world_state_v1.json"),
    )
    assert payload == {
        "version": "v1",
        "updated_at": "2026-07-14T12:00:00+00:00",
        "date": DATE,
        "season": "summer",
        "latest_reviewed_recipe_id": "hcr_001",
        "latest_reviewed_outfit_id": "wc_001",
        "latest_reviewed_environment_id": "env_001",
        "continuity_alerts": ["outside-life proof"],
        "blocked_recipe_ids": ["hcr_001"],
        "deprioritized_recipe_ids": ["hcr_003"],
        "preferred_rotation_recipe_ids": ["hcr_002"],
        "recent_counts": {"home_share": 0.5},
        "state_path": "pipeline/state/lena_world_state_v1.json",
    }


def test_main_writes_world_state_report_with_recommendation_binding_and_safe_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions"
    node = tmp_path / "pipeline" / "influencer_nodes" / "lena"
    prompts = tmp_path / "pipeline" / "prompt_banks" / "lena"
    state_dir = tmp_path / "pipeline" / "state"

    _write_json(node / "world_continuity_policy_v1.json", _continuity_policy())
    _write_json(node / "persona.json", {"public_positioning": "warm creator", "identity_rule": "same Lena"})
    _write_json(node / "daily_cadence.json", {"daily_posts": 5})
    _write_json(node / "content_buckets.json", {"buckets": {"trust": {"purpose": "trust"}}})
    _write_json(node / "life_engine_realism_memory_policy_v1.json", {"memory_path": "pipeline/state/lena_life_engine_realism_memory_v1.json"})
    _write_json(tmp_path / "pipeline" / "config" / "lena_generation_policy.json", {"anti_repetition": {"avoid_back_to_back_media_type": True}})
    _write_json(prompts / "lena_high_caliber_prompt_recipe_bank_v1.json", _recipe_bank())
    _write_json(prompts / "lena_wardrobe_catalog_v1.json", _wardrobe_catalog())
    _write_json(prompts / "lena_environment_catalog_v1.json", _environment_catalog())
    _write_json(
        state_dir / "lena_life_engine_realism_memory_v1.json",
        {
            "entries": [
                {"recipe_id": "hcr_001", "outfit_id": "wc_001", "environment_id": "env_001", "date": "2026-07-10", "logged_at": "1", "qa_status": "approved"},
                {"recipe_id": "hcr_001", "outfit_id": "wc_001", "environment_id": "env_001", "date": "2026-07-11", "logged_at": "2", "qa_status": "approved"},
                {"recipe_id": "hcr_001", "outfit_id": "wc_001", "environment_id": "env_001", "date": "2026-07-12", "logged_at": "3", "qa_status": "approved"},
            ]
        },
    )
    _write_json(
        next_actions / DATE / f"lena_next_generation_step_{DATE}.json",
        {
            "recommendation": {
                "recommended_recipe_id": "hcr_001",
                "recommended_outfit_id": "wc_001",
                "recommended_environment_id": "env_001",
                "action_type": "collect_first_controlled_proof",
                "next_live_gate": "review",
            }
        },
    )

    monkeypatch.setattr(world_state, "ROOT", tmp_path)
    monkeypatch.setattr(world_state, "NODE", node)
    monkeypatch.setattr(world_state, "PROMPTS", prompts)
    monkeypatch.setattr(world_state, "STATE_DIR", state_dir)
    monkeypatch.setattr(world_state, "NEXT_ACTIONS", next_actions)
    monkeypatch.setattr(world_state, "POLICY_PATH", node / "world_continuity_policy_v1.json")
    monkeypatch.setattr(world_state, "PERSONA_PATH", node / "persona.json")
    monkeypatch.setattr(world_state, "CADENCE_PATH", node / "daily_cadence.json")
    monkeypatch.setattr(world_state, "BUCKETS_PATH", node / "content_buckets.json")
    monkeypatch.setattr(world_state, "GEN_POLICY_PATH", tmp_path / "pipeline" / "config" / "lena_generation_policy.json")
    monkeypatch.setattr(world_state, "REALISM_POLICY_PATH", node / "life_engine_realism_memory_policy_v1.json")
    monkeypatch.setattr(world_state, "RECIPE_BANK_PATH", prompts / "lena_high_caliber_prompt_recipe_bank_v1.json")
    monkeypatch.setattr(world_state, "WARDROBE_PATH", prompts / "lena_wardrobe_catalog_v1.json")
    monkeypatch.setattr(world_state, "ENV_PATH", prompts / "lena_environment_catalog_v1.json")
    monkeypatch.setattr(
        world_state,
        "datetime",
        type("FakeDateTime", (), {"now": staticmethod(lambda tz=None: datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc if tz else None))}),
    )
    monkeypatch.setattr(sys, "argv", ["world", "--date", DATE])

    assert world_state.main() == 0

    report_path = next_actions / DATE / f"lena_world_state_{DATE}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_type"] == "lena_world_state"
    assert report["version"] == "v1"
    assert report["immediate_locked_proof_lane"]["recipe_id"] == "hcr_001"
    assert report["broader_rotation_candidates"][0]["recipe_id"] == "hcr_002"
    assert report["queue_rotation_controls"]["prefer_recipe_ids"] == ["hcr_002", "hcr_003"]
    assert report["safe_operations"] == {
        "api_call_made": False,
        "generation_call_performed": False,
        "upload_performed": False,
        "queue_mutated": False,
        "publish_performed": False,
        "credentials_read": False,
    }
    canonical = json.loads((state_dir / "lena_world_state_v1.json").read_text(encoding="utf-8"))
    assert canonical["state_path"] == "pipeline/state/lena_world_state_v1.json"
