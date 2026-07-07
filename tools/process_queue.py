"""Manual helper to process pipeline/queue with the new PostingManager."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.posting_manager import PostingManager  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Process content_bot pipeline/queue posts.")
    parser.add_argument("--max-posts", type=int, default=None, help="Maximum posts to process this run; default comes from config.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and generate receipts without posting or moving queue files.")
    parser.add_argument("--live", action="store_true", help="Allow queue mutation and configured publisher backend.")
    parser.add_argument("--media-type", choices=["photo", "video"], action="append", help="Restrict to one or more media types.")
    parser.add_argument("--date", default="", help="Only process queue items whose filenames start with this YYYY-MM-DD date.")
    parser.add_argument("--config", default=None, help="Optional posting_config.json path.")
    args = parser.parse_args()

    if args.dry_run and args.live:
        parser.error("Use either --dry-run or --live, not both.")

    dry_run = True if args.dry_run else (False if args.live else None)
    date_prefix = (args.date or os.environ.get("LENA_PUBLISH_DATE") or "").strip()
    result = PostingManager(config_path=args.config).process_queue(
        max_posts=args.max_posts,
        dry_run=dry_run,
        media_types=args.media_type,
        date_prefix=date_prefix or None,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
