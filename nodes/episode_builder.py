"""
nodes/episode_builder.py

Defines a simple shots list and the build_episode(shots, out_path) function
used by the demo pipeline. Integrates TTSGuard and local TTS fallback so
cloud synths are only used when within quota; otherwise local TTS or silent
fallback is used.
"""

from pathlib import Path
from typing import List, Dict, Optional
import logging

from nodes.renderer import render_final_video
from nodes.voiceover_engine import generate_and_save_demo_voiceover
from nodes.tts_guard import TTSGuard
from nodes.local_tts_fallback import synthesize_to_file

logger = logging.getLogger(__name__)

# Default demo assets (adjust these paths to match your repo)
_ASSETS = Path("assets")
_DEFAULT_BG = _ASSETS / "bg_sample.png"
_DEFAULT_CHAR = _ASSETS / "char_sample.png"
_DEFAULT_MUSIC = _ASSETS / "music_sample.mp3"

# A small, safe default shots list so the demo runs out-of-the-box.
shots: List[Dict] = [
    {
        "id": "shot-1",
        "background": str(_DEFAULT_BG),
        "character": str(_DEFAULT_CHAR),
        "subtitle": "Welcome to the demo. This is shot one.",
        "music": str(_DEFAULT_MUSIC),
        "duration": 6.0,
        "voice_text": "Welcome to the demo. This is shot one."
    },
    {
        "id": "shot-2",
        "background": str(_DEFAULT_BG),
        "character": str(_DEFAULT_CHAR),
        "subtitle": "This is shot two. Thanks for watching.",
        "music": str(_DEFAULT_MUSIC),
        "duration": 5.0,
        "voice_text": "This is shot two. Thanks for watching."
    },
]


def get_shots() -> List[Dict]:
    """
    Return the default shots list. Callers may modify or replace this list.
    """
    return shots


def _ensure_asset_paths(s: Dict) -> None:
    """
    Ensure asset paths exist; log warnings if they don't.
    This keeps the pipeline robust while letting the renderer raise if a required file is missing.
    """
    for key in ("background", "character", "music"):
        if key in s and s[key]:
            p = Path(s[key])
            if not p.exists():
                logger.warning("Asset not found for shot %s: %s -> %s", s.get("id"), key, s[key])


def build_episode(shots_list: List[Dict], out_path: str) -> None:
    """
    Build an episode by rendering each shot and concatenating them into out_path.
    This function mirrors the simple pipeline used by the demo:
      - For each shot: generate voiceover (if possible), render final shot to temp file
      - Concatenate shot files into the final episode file
    """
    from moviepy.editor import concatenate_videoclips, VideoFileClip
    import tempfile
    import shutil

    # TTS guard: prevents accidental cloud overage and caches by text hash
    guard = TTSGuard(quota_per_month=500_000, counter_file="data/tts_counter.yaml", cache_dir="assets/audio/cache")

    tmp_files = []
    try:
        for idx, s in enumerate(shots_list):
            _ensure_asset_paths(s)
            logger.info("Rendering shot %d/%d…", idx + 1, len(shots_list))

            # Voiceover selection logic:
            voice_path = None
            voice_text = s.get("voice_text", "")
            shot_id = s.get("id", f"shot-{idx}")

            if voice_text and voice_text.strip():
                allowed, reason = guard.request_synthesis(voice_text)
                logger.debug("TTSGuard request for shot %s: allowed=%s reason=%s", shot_id, allowed, reason)

                if allowed and reason == "cached":
                    # Use cached file
                    voice_path = str(guard.cache_path_for(voice_text))
                    logger.info("Using cached voice for shot %s -> %s", shot_id, voice_path)

                elif allowed and reason == "ok":
                    # Try Azure first (generate_and_save_demo_voiceover writes to canonical path)
                    try:
                        # generate_and_save_demo_voiceover uses a stable filename; we prefer cache path
                        out_cache = guard.cache_path_for(voice_text)
                        # Attempt Azure synthesis to the cache path via voiceover_engine
                        success = False
                        try:
                            # If Azure works, generate_and_save_demo_voiceover writes to assets/audio/voiceover.mp3
                            # We call generate_voiceover_clip to attempt writing directly to the cache path if available.
                            from nodes.voiceover_engine import generate_voiceover_clip
                            result = generate_voiceover_clip(voice_text, out_path=out_cache)
                            if result:
                                success = True
                                voice_path = str(out_cache)
                                logger.info("Azure TTS wrote cached file for shot %s -> %s", shot_id, voice_path)
                        except Exception:
                            logger.exception("Azure TTS attempt failed for shot %s", shot_id)

                        if not success:
                            # Azure failed or not configured: try local TTS fallback and keep cache
                            local_result = synthesize_to_file(voice_text, out_cache)
                            if local_result:
                                voice_path = str(out_cache)
                                logger.info("Local TTS wrote cached file for shot %s -> %s", shot_id, voice_path)
                            else:
                                # If local also failed, roll back reserved chars and proceed without voice
                                guard.record_synthesis_failure(voice_text)
                                logger.info("TTS failed for shot %s; proceeding without voiceover.", shot_id)

                    except Exception:
                        logger.exception("Unexpected error during TTS for shot %s; proceeding without voiceover.", shot_id)
                        # Ensure we don't leave reserved quota consumed on unexpected failure
                        guard.record_synthesis_failure(voice_text)

                else:
                    # Not allowed (quota exceeded) — try local fallback without consuming quota
                    logger.info("Quota exceeded or synthesis disallowed for shot %s: %s", shot_id, reason)
                    cache_path = guard.cache_path_for(voice_text)
                    if not cache_path.exists():
                        local_result = synthesize_to_file(voice_text, cache_path)
                        if local_result:
                            voice_path = str(cache_path)
                            logger.info("Local TTS saved for shot %s -> %s", shot_id, voice_path)
                        else:
                            logger.info("Local TTS failed for shot %s; proceeding without voiceover.", shot_id)
                    else:
                        voice_path = str(cache_path)
                        logger.info("Using existing cached file for shot %s -> %s", shot_id, voice_path)

            # Render the shot to a temporary file
            tmp = Path(tempfile.gettempdir()) / f"temp_shot_{idx}.mp4"
            # Ensure previous temp is removed
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

            render_final_video(
                background_path=s["background"],
                character_path=s.get("character"),
                subtitle_text=s.get("subtitle", ""),
                music_path=s.get("music"),
                voiceover_path=voice_path,
                out_path=str(tmp),
                duration=s.get("duration"),
            )
            tmp_files.append(str(tmp))

        # Concatenate shots
        clips = [VideoFileClip(p) for p in tmp_files]
        final = concatenate_videoclips(clips, method="compose")
        out_dir = Path(out_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        final.write_videofile(str(out_path), codec="libx264", audio_codec="aac", threads=0)
        final.close()
        for c in clips:
            c.close()

    finally:
        # Clean up temp files
        for p in tmp_files:
            try:
                Path(p).unlink()
            except Exception:
                pass
