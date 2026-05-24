# pipeline/renderer/renderer.py
# ReelForge Renderer Stage
# Python 3.11+, UTF-8 (no BOM)

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
import subprocess

STAGE = "renderer"


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

        comp_out = root / "pipeline" / "output" / "compositor"
        tts_out = root / "pipeline" / "output" / "tts"
        output_dir = root / "pipeline" / "output" / STAGE
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find compositor metadata
        comp_meta = comp_out / "metadata.json"
        if not comp_meta.exists():
            raise FileNotFoundError("compositor metadata.json not found")

        comp_data = json.loads(comp_meta.read_text(encoding="utf-8"))
        frames_dir = root / comp_data["outputs"]["frames_dir"]
        if not frames_dir.exists():
            raise FileNotFoundError(f"frames_dir not found: {frames_dir}")

        # Find audio
        wav_files = sorted(tts_out.glob("voice_*.wav"))
        if not wav_files:
            raise FileNotFoundError("No voice_*.wav found in TTS output folder")
        audio_path = wav_files[-1]

        render_id = uuid.uuid4().hex
        video_path = output_dir / f"episode_{render_id}.mp4"

        # Expect frame_0001.png, frame_0002.png, ...
        first_frame = frames_dir / "frame_0001.png"
        if not first_frame.exists():
            raise FileNotFoundError(
                f"Expected first frame at {first_frame}, not found"
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            "30",
            "-i",
            str(frames_dir / "frame_%04d.png"),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")

        metadata = {
            "source_id": render_id,
            "node": "ai_lady",
            "stage": STAGE,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "inputs": [
                str(frames_dir.relative_to(root)),
                audio_path.name,
            ],
            "params": {
                "fps": 30,
                "vcodec": "libx264",
                "acodec": "aac",
            },
            "outputs": {
                "video": str(video_path.relative_to(root)),
            },
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
        print(f"[renderer] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
