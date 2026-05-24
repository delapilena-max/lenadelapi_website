# nodes/ai_lady_instagram/open_composer.py
from playwright.sync_api import sync_playwright, TimeoutError
import sys, time

def verify_composer_open(page):
    return page.locator('input[type="file"], div[role="dialog"] textarea, div[role="dialog"] input').count() > 0

def open_composer(page):
    selectors = [
        'a[role="link"]:has-text("Create")',
        'button[aria-label="Create"]',
        'a[href^="/create"]',
        'svg[aria-label="New post"]',
        'a[title="Create"]',
        'button[aria-label*="New"]'
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                try:
                    el.click(timeout=5000)
                    time.sleep(0.5)
                    if verify_composer_open(page):
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    # fallback: read href and navigate
    try:
        href = page.get_attribute('a:has-text("Create")', 'href')
        if href:
            base = "https://www.instagram.com"
            page.goto(base + href, wait_until="networkidle")
            if verify_composer_open(page):
                return True
    except Exception:
        pass

    # final fallback: try generic new/plus button
    try:
        alt = page.locator('button[aria-label*="New"], button[aria-label*="Create"]').first
        if alt.count() and alt.is_visible():
            alt.click()
            time.sleep(0.5)
            if verify_composer_open(page):
                return True
    except Exception:
        pass

    raise RuntimeError("Unable to open composer via UI selectors or href fallback")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.instagram.com/", wait_until="networkidle")
        time.sleep(2)
        try:
            ok = open_composer(page)
            print("Composer opened:", ok)
        except Exception as e:
            print("Failed to open composer:", str(e))
            nav = page.locator('nav')
            if nav.count():
                print("Nav snapshot:", nav.inner_html()[:2000])
            sys.exit(1)
        # keep browser open for inspection; close if you want:
        # browser.close()

if __name__ == "__main__":
    main()
