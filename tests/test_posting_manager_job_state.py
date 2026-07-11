from __future__ import annotations

import json
from pathlib import Path

from pipeline.lena_job_state import create_snapshot, load_snapshot, save_snapshot
from pipeline.posting_manager import PostingManager
import pipeline.posting_manager as posting_manager_module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_manager(tmp_path: Path) -> PostingManager:
    root = tmp_path / "workspace"
    return PostingManager(
        config={
            "queue_dir": str(root / "queue"),
            "published_dir": str(root / "queue" / "published"),
            "failed_dir": str(root / "queue" / "failed"),
            "receipt_dir": str(root / "queue" / "receipts"),
            "feedback_file": str(root / "feedback" / "feedback.jsonl"),
            "publisher_backend": "local",
            "dry_run": False,
            "max_attempts": 1,
            "platforms": ["instagram"],
            "caption": {
                "default_hashtags": ["#Lena"],
                "fallback_templates": ["Fallback caption"],
            },
        }
    )


def _seed_queue_post(manager: PostingManager, post_id: str = "queued-job-1") -> Path:
    media_path = manager.queue_dir / f"{post_id}.png"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"fake-png-bytes")

    post_path = manager.queue_dir / f"{post_id}.json"
    _write_json(
        post_path,
        {
            "post_id": post_id,
            "media_path": str(media_path),
            "media_type": "photo",
            "caption": "A prepared caption",
            "platforms": ["instagram"],
            "metadata": {"caption_variant": "v1"},
        },
    )
    return post_path


def _patch_state_dir(monkeypatch, state_dir: Path) -> None:
    monkeypatch.setattr(
        posting_manager_module,
        "load_job_state_snapshot",
        lambda canonical_job_id: load_snapshot(canonical_job_id, state_dir=state_dir),
    )
    monkeypatch.setattr(
        posting_manager_module,
        "save_job_state_snapshot",
        lambda snapshot: save_snapshot(snapshot, state_dir=state_dir),
    )


def test_process_one_advances_existing_queued_snapshot_to_published_pending_learning(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager, post_id="queued-job-1")

    def _publish_with_platform_media_id(post, *, dry_run: bool):
        return {
            "ok": True,
            "result": {"instagram_result": {"instagram_media_id": "18000000000000000"}},
        }

    monkeypatch.setattr(manager, "publish", _publish_with_platform_media_id)

    queued_snapshot = create_snapshot(
        canonical_job_id="queued-job-1",
        output_slot_id="queued-job-1",
        current_state="queued",
        source_slot_id="source-slot-1",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    result = manager.process_one(post_path, dry_run=False)

    assert result["status"] == "success"
    assert result["job_state_result"]["status"] == "updated"

    updated = load_snapshot("queued-job-1", state_dir=state_dir)
    assert updated is not None
    assert updated["canonical_job_id"] == "queued-job-1"
    assert updated["output_slot_id"] == "queued-job-1"
    assert updated["source_slot_id"] == "source-slot-1"
    assert updated["previous_state"] == "queued"
    assert updated["current_state"] == "published_pending_learning"
    assert updated["platform_media_id"] == "18000000000000000"
    assert updated["artifact_paths"]["queue_item"].endswith("published\\queued-job-1.json")
    assert updated["artifact_paths"]["publish_receipt"].endswith("published\\queued-job-1.json.receipt.json")
    assert "publish_receipt" in updated["artifact_evidence"]


def test_process_one_does_not_write_state_transition_on_dry_run(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager, post_id="queued-job-dry-run")

    queued_snapshot = create_snapshot(
        canonical_job_id="queued-job-dry-run",
        output_slot_id="queued-job-dry-run",
        current_state="queued",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    result = manager.process_one(post_path, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["job_state_result"] is None

    unchanged = load_snapshot("queued-job-dry-run", state_dir=state_dir)
    assert unchanged is not None
    assert unchanged["current_state"] == "queued"
    assert unchanged["previous_state"] is None


def test_process_one_does_not_invent_missing_snapshot(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager, post_id="missing-snapshot-job")

    result = manager.process_one(post_path, dry_run=False)

    assert result["status"] == "success"
    assert result["job_state_result"]["status"] == "skipped"
    assert result["job_state_result"]["reason"] == "missing_snapshot"
    assert load_snapshot("missing-snapshot-job", state_dir=state_dir) is None


def test_repeat_publish_state_recording_fails_closed_after_first_transition(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)

    queued_snapshot = create_snapshot(
        canonical_job_id="repeat-job",
        output_slot_id="repeat-job",
        current_state="queued",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    post_path = _seed_queue_post(manager, post_id="repeat-job")
    first_result = manager.process_one(post_path, dry_run=False)
    assert first_result["job_state_result"]["status"] == "updated"

    published_post_path = manager.published_dir / "repeat-job.json"
    synthetic_publish_response = {
        "ok": True,
        "result": {"instagram_result": {"instagram_media_id": "18000000000000000"}},
    }
    second_result = manager._record_published_job_state_transition(
        manager.validate_post(published_post_path),
        published_post_path,
        synthetic_publish_response,
    )

    assert second_result["status"] == "skipped"
    assert second_result["reason"] == "unexpected_state"

    snapshot = load_snapshot("repeat-job", state_dir=state_dir)
    assert snapshot is not None
    assert snapshot["current_state"] == "published_pending_learning"


def test_publish_failure_does_not_advance_state_or_write_hard_stopped(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager, post_id="failed-publish-job")

    queued_snapshot = create_snapshot(
        canonical_job_id="failed-publish-job",
        output_slot_id="failed-publish-job",
        current_state="queued",
        source_slot_id="source-slot-2",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    def _failed_publish(post, *, dry_run: bool):
        return {"ok": False, "error": "synthetic publish failure"}

    monkeypatch.setattr(manager, "publish", _failed_publish)

    result = manager.process_one(post_path, dry_run=False)

    assert result["status"] == "failed"

    unchanged = load_snapshot("failed-publish-job", state_dir=state_dir)
    assert unchanged is not None
    assert unchanged["canonical_job_id"] == "failed-publish-job"
    assert unchanged["source_slot_id"] == "source-slot-2"
    assert unchanged["current_state"] == "queued"
    assert unchanged["previous_state"] is None
    assert unchanged["current_state"] != "hard_stopped"
