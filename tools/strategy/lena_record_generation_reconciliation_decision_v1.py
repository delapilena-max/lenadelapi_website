from __future__ import annotations

"""Record a human reconciliation authority for Lena generation.

This artifact resolves a strategic recommendation versus executable candidate
divergence. It authorizes handoff preparation only, and it does not authorize
generation, spending, QA bypass, retries, queue mutation, or publishing.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

REPORT_TYPE = "lena_generation_reconciliation_decision"
SCHEMA_VERSION = "lena_generation_reconciliation_decision_v1"
RECONCILIATION_REPORT_TYPE = "lena_generation_reconciliation"
RECONCILIATION_SCHEMA_VERSION = "lena_generation_reconciliation_v1"
DEFAULT_EXPIRATION_MINUTES = 30
DECISIONS_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "reconciliation_decisions"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPERATOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ReconciliationDecisionError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ReconciliationDecisionError(code, detail)


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(_read_bytes(path))
    except OSError as exc:
        raise ReconciliationDecisionError(
            "invalid_reconciliation_artifact",
            f"could not compute sha256 for {path}: {exc}",
        ) from exc


def read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ReconciliationDecisionError("malformed_json", f"could not read {label}: {exc}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ReconciliationDecisionError("malformed_json", f"{label} is not valid JSON: {exc}") from exc
    _require(isinstance(data, dict), "malformed_json", f"{label} must be a JSON object")
    return data


def repo_relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_repo_path(raw_path: str, *, code: str, label: str) -> Path:
    value = str(raw_path or "").strip()
    _require(value, code, f"{label} is missing")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ReconciliationDecisionError("repository_path_invalid", f"{label} escapes the repository: {value}") from exc
    return resolved


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _parse_iso8601_utc(raw: Any, *, code: str, label: str) -> datetime:
    text = str(raw or "").strip()
    if not text:
        raise ReconciliationDecisionError(code, f"{label} is missing")
    normalized = text.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReconciliationDecisionError(code, f"{label} is not a valid ISO-8601 timestamp: {text!r}") from exc
    if value.tzinfo is None:
        raise ReconciliationDecisionError(code, f"{label} must include a UTC offset: {text!r}")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _expires_at(generated_at: datetime, raw: Any | None) -> datetime:
    if raw is None or str(raw).strip() == "":
        return generated_at + timedelta(minutes=DEFAULT_EXPIRATION_MINUTES)
    expires_at = _parse_iso8601_utc(raw, code="decision_expiration_invalid", label="expires_at_utc")
    _require(
        expires_at > generated_at,
        "decision_expiration_invalid",
        "expires_at_utc must be later than generated_at_utc",
    )
    return expires_at


def _validate_source_artifact(
    path_value: str,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[Path, str]:
    path = _resolve_repo_path(path_value, code="missing_reconciliation_artifact", label=label)
    _require(path.is_file(), "missing_reconciliation_artifact", f"missing required artifact: {path}")
    _require(
        SHA256_RE.fullmatch(expected_sha256 or "") is not None,
        "source_artifact_drift",
        f"{label} sha256 is missing or invalid",
    )
    actual = sha256_file(path)
    _require(actual == expected_sha256, "source_artifact_drift", f"{label} sha256 does not match current bytes")
    return path, actual


def _load_reconciliation_artifact(path_value: str) -> tuple[Path, dict[str, Any], str]:
    path = _resolve_repo_path(path_value, code="missing_reconciliation_artifact", label="reconciliation artifact")
    _require(path.is_file(), "missing_reconciliation_artifact", f"missing required artifact: {path}")
    sha256 = sha256_file(path)
    report = read_json(path, label="reconciliation artifact")
    _require(
        report.get("report_type") == RECONCILIATION_REPORT_TYPE,
        "invalid_reconciliation_artifact",
        f"{path} has report_type {report.get('report_type')!r}, expected {RECONCILIATION_REPORT_TYPE!r}",
    )
    _require(
        report.get("schema_version") == RECONCILIATION_SCHEMA_VERSION,
        "invalid_reconciliation_artifact",
        f"{path} has schema_version {report.get('schema_version')!r}, expected {RECONCILIATION_SCHEMA_VERSION!r}",
    )
    return path, report, sha256


def expected_confirmation_phrase(report: dict[str, Any]) -> str:
    return (
        f"I approve reconciling Lena recommendation {report['recommendation_recipe_id']} "
        f"to selected candidate {report['selected_candidate_recipe_id']} "
        f"for slot {report['selected_candidate_slot_id']}. "
        "This decision authorizes handoff preparation only and does not authorize live generation or publishing."
    )


def _source_artifact_record(path_value: str, expected_sha256: str, *, label: str) -> dict[str, Any]:
    path, actual = _validate_source_artifact(path_value, expected_sha256, label=label)
    return {
        "source_artifact_path": repo_relative_path(path),
        "source_artifact_sha256": actual,
        "source_artifact_present": True,
    }


def _read_validated_source_artifact(path_value: str, expected_sha256: str, *, label: str) -> tuple[Path, dict[str, Any]]:
    path, actual = _validate_source_artifact(path_value, expected_sha256, label=label)
    _require(path.is_file(), "source_artifact_drift", f"{label} is missing: {path}")
    report = read_json(path, label=label)
    return path, report


def _decision_identity_core(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "source_reconciliation_artifact_sha256": report["source_reconciliation_artifact_sha256"],
        "operator_id": report["operator_id"],
        "selected_candidate_id": report["selected_candidate_id"],
        "selected_recipe_id": report["selected_recipe_id"],
        "selected_slot_id": report["selected_slot_id"],
        "confirmation_phrase_sha256": report["confirmation_phrase_sha256"],
    }


def _decision_id(report: dict[str, Any]) -> str:
    return sha256_bytes(_canonical_bytes(_decision_identity_core(report)))


def _reconciliation_source_sha(report: dict[str, Any]) -> str:
    core = dict(report)
    core.pop("source_reconciliation_artifact_sha256", None)
    return sha256_bytes(_canonical_bytes(core))


def decision_output_path(date_str: str, decision_id: str) -> Path:
    return DECISIONS_ROOT / date_str / f"lena_generation_reconciliation_decision_{decision_id[:12]}.json"


def _find_existing_decision_for_reconciliation(date_str: str, reconciliation_path: str, reconciliation_sha256: str) -> tuple[Path | None, dict[str, Any] | None]:
    base = DECISIONS_ROOT / date_str
    if not base.is_dir():
        return None, None
    for path in sorted(base.glob("lena_generation_reconciliation_decision_*.json")):
        try:
            existing = read_json(path, label="existing decision artifact")
        except ReconciliationDecisionError:
            continue
        if not isinstance(existing, dict):
            continue
        if (
            existing.get("source_reconciliation_artifact_path") == reconciliation_path
            and existing.get("source_reconciliation_artifact_sha256") == reconciliation_sha256
        ):
            return path, existing
    return None, None


def _validate_reconciliation_artifact(
    reconciliation_artifact_path: str,
    operator_id: str,
    selected_candidate_id: str,
    selected_recipe_id: str,
    selected_slot_id: str,
    confirmation: str,
    expires_at: str | None,
) -> dict[str, Any]:
    reconciliation_path, reconciliation, reconciliation_sha256 = _load_reconciliation_artifact(reconciliation_artifact_path)
    _require(
        str(reconciliation.get("date", "")).strip(),
        "invalid_reconciliation_artifact",
        f"{reconciliation_path} is missing date",
    )
    _require(
        str(reconciliation.get("reconciliation_status", "")).strip() == "operator_review_required",
        "reconciliation_status_invalid",
        "reconciliation_status must be operator_review_required",
    )
    _require(
        bool(reconciliation.get("operator_review_required")) is True,
        "reconciliation_not_operator_reviewable",
        "reconciliation must remain operator-review required",
    )
    _require(
        str(reconciliation.get("divergence_status", "")).strip() == "recipe_mismatch",
        "reconciliation_already_aligned",
        "reconciliation divergence must remain recipe_mismatch",
    )
    _require(
        str(reconciliation.get("resolution_policy", "")).strip() == "explicit_operator_reconciliation_required",
        "reconciliation_status_invalid",
        "reconciliation resolution policy must require explicit operator reconciliation",
    )
    _require(
        not reconciliation.get("final_reconciled_candidate_id")
        and not reconciliation.get("final_reconciled_candidate_recipe_id")
        and not reconciliation.get("final_reconciled_candidate_slot_id"),
        "reconciliation_already_resolved",
        "reconciliation must not already contain final reconciled identifiers",
    )

    operator = str(operator_id or "").strip()
    _require(bool(operator) and OPERATOR_ID_RE.fullmatch(operator) is not None, "operator_id_invalid", "operator_id is invalid")

    chosen_candidate_id = str(selected_candidate_id or "").strip()
    chosen_recipe_id = str(selected_recipe_id or "").strip()
    chosen_slot_id = str(selected_slot_id or "").strip()
    _require(bool(chosen_candidate_id), "selected_candidate_mismatch", "selected candidate id is missing")
    _require(bool(chosen_recipe_id), "selected_recipe_mismatch", "selected recipe id is missing")
    _require(bool(chosen_slot_id), "selected_slot_mismatch", "selected slot id is missing")

    _require(
        chosen_candidate_id == str(reconciliation.get("selected_candidate_id", "")).strip(),
        "selected_candidate_mismatch",
        "selected_candidate_id does not match the reconciliation source",
    )
    _require(
        chosen_recipe_id == str(reconciliation.get("selected_candidate_recipe_id", "")).strip(),
        "selected_recipe_mismatch",
        "selected_recipe_id does not match the reconciliation source",
    )
    _require(
        chosen_slot_id == str(reconciliation.get("selected_candidate_slot_id", "")).strip(),
        "selected_slot_mismatch",
        "selected_slot_id does not match the reconciliation source",
    )

    source_learning = reconciliation.get("source_artifacts", {}).get("learning", {})
    source_recommendation = reconciliation.get("source_artifacts", {}).get("recommendation", {})
    source_candidate = reconciliation.get("source_artifacts", {}).get("selected_candidate", {})
    for key, label in (
        (source_learning, "learning"),
        (source_recommendation, "recommendation"),
        (source_candidate, "selected candidate"),
    ):
        _require(isinstance(key, dict), "source_artifact_drift", f"reconciliation is missing {label} source metadata")

    learning_path = str(source_learning.get("source_artifact_path", "")).strip()
    learning_sha = str(source_learning.get("source_artifact_sha256", "")).strip()
    recommendation_path = str(source_recommendation.get("source_artifact_path", "")).strip()
    recommendation_sha = str(source_recommendation.get("source_artifact_sha256", "")).strip()
    candidate_path = str(source_candidate.get("source_artifact_path", "")).strip()
    candidate_sha = str(source_candidate.get("source_artifact_sha256", "")).strip()
    _require(learning_path and recommendation_path and candidate_path, "source_artifact_drift", "reconciliation source artifact paths are missing")
    _require(learning_sha and recommendation_sha and candidate_sha, "source_artifact_drift", "reconciliation source artifact shas are missing")

    learning = _source_artifact_record(learning_path, learning_sha, label="learning artifact")
    recommendation = _source_artifact_record(recommendation_path, recommendation_sha, label="recommendation artifact")
    selected_candidate = _source_artifact_record(candidate_path, candidate_sha, label="selected candidate artifact")

    current_learning_path, current_learning = _read_validated_source_artifact(
        learning_path, learning_sha, label="learning artifact"
    )
    current_recommendation_path, current_recommendation = _read_validated_source_artifact(
        recommendation_path, recommendation_sha, label="recommendation artifact"
    )
    current_candidate_path, current_candidate = _read_validated_source_artifact(
        candidate_path, candidate_sha, label="selected candidate artifact"
    )

    _require(
        current_learning.get("report_type") == "lena_post_outcome_learning_state",
        "source_artifact_drift",
        "learning artifact drifted or is invalid",
    )
    _require(
        current_recommendation.get("report_type") == "lena_next_generation_step",
        "source_artifact_drift",
        "recommendation artifact drifted or is invalid",
    )
    _require(
        current_candidate.get("schema_version") == "lena_pre_generation_candidate_gate_v1",
        "source_artifact_drift",
        "selected candidate artifact drifted or is invalid",
    )
    _require(
        sha256_file(current_learning_path) == learning_sha,
        "source_artifact_drift",
        "learning artifact sha256 does not match the reconciliation source",
    )
    _require(
        sha256_file(current_recommendation_path) == recommendation_sha,
        "source_artifact_drift",
        "recommendation artifact sha256 does not match the reconciliation source",
    )
    _require(
        sha256_file(current_candidate_path) == candidate_sha,
        "source_artifact_drift",
        "selected candidate artifact sha256 does not match the reconciliation source",
    )

    _require(
        str(current_recommendation.get("date", "")).strip() == str(reconciliation.get("date", "")).strip(),
        "source_artifact_drift",
        "recommendation artifact date drifted",
    )
    _require(
        str(current_candidate.get("as_of_date", "")).strip() == str(reconciliation.get("date", "")).strip(),
        "source_artifact_drift",
        "selected candidate artifact date drifted",
    )

    current_recommendation_body = current_recommendation.get("recommendation")
    _require(isinstance(current_recommendation_body, dict), "invalid_reconciliation_artifact", "recommendation artifact missing recommendation body")
    current_candidate_body = current_candidate.get("candidate")
    _require(isinstance(current_candidate_body, dict), "invalid_reconciliation_artifact", "selected candidate artifact missing candidate body")

    _require(
        str(reconciliation.get("recommendation_recipe_id", "")).strip()
        == str(current_recommendation_body.get("recommended_recipe_id", "")).strip(),
        "source_artifact_drift",
        "recommendation recipe drifted from the reconciliation source",
    )
    _require(
        str(reconciliation.get("selected_candidate_id", "")).strip()
        == str(current_candidate_body.get("candidate_id", "")).strip(),
        "source_artifact_drift",
        "selected candidate id drifted from the reconciliation source",
    )
    _require(
        str(reconciliation.get("selected_candidate_recipe_id", "")).strip()
        == str(current_candidate_body.get("recipe_id", "")).strip(),
        "source_artifact_drift",
        "selected candidate recipe drifted from the reconciliation source",
    )
    _require(
        str(reconciliation.get("selected_candidate_slot_id", "")).strip()
        == str(current_candidate_body.get("slot_id", "")).strip(),
        "source_artifact_drift",
        "selected candidate slot drifted from the reconciliation source",
    )
    _require(
        str(reconciliation.get("selected_candidate_prompt_sha256", "")).strip()
        == str(current_candidate_body.get("prompt_sha256", "")).strip(),
        "source_artifact_drift",
        "selected candidate prompt sha drifted from the reconciliation source",
    )

    phrase = confirmation.strip()
    expected_phrase = expected_confirmation_phrase(reconciliation)
    _require(phrase == expected_phrase, "confirmation_phrase_mismatch", "confirmation phrase must match the reconciliation source exactly")
    reconciliation_source_sha = str(reconciliation.get("source_reconciliation_artifact_sha256", "")).strip()
    if reconciliation_source_sha:
        _require(
            SHA256_RE.fullmatch(reconciliation_source_sha) is not None,
            "reconciliation_sha_mismatch",
            "reconciliation artifact source sha256 is invalid",
        )
        _require(
            reconciliation_source_sha == _reconciliation_source_sha(reconciliation),
            "reconciliation_sha_mismatch",
            "reconciliation artifact source sha256 does not match the reconciliation body",
        )

    generated_at = iso_now()
    expires_at_value = _expires_at(generated_at, expires_at)

    decision = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "date": str(reconciliation.get("date", "")).strip(),
        "generated_at_utc": generated_at.isoformat(),
        "expires_at_utc": expires_at_value.isoformat(),
        "decision_id": "",
        "decision_identity_sha256": "",
        "operator_id": operator,
        "source_reconciliation_artifact_path": repo_relative_path(reconciliation_path),
        "source_reconciliation_artifact_sha256": reconciliation_sha256,
        "source_learning_artifact_path": learning["source_artifact_path"],
        "source_learning_artifact_sha256": learning["source_artifact_sha256"],
        "source_recommendation_artifact_path": recommendation["source_artifact_path"],
        "source_recommendation_artifact_sha256": recommendation["source_artifact_sha256"],
        "source_selected_candidate_artifact_path": selected_candidate["source_artifact_path"],
        "source_selected_candidate_artifact_sha256": selected_candidate["source_artifact_sha256"],
        "original_recommendation_recipe_id": str(reconciliation.get("recommendation_recipe_id", "")).strip(),
        "original_recommendation_outfit_id": str(reconciliation.get("recommendation_outfit_id", "")).strip(),
        "original_recommendation_environment_id": str(reconciliation.get("recommendation_environment_id", "")).strip(),
        "original_recommendation_action_type": str(reconciliation.get("recommendation_action_type", "")).strip(),
        "selected_candidate_id": chosen_candidate_id,
        "selected_recipe_id": chosen_recipe_id,
        "selected_slot_id": chosen_slot_id,
        "selected_hook_id": str(reconciliation.get("selected_candidate_hook_id", "")).strip(),
        "selected_prompt_sha256": str(reconciliation.get("selected_candidate_prompt_sha256", "")).strip(),
        "divergence_status": str(reconciliation.get("divergence_status", "")).strip(),
        "resolution_policy": str(reconciliation.get("resolution_policy", "")).strip(),
        "confirmation_phrase": phrase,
        "confirmation_phrase_sha256": sha256_bytes(phrase.encode("utf-8")),
        "final_reconciled_candidate_id": chosen_candidate_id,
        "final_reconciled_recipe_id": chosen_recipe_id,
        "final_reconciled_slot_id": chosen_slot_id,
        "authority_scope": "handoff_preparation_only",
        "live_generation_authorized": False,
        "publishing_authorized": False,
        "exact_next_allowed_action": "build_next_live_image_handoff",
        "source_artifacts": {
            "reconciliation": {
                "source_artifact_path": repo_relative_path(reconciliation_path),
                "source_artifact_sha256": reconciliation_sha256,
                "source_artifact_present": True,
                "reconciliation_status": str(reconciliation.get("reconciliation_status", "")).strip(),
                "operator_review_required": bool(reconciliation.get("operator_review_required", False)),
                "divergence_status": str(reconciliation.get("divergence_status", "")).strip(),
                "resolution_policy": str(reconciliation.get("resolution_policy", "")).strip(),
            },
            "learning": learning,
            "recommendation": recommendation,
            "selected_candidate": selected_candidate,
        },
        "side_effect_flags": {
            "provider_call_performed": False,
            "generation_performed": False,
            "live_generation_authorized": False,
            "publishing_authorized": False,
            "approval_consumed": False,
            "claims_written": False,
            "receipts_written": False,
            "queue_mutated": False,
            "publish_performed": False,
        },
    }
    decision["decision_id"] = _decision_id(decision)
    decision["decision_identity_sha256"] = decision["decision_id"]
    return decision


def _decision_core_for_fingerprint(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"generated_at_utc", "expires_at_utc"}
    }


def _find_reconciliation_conflicts(report: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    base = DECISIONS_ROOT / report["date"]
    if not base.is_dir():
        return None, None
    for path in sorted(base.glob("lena_generation_reconciliation_decision_*.json")):
        try:
            existing = read_json(path, label="existing decision artifact")
        except ReconciliationDecisionError:
            continue
        if not isinstance(existing, dict):
            continue
        same_reconciliation = (
            existing.get("source_reconciliation_artifact_path") == report["source_reconciliation_artifact_path"]
            and existing.get("source_reconciliation_artifact_sha256") == report["source_reconciliation_artifact_sha256"]
        )
        if not same_reconciliation:
            continue
        same_identity = existing.get("decision_identity_sha256") == report["decision_identity_sha256"]
        same_body = _decision_core_for_fingerprint(existing) == _decision_core_for_fingerprint(report)
        if same_identity and same_body:
            return path, existing
        raise ReconciliationDecisionError(
            "decision_identity_conflict",
            f"reconciliation already has a conflicting operator decision: {path}",
        )
    return None, None


def write_report(report: dict[str, Any], date_str: str) -> tuple[Path, dict[str, Any], bool]:
    path = decision_output_path(date_str, report["decision_id"])
    existing_path, existing = _find_reconciliation_conflicts(report)
    if existing_path is not None and existing is not None:
        return existing_path, existing, True
    if path.exists():
        current = read_json(path, label="decision artifact")
        if _decision_core_for_fingerprint(current) == _decision_core_for_fingerprint(report):
            return path, current, True
        raise ReconciliationDecisionError("decision_identity_conflict", f"refusing to overwrite conflicting decision artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path, report, False


def build_generation_reconciliation_decision(
    reconciliation_artifact_path: str,
    operator_id: str,
    selected_candidate_id: str,
    selected_recipe_id: str,
    selected_slot_id: str,
    confirmation: str,
    *,
    expires_at: str | None = None,
) -> dict[str, Any]:
    _reconciliation_path, reconciliation, _reconciliation_sha256 = _load_reconciliation_artifact(reconciliation_artifact_path)
    return _validate_reconciliation_artifact(
        reconciliation_artifact_path,
        operator_id,
        selected_candidate_id,
        selected_recipe_id,
        selected_slot_id,
        confirmation,
        expires_at,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a human Lena reconciliation decision for a review-required reconciliation artifact."
    )
    parser.add_argument("--reconciliation-artifact", required=True, help="Path to the reconciliation artifact")
    parser.add_argument("--operator-id", required=True, help="Human operator identifier")
    parser.add_argument("--selected-candidate-id", required=True, help="Selected candidate identifier")
    parser.add_argument("--selected-recipe-id", required=True, help="Selected recipe identifier")
    parser.add_argument("--selected-slot-id", required=True, help="Selected slot identifier")
    parser.add_argument("--confirmation", required=True, help="Exact confirmation phrase")
    parser.add_argument("--expires-at", default="", help="Optional ISO-8601 UTC expiration timestamp")
    args = parser.parse_args()

    try:
        report = build_generation_reconciliation_decision(
            args.reconciliation_artifact,
            args.operator_id,
            args.selected_candidate_id,
            args.selected_recipe_id,
            args.selected_slot_id,
            args.confirmation,
            expires_at=args.expires_at or None,
        )
        path, written, reused = write_report(report, str(report["date"]))
    except ReconciliationDecisionError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_code": exc.code,
                    "detail": exc.detail,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(path),
                "date": report["date"],
                "decision_id": written["decision_id"],
                "reused": reused,
                "exact_next_allowed_action": written["exact_next_allowed_action"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
