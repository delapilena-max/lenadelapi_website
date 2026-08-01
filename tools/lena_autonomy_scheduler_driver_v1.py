from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tools import lena_autonomy_runtime_evidence_v1 as autonomy_runtime
from tools import lena_autonomy_daily_schedule_v1 as schedule_mod
from tools import lena_full_photo_autonomy_v1 as full_autonomy
from tools import lena_autopublish_approved_queue_v2_8 as autonomous_publisher

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / Path(autonomy_runtime.SCHEDULER_DRIVER_RUNTIME_ROOT.as_posix())

REPORT_TYPE_RECEIPT = "lena_autonomy_scheduler_receipt"
SCHEMA_VERSION = "v1"

TERMINAL_STATUSES = {"published", "skipped"}


def _now_chicago() -> datetime:
    return datetime.now(schedule_mod.TZ)


def _normalize_now(now: datetime | None) -> datetime:
    now = now or _now_chicago()
    if now.tzinfo is None:
        # A naive --now override is treated as an America/Chicago wall
        # clock, not converted -- the whole point of an operator override
        # is to say "pretend it is this Chicago time", regardless of the
        # machine's own display timezone.
        return now.replace(tzinfo=schedule_mod.TZ)
    return now.astimezone(schedule_mod.TZ)


def _state_path(date_str: str, slot: str, state_root: Path) -> Path:
    return state_root / date_str / f"{slot}_state.json"


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_started"}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"status": "not_started"}
    if not isinstance(loaded, dict) or "status" not in loaded:
        return {"status": "not_started"}
    return loaded


def _write_state_atomic(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp{id(state)}")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _write_receipt(receipt_root: Path, date_str: str, slot: str, kind: str, payload: dict[str, Any], *, now: datetime) -> Path:
    stamp = now.strftime("%H%M%S_%f")
    receipt_dir = receipt_root / date_str
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"{slot}_{kind}_{stamp}.json"
    record = {
        "report_type": REPORT_TYPE_RECEIPT,
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "schedule_slot": slot,
        "receipt_kind": kind,
        "recorded_at": now.isoformat(),
        **payload,
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def run_slot_once(
    *,
    date_str: str,
    slot: str,
    now: datetime,
    schedule: dict[str, Any],
    state_root: Path,
    receipt_root: Path,
    policy_path: Path,
    run_cycle: Callable[..., dict[str, Any]],
    run_publish: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    state_path = _state_path(date_str, slot, state_root)
    state = _read_state(state_path)
    status = state.get("status", "not_started")
    generation_due_at = schedule_mod.generation_at(schedule, slot)
    publish_due_at = schedule_mod.publish_at(schedule, slot)

    if status in TERMINAL_STATUSES:
        return {"slot": slot, "action": "noop", "status": status}

    if status == "queued_awaiting_publish":
        if now < publish_due_at:
            return {"slot": slot, "action": "noop", "status": "queued_awaiting_publish"}
        try:
            publish_result = run_publish(day=date_str, slot_keyword=slot, limit=1, dry_run=False)
        except Exception as exc:  # noqa: BLE001 - recorded, never crashes the poll loop
            receipt = _write_receipt(
                receipt_root, date_str, slot, "publish_failure",
                {"error_code": str(getattr(exc, "code", "publish_error")), "error_detail": str(getattr(exc, "detail", str(exc)))},
                now=now,
            )
            _write_state_atomic(state_path, {"status": "queued_awaiting_publish", "last_publish_error": str(exc), "last_publish_receipt": str(receipt)})
            return {"slot": slot, "action": "publish_failed", "error": str(exc)}
        posted = int(publish_result.get("posted_count", 0)) == 1
        receipt = _write_receipt(receipt_root, date_str, slot, "publish", {"publish_result": publish_result, "posted": posted}, now=now)
        new_status = "published" if posted else "queued_awaiting_publish"
        _write_state_atomic(state_path, {"status": new_status, "publish_receipt": str(receipt)})
        return {"slot": slot, "action": "published" if posted else "publish_no_op", "publish_result": publish_result}

    if status == "generation_failed":
        if now < publish_due_at:
            return {"slot": slot, "action": "noop", "status": "generation_failed_awaiting_publish_time"}
        receipt = _write_receipt(receipt_root, date_str, slot, "skip", {"reason": "generation_failed_before_publish_time"}, now=now)
        _write_state_atomic(state_path, {"status": "skipped", "skip_receipt": str(receipt)})
        return {"slot": slot, "action": "skipped", "reason": "generation_failed"}

    # status == "not_started"
    if now >= publish_due_at:
        receipt = _write_receipt(receipt_root, date_str, slot, "skip", {"reason": "publish_time_reached_before_generation_started"}, now=now)
        _write_state_atomic(state_path, {"status": "skipped", "skip_receipt": str(receipt)})
        return {"slot": slot, "action": "skipped", "reason": "generation_never_started"}

    if now < generation_due_at:
        return {"slot": slot, "action": "noop", "status": "waiting_for_generation_window"}

    try:
        result = run_cycle(day=date_str, schedule_slot=slot, policy_path=policy_path, hold_for_publish=True)
    except full_autonomy.FullPhotoAutonomyError as exc:
        if exc.code == "cycle_already_running":
            # Another slot's cycle currently holds the day lock -- try
            # again next poll instead of failing the slot.
            return {"slot": slot, "action": "noop", "status": "day_lock_busy"}
        # Any other failure (including schedule_slot_already_used_today,
        # which means canonical on-disk state says this slot was already
        # authorized -- e.g. our own state file was lost after a crash)
        # fails this slot closed. We never re-authorize a slot; recovery
        # means trusting the authoritative authorization/report files, not
        # guessing a retry is safe.
        receipt = _write_receipt(receipt_root, date_str, slot, "generation_failure", {"error_code": exc.code, "error_detail": exc.detail}, now=now)
        _write_state_atomic(state_path, {"status": "generation_failed", "generation_receipt": str(receipt)})
        return {"slot": slot, "action": "generation_failed", "error_code": exc.code}

    ok = bool(result.get("ok"))
    disposition = result.get("autonomous_disposition")
    if ok and disposition == "accept_and_hold_for_publish":
        receipt = _write_receipt(receipt_root, date_str, slot, "generation", {"result": result}, now=now)
        _write_state_atomic(state_path, {"status": "queued_awaiting_publish", "generation_receipt": str(receipt)})
        if now < publish_due_at:
            return {"slot": slot, "action": "generated_and_queued"}
        # Generation ran long enough that publish is already due by the
        # time it finished -- act immediately rather than waiting for the
        # next minute's poll.
        return run_slot_once(
            date_str=date_str, slot=slot, now=now, schedule=schedule,
            state_root=state_root, receipt_root=receipt_root, policy_path=policy_path,
            run_cycle=run_cycle, run_publish=run_publish,
        )

    receipt = _write_receipt(receipt_root, date_str, slot, "generation_failure", {"result": result}, now=now)
    _write_state_atomic(state_path, {"status": "generation_failed", "generation_receipt": str(receipt)})
    return {"slot": slot, "action": "generation_failed", "disposition": disposition}


def run_once(
    *,
    now: datetime | None = None,
    date_str: str | None = None,
    schedule_root: Path | None = None,
    state_root: Path | None = None,
    receipt_root: Path | None = None,
    policy_path: Path = full_autonomy.POLICY_PATH,
    run_cycle: Callable[..., dict[str, Any]] = full_autonomy.run_controlled_cycle,
    run_publish: Callable[..., dict[str, Any]] = autonomous_publisher.run_scheduled_autonomous,
    inspect_only: bool = False,
) -> dict[str, Any]:
    resolved_now = _normalize_now(now)
    resolved_date = date_str or resolved_now.date().isoformat()
    schedule = schedule_mod.load_or_create_daily_schedule(resolved_date, schedule_root=schedule_root)

    if inspect_only:
        return {
            "ok": True,
            "mode": "inspect_only",
            "date": resolved_date,
            "now": resolved_now.isoformat(),
            "timezone": schedule_mod.TIMEZONE_NAME,
            "schedule": schedule,
        }

    resolved_state_root = state_root or STATE_ROOT
    resolved_receipt_root = receipt_root or STATE_ROOT
    results = [
        run_slot_once(
            date_str=resolved_date,
            slot=slot,
            now=resolved_now,
            schedule=schedule,
            state_root=resolved_state_root,
            receipt_root=resolved_receipt_root,
            policy_path=policy_path,
            run_cycle=run_cycle,
            run_publish=run_publish,
        )
        for slot in schedule_mod.SLOT_ORDER
    ]
    return {"ok": True, "mode": "run", "date": resolved_date, "now": resolved_now.isoformat(), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotent per-minute driver for Lena's controlled photo autonomy schedule.")
    parser.add_argument("--inspect-only", action="store_true", help="Show today's deterministic schedule without generating or publishing.")
    parser.add_argument("--now", default=None, help="Override 'now' as an ISO datetime, for testing/inspection (interpreted as America/Chicago if no UTC offset is given).")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else None
    report = run_once(now=now, inspect_only=args.inspect_only)
    print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
