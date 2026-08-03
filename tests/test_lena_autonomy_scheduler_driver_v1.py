from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

import tools.lena_autonomy_runtime_evidence_v1 as runtime_evidence
import tools.lena_autonomy_daily_schedule_v1 as schedule_mod
import tools.lena_autonomy_scheduler_driver_v1 as driver


DATE = "2026-07-24"


def test_scheduler_driver_uses_shared_governed_runtime_root() -> None:
    assert driver.STATE_ROOT == driver.ROOT / Path(runtime_evidence.SCHEDULER_DRIVER_RUNTIME_ROOT.as_posix())


def _roots(tmp_path: Path) -> dict[str, object]:
    return {
        "schedule_root": tmp_path / "schedule",
        "state_root": tmp_path / "state",
        "receipt_root": tmp_path / "state",
        "validate_publish_readiness": _ready_stub(),
    }


def _ready_stub(*, ok: bool = True, reason: str = "ready"):
    def validate_publish_readiness(*, root, platform, media_type):
        return {
            "ok": ok,
            "reason": reason,
            "platform": platform,
            "media_type": media_type,
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "instagram_container_created": False,
        }

    return validate_publish_readiness


def _held_cycle_stub(calls: list[str]):
    def run_cycle(*, day, schedule_slot, policy_path, hold_for_publish):
        calls.append(schedule_slot)
        assert hold_for_publish is True
        return {"ok": True, "autonomous_disposition": "accept_and_hold_for_publish", "publish_performed": False}

    return run_cycle


def _failing_cycle_stub(calls: list[str]):
    def run_cycle(*, day, schedule_slot, policy_path, hold_for_publish):
        calls.append(schedule_slot)
        return {"ok": False, "autonomous_disposition": "operational_failure", "publish_performed": False}

    return run_cycle


def _publish_stub(calls: list[str], *, posted: bool = True):
    def run_publish(*, day, slot_keyword, limit, dry_run):
        calls.append(slot_keyword)
        return {"ok": True, "posted_count": 1 if posted else 0, "publish_calls_performed": 1 if posted else 0}

    return run_publish


def test_same_slot_cannot_generate_twice(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    inside_window = schedule_mod.generation_at(schedule, "morning") + timedelta(minutes=1)

    for _ in range(3):
        driver.run_once(
            now=inside_window,
            date_str=DATE,
            policy_path=tmp_path / "policy.json",
            run_cycle=_held_cycle_stub(generation_calls),
            run_publish=_publish_stub([]),
            **_roots(tmp_path),
        )

    assert generation_calls.count("morning") == 1


def test_same_slot_cannot_publish_twice(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    publish_calls: list[str] = []
    inside_window = schedule_mod.generation_at(schedule, "morning") + timedelta(minutes=1)
    at_publish = schedule_mod.publish_at(schedule, "morning") + timedelta(minutes=1)

    driver.run_once(
        now=inside_window, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
    )
    for _ in range(3):
        driver.run_once(
            now=at_publish, date_str=DATE, policy_path=tmp_path / "policy.json",
            run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
        )

    assert publish_calls.count("morning") == 1


def test_repeated_polling_across_the_full_window_is_idempotent(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    publish_calls: list[str] = []
    generation_at = schedule_mod.generation_at(schedule, "morning")
    publish_at = schedule_mod.publish_at(schedule, "morning")

    # Simulate a real per-minute poll from well before the generation
    # window through well after publish -- every single minute, not just
    # the two moments that matter.
    minute = generation_at - timedelta(minutes=5)
    end = publish_at + timedelta(minutes=5)
    poll_count = 0
    while minute <= end:
        driver.run_once(
            now=minute, date_str=DATE, policy_path=tmp_path / "policy.json",
            run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
        )
        minute += timedelta(minutes=1)
        poll_count += 1

    assert poll_count > 50
    assert generation_calls.count("morning") == 1
    assert publish_calls.count("morning") == 1


def test_completed_early_item_waits_until_its_publish_time(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    publish_calls: list[str] = []
    inside_window = schedule_mod.generation_at(schedule, "morning") + timedelta(minutes=1)

    result = driver.run_once(
        now=inside_window, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
    )

    assert generation_calls == ["morning"]
    assert publish_calls == []
    morning_result = next(r for r in result["results"] if r["slot"] == "morning")
    assert morning_result["action"] == "generated_and_queued"
    state_path = driver._state_path(DATE, "morning", tmp_path / "state")
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "queued_awaiting_publish"


def test_failed_generation_records_a_skip_instead_of_a_late_publish(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    publish_calls: list[str] = []
    inside_window = schedule_mod.generation_at(schedule, "morning") + timedelta(minutes=1)
    after_publish = schedule_mod.publish_at(schedule, "morning") + timedelta(minutes=1)

    driver.run_once(
        now=inside_window, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_failing_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
    )
    state_path = driver._state_path(DATE, "morning", tmp_path / "state")
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "generation_failed"

    result = driver.run_once(
        now=after_publish, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_failing_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
    )

    assert publish_calls == []  # never published a nonexistent item
    morning_result = next(r for r in result["results"] if r["slot"] == "morning")
    assert morning_result["action"] == "skipped"
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "skipped"


def test_missing_instagram_login_token_blocks_before_generation(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    inside_window = schedule_mod.generation_at(schedule, "morning") + timedelta(minutes=1)

    result = driver.run_once(
        now=inside_window,
        date_str=DATE,
        policy_path=tmp_path / "policy.json",
        run_cycle=_held_cycle_stub(generation_calls),
        run_publish=_publish_stub([]),
        validate_publish_readiness=_ready_stub(ok=False, reason="instagram_login_access_token_missing"),
        schedule_root=tmp_path / "schedule",
        state_root=tmp_path / "state",
        receipt_root=tmp_path / "state",
    )

    assert generation_calls == []
    morning = next(r for r in result["results"] if r["slot"] == "morning")
    assert morning == {"slot": "morning", "action": "generation_blocked", "reason": "instagram_login_access_token_missing"}
    state = json.loads(driver._state_path(DATE, "morning", tmp_path / "state").read_text(encoding="utf-8"))
    assert state["status"] == "generation_blocked"
    assert state["provider_calls_performed"] == 0
    assert state["container_creation_performed"] == 0
    receipt = next((tmp_path / "state" / DATE).glob("morning_generation_blocked_*.json"))
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["provider_calls_performed"] == 0
    assert payload["queue_creation_performed"] == 0
    assert payload["container_creation_performed"] == 0
    assert payload["publish_calls_performed"] == 0


def test_invalid_instagram_login_token_blocks_queued_publish_without_retry_loop(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    publish_calls: list[str] = []
    state_path = driver._state_path(DATE, "morning", tmp_path / "state")
    driver._write_state_atomic(state_path, {"status": "queued_awaiting_publish"})
    at_publish = schedule_mod.publish_at(schedule, "morning") + timedelta(minutes=1)

    def fail_if_generation_runs(**kwargs):
        raise AssertionError("generation must not run during publish recovery")

    for _ in range(2):
        result = driver.run_once(
            now=at_publish,
            date_str=DATE,
            policy_path=tmp_path / "policy.json",
            run_cycle=fail_if_generation_runs,
            run_publish=_publish_stub(publish_calls, posted=False),
            validate_publish_readiness=_ready_stub(ok=False, reason="instagram_token_invalid"),
            schedule_root=tmp_path / "schedule",
            state_root=tmp_path / "state",
            receipt_root=tmp_path / "state",
        )

    assert publish_calls == []
    morning = next(r for r in result["results"] if r["slot"] == "morning")
    assert morning == {"slot": "morning", "action": "noop", "status": "publish_blocked"}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "publish_blocked"
    receipts = list((tmp_path / "state" / DATE).glob("morning_publish_blocked_*.json"))
    assert len(receipts) == 1


def test_missed_generation_window_records_a_skip_without_publishing_late(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    publish_calls: list[str] = []
    # Driver was never invoked at all until well after publish time --
    # generation must never fire this late, and nothing should publish.
    after_publish = schedule_mod.publish_at(schedule, "morning") + timedelta(minutes=30)

    result = driver.run_once(
        now=after_publish, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **_roots(tmp_path),
    )

    assert generation_calls == []
    assert publish_calls == []
    morning_result = next(r for r in result["results"] if r["slot"] == "morning")
    assert morning_result["action"] == "skipped"
    assert morning_result["reason"] == "generation_never_started"


def test_full_offline_path_schedule_to_receipt(tmp_path: Path) -> None:
    schedule = schedule_mod.compute_daily_schedule(DATE)
    generation_calls: list[str] = []
    publish_calls: list[str] = []
    inside_window = schedule_mod.generation_at(schedule, "morning") + timedelta(minutes=1)
    at_publish = schedule_mod.publish_at(schedule, "morning") + timedelta(minutes=1)
    roots = _roots(tmp_path)

    inspect = driver.run_once(now=inside_window, date_str=DATE, inspect_only=True, **roots)
    assert inspect["mode"] == "inspect_only"
    assert set(inspect["schedule"]["slots"]) == {"morning", "afternoon", "evening"}

    generated = driver.run_once(
        now=inside_window, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **roots,
    )
    morning_gen = next(r for r in generated["results"] if r["slot"] == "morning")
    assert morning_gen["action"] == "generated_and_queued"
    generation_receipts = list((roots["receipt_root"] / DATE).glob("morning_generation_*.json"))
    assert len(generation_receipts) == 1

    published = driver.run_once(
        now=at_publish, date_str=DATE, policy_path=tmp_path / "policy.json",
        run_cycle=_held_cycle_stub(generation_calls), run_publish=_publish_stub(publish_calls), **roots,
    )
    morning_pub = next(r for r in published["results"] if r["slot"] == "morning")
    assert morning_pub["action"] == "published"
    publish_receipts = list((roots["receipt_root"] / DATE).glob("morning_publish_*.json"))
    assert len(publish_receipts) == 1

    assert generation_calls == ["morning"]
    assert publish_calls == ["morning"]


def test_historical_wrapper_bootstrap_repo_root_argument_failed_driver_parse() -> None:
    original_argv = sys.argv[:]
    try:
        sys.argv = ["-", r"C:\projects\ai\content_bot_photo_production_main_v1"]
        with pytest.raises(SystemExit) as excinfo:
            driver.main()
    finally:
        sys.argv = original_argv

    assert excinfo.value.code == 2
