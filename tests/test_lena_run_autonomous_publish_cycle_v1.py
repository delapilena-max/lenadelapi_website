"""Focused offline tests for the unattended publish-cycle orchestrator.

The wrapper sequences three already-independently-tested steps (packet
bridge, queue builder, scheduled-autonomous publisher). These tests prove
the ORCHESTRATION contract specifically: a failure at any stage aborts the
cycle rather than proceeding into a stale/absent queue, and dry-run never
reaches a real publish call. Fully offline -- no subprocess actually calls
Instagram/Facebook; dry_run=True is asserted to make zero real calls, same
guarantee tests/test_lena_autopublish_approved_queue_v2_8.py already proves
for run_scheduled_autonomous itself.
"""
from __future__ import annotations

import json

import pytest

import tools.lena_run_autonomous_publish_cycle_v1 as cycle
import tools.lena_build_publish_packet_v1 as packet_bridge
import tools.lena_autopublish_approved_queue_v2_8 as autopublish

DATE = "2026-07-24"
SLOT_KEYWORD = "morning"


def test_bridge_failure_aborts_before_touching_the_queue_or_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_date):
        raise RuntimeError("bridge exploded")

    monkeypatch.setattr(packet_bridge, "build_publish_packets", boom)
    subprocess_calls = []
    monkeypatch.setattr(
        cycle.subprocess, "run", lambda *a, **k: subprocess_calls.append((a, k)) or (_ for _ in ()).throw(AssertionError("must not be called"))
    )
    publish_calls = []
    monkeypatch.setattr(
        autopublish,
        "run_scheduled_autonomous",
        lambda **kwargs: publish_calls.append(kwargs) or {"ok": True},
    )

    report = cycle.run_publish_cycle(day=DATE, slot_keyword=SLOT_KEYWORD, dry_run=True)

    assert report["ok"] is False
    assert report["failed_stage"] == "build_publish_packets"
    assert subprocess_calls == []
    assert publish_calls == []


def test_queue_builder_failure_aborts_before_publishing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        packet_bridge, "build_publish_packets", lambda _date: {"ok": True, "added_count": 1}
    )

    class FakeCompleted:
        returncode = 1
        stdout = json.dumps({"ok": False, "error": "queue_builder_exploded"})
        stderr = ""

    monkeypatch.setattr(cycle.subprocess, "run", lambda *a, **k: FakeCompleted())
    publish_calls = []
    monkeypatch.setattr(
        autopublish,
        "run_scheduled_autonomous",
        lambda **kwargs: publish_calls.append(kwargs) or {"ok": True},
    )

    report = cycle.run_publish_cycle(day=DATE, slot_keyword=SLOT_KEYWORD, dry_run=True)

    assert report["ok"] is False
    assert report["failed_stage"] == "build_approved_publish_queue"
    assert publish_calls == []


def test_queue_builder_invoked_with_the_approved_platform_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        packet_bridge, "build_publish_packets", lambda _date: {"ok": True, "added_count": 1}
    )

    captured = {}

    class FakeCompleted:
        returncode = 0
        stdout = json.dumps({"ok": True, "queue_count": 1})
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return FakeCompleted()

    monkeypatch.setattr(cycle.subprocess, "run", fake_run)
    monkeypatch.setattr(
        autopublish,
        "run_scheduled_autonomous",
        lambda **kwargs: {"ok": True, "kwargs": kwargs},
    )

    report = cycle.run_publish_cycle(day=DATE, slot_keyword=SLOT_KEYWORD, dry_run=True)

    assert report["ok"] is True
    argv = captured["argv"]
    assert "--date" in argv and DATE in argv
    assert "--platforms" in argv
    platforms_value = argv[argv.index("--platforms") + 1]
    assert platforms_value == "Instagram Feed"


def test_successful_dry_run_reaches_publish_stage_with_dry_run_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        packet_bridge, "build_publish_packets", lambda _date: {"ok": True, "added_count": 1}
    )

    class FakeCompleted:
        returncode = 0
        stdout = json.dumps({"ok": True, "queue_count": 1})
        stderr = ""

    monkeypatch.setattr(cycle.subprocess, "run", lambda *a, **k: FakeCompleted())

    captured_kwargs = {}

    def fake_scheduled(**kwargs):
        captured_kwargs.update(kwargs)
        return {"ok": True, "posted": False, "dry_run": True}

    monkeypatch.setattr(autopublish, "run_scheduled_autonomous", fake_scheduled)

    report = cycle.run_publish_cycle(day=DATE, slot_keyword=SLOT_KEYWORD, dry_run=True)

    assert report["ok"] is True
    assert captured_kwargs["day"] == DATE
    assert captured_kwargs["slot_keyword"] == SLOT_KEYWORD
    assert captured_kwargs["limit"] == 1
    assert captured_kwargs["dry_run"] is True


def test_publish_stage_failure_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        packet_bridge, "build_publish_packets", lambda _date: {"ok": True, "added_count": 1}
    )

    class FakeCompleted:
        returncode = 0
        stdout = json.dumps({"ok": True, "queue_count": 1})
        stderr = ""

    monkeypatch.setattr(cycle.subprocess, "run", lambda *a, **k: FakeCompleted())

    def fake_scheduled(**_kwargs):
        raise autopublish.AutopublishError("approved_queue_missing", "no rows")

    monkeypatch.setattr(autopublish, "run_scheduled_autonomous", fake_scheduled)

    report = cycle.run_publish_cycle(day=DATE, slot_keyword=SLOT_KEYWORD, dry_run=False)

    assert report["ok"] is False
    assert report["failed_stage"] == "run_scheduled_autonomous"
    assert report["error_code"] == "approved_queue_missing"
