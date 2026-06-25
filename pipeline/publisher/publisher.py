# pipeline/publisher/publisher.py
# ReelForge Publisher Stage
# Python 3.11+, UTF-8 (no BOM)

import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import shutil

STAGE = "publisher"


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

        renderer_out = root / "pipeline" / "output" / "renderer"
        output_dir = root / "pipeline" / "output" / STAGE
        output_dir.mkdir(parents=True, exist_ok=True)

        outbox_pending = root / "outbox" / "pending"
        outbox_pending.mkdir(parents=True, exist_ok=True)

        # Find rendered video
        videos = sorted(renderer_out.glob("episode_*.mp4"))
        if not videos:
            raise FileNotFoundError("No episode_*.mp4 found in renderer output folder")

        video_path = videos[-1]

        publish_id = uuid.uuid4().hex
        dest_video = outbox_pending / f"{publish_id}.mp4"

        # Copy video into outbox/pending
        shutil.copy2(video_path, dest_video)

        # Build publish_request.json
        publish_request = {
            "publish_id": publish_id,
            "node": "ai_lady",
            "timestamp_utc": datetime.utcnow().isoformat(),
            "media_path": str(dest_video.relative_to(root)),
            "metadata": {
                "source_video": video_path.name,
            },
            "publish_window": {
                "start_utc": (datetime.utcnow() + timedelta(minutes=1)).isoformat(),
                "end_utc": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            },
            "dry_run": True,  # default until adapters are fully wired
        }

        req_path = outbox_pending / f"{publish_id}.publish_request.json"
        req_path.write_text(json.dumps(publish_request, indent=2), encoding="utf-8")

        # Metadata for the stage
        metadata = {
            "source_id": publish_id,
            "node": "ai_lady",
            "stage": STAGE,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "inputs": [video_path.name],
            "params": {
                "dry_run": True,
            },
            "outputs": {
                "pending_video": str(dest_video.relative_to(root)),
                "publish_request": str(req_path.relative_to(root)),
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
        print(f"[publisher] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
