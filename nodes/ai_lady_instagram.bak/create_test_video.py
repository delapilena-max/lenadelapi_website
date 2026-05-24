# nodes/ai_lady_instagram/create_test_video.py
# Creates a small test MP4 in outbox/content_test.mp4 and a caption file outbox/content_test.txt
# Usage:
# & .\.venv\Scripts\python.exe nodes/ai_lady_instagram\create_test_video.py
#
# Behavior:
# - If ffmpeg is available on PATH, it uses ffmpeg to synthesize a 3s black MP4 with "TEST" text.
# - Otherwise it attempts to download a small sample MP4 from a public URL.
# - Writes a caption file alongside the video.
# - Exits with code 0 on success, nonzero on failure.

import shutil
import subprocess
import sys
from pathlib import Path
import urllib.request
import tempfile

OUTBOX = Path("outbox")
OUTBOX.mkdir(parents=True, exist_ok=True)

VIDEO_PATH = OUTBOX / "content_test.mp4"
CAPTION_PATH = OUTBOX / "content_test.txt"

SAMPLE_DOWNLOAD_URL = "https://sample-videos.com/video123/mp4/240/big_buck_bunny_240p_1mb.mp4"
# If you prefer a different sample, replace the URL above.

def ffmpeg_available():
    return shutil.which("ffmpeg") is not None

def create_with_ffmpeg(target: Path):
    # Build ffmpeg command to create a 3-second black video with centered TEST text.
    # Use a font path that exists on Windows by default; if not found, omit drawtext.
    font_paths = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font = None
    for p in font_paths:
        if Path(p).exists():
            font = p
            break

    drawtext = ""
    if font:
        drawtext = f",drawtext=fontfile={font}:fontsize=36:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:text='TEST'"
    # ffmpeg filter chain
    vf = f"color=c=black:s=640x360:d=3{drawtext}"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", vf,
        "-c:v", "libx264",
        "-t", "3",
        str(target)
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            print("ffmpeg failed:", proc.stderr.strip())
            return False, proc.stderr
        return True, proc.stdout + proc.stderr
    except Exception as e:
        return False, str(e)

def download_sample(target: Path, url: str):
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            # write to temp then move
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(resp.read())
                tmp_path = Path(tmp.name)
        tmp_path.replace(target)
        return True, "downloaded"
    except Exception as e:
        return False, str(e)

def write_caption(path: Path, text: str):
    path.write_text(text, encoding="utf-8")

def main():
    # If file already exists, do nothing and report success
    if VIDEO_PATH.exists() and CAPTION_PATH.exists():
        print(f"Test video and caption already exist: {VIDEO_PATH.name}")
        sys.exit(0)

    print("Creating test video:", VIDEO_PATH)
    if ffmpeg_available():
        ok, out = create_with_ffmpeg(VIDEO_PATH)
        if not ok:
            print("ffmpeg creation failed, attempting download fallback.")
            ok2, out2 = download_sample(VIDEO_PATH, SAMPLE_DOWNLOAD_URL)
            if not ok2:
                print("ERROR: Could not create or download test video:", out2)
                sys.exit(1)
            else:
                print("Downloaded sample video as fallback.")
        else:
            print("Created test video with ffmpeg.")
    else:
        print("ffmpeg not found on PATH; attempting to download a sample video.")
        ok, out = download_sample(VIDEO_PATH, SAMPLE_DOWNLOAD_URL)
        if not ok:
            print("ERROR: Could not download sample video:", out)
            sys.exit(1)
        print("Downloaded sample video.")

    # Write caption
    try:
        write_caption(CAPTION_PATH, "Test caption from pipeline")
        print("Wrote caption:", CAPTION_PATH.name)
    except Exception as e:
        print("ERROR: Could not write caption file:", e)
        # If video was created but caption failed, still exit nonzero so watcher can handle it
        sys.exit(1)

    print("Test video and caption ready.")
    sys.exit(0)

if __name__ == "__main__":
    main()
