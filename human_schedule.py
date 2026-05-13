"""
human_schedule.py  — Human-pattern posting schedule engine (CDT, East Lincoln IL)
Generates staggered irregular times per platform that read like a real person's feed.
"""
import random
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")

# Posting windows (start_h, start_m, end_h, end_m) — Central time
WINDOWS = {
    "early_morning": ( 6, 30,  8, 30),  # Getting ready / coffee
    "morning":       ( 8, 30, 10,  0),  # Commute scroll
    "lunch":         (11, 45, 13, 15),  # Lunch break
    "afternoon":     (14, 30, 16, 30),  # Afternoon lull at desk
    "evening":       (17, 30, 19, 30),  # After-work wind-down
    "prime":         (19, 30, 22,  0),  # Peak engagement
    "late":          (22,  0, 23, 30),  # Night owls
}

WEEKEND_SHIFT = 75  # minutes — sleeping in on Sat/Sun

# Each platform's preferred windows, ordered by priority
PLATFORM_WINDOWS = {
    "tiktok":    ["prime", "afternoon", "evening", "lunch"],
    "instagram": ["morning", "lunch", "evening", "prime"],
    "facebook":  ["morning", "lunch", "afternoon"],
    "youtube":   ["afternoon", "prime", "evening"],
    "pinterest": ["prime", "late", "afternoon"],
}

PLATFORM_MAX_DAILY = {
    "tiktok": 3, "instagram": 2, "facebook": 2, "youtube": 1, "pinterest": 4
}

def _rng(char_name: str, tag: str, today: date) -> random.Random:
    seed = int(today.strftime("%Y%m%d")) * 31337 + abs(hash(char_name + tag)) % 99991
    return random.Random(seed)

def should_post_today(char_name: str, rules: dict, today: date) -> bool:
    """True if this character should be active today based on weekly frequency."""
    rng = _rng(char_name, "active", today)
    freq = rules.get("frequency", {})
    n = rng.randint(freq.get("min_per_week", 4), freq.get("max_per_week", 7))
    active_days = sorted(rng.sample(range(7), min(n, 7)))
    return today.weekday() in active_days

def get_post_times(char_name: str, rules: dict, today: date) -> list:
    """
    Returns list of (datetime, platform) sorted by time.
    Applies human-pattern variance: weekend shift, window jitter, stagger.
    """
    platforms = rules.get("platforms", [])
    rng = _rng(char_name, "times", today)
    is_weekend = today.weekday() >= 5
    raw = []

    for platform in platforms:
        max_posts = PLATFORM_MAX_DAILY.get(platform, 1)
        windows   = PLATFORM_WINDOWS.get(platform, ["lunch", "prime"])
        n = rng.randint(1, min(2, max_posts, len(windows)))
        chosen = rng.sample(windows, n)

        for wname in chosen:
            sh, sm, eh, em = WINDOWS[wname]
            start = datetime(today.year, today.month, today.day, sh, sm, tzinfo=TZ)
            end   = datetime(today.year, today.month, today.day, eh, em, tzinfo=TZ)
            if is_weekend:
                start += timedelta(minutes=WEEKEND_SHIFT)
                end   += timedelta(minutes=WEEKEND_SHIFT)
            span = max(1, int((end - start).total_seconds()))
            jitter = rng.randint(-7, 7) * 60
            t = start + timedelta(seconds=max(0, rng.randint(0, span) + jitter))
            t = min(t, datetime(today.year, today.month, today.day, 23, 55, tzinfo=TZ))
            raw.append((t, platform))

    raw.sort(key=lambda x: x[0])

    # Ensure posts are at least 3–8 min apart (humans don't blast all at once)
    result, last = [], None
    for t, p in raw:
        if last and (t - last).total_seconds() < 180:
            t = last + timedelta(minutes=rng.randint(3, 8))
        result.append((t, p))
        last = t

    return result
