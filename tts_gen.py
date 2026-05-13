"""
tts_gen.py - TTS voiceover generator for batch_render pipeline.
Uses edge-tts with the voice defined in config["voice"].
"""

import asyncio
import logging
from pathlib import Path
import edge_tts

log = logging.getLogger(__name__)
DEFAULT_VOICE = "en-US-AriaNeural"


async def _synthesize(text: str, voice: str, output_path: str) -> None:
    comm = edge_tts.Communicate(text, voice)
    await comm.save(output_path)


def build_script(episode: dict) -> str:
    subtitles = episode.get("subtitles") or []
    parts = [str(s.get("text", "")).strip() for s in subtitles if s.get("text")]
    return " ".join(parts)


def generate_tts(episode: dict, output_path: str, voice: str = DEFAULT_VOICE) -> bool:
    script = build_script(episode)
    if not script:
        log.error("generate_tts: no text to synthesize")
        return False
    log.info("generate_tts: voice=%s, chars=%d", voice, len(script))
    try:
        asyncio.run(_synthesize(script, voice, output_path))
        size = Path(output_path).stat().st_size
        log.info("generate_tts: wrote %s (%.1f KB)", output_path, size / 1024)
        return True
    except Exception as e:
        log.error("generate_tts: failed — %s", e)
        return False
