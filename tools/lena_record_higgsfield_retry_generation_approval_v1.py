from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_higgsfield_retry_generation_approval_v1 import (  # noqa: E402
    HiggsfieldRetryGenerationApprovalError,
    approval_output_path,
    build_retry_generation_approval_record,
    confirmation_phrase,
    inspect_retry_handoff_artifact,
    write_retry_generation_approval_record_atomic,
)
from tools.lena_higgsfield_generation_approval_v1 import CANONICAL_OPERATOR_ID  # noqa: E402


def record_retry_generation_approval(
    *,
    retry_handoff_artifact: Path,
    operator_id: str,
    confirm: str,
    out_root: Path | None = None,
) -> dict:
    retry_facts = inspect_retry_handoff_artifact(retry_handoff_artifact)
    record = build_retry_generation_approval_record(
        retry_facts,
        operator_id=operator_id,
        confirmation=confirm,
    )
    output_path = approval_output_path(retry_facts["date"], retry_facts["slot_id"], out_root)
    write_retry_generation_approval_record_atomic(output_path, record)
    return {
        "ok": True,
        "approval_artifact_path": str(output_path),
        "date": retry_facts["date"],
        "slot_id": retry_facts["slot_id"],
        "operator_id": operator_id,
        "required_confirmation": confirmation_phrase(retry_facts["slot_id"]),
        "files_written_this_run": [str(output_path)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record a single-use local Higgsfield retry generation approval for a "
            "validated Lena retry handoff artifact. This tool never calls the "
            "executor or any provider."
        )
    )
    parser.add_argument("--retry-handoff-artifact", required=True, type=Path)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--out-root", default=None)
    args = parser.parse_args()

    out_root = None
    if args.out_root:
        candidate = Path(args.out_root)
        out_root = candidate if candidate.is_absolute() else (ROOT / candidate)

    try:
        summary = record_retry_generation_approval(
            retry_handoff_artifact=args.retry_handoff_artifact,
            operator_id=args.operator_id,
            confirm=args.confirm,
            out_root=out_root,
        )
    except HiggsfieldRetryGenerationApprovalError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": exc.code,
                    "error": exc.detail,
                    "required_operator_id": CANONICAL_OPERATOR_ID,
                    "files_written_this_run": [],
                },
                indent=2,
            )
        )
        return 1

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
