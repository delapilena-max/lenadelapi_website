# nodes/ai_lady_instagram/poster_persistent_auto.py
# Usage:
# & .\.venv\Scripts\python.exe nodes/ai_lady_instagram/poster_persistent_auto.py output/final.mp4 "Caption text here"

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError

PROFILE_DIR = "nodes/ai_lady_instagram/profile"  # persistent profile folder
TARGET_UPLOAD = "https://www.instagram.com/create/select/?force=1"
LOG_DIR = Path("nodes/ai_lady_instagram/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

async def run_upload(video_path: str, caption: str):
    video_path = str(Path(video_path).resolve())
    async with async_playwright() as p:
        # Launch persistent context so the real profile (cookies, logged-in) is used
        try:
            context = await p.chromium.launch_persistent_context(user_data_dir=PROFILE_DIR, headless=False)
        except Exception as e:
            print("ERROR: Could not launch persistent context:", e)
            return 1

        page = await context.new_page()

        # Warm session
        try:
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        # Navigate directly to the upload URL
        try:
            await page.goto(TARGET_UPLOAD, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print("ERROR: Could not navigate to upload URL:", e)
            await context.close()
            return 1

        # Helper: try multiple selectors to find file input or "Select from computer" button
        file_input = None
        try:
            # 1) direct file input
            try:
                file_input = await page.wait_for_selector("input[type='file']", timeout=7000)
            except TimeoutError:
                file_input = None

            # 2) "Select from computer" button then file input
            if not file_input:
                try:
                    btn = await page.wait_for_selector("button:has-text('Select from computer')", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    file_input = await page.wait_for_selector("input[type='file']", timeout=5000)
                except TimeoutError:
                    file_input = None

            # 3) text fallback
            if not file_input:
                try:
                    btn = await page.wait_for_selector("text=Select from computer", timeout=5000)
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    file_input = await page.wait_for_selector("input[type='file']", timeout=5000)
                except TimeoutError:
                    file_input = None

            # 4) try scanning for any visible input[type=file] in the DOM
            if not file_input:
                inputs = await page.query_selector_all("input[type='file']")
                for inp in inputs:
                    try:
                        visible = await inp.is_visible()
                    except Exception:
                        visible = True
                    if visible:
                        file_input = inp
                        break

            if not file_input:
                print("ERROR: File chooser/input not found on upload page.")
                await dump_page_for_debug(page)
                await context.close()
                return 1

        except Exception as e:
            print("ERROR: Exception while locating file input:", e)
            await dump_page_for_debug(page)
            await context.close()
            return 1

        # Upload the file
        try:
            await file_input.set_input_files(video_path)
            print("Video selected.")
        except Exception as e:
            print("ERROR: Failed to set input files:", e)
            await dump_page_for_debug(page)
            await context.close()
            return 1

        # Wait for UI to accept the file and show Next/preview
        await page.wait_for_timeout(3000)

        # Click Next twice (some flows require two Next clicks)
        try:
            for _ in range(2):
                try:
                    btn = await page.wait_for_selector("text=Next", timeout=10000)
                    await btn.click()
                    await page.wait_for_timeout(1200)
                except TimeoutError:
                    # fallback to aria-label
                    try:
                        btn = await page.wait_for_selector("button[aria-label='Next']", timeout=4000)
                        await btn.click()
                        await page.wait_for_timeout(1200)
                    except TimeoutError:
                        # if Next not found, continue — maybe already on caption step
                        break
        except Exception as e:
            print("WARNING: Error clicking Next buttons:", e)

        # Fill caption
        try:
            caption_box = None
            try:
                caption_box = await page.wait_for_selector("textarea[placeholder*='caption'], textarea[aria-label*='caption']", timeout=8000)
            except TimeoutError:
                # fallback to any textarea
                try:
                    caption_box = await page.wait_for_selector("textarea", timeout=8000)
                except TimeoutError:
                    caption_box = None

            if not caption_box:
                print("ERROR: Caption box not found.")
                await dump_page_for_debug(page)
                await context.close()
                return 1

            await caption_box.fill(caption)
            print("Caption filled.")
        except Exception as e:
            print("ERROR: Failed to fill caption:", e)
            await dump_page_for_debug(page)
            await context.close()
            return 1

        # Click Share
        try:
            try:
                share_btn = await page.wait_for_selector("text=Share", timeout=15000)
                await share_btn.click()
            except TimeoutError:
                share_btn = await page.wait_for_selector("button[aria-label='Share']", timeout=8000)
                await share_btn.click()
        except TimeoutError:
            print("ERROR: Share button not found.")
            await dump_page_for_debug(page)
            await context.close()
            return 1
        except Exception as e:
            print("ERROR: Exception clicking Share:", e)
            await dump_page_for_debug(page)
            await context.close()
            return 1

        # Wait for post to complete (heuristic: wait and look for toast or redirect)
        await page.wait_for_timeout(8000)
        print("Posting initiated; waiting briefly for completion.")
        await page.wait_for_timeout(4000)

        # Close context (keeps profile changes)
        await context.close()
        print("Post flow finished (no fatal errors detected).")
        return 0

async def dump_page_for_debug(page):
    try:
        url = page.url
    except Exception:
        url = "<error reading page.url>"
    try:
        html = await page.content()
        path = LOG_DIR / "last_page.html"
        path.write_text(html, encoding="utf-8")
        print(f"Saved page HTML to {path}")
    except Exception as e:
        print("Could not save page HTML:", e)
    try:
        ls = await page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
        ss = await page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))")
        snapshot = {"url": url, "localStorage": ls, "sessionStorage": ss}
        (LOG_DIR / "last_page_snapshot.json").write_text(str(snapshot), encoding="utf-8")
        print("Saved page snapshot.")
    except Exception as e:
        print("Could not save page snapshot:", e)

def write_run_log(video_path: str, out: str):
    name = Path(video_path).name
    (LOG_DIR / f"{name}.runlog").write_text(out, encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: poster_persistent_auto.py <video_path> <caption>")
        sys.exit(2)
    video = sys.argv[1]
    caption = " ".join(sys.argv[2:])
    rc = asyncio.run(run_upload(video, caption))
    write_run_log(video, f"Exit code: {rc}\n")
    sys.exit(rc)
