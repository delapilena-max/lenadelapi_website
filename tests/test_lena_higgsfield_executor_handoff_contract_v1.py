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
import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff_builder
import tools.strategy.lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff_mod


DATE = "2026-07-13"
RECIPE_ID = "hcr_006"
SLOT_ID = f"higgsfield-20260713-{RECIPE_ID}-photo"
HANDOFF_NAME = f"lena_next_live_image_handoff_{DATE}.json"
EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
HANDOFF_COMMAND = f"python {EXECUTOR_PATH} --handoff-artifact pipeline/strategy/lena/next_actions/{DATE}/{HANDOFF_NAME}"
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
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {slot_id}",
        },
        "decision_fingerprint_sha256": "5" * 64,
        "generated_at_utc": generated_at_utc,
        "provider_authorized": False,
        "side_effects_performed": [],
    }


def _source_from_prompt(prompt_text: str = PROMPT_TEXT) -> dict:
    return {
        "resolver": "content_packet_dryrun",
        "slot_prefix": RECIPE_ID,
        "pack_count": 1,
        "pack_variety_warnings": [],
        "image": {
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


def _build_packet_fixture(tmp_root: Path, monkeypatch: pytest.MonkeyPatch, *, prompt_text: str = PROMPT_TEXT) -> tuple[Path, dict]:
    _patch_roots(tmp_root, monkeypatch)
    next_actions = tmp_root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    packets = tmp_root / "pipeline" / "strategy" / "lena" / "content_packets" / DATE
    candidates = tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    content_packet_path = packets / f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
    selected_candidate_path = candidates / "lena_pre_generation_candidate_selected.json"
    packet_report = _content_packet_payload(prompt_text)

    _write_json(learning_path, _learning_payload())
    _write_json(recommendation_path, _recommendation_payload(learning_path))
    _write_json(queue_path, _queue_payload())
    _write_json(content_packet_path, packet_report)
    _write_json(selected_candidate_path, _selected_candidate_payload())

    monkeypatch.setattr(
        executor,
        "_rebuild_packet_prompt_source",
        lambda _path: (copy.deepcopy(packet_report), _source_from_prompt(prompt_text)),
    )

    packet = handoff_builder.build_handoff(DATE)
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
        "compact_provider_prompt_budget": 2499,
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
        "source_recommendation_artifact_path": recommendation_repo_path.as_posix(),
        "source_recommendation_artifact_sha256": hashlib.sha256(recommendation_path.read_bytes()).hexdigest(),
        "source_learning_artifact_path": learning_repo_path.as_posix(),
        "source_learning_artifact_sha256": hashlib.sha256(learning_path.read_bytes()).hexdigest(),
        "source_queue_dry_run_artifact_path": queue_repo_path.as_posix(),
        "source_queue_dry_run_artifact_sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        "source_selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "source_selected_candidate_artifact_sha256": selected_candidate_sha,
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
        lambda _path: (copy.deepcopy(packet_report), copy.deepcopy(source)),
    )

    with pytest.raises(executor.HandoffArtifactError) as excinfo:
        executor._validate_handoff_packet(handoff_path)

    assert excinfo.value.code == "selected_candidate_recommendation_mismatch"
    assert not approval_mod.claim_output_path(date, slot_id).exists()
    assert not approval_mod.receipt_output_path(date, slot_id).exists()
    assert not executor.manifest_path(date, slot_id).exists()


def test_prompt_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path, packet_report = _build_packet_fixture(tmp_path, monkeypatch, prompt_text=PROMPT_TEXT)
    monkeypatch.setattr(
        executor,
        "_rebuild_packet_prompt_source",
        lambda _path: (copy.deepcopy(packet_report), _source_from_prompt(PROMPT_TEXT + " drift")),
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
    assert "--approval-artifact" in stdout or "review-only" in stdout


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


def _build_retry_fixture(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    _patch_roots(tmp_root, monkeypatch)
    retry_date = "2026-07-14"
    original_slot = "higgsfield-20260714-hcr_011-photo"
    custom_reference_id = "90a293d7-f3af-4377-8751-3304a27b6f31"
    original_prompt = (
        "[Subject]: Lena (Magdalena Delapi). Identity is fixed: preserve her approved adult slim-thick hourglass body and face. "
        "Do not reinterpret her as a different person. Do not slim her into petite, narrow-hipped proportions. Keep full natural "
        "lifted bust, defined waist, and wide hips. Hair stays reference-true warm medium-brown with visible honey/caramel highlights "
        "and lighter face-framing pieces. Wardrobe and accessories: Cherry red fitted square-neck mini dress visible from neckline "
        "through upper torso only. Gold hoop earrings. [Action]: Waist-up or chest-up only. Lena stands near the mirror at a 20-30 "
        "degree angle toward the mirror or window. Mirror-selfie phone visibility is acceptable if the phone sits low enough to keep "
        "her face readable. [Environment]: Home getting-ready corner or bedroom vanity area. Mirror edge visible, not full mirror "
        "dominance. Dresser or small vanity surface, a few products, clothes draped on a chair, shoes near the mirror, warm apartment "
        "light, and ordinary home clutter kept tasteful. Lived-in and elevated, never hotel-like. [Cinematography]: 85mm portrait "
        "compression or 50mm close lifestyle portrait, waist-up framing, real phone-camera skin detail, shallow depth of field, "
        "blue-hour ambient mixed with warm lamp fill, candid apartment realism, non-studio. [Lighting/Style]: Face-first available "
        "light only. Cool blue-hour window light shapes one side of the face while an ordinary warm bedside lamp lifts the shadow side "
        "just enough to keep pores, under-eye texture, and lip texture alive. No beauty-dish polish, no ring light, no glam campaign "
        "finish. [Technical]: Photorealistic high-resolution image with visible pores, fine facial texture, natural under-eye retention, "
        "imperfect lip texture, tiny tone variation, stray hair strands, realistic catchlights, and scene-true shadow falloff. Face "
        "detail comes from the Lena character element; keep the facial surface faithful to the approved references. Hands remain "
        "anatomically correct with five fingers, believable knuckles, clean thumb placement, and relaxed wrists."
    )
    original_prompt_sha = hashlib.sha256(original_prompt.encode("utf-8")).hexdigest()
    handoff_repo_path = Path("pipeline/strategy/lena/next_actions") / retry_date / f"lena_next_live_image_handoff_{retry_date}.json"
    packet_repo_path = Path("pipeline/strategy/lena/content_packets") / retry_date / f"lena_content_packet_dryrun_{retry_date}_hcr_011.json"
    handoff_path = tmp_root / handoff_repo_path
    packet_path = tmp_root / packet_repo_path
    selected_candidate_repo_path = Path("pipeline/strategy/lena/pre_generation_candidates") / retry_date / "lena_pre_generation_candidate_selected.json"
    _write_json(
        packet_path,
        {
            "report_type": "lena_content_packet_dryrun",
            "generated_date": retry_date,
            "recipe_id": "hcr_011",
            "compact_provider_prompt_preview": original_prompt,
            "compact_provider_prompt_sha256": original_prompt_sha,
            "compact_provider_prompt_budget": 2499,
            "provider_prompt_contract": {"provider_route": "higgsfield_forward_no_live", "live_authority": False},
        },
    )
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
    _write_json(
        handoff_path,
        {
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
            },
            "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
            "selected_prompt_input_artifact_sha256": packet_sha,
            "selected_prompt_input": {
                "prompt_sha256": original_prompt_sha,
                "prompt_text": original_prompt,
                "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
                "selected_candidate_artifact_sha256": selected_candidate_sha,
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
                "soul_metadata": {
                    "name": "Lena",
                    "type": "Soul 2.0",
                    "custom_reference_id": custom_reference_id,
                    "identity_is_prompt_instruction": False,
                },
                "selected_prompt_sha256": original_prompt_sha,
                "selected_prompt_text": original_prompt,
            },
        },
    )
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
                "pose_body_language_id": None,
                "pose_body_language_label": "getting ready at the mirror",
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
    monkeypatch.setattr(
        executor,
        "run_live",
        lambda *args, **kwargs: {
            "job_id": "job-123",
            "status": "completed",
            "result_urls": ["https://example.com/final.png"],
            "saved_image_path": str(tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"),
            "image_format_detected": ".png",
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        },
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
