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
    ResolveError,
    build_queue_draft,
    resolve_packet_inputs,
    resolve_packet_inputs_video,
)

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")


def _make_test_video(path: Path, duration: float = 3.0, width: int = 640, height: int = 1136) -> Path:
    """Creates a tiny, synthetic, silent-audio local MP4 test fixture via
    ffmpeg's lavfi testsrc/anullsrc generators -- not an AI-generated or
    provider-rendered asset, purely a deterministic isolated test fixture
    (same category as the PIL.Image.new(...) PNG fixtures already used by
    the clean-export test suite)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=24",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True, capture_output=True, timeout=60,
    )
    return path


def _write_qa_pass(asset_review_root: Path, date_str: str, slot_id: str) -> None:
    """Minimal, real, schema_version=2 (legacy-exempt from newer
    hard-gating fields, e.g. pose_action_scene_compliance) all-pass QA
    record, shaped like a real repo QA artifact (see
    pipeline/asset_review/lena/2026-07-05/2026-07-05-01-photo_qa.json)."""
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


def _write_photo_workorder(workorder_root: Path, date_str: str, slot_id: str, image_path: Path) -> None:
    manifest = {
        "date": date_str,
        "slots": [
            {
                "slot_id": slot_id,
                "caption": "test caption\n\n#test",
                "activity": "test activity",
                "pose": "test pose",
                "visual_style": "test visual style",
                "expected_assets": {"seed_image_path": str(image_path)},
                "metadata": {
                    "avatar_nickname": "Lena",
                    "image_engine": "kling_image_3.0",
                    "image_prompt": "a real test prompt",
                },
            }
        ],
    }
    out_path = workorder_root / date_str / "daily_workorders.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_video_workorder(workorder_root: Path, date_str: str, slot_id: str, video_path: Path) -> None:
    manifest = {
        "date": date_str,
        "slots": [
            {
                "slot_id": slot_id,
                "caption": "test video caption\n\n#test",
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


@pytest.fixture
def isolated_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirects the resolver's workorder-manifest root and the QA module's
    asset-review root at isolated tmp_path directories -- never touches any
    real repo path. Both are module-level constants in production code
    (not parameterized per-call), so monkeypatching is the correct,
    standard isolation mechanism here."""
    workorder_root = tmp_path / "kling_workorders"
    asset_review_root = tmp_path / "asset_review" / "lena"
    monkeypatch.setattr(packet_mod, "WORKORDER_ROOT", workorder_root)
    monkeypatch.setattr(lena_photo_qa, "ASSET_REVIEW_ROOT", asset_review_root)
    return {"workorder_root": workorder_root, "asset_review_root": asset_review_root}


# 1. Existing photo resolution still works unchanged.
def test_photo_resolution_unchanged(tmp_path: Path, isolated_roots) -> None:
    from PIL import Image

    date_str = "2026-07-11"
    slot_id = "2026-07-11-01-photo"
    image_path = tmp_path / "assets" / "seed.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(image_path, format="PNG")

    _write_photo_workorder(isolated_roots["workorder_root"], date_str, slot_id, image_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs(date_str, slot_id)
    assert resolved["image_path"] == str(image_path)
    assert resolved.get("media_kind") is None
    assert "video_path" not in resolved


# 2. Real local MP4 fixture resolves as video.
# 3. Video resolution captures path.
@requires_ffmpeg
def test_video_resolution_captures_path(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-01-video"
    video_path = _make_test_video(tmp_path / "assets" / "clip.mp4", duration=3.0, width=640, height=1136)

    _write_video_workorder(isolated_roots["workorder_root"], date_str, slot_id, video_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_video(date_str, slot_id)
    assert resolved["media_kind"] == "video"
    assert resolved["video_path"] == str(video_path)


# 4. Video resolution captures duration.
@requires_ffmpeg
def test_video_resolution_captures_duration(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-02-video"
    video_path = _make_test_video(tmp_path / "assets" / "clip2.mp4", duration=4.0, width=640, height=1136)

    _write_video_workorder(isolated_roots["workorder_root"], date_str, slot_id, video_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_video(date_str, slot_id)
    assert resolved["duration_seconds"] == pytest.approx(4.0, abs=0.3)


# 5. Video resolution captures dimensions.
@requires_ffmpeg
def test_video_resolution_captures_dimensions(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-03-video"
    video_path = _make_test_video(tmp_path / "assets" / "clip3.mp4", duration=2.0, width=576, height=1024)

    _write_video_workorder(isolated_roots["workorder_root"], date_str, slot_id, video_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_video(date_str, slot_id)
    assert resolved["width"] == 576
    assert resolved["height"] == 1024
    assert resolved["aspect_ratio"] == pytest.approx(576 / 1024, abs=0.001)


def test_video_resolution_requires_video_prompt(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-04-video"
    video_path = _make_test_video(tmp_path / "assets" / "clip4.mp4") if FFMPEG else tmp_path / "assets" / "clip4.mp4"
    if not FFMPEG:
        pytest.skip("ffmpeg not available")

    manifest = {
        "date": date_str,
        "slots": [{
            "slot_id": slot_id,
            "expected_assets": {"video_path": str(video_path)},
            "metadata": {"avatar_nickname": "Lena"},  # missing video_prompt
        }],
    }
    out_path = isolated_roots["workorder_root"] / date_str / "daily_workorders.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest), encoding="utf-8")
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    with pytest.raises(ResolveError, match="video_prompt"):
        resolve_packet_inputs_video(date_str, slot_id)


# 6. build_queue_draft() still emits photo for a photo asset.
def test_build_queue_draft_still_emits_photo(tmp_path: Path, isolated_roots) -> None:
    from PIL import Image

    date_str = "2026-07-11"
    slot_id = "2026-07-11-05-photo"
    image_path = tmp_path / "assets" / "seed2.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(image_path, format="PNG")

    _write_photo_workorder(isolated_roots["workorder_root"], date_str, slot_id, image_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs(date_str, slot_id)
    draft = build_queue_draft(resolved, Path("dummy_packet.md"))
    assert draft["media_type"] == "photo"
    assert draft["media_path"] == str(image_path)
    assert "image_engine" in draft["metadata"]
    assert "video_prompt" not in draft["metadata"]


# 7. build_queue_draft() emits video/reel correctly for a video asset.
@requires_ffmpeg
def test_build_queue_draft_emits_video(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-06-video"
    video_path = _make_test_video(tmp_path / "assets" / "clip6.mp4", duration=3.0, width=640, height=1136)

    _write_video_workorder(isolated_roots["workorder_root"], date_str, slot_id, video_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_video(date_str, slot_id)
    draft = build_queue_draft(resolved, Path("dummy_packet.md"))
    assert draft["media_type"] == "video"
    assert draft["media_path"] == str(video_path)
    assert draft["metadata"]["video_prompt"] == "a real test video prompt"
    assert "image_engine" not in draft["metadata"]
    assert draft["metadata"]["duration_seconds"] == pytest.approx(3.0, abs=0.3)
    assert draft["metadata"]["width"] == 640
    assert draft["metadata"]["height"] == 1136


# --- pose_body_language_id / expression_gaze_id forwarding (2026-07-11) ----
#
# Photo (Kling-workorder-shaped) and video paths both read these two IDs
# only from the real workorder slot's own metadata -- never from the
# free-text `pose` field, never from image_prompt/video_prompt. Historical
# workorders (every real one on disk today) genuinely lack both fields;
# that must remain a clean, non-fabricated None, not a hard-fail.

def _write_photo_workorder_with_provenance(
    workorder_root: Path,
    date_str: str,
    slot_id: str,
    image_path: Path,
    pose_body_language_id=None,
    expression_gaze_id=None,
) -> None:
    metadata = {
        "avatar_nickname": "Lena",
        "image_engine": "kling_image_3.0",
        "image_prompt": "a real test prompt mentioning weight_shift_one_hip pose casually",
    }
    if pose_body_language_id is not None:
        metadata["pose_body_language_id"] = pose_body_language_id
    if expression_gaze_id is not None:
        metadata["expression_gaze_id"] = expression_gaze_id
    manifest = {
        "date": date_str,
        "slots": [
            {
                "slot_id": slot_id,
                "caption": "test caption\n\n#test",
                "activity": "test activity",
                # Deliberately contains text that overlaps a real pose/expression
                # ID's label, to prove forwarding never parses this field.
                "pose": "weight shift onto one hip, closed mouth smile direct",
                "visual_style": "test visual style",
                "expected_assets": {"seed_image_path": str(image_path)},
                "metadata": metadata,
            }
        ],
    }
    out_path = workorder_root / date_str / "daily_workorders.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# 9. pose_body_language_id is forwarded (photo/Kling-shaped path) when present.
# 10. expression_gaze_id is forwarded (photo/Kling-shaped path) when present.
# 11. Both exact values survive into resolve_packet_inputs()'s output.
def test_photo_resolution_forwards_pose_and_expression_ids_when_present(tmp_path: Path, isolated_roots) -> None:
    from PIL import Image

    date_str = "2026-07-11"
    slot_id = "2026-07-11-07-photo"
    image_path = tmp_path / "assets" / "seed7.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(image_path, format="PNG")

    _write_photo_workorder_with_provenance(
        isolated_roots["workorder_root"], date_str, slot_id, image_path,
        pose_body_language_id="pose_p001", expression_gaze_id="exp_g001",
    )
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs(date_str, slot_id)
    assert resolved["pose_body_language_id"] == "pose_p001"
    assert resolved["expression_gaze_id"] == "exp_g001"


# 4/5/8. Missing fields remain genuinely None -- historical workorders
# (every real one on disk today) build successfully without either field.
def test_photo_resolution_leaves_pose_and_expression_ids_none_when_absent(tmp_path: Path, isolated_roots) -> None:
    from PIL import Image

    date_str = "2026-07-11"
    slot_id = "2026-07-11-08-photo"
    image_path = tmp_path / "assets" / "seed8.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(image_path, format="PNG")

    # Uses the pre-existing helper -- its workorder has no
    # pose_body_language_id/expression_gaze_id at all, matching every real
    # historical workorder in the repo today.
    _write_photo_workorder(isolated_roots["workorder_root"], date_str, slot_id, image_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs(date_str, slot_id)
    assert resolved["pose_body_language_id"] is None
    assert resolved["expression_gaze_id"] is None
    # Historical compatibility: build_queue_draft() still succeeds and the
    # keys are absent entirely from metadata, never written as None/"".
    draft = build_queue_draft(resolved, Path("dummy_packet.md"))
    assert "pose_body_language_id" not in draft["metadata"]
    assert "expression_gaze_id" not in draft["metadata"]


# 6/7. No inference from the free-text pose field or image_prompt, even
# when that text happens to overlap a real pose/expression label.
def test_photo_resolution_never_infers_ids_from_pose_text_or_prompt(tmp_path: Path, isolated_roots) -> None:
    from PIL import Image

    date_str = "2026-07-11"
    slot_id = "2026-07-11-09-photo"
    image_path = tmp_path / "assets" / "seed9.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(image_path, format="PNG")

    # No pose_body_language_id/expression_gaze_id passed -- but the
    # free-text `pose` field and image_prompt (set inside the helper)
    # deliberately contain real pose/expression label text.
    _write_photo_workorder_with_provenance(
        isolated_roots["workorder_root"], date_str, slot_id, image_path,
    )
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs(date_str, slot_id)
    assert resolved["pose"] == "weight shift onto one hip, closed mouth smile direct"
    assert resolved["pose_body_language_id"] is None
    assert resolved["expression_gaze_id"] is None


# 2/3/11. expression_gaze_id/pose_body_language_id forwarded on the video
# path when present, and both exact values survive into build_queue_draft().
@requires_ffmpeg
def test_video_resolution_forwards_and_preserves_pose_and_expression_ids(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-11"
    slot_id = "2026-07-11-10-video"
    video_path = _make_test_video(tmp_path / "assets" / "clip10.mp4", duration=3.0, width=640, height=1136)

    manifest = {
        "date": date_str,
        "slots": [{
            "slot_id": slot_id,
            "caption": "test video caption\n\n#test",
            "activity": "test activity",
            "pose": "test pose text",
            "visual_style": "test visual style",
            "expected_assets": {"video_path": str(video_path)},
            "metadata": {
                "avatar_nickname": "Lena",
                "video_prompt": "a real test video prompt",
                "lane": "test_lane",
                "pose_body_language_id": "pose_p001",
                "expression_gaze_id": "exp_g001",
            },
        }],
    }
    out_path = isolated_roots["workorder_root"] / date_str / "daily_workorders.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_video(date_str, slot_id)
    assert resolved["pose_body_language_id"] == "pose_p001"
    assert resolved["expression_gaze_id"] == "exp_g001"

    draft = build_queue_draft(resolved, Path("dummy_packet.md"))
    assert draft["metadata"]["pose_body_language_id"] == "pose_p001"
    assert draft["metadata"]["expression_gaze_id"] == "exp_g001"


# 9/10/11/12/13. build_queue_draft() (photo path) preserves the two new
# fields exactly, and every pre-existing identity/creative field
# (wardrobe_outfit_id N/A here since not set by this fixture; source_slot_id,
# slot_id, post_id, activity, media_type) remains unchanged.
def test_build_queue_draft_photo_preserves_pose_and_expression_ids_and_existing_identity(tmp_path: Path, isolated_roots) -> None:
    from PIL import Image

    date_str = "2026-07-11"
    slot_id = "2026-07-11-11-photo"
    image_path = tmp_path / "assets" / "seed11.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(image_path, format="PNG")

    _write_photo_workorder_with_provenance(
        isolated_roots["workorder_root"], date_str, slot_id, image_path,
        pose_body_language_id="pose_p001", expression_gaze_id="exp_g001",
    )
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs(date_str, slot_id)
    draft = build_queue_draft(resolved, Path("dummy_packet.md"))

    assert draft["metadata"]["pose_body_language_id"] == "pose_p001"
    assert draft["metadata"]["expression_gaze_id"] == "exp_g001"
    # Pre-existing identity/creative fields unchanged by this slice.
    assert draft["slot_id"] == slot_id
    assert draft["post_id"] == slot_id
    assert draft["metadata"]["source_slot_id"] == slot_id
    assert draft["metadata"]["activity"] == "test activity"
    assert draft["media_type"] == "photo"
