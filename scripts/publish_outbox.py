# scripts/publish_outbox.py
# One-step publisher: process newest pipeline/outbox/ai_lady/post_request_*.json
# Usage: python scripts/publish_outbox.py

import json
import shutil
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUTBOX_DIR = ROOT / "pipeline" / "outbox" / "ai_lady"
PUBLISHED_DIR = ROOT / "pipeline" / "published" / "ai_lady"
PROFILE_DIR = ROOT / "nodes" / "ai_lady_instagram"
PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

def find_latest_outbox():
    files = sorted(OUTBOX_DIR.glob("post_request_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[publish] ERROR reading {p}: {e}", file=sys.stderr)
        return None

def write_json(p: Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def append_history(entry):
    hist_path = PROFILE_DIR / "history.json"
    history = []
    if hist_path.exists():
        try:
            history = json.loads(hist_path.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append(entry)
    write_json(hist_path, history)
    print(f"[publish] Appended to history: {hist_path}")

def update_last_post(entry):
    last_path = PROFILE_DIR / "last_post.json"
    write_json(last_path, entry)
    print(f"[publish] Wrote last_post: {last_path}")

def main():
    outbox_file = find_latest_outbox()
    if not outbox_file:
        print("[publish] No outbox post_request_*.json found.", file=sys.stderr)
        return 1

    print(f"[publish] Processing outbox: {outbox_file}")
    data = load_json(outbox_file)
    if not data:
        return 2

    media_rel = data.get("media")
    if not media_rel:
        print("[publish] No 'media' field in outbox JSON.", file=sys.stderr)
        return 3

    media_path = ROOT / Path(media_rel)
    if not media_path.exists():
        print(f"[publish] Media file not found: {media_path}", file=sys.stderr)
        return 4

    # Copy media and meta to published folder
    dest_media = PUBLISHED_DIR / media_path.name
    try:
        shutil.copy2(media_path, dest_media)
        print(f"[publish] Copied media -> {dest_media}")
    except Exception as e:
        print(f"[publish] ERROR copying media: {e}", file=sys.stderr)
        return 5

    meta_src = media_path.with_suffix(media_path.suffix + ".meta.json")
    if meta_src.exists():
        try:
            shutil.copy2(meta_src, dest_media.with_suffix(dest_media.suffix + ".meta.json"))
            print(f"[publish] Copied meta -> {dest_media.with_suffix(dest_media.suffix + '.meta.json')}")
        except Exception as e:
            print(f"[publish] WARNING copying meta: {e}", file=sys.stderr)

    # Build history/last_post entry
    ts_now = datetime.utcnow().isoformat()
    history_entry = {
        "ts": ts_now,
        "theme": data.get("meta", {}).get("theme") or data.get("meta", {}).get("caption") or "unknown",
        "media": str(dest_media).replace("\\", "\\\\"),
        "prefer": data.get("meta", {}).get("format") or "image"
    }

    append_history(history_entry)
    update_last_post({"ts": ts_now, "media": str(dest_media), "source": data.get("source", "unknown")})

    print(f"[publish] Done. Published {dest_media.name}")
    return 0

if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
    