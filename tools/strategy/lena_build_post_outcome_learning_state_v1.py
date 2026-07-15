from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
MEMORY_POLICY = NODE / "life_engine_realism_memory_policy_v1.json"
POST_OUTCOME_POLICY = NODE / "post_outcome_learning_policy_v1.json"
DEFAULT_MEMORY_STATE = ROOT / "pipeline" / "state" / "lena_life_engine_realism_memory_v1.json"

WIN_STATUSES = {
    "approved",
    "publishable",
    "publishable_quality",
    "strong_candidate_needs_skin_realism_review",
}


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_policy_path() -> Path:
    policy = read_json_or_empty(MEMORY_POLICY)
    memory_path = str(policy.get("memory_path", "")).strip()
    if memory_path:
        candidate = ROOT / memory_path
        if candidate.is_file():
            return candidate
    return DEFAULT_MEMORY_STATE


def load_memory_state() -> tuple[Path, dict[str, Any]]:
    path = load_policy_path()
    return path, read_json_or_empty(path)


def active_winner_posts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    winners: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("qa_status") not in WIN_STATUSES:
            continue
        winners.append(
            {
                "task_id": entry.get("task_id", ""),
                "date": entry.get("date", ""),
                "recipe_id": entry.get("recipe_id", ""),
                "outfit_id": entry.get("outfit_id", ""),
                "environment_id": entry.get("environment_id", ""),
                "provider": entry.get("provider", ""),
                "qa_status": entry.get("qa_status", ""),
            }
        )
    return winners


def preferred_recipe_ids(winner_posts: list[dict[str, Any]]) -> list[str]:
    preferred: list[str] = []
    for post in reversed(winner_posts):
        recipe_id = str(post.get("recipe_id", "")).strip()
        if recipe_id and recipe_id not in preferred:
            preferred.append(recipe_id)
    return preferred


def learning_status_from(winner_count: int, entry_count: int, publish_state_present: bool) -> str:
    if winner_count > 0 or publish_state_present:
        return "current"
    if entry_count > 0:
        return "manual_or_future_capability_required"
    return "manual_or_future_capability_required"


def build_learning_state(date_str: str) -> dict[str, Any]:
    memory_path, memory_state = load_memory_state()
    entries = memory_state.get("entries", [])
    if not isinstance(entries, list):
        entries = []

    post_outcome_policy = read_json_or_empty(POST_OUTCOME_POLICY)
    manual_post_log_path = ROOT / str(post_outcome_policy.get("manual_post_log_path", "")).strip()
    post_metrics_path = ROOT / str(post_outcome_policy.get("post_metrics_path", "")).strip()
    publish_state_path = ROOT / str(post_outcome_policy.get("publish_state_path", "")).strip()

    manual_post_log = read_json_or_empty(manual_post_log_path)
    post_metrics = read_json_or_empty(post_metrics_path)
    publish_state = read_json_or_empty(publish_state_path)

    winner_posts = active_winner_posts(entries)
    preferred_ids = preferred_recipe_ids(winner_posts)
    qa_status_counts = Counter(str(entry.get("qa_status", "unknown")) for entry in entries)
    publish_state_present = publish_state_path.is_file() and bool(publish_state)

    learning_status = learning_status_from(len(winner_posts), len(entries), publish_state_present)
    pending_metrics_posts: list[dict[str, Any]] = []
    stale_pending_metrics_posts: list[dict[str, Any]] = []
    if isinstance(post_metrics.get("pending_metrics_posts"), list):
        pending_metrics_posts = [item for item in post_metrics["pending_metrics_posts"] if isinstance(item, dict)]
    if isinstance(post_metrics.get("stale_pending_metrics_posts"), list):
        stale_pending_metrics_posts = [
            item for item in post_metrics["stale_pending_metrics_posts"] if isinstance(item, dict)
        ]

    if not pending_metrics_posts and not stale_pending_metrics_posts:
        if learning_status == "current":
            pending_metrics_posts = []
            stale_pending_metrics_posts = []

    metrics_resolution_summary = {
        "learning_status": learning_status,
        "current_count": len(winner_posts),
        "usable_but_incomplete_count": 0,
        "stale_unresolved_count": len(stale_pending_metrics_posts),
        "manual_or_future_capability_required_count": 0 if learning_status == "current" else 1,
    }

    if learning_status == "manual_or_future_capability_required":
        pending_metrics_posts = []
        stale_pending_metrics_posts = []

    report = {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": date_str,
        "generated_at": iso_now(),
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "status": "ok",
        "source_policy_path": repo_relative_path(POST_OUTCOME_POLICY),
        "source_memory_policy_path": repo_relative_path(MEMORY_POLICY),
        "source_memory_state_path": repo_relative_path(memory_path),
        "source_memory_state_present": memory_path.is_file(),
        "source_memory_state_updated_at": memory_state.get("updated_at", ""),
        "source_manual_post_log_path": repo_relative_path(manual_post_log_path),
        "source_manual_post_log_present": manual_post_log_path.is_file(),
        "source_post_metrics_path": repo_relative_path(post_metrics_path),
        "source_post_metrics_present": post_metrics_path.is_file(),
        "source_publish_state_path": repo_relative_path(publish_state_path),
        "source_publish_state_present": publish_state_path.is_file(),
        "published_post_count": len(winner_posts),
        "pending_metrics_posts": pending_metrics_posts,
        "stale_pending_metrics_posts": stale_pending_metrics_posts,
        "winner_posts": winner_posts,
        "queue_boosts": {
            "preferred_recipe_ids": preferred_ids,
        },
        "metrics_resolution_summary": metrics_resolution_summary,
        "learning_status": learning_status,
        "learning_status_label": {
            "current": "learning_current",
            "usable_but_incomplete": "learning_degraded_incomplete",
            "stale_unresolved": "learning_stale_unresolved",
            "manual_or_future_capability_required": "learning_manual_or_future_capability_required",
        }.get(learning_status, "learning_unavailable"),
        "learning_required_follow_up_action": {
            "current": "no_follow_up_required",
            "usable_but_incomplete": "complete_missing_metrics_or_refresh_learning",
            "stale_unresolved": "refresh_or_resolve_stale_unresolved_posts",
            "manual_or_future_capability_required": "manual_or_future_capability_resolution_required",
        }.get(learning_status, "rebuild_and_pass_an_explicit_learning_artifact"),
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
        "summary": {
            "entry_count": len(entries),
            "winner_count": len(winner_posts),
            "qa_status_counts": dict(qa_status_counts),
            "preferred_recipe_ids": preferred_ids,
            "manual_post_log_present": manual_post_log_path.is_file(),
            "post_metrics_present": post_metrics_path.is_file(),
            "publish_state_present": publish_state_present,
            "memory_state_present": memory_path.is_file(),
            "memory_state_updated_at": memory_state.get("updated_at", ""),
            "learning_status": learning_status,
        },
    }

    if manual_post_log:
        report["summary"]["manual_post_log_entry_count"] = len(manual_post_log.get("entries", [])) if isinstance(manual_post_log.get("entries"), list) else 0
    if post_metrics:
        report["summary"]["post_metrics_entry_count"] = len(post_metrics.get("entries", [])) if isinstance(post_metrics.get("entries"), list) else 0
    if publish_state:
        report["summary"]["publish_state_entry_count"] = len(publish_state.get("entries", [])) if isinstance(publish_state.get("entries"), list) else 0

    return report


def save_report(report: dict[str, Any], date_str: str) -> Path:
    out_dir = NEXT_ACTIONS / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lena_post_outcome_learning_state_{date_str}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the report-only Lena post outcome learning state."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for outputs")
    args = parser.parse_args()

    report = build_learning_state(args.date)
    output_path = save_report(report, args.date)
    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(output_path),
                "date": args.date,
                "learning_status": report["learning_status"],
                "winner_post_count": report["summary"]["winner_count"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
