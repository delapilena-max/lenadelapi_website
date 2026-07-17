from __future__ import annotations

import hashlib
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tools.lena_higgsfield_generation_approval_v1 as canonical_approval
import tools.lena_higgsfield_retry_generation_approval_v1 as retry_approval
import tools.lena_record_higgsfield_retry_generation_approval_v1 as record_tool
from tools.lena_higgsfield_retry_generation_approval_v1 import (
    APPROVAL_TTL_MINUTES,
    HiggsfieldRetryGenerationApprovalError,
    approval_output_path,
    build_retry_generation_approval_record,
    build_retry_generation_claim_record,
    build_retry_generation_execution_receipt_record,
    claim_output_path,
    confirmation_phrase,
    inspect_retry_handoff_artifact,
    receipt_output_path,
    validate_retry_generation_approval_artifact,
    write_retry_generation_approval_record_atomic,
    write_retry_generation_claim_atomic,
    write_retry_generation_execution_receipt_atomic,
)
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_mod


DATE = "2026-07-14"
ORIGINAL_SLOT = "higgsfield-20260714-hcr_011-photo"
RETRY_SLOT = "higgsfield-20260714-hcr_011-retry01-photo"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
PROOF_PACKET_PATH = Path("pipeline/strategy/lena/content_packets/2026-07-17/lena_content_packet_dryrun_2026-07-17_hcr_011.json")
ORIGINAL_PROMPT = json.loads(PROOF_PACKET_PATH.read_text(encoding="utf-8"))["compact_provider_prompt_preview"]
PROMPT_SHA = hashlib.sha256(ORIGINAL_PROMPT.encode("utf-8")).hexdigest()


def _patch_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canonical_approval, "ROOT", tmp_path)
    monkeypatch.setattr(
        canonical_approval,
        "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(retry_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        retry_mod,
        "DEFAULT_OUTPUT_ROOT",
        tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs",
    )
    monkeypatch.setattr(retry_approval, "ROOT", tmp_path)
    monkeypatch.setattr(
        retry_approval,
        "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(record_tool, "ROOT", tmp_path)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _seed_bound_retry_source(tmp_path: Path) -> dict[str, Path]:
    handoff_repo_path = Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_next_live_image_handoff_{DATE}.json"
    packet_repo_path = Path("pipeline/strategy/lena/content_packets") / DATE / f"lena_content_packet_dryrun_{DATE}_hcr_011.json"
    handoff_path = tmp_path / handoff_repo_path
    packet_path = tmp_path / packet_repo_path
    packet_report = {
        "report_type": "lena_content_packet_dryrun",
        "generated_date": DATE,
        "recipe_id": "hcr_011",
        "compact_provider_prompt_preview": ORIGINAL_PROMPT,
        "compact_provider_prompt_sha256": PROMPT_SHA,
        "compact_provider_prompt_budget": 2499,
        "provider_prompt_contract": {"provider_route": "higgsfield_forward_no_live", "live_authority": False},
    }
    _write_json(packet_path, packet_report)
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    handoff_report = {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "created_at": "2026-07-15T05:00:00+00:00",
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
        "selected_slot_id": ORIGINAL_SLOT,
        "expected_handoff_artifact_path": handoff_repo_path.as_posix(),
        "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
        "selected_prompt_input_artifact_sha256": packet_sha,
        "selected_prompt_input": {"prompt_sha256": PROMPT_SHA, "prompt_text": ORIGINAL_PROMPT},
        "structured_executor_inputs": {
            "provider": "higgsfield",
            "executor_type": "higgsfield_cli",
            "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
            "model": "text2image_soul_v2",
            "aspect_ratio": "9:16",
            "negative_prompt_enabled": False,
            "live_execution_authorized": False,
            "date": DATE,
            "slot_id": ORIGINAL_SLOT,
            "handoff_artifact_path": handoff_repo_path.as_posix(),
            "soul_metadata": {
                "name": "Lena",
                "type": "Soul 2.0",
                "custom_reference_id": CUSTOM_REFERENCE_ID,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_sha256": PROMPT_SHA,
            "selected_prompt_text": ORIGINAL_PROMPT,
        },
    }
    _write_json(handoff_path, handoff_report)
    handoff_sha = hashlib.sha256(handoff_path.read_bytes()).hexdigest()

    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{ORIGINAL_SLOT}_seed.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nretry-proof-image")

    manifest_repo_path = Path("pipeline/higgsfield_debug") / DATE / ORIGINAL_SLOT / "result_manifest.json"
    manifest_path = tmp_path / manifest_repo_path
    manifest_report = {
        "provider": "higgsfield",
        "slot_id": ORIGINAL_SLOT,
        "prompt_sha256": PROMPT_SHA,
        "saved_image_path": str(image_path),
        "provider_job_id": "job-123",
        "provider_status": "completed",
    }
    _write_json(manifest_path, manifest_report)

    receipt_repo_path = Path("pipeline/approvals/lena/generation") / DATE / f"{ORIGINAL_SLOT}_higgsfield_generation_execution_receipt.json"
    receipt_path = tmp_path / receipt_repo_path
    receipt_report = {
        "report_type": "lena_higgsfield_generation_execution_receipt",
        "schema_version": "v1",
        "receipt_type": "higgsfield_single_generation_execution_receipt",
        "handoff_artifact_path": handoff_repo_path.as_posix(),
        "handoff_artifact_sha256": handoff_sha,
        "date": DATE,
        "slot_id": ORIGINAL_SLOT,
        "prompt_sha256": PROMPT_SHA,
        "outcome": "success",
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "provider_submission_may_have_occurred": True,
        "subprocess_start_attempted": True,
        "output_path": str(image_path),
        "actual_manifest_path": manifest_repo_path.as_posix(),
        "provider": "Higgsfield",
        "executor": "Higgsfield CLI repo adapter",
        "model": "text2image_soul_v2",
        "aspect_ratio": "9:16",
        "custom_reference_id": CUSTOM_REFERENCE_ID,
    }
    _write_json(receipt_path, receipt_report)

    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=handoff_path,
        execution_receipt=receipt_path,
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=True,
    )
    retry_handoff_path = Path(report["retry_handoff_artifact_path"])
    return {
        "handoff_path": handoff_path,
        "receipt_path": receipt_path,
        "packet_path": packet_path,
        "manifest_path": manifest_path,
        "image_path": image_path,
        "retry_handoff_path": retry_handoff_path,
    }


def _record_retry_approval(
    retry_handoff_path: Path,
    *,
    operator_id: str = canonical_approval.CANONICAL_OPERATOR_ID,
    confirm: str | None = None,
    approved_at: datetime | None = None,
) -> Path:
    retry_facts = inspect_retry_handoff_artifact(retry_handoff_path)
    record = build_retry_generation_approval_record(
        retry_facts,
        operator_id=operator_id,
        confirmation=confirm if confirm is not None else confirmation_phrase(RETRY_SLOT),
        approved_at=approved_at,
    )
    out_path = approval_output_path(DATE, RETRY_SLOT)
    write_retry_generation_approval_record_atomic(out_path, record)
    return out_path


def _run_record_tool(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["record_tool", *args])
    return record_tool.main()


def test_valid_retry_approval_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    approval_path = _record_retry_approval(seeded["retry_handoff_path"])
    retry_facts = inspect_retry_handoff_artifact(seeded["retry_handoff_path"])

    result = validate_retry_generation_approval_artifact(approval_path)
    assert result["is_expired"] is False
    assert result["retry_facts"]["slot_id"] == RETRY_SLOT
    assert result["retry_facts"]["prompt_sha256"] == retry_facts["prompt_sha256"]
    assert result["scope_summary"]["authorized_attempts"] == 1
    assert result["scope_summary"]["upload_authorized"] is False
    assert result["scope_summary"]["queue_promotion_authorized"] is False
    assert result["scope_summary"]["publish_authorized"] is False
    assert result["scope_summary"]["scheduling_authorized"] is False
    assert result["scope_summary"]["analytics_mutation_authorized"] is False


def test_retry_recording_tool_writes_scoped_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)

    code = _run_record_tool(
        monkeypatch,
        "--retry-handoff-artifact", str(seeded["retry_handoff_path"]),
        "--operator-id", "nicolas",
        "--confirm", confirmation_phrase(RETRY_SLOT),
    )
    assert code == 0
    expected = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{RETRY_SLOT}_higgsfield_retry_generation_approval.json"
    assert expected.is_file()
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] is True
    assert stdout["files_written_this_run"] == [str(expected)]


def test_retry_approval_rejects_wrong_slot_prompt_or_retry_handoff_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    approval_path = _record_retry_approval(seeded["retry_handoff_path"])
    approval = json.loads(approval_path.read_text(encoding="utf-8"))

    approval["slot_id"] = "wrong-slot"
    approval["confirmation_statement"] = confirmation_phrase("wrong-slot")
    approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(HiggsfieldRetryGenerationApprovalError) as excinfo:
        validate_retry_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_slot_binding_mismatch"

    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["slot_id"] = RETRY_SLOT
    approval["confirmation_statement"] = confirmation_phrase(RETRY_SLOT)
    approval["prompt_sha256"] = hashlib.sha256(b"wrong").hexdigest()
    approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(HiggsfieldRetryGenerationApprovalError) as excinfo:
        validate_retry_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_prompt_sha_mismatch"

    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["prompt_sha256"] = inspect_retry_handoff_artifact(seeded["retry_handoff_path"])["prompt_sha256"]
    approval["retry_handoff_artifact_sha256"] = "0" * 64
    approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(HiggsfieldRetryGenerationApprovalError) as excinfo:
        validate_retry_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_retry_handoff_sha_mismatch"


def test_retry_approval_fails_closed_on_broken_original_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    approval_path = _record_retry_approval(seeded["retry_handoff_path"])
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["provider_status"] = "tampered"
    seeded["receipt_path"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(HiggsfieldRetryGenerationApprovalError) as excinfo:
        validate_retry_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "receipt_sha_mismatch"


def test_retry_approval_expiry_and_single_use_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    approval_path = _record_retry_approval(
        seeded["retry_handoff_path"],
        approved_at=datetime.now(timezone.utc) - timedelta(minutes=APPROVAL_TTL_MINUTES + 1),
    )
    with pytest.raises(HiggsfieldRetryGenerationApprovalError) as excinfo:
        validate_retry_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_expired"

    approval_path.unlink()
    approval_path = _record_retry_approval(seeded["retry_handoff_path"])
    approval_result = validate_retry_generation_approval_artifact(approval_path)
    claim_record = build_retry_generation_claim_record(approval_result)
    claim_path = claim_output_path(DATE, RETRY_SLOT)
    results: list[str] = []

    def _attempt() -> None:
        try:
            write_retry_generation_claim_atomic(claim_path, claim_record)
            results.append("claimed")
        except HiggsfieldRetryGenerationApprovalError as exc:
            results.append(exc.code)

    thread_a = threading.Thread(target=_attempt)
    thread_b = threading.Thread(target=_attempt)
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert results.count("claimed") == 1
    assert results.count("retry_generation_claim_already_exists") == 1


def test_retry_execution_receipt_binds_flags_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    approval_path = _record_retry_approval(seeded["retry_handoff_path"])
    approval_result = validate_retry_generation_approval_artifact(approval_path)
    claim_path = claim_output_path(DATE, RETRY_SLOT)
    write_retry_generation_claim_atomic(claim_path, build_retry_generation_claim_record(approval_result))

    receipt = build_retry_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome="execution_failed",
        failure_stage="provider_rejection",
        error_text="sanitized failure",
        subprocess_start_attempted=True,
        provider_submission_may_have_occurred=True,
        provider_job_id="job-123",
        provider_status="processing",
        output_path=None,
        image_format_detected=None,
        actual_manifest_path=None,
    )
    receipt_path = receipt_output_path(DATE, RETRY_SLOT)
    write_retry_generation_execution_receipt_atomic(receipt_path, receipt)
    assert receipt["publish_authorized"] is False
    assert receipt["queue_promotion_authorized"] is False
    assert receipt["upload_authorized"] is False
    assert receipt["scheduling_authorized"] is False
    assert receipt["analytics_mutation_authorized"] is False
