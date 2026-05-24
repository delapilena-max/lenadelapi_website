# nodes/ai_lady_instagram/generator.py
"""
Generator with Kling Pro integration, atomic render, caching, and robust failure artifacts.
- Calls Kling for realism/style parameters and caches the response to outbox/<name>.kling.json
- Renders to a temp file and atomically moves the final MP4 into outbox/
- Writes outbox/<name>.txt (caption) and outbox/<name>.prompt.txt (Kling prompt)
- Writes outbox/<name>.render.err on ffmpeg failure
Usage:
  python nodes/ai_lady_instagram/generator.py --name content_test --caption "My caption" --prompt "short prompt for Kling"
"""

from pathlib import Path
import subprocess
import argparse
import os
import json
import time
import logging
import requests
import sys

# Basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUTBOX = Path("outbox")
OUTBOX.mkdir(exist_ok=True)

# Kling defaults and env
KLING_API_KEY = os.environ.get("KLING_API_KEY")
KLING_API_URL = os.environ.get("KLING_API_URL", "https://api.kling.ai/v1")
KLING_TIMEOUT = 15  # seconds

def call_kling_for_style(name: str, prompt: str, max_attempts: int = 4) -> dict:
    """
    Call Kling Pro to get realism/style parameters.
    Caches response to outbox/<name>.kling.json and writes outbox/<name>.prompt.txt.
    On repeated failure, writes a deterministic fallback and returns it.
    """
    cache_file = OUTBOX / f"{name}.kling.json"
    prompt_file = OUTBOX / f"{name}.prompt.txt"

    # Save the prompt for reproducibility
    prompt_file.write_text(prompt, encoding="utf-8")

    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            logging.warning("Failed to read existing Kling cache; will re-request.")

    if not KLING_API_KEY:
        logging.warning("KLING_API_KEY not set; using fallback style.")
        fallback = {"fallback": True, "style": "neutral", "color_grade": "cinematic", "text_style": {"font": None}}
        cache_file.write_text(json.dumps(fallback), encoding="utf-8")
        return fallback

    headers = {"Authorization": f"Bearer {KLING_API_KEY}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "mode": "realism", "quality": "pro"}

    for attempt in range(1, max_attempts + 1):
        try:
            time.sleep(0.15)  # tiny throttle to avoid bursts
            r = requests.post(f"{KLING_API_URL}/style", headers=headers, json=payload, timeout=KLING_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                cache_file.write_text(json.dumps(data), encoding="utf-8")
                logging.info("Kling style fetched and cached.")
                return data
            elif 500 <= r.status_code < 600:
                logging.warning("Kling server error %s; retrying (attempt %d)", r.status_code, attempt)
                time.sleep(2 ** attempt)
                continue
            else:
                logging.warning("Kling returned status %s; using fallback.", r.status_code)
                break
        except requests.RequestException as e:
            logging.warning("Kling request exception: %s; attempt %d", e, attempt)
            time.sleep(2 ** attempt)

    # deterministic fallback
    fallback = {"fallback": True, "style": "neutral", "color_grade": "cinematic", "text_style": {"font": None}}
    cache_file.write_text(json.dumps(fallback), encoding="utf-8")
    logging.info("Using Kling fallback style and cached it.")
    return fallback

def build_ffmpeg_command(tmp_path: Path, kling_style: dict, overlay_text: str = None) -> list:
    """
    Build an ffmpeg command list based on Kling style parameters.
    This example maps a simple color_grade to a basic filter; extend as needed.
    Avoids fontfile usage to reduce fontconfig issues on Windows.
    """
    vf_filters = []

    # Simple color grade mapping (extend with LUTs or more complex chains if available)
    color_grade = kling_style.get("color_grade", "none")
    if color_grade == "cinematic":
        # slight contrast and saturation boost
        vf_filters.append("eq=contrast=1.1:saturation=1.15")
    elif color_grade == "desaturated":
        vf_filters.append("eq=saturation=0.7")
    # else: no color grade

    # Optional overlay text (drawtext) - avoid fontfile to reduce fontconfig dependency
    if overlay_text:
        # escape single quotes in overlay_text for ffmpeg drawtext
        safe_text = overlay_text.replace("'", r"\'")
        drawtext = f"drawtext=text='{safe_text}':fontsize=36:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2"
        vf_filters.append(drawtext)

    vf = ",".join(vf_filters) if vf_filters else None

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=640x360:d=3",
        "-t", "3",
    ]

    if vf:
        cmd += ["-vf", vf]

    cmd += ["-c:v", "libx264", str(tmp_path)]
    return cmd

def render_to_temp_and_move(name: str, caption: str, prompt: str) -> int:
    """
    High-level render flow:
    - call Kling for style
    - build ffmpeg command
    - run ffmpeg to a temp file
    - on success, atomically move to outbox/<name>.mp4 and write caption
    - on failure, write outbox/<name>.render.err
    Returns ffmpeg exit code (0 on success).
    """
    tmp = OUTBOX / f"{name}.mp4.tmp"
    final = OUTBOX / f"{name}.mp4"
    kling_data = call_kling_for_style(name, prompt)

    # Optionally use Kling-provided text style or overlay text
    overlay_text = None
    if kling_data.get("text"):
        overlay_text = kling_data.get("text")
    else:
        # default overlay for testing; set to None to skip
        overlay_text = None

    ffmpeg_cmd = build_ffmpeg_command(tmp, kling_data, overlay_text)

    logging.info("Running ffmpeg: %s", " ".join(ffmpeg_cmd))
    proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        err_text = proc.stderr or "ffmpeg failed with no stderr"
        (OUTBOX / f"{name}.render.err").write_text(err_text, encoding="utf-8")
        logging.error("ffmpeg failed for %s; wrote render.err", name)
        # cleanup tmp if present
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return proc.returncode

    # sanity checks
    if not tmp.exists() or tmp.stat().st_size == 0:
        (OUTBOX / f"{name}.render.err").write_text("render produced empty file", encoding="utf-8")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        logging.error("ffmpeg produced empty file for %s", name)
        return 1

    # atomic move
    tmp.replace(final)
    # write caption and a copy of the prompt for reproducibility
    (OUTBOX / f"{name}.txt").write_text(caption, encoding="utf-8")
    (OUTBOX / f"{name}.prompt.txt").write_text(prompt, encoding="utf-8")
    logging.info("Rendered and moved final file to %s", final)
    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Base name for output files (no extension)")
    parser.add_argument("--caption", required=True, help="Caption text to write to outbox/<name>.txt")
    parser.add_argument("--prompt", required=False, default="Make this look realistic and cinematic", help="Prompt to send to Kling for realism/style")
    args = parser.parse_args()

    rc = render_to_temp_and_move(args.name, args.caption, args.prompt)
    if rc != 0:
        print(f"Render failed (exit {rc}). See outbox/{args.name}.render.err", file=sys.stderr)
        sys.exit(rc)

    print(f"Rendered and wrote outbox/{args.name}.mp4 and caption.")

if __name__ == "__main__":
    main()
