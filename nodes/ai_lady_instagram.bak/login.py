# nodes/ai_lady_instagram/login.py

import asyncio
from playwright.async_api import async_playwright

PROFILE_DIR = "nodes/ai_lady_instagram/profile"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
        )

        page = await browser.new_page()
        await page.goto("https://www.instagram.com/")

        print("\n----------------------------------------")
        print("Log in manually in the browser window.")
        print("When you see your Instagram home feed,")
        print("come back here and press ENTER.")
        print("----------------------------------------\n")
        input()

        print("Saving session…")
        await browser.storage_state(path=f"{PROFILE_DIR}/state.json")
        print("Done. Session saved.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
