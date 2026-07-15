from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.influencer_nodes.lena import autonomy_ladder
from pipeline.influencer_nodes.lena import canonical_brain_assets


ROOT = Path(__file__).resolve().parents[2]
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"

REPORT_TYPE = "lena_autonomous_generation_eligibility_shadow"
SCHEMA_VERSION = "v1"
STRATEGY_PREP_REPORT_TYPE = "lena_strategy_autonomy_prep"
NEXT_STEP_REPORT_TYPE = "lena_next_generation_step"
HANDOFF_REPORT_TYPE = "lena_next_live_image_handoff"

SUCCESS_STATUS = "autonomous_eligibility_passed"
PENDING_STATUS = "autonomous_eligibility_pending"
MISSING_INPUT_CODE = "missing_required_input"
INVALID_INPUT_CODE = "invalid_required_input"


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def repo_relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def dated_path(base: Path, date_str: str, filename: str) -> Path:
    return base / date_str / filename


def report_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_autonomous_generation_eligibility_shadow_{date_str}.json")


def strategy_prep_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_strategy_autonomy_prep_{date_str}.json")


def next_step_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_generation_step_{date_str}.json")


def handoff_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_live_image_handoff_{date_str}.json")


def _load_report(path: Path, *, report_type: str | None = None, schema_version: str | None = None) -> dict[str, Any] | None:
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


def _source_artifact_record(path: Path, report: dict[str, Any] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_artifact_path": repo_relative_path(path),
        "source_artifact_present": path.is_file(),
        "source_artifact_sha256": sha256_file(path) if path.is_file() else None,
    }
    if isinstance(report, dict):
        record["source_report_type"] = report.get("report_type", "")
        record["source_schema_version"] = report.get("schema_version", "")
    return record


def _check(
    check_id: str,
    passed: bool,
    *,
    blocking: bool,
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": passed,
        "blocking": blocking,
        "reason": reason,
        "evidence": evidence or {},
    }


def _canonical_manifest_record() -> dict[str, Any]:
    manifest = canonical_brain_assets.load_canonical_brain_assets()
    module_path = Path(canonical_brain_assets.__file__).resolve()
    return {
        "source_artifact_path": repo_relative_path(module_path),
        "source_artifact_present": module_path.is_file(),
        "source_artifact_sha256": sha256_file(module_path) if module_path.is_file() else None,
        "canonical_brain_assets_status": manifest.get("canonical_brain_assets_status", ""),
        "missing_required_assets": manifest.get("missing_required_assets", []),
        "dirty_workspace_dependency": manifest.get("dirty_workspace_dependency", None),
        "assets": manifest.get("assets", []),
    }


def _validate_strategy_prep(date_str: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = strategy_prep_path(date_str)
    report = _load_report(path, report_type=STRATEGY_PREP_REPORT_TYPE)
    return _source_artifact_record(path, report), report or {}


def _validate_next_step(date_str: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = next_step_path(date_str)
    report = _load_report(path, report_type=NEXT_STEP_REPORT_TYPE)
    return _source_artifact_record(path, report), report or {}


def _validate_handoff(date_str: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = handoff_path(date_str)
    report = _load_report(path, report_type=HANDOFF_REPORT_TYPE)
    return _source_artifact_record(path, report), report or {}


def _strategy_prep_consistent(report: dict[str, Any]) -> tuple[bool, str]:
    if not report:
        return False, "strategy prep artifact is missing or invalid"
    if report.get("dry_run") is not True:
        return False, "strategy prep must remain a dry run"
    if report.get("provider_call_enabled") is not False:
        return False, "strategy prep must not enable provider calls"
    if report.get("generation_call_performed") is not False:
        return False, "strategy prep must not perform generation"
    if report.get("api_call_made") is not False:
        return False, "strategy prep must not make API calls"
    safe_ops = report.get("safe_operations", {})
    if not isinstance(safe_ops, dict):
        return False, "strategy prep safe_operations must be a JSON object"
    for key in ("api_call_made", "generation_call_performed", "upload_performed", "queue_mutated", "publish_performed", "credentials_read"):
        if safe_ops.get(key) is not False:
            return False, f"strategy prep safe operation flag {key} must remain false"
    if report.get("status") == "failed":
        return False, "strategy prep reported a failed status"
    steps = report.get("steps", [])
    if not isinstance(steps, list):
        return False, "strategy prep steps must be a list"
    if any(isinstance(step, dict) and step.get("ok") is False for step in steps):
        return False, "strategy prep contains a failed sub-step"
    return True, "strategy prep is dry-run only and internally consistent"


def _next_step_consistent(prep: dict[str, Any], report: dict[str, Any]) -> tuple[bool, str]:
    if not report:
        return False, "next-generation step artifact is missing or invalid"
    recommendation = report.get("recommendation", {})
    if not isinstance(recommendation, dict):
        return False, "next-generation step recommendation must be a JSON object"
    if prep:
        prep_summary = prep.get("summary", {})
        if not isinstance(prep_summary, dict):
            return False, "strategy prep summary must be a JSON object"
        prep_recipe = str(prep_summary.get("recommended_recipe_id", "")).strip()
        report_recipe = str(recommendation.get("recommended_recipe_id", "")).strip()
        if prep_recipe and report_recipe and prep_recipe != report_recipe:
            return False, "next-generation step recipe does not match strategy prep"
        prep_handoff_path = str(prep_summary.get("next_live_image_handoff_path", "")).strip()
        if prep_handoff_path:
            expected_suffix = f"pipeline/strategy/lena/next_actions/{report.get('date', '')}/lena_next_live_image_handoff_{report.get('date', '')}.json"
            normalized_prep_handoff_path = prep_handoff_path.replace("\\", "/")
            if not normalized_prep_handoff_path.endswith(expected_suffix):
                return False, "strategy prep handoff path does not match the current date"
    learning_status = str(report.get("learning_status", "")).strip()
    if learning_status not in {"current", "usable_but_incomplete", "stale_unresolved", "manual_or_future_capability_required", "unavailable"}:
        return False, "next-generation step learning_status is not recognized"
    follow_up = str(report.get("learning_required_follow_up_action", "")).strip()
    if not follow_up:
        return False, "next-generation step missing learning follow-up"
    if not str(recommendation.get("recommended_recipe_id", "")).strip():
        return False, "next-generation step missing recommended recipe"
    return True, "next-generation step matches the strategy recommendation"


def _handoff_consistent(next_step: dict[str, Any], report: dict[str, Any]) -> tuple[bool, str]:
    if not report:
        return False, "live image handoff artifact is missing or invalid"
    if report.get("live_execution_state") != "blocked":
        return False, "live image handoff must remain blocked"
    if report.get("live_execution_authorized") is not False:
        return False, "live image handoff must not authorize execution"
    if report.get("generation_approval_required") is not True:
        return False, "live image handoff must require generation approval"
    if report.get("manual_operator_approval_required") is not True:
        return False, "live image handoff must keep manual approval required"
    if report.get("provider_call_performed") is not False:
        return False, "live image handoff must not claim a provider call"
    if report.get("generation_performed") is not False:
        return False, "live image handoff must not claim generation"
    if report.get("publish_authorized") is not False:
        return False, "live image handoff must not authorize publishing"
    if report.get("manual_publish_review_required") is not True:
        return False, "live image handoff must keep manual publish review required"
    structured = report.get("structured_executor_inputs", {})
    if not isinstance(structured, dict):
        return False, "live image handoff structured_executor_inputs must be a JSON object"
    if structured.get("live_execution_authorized") is not False:
        return False, "structured executor inputs must keep live execution disabled"
    if structured.get("generation_approval_required") is not True:
        return False, "structured executor inputs must require generation approval"
    if structured.get("manual_operator_approval_required") is not True:
        return False, "structured executor inputs must require manual approval"
    if structured.get("provider_call_performed") is not False:
        return False, "structured executor inputs must keep provider calls disabled"
    if structured.get("generation_performed") is not False:
        return False, "structured executor inputs must keep generation disabled"
    if structured.get("publish_authorized") is not False:
        return False, "structured executor inputs must keep publish disabled"
    if structured.get("manual_publish_review_required") is not True:
        return False, "structured executor inputs must keep manual publish review required"
    if next_step:
        recommendation = next_step.get("recommendation", {})
        if isinstance(recommendation, dict):
            expected_recipe = str(recommendation.get("recommended_recipe_id", "")).strip()
            selected_recipe = str(report.get("selected_recipe_id", "")).strip()
            if expected_recipe and selected_recipe and expected_recipe != selected_recipe:
                return False, "live image handoff recipe does not match the next-generation step"
    return True, "live image handoff remains review-only and not executable"


def _authority_state(
    *,
    manifest: dict[str, Any],
    ladder_contract: dict[str, Any],
    ladder_summary: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    autonomy_rules = ladder_contract.get("autonomy_rules", {})
    return {
        "manual_approval_pending": bool(handoff.get("manual_operator_approval_required", False)),
        "manual_approval_scaffold_active": bool(handoff.get("generation_approval_required", False)),
        "autonomous_eligibility_pending": False,
        "autonomous_eligibility_passed": False,
        "provider_execution_frozen": True,
        "publish_frozen": bool(ladder_summary.get("publish_freeze_active", False)),
        "publish_freeze_active": bool(ladder_summary.get("publish_freeze_active", False)),
        "auto_approval_forbidden": bool(autonomy_rules.get("auto_approval_forbidden", False)),
        "implicit_escalation_forbidden": bool(autonomy_rules.get("implicit_escalation_forbidden", False)),
        "generation_approval_does_not_imply_posting_approval": bool(
            autonomy_rules.get("generation_approval_does_not_imply_posting_approval", False)
        ),
        "dirty_workspace_dependency": bool(manifest.get("dirty_workspace_dependency", False)),
        "live_execution_authorized": bool(handoff.get("live_execution_authorized", False)),
        "generation_approval_required": bool(handoff.get("generation_approval_required", False)),
        "manual_operator_approval_required": bool(handoff.get("manual_operator_approval_required", False)),
        "provider_call_performed": bool(handoff.get("provider_call_performed", False)),
        "generation_performed": bool(handoff.get("generation_performed", False)),
        "publish_authorized": bool(handoff.get("publish_authorized", False)),
        "manual_publish_review_required": bool(handoff.get("manual_publish_review_required", False)),
    }


def _next_allowed_action(eligibility_status: str, *, authority_state: dict[str, Any], blocking_reasons: list[str]) -> dict[str, Any]:
    if eligibility_status != SUCCESS_STATUS:
        if any(reason.startswith("canonical_brain_manifest") for reason in blocking_reasons):
            return {
                "status": eligibility_status,
                "action": "rebuild_missing_canonical_artifact",
                "reason": "the canonical Lena brain manifest is incomplete",
            }
        return {
            "status": eligibility_status,
            "action": "resolve_missing_eligibility_inputs",
            "reason": "one or more shadow eligibility inputs are missing or invalid",
        }
    if authority_state.get("provider_execution_frozen", False):
        return {
            "status": eligibility_status,
            "action": "await_explicit_provider_authorization",
            "reason": "shadow checks passed, but live provider execution remains disabled",
        }
    if authority_state.get("publish_frozen", False):
        return {
            "status": eligibility_status,
            "action": "do_not_publish",
            "reason": "publish freeze remains active",
        }
    return {
        "status": eligibility_status,
        "action": "maintain_shadow_mode_only",
        "reason": "all current shadow checks passed and the report remains read-only",
    }


def build_autonomous_generation_eligibility_shadow(date_str: str) -> dict[str, Any]:
    manifest = canonical_brain_assets.load_canonical_brain_assets()
    ladder_contract = autonomy_ladder.load_contract()
    ladder = autonomy_ladder.contract_summary(ladder_contract)

    strategy_prep_artifact, strategy_prep = _validate_strategy_prep(date_str)
    next_step_artifact, next_step = _validate_next_step(date_str)
    handoff_artifact, handoff = _validate_handoff(date_str)
    canonical_manifest = _canonical_manifest_record()

    checks: list[dict[str, Any]] = []

    manifest_ready = (
        manifest.get("canonical_brain_assets_status") == "ready"
        and not manifest.get("missing_required_assets")
    )
    checks.append(
        _check(
            "canonical_brain_manifest_ready",
            manifest_ready,
            blocking=not manifest_ready,
            reason=(
                "canonical Lena brain manifest is ready"
                if manifest_ready
                else "canonical Lena brain manifest is missing required assets"
            ),
            evidence={
                "canonical_brain_assets_status": manifest.get("canonical_brain_assets_status", ""),
                "missing_required_assets": manifest.get("missing_required_assets", []),
                "dirty_workspace_dependency": manifest.get("dirty_workspace_dependency", None),
            },
        )
    )

    dirty_dependency_clear = manifest.get("dirty_workspace_dependency") is False
    checks.append(
        _check(
            "canonical_brain_manifest_dirty_workspace_dependency_false",
            dirty_dependency_clear,
            blocking=not dirty_dependency_clear,
            reason=(
                "canonical Lena brain manifest does not depend on the dirty evidence workspace"
                if dirty_dependency_clear
                else "canonical Lena brain manifest reports a dirty-workspace dependency"
            ),
            evidence={
                "dirty_workspace_dependency": manifest.get("dirty_workspace_dependency", None),
            },
        )
    )

    strategy_ok, strategy_reason = _strategy_prep_consistent(strategy_prep)
    checks.append(
        _check(
            "strategy_prep_consistent",
            strategy_ok,
            blocking=not strategy_ok,
            reason=strategy_reason,
            evidence=strategy_prep,
        )
    )

    next_step_ok, next_step_reason = _next_step_consistent(strategy_prep, next_step)
    checks.append(
        _check(
            "next_generation_step_consistent",
            next_step_ok,
            blocking=not next_step_ok,
            reason=next_step_reason,
            evidence=next_step,
        )
    )

    handoff_ok, handoff_reason = _handoff_consistent(next_step, handoff)
    checks.append(
        _check(
            "live_image_handoff_review_only",
            handoff_ok,
            blocking=not handoff_ok,
            reason=handoff_reason,
            evidence=handoff,
        )
    )

    autonomy_rules = ladder_contract.get("autonomy_rules", {})
    ladder_ok = bool(
        ladder.get("publish_freeze_active", False)
        and autonomy_rules.get("auto_approval_forbidden", False)
        and autonomy_rules.get("implicit_escalation_forbidden", False)
        and autonomy_rules.get("generation_approval_does_not_imply_posting_approval", False)
    )
    checks.append(
        _check(
            "autonomy_ladder_publish_frozen",
            ladder_ok,
            blocking=not ladder_ok,
            reason=(
                "autonomy ladder keeps publish frozen and forbids auto-approval"
                if ladder_ok
                else "autonomy ladder no longer enforces the required frozen state"
            ),
            evidence=ladder,
        )
    )

    authority_state = _authority_state(
        manifest=manifest,
        ladder_contract=ladder_contract,
        ladder_summary=ladder,
        handoff=handoff,
    )
    blocking_reasons = [check["check_id"] for check in checks if check["blocking"] and not check["passed"]]

    eligibility_status = SUCCESS_STATUS if not blocking_reasons else PENDING_STATUS
    authority_state["autonomous_eligibility_pending"] = eligibility_status == PENDING_STATUS
    authority_state["autonomous_eligibility_passed"] = eligibility_status == SUCCESS_STATUS

    next_action = _next_allowed_action(
        eligibility_status,
        authority_state=authority_state,
        blocking_reasons=blocking_reasons,
    )

    source_artifacts = {
        "canonical_brain_assets": canonical_manifest,
        "strategy_prep": {
            **strategy_prep_artifact,
            "summary": strategy_prep.get("summary", {}),
        },
        "next_generation_step": {
            **next_step_artifact,
            "summary": next_step.get("recommendation", {}),
            "learning_status": next_step.get("learning_status", ""),
            "learning_required_follow_up_action": next_step.get("learning_required_follow_up_action", ""),
        },
        "live_image_handoff": {
            **handoff_artifact,
            "selected_slot_id": handoff.get("selected_slot_id", ""),
            "selected_recipe_id": handoff.get("selected_recipe_id", ""),
            "live_execution_state": handoff.get("live_execution_state", ""),
            "live_execution_authorized": handoff.get("live_execution_authorized", False),
            "generation_approval_required": handoff.get("generation_approval_required", False),
            "manual_operator_approval_required": handoff.get("manual_operator_approval_required", False),
            "provider_call_performed": handoff.get("provider_call_performed", False),
            "generation_performed": handoff.get("generation_performed", False),
            "publish_authorized": handoff.get("publish_authorized", False),
            "manual_publish_review_required": handoff.get("manual_publish_review_required", False),
        },
        "autonomy_ladder": {
            "source_artifact_path": repo_relative_path(autonomy_ladder.CONTRACT_PATH),
            "source_artifact_present": autonomy_ladder.CONTRACT_PATH.is_file(),
            "source_artifact_sha256": sha256_file(autonomy_ladder.CONTRACT_PATH)
            if autonomy_ladder.CONTRACT_PATH.is_file()
            else None,
            "contract_summary": ladder,
            "autonomy_rules": ladder_contract.get("autonomy_rules", {}),
        },
    }

    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "generated_at": iso_now(),
        "eligibility_status": eligibility_status,
        "checks": checks,
        "blocking_reasons": blocking_reasons,
        "source_artifacts": source_artifacts,
        "authority_state": authority_state,
        "next_allowed_action": next_action,
        "dirty_workspace_dependency": False,
        "shadow_mode_only": True,
        "provider_call_performed": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "queue_mutated": False,
        "publish_performed": False,
    }


def write_report(report: dict[str, Any], date_str: str) -> Path:
    path = report_path(date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the read-only Lena autonomous generation eligibility shadow report."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for outputs")
    args = parser.parse_args()

    report = build_autonomous_generation_eligibility_shadow(args.date)
    path = write_report(report, args.date)
    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(path),
                "date": args.date,
                "eligibility_status": report["eligibility_status"],
                "next_allowed_action": report["next_allowed_action"]["action"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
