from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.identity import lena_higgsfield_identity as identity
from pipeline.presence import human_presence_candidate_ranking_v1 as presence_ranking
from pipeline.presence import human_presence_prompt_plan_v1 as presence_plan
from pipeline.presence.human_presence_output_qa_v1 import HumanPresenceOutputQAError
from pipeline.influencer_nodes.lena import autonomy_ladder
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools import lena_presence_output_qa_disposition_v1 as presence_output_qa
from tools import lena_photo_qa_disposition_v1 as qa_disposition
from tools.strategy import lena_execute_retry_decision_v1 as retry_decision
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff
from tools.strategy import lena_run_generated_asset_qa_v1 as wrapper
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


DATE = "2026-07-15"
SLOT_ID = "higgsfield-20260715-hcr_011-photo"
RECIPE_ID = "hcr_011"
PROMPT = "Exact synthetic Lena prompt for QA lifecycle tests."
PROMPT_SHA = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wrapper, "ROOT", tmp_path)
    monkeypatch.setattr(wrapper, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(approval, "ROOT", tmp_path)
    monkeypatch.setattr(approval, "DEFAULT_APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")
    monkeypatch.setattr(qa_disposition, "ROOT", tmp_path)
    monkeypatch.setattr(qa_disposition, "OUTPUT_ROOT", tmp_path / "pipeline" / "asset_review" / "lena")
    monkeypatch.setattr(presence_output_qa, "ROOT", tmp_path)
    monkeypatch.setattr(presence_output_qa, "OUTPUT_ROOT", tmp_path / "pipeline" / "asset_review" / "lena" / "presence_output_qa")
    monkeypatch.setattr(identity, "ROOT", tmp_path)
    monkeypatch.setattr(identity, "HIGGSFIELD_DEBUG_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    monkeypatch.setattr(retry_decision, "ROOT", tmp_path)
    monkeypatch.setattr(retry_decision, "DEFAULT_OUTPUT_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "retry_decisions")
    monkeypatch.setattr(retry_handoff, "ROOT", tmp_path)
    monkeypatch.setattr(retry_handoff, "DEFAULT_OUTPUT_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs")
    monkeypatch.setattr(autonomy_ladder, "assert_allowed", lambda *args, **kwargs: None)


def _approval_result(tmp_path: Path) -> dict[str, object]:
    approval_repo_path = f"pipeline/approvals/lena/generation/{DATE}/{SLOT_ID}_higgsfield_generation_approval.json"
    handoff_repo_path = f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"
    approval_path = tmp_path / approval_repo_path
    candidate_selection_binding = {
        "selected_candidate_artifact_path": (
            f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/"
            "lena_pre_generation_candidate_selected.json"
        ),
        "selected_candidate_artifact_sha256": "b" * 64,
        "candidate_id": f"{SLOT_ID}::{RECIPE_ID}::fixture",
        "slot_id": SLOT_ID,
        "recipe_id": RECIPE_ID,
        "candidate_prompt_sha256": PROMPT_SHA,
        "candidate_lane": "fixture_lane",
        "source_prompt_family": "prompt_library_candidate",
    }
    provider_execution_binding = {
        "content_packet_artifact_path": (
            f"pipeline/strategy/lena/content_packets/{DATE}/"
            f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
        ),
        "content_packet_artifact_sha256": "c" * 64,
        "recipe_id": RECIPE_ID,
        "slot_id": SLOT_ID,
        "provider_prompt_sha256": PROMPT_SHA,
        "provider_lane": "fixture_lane",
        "source_prompt_family": "compact_provider_prompt",
        "provider": "higgsfield",
        "model": "text2image_soul_v2",
    }
    binding_linkage = {
        "selected_candidate_artifact_path": candidate_selection_binding[
            "selected_candidate_artifact_path"
        ],
        "selected_candidate_artifact_sha256": candidate_selection_binding[
            "selected_candidate_artifact_sha256"
        ],
        "content_packet_artifact_path": provider_execution_binding[
            "content_packet_artifact_path"
        ],
        "content_packet_artifact_sha256": provider_execution_binding[
            "content_packet_artifact_sha256"
        ],
        "recipe_id": RECIPE_ID,
        "slot_id": SLOT_ID,
        "candidate_id": candidate_selection_binding["candidate_id"],
        "candidate_lane": "fixture_lane",
        "provider_lane": "fixture_lane",
        "candidate_prompt_family": "prompt_library_candidate",
        "provider_prompt_family": "compact_provider_prompt",
    }
    approval_record = {
        "report_type": approval.APPROVAL_REPORT_TYPE,
        "schema_version": approval.APPROVAL_SCHEMA_VERSION,
        "approval_type": approval.APPROVAL_TYPE,
        "operator_id": approval.CANONICAL_OPERATOR_ID,
        "approved_at_utc": "2026-07-15T12:00:00+00:00",
        "expires_at_utc": "2026-07-15T12:30:00+00:00",
        "handoff_artifact_path": handoff_repo_path,
        "handoff_artifact_sha256": "a" * 64,
        "handoff_report_type": approval.HANDOFF_REPORT_TYPE,
        "handoff_schema_version": approval.HANDOFF_SCHEMA_VERSION,
        "date": DATE,
        "slot_id": SLOT_ID,
        "prompt_sha256": PROMPT_SHA,
        "candidate_selection_binding": candidate_selection_binding,
        "provider_execution_binding": provider_execution_binding,
        "binding_linkage": binding_linkage,
        "provider": approval.APPROVAL_PROVIDER,
        "executor": approval.APPROVAL_EXECUTOR,
        "model": approval.MODEL,
        "aspect_ratio": approval.ASPECT_RATIO,
        "soul_name": approval.SOUL_NAME,
        "soul_type": approval.SOUL_TYPE,
        "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
        "confirmation_statement": approval.confirmation_phrase(SLOT_ID),
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }
    _write_json(approval_path, approval_record)
    return {
        "approval": approval_record,
        "approval_path": approval_path,
        "approval_repo_path": approval_repo_path,
        "approval_sha256": _sha(approval_path),
        "handoff_facts": {
            "date": DATE,
            "slot_id": SLOT_ID,
            "handoff_repo_path": handoff_repo_path,
            "handoff_sha256": "a" * 64,
            "prompt_sha256": PROMPT_SHA,
            "candidate_selection_binding": candidate_selection_binding,
            "provider_execution_binding": provider_execution_binding,
            "binding_linkage": binding_linkage,
            "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
            "soul_name": approval.SOUL_NAME,
            "soul_type": approval.SOUL_TYPE,
        },
        "approved_at_utc": "2026-07-15T12:00:00+00:00",
        "expires_at_utc": "2026-07-15T12:30:00+00:00",
        "is_expired": False,
        "scope_summary": {
            "authorized_attempts": 1,
            "upload_authorized": False,
            "queue_promotion_authorized": False,
            "publish_authorized": False,
            "analytics_mutation_authorized": False,
        },
    }


def _build_fixture(tmp_path: Path) -> dict[str, object]:
    approval_result = _approval_result(tmp_path)
    claim_path = approval.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval.receipt_output_path(DATE, SLOT_ID)
    approval.write_generation_claim_atomic(claim_path, approval.build_generation_claim_record(approval_result))

    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "white").save(image_path)
    image_sha256 = _sha(image_path)

    manifest = {
        "provider": "higgsfield",
        "date": DATE,
        "slot_id": SLOT_ID,
        "provider_status": "completed",
        "saved_image_path": str(image_path),
        "saved_image_sha256": image_sha256,
        "generation_claim_artifact_path": approval.repo_relative_path(claim_path),
        "generation_execution_receipt_path": approval.repo_relative_path(receipt_path),
        "provider_job_id": "job-123",
        "image_format_detected": ".png",
    }
    _write_json(manifest_path, manifest)
    manifest_sha256 = _sha(manifest_path)

    receipt = approval.build_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome="success",
        subprocess_start_attempted=True,
        provider_submission_may_have_occurred=True,
        provider_job_id="job-123",
        provider_status="completed",
        output_path=str(image_path),
        image_format_detected=".png",
        actual_manifest_path=approval.repo_relative_path(manifest_path),
        generated_image_sha256=image_sha256,
        manifest_sha256=manifest_sha256,
    )
    approval.write_generation_execution_receipt_atomic(receipt_path, receipt)

    accounting_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_live_generation_accounting_{DATE}_{SLOT_ID}.json"
    accounting = {
        "report_type": "lena_live_generation_accounting",
        "schema_version": "v1",
        "generated_at": "2026-07-15T12:02:00+00:00",
        "date": DATE,
        "slot_id": SLOT_ID,
        "recipe_id": RECIPE_ID,
        "live_generation_accounting_status": "live_generation_accounted",
        "handoff_artifact": approval_result["handoff_facts"]["handoff_repo_path"],
        "approval_artifact": approval_result["approval_repo_path"],
        "executor_result_manifest": approval.repo_relative_path(manifest_path),
        "generated_output_paths": {
            "saved_image_path": str(image_path),
            "manifest_path": approval.repo_relative_path(manifest_path),
        },
        "generation_claim_artifact": approval.repo_relative_path(claim_path),
        "generation_receipt_artifact": approval.repo_relative_path(receipt_path),
        "claim_written": True,
        "receipt_written": True,
        "manifest_written": True,
        "publish_authorized": False,
        "publish_performed": False,
        "queue_mutated": False,
        "qa_disposition_required": True,
        "next_allowed_action": "run_qa_disposition",
        "dirty_workspace_dependency": False,
        "failure_stage": None,
        "failure_error_text": None,
        "provider_submission_may_have_occurred": True,
        "subprocess_start_attempted": True,
        "side_effect_flags": {
            "provider_call_performed": True,
            "generation_performed": True,
            "publish_performed": False,
            "queue_mutated": False,
            "approval_consumed": True,
            "claims_written": True,
            "receipts_written": True,
            "qa_run": False,
            "retry_executed": False,
            "dirty_workspace_dependency": False,
        },
    }
    _write_json(accounting_path, accounting)

    decision_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / "lena_execute_selected_candidate_2026-07-15.json"
    decision = {
        "schema_version": "lena_execute_selected_candidate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": "b" * 40,
        "candidate_status": "selected",
        "final_action": "prepare_higgsfield_still_dry_run_for_review",
        "candidate": {
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_fixture",
            "slot_id": SLOT_ID,
            "lane": "synthetic lane",
            "recipe_id": RECIPE_ID,
            "hook_id": "cbn_fixture",
            "prompt_sha256": PROMPT_SHA,
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {SLOT_ID}",
        },
        "exact_next_allowed_action": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {SLOT_ID}",
        "provider_authorized": False,
        "side_effects_performed": [],
        "decision_fingerprint_sha256": "c" * 64,
        "generated_at_utc": "2026-07-15T12:01:00Z",
    }
    _write_json(decision_path, decision)

    reference_path = tmp_path / "refs" / "lena_reference.png"
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), "gray").save(reference_path)
    reference_authority_path = tmp_path / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json"
    _write_json(
        reference_authority_path,
        {
            "schema_version": "lena_identity_reference_authority_v1",
            "authority_id": "lena_visual_reference_authority_v1",
            "authority_commit": "d" * 40,
            "reference_set_sha256": "e" * 64,
            "references": [{"path": approval.repo_relative_path(reference_path), "sha256": _sha(reference_path)}],
        },
    )
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), "gray").save(reference_path)

    evidence_path = identity.identity_verification_evidence_path(DATE, SLOT_ID)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        evidence_path,
        {
            "schema_version": identity.SCHEMA_VERSION,
            "verified_at_utc": "2026-07-15T12:03:00+00:00",
            "provider": "higgsfield",
            "date": DATE,
            "slot_id": SLOT_ID,
            "provider_job_id": "job-123",
            "provider_job_status": "completed",
            "job_type": identity.EXPECTED_JOB_TYPE,
            "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
            "soul_name": identity.EXPECTED_SOUL_NAME,
            "soul_type": identity.EXPECTED_SOUL_TYPE,
            "prompt_sha256": PROMPT_SHA,
            "width": identity.EXPECTED_WIDTH,
            "height": identity.EXPECTED_HEIGHT,
            "local_image_path": str(image_path),
            "local_image_sha256": _sha(image_path),
            "local_image_sha256_provenance": "fixture local hash",
            "verification_result": "pass",
            "checks_passed": ["fixture"],
        },
    )

    return {
        "approval_result": approval_result,
        "accounting_path": accounting_path,
        "decision_path": decision_path,
        "manifest_path": manifest_path,
        "image_path": image_path,
        "claim_path": claim_path,
        "receipt_path": receipt_path,
        "reference_path": reference_path,
        "reference_authority_path": reference_authority_path,
        "reference_sha": _sha(reference_path),
        "evidence_path": evidence_path,
    }


def _add_hpe_prompt_pack_evidence(
    decision: dict[str, object],
    *,
    plan: dict[str, object],
    plan_fingerprint_sha256: str | None = None,
) -> dict[str, object]:
    decision = json.loads(json.dumps(decision))
    decision["evidence"] = {"prompt_pack": {"human_presence": plan}}
    if plan_fingerprint_sha256 is not None:
        decision["plan_fingerprint_sha256"] = plan_fingerprint_sha256
    return decision


def _build_hpe_fixture(
    tmp_path: Path,
    *,
    include_plan_fingerprint: bool,
) -> dict[str, object]:
    fixture = _build_fixture(tmp_path)
    contract = lena_profile.build_lena_presence_contract()
    plan = presence_plan.compile_human_presence_prompt_plan(contract, medium="still_image")
    decision = json.loads(fixture["decision_path"].read_text(encoding="utf-8"))
    fingerprint = presence_ranking.plan_fingerprint_sha256(plan)
    updated = _add_hpe_prompt_pack_evidence(
        decision,
        plan=plan,
        plan_fingerprint_sha256=fingerprint if include_plan_fingerprint else None,
    )
    _write_json(fixture["decision_path"], updated)
    fixture["human_presence_plan"] = plan
    fixture["human_presence_plan_fingerprint_sha256"] = fingerprint if include_plan_fingerprint else None
    return fixture


def _photo_qa_accept_runner(fixture: dict[str, object]):
    def qa_runner(**kwargs: object) -> dict[str, object]:
        return {
            "schema_version": qa_disposition.SCHEMA_VERSION,
            "influencer_id": "lena",
            "generated_at_utc": "2026-07-15T12:04:00Z",
            "authority_commit": "b" * 40,
            "decision_artifact_path": str(fixture["decision_path"].resolve()),
            "decision_fingerprint_sha256": "c" * 64,
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_fixture",
            "slot_id": SLOT_ID,
            "lane": "synthetic lane",
            "recipe_id": RECIPE_ID,
            "hook_id": "cbn_fixture",
            "prompt_sha256": PROMPT_SHA,
            "image_path": str(fixture["image_path"].resolve()),
            "image_sha256": _sha(fixture["image_path"]),
            "generation_provenance": {
                "date": DATE,
                "manifest_path": approval.repo_relative_path(fixture["manifest_path"]),
            },
            "identity_reference_provenance": {},
            "qa_inputs": {},
            "qa_checks": {},
            "reason_codes": [],
            "disposition": "accept",
            "retry_eligible": False,
            "hard_stop_reason": None,
            "confidence": "high",
            "reviewer_type": "local_validation_only",
            "visual_judgment_source": {},
            "provider_called": False,
            "side_effects_performed": [],
            "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
        }

    return qa_runner


def test_missing_accounting_report_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    with pytest.raises(wrapper.GeneratedAssetQaLifecycleError) as excinfo:
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=tmp_path / "missing.json",
            decision_artifact=tmp_path / "decision.json",
            identity_reference_authority_artifact=tmp_path / "authority.json",
            identity_reference_authority_sha256="f" * 64,
            identity_references=[(tmp_path / "ref.png", "f" * 64)],
        )
    assert excinfo.value.code == "missing_live_generation_accounting_report"


def test_missing_generated_image_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    fixture["image_path"].unlink()

    called = {"value": False}

    def qa_runner(**_kwargs: object) -> dict[str, object]:
        called["value"] = True
        raise AssertionError("qa runner should not be called when the generated image is missing")

    with pytest.raises(wrapper.GeneratedAssetQaLifecycleError) as excinfo:
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=qa_runner,
        )
    assert excinfo.value.code == "generated_image_missing"
    assert called["value"] is False


def test_missing_claim_or_receipt_linkage_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    receipt = json.loads(fixture["receipt_path"].read_text(encoding="utf-8"))
    receipt["claim_artifact_path"] = "pipeline/approvals/lena/generation/wrong.json"
    _write_json(fixture["receipt_path"], receipt)

    called = {"value": False}

    def qa_runner(**_kwargs: object) -> dict[str, object]:
        called["value"] = True
        raise AssertionError("qa runner should not be called when claim/receipt linkage is broken")

    with pytest.raises(wrapper.GeneratedAssetQaLifecycleError) as excinfo:
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=qa_runner,
        )
    assert excinfo.value.code == "generation_receipt_binding_mismatch"
    assert called["value"] is False


def test_valid_receipt_hashes_delegate_to_qa_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    receipt = json.loads(fixture["receipt_path"].read_text(encoding="utf-8"))

    called = {"value": False}

    def qa_runner(**_kwargs: object) -> dict[str, object]:
        called["value"] = True
        return _photo_qa_accept_runner(fixture)(**_kwargs)

    wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=qa_runner,
    )

    assert receipt["generated_image_sha256"] == _sha(fixture["image_path"])
    assert receipt["manifest_sha256"] == _sha(fixture["manifest_path"])
    assert called["value"] is True


def test_wrong_receipt_generated_image_sha_fails_before_qa_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    receipt = json.loads(fixture["receipt_path"].read_text(encoding="utf-8"))
    receipt["generated_image_sha256"] = "0" * 64
    _write_json(fixture["receipt_path"], receipt)

    called = {"value": False}

    def qa_runner(**_kwargs: object) -> dict[str, object]:
        called["value"] = True
        raise AssertionError("qa runner should not be called when receipt image hash is wrong")

    with pytest.raises(wrapper.GeneratedAssetQaLifecycleError) as excinfo:
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=qa_runner,
        )

    assert excinfo.value.code == "generation_receipt_binding_mismatch"
    assert "generated_image_sha256" in excinfo.value.detail
    assert called["value"] is False


def test_wrong_receipt_manifest_sha_fails_before_qa_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    receipt = json.loads(fixture["receipt_path"].read_text(encoding="utf-8"))
    receipt["manifest_sha256"] = "0" * 64
    _write_json(fixture["receipt_path"], receipt)

    called = {"value": False}

    def qa_runner(**_kwargs: object) -> dict[str, object]:
        called["value"] = True
        raise AssertionError("qa runner should not be called when receipt manifest hash is wrong")

    with pytest.raises(wrapper.GeneratedAssetQaLifecycleError) as excinfo:
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=qa_runner,
        )

    assert excinfo.value.code == "generation_receipt_binding_mismatch"
    assert "manifest_sha256" in excinfo.value.detail
    assert called["value"] is False


def test_manifest_saved_image_sha_mismatch_fails_before_qa_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    manifest = json.loads(fixture["manifest_path"].read_text(encoding="utf-8"))
    manifest["saved_image_sha256"] = "0" * 64
    _write_json(fixture["manifest_path"], manifest)

    called = {"value": False}

    def qa_runner(**_kwargs: object) -> dict[str, object]:
        called["value"] = True
        raise AssertionError("qa runner should not be called when manifest image hash is wrong")

    with pytest.raises(wrapper.GeneratedAssetQaLifecycleError) as excinfo:
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=qa_runner,
        )

    assert excinfo.value.code == "executor_result_manifest_image_sha_mismatch"
    assert called["value"] is False


def test_valid_generated_asset_delegates_to_qa_and_writes_lifecycle_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    captured: dict[str, object] = {}

    def qa_runner(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "schema_version": qa_disposition.SCHEMA_VERSION,
            "influencer_id": "lena",
            "generated_at_utc": "2026-07-15T12:04:00Z",
            "authority_commit": "b" * 40,
            "decision_artifact_path": str(fixture["decision_path"].resolve()),
            "decision_fingerprint_sha256": "c" * 64,
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_fixture",
            "slot_id": SLOT_ID,
            "lane": "synthetic lane",
            "recipe_id": RECIPE_ID,
            "hook_id": "cbn_fixture",
            "prompt_sha256": PROMPT_SHA,
            "image_path": str(fixture["image_path"].resolve()),
            "image_sha256": _sha(fixture["image_path"]),
            "generation_provenance": {
                "date": DATE,
                "manifest_path": approval.repo_relative_path(fixture["manifest_path"]),
            },
            "identity_reference_provenance": {},
            "qa_inputs": {},
            "qa_checks": {},
            "reason_codes": [],
            "disposition": "accept",
            "retry_eligible": False,
            "hard_stop_reason": None,
            "confidence": "high",
            "reviewer_type": "local_validation_only",
            "visual_judgment_source": {},
            "provider_called": False,
            "side_effects_performed": [],
            "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
        }

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=qa_runner,
    )

    assert captured["decision_path"] == fixture["decision_path"].resolve()
    assert captured["manifest_path"] == fixture["manifest_path"].resolve()
    assert captured["image_path"] == fixture["image_path"].resolve()
    assert report["qa_lifecycle_status"] == "qa_lifecycle_passed"
    assert report["qa_status"] == "accept"
    assert report["retry_recommended"] is False
    assert report["next_allowed_action"] == "await_publish_authorization"
    assert report["human_presence_output_qa_state"]["status"] == "not_requested"
    assert report["human_presence_output_qa_state"]["reason"] == "hpe_not_requested"
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["generation_claim_artifact"] == approval.repo_relative_path(fixture["claim_path"])
    assert report["generation_receipt_artifact"] == approval.repo_relative_path(fixture["receipt_path"])
    assert report["qa_disposition_artifact"].endswith("_qa_disposition.json")
    assert report["side_effect_flags"]["provider_call_performed"] is False
    assert report["side_effect_flags"]["generation_performed"] is False
    assert report["side_effect_flags"]["qa_run"] is True
    assert report["side_effect_flags"]["retry_executed"] is False
    assert report["side_effect_flags"]["dirty_workspace_dependency"] is False
    assert wrapper.report_path(DATE, SLOT_ID, wrapper.NEXT_ACTIONS).is_file()
    assert json.loads(wrapper.report_path(DATE, SLOT_ID, wrapper.NEXT_ACTIONS).read_text(encoding="utf-8")) == report


def test_hpe_success_records_completed_lifecycle_state_and_image_index_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    captured: dict[str, object] = {}

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        captured.update(kwargs)
        return presence_output_qa.run_presence_output_qa(
            date_str=str(kwargs["date_str"]),
            slot_id=str(kwargs["slot_id"]),
            image_index=int(kwargs["image_index"]),
            plan=kwargs["plan"],
            candidate_decision_path=Path(kwargs["candidate_decision_path"]),
            manifest_path=Path(kwargs["manifest_path"]),
            image_path=Path(kwargs["image_path"]),
            media_type=str(kwargs["media_type"]),
            output_root=presence_output_qa.OUTPUT_ROOT,
            evaluated_at_utc="2026-07-15T12:04:00Z",
        )

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
        human_presence_output_qa_runner=hpe_runner,
    )

    assert set(captured) == {
        "date_str",
        "slot_id",
        "image_index",
        "plan",
        "candidate_decision_path",
        "manifest_path",
        "image_path",
        "media_type",
        "live_presence_semantic_review",
    }
    assert captured["date_str"] == DATE
    assert captured["slot_id"] == SLOT_ID
    assert captured["image_index"] == 0
    assert captured["plan"] == fixture["human_presence_plan"]
    assert captured["candidate_decision_path"] == fixture["decision_path"].resolve()
    assert captured["manifest_path"] == fixture["manifest_path"].resolve()
    assert captured["image_path"] == fixture["image_path"].resolve()
    assert captured["media_type"] == "still_image"
    assert captured["live_presence_semantic_review"] is False
    assert report["qa_status"] == "accept"
    assert report["human_presence_output_qa_state"]["status"] == "completed"
    assert report["human_presence_output_qa_state"]["image_index"] == 0
    assert report["human_presence_output_qa_state"]["integrity_status"] == "not_assessable"
    assert report["human_presence_output_qa_state"]["recommendation"] == "not_assessable"
    assert report["human_presence_output_qa_state"]["artifact_path"].endswith(".json")
    assert report["human_presence_output_qa_state"]["semantic_status"] == "not_evaluated"
    assert report["human_presence_output_qa_state"]["error_code"] is None
    assert report["human_presence_output_qa_state"]["authority"] == "evidence_only"
    assert report["side_effect_flags"]["provider_call_performed"] is False
    assert report["side_effect_flags"]["generation_performed"] is False
    assert report["side_effect_flags"]["qa_run"] is True


def test_live_presence_semantic_review_flag_is_forwarded_to_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    captured: dict[str, object] = {}

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        captured.update(kwargs)
        return presence_output_qa.run_presence_output_qa(
            date_str=str(kwargs["date_str"]),
            slot_id=str(kwargs["slot_id"]),
            image_index=int(kwargs["image_index"]),
            plan=kwargs["plan"],
            candidate_decision_path=Path(kwargs["candidate_decision_path"]),
            manifest_path=Path(kwargs["manifest_path"]),
            image_path=Path(kwargs["image_path"]),
            media_type=str(kwargs["media_type"]),
            output_root=presence_output_qa.OUTPUT_ROOT,
            evaluated_at_utc="2026-07-15T12:04:00Z",
        )

    wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
        human_presence_output_qa_runner=hpe_runner,
        live_presence_semantic_review=True,
    )

    assert captured["live_presence_semantic_review"] is True


def test_hpe_without_plan_fingerprint_still_completes_as_not_assessable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=False)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
    )

    assert report["human_presence_output_qa_state"]["status"] == "completed"
    assert report["human_presence_output_qa_state"]["integrity_status"] == "not_assessable"
    assert report["human_presence_output_qa_state"]["recommendation"] == "not_assessable"
    assert report["human_presence_output_qa_state"]["reason"] is None
    assert report["human_presence_output_qa_state"]["artifact_path"].endswith(".json")
    assert report["qa_status"] == "accept"


def test_absent_hpe_metadata_marks_not_requested_and_skips_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    called = {"value": False}

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        called["value"] = True
        raise AssertionError("HPE runner should not be called when metadata is absent")

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
        human_presence_output_qa_runner=hpe_runner,
    )

    assert called["value"] is False
    assert report["qa_status"] == "accept"
    assert report["human_presence_output_qa_state"]["status"] == "not_requested"
    assert report["human_presence_output_qa_state"]["reason"] == "hpe_not_requested"
    assert report["human_presence_output_qa_state"]["artifact_path"] is None


def test_malformed_hpe_metadata_is_reported_as_error_without_disguising_as_not_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    decision = json.loads(fixture["decision_path"].read_text(encoding="utf-8"))
    decision["evidence"] = {"prompt_pack": {"human_presence": "not-a-dict"}}
    _write_json(fixture["decision_path"], decision)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
    )

    assert report["human_presence_output_qa_state"]["status"] == "error"
    assert report["human_presence_output_qa_state"]["error_code"] == "presence_output_qa_integration_error"
    assert report["human_presence_output_qa_state"]["reason"] is None
    assert report["qa_status"] == "accept"


def test_hpe_typed_error_preserves_photo_qa_disposition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        raise HumanPresenceOutputQAError("presence_output_invalid_sha256", "bad image hash")

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
        human_presence_output_qa_runner=hpe_runner,
    )

    assert report["qa_status"] == "accept"
    assert report["human_presence_output_qa_state"]["status"] == "error"
    assert report["human_presence_output_qa_state"]["error_code"] == "presence_output_invalid_sha256"
    assert report["human_presence_output_qa_state"]["error_message"] == "bad image hash"


def test_hpe_filesystem_error_is_reported_as_integration_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        raise OSError("disk full")

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=_photo_qa_accept_runner(fixture),
        human_presence_output_qa_runner=hpe_runner,
    )

    assert report["human_presence_output_qa_state"]["status"] == "error"
    assert report["human_presence_output_qa_state"]["error_code"] == "presence_output_qa_integration_error"
    assert report["human_presence_output_qa_state"]["error_message"] == "disk full"
    assert report["qa_status"] == "accept"


def test_hpe_type_error_propagates_without_becoming_integration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    observed = {"called": False}

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        observed["called"] = True
        raise TypeError("bad runner wiring")

    with pytest.raises(TypeError, match="bad runner wiring"):
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=_photo_qa_accept_runner(fixture),
            human_presence_output_qa_runner=hpe_runner,
        )

    assert observed["called"] is True
    assert wrapper.report_path(DATE, SLOT_ID, wrapper.NEXT_ACTIONS).exists() is False


def test_unexpected_hpe_exception_is_not_silently_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    def hpe_runner(**kwargs: object) -> tuple[Path, dict[str, object]]:
        raise RuntimeError("unexpected bug")

    with pytest.raises(RuntimeError, match="unexpected bug"):
        wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=_photo_qa_accept_runner(fixture),
            human_presence_output_qa_runner=hpe_runner,
        )


def test_qa_fail_surfaces_retry_reference_without_executing_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])
    decision = json.loads(fixture["decision_path"].read_text(encoding="utf-8"))

    def qa_runner(**kwargs: object) -> dict[str, object]:
        return {
            "schema_version": qa_disposition.SCHEMA_VERSION,
            "influencer_id": "lena",
            "generated_at_utc": "2026-07-15T12:05:00Z",
            "authority_commit": "b" * 40,
            "decision_artifact_path": str(fixture["decision_path"].resolve()),
            "decision_fingerprint_sha256": "c" * 64,
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_fixture",
            "slot_id": SLOT_ID,
            "lane": "synthetic lane",
            "recipe_id": RECIPE_ID,
            "hook_id": "cbn_fixture",
            "prompt_sha256": PROMPT_SHA,
            "image_path": str(fixture["image_path"].resolve()),
            "image_sha256": _sha(fixture["image_path"]),
            "generation_provenance": {
                "date": DATE,
                "manifest_path": approval.repo_relative_path(fixture["manifest_path"]),
            },
            "identity_reference_provenance": {},
            "qa_inputs": {},
            "qa_checks": {},
            "reason_codes": ["composition_below_standard"],
            "disposition": "retryable_failure",
            "retry_eligible": True,
            "hard_stop_reason": None,
            "confidence": "medium",
            "reviewer_type": "local_validation_only",
            "visual_judgment_source": {},
            "provider_called": False,
            "side_effects_performed": [],
            "exact_next_allowed_action": "retry_review_required",
        }

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=qa_runner,
    )

    retry_slot_id = retry_decision._retry_slot_id(SLOT_ID)
    assert report["qa_lifecycle_status"] == "qa_lifecycle_retry_review_required"
    assert report["qa_status"] == "retryable_failure"
    assert report["retry_recommended"] is True
    assert report["retry_decision_artifact"] == approval.repo_relative_path(
        retry_decision.retry_decision_artifact_path(DATE, retry_slot_id, decision["decision_fingerprint_sha256"])
    )
    assert report["retry_handoff_artifact"] == approval.repo_relative_path(
        retry_handoff.retry_handoff_artifact_path(DATE, retry_slot_id, PROMPT_SHA)
    )
    assert report["next_allowed_action"] == "retry_review_required"
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["side_effect_flags"]["qa_run"] is True
    assert report["side_effect_flags"]["retry_executed"] is False
    assert report["side_effect_flags"]["dirty_workspace_dependency"] is False


def test_blocked_human_visual_review_waits_without_retry_or_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    def qa_runner(**kwargs: object) -> dict[str, object]:
        return {
            "schema_version": qa_disposition.SCHEMA_VERSION,
            "influencer_id": "lena",
            "generated_at_utc": "2026-07-15T12:05:00Z",
            "authority_commit": "b" * 40,
            "decision_artifact_path": str(fixture["decision_path"].resolve()),
            "decision_fingerprint_sha256": "c" * 64,
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_fixture",
            "slot_id": SLOT_ID,
            "lane": "synthetic lane",
            "recipe_id": RECIPE_ID,
            "hook_id": "cbn_fixture",
            "prompt_sha256": PROMPT_SHA,
            "image_path": str(fixture["image_path"].resolve()),
            "image_sha256": _sha(fixture["image_path"]),
            "generation_provenance": {
                "date": DATE,
                "manifest_path": approval.repo_relative_path(fixture["manifest_path"]),
            },
            "identity_reference_provenance": {},
            "qa_inputs": {},
            "qa_checks": {},
            "reason_codes": ["human_visual_review_required"],
            "disposition": "blocked",
            "retry_eligible": False,
            "hard_stop_reason": None,
            "confidence": "low",
            "reviewer_type": "local_validation_only",
            "visual_judgment_source": {},
            "provider_called": False,
            "side_effects_performed": [],
            "exact_next_allowed_action": "human_visual_review_required",
        }

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=qa_runner,
    )

    assert report["qa_lifecycle_status"] == "awaiting_human_visual_review"
    assert report["qa_status"] == "blocked"
    assert report["retry_recommended"] is False
    assert report["retry_decision_artifact"] == ""
    assert report["retry_handoff_artifact"] == ""
    assert report["next_allowed_action"] == "human_visual_review_required"
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["side_effect_flags"]["qa_run"] is True
    assert report["side_effect_flags"]["retry_executed"] is False


def test_unbound_photo_qa_binding_error_is_not_masked_or_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_fixture(tmp_path)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    def qa_runner(**kwargs: object) -> dict[str, object]:
        return {
            "schema_version": qa_disposition.SCHEMA_VERSION,
            "influencer_id": "lena",
            "disposition": "blocked",
            "reason_codes": ["provenance_mismatch"],
            "hard_stop_reason": "generation_manifest_defect",
            "provider_called": False,
            "side_effects_performed": [],
            "exact_next_allowed_action": "review_generated_asset",
            "qa_inputs": {
                "binding_error": "manifest is missing required generation provenance: pose_body_language_id",
            },
        }

    def fail_writer(*args: object, **kwargs: object) -> None:
        raise AssertionError("unbound QA artifacts must not be passed to the disposition writer")

    monkeypatch.setattr(qa_disposition, "write_disposition_artifact", fail_writer)

    report = wrapper.evaluate_generated_asset_qa_lifecycle(
        live_generation_accounting_artifact=fixture["accounting_path"],
        decision_artifact=fixture["decision_path"],
        identity_reference_authority_artifact=fixture["reference_authority_path"],
        identity_reference_authority_sha256="e" * 64,
        identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
        identity_evidence_artifact=fixture["evidence_path"],
        qa_runner=qa_runner,
    )

    assert report["qa_lifecycle_status"] == "qa_lifecycle_blocked_unbound"
    assert report["blocking_reasons"] == ["qa_binding_error"]
    assert report["qa_disposition_artifact"] is None
    assert report["qa_inputs"]["binding_error"] == "manifest is missing required generation provenance: pose_body_language_id"
    assert report["provider_call_performed"] is False
    assert report["generation_performed"] is False
    assert report["side_effect_flags"]["retry_executed"] is False
    assert wrapper.report_path(DATE, SLOT_ID, wrapper.NEXT_ACTIONS).exists() is False


def test_hpe_authority_invariance_matrix_stays_stable_across_semantic_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    fixture = _build_hpe_fixture(tmp_path, include_plan_fingerprint=True)
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: fixture["approval_result"])

    def semantic_provider_for(status: str):
        def _provider(**kwargs: object) -> dict[str, object]:
            if status == "error":
                return {
                    "semantic_status": "error",
                    "semantic_findings": [],
                    "semantic_result_provenance": None,
                    "semantic_error": {"error_code": "semantic_visual_review_provider_unavailable", "error_message": "synthetic proof provider error"},
                }
            if status == "not_assessable":
                return {
                    "semantic_status": "not_assessable",
                    "semantic_findings": [],
                    "semantic_result_provenance": None,
                    "semantic_error": None,
                }
            findings: list[dict[str, object]] = []
            if status == "findings_present":
                findings = [
                    {
                        "finding_code": "object_interaction_plan_contradiction",
                        "category": "plan_contradiction",
                        "plan_field_ref": "performance_actions.object_interaction",
                        "plan_field_value": "simple_prop_hold",
                        "observed_description": "The hand is not interacting with an object.",
                        "confidence": "high",
                        "image_index": 0,
                        "advisory_only": False,
                    }
                ]
            return {
                "semantic_status": "aligned" if not findings else "findings_present",
                "semantic_findings": findings,
                "semantic_result_provenance": {
                    "provider": kwargs.get("provider", "anthropic"),
                    "model": kwargs.get("model", "claude-sonnet-5"),
                    "request_binding_sha256": "a" * 64,
                    "evaluated_at_utc": "2026-07-15T12:04:00Z",
                    "response_schema_version": "human_presence_semantic_visual_observations_v1",
                },
                "semantic_error": None,
            }

        return _provider

    statuses = ["aligned", "findings_present", "error", "not_assessable", "not_evaluated"]
    baseline: dict[str, object] | None = None
    for status in statuses:
        qa_root = tmp_path / status / "qa"
        lifecycle_root = tmp_path / status / "next_actions"
        report = wrapper.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=fixture["accounting_path"],
            decision_artifact=fixture["decision_path"],
            identity_reference_authority_artifact=fixture["reference_authority_path"],
            identity_reference_authority_sha256="e" * 64,
            identity_references=[(fixture["reference_path"], fixture["reference_sha"])],
            identity_evidence_artifact=fixture["evidence_path"],
            qa_runner=_photo_qa_accept_runner(fixture),
            human_presence_output_qa_runner=lambda **kwargs: presence_output_qa.run_presence_output_qa(
                date_str=str(kwargs["date_str"]),
                slot_id=str(kwargs["slot_id"]),
                image_index=int(kwargs["image_index"]),
                plan=kwargs["plan"],
                candidate_decision_path=Path(kwargs["candidate_decision_path"]),
                manifest_path=Path(kwargs["manifest_path"]),
                image_path=Path(kwargs["image_path"]),
                media_type=str(kwargs["media_type"]),
                output_root=qa_root,
                evaluated_at_utc="2026-07-15T12:04:00Z",
                live_presence_semantic_review=kwargs["live_presence_semantic_review"],
                semantic_provider=semantic_provider_for(status) if status != "not_evaluated" else None,
            ),
            live_presence_semantic_review=status != "not_evaluated",
            qa_output_root=qa_root,
            lifecycle_output_root=lifecycle_root,
        )
        summary = {
            "qa_lifecycle_status": report["qa_lifecycle_status"],
            "qa_status": report["qa_status"],
            "publish_authorized": report["publish_authorized"],
            "publish_performed": report["publish_performed"],
            "queue_mutated": report["queue_mutated"],
            "provider_call_performed": report["side_effect_flags"]["provider_call_performed"],
            "generation_performed": report["side_effect_flags"]["generation_performed"],
            "qa_run": report["side_effect_flags"]["qa_run"],
            "retry_executed": report["side_effect_flags"]["retry_executed"],
            "dirty_workspace_dependency": report["side_effect_flags"]["dirty_workspace_dependency"],
            "human_presence_authority": report["human_presence_output_qa_state"]["authority"],
        }
        if baseline is None:
            baseline = summary
        else:
            assert summary == baseline
        assert report["human_presence_output_qa_state"]["semantic_status"] in {
            "aligned",
            "findings_present",
            "error",
            "not_assessable",
            "not_evaluated",
        }


def test_wrapper_source_does_not_import_provider_publish_or_queue_helpers() -> None:
    source = Path(wrapper.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert "pipeline.higgsfield_lena_api_executor" not in imported_modules
    assert not any("publish" in module for module in imported_modules)
    assert not any("queue" in module for module in imported_modules)
    assert not any("execute_approved_live_generation" in module for module in imported_modules)
    assert "lena_photo_qa_disposition_v1" in source
    assert "lena_higgsfield_generation_approval_v1" in source
