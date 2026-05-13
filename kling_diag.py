import os, time, jwt, requests

def _load_env():
    if not os.path.exists(".env"):
        return
    with open(".env", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()
AK = os.environ.get("KLING_AK", "")
SK = os.environ.get("KLING_SK", "")

def token():
    return jwt.encode({"iss": AK, "exp": int(time.time())+1800, "nbf": int(time.time())-5}, SK, algorithm="HS256")

def hdrs():
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

PAYLOAD = {
    "model_name": "kling-v1",
    "prompt": "a woman smiling in a coffee shop, photorealistic",
    "n": 1,
    "aspect_ratio": "9:16"
}

for base in ["https://api.klingai.com", "https://api-singapore.klingai.com"]:
    print(f"\n--- Testing: {base} ---")
    resp = requests.post(f"{base}/v1/images/generations", headers=hdrs(), json=PAYLOAD, timeout=30)
    print(f"  HTTP: {resp.status_code}")
    print(f"  BODY: {resp.text}")
