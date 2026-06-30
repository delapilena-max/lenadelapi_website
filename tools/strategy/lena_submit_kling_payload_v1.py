"""
Lena Kling Omni Transport v1

Reads a reviewed dry-run payload JSON produced by
lena_build_kling_payload_dryrun_v1 and can POST envelope["payload"]
exactly as-is to the Kling /v1/images/omni-image endpoint.

Dry-run by default. Live mode requires BOTH explicit flags:
  --live --i-understand-this-spends-credits

This script is transport-only:
  - No prompt assembly
  - No wardrobe selection
  - No scene logic
  - No old element IDs
  - No R2 upload
  - No publish
  - No queue

Usage:
  # Validate only (no API call):
  python tools/strategy/lena_submit_kling_payload_v1.py \\
      --payload pipeline/strategy/lena/kling_payloads/2026-06-26/kling_payload_dryrun_2026-06-26_hcr_003.json

  # Live generation (spends credits):
  python tools/strategy/lena_submit_kling_payload_v1.py \\
      --payload <path> --live --i-understand-this-spends-credits
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import urllib.error
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
RESULTS_BASE = ROOT / "pipeline" / "strategy" / "lena" / "kling_results"

OMNI_ENDPOINT = "https://api.klingai.com/v1/images/omni-image"
OMNI_POLL_TMPL = OMNI_ENDPOINT + "/{task_id}"

LENA_ELEMENT_ID = "u_313006264506046"

BLOCKED_IDS = [
    "313794609092321",
    "313524913093322",
    "314409553525527",
    "314410301504207",
]
BLOCKED_TERMS = [
    "Goodtest1",
    "element_list",
    "/v1/images/generations",
    "image_reference_intensity",
    "face_reference_intensity",
]

JWT_TTL = 1800
POLL_INTERVAL = 6
POLL_TIMEOUT = 360


# ── .env loader ───────────────────────────────────────────────────────────────

def _load_env_manual(path: Path) -> None:
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        raw = raw.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = raw


def load_env() -> None:
    if not ENV_PATH.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(str(ENV_PATH), override=False)
    except ImportError:
        _load_env_manual(ENV_PATH)


# ── Credentials ───────────────────────────────────────────────────────────────

def _resolve(candidates: list[str]) -> tuple[bool, str]:
    for name in candidates:
        val = os.environ.get(name, "").strip()
        if val:
            return True, val
    return False, ""


def require_credentials() -> tuple[str, str]:
    ak_ok, ak = _resolve(["KLING_AK", "KLING_ACCESS_KEY"])
    sk_ok, sk = _resolve(["KLING_SK", "KLING_SECRET_KEY"])
    if not ak_ok or not sk_ok:
        raise SystemExit(
            "[ABORT] Missing KLING_AK/KLING_ACCESS_KEY or "
            "KLING_SK/KLING_SECRET_KEY in .env"
        )
    return ak, sk


def credential_status() -> dict:
    ak_ok, _ = _resolve(["KLING_AK", "KLING_ACCESS_KEY"])
    sk_ok, _ = _resolve(["KLING_SK", "KLING_SECRET_KEY"])
    return {"kling_ak_present": ak_ok, "kling_sk_present": sk_ok}


def credential_status_not_checked() -> dict:
    return {
        "kling_ak_present": "not_checked_dry_run_no_env_read",
        "kling_sk_present": "not_checked_dry_run_no_env_read",
    }


# ── JWT ───────────────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def build_jwt(ak: str, sk: str) -> str:
    now = int(time.time())
    payload = {"iss": ak, "exp": now + JWT_TTL, "nbf": now - 5}
    try:
        import jwt as pyjwt
        return pyjwt.encode(payload, sk, algorithm="HS256")
    except ImportError:
        pass
    header = _b64url(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    body = _b64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    signing = f"{header}.{body}".encode()
    sig = _b64url(hmac.new(sk.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _auth_headers(jwt_token: str) -> dict:
    return {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "User-Agent": "lena-content-bot-transport/1.0",
    }


def http_post(url: str, jwt_token: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers=_auth_headers(jwt_token), method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode()}") from exc


def http_get(url: str, jwt_token: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {jwt_token}"}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode()}") from exc


# ── Poll ──────────────────────────────────────────────────────────────────────

def poll_task(jwt_token: str, task_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        resp = http_get(OMNI_POLL_TMPL.format(task_id=task_id), jwt_token)
        status = resp.get("data", {}).get("task_status", "")
        print(f"  [poll] task_id={task_id}  status={status}")
        if status in ("succeed", "failed"):
            return resp
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(
        f"Task {task_id} did not complete within {POLL_TIMEOUT}s"
    )


# ── Download ──────────────────────────────────────────────────────────────────

def download_image(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "lena-content-bot-transport/1.0"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


# ── Envelope validation ───────────────────────────────────────────────────────

def validate_envelope(env: dict) -> list[str]:
    failures = []

    gate_checks = {
        "dry_run is True": env.get("dry_run") is True,
        "provider_call_enabled is False": (
            env.get("provider_call_enabled") is False
        ),
        "generation_call_performed is False": (
            env.get("generation_call_performed") is False
        ),
        "api_call_made is False": env.get("api_call_made") is False,
        "publishing_approval is not_approved": (
            env.get("publishing_approval") == "not_approved"
        ),
        "master_identity_body_present": (
            env.get("master_identity_body_present") is True
        ),
        "element_version_present": (
            env.get("element_version_present") is True
        ),
        "blocked_terms_absent": (
            env.get("blocked_terms_absent") is True
        ),
        "prompt_chars < 2500": (
            isinstance(env.get("prompt_chars"), int)
            and env["prompt_chars"] < 2500
        ),
    }
    for name, ok in gate_checks.items():
        if not ok:
            failures.append(name)

    payload = env.get("payload", {})
    if payload.get("fromElementId") != LENA_ELEMENT_ID:
        failures.append(
            f"fromElementId must be {LENA_ELEMENT_ID!r}, "
            f"got {payload.get('fromElementId')!r}"
        )

    payload_str = json.dumps(payload)
    found_blocked = [
        t for t in (BLOCKED_TERMS + BLOCKED_IDS) if t in payload_str
    ]
    if found_blocked:
        failures.append(f"blocked terms in payload: {found_blocked}")

    return failures


# ── Manifest ──────────────────────────────────────────────────────────────────

def build_manifest(
    *,
    envelope: dict,
    payload_path: Path,
    live_mode: bool,
    submit_resp: dict | None,
    poll_resp: dict | None,
    saved_paths: list[str],
    error: str | None,
) -> dict:
    payload = envelope.get("payload", {})
    task_id = (submit_resp or {}).get("data", {}).get("task_id")
    task_status = (poll_resp or {}).get("data", {}).get("task_status")
    eid = payload.get("fromElementId", "")
    prompt_text = payload.get("prompt", "")

    return {
        "source_payload_path": str(payload_path),
        "source_packet_path": envelope.get("source_packet_path"),
        "recipe_id": envelope.get("source_recipe_id"),
        "packet_id": envelope.get("source_packet_id"),
        "prompt_hash": hashlib.sha256(
            prompt_text.encode()
        ).hexdigest()[:16],
        "prompt_chars": envelope.get("prompt_chars"),
        "provider_endpoint": OMNI_ENDPOINT,
        "model": payload.get("model_name"),
        "character_id_masked": f"u_...{eid[-6:]}" if eid else None,
        "aspect_ratio": payload.get("aspect_ratio"),
        "resolution": payload.get("resolution"),
        "n": payload.get("n"),
        "live_mode": live_mode,
        "generation_call_performed": live_mode,
        "api_call_made": live_mode,
        "task_id": task_id,
        "task_status": task_status,
        "saved_image_paths": saved_paths,
        "image_count": len(saved_paths),
        "publish_status": "not_approved",
        "upload_to_r2": False,
        "instagram_enabled": False,
        "facebook_enabled": False,
        "error": error,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ── Output ────────────────────────────────────────────────────────────────────

def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8"
    )


def results_dir(date: str) -> Path:
    return RESULTS_BASE / date


def manifest_path(date: str, recipe_id: str, task_id: str | None = None) -> Path:
    if task_id:
        return results_dir(date) / f"kling_result_{date}_{recipe_id}_{task_id}.json"
    return results_dir(date) / f"kling_result_{date}_{recipe_id}.json"


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(
    envelope: dict,
    creds: dict,
    live_mode: bool,
    manifest: dict | None,
    manifest_file: Path | None,
    validation_failures: list[str],
) -> None:
    payload = envelope.get("payload", {})
    eid = payload.get("fromElementId", "")
    sep = "=" * 68
    print()
    print(sep)
    print("  LENA KLING OMNI TRANSPORT v1")
    print(sep)
    print(f"  mode                   : {'LIVE — CREDITS SPENT' if live_mode else 'DRY RUN — no API call'}")
    print(f"  endpoint               : {OMNI_ENDPOINT}")
    print(f"  model                  : {payload.get('model_name')}")
    print(f"  recipe_id              : {envelope.get('source_recipe_id')}")
    print(f"  prompt_chars           : {envelope.get('prompt_chars')}")
    print(f"  fromElementId          : u_...{eid[-6:] if eid else '?'}")
    print(f"  elementVersion present : {envelope.get('element_version_present')}")
    print(f"  image_list count       : {envelope.get('image_list_count')}")
    print(f"  negative_prompt        : {envelope.get('negative_prompt_present')}")
    print(f"  master identity        : {envelope.get('master_identity_body_present')}")
    print(f"  blocked absent         : {envelope.get('blocked_terms_absent')}")
    print()
    print(f"  KLING_AK present       : {creds.get('kling_ak_present')}")
    print(f"  KLING_SK present       : {creds.get('kling_sk_present')}")
    print()
    if validation_failures:
        print("  VALIDATION FAILURES:")
        for f in validation_failures:
            print(f"    {f}")
        print()
    else:
        print("  Payload validation     : PASSED")
        print()
    if live_mode and manifest:
        print(f"  task_id                : {manifest.get('task_id')}")
        print(f"  task_status            : {manifest.get('task_status')}")
        print(f"  images saved           : {manifest.get('image_count')}")
        for p in manifest.get("saved_image_paths", []):
            print(f"    {p}")
        if manifest.get("error"):
            print(f"  ERROR                  : {manifest['error']}")
        print()
        print(f"  manifest               : {manifest_file}")
    elif not live_mode:
        print("  Kling was NOT called. Pass --live --i-understand-this-spends-credits")
        print("  to submit exactly this payload to the Kling API.")
    print()
    print("  NO R2 upload.    NO publish.    NO queue.    NO schedule.")
    print(sep)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lena Kling Omni transport — reads a reviewed payload JSON "
        "and optionally submits it live."
    )
    parser.add_argument(
        "--payload",
        required=True,
        help="Path to a reviewed Kling dry-run payload JSON envelope.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Live flag 1 of 2. No API call without both live flags.",
    )
    parser.add_argument(
        "--i-understand-this-spends-credits",
        action="store_true",
        dest="credits_confirm",
        help="Live flag 2 of 2. Required together with --live.",
    )
    args = parser.parse_args()

    live_mode = args.live and args.credits_confirm

    payload_path = Path(args.payload)
    if not payload_path.is_file():
        raise SystemExit(f"[ABORT] Payload file not found: {payload_path}")

    with payload_path.open(encoding="utf-8") as f:
        envelope = json.load(f)

    creds = credential_status_not_checked()

    failures = validate_envelope(envelope)

    if failures:
        print_summary(
            envelope, creds, live_mode=False,
            manifest=None, manifest_file=None,
            validation_failures=failures,
        )
        raise SystemExit(
            f"[ABORT] Payload validation failed: {failures}"
        )

    recipe_id = envelope.get("source_recipe_id", "unknown")
    date = envelope.get("generated_date", "unknown")

    if not live_mode:
        if args.live and not args.credits_confirm:
            print(
                "[INFO] --live set but --i-understand-this-spends-credits missing "
                "— staying in dry-run."
            )
        elif args.credits_confirm and not args.live:
            print(
                "[INFO] --i-understand-this-spends-credits set but --live missing "
                "— staying in dry-run."
            )
        print_summary(
            envelope, creds, live_mode=False,
            manifest=None, manifest_file=None,
            validation_failures=[],
        )
        return 0

    # ── Live path ────────────────────────────────────────────────────────────
    print("[lena_submit_kling_payload_v1] Live mode. Credentials never printed.")
    load_env()
    creds = credential_status()
    ak, sk = require_credentials()
    jwt_token = build_jwt(ak, sk)
    del ak, sk

    kling_payload = envelope["payload"]
    submit_resp = None
    poll_resp = None
    saved_paths: list[str] = []
    error = None

    print(f"[lena_submit_kling_payload_v1] POST {OMNI_ENDPOINT}")

    try:
        submit_resp = http_post(OMNI_ENDPOINT, jwt_token, kling_payload)
        submit_code = submit_resp.get("code")
        task_id = submit_resp.get("data", {}).get("task_id")
        print(f"  submit_code: {submit_code}  task_id: {task_id}")

        if submit_code != 0 or not task_id:
            error = (
                f"Submission failed — code={submit_code} "
                f"message={submit_resp.get('message')}"
            )
            print(f"[ERROR] {error}")
        else:
            print(
                f"[lena_submit_kling_payload_v1] Polling "
                f"(max {POLL_TIMEOUT}s)..."
            )
            poll_resp = poll_task(jwt_token, task_id)
            task_status = poll_resp.get("data", {}).get("task_status")
            print(f"  final status: {task_status}")

            if task_status == "succeed":
                images = (
                    poll_resp.get("data", {})
                    .get("task_result", {})
                    .get("images", [])
                )
                out_dir = results_dir(date)
                suffixes = ["_a", "_b", "_c", "_d"]
                for idx, img in enumerate(images):
                    url = img.get("url", "")
                    if not url:
                        continue
                    suf = suffixes[idx] if idx < len(suffixes) else f"_{idx}"
                    if task_id:
                        dest = out_dir / f"lena_{recipe_id}_{date}_{task_id}{suf}.jpg"
                    else:
                        dest = out_dir / f"lena_{recipe_id}_{date}{suf}.jpg"
                    saved = download_image(url, dest)
                    print(f"  saved -> {saved}")
                    saved_paths.append(str(saved))
            else:
                error = f"Task ended with status: {task_status}"
                print(f"[ERROR] {error}")

    except Exception as exc:
        error = str(exc)
        print(f"[ERROR] {error}")

    mf = build_manifest(
        envelope=envelope,
        payload_path=payload_path,
        live_mode=True,
        submit_resp=submit_resp,
        poll_resp=poll_resp,
        saved_paths=saved_paths,
        error=error,
    )
    mf_path = manifest_path(date, recipe_id, mf.get("task_id"))
    save_json(mf_path, mf)
    print(f"[lena_submit_kling_payload_v1] Manifest saved: {mf_path}")

    print_summary(
        envelope, creds, live_mode=True,
        manifest=mf, manifest_file=mf_path,
        validation_failures=[],
    )

    return 0 if not error else 1


if __name__ == "__main__":
    sys.exit(main())
