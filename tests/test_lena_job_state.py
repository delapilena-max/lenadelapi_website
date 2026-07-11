from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.lena_job_state import (
    StateTransitionError,
    apply_transition,
    create_snapshot,
    derive_canonical_job_id,
    derive_snapshot_from_artifacts,
    load_snapshot,
    save_snapshot,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _make_repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pipeline").mkdir(parents=True, exist_ok=True)
    return root


def test_valid_state_creation() -> None:
    snapshot = create_snapshot(source_slot_id="2026-07-10-01-photo")
    assert snapshot["canonical_job_id"] == "2026-07-10-01-photo"
    assert snapshot["current_state"] == "planned"
    assert snapshot["current_owner"] == "planning"
    assert snapshot["state_source"] == "explicit"


def test_deterministic_job_identity_prefers_output_slot_id_when_present() -> None:
    job_id = derive_canonical_job_id(
        source_slot_id="2026-07-10-01-photo",
        output_slot_id="2026-07-10-01-photo-story",
        provider_job_id="903333900062163005",
    )
    assert job_id == "2026-07-10-01-photo-story"


def test_same_source_slot_and_different_output_slots_do_not_collide() -> None:
    feed_job_id = derive_canonical_job_id(
        source_slot_id="source-123",
        output_slot_id="source-123-feed",
    )
    story_job_id = derive_canonical_job_id(
        source_slot_id="source-123",
        output_slot_id="source-123-story",
    )
    assert feed_job_id == "source-123-feed"
    assert story_job_id == "source-123-story"
    assert feed_job_id != story_job_id


def test_valid_transition() -> None:
    snapshot = create_snapshot(source_slot_id="job-1")
    updated = apply_transition(snapshot, "generating")
    assert updated["previous_state"] == "planned"
    assert updated["current_state"] == "generating"
    assert updated["current_owner"] == "generation"


def test_invalid_transition_rejection() -> None:
    snapshot = create_snapshot(source_slot_id="job-2")
    with pytest.raises(StateTransitionError):
        apply_transition(snapshot, "approved")


def test_approved_to_queued_rejection() -> None:
    snapshot = create_snapshot(source_slot_id="job-3", current_state="approved")
    with pytest.raises(StateTransitionError):
        apply_transition(snapshot, "queued")


def test_clean_export_required_to_queued_rejection() -> None:
    snapshot = create_snapshot(source_slot_id="job-4", current_state="clean_export_required")
    with pytest.raises(StateTransitionError):
        apply_transition(snapshot, "queued")


def test_clean_export_verified_to_queued_acceptance() -> None:
    snapshot = create_snapshot(source_slot_id="job-5", current_state="clean_export_verified")
    updated = apply_transition(snapshot, "queued")
    assert updated["current_state"] == "queued"
    assert updated["previous_state"] == "clean_export_verified"


def test_hard_stop_persistence() -> None:
    snapshot = create_snapshot(source_slot_id="job-6", current_state="generating")
    updated = apply_transition(
        snapshot,
        "hard_stopped",
        hard_stop_reason="provider failed after retries",
        originating_stage="generation",
        failure_classification="attempts_exhausted",
        retryable=False,
        manual_intervention_required=True,
        attempts_exhausted=True,
    )
    assert updated["current_state"] == "hard_stopped"
    assert updated["hard_stop_reason"] == "provider failed after retries"
    assert updated["originating_stage"] == "generation"
    assert updated["failure_classification"] == "attempts_exhausted"
    assert updated["retryable"] is False
    assert updated["manual_intervention_required"] is True
    assert updated["attempts_exhausted"] is True


def test_save_load_round_trip(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    snapshot = create_snapshot(
        source_slot_id="job-7",
        current_state="qa_required",
        attempt_counters_by_stage={"generation": 1},
    )
    save_snapshot(snapshot, state_dir=state_dir)
    loaded = load_snapshot("job-7", state_dir=state_dir)
    assert loaded is not None
    assert loaded["canonical_job_id"] == "job-7"
    assert loaded["current_state"] == "qa_required"
    assert loaded["attempt_counters_by_stage"] == {"generation": 1}


def test_artifact_reconciliation_is_fail_closed_for_queue_without_clean_export_verify(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    slot_id = "2026-07-07-03-photo"

    _write_json(
        root / "pipeline" / "asset_review" / "lena" / "2026-07-07" / f"{slot_id}_qa.json",
        {"slot_id": slot_id, "overall": "pass"},
    )
    _write_text(
        root / "pipeline" / "publish_packets" / "lena" / "2026-07-07" / f"LENA_PUBLISH_PACKET_{slot_id}.md",
        "draft packet",
    )
    _write_json(
        root / "pipeline" / "queue" / f"{slot_id}.json",
        {
            "post_id": slot_id,
            "slot_id": slot_id,
            "publish_attempts": 2,
            "metadata": {"source_task_id": "provider-123"},
        },
    )

    snapshot = derive_snapshot_from_artifacts(root=root, source_slot_id=slot_id)
    assert snapshot["current_state"] == "clean_export_required"
    assert snapshot["attempt_counters_by_stage"] == {"queue_publish": 2}
    assert any("queued state is withheld" in note for note in snapshot["notes"])


def test_artifact_reconciliation_uses_publish_receipt_for_published_pending_learning(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    slot_id = "2026-07-05-01-photo"

    _write_json(
        root / "pipeline" / "queue" / "published" / f"{slot_id}.json.receipt.json",
        {
            "post_id": slot_id,
            "instagram_media_id": "18086313821391447",
            "status": "published",
        },
    )

    snapshot = derive_snapshot_from_artifacts(root=root, source_slot_id=slot_id)
    assert snapshot["current_state"] == "published_pending_learning"
    assert snapshot["platform_media_id"] == "18086313821391447"
    assert any("Published artifact observed" in note for note in snapshot["notes"])


def test_artifact_reconciliation_keeps_distinct_output_identity_for_story_variant(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    source_slot_id = "readypack0709-pack007-00-photo"
    output_slot_id = "readypack0709-pack007-00-photo-story"

    _write_json(
        root / "pipeline" / "kling_workorders" / "2026-07-09" / "daily_workorders.json",
        {
            "slots": [
                {
                    "slot_id": source_slot_id,
                    "workorder_id": "wo-story-123",
                    "expected_assets": {
                        "final_photo_path": str(
                            root / "pipeline" / "kling_library" / "lena" / "2026-07-09" / f"{source_slot_id}_seed.png"
                        )
                    },
                }
            ]
        },
    )
    _write_json(
        root / "pipeline" / "asset_review" / "lena" / "2026-07-09" / f"{source_slot_id}_qa.json",
        {"slot_id": source_slot_id, "overall": "pass"},
    )
    _write_text(
        root / "pipeline" / "publish_packets" / "lena" / "2026-07-09" / f"{output_slot_id}_approval.md",
        "story packet",
    )
    _write_json(
        root / "pipeline" / "queue" / f"{output_slot_id}.json",
        {
            "post_id": output_slot_id,
            "slot_id": source_slot_id,
            "publish_attempts": 1,
            "metadata": {"source_task_id": "provider-story-123"},
        },
    )

    snapshot = derive_snapshot_from_artifacts(
        root=root,
        source_slot_id=source_slot_id,
        output_slot_id=output_slot_id,
    )

    assert snapshot["canonical_job_id"] == output_slot_id
    assert snapshot["source_slot_id"] == source_slot_id
    assert snapshot["output_slot_id"] == output_slot_id
    assert snapshot["attempt_counters_by_stage"] == {"queue_publish": 1}
    assert snapshot["artifact_paths"]["publish_packet"] is not None
    assert snapshot["artifact_paths"]["queue_item"] is not None
    assert snapshot["current_state"] == "clean_export_required"


def test_original_source_artifacts_remain_untouched(tmp_path: Path) -> None:
    root = _make_repo_root(tmp_path)
    slot_id = "2026-07-05-02-photo"
    workorder_path = root / "pipeline" / "kling_workorders" / "2026-07-05" / "daily_workorders.json"
    qa_path = root / "pipeline" / "asset_review" / "lena" / "2026-07-05" / f"{slot_id}_qa.json"

    _write_json(
        workorder_path,
        {
            "slots": [
                {
                    "slot_id": slot_id,
                    "workorder_id": "wo-123",
                    "expected_assets": {"final_photo_path": str(root / "pipeline" / "kling_library" / "lena" / "2026-07-05" / f"{slot_id}_seed.png")},
                }
            ]
        },
    )
    _write_json(qa_path, {"slot_id": slot_id, "overall": "fail", "failure_reasons": ["not approved"]})

    before_workorder = workorder_path.read_text(encoding="utf-8")
    before_qa = qa_path.read_text(encoding="utf-8")

    snapshot = derive_snapshot_from_artifacts(root=root, source_slot_id=slot_id)

    assert snapshot["current_state"] == "qa_required"
    assert workorder_path.read_text(encoding="utf-8") == before_workorder
    assert qa_path.read_text(encoding="utf-8") == before_qa
