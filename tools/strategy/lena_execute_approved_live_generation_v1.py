from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pipeline.higgsfield_lena_api_executor as executor
from tools import lena_higgsfield_generation_approval_v1 as approval


ROOT = Path(__file__).resolve().parents[2]
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"

REPORT_TYPE = "lena_live_generation_accounting"
SCHEMA_VERSION = "v1"


class LiveGenerationAccountingError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def repo_relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LiveGenerationAccountingError(code, detail)


def report_path(date_str: str, slot_id: str) -> Path:
    return NEXT_ACTIONS / date_str / f"lena_live_generation_accounting_{date_str}_{slot_id}.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise LiveGenerationAccountingError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def load_execution_context(
    handoff_artifact: Path,
    approval_artifact: Path,
) -> dict[str, Any]:
    handoff_report, source, packet_validation, validation = executor._validate_handoff_packet(Path(handoff_artifact))
    approval_result = approval.validate_generation_approval_artifact(Path(approval_artifact))

    handoff_facts = approval_result["handoff_facts"]
    date_str = str(handoff_facts["date"])
    slot_id = str(handoff_facts["slot_id"])
    claim_path = approval.claim_output_path(date_str, slot_id)
    receipt_path = approval.receipt_output_path(date_str, slot_id)
    manifest_repo_path = executor.manifest_path(date_str, slot_id)

    return {
        "date": date_str,
        "slot_id": slot_id,
        "recipe_id": str(handoff_report.get("selected_recipe_id") or ""),
        "handoff_report": handoff_report,
        "source": source,
        "packet_validation": packet_validation,
        "validation": validation,
        "approval_result": approval_result,
        "claim_path": claim_path,
        "receipt_path": receipt_path,
        "manifest_path": manifest_repo_path,
        "handoff_artifact": Path(handoff_artifact),
        "approval_artifact": Path(approval_artifact),
        "custom_reference_id": str(handoff_facts["custom_reference_id"]),
    }


def _base_report(
    *,
    context: dict[str, Any],
    live: bool,
    execution_result: dict[str, Any] | None,
    claim_written: bool,
    receipt_written: bool,
) -> dict[str, Any]:
    live_result = execution_result.get("live_result") if execution_result else None
    saved_image_path = live_result.get("saved_image_path") if live_result else None
    manifest_repo_path = Path(execution_result["manifest_path"]) if execution_result and execution_result.get("manifest_path") else context["manifest_path"]
    provider_submission_may_have_occurred = bool(execution_result.get("provider_submission_may_have_occurred")) if execution_result else False
    provider_call_performed = bool(execution_result.get("provider_call_performed")) if execution_result else False
    generation_performed = bool(execution_result.get("generation_performed")) if execution_result else False
    failure_stage = execution_result.get("failure_stage") if execution_result else None
    failure_error_text = execution_result.get("failure_error_text") if execution_result else None
    manifest_written = bool(execution_result.get("manifest_written")) if execution_result else False
    claim_written = bool(claim_written or (execution_result and execution_result.get("claim_written")))
    receipt_written = bool(receipt_written or (execution_result and execution_result.get("receipt_written")))
    report = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_now(),
        "date": context["date"],
        "slot_id": context["slot_id"],
        "recipe_id": context["recipe_id"],
        "live_generation_accounting_status": (
            "live_generation_accounted"
            if live and execution_result and execution_result.get("ok")
            else "live_generation_failed_accounted"
            if live and execution_result and not execution_result.get("ok")
            else "live_generation_validated"
        ),
        "handoff_artifact": repo_relative_path(context["handoff_artifact"]),
        "approval_artifact": repo_relative_path(context["approval_artifact"]),
        "executor_result_manifest": repo_relative_path(manifest_repo_path) if manifest_repo_path else "",
        "generated_output_paths": {
            "saved_image_path": repo_relative_path(Path(saved_image_path)) if saved_image_path else None,
            "manifest_path": repo_relative_path(manifest_repo_path) if manifest_repo_path else None,
        },
        "generation_claim_artifact": repo_relative_path(context["claim_path"]),
        "generation_receipt_artifact": repo_relative_path(context["receipt_path"]),
        "claim_written": claim_written,
        "receipt_written": receipt_written,
        "manifest_written": manifest_written,
        "publish_authorized": False,
        "publish_performed": False,
        "queue_mutated": False,
        "qa_disposition_required": True,
        "next_allowed_action": (
            "run_qa_disposition"
            if live and execution_result and execution_result.get("ok")
            else "review_live_generation_failure"
            if live and execution_result and not execution_result.get("ok")
            else "run_approved_live_generation"
        ),
        "dirty_workspace_dependency": False,
        "failure_stage": failure_stage,
        "failure_error_text": failure_error_text,
        "provider_submission_may_have_occurred": provider_submission_may_have_occurred,
        "subprocess_start_attempted": bool(execution_result.get("subprocess_start_attempted")) if execution_result else False,
        "side_effect_flags": {
            "provider_call_performed": provider_call_performed,
            "generation_performed": generation_performed,
            "publish_performed": False,
            "queue_mutated": False,
            "approval_consumed": claim_written,
            "claims_written": claim_written,
            "receipts_written": receipt_written,
            "qa_run": False,
            "retry_executed": False,
            "dirty_workspace_dependency": False,
        },
    }
    return report


def execute_approved_live_generation(
    handoff_artifact: Path,
    approval_artifact: Path,
    *,
    live: bool = False,
    custom_reference_id: str | None = None,
    live_executor: Callable[[str, str, dict[str, Any], str], dict[str, Any]] | None = None,
    context_loader: Callable[[Path, Path], dict[str, Any]] = load_execution_context,
) -> dict[str, Any]:
    handoff_artifact = Path(handoff_artifact)
    approval_artifact = Path(approval_artifact)
    _require(handoff_artifact.is_file(), "missing_handoff", f"missing required handoff artifact: {handoff_artifact}")
    _require(approval_artifact.is_file(), "missing_approval", f"missing required approval artifact: {approval_artifact}")

    context = context_loader(handoff_artifact, approval_artifact)
    if not live:
        return _base_report(
            context=context,
            live=False,
            execution_result=None,
            claim_written=False,
            receipt_written=False,
        )

    execution_result = executor.execute_approved_handoff_live_generation(
        context,
        custom_reference_id=custom_reference_id,
        live_executor=live_executor or executor.run_live,
    )
    report = _base_report(
        context=context,
        live=True,
        execution_result=execution_result,
        claim_written=bool(execution_result.get("claim_written")),
        receipt_written=bool(execution_result.get("receipt_written")),
    )
    _write_json_atomic(report_path(context["date"], context["slot_id"]), report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute an approved Lena live generation and write accounting output.")
    parser.add_argument("--handoff-artifact", type=Path, required=True)
    parser.add_argument("--approval-artifact", type=Path, required=True)
    parser.add_argument("--custom-reference-id", default=None)
    parser.add_argument("--live", action="store_true", help="Perform the approved live execution.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        report = execute_approved_live_generation(
            args.handoff_artifact,
            args.approval_artifact,
            live=args.live,
            custom_reference_id=args.custom_reference_id,
        )
    except LiveGenerationAccountingError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1

    print(json.dumps({"ok": True, "report": report, "report_path": repo_relative_path(report_path(report["date"], report["slot_id"]))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
