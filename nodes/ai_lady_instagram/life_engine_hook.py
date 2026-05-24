# nodes/ai_lady_instagram/life_engine_hook.py
# Hook to run the Life Engine and queue a post_request JSON into pipeline/outbox/ai_lady
# Drop-in file: add to repo and run with `python nodes/ai_lady_instagram/life_engine_hook.py`
# Python 3.8+ (works in your venv). Ensures project root is on sys.path.

import sys
from pathlib import Path
import json
import time
from datetime import datetime

# Ensure project root is on sys.path so `import nodes.*` works when running the script directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    try:
        out_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[HOOK] ERROR writing outbox entry: {e}", file=sys.stderr)
        return None
    print(f"[HOOK] Wrote outbox entry -> {out_path}")
    return out_path


def run_once():
    try:
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
        out = _write_outbox_entry(media_path, meta)
        if not out:
            return 1

        print(f"[HOOK] Success: queued {media_path.name}")
        return 0

    except Exception as e:
        import traceback, sys as _sys
        traceback.print_exc()
        print(f"[HOOK] ERROR: {e}", file=_sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_once())
    