from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

PLATFORMS = "Instagram Feed,Facebook Page"
STRATEGY_AUTONOMY_RUNNER = "tools/lena_strategy_autonomy_run_v1.py"


def run_step(
    label: str,
    cmd: list[str],
    dry_run: bool = False,
    skip_on_dry: bool = False,
    capture_output: bool = False,
) -> dict:
    if dry_run and skip_on_dry:
        print(f"[orchestrator] DRY-RUN skip: {label}")
        return {
            "label": label,
            "ok": True,
            "skipped": True,
            "reason": "dry_run",
        }
    print(f"\n[orchestrator] >>> {label}")
    print("  " + " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=capture_output,
        encoding="utf-8",
        errors="replace",
    )
    if capture_output and result.stdout:
        print(result.stdout.strip())
    if capture_output and result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    ok = result.returncode == 0
    status = "PASS" if ok else f"FAIL(rc={result.returncode})"
    print(f"[orchestrator] <<< {label}  {status}")
    step = {"label": label, "ok": ok, "returncode": result.returncode}
    if capture_output:
        step["stdout"] = result.stdout
        step["stderr"] = result.stderr
    return step


def _try_parse_json(text: str) -> dict | list | None:
    raw = (text or "").strip()
    if not raw or (not raw.startswith("{") and not raw.startswith("[")):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _tail_lines(text: str, limit: int = 12) -> list[str]:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if len(lines) <= limit:
        return lines
    return lines[-limit:]


def _strategy_summary_from_steps(steps: list[dict]) -> dict:
    step = next(
        (item for item in steps if item.get("label") == "strategy_autonomy_prep"),
        None,
    )
    if not step:
        return {}
    parsed = _try_parse_json(step.get("stdout", "") or "")
    if not isinstance(parsed, dict):
        return {
            "step_present": True,
            "ok": step.get("ok", False),
            "stdout_tail": _tail_lines(step.get("stdout", "")),
            "stderr_tail": _tail_lines(step.get("stderr", "")),
        }
    return {
        "step_present": True,
        "ok": step.get("ok", False),
        "meta_feedback_refresh_ok": parsed.get("meta_feedback_refresh_ok", False),
        "meta_feedback_report": parsed.get("meta_feedback_report", ""),
        "meta_feedback_metrics_updated": parsed.get("meta_feedback_metrics_updated", 0),
        "meta_feedback_comments_logged": parsed.get("meta_feedback_comments_logged", 0),
        "strategy_prep_report": parsed.get("strategy_prep_report", ""),
        "next_live_image_handoff_report": parsed.get(
            "next_live_image_handoff_report", ""
        ),
        "next_live_image_handoff_markdown": parsed.get(
            "next_live_image_handoff_markdown", ""
        ),
        "recommended_recipe_id": parsed.get("recommended_recipe_id", ""),
        "recommended_video_recipe_id": parsed.get("recommended_video_recipe_id", ""),
        "queue_recipes": parsed.get("queue_recipes", []),
        "video_candidate_recipe_ids": parsed.get("video_candidate_recipe_ids", []),
        "video_payload_count": parsed.get("video_payload_count", 0),
        "video_seed_available_count": parsed.get("video_seed_available_count", 0),
        "video_transport_ready_count": parsed.get("video_transport_ready_count", 0),
        "video_live_ready_count": parsed.get("video_live_ready_count", 0),
        "continuity_alert_count": parsed.get("continuity_alert_count", 0),
        "preferred_rotation_recipe_ids": parsed.get("preferred_rotation_recipe_ids", []),
        "deprioritized_rotation_recipe_ids": parsed.get("deprioritized_rotation_recipe_ids", []),
        "active_engagement_signal_classes": parsed.get("active_engagement_signal_classes", []),
        "engagement_preferred_recipe_ids": parsed.get("engagement_preferred_recipe_ids", []),
        "winner_post_count": parsed.get("winner_post_count", 0),
        "pending_metrics_count": parsed.get("pending_metrics_count", 0),
        "post_outcome_preferred_recipe_ids": parsed.get("post_outcome_preferred_recipe_ids", []),
        "broader_autonomous_generation_ready": parsed.get(
            "broader_autonomous_generation_ready", False
        ),
        "strategy_gate_blocked": parsed.get("strategy_gate_blocked", False),
        "strategy_gate_reasons": parsed.get("strategy_gate_reasons", []),
        "stdout_tail": _tail_lines(step.get("stdout", "")),
        "stderr_tail": _tail_lines(step.get("stderr", "")),
    }


def _strategy_gate_blocked(steps: list[dict]) -> bool:
    summary = _strategy_summary_from_steps(steps)
    if not summary.get("step_present"):
        return False
    if not summary.get("ok", False):
        return True
    return (
        not summary.get("broader_autonomous_generation_ready", False)
        or summary.get("strategy_gate_blocked", False)
    )


def _strategy_queue_report_path(steps: list[dict]) -> str:
    summary = _strategy_summary_from_steps(steps)
    prep_report_path = str(summary.get("strategy_prep_report", "")).strip()
    if not prep_report_path:
        return ""
    try:
        prep_report = json.loads(Path(prep_report_path).read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    return str(prep_report.get("artifacts", {}).get("autonomous_generation_queue", "")).strip()


def _review_artifacts(day: str) -> dict:
    base = ROOT / "pipeline" / "strategy" / "lena" / "next_actions" / day
    artifacts = {
        "unreviewed_queue_json": base / f"lena_unreviewed_kling_result_queue_{day}.json",
        "unreviewed_queue_markdown": base / f"LENA_UNREVIEWED_KLING_RESULT_QUEUE_{day}.md",
        "review_draft_queue_json": base / f"lena_kling_review_draft_queue_{day}.json",
        "review_draft_queue_markdown": base / f"lena_kling_review_draft_queue_{day}.md",
        "image_diagnostics_report_json": base / f"lena_kling_image_diagnostics_report_{day}.json",
        "image_diagnostics_report_markdown": base / f"lena_kling_image_diagnostics_report_{day}.md",
        "final_review_packet_json": base / f"lena_kling_final_review_packet_{day}.json",
        "final_review_packet_markdown": base / f"lena_kling_final_review_packet_{day}.md",
        "final_review_packet_include_reviewed_json": base / f"lena_kling_final_review_packet_{day}_include_reviewed.json",
        "final_review_packet_include_reviewed_markdown": base / f"lena_kling_final_review_packet_{day}_include_reviewed.md",
        "post_kling_review_prep_json": base / f"lena_post_kling_review_prep_{day}.json",
        "post_kling_review_prep_markdown": base / f"lena_post_kling_review_prep_{day}.md",
        "apply_kling_review_packet_json": base / f"lena_apply_kling_review_packet_{day}.json",
        "apply_kling_review_packet_markdown": base / f"lena_apply_kling_review_packet_{day}.md",
    }
    return {
        key: str(path) if path.is_file() else ""
        for key, path in artifacts.items()
    }


def _publish_artifacts(day: str) -> dict:
    base_readiness = ROOT / "pipeline" / "publish_readiness" / "lena" / day
    base_packets = ROOT / "pipeline" / "publish_packets" / "lena" / day
    base_queue = ROOT / "pipeline" / "publishing" / "lena" / "approved_queue" / day
    base_closure = ROOT / "pipeline" / "publishing" / "lena" / "closure_reports" / day
    artifacts = {
        "publish_readiness_json": base_readiness / "publish_readiness_packet_v2_1.json",
        "publish_readiness_markdown": base_readiness / "PUBLISH_READINESS_PACKET.md",
        "publish_packets_json": base_packets / "lena_publish_packets_v2_4.json",
        "publish_packets_markdown": base_packets / "LENA_PUBLISH_PACKETS.md",
        "approved_queue_json": base_queue / "lena_approved_publish_queue_v2_8.json",
        "approved_queue_csv": base_queue / "lena_approved_publish_queue_v2_8.csv",
        "approved_queue_markdown": base_queue / "LENA_APPROVED_PUBLISH_QUEUE.md",
        "closure_report_json": base_closure / f"lena_publish_closure_{day}.json",
        "closure_report_markdown": base_closure / f"LENA_PUBLISH_CLOSURE_{day}.md",
    }
    return {
        key: str(path) if path.is_file() else ""
        for key, path in artifacts.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Lena daily 3-photo orchestrator v1")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Skip live generation; run rest without posting",
    )
    ap.add_argument(
        "--with-strategy-prep",
        action="store_true",
        help="Run the dry-run image-strategy autonomy prep stack before daily generation/publish steps",
    )
    ap.add_argument(
        "--strategy-prep-only",
        action="store_true",
        help="Run only the strategy autonomy prep step, then stop",
    )
    ap.add_argument(
        "--strategy-queue-limit",
        type=int,
        default=6,
        help="Queue slot count to pass into the strategy autonomy prep runner",
    )
    ap.add_argument(
        "--strategy-recipes",
        default="",
        help="Optional comma-separated recipe IDs for the strategy autonomy prep runner",
    )
    ap.add_argument(
        "--allow-continue-when-strategy-not-ready",
        action="store_true",
        help="Override the strategy readiness gate and continue into the older daily flow even when broader autonomy is not ready",
    )
    ap.add_argument(
        "--refresh-meta-feedback",
        action="store_true",
        help=(
            "Refresh live Meta metrics/comments before strategy autonomy prep so the "
            "planning layer reads fresher platform state."
        ),
    )
    args = ap.parse_args()

    day = args.date
    dr = args.dry_run
    if args.strategy_prep_only and not args.with_strategy_prep:
        args.with_strategy_prep = True

    started_at = datetime.now().isoformat(timespec="seconds")
    print(
        f"[orchestrator] date={day}  dry_run={dr}  "
        f"with_strategy_prep={args.with_strategy_prep}  "
        f"strategy_prep_only={args.strategy_prep_only}  "
        f"started={started_at}"
    )

    steps: list[dict] = []

    if args.with_strategy_prep:
        strategy_cmd = [
            PY,
            STRATEGY_AUTONOMY_RUNNER,
            "--date",
            day,
            "--queue-limit",
            str(args.strategy_queue_limit),
        ]
        if args.strategy_recipes:
            strategy_cmd.extend(["--recipes", args.strategy_recipes])
        if args.refresh_meta_feedback:
            strategy_cmd.append("--refresh-meta-feedback")
        steps.append(
            run_step(
                "strategy_autonomy_prep",
                strategy_cmd,
                capture_output=True,
            )
        )
        if not steps[-1]["ok"]:
            return _abort(steps, day, started_at, "strategy_autonomy_prep")
        if args.strategy_prep_only:
            return _finish(steps, day, started_at, ok=True)
        if (
            not args.allow_continue_when_strategy_not_ready
            and _strategy_gate_blocked(steps)
        ):
            print(
                "\n[orchestrator] STRATEGY GATE: broader autonomous generation "
                "is not ready yet. Stopping before legacy daily generation/publish "
                "steps. Use --allow-continue-when-strategy-not-ready only if you "
                "intend to override this guardrail."
            )
            return _abort(steps, day, started_at, "strategy_readiness_gate")

    # Step 1 - generate 3 Kling slots (skip entirely on dry-run)
    gen_cmd = [
        PY,
        "tools/generation/lena_run_daily_kling_omni_live_v1.py",
        "--date",
        day,
        "--limit",
        "3",
        "--execute-live",
        "--confirm-daily-three-photo-kling-omni-live",
    ]
    queue_report_path = _strategy_queue_report_path(steps)
    if queue_report_path:
        gen_cmd.extend(["--queue-report", queue_report_path])
    steps.append(run_step("generate", gen_cmd, dry_run=dr, skip_on_dry=True))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "generate")

    # Step 2 - quality gate + autonomous asset approval
    gate_cmd = [
        PY,
        "tools/lena_autonomous_asset_approval_gate_v2_6_1.py",
        "--date",
        day,
    ]
    steps.append(run_step("approval_gate", gate_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "approval_gate")

    # Step 3 - build publish readiness packet from exact-date approved assets
    readiness_cmd = [
        PY,
        "tools/lena_build_publish_readiness_packet_v2_1.py",
        "--date",
        day,
    ]
    steps.append(run_step("publish_readiness", readiness_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "publish_readiness")

    # Step 4 - generate publish packets (captions, hashtags, metadata)
    packet_cmd = [
        PY,
        "tools/lena_publish_packet_director_generate_v2_4.py",
        "--date",
        day,
    ]
    steps.append(run_step("packet_director", packet_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "packet_director")

    # Step 5 - build approved publish queue (Instagram Feed + Facebook Page)
    queue_cmd = [
        PY,
        "tools/lena_build_approved_publish_queue_v2_8.py",
        "--date",
        day,
        "--platforms",
        PLATFORMS,
    ]
    if dr:
        queue_cmd.append("--replace")
    steps.append(run_step("queue_build", queue_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "queue_build")

    return _finish(steps, day, started_at, ok=True)


def _abort(steps: list, day: str, started_at: str, failed_at: str) -> int:
    print(f"\n[orchestrator] ABORTED at step: {failed_at}")
    _write_report(steps, day, started_at, ok=False, aborted_at=failed_at)
    return 1


def _finish(steps: list, day: str, started_at: str, ok: bool) -> int:
    print(f"\n[orchestrator] DONE  ok={ok}")
    _write_report(steps, day, started_at, ok=ok)
    return 0 if ok else 1


def _write_report(
    steps: list,
    day: str,
    started_at: str,
    ok: bool,
    aborted_at: str = "",
) -> None:
    outdir = ROOT / "pipeline" / "publishing" / "lena" / "orchestrator_reports" / day
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    report = {
        "ok": ok,
        "version": "v1.6",
        "date": day,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "aborted_at": aborted_at,
        "strategy_summary": _strategy_summary_from_steps(steps),
        "strategy_gate": {
            "enforced": True,
            "blocked": aborted_at == "strategy_readiness_gate",
        },
        "review_artifacts": _review_artifacts(day),
        "publish_artifacts": _publish_artifacts(day),
        "steps": steps,
    }
    path = outdir / f"orchestrator_report_{ts}_v1_6.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[orchestrator] report: {path}")


if __name__ == "__main__":
    sys.exit(main())
