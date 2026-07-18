from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "pipeline" / "asset_review" / "lena" / "hpe_closure"

SCHEMA_VERSION_FINAL_CI = "human_presence_final_ci_confirmation_v1"
SCHEMA_VERSION_HUMAN_REVIEW = "human_presence_human_evidence_review_v1"
SCHEMA_VERSION_MANUAL_SEMANTIC_REVIEW = "human_presence_manual_semantic_review_v1"
SCHEMA_VERSION_ORDINARY_LANE_PROOF = "human_presence_ordinary_lane_proof_v1"

FINAL_CI_REQUIRED_CHECK_NAMES = ("build", "main_ci_check")
FINAL_CI_SUCCESS_CONCLUSION_ALIASES = {"success", "pass"}
FINAL_CI_NON_VERIFYING_CONCLUSIONS = (
    "failure",
    "fail",
    "cancelled",
    "skipped",
    "pending",
    "neutral",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
)
HUMAN_REVIEW_DISPOSITIONS = ("accepted_for_hpe_closure", "rejected", "insufficient_evidence")
MANUAL_SEMANTIC_DISPOSITIONS = ("accepted_for_hpe_closure", "rejected", "insufficient_evidence")
ORDINARY_LANE_PROOF_DISPOSITIONS = ("accepted_for_hpe_closure", "rejected", "insufficient_evidence")
MANUAL_SEMANTIC_ASPECT_IDS = (
    "gaze_and_viewer_recognition",
    "expression_progression",
    "body_and_pose_naturalness",
    "anatomy_continuity",
    "clothing_continuity",
    "identity_continuity",
    "mannequin_or_frozen_expression_failures",
    "hpe_presence_characteristics",
    "safety_non_explicit_compliance",
)
HUMAN_REVIEW_CONFIRMATION_STATEMENT = "I reviewed the evidence and accept it for HPE closure."
MANUAL_SEMANTIC_CONFIRMATION_STATEMENT = "I reviewed the image and accept the manual semantic review for HPE closure."
ORDINARY_LANE_PROOF_CONFIRMATION_STATEMENT = "I reviewed the ordinary lane evidence and accept it for HPE closure."
MANUAL_SEMANTIC_EVIDENCE_SOURCE = "manual_human_semantic_review"
ORDINARY_LANE_PROOF_EVIDENCE_SOURCE = "ordinary_lane_proof"

_SHA256_RE = frozenset("0123456789abcdef")
_COMMIT_SHA_RE = frozenset("0123456789abcdef")


class ClosureEvidenceError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ClosureEvidenceError(code, detail)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in _SHA256_RE for char in value)


def _is_commit_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in _COMMIT_SHA_RE for char in value)


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ClosureEvidenceError("artifact_missing", f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClosureEvidenceError("artifact_invalid", f"could not parse {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClosureEvidenceError("artifact_invalid", f"{label} must be a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    payload_bytes = serialized.encode("utf-8")
    if path.exists():
        if path.read_bytes() == payload_bytes:
            return
        raise ClosureEvidenceError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        handle.write(payload_bytes)
        handle.flush()
    try:
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def final_ci_confirmation_artifact_path(
    date_str: str,
    slot_id: str,
    image_index: int,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    return output_root / date_str / slot_id / f"lena_hpe_final_ci_confirmation_{slot_id}_{image_index:02d}.json"


def human_evidence_review_artifact_path(
    date_str: str,
    slot_id: str,
    image_index: int,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    return output_root / date_str / slot_id / f"lena_hpe_human_evidence_review_{slot_id}_{image_index:02d}.json"


def manual_semantic_review_artifact_path(
    date_str: str,
    slot_id: str,
    image_index: int,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    return output_root / date_str / slot_id / f"lena_hpe_manual_semantic_review_{slot_id}_{image_index:02d}.json"


def _validate_check_entry(entry: Any, *, allow_missing_conclusion: bool = False) -> dict[str, Any]:
    _require(isinstance(entry, dict), "ci_evidence_invalid", "required_checks entries must be objects")
    _require(
        set(entry).issubset({"check_name", "conclusion", "github_url", "check_run_id"}),
        "ci_evidence_invalid",
        "required_checks entries have unexpected keys",
    )
    check_name = str(entry.get("check_name") or "").strip()
    _require(bool(check_name), "ci_evidence_invalid", "required_checks entries need check_name")
    conclusion_value = entry.get("conclusion")
    if conclusion_value is None or conclusion_value == "":
        _require(allow_missing_conclusion, "ci_evidence_invalid", "required_checks entries need conclusion")
        normalized_conclusion: str | None = None
    else:
        conclusion = str(conclusion_value).strip()
        _require(bool(conclusion), "ci_evidence_invalid", "required_checks entries need conclusion")
        normalized_conclusion = conclusion.strip().lower()
        if normalized_conclusion in FINAL_CI_SUCCESS_CONCLUSION_ALIASES:
            normalized_conclusion = "pass"
    github_url = entry.get("github_url")
    if github_url is not None:
        _require(isinstance(github_url, str) and github_url.strip(), "ci_evidence_invalid", "github_url must be a string")
    check_run_id = entry.get("check_run_id")
    if check_run_id is not None:
        _require(
            isinstance(check_run_id, (str, int)) and str(check_run_id).strip(),
            "ci_evidence_invalid",
            "check_run_id must be a string or integer",
        )
    return {
        "check_name": check_name,
        "conclusion": normalized_conclusion,
        **({"github_url": github_url} if github_url is not None else {}),
        **({"check_run_id": check_run_id} if check_run_id is not None else {}),
    }


def build_final_ci_confirmation_artifact(
    *,
    repository: str,
    pr_number: int,
    reviewed_head_sha: str,
    merge_commit_sha: str,
    required_checks: list[dict[str, Any]],
    evidence_source: str,
    authority_commit_expected: str,
    authority_commit_final: str,
    evidence_collected_at_utc: str | None = None,
    github_pr_url: str | None = None,
    github_merge_commit_url: str | None = None,
) -> dict[str, Any]:
    _require(isinstance(repository, str) and repository.strip(), "ci_evidence_invalid", "repository is required")
    _require(isinstance(pr_number, int) and pr_number > 0, "ci_evidence_invalid", "pr_number must be a positive integer")
    for label, value in (
        ("reviewed_head_sha", reviewed_head_sha),
        ("merge_commit_sha", merge_commit_sha),
        ("authority_commit_expected", authority_commit_expected),
        ("authority_commit_final", authority_commit_final),
    ):
        _require(_is_commit_sha(value), "ci_evidence_invalid", f"{label} must be a commit sha")
    _require(isinstance(required_checks, list) and required_checks, "ci_evidence_invalid", "required_checks must be a non-empty list")
    normalized_checks = [_validate_check_entry(entry) for entry in required_checks]
    _require(
        {entry["check_name"] for entry in normalized_checks} == set(FINAL_CI_REQUIRED_CHECK_NAMES),
        "ci_evidence_invalid",
        f"required_checks must contain exactly {FINAL_CI_REQUIRED_CHECK_NAMES!r}",
    )
    _require(isinstance(evidence_source, str) and evidence_source.strip(), "ci_evidence_invalid", "evidence_source is required")
    _require(
        isinstance(evidence_collected_at_utc, str) and evidence_collected_at_utc.strip() or evidence_collected_at_utc is None,
        "ci_evidence_invalid",
        "evidence_collected_at_utc must be omitted or a non-empty string",
    )
    if evidence_collected_at_utc is None:
        evidence_collected_at_utc = _utcnow_iso()
    artifact = {
        "schema_version": SCHEMA_VERSION_FINAL_CI,
        "repository": repository.strip(),
        "pr_number": pr_number,
        "reviewed_head_sha": reviewed_head_sha,
        "merge_commit_sha": merge_commit_sha,
        "required_checks": normalized_checks,
        "evidence_collected_at_utc": evidence_collected_at_utc,
        "evidence_source": evidence_source.strip(),
        "authority_commit_expected": authority_commit_expected,
        "authority_commit_final": authority_commit_final,
    }
    if github_pr_url is not None:
        _require(isinstance(github_pr_url, str) and github_pr_url.strip(), "ci_evidence_invalid", "github_pr_url must be a string")
        artifact["github_pr_url"] = github_pr_url.strip()
    if github_merge_commit_url is not None:
        _require(
            isinstance(github_merge_commit_url, str) and github_merge_commit_url.strip(),
            "ci_evidence_invalid",
            "github_merge_commit_url must be a string",
        )
        artifact["github_merge_commit_url"] = github_merge_commit_url.strip()
    return artifact


def validate_final_ci_confirmation_artifact(
    artifact: dict[str, Any],
    *,
    expected_repository: str | None = None,
    expected_pr_number: int | None = None,
    expected_reviewed_head_sha: str | None = None,
    expected_merge_commit_sha: str | None = None,
    expected_authority_commit: str | None = None,
) -> dict[str, Any]:
    _require(isinstance(artifact, dict), "ci_evidence_invalid", "final CI evidence must be a JSON object")
    _require(
        artifact.get("schema_version") == SCHEMA_VERSION_FINAL_CI,
        "ci_evidence_invalid",
        "final CI evidence schema_version mismatch",
    )
    if expected_repository is not None:
        _require(artifact.get("repository") == expected_repository, "ci_evidence_invalid", "repository mismatch")
    if expected_pr_number is not None:
        _require(artifact.get("pr_number") == expected_pr_number, "ci_evidence_invalid", "pr_number mismatch")
    for label, expected in (
        ("reviewed_head_sha", expected_reviewed_head_sha),
        ("merge_commit_sha", expected_merge_commit_sha),
        ("authority_commit_expected", expected_authority_commit),
        ("authority_commit_final", expected_authority_commit),
    ):
        actual = str(artifact.get(label) or "")
        _require(_is_commit_sha(actual), "ci_evidence_invalid", f"{label} must be a commit sha")
        if expected is not None:
            _require(actual == expected, "ci_evidence_invalid", f"{label} mismatch")
    _require(isinstance(artifact.get("evidence_collected_at_utc"), str) and artifact["evidence_collected_at_utc"].strip(), "ci_evidence_invalid", "evidence_collected_at_utc is required")
    _require(isinstance(artifact.get("evidence_source"), str) and artifact["evidence_source"].strip(), "ci_evidence_invalid", "evidence_source is required")
    required_checks = artifact.get("required_checks")
    _require(isinstance(required_checks, list) and required_checks, "ci_evidence_invalid", "required_checks must be a non-empty list")
    normalized_checks = [_validate_check_entry(entry, allow_missing_conclusion=True) for entry in required_checks]
    _require(
        {entry["check_name"] for entry in normalized_checks} == set(FINAL_CI_REQUIRED_CHECK_NAMES),
        "ci_evidence_invalid",
        f"required_checks must contain exactly {FINAL_CI_REQUIRED_CHECK_NAMES!r}",
    )
    normalized = dict(artifact)
    normalized["required_checks"] = normalized_checks
    return normalized


def write_final_ci_confirmation_artifact(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    artifact: dict[str, Any],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[Path, str]:
    path = final_ci_confirmation_artifact_path(date_str, slot_id, image_index, output_root)
    _write_json_atomic(path, artifact)
    return path, _sha256_file(path)


def _normalize_findings(findings: Any) -> list[dict[str, Any]]:
    _require(isinstance(findings, list), "human_review_invalid", "findings must be a list")
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        _require(isinstance(finding, dict), "human_review_invalid", "findings entries must be objects")
        _require(set(finding).issubset({"code", "detail", "severity"}), "human_review_invalid", "findings entries have unexpected keys")
        code = str(finding.get("code") or "").strip()
        detail = str(finding.get("detail") or "").strip()
        _require(bool(code) and bool(detail), "human_review_invalid", "findings entries need code and detail")
        severity = finding.get("severity")
        if severity is not None:
            _require(isinstance(severity, str) and severity.strip(), "human_review_invalid", "finding severity must be a string")
        normalized.append({"code": code, "detail": detail, **({"severity": severity} if severity is not None else {})})
    return normalized


def _validate_bound_file(path_value: str, sha_value: str, *, label: str) -> tuple[Path, str]:
    path = _resolve_path(path_value)
    _require(path.is_file(), "human_review_invalid", f"{label} path does not exist: {path}")
    _require(_is_sha256(sha_value), "human_review_invalid", f"{label} sha256 is invalid")
    actual_sha = _sha256_file(path)
    _require(actual_sha == sha_value, "human_review_invalid", f"{label} sha256 mismatch")
    return path, actual_sha


def build_human_evidence_review_artifact(
    *,
    reviewer_operator_id: str,
    reviewed_image_path: str | Path,
    reviewed_image_sha256: str,
    candidate_artifact_path: str | Path,
    candidate_artifact_sha256: str,
    handoff_artifact_path: str | Path,
    handoff_artifact_sha256: str,
    execution_receipt_artifact_path: str | Path,
    execution_receipt_artifact_sha256: str,
    provider_job_id: str,
    authority_commit_expected: str,
    authority_commit_final: str,
    disposition: str,
    findings: list[dict[str, Any]],
    confirmation_statement: str,
    publishing_authorized: bool = False,
    evidence_source: str = "human_operator",
    reviewed_at_utc: str | None = None,
) -> dict[str, Any]:
    _require(isinstance(reviewer_operator_id, str) and reviewer_operator_id.strip(), "human_review_invalid", "reviewer_operator_id is required")
    reviewed_path = _resolve_path(reviewed_image_path)
    candidate_path = _resolve_path(candidate_artifact_path)
    handoff_path = _resolve_path(handoff_artifact_path)
    receipt_path = _resolve_path(execution_receipt_artifact_path)
    _require(isinstance(provider_job_id, str) and provider_job_id.strip(), "human_review_invalid", "provider_job_id is required")
    _require(disposition in HUMAN_REVIEW_DISPOSITIONS, "human_review_invalid", "disposition is invalid")
    _require(confirmation_statement == HUMAN_REVIEW_CONFIRMATION_STATEMENT, "human_review_invalid", "confirmation_statement mismatch")
    _require(publishing_authorized is False, "human_review_invalid", "publishing must remain unauthorized")
    _require(isinstance(evidence_source, str) and evidence_source.strip(), "human_review_invalid", "evidence_source is required")
    _require(_is_commit_sha(authority_commit_expected), "human_review_invalid", "authority_commit_expected must be a commit sha")
    _require(_is_commit_sha(authority_commit_final), "human_review_invalid", "authority_commit_final must be a commit sha")
    if reviewed_at_utc is None:
        reviewed_at_utc = _utcnow_iso()
    _validate_bound_file(reviewed_path, reviewed_image_sha256, label="reviewed_image")
    _validate_bound_file(candidate_path, candidate_artifact_sha256, label="candidate_artifact")
    _validate_bound_file(handoff_path, handoff_artifact_sha256, label="handoff_artifact")
    _validate_bound_file(receipt_path, execution_receipt_artifact_sha256, label="execution_receipt_artifact")
    artifact = {
        "schema_version": SCHEMA_VERSION_HUMAN_REVIEW,
        "reviewer_operator_id": reviewer_operator_id.strip(),
        "reviewed_image_path": str(reviewed_path),
        "reviewed_image_sha256": reviewed_image_sha256,
        "candidate_artifact_path": str(candidate_path),
        "candidate_artifact_sha256": candidate_artifact_sha256,
        "handoff_artifact_path": str(handoff_path),
        "handoff_artifact_sha256": handoff_artifact_sha256,
        "execution_receipt_artifact_path": str(receipt_path),
        "execution_receipt_artifact_sha256": execution_receipt_artifact_sha256,
        "provider_job_id": provider_job_id.strip(),
        "authority_commit_expected": authority_commit_expected,
        "authority_commit_final": authority_commit_final,
        "reviewed_at_utc": reviewed_at_utc,
        "disposition": disposition,
        "findings": _normalize_findings(findings),
        "confirmation_statement": confirmation_statement,
        "publishing_authorized": False,
        "evidence_source": evidence_source.strip(),
    }
    return artifact


def validate_human_evidence_review_artifact(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    _require(isinstance(artifact, dict), "human_review_invalid", "human review evidence must be a JSON object")
    _require(
        artifact.get("schema_version") == SCHEMA_VERSION_HUMAN_REVIEW,
        "human_review_invalid",
        "human review schema_version mismatch",
    )
    _require(isinstance(artifact.get("reviewer_operator_id"), str) and artifact["reviewer_operator_id"].strip(), "human_review_invalid", "reviewer_operator_id is required")
    _require(isinstance(artifact.get("provider_job_id"), str) and artifact["provider_job_id"].strip(), "human_review_invalid", "provider_job_id is required")
    _require(_is_commit_sha(str(artifact.get("authority_commit_expected") or "")), "human_review_invalid", "authority_commit_expected must be a commit sha")
    _require(_is_commit_sha(str(artifact.get("authority_commit_final") or "")), "human_review_invalid", "authority_commit_final must be a commit sha")
    _require(isinstance(artifact.get("reviewed_at_utc"), str) and artifact["reviewed_at_utc"].strip(), "human_review_invalid", "reviewed_at_utc is required")
    _require(artifact.get("disposition") in HUMAN_REVIEW_DISPOSITIONS, "human_review_invalid", "disposition is invalid")
    _require(artifact.get("confirmation_statement") == HUMAN_REVIEW_CONFIRMATION_STATEMENT, "human_review_invalid", "confirmation_statement mismatch")
    _require(artifact.get("publishing_authorized") is False, "human_review_invalid", "publishing_authorized must be false")
    _require(isinstance(artifact.get("evidence_source"), str) and artifact["evidence_source"].strip(), "human_review_invalid", "evidence_source is required")
    normalized = dict(artifact)
    for field in (
        "reviewed_image",
        "candidate_artifact",
        "handoff_artifact",
        "execution_receipt_artifact",
    ):
        path_key = f"{field}_path"
        sha_key = f"{field}_sha256"
        path, _ = _validate_bound_file(str(artifact.get(path_key) or ""), str(artifact.get(sha_key) or ""), label=field)
        normalized[path_key] = str(path)
    normalized["findings"] = _normalize_findings(artifact.get("findings"))
    return normalized


def write_human_evidence_review_artifact(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    artifact: dict[str, Any],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[Path, str]:
    path = human_evidence_review_artifact_path(date_str, slot_id, image_index, output_root)
    _write_json_atomic(path, artifact)
    return path, _sha256_file(path)


def _normalize_semantic_assessment(assessment: Any) -> list[dict[str, Any]]:
    _require(isinstance(assessment, list), "manual_semantic_review_invalid", "assessment must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in assessment:
        _require(isinstance(item, dict), "manual_semantic_review_invalid", "assessment entries must be objects")
        _require(set(item).issubset({"aspect_id", "status", "detail", "observed_value"}), "manual_semantic_review_invalid", "assessment entries have unexpected keys")
        aspect_id = str(item.get("aspect_id") or "").strip()
        status = str(item.get("status") or "").strip()
        detail = str(item.get("detail") or "").strip()
        _require(aspect_id in MANUAL_SEMANTIC_ASPECT_IDS, "manual_semantic_review_invalid", f"unsupported aspect_id {aspect_id!r}")
        _require(aspect_id not in seen, "manual_semantic_review_invalid", f"duplicate aspect_id {aspect_id!r}")
        _require(status in {"verified", "not_verified", "blocked"}, "manual_semantic_review_invalid", "assessment status is invalid")
        _require(bool(detail), "manual_semantic_review_invalid", "assessment detail is required")
        observed_value = item.get("observed_value")
        if observed_value is not None:
            _require(isinstance(observed_value, (str, int, float, bool, list, dict)) or observed_value is None, "manual_semantic_review_invalid", "observed_value type is invalid")
        seen.add(aspect_id)
        normalized.append(
            {
                "aspect_id": aspect_id,
                "status": status,
                "detail": detail,
                **({"observed_value": observed_value} if observed_value is not None else {}),
            }
        )
    _require(seen == set(MANUAL_SEMANTIC_ASPECT_IDS), "manual_semantic_review_invalid", "assessment coverage is incomplete")
    return normalized


def build_manual_semantic_review_artifact(
    *,
    reviewer_operator_id: str,
    reviewed_image_path: str | Path,
    reviewed_image_sha256: str,
    prompt_artifact_path: str | Path,
    prompt_sha256: str,
    candidate_artifact_path: str | Path,
    candidate_artifact_sha256: str,
    execution_receipt_artifact_path: str | Path,
    execution_receipt_artifact_sha256: str,
    provider_job_id: str | None = None,
    authority_commit_expected: str,
    authority_commit_final: str,
    disposition: str,
    assessment: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    confirmation_statement: str,
    evidence_source: str = "manual_human_semantic_review",
    publishing_authorized: bool = False,
    reviewed_at_utc: str | None = None,
) -> dict[str, Any]:
    _require(isinstance(reviewer_operator_id, str) and reviewer_operator_id.strip(), "manual_semantic_review_invalid", "reviewer_operator_id is required")
    _require(disposition in MANUAL_SEMANTIC_DISPOSITIONS, "manual_semantic_review_invalid", "disposition is invalid")
    _require(confirmation_statement == MANUAL_SEMANTIC_CONFIRMATION_STATEMENT, "manual_semantic_review_invalid", "confirmation_statement mismatch")
    _require(publishing_authorized is False, "manual_semantic_review_invalid", "publishing must remain unauthorized")
    _require(isinstance(evidence_source, str) and evidence_source.strip(), "manual_semantic_review_invalid", "evidence_source is required")
    _require(_is_commit_sha(authority_commit_expected), "manual_semantic_review_invalid", "authority_commit_expected must be a commit sha")
    _require(_is_commit_sha(authority_commit_final), "manual_semantic_review_invalid", "authority_commit_final must be a commit sha")
    if provider_job_id is not None:
        _require(isinstance(provider_job_id, str) and provider_job_id.strip(), "manual_semantic_review_invalid", "provider_job_id must be a string")
    if reviewed_at_utc is None:
        reviewed_at_utc = _utcnow_iso()
    reviewed_path, _ = _validate_bound_file(str(reviewed_image_path), reviewed_image_sha256, label="reviewed_image")
    prompt_path, _ = _validate_bound_file(str(prompt_artifact_path), prompt_sha256, label="prompt_artifact")
    candidate_path, _ = _validate_bound_file(str(candidate_artifact_path), candidate_artifact_sha256, label="candidate_artifact")
    receipt_path, _ = _validate_bound_file(str(execution_receipt_artifact_path), execution_receipt_artifact_sha256, label="execution_receipt_artifact")
    normalized_assessment = _normalize_semantic_assessment(assessment)
    if disposition == "accepted_for_hpe_closure":
        _require(
            all(entry["status"] == "verified" for entry in normalized_assessment),
            "manual_semantic_review_invalid",
            "accepted semantic reviews must mark every aspect verified",
        )
    artifact = {
        "schema_version": SCHEMA_VERSION_MANUAL_SEMANTIC_REVIEW,
        "reviewer_operator_id": reviewer_operator_id.strip(),
        "reviewed_image_path": str(reviewed_path),
        "reviewed_image_sha256": reviewed_image_sha256,
        "prompt_artifact_path": str(prompt_path),
        "prompt_sha256": prompt_sha256,
        "candidate_artifact_path": str(candidate_path),
        "candidate_artifact_sha256": candidate_artifact_sha256,
        "execution_receipt_artifact_path": str(receipt_path),
        "execution_receipt_artifact_sha256": execution_receipt_artifact_sha256,
        **({"provider_job_id": provider_job_id.strip()} if provider_job_id is not None else {}),
        "authority_commit_expected": authority_commit_expected,
        "authority_commit_final": authority_commit_final,
        "reviewed_at_utc": reviewed_at_utc,
        "disposition": disposition,
        "assessment": normalized_assessment,
        "findings": _normalize_findings(findings),
        "confirmation_statement": confirmation_statement,
        "evidence_source": evidence_source.strip(),
        "publishing_authorized": False,
    }
    return artifact


def validate_manual_semantic_review_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(artifact, dict), "manual_semantic_review_invalid", "manual semantic review evidence must be a JSON object")
    _require(
        artifact.get("schema_version") == SCHEMA_VERSION_MANUAL_SEMANTIC_REVIEW,
        "manual_semantic_review_invalid",
        "manual semantic review schema_version mismatch",
    )
    _require(isinstance(artifact.get("reviewer_operator_id"), str) and artifact["reviewer_operator_id"].strip(), "manual_semantic_review_invalid", "reviewer_operator_id is required")
    _require(isinstance(artifact.get("reviewed_at_utc"), str) and artifact["reviewed_at_utc"].strip(), "manual_semantic_review_invalid", "reviewed_at_utc is required")
    _require(artifact.get("disposition") in MANUAL_SEMANTIC_DISPOSITIONS, "manual_semantic_review_invalid", "disposition is invalid")
    _require(artifact.get("confirmation_statement") == MANUAL_SEMANTIC_CONFIRMATION_STATEMENT, "manual_semantic_review_invalid", "confirmation_statement mismatch")
    _require(artifact.get("publishing_authorized") is False, "manual_semantic_review_invalid", "publishing_authorized must be false")
    _require(artifact.get("evidence_source") == MANUAL_SEMANTIC_EVIDENCE_SOURCE, "manual_semantic_review_invalid", "evidence_source mismatch")
    _require(_is_commit_sha(str(artifact.get("authority_commit_expected") or "")), "manual_semantic_review_invalid", "authority_commit_expected must be a commit sha")
    _require(_is_commit_sha(str(artifact.get("authority_commit_final") or "")), "manual_semantic_review_invalid", "authority_commit_final must be a commit sha")
    provider_job_id = artifact.get("provider_job_id")
    if provider_job_id is not None:
        _require(isinstance(provider_job_id, str) and provider_job_id.strip(), "manual_semantic_review_invalid", "provider_job_id must be a string")
    normalized = dict(artifact)
    for field in (
        "reviewed_image",
        "prompt_artifact",
        "candidate_artifact",
        "execution_receipt_artifact",
    ):
        path_key = f"{field}_path"
        sha_key = "prompt_sha256" if field == "prompt_artifact" else f"{field}_sha256"
        path, _ = _validate_bound_file(str(artifact.get(path_key) or ""), str(artifact.get(sha_key) or ""), label=field)
        normalized[path_key] = str(path)
    normalized["assessment"] = _normalize_semantic_assessment(artifact.get("assessment"))
    normalized["findings"] = _normalize_findings(artifact.get("findings"))
    if normalized["disposition"] == "accepted_for_hpe_closure":
        _require(
            all(entry["status"] == "verified" for entry in normalized["assessment"]),
            "manual_semantic_review_invalid",
            "accepted semantic reviews must mark every aspect verified",
        )
    return normalized


def build_ordinary_lane_proof_artifact(
    *,
    reviewer_operator_id: str,
    reviewed_image_path: str | Path,
    reviewed_image_sha256: str,
    prompt_artifact_path: str | Path,
    prompt_sha256: str,
    candidate_artifact_path: str | Path,
    candidate_artifact_sha256: str,
    slot_id: str,
    authority_commit_expected: str,
    authority_commit_final: str,
    disposition: str,
    findings: list[dict[str, Any]],
    confirmation_statement: str,
    evidence_source: str = ORDINARY_LANE_PROOF_EVIDENCE_SOURCE,
    publishing_authorized: bool = False,
    reviewed_at_utc: str | None = None,
) -> dict[str, Any]:
    _require(isinstance(reviewer_operator_id, str) and reviewer_operator_id.strip(), "ordinary_lane_proof_invalid", "reviewer_operator_id is required")
    _require(disposition in ORDINARY_LANE_PROOF_DISPOSITIONS, "ordinary_lane_proof_invalid", "disposition is invalid")
    _require(confirmation_statement == ORDINARY_LANE_PROOF_CONFIRMATION_STATEMENT, "ordinary_lane_proof_invalid", "confirmation_statement mismatch")
    _require(publishing_authorized is False, "ordinary_lane_proof_invalid", "publishing must remain unauthorized")
    _require(evidence_source == ORDINARY_LANE_PROOF_EVIDENCE_SOURCE, "ordinary_lane_proof_invalid", "evidence_source mismatch")
    _require(isinstance(slot_id, str) and slot_id.strip(), "ordinary_lane_proof_invalid", "slot_id is required")
    _require(_is_commit_sha(authority_commit_expected), "ordinary_lane_proof_invalid", "authority_commit_expected must be a commit sha")
    _require(_is_commit_sha(authority_commit_final), "ordinary_lane_proof_invalid", "authority_commit_final must be a commit sha")
    if reviewed_at_utc is None:
        reviewed_at_utc = _utcnow_iso()
    reviewed_path, _ = _validate_bound_file(str(reviewed_image_path), reviewed_image_sha256, label="reviewed_image")
    prompt_path, _ = _validate_bound_file(str(prompt_artifact_path), prompt_sha256, label="prompt_artifact")
    candidate_path, _ = _validate_bound_file(str(candidate_artifact_path), candidate_artifact_sha256, label="candidate_artifact")
    artifact = {
        "schema_version": SCHEMA_VERSION_ORDINARY_LANE_PROOF,
        "reviewer_operator_id": reviewer_operator_id.strip(),
        "reviewed_image_path": str(reviewed_path),
        "reviewed_image_sha256": reviewed_image_sha256,
        "prompt_artifact_path": str(prompt_path),
        "prompt_sha256": prompt_sha256,
        "candidate_artifact_path": str(candidate_path),
        "candidate_artifact_sha256": candidate_artifact_sha256,
        "slot_id": slot_id.strip(),
        "authority_commit_expected": authority_commit_expected,
        "authority_commit_final": authority_commit_final,
        "reviewed_at_utc": reviewed_at_utc,
        "disposition": disposition,
        "findings": _normalize_findings(findings),
        "confirmation_statement": confirmation_statement,
        "evidence_source": evidence_source,
        "publishing_authorized": False,
    }
    return artifact


def validate_ordinary_lane_proof_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(artifact, dict), "ordinary_lane_proof_invalid", "ordinary lane proof evidence must be a JSON object")
    _require(
        artifact.get("schema_version") == SCHEMA_VERSION_ORDINARY_LANE_PROOF,
        "ordinary_lane_proof_invalid",
        "ordinary lane proof schema_version mismatch",
    )
    _require(isinstance(artifact.get("reviewer_operator_id"), str) and artifact["reviewer_operator_id"].strip(), "ordinary_lane_proof_invalid", "reviewer_operator_id is required")
    _require(isinstance(artifact.get("reviewed_at_utc"), str) and artifact["reviewed_at_utc"].strip(), "ordinary_lane_proof_invalid", "reviewed_at_utc is required")
    _require(isinstance(artifact.get("slot_id"), str) and artifact["slot_id"].strip(), "ordinary_lane_proof_invalid", "slot_id is required")
    _require(artifact.get("disposition") in ORDINARY_LANE_PROOF_DISPOSITIONS, "ordinary_lane_proof_invalid", "disposition is invalid")
    _require(artifact.get("confirmation_statement") == ORDINARY_LANE_PROOF_CONFIRMATION_STATEMENT, "ordinary_lane_proof_invalid", "confirmation_statement mismatch")
    _require(artifact.get("publishing_authorized") is False, "ordinary_lane_proof_invalid", "publishing_authorized must be false")
    _require(artifact.get("evidence_source") == ORDINARY_LANE_PROOF_EVIDENCE_SOURCE, "ordinary_lane_proof_invalid", "evidence_source mismatch")
    _require(_is_commit_sha(str(artifact.get("authority_commit_expected") or "")), "ordinary_lane_proof_invalid", "authority_commit_expected must be a commit sha")
    _require(_is_commit_sha(str(artifact.get("authority_commit_final") or "")), "ordinary_lane_proof_invalid", "authority_commit_final must be a commit sha")
    normalized = dict(artifact)
    for field in ("reviewed_image", "prompt_artifact", "candidate_artifact"):
        path_key = f"{field}_path"
        sha_key = "prompt_sha256" if field == "prompt_artifact" else f"{field}_sha256"
        path, _ = _validate_bound_file(str(artifact.get(path_key) or ""), str(artifact.get(sha_key) or ""), label=field)
        normalized[path_key] = str(path)
    normalized["findings"] = _normalize_findings(artifact.get("findings"))
    return normalized


def write_ordinary_lane_proof_artifact(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    artifact: dict[str, Any],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[Path, str]:
    path = output_root / date_str / slot_id / f"lena_hpe_ordinary_lane_proof_{slot_id}_{image_index:02d}.json"
    _write_json_atomic(path, artifact)
    return path, _sha256_file(path)


def write_manual_semantic_review_artifact(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    artifact: dict[str, Any],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[Path, str]:
    path = manual_semantic_review_artifact_path(date_str, slot_id, image_index, output_root)
    _write_json_atomic(path, artifact)
    return path, _sha256_file(path)
