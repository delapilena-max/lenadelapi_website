import os
import random
import time
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import sync_playwright, Page

BASE = Path("nodes/ai_lady_instagram")
STORAGE_STATE = BASE / "storage_state.json"
DEBUG_DIR = BASE / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

HEADLESS = os.environ.get("INTERACTION_HEADLESS", "true").lower() in ("1", "true", "yes")

LONG = 120000


# -----------------------------
# Utility / Debug
# -----------------------------
def dump_debug(page: Page, name_prefix: str = "interaction_debug"):
    ts = int(time.time())
    html_path = DEBUG_DIR / f"{name_prefix}.{ts}.html"
    png_path = DEBUG_DIR / f"{name_prefix}.{ts}.png"
    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(png_path), full_page=True)
    except Exception:
        pass
    print(f"[DEBUG] Saved: {html_path}")
    print(f"[DEBUG] Screenshot: {png_path}")


def close_modals(page: Page):
    selectors = [
        'button:has-text("Not Now")',
        'button:has-text("Not now")',
        'button:has-text("Close")',
        'button:has-text("Accept")',
        'button:has-text("Allow all cookies")',
        'button:has-text("Only allow essential cookies")',
        'button[aria-label="Close"]',
        'div[role="dialog"] button:has-text("OK")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=3000)
                time.sleep(0.4)
        except Exception:
            continue


# -----------------------------
# Comment Generation
# -----------------------------
POSITIVE_COMMENT_TEMPLATES: List[str] = [
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


def generate_positive_comment() -> str:
    # Simple random positive comment; can later be replaced with Life Engine–driven text
    return random.choice(POSITIVE_COMMENT_TEMPLATES)


# -----------------------------
# Core Interaction Logic
# -----------------------------
def like_post(page: Page, post_index: int) -> bool:
    """
    Attempts to like a post in the feed by index (0-based).
    Returns True if it believes the like succeeded.
    """
    try:
        posts = page.locator('article').all()
        if post_index >= len(posts):
            return False

        post = posts[post_index]
        # Like button: usually a button with aria-label="Like" or a heart icon
        like_selectors = [
            'button[aria-label="Like"]',
            'svg[aria-label="Like"]',
        ]
        for sel in like_selectors:
            try:
                el = post.locator(sel).first
                if el.count() and el.is_visible():
                    el.click(timeout=5000)
                    time.sleep(random.uniform(1.0, 2.0))
                    print(f"[INFO] Liked post #{post_index}")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def comment_on_post(page: Page, post_index: int, comment: str) -> bool:
    """
    Attempts to leave a positive comment on a post in the feed by index.
    Returns True if it believes the comment was submitted.
    """
    try:
        posts = page.locator('article').all()
        if post_index >= len(posts):
            return False

        post = posts[post_index]

        # Open comment box
        try:
            comment_button = post.locator('svg[aria-label="Comment"]').first
            if comment_button.count() and comment_button.is_visible():
                comment_button.click(timeout=5000)
                time.sleep(random.uniform(1.0, 1.5))
        except Exception:
            # Try clicking into the comment textarea directly
            pass

        # Comment textarea
        textarea_selectors = [
            'textarea[aria-label="Add a comment…"]',
            'textarea[placeholder="Add a comment…"]',
        ]
        textarea = None
        for sel in textarea_selectors:
            try:
                candidate = page.locator(sel).first
                if candidate.count() and candidate.is_visible():
                    textarea = candidate
                    break
            except Exception:
                continue

        if not textarea:
            return False

        textarea.click(timeout=5000)
        textarea.fill(comment)
        time.sleep(random.uniform(0.8, 1.5))

        # Submit comment (Enter key)
        textarea.press("Enter")
        time.sleep(random.uniform(1.5, 2.5))

        print(f"[INFO] Commented on post #{post_index}: {comment}")
        return True
    except Exception:
        return False


def scroll_feed(page: Page, times: int = 3):
    for _ in range(times):
        try:
            page.mouse.wheel(0, random.randint(600, 900))
            time.sleep(random.uniform(1.0, 2.0))
        except Exception:
            break


def interact_with_feed(
    page: Page,
    max_likes: int = 5,
    max_comments: int = 2,
    comment_probability: float = 0.4,
):
    """
    Core interaction routine:
    - Scrolls feed
    - Likes a few posts
    - Occasionally leaves positive comments
    """
    close_modals(page)

    # Ensure feed is visible
    try:
        page.wait_for_selector('div[role="feed"]', timeout=15000)
    except Exception:
        print("[WARN] Feed not detected; dumping debug.")
        dump_debug(page, "no_feed")
        return

    likes_done = 0
    comments_done = 0
    post_index = 0

    # We’ll walk through a few posts, scrolling as needed
    while likes_done < max_likes and post_index < 20:
        # Try to like this post
        if like_post(page, post_index):
            likes_done += 1

            # Maybe comment
            if comments_done < max_comments and random.random() < comment_probability:
                comment_text = generate_positive_comment()
                if comment_on_post(page, post_index, comment_text):
                    comments_done += 1

        # Move on
        post_index += 1

        # Occasionally scroll to load more posts
        if post_index % 3 == 0:
            scroll_feed(page, times=1)

        # Random human-like pause
        time.sleep(random.uniform(1.0, 2.0))

    print(f"[INFO] Interaction session complete. Likes: {likes_done}, Comments: {comments_done}")


# -----------------------------
# Hashtag / Explore Interaction (Optional)
# -----------------------------
def interact_with_hashtag(
    page: Page,
    hashtag: str,
    max_likes: int = 3,
    max_comments: int = 1,
    comment_probability: float = 0.5,
):
    """
    Visit a hashtag page and interact with a few posts.
    """
    url = f"https://www.instagram.com/explore/tags/{hashtag.strip('#')}/"
    print(f"[INFO] Visiting hashtag: {hashtag} -> {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=LONG)
    except Exception:
        print("[WARN] Failed to load hashtag page.")
        dump_debug(page, "hashtag_load_fail")
        return

    close_modals(page)
    time.sleep(random.uniform(2.0, 3.0))

    likes_done = 0
    comments_done = 0

    # Click into first few posts from the grid
    try:
        thumbs = page.locator('article a').all()
    except Exception:
        thumbs = []

    for i, thumb in enumerate(thumbs[:10]):
        try:
            thumb.click(timeout=5000)
            time.sleep(random.uniform(1.5, 2.5))

            # Now in modal view
            if like_post(page, 0):  # reuse like_post logic on the modal article
                likes_done += 1

                if comments_done < max_comments and random.random() < comment_probability:
                    comment_text = generate_positive_comment()
                    if comment_on_post(page, 0, comment_text):
                        comments_done += 1

            # Close modal
            try:
                close_btn = page.locator('button[aria-label="Close"]').first
                if close_btn.count() and close_btn.is_visible():
                    close_btn.click(timeout=5000)
            except Exception:
                page.keyboard.press("Escape")

            time.sleep(random.uniform(1.0, 2.0))

            if likes_done >= max_likes:
                break
        except Exception:
            continue

    print(f"[INFO] Hashtag interaction complete. Likes: {likes_done}, Comments: {comments_done}")


# -----------------------------
# Main Entry
# -----------------------------
def main():
    """
    Run a single interaction session:
    - Interact with home feed
    - Optionally interact with one hashtag (can be wired to Life Engine later)
    """
    hashtag: Optional[str] = os.environ.get("AI_LADY_HASHTAG")  # e.g. "girls", "selfcare", etc.

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        context_kwargs = {}
        if STORAGE_STATE.exists():
            context_kwargs["storage_state"] = str(STORAGE_STATE)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=LONG)
        except Exception:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)

        close_modals(page)
        time.sleep(random.uniform(2.0, 3.0))

        print("[INFO] Starting feed interaction…")
        interact_with_feed(
            page,
            max_likes=random.randint(3, 7),
            max_comments=random.randint(1, 3),
            comment_probability=0.4,
        )

        if hashtag:
            # Small pause between modes
            time.sleep(random.uniform(3.0, 5.0))
            print(f"[INFO] Starting hashtag interaction for #{hashtag}…")
            interact_with_hashtag(
                page,
                hashtag=hashtag,
                max_likes=random.randint(2, 5),
                max_comments=random.randint(1, 2),
                comment_probability=0.5,
            )

        browser.close()
        print("[INFO] Interaction worker finished.")


if __name__ == "__main__":
    main()
