from __future__ import annotations

import json
from typing import Any


REPORT_TYPE = "human_presence_engine_closure_verification"
SCHEMA_VERSION = "human_presence_engine_closure_verification_v1"
STATUS_VALUES = ("verified", "not_verified", "not_applicable", "blocked")
LANE_VALUES = ("controlled_proof", "ordinary_lane")
MANDATORY_CONDITION_IDS = (
    "connected_path_runtime_verification",
    "supported_prompt_influence_verification",
    "failure_indicator_qa_only_verification",
    "authority_invariance_verification",
    "artifact_integrity_verification",
    "provider_free_controlled_proof",
    "controlled_live_semantic_proof_receipt",
    "ordinary_lane_proof",
    "human_evidence_review",
    "final_ci_confirmation",
    "authority_commit_binding",
)
REQUIRED_KEYS = frozenset(
    {
        "report_type",
        "schema_version",
        "current_commit_sha",
        "authority_commit_expected",
        "authority_commit_final",
        "base_commit_sha",
        "execution_timestamp_utc",
        "branch",
        "lane_type",
        "selected_slot_id",
        "selected_candidate_id",
        "hpe_plan_fingerprint_sha256",
        "candidate_ranking_evidence",
        "selected_candidate_evidence",
        "prompt_plan_evidence",
        "final_prompt_influence_evidence",
        "integrity_qa_evidence",
        "semantic_qa_configuration",
        "semantic_qa_evidence",
        "lifecycle_report_evidence",
        "authority_boundary_evidence",
        "required_artifact_paths",
        "mandatory_condition_results",
        "closure_status",
        "blocking_findings",
    }
)
_SHA256_RE = frozenset("0123456789abcdef")
_COMMIT_SHA_RE = frozenset("0123456789abcdef")


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


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in _SHA256_RE for char in value)


def _is_commit_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in _COMMIT_SHA_RE for char in value)


def _normalize_status(value: Any, *, label: str) -> str:
    _require(isinstance(value, str), "closure_status_invalid", f"{label} must be a string")
    normalized = value.strip()
    _require(normalized in STATUS_VALUES, "closure_status_invalid", f"{label} must be one of {STATUS_VALUES!r}")
    return normalized


def _normalize_lane_type(value: Any) -> str:
    _require(isinstance(value, str), "closure_lane_invalid", "lane_type must be a string")
    normalized = value.strip()
    _require(normalized in LANE_VALUES, "closure_lane_invalid", f"lane_type must be one of {LANE_VALUES!r}")
    return normalized


def _normalize_findings(findings: Any) -> list[dict[str, Any]]:
    _require(isinstance(findings, list), "closure_findings_invalid", "blocking_findings must be a list")
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        _require(isinstance(finding, dict), "closure_findings_invalid", "blocking_findings entries must be objects")
        code = str(finding.get("code") or "").strip()
        detail = str(finding.get("detail") or "").strip()
        _require(bool(code) and bool(detail), "closure_findings_invalid", "blocking_findings entries need code and detail")
        normalized.append({"code": code, "detail": detail})
    return normalized


def _normalize_mandatory_condition_results(value: Any) -> dict[str, str]:
    _require(isinstance(value, dict), "closure_report_invalid", "mandatory_condition_results must be an object")
    missing = [condition_id for condition_id in MANDATORY_CONDITION_IDS if condition_id not in value]
    _require(
        not missing,
        "closure_report_missing_keys",
        f"mandatory_condition_results is missing keys: {', '.join(sorted(missing))}",
    )
    extra = sorted(set(value) - set(MANDATORY_CONDITION_IDS))
    _require(not extra, "closure_report_invalid", f"mandatory_condition_results has unexpected keys: {', '.join(extra)}")
    normalized: dict[str, str] = {}
    for condition_id in MANDATORY_CONDITION_IDS:
        status = _normalize_status(value.get(condition_id), label=f"mandatory_condition_results.{condition_id}")
        _require(
            status != "not_applicable",
            "closure_report_invalid",
            f"mandatory condition {condition_id} cannot be not_applicable",
        )
        normalized[condition_id] = status
    return normalized


def _derive_closure_status(*, blocking_findings: list[dict[str, Any]], mandatory_condition_results: dict[str, str]) -> str:
    if blocking_findings:
        return "blocked"
    if any(value == "blocked" for value in mandatory_condition_results.values()):
        return "blocked"
    if any(value == "not_verified" for value in mandatory_condition_results.values()):
        return "not_verified"
    return "verified"


def _normalized_report(report: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(report, dict), "closure_report_invalid", "closure report must be a JSON object")
    missing = [key for key in REQUIRED_KEYS if key not in report]
    _require(not missing, "closure_report_missing_keys", f"closure report is missing keys: {', '.join(sorted(missing))}")
    _require(report.get("report_type") == REPORT_TYPE, "closure_report_invalid", "report_type mismatch")
    _require(report.get("schema_version") == SCHEMA_VERSION, "closure_report_invalid", "schema_version mismatch")
    _require(_is_sha256(report.get("hpe_plan_fingerprint_sha256")), "closure_report_invalid", "invalid plan fingerprint")
    _require(_is_commit_sha(report.get("current_commit_sha")), "closure_report_invalid", "invalid current commit sha")
    _require(_is_commit_sha(report.get("authority_commit_expected")), "closure_report_invalid", "invalid authority_commit_expected")
    _require(_is_commit_sha(report.get("authority_commit_final")), "closure_report_invalid", "invalid authority_commit_final")
    _require(_is_commit_sha(report.get("base_commit_sha")), "closure_report_invalid", "invalid base commit sha")
    _require(
        isinstance(report.get("execution_timestamp_utc"), str) and report["execution_timestamp_utc"].strip(),
        "closure_report_invalid",
        "execution timestamp is missing",
    )
    _require(isinstance(report.get("branch"), str) and report["branch"].strip(), "closure_report_invalid", "branch is missing")
    _require(
        isinstance(report.get("selected_slot_id"), str) and report["selected_slot_id"].strip(),
        "closure_report_invalid",
        "selected_slot_id is missing",
    )
    _require(
        isinstance(report.get("selected_candidate_id"), str) and report["selected_candidate_id"].strip(),
        "closure_report_invalid",
        "selected_candidate_id is missing",
    )
    _require(isinstance(report.get("candidate_ranking_evidence"), dict), "closure_report_invalid", "candidate_ranking_evidence must be an object")
    _require(isinstance(report.get("selected_candidate_evidence"), dict), "closure_report_invalid", "selected_candidate_evidence must be an object")
    _require(isinstance(report.get("prompt_plan_evidence"), dict), "closure_report_invalid", "prompt_plan_evidence must be an object")
    _require(isinstance(report.get("final_prompt_influence_evidence"), list), "closure_report_invalid", "final_prompt_influence_evidence must be a list")
    _require(isinstance(report.get("integrity_qa_evidence"), dict), "closure_report_invalid", "integrity_qa_evidence must be an object")
    _require(isinstance(report.get("semantic_qa_configuration"), dict), "closure_report_invalid", "semantic_qa_configuration must be an object")
    _require(isinstance(report.get("semantic_qa_evidence"), dict), "closure_report_invalid", "semantic_qa_evidence must be an object")
    _require(isinstance(report.get("lifecycle_report_evidence"), dict), "closure_report_invalid", "lifecycle_report_evidence must be an object")
    _require(isinstance(report.get("authority_boundary_evidence"), dict), "closure_report_invalid", "authority_boundary_evidence must be an object")
    _require(isinstance(report.get("required_artifact_paths"), dict), "closure_report_invalid", "required_artifact_paths must be an object")
    lane_type = _normalize_lane_type(report.get("lane_type"))
    findings = _normalize_findings(report.get("blocking_findings"))
    mandatory_condition_results = _normalize_mandatory_condition_results(report.get("mandatory_condition_results"))
    closure_status = _normalize_status(report.get("closure_status"), label="closure_status")

    expected_status = _derive_closure_status(
        blocking_findings=findings,
        mandatory_condition_results=mandatory_condition_results,
    )
    _require(
        closure_status == expected_status,
        "closure_report_invalid",
        f"closure_status must be {expected_status!r} for the supplied mandatory conditions",
    )
    if lane_type == "controlled_proof":
        _require(
            mandatory_condition_results["controlled_live_semantic_proof_receipt"] in {"verified", "not_verified", "blocked"},
            "closure_report_invalid",
            "controlled proof lane requires a controlled live semantic proof receipt status",
        )
    if lane_type == "ordinary_lane":
        _require(
            mandatory_condition_results["ordinary_lane_proof"] in {"verified", "not_verified", "blocked"},
            "closure_report_invalid",
            "ordinary lane requires an ordinary lane proof status",
        )

    return {
        **report,
        "lane_type": lane_type,
        "blocking_findings": findings,
        "mandatory_condition_results": mandatory_condition_results,
        "closure_status": closure_status,
    }


def build_closure_verification_report(
    *,
    current_commit_sha: str,
    authority_commit_expected: str,
    authority_commit_final: str,
    base_commit_sha: str,
    execution_timestamp_utc: str,
    branch: str,
    lane_type: str,
    selected_slot_id: str,
    selected_candidate_id: str,
    hpe_plan_fingerprint_sha256: str,
    candidate_ranking_evidence: dict[str, Any],
    selected_candidate_evidence: dict[str, Any],
    prompt_plan_evidence: dict[str, Any],
    final_prompt_influence_evidence: list[dict[str, Any]],
    integrity_qa_evidence: dict[str, Any],
    semantic_qa_configuration: dict[str, Any],
    semantic_qa_evidence: dict[str, Any],
    lifecycle_report_evidence: dict[str, Any],
    authority_boundary_evidence: dict[str, Any],
    required_artifact_paths: dict[str, Any],
    mandatory_condition_results: dict[str, Any],
    blocking_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "current_commit_sha": current_commit_sha,
        "authority_commit_expected": authority_commit_expected,
        "authority_commit_final": authority_commit_final,
        "base_commit_sha": base_commit_sha,
        "execution_timestamp_utc": execution_timestamp_utc,
        "branch": branch,
        "lane_type": lane_type,
        "selected_slot_id": selected_slot_id,
        "selected_candidate_id": selected_candidate_id,
        "hpe_plan_fingerprint_sha256": hpe_plan_fingerprint_sha256,
        "candidate_ranking_evidence": candidate_ranking_evidence,
        "selected_candidate_evidence": selected_candidate_evidence,
        "prompt_plan_evidence": prompt_plan_evidence,
        "final_prompt_influence_evidence": final_prompt_influence_evidence,
        "integrity_qa_evidence": integrity_qa_evidence,
        "semantic_qa_configuration": semantic_qa_configuration,
        "semantic_qa_evidence": semantic_qa_evidence,
        "lifecycle_report_evidence": lifecycle_report_evidence,
        "authority_boundary_evidence": authority_boundary_evidence,
        "required_artifact_paths": required_artifact_paths,
        "mandatory_condition_results": mandatory_condition_results,
        "blocking_findings": blocking_findings or [],
    }
    report["closure_status"] = _derive_closure_status(
        blocking_findings=report["blocking_findings"],
        mandatory_condition_results=_normalize_mandatory_condition_results(report["mandatory_condition_results"]),
    )
    return _normalized_report(report)


def validate_closure_verification_report(report: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalized_report(report)
    report.clear()
    report.update(normalized)
    return report
