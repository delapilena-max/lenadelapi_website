import os
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("nodes/ai_lady_instagram")
STORAGE_STATE = BASE / "storage_state.json"
DEBUG_DIR = BASE / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

IG_USERNAME = os.environ.get("IG_USERNAME")
IG_PASSWORD = os.environ.get("IG_PASSWORD")
HEADLESS = os.environ.get("POSTER_HEADLESS", "false").lower() in ("1", "true", "yes")

SHORT = 10000
MEDIUM = 30000
LONG = 120000


def dump_debug(page, name_prefix="save_state"):
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


def detect_login_page(page):
    try:
        if page.locator('input[name="username"], input[name="password"]').count():
            return True
        body = page.locator("body").inner_text().lower()
        if "log into instagram" in body:
            return True
    except Exception:
        pass
    return False


def close_modals(page):
    selectors = [
        'button:has-text("Not Now")',
        'button:has-text("Not now")',
        'button:has-text("Close")',
        'button:has-text("Accept")',
        'button:has-text("Continue")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=5000)
                time.sleep(0.5)
        except Exception:
            continue


def login(page):
    if not detect_login_page(page):
        return True

    if IG_USERNAME and IG_PASSWORD:
        try:
            u = page.locator('input[name="username"]').first
            if u.count():
                u.fill(IG_USERNAME, timeout=SHORT)

            p = page.locator('input[name="password"]').first
            if p.count():
                p.fill(IG_PASSWORD, timeout=SHORT)

            btn = page.locator('button[type="submit"]').first
            if btn.count():
                btn.click(timeout=SHORT)

            for _ in range(60):
                time.sleep(1)
                if not detect_login_page(page):
                    return True

        except Exception:
            pass

    if HEADLESS:
        print("Headless mode: cannot complete manual login.")
        return False

    print("Please complete login manually in the browser window.")
    for _ in range(180):
        time.sleep(1)
        if not detect_login_page(page):
            return True

    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=LONG)
        except Exception:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)

        close_modals(page)

        if not login(page):
            dump_debug(page, "login_failed")
            print("Login failed.")
            return

        close_modals(page)

        try:
            context.storage_state(path=str(STORAGE_STATE))
            print(f"Saved storage state to {STORAGE_STATE}")
        except Exception:
            dump_debug(page, "save_state_failed")
            print("Failed to save storage state.")

        browser.close()


if __name__ == "__main__":
    main()
