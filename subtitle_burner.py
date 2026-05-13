"""
subtitle_burner.py - Burns timed subtitles onto a video using ffmpeg.
Brainrot style: bold white text, thick black outline, centered, big font.
"""

import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PLAY_RES_X = 1080
PLAY_RES_Y = 1920
PRIMARY_COLOUR = "&H00FFFFFF"
OUTLINE_COLOUR = "&H00000000"
BACK_COLOUR    = "&H00000000"
FONT_NAME  = "Arial"
FONT_SIZE  = 88
BOLD       = 1
ITALIC     = 0
OUTLINE    = 5
SHADOW     = 2
ALIGNMENT  = 2
MARGIN_V   = 120
MARGIN_H   = 60

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_RES_X}
PlayResY: {PLAY_RES_Y}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Brainrot,{FONT_NAME},{FONT_SIZE},{PRIMARY_COLOUR},&H000000FF,{OUTLINE_COLOUR},{BACK_COLOUR},{BOLD},{ITALIC},0,0,100,100,0,0,1,{OUTLINE},{SHADOW},{ALIGNMENT},{MARGIN_H},{MARGIN_H},{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def _seconds_to_ass(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _clean_text(text: str) -> str:
    return text.replace("{", "").replace("}", "").replace("\n", "\\N").strip()

def build_ass(subtitles: list) -> str:
    lines = [ASS_HEADER]
    for entry in subtitles:
        start = float(entry.get("start", 0))
        dur   = float(entry.get("duration", 1.5))
        end   = start + dur
        text  = _clean_text(str(entry.get("text", "")))
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{_seconds_to_ass(start)},{_seconds_to_ass(end)},"
            f"Brainrot,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"

def burn_subtitles(episode: dict, input_video: str, output_video: str) -> bool:
    subtitles = episode.get("subtitles") or []
    if not subtitles:
        log.warning("burn_subtitles: no subtitles — copying input unchanged")
        import shutil
        shutil.copy2(input_video, output_video)
        return True

    in_path  = Path(input_video)
    out_path = Path(output_video)
    ass_path = in_path.parent / "subs.ass"

    if not in_path.exists():
        log.error("burn_subtitles: input not found: %s", input_video)
        return False

    ass_path.write_text(build_ass(subtitles), encoding="utf-8")
    log.info("burn_subtitles: wrote %d lines to %s", len(subtitles), ass_path)

    ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(out_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("ffmpeg subtitle burn failed:\n%s", result.stderr[-3000:])
            return False
        log.info("burn_subtitles: done -> %s", out_path)
        return True
    except FileNotFoundError:
        log.error("ffmpeg not found on PATH")
        return False
    finally:
        try:
            ass_path.unlink()
        except OSError:
            pass
