"""
bootstrap.py - One-time setup for the AI Lady content pipeline.
Run ONCE before your first batch_render.py.
Checks env vars, dirs, files, ffmpeg, Python deps, then seeds music library.
"""

import os, sys, json, logging, subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REQUIRED_ENV = {
    "KLING_ACCESS_KEY":  "Kling AI API access key",
    "KLING_SECRET_KEY":  "Kling AI API secret key",
    "JAMENDO_CLIENT_ID": "Jamendo API client ID (free at devportal.jamendo.com)",
}
REQUIRED_DIRS  = ["assets/audio/tracks", "episodes", "nodes/ai_lady", "output"]
REQUIRED_FILES = {
    "nodes/ai_lady/config.json":  "AI Lady node config",
    "nodes/ai_lady/scenes.json":  "AI Lady scenes library",
    "nodes/ai_lady/ref_face.png": "Face reference image for PuLID",
}
MUSIC_TARGET = 80
MUSIC_MIN    = 20

def check_env():
    missing = []
    for var, desc in REQUIRED_ENV.items():
        val = os.environ.get(var, "")
        if not val: missing.append((var, desc))
        else: log.info("  ✓ %s set", var)
    return missing

def check_dirs():
    for d in REQUIRED_DIRS:
        Path(d).mkdir(parents=True, exist_ok=True)
        log.info("  ✓ %s", d)

def check_files():
    missing = []
    for f, desc in REQUIRED_FILES.items():
        if Path(f).exists(): log.info("  ✓ %s", f)
        else: missing.append((f, desc))
    return missing

def check_ffmpeg():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            log.info("  ✓ ffmpeg: %s", r.stdout.split("\n")[0][:60])
            return True
    except FileNotFoundError: pass
    return False

def check_deps():
    missing = []
    for pkg in ["edge_tts", "jwt", "requests"]:
        try: __import__(pkg); log.info("  ✓ %s", pkg)
        except ImportError: missing.append(pkg)
    return missing

def count_tracks():
    d = Path("assets/audio/tracks")
    return len([p for p in d.glob("*.mp3") if p.stat().st_size > 50_000]) if d.exists() else 0

def seed_music():
    current = count_tracks()
    if current >= MUSIC_TARGET:
        log.info("Music library OK: %d tracks", current); return current
    needed = MUSIC_TARGET - current
    log.info("Seeding music library: fetching %d tracks from Jamendo...", needed)
    try:
        from music_fetcher import fetch_library
        fetch_library(count=needed)
        total = count_tracks()
        log.info("Music library: %d total tracks", total)
        return total
    except Exception as e:
        log.error("Music seed failed: %s", e)
        return current

def bootstrap():
    print("\n" + "="*60)
    print("  AI LADY PIPELINE — BOOTSTRAP")
    print("="*60 + "\n")

    errors, warnings = [], []

    log.info("Checking env vars...")
    for var, desc in check_env():
        if "JAMENDO" in var:
            warnings.append(f"  ⚠ {var} missing — music seeding skipped")
        else:
            errors.append(f"  ✗ {var} — {desc}")

    log.info("Checking directories...")
    check_dirs()

    log.info("Checking required files...")
    for f, desc in check_files():
        if "ref_face" in f:
            warnings.append(f"  ⚠ {f} missing — PuLID disabled, generic face used")
        else:
            errors.append(f"  ✗ {f} — {desc}")

    log.info("Checking ffmpeg...")
    if not check_ffmpeg():
        errors.append("  ✗ ffmpeg not found — install from ffmpeg.org")

    log.info("Checking Python packages...")
    pkgs = check_deps()
    if pkgs:
        errors.append(f"  ✗ Missing packages: {', '.join(pkgs)} — run: pip install {' '.join(pkgs)}")

    track_count = count_tracks()
    if os.environ.get("JAMENDO_CLIENT_ID"):
        log.info("Seeding music library...")
        track_count = seed_music()
    else:
        warnings.append(f"  ⚠ {track_count} tracks found — set JAMENDO_CLIENT_ID to auto-seed")

    print("\n" + "="*60)
    print("  BOOTSTRAP REPORT")
    print("="*60)
    if errors:
        print("\n🔴 BLOCKERS:")
        for e in errors: print(e)
    else:
        print("\n✅ No blockers.")
    if warnings:
        print("\n🟡 WARNINGS:")
        for w in warnings: print(w)
    print(f"\n🎵 Music library: {track_count} tracks")
    print("\n" + ("🟢 READY — run: python batch_render.py" if not errors else "🔴 Fix blockers then re-run bootstrap.py"))
    print("="*60 + "\n")
    return not errors

if __name__ == "__main__":
    sys.exit(0 if bootstrap() else 1)
