import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            "pw_profile",
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        )
        with open("kling_state.json","r",encoding="utf-8") as f:
            state = json.load(f)
        await context.add_cookies(state.get("cookies", []))
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://kling.ai/app/image/new", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        matches = await page.locator("text=Generate").all()
        print("Matches found:", len(matches))
        for i, m in enumerate(matches, 1):
            outer = await m.evaluate("el => el.outerHTML")
            print(f"\n--- Match {i} ---\n{outer}\n")

        await page.wait_for_timeout(2000)

if __name__ == "__main__":
    asyncio.run(main())
