# nodes/life_engine.py
"""
Life Engine (enhanced).
create_post_media(outbox_dir: str) -> str
- Reads nodes/life_profile.json
- Decides whether to post now (prob + cadence)
- Picks theme using weighted interests + novelty bias
- Calls nodes.life_generator.generate_media and returns path
- Updates profile weights and writes history to nodes/ai_lady_instagram/history.json
"""

import json
import random
import time
from pathlib import Path
from datetime import datetime, timedelta

PROFILE_PATH = Path("nodes/life_profile.json")
LAST_POST = Path("nodes/ai_lady_instagram/last_post.json")
HISTORY = Path("nodes/ai_lady_instagram/history.json")

def _load_profile():
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

def _save_profile(profile):
    try:
        PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _read_last_post_time():
    try:
        if LAST_POST.exists():
            data = json.loads(LAST_POST.read_text(encoding="utf-8"))
            ts = data.get("last_post_ts")
            if ts:
                return datetime.fromisoformat(ts)
    except Exception:
        pass
    return None

def _write_last_post_time(dt):
    try:
        LAST_POST.parent.mkdir(parents=True, exist_ok=True)
        LAST_POST.write_text(json.dumps({"last_post_ts": dt.isoformat()}), encoding="utf-8")
    except Exception:
        pass

def _append_history(entry):
    try:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        hist = []
        if HISTORY.exists():
            try:
                hist = json.loads(HISTORY.read_text(encoding="utf-8"))
            except Exception:
                hist = []
        hist.insert(0, entry)
        hist = hist[:200]
        HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _should_post(profile):
    prefs = profile.get("posting_preferences", {})
    prob = prefs.get("post_probability", 1.0)
    min_days = prefs.get("min_days_between", 0)
    if prob < 1.0 and random.random() > prob:
        return False
    last = _read_last_post_time()
    if last and (datetime.utcnow() < last + timedelta(days=min_days)):
        return False
    return True

def _decay_weights(profile):
    rules = profile.get("growth_rules", {})
    decay = rules.get("weight_decay_per_day", 0.01)
    if decay <= 0:
        return
    interests = profile.get("interests", {})
    for k, v in list(interests.items()):
        newv = max(v - decay, rules.get("min_weight", 0.1))
        interests[k] = newv
    profile["interests"] = interests

def _pick_theme(profile):
    interests = profile.get("interests", {})
    if not interests:
        return "everyday"
    # novelty bias: lower probability for recently used themes in history
    history = []
    try:
        if HISTORY.exists():
            history = json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        history = []
    recent_themes = [h.get("theme") for h in history[:10] if h.get("theme")]
    # build weighted list
    items = []
    for theme, weight in interests.items():
        novelty = 1.0
        if theme in recent_themes:
            novelty = 1.0 - profile.get("posting_preferences", {}).get("novelty_bias", 0.3)
        items.append((theme, max(weight * novelty, 0.01)))
    total = sum(w for _, w in items)
    if total <= 0:
        return random.choice(list(interests.keys()))
    r = random.random() * total
    upto = 0
    for theme, w in items:
        upto += w
        if r <= upto:
            return theme
    return items[-1][0]

def _update_profile_after_post(profile, theme):
    rules = profile.get("growth_rules", {})
    inc = rules.get("weight_increment_on_post", 0.08)
    maxw = rules.get("max_weight", 3.0)
    interests = profile.get("interests", {})
    interests[theme] = min(interests.get(theme, 0.0) + inc, maxw)
    profile["interests"] = interests
    # small mood shift
    profile["mood"] = random.choice(["content", "excited", "reflective"])
    _save_profile(profile)

def create_post_media(outbox_dir: str) -> str:
    profile = _load_profile()
    if not profile:
        return ""
    # decay weights daily (simple)
    _decay_weights(profile)
    # decide whether to post now
    if not _should_post(profile):
        return ""
    interests = profile.get("interests", {})
    # pick theme and prefer type
    theme = _pick_theme(profile)
    prefs = profile.get("posting_preferences", {})
    image_weight = prefs.get("image_weight", 0.6)
    prefer = "image" if random.random() < image_weight else "video"
    # call generator
    try:
        import importlib
        lg = importlib.import_module("nodes.life_generator")
        if hasattr(lg, "generate_media"):
            path = lg.generate_media(outbox_dir, theme, prefer, profile)
            if path:
                # update last_post timestamp and history and profile
                now = datetime.utcnow()
                _write_last_post_time(now)
                entry = {
                    "ts": now.isoformat(),
                    "theme": theme,
                    "media": str(path),
                    "prefer": prefer
                }
                _append_history(entry)
                _update_profile_after_post(profile, theme)
                return path
    except Exception:
        pass
    return ""
