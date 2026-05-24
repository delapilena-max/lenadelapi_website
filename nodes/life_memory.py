# nodes/life_memory.py
"""
Life Memory utilities for AI Lady.
- Persistent storage for profile, history, and analytics.
- Weight update rules: decay, reinforcement, normalization.
- Topic novelty and simple similarity heuristics.
- Caption template harvesting and template scoring.
"""

import json
import math
import random
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

PROFILE_PATH = Path("nodes/life_profile.json")
HISTORY_PATH = Path("nodes/ai_lady_instagram/history.json")
ANALYTICS_PATH = Path("nodes/ai_lady_instagram/analytics.json")

def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _save_json(p: Path, obj):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def load_profile() -> Dict:
    prof = _load_json(PROFILE_PATH)
    if not prof:
        prof = {
            "interests": {},
            "caption_templates": [],
            "posting_preferences": {}
        }
    return prof

def save_profile(profile: Dict):
    _save_json(PROFILE_PATH, profile)

def append_history(entry: Dict):
    hist = _load_json(HISTORY_PATH) or []
    hist.insert(0, entry)
    hist = hist[:1000]
    _save_json(HISTORY_PATH, hist)

def read_history(n: int = 50) -> List[Dict]:
    hist = _load_json(HISTORY_PATH) or []
    return hist[:n]

def read_analytics() -> Dict:
    return _load_json(ANALYTICS_PATH) or {}

def write_analytics(data: Dict):
    _save_json(ANALYTICS_PATH, data)

# -------------------------
# Weight updates and decay
# -------------------------
def decay_interest_weights(profile: Dict, days: float = 1.0):
    rules = profile.get("growth_rules", {})
    decay_per_day = rules.get("weight_decay_per_day", 0.01)
    if decay_per_day <= 0:
        return
    interests = profile.get("interests", {})
    for k, v in list(interests.items()):
        newv = max(v - decay_per_day * days, rules.get("min_weight", 0.1))
        interests[k] = newv
    profile["interests"] = interests
    save_profile(profile)

def reinforce_interest(profile: Dict, theme: str, reward: float = 0.08):
    interests = profile.get("interests", {})
    rules = profile.get("growth_rules", {})
    maxw = rules.get("max_weight", 3.0)
    interests[theme] = min(interests.get(theme, 0.0) + reward, maxw)
    profile["interests"] = interests
    save_profile(profile)

def normalize_interests(profile: Dict, target_sum: float = None):
    interests = profile.get("interests", {})
    total = sum(interests.values()) or 1.0
    if target_sum is None:
        target_sum = total
    factor = target_sum / total if total > 0 else 1.0
    for k in interests:
        interests[k] = max(interests[k] * factor, profile.get("growth_rules", {}).get("min_weight", 0.1))
    profile["interests"] = interests
    save_profile(profile)

# -------------------------
# Topic novelty and similarity
# -------------------------
def recent_themes(history_n: int = 20) -> List[str]:
    hist = read_history(history_n)
    return [h.get("theme") for h in hist if h.get("theme")]

def novelty_score(profile: Dict, theme: str, recent_n: int = 20) -> float:
    recent = recent_themes(recent_n)
    bias = profile.get("posting_preferences", {}).get("novelty_bias", 0.3)
    if theme in recent:
        return max(0.01, 1.0 - bias)
    return 1.0

def pick_weighted_theme(profile: Dict) -> str:
    interests = profile.get("interests", {})
    if not interests:
        return "everyday"
    items = []
    for theme, weight in interests.items():
        nov = novelty_score(profile, theme)
        items.append((theme, max(weight * nov, 0.001)))
    total = sum(w for _, w in items)
    r = random.random() * total
    upto = 0.0
    for theme, w in items:
        upto += w
        if r <= upto:
            return theme
    return items[-1][0]

# -------------------------
# Caption template harvesting
# -------------------------
def harvest_caption_template(profile: Dict, caption: str, min_quality: float = 0.8):
    # Simple heuristic: short captions with a question or sensory detail are good
    if not caption or len(caption) < 12:
        return
    tpl_list = profile.get("caption_templates", [])
    candidate = caption.strip()
    if len(candidate) > 200:
        candidate = candidate[:200]
    if candidate in tpl_list:
        return
    tpl_list.insert(0, candidate)
    profile["caption_templates"] = tpl_list[:200]
    save_profile(profile)

# -------------------------
# Engagement simulation (optional)
# -------------------------
def simulate_engagement(media_path: str, theme: str, profile: Dict) -> Dict:
    weight = profile.get("interests", {}).get(theme, 0.5)
    nov = novelty_score(profile, theme)
    base = 50.0 * (1.0 + math.log1p(weight))
    likes = int(base * nov * (0.8 + random.random() * 0.8))
    comments = int(max(0, (likes / 20) * (0.5 + random.random())))
    metrics = {"likes": likes, "comments": comments, "engagement": likes + comments * 3}
    analytics = read_analytics()
    analytics_entry = {"ts": datetime.utcnow().isoformat(), "media": media_path, "theme": theme, **metrics}
    analytics.setdefault("posts", []).insert(0, analytics_entry)
    write_analytics(analytics)
    return metrics
