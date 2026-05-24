import re
from typing import List


# Very simple keyword-based safety filter.
# This is intentionally conservative: if in doubt, do NOT comment.
RISKY_KEYWORDS: List[str] = [
    # Violence / harm
    "kill", "murder", "suicide", "self harm", "self-harm",
    "blood", "gore", "shooting", "weapon", "gun",

    # Hate / slurs (keep generic, do NOT list slurs explicitly in code)
    "hate crime", "racist", "nazis", "kkk",

    # Politics / controversy
    "election", "president", "democrat", "republican", "leftist", "right wing",
    "politics", "political",

    # Sexual / explicit
    "onlyfans", "nsfw", "18+", "explicit",

    # Drugs
    "cocaine", "heroin", "meth", "overdose",
]

SUSPICIOUS_ACCOUNT_PATTERNS: List[str] = [
    r"freefollowers",
    r"free_followers",
    r"giveaway_\d+",
    r"crypto",
    r"forex",
]


def text_looks_risky(text: str) -> bool:
    lowered = text.lower()
    for kw in RISKY_KEYWORDS:
        if kw in lowered:
            return True
    return False


def username_looks_suspicious(username: str) -> bool:
    lowered = username.lower()
    for pattern in SUSPICIOUS_ACCOUNT_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False


def should_comment_on_post(
    post_caption: str,
    username: str,
    already_liked: bool,
    daily_comment_count: int,
    daily_comment_limit: int = 40,
) -> bool:
    """
    High-level safety gate:
    - Do not comment if caption looks risky
    - Do not comment if username looks suspicious
    - Do not comment if daily comment limit is reached
    - Do not comment if we haven't liked the post first (optional preference)
    """
    if daily_comment_count >= daily_comment_limit:
        return False

    if text_looks_risky(post_caption):
        return False

    if username_looks_suspicious(username):
        return False

    if not already_liked:
        # Optional: require like before comment to feel more natural
        return False

    return True


def should_like_post(
    post_caption: str,
    username: str,
    daily_like_count: int,
    daily_like_limit: int = 200,
) -> bool:
    """
    Safety gate for likes:
    - Do not like risky content
    - Do not like suspicious accounts
    - Respect daily like limit
    """
    if daily_like_count >= daily_like_limit:
        return False

    if text_looks_risky(post_caption):
        return False

    if username_looks_suspicious(username):
        return False

    return True


def main():
    tests = [
        ("I love this cozy day", "normal_user"),
        ("political rant about election", "normal_user"),
        ("check out my onlyfans", "normal_user"),
        ("just a cute outfit", "freefollowers_123"),
    ]
    for caption, user in tests:
        print("----")
        print("Caption:", caption)
        print("User:", user)
        print("Like?", should_like_post(caption, user, daily_like_count=0))
        print("Comment?", should_comment_on_post(caption, user, already_liked=True, daily_comment_count=0))


if __name__ == "__main__":
    main()
    