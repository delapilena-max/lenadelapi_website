"""
pipeline.scheduler_jobs
=======================

Registers the default autonomous content_bot jobs:

- periodic_lena_production: maintains Lena production manifest, packages completed Kling outputs, runs contract preflight
- periodic_posting: creates/uses daily schedule and drains pipeline/queue
- periodic_backup: calls backup_manager when available

Importing this module is safe and idempotent. Call register_jobs() from the
orchestrator or use pipeline.scheduler.import_jobs().
"""
from __future__ import annotations

from typing import Any, Dict, List
import importlib
import os
import traceback

try:
    from . import scheduler
    from .feedback.collector import FeedbackCollector
    from .posting_manager import PostingManager, truthy, read_json
    from .schedule.generator import due_slots, ensure_daily_schedule, mark_slot_used, save_schedule
except Exception:  # direct script fallback
    import scheduler  # type: ignore
    from feedback.collector import FeedbackCollector  # type: ignore
    from posting_manager import PostingManager, truthy, read_json  # type: ignore
    from schedule.generator import due_slots, ensure_daily_schedule, mark_slot_used, save_schedule  # type: ignore


def _feedback() -> FeedbackCollector:
    return FeedbackCollector(
        scheduler.get_config().get("posting", {}).get("feedback_file")
        or "feedback/feedback.jsonl"
    )


def _job_cfg(name: str) -> Dict[str, Any]:
    cfg = scheduler.get_config().get("jobs", {}).get(name, {})
    return cfg if isinstance(cfg, dict) else {}


def manager_config_from_scheduler(post_cfg: Dict[str, Any]) -> Dict[str, Any]:
    from .posting_manager import load_config  # type: ignore

    cfg = load_config()
    cfg.update(post_cfg or {})
    return cfg


def periodic_lena_production_job() -> Dict[str, Any]:
    """
    Autonomous Lena production supervisor.

    Creates/maintains the machine-readable Lena production manifest,
    packages completed Kling outputs into pipeline/queue, and runs contract
    preflight. This job does not post by itself.
    """
    from pipeline.lena_production_job import run_lena_production

    return run_lena_production()


def periodic_posting_job() -> Dict[str, Any]:
    cfg = scheduler.get_config()
    post_cfg = cfg.get("posting", {}) if isinstance(cfg.get("posting"), dict) else {}
    schedule_cfg = cfg.get("schedule", {}) if isinstance(cfg.get("schedule"), dict) else {}
    job_cfg = _job_cfg("periodic_posting")
    fb = _feedback()

    schedule_payload = ensure_daily_schedule(schedule_cfg)

    force_due = truthy(os.environ.get("CONTENT_BOT_FORCE_POSTING_DUE")) or truthy(
        job_cfg.get("force_due", False)
    )

    if force_due:
        slots = [
            slot
            for slot in schedule_payload.get("slots", [])
            if isinstance(slot, dict) and not slot.get("used")
        ]
    else:
        slots = due_slots(schedule_payload)

    media_filter_value = (
        os.environ.get("LENA_AUTONOMOUS_ONLY_MEDIA_TYPE")
        or job_cfg.get("only_media_type")
        or ""
    )
    allowed_media_types = {
        part.strip().lower()
        for part in str(media_filter_value).split(",")
        if part.strip()
    }
    if allowed_media_types:
        slots = [
            slot
            for slot in slots
            if str(slot.get("media_type") or "").strip().lower() in allowed_media_types
        ]

    max_posts = int(job_cfg.get("max_posts_per_run") or post_cfg.get("max_posts_per_run") or 3)
    max_posts = max(0, max_posts)

    dry_run = truthy(post_cfg.get("dry_run", True))
    if "CONTENT_BOT_POSTING_DRY_RUN" in os.environ:
        dry_run = truthy(os.environ.get("CONTENT_BOT_POSTING_DRY_RUN"))

    manager = PostingManager(config={**manager_config_from_scheduler(post_cfg), "dry_run": dry_run})

    slot_results: List[Dict[str, Any]] = []
    processed_posts = 0
    schedule_dirty = False

    for slot in slots:
        slot_id = str(slot.get("slot_id") or "").strip()
        media_type = str(slot.get("media_type") or "").lower()
        matched_path = None
        for post_file in manager.list_post_files():
            payload = read_json(post_file, {})
            if not isinstance(payload, dict):
                continue
            payload_slot_id = str(payload.get("slot_id") or post_file.stem).strip()
            payload_media_type = str(payload.get("media_type") or "").lower().strip()
            if payload_slot_id == slot_id and (not media_type or payload_media_type == media_type):
                matched_path = post_file
                break

        if matched_path is None:
            result = {
                "ok": False,
                "status": "slot_missing_queue_item",
                "slot_id": slot_id,
                "media_type": media_type,
                "success_count": 0,
                "failed_count": 0,
            }
        elif processed_posts >= max_posts:
            result = {
                "ok": True,
                "status": "deferred_max_posts",
                "slot_id": slot_id,
                "media_type": media_type,
                "matched_queue_path": str(matched_path),
                "success_count": 0,
                "failed_count": 0,
            }
        else:
            process_result = manager.process_one(matched_path, dry_run=dry_run, media_types=[media_type] if media_type else None)
            status = str(process_result.get("status") or "")
            processed_posts += 1
            result = {
                "ok": status in {"success", "dry_run"},
                "status": status,
                "slot_id": slot_id,
                "media_type": media_type,
                "matched_queue_path": str(matched_path),
                "process_result": process_result,
                "success_count": 1 if status in {"success", "dry_run"} else 0,
                "failed_count": 1 if status in {"failed", "dry_run_failed"} else 0,
            }

        slot_record: Dict[str, Any] = {
            "slot_id": slot_id,
            "media_type": media_type,
            "posting_result": result,
        }

        if result.get("success_count", 0) > 0 and not dry_run:
            mark_slot_used(
                schedule_payload,
                str(slot.get("slot_id")),
                metadata={"posting_result": result},
            )
            slot_record["marked_used"] = True
        elif result.get("success_count", 0) > 0 and dry_run:
            slot_record["marked_used"] = False
            slot_record["reason"] = "dry_run"
        elif result.get("status") == "deferred_max_posts":
            slot_record["marked_used"] = False
            slot_record["reason"] = "max_posts_reached"
        else:
            if not dry_run and result.get("status") in {"slot_missing_queue_item", "failed"}:
                slot["attempts"] = int(slot.get("attempts") or 0) + 1
                schedule_dirty = True
            slot_record["marked_used"] = False

        slot_results.append(slot_record)

    if schedule_dirty and not dry_run:
        save_schedule(schedule_payload)

    status = (
        "success"
        if all(r.get("posting_result", {}).get("failed_count", 0) == 0 for r in slot_results)
        else "failure"
    )

    payload = {
        "ok": status == "success",
        "dry_run": dry_run,
        "schedule_path": schedule_payload.get("path"),
        "due_slots": len(slots),
        "media_type_filter": sorted(allowed_media_types),
        "processed_posts": processed_posts,
        "slot_results": slot_results,
        "timestamp_utc": scheduler.utc_now().isoformat(),
    }

    fb.append(event_type="periodic_posting", status=status, metadata=payload)
    return payload


def _import_backup_manager():
    for module_name in ("pipeline.backup_manager", "backup_manager"):
        try:
            return importlib.import_module(module_name)
        except Exception:
            continue
    return None


def periodic_backup_job() -> Dict[str, Any]:
    cfg = scheduler.get_config()
    backup_cfg = cfg.get("backup", {}) if isinstance(cfg.get("backup"), dict) else {}
    fb = _feedback()

    if not truthy(backup_cfg.get("enabled", True)):
        payload = {"ok": True, "status": "skipped", "reason": "backup disabled by config"}
        fb.append(event_type="periodic_backup", status="success", metadata=payload)
        return payload

    dry_run = truthy(backup_cfg.get("dry_run", False)) or truthy(
        os.environ.get("CONTENT_BOT_BACKUP_DRY_RUN")
    )

    if dry_run:
        payload = {
            "ok": True,
            "status": "dry_run",
            "reason": "backup dry-run enabled; backup_manager import skipped",
        }
        fb.append(event_type="periodic_backup", status="success", metadata=payload)
        return payload

    module = _import_backup_manager()

    if module is None:
        payload = {"ok": True, "status": "skipped", "reason": "backup_manager module not found"}
        fb.append(event_type="periodic_backup", status="success", metadata=payload)
        return payload

    for name in ("run_backup", "perform_backup", "create_backup", "backup", "main"):
        fn = getattr(module, name, None)

        if callable(fn):
            try:
                result = fn()
                payload = {
                    "ok": True,
                    "status": "success",
                    "callable": name,
                    "result": result,
                }
                fb.append(event_type="periodic_backup", status="success", metadata=payload)
                return payload
            except Exception as exc:
                payload = {
                    "ok": False,
                    "status": "failure",
                    "callable": name,
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=10),
                }
                fb.append(
                    event_type="periodic_backup",
                    status="failure",
                    error=str(exc),
                    metadata=payload,
                )
                return payload

    payload = {
        "ok": True,
        "status": "skipped",
        "reason": "backup_manager has no supported callable",
    }
    fb.append(event_type="periodic_backup", status="success", metadata=payload)
    return payload


def register_jobs() -> None:
    scheduler.load_config()

    scheduler.register_job(
        "periodic_lena_production",
        periodic_lena_production_job,
        interval_seconds=_job_cfg("periodic_lena_production").get("interval_seconds", 300),
        enabled=_job_cfg("periodic_lena_production").get("enabled", True),
        run_on_start=_job_cfg("periodic_lena_production").get("run_on_start", True),
        description=(
            "Maintain Lena production manifest, package completed Kling outputs, "
            "and run contract preflight."
        ),
        metadata={"component": "lena_production", "node": "lena"},
    )

    scheduler.register_job(
        "periodic_posting",
        periodic_posting_job,
        interval_seconds=_job_cfg("periodic_posting").get("interval_seconds", 300),
        enabled=_job_cfg("periodic_posting").get("enabled", True),
        run_on_start=_job_cfg("periodic_posting").get("run_on_start", True),
        description="Create daily schedule and process due posts from pipeline/queue.",
        metadata={"component": "posting", "node": "lena"},
    )

    scheduler.register_job(
        "periodic_backup",
        periodic_backup_job,
        interval_seconds=_job_cfg("periodic_backup").get("interval_seconds", 3600),
        enabled=_job_cfg("periodic_backup").get("enabled", True),
        run_on_start=_job_cfg("periodic_backup").get("run_on_start", False),
        description="Run backup_manager when available and record feedback.",
        metadata={"component": "backup"},
    )


# Idempotent import behavior: importing the module registers/updates jobs once.
register_jobs()
