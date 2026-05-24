# nodes/life_engine.py
# Self-contained, pasteable implementation of the engine module with safe publish logic.
# Drop this file into nodes/life_engine.py (overwrite existing) and run your usual commands.
#
# Behavior:
# - Loads profile from PROFILE_PATH (if present)
# - Decides whether to post via _should_post(profile)
# - Picks the first media file in the provided outbox directory (simple selection)
# - Builds a history entry and appends it to HISTORY
# - Performs a guarded publish step: backup LAST_POST, move media to pipeline/published/ai_lady,
#   update history entry to point to published path, write LAST_POST, and rollback on failure.
#
# NOTE: This is intentionally conservative and defensive. Adjust selection logic and metadata
# generation to match your real engine behavior.

import json
import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# --- Constants (match your environment) ---
PROFILE_PATH = Path("nodes/ai_lady_instagram/profile.json")
HISTORY = Path("nodes/ai_lady_instagram/history.json")
LAST_POST = Path("nodes/ai_lady_instagram/last_post.json")

# --- Utilities ---------------------------------------------------------------

def _load_profile() -> Dict[str, Any]:
    """Load profile JSON if present, otherwise return a sensible default."""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    # default profile used earlier in the session
    return {
        "name": "AI Lady",
        "handle": "lenadelapi",
        "posting_preferences": {
            "post_probability": 1.0,
            "min_days_between": 0
        },
        "caption_templates": ["Tiny moment: {lead}"]
    }

def _read_last_post_time() -> Optional[datetime]:
    """Read LAST_POST and return a datetime or None."""
    try:
        if LAST_POST.exists():
            data = json.loads(LAST_POST.read_text(encoding="utf-8"))
            ts = data.get("last_post_ts")
            if ts:
                return datetime.fromisoformat(ts)
    except Exception:
        pass
    return None

def _should_post(profile: Dict[str, Any]) -> bool:
    """Decide whether to post based on profile preferences."""
    prefs = profile.get("posting_preferences", {})
    prob = prefs.get("post_probability", 1.0)
    min_days = prefs.get("min_days_between", 0)
    # probabilistic check
    if prob < 1.0 and random.random() > prob:
        return False
    # cadence check
    last = _read_last_post_time()
    if last and (datetime.utcnow() < last + timedelta(days=min_days)):
        return False
    return True

def _ensure_history():
    """Ensure history file exists and is a JSON array."""
    if not HISTORY.exists():
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text("[]", encoding="utf-8")

def _append_history(entry: Dict[str, Any]):
    """Prepend an entry to the history JSON array (most recent first)."""
    _ensure_history()
    try:
        hist = json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        hist = []
    # Prepend new entry
    hist.insert(0, entry)
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

# --- Media selection (simple) ------------------------------------------------

def _select_media_from_outbox(outbox_dir: str) -> Optional[str]:
    """
    Very simple selection: pick the first file in the outbox directory.
    Returns the path string or None if nothing found.
    """
    p = Path(outbox_dir)
    if not p.exists() or not p.is_dir():
        return None
    # consider common media extensions
    exts = [".mp4", ".mov", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webm"]
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix.lower() in exts:
            return str(f)
    return None

# --- Main engine function ---------------------------------------------------

def create_post_media(outbox_dir: str) -> str:
    """
    Main entry: create (select) a post media from outbox_dir, append history,
    and perform a safe publish (backup last_post, move file, update history, write last_post).
    Returns the final path (published path if publish succeeded, original path otherwise),
    or empty string if nothing was created/selected.
    """
    profile = _load_profile()
    if not _should_post(profile):
        # Engine decides not to post now
        return ""

    # Select media
    path = _select_media_from_outbox(outbox_dir)
    if not path:
        return ""

    # Build a minimal metadata object (in real engine this would be richer)
    meta = {
        "caption": profile.get("caption_templates", [""])[0].format(lead="small moment"),
        "theme": "unknown",
        "tags": [],
        "confidence": 0.9,
        "generated_at": int(datetime.utcnow().timestamp()),
        "format": "video" if Path(path).suffix.lower() in [".mp4", ".mov", ".webm"] else "image"
    }

    # Build history entry
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "theme": meta.get("theme"),
        "media": path,
        "prefer": "video" if meta["format"] == "video" else "image",
        "meta": meta,
        "metrics": {}
    }

    # Append to history (most recent first)
    try:
        _append_history(entry)
    except Exception as e:
        # If history append fails, still attempt to continue but warn
        print(f"[warning] failed to append history: {e}", file=sys.stderr)

    # --- safe publish: backup last_post, move media to published, update history, write last_post, rollback on error ---
    try:
        pub_dir = Path("pipeline") / "published" / "ai_lady"
        pub_dir.mkdir(parents=True, exist_ok=True)

        # prepare last_post paths
        last_post_path = LAST_POST if LAST_POST else None
        backup_path = None
        if last_post_path and last_post_path.exists():
            backup_path = last_post_path.with_suffix(last_post_path.suffix + ".bak")
            shutil.copy2(str(last_post_path), str(backup_path))

        # move media file to published
        src_path = Path(path)
        dest_path = pub_dir / src_path.name
        try:
            shutil.move(str(src_path), str(dest_path))
        except Exception as e_move:
            # restore last_post backup if move failed
            if backup_path and backup_path.exists() and last_post_path:
                shutil.copy2(str(backup_path), str(last_post_path))
            raise RuntimeError(f"Failed to move media to published: {e_move}")

        # update the history entry to point to published path
        try:
            if HISTORY and HISTORY.exists():
                hist = json.loads(HISTORY.read_text(encoding="utf-8"))
                # assume the most recent entry is the one we just appended
                if hist:
                    # If engine appends at front, update hist[0]; otherwise adjust as needed.
                    hist[0]["media"] = str(dest_path)
                    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e_hist:
            # attempt to move file back and restore last_post backup
            try:
                shutil.move(str(dest_path), str(src_path))
            except Exception:
                pass
            if backup_path and backup_path.exists() and last_post_path:
                shutil.copy2(str(backup_path), str(last_post_path))
            raise RuntimeError(f"Failed to update history after publish: {e_hist}")

        # write last_post safely
        try:
            now_iso = datetime.utcnow().isoformat()
            lp = {"last_post_ts": now_iso}
            if last_post_path:
                last_post_path.write_text(json.dumps(lp, ensure_ascii=False), encoding="utf-8")
            else:
                # fallback location if LAST_POST constant is not set
                Path("nodes/ai_lady_instagram/last_post.json").write_text(json.dumps(lp, ensure_ascii=False), encoding="utf-8")
        except Exception as e_lp:
            # rollback: move file back to outbox and restore last_post backup
            try:
                shutil.move(str(dest_path), str(src_path))
            except Exception:
                pass
            if backup_path and backup_path.exists() and last_post_path:
                shutil.copy2(str(backup_path), str(last_post_path))
            raise RuntimeError(f"Failed to write last_post.json: {e_lp}")

        # success: remove backup if present
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass

        # set path to published file for return
        path = str(dest_path)

    except Exception as e:
        # Log error to stderr and keep original path (or empty) as return value.
        try:
            print(f"[publish error] {e}", file=sys.stderr)
        except Exception:
            pass

    # Return the final path (published path on success)
    return path or ""

# --- If run as script for quick testing -------------------------------------

if __name__ == "__main__":
    # Simple CLI: python -c "from nodes import life_engine; print(life_engine.create_post_media('pipeline/outbox/ai_lady'))"
    if len(sys.argv) > 1:
        outbox = sys.argv[1]
    else:
        outbox = "pipeline/outbox/ai_lady"
    result = create_post_media(outbox)
    print("RETURN:", repr(result))
