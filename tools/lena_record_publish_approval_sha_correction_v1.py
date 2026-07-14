from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_publish_approval_binding_v1 import (  # noqa: E402
    build_approval_sha_binding_correction,
    resolve_approval_output_path,
    write_approval_sha_binding_correction,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one existing Lena publish approval whose only defect is missing or incorrect "
            "publish-packet/queue-draft SHA bindings, and optionally write one immutable correction "
            "artifact that supersedes that approval for execution only. Defaults to dry-run."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact slot_id")
    parser.add_argument("--out-dir", default=None, help="Override the packet/queue-draft/approval output base directory.")
    parser.add_argument(
        "--write-artifact",
        action="store_true",
        help="Write the correction artifact. Without this flag, only a dry-run report is printed.",
    )
    args = parser.parse_args()

    out_dir: Optional[Path] = None
    if args.out_dir:
        candidate = Path(args.out_dir)
        out_dir = candidate if candidate.is_absolute() else (ROOT / candidate)

    approval_path = resolve_approval_output_path(args.date, args.slot_id, out_dir)
    try:
        correction, correction_path = build_approval_sha_binding_correction(approval_path)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "date": args.date,
                    "slot_id": args.slot_id,
                    "approval_path": str(approval_path),
                    "error": str(exc),
                    "files_written_this_run": [],
                },
                indent=2,
            )
        )
        return 1

    report = {
        "approval_path": str(approval_path),
        "future_correction_artifact_path": str(correction_path),
        "future_correction_artifact": correction,
    }
    if not args.write_artifact:
        print(json.dumps({"ok": True, "dry_run": True, "checked": report, "files_written_this_run": []}, indent=2))
        return 0

    try:
        write_approval_sha_binding_correction(correction_path, correction)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "date": args.date,
                    "slot_id": args.slot_id,
                    "approval_path": str(approval_path),
                    "checked": report,
                    "error": str(exc),
                    "files_written_this_run": [],
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "checked": report,
                "files_written_this_run": [str(correction_path)],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
