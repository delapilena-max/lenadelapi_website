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
    if report is None:
        return {
            **_section_base(path, None),
            "status": "blocked_missing_input",
            "summary": {},
        }

    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        **_section_base(path, report),
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
    if report is None:
        return {
            **_section_base(path, None),
            "status": "blocked_missing_input",
            "summary": {},
        }

    recommendation = report.get("recommendation", {})
    if not isinstance(recommendation, dict):
        recommendation = {}
    return {
        **_section_base(path, report),
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
    slot_id = _candidate_slot_id(date_str, candidate_selection, report)
    if report is None:
        return (
            {
                **_section_base(path, None),
                "status": "blocked_missing_input",
                "summary": {
                    "selected_slot_id": slot_id,
                },
            },
            slot_id,
        )

    return (
        {
            **_section_base(path, report),
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
    if not slot_id:
        return {
            "status": "approval_pending",
            "generation_approval": {
                "source_artifact_path": "",
                "source_artifact_present": False,
            },
            "claim": {"source_artifact_path": "", "source_artifact_present": False, "status": "missing"},
            "receipt": {"source_artifact_path": "", "source_artifact_present": False, "status": "missing"},
        }

    candidates = approval_paths(date_str, slot_id)
    approval_path = candidates[0] if candidates else None
    approval = load_report(approval_path, report_type="lena_higgsfield_generation_approval") if approval_path else None
    if approval is None:
        return {
            "status": "approval_pending",
            "generation_approval": {
                **_section_base(approval_path, None),
                "status": "missing",
                "summary": {},
            },
            "claim": {
                "source_artifact_path": repo_relative_path(claim_path(date_str, slot_id)),
                "source_artifact_present": False,
                "status": "missing",
            },
            "receipt": {
                "source_artifact_path": repo_relative_path(receipt_path(date_str, slot_id)),
                "source_artifact_present": False,
                "status": "missing",
            },
        }

    claim = load_report(claim_path(date_str, slot_id), report_type="lena_higgsfield_generation_claim")
    receipt = load_report(receipt_path(date_str, slot_id), report_type="lena_higgsfield_generation_execution_receipt")
    return {
        "status": "approved",
        "generation_approval": {
            **_section_base(approval_path, approval),
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
            **_section_base(claim_path(date_str, slot_id), claim),
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
            **_section_base(receipt_path(date_str, slot_id), receipt),
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
    if qa_report is None:
        return {
            **_section_base(qa_path, None),
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
        **_section_base(qa_path, qa_report),
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

    if retry_decision is not None:
        return {
            "status": "retry_recommended",
            "retry_decision": {
                **_section_base(retry_decision_path, retry_decision),
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
                **_section_base(retry_handoff_path, retry_handoff),
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
            "retry_decision": {
                "source_artifact_path": "",
                "source_artifact_present": False,
                "status": "missing",
                "summary": {},
            },
            "retry_handoff": {
                "source_artifact_path": repo_relative_path(retry_handoff_path),
                "source_artifact_present": retry_handoff is not None,
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
        "retry_decision": {
            "source_artifact_path": repo_relative_path(retry_decision_path),
            "source_artifact_present": retry_decision is not None,
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
            "action": "obtain_explicit_generation_approval",
            "reason": "the Level 2 handoff is ready but explicit human approval is still absent",
        },
        "qa_blocked": {
            "action": "review_qa_and_prepare_retry_recommendation_only",
            "reason": "QA disposition blocked the current run",
        },
        "retry_recommended": {
            "action": "prepare_retry_handoff_reference_only",
            "reason": "QA recommends retry handling, but this package does not execute retries",
        },
        "ready_for_operator_review": {
            "action": "await_human_review_within_level_2_contract",
            "reason": "the package is complete and remains inside the frozen Level 2 boundary",
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
