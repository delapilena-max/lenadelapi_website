import sys
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE = Path("nodes/ai_lady_instagram")
STORAGE_STATE = BASE / "storage_state.json"
DEBUG_DIR = BASE / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

HEADLESS = os.environ.get("POSTER_HEADLESS", "true").lower() in ("1", "true", "yes")
LONG = 120000


def dump_debug(page, name_prefix="poster_debug"):
    ts = int(time.time())
    html_path = DEBUG_DIR / f"{name_prefix}.{ts}.html"
    png_path = DEBUG_DIR / f"{name_prefix}.{ts}.png"
    try: html_path.write_text(page.content(), encoding="utf-8")
    except: pass
    try: page.screenshot(path=str(png_path), full_page=True)
    except: pass
    print(f"[DEBUG] Saved: {html_path}")
    print(f"[DEBUG] Screenshot: {png_path}")


def close_modals(page):
    selectors = [
        'button:has-text("Not Now")',
        'button:has-text("Not now")',
        'button:has-text("Close")',
        'button:has-text("Accept")',
        'button:has-text("Allow all cookies")',
        'button[aria-label="Close"]',
        'div[role="dialog"] button:has-text("OK")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=2000)
                time.sleep(0.3)
        except:
            continue


def composer_visible(page):
    try:
        loc = page.locator(
            'div[role="dialog"] input[type="file"], '
            'input[type="file"][accept*="image"], '
            'input[type="file"][accept*="video"], '
            'textarea[aria-label*="caption"]'
        )
        return loc.count() > 0
    except:
        return False


def human_click(locator):
    try: locator.hover(timeout=1500)
    except: pass

    try:
        locator.dispatch_event("pointerdown")
        locator.dispatch_event("pointerup")
    except: pass

    try:
        locator.click(timeout=1500)
        return True
    except: pass

    try:
        locator.click(timeout=1500, force=True)
        return True
    except: pass

    try:
        locator.dblclick(timeout=1500, force=True)
        return True
    except: pass

    try:
        locator.tap()
        return True
    except: pass

    return False


def click_post_in_popup(page):
    selector = 'div[role="menu"] div[role="menuitem"]:has-text("Post")'

    for attempt in range(6):
        try:
            page.wait_for_selector(selector, timeout=3000)
            el = page.locator(selector).first

            if not el.count():
                time.sleep(0.5)
                continue

            if not el.is_visible():
                time.sleep(0.5)
                continue

            box = el.bounding_box()
            if not box or box["width"] < 5 or box["height"] < 5:
                time.sleep(0.5)
                continue

            if human_click(el):
                print(f"[INFO] Clicked REAL Post (attempt {attempt+1})")
                time.sleep(2)
                return True

        except PlaywrightTimeoutError:
            time.sleep(0.5)
        except:
            time.sleep(0.5)

    print("[WARN] Could not click visible Post.")
    dump_debug(page, "post_popup_fail")
    return False


def open_composer(page):
    close_modals(page)

    try: page.wait_for_selector('div[role="feed"]', timeout=8000)
    except: pass

    create_selectors = [
        'a[href="#"] svg[aria-label="New post"]',
        'svg[aria-label="New post"]',
        'svg[aria-label="Create"]',
        'svg[aria-label="New Post"]',
        'svg[aria-label="Create new post"]',
    ]

    for attempt in range(4):
        close_modals(page)

        clicked = False
        for sel in create_selectors:
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible():
                    el.click(timeout=3000)
                    clicked = True
                    print(f"[INFO] Clicked Create (attempt {attempt+1})")
                    time.sleep(1.2)
                    break
            except:
                continue

        if not clicked:
            try:
                page.mouse.click(1180, 80)
                clicked = True
                print(f"[INFO] Clicked Create via coords (attempt {attempt+1})")
                time.sleep(1.2)
            except:
                pass

        if clicked:
            if click_post_in_popup(page):
                for _ in range(12):
                    if composer_visible(page):
                        print("[INFO] Composer opened.")
                        return True
                    time.sleep(0.6)

        time.sleep(0.8)

    dump_debug(page, "open_composer_fail")
    return False


def upload_media(page, media_path):
    try:
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(media_path)
        time.sleep(2)
        print(f"[INFO] Uploaded media: {media_path}")
        return True
    except:
        dump_debug(page, "upload_fail")
        return False


def click_next(page):
    selectors = [
        'button:has-text("Next")',
        'div[role="button"]:has-text("Next")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=3000)
                time.sleep(2)
                print(f"[INFO] Clicked Next")
                return True
        except:
            continue
    return False


def set_caption(page, caption):
    try:
        ta = page.locator('textarea[aria-label*="caption"]').first
        if ta.count():
            ta.fill(caption)
            time.sleep(1)
            print("[INFO] Caption set.")
            return True
    except:
        pass
    return False


def click_share(page):
    selectors = [
        'button:has-text("Share")',
        'div[role="button"]:has-text("Share")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=3000)
                time.sleep(3)
                print("[INFO] Clicked Share")
                return True
        except:
            continue
    return False


def wait_for_post_complete(page):
    for _ in range(40):
        if "Your post has been shared" in page.content():
            print("[INFO] Post confirmed shared.")
            return True
        time.sleep(1)
    print("[WARN] No confirmation text.")
    return False


def main():
    if len(sys.argv) < 3:
        print("Usage: poster_retry.py <media_path> <caption>")
        sys.exit(1)

    media_path = sys.argv[1]
    caption = sys.argv[2]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)

        ctx_args = {}
        if STORAGE_STATE.exists():
            ctx_args["storage_state"] = str(STORAGE_STATE)

        context = browser.new_context(**ctx_args)
        page = context.new_page()

        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=LONG)
        close_modals(page)

        if not open_composer(page):
            print("[ERROR] Failed to open composer.")
            dump_debug(page, "composer_open_fail")
            browser.close()
            sys.exit(2)

        if not upload_media(page, media_path):
            print("[ERROR] Failed to upload media.")
            browser.close()
            sys.exit(3)

        if not click_next(page):
            print("[ERROR] Failed at first Next.")
            dump_debug(page, "next_fail")
            browser.close()
            sys.exit(4)

        if not click_next(page):
            print("[ERROR] Failed at second Next.")
            dump_debug(page, "next2_fail")
            browser.close()
            sys.exit(5)

        if not set_caption(page, caption):
            print("[ERROR] Failed to set caption.")
            dump_debug(page, "caption_fail")
            browser.close()
            sys.exit(6)

        if not click_share(page):
            print("[ERROR] Failed to click Share.")
            dump_debug(page, "share_fail")
            browser.close()
            sys.exit(7)

        if not wait_for_post_complete(page):
            print("[WARN] Post may not have completed.")
            dump_debug(page, "post_wait_fail")
            browser.close()
            sys.exit(8)

        browser.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
