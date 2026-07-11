from __future__ import annotations

import json
from pathlib import Path
import urllib.request

import pipeline.lena_job_state as lena_job_state
from pipeline.lena_job_state import create_snapshot, save_snapshot
from tools.lena_inspect_in_flight_publish_claims_v1 import inspect_in_flight_publish_claims
import tools.lena_inspect_in_flight_publish_claims_v1 as inspector_module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_config(root: Path) -> dict:
    return {
        "queue_dir": str(root / "pipeline" / "queue"),
        "published_dir": str(root / "pipeline" / "queue" / "published"),
        "failed_dir": str(root / "pipeline" / "queue" / "failed"),
        "in_flight_dir": str(root / "pipeline" / "queue" / "in_flight"),
    }


def _seed_in_flight(root: Path, *, post_id: str, slot_id: str | None = None) -> Path:
    queue_dir = root / "pipeline" / "queue"
    media_path = queue_dir / f"{post_id}.png"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"fake-png-bytes")
    path = queue_dir / "in_flight" / f"{post_id}.json"
    _write_json(
        path,
        {
            "post_id": post_id,
            "slot_id": slot_id or post_id,
            "media_path": str(media_path),
            "media_type": "photo",
            "caption": "Prepared caption",
            "platforms": ["instagram"],
            "metadata": {"caption_variant": "v1"},
        },
    )
    return path


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = (path.stat().st_mtime_ns, len(path.read_bytes()))
    return snapshot


def _receipt_payload(post_id: str, *, publish_backend: str = "pipeline.publisher.instagram_queue_bridge") -> dict:
    return {
        "status": "published",
        "post_id": post_id,
        "instagram_media_id": "18000000000000000",
        "publish_response": {
            "ok": True,
            "backend": publish_backend,
            "result": {
                "instagram_result": {
                    "instagram_media_id": "18000000000000000",
                    "published_response": {"id": "18000000000000000"},
                }
            },
        },
    }


def test_in_flight_with_published_json_and_receipt_is_locally_confirmed(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-success-1")
    published_path = root / "pipeline" / "queue" / "published" / "claim-success-1.json"
    _write_json(published_path, {"post_id": "claim-success-1", "slot_id": "claim-success-1"})
    _write_json(published_path.with_suffix(".json.receipt.json"), _receipt_payload("claim-success-1"))

    result = inspect_in_flight_publish_claims(root=root, config=config)

    assert result["counts"]["published_locally_confirmed"] == 1
    assert result["items"][0]["classification"] == "published_locally_confirmed"


def test_live_queue_and_in_flight_without_receipt_is_pre_unlink_duplicate(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-duplicate-1")
    _write_json(
        root / "pipeline" / "queue" / "claim-duplicate-1.json",
        {"post_id": "claim-duplicate-1", "slot_id": "claim-duplicate-1"},
    )

    result = inspect_in_flight_publish_claims(root=root, config=config)

    assert result["items"][0]["classification"] == "claimed_pre_unlink_duplicate"


def test_lone_in_flight_is_ambiguous_without_local_publish_evidence(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-ambiguous-1")

    result = inspect_in_flight_publish_claims(root=root, config=config)

    assert result["items"][0]["classification"] == "claimed_no_local_publish_evidence"


def test_published_json_without_receipt_is_classified_separately(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-moved-1")
    _write_json(
        root / "pipeline" / "queue" / "published" / "claim-moved-1.json",
        {"post_id": "claim-moved-1", "slot_id": "claim-moved-1"},
    )

    result = inspect_in_flight_publish_claims(root=root, config=config)

    assert result["items"][0]["classification"] == "published_move_without_receipt"


def test_failed_artifact_without_receipt_is_external_state_unknown(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-failed-1")
    _write_json(
        root / "pipeline" / "queue" / "failed" / "claim-failed-1.failed_publish.json",
        {"post_id": "claim-failed-1", "slot_id": "claim-failed-1", "last_error": "boom"},
    )

    result = inspect_in_flight_publish_claims(root=root, config=config)

    assert result["items"][0]["classification"] == "failed_local_record_external_state_unknown"


def test_conflicting_evidence_requires_manual_review(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-conflict-1")
    published_path = root / "pipeline" / "queue" / "published" / "claim-conflict-1.json"
    _write_json(published_path, {"post_id": "claim-conflict-1", "slot_id": "claim-conflict-1"})
    _write_json(published_path.with_suffix(".json.receipt.json"), _receipt_payload("claim-conflict-1"))
    _write_json(
        root / "pipeline" / "queue" / "failed" / "claim-conflict-1.failed_publish.json",
        {"post_id": "claim-conflict-1", "slot_id": "claim-conflict-1", "last_error": "boom"},
    )

    result = inspect_in_flight_publish_claims(root=root, config=config)

    assert result["items"][0]["classification"] == "manual_review_required"


def test_item_age_is_informational_only_and_never_safe_to_retry(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    in_flight_path = _seed_in_flight(root, post_id="claim-old-1")
    stale_seconds = 86400
    old_mtime = in_flight_path.stat().st_mtime - stale_seconds
    in_flight_path.touch()
    media_path = root / "pipeline" / "queue" / "claim-old-1.png"
    for path in (in_flight_path, media_path):
        path.touch()
        Path(path).touch()
    for path in (in_flight_path, media_path):
        import os
        os.utime(path, (old_mtime, old_mtime))

    result = inspect_in_flight_publish_claims(root=root, config=config)
    item = result["items"][0]

    assert item["classification"] == "claimed_no_local_publish_evidence"
    assert item["in_flight_age_seconds"] >= stale_seconds - 5
    assert "safe_to_retry" not in item


def test_inspector_is_read_only_and_never_calls_publish_or_network(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    config = _build_config(root)
    _seed_in_flight(root, post_id="claim-readonly-1")
    state_dir = root / "pipeline" / "state" / "lena_jobs"
    snapshot = create_snapshot(
        canonical_job_id="claim-readonly-1",
        output_slot_id="claim-readonly-1",
        current_state="queued",
    )
    save_snapshot(snapshot, state_dir=state_dir)

    def _fail(*args, **kwargs):
        raise AssertionError("unexpected external or publisher call")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    monkeypatch.setattr(lena_job_state, "save_snapshot", _fail)
    monkeypatch.setattr(inspector_module, "_load_config", lambda path=None: config)

    before = _snapshot_tree(root)
    result = inspect_in_flight_publish_claims(root=root, config=config)
    after = _snapshot_tree(root)

    assert result["items"][0]["classification"] == "claimed_no_local_publish_evidence"
    assert before == after
