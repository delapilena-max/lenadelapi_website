"""
free_video_gen.py — ReelForge Zero-Cost Video Engine
Permanent free replacement for Kling AI.
Uses: FFmpeg (Ken Burns animation) + Pexels API (free stock B-roll)
Cost: $0 forever. No API credits. No subscriptions.

KLING_MODE options:
  mock        → dummy black video, for testing only
  free_local  → this file, Ken Burns + Pexels, $0 production
  kling       → real Kling API (costs money, avoid)
"""

import os
import sys
import uuid
import json
import random
import subprocess
import urllib.request
import urllib.parse
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ── Pexels free API ──────────────────────────────────────────
# Sign up free at https://www.pexels.com/api/
# 200 requests/hour, 20,000/month, commercial use allowed
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_CACHE_DIR = "output/pexels_cache"


# ════════════════════════════════════════════════════════════
# 1. KEN BURNS — Animate any still image into a video clip
#    Pure FFmpeg. No model. No API. Runs on any machine. $0.
# ════════════════════════════════════════════════════════════

def ken_burns(
    image_path: str,
    duration: int = 6,
    output_path: str = None,
    effect: str = "random",   # zoom_in | zoom_out | pan_left | pan_right | random
    resolution: str = "1080x1920",
) -> str:
    if output_path is None:
        os.makedirs("output/clips", exist_ok=True)
        output_path = f"output/clips/kb_{uuid.uuid4().hex[:8]}.mp4"

    w, h = resolution.split("x")
    fps = 30
    total_frames = duration * fps

    effects = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
    if effect == "random":
        effect = random.choice(effects)

    if effect == "zoom_in":
        zoom_expr = "'min(zoom+0.0008,1.3)'"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "zoom_out":
        zoom_expr = "'if(eq(on,1),1.3,max(zoom-0.0008,1.0))'"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "pan_left":
        zoom_expr = "'1.2'"
        x_expr = "'iw/2-(iw/zoom/2)+on*0.3'"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "pan_right":
        zoom_expr = "'1.2'"
        x_expr = "'iw/2-(iw/zoom/2)-on*0.3'"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = "'min(zoom+0.0008,1.3)'"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    vf = (
        f"zoompan=z={zoom_expr}:d={total_frames}"
        f":x='{x_expr}':y='{y_expr}'"
        f":s={w}x{h}:fps={fps}"
        f",setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-shortest",
        "-loglevel", "error",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True)
        log.info(f"[FREE VIDEO] Ken Burns ({effect}) → {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        log.error(f"[FREE VIDEO] ffmpeg failed: {e}")
        raise


# ════════════════════════════════════════════════════════════
# 2. PEXELS — Free stock B-roll video search & download
#    Free tier: 200 req/hr, 20k/month, commercial use OK
#    Sign up: https://www.pexels.com/api/
# ════════════════════════════════════════════════════════════

def fetch_pexels_broll(
    query: str,
    duration_max: int = 15,
    output_path: str = None,
    orientation: str = "portrait",
) -> str:
    if not PEXELS_API_KEY:
        log.warning("[PEXELS] No PEXELS_API_KEY in .env — falling back to Ken Burns")
        return None

    os.makedirs(PEXELS_CACHE_DIR, exist_ok=True)

    safe_query = query.replace(" ", "_")[:30]
    cache_file = os.path.join(PEXELS_CACHE_DIR, f"{safe_query}.mp4")
    if os.path.exists(cache_file):
        log.info(f"[PEXELS] Cache hit → {cache_file}")
        return cache_file

    params = urllib.parse.urlencode({
        "query": query,
        "orientation": orientation,
        "size": "medium",
        "per_page": 10,
    })
    url = f"https://api.pexels.com/videos/search?{params}"
    req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log.error(f"[PEXELS] API error: {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        log.warning(f"[PEXELS] No results for '{query}'")
        return None

    for video in videos:
        if video.get("duration", 999) > duration_max:
            continue
        files = video.get("video_files", [])
        files_sorted = sorted(
            [f for f in files if f.get("width", 0) <= 1080],
            key=lambda f: f.get("width", 0), reverse=True
        )
        if not files_sorted:
            continue

        video_url = files_sorted[0]["link"]
        dest = output_path or cache_file

        try:
            urllib.request.urlretrieve(video_url, dest)
            log.info(f"[PEXELS] Downloaded '{query}' → {dest}")
            return dest
        except Exception as e:
            log.error(f"[PEXELS] Download failed: {e}")
            return None

    log.warning(f"[PEXELS] No suitable video found for '{query}'")
    return None


# ════════════════════════════════════════════════════════════
# 3. MASTER DISPATCHER — Drop-in Kling replacement
# ════════════════════════════════════════════════════════════

def generate_video(
    prompt: str,
    image_path: str = None,
    duration: int = 6,
    output_path: str = None,
    **kwargs,
) -> str:
    mode = os.environ.get("KLING_MODE", "free_local").strip().lower()

    if mode == "mock":
        return _generate_mock(prompt, duration, output_path)
    elif mode == "free_local":
        return _generate_free(prompt, image_path, duration, output_path)
    elif mode == "kling":
        log.warning("[KLING] Real Kling API called — this costs credits!")
        from kling_api import call_kling
        return call_kling(prompt, image_path=image_path, duration=duration, **kwargs)
    else:
        raise ValueError(f"Unknown KLING_MODE='{mode}'. Use: mock | free_local | kling")


def _generate_free(prompt, image_path, duration, output_path):
    if image_path and os.path.exists(str(image_path)):
        log.info(f"[FREE VIDEO] Animating image with Ken Burns: {image_path}")
        return ken_burns(image_path, duration=duration, output_path=output_path)

    log.info(f"[FREE VIDEO] No image — fetching Pexels B-roll for: '{prompt}'")
    pexels_path = fetch_pexels_broll(prompt, duration_max=duration + 5, output_path=output_path)
    if pexels_path:
        return pexels_path

    log.warning("[FREE VIDEO] All sources failed — using dummy video")
    return _generate_mock(prompt, duration, output_path)


def _generate_mock(prompt, duration, output_path):
    if output_path is None:
        os.makedirs("output/mock_videos", exist_ok=True)
        output_path = f"output/mock_videos/mock_{uuid.uuid4().hex[:8]}.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1080x1920:d={duration}:rate=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", "drawtext=text='[MOCK VIDEO]':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
        "-t", str(duration), "-c:v", "libx264", "-c:a", "aac",
        "-shortest", "-loglevel", "error", output_path,
    ]
    try:
        subprocess.run(cmd, check=True)
    except Exception:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"")
    log.info(f"[MOCK VIDEO] {output_path}")
    return output_path
