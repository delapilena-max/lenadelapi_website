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
from pipeline.influencer_nodes.lena import autonomy_ladder
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools import lena_photo_qa_disposition_v1 as qa_disposition
from tools.strategy import lena_execute_retry_decision_v1 as retry_decision
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff
from tools.strategy import lena_run_generated_asset_qa_v1 as wrapper


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

    manifest = {
        "provider": "higgsfield",
        "date": DATE,
        "slot_id": SLOT_ID,
        "provider_status": "completed",
        "saved_image_path": str(image_path),
        "generation_claim_artifact_path": approval.repo_relative_path(claim_path),
        "generation_execution_receipt_path": approval.repo_relative_path(receipt_path),
        "provider_job_id": "job-123",
        "image_format_detected": ".png",
    }
    _write_json(manifest_path, manifest)

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
