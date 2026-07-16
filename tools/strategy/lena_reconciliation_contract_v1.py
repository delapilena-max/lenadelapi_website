from __future__ import annotations

"""Shared reconciliation authority validation for Lena generation.

This helper keeps reconciliation provenance checks consistent across the
handoff builder, approval validator, and executor. It authorizes only
handoff preparation and fails closed on stale, tampered, mismatched, or
over-scoped reconciliation artifacts.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.strategy.lena_record_generation_reconciliation_decision_v1 import (
    expected_confirmation_phrase,
)

ROOT = Path(__file__).resolve().parents[2]

RECONCILIATION_REPORT_TYPE = "lena_generation_reconciliation"
RECONCILIATION_SCHEMA_VERSION = "lena_generation_reconciliation_v1"
RECONCILIATION_DECISION_REPORT_TYPE = "lena_generation_reconciliation_decision"
RECONCILIATION_DECISION_SCHEMA_VERSION = "lena_generation_reconciliation_decision_v1"
RECONCILIATION_DATE_ERROR_CODE = "reconciliation_status_invalid"
RECONCILIATION_STATUS_RECONCILED = "reconciled"
RECONCILIATION_STATUS_OPERATOR_REVIEW_REQUIRED = "operator_review_required"
RECONCILIATION_DIVERGENCE_ALIGNED = "aligned"
RECONCILIATION_DIVERGENCE_RECIPE_MISMATCH = "recipe_mismatch"
RECONCILIATION_POLICY_SELECTED_CANDIDATE_AUTHORITATIVE = "selected_candidate_authoritative"
RECONCILIATION_POLICY_OPERATOR_REVIEW_REQUIRED = "explicit_operator_reconciliation_required"
RECONCILIATION_NEXT_ACTION_BUILD = "build_next_live_image_handoff"
RECONCILIATION_NEXT_ACTION_DECISION = "create_operator_reconciliation_decision"
RECONCILIATION_AUTHORITY_SCOPE = "handoff_preparation_only"
RECONCILIATION_DECISION_TTL_MINUTES = 30

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReconciliationContractError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ReconciliationContractError(code, detail)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def repo_relative_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_repo_path(path_value: str, *, code: str, label: str) -> Path:
    raw = str(path_value or "").strip()
    _require(bool(raw), code, f"{label} is missing")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ReconciliationContractError(code, f"{label} escapes the repository: {raw}") from exc
    return resolved


def read_json(path: Path, *, label: str, code: str) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ReconciliationContractError(code, f"could not read {label}: {exc}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ReconciliationContractError(code, f"{label} is not valid JSON: {exc}") from exc
    _require(isinstance(data, dict), code, f"{label} must be a JSON object")
    return data


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _reconciliation_source_sha(report: dict[str, Any]) -> str:
    core = dict(report)
    core.pop("source_reconciliation_artifact_sha256", None)
    return sha256_bytes(_canonical_bytes(core))


def _load_artifact(path_value: str, *, expected_report_type: str, expected_schema_version: str, date_str: str, missing_code: str, invalid_code: str, label: str) -> tuple[Path, dict[str, Any], str]:
    path = resolve_repo_path(path_value, code=missing_code, label=label)
    _require(path.is_file(), missing_code, f"missing required artifact: {path}")
    sha256 = sha256_file(path)
    report = read_json(path, label=label, code=invalid_code)
    _require(report.get("report_type") == expected_report_type, invalid_code, f"{path} has report_type {report.get('report_type')!r}, expected {expected_report_type!r}")
    _require(report.get("schema_version") == expected_schema_version, invalid_code, f"{path} has schema_version {report.get('schema_version')!r}, expected {expected_schema_version!r}")
    _require(str(report.get("date", "")).strip() == date_str, invalid_code, f"{path} has date {report.get('date')!r}, expected {date_str!r}")
    return path, report, sha256


def _validate_source_artifact_entry(
    entry: dict[str, Any],
    *,
    expected_path: Path,
    expected_sha256: str,
    label: str,
    missing_code: str,
    invalid_code: str,
) -> None:
    _require(isinstance(entry, dict), invalid_code, f"{label} source artifact metadata must be a JSON object")
    path_value = str(entry.get("source_artifact_path", "")).strip()
    sha_value = str(entry.get("source_artifact_sha256", "")).strip()
    _require(path_value, missing_code, f"{label} source artifact path is missing")
    _require(sha_value, missing_code, f"{label} source artifact sha256 is missing")
    resolved = resolve_repo_path(path_value, code=missing_code, label=f"{label} source artifact")
    _require(resolved == expected_path.resolve(), invalid_code, f"{label} source artifact path drifted")
    _require(sha_value == expected_sha256, invalid_code, f"{label} source artifact sha256 drifted")


def load_reconciliation_report(path_value: str, *, date_str: str) -> tuple[Path, dict[str, Any], str]:
    path, report, sha256 = _load_artifact(
        path_value,
        expected_report_type=RECONCILIATION_REPORT_TYPE,
        expected_schema_version=RECONCILIATION_SCHEMA_VERSION,
        date_str=date_str,
        missing_code="missing_reconciliation_artifact",
        invalid_code="invalid_reconciliation_artifact",
        label="reconciliation artifact",
    )
    _require(
        str(report.get("reconciliation_status", "")).strip() in {
            RECONCILIATION_STATUS_RECONCILED,
            RECONCILIATION_STATUS_OPERATOR_REVIEW_REQUIRED,
        },
        RECONCILIATION_DATE_ERROR_CODE,
        "reconciliation_status must be reconciled or operator_review_required",
    )
    operator_review_required = bool(report.get("operator_review_required"))
    divergence_status = str(report.get("divergence_status", "")).strip()
    resolution_policy = str(report.get("resolution_policy", "")).strip()
    exact_next_allowed_action = str(report.get("exact_next_allowed_action", "")).strip()
    status = str(report.get("reconciliation_status", "")).strip()
    if status == RECONCILIATION_STATUS_RECONCILED:
        _require(operator_review_required is False, "reconciliation_status_invalid", "aligned reconciliation must not require operator review")
        _require(divergence_status == RECONCILIATION_DIVERGENCE_ALIGNED, "reconciliation_status_invalid", "aligned reconciliation must report divergence_status='aligned'")
        _require(resolution_policy == RECONCILIATION_POLICY_SELECTED_CANDIDATE_AUTHORITATIVE, "reconciliation_status_invalid", "aligned reconciliation must use selected_candidate_authoritative policy")
        _require(exact_next_allowed_action == RECONCILIATION_NEXT_ACTION_BUILD, "reconciliation_next_action_invalid", "aligned reconciliation must allow handoff construction")
        _require(
            str(report.get("recommendation_recipe_id", "")).strip() == str(report.get("selected_candidate_recipe_id", "")).strip(),
            "reconciled_recipe_mismatch",
            "aligned reconciliation must keep recommendation and selected candidate on the same recipe",
        )
        _require(
            str(report.get("final_reconciled_candidate_recipe_id", "")).strip() == str(report.get("selected_candidate_recipe_id", "")).strip(),
            "reconciled_recipe_mismatch",
            "aligned reconciliation final recipe must match the selected candidate recipe",
        )
    else:
        _require(operator_review_required is True, "reconciliation_status_invalid", "operator_review_required reconciliation must remain review-required")
        _require(divergence_status == RECONCILIATION_DIVERGENCE_RECIPE_MISMATCH, "reconciliation_status_invalid", "review-required reconciliation must report recipe_mismatch")
        _require(resolution_policy == RECONCILIATION_POLICY_OPERATOR_REVIEW_REQUIRED, "reconciliation_status_invalid", "review-required reconciliation must require explicit operator reconciliation")
        _require(exact_next_allowed_action == RECONCILIATION_NEXT_ACTION_DECISION, "reconciliation_next_action_invalid", "review-required reconciliation must request an operator decision")
        _require(
            str(report.get("recommendation_recipe_id", "")).strip() != str(report.get("selected_candidate_recipe_id", "")).strip(),
            "reconciliation_status_invalid",
            "review-required reconciliation must capture a recipe mismatch",
        )

    source_artifacts = report.get("source_artifacts")
    _require(isinstance(source_artifacts, dict), "invalid_reconciliation_artifact", "reconciliation artifact is missing source_artifacts")
    for label in ("learning", "recommendation", "selected_candidate"):
        _require(isinstance(source_artifacts.get(label), dict), "invalid_reconciliation_artifact", f"reconciliation artifact is missing {label} source metadata")

    if status == RECONCILIATION_STATUS_RECONCILED:
        _require(
            str(report.get("final_reconciled_candidate_id", "")).strip(),
            "reconciled_candidate_mismatch",
            "aligned reconciliation must include final_reconciled_candidate_id",
        )
        _require(
            str(report.get("final_reconciled_candidate_recipe_id", "")).strip(),
            "reconciled_recipe_mismatch",
            "aligned reconciliation must include final_reconciled_candidate_recipe_id",
        )
        _require(
            str(report.get("final_reconciled_candidate_slot_id", "")).strip(),
            "reconciled_slot_mismatch",
            "aligned reconciliation must include final_reconciled_candidate_slot_id",
        )
    else:
        _require(
            not report.get("final_reconciled_candidate_id")
            and not report.get("final_reconciled_candidate_recipe_id")
            and not report.get("final_reconciled_candidate_slot_id"),
            "reconciliation_status_invalid",
            "review-required reconciliation must not already contain final reconciled identifiers",
        )

    _require(report.get("dirty_workspace_dependency") is False, "invalid_reconciliation_artifact", "reconciliation artifact must remain clean of dirty-workspace dependency")
    _require(report.get("shadow_mode_only") is True, "invalid_reconciliation_artifact", "reconciliation artifact must remain shadow-mode only")
    _require(report.get("provider_call_performed") is False, "invalid_reconciliation_artifact", "reconciliation artifact must not claim provider calls")
    _require(report.get("approval_consumed") is False, "invalid_reconciliation_artifact", "reconciliation artifact must not claim approval consumption")
    _require(report.get("claims_written") is False, "invalid_reconciliation_artifact", "reconciliation artifact must not claim claims written")
    _require(report.get("receipts_written") is False, "invalid_reconciliation_artifact", "reconciliation artifact must not claim receipts written")
    _require(report.get("queue_mutated") is False, "invalid_reconciliation_artifact", "reconciliation artifact must not claim queue mutation")
    _require(report.get("publish_performed") is False, "invalid_reconciliation_artifact", "reconciliation artifact must not claim publishing")

    learning_path = resolve_repo_path(
        str(source_artifacts["learning"].get("source_artifact_path", "")),
        code="reconciliation_source_drift",
        label="learning source artifact",
    )
    recommendation_path = resolve_repo_path(
        str(source_artifacts["recommendation"].get("source_artifact_path", "")),
        code="reconciliation_source_drift",
        label="recommendation source artifact",
    )
    selected_candidate_path = resolve_repo_path(
        str(source_artifacts["selected_candidate"].get("source_artifact_path", "")),
        code="reconciliation_source_drift",
        label="selected candidate source artifact",
    )
    _validate_source_artifact_entry(
        source_artifacts["learning"],
        expected_path=learning_path,
        expected_sha256=sha256_file(learning_path),
        label="learning",
        missing_code="reconciliation_source_drift",
        invalid_code="reconciliation_source_drift",
    )
    _validate_source_artifact_entry(
        source_artifacts["recommendation"],
        expected_path=recommendation_path,
        expected_sha256=sha256_file(recommendation_path),
        label="recommendation",
        missing_code="reconciliation_source_drift",
        invalid_code="reconciliation_source_drift",
    )
    _validate_source_artifact_entry(
        source_artifacts["selected_candidate"],
        expected_path=selected_candidate_path,
        expected_sha256=sha256_file(selected_candidate_path),
        label="selected candidate",
        missing_code="reconciliation_source_drift",
        invalid_code="reconciliation_source_drift",
    )

    if report.get("source_reconciliation_artifact_sha256"):
        _require(
            SHA256_RE.fullmatch(str(report.get("source_reconciliation_artifact_sha256", ""))) is not None,
            "reconciliation_sha_mismatch",
            "reconciliation source sha256 must be exactly 64 lowercase hexadecimal characters",
        )
        _require(
            str(report.get("source_reconciliation_artifact_sha256", "")).strip() == _reconciliation_source_sha(report),
            "reconciliation_sha_mismatch",
            "reconciliation source sha256 does not match the reconciliation body",
        )

    return path, report, sha256


def load_reconciliation_decision(
    path_value: str,
    *,
    date_str: str,
    reconciliation_path: Path,
    reconciliation_report: dict[str, Any],
    reconciliation_sha256: str,
) -> tuple[Path, dict[str, Any], str]:
    path, report, sha256 = _load_artifact(
        path_value,
        expected_report_type=RECONCILIATION_DECISION_REPORT_TYPE,
        expected_schema_version=RECONCILIATION_DECISION_SCHEMA_VERSION,
        date_str=date_str,
        missing_code="missing_reconciliation_decision",
        invalid_code="invalid_reconciliation_decision",
        label="reconciliation decision artifact",
    )
    _require(
        str(report.get("reconciliation_status", "")).strip() in {
            RECONCILIATION_STATUS_RECONCILED,
            RECONCILIATION_STATUS_OPERATOR_REVIEW_REQUIRED,
        },
        "invalid_reconciliation_decision",
        "decision reconciliation_status is invalid",
    )
    _require(
        str(report.get("source_reconciliation_artifact_path", "")).strip() == repo_relative_path(reconciliation_path),
        "reconciliation_decision_binding_mismatch",
        "decision must bind the supplied reconciliation artifact path exactly",
    )
    self_reported_source_sha = str(report.get("source_reconciliation_artifact_sha256", "")).strip()
    if self_reported_source_sha:
        _require(
            SHA256_RE.fullmatch(self_reported_source_sha) is not None,
            "reconciliation_sha_mismatch",
            "decision self-reported reconciliation sha must be exactly 64 lowercase hexadecimal characters",
        )
        _require(
            self_reported_source_sha in {
                _reconciliation_source_sha(reconciliation_report),
                reconciliation_sha256,
            },
            "reconciliation_sha_mismatch",
            "decision self-reported reconciliation sha does not match the reconciliation artifact",
        )

    _require(
        str(report.get("operator_id", "")).strip(),
        "invalid_reconciliation_decision",
        "decision operator_id is missing",
    )
    _require(
        str(report.get("selected_candidate_id", "")).strip(),
        "invalid_reconciliation_decision",
        "decision selected_candidate_id is missing",
    )
    _require(
        str(report.get("selected_recipe_id", "")).strip(),
        "invalid_reconciliation_decision",
        "decision selected_recipe_id is missing",
    )
    _require(
        str(report.get("selected_slot_id", "")).strip(),
        "invalid_reconciliation_decision",
        "decision selected_slot_id is missing",
    )
    _require(
        str(report.get("authority_scope", "")).strip() == RECONCILIATION_AUTHORITY_SCOPE,
        "reconciliation_decision_authority_invalid",
        "decision authority scope must remain handoff_preparation_only",
    )
    _require(
        report.get("live_generation_authorized") is False,
        "reconciliation_decision_generation_authority_forbidden",
        "decision must not authorize live generation",
    )
    _require(
        report.get("publishing_authorized") is False,
        "reconciliation_decision_publish_authority_forbidden",
        "decision must not authorize publishing",
    )
    _require(
        str(report.get("exact_next_allowed_action", "")).strip() == RECONCILIATION_NEXT_ACTION_BUILD,
        "reconciliation_next_action_invalid",
        "decision next_allowed_action must remain build_next_live_image_handoff",
    )
    expires_at = str(report.get("decision_expires_at_utc", "")).strip()
    generated_at = str(report.get("generated_at_utc", "")).strip()
    _require(expires_at and generated_at, "invalid_reconciliation_decision", "decision must include generated_at_utc and decision_expires_at_utc")
    _require(
        report.get("decision_identity_sha256") == report.get("decision_id"),
        "invalid_reconciliation_decision",
        "decision_identity_sha256 must equal decision_id",
    )
    confirmation = str(report.get("confirmation_phrase", "")).strip()
    _require(
        confirmation == expected_confirmation_phrase(reconciliation_report),
        "invalid_reconciliation_decision",
        "decision confirmation phrase must match the reconciliation source exactly",
    )
    _require(
        str(report.get("selected_candidate_recipe_id", "")).strip() == str(reconciliation_report.get("selected_candidate_recipe_id", "")).strip(),
        "reconciliation_decision_recipe_mismatch",
        "decision selected_recipe_id must match the reconciliation source",
    )
    _require(
        str(report.get("selected_candidate_slot_id", "")).strip() == str(reconciliation_report.get("selected_candidate_slot_id", "")).strip(),
        "reconciliation_decision_slot_mismatch",
        "decision selected_slot_id must match the reconciliation source",
    )
    _require(
        str(report.get("selected_candidate_id", "")).strip() == str(reconciliation_report.get("selected_candidate_id", "")).strip(),
        "reconciliation_decision_candidate_mismatch",
        "decision selected_candidate_id must match the reconciliation source",
    )
    _require(
        str(report.get("selected_candidate_prompt_sha256", "")).strip() == str(reconciliation_report.get("selected_candidate_prompt_sha256", "")).strip(),
        "reconciliation_decision_binding_mismatch",
        "decision selected_candidate_prompt_sha256 must match the reconciliation source",
    )
    if str(report.get("expires_at_utc", "")).strip():
        from datetime import datetime, timezone

        expires = datetime.fromisoformat(str(report["expires_at_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        generated = datetime.fromisoformat(str(report["generated_at_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        _require(expires > generated, "reconciliation_decision_expired", "decision expires_at_utc must be later than generated_at_utc")
    return path, report, sha256


def build_handoff_reconciliation_provenance(
    *,
    date_str: str,
    recommendation_recipe_id: str,
    selected_candidate_path: Path,
    selected_candidate_report: dict[str, Any],
    selected_candidate_body: dict[str, Any],
    reconciliation_artifact_path: str,
    reconciliation_decision_artifact_path: str | None,
) -> dict[str, Any]:
    reconciliation_path, reconciliation_report, reconciliation_sha256 = load_reconciliation_report(
        reconciliation_artifact_path,
        date_str=date_str,
    )
    _require(
        str(reconciliation_report.get("recommendation_recipe_id", "")).strip() == recommendation_recipe_id,
        "reconciled_recipe_mismatch",
        "reconciliation recommendation recipe does not match the current recommendation",
    )
    _require(
        str(reconciliation_report.get("selected_candidate_id", "")).strip() == str(selected_candidate_body.get("candidate_id", "")).strip(),
        "reconciled_candidate_mismatch",
        "reconciliation selected candidate id does not match the selected candidate artifact",
    )
    _require(
        str(reconciliation_report.get("selected_candidate_recipe_id", "")).strip() == str(selected_candidate_body.get("recipe_id", "")).strip(),
        "reconciled_recipe_mismatch",
        "reconciliation selected candidate recipe does not match the selected candidate artifact",
    )
    _require(
        str(reconciliation_report.get("selected_candidate_slot_id", "")).strip() == str(selected_candidate_body.get("slot_id", "")).strip(),
        "reconciled_slot_mismatch",
        "reconciliation selected candidate slot does not match the selected candidate artifact",
    )
    _require(
        str(reconciliation_report.get("selected_candidate_prompt_sha256", "")).strip() == str(selected_candidate_body.get("prompt_sha256", "")).strip(),
        "reconciled_candidate_mismatch",
        "reconciliation selected candidate prompt sha256 does not match the selected candidate artifact",
    )
    _require(
        reconciliation_report.get("source_artifacts", {}).get("selected_candidate", {}).get("source_artifact_path") == repo_relative_path(selected_candidate_path),
        "reconciliation_source_drift",
        "reconciliation selected candidate source path does not match the selected candidate artifact path",
    )
    _require(
        reconciliation_report.get("source_artifacts", {}).get("selected_candidate", {}).get("source_artifact_sha256") == sha256_file(selected_candidate_path),
        "reconciliation_source_drift",
        "reconciliation selected candidate source sha does not match the selected candidate artifact bytes",
    )
    _require(
        reconciliation_report.get("source_artifacts", {}).get("recommendation", {}).get("source_artifact_path"),
        "reconciliation_source_drift",
        "reconciliation recommendation source metadata is missing",
    )
    _require(
        reconciliation_report.get("source_artifacts", {}).get("learning", {}).get("source_artifact_path"),
        "reconciliation_source_drift",
        "reconciliation learning source metadata is missing",
    )

    aligned = str(reconciliation_report.get("reconciliation_status", "")).strip() == RECONCILIATION_STATUS_RECONCILED
    decision_path: Path | None = None
    decision_report: dict[str, Any] | None = None
    decision_sha256: str | None = None

    if aligned:
        _require(
            reconciliation_decision_artifact_path is None or not str(reconciliation_decision_artifact_path).strip(),
            "unexpected_reconciliation_decision",
            "aligned reconciliation must not be paired with an operator decision artifact",
        )
        final_candidate_id = str(reconciliation_report.get("final_reconciled_candidate_id", "")).strip()
        final_recipe_id = str(reconciliation_report.get("final_reconciled_candidate_recipe_id", "")).strip()
        final_slot_id = str(reconciliation_report.get("final_reconciled_candidate_slot_id", "")).strip()
        final_hook_id = str(reconciliation_report.get("final_reconciled_candidate_hook_id", "")).strip()
        final_prompt_sha256 = str(reconciliation_report.get("final_reconciled_candidate_prompt_sha256", "")).strip()
        final_artifact_path = str(reconciliation_report.get("final_reconciled_candidate_artifact_path", "")).strip()
        final_artifact_sha256 = str(reconciliation_report.get("final_reconciled_candidate_artifact_sha256", "")).strip()
        _require(final_candidate_id, "reconciled_candidate_mismatch", "aligned reconciliation must provide a final reconciled candidate id")
        _require(final_recipe_id, "reconciled_recipe_mismatch", "aligned reconciliation must provide a final reconciled recipe id")
        _require(final_slot_id, "reconciled_slot_mismatch", "aligned reconciliation must provide a final reconciled slot id")
        _require(final_prompt_sha256 == str(selected_candidate_body.get("prompt_sha256", "")).strip(), "reconciled_candidate_mismatch", "aligned reconciliation final prompt sha must match the selected candidate")
        _require(final_candidate_id == str(selected_candidate_body.get("candidate_id", "")).strip(), "reconciled_candidate_mismatch", "aligned reconciliation final candidate must match the selected candidate")
        _require(final_recipe_id == str(selected_candidate_body.get("recipe_id", "")).strip(), "reconciled_recipe_mismatch", "aligned reconciliation final recipe must match the selected candidate")
        _require(final_slot_id == str(selected_candidate_body.get("slot_id", "")).strip(), "reconciled_slot_mismatch", "aligned reconciliation final slot must match the selected candidate")
        _require(final_artifact_path == repo_relative_path(selected_candidate_path), "reconciled_candidate_mismatch", "aligned reconciliation final artifact path must match the selected candidate")
        _require(final_artifact_sha256 == sha256_file(selected_candidate_path), "reconciled_candidate_mismatch", "aligned reconciliation final artifact sha must match the selected candidate")
    else:
        _require(
            bool(str(reconciliation_decision_artifact_path or "").strip()),
            "missing_reconciliation_decision",
            "divergent reconciliation must be paired with an operator decision artifact",
        )
        decision_path, decision_report, decision_sha256 = load_reconciliation_decision(
            str(reconciliation_decision_artifact_path),
            date_str=date_str,
            reconciliation_path=reconciliation_path,
            reconciliation_report=reconciliation_report,
            reconciliation_sha256=reconciliation_sha256,
        )
        _require(
            str(decision_report.get("source_reconciliation_artifact_sha256", "")).strip()
            in {"", _reconciliation_source_sha(reconciliation_report), reconciliation_sha256},
            "reconciliation_decision_sha_mismatch",
            "operator decision reconciliation source sha does not match the reconciliation artifact",
        )
        final_candidate_id = str(decision_report.get("selected_candidate_id", "")).strip()
        final_recipe_id = str(decision_report.get("selected_recipe_id", "")).strip()
        final_slot_id = str(decision_report.get("selected_slot_id", "")).strip()
        final_hook_id = str(reconciliation_report.get("selected_candidate_hook_id", "")).strip()
        final_prompt_sha256 = str(decision_report.get("selected_candidate_prompt_sha256", "")).strip()
        final_artifact_path = repo_relative_path(selected_candidate_path)
        final_artifact_sha256 = sha256_file(selected_candidate_path)
        _require(final_candidate_id == str(selected_candidate_body.get("candidate_id", "")).strip(), "reconciliation_decision_candidate_mismatch", "operator decision candidate must match the selected candidate")
        _require(final_recipe_id == str(selected_candidate_body.get("recipe_id", "")).strip(), "reconciliation_decision_recipe_mismatch", "operator decision recipe must match the selected candidate")
        _require(final_slot_id == str(selected_candidate_body.get("slot_id", "")).strip(), "reconciliation_decision_slot_mismatch", "operator decision slot must match the selected candidate")
        _require(final_prompt_sha256 == str(selected_candidate_body.get("prompt_sha256", "")).strip(), "reconciliation_decision_binding_mismatch", "operator decision prompt sha must match the selected candidate")
        _require(
            str(decision_report.get("authority_scope", "")).strip() == RECONCILIATION_AUTHORITY_SCOPE,
            "reconciliation_decision_authority_invalid",
            "operator decision must remain handoff-preparation only",
        )
        _require(decision_report.get("live_generation_authorized") is False, "reconciliation_decision_generation_authority_forbidden", "operator decision must not authorize live generation")
        _require(decision_report.get("publishing_authorized") is False, "reconciliation_decision_publish_authority_forbidden", "operator decision must not authorize publishing")
        _require(
            str(decision_report.get("exact_next_allowed_action", "")).strip() == RECONCILIATION_NEXT_ACTION_BUILD,
            "reconciliation_next_action_invalid",
            "operator decision next allowed action must be build_next_live_image_handoff",
        )

    return {
        "reconciliation": {
            "source_artifact_path": repo_relative_path(reconciliation_path),
            "source_artifact_sha256": reconciliation_sha256,
            "schema_version": reconciliation_report.get("schema_version", ""),
            "report_type": reconciliation_report.get("report_type", ""),
            "date": date_str,
            "reconciliation_status": reconciliation_report.get("reconciliation_status", ""),
            "operator_review_required": bool(reconciliation_report.get("operator_review_required", False)),
            "divergence_status": reconciliation_report.get("divergence_status", ""),
            "resolution_policy": reconciliation_report.get("resolution_policy", ""),
            "exact_next_allowed_action": reconciliation_report.get("exact_next_allowed_action", ""),
            "decision_required": not aligned,
        },
        "final_candidate": {
            "candidate_id": final_candidate_id,
            "recipe_id": final_recipe_id,
            "slot_id": final_slot_id,
            "hook_id": final_hook_id,
            "prompt_sha256": final_prompt_sha256,
            "artifact_path": final_artifact_path,
            "artifact_sha256": final_artifact_sha256,
        },
        "decision": None
        if decision_report is None
        else {
            "source_artifact_path": repo_relative_path(decision_path),
            "source_artifact_sha256": decision_sha256,
            "decision_id": decision_report.get("decision_id", ""),
            "operator_id": decision_report.get("operator_id", ""),
            "expires_at_utc": decision_report.get("decision_expires_at_utc", ""),
            "authority_scope": decision_report.get("authority_scope", ""),
            "live_generation_authorized": decision_report.get("live_generation_authorized", False),
            "publishing_authorized": decision_report.get("publishing_authorized", False),
            "next_allowed_action": decision_report.get("exact_next_allowed_action", ""),
        },
    }


def validate_handoff_reconciliation_provenance(
    handoff_report: dict[str, Any],
    selected_candidate_binding: dict[str, Any],
) -> dict[str, Any]:
    reconciliation_path_value = str(handoff_report.get("source_reconciliation_artifact_path") or "").strip()
    reconciliation_sha_value = str(handoff_report.get("source_reconciliation_artifact_sha256") or "").strip()
    _require(
        reconciliation_path_value and reconciliation_sha_value,
        "missing_reconciliation_artifact",
        "handoff must include reconciliation provenance",
    )
    reconciliation_path = resolve_repo_path(
        reconciliation_path_value,
        code="missing_reconciliation_artifact",
        label="handoff reconciliation artifact",
    )
    _require(
        reconciliation_path.is_file(),
        "missing_reconciliation_artifact",
        f"missing required artifact: {reconciliation_path}",
    )
    reconciliation_sha256 = sha256_file(reconciliation_path)
    _require(
        reconciliation_sha256 == reconciliation_sha_value,
        "reconciliation_sha_mismatch",
        "handoff reconciliation artifact sha256 does not match current bytes",
    )
    reconciliation_report = read_json(
        reconciliation_path,
        label="reconciliation artifact",
        code="invalid_reconciliation_artifact",
    )
    _require(
        reconciliation_report.get("report_type") == RECONCILIATION_REPORT_TYPE,
        "invalid_reconciliation_artifact",
        f"{reconciliation_path} has report_type {reconciliation_report.get('report_type')!r}, expected {RECONCILIATION_REPORT_TYPE!r}",
    )
    _require(
        reconciliation_report.get("schema_version") == RECONCILIATION_SCHEMA_VERSION,
        "invalid_reconciliation_artifact",
        f"{reconciliation_path} has schema_version {reconciliation_report.get('schema_version')!r}, expected {RECONCILIATION_SCHEMA_VERSION!r}",
    )
    _require(
        str(handoff_report.get("date", "")).strip() == str(reconciliation_report.get("date", "")).strip(),
        "reconciliation_source_drift",
        "handoff date must match the reconciliation artifact date",
    )
    _require(
        str(handoff_report.get("source_recommendation_artifact_path", "")).strip(),
        "missing_reconciliation_artifact",
        "handoff must include a recommendation provenance path",
    )
    selected_candidate_final = {
        "candidate_id": str(selected_candidate_binding.get("selected_candidate_id", "")).strip(),
        "recipe_id": str(selected_candidate_binding.get("selected_candidate_recipe_id", "")).strip(),
        "slot_id": str(selected_candidate_binding.get("selected_candidate_slot_id", "")).strip(),
        "hook_id": str(selected_candidate_binding.get("selected_candidate_hook_id", "")).strip(),
        "prompt_sha256": str(selected_candidate_binding.get("selected_candidate_prompt_sha256", "")).strip(),
        "artifact_path": repo_relative_path(selected_candidate_binding["selected_candidate_path"]),
        "artifact_sha256": str(selected_candidate_binding.get("selected_candidate_sha256", "")).strip(),
    }

    decision_path_value = str(handoff_report.get("source_reconciliation_decision_artifact_path") or "").strip()
    decision_sha_value = str(handoff_report.get("source_reconciliation_decision_artifact_sha256") or "").strip()
    aligned = str(reconciliation_report.get("reconciliation_status", "")).strip() == RECONCILIATION_STATUS_RECONCILED
    if aligned:
        _require(
            not decision_path_value and not decision_sha_value and not handoff_report.get("source_reconciliation_decision_id"),
            "unexpected_reconciliation_decision",
            "aligned reconciliation handoffs must not include operator decision provenance",
        )
    else:
        _require(decision_path_value and decision_sha_value, "missing_reconciliation_decision", "divergent reconciliation handoffs must include operator decision provenance")
        decision_path = resolve_repo_path(
            decision_path_value,
            code="missing_reconciliation_decision",
            label="handoff reconciliation decision",
        )
        _require(
            decision_path.is_file(),
            "missing_reconciliation_decision",
            f"missing required artifact: {decision_path}",
        )
        decision_report = read_json(decision_path, label="reconciliation decision artifact", code="invalid_reconciliation_decision")
        _require(
            sha256_file(decision_path) == decision_sha_value,
            "reconciliation_decision_sha_mismatch",
            "handoff reconciliation decision sha256 does not match current bytes",
        )
        _require(
            str(decision_report.get("source_reconciliation_artifact_path", "")).strip() == reconciliation_path_value,
            "reconciliation_decision_binding_mismatch",
            "handoff reconciliation decision must bind the handoff reconciliation artifact",
        )
        _require(
            str(decision_report.get("source_reconciliation_artifact_sha256", "")).strip() == reconciliation_sha256,
            "reconciliation_decision_sha_mismatch",
            "handoff reconciliation decision source sha must match the reconciliation artifact",
        )
        _require(
            str(handoff_report.get("source_reconciliation_decision_id", "")).strip() == str(decision_report.get("decision_id", "")).strip(),
            "reconciliation_decision_binding_mismatch",
            "handoff reconciliation decision id must match the decision artifact",
        )
        _require(
            str(handoff_report.get("source_reconciliation_decision_operator_id", "")).strip() == str(decision_report.get("operator_id", "")).strip(),
            "reconciliation_decision_binding_mismatch",
            "handoff reconciliation decision operator id must match the decision artifact",
        )
        _require(
            str(handoff_report.get("source_reconciliation_decision_expires_at_utc", "")).strip() == str(decision_report.get("decision_expires_at_utc", "")).strip(),
            "reconciliation_decision_binding_mismatch",
            "handoff reconciliation decision expiration must match the decision artifact",
        )
        _require(
            str(handoff_report.get("source_reconciliation_decision_authority_scope", "")).strip() == str(decision_report.get("authority_scope", "")).strip(),
            "reconciliation_decision_authority_invalid",
            "handoff reconciliation decision authority scope must match the decision artifact",
        )
        _require(
            handoff_report.get("source_reconciliation_decision_live_generation_authorized") is False
            and decision_report.get("live_generation_authorized") is False,
            "reconciliation_decision_generation_authority_forbidden",
            "handoff reconciliation decision must not authorize live generation",
        )
        _require(
            handoff_report.get("source_reconciliation_decision_publishing_authorized") is False
            and decision_report.get("publishing_authorized") is False,
            "reconciliation_decision_publish_authority_forbidden",
            "handoff reconciliation decision must not authorize publishing",
        )
        _require(
            str(handoff_report.get("source_reconciliation_decision_next_allowed_action", "")).strip() == str(decision_report.get("exact_next_allowed_action", "")).strip() == RECONCILIATION_NEXT_ACTION_BUILD,
            "reconciliation_next_action_invalid",
            "handoff reconciliation decision next allowed action must be build_next_live_image_handoff",
        )
        _require(
            str(decision_report.get("selected_candidate_id", "")).strip() == str(selected_candidate_binding.get("selected_candidate_id", "")).strip(),
            "reconciliation_decision_candidate_mismatch",
            "handoff reconciliation decision candidate must match the selected candidate binding",
        )
        _require(
            str(decision_report.get("selected_recipe_id", "")).strip() == str(selected_candidate_binding.get("selected_candidate_recipe_id", "")).strip(),
            "reconciliation_decision_recipe_mismatch",
            "handoff reconciliation decision recipe must match the selected candidate binding",
        )
        _require(
            str(decision_report.get("selected_slot_id", "")).strip() == str(selected_candidate_binding.get("selected_candidate_slot_id", "")).strip(),
            "reconciliation_decision_slot_mismatch",
            "handoff reconciliation decision slot must match the selected candidate binding",
        )
        _require(
            str(decision_report.get("authority_scope", "")).strip() == RECONCILIATION_AUTHORITY_SCOPE,
            "reconciliation_decision_authority_invalid",
            "handoff reconciliation decision must remain handoff-preparation-only",
        )
        _require(
            decision_report.get("live_generation_authorized") is False,
            "reconciliation_decision_generation_authority_forbidden",
            "handoff reconciliation decision must not authorize live generation",
        )
        _require(
            decision_report.get("publishing_authorized") is False,
            "reconciliation_decision_publish_authority_forbidden",
            "handoff reconciliation decision must not authorize publishing",
        )

    return {
        "reconciliation": {
            "source_artifact_path": reconciliation_path_value,
            "source_artifact_sha256": reconciliation_sha256,
            "schema_version": reconciliation_report.get("schema_version", ""),
            "reconciliation_status": reconciliation_report.get("reconciliation_status", ""),
            "operator_review_required": bool(reconciliation_report.get("operator_review_required", False)),
            "divergence_status": reconciliation_report.get("divergence_status", ""),
            "resolution_policy": reconciliation_report.get("resolution_policy", ""),
            "exact_next_allowed_action": reconciliation_report.get("exact_next_allowed_action", ""),
            "decision_required": not aligned,
        },
        "final_candidate": selected_candidate_final,
        "decision": None
        if aligned
        else {
            "source_artifact_path": decision_path_value,
            "source_artifact_sha256": decision_sha_value,
            "decision_id": decision_report.get("decision_id", ""),
            "operator_id": decision_report.get("operator_id", ""),
            "expires_at_utc": decision_report.get("decision_expires_at_utc", ""),
            "authority_scope": decision_report.get("authority_scope", ""),
            "live_generation_authorized": decision_report.get("live_generation_authorized", False),
            "publishing_authorized": decision_report.get("publishing_authorized", False),
            "next_allowed_action": decision_report.get("exact_next_allowed_action", ""),
        },
    }
