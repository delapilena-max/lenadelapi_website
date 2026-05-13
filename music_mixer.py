"""
music_mixer.py - Duck background music under TTS voiceover via ffmpeg.
Drop any mp3s into assets/audio/tracks/ — this picks one at random each episode.
"""

import random, logging, subprocess, shutil
from pathlib import Path

log = logging.getLogger(__name__)

TRACKS_DIR  = Path("assets/audio/tracks")
DUCK_VOLUME = 0.12
FADE_OUT    = 1.5

def pick_track():
    tracks = [str(p) for p in TRACKS_DIR.glob("*.mp3") if p.stat().st_size > 50_000]
    if not tracks:
        log.warning("pick_track: no mp3s found in %s", TRACKS_DIR)
        return None
    return random.choice(tracks)

def get_video_duration(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        log.warning("ffprobe failed: %s", e)
    return None

def mix_music(input_video, output_video, track_path=None):
    track = track_path or pick_track()
    if not track:
        log.warning("mix_music: no track available — copying unchanged")
        shutil.copy2(input_video, output_video)
        return True

    duration   = get_video_duration(input_video)
    fade_start = max(0, (duration or 30) - FADE_OUT)
    log.info("mix_music: %.1fs | track=%s | duck=%.0f%%",
             duration or 0, Path(track).name, DUCK_VOLUME * 100)

    filter_complex = (
        f"[1:a]volume={DUCK_VOLUME},"
        f"afade=t=out:st={fade_start:.3f}:d={FADE_OUT},"
        f"apad[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-stream_loop", "-1", "-i", track,
        "-filter_complex", filter_complex,
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", output_video
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("ffmpeg music mix failed:\n%s", result.stderr[-3000:])
            return False
        log.info("mix_music: done -> %s", output_video)
        return True
    except FileNotFoundError:
        log.error("ffmpeg not found on PATH")
        return False
