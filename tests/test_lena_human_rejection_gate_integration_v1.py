from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import lena_human_rejection_gate_v1 as rejection_gate
from tools import lena_record_human_rejection_v1 as record_rejection
from tools import lena_record_publish_approval_v1 as record_approval
from tools import lena_apply_publish_approval_v1 as apply_approval
from tools import lena_promote_to_queue_v1 as promote_queue
from tools.lena_build_publish_packet_v1 import (
    QUEUE_DRAFT_CAPTION_PLACEHOLDER,
    resolve_packet_output_path,
    resolve_queue_draft_output_path,
)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_photo_item(tmp_path: Path) -> dict:
    date_str = "2026-07-13"
    slot_id = "test-human-rejection-photo"
    out_dir = tmp_path / "publish_packets"
    review_root = tmp_path / "asset_review" / "lena"
    image_path = tmp_path / "assets" / "photo.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"photo-bytes")

    packet_path = resolve_packet_output_path(date_str, slot_id, out_dir)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text("# packet\n", encoding="utf-8")

    draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
    decision_path = tmp_path / "decision.json"
    decision = {"as_of_date": date_str, "decision_fingerprint_sha256": "d" * 64}
    _write_json(decision_path, decision)

    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "provider": "higgsfield",
        "job_type": "text2image_soul_v2",
        "saved_image_path": str(image_path.resolve()),
        "prompt_sha256": "p" * 64,
        "provider_job_id": "job-1",
        "provider_status": "completed",
    }
    _write_json(manifest_path, manifest)

    qa_path = review_root / date_str / f"{slot_id}__{_sha(image_path)}_qa_disposition.json"
    qa = {
        "schema_version": "lena_photo_qa_disposition_v1",
        "influencer_id": "lena",
        "slot_id": slot_id,
        "image_path": str(image_path.resolve()),
        "image_sha256": _sha(image_path),
        "decision_artifact_path": str(decision_path.resolve()),
        "decision_fingerprint_sha256": "d" * 64,
        "prompt_sha256": "p" * 64,
        "disposition": "accept",
        "reviewer_type": "bounded_visual_provider",
        "provider_called": True,
        "reason_codes": [],
        "side_effects_performed": [],
        "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
        "generation_provenance": {
            "date": date_str,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": _sha(manifest_path),
            "provider_job_id": "job-1",
            "provider_status": "completed",
        },
    }
    _write_json(qa_path, qa)

    approved_caption = "approved caption #test"
    draft = {
        "post_id": slot_id,
        "slot_id": slot_id,
        "media_path": str(image_path.resolve()),
        "media_type": "photo",
        "platforms": ["instagram"],
        "caption": QUEUE_DRAFT_CAPTION_PLACEHOLDER,
        "approved_for_live_publish": False,
        "operator_review_required": True,
        "metadata": {
            "avatar_nickname": "Lena",
            "image_engine": "kling_text2image",
            "image_prompt": "prompt",
            "publish_packet_path": str(packet_path.resolve()),
            "qa_path": str(qa_path.resolve()),
            "qa_overall": "pass",
            "source_date": date_str,
            "source_slot_id": slot_id,
            "generated_by": "tools/lena_build_publish_packet_v1.py",
            "queue_draft_only": True,
            "activity": "walk",
            "pose": "casual",
            "visual_style": "daylight",
        },
    }
    _write_json(draft_path, draft)

    approval_path = record_approval.resolve_approval_output_path(date_str, slot_id, out_dir)
    approval = {
        "post_id": slot_id,
        "source_date": date_str,
        "publish_packet_path": str(packet_path.resolve()),
        "queue_draft_path": str(draft_path.resolve()),
        "qa_path": str(qa_path.resolve()),
        "qa_overall": "pass",
        "approved_caption": approved_caption,
        "hashtag_count": 1,
        "platforms": ["instagram"],
        "approved_by": "operator",
        "caption_approval_statement": record_approval.REQUIRED_CAPTION_CONFIRM_PHRASE,
        "live_publish_statement": record_approval.REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE,
        "approved_at_utc": "2026-07-13T12:00:00+00:00",
        "manual_one_off_confirmed": True,
        "generated_by": "tests",
        "promotion_status": "not_yet_promoted",
    }
    _write_json(approval_path, approval)

    resolved = {
        "intended_packet_output_path": str(packet_path.resolve()),
        "qa_path": str(qa_path.resolve()),
        "qa_overall": "pass",
        "image_path": str(image_path.resolve()),
    }
    return {
        "date": date_str,
        "slot": slot_id,
        "out_dir": out_dir,
        "review_root": review_root,
        "image_path": image_path,
        "packet_path": packet_path,
        "draft_path": draft_path,
        "qa_path": qa_path,
        "approval_path": approval_path,
        "approved_caption": approved_caption,
        "resolved": resolved,
    }


def _record_rejection(ctx: dict, monkeypatch: pytest.MonkeyPatch) -> Path:
    decision = {"as_of_date": ctx["date"], "decision_fingerprint_sha256": "d" * 64}
    manifest = json.loads((ctx["image_path"].parents[1] / "manifest.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(record_rejection, "ROOT", ctx["image_path"].parents[1])
    monkeypatch.setattr(record_rejection.disposition, "disposition_artifact_path", lambda artifact: ctx["qa_path"])
    monkeypatch.setattr(record_rejection.disposition, "_validate_decision", lambda path: (decision, {"slot_id": ctx["slot"]}))
    monkeypatch.setattr(
        record_rejection.disposition,
        "_inspect_image",
        lambda path, generated: {"path": str(Path(path).resolve()), "sha256": _sha(Path(path))},
    )
    monkeypatch.setattr(record_rejection.disposition, "_validate_manifest", lambda path, d, c, i: manifest)
    rejection, retry, rejection_path, retry_path = record_rejection.build_rejection_and_retry_plan(
        date_str=ctx["date"],
        slot_id=ctx["slot"],
        image_sha=_sha(ctx["image_path"]),
        disposition_path=ctx["qa_path"],
        disposition_sha=_sha(ctx["qa_path"]),
        publish_packet_path=ctx["packet_path"],
        queue_draft_path=ctx["draft_path"],
        reason=record_rejection.EXACT_REASON,
        output_root=ctx["review_root"],
    )
    record_rejection._write_pair(rejection, retry, rejection_path, retry_path)
    assert retry_path.is_file()
    return rejection_path


def test_publish_approval_blocks_on_valid_matching_human_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path)
    _record_rejection(ctx, monkeypatch)
    monkeypatch.setattr(rejection_gate, "DEFAULT_REJECTION_ROOT", ctx["review_root"])
    monkeypatch.setattr(record_approval, "resolve_packet_inputs", lambda *args, **kwargs: ctx["resolved"])

    with pytest.raises(record_approval.ApprovalCheckError, match="matching human rejection artifact blocks this item"):
        record_approval.check_publish_approval(
            ctx["date"],
            ctx["slot"],
            approved_caption=ctx["approved_caption"],
            approved_by="operator",
            caption_confirm=record_approval.REQUIRED_CAPTION_CONFIRM_PHRASE,
            platforms=["instagram"],
            out_dir=ctx["out_dir"],
            queue_draft_path_override=None,
        )


def test_publish_approval_blocks_on_tampered_matching_human_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path)
    rejection_path = _record_rejection(ctx, monkeypatch)
    tampered = json.loads(rejection_path.read_text(encoding="utf-8"))
    tampered["publish_packet_sha256"] = "0" * 64
    _write_json(rejection_path, tampered)
    monkeypatch.setattr(rejection_gate, "DEFAULT_REJECTION_ROOT", ctx["review_root"])
    monkeypatch.setattr(record_approval, "resolve_packet_inputs", lambda *args, **kwargs: ctx["resolved"])

    with pytest.raises(record_approval.ApprovalCheckError, match="publish_packet_sha256"):
        record_approval.check_publish_approval(
            ctx["date"],
            ctx["slot"],
            approved_caption=ctx["approved_caption"],
            approved_by="operator",
            caption_confirm=record_approval.REQUIRED_CAPTION_CONFIRM_PHRASE,
            platforms=["instagram"],
            out_dir=ctx["out_dir"],
            queue_draft_path_override=None,
        )


def test_unrelated_human_rejection_does_not_block_other_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path)
    other = dict(ctx)
    other["slot"] = "different-slot"
    artifact_path = ctx["review_root"] / ctx["date"] / f"{other['slot']}__{_sha(ctx['image_path'])}_human_rejection.json"
    _write_json(artifact_path, {
        "schema_version": "lena_human_rejection_v1",
        "influencer_id": "lena",
        "recorded_at_utc": "2026-07-13T12:30:00Z",
        "date": ctx["date"],
        "slot_id": other["slot"],
        "image_sha256": _sha(ctx["image_path"]),
        "publish_packet_path": str(ctx["packet_path"].resolve()),
        "publish_packet_sha256": _sha(ctx["packet_path"]),
        "queue_draft_path": str(ctx["draft_path"].resolve()),
        "queue_draft_sha256": _sha(ctx["draft_path"]),
        "qa_disposition_artifact_path": str(ctx["qa_path"].resolve()),
        "qa_disposition_artifact_sha256": _sha(ctx["qa_path"]),
        "decision_artifact_path": str((tmp_path / "decision.json").resolve()),
        "decision_fingerprint_sha256": "d" * 64,
        "operator_reason": record_rejection.EXACT_REASON,
        "classification": "identity_related_human_rejection",
        "retryable": True,
        "retry_attempt": 1,
        "retry_cap": 1,
        "historical_artifacts_modified": [],
    })
    monkeypatch.setattr(rejection_gate, "DEFAULT_REJECTION_ROOT", ctx["review_root"])
    monkeypatch.setattr(record_approval, "resolve_packet_inputs", lambda *args, **kwargs: ctx["resolved"])

    checked = record_approval.check_publish_approval(
        ctx["date"],
        ctx["slot"],
        approved_caption=ctx["approved_caption"],
        approved_by="operator",
        caption_confirm=record_approval.REQUIRED_CAPTION_CONFIRM_PHRASE,
        platforms=["instagram"],
        out_dir=ctx["out_dir"],
        queue_draft_path_override=None,
    )
    assert checked["slot_id"] == ctx["slot"]


def test_apply_publish_approval_blocks_on_matching_human_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path)
    _record_rejection(ctx, monkeypatch)
    monkeypatch.setattr(rejection_gate, "DEFAULT_REJECTION_ROOT", ctx["review_root"])

    with pytest.raises(apply_approval.ApplyApprovalError, match="matching human rejection artifact blocks this item"):
        apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])


def test_queue_promotion_blocks_on_matching_human_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path)
    draft = json.loads(ctx["draft_path"].read_text(encoding="utf-8"))
    draft["caption"] = ctx["approved_caption"]
    _write_json(ctx["draft_path"], draft)
    _record_rejection(ctx, monkeypatch)
    monkeypatch.setattr(rejection_gate, "DEFAULT_REJECTION_ROOT", ctx["review_root"])

    with pytest.raises(promote_queue.PromoteError, match="matching human rejection artifact blocks this item"):
        promote_queue.check_promote_to_queue(
            ctx["date"],
            ctx["slot"],
            "kling",
            out_dir=ctx["out_dir"],
            queue_root=tmp_path / "live_queue",
        )


def test_recorder_output_blocks_approval_apply_and_promotion_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path)
    rejection_path = _record_rejection(ctx, monkeypatch)
    assert rejection_path.is_file()
    monkeypatch.setattr(rejection_gate, "DEFAULT_REJECTION_ROOT", ctx["review_root"])
    monkeypatch.setattr(record_approval, "resolve_packet_inputs", lambda *args, **kwargs: ctx["resolved"])

    with pytest.raises(record_approval.ApprovalCheckError, match="matching human rejection artifact blocks this item"):
        record_approval.check_publish_approval(
            ctx["date"],
            ctx["slot"],
            approved_caption=ctx["approved_caption"],
            approved_by="operator",
            caption_confirm=record_approval.REQUIRED_CAPTION_CONFIRM_PHRASE,
            platforms=["instagram"],
            out_dir=ctx["out_dir"],
            queue_draft_path_override=None,
        )

    with pytest.raises(apply_approval.ApplyApprovalError, match="matching human rejection artifact blocks this item"):
        apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])

    draft = json.loads(ctx["draft_path"].read_text(encoding="utf-8"))
    draft["caption"] = ctx["approved_caption"]
    _write_json(ctx["draft_path"], draft)
    with pytest.raises(promote_queue.PromoteError, match="matching human rejection artifact blocks this item"):
        promote_queue.check_promote_to_queue(
            ctx["date"],
            ctx["slot"],
            "kling",
            out_dir=ctx["out_dir"],
            queue_root=tmp_path / "live_queue",
        )
