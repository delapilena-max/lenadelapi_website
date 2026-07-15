from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import tools.strategy.lena_build_autonomous_generation_queue_dryrun_v1 as queue_builder


DATE = "2026-07-14"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _recipe_bank(path: Path) -> None:
    _write_json(
        path,
        {
            "recipes": [
                {
                    "id": "hcr_011",
                    "proof_priority": 1,
                    "production_proof_mode": True,
                    "production_status": "active",
                },
                {
                    "id": "hcr_005",
                    "proof_priority": 5,
                    "production_proof_mode": False,
                    "production_status": "active",
                },
                {
                    "id": "hcr_002",
                    "proof_priority": 7,
                    "production_proof_mode": False,
                    "production_status": "active",
                },
            ]
        },
    )


def _audit_payload(*, broader_ready: bool = False) -> dict:
    return {
        "report_type": "lena_autonomous_generation_readiness_audit",
        "date": DATE,
        "memory_progress": {
            "wins_logged": 1,
            "face_skin_wins_logged": 0,
            "garment_stability_wins_logged": 1,
            "broader_autonomous_generation_ready": broader_ready,
            "autonomous_publishing_unlocked": False,
        },
        "lanes": [
            {
                "recipe_id": "hcr_005",
                "title": "Public proof",
                "scene_type": "rooftop",
                "autonomy_grade": "ready",
                "payload_headroom": 160,
                "outfit_used": "wc_a",
                "environment_used": "env_a",
                "autonomy_reasons": ["ready lane"],
                "packet_path": "pipeline/strategy/lena/content_packets/2026-07-14/hcr_005.json",
            },
            {
                "recipe_id": "hcr_011",
                "title": "Face proof",
                "scene_type": "mirror",
                "autonomy_grade": "ready",
                "payload_headroom": 140,
                "outfit_used": "wc_b",
                "environment_used": "env_b",
                "autonomy_reasons": ["ready lane"],
                "packet_path": "pipeline/strategy/lena/content_packets/2026-07-14/hcr_011.json",
            },
            {
                "recipe_id": "hcr_002",
                "title": "Street backup",
                "scene_type": "street",
                "autonomy_grade": "ready_with_warnings",
                "payload_headroom": 40,
                "outfit_used": "wc_c",
                "environment_used": "env_c",
                "autonomy_reasons": ["warning lane"],
                "packet_path": "pipeline/strategy/lena/content_packets/2026-07-14/hcr_002.json",
            },
        ],
    }


def _world_state_payload() -> dict:
    return {
        "report_type": "lena_world_state",
        "date": DATE,
        "queue_rotation_controls": {
            "blocked_recipe_ids": [],
            "deprioritized_recipe_ids": ["hcr_002"],
            "prefer_recipe_ids": ["hcr_005"],
            "reasons_by_recipe": {
                "hcr_005": ["outside-world continuity needed"],
                "hcr_002": ["temporarily repetitive"],
            },
        },
    }


def _engagement_payload() -> dict:
    return {
        "report_type": "lena_engagement_demand_state",
        "date": DATE,
        "queue_boosts": {
            "boost_by_recipe_id": {"hcr_005": 9},
            "reasons_by_recipe": {"hcr_005": ["comments favor public lane"]},
        },
    }


def _post_outcome_payload() -> dict:
    return {
        "report_type": "lena_post_outcome_learning_state",
        "date": DATE,
        "metrics_resolution_summary": {"learning_status": "current"},
        "queue_boosts": {
            "preferred_recipe_ids": ["hcr_011"],
            "boost_by_recipe_id": {"hcr_011": 6},
            "reasons_by_recipe": {"hcr_011": ["winner follow-up"]},
        },
    }


def _next_step_payload(action_type: str = "collect_first_controlled_proof") -> dict:
    return {
        "report_type": "lena_next_generation_step",
        "date": DATE,
        "learning_status": "current",
        "recommendation": {
            "action_type": action_type,
            "recommended_recipe_id": "hcr_011",
            "recommended_outfit_id": "wc_b",
            "recommended_environment_id": "env_b",
            "next_live_gate": "review",
        },
    }


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions"
    recipe_bank = tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_high_caliber_prompt_recipe_bank_v1.json"
    monkeypatch.setattr(queue_builder, "ROOT", tmp_path)
    monkeypatch.setattr(queue_builder, "NEXT_ACTIONS", next_actions)
    monkeypatch.setattr(queue_builder, "RECIPE_BANK", recipe_bank)
    return next_actions, recipe_bank


def test_build_queue_is_deterministic_and_applies_boosts_and_penalties(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    next_actions, recipe_bank = _patch_layout(monkeypatch, tmp_path)
    _recipe_bank(recipe_bank)
    date_dir = next_actions / DATE
    _write_json(date_dir / f"lena_autonomous_generation_readiness_audit_{DATE}.json", _audit_payload())
    _write_json(date_dir / f"lena_world_state_{DATE}.json", _world_state_payload())
    _write_json(date_dir / f"lena_engagement_demand_state_{DATE}.json", _engagement_payload())
    _write_json(date_dir / f"lena_post_outcome_learning_state_{DATE}.json", _post_outcome_payload())
    _write_json(date_dir / f"lena_next_generation_step_{DATE}.json", _next_step_payload())

    monkeypatch.setattr(
        queue_builder,
        "datetime",
        type("FakeDateTime", (), {"now": staticmethod(lambda tz=None: datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc if tz else None))}),
    )
    monkeypatch.setattr(sys, "argv", ["queue", "--date", DATE, "--limit", "3"])

    assert queue_builder.main() == 0

    report_path = next_actions / DATE / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_type"] == "lena_autonomous_generation_queue_dryrun"
    assert report["version"] == "v1"
    assert report["dry_run"] is True
    assert report["provider_call_enabled"] is False
    assert report["generation_call_performed"] is False
    assert report["api_call_made"] is False
    assert report["publishing_approval"] == "not_approved"
    assert report["safe_operations"] == {
        "api_call_made": False,
        "generation_call_performed": False,
        "upload_performed": False,
        "queue_mutated": False,
        "publish_performed": False,
        "credentials_read": False,
    }
    assert report["proof_lane_lock_active"] is True
    assert [row["recipe_id"] for row in report["queue_slots"]] == ["hcr_011", "hcr_005", "hcr_002"]
    assert report["queue_slots"][0]["proof_lane_locked"] is True
    assert report["queue_slots"][0]["why"][0] == "matches current proof-lane lock from next-step recommendation"
    assert "post-outcome note: winner follow-up" in report["queue_slots"][0]["why"]
    assert "engagement-state note: comments favor public lane" in report["queue_slots"][1]["why"]
    assert any("temporarily repetitive" in reason for reason in report["queue_slots"][2]["why"])
    assert report["queue_slots"][2]["recommended_handoff_command"] == (
        f"python tools/strategy/lena_build_next_live_image_handoff_v1.py --date {DATE}"
    )


def test_rotation_preview_excludes_locked_recipe_and_repeated_outfits() -> None:
    queue = [
        {
            "recipe_id": "hcr_011",
            "title": "locked",
            "scene_type": "mirror",
            "outfit_used": "wc_b",
            "environment_used": "env_b",
            "payload_headroom": 120,
            "proof_priority": 1,
            "priority_score": 140,
            "why": ["locked"],
            "production_proof_mode": True,
        },
        {
            "recipe_id": "hcr_005",
            "title": "first open",
            "scene_type": "street",
            "outfit_used": "wc_a",
            "environment_used": "env_a",
            "payload_headroom": 150,
            "proof_priority": 3,
            "priority_score": 130,
            "why": ["open"],
            "production_proof_mode": False,
        },
        {
            "recipe_id": "hcr_002",
            "title": "duplicate outfit",
            "scene_type": "street",
            "outfit_used": "wc_a",
            "environment_used": "env_c",
            "payload_headroom": 151,
            "proof_priority": 4,
            "priority_score": 129,
            "why": ["open"],
            "production_proof_mode": False,
        },
    ]

    preview = queue_builder.build_rotation_preview(
        {"memory_progress": {}, "lanes": []},
        DATE,
        exclude_recipe_id="hcr_011",
        exclude_outfit_id="wc_b",
        limit=4,
    )
    assert preview == []

    original = queue_builder.build_queue
    try:
        queue_builder.build_queue = lambda *args, **kwargs: queue
        preview = queue_builder.build_rotation_preview(
            {"memory_progress": {}, "lanes": []},
            DATE,
            exclude_recipe_id="hcr_011",
            exclude_outfit_id="wc_b",
            limit=4,
        )
    finally:
        queue_builder.build_queue = original

    assert [row["recipe_id"] for row in preview] == ["hcr_005"]


def test_proof_lane_lock_is_suppressed_after_broader_ready_except_explicit_proof_actions() -> None:
    audit = {"memory_progress": {"broader_autonomous_generation_ready": True}}
    assert queue_builder.should_apply_proof_lane_lock(
        audit,
        {"recipe_id": "hcr_011", "action_type": "collect_first_controlled_proof"},
    ) is True
    assert queue_builder.should_apply_proof_lane_lock(
        audit,
        {"recipe_id": "hcr_011", "action_type": "broader_rotation"},
    ) is False


def test_missing_malformed_and_date_mismatched_inputs_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    next_actions, recipe_bank = _patch_layout(monkeypatch, tmp_path)
    _recipe_bank(recipe_bank)
    date_dir = next_actions / DATE
    _write_json(date_dir / f"lena_autonomous_generation_readiness_audit_{DATE}.json", _audit_payload())
    _write_json(date_dir / f"lena_world_state_{DATE}.json", _world_state_payload())
    _write_json(date_dir / f"lena_post_outcome_learning_state_{DATE}.json", _post_outcome_payload())
    _write_json(date_dir / f"lena_next_generation_step_{DATE}.json", _next_step_payload())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queue",
            "--date",
            DATE,
            "--limit",
            "2",
            "--engagement-demand-path",
            str(date_dir / "missing_engagement.json"),
        ],
    )
    with pytest.raises(FileNotFoundError, match="missing_engagement.json"):
        queue_builder.main()

    _write_json(date_dir / f"lena_engagement_demand_state_{DATE}.json", _engagement_payload())
    (date_dir / f"lena_world_state_{DATE}.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["queue", "--date", DATE, "--limit", "2"])
    with pytest.raises(json.JSONDecodeError):
        queue_builder.main()

    _write_json(date_dir / f"lena_world_state_{DATE}.json", {**_world_state_payload(), "date": "2026-07-13"})
    with pytest.raises(SystemExit, match="date_mismatch"):
        queue_builder.main()
