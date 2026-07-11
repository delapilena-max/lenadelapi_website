from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.lena_scrub_media_metadata_v1 import resolve_clean_output_path, scrub_video_metadata
from tools.lena_promote_to_queue_v1 import (
    PromoteError,
    _validate_queue_draft,
)
from pipeline.publisher.instagram_queue_bridge import (
    INSTAGRAM_REEL_MAX_DURATION_SECONDS,
    _validate_contract,
)

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")


def _make_test_video(path: Path, duration: float = 3.0, width: int = 640, height: int = 1136) -> Path:
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


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _valid_video_queue_draft(video_path: Path) -> dict:
    return {
        "post_id": "test-video-slot",
        "slot_id": "test-video-slot",
        "media_path": str(video_path),
        "media_type": "video",
        "platforms": ["instagram"],
        "caption": "approved caption #test",
        "approved_for_live_publish": False,
        "operator_review_required": True,
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "activity": "test activity",
            "pose": "test pose",
            "visual_style": "test visual style",
            "queue_draft_only": True,
        },
    }


# 8. Promotion accepts valid video.
# 9. Promotion accepts valid reel.
@pytest.mark.parametrize("media_type", ["video", "reel"])
def test_validate_queue_draft_accepts_video_reel(tmp_path: Path, media_type: str) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"not a real video, path existence only")

    draft = _valid_video_queue_draft(video_path)
    draft["media_type"] = media_type
    # _validate_queue_draft() itself does not require the file to be a real
    # decodable video (that is the clean-export/bridge layer's job) -- only
    # that it exists and the metadata contract fields are present.
    _validate_queue_draft(draft, "test-video-slot", "video", "approved caption #test", 1)  # must not raise


# 10. Promotion still rejects unsupported media types.
def test_validate_queue_draft_rejects_unsupported_media_type(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"x")
    draft = _valid_video_queue_draft(video_path)
    draft["media_type"] = "carousel"  # never supported
    with pytest.raises(PromoteError, match="not supported"):
        _validate_queue_draft(draft, "test-video-slot", "video", "approved caption #test", 1)


def test_validate_queue_draft_video_requires_video_prompt(tmp_path: Path) -> None:
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"x")
    draft = _valid_video_queue_draft(video_path)
    del draft["metadata"]["video_prompt"]
    with pytest.raises(PromoteError, match="video_prompt"):
        _validate_queue_draft(draft, "test-video-slot", "video", "approved caption #test", 1)


def test_validate_queue_draft_video_does_not_require_image_engine(tmp_path: Path) -> None:
    """Confirms the video branch never requires image_engine/image_prompt/
    activity/pose/visual_style/resolution the way the photo branch does --
    only avatar_nickname and video_prompt."""
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"x")
    draft = _valid_video_queue_draft(video_path)
    del draft["metadata"]["activity"]
    del draft["metadata"]["pose"]
    del draft["metadata"]["visual_style"]
    _validate_queue_draft(draft, "test-video-slot", "video", "approved caption #test", 1)  # must not raise


# 11. Bridge video/reel branch accepts a correctly shaped provider-neutral payload.
@requires_ffmpeg
def test_bridge_accepts_provider_neutral_video_payload(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "clip.mp4", duration=3.0)
    scrub_video_metadata(video_path)
    clean_path = resolve_clean_output_path(video_path)

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "video",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
            "source_asset_sha256": _sha(video_path),
            "clean_export_derivative_sha256": _sha(clean_path),
        },
    }
    _validate_contract(payload)  # must not raise


# 12. Bridge no longer requires legacy Kling-specific engine identifiers.
@requires_ffmpeg
def test_bridge_no_longer_requires_kling_fields(tmp_path: Path) -> None:
    """A provider-neutral video payload with NO seed_image_path,
    seed_image_engine, video_engine, motion_control, fps, or resolution
    field at all must still pass -- these were the legacy Kling-coupled
    requirements this slice removed."""
    video_path = _make_test_video(tmp_path / "clip2.mp4", duration=2.5)
    scrub_video_metadata(video_path)
    clean_path = resolve_clean_output_path(video_path)

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "reel",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
            "source_asset_sha256": _sha(video_path),
            "clean_export_derivative_sha256": _sha(clean_path),
        },
    }
    assert "seed_image_path" not in payload["metadata"]
    assert "video_engine" not in payload["metadata"]
    assert "motion_control" not in payload["metadata"]
    _validate_contract(payload)  # must not raise despite the absence of all legacy fields


# 13. Historical 7-second provider-coupled assumption is no longer the active Reel policy source.
def test_duration_policy_no_longer_kling_coupled() -> None:
    """The historical ceiling was read from pipeline/config/
    lena_kling_contract.json's max_video_duration_seconds (7). The new
    policy owner is the provider-neutral INSTAGRAM_REEL_MAX_DURATION_SECONDS
    constant in instagram_queue_bridge.py itself, deliberately None (no
    real Instagram Reels limit has been confirmed/authorized yet -- see
    the constant's own docstring)."""
    assert INSTAGRAM_REEL_MAX_DURATION_SECONDS is None


@requires_ffmpeg
def test_bridge_accepts_video_longer_than_legacy_seven_second_cap(tmp_path: Path) -> None:
    """A real, 10-second video (longer than the old 7s Kling cap) must pass
    the bridge's video branch now that duration is not upper-bounded by an
    unconfirmed policy value."""
    video_path = _make_test_video(tmp_path / "long_clip.mp4", duration=10.0)
    scrub_video_metadata(video_path)
    clean_path = resolve_clean_output_path(video_path)

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "video",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
            "source_asset_sha256": _sha(video_path),
            "clean_export_derivative_sha256": _sha(clean_path),
        },
    }
    _validate_contract(payload)  # must not raise -- 10s > legacy 7s cap, correctly no longer enforced


# 14. Verified clean MP4 path passes clean-export re-verification.
@requires_ffmpeg
def test_clean_export_video_verifies(tmp_path: Path) -> None:
    from tools.lena_verify_clean_export_v1 import verify_clean_export

    video_path = _make_test_video(tmp_path / "clip3.mp4", duration=2.0)
    scrub_video_metadata(video_path)
    facts = verify_clean_export(video_path)
    assert facts["verified_clean_after_scrub"] is True


# 15. Raw MP4 source cannot be used as publish media.
@requires_ffmpeg
def test_raw_video_source_cannot_publish(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "clip4.mp4", duration=2.0)
    scrub_video_metadata(video_path)

    payload = {
        "platforms": ["instagram"],
        "media_path": str(video_path),  # deliberately the raw source, not the clean derivative
        "media_type": "video",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
        },
    }
    with pytest.raises(ValueError):
        _validate_contract(payload)


# 16. Tampered clean MP4 rejects.
@requires_ffmpeg
def test_tampered_clean_video_rejects(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "clip5.mp4", duration=2.0)
    scrub_video_metadata(video_path)
    clean_path = resolve_clean_output_path(video_path)
    with clean_path.open("ab") as fh:
        fh.write(b"\x00tampered")

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "video",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
        },
    }
    with pytest.raises(ValueError):
        _validate_contract(payload)


# 17. Missing video derivative rejects.
@requires_ffmpeg
def test_missing_video_derivative_rejects(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "clip6.mp4", duration=2.0)  # scrubber never run
    clean_path = resolve_clean_output_path(video_path)

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "video",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
        },
    }
    with pytest.raises(ValueError):
        _validate_contract(payload)


# 18. Missing sidecar rejects.
@requires_ffmpeg
def test_missing_video_sidecar_rejects(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "clip7.mp4", duration=2.0)
    scrub_video_metadata(video_path)
    clean_path = resolve_clean_output_path(video_path)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    sidecar_path.unlink()

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "video",
        "caption": "a real caption #test",
        "metadata": {
            "avatar_nickname": "Lena",
            "video_prompt": "a real test video prompt",
            "clean_export_verified": True,
            "source_asset_path": str(video_path),
        },
    }
    with pytest.raises(ValueError):
        _validate_contract(payload)
