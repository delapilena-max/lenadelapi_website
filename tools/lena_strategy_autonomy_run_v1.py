from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
RUNNER = ROOT / "tools" / "strategy" / "lena_run_strategy_autonomy_prep_v1.py"
META_REFRESH = ROOT / "tools" / "lena_meta_refresh_feedback_v1.py"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"


def run_step(label: str, cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "label": label,
        "cmd": cmd,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def now_ts() -> str:
    return datetime.now().strftime("%H%M%S")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_report(day: str, report: dict) -> Path:
    out_dir = NEXT_ACTIONS / day
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lena_strategy_autonomy_run_{now_ts()}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def post_kling_review_prep_report_path(day: str) -> Path:
    return NEXT_ACTIONS / day / f"lena_post_kling_review_prep_{day}.json"


def post_kling_review_prep_markdown_path(day: str) -> Path:
    return NEXT_ACTIONS / day / f"lena_post_kling_review_prep_{day}.md"


def apply_kling_review_packet_report_path(day: str) -> Path:
    return NEXT_ACTIONS / day / f"lena_apply_kling_review_packet_{day}.json"


def apply_kling_review_packet_markdown_path(day: str) -> Path:
    return NEXT_ACTIONS / day / f"lena_apply_kling_review_packet_{day}.md"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Top-level Lena strategy autonomy dry-run entrypoint."
    )
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument(
        "--recipes",
        default="",
        help="Optional comma-separated recipe IDs. Defaults to active proof-priority order.",
    )
    ap.add_argument("--queue-limit", type=int, default=6)
    ap.add_argument(
        "--refresh-meta-feedback",
        action="store_true",
        help=(
            "Refresh live Meta metrics/comments before the dry-run strategy prep so "
            "queue and recommendation logic can read fresher platform state."
        ),
    )
    ap.add_argument(
        "--meta-max-posts",
        type=int,
        default=12,
        help="Recent Meta post count to inspect when refreshing live feedback.",
    )
    ap.add_argument(
        "--meta-comments-limit",
        type=int,
        default=25,
        help="Comment fetch limit per Meta post during live feedback refresh.",
    )
    args = ap.parse_args()

    started_at = datetime.now().isoformat(timespec="seconds")
    steps = []

    if args.refresh_meta_feedback:
        refresh_cmd = [
            PY,
            str(META_REFRESH),
            "--max-posts",
            str(args.meta_max_posts),
            "--comments-limit",
            str(args.meta_comments_limit),
            "--queue-limit",
            str(args.queue_limit),
        ]
        steps.append(run_step("meta_feedback_refresh", refresh_cmd))

    cmd = [PY, str(RUNNER), "--date", args.date, "--queue-limit", str(args.queue_limit)]
    if args.recipes:
        cmd.extend(["--recipes", args.recipes])

    steps.append(run_step("strategy_autonomy_prep", cmd))
    step = steps[-1]

    result = {
        "ok": step["ok"],
        "version": "v1",
        "date": args.date,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "steps": [
            {
                "label": item["label"],
                "ok": item["ok"],
                "returncode": item["returncode"],
                "cmd": item["cmd"],
            }
            for item in steps
        ],
    }

    meta_summary = {}
    refresh_step = next(
        (item for item in steps if item["label"] == "meta_feedback_refresh"),
        None,
    )
    if refresh_step:
        try:
            parsed_refresh = json.loads(refresh_step["stdout"])
            meta_summary = {
                "ok": refresh_step["ok"],
                "report_path": parsed_refresh.get("report_path", ""),
                "metrics_updated": parsed_refresh.get("metrics_updated", 0),
                "comments_logged": parsed_refresh.get("comments_logged", 0),
                "candidate_post_count": parsed_refresh.get("candidate_post_count", 0),
                "changed_dates": parsed_refresh.get("changed_dates", []),
            }
        except Exception:
            meta_summary = {
                "ok": refresh_step["ok"],
                "stdout": refresh_step["stdout"],
                "stderr": refresh_step["stderr"],
            }

    summary = {}
    prep_report_path = None
    try:
        parsed = json.loads(step["stdout"])
        prep_report_path = parsed.get("report_path")
        if prep_report_path:
            prep_report = read_json(Path(prep_report_path))
            summary = prep_report.get("summary", {})
    except Exception:
        parsed = None

    if prep_report_path:
        result["strategy_prep_report"] = prep_report_path
    if meta_summary:
        result["meta_feedback_summary"] = meta_summary
    if summary:
        result["summary"] = summary
        result["next_live_image_handoff_report"] = summary.get(
            "next_live_image_handoff_path", ""
        )
        result["next_live_image_handoff_markdown"] = summary.get(
            "next_live_image_handoff_markdown_path", ""
        )
    if post_kling_review_prep_report_path(args.date).is_file():
        result["post_kling_review_prep_report"] = str(
            post_kling_review_prep_report_path(args.date)
        )
    if post_kling_review_prep_markdown_path(args.date).is_file():
        result["post_kling_review_prep_markdown"] = str(
            post_kling_review_prep_markdown_path(args.date)
        )
    if apply_kling_review_packet_report_path(args.date).is_file():
        result["apply_kling_review_packet_report"] = str(
            apply_kling_review_packet_report_path(args.date)
        )
    if apply_kling_review_packet_markdown_path(args.date).is_file():
        result["apply_kling_review_packet_markdown"] = str(
            apply_kling_review_packet_markdown_path(args.date)
        )
    if step["stdout"].strip():
        result["stdout"] = step["stdout"]
    if step["stderr"].strip():
        result["stderr"] = step["stderr"]
    if refresh_step and refresh_step["stdout"].strip():
        result["meta_feedback_stdout"] = refresh_step["stdout"]
    if refresh_step and refresh_step["stderr"].strip():
        result["meta_feedback_stderr"] = refresh_step["stderr"]

    report_path = write_report(args.date, result)
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "report_path": str(report_path),
                "meta_feedback_refresh_ok": meta_summary.get("ok", False),
                "meta_feedback_report": meta_summary.get("report_path", ""),
                "meta_feedback_metrics_updated": meta_summary.get("metrics_updated", 0),
                "meta_feedback_comments_logged": meta_summary.get("comments_logged", 0),
                "strategy_prep_report": prep_report_path or "",
                "next_live_image_handoff_report": summary.get(
                    "next_live_image_handoff_path", ""
                ),
                "next_live_image_handoff_markdown": summary.get(
                    "next_live_image_handoff_markdown_path", ""
                ),
                "post_kling_review_prep_report": (
                    str(post_kling_review_prep_report_path(args.date))
                    if post_kling_review_prep_report_path(args.date).is_file()
                    else ""
                ),
                "post_kling_review_prep_markdown": (
                    str(post_kling_review_prep_markdown_path(args.date))
                    if post_kling_review_prep_markdown_path(args.date).is_file()
                    else ""
                ),
                "apply_kling_review_packet_report": (
                    str(apply_kling_review_packet_report_path(args.date))
                    if apply_kling_review_packet_report_path(args.date).is_file()
                    else ""
                ),
                "apply_kling_review_packet_markdown": (
                    str(apply_kling_review_packet_markdown_path(args.date))
                    if apply_kling_review_packet_markdown_path(args.date).is_file()
                    else ""
                ),
                "recommended_recipe_id": summary.get("recommended_recipe_id", ""),
                "recommended_video_recipe_id": summary.get("recommended_video_recipe_id", ""),
                "queue_recipes": summary.get("queue_recipes", []),
                "video_candidate_recipe_ids": summary.get("video_candidate_recipe_ids", []),
                "video_payload_count": summary.get("video_payload_count", 0),
                "video_seed_available_count": summary.get("video_seed_available_count", 0),
                "video_transport_ready_count": summary.get("video_transport_ready_count", 0),
                "video_live_ready_count": summary.get("video_live_ready_count", 0),
                "continuity_alert_count": summary.get("continuity_alert_count", 0),
                "preferred_rotation_recipe_ids": summary.get("preferred_rotation_recipe_ids", []),
                "deprioritized_rotation_recipe_ids": summary.get("deprioritized_rotation_recipe_ids", []),
                "active_engagement_signal_classes": summary.get("active_engagement_signal_classes", []),
                "engagement_preferred_recipe_ids": summary.get("engagement_preferred_recipe_ids", []),
                "winner_post_count": summary.get("winner_post_count", 0),
                "pending_metrics_count": summary.get("pending_metrics_count", 0),
                "post_outcome_preferred_recipe_ids": summary.get("post_outcome_preferred_recipe_ids", []),
                "broader_autonomous_generation_ready": summary.get(
                    "broader_autonomous_generation_ready", False
                ),
                "strategy_gate_blocked": summary.get("strategy_gate_blocked", False),
                "strategy_gate_reasons": summary.get("strategy_gate_reasons", []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
