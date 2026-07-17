from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pipeline.presence.human_presence_candidate_ranking_v1 import plan_fingerprint_sha256


SCHEMA_VERSION_V1 = "human_presence_output_qa_v1"
SCHEMA_VERSION_V2 = "human_presence_output_qa_v2"
SCHEMA_VERSION = SCHEMA_VERSION_V2
REPORT_TYPE = "human_presence_output_qa"
SUPPORTED_MEDIA_TYPES = frozenset({"still_image"})
INTEGRITY_PASS = "integrity_pass"
INTEGRITY_FAILURE = "integrity_failure"
NOT_ASSESSABLE = "not_assessable"
SEMANTIC_STATUS_ENUM = (
    "not_evaluated",
    "not_assessable",
    "aligned",
    "findings_present",
    "error",
)
FINDING_CODES = (
    "pose_plan_contradiction",
    "gaze_plan_contradiction",
    "expression_plan_contradiction",
    "body_language_plan_contradiction",
    "object_interaction_plan_contradiction",
    "environment_interaction_mismatch",
    "dead_eye_presence",
    "frozen_expression_presence",
    "mannequin_pose_presence",
)
FINDING_CATEGORIES = (
    "plan_contradiction",
    "presence_failure_indicator",
    "environment_mismatch",
)
SEMANTIC_ERROR_CODES = (
    "semantic_visual_review_timeout",
    "semantic_visual_review_rate_limit",
    "semantic_visual_review_provider_unavailable",
    "semantic_visual_review_malformed_payload",
    "semantic_visual_review_invalid_payload",
    "semantic_visual_review_config_missing",
    "semantic_visual_review_unsupported_media",
    "semantic_visual_review_image_unreadable",
    "semantic_visual_review_internal_error",
)
SEMANTIC_RESPONSE_SCHEMA_VERSION = "human_presence_semantic_visual_observations_v1"
_SEMANTIC_RESULT_REQUIRED_KEYS = frozenset({
    "semantic_status",
    "semantic_findings",
    "semantic_result_provenance",
    "semantic_error",
})
_SEMANTIC_FINDING_KEYS = frozenset({
    "finding_code",
    "category",
    "plan_field_ref",
    "plan_field_value",
    "observed_description",
    "confidence",
    "image_index",
    "advisory_only",
})
_SEMANTIC_FINDING_CONFIDENCE = frozenset({"high", "medium", "low"})
_STILL_IMAGE_PLAN_FIELD_ALLOWLIST = (
    "viewer_relationship.awareness",
    "viewer_relationship.performance_level",
    "viewer_relationship.invitation_level",
    "gaze_arc.start_focus",
    "gaze_arc.recognition_behavior",
    "gaze_arc.hold_intensity",
    "expression_arc.start_state",
    "expression_arc.peak_state",
    "performance_actions.primary_action",
    "performance_actions.object_interaction",
    "movement_dynamics.weight_transfer",
    "movement_dynamics.asymmetry_level",
    "body_presentation.adult_character_required",
    "body_presentation.silhouette_profile.bust_emphasis",
    "body_presentation.silhouette_profile.waist_hip_contrast",
    "body_presentation.silhouette_profile.hip_glute_emphasis",
    "body_presentation.silhouette_profile.proportion_realism",
    "body_presentation.silhouette_profile.silhouette_shape_class",
    "body_presentation.wardrobe_body_interaction",
    "body_presentation.anatomy_continuity_required",
    "body_presentation.gravity_and_soft_tissue_realism",
    "body_presentation.framing_intent",
    "sensual_presence.tier",
    "sensual_presence.exposure_dependency",
    "sensual_presence.confidence_level",
    "failure_indicators.dead_or_unfocused_eyes",
    "failure_indicators.frozen_expression",
    "failure_indicators.mannequin_pose",
    "failure_indicators.face_body_emotion_mismatch",
    "failure_indicators.sexual_styling_without_personality",
)
_SEMANTIC_FINDING_TO_CATEGORY = {
    "pose_plan_contradiction": "plan_contradiction",
    "gaze_plan_contradiction": "plan_contradiction",
    "expression_plan_contradiction": "plan_contradiction",
    "body_language_plan_contradiction": "plan_contradiction",
    "object_interaction_plan_contradiction": "plan_contradiction",
    "environment_interaction_mismatch": "environment_mismatch",
    "dead_eye_presence": "presence_failure_indicator",
    "frozen_expression_presence": "presence_failure_indicator",
    "mannequin_pose_presence": "presence_failure_indicator",
}
_SEMANTIC_FINDING_TO_PLAN_REF = {
    "pose_plan_contradiction": "performance_actions.primary_action",
    "gaze_plan_contradiction": "gaze_arc.start_focus",
    "expression_plan_contradiction": "expression_arc.peak_state",
    "body_language_plan_contradiction": "movement_dynamics.weight_transfer",
    "object_interaction_plan_contradiction": "performance_actions.object_interaction",
    "environment_interaction_mismatch": "body_presentation.framing_intent",
    "dead_eye_presence": "failure_indicators.dead_or_unfocused_eyes",
    "frozen_expression_presence": "failure_indicators.frozen_expression",
    "mannequin_pose_presence": "failure_indicators.mannequin_pose",
}
_SEMANTIC_FINDING_DETAIL_LIMIT = 300
_SEMANTIC_FINDING_IMAGE_INDEX = 0
_SEMANTIC_RESULT_PROVENANCE_KEYS = frozenset({
    "provider",
    "model",
    "request_binding_sha256",
    "evaluated_at_utc",
    "response_schema_version",
})

_BINDING_NAMES = ("plan", "candidate_decision", "manifest", "generated_image")
_BINDING_STATUSES = frozenset(
    {"verified", "mismatch", "structurally_validated", "observed_only", "not_assessable"}
)
_REQUIRED_ARTIFACT_KEYS = frozenset({
    "report_type",
    "schema_version",
    "medium",
    "evaluator_version",
    "generated_at_utc",
    "integrity_status",
    "integrity_findings",
    "semantic_status",
    "semantic_findings",
    "binding_records",
    "source_artifacts",
    "recommendation",
})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_INTEGRITY_STATUS_TO_RECOMMENDATION = {
    "valid": INTEGRITY_PASS,
    "invalid": INTEGRITY_FAILURE,
    "not_assessable": NOT_ASSESSABLE,
}


class HumanPresenceOutputQAError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _require_sha256(value: Any, label: str, *, allow_none: bool = False) -> str | None:
    if value is None:
        if allow_none:
            return None
        raise HumanPresenceOutputQAError(
            "presence_output_invalid_sha256",
            f"{label} is missing",
        )
    value = str(value).lower()
    if not _SHA256_RE.fullmatch(value):
        raise HumanPresenceOutputQAError(
            "presence_output_invalid_sha256",
            f"{label} must be exactly 64 lowercase hexadecimal characters",
        )
    return value


def _validate_source_path(value: Any, label: str, *, allow_none: bool = True) -> str | None:
    if value is None:
        if allow_none:
            return None
        raise HumanPresenceOutputQAError("presence_output_invalid_path", f"{label} is missing")
    if not isinstance(value, str) or not value:
        raise HumanPresenceOutputQAError("presence_output_invalid_path", f"{label} must be a non-empty string")
    return value


def _default_not_assessable_findings(reason: str, *, binding_name: str | None = None) -> list[dict[str, Any]]:
    finding: dict[str, Any] = {
        "finding_code": reason,
        "dimension": "integrity",
        "severity": "info",
    }
    if binding_name is not None:
        finding["binding_name"] = binding_name
    return [finding]


def _binding_record(
    *,
    binding_name: str,
    binding_status: str,
    observed_sha256: str | None,
    expected_sha256: str | None,
    verification_basis: str,
    source_path: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if binding_name not in _BINDING_NAMES:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"binding_name {binding_name!r} is not supported",
        )
    if binding_status not in _BINDING_STATUSES:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"binding_status {binding_status!r} is not supported",
        )
    observed = _require_sha256(observed_sha256, f"{binding_name} observed_sha256", allow_none=True)
    expected = _require_sha256(expected_sha256, f"{binding_name} expected_sha256", allow_none=True)
    if binding_status in {"verified", "mismatch"} and (observed is None or expected is None):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"{binding_name} binding {binding_status!r} requires both observed and expected sha256 values",
        )
    if binding_status in {"structurally_validated", "observed_only"}:
        if observed is None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                f"{binding_name} binding {binding_status!r} requires an observed sha256 value",
            )
        if expected is not None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                f"{binding_name} binding {binding_status!r} may not carry an expected sha256 value",
            )
    if binding_status == "not_assessable":
        if expected is not None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                f"{binding_name} binding 'not_assessable' may not carry an expected sha256 value",
            )
    if not isinstance(verification_basis, str) or not verification_basis.strip():
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"{binding_name} verification_basis must be a non-empty string",
        )
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"{binding_name} details must be a JSON object",
        )
    source_path = _validate_source_path(source_path, f"{binding_name} source_path")
    return {
        "binding_name": binding_name,
        "binding_status": binding_status,
        "observed_sha256": observed,
        "expected_sha256": expected,
        "verification_basis": verification_basis,
        "source_path": source_path,
        "details": details,
    }


def _binding_record_from_result(
    record: dict[str, Any],
    *,
    source_path: str | None,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "binding_records must contain JSON objects",
        )
    merged = dict(record)
    merged["source_path"] = source_path if source_path is not None else merged.get("source_path")
    return _binding_record(
        binding_name=str(merged.get("binding_name") or ""),
        binding_status=str(merged.get("binding_status") or ""),
        observed_sha256=merged.get("observed_sha256"),
        expected_sha256=merged.get("expected_sha256"),
        verification_basis=str(merged.get("verification_basis") or ""),
        source_path=merged.get("source_path"),
        details=merged.get("details") if isinstance(merged.get("details"), dict) else {},
    )


def _binding_findings(binding_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in binding_records:
        status = record["binding_status"]
        name = record["binding_name"]
        if status == "verified":
            continue
        if status == "mismatch":
            findings.append(
                {
                    "finding_code": f"{name}_mismatch",
                    "dimension": "integrity",
                    "severity": "critical",
                    "binding_name": name,
                    "observed": record["observed_sha256"],
                    "expected": record["expected_sha256"],
                }
            )
            continue
        findings.append(
            {
                "finding_code": f"{name}_{status}",
                "dimension": "integrity",
                "severity": "info",
                "binding_name": name,
                "observed": record["observed_sha256"],
                "expected": record["expected_sha256"],
                "verification_basis": record["verification_basis"],
            }
        )
    return findings


def _status_from_binding_records(binding_records: list[dict[str, Any]]) -> str:
    if any(record["binding_status"] == "mismatch" for record in binding_records):
        return "invalid"
    if all(record["binding_status"] == "verified" for record in binding_records):
        return "valid"
    return "not_assessable"


def _no_hpe_binding_records(source_artifacts: dict[str, str]) -> list[dict[str, Any]]:
    return [
        _binding_record(
            binding_name="plan",
            binding_status="not_assessable",
            observed_sha256=None,
            expected_sha256=None,
            verification_basis="hpe_not_requested",
            source_path=source_artifacts.get("plan_path"),
            details={"reason": "hpe_not_requested"},
        ),
        _binding_record(
            binding_name="candidate_decision",
            binding_status="not_assessable",
            observed_sha256=None,
            expected_sha256=None,
            verification_basis="hpe_not_requested",
            source_path=source_artifacts.get("candidate_decision_path"),
            details={"reason": "hpe_not_requested"},
        ),
        _binding_record(
            binding_name="manifest",
            binding_status="not_assessable",
            observed_sha256=None,
            expected_sha256=None,
            verification_basis="hpe_not_requested",
            source_path=source_artifacts.get("manifest_path"),
            details={"reason": "hpe_not_requested"},
        ),
        _binding_record(
            binding_name="generated_image",
            binding_status="not_assessable",
            observed_sha256=None,
            expected_sha256=None,
            verification_basis="hpe_not_requested",
            source_path=source_artifacts.get("image_path"),
            details={"reason": "hpe_not_requested"},
        ),
    ]


def _load_expected_sha_from_artifact(
    artifact: dict[str, Any],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = artifact.get(key)
        if _is_sha256(value):
            return str(value).lower()
    return None


def _plan_path_get(plan: dict[str, Any], *path: str) -> Any:
    current: Any = plan
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                f"plan is missing required field {'.'.join(path)}",
            )
        current = current[key]
    return current


def _failure_indicator_value(plan: dict[str, Any], name: str) -> bool:
    indicators = _plan_path_get(plan, "failure_indicators")
    if not isinstance(indicators, list) or not all(isinstance(item, str) for item in indicators):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "plan failure_indicators must be a JSON array of strings",
        )
    return name in indicators


def _still_image_plan_field_values(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "viewer_relationship.awareness": _plan_path_get(plan, "viewer_relationship", "contract", "awareness"),
        "viewer_relationship.performance_level": _plan_path_get(plan, "viewer_relationship", "contract", "performance_level"),
        "viewer_relationship.invitation_level": _plan_path_get(plan, "viewer_relationship", "contract", "invitation_level"),
        "gaze_arc.start_focus": _plan_path_get(plan, "gaze_arc", "contract", "start_focus"),
        "gaze_arc.recognition_behavior": _plan_path_get(plan, "gaze_arc", "contract", "recognition_behavior"),
        "gaze_arc.hold_intensity": _plan_path_get(plan, "gaze_arc", "contract", "hold_intensity"),
        "expression_arc.start_state": _plan_path_get(plan, "expression_arc", "contract", "start_state"),
        "expression_arc.peak_state": _plan_path_get(plan, "expression_arc", "contract", "peak_state"),
        "performance_actions.primary_action": _plan_path_get(plan, "performance_actions", "contract", "primary_action"),
        "performance_actions.object_interaction": _plan_path_get(plan, "performance_actions", "contract", "object_interaction"),
        "movement_dynamics.weight_transfer": _plan_path_get(plan, "movement_dynamics", "contract", "weight_transfer"),
        "movement_dynamics.asymmetry_level": _plan_path_get(plan, "movement_dynamics", "contract", "asymmetry_level"),
        "body_presentation.adult_character_required": _plan_path_get(plan, "body_presentation", "contract", "adult_character_required"),
        "body_presentation.silhouette_profile.bust_emphasis": _plan_path_get(plan, "body_presentation", "contract", "silhouette_profile", "bust_emphasis"),
        "body_presentation.silhouette_profile.waist_hip_contrast": _plan_path_get(plan, "body_presentation", "contract", "silhouette_profile", "waist_hip_contrast"),
        "body_presentation.silhouette_profile.hip_glute_emphasis": _plan_path_get(plan, "body_presentation", "contract", "silhouette_profile", "hip_glute_emphasis"),
        "body_presentation.silhouette_profile.proportion_realism": _plan_path_get(plan, "body_presentation", "contract", "silhouette_profile", "proportion_realism"),
        "body_presentation.silhouette_profile.silhouette_shape_class": _plan_path_get(plan, "body_presentation", "contract", "silhouette_profile", "silhouette_shape_class"),
        "body_presentation.wardrobe_body_interaction": _plan_path_get(plan, "body_presentation", "contract", "wardrobe_body_interaction"),
        "body_presentation.anatomy_continuity_required": _plan_path_get(plan, "body_presentation", "contract", "anatomy_continuity_required"),
        "body_presentation.gravity_and_soft_tissue_realism": _plan_path_get(plan, "body_presentation", "contract", "gravity_and_soft_tissue_realism"),
        "body_presentation.framing_intent": _plan_path_get(plan, "body_presentation", "contract", "framing_intent"),
        "sensual_presence.tier": _plan_path_get(plan, "sensual_presence", "contract", "tier"),
        "sensual_presence.exposure_dependency": _plan_path_get(plan, "sensual_presence", "contract", "exposure_dependency"),
        "sensual_presence.confidence_level": _plan_path_get(plan, "sensual_presence", "contract", "confidence_level"),
        "failure_indicators.dead_or_unfocused_eyes": _failure_indicator_value(plan, "dead_or_unfocused_eyes"),
        "failure_indicators.frozen_expression": _failure_indicator_value(plan, "frozen_expression"),
        "failure_indicators.mannequin_pose": _failure_indicator_value(plan, "mannequin_pose"),
        "failure_indicators.face_body_emotion_mismatch": _failure_indicator_value(plan, "face_body_emotion_mismatch"),
        "failure_indicators.sexual_styling_without_personality": _failure_indicator_value(plan, "sexual_styling_without_personality"),
    }


def _semantics_base_result(
    *,
    semantic_status: str,
    semantic_findings: list[dict[str, Any]] | None = None,
    semantic_result_provenance: dict[str, Any] | None = None,
    semantic_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "semantic_status": semantic_status,
        "semantic_findings": semantic_findings or [],
        "semantic_result_provenance": semantic_result_provenance,
        "semantic_error": semantic_error,
    }


def _semantic_error_payload(error_code: str, error_message: str) -> dict[str, Any]:
    if error_code not in SEMANTIC_ERROR_CODES:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic error code {error_code!r} is not supported",
        )
    if not isinstance(error_message, str) or not error_message.strip():
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "semantic error message must be a non-empty string",
        )
    return {"error_code": error_code, "error_message": error_message.strip()[:500]}


def _semantic_provenance_payload(
    *,
    provider: str,
    model: str,
    request_binding_sha256: str,
    evaluated_at_utc: str,
    response_schema_version: str,
) -> dict[str, Any]:
    if not isinstance(model, str) or not model.strip():
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "semantic model must be a non-empty string",
        )
    request_binding_sha256 = _require_sha256(request_binding_sha256, "request_binding_sha256")
    if not isinstance(evaluated_at_utc, str) or not evaluated_at_utc.strip():
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "evaluated_at_utc must be a non-empty string",
        )
    if response_schema_version != SEMANTIC_RESPONSE_SCHEMA_VERSION:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "semantic response schema version mismatch",
        )
    return {
        "provider": provider,
        "model": model,
        "request_binding_sha256": request_binding_sha256,
        "evaluated_at_utc": evaluated_at_utc,
        "response_schema_version": response_schema_version,
    }


def _semantic_findings_or_empty(findings: Any) -> list[dict[str, Any]]:
    if findings is None:
        return []
    if not isinstance(findings, list):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "semantic_findings must be a JSON array",
        )
    return findings


def _validate_semantic_finding(
    finding: Any,
    *,
    image_index: int,
    plan_values: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(finding, dict):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "semantic findings must contain JSON objects",
        )
    if set(finding) != _SEMANTIC_FINDING_KEYS:
        extra = sorted(set(finding) - _SEMANTIC_FINDING_KEYS)
        missing = sorted(_SEMANTIC_FINDING_KEYS - set(finding))
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic finding keys must match the approved schema; missing={missing}, extra={extra}",
        )
    code = finding["finding_code"]
    category = finding["category"]
    plan_field_ref = finding["plan_field_ref"]
    observed_description = finding["observed_description"]
    confidence = finding["confidence"]
    finding_image_index = finding["image_index"]
    advisory_only = finding["advisory_only"]
    if code not in FINDING_CODES:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"finding_code {code!r} is not supported",
        )
    expected_category = _SEMANTIC_FINDING_TO_CATEGORY.get(code)
    if category not in FINDING_CATEGORIES or expected_category != category:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"finding category {category!r} is not compatible with {code!r}",
        )
    expected_ref = _SEMANTIC_FINDING_TO_PLAN_REF.get(code)
    if plan_field_ref not in _STILL_IMAGE_PLAN_FIELD_ALLOWLIST or expected_ref != plan_field_ref:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"plan_field_ref {plan_field_ref!r} is not allowed for {code!r}",
        )
    if plan_field_ref not in plan_values:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"plan_field_ref {plan_field_ref!r} was not present in the approved plan subset",
        )
    if finding.get("plan_field_value") != plan_values[plan_field_ref]:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"plan_field_value for {plan_field_ref!r} does not match the compiled plan",
        )
    if not isinstance(observed_description, str) or not observed_description.strip():
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "observed_description must be a non-empty string",
        )
    if len(observed_description) > _SEMANTIC_FINDING_DETAIL_LIMIT:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "observed_description is too long",
        )
    if confidence not in _SEMANTIC_FINDING_CONFIDENCE:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"confidence {confidence!r} is not supported",
        )
    if finding_image_index != image_index:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"image_index {finding_image_index!r} does not match the requested image index",
        )
    if not isinstance(advisory_only, bool):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "advisory_only must be boolean",
        )
    return {
        "finding_code": code,
        "category": category,
        "plan_field_ref": plan_field_ref,
        "plan_field_value": finding["plan_field_value"],
        "observed_description": observed_description.strip(),
        "confidence": confidence,
        "image_index": finding_image_index,
        "advisory_only": advisory_only,
    }


def _validate_semantic_result(
    value: Any,
    *,
    image_index: int,
    plan_values: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "semantic result must be a JSON object",
        )
    public_keys = {key for key in value if not str(key).startswith("_")}
    if public_keys != _SEMANTIC_RESULT_REQUIRED_KEYS:
        missing = sorted(_SEMANTIC_RESULT_REQUIRED_KEYS - public_keys)
        extra = sorted(public_keys - _SEMANTIC_RESULT_REQUIRED_KEYS)
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic result keys must match the approved schema; missing={missing}, extra={extra}",
        )
    status = value["semantic_status"]
    if status not in SEMANTIC_STATUS_ENUM:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic_status {status!r} is not supported",
        )
    findings = _semantic_findings_or_empty(value["semantic_findings"])
    validated_findings = [_validate_semantic_finding(finding, image_index=image_index, plan_values=plan_values) for finding in findings]
    provenance = value["semantic_result_provenance"]
    error = value["semantic_error"]
    if status in {"aligned", "findings_present"}:
        if provenance is None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                "semantic_result_provenance is required for evaluated semantic states",
            )
        if error is not None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                "semantic_error must be null for evaluated semantic states",
            )
        validated_provenance = _semantic_provenance_payload(
            provider=str(provenance.get("provider") or ""),
            model=str(provenance.get("model") or ""),
            request_binding_sha256=str(provenance.get("request_binding_sha256") or ""),
            evaluated_at_utc=str(provenance.get("evaluated_at_utc") or ""),
            response_schema_version=str(provenance.get("response_schema_version") or ""),
        )
        validated_error = None
    else:
        if provenance is not None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                f"semantic_result_provenance must be null when semantic_status is {status!r}",
            )
        validated_provenance = None
        validated_error = None
        if status == "error":
            if not isinstance(error, dict):
                raise HumanPresenceOutputQAError(
                    "presence_output_malformed_artifact",
                    "semantic_error must be an object when semantic_status is error",
                )
            validated_error = _semantic_error_payload(
                error_code=str(error.get("error_code") or ""),
                error_message=str(error.get("error_message") or ""),
            )
        else:
            if error is not None:
                raise HumanPresenceOutputQAError(
                    "presence_output_malformed_artifact",
                    f"semantic_error must be null when semantic_status is {status!r}",
                )
            validated_error = None
    if status == "not_evaluated" and validated_findings:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "not_evaluated artifacts may not carry semantic findings",
        )
    if status == "not_assessable" and validated_findings:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "not_assessable artifacts may not carry semantic findings",
        )
    if status == "aligned" and validated_findings:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "aligned artifacts may not carry semantic findings",
        )
    if status == "findings_present" and not validated_findings:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "findings_present artifacts must carry at least one semantic finding",
        )
    if status == "error" and validated_findings:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "error artifacts may not carry semantic findings",
        )
    if status in {"not_evaluated", "not_assessable"} and validated_provenance is not None:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic_result_provenance must be null when semantic_status is {status!r}",
        )
    if plan_values is not None:
        for finding in validated_findings:
            if finding["plan_field_value"] != plan_values.get(finding["plan_field_ref"]):
                raise HumanPresenceOutputQAError(
                    "presence_output_malformed_artifact",
                    f"plan_field_value for {finding['plan_field_ref']!r} does not match the compiled plan",
                )
    return {
        "semantic_status": status,
        "semantic_findings": validated_findings,
        "semantic_result_provenance": validated_provenance,
        "semantic_error": validated_error,
    }


def evaluate_still_image_presence_integrity(
    *,
    plan: dict[str, Any] | None,
    expected_plan_fingerprint_sha256: str | None,
    candidate_decision: dict[str, Any] | None,
    candidate_decision_sha256: str | None,
    expected_candidate_decision_sha256: str | None,
    manifest: dict[str, Any] | None,
    manifest_sha256: str | None,
    expected_manifest_sha256: str | None,
    image_sha256: str | None,
    expected_image_sha256: str | None,
    media_type: str,
    source_artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate integrity of a still-image output against its source artifacts.

    The result distinguishes verified, structurally validated, observed-only,
    and not-assessable bindings. A lack of independent expected values keeps
    the artifact honest by returning ``not_assessable`` instead of ``valid``.
    """

    source_artifacts = source_artifacts or {}
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise HumanPresenceOutputQAError(
            "presence_output_unsupported_media",
            (
                f"media_type {media_type!r} is not in the supported set; "
                f"supported: {sorted(SUPPORTED_MEDIA_TYPES)}"
            ),
        )

    if plan is None:
        binding_records = _no_hpe_binding_records(source_artifacts)
        return {
            "integrity_status": "not_assessable",
            "integrity_findings": _default_not_assessable_findings("missing_required_input", binding_name="plan"),
            "semantic_status": "not_evaluated",
            "semantic_findings": [],
            "binding_records": binding_records,
        }

    findings: list[dict[str, Any]] = []
    binding_records: list[dict[str, Any]] = []

    # 1. Plan fingerprint
    actual_fingerprint = plan_fingerprint_sha256(plan)
    if expected_plan_fingerprint_sha256 is None:
        binding_records.append(
            _binding_record(
                binding_name="plan",
                binding_status="not_assessable",
                observed_sha256=actual_fingerprint,
                expected_sha256=None,
                verification_basis="no_independent_upstream_digest",
                source_path=source_artifacts.get("plan_path"),
                details={"reason": "no_independent_upstream_digest"},
            )
        )
        findings.append(
            {
                "finding_code": "plan_fingerprint_not_assessable",
                "dimension": "integrity",
                "severity": "info",
                "binding_name": "plan",
                "observed": actual_fingerprint,
                "expected": None,
                "verification_basis": "no_independent_upstream_digest",
            }
        )
    else:
        expected_plan_fingerprint_sha256 = _require_sha256(
            expected_plan_fingerprint_sha256,
            "expected_plan_fingerprint_sha256",
        )
        if actual_fingerprint == expected_plan_fingerprint_sha256:
            binding_records.append(
                _binding_record(
                    binding_name="plan",
                    binding_status="verified",
                    observed_sha256=actual_fingerprint,
                    expected_sha256=expected_plan_fingerprint_sha256,
                    verification_basis="independent_expected_plan_fingerprint",
                    source_path=source_artifacts.get("plan_path"),
                    details={"reason": "independent_expected_plan_fingerprint"},
                )
            )
        else:
            binding_records.append(
                _binding_record(
                    binding_name="plan",
                    binding_status="mismatch",
                    observed_sha256=actual_fingerprint,
                    expected_sha256=expected_plan_fingerprint_sha256,
                    verification_basis="independent_expected_plan_fingerprint",
                    source_path=source_artifacts.get("plan_path"),
                    details={"reason": "independent_expected_plan_fingerprint"},
                )
            )
            findings.append(
                {
                    "finding_code": "plan_fingerprint_mismatch",
                    "dimension": "integrity",
                    "severity": "critical",
                    "binding_name": "plan",
                    "observed": actual_fingerprint,
                    "expected": expected_plan_fingerprint_sha256,
                }
            )

    # 2. Candidate decision binding
    if candidate_decision is None or candidate_decision_sha256 is None:
        binding_records.append(
            _binding_record(
                binding_name="candidate_decision",
                binding_status="not_assessable",
                observed_sha256=candidate_decision_sha256,
                expected_sha256=None,
                verification_basis="missing_required_input",
                source_path=source_artifacts.get("candidate_decision_path"),
                details={"reason": "missing_required_input"},
            )
        )
        findings.append(
            {
                "finding_code": "candidate_decision_missing_required_input",
                "dimension": "integrity",
                "severity": "info",
                "binding_name": "candidate_decision",
                "observed": candidate_decision_sha256,
                "expected": None,
                "verification_basis": "missing_required_input",
            }
        )
    else:
        observed_cd_sha = _require_sha256(candidate_decision_sha256, "candidate_decision_sha256")
        if expected_candidate_decision_sha256 is not None:
            expected_candidate_decision_sha256 = _require_sha256(
                expected_candidate_decision_sha256,
                "expected_candidate_decision_sha256",
            )
            if observed_cd_sha == expected_candidate_decision_sha256:
                status = "verified"
                finding_code = None
            else:
                status = "mismatch"
                finding_code = "candidate_decision_binding_mismatch"
        else:
            status = "structurally_validated"
            finding_code = "candidate_decision_structurally_validated"
        binding_records.append(
            _binding_record(
                binding_name="candidate_decision",
                binding_status=status,
                observed_sha256=observed_cd_sha,
                expected_sha256=expected_candidate_decision_sha256,
                verification_basis="json_object_loaded_and_raw_sha_observed",
                source_path=source_artifacts.get("candidate_decision_path"),
                details={"structural_validation": "json_object_loaded"},
            )
        )
        if finding_code is not None:
            findings.append(
                {
                    "finding_code": finding_code,
                    "dimension": "integrity",
                    "severity": "critical" if status == "mismatch" else "info",
                    "binding_name": "candidate_decision",
                    "observed": observed_cd_sha,
                    "expected": expected_candidate_decision_sha256,
                    "verification_basis": "json_object_loaded_and_raw_sha_observed",
                }
            )

    # 3. Manifest binding
    if manifest is None or manifest_sha256 is None:
        binding_records.append(
            _binding_record(
                binding_name="manifest",
                binding_status="not_assessable",
                observed_sha256=manifest_sha256,
                expected_sha256=None,
                verification_basis="missing_required_input",
                source_path=source_artifacts.get("manifest_path"),
                details={"reason": "missing_required_input"},
            )
        )
        findings.append(
            {
                "finding_code": "manifest_missing_required_input",
                "dimension": "integrity",
                "severity": "info",
                "binding_name": "manifest",
                "observed": manifest_sha256,
                "expected": None,
                "verification_basis": "missing_required_input",
            }
        )
    else:
        observed_mf_sha = _require_sha256(manifest_sha256, "manifest_sha256")
        if expected_manifest_sha256 is not None:
            expected_manifest_sha256 = _require_sha256(
                expected_manifest_sha256,
                "expected_manifest_sha256",
            )
            if observed_mf_sha == expected_manifest_sha256:
                status = "verified"
                finding_code = None
            else:
                status = "mismatch"
                finding_code = "manifest_binding_mismatch"
        else:
            status = "structurally_validated"
            finding_code = "manifest_structurally_validated"
        binding_records.append(
            _binding_record(
                binding_name="manifest",
                binding_status=status,
                observed_sha256=observed_mf_sha,
                expected_sha256=expected_manifest_sha256,
                verification_basis="json_object_loaded_and_raw_sha_observed",
                source_path=source_artifacts.get("manifest_path"),
                details={"structural_validation": "json_object_loaded"},
            )
        )
        if finding_code is not None:
            findings.append(
                {
                    "finding_code": finding_code,
                    "dimension": "integrity",
                    "severity": "critical" if status == "mismatch" else "info",
                    "binding_name": "manifest",
                    "observed": observed_mf_sha,
                    "expected": expected_manifest_sha256,
                    "verification_basis": "json_object_loaded_and_raw_sha_observed",
                }
            )

    # 4. Generated image binding
    if image_sha256 is None:
        binding_records.append(
            _binding_record(
                binding_name="generated_image",
                binding_status="not_assessable",
                observed_sha256=None,
                expected_sha256=None,
                verification_basis="missing_required_input",
                source_path=source_artifacts.get("image_path"),
                details={"reason": "missing_required_input"},
            )
        )
        findings.append(
            {
                "finding_code": "generated_image_missing_required_input",
                "dimension": "integrity",
                "severity": "info",
                "binding_name": "generated_image",
                "observed": None,
                "expected": None,
                "verification_basis": "missing_required_input",
            }
        )
    elif expected_image_sha256 is None:
        observed_img_sha = _require_sha256(image_sha256, "image_sha256")
        binding_records.append(
            _binding_record(
                binding_name="generated_image",
                binding_status="not_assessable",
                observed_sha256=observed_img_sha,
                expected_sha256=None,
                verification_basis="no_independent_upstream_digest",
                source_path=source_artifacts.get("image_path"),
                details={"reason": "no_independent_upstream_digest"},
            )
        )
        findings.append(
            {
                "finding_code": "generated_image_not_assessable",
                "dimension": "integrity",
                "severity": "info",
                "binding_name": "generated_image",
                "observed": observed_img_sha,
                "expected": None,
                "verification_basis": "no_independent_upstream_digest",
            }
        )
    else:
        observed_img_sha = _require_sha256(image_sha256, "image_sha256")
        expected_image_sha256 = _require_sha256(expected_image_sha256, "expected_image_sha256")
        if observed_img_sha == expected_image_sha256:
            status = "verified"
            finding_code = None
        else:
            status = "mismatch"
            finding_code = "image_sha256_mismatch"
        binding_records.append(
            _binding_record(
                binding_name="generated_image",
                binding_status=status,
                observed_sha256=observed_img_sha,
                expected_sha256=expected_image_sha256,
                verification_basis="independent_expected_image_sha256",
                source_path=source_artifacts.get("image_path"),
                details={"reason": "independent_expected_image_sha256"},
            )
        )
        if finding_code is not None:
            findings.append(
                {
                    "finding_code": finding_code,
                    "dimension": "integrity",
                    "severity": "critical",
                    "binding_name": "generated_image",
                    "observed": observed_img_sha,
                    "expected": expected_image_sha256,
                    "verification_basis": "independent_expected_image_sha256",
                }
            )

    integrity_status = _status_from_binding_records(binding_records)
    if any(record["binding_status"] == "mismatch" for record in binding_records):
        integrity_status = "invalid"
    elif all(record["binding_status"] == "verified" for record in binding_records):
        integrity_status = "valid"

    return {
        "integrity_status": integrity_status,
        "integrity_findings": findings,
        "semantic_status": "not_evaluated",
        "semantic_findings": [],
        "binding_records": binding_records,
    }


def _build_binding_records_for_artifact(
    integrity_result: dict[str, Any],
    source_artifacts: dict[str, str | None],
) -> list[dict[str, Any]]:
    source_map = {
        "plan": source_artifacts.get("plan_path"),
        "candidate_decision": source_artifacts.get("candidate_decision_path"),
        "manifest": source_artifacts.get("manifest_path"),
        "generated_image": source_artifacts.get("image_path"),
    }
    binding_records = []
    for record in integrity_result["binding_records"]:
        binding_records.append(
            _binding_record_from_result(
                record,
                source_path=source_map.get(record["binding_name"]),
            )
        )
    return binding_records


def build_presence_output_qa_artifact_v1(
    *,
    integrity_result: dict[str, Any],
    source_artifacts: dict[str, str | None],
    evaluator_version: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Assemble the legacy v1 output-QA artifact dict."""

    status = integrity_result["integrity_status"]
    recommendation = _INTEGRITY_STATUS_TO_RECOMMENDATION.get(status, NOT_ASSESSABLE)
    binding_records = _build_binding_records_for_artifact(integrity_result, source_artifacts)
    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION_V1,
        "medium": "still_image",
        "evaluator_version": evaluator_version,
        "generated_at_utc": generated_at_utc or _utcnow_iso(),
        "integrity_status": status,
        "integrity_findings": integrity_result["integrity_findings"],
        "semantic_status": integrity_result["semantic_status"],
        "semantic_findings": integrity_result["semantic_findings"],
        "binding_records": binding_records,
        "source_artifacts": {
            key: value for key, value in source_artifacts.items() if value is not None
        },
        "recommendation": recommendation,
    }


def build_presence_output_qa_artifact_v2(
    *,
    integrity_result: dict[str, Any],
    semantic_result: dict[str, Any],
    source_artifacts: dict[str, str | None],
    evaluator_version: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Assemble the v2 output-QA artifact dict."""

    status = integrity_result["integrity_status"]
    recommendation = _INTEGRITY_STATUS_TO_RECOMMENDATION.get(status, NOT_ASSESSABLE)
    binding_records = _build_binding_records_for_artifact(integrity_result, source_artifacts)
    semantic = _validate_semantic_result(
        semantic_result,
        image_index=_SEMANTIC_FINDING_IMAGE_INDEX,
        plan_values=semantic_result.get("_plan_values"),
    )
    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION_V2,
        "medium": "still_image",
        "evaluator_version": evaluator_version,
        "generated_at_utc": generated_at_utc or _utcnow_iso(),
        "integrity_status": status,
        "integrity_findings": integrity_result["integrity_findings"],
        "semantic_status": semantic["semantic_status"],
        "semantic_findings": semantic["semantic_findings"],
        "semantic_result_provenance": semantic["semantic_result_provenance"],
        "semantic_error": semantic["semantic_error"],
        "binding_records": binding_records,
        "source_artifacts": {
            key: value for key, value in source_artifacts.items() if value is not None
        },
        "recommendation": recommendation,
    }


def build_presence_output_qa_artifact(
    *,
    integrity_result: dict[str, Any],
    source_artifacts: dict[str, str | None],
    evaluator_version: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible v2 builder alias."""

    semantic_result = integrity_result.get("_semantic_result") or {
        "semantic_status": integrity_result["semantic_status"],
        "semantic_findings": integrity_result["semantic_findings"],
        "semantic_result_provenance": None,
        "semantic_error": None,
        "_plan_values": {},
    }
    return build_presence_output_qa_artifact_v2(
        integrity_result=integrity_result,
        semantic_result=semantic_result,
        source_artifacts=source_artifacts,
        evaluator_version=evaluator_version,
        generated_at_utc=generated_at_utc,
    )


def _validate_binding_records(binding_records: Any) -> list[dict[str, Any]]:
    if not isinstance(binding_records, list) or not binding_records:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "binding_records must be a non-empty JSON array",
        )
    validated = [_binding_record_from_result(record, source_path=record.get("source_path")) for record in binding_records]
    names = [record["binding_name"] for record in validated]
    if set(names) != set(_BINDING_NAMES) or len(names) != len(_BINDING_NAMES):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "binding_records must contain exactly one record for each required binding",
        )
    return validated


def _validate_artifact_common(artifact: dict[str, Any], *, schema_version: str) -> dict[str, Any]:
    def _fail(detail: str) -> None:
        raise HumanPresenceOutputQAError("presence_output_malformed_artifact", detail)

    if not isinstance(artifact, dict):
        _fail("artifact must be a JSON object")

    missing = _REQUIRED_ARTIFACT_KEYS - artifact.keys()
    if missing:
        _fail(f"artifact is missing required keys: {sorted(missing)}")

    if artifact["schema_version"] != schema_version:
        _fail(f"schema_version must be {schema_version!r}, got {artifact['schema_version']!r}")

    if artifact["report_type"] != REPORT_TYPE:
        _fail(f"report_type must be {REPORT_TYPE!r}, got {artifact['report_type']!r}")

    if not isinstance(artifact["source_artifacts"], dict):
        _fail("source_artifacts must be a JSON object")

    status = artifact["integrity_status"]
    if status not in _INTEGRITY_STATUS_TO_RECOMMENDATION:
        _fail(f"integrity_status {status!r} is not a known value")

    expected_rec = _INTEGRITY_STATUS_TO_RECOMMENDATION[status]
    if artifact["recommendation"] != expected_rec:
        _fail(
            f"recommendation {artifact['recommendation']!r} is inconsistent with "
            f"integrity_status {status!r}; expected {expected_rec!r}"
        )

    binding_records = _validate_binding_records(artifact["binding_records"])
    mismatch_bindings = [record for record in binding_records if record["binding_status"] == "mismatch"]
    non_verified = [record for record in binding_records if record["binding_status"] != "verified"]

    if status == "valid":
        if artifact["integrity_findings"]:
            _fail("valid artifacts may not carry integrity findings")
        if non_verified:
            _fail("valid artifacts may only contain verified binding records")
    elif status == "invalid":
        if not artifact["integrity_findings"]:
            _fail("invalid artifacts must carry at least one integrity finding")
        if not mismatch_bindings:
            _fail("invalid artifacts must include at least one mismatch binding")
    else:
        if not non_verified:
            _fail("not_assessable artifacts must include at least one non-verified binding")
        if not artifact["integrity_findings"]:
            _fail("not_assessable artifacts must explain why they are not assessable")

    for record in binding_records:
        if record["binding_status"] == "verified":
            if not _is_sha256(record["observed_sha256"]) or not _is_sha256(record["expected_sha256"]):
                _fail("verified bindings must carry both observed and expected sha256 values")
        elif record["binding_status"] == "mismatch":
            if not _is_sha256(record["observed_sha256"]) or not _is_sha256(record["expected_sha256"]):
                _fail("mismatched bindings must carry both observed and expected sha256 values")
        elif record["binding_status"] in {"structurally_validated", "observed_only"}:
            if not _is_sha256(record["observed_sha256"]):
                _fail(f"{record['binding_name']} binding must carry an observed sha256 value")
            if record["expected_sha256"] is not None:
                _fail(
                    f"{record['binding_name']} binding status {record['binding_status']!r} "
                    "may not carry an expected sha256 value"
                )
        elif record["binding_status"] == "not_assessable":
            if record["expected_sha256"] is not None:
                _fail(f"{record['binding_name']} not_assessable record may not carry an expected sha256 value")
            if record["observed_sha256"] is not None and not _is_sha256(record["observed_sha256"]):
                _fail(f"{record['binding_name']} not_assessable record carries an invalid observed sha256 value")
        else:
            _fail(f"binding_status {record['binding_status']!r} is not allowed")

    return artifact


def validate_presence_output_qa_artifact_v1(artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate a legacy v1 presence output QA artifact."""

    artifact = _validate_artifact_common(artifact, schema_version=SCHEMA_VERSION_V1)
    if artifact["semantic_status"] != "not_evaluated":
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic_status must be 'not_evaluated' in v1, got {artifact['semantic_status']!r}",
        )
    if artifact["semantic_findings"] != []:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"semantic_findings must be [] in v1, got {artifact['semantic_findings']!r}",
        )
    if "semantic_result_provenance" in artifact or "semantic_error" in artifact:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "v1 artifacts may not contain semantic_result_provenance or semantic_error",
        )
    return artifact


def validate_presence_output_qa_artifact_v2(artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate a v2 presence output QA artifact."""

    artifact = _validate_artifact_common(artifact, schema_version=SCHEMA_VERSION_V2)
    if "semantic_result_provenance" not in artifact or "semantic_error" not in artifact:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "v2 artifacts must include semantic_result_provenance and semantic_error",
        )
    semantic = _validate_semantic_result(
        {
            "semantic_status": artifact["semantic_status"],
            "semantic_findings": artifact["semantic_findings"],
            "semantic_result_provenance": artifact["semantic_result_provenance"],
            "semantic_error": artifact["semantic_error"],
        },
        image_index=_SEMANTIC_FINDING_IMAGE_INDEX,
        plan_values=None,
    )
    if semantic["semantic_status"] in {"aligned", "findings_present"} and semantic["semantic_result_provenance"] is None:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "validated semantic results must carry provenance",
        )
    if semantic["semantic_status"] in {"not_evaluated", "not_assessable"}:
        if semantic["semantic_result_provenance"] is not None or semantic["semantic_error"] is not None:
            raise HumanPresenceOutputQAError(
                "presence_output_malformed_artifact",
                "non-evaluated semantic states must not carry provenance or semantic errors",
            )
    return artifact


def validate_presence_output_qa_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate a presence output QA artifact dict by schema version."""

    if not isinstance(artifact, dict):
        raise HumanPresenceOutputQAError("presence_output_malformed_artifact", "artifact must be a JSON object")
    schema_version = artifact.get("schema_version")
    if schema_version == SCHEMA_VERSION_V1:
        return validate_presence_output_qa_artifact_v1(artifact)
    if schema_version == SCHEMA_VERSION_V2:
        return validate_presence_output_qa_artifact_v2(artifact)
    raise HumanPresenceOutputQAError(
        "presence_output_malformed_artifact",
        f"schema_version {schema_version!r} is not supported",
    )
