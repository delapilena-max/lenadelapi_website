from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

import pipeline.higgsfield_lena_api_executor as executor
import tools.lena_higgsfield_generation_approval_v1 as approval
import tools.strategy.lena_execute_approved_live_generation_v1 as wrapper
from tests import test_lena_higgsfield_generation_approval_v1 as approval_fixture


DATE = "2026-07-15"
SLOT_ID = "higgsfield-20260715-hcr_011-photo"
RECIPE_ID = "hcr_011"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wrapper, "ROOT", tmp_path)
    monkeypatch.setattr(wrapper, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(executor, "ROOT", tmp_path)
    monkeypatch.setattr(approval, "ROOT", tmp_path)
    monkeypatch.setattr(approval, "DEFAULT_APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")


def _touch(path: Path, payload: str = "{}\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _write_image(path: Path, *, size: tuple[int, int] = (1152, 2048)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def _write_reference_authority(tmp_path: Path, reference_path: Path) -> None:
    _touch(reference_path, "reference-bytes\n")
    _touch(
        tmp_path / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json",
        json.dumps(
            {
                "schema_version": "lena_identity_reference_authority_v1",
                "authority_id": "lena_visual_reference_authority_v1",
                "references": [
                    {
                        "path": wrapper.repo_relative_path(reference_path),
                        "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                    }
                ],
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
    )


def _approval_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    monkeypatch.setattr(approval_fixture, "DATE", DATE)
    monkeypatch.setattr(approval_fixture, "SLOT_ID", SLOT_ID)
    monkeypatch.setattr(
        approval_fixture,
        "RECONCILIATION_PATH",
        f"pipeline/strategy/lena/reconciliations/{DATE}/lena_generation_reconciliation_fixture.json",
    )
    approval_fixture._patch_root(tmp_path, monkeypatch)
    handoff_path = approval_fixture._write_handoff(tmp_path)
    approval_path = approval_fixture._record_and_write(tmp_path, handoff_path)
    result = approval.validate_generation_approval_artifact(approval_path)
    result["claim_path"] = approval.claim_output_path(DATE, SLOT_ID)
    result["receipt_path"] = approval.receipt_output_path(DATE, SLOT_ID)
    return result


def _context_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    approval_result = _approval_result(tmp_path, monkeypatch)
    manifest_path = executor.manifest_path(DATE, SLOT_ID)
    return {
        "date": DATE,
        "slot_id": SLOT_ID,
        "recipe_id": RECIPE_ID,
        "handoff_report": {"selected_recipe_id": RECIPE_ID},
        "source": {"image": {"image_prompt": "mock prompt"}},
        "packet_validation": {"ok": True},
        "validation": {"ok": True},
        "approval_result": approval_result,
        "claim_path": approval_result["claim_path"],
        "receipt_path": approval_result["receipt_path"],
        "manifest_path": manifest_path,
        "handoff_artifact": approval_result["handoff_facts"]["handoff_path"],
        "approval_artifact": approval_result["approval_path"],
        "custom_reference_id": CUSTOM_REFERENCE_ID,
    }


def test_missing_handoff_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    approval_path = _touch(tmp_path / "approval.json")
    with pytest.raises(wrapper.LiveGenerationAccountingError) as excinfo:
        wrapper.execute_approved_live_generation(tmp_path / "missing_handoff.json", approval_path)
    assert excinfo.value.code == "missing_handoff"


def test_missing_approval_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    with pytest.raises(wrapper.LiveGenerationAccountingError) as excinfo:
        wrapper.execute_approved_live_generation(handoff_path, tmp_path / "missing_approval.json")
    assert excinfo.value.code == "missing_approval"


def test_stale_handoff_is_rejected_by_live_execution_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    stale_handoff_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_next_live_image_handoff_{DATE}.json"
    stale_handoff_path.parent.mkdir(parents=True, exist_ok=True)
    stale_handoff_path.write_text(
        json.dumps(
            {
                "report_type": "lena_next_live_image_handoff",
                "schema_version": "v1",
                "created_at": "2026-07-15T12:00:00+00:00",
                "execution_owner": "claude",
                "provider": "higgsfield",
                "executor_type": "higgsfield_cli",
                "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
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
                "date": DATE,
                "selected_slot_id": SLOT_ID,
                "selected_recipe_id": RECIPE_ID,
                "expected_handoff_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
                "selected_prompt_input": {
                    "prompt_sha256": "b" * 64,
                },
                "selected_prompt_input_artifact_sha256": "c" * 64,
                "structured_executor_inputs": {
                    "provider": "higgsfield",
                    "executor_type": "higgsfield_cli",
                    "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
                    "model": "text2image_soul_v2",
                    "aspect_ratio": "9:16",
                    "negative_prompt_enabled": False,
                    "live_execution_authorized": False,
                    "date": DATE,
                    "slot_id": SLOT_ID,
                    "handoff_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
                    "soul_metadata": {
                        "name": "Lena",
                        "type": "Soul 2.0",
                        "custom_reference_id": CUSTOM_REFERENCE_ID,
                        "identity_is_prompt_instruction": False,
                    },
                    "selected_prompt_sha256": "b" * 64,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(
            {
                "report_type": "lena_higgsfield_generation_approval",
                "schema_version": "v1",
                "approval_type": "higgsfield_single_generation",
                "operator_id": "nicolas",
                "approved_at_utc": "2099-07-15T12:00:00+00:00",
                "expires_at_utc": "2099-07-15T12:30:00+00:00",
                "handoff_artifact_path": f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json",
                "handoff_artifact_sha256": "a" * 64,
                "handoff_report_type": "lena_next_live_image_handoff",
                "handoff_schema_version": "v1",
                "date": DATE,
                "slot_id": SLOT_ID,
                "prompt_sha256": "b" * 64,
                "provider": "Higgsfield",
                "executor": "Higgsfield CLI repo adapter",
                "model": "text2image_soul_v2",
                "aspect_ratio": "9:16",
                "soul_name": "Lena",
                "soul_type": "Soul 2.0",
                "custom_reference_id": CUSTOM_REFERENCE_ID,
                "confirmation_statement": approval.confirmation_phrase(SLOT_ID),
                "credits_may_be_spent_acknowledged": True,
                "authorized_attempts": 1,
                "upload_authorized": False,
                "queue_promotion_authorized": False,
                "publish_authorized": False,
                "analytics_mutation_authorized": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def validating_context_loader(_handoff: Path, approval_artifact: Path) -> dict[str, object]:
        approval.validate_generation_approval_artifact(approval_artifact)
        return {
            "date": DATE,
            "slot_id": SLOT_ID,
            "recipe_id": RECIPE_ID,
            "handoff_report": {"selected_recipe_id": RECIPE_ID},
            "source": {"image": {"image_prompt": "mock prompt"}},
            "packet_validation": {"ok": True},
            "validation": {"ok": True},
            "approval_result": {"approval": {}, "handoff_facts": {}},
            "claim_path": approval.claim_output_path(DATE, SLOT_ID),
            "receipt_path": approval.receipt_output_path(DATE, SLOT_ID),
            "manifest_path": wrapper.ROOT / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json",
            "handoff_artifact": stale_handoff_path,
            "approval_artifact": approval_artifact,
            "custom_reference_id": CUSTOM_REFERENCE_ID,
        }

    with pytest.raises(approval.HiggsfieldGenerationApprovalError) as excinfo:
        wrapper.execute_approved_live_generation(
            stale_handoff_path,
            approval_path,
            live=True,
            context_loader=validating_context_loader,
        )
    assert excinfo.value.code == "handoff_selected_candidate_provenance_missing"


def test_dry_run_reports_no_publish_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")
    report = wrapper.execute_approved_live_generation(
        handoff_path,
        approval_path,
        live=False,
        context_loader=lambda *_args: _context_loader(tmp_path, monkeypatch),
    )

    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["qa_disposition_required"] is True
    assert report["next_allowed_action"] == "run_approved_live_generation"
    assert report["side_effect_flags"]["approval_consumed"] is False
    assert report["side_effect_flags"]["provider_call_performed"] is False
    assert report["side_effect_flags"]["generation_performed"] is False
    assert report["side_effect_flags"]["qa_run"] is False
    assert report["dirty_workspace_dependency"] is False


def test_success_accounting_writes_manifest_claim_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")

    saved_image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
    claim_path = approval.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval.receipt_output_path(DATE, SLOT_ID)
    reference_path = tmp_path / "refs" / "lena_reference.png"
    _write_reference_authority(tmp_path, reference_path)

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path, monkeypatch)
        ctx["claim_path"] = claim_path
        ctx["receipt_path"] = receipt_path
        ctx["manifest_path"] = manifest_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(date_str: str, slot_id: str, source: dict[str, object], custom_reference_id: str) -> dict[str, object]:
        assert date_str == DATE
        assert slot_id == SLOT_ID
        assert custom_reference_id == CUSTOM_REFERENCE_ID
        _write_image(saved_image_path)
        return {
            "job_id": "job-123",
            "status": "processing",
            "result_urls": ["https://example.invalid/result.png"],
            "saved_image_path": str(saved_image_path),
            "image_format_detected": ".png",
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        }

    def fake_build_manifest(
        date_str: str,
        slot_id: str,
        source: dict[str, object],
        custom_reference_id: str,
        live_result: dict[str, object] | None,
        *,
        claim_repo_path: str | None = None,
        receipt_repo_path: str | None = None,
        saved_image_sha256: str | None = None,
    ) -> dict[str, object]:
        return {
            "provider": "higgsfield",
            "date": date_str,
            "slot_id": slot_id,
            "saved_image_path": live_result.get("saved_image_path") if live_result else None,
            "image_format_detected": live_result.get("image_format_detected") if live_result else None,
            "claim_repo_path": claim_repo_path,
            "receipt_repo_path": receipt_repo_path,
            "saved_image_sha256": saved_image_sha256,
            "provider_status": "completed",
            "provider_job_id": live_result.get("job_id") if live_result else None,
            "job_type": "text2image_soul_v2",
            "custom_reference_id": custom_reference_id,
            "cli_soul_name": "Lena",
            "cli_soul_type": "soul_2",
            "prompt_sha256": "b" * 64,
        }

    monkeypatch.setattr(executor, "build_manifest", fake_build_manifest)

    report = wrapper.execute_approved_live_generation(
        handoff_path,
        approval_path,
        live=True,
        live_executor=fake_run_live,
        context_loader=fake_context_loader,
    )

    assert report["live_generation_accounting_status"] == "live_generation_accounted"
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["qa_disposition_required"] is True
    assert report["next_allowed_action"] == "run_qa_disposition"
    assert report["claim_written"] is True
    assert report["receipt_written"] is True
    assert report["manifest_written"] is True
    assert report["provider_submission_may_have_occurred"] is True
    assert report["subprocess_start_attempted"] is True
    assert report["generation_claim_artifact"] == wrapper.repo_relative_path(claim_path)
    assert report["generation_receipt_artifact"] == wrapper.repo_relative_path(receipt_path)
    assert report["executor_result_manifest"] == wrapper.repo_relative_path(manifest_path)
    assert report["generated_output_paths"]["saved_image_path"] == wrapper.repo_relative_path(saved_image_path)
    assert report["generated_output_paths"]["manifest_path"] == wrapper.repo_relative_path(manifest_path)
    assert report["identity_evidence_artifact"].endswith("identity_verification.json")
    assert len(report["identity_evidence_artifact_sha256"]) == 64
    assert report["generated_output_paths"]["identity_evidence_path"] == report["identity_evidence_artifact"]
    assert report["side_effect_flags"]["provider_call_performed"] is True
    assert report["side_effect_flags"]["generation_performed"] is True
    assert report["side_effect_flags"]["identity_evidence_written"] is True
    assert report["side_effect_flags"]["approval_consumed"] is True
    assert report["side_effect_flags"]["claims_written"] is True
    assert report["side_effect_flags"]["receipts_written"] is True
    assert report["side_effect_flags"]["publish_performed"] is False
    assert report["side_effect_flags"]["queue_mutated"] is False
    assert report["side_effect_flags"]["qa_run"] is False
    assert report["side_effect_flags"]["retry_executed"] is False
    assert report["side_effect_flags"]["dirty_workspace_dependency"] is False
    assert claim_path.is_file()
    assert receipt_path.is_file()
    assert manifest_path.is_file()
    identity_evidence_path = tmp_path / report["identity_evidence_artifact"]
    assert identity_evidence_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity_evidence = json.loads(identity_evidence_path.read_text(encoding="utf-8"))
    assert receipt["generated_image_sha256"] == hashlib.sha256(saved_image_path.read_bytes()).hexdigest()
    assert receipt["manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert manifest["saved_image_sha256"] == receipt["generated_image_sha256"]
    assert identity_evidence["local_image_sha256"] == receipt["generated_image_sha256"]
    assert identity_evidence["custom_reference_id"] == CUSTOM_REFERENCE_ID
    assert identity_evidence["soul_name"] == "Lena"
    assert identity_evidence["soul_type"] == "soul_2"
    assert identity_evidence["width"] == 1152
    assert identity_evidence["height"] == 2048
    assert wrapper.report_path(DATE, SLOT_ID).is_file()
    assert json.loads(wrapper.report_path(DATE, SLOT_ID).read_text(encoding="utf-8")) == report


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda manifest, paths: manifest.pop("cli_soul_name"), "manifest_cli_soul_name_missing"),
        (lambda manifest, paths: manifest.pop("cli_soul_type"), "manifest_cli_soul_type_missing"),
        (lambda manifest, paths: manifest.__setitem__("cli_soul_type", "Soul 2.0"), "manifest_cli_soul_type_mismatch"),
        (lambda manifest, paths: manifest.__setitem__("provider_status", "processing"), "manifest_provider_status_mismatch"),
        (lambda manifest, paths: manifest.__setitem__("provider_job_id", ""), "manifest_provider_job_id_missing"),
        (lambda manifest, paths: manifest.pop("prompt_sha256"), "manifest_prompt_sha256_missing"),
        (lambda manifest, paths: manifest.__setitem__("saved_image_path", str(paths["other_image_path"])), "manifest_saved_image_path_mismatch"),
        (lambda manifest, paths: manifest.__setitem__("saved_image_sha256", "0" * 64), "manifest_saved_image_sha256_mismatch"),
        (lambda manifest, paths: None, "generated_image_dimensions_mismatch"),
    ],
)
def test_identity_evidence_manifest_validation_failures_do_not_write_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator: object,
    expected_code: str,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")
    reference_path = tmp_path / "refs" / "lena_reference.png"
    _write_reference_authority(tmp_path, reference_path)
    saved_image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"
    other_image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / "other_seed.png"
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
    claim_path = approval.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval.receipt_output_path(DATE, SLOT_ID)
    state = {"provider_calls": 0}

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path, monkeypatch)
        ctx["claim_path"] = claim_path
        ctx["receipt_path"] = receipt_path
        ctx["manifest_path"] = manifest_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(date_str: str, slot_id: str, source: dict[str, object], custom_reference_id: str) -> dict[str, object]:
        state["provider_calls"] += 1
        size = (64, 64) if expected_code == "generated_image_dimensions_mismatch" else (1152, 2048)
        _write_image(saved_image_path, size=size)
        _write_image(other_image_path)
        return {
            "job_id": "job-123",
            "status": "processing",
            "result_urls": ["https://example.invalid/result.png"],
            "saved_image_path": str(saved_image_path),
            "image_format_detected": ".png",
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        }

    def fake_build_manifest(
        date_str: str,
        slot_id: str,
        source: dict[str, object],
        custom_reference_id: str,
        live_result: dict[str, object] | None,
        *,
        claim_repo_path: str | None = None,
        receipt_repo_path: str | None = None,
        saved_image_sha256: str | None = None,
    ) -> dict[str, object]:
        manifest: dict[str, object] = {
            "provider": "higgsfield",
            "date": date_str,
            "slot_id": slot_id,
            "saved_image_path": live_result.get("saved_image_path") if live_result else None,
            "image_format_detected": live_result.get("image_format_detected") if live_result else None,
            "claim_repo_path": claim_repo_path,
            "receipt_repo_path": receipt_repo_path,
            "saved_image_sha256": saved_image_sha256,
            "provider_status": "completed",
            "provider_job_id": live_result.get("job_id") if live_result else None,
            "job_type": "text2image_soul_v2",
            "custom_reference_id": custom_reference_id,
            "cli_soul_name": "Lena",
            "cli_soul_type": "soul_2",
            "prompt_sha256": "b" * 64,
        }
        mutator(manifest, {"other_image_path": other_image_path})
        return manifest

    monkeypatch.setattr(executor, "build_manifest", fake_build_manifest)

    with pytest.raises(wrapper.LiveGenerationAccountingError) as excinfo:
        wrapper.execute_approved_live_generation(
            handoff_path,
            approval_path,
            live=True,
            live_executor=fake_run_live,
            context_loader=fake_context_loader,
        )

    assert excinfo.value.code == expected_code
    assert state["provider_calls"] == 1
    assert claim_path.is_file()
    assert receipt_path.is_file()
    assert manifest_path.is_file()
    assert not (tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "identity_verification.json").exists()
    assert not wrapper.report_path(DATE, SLOT_ID).exists()


def test_failure_before_provider_submission_is_accounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")

    claim_path = approval.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval.receipt_output_path(DATE, SLOT_ID)

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path, monkeypatch)
        ctx["claim_path"] = claim_path
        ctx["receipt_path"] = receipt_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise executor.ProviderCallError(
            "provider never started",
            stage="pre_submission",
            subprocess_start_attempted=False,
            provider_submission_may_have_occurred=False,
        )

    report = wrapper.execute_approved_live_generation(
        handoff_path,
        approval_path,
        live=True,
        live_executor=fake_run_live,
        context_loader=fake_context_loader,
    )

    assert report["live_generation_accounting_status"] == "live_generation_failed_accounted"
    assert report["failure_stage"] == "pre_submission"
    assert report["provider_submission_may_have_occurred"] is False
    assert report["subprocess_start_attempted"] is False
    assert report["claim_written"] is True
    assert report["receipt_written"] is True
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["qa_disposition_required"] is True
    assert report["next_allowed_action"] == "review_live_generation_failure"
    assert report["side_effect_flags"]["provider_call_performed"] is False
    assert report["side_effect_flags"]["claims_written"] is True
    assert report["side_effect_flags"]["receipts_written"] is True
    assert report["side_effect_flags"]["publish_performed"] is False
    assert report["side_effect_flags"]["queue_mutated"] is False
    assert report["side_effect_flags"]["qa_run"] is False
    assert report["side_effect_flags"]["retry_executed"] is False
    assert claim_path.is_file()
    assert receipt_path.is_file()
    assert wrapper.report_path(DATE, SLOT_ID).is_file()


def test_success_without_reference_authority_does_not_write_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")

    saved_image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
    claim_path = approval.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval.receipt_output_path(DATE, SLOT_ID)

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path, monkeypatch)
        ctx["claim_path"] = claim_path
        ctx["receipt_path"] = receipt_path
        ctx["manifest_path"] = manifest_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(date_str: str, slot_id: str, source: dict[str, object], custom_reference_id: str) -> dict[str, object]:
        _write_image(saved_image_path)
        return {
            "job_id": "job-123",
            "status": "processing",
            "result_urls": ["https://example.invalid/result.png"],
            "saved_image_path": str(saved_image_path),
            "image_format_detected": ".png",
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        }

    def fake_build_manifest(
        date_str: str,
        slot_id: str,
        source: dict[str, object],
        custom_reference_id: str,
        live_result: dict[str, object] | None,
        *,
        claim_repo_path: str | None = None,
        receipt_repo_path: str | None = None,
        saved_image_sha256: str | None = None,
    ) -> dict[str, object]:
        return {
            "provider": "higgsfield",
            "date": date_str,
            "slot_id": slot_id,
            "saved_image_path": live_result.get("saved_image_path") if live_result else None,
            "image_format_detected": live_result.get("image_format_detected") if live_result else None,
            "claim_repo_path": claim_repo_path,
            "receipt_repo_path": receipt_repo_path,
            "saved_image_sha256": saved_image_sha256,
            "provider_status": "completed",
            "provider_job_id": live_result.get("job_id") if live_result else None,
            "job_type": "text2image_soul_v2",
            "custom_reference_id": custom_reference_id,
            "cli_soul_name": "Lena",
            "cli_soul_type": "soul_2",
            "prompt_sha256": "b" * 64,
        }

    monkeypatch.setattr(executor, "build_manifest", fake_build_manifest)

    with pytest.raises(wrapper.LiveGenerationAccountingError) as excinfo:
        wrapper.execute_approved_live_generation(
            handoff_path,
            approval_path,
            live=True,
            live_executor=fake_run_live,
            context_loader=fake_context_loader,
        )

    assert excinfo.value.code == "reference_authority_missing_or_invalid"
    assert not wrapper.report_path(DATE, SLOT_ID).exists()
    assert not (tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "identity_verification.json").exists()


def test_failure_after_provider_submission_is_accounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")

    claim_path = approval.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval.receipt_output_path(DATE, SLOT_ID)

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path, monkeypatch)
        ctx["claim_path"] = claim_path
        ctx["receipt_path"] = receipt_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise executor.ProviderCallError(
            "provider may have received the request",
            stage="post_submission",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id="job-789",
            provider_status="running",
            output_path=str(tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"),
            image_format_detected=".png",
        )

    report = wrapper.execute_approved_live_generation(
        handoff_path,
        approval_path,
        live=True,
        live_executor=fake_run_live,
        context_loader=fake_context_loader,
    )

    assert report["live_generation_accounting_status"] == "live_generation_failed_accounted"
    assert report["failure_stage"] == "post_submission"
    assert report["provider_submission_may_have_occurred"] is True
    assert report["subprocess_start_attempted"] is True
    assert report["claim_written"] is True
    assert report["receipt_written"] is True
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["qa_disposition_required"] is True
    assert report["next_allowed_action"] == "review_live_generation_failure"
    assert report["side_effect_flags"]["provider_call_performed"] is True
    assert report["side_effect_flags"]["claims_written"] is True
    assert report["side_effect_flags"]["receipts_written"] is True
    assert report["side_effect_flags"]["publish_performed"] is False
    assert report["side_effect_flags"]["queue_mutated"] is False
    assert report["side_effect_flags"]["qa_run"] is False
    assert report["side_effect_flags"]["retry_executed"] is False
    assert claim_path.is_file()
    assert receipt_path.is_file()
    assert wrapper.report_path(DATE, SLOT_ID).is_file()


def test_failure_when_receipt_write_itself_fails_is_accounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")

    claim_path = approval.claim_output_path(DATE, SLOT_ID)

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path, monkeypatch)
        ctx["claim_path"] = claim_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise executor.ProviderCallError(
            "provider may have received the request",
            stage="post_submission",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id="job-789",
            provider_status="running",
            output_path=str(tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"),
            image_format_detected=".png",
        )

    def failing_receipt_writer(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("receipt disk write failed")

    monkeypatch.setattr(executor, "_write_generation_execution_receipt", failing_receipt_writer)

    report = wrapper.execute_approved_live_generation(
        handoff_path,
        approval_path,
        live=True,
        live_executor=fake_run_live,
        context_loader=fake_context_loader,
    )

    assert report["live_generation_accounting_status"] == "live_generation_failed_accounted"
    assert report["failure_stage"] == "post_submission"
    assert report["provider_submission_may_have_occurred"] is True
    assert report["claim_written"] is True
    assert report["receipt_written"] is False
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["qa_disposition_required"] is True
    assert report["next_allowed_action"] == "review_live_generation_failure"
    assert "receipt write failed" in report["failure_error_text"]
    assert report["side_effect_flags"]["provider_call_performed"] is True
    assert report["side_effect_flags"]["claims_written"] is True
    assert report["side_effect_flags"]["receipts_written"] is False
    assert report["side_effect_flags"]["publish_performed"] is False
    assert report["side_effect_flags"]["queue_mutated"] is False
    assert report["side_effect_flags"]["qa_run"] is False
    assert report["side_effect_flags"]["retry_executed"] is False
    assert claim_path.is_file()
    assert not approval.receipt_output_path(DATE, SLOT_ID).is_file()
    assert wrapper.report_path(DATE, SLOT_ID).is_file()


def test_wrapper_source_does_not_import_publish_queue_qa_or_retry_helpers() -> None:
    source = Path(wrapper.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("publish" in module for module in imported_modules)
    assert not any("queue" in module for module in imported_modules)
    assert not any("qa" in module for module in imported_modules)
    assert not any("retry" in module for module in imported_modules)
