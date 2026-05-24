# play_debug_redirect.py
from playwright.sync_api import sync_playwright
import json, time

STATE = "nodes/ai_lady_instagram/profile/state.json"
TARGET = "https://www.instagram.com/create/select/?force=1"

def dict_from_storage(page, storage_name):
    try:
        items = page.evaluate(f"() => Object.fromEntries(Object.entries({storage_name}))")
        return items
    except Exception as e:
        return {"error": str(e)}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state=STATE)
    page = context.new_page()

    # Network logging
    def on_request(r):
        print("REQ >", r.method, r.url)
    def on_response(r):
        loc = r.headers.get("location")
        print("RES >", r.status, r.url, "Location:", loc)
    page.on("request", on_request)
    page.on("response", on_response)

    # Console and frame navigation
    page.on("console", lambda msg: print("CONSOLE >", msg.type, msg.text))
    page.on("framenavigated", lambda frame: print("FRAME NAV >", frame.url))

    # Inject overrides BEFORE navigation to catch client-side redirects
    page.add_init_script(
        """
        // Prevent and log common client-side navigations
        (function(){
            const log = (k,v)=>{ try{ console.log('[NAV-INTERCEPT]', k, v); }catch(e){} };
            const origAssign = window.location.assign;
            const origReplace = window.location.replace;
            window.location.assign = function(u){ log('assign', u); /* block */ };
            window.location.replace = function(u){ log('replace', u); /* block */ };
            Object.defineProperty(window.location, 'href', {
                set: function(u){ log('set href', u); /* block */ },
                get: function(){ return document.location.href; }
            });
            const origPush = history.pushState;
            const origReplaceState = history.replaceState;
            history.pushState = function(s, t, u){ log('pushState', u); return origPush.apply(this, arguments); };
            history.replaceState = function(s, t, u){ log('replaceState', u); return origReplaceState.apply(this, arguments); };
            // catch meta refresh
            const observer = new MutationObserver(()=> {
                const metas = document.querySelectorAll('meta[http-equiv="refresh"]');
                metas.forEach(m=>{ log('meta-refresh', m.getAttribute('content')); m.setAttribute('content','0;url=about:blank'); });
            });
            try { observer.observe(document, { childList:true, subtree:true }); } catch(e){}
            // intercept fetch/XHR that might navigate
            const origFetch = window.fetch;
            window.fetch = function(){ log('fetch called', arguments[0]); return origFetch.apply(this, arguments); };
            const XHR = window.XMLHttpRequest;
            function X(){ XHR.apply(this, arguments); this.addEventListener('load', function(){ try{ console.log('[XHR-LOAD]', this.responseURL); }catch(e){} }); }
            X.prototype = XHR.prototype;
            window.XMLHttpRequest = X;
        })();
        """
    )

    print("GOING TO:", TARGET)
    page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)

    print("PAGE DOMCONTENTLOADED. Waiting 8s for client scripts to run...")
    time.sleep(8)

    # Capture current URL and location.href
    try:
        current_url = page.url
    except Exception as e:
        current_url = f"error: {e}"
    try:
        href = page.evaluate("() => location.href")
    except Exception as e:
        href = f"error: {e}"

    print("\n--- SUMMARY ---")
    print("CURRENT PAGE URL:", current_url)
    print("location.href:", href)

    # Cookies
    try:
        cookies = context.cookies()
    except Exception as e:
        cookies = [{"error": str(e)}]
    print("\nCookies (count={}):".format(len(cookies)))
    for c in cookies:
        print(json.dumps(c, ensure_ascii=False))

    # localStorage / sessionStorage
    ls = dict_from_storage(page, "localStorage")
    ss = dict_from_storage(page, "sessionStorage")
    print("\nlocalStorage keys/values:")
    print(json.dumps(ls, indent=2, ensure_ascii=False))
    print("\nsessionStorage keys/values:")
    print(json.dumps(ss, indent=2, ensure_ascii=False))

    # meta refresh tags
    try:
        metas = page.evaluate("() => Array.from(document.querySelectorAll('meta[http-equiv]')).map(m=>({httpEquiv:m.httpEquiv, content:m.content, outerHTML:m.outerHTML}))")
    except Exception as e:
        metas = [{"error": str(e)}]
    print("\nmeta[http-equiv] tags:")
    print(json.dumps(metas, indent=2, ensure_ascii=False))

    # service worker registrations
    try:
        sw_regs = page.evaluate("() => navigator.serviceWorker.getRegistrations().then(r=>r.map(reg=>({scope: reg.scope, active: !!reg.active})))")
    except Exception as e:
        sw_regs = {"error": str(e)}
    print("\nserviceWorker registrations (may be empty):")
    print(json.dumps(sw_regs, indent=2, ensure_ascii=False))

    print("\n--- END SUMMARY ---")
    print("PAUSE: Press Enter to close browser and finish.")
    input()
    browser.close()
