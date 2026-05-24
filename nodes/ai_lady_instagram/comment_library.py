import random
from typing import List, Dict


# Base structure:
# comments[mood][content_type] = [list of strings]
COMMENTS: Dict[str, Dict[str, List[str]]] = {
    "cozy": {
        "selfie": [
            "You look so soft and cozy ✨",
            "This feels like a warm hug",
            "The cozy vibes are everything",
            "You look so gentle here",
        ],
        "outfit": [
            "This outfit is such a cozy dream",
            "Love this soft look on you",
            "The textures are so comforting",
        ],
        "general": [
            "This is so cozy I can’t deal",
            "The vibes are immaculate and soft",
            "This makes me want a blanket and tea",
        ],
    },
    "energetic": {
        "selfie": [
            "Your energy is everything 🔥",
            "You look so alive here",
            "This is such a power shot",
        ],
        "outfit": [
            "This fit is a whole statement",
            "The energy in this look is unreal",
        ],
        "general": [
            "The vibes are so high here",
            "This made my whole mood better",
        ],
    },
    "girlboss": {
        "selfie": [
            "CEO energy only",
            "You look like you’re running the world",
        ],
        "outfit": [
            "This is such a girlboss look",
            "Power outfit, power energy",
        ],
        "general": [
            "Big girlboss vibes here",
            "This is so inspiring",
        ],
    },
    "soft": {
        "selfie": [
            "You look so soft and pretty",
            "This is such a gentle moment",
        ],
        "outfit": [
            "This look is so soft and dreamy",
        ],
        "general": [
            "This feels like a soft little daydream",
        ],
    },
    "quiet": {
        "selfie": [
            "You look so peaceful here",
            "This feels like a quiet little moment",
        ],
        "general": [
            "This is so calm and grounding",
            "Love how peaceful this feels",
        ],
    },
    "playful": {
        "selfie": [
            "This is so fun omg",
            "Your energy is so playful here",
        ],
        "general": [
            "This made me smile so much",
            "The playful vibes are everything",
        ],
    },
    "romantic": {
        "selfie": [
            "You look like a soft romantic movie scene",
            "This is so dreamy and romantic",
        ],
        "general": [
            "The romantic vibes are unreal",
            "This feels like a love story",
        ],
    },
    "curious": {
        "general": [
            "This is so interesting, I love it",
            "This makes me want to know more",
        ],
    },
}


FALLBACK_COMMENTS: List[str] = [
    "This is gorgeous ✨",
    "Love this energy 💕",
    "You look amazing",
    "Obsessed with this vibe",
    "Such a mood today",
    "So pretty omg",
    "This made my day",
    "Absolutely stunning",
    "The aesthetic is everything",
    "Love this so much",
    "You’re glowing ✨",
    "This is so cute",
    "Big fan of this",
    "This feels so cozy",
    "The vibes are immaculate",
]


def get_comment(mood: str = "cozy", content_type: str = "general") -> str:
    mood_dict = COMMENTS.get(mood)
    if mood_dict:
        options = mood_dict.get(content_type) or mood_dict.get("general")
        if options:
            return random.choice(options)

    return random.choice(FALLBACK_COMMENTS)


def main():
    for mood in COMMENTS.keys():
        print(f"--- {mood} ---")
        for content_type in ["selfie", "outfit", "general"]:
            print(content_type, "->", get_comment(mood, content_type))


if __name__ == "__main__":
    main()
