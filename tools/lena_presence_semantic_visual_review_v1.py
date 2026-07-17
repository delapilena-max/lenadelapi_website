from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.presence.human_presence_output_qa_v1 import (
    FINDING_CATEGORIES,
    FINDING_CODES,
    SEMANTIC_ERROR_CODES,
    SEMANTIC_RESPONSE_SCHEMA_VERSION,
    SEMANTIC_STATUS_ENUM,
    HumanPresenceOutputQAError,
    _SEMANTIC_FINDING_KEYS,
    _SEMANTIC_FINDING_TO_CATEGORY,
    _SEMANTIC_FINDING_TO_PLAN_REF,
    _semantic_error_payload,
    _semantic_provenance_payload,
    _STILL_IMAGE_PLAN_FIELD_ALLOWLIST,
    _still_image_plan_field_values,
    _validate_semantic_result,
)
from tools.lena_structured_visual_tool_v1 import (
    StructuredVisualToolError,
    StructuredVisualImage,
    call_anthropic_structured_visual_tool,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_AUTHORITY_PATH = ROOT / "pipeline" / "identity" / "lena_visual_model_authority_v1.json"
REQUEST_SCHEMA_VERSION = "lena_presence_semantic_visual_review_request_v1"
REQUEST_TOOL_NAME = "submit_hpe_semantic_findings"
REQUEST_MAX_TOKENS = 2048
SEMANTIC_PROVIDER_NAME = "anthropic"
SEMANTIC_MODEL_NAME = "claude-sonnet-5"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _request_binding_sha256(request: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(request)).hexdigest()


def _load_model_authority() -> dict[str, Any]:
    try:
        payload = json.loads(MODEL_AUTHORITY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            f"visual model authority is unavailable: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "visual model authority must be a JSON object",
        )
    return payload


def _validate_provider_model_authority(provider: str, model: str) -> dict[str, Any]:
    authority = _load_model_authority()
    if authority.get("provider") != SEMANTIC_PROVIDER_NAME or authority.get("approved_model") != SEMANTIC_MODEL_NAME:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "visual model authority is not aligned with the approved semantic provider/model",
        )
    if provider != SEMANTIC_PROVIDER_NAME or model != SEMANTIC_MODEL_NAME:
        raise HumanPresenceOutputQAError(
            "presence_output_malformed_artifact",
            "requested semantic provider/model does not exactly match the approved authority",
        )
    return {
        "path": str(MODEL_AUTHORITY_PATH.resolve()),
        "provider": provider,
        "approved_model": model,
    }


def _semantic_request_payload(
    *,
    plan: dict[str, Any],
    image_sha256: str,
    image_index: int,
    provider: str,
    model: str,
) -> dict[str, Any]:
    plan_values = _still_image_plan_field_values(plan)
    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "image_index": image_index,
        "image_sha256": image_sha256,
        "provider": provider,
        "model": model,
        "response_schema_version": SEMANTIC_RESPONSE_SCHEMA_VERSION,
        "plan_field_values": plan_values,
        "allowed_finding_codes": list(FINDING_CODES),
        "allowed_finding_categories": list(FINDING_CATEGORIES),
        "allowed_plan_field_refs": list(plan_values),
        "instruction": (
            "Evaluate only what is directly visible in this single still image. "
            "Do not infer temporal transitions, speech, motion sequences, or behavior across frames. "
            "Return findings only when the rendered person obviously contradicts the compiled HPE plan."
        ),
    }


def _tool_schema() -> dict[str, Any]:
    finding_schema = {
        "type": "object",
        "properties": {
            "finding_code": {"type": "string", "enum": list(FINDING_CODES)},
            "category": {"type": "string", "enum": list(FINDING_CATEGORIES)},
            "plan_field_ref": {"type": "string", "enum": list(_STILL_IMAGE_PLAN_FIELD_ALLOWLIST)},
            "plan_field_value": {},
            "observed_description": {"type": "string", "minLength": 1, "maxLength": 300},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "image_index": {"type": "integer"},
            "advisory_only": {"type": "boolean"},
        },
        "required": list(_SEMANTIC_FINDING_KEYS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "enum": [SEMANTIC_RESPONSE_SCHEMA_VERSION]},
            "findings": {
                "type": "array",
                "items": finding_schema,
            },
        },
        "required": ["schema_version", "findings"],
        "additionalProperties": False,
    }


def _response_is_not_assessable(detail: str) -> bool:
    return False


def _semantic_result_not_assessable(reason: str) -> dict[str, Any]:
    return {
        "semantic_status": "not_assessable",
        "semantic_findings": [],
        "semantic_result_provenance": None,
        "semantic_error": None,
    }


def _semantic_result_error(error_code: str, error_message: str) -> dict[str, Any]:
    return {
        "semantic_status": "error",
        "semantic_findings": [],
        "semantic_result_provenance": None,
        "semantic_error": _semantic_error_payload(error_code, error_message),
    }


def _validated_semantic_result(
    *,
    plan_values: dict[str, Any],
    raw_payload: Any,
    image_index: int,
    provider: str,
    model: str,
    request_binding_sha256: str,
) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise StructuredVisualToolError(
            "malformed_provider_payload",
            "semantic provider returned a non-object tool payload",
        )
    allowed_keys = {"schema_version", "findings"}
    if set(raw_payload) != allowed_keys:
        raise StructuredVisualToolError(
            "malformed_provider_payload",
            "semantic provider returned unexpected keys",
        )
    if raw_payload.get("schema_version") != SEMANTIC_RESPONSE_SCHEMA_VERSION:
        raise StructuredVisualToolError(
            "invalid_provider_payload",
            "semantic provider returned an unexpected schema_version",
        )
    findings = raw_payload.get("findings")
    if not isinstance(findings, list):
        raise StructuredVisualToolError(
            "malformed_provider_payload",
            "semantic provider findings must be an array",
        )
    semantic_status = "aligned" if not findings else "findings_present"
    semantic_result = {
        "semantic_status": semantic_status,
        "semantic_findings": findings,
        "semantic_result_provenance": _semantic_provenance_payload(
            provider=provider,
            model=model,
            request_binding_sha256=request_binding_sha256,
            evaluated_at_utc=_utcnow_iso(),
            response_schema_version=SEMANTIC_RESPONSE_SCHEMA_VERSION,
        ),
        "semantic_error": None,
    }
    validated = _validate_semantic_result(
        semantic_result,
        image_index=image_index,
        plan_values=plan_values,
    )
    return {
        "semantic_status": validated["semantic_status"],
        "semantic_findings": validated["semantic_findings"],
        "semantic_result_provenance": validated["semantic_result_provenance"],
        "semantic_error": validated["semantic_error"],
    }


def evaluate_hpe_semantic_still_image_presence(
    *,
    plan: dict[str, Any],
    image_path: Path,
    image_sha256: str,
    image_index: int,
    provider: str,
    model: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Evaluate bounded still-image HPE semantics with one structured provider call."""

    try:
        plan_values = _still_image_plan_field_values(plan)
    except HumanPresenceOutputQAError as exc:
        return _semantic_result_not_assessable(str(exc))

    try:
        provider_authority = _validate_provider_model_authority(provider, model)
    except HumanPresenceOutputQAError as exc:
        return _semantic_result_error("semantic_visual_review_config_missing", str(exc))

    request_payload = _semantic_request_payload(
        plan=plan,
        image_sha256=image_sha256,
        image_index=image_index,
        provider=provider,
        model=model,
    )
    request_binding_sha256 = _request_binding_sha256(request_payload)
    system_prompt = (
        "You are a bounded visual QA reviewer for HPE-2C. "
        "Assess only presence semantics from one still image. "
        "Do not judge identity, anatomy, hands, image quality, publishing, retry, or authority. "
        "Return only the approved JSON tool payload."
    )
    user_text = json.dumps(request_payload, sort_keys=True, ensure_ascii=False)

    try:
        raw_payload = call_anthropic_structured_visual_tool(
            images=[StructuredVisualImage(path=image_path, sha256=image_sha256, role="generated_candidate")],
            system_prompt=system_prompt,
            user_text=user_text,
            tool_name=REQUEST_TOOL_NAME,
            tool_schema=_tool_schema(),
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=REQUEST_MAX_TOKENS,
        )
    except StructuredVisualToolError as exc:
        if exc.code in {"image_unreadable", "unsupported_media", "image_hash_mismatch"}:
            return _semantic_result_not_assessable(exc.detail)
        if exc.code in {"provider_timeout", "provider_rate_limit", "provider_overloaded", "provider_unavailable", "provider_status_error"}:
            mapped_code = {
                "provider_timeout": "semantic_visual_review_timeout",
                "provider_rate_limit": "semantic_visual_review_rate_limit",
                "provider_overloaded": "semantic_visual_review_overloaded",
                "provider_unavailable": "semantic_visual_review_provider_unavailable",
                "provider_status_error": "semantic_visual_review_provider_unavailable",
            }[exc.code]
            return _semantic_result_error(
                mapped_code,
                exc.detail[:500],
            )
        if exc.code in {"malformed_provider_payload", "invalid_provider_payload"}:
            return _semantic_result_error(
                "semantic_visual_review_malformed_payload",
                exc.detail[:500],
            )
        raise

    try:
        return _validated_semantic_result(
            plan_values=plan_values,
            raw_payload=raw_payload,
            image_index=image_index,
            provider=provider_authority["provider"],
            model=provider_authority["approved_model"],
            request_binding_sha256=request_binding_sha256,
        )
    except (HumanPresenceOutputQAError, StructuredVisualToolError) as exc:
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        return _semantic_result_error("semantic_visual_review_invalid_payload", str(detail)[:500])
