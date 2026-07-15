from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.strategy.lena_recommend_next_generation_step_v1 as recommend
import tools.strategy.lena_run_strategy_autonomy_prep_v1 as prep


DATE = "2026-07-14"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _learning_report(
    *,
    date: str = DATE,
    status: str,
    preferred_recipe_ids: list[str] | None = None,
    published_post_count: int = 3,
    pending_metrics_count: int = 2,
    stale_pending_metrics_count: int = 1,
    winner_posts: list[dict] | None = None,
) -> dict:
    preferred_recipe_ids = preferred_recipe_ids or []
    winner_posts = winner_posts or []
    return {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": date,
        "published_post_count": published_post_count,
        "pending_metrics_posts": [{}] * pending_metrics_count,
        "stale_pending_metrics_posts": [{}] * stale_pending_metrics_count,
        "winner_posts": winner_posts,
        "queue_boosts": {"preferred_recipe_ids": preferred_recipe_ids},
        "metrics_resolution_summary": {
            "learning_status": status,
            "current_count": published_post_count - pending_metrics_count,
            "usable_but_incomplete_count": 1 if status == "usable_but_incomplete" else 0,
            "stale_unresolved_count": stale_pending_metrics_count if status == "stale_unresolved" else 0,
            "manual_or_future_capability_required_count": 1
            if status == "manual_or_future_capability_required"
            else 0,
        },
    }


def _learning_context(path: Path, expected_date: str = DATE) -> dict:
    return recommend.load_learning_context(str(path), expected_date)


def test_prep_builds_learning_before_recommendation_and_threads_exact_artifact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prep_root = tmp_path / "next_actions"
    monkeypatch.setattr(prep, "NEXT_ACTIONS", prep_root)

    calls: list[tuple[str, list[str]]] = []
    date = DATE
    learning_path = prep.post_outcome_path(date)
    next_step_path = prep.next_step_path(date)
    queue_path = prep.queue_path(date)
    audit_path = prep.audit_path(date)
    world_state_path = prep.world_state_path(date)
    engagement_demand_path = prep.engagement_demand_path(date)

    def fake_run_step(step: str, cmd: list[str]) -> dict:
        calls.append((step, cmd))
        if step == "build_post_outcome_learning_state":
            _write_json(learning_path, _learning_report(status="current"))
        elif step == "recommend_next_generation_step":
            _write_json(
                next_step_path,
                {
                    "report_type": "lena_next_generation_step",
                    "recommendation": {
                        "recommended_recipe_id": "",
                        "learning_artifact_path": str(learning_path),
                        "learning_status": "current",
                        "learning_availability": "available",
                        "learning_validation_state": "valid",
                        "learning_validation_error": "",
                        "learning_published_post_count": 3,
                        "learning_pending_metrics_count": 2,
                        "learning_stale_pending_metrics_count": 1,
                        "learning_resolution_state_summary": {"learning_status": "current"},
                        "learning_required_follow_up_action": "no_follow_up_required",
                    },
                },
            )
        elif step == "build_autonomous_generation_queue_dryrun":
            _write_json(queue_path, {"queue_slots": []})
        elif step == "audit_autonomous_generation_readiness":
            _write_json(audit_path, {"memory_progress": {"broader_autonomous_generation_ready": False}})
        elif step == "build_world_state":
            _write_json(world_state_path, {})
        elif step == "build_engagement_demand_state":
            _write_json(engagement_demand_path, {})
        return {
            "step": step,
            "ok": True,
            "returncode": 0,
            "cmd": cmd,
            "stdout_json": {},
            "stdout_tail": [],
            "stderr_tail": [],
        }

    monkeypatch.setattr(prep, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["prep", "--date", date, "--recipes", "recipe-a"])

    assert prep.main() == 0

    step_names = [step for step, _ in calls]
    assert step_names.index("build_post_outcome_learning_state") < step_names.index("recommend_next_generation_step")
    assert not any(step.startswith("build_kling_payload_dryrun") for step in step_names)
    assert not any(step.startswith("build_kling_video_payload_dryrun") for step in step_names)
    assert step_names.index("build_autonomous_generation_queue_dryrun") < step_names.index("build_next_live_image_handoff")
    assert "select_pre_generation_candidate" not in step_names

    recommend_cmd = next(cmd for step, cmd in calls if step == "recommend_next_generation_step")
    assert "--learning-artifact-path" in recommend_cmd
    assert str(learning_path) in recommend_cmd
    report = json.loads((prep_root / date / f"lena_strategy_autonomy_prep_{date}.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["summary"]["learning_artifact_path"] == str(learning_path)
    assert report["summary"]["learning_status"] == "current"
    assert report["summary"]["learning_pending_metrics_count"] == 2
    assert report["summary"]["payload_count"] == 0
    assert report["summary"]["video_payload_count"] == 0
    assert report["summary"]["provider_routing_mode"] == "higgsfield_forward_no_live"
    assert report["summary"]["next_live_handoff_script_present"] is True
    assert report["summary"]["next_live_handoff_blocker"] == ""


@pytest.mark.parametrize(
    "status,label,follow_up",
    [
        ("current", "learning_current", "no_follow_up_required"),
        ("usable_but_incomplete", "learning_degraded_incomplete", "complete_missing_metrics_or_refresh_learning"),
        ("stale_unresolved", "learning_stale_unresolved", "refresh_or_resolve_stale_unresolved_posts"),
        (
            "manual_or_future_capability_required",
            "learning_manual_or_future_capability_required",
            "manual_or_future_capability_resolution_required",
        ),
    ],
)
def test_load_learning_context_accepts_valid_statuses_and_preserves_counts(
    tmp_path: Path,
    status: str,
    label: str,
    follow_up: str,
) -> None:
    artifact = tmp_path / f"{status}.json"
    _write_json(
        artifact,
        _learning_report(
            status=status,
            preferred_recipe_ids=["recipe-a", "recipe-b"],
            winner_posts=[{"recipe_id": "recipe-a"}],
            published_post_count=4,
            pending_metrics_count=2,
            stale_pending_metrics_count=1,
        ),
    )

    context = _learning_context(artifact)

    assert context["learning_artifact_valid"] is True
    assert context["learning_availability"] == "available"
    assert context["learning_status"] == status
    assert context["learning_status_label"] == label
    assert context["learning_required_follow_up_action"] == follow_up
    assert context["learning_artifact_path"] == str(artifact)
    assert context["learning_published_post_count"] == 4
    assert context["learning_pending_metrics_count"] == 2
    assert context["learning_stale_pending_metrics_count"] == 1
    assert context["learning_resolution_state_summary"]["learning_status"] == status
    assert context["learning_preferred_recipe_ids"] == ["recipe-a", "recipe-b"]
    assert context["learning_winner_post_count"] == 1


@pytest.mark.parametrize(
    "artifact_name,payload,expected_validation_state,expected_error",
    [
        ("missing.json", None, "invalid", "learning_artifact_unavailable"),
        ("malformed.json", "{not json", "unreadable", "learning_artifact_unreadable"),
        (
            "wrong_type.json",
            {"report_type": "something_else", "date": DATE, "metrics_resolution_summary": {"learning_status": "current"}},
            "wrong_report_type",
            "learning_artifact_wrong_report_type",
        ),
        (
            "date_mismatch.json",
            {
                "report_type": "lena_post_outcome_learning_state",
                "date": "2026-07-13",
                "metrics_resolution_summary": {"learning_status": "current"},
            },
            "date_mismatch",
            "learning_artifact_date_mismatch",
        ),
    ],
)
def test_load_learning_context_fails_closed_on_missing_malformed_or_mismatched_inputs(
    tmp_path: Path,
    artifact_name: str,
    payload,
    expected_validation_state: str,
    expected_error: str,
) -> None:
    artifact = tmp_path / artifact_name
    if payload is None:
        pass
    elif isinstance(payload, str):
        artifact.write_text(payload, encoding="utf-8")
    else:
        _write_json(artifact, payload)

    context = _learning_context(artifact)

    assert context["learning_artifact_valid"] is False
    assert context["learning_availability"] == "unavailable"
    assert context["learning_status"] == "unavailable"
    assert context["learning_validation_state"] == expected_validation_state
    assert context["learning_validation_error"] == expected_error
    assert context["learning_required_follow_up_action"] == "rebuild_and_pass_an_explicit_learning_artifact"


def test_build_recommendation_uses_learning_signal_when_base_recipe_is_blank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "learning.json"
    _write_json(
        artifact,
        _learning_report(
            status="current",
            preferred_recipe_ids=["recipe-a", "recipe-missing"],
            published_post_count=3,
            pending_metrics_count=0,
            stale_pending_metrics_count=0,
        ),
    )
    monkeypatch.setattr(recommend, "recipe_exists", lambda recipe_id: recipe_id == "recipe-a")

    recommendation = recommend.build_recommendation({}, [], {}, _learning_context(artifact))

    assert recommendation["action_type"] == "collect_first_controlled_proof"
    assert recommendation["recommended_recipe_id"] == "recipe-a"
    assert recommendation["learning_status"] == "current"
    assert recommendation["learning_signal_used"] == ["queue_boosts.preferred_recipe_ids", "recommended_recipe_id_fallback"]
    assert recommendation["learning_required_follow_up_action"] == "no_follow_up_required"


def test_build_recommendation_keeps_blank_recipe_when_learning_has_no_actionable_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "learning.json"
    _write_json(
        artifact,
        _learning_report(
            status="usable_but_incomplete",
            preferred_recipe_ids=[],
            published_post_count=3,
            pending_metrics_count=1,
            stale_pending_metrics_count=0,
        ),
    )
    monkeypatch.setattr(recommend, "recipe_exists", lambda recipe_id: False)

    recommendation = recommend.build_recommendation({}, [], {}, _learning_context(artifact))

    assert recommendation["action_type"] == "collect_first_controlled_proof"
    assert recommendation["recommended_recipe_id"] == ""
    assert recommendation["learning_status"] == "usable_but_incomplete"
    assert recommendation["learning_signal_used"] == []


def test_build_recommendation_surfaces_stale_learning_and_follow_up_without_deadlocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "learning.json"
    _write_json(
        artifact,
        _learning_report(
            status="stale_unresolved",
            preferred_recipe_ids=["recipe-a"],
            published_post_count=3,
            pending_metrics_count=1,
            stale_pending_metrics_count=1,
        ),
    )
    monkeypatch.setattr(recommend, "recipe_exists", lambda recipe_id: recipe_id == "recipe-a")

    recommendation = recommend.build_recommendation({}, [], {}, _learning_context(artifact))

    assert recommendation["recommended_recipe_id"] == "recipe-a"
    assert recommendation["learning_status"] == "stale_unresolved"
    assert recommendation["learning_required_follow_up_action"] == "refresh_or_resolve_stale_unresolved_posts"
    assert recommendation["rationale"][0] == "Outcome learning is stale unresolved."


def test_build_recommendation_surfaces_manual_or_future_capability_required_without_inventing_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "learning.json"
    _write_json(
        artifact,
        _learning_report(
            status="manual_or_future_capability_required",
            preferred_recipe_ids=[],
            published_post_count=3,
            pending_metrics_count=1,
            stale_pending_metrics_count=0,
        ),
    )
    monkeypatch.setattr(recommend, "recipe_exists", lambda recipe_id: False)

    recommendation = recommend.build_recommendation({}, [], {}, _learning_context(artifact))

    assert recommendation["learning_status"] == "manual_or_future_capability_required"
    assert recommendation["learning_required_follow_up_action"] == "manual_or_future_capability_resolution_required"
    assert recommendation["learning_status_label"] == "learning_manual_or_future_capability_required"
    assert recommendation["learning_resolution_state_summary"]["learning_status"] == "manual_or_future_capability_required"


def test_build_recommendation_without_learning_artifact_reports_unavailable_truthfully() -> None:
    recommendation = recommend.build_recommendation({}, [], {}, recommend.load_learning_context("", DATE))

    assert recommendation["learning_artifact_valid"] is False
    assert recommendation["learning_status"] == "unavailable"
    assert recommendation["learning_availability"] == "unavailable"
    assert recommendation["learning_validation_state"] == "not_provided"
    assert recommendation["learning_required_follow_up_action"] == "rebuild_and_pass_an_explicit_learning_artifact"
    assert recommendation["rationale"][0] == "Outcome learning is unavailable for this recommendation."


def test_recommend_main_writes_date_on_authoritative_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_path = tmp_path / "policy.json"
    memory_path = tmp_path / "pipeline" / "state" / "memory.json"
    output_base = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions"
    world_state = tmp_path / "pipeline" / "state" / "lena_world_state_v1.json"
    learning_artifact = tmp_path / "learning.json"

    _write_json(
        policy_path,
        {
            "memory_path": "pipeline/state/memory.json",
            "autonomy_gate": {
                "required_before_broader_autonomous_generation": [],
                "autonomous_publishing_unlocked": False,
            },
        },
    )
    _write_json(
        memory_path,
        {
            "entries": [
                {
                    "qa_status": "approved",
                    "recipe_id": "recipe-a",
                    "date": DATE,
                    "skin_face_realism_notes": ["face reads believable"],
                    "wardrobe_construction_notes": ["single garment continuity held"],
                }
            ]
        },
    )
    _write_json(world_state, {})
    _write_json(
        learning_artifact,
        _learning_report(
            status="current",
            preferred_recipe_ids=["recipe-a"],
            published_post_count=1,
            pending_metrics_count=0,
            stale_pending_metrics_count=0,
        ),
    )

    monkeypatch.setattr(recommend, "POLICY", policy_path)
    monkeypatch.setattr(recommend, "ROOT", tmp_path)
    monkeypatch.setattr(recommend, "WORLD_STATE", world_state)
    monkeypatch.setattr(recommend, "OUTPUT_BASE", output_base)
    monkeypatch.setattr(recommend, "recipe_exists", lambda recipe_id: recipe_id == "recipe-a")
    monkeypatch.setattr(
        recommend,
        "build_recommendation",
        lambda *_args, **_kwargs: {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": "recipe-a",
            "recommended_outfit_id": "wc_a",
            "recommended_environment_id": "env_a",
            "next_live_gate": "review",
            "learning_artifact_path": str(learning_artifact),
            "learning_status": "current",
            "learning_availability": "available",
            "learning_required_follow_up_action": "no_follow_up_required",
        },
    )
    monkeypatch.setattr(sys, "argv", ["recommend", "--date", DATE, "--learning-artifact-path", str(learning_artifact)])

    assert recommend.main() == 0

    report_path = output_base / DATE / f"lena_next_generation_step_{DATE}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["date"] == DATE
    assert report["report_type"] == "lena_next_generation_step"
