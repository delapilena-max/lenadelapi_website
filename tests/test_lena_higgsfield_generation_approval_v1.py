from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tools.lena_higgsfield_generation_approval_v1 as approval_mod
from tools.lena_higgsfield_generation_approval_v1 import (
    APPROVAL_TTL_MINUTES,
    CANONICAL_OPERATOR_ID,
    HiggsfieldGenerationApprovalError,
    build_generation_claim_record,
    build_generation_execution_receipt_record,
    build_generation_approval_record,
    claim_output_path,
    confirmation_phrase,
    inspect_handoff_artifact,
    receipt_output_path,
    validate_generation_approval_artifact,
    write_generation_claim_atomic,
    write_approval_record_atomic,
    write_generation_execution_receipt_atomic,
)

DATE = "2026-07-14"
SLOT_ID = "readypack0709-pack003-08-photo-approval-test"
PROMPT_SHA = hashlib.sha256(b"synthetic-approved-prompt-bytes").hexdigest()
CANDIDATE_ARTIFACT_SHA = hashlib.sha256(b"synthetic-candidate-artifact-bytes").hexdigest()
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"


def _patch_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        approval_mod, "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )


def _handoff_repo_path() -> str:
    return f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"


def _valid_handoff_report() -> dict:
    handoff_repo_path = _handoff_repo_path()
    return {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "created_at": "2026-07-14T12:00:00+00:00",
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
        "expected_handoff_artifact_path": handoff_repo_path,
        "selected_prompt_input": {
            "prompt_sha256": PROMPT_SHA,
        },
        "selected_prompt_input_artifact_sha256": CANDIDATE_ARTIFACT_SHA,
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
            "handoff_artifact_path": handoff_repo_path,
            "soul_metadata": {
                "name": "Lena",
                "type": "Soul 2.0",
                "custom_reference_id": CUSTOM_REFERENCE_ID,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_sha256": PROMPT_SHA,
        },
    }


def _write_handoff(tmp_path: Path, report: dict | None = None) -> Path:
    handoff_path = tmp_path / _handoff_repo_path()
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps(report or _valid_handoff_report(), indent=2), encoding="utf-8")
    return handoff_path


def _record_and_write(
    tmp_path: Path,
    handoff_path: Path,
    *,
    operator_id: str = CANONICAL_OPERATOR_ID,
    confirm: str | None = None,
    approved_at: datetime | None = None,
) -> Path:
    handoff_facts = inspect_handoff_artifact(handoff_path)
    confirmation = confirm if confirm is not None else confirmation_phrase(SLOT_ID)
    record = build_generation_approval_record(
        handoff_facts, operator_id=operator_id, confirmation=confirmation, approved_at=approved_at,
    )
    out_path = approval_mod.approval_output_path(DATE, SLOT_ID)
    write_approval_record_atomic(out_path, record)
    return out_path


# --- inspect_handoff_artifact -------------------------------------------------

def test_inspect_handoff_artifact_extracts_expected_facts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    facts = inspect_handoff_artifact(handoff_path)
    assert facts["date"] == DATE
    assert facts["slot_id"] == SLOT_ID
    assert facts["prompt_sha256"] == PROMPT_SHA
    assert facts["custom_reference_id"] == CUSTOM_REFERENCE_ID
    assert facts["handoff_repo_path"] == _handoff_repo_path()


# --- build + validate round trip ---------------------------------------------

def test_build_and_validate_round_trip_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)

    result = validate_generation_approval_artifact(approval_path, now=datetime.now(timezone.utc))
    assert result["is_expired"] is False
    assert result["scope_summary"]["authorized_attempts"] == 1
    assert result["scope_summary"]["upload_authorized"] is False
    assert result["scope_summary"]["queue_promotion_authorized"] is False
    assert result["scope_summary"]["publish_authorized"] is False
    assert result["scope_summary"]["analytics_mutation_authorized"] is False
    assert result["handoff_facts"]["slot_id"] == SLOT_ID


def test_generation_claim_binds_exact_identity_and_expected_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval_result = validate_generation_approval_artifact(approval_path)

    claim = build_generation_claim_record(approval_result)

    assert claim["report_type"] == "lena_higgsfield_generation_claim"
    assert claim["claim_type"] == "higgsfield_single_generation_consumption_claim"
    assert claim["approval_artifact_path"].endswith("_higgsfield_generation_approval.json")
    assert claim["handoff_artifact_path"] == _handoff_repo_path()
    assert claim["date"] == DATE
    assert claim["slot_id"] == SLOT_ID
    assert claim["prompt_sha256"] == PROMPT_SHA
    assert claim["operator_id"] == CANONICAL_OPERATOR_ID
    assert claim["provider"] == "Higgsfield"
    assert claim["executor"] == "Higgsfield CLI repo adapter"
    assert claim["model"] == "text2image_soul_v2"
    assert claim["aspect_ratio"] == "9:16"
    assert claim["custom_reference_id"] == CUSTOM_REFERENCE_ID
    assert claim["authorized_attempts"] == 1
    assert claim["consumed_attempt_number"] == 1
    assert claim["expected_manifest_path"] == f"pipeline/higgsfield_debug/{DATE}/{SLOT_ID}/result_manifest.json"
    assert claim["expected_output_directory"] == f"pipeline/higgsfield_library/lena/{DATE}"
    assert claim["expected_output_stem"] == f"{SLOT_ID}_seed"
    assert claim["allowed_output_extensions"] == [".png", ".jpg", ".webp", ".bin"]
    assert claim["state"] == "claimed_pending_receipt"
    assert claim["upload_authorized"] is False
    assert claim["queue_promotion_authorized"] is False
    assert claim["publish_authorized"] is False
    assert claim["analytics_mutation_authorized"] is False


def test_generation_execution_receipt_binds_claim_and_failure_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval_result = validate_generation_approval_artifact(approval_path)
    claim_path = claim_output_path(DATE, SLOT_ID)
    write_generation_claim_atomic(claim_path, build_generation_claim_record(approval_result))

    receipt = build_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome="execution_failed",
        failure_stage="provider_output_parse_failure",
        error_text="sanitized failure",
        subprocess_start_attempted=True,
        provider_submission_may_have_occurred=True,
        provider_job_id="job-123",
        provider_status="processing",
        output_path=None,
        image_format_detected=None,
        actual_manifest_path=None,
    )

    assert receipt["report_type"] == "lena_higgsfield_generation_execution_receipt"
    assert receipt["receipt_type"] == "higgsfield_single_generation_execution_receipt"
    assert receipt["claim_artifact_path"].endswith("_higgsfield_generation_claim.json")
    assert receipt["approval_artifact_path"].endswith("_higgsfield_generation_approval.json")
    assert receipt["handoff_artifact_path"] == _handoff_repo_path()
    assert receipt["date"] == DATE
    assert receipt["slot_id"] == SLOT_ID
    assert receipt["prompt_sha256"] == PROMPT_SHA
    assert receipt["outcome"] == "execution_failed"
    assert receipt["failure_stage"] == "provider_output_parse_failure"
    assert receipt["error_text"] == "sanitized failure"
    assert receipt["subprocess_start_attempted"] is True
    assert receipt["provider_submission_may_have_occurred"] is True
    assert receipt["provider_job_id"] == "job-123"
    assert receipt["provider_status"] == "processing"
    assert receipt["expected_manifest_path"] == f"pipeline/higgsfield_debug/{DATE}/{SLOT_ID}/result_manifest.json"
    assert receipt["actual_manifest_path"] is None
    assert receipt["upload_authorized"] is False
    assert receipt["queue_promotion_authorized"] is False
    assert receipt["publish_authorized"] is False
    assert receipt["analytics_mutation_authorized"] is False


def test_confirmation_phrase_names_slot_and_credit_acknowledgement() -> None:
    phrase = confirmation_phrase(SLOT_ID)
    assert SLOT_ID in phrase
    assert "credits" in phrase.lower()


# --- wrong operator ------------------------------------------------------------

def test_build_rejects_wrong_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        _record_and_write(tmp_path, handoff_path, operator_id="someone_else")
    assert excinfo.value.code == "approval_operator_mismatch"


def test_validate_rejects_approval_tampered_to_wrong_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["operator_id"] = "someone_else"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_operator_mismatch"


# --- wrong confirmation ---------------------------------------------------------

def test_build_rejects_wrong_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        _record_and_write(tmp_path, handoff_path, confirm="I approve this, basically")
    assert excinfo.value.code == "approval_confirmation_mismatch"


def test_validate_rejects_approval_tampered_to_wrong_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["confirmation_statement"] = "close enough"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_confirmation_mismatch"


# --- expiry ----------------------------------------------------------------------

def test_validate_rejects_expired_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approved_at = datetime.now(timezone.utc) - timedelta(minutes=APPROVAL_TTL_MINUTES + 1)
    approval_path = _record_and_write(tmp_path, handoff_path, approved_at=approved_at)

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_expired"


def test_validate_accepts_approval_still_within_ttl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approved_at = datetime.now(timezone.utc) - timedelta(minutes=APPROVAL_TTL_MINUTES - 1)
    approval_path = _record_and_write(tmp_path, handoff_path, approved_at=approved_at)

    result = validate_generation_approval_artifact(approval_path)
    assert result["is_expired"] is False


def test_validate_expired_can_still_be_inspected_when_not_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approved_at = datetime.now(timezone.utc) - timedelta(minutes=APPROVAL_TTL_MINUTES + 5)
    approval_path = _record_and_write(tmp_path, handoff_path, approved_at=approved_at)

    result = validate_generation_approval_artifact(approval_path, require_not_expired=False)
    assert result["is_expired"] is True


def test_validate_rejects_non_standard_expiry_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approved_at = datetime.fromisoformat(approval["approved_at_utc"])
    approval["expires_at_utc"] = (approved_at + timedelta(minutes=45)).isoformat()
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_expiry_window_invalid"


# --- handoff/prompt/slot/date hash binding ----------------------------------------

def test_validate_rejects_stale_handoff_sha_after_handoff_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)

    report = json.loads(handoff_path.read_text(encoding="utf-8"))
    report["created_at"] = "2026-07-14T13:00:00+00:00"
    handoff_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_handoff_sha_mismatch"


def test_validate_rejects_wrong_slot_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["slot_id"] = "some-other-slot"
    # The required confirmation phrase is itself slot-bound; update it too so
    # this test isolates the slot/handoff binding check, not the (separately
    # tested) confirmation-mismatch check.
    approval["confirmation_statement"] = confirmation_phrase("some-other-slot")
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_slot_binding_mismatch"


def test_validate_rejects_wrong_date_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["date"] = "2026-07-01"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_date_binding_mismatch"


def test_validate_rejects_wrong_prompt_sha_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["prompt_sha256"] = hashlib.sha256(b"a-different-prompt").hexdigest()
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_prompt_sha_mismatch"


def test_validate_rejects_malformed_prompt_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["prompt_sha256"] = "NOT-A-SHA"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_prompt_sha_missing_or_invalid"


# --- provider / model / aspect / soul -----------------------------------------

@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("provider", "kling", "approval_provider_mismatch"),
        ("model", "text2image_v1", "approval_model_mismatch"),
        ("aspect_ratio", "1:1", "approval_aspect_ratio_mismatch"),
        ("soul_name", "Not Lena", "approval_soul_name_mismatch"),
        ("soul_type", "Soul 1.0", "approval_soul_type_mismatch"),
        ("executor", "some other executor", "approval_executor_mismatch"),
    ],
)
def test_validate_rejects_provider_model_aspect_soul_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str, expected_code: str
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval[field] = value
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == expected_code


def test_validate_rejects_custom_reference_id_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["custom_reference_id"] = "wrong-reference-id"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_custom_reference_id_mismatch"


# --- prohibited authorization flags -------------------------------------------

@pytest.mark.parametrize(
    "field",
    [
        "upload_authorized",
        "queue_promotion_authorized",
        "publish_authorized",
        "analytics_mutation_authorized",
    ],
)
def test_validate_rejects_prohibited_authorization_flag_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval[field] = True
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == f"approval_scope_{field}_invalid"


def test_build_never_sets_any_prohibited_authorization_flag_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    for field in (
        "upload_authorized", "queue_promotion_authorized",
        "publish_authorized", "analytics_mutation_authorized",
    ):
        assert approval[field] is False


def test_validate_rejects_authorized_attempts_other_than_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["authorized_attempts"] = 2
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_authorized_attempts_invalid"


def test_validate_rejects_missing_credits_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["credits_may_be_spent_acknowledged"] = False
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "approval_credits_acknowledgement_missing"


# --- overwrite / atomic write --------------------------------------------------

def test_write_approval_record_atomic_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    assert approval_path.is_file()

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        _record_and_write(tmp_path, handoff_path)
    assert excinfo.value.code == "approval_already_exists"


def test_write_approval_record_atomic_leaves_no_tmp_file_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    leftovers = list(approval_path.parent.glob("*.tmp"))
    assert leftovers == []


def test_write_generation_claim_atomic_allows_exactly_one_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval_result = validate_generation_approval_artifact(approval_path)
    claim_record = build_generation_claim_record(approval_result)
    out_path = claim_output_path(DATE, SLOT_ID)
    results: list[str] = []

    def _attempt() -> None:
        try:
            write_generation_claim_atomic(out_path, claim_record)
            results.append("claimed")
        except HiggsfieldGenerationApprovalError as exc:
            results.append(exc.code)

    thread_a = threading.Thread(target=_attempt)
    thread_b = threading.Thread(target=_attempt)
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert results.count("claimed") == 1
    assert results.count("generation_claim_already_exists") == 1
    assert out_path.is_file()
    assert list(out_path.parent.glob("*.tmp")) == []


def test_write_generation_execution_receipt_atomic_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    approval_result = validate_generation_approval_artifact(approval_path)
    claim_path = claim_output_path(DATE, SLOT_ID)
    write_generation_claim_atomic(claim_path, build_generation_claim_record(approval_result))
    receipt_path = receipt_output_path(DATE, SLOT_ID)
    receipt_record = build_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome="success",
        failure_stage=None,
        error_text=None,
        subprocess_start_attempted=True,
        provider_submission_may_have_occurred=True,
        provider_job_id="job-123",
        provider_status="completed",
        output_path="C:/fake/path.png",
        image_format_detected=".png",
        actual_manifest_path=f"pipeline/higgsfield_debug/{DATE}/{SLOT_ID}/result_manifest.json",
    )
    write_generation_execution_receipt_atomic(receipt_path, receipt_record)

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        write_generation_execution_receipt_atomic(receipt_path, receipt_record)
    assert excinfo.value.code == "generation_execution_receipt_already_exists"


# --- fail-closed handoff-side gates (reused invariants) -----------------------

@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda report: report.__setitem__("live_execution_authorized", True), "handoff_live_authorization_invalid"),
        (lambda report: report.__setitem__("generation_performed", True), "handoff_generation_performed_invalid"),
        (lambda report: report["structured_executor_inputs"].__setitem__("negative_prompt_enabled", True), "handoff_negative_prompt_invalid"),
        (lambda report: report["structured_executor_inputs"]["soul_metadata"].__setitem__("identity_is_prompt_instruction", True), "handoff_soul_identity_mode_invalid"),
    ],
)
def test_inspect_handoff_artifact_fails_closed_on_unsafe_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str
) -> None:
    _patch_root(tmp_path, monkeypatch)
    report = _valid_handoff_report()
    mutator(report)
    handoff_path = _write_handoff(tmp_path, report)

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        inspect_handoff_artifact(handoff_path)
    assert excinfo.value.code == expected_code
