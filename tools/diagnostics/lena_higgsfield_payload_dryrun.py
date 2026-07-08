from __future__ import annotations

# Local, no-call diagnostic for a hypothetical Higgsfield generation of a real,
# already-existing Lena workorder slot.
#
# Prints a Higgsfield command/contract summary (model placeholder, prompt
# length, intended CLI shape, expected output/manifest paths, identity-
# strategy placeholder, risk flags) WITHOUT executing anything. This exists
# because Higgsfield has no documented native dry-run mode (see the
# 2026-07-08 Higgsfield docs/CLI/MCP verification audit and
# tools/LEGACY_PROVIDER_SURFACES.md's "Provider transition in progress:
# Higgsfield" section) -- every field below is either read directly from a
# real slot on disk, or explicitly marked as an unconfirmed placeholder.
#
# HARD CONSTRAINTS (enforced by construction -- this script cannot violate
# them):
#   - No subprocess, no network (no requests/urllib/http import anywhere).
#   - No Higgsfield SDK/CLI import or call of any kind.
#   - No .env read (no pipeline.env_loader import).
#   - No executor import (no pipeline.kling_apilena_api_executor import).
#   - No file writes of any kind -- stdout-only. No directories created.
#   - Never prints the full image_prompt or negative_prompt text -- lengths
#     only, per explicit instruction not to leak full prompt content into a
#     diagnostic transcript.
#
# Run:
#   python tools/diagnostics/lena_higgsfield_payload_dryrun.py --date 2026-07-07 --slot-id 2026-07-07-03-photo

import argparse
import json
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
WORKORDER_ROOT = ROOT / "pipeline" / "kling_workorders"

# Placeholder only -- not verified against any real Higgsfield model list.
# See the 2026-07-08 docs verification: Higgsfield exposes 30+ models
# (Soul, Cinema Studio, Flux, Seedream, Kling, Veo, etc.) but which one Lena
# would actually use has not been decided or tested.
PROPOSED_MODEL_PLACEHOLDER = "soul-2 (PLACEHOLDER -- unconfirmed, not selected)"

RISK_FLAGS = (
    "prompt length unknown",
    "negative prompt support unknown",
    "output download path unknown",
    "Soul identity unresolved",
    "moderation/NSFW threshold untested",
    "no live call made",
    "Higgsfield model placeholder unverified",
    "CLI not installed or called by this tool",
)


class ResolveError(Exception):
    """Raised for any hard-fail condition in slot resolution. Never caught
    silently -- main() reports it and exits non-zero."""


def _load_daily_manifest(date_str: str) -> dict:
    path = WORKORDER_ROOT / date_str / "daily_workorders.json"
    if not path.exists():
        raise ResolveError(f"no daily_workorders.json for {date_str}: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ResolveError(f"failed to parse {path}: {exc}") from exc


def _resolve_slot(manifest: dict, slot_id: str) -> dict:
    slots = manifest.get("slots") if isinstance(manifest.get("slots"), list) else []
    for slot in slots:
        if isinstance(slot, dict) and slot.get("slot_id") == slot_id:
            return slot
    raise ResolveError(f"slot_id '{slot_id}' not found in this date's daily_workorders.json")


def _unset_or(value: Any) -> str:
    if value is None or value == "":
        return "<unset>"
    return str(value)


def build_dryrun_summary(date_str: str, slot: dict) -> dict:
    metadata = slot.get("metadata") if isinstance(slot.get("metadata"), dict) else {}
    expected_assets = slot.get("expected_assets") if isinstance(slot.get("expected_assets"), dict) else {}

    media_type = str(slot.get("media_type") or "<unset>")
    image_prompt = slot.get("image_prompt")
    negative_prompt = slot.get("negative_prompt")

    slot_id = str(slot.get("slot_id") or "<unset>")

    if media_type == "video":
        expected_output_path = _unset_or(expected_assets.get("final_video_path"))
    else:
        expected_output_path = _unset_or(
            expected_assets.get("seed_image_path") or expected_assets.get("final_photo_path")
        )

    intended_command = (
        f"higgsfield generate create {PROPOSED_MODEL_PLACEHOLDER.split(' ')[0]} "
        f"--prompt \"<image_prompt, len={len(image_prompt) if isinstance(image_prompt, str) else 0}, not printed>\" "
        f"--json --wait   # NOT EXECUTED -- dry-run only, no subprocess call"
    )

    return {
        "date": date_str,
        "slot_id": slot_id,
        "media_type": media_type,
        "proposed_model_placeholder": PROPOSED_MODEL_PLACEHOLDER,
        "image_prompt_length": len(image_prompt) if isinstance(image_prompt, str) else 0,
        "image_prompt_present": isinstance(image_prompt, str) and bool(image_prompt),
        "negative_prompt_length": len(negative_prompt) if isinstance(negative_prompt, str) else 0,
        "negative_prompt_present": isinstance(negative_prompt, str) and bool(negative_prompt),
        "negative_prompt_support_status": "unknown",
        "metadata_image_engine": _unset_or(metadata.get("image_engine")),
        "metadata_seed_image_engine": _unset_or(metadata.get("seed_image_engine")),
        "intended_command_shape": intended_command,
        "expected_output_path": expected_output_path,
        "proposed_debug_manifest_path": str(
            ROOT / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"
        ),
        "identity_strategy": (
            "Soul/reference mapping unresolved; Kling element identity "
            "(KLING_LENA_ELEMENT_UI_ID) does not transfer directly."
        ),
        "risk_flags": list(RISK_FLAGS),
    }


def print_summary(summary: dict) -> None:
    print("=== Higgsfield payload/contract -- LOCAL NO-CALL DRY RUN ===\n")
    print(f"date                        : {summary['date']}")
    print(f"slot_id                     : {summary['slot_id']}")
    print(f"media_type                  : {summary['media_type']}")
    print()
    print(f"proposed model (PLACEHOLDER): {summary['proposed_model_placeholder']}")
    print()
    print("image_prompt:")
    print(f"  present                   : {summary['image_prompt_present']}")
    print(f"  raw length                : {summary['image_prompt_length']} chars (Higgsfield limit unknown)")
    print()
    print("negative_prompt:")
    print(f"  present                   : {summary['negative_prompt_present']}")
    print(f"  raw length                : {summary['negative_prompt_length']} chars")
    print(f"  support status            : {summary['negative_prompt_support_status']}")
    print()
    print("existing metadata provider markers (not currently populated by any real code path):")
    print(f"  metadata.image_engine      : {summary['metadata_image_engine']}")
    print(f"  metadata.seed_image_engine : {summary['metadata_seed_image_engine']}")
    print()
    print("intended command shape (NOT EXECUTED):")
    print(f"  {summary['intended_command_shape']}")
    print()
    print(f"expected local output path  : {summary['expected_output_path']}")
    print(f"proposed debug manifest path: {summary['proposed_debug_manifest_path']}")
    print()
    print(f"identity strategy           : {summary['identity_strategy']}")
    print()
    print("risk flags:")
    for flag in summary["risk_flags"]:
        print(f"  - {flag}")
    print()
    print("=== RESULT: no subprocess call, no network call, no Higgsfield CLI/SDK use, "
          "no file written. Dry-run only. ===")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="workorder date, e.g. 2026-07-07")
    parser.add_argument("--slot-id", required=True, dest="slot_id", help="slot_id to inspect, e.g. 2026-07-07-03-photo")
    args = parser.parse_args()

    try:
        manifest = _load_daily_manifest(args.date)
        slot = _resolve_slot(manifest, args.slot_id)
    except ResolveError as exc:
        print(f"[ABORT] {exc}")
        return 1

    summary = build_dryrun_summary(args.date, slot)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
