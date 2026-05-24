# scripts/force_post.py
# Force a media generation and queue a post_request JSON into pipeline/outbox/ai_lady
# Usage: python scripts/force_post.py
# Python 3.8+

import sys
from pathlib import Path
import json
import time
from datetime import datetime

# Ensure project root is on sys.path so imports work when running this script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTBOX_DIR = Path("pipeline/outbox/ai_lady")
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def _write_outbox_entry(media_path: Path, meta: dict):
    ts = int(time.time())
    entry = {
        "created_at": datetime.utcnow().isoformat(),
        "media": str(media_path),
        "meta": meta,
        "source": "force_post.py",
    }
    out_path = OUTBOX_DIR / f"post_request_{ts}.json"
    out_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _read_meta(media_path: Path):
    meta_path = media_path.with_suffix(media_path.suffix + ".meta.json")
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    try:
        import importlib
        lg = importlib.import_module("nodes.life_generator")
    except Exception as e:
        print(f"[force_post] ERROR importing nodes.life_generator: {e}", file=sys.stderr)
        return 2

    # Load profile if available
    profile = {}
    try:
        prof_path = Path("nodes/life_profile.json")
        if prof_path.exists():
            profile = json.loads(prof_path.read_text(encoding="utf-8"))
    except Exception:
        profile = {}

    # Choose defaults
    theme = "everyday"
    prefer = "image"

    # Try to pick a theme from profile interests if present
    try:
        interests = profile.get("interests", {})
        if interests:
            # pick highest-weight theme
            theme = max(interests.items(), key=lambda kv: kv[1])[0]
    except Exception:
        pass

    # Generate media (force image by prefer)
    try:
        path = lg.generate_media(str(OUTBOX_DIR), theme=theme, prefer=prefer, profile=profile)
        if not path:
            print("[force_post] life_generator returned no path", file=sys.stderr)
            return 1
        media_path = Path(path)
        if not media_path.exists():
            print(f"[force_post] Generated media not found: {media_path}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"[force_post] ERROR generating media: {e}", file=sys.stderr)
        return 2

    # Read meta and write outbox entry
    meta = _read_meta(media_path)
    out = _write_outbox_entry(media_path, meta)
    print(f"[force_post] Wrote outbox entry -> {out}")
    print(f"[force_post] Success: queued {media_path.name}")
    return 0


if __name__ == "__main__":
    import sys as _sys
    try:
        rc = main()
        raise SystemExit(rc)
    except KeyboardInterrupt:
        print("[force_post] Interrupted by user", file=_sys.stderr)
        raise SystemExit(130)
