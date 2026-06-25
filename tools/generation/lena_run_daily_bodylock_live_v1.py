"""
Standalone live runner for Lena daily BodyLock Kling v3 Omni Image generation.

No publishing, no scheduling, no R2 upload of generated outputs, no element modification.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
BATCH_BASE = ROOT / "pipeline" / "workorders" / "lena" / "photo_batches"
LIVE_BASE = ROOT / "pipeline" / "workorders" / "lena" / "bodylock_daily_live_runs"
ASSET_BASE = ROOT / "pipeline" / "content_library" / "lena" / "assets"

OMNI_ENDPOINT = os.environ.get("KLING_OMNI_ENDPOINT", "https://api.klingai.com/v1/images/omni-image").rstrip("/")
OMNI_MODEL = "kling-v3-omni"
ASPECT_RATIO = "9:16"
RESOLUTION = "2k"
_RETIRED_ELEMENT_ID = 313524913093322
ELEMENT_ID: int = 0  # loaded from env at startup — see main()
REQUIRED_N = 1
POLL_INTERVAL_SECONDS = 5
POLL_MAX_SECONDS = 420
JWT_TTL_SECONDS = 1800

UNSUPPORTED_PARAMS = {"element_strength", "reference_weight", "seed", "body_lock_strength", "lora_id"}
SLOT_KEYS = ("photo_workorders", "photos", "photo_slots", "slots", "workorders", "items")


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_jwt(access_key: str, secret_key: str) -> str:
    now = int(time.time())
    payload = {"iss": access_key, "exp": now + JWT_TTL_SECONDS, "nbf": now - 5}
    try:
        import jwt  # type: ignore
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        return token.decode("utf-8") if isinstance(token, bytes) else token
    except ImportError:
        pass
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = b64url(hmac.new(secret_key.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def http_json(method: str, url: str, headers: Dict[str, str], body: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def compact_date(date_label: str) -> str:
    return date_label.replace("-", "")


def find_batch(date_label: str, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    expected = BATCH_BASE / date_label / f"lena_kling_omni_daily_{compact_date(date_label)}.json"
    if expected.is_file():
        return expected
    candidates = sorted((BATCH_BASE / date_label).glob("lena_kling_omni_daily_*.json"))
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(f"Could not find unique batch JSON for {date_label}")


def is_slot(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("prompt"), str)
        and bool(value.get("prompt", "").strip())
        and any(k in value for k in ("slot_type", "photo_id", "title", "content_pillar"))
    )


def find_slots(batch: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    for key in SLOT_KEYS:
        value = batch.get(key)
        if isinstance(value, list) and value and all(is_slot(v) for v in value):
            return key, value
    for key, value in batch.items():
        if isinstance(value, list) and value and all(is_slot(v) for v in value):
            return key, value
    raise KeyError("No slot list found in batch JSON")


def slot_label(slot: Dict[str, Any], index: int) -> str:
    raw = " ".join(str(slot.get(k, "")) for k in ("slot_type", "photo_id", "title", "content_pillar")).lower()
    for name in ("morning", "afternoon", "evening"):
        if name in raw:
            return name
    fallback = str(slot.get("slot_type") or slot.get("photo_id") or f"slot_{index + 1}")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", fallback).strip("_").lower()


def select_slots(slots: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    labeled = [(slot_label(slot, idx), slot) for idx, slot in enumerate(slots)]
    selected: List[Tuple[str, Dict[str, Any]]] = []
    for name in ("morning", "afternoon", "evening"):
        matches = [(label, slot) for label, slot in labeled if label == name]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {name} slot, found {len(matches)}")
        selected.append(matches[0])
    return selected


def build_payload(label: str, slot: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "model_name": OMNI_MODEL,
        "prompt": str(slot["prompt"]),
        "element_list": [{"element_id": ELEMENT_ID}],
        "image_list": slot.get("kling_image_list"),
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "n": slot.get("kling_n"),
    }
    validate_payload(label, payload)
    return payload


def validate_payload(label: str, payload: Dict[str, Any]) -> None:
    errors: List[str] = []
    bad = sorted(UNSUPPORTED_PARAMS.intersection(payload.keys()))
    if bad:
        errors.append(f"{label}: unsupported params: {bad}")
    if payload.get("element_list") != [{"element_id": ELEMENT_ID}]:
        errors.append(
            f"{label}: element_list must use active Lena element" " (retired element rejected)"
        )
    image_list = payload.get("image_list")
    if not isinstance(image_list, list) or len(image_list) != 1:
        errors.append(f"{label}: image_list missing or invalid")
    else:
        url = str(image_list[0].get("image", "")).strip()
        if not url.startswith("https://"):
            errors.append(f"{label}: image URL must start with https://")
        if "PLACEHOLDER" in url:
            errors.append(f"{label}: image URL contains PLACEHOLDER")
    if payload.get("n") != REQUIRED_N:
        errors.append(f"{label}: n must be {REQUIRED_N}, got {payload.get('n')!r}")
    if not isinstance(payload.get("prompt"), str) or not payload["prompt"].strip():
        errors.append(f"{label}: prompt missing")
    if errors:
        for err in errors:
            print(f"VALIDATION ERROR: {err}")
        raise SystemExit(1)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")


def poll_task(token: str, task_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + POLL_MAX_SECONDS
    while time.time() < deadline:
        resp = http_json("GET", f"{OMNI_ENDPOINT}/{task_id}", headers)
        status = resp.get("data", {}).get("task_status", "")
        print(f"  [poll] {task_id} status={status}")
        if status in {"succeed", "failed"}:
            return resp
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Task {task_id} timed out after {POLL_MAX_SECONDS}s")


def image_urls_from(resp: Dict[str, Any]) -> List[str]:
    images = resp.get("data", {}).get("task_result", {}).get("images", [])
    if not isinstance(images, list):
        return []
    return [str(img.get("url", "")).strip() for img in images if isinstance(img, dict) and img.get("url")]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "lena-daily-bodylock/1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())


def run_slot(label: str, payload: Dict[str, Any], token: str, live_dir: Path, asset_dir: Path) -> Dict[str, Any]:
    print(f"\\n[{label}] BodyLock request validation: PASSED")
    print(f"[{label}] element_list: present (element ID not printed)")
    print(f"[{label}] image_list  : {payload['image_list']}")
    print(f"[{label}] n           : {payload['n']}")
    save_json(live_dir / f"{label}_request_payload.json", payload)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    submit = http_json("POST", OMNI_ENDPOINT, headers, payload)
    save_json(live_dir / f"{label}_submit_response.json", submit)
    code = submit.get("code")
    task_id = submit.get("data", {}).get("task_id")
    print(f"[{label}] submit_code={code} task_id={task_id}")
    if code != 0 or not task_id:
        raise RuntimeError(f"[{label}] Submission failed: code={code}; message={submit.get('message')}")
    poll = poll_task(token, str(task_id))
    save_json(live_dir / f"{label}_poll_response.json", poll)
    status = poll.get("data", {}).get("task_status")
    urls = image_urls_from(poll)
    paths: List[str] = []
    for idx, url in enumerate(urls):
        suffix = chr(ord("a") + idx)
        path = asset_dir / f"bodylock_daily_{label}_{suffix}.jpg"
        download(url, path)
        paths.append(str(path))
        print(f"[{label}] saved -> {path}")
    return {"label": label, "task_id": str(task_id), "status": str(status), "image_urls": urls, "image_paths": paths, "n": payload["n"]}


def write_summary(date_label: str, results: List[Dict[str, Any]], live_dir: Path) -> None:
    lines = [
        f"# Lena Daily BodyLock Live Run — {date_label}",
        "",
        f"Completed: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "| Slot | Task ID | Status | Image count | n | image_list |",
        "|---|---|---|---:|---:|---|",
    ]
    for r in results:
        lines.append(f"| {r['label']} | {r['task_id']} | {r['status']} | {len(r['image_urls'])} | {r['n']} | YES |")
    lines += ["", "## Output images", ""]
    for r in results:
        lines.append(f"### {r['label']}")
        for path, url in zip(r["image_paths"], r["image_urls"]):
            lines.append(f"- Local: `{path}`")
            lines.append(f"  URL: {url}")
        lines.append("")
    lines += [
        "## Safety confirmation",
        "",
        "- STOPPED — no publishing performed.",
        "- No scheduling performed.",
        "- No R2 upload of generated outputs.",
        "- Element (ID not printed) was not modified.",
        "- No new element was created.",
        "- No unsupported params were present; validated before submit.",
    ]
    (live_dir / "live_summary.md").write_text("\\n".join(lines) + "\\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--batch-path", default=None)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--confirm-daily-three-photo-kling-omni-live", action="store_true")
    args = parser.parse_args()

    if args.preflight_only and args.execute_live:
        raise SystemExit("Use either --preflight-only or --execute-live, not both.")

    load_env(ENV_PATH)

    global ELEMENT_ID
    _raw_eid = os.environ.get("KLING_LENA_ELEMENT_ASSET_ID", "").strip()
    if not _raw_eid:
        raise SystemExit(
            "[ABORT] KLING_LENA_ELEMENT_ASSET_ID missing from environment."
        )
    try:
        ELEMENT_ID = int(_raw_eid)
    except ValueError:
        raise SystemExit(
            "[ABORT] KLING_LENA_ELEMENT_ASSET_ID is not a valid integer."
        )
    if ELEMENT_ID == _RETIRED_ELEMENT_ID:
        raise SystemExit(
            "[ABORT] KLING_LENA_ELEMENT_ASSET_ID matches retired element;"
            " update .env to active element."
        )
    print("  element_id   : present (valid, not retired)")

    batch_path = find_batch(args.date, args.batch_path)
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(batch, dict):
        raise TypeError("Batch JSON root must be an object")

    slot_key, slots = find_slots(batch)
    selected = select_slots(slots)
    payloads = [(label, build_payload(label, slot)) for label, slot in selected]

    live_dir = LIVE_BASE / args.date
    asset_dir = ASSET_BASE / args.date / "bodylock_daily_live"
    live_dir.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    print(f"Batch path       : {batch_path}")
    print(f"Slot list key    : {slot_key}")
    print("Selected slots   : " + ", ".join(label for label, _payload in payloads))
    print(f"Output directory : {live_dir}")
    print(f"Asset directory  : {asset_dir}")
    print("Validation       : PASSED for all 3 BodyLock payloads")

    if args.preflight_only or not args.execute_live:
        for label, payload in payloads:
            print(f"\\nPAYLOAD — {label}")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("\\nPREFLIGHT COMPLETE — no live generation performed")
        return 0

    if not args.confirm_daily_three_photo_kling_omni_live:
        raise SystemExit("[ABORT] --confirm-daily-three-photo-kling-omni-live is required.")

    ak = (os.environ.get("KLING_AK", "") or os.environ.get("KLING_ACCESS_KEY", "")).strip()
    sk = (os.environ.get("KLING_SK", "") or os.environ.get("KLING_SECRET_KEY", "")).strip()
    if not ak or not sk:
        raise SystemExit("[ABORT] Kling credentials missing from environment.")

    print("\\nBuilding Kling JWT. Credentials are not logged.")
    token = build_jwt(ak, sk)
    del ak, sk

    results = [run_slot(label, payload, token, live_dir, asset_dir) for label, payload in payloads]
    write_summary(args.date, results, live_dir)

    print("\\n" + "=" * 72)
    print("LENA DAILY BODYLOCK LIVE RUN COMPLETE")
    print("=" * 72)
    for r in results:
        print(f"{r['label']} task_id: {r['task_id']} status={r['status']}")
        for path in r["image_paths"]:
            print(f"  {path}")
    print("Every request included image_list: YES")
    print("Every request used n=1: YES")
    print("Unsupported params present: none; validated")
    print("STOPPED — no publishing performed")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
