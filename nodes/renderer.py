"""
nodes/renderer.py

Simple renderer used by the demo pipeline.

Exports:
- render_final_video(background_path, character_path, subtitle_text,
                     music_path, voiceover_path, out_path, duration)

Behavior:
- If `background_path` is a video file, it is used as the clip; otherwise an ImageClip is created.
- Optional `character_path` is overlaid centered on the background.
- Optional `voiceover_path` is mixed with optional `music_path` (music is lowered).
- `subtitle_text` is rendered as a TextClip and placed near the bottom.
- `duration` is required when background is an image.
- Ensures `fps` is set before writing the file.
"""

from __future__ import annotations
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import moviepy to avoid import-time cost in callers that don't render
def _import_moviepy():
    try:
        from moviepy.editor import (
            VideoFileClip,
            AudioFileClip,
            ImageClip,
            CompositeVideoClip,
            concatenate_videoclips,
            TextClip,
        )
        return {
            "VideoFileClip": VideoFileClip,
            "AudioFileClip": AudioFileClip,
            "ImageClip": ImageClip,
            "CompositeVideoClip": CompositeVideoClip,
            "concatenate_videoclips": concatenate_videoclips,
            "TextClip": TextClip,
        }
    except Exception:
        logger.exception("Failed to import moviepy. Ensure moviepy is installed in the active environment.")
        raise


def _is_video_file(p: Path) -> bool:
    # Basic heuristic based on extension
    return p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg")


def _make_background_clip(background_path: str, duration: Optional[float], mp) -> object:
    p = Path(background_path)
    if p.exists() and _is_video_file(p):
        clip = mp["VideoFileClip"](str(p))
        # If duration provided and shorter than clip, subclip; if longer, loop
        if duration is not None:
            if clip.duration > duration:
                clip = clip.subclip(0, duration)
            elif clip.duration < duration:
                # loop the clip to reach duration
                clips = []
                t = 0.0
                while t < duration:
                    remaining = duration - t
                    clips.append(clip.subclip(0, min(clip.duration, remaining)))
                    t += clip.duration
                clip = mp["concatenate_videoclips"](clips, method="compose")
        return clip
    else:
        # treat as image
        img = mp["ImageClip"](str(p)) if p.exists() else mp["ImageClip"](str(Path("assets/bg_sample.png")))
        if duration is None:
            raise ValueError("duration is required when background is an image")
        img = img.set_duration(duration)
        return img


def _make_character_clip(character_path: Optional[str], base_clip, mp) -> Optional[object]:
    if not character_path:
        return None
    p = Path(character_path)
    if not p.exists():
        logger.warning("Character asset not found: %s", character_path)
        return None
    try:
        char = mp["ImageClip"](str(p))
        # scale character to a fraction of the base clip width
        target_w = base_clip.w * 0.35
        if char.w > target_w:
            char = char.resize(width=target_w)
        # center horizontally, place slightly above bottom
        char = char.set_position(("center", base_clip.h * 0.45)).set_duration(base_clip.duration)
        return char
    except Exception:
        logger.exception("Failed to create character clip from %s", character_path)
        return None


def _make_subtitle_clip(text: Optional[str], base_clip, mp, fontsize: int = 28, color: str = "white") -> Optional[object]:
    if not text:
        return None
    try:
        # TextClip can be slow; use a simple configuration
        txt = mp["TextClip"](text, fontsize=fontsize, color=color, font="Arial", method="caption", size=(base_clip.w * 0.9, None))
        txt = txt.set_position(("center", base_clip.h * 0.82)).set_duration(base_clip.duration)
        # add a semi-transparent background by returning the text clip itself (moviepy handles alpha)
        return txt
    except Exception:
        logger.exception("Failed to create subtitle clip.")
        return None


def _compose_audio(voiceover_path: Optional[str], music_path: Optional[str], base_clip, mp) -> Optional[object]:
    """
    Returns an AudioFileClip or None. If both voiceover and music exist,
    voiceover is prioritized and music is lowered and looped to match duration.
    """
    if not voiceover_path and not music_path:
        return None

    audio_clips = []
    try:
        if voiceover_path and Path(voiceover_path).exists():
            voice = mp["AudioFileClip"](str(voiceover_path))
            # If voiceover shorter than base, we let it play; otherwise trim
            if voice.duration > base_clip.duration:
                voice = voice.subclip(0, base_clip.duration)
            audio_clips.append(("voice", voice))
        if music_path and Path(music_path).exists():
            music = mp["AudioFileClip"](str(music_path))
            # loop music to match duration
            if music.duration < base_clip.duration:
                # concatenate copies
                parts = []
                t = 0.0
                while t < base_clip.duration:
                    parts.append(music.subclip(0, min(music.duration, base_clip.duration - t)))
                    t += music.duration
                music = mp["concatenate_videoclips"](parts) if parts else music
            if music.duration > base_clip.duration:
                music = music.subclip(0, base_clip.duration)
            # lower music volume if voice exists
            if any(name == "voice" for name, _ in audio_clips):
                music = music.volumex(0.25)
            audio_clips.append(("music", music))
    except Exception:
        logger.exception("Failed to load audio files.")
        # fallback: return whichever loaded
        if audio_clips:
            return audio_clips[0][1]
        return None

    # Mix audio: prefer voice as primary track; if both, overlay music under voice
    if not audio_clips:
        return None
    if len(audio_clips) == 1:
        return audio_clips[0][1]
    # Both present: overlay by setting music as background and voice as main
    # MoviePy doesn't have a direct "mix" helper for AudioFileClip objects, but CompositeAudioClip can be used.
    try:
        from moviepy.audio.AudioClip import CompositeAudioClip  # type: ignore
        clips = []
        for name, clip in audio_clips:
            clips.append(clip)
        comp_audio = CompositeAudioClip(clips).set_duration(base_clip.duration)
        return comp_audio
    except Exception:
        # If CompositeAudioClip import fails, return voice only
        logger.exception("Failed to composite audio; returning voice only if available.")
        for name, clip in audio_clips:
            if name == "voice":
                return clip
        return audio_clips[0][1]


def render_final_video(
    background_path: str,
    character_path: Optional[str] = None,
    subtitle_text: Optional[str] = None,
    music_path: Optional[str] = None,
    voiceover_path: Optional[str] = None,
    out_path: str = "output/episode_shot.mp4",
    duration: Optional[float] = None,
) -> None:
    """
    Render a single shot to out_path.

    Parameters:
    - background_path: path to image or video
    - character_path: optional image path to overlay
    - subtitle_text: optional subtitle string
    - music_path: optional music file path
    - voiceover_path: optional voiceover file path
    - out_path: destination mp4 path
    - duration: required if background is an image
    """
    mp = _import_moviepy()
    VideoFileClip = mp["VideoFileClip"]
    CompositeVideoClip = mp["CompositeVideoClip"]

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    try:
        bg_clip = _make_background_clip(background_path, duration, mp)
    except Exception:
        logger.exception("Failed to create background clip; aborting render.")
        raise

    # Ensure base clip has size attributes
    if not hasattr(bg_clip, "w") or not hasattr(bg_clip, "h"):
        # try to set a default size
        try:
            bg_clip = bg_clip.resize(width=1280)
        except Exception:
            pass

    # Character overlay
    char_clip = _make_character_clip(character_path, bg_clip, mp)
    # Subtitle overlay
    subtitle_clip = _make_subtitle_clip(subtitle_text, bg_clip, mp)

    # Compose video layers
    layers = [bg_clip]
    if char_clip:
        layers.append(char_clip)
    if subtitle_clip:
        layers.append(subtitle_clip)

    try:
        comp = CompositeVideoClip(layers, size=(bg_clip.w, bg_clip.h))
        comp = comp.set_duration(bg_clip.duration)
    except Exception:
        logger.exception("Failed to compose video clip.")
        raise

    # Attach audio
    audio = _compose_audio(voiceover_path, music_path, comp, mp)
    if audio:
        try:
            comp = comp.set_audio(audio)
        except Exception:
            logger.exception("Failed to set audio on composite clip; continuing without audio.")

    # Ensure fps is set
    DEFAULT_FPS = 24
    if getattr(comp, "fps", None) is None:
        comp.fps = DEFAULT_FPS

    # Write file
    try:
        comp.write_videofile(
            str(out_p),
            codec="libx264",
            audio_codec="aac",
            threads=0,
            fps=comp.fps,
            verbose=False,
            logger=None,
        )
        logger.info("Rendered shot -> %s", out_p)
    except Exception:
        logger.exception("Failed to write video file %s", out_p)
        raise
    finally:
        # close clips to release resources
        try:
            comp.close()
        except Exception:
            pass
        try:
            bg_clip.close()
        except Exception:
            pass
        if char_clip:
            try:
                char_clip.close()
            except Exception:
                pass
        if subtitle_clip:
            try:
                subtitle_clip.close()
            except Exception:
                pass
