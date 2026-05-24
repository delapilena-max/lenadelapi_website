import json
import time
from pathlib import Path
from typing import Dict, Any, List

BASE = Path("nodes/ai_lady_instagram")
STATE_DIR = BASE / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

RELATIONSHIPS_FILE = STATE_DIR / "relationships.json"


def load_relationships() -> Dict[str, Any]:
    if not RELATIONSHIPS_FILE.exists():
        return {}
    try:
        return json.loads(RELATIONSHIPS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_relationships(data: Dict[str, Any]):
    RELATIONSHIPS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_interaction(username: str, interaction_type: str):
    """
    interaction_type: "like", "comment", "story_view", etc.
    """
    data = load_relationships()
    now = int(time.time())

    user = data.get(username, {
        "username": username,
        "interactions": [],
        "last_interaction": 0,
        "interaction_count": 0,
    })

    user["interactions"].append({
        "type": interaction_type,
        "timestamp": now,
    })
    user["last_interaction"] = now
    user["interaction_count"] = user.get("interaction_count", 0) + 1

    data[username] = user
    save_relationships(data)


def get_priority_accounts(limit: int = 20) -> List[str]:
    """
    Returns usernames sorted by:
    - higher interaction_count
    - more recent last_interaction
    """
    data = load_relationships()
    users = list(data.values())

    users.sort(
        key=lambda u: (u.get("interaction_count", 0), u.get("last_interaction", 0)),
        reverse=True,
    )

    return [u["username"] for u in users[:limit]]


def get_cooldown_accounts(cooldown_seconds: int = 3600) -> List[str]:
    """
    Returns usernames that were interacted with too recently.
    """
    data = load_relationships()
    now = int(time.time())
    cooldown = []
    for username, u in data.items():
        last = u.get("last_interaction", 0)
        if now - last < cooldown_seconds:
            cooldown.append(username)
    return cooldown


def main():
    # Simple test
    record_interaction("example_user", "like")
    record_interaction("example_user", "comment")
    record_interaction("another_user", "like")

    print("Priority accounts:", get_priority_accounts())
    print("Cooldown accounts:", get_cooldown_accounts(cooldown_seconds=999999))


if __name__ == "__main__":
    main()
