from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import pipeline.higgsfield_lena_api_executor as executor
import tools.lena_higgsfield_generation_approval_v1 as approval_mod
import tools.lena_higgsfield_retry_generation_approval_v1 as retry_approval_mod
import tools.lena_photo_qa_disposition_v1 as disposition_mod
import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff_builder
import tools.strategy.lena_reconciliation_contract_v1 as reconciliation_contract
import tools.strategy.lena_record_generation_reconciliation_decision_v1 as decision_mod
import tools.strategy.lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff_mod
from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits
from tests.fixtures import lena_pose_provenance as pose_fixture
from tests.test_lena_prepare_higgsfield_retry_handoff_v1 import ORIGINAL_PROMPT


DATE = "2026-07-13"
RECIPE_ID = "hcr_006"
SLOT_ID = f"higgsfield-20260713-{RECIPE_ID}-photo"
HANDOFF_NAME = f"lena_next_live_image_handoff_{DATE}.json"
EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
HANDOFF_COMMAND = f"python {EXECUTOR_PATH} --handoff-artifact pipeline/strategy/lena/next_actions/{DATE}/{HANDOFF_NAME}"
PROMPT_TEXT = pose_fixture.canonical_prompt()
RECONCILIATION_PATH = f"pipeline/strategy/lena/reconciliations/{DATE}/lena_generation_reconciliation_fixture.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_roots(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor, "ROOT", tmp_root)
    monkeypatch.setattr(handoff_builder, "ROOT", tmp_root)
    monkeypatch.setattr(handoff_builder, "NEXT_ACTIONS", tmp_root / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(handoff_builder, "CONTENT_PACKETS", tmp_root / "pipeline" / "strategy" / "lena" / "content_packets")
    monkeypatch.setattr(
        handoff_builder,
        "PRE_GENERATION_CANDIDATES",
        tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
    )
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_root)
    monkeypatch.setattr(decision_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        decision_mod,
        "DECISIONS_ROOT",
        tmp_root / "pipeline" / "strategy" / "lena" / "reconciliation_decisions",
    )
    monkeypatch.setattr(approval_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        approval_mod,
        "DEFAULT_APPROVAL_ROOT",
        tmp_root / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(retry_handoff_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        retry_handoff_mod,
        "DEFAULT_OUTPUT_ROOT",
        tmp_root / "pipeline" / "strategy" / "lena" / "retry_handoffs",
    )
    monkeypatch.setattr(retry_approval_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        retry_approval_mod,
        "DEFAULT_APPROVAL_ROOT",
        tmp_root / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(
        handoff_builder.pose_provenance,
        "build_candidate_pose_provenance",
        pose_fixture.candidate_pose_provenance,
    )
    monkeypatch.setattr(
        handoff_builder.pose_provenance,
        "build_candidate_expression_provenance",
        pose_fixture.candidate_expression_provenance,
    )
    monkeypatch.setattr(
        handoff_builder.packet_builder,
        "rebuild_packet_from_authoritative_sources",
        lambda packet, pose_binding=None, expression_binding=None: pose_fixture.bind_packet(
            packet,
            pose_binding=pose_binding,
            expression_binding=expression_binding,
        ),
    )


def _learning_payload(status: str = "current") -> dict:
    return {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": DATE,
        "published_post_count": 3,
        "pending_metrics_posts": [{}],
        "stale_pending_metrics_posts": [{}],
        "winner_posts": [{"recipe_id": RECIPE_ID}],
        "queue_boosts": {"preferred_recipe_ids": [RECIPE_ID]},
        "metrics_resolution_summary": {
            "learning_status": status,
            "current_count": 2,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0,
        },
    }


def _recommendation_payload(learning_path: Path, status: str = "current") -> dict:
    return {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_artifact_path": str(learning_path),
        "learning_status": status,
        "learning_status_label": "learning_current",
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": 3,
        "learning_pending_metrics_count": 1,
        "learning_stale_pending_metrics_count": 1,
        "learning_resolution_state_summary": _learning_payload(status)["metrics_resolution_summary"],
        "learning_required_follow_up_action": "no_follow_up_required",
        "learning_winner_post_count": 1,
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": RECIPE_ID,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids", "winner_posts"],
            "next_live_gate": "review",
        },
    }


def _queue_payload(recipe_id: str = RECIPE_ID) -> dict:
    return {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "dry_run": True,
        "proof_lane_lock": {
            "action_type": "collect_first_controlled_proof",
            "recipe_id": recipe_id,
            "outfit_id": "wc_p059",
            "environment_id": "env_p001",
            "next_live_gate": "review",
        },
        "proof_lane_lock_active": True,
        "queue_slots": [
            {
                "recipe_id": recipe_id,
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


def _content_packet_payload(prompt_text: str = PROMPT_TEXT) -> dict:
    prompt_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    return {
        "report_type": "lena_content_packet_dryrun",
        "schema_version": "v1",
        "packet_id": f"cpkt_20260713_{RECIPE_ID}",
        "generated_date": DATE,
        "generator": "lena_build_content_packet_dryrun_v1",
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "publishing_approval": "not_approved",
        "recipe_id": RECIPE_ID,
        "scene_type": "parking_garage_flash",
        "wardrobe_outfit_id": "wc_p059",
        "content_pillar": "beautiful_trouble",
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


def _selected_candidate_payload(recipe_id: str = RECIPE_ID, *, generated_at_utc: str = "2026-07-13T12:34:57Z") -> dict:
    prompt_sha = hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
    slot_id = f"higgsfield-20260713-{recipe_id}-photo"
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": f"{slot_id}::{recipe_id}::cbn_004",
            "slot_id": slot_id,
            "lane": "parking_garage_flash",
            "recipe_id": recipe_id,
            "hook_id": "cbn_004",
            "prompt_sha256": prompt_sha,
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
            "expression_gaze_id": pose_fixture.EXPRESSION_ID,
            "expression_gaze_label": pose_fixture.EXPRESSION_LABEL,
            "expression_canonical_text": pose_fixture.EXPRESSION_TEXT,
            "expression_text": pose_fixture.EXPRESSION_TEXT,
            "expression_safe_fallback_used": False,
            "expression_safe_fallback_reason": None,
            "expression_scene_conflict_terms": [],
            "expression_derivation_scene_action": "standing in a controlled studio portrait",
            "expression_gaze_id": pose_fixture.EXPRESSION_ID,
            "expression_gaze_label": pose_fixture.EXPRESSION_LABEL,
            "expression_canonical_text": pose_fixture.EXPRESSION_TEXT,
            "expression_text": pose_fixture.EXPRESSION_TEXT,
            "expression_safe_fallback_used": False,
            "expression_safe_fallback_reason": None,
            "expression_scene_conflict_terms": [],
            "expression_derivation_scene_action": "standing in a controlled studio portrait",
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {slot_id}",
        },
        "decision_fingerprint_sha256": "5" * 64,
        "generated_at_utc": generated_at_utc,
        "provider_authorized": False,
        "side_effects_performed": [],
    }


def _source_from_prompt(
    prompt_text: str = PROMPT_TEXT,
    pose_binding: dict | None = None,
    expression_binding: dict | None = None,
    *,
    packet_path: str | None = None,
    packet_sha256: str | None = None,
    packet_bound_sha256: str | None = None,
) -> dict:
    pose_binding = pose_binding or pose_fixture.static_pose_provenance()
    expression_binding = expression_binding or pose_fixture.static_expression_provenance()
    return {
        "resolver": "content_packet_dryrun",
        "slot_prefix": RECIPE_ID,
        "pack_count": 1,
        "pack_variety_warnings": [],
        "image": {
            "slot_id": SLOT_ID,
            "lane": "parking_garage_flash",
            "wardrobe_outfit_id": "wc_p059",
            "wardrobe_outfit_name": "fixture outfit",
            "wardrobe_silhouette_class": "beautiful_trouble",
            "environment_id": "env_p001",
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_body_language_label": pose_binding["pose_body_language_label"],
            "pose_text": pose_binding["pose_text"],
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_artifact_path": packet_path or (
                f"pipeline/strategy/lena/content_packets/{DATE}/"
                f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
            ),
            "pose_bound_content_packet_artifact_sha256": packet_sha256 or "3" * 64,
            "pose_bound_content_packet_sha256": packet_bound_sha256 or "4" * 64,
            "expression_gaze_id": expression_binding["expression_gaze_id"],
            "expression_gaze_label": expression_binding["expression_gaze_label"],
            "expression_text": expression_binding["expression_text"],
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_artifact_path": packet_path or (
                f"pipeline/strategy/lena/content_packets/{DATE}/"
                f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
            ),
            "expression_bound_content_packet_artifact_sha256": packet_sha256 or "3" * 64,
            "expression_bound_content_packet_sha256": packet_bound_sha256 or "4" * 64,
            "effective_wardrobe_silhouette_class": "beautiful_trouble",
            "soul_name": "Lena",
            "soul_version": "Soul 2.0",
            "soul_selection_mode": "provider_config_not_prompt_text",
            "camera_text": "35mm lens, natural grain",
            "lighting_text": "warm lobby spill and realistic night shadow falloff",
            "negative_prompt_enabled": False,
            "image_prompt": prompt_text,
            "validation": {
                "framing_present": True,
                "wardrobe_casual_free": True,
                "wardrobe_casual_terms_found": [],
                "scene_action_conflict_free": True,
                "scene_action_conflict_terms_found": [],
                "soul_anchor_absent": True,
                "negative_prompt_disabled": True,
                "heavy_overcorrection_free": True,
                "heavy_overcorrection_terms_found": [],
                "pose_scene_match_pass": True,
                "pose_scene_mismatch_terms_found": [],
                "low_hook_terms_found": [],
                "final_expression_text": "calm expression",
                "expression_safe_fallback_used": False,
                "expression_safe_fallback_reason": "",
                "expression_scene_gaze_conflict_terms_found": [],
            },
        },
    }


def _build_packet_fixture(tmp_root: Path, monkeypatch: pytest.MonkeyPatch, *, prompt_text: str = PROMPT_TEXT) -> tuple[Path, dict]:
    _patch_roots(tmp_root, monkeypatch)
    next_actions = tmp_root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    packets = tmp_root / "pipeline" / "strategy" / "lena" / "content_packets" / DATE
    candidates = tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    reconciliations = tmp_root / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    content_packet_path = packets / f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
    selected_candidate_path = candidates / "lena_pre_generation_candidate_selected.json"
    reconciliation_path = reconciliations / "lena_generation_reconciliation_fixture.json"
    packet_report = _content_packet_payload(prompt_text)

    _write_json(learning_path, _learning_payload())
    _write_json(recommendation_path, _recommendation_payload(learning_path))
    _write_json(queue_path, _queue_payload())
    _write_json(content_packet_path, packet_report)
    _write_json(selected_candidate_path, _selected_candidate_payload())
    learning_sha256 = reconciliation_contract.sha256_file(learning_path)
    recommendation_sha256 = reconciliation_contract.sha256_file(recommendation_path)
    selected_sha256 = reconciliation_contract.sha256_file(selected_candidate_path)
    _write_json(
        reconciliation_path,
        {
            "report_type": "lena_generation_reconciliation",
            "schema_version": "lena_generation_reconciliation_v1",
            "date": DATE,
            "generated_at": "2026-07-13T12:34:56+00:00",
            "source_revision": "085620d1",
            "source_revision_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
            "source_artifacts": {
                "learning": {
                    "source_artifact_path": learning_path.relative_to(tmp_root).as_posix(),
                    "source_artifact_sha256": learning_sha256,
                },
                "recommendation": {
                    "source_artifact_path": recommendation_path.relative_to(tmp_root).as_posix(),
                    "source_artifact_sha256": recommendation_sha256,
                },
                "selected_candidate": {
                    "source_artifact_path": selected_candidate_path.relative_to(tmp_root).as_posix(),
                    "source_artifact_sha256": selected_sha256,
                },
            },
            "learning_status": "current",
            "recommendation_recipe_id": RECIPE_ID,
            "recommendation_outfit_id": "wc_p059",
            "recommendation_environment_id": "env_p001",
            "recommendation_action_type": "collect_first_controlled_proof",
            "selected_candidate_id": _selected_candidate_payload()["candidate"]["candidate_id"],
            "selected_candidate_recipe_id": RECIPE_ID,
            "selected_candidate_slot_id": SLOT_ID,
            "selected_candidate_hook_id": "cbn_004",
            "selected_candidate_prompt_sha256": hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest(),
            "divergence_status": "aligned",
            "resolution_policy": "selected_candidate_authoritative",
            "reconciliation_status": "reconciled",
            "operator_review_required": False,
            "final_reconciled_candidate_id": _selected_candidate_payload()["candidate"]["candidate_id"],
            "final_reconciled_candidate_recipe_id": RECIPE_ID,
            "final_reconciled_candidate_slot_id": SLOT_ID,
            "final_reconciled_candidate_hook_id": "cbn_004",
            "final_reconciled_candidate_prompt_sha256": hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest(),
            "final_reconciled_candidate_artifact_path": selected_candidate_path.relative_to(tmp_root).as_posix(),
            "final_reconciled_candidate_artifact_sha256": selected_sha256,
            "exact_next_allowed_action": "build_next_live_image_handoff",
            "next_allowed_action": {
                "status": "reconciled",
                "action": "build_next_live_image_handoff",
                "reason": "recommendation and selected candidate are aligned and may be handed off",
            },
            "reconciliation_fingerprint_sha256": "d" * 64,
            "output_artifact_path": reconciliation_path.relative_to(tmp_root).as_posix(),
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
    )

    def rebuild_fixture(
        _path,
        _slot_id_override=None,
        _candidate_path=None,
        expected_pose_provenance=None,
        expected_expression_provenance=None,
    ):
        bound = pose_fixture.bind_packet(
            packet_report,
            pose_binding=expected_pose_provenance,
            expression_binding=expected_expression_provenance,
        )
        bound_sha = hashlib.sha256(
            json.dumps(bound, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return bound, _source_from_prompt(
            prompt_text,
            expected_pose_provenance,
            expected_expression_provenance,
            packet_path=content_packet_path.relative_to(tmp_root).as_posix(),
            packet_sha256=hashlib.sha256(content_packet_path.read_bytes()).hexdigest(),
            packet_bound_sha256=bound_sha,
        )

    monkeypatch.setattr(executor, "_rebuild_packet_prompt_source", rebuild_fixture)

    packet = handoff_builder.build_handoff(DATE, str(reconciliation_path.relative_to(tmp_root).as_posix()))
    packet_path, _ = handoff_builder.save_handoff(packet, DATE)
    assert packet_path.is_file()
    return packet_path, packet_report


@pytest.fixture(autouse=True)
def _forbid_live_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("provider subprocess must not be invoked by handoff validation tests")

    monkeypatch.setattr(executor.subprocess, "run", forbidden)


def test_handoff_dry_run_accepts_valid_packet_and_emits_expected_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield Lena executor -- HANDOFF DRY RUN (no provider/network call) ===" in stdout
    assert "handoff validation     : True" in stdout
    assert f"date                    : {DATE}" in stdout
    assert f"slot_id                 : {SLOT_ID}" in stdout
    assert "prompt sha match        : True" in stdout
    assert "provider/model/aspect/soul agreement : True" in stdout
    assert "provider_call_performed : False" in stdout
    assert "generation_performed    : False" in stdout
    assert "live_execution_authorized: False" in stdout


def test_candidate_to_handoff_to_manifest_to_qa_preserves_pose_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    report, source, _, _ = executor._validate_handoff_packet(handoff_path)
    bound_pose = report["pose_provenance"]
    image_path = tmp_path / "generated.png"
    image_path.write_bytes(b"synthetic-png-fixture")
    manifest = executor.build_manifest(
        DATE,
        SLOT_ID,
        source,
        executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID,
        {
            "job_id": "job-pose-provenance",
            "status": "completed",
            "result_urls": [],
            "saved_image_path": str(image_path.resolve()),
        },
    )
    manifest["image_format_detected"] = ".png"
    manifest_path = tmp_path / "result_manifest.json"
    _write_json(manifest_path, manifest)

    candidate = {
        "slot_id": SLOT_ID,
        "lane": source["image"]["lane"],
        "prompt_sha256": manifest["prompt_sha256"],
        "pose_body_language_id": bound_pose["pose_body_language_id"],
        "pose": bound_pose["pose_body_language_label"],
        "wardrobe_outfit_id": source["image"]["wardrobe_outfit_id"],
        "visual_style": source["image"]["effective_wardrobe_silhouette_class"],
    }
    decision = {"as_of_date": DATE, "authority_commit": "a" * 40}
    monkeypatch.setattr(disposition_mod, "_validate_manifest_bank_context", lambda *_args: None)
    monkeypatch.setattr(
        disposition_mod,
        "_validate_manifest_pose_contract",
        lambda *_args, **_kwargs: bound_pose,
    )
    validated = disposition_mod._validate_manifest(
        manifest_path,
        decision,
        candidate,
        {"path": str(image_path.resolve()), "format": "PNG"},
        "authorization_bound_handoff",
        provider_binding={
            "provider_lane": source["image"]["lane"],
            "provider_prompt_sha256": manifest["prompt_sha256"],
            "slot_id": SLOT_ID,
        },
    )

    assert report["selected_prompt_input"]["pose_provenance"] == bound_pose
    assert source["image"]["pose_provenance"] == bound_pose
    assert validated["pose_provenance"] == bound_pose
    assert validated["pose_body_language_id"] == bound_pose["pose_body_language_id"]


@pytest.mark.parametrize("boundary", ["executor", "approval"])
def test_pose_copy_disagreement_is_rejected_by_executor_and_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    handoff_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    report = json.loads(handoff_path.read_text(encoding="utf-8"))
    report["structured_executor_inputs"]["pose_provenance"] = dict(report["pose_provenance"])
    report["structured_executor_inputs"]["pose_provenance"]["pose_body_language_id"] = "pose_conflict"
    _write_json(handoff_path, report)

    error_type = (
        executor.HandoffArtifactError
        if boundary == "executor"
        else approval_mod.HiggsfieldGenerationApprovalError
    )
    with pytest.raises(error_type) as excinfo:
        if boundary == "executor":
            executor._validate_handoff_packet(handoff_path)
        else:
            approval_mod.inspect_handoff_artifact(handoff_path)
    assert excinfo.value.code == "handoff_pose_provenance_mismatch"


def test_validate_handoff_packet_uses_authoritative_handoff_slot_and_preserves_prompt_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet_path, packet_report = _build_packet_fixture(tmp_path, monkeypatch)
    original_rebuild = executor._rebuild_packet_prompt_source
    seen: dict[str, str | None] = {}

    def rebuild(
        packet_path: Path,
        slot_id_override: str | None = None,
        candidate_path=None,
        *,
        expected_pose_provenance=None,
        expected_expression_provenance=None,
    ):
        seen["slot_id_override"] = slot_id_override
        rebuilt_packet, source = original_rebuild(
            packet_path,
            slot_id_override,
            candidate_path,
            expected_pose_provenance=expected_pose_provenance,
            expected_expression_provenance=expected_expression_provenance,
        )
        if isinstance(slot_id_override, str) and slot_id_override.strip():
            source["image"]["slot_id"] = slot_id_override
        return rebuilt_packet, source

    monkeypatch.setattr(executor, "_rebuild_packet_prompt_source", rebuild)

    report, source, packet_validation, validation = executor._validate_handoff_packet(packet_path)

    assert seen["slot_id_override"] == SLOT_ID
    assert report["selected_slot_id"] == SLOT_ID
    assert report["selected_recipe_id"] == RECIPE_ID
    assert source["image"]["slot_id"] == SLOT_ID
    assert source["image"]["image_prompt"] == packet_report["compact_provider_prompt_preview"]
    assert packet_validation["slot_id"] == SLOT_ID
    assert packet_validation["selected_prompt_sha256"] == packet_report["compact_provider_prompt_sha256"]
    assert packet_validation["regenerated_prompt_sha256"] == packet_report["compact_provider_prompt_sha256"]
    assert packet_validation["prompt_sha_match"] is True
    assert packet_validation["selected_candidate_binding_valid"] is True
    assert packet_validation["reconciliation_provenance_valid"] is True
    assert validation["ok"] is True


def test_validate_handoff_packet_rejects_rebuilt_source_slot_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    original_rebuild = executor._rebuild_packet_prompt_source

    def rebuild(
        packet_path: Path,
        slot_id_override: str | None = None,
        candidate_path=None,
        *,
        expected_pose_provenance=None,
        expected_expression_provenance=None,
    ):
        rebuilt_packet, source = original_rebuild(
            packet_path,
            slot_id_override,
            candidate_path,
            expected_pose_provenance=expected_pose_provenance,
            expected_expression_provenance=expected_expression_provenance,
        )
        source["image"]["slot_id"] = "unrelated-slot"
        return rebuilt_packet, source

    monkeypatch.setattr(executor, "_rebuild_packet_prompt_source", rebuild)

    with pytest.raises(executor.HandoffArtifactError) as excinfo:
        executor._validate_handoff_packet(packet_path)

    assert excinfo.value.code == "handoff_slot_mismatch"


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda packet: packet.__setitem__("execution_owner", "someone_else"), "handoff_execution_owner_mismatch"),
        (lambda packet: packet.__setitem__("provider", "other"), "handoff_provider_mismatch"),
        (lambda packet: packet.__setitem__("executor_type", "other"), "handoff_executor_type_mismatch"),
        (lambda packet: packet.__setitem__("generation_performed", True), "handoff_generation_performed"),
        (lambda packet: packet.__setitem__("publish_authorized", True), "handoff_publish_authorized"),
        (lambda packet: packet["structured_executor_inputs"].__setitem__("negative_prompt_enabled", True), "handoff_negative_prompt_enabled"),
        (lambda packet: packet["structured_executor_inputs"].__setitem__("model", "bad_model"), "handoff_model_mismatch"),
        (lambda packet: packet["structured_executor_inputs"].__setitem__("aspect_ratio", "1:1"), "handoff_aspect_mismatch"),
        (lambda packet: packet["structured_executor_inputs"]["soul_metadata"].__setitem__("name", "Not Lena"), "handoff_soul_name_mismatch"),
        (lambda packet: packet["structured_executor_inputs"]["soul_metadata"].__setitem__("custom_reference_id", "wrong"), "handoff_soul_reference_mismatch"),
        (lambda packet: packet["structured_executor_inputs"]["soul_metadata"].__setitem__("identity_is_prompt_instruction", True), "handoff_soul_prompt_instruction_invalid"),
        (lambda packet: packet["selected_prompt_input"].__setitem__("prompt_sha256", "0" * 64), "handoff_prompt_sha_mismatch"),
        (lambda packet: packet["structured_executor_inputs"].__setitem__("date", "2026-07-12"), "handoff_date_mismatch"),
    ],
)
def test_handoff_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutator,
    expected_code: str,
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    mutator(packet)
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert expected_code in stdout


def test_forged_expression_prompt_rejects_before_approval_validation_or_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    forged_prompt = packet["selected_prompt_input"]["prompt_text"].replace(
        f"[Expression]: {pose_fixture.EXPRESSION_TEXT}",
        "[Expression]: forged expression",
    )
    assert forged_prompt != packet["selected_prompt_input"]["prompt_text"]
    packet["selected_prompt_input"]["prompt_text"] = forged_prompt
    packet["structured_executor_inputs"]["selected_prompt_text"] = forged_prompt
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        executor,
        "_validate_approval_artifact",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("approval validation must not be reached for a forged handoff")
        ),
    )
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("provider execution must not be reached for a forged handoff")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--handoff-artifact",
            str(packet_path),
            "--approval-artifact",
            str(approval_path),
            "--live",
        ],
    )

    assert executor.main() == 1
    assert "handoff_prompt_text_mismatch" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("block_name", "expected_code"),
    [
        ("candidate_selection_binding", "handoff_candidate_selection_binding_missing"),
        ("provider_execution_binding", "handoff_provider_execution_binding_missing"),
        ("binding_linkage", "handoff_binding_linkage_missing"),
    ],
)
def test_incomplete_authority_handoff_rejects_before_approval_validation_or_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    block_name: str,
    expected_code: str,
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet.pop(block_name)
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        executor,
        "_validate_approval_artifact",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("approval validation must not be reached for an incomplete handoff")
        ),
    )
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("provider execution must not be reached for an incomplete handoff")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--handoff-artifact",
            str(packet_path),
            "--approval-artifact",
            str(approval_path),
            "--live",
        ],
    )

    assert executor.main() == 1
    assert expected_code in capsys.readouterr().out


def test_validate_handoff_packet_rejects_selected_candidate_recommendation_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live execution must not be reached")),
    )
    monkeypatch.setattr(
        executor.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider subprocess must not be reached")),
    )

    date = "2026-07-15"
    slot_id = "higgsfield-20260715-hcr_008-photo"
    recommendation_recipe_id = "hcr_011"
    selected_recipe_id = "hcr_008"
    custom_reference_id = "90a293d7-f3af-4377-8751-3304a27b6f31"
    prompt_text = "Scene: candlelit arrival. Wardrobe: structured black set. Lighting: realistic low-light skin texture."
    prompt_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    next_actions_repo = Path("pipeline") / "strategy" / "lena" / "next_actions" / date
    packets_repo = Path("pipeline") / "strategy" / "lena" / "content_packets" / date
    candidates_repo = Path("pipeline") / "strategy" / "lena" / "pre_generation_candidates" / date
    learning_repo_path = next_actions_repo / f"lena_post_outcome_learning_state_{date}.json"
    recommendation_repo_path = next_actions_repo / f"lena_next_generation_step_{date}.json"
    queue_repo_path = next_actions_repo / f"lena_autonomous_generation_queue_dryrun_{date}.json"
    packet_repo_path = packets_repo / f"lena_content_packet_dryrun_{date}_{recommendation_recipe_id}.json"
    selected_candidate_repo_path = candidates_repo / "lena_pre_generation_candidate_selected.json"
    handoff_repo_path = next_actions_repo / f"lena_next_live_image_handoff_{date}.json"

    learning_path = tmp_path / learning_repo_path
    recommendation_path = tmp_path / recommendation_repo_path
    queue_path = tmp_path / queue_repo_path
    packet_path = tmp_path / packet_repo_path
    selected_candidate_path = tmp_path / selected_candidate_repo_path
    handoff_path = tmp_path / handoff_repo_path

    learning_report = {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": date,
        "published_post_count": 3,
        "pending_metrics_posts": [{}],
        "stale_pending_metrics_posts": [{}],
        "winner_posts": [{"recipe_id": recommendation_recipe_id}],
        "queue_boosts": {"preferred_recipe_ids": [recommendation_recipe_id]},
        "metrics_resolution_summary": {
            "learning_status": "current",
            "current_count": 2,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0,
        },
    }
    recommendation_report = {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": date,
        "learning_artifact_path": learning_path.as_posix(),
        "learning_status": learning_report["metrics_resolution_summary"]["learning_status"],
        "learning_status_label": "learning_current",
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": learning_report["published_post_count"],
        "learning_pending_metrics_count": len(learning_report["pending_metrics_posts"]),
        "learning_stale_pending_metrics_count": len(learning_report["stale_pending_metrics_posts"]),
        "learning_resolution_state_summary": learning_report["metrics_resolution_summary"],
        "learning_required_follow_up_action": "no_follow_up_required",
        "learning_winner_post_count": len(learning_report["winner_posts"]),
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": recommendation_recipe_id,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids", "winner_posts"],
            "next_live_gate": "review",
        },
    }
    queue_report = {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "date": date,
        "dry_run": True,
        "queue_slots": [
            {
                "recipe_id": recommendation_recipe_id,
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
    packet_report = {
        "report_type": "lena_content_packet_dryrun",
        "generated_date": date,
        "recipe_id": recommendation_recipe_id,
        "packet_id": f"cpkt_{date.replace('-', '')}_{recommendation_recipe_id}",
        "strong_hook_id": "cbn_004",
        "hook_text": "Tried To Dress Down. Failed.",
        "caption_draft": "caught me on the way in",
        "compact_provider_prompt_preview": prompt_text,
        "compact_provider_prompt_sha256": prompt_sha,
        "compact_provider_prompt_budget": prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS,
        "provider_prompt_contract": {
            "provider_route": "higgsfield_forward_no_live",
            "live_authority": False,
        },
    }
    selected_candidate_payload = {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": date,
        "authority_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": f"{slot_id}::{selected_recipe_id}::cbn_004",
            "slot_id": slot_id,
            "lane": "parking_garage_flash",
            "recipe_id": selected_recipe_id,
            "hook_id": "cbn_004",
            "prompt_sha256": prompt_sha,
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date} --slot-id {slot_id}",
        },
        "decision_fingerprint_sha256": "5" * 64,
        "generated_at_utc": "2026-07-15T12:34:57Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    _write_json(learning_path, learning_report)
    _write_json(recommendation_path, recommendation_report)
    _write_json(queue_path, queue_report)
    _write_json(packet_path, packet_report)
    _write_json(selected_candidate_path, selected_candidate_payload)

    reconciliation_repo_path = Path("pipeline/strategy/lena/reconciliations") / date / "lena_generation_reconciliation_fixture.json"
    reconciliation_path = tmp_path / reconciliation_repo_path
    _write_json(
        reconciliation_path,
        {
            "report_type": "lena_generation_reconciliation",
            "schema_version": "lena_generation_reconciliation_v1",
            "date": date,
            "generated_at": "2026-07-15T12:00:00+00:00",
            "source_revision": "085620d1",
            "source_revision_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
            "source_artifacts": {
                "learning": {
                    "source_artifact_path": learning_repo_path.as_posix(),
                    "source_artifact_sha256": hashlib.sha256(learning_path.read_bytes()).hexdigest(),
                },
                "recommendation": {
                    "source_artifact_path": recommendation_repo_path.as_posix(),
                    "source_artifact_sha256": hashlib.sha256(recommendation_path.read_bytes()).hexdigest(),
                },
                "selected_candidate": {
                    "source_artifact_path": selected_candidate_repo_path.as_posix(),
                    "source_artifact_sha256": hashlib.sha256(selected_candidate_path.read_bytes()).hexdigest(),
                },
            },
            "learning_status": "current",
            "recommendation_recipe_id": recommendation_recipe_id,
            "recommendation_outfit_id": "wc_p059",
            "recommendation_environment_id": "env_p001",
            "recommendation_action_type": "collect_first_controlled_proof",
            "selected_candidate_id": selected_candidate_payload["candidate"]["candidate_id"],
            "selected_candidate_recipe_id": selected_candidate_payload["candidate"]["recipe_id"],
            "selected_candidate_slot_id": selected_candidate_payload["candidate"]["slot_id"],
            "selected_candidate_hook_id": selected_candidate_payload["candidate"]["hook_id"],
            "selected_candidate_prompt_sha256": selected_candidate_payload["candidate"]["prompt_sha256"],
            "divergence_status": "recipe_mismatch",
            "resolution_policy": "explicit_operator_reconciliation_required",
            "reconciliation_status": "operator_review_required",
            "operator_review_required": True,
            "exact_next_allowed_action": "create_operator_reconciliation_decision",
            "next_allowed_action": {
                "status": "operator_review_required",
                "action": "create_operator_reconciliation_decision",
                "reason": "recommendation and selected candidate require explicit operator reconciliation",
            },
            "dirty_workspace_dependency": False,
            "shadow_mode_only": True,
            "provider_call_performed": False,
            "approval_consumed": False,
            "claims_written": False,
            "receipts_written": False,
            "queue_mutated": False,
            "publish_performed": False,
            "blocking_reasons": ["recommendation_recipe_id_differs_from_selected_candidate_recipe_id"],
        },
    )
    reconciliation_sha = hashlib.sha256(reconciliation_path.read_bytes()).hexdigest()
    decision = decision_mod.build_generation_reconciliation_decision(
        reconciliation_repo_path.as_posix(),
        "nicolas",
        selected_candidate_payload["candidate"]["candidate_id"],
        selected_candidate_payload["candidate"]["recipe_id"],
        selected_candidate_payload["candidate"]["slot_id"],
        decision_mod.expected_confirmation_phrase(json.loads(reconciliation_path.read_text(encoding="utf-8"))),
    )
    decision_path, _, _ = decision_mod.write_report(decision, date)

    selected_candidate_sha = hashlib.sha256(selected_candidate_path.read_bytes()).hexdigest()
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    handoff_report = {
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
        "date": date,
        "selected_slot_id": slot_id,
        "selected_recipe_id": selected_recipe_id,
        "expected_handoff_artifact_path": handoff_repo_path.as_posix(),
        "source_learning_artifact_path": learning_repo_path.as_posix(),
        "source_learning_artifact_sha256": hashlib.sha256(learning_path.read_bytes()).hexdigest(),
        "source_recommendation_artifact_path": recommendation_repo_path.as_posix(),
        "source_recommendation_artifact_sha256": hashlib.sha256(recommendation_path.read_bytes()).hexdigest(),
        "source_queue_dry_run_artifact_path": queue_repo_path.as_posix(),
        "source_queue_dry_run_artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        "source_selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "source_selected_candidate_artifact_sha256": selected_candidate_sha,
        "source_reconciliation_artifact_path": reconciliation_repo_path.as_posix(),
        "source_reconciliation_artifact_sha256": reconciliation_sha,
        "source_reconciliation_decision_artifact_path": decision_path.relative_to(tmp_path).as_posix(),
        "source_reconciliation_decision_artifact_sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
        "source_reconciliation_decision_id": decision["decision_id"],
        "source_reconciliation_decision_operator_id": decision["operator_id"],
        "source_reconciliation_decision_expires_at_utc": decision["decision_expires_at_utc"],
        "source_reconciliation_decision_authority_scope": decision["authority_scope"],
        "source_reconciliation_decision_live_generation_authorized": decision["live_generation_authorized"],
        "source_reconciliation_decision_publishing_authorized": decision["publishing_authorized"],
        "source_reconciliation_decision_next_allowed_action": decision["exact_next_allowed_action"],
        "source_recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": recommendation_recipe_id,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids", "winner_posts"],
            "next_live_gate": "review",
        },
        "selected_candidate": {
            "artifact_path": selected_candidate_repo_path.as_posix(),
            "artifact_sha256": selected_candidate_sha,
            "candidate_id": selected_candidate_payload["candidate"]["candidate_id"],
            "slot_id": selected_candidate_payload["candidate"]["slot_id"],
            "recipe_id": selected_candidate_payload["candidate"]["recipe_id"],
            "prompt_sha256": selected_candidate_payload["candidate"]["prompt_sha256"],
            "schema_version": selected_candidate_payload["schema_version"],
            "candidate_status": selected_candidate_payload["candidate_status"],
        },
        "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
        "selected_prompt_input_artifact_sha256": packet_sha,
        "selected_prompt_input": {
            "packet_id": packet_report["packet_id"],
            "hook_id": packet_report["strong_hook_id"],
            "hook_text": packet_report["hook_text"],
            "caption_seed": packet_report["caption_draft"],
            "prompt_sha256": prompt_sha,
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date} --slot-id {slot_id}",
        },
        "structured_executor_inputs": {
            "provider": "higgsfield",
            "executor_type": "higgsfield_cli",
            "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
            "model": "text2image_soul_v2",
            "aspect_ratio": "9:16",
            "negative_prompt_enabled": False,
            "live_execution_authorized": False,
            "date": date,
            "slot_id": slot_id,
            "handoff_artifact_path": handoff_repo_path.as_posix(),
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "soul_metadata": {
                "name": "Lena",
                "type": "Soul 2.0",
                "custom_reference_id": custom_reference_id,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_sha256": prompt_sha,
            "selected_prompt_text": prompt_text,
            "dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --handoff-artifact {handoff_repo_path.as_posix()}",
            "live_command": f"python pipeline/higgsfield_lena_api_executor.py --handoff-artifact {handoff_repo_path.as_posix()} --live",
            "dry_run_argv": [
                "python",
                "pipeline/higgsfield_lena_api_executor.py",
                "--handoff-artifact",
                handoff_repo_path.as_posix(),
            ],
            "live_argv": [
                "python",
                "pipeline/higgsfield_lena_api_executor.py",
                "--handoff-artifact",
                handoff_repo_path.as_posix(),
                "--live",
            ],
        },
    }
    _write_json(handoff_path, handoff_report)

    source = {
        "resolver": "content_packet_dryrun",
        "slot_prefix": recommendation_recipe_id,
        "pack_count": 1,
        "pack_variety_warnings": [],
        "image": {
            "slot_id": slot_id,
            "lane": "parking_garage_flash",
            "wardrobe_outfit_id": "wc_p059",
            "environment_id": "env_p001",
            "pose_body_language_id": None,
            "pose_body_language_label": "leaning against the elevator wall before heading up",
            "effective_wardrobe_silhouette_class": "beautiful_trouble",
            "soul_name": "Lena",
            "soul_version": "Soul 2.0",
            "soul_selection_mode": "provider_config_not_prompt_text",
            "camera_text": "35mm lens, natural grain",
            "lighting_text": "warm lobby spill and realistic night shadow falloff",
            "negative_prompt_enabled": False,
            "image_prompt": prompt_text,
            "validation": {
                "framing_present": True,
                "wardrobe_casual_free": True,
                "wardrobe_casual_terms_found": [],
                "scene_action_conflict_free": True,
                "scene_action_conflict_terms_found": [],
                "soul_anchor_absent": True,
                "negative_prompt_disabled": True,
                "heavy_overcorrection_free": True,
                "heavy_overcorrection_terms_found": [],
                "pose_scene_match_pass": True,
                "pose_scene_mismatch_terms_found": [],
                "low_hook_terms_found": [],
                "final_expression_text": "",
                "expression_safe_fallback_used": False,
                "expression_safe_fallback_reason": "",
                "expression_scene_gaze_conflict_terms_found": [],
            },
        },
    }

    monkeypatch.setattr(
        executor,
        "_rebuild_packet_prompt_source",
        lambda _path, _slot_id_override=None, _candidate_path=None,
        expected_pose_provenance=None, expected_expression_provenance=None: (
            copy.deepcopy(packet_report), copy.deepcopy(source)
        ),
    )

    with pytest.raises(executor.HandoffArtifactError) as excinfo:
        executor._validate_handoff_packet(handoff_path)

    assert excinfo.value.code == "selected_candidate_recommendation_mismatch"
    assert not approval_mod.claim_output_path(date, slot_id).exists()
    assert not approval_mod.receipt_output_path(date, slot_id).exists()
    assert not executor.manifest_path(date, slot_id).exists()


def test_legacy_handoff_missing_reconciliation_provenance_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch, prompt_text=PROMPT_TEXT)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    for key in (
        "source_reconciliation_artifact_path",
        "source_reconciliation_artifact_sha256",
        "source_reconciliation_decision_artifact_path",
        "source_reconciliation_decision_artifact_sha256",
        "source_reconciliation_decision_id",
        "source_reconciliation_decision_operator_id",
        "source_reconciliation_decision_expires_at_utc",
        "source_reconciliation_decision_authority_scope",
        "source_reconciliation_decision_live_generation_authorized",
        "source_reconciliation_decision_publishing_authorized",
        "source_reconciliation_decision_next_allowed_action",
    ):
        packet.pop(key, None)
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(reconciliation_contract.ReconciliationContractError) as excinfo:
        executor._validate_handoff_packet(packet_path)
    assert excinfo.value.code == "missing_reconciliation_artifact"
    assert not approval_mod.claim_output_path(DATE, SLOT_ID).exists()
    assert not approval_mod.receipt_output_path(DATE, SLOT_ID).exists()
    assert not executor.manifest_path(DATE, SLOT_ID).exists()


def test_prompt_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, packet_report = _build_packet_fixture(tmp_path, monkeypatch, prompt_text=PROMPT_TEXT)
    monkeypatch.setattr(
        executor,
        "_rebuild_packet_prompt_source",
        lambda _path, _slot_id_override=None, _candidate_path=None,
        expected_pose_provenance=None, expected_expression_provenance=None: (
            copy.deepcopy(packet_report),
            _source_from_prompt(
                PROMPT_TEXT + " drift",
                expected_pose_provenance,
                expected_expression_provenance,
            )
        ),
    )
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "handoff_prompt_sha_mismatch" in stdout


def test_source_artifact_sha_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    queue_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue["queue_slots"][0]["priority_score"] = 999
    _write_json(queue_path, queue)
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "handoff_queue_sha_mismatch" in stdout


def test_handoff_live_rejected_without_separate_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live provider path must not be reached")),
    )
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path), "--live"])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "[ABORT] --live with --handoff-artifact requires a valid --approval-artifact." in stdout
    assert "The handoff remains review-only and is never rewritten into live authorization." in stdout


def test_handoff_cli_aborts_cleanly_on_missing_reconciliation_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    reconciliation_path = tmp_path / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE / "lena_generation_reconciliation_fixture.json"
    reconciliation_path.unlink()
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path), "--live"])

    assert executor.main() == 1
    stdout = capsys.readouterr()
    assert f"[ABORT] missing_reconciliation_artifact: missing required artifact: {reconciliation_path}" in stdout.out
    assert "Traceback" not in stdout.err
    assert not approval_mod.approval_output_path(DATE, SLOT_ID).exists()
    assert not approval_mod.claim_output_path(DATE, SLOT_ID).exists()
    assert not approval_mod.receipt_output_path(DATE, SLOT_ID).exists()
    assert not executor.manifest_path(DATE, SLOT_ID).exists()


def test_handoff_cli_does_not_swallow_unexpected_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(executor, "_validate_handoff_packet", lambda _path: (_ for _ in ()).throw(ValueError("boom")))
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    with pytest.raises(ValueError, match="boom"):
        executor.main()


def _build_approval_fixture(handoff_path: Path, *, slot_id: str = SLOT_ID, date_str: str = DATE) -> Path:
    handoff_facts = approval_mod.inspect_handoff_artifact(handoff_path)
    record = approval_mod.build_generation_approval_record(
        handoff_facts,
        operator_id=approval_mod.CANONICAL_OPERATOR_ID,
        confirmation=approval_mod.confirmation_phrase(slot_id),
    )
    out_path = approval_mod.approval_output_path(date_str, slot_id)
    approval_mod.write_approval_record_atomic(out_path, record)
    return out_path


def _build_retry_fixture(
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    safe_prompt: bool = True,
) -> tuple[Path, Path]:
    _patch_roots(tmp_root, monkeypatch)
    retry_date = "2026-07-14"
    original_slot = "higgsfield-20260714-hcr_011-photo"
    custom_reference_id = "90a293d7-f3af-4377-8751-3304a27b6f31"
    original_prompt = (
        ORIGINAL_PROMPT.replace("lingerie", "intimate apparel")
        if safe_prompt
        else ORIGINAL_PROMPT
    )
    original_prompt_sha = hashlib.sha256(original_prompt.encode("utf-8")).hexdigest()
    handoff_repo_path = Path("pipeline/strategy/lena/next_actions") / retry_date / f"lena_next_live_image_handoff_{retry_date}.json"
    packet_repo_path = Path("pipeline/strategy/lena/content_packets") / retry_date / f"lena_content_packet_dryrun_{retry_date}_hcr_011.json"
    handoff_path = tmp_root / handoff_repo_path
    packet_path = tmp_root / packet_repo_path
    selected_candidate_repo_path = Path("pipeline/strategy/lena/pre_generation_candidates") / retry_date / "lena_pre_generation_candidate_selected.json"
    packet_report = {
        "report_type": "lena_content_packet_dryrun",
        "generated_date": retry_date,
        "recipe_id": "hcr_011",
        "scene_type": "fit_check_mirror_getting_ready",
        "wardrobe_outfit_id": "wc_p059",
        "environment_id": "env_p001",
        "compact_provider_prompt_preview": original_prompt,
        "compact_provider_prompt_sha256": original_prompt_sha,
        "compact_provider_prompt_budget": prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS,
        "provider_prompt_contract": {"provider_route": "higgsfield_forward_no_live", "live_authority": False},
    }
    _write_json(packet_path, packet_report)
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    selected_candidate_payload = {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": retry_date,
        "authority_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": f"{original_slot}::hcr_011::cbn_004",
            "slot_id": original_slot,
            "lane": "fit_check_mirror_getting_ready",
            "recipe_id": "hcr_011",
            "hook_id": "cbn_004",
            "prompt_sha256": original_prompt_sha,
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
            "expression_gaze_id": pose_fixture.EXPRESSION_ID,
            "expression_gaze_label": pose_fixture.EXPRESSION_LABEL,
            "expression_canonical_text": pose_fixture.EXPRESSION_TEXT,
            "expression_text": pose_fixture.EXPRESSION_TEXT,
            "expression_safe_fallback_used": False,
            "expression_safe_fallback_reason": None,
            "expression_scene_conflict_terms": [],
            "expression_derivation_scene_action": "standing in a controlled studio portrait",
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {retry_date} --slot-id {original_slot}",
        },
        "decision_fingerprint_sha256": "7" * 64,
        "generated_at_utc": "2026-07-14T12:34:57Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    selected_candidate_path = tmp_root / selected_candidate_repo_path
    _write_json(selected_candidate_path, selected_candidate_payload)
    selected_candidate_sha = hashlib.sha256(selected_candidate_path.read_bytes()).hexdigest()
    pose_binding = pose_fixture.candidate_pose_provenance(selected_candidate_path, root=tmp_root)
    expression_binding = pose_fixture.candidate_expression_provenance(
        selected_candidate_path,
        root=tmp_root,
    )
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
            "date": retry_date,
            "selected_slot_id": original_slot,
            "selected_recipe_id": "hcr_011",
            "expected_handoff_artifact_path": handoff_repo_path.as_posix(),
            "source_selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "source_selected_candidate_artifact_sha256": selected_candidate_sha,
            "selected_candidate": {
                "artifact_path": selected_candidate_repo_path.as_posix(),
                "artifact_sha256": selected_candidate_sha,
                "candidate_id": selected_candidate_payload["candidate"]["candidate_id"],
                "slot_id": selected_candidate_payload["candidate"]["slot_id"],
                "recipe_id": selected_candidate_payload["candidate"]["recipe_id"],
                "prompt_sha256": selected_candidate_payload["candidate"]["prompt_sha256"],
                "schema_version": selected_candidate_payload["schema_version"],
                "candidate_status": selected_candidate_payload["candidate_status"],
                "pose_body_language_id": pose_fixture.POSE_ID,
                "pose_body_language_label": pose_fixture.POSE_LABEL,
                "expression_gaze_id": expression_binding["expression_gaze_id"],
                "expression_gaze_label": expression_binding["expression_gaze_label"],
            },
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": "4" * 64,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": "4" * 64,
            "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
            "selected_prompt_input_artifact_sha256": packet_sha,
            "selected_prompt_input": {
                "prompt_sha256": original_prompt_sha,
                "prompt_text": original_prompt,
                "lane": packet_report["scene_type"],
                "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
                "selected_candidate_artifact_sha256": selected_candidate_sha,
                "pose_provenance": pose_binding,
                "pose_bound_content_packet_sha256": "4" * 64,
                "expression_provenance": expression_binding,
                "expression_bound_content_packet_sha256": "4" * 64,
            },
            "structured_executor_inputs": {
                "provider": "higgsfield",
                "executor_type": "higgsfield_cli",
                "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
                "model": "text2image_soul_v2",
                "aspect_ratio": "9:16",
                "negative_prompt_enabled": False,
                "live_execution_authorized": False,
                "date": retry_date,
                "slot_id": original_slot,
                "handoff_artifact_path": handoff_repo_path.as_posix(),
                "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
                "selected_candidate_artifact_sha256": selected_candidate_sha,
                "pose_provenance": pose_binding,
                "pose_bound_content_packet_sha256": "4" * 64,
                "expression_provenance": expression_binding,
                "expression_bound_content_packet_sha256": "4" * 64,
                "soul_metadata": {
                    "name": "Lena",
                    "type": "Soul 2.0",
                    "custom_reference_id": custom_reference_id,
                    "identity_is_prompt_instruction": False,
                },
                "selected_prompt_sha256": original_prompt_sha,
                "selected_prompt_text": original_prompt,
            },
        }
    learning_repo_path = Path("pipeline/strategy/lena/next_actions") / retry_date / f"lena_post_outcome_learning_state_{retry_date}.json"
    recommendation_repo_path = Path("pipeline/strategy/lena/next_actions") / retry_date / f"lena_next_generation_step_{retry_date}.json"
    queue_repo_path = Path("pipeline/strategy/lena/next_actions") / retry_date / f"lena_autonomous_generation_queue_dryrun_{retry_date}.json"
    learning_path = tmp_root / learning_repo_path
    recommendation_path = tmp_root / recommendation_repo_path
    queue_path = tmp_root / queue_repo_path
    _write_json(
        learning_path,
        {
            "report_type": "lena_post_outcome_learning_state",
            "version": "v1",
            "date": retry_date,
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
        },
    )
    _write_json(
        recommendation_path,
        {
            "report_type": "lena_next_generation_step",
            "version": "v1",
            "date": retry_date,
            "learning_artifact_path": learning_repo_path.as_posix(),
            "learning_status": "current",
            "learning_status_label": "learning_current",
            "learning_validation_state": "valid",
            "learning_validation_error": "",
            "learning_availability": "available",
            "learning_published_post_count": 3,
            "learning_pending_metrics_count": 1,
            "learning_stale_pending_metrics_count": 1,
            "learning_resolution_state_summary": {
                "learning_status": "current",
                "current_count": 2,
                "usable_but_incomplete_count": 0,
                "stale_unresolved_count": 0,
                "manual_or_future_capability_required_count": 0,
            },
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
        },
    )
    _write_json(
        queue_path,
        {
            "report_type": "lena_autonomous_generation_queue_dryrun",
            "version": "v1",
            "date": retry_date,
            "dry_run": True,
            "queue_slots": [
                {
                    "recipe_id": "hcr_011",
                    "title": "Getting Ready Mirror",
                    "scene_type": "fit_check_mirror_getting_ready",
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
        },
    )
    reconciliation_repo_path = Path("pipeline/strategy/lena/reconciliations") / retry_date / "lena_generation_reconciliation_fixture.json"
    reconciliation_path = tmp_root / reconciliation_repo_path
    _write_json(
        reconciliation_path,
        {
            "report_type": "lena_generation_reconciliation",
            "schema_version": "lena_generation_reconciliation_v1",
            "date": retry_date,
            "generated_at": "2026-07-14T12:00:00+00:00",
            "source_revision": "085620d1",
            "source_revision_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
            "source_artifacts": {
                "learning": {
                    "source_artifact_path": learning_repo_path.as_posix(),
                    "source_artifact_sha256": hashlib.sha256(learning_path.read_bytes()).hexdigest(),
                },
                "recommendation": {
                    "source_artifact_path": recommendation_repo_path.as_posix(),
                    "source_artifact_sha256": hashlib.sha256(recommendation_path.read_bytes()).hexdigest(),
                },
                "selected_candidate": {
                    "source_artifact_path": selected_candidate_repo_path.as_posix(),
                    "source_artifact_sha256": selected_candidate_sha,
                },
            },
            "learning_status": "current",
            "recommendation_recipe_id": "hcr_011",
            "recommendation_outfit_id": "wc_p059",
            "recommendation_environment_id": "env_p001",
            "recommendation_action_type": "collect_first_controlled_proof",
            "selected_candidate_id": selected_candidate_payload["candidate"]["candidate_id"],
            "selected_candidate_recipe_id": selected_candidate_payload["candidate"]["recipe_id"],
            "selected_candidate_slot_id": selected_candidate_payload["candidate"]["slot_id"],
            "selected_candidate_hook_id": selected_candidate_payload["candidate"]["hook_id"],
            "selected_candidate_prompt_sha256": selected_candidate_payload["candidate"]["prompt_sha256"],
            "divergence_status": "aligned",
            "resolution_policy": "selected_candidate_authoritative",
            "reconciliation_status": "reconciled",
            "operator_review_required": False,
            "final_reconciled_candidate_id": selected_candidate_payload["candidate"]["candidate_id"],
            "final_reconciled_candidate_recipe_id": selected_candidate_payload["candidate"]["recipe_id"],
            "final_reconciled_candidate_slot_id": selected_candidate_payload["candidate"]["slot_id"],
            "final_reconciled_candidate_hook_id": selected_candidate_payload["candidate"]["hook_id"],
            "final_reconciled_candidate_prompt_sha256": selected_candidate_payload["candidate"]["prompt_sha256"],
            "final_reconciled_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "final_reconciled_candidate_artifact_sha256": selected_candidate_sha,
            "exact_next_allowed_action": "build_next_live_image_handoff",
            "next_allowed_action": {
                "status": "reconciled",
                "action": "build_next_live_image_handoff",
                "reason": "recommendation and selected candidate are aligned and may be handed off",
            },
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
    )
    handoff_report["source_learning_artifact_path"] = learning_repo_path.as_posix()
    handoff_report["source_learning_artifact_sha256"] = hashlib.sha256(learning_path.read_bytes()).hexdigest()
    handoff_report["source_recommendation_artifact_path"] = recommendation_repo_path.as_posix()
    handoff_report["source_recommendation_artifact_sha256"] = hashlib.sha256(recommendation_path.read_bytes()).hexdigest()
    handoff_report["source_queue_dry_run_artifact_path"] = queue_repo_path.as_posix()
    handoff_report["source_queue_dry_run_artifact_sha256"] = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    handoff_report["source_reconciliation_artifact_path"] = reconciliation_repo_path.as_posix()
    handoff_report["source_reconciliation_artifact_sha256"] = hashlib.sha256(reconciliation_path.read_bytes()).hexdigest()
    handoff_report["source_reconciliation_decision_artifact_path"] = None
    handoff_report["source_reconciliation_decision_artifact_sha256"] = None
    selected_candidate_body = selected_candidate_payload["candidate"]
    pose_bound_packet_sha = "4" * 64
    handoff_report["candidate_selection_binding"] = {
        "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "selected_candidate_artifact_sha256": selected_candidate_sha,
        "candidate_id": selected_candidate_body["candidate_id"],
        "slot_id": selected_candidate_body["slot_id"],
        "recipe_id": selected_candidate_body["recipe_id"],
        "candidate_prompt_sha256": selected_candidate_body["prompt_sha256"],
        "candidate_lane": selected_candidate_body["lane"],
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_body_language_label": pose_binding["pose_body_language_label"],
        "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_gaze_label": expression_binding["expression_gaze_label"],
        "expression_provenance_fingerprint_sha256": expression_binding[
            "expression_provenance_fingerprint_sha256"
        ],
        "source_prompt_family": "prompt_library_candidate",
    }
    handoff_report["provider_execution_binding"] = {
        "content_packet_artifact_path": packet_repo_path.as_posix(),
        "content_packet_artifact_sha256": packet_sha,
        "recipe_id": selected_candidate_body["recipe_id"],
        "slot_id": original_slot,
        "provider_prompt_sha256": original_prompt_sha,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha,
        "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        "expression_bound_content_packet_sha256": pose_bound_packet_sha,
        "expression_provenance_fingerprint_sha256": expression_binding[
            "expression_provenance_fingerprint_sha256"
        ],
        "provider_lane": packet_report["scene_type"],
        "source_prompt_family": "compact_provider_prompt",
        "provider": "higgsfield",
        "model": "text2image_soul_v2",
    }
    handoff_report["binding_linkage"] = {
        "recommendation_artifact_path": recommendation_repo_path.as_posix(),
        "recommendation_artifact_sha256": hashlib.sha256(recommendation_path.read_bytes()).hexdigest(),
        "queue_artifact_path": queue_repo_path.as_posix(),
        "queue_artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "selected_candidate_artifact_sha256": selected_candidate_sha,
        "content_packet_artifact_path": packet_repo_path.as_posix(),
        "content_packet_artifact_sha256": packet_sha,
        "recipe_id": selected_candidate_body["recipe_id"],
        "slot_id": original_slot,
        "candidate_id": selected_candidate_body["candidate_id"],
        "outfit_id": packet_report["wardrobe_outfit_id"],
        "environment_id": packet_report["environment_id"],
        "candidate_lane": selected_candidate_body["lane"],
        "provider_lane": packet_report["scene_type"],
        "candidate_prompt_family": "prompt_library_candidate",
        "provider_prompt_family": "compact_provider_prompt",
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        "pose_bound_content_packet_sha256": pose_bound_packet_sha,
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_provenance_fingerprint_sha256": expression_binding[
            "expression_provenance_fingerprint_sha256"
        ],
        "expression_bound_content_packet_sha256": pose_bound_packet_sha,
        "prompt_family_relationship": (
            "candidate prompt family and provider prompt family are intentionally "
            "distinct for the same recipe/slot chain"
        ),
    }
    _write_json(handoff_path, handoff_report)
    handoff_sha = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
    image_path = tmp_root / "pipeline" / "higgsfield_library" / "lena" / retry_date / f"{original_slot}_seed.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nretry-proof-image")
    manifest_repo_path = Path("pipeline/higgsfield_debug") / retry_date / original_slot / "result_manifest.json"
    _write_json(
        tmp_root / manifest_repo_path,
        {
            "provider": "higgsfield",
            "slot_id": original_slot,
            "prompt_sha256": original_prompt_sha,
            "image_prompt": original_prompt,
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_body_language_label": pose_binding["pose_body_language_label"],
            "pose_text": pose_binding["pose_text"],
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_artifact_path": packet_repo_path.as_posix(),
            "pose_bound_content_packet_artifact_sha256": packet_sha,
            "pose_bound_content_packet_sha256": "4" * 64,
            "expression_gaze_id": expression_binding["expression_gaze_id"],
            "expression_gaze_label": expression_binding["expression_gaze_label"],
            "expression_text": expression_binding["expression_text"],
            "expression_safe_fallback_used": expression_binding["expression_safe_fallback_used"],
            "expression_safe_fallback_reason": expression_binding["expression_safe_fallback_reason"],
            "expression_scene_conflict_terms": expression_binding["expression_scene_conflict_terms"],
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_artifact_path": packet_repo_path.as_posix(),
            "expression_bound_content_packet_artifact_sha256": packet_sha,
            "expression_bound_content_packet_sha256": "4" * 64,
            "saved_image_path": str(image_path),
            "provider_job_id": "job-123",
            "provider_status": "completed",
        },
    )
    receipt_repo_path = Path("pipeline/approvals/lena/generation") / retry_date / f"{original_slot}_higgsfield_generation_execution_receipt.json"
    receipt_path = tmp_root / receipt_repo_path
    _write_json(
        receipt_path,
        {
            "report_type": "lena_higgsfield_generation_execution_receipt",
            "schema_version": "v1",
            "receipt_type": "higgsfield_single_generation_execution_receipt",
            "handoff_artifact_path": handoff_repo_path.as_posix(),
            "handoff_artifact_sha256": handoff_sha,
            "date": retry_date,
            "slot_id": original_slot,
            "prompt_sha256": original_prompt_sha,
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
            "custom_reference_id": custom_reference_id,
        },
    )
    monkeypatch.setattr(
        retry_handoff_mod.pose_provenance,
        "validate_source_generation_pose_contract",
        lambda manifest, report, root=None: {
            "pose_provenance": pose_binding,
            "expression_provenance": expression_binding,
            "prompt": original_prompt,
            "prompt_sha256": original_prompt_sha,
            "packet_path": packet_path,
            "packet_artifact_sha256": packet_sha,
            "packet_digest_sha256": "4" * 64,
            "rebuilt_packet": {},
        },
    )
    retry_report = retry_handoff_mod.evaluate_retry_handoff(
        handoff_artifact=handoff_path,
        execution_receipt=receipt_path,
        output_root=retry_handoff_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=True,
    )
    retry_handoff_path = Path(retry_report["retry_handoff_artifact_path"])
    retry_facts = retry_approval_mod.inspect_retry_handoff_artifact(retry_handoff_path)
    approval_record = retry_approval_mod.build_retry_generation_approval_record(
        retry_facts,
        operator_id=approval_mod.CANONICAL_OPERATOR_ID,
        confirmation=retry_approval_mod.confirmation_phrase(retry_facts["slot_id"]),
    )
    approval_path = retry_approval_mod.approval_output_path(retry_facts["date"], retry_facts["slot_id"])
    retry_approval_mod.write_retry_generation_approval_record_atomic(approval_path, approval_record)

    def fake_validate_handoff_packet(path: Path):
        report = json.loads(handoff_path.read_text(encoding="utf-8"))
        source = {
            "resolver": "content_packet_dryrun",
            "slot_prefix": "hcr_011",
            "pack_count": 1,
            "pack_variety_warnings": [],
            "image": {
                "slot_id": original_slot,
                "lane": "fit_check_mirror_getting_ready",
                "wardrobe_outfit_id": "wc_p020",
                "environment_id": "env_v008",
                "pose_body_language_id": pose_binding["pose_body_language_id"],
                "pose_body_language_label": pose_binding["pose_body_language_label"],
                "pose_text": pose_binding["pose_text"],
                "pose_provenance": pose_binding,
                "pose_bound_content_packet_artifact_path": packet_repo_path.as_posix(),
                "pose_bound_content_packet_artifact_sha256": packet_sha,
                "pose_bound_content_packet_sha256": "4" * 64,
                "expression_gaze_id": expression_binding["expression_gaze_id"],
                "expression_gaze_label": expression_binding["expression_gaze_label"],
                "expression_text": expression_binding["expression_text"],
                "expression_provenance": expression_binding,
                "expression_bound_content_packet_artifact_path": packet_repo_path.as_posix(),
                "expression_bound_content_packet_artifact_sha256": packet_sha,
                "expression_bound_content_packet_sha256": "4" * 64,
                "effective_wardrobe_silhouette_class": "beautiful_trouble",
                "soul_name": "Lena",
                "soul_version": "Soul 2.0",
                "soul_selection_mode": "provider_config_not_prompt_text",
                "camera_text": "85mm portrait compression",
                "lighting_text": "blue-hour ambient mixed with warm lamp fill",
                "negative_prompt_enabled": False,
                "image_prompt": original_prompt,
                "validation": {
                    "framing_present": True,
                    "wardrobe_casual_free": True,
                    "wardrobe_casual_terms_found": [],
                    "scene_action_conflict_free": True,
                    "scene_action_conflict_terms_found": [],
                    "soul_anchor_absent": True,
                    "negative_prompt_disabled": True,
                    "heavy_overcorrection_free": True,
                    "heavy_overcorrection_terms_found": [],
                    "pose_scene_match_pass": True,
                    "pose_scene_mismatch_terms_found": [],
                    "low_hook_terms_found": [],
                    "final_expression_text": "",
                    "expression_safe_fallback_used": False,
                    "expression_safe_fallback_reason": "",
                    "expression_scene_gaze_conflict_terms_found": [],
                },
            },
        }
        packet_validation = {
            "ok": True,
            "prompt_matches_expected": None,
            "hard_exclude_reasons": [],
            "all_reasons": [],
        }
        return report, source, packet_validation, packet_validation

    monkeypatch.setattr(executor, "_validate_handoff_packet", fake_validate_handoff_packet)
    return retry_handoff_path, approval_path


def test_approval_artifact_requires_handoff_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_approval = tmp_path / "approval.json"
    fake_approval.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["executor", "--approval-artifact", str(fake_approval)])

    assert executor.main() == 1
    assert "--approval-artifact requires --handoff-artifact" in capsys.readouterr().out


def test_dry_run_reports_valid_approval_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path)],
    )

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield generation approval -- validation (no consumption) ===" in stdout
    assert "operator_id              : nicolas" in stdout
    assert "approval-handoff binding : confirmed exact match to supplied --handoff-artifact" in stdout


def test_dry_run_with_valid_approval_creates_no_claim_or_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path)],
    )

    assert executor.main() == 0
    assert "=== Higgsfield generation approval -- validation (no consumption) ===" in capsys.readouterr().out
    assert not approval_mod.claim_output_path(DATE, SLOT_ID).exists()
    assert not approval_mod.receipt_output_path(DATE, SLOT_ID).exists()


def test_invalid_approval_reported_and_blocks_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["operator_id"] = "not_nicolas"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path)],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "approval validation failed" in stdout
    assert "approval_operator_mismatch" in stdout


def test_valid_handoff_and_approval_live_creates_claim_receipt_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    saved_image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"

    def fake_run_live(*args, **kwargs):
        saved_image_path.parent.mkdir(parents=True, exist_ok=True)
        saved_image_path.write_bytes(b"generated-image-bytes")
        return {
            "job_id": "job-123",
            "status": "completed",
            "result_urls": ["https://example.com/final.png"],
            "saved_image_path": str(saved_image_path),
            "image_format_detected": ".png",
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        }

    monkeypatch.setattr(
        executor,
        "run_live",
        fake_run_live,
    )
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path), "--live"],
    )

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    claim_path = approval_mod.claim_output_path(DATE, SLOT_ID)
    receipt_path = approval_mod.receipt_output_path(DATE, SLOT_ID)
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
    assert claim_path.is_file()
    assert receipt_path.is_file()
    assert manifest_path.is_file()
    assert "claim written" in stdout
    assert "receipt written" in stdout


def test_existing_claim_blocks_reuse_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    approval_result = approval_mod.validate_generation_approval_artifact(approval_path)
    approval_mod.write_generation_claim_atomic(
        approval_mod.claim_output_path(DATE, SLOT_ID),
        approval_mod.build_generation_claim_record(approval_result),
    )
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider path must not be reached after claim collision")),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path), "--live"],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "generation_claim_already_exists" in stdout
    assert not approval_mod.receipt_output_path(DATE, SLOT_ID).exists()


@pytest.mark.parametrize(
    ("stage", "provider_submission_may_have_occurred"),
    [
        ("subprocess_start_failure", False),
        ("provider_rejection", True),
        ("provider_output_parse_failure", True),
        ("provider_output_invalid", True),
        ("download_failure", True),
    ],
)
def test_live_failures_retain_claim_and_write_failure_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stage: str,
    provider_submission_may_have_occurred: bool,
) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)

    def _fail_live(*args, **kwargs):
        raise executor.ProviderCallError(
            f"synthetic {stage}",
            stage=stage,
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=provider_submission_may_have_occurred,
            provider_job_id="job-123" if provider_submission_may_have_occurred else None,
            provider_status="processing" if provider_submission_may_have_occurred else None,
        )

    monkeypatch.setattr(executor, "run_live", _fail_live)
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path), "--live"],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert approval_mod.claim_output_path(DATE, SLOT_ID).is_file()
    assert approval_mod.receipt_output_path(DATE, SLOT_ID).is_file()
    assert "Claim retained" in stdout


def test_handoff_packet_paths_remain_repo_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packet_path, _ = _build_packet_fixture(tmp_path, monkeypatch)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    for key in (
        "expected_handoff_artifact_path",
        "expected_handoff_markdown_path",
        "source_recommendation_artifact_path",
        "source_learning_artifact_path",
        "source_queue_dry_run_artifact_path",
        "selected_prompt_input_artifact_path",
    ):
        assert not Path(str(packet[key])).is_absolute()
    assert packet["structured_executor_inputs"]["handoff_artifact_path"] == packet["expected_handoff_artifact_path"]
    assert packet["structured_executor_inputs"]["handoff_markdown_path"] == packet["expected_handoff_markdown_path"]


def test_retry_dry_run_remains_no_live_without_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, _ = _build_retry_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["executor", "--retry-decision-artifact", str(retry_handoff_path)])

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "DRY RUN" in stdout
    assert "no subprocess call, no network call, no file written" in stdout
    assert not retry_approval_mod.claim_output_path("2026-07-14", "higgsfield-20260714-hcr_011-retry01-photo").exists()
    assert not retry_approval_mod.receipt_output_path("2026-07-14", "higgsfield-20260714-hcr_011-retry01-photo").exists()


def test_retry_live_requires_separate_retry_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, _ = _build_retry_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["executor", "--retry-decision-artifact", str(retry_handoff_path), "--live"])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "--retry-approval-artifact" in stdout


def test_retry_dry_run_reports_valid_retry_approval_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
        ],
    )

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield retry generation approval -- validation (no consumption) ===" in stdout
    assert "approval-retry binding   : confirmed exact match to supplied --retry-decision-artifact" in stdout


def test_retry_prompt_validation_failure_precedes_approval_consumption_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(
        tmp_path,
        monkeypatch,
        safe_prompt=False,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("invalid zero-loss retry prompt reached provider execution")

    monkeypatch.setattr(executor, "run_live", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "failed validation before approval consumption or provider execution" in stdout
    retry_slot = "higgsfield-20260714-hcr_011-retry01-photo"
    assert not retry_approval_mod.claim_output_path("2026-07-14", retry_slot).exists()
    assert not retry_approval_mod.receipt_output_path("2026-07-14", retry_slot).exists()


def test_retry_live_rejects_wrong_slot_or_prompt_or_retry_handoff_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path, monkeypatch)
    approval = json.loads(retry_approval_path.read_text(encoding="utf-8"))
    approval["slot_id"] = "wrong-slot"
    approval["confirmation_statement"] = retry_approval_mod.confirmation_phrase("wrong-slot")
    retry_approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    assert "approval_slot_binding_mismatch" in capsys.readouterr().out

    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path / "prompt", monkeypatch)
    approval = json.loads(retry_approval_path.read_text(encoding="utf-8"))
    approval["prompt_sha256"] = hashlib.sha256(b"wrong").hexdigest()
    retry_approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    assert "approval_prompt_sha_mismatch" in capsys.readouterr().out

    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path / "binding", monkeypatch)
    approval = json.loads(retry_approval_path.read_text(encoding="utf-8"))
    approval["retry_handoff_artifact_path"] = "pipeline/strategy/lena/retry_handoffs/2026-07-14/wrong.json"
    retry_approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    assert "wrong.json" in capsys.readouterr().out


def test_retry_live_rejects_expired_or_broken_lineage_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path, monkeypatch)
    approval = json.loads(retry_approval_path.read_text(encoding="utf-8"))
    approved_at = datetime.now(timezone.utc) - timedelta(minutes=retry_approval_mod.APPROVAL_TTL_MINUTES + 1)
    approval["approved_at_utc"] = approved_at.replace(microsecond=0).isoformat()
    approval["expires_at_utc"] = (approved_at + timedelta(minutes=retry_approval_mod.APPROVAL_TTL_MINUTES)).replace(microsecond=0).isoformat()
    retry_approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    assert "approval_expired" in capsys.readouterr().out

    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path / "lineage", monkeypatch)
    source_receipt = tmp_path / "lineage" / "pipeline" / "approvals" / "lena" / "generation" / "2026-07-14" / "higgsfield-20260714-hcr_011-photo_higgsfield_generation_execution_receipt.json"
    receipt = json.loads(source_receipt.read_text(encoding="utf-8"))
    receipt["provider_status"] = "tampered"
    source_receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    assert "source_execution_receipt_sha256 does not match the current receipt bytes" in capsys.readouterr().out


def test_retry_live_success_creates_retry_claim_receipt_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path, monkeypatch)
    retry_slot = "higgsfield-20260714-hcr_011-retry01-photo"
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: {
            "job_id": "job-123",
            "status": "completed",
            "result_urls": ["https://example.com/final.png"],
            "saved_image_path": str(tmp_path / "pipeline" / "higgsfield_library" / "lena" / "2026-07-14" / f"{retry_slot}_seed.png"),
            "image_format_detected": ".png",
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert retry_approval_mod.claim_output_path("2026-07-14", retry_slot).is_file()
    assert retry_approval_mod.receipt_output_path("2026-07-14", retry_slot).is_file()
    assert (tmp_path / "pipeline" / "higgsfield_debug" / "2026-07-14" / retry_slot / "result_manifest.json").is_file()
    assert "retry claim written" in stdout
    assert "retry receipt written" in stdout


def test_retry_live_rejects_reused_approval_and_consumes_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path, monkeypatch)
    retry_slot = "higgsfield-20260714-hcr_011-retry01-photo"
    approval_result = retry_approval_mod.validate_retry_generation_approval_artifact(retry_approval_path)
    retry_approval_mod.write_retry_generation_claim_atomic(
        retry_approval_mod.claim_output_path("2026-07-14", retry_slot),
        retry_approval_mod.build_retry_generation_claim_record(approval_result),
    )
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider path must not be reached after retry claim collision")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    assert "retry_generation_claim_already_exists" in capsys.readouterr().out

    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path / "failure", monkeypatch)
    def _fail_live(*args, **kwargs):
        raise executor.ProviderCallError(
            "synthetic provider rejection",
            stage="provider_rejection",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id="job-123",
            provider_status="processing",
        )

    monkeypatch.setattr(executor, "run_live", _fail_live)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )
    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert retry_approval_mod.claim_output_path("2026-07-14", retry_slot).is_file()
    assert retry_approval_mod.receipt_output_path("2026-07-14", retry_slot).is_file()
    assert "Retry claim retained" in stdout


def test_retry_receipt_prevents_second_attempt_even_without_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    retry_handoff_path, retry_approval_path = _build_retry_fixture(tmp_path, monkeypatch)
    retry_slot = "higgsfield-20260714-hcr_011-retry01-photo"
    approval_result = retry_approval_mod.validate_retry_generation_approval_artifact(retry_approval_path)
    claim_path = retry_approval_mod.claim_output_path("2026-07-14", retry_slot)
    retry_approval_mod.write_retry_generation_claim_atomic(
        claim_path,
        retry_approval_mod.build_retry_generation_claim_record(approval_result),
    )
    retry_approval_mod.write_retry_generation_execution_receipt_atomic(
        retry_approval_mod.receipt_output_path("2026-07-14", retry_slot),
        retry_approval_mod.build_retry_generation_execution_receipt_record(
            claim_path,
            approval_result,
            outcome="execution_failed",
            failure_stage="provider_rejection",
            error_text="already consumed",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id="job-123",
            provider_status="failed",
            output_path=None,
            image_format_detected=None,
            actual_manifest_path=None,
        ),
    )
    claim_path.unlink()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "executor",
            "--retry-decision-artifact",
            str(retry_handoff_path),
            "--retry-approval-artifact",
            str(retry_approval_path),
            "--live",
        ],
    )

    assert executor.main() == 1
    assert "retry_generation_already_consumed" in capsys.readouterr().out


def test_rebuild_packet_prompt_source_populates_candidate_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_rebuild_packet_prompt_source must copy pose/expression from the candidate artifact
    and derive wardrobe name/silhouette from the catalog — not hardcode nulls."""
    import tools.strategy.lena_build_content_packet_dryrun_v1 as packet_builder
    import pipeline.prompting.lena_prompt_brain as prompt_brain

    packet_report = {**_content_packet_payload(), "wardrobe_outfit_id": "wc_p050"}
    packet_path = tmp_path / "lena_content_packet_dryrun_test.json"
    _write_json(packet_path, packet_report)

    candidate_path = tmp_path / "lena_pre_generation_candidate_test.json"
    _write_json(candidate_path, {
        "authority_commit": "a" * 40,
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": "test-cand-provenance-001",
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose": pose_fixture.POSE_LABEL,
            "expression_gaze_id": "expr_soft_direct",
            "expression_gaze_label": "soft direct gaze",
        }
    })

    monkeypatch.setattr(
        executor, "load_content_packet_report", lambda _p, _d: packet_report
    )
    monkeypatch.setattr(
        packet_builder,
        "rebuild_packet_from_authoritative_sources",
        lambda _r, pose_binding=None, expression_binding=None: pose_fixture.bind_packet(
            _r,
            pose_binding=pose_binding,
            expression_binding=expression_binding,
        ),
    )
    expected_pose = pose_fixture.static_pose_provenance()
    expected_expression = pose_fixture.static_expression_provenance()
    monkeypatch.setattr(
        handoff_builder.pose_provenance,
        "build_candidate_pose_provenance",
        lambda _path, root=None: expected_pose,
    )
    monkeypatch.setattr(
        handoff_builder.pose_provenance,
        "build_candidate_expression_provenance",
        lambda _path, root=None: expected_expression,
    )
    fake_wf_entry = {
        "outfit_id": "wc_p050",
        "name": "Dusty Rose Off-Shoulder Knit Top + Stone-Wash Straight Jeans",
        "style_lane": "jeans_based",
    }
    monkeypatch.setattr(packet_builder, "load_json", lambda _p: [fake_wf_entry])
    monkeypatch.setattr(
        packet_builder, "select_wardrobe_entry", lambda _c, _id, *_a: fake_wf_entry
    )
    monkeypatch.setattr(prompt_brain, "catalog_outfit_silhouette_class", lambda _e: "jeans_based")

    _, source = executor._rebuild_packet_prompt_source(
        packet_path,
        "test-slot-001",
        candidate_path,
        expected_pose_provenance=expected_pose,
        expected_expression_provenance=expected_expression,
    )
    img = source["image"]

    assert img["pose_body_language_id"] == pose_fixture.POSE_ID, (
        "pose_body_language_id must be populated from candidate artifact"
    )
    assert img["wardrobe_outfit_name"] == "Dusty Rose Off-Shoulder Knit Top + Stone-Wash Straight Jeans", (
        "wardrobe_outfit_name must be derived from catalog entry"
    )
    assert img["wardrobe_silhouette_class"] == "jeans_based", (
        "wardrobe_silhouette_class must be derived from catalog_outfit_silhouette_class"
    )
    assert img["effective_wardrobe_silhouette_class"] == img["wardrobe_silhouette_class"], (
        "effective_wardrobe_silhouette_class must equal wardrobe_silhouette_class, not content_pillar"
    )
    assert img["effective_wardrobe_silhouette_class"] != packet_report.get("content_pillar"), (
        "effective_wardrobe_silhouette_class must not be the content_pillar string"
    )
