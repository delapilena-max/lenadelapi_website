"""
Lena Strategy Autonomy Prep Runner v1

Canonical dry-run strategy prep for the Lena image autonomy path.

Runs, in order:
1. recipe catalog lock validation
2. content packet batch dry run
3. Kling payload dry runs for the selected recipes
4. autonomous generation readiness audit
5. next generation step recommendation
6. autonomous generation queue dry run

Safe: no API calls, no image generation, no video generation, no upload,
no queue mutation, no publish, no schedule, no credential reads.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPE_BANK = (
    ROOT / "pipeline" / "prompt_banks" / "lena"
    / "lena_high_caliber_prompt_recipe_bank_v1.json"
)
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
CONTENT_PACKETS = ROOT / "pipeline" / "strategy" / "lena" / "content_packets"
KLING_PAYLOADS = ROOT / "pipeline" / "strategy" / "lena" / "kling_payloads"

VALIDATE_LOCKS = ROOT / "tools" / "strategy" / "lena_validate_recipe_catalog_locks_v1.py"
BUILD_BATCH = ROOT / "tools" / "strategy" / "lena_build_content_batch_dryrun_v1.py"
BUILD_PAYLOAD = ROOT / "tools" / "strategy" / "lena_build_kling_payload_dryrun_v1.py"
BUILD_VIDEO_PAYLOAD = ROOT / "tools" / "strategy" / "lena_build_kling_video_payload_dryrun_v1.py"
AUDIT = ROOT / "tools" / "strategy" / "lena_audit_autonomous_generation_readiness_v1.py"
RECOMMEND = ROOT / "tools" / "strategy" / "lena_recommend_next_generation_step_v1.py"
WORLD_STATE = ROOT / "tools" / "strategy" / "lena_build_world_state_v1.py"
ENGAGEMENT_DEMAND = ROOT / "tools" / "strategy" / "lena_build_engagement_demand_state_v1.py"
POST_OUTCOME = ROOT / "tools" / "strategy" / "lena_build_post_outcome_learning_state_v1.py"
BUILD_QUEUE = ROOT / "tools" / "strategy" / "lena_build_autonomous_generation_queue_dryrun_v1.py"
BUILD_NEXT_LIVE_HANDOFF = ROOT / "tools" / "strategy" / "lena_build_next_live_image_handoff_v1.py"
VIDEO_PAYLOADS = ROOT / "pipeline" / "strategy" / "lena" / "kling_video_payloads"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def default_recipe_ids() -> list[str]:
    data = read_json(RECIPE_BANK)
    active = [
        recipe for recipe in data.get("recipes", [])
        if recipe.get("production_status") != "test_only"
    ]
    active.sort(
        key=lambda recipe: (
            recipe.get("proof_priority") is None,
            recipe.get("proof_priority", 999),
            recipe.get("id", ""),
        )
    )
    return [recipe["id"] for recipe in active]


def try_parse_json(text: str) -> dict | list | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if not raw.startswith("{") and not raw.startswith("["):
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


def run_step(step_name: str, cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    parsed = try_parse_json(proc.stdout)
    return {
        "step": step_name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout_json": parsed,
        "stdout_tail": tail_lines(proc.stdout),
        "stderr_tail": tail_lines(proc.stderr),
    }


def manifest_path(date_str: str) -> Path:
    return (
        CONTENT_PACKETS / date_str
        / f"lena_content_packet_batch_manifest_dryrun_{date_str}.json"
    )


def payload_path(date_str: str, recipe_id: str) -> Path:
    return (
        KLING_PAYLOADS / date_str
        / f"kling_payload_dryrun_{date_str}_{recipe_id}.json"
    )


def video_payload_path(date_str: str, recipe_id: str) -> Path:
    return (
        VIDEO_PAYLOADS / date_str
        / f"kling_video_payload_dryrun_{date_str}_{recipe_id}.json"
    )


def audit_path(date_str: str) -> Path:
    return (
        NEXT_ACTIONS / date_str
        / f"lena_autonomous_generation_readiness_audit_{date_str}.json"
    )


def next_step_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_next_generation_step_{date_str}.json"


def queue_path(date_str: str) -> Path:
    return (
        NEXT_ACTIONS / date_str
        / f"lena_autonomous_generation_queue_dryrun_{date_str}.json"
    )


def next_live_handoff_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_next_live_image_handoff_{date_str}.json"


def next_live_handoff_md_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_next_live_image_handoff_{date_str}.md"


def world_state_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_world_state_{date_str}.json"


def engagement_demand_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_engagement_demand_state_{date_str}.json"


def post_outcome_path(date_str: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_post_outcome_learning_state_{date_str}.json"


def save_report(report: dict, date_str: str) -> Path:
    out_dir = NEXT_ACTIONS / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lena_strategy_autonomy_prep_{date_str}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def packet_path(date_str: str, recipe_id: str) -> Path:
    return (
        CONTENT_PACKETS / date_str
        / f"lena_content_packet_dryrun_{date_str}_{recipe_id}.json"
    )


def packet_supports_video(packet: dict) -> bool:
    best = str(packet.get("best_content_type", "")).lower()
    return "reel" in best or "video" in best


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the canonical Lena strategy autonomy prep dry-run stack."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for outputs")
    parser.add_argument(
        "--recipes",
        default="",
        help=(
            "Optional comma-separated recipe IDs. "
            "Defaults to all active recipes ordered by proof_priority."
        ),
    )
    parser.add_argument(
        "--queue-limit",
        type=int,
        default=6,
        help="Queue slot count for autonomous_generation_queue_dryrun",
    )
    args = parser.parse_args()

    recipe_ids = (
        [item.strip() for item in args.recipes.split(",") if item.strip()]
        if args.recipes
        else default_recipe_ids()
    )

    report = {
        "report_type": "lena_strategy_autonomy_prep",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "date": args.date,
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "recipe_ids": recipe_ids,
        "queue_limit": args.queue_limit,
        "steps": [],
        "status": "running",
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
    }

    steps = report["steps"]

    step = run_step("validate_recipe_catalog_locks", [sys.executable, str(VALIDATE_LOCKS)])
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    batch_cmd = [sys.executable, str(BUILD_BATCH), "--date", args.date]
    if args.recipes:
        batch_cmd.extend(["--recipes", ",".join(recipe_ids)])
    step = run_step("build_content_batch_dryrun", batch_cmd)
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    payload_results = []
    for recipe_id in recipe_ids:
        payload_cmd = [
            sys.executable,
            str(BUILD_PAYLOAD),
            "--recipe",
            recipe_id,
            "--date",
            args.date,
        ]
        payload_step = run_step(f"build_kling_payload_dryrun:{recipe_id}", payload_cmd)
        steps.append(payload_step)
        payload_results.append(payload_step)
        if not payload_step["ok"]:
            report["status"] = "failed"
            report["failed_step"] = payload_step["step"]
            output_path = save_report(report, args.date)
            print(json.dumps({"ok": False, "failed_step": payload_step["step"], "report_path": str(output_path)}, indent=2))
            return 1

    video_payload_results = []
    video_candidate_recipe_ids = []
    for recipe_id in recipe_ids:
        current_packet_path = packet_path(args.date, recipe_id)
        if not current_packet_path.is_file():
            continue
        current_packet = read_json(current_packet_path)
        if not packet_supports_video(current_packet):
            continue
        video_candidate_recipe_ids.append(recipe_id)
        video_payload_cmd = [
            sys.executable,
            str(BUILD_VIDEO_PAYLOAD),
            "--packet",
            str(current_packet_path),
        ]
        video_payload_step = run_step(
            f"build_kling_video_payload_dryrun:{recipe_id}",
            video_payload_cmd,
        )
        steps.append(video_payload_step)
        video_payload_results.append(video_payload_step)
        if not video_payload_step["ok"]:
            report["status"] = "failed"
            report["failed_step"] = video_payload_step["step"]
            output_path = save_report(report, args.date)
            print(json.dumps({"ok": False, "failed_step": video_payload_step["step"], "report_path": str(output_path)}, indent=2))
            return 1

    audit_cmd = [sys.executable, str(AUDIT), "--date", args.date]
    if args.recipes:
        audit_cmd.extend(["--recipes", *recipe_ids])
    step = run_step("audit_autonomous_generation_readiness", audit_cmd)
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    step = run_step("build_post_outcome_learning_state", [sys.executable, str(POST_OUTCOME), "--date", args.date])
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    learning_path = post_outcome_path(args.date)

    step = run_step(
        "recommend_next_generation_step",
        [
            sys.executable,
            str(RECOMMEND),
            "--date",
            args.date,
            "--learning-artifact-path",
            str(learning_path),
        ],
    )
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    step = run_step("build_world_state", [sys.executable, str(WORLD_STATE), "--date", args.date])
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    step = run_step("build_engagement_demand_state", [sys.executable, str(ENGAGEMENT_DEMAND), "--date", args.date])
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    step = run_step(
        "build_autonomous_generation_queue_dryrun",
        [
            sys.executable,
            str(BUILD_QUEUE),
            "--date",
            args.date,
            "--limit",
            str(args.queue_limit),
        ],
    )
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    audit_report = read_json(audit_path(args.date)) if audit_path(args.date).is_file() else {}
    next_step_report = read_json(next_step_path(args.date)) if next_step_path(args.date).is_file() else {}
    world_state_report = read_json(world_state_path(args.date)) if world_state_path(args.date).is_file() else {}
    engagement_demand_report = read_json(engagement_demand_path(args.date)) if engagement_demand_path(args.date).is_file() else {}
    post_outcome_report = read_json(post_outcome_path(args.date)) if post_outcome_path(args.date).is_file() else {}
    queue_report = read_json(queue_path(args.date)) if queue_path(args.date).is_file() else {}
    video_payload_reports = [
        read_json(video_payload_path(args.date, recipe_id))
        for recipe_id in video_candidate_recipe_ids
        if video_payload_path(args.date, recipe_id).is_file()
    ]

    report["status"] = "ok"
    report["artifacts"] = {
        "batch_manifest": str(manifest_path(args.date)),
        "payloads": [str(payload_path(args.date, recipe_id)) for recipe_id in recipe_ids],
        "video_payloads": [
            str(video_payload_path(args.date, recipe_id))
            for recipe_id in video_candidate_recipe_ids
        ],
        "readiness_audit": str(audit_path(args.date)),
        "next_generation_step": str(next_step_path(args.date)),
        "world_state": str(world_state_path(args.date)),
        "engagement_demand_state": str(engagement_demand_path(args.date)),
        "post_outcome_learning_state": str(post_outcome_path(args.date)),
        "autonomous_generation_queue": str(queue_path(args.date)),
        "next_live_image_handoff": str(next_live_handoff_path(args.date)),
        "next_live_image_handoff_markdown": str(next_live_handoff_md_path(args.date)),
    }
    broader_ready = audit_report.get("memory_progress", {}).get(
        "broader_autonomous_generation_ready", False
    )
    queue_head = queue_report.get("queue_slots", [{}])[0] if queue_report.get("queue_slots") else {}
    report["summary"] = {
        "queue_head_recipe_id": (
            queue_report.get("queue_slots", [{}])[0].get("recipe_id", "")
            if queue_report.get("queue_slots")
            else ""
        ),
        "active_recipe_count": len(recipe_ids),
        "payload_count": len(recipe_ids),
        "video_candidate_recipe_ids": video_candidate_recipe_ids,
        "video_payload_count": len(video_candidate_recipe_ids),
        "video_seed_available_count": sum(
            1 for item in video_payload_reports if item.get("seed_image_present") is True
        ),
        "video_transport_ready_count": sum(
            1 for item in video_payload_reports if item.get("seed_image_transport_ready") is True
        ),
        "video_live_ready_count": sum(
            1 for item in video_payload_reports if item.get("seed_image_live_ready") is True
        ),
        "lane_status_counts": audit_report.get("lane_status_counts", {}),
        "broader_autonomous_generation_ready": broader_ready,
        "strategy_gate_blocked": audit_report.get("strategy_gate", {}).get(
            "blocked", False
        ),
        "strategy_gate_reasons": audit_report.get("strategy_gate", {}).get(
            "block_reasons", []
        ),
        "recommended_recipe_id": (
            queue_head.get("recipe_id", "")
            if broader_ready and queue_report.get("queue_slots")
            else next_step_report.get("recommendation", {}).get("recommended_recipe_id", "")
        ),
        "recommended_outfit_id": (
            queue_head.get("outfit_used", "")
            if broader_ready and queue_report.get("queue_slots")
            else next_step_report.get("recommendation", {}).get("recommended_outfit_id", "")
        ),
        "recommended_environment_id": (
            queue_head.get("environment_used", "")
            if broader_ready and queue_report.get("queue_slots")
            else next_step_report.get("recommendation", {}).get("recommended_environment_id", "")
        ),
        "learning_artifact_path": next_step_report.get("recommendation", {}).get("learning_artifact_path", ""),
        "learning_availability": next_step_report.get("recommendation", {}).get("learning_availability", ""),
        "learning_status": next_step_report.get("recommendation", {}).get("learning_status", ""),
        "learning_validation_state": next_step_report.get("recommendation", {}).get("learning_validation_state", ""),
        "learning_validation_error": next_step_report.get("recommendation", {}).get("learning_validation_error", ""),
        "learning_published_post_count": next_step_report.get("recommendation", {}).get("learning_published_post_count", 0),
        "learning_pending_metrics_count": next_step_report.get("recommendation", {}).get("learning_pending_metrics_count", 0),
        "learning_stale_pending_metrics_count": next_step_report.get("recommendation", {}).get("learning_stale_pending_metrics_count", 0),
        "learning_resolution_state_summary": next_step_report.get("recommendation", {}).get("learning_resolution_state_summary", {}),
        "learning_required_follow_up_action": next_step_report.get("recommendation", {}).get("learning_required_follow_up_action", ""),
        "recommended_video_recipe_id": (
            next_step_report.get("recommendation", {}).get("recommended_recipe_id", "")
            if next_step_report.get("recommendation", {}).get("recommended_recipe_id", "") in video_candidate_recipe_ids
            else (video_candidate_recipe_ids[0] if video_candidate_recipe_ids else "")
        ),
        "continuity_alert_count": len(world_state_report.get("continuity_alerts", [])),
        "preferred_rotation_recipe_ids": world_state_report.get("queue_rotation_controls", {}).get(
            "prefer_recipe_ids", []
        ),
        "deprioritized_rotation_recipe_ids": world_state_report.get("queue_rotation_controls", {}).get(
            "deprioritized_recipe_ids", []
        ),
        "active_engagement_signal_classes": engagement_demand_report.get(
            "active_signal_classes", []
        ),
        "engagement_preferred_recipe_ids": engagement_demand_report.get("queue_boosts", {}).get(
            "preferred_recipe_ids", []
        ),
        "winner_post_count": len(post_outcome_report.get("winner_posts", [])),
        "pending_metrics_count": len(post_outcome_report.get("pending_metrics_posts", [])),
        "post_outcome_preferred_recipe_ids": post_outcome_report.get("queue_boosts", {}).get(
            "preferred_recipe_ids", []
        ),
        "queue_recipes": [row.get("recipe_id", "") for row in queue_report.get("queue_slots", [])],
        "next_live_image_handoff_path": str(next_live_handoff_path(args.date)),
        "next_live_image_handoff_markdown_path": str(next_live_handoff_md_path(args.date)),
        "next_live_handoff_script_present": BUILD_NEXT_LIVE_HANDOFF.is_file(),
        "next_live_handoff_blocker": "" if BUILD_NEXT_LIVE_HANDOFF.is_file() else "missing_script",
    }

    save_report(report, args.date)

    step = run_step(
        "build_next_live_image_handoff",
        [sys.executable, str(BUILD_NEXT_LIVE_HANDOFF), "--date", args.date],
    )
    steps.append(step)
    if not step["ok"]:
        report["status"] = "failed"
        report["failed_step"] = step["step"]
        output_path = save_report(report, args.date)
        print(json.dumps({"ok": False, "failed_step": step["step"], "report_path": str(output_path)}, indent=2))
        return 1

    output_path = save_report(report, args.date)
    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(output_path),
                "active_recipe_count": report["summary"]["active_recipe_count"],
                "payload_count": report["summary"]["payload_count"],
                "video_payload_count": report["summary"]["video_payload_count"],
                "recommended_video_recipe_id": report["summary"]["recommended_video_recipe_id"],
                "broader_autonomous_generation_ready": report["summary"]["broader_autonomous_generation_ready"],
                "strategy_gate_blocked": report["summary"]["strategy_gate_blocked"],
                "strategy_gate_reasons": report["summary"]["strategy_gate_reasons"],
                "video_seed_available_count": report["summary"]["video_seed_available_count"],
                "video_transport_ready_count": report["summary"]["video_transport_ready_count"],
                "recommended_recipe_id": report["summary"]["recommended_recipe_id"],
                "queue_recipes": report["summary"]["queue_recipes"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
