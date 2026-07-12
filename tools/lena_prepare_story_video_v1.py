from __future__ import annotations

# Lena short-form music-backed video preparation -- composes an approved
# 9:16 image master with a deterministically-selected approved audio track
# into one 20-second MP4 asset with a real audio stream. The publishing
# layer may later route that SAME validated asset explicitly as either an
# Instagram Reel or an Instagram Story.
#
# Reuses tools/lena_music_pool_v1.py for eligibility/selection (never
# duplicates that logic). Never downloads music, never calls any
# provider/network surface, never mutates the source image or the source
# audio file -- both are only ever opened for reading.
#
# Composition, entirely local and deterministic via ffmpeg:
#   - the source image is looped as video frames for exactly 20 seconds,
#     at its own native pixel dimensions (no resize, no crop -- the source
#     is already 9:16, so no transformation is needed to reach a 9:16
#     output)
#   - the selected track's audio is muxed in, trimmed to the same 20
#     seconds (the track must already be >= 20s; this tool fails closed
#     rather than loop a short track)
#
# Run:
#   python tools/lena_prepare_story_video_v1.py --source pipeline/higgsfield_library/lena/2026-07-09/readypack0709-pack007-00-photo_seed.png --slot readypack0709-pack007-00-photo-story

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_music_pool_v1 import (  # noqa: E402
    MusicPoolError,
    check_track_eligibility,
    load_manifest,
    select_track_deterministic,
)

TARGET_DURATION_SECONDS = 20
VIDEO_FPS = 30
# Deterministic audio fade-out (2026-07-10): the raw 20s truncation of an
# eligible track (which is only guaranteed >= 20s, not exactly 20s, and
# never authored to end at that point) cuts off mid-phrase with an audible
# click/pop. Fixed, deterministic fade -- never data-dependent, never
# random -- full volume preserved through most of the clip, fading to
# silence over the final second. Video is never faded, only audio.
FADE_OUT_DURATION_SECONDS = 1.0
FADE_OUT_START_SECONDS = TARGET_DURATION_SECONDS - FADE_OUT_DURATION_SECONDS


class StoryVideoError(Exception):
    """Raised for any hard-fail condition. No file is ever written when
    this is raised."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ffprobe(path: Path) -> Dict[str, Any]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if probe.returncode != 0:
        raise StoryVideoError(f"ffprobe failed on {path}: {probe.stderr.strip()[-2000:]}")
    return json.loads(probe.stdout)


def _find_manifest_track(manifest: Dict[str, Any], track_id: str) -> Optional[Dict[str, Any]]:
    for track in manifest.get("tracks", []):
        if str(track.get("track_id") or "") == track_id:
            return track
    return None


def validate_music_backed_shortform_asset(
    video_path: Path,
    *,
    expected_track_id: Optional[str] = None,
    expected_track_sha256: Optional[str] = None,
    manifest_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only validator for the shared 9:16 short-form asset contract.

    This is intentionally destination-agnostic: the SAME validated MP4 can
    later be routed as a Reel or a Story by the publishing layer. It proves
    the asset itself is a real, approved music-backed short-form video:
    real file on disk, matching provenance sidecar, approved eligible track,
    H.264 video, AAC audio, readable video+audio streams, 9:16 geometry,
    and ~20 second duration.
    """
    resolved_video_path = video_path.resolve()
    if not resolved_video_path.exists():
        raise StoryVideoError(f"short-form video does not exist: {resolved_video_path}")

    provenance_path = resolved_video_path.with_name(resolved_video_path.stem + "_provenance.json")
    if not provenance_path.exists():
        raise StoryVideoError(f"short-form provenance sidecar does not exist: {provenance_path}")

    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise StoryVideoError(f"short-form provenance sidecar failed to parse: {provenance_path}: {exc}") from exc

    if provenance.get("generated_by") != "tools/lena_prepare_story_video_v1.py":
        raise StoryVideoError(
            f"unexpected provenance generator {provenance.get('generated_by')!r} for {resolved_video_path}"
        )
    if Path(str(provenance.get("output_path") or "")).resolve() != resolved_video_path:
        raise StoryVideoError(
            "short-form provenance output_path does not match the actual asset path: "
            f"{provenance.get('output_path')!r} vs {resolved_video_path}"
        )

    actual_video_sha256 = _sha256_file(resolved_video_path)
    if provenance.get("output_sha256") != actual_video_sha256:
        raise StoryVideoError(
            f"short-form video SHA-256 {actual_video_sha256!r} does not match provenance output_sha256 "
            f"{provenance.get('output_sha256')!r}"
        )

    selected_track_id = str(provenance.get("selected_track_id") or "").strip()
    selected_track_sha256 = str(provenance.get("selected_track_sha256") or "").strip()
    if not selected_track_id:
        raise StoryVideoError("short-form provenance is missing selected_track_id")
    if not selected_track_sha256:
        raise StoryVideoError("short-form provenance is missing selected_track_sha256")
    if expected_track_id and selected_track_id != expected_track_id:
        raise StoryVideoError(
            f"short-form asset uses track_id {selected_track_id!r}, expected {expected_track_id!r}"
        )
    if expected_track_sha256 and selected_track_sha256 != expected_track_sha256:
        raise StoryVideoError(
            f"short-form asset uses track SHA-256 {selected_track_sha256!r}, expected {expected_track_sha256!r}"
        )

    manifest = load_manifest(manifest_path)
    manifest_track = _find_manifest_track(manifest, selected_track_id)
    if manifest_track is None:
        raise StoryVideoError(f"selected track_id {selected_track_id!r} is not present in the approved music manifest")
    if str(manifest_track.get("sha256") or "") != selected_track_sha256:
        raise StoryVideoError(
            f"selected track sha256 {selected_track_sha256!r} does not match manifest sha256 "
            f"{manifest_track.get('sha256')!r}"
        )

    reasons = check_track_eligibility(manifest_track)
    if reasons:
        raise StoryVideoError(
            f"selected track {selected_track_id!r} is no longer eligible: " + "; ".join(reasons)
        )

    probe = _ffprobe(resolved_video_path)
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams:
        raise StoryVideoError("short-form asset has no video stream")
    if not audio_streams:
        raise StoryVideoError("short-form asset has no audio stream")

    v0 = video_streams[0]
    a0 = audio_streams[0]
    width = int(v0.get("width") or 0)
    height = int(v0.get("height") or 0)
    if width <= 0 or height <= 0:
        raise StoryVideoError(f"short-form asset has invalid video dimensions {width}x{height}")
    if width * 16 != height * 9:
        raise StoryVideoError(
            f"short-form asset is not exact 9:16: {width}x{height}"
        )

    duration_value = fmt.get("duration")
    if duration_value is None:
        raise StoryVideoError("short-form asset has no measurable duration")
    duration_seconds = float(duration_value)
    if abs(duration_seconds - TARGET_DURATION_SECONDS) > 0.05:
        raise StoryVideoError(
            f"short-form asset duration {duration_seconds:.6f}s is not the required {TARGET_DURATION_SECONDS}s"
        )

    if str(v0.get("codec_name") or "").lower() != "h264":
        raise StoryVideoError(f"short-form asset video codec is not h264: {v0.get('codec_name')!r}")
    if str(a0.get("codec_name") or "").lower() != "aac":
        raise StoryVideoError(f"short-form asset audio codec is not aac: {a0.get('codec_name')!r}")

    return {
        "ok": True,
        "video_path": str(resolved_video_path),
        "provenance_path": str(provenance_path),
        "slot_id": provenance.get("slot_id"),
        "track_id": selected_track_id,
        "track_sha256": selected_track_sha256,
        "video_sha256": actual_video_sha256,
        "duration_seconds": duration_seconds,
        "video_codec": str(v0.get("codec_name") or ""),
        "audio_codec": str(a0.get("codec_name") or ""),
        "width": width,
        "height": height,
        "audio_channels": a0.get("channels"),
        "audio_sample_rate_hz": int(a0["sample_rate"]) if a0.get("sample_rate") else None,
    }


def resolve_story_video_path(source_path: Path) -> Path:
    """Mirrors the same <slot>_seed.png -> <slot>_X convention used by
    tools/lena_prepare_feed_derivative_v1.py's _feed.png sibling -- here,
    <slot>_story.mp4, beside the source image."""
    stem = source_path.stem
    if not stem.endswith("_seed"):
        raise StoryVideoError(
            f"source filename {source_path.name!r} does not follow the expected "
            "<slot>_seed<ext> convention -- refusing to guess an output filename"
        )
    return source_path.with_name(stem[: -len("_seed")] + "_story.mp4")


def build_story_video(
    source_image_path: Path,
    slot_id: str,
    output_path: Optional[Path] = None,
    force: bool = False,
    manifest_path: Optional[Path] = None,
) -> Dict[str, Any]:
    source_image_path = source_image_path.resolve()
    if not source_image_path.exists():
        raise StoryVideoError(f"source image does not exist: {source_image_path}")

    target_path = (output_path or resolve_story_video_path(source_image_path)).resolve()
    if target_path.exists() and not force:
        raise StoryVideoError(f"Story video already exists at {target_path} -- pass force=True/--force to overwrite")

    with Image.open(source_image_path) as im:
        src_w, src_h = im.size
    source_sha256_before = _sha256_file(source_image_path)

    try:
        selected_track = select_track_deterministic(slot_id, manifest_path)
    except MusicPoolError as exc:
        raise StoryVideoError(f"music pool selection failed: {exc}") from exc

    track_path = Path(str(selected_track["local_path"]))
    track_sha256_before = _sha256_file(track_path)
    track_duration = float(selected_track.get("duration_seconds") or 0)
    if track_duration < TARGET_DURATION_SECONDS:
        raise StoryVideoError(
            f"selected track {selected_track.get('filename')!r} is {track_duration:.3f}s, shorter than the "
            f"required {TARGET_DURATION_SECONDS}s -- failing closed rather than looping silently"
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(source_image_path),
        "-i", str(track_path),
        "-t", str(TARGET_DURATION_SECONDS),
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-af", f"afade=t=out:st={FADE_OUT_START_SECONDS}:d={FADE_OUT_DURATION_SECONDS}",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(target_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise StoryVideoError(f"ffmpeg composition failed: {result.stderr.strip()[-3000:]}")

    source_sha256_after = _sha256_file(source_image_path)
    track_sha256_after = _sha256_file(track_path)
    if source_sha256_after != source_sha256_before:
        raise StoryVideoError("source image SHA-256 changed during composition -- refusing to trust the result")
    if track_sha256_after != track_sha256_before:
        raise StoryVideoError("source audio SHA-256 changed during composition -- refusing to trust the result")

    probe = _ffprobe(target_path)
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if not video_streams:
        raise StoryVideoError("composed output has no video stream -- refusing to report success")
    if not audio_streams:
        raise StoryVideoError("composed output has no audio stream -- refusing to report success (fail closed, no silent Story)")

    v0, a0 = video_streams[0], audio_streams[0]
    output_sha256 = _sha256_file(target_path)

    provenance = {
        "generated_by": "tools/lena_prepare_story_video_v1.py",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "slot_id": slot_id,
        "source_image_path": str(source_image_path),
        "source_image_sha256": source_sha256_before,
        "source_image_dimensions": [src_w, src_h],
        "selected_track_id": selected_track.get("track_id"),
        "selected_track_filename": selected_track.get("filename"),
        "selected_track_sha256": track_sha256_before,
        "source_manifest_path": str((manifest_path or (ROOT / "assets" / "royaltyfree audio" / "manifest.json")).resolve()),
        "output_path": str(target_path),
        "output_sha256": output_sha256,
        "target_duration_seconds": TARGET_DURATION_SECONDS,
        "measured_duration_seconds": float(fmt.get("duration")) if fmt.get("duration") else None,
        "audio_fade_out_start_seconds": FADE_OUT_START_SECONDS,
        "audio_fade_out_duration_seconds": FADE_OUT_DURATION_SECONDS,
        "video_codec": v0.get("codec_name"),
        "video_width": v0.get("width"),
        "video_height": v0.get("height"),
        "audio_codec": a0.get("codec_name"),
        "audio_sample_rate_hz": int(a0["sample_rate"]) if a0.get("sample_rate") else None,
        "audio_channels": a0.get("channels"),
    }
    provenance_path = target_path.with_name(target_path.stem + "_provenance.json")
    if provenance_path.exists() and not force:
        raise StoryVideoError(f"provenance file already exists at {provenance_path} -- pass force=True/--force to overwrite")
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")

    return {**provenance, "provenance_path": str(provenance_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Composes an approved 9:16 Lena image master with a deterministically-selected "
            "approved audio track into a 20-second MP4 Story video. Never mutates the source "
            "image or audio, never calls any provider/API."
        )
    )
    parser.add_argument("--source", required=True, help="Path to the source <slot>_seed.png master")
    parser.add_argument("--slot", required=True, help="Slot/post identity used for deterministic track selection")
    parser.add_argument("--output", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.is_absolute():
        source_path = (ROOT / source_path).resolve()
    output_path = Path(args.output).resolve() if args.output else None
    manifest_path = Path(args.manifest).resolve() if args.manifest else None

    try:
        result = build_story_video(source_path, args.slot, output_path, args.force, manifest_path)
    except StoryVideoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
