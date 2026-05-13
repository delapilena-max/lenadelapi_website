import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import json
import os

STATE_PATH = Path("kling_state.json")

# Path to your REAL Chrome installation
REAL_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            "pw_profile",
            headless=False,
            executable_path=REAL_CHROME,
            args=[
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1400, "height": 900},
            locale="en-US",
            java_script_enabled=True,
        )

        page = await browser.new_page()
        await page.goto("https://kling.ai", wait_until="domcontentloaded")

        print("\n=== LOG IN TO KLING (REAL CHROME) ===")
        print("This is your ACTUAL Chrome, not Chrome-for-Testing.")
        print("Google login WILL work here.")
        print("Log in normally. I will capture state in 5 minutes.\n")

        await page.wait_for_timeout(5 * 60 * 1000)

        state = await browser.storage_state()
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

        print(f"Saved authenticated state to {STATE_PATH.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())
