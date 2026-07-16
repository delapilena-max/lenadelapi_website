from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.influencer_nodes.lena import canonical_brain_assets


ROOT = Path(__file__).resolve().parents[2]

REPORT_TYPE = "lena_generation_reconciliation"
SCHEMA_VERSION = "lena_generation_reconciliation_v1"
LEARNING_REPORT_TYPE = "lena_post_outcome_learning_state"
RECOMMENDATION_REPORT_TYPE = "lena_next_generation_step"
SELECTED_CANDIDATE_REPORT_TYPE = "lena_pre_generation_candidate_gate_v1"

RECONCILED_STATUS = "reconciled"
OPERATOR_REVIEW_REQUIRED_STATUS = "operator_review_required"
ALIGNED_DIVERGENCE_STATUS = "aligned"
RECIPE_MISMATCH_DIVERGENCE_STATUS = "recipe_mismatch"
CANONICAL_MANIFEST_INCOMPLETE_STATUS = "canonical_brain_manifest_incomplete"

RESOLUTION_POLICY_SELECTED_CANDIDATE_AUTHORITATIVE = "selected_candidate_authoritative"
RESOLUTION_POLICY_OPERATOR_REVIEW_REQUIRED = "explicit_operator_reconciliation_required"

NEXT_ACTION_BUILD_NEXT_LIVE_IMAGE_HANDOFF = "build_next_live_image_handoff"
NEXT_ACTION_CREATE_OPERATOR_RECONCILIATION_DECISION = "create_operator_reconciliation_decision"


class ReconciliationError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ReconciliationError(code, detail)


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(_read_bytes(path))
    except OSError as exc:
        raise ReconciliationError(
            "sha256_computation_failed",
            f"could not compute sha256 for {path}: {exc}",
        ) from exc


def read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ReconciliationError("malformed_json", f"could not read {label}: {exc}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ReconciliationError("malformed_json", f"{label} is not valid JSON: {exc}") from exc
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


def _resolve_repo_path(raw_path: str, *, label: str) -> Path:
    value = str(raw_path or "").strip()
    _require(value, "missing_required_input", f"{label} is missing")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ReconciliationError("path_escape", f"{label} escapes the repository: {value}") from exc
    return resolved


def _artifact_record(path: Path, report: dict[str, Any] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_artifact_path": repo_relative_path(path),
        "source_artifact_present": path.is_file(),
        "source_artifact_sha256": sha256_file(path) if path.is_file() else None,
    }
    if isinstance(report, dict):
        record["source_report_type"] = report.get("report_type", "")
        record["source_schema_version"] = report.get("schema_version", "")
        if report.get("date") is not None:
            record["source_date"] = report.get("date", "")
    return record


def _source_revision(candidate_report: dict[str, Any]) -> tuple[str, str]:
    authority_commit = str(candidate_report.get("authority_commit") or "").strip()
    _require(
        len(authority_commit) == 40 and all(ch in "0123456789abcdef" for ch in authority_commit),
        "selected_candidate_required_field_missing_or_invalid",
        "selected candidate authority_commit must be a full lowercase git commit hash",
    )
    return authority_commit[:8], authority_commit


def _rank_index(recipe_ids: list[str], recipe_id: str) -> int | None:
    try:
        return recipe_ids.index(recipe_id)
    except ValueError:
        return None


def _load_learning_report(path: Path, expected_date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(path.is_file(), "missing_required_input", f"missing required learning artifact: {path}")
    report = read_json(path, label="learning artifact")
    _require(
        report.get("report_type") == LEARNING_REPORT_TYPE,
        "wrong_report_type",
        f"{path} has report_type {report.get('report_type')!r}, expected {LEARNING_REPORT_TYPE!r}",
    )
    _require(
        report.get("version") == "v1",
        "wrong_schema_version",
        f"{path} has version {report.get('version')!r}, expected 'v1'",
    )
    _require(
        str(report.get("date", "")).strip() == expected_date,
        "wrong_date",
        f"{path} has date {report.get('date')!r}, expected {expected_date!r}",
    )
    _require(
        isinstance(report.get("metrics_resolution_summary"), dict),
        "missing_required_field",
        f"{path} is missing metrics_resolution_summary",
    )
    _require(
        str(report.get("learning_status", "")).strip(),
        "missing_required_field",
        f"{path} is missing learning_status",
    )
    _require(
        str(report.get("learning_required_follow_up_action", "")).strip(),
        "missing_required_field",
        f"{path} is missing learning_required_follow_up_action",
    )
    return _artifact_record(path, report), report


def _load_recommendation_report(path: Path, expected_date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(path.is_file(), "missing_required_input", f"missing required recommendation artifact: {path}")
    report = read_json(path, label="recommendation artifact")
    _require(
        report.get("report_type") == RECOMMENDATION_REPORT_TYPE,
        "wrong_report_type",
        f"{path} has report_type {report.get('report_type')!r}, expected {RECOMMENDATION_REPORT_TYPE!r}",
    )
    _require(
        report.get("version") == "v1",
        "wrong_schema_version",
        f"{path} has version {report.get('version')!r}, expected 'v1'",
    )
    _require(
        str(report.get("date", "")).strip() == expected_date,
        "wrong_date",
        f"{path} has date {report.get('date')!r}, expected {expected_date!r}",
    )
    recommendation = report.get("recommendation")
    _require(
        isinstance(recommendation, dict),
        "missing_required_field",
        f"{path} is missing recommendation",
    )
    for field in ("recommended_recipe_id", "recommended_outfit_id", "recommended_environment_id", "action_type"):
        _require(
            str(recommendation.get(field, "")).strip(),
            "missing_required_field",
            f"{path} is missing recommendation.{field}",
        )
    _require(
        str(report.get("learning_status", "")).strip(),
        "missing_required_field",
        f"{path} is missing learning_status",
    )
    return _artifact_record(path, report), report


def _load_selected_candidate_report(path: Path, expected_date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(path.is_file(), "missing_required_input", f"missing required selected candidate artifact: {path}")
    report = read_json(path, label="selected candidate artifact")
    _require(
        report.get("schema_version") == SELECTED_CANDIDATE_REPORT_TYPE,
        "wrong_schema_version",
        f"{path} has schema_version {report.get('schema_version')!r}, expected {SELECTED_CANDIDATE_REPORT_TYPE!r}",
    )
    _require(
        str(report.get("as_of_date", "")).strip() == expected_date,
        "wrong_date",
        f"{path} has as_of_date {report.get('as_of_date')!r}, expected {expected_date!r}",
    )
    _require(
        str(report.get("candidate_status", "")).strip() == "selected",
        "candidate_status_not_selected",
        f"{path} must remain a selected candidate artifact",
    )
    candidate = report.get("candidate")
    _require(
        isinstance(candidate, dict),
        "candidate_body_missing",
        f"{path} must contain a candidate object",
    )
    for field in ("candidate_id", "slot_id", "lane", "recipe_id", "hook_id", "prompt_sha256"):
        _require(
            str(candidate.get(field, "")).strip(),
            "selected_candidate_required_field_missing_or_invalid",
            f"{path} is missing candidate.{field}",
        )
    _require(
        str(report.get("authority_commit", "")).strip(),
        "selected_candidate_required_field_missing_or_invalid",
        f"{path} is missing authority_commit",
    )
    _require(
        str(report.get("decision_fingerprint_sha256", "")).strip(),
        "selected_candidate_required_field_missing_or_invalid",
        f"{path} is missing decision_fingerprint_sha256",
    )
    return _artifact_record(path, report), report


def _canonical_manifest_record() -> dict[str, Any]:
    module_path = ROOT / "pipeline" / "influencer_nodes" / "lena" / "canonical_brain_assets.py"
    manifest = canonical_brain_assets.load_canonical_brain_assets()
    return {
        "source_artifact_path": repo_relative_path(module_path),
        "source_artifact_present": module_path.is_file(),
        "source_artifact_sha256": sha256_file(module_path) if module_path.is_file() else None,
        "canonical_brain_assets_status": manifest.get("canonical_brain_assets_status", ""),
        "missing_required_assets": manifest.get("missing_required_assets", []),
        "dirty_workspace_dependency": manifest.get("dirty_workspace_dependency", False),
        "assets": manifest.get("assets", []),
    }


def _comparison_summary(
    *,
    learning: dict[str, Any],
    recommendation: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    recommendation_body = recommendation["recommendation"]
    candidate_body = candidate["candidate"]
    preferred_recipe_ids = [
        recipe_id
        for recipe_id in learning.get("queue_boosts", {}).get("preferred_recipe_ids", [])
        if isinstance(recipe_id, str) and recipe_id.strip()
    ]
    recommended_recipe_id = str(recommendation_body.get("recommended_recipe_id", "")).strip()
    selected_recipe_id = str(candidate_body.get("recipe_id", "")).strip()
    recipe_match = recommended_recipe_id == selected_recipe_id and bool(recommended_recipe_id)
    selected_candidate_id = str(candidate_body.get("candidate_id", "")).strip()
    selected_slot_id = str(candidate_body.get("slot_id", "")).strip()
    selected_hook_id = str(candidate_body.get("hook_id", "")).strip()
    selected_prompt_sha256 = str(candidate_body.get("prompt_sha256", "")).strip()
    return {
        "recommended_recipe_id": recommended_recipe_id,
        "recommended_outfit_id": str(recommendation_body.get("recommended_outfit_id", "")).strip(),
        "recommended_environment_id": str(recommendation_body.get("recommended_environment_id", "")).strip(),
        "recommended_action_type": str(recommendation_body.get("action_type", "")).strip(),
        "recommended_learning_signal_used": recommendation_body.get("learning_signal_used", []),
        "selected_candidate_id": selected_candidate_id,
        "selected_candidate_recipe_id": selected_recipe_id,
        "selected_candidate_slot_id": selected_slot_id,
        "selected_candidate_hook_id": selected_hook_id,
        "selected_candidate_prompt_sha256": selected_prompt_sha256,
        "selected_candidate_authority_commit": str(candidate.get("authority_commit", "")).strip(),
        "selected_candidate_schema_version": str(candidate.get("schema_version", "")).strip(),
        "selected_candidate_status": str(candidate.get("candidate_status", "")).strip(),
        "recipe_match": recipe_match,
        "recommendation_recipe_rank_index": _rank_index(preferred_recipe_ids, recommended_recipe_id),
        "selected_candidate_recipe_rank_index": _rank_index(preferred_recipe_ids, selected_recipe_id),
        "recommended_recipe_is_preferred": recommended_recipe_id in preferred_recipe_ids,
        "selected_candidate_recipe_is_preferred": selected_recipe_id in preferred_recipe_ids,
        "preferred_recipe_ids": preferred_recipe_ids,
    }


def _divergence_status(canonical_ready: bool, recipe_match: bool) -> tuple[str, str, bool]:
    if not canonical_ready:
        return CANONICAL_MANIFEST_INCOMPLETE_STATUS, RESOLUTION_POLICY_OPERATOR_REVIEW_REQUIRED, True
    if not recipe_match:
        return RECIPE_MISMATCH_DIVERGENCE_STATUS, RESOLUTION_POLICY_OPERATOR_REVIEW_REQUIRED, True
    return ALIGNED_DIVERGENCE_STATUS, RESOLUTION_POLICY_SELECTED_CANDIDATE_AUTHORITATIVE, False


def _next_allowed_action(reconciliation_status: str, divergence_status: str) -> dict[str, Any]:
    if reconciliation_status == RECONCILED_STATUS:
        return {
            "status": reconciliation_status,
            "action": NEXT_ACTION_BUILD_NEXT_LIVE_IMAGE_HANDOFF,
            "reason": "recommendation and selected candidate are aligned and may be handed off",
        }
    reason = {
        RECIPE_MISMATCH_DIVERGENCE_STATUS: "recommendation and selected candidate disagree on the recipe",
        CANONICAL_MANIFEST_INCOMPLETE_STATUS: "canonical Lena brain manifest is incomplete",
    }.get(divergence_status, "operator review is required before any handoff can be rebuilt")
    return {
        "status": reconciliation_status,
        "action": NEXT_ACTION_CREATE_OPERATOR_RECONCILIATION_DECISION,
        "reason": reason,
    }


def _source_artifacts(
    *,
    learning_path: Path,
    learning_report: dict[str, Any],
    recommendation_path: Path,
    recommendation_report: dict[str, Any],
    selected_candidate_path: Path,
    selected_candidate_report: dict[str, Any],
    canonical_manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "canonical_brain_assets": {
            "source_artifact_path": repo_relative_path(
                ROOT / "pipeline" / "influencer_nodes" / "lena" / "canonical_brain_assets.py"
            ),
            "source_artifact_present": bool(canonical_manifest.get("source_artifact_present", False)),
            "source_artifact_sha256": canonical_manifest.get("source_artifact_sha256"),
            "canonical_brain_assets_status": canonical_manifest.get("canonical_brain_assets_status", ""),
            "missing_required_assets": canonical_manifest.get("missing_required_assets", []),
            "dirty_workspace_dependency": canonical_manifest.get("dirty_workspace_dependency", False),
            "assets": canonical_manifest.get("assets", []),
        },
        "learning": {
            **_artifact_record(learning_path, learning_report),
            "learning_status": str(learning_report.get("learning_status", "")).strip(),
            "learning_required_follow_up_action": str(
                learning_report.get("learning_required_follow_up_action", "")
            ).strip(),
            "preferred_recipe_ids": [
                recipe_id
                for recipe_id in learning_report.get("queue_boosts", {}).get("preferred_recipe_ids", [])
                if isinstance(recipe_id, str) and recipe_id.strip()
            ],
        },
        "recommendation": {
            **_artifact_record(recommendation_path, recommendation_report),
            "learning_status": str(recommendation_report.get("learning_status", "")).strip(),
            "learning_required_follow_up_action": str(
                recommendation_report.get("learning_required_follow_up_action", "")
            ).strip(),
            "recommendation": recommendation_report.get("recommendation", {}),
        },
        "selected_candidate": {
            **_artifact_record(selected_candidate_path, selected_candidate_report),
            "selected_candidate": selected_candidate_report.get("candidate", {}),
            "authority_commit": str(selected_candidate_report.get("authority_commit", "")).strip(),
            "decision_fingerprint_sha256": str(
                selected_candidate_report.get("decision_fingerprint_sha256", "")
            ).strip(),
        },
    }


def build_generation_reconciliation(
    date_str: str,
    learning_artifact_path: str,
    recommendation_artifact_path: str,
    selected_candidate_artifact_path: str,
) -> dict[str, Any]:
    learning_path = _resolve_repo_path(learning_artifact_path, label="learning artifact")
    recommendation_path = _resolve_repo_path(recommendation_artifact_path, label="recommendation artifact")
    selected_candidate_path = _resolve_repo_path(
        selected_candidate_artifact_path, label="selected candidate artifact"
    )

    learning_record, learning_report = _load_learning_report(learning_path, date_str)
    recommendation_record, recommendation_report = _load_recommendation_report(recommendation_path, date_str)
    selected_candidate_record, selected_candidate_report = _load_selected_candidate_report(
        selected_candidate_path, date_str
    )

    canonical_manifest = _canonical_manifest_record()
    comparison = _comparison_summary(
        learning=learning_report,
        recommendation=recommendation_report,
        candidate=selected_candidate_report,
    )

    canonical_ready = (
        canonical_manifest.get("canonical_brain_assets_status") == "ready"
        and not canonical_manifest.get("missing_required_assets")
        and canonical_manifest.get("dirty_workspace_dependency") is False
    )
    divergence_status, resolution_policy, operator_review_required = _divergence_status(
        canonical_ready,
        bool(comparison["recipe_match"]),
    )

    reconciliation_status = RECONCILED_STATUS if not operator_review_required else OPERATOR_REVIEW_REQUIRED_STATUS
    final_candidate = selected_candidate_report if reconciliation_status == RECONCILED_STATUS else None
    final_candidate_body = final_candidate.get("candidate", {}) if isinstance(final_candidate, dict) else {}

    ranking_evidence = {
        "learning_status": str(learning_report.get("learning_status", "")).strip(),
        "learning_required_follow_up_action": str(
            learning_report.get("learning_required_follow_up_action", "")
        ).strip(),
        "preferred_recipe_ids": comparison["preferred_recipe_ids"],
        "recommended_recipe_rank_index": comparison["recommendation_recipe_rank_index"],
        "selected_candidate_recipe_rank_index": comparison["selected_candidate_recipe_rank_index"],
        "recommended_recipe_is_preferred": comparison["recommended_recipe_is_preferred"],
        "selected_candidate_recipe_is_preferred": comparison["selected_candidate_recipe_is_preferred"],
    }
    compatibility_evidence = {
        "recipe_match": comparison["recipe_match"],
        "selected_candidate_status": comparison["selected_candidate_status"],
        "selected_candidate_body_present": True,
        "recommended_recipe_id": comparison["recommended_recipe_id"],
        "recommended_outfit_id": comparison["recommended_outfit_id"],
        "recommended_environment_id": comparison["recommended_environment_id"],
        "selected_candidate_recipe_id": comparison["selected_candidate_recipe_id"],
        "selected_candidate_slot_id": comparison["selected_candidate_slot_id"],
        "selected_candidate_id": comparison["selected_candidate_id"],
        "selected_candidate_hook_id": comparison["selected_candidate_hook_id"],
        "selected_candidate_prompt_sha256": comparison["selected_candidate_prompt_sha256"],
        "selected_candidate_authority_commit": comparison["selected_candidate_authority_commit"],
        "selected_candidate_schema_version": comparison["selected_candidate_schema_version"],
        "recommendation_learning_signal_used": comparison["recommended_learning_signal_used"],
    }

    blocking_reasons = []
    if divergence_status == RECIPE_MISMATCH_DIVERGENCE_STATUS:
        blocking_reasons.append("recipe_mismatch")
    elif divergence_status == CANONICAL_MANIFEST_INCOMPLETE_STATUS:
        blocking_reasons.append("canonical_brain_manifest_incomplete")

    source_revision = comparison["selected_candidate_authority_commit"][:8]
    source_revision_commit = comparison["selected_candidate_authority_commit"]
    fingerprint_core = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "source_revision": source_revision,
        "source_revision_commit": source_revision_commit,
        "learning_artifact_sha256": learning_record["source_artifact_sha256"],
        "recommendation_artifact_sha256": recommendation_record["source_artifact_sha256"],
        "selected_candidate_artifact_sha256": selected_candidate_record["source_artifact_sha256"],
        "canonical_brain_assets_sha256": canonical_manifest["source_artifact_sha256"],
        "learning_status": learning_report.get("learning_status", ""),
        "recommended_recipe_id": comparison["recommended_recipe_id"],
        "selected_candidate_recipe_id": comparison["selected_candidate_recipe_id"],
        "reconciliation_status": reconciliation_status,
        "divergence_status": divergence_status,
        "resolution_policy": resolution_policy,
        "operator_review_required": operator_review_required,
        "blocking_reasons": blocking_reasons,
    }
    reconciliation_fingerprint_sha256 = sha256_bytes(
        json.dumps(fingerprint_core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    output_path = (
        ROOT
        / "pipeline"
        / "strategy"
        / "lena"
        / "reconciliations"
        / date_str
        / f"lena_generation_reconciliation_{source_revision}_{reconciliation_fingerprint_sha256[:12]}.json"
    )

    report = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "generated_at": iso_now(),
        "source_revision": source_revision,
        "source_revision_commit": source_revision_commit,
        "source_artifacts": _source_artifacts(
            learning_path=learning_path,
            learning_report=learning_report,
            recommendation_path=recommendation_path,
            recommendation_report=recommendation_report,
            selected_candidate_path=selected_candidate_path,
            selected_candidate_report=selected_candidate_report,
            canonical_manifest=canonical_manifest,
        ),
        "learning_status": str(learning_report.get("learning_status", "")).strip(),
        "recommendation_recipe_id": comparison["recommended_recipe_id"],
        "recommendation_outfit_id": comparison["recommended_outfit_id"],
        "recommendation_environment_id": comparison["recommended_environment_id"],
        "recommendation_action_type": comparison["recommended_action_type"],
        "recommendation_learning_signal_used": comparison["recommended_learning_signal_used"],
        "selected_candidate_id": comparison["selected_candidate_id"],
        "selected_candidate_recipe_id": comparison["selected_candidate_recipe_id"],
        "selected_candidate_slot_id": comparison["selected_candidate_slot_id"],
        "selected_candidate_hook_id": comparison["selected_candidate_hook_id"],
        "selected_candidate_prompt_sha256": comparison["selected_candidate_prompt_sha256"],
        "selected_candidate_authority_commit": comparison["selected_candidate_authority_commit"],
        "selected_candidate_schema_version": comparison["selected_candidate_schema_version"],
        "selected_candidate_status": comparison["selected_candidate_status"],
        "ranking_evidence": ranking_evidence,
        "compatibility_evidence": compatibility_evidence,
        "blocking_reasons": blocking_reasons,
        "divergence_status": divergence_status,
        "resolution_policy": resolution_policy,
        "reconciliation_status": reconciliation_status,
        "operator_review_required": operator_review_required,
        "final_reconciled_candidate_id": comparison["selected_candidate_id"] if reconciliation_status == RECONCILED_STATUS else None,
        "final_reconciled_candidate_recipe_id": comparison["selected_candidate_recipe_id"] if reconciliation_status == RECONCILED_STATUS else None,
        "final_reconciled_candidate_slot_id": comparison["selected_candidate_slot_id"] if reconciliation_status == RECONCILED_STATUS else None,
        "final_reconciled_candidate_hook_id": comparison["selected_candidate_hook_id"] if reconciliation_status == RECONCILED_STATUS else None,
        "final_reconciled_candidate_prompt_sha256": comparison["selected_candidate_prompt_sha256"] if reconciliation_status == RECONCILED_STATUS else None,
        "final_reconciled_candidate_artifact_path": repo_relative_path(selected_candidate_path) if reconciliation_status == RECONCILED_STATUS else None,
        "final_reconciled_candidate_artifact_sha256": selected_candidate_record["source_artifact_sha256"] if reconciliation_status == RECONCILED_STATUS else None,
        "exact_next_allowed_action": (
            NEXT_ACTION_BUILD_NEXT_LIVE_IMAGE_HANDOFF
            if reconciliation_status == RECONCILED_STATUS
            else NEXT_ACTION_CREATE_OPERATOR_RECONCILIATION_DECISION
        ),
        "next_allowed_action": _next_allowed_action(reconciliation_status, divergence_status),
        "reconciliation_fingerprint_sha256": reconciliation_fingerprint_sha256,
        "output_artifact_path": repo_relative_path(output_path),
        "dirty_workspace_dependency": False,
        "shadow_mode_only": True,
        "provider_call_performed": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "queue_mutated": False,
        "publish_performed": False,
    }
    return report


def write_report(report: dict[str, Any], date_str: str) -> Path:
    source_revision = str(report.get("source_revision", "")).strip() or "unknown"
    fingerprint = str(report.get("reconciliation_fingerprint_sha256", "")).strip()
    _require(
        source_revision,
        "missing_required_field",
        "report is missing source_revision",
    )
    _require(
        len(fingerprint) == 64,
        "missing_required_field",
        "report is missing reconciliation_fingerprint_sha256",
    )
    path = (
        ROOT
        / "pipeline"
        / "strategy"
        / "lena"
        / "reconciliations"
        / date_str
        / f"lena_generation_reconciliation_{source_revision}_{fingerprint[:12]}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the Lena generation reconciliation report."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for outputs")
    parser.add_argument("--learning-artifact", required=True, help="Path to the learning artifact")
    parser.add_argument(
        "--recommendation-artifact",
        required=True,
        help="Path to the next-generation recommendation artifact",
    )
    parser.add_argument(
        "--selected-candidate-artifact",
        required=True,
        help="Path to the selected candidate artifact",
    )
    args = parser.parse_args()

    try:
        report = build_generation_reconciliation(
            args.date,
            args.learning_artifact,
            args.recommendation_artifact,
            args.selected_candidate_artifact,
        )
        path = write_report(report, args.date)
    except ReconciliationError as exc:
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
                "date": args.date,
                "reconciliation_status": report["reconciliation_status"],
                "exact_next_allowed_action": report["exact_next_allowed_action"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
