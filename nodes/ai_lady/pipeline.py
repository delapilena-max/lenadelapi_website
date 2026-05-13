#!/usr/bin/env python3
"""
pipeline.py

Purpose
-------
- Integrate director -> storyboard into one automatic generation step.
- Load director_scene_library.json, generate a scene, convert to storyboard, save both.
- Designed to be used by your scheduler or called from other scripts.

Usage
-----
# generate with a prompt and seed, save both files
python3 nodes/ai_lady/pipeline.py --prompt "soft girl morning" --seed 42

# generate without saving scene (still saves storyboard)
python3 nodes/ai_lady/pipeline.py --no-save-scene

# print storyboard JSON to stdout
python3 nodes/ai_lady/pipeline.py --pretty
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Try to import local modules (director.py and storyboard.py must be in the same package folder)
BASE_DIR = Path.cwd()
AI_DIR = BASE_DIR / "nodes" / "ai_lady"
sys.path.insert(0, str(AI_DIR))

try:
    import director as director_mod
except Exception as e:
    raise ImportError(f"Failed to import director.py from {AI_DIR}: {e}")

try:
    import storyboard as storyboard_mod
except Exception as e:
    raise ImportError(f"Failed to import storyboard.py from {AI_DIR}: {e}")

# CLI and orchestration
def run_pipeline(
    prompt: Optional[str] = None,
    mood: Optional[str] = None,
    prefer: Optional[str] = None,
    seed: Optional[int] = None,
    save_scene: bool = True,
    save_storyboard: bool = True,
    pretty: bool = False,
) -> Dict[str, Any]:
    """
    High-level pipeline:
    1. Generate scene via director.generate_scene
    2. Convert scene -> storyboard via storyboard.build_storyboard
    3. Save outputs and return combined result dict
    """
    # 1. generate scene
    scene = director_mod.generate_scene(
        prompt=prompt,
        mood=mood,
        prefer=prefer,
        seed=seed,
        library_path=None,
        save=save_scene,
    )

    # 2. build storyboard
    sb = storyboard_mod.build_storyboard(scene)

    # 3. validate storyboard
    storyboard_mod.validate_storyboard(sb)

    # 4. save storyboard if requested
    if save_storyboard:
        out_path = storyboard_mod.save_storyboard(sb)
        sb["_saved_path"] = str(out_path)

    # attach saved scene path if director saved it
    if save_scene and "_saved_path" in scene:
        sb["_scene_saved_path"] = scene["_saved_path"]

    # return both
    result = {"scene": scene, "storyboard": sb}
    return result


def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Run director -> storyboard pipeline.")
    parser.add_argument("--prompt", "-p", help="Prompt to bias scene selection", default=None)
    parser.add_argument("--mood", "-m", help="Mood hint (soft, neon, moody)", default=None)
    parser.add_argument("--prefer", help="Prefer a specific template name", default=None)
    parser.add_argument("--seed", type=int, help="Random seed for deterministic output", default=None)
    parser.add_argument("--no-save-scene", action="store_true", help="Do not save the director scene JSON to disk")
    parser.add_argument("--no-save-storyboard", action="store_true", help="Do not save the storyboard JSON to disk")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the final storyboard JSON to stdout")
    args = parser.parse_args()

    try:
        result = run_pipeline(
            prompt=args.prompt,
            mood=args.mood,
            prefer=args.prefer,
            seed=args.seed,
            save_scene=not args.no_save_scene,
            save_storyboard=not args.no_save_storyboard,
            pretty=args.pretty,
        )
    except Exception as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(2)

    # print storyboard (or full result) to stdout for pipeline consumption
    if args.pretty:
        print(json.dumps(result["storyboard"], indent=2, ensure_ascii=False))
    else:
        # compact output: include scene id and storyboard path
        out = {
            "scene_id": result["scene"].get("scene_id"),
            "scene_path": result["scene"].get("_saved_path"),
            "storyboard_id": result["storyboard"].get("scene_id"),
            "storyboard_path": result["storyboard"].get("_saved_path"),
        }
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
