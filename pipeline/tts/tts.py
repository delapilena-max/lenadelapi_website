# pipeline/tts/tts.py
# ReelForge TTS Stage (stub)
# Python 3.11+, UTF-8 (no BOM)

import json
import sys
from pathlib import Path
from datetime import datetime

STAGE = "tts"


def write_status(path: Path, status: str, error: str | None, start: datetime):
    duration = (datetime.utcnow() - start).total_seconds()
    status_data = {
        "status": status,
        "error": error,
        "duration_seconds": duration,
    }
    (path / f"{STAGE}.status.json").write_text(
        json.dumps(status_data, indent=2), encoding="utf-8"
    )


def main():
    start = datetime.utcnow()

    try:
        root = Path(__file__).resolve().parents[2]

        dialogue_out = root / "pipeline" / "output" / "dialogue"
        output_dir = root / "pipeline" / "output" / STAGE
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find dialogue output
        text_files = sorted(dialogue_out.glob("*.txt"))
        if not text_files:
            raise FileNotFoundError("No dialogue text found in dialogue output folder")

        dialogue_text = text_files[-1].read_text(encoding="utf-8")

        # Write stub JSON
        tts_output = {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "dialogue_text": dialogue_text,
            "audio_file": "voice_0001.wav",
            "note": "Stub TTS stage. Replace with real TTS later.",
        }

        (output_dir / "tts_output.json").write_text(
            json.dumps(tts_output, indent=2), encoding="utf-8"
        )

        # Create a minimal valid WAV file so renderer can use it
        wav_path = output_dir / "voice_0001.wav"

        # 44-byte minimal WAV header (PCM, 1 channel, 16-bit, 44100 Hz, no data)
        wav_header = bytes.fromhex(
            "524946460024000057415645666D7420100000000100010044AC000010B10200020010006461746100000000"
        )

        wav_path.write_bytes(wav_header)

        write_status(output_dir, "success", None, start)
        return 0

    except Exception as e:
        output_dir = Path(__file__).resolve().parents[2] / "pipeline" / "output" / STAGE
        output_dir.mkdir(parents=True, exist_ok=True)
        write_status(output_dir, "failed", str(e), start)
        print(f"[tts] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
