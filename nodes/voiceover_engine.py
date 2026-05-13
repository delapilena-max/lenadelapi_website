"""
nodes/voiceover_engine.py

Voiceover generation helper used by the demo pipeline.

Behavior:
- If AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are set in the environment,
  this module will attempt to synthesize speech using Azure Speech SDK and
  write an MP3 file to assets/audio/voiceover.mp3.
- If Azure credentials are missing or synthesis fails, the function returns None.
- The rest of the pipeline should handle a None return (silent fallback).

Usage:
from nodes.voiceover_engine import generate_voiceover_clip
voice_path = generate_voiceover_clip("Hello world")
if voice_path:
    # use voice_path in renderer
else:
    # pipeline will proceed without voiceover
"""

from pathlib import Path
import os
import logging
import uuid

# Optional import for Azure Speech SDK. If not installed, we will gracefully handle it.
try:
    import azure.cognitiveservices.speech as speechsdk  # type: ignore
    _HAS_AZURE_SDK = True
except Exception:
    _HAS_AZURE_SDK = False

# Output folder for generated voiceovers
_AUDIO_DIR = Path("assets") / "audio"
_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Default output filename (overwritten per-run to avoid collisions)
_DEFAULT_VOICE_FILENAME = _AUDIO_DIR / "voiceover.mp3"

logger = logging.getLogger(__name__)


def _azure_synthesize_to_file(text: str, out_path: Path, voice: str, rate: float) -> bool:
    """
    Synthesize `text` to `out_path` using Azure Speech SDK.
    Returns True on success, False on failure.
    """
    if not _HAS_AZURE_SDK:
        logger.debug("Azure Speech SDK not installed.")
        return False

    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        logger.debug("Azure credentials missing from environment.")
        return False

    try:
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        # Use MP3 output
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
        # Set voice if provided
        if voice:
            speech_config.speech_synthesis_voice_name = voice

        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(out_path))
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        # Optionally adjust speaking rate via SSML wrapper if rate != 0
        if rate and abs(rate) > 1e-6:
            # rate is expected as a percentage change string for SSML, e.g., "+10%" or "-10%"
            # Here we accept a float like 0.0 (default), or 0.1 for +10%, -0.1 for -10%
            pct = int(rate * 100)
            sign = "+" if pct >= 0 else ""
            ssml = f"""
<speak version='1.0' xml:lang='en-US'>
  <voice name='{voice}'>
    <prosody rate='{sign}{pct}%'>
      {text}
    </prosody>
  </voice>
</speak>
"""
            result = synthesizer.speak_ssml_async(ssml).get()
        else:
            result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.debug("Azure synthesis succeeded, file written: %s", out_path)
            return True
        else:
            logger.warning("Azure synthesis did not complete successfully: %s", result.reason)
            return False

    except Exception as exc:
        logger.exception("Azure synthesis failed: %s", exc)
        # Ensure we don't leave a corrupt file
        try:
            if out_path.exists():
                out_path.unlink()
        except Exception:
            pass
        return False


def generate_voiceover_clip(text: str,
                            out_path: Path | str | None = None,
                            voice: str = "en-US-JennyNeural",
                            rate: float = 0.0) -> str | None:
    """
    Generate a voiceover MP3 for `text`.

    Parameters
    - text: the text to synthesize
    - out_path: optional Path or string for output file. If omitted, uses assets/audio/voiceover-<uuid>.mp3
    - voice: Azure voice name (if using Azure). Default is a common US neural voice.
    - rate: speaking rate adjustment as a float fraction (0.1 == +10%, -0.1 == -10%). Default 0.0.

    Returns:
    - Path (string) to the generated MP3 on success.
    - None on failure or if credentials are missing.
    """
    if not text or not text.strip():
        logger.debug("Empty text provided to generate_voiceover_clip; returning None.")
        return None

    if out_path is None:
        out_path = _AUDIO_DIR / f"voiceover-{uuid.uuid4().hex[:8]}.mp3"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Try Azure synthesis first if available
    success = _azure_synthesize_to_file(text, out_path, voice, rate)
    if success:
        logger.info("Voiceover generated successfully → %s", out_path)
        return str(out_path)

    # If Azure is not configured or failed, return None so the pipeline can fallback to silent audio
    logger.info("Voiceover generation unavailable; returning None (pipeline should handle silent fallback).")
    return None


# Convenience wrapper used by the demo pipeline (keeps a stable filename)
def generate_and_save_demo_voiceover(text: str) -> str | None:
    """
    Generate voiceover and save to the canonical demo filename assets/audio/voiceover.mp3.
    Returns the path string on success, or None on failure.
    """
    out = _DEFAULT_VOICE_FILENAME
    # Remove previous file if present to avoid stale audio
    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass

    return generate_voiceover_clip(text, out_path=out)


if __name__ == "__main__":
    # Quick local smoke test (won't run synthesis unless Azure creds are present)
    logging.basicConfig(level=logging.DEBUG)
    sample = "This is a quick voiceover test."
    path = generate_and_save_demo_voiceover(sample)
    if path:
        print("Voiceover written to:", path)
    else:
        print("Voiceover not generated (Azure credentials missing or synthesis failed).")
