from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import tools.strategy.lena_execute_approved_live_generation_v1 as wrapper
import tools.lena_higgsfield_generation_approval_v1 as approval


DATE = "2026-07-15"
SLOT_ID = "higgsfield-20260715-hcr_011-photo"
RECIPE_ID = "hcr_011"


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wrapper, "ROOT", tmp_path)
    monkeypatch.setattr(wrapper, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")


def _touch(path: Path, payload: str = "{}\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _approval_result(tmp_path: Path) -> dict:
    handoff_repo_path = f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"
    approval_repo_path = f"pipeline/approvals/lena/generation/{DATE}/{SLOT_ID}_higgsfield_generation_approval.json"
    claim_repo_path = f"pipeline/approvals/lena/generation/{DATE}/{SLOT_ID}_higgsfield_generation_claim.json"
    receipt_repo_path = f"pipeline/approvals/lena/generation/{DATE}/{SLOT_ID}_higgsfield_generation_execution_receipt.json"
    approval_record = {
        "report_type": "lena_higgsfield_generation_approval",
        "schema_version": "v1",
        "approval_type": "higgsfield_single_generation",
        "operator_id": "nicolas",
        "approved_at_utc": "2026-07-15T12:00:00+00:00",
        "expires_at_utc": "2026-07-15T12:30:00+00:00",
        "handoff_artifact_path": handoff_repo_path,
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
        "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
        "confirmation_statement": approval.confirmation_phrase(SLOT_ID),
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }
    return {
        "approval": approval_record,
        "approval_path": tmp_path / approval_repo_path,
        "approval_repo_path": approval_repo_path,
        "approval_sha256": "c" * 64,
        "handoff_facts": {
            "date": DATE,
            "slot_id": SLOT_ID,
            "handoff_repo_path": handoff_repo_path,
            "handoff_sha256": "a" * 64,
            "prompt_sha256": "b" * 64,
            "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
            "soul_name": "Lena",
            "soul_type": "Soul 2.0",
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
        "claim_path": tmp_path / claim_repo_path,
        "receipt_path": tmp_path / receipt_repo_path,
    }


def _context_loader(tmp_path: Path) -> dict[str, object]:
    approval_result = _approval_result(tmp_path)
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
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
        "handoff_artifact": approval_result["approval_path"].parent.parent.parent / "strategy" / "lena" / "next_actions" / DATE / f"lena_next_live_image_handoff_{DATE}.json",
        "approval_artifact": approval_result["approval_path"],
        "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
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


def test_dry_run_reports_no_publish_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")
    report = wrapper.execute_approved_live_generation(
        handoff_path,
        approval_path,
        live=False,
        context_loader=lambda *_args: _context_loader(tmp_path),
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


def test_mocked_live_execution_writes_accounting_report_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    handoff_path = _touch(tmp_path / "handoff.json")
    approval_path = _touch(tmp_path / "approval.json")

    saved_image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
    claim_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_claim.json"
    receipt_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_execution_receipt.json"

    def fake_context_loader(*_args: object) -> dict[str, object]:
        ctx = _context_loader(tmp_path)
        ctx["claim_path"] = claim_path
        ctx["receipt_path"] = receipt_path
        ctx["manifest_path"] = manifest_path
        ctx["approval_artifact"] = approval_path
        ctx["handoff_artifact"] = handoff_path
        return ctx

    def fake_run_live(date_str: str, slot_id: str, source: dict[str, object], custom_reference_id: str) -> dict[str, object]:
        assert date_str == DATE
        assert slot_id == SLOT_ID
        assert custom_reference_id == "90a293d7-f3af-4377-8751-3304a27b6f31"
        return {
            "job_id": "job-123",
            "status": "processing",
            "result_urls": ["https://example.invalid/result.png"],
            "saved_image_path": str(saved_image_path),
            "image_format_detected": ".png",
            "subprocess_start_attempted": False,
            "provider_submission_may_have_occurred": False,
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
    ) -> dict[str, object]:
        return {
            "date": date_str,
            "slot_id": slot_id,
            "saved_image_path": live_result.get("saved_image_path") if live_result else None,
            "image_format_detected": live_result.get("image_format_detected") if live_result else None,
            "claim_repo_path": claim_repo_path,
            "receipt_repo_path": receipt_repo_path,
        }

    monkeypatch.setattr(wrapper, "build_manifest", fake_build_manifest)

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
    assert report["generation_claim_artifact"] == wrapper.repo_relative_path(claim_path)
    assert report["generation_receipt_artifact"] == wrapper.repo_relative_path(receipt_path)
    assert report["executor_result_manifest"] == wrapper.repo_relative_path(manifest_path)
    assert report["generated_output_paths"]["saved_image_path"] == wrapper.repo_relative_path(saved_image_path)
    assert report["generated_output_paths"]["manifest_path"] == wrapper.repo_relative_path(manifest_path)
    assert report["side_effect_flags"]["provider_call_performed"] is False
    assert report["side_effect_flags"]["generation_performed"] is True
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
    assert wrapper.report_path(DATE, SLOT_ID).is_file()
    assert json.loads(wrapper.report_path(DATE, SLOT_ID).read_text(encoding="utf-8")) == report


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
