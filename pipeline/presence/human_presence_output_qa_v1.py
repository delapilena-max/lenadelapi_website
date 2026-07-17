from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pipeline.presence.human_presence_candidate_ranking_v1 import plan_fingerprint_sha256


SCHEMA_VERSION = "human_presence_output_qa_v1"
REPORT_TYPE = "human_presence_output_qa"
SUPPORTED_MEDIA_TYPES = frozenset({"still_image"})
INTEGRITY_PASS = "integrity_pass"
INTEGRITY_FAILURE = "integrity_failure"
NOT_ASSESSABLE = "not_assessable"

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


def _not_assessable_result() -> dict[str, Any]:
    return {
        "integrity_status": "not_assessable",
        "integrity_findings": [{"finding_code": "missing_required_input", "missing": ["plan"]}],
        "semantic_status": "not_evaluated",
        "semantic_findings": [],
    }


def evaluate_still_image_presence_integrity(
    *,
    plan: dict[str, Any] | None,
    expected_plan_fingerprint_sha256: str | None,
    candidate_decision: dict[str, Any],
    expected_candidate_decision_sha256: str,
    manifest: dict[str, Any],
    expected_manifest_sha256: str,
    image_sha256: str,
    expected_image_sha256: str,
    media_type: str,
) -> dict[str, Any]:
    """Evaluate integrity of a still-image output against its source artifacts.

    Returns a structured result dict with:
      - integrity_status: "valid" | "invalid" | "not_assessable"
      - integrity_findings: list of finding dicts (empty when valid or not_assessable)
      - semantic_status: always "not_evaluated" in PR1
      - semantic_findings: always [] in PR1

    Raises HumanPresenceOutputQAError for precondition violations only
    (unsupported media_type). NOT_ASSESSABLE is a return state, not an
    exception.
    """
    # NOT_ASSESSABLE: plan was not supplied — no HPE was requested for this
    # output so integrity cannot be evaluated against a presence plan.
    if plan is None or not expected_plan_fingerprint_sha256:
        return _not_assessable_result()

    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise HumanPresenceOutputQAError(
            "presence_output_unsupported_media",
            (
                f"media_type {media_type!r} is not in the supported set; "
                f"supported: {sorted(SUPPORTED_MEDIA_TYPES)}"
            ),
        )

    findings: list[dict[str, Any]] = []

    # 1. Plan fingerprint — recomputed vs. recorded expected value.
    actual_fingerprint = plan_fingerprint_sha256(plan)
    if actual_fingerprint != expected_plan_fingerprint_sha256:
        findings.append({
            "finding_code": "plan_fingerprint_mismatch",
            "dimension": "integrity",
            "severity": "critical",
            "observed": actual_fingerprint,
            "expected": expected_plan_fingerprint_sha256,
        })

    # 2. Candidate decision binding — canonical SHA-256 of the loaded dict vs.
    #    the SHA-256 the caller computed from the raw file bytes. These agree
    #    when the file was written as canonical JSON (as the gate tool does).
    actual_cd_sha = _sha256_canonical(candidate_decision)
    if actual_cd_sha != expected_candidate_decision_sha256:
        findings.append({
            "finding_code": "candidate_decision_binding_mismatch",
            "dimension": "integrity",
            "severity": "critical",
            "observed": actual_cd_sha,
            "expected": expected_candidate_decision_sha256,
        })

    # 3. Manifest binding — same pattern.
    actual_mf_sha = _sha256_canonical(manifest)
    if actual_mf_sha != expected_manifest_sha256:
        findings.append({
            "finding_code": "manifest_binding_mismatch",
            "dimension": "integrity",
            "severity": "critical",
            "observed": actual_mf_sha,
            "expected": expected_manifest_sha256,
        })

    # 4. Image SHA-256 — actual (raw bytes) vs. expected from binding record.
    if image_sha256 != expected_image_sha256:
        findings.append({
            "finding_code": "image_sha256_mismatch",
            "dimension": "integrity",
            "severity": "critical",
            "observed": image_sha256,
            "expected": expected_image_sha256,
        })

    return {
        "integrity_status": "valid" if not findings else "invalid",
        "integrity_findings": findings,
        "semantic_status": "not_evaluated",
        "semantic_findings": [],
    }


def build_presence_output_qa_artifact(
    *,
    integrity_result: dict[str, Any],
    plan_fingerprint_sha256_value: str,
    candidate_decision_sha256: str,
    manifest_sha256: str,
    image_sha256: str,
    source_artifacts: dict[str, str],
    evaluator_version: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Assemble the full output-QA artifact dict.

    ``integrity_result`` must be the dict returned by
    ``evaluate_still_image_presence_integrity``. All other parameters are
    binding/provenance metadata recorded alongside the evaluation result.
    """
    status = integrity_result["integrity_status"]
    recommendation = _INTEGRITY_STATUS_TO_RECOMMENDATION.get(status, NOT_ASSESSABLE)
    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "medium": "still_image",
        "evaluator_version": evaluator_version,
        "generated_at_utc": generated_at_utc or _utcnow_iso(),
        "integrity_status": status,
        "integrity_findings": integrity_result["integrity_findings"],
        "semantic_status": integrity_result["semantic_status"],
        "semantic_findings": integrity_result["semantic_findings"],
        "binding_records": {
            "plan_fingerprint_sha256": plan_fingerprint_sha256_value,
            "candidate_decision_sha256": candidate_decision_sha256,
            "manifest_sha256": manifest_sha256,
            "image_sha256": image_sha256,
        },
        "source_artifacts": source_artifacts,
        "recommendation": recommendation,
    }


def validate_presence_output_qa_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate a presence output QA artifact dict.

    Raises ``HumanPresenceOutputQAError("presence_output_malformed_artifact",
    ...)`` on any structural or consistency violation. Returns the artifact
    unchanged when valid.

    PR1 invariants enforced:
    - All required top-level keys must be present.
    - ``schema_version`` must equal ``SCHEMA_VERSION``.
    - ``report_type`` must equal ``REPORT_TYPE``.
    - ``recommendation`` must be consistent with ``integrity_status``.
    - ``semantic_status`` must be ``"not_evaluated"``.
    - ``semantic_findings`` must be ``[]``.
    """

    def _fail(detail: str) -> None:
        raise HumanPresenceOutputQAError("presence_output_malformed_artifact", detail)

    if not isinstance(artifact, dict):
        _fail("artifact must be a JSON object")

    missing = _REQUIRED_ARTIFACT_KEYS - artifact.keys()
    if missing:
        _fail(f"artifact is missing required keys: {sorted(missing)}")

    if artifact["schema_version"] != SCHEMA_VERSION:
        _fail(
            f"schema_version must be {SCHEMA_VERSION!r}, got {artifact['schema_version']!r}"
        )

    if artifact["report_type"] != REPORT_TYPE:
        _fail(f"report_type must be {REPORT_TYPE!r}, got {artifact['report_type']!r}")

    status = artifact["integrity_status"]
    if status not in _INTEGRITY_STATUS_TO_RECOMMENDATION:
        _fail(f"integrity_status {status!r} is not a known value")

    expected_rec = _INTEGRITY_STATUS_TO_RECOMMENDATION[status]
    if artifact["recommendation"] != expected_rec:
        _fail(
            f"recommendation {artifact['recommendation']!r} is inconsistent with "
            f"integrity_status {status!r}; expected {expected_rec!r}"
        )

    if artifact["semantic_status"] != "not_evaluated":
        _fail(
            f"semantic_status must be 'not_evaluated' in PR1, "
            f"got {artifact['semantic_status']!r}"
        )

    if artifact["semantic_findings"] != []:
        _fail(
            f"semantic_findings must be [] in PR1, "
            f"got {artifact['semantic_findings']!r}"
        )

    return artifact
