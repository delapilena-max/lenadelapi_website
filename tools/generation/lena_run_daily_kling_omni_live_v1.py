from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
LIVE_TEST = ROOT / "tools" / "generation" / "lena_kling_omni_image_public_api_live_test_v1.py"
SUBMIT_PAYLOAD = ROOT / "tools" / "strategy" / "lena_submit_kling_payload_v1.py"
LOG_ASSET = ROOT / "tools" / "lena_log_asset_v1_8.py"
BUILD_REVIEW_QUEUE = ROOT / "tools" / "strategy" / "lena_build_unreviewed_kling_result_queue_v1.py"
BUILD_REVIEW_DRAFT_QUEUE = ROOT / "tools" / "strategy" / "lena_build_kling_review_draft_queue_v1.py"
BUILD_IMAGE_DIAGNOSTICS_REPORT = ROOT / "tools" / "strategy" / "lena_build_kling_image_diagnostics_report_v1.py"
BUILD_FINAL_REVIEW_PACKET = ROOT / "tools" / "strategy" / "lena_build_kling_final_review_packet_v1.py"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
PAYLOAD_BASE = ROOT / "pipeline" / "strategy" / "lena" / "kling_payloads"
WORKORDER_BASE = ROOT / "pipeline" / "provider_workorders" / "openart_seedance"
RESULTS_BASE = ROOT / "pipeline" / "strategy" / "lena" / "kling_results"

SLOTS = [
    {"key": "morning", "slot_type": "morning_lifestyle_photo", "extras": []},
    {"key": "afternoon", "slot_type": "lifestyle_photo", "extras": []},
    {"key": "evening", "slot_type": "evening_candid_photo", "extras": []},
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def norm_text(value: str) -> str:
    return str(value or "").replace("_", " ").strip()


def discover_queue_report(run_date: str) -> Path | None:
    path = NEXT_ACTIONS / run_date / f"lena_autonomous_generation_queue_dryrun_{run_date}.json"
    return path if path.is_file() else None


def payload_path(run_date: str, recipe_id: str) -> Path:
    return PAYLOAD_BASE / run_date / f"kling_payload_dryrun_{run_date}_{recipe_id}.json"


def latest_manifest(run_date: str, recipe_id: str) -> Path | None:
    matches = sorted((RESULTS_BASE / run_date).glob(f"kling_result_{run_date}_{recipe_id}*.json"))
    return matches[-1] if matches else None


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def refresh_review_queue(run_date: str) -> dict:
    proc = run_cmd([PYTHON, str(BUILD_REVIEW_QUEUE), "--date", run_date])
    parsed = {}
    if proc.stdout.strip().startswith("{"):
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = {}
    return {
        "ok": proc.returncode == 0,
        "json": parsed.get("json", ""),
        "markdown": parsed.get("markdown", ""),
        "unreviewed_count": parsed.get("unreviewed_count", 0),
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-10:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-10:],
    }


def refresh_review_draft_queue(run_date: str) -> dict:
    proc = run_cmd([PYTHON, str(BUILD_REVIEW_DRAFT_QUEUE), "--date", run_date])
    parsed = {}
    if proc.stdout.strip().startswith("{"):
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = {}
    return {
        "ok": proc.returncode == 0,
        "json": parsed.get("json", ""),
        "markdown": parsed.get("markdown", ""),
        "entry_count": parsed.get("entry_count", 0),
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-10:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-10:],
    }


def refresh_final_review_packet(run_date: str) -> dict:
    proc = run_cmd([PYTHON, str(BUILD_FINAL_REVIEW_PACKET), "--date", run_date])
    parsed = {}
    if proc.stdout.strip().startswith("{"):
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = {}
    return {
        "ok": proc.returncode == 0,
        "json": parsed.get("json", ""),
        "markdown": parsed.get("markdown", ""),
        "entry_count": parsed.get("entry_count", 0),
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-10:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-10:],
    }


def refresh_image_diagnostics_report(run_date: str) -> dict:
    proc = run_cmd([PYTHON, str(BUILD_IMAGE_DIAGNOSTICS_REPORT), "--date", run_date])
    parsed = {}
    if proc.stdout.strip().startswith("{"):
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = {}
    return {
        "ok": proc.returncode == 0,
        "json": parsed.get("json", ""),
        "markdown": parsed.get("markdown", ""),
        "entry_count": parsed.get("entry_count", 0),
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-10:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-10:],
    }


def locate_packet_from_payload(payload_file: Path) -> dict:
    envelope = read_json(payload_file)
    packet_path = Path(str(envelope.get("source_packet_path", "")))
    packet = read_json(packet_path) if packet_path.is_file() else {}
    return {"envelope": envelope, "packet": packet, "packet_path": packet_path}


def build_slot_id(run_date: str, index: int) -> str:
    return f"{run_date}-{index:02d}-photo"


def lane_label(packet: dict) -> str:
    scene = norm_text(packet.get("scene_type", ""))
    pillar = norm_text(packet.get("content_pillar", ""))
    title = norm_text(packet.get("title", ""))
    joined = " | ".join(part for part in [scene, pillar, title] if part)
    return joined or "lifestyle"


def pose_label(queue_slot: dict, packet: dict) -> str:
    return (
        norm_text(queue_slot.get("scene_type", ""))
        or norm_text(packet.get("scene_type", ""))
        or norm_text(queue_slot.get("title", ""))
        or "camera-roll still"
    )


def location_label(queue_slot: dict, packet: dict) -> str:
    env_context = norm_text(packet.get("environment_context", ""))
    env_id = norm_text(queue_slot.get("environment_used", "") or packet.get("environment_id", ""))
    if env_context and env_id:
        return f"{env_id} | {env_context}"
    return env_context or env_id or "unknown"


def mood_label(queue_slot: dict, packet: dict) -> str:
    title = norm_text(queue_slot.get("title", "") or packet.get("title", ""))
    pillar = norm_text(packet.get("content_pillar", ""))
    return title or pillar or "strategy queue generation"


def build_bridge_workorder(
    *,
    run_date: str,
    slot_id: str,
    queue_slot: dict,
    packet: dict,
    packet_path: Path,
    payload_file: Path,
    manifest_file: Path,
    image_path: str,
) -> dict:
    return {
        "version": "v1.0.0",
        "seeded_by": "lena_strategy_queue_kling_bridge_v1",
        "date": run_date,
        "slot_id": slot_id,
        "media_type": "photo",
        "workorder_type": "photo",
        "provider_tool": "Kling Omni Character Element",
        "provider": "kling",
        "lane": lane_label(packet),
        "pillar": norm_text(packet.get("content_pillar", "")),
        "scene": norm_text(queue_slot.get("scene_type", "") or packet.get("scene_type", "")),
        "shot_description": norm_text(queue_slot.get("title", "") or packet.get("scene_type", "")),
        "recipe_id": queue_slot.get("recipe_id", ""),
        "outfit_id": queue_slot.get("outfit_used", "") or packet.get("wardrobe_outfit_id", ""),
        "environment_id": queue_slot.get("environment_used", "") or packet.get("environment_id", ""),
        "asset_path": image_path,
        "source_payload_path": str(payload_file),
        "source_packet_path": str(packet_path),
        "source_result_manifest_path": str(manifest_file),
        "priority_score": queue_slot.get("priority_score", 0),
        "queue_why": queue_slot.get("why", []),
        "manual_approval_required": True,
        "public_action_locked": True,
        "auto_posting": False,
        "auto_replying": False,
        "auto_outreach": False,
    }


def write_bridge_workorder(run_date: str, slot_id: str, payload: dict) -> Path:
    out_dir = WORKORDER_BASE / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slot_id}_provider_workorder.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def log_asset(
    *,
    run_date: str,
    slot_id: str,
    image_path: str,
    queue_slot: dict,
    packet: dict,
    manifest: dict,
    payload_file: Path,
) -> subprocess.CompletedProcess[str]:
    recipe_id = queue_slot.get("recipe_id", "")
    notes = " | ".join(
        [
            "Strategy queue Kling bridge v1",
            f"recipe {recipe_id}",
            f"task_id {manifest.get('task_id', '')}",
            f"payload {payload_file.name}",
            f"result_manifest {Path(str(manifest.get('source_manifest_path', ''))).name or Path(str(image_path)).name}",
        ]
    )
    cmd = [
        PYTHON,
        str(LOG_ASSET),
        "--source-path",
        image_path,
        "--date",
        run_date,
        "--slot-id",
        slot_id,
        "--media-type",
        "photo",
        "--provider",
        "kling",
        "--status",
        "generated",
        "--lane",
        lane_label(packet),
        "--outfit",
        queue_slot.get("outfit_used", "") or packet.get("wardrobe_outfit_id", "") or "unknown",
        "--location",
        location_label(queue_slot, packet),
        "--pose-motion",
        pose_label(queue_slot, packet),
        "--mood",
        mood_label(queue_slot, packet),
        "--quality-score",
        "70",
        "--identity-score",
        "70",
        "--reuse-score",
        "50",
        "--notes",
        notes,
    ]
    return run_cmd(cmd)


def submit_strategy_queue_slot(
    *,
    run_date: str,
    queue_slot: dict,
    slot_index: int,
    live: bool,
) -> dict:
    recipe_id = queue_slot.get("recipe_id", "")
    slot_id = build_slot_id(run_date, slot_index)
    current_payload = payload_path(run_date, recipe_id)
    if not current_payload.is_file():
        return {
            "mode": "strategy_queue",
            "slot_id": slot_id,
            "recipe_id": recipe_id,
            "ok": False,
            "error": f"payload file missing: {current_payload}",
        }

    packet_info = locate_packet_from_payload(current_payload)
    before_manifest = latest_manifest(run_date, recipe_id)
    cmd = [PYTHON, str(SUBMIT_PAYLOAD), "--payload", str(current_payload)]
    if live:
        cmd.extend(["--live", "--i-understand-this-spends-credits"])
    proc = run_cmd(cmd)
    after_manifest = latest_manifest(run_date, recipe_id)
    manifest_file = after_manifest if after_manifest and after_manifest != before_manifest else after_manifest
    manifest = read_json(manifest_file) if manifest_file and manifest_file.is_file() else {}

    workorder_file = None
    asset_log = None
    asset_row = {}
    if live and proc.returncode == 0 and manifest.get("saved_image_paths"):
        first_image = manifest["saved_image_paths"][0]
        bridge = build_bridge_workorder(
            run_date=run_date,
            slot_id=slot_id,
            queue_slot=queue_slot,
            packet=packet_info["packet"],
            packet_path=packet_info["packet_path"],
            payload_file=current_payload,
            manifest_file=manifest_file,
            image_path=first_image,
        )
        workorder_file = write_bridge_workorder(run_date, slot_id, bridge)
        asset_log = log_asset(
            run_date=run_date,
            slot_id=slot_id,
            image_path=first_image,
            queue_slot=queue_slot,
            packet=packet_info["packet"],
            manifest=manifest,
            payload_file=current_payload,
        )
        if asset_log.returncode == 0 and asset_log.stdout.strip().startswith("{"):
            try:
                asset_row = json.loads(asset_log.stdout).get("row", {})
            except json.JSONDecodeError:
                asset_row = {}

    return {
        "mode": "strategy_queue",
        "slot_id": slot_id,
        "recipe_id": recipe_id,
        "title": queue_slot.get("title", ""),
        "ok": proc.returncode == 0,
        "payload_path": str(current_payload),
        "manifest_path": str(manifest_file) if manifest_file else "",
        "task_id": manifest.get("task_id", ""),
        "saved_image_paths": manifest.get("saved_image_paths", []),
        "asset_memory_row": asset_row,
        "bridge_workorder_path": str(workorder_file) if workorder_file else "",
        "transport_stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
        "transport_stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        "asset_log_ok": bool(asset_log and asset_log.returncode == 0),
        "asset_log_stderr_tail": ([line for line in asset_log.stderr.splitlines() if line.strip()][-10:] if asset_log else []),
    }


def run_strategy_queue_mode(run_date: str, queue_report: Path, live: bool, limit: int) -> int:
    queue = read_json(queue_report)
    queue_slots = queue.get("queue_slots", [])[:limit]
    if not queue_slots:
        print(json.dumps({"ok": False, "error": f"no queue slots in {queue_report}"}, indent=2, ensure_ascii=False))
        return 1

    print(f"[lena_run_daily_kling_omni_live_v1] mode        : strategy_queue")
    print(f"[lena_run_daily_kling_omni_live_v1] date        : {run_date}")
    print(f"[lena_run_daily_kling_omni_live_v1] queue_report: {queue_report}")
    print(f"[lena_run_daily_kling_omni_live_v1] limit       : {limit}")
    print(f"[lena_run_daily_kling_omni_live_v1] live        : {live}")

    results = []
    for index, queue_slot in enumerate(queue_slots, start=1):
        recipe_id = queue_slot.get("recipe_id", "")
        print(f"\n[runner] queue_slot={index} recipe={recipe_id} live={live}")
        result = submit_strategy_queue_slot(
            run_date=run_date,
            queue_slot=queue_slot,
            slot_index=index,
            live=live,
        )
        results.append(result)
        print(f"[runner] status={result['ok']} slot_id={result['slot_id']} manifest={result.get('manifest_path', '')}")

    all_ok = all(item.get("ok") for item in results)
    summary = {
        "ok": all_ok,
        "mode": "strategy_queue",
        "date": run_date,
        "queue_report": str(queue_report),
        "live": live,
        "limit": limit,
        "result_count": len(results),
        "results": results,
    }
    review_queue = refresh_review_queue(run_date)
    summary["review_queue_refresh"] = review_queue
    summary["review_draft_queue_refresh"] = refresh_review_draft_queue(run_date)
    summary["image_diagnostics_refresh"] = refresh_image_diagnostics_report(run_date)
    summary["final_review_packet_refresh"] = refresh_final_review_packet(run_date)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if all_ok else 1


def run_legacy_slot_mode(run_date: str, live: bool) -> int:
    dc = run_date.replace("-", "")
    batch = f"lena_kling_omni_daily_{dc}.json"

    print(f"[lena_run_daily_kling_omni_live_v1] mode  : legacy_slots")
    print(f"[lena_run_daily_kling_omni_live_v1] date  : {run_date}")
    print(f"[lena_run_daily_kling_omni_live_v1] batch : {batch}")
    print(f"[lena_run_daily_kling_omni_live_v1] live  : {live}")

    results = []
    for slot in SLOTS:
        rid = f"kling_omni_daily_{slot['key']}_{dc}"
        cmd = [
            PYTHON,
            str(LIVE_TEST),
            "--date",
            run_date,
            "--batch",
            batch,
            "--slot",
            slot["slot_type"],
            "--result-id",
            rid,
        ]
        for extra_id in slot["extras"]:
            cmd.extend(["--extra-element-id", str(extra_id)])
        if live:
            cmd.extend(["--execute-live", "--confirm-single-slot-official-omni-test"])
        print(f"\n[runner] slot={slot['slot_type']} live={live}")
        proc = subprocess.run(cmd, cwd=str(ROOT))
        results.append({"slot": slot["slot_type"], "rc": proc.returncode, "result_id": rid})

    all_ok = all(item["rc"] == 0 for item in results)
    summary = {"ok": all_ok, "mode": "legacy_slots", "results": results}
    summary["review_queue_refresh"] = refresh_review_queue(run_date)
    summary["review_draft_queue_refresh"] = refresh_review_draft_queue(run_date)
    summary["image_diagnostics_refresh"] = refresh_image_diagnostics_report(run_date)
    summary["final_review_packet_refresh"] = refresh_final_review_packet(run_date)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--execute-live", action="store_true", dest="execute_live")
    parser.add_argument(
        "--confirm-daily-three-photo-kling-omni-live",
        action="store_true",
        dest="confirm_live",
    )
    parser.add_argument("--queue-report", default="")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    live = args.execute_live and args.confirm_live
    queue_report = Path(args.queue_report) if args.queue_report else discover_queue_report(args.date)

    if queue_report and queue_report.is_file():
        return run_strategy_queue_mode(args.date, queue_report, live, args.limit)
    return run_legacy_slot_mode(args.date, live)


if __name__ == "__main__":
    raise SystemExit(main())
