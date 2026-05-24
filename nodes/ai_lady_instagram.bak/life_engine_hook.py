# nodes/ai_lady_instagram/life_engine_hook.py
# Hook to run the Life Engine and publish a generated media item to the pipeline outbox.
# Python 3.11+, UTF-8

import json
import sys
import time
from pathlib import Path
from datetime import datetime

OUTBOX_DIR = Path("pipeline/outbox/ai_lady")
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

def _read_meta(media_path: Path):
    meta_path = media_path.with_suffix(media_path.suffix + ".meta.json")
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_outbox_entry(media_path: Path, meta: dict):
    ts = int(time.time())
    entry = {
        "created_at": datetime.utcnow().isoformat(),
        "media": str(media_path),
        "meta": meta,
        "source": "life_engine_hook",
    }
    out_path = OUTBOX_DIR / f"post_request_{ts}.json"
    out_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[HOOK] Wrote outbox entry -> {out_path}")
    return out_path

def run_once():
    try:
        # import life_engine and call create_post_media
        import importlib
        le = importlib.import_module("nodes.life_engine")
        if not hasattr(le, "create_post_media"):
            print("[HOOK] life_engine.create_post_media not found", file=sys.stderr)
            return 1

        media_path = le.create_post_media(str(OUTBOX_DIR))
        if not media_path:
            print("[HOOK] life_engine decided not to post right now.")
            return 0

        media_path = Path(media_path)
        if not media_path.exists():
            print(f"[HOOK] Generated media not found: {media_path}", file=sys.stderr)
            return 1

        meta = _read_meta(media_path)
        _write_outbox_entry(media_path, meta)
        print(f"[HOOK] Success: queued {media_path.name}")
        return 0

    except Exception as e:
        print(f"[HOOK] ERROR: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(run_once())
