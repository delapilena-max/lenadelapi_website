from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

import tools.lena_autonomy_daily_schedule_v1 as schedule_mod


def test_same_date_always_produces_the_same_three_times() -> None:
    first = schedule_mod.compute_daily_schedule("2026-07-24")
    second = schedule_mod.compute_daily_schedule("2026-07-24")
    assert first == second
    assert first["fingerprint_sha256"] == second["fingerprint_sha256"]


def test_different_dates_vary_within_the_ten_minute_window() -> None:
    seen_offsets = set()
    for day in range(1, 32):
        schedule = schedule_mod.compute_daily_schedule(f"2026-07-{day:02d}")
        for slot in schedule_mod.SLOT_ORDER:
            offset = schedule["slots"][slot]["offset_minutes"]
            assert -10 <= offset <= 10
            seen_offsets.add(offset)
    # Across 31 distinct dates the deterministic hash should not collapse
    # to a single constant offset -- proves real variation, not a no-op.
    assert len(seen_offsets) > 1


def test_generation_time_is_exactly_forty_five_minutes_before_publish_time() -> None:
    schedule = schedule_mod.compute_daily_schedule("2026-07-24")
    for slot in schedule_mod.SLOT_ORDER:
        publish = schedule_mod.publish_at(schedule, slot)
        generation = schedule_mod.generation_at(schedule, slot)
        assert publish - generation == timedelta(minutes=45)


def test_times_use_america_chicago_across_dst_transitions() -> None:
    winter = schedule_mod.compute_daily_schedule("2026-01-15")  # CST, UTC-6
    summer = schedule_mod.compute_daily_schedule("2026-07-24")  # CDT, UTC-5
    winter_publish = schedule_mod.publish_at(winter, "morning")
    summer_publish = schedule_mod.publish_at(summer, "morning")
    assert winter_publish.utcoffset() == timedelta(hours=-6)
    assert summer_publish.utcoffset() == timedelta(hours=-5)
    assert winter["timezone"] == "America/Chicago"
    assert summer["timezone"] == "America/Chicago"


def test_slots_stay_ordered_and_non_overlapping() -> None:
    schedule = schedule_mod.compute_daily_schedule("2026-07-24")
    times = [schedule_mod.publish_at(schedule, slot) for slot in schedule_mod.SLOT_ORDER]
    assert times == sorted(times)
    assert len(set(times)) == 3


def test_load_or_create_daily_schedule_is_idempotent_on_disk(tmp_path: Path) -> None:
    root = tmp_path / "daily_schedule"
    first = schedule_mod.load_or_create_daily_schedule("2026-07-24", schedule_root=root)
    second = schedule_mod.load_or_create_daily_schedule("2026-07-24", schedule_root=root)
    assert first["fingerprint_sha256"] == second["fingerprint_sha256"]
    assert first["slots"] == second["slots"]
    written_files = list((root / "2026-07-24").glob("*.json"))
    assert len(written_files) == 1


def test_load_or_create_daily_schedule_rejects_tampered_artifact(tmp_path: Path) -> None:
    import json

    root = tmp_path / "daily_schedule"
    schedule_mod.load_or_create_daily_schedule("2026-07-24", schedule_root=root)
    path = schedule_mod.daily_schedule_path("2026-07-24", root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["slots"]["morning"]["offset_minutes"] = 9999
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(schedule_mod.DailyScheduleError) as exc:
        schedule_mod.load_or_create_daily_schedule("2026-07-24", schedule_root=root)
    assert exc.value.code == "schedule_artifact_fingerprint_mismatch"
