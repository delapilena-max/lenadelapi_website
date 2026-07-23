from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, date
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.media_host.r2_uploader import upload_file_to_r2
from pipeline.lena_publish_quality_gate import quality_gate_media, mark_published_fingerprint

BASE_DIR = ROOT / "pipeline" / "higgsfield_library" / "lena"
STATE_PATH = ROOT / "pipeline" / "state" / "lena_r2_publish_state.json"
LOG_DIR = ROOT / "pipeline" / "publish_logs"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

BLOCKED_PARTS = {
    "bad_identity",
    "blocked_raw_reference",
    "raw_reference",
    "raw_references",
    "reference",
    "references",
    "assets",
    "public_media",
    "nodes",
    "profiles",
    "_patch_tmp",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_stem(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"[^a-z0-9_-]+", "-", stem).strip("-")
    return stem or "media"


def fingerprint(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:12]


def media_type(path: Path) -> str:
    if path.suffix.lower() in VIDEO_EXTS:
        return "video"
    return "photo"


QUEUE_DIR = ROOT / "pipeline" / "queue"
PUBLISH_DATE = os.environ.get("LENA_PUBLISH_DATE") or date.today().isoformat()

BANNED_CAPTION_TERMS = [
    "AI",
    "artificial intelligence",
    "virtual influencer",
    "synthetic",
    "digital human",
    "bot",
    "generated",
    "avatar",
    "fake",
    "computer generated",
]


def clean_caption_public(caption: str) -> str:
    cleaned = caption or ""
    for term in BANNED_CAPTION_TERMS:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def slot_id_from_media_path(path: Path) -> str:
    stem = path.stem
    for suffix in ["_video", "_feed", "_seed", "_image", "_photo"]:
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
    return stem


def find_caption_in_obj(obj) -> str | None:
    if isinstance(obj, dict):
        for key in ["caption", "post_caption", "instagram_caption"]:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        meta = obj.get("metadata")
        if isinstance(meta, dict):
            found = find_caption_in_obj(meta)
            if found:
                return found

    return None


def caption_from_queue_or_brain(path: Path) -> str | None:
    slot_id = slot_id_from_media_path(path)
    queue_path = QUEUE_DIR / f"{slot_id}.json"

    if queue_path.exists():
        try:
            data = json.loads(queue_path.read_text(encoding="utf-8"))
            found = find_caption_in_obj(data)
            if found and found.strip().lower() not in {"lena", "new post"}:
                return clean_caption_public(found)
        except Exception:
            pass

    # Fallback: generate a Prompt Brain caption from the slot id.
    try:
        from pipeline.prompting.lena_prompt_brain import generate_prompt_package

        date_part = "-".join(slot_id.split("-")[:3])
        package = generate_prompt_package(date_part, slot_id, media_type(path), None)
        caption = package.get("caption")
        if caption:
            return clean_caption_public(caption)
    except Exception:
        pass

    return None


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"published": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"published": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_safe_media(path: Path) -> bool:
    if not path.is_file():
        return False

    # For photo feed posts, prefer feed-safe 4:5 derivatives over raw vertical seed images.
    # Example: 2026-06-10-01-photo_feed.png replaces 2026-06-10-01-photo_seed.png.
    if path.suffix.lower() in IMAGE_EXTS and path.name.endswith("_seed.png"):
        feed_copy = path.with_name(path.name.replace("_seed.png", "_feed.png"))
        if feed_copy.exists():
            return False

    if path.suffix.lower() not in MEDIA_EXTS:
        return False

    # Video seed images are private generation intermediates, not public photos.
    if path.suffix.lower() in IMAGE_EXTS and "video_seed" in path.stem.lower():
        return False

    try:
        path.relative_to(BASE_DIR)
    except ValueError:
        return False

    parts = {p.lower() for p in path.parts}
    if parts & BLOCKED_PARTS:
        return False

    blocked_tokens = ("bad", "blocked", "raw", "reference")
    if any(token in part for part in parts for token in blocked_tokens):
        return False

    return True



def slot_order_key(path: Path) -> tuple:
    """
    Sort newest production date first, then v1.2 slot order ascending.
    Example:
      2026-06-10-01-photo_seed.png
      2026-06-10-02-photo_seed.png
      2026-06-10-03-video_video.mp4
      2026-06-10-04-photo_seed.png
      2026-06-10-05-photo_seed.png
    """
    name = path.name
    m = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{2})-(photo|video)", name)
    if m:
        date_str = m.group(1)
        slot_num = int(m.group(2))
        # Newest date first, slot order first within that date.
        return (-int(date_str.replace("-", "")), slot_num, name)
    # Fallback: newer files first, after properly named production files.
    return (0, 999, -path.stat().st_mtime_ns)


def all_candidates() -> list[Path]:
    """
    v1.2 safety rule:
    Publish only from the selected day's queue files, never from old library inventory.
    Default date is today; override with LENA_PUBLISH_DATE=YYYY-MM-DD.
    """
    files: list[Path] = []

    for qpath in sorted(QUEUE_DIR.glob(f"{PUBLISH_DATE}-*.json")):
        try:
            data = json.loads(qpath.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        meta = data.get("metadata") or {}
        if data.get("status") == "rejected" or meta.get("manual_rejected") is True:
            continue

        raw = data.get("media_path")
        if not raw:
            continue

        media_path = Path(str(raw))
        if not media_path.is_absolute():
            media_path = ROOT / media_path

        if is_safe_media(media_path):
            files.append(media_path)

    files.sort(key=slot_order_key)
    return files


def next_unpublished(media_type_filter: str | None = None) -> Path | None:
    state = load_state()
    published = state.get("published", {})

    for path in all_candidates():
        if media_type_filter and media_type(path) != media_type_filter:
            continue
        fp = fingerprint(path)
        if fp not in published:
            return path

    return None


def mark(path: Path, status: str, extra: dict | None = None) -> dict:
    state = load_state()
    fp = fingerprint(path)
    state.setdefault("published", {})[fp] = {
        "status": status,
        "path": str(path),
        "fingerprint": fp,
        "marked_at_utc": now_iso(),
        **(extra or {}),
    }
    save_state(state)
    return state["published"][fp]


def r2_key_for(path: Path, fp: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"lena/{day}/{safe_stem(path.name)}-{fp}{path.suffix.lower()}"



def is_dance_video_requiring_music(path: Path) -> bool:
    slot_id = slot_id_from_media_path(path)
    queue_path = QUEUE_DIR / f"{slot_id}.json"

    if not queue_path.exists():
        return False

    try:
        data = json.loads(queue_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return False

    meta = data.get("metadata") or {}
    final_intent = str(meta.get("final_intent") or "").lower()
    reference_mode = str(meta.get("reference_mode") or "").lower()
    motion_style = str(meta.get("motion_style") or "").lower()
    caption = str(data.get("caption") or "").lower()

    return (
        "dance" in final_intent
        or "dance" in reference_mode
        or "dance" in motion_style
        or "dance" in caption
        or "tiktok" in caption
    )


def publish_path(path: Path, caption: str) -> dict:
    caption = clean_caption_public(caption)
    fp = fingerprint(path)
    mtype = media_type(path)

    if (
        mtype == "video"
        and is_dance_video_requiring_music(path)
        and os.environ.get("LENA_ALLOW_SILENT_DANCE_VIDEO", "") != "1"
    ):
        raise RuntimeError(
            "Dance video requires music selection before publishing. "
            "Do not auto-publish silent dance videos. "
            "Upload manually to TikTok/IG Reels and pick music in-app, "
            "or set LENA_ALLOW_SILENT_DANCE_VIDEO=1 only for an intentional override."
        )

    gate = quality_gate_media(media_path=path, caption=caption, media_type=mtype)
    if not gate.ok:
        raise RuntimeError("Publish blocked by quality gate: " + "; ".join(gate.errors))

    key = r2_key_for(path, fp)

    upload = upload_file_to_r2(path, key)
    public_url = upload["public_url"]

    post_id = f"lena_auto_{fp}"

    cmd = [
        sys.executable,
        str(ROOT / "tools" / "instagram_publish_smoke.py"),
        "--media-url",
        public_url,
        "--media-type",
        mtype,
        "--caption",
        caption,
        "--post-id",
        post_id,
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )

    result = {
        "ok": proc.returncode == 0,
        "source_path": str(path),
        "fingerprint": fp,
        "media_type": mtype,
        "quality_gate": gate.to_dict(),
        "r2": upload,
        "publish_stdout": proc.stdout,
        "publish_stderr": proc.stderr,
        "publish_returncode": proc.returncode,
        "timestamp_utc": now_iso(),
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"lena_auto_publish_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{fp}.json"
    log_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["log_path"] = str(log_path)

    if proc.returncode != 0:
        print(json.dumps(result, indent=2))
        raise SystemExit(proc.returncode)

    mark(path, "published", {
        "r2_key": key,
        "public_url": public_url,
        "log_path": str(log_path),
    })

    print(json.dumps(result, indent=2))
    if result.get("ok"):
        mark_published_fingerprint(path, extra={"media_type": mtype, "r2_key": key})

    return result



def _auto_caption_for_publish(path: Path) -> str:
    """Return queue/Prompt Brain caption using whatever caption helper this file has."""
    for name in (
        "caption_from_queue_or_brain",
        "caption_for_media",
        "caption_for_media_path",
        "caption_for_path",
        "resolve_caption_for_media",
        "resolve_caption",
    ):
        fn = globals().get(name)
        if callable(fn):
            try:
                value = fn(path)
            except TypeError:
                continue
            except Exception:
                continue
            if isinstance(value, str) and value.strip():
                return clean_caption_public(value)
    return ""

# LEGACY -- DISABLED FOR SAFETY
# This script bypassed the FINAL_PUBLISH_APPROVED_BY_NICOLAS sidecar gate.
# Must not be used for Lena production until rebuilt to enforce the gate.
# Use the gated connector (lena_publish_instagram_feed_v2_8.py) instead.
def main() -> int:
    print(
        "DISABLED_FOR_SAFETY: lena_publish_next_r2.py is disabled."
        " Use gated connector path requiring FINAL_PUBLISH_APPROVED_BY_NICOLAS."
    )
    return 1
    # ── unreachable legacy body ───────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Upload next fresh Lena media to R2 and publish to Instagram.")
    parser.add_argument("--caption", default=os.environ.get("LENA_DEFAULT_CAPTION", ""), help="Instagram caption override. Empty uses queue/Prompt Brain caption.")
    parser.add_argument("--only-media-type", choices=["photo", "video"], default="", help="Only publish this media type.")
    parser.add_argument("--dry-run", action="store_true", help="Show the next file without uploading or posting.")
    parser.add_argument("--mark-latest-published", action="store_true", help="Mark latest safe media as already published.")
    args = parser.parse_args()

    candidates = all_candidates()

    if args.mark_latest_published:
        if not candidates:
            print(json.dumps({"ok": False, "reason": "no safe media found"}, indent=2))
            return 1
        marked = mark(candidates[0], "already_published_manual_mark", {"reason": "smoke test already posted"})
        print(json.dumps({"ok": True, "marked": marked}, indent=2))
        return 0

    path = next_unpublished(args.only_media_type or None)
    if not path:
        print(json.dumps({"ok": True, "publish_date": PUBLISH_DATE, "status": "no_unpublished_media_found"}, indent=2))
        return 0

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "publish_date": PUBLISH_DATE,
            "next_media": str(path),
            "media_type": media_type(path),
            "fingerprint": fingerprint(path),
        }, indent=2))
        return 0

    caption = (args.caption or "").strip()
    if caption == "Lena":
        caption = ""
    if not caption:
        caption = _auto_caption_for_publish(path)
    if not caption or caption == "Lena":
        raise RuntimeError("No non-default queue/Prompt Brain caption available for selected media.")
    if not caption or caption.strip().lower() in {"lena", "auto", "default", "new post"}:
        caption = caption_from_queue_or_brain(path) or caption

    publish_path(path, caption)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
