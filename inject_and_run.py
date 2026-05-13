"""
inject_and_run.py
Reads kling_state.json, injects cookies + localStorage into the running
Chrome (CDP on 127.0.0.1:9222), verifies kling.ai login, saves state back,
then runs face_cache_builder.py --count 1 and streams all output.

Usage (from repo root, venv active):
    python inject_and_run.py
"""

import asyncio, json, subprocess, sys, pathlib, time

STATE_FILE = pathlib.Path("kling_state.json")
CDP_URL    = "http://127.0.0.1:9222"
TARGET_URL = "https://kling.ai/app/image/new"
BUILDER    = ["python", "face_cache_builder.py", "--count", "1"]

async def inject_and_verify():
    from playwright.async_api import async_playwright

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    cookies   = state.get("cookies", [])
    origins   = state.get("origins", [])   # Playwright storage-state format
    ls_items  = {}

    # Pull localStorage for kling.ai from origins array (Playwright format)
    for origin in origins:
        if "kling.ai" in origin.get("origin", ""):
            for item in origin.get("localStorage", []):
                ls_items[item["name"]] = item["value"]

    print(f"[inject] Loaded {len(cookies)} cookies, {len(ls_items)} localStorage keys")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # --- Set cookies ---
        kling_cookies = [c for c in cookies if "kling.ai" in c.get("domain", "")]
        if kling_cookies:
            await ctx.add_cookies(kling_cookies)
            print(f"[inject] Set {len(kling_cookies)} kling.ai cookies")

        # --- Navigate and inject localStorage ---
        print(f"[inject] Navigating to {TARGET_URL} ...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        if ls_items:
            js_set = "; ".join(
                f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)})"
                for k, v in ls_items.items()
            )
            await page.evaluate(js_set)
            print(f"[inject] Set {len(ls_items)} localStorage keys")
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

        # --- Check login ---
        user_val = await page.evaluate("localStorage.getItem('user')")
        title    = await page.title()
        print(f"[inject] Page title : {title}")
        print(f"[inject] localStorage['user'] present: {bool(user_val)}")

        # Heuristic: if URL redirected to login page we're still logged out
        current = page.url
        if "login" in current.lower() or "signin" in current.lower():
            print("[inject] WARNING: page redirected to login — manual sign-in may still be needed")
            print("[inject] Complete login in the browser window, then press ENTER here to continue...")
            input()
            # Refresh check after manual login
            user_val = await page.evaluate("localStorage.getItem('user')")
            print(f"[inject] After manual login — localStorage['user'] present: {bool(user_val)}")

        # --- Save updated state back ---
        updated_storage = await ctx.storage_state()
        STATE_FILE.write_text(json.dumps(updated_storage, indent=2), encoding="utf-8")
        print(f"[inject] Saved updated storage state to {STATE_FILE}")

        await browser.close()

    return bool(user_val)

def run_builder():
    print("\n" + "="*60)
    print(f"[builder] Running: {' '.join(BUILDER)}")
    print("="*60 + "\n")
    result = subprocess.run(
        BUILDER,
        stdout=sys.stdout,  # stream live
        stderr=sys.stderr,
        text=True,
    )
    print("\n" + "="*60)
    print(f"[builder] Exit code: {result.returncode}")
    print("="*60)
    return result.returncode

async def main():
    try:
        logged_in = await inject_and_verify()
        if not logged_in:
            print("[inject] Could not confirm login — proceeding anyway (builder may fail)")
    except Exception as e:
        print(f"[inject] CDP injection error: {e}")
        print("[inject] Proceeding to builder run anyway...")

    rc = run_builder()
    sys.exit(rc)

if __name__ == "__main__":
    asyncio.run(main())