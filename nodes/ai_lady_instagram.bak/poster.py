# nodes/ai_lady_instagram/poster.py

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError

STATE_FILE = "nodes/ai_lady_instagram/profile/state.json"

async def post_instagram(video_path: str, caption: str):
    video_path = str(Path(video_path).resolve())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=STATE_FILE)
        page = await context.new_page()

        # Warm up session
        await page.goto("https://www.instagram.com/")
        try:
            await page.wait_for_selector("a[href='/explore/']", timeout=20000)
        except TimeoutError:
            print("ERROR: Home feed did not load. Session may be invalid.")
            await browser.close()
            return

        print("Home feed loaded. Session warmed.")

        # Click through Create -> Post -> open file chooser (robust, many fallbacks)
        try:
            # Try explicit aria/title/selectors for the "new post" / "create" control
            create_selectors = [
                "button[aria-label='New post']",
                "button[aria-label='Create']",
                "button[title='Create']",
                "button:has-text('+ Create')",
                "text=Create",
                "svg[aria-label='New post']",
                "div[role='button'][aria-label='New post']"
            ]
            clicked = False
            for sel in create_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=3000)
                    await page.click(sel)
                    clicked = True
                    break
                except TimeoutError:
                    continue

            if not clicked:
                # Try the top-right "plus" icon by role/menu patterns
                try:
                    await page.wait_for_selector("header button, div[role='menu'] button", timeout=3000)
                    candidates = await page.query_selector_all("header button, div[role='menu'] button, button[role='menuitem']")
                    for c in candidates:
                        try:
                            # avoid clicking profile avatar by checking accessible name
                            name = ""
                            try:
                                name = (await c.get_attribute("aria-label")) or (await c.inner_text())
                            except Exception:
                                name = ""
                            if name and "profile" in name.lower():
                                continue
                            await c.click()
                            clicked = True
                            break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not clicked:
                print("ERROR: Create control not found.")
                await browser.close()
                return

            # Wait for the menu and click Post (try text and role fallbacks)
            post_selectors = ["text=Post", "button:has-text('Post')", "div[role='menuitem']:has-text('Post')"]
            post_clicked = False
            for sel in post_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                    await page.click(sel)
                    post_clicked = True
                    break
                except TimeoutError:
                    continue

            if not post_clicked:
                # Some UIs show a modal with "Create" options as buttons; try clicking the first "Post" like element
                try:
                    await page.wait_for_timeout(1000)
                    candidates = await page.query_selector_all("button, div[role='menuitem'], a")
                    for c in candidates:
                        try:
                            txt = (await c.inner_text()).strip().lower()
                        except Exception:
                            txt = ""
                        if "post" in txt or "select from computer" in txt or "select" in txt:
                            try:
                                await c.click()
                                post_clicked = True
                                break
                            except Exception:
                                continue
                except Exception:
                    pass

            if not post_clicked:
                print("ERROR: Could not find Post option in Create menu.")
                await browser.close()
                return

            # Wait for either the visible file input or the "Select from computer" button
            try:
                file_input = await page.wait_for_selector("input[type='file']", timeout=8000)
            except TimeoutError:
                # Try explicit button selector first, then the text= fallback (separate calls)
                try:
                    await page.wait_for_selector("button:has-text('Select from computer')", timeout=8000)
                    await page.click("button:has-text('Select from computer')")
                    file_input = await page.wait_for_selector("input[type='file']", timeout=8000)
                except TimeoutError:
                    try:
                        await page.wait_for_selector("text=Select from computer", timeout=8000)
                        await page.click("text=Select from computer")
                        file_input = await page.wait_for_selector("input[type='file']", timeout=8000)
                    except TimeoutError:
                        print("ERROR: File chooser not found after Post.")
                        await browser.close()
                        return

        except TimeoutError:
            print("ERROR: Could not navigate Create -> Post -> file chooser. UI selectors may have changed.")
            await browser.close()
            return

        print("Upload page loaded or file chooser opened.")

        # Upload video
        await file_input.set_input_files(video_path)
        print("Video selected.")

        await page.wait_for_timeout(4000)

        # Next → Next (handle buttons that may be labeled differently)
        try:
            next_btn = await page.wait_for_selector("text=Next", timeout=20000)
            await next_btn.click()
            await page.wait_for_timeout(2000)

            next_btn = await page.wait_for_selector("text=Next", timeout=20000)
            await next_btn.click()
            await page.wait_for_timeout(2000)
        except TimeoutError:
            # Some flows use aria-label or different text; try alternative selectors
            try:
                next_btn = await page.wait_for_selector("button[aria-label='Next']", timeout=5000)
                await next_btn.click()
                await page.wait_for_timeout(2000)
            except TimeoutError:
                print("WARNING: Could not find Next button(s). Continuing to caption step.")

        # Caption
        try:
            # Prefer placeholder/aria-label that contains "caption" or fallback to any textarea
            try:
                caption_box = await page.wait_for_selector("textarea[placeholder*='caption'], textarea[aria-label*='caption']", timeout=15000)
            except TimeoutError:
                caption_box = await page.wait_for_selector("textarea", timeout=15000)
        except TimeoutError:
            print("ERROR: Caption box not found.")
            await browser.close()
            return

        await caption_box.fill(caption)
        print("Caption filled.")

        # Share (handle different button text variants)
        try:
            share_button = await page.wait_for_selector("text=Share", timeout=20000)
            await share_button.click()
        except TimeoutError:
            try:
                share_button = await page.wait_for_selector("button[aria-label='Share']", timeout=10000)
                await share_button.click()
            except TimeoutError:
                print("ERROR: Share button not found.")
                await browser.close()
                return

        print("Posting…")

        await page.wait_for_timeout(8000)

        print("Post complete.")
        await browser.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python poster.py <video_path> <caption>")
        sys.exit(1)

    video = sys.argv[1]
    caption = " ".join(sys.argv[2:])
    asyncio.run(post_instagram(video, caption))
