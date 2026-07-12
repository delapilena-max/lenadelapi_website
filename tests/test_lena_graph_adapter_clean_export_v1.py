from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tools.lena_scrub_media_metadata_v1 import resolve_clean_output_path, scrub_image_metadata
from pipeline.publisher.instagram_graph_adapter import (
    InstagramPublishError,
    _validate_clean_export_before_publish,
    build_container_creation_request,
    publish_post,
    wait_for_container_if_needed,
)

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")


def _make_source_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(90, 100, 110)).save(path, format="PNG")
    return path


def _make_clean_pair(tmp_path: Path, name: str = "asset_seed.png") -> Path:
    source = _make_source_png(tmp_path / name)
    scrub_image_metadata(source)
    return source


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


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


def _valid_payload(source: Path) -> dict:
    clean_path = resolve_clean_output_path(source)
    return {
        "post_id": "test_post",
        "media_type": "photo",
        "caption": "a caption",
        "media_path": str(clean_path),
        "metadata": {
            "clean_export_verified": True,
            "source_asset_path": str(source),
            "source_asset_sha256": _sha(source),
            "clean_export_derivative_sha256": _sha(clean_path),
        },
    }


# 1. verified clean derivative passes
def test_verified_clean_derivative_passes(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path)
    payload = _valid_payload(source)
    _validate_clean_export_before_publish(payload)  # must not raise


# 2. raw source rejects
def test_media_path_as_raw_source_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "raw_source_reject.png")
    payload = _valid_payload(source)
    payload["media_path"] = str(source)
    with pytest.raises(InstagramPublishError, match="does not equal the independently"):
        _validate_clean_export_before_publish(payload)


# 3. unrelated decoy path rejects
def test_media_path_decoy_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "decoy_reject.png")
    payload = _valid_payload(source)
    decoy = tmp_path / "decoy.png"
    Image.new("RGB", (2, 2)).save(decoy, format="PNG")
    payload["media_path"] = str(decoy)
    with pytest.raises(InstagramPublishError, match="does not equal the independently"):
        _validate_clean_export_before_publish(payload)


# 4. missing derivative rejects
def test_missing_derivative_rejects(tmp_path: Path) -> None:
    source = _make_source_png(tmp_path / "no_derivative.png")  # scrubber never run
    clean_path = resolve_clean_output_path(source)
    payload = {
        "media_path": str(clean_path),
        "metadata": {"source_asset_path": str(source)},
    }
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 5. missing sidecar rejects
def test_missing_sidecar_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "missing_sidecar.png")
    clean_path = resolve_clean_output_path(source)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    sidecar_path.unlink()
    payload = _valid_payload(source)
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 6. derivative hash tampering rejects
def test_derivative_tampering_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "tampered_derivative.png")
    payload = _valid_payload(source)
    clean_path = resolve_clean_output_path(source)
    with clean_path.open("ab") as fh:
        fh.write(b"\x00tampered")
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 7. source hash tampering rejects
def test_source_tampering_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "tampered_source.png")
    payload = _valid_payload(source)
    with source.open("ab") as fh:
        fh.write(b"\x00tampered")
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 8. sidecar hash mismatch rejects
def test_sidecar_hash_mismatch_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "sidecar_mismatch.png")
    clean_path = resolve_clean_output_path(source)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["output_sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    payload = _valid_payload(source)
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 9. verified_clean_after_scrub false rejects
def test_verified_clean_after_scrub_false_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "not_verified.png")
    clean_path = resolve_clean_output_path(source)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["verified_clean_after_scrub"] = False
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    payload = _valid_payload(source)
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 10. truthy-but-not-literal-True rejects
def test_verified_clean_after_scrub_truthy_not_true_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "truthy_not_true.png")
    clean_path = resolve_clean_output_path(source)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["verified_clean_after_scrub"] = 1
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    payload = _valid_payload(source)
    with pytest.raises(InstagramPublishError, match="clean-export verification failed"):
        _validate_clean_export_before_publish(payload)


# 11. historical pre-contract payload rejects
def test_historical_pre_contract_payload_rejects(tmp_path: Path) -> None:
    """A payload shaped exactly like tools/instagram_publish_smoke.py's real
    current payload -- public_media_url only, no media_path, no metadata at
    all -- must reject, never silently proceed to construct a Meta request."""
    payload = {
        "post_id": "instagram_smoke_test",
        "media_type": "photo",
        "caption": "Test post from Lena automation.",
        "public_media_url": "https://example.com/whatever.jpg",
        "platforms": ["instagram"],
    }
    with pytest.raises(InstagramPublishError, match="source_asset_path is missing"):
        _validate_clean_export_before_publish(payload)


# 12. direct Graph-adapter call without valid clean-export proof rejects
def test_direct_publish_post_call_without_proof_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulates exactly the real bypass this slice closes: a direct call to
    publish_post() (as tools/instagram_publish_smoke.py performs), with no
    clean-export proof at all. Must reject before any env var is even
    required, and therefore before any network call could occur."""
    monkeypatch.delenv("INSTAGRAM_GRAPH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_GRAPH_USER_ID", raising=False)
    monkeypatch.delenv("META_IG_USER_ID", raising=False)

    payload = {
        "post_id": "smoke_test_bypass_attempt",
        "media_type": "photo",
        "caption": "attempted bypass",
        "public_media_url": "https://example.com/raw_unverified.jpg",
        "platforms": ["instagram"],
    }
    with pytest.raises(InstagramPublishError, match="clean-export verification failed|source_asset_path is missing"):
        publish_post(payload)


# 13. no raw-source fallback occurs
def test_no_fallback_to_raw_source_on_any_failure(tmp_path: Path) -> None:
    source = _make_source_png(tmp_path / "no_fallback.png")  # no derivative at all
    payload = {
        "media_path": str(source),  # deliberately the raw source itself
        "metadata": {"source_asset_path": str(source)},
    }
    with pytest.raises(InstagramPublishError):
        _validate_clean_export_before_publish(payload)


# 14. canonical bridge path still passes with valid clean-export proof
def test_valid_payload_passes_gate_and_reaches_next_real_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves the gate does not falsely reject a genuinely valid payload: a
    real, verified clean-export payload must pass _validate_clean_export_
    before_publish() and let publish_post() proceed to its next real check
    (the required env vars) -- proven by asserting the raised error is the
    *env var* error, never a clean-export error, and confirming this without
    ever making a network call."""
    monkeypatch.delenv("INSTAGRAM_GRAPH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_GRAPH_USER_ID", raising=False)
    monkeypatch.delenv("META_IG_USER_ID", raising=False)

    source = _make_clean_pair(tmp_path, "passes_gate.png")
    payload = _valid_payload(source)

    with pytest.raises(InstagramPublishError, match="missing required environment variable"):
        publish_post(payload)


@requires_ffmpeg
def test_build_container_request_reel_uses_video_url_without_share_to_feed(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "reel.mp4", duration=2.0)
    request = build_container_creation_request(
        media_url="https://example.com/reel.mp4",
        media_type="reel",
        caption="caption",
        media_path=video_path,
    )
    assert request["video_url"] == "https://example.com/reel.mp4"
    assert request["media_type"] == "REELS"
    assert "image_url" not in request
    assert "share_to_feed" not in request


@requires_ffmpeg
def test_build_container_request_story_video_uses_video_url_and_stories(tmp_path: Path) -> None:
    video_path = _make_test_video(tmp_path / "story.mp4", duration=2.0)
    request = build_container_creation_request(
        media_url="https://example.com/story.mp4",
        media_type="story",
        caption="caption",
        media_path=video_path,
    )
    assert request["video_url"] == "https://example.com/story.mp4"
    assert request["media_type"] == "STORIES"
    assert "image_url" not in request


@requires_ffmpeg
def test_build_container_request_story_video_without_audio_rejects(tmp_path: Path) -> None:
    video_path = tmp_path / "silent_story.mp4"
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=640x1136:rate=24",
            "-t", "2",
            "-c:v", "libx264",
            str(video_path),
        ],
        check=True, capture_output=True, timeout=60,
    )
    with pytest.raises(InstagramPublishError, match="no audio stream"):
        build_container_creation_request(
            media_url="https://example.com/silent_story.mp4",
            media_type="story",
            caption="caption",
            media_path=video_path,
        )


def test_wait_for_container_polls_video_story(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter([
        {"status_code": "IN_PROGRESS"},
        {"status_code": "FINISHED"},
    ])
    monkeypatch.setattr(
        "pipeline.publisher.instagram_graph_adapter.get_container_status",
        lambda **kwargs: next(states),
    )
    monkeypatch.setattr("pipeline.publisher.instagram_graph_adapter.time.sleep", lambda *_args, **_kwargs: None)
    result = wait_for_container_if_needed(
        creation_id="123",
        access_token="token",
        media_type="story",
        creation_request={"video_url": "https://example.com/story.mp4", "media_type": "STORIES"},
    )
    assert result["status_code"] == "FINISHED"


# 15. no network call occurs during tests -- structural guarantee, not just
# an assertion: `requests` is never monkeypatched to a fake in this file,
# so if any test above ever reached a real requests.request() call it would
# raise a connection error (a different, visible failure), not silently
# succeed. Every test above either raises before reaching that point or
# (test 14) is proven to stop at the env-var check, one step before any
# network code path.
