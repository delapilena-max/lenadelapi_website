from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pipeline.presence.human_presence_candidate_ranking_v1 import plan_fingerprint_sha256


SCHEMA_VERSION = "human_presence_output_qa_v1"
REPORT_TYPE = "human_presence_output_qa"
SUPPORTED_MEDIA_TYPES = frozenset({"still_image"})
INTEGRITY_PASS = "integrity_pass"
INTEGRITY_FAILURE = "integrity_failure"
NOT_ASSESSABLE = "not_assessable"

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


def build_presence_output_qa_artifact(
    *,
    integrity_result: dict[str, Any],
    source_artifacts: dict[str, str | None],
    evaluator_version: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Assemble the full output-QA artifact dict.

    ``integrity_result`` must be the dict returned by
    ``evaluate_still_image_presence_integrity``. The binding records are
    preserved verbatim except for path materialization from ``source_artifacts``.
    """

    status = integrity_result["integrity_status"]
    recommendation = _INTEGRITY_STATUS_TO_RECOMMENDATION.get(status, NOT_ASSESSABLE)
    binding_records = []
    source_map = {
        "plan": source_artifacts.get("plan_path"),
        "candidate_decision": source_artifacts.get("candidate_decision_path"),
        "manifest": source_artifacts.get("manifest_path"),
        "generated_image": source_artifacts.get("image_path"),
    }
    for record in integrity_result["binding_records"]:
        binding_records.append(
            _binding_record_from_result(
                record,
                source_path=source_map.get(record["binding_name"]),
            )
        )
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
        "binding_records": binding_records,
        "source_artifacts": {
            key: value for key, value in source_artifacts.items() if value is not None
        },
        "recommendation": recommendation,
    }


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


def validate_presence_output_qa_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate a presence output QA artifact dict."""

    def _fail(detail: str) -> None:
        raise HumanPresenceOutputQAError("presence_output_malformed_artifact", detail)

    if not isinstance(artifact, dict):
        _fail("artifact must be a JSON object")

    missing = _REQUIRED_ARTIFACT_KEYS - artifact.keys()
    if missing:
        _fail(f"artifact is missing required keys: {sorted(missing)}")

    if artifact["schema_version"] != SCHEMA_VERSION:
        _fail(f"schema_version must be {SCHEMA_VERSION!r}, got {artifact['schema_version']!r}")

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

    if artifact["semantic_status"] != "not_evaluated":
        _fail(
            f"semantic_status must be 'not_evaluated' in PR1, "
            f"got {artifact['semantic_status']!r}"
        )
    if artifact["semantic_findings"] != []:
        _fail(f"semantic_findings must be [] in PR1, got {artifact['semantic_findings']!r}")

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
