from __future__ import annotations

# Lena Story-video preparation -- composes an approved 9:16 image master
# with a deterministically-selected approved audio track into a 20-second
# MP4 Story video with a real audio stream.
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
