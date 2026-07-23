from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.strategy.lena_recommend_next_generation_step_v1 as recommend
import tools.strategy.lena_build_post_outcome_learning_state_v1 as learning


DATE = "2026-07-15"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(learning, "ROOT", tmp_path)
    monkeypatch.setattr(learning, "NODE", tmp_path / "pipeline" / "influencer_nodes" / "lena")
    monkeypatch.setattr(learning, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(learning, "MEMORY_POLICY", tmp_path / "pipeline" / "influencer_nodes" / "lena" / "life_engine_realism_memory_policy_v1.json")
    monkeypatch.setattr(learning, "POST_OUTCOME_POLICY", tmp_path / "pipeline" / "influencer_nodes" / "lena" / "post_outcome_learning_policy_v1.json")
    monkeypatch.setattr(learning, "DEFAULT_MEMORY_STATE", tmp_path / "pipeline" / "state" / "lena_life_engine_realism_memory_v1.json")


def _memory_policy_payload() -> dict:
    return {
        "version": "v1.0.0",
        "memory_path": "pipeline/state/lena_life_engine_realism_memory_v1.json",
        "autonomy_gate": {
            "required_before_broader_autonomous_generation": ["wins", "memory"],
            "autonomous_publishing_unlocked": False,
        },
    }


def _post_outcome_policy_payload() -> dict:
    return {
        "version": "v1.0.0",
        "manual_post_log_path": "pipeline/analytics/lena_manual_post_log_v2_7.csv",
        "post_metrics_path": "pipeline/analytics/lena_post_metrics_v1_6_1.csv",
        "publish_state_path": "pipeline/state/lena_r2_publish_state.json",
        "state_path": "pipeline/state/lena_post_outcome_learning_state_v1.json",
        "report_dir": "pipeline/strategy/lena/next_actions",
    }


def _memory_state_payload() -> dict:
    return {
        "version": "v1.0.0",
        "updated_at": "2026-07-15T12:00:00+00:00",
        "entries": [
            {
                "task_id": "1",
                "date": DATE,
                "recipe_id": "hcr_011",
                "outfit_id": "wc_p020",
                "environment_id": "env_v008",
                "provider": "higgsfield",
                "qa_status": "publishable_quality",
            },
            {
                "task_id": "2",
                "date": DATE,
                "recipe_id": "hcr_008",
                "outfit_id": "wc_p062",
                "environment_id": "env_r001",
                "provider": "higgsfield",
                "qa_status": "approved",
            },
            {
                "task_id": "3",
                "date": DATE,
                "recipe_id": "hcr_002",
                "outfit_id": "wc_p033",
                "environment_id": "env_s001",
                "provider": "higgsfield",
                "qa_status": "rejected",
            },
        ],
    }


def test_build_post_outcome_learning_state_writes_report_and_is_consumed_by_recommendation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _write_json(learning.MEMORY_POLICY, _memory_policy_payload())
    _write_json(learning.POST_OUTCOME_POLICY, _post_outcome_policy_payload())
    _write_json(learning.DEFAULT_MEMORY_STATE, _memory_state_payload())
    _write_json(tmp_path / "pipeline" / "analytics" / "lena_manual_post_log_v2_7.csv", {"entries": []})
    _write_json(tmp_path / "pipeline" / "analytics" / "lena_post_metrics_v1_6_1.csv", {"entries": []})

    monkeypatch.setattr(sys, "argv", ["learning", "--date", DATE])
    assert learning.main() == 0

    output_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_post_outcome_learning_state_{DATE}.json"
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["report_type"] == "lena_post_outcome_learning_state"
    assert report["date"] == DATE
    assert report["dry_run"] is True
    assert report["provider_call_enabled"] is False
    assert report["generation_call_performed"] is False
    assert report["api_call_made"] is False
    assert report["publishing_approval"] == "not_approved"
    assert report["published_post_count"] == 2
    assert report["metrics_resolution_summary"]["learning_status"] == "current"
    assert report["metrics_resolution_summary"]["current_count"] == 2
    assert report["learning_status"] == "current"
    assert report["learning_required_follow_up_action"] == "no_follow_up_required"
    assert report["queue_boosts"]["preferred_recipe_ids"] == ["hcr_008", "hcr_011"]
    assert report["safe_operations"] == {
        "api_call_made": False,
        "generation_call_performed": False,
        "upload_performed": False,
        "queue_mutated": False,
        "publish_performed": False,
        "credentials_read": False,
    }
    assert "C:\\projects\\ai\\content_bot" not in json.dumps(report, sort_keys=True)

    context = recommend.load_learning_context(str(output_path), DATE)
    assert context["learning_artifact_valid"] is True
    assert context["learning_status"] == "current"
    assert context["learning_required_follow_up_action"] == "no_follow_up_required"
    assert context["learning_published_post_count"] == 2
    assert context["learning_winner_post_count"] == 2
    assert context["learning_preferred_recipe_ids"] == ["hcr_008", "hcr_011"]
    assert context["learning_resolution_state_summary"]["learning_status"] == "current"

