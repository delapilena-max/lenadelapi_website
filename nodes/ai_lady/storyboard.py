#!/usr/bin/env python3
"""
storyboard.py

Purpose
-------
- Take a director-generated scene JSON (file or stdin).
- Convert and normalize it into the storyboard schema your pipeline consumes.
- Validate required fields and types.
- Save the final storyboard JSON to:
    nodes/ai_lady/storyboards/<timestamp>_<scene_id>.json

Design goals
------------
- Single-file, paste-ready, stdlib only.
- Clear mapping rules and sensible defaults.
- CLI friendly for pipeline integration.
"""

from __future__ import annotations
import json
import sys
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Paths (adjust if your repo layout differs)
BASE_DIR = Path.cwd()
DEFAULT_LIBRARY_DIR = BASE_DIR / "nodes" / "ai_lady"
OUT_DIR = DEFAULT_LIBRARY_DIR / "storyboards"

# Storyboard schema defaults
STORYBOARD_SCHEMA = {
    "scene_id": None,
    "duration_seconds": 6,
    "camera": {"type": "static", "movement": "none", "framing": "medium_shot"},
    "character": {"name": "Lena", "pose": "neutral", "expression": "neutral", "action": None, "outfit": None},
    "environment": {"location": "indoor", "lighting": "soft", "props": []},
    "motion": {"body": "minimal", "hair": "minimal", "camera": "none"},
    "text_overlay": {"enabled": False, "content": "", "style": "minimal", "placement": "bottom"},
    "audio": {"type": "ambient", "track_id": None},
    # optional metadata
    "notes": None,
    "tags": [],
}


def load_scene(path: Optional[Path]) -> Dict[str, Any]:
    """Load scene JSON from a file or stdin (if path is None)."""
    if path:
        if not path.exists():
            raise FileNotFoundError(f"Scene file not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    else:
        # read from stdin
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("No input provided on stdin")
        return json.loads(raw)


def normalize_camera(camera: Any) -> Dict[str, Any]:
    """Normalize camera field into structured dict."""
    default = STORYBOARD_SCHEMA["camera"].copy()
    if not camera:
        return default
    if isinstance(camera, str):
        c = camera.lower()
        if "static" in c:
            return {"type": "static", "movement": "none", "framing": "medium_shot"}
        if "tracking" in c:
            return {"type": "tracking", "movement": "forward", "framing": "full_shot"}
        if "mirror" in c or "reflection" in c:
            return {"type": "mirror_reflection", "movement": "none", "framing": "medium_shot"}
        if "pov" in c or "first_person" in c:
            return {"type": "first_person_pov", "movement": "none", "framing": "medium_shot"}
        if "pan" in c:
            return {"type": "static", "movement": "slow_pan", "framing": "medium_shot"}
        if "handheld" in c:
            return {"type": "handheld", "movement": "handheld_slight", "framing": "medium_shot"}
        # fallback
        return default
    if isinstance(camera, dict):
        out = default.copy()
        out.update({k: camera.get(k, out[k]) for k in out.keys()})
        return out
    return default


def normalize_character(char: Any) -> Dict[str, Any]:
    """Normalize character block."""
    default = STORYBOARD_SCHEMA["character"].copy()
    if not char:
        return default
    out = default.copy()
    # accept either nested dict or top-level fields
    if isinstance(char, dict):
        out["name"] = char.get("name", out["name"])
        out["pose"] = char.get("pose", out["pose"])
        out["expression"] = char.get("expression", out["expression"])
        out["action"] = char.get("action", out["action"])
        out["outfit"] = char.get("outfit", out["outfit"])
    return out


def normalize_environment(env: Any) -> Dict[str, Any]:
    default = STORYBOARD_SCHEMA["environment"].copy()
    if not env:
        return default
    out = default.copy()
    if isinstance(env, dict):
        out["location"] = env.get("location", out["location"])
        out["lighting"] = env.get("lighting", out["lighting"])
        out["props"] = env.get("props", out["props"]) or out["props"]
    return out


def normalize_motion(motion: Any) -> Dict[str, Any]:
    default = STORYBOARD_SCHEMA["motion"].copy()
    if not motion:
        return default
    out = default.copy()
    if isinstance(motion, dict):
        out.update({k: motion.get(k, out[k]) for k in out.keys()})
    elif isinstance(motion, str):
        # simple parsing heuristics
        s = motion.lower()
        if "sway" in s:
            out["body"] = "subtle_sway"
        if "hair" in s:
            out["hair"] = "slight"
        if "step" in s:
            out["body"] = "step"
    return out


def normalize_text_overlay(text: Any) -> Dict[str, Any]:
    default = STORYBOARD_SCHEMA["text_overlay"].copy()
    if not text:
        return default
    out = default.copy()
    # text may be boolean, dict, or style string
    if isinstance(text, bool):
        out["enabled"] = text
    elif isinstance(text, dict):
        out["enabled"] = bool(text.get("enabled", True))
        out["content"] = text.get("content", out["content"])
        out["style"] = text.get("style", out["style"])
        out["placement"] = text.get("placement", out["placement"])
    elif isinstance(text, str):
        out["enabled"] = True
        out["content"] = text
    return out


def normalize_audio(audio: Any) -> Dict[str, Any]:
    default = STORYBOARD_SCHEMA["audio"].copy()
    if not audio:
        return default
    out = default.copy()
    if isinstance(audio, dict):
        out["type"] = audio.get("type", out["type"])
        out["track_id"] = audio.get("track_id", out["track_id"])
    elif isinstance(audio, str):
        out["type"] = audio
    return out


def build_storyboard(scene: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a director scene dict into the final storyboard schema.
    Accepts flexible input shapes and fills defaults.
    """
    sb = {}

    # scene_id
    scene_id = scene.get("scene_id") or scene.get("name") or f"scene_{uuid.uuid4().hex[:8]}"
    # ensure no spaces and safe filename
    scene_id_safe = str(scene_id).replace(" ", "_")
    sb["scene_id"] = scene_id_safe

    # duration
    dur = scene.get("duration_seconds") or scene.get("duration") or STORYBOARD_SCHEMA["duration_seconds"]
    try:
        dur = int(dur)
        if dur <= 0:
            dur = STORYBOARD_SCHEMA["duration_seconds"]
    except Exception:
        dur = STORYBOARD_SCHEMA["duration_seconds"]
    sb["duration_seconds"] = dur

    # camera
    sb["camera"] = normalize_camera(scene.get("camera") or scene.get("camera", None) or scene.get("camera_type"))

    # character
    # allow director to pass character block or top-level fields
    char_block = scene.get("character") or {
        "name": scene.get("character_name"),
        "pose": scene.get("pose"),
        "expression": scene.get("expression"),
        "action": scene.get("action"),
        "outfit": scene.get("outfit"),
    }
    sb["character"] = normalize_character(char_block)

    # environment
    env_block = scene.get("environment") or {
        "location": scene.get("location"),
        "lighting": scene.get("lighting"),
        "props": scene.get("props"),
    }
    sb["environment"] = normalize_environment(env_block)

    # motion
    sb["motion"] = normalize_motion(scene.get("motion") or scene.get("movement"))

    # text overlay
    # director may set text_overlay dict or text_style or text_overlay_enabled
    text_block = scene.get("text_overlay") or scene.get("text") or scene.get("text_style") or scene.get("text_overlay_enabled")
    # if text_block is a boolean flag stored in text_overlay_enabled, convert
    if isinstance(text_block, bool):
        text_block = {"enabled": text_block, "content": scene.get("text_overlay_content", "")}
    sb["text_overlay"] = normalize_text_overlay(text_block)

    # audio
    sb["audio"] = normalize_audio(scene.get("audio") or scene.get("audio_type"))

    # optional metadata passthrough
    sb["notes"] = scene.get("notes") or scene.get("_notes")
    sb["tags"] = scene.get("tags") or scene.get("_tags") or []

    # ensure types
    if not isinstance(sb["tags"], list):
        sb["tags"] = [str(sb["tags"])]

    return sb


def validate_storyboard(sb: Dict[str, Any]) -> None:
    """Basic validation of the storyboard structure."""
    required = ["scene_id", "duration_seconds", "camera", "character", "environment", "motion", "text_overlay", "audio"]
    for r in required:
        if r not in sb:
            raise ValueError(f"Storyboard missing required field: {r}")
    if not isinstance(sb["duration_seconds"], int) or sb["duration_seconds"] <= 0:
        raise ValueError("duration_seconds must be a positive integer")
    # camera must have type
    if not isinstance(sb["camera"], dict) or "type" not in sb["camera"]:
        raise ValueError("camera must be a dict with at least a 'type' field")


def save_storyboard(sb: Dict[str, Any], out_dir: Path = OUT_DIR) -> Path:
    """Save storyboard JSON to disk and return the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{sb['scene_id']}.json"
    path = out_dir / filename
    with path.open("w", encoding="utf-8") as fh:
        json.dump(sb, fh, indent=2, ensure_ascii=False)
    return path


def cli_main():
    import argparse

    parser = argparse.ArgumentParser(description="Convert director scene JSON into a storyboard JSON.")
    parser.add_argument("--scene-file", "-s", help="Path to director scene JSON. If omitted, reads JSON from stdin.", default=None)
    parser.add_argument("--out-dir", "-o", help="Output directory for storyboards", default=str(OUT_DIR))
    parser.add_argument("--no-save", action="store_true", help="Do not save file; print to stdout only")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON to stdout")
    args = parser.parse_args()

    scene_path = Path(args.scene_file) if args.scene_file else None
    try:
        scene = load_scene(scene_path)
    except Exception as e:
        print(f"Error loading scene: {e}", file=sys.stderr)
        sys.exit(2)

    storyboard = build_storyboard(scene)

    try:
        validate_storyboard(storyboard)
    except Exception as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(3)

    if not args.no_save:
        out_path = save_storyboard(storyboard, Path(args.out_dir))
        storyboard["_saved_path"] = str(out_path)

    # print to stdout for pipeline consumption
    if args.pretty:
        print(json.dumps(storyboard, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(storyboard, ensure_ascii=False))


if __name__ == "__main__":
    cli_main()
