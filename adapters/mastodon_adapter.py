import os, requests, json
MASTO_BASE = os.environ.get("MASTODON_BASE_URL","").rstrip("/")
MASTO_TOKEN = os.environ.get("MASTODON_ACCESS_TOKEN","").strip()
HEADERS = {"Authorization": f"Bearer {MASTO_TOKEN}","Content-Type":"application/json"}
def post_status(text, visibility="public"):
    if not MASTO_BASE or not MASTO_TOKEN:
        return {"status":"dry_run","text":text[:140]}
    url = f"{MASTO_BASE}/api/v1/statuses"
    payload = {"status": text, "visibility": visibility}
    r = requests.post(url, headers=HEADERS, json=payload, timeout=15)
    r.raise_for_status()
    return {"status":"posted","response": r.json()}
