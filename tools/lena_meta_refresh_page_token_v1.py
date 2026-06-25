"""
Lena Meta Page Token Refresher v1 — Facebook Login long-lived Page token flow.

Steps:
  STEP_A_EXCHANGE_USER_TOKEN  — accept short-lived USER token, exchange for long-lived
  STEP_B_FETCH_PAGES          — call /me/accounts to list pages + IG linkage
  STEP_C_SELECT_LENA_PAGE     — verify page name, ID, IG ID, IG username
  STEP_D_WRITE_ENV            — backup .env, write META_PAGE_ACCESS_TOKEN
  STEP_E_VALIDATE_PAGE_TOKEN  — debug_token confirms PAGE type, valid, scopes

No token values are printed or logged at any point.
"""
from __future__ import annotations
import getpass, json, os, re, shutil, subprocess, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[1]
ENV_PATH  = ROOT / ".env"
PAGE_ID   = "1267219163131062"
PAGE_NAME = "Lena Delapi"
IG_ID     = "17841409711154047"
IG_USER   = "lenadelapineapple.official"
GRAPH_VER = "v25.0"
BASE      = f"https://graph.facebook.com/{GRAPH_VER}"
REQUIRED_SCOPES = {
    "pages_manage_posts", "pages_read_engagement",
    "instagram_basic", "instagram_content_publish",
}

SA = "STEP_A_EXCHANGE_USER_TOKEN"
SB = "STEP_B_FETCH_PAGES"
SC = "STEP_C_SELECT_LENA_PAGE"
SD = "STEP_D_WRITE_ENV"
SE = "STEP_E_VALIDATE_PAGE_TOKEN"


# ── helpers ──────────────────────────────────────────────────────────────────

def load_env_raw(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def get_env_val(raw: str, *keys: str) -> str:
    for k in keys:
        m = re.search(rf'^{re.escape(k)}\s*=\s*(.+)$', raw, re.MULTILINE)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def set_env_key(raw: str, key: str, value: str) -> str:
    pat = re.compile(rf'^({re.escape(key)}\s*=\s*)(.*)$', re.MULTILINE)
    if pat.search(raw):
        return pat.sub(rf'\g<1>{value}', raw)
    sep = "\n" if raw.endswith("\n") else "\n\n"
    return raw + f"{sep}{key}={value}\n"


def http_get(path: str, params: dict) -> dict:
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url), timeout=20
        ) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            return {"error": {"code": exc.code, "message": str(exc)}}
    except urllib.error.URLError as exc:
        return {"error": {"code": 0, "message": f"network: {exc.reason}"}}
    except Exception as exc:
        return {"error": {"code": 0, "message": str(exc)}}


def classify_error(resp: dict) -> str:
    """Map a Graph API error dict to one of the allowed sanitized reasons."""
    err  = resp.get("error", {})
    code = int(err.get("code", 0))
    sub  = int(err.get("error_subcode", 0) or 0)
    msg  = err.get("message", "").lower()

    if code == 190:
        if sub in (463, 467, 492):
            return "token expired"
        if sub == 460:
            return "app mismatch"
        # generic OAuthException
        if "expired" in msg:
            return "token expired"
        if "app" in msg or "client" in msg:
            return "app mismatch"
        return "bad token type"
    if code == 200 or "permission" in msg or "scope" in msg:
        return "missing scope"
    if code == 0 or "network" in msg or "connect" in msg or "timeout" in msg:
        return "network/API error"
    return "network/API error"


def fmt_ts(ts) -> str:
    if not ts or ts == 0:
        return "never expires"
    try:
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def step_pass(label: str, detail: str = "") -> None:
    print(f"  {label}: PASS" + (f"  ({detail})" if detail else ""))


def step_fail(label: str, reason: str) -> int:
    print(f"  {label}: FAIL — {reason}")
    return 1


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    raw     = load_env_raw(ENV_PATH)
    app_id  = get_env_val(raw, "META_APP_ID", "FACEBOOK_APP_ID")
    app_sec = get_env_val(raw, "META_APP_SECRET", "FACEBOOK_APP_SECRET")

    print("=" * 64)
    print("  LENA META PAGE TOKEN REFRESHER v1")
    print("=" * 64)
    print(f"  META_APP_ID     : {'PRESENT' if app_id  else 'MISSING'}")
    print(f"  META_APP_SECRET : {'PRESENT' if app_sec else 'MISSING'}")
    print(f"  Target page ID  : {PAGE_ID}  ({PAGE_NAME})")
    print(f"  Target IG ID    : {IG_ID}  (@{IG_USER})")
    print()

    if not app_id or not app_sec:
        print("[ABORT] META_APP_ID or META_APP_SECRET missing from .env")
        return 1

    # Accept token via hidden prompt — value never echoed or printed
    try:
        short_token = getpass.getpass(
            "Paste short-lived Facebook USER token (hidden, not echoed): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[ABORT] No token entered.")
        return 1

    if not short_token:
        print("[ABORT] No token entered.")
        return 1
    print(f"  Token received  : length={len(short_token)} chars (value hidden)")
    print()

    # ── STEP A — exchange for long-lived user token ───────────────────────────
    print(f"  Running {SA} ...")
    resp = http_get("oauth/access_token", {
        "grant_type":        "fb_exchange_token",
        "client_id":         app_id,
        "client_secret":     app_sec,
        "fb_exchange_token": short_token,
    })
    del short_token

    if "error" in resp:
        return step_fail(SA, classify_error(resp))

    ll_token = resp.get("access_token", "")
    if not ll_token:
        return step_fail(SA, "bad token type")

    step_pass(SA, f"token_type={resp.get('token_type')}  "
                  f"expires_in={resp.get('expires_in', 'unknown')}s")
    print()

    # ── STEP B — fetch pages via /me/accounts ─────────────────────────────────
    print(f"  Running {SB} ...")
    accts = http_get("me/accounts", {
        "access_token": ll_token,
        "fields": (
            "id,name,access_token,"
            "instagram_business_account{id,username}"
        ),
        "limit": "50",
    })

    if "error" in accts:
        del ll_token
        return step_fail(SB, classify_error(accts))

    pages = accts.get("data", [])
    step_pass(SB, f"pages_returned={len(pages)}")
    for pg in pages:
        iba = pg.get("instagram_business_account") or {}
        print(f"    id={pg.get('id')}  name={pg.get('name')}  "
              f"ig={iba.get('id', '-')}  @{iba.get('username', '-')}")
    print()

    # ── STEP C — select and verify Lena page ─────────────────────────────────
    print(f"  Running {SC} ...")
    target = next(
        (p for p in pages if str(p.get("id", "")) == PAGE_ID), None
    )
    if not target:
        del ll_token
        return step_fail(SC, "page not found")

    iba      = target.get("instagram_business_account") or {}
    ig_found = iba.get("id", "")
    ig_uname = iba.get("username", "")
    pg_name  = target.get("name", "")
    pg_tok   = target.get("access_token", "")

    checks = {
        "page_id":   (str(target.get("id", "")) == PAGE_ID,   "page not found"),
        "page_name": (pg_name == PAGE_NAME,                    "page not found"),
        "ig_id":     (ig_found == IG_ID,                       "IG mismatch"),
        "ig_user":   (ig_uname == IG_USER,                     "IG mismatch"),
        "pg_token":  (bool(pg_tok),                            "bad token type"),
    }

    failed = [(label, reason) for label, (ok, reason) in checks.items() if not ok]

    print(f"    page_id   : {target.get('id')}  "
          f"{'OK' if checks['page_id'][0]   else 'MISMATCH'}")
    print(f"    page_name : {pg_name}  "
          f"{'OK' if checks['page_name'][0] else f'MISMATCH — expected {PAGE_NAME}'}")
    print(f"    ig_id     : {ig_found}  "
          f"{'OK' if checks['ig_id'][0]     else f'MISMATCH — expected {IG_ID}'}")
    print(f"    ig_user   : @{ig_uname}  "
          f"{'OK' if checks['ig_user'][0]   else f'MISMATCH — expected {IG_USER}'}")
    print(f"    page_token: {'obtained (hidden)'  if pg_tok else 'MISSING'}  "
          f"length={len(pg_tok)}")

    if failed:
        del ll_token, pg_tok
        first_reason = failed[0][1]
        return step_fail(SC, first_reason)

    step_pass(SC, "all identity checks OK")
    print()

    # ── STEP D — backup + write .env ─────────────────────────────────────────
    print(f"  Running {SD} ...")
    del ll_token  # no longer needed

    bak_path = str(ENV_PATH) + f".bak_refresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        subprocess.run(["attrib", "-R", str(ENV_PATH)], check=False,
                       capture_output=True)
    except Exception:
        pass

    try:
        shutil.copy2(str(ENV_PATH), bak_path)
        print(f"    backup created : {bak_path}")
    except Exception as exc:
        print(f"    backup FAILED  : {exc}")
        del pg_tok
        return step_fail(SD, "env write blocked")

    try:
        updated = set_env_key(raw, "META_PAGE_ACCESS_TOKEN", pg_tok)
        ENV_PATH.write_text(updated, encoding="utf-8")
        del pg_tok
    except PermissionError:
        return step_fail(SD, "env write blocked")
    except Exception:
        return step_fail(SD, "env write blocked")

    step_pass(SD, "META_PAGE_ACCESS_TOKEN written")
    print()

    # ── STEP E — validate new token from .env ────────────────────────────────
    print(f"  Running {SE} ...")
    raw2    = load_env_raw(ENV_PATH)
    new_tok = get_env_val(raw2, "META_PAGE_ACCESS_TOKEN")
    if not new_tok:
        return step_fail(SE, "bad token type")

    app_token = f"{app_id}|{app_sec}"
    dbg = http_get("debug_token", {
        "input_token":  new_tok,
        "access_token": app_token,
    })
    del new_tok

    if "error" in dbg:
        return step_fail(SE, classify_error(dbg))

    d        = dbg.get("data", {})
    ttype    = d.get("type")
    is_valid = d.get("is_valid")
    exp      = d.get("expires_at")
    scopes   = set(d.get("scopes", []))
    missing  = REQUIRED_SCOPES - scopes

    print(f"    token_type : {ttype}")
    print(f"    is_valid   : {is_valid}")
    print(f"    expires_at : {fmt_ts(exp)}")
    print(f"    application: {d.get('application')}")
    print(f"    scopes     : {', '.join(sorted(scopes))}")
    if missing:
        print(f"    MISSING    : {sorted(missing)}")

    never = (exp == 0 or exp is None)

    if ttype != "PAGE":
        return step_fail(SE, "bad token type")
    if not is_valid:
        return step_fail(SE, "token expired")
    if missing:
        return step_fail(SE, "missing scope")

    step_pass(SE, f"PAGE token  valid={is_valid}  expires={fmt_ts(exp)}")
    print()

    print("=" * 64)
    if ttype == "PAGE" and never and is_valid and not missing:
        print("  RESULT: SAFE — Page token, never expires, all scopes present.")
    elif ttype == "PAGE" and is_valid:
        print(f"  RESULT: EXPIRING — expires {fmt_ts(exp)}.")
    print()
    print("  Next step: share RESULT with Nicolas for publish approval.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
