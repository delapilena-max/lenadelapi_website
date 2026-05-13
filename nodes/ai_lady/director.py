#!/usr/bin/env python3
"""
director.py

Purpose
-------
- Load a scene template library (JSON).
- Choose a scene template based on an optional prompt, mood, or explicit name.
- Apply sensible defaults and lightweight randomization/variation.
- Return a validated scene dict matching the storyboard schema.
- Save the scene JSON to nodes/ai_lady/scenes/<timestamp>_<scene_id>.json

Design goals
------------
- Single-file, paste-ready, no external dependencies (stdlib only).
- Deterministic when a seed is provided.
- Clear extension points for rules, constraints, and customizers.
"""

from __future__ import annotations
import json
import random
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths (adjust if your repo layout differs)
BASE_DIR = Path.cwd()
LIB_PATH = BASE_DIR / "nodes" / "ai_lady" / "director_scene_library.json"
OUT_DIR = BASE_DIR / "nodes" / "ai_lady" / "scenes"

# Default schema fields and defaults
DEFAULT_DURATION = 6  # seconds
DEFAULT_CAMERA = {"type": "static", "movement": "none", "framing": "medium_shot"}
DEFAULT_CHARACTER = {
    "name": "Lena",
    "pose": "neutral",
    "expression": "neutral",
    "action": None,
    "outfit": None,
}
DEFAULT_ENVIRONMENT = {"location": "indoor", "lighting": "soft", "props": []}
DEFAULT_MOTION = {"body": "minimal", "hair": "minimal", "camera": "none"}
DEFAULT_TEXT_OVERLAY = {
    "enabled": False,
    "content": "",
    "style": "minimal",
    "placement": "bottom",
}
DEFAULT_AUDIO = {"type": "ambient", "track_id": None}


def load_library(path: Path = LIB_PATH) -> List[Dict[str, Any]]:
    """Load the scene template library from JSON. If missing, return empty list."""
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return []


def simple_prompt_match(prompt: str, template: Dict[str, Any]) -> int:
    """
    Very small heuristic to score how well a template matches a prompt.
    Returns integer score (higher = better).
    """
    if not prompt:
        return 0
    score = 0
    p = prompt.lower()
    for key in ("name", "location", "lighting", "camera", "pose", "outfit_category", "audio_type", "text_style"):
        val = template.get(key)
        if not val:
            continue
        if isinstance(val, str) and val.lower() in p:
            score += 3
    # small bonus for synonyms
    if "soft" in p and "soft" in (template.get("lighting") or ""):
        score += 1
    return score


def choose_template(
    library: List[Dict[str, Any]],
    prompt: Optional[str] = None,
    mood: Optional[str] = None,
    prefer: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Choose a template from the library.
    - If prefer is a template name, try to find it.
    - If prompt is provided, score templates and pick top candidates.
    - Otherwise pick randomly.
    """
    rnd = random.Random(seed)
    if not library:
        raise RuntimeError("Scene library is empty. Add director_scene_library.json to nodes/ai_lady/")

    # prefer exact name
    if prefer:
        for t in library:
            if t.get("name") == prefer:
                return t.copy()

    # score by prompt
    if prompt:
        scored = [(simple_prompt_match(prompt, t), t) for t in library]
        scored.sort(key=lambda x: x[0], reverse=True)
        top_score = scored[0][0]
        # if top score is zero, fallback to random
        if top_score > 0:
            # pick among top N with same score
            top_candidates = [t for s, t in scored if s == top_score]
            return rnd.choice(top_candidates).copy()

    # mood-based lightweight filter
    if mood:
        mood = mood.lower()
        filtered = [t for t in library if mood in (t.get("lighting", "") + " " + (t.get("audio_type") or "")).lower()]
        if filtered:
            return rnd.choice(filtered).copy()

    # default random pick
    return rnd.choice(library).copy()


def apply_variations(template: Dict[str, Any], seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Apply small variations to make scenes less repetitive:
    - duration jitter
    - camera movement choices based on camera type
    - fill missing fields with defaults
    - generate outfit and action suggestions
    """
    rnd = random.Random(seed or int(time.time()))
    scene = {}

    # IDs and timing
    scene_id = template.get("name") or f"scene_{uuid.uuid4().hex[:8]}"
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    scene["scene_id"] = f"{scene_id}_{timestamp}"
    scene["duration_seconds"] = int(template.get("duration_seconds", DEFAULT_DURATION) * rnd.uniform(0.9, 1.3))

    # Camera
    cam = {}
    cam_type = template.get("camera", "static")
    # normalize camera field if it's a string
    if isinstance(cam_type, str):
        # map some known camera descriptors to structured camera
        if cam_type.startswith("static"):
            cam = {"type": "static", "movement": "none", "framing": cam_type.split("_")[-1] if "_" in cam_type else "medium_shot"}
        elif cam_type.startswith("tracking") or "tracking" in cam_type:
            cam = {"type": "tracking", "movement": "forward", "framing": "full_shot"}
        elif cam_type in ("mirror_reflection", "over_shoulder", "first_person_pov"):
            cam = {"type": cam_type, "movement": "none", "framing": "medium_shot"}
        elif cam_type == "slow_pan":
            cam = {"type": "static", "movement": "slow_pan", "framing": "medium_shot"}
        else:
            cam = DEFAULT_CAMERA.copy()
    elif isinstance(cam_type, dict):
        cam = cam_type.copy()
    else:
        cam = DEFAULT_CAMERA.copy()

    # small random camera shake for handheld descriptors
    if "handheld" in (template.get("camera") or ""):
        cam["movement"] = "handheld_slight"

    scene["camera"] = cam

    # Character
    char = DEFAULT_CHARACTER.copy()
    char.update({
        "name": template.get("character_name", "Lena"),
        "pose": template.get("pose") or char["pose"],
        "expression": template.get("expression") or char["expression"],
    })
    # action inference
    action = template.get("motion") or template.get("action") or template.get("character_action")
    if isinstance(action, str):
        char["action"] = action
    else:
        # small heuristics
        if "spin" in (template.get("motion") or "") or "spin" in (template.get("pose") or ""):
            char["action"] = "spin"
        elif "sip" in (template.get("motion") or ""):
            char["action"] = "sip"
        else:
            char["action"] = template.get("action") or None

    # outfit resolution
    outfit_cat = template.get("outfit_category") or "casual"
    # simple outfit mapping (extendable)
    outfit_map = {
        "soft_girl": "pink crop top;denim skirt",
        "girly": "cute top;mini skirt",
        "cozy": "oversized sweater;leggings",
        "streetwear": "hoodie;cargo pants",
        "glam": "silk dress;heels",
        "minimal": "neutral tee;jeans",
        "summer": "breezy dress;sandals",
        "fashion": "statement outfit",
        "dancewear": "crop top;shorts",
        "beauty": "vanity outfit",
        "retro": "vintage dress",
        "boho": "flowy dress",
        "edgy": "leather jacket",
        "varied": "mix and match",
        "performance": "stage outfit",
        "editorial": "high fashion",
    }
    char["outfit"] = template.get("outfit") or outfit_map.get(outfit_cat, outfit_cat)

    scene["character"] = char

    # Environment
    env = DEFAULT_ENVIRONMENT.copy()
    env["location"] = template.get("location") or env["location"]
    env["lighting"] = template.get("lighting") or env["lighting"]
    env["props"] = template.get("props") or env["props"]
    scene["environment"] = env

    # Motion
    motion = DEFAULT_MOTION.copy()
    # map template motion fields
    t_motion = template.get("motion") or {}
    if isinstance(t_motion, str):
        # simple parsing
        motion["body"] = t_motion if "body" in t_motion else motion["body"]
        if "hair" in t_motion:
            motion["hair"] = "slight"
    elif isinstance(t_motion, dict):
        motion.update(t_motion)
    # small randomization
    if rnd.random() < 0.15:
        motion["body"] = rnd.choice(["subtle_sway", "step", "breath"])
    scene["motion"] = motion

    # Text overlay
    text = DEFAULT_TEXT_OVERLAY.copy()
    text_enabled = template.get("text_overlay_enabled") or template.get("text_overlay") or template.get("text_style")
    if text_enabled:
        text["enabled"] = True
        text["content"] = template.get("text_overlay_content") or template.get("text") or ""
        text["style"] = template.get("text_style") or text["style"]
        text["placement"] = template.get("text_placement") or text["placement"]
    scene["text_overlay"] = text

    # Audio
    audio = DEFAULT_AUDIO.copy()
    audio["type"] = template.get("audio_type") or audio["type"]
    audio["track_id"] = template.get("track_id") or None
    scene["audio"] = audio

    # Additional metadata from template (pass-through)
    for k in ("notes", "tags"):
        if k in template:
            scene[k] = template[k]

    return scene


def validate_scene(scene: Dict[str, Any]) -> None:
    """Basic validation to ensure required keys exist and types are sane."""
    required = ["scene_id", "duration_seconds", "camera", "character", "environment", "motion", "text_overlay", "audio"]
    for r in required:
        if r not in scene:
            raise ValueError(f"Scene missing required field: {r}")
    if not isinstance(scene["duration_seconds"], int) or scene["duration_seconds"] <= 0:
        raise ValueError("duration_seconds must be a positive integer")


def save_scene(scene: Dict[str, Any], out_dir: Path = OUT_DIR) -> Path:
    """Save scene JSON to disk and return the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{scene['scene_id']}.json"
    path = out_dir / filename
    with path.open("w", encoding="utf-8") as fh:
        json.dump(scene, fh, indent=2, ensure_ascii=False)
    return path


def generate_scene(
    prompt: Optional[str] = None,
    mood: Optional[str] = None,
    prefer: Optional[str] = None,
    seed: Optional[int] = None,
    library_path: Optional[Path] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """High-level helper: load library, choose template, apply variations, validate, save, return scene."""
    lib = load_library(library_path or LIB_PATH)
    template = choose_template(lib, prompt=prompt, mood=mood, prefer=prefer, seed=seed)
    scene = apply_variations(template, seed=seed)
    validate_scene(scene)
    if save:
        path = save_scene(scene)
        scene["_saved_path"] = str(path)
    return scene


# CLI convenience
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Director: generate a scene JSON from the scene library.")
    parser.add_argument("--prompt", "-p", help="Natural language prompt to bias scene selection", default=None)
    parser.add_argument("--mood", "-m", help="Mood or lighting hint (e.g., soft, moody, neon)", default=None)
    parser.add_argument("--prefer", help="Prefer a specific template name", default=None)
    parser.add_argument("--seed", type=int, help="Random seed for deterministic output", default=None)
    parser.add_argument("--no-save", action="store_true", help="Do not save the scene file to disk")
    parser.add_argument("--library", help="Path to scene library JSON", default=str(LIB_PATH))
    args = parser.parse_args()

    scene = generate_scene(
        prompt=args.prompt,
        mood=args.mood,
        prefer=args.prefer,
        seed=args.seed,
        library_path=Path(args.library),
        save=not args.no_save,
    )
    # Print compact JSON to stdout for pipeline consumption
    print(json.dumps(scene, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
