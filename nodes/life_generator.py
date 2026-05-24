# nodes/life_generator.py
"""
Life Generator (enhanced).
generate_media(outbox_dir: str, theme: str, prefer: str, profile: dict) -> str
- Creates placeholder media and writes <media>.meta.json with caption, theme, tags, confidence.
- Replace placeholder media creation with model calls later.
"""

import os
import time
import random
import json
from pathlib import Path

def _safe_text(s):
    try:
        return str(s)
    except Exception:
        return ""

def _write_meta(media_path: Path, meta: dict):
    try:
        meta_path = media_path.with_suffix(media_path.suffix + ".meta.json")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def _choose_caption(profile, theme, detail=None):
    templates = profile.get("caption_templates", []) if profile else []
    if not templates:
        templates = ["{lead} — small moment."]
    tpl = random.choice(templates)
    lead = theme
    detail = detail or random.choice(["a tiny win", "a quiet morning", "a new recipe", "a good song"])
    caption = tpl.replace("{lead}", lead).replace("{detail}", detail).replace("{interest}", theme)
    # add voice tweak
    voice = random.choice(profile.get("voice_examples", [])) if profile else ""
    if "short" in voice:
        caption = caption.split(".")[0] + "."
    return caption.strip()

def generate_media(outbox_dir: str, theme: str = "everyday", prefer: str = None, profile: dict = None) -> str:
    outdir = Path(outbox_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    # Decide image or video
    if prefer == "video":
        choice = "video"
    elif prefer == "image":
        choice = "image"
    else:
        image_weight = profile.get("posting_preferences", {}).get("image_weight", 0.6) if profile else 0.6
        choice = "image" if random.random() < image_weight else "video"

    # Build caption and tags
    caption = _choose_caption(profile or {}, theme)
    tags = [theme.replace(" ", "_")]
    confidence = 0.9

    if choice == "image":
        fname = outdir / f"life_gen_{theme}_{ts}.jpg"
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGB", (1080,1080), color=(int(random.random()*200)+30,120,140))
            d = ImageDraw.Draw(img)
            d.text((40,40), f"{theme} • {ts}", fill=(255,255,255))
            img.save(fname, quality=85)
        except Exception:
            try:
                fname.write_bytes(b"")
            except Exception:
                pass
    else:
        fname = outdir / f"life_gen_{theme}_{ts}.mp4"
        try:
            cmd = f'ffmpeg -y -f lavfi -i color=c=black:s=640x640:d=2 -c:v libx264 -t 2 "{fname}" -loglevel error'
            rc = os.system(cmd)
            if rc != 0:
                try:
                    fname.write_bytes(b"")
                except Exception:
                    pass
        except Exception:
            try:
                fname.write_bytes(b"")
            except Exception:
                pass

    meta = {
        "caption": caption,
        "theme": theme,
        "tags": tags,
        "confidence": confidence,
        "generated_at": ts,
        "format": "image" if choice == "image" else "video"
    }
    _write_meta(Path(str(fname)), meta)
    return str(fname)
    