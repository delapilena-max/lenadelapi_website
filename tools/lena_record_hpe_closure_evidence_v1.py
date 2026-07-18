from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_closure_evidence_v1 as closure_evidence  # noqa: E402


class HPEClosureEvidenceRecorderError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HPEClosureEvidenceRecorderError("payload_invalid", f"could not read payload {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HPEClosureEvidenceRecorderError("payload_invalid", "payload must be a JSON object")
    return payload


def record_final_ci_confirmation(payload: dict[str, Any], *, output_root: Path) -> dict[str, Any]:
    artifact = closure_evidence.build_final_ci_confirmation_artifact(
        repository=str(payload["repository"]),
        pr_number=int(payload["pr_number"]),
        reviewed_head_sha=str(payload["reviewed_head_sha"]),
        merge_commit_sha=str(payload["merge_commit_sha"]),
        required_checks=list(payload["required_checks"]),
        evidence_source=str(payload["evidence_source"]),
        authority_commit_expected=str(payload["authority_commit_expected"]),
        authority_commit_final=str(payload["authority_commit_final"]),
        evidence_collected_at_utc=payload.get("evidence_collected_at_utc"),
        github_pr_url=payload.get("github_pr_url"),
        github_merge_commit_url=payload.get("github_merge_commit_url"),
    )
    path, sha = closure_evidence.write_final_ci_confirmation_artifact(
        date_str=str(payload["date_str"]),
        slot_id=str(payload["slot_id"]),
        image_index=int(payload["image_index"]),
        artifact=artifact,
        output_root=output_root,
    )
    return {"artifact_path": str(path), "artifact_sha256": sha}


def record_human_evidence_review(payload: dict[str, Any], *, output_root: Path) -> dict[str, Any]:
    artifact = closure_evidence.build_human_evidence_review_artifact(
        reviewer_operator_id=str(payload["reviewer_operator_id"]),
        reviewed_image_path=payload["reviewed_image_path"],
        reviewed_image_sha256=str(payload["reviewed_image_sha256"]),
        candidate_artifact_path=payload["candidate_artifact_path"],
        candidate_artifact_sha256=str(payload["candidate_artifact_sha256"]),
        handoff_artifact_path=payload["handoff_artifact_path"],
        handoff_artifact_sha256=str(payload["handoff_artifact_sha256"]),
        execution_receipt_artifact_path=payload["execution_receipt_artifact_path"],
        execution_receipt_artifact_sha256=str(payload["execution_receipt_artifact_sha256"]),
        provider_job_id=str(payload["provider_job_id"]),
        authority_commit_expected=str(payload["authority_commit_expected"]),
        authority_commit_final=str(payload["authority_commit_final"]),
        disposition=str(payload["disposition"]),
        findings=list(payload.get("findings") or []),
        confirmation_statement=str(payload["confirmation_statement"]),
        publishing_authorized=bool(payload.get("publishing_authorized", False)),
        evidence_source=str(payload.get("evidence_source", "human_operator")),
        reviewed_at_utc=payload.get("reviewed_at_utc"),
    )
    path, sha = closure_evidence.write_human_evidence_review_artifact(
        date_str=str(payload["date_str"]),
        slot_id=str(payload["slot_id"]),
        image_index=int(payload["image_index"]),
        artifact=artifact,
        output_root=output_root,
    )
    return {"artifact_path": str(path), "artifact_sha256": sha}


def record_manual_semantic_review(payload: dict[str, Any], *, output_root: Path) -> dict[str, Any]:
    artifact = closure_evidence.build_manual_semantic_review_artifact(
        reviewer_operator_id=str(payload["reviewer_operator_id"]),
        reviewed_image_path=payload["reviewed_image_path"],
        reviewed_image_sha256=str(payload["reviewed_image_sha256"]),
        prompt_artifact_path=payload["prompt_artifact_path"],
        prompt_sha256=str(payload["prompt_sha256"]),
        candidate_artifact_path=payload["candidate_artifact_path"],
        candidate_artifact_sha256=str(payload["candidate_artifact_sha256"]),
        execution_receipt_artifact_path=payload["execution_receipt_artifact_path"],
        execution_receipt_artifact_sha256=str(payload["execution_receipt_artifact_sha256"]),
        provider_job_id=str(payload["provider_job_id"]),
        authority_commit_expected=str(payload["authority_commit_expected"]),
        authority_commit_final=str(payload["authority_commit_final"]),
        disposition=str(payload["disposition"]),
        assessment=list(payload["assessment"]),
        findings=list(payload.get("findings") or []),
        confirmation_statement=str(payload["confirmation_statement"]),
        evidence_source=str(payload.get("evidence_source", "manual_human_semantic_review")),
        publishing_authorized=bool(payload.get("publishing_authorized", False)),
        reviewed_at_utc=payload.get("reviewed_at_utc"),
    )
    path, sha = closure_evidence.write_manual_semantic_review_artifact(
        date_str=str(payload["date_str"]),
        slot_id=str(payload["slot_id"]),
        image_index=int(payload["image_index"]),
        artifact=artifact,
        output_root=output_root,
    )
    return {"artifact_path": str(path), "artifact_sha256": sha}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record HPE closure evidence artifacts.")
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=closure_evidence.DEFAULT_OUTPUT_ROOT)
    subparsers = parser.add_subparsers(dest="kind", required=True)
    subparsers.add_parser("final-ci")
    subparsers.add_parser("human-review")
    subparsers.add_parser("manual-semantic-review")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        payload = _load_payload(args.payload)
        if args.kind == "final-ci":
            result = record_final_ci_confirmation(payload, output_root=args.output_root)
        elif args.kind == "human-review":
            result = record_human_evidence_review(payload, output_root=args.output_root)
        else:
            result = record_manual_semantic_review(payload, output_root=args.output_root)
    except (HPEClosureEvidenceRecorderError, closure_evidence.ClosureEvidenceError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "code": getattr(exc, "code", "payload_invalid"), "detail": str(exc)}, indent=2))
        return 1

    print(json.dumps({"ok": True, **result}, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
