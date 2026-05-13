import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright


async def run_kling_job(manifest_path: Path, output_dir: Path):
    """
    Execute a Kling job described in the manifest using saved authenticated state.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clip = manifest["clips"][0]  # one clip per storyboard for now

    prompt = clip["prompt"]
    duration = clip["duration_seconds"]
    output_path = Path(clip["output_path"])

    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        # ⭐ Load the saved authenticated session ⭐
        context = await browser.new_context(
            storage_state="C:/projects/ai/content_bot/kling_state.json"
        )

        page = await context.new_page()

        # Force global region login page (even though you're already logged in)
        await page.goto(
            "https://klingai.com/video?lang=en&region=global",
            wait_until="networkidle"
        )

        # Wait for page to load
        await page.wait_for_load_state("networkidle")

        # Fill prompt
        await page.fill("textarea.prompt-input", prompt)

        # Set duration if UI supports it
        try:
            await page.fill("input.duration-input", str(duration))
        except:
            pass  # Kling UI changes often

        # Click generate
        await page.click("button.generate-btn")

        # Wait for render to complete
        await page.wait_for_selector("video.generated-video", timeout=600000)

        # Get video URL
        video_url = await page.get_attribute("video.generated-video", "src")

        # Download video
        video_bytes = await page.evaluate(
            """async (url) => {
                const res = await fetch(url);
                const buf = await res.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }""",
            video_url
        )

        # Save file
        with open(output_path, "wb") as f:
            f.write(bytes(video_bytes))

        await browser.close()

    return str(output_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run Kling automation for a manifest.")
    parser.add_argument("--manifest", required=True, help="Path to Kling job manifest JSON")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clip = manifest["clips"][0]
    output_path = Path(clip["output_path"]).resolve()
    output_dir = output_path.parent

    # Run async
    final_path = asyncio.run(run_kling_job(manifest_path, output_dir))

    print(json.dumps({"clip": final_path}, indent=2))


if __name__ == "__main__":
    main()
