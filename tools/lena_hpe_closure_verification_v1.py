from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_engine_closure_v1 as closure_schema  # noqa: E402
from tools.lena_run_hpe_controlled_proof_v1 import (  # noqa: E402
    HPEControlledProofError,
    build_closure_report_from_proof,
    _load_json_object,
)


class HPEClosureVerificationError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _git_rev_parse(ref: str) -> str:
    result = subprocess.run(["git", "rev-parse", ref], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    payload_bytes = serialized.encode("utf-8")
    if path.exists():
        if path.read_bytes() == payload_bytes:
            return
        raise HPEClosureVerificationError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    path.write_bytes(payload_bytes)


def verify_closure_report(
    proof_report_path: Path,
    *,
    base_commit_sha: str | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    proof_report = _load_json_object(proof_report_path)
    if base_commit_sha is None:
        base_commit_sha = _git_rev_parse("origin/main")
    closure_report = build_closure_report_from_proof(proof_report, base_commit_sha=base_commit_sha)
    validated = closure_schema.validate_closure_verification_report(closure_report)
    if output_path is not None:
        _write_json_atomic(output_path, validated)
    return validated


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a deterministic HPE closure proof report.")
    parser.add_argument("--proof-report", type=Path, required=True)
    parser.add_argument("--base-commit-sha")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        report = verify_closure_report(
            args.proof_report,
            base_commit_sha=args.base_commit_sha,
            output_path=args.output_path,
        )
    except (HPEClosureVerificationError, HPEControlledProofError, closure_schema.HumanPresenceEngineClosureError) as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1

    print(json.dumps({"ok": report["closure_status"] == "verified", "closure_report": report}, indent=2))
    return 0 if report["closure_status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

