from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pipeline.higgsfield_lena_api_executor as executor
import tools.lena_higgsfield_generation_approval_v1 as approval_mod
import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff_builder
import tools.strategy.lena_reconciliation_contract_v1 as reconciliation_contract
import tools.strategy.lena_record_generation_reconciliation_decision_v1 as decision_mod


DATE = "2026-07-15"
RECOMMENDATION_RECIPE_ID = "hcr_011"
SELECTED_RECIPE_ID = "hcr_006"
SLOT_ID = "higgsfield-20260715-hcr_006-photo"
SELECTED_CANDIDATE_ID = f"{SLOT_ID}::{SELECTED_RECIPE_ID}::cbn_004"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
PROMPT_TEXT = "Scene: candlelit arrival. Wardrobe: structured black set. Lighting: realistic low-light skin texture."


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
    monkeypatch.setattr(approval_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        approval_mod,
        "DEFAULT_APPROVAL_ROOT",
        tmp_root / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_root)
    monkeypatch.setattr(decision_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        decision_mod,
        "DECISIONS_ROOT",
        tmp_root / "pipeline" / "strategy" / "lena" / "reconciliation_decisions",
    )


def _learning_payload() -> dict:
    return {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": DATE,
        "published_post_count": 3,
        "pending_metrics_posts": [{}],
        "stale_pending_metrics_posts": [{}],
        "winner_posts": [{"recipe_id": RECOMMENDATION_RECIPE_ID}],
        "queue_boosts": {"preferred_recipe_ids": [RECOMMENDATION_RECIPE_ID]},
        "metrics_resolution_summary": {
            "learning_status": "current",
            "current_count": 2,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0,
        },
    }


def _recommendation_payload(learning_path: Path) -> dict:
    learning = _learning_payload()
    return {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_artifact_path": learning_path.as_posix(),
        "learning_status": "current",
        "learning_status_label": "learning_current",
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": learning["published_post_count"],
        "learning_pending_metrics_count": len(learning["pending_metrics_posts"]),
        "learning_stale_pending_metrics_count": len(learning["stale_pending_metrics_posts"]),
        "learning_resolution_state_summary": learning["metrics_resolution_summary"],
        "learning_required_follow_up_action": "no_follow_up_required",
        "learning_winner_post_count": len(learning["winner_posts"]),
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": RECOMMENDATION_RECIPE_ID,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids", "winner_posts"],
            "next_live_gate": "review",
        },
    }


def _queue_payload() -> dict:
    return {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "date": DATE,
        "dry_run": True,
        "proof_lane_lock": {
            "action_type": "collect_first_controlled_proof",
            "recipe_id": RECOMMENDATION_RECIPE_ID,
            "outfit_id": "wc_p059",
            "environment_id": "env_p001",
            "next_live_gate": "review",
        },
        "proof_lane_lock_active": True,
        "queue_slots": [
            {
                "recipe_id": RECOMMENDATION_RECIPE_ID,
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


def _packet_payload() -> dict:
    prompt_sha = hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
    return {
        "report_type": "lena_content_packet_dryrun",
        "schema_version": "v1",
        "packet_id": f"cpkt_{DATE.replace('-', '')}_{SELECTED_RECIPE_ID}",
        "generated_date": DATE,
        "generator": "lena_build_content_packet_dryrun_v1",
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "publishing_approval": "not_approved",
        "recipe_id": SELECTED_RECIPE_ID,
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
        "compact_provider_prompt_preview": PROMPT_TEXT,
        "compact_provider_prompt_chars": len(PROMPT_TEXT),
        "compact_provider_prompt_budget": 2499,
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


def _selected_candidate_payload() -> dict:
    prompt_sha = hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": "2ed48fd29215ffc499b64f15255f6c4038bf484a",
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": SELECTED_CANDIDATE_ID,
            "slot_id": SLOT_ID,
            "lane": "parking_garage_flash",
            "recipe_id": SELECTED_RECIPE_ID,
            "hook_id": "cbn_004",
            "prompt_sha256": prompt_sha,
            "pose_body_language_id": "pose_p018",
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {SLOT_ID}",
        },
        "decision_fingerprint_sha256": "5" * 64,
        "generated_at_utc": "2026-07-15T12:34:57Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    }


def _reconciliation_payload(tmp_root: Path) -> tuple[dict, dict[str, Path]]:
    next_actions = tmp_root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    packets = tmp_root / "pipeline" / "strategy" / "lena" / "content_packets" / DATE
    pre_generation = tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    reconciliations = tmp_root / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    packet_path = packets / f"lena_content_packet_dryrun_{DATE}_{SELECTED_RECIPE_ID}.json"
    selected_candidate_path = pre_generation / "lena_pre_generation_candidate_selected.json"
    reconciliation_path = reconciliations / "lena_generation_reconciliation_fixture.json"

    learning = _learning_payload()
    recommendation = _recommendation_payload(learning_path)
    queue = _queue_payload()
    packet = _packet_payload()
    selected_candidate = _selected_candidate_payload()

    for path, payload in (
        (learning_path, learning),
        (recommendation_path, recommendation),
        (queue_path, queue),
        (packet_path, packet),
        (selected_candidate_path, selected_candidate),
    ):
        _write_json(path, payload)
    rebuilt_packet, rebuilt_source = executor._rebuild_packet_prompt_source(packet_path)
    actual_prompt = str(rebuilt_source.get("image", {}).get("image_prompt") or "")
    packet["compact_provider_prompt_preview"] = actual_prompt
    packet["compact_provider_prompt_sha256"] = hashlib.sha256(actual_prompt.encode("utf-8")).hexdigest()
    _write_json(packet_path, packet)
    selected_candidate["candidate"]["prompt_sha256"] = packet["compact_provider_prompt_sha256"]
    _write_json(selected_candidate_path, selected_candidate)
    learning_sha256 = reconciliation_contract.sha256_file(learning_path)
    recommendation_sha256 = reconciliation_contract.sha256_file(recommendation_path)
    selected_sha256 = reconciliation_contract.sha256_file(selected_candidate_path)

    reconciliation = {
        "report_type": "lena_generation_reconciliation",
        "schema_version": "lena_generation_reconciliation_v1",
        "date": DATE,
        "generated_at": "2026-07-15T12:00:00+00:00",
        "source_revision": "2ed48fd2",
        "source_revision_commit": "2ed48fd29215ffc499b64f15255f6c4038bf484a",
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
        "recommendation_recipe_id": RECOMMENDATION_RECIPE_ID,
        "recommendation_outfit_id": "wc_p059",
        "recommendation_environment_id": "env_p001",
        "recommendation_action_type": "collect_first_controlled_proof",
        "selected_candidate_id": SELECTED_CANDIDATE_ID,
        "selected_candidate_recipe_id": SELECTED_RECIPE_ID,
        "selected_candidate_slot_id": SLOT_ID,
        "selected_candidate_hook_id": "cbn_004",
        "selected_candidate_prompt_sha256": packet["compact_provider_prompt_sha256"],
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
    }
    _write_json(reconciliation_path, reconciliation)
    return reconciliation, {
        "learning_path": learning_path,
        "recommendation_path": recommendation_path,
        "queue_path": queue_path,
        "packet_path": packet_path,
        "selected_candidate_path": selected_candidate_path,
        "reconciliation_path": reconciliation_path,
    }


def _write_decision_with_timestamps(
    *,
    reconciliation: dict,
    reconciliation_repo_path: str,
    generated_at_utc: str,
    expires_at_utc: str,
) -> Path:
    confirmation = decision_mod.expected_confirmation_phrase(reconciliation)
    decision_report = decision_mod.build_generation_reconciliation_decision(
        reconciliation_repo_path,
        "nicolas",
        SELECTED_CANDIDATE_ID,
        SELECTED_RECIPE_ID,
        SLOT_ID,
        confirmation,
    )
    decision_path, _, _ = decision_mod.write_report(decision_report, DATE)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["generated_at_utc"] = generated_at_utc
    decision["expires_at_utc"] = expires_at_utc
    decision["decision_expires_at_utc"] = expires_at_utc
    _write_json(decision_path, decision)
    return decision_path


@pytest.fixture(autouse=True)
def _forbid_live_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider subprocess must not run")))
    monkeypatch.setattr(executor, "run_live", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_live must not run")))


def test_report_only_reconciliation_flow_binds_handoff_and_blocks_live_without_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    reconciliation, paths = _reconciliation_payload(tmp_path)
    reconciliation_repo_path = paths["reconciliation_path"].relative_to(tmp_path).as_posix()

    confirmation = decision_mod.expected_confirmation_phrase(reconciliation)
    decision_report = decision_mod.build_generation_reconciliation_decision(
        reconciliation_repo_path,
        "nicolas",
        SELECTED_CANDIDATE_ID,
        SELECTED_RECIPE_ID,
        SLOT_ID,
        confirmation,
    )
    decision_path, written_decision, reused = decision_mod.write_report(decision_report, DATE)

    handoff_report = handoff_builder.build_handoff(
        DATE,
        reconciliation_repo_path,
        decision_path.relative_to(tmp_path).as_posix(),
    )
    handoff_path, markdown_path = handoff_builder.save_handoff(handoff_report, DATE)

    synthetic_packet_report = {
        "report_type": "lena_content_packet_dryrun",
        "schema_version": "v1",
        "generated_date": DATE,
        "recipe_id": SELECTED_RECIPE_ID,
        "packet_id": f"cpkt_{DATE.replace('-', '')}_{SELECTED_RECIPE_ID}",
        "compact_provider_prompt_preview": PROMPT_TEXT,
        "compact_provider_prompt_sha256": hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest(),
        "strong_hook_id": "cbn_004",
        "hook_text": "Tried To Dress Down. Failed.",
        "caption_draft": "caught me on the way in",
    }
    synthetic_source = {
        "resolver": "synthetic",
        "slot_prefix": SELECTED_RECIPE_ID,
        "pack_count": 1,
        "pack_variety_warnings": [],
        "slot_id": SLOT_ID,
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
        "image_prompt": PROMPT_TEXT,
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
        }
    inspected = approval_mod.inspect_handoff_artifact(handoff_path)

    assert reused is False
    assert decision_path.is_file()
    assert handoff_path.is_file()
    assert markdown_path.is_file()
    assert inspected["selected_candidate_recipe_id"] == SELECTED_RECIPE_ID
    assert inspected["reconciled_candidate"]["recipe_id"] == SELECTED_RECIPE_ID
    assert inspected["reconciliation"]["reconciliation_status"] == "operator_review_required"
    assert inspected["reconciliation"]["decision_required"] is True
    assert inspected["reconciliation_decision"]["authority_scope"] == "handoff_preparation_only"
    assert inspected["reconciliation_decision"]["live_generation_authorized"] is False
    assert inspected["reconciliation_decision"]["publishing_authorized"] is False
    assert handoff_report["source_recommendation"]["recommended_recipe_id"] == RECOMMENDATION_RECIPE_ID
    assert handoff_report["reconciled_candidate"]["recipe_id"] == SELECTED_RECIPE_ID
    assert handoff_report["selected_candidate"]["candidate_id"] == SELECTED_CANDIDATE_ID
    assert handoff_report["selected_candidate"]["recipe_id"] == SELECTED_RECIPE_ID
    assert handoff_report["selected_candidate"]["slot_id"] == SLOT_ID
    assert handoff_report["reconciled_candidate"]["recipe_id"] == SELECTED_RECIPE_ID
    assert handoff_report["reconciled_candidate"]["slot_id"] == SLOT_ID
    assert handoff_report["source_recommendation_artifact_path"] == paths["recommendation_path"].relative_to(tmp_path).as_posix()
    assert handoff_report["source_selected_candidate_artifact_path"] == paths["selected_candidate_path"].relative_to(tmp_path).as_posix()
    rebuilt_packet, rebuilt_source = executor._rebuild_packet_prompt_source(paths["packet_path"])
    assert rebuilt_packet["recipe_id"] == SELECTED_RECIPE_ID
    assert rebuilt_source["image"]["slot_id"] == f"higgsfield-{DATE.replace('-', '')}-{SELECTED_RECIPE_ID}-photo"
    assert isinstance(rebuilt_source["image"]["image_prompt"], str)
    assert rebuilt_source["image"]["image_prompt"]
    assert approval_mod.approval_output_path(DATE, SLOT_ID).exists() is False
    assert approval_mod.claim_output_path(DATE, SLOT_ID).exists() is False
    assert approval_mod.receipt_output_path(DATE, SLOT_ID).exists() is False
    assert executor.manifest_path(DATE, SLOT_ID).exists() is False

    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(handoff_path), "--live"])
    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "handoff_slot_mismatch" not in stdout
    assert "[ABORT] --live with --handoff-artifact requires a valid --approval-artifact." in stdout
    assert "The handoff remains review-only and is never rewritten into live authorization." in stdout
    assert approval_mod.approval_output_path(DATE, SLOT_ID).exists() is False
    assert approval_mod.claim_output_path(DATE, SLOT_ID).exists() is False
    assert approval_mod.receipt_output_path(DATE, SLOT_ID).exists() is False
    assert executor.manifest_path(DATE, SLOT_ID).exists() is False


@pytest.mark.parametrize(
    ("generated_at_utc", "expires_at_utc", "now_utc", "expected_code"),
    [
        (
            "2026-07-15T12:00:00+00:00",
            "2026-07-15T12:30:00+00:00",
            datetime(2026, 7, 15, 12, 29, 59, tzinfo=timezone.utc),
            None,
        ),
        (
            "2026-07-15T12:00:00+00:00",
            "2026-07-15T12:30:00+00:00",
            datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc),
            "reconciliation_decision_expired",
        ),
        (
            "2026-07-15T12:00:00+00:00",
            "2026-07-15T12:30:00+00:00",
            datetime(2026, 7, 15, 12, 30, 1, tzinfo=timezone.utc),
            "reconciliation_decision_expired",
        ),
        (
            "2020-01-01T00:00:00+00:00",
            "2020-01-01T00:30:00+00:00",
            datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc),
            "reconciliation_decision_expired",
        ),
    ],
)
def test_reconciliation_decision_wall_clock_expiry_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generated_at_utc: str,
    expires_at_utc: str,
    now_utc: datetime,
    expected_code: str | None,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    reconciliation, paths = _reconciliation_payload(tmp_path)
    reconciliation_repo_path = paths["reconciliation_path"].relative_to(tmp_path).as_posix()
    decision_path = _write_decision_with_timestamps(
        reconciliation=reconciliation,
        reconciliation_repo_path=reconciliation_repo_path,
        generated_at_utc=generated_at_utc,
        expires_at_utc=expires_at_utc,
    )

    if expected_code is None:
        loaded_path, loaded_report, loaded_sha256 = reconciliation_contract.load_reconciliation_decision(
            decision_path.relative_to(tmp_path).as_posix(),
            date_str=DATE,
            reconciliation_path=paths["reconciliation_path"],
            reconciliation_report=reconciliation,
            reconciliation_sha256=reconciliation_contract.sha256_file(paths["reconciliation_path"]),
            now_utc=now_utc,
        )
        assert loaded_path == decision_path
        assert loaded_report["decision_expires_at_utc"] == expires_at_utc
        assert loaded_sha256 == reconciliation_contract.sha256_file(decision_path)
    else:
        with pytest.raises(reconciliation_contract.ReconciliationContractError) as excinfo:
            reconciliation_contract.load_reconciliation_decision(
                decision_path.relative_to(tmp_path).as_posix(),
                date_str=DATE,
                reconciliation_path=paths["reconciliation_path"],
                reconciliation_report=reconciliation,
                reconciliation_sha256=reconciliation_contract.sha256_file(paths["reconciliation_path"]),
                now_utc=now_utc,
            )
        assert excinfo.value.code == expected_code


def test_aligned_reconciliation_rejects_supplied_decision_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    reconciliation, paths = _reconciliation_payload(tmp_path)
    reconciliation_repo_path = paths["reconciliation_path"].relative_to(tmp_path).as_posix()
    selected_candidate = json.loads(paths["selected_candidate_path"].read_text(encoding="utf-8"))["candidate"]
    recommendation = json.loads(paths["recommendation_path"].read_text(encoding="utf-8"))
    recommendation["recommendation"]["recommended_recipe_id"] = SELECTED_RECIPE_ID
    _write_json(paths["recommendation_path"], recommendation)
    queue = json.loads(paths["queue_path"].read_text(encoding="utf-8"))
    queue["proof_lane_lock"]["recipe_id"] = SELECTED_RECIPE_ID
    queue["queue_slots"][0]["recipe_id"] = SELECTED_RECIPE_ID
    _write_json(paths["queue_path"], queue)
    aligned_reconciliation = copy.deepcopy(reconciliation)
    aligned_reconciliation["recommendation_recipe_id"] = SELECTED_RECIPE_ID
    aligned_reconciliation["divergence_status"] = "aligned"
    aligned_reconciliation["resolution_policy"] = "selected_candidate_authoritative"
    aligned_reconciliation["reconciliation_status"] = "reconciled"
    aligned_reconciliation["operator_review_required"] = False
    aligned_reconciliation["final_reconciled_candidate_id"] = SELECTED_CANDIDATE_ID
    aligned_reconciliation["final_reconciled_candidate_recipe_id"] = SELECTED_RECIPE_ID
    aligned_reconciliation["final_reconciled_candidate_slot_id"] = SLOT_ID
    aligned_reconciliation["final_reconciled_candidate_hook_id"] = selected_candidate["hook_id"]
    aligned_reconciliation["final_reconciled_candidate_prompt_sha256"] = selected_candidate["prompt_sha256"]
    aligned_reconciliation["final_reconciled_candidate_artifact_path"] = paths["selected_candidate_path"].relative_to(tmp_path).as_posix()
    aligned_reconciliation["final_reconciled_candidate_artifact_sha256"] = reconciliation_contract.sha256_file(paths["selected_candidate_path"])
    aligned_reconciliation["exact_next_allowed_action"] = "build_next_live_image_handoff"
    aligned_reconciliation["next_allowed_action"] = {
        "status": "reconciled",
        "action": "build_next_live_image_handoff",
        "reason": "recommendation and selected candidate are aligned and may be handed off",
    }
    aligned_reconciliation["blocking_reasons"] = []
    aligned_reconciliation["source_artifacts"]["recommendation"]["source_artifact_sha256"] = reconciliation_contract.sha256_file(paths["recommendation_path"])
    _write_json(paths["reconciliation_path"], aligned_reconciliation)
    handoff_report = handoff_builder.build_handoff(DATE, reconciliation_repo_path)
    handoff_path, _ = handoff_builder.save_handoff(handoff_report, DATE)
    mutated_handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    mutated_handoff["source_reconciliation_decision_artifact_path"] = "pipeline/strategy/lena/reconciliation_decisions/2026-07-15/lena_generation_reconciliation_decision_dummy.json"
    mutated_handoff["source_reconciliation_decision_artifact_sha256"] = "1" * 64
    mutated_handoff["source_reconciliation_decision_id"] = "decision-id"
    mutated_handoff["source_reconciliation_decision_operator_id"] = "nicolas"
    mutated_handoff["source_reconciliation_decision_expires_at_utc"] = "2026-07-15T12:30:00+00:00"
    mutated_handoff["source_reconciliation_decision_authority_scope"] = "handoff_preparation_only"
    mutated_handoff["source_reconciliation_decision_live_generation_authorized"] = False
    mutated_handoff["source_reconciliation_decision_publishing_authorized"] = False
    mutated_handoff["source_reconciliation_decision_next_allowed_action"] = "build_next_live_image_handoff"
    _write_json(handoff_path, mutated_handoff)

    selected_candidate_binding = approval_mod.validate_selected_candidate_binding(mutated_handoff)
    with pytest.raises(reconciliation_contract.ReconciliationContractError) as excinfo:
        reconciliation_contract.validate_handoff_reconciliation_provenance(mutated_handoff, selected_candidate_binding)
    assert excinfo.value.code == "unexpected_reconciliation_decision"


def test_cli_aborts_cleanly_on_expired_reconciliation_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    reconciliation, paths = _reconciliation_payload(tmp_path)
    reconciliation_repo_path = paths["reconciliation_path"].relative_to(tmp_path).as_posix()
    decision_path = _write_decision_with_timestamps(
        reconciliation=reconciliation,
        reconciliation_repo_path=reconciliation_repo_path,
        generated_at_utc="2020-01-01T00:00:00+00:00",
        expires_at_utc="2020-01-01T00:30:00+00:00",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "handoff",
            "--date",
            DATE,
            "--reconciliation-artifact",
            reconciliation_repo_path,
            "--reconciliation-decision-artifact",
            decision_path.relative_to(tmp_path).as_posix(),
        ],
    )

    assert handoff_builder.main() == 1
    captured = capsys.readouterr()
    assert "[ABORT] reconciliation_decision_expired:" in captured.out
    assert "Traceback" not in captured.err
    assert handoff_builder.handoff_json_path(DATE).exists() is False
    assert handoff_builder.handoff_markdown_path(DATE).exists() is False
