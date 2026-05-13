from playwright.sync_api import sync_playwright
import sys

def main():
    pw = sync_playwright().start()
    try:
        # Try IPv4 loopback (some Windows setups bind CDP to 127.0.0.1 instead of ::1)
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        ctx.storage_state(path="kling_state.json")
        print("Saved storage state to kling_state.json")
    except Exception as e:
        print("ERROR saving storage state:", e, file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            pw.stop()
        except Exception:
            pass

if __name__ == "__main__":
    main()
