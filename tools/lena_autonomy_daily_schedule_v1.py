from __future__ import annotations

import hashlib
import json
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "daily_schedule"

TIMEZONE_NAME = "America/Chicago"
TZ = ZoneInfo(TIMEZONE_NAME)

REPORT_TYPE = "lena_autonomy_daily_schedule"
SCHEMA_VERSION = "v1"

GENERATION_LEAD_MINUTES = 45
VARIATION_WINDOW_MINUTES = 10

# Authoritative base publish times (2026-07-24, Nicolas). Deterministically
# varied by up to +/-10 minutes per date so the schedule is not a fixed
# clock tick, while staying reproducible: the same date always produces the
# same three times (see _slot_offset_minutes).
SLOT_BASE_TIMES: dict[str, tuple[int, int]] = {
    "morning": (10, 27),
    "afternoon": (14, 14),
    "evening": (19, 45),
}
SLOT_ORDER: tuple[str, ...] = ("morning", "afternoon", "evening")


class DailyScheduleError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise DailyScheduleError(code, detail)


def _parse_date(date_str: str) -> date_cls:
    try:
        return date_cls.fromisoformat(date_str)
    except (TypeError, ValueError) as exc:
        raise DailyScheduleError("invalid_date", f"{date_str!r} is not a valid ISO date") from exc


def _slot_seed(date_str: str, slot: str) -> int:
    # Deterministic per (date, slot): same inputs always hash to the same
    # integer, so the same date always reproduces the same three times.
    digest = hashlib.sha256(f"lena_autonomy_daily_schedule_v1|{date_str}|{slot}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _slot_offset_minutes(date_str: str, slot: str) -> int:
    span = 2 * VARIATION_WINDOW_MINUTES + 1  # 21 integer values: -10..+10 inclusive
    return (_slot_seed(date_str, slot) % span) - VARIATION_WINDOW_MINUTES


def _fingerprint_from_slots(slots: dict[str, Any]) -> str:
    fingerprint_source = json.dumps(
        {slot: {"publish_at": slots[slot]["publish_at"], "offset_minutes": slots[slot]["offset_minutes"]} for slot in SLOT_ORDER},
        sort_keys=True,
    )
    return hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()


def compute_daily_schedule(date_str: str) -> dict[str, Any]:
    parsed = _parse_date(date_str)
    slots: dict[str, Any] = {}
    previous_publish_at: datetime | None = None
    for slot in SLOT_ORDER:
        hour, minute = SLOT_BASE_TIMES[slot]
        base_dt = datetime(parsed.year, parsed.month, parsed.day, hour, minute, tzinfo=TZ)
        offset_minutes = _slot_offset_minutes(date_str, slot)
        publish_at = base_dt + timedelta(minutes=offset_minutes)
        generation_at = publish_at - timedelta(minutes=GENERATION_LEAD_MINUTES)
        if previous_publish_at is not None:
            _require(publish_at > previous_publish_at, "slots_not_ordered", f"{slot} publish time does not strictly follow the prior slot")
        previous_publish_at = publish_at
        slots[slot] = {
            "schedule_slot": slot,
            "base_time": f"{hour:02d}:{minute:02d}",
            "offset_minutes": offset_minutes,
            "publish_at": publish_at.isoformat(),
            "generation_at": generation_at.isoformat(),
            "seed": _slot_seed(date_str, slot),
        }
    fingerprint = _fingerprint_from_slots(slots)
    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "timezone": TIMEZONE_NAME,
        "generation_lead_minutes": GENERATION_LEAD_MINUTES,
        "variation_window_minutes": VARIATION_WINDOW_MINUTES,
        "slot_order": list(SLOT_ORDER),
        "slots": slots,
        "fingerprint_sha256": fingerprint,
    }


def daily_schedule_path(date_str: str, schedule_root: Path | None = None) -> Path:
    root = schedule_root or SCHEDULE_ROOT
    return root / date_str / f"lena_autonomy_daily_schedule_{date_str}.json"


def load_or_create_daily_schedule(date_str: str, *, schedule_root: Path | None = None) -> dict[str, Any]:
    root = schedule_root or SCHEDULE_ROOT
    path = daily_schedule_path(date_str, root)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyScheduleError("schedule_artifact_missing_or_invalid", f"{path}: {exc}") from exc
        _require(isinstance(existing, dict) and existing.get("report_type") == REPORT_TYPE, "schedule_artifact_invalid", f"{path} is not a daily schedule artifact")
        _require(existing.get("date") == date_str, "schedule_artifact_date_mismatch", f"{path} date does not match {date_str}")
        existing_slots = existing.get("slots")
        _require(isinstance(existing_slots, dict) and set(existing_slots) == set(SLOT_ORDER), "schedule_artifact_slots_invalid", f"{path} slots are missing or incomplete")
        _require(
            existing.get("fingerprint_sha256") == _fingerprint_from_slots(existing_slots),
            "schedule_artifact_fingerprint_mismatch",
            f"{path} declared fingerprint does not match its own slot data -- artifact was edited after being written",
        )
        recomputed = compute_daily_schedule(date_str)
        _require(
            existing.get("fingerprint_sha256") == recomputed["fingerprint_sha256"],
            "schedule_artifact_drift",
            f"{path} fingerprint does not match deterministic recomputation for {date_str}",
        )
        result = dict(existing)
        result["schedule_artifact_path"] = str(path)
        return result
    computed = compute_daily_schedule(date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp{id(computed)}")
    tmp_path.write_text(json.dumps(computed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        tmp_path.replace(path)
    except FileExistsError:
        tmp_path.unlink(missing_ok=True)
        return load_or_create_daily_schedule(date_str, schedule_root=root)
    result = dict(computed)
    result["schedule_artifact_path"] = str(path)
    return result


def publish_at(schedule: dict[str, Any], slot: str) -> datetime:
    return datetime.fromisoformat(schedule["slots"][slot]["publish_at"])


def generation_at(schedule: dict[str, Any], slot: str) -> datetime:
    return datetime.fromisoformat(schedule["slots"][slot]["generation_at"])
