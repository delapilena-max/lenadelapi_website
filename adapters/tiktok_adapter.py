# adapters/tiktok_adapter.py
# ReelForge TikTok Adapter (Stub)
# Python 3.11+, UTF-8 (no BOM)

"""
This is a minimal TikTok adapter stub.
It does NOT log in, post, or automate TikTok yet.
It only:
- reads approved videos
- prepares a post job structure
- logs what would be posted

Later we will replace this with Selenium automation.
"""

from pathlib import Path
import json
from datetime import datetime


def process_approved(root: Path):
    approved = root / "outbox" / "approved"
    posted = root / "outbox" / "posted"
    posted.mkdir(parents=True, exist_ok=True)

    for req_file in approved.glob("*.publish_request.json"):
        data = json.loads(req_file.read_text(encoding="utf-8"))
        publish_id = data["publish_id"]

        video_rel = data["media_path"]
        video_src = root / video_rel

        if not video_src.exists():
            print(f"[tiktok_adapter] Missing video for {publish_id}: {video_src}")
            continue

        # For now, just log the action
        log = {
            "publish_id": publish_id,
            "platform": "tiktok",
            "timestamp_utc": datetime.utcnow().isoformat(),
            "video": str(video_src),
            "status": "stub_only_no_post",
        }

        log_path = posted / f"{publish_id}.tiktok_stub.json"
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

        print(f"[tiktok_adapter] Stub processed {publish_id}")


def main():
    root = Path(__file__).resolve().parents[1]
    process_approved(root)


if __name__ == "__main__":
    main()
