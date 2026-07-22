from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from pipeline import higgsfield_lena_api_executor as executor
from tools import lena_higgsfield_generation_approval_v1 as approval_mod
import tools.strategy.lena_reconciliation_contract_v1 as reconciliation_contract
import tools.strategy.lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_mod
from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits
from tests.fixtures import lena_pose_provenance as pose_fixture


DATE = "2026-07-14"
ORIGINAL_SLOT = "higgsfield-20260714-hcr_011-photo"
RETRY_SLOT = "higgsfield-20260714-hcr_011-retry01-photo"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
ORIGINAL_PROMPT = packet_builder.rebuild_packet_from_authoritative_sources(
    {
        "recipe_id": "hcr_011",
        "strong_hook_id": "mf_001",
        "generated_date": "2026-07-17",
        "wardrobe_outfit_id": "wc_p020",
        "environment_id": "env_v008",
        "hook_selection_reason": "mirror fitcheck",
    },
    pose_binding=pose_fixture.static_pose_provenance(),
    expression_binding=pose_fixture.static_expression_provenance(),
)["compact_provider_prompt_preview"]
PROMPT_SHA = hashlib.sha256(ORIGINAL_PROMPT.encode("utf-8")).hexdigest()
SELECTED_CANDIDATE_REPO_PATH = Path(
    f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/lena_pre_generation_candidate_selected.json"
)


def _selected_candidate_payload() -> dict:
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "authority_commit": "a" * 40,
        "candidate_status": "selected",
        "generated_at_utc": "2026-07-14T12:00:00+00:00",
        "candidate": {
            "candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
            "slot_id": ORIGINAL_SLOT,
            "lane": "fit_check_mirror_getting_ready",
            "recipe_id": "hcr_011",
            "prompt_sha256": PROMPT_SHA,
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
        },
    }


def _selected_candidate_sha() -> str:
    return hashlib.sha256(
        json.dumps(_selected_candidate_payload(), indent=2).replace("\n", os.linesep).encode("utf-8")
    ).hexdigest()


def _patch_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        approval_mod,
        "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(retry_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        retry_mod,
        "DEFAULT_OUTPUT_ROOT",
        tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs",
    )
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_path)
    monkeypatch.setattr(
        retry_mod.pose_provenance,
        "build_candidate_pose_provenance",
        pose_fixture.candidate_pose_provenance,
    )
    monkeypatch.setattr(
        retry_mod.pose_provenance,
        "build_candidate_expression_provenance",
        pose_fixture.candidate_expression_provenance,
    )


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _seed_bound_retry_source(tmp_path: Path) -> dict[str, Path]:
    handoff_repo_path = Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_next_live_image_handoff_{DATE}.json"
    packet_repo_path = Path("pipeline/strategy/lena/content_packets") / DATE / f"lena_content_packet_dryrun_{DATE}_hcr_011.json"
    selected_candidate_repo_path = SELECTED_CANDIDATE_REPO_PATH
    handoff_path = tmp_path / handoff_repo_path
    packet_path = tmp_path / packet_repo_path
    selected_candidate_path = tmp_path / selected_candidate_repo_path
    packet_report = {
        "report_type": "lena_content_packet_dryrun",
        "generated_date": DATE,
        "recipe_id": "hcr_011",
        "scene_type": "fit_check_mirror_getting_ready",
        "strong_hook_id": "mf_001",
        "wardrobe_outfit_id": "wc_p020",
        "environment_id": "env_v008",
        "hook_selection_reason": "retry source fixture",
        "compact_provider_prompt_preview": ORIGINAL_PROMPT,
        "compact_provider_prompt_sha256": PROMPT_SHA,
        "compact_provider_prompt_budget": prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS,
        "provider_prompt_contract": {
            "provider_route": "higgsfield_forward_no_live",
            "live_authority": False,
        },
    }
    _write_json(packet_path, packet_report)
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    selected_candidate_path.parent.mkdir(parents=True, exist_ok=True)
    selected_candidate_path.write_text(json.dumps(_selected_candidate_payload(), indent=2) + "\n", encoding="utf-8")
    selected_candidate_sha = hashlib.sha256(selected_candidate_path.read_bytes()).hexdigest()
    pose_binding = pose_fixture.candidate_pose_provenance(selected_candidate_path, root=tmp_path)
    expression_binding = pose_fixture.candidate_expression_provenance(
        selected_candidate_path,
        root=tmp_path,
    )
    pose_bound_packet = pose_fixture.authoritatively_bind_packet(
        packet_report,
        pose_binding=pose_binding,
        expression_binding=expression_binding,
    )
    pose_bound_packet_sha = hashlib.sha256(
        json.dumps(
            pose_bound_packet,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    learning_repo_path = Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_repo_path = Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_next_generation_step_{DATE}.json"
    queue_repo_path = Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    reconciliation_repo_path = Path("pipeline/strategy/lena/reconciliations") / DATE / "lena_generation_reconciliation_fixture.json"
    learning_path = tmp_path / learning_repo_path
    recommendation_path = tmp_path / recommendation_repo_path
    queue_path = tmp_path / queue_repo_path
    reconciliation_path = tmp_path / reconciliation_repo_path
    learning_report = {
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
    recommendation_report = {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_artifact_path": learning_repo_path.as_posix(),
        "learning_status": "current",
        "learning_status_label": "learning_current",
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": 3,
        "learning_pending_metrics_count": 1,
        "learning_stale_pending_metrics_count": 1,
        "learning_resolution_state_summary": learning_report["metrics_resolution_summary"],
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
    queue_report = {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "date": DATE,
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
    }
    _write_json(learning_path, learning_report)
    _write_json(recommendation_path, recommendation_report)
    _write_json(queue_path, queue_report)
    learning_sha256 = hashlib.sha256(learning_path.read_bytes()).hexdigest()
    recommendation_sha256 = hashlib.sha256(recommendation_path.read_bytes()).hexdigest()
    selected_sha256 = hashlib.sha256(selected_candidate_path.read_bytes()).hexdigest()
    reconciliation_report = {
        "report_type": "lena_generation_reconciliation",
        "schema_version": "lena_generation_reconciliation_v1",
        "date": DATE,
        "generated_at": "2026-07-15T12:00:00+00:00",
        "source_revision": "085620d1",
        "source_revision_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
        "source_artifacts": {
            "learning": {
                "source_artifact_path": learning_repo_path.as_posix(),
                "source_artifact_sha256": learning_sha256,
            },
            "recommendation": {
                "source_artifact_path": recommendation_repo_path.as_posix(),
                "source_artifact_sha256": recommendation_sha256,
            },
            "selected_candidate": {
                "source_artifact_path": selected_candidate_repo_path.as_posix(),
                "source_artifact_sha256": selected_sha256,
            },
        },
        "learning_status": "current",
        "recommendation_recipe_id": "hcr_011",
        "recommendation_outfit_id": "wc_p059",
        "recommendation_environment_id": "env_p001",
        "recommendation_action_type": "collect_first_controlled_proof",
        "selected_candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
        "selected_candidate_recipe_id": "hcr_011",
        "selected_candidate_slot_id": ORIGINAL_SLOT,
        "selected_candidate_hook_id": "cbn_004",
        "selected_candidate_prompt_sha256": PROMPT_SHA,
        "divergence_status": "aligned",
        "resolution_policy": "selected_candidate_authoritative",
        "reconciliation_status": "reconciled",
        "operator_review_required": False,
        "final_reconciled_candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
        "final_reconciled_candidate_recipe_id": "hcr_011",
        "final_reconciled_candidate_slot_id": ORIGINAL_SLOT,
        "final_reconciled_candidate_hook_id": "cbn_004",
        "final_reconciled_candidate_prompt_sha256": PROMPT_SHA,
        "final_reconciled_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "final_reconciled_candidate_artifact_sha256": selected_sha256,
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
    }
    _write_json(reconciliation_path, reconciliation_report)
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
        "selected_recipe_id": "hcr_011",
        "expected_handoff_artifact_path": handoff_repo_path.as_posix(),
        "source_selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "source_selected_candidate_artifact_sha256": selected_candidate_sha,
        "source_learning_artifact_path": learning_repo_path.as_posix(),
        "source_learning_artifact_sha256": learning_sha256,
        "source_recommendation_artifact_path": recommendation_repo_path.as_posix(),
        "source_recommendation_artifact_sha256": recommendation_sha256,
        "source_queue_dry_run_artifact_path": queue_repo_path.as_posix(),
        "source_queue_dry_run_artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        "source_reconciliation_artifact_path": reconciliation_repo_path.as_posix(),
        "source_reconciliation_artifact_sha256": hashlib.sha256(reconciliation_path.read_bytes()).hexdigest(),
        "source_reconciliation_decision_artifact_path": None,
        "source_reconciliation_decision_artifact_sha256": None,
        "selected_candidate": {
            "artifact_path": selected_candidate_repo_path.as_posix(),
            "artifact_sha256": selected_candidate_sha,
            "candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
            "slot_id": ORIGINAL_SLOT,
            "recipe_id": "hcr_011",
            "prompt_sha256": PROMPT_SHA,
            "schema_version": "lena_pre_generation_candidate_gate_v1",
            "candidate_status": "selected",
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
            "expression_gaze_id": expression_binding["expression_gaze_id"],
            "expression_gaze_label": expression_binding["expression_gaze_label"],
        },
        "candidate_selection_binding": {
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
            "slot_id": ORIGINAL_SLOT,
            "recipe_id": "hcr_011",
            "candidate_prompt_sha256": PROMPT_SHA,
            "candidate_lane": "fit_check_mirror_getting_ready",
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_body_language_label": pose_binding["pose_body_language_label"],
            "pose_provenance_fingerprint_sha256": pose_binding[
                "pose_provenance_fingerprint_sha256"
            ],
            "expression_gaze_id": expression_binding["expression_gaze_id"],
            "expression_gaze_label": expression_binding["expression_gaze_label"],
            "expression_provenance_fingerprint_sha256": expression_binding[
                "expression_provenance_fingerprint_sha256"
            ],
            "source_prompt_family": "prompt_library_candidate",
        },
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha,
        "expression_provenance": expression_binding,
        "expression_bound_content_packet_sha256": pose_bound_packet_sha,
        "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
        "selected_prompt_input_artifact_sha256": packet_sha,
        "selected_prompt_input": {
            "artifact_path": packet_repo_path.as_posix(),
            "artifact_sha256": packet_sha,
            "prompt_sha256": PROMPT_SHA,
            "prompt_text": ORIGINAL_PROMPT,
            "lane": "fit_check_mirror_getting_ready",
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": pose_bound_packet_sha,
        },
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
            "selected_prompt_input_artifact_sha256": packet_sha,
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": pose_bound_packet_sha,
        },
        "provider_execution_binding": {
            "content_packet_artifact_path": packet_repo_path.as_posix(),
            "content_packet_artifact_sha256": packet_sha,
            "recipe_id": "hcr_011",
            "slot_id": ORIGINAL_SLOT,
            "provider_prompt_sha256": PROMPT_SHA,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha,
            "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
            "expression_bound_content_packet_sha256": pose_bound_packet_sha,
            "expression_provenance_fingerprint_sha256": expression_binding[
                "expression_provenance_fingerprint_sha256"
            ],
            "provider_lane": "fit_check_mirror_getting_ready",
            "source_prompt_family": "compact_provider_prompt",
            "provider": "higgsfield",
            "model": "text2image_soul_v2",
        },
        "binding_linkage": {
            "recommendation_artifact_path": recommendation_repo_path.as_posix(),
            "recommendation_artifact_sha256": recommendation_sha256,
            "queue_artifact_path": queue_repo_path.as_posix(),
            "queue_artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "content_packet_artifact_path": packet_repo_path.as_posix(),
            "content_packet_artifact_sha256": packet_sha,
            "recipe_id": "hcr_011",
            "slot_id": ORIGINAL_SLOT,
            "candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
            "outfit_id": packet_report["wardrobe_outfit_id"],
            "environment_id": packet_report["environment_id"],
            "candidate_lane": "fit_check_mirror_getting_ready",
            "provider_lane": "fit_check_mirror_getting_ready",
            "candidate_prompt_family": "prompt_library_candidate",
            "provider_prompt_family": "compact_provider_prompt",
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_bound_content_packet_sha256": pose_bound_packet_sha,
            "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
            "expression_gaze_id": expression_binding["expression_gaze_id"],
            "expression_provenance_fingerprint_sha256": expression_binding[
                "expression_provenance_fingerprint_sha256"
            ],
            "expression_bound_content_packet_sha256": pose_bound_packet_sha,
            "prompt_family_relationship": (
                "candidate prompt family and provider prompt family are intentionally "
                "distinct for the same recipe/slot chain"
            ),
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
        "date": DATE,
        "slot_id": ORIGINAL_SLOT,
        "lane": "fit_check_mirror_getting_ready",
        "prompt_sha256": PROMPT_SHA,
        "image_prompt": ORIGINAL_PROMPT,
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_body_language_label": pose_binding["pose_body_language_label"],
        "pose_text": pose_binding["pose_text"],
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_artifact_path": packet_repo_path.as_posix(),
        "pose_bound_content_packet_artifact_sha256": packet_sha,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha,
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_gaze_label": expression_binding["expression_gaze_label"],
        "expression_text": expression_binding["expression_text"],
        "expression_safe_fallback_used": expression_binding[
            "expression_safe_fallback_used"
        ],
        "expression_safe_fallback_reason": expression_binding[
            "expression_safe_fallback_reason"
        ],
        "expression_scene_conflict_terms": expression_binding[
            "expression_scene_conflict_terms"
        ],
        "expression_provenance": expression_binding,
        "expression_bound_content_packet_artifact_path": packet_repo_path.as_posix(),
        "expression_bound_content_packet_artifact_sha256": packet_sha,
        "expression_bound_content_packet_sha256": pose_bound_packet_sha,
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
        "candidate_selection_binding": handoff_report["candidate_selection_binding"],
        "provider_execution_binding": handoff_report["provider_execution_binding"],
        "binding_linkage": handoff_report["binding_linkage"],
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
    return {
        "handoff_path": handoff_path,
        "receipt_path": receipt_path,
        "packet_path": packet_path,
        "manifest_path": manifest_path,
        "image_path": image_path,
    }


def _refresh_bound_packet_evidence(seeded: dict[str, Path]) -> None:
    packet = json.loads(seeded["packet_path"].read_text(encoding="utf-8"))
    packet_sha = hashlib.sha256(seeded["packet_path"].read_bytes()).hexdigest()
    handoff = json.loads(seeded["handoff_path"].read_text(encoding="utf-8"))
    bound_packet = pose_fixture.authoritatively_bind_packet(packet, pose_binding=handoff["pose_provenance"])
    bound_packet_sha = hashlib.sha256(
        json.dumps(bound_packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    handoff["selected_prompt_input_artifact_sha256"] = packet_sha
    handoff["selected_prompt_input"]["artifact_sha256"] = packet_sha
    handoff["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["selected_prompt_input"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["structured_executor_inputs"]["selected_prompt_input_artifact_sha256"] = packet_sha
    handoff["structured_executor_inputs"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["provider_execution_binding"]["content_packet_artifact_sha256"] = packet_sha
    handoff["provider_execution_binding"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["binding_linkage"]["content_packet_artifact_sha256"] = packet_sha
    handoff["binding_linkage"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    _write_json(seeded["handoff_path"], handoff)
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    manifest["pose_bound_content_packet_artifact_sha256"] = packet_sha
    manifest["pose_bound_content_packet_sha256"] = bound_packet_sha
    _write_json(seeded["manifest_path"], manifest)
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["handoff_artifact_sha256"] = hashlib.sha256(
        seeded["handoff_path"].read_bytes()
    ).hexdigest()
    _write_json(seeded["receipt_path"], receipt)


def test_build_and_validate_retry_handoff_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)

    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=True,
    )
    artifact_path = Path(report["retry_handoff_artifact_path"])
    assert report["state"] == "retry_handoff_written"
    assert artifact_path.is_file()
    assert report["original_slot_id"] == ORIGINAL_SLOT
    assert report["retry_slot_id"] == RETRY_SLOT

    artifact = retry_mod.validate_retry_handoff_artifact(artifact_path)
    prompt = artifact["retry_prompt_text"]
    assert prompt.count("[Subject Presence]:") == 1
    assert packet_builder.HPE_SUBJECT_PRESENCE_COMPACT in prompt
    assert prompt.index("[Subject]:") < prompt.index("[Subject Presence]:") < prompt.index("[Action]:") < prompt.index("[Environment]:") < prompt.index("[Cinematography]:") < prompt.index("[Lighting/Style]:") < prompt.index("[Technical]:")
    assert report["retry_prompt_headroom_status"] == retry_mod._headroom_status(
        artifact["retry_prompt_budget"] - len(prompt)
    )
    assert artifact["retry_prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert "Mirror-selfie phone visibility is acceptable" not in prompt
    assert "No foreground phone, visible device screens, or direct posed full-torso portrait." in prompt
    assert "chest-up or waist-up framing only" in prompt
    assert "Hips, thighs, and the dress hemline never appear" in prompt
    assert f"[Action]: {pose_fixture.POSE_TEXT}" in prompt
    assert "actively checking or adjusting one gold hoop earring" not in prompt
    assert "must read as a real getting-ready vanity moment" in prompt
    assert "No fake freckles or poreless/plastic skin." in prompt
    assert "slightly fuller is okay, not a hard gate" in prompt
    assert len(prompt) <= prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    assert artifact["retry_prompt_budget"] == prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    assert artifact["retry_prompt_length"] == len(prompt)
    assert artifact["retry_prompt_headroom"] == (
        prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS - len(prompt)
    )
    assert artifact["retry_prompt_headroom"] >= 70
    assert artifact["retry_prompt_headroom_policy"] == {"hard_block_below": 30, "warning_below": 70}
    assert artifact["retry_prompt_headroom_status"] == "ready"
    source_handoff = json.loads(seeded["handoff_path"].read_text(encoding="utf-8"))
    assert artifact["pose_provenance"] == source_handoff["pose_provenance"]
    assert artifact["source_pose_bound_content_packet_sha256"] == source_handoff["pose_bound_content_packet_sha256"]


@pytest.mark.parametrize("block", approval_mod.AUTHORITY_BLOCK_KEYS)
def test_retry_source_receipt_requires_complete_authority_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    block: str,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt.pop(block)
    _write_json(seeded["receipt_path"], receipt)

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.evaluate_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
            write_artifact=False,
        )
    assert excinfo.value.code == f"receipt_{block}_missing"


@pytest.mark.parametrize(
    "reason_code",
    ["background_identity_duplication", "hair_crown_forelock_artifact"],
)
def test_null_pose_source_manifest_cannot_seed_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason_code: str,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    manifest["pose_provenance"] = None
    manifest["pose_body_language_id"] = None
    manifest["pose_body_language_label"] = None
    manifest["pose_text"] = None
    _write_json(seeded["manifest_path"], manifest)
    soul = (
        {"id": "current", "name": "Lena", "type": "soul_2", "status": "completed"}
        if reason_code == "hair_crown_forelock_artifact"
        else None
    )

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
            reason_code=reason_code,
            soul_record=soul,
        )
    assert excinfo.value.code == "pose_provenance_missing"


@pytest.mark.parametrize(
    "reason_code",
    ["background_identity_duplication", "hair_crown_forelock_artifact"],
)
def test_null_expression_source_manifest_cannot_seed_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason_code: str,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    manifest["expression_provenance"] = None
    manifest["expression_gaze_id"] = None
    manifest["expression_gaze_label"] = None
    manifest["expression_text"] = None
    _write_json(seeded["manifest_path"], manifest)
    soul = (
        {"id": "current", "name": "Lena", "type": "soul_2", "status": "completed"}
        if reason_code == "hair_crown_forelock_artifact"
        else None
    )

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
            reason_code=reason_code,
            soul_record=soul,
        )
    assert excinfo.value.code == "expression_provenance_missing"


def test_source_manifest_pose_binding_must_match_source_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    changed = dict(manifest["pose_provenance"])
    changed["selected_candidate_artifact_sha256"] = "9" * 64
    core = {
        key: value
        for key, value in changed.items()
        if key != "pose_provenance_fingerprint_sha256"
    }
    changed["pose_provenance_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    manifest["pose_provenance"] = changed
    _write_json(seeded["manifest_path"], manifest)

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        )
    assert excinfo.value.code == "manifest_pose_provenance_mismatch"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda manifest: manifest["pose_provenance"].pop("pose_text"), "pose_provenance_incomplete"),
        (lambda manifest: manifest.update(pose_body_language_id="pose_conflict"), "manifest_pose_provenance_mismatch"),
        (lambda manifest: manifest.update(pose_bound_content_packet_sha256="f" * 64), "manifest_pose_bound_packet_mismatch"),
    ],
)
def test_partial_flat_or_packet_digest_source_pose_contract_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    code: str,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    mutation(manifest)
    _write_json(seeded["manifest_path"], manifest)

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        )
    assert excinfo.value.code == code


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda manifest: manifest["expression_provenance"].pop("expression_text"),
            "expression_provenance_incomplete",
        ),
        (
            lambda manifest: manifest.update(expression_gaze_id="expression_conflict"),
            "manifest_expression_provenance_mismatch",
        ),
        (
            lambda manifest: manifest.update(expression_bound_content_packet_sha256="f" * 64),
            "manifest_expression_bound_packet_mismatch",
        ),
    ],
)
def test_partial_flat_or_packet_digest_source_expression_contract_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    code: str,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    mutation(manifest)
    _write_json(seeded["manifest_path"], manifest)

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        )
    assert excinfo.value.code == code


def test_hair_retry_handoff_binds_current_completed_soul_and_preserves_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    packet = json.loads(seeded["packet_path"].read_text(encoding="utf-8"))
    packet["compact_provider_prompt_budget"] = 4096
    seeded["packet_path"].write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    handoff = json.loads(seeded["handoff_path"].read_text(encoding="utf-8"))
    packet_sha = hashlib.sha256(seeded["packet_path"].read_bytes()).hexdigest()
    bound_packet = pose_fixture.authoritatively_bind_packet(packet, pose_binding=handoff["pose_provenance"])
    bound_packet_sha = hashlib.sha256(
        json.dumps(bound_packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    handoff["selected_prompt_input_artifact_sha256"] = packet_sha
    handoff["selected_prompt_input"]["artifact_sha256"] = packet_sha
    handoff["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["selected_prompt_input"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["structured_executor_inputs"]["selected_prompt_input_artifact_sha256"] = packet_sha
    handoff["structured_executor_inputs"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["provider_execution_binding"]["content_packet_artifact_sha256"] = packet_sha
    handoff["provider_execution_binding"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    handoff["binding_linkage"]["content_packet_artifact_sha256"] = packet_sha
    handoff["binding_linkage"]["pose_bound_content_packet_sha256"] = bound_packet_sha
    seeded["handoff_path"].write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(seeded["manifest_path"].read_text(encoding="utf-8"))
    manifest["pose_bound_content_packet_artifact_sha256"] = packet_sha
    manifest["pose_bound_content_packet_sha256"] = bound_packet_sha
    seeded["manifest_path"].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["handoff_artifact_sha256"] = hashlib.sha256(seeded["handoff_path"].read_bytes()).hexdigest()
    seeded["receipt_path"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    current_soul = {
        "id": "e45ec580-a6db-4063-a9b2-f9163856daae",
        "name": "Lena",
        "type": "soul_2",
        "status": "completed",
    }

    path, artifact = retry_mod.build_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        reason_code="hair_crown_forelock_artifact",
        soul_record=current_soul,
    )
    retry_mod.write_retry_handoff_artifact(path, artifact)
    validated = retry_mod.validate_retry_handoff_artifact(path)

    assert validated["retry_purpose"] == "hair_crown_forelock_contract_repair"
    assert validated["reason_code"] == "hair_crown_forelock_artifact"
    assert validated["custom_reference_id"] == current_soul["id"]
    assert validated["soul_name"] == "Lena"
    assert validated["soul_type"] == "soul_2"
    assert validated["retry_soul_binding"] == current_soul
    assert validated["historical_custom_reference_id"] == CUSTOM_REFERENCE_ID
    assert retry_mod.HAIR_CROWN_CONSTRAINT in validated["retry_prompt_text"]
    assert validated["retry_constraints"]["only_hair_crown_defect_may_change"] is True
    assert validated["retry_constraints"]["preserve"] == retry_mod.HAIR_CROWN_PRESERVES
    assert validated["pose_provenance"] == handoff["pose_provenance"]
    assert f"[Action]: {handoff['pose_provenance']['pose_text']}" in validated["retry_prompt_text"]


@pytest.mark.parametrize(
    ("records", "code"),
    [
        ([], "soul_resolution_ambiguous"),
        ([{"id": "x", "name": "Lena", "type": "soul_2", "status": "processing"}], "soul_resolution_ambiguous"),
        ([{"id": "x", "name": "Other", "type": "soul_2", "status": "completed"}], "soul_resolution_ambiguous"),
        ([{"id": "x", "name": "Lena", "type": "soul_1", "status": "completed"}], "soul_resolution_ambiguous"),
        (
            [
                {"id": "x", "name": "Lena", "type": "soul_2", "status": "completed"},
                {"id": "y", "name": "Lena", "type": "soul_2", "status": "completed"},
            ],
            "soul_resolution_ambiguous",
        ),
    ],
)
def test_current_soul_resolution_fails_closed(records: list[dict], code: str) -> None:
    class Completed:
        returncode = 0
        stdout = json.dumps(records)
        stderr = ""

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.resolve_current_lena_soul(cli_runner=lambda *args, **kwargs: Completed())
    assert excinfo.value.code == code


def test_current_soul_resolution_accepts_single_completed_lena_soul_2() -> None:
    expected = {"id": "e45ec580-a6db-4063-a9b2-f9163856daae", "name": "Lena", "type": "soul_2", "status": "completed"}

    class Completed:
        returncode = 0
        stdout = json.dumps([expected])
        stderr = ""

    assert retry_mod.resolve_current_lena_soul(cli_runner=lambda *args, **kwargs: Completed()) == expected


def test_retry_handoff_fails_closed_on_receipt_prompt_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["prompt_sha256"] = "0" * 64
    seeded["receipt_path"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
        )
    assert excinfo.value.code == "receipt_prompt_sha_mismatch"


def test_retry_handoff_warns_but_allows_below_configured_warning_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    headroom = (
        prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
        - len(retry_mod._replace_sections(ORIGINAL_PROMPT))
    )
    monkeypatch.setattr(retry_mod.readiness_audit, "PAYLOAD_HEADROOM_HARD_BLOCK_BELOW", headroom - 1)
    monkeypatch.setattr(retry_mod.readiness_audit, "PAYLOAD_HEADROOM_WARNING_BELOW", headroom + 1)

    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=False,
    )
    assert report["retry_prompt_headroom"] == headroom
    assert report["retry_prompt_headroom_status"] == "warning"
    assert report["retry_prompt_headroom_policy"] == {
        "hard_block_below": headroom - 1,
        "warning_below": headroom + 1,
    }


def test_retry_handoff_fails_closed_below_configured_hard_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    headroom = (
        prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
        - len(retry_mod._replace_sections(ORIGINAL_PROMPT))
    )
    monkeypatch.setattr(retry_mod.readiness_audit, "PAYLOAD_HEADROOM_HARD_BLOCK_BELOW", headroom + 1)

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        )
    assert excinfo.value.code == "retry_prompt_headroom_too_low"


def test_executor_accepts_new_retry_handoff_artifact_in_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=True,
    )
    artifact_path = Path(report["retry_handoff_artifact_path"])
    retry_artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    bound_pose = retry_artifact["pose_provenance"]
    bound_expression = retry_artifact["expression_provenance"]

    def fake_validate_handoff_packet(path: Path):
        source = {
            "resolver": "content_packet_dryrun",
            "slot_prefix": "hcr_011",
            "pack_count": 1,
            "pack_variety_warnings": [],
            "image": {
                "slot_id": ORIGINAL_SLOT,
                "lane": "fit_check_mirror_getting_ready",
                "image_prompt": ORIGINAL_PROMPT,
                "pose_body_language_id": bound_pose["pose_body_language_id"],
                "pose_body_language_label": bound_pose["pose_body_language_label"],
                "pose_text": bound_pose["pose_text"],
                "pose_provenance": bound_pose,
                "expression_gaze_id": bound_expression["expression_gaze_id"],
                "expression_gaze_label": bound_expression["expression_gaze_label"],
                "expression_text": bound_expression["expression_text"],
                "expression_provenance": bound_expression,
            },
        }
        return ({}, source, {}, {"ok": True, "prompt_matches_expected": None, "hard_exclude_reasons": [], "all_reasons": []})

    monkeypatch.setattr(executor, "_validate_handoff_packet", fake_validate_handoff_packet)
    monkeypatch.setattr(
        executor,
        "validate_candidate",
        lambda source, expected: {"ok": True, "prompt_matches_expected": None, "hard_exclude_reasons": [], "all_reasons": []},
    )
    monkeypatch.setattr(sys, "argv", ["executor", "--retry-decision-artifact", str(artifact_path)])
    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===" in stdout
    assert f"slot_id                 : {RETRY_SLOT}" in stdout
    assert "validation ok           : True" in stdout
    assert "no subprocess call, no network call, no file written" in stdout
