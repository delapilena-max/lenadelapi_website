# pipelines/dialogue/dialogue.py
# ReelForge Dialogue Stage
# Python 3.11+, UTF-8 (no BOM)

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

STAGE = "dialogue"


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
        # Stage I/O folders
        root = Path(__file__).resolve().parents[2]
        input_dir = root / "pipeline" / "input" / STAGE
        output_dir = root / "pipeline" / "output" / STAGE

        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Validate input
        prompt_file = input_dir / "prompt.txt"
        if not prompt_file.exists():
            raise FileNotFoundError("Missing prompt.txt in dialogue input folder")

        prompt_text = prompt_file.read_text(encoding="utf-8").strip()
        if not prompt_text:
            raise ValueError("prompt.txt is empty")

        # Produce script
        script = f"{prompt_text}\n\n# ReelForge auto-generated dialogue"
        script_id = uuid.uuid4().hex
        script_path = output_dir / f"script_{script_id}.txt"
        script_path.write_text(script, encoding="utf-8")

        # Metadata
        metadata = {
            "source_id": script_id,
            "node": "ai_lady",
            "stage": STAGE,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "inputs": ["prompt.txt"],
            "params": {},
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        write_status(output_dir, "success", None, start)
        return 0

    except Exception as e:
        # Failure path
        output_dir = Path(__file__).resolve().parents[2] / "pipeline" / "output" / STAGE
        output_dir.mkdir(parents=True, exist_ok=True)
        write_status(output_dir, "failed", str(e), start)
        print(f"[dialogue] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
