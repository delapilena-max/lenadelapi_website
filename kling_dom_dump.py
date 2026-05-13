import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        # Start persistent context
        context = await p.chromium.launch_persistent_context(
            "pw_profile",
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        )

        # Load cookies manually
        with open("kling_state.json", "r", encoding="utf-8") as f:
            state = json.load(f)

        await context.add_cookies(state["cookies"])

        # Use existing page or open a new one
        if context.pages:
            page = context.pages[0]
        else:
            page = await context.new_page()

        await page.goto("https://kling.ai/app/image/new", wait_until="domcontentloaded")

        # Wait for UI to settle
        await page.wait_for_timeout(3000)

        # Dump full DOM
        html = await page.content()

        print("\n=== DOM DUMP START ===\n")
        print(html[:20000])  # print first 20k chars
        print("\n=== DOM DUMP END ===\n")

        # Keep window open briefly
        await page.wait_for_timeout(5000)

if __name__ == "__main__":
    asyncio.run(main())
