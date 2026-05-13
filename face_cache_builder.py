#!/usr/bin/env python3
"""
face_cache_builder.py
Stable auto-prompting Playwright script.

Priority for prompt:
1) CLI --prompt
2) ENV PROMPT_TEXT
3) templates/prompt.txt
4) aggregated prompts from project files (newest)
5) fallback default
"""
import argparse, os, time, re, json, base64, requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE_DIR = "pw_profile"
STORAGE_STATE_FILE = "kling_state.json"
OUT_DIR = Path("nodes/ai_lady/face_cache")
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE_URL = "https://kling.ai/app/image/new"
DEFAULT_TIMEOUT_MS = 45_000

def ensure_out_dir():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

def save_bytes_to_file(bts, out_path):
    with open(out_path, "wb") as f:
        f.write(bts)

def download_http_src(src_url, out_path):
    resp = requests.get(src_url, timeout=30)
    resp.raise_for_status()
    save_bytes_to_file(resp.content, out_path)
    return out_path

def save_data_url(data_url, out_path):
    header, b64 = data_url.split(",", 1)
    data = base64.b64decode(b64)
    save_bytes_to_file(data, out_path)
    return out_path

def save_image_src_sync(src, out_path, page=None):
    if not src:
        raise RuntimeError("Empty image src")
    if src.startswith("data:"):
        return save_data_url(src, out_path)
    src = src.strip().strip('"').strip("'")
    if page is not None:
        try:
            r = page.request.get(src, timeout=30_000)
            if getattr(r, "status", None) != 200:
                return download_http_src(src, out_path)
            content = r.body()
            save_bytes_to_file(content, out_path)
            return out_path
        except Exception:
            return download_http_src(src, out_path)
    else:
        return download_http_src(src, out_path)

# Minimal robust prompt aggregation
def _read_text_file(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return ""

def _extract_prompts_from_text(text):
    candidates = []
    for m in re.finditer(r'(?im)^\s*(prompt|description|scene|seed_prompt)\s*[:=-]\s*(.+)$', text):
        val = m.group(2).strip().strip('\"\'')
        if len(val) >= 20:
            candidates.append(val)
    for m in re.finditer(r'(?s)"?(prompt|description|scene|seed_prompt)"?\s*[:=]\s*"([^"]{20,})"', text):
        candidates.append(m.group(2).strip())
    paras = re.split(r'\n{2,}', text)
    for p in paras:
        s = p.strip()
        if len(s) >= 40 and not re.match(r'^[\-\*\`\#\s]+$', s):
            candidates.append(" ".join(s.splitlines()).strip())
    seen = set(); out=[]
    for c in candidates:
        if c not in seen:
            seen.add(c); out.append(c)
    return out

def aggregate_prompts_from_project():
    root = Path(".").resolve()
    paths = ["templates","prompts","life_generator","director","storyboard","nodes","."]
    found=[]
    for base in paths:
        basep = (root / base).resolve()
        if not basep.exists(): continue
        files = [basep] if basep.is_file() else [p for p in basep.rglob("*") if p.is_file()]
        for p in files:
            try:
                text = _read_text_file(p)
                candidates = _extract_prompts_from_text(text)
                for c in candidates:
                    c_norm = " ".join(c.split())
                    if len(c_norm) >= 20:
                        found.append((c_norm, str(p), p.stat().st_mtime))
            except Exception:
                continue
    found_sorted = sorted(found, key=lambda t: t[2], reverse=True)
    seen=set(); out=[]
    for prompt,src,mt in found_sorted:
        if prompt in seen: continue
        seen.add(prompt); out.append((prompt,src,mt))
    return out

def load_auto_prompt(args):
    if getattr(args, "prompt", None):
        p = args.prompt.strip()
        if p: return p
    envp = os.environ.get("PROMPT_TEXT")
    if envp and envp.strip(): return envp.strip()
    tpl = Path("templates") / "prompt.txt"
    if tpl.exists():
        try:
            txt = tpl.read_text(encoding="utf-8").strip()
            if txt: return txt
        except Exception:
            pass
    agg = aggregate_prompts_from_project()
    if agg:
        return agg[0][0]
    return "photorealistic portrait of a young woman, neutral background, studio lighting, high detail"

def ensure_prompt_filled_sync(page, prompt_text, timeout=10000):
    selectors = [
        "textarea[placeholder*='prompt']","textarea","input[placeholder*='prompt']",
        "div[contenteditable='true']","div[role='textbox']","[data-testid*='prompt']","[aria-label*='prompt']"
    ]
    end = time.time() + (timeout/1000.0)
    last_err=None
    while time.time() < end:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if not loc.count(): continue
                try:
                    tag = loc.evaluate("el => el.tagName.toLowerCase()")
                except Exception:
                    tag = ""
                if tag in ("textarea","input"):
                    try:
                        loc.fill(prompt_text)
                    except Exception:
                        loc.evaluate("el => { el.value = arguments[0]; }", prompt_text)
                    try:
                        loc.evaluate("el => el.blur && el.blur()")
                    except Exception:
                        pass
                else:
                    try:
                        loc.evaluate("(el, txt) => { el.focus(); el.innerText = txt; el.dispatchEvent(new Event('input',{bubbles:true})); el.blur(); }", prompt_text)
                    except Exception:
                        try:
                            loc.evaluate("el => { el.textContent = arguments[0]; }", prompt_text)
                        except Exception:
                            pass
                val = ""
                try:
                    if tag in ("textarea","input"):
                        val = loc.evaluate("el => el.value") or ""
                    else:
                        val = loc.evaluate("el => el.innerText || el.textContent || ''") or ""
                except Exception:
                    val = ""
                if val and val.strip(): return True
            except Exception as e:
                last_err = e; continue
        time.sleep(0.25)
    raise RuntimeError(f"Failed to set prompt text. Last error: {last_err}")

def click_generate_and_get_src_sync(page, timeout=DEFAULT_TIMEOUT_MS):
    candidates = ["div.inner:has-text(\"Generate\")","text=Generate","button:has-text(\"Generate\")","button:has-text(\"Create\")"]
    clicked=False
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_enabled():
                loc.click(); clicked=True; break
        except Exception:
            continue
    if not clicked:
        try:
            btn = page.locator("button:visible, [role='button']:visible").first
            if btn.count() and btn.is_enabled():
                btn.click(); clicked=True
        except Exception:
            pass
    if not clicked:
        raise RuntimeError("Generate control not found or not clickable")
    try:
        page.wait_for_selector("img[src], canvas, div[role='img']", timeout=timeout)
    except PWTimeout:
        raise RuntimeError("Timed out waiting for generated image/canvas after clicking Generate")
    imgs = page.locator("img[src]")
    for i in range(imgs.count()):
        el = imgs.nth(i)
        try:
            if el.is_visible():
                src = el.get_attribute("src")
                if src and len(src) > 50: return src
        except Exception:
            continue
    canvases = page.locator("canvas")
    for i in range(canvases.count()):
        c = canvases.nth(i)
        try:
            if c.is_visible():
                data_url = c.evaluate("el => el.toDataURL && el.toDataURL('image/jpeg', 0.92)")
                if data_url and len(data_url) > 200: return data_url
        except Exception:
            continue
    roles = page.locator("div[role='img']")
    for i in range(roles.count()):
        r = roles.nth(i)
        try:
            if r.is_visible():
                style = r.get_attribute("style") or ""
                m = re.search(r"url\\(([^)]+)\\)", style)
                if m:
                    url = m.group(1).strip('\"\\' ' ')
                    if url: return url
        except Exception:
            continue
    raise RuntimeError("No valid generated image found after clicking Generate")

def run_builder(count, args):
    ensure_out_dir()
    with sync_playwright() as p:
        browser_type = p.chromium
        context = browser_type.launch_persistent_context(PROFILE_DIR, headless=False, executable_path=CHROME_PATH, args=["--disable-dev-shm-usage"])
        if os.path.exists(STORAGE_STATE_FILE):
            try:
                cookies = json.loads(Path(STORAGE_STATE_FILE).read_text(encoding="utf-8")).get("cookies",[])
                if cookies: context.add_cookies(cookies)
            except Exception:
                pass
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        for i in range(1, count+1):
            filename = f"lady_{i:04d}.jpg"
            out_path = OUT_DIR / filename
            prompt_text = load_auto_prompt(args)
            ensure_prompt_filled_sync(page, prompt_text)
            src = click_generate_and_get_src_sync(page, timeout=DEFAULT_TIMEOUT_MS)
            save_image_src_sync(src, str(out_path), page=page)
            size = out_path.stat().st_size if out_path.exists() else 0
            if size < 10000:
                print(f"Warning: saved file is small ({size} bytes).")
            else:
                print(f"Saved {filename} ({size} bytes)")
            time.sleep(1.0)
        try:
            context.close()
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="Face cache builder for Kling.")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--prompt", type=str, default=None)
    args = parser.parse_args()
    try:
        run_builder(args.count, args)
    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as e:
        print("Fatal error:", e)

if __name__ == "__main__":
    main()
