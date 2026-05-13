import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        # Start persistent context FIRST
        context = await p.chromium.launch_persistent_context(
            "pw_profile",
            headless=False,
        )

        # THEN load cookies manually (the correct API)
        with open("kling_state.json", "r", encoding="utf-8") as f:
            state = json.load(f)

        # Add cookies to the context
        await context.add_cookies(state["cookies"])

        page = await context.new_page()
        await page.goto("https://kling.ai", wait_until="domcontentloaded")

        print("Loaded Kling with your real Chrome cookies.")

        # Keep browser open
        await page.wait_for_timeout(99999999)

if __name__ == "__main__":
    asyncio.run(main())
