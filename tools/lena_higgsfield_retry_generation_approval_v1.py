from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools import lena_higgsfield_generation_approval_v1 as canonical_approval
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "generation"

APPROVAL_REPORT_TYPE = "lena_higgsfield_retry_generation_approval"
APPROVAL_SCHEMA_VERSION = "v1"
APPROVAL_TYPE = "higgsfield_single_retry_generation"
CLAIM_REPORT_TYPE = "lena_higgsfield_retry_generation_claim"
CLAIM_SCHEMA_VERSION = "v1"
CLAIM_TYPE = "higgsfield_single_retry_generation_consumption_claim"
RECEIPT_REPORT_TYPE = "lena_higgsfield_retry_generation_execution_receipt"
RECEIPT_SCHEMA_VERSION = "v1"
RECEIPT_TYPE = "higgsfield_single_retry_generation_execution_receipt"
APPROVAL_TTL_MINUTES = canonical_approval.APPROVAL_TTL_MINUTES


class HiggsfieldRetryGenerationApprovalError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def approval_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_retry_generation_approval.json"


def claim_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_retry_generation_claim.json"


def receipt_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_retry_generation_execution_receipt.json"


def confirmation_phrase(slot_id: str) -> str:
    return (
        f"I approve one live Higgsfield retry generation attempt for slot {slot_id} "
        "and understand that credits may be spent."
    )


def repo_relative_path(path: Path) -> str:
    return canonical_approval.repo_relative_path(path)


def sha256_file(path: Path) -> str:
    return canonical_approval.sha256_file(path)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HiggsfieldRetryGenerationApprovalError(code, detail)


def _translate_retry_error(exc: retry_handoff.RetryHandoffError) -> HiggsfieldRetryGenerationApprovalError:
    return HiggsfieldRetryGenerationApprovalError(exc.code, exc.detail)


def _translate_canonical_error(
    exc: canonical_approval.HiggsfieldGenerationApprovalError,
) -> HiggsfieldRetryGenerationApprovalError:
    return HiggsfieldRetryGenerationApprovalError(exc.code, exc.detail)


def inspect_retry_handoff_artifact(retry_handoff_path: Path) -> dict[str, Any]:
    retry_handoff_path = retry_handoff_path.resolve()
    try:
        artifact = retry_handoff.validate_retry_handoff_artifact(retry_handoff_path)
    except retry_handoff.RetryHandoffError as exc:
        raise _translate_retry_error(exc) from exc

    return {
        "artifact": artifact,
        "retry_handoff_path": retry_handoff_path,
        "retry_handoff_repo_path": repo_relative_path(retry_handoff_path),
        "retry_handoff_sha256": sha256_file(retry_handoff_path),
        "date": str(artifact["date"]),
        "slot_id": str(artifact["retry_slot_id"]),
        "prompt_sha256": str(artifact["retry_prompt_sha256"]),
        "prompt_text": str(artifact["retry_prompt_text"]),
        "original_slot_id": str(artifact["original_slot_id"]),
        "source_handoff_artifact_path": str(artifact["source_handoff_artifact_path"]),
        "source_handoff_artifact_sha256": str(artifact["source_handoff_artifact_sha256"]),
        "source_execution_receipt_path": str(artifact["source_execution_receipt_path"]),
        "source_execution_receipt_sha256": str(artifact["source_execution_receipt_sha256"]),
        "provider": str(artifact["provider"]),
        "executor": str(artifact["executor"]),
        "model": str(artifact["model"]),
        "aspect_ratio": str(artifact["aspect_ratio"]),
        "custom_reference_id": str(artifact["custom_reference_id"]),
        "soul_name": str(artifact["soul_name"]),
        "soul_type": str(artifact["soul_type"]),
        "retry_handoff_fingerprint_sha256": str(artifact["retry_handoff_fingerprint_sha256"]),
        "expression_provenance_fingerprint_sha256": str(
            artifact["expression_provenance_fingerprint_sha256"]
        ),
    }


def build_retry_generation_approval_record(
    retry_facts: dict[str, Any],
    *,
    operator_id: str,
    confirmation: str,
    approved_at: datetime | None = None,
) -> dict[str, Any]:
    _require(
        operator_id == canonical_approval.CANONICAL_OPERATOR_ID,
        "approval_operator_mismatch",
        f"operator_id must be exactly {canonical_approval.CANONICAL_OPERATOR_ID!r}",
    )
    expected_confirmation = confirmation_phrase(retry_facts["slot_id"])
    _require(
        confirmation == expected_confirmation,
        "approval_confirmation_mismatch",
        "confirmation_statement did not exactly match the required retry approval phrase",
    )

    approved_at = (approved_at or utcnow()).astimezone(timezone.utc).replace(microsecond=0)
    expires_at = approved_at + timedelta(minutes=APPROVAL_TTL_MINUTES)
    artifact = retry_facts["artifact"]
    return {
        "report_type": APPROVAL_REPORT_TYPE,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_type": APPROVAL_TYPE,
        "operator_id": operator_id,
        "approved_at_utc": approved_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "retry_handoff_artifact_path": retry_facts["retry_handoff_repo_path"],
        "retry_handoff_artifact_sha256": retry_facts["retry_handoff_sha256"],
        "retry_handoff_report_type": artifact.get("report_type"),
        "retry_handoff_schema_version": artifact.get("schema_version"),
        "retry_handoff_fingerprint_sha256": retry_facts["retry_handoff_fingerprint_sha256"],
        "expression_provenance_fingerprint_sha256": retry_facts[
            "expression_provenance_fingerprint_sha256"
        ],
        "date": retry_facts["date"],
        "slot_id": retry_facts["slot_id"],
        "prompt_sha256": retry_facts["prompt_sha256"],
        "original_slot_id": retry_facts["original_slot_id"],
        "source_handoff_artifact_path": retry_facts["source_handoff_artifact_path"],
        "source_handoff_artifact_sha256": retry_facts["source_handoff_artifact_sha256"],
        "source_execution_receipt_path": retry_facts["source_execution_receipt_path"],
        "source_execution_receipt_sha256": retry_facts["source_execution_receipt_sha256"],
        "provider": retry_facts["provider"],
        "executor": retry_facts["executor"],
        "model": retry_facts["model"],
        "aspect_ratio": retry_facts["aspect_ratio"],
        "soul_name": retry_facts["soul_name"],
        "soul_type": retry_facts["soul_type"],
        "custom_reference_id": retry_facts["custom_reference_id"],
        "confirmation_statement": confirmation,
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "scheduling_authorized": False,
        "analytics_mutation_authorized": False,
        "immutability": "immutable_once_written",
        "authorization_identity_mode": "procedural_local_authorization_record_only",
    }


def validate_retry_generation_approval_artifact(
    approval_path: Path,
    *,
    now: datetime | None = None,
    require_not_expired: bool = True,
) -> dict[str, Any]:
    approval_path = approval_path.resolve()
    try:
        approval = canonical_approval.read_json_object(
            approval_path,
            code="approval_missing_or_invalid",
            label="Higgsfield retry generation approval artifact",
        )
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc

    _require(
        approval.get("report_type") == APPROVAL_REPORT_TYPE,
        "approval_report_type_mismatch",
        f"approval report_type must be {APPROVAL_REPORT_TYPE!r}",
    )
    _require(
        approval.get("schema_version") == APPROVAL_SCHEMA_VERSION,
        "approval_schema_version_mismatch",
        f"approval schema_version must be {APPROVAL_SCHEMA_VERSION!r}",
    )
    _require(
        approval.get("approval_type") == APPROVAL_TYPE,
        "approval_type_mismatch",
        f"approval approval_type must be {APPROVAL_TYPE!r}",
    )
    _require(
        approval.get("operator_id") == canonical_approval.CANONICAL_OPERATOR_ID,
        "approval_operator_mismatch",
        f"approval operator_id must be exactly {canonical_approval.CANONICAL_OPERATOR_ID!r}",
    )
    try:
        approved_at = canonical_approval.parse_iso8601_utc(
            approval.get("approved_at_utc"),
            code="approval_approved_at_invalid",
            label="approval approved_at_utc",
        )
        expires_at = canonical_approval.parse_iso8601_utc(
            approval.get("expires_at_utc"),
            code="approval_expires_at_invalid",
            label="approval expires_at_utc",
        )
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc
    _require(
        expires_at - approved_at == timedelta(minutes=APPROVAL_TTL_MINUTES),
        "approval_expiry_window_invalid",
        f"approval expires_at_utc must be exactly {APPROVAL_TTL_MINUTES} minutes after approved_at_utc",
    )
    now = (now or utcnow()).astimezone(timezone.utc)
    if require_not_expired:
        _require(now <= expires_at, "approval_expired", f"approval expired at {expires_at.isoformat()}")

    date_str = str(approval.get("date") or "").strip()
    slot_id = str(approval.get("slot_id") or "").strip()
    _require(bool(date_str), "approval_date_missing", "approval date is missing")
    _require(bool(slot_id), "approval_slot_missing", "approval slot_id is missing")
    try:
        prompt_sha = canonical_approval.require_sha256(
            approval.get("prompt_sha256"),
            code="approval_prompt_sha_missing_or_invalid",
            label="approval prompt_sha256",
        )
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc
    _require(
        approval.get("confirmation_statement") == confirmation_phrase(slot_id),
        "approval_confirmation_mismatch",
        "approval confirmation_statement did not exactly match the required retry approval phrase",
    )
    _require(
        approval.get("credits_may_be_spent_acknowledged") is True,
        "approval_credits_acknowledgement_missing",
        "approval must acknowledge that execution may spend credits",
    )
    _require(
        approval.get("authorized_attempts") == 1,
        "approval_authorized_attempts_invalid",
        "approval authorized_attempts must be exactly 1",
    )
    for key in (
        "upload_authorized",
        "queue_promotion_authorized",
        "publish_authorized",
        "scheduling_authorized",
        "analytics_mutation_authorized",
    ):
        _require(approval.get(key) is False, f"approval_scope_{key}_invalid", f"approval {key} must be false")

    retry_handoff_path = canonical_approval.resolve_repo_path(
        str(approval.get("retry_handoff_artifact_path") or ""),
        code="approval_retry_handoff_path_missing",
        label="approval retry_handoff_artifact_path",
    )
    retry_facts = inspect_retry_handoff_artifact(retry_handoff_path)
    _require(
        approval.get("retry_handoff_artifact_path") == retry_facts["retry_handoff_repo_path"],
        "approval_retry_handoff_path_binding_mismatch",
        "approval retry_handoff_artifact_path does not match the exact retry handoff repo-relative path",
    )
    try:
        retry_handoff_sha = canonical_approval.require_sha256(
            approval.get("retry_handoff_artifact_sha256"),
            code="approval_retry_handoff_sha_missing_or_invalid",
            label="approval retry_handoff_artifact_sha256",
        )
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc
    _require(
        retry_handoff_sha == retry_facts["retry_handoff_sha256"],
        "approval_retry_handoff_sha_mismatch",
        "approval retry_handoff_artifact_sha256 does not match the current retry handoff bytes",
    )
    _require(
        approval.get("retry_handoff_report_type") == retry_handoff.REPORT_TYPE,
        "approval_retry_handoff_report_type_mismatch",
        f"approval retry_handoff_report_type must be {retry_handoff.REPORT_TYPE!r}",
    )
    _require(
        approval.get("retry_handoff_schema_version") == retry_handoff.SCHEMA_VERSION,
        "approval_retry_handoff_schema_version_mismatch",
        f"approval retry_handoff_schema_version must be {retry_handoff.SCHEMA_VERSION!r}",
    )
    _require(
        approval.get("retry_handoff_fingerprint_sha256") == retry_facts["retry_handoff_fingerprint_sha256"],
        "approval_retry_handoff_fingerprint_mismatch",
        "approval retry_handoff_fingerprint_sha256 does not match the current retry handoff fingerprint",
    )
    _require(
        approval.get("expression_provenance_fingerprint_sha256")
        == retry_facts["expression_provenance_fingerprint_sha256"],
        "approval_expression_provenance_fingerprint_mismatch",
        "approval expression provenance fingerprint does not match the retry handoff",
    )
    _require(date_str == retry_facts["date"], "approval_date_binding_mismatch", "approval date does not match the bound retry handoff date")
    _require(slot_id == retry_facts["slot_id"], "approval_slot_binding_mismatch", "approval slot_id does not match the bound retry slot_id")
    _require(prompt_sha == retry_facts["prompt_sha256"], "approval_prompt_sha_mismatch", "approval prompt_sha256 does not match the bound retry prompt sha")
    _require(
        approval.get("original_slot_id") == retry_facts["original_slot_id"],
        "approval_original_slot_binding_mismatch",
        "approval original_slot_id does not match the bound original slot_id",
    )
    _require(
        approval.get("source_handoff_artifact_path") == retry_facts["source_handoff_artifact_path"],
        "approval_source_handoff_path_binding_mismatch",
        "approval source_handoff_artifact_path does not match the retry handoff lineage",
    )
    _require(
        approval.get("source_handoff_artifact_sha256") == retry_facts["source_handoff_artifact_sha256"],
        "approval_source_handoff_sha_mismatch",
        "approval source_handoff_artifact_sha256 does not match the retry handoff lineage",
    )
    _require(
        approval.get("source_execution_receipt_path") == retry_facts["source_execution_receipt_path"],
        "approval_source_execution_receipt_path_binding_mismatch",
        "approval source_execution_receipt_path does not match the retry handoff lineage",
    )
    _require(
        approval.get("source_execution_receipt_sha256") == retry_facts["source_execution_receipt_sha256"],
        "approval_source_execution_receipt_sha_mismatch",
        "approval source_execution_receipt_sha256 does not match the retry handoff lineage",
    )
    _require(
        approval.get("provider") == retry_facts["provider"],
        "approval_provider_mismatch",
        f"approval provider must be {retry_facts['provider']!r}",
    )
    _require(
        approval.get("executor") == retry_facts["executor"],
        "approval_executor_mismatch",
        f"approval executor must be {retry_facts['executor']!r}",
    )
    _require(
        approval.get("model") == retry_facts["model"],
        "approval_model_mismatch",
        f"approval model must be {retry_facts['model']!r}",
    )
    _require(
        approval.get("aspect_ratio") == retry_facts["aspect_ratio"],
        "approval_aspect_ratio_mismatch",
        f"approval aspect_ratio must be {retry_facts['aspect_ratio']!r}",
    )
    _require(
        approval.get("soul_name") == retry_facts["soul_name"],
        "approval_soul_name_mismatch",
        f"approval soul_name must be {retry_facts['soul_name']!r}",
    )
    _require(
        approval.get("soul_type") == retry_facts["soul_type"],
        "approval_soul_type_mismatch",
        f"approval soul_type must be {retry_facts['soul_type']!r}",
    )
    _require(
        approval.get("custom_reference_id") == retry_facts["custom_reference_id"],
        "approval_custom_reference_id_mismatch",
        "approval custom_reference_id does not match the bound retry handoff Soul reference",
    )

    return {
        "approval": approval,
        "approval_path": approval_path,
        "approval_repo_path": repo_relative_path(approval_path),
        "approval_sha256": sha256_file(approval_path),
        "retry_facts": retry_facts,
        "approved_at_utc": approved_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "is_expired": now > expires_at,
        "scope_summary": {
            "authorized_attempts": approval["authorized_attempts"],
            "upload_authorized": approval["upload_authorized"],
            "queue_promotion_authorized": approval["queue_promotion_authorized"],
            "publish_authorized": approval["publish_authorized"],
            "scheduling_authorized": approval["scheduling_authorized"],
            "analytics_mutation_authorized": approval["analytics_mutation_authorized"],
        },
    }


def build_retry_generation_claim_record(
    approval_result: dict[str, Any],
    *,
    claimed_at: datetime | None = None,
) -> dict[str, Any]:
    approval = approval_result["approval"]
    retry_facts = approval_result["retry_facts"]
    date_str = retry_facts["date"]
    slot_id = retry_facts["slot_id"]
    return {
        "report_type": CLAIM_REPORT_TYPE,
        "schema_version": CLAIM_SCHEMA_VERSION,
        "claim_type": CLAIM_TYPE,
        "claimed_at_utc": (claimed_at or utcnow()).astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "approval_artifact_path": approval_result["approval_repo_path"],
        "approval_artifact_sha256": approval_result["approval_sha256"],
        "retry_handoff_artifact_path": retry_facts["retry_handoff_repo_path"],
        "retry_handoff_artifact_sha256": retry_facts["retry_handoff_sha256"],
        "retry_handoff_fingerprint_sha256": retry_facts["retry_handoff_fingerprint_sha256"],
        "expression_provenance_fingerprint_sha256": retry_facts[
            "expression_provenance_fingerprint_sha256"
        ],
        "date": date_str,
        "slot_id": slot_id,
        "prompt_sha256": retry_facts["prompt_sha256"],
        "original_slot_id": retry_facts["original_slot_id"],
        "source_handoff_artifact_path": retry_facts["source_handoff_artifact_path"],
        "source_handoff_artifact_sha256": retry_facts["source_handoff_artifact_sha256"],
        "source_execution_receipt_path": retry_facts["source_execution_receipt_path"],
        "source_execution_receipt_sha256": retry_facts["source_execution_receipt_sha256"],
        "operator_id": approval["operator_id"],
        "provider": approval["provider"],
        "executor": approval["executor"],
        "model": approval["model"],
        "aspect_ratio": approval["aspect_ratio"],
        "soul_name": approval["soul_name"],
        "soul_type": approval["soul_type"],
        "custom_reference_id": approval["custom_reference_id"],
        "authorized_attempts": 1,
        "consumed_attempt_number": 1,
        "expected_manifest_path": repo_relative_path(canonical_approval.expected_manifest_path(date_str, slot_id)),
        "expected_output_directory": repo_relative_path(canonical_approval.expected_output_directory(date_str)),
        "expected_output_stem": canonical_approval.expected_output_stem(slot_id),
        "allowed_output_extensions": list(canonical_approval.ALLOWED_OUTPUT_EXTENSIONS),
        "state": "claimed_pending_receipt",
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "scheduling_authorized": False,
        "analytics_mutation_authorized": False,
    }


def build_retry_generation_execution_receipt_record(
    claim_path: Path,
    approval_result: dict[str, Any],
    *,
    outcome: str,
    failure_stage: str | None = None,
    error_text: str | None = None,
    subprocess_start_attempted: bool,
    provider_submission_may_have_occurred: bool,
    provider_job_id: str | None = None,
    provider_status: str | None = None,
    output_path: str | None = None,
    image_format_detected: str | None = None,
    actual_manifest_path: str | None = None,
    receipt_written_at: datetime | None = None,
) -> dict[str, Any]:
    approval = approval_result["approval"]
    retry_facts = approval_result["retry_facts"]
    date_str = retry_facts["date"]
    slot_id = retry_facts["slot_id"]
    claim_path = claim_path.resolve()
    return {
        "report_type": RECEIPT_REPORT_TYPE,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "receipt_written_at_utc": (receipt_written_at or utcnow()).astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "claim_artifact_path": repo_relative_path(claim_path),
        "claim_artifact_sha256": sha256_file(claim_path),
        "approval_artifact_path": approval_result["approval_repo_path"],
        "approval_artifact_sha256": approval_result["approval_sha256"],
        "retry_handoff_artifact_path": retry_facts["retry_handoff_repo_path"],
        "retry_handoff_artifact_sha256": retry_facts["retry_handoff_sha256"],
        "retry_handoff_fingerprint_sha256": retry_facts["retry_handoff_fingerprint_sha256"],
        "expression_provenance_fingerprint_sha256": retry_facts[
            "expression_provenance_fingerprint_sha256"
        ],
        "date": date_str,
        "slot_id": slot_id,
        "prompt_sha256": retry_facts["prompt_sha256"],
        "original_slot_id": retry_facts["original_slot_id"],
        "source_handoff_artifact_path": retry_facts["source_handoff_artifact_path"],
        "source_handoff_artifact_sha256": retry_facts["source_handoff_artifact_sha256"],
        "source_execution_receipt_path": retry_facts["source_execution_receipt_path"],
        "source_execution_receipt_sha256": retry_facts["source_execution_receipt_sha256"],
        "outcome": outcome,
        "failure_stage": failure_stage,
        "error_text": error_text,
        "subprocess_start_attempted": subprocess_start_attempted,
        "provider_submission_may_have_occurred": provider_submission_may_have_occurred,
        "provider_job_id": provider_job_id,
        "provider_status": provider_status,
        "output_path": output_path,
        "image_format_detected": image_format_detected,
        "expected_manifest_path": repo_relative_path(canonical_approval.expected_manifest_path(date_str, slot_id)),
        "actual_manifest_path": actual_manifest_path,
        "operator_id": approval["operator_id"],
        "provider": approval["provider"],
        "executor": approval["executor"],
        "model": approval["model"],
        "aspect_ratio": approval["aspect_ratio"],
        "soul_name": approval["soul_name"],
        "soul_type": approval["soul_type"],
        "custom_reference_id": approval["custom_reference_id"],
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "scheduling_authorized": False,
        "analytics_mutation_authorized": False,
    }


def _write_immutable_record_atomic(
    path: Path,
    record: dict[str, Any],
    *,
    error_code: str,
    error_label: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    try:
        temp_path.write_text(payload, encoding="utf-8")
        os.link(str(temp_path), str(path))
    except FileExistsError as exc:
        raise HiggsfieldRetryGenerationApprovalError(
            error_code,
            f"refusing to overwrite an existing {error_label}: {path}",
        ) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_retry_generation_approval_record_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise HiggsfieldRetryGenerationApprovalError(
            "approval_already_exists",
            f"refusing to overwrite an existing retry approval artifact: {path}",
        )
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    try:
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def write_retry_generation_claim_atomic(path: Path, record: dict[str, Any]) -> None:
    _write_immutable_record_atomic(
        path,
        record,
        error_code="retry_generation_claim_already_exists",
        error_label="retry generation claim artifact",
    )


def write_retry_generation_execution_receipt_atomic(path: Path, record: dict[str, Any]) -> None:
    _write_immutable_record_atomic(
        path,
        record,
        error_code="retry_generation_execution_receipt_already_exists",
        error_label="retry generation execution receipt artifact",
    )
