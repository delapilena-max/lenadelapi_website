from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import tools.lena_observe_autonomous_photo_cycle_v1 as observer
from tools import lena_autonomy_daily_schedule_v1 as schedule_mod


DATE = "2026-08-01"
SLOT = "morning"
SLOT_ID = "lenagate20260801proof-pack000-00-photo"
QUEUE_ID = "q_proof0001"
POST_URL = "https://www.instagram.com/p/PROOF123/"
POST_ID = "18025763933677164"
SOURCE_SHA = "a" * 64
CLEAN_SHA = "b" * 64
PROMPT_SHA = "c" * 64
APPROVAL_SHA = "e" * 64
EXEC_SHA = "f" * 64
MANIFEST_SHA = "1" * 64
QA_SHA = "2" * 64
CANDIDATE_SHA = "3" * 64


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _schedule() -> dict[str, Any]:
    return schedule_mod.compute_daily_schedule(DATE)


def _times() -> dict[str, datetime]:
    schedule = _schedule()
    generation_at = schedule_mod.generation_at(schedule, SLOT)
    publish_at = schedule_mod.publish_at(schedule, SLOT)
    return {
        "generation_at": generation_at,
        "publish_at": publish_at,
    }


def _task_probe(*, enabled: bool = True, state: str = "Ready", next_run_time: str | None = None) -> dict[str, Any]:
    return {
        "present": True,
        "enabled": enabled,
        "state": state,
        "last_task_result": 0,
        "last_run_time": None,
        "next_run_time": next_run_time,
        "actions": [
            {
                "execute": "powershell.exe",
                "arguments": "-File tools/lena_autonomy_scheduler_driver_run_v1.ps1",
                "working_directory": "C:\\deploy",
            }
        ],
    }


def _run_events(*, when: datetime, automatic: bool = True, result_code: int = 0, count: int = 1) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    record_id = 100
    for index in range(count):
        base = when + timedelta(minutes=index)
        instance = f"instance-{index}"
        if automatic:
            events.append({"event_id": 107, "record_id": record_id, "time_created": base.isoformat(), "task_name": observer.CANONICAL_TASK_NAME, "instance_id": instance, "action_name": "", "result_code": None})
            record_id += 1
        events.append({"event_id": 100, "record_id": record_id, "time_created": (base + timedelta(seconds=1)).isoformat(), "task_name": observer.CANONICAL_TASK_NAME, "instance_id": instance, "action_name": "", "result_code": None})
        record_id += 1
        events.append({"event_id": 200, "record_id": record_id, "time_created": (base + timedelta(seconds=2)).isoformat(), "task_name": observer.CANONICAL_TASK_NAME, "instance_id": instance, "action_name": "powershell.exe", "result_code": None})
        record_id += 1
        events.append({"event_id": 201, "record_id": record_id, "time_created": (base + timedelta(seconds=3)).isoformat(), "task_name": observer.CANONICAL_TASK_NAME, "instance_id": instance, "action_name": "powershell.exe", "result_code": result_code})
        record_id += 1
        events.append({"event_id": 102, "record_id": record_id, "time_created": (base + timedelta(seconds=4)).isoformat(), "task_name": observer.CANONICAL_TASK_NAME, "instance_id": instance, "action_name": "", "result_code": None})
        record_id += 1
    return events


def _event_probe(events: list[dict[str, Any]]):
    def probe(task_name: str, max_events: int) -> list[dict[str, Any]]:
        assert task_name == observer.CANONICAL_TASK_NAME
        return events[:max_events]

    return probe


def _queue_fieldnames() -> list[str]:
    return [
        "queue_id", "date", "created_at", "slot_id", "schedule_slot", "platform", "media_type", "lane", "asset_status", "asset_path", "asset_sha256",
        "growth_bucket", "hook_category", "audio_name", "caption", "short_caption", "pinned_comment", "story_prompt", "story_poll", "post_poll",
        "keyword_notes", "public_text_score", "public_text_decision", "publish_state", "publish_mode", "connector_path", "post_url", "posted_at",
        "failure_reason", "attempt_count", "notes", "candidate_artifact_sha256", "prompt_sha256", "packet_sha256", "handoff_sha256", "approval_sha256",
        "execution_receipt_sha256", "manifest_sha256", "qa_sha256", "clean_export_report_path", "clean_export_report_sha256",
    ]


def _write_queue_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_queue_fieldnames())
        writer.writeheader()
        writer.writerows(rows)


def _base_authorization(*, handoff_sha: str) -> dict[str, Any]:
    return {
        "report_type": "lena_standing_autonomy_cycle_authorization",
        "schema_version": "v1",
        "authorization_mode": "standing_autonomy_policy",
        "date": DATE,
        "slot_id": SLOT_ID,
        "schedule_slot": SLOT,
        "candidate_artifact_path": f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/candidate.json",
        "candidate_artifact_sha256": CANDIDATE_SHA,
        "prompt_sha256": PROMPT_SHA,
        "generation_handoff_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
        "generation_handoff_artifact_sha256": handoff_sha,
        "custom_reference_id": observer.SOUL_ID,
        "controlled_photo_autonomy": {
            "enabled": True,
            "qa_mode": "autonomous_local",
            "external_visual_diagnostic": {
                "enabled": False,
                "provider": "anthropic",
            },
        },
        "allowed_media_types": ["photo"],
    }


def _base_execution_receipt(*, handoff_sha: str) -> dict[str, Any]:
    return {
        "report_type": "lena_higgsfield_standing_autonomy_generation_execution_receipt",
        "receipt_written_at_utc": "2026-08-01T14:10:00Z",
        "slot_id": SLOT_ID,
        "date": DATE,
        "custom_reference_id": observer.SOUL_ID,
        "outcome": "success",
        "generated_image_sha256": SOURCE_SHA,
        "handoff_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
        "handoff_artifact_sha256": handoff_sha,
        "operator_id": "lena_autonomy_controller",
    }


def _base_manifest() -> dict[str, Any]:
    return {
        "provider": "higgsfield",
        "job_type": "text2image_soul_v2",
        "date": DATE,
        "slot_id": SLOT_ID,
        "timestamp_utc": "2026-08-01T14:10:00Z",
        "custom_reference_id": observer.SOUL_ID,
        "soul_id": observer.SOUL_ID,
        "live_attempt_count": 1,
        "retry_count": 0,
        "provider_job_id": "job-001",
        "provider_status": "completed",
        "saved_image_sha256": SOURCE_SHA,
        "submitted_prompt_sha256": PROMPT_SHA,
    }


def _base_identity() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "verified_at_utc": "2026-08-01T14:10:01Z",
        "date": DATE,
        "slot_id": SLOT_ID,
        "custom_reference_id": observer.SOUL_ID,
        "soul_id": observer.SOUL_ID,
        "verification_result": "pass",
        "local_image_sha256": SOURCE_SHA,
    }


def _base_qa(*, disposition: str = "accept", provider_called: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "lena_photo_qa_disposition_v1",
        "generated_at_utc": "2026-08-01T14:10:02Z",
        "slot_id": SLOT_ID,
        "disposition": disposition,
        "qa_inputs": {
            "qa_mode": "autonomous_local",
        },
        "visual_judgment_source": {
            "provider_called": provider_called,
        },
        "provider_called": provider_called,
    }


def _base_packet(clean_report_path: str, *, handoff_sha: str) -> dict[str, Any]:
    return {
        "slot_id": SLOT_ID,
        "platform": "Instagram Feed",
        "media_type": "photo",
        "asset_path": "C:/temp/clean.png",
        "asset_sha256": CLEAN_SHA,
        "source_asset_path": "C:/temp/source.png",
        "source_asset_sha256": SOURCE_SHA,
        "caption": "The mirror said keep it.",
        "handoff_sha256": handoff_sha,
        "approval_sha256": APPROVAL_SHA,
        "execution_receipt_sha256": EXEC_SHA,
        "manifest_sha256": MANIFEST_SHA,
        "qa_sha256": QA_SHA,
        "clean_export_report_path": clean_report_path,
        "clean_export_report_sha256": "4" * 64,
    }


def _base_clean() -> dict[str, Any]:
    return {
        "schema_version": "lena_privacy_clean_photo_v1",
        "created_at_utc": "2026-08-01T14:10:03Z",
        "source_sha256": SOURCE_SHA,
        "output_sha256": CLEAN_SHA,
        "verified_clean": True,
    }


def _base_queue_row(clean_report_path: str, *, handoff_sha: str, notes: str = "", publish_state: str = "posted") -> dict[str, str]:
    return {
        "queue_id": QUEUE_ID,
        "date": DATE,
        "created_at": "2026-08-01T14:10:04Z",
        "slot_id": SLOT_ID,
        "schedule_slot": SLOT,
        "platform": "Instagram Feed",
        "media_type": "photo",
        "lane": "mirror outfit check",
        "asset_status": "approved",
        "asset_path": "C:/temp/clean.png",
        "asset_sha256": CLEAN_SHA,
        "growth_bucket": "controlled_photo_autonomy",
        "hook_category": "",
        "audio_name": "",
        "caption": "The mirror said keep it.",
        "short_caption": "The mirror said keep it.",
        "pinned_comment": "",
        "story_prompt": "",
        "story_poll": "",
        "post_poll": "",
        "keyword_notes": "",
        "public_text_score": "100",
        "public_text_decision": "APPROVED",
        "publish_state": publish_state,
        "publish_mode": "explicit_live_connector_required",
        "connector_path": "tools/publishers/lena_publish_instagram_feed_v2_8.py",
        "post_url": POST_URL if publish_state == "posted" else "",
        "posted_at": "2026-08-01T09:34:00-05:00" if publish_state == "posted" else "",
        "failure_reason": "",
        "attempt_count": "0",
        "notes": notes,
        "candidate_artifact_sha256": CANDIDATE_SHA,
        "prompt_sha256": PROMPT_SHA,
        "packet_sha256": "5" * 64,
        "handoff_sha256": handoff_sha,
        "approval_sha256": APPROVAL_SHA,
        "execution_receipt_sha256": EXEC_SHA,
        "manifest_sha256": MANIFEST_SHA,
        "qa_sha256": QA_SHA,
        "clean_export_report_path": clean_report_path,
        "clean_export_report_sha256": "4" * 64,
    }


def _base_receipt(*, verification_ok: bool = True, reconciled: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "report_type": "lena_approved_queue_publish_receipt",
        "schema_version": "v1",
        "date": DATE,
        "slot_id": SLOT_ID,
        "queue_id": QUEUE_ID,
        "platform": "Instagram Feed",
        "media_type": "photo",
        "captured_at_utc": "2026-08-01T14:10:05Z",
        "posted": True,
        "post_id": POST_ID,
        "post_url": POST_URL,
        "provider_result": {
            "ok": True,
            "posted": True,
            "post_id": POST_ID,
            "post_url": POST_URL,
            "extra": {
                "media": {
                    "pre_container_media_verification": {
                        "ok": verification_ok,
                        "sha256": CLEAN_SHA,
                    }
                }
            },
        },
    }
    if reconciled:
        payload["reconciled_from_dispatch_report"] = True
    return payload


def _base_dispatch_report() -> dict[str, Any]:
    return {
        "ok": True,
        "results": [
            {
                "queue_id": QUEUE_ID,
                "slot_id": SLOT_ID,
                "result": {
                    "posted": True,
                    "post_id": POST_ID,
                    "post_url": POST_URL,
                },
            }
        ],
    }


def _write_success_fixture(root: Path) -> None:
    clean_path = root / "temp" / "clean_provenance.json"
    handoff_path = root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_next_live_image_handoff_{DATE}.json"
    _write_json(handoff_path, {"slot_id": SLOT_ID, "prompt_sha256": PROMPT_SHA})
    handoff_sha = observer._sha256_file(handoff_path)
    _write_json(root / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / DATE / f"lena_bounded_live_cycle_authorization_{DATE}_{SLOT_ID}.json", _base_authorization(handoff_sha=handoff_sha))
    _write_json(root / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_standing_autonomy_generation_approval.json", {"report_type": "lena_higgsfield_standing_autonomy_generation_approval"})
    _write_json(root / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_execution_receipt.json", _base_execution_receipt(handoff_sha=handoff_sha))
    _write_json(root / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json", _base_manifest())
    _write_json(root / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "identity_verification.json", _base_identity())
    _write_json(root / "pipeline" / "asset_review" / "lena" / DATE / f"{SLOT_ID}__{SOURCE_SHA}_qa_disposition.json", _base_qa())
    _write_json(clean_path, _base_clean())
    _write_json(root / "pipeline" / "publish_packets" / "lena" / DATE / "lena_publish_packets_v2_4.json", {"date": DATE, "packets": [_base_packet(str(clean_path), handoff_sha=handoff_sha)]})
    _write_queue_csv(
        root / "pipeline" / "publishing" / "lena" / "approved_queue" / DATE / "lena_approved_publish_queue_v2_8.csv",
        [_base_queue_row(str(clean_path), handoff_sha=handoff_sha)],
    )
    _write_json(
        root / "pipeline" / "publishing" / "lena" / "approved_queue_receipts" / DATE / SLOT_ID / f"{QUEUE_ID}_Instagram_Feed_publish_receipt.json",
        _base_receipt(),
    )
    _write_json(
        root / "pipeline" / "publishing" / "lena" / "dispatch_reports" / DATE / "approved_queue_autopublish_report_141005.json",
        _base_dispatch_report(),
    )
    _write_json(
        root / "pipeline" / "autonomy" / "lena" / "scheduler_driver" / DATE / f"{SLOT}_state.json",
        {"status": "published"},
    )


def _snapshot(root: Path, *, now: datetime, enabled: bool = True, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return observer.build_snapshot(
        deployment_root=root,
        now=now,
        task_probe=lambda task_name: _task_probe(enabled=enabled),
        event_probe=_event_probe(events or []),
    )


def test_healthy_no_slot_due_polling(tmp_path: Path) -> None:
    generation_at = _times()["generation_at"]
    now = generation_at - timedelta(minutes=5)

    snapshot = _snapshot(tmp_path, now=now, events=_run_events(when=now - timedelta(minutes=3), count=3))

    assert snapshot["slot_currently_due"] is False
    assert snapshot["current_cycle"]["classification"] == "not_due_yet"


def test_three_successful_automatic_poll_events_are_summarized(tmp_path: Path) -> None:
    generation_at = _times()["generation_at"]
    now = generation_at - timedelta(minutes=5)

    snapshot = _snapshot(tmp_path, now=now, events=_run_events(when=now - timedelta(minutes=3), count=3))

    assert snapshot["scheduler"]["recent_run_count"] == 3
    assert snapshot["scheduler"]["latest_completed_run"]["automatic_time_trigger"] is True
    assert snapshot["scheduler"]["latest_completed_run"]["result_code"] == 0


def test_complete_unattended_cycle_classifies_success(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    publish_at = _times()["publish_at"]
    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "autonomous_cycle_completed"
    assert snapshot["current_cycle"]["issues"] == []


def test_scheduler_disabled_returns_terminal_watch_result(tmp_path: Path) -> None:
    generation_at = _times()["generation_at"]
    result = observer.watch_next_due_slot(
        deployment_root=tmp_path,
        timeout_seconds=1,
        poll_seconds=1,
        now=generation_at - timedelta(minutes=5),
        task_probe=lambda task_name: _task_probe(enabled=False),
        event_probe=_event_probe([]),
    )

    assert result["terminal_result"] == "scheduler_disabled"


def test_scheduler_nonzero_completion_fails_closed(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    publish_at = _times()["publish_at"]
    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"], result_code=1))

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "scheduler_nonzero_result" for item in snapshot["current_cycle"]["issues"])


def test_generation_failure_is_reported_from_scheduler_receipt(tmp_path: Path) -> None:
    publish_at = _times()["publish_at"]
    _write_json(
        tmp_path / "pipeline" / "autonomy" / "lena" / "scheduler_driver" / DATE / f"{SLOT}_state.json",
        {"status": "generation_failed"},
    )
    _write_json(
        tmp_path / "pipeline" / "autonomy" / "lena" / "scheduler_driver" / DATE / f"{SLOT}_generation_failure_093000_000001.json",
        {
            "report_type": "lena_autonomy_scheduler_receipt",
            "receipt_kind": "generation_failure",
            "recorded_at": "2026-08-01T09:30:00-05:00",
            "result": {
                "failure": {
                    "code": "clean_export_verification_failed",
                    "detail": "privacy-clean derivative still contains disallowed metadata",
                }
            },
        },
    )

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "clean_export_verification_failed" for item in snapshot["current_cycle"]["issues"])


def test_qa_rejection_blocks_completion(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    qa_path = tmp_path / "pipeline" / "asset_review" / "lena" / DATE / f"{SLOT_ID}__{SOURCE_SHA}_qa_disposition.json"
    _write_json(qa_path, _base_qa(disposition="reject"))
    publish_at = _times()["publish_at"]

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "qa_rejected" for item in snapshot["current_cycle"]["issues"])


def test_host_verification_failure_blocks_completion(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    receipt_path = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts" / DATE / SLOT_ID / f"{QUEUE_ID}_Instagram_Feed_publish_receipt.json"
    _write_json(receipt_path, _base_receipt(verification_ok=False))
    publish_at = _times()["publish_at"]

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "host_verification_failed" for item in snapshot["current_cycle"]["issues"])


def test_successful_publish_missing_automatic_receipt_fails_closed(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    receipt_path = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts" / DATE / SLOT_ID / f"{QUEUE_ID}_Instagram_Feed_publish_receipt.json"
    receipt_path.unlink()
    publish_at = _times()["publish_at"]

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "automatic_receipt_missing" for item in snapshot["current_cycle"]["issues"])


def test_duplicate_queue_row_is_evidence_inconsistent(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    queue_path = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue" / DATE / "lena_approved_publish_queue_v2_8.csv"
    clean_path = str(tmp_path / "temp" / "clean_provenance.json")
    handoff_sha = observer._sha256_file(tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_next_live_image_handoff_{DATE}.json")
    _write_queue_csv(queue_path, [_base_queue_row(clean_path, handoff_sha=handoff_sha), _base_queue_row(clean_path, handoff_sha=handoff_sha)])
    publish_at = _times()["publish_at"]

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "evidence_inconsistent"
    assert any(item["code"] == "duplicate_queue_rows" for item in snapshot["current_cycle"]["issues"])


def test_conflicting_shas_are_evidence_inconsistent(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    clean_path = tmp_path / "temp" / "clean_provenance.json"
    _write_json(
        clean_path,
        {
            **_base_clean(),
            "output_sha256": "9" * 64,
        },
    )
    publish_at = _times()["publish_at"]

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "evidence_inconsistent"
    assert any(item["code"] == "output_sha_mismatch" for item in snapshot["current_cycle"]["issues"])


def test_manual_start_evidence_is_rejected_as_unattended_proof(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    publish_at = _times()["publish_at"]
    manual_only_events = _run_events(when=_times()["generation_at"], automatic=False)

    snapshot = _snapshot(tmp_path, now=publish_at, events=manual_only_events)

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "manual_start_or_missing_time_trigger" for item in snapshot["current_cycle"]["issues"])


def test_manual_generation_approval_does_not_count_as_unattended(tmp_path: Path) -> None:
    _write_success_fixture(tmp_path)
    _write_json(
        tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_approval.json",
        {"report_type": "lena_higgsfield_generation_approval", "operator_id": "nicolas"},
    )
    publish_at = _times()["publish_at"]

    snapshot = _snapshot(tmp_path, now=publish_at, events=_run_events(when=_times()["generation_at"]))

    assert snapshot["current_cycle"]["classification"] == "cycle_failed"
    assert any(item["code"] == "manual_generation_approval_present" for item in snapshot["current_cycle"]["issues"])


def test_observer_contract_exposes_no_mutation_or_network_capability(tmp_path: Path) -> None:
    generation_at = _times()["generation_at"]
    snapshot = _snapshot(tmp_path, now=generation_at - timedelta(minutes=5), events=[])

    assert snapshot["observer_contract"] == {
        "read_only": True,
        "network_calls_permitted": False,
        "mutation_permitted": False,
        "provider_calls_permitted": False,
        "publish_calls_permitted": False,
        "queue_mutations_permitted": False,
    }
