"""
nodes/local_tts_fallback.py

Local TTS fallback used during development to avoid calling Azure.
Behavior:
- Try an offline engine (pyttsx3) first.
- If pyttsx3 is unavailable or fails, fall back to gTTS (Google TTS) which requires internet.
- Writes MP3 to the requested path and returns the path string on success, or None on failure.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def _save_with_pyttsx3(text: str, out_path: Path) -> bool:
    try:
        import pyttsx3
    except Exception:
        logger.debug("pyttsx3 not installed.")
        return False

    try:
        engine = pyttsx3.init()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
        engine.stop()
        if out_path.exists():
            logger.debug("pyttsx3 wrote file: %s", out_path)
            return True
        return False
    except Exception:
        logger.exception("pyttsx3 synthesis failed.")
        return False

def _save_with_gtts(text: str, out_path: Path, lang: str = "en") -> bool:
    try:
        from gtts import gTTS
    except Exception:
        logger.debug("gTTS not installed.")
        return False

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tts = gTTS(text=text, lang=lang)
        tts.save(str(out_path))
        if out_path.exists():
            logger.debug("gTTS wrote file: %s", out_path)
            return True
        return False
    except Exception:
        logger.exception("gTTS synthesis failed.")
        return False

def synthesize_to_file(text: str, out_path: str | Path, prefer: str = "pyttsx3") -> str | None:
    """
    Synthesize 	ext to out_path. Return path string on success, None on failure.
    prefer: 'pyttsx3' or 'gtts' to prefer one method first.
    """
    if not text or not text.strip():
        logger.debug("Empty text provided to local TTS; returning None.")
        return None

    out = Path(out_path)
    if out.suffix.lower() not in (".mp3", ".wav"):
        out = out.with_suffix(".mp3")

    order = [prefer, "gtts" if prefer == "pyttsx3" else "pyttsx3"]
    for engine in order:
        if engine == "pyttsx3":
            ok = _save_with_pyttsx3(text, out)
        else:
            ok = _save_with_gtts(text, out)
        if ok:
            return str(out)

    logger.warning("Local TTS failed for both pyttsx3 and gTTS.")
    return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    sample = "This is a local TTS test. It should save an MP3 file."
    out = Path("assets/audio/local_demo.mp3")
    path = synthesize_to_file(sample, out)
    if path:
        print("Local TTS wrote:", path)
    else:
        print("Local TTS failed.")
