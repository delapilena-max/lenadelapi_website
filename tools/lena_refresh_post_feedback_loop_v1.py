from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
FOLLOWUP_POLICY = (
    ROOT
    / "pipeline"
    / "influencer_nodes"
    / "lena"
    / "followup_post_decision_policy_v1_7.json"
)
POST_OUTCOME_POLICY = (
    ROOT
    / "pipeline"
    / "influencer_nodes"
    / "lena"
    / "post_outcome_learning_policy_v1.json"
)

BUILD_ENGAGEMENT = ROOT / "tools" / "strategy" / "lena_build_engagement_demand_state_v1.py"
BUILD_OUTCOME = ROOT / "tools" / "strategy" / "lena_build_post_outcome_learning_state_v1.py"
BUILD_QUEUE = ROOT / "tools" / "strategy" / "lena_build_autonomous_generation_queue_dryrun_v1.py"
REVIEW_BRIDGE = ROOT / "tools" / "lena_review_metrics_engagement_bridge_v1_6_1.py"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def try_parse_json(text: str) -> dict | list | None:
    raw = (text or "").strip()
    if not raw or (not raw.startswith("{") and not raw.startswith("[")):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def tail_lines(text: str, limit: int = 20) -> list[str]:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if len(lines) <= limit:
        return lines
    return lines[-limit:]


def run_step(step: str, cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "step": step,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout_json": try_parse_json(proc.stdout),
        "stdout_tail": tail_lines(proc.stdout),
        "stderr_tail": tail_lines(proc.stderr),
    }


def post_outcome_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_post_outcome_learning_state_{date_str}.json"


def queue_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_autonomous_generation_queue_dryrun_{date_str}.json"


def report_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_post_feedback_loop_{date_str}.json"


def top_winner(outcome: dict) -> dict:
    winners = list(outcome.get("winner_posts", []))
    if not winners:
        return {}
    winners.sort(
        key=lambda row: (
            float(row.get("score") or 0),
            row.get("date", ""),
        ),
        reverse=True,
    )
    return winners[0]


def _post_key(item: dict) -> tuple[str, str, str]:
    return (item.get("date", ""), item.get("slot_id", ""), item.get("platform", ""))


def _stale_keys(outcome: dict) -> set[tuple[str, str, str]]:
    return {_post_key(item) for item in outcome.get("stale_pending_metrics_posts", [])}


def _derived_metrics_resolution_state(item: dict, stale_keys: set[tuple[str, str, str]]) -> str:
    state = (item.get("metrics_resolution_state") or "").strip()
    if state:
        return state
    classification = (item.get("classification") or "").strip().lower()
    if classification and classification not in {"pending", "missing"}:
        return "resolved"
    if _post_key(item) in stale_keys:
        return "pending_refreshable"
    return "pending_never_refreshed"


def _metrics_resolution_action(state: str) -> str:
    return {
        "resolved": "no_metrics_resolution_action",
        "manual_only_unverified": "manual_identity_or_metric_update_required",
        "pending_never_refreshed": "request_supported_meta_refresh",
        "pending_refreshable": "request_supported_meta_refresh",
        "pending_unsupported": "manual_or_future_capability_resolution_required",
        "refresh_failed": "retry_or_escalate_refresh",
    }.get(state, "manual_review_required")


def build_metrics_resolution_actions(outcome: dict) -> list[dict]:
    items = list(outcome.get("metrics_resolution_posts") or outcome.get("pending_metrics_posts", []))
    stale_keys = _stale_keys(outcome)
    actions: list[dict] = []
    for item in items:
        state = _derived_metrics_resolution_state(item, stale_keys)
        if state == "resolved":
            continue
        action = item.get("recommended_action") or _metrics_resolution_action(state)
        actions.append(
            {
                "type": "operations",
                "priority": 1 if item.get("is_stale") or _post_key(item) in stale_keys else 2,
                "action": action,
                "reason": item.get("metrics_resolution_reason", ""),
                "date": item.get("date", ""),
                "platform": item.get("platform", ""),
                "slot_id": item.get("slot_id", ""),
                "metrics_resolution_state": state,
                "is_stale": bool(item.get("is_stale") or _post_key(item) in stale_keys),
            }
        )
    actions.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("date", ""),
            item.get("platform", ""),
            item.get("slot_id", ""),
        )
    )
    return actions


def learning_status_from_outcome(outcome: dict) -> str:
    summary = outcome.get("metrics_resolution_summary")
    if isinstance(summary, dict) and summary.get("learning_status"):
        return str(summary.get("learning_status"))
    items = list(outcome.get("metrics_resolution_posts") or outcome.get("pending_metrics_posts", []))
    stale_keys = _stale_keys(outcome)
    normalized = []
    for item in items:
        state = _derived_metrics_resolution_state(item, stale_keys)
        normalized.append({"metrics_resolution_state": state, "is_stale": bool(item.get("is_stale") or _post_key(item) in stale_keys)})
    if not normalized:
        return "current"
    unresolved = [item for item in normalized if item["metrics_resolution_state"] != "resolved"]
    if not unresolved:
        return "current"
    if any(item["is_stale"] for item in unresolved):
        return "stale_unresolved"
    if any(item["metrics_resolution_state"] in {"manual_only_unverified", "pending_unsupported", "refresh_failed"} for item in unresolved):
        return "manual_or_future_capability_required"
    return "usable_but_incomplete"


def build_recommended_actions(
    bridge: dict,
    outcome: dict,
    queue: dict,
    followup_policy: dict,
    outcome_policy: dict,
) -> list[dict]:
    actions: list[dict] = []
    signal_map = followup_policy.get("signals_to_followups", {})
    followup_days = int(
        outcome_policy.get("freshness_windows", {}).get("followup_days", 3)
    )

    metrics_resolution_actions = build_metrics_resolution_actions(outcome)
    pending_metrics_count = len(outcome.get("pending_metrics_posts", []))
    stale_pending_metrics_count = len(outcome.get("stale_pending_metrics_posts", []))
    queue_recipes = queue.get("queue_recipe_ids", [])
    if not queue_recipes:
        queue_recipes = [
            slot.get("recipe_id", "")
            for slot in queue.get("queue_slots", [])
            if slot.get("recipe_id", "")
        ]
    preferred_outcome_recipes = outcome.get("queue_boosts", {}).get(
        "preferred_recipe_ids", []
    )
    active_signals = bridge.get("active_signal_classes", [])
    winner = top_winner(outcome)

    actions.extend(metrics_resolution_actions)

    refreshable_items = [
        item for item in (outcome.get("metrics_resolution_posts") or outcome.get("pending_metrics_posts", []))
        if (item.get("metrics_resolution_state") or "").strip() in {"pending_never_refreshed", "pending_refreshable"}
    ]
    unsupported_items = [
        item for item in (outcome.get("metrics_resolution_posts") or outcome.get("pending_metrics_posts", []))
        if (item.get("metrics_resolution_state") or "").strip() == "pending_unsupported"
    ]
    manual_items = [
        item for item in (outcome.get("metrics_resolution_posts") or outcome.get("pending_metrics_posts", []))
        if (item.get("metrics_resolution_state") or "").strip() == "manual_only_unverified"
    ]
    failed_items = [
        item for item in (outcome.get("metrics_resolution_posts") or outcome.get("pending_metrics_posts", []))
        if (item.get("metrics_resolution_state") or "").strip() == "refresh_failed"
    ]

    if failed_items:
        actions.append(
            {
                "type": "operations",
                "priority": 1,
                "action": "retry_or_escalate_refresh",
                "reason": "One or more published posts have affirmative refresh failure evidence.",
                "item_count": len(failed_items),
            }
        )
    elif refreshable_items:
        action_name = "request_supported_meta_refresh"
        if stale_pending_metrics_count:
            reason = (
                f"{stale_pending_metrics_count} stale published post(s) remain unresolved and can still be refreshed with supported fields."
            )
        else:
            reason = (
                f"{len(refreshable_items)} published post(s) still need supported metrics refresh before outcome learning can fully steer rotation."
            )
        actions.append(
            {
                "type": "operations",
                "priority": 2,
                "action": action_name,
                "reason": reason,
                "item_count": len(refreshable_items),
            }
        )
    elif unsupported_items:
        actions.append(
            {
                "type": "operations",
                "priority": 2,
                "action": "manual_or_future_capability_resolution_required",
                "reason": (
                    f"{len(unsupported_items)} published post(s) are blocked only by metrics the current refresh contract cannot request."
                ),
                "item_count": len(unsupported_items),
            }
        )
    elif manual_items:
        actions.append(
            {
                "type": "operations",
                "priority": 2,
                "action": "manual_identity_or_metric_update_required",
                "reason": (
                    f"{len(manual_items)} manual-log post(s) do not yet have real published identity evidence."
                ),
                "item_count": len(manual_items),
            }
        )

    if winner:
        actions.append(
            {
                "type": "content_followup",
                "priority": 1,
                "action": "repeat_or_iterate_winner",
                "reason": (
                    f"Recent {winner.get('classification')} performance on "
                    f"lane={winner.get('lane')} hook={winner.get('hook_category')} "
                    f"score={winner.get('score')}."
                ),
                "lane": winner.get("lane", ""),
                "hook_category": winner.get("hook_category", ""),
                "recommended_window_days": followup_days,
                "recommended_recipe_ids": preferred_outcome_recipes[:4] or queue_recipes[:4],
            }
        )

    seen_signals: set[str] = set()
    for signal in active_signals:
        if signal in seen_signals:
            continue
        seen_signals.add(signal)
        mapped = signal_map.get(signal)
        if not mapped:
            continue
        actions.append(
            {
                "type": "audience_followup",
                "priority": 2,
                "action": signal,
                "reason": mapped,
                "recommended_recipe_ids": queue_recipes[:4],
            }
        )

    if queue_recipes:
        actions.append(
            {
                "type": "generation",
                "priority": 3,
                "action": "use_current_priority_queue",
                "reason": "Rotation memory, audience demand, and post outcomes are now merged into the current queue.",
                "recommended_recipe_ids": queue_recipes[:6],
            }
        )

    actions.sort(key=lambda item: (item.get("priority", 99), item.get("action", "")))
    return actions[:8]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh Lena post-feedback memory and follow-up actions."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for report outputs")
    parser.add_argument(
        "--queue-limit",
        type=int,
        default=6,
        help="Queue slot count to pass into the queue refresh step",
    )
    args = parser.parse_args()

    followup_policy = read_json(FOLLOWUP_POLICY)
    outcome_policy = read_json(POST_OUTCOME_POLICY)

    report = {
        "report_type": "lena_post_feedback_loop",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "date": args.date,
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "queue_limit": args.queue_limit,
        "steps": [],
        "status": "running",
    }

    steps = report["steps"]
    steps.append(
        run_step(
            "build_engagement_demand_state",
            [PY, str(BUILD_ENGAGEMENT), "--date", args.date],
        )
    )
    steps.append(
        run_step(
            "build_post_outcome_learning_state",
            [PY, str(BUILD_OUTCOME), "--date", args.date],
        )
    )
    steps.append(
        run_step(
            "build_autonomous_generation_queue_dryrun",
            [PY, str(BUILD_QUEUE), "--date", args.date, "--limit", str(args.queue_limit)],
        )
    )
    steps.append(
        run_step(
            "review_metrics_engagement_bridge",
            [PY, str(REVIEW_BRIDGE), "--date", args.date],
        )
    )

    failed = next((step for step in steps if not step["ok"]), None)
    if failed:
        report["status"] = "failed"
        report["failed_step"] = failed["step"]
        path = report_path(args.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": False,
                    "failed_step": failed["step"],
                    "report_path": str(path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    outcome = read_json(post_outcome_path(args.date)) if post_outcome_path(args.date).is_file() else {}
    queue = read_json(queue_path(args.date)) if queue_path(args.date).is_file() else {}
    bridge = {}
    bridge_step = next(
        (step for step in steps if step["step"] == "review_metrics_engagement_bridge"),
        None,
    )
    if bridge_step and isinstance(bridge_step.get("stdout_json"), dict):
        bridge = bridge_step["stdout_json"]

    actions = build_recommended_actions(
        bridge,
        outcome,
        queue,
        followup_policy,
        outcome_policy,
    )

    report["status"] = "ok"
    report["artifacts"] = {
        "post_outcome_learning_state": str(post_outcome_path(args.date)),
        "autonomous_generation_queue": str(queue_path(args.date)),
    }
    report["summary"] = {
        "winner_post_count": len(outcome.get("winner_posts", [])),
        "pending_metrics_count": len(outcome.get("pending_metrics_posts", [])),
        "stale_pending_metrics_count": len(outcome.get("stale_pending_metrics_posts", [])),
        "metrics_resolution_status": learning_status_from_outcome(outcome),
        "metrics_resolution_actions": build_metrics_resolution_actions(outcome),
        "active_signal_classes": bridge.get("active_signal_classes", []),
        "queue_recipe_ids": [
            slot.get("recipe_id", "")
            for slot in queue.get("queue_slots", [])
            if slot.get("recipe_id", "")
        ] if queue.get("queue_slots") else queue.get("queue_recipe_ids", []),
        "recommended_actions": actions,
    }

    path = report_path(args.date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "version": "v1.0.0",
                "date": args.date,
                "winner_post_count": report["summary"]["winner_post_count"],
                "pending_metrics_count": report["summary"]["pending_metrics_count"],
                "metrics_resolution_status": report["summary"]["metrics_resolution_status"],
                "active_signal_classes": report["summary"]["active_signal_classes"],
                "queue_recipe_ids": report["summary"]["queue_recipe_ids"],
                "recommended_actions": actions,
                "metrics_resolution_actions": report["summary"]["metrics_resolution_actions"],
                "report_path": str(path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
