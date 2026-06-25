"""
Lena Asset Sidecar Initializer v1

Creates the .status.json sidecar for a newly generated Lena asset.
All approval fields default to safe/blocked values.

No publish approval is ever granted by this script.
FINAL_PUBLISH_APPROVED_BY_NICOLAS must be written manually after Nicolas
reviews the asset, caption, and visual/caption match.

Usage:
  python tools/generation/lena_sidecar_init_v1.py \\
    --asset-path pipeline/content_library/lena/assets/2026-06-26/lena_slot01.jpg \\
    --slot-id 2026-06-26-01-photo \\
    --date 2026-06-26

  python tools/generation/lena_sidecar_init_v1.py ... --dry-run
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SAFE_DEFAULTS: dict = {
    "visual_status":                          "candidate_only",
    "publish_approved":                       False,
    "caption_approved":                       False,
    "caption_visual_match_approved":          False,
    "publish_blocked_reason":                 "not explicitly approved by Nicolas",
    "no_publish_without_explicit_future_approval": True,
    "instagram_published":                    False,
    "instagram_currently_live":               False,
    "r2_uploaded":                            False,
    "queue_entry_created":                    False,
}

FINAL_PUBLISH_APPROVAL_SCHEMA: dict = {
    "_description": (
        "Write this object manually after Nicolas reviews asset + caption."
        " Never set by any automated script."
    ),
    "approved":                     "<must be set to true by Nicolas>",
    "asset_path":                   "<exact absolute or ROOT-relative asset path>",
    "caption":                      "<exact caption text matching publish payload>",
    "target_platform":              "<e.g. Instagram Feed>",
    "caption_visual_match_approved": "<must be set to true by Nicolas>",
    "known_visual_qa_objections":   [],
    "approved_by":                  "Nicolas",
    "approved_at":                  "<ISO 8601 timestamp>",
}


def resolve_asset_path(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def build_sidecar(
    asset_path: Path,
    slot_id: str,
    date: str,
    generation_details: dict | None,
) -> dict:
    rel = str(asset_path.relative_to(ROOT)).replace("\\", "/")
    sidecar: dict = {
        "asset_filename": asset_path.name,
        "asset_path":     rel,
        "date":           date,
        "slot_id":        slot_id,
        "created_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **SAFE_DEFAULTS,
    }
    if generation_details is not None:
        sidecar["generation_details"] = generation_details
    sidecar["_FINAL_PUBLISH_APPROVAL_SCHEMA"] = FINAL_PUBLISH_APPROVAL_SCHEMA
    return sidecar


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Initialize a safe .status.json sidecar for a Lena asset."
    )
    ap.add_argument(
        "--asset-path", required=True, dest="asset_path",
        help="Path to asset file (absolute or relative to repo root).",
    )
    ap.add_argument(
        "--slot-id", required=True, dest="slot_id",
        help="Slot ID, e.g. 2026-06-26-01-photo.",
    )
    ap.add_argument(
        "--date", required=True,
        help="Content date YYYY-MM-DD.",
    )
    ap.add_argument(
        "--generation-details-json", default="", dest="gen_details_json",
        help=(
            "Optional JSON string of generation metadata. "
            "Stored under generation_details. "
            "Never used to grant publish approval."
        ),
    )
    ap.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Preview sidecar contents; do not write to disk.",
    )
    args = ap.parse_args()

    asset_path = resolve_asset_path(args.asset_path)
    sidecar_path = asset_path.with_suffix(".status.json")

    print("=" * 64)
    print("  LENA SIDECAR INITIALIZER v1")
    print("=" * 64)
    print(f"  asset_path   : {asset_path}")
    print(f"  sidecar_path : {sidecar_path}")
    print(f"  slot_id      : {args.slot_id}")
    print(f"  date         : {args.date}")
    print(f"  dry_run      : {args.dry_run}")
    print()

    if not asset_path.exists():
        print("ABORT: asset file not found.")
        print(f"  expected : {asset_path}")
        return 1

    if sidecar_path.exists():
        print("ABORT: sidecar already exists — will not overwrite.")
        print(f"  path     : {sidecar_path}")
        if args.dry_run:
            print()
            print("DRY RUN note: even in dry-run mode the existing sidecar")
            print("would block a live write. Delete it manually to reinitialize.")
        return 1

    generation_details: dict | None = None
    if args.gen_details_json.strip():
        try:
            generation_details = json.loads(args.gen_details_json)
            if not isinstance(generation_details, dict):
                print("ABORT: --generation-details-json must be a JSON object.")
                return 1
        except json.JSONDecodeError as exc:
            print(f"ABORT: --generation-details-json is not valid JSON: {exc}")
            return 1

    sidecar = build_sidecar(
        asset_path=asset_path,
        slot_id=args.slot_id,
        date=args.date,
        generation_details=generation_details,
    )

    print("Sidecar preview:")
    print(json.dumps(sidecar, indent=2, ensure_ascii=False))
    print()

    if args.dry_run:
        print("DRY RUN — sidecar not written.")
        print()
        print("Approval gate fields confirmed absent:")
        print(f"  FINAL_PUBLISH_APPROVED_BY_NICOLAS : not present")
        print(f"  publish_approved                  : {sidecar['publish_approved']}")
        print(f"  caption_visual_match_approved     : {sidecar['caption_visual_match_approved']}")
        print(f"  visual_status                     : {sidecar['visual_status']}")
        print(f"  publish_blocked_reason            : {sidecar['publish_blocked_reason']!r}")
        return 0

    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Written : {sidecar_path}")
    print()
    print("Approval gate fields confirmed absent:")
    print(f"  FINAL_PUBLISH_APPROVED_BY_NICOLAS : not present")
    print(f"  publish_approved                  : {sidecar['publish_approved']}")
    print(f"  caption_visual_match_approved     : {sidecar['caption_visual_match_approved']}")
    print(f"  visual_status                     : {sidecar['visual_status']}")
    print(f"  publish_blocked_reason            : {sidecar['publish_blocked_reason']!r}")
    print()
    print("Asset is blocked from publish until Nicolas adds")
    print("FINAL_PUBLISH_APPROVED_BY_NICOLAS manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
