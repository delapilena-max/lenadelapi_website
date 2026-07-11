from __future__ import annotations

import json
import threading
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
            "in_flight_dir": str(root / "queue" / "in_flight"),
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


def _seed_queue_post(
    manager: PostingManager,
    *,
    post_id: str = "queued-claim-1",
    slot_id: str | None = None,
) -> Path:
    media_path = manager.queue_dir / f"{post_id}.png"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"fake-png-bytes")

    post_path = manager.queue_dir / f"{post_id}.json"
    _write_json(
        post_path,
        {
            "post_id": post_id,
            "slot_id": slot_id or post_id,
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


def test_atomic_claim_allows_exactly_one_winner(tmp_path: Path) -> None:
    manager_a = _build_manager(tmp_path)
    manager_b = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager_a, post_id="claim-race-1")

    barrier = threading.Barrier(2)
    results: list[dict] = []

    def _attempt_claim(manager: PostingManager) -> None:
        barrier.wait()
        results.append(manager._claim_queue_item(post_path))

    thread_a = threading.Thread(target=_attempt_claim, args=(manager_a,))
    thread_b = threading.Thread(target=_attempt_claim, args=(manager_b,))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    winners = [result for result in results if result["status"] == "claimed"]
    losers = [result for result in results if result["status"] == "skipped"]

    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0]["reason"] == "claimed_elsewhere"
    assert not post_path.exists()
    assert (manager_a.in_flight_dir / "claim-race-1.json").exists()


def test_concurrent_process_one_claims_once_and_loser_skips_without_publish(tmp_path: Path) -> None:
    manager_a = _build_manager(tmp_path)
    manager_b = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager_a, post_id="concurrent-publish-1")

    barrier = threading.Barrier(2)
    publish_calls: list[str] = []

    def _fake_publish(post, *, dry_run: bool):
        publish_calls.append(post.post_id)
        return {"ok": True, "result": {"instagram_result": {}}}

    manager_a.publish = _fake_publish  # type: ignore[method-assign]
    manager_b.publish = _fake_publish  # type: ignore[method-assign]

    results: list[dict] = []

    def _run(manager: PostingManager) -> None:
        barrier.wait()
        results.append(manager.process_one(post_path, dry_run=False))

    thread_a = threading.Thread(target=_run, args=(manager_a,))
    thread_b = threading.Thread(target=_run, args=(manager_b,))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    successes = [result for result in results if result["status"] == "success"]
    skipped = [result for result in results if result["status"] == "skipped"]

    assert len(successes) == 1
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "claimed_elsewhere"
    assert publish_calls == ["concurrent-publish-1"]
    assert (manager_a.published_dir / "concurrent-publish-1.json").exists()
    assert not post_path.exists()
    assert not (manager_a.in_flight_dir / "concurrent-publish-1.json").exists()


def test_successful_claimed_publish_moves_to_published_and_advances_job_state(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(
        manager,
        post_id="output-claim-1",
        slot_id="source-slot-claim-1",
    )

    queued_snapshot = create_snapshot(
        canonical_job_id="output-claim-1",
        output_slot_id="output-claim-1",
        source_slot_id="source-slot-claim-1",
        current_state="queued",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    def _publish_with_platform_media_id(post, *, dry_run: bool):
        return {
            "ok": True,
            "result": {"instagram_result": {"instagram_media_id": "18000000000000000"}},
        }

    monkeypatch.setattr(manager, "publish", _publish_with_platform_media_id)

    result = manager.process_one(post_path, dry_run=False)

    published_path = manager.published_dir / "output-claim-1.json"
    receipt_path = published_path.with_suffix(".json.receipt.json")

    assert result["status"] == "success"
    assert result["post_id"] == "output-claim-1"
    assert result["job_state_result"]["status"] == "updated"
    assert published_path.exists()
    assert receipt_path.exists()
    assert not post_path.exists()
    assert not (manager.in_flight_dir / "output-claim-1.json").exists()

    updated = load_snapshot("output-claim-1", state_dir=state_dir)
    assert updated is not None
    assert updated["canonical_job_id"] == "output-claim-1"
    assert updated["source_slot_id"] == "source-slot-claim-1"
    assert updated["current_state"] == "published_pending_learning"


def test_dry_run_does_not_claim_or_mutate_queue_state(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager, post_id="dry-run-claim-1")

    queued_snapshot = create_snapshot(
        canonical_job_id="dry-run-claim-1",
        output_slot_id="dry-run-claim-1",
        current_state="queued",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    result = manager.process_one(post_path, dry_run=True)

    assert result["status"] == "dry_run"
    assert post_path.exists()
    assert not (manager.in_flight_dir / "dry-run-claim-1.json").exists()
    assert not (manager.published_dir / "dry-run-claim-1.json").exists()
    unchanged = load_snapshot("dry-run-claim-1", state_dir=state_dir)
    assert unchanged is not None
    assert unchanged["current_state"] == "queued"


def test_missing_live_queue_item_is_skipped_safely(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)
    missing_path = manager.queue_dir / "missing-live-item.json"

    result = manager.process_one(missing_path, dry_run=False)

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_queue_item"


def test_stale_in_flight_residue_is_not_scanned_or_auto_published(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)
    manager.ensure_dirs()

    media_path = manager.queue_dir / "stale-claim-1.png"
    media_path.write_bytes(b"fake-png-bytes")
    stale_claim_path = manager.in_flight_dir / "stale-claim-1.json"
    _write_json(
        stale_claim_path,
        {
            "post_id": "stale-claim-1",
            "slot_id": "stale-claim-1",
            "media_path": str(media_path),
            "media_type": "photo",
            "caption": "A prepared caption",
            "platforms": ["instagram"],
            "metadata": {"caption_variant": "v1"},
        },
    )

    assert manager.list_post_files() == []

    result = manager.process_one(manager.queue_dir / "stale-claim-1.json", dry_run=False)

    assert result["status"] == "skipped"
    assert result["reason"] == "claimed_elsewhere"
    assert stale_claim_path.exists()


def test_publish_failure_after_claim_moves_item_out_of_live_queue_without_state_advance(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    _patch_state_dir(monkeypatch, state_dir)

    manager = _build_manager(tmp_path)
    post_path = _seed_queue_post(manager, post_id="failed-claim-1")

    queued_snapshot = create_snapshot(
        canonical_job_id="failed-claim-1",
        output_slot_id="failed-claim-1",
        source_slot_id="source-slot-failed-1",
        current_state="queued",
    )
    save_snapshot(queued_snapshot, state_dir=state_dir)

    def _failed_publish(post, *, dry_run: bool):
        return {"ok": False, "error": "synthetic publish failure"}

    monkeypatch.setattr(manager, "publish", _failed_publish)

    result = manager.process_one(post_path, dry_run=False)

    failed_files = list(manager.failed_dir.glob("failed-claim-1*.json"))

    assert result["status"] == "failed"
    assert not post_path.exists()
    assert not (manager.in_flight_dir / "failed-claim-1.json").exists()
    assert failed_files

    unchanged = load_snapshot("failed-claim-1", state_dir=state_dir)
    assert unchanged is not None
    assert unchanged["current_state"] == "queued"
    assert unchanged["source_slot_id"] == "source-slot-failed-1"
