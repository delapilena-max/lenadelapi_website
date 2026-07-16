from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from pipeline.influencer_nodes.lena import autonomy_ladder  # noqa: E402

DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "generation"

APPROVAL_REPORT_TYPE = "lena_higgsfield_generation_approval"
APPROVAL_SCHEMA_VERSION = "v1"
APPROVAL_TYPE = "higgsfield_single_generation"
CLAIM_REPORT_TYPE = "lena_higgsfield_generation_claim"
CLAIM_SCHEMA_VERSION = "v1"
CLAIM_TYPE = "higgsfield_single_generation_consumption_claim"
RECEIPT_REPORT_TYPE = "lena_higgsfield_generation_execution_receipt"
RECEIPT_SCHEMA_VERSION = "v1"
RECEIPT_TYPE = "higgsfield_single_generation_execution_receipt"
HANDOFF_REPORT_TYPE = "lena_next_live_image_handoff"
HANDOFF_SCHEMA_VERSION = "v1"
SELECTED_CANDIDATE_REPORT_TYPE = "lena_pre_generation_candidate_gate_v1"
SELECTED_CANDIDATE_SCHEMA_VERSION = "lena_pre_generation_candidate_gate_v1"
HANDOFF_EXECUTION_OWNER = "claude"
HANDOFF_PROVIDER = "higgsfield"
HANDOFF_EXECUTOR_TYPE = "higgsfield_cli"
REPO_EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
ALLOWED_OUTPUT_EXTENSIONS = (".png", ".jpg", ".webp", ".bin")

CANONICAL_OPERATOR_ID = "nicolas"
APPROVAL_PROVIDER = "Higgsfield"
APPROVAL_EXECUTOR = "Higgsfield CLI repo adapter"
MODEL = "text2image_soul_v2"
ASPECT_RATIO = "9:16"
SOUL_NAME = "Lena"
SOUL_TYPE = "Soul 2.0"
APPROVAL_TTL_MINUTES = 30

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HiggsfieldGenerationApprovalError(RuntimeError):
    """Fail-closed error for Higgsfield generation approval validation."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def approval_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_generation_approval.json"


def claim_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_generation_claim.json"


def receipt_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_generation_execution_receipt.json"


def confirmation_phrase(slot_id: str) -> str:
    return (
        f"I approve one live Higgsfield generation attempt for slot {slot_id} "
        "and understand that credits may be spent."
    )


def repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_repo_path(path_value: str, *, code: str, label: str) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise HiggsfieldGenerationApprovalError(code, f"{label} is missing")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_manifest_path(date_str: str, slot_id: str) -> Path:
    return ROOT / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"


def expected_output_directory(date_str: str) -> Path:
    return ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str


def expected_output_stem(slot_id: str) -> str:
    return f"{slot_id}_seed"


def read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise HiggsfieldGenerationApprovalError(code, f"{label} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HiggsfieldGenerationApprovalError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HiggsfieldGenerationApprovalError(code, f"{label} must be a JSON object: {path}")
    return payload


def parse_iso8601_utc(raw: Any, *, code: str, label: str) -> datetime:
    text = str(raw or "").strip()
    if not text:
        raise HiggsfieldGenerationApprovalError(code, f"{label} is missing")
    normalized = text.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HiggsfieldGenerationApprovalError(code, f"{label} is not a valid ISO-8601 timestamp: {text!r}") from exc
    if value.tzinfo is None:
        raise HiggsfieldGenerationApprovalError(code, f"{label} must include a UTC offset: {text!r}")
    return value.astimezone(timezone.utc)


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HiggsfieldGenerationApprovalError(code, detail)


def require_sha256(raw: Any, *, code: str, label: str) -> str:
    value = str(raw or "")
    if not SHA256_RE.fullmatch(value):
        raise HiggsfieldGenerationApprovalError(code, f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def inspect_handoff_artifact(handoff_path: Path) -> dict[str, Any]:
    handoff_path = handoff_path.resolve()
    report = read_json_object(
        handoff_path,
        code="handoff_missing_or_invalid",
        label="Higgsfield handoff artifact",
    )
    require(
        report.get("report_type") == HANDOFF_REPORT_TYPE,
        "handoff_report_type_mismatch",
        f"handoff report_type must be {HANDOFF_REPORT_TYPE!r}",
    )
    require(
        report.get("schema_version") == HANDOFF_SCHEMA_VERSION,
        "handoff_schema_version_mismatch",
        f"handoff schema_version must be {HANDOFF_SCHEMA_VERSION!r}",
    )
    require(
        report.get("execution_owner") == HANDOFF_EXECUTION_OWNER,
        "handoff_execution_owner_mismatch",
        f"handoff execution_owner must be {HANDOFF_EXECUTION_OWNER!r}",
    )
    require(
        report.get("provider") == HANDOFF_PROVIDER,
        "handoff_provider_mismatch",
        f"handoff provider must be {HANDOFF_PROVIDER!r}",
    )
    require(
        report.get("executor_type") == HANDOFF_EXECUTOR_TYPE,
        "handoff_executor_type_mismatch",
        f"handoff executor_type must be {HANDOFF_EXECUTOR_TYPE!r}",
    )
    require(
        report.get("repo_executor_path") == REPO_EXECUTOR_PATH,
        "handoff_repo_executor_path_mismatch",
        f"handoff repo_executor_path must be {REPO_EXECUTOR_PATH!r}",
    )
    require(
        report.get("packet_state") == "packet_valid_for_claude_review",
        "handoff_not_review_ready",
        "handoff packet_state must remain review-only",
    )
    require(
        report.get("dry_run_executor_contract_state") == "ready",
        "handoff_contract_state_invalid",
        "handoff dry_run_executor_contract_state must be 'ready'",
    )
    require(
        report.get("live_execution_state") == "blocked",
        "handoff_live_state_invalid",
        "handoff live_execution_state must remain 'blocked'",
    )
    require(
        report.get("live_execution_authorized") is False,
        "handoff_live_authorization_invalid",
        "handoff must not authorize live execution",
    )
    require(
        report.get("generation_approval_required") is True,
        "handoff_generation_approval_flag_invalid",
        "handoff must require generation approval",
    )
    require(
        report.get("manual_operator_approval_required") is True,
        "handoff_manual_operator_approval_flag_invalid",
        "handoff must require manual operator approval",
    )
    require(
        report.get("provider_call_performed") is False,
        "handoff_provider_call_invalid",
        "handoff must not claim a provider call was performed",
    )
    require(
        report.get("generation_performed") is False,
        "handoff_generation_performed_invalid",
        "handoff must not claim generation was performed",
    )
    require(
        report.get("publish_authorized") is False,
        "handoff_publish_authorized_invalid",
        "handoff must not authorize publish",
    )
    require(
        report.get("manual_publish_review_required") is True,
        "handoff_manual_publish_review_invalid",
        "handoff must keep manual publish review required",
    )
    parse_iso8601_utc(report.get("created_at"), code="handoff_created_at_invalid", label="handoff created_at")

    selected_candidate_binding = validate_selected_candidate_binding(report)
    selected_candidate_path = selected_candidate_binding["selected_candidate_path"]
    selected_candidate_sha_value = selected_candidate_binding["selected_candidate_sha256"]
    selected_candidate = selected_candidate_binding["selected_candidate"]

    structured = report.get("structured_executor_inputs")
    require(
        isinstance(structured, dict),
        "handoff_executor_inputs_missing",
        "handoff structured_executor_inputs must be a JSON object",
    )
    require(
        structured.get("provider") == HANDOFF_PROVIDER,
        "handoff_structured_provider_mismatch",
        f"handoff structured provider must be {HANDOFF_PROVIDER!r}",
    )
    require(
        structured.get("executor_type") == HANDOFF_EXECUTOR_TYPE,
        "handoff_structured_executor_type_mismatch",
        f"handoff structured executor_type must be {HANDOFF_EXECUTOR_TYPE!r}",
    )
    require(
        structured.get("repo_executor_path") == REPO_EXECUTOR_PATH,
        "handoff_structured_executor_path_mismatch",
        f"handoff structured repo_executor_path must be {REPO_EXECUTOR_PATH!r}",
    )
    require(
        structured.get("model") == MODEL,
        "handoff_model_mismatch",
        f"handoff model must be {MODEL!r}",
    )
    require(
        structured.get("aspect_ratio") == ASPECT_RATIO,
        "handoff_aspect_ratio_mismatch",
        f"handoff aspect_ratio must be {ASPECT_RATIO!r}",
    )
    require(
        structured.get("negative_prompt_enabled") is False,
        "handoff_negative_prompt_invalid",
        "handoff must keep negative_prompt_enabled false",
    )
    require(
        structured.get("live_execution_authorized") is False,
        "handoff_structured_live_authorization_invalid",
        "handoff structured inputs must not authorize live execution",
    )

    slot_id = str(report.get("selected_slot_id") or "").strip()
    date_str = str(report.get("date") or "").strip()
    require(slot_id, "handoff_slot_missing", "handoff selected_slot_id is missing")
    require(date_str, "handoff_date_missing", "handoff date is missing")
    require(
        structured.get("date") == date_str,
        "handoff_structured_date_mismatch",
        "handoff structured date does not match report date",
    )
    require(
        structured.get("slot_id") == slot_id,
        "handoff_structured_slot_mismatch",
        "handoff structured slot_id does not match report slot_id",
    )

    handoff_repo_path = repo_relative_path(handoff_path)
    require(
        report.get("expected_handoff_artifact_path") == handoff_repo_path,
        "handoff_path_binding_mismatch",
        "handoff expected_handoff_artifact_path does not match the exact handoff path",
    )
    require(
        structured.get("handoff_artifact_path") == handoff_repo_path,
        "handoff_structured_path_binding_mismatch",
        "handoff structured handoff_artifact_path does not match the exact handoff path",
    )

    soul = structured.get("soul_metadata")
    require(isinstance(soul, dict), "handoff_soul_metadata_missing", "handoff soul_metadata must be a JSON object")
    require(
        soul.get("name") == SOUL_NAME,
        "handoff_soul_name_mismatch",
        f"handoff soul name must be {SOUL_NAME!r}",
    )
    require(
        soul.get("type") == SOUL_TYPE,
        "handoff_soul_type_mismatch",
        f"handoff soul type must be {SOUL_TYPE!r}",
    )
    custom_reference_id = str(soul.get("custom_reference_id") or "").strip()
    require(custom_reference_id, "handoff_custom_reference_id_missing", "handoff custom_reference_id is missing")
    require(
        soul.get("identity_is_prompt_instruction") is False,
        "handoff_soul_identity_mode_invalid",
        "handoff Soul identity must remain metadata, not prompt text",
    )

    prompt_sha = require_sha256(
        structured.get("selected_prompt_sha256"),
        code="handoff_prompt_sha_missing_or_invalid",
        label="handoff structured selected_prompt_sha256",
    )
    selected_prompt = report.get("selected_prompt_input")
    require(
        isinstance(selected_prompt, dict),
        "handoff_selected_prompt_input_missing",
        "handoff selected_prompt_input must be a JSON object",
    )
    require(
        selected_prompt.get("prompt_sha256") == prompt_sha,
        "handoff_prompt_sha_binding_mismatch",
        "handoff selected_prompt_input.prompt_sha256 does not match structured selected_prompt_sha256",
    )
    require_sha256(
        report.get("selected_prompt_input_artifact_sha256"),
        code="handoff_candidate_artifact_sha_missing_or_invalid",
        label="handoff selected_prompt_input_artifact_sha256",
    )

    return {
        "report": report,
        "handoff_path": handoff_path,
        "handoff_repo_path": handoff_repo_path,
        "handoff_sha256": sha256_file(handoff_path),
        "date": date_str,
        "slot_id": slot_id,
        "prompt_sha256": prompt_sha,
        "custom_reference_id": custom_reference_id,
        "soul_name": soul.get("name"),
        "soul_type": soul.get("type"),
        "selected_candidate_path": selected_candidate_path,
        "selected_candidate_repo_path": repo_relative_path(selected_candidate_path) if selected_candidate_path else "",
        "selected_candidate_sha256": selected_candidate_sha_value,
        "selected_candidate": selected_candidate,
        "selected_candidate_id": selected_candidate_binding["selected_candidate_id"],
        "selected_candidate_slot_id": selected_candidate_binding["selected_candidate_slot_id"],
        "selected_candidate_recipe_id": selected_candidate_binding["selected_candidate_recipe_id"],
        "selected_candidate_prompt_sha256": selected_candidate_binding["selected_candidate_prompt_sha256"],
    }


def validate_selected_candidate_binding(report: dict[str, Any]) -> dict[str, Any]:
    selected_recipe_id = str(report.get("selected_recipe_id") or "").strip()
    require(
        selected_recipe_id,
        "handoff_selected_candidate_provenance_missing",
        "handoff selected_recipe_id is missing",
    )

    selected_candidate_binding = report.get("selected_candidate")
    require(
        isinstance(selected_candidate_binding, dict),
        "handoff_selected_candidate_provenance_missing",
        "handoff selected_candidate must be a JSON object",
    )

    selected_candidate_path_value = str(report.get("source_selected_candidate_artifact_path") or "").strip()
    selected_candidate_sha_value = str(report.get("source_selected_candidate_artifact_sha256") or "").strip()
    require(
        selected_candidate_path_value,
        "handoff_selected_candidate_path_missing",
        "handoff source_selected_candidate_artifact_path is missing",
    )
    require(
        selected_candidate_sha_value,
        "handoff_selected_candidate_sha_missing",
        "handoff source_selected_candidate_artifact_sha256 is missing",
    )
    require(
        str(selected_candidate_binding.get("artifact_path", "")).strip() == selected_candidate_path_value,
        "handoff_selected_candidate_binding_mismatch",
        "handoff selected_candidate.artifact_path must match source_selected_candidate_artifact_path",
    )
    require(
        str(selected_candidate_binding.get("artifact_sha256", "")).strip() == selected_candidate_sha_value,
        "handoff_selected_candidate_sha_binding_mismatch",
        "handoff selected_candidate.artifact_sha256 must match source_selected_candidate_artifact_sha256",
    )

    selected_candidate_path = resolve_repo_path(
        selected_candidate_path_value,
        code="handoff_selected_candidate_path_invalid",
        label="handoff source_selected_candidate_artifact_path",
    )
    selected_candidate = read_json_object(
        selected_candidate_path,
        code="handoff_selected_candidate_missing_or_invalid",
        label="selected candidate artifact",
    )
    require_sha256(
        selected_candidate_sha_value,
        code="handoff_selected_candidate_sha_invalid",
        label="handoff source_selected_candidate_artifact_sha256",
    )
    require(
        sha256_file(selected_candidate_path) == selected_candidate_sha_value,
        "handoff_selected_candidate_sha_mismatch",
        "handoff selected candidate artifact sha256 does not match current bytes",
    )
    require(
        selected_candidate.get("schema_version") == SELECTED_CANDIDATE_SCHEMA_VERSION,
        "handoff_selected_candidate_schema_mismatch",
        f"selected candidate schema_version must be {SELECTED_CANDIDATE_SCHEMA_VERSION!r}",
    )
    require(
        selected_candidate.get("candidate_status") == "selected",
        "handoff_selected_candidate_status_invalid",
        "selected candidate artifact must remain selected",
    )
    selected_candidate_body = selected_candidate.get("candidate")
    require(
        isinstance(selected_candidate_body, dict),
        "handoff_selected_candidate_body_missing",
        "selected candidate artifact must contain a candidate object",
    )
    require(
        str(selected_candidate_body.get("candidate_id", "")).strip()
        == str(selected_candidate_binding.get("candidate_id", "")).strip(),
        "handoff_selected_candidate_id_mismatch",
        "selected candidate candidate_id does not match the handoff snapshot",
    )
    require(
        str(selected_candidate_body.get("slot_id", "")).strip()
        == str(selected_candidate_binding.get("slot_id", "")).strip(),
        "handoff_selected_candidate_slot_mismatch",
        "selected candidate slot_id does not match the handoff snapshot",
    )
    require(
        str(selected_candidate_body.get("recipe_id", "")).strip() == selected_recipe_id,
        "handoff_selected_candidate_recipe_mismatch",
        "selected candidate recipe_id does not match the handoff recipe_id",
    )
    require(
        str(selected_candidate_body.get("prompt_sha256", "")).strip()
        == str(selected_candidate_binding.get("prompt_sha256", "")).strip(),
        "handoff_selected_candidate_prompt_sha_mismatch",
        "selected candidate prompt_sha256 does not match the handoff snapshot",
    )
    require(
        str(selected_candidate_binding.get("schema_version", "")).strip() == SELECTED_CANDIDATE_SCHEMA_VERSION,
        "handoff_selected_candidate_snapshot_schema_mismatch",
        f"handoff selected_candidate.schema_version must be {SELECTED_CANDIDATE_SCHEMA_VERSION!r}",
    )
    require(
        str(selected_candidate_binding.get("candidate_status", "")).strip() == "selected",
        "handoff_selected_candidate_snapshot_status_invalid",
        "handoff selected_candidate.candidate_status must remain selected",
    )

    selected_prompt_input = report.get("selected_prompt_input")
    require(
        isinstance(selected_prompt_input, dict),
        "handoff_selected_prompt_input_missing",
        "handoff selected_prompt_input must be a JSON object",
    )
    structured_preview = report.get("structured_executor_inputs")
    require(
        isinstance(structured_preview, dict),
        "handoff_executor_inputs_missing",
        "handoff structured_executor_inputs must be a JSON object",
    )
    require(
        str(selected_prompt_input.get("selected_candidate_artifact_path", "")).strip() == selected_candidate_path_value,
        "handoff_selected_candidate_binding_mismatch",
        "handoff selected_prompt_input.selected_candidate_artifact_path must match the selected candidate artifact",
    )
    require(
        str(selected_prompt_input.get("selected_candidate_artifact_sha256", "")).strip() == selected_candidate_sha_value,
        "handoff_selected_candidate_sha_binding_mismatch",
        "handoff selected_prompt_input.selected_candidate_artifact_sha256 must match the selected candidate artifact sha256",
    )
    require(
        str(structured_preview.get("selected_candidate_artifact_path", "")).strip() == selected_candidate_path_value,
        "handoff_structured_selected_candidate_binding_mismatch",
        "handoff structured_executor_inputs.selected_candidate_artifact_path must match the selected candidate artifact",
    )
    require(
        str(structured_preview.get("selected_candidate_artifact_sha256", "")).strip() == selected_candidate_sha_value,
        "handoff_structured_selected_candidate_sha_mismatch",
        "handoff structured_executor_inputs.selected_candidate_artifact_sha256 must match the selected candidate artifact sha256",
    )

    return {
        "selected_candidate_path": selected_candidate_path,
        "selected_candidate_sha256": selected_candidate_sha_value,
        "selected_candidate": selected_candidate,
        "selected_candidate_id": str(selected_candidate_body.get("candidate_id", "")).strip(),
        "selected_candidate_slot_id": str(selected_candidate_body.get("slot_id", "")).strip(),
        "selected_candidate_recipe_id": str(selected_candidate_body.get("recipe_id", "")).strip(),
        "selected_candidate_prompt_sha256": str(selected_candidate_body.get("prompt_sha256", "")).strip(),
    }


def build_generation_approval_record(
    handoff_facts: dict[str, Any],
    *,
    operator_id: str,
    confirmation: str,
    approved_at: datetime | None = None,
) -> dict[str, Any]:
    try:
        autonomy_ladder.assert_allowed(
            "lena_higgsfield_generation_approval_v1",
            level=2,
            action="explicit per-slot human approval consumption",
        )
    except autonomy_ladder.AutonomyLadderError as exc:
        raise HiggsfieldGenerationApprovalError(exc.code, exc.detail) from exc

    require(
        operator_id == CANONICAL_OPERATOR_ID,
        "approval_operator_mismatch",
        f"operator_id must be exactly {CANONICAL_OPERATOR_ID!r}",
    )
    expected_confirmation = confirmation_phrase(handoff_facts["slot_id"])
    require(
        confirmation == expected_confirmation,
        "approval_confirmation_mismatch",
        "confirmation_statement did not exactly match the required approval phrase",
    )

    approved_at = approved_at or utcnow()
    approved_at = approved_at.astimezone(timezone.utc).replace(microsecond=0)
    expires_at = approved_at + timedelta(minutes=APPROVAL_TTL_MINUTES)
    report = handoff_facts["report"]
    return {
        "report_type": APPROVAL_REPORT_TYPE,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_type": APPROVAL_TYPE,
        "operator_id": operator_id,
        "approved_at_utc": approved_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "handoff_artifact_path": handoff_facts["handoff_repo_path"],
        "handoff_artifact_sha256": handoff_facts["handoff_sha256"],
        "handoff_report_type": report.get("report_type"),
        "handoff_schema_version": report.get("schema_version"),
        "date": handoff_facts["date"],
        "slot_id": handoff_facts["slot_id"],
        "prompt_sha256": handoff_facts["prompt_sha256"],
        "provider": APPROVAL_PROVIDER,
        "executor": APPROVAL_EXECUTOR,
        "model": MODEL,
        "aspect_ratio": ASPECT_RATIO,
        "soul_name": handoff_facts["soul_name"],
        "soul_type": handoff_facts["soul_type"],
        "custom_reference_id": handoff_facts["custom_reference_id"],
        "confirmation_statement": confirmation,
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
        "immutability": "immutable_once_written",
        "authorization_identity_mode": "procedural_local_authorization_record_only",
    }


def validate_generation_approval_artifact(
    approval_path: Path,
    *,
    now: datetime | None = None,
    require_not_expired: bool = True,
) -> dict[str, Any]:
    try:
        autonomy_ladder.assert_allowed(
            "lena_higgsfield_generation_approval_v1",
            level=2,
            action="explicit per-slot human approval consumption",
        )
    except autonomy_ladder.AutonomyLadderError as exc:
        raise HiggsfieldGenerationApprovalError(exc.code, exc.detail) from exc

    approval_path = approval_path.resolve()
    approval = read_json_object(
        approval_path,
        code="approval_missing_or_invalid",
        label="Higgsfield generation approval artifact",
    )
    require(
        approval.get("report_type") == APPROVAL_REPORT_TYPE,
        "approval_report_type_mismatch",
        f"approval report_type must be {APPROVAL_REPORT_TYPE!r}",
    )
    require(
        approval.get("schema_version") == APPROVAL_SCHEMA_VERSION,
        "approval_schema_version_mismatch",
        f"approval schema_version must be {APPROVAL_SCHEMA_VERSION!r}",
    )
    require(
        approval.get("approval_type") == APPROVAL_TYPE,
        "approval_type_mismatch",
        f"approval approval_type must be {APPROVAL_TYPE!r}",
    )
    require(
        approval.get("operator_id") == CANONICAL_OPERATOR_ID,
        "approval_operator_mismatch",
        f"approval operator_id must be exactly {CANONICAL_OPERATOR_ID!r}",
    )
    approved_at = parse_iso8601_utc(
        approval.get("approved_at_utc"),
        code="approval_approved_at_invalid",
        label="approval approved_at_utc",
    )
    expires_at = parse_iso8601_utc(
        approval.get("expires_at_utc"),
        code="approval_expires_at_invalid",
        label="approval expires_at_utc",
    )
    require(
        expires_at - approved_at == timedelta(minutes=APPROVAL_TTL_MINUTES),
        "approval_expiry_window_invalid",
        f"approval expires_at_utc must be exactly {APPROVAL_TTL_MINUTES} minutes after approved_at_utc",
    )
    now = (now or utcnow()).astimezone(timezone.utc)
    if require_not_expired:
        require(
            now <= expires_at,
            "approval_expired",
            f"approval expired at {expires_at.isoformat()}",
        )

    date_str = str(approval.get("date") or "").strip()
    slot_id = str(approval.get("slot_id") or "").strip()
    require(date_str, "approval_date_missing", "approval date is missing")
    require(slot_id, "approval_slot_missing", "approval slot_id is missing")
    require(
        approval.get("provider") == APPROVAL_PROVIDER,
        "approval_provider_mismatch",
        f"approval provider must be {APPROVAL_PROVIDER!r}",
    )
    require(
        approval.get("executor") == APPROVAL_EXECUTOR,
        "approval_executor_mismatch",
        f"approval executor must be {APPROVAL_EXECUTOR!r}",
    )
    require(
        approval.get("model") == MODEL,
        "approval_model_mismatch",
        f"approval model must be {MODEL!r}",
    )
    require(
        approval.get("aspect_ratio") == ASPECT_RATIO,
        "approval_aspect_ratio_mismatch",
        f"approval aspect_ratio must be {ASPECT_RATIO!r}",
    )
    require(
        approval.get("soul_name") == SOUL_NAME,
        "approval_soul_name_mismatch",
        f"approval soul_name must be {SOUL_NAME!r}",
    )
    require(
        approval.get("soul_type") == SOUL_TYPE,
        "approval_soul_type_mismatch",
        f"approval soul_type must be {SOUL_TYPE!r}",
    )
    custom_reference_id = str(approval.get("custom_reference_id") or "").strip()
    require(custom_reference_id, "approval_custom_reference_id_missing", "approval custom_reference_id is missing")
    prompt_sha = require_sha256(
        approval.get("prompt_sha256"),
        code="approval_prompt_sha_missing_or_invalid",
        label="approval prompt_sha256",
    )
    expected_confirmation = confirmation_phrase(slot_id)
    require(
        approval.get("confirmation_statement") == expected_confirmation,
        "approval_confirmation_mismatch",
        "approval confirmation_statement did not exactly match the required phrase",
    )
    require(
        approval.get("credits_may_be_spent_acknowledged") is True,
        "approval_credits_acknowledgement_missing",
        "approval must acknowledge that execution may spend credits",
    )
    require(
        approval.get("authorized_attempts") == 1,
        "approval_authorized_attempts_invalid",
        "approval authorized_attempts must be exactly 1",
    )
    for key in (
        "upload_authorized",
        "queue_promotion_authorized",
        "publish_authorized",
        "analytics_mutation_authorized",
    ):
        require(
            approval.get(key) is False,
            f"approval_scope_{key}_invalid",
            f"approval {key} must be false",
        )

    handoff_path = resolve_repo_path(
        str(approval.get("handoff_artifact_path") or ""),
        code="approval_handoff_path_missing",
        label="approval handoff_artifact_path",
    )
    handoff_facts = inspect_handoff_artifact(handoff_path)
    require(
        approval.get("handoff_artifact_path") == handoff_facts["handoff_repo_path"],
        "approval_handoff_path_binding_mismatch",
        "approval handoff_artifact_path does not match the exact handoff repo-relative path",
    )
    handoff_sha = require_sha256(
        approval.get("handoff_artifact_sha256"),
        code="approval_handoff_sha_missing_or_invalid",
        label="approval handoff_artifact_sha256",
    )
    require(
        handoff_sha == handoff_facts["handoff_sha256"],
        "approval_handoff_sha_mismatch",
        "approval handoff_artifact_sha256 does not match the current handoff bytes",
    )
    require(
        approval.get("handoff_report_type") == HANDOFF_REPORT_TYPE,
        "approval_handoff_report_type_mismatch",
        f"approval handoff_report_type must be {HANDOFF_REPORT_TYPE!r}",
    )
    require(
        approval.get("handoff_schema_version") == HANDOFF_SCHEMA_VERSION,
        "approval_handoff_schema_version_mismatch",
        f"approval handoff_schema_version must be {HANDOFF_SCHEMA_VERSION!r}",
    )
    require(
        date_str == handoff_facts["date"],
        "approval_date_binding_mismatch",
        "approval date does not match the bound handoff date",
    )
    require(
        slot_id == handoff_facts["slot_id"],
        "approval_slot_binding_mismatch",
        "approval slot_id does not match the bound handoff slot_id",
    )
    require(
        prompt_sha == handoff_facts["prompt_sha256"],
        "approval_prompt_sha_mismatch",
        "approval prompt_sha256 does not match the bound handoff prompt sha",
    )
    require(
        custom_reference_id == handoff_facts["custom_reference_id"],
        "approval_custom_reference_id_mismatch",
        "approval custom_reference_id does not match the bound handoff Soul reference",
    )

    return {
        "approval": approval,
        "approval_path": approval_path,
        "approval_repo_path": repo_relative_path(approval_path),
        "approval_sha256": sha256_file(approval_path),
        "handoff_facts": handoff_facts,
        "approved_at_utc": approved_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "is_expired": now > expires_at,
        "scope_summary": {
            "authorized_attempts": approval["authorized_attempts"],
            "upload_authorized": approval["upload_authorized"],
            "queue_promotion_authorized": approval["queue_promotion_authorized"],
            "publish_authorized": approval["publish_authorized"],
            "analytics_mutation_authorized": approval["analytics_mutation_authorized"],
        },
    }


def build_generation_claim_record(
    approval_result: dict[str, Any],
    *,
    claimed_at: datetime | None = None,
) -> dict[str, Any]:
    approval = approval_result["approval"]
    handoff_facts = approval_result["handoff_facts"]
    date_str = handoff_facts["date"]
    slot_id = handoff_facts["slot_id"]
    return {
        "report_type": CLAIM_REPORT_TYPE,
        "schema_version": CLAIM_SCHEMA_VERSION,
        "claim_type": CLAIM_TYPE,
        "claimed_at_utc": (claimed_at or utcnow()).astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "approval_artifact_path": approval_result["approval_repo_path"],
        "approval_artifact_sha256": approval_result["approval_sha256"],
        "handoff_artifact_path": handoff_facts["handoff_repo_path"],
        "handoff_artifact_sha256": handoff_facts["handoff_sha256"],
        "date": date_str,
        "slot_id": slot_id,
        "prompt_sha256": handoff_facts["prompt_sha256"],
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
        "expected_manifest_path": repo_relative_path(expected_manifest_path(date_str, slot_id)),
        "expected_output_directory": repo_relative_path(expected_output_directory(date_str)),
        "expected_output_stem": expected_output_stem(slot_id),
        "allowed_output_extensions": list(ALLOWED_OUTPUT_EXTENSIONS),
        "state": "claimed_pending_receipt",
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }


def build_generation_execution_receipt_record(
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
    handoff_facts = approval_result["handoff_facts"]
    date_str = handoff_facts["date"]
    slot_id = handoff_facts["slot_id"]
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
        "handoff_artifact_path": handoff_facts["handoff_repo_path"],
        "handoff_artifact_sha256": handoff_facts["handoff_sha256"],
        "date": date_str,
        "slot_id": slot_id,
        "prompt_sha256": handoff_facts["prompt_sha256"],
        "outcome": outcome,
        "failure_stage": failure_stage,
        "error_text": error_text,
        "subprocess_start_attempted": subprocess_start_attempted,
        "provider_submission_may_have_occurred": provider_submission_may_have_occurred,
        "provider_job_id": provider_job_id,
        "provider_status": provider_status,
        "output_path": output_path,
        "image_format_detected": image_format_detected,
        "expected_manifest_path": repo_relative_path(expected_manifest_path(date_str, slot_id)),
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
        raise HiggsfieldGenerationApprovalError(
            error_code,
            f"refusing to overwrite an existing {error_label}: {path}",
        ) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_approval_record_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise HiggsfieldGenerationApprovalError(
            "approval_already_exists",
            f"refusing to overwrite an existing approval artifact: {path}",
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


def write_generation_claim_atomic(path: Path, record: dict[str, Any]) -> None:
    _write_immutable_record_atomic(
        path,
        record,
        error_code="generation_claim_already_exists",
        error_label="generation claim artifact",
    )


def write_generation_execution_receipt_atomic(path: Path, record: dict[str, Any]) -> None:
    _write_immutable_record_atomic(
        path,
        record,
        error_code="generation_execution_receipt_already_exists",
        error_label="generation execution receipt artifact",
    )
