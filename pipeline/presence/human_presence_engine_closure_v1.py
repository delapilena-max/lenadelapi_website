from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "human_presence_engine_closure_v1"
STATUS_VALUES = ("verified", "not_verified", "blocked", "not_applicable")
CATEGORY_VALUES = (
    "ranking",
    "selection",
    "gate_binding",
    "prompt_compilation",
    "prompt_consumption",
    "prompt_influence",
    "qa",
    "configuration",
    "lifecycle",
    "authority",
    "reconciliation",
    "integrity",
    "commit",
)
ITEM_IDS = (
    "candidate_ranking_consumption",
    "selected_candidate_propagation",
    "candidate_plan_gate_binding",
    "prompt_plan_compilation",
    "active_prompt_builder_consumption",
    "pose_prompt_influence",
    "gaze_prompt_influence",
    "expression_prompt_influence",
    "body_language_prompt_influence",
    "object_interaction_prompt_influence",
    "environment_interaction_classification",
    "viewer_relationship_prompt_influence",
    "sensual_presence_prompt_influence",
    "failure_indicator_qa_influence",
    "output_integrity_qa",
    "semantic_configuration",
    "lifecycle_reporting",
    "authority_invariance",
    "reconciliation_invariance",
    "artifact_integrity",
    "commit_binding",
)
DEFAULT_MANDATORY_CONDITIONS = (
    "connected-path runtime evidence verified",
    "prompt-influence matrix verified for supported dimensions",
    "failure indicators classified as QA-only",
    "authority-invariance verified",
    "controlled proof remains outstanding",
    "live semantic proof remains outstanding",
    "ordinary proof remains outstanding",
    "human evidence review remains outstanding",
    "final CI confirmation remains outstanding",
)


class HumanPresenceEngineClosureError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HumanPresenceEngineClosureError(code, detail)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def closure_fingerprint_sha256(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    payload.pop("closure_fingerprint_sha256", None)
    payload.pop("provenance", None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _validate_nonempty_str(value: Any, *, label: str) -> str:
    _require(isinstance(value, str) and value.strip(), "closure_malformed_artifact", f"{label} must be a non-empty string")
    return str(value)


def _validate_status(value: Any) -> str:
    _require(value in STATUS_VALUES, "closure_malformed_artifact", f"status {value!r} is not supported")
    return str(value)


def _validate_category(value: Any) -> str:
    _require(value in CATEGORY_VALUES, "closure_malformed_artifact", f"category {value!r} is not supported")
    return str(value)


def _validate_item_id(value: Any) -> str:
    _require(value in ITEM_IDS, "closure_malformed_artifact", f"item_id {value!r} is not supported")
    return str(value)


def validate_closure_item(item: Any) -> dict[str, Any]:
    _require(isinstance(item, dict), "closure_malformed_artifact", "item must be a JSON object")
    missing = {"item_id", "status", "category", "evidence_ref", "producer", "consumer", "detail", "advisory_only"} - set(item)
    _require(not missing, "closure_malformed_artifact", f"item is missing required keys: {sorted(missing)}")
    extra = set(item) - {"item_id", "status", "category", "evidence_ref", "producer", "consumer", "detail", "advisory_only"}
    _require(not extra, "closure_malformed_artifact", f"item contains unsupported keys: {sorted(extra)}")
    item_id = _validate_item_id(item["item_id"])
    status = _validate_status(item["status"])
    category = _validate_category(item["category"])
    evidence_ref = _validate_nonempty_str(item["evidence_ref"], label=f"{item_id} evidence_ref")
    producer = _validate_nonempty_str(item["producer"], label=f"{item_id} producer")
    consumer = _validate_nonempty_str(item["consumer"], label=f"{item_id} consumer")
    _require(isinstance(item["advisory_only"], bool), "closure_malformed_artifact", f"{item_id} advisory_only must be boolean")
    _require(item["detail"] is not None, "closure_malformed_artifact", f"{item_id} detail must not be null")
    if status == "not_applicable":
        _require(item["advisory_only"] is True, "closure_malformed_artifact", f"{item_id} not_applicable items must be advisory-only")
    return {
        "item_id": item_id,
        "status": status,
        "category": category,
        "evidence_ref": evidence_ref,
        "producer": producer,
        "consumer": consumer,
        "detail": item["detail"],
        "advisory_only": item["advisory_only"],
    }


def validate_evidence_binding(binding: Any) -> dict[str, Any]:
    _require(isinstance(binding, dict), "closure_malformed_artifact", "evidence binding must be a JSON object")
    required = {"binding_id", "status", "source_ref", "observed_sha256", "expected_sha256", "detail"}
    missing = required - set(binding)
    _require(not missing, "closure_malformed_artifact", f"evidence binding is missing required keys: {sorted(missing)}")
    extra = set(binding) - required
    _require(not extra, "closure_malformed_artifact", f"evidence binding contains unsupported keys: {sorted(extra)}")
    binding_id = _validate_nonempty_str(binding["binding_id"], label="binding_id")
    status = _validate_status(binding["status"])
    source_ref = _validate_nonempty_str(binding["source_ref"], label=f"{binding_id} source_ref")
    _require(binding["observed_sha256"] is None or isinstance(binding["observed_sha256"], str), "closure_malformed_artifact", f"{binding_id} observed_sha256 must be a string or null")
    _require(binding["expected_sha256"] is None or isinstance(binding["expected_sha256"], str), "closure_malformed_artifact", f"{binding_id} expected_sha256 must be a string or null")
    _require(binding["detail"] is not None, "closure_malformed_artifact", f"{binding_id} detail must not be null")
    return {
        "binding_id": binding_id,
        "status": status,
        "source_ref": source_ref,
        "observed_sha256": binding["observed_sha256"],
        "expected_sha256": binding["expected_sha256"],
        "detail": binding["detail"],
    }


def _overall_status(items: list[dict[str, Any]]) -> str:
    mandatory = [item for item in items if not item["advisory_only"]]
    if not mandatory:
        return "not_verified"
    if any(item["status"] == "blocked" for item in mandatory):
        return "blocked"
    if any(item["status"] in {"not_verified", "not_applicable"} for item in mandatory):
        return "not_verified"
    return "verified"


def build_human_presence_engine_closure_report(
    *,
    items: list[dict[str, Any]],
    evidence_bindings: list[dict[str, Any]],
    mandatory_conditions: list[str] | tuple[str, ...] = DEFAULT_MANDATORY_CONDITIONS,
    not_applicable_reasons: dict[str, str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validated_items = [validate_closure_item(item) for item in items]
    validated_bindings = [validate_evidence_binding(binding) for binding in evidence_bindings]
    closure_status = _overall_status(validated_items)
    report = {
        "schema_version": SCHEMA_VERSION,
        "closure_status": closure_status,
        "items": validated_items,
        "checked_item_count": len(validated_items),
        "evidence_bindings": validated_bindings,
        "mandatory_conditions": [str(condition) for condition in mandatory_conditions],
        "not_applicable_reasons": dict(not_applicable_reasons or {}),
    }
    if provenance is not None:
        _require(isinstance(provenance, dict), "closure_malformed_artifact", "provenance must be a JSON object")
        report["provenance"] = provenance
    report["closure_fingerprint_sha256"] = closure_fingerprint_sha256(report)
    return report


def validate_human_presence_engine_closure_report(report: Any) -> dict[str, Any]:
    _require(isinstance(report, dict), "closure_malformed_artifact", "report must be a JSON object")
    required = {
        "schema_version",
        "closure_status",
        "items",
        "checked_item_count",
        "evidence_bindings",
        "mandatory_conditions",
        "not_applicable_reasons",
        "closure_fingerprint_sha256",
    }
    missing = required - set(report)
    _require(not missing, "closure_malformed_artifact", f"report is missing required keys: {sorted(missing)}")
    _require(report["schema_version"] == SCHEMA_VERSION, "closure_malformed_artifact", f"schema_version must be {SCHEMA_VERSION!r}")
    _require(report["closure_status"] in STATUS_VALUES, "closure_malformed_artifact", f"closure_status {report['closure_status']!r} is not supported")
    _require(isinstance(report["items"], list) and report["items"], "closure_malformed_artifact", "items must be a non-empty array")
    validated_items = [validate_closure_item(item) for item in report["items"]]
    _require(report["checked_item_count"] == len(validated_items), "closure_malformed_artifact", "checked_item_count does not match item count")
    _require(isinstance(report["evidence_bindings"], list), "closure_malformed_artifact", "evidence_bindings must be an array")
    validated_bindings = [validate_evidence_binding(binding) for binding in report["evidence_bindings"]]
    _require(isinstance(report["mandatory_conditions"], list), "closure_malformed_artifact", "mandatory_conditions must be an array")
    _require(isinstance(report["not_applicable_reasons"], dict), "closure_malformed_artifact", "not_applicable_reasons must be a JSON object")
    if "provenance" in report:
        _require(isinstance(report["provenance"], dict), "closure_malformed_artifact", "provenance must be a JSON object")
    item_ids = [item["item_id"] for item in validated_items]
    _require(len(item_ids) == len(set(item_ids)), "closure_malformed_artifact", "item_ids must be unique")
    binding_ids = [binding["binding_id"] for binding in validated_bindings]
    _require(len(binding_ids) == len(set(binding_ids)), "closure_malformed_artifact", "evidence_bindings must be unique")
    expected_fingerprint = closure_fingerprint_sha256({k: v for k, v in report.items() if k != "closure_fingerprint_sha256"})
    _require(
        report["closure_fingerprint_sha256"] == expected_fingerprint,
        "closure_malformed_artifact",
        "closure_fingerprint_sha256 does not match canonical content",
    )
    return report
