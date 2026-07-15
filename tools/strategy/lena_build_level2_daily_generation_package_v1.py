from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.influencer_nodes.lena import autonomy_ladder


ROOT = Path(__file__).resolve().parents[2]
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
APPROVAL_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "generation"
QA_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
RETRY_DECISIONS_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "retry_decisions"
RETRY_HANDOFFS_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "retry_handoffs"

REPORT_TYPE = "lena_level2_daily_generation_package"
SCHEMA_VERSION = "v1"
STRATEGY_PREP_REPORT_TYPE = "lena_strategy_autonomy_prep"
NEXT_STEP_REPORT_TYPE = "lena_next_generation_step"
HANDOFF_REPORT_TYPE = "lena_next_live_image_handoff"
GENERATION_APPROVAL_SCHEMA_VERSION = "v1"
RETRY_DECISION_SCHEMA_VERSION = "lena_retry_decision_v1"
RETRY_HANDOFF_SCHEMA_VERSION = "lena_higgsfield_retry_handoff_v1"
QA_SCHEMA_VERSION = "lena_photo_qa_disposition_v1"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def repo_relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def dated_path(base: Path, date_str: str, filename: str) -> Path:
    return base / date_str / filename


def package_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_level2_daily_generation_package_{date_str}.json")


def strategy_prep_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_strategy_autonomy_prep_{date_str}.json")


def next_step_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_generation_step_{date_str}.json")


def handoff_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_live_image_handoff_{date_str}.json")


def retry_decision_paths(date_str: str) -> list[Path]:
    base = RETRY_DECISIONS_ROOT / date_str
    return sorted(base.glob("*_retry_decision.json"))


def retry_handoff_paths(date_str: str) -> list[Path]:
    base = RETRY_HANDOFFS_ROOT / date_str
    return sorted(base.glob("*_retry_handoff.json"))


def approval_paths(date_str: str, slot_id: str | None = None) -> list[Path]:
    base = APPROVAL_ROOT / date_str
    if slot_id:
        exact = base / f"{slot_id}_higgsfield_generation_approval.json"
        if exact.is_file():
            return [exact]
    return sorted(base.glob("*_higgsfield_generation_approval.json"))


def claim_path(date_str: str, slot_id: str) -> Path:
    return APPROVAL_ROOT / date_str / f"{slot_id}_higgsfield_generation_claim.json"


def receipt_path(date_str: str, slot_id: str) -> Path:
    return APPROVAL_ROOT / date_str / f"{slot_id}_higgsfield_generation_execution_receipt.json"


def qa_paths(date_str: str, slot_id: str | None = None) -> list[Path]:
    base = QA_ROOT / date_str
    if slot_id:
        matching = sorted(base.glob(f"{slot_id}__*_qa_disposition.json"))
        if matching:
            return matching
    return sorted(base.glob("*_qa_disposition.json"))


def load_report(path: Path, *, report_type: str | None = None, schema_version: str | None = None) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        report = read_json(path)
    except Exception:
        return None
    if not isinstance(report, dict):
        return None
    if report_type is not None and report.get("report_type") != report_type:
        return None
    if schema_version is not None and report.get("schema_version") != schema_version:
        return None
    return report


def _section_base(path: Path | None, report: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "source_artifact_path": repo_relative_path(path),
        "source_artifact_present": report is not None,
        "source_report_type": report.get("report_type", "") if report else "",
        "source_schema_version": report.get("schema_version", "") if report else "",
    }


def _summary_from(report: dict[str, Any] | None, keys: list[str]) -> dict[str, Any]:
    if not report:
        return {}
    return {key: report.get(key) for key in keys}


def _diagnostic_entry(
    *,
    expected_artifact: str,
    artifact_exists: bool,
    blocking: bool,
    diagnostic: str,
    safe_next_step: str,
) -> dict[str, Any]:
    return {
        "expected_artifact": expected_artifact,
        "artifact_exists": artifact_exists,
        "blocking": blocking,
        "diagnostic": diagnostic,
        "safe_next_step": safe_next_step,
    }


def _artifact_diagnostic(
    path: Path | None,
    report: dict[str, Any] | None,
    *,
    expected_artifact: str,
    blocking: bool,
    diagnostic: str,
    safe_next_step: str,
) -> dict[str, Any]:
    artifact_exists = bool(path and path.is_file())
    return {
        "source_artifact_path": repo_relative_path(path),
        "source_artifact_present": report is not None,
        "source_report_type": report.get("report_type", "") if report else "",
        "source_schema_version": report.get("schema_version", "") if report else "",
        "diagnostic": _diagnostic_entry(
            expected_artifact=expected_artifact,
            artifact_exists=artifact_exists,
            blocking=blocking,
            diagnostic=diagnostic,
            safe_next_step=safe_next_step,
        ),
    }


def _candidate_slot_id(date_str: str, candidate_selection: dict[str, Any] | None, handoff: dict[str, Any] | None) -> str:
    if handoff:
        slot_id = str(handoff.get("selected_slot_id") or handoff.get("queue_head", {}).get("slot_id") or "").strip()
        if slot_id:
            return slot_id
    if candidate_selection:
        recipe_id = str(candidate_selection.get("recommendation", {}).get("recommended_recipe_id") or "").strip()
        if recipe_id:
            return f"higgsfield-{date_str.replace('-', '')}-{recipe_id}-photo"
    return ""


def build_strategy_plan_state(date_str: str) -> dict[str, Any]:
    path = strategy_prep_path(date_str)
    report = load_report(path, report_type=STRATEGY_PREP_REPORT_TYPE)
    expected_artifact = str(path.relative_to(ROOT).as_posix())
    safe_next_step = f"python -m tools.strategy.lena_run_strategy_autonomy_prep_v1 --date {date_str}"
    if report is None:
        return {
            **_artifact_diagnostic(
                path,
                None,
                expected_artifact=expected_artifact,
                blocking=True,
                diagnostic="autonomous_eligibility_pending: the strategy plan state is missing, so the machine eligibility gate cannot advance.",
                safe_next_step=safe_next_step,
            ),
            "status": "blocked_missing_input",
            "summary": {},
        }

    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        **_artifact_diagnostic(
            path,
            report,
            expected_artifact=expected_artifact,
            blocking=False,
            diagnostic="strategy plan state present and ready for autonomous eligibility review.",
            safe_next_step=safe_next_step,
        ),
        "status": "ready",
        "summary": {
            "strategy_gate_blocked": summary.get("strategy_gate_blocked"),
            "recommended_recipe_id": summary.get("recommended_recipe_id", ""),
            "queue_recipes": summary.get("queue_recipes", []),
            "next_live_image_handoff_path": summary.get("next_live_image_handoff_path", ""),
            "broader_autonomous_generation_ready": summary.get("broader_autonomous_generation_ready", False),
            "learning_status": summary.get("learning_status", ""),
        },
    }


def build_candidate_selection_state(date_str: str) -> dict[str, Any]:
    path = next_step_path(date_str)
    report = load_report(path, report_type=NEXT_STEP_REPORT_TYPE)
    expected_artifact = str(path.relative_to(ROOT).as_posix())
    safe_next_step = f"python -m tools.strategy.lena_recommend_next_generation_step_v1 --date {date_str}"
    if report is None:
        return {
            **_artifact_diagnostic(
                path,
                None,
                expected_artifact=expected_artifact,
                blocking=True,
                diagnostic="autonomous_eligibility_pending: the candidate selection report is missing, so no next candidate can be summarized.",
                safe_next_step=safe_next_step,
            ),
            "status": "blocked_missing_input",
            "summary": {},
        }

    recommendation = report.get("recommendation", {})
    if not isinstance(recommendation, dict):
        recommendation = {}
    return {
        **_artifact_diagnostic(
            path,
            report,
            expected_artifact=expected_artifact,
            blocking=False,
            diagnostic="candidate selection report present and suitable for Level 2 package summary.",
            safe_next_step=safe_next_step,
        ),
        "status": "ready",
        "summary": {
            "action_type": recommendation.get("action_type", ""),
            "recommended_recipe_id": recommendation.get("recommended_recipe_id", ""),
            "recommended_outfit_id": recommendation.get("recommended_outfit_id", ""),
            "recommended_environment_id": recommendation.get("recommended_environment_id", ""),
            "next_live_gate": recommendation.get("next_live_gate", ""),
            "learning_status": report.get("learning_status", ""),
            "learning_required_follow_up_action": report.get("learning_required_follow_up_action", ""),
            "learning_signal_used": recommendation.get("learning_signal_used", []),
        },
    }


def build_live_generation_handoff_state(date_str: str, candidate_selection: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    path = handoff_path(date_str)
    report = load_report(path, report_type=HANDOFF_REPORT_TYPE)
    expected_artifact = str(path.relative_to(ROOT).as_posix())
    safe_next_step = f"python -m tools.strategy.lena_build_next_live_image_handoff_v1 --date {date_str}"
    slot_id = _candidate_slot_id(date_str, candidate_selection, report)
    if report is None:
        return (
            {
                **_artifact_diagnostic(
                    path,
                    None,
                    expected_artifact=expected_artifact,
                    blocking=True,
                    diagnostic="machine_eligibility_gate: the live-generation handoff is missing, so no boundary-ready packet can be summarized.",
                    safe_next_step=safe_next_step,
                ),
                "status": "blocked_missing_input",
                "summary": {
                    "selected_slot_id": slot_id,
                },
            },
            slot_id,
        )

    return (
        {
            **_artifact_diagnostic(
                path,
                report,
                expected_artifact=expected_artifact,
                blocking=False,
                diagnostic="live-generation handoff present and ready for operator review.",
                safe_next_step=safe_next_step,
            ),
            "status": "ready",
            "summary": {
                "selected_slot_id": report.get("selected_slot_id", ""),
                "packet_state": report.get("packet_state", ""),
                "dry_run_executor_contract_state": report.get("dry_run_executor_contract_state", ""),
                "live_execution_state": report.get("live_execution_state", ""),
                "live_execution_authorized": report.get("live_execution_authorized", False),
                "generation_approval_required": report.get("generation_approval_required", False),
                "manual_operator_approval_required": report.get("manual_operator_approval_required", False),
                "provider_call_performed": report.get("provider_call_performed", False),
                "generation_performed": report.get("generation_performed", False),
                "publish_authorized": report.get("publish_authorized", False),
                "manual_publish_review_required": report.get("manual_publish_review_required", False),
                "repo_executor_path": report.get("repo_executor_path", ""),
                "selected_prompt_input_artifact_path": report.get("selected_prompt_input_artifact_path", ""),
            },
        },
        slot_id,
    )


def build_approval_boundary_state(date_str: str, slot_id: str) -> dict[str, Any]:
    expected_generation_artifact = (
        repo_relative_path(approval_paths(date_str, slot_id)[0])
        if approval_paths(date_str, slot_id)
        else str(
            Path("pipeline")
            / "approvals"
            / "lena"
            / "generation"
            / date_str
            / f"{slot_id or '<slot_id>'}_higgsfield_generation_approval.json"
        )
    )
    expected_claim_artifact = repo_relative_path(claim_path(date_str, slot_id)) if slot_id else str(
        Path("pipeline")
        / "approvals"
        / "lena"
        / "generation"
        / date_str
        / "<slot_id>_higgsfield_generation_claim.json"
    )
    expected_receipt_artifact = repo_relative_path(receipt_path(date_str, slot_id)) if slot_id else str(
        Path("pipeline")
        / "approvals"
        / "lena"
        / "generation"
        / date_str
        / "<slot_id>_higgsfield_generation_execution_receipt.json"
    )
    safe_next_step = (
        "tools/lena_higgsfield_generation_approval_v1.py library entrypoints "
        "(build_generation_approval_record, build_generation_claim_record, "
        "build_generation_execution_receipt_record; no CLI entrypoint is defined)"
    )
    if not slot_id:
        return {
            "status": "approval_pending",
            "diagnostic": _diagnostic_entry(
                expected_artifact=expected_generation_artifact,
                artifact_exists=False,
                blocking=True,
                diagnostic="autonomous_eligibility_pending: the approval boundary cannot be completed until a live-generation handoff yields a slot_id.",
                safe_next_step=safe_next_step,
            ),
            "generation_approval": {
                "source_artifact_path": "",
                "source_artifact_present": False,
                "source_report_type": "",
                "source_schema_version": "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_generation_artifact,
                    artifact_exists=False,
                    blocking=True,
                    diagnostic="bootstrap approval scaffold missing because no slot_id is available yet.",
                    safe_next_step=safe_next_step,
                ),
            },
            "claim": {
                "source_artifact_path": "",
                "source_artifact_present": False,
                "source_report_type": "",
                "source_schema_version": "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_claim_artifact,
                    artifact_exists=False,
                    blocking=True,
                    diagnostic="bootstrap claim scaffold missing because no slot_id is available yet.",
                    safe_next_step=safe_next_step,
                ),
                "status": "missing",
            },
            "receipt": {
                "source_artifact_path": "",
                "source_artifact_present": False,
                "source_report_type": "",
                "source_schema_version": "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_receipt_artifact,
                    artifact_exists=False,
                    blocking=True,
                    diagnostic="bootstrap receipt scaffold missing because no slot_id is available yet.",
                    safe_next_step=safe_next_step,
                ),
                "status": "missing",
            },
        }

    candidates = approval_paths(date_str, slot_id)
    approval_path = candidates[0] if candidates else None
    approval = load_report(approval_path, report_type="lena_higgsfield_generation_approval") if approval_path else None
    if approval is None:
        return {
            "status": "approval_pending",
            "diagnostic": _diagnostic_entry(
                expected_artifact=expected_generation_artifact,
                artifact_exists=bool(approval_path and approval_path.is_file()),
                blocking=True,
                diagnostic="autonomous_eligibility_pending: the approval boundary is waiting on a committed approval artifact for the selected slot.",
                safe_next_step=safe_next_step,
            ),
            "generation_approval": {
                **_artifact_diagnostic(
                    approval_path,
                    None,
                    expected_artifact=expected_generation_artifact,
                    blocking=True,
                    diagnostic="approval boundary artifact missing; bootstrap approval scaffold is still required.",
                    safe_next_step=safe_next_step,
                ),
                "status": "missing",
                "summary": {},
            },
            "claim": {
                "source_artifact_path": repo_relative_path(claim_path(date_str, slot_id)),
                "source_artifact_present": False,
                "source_report_type": "",
                "source_schema_version": "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_claim_artifact,
                    artifact_exists=claim_path(date_str, slot_id).is_file(),
                    blocking=True,
                    diagnostic="claim record is missing; the machine eligibility gate still needs a bootstrap claim record for auditability.",
                    safe_next_step=safe_next_step,
                ),
                "status": "missing",
            },
            "receipt": {
                "source_artifact_path": repo_relative_path(receipt_path(date_str, slot_id)),
                "source_artifact_present": False,
                "source_report_type": "",
                "source_schema_version": "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_receipt_artifact,
                    artifact_exists=receipt_path(date_str, slot_id).is_file(),
                    blocking=True,
                    diagnostic="receipt record is missing; the machine eligibility gate still needs a bootstrap receipt for auditability.",
                    safe_next_step=safe_next_step,
                ),
                "status": "missing",
            },
        }

    claim = load_report(claim_path(date_str, slot_id), report_type="lena_higgsfield_generation_claim")
    receipt = load_report(receipt_path(date_str, slot_id), report_type="lena_higgsfield_generation_execution_receipt")
    return {
        "status": "approved",
        "diagnostic": _diagnostic_entry(
            expected_artifact=expected_generation_artifact,
            artifact_exists=True,
            blocking=False,
            diagnostic="approval boundary artifacts are present; machine eligibility can be audited without assuming permanent human approval as the product goal.",
            safe_next_step=safe_next_step,
        ),
        "generation_approval": {
            **_artifact_diagnostic(
                approval_path,
                approval,
                expected_artifact=expected_generation_artifact,
                blocking=False,
                diagnostic="generation approval artifact present and suitable for bootstrap audit review.",
                safe_next_step=safe_next_step,
            ),
            "status": "recorded",
            "summary": {
                "operator_id": approval.get("operator_id", ""),
                "approved_at_utc": approval.get("approved_at_utc", ""),
                "expires_at_utc": approval.get("expires_at_utc", ""),
                "authorized_attempts": approval.get("authorized_attempts", 0),
                "upload_authorized": approval.get("upload_authorized", False),
                "queue_promotion_authorized": approval.get("queue_promotion_authorized", False),
                "publish_authorized": approval.get("publish_authorized", False),
                "analytics_mutation_authorized": approval.get("analytics_mutation_authorized", False),
                "confirmation_statement": approval.get("confirmation_statement", ""),
            },
        },
        "claim": {
            **_artifact_diagnostic(
                claim_path(date_str, slot_id),
                claim,
                expected_artifact=expected_claim_artifact,
                blocking=False,
                diagnostic="claim record present and suitable for bootstrap audit review.",
                safe_next_step=safe_next_step,
            ),
            "status": "recorded" if claim else "missing",
            "summary": _summary_from(
                claim,
                [
                    "report_type",
                    "schema_version",
                    "claim_type",
                    "operator_id",
                    "approved_at_utc",
                    "expires_at_utc",
                    "authorized_attempts",
                    "upload_authorized",
                    "queue_promotion_authorized",
                    "publish_authorized",
                    "analytics_mutation_authorized",
                ],
            ),
        },
        "receipt": {
            **_artifact_diagnostic(
                receipt_path(date_str, slot_id),
                receipt,
                expected_artifact=expected_receipt_artifact,
                blocking=False,
                diagnostic="receipt record present and suitable for bootstrap audit review.",
                safe_next_step=safe_next_step,
            ),
            "status": "recorded" if receipt else "missing",
            "summary": _summary_from(
                receipt,
                [
                    "report_type",
                    "schema_version",
                    "receipt_type",
                    "operator_id",
                    "outcome",
                    "authorized_attempts",
                    "upload_authorized",
                    "queue_promotion_authorized",
                    "publish_authorized",
                    "analytics_mutation_authorized",
                    "output_path",
                ],
            ),
        },
    }


def build_qa_disposition_state(date_str: str, slot_id: str) -> dict[str, Any]:
    candidates = qa_paths(date_str, slot_id)
    qa_path = candidates[0] if candidates else None
    qa_report = load_report(qa_path, schema_version=QA_SCHEMA_VERSION) if qa_path else None
    expected_artifact = repo_relative_path(qa_path) if qa_path else str(
        Path("pipeline") / "asset_review" / "lena" / date_str / f"{slot_id or '<slot_id>'}__<image_sha>_qa_disposition.json"
    )
    safe_next_step = (
        "python -m tools.lena_photo_qa_disposition_v1 --decision-artifact <decision> --manifest <manifest> "
        "--image <image> --expected-image-sha256 <sha256> --identity-evidence <path> "
        "--identity-reference-authority-artifact <path> --identity-reference-authority-sha256 <sha256>"
    )
    if qa_report is None:
        return {
            **_artifact_diagnostic(
                qa_path,
                None,
                expected_artifact=expected_artifact,
                blocking=True,
                diagnostic="machine_eligibility_gate: the QA disposition artifact is missing, so readiness cannot be concluded.",
                safe_next_step=safe_next_step,
            ),
            "status": "blocked_missing_input",
            "summary": {},
        }

    disposition = str(qa_report.get("disposition", "")).strip()
    if disposition == "hard_stop":
        status = "qa_blocked"
    elif bool(qa_report.get("retry_eligible")):
        status = "retry_recommended"
    else:
        status = "ready"
    return {
        **_artifact_diagnostic(
            qa_path,
            qa_report,
            expected_artifact=expected_artifact,
            blocking=status != "ready",
            diagnostic="QA disposition present; readiness can be summarized without calling the visual-review provider.",
            safe_next_step=safe_next_step,
        ),
        "status": status,
        "summary": {
            "disposition": qa_report.get("disposition", ""),
            "retry_eligible": qa_report.get("retry_eligible", False),
            "confidence": qa_report.get("confidence", ""),
            "hard_stop_reason": qa_report.get("hard_stop_reason", ""),
            "exact_next_allowed_action": qa_report.get("exact_next_allowed_action", ""),
            "decision_kind": qa_report.get("qa_inputs", {}).get("decision_kind", ""),
            "provider_called": qa_report.get("provider_called", False),
            "side_effects_performed": qa_report.get("side_effects_performed", []),
        },
    }


def build_retry_recommendation_state(date_str: str, qa_state: dict[str, Any], slot_id: str) -> dict[str, Any]:
    retry_decision_candidates = retry_decision_paths(date_str)
    retry_decision_path = retry_decision_candidates[0] if retry_decision_candidates else None
    retry_decision = load_report(retry_decision_path, schema_version=RETRY_DECISION_SCHEMA_VERSION) if retry_decision_path else None
    retry_handoff_candidates = retry_handoff_paths(date_str)
    retry_handoff_path = retry_handoff_candidates[0] if retry_handoff_candidates else None
    retry_handoff = load_report(retry_handoff_path, schema_version=RETRY_HANDOFF_SCHEMA_VERSION) if retry_handoff_path else None
    expected_retry_decision = repo_relative_path(retry_decision_path) if retry_decision_path else str(
        Path("pipeline") / "strategy" / "lena" / "retry_decisions" / date_str / "<retry_decision>_retry_decision.json"
    )
    expected_retry_handoff = repo_relative_path(retry_handoff_path) if retry_handoff_path else str(
        Path("pipeline") / "strategy" / "lena" / "retry_handoffs" / date_str / "<retry_handoff>_retry_handoff.json"
    )
    retry_decision_safe_next_step = (
        "python -m tools.strategy.lena_execute_retry_decision_v1 --correction-artifact <path> --output-root pipeline/strategy/lena/retry_decisions --write-decision"
    )
    retry_handoff_safe_next_step = (
        "python -m tools.strategy.lena_prepare_higgsfield_retry_handoff_v1 --handoff-artifact <path> --execution-receipt <path> --output-root pipeline/strategy/lena/retry_handoffs --write-artifact"
    )
    retry_blocking = qa_state.get("status") == "retry_recommended"

    if retry_decision is not None:
        return {
            "status": "retry_recommended",
            "diagnostic": _diagnostic_entry(
                expected_artifact={
                    "retry_decision": expected_retry_decision,
                    "retry_handoff": expected_retry_handoff,
                },
                artifact_exists=True,
                blocking=retry_blocking,
                diagnostic="retry follow-up artifacts are present or discoverable; this section remains a report-only eligibility surface.",
                safe_next_step=f"{retry_decision_safe_next_step} | {retry_handoff_safe_next_step}",
            ),
            "retry_decision": {
                **_artifact_diagnostic(
                    retry_decision_path,
                    retry_decision,
                    expected_artifact=expected_retry_decision,
                    blocking=retry_blocking,
                    diagnostic="retry decision present; this is a follow-up artifact, not a default blocking prerequisite.",
                    safe_next_step=retry_decision_safe_next_step,
                ),
                "status": retry_decision.get("state", "ready"),
                "summary": {
                    "retry_decision_fingerprint_sha256": retry_decision.get("retry_decision_fingerprint_sha256", ""),
                    "original_slot_id": retry_decision.get("original_slot_id", ""),
                    "retry_slot_id": retry_decision.get("retry_slot_id", ""),
                    "retry_attempt": retry_decision.get("retry_attempt", 0),
                    "retry_cap": retry_decision.get("retry_cap", 0),
                    "retry_prompt_sha256": retry_decision.get("retry_prompt_sha256", ""),
                    "provider_called": retry_decision.get("provider_called", False),
                    "generation_performed": retry_decision.get("generation_performed", False),
                    "side_effects_performed": retry_decision.get("side_effects_performed", []),
                    "exact_next_allowed_action": retry_decision.get("exact_next_allowed_action", ""),
                },
            },
            "retry_handoff": {
                **_artifact_diagnostic(
                    retry_handoff_path,
                    retry_handoff,
                    expected_artifact=expected_retry_handoff,
                    blocking=retry_blocking,
                    diagnostic="retry handoff present or pending as a follow-up artifact, not as a default blocking prerequisite.",
                    safe_next_step=retry_handoff_safe_next_step,
                ),
                "status": "recorded" if retry_handoff else "missing",
                "summary": _summary_from(
                    retry_handoff,
                    [
                        "schema_version",
                        "report_type",
                        "retry_handoff_artifact_path",
                        "retry_handoff_fingerprint_sha256",
                        "retry_slot_id",
                        "original_slot_id",
                        "retry_prompt_sha256",
                    ],
                ),
            },
            "recommendation_only": True,
            "source_qa_disposition_path": qa_state.get("source_artifact_path", ""),
        }

    if qa_state.get("status") == "retry_recommended":
        return {
            "status": "retry_recommended",
            "diagnostic": _diagnostic_entry(
                expected_artifact={
                    "retry_decision": expected_retry_decision,
                    "retry_handoff": expected_retry_handoff,
                },
                artifact_exists=False,
                blocking=True,
                diagnostic="autonomous_eligibility_pending: QA recommends retry follow-up, so the retry surface is informative and reviewable.",
                safe_next_step=f"{retry_decision_safe_next_step} | {retry_handoff_safe_next_step}",
            ),
            "retry_decision": {
                "source_artifact_path": "",
                "source_artifact_present": False,
                "source_report_type": "",
                "source_schema_version": "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_retry_decision,
                    artifact_exists=False,
                    blocking=True,
                    diagnostic="retry is explicitly recommended by QA, so a retry decision becomes an operator-useful follow-up artifact.",
                    safe_next_step=retry_decision_safe_next_step,
                ),
                "status": "missing",
                "summary": {},
            },
            "retry_handoff": {
                "source_artifact_path": repo_relative_path(retry_handoff_path),
                "source_artifact_present": retry_handoff is not None,
                "source_report_type": retry_handoff.get("report_type", "") if retry_handoff else "",
                "source_schema_version": retry_handoff.get("schema_version", "") if retry_handoff else "",
                "diagnostic": _diagnostic_entry(
                    expected_artifact=expected_retry_handoff,
                    artifact_exists=bool(retry_handoff_path and retry_handoff_path.is_file()),
                    blocking=True,
                    diagnostic="retry is explicitly recommended by QA, so a retry handoff reference is helpful even if only as a follow-up artifact.",
                    safe_next_step=retry_handoff_safe_next_step,
                ),
                "status": "recorded" if retry_handoff else "missing",
                "summary": _summary_from(
                    retry_handoff,
                    [
                        "schema_version",
                        "report_type",
                        "retry_handoff_artifact_path",
                        "retry_handoff_fingerprint_sha256",
                        "retry_slot_id",
                        "original_slot_id",
                        "retry_prompt_sha256",
                    ],
                ),
            },
            "recommendation_only": True,
            "source_qa_disposition_path": qa_state.get("source_artifact_path", ""),
        }

    return {
        "status": "not_needed",
        "diagnostic": _diagnostic_entry(
            expected_artifact={
                "retry_decision": expected_retry_decision,
                "retry_handoff": expected_retry_handoff,
            },
            artifact_exists=bool(retry_decision_path and retry_decision_path.is_file()) or bool(retry_handoff_path and retry_handoff_path.is_file()),
            blocking=False,
            diagnostic="retry is not needed for the current package, so this remains an optional follow-up surface.",
            safe_next_step=f"{retry_decision_safe_next_step} | {retry_handoff_safe_next_step}",
        ),
        "retry_decision": {
            "source_artifact_path": repo_relative_path(retry_decision_path),
            "source_artifact_present": retry_decision is not None,
            "source_report_type": retry_decision.get("report_type", "") if retry_decision else "",
            "source_schema_version": retry_decision.get("schema_version", "") if retry_decision else "",
            "diagnostic": _diagnostic_entry(
                expected_artifact=expected_retry_decision,
                artifact_exists=bool(retry_decision_path and retry_decision_path.is_file()),
                blocking=False,
                diagnostic="retry is not needed for the current package, so this remains an optional follow-up surface.",
                safe_next_step=retry_decision_safe_next_step,
            ),
            "status": "recorded" if retry_decision else "missing",
            "summary": _summary_from(
                retry_decision,
                [
                    "retry_decision_fingerprint_sha256",
                    "original_slot_id",
                    "retry_slot_id",
                    "retry_attempt",
                    "retry_cap",
                    "retry_prompt_sha256",
                    "provider_called",
                    "generation_performed",
                    "side_effects_performed",
                    "exact_next_allowed_action",
                ],
            ),
        },
        "retry_handoff": {
            "source_artifact_path": repo_relative_path(retry_handoff_path),
            "source_artifact_present": retry_handoff is not None,
            "source_report_type": retry_handoff.get("report_type", "") if retry_handoff else "",
            "source_schema_version": retry_handoff.get("schema_version", "") if retry_handoff else "",
            "diagnostic": _diagnostic_entry(
                expected_artifact=expected_retry_handoff,
                artifact_exists=bool(retry_handoff_path and retry_handoff_path.is_file()),
                blocking=False,
                diagnostic="retry is not needed for the current package, so the retry handoff remains optional and informational.",
                safe_next_step=retry_handoff_safe_next_step,
            ),
            "status": "recorded" if retry_handoff else "missing",
            "summary": _summary_from(
                retry_handoff,
                [
                    "schema_version",
                    "report_type",
                    "retry_handoff_artifact_path",
                    "retry_handoff_fingerprint_sha256",
                    "retry_slot_id",
                    "original_slot_id",
                    "retry_prompt_sha256",
                ],
            ),
        },
        "recommendation_only": False,
        "source_qa_disposition_path": qa_state.get("source_artifact_path", ""),
    }


def build_autonomy_ladder_state() -> dict[str, Any]:
    contract = autonomy_ladder.load_contract()
    level_3 = autonomy_ladder.get_level(contract, 3)
    level_4 = autonomy_ladder.get_level(contract, 4)
    level_5 = autonomy_ladder.get_level(contract, 5)
    summary = autonomy_ladder.contract_summary(contract)
    return {
        "contract_path": "pipeline/influencer_nodes/lena/autonomy_ladder_v1.json",
        "version": contract.get("version", ""),
        "schema_version": contract.get("schema_version", ""),
        "publish_freeze_active": summary.get("publish_freeze_active", False),
        "level_3_state": level_3.get("status", ""),
        "level_3_disabled_by_publish_freeze": level_3.get("disabled_by_publish_freeze", False),
        "level_3_future_only": level_3.get("future_placeholder", False),
        "level_4_state": level_4.get("status", ""),
        "level_5_state": level_5.get("status", ""),
        "active_levels": summary.get("active_levels", []),
        "auto_approval_forbidden": contract.get("autonomy_rules", {}).get("auto_approval_forbidden", False),
        "implicit_escalation_forbidden": contract.get("autonomy_rules", {}).get("implicit_escalation_forbidden", False),
        "generation_approval_does_not_imply_posting_approval": contract.get("autonomy_rules", {}).get(
            "generation_approval_does_not_imply_posting_approval",
            False,
        ),
    }


def determine_overall_state(
    strategy_plan_state: dict[str, Any],
    candidate_selection_state: dict[str, Any],
    handoff_state: dict[str, Any],
    approval_boundary_state: dict[str, Any],
    qa_disposition_state: dict[str, Any],
    retry_recommendation_state: dict[str, Any],
) -> str:
    if any(section.get("status") == "blocked_missing_input" for section in (strategy_plan_state, candidate_selection_state, handoff_state, qa_disposition_state)):
        return "blocked_missing_input"
    if approval_boundary_state.get("status") == "approval_pending":
        return "approval_pending"
    if qa_disposition_state.get("status") == "qa_blocked":
        return "qa_blocked"
    if retry_recommendation_state.get("status") == "retry_recommended":
        return "retry_recommended"
    return "ready_for_operator_review"


def next_allowed_action_for(state: str) -> dict[str, Any]:
    mapping = {
        "blocked_missing_input": {
            "action": "resolve_missing_upstream_input",
            "reason": "one or more upstream boundary artifacts are missing or invalid",
        },
        "approval_pending": {
            "action": "resolve_machine_eligibility_gate",
            "reason": "the bootstrap eligibility boundary still needs the committed approval artifacts that satisfy existing contracts",
        },
        "qa_blocked": {
            "action": "review_machine_eligibility_results",
            "reason": "QA disposition blocked the current run and needs operator review before another eligibility pass",
        },
        "retry_recommended": {
            "action": "prepare_retry_handoff_reference_only",
            "reason": "QA recommends retry handling, but this package only reports the follow-up eligibility surface",
        },
        "ready_for_operator_review": {
            "action": "await_operator_review_optional",
            "reason": "the package is complete and remains inside the frozen Level 2 boundary while machine eligibility continues to evolve",
        },
    }
    return {"status": state, **mapping.get(state, mapping["blocked_missing_input"])}


def build_level2_daily_generation_package(date_str: str) -> dict[str, Any]:
    strategy_plan_state = build_strategy_plan_state(date_str)
    candidate_selection_state = build_candidate_selection_state(date_str)
    handoff_state, slot_id = build_live_generation_handoff_state(date_str, candidate_selection_state)
    approval_boundary_state = build_approval_boundary_state(date_str, slot_id)
    qa_disposition_state = build_qa_disposition_state(date_str, slot_id)
    retry_recommendation_state = build_retry_recommendation_state(date_str, qa_disposition_state, slot_id)
    overall_state = determine_overall_state(
        strategy_plan_state,
        candidate_selection_state,
        handoff_state,
        approval_boundary_state,
        qa_disposition_state,
        retry_recommendation_state,
    )
    ladder_state = build_autonomy_ladder_state()
    next_action = next_allowed_action_for(overall_state)

    blocking_sections = [
        name
        for name, section in (
            ("strategy_plan_state", strategy_plan_state),
            ("candidate_selection_state", candidate_selection_state),
            ("live_generation_handoff_state", handoff_state),
            ("approval_boundary_state", approval_boundary_state),
            ("qa_disposition_state", qa_disposition_state),
            ("retry_recommendation_state", retry_recommendation_state),
        )
        if section.get("status") in {"blocked_missing_input", "approval_pending", "qa_blocked", "retry_recommended"}
    ]

    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "generated_at": iso_now(),
        "dry_run": True,
        "authority_source": "committed_autonomy_ladder_and_existing_json_reports_only",
        "provider_call_performed": False,
        "publish_performed": False,
        "queue_mutated": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "retry_executed": False,
        "strategy_plan_state": strategy_plan_state,
        "candidate_selection_state": candidate_selection_state,
        "live_generation_handoff_state": handoff_state,
        "approval_boundary_state": approval_boundary_state,
        "qa_disposition_state": qa_disposition_state,
        "retry_recommendation_state": retry_recommendation_state,
        "final_operator_report": {
            "status": overall_state,
            "ready_for_human_review": overall_state == "ready_for_operator_review",
            "blocking_sections": blocking_sections,
            "next_allowed_action": next_action["action"],
            "summary": {
                "strategy_gate_blocked": strategy_plan_state.get("summary", {}).get("strategy_gate_blocked"),
                "recommended_recipe_id": candidate_selection_state.get("summary", {}).get("recommended_recipe_id", ""),
                "selected_slot_id": handoff_state.get("summary", {}).get("selected_slot_id", ""),
                "qa_disposition": qa_disposition_state.get("summary", {}).get("disposition", ""),
                "retry_status": retry_recommendation_state.get("status", ""),
                "publish_freeze_active": ladder_state.get("publish_freeze_active", False),
            },
        },
        "autonomy_ladder_status": ladder_state,
        "next_allowed_action": next_action,
    }


def write_package(report: dict[str, Any], date_str: str) -> Path:
    path = package_path(date_str)
    write_json(path, report)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the report-only Lena Level 2 daily generation package.")
    parser.add_argument("--date", default=utc_date(), help="UTC date for outputs")
    args = parser.parse_args()

    try:
        report = build_level2_daily_generation_package(args.date)
        path = write_package(report, args.date)
    except autonomy_ladder.AutonomyLadderError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "error": exc.detail}, indent=2, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(path),
                "date": args.date,
                "overall_state": report["final_operator_report"]["status"],
                "next_allowed_action": report["next_allowed_action"]["action"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
