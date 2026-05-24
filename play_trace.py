# play_trace.py
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    ctx = b.new_context(storage_state="nodes/ai_lady_instagram/profile/state.json")
    page = ctx.new_page()

    def on_request(r):
        print("REQ >", r.method, r.url)
    def on_response(r):
        loc = r.headers.get("location")
        print("RES >", r.status, r.url, "Location:", loc)
    def on_frame_nav(frame):
        try:
            print("FRAME NAV >", frame.url)
        except Exception:
            pass
    def on_console(msg):
        print("CONSOLE >", msg.type, msg.text)

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("framenavigated", on_frame_nav)
    page.on("console", on_console)

    print("GOING TO: https://www.instagram.com/create/select/?force=1")
    page.goto("https://www.instagram.com/create/select/?force=1")
    print("PAGE LOAD DONE — waiting 10s for any client redirects or JS navigation")
    time.sleep(10)
    print("NOW capturing current URL and location.href")
    print("CURRENT PAGE URL:", page.url)
    href = page.evaluate("() => location.href")
    print("location.href:", href)
    print("PAUSED — press Enter in terminal to finish and close browser")
    input()
    b.close()
