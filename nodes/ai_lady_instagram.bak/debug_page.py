# nodes/ai_lady_instagram/debug_page.py
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError

STATE_FILE = "nodes/ai_lady_instagram/profile/state.json"
OUT_PNG = "nodes/ai_lady_instagram/ig_debug.png"
OUT_HTML = "nodes/ai_lady_instagram/ig_debug.html"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=STATE_FILE)
        page = await context.new_page()
        await page.goto("https://www.instagram.com/")
        try:
            await page.wait_for_timeout(3000)
            await page.screenshot(path=OUT_PNG, full_page=True)
            html = await page.content()
            Path(OUT_HTML).write_text(html, encoding="utf-8")
            print(f"Saved {OUT_PNG} and {OUT_HTML}")
        except Exception as e:
            print("ERROR_DEBUG:", e)
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
