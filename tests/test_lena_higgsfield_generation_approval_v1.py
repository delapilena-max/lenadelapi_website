from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tools.lena_higgsfield_generation_approval_v1 as approval_mod
import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff_builder
import tools.strategy.lena_reconciliation_contract_v1 as reconciliation_contract
from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits
from tests.fixtures import lena_pose_provenance as pose_fixture
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
PROMPT_TEXT = pose_fixture.canonical_prompt()
PROMPT_SHA = hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
CANDIDATE_ARTIFACT_SHA = hashlib.sha256(b"synthetic-candidate-artifact-bytes").hexdigest()
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
RECONCILIATION_PATH = f"pipeline/strategy/lena/reconciliations/{DATE}/lena_generation_reconciliation_fixture.json"


def _patch_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        approval_mod, "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(handoff_builder, "ROOT", tmp_path)
    monkeypatch.setattr(handoff_builder, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(handoff_builder, "CONTENT_PACKETS", tmp_path / "pipeline" / "strategy" / "lena" / "content_packets")
    monkeypatch.setattr(
        handoff_builder,
        "PRE_GENERATION_CANDIDATES",
        tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
    )
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_path)
    monkeypatch.setattr(
        handoff_builder.pose_provenance,
        "build_candidate_pose_provenance",
        pose_fixture.candidate_pose_provenance,
    )
    monkeypatch.setattr(
        handoff_builder.packet_builder,
        "rebuild_packet_from_authoritative_sources",
        lambda packet, pose_binding=None: pose_fixture.bind_packet(packet, pose_binding=pose_binding),
    )


def _handoff_repo_path() -> str:
    return f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"


def _selected_candidate_repo_path() -> str:
    return f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/lena_pre_generation_candidate_selected.json"


def _selected_candidate_payload() -> dict:
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": "b" * 40,
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_004",
            "slot_id": SLOT_ID,
            "lane": "readypack lane",
            "recipe_id": "hcr_011",
            "hook_id": "cbn_004",
            "prompt_sha256": PROMPT_SHA,
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {SLOT_ID}",
        },
        "decision_fingerprint_sha256": "c" * 64,
        "generated_at_utc": "2026-07-14T12:00:00Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    }


def _selected_candidate_sha() -> str:
    return hashlib.sha256(
        json.dumps(_selected_candidate_payload(), indent=2).replace("\n", os.linesep).encode("utf-8")
    ).hexdigest()


def _reconciliation_payload() -> dict:
    selected_candidate_repo_path = _selected_candidate_repo_path()
    selected_candidate_sha = _selected_candidate_sha()
    selected_candidate_payload = _selected_candidate_payload()
    return {
        "reconciliation": {
            "source_artifact_path": f"pipeline/strategy/lena/reconciliations/{DATE}/lena_generation_reconciliation_b0000000_dddddddddddd.json",
            "source_artifact_sha256": "d" * 64,
            "schema_version": "lena_generation_reconciliation_v1",
            "report_type": "lena_generation_reconciliation",
            "date": DATE,
            "reconciliation_status": "reconciled",
            "operator_review_required": False,
            "divergence_status": "aligned",
            "resolution_policy": "selected_candidate_authoritative",
            "exact_next_allowed_action": "build_next_live_image_handoff",
            "decision_required": False,
        },
        "reconciled_candidate": {
            "candidate_id": selected_candidate_payload["candidate"]["candidate_id"],
            "recipe_id": selected_candidate_payload["candidate"]["recipe_id"],
            "slot_id": selected_candidate_payload["candidate"]["slot_id"],
            "hook_id": selected_candidate_payload["candidate"]["hook_id"],
            "prompt_sha256": selected_candidate_payload["candidate"]["prompt_sha256"],
            "artifact_path": selected_candidate_repo_path,
            "artifact_sha256": selected_candidate_sha,
        },
    }


def _valid_handoff_report(tmp_path: Path) -> dict:
    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    packets = tmp_path / "pipeline" / "strategy" / "lena" / "content_packets" / DATE
    pre_generation = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    recommendations = next_actions / f"lena_next_generation_step_{DATE}.json"
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    packet_path = packets / f"lena_content_packet_dryrun_{DATE}_hcr_011.json"
    selected_candidate_path = pre_generation / "lena_pre_generation_candidate_selected.json"
    reconciliation_path = tmp_path / RECONCILIATION_PATH

    learning = {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": DATE,
        "published_post_count": 3,
        "pending_metrics_posts": [{}],
        "stale_pending_metrics_posts": [{}],
        "winner_posts": [{"recipe_id": "hcr_011"}],
        "queue_boosts": {"preferred_recipe_ids": ["hcr_011"]},
        "metrics_resolution_summary": {
            "learning_status": "current",
            "current_count": 2,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0,
        },
    }
    recommendation = {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_artifact_path": str(learning_path),
        "learning_status": "current",
        "learning_status_label": "learning_current",
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": 3,
        "learning_pending_metrics_count": 1,
        "learning_stale_pending_metrics_count": 1,
        "learning_resolution_state_summary": learning["metrics_resolution_summary"],
        "learning_required_follow_up_action": "no_follow_up_required",
        "learning_winner_post_count": 1,
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": "hcr_011",
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids", "winner_posts"],
            "next_live_gate": "review",
        },
    }
    queue = {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "dry_run": True,
        "proof_lane_lock": {
            "action_type": "collect_first_controlled_proof",
            "recipe_id": "hcr_011",
            "outfit_id": "wc_p059",
            "environment_id": "env_p001",
            "next_live_gate": "review",
        },
        "proof_lane_lock_active": True,
        "queue_slots": [
            {
                "recipe_id": "hcr_011",
                "title": "Parking Garage Flash",
                "scene_type": "parking_garage_flash",
                "autonomy_grade": "ready",
                "payload_headroom": 261,
                "outfit_used": "wc_p059",
                "environment_used": "env_p001",
                "proof_priority": 9,
                "production_proof_mode": False,
                "priority_score": 125,
                "why": ["matches current proof-lane lock from next-step recommendation"],
                "proof_lane_locked": True,
            }
        ],
    }
    prompt_text = PROMPT_TEXT
    prompt_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    packet = {
        "report_type": "lena_content_packet_dryrun",
        "schema_version": "v1",
        "packet_id": "cpkt_20260713_hcr_011",
        "generated_date": DATE,
        "generator": "lena_build_content_packet_dryrun_v1",
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "publishing_approval": "not_approved",
        "recipe_id": "hcr_011",
        "scene_type": "parking_garage_flash",
        "wardrobe_outfit_id": "wc_p059",
        "content_pillar": "beautiful_trouble",
        "platform_targets": ["Instagram Feed"],
        "best_content_type": "photo",
        "high_caliber_source_sections": {
            "subject_pose": "leaning against the elevator wall before heading up",
            "style_lighting": "warm lobby spill and realistic night shadow falloff",
            "technical_keywords": "35mm lens, natural grain",
        },
        "compact_provider_prompt_preview": prompt_text,
        "compact_provider_prompt_chars": len(prompt_text),
        "compact_provider_prompt_budget": prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS,
        "compact_provider_prompt_sha256": prompt_sha,
        "strong_hook_id": "cbn_004",
        "hook_text": "Tried To Dress Down. Failed.",
        "hook_selection_reason": "highest score",
        "caption_draft": "caught me on the way in",
        "caption_followup": "kept the first frame",
        "environment_id": "env_p001",
        "environment_context": "Environment: parking garage entry.",
        "provider_prompt_contract": {
            "provider_route": "higgsfield_forward_no_live",
            "live_authority": False,
            "scene_logic_contract_present": True,
            "master_identity_body_present": True,
            "blocked_terms_absent": True,
            "blocked_terms_found": [],
            "outfit_controlled": True,
            "environment_controlled": True,
        },
    }
    selected_candidate = _selected_candidate_payload()
    reconciliation = _reconciliation_payload()

    for path, payload in (
        (learning_path, learning),
        (recommendations, recommendation),
        (queue_path, queue),
        (packet_path, packet),
        (selected_candidate_path, selected_candidate),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    learning_sha256 = reconciliation_contract.sha256_file(learning_path)
    recommendation_sha256 = reconciliation_contract.sha256_file(recommendations)
    selected_sha256 = reconciliation_contract.sha256_file(selected_candidate_path)
    reconciliation_path.parent.mkdir(parents=True, exist_ok=True)
    reconciliation_path.write_text(
        json.dumps(
            {
                "report_type": "lena_generation_reconciliation",
                "schema_version": "lena_generation_reconciliation_v1",
                "date": DATE,
                "generated_at": "2026-07-14T12:00:00+00:00",
                "source_revision": "b0000000",
                "source_revision_commit": "b" * 40,
                "source_artifacts": {
                    "learning": {
                        "source_artifact_path": learning_path.relative_to(tmp_path).as_posix(),
                        "source_artifact_sha256": learning_sha256,
                    },
                    "recommendation": {
                        "source_artifact_path": recommendations.relative_to(tmp_path).as_posix(),
                        "source_artifact_sha256": recommendation_sha256,
                    },
                    "selected_candidate": {
                        "source_artifact_path": selected_candidate_path.relative_to(tmp_path).as_posix(),
                        "source_artifact_sha256": selected_sha256,
                    },
                },
                "learning_status": "current",
                "recommendation_recipe_id": "hcr_011",
                "recommendation_outfit_id": "wc_p059",
                "recommendation_environment_id": "env_p001",
                "recommendation_action_type": "collect_first_controlled_proof",
                "selected_candidate_id": selected_candidate["candidate"]["candidate_id"],
                "selected_candidate_recipe_id": selected_candidate["candidate"]["recipe_id"],
                "selected_candidate_slot_id": selected_candidate["candidate"]["slot_id"],
                "selected_candidate_hook_id": selected_candidate["candidate"]["hook_id"],
                "selected_candidate_prompt_sha256": selected_candidate["candidate"]["prompt_sha256"],
                "divergence_status": "aligned",
                "resolution_policy": "selected_candidate_authoritative",
                "reconciliation_status": "reconciled",
                "operator_review_required": False,
                "final_reconciled_candidate_id": selected_candidate["candidate"]["candidate_id"],
                "final_reconciled_candidate_recipe_id": selected_candidate["candidate"]["recipe_id"],
                "final_reconciled_candidate_slot_id": selected_candidate["candidate"]["slot_id"],
                "final_reconciled_candidate_hook_id": selected_candidate["candidate"]["hook_id"],
                "final_reconciled_candidate_prompt_sha256": selected_candidate["candidate"]["prompt_sha256"],
                "final_reconciled_candidate_artifact_path": selected_candidate_path.relative_to(tmp_path).as_posix(),
                "final_reconciled_candidate_artifact_sha256": selected_sha256,
                "exact_next_allowed_action": "build_next_live_image_handoff",
                "next_allowed_action": {
                    "status": "reconciled",
                    "action": "build_next_live_image_handoff",
                    "reason": "recommendation and selected candidate are aligned and may be handed off",
                },
                "reconciliation_fingerprint_sha256": reconciliation["reconciliation"]["source_artifact_sha256"],
                "output_artifact_path": reconciliation_path.relative_to(tmp_path).as_posix(),
                "dirty_workspace_dependency": False,
                "shadow_mode_only": True,
                "provider_call_performed": False,
                "approval_consumed": False,
                "claims_written": False,
                "receipts_written": False,
                "queue_mutated": False,
                "publish_performed": False,
                "blocking_reasons": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = handoff_builder.build_handoff(DATE, RECONCILIATION_PATH)
    return report


def _write_handoff(tmp_path: Path, report: dict | None = None) -> Path:
    handoff_path = tmp_path / _handoff_repo_path()
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps(report or _valid_handoff_report(tmp_path), indent=2), encoding="utf-8")
    selected_candidate_path = tmp_path / _selected_candidate_repo_path()
    selected_candidate_path.parent.mkdir(parents=True, exist_ok=True)
    selected_candidate_path.write_text(json.dumps(_selected_candidate_payload(), indent=2), encoding="utf-8")
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
    assert facts["selected_candidate_repo_path"] == _selected_candidate_repo_path()
    assert facts["selected_candidate_id"] == f"{SLOT_ID}::hcr_011::cbn_004"
    assert facts["selected_candidate_slot_id"] == SLOT_ID
    assert facts["selected_candidate_recipe_id"] == "hcr_011"
    assert facts["selected_candidate_prompt_sha256"] == PROMPT_SHA
    assert facts["provider_execution_binding"]["provider_prompt_sha256"] == PROMPT_SHA
    assert facts["provider_execution_binding"]["provider_lane"] == "parking_garage_flash"
    assert facts["binding_linkage"]["candidate_prompt_family"] == "prompt_library_candidate"
    assert facts["binding_linkage"]["provider_prompt_family"] == "compact_provider_prompt"


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


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda report: report.pop("selected_candidate"), "handoff_selected_candidate_provenance_missing"),
        (lambda report: report["selected_candidate"].pop("candidate_id"), "handoff_selected_candidate_id_mismatch"),
        (lambda report: report["selected_candidate"].pop("slot_id"), "handoff_selected_candidate_slot_mismatch"),
        (lambda report: report["selected_candidate"].__setitem__("candidate_status", "abstain"), "handoff_selected_candidate_snapshot_status_invalid"),
        (lambda report: report["selected_candidate"].__setitem__("prompt_sha256", hashlib.sha256(b"other-prompt").hexdigest()), "handoff_selected_candidate_prompt_sha_mismatch"),
    ],
)
def test_validate_rejects_selected_candidate_snapshot_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    report = json.loads(handoff_path.read_text(encoding="utf-8"))
    mutator(report)
    handoff_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == expected_code


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda payload: payload.__setitem__("candidate_status", "abstain"), "handoff_selected_candidate_sha_mismatch"),
        (lambda payload: payload["candidate"].__setitem__("slot_id", "wrong-slot"), "handoff_selected_candidate_sha_mismatch"),
        (lambda payload: payload["candidate"].__setitem__("recipe_id", "hcr_008"), "handoff_selected_candidate_sha_mismatch"),
    ],
)
def test_validate_rejects_selected_candidate_file_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    candidate_path = tmp_path / _selected_candidate_repo_path()
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    mutator(payload)
    candidate_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == expected_code


def test_validate_rejects_malformed_selected_candidate_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    approval_path = _record_and_write(tmp_path, handoff_path)
    candidate_path = tmp_path / _selected_candidate_repo_path()
    candidate_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        validate_generation_approval_artifact(approval_path)
    assert excinfo.value.code == "handoff_selected_candidate_missing_or_invalid"


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
        (lambda report: report.pop("source_selected_candidate_artifact_path"), "handoff_selected_candidate_path_missing"),
    ],
)
def test_inspect_handoff_artifact_fails_closed_on_unsafe_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str
) -> None:
    _patch_root(tmp_path, monkeypatch)
    report = _valid_handoff_report(tmp_path)
    mutator(report)
    handoff_path = _write_handoff(tmp_path, report)

    with pytest.raises(HiggsfieldGenerationApprovalError) as excinfo:
        inspect_handoff_artifact(handoff_path)
    assert excinfo.value.code == expected_code
