# pipeline/compositor/compositor.py
# ReelForge Compositor Stage (stub)
# Python 3.11+, UTF-8 (no BOM)

import json
import sys
from pathlib import Path
from datetime import datetime

STAGE = "compositor"


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

        tts_out = root / "pipeline" / "output" / "tts"
        output_dir = root / "pipeline" / "output" / STAGE
        frames_dir = output_dir / "frames"

        output_dir.mkdir(parents=True, exist_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Find TTS output
        tts_json = tts_out / "tts_output.json"
        if not tts_json.exists():
            raise FileNotFoundError("Missing tts_output.json from TTS stage")

        tts_data = json.loads(tts_json.read_text(encoding="utf-8"))

        # Create fake frames so renderer can find them
        for i in range(1, 3):
            frame_path = frames_dir / f"frame_{i:04d}.png"
            frame_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

        # Write compositor_output.json
        compositor_output = {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "dialogue_text": tts_data.get("dialogue_text", ""),
            "frames": ["frame_0001.png", "frame_0002.png"],
            "note": "Stub compositor stage. Replace with real compositor later.",
        }
        (output_dir / "compositor_output.json").write_text(
            json.dumps(compositor_output, indent=2), encoding="utf-8"
        )

        # Write metadata.json EXACTLY how renderer expects it
        metadata = {
            "outputs": {
                "frames_dir": str(frames_dir.relative_to(root))
            },
            "fps": 24,
            "width": 1080,
            "height": 1920,
            "note": "Stub metadata for renderer compatibility"
        }

        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        write_status(output_dir, "success", None, start)
        return 0

    except Exception as e:
        output_dir = Path(__file__).resolve().parents[2] / "pipeline" / "output" / STAGE
        output_dir.mkdir(parents=True, exist_ok=True)
        write_status(output_dir, "failed", str(e), start)
        print(f"[compositor] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
