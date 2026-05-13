"""
music_fetcher.py - Bulk download royalty-free background music into assets/audio/tracks/
Primary source: Jamendo API (free client_id at developers.jamendo.com)
Usage: python music_fetcher.py --count 100
"""

import os, sys, time, argparse, logging, requests
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TRACKS_DIR   = Path("assets/audio/tracks")
JAMENDO_BASE = "https://api.jamendo.com/v3.0"
BRAINROT_TAGS = ["lofi", "ambient", "chillout", "electronic", "upbeat", "pop", "indie", "acoustic", "relaxing"]

def get_client_id():
    cid = os.environ.get("JAMENDO_CLIENT_ID", "")
    if not cid:
        raise EnvironmentError("Set JAMENDO_CLIENT_ID env var.\nGet a free key at: https://devportal.jamendo.com/signup")
    return cid

def fetch_track_page(client_id, tag, page=1, limit=50):
    params = {"client_id": client_id, "format": "json", "limit": limit,
              "offset": (page - 1) * limit, "tags": tag, "audioformat": "mp32",
              "include": "musicinfo", "order": "popularity_total"}
    try:
        resp = requests.get(f"{JAMENDO_BASE}/tracks/", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        log.warning("Jamendo fetch failed (tag=%s page=%d): %s", tag, page, e)
        return []

def download_track(track, out_dir):
    track_id  = track.get("id", "unknown")
    name      = track.get("name", track_id)
    audio_url = track.get("audio", "")
    artist    = track.get("artist_name", "unknown").replace(" ", "_")
    if not audio_url:
        return False
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:50]
    out_path  = out_dir / f"{artist}__{safe_name}__{track_id}.mp3"
    if out_path.exists():
        log.info("Already exists: %s", out_path.name)
        return True
    try:
        resp = requests.get(audio_url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        log.info("Downloaded: %s (%d KB)", out_path.name, out_path.stat().st_size // 1024)
        return True
    except Exception as e:
        log.warning("Failed: %s — %s", out_path.name, e)
        try: out_path.unlink()
        except OSError: pass
        return False

def fetch_library(count=100):
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    client_id  = get_client_id()
    downloaded = 0
    per_tag    = max(1, count // len(BRAINROT_TAGS))
    log.info("Fetching %d tracks across %d tags -> %s", count, len(BRAINROT_TAGS), TRACKS_DIR)
    for tag in BRAINROT_TAGS:
        if downloaded >= count: break
        log.info("--- Tag: %s ---", tag)
        page, tag_count = 1, 0
        while tag_count < per_tag and downloaded < count:
            tracks = fetch_track_page(client_id, tag, page=page, limit=50)
            if not tracks: break
            for track in tracks:
                if downloaded >= count: break
                if download_track(track, TRACKS_DIR):
                    downloaded += 1; tag_count += 1
                time.sleep(0.3)
            page += 1
    log.info("Done. %d tracks in %s", downloaded, TRACKS_DIR)
    return downloaded

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    args = ap.parse_args()
    try:
        fetch_library(args.count)
    except EnvironmentError as e:
        print(f"\n{e}\n"); sys.exit(1)
