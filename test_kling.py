"""test_kling.py — run: python test_kling.py"""
import os, time, requests
from pathlib import Path

try:
    import jwt
except ImportError:
    print("ERROR: pip install PyJWT"); exit(1)

def load_env(path=".env"):
    env = Path(path)
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()

ak = os.environ.get("KLING_ACCESS_KEY", "").strip()
sk = os.environ.get("KLING_SECRET_KEY", "").strip()
print(f"AK ({len(ak)} chars): {ak[:6]}...{ak[-4:]}")
print(f"SK ({len(sk)} chars): {sk[:6]}...{sk[-4:]}\n")

now = int(time.time())
token = jwt.encode({"iss": ak, "exp": now + 1800, "nbf": now - 5}, sk, algorithm="HS256")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

for base in [
    "https://api-singapore.klingai.com",
    "https://api.klingai.com",
]:
    url = f"{base}/v1/videos/image2video"
    print(f"Testing: {url}")
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        print(f"  Status : {r.status_code}")
        print(f"  Body   : {r.text[:200]}\n")
    except Exception as e:
        print(f"  Error  : {e}\n")
