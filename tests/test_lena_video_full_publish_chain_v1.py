from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pipeline.qa.lena_photo_qa as lena_photo_qa
import tools.lena_build_publish_packet_v1 as packet_mod
from tools.lena_build_publish_packet_v1 import (
    resolve_packet_inputs_video,
    build_queue_draft,
    write_packet,
    write_queue_draft,
    resolve_queue_draft_output_path,
)
from tools.lena_record_publish_approval_v1 import (
    check_publish_approval,
    write_approval_record,
    REQUIRED_CAPTION_CONFIRM_PHRASE,
    REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE,
)
from tools.lena_apply_publish_approval_v1 import (
    check_apply_publish_approval,
    apply_publish_approval,
)
from tools.lena_promote_to_queue_v1 import (
    check_promote_to_queue,
    promote_to_queue,
)
from tools.lena_scrub_media_metadata_v1 import scrub_video_metadata, resolve_clean_output_path

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")


def _make_test_video(path: Path, duration: float = 3.0, width: int = 640, height: int = 1136) -> Path:
    """Synthetic, local, ffmpeg-lavfi-generated test fixture -- not an AI
    render or provider call. Same fixture category already used in
    tests/test_lena_video_resolver_v1.py and
    tests/test_lena_video_promotion_bridge_v1.py, deliberately duplicated
    (not imported) here so this integration test never depends on another
    test file's internal helpers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=24",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True, capture_output=True, timeout=60,
    )
    return path


def _write_qa_pass(asset_review_root: Path, date_str: str, slot_id: str) -> None:
    status_fields = [
        "identity_fidelity", "face_realism_anti_generic_drift", "skin_realism_no_invented_marks",
        "wardrobe_class_fidelity", "public_scene_clothing_continuity", "outerwear_underlayer_correctness",
        "body_shape_continuity", "hands_anatomy_sanity", "environment_realism_scene_coherence",
        "caption_scene_coherence",
    ]
    qa = {
        "schema_version": "2",
        "slot_id": slot_id,
        "date": date_str,
        "media_type": "video",
        "reviewed_by": "test-fixture",
        "reviewed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checklist": {k: {"status": "pass", "notes": "fixture"} for k in status_fields},
        "production_scoring": {
            "hook_strength": {"score": "strong", "notes": "fixture"},
            "styling_sexy_platform_safe": {"status": "pass", "notes": "fixture"},
            "outfit_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": "fixture"},
            "scene_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": "fixture"},
        },
        "overall": "pass",
        "failure_reasons": [],
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "publish_ready": True,
        "publish_ready_reason": "fixture",
    }
    out_path = asset_review_root / date_str / f"{slot_id}_qa.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(qa, indent=2), encoding="utf-8")


def _write_video_workorder(workorder_root: Path, date_str: str, slot_id: str, video_path: Path) -> None:
    manifest = {
        "date": date_str,
        "slots": [
            {
                "slot_id": slot_id,
                "caption": "the light stayed on for us\n\n#test",
                "activity": "test activity",
                "pose": "test pose",
                "visual_style": "test visual style",
                "expected_assets": {"video_path": str(video_path)},
                "metadata": {
                    "avatar_nickname": "Lena",
                    "video_prompt": "a real test video prompt",
                    "lane": "test_lane",
                },
            }
        ],
    }
    out_path = workorder_root / date_str / "daily_workorders.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


@requires_ffmpeg
def test_full_video_publish_chain_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-chain-video"

    # Isolate every module-level path constant this chain touches -- never
    # the real repo's pipeline/kling_workorders/, pipeline/asset_review/, or
    # pipeline/queue/.
    workorder_root = tmp_path / "kling_workorders"
    asset_review_root = tmp_path / "asset_review" / "lena"
    packet_out_dir = tmp_path / "publish_packets"
    queue_root = tmp_path / "live_queue"
    monkeypatch.setattr(packet_mod, "WORKORDER_ROOT", workorder_root)
    monkeypatch.setattr(lena_photo_qa, "ASSET_REVIEW_ROOT", asset_review_root)

    # --- 0. Real local video fixture, plus its untouched-baseline hash ---
    video_path = _make_test_video(tmp_path / "assets" / "chain_clip.mp4", duration=3.0, width=640, height=1136)
    import hashlib
    source_sha_before = hashlib.sha256(video_path.read_bytes()).hexdigest()

    _write_video_workorder(workorder_root, date_str, slot_id, video_path)
    _write_qa_pass(asset_review_root, date_str, slot_id)

    # --- 1/2. resolve_packet_inputs_video() ---
    resolved = resolve_packet_inputs_video(date_str, slot_id, packet_out_dir)
    assert resolved["media_kind"] == "video"
    assert resolved["video_path"] == str(video_path)
    assert resolved["duration_seconds"] == pytest.approx(3.0, abs=0.3)
    assert resolved["width"] == 640
    assert resolved["height"] == 1136
    assert resolved["slot_id"] == slot_id
    assert resolved["date"] == date_str

    # --- 3. build_queue_draft() ---
    packet_output_path = write_packet(resolved, packet_out_dir, force=False)
    draft = build_queue_draft(resolved, packet_output_path)
    assert draft["media_type"] == "video"
    assert draft["media_path"] == str(video_path)  # raw source, pre-promotion
    assert draft["metadata"]["video_prompt"] == "a real test video prompt"
    assert draft["metadata"]["duration_seconds"] == pytest.approx(3.0, abs=0.3)
    assert draft["metadata"]["width"] == 640
    assert draft["metadata"]["height"] == 1136
    assert draft["metadata"]["source_slot_id"] == slot_id
    assert draft["metadata"]["source_date"] == date_str
    assert draft["metadata"]["queue_draft_only"] is True
    assert draft["approved_for_live_publish"] is False

    queue_draft_path = write_queue_draft(resolved, packet_output_path, packet_out_dir, force=False)
    assert queue_draft_path.exists()

    # --- 4. record publish approval (real function, no bypass) ---
    approved_caption = "the light stayed on for us\n\n#test"
    approval_summary = check_publish_approval(
        date_str, slot_id,
        approved_caption=approved_caption,
        approved_by="test-operator",
        caption_confirm=REQUIRED_CAPTION_CONFIRM_PHRASE,
        platforms=["instagram"],
        out_dir=packet_out_dir,
        queue_draft_path_override=None,
        provider="video",
        live_publish_confirm=REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE,
    )
    approval_path = write_approval_record(approval_summary, force=False)
    assert approval_path.exists()

    # --- 5. apply publish approval (real function, no bypass) ---
    apply_summary = check_apply_publish_approval(date_str, slot_id, packet_out_dir)
    assert apply_summary["would_write"] is True
    applied_path = apply_publish_approval(apply_summary)
    assert applied_path == queue_draft_path
    applied_draft = json.loads(queue_draft_path.read_text(encoding="utf-8"))
    assert applied_draft["caption"] == approved_caption
    # Every other field byte-identical to what build_queue_draft() produced.
    assert applied_draft["media_path"] == str(video_path)
    assert applied_draft["media_type"] == "video"

    # --- 6. clean derivative + real provenance sidecar (existing scrubber) ---
    scrub_video_metadata(video_path)
    clean_path = resolve_clean_output_path(video_path)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    assert clean_path.exists()
    assert sidecar_path.exists()
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["verified_clean_after_scrub"] is True

    # --- 7/8. promotion re-validates everything and succeeds ---
    checked = check_promote_to_queue(
        date_str, slot_id, "video",
        out_dir=packet_out_dir, queue_root=queue_root,
    )
    clean_export_facts = checked["clean_export"]
    assert clean_export_facts["source_path"] == str(video_path)
    assert clean_export_facts["clean_derivative_path"] == str(clean_path)
    assert clean_export_facts["verified_clean_after_scrub"] is True
    assert checked["would_write"] is True

    written_path = promote_to_queue(checked)
    assert written_path is not None
    assert written_path == queue_root / f"{slot_id}.json"

    promoted_item = json.loads(written_path.read_text(encoding="utf-8"))

    # --- 9/10. promoted media_path == verified clean derivative, != raw source ---
    assert promoted_item["media_path"] == str(clean_path)
    assert promoted_item["media_path"] != str(video_path)
    assert promoted_item["approved_for_live_publish"] is True
    assert promoted_item["operator_review_required"] is False

    # --- 11. raw source path/hash preserved separately as provenance ---
    assert promoted_item["metadata"]["source_asset_path"] == str(video_path)
    assert promoted_item["metadata"]["source_asset_sha256"] == source_sha_before
    assert promoted_item["metadata"]["clean_export_verified"] is True

    # --- 13. raw source remains byte-identical after the entire chain ---
    source_sha_after = hashlib.sha256(video_path.read_bytes()).hexdigest()
    assert source_sha_after == source_sha_before

    # --- 14. no real repo artifact touched ---
    # WORKORDER_ROOT/ASSET_REVIEW_ROOT were monkeypatched to tmp_path for the
    # whole test, so nothing was ever written under the real
    # pipeline/kling_workorders/ or pipeline/asset_review/ trees. The one
    # path this chain could plausibly reach in the real repo is the real
    # live queue -- explicitly confirmed untouched (queue_root above was
    # always the isolated tmp directory, never LIVE_QUEUE_ROOT).
    real_queue_item = Path(packet_mod.ROOT) / "pipeline" / "queue" / f"{slot_id}.json"
    assert not real_queue_item.exists()
