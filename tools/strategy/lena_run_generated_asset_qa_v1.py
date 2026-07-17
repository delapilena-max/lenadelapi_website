from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

import tools.lena_higgsfield_generation_approval_v1 as approval
import tools.lena_presence_output_qa_disposition_v1 as human_presence_qa
import tools.lena_photo_qa_disposition_v1 as qa_disposition
import tools.strategy.lena_execute_retry_decision_v1 as retry_decision
import tools.strategy.lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff
from pipeline.identity import lena_higgsfield_identity as identity
from pipeline.influencer_nodes.lena import autonomy_ladder
from pipeline.presence.human_presence_output_qa_v1 import HumanPresenceOutputQAError


ROOT = Path(__file__).resolve().parents[2]
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
ACCOUNTING_REPORT_TYPE = "lena_live_generation_accounting"
ACCOUNTING_SCHEMA_VERSION = "v1"
LIFECYCLE_REPORT_TYPE = "lena_generated_asset_qa_lifecycle"
LIFECYCLE_SCHEMA_VERSION = "v1"
ACCOUNTING_RE = re.compile(
    r"^lena_live_generation_accounting_(?P<date>\d{4}-\d{2}-\d{2})_(?P<slot_id>.+)\.json$"
)


class GeneratedAssetQaLifecycleError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class PresenceOutputQARunner(Protocol):
    def __call__(
        self,
        *,
        date_str: str,
        slot_id: str,
        image_index: int,
        plan: dict[str, Any] | None,
        candidate_decision_path: Path,
        manifest_path: Path,
        image_path: Path,
        media_type: str,
        output_root: Path | None = None,
        evaluated_at_utc: str | None = None,
        live_presence_semantic_review: bool = False,
        semantic_provider: Callable[..., dict[str, Any]] | None = None,
        semantic_timeout_seconds: float = 30.0,
    ) -> tuple[Path, dict[str, Any]]:
        ...


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
        raise GeneratedAssetQaLifecycleError(code, detail)


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise GeneratedAssetQaLifecycleError(code, f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GeneratedAssetQaLifecycleError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GeneratedAssetQaLifecycleError(code, f"{label} must be a JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise GeneratedAssetQaLifecycleError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def parse_accounting_path(path: Path) -> tuple[str, str]:
    match = ACCOUNTING_RE.fullmatch(path.name)
    if match:
        return match.group("date"), match.group("slot_id")
    return utc_date(), "blocked"


def report_path(date_str: str, slot_id: str, output_root: Path = NEXT_ACTIONS) -> Path:
    return output_root / date_str / f"{LIFECYCLE_REPORT_TYPE}_{date_str}_{slot_id}.json"


def _load_accounting_report(path: Path) -> dict[str, Any]:
    report = _read_json_object(path, code="missing_live_generation_accounting_report", label="live generation accounting artifact")
    _require(
        report.get("report_type") == ACCOUNTING_REPORT_TYPE,
        "live_generation_accounting_report_type_mismatch",
        f"live generation accounting report_type must be {ACCOUNTING_REPORT_TYPE!r}",
    )
    _require(
        report.get("schema_version") == ACCOUNTING_SCHEMA_VERSION,
        "live_generation_accounting_schema_version_mismatch",
        f"live generation accounting schema_version must be {ACCOUNTING_SCHEMA_VERSION!r}",
    )
    _require(
        report.get("live_generation_accounting_status") == "live_generation_accounted",
        "live_generation_accounting_not_successful",
        "live generation accounting must report a successful accounted execution",
    )
    _require(report.get("publish_authorized") is False, "publish_authorized_invalid", "live generation accounting must not authorize publish")
    _require(report.get("publish_performed") is False, "publish_performed_invalid", "live generation accounting must not perform publish")
    _require(report.get("queue_mutated") is False, "queue_mutated_invalid", "live generation accounting must not mutate the queue")
    _require(report.get("qa_disposition_required") is True, "qa_disposition_required_invalid", "live generation accounting must require QA disposition")
    _require(report.get("claim_written") is True, "claim_not_written", "live generation accounting must record a claim")
    _require(report.get("receipt_written") is True, "receipt_not_written", "live generation accounting must record a receipt")
    generated_output_paths = report.get("generated_output_paths", {})
    _require(isinstance(generated_output_paths, dict), "generated_output_paths_invalid", "generated_output_paths must be a JSON object")
    _require(
        bool(generated_output_paths.get("saved_image_path")),
        "generated_image_path_missing",
        "live generation accounting must contain a saved image path",
    )
    _require(
        bool(generated_output_paths.get("manifest_path")),
        "executor_result_manifest_missing",
        "live generation accounting must contain a manifest path",
    )
    _require(
        bool(report.get("generation_claim_artifact")),
        "generation_claim_artifact_missing",
        "live generation accounting must contain a generation claim artifact path",
    )
    _require(
        bool(report.get("generation_receipt_artifact")),
        "generation_receipt_artifact_missing",
        "live generation accounting must contain a generation receipt artifact path",
    )
    return report


def _resolve_repo_path(path_value: str, *, label: str) -> Path:
    raw = str(path_value or "").strip()
    _require(bool(raw), f"{label}_missing", f"{label} is missing")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _source_record(path: Path, *, report_type: str | None = None, schema_version: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_artifact_path": repo_relative_path(path),
        "source_artifact_present": path.is_file(),
        "source_artifact_sha256": _sha256_file(path) if path.is_file() else None,
    }
    if report_type is not None:
        record["source_report_type"] = report_type
    if schema_version is not None:
        record["source_schema_version"] = schema_version
    return record


def _validate_claim_and_receipt(
    *,
    accounting_report: dict[str, Any],
    approval_result: dict[str, Any],
    manifest_path: Path,
    claim_path: Path,
    receipt_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_claim = approval.build_generation_claim_record(approval_result)
    expected_claim.pop("claimed_at_utc", None)
    actual_claim = _read_json_object(
        claim_path,
        code="generation_claim_missing_or_invalid",
        label="generation claim artifact",
    )
    actual_claim_without_timestamp = dict(actual_claim)
    actual_claim_without_timestamp.pop("claimed_at_utc", None)
    for key, value in expected_claim.items():
        _require(
            actual_claim_without_timestamp.get(key) == value,
            "generation_claim_binding_mismatch",
            f"generation claim artifact field {key!r} does not match the approval lineage",
        )

    expected_receipt = approval.build_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome="success",
        subprocess_start_attempted=bool(accounting_report.get("subprocess_start_attempted")),
        provider_submission_may_have_occurred=bool(accounting_report.get("provider_submission_may_have_occurred")),
        provider_job_id=str(_read_json_object(manifest_path, code="executor_result_manifest_missing_or_invalid", label="executor result manifest").get("provider_job_id") or ""),
        provider_status=str(_read_json_object(manifest_path, code="executor_result_manifest_missing_or_invalid", label="executor result manifest").get("provider_status") or ""),
        output_path=str(_read_json_object(manifest_path, code="executor_result_manifest_missing_or_invalid", label="executor result manifest").get("saved_image_path") or ""),
        image_format_detected=str(_read_json_object(manifest_path, code="executor_result_manifest_missing_or_invalid", label="executor result manifest").get("image_format_detected") or ""),
        actual_manifest_path=repo_relative_path(manifest_path),
    )
    expected_receipt = dict(expected_receipt)
    expected_receipt.pop("receipt_written_at_utc", None)

    actual_receipt = _read_json_object(
        receipt_path,
        code="generation_receipt_missing_or_invalid",
        label="generation receipt artifact",
    )
    actual_receipt_without_timestamp = dict(actual_receipt)
    actual_receipt_without_timestamp.pop("receipt_written_at_utc", None)
    for key, value in expected_receipt.items():
        _require(
            actual_receipt_without_timestamp.get(key) == value,
            "generation_receipt_binding_mismatch",
            f"generation receipt artifact field {key!r} does not match the approval lineage",
        )
    return actual_claim, actual_receipt


def _retry_reference_artifacts(
    *,
    decision_artifact: dict[str, Any],
    date_str: str,
    qa_artifact: dict[str, Any],
) -> tuple[str, str]:
    if not qa_artifact.get("retry_eligible"):
        return "", ""
    candidate = decision_artifact.get("candidate", {})
    retry_slot_id = retry_decision._retry_slot_id(str(candidate.get("slot_id", "")))
    decision_fingerprint = str(decision_artifact.get("decision_fingerprint_sha256") or "")
    prompt_sha = str(candidate.get("prompt_sha256") or "")
    retry_decision_path = retry_decision.retry_decision_artifact_path(
        date_str,
        retry_slot_id,
        decision_fingerprint,
    )
    retry_handoff_path = retry_handoff.retry_handoff_artifact_path(
        date_str,
        retry_slot_id,
        prompt_sha,
    )
    return repo_relative_path(retry_decision_path), repo_relative_path(retry_handoff_path)


def _default_human_presence_output_qa_state() -> dict[str, Any]:
    return {
        "schema_version": "human_presence_output_qa_lifecycle_state_v1",
        "status": "not_requested",
        "artifact_path": None,
        "image_index": 0,
        "integrity_status": None,
        "recommendation": None,
        "semantic_status": "not_evaluated",
        "error_code": None,
        "error_message": None,
        "reason": "hpe_not_requested",
        "authority": "evidence_only",
    }


def _error_human_presence_output_qa_state(error_code: str, error_message: str) -> dict[str, Any]:
    return {
        "schema_version": "human_presence_output_qa_lifecycle_state_v1",
        "status": "error",
        "artifact_path": None,
        "image_index": 0,
        "integrity_status": None,
        "recommendation": None,
        "semantic_status": "not_evaluated",
        "error_code": error_code,
        "error_message": error_message,
        "reason": None,
        "authority": "evidence_only",
    }


def _completed_human_presence_output_qa_state(artifact_path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "human_presence_output_qa_lifecycle_state_v1",
        "status": "completed",
        "artifact_path": repo_relative_path(artifact_path),
        "image_index": 0,
        "integrity_status": artifact.get("integrity_status"),
        "recommendation": artifact.get("recommendation"),
        "semantic_status": artifact.get("semantic_status", "not_evaluated"),
        "error_code": None,
        "error_message": None,
        "reason": None,
        "authority": "evidence_only",
    }


def _resolve_human_presence_output_qa_plan_state(decision_report: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    evidence = decision_report.get("evidence")
    if evidence is None:
        return None, _default_human_presence_output_qa_state()
    if not isinstance(evidence, dict):
        return None, _error_human_presence_output_qa_state(
            "presence_output_qa_integration_error",
            "decision evidence must be a JSON object",
        )
    prompt_pack = evidence.get("prompt_pack")
    if prompt_pack is None:
        return None, _default_human_presence_output_qa_state()
    if not isinstance(prompt_pack, dict):
        return None, _error_human_presence_output_qa_state(
            "presence_output_qa_integration_error",
            "decision prompt_pack must be a JSON object",
        )
    if "human_presence" not in prompt_pack:
        return None, _default_human_presence_output_qa_state()
    human_presence = prompt_pack.get("human_presence")
    if human_presence is None:
        return None, _default_human_presence_output_qa_state()
    if not isinstance(human_presence, dict):
        return None, _error_human_presence_output_qa_state(
            "presence_output_qa_integration_error",
            "decision human_presence plan must be a JSON object",
        )
    return human_presence, None


def evaluate_generated_asset_qa_lifecycle(
    *,
    live_generation_accounting_artifact: Path,
    decision_artifact: Path,
    identity_reference_authority_artifact: Path,
    identity_reference_authority_sha256: str,
    identity_references: Iterable[tuple[Path, str]],
    identity_evidence_artifact: Path | None = None,
    qa_runner: Callable[..., dict[str, Any]] = qa_disposition.evaluate_photo_qa_disposition,
    human_presence_output_qa_runner: PresenceOutputQARunner = human_presence_qa.run_presence_output_qa,
    qa_output_root: Path | None = None,
    lifecycle_output_root: Path | None = None,
    live_presence_semantic_review: bool = False,
) -> dict[str, Any]:
    if qa_output_root is None:
        qa_output_root = qa_disposition.OUTPUT_ROOT
    if lifecycle_output_root is None:
        lifecycle_output_root = NEXT_ACTIONS

    accounting_path = Path(live_generation_accounting_artifact).resolve()
    date_str, slot_id = parse_accounting_path(accounting_path)

    try:
        autonomy_ladder.assert_allowed(
            "lena_run_generated_asset_qa_v1",
            level=2,
            action="QA disposition orchestration",
        )
    except autonomy_ladder.AutonomyLadderError as exc:
        raise GeneratedAssetQaLifecycleError(exc.code, exc.detail) from exc

    accounting_report = _load_accounting_report(accounting_path)
    date_str = str(accounting_report.get("date") or date_str)
    slot_id = str(accounting_report.get("slot_id") or slot_id)
    recipe_id = str(accounting_report.get("recipe_id") or "")

    approval_artifact = _resolve_repo_path(str(accounting_report.get("approval_artifact") or ""), label="approval_artifact")
    approval_result = approval.validate_generation_approval_artifact(approval_artifact, require_not_expired=False)

    manifest_path = _resolve_repo_path(str(accounting_report.get("executor_result_manifest") or ""), label="executor_result_manifest")
    image_path = _resolve_repo_path(str(accounting_report.get("generated_output_paths", {}).get("saved_image_path") or ""), label="generated_image_path")
    claim_path = _resolve_repo_path(str(accounting_report.get("generation_claim_artifact") or ""), label="generation_claim_artifact")
    receipt_path = _resolve_repo_path(str(accounting_report.get("generation_receipt_artifact") or ""), label="generation_receipt_artifact")

    _require(image_path.is_file(), "generated_image_missing", f"generated image is missing: {image_path}")
    _require(manifest_path.is_file(), "executor_result_manifest_missing", f"executor result manifest is missing: {manifest_path}")
    _require(claim_path.is_file(), "generation_claim_missing", f"generation claim is missing: {claim_path}")
    _require(receipt_path.is_file(), "generation_receipt_missing", f"generation receipt is missing: {receipt_path}")

    manifest = _read_json_object(
        manifest_path,
        code="executor_result_manifest_missing_or_invalid",
        label="executor result manifest",
    )
    _require(manifest.get("provider") == "higgsfield", "executor_result_manifest_provider_invalid", "manifest provider must be higgsfield")
    _require(manifest.get("date") == date_str, "executor_result_manifest_date_mismatch", "manifest date does not match the accounting report")
    _require(manifest.get("slot_id") == slot_id, "executor_result_manifest_slot_mismatch", "manifest slot_id does not match the accounting report")
    _require(manifest.get("provider_status") == "completed", "executor_result_manifest_not_completed", "manifest provider_status must be completed")
    _require(
        str(manifest.get("saved_image_path") or "").strip() == str(image_path),
        "executor_result_manifest_image_mismatch",
        "manifest saved_image_path does not match the generated image",
    )
    _require(
        str(manifest.get("generation_claim_artifact_path") or "").strip() == repo_relative_path(claim_path),
        "executor_result_manifest_claim_mismatch",
        "manifest claim path does not match the generation claim",
    )
    _require(
        str(manifest.get("generation_execution_receipt_path") or "").strip() == repo_relative_path(receipt_path),
        "executor_result_manifest_receipt_mismatch",
        "manifest receipt path does not match the generation receipt",
    )

    actual_claim, actual_receipt = _validate_claim_and_receipt(
        accounting_report=accounting_report,
        approval_result=approval_result,
        manifest_path=manifest_path,
        claim_path=claim_path,
        receipt_path=receipt_path,
    )

    decision_path = Path(decision_artifact).resolve()
    _require(decision_path.is_file(), "decision_artifact_missing", f"decision artifact is missing: {decision_path}")

    reference_specs = list(identity_references)
    _require(reference_specs, "identity_reference_missing", "at least one identity reference is required")
    if identity_evidence_artifact is None:
        identity_evidence_artifact = identity.identity_verification_evidence_path(date_str, slot_id)

    qa_artifact = qa_runner(
        decision_path=decision_path,
        manifest_path=manifest_path,
        image_path=image_path,
        identity_evidence_path=identity_evidence_artifact,
        reference_specs=reference_specs,
        reference_authority_artifact=identity_reference_authority_artifact,
        reference_authority_sha256=identity_reference_authority_sha256,
        expected_image_sha256=_sha256_file(image_path),
    )

    qa_path, qa_written_artifact, _qa_was_written = qa_disposition.write_disposition_artifact(qa_artifact, output_root=qa_output_root)
    qa_status = str(qa_written_artifact.get("disposition") or qa_artifact.get("disposition") or "blocked")
    retry_recommended = bool(qa_written_artifact.get("retry_eligible"))
    decision_report = _read_json_object(decision_path, code="decision_artifact_missing_or_invalid", label="decision artifact")
    human_presence_plan, human_presence_output_qa_state = _resolve_human_presence_output_qa_plan_state(decision_report)
    if human_presence_output_qa_state is None:
        try:
            human_presence_artifact_path, human_presence_artifact = human_presence_output_qa_runner(
                date_str=date_str,
                slot_id=slot_id,
                image_index=0,
                plan=human_presence_plan,
                candidate_decision_path=decision_path,
                manifest_path=manifest_path,
                image_path=image_path,
                media_type="still_image",
                live_presence_semantic_review=live_presence_semantic_review,
            )
            human_presence_output_qa_state = _completed_human_presence_output_qa_state(
                human_presence_artifact_path,
                human_presence_artifact,
            )
        except HumanPresenceOutputQAError as exc:
            human_presence_output_qa_state = _error_human_presence_output_qa_state(exc.code, str(exc))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            human_presence_output_qa_state = _error_human_presence_output_qa_state(
                "presence_output_qa_integration_error",
                str(exc),
            )
    retry_decision_artifact, retry_handoff_artifact = _retry_reference_artifacts(
        decision_artifact=decision_report,
        date_str=date_str,
        qa_artifact=qa_written_artifact,
    )

    if qa_status == "accept":
        qa_lifecycle_status = "qa_lifecycle_passed"
        next_allowed_action = "await_publish_authorization"
    elif retry_recommended:
        qa_lifecycle_status = "qa_lifecycle_retry_review_required"
        next_allowed_action = "retry_review_required"
    else:
        qa_lifecycle_status = "qa_lifecycle_failed"
        next_allowed_action = "review_generated_asset"

    report = {
        "report_type": LIFECYCLE_REPORT_TYPE,
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "date": date_str,
        "slot_id": slot_id,
        "recipe_id": recipe_id,
        "generated_at": iso_now(),
        "qa_lifecycle_status": qa_lifecycle_status,
        "blocking_reasons": [],
        "live_generation_accounting_artifact": repo_relative_path(accounting_path),
        "executor_result_manifest": repo_relative_path(manifest_path),
        "generated_output_paths": {
            "saved_image_path": repo_relative_path(image_path),
            "manifest_path": repo_relative_path(manifest_path),
        },
        "generation_claim_artifact": repo_relative_path(claim_path),
        "generation_receipt_artifact": repo_relative_path(receipt_path),
        "qa_disposition_artifact": repo_relative_path(qa_path),
        "human_presence_output_qa_state": human_presence_output_qa_state,
        "qa_status": qa_status,
        "retry_recommended": retry_recommended,
        "retry_decision_artifact": retry_decision_artifact,
        "retry_handoff_artifact": retry_handoff_artifact,
        "publish_authorized": False,
        "publish_performed": False,
        "queue_mutated": False,
        "next_allowed_action": next_allowed_action,
        "dirty_workspace_dependency": False,
        "provider_call_performed": False,
        "generation_performed": False,
        "side_effect_flags": {
            "provider_call_performed": False,
            "generation_performed": False,
            "qa_run": True,
            "retry_executed": False,
            "retry_handoff_written": False,
            "publish_performed": False,
            "queue_mutated": False,
            "claims_written": False,
            "receipts_written": False,
            "approval_consumed": False,
            "dirty_workspace_dependency": False,
        },
        "source_artifacts": {
            "live_generation_accounting": _source_record(accounting_path, report_type=accounting_report.get("report_type"), schema_version=accounting_report.get("schema_version")),
            "approval": _source_record(approval_artifact, report_type=approval_result.get("approval", {}).get("report_type"), schema_version=approval_result.get("approval", {}).get("schema_version")),
            "executor_result_manifest": _source_record(manifest_path),
            "generated_image": _source_record(image_path),
            "generation_claim": _source_record(claim_path),
            "generation_receipt": _source_record(receipt_path),
            "qa_disposition": _source_record(qa_path, report_type=qa_written_artifact.get("report_type"), schema_version=qa_written_artifact.get("schema_version")),
        },
        "linked_claim_artifact": actual_claim,
        "linked_receipt_artifact": actual_receipt,
    }
    _write_json_atomic(report_path(date_str, slot_id, lifecycle_output_root), report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only Lena generated-asset QA orchestration wrapper.")
    parser.add_argument("--live-generation-accounting-artifact", type=Path, required=True)
    parser.add_argument("--decision-artifact", type=Path, required=True)
    parser.add_argument("--identity-reference-authority-artifact", type=Path, required=True)
    parser.add_argument("--identity-reference-authority-sha256", required=True)
    parser.add_argument("--identity-reference", action="append", default=[], metavar="PATH::SHA256")
    parser.add_argument("--identity-evidence-artifact", type=Path)
    parser.add_argument("--qa-output-root", type=Path, default=qa_disposition.OUTPUT_ROOT)
    parser.add_argument("--lifecycle-output-root", type=Path, default=NEXT_ACTIONS)
    parser.add_argument("--live-presence-semantic-review", action="store_true")
    args = parser.parse_args()

    try:
        report = evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=args.live_generation_accounting_artifact,
            decision_artifact=args.decision_artifact,
            identity_reference_authority_artifact=args.identity_reference_authority_artifact,
            identity_reference_authority_sha256=args.identity_reference_authority_sha256,
            identity_references=[qa_disposition.parse_reference_spec(value) for value in args.identity_reference],
            identity_evidence_artifact=args.identity_evidence_artifact,
            qa_output_root=args.qa_output_root,
            lifecycle_output_root=args.lifecycle_output_root,
            live_presence_semantic_review=args.live_presence_semantic_review,
        )
    except GeneratedAssetQaLifecycleError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "ok": report["qa_lifecycle_status"] == "qa_lifecycle_passed",
                "report": report,
                "report_path": repo_relative_path(report_path(report["date"], report["slot_id"], args.lifecycle_output_root)),
            },
            indent=2,
        )
    )
    return 0 if report["qa_lifecycle_status"] == "qa_lifecycle_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
