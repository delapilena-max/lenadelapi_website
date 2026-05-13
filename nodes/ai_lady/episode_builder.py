import json
from pathlib import Path
from datetime import datetime
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip


def load_clips(clip_paths):
    clips = []
    for p in clip_paths:
        p = Path(p)
        if not p.exists():
            raise FileNotFoundError(f"Clip not found: {p}")
        clips.append(VideoFileClip(str(p)))
    return clips


def normalize_clip(clip, target_w=1080, target_h=1920, target_fps=24):
    """
    Ensures all clips match the same resolution and FPS.
    """
    # Resize if needed
    if clip.w != target_w or clip.h != target_h:
        clip = clip.resize(newsize=(target_w, target_h))

    # Set FPS
    if clip.fps != target_fps:
        clip = clip.set_fps(target_fps)

    return clip


def build_episode(
    clip_paths,
    output_dir,
    target_w=1080,
    target_h=1920,
    target_fps=24,
    crossfade=0.0,
    bg_audio_path=None,
    bg_audio_volume=0.15,
):
    """
    Build a final stitched episode from multiple Kling clips.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load and normalize
    raw_clips = load_clips(clip_paths)
    clips = [
        normalize_clip(c, target_w=target_w, target_h=target_h, target_fps=target_fps)
        for c in raw_clips
    ]

    # Apply crossfade if desired
    if crossfade > 0:
        final = concatenate_videoclips(clips, method="compose", padding=-crossfade)
    else:
        final = concatenate_videoclips(clips, method="compose")

    # Add background audio
    if bg_audio_path:
        bg_audio = AudioFileClip(str(bg_audio_path)).volumex(bg_audio_volume)
        final = final.set_audio(bg_audio)

    # Output path
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = output_dir / f"episode_{ts}.mp4"

    # Write final video
    final.write_videofile(
        str(out_path),
        codec="libx264",
        audio_codec="aac",
        fps=target_fps,
        threads=4,
        preset="medium",
        bitrate="5000k",
    )

    return str(out_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Stitch Kling clips into a final episode.")
    parser.add_argument("--clips", nargs="+", required=True, help="List of clip paths")
    parser.add_argument("--output-dir", required=True, help="Directory for final episodes")
    parser.add_argument("--crossfade", type=float, default=0.0, help="Seconds of crossfade")
    parser.add_argument("--bg-audio", default=None, help="Optional background audio file")
    parser.add_argument("--bg-volume", type=float, default=0.15, help="Background audio volume")

    args = parser.parse_args()

    out = build_episode(
        clip_paths=args.clips,
        output_dir=args.output_dir,
        crossfade=args.crossfade,
        bg_audio_path=args.bg_audio,
        bg_audio_volume=args.bg_volume,
    )

    print(json.dumps({"episode": out}, indent=2))


if __name__ == "__main__":
    main()
