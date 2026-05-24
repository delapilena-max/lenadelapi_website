# outbox/worker_auto_approve.py
# ReelForge simple auto-approve worker
# Python 3.11+, UTF-8 (no BOM)

import json
from pathlib import Path
from datetime import datetime
import shutil


def process_pending(root: Path):
    pending = root / "outbox" / "pending"
    approved = root / "outbox" / "approved"

    pending.mkdir(parents=True, exist_ok=True)
    approved.mkdir(parents=True, exist_ok=True)

    for req_file in pending.glob("*.publish_request.json"):
        data = json.loads(req_file.read_text(encoding="utf-8"))
        publish_id = data["publish_id"]

        video_rel = data["media_path"]
        video_src = root / video_rel

        if not video_src.exists():
            print(f"[auto_approve] Missing video for {publish_id}: {video_src}")
            continue

        # Move video + request into approved
        dest_video = approved / f"{publish_id}.mp4"
        dest_req = approved / f"{publish_id}.publish_request.json"

        shutil.move(str(video_src), dest_video)
        shutil.move(str(req_file), dest_req)

        # Write simple approval metadata
        meta = {
            "publish_id": publish_id,
            "approved_utc": datetime.utcnow().isoformat(),
            "source_video": str(dest_video.relative_to(root)),
        }
        (approved / f"{publish_id}.approved.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        print(f"[auto_approve] Approved {publish_id}")


def main():
    root = Path(__file__).resolve().parents[1]
    process_pending(root)


if __name__ == "__main__":
    main()
