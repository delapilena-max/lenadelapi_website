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
