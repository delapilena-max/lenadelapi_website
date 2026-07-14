from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import lena_apply_publish_approval_v1 as apply_approval
from tools import lena_promote_to_queue_v1 as promote_queue
from tools import lena_record_publish_approval_v1 as record_approval
from tools import lena_publish_approval_binding_v1 as approval_binding
from tools.lena_build_publish_packet_v1 import (
    QUEUE_DRAFT_CAPTION_PLACEHOLDER,
    resolve_packet_output_path,
    resolve_queue_draft_output_path,
)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_photo_item(tmp_path: Path, slot_id: str) -> dict:
    date_str = "2026-07-13"
    out_dir = tmp_path / "publish_packets"
    image_path = tmp_path / "assets" / f"{slot_id}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(f"{slot_id}-bytes".encode("utf-8"))

    packet_path = resolve_packet_output_path(date_str, slot_id, out_dir)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text("# packet\n", encoding="utf-8")

    qa_path = tmp_path / "asset_review" / "lena" / date_str / f"{slot_id}__{_sha(image_path)}_qa_disposition.json"
    qa = {
        "schema_version": "lena_photo_qa_disposition_v1",
        "slot_id": slot_id,
        "image_path": str(image_path.resolve()),
        "image_sha256": _sha(image_path),
        "disposition": "accept",
    }
    _write_json(qa_path, qa)

    draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
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

    return {
        "date": date_str,
        "slot": slot_id,
        "out_dir": out_dir,
        "image_path": image_path,
        "packet_path": packet_path,
        "draft_path": draft_path,
        "qa_path": qa_path,
        "approved_caption": "Approved caption #one",
        "resolved": {
            "intended_packet_output_path": str(packet_path.resolve()),
            "qa_path": str(qa_path.resolve()),
            "qa_overall": "pass",
            "image_path": str(image_path.resolve()),
        },
    }


def _record_real_approval(
    ctx: dict,
    monkeypatch: pytest.MonkeyPatch,
    *,
    live_publish: bool,
) -> Path:
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
        live_publish_confirm=(
            record_approval.REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE if live_publish else None
        ),
    )
    return record_approval.write_approval_record(checked, force=False)


def _set_draft_caption(ctx: dict) -> None:
    draft = json.loads(ctx["draft_path"].read_text(encoding="utf-8"))
    draft["caption"] = ctx["approved_caption"]
    _write_json(ctx["draft_path"], draft)


def _stub_promotion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(promote_queue, "_revalidate_with_resolver", lambda *args, **kwargs: {"qa_overall": "pass"})
    monkeypatch.setattr(
        promote_queue,
        "_validate_clean_export",
        lambda queue_draft: {
            "source_path": queue_draft["media_path"],
            "source_sha256": _sha(Path(queue_draft["media_path"])),
            "clean_derivative_path": queue_draft["media_path"],
            "clean_derivative_sha256": _sha(Path(queue_draft["media_path"])),
            "clean_provenance_sidecar_path": str(Path(queue_draft["media_path"]).with_suffix(".json")),
            "generated_by": "tests",
            "created_at_utc": "2026-07-13T12:00:00Z",
        },
    )


def test_valid_native_sha_bound_approval_reaches_apply_and_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "native-approval-photo")
    approval_path = _record_real_approval(ctx, monkeypatch, live_publish=True)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    assert approval["publish_packet_sha256"] == _sha(ctx["packet_path"])
    assert approval["queue_draft_sha256"] == _sha(ctx["draft_path"])

    apply_checked = apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])
    assert apply_checked["approval_binding_source"] == "native"
    assert apply_checked["would_write"] is True
    apply_approval.apply_publish_approval(apply_checked)

    _stub_promotion(monkeypatch)
    promote_checked = promote_queue.check_promote_to_queue(
        ctx["date"], ctx["slot"], "kling", out_dir=ctx["out_dir"], queue_root=tmp_path / "queue"
    )
    assert promote_checked["approval_binding_source"] == "native"
    assert promote_checked["would_write"] is True
    second_apply = apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])
    assert second_apply["approval_binding_source"] == "native"
    assert second_apply["already_applied"] is True
    assert second_apply["would_write"] is False
    assert second_apply["fields_that_would_change"] == []
    assert apply_approval.apply_publish_approval(second_apply) is None


def test_missing_or_mismatched_native_hashes_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "missing-hash-photo")
    approval_path = _record_real_approval(ctx, monkeypatch, live_publish=True)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.pop("publish_packet_sha256")
    approval["queue_draft_sha256"] = "0" * 64
    _write_json(approval_path, approval)

    with pytest.raises(apply_approval.ApplyApprovalError, match="approval SHA bindings are missing or invalid"):
        apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])

    _set_draft_caption(ctx)
    _stub_promotion(monkeypatch)
    with pytest.raises(promote_queue.PromoteError, match="approval SHA bindings are missing or invalid"):
        promote_queue.check_promote_to_queue(
            ctx["date"], ctx["slot"], "kling", out_dir=ctx["out_dir"], queue_root=tmp_path / "queue"
        )


def test_valid_correction_path_reaches_apply_and_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "corrected-approval-photo")
    approval_path = _record_real_approval(ctx, monkeypatch, live_publish=True)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.pop("publish_packet_sha256")
    approval.pop("queue_draft_sha256")
    _write_json(approval_path, approval)

    correction, correction_path = approval_binding.build_approval_sha_binding_correction(approval_path)
    approval_binding.write_approval_sha_binding_correction(correction_path, correction)

    apply_checked = apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])
    assert apply_checked["approval_binding_source"] == "corrected"
    assert apply_checked["approval_correction_artifact_path"] == str(correction_path)
    apply_approval.apply_publish_approval(apply_checked)

    _stub_promotion(monkeypatch)
    promote_checked = promote_queue.check_promote_to_queue(
        ctx["date"], ctx["slot"], "kling", out_dir=ctx["out_dir"], queue_root=tmp_path / "queue"
    )
    assert promote_checked["approval_binding_source"] == "corrected"
    assert promote_checked["approval_correction_artifact_path"] == str(correction_path)
    second_apply = apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])
    assert second_apply["approval_binding_source"] == "corrected"
    assert second_apply["already_applied"] is True
    assert second_apply["would_write"] is False
    assert second_apply["fields_that_would_change"] == []
    assert apply_approval.apply_publish_approval(second_apply) is None


def test_tampered_or_duplicate_correction_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "tampered-correction-photo")
    approval_path = _record_real_approval(ctx, monkeypatch, live_publish=False)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.pop("publish_packet_sha256")
    approval.pop("queue_draft_sha256")
    _write_json(approval_path, approval)

    correction, correction_path = approval_binding.build_approval_sha_binding_correction(approval_path)
    approval_binding.write_approval_sha_binding_correction(correction_path, correction)

    with pytest.raises(ValueError, match="already exists"):
        approval_binding.build_approval_sha_binding_correction(approval_path)

    tampered = json.loads(correction_path.read_text(encoding="utf-8"))
    tampered["publish_packet_sha256"] = "0" * 64
    _write_json(correction_path, tampered)

    with pytest.raises(apply_approval.ApplyApprovalError, match="correction artifact publish_packet_sha256"):
        apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])


def test_unrelated_deficient_approval_remains_unaffected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "primary-approval-photo")
    other = _seed_photo_item(tmp_path, "other-approval-photo")
    _record_real_approval(ctx, monkeypatch, live_publish=False)
    other_approval_path = _record_real_approval(other, monkeypatch, live_publish=False)

    other_approval = json.loads(other_approval_path.read_text(encoding="utf-8"))
    other_approval.pop("publish_packet_sha256")
    other_approval.pop("queue_draft_sha256")
    _write_json(other_approval_path, other_approval)
    correction, correction_path = approval_binding.build_approval_sha_binding_correction(other_approval_path)
    approval_binding.write_approval_sha_binding_correction(correction_path, correction)

    checked = apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])
    assert checked["approval_binding_source"] == "native"


def test_wrong_applied_caption_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "wrong-applied-caption-photo")
    approval_path = _record_real_approval(ctx, monkeypatch, live_publish=True)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.pop("publish_packet_sha256")
    approval.pop("queue_draft_sha256")
    _write_json(approval_path, approval)
    correction, correction_path = approval_binding.build_approval_sha_binding_correction(approval_path)
    approval_binding.write_approval_sha_binding_correction(correction_path, correction)

    draft = json.loads(ctx["draft_path"].read_text(encoding="utf-8"))
    draft["caption"] = "Different caption"
    _write_json(ctx["draft_path"], draft)

    with pytest.raises(apply_approval.ApplyApprovalError, match="queue_draft_sha256"):
        apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])

    _stub_promotion(monkeypatch)
    with pytest.raises(promote_queue.PromoteError, match="queue_draft_sha256"):
        promote_queue.check_promote_to_queue(
            ctx["date"], ctx["slot"], "kling", out_dir=ctx["out_dir"], queue_root=tmp_path / "queue"
        )


def test_unrelated_post_apply_draft_mutation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _seed_photo_item(tmp_path, "post-apply-mutation-photo")
    approval_path = _record_real_approval(ctx, monkeypatch, live_publish=True)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval.pop("publish_packet_sha256")
    approval.pop("queue_draft_sha256")
    _write_json(approval_path, approval)
    correction, correction_path = approval_binding.build_approval_sha_binding_correction(approval_path)
    approval_binding.write_approval_sha_binding_correction(correction_path, correction)

    checked = apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])
    apply_approval.apply_publish_approval(checked)

    draft = json.loads(ctx["draft_path"].read_text(encoding="utf-8"))
    draft["metadata"]["visual_style"] = "tampered"
    _write_json(ctx["draft_path"], draft)

    with pytest.raises(apply_approval.ApplyApprovalError, match="queue_draft_sha256"):
        apply_approval.check_apply_publish_approval(ctx["date"], ctx["slot"], ctx["out_dir"])

    _stub_promotion(monkeypatch)
    with pytest.raises(promote_queue.PromoteError, match="queue_draft_sha256"):
        promote_queue.check_promote_to_queue(
            ctx["date"], ctx["slot"], "kling", out_dir=ctx["out_dir"], queue_root=tmp_path / "queue"
        )
