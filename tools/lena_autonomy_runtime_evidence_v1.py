from __future__ import annotations

import re
from datetime import date
from pathlib import PurePosixPath

AUTONOMY_RUNTIME_ROOT = PurePosixPath("pipeline/autonomy/lena")
DAILY_SCHEDULE_RUNTIME_ROOT = AUTONOMY_RUNTIME_ROOT / "daily_schedule"
SCHEDULER_DRIVER_RUNTIME_ROOT = AUTONOMY_RUNTIME_ROOT / "scheduler_driver"

SLOTS = frozenset({"morning", "afternoon", "evening"})
SCHEDULER_DRIVER_RECEIPT_KINDS = frozenset(
    {
        "generation",
        "generation_failure",
        "generation_blocked",
        "generation_success",
        "publish",
        "publish_blocked",
        "publish_failure",
        "poll",
        "poll_result",
        "skip",
    }
)

DATE_SEGMENT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLOT_RE = "|".join(sorted(SLOTS))
RECEIPT_KIND_RE = "|".join(sorted(re.escape(kind) for kind in SCHEDULER_DRIVER_RECEIPT_KINDS))
SCHEDULER_STATE_RE = re.compile(rf"^(?P<slot>{SLOT_RE})_state\.json$")
SCHEDULER_RECEIPT_RE = re.compile(
    rf"^(?P<slot>{SLOT_RE})_(?P<kind>{RECEIPT_KIND_RE})_(?P<stamp>\d{{6}}_\d{{6}})\.json$"
)


def _valid_date_segment(value: str) -> bool:
    if not DATE_SEGMENT_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def daily_schedule_runtime_match(parts: tuple[str, ...]) -> bool:
    if len(parts) != 2 or not _valid_date_segment(parts[0]):
        return False
    return parts[1] == f"lena_autonomy_daily_schedule_{parts[0]}.json"


def scheduler_driver_runtime_match(parts: tuple[str, ...]) -> bool:
    if len(parts) != 2 or not _valid_date_segment(parts[0]):
        return False
    filename = parts[1]
    if SCHEDULER_STATE_RE.fullmatch(filename):
        return True
    return bool(SCHEDULER_RECEIPT_RE.fullmatch(filename))


def autonomy_runtime_match(parts: tuple[str, ...]) -> bool:
    if len(parts) < 2:
        return False
    root, remaining = parts[0], parts[1:]
    if root == "daily_schedule":
        return daily_schedule_runtime_match(remaining)
    if root == "scheduler_driver":
        return scheduler_driver_runtime_match(remaining)
    return False
