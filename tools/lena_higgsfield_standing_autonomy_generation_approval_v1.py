from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools import lena_higgsfield_generation_approval_v1 as canonical_approval
from pipeline.identity import lena_higgsfield_soul_cinema_contract_v1 as soul_cinema_contract

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "generation"

APPROVAL_REPORT_TYPE = "lena_higgsfield_standing_autonomy_generation_approval"
APPROVAL_SCHEMA_VERSION = "v1"
APPROVAL_TYPE = "higgsfield_single_standing_autonomy_generation"
CLAIM_REPORT_TYPE = "lena_higgsfield_standing_autonomy_generation_claim"
CLAIM_SCHEMA_VERSION = "v1"
CLAIM_TYPE = "higgsfield_single_standing_autonomy_generation_consumption_claim"
RECEIPT_REPORT_TYPE = "lena_higgsfield_standing_autonomy_generation_execution_receipt"
RECEIPT_SCHEMA_VERSION = "v1"
RECEIPT_TYPE = "higgsfield_single_standing_autonomy_generation_execution_receipt"
APPROVAL_TTL_MINUTES = canonical_approval.APPROVAL_TTL_MINUTES
STANDING_AUTONOMY_AUTHORIZATION_MODE = "standing_autonomy_policy"

CONTROLLED_RECIPE_ID = "hcr_012"
CONTROLLED_WARDROBE_ID = "wc_p050"


class HiggsfieldStandingAutonomyGenerationApprovalError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def approval_output_path(date_str: str, slot_id: str, out_root: Path | None = None) -> Path:
    base = out_root if out_root is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_higgsfield_standing_autonomy_generation_approval.json"


def claim_output_path(date_str: str, slot_id: str) -> Path:
    return canonical_approval.claim_output_path(date_str, slot_id)


def receipt_output_path(date_str: str, slot_id: str) -> Path:
    return canonical_approval.receipt_output_path(date_str, slot_id)


def repo_relative_path(path: Path) -> str:
    return canonical_approval.repo_relative_path(path)


def sha256_file(path: Path) -> str:
    return canonical_approval.sha256_file(path)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HiggsfieldStandingAutonomyGenerationApprovalError(code, detail)


def _translate_canonical_error(
    exc: canonical_approval.HiggsfieldGenerationApprovalError,
) -> HiggsfieldStandingAutonomyGenerationApprovalError:
    return HiggsfieldStandingAutonomyGenerationApprovalError(exc.code, exc.detail)


# --- Fresh, from-disk re-derivation of every bound handoff/candidate fact ----
#
# Deliberately independent of pipeline.higgsfield_lena_api_executor to avoid a
# circular import (the executor calls into this module's write/validate
# functions). Reads the handoff and candidate artifacts directly and extracts
# exactly the fields the standing-autonomy generation approval binds to.

def inspect_generation_handoff_for_standing_autonomy(
    handoff_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    handoff_path = handoff_path.resolve()
    candidate_path = candidate_path.resolve()
    try:
        report = canonical_approval.read_json_object(
            handoff_path,
            code="handoff_missing_or_invalid",
            label="Higgsfield next-live-image handoff artifact",
        )
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc
    _require(
        report.get("report_type") == canonical_approval.HANDOFF_REPORT_TYPE,
        "handoff_report_type_mismatch",
        f"handoff report_type must be {canonical_approval.HANDOFF_REPORT_TYPE!r}",
    )
    _require(
        report.get("schema_version") == canonical_approval.HANDOFF_SCHEMA_VERSION,
        "handoff_schema_version_mismatch",
        f"handoff schema_version must be {canonical_approval.HANDOFF_SCHEMA_VERSION!r}",
    )

    try:
        selected_candidate_binding = canonical_approval.validate_selected_candidate_binding(report)
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc
    _require(
        candidate_path == selected_candidate_binding["selected_candidate_path"].resolve(),
        "candidate_path_binding_mismatch",
        "selected candidate path must match the handoff's canonical selected-candidate binding",
    )
    candidate = selected_candidate_binding["selected_candidate"]

    # authority_commit and decision_fingerprint_sha256 are fields on the
    # top-level decision envelope (lena_pre_generation_candidate_gate_v1's
    # own output), not on the nested "candidate" sub-object -- present
    # regardless of whether the artifact uses the nested or flat shape.
    authority_commit = str(candidate.get("authority_commit") or "").strip()
    _require(
        len(authority_commit) == 40 and all(ch in "0123456789abcdef" for ch in authority_commit),
        "candidate_authority_commit_invalid",
        "selected candidate authority_commit must be a full lowercase git commit hash",
    )

    selected_candidate = report.get("selected_candidate")
    _require(isinstance(selected_candidate, dict), "handoff_selected_candidate_missing", "handoff selected_candidate is missing")
    recipe_id = str(report.get("selected_recipe_id") or "").strip()
    wardrobe_outfit_id = str(selected_candidate.get("wardrobe_outfit_id") or "").strip()
    effective_wardrobe_silhouette_class = str(selected_candidate.get("effective_wardrobe_silhouette_class") or "").strip()
    _require(recipe_id, "handoff_recipe_id_missing", "handoff selected_recipe_id is missing")
    _require(wardrobe_outfit_id, "handoff_wardrobe_outfit_id_missing", "handoff selected_candidate.wardrobe_outfit_id is missing")

    pose_provenance = report.get("pose_provenance")
    expression_provenance = report.get("expression_provenance")
    _require(isinstance(pose_provenance, dict) and bool(pose_provenance), "handoff_pose_provenance_missing", "handoff pose_provenance is missing")
    _require(isinstance(expression_provenance, dict) and bool(expression_provenance), "handoff_expression_provenance_missing", "handoff expression_provenance is missing")
    pose_bound_content_packet_sha256 = canonical_approval.require_sha256(
        report.get("pose_bound_content_packet_sha256"),
        code="handoff_pose_bound_packet_sha_invalid",
        label="handoff pose_bound_content_packet_sha256",
    )
    expression_bound_content_packet_sha256 = canonical_approval.require_sha256(
        report.get("expression_bound_content_packet_sha256"),
        code="handoff_expression_bound_packet_sha_invalid",
        label="handoff expression_bound_content_packet_sha256",
    )

    structured = report.get("structured_executor_inputs") or {}
    prompt_sha256 = canonical_approval.require_sha256(
        structured.get("selected_prompt_sha256"),
        code="handoff_prompt_sha_invalid",
        label="handoff structured_executor_inputs.selected_prompt_sha256",
    )
    custom_reference_id = str(structured.get("custom_reference_id") or "").strip()
    _require(custom_reference_id, "handoff_custom_reference_id_missing", "handoff structured_executor_inputs.custom_reference_id is missing")
    try:
        generation_reference = soul_cinema_contract.validate_generation_reference_binding(
            structured.get("generation_reference")
        )
    except soul_cinema_contract.SoulCinemaContractError as exc:
        raise HiggsfieldStandingAutonomyGenerationApprovalError(
            exc.code, exc.detail
        ) from exc
    _require(
        report.get("generation_reference") == generation_reference,
        "handoff_generation_reference_mismatch",
        "handoff top-level generation reference differs from structured executor inputs",
    )

    authority_blocks = canonical_approval.require_authority_blocks(report)

    decision_fingerprint_sha256 = str(
        candidate.get("decision_fingerprint_sha256") or ""
    ).strip() or None

    return {
        "report": report,
        "handoff_path": handoff_path,
        "handoff_repo_path": repo_relative_path(handoff_path),
        "handoff_sha256": sha256_file(handoff_path),
        "candidate_artifact_path": candidate_path,
        "candidate_artifact_repo_path": repo_relative_path(candidate_path),
        "candidate_artifact_sha256": sha256_file(candidate_path),
        "date": str(report.get("date") or "").strip(),
        "slot_id": str(report.get("selected_slot_id") or "").strip(),
        "recipe_id": recipe_id,
        "wardrobe_outfit_id": wardrobe_outfit_id,
        "effective_wardrobe_silhouette_class": effective_wardrobe_silhouette_class,
        "prompt_sha256": prompt_sha256,
        "custom_reference_id": custom_reference_id,
        "generation_reference": generation_reference,
        "authority_commit": authority_commit,
        "decision_fingerprint_sha256": decision_fingerprint_sha256,
        "pose_provenance": pose_provenance,
        "expression_provenance": expression_provenance,
        "pose_bound_content_packet_sha256": pose_bound_content_packet_sha256,
        "expression_bound_content_packet_sha256": expression_bound_content_packet_sha256,
        "candidate_selection_binding": authority_blocks[0],
        "provider_execution_binding": authority_blocks[1],
        "binding_linkage": authority_blocks[2],
        "provider": str(report.get("provider") or ""),
        "executor": str(report.get("executor_type") or ""),
        "model": str((report.get("structured_executor_inputs") or {}).get("model") or ""),
        "aspect_ratio": str((report.get("structured_executor_inputs") or {}).get("aspect_ratio") or ""),
        "soul_name": str(((report.get("structured_executor_inputs") or {}).get("soul_metadata") or {}).get("name") or ""),
        "soul_type": str(((report.get("structured_executor_inputs") or {}).get("soul_metadata") or {}).get("type") or ""),
    }


def build_standing_autonomy_generation_approval_record(
    handoff_facts: dict[str, Any],
    authorization_result: dict[str, Any],
    *,
    approved_at: datetime | None = None,
) -> dict[str, Any]:
    from tools import lena_standing_autonomy_policy_v1 as standing_autonomy

    auth = authorization_result.get("artifact")
    _require(isinstance(auth, dict), "standing_authorization_invalid", "standing authorization artifact is missing")
    _require(auth.get("consumed") is True, "standing_authorization_not_consumed", "standing authorization must be consumed before a generation approval can be issued")
    controlled = auth.get("controlled_photo_autonomy")
    _require(
        isinstance(controlled, dict) and controlled.get("enabled") is True,
        "standing_authorization_scope_invalid",
        "standing authorization does not enable controlled photo autonomy",
    )
    _require(controlled.get("recipe_id") == CONTROLLED_RECIPE_ID, "standing_authorization_recipe_invalid", f"standing authorization recipe must be {CONTROLLED_RECIPE_ID!r}")
    _require(controlled.get("wardrobe_outfit_id") == CONTROLLED_WARDROBE_ID, "standing_authorization_wardrobe_invalid", f"standing authorization wardrobe must be {CONTROLLED_WARDROBE_ID!r}")
    _require(int(auth.get("provider_call_cap_per_cycle", 0)) == 2, "standing_provider_cap_invalid", "standing authorization must permit exactly two provider calls")
    _require(int(auth.get("retry_cap_per_cycle", -1)) == 1, "standing_retry_cap_invalid", "standing authorization must permit exactly one retry")

    _require(handoff_facts["recipe_id"] == CONTROLLED_RECIPE_ID, "standing_generation_recipe_mismatch", "generation handoff is outside the controlled recipe")
    _require(handoff_facts["wardrobe_outfit_id"] == CONTROLLED_WARDROBE_ID, "standing_generation_wardrobe_mismatch", "generation handoff is outside the controlled wardrobe")
    _require(handoff_facts["slot_id"] == auth.get("slot_id"), "standing_generation_slot_mismatch", "generation handoff slot does not match the standing authorization")
    _require(handoff_facts["date"] == auth.get("date"), "standing_generation_date_mismatch", "generation handoff date does not match the standing authorization")
    _require(handoff_facts["candidate_artifact_sha256"] == auth.get("candidate_artifact_sha256"), "standing_generation_candidate_sha_mismatch", "generation candidate SHA does not match the standing authorization")
    _require(
        handoff_facts["candidate_artifact_repo_path"] == repo_relative_path(Path(str(auth.get("candidate_artifact_path") or ""))),
        "standing_generation_candidate_path_mismatch",
        "generation candidate path does not match the standing authorization",
    )
    _require(handoff_facts["handoff_sha256"] == auth.get("generation_handoff_artifact_sha256"), "standing_generation_handoff_sha_mismatch", "generation handoff SHA does not match the standing authorization")
    _require(
        handoff_facts["handoff_repo_path"] == repo_relative_path(Path(str(auth.get("generation_handoff_artifact_path") or ""))),
        "standing_generation_handoff_path_mismatch",
        "generation handoff path does not match the standing authorization",
    )
    _require(handoff_facts["prompt_sha256"] == auth.get("prompt_sha256"), "standing_generation_prompt_sha_mismatch", "generation prompt SHA does not match the standing authorization")
    _require(handoff_facts["custom_reference_id"] == auth.get("custom_reference_id"), "standing_generation_reference_id_mismatch", "generation custom_reference_id does not match the standing authorization")
    for key in canonical_approval.AUTHORITY_BLOCK_KEYS:
        _require(handoff_facts[key] == auth.get(key), f"standing_generation_{key}_mismatch", f"generation {key} does not match the standing authorization")

    approved_at = (approved_at or utcnow()).astimezone(timezone.utc).replace(microsecond=0)
    expires_at = approved_at + timedelta(minutes=APPROVAL_TTL_MINUTES)
    auth_path = Path(str(authorization_result["path"])).resolve()
    return {
        "report_type": APPROVAL_REPORT_TYPE,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_type": APPROVAL_TYPE,
        "operator_id": standing_autonomy.AUTHORIZATION_ISSUER,
        "authorization_identity_mode": STANDING_AUTONOMY_AUTHORIZATION_MODE,
        "approved_at_utc": approved_at.isoformat(),
        "expires_at_utc": expires_at.isoformat(),
        "date": handoff_facts["date"],
        "slot_id": handoff_facts["slot_id"],
        "recipe_id": handoff_facts["recipe_id"],
        "wardrobe_outfit_id": handoff_facts["wardrobe_outfit_id"],
        "effective_wardrobe_silhouette_class": handoff_facts["effective_wardrobe_silhouette_class"],
        "handoff_artifact_path": handoff_facts["handoff_repo_path"],
        "handoff_artifact_sha256": handoff_facts["handoff_sha256"],
        "handoff_report_type": canonical_approval.HANDOFF_REPORT_TYPE,
        "handoff_schema_version": canonical_approval.HANDOFF_SCHEMA_VERSION,
        "candidate_artifact_path": handoff_facts["candidate_artifact_repo_path"],
        "candidate_artifact_sha256": handoff_facts["candidate_artifact_sha256"],
        "authority_commit": handoff_facts["authority_commit"],
        "decision_fingerprint_sha256": handoff_facts["decision_fingerprint_sha256"],
        "prompt_sha256": handoff_facts["prompt_sha256"],
        "pose_provenance": handoff_facts["pose_provenance"],
        "expression_provenance": handoff_facts["expression_provenance"],
        "pose_bound_content_packet_sha256": handoff_facts["pose_bound_content_packet_sha256"],
        "expression_bound_content_packet_sha256": handoff_facts["expression_bound_content_packet_sha256"],
        "candidate_selection_binding": handoff_facts["candidate_selection_binding"],
        "provider_execution_binding": handoff_facts["provider_execution_binding"],
        "binding_linkage": handoff_facts["binding_linkage"],
        "provider": handoff_facts["provider"],
        "executor": handoff_facts["executor"],
        "model": handoff_facts["model"],
        "aspect_ratio": handoff_facts["aspect_ratio"],
        "soul_name": handoff_facts["soul_name"],
        "soul_type": handoff_facts["soul_type"],
        "custom_reference_id": handoff_facts["custom_reference_id"],
        "generation_reference": handoff_facts["generation_reference"],
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "scheduling_authorized": False,
        "analytics_mutation_authorized": False,
        "immutability": "immutable_once_written",
        "standing_authorization_artifact_path": repo_relative_path(auth_path),
        "standing_authorization_artifact_sha256": sha256_file(auth_path),
        "standing_authorization_cycle_id": auth.get("cycle_id"),
        "standing_policy_artifact_sha256": auth.get("policy_artifact_sha256"),
    }


def validate_standing_autonomy_generation_approval_artifact(
    approval_path: Path,
    *,
    now: datetime | None = None,
    require_not_expired: bool = True,
) -> dict[str, Any]:
    from tools import lena_standing_autonomy_policy_v1 as standing_autonomy

    approval_path = approval_path.resolve()
    try:
        approval = canonical_approval.read_json_object(
            approval_path,
            code="approval_missing_or_invalid",
            label="Higgsfield standing-autonomy generation approval artifact",
        )
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc

    _require(approval.get("report_type") == APPROVAL_REPORT_TYPE, "approval_report_type_mismatch", f"approval report_type must be {APPROVAL_REPORT_TYPE!r}")
    _require(approval.get("schema_version") == APPROVAL_SCHEMA_VERSION, "approval_schema_version_mismatch", f"approval schema_version must be {APPROVAL_SCHEMA_VERSION!r}")
    _require(approval.get("approval_type") == APPROVAL_TYPE, "approval_type_mismatch", f"approval approval_type must be {APPROVAL_TYPE!r}")
    _require(
        approval.get("authorization_identity_mode") == STANDING_AUTONOMY_AUTHORIZATION_MODE,
        "approval_authorization_mode_invalid",
        f"approval authorization_identity_mode must be {STANDING_AUTONOMY_AUTHORIZATION_MODE!r}",
    )
    _require(
        approval.get("operator_id") == standing_autonomy.AUTHORIZATION_ISSUER,
        "approval_operator_mismatch",
        f"approval operator_id must be exactly {standing_autonomy.AUTHORIZATION_ISSUER!r}",
    )

    try:
        approved_at = canonical_approval.parse_iso8601_utc(approval.get("approved_at_utc"), code="approval_approved_at_invalid", label="approval approved_at_utc")
        expires_at = canonical_approval.parse_iso8601_utc(approval.get("expires_at_utc"), code="approval_expires_at_invalid", label="approval expires_at_utc")
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc
    _require(expires_at - approved_at == timedelta(minutes=APPROVAL_TTL_MINUTES), "approval_expiry_window_invalid", f"approval expires_at_utc must be exactly {APPROVAL_TTL_MINUTES} minutes after approved_at_utc")
    now = (now or utcnow()).astimezone(timezone.utc)
    if require_not_expired:
        _require(now <= expires_at, "approval_expired", f"approval expired at {expires_at.isoformat()}")

    _require(approval.get("credits_may_be_spent_acknowledged") is True, "approval_credits_acknowledgement_missing", "approval must acknowledge that execution may spend credits")
    _require(approval.get("authorized_attempts") == 1, "approval_authorized_attempts_invalid", "approval authorized_attempts must be exactly 1")
    for key in ("upload_authorized", "queue_promotion_authorized", "publish_authorized", "scheduling_authorized", "analytics_mutation_authorized"):
        _require(approval.get(key) is False, f"approval_scope_{key}_invalid", f"approval {key} must be false")

    date_str = str(approval.get("date") or "").strip()
    slot_id = str(approval.get("slot_id") or "").strip()
    _require(bool(date_str), "approval_date_missing", "approval date is missing")
    _require(bool(slot_id), "approval_slot_missing", "approval slot_id is missing")
    _require(approval.get("recipe_id") == CONTROLLED_RECIPE_ID, "approval_recipe_invalid", f"approval recipe_id must be {CONTROLLED_RECIPE_ID!r}")
    _require(approval.get("wardrobe_outfit_id") == CONTROLLED_WARDROBE_ID, "approval_wardrobe_invalid", f"approval wardrobe_outfit_id must be {CONTROLLED_WARDROBE_ID!r}")

    handoff_path = canonical_approval.resolve_repo_path(
        str(approval.get("handoff_artifact_path") or ""),
        code="approval_handoff_path_missing",
        label="approval handoff_artifact_path",
    )
    candidate_path = canonical_approval.resolve_repo_path(
        str(approval.get("candidate_artifact_path") or ""),
        code="approval_candidate_path_missing",
        label="approval candidate_artifact_path",
    )
    handoff_facts = inspect_generation_handoff_for_standing_autonomy(handoff_path, candidate_path)

    _require(approval.get("handoff_artifact_path") == handoff_facts["handoff_repo_path"], "approval_handoff_path_binding_mismatch", "approval handoff_artifact_path does not match the exact handoff repo-relative path")
    handoff_sha = canonical_approval.require_sha256(approval.get("handoff_artifact_sha256"), code="approval_handoff_sha_missing_or_invalid", label="approval handoff_artifact_sha256")
    _require(handoff_sha == handoff_facts["handoff_sha256"], "approval_handoff_sha_mismatch", "approval handoff_artifact_sha256 does not match the current handoff bytes")
    _require(approval.get("handoff_report_type") == canonical_approval.HANDOFF_REPORT_TYPE, "approval_handoff_report_type_mismatch", "approval handoff_report_type mismatch")
    _require(approval.get("handoff_schema_version") == canonical_approval.HANDOFF_SCHEMA_VERSION, "approval_handoff_schema_version_mismatch", "approval handoff_schema_version mismatch")

    _require(approval.get("candidate_artifact_path") == handoff_facts["candidate_artifact_repo_path"], "approval_candidate_path_binding_mismatch", "approval candidate_artifact_path does not match the exact candidate repo-relative path")
    candidate_sha = canonical_approval.require_sha256(approval.get("candidate_artifact_sha256"), code="approval_candidate_sha_missing_or_invalid", label="approval candidate_artifact_sha256")
    _require(candidate_sha == handoff_facts["candidate_artifact_sha256"], "approval_candidate_sha_mismatch", "approval candidate_artifact_sha256 does not match the current candidate bytes")

    _require(date_str == handoff_facts["date"], "approval_date_binding_mismatch", "approval date does not match the bound handoff date")
    _require(slot_id == handoff_facts["slot_id"], "approval_slot_binding_mismatch", "approval slot_id does not match the bound handoff slot_id")
    _require(approval.get("recipe_id") == handoff_facts["recipe_id"], "approval_recipe_binding_mismatch", "approval recipe_id does not match the bound handoff recipe")
    _require(approval.get("wardrobe_outfit_id") == handoff_facts["wardrobe_outfit_id"], "approval_wardrobe_binding_mismatch", "approval wardrobe_outfit_id does not match the bound handoff wardrobe")
    _require(approval.get("effective_wardrobe_silhouette_class") == handoff_facts["effective_wardrobe_silhouette_class"], "approval_silhouette_binding_mismatch", "approval effective_wardrobe_silhouette_class does not match the bound handoff")

    prompt_sha = canonical_approval.require_sha256(approval.get("prompt_sha256"), code="approval_prompt_sha_missing_or_invalid", label="approval prompt_sha256")
    _require(prompt_sha == handoff_facts["prompt_sha256"], "approval_prompt_sha_mismatch", "approval prompt_sha256 does not match the bound handoff prompt sha")
    _require(approval.get("custom_reference_id") == handoff_facts["custom_reference_id"], "approval_custom_reference_id_mismatch", "approval custom_reference_id does not match the bound handoff")
    try:
        approval_generation_reference = (
            soul_cinema_contract.validate_generation_reference_binding(
                approval.get("generation_reference")
            )
        )
    except soul_cinema_contract.SoulCinemaContractError as exc:
        raise HiggsfieldStandingAutonomyGenerationApprovalError(
            exc.code, exc.detail
        ) from exc
    _require(
        approval_generation_reference == handoff_facts["generation_reference"],
        "approval_generation_reference_mismatch",
        "approval generation reference does not match the bound handoff source image",
    )

    authority_commit = str(approval.get("authority_commit") or "")
    _require(len(authority_commit) == 40 and authority_commit == handoff_facts["authority_commit"], "approval_authority_commit_mismatch", "approval authority_commit does not match the bound candidate")
    _require(approval.get("decision_fingerprint_sha256") == handoff_facts["decision_fingerprint_sha256"], "approval_decision_fingerprint_mismatch", "approval decision_fingerprint_sha256 does not match the bound candidate")

    _require(approval.get("pose_provenance") == handoff_facts["pose_provenance"], "approval_pose_provenance_mismatch", "approval pose_provenance does not match the bound handoff")
    _require(approval.get("expression_provenance") == handoff_facts["expression_provenance"], "approval_expression_provenance_mismatch", "approval expression_provenance does not match the bound handoff")
    _require(
        approval.get("pose_bound_content_packet_sha256") == handoff_facts["pose_bound_content_packet_sha256"],
        "approval_pose_bound_packet_mismatch",
        "approval pose_bound_content_packet_sha256 does not match the bound handoff",
    )
    _require(
        approval.get("expression_bound_content_packet_sha256") == handoff_facts["expression_bound_content_packet_sha256"],
        "approval_expression_bound_packet_mismatch",
        "approval expression_bound_content_packet_sha256 does not match the bound handoff",
    )

    approval_authority_blocks = canonical_approval.validate_authority_snapshots_against_handoff(approval, handoff_facts, owner="approval")

    for key, expected in (
        ("provider", handoff_facts["provider"]),
        ("executor", handoff_facts["executor"]),
        ("model", handoff_facts["model"]),
        ("aspect_ratio", handoff_facts["aspect_ratio"]),
        ("soul_name", handoff_facts["soul_name"]),
        ("soul_type", handoff_facts["soul_type"]),
    ):
        _require(approval.get(key) == expected, f"approval_{key}_mismatch", f"approval {key} must be {expected!r}")

    standing_auth_path = canonical_approval.resolve_repo_path(
        str(approval.get("standing_authorization_artifact_path") or ""),
        code="standing_authorization_path_missing",
        label="standing authorization artifact",
    )
    try:
        standing_authorization_result = standing_autonomy.validate_cycle_authorization_artifact(
            standing_auth_path,
            allow_consumed=True,
        )
    except standing_autonomy.StandingAutonomyPolicyError as exc:
        raise HiggsfieldStandingAutonomyGenerationApprovalError(exc.code, exc.detail) from exc
    standing_auth = standing_authorization_result["artifact"]
    _require(standing_auth.get("consumed") is True, "standing_authorization_not_consumed", "standing authorization must be consumed")
    _require(
        approval.get("standing_authorization_artifact_path") == repo_relative_path(standing_auth_path),
        "standing_authorization_path_mismatch",
        "approval does not use the canonical standing authorization path",
    )
    _require(
        approval.get("standing_authorization_artifact_sha256") == sha256_file(standing_auth_path),
        "standing_authorization_sha_mismatch",
        "approval standing authorization SHA does not match current bytes",
    )
    controlled = standing_auth.get("controlled_photo_autonomy")
    _require(isinstance(controlled, dict) and controlled.get("enabled") is True, "standing_authorization_scope_invalid", "controlled photo autonomy is not enabled")
    _require(controlled.get("recipe_id") == CONTROLLED_RECIPE_ID, "standing_authorization_recipe_invalid", f"standing authorization recipe must be {CONTROLLED_RECIPE_ID!r}")
    _require(controlled.get("wardrobe_outfit_id") == CONTROLLED_WARDROBE_ID, "standing_authorization_wardrobe_invalid", f"standing authorization wardrobe must be {CONTROLLED_WARDROBE_ID!r}")
    _require(int(standing_auth.get("provider_call_cap_per_cycle", 0)) == 2, "standing_provider_cap_invalid", "standing provider cap must be two")
    _require(int(standing_auth.get("retry_cap_per_cycle", -1)) == 1, "standing_retry_cap_invalid", "standing retry cap must be one")
    _require(standing_auth.get("slot_id") == slot_id, "standing_generation_slot_mismatch", "standing authorization slot differs from the approval")
    _require(standing_auth.get("date") == date_str, "standing_generation_date_mismatch", "standing authorization date differs from the approval")
    _require(standing_auth.get("candidate_artifact_sha256") == handoff_facts["candidate_artifact_sha256"], "standing_generation_candidate_sha_mismatch", "standing authorization candidate SHA differs from the bound candidate")
    _require(standing_auth.get("generation_handoff_artifact_sha256") == handoff_facts["handoff_sha256"], "standing_generation_handoff_sha_mismatch", "standing authorization handoff SHA differs from the bound handoff")
    _require(standing_auth.get("prompt_sha256") == handoff_facts["prompt_sha256"], "standing_generation_prompt_sha_mismatch", "standing authorization prompt SHA differs from the bound handoff")
    _require(approval.get("standing_authorization_cycle_id") == standing_auth.get("cycle_id"), "standing_cycle_id_mismatch", "approval cycle ID differs from the standing authorization")
    _require(approval.get("standing_policy_artifact_sha256") == standing_auth.get("policy_artifact_sha256"), "standing_policy_sha_mismatch", "approval policy SHA differs from the standing authorization")

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
            "scheduling_authorized": approval["scheduling_authorized"],
            "analytics_mutation_authorized": approval["analytics_mutation_authorized"],
        },
        "authority_blocks": approval_authority_blocks,
        "standing_authorization_result": standing_authorization_result,
    }


def write_standing_autonomy_generation_approval_record_atomic(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise HiggsfieldStandingAutonomyGenerationApprovalError(
            "approval_already_exists",
            f"refusing to overwrite an existing standing-autonomy generation approval artifact: {path}",
        )
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    try:
        temp_path.write_text(payload, encoding="utf-8")
        validate_standing_autonomy_generation_approval_artifact(temp_path, require_not_expired=False)
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


# --- Claim lineage -----------------------------------------------------------

def build_standing_autonomy_generation_claim_record(
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
        "candidate_artifact_path": handoff_facts["candidate_artifact_repo_path"],
        "candidate_artifact_sha256": handoff_facts["candidate_artifact_sha256"],
        "date": date_str,
        "slot_id": slot_id,
        "recipe_id": handoff_facts["recipe_id"],
        "wardrobe_outfit_id": handoff_facts["wardrobe_outfit_id"],
        "prompt_sha256": handoff_facts["prompt_sha256"],
        "authority_commit": handoff_facts["authority_commit"],
        "candidate_selection_binding": handoff_facts["candidate_selection_binding"],
        "provider_execution_binding": handoff_facts["provider_execution_binding"],
        "binding_linkage": handoff_facts["binding_linkage"],
        "operator_id": approval["operator_id"],
        "provider": approval["provider"],
        "executor": approval["executor"],
        "model": approval["model"],
        "aspect_ratio": approval["aspect_ratio"],
        "soul_name": approval["soul_name"],
        "soul_type": approval["soul_type"],
        "custom_reference_id": approval["custom_reference_id"],
        "generation_reference": approval["generation_reference"],
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
        "analytics_mutation_authorized": False,
    }


def validate_standing_autonomy_generation_claim_lineage(
    record: Any,
    *,
    claim_path: Path | None = None,
) -> dict[str, Any]:
    owner = "standing_autonomy_generation_claim"
    _require(isinstance(record, dict) and record.get("report_type") == CLAIM_REPORT_TYPE, f"{owner}_report_type_mismatch", f"{owner} report_type must be {CLAIM_REPORT_TYPE!r}")
    _require(record.get("schema_version") == CLAIM_SCHEMA_VERSION, f"{owner}_schema_version_mismatch", f"{owner} schema_version must be {CLAIM_SCHEMA_VERSION!r}")
    _require(record.get("claim_type") == CLAIM_TYPE, f"{owner}_type_mismatch", f"{owner} claim_type must be {CLAIM_TYPE!r}")
    try:
        canonical_approval.parse_iso8601_utc(record.get("claimed_at_utc"), code=f"{owner}_claimed_at_invalid", label=f"{owner} claimed_at_utc")
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc

    approval_path = canonical_approval.resolve_repo_path(
        str(record.get("approval_artifact_path") or ""),
        code=f"{owner}_approval_path_missing",
        label=f"{owner} approval_artifact_path",
    )
    approval_result = validate_standing_autonomy_generation_approval_artifact(approval_path, require_not_expired=False)
    handoff_facts = approval_result["handoff_facts"]
    date_str = handoff_facts["date"]
    slot_id = handoff_facts["slot_id"]

    _require(record.get("approval_artifact_path") == approval_result["approval_repo_path"], f"{owner}_approval_path_mismatch", f"{owner} approval_artifact_path must be canonical")
    _require(record.get("approval_artifact_sha256") == approval_result["approval_sha256"], f"{owner}_approval_sha_mismatch", f"{owner} approval_artifact_sha256 must match the validated approval")

    if claim_path is not None:
        _require(claim_path.resolve() == claim_output_path(date_str, slot_id).resolve(), f"{owner}_path_mismatch", f"{owner} artifact path must be the canonical claim path for the validated slot")

    for key in (
        "handoff_artifact_path", "handoff_artifact_sha256",
        "candidate_artifact_path", "candidate_artifact_sha256",
        "date", "slot_id", "recipe_id", "wardrobe_outfit_id",
        "prompt_sha256", "authority_commit",
        "candidate_selection_binding", "provider_execution_binding", "binding_linkage",
        "operator_id", "provider", "executor", "model", "aspect_ratio",
        "soul_name", "soul_type", "custom_reference_id", "generation_reference",
    ):
        expected = {
            "handoff_artifact_path": handoff_facts["handoff_repo_path"],
            "handoff_artifact_sha256": handoff_facts["handoff_sha256"],
            "candidate_artifact_path": handoff_facts["candidate_artifact_repo_path"],
            "candidate_artifact_sha256": handoff_facts["candidate_artifact_sha256"],
            "date": handoff_facts["date"],
            "slot_id": handoff_facts["slot_id"],
            "recipe_id": handoff_facts["recipe_id"],
            "wardrobe_outfit_id": handoff_facts["wardrobe_outfit_id"],
            "prompt_sha256": handoff_facts["prompt_sha256"],
            "authority_commit": handoff_facts["authority_commit"],
            "candidate_selection_binding": handoff_facts["candidate_selection_binding"],
            "provider_execution_binding": handoff_facts["provider_execution_binding"],
            "binding_linkage": handoff_facts["binding_linkage"],
            "operator_id": approval_result["approval"]["operator_id"],
            "provider": approval_result["approval"]["provider"],
            "executor": approval_result["approval"]["executor"],
            "model": approval_result["approval"]["model"],
            "aspect_ratio": approval_result["approval"]["aspect_ratio"],
            "soul_name": approval_result["approval"]["soul_name"],
            "soul_type": approval_result["approval"]["soul_type"],
            "custom_reference_id": approval_result["approval"]["custom_reference_id"],
            "generation_reference": approval_result["approval"]["generation_reference"],
        }[key]
        _require(record.get(key) == expected, f"{owner}_{key}_mismatch", f"{owner} {key} must exactly match the validated approval lineage")

    expected_values = {
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
        "analytics_mutation_authorized": False,
    }
    for key, expected in expected_values.items():
        _require(record.get(key) == expected, f"{owner}_{key}_mismatch", f"{owner} {key} must match the canonical claim contract")

    return {"approval_result": approval_result, "handoff_facts": handoff_facts}


def write_standing_autonomy_generation_claim_atomic(path: Path, record: dict[str, Any]) -> None:
    validate_standing_autonomy_generation_claim_lineage(record, claim_path=path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    try:
        temp_path.write_text(payload, encoding="utf-8")
        os.link(str(temp_path), str(path))
    except FileExistsError as exc:
        raise HiggsfieldStandingAutonomyGenerationApprovalError(
            "standing_autonomy_generation_claim_already_exists",
            f"refusing to overwrite an existing standing-autonomy generation claim artifact: {path}",
        ) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()


# --- Receipt lineage ----------------------------------------------------------

def build_standing_autonomy_generation_execution_receipt_record(
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
    generated_image_sha256: str | None = None,
    manifest_sha256: str | None = None,
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
        "candidate_artifact_path": handoff_facts["candidate_artifact_repo_path"],
        "candidate_artifact_sha256": handoff_facts["candidate_artifact_sha256"],
        "date": date_str,
        "slot_id": slot_id,
        "recipe_id": handoff_facts["recipe_id"],
        "wardrobe_outfit_id": handoff_facts["wardrobe_outfit_id"],
        "prompt_sha256": handoff_facts["prompt_sha256"],
        "authority_commit": handoff_facts["authority_commit"],
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
        "generated_image_sha256": generated_image_sha256,
        "manifest_sha256": manifest_sha256,
        "operator_id": approval["operator_id"],
        "provider": approval["provider"],
        "executor": approval["executor"],
        "model": approval["model"],
        "aspect_ratio": approval["aspect_ratio"],
        "soul_name": approval["soul_name"],
        "soul_type": approval["soul_type"],
        "custom_reference_id": approval["custom_reference_id"],
        "generation_reference": approval["generation_reference"],
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }


def validate_standing_autonomy_generation_receipt_lineage(
    record: Any,
    *,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    owner = "standing_autonomy_generation_receipt"
    _require(isinstance(record, dict) and record.get("report_type") == RECEIPT_REPORT_TYPE, f"{owner}_report_type_mismatch", f"{owner} report_type must be {RECEIPT_REPORT_TYPE!r}")
    _require(record.get("schema_version") == RECEIPT_SCHEMA_VERSION, f"{owner}_schema_version_mismatch", f"{owner} schema_version must be {RECEIPT_SCHEMA_VERSION!r}")
    _require(record.get("receipt_type") == RECEIPT_TYPE, f"{owner}_type_mismatch", f"{owner} receipt_type must be {RECEIPT_TYPE!r}")
    try:
        canonical_approval.parse_iso8601_utc(record.get("receipt_written_at_utc"), code=f"{owner}_written_at_invalid", label=f"{owner} receipt_written_at_utc")
    except canonical_approval.HiggsfieldGenerationApprovalError as exc:
        raise _translate_canonical_error(exc) from exc

    claim_path = canonical_approval.resolve_repo_path(
        str(record.get("claim_artifact_path") or ""),
        code=f"{owner}_claim_path_missing",
        label=f"{owner} claim_artifact_path",
    )
    _require(record.get("claim_artifact_path") == repo_relative_path(claim_path), f"{owner}_claim_path_noncanonical", f"{owner} claim_artifact_path must use the canonical path")
    claim_sha = canonical_approval.require_sha256(record.get("claim_artifact_sha256"), code=f"{owner}_claim_sha_invalid", label=f"{owner} claim_artifact_sha256")
    _require(claim_path.is_file(), f"{owner}_claim_missing", f"{owner} referenced claim artifact is missing: {claim_path}")
    _require(sha256_file(claim_path) == claim_sha, f"{owner}_claim_sha_mismatch", f"{owner} claim_artifact_sha256 does not match the referenced claim bytes")

    claim = canonical_approval.read_json_object(claim_path, code=f"{owner}_claim_invalid", label=f"{owner} claim artifact")
    claim_lineage = validate_standing_autonomy_generation_claim_lineage(claim, claim_path=claim_path)
    handoff_facts = claim_lineage["handoff_facts"]
    date_str = handoff_facts["date"]
    slot_id = handoff_facts["slot_id"]

    if receipt_path is not None:
        _require(receipt_path.resolve() == receipt_output_path(date_str, slot_id).resolve(), f"{owner}_path_mismatch", f"{owner} artifact path must be the canonical receipt path for the validated slot")

    _require(
        record.get("approval_artifact_sha256") == claim_lineage["approval_result"]["approval_sha256"],
        f"{owner}_claim_approval_mismatch",
        f"{owner} and its claim must bind the same validated approval artifact",
    )

    for key in (
        "approval_artifact_path", "handoff_artifact_path", "handoff_artifact_sha256",
        "candidate_artifact_path", "candidate_artifact_sha256",
        "date", "slot_id", "recipe_id", "wardrobe_outfit_id", "prompt_sha256", "authority_commit",
        "operator_id", "provider", "executor", "model", "aspect_ratio", "soul_name", "soul_type", "custom_reference_id", "generation_reference",
    ):
        _require(record.get(key) == claim.get(key), f"{owner}_claim_{key}_mismatch", f"{owner} {key} must exactly match the validated claim lineage")

    expected_values = {
        "expected_manifest_path": repo_relative_path(canonical_approval.expected_manifest_path(date_str, slot_id)),
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }
    for key, expected in expected_values.items():
        _require(record.get(key) == expected, f"{owner}_{key}_mismatch", f"{owner} {key} must match the canonical receipt contract")

    return {**claim_lineage, "claim": claim, "claim_path": claim_path, "claim_sha256": claim_sha}


def write_standing_autonomy_generation_execution_receipt_atomic(path: Path, record: dict[str, Any]) -> None:
    validate_standing_autonomy_generation_receipt_lineage(record, receipt_path=path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    try:
        temp_path.write_text(payload, encoding="utf-8")
        os.link(str(temp_path), str(path))
    except FileExistsError as exc:
        raise HiggsfieldStandingAutonomyGenerationApprovalError(
            "standing_autonomy_generation_execution_receipt_already_exists",
            f"refusing to overwrite an existing standing-autonomy generation execution receipt artifact: {path}",
        ) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()
