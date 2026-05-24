import os
import time
import json
import shutil
import logging
import subprocess
from pathlib import Path

BASE = Path("nodes/ai_lady_instagram")
OUTBOX = Path("outbox")
QUARANTINE = OUTBOX / "quarantine"
PREPARED = Path(os.environ.get("POSTER_PREPARED_DIR", "outbox/prepared"))
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "watcher.log"

CONF_THRESHOLD = float(os.environ.get("POSTER_CONFIDENCE_THRESHOLD", "0.8"))
FORCE_MEDIA = os.environ.get("POSTER_FORCE_MEDIA")
PYTHON = os.environ.get("PYTHON", "python")

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)


def read_meta(media: Path) -> dict:
    try:
        meta = media.with_suffix(media.suffix + ".meta.json")
        if meta.exists():
            return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def quarantine_media(media: Path, reason: str):
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    dest = QUARANTINE / media.name
    try:
        shutil.move(str(media), str(dest))
        meta = media.with_suffix(media.suffix + ".meta.json")
        if meta.exists():
            shutil.move(str(meta), str(dest.with_suffix(dest.suffix + ".meta.json")))
    except Exception:
        pass
    logging.warning(f"Media quarantined: {media} — {reason}")


def pick_media() -> Path | None:
    images = []
    videos = []

    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        images.extend(OUTBOX.glob(ext))

    for ext in ("*.mp4", "*.mov", "*.m4v", "*.webm"):
        videos.extend(OUTBOX.glob(ext))

    images = [p for p in images if p.is_file()]
    videos = [p for p in videos if p.is_file()]

    if FORCE_MEDIA == "image":
        pool = images
    elif FORCE_MEDIA == "video":
        pool = videos
    else:
        pool = images + videos

    if not pool:
        return None

    return sorted(pool, key=lambda p: p.stat().st_mtime)[0]


def run_poster(media: Path, caption: str) -> bool:
    cmd = [
        PYTHON,
        "nodes/ai_lady_instagram/poster_retry.py",
        str(media),
        caption
    ]

    logging.info(f"Running poster: {' '.join(cmd)}")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        logging.info(proc.stdout)
        if proc.stderr:
            logging.error(proc.stderr)

        return proc.returncode == 0
    except Exception as e:
        logging.exception(f"Poster execution failed: {e}")
        return False


def main_loop():
    logging.info("Watcher started.")

    while True:
        try:
            media = pick_media()
            if not media:
                time.sleep(10)
                continue

            meta = read_meta(media)
            caption = meta.get("caption", "A day in the life")
            confidence = float(meta.get("confidence", 1.0))

            if confidence < CONF_THRESHOLD:
                quarantine_media(media, f"confidence {confidence} < threshold {CONF_THRESHOLD}")
                continue

            ok = run_poster(media, caption)
            if ok:
                try:
                    PREPARED.mkdir(parents=True, exist_ok=True)
                    dest = PREPARED / media.name
                    shutil.move(str(media), str(dest))

                    meta_src = media.with_suffix(media.suffix + ".meta.json")
                    if meta_src.exists():
                        shutil.move(str(meta_src), str(dest.with_suffix(dest.suffix + ".meta.json")))
                except Exception:
                    pass

                logging.info(f"Posted successfully: {media}")
            else:
                quarantine_media(media, "poster failed")

        except Exception as e:
            logging.exception(f"Watcher loop error: {e}")

        time.sleep(5)


if __name__ == "__main__":
    main_loop()
