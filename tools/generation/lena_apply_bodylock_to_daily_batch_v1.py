"""
lena_apply_bodylock_to_daily_batch_v1.py

Standalone post-processor for Lena's daily Kling Omni batch JSON.

It applies the validated BodyLock setup to an existing daily batch:
- element_list / kling_element_id: KLING_LENA_ELEMENT_ASSET_ID (from .env)
- image_list / kling_image_list: LENA_KLING_BODY_ANCHOR_URL
- n / kling_n: LENA_KLING_BODYLOCK_N, default 1

This script does NOT call Kling, publish, schedule, upload generated outputs,
modify the Kling element, or create a new element.

Usage:
  python tools/generation/lena_apply_bodylock_to_daily_batch_v1.py --date 2026-06-19
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, MutableMapping, Tuple


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

BATCH_BASE = ROOT / "pipeline" / "workorders" / "lena" / "photo_batches"
DRYRUN_BASE = ROOT / "pipeline" / "workorders" / "lena" / "bodylock_daily_default_tests"

OMNI_MODEL = "kling-v3-omni"
ASPECT_RATIO = "9:16"
RESOLUTION = "2k"
_RETIRED_ELEMENT_ID = 313524913093322
ELEMENT_ID: int = 0  # loaded from env at startup — see main()
DEFAULT_BODYLOCK_N = 1
NON_BODYLOCK_DEFAULT_N = 2

UNSUPPORTED_PARAMS = {
    "element_strength",
    "reference_weight",
    "seed",
    "body_lock_strength",
    "lora_id",
}

LIKELY_SLOT_KEYS = (
    "photo_workorders",
    "photos",
    "photo_slots",
    "slots",
    "workorders",
    "items",
)


def load_env_file(path: Path) -> None:
    """Load .env values without overwriting values already present in the shell."""
    if not path.is_file():
        return

    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path, override=False)
        return
    except ImportError:
        pass

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


def parse_positive_int(raw_value: str | None, default: int) -> int:
    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value.strip())
    except ValueError:
        return default

    return value if value > 0 else default


def get_bodylock_config() -> Dict[str, Any]:
    anchor_url = os.environ.get("LENA_KLING_BODY_ANCHOR_URL", "").strip()
    enabled_raw = os.environ.get("LENA_KLING_BODYLOCK_ENABLED", "").strip()
    n_value = parse_positive_int(os.environ.get("LENA_KLING_BODYLOCK_N"), DEFAULT_BODYLOCK_N)

    if enabled_raw == "0":
        enabled = False
    elif enabled_raw == "1":
        enabled = bool(anchor_url)
    else:
        enabled = bool(anchor_url)

    return {
        "enabled": enabled,
        "anchor_url": anchor_url,
        "n": n_value,
        "enabled_raw": enabled_raw,
    }


def date_compact(date_label: str) -> str:
    return date_label.replace("-", "")


def locate_batch_file(date_label: str, explicit_path: str | None = None) -> Path:
    if explicit_path:
        path = Path(explicit_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"Batch file not found: {path}")
        return path

    folder = BATCH_BASE / date_label
    expected = folder / f"lena_kling_omni_daily_{date_compact(date_label)}.json"

    if expected.is_file():
        return expected

    candidates = sorted(folder.glob("lena_kling_omni_daily_*.json"))
    if len(candidates) == 1:
        return candidates[0]

    if not folder.is_dir():
        raise FileNotFoundError(f"Batch folder not found: {folder}")

    raise FileNotFoundError(
        f"Could not uniquely locate batch JSON in {folder}. "
        f"Expected {expected.name}; candidates={len(candidates)}"
    )


def is_slot_like_dict(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    has_prompt = isinstance(value.get("prompt"), str) and bool(value["prompt"].strip())
    has_identity = any(key in value for key in ("slot_type", "photo_id", "title", "content_pillar"))

    return has_prompt and has_identity


def find_photo_slots(batch: MutableMapping[str, Any]) -> Tuple[str, List[MutableMapping[str, Any]]]:
    """Find the list of photo slot dicts in the batch JSON."""
    for key in LIKELY_SLOT_KEYS:
        value = batch.get(key)
        if isinstance(value, list) and value and all(is_slot_like_dict(item) for item in value):
            return key, value  # type: ignore[return-value]

    for key, value in batch.items():
        if isinstance(value, list) and value and all(is_slot_like_dict(item) for item in value):
            return key, value  # type: ignore[return-value]

    raise KeyError(
        "Could not find photo slots in batch JSON. Expected a list containing dicts "
        "with at least prompt plus slot_type/photo_id/title/content_pillar."
    )


def slot_label(slot: MutableMapping[str, Any], index: int) -> str:
    raw = " ".join(
        str(slot.get(key, ""))
        for key in ("slot_type", "photo_id", "title", "content_pillar")
    ).lower()

    if "morning" in raw:
        return "morning"
    if "afternoon" in raw:
        return "afternoon"
    if "evening" in raw:
        return "evening"

    fallback = str(slot.get("slot_type") or slot.get("photo_id") or f"slot_{index + 1}")
    fallback = re.sub(r"[^a-zA-Z0-9_]+", "_", fallback).strip("_").lower()

    return fallback or f"slot_{index + 1}"


def apply_bodylock_to_slot(slot: MutableMapping[str, Any], bodylock: Dict[str, Any]) -> None:
    slot["kling_element_id"] = ELEMENT_ID
    slot["bodylock_enabled"] = bool(bodylock["enabled"])

    if bodylock["enabled"]:
        slot["kling_image_list"] = [{"image": bodylock["anchor_url"]}]
        slot["kling_n"] = int(bodylock["n"])
    else:
        slot["kling_image_list"] = []
        slot.setdefault("kling_n", NON_BODYLOCK_DEFAULT_N)


def build_api_payload(slot: MutableMapping[str, Any], bodylock: Dict[str, Any]) -> Dict[str, Any]:
    n_value = int(slot.get("kling_n") or (bodylock["n"] if bodylock["enabled"] else NON_BODYLOCK_DEFAULT_N))

    payload: Dict[str, Any] = {
        "model_name": OMNI_MODEL,
        "prompt": str(slot["prompt"]),
        "element_list": [{"element_id": ELEMENT_ID}],
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "n": n_value,
    }

    image_list = slot.get("kling_image_list")
    if image_list:
        payload["image_list"] = image_list

    return payload


def validate_payload(label: str, payload: Dict[str, Any], bodylock: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    missing = [key for key in ("model_name", "prompt", "element_list", "aspect_ratio", "resolution", "n") if key not in payload]
    for key in missing:
        errors.append(f"{label}: missing {key}")

    bad = sorted(UNSUPPORTED_PARAMS.intersection(payload.keys()))
    if bad:
        errors.append(f"{label}: unsupported params present: {bad}")

    element_list = payload.get("element_list")
    if not isinstance(element_list, list) or len(element_list) != 1:
        errors.append(f"{label}: element_list must contain exactly one entry")
    elif element_list[0].get("element_id") != ELEMENT_ID:
        errors.append(
            f"{label}: element_id does not match active Lena element" " (retired element rejected)"
        )

    if bodylock["enabled"]:
        image_list = payload.get("image_list")
        if not isinstance(image_list, list) or len(image_list) != 1:
            errors.append(f"{label}: BodyLock enabled but image_list missing or invalid")
        else:
            url = str(image_list[0].get("image", "")).strip()
            if not url.startswith("https://"):
                errors.append(f"{label}: image_list URL must start with https://")
            if "PLACEHOLDER" in url:
                errors.append(f"{label}: image_list URL contains PLACEHOLDER")

        if payload.get("n") != int(bodylock["n"]):
            errors.append(f"{label}: n must be {bodylock['n']} when BodyLock is enabled")

        if int(bodylock["n"]) != DEFAULT_BODYLOCK_N:
            errors.append(f"{label}: stabilization mode expects n={DEFAULT_BODYLOCK_N}, got {bodylock['n']}")

    return errors


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_dryrun_exports(
    date_label: str,
    slots: List[MutableMapping[str, Any]],
    bodylock: Dict[str, Any],
    batch_path: Path,
    backup_path: Path | None,
) -> Tuple[List[Path], Path]:
    out_dir = DRYRUN_BASE / date_label
    out_dir.mkdir(parents=True, exist_ok=True)

    saved_payloads: List[Path] = []
    validation_errors: List[str] = []

    seen_labels = set()
    for index, slot in enumerate(slots):
        label = slot_label(slot, index)
        if label in seen_labels:
            label = f"{label}_{index + 1}"
        seen_labels.add(label)

        payload = build_api_payload(slot, bodylock)
        validation_errors.extend(validate_payload(label, payload, bodylock))

        payload_path = out_dir / f"dryrun_{label}_payload.json"
        save_json(payload_path, payload)
        saved_payloads.append(payload_path)

    if validation_errors:
        for error in validation_errors:
            print(f"VALIDATION ERROR: {error}")
        raise SystemExit(1)

    lines = [
        f"# BodyLock Daily Default Dry-Run — {date_label}",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Batch",
        "",
        f"- Original batch: `{batch_path}`",
        f"- Backup: `{backup_path}`" if backup_path else "- Backup: not created because BodyLock is disabled",
        "",
        "## BodyLock",
        "",
        f"- BodyLock enabled: {'YES' if bodylock['enabled'] else 'NO'}",
        f"- Body anchor URL present: {'YES' if bodylock['anchor_url'] else 'NO'}",
        f"- image_list attached: {'YES' if bodylock['enabled'] else 'NO'}",
        "- element_id: present (not printed)",
        f"- n: {bodylock['n'] if bodylock['enabled'] else 'unchanged/non-BodyLock'}",
        "",
        "## Payload files",
        "",
    ]

    lines.extend(f"- `{path.name}`" for path in saved_payloads)

    lines.extend(
        [
            "",
            "## Validation",
            "",
            "- Every payload has `element_list`.",
            "- BodyLock-enabled payloads have `image_list`.",
            "- No unsupported Kling parameters are present.",
            "- No live generation performed.",
            "",
            "## Safety",
            "",
            "- No Kling API call performed.",
            "- No publishing performed.",
            "- No scheduling performed.",
            "- No generated outputs uploaded to R2.",
            f"- Element {ELEMENT_ID} not modified.",
            "- No new element created.",
        ]
    )

    summary_path = out_dir / "dryrun_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return saved_payloads, summary_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply BodyLock fields to an existing Lena daily batch JSON and export dry-run payloads."
    )
    parser.add_argument("--date", required=True, help="Batch date, format YYYY-MM-DD.")
    parser.add_argument("--batch-path", default=None, help="Optional explicit path to batch JSON.")
    args = parser.parse_args()

    load_env_file(ENV_PATH)
    bodylock = get_bodylock_config()

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

    if not bodylock["enabled"] or not bodylock["anchor_url"]:
        raise SystemExit(
            "[ABORT] BodyLock requires LENA_KLING_BODY_ANCHOR_URL in .env."
            " Element-only generation is blocked."
        )

    batch_path = locate_batch_file(args.date, args.batch_path)
    batch = json.loads(batch_path.read_text(encoding="utf-8"))

    if not isinstance(batch, dict):
        raise TypeError(f"Batch JSON root must be an object: {batch_path}")

    slot_key, slots = find_photo_slots(batch)

    backup_path: Path | None = None

    print(f"Original batch path    : {batch_path}")
    print(f"Slot list key          : {slot_key}")
    print(f"Slot count             : {len(slots)}")
    print(f"BodyLock enabled       : {'YES' if bodylock['enabled'] else 'NO'}")
    print(f"Body anchor URL present: {'YES' if bodylock['anchor_url'] else 'NO'}")
    print(f"image_list attached    : {'YES' if bodylock['enabled'] else 'NO'}")
    print("element_id             : present (valid, not retired)")
    print(f"n                      : {bodylock['n'] if bodylock['enabled'] else 'unchanged/non-BodyLock'}")
    print()

    if bodylock["enabled"]:
        backup_path = batch_path.with_name(batch_path.name + ".bak_bodylock_apply_20260619")
        if not backup_path.exists():
            shutil.copy2(batch_path, backup_path)

        for slot in slots:
            apply_bodylock_to_slot(slot, bodylock)

        batch.setdefault("bodylock", {})
        batch["bodylock"].update(
            {
                "enabled": True,
                "anchor_url": bodylock["anchor_url"],
                "n": bodylock["n"],
                "element_id": ELEMENT_ID,
                "applied_by": "lena_apply_bodylock_to_daily_batch_v1.py",
                "applied_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

        batch_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        print("BodyLock disabled. Batch was not modified; dry-run summary will still be written.")

    payload_paths, summary_path = write_dryrun_exports(
        date_label=args.date,
        slots=slots,
        bodylock=bodylock,
        batch_path=batch_path,
        backup_path=backup_path,
    )

    print(f"Backup path            : {backup_path if backup_path else 'not created'}")
    print(f"Modified batch path    : {batch_path if bodylock['enabled'] else 'not modified'}")
    print()
    print("Dry-run payload paths:")
    for path in payload_paths:
        print(f"  {path}")
    print(f"  {summary_path}")
    print()
    print("DRY-RUN COMPLETE — no live generation performed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
