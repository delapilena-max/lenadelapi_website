from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.strategy.lena_build_level2_daily_generation_package_v1 as package_builder


DATE = "2026-07-15"
RECIPE_ID = "hcr_011"
SLOT_ID = f"higgsfield-20260715-{RECIPE_ID}-photo"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(package_builder, "ROOT", tmp_path)
    monkeypatch.setattr(package_builder, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(package_builder, "APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")
    monkeypatch.setattr(package_builder, "QA_ROOT", tmp_path / "pipeline" / "asset_review" / "lena")
    monkeypatch.setattr(package_builder, "RETRY_DECISIONS_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "retry_decisions")
    monkeypatch.setattr(package_builder, "RETRY_HANDOFFS_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs")


def _file_snapshot(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def _assert_diag(section: dict, *, expected_suffix: str, exists: bool, blocking: bool, safe_step_contains: str) -> None:
    diag = section["diagnostic"]
    assert diag["expected_artifact"].replace("\\", "/").endswith(expected_suffix)
    assert diag["artifact_exists"] is exists
    assert diag["blocking"] is blocking
    assert isinstance(diag["diagnostic"], str) and diag["diagnostic"]
    assert safe_step_contains in diag["safe_next_step"]


def _strategy_prep_payload() -> dict:
    return {
        "report_type": "lena_strategy_autonomy_prep",
        "version": "v1",
        "date": DATE,
        "summary": {
            "strategy_gate_blocked": True,
            "recommended_recipe_id": RECIPE_ID,
            "queue_recipes": [RECIPE_ID, "hcr_005"],
            "next_live_image_handoff_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
            "broader_autonomous_generation_ready": False,
            "learning_status": "current",
        },
    }


def _next_step_payload() -> dict:
    return {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_status": "current",
        "learning_required_follow_up_action": "no_follow_up_required",
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": RECIPE_ID,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "next_live_gate": "review",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids"],
        },
    }


def _handoff_payload() -> dict:
    return {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "date": DATE,
        "selected_slot_id": SLOT_ID,
        "packet_state": "packet_valid_for_claude_review",
        "dry_run_executor_contract_state": "ready",
        "live_execution_state": "blocked",
        "live_execution_authorized": False,
        "generation_approval_required": True,
        "manual_operator_approval_required": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "publish_authorized": False,
        "manual_publish_review_required": True,
        "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
        "selected_prompt_input_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
    }


def _shadow_eligibility_payload(*, eligibility_status: str = "autonomous_eligibility_passed") -> dict:
    return {
        "report_type": "lena_autonomous_generation_eligibility_shadow",
        "schema_version": "v1",
        "date": DATE,
        "generated_at": "2026-07-15T12:00:00+00:00",
        "eligibility_status": eligibility_status,
        "checks": [
            {
                "check_id": "canonical_brain_manifest_ready",
                "passed": True,
                "blocking": False,
                "reason": "canonical Lena brain manifest is ready",
                "evidence": {
                    "canonical_brain_assets_status": "ready",
                    "missing_required_assets": [],
                    "dirty_workspace_dependency": False,
                },
            }
        ],
        "blocking_reasons": [],
        "source_artifacts": {
            "canonical_brain_assets": {
                "source_artifact_path": "pipeline/influencer_nodes/lena/canonical_brain_assets.py",
                "source_artifact_present": True,
                "source_artifact_sha256": "1" * 64,
                "canonical_brain_assets_status": "ready",
                "missing_required_assets": [],
                "dirty_workspace_dependency": False,
                "assets": [
                    {
                        "asset_id": "prompt_brain",
                        "path": "pipeline/prompting/lena_prompt_brain.py",
                        "exists": True,
                        "required": True,
                        "sha256": "2" * 64,
                        "category": "prompt_brain",
                        "kind": "file",
                    }
                ],
            },
            "strategy_prep": {
                "source_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_strategy_autonomy_prep_{DATE}.json",
                "source_artifact_present": True,
                "source_artifact_sha256": "3" * 64,
            },
            "next_generation_step": {
                "source_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_generation_step_{DATE}.json",
                "source_artifact_present": True,
                "source_artifact_sha256": "4" * 64,
            },
            "live_image_handoff": {
                "source_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
                "source_artifact_present": True,
                "source_artifact_sha256": "5" * 64,
            },
            "autonomy_ladder": {
                "source_artifact_path": "pipeline/influencer_nodes/lena/autonomy_ladder_v1.json",
                "source_artifact_present": True,
                "source_artifact_sha256": "6" * 64,
            },
        },
        "authority_state": {
            "manual_approval_pending": True,
            "manual_approval_scaffold_active": True,
            "autonomous_eligibility_pending": eligibility_status != "autonomous_eligibility_passed",
            "autonomous_eligibility_passed": eligibility_status == "autonomous_eligibility_passed",
            "provider_execution_frozen": True,
            "publish_frozen": True,
            "publish_freeze_active": True,
            "auto_approval_forbidden": True,
            "implicit_escalation_forbidden": True,
            "generation_approval_does_not_imply_posting_approval": True,
            "dirty_workspace_dependency": False,
            "live_execution_authorized": False,
            "generation_approval_required": True,
            "manual_operator_approval_required": True,
            "provider_call_performed": False,
            "generation_performed": False,
            "publish_authorized": False,
            "manual_publish_review_required": True,
        },
        "next_allowed_action": {
            "status": eligibility_status,
            "action": "await_explicit_provider_authorization",
            "reason": "shadow checks passed, but live provider execution remains disabled",
        },
        "dirty_workspace_dependency": False,
        "shadow_mode_only": True,
        "provider_call_performed": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "queue_mutated": False,
        "publish_performed": False,
    }


def _approval_payload() -> dict:
    return {
        "report_type": "lena_higgsfield_generation_approval",
        "schema_version": "v1",
        "approval_type": "higgsfield_single_generation",
        "operator_id": "nicolas",
        "approved_at_utc": "2026-07-15T12:00:00+00:00",
        "expires_at_utc": "2026-07-15T12:30:00+00:00",
        "date": DATE,
        "slot_id": SLOT_ID,
        "prompt_sha256": "a" * 64,
        "confirmation_statement": "I approve one live Higgsfield generation attempt for slot higgsfield-20260715-hcr_011-photo and understand that credits may be spent.",
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }


def _claim_payload() -> dict:
    return {
        "report_type": "lena_higgsfield_generation_claim",
        "schema_version": "v1",
        "claim_type": "higgsfield_single_generation_consumption_claim",
        "operator_id": "nicolas",
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }


def _receipt_payload() -> dict:
    return {
        "report_type": "lena_higgsfield_generation_execution_receipt",
        "schema_version": "v1",
        "receipt_type": "higgsfield_single_generation_execution_receipt",
        "operator_id": "nicolas",
        "outcome": "success",
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
        "output_path": "pipeline/higgsfield_library/lena/2026-07-15/example.png",
    }


def _qa_payload(*, disposition: str = "approved", retry_eligible: bool = False) -> dict:
    return {
        "schema_version": "lena_photo_qa_disposition_v1",
        "date": DATE,
        "slot_id": SLOT_ID,
        "disposition": disposition,
        "retry_eligible": retry_eligible,
        "confidence": "high" if disposition != "hard_stop" else "blocked",
        "hard_stop_reason": "" if disposition != "hard_stop" else "unsafe_presentation",
        "exact_next_allowed_action": "await_human_review_within_level_2_contract",
        "qa_inputs": {"decision_kind": "selected_candidate"},
        "provider_called": False,
        "side_effects_performed": [],
    }


def _retry_decision_payload() -> dict:
    return {
        "schema_version": "lena_retry_decision_v1",
        "state": "ready_for_retry_live_authorization",
        "influencer_id": "lena",
        "retry_decision_fingerprint_sha256": "b" * 64,
        "original_slot_id": SLOT_ID,
        "retry_slot_id": "higgsfield-20260715-hcr_011-retry01-photo",
        "retry_attempt": 1,
        "retry_cap": 1,
        "lane": "face_skin_win",
        "recipe_id": RECIPE_ID,
        "hook_id": "cbn_004",
        "original_prompt_sha256": "c" * 64,
        "retry_prompt_sha256": "d" * 64,
        "provider_called": False,
        "generation_performed": False,
        "side_effects_performed": [],
        "exact_next_allowed_action": "separate_explicit_nicolas_authorization_required",
    }


def _build_fixture_tree(
    tmp_path: Path,
    *,
    include_strategy_prep: bool = True,
    include_next_step: bool = True,
    include_handoff: bool = True,
    include_shadow_eligibility: bool = True,
    include_approval: bool = True,
    include_claim: bool = True,
    include_receipt: bool = True,
    include_qa: bool = True,
    qa_disposition: str = "approved",
    qa_retry_eligible: bool = False,
    include_retry_decision: bool = False,
    include_retry_handoff: bool = False,
) -> None:
    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    approvals = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE
    qa_root = tmp_path / "pipeline" / "asset_review" / "lena" / DATE
    retry_decisions = tmp_path / "pipeline" / "strategy" / "lena" / "retry_decisions" / DATE
    retry_handoffs = tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs" / DATE

    if include_strategy_prep:
        _write_json(next_actions / f"lena_strategy_autonomy_prep_{DATE}.json", _strategy_prep_payload())
    if include_next_step:
        _write_json(next_actions / f"lena_next_generation_step_{DATE}.json", _next_step_payload())
    if include_handoff:
        _write_json(next_actions / f"lena_next_live_image_handoff_{DATE}.json", _handoff_payload())
    if include_shadow_eligibility:
        _write_json(
            next_actions / f"lena_autonomous_generation_eligibility_shadow_{DATE}.json",
            _shadow_eligibility_payload(),
        )
    if include_approval:
        _write_json(approvals / f"{SLOT_ID}_higgsfield_generation_approval.json", _approval_payload())
    if include_claim:
        _write_json(approvals / f"{SLOT_ID}_higgsfield_generation_claim.json", _claim_payload())
    if include_receipt:
        _write_json(approvals / f"{SLOT_ID}_higgsfield_generation_execution_receipt.json", _receipt_payload())
    if include_qa:
        _write_json(qa_root / f"{SLOT_ID}__aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899_qa_disposition.json", _qa_payload(disposition=qa_disposition, retry_eligible=qa_retry_eligible))
    if include_retry_decision:
        _write_json(retry_decisions / "higgsfield-20260715-hcr_011-retry01-photo__123456789abc_retry_decision.json", _retry_decision_payload())
    if include_retry_handoff:
        _write_json(retry_handoffs / "higgsfield-20260715-hcr_011-retry01-photo__abcdef123456_retry_handoff.json", {
            "schema_version": "lena_higgsfield_retry_handoff_v1",
            "report_type": "lena_higgsfield_retry_handoff",
            "date": DATE,
            "retry_slot_id": "higgsfield-20260715-hcr_011-retry01-photo",
            "original_slot_id": SLOT_ID,
            "retry_prompt_sha256": "d" * 64,
            "retry_handoff_artifact_path": f"pipeline/strategy/lena/retry_handoffs/{DATE}/higgsfield-20260715-hcr_011-retry01-photo__abcdef123456_retry_handoff.json",
            "retry_handoff_fingerprint_sha256": "e" * 64,
        })


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(package_builder, "ROOT", tmp_path)
    monkeypatch.setattr(package_builder, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(package_builder, "APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")
    monkeypatch.setattr(package_builder, "QA_ROOT", tmp_path / "pipeline" / "asset_review" / "lena")
    monkeypatch.setattr(package_builder, "RETRY_DECISIONS_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "retry_decisions")
    monkeypatch.setattr(package_builder, "RETRY_HANDOFFS_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs")


def test_build_package_writes_durable_json_with_all_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)
    before = _file_snapshot(tmp_path)

    report = package_builder.build_level2_daily_generation_package(DATE)
    output_path = package_builder.write_package(report, DATE)
    after = _file_snapshot(tmp_path)

    assert output_path == package_builder.package_path(DATE)
    assert output_path.is_file()
    assert json.loads(output_path.read_text(encoding="utf-8")) == report
    assert report["report_type"] == "lena_level2_daily_generation_package"
    assert report["schema_version"] == "v1"
    assert report["strategy_plan_state"]["status"] == "ready"
    assert report["candidate_selection_state"]["status"] == "ready"
    assert report["live_generation_handoff_state"]["status"] == "ready"
    assert report["autonomous_eligibility_shadow_state"]["status"] == "autonomous_eligibility_shadow_ready"
    assert report["autonomous_eligibility_shadow_state"]["summary"]["eligibility_status"] == "autonomous_eligibility_passed"
    assert report["autonomous_eligibility_shadow_state"]["summary"]["authority_state"]["provider_execution_frozen"] is True
    assert report["autonomous_eligibility_shadow_state"]["summary"]["authority_state"]["provider_call_performed"] is False
    assert report["autonomous_eligibility_shadow_state"]["summary"]["next_allowed_action"]["action"] == "await_explicit_provider_authorization"
    assert report["autonomous_eligibility_shadow_state"]["summary"]["source_artifacts"]["canonical_brain_assets"]["source_artifact_present"] is True
    assert report["approval_boundary_state"]["status"] == "approved"
    assert report["qa_disposition_state"]["status"] == "ready"
    assert report["retry_recommendation_state"]["status"] == "not_needed"
    assert report["autonomy_ladder_status"]["publish_freeze_active"] is False
    assert report["autonomy_ladder_status"]["level_3_state"] == "active"
    assert report["autonomy_ladder_status"]["level_3_disabled_by_publish_freeze"] is False
    assert report["autonomy_ladder_status"]["level_4_state"] == "future_only"
    assert report["autonomy_ladder_status"]["level_5_state"] == "future_only"
    assert report["final_operator_report"]["status"] == "ready_for_operator_review"
    assert report["next_allowed_action"]["action"] == "await_human_review_within_level_2_contract"
    assert "autonomous_eligibility_shadow_state" not in report["final_operator_report"]["blocking_sections"]
    assert after - before == {Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_level2_daily_generation_package_{DATE}.json"}

    serialized = json.dumps(report, sort_keys=True)
    assert "C:\\projects\\ai\\content_bot" not in serialized
    assert "content_bot_pr_clean" not in serialized
    assert not hasattr(package_builder, "subprocess")
    assert not hasattr(package_builder, "run_step")
    assert "subprocess" not in package_builder.__dict__
    assert "run_step" not in package_builder.__dict__

    _assert_diag(
        report["strategy_plan_state"],
        expected_suffix=f"pipeline/strategy/lena/next_actions/{DATE}/lena_strategy_autonomy_prep_{DATE}.json",
        exists=True,
        blocking=False,
        safe_step_contains="lena_run_strategy_autonomy_prep_v1",
    )
    _assert_diag(
        report["candidate_selection_state"],
        expected_suffix=f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_generation_step_{DATE}.json",
        exists=True,
        blocking=False,
        safe_step_contains="lena_recommend_next_generation_step_v1",
    )
    _assert_diag(
        report["live_generation_handoff_state"],
        expected_suffix=f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
        exists=True,
        blocking=False,
        safe_step_contains="lena_build_next_live_image_handoff_v1",
    )
    assert report["approval_boundary_state"]["diagnostic"]["blocking"] is False
    assert "library entrypoints" in report["approval_boundary_state"]["diagnostic"]["safe_next_step"]
    assert report["approval_boundary_state"]["generation_approval"]["diagnostic"]["artifact_exists"] is True
    assert report["approval_boundary_state"]["claim"]["diagnostic"]["artifact_exists"] is True
    assert report["approval_boundary_state"]["receipt"]["diagnostic"]["artifact_exists"] is True
    _assert_diag(
        report["qa_disposition_state"],
        expected_suffix=f"pipeline/asset_review/lena/{DATE}/{SLOT_ID}__aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899_qa_disposition.json",
        exists=True,
        blocking=False,
        safe_step_contains="--decision-artifact",
    )
    assert report["retry_recommendation_state"]["diagnostic"]["blocking"] is False


def test_missing_upstream_input_produces_blocked_missing_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, include_next_step=False)

    report = package_builder.build_level2_daily_generation_package(DATE)

    assert report["candidate_selection_state"]["status"] == "blocked_missing_input"
    assert report["final_operator_report"]["status"] == "blocked_missing_input"
    assert report["next_allowed_action"]["action"] == "resolve_missing_upstream_input"
    assert report["candidate_selection_state"]["diagnostic"]["artifact_exists"] is False
    assert report["candidate_selection_state"]["diagnostic"]["blocking"] is True
    assert "lena_recommend_next_generation_step_v1" in report["candidate_selection_state"]["diagnostic"]["safe_next_step"]
    assert report["live_generation_handoff_state"]["diagnostic"]["artifact_exists"] is True
    assert report["strategy_plan_state"]["diagnostic"]["artifact_exists"] is True


def test_missing_shadow_eligibility_is_non_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, include_shadow_eligibility=False)

    report = package_builder.build_level2_daily_generation_package(DATE)

    assert report["autonomous_eligibility_shadow_state"]["status"] == "autonomous_eligibility_shadow_missing"
    assert report["autonomous_eligibility_shadow_state"]["diagnostic"]["artifact_exists"] is False
    assert report["autonomous_eligibility_shadow_state"]["diagnostic"]["blocking"] is False
    assert report["final_operator_report"]["status"] == "ready_for_operator_review"
    assert report["next_allowed_action"]["action"] == "await_human_review_within_level_2_contract"
    assert "autonomous_eligibility_shadow_state" not in report["final_operator_report"]["blocking_sections"]


def test_missing_approval_produces_approval_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, include_approval=False)

    report = package_builder.build_level2_daily_generation_package(DATE)

    assert report["approval_boundary_state"]["status"] == "approval_pending"
    assert report["approval_boundary_state"]["generation_approval"]["status"] == "missing"
    assert report["final_operator_report"]["status"] == "approval_pending"
    assert report["next_allowed_action"]["action"] == "obtain_explicit_generation_approval"
    assert report["approval_boundary_state"]["diagnostic"]["blocking"] is True
    assert report["approval_boundary_state"]["generation_approval"]["diagnostic"]["artifact_exists"] is False
    assert report["approval_boundary_state"]["claim"]["diagnostic"]["artifact_exists"] is True
    assert report["approval_boundary_state"]["receipt"]["diagnostic"]["artifact_exists"] is True
    assert "library entrypoints" in report["approval_boundary_state"]["diagnostic"]["safe_next_step"]


def test_qa_failure_produces_qa_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, qa_disposition="hard_stop", qa_retry_eligible=False)

    report = package_builder.build_level2_daily_generation_package(DATE)

    assert report["qa_disposition_state"]["status"] == "qa_blocked"
    assert report["final_operator_report"]["status"] == "qa_blocked"
    assert report["next_allowed_action"]["action"] == "review_qa_and_prepare_retry_recommendation_only"
    assert report["qa_disposition_state"]["diagnostic"]["artifact_exists"] is True
    assert report["qa_disposition_state"]["diagnostic"]["blocking"] is True
    assert "--expected-image-sha256" in report["qa_disposition_state"]["diagnostic"]["safe_next_step"]


def test_retry_needed_reports_recommendation_only_and_does_not_execute_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, qa_disposition="retryable_failure", qa_retry_eligible=True)

    report = package_builder.build_level2_daily_generation_package(DATE)

    assert report["qa_disposition_state"]["status"] == "retry_recommended"
    assert report["retry_recommendation_state"]["status"] == "retry_recommended"
    assert report["retry_recommendation_state"]["recommendation_only"] is True
    assert report["retry_recommendation_state"]["retry_decision"]["status"] == "missing"
    assert report["final_operator_report"]["status"] == "retry_recommended"
    assert report["next_allowed_action"]["action"] == "prepare_retry_handoff_reference_only"
    assert report["retry_recommendation_state"]["retry_decision"]["diagnostic"]["blocking"] is True
    assert report["retry_recommendation_state"]["retry_handoff"]["diagnostic"]["blocking"] is True
    assert "lena_execute_retry_decision_v1" in report["retry_recommendation_state"]["retry_decision"]["diagnostic"]["safe_next_step"]
    assert "lena_prepare_higgsfield_retry_handoff_v1" in report["retry_recommendation_state"]["retry_handoff"]["diagnostic"]["safe_next_step"]
    assert not (tmp_path / "pipeline" / "strategy" / "lena" / "retry_decisions" / DATE).exists()
