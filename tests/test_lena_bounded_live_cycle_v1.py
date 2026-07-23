from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

import pipeline.identity.lena_higgsfield_identity as identity
import pipeline.higgsfield_lena_api_executor as higgsfield_executor
from tests.fixtures import lena_pose_provenance as pose_fixture
import tools.lena_bounded_live_cycle_v1 as cycle
import tools.lena_autopublish_approved_queue_v2_8 as autonomous_publisher
import tools.lena_higgsfield_generation_approval_v1 as approval
import tools.lena_higgsfield_standing_autonomy_generation_approval_v1 as standing_generation_approval
import tools.lena_photo_qa_disposition_v1 as photo_qa
import tools.lena_standing_autonomy_policy_v1 as standing_autonomy


DATE = "2026-07-18"
SLOT_ID = "lenagate202607176924dc10-pack000-00-photo"
RECIPE_ID = "hcr_012"
HOOK_ID = "cbn_001"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
PROMPT_SHA = "186c0feb77d819cf1d001507dd56448e22057eeab5f2af33c83e0b464abdf640"
AUTHORITY_COMMIT = "6924dc10d7916b3bc91a87953ca3e319171e42fc"
CAPTION = "single-command bounded live cycle"
PLATFORM = "Instagram Feed"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha_without_keys(payload: dict, excluded_keys: set[str]) -> str:
    value = json.loads(json.dumps(payload, indent=2, ensure_ascii=True))
    for key in excluded_keys:
        value.pop(key, None)
    return hashlib.sha256((json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _write_auth_json(path: Path, payload: dict) -> Path:
    payload = json.loads(json.dumps(payload, indent=2, ensure_ascii=True))
    payload["authorization_artifact_sha256"] = _json_sha_without_keys(payload, {"authorization_artifact_sha256"})
    return _write_json(path, payload)


def _write_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1152, 2048), "white").save(path)
    return path


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        fixed = datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc)
        return fixed if tz is None else fixed.astimezone(tz)


def _patch_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cycle, "ROOT", tmp_path)
    monkeypatch.setattr(cycle, "AUTH_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles")
    monkeypatch.setattr(cycle, "REPORT_ROOT", tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles")
    monkeypatch.setattr(cycle, "POLICY_ROOT", tmp_path / "pipeline" / "config")
    monkeypatch.setattr(cycle, "DEFAULT_POLICY_PATH", tmp_path / "pipeline" / "config" / "lena_standing_autonomy_policy_v1.json")
    monkeypatch.setattr(identity, "HIGGSFIELD_DEBUG_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    monkeypatch.setattr(photo_qa, "OUTPUT_ROOT", tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa")
    monkeypatch.setattr(approval, "ROOT", tmp_path)
    monkeypatch.setattr(approval, "DEFAULT_APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")
    monkeypatch.setattr(standing_generation_approval, "ROOT", tmp_path)
    monkeypatch.setattr(standing_generation_approval, "DEFAULT_APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")
    monkeypatch.setattr(standing_autonomy, "ROOT", tmp_path)
    monkeypatch.setattr(standing_autonomy, "POLICY_ROOT", tmp_path / "pipeline" / "config")
    monkeypatch.setattr(standing_autonomy, "AUTH_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles")
    monkeypatch.setattr(standing_autonomy, "REPORT_ROOT", tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles")


def _patch_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cycle, "datetime", _FixedDateTime)
    monkeypatch.setattr(cycle, "_now_utc", lambda: datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc))
    monkeypatch.setattr(identity, "_utc_now", lambda: datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc))
    monkeypatch.setattr(standing_autonomy, "_now_utc", lambda: datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc))


def _candidate_path(tmp_path: Path, date_str: str = DATE) -> Path:
    return tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / date_str / "lena_pre_generation_candidate_selected.json"


def _handoff_path(tmp_path: Path, date_str: str = DATE) -> Path:
    return tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_next_live_image_handoff_{date_str}.json"


def _policy_path(tmp_path: Path) -> Path:
    return tmp_path / "pipeline" / "config" / "lena_standing_autonomy_policy_v1.json"


def _auth_path(tmp_path: Path, date_str: str = DATE, slot_id: str = SLOT_ID) -> Path:
    return tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / date_str / f"lena_bounded_live_cycle_authorization_{date_str}_{slot_id}.json"


def _policy_payload(*, autonomy_enabled: bool = True, live_generation_enabled: bool = True, live_publishing_enabled: bool = True, kill_switch_enabled: bool = True, expires_at_utc: str | None = None, daily_spend_ceiling: float = 25.0) -> dict:
    return {
        "report_type": standing_autonomy.POLICY_REPORT_TYPE,
        "schema_version": standing_autonomy.POLICY_SCHEMA_VERSION,
        "policy_id": "lena_standing_autonomy_policy_v1",
        "policy_version": "v1",
        "autonomy_enabled": autonomy_enabled,
        "live_generation_enabled": live_generation_enabled,
        "live_publishing_enabled": live_publishing_enabled,
        "kill_switch_enabled": kill_switch_enabled,
        "allowed_provider": "Higgsfield",
        "allowed_model": "text2image_soul_v2",
        "allowed_soul": "Lena",
        "allowed_platforms": ["Instagram Feed", "Facebook Page"],
        "provider_call_cap_per_cycle": 1,
        "publish_action_cap_per_cycle": 1,
        "retry_cap_per_cycle": 0,
        "maximum_cycles_per_day": 3,
        "maximum_provider_calls_per_day": 3,
        "maximum_publish_actions_per_day": 3,
        "daily_spend_ceiling": daily_spend_ceiling,
        "spend_unit": "provider_credits",
        "allowed_media_types": ["photo"],
        "duplicate_content_rejection_enabled": True,
        "qa_required": True,
        "identity_verification_required": True,
        "analytics_triggered_regeneration_disabled": True,
        "effective_at_utc": "2026-07-18T00:00:00Z",
        "expires_at_utc": expires_at_utc,
    }


def _build_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    date_str: str = DATE,
    slot_id: str = SLOT_ID,
    platform: str = PLATFORM,
    publish_authorized: bool = True,
    daily_spend_ceiling: float = 25.0,
    consumed: bool = False,
    policy_overrides: dict | None = None,
    nested_candidate: bool = False,
    controlled: bool = False,
) -> dict[str, Path | dict]:
    candidate_path = _candidate_path(tmp_path, date_str)
    handoff_path = _handoff_path(tmp_path, date_str)
    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.png"
    policy_path = _policy_path(tmp_path)

    candidate = {
        "candidate_id": f"{slot_id}::{RECIPE_ID}::{HOOK_ID}",
        "slot_id": slot_id,
        "lane": "bounded-live",
        "recipe_id": RECIPE_ID,
        "hook_id": HOOK_ID,
        "prompt_sha256": PROMPT_SHA,
        "wardrobe_outfit_id": "wc_p050" if controlled else None,
        "authority_commit": AUTHORITY_COMMIT,
        "decision_fingerprint_sha256": "d" * 64 if controlled else None,
        "final_action": "prepare_higgsfield_still_dry_run_for_review",
        "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date_str} --slot-id {slot_id}",
    }
    if controlled:
        candidate.update(
            {
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
            }
        )
    candidate_file = {"candidate": dict(candidate)} if controlled or nested_candidate else dict(candidate)
    candidate_file["schema_version"] = "lena_pre_generation_candidate_gate_v1"
    candidate_file["candidate_status"] = "selected"
    if controlled:
        candidate_file["authority_commit"] = AUTHORITY_COMMIT
        candidate_file["decision_fingerprint_sha256"] = "d" * 64
    _write_json(candidate_path, candidate_file)
    candidate_repo_path = candidate_path.relative_to(tmp_path).as_posix()
    candidate_sha = _sha(candidate_path)
    pose_binding = pose_fixture.static_pose_provenance(
        candidate_path=candidate_repo_path,
        candidate_sha256=candidate_sha,
        authority_commit=AUTHORITY_COMMIT,
    )
    expression_binding = pose_fixture.static_expression_provenance(
        candidate_path=candidate_repo_path,
        candidate_sha256=candidate_sha,
        authority_commit=AUTHORITY_COMMIT,
    )
    # A separate copy for embedding as the handoff's selected_candidate: real
    # production handoffs embed the candidate's own artifact_path/sha256
    # (computed after the candidate file is written), never inside the
    # candidate file itself.
    candidate_for_handoff = dict(
        candidate,
        schema_version="lena_pre_generation_candidate_gate_v1",
        candidate_status="selected",
        artifact_path=candidate_repo_path,
        artifact_sha256=candidate_sha,
    )
    policy = _policy_payload(daily_spend_ceiling=daily_spend_ceiling)
    if controlled:
        model_authority = tmp_path / "pipeline" / "identity" / "lena_visual_model_authority_v1.json"
        reference_authority = tmp_path / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json"
        _write_json(model_authority, {"authority_id": "lena_visual_model_authority_v1"})
        _write_json(reference_authority, {"reference_set_sha256": "a" * 64})
        policy.update(
            {
                "provider_call_cap_per_cycle": 2,
                "retry_cap_per_cycle": 1,
                "maximum_provider_calls_per_day": 2,
                "emergency_stop": False,
                "controlled_photo_autonomy": {
                    "enabled": True,
                    "recipe_id": "hcr_012",
                    "wardrobe_outfit_id": "wc_p050",
                    "visual_provider": "anthropic",
                    "visual_model": "claude-sonnet-5",
                    "visual_model_authority_path": "pipeline/identity/lena_visual_model_authority_v1.json",
                    "identity_reference_authority_path": "pipeline/identity/lena_visual_reference_authority_v1.json",
                    "retry_reason_codes": ["hair_crown_forelock_artifact"],
                    "provider_call_cap_per_cycle": 2,
                    "retry_cap_per_cycle": 1,
                    "queue_item_cap_per_cycle": 1,
                    "publish_action_cap_per_cycle": 1,
                    "privacy_clean_derivative_required": True,
                    "human_review_is_exception_only": True,
                    "schedule_slot": "morning",
                },
            }
        )
    if policy_overrides:
        policy.update(policy_overrides)
    _write_json(policy_path, policy)
    (tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles").mkdir(parents=True, exist_ok=True)

    handoff = {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "execution_owner": "claude",
        "provider": "higgsfield",
        "executor_type": "higgsfield_cli",
        "date": date_str,
        "selected_slot_id": slot_id,
        "selected_recipe_id": RECIPE_ID,
        "selected_candidate_path": candidate_repo_path,
        "selected_candidate_sha256": candidate_sha,
        "selected_candidate": candidate_for_handoff,
        "source_selected_candidate_artifact_path": candidate_repo_path,
        "source_selected_candidate_artifact_sha256": candidate_sha,
        "prompt_sha256": PROMPT_SHA,
        "custom_reference_id": CUSTOM_REFERENCE_ID,
        "platform": platform,
        "live_execution_authorized": False,
        "generation_approval_required": True,
        "manual_operator_approval_required": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "publish_authorized": False,
        "manual_publish_review_required": True,
        "packet_state": "packet_valid_for_claude_review",
        "dry_run_executor_contract_state": "ready",
        "live_execution_state": "blocked",
        "structured_executor_inputs": {
            "date": date_str,
            "selected_slot_id": slot_id,
            "selected_recipe_id": RECIPE_ID,
            "selected_candidate_path": candidate_repo_path,
            "selected_candidate_sha256": candidate_sha,
            "selected_candidate_artifact_path": candidate_repo_path,
            "selected_candidate_artifact_sha256": candidate_sha,
            "prompt_sha256": PROMPT_SHA,
            "selected_prompt_sha256": PROMPT_SHA,
            "expected_output_directory": (Path("pipeline") / "higgsfield_library" / "lena" / date_str).as_posix(),
            "expected_output_stem": f"{slot_id}_seed",
            "allowed_output_extensions": list(approval.ALLOWED_OUTPUT_EXTENSIONS),
            "model": "text2image_soul_v2",
            "aspect_ratio": "9:16",
            "custom_reference_id": CUSTOM_REFERENCE_ID,
            "provider": "higgsfield",
            "executor_type": "higgsfield_cli",
            "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
            "negative_prompt_enabled": False,
            "live_execution_authorized": False,
        },
    }
    _write_json(handoff_path, handoff)

    packet_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_selected_prompt_input_{date_str}.json"
    handoff_repo_path = Path("pipeline/strategy/lena/next_actions") / date_str / f"lena_next_live_image_handoff_{date_str}.json"
    packet_repo_path = Path("pipeline/strategy/lena/next_actions") / date_str / f"lena_selected_prompt_input_{date_str}.json"
    packet = {
        "report_type": "lena_selected_prompt_input",
        "schema_version": "v1",
        "packet_id": f"{slot_id}::packet",
        "strong_hook_id": HOOK_ID,
        "hook_text": "soul-forward vanity framing",
        "caption_draft": CAPTION,
        "compact_provider_prompt_sha256": PROMPT_SHA,
        "compact_provider_prompt_preview": "provider prompt preview",
        "recipe_id": RECIPE_ID,
        "lane": "bounded-live",
        "selected_candidate_artifact_path": candidate_repo_path,
        "selected_candidate_artifact_sha256": candidate_sha,
        "image": {
            "slot_id": slot_id,
            "lane": "bounded-live",
            "soul_name": "Lena",
            "soul_version": "Soul 2.0",
            "soul_selection_mode": "provider_config_not_prompt_text",
            "negative_prompt_enabled": False,
            "image_prompt": "provider prompt preview",
        },
    }
    _write_json(packet_path, packet)
    packet_bound_sha = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    recommendation_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_next_generation_step_{date_str}.json"
    learning_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_post_outcome_learning_state_{date_str}.json"
    queue_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_autonomous_generation_queue_dryrun_{date_str}.json"

    candidate_selection_binding = {
        "selected_candidate_artifact_path": candidate_repo_path,
        "selected_candidate_artifact_sha256": candidate_sha,
        "candidate_id": candidate["candidate_id"],
        "slot_id": slot_id,
        "recipe_id": RECIPE_ID,
        "candidate_prompt_sha256": PROMPT_SHA,
        "candidate_lane": candidate["lane"],
        "source_prompt_family": "prompt_library_candidate",
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_body_language_label": pose_binding["pose_body_language_label"],
        "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_gaze_label": expression_binding["expression_gaze_label"],
        "expression_provenance_fingerprint_sha256": expression_binding["expression_provenance_fingerprint_sha256"],
    }
    provider_execution_binding = {
        "content_packet_artifact_path": packet_repo_path.as_posix(),
        "content_packet_artifact_sha256": _sha(packet_path),
        "recipe_id": RECIPE_ID,
        "slot_id": slot_id,
        "provider_prompt_sha256": PROMPT_SHA,
        "provider_lane": packet["lane"],
        "source_prompt_family": "compact_provider_prompt",
        "provider": "higgsfield",
        "model": "text2image_soul_v2",
        "pose_bound_content_packet_sha256": packet_bound_sha,
        "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        "expression_bound_content_packet_sha256": packet_bound_sha,
        "expression_provenance_fingerprint_sha256": expression_binding["expression_provenance_fingerprint_sha256"],
    }
    binding_linkage = {
        "recommendation_artifact_path": recommendation_path.relative_to(tmp_path).as_posix(),
        "recommendation_artifact_sha256": "",
        "queue_artifact_path": queue_path.relative_to(tmp_path).as_posix(),
        "queue_artifact_sha256": "",
        "selected_candidate_artifact_path": candidate_repo_path,
        "selected_candidate_artifact_sha256": candidate_sha,
        "content_packet_artifact_path": packet_repo_path.as_posix(),
        "content_packet_artifact_sha256": _sha(packet_path),
        "recipe_id": RECIPE_ID,
        "slot_id": slot_id,
        "candidate_id": candidate["candidate_id"],
        "outfit_id": "wc_p059",
        "environment_id": "env_p001",
        "candidate_lane": candidate["lane"],
        "provider_lane": packet["lane"],
        "candidate_prompt_family": "prompt_library_candidate",
        "provider_prompt_family": "compact_provider_prompt",
        "prompt_family_relationship": "candidate prompt family and provider prompt family are intentionally distinct for the same recipe/slot chain",
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        "pose_bound_content_packet_sha256": packet_bound_sha,
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_provenance_fingerprint_sha256": expression_binding["expression_provenance_fingerprint_sha256"],
        "expression_bound_content_packet_sha256": packet_bound_sha,
    }
    selected_prompt_input = {
        "artifact_path": packet_repo_path.as_posix(),
        "artifact_sha256": _sha(packet_path),
        "selected_candidate_artifact_path": candidate_repo_path,
        "selected_candidate_artifact_sha256": candidate_sha,
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_sha256": packet_bound_sha,
        "expression_provenance": expression_binding,
        "expression_bound_content_packet_sha256": packet_bound_sha,
        "artifact_report_type": packet["report_type"],
        "packet_id": packet["packet_id"],
        "prompt_sha256": PROMPT_SHA,
        "prompt_text": packet["compact_provider_prompt_preview"],
        "prompt_text_status": "available",
        "prompt_text_available": True,
        "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --handoff-artifact {handoff_repo_path.as_posix()}",
        "lane": packet["lane"],
        "recipe_id": RECIPE_ID,
        "hook_id": HOOK_ID,
        "hook_text": packet["hook_text"],
        "caption_seed": CAPTION,
        "activity": "leaning against the elevator wall before heading up",
        "source_prompt_family": "compact_provider_prompt",
        "concept_summary": "parking_garage_flash | leaning against the elevator wall before heading up | warm lobby spill and realistic night shadow falloff",
    }
    handoff.update(
        {
            "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
            "selected_prompt_input_artifact_sha256": _sha(packet_path),
            "selected_prompt_input": selected_prompt_input,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": packet_bound_sha,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": packet_bound_sha,
            "candidate_selection_binding": candidate_selection_binding,
            "provider_execution_binding": provider_execution_binding,
            "binding_linkage": binding_linkage,
        }
    )
    handoff["structured_executor_inputs"].update(
        {
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": packet_bound_sha,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": packet_bound_sha,
        }
    )
    _write_json(handoff_path, handoff)
    recommendation = {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": date_str,
        "learning_artifact_path": str(learning_path.relative_to(tmp_path)).replace("\\", "/"),
        "learning_status": "current",
        "learning_published_post_count": 3,
        "learning_pending_metrics_count": 0,
        "learning_stale_pending_metrics_count": 0,
        "learning_resolution_state_summary": {
            "learning_status": "current",
            "current_count": 2,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0,
        },
        "recommendation": {
            "recommended_recipe_id": RECIPE_ID,
        },
    }
    learning = {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": date_str,
        "published_post_count": 3,
        "pending_metrics_posts": [],
        "stale_pending_metrics_posts": [],
        "winner_posts": [{"recipe_id": RECIPE_ID}],
        "queue_boosts": {"preferred_recipe_ids": [RECIPE_ID]},
        "metrics_resolution_summary": {
            "learning_status": "current",
            "current_count": 2,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0,
        },
    }
    queue = {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "date": date_str,
        "queue_slots": [
            {
                "slot_id": slot_id,
                "recipe_id": RECIPE_ID,
            }
        ],
    }
    _write_json(recommendation_path, recommendation)
    _write_json(learning_path, learning)
    _write_json(queue_path, queue)

    binding_linkage["recommendation_artifact_sha256"] = _sha(recommendation_path)
    binding_linkage["queue_artifact_sha256"] = _sha(queue_path)
    handoff["binding_linkage"] = binding_linkage
    _write_json(handoff_path, handoff)

    def fake_validate_handoff_packet(handoff_file: Path):
        assert handoff_file.resolve() == handoff_path.resolve()
        report = {
            "report_type": "lena_next_live_image_handoff",
            "schema_version": "v1",
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
            "date": date_str,
            "selected_slot_id": slot_id,
            "selected_recipe_id": RECIPE_ID,
            "selected_candidate_path": candidate_repo_path,
            "selected_candidate_sha256": candidate_sha,
            "selected_candidate": candidate_for_handoff,
            "source_selected_candidate_artifact_path": candidate_repo_path,
            "source_selected_candidate_artifact_sha256": candidate_sha,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": packet_bound_sha,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": packet_bound_sha,
            "candidate_selection_binding": candidate_selection_binding,
            "provider_execution_binding": provider_execution_binding,
            "binding_linkage": binding_linkage,
            "platform": platform,
            "expected_output_directory": (Path("pipeline") / "higgsfield_library" / "lena" / date_str).as_posix(),
            "expected_output_stem": f"{slot_id}_seed",
            "allowed_output_extensions": list(approval.ALLOWED_OUTPUT_EXTENSIONS),
            "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
            "selected_prompt_input_artifact_sha256": _sha(packet_path),
            "selected_prompt_input": {
                "packet_id": packet["packet_id"],
                "hook_id": packet["strong_hook_id"],
                "hook_text": packet["hook_text"],
                "caption_seed": packet["caption_draft"],
                "prompt_sha256": PROMPT_SHA,
                "artifact_path": packet_repo_path.as_posix(),
                "selected_candidate_artifact_path": candidate_repo_path,
                "selected_candidate_artifact_sha256": candidate_sha,
                "pose_provenance": pose_binding,
                "pose_bound_content_packet_sha256": packet_bound_sha,
                "expression_provenance": expression_binding,
                "expression_bound_content_packet_sha256": packet_bound_sha,
                "lane": packet["lane"],
                "recipe_id": RECIPE_ID,
                "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --handoff-artifact {handoff_repo_path.as_posix()}",
            },
            "source_recommendation_artifact_path": (Path("pipeline/strategy/lena/next_actions") / date_str / f"lena_next_generation_step_{date_str}.json").as_posix(),
            "source_learning_artifact_path": (Path("pipeline/strategy/lena/next_actions") / date_str / f"lena_post_outcome_learning_state_{date_str}.json").as_posix(),
            "source_queue_dry_run_artifact_path": (Path("pipeline/strategy/lena/next_actions") / date_str / f"lena_autonomous_generation_queue_dryrun_{date_str}.json").as_posix(),
            "source_recommendation_artifact_sha256": _sha(recommendation_path),
            "source_learning_artifact_sha256": _sha(learning_path),
            "source_queue_dry_run_artifact_sha256": _sha(queue_path),
            "structured_executor_inputs": {
                "provider": "higgsfield",
                "executor_type": "higgsfield_cli",
                "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
                "model": "text2image_soul_v2",
                "aspect_ratio": "9:16",
                "negative_prompt_enabled": False,
                "live_execution_authorized": False,
                "date": date_str,
                "slot_id": slot_id,
                "handoff_artifact_path": handoff_repo_path.as_posix(),
                "selected_candidate_artifact_path": candidate_repo_path,
                "selected_candidate_artifact_sha256": candidate_sha,
                "pose_provenance": pose_binding,
                "pose_bound_content_packet_sha256": packet_bound_sha,
                "expression_provenance": expression_binding,
                "expression_bound_content_packet_sha256": packet_bound_sha,
                "soul_metadata": {
                    "name": "Lena",
                    "type": "Soul 2.0",
                    "custom_reference_id": CUSTOM_REFERENCE_ID,
                    "identity_is_prompt_instruction": False,
                },
                "selected_prompt_sha256": PROMPT_SHA,
                "selected_prompt_text": "provider prompt preview",
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
                "expected_output_directory": (Path("pipeline") / "higgsfield_library" / "lena" / date_str).as_posix(),
                "expected_output_stem": f"{slot_id}_seed",
                "allowed_output_extensions": list(approval.ALLOWED_OUTPUT_EXTENSIONS),
            },
            "custom_reference_id": CUSTOM_REFERENCE_ID,
            "prompt_sha256": PROMPT_SHA,
            "handoff_artifact_path": handoff_repo_path.as_posix(),
            "handoff_sha256": _sha(handoff_path),
        }
        source = {
            "resolver": "content_packet_dryrun",
            "slot_prefix": RECIPE_ID,
            "pack_count": 1,
            "pack_variety_warnings": [],
            "image": {
                "slot_id": slot_id,
                "lane": "bounded-live",
                "soul_name": "Lena",
                "soul_version": "Soul 2.0",
                "soul_selection_mode": "provider_config_not_prompt_text",
                "negative_prompt_enabled": False,
                "image_prompt": "provider prompt preview",
            },
        }
        packet_validation = {"ok": True}
        validation = {"ok": True}
        return report, source, packet_validation, validation

    monkeypatch.setattr(higgsfield_executor, "_validate_handoff_packet", fake_validate_handoff_packet)

    auth_bundle = standing_autonomy.issue_cycle_authorization(policy_path, handoff_path, auth_root=tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles", report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles")
    auth_path = Path(auth_bundle["path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth.update(
        {
            "publish_authorized": publish_authorized,
            "daily_spend_ceiling": daily_spend_ceiling,
            "consumed": consumed,
            "consumed_at_utc": None,
            "authorization_state_before": {"single_use": True, "consumed": consumed, "consumed_at_utc": None},
            "authorization_state_after": {"single_use": True, "consumed": consumed, "consumed_at_utc": None},
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "retries_performed": 0,
            "expected_output_directory": str(image_path.parent),
            "expected_output_stem": image_path.stem,
            "allowed_output_extensions": list(approval.ALLOWED_OUTPUT_EXTENSIONS),
            "platform": platform,
            "caption": CAPTION,
            "generation_handoff_artifact_path": str(handoff_path),
            "generation_handoff_artifact_sha256": _sha(handoff_path),
            "candidate_artifact_path": str(candidate_path),
            "candidate_artifact_sha256": _sha(candidate_path),
        }
    )
    auth["authorization_artifact_sha256"] = _json_sha_without_keys(auth, {"authorization_artifact_sha256"})
    _write_json(auth_path, auth)
    return {
        "candidate_path": candidate_path,
        "candidate": candidate,
        "policy_path": policy_path,
        "policy": policy,
        "auth_path": auth_path,
        "auth": auth,
        "handoff_path": handoff_path,
        "handoff": handoff,
        "image_path": image_path,
    }


def _selected_candidate_bound_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path | dict]:
    _patch_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path, monkeypatch, controlled=True)
    candidate_path = Path(bundle["candidate_path"])
    handoff_path = Path(bundle["handoff_path"])
    candidate_body = dict(bundle["candidate"])  # type: ignore[arg-type]
    candidate_doc = {
        "schema_version": approval.SELECTED_CANDIDATE_SCHEMA_VERSION,
        "candidate_status": "selected",
        "authority_commit": AUTHORITY_COMMIT,
        "decision_fingerprint_sha256": "d" * 64,
        "candidate": candidate_body,
    }
    _write_json(candidate_path, candidate_doc)
    candidate_sha = _sha(candidate_path)
    candidate_repo_path = candidate_path.relative_to(tmp_path).as_posix()

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["selected_candidate_path"] = candidate_repo_path
    handoff["selected_candidate_sha256"] = candidate_sha
    handoff["source_selected_candidate_artifact_path"] = candidate_repo_path
    handoff["source_selected_candidate_artifact_sha256"] = candidate_sha
    handoff["selected_candidate"].update(
        {
            "schema_version": approval.SELECTED_CANDIDATE_SCHEMA_VERSION,
            "candidate_status": "selected",
            "artifact_path": candidate_repo_path,
            "artifact_sha256": candidate_sha,
        }
    )
    handoff["selected_prompt_input"]["selected_candidate_artifact_path"] = candidate_repo_path
    handoff["selected_prompt_input"]["selected_candidate_artifact_sha256"] = candidate_sha
    handoff["structured_executor_inputs"]["selected_candidate_artifact_path"] = candidate_repo_path
    handoff["structured_executor_inputs"]["selected_candidate_artifact_sha256"] = candidate_sha
    handoff["candidate_selection_binding"]["selected_candidate_artifact_path"] = candidate_repo_path
    handoff["candidate_selection_binding"]["selected_candidate_artifact_sha256"] = candidate_sha
    handoff["binding_linkage"]["selected_candidate_artifact_path"] = candidate_repo_path
    handoff["binding_linkage"]["selected_candidate_artifact_sha256"] = candidate_sha
    _write_json(handoff_path, handoff)

    bundle["handoff"] = handoff
    return bundle


def _sync_selected_candidate_sha(handoff: dict, candidate_sha: str) -> None:
    handoff["selected_candidate_sha256"] = candidate_sha
    handoff["source_selected_candidate_artifact_sha256"] = candidate_sha
    handoff["selected_candidate"]["artifact_sha256"] = candidate_sha
    handoff["selected_prompt_input"]["selected_candidate_artifact_sha256"] = candidate_sha
    handoff["structured_executor_inputs"]["selected_candidate_artifact_sha256"] = candidate_sha
    handoff["candidate_selection_binding"]["selected_candidate_artifact_sha256"] = candidate_sha
    handoff["binding_linkage"]["selected_candidate_artifact_sha256"] = candidate_sha


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing_source_path", "handoff_selected_candidate_path_missing"),
        ("missing_source_sha", "handoff_selected_candidate_sha_missing"),
        ("embedded_path_mismatch", "handoff_selected_candidate_binding_mismatch"),
        ("embedded_sha_mismatch", "handoff_selected_candidate_sha_binding_mismatch"),
        ("embedded_candidate_disagreement", "handoff_selected_candidate_id_mismatch"),
        ("selected_prompt_path_mismatch", "handoff_selected_candidate_binding_mismatch"),
        ("structured_sha_mismatch", "handoff_structured_selected_candidate_sha_mismatch"),
        ("stale_candidate_artifact", "handoff_selected_candidate_sha_mismatch"),
        ("malformed_candidate_envelope", "handoff_selected_candidate_body_missing"),
        ("caller_candidate_path_mismatch", "candidate_path_binding_mismatch"),
    ],
)
def test_standing_autonomy_inspection_enforces_selected_candidate_binding_equivalence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_code: str,
) -> None:
    bundle = _selected_candidate_bound_bundle(tmp_path, monkeypatch)
    candidate_path = Path(bundle["candidate_path"])
    handoff_path = Path(bundle["handoff_path"])
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    candidate_arg = candidate_path

    if case == "missing_source_path":
        handoff.pop("source_selected_candidate_artifact_path")
    elif case == "missing_source_sha":
        handoff.pop("source_selected_candidate_artifact_sha256")
    elif case == "embedded_path_mismatch":
        handoff["selected_candidate"]["artifact_path"] = "pipeline/strategy/lena/pre_generation_candidates/2099-01-01/other.json"
    elif case == "embedded_sha_mismatch":
        handoff["selected_candidate"]["artifact_sha256"] = "f" * 64
    elif case == "embedded_candidate_disagreement":
        handoff["selected_candidate"]["candidate_id"] = "substituted-candidate"
    elif case == "selected_prompt_path_mismatch":
        handoff["selected_prompt_input"]["selected_candidate_artifact_path"] = "pipeline/strategy/lena/pre_generation_candidates/2099-01-01/other.json"
    elif case == "structured_sha_mismatch":
        handoff["structured_executor_inputs"]["selected_candidate_artifact_sha256"] = "e" * 64
    elif case == "stale_candidate_artifact":
        candidate_doc = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate_doc["candidate"]["candidate_id"] = "substituted-candidate"
        _write_json(candidate_path, candidate_doc)
    elif case == "malformed_candidate_envelope":
        candidate_doc = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate_doc.pop("candidate")
        _write_json(candidate_path, candidate_doc)
        _sync_selected_candidate_sha(handoff, _sha(candidate_path))
    elif case == "caller_candidate_path_mismatch":
        candidate_arg = candidate_path.with_name("other_selected_candidate.json")
        _write_json(candidate_arg, json.loads(candidate_path.read_text(encoding="utf-8")))
    else:
        raise AssertionError(f"unhandled case: {case}")

    _write_json(handoff_path, handoff)

    with pytest.raises(standing_generation_approval.HiggsfieldStandingAutonomyGenerationApprovalError) as exc_info:
        standing_generation_approval.inspect_generation_handoff_for_standing_autonomy(
            handoff_path,
            candidate_arg,
        )
    assert exc_info.value.code == expected_code


def _rewrite_candidate_shape_and_bindings(bundle: dict[str, Path | dict], *, nested_candidate: dict) -> None:
    candidate_path = Path(bundle["candidate_path"])
    handoff_path = Path(bundle["handoff_path"])
    auth_path = Path(bundle["auth_path"])
    _write_json(candidate_path, {"candidate": nested_candidate})
    candidate_sha = _sha(candidate_path)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["selected_candidate_sha256"] = candidate_sha
    if isinstance(handoff.get("selected_candidate"), dict):
        handoff["selected_candidate"]["artifact_sha256"] = candidate_sha
    handoff["handoff_sha256"] = _json_sha_without_keys(handoff, {"handoff_sha256"})
    _write_json(handoff_path, handoff)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["candidate_artifact_sha256"] = candidate_sha
    auth["generation_handoff_artifact_sha256"] = _sha(handoff_path)
    if isinstance(auth.get("audited_inputs"), dict):
        auth["audited_inputs"]["candidate_artifact_sha256"] = candidate_sha
        auth["audited_inputs"]["handoff_artifact_sha256"] = _sha(handoff_path)
    auth["authorization_artifact_sha256"] = _json_sha_without_keys(auth, {"authorization_artifact_sha256"})
    _write_auth_json(auth_path, auth)


def _build_simulation_artifacts(tmp_path: Path, bundle: dict[str, Path | dict], *, qa_disposition: str = "accept", qa_overall: str = "pass") -> dict[str, Path | dict]:
    date_str = DATE
    slot_id = SLOT_ID
    image_path = bundle["image_path"]
    assert isinstance(image_path, Path)
    _write_image(image_path)
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"
    manifest = {
        "report_type": "lena_higgsfield_result_manifest",
        "schema_version": "v1",
        "date": date_str,
        "slot_id": slot_id,
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "saved_image_path": str(image_path),
        "generation_claim_artifact_path": str(approval.claim_output_path(date_str, slot_id)),
        "generation_execution_receipt_path": str(approval.receipt_output_path(date_str, slot_id)),
    }
    _write_json(manifest_path, manifest)
    receipt_path = approval.receipt_output_path(date_str, slot_id)
    receipt = {
        "report_type": "lena_higgsfield_generation_execution_receipt",
        "schema_version": "v1",
        "slot_id": slot_id,
        "date": date_str,
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "output_path": str(image_path),
        "actual_manifest_path": str(manifest_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha(manifest_path),
        "generated_image_path": str(image_path),
        "generated_image_sha256": _sha(image_path),
        "subprocess_start_attempted": True,
        "provider_submission_may_have_occurred": True,
    }
    _write_json(receipt_path, receipt)
    claim_path = approval.claim_output_path(date_str, slot_id)
    claim = {
        "report_type": "lena_higgsfield_generation_claim",
        "schema_version": "v1",
        "slot_id": slot_id,
        "date": date_str,
        "claimed_at_utc": "2026-07-18T01:00:00+00:00",
        "consumed_attempt_number": 1,
        "state": "claimed_pending_receipt",
    }
    _write_json(claim_path, claim)
    qa_path = tmp_path / "pipeline" / "asset_review" / "lena" / "presence_output_qa" / date_str / slot_id / f"presence_qa_{slot_id}_00.json"
    qa_artifact = {
        "report_type": "lena_presence_output_qa",
        "schema_version": "v2",
        "slot_id": slot_id,
        "date": date_str,
        "disposition": qa_disposition,
        "overall": qa_overall,
        "provider_job_id": "job-123",
        "image_sha256": _sha(image_path),
        "generation_provenance": {"date": date_str},
        "production_scoring": {
            "styling_sexy_platform_safe": {"status": "pass", "notes": "adult non-explicit styling allowed"},
        },
    }
    _write_json(qa_path, qa_artifact)
    auth_path = Path(bundle["auth_path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth.update(
        {
            "provider_generation_receipt_path": str(receipt_path),
            "provider_generation_receipt_sha256": _sha(receipt_path),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha(manifest_path),
            "qa_artifact_path": str(qa_path),
            "qa_artifact_sha256": _sha(qa_path),
            "expected_output_directory": str(image_path.parent),
            "expected_output_stem": image_path.stem,
            "allowed_output_extensions": list(approval.ALLOWED_OUTPUT_EXTENSIONS),
            "authorization_state_before": {"single_use": True, "consumed": False, "consumed_at_utc": None},
            "authorization_state_after": {"single_use": True, "consumed": False, "consumed_at_utc": None},
        }
    )
    auth["authorization_artifact_sha256"] = _json_sha_without_keys(auth, {"authorization_artifact_sha256"})
    _write_json(auth_path, auth)
    return {
        **bundle,
        "provider_generation_receipt_path": receipt_path,
        "provider_generation_receipt_sha256": _sha(receipt_path),
        "manifest_path": manifest_path,
        "manifest_sha256": _sha(manifest_path),
        "qa_artifact_path": qa_path,
        "qa_artifact_sha256": _sha(qa_path),
        "expected_output_directory": image_path.parent,
        "expected_output_stem": image_path.stem,
    }


def _install_live_fakes(monkeypatch: pytest.MonkeyPatch, bundle: dict[str, Path | dict], tmp_path: Path, *, qa_disposition: str = "accept", qa_overall: str = "pass") -> dict[str, object]:
    expected_handoff_repo_path = Path(bundle["handoff_path"]).resolve().relative_to(tmp_path).as_posix()
    state: dict[str, object] = {
        "provider_calls": 0,
        "publish_calls": 0,
        "provider_error": None,
        "publish_error": None,
        "qa_disposition": qa_disposition,
        "qa_overall": qa_overall,
        "qa_calls": 0,
        "provider_manifest_overrides": {},
        "publish_overrides": {},
        "provider_contexts": [],
        "expected_handoff_repo_path": expected_handoff_repo_path,
        "reference_authority": tmp_path / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json",
    }
    _write_json(
        state["reference_authority"],  # type: ignore[arg-type]
        {
            "schema_version": "lena_identity_reference_authority_v1",
            "influencer_id": "lena",
            "authority_id": "lena_visual_reference_authority_v1",
            "authority_commit": AUTHORITY_COMMIT,
            "reference_set_sha256": "a" * 64,
            "references": [
                {
                    "path": str(tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"),
                    "sha256": "a" * 64,
                }
            ],
        },
    )
    reference_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"

    def fake_execute_approved_handoff_live_generation(context: dict[str, object], *, custom_reference_id=None, live_executor=None):
        approval_result = context["approval_result"]
        approval_record = approval_result["approval"]
        if approval_record.get("authorization_identity_mode") == "standing_autonomy_policy":
            assert Path(approval_result["approval_path"]).resolve() == standing_generation_approval.approval_output_path(DATE, SLOT_ID).resolve()
        else:
            assert approval_record["authorization_mode"] == "standing_autonomy_policy"
            assert Path(approval_result["approval_path"]).resolve() == Path(bundle["auth_path"]).resolve()
        handoff_facts = context["approval_result"]["handoff_facts"]
        assert Path(str(handoff_facts["handoff_path"])).resolve() == Path(bundle["handoff_path"]).resolve()
        assert handoff_facts["handoff_repo_path"] == state["expected_handoff_repo_path"]
        state["provider_contexts"].append(context)
        state["provider_calls"] = int(state["provider_calls"]) + 1
        image_path = Path(bundle["image_path"])
        _write_image(image_path)
        manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
        manifest = {
            "provider": "higgsfield",
            "job_type": "text2image_soul_v2",
            "date": DATE,
            "slot_id": SLOT_ID,
            "lane": "bounded-live",
            "prompt_sha256": PROMPT_SHA,
            "image_prompt": "live prompt",
            "provider_job_id": "job-123",
            "provider_status": "completed",
            "custom_reference_id": CUSTOM_REFERENCE_ID,
            "cli_soul_name": "Lena",
            "cli_soul_type": "soul_2",
            "saved_image_path": str(image_path),
            "saved_image_sha256": _sha(image_path),
            "width": 1152,
            "height": 2048,
        }
        manifest.update(state["provider_manifest_overrides"])  # type: ignore[arg-type]
        _write_json(manifest_path, manifest)
        claim_path = approval.claim_output_path(DATE, SLOT_ID)
        receipt_path = approval.receipt_output_path(DATE, SLOT_ID)
        claim = {
            "report_type": "lena_higgsfield_generation_claim",
            "schema_version": "v1",
            "slot_id": SLOT_ID,
            "date": DATE,
            "claimed_at_utc": "2026-07-18T01:00:00+00:00",
            "consumed_attempt_number": 1,
            "state": "claimed_pending_receipt",
        }
        receipt = {
            "report_type": "lena_higgsfield_generation_execution_receipt",
            "schema_version": "v1",
            "slot_id": SLOT_ID,
            "date": DATE,
            "provider_job_id": "job-123",
            "provider_status": "completed",
            "output_path": str(image_path),
            "actual_manifest_path": str(manifest_path),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha(manifest_path),
            "generated_image_path": str(image_path),
            "generated_image_sha256": _sha(image_path),
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        }
        _write_json(claim_path, claim)
        _write_json(receipt_path, receipt)
        return {
            "ok": True,
            "date": DATE,
            "slot_id": SLOT_ID,
            "recipe_id": RECIPE_ID,
            "selected_slot_id": SLOT_ID,
            "selected_recipe_id": RECIPE_ID,
            "claim_path": claim_path,
            "receipt_path": receipt_path,
            "manifest_path": manifest_path,
            "claim_written": True,
            "receipt_written": True,
            "manifest_written": True,
            "provider_submission_may_have_occurred": True,
            "subprocess_start_attempted": True,
            "provider_call_performed": True,
            "generation_performed": True,
            "live_result": {
                "job_id": "job-123",
                "status": "completed",
                "saved_image_path": str(image_path),
                "image_format_detected": "png",
                "provider_submission_may_have_occurred": True,
                "subprocess_start_attempted": True,
            },
            "manifest_record": manifest,
            "receipt_info": {"receipt_path": receipt_path, "receipt_repo_path": str(receipt_path)},
        }

    def fake_load_reference_specs():
        return state["reference_authority"], _sha(Path(state["reference_authority"])), [(reference_path, _sha(reference_path))]  # type: ignore[arg-type]

    def fake_evaluate_photo_qa_disposition(**kwargs):
        state["qa_calls"] = int(state["qa_calls"]) + 1
        artifact = {
            "report_type": "lena_presence_output_qa",
            "schema_version": "v2",
            "slot_id": SLOT_ID,
            "date": DATE,
            "disposition": state["qa_disposition"],
            "overall": state["qa_overall"],
            "provider_job_id": "job-123",
            "image_sha256": _sha(bundle["image_path"]),
            "generation_provenance": {"date": DATE},
            "reason_codes": state.get("qa_reason_codes", []),
            "exact_next_allowed_action": state.get("qa_exact_next_allowed_action", "existing_downstream_qa_and_human_review_gates_only"),
            "production_scoring": {
                "styling_sexy_platform_safe": {
                    "status": "pass" if state["qa_disposition"] == "accept" else "fail",
                    "notes": "adult non-explicit styling allowed" if state["qa_disposition"] == "accept" else "safety issue",
                }
            },
        }
        return artifact

    def fake_write_disposition_artifact(artifact: dict, output_root: Path | None = None):
        root = output_root or (tmp_path / "pipeline" / "asset_review" / "lena" / "presence_output_qa")
        path = root / DATE / SLOT_ID / f"presence_qa_{SLOT_ID}_00.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing == artifact:
                return path, existing, False
            raise photo_qa.CollisionError("corrupt_or_untrusted_evidence", f"conflicting QA disposition already exists; refusing overwrite: {path}")
        _write_json(path, artifact)
        return path, artifact, True

    def fake_run_publisher(*, platform: str, payload_path: Path) -> dict[str, object]:
        state["publish_calls"] = int(state["publish_calls"]) + 1
        assert platform == PLATFORM
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if state["publish_error"] is not None:
            raise state["publish_error"]  # type: ignore[misc]
        result = {
            "post_id": "post-123",
            "post_url": "https://example.invalid/post-123",
            "posted_at": "2026-07-18T01:02:03Z",
        }
        result.update(state["publish_overrides"])  # type: ignore[arg-type]
        result["payload_path"] = payload_path
        result["payload_sha256"] = _sha(payload_path)
        result["payload"] = payload
        result["cmd"] = ["publisher"]
        result["cmd_text"] = "publisher"
        result["returncode"] = 0
        result["stdout"] = json.dumps({"ok": True, **result}, default=str)
        result["stderr"] = ""
        result["parsed"] = {"ok": True, **result}
        return result

    monkeypatch.setattr(higgsfield_executor, "execute_approved_handoff_live_generation", fake_execute_approved_handoff_live_generation)
    monkeypatch.setattr(cycle, "_load_reference_specs", fake_load_reference_specs)
    monkeypatch.setattr(photo_qa, "evaluate_photo_qa_disposition", fake_evaluate_photo_qa_disposition)
    monkeypatch.setattr(photo_qa, "write_disposition_artifact", fake_write_disposition_artifact)
    monkeypatch.setattr(cycle, "_run_publisher", fake_run_publisher)
    return state


def _run_cycle(bundle: dict[str, Path | dict], *, simulate: bool, report_root: Path):
    return cycle.run_cycle(bundle["auth_path"], simulate=simulate, report_root=report_root)  # type: ignore[arg-type]


def _run_cycle_outcome(bundle: dict[str, Path | dict], *, simulate: bool, report_root: Path):
    try:
        return ("report", _run_cycle(bundle, simulate=simulate, report_root=report_root))
    except cycle.LenaBoundedLiveCycleError as exc:
        return ("error", exc)


def test_controlled_live_success_autonomously_cleans_queues_schedules_and_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, controlled=True)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    admissions: list[dict] = []

    monkeypatch.setattr(
        autonomous_publisher,
        "_validate_policy_artifact",
        lambda path: {
            "path": Path(path),
            "sha256": "p" * 64,
            "artifact": {
                "policy_id": "lena_approved_queue_auto_publisher_policy_v2_8",
                "policy_version": "v2.8.0",
            },
        },
    )

    def fake_admit(**kwargs):
        admissions.append(kwargs)
        assert Path(kwargs["asset_path"]).is_file()
        assert kwargs["schedule_slot"] == "morning"
        assert kwargs["lineage"]["qa_sha256"]
        return {"queue_path": str(tmp_path / "queue.csv"), "queue_id": "controlled-queue-1", "created": True}

    monkeypatch.setattr(autonomous_publisher, "admit_controlled_photo", fake_admit)
    monkeypatch.setattr(
        autonomous_publisher,
        "run_scheduled_autonomous",
        lambda **kwargs: {
            "ok": True,
            "posted_count": 1,
            "publish_calls_performed": 1,
            "receipt_paths": [str(tmp_path / "publish-receipt.json")],
        },
    )

    report = _run_cycle(
        bundle,
        simulate=False,
        report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles",
    )

    assert report["ok"] is True, report.get("failure")
    assert report["autonomous_disposition"] == "accept_and_publish"
    assert report["human_review_required"] is False
    assert report["human_per_cycle_approval_required"] is False
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert report["queue_mutated"] is True
    assert report["publish_performed"] is True
    assert admissions and state["qa_calls"] == 1


def test_controlled_hair_rejection_executes_one_retry_then_publishes_without_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, controlled=True)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    qa_count = {"value": 0}
    retry_slot = f"{SLOT_ID}-retry01"
    retry_handoff_path = _write_json(tmp_path / "retry-handoff.json", {"retry": 1})
    retry_approval_path = _write_json(tmp_path / "retry-approval.json", {"approval": 1})

    def fake_identity(**kwargs):
        path = Path(kwargs["identity_evidence_path"])
        payload = {
            "date": kwargs["date_str"],
            "slot_id": kwargs["slot_id"],
            "local_image_sha256": kwargs["image_sha256"],
        }
        _write_json(path, payload)
        return path, payload, True

    def fake_qa(**kwargs):
        qa_count["value"] += 1
        if qa_count["value"] == 1:
            return {
                "report_type": "lena_photo_qa_disposition",
                "schema_version": "v1",
                "slot_id": SLOT_ID,
                "date": DATE,
                "disposition": "retryable_failure",
                "overall": "fail",
                "reason_codes": ["hair_crown_forelock_artifact"],
                "image_sha256": kwargs["expected_image_sha256"],
            }
        return {
            "report_type": "lena_photo_qa_disposition",
            "schema_version": "v1",
            "slot_id": retry_slot,
            "date": DATE,
            "disposition": "accept",
            "overall": "pass",
            "reason_codes": [],
            "image_sha256": kwargs["expected_image_sha256"],
        }

    def fake_write_qa(artifact, output_root=None):
        path = tmp_path / "qa" / f"qa-{qa_count['value']}.json"
        _write_json(path, artifact)
        return path, artifact, True

    monkeypatch.setattr(cycle, "_build_local_identity_evidence", fake_identity)
    monkeypatch.setattr(photo_qa, "evaluate_photo_qa_disposition", fake_qa)
    monkeypatch.setattr(photo_qa, "write_disposition_artifact", fake_write_qa)
    monkeypatch.setattr(
        cycle.retry_handoff,
        "evaluate_retry_handoff",
        lambda **kwargs: {
            "retry_handoff_artifact_path": str(retry_handoff_path),
            "retry_handoff_fingerprint_sha256": "r" * 64,
        },
    )
    retry_facts = {
        "date": DATE,
        "slot_id": retry_slot,
        "prompt_sha256": "9" * 64,
        "retry_handoff_sha256": _sha(retry_handoff_path),
        "retry_handoff_fingerprint_sha256": "r" * 64,
    }
    monkeypatch.setattr(
        cycle,
        "_issue_controlled_retry_approval",
        lambda auth, path: {
            "approval_path": retry_approval_path,
            "approval_sha256": _sha(retry_approval_path),
            "retry_facts": retry_facts,
        },
    )
    retry_image = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{retry_slot}_seed.png"
    retry_manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / retry_slot / "result_manifest.json"
    retry_claim_path = _write_json(tmp_path / "retry-claim.json", {"claim": 1})
    retry_receipt_path = _write_json(tmp_path / "retry-receipt.json", {"receipt": 1})

    def fake_retry_execute(*args, **kwargs):
        _write_image(retry_image)
        _write_json(
            retry_manifest_path,
            {
                "provider": "higgsfield",
                "date": DATE,
                "slot_id": retry_slot,
                "prompt_sha256": retry_facts["prompt_sha256"],
                "provider_job_id": "job-retry",
                "provider_status": "completed",
                "saved_image_path": str(retry_image),
                "saved_image_sha256": _sha(retry_image),
            },
        )
        return {"ok": True}

    monkeypatch.setattr(higgsfield_executor, "execute_approved_retry_live_generation", fake_retry_execute)
    monkeypatch.setattr(
        cycle,
        "_validate_completed_retry_provider_result",
        lambda result, retry_facts: {
            "claim_path": retry_claim_path,
            "receipt_path": retry_receipt_path,
            "manifest_path": retry_manifest_path,
            "provider_manifest": json.loads(retry_manifest_path.read_text(encoding="utf-8")),
            "provider_claim": {"claim": 1},
            "provider_receipt": {"receipt": 1},
            "generated_image_path": retry_image,
            "generated_image_sha256": _sha(retry_image),
        },
    )
    monkeypatch.setattr(
        autonomous_publisher,
        "_validate_policy_artifact",
        lambda path: {"sha256": "p" * 64, "artifact": {"policy_id": "lena_approved_queue_auto_publisher_policy_v2_8", "policy_version": "v2.8.0"}},
    )
    monkeypatch.setattr(autonomous_publisher, "admit_controlled_photo", lambda **kwargs: {"queue_path": str(tmp_path / "queue.csv"), "queue_id": "retry-queue", "created": True})
    monkeypatch.setattr(autonomous_publisher, "run_scheduled_autonomous", lambda **kwargs: {"posted_count": 1, "publish_calls_performed": 1})

    report = _run_cycle(
        bundle,
        simulate=False,
        report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles",
    )

    assert report["autonomous_disposition"] == "accept_and_publish"
    assert report["provider_calls_performed"] == 2
    assert report["retries_performed"] == 1
    assert report["retry_executed"] is True
    assert report["human_review_required"] is False
    assert qa_count["value"] == 2


def test_controlled_missing_or_malformed_visual_qa_records_operational_failure_without_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, controlled=True)
    _install_live_fakes(monkeypatch, bundle, tmp_path)
    publish = {"count": 0}
    monkeypatch.setattr(
        photo_qa,
        "evaluate_photo_qa_disposition",
        lambda **kwargs: (_ for _ in ()).throw(photo_qa.BoundaryError("visual_review_unavailable", "malformed automated observations")),
    )
    monkeypatch.setattr(
        autonomous_publisher,
        "run_scheduled_autonomous",
        lambda **kwargs: publish.__setitem__("count", publish["count"] + 1),
    )

    report = _run_cycle(
        bundle,
        simulate=False,
        report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles",
    )

    assert report["ok"] is False
    assert report["failed_stage"] == "automated_visual_qa"
    assert report["failure"]["code"] == "visual_review_unavailable"
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 0
    assert publish["count"] == 0


def test_policy_issue_and_simulation_success_chain_without_consumption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    bundle = _build_simulation_artifacts(tmp_path, bundle)

    first = _run_cycle(bundle, simulate=True, report_root=tmp_path / "reports_a")
    second = _run_cycle(bundle, simulate=True, report_root=tmp_path / "reports_b")

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["simulation_mode"] is True
    assert first["live_execution"] is False
    assert first["authorization_mode"] == "standing_autonomy_policy"
    assert first["provider_calls_performed"] == 0
    assert first["publish_calls_performed"] == 0
    assert first["authorization_consumption_implemented"] is False
    assert first["authorization_consumed"] is False
    assert second["authorization_consumed"] is False
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False
    assert first["child_artifacts"]["policy_artifact"]["path"].endswith("lena_standing_autonomy_policy_v1.json")
    assert first["child_artifacts"]["authorization_artifact"]["path"].endswith(f"{SLOT_ID}.json")


def test_simulation_nested_candidate_artifact_shape_validates_without_consumption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, nested_candidate=True)
    bundle = _build_simulation_artifacts(tmp_path, bundle)

    report = _run_cycle(bundle, simulate=True, report_root=tmp_path / "reports")

    assert report["ok"] is True
    assert report["simulation_mode"] is True
    assert report["live_execution"] is False
    assert report["authorization_consumed"] is False
    assert report["provider_calls_performed"] == 0
    assert report["publish_calls_performed"] == 0
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False


def test_live_success_consumes_authorization_and_binds_all_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    auth_sha_before = _sha(Path(bundle["auth_path"]))
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    report = _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports")

    auth_after = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    sidecar_artifact = report["child_artifacts"]["publish_sidecar"]
    sidecar_path = Path(sidecar_artifact["path"])
    assert sidecar_path.exists()
    assert sidecar_artifact["sha256"] == _sha(sidecar_path)
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["live_execution"] is True
    assert report["simulation_mode"] is False
    assert report["authorization_mode"] == "standing_autonomy_policy"
    assert report["human_per_cycle_approval_required"] is False
    assert report["human_per_cycle_approval_present"] is False
    assert report["authorization_consumption_implemented"] is True
    assert report["authorization_consumed"] is True
    assert report["authorization_artifact_sha256_before_consumption"] == auth_sha_before
    assert auth_after["consumed"] is True
    assert auth_after["cycle_id"] == report["cycle_id"]
    assert auth_after["cycle_authorization_sha256"] == auth_sha_before
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert report["retries_performed"] == 0
    assert state["provider_calls"] == 1
    assert state["publish_calls"] == 1
    assert state["qa_calls"] == 1
    assert state["provider_contexts"][0]["approval_result"]["handoff_facts"]["handoff_repo_path"] == state["expected_handoff_repo_path"]
    assert [stage["stage"] for stage in report["stage_coverage"]] == list(cycle.LIVE_STAGES)
    assert report["child_artifacts"]["policy_artifact"]["path"].endswith("lena_standing_autonomy_policy_v1.json")
    assert report["child_artifacts"]["authorization_artifact"]["sha256"] == auth_sha_before
    assert report["child_artifacts"]["candidate_artifact"]["sha256"] == _sha(Path(bundle["candidate_path"]))
    assert report["child_artifacts"]["generated_asset"]["sha256"] == _sha(Path(bundle["image_path"]))
    assert report["publish_receipt"]["remote_post_id"] == "post-123"
    assert report["analytics_handoff"]["remote_post_id"] == "post-123"
    assert "FINAL_PUBLISH_APPROVED_BY_NICOLAS" not in sidecar
    assert sidecar["authorization_mode"] == "standing_autonomy_policy"
    assert sidecar["publish_authorized_by_policy"] is True
    assert sidecar["human_per_cycle_approval_required"] is False
    assert sidecar["human_per_cycle_approval_present"] is False


def test_post_provider_validation_failure_writes_complete_aggregate_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    state["provider_manifest_overrides"] = {"saved_image_sha256": "0" * 64}

    report = _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports")

    assert report["ok"] is False
    assert report["failed_stage"] == "provider_generation_validation"
    assert report["failure"]["code"] == "provider_manifest_image_sha_mismatch"
    assert report["provider_calls_performed"] == 1
    assert report["provider_job_id"] == "job-123"
    assert report["generated_image_path"] == str(Path(bundle["image_path"]).resolve())
    assert report["generated_image_sha256"] == _sha(Path(bundle["image_path"]))
    assert report["publish_calls_performed"] == 0
    assert report["retries_performed"] == 0
    assert state["provider_calls"] == 1
    assert state["qa_calls"] == 0
    assert state["publish_calls"] == 0
    for label in ("claim", "receipt", "manifest", "generated_image"):
        assert report["provider_generation_evidence"][label]["path"]
        assert report["provider_generation_evidence"][label]["sha256"]


@pytest.mark.parametrize("nested_candidate", [False, True], ids=["flat", "nested"])
def test_live_candidate_artifact_shape_normalization_validates_both_candidate_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nested_candidate: bool
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, nested_candidate=nested_candidate)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)

    report = _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports")

    assert report["ok"] is True
    assert report["live_execution"] is True
    assert report["simulation_mode"] is False
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert state["provider_calls"] == 1
    assert state["publish_calls"] == 1
    assert state["provider_contexts"][0]["approval_result"]["handoff_facts"]["handoff_repo_path"] == state["expected_handoff_repo_path"]
    assert state["provider_contexts"][0]["approval_result"]["handoff_facts"]["selected_candidate"]["candidate_id"] == f"{SLOT_ID}::{RECIPE_ID}::{HOOK_ID}"
    assert report["child_artifacts"]["candidate_artifact"]["sha256"] == _sha(Path(bundle["candidate_path"]))
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True


@pytest.mark.parametrize(
    "field, expected_code",
    [
        ("candidate_id", "candidate_id_mismatch"),
        ("slot_id", "slot_id_mismatch"),
        ("generation_handoff_artifact_sha256", "handoff_sha_mismatch"),
        ("generation_handoff_artifact_path", "handoff_path_escape"),
        ("generation_handoff_artifact_path", "handoff_artifact_path_missing"),
    ],
)
def test_live_nested_candidate_binding_mismatches_fail_closed_without_provider_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, expected_code: str
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, nested_candidate=True)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    if field in {"candidate_id", "slot_id"}:
        nested_candidate = json.loads(Path(bundle["candidate_path"]).read_text(encoding="utf-8"))["candidate"]
        nested_candidate[field] = f"mismatch-{field}"
        _rewrite_candidate_shape_and_bindings(bundle, nested_candidate=nested_candidate)
    else:
        auth = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
        if field == "generation_handoff_artifact_sha256":
            auth[field] = "0" * 64
        elif expected_code == "handoff_artifact_path_missing":
            auth[field] = ""
        else:
            auth[field] = "C:/escape.json"
        _write_auth_json(Path(bundle["auth_path"]), auth)

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports")
    if kind == "error":
        assert value.code == expected_code
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == expected_code

    assert int(state["provider_calls"]) == 0
    assert int(state["publish_calls"]) == 0
    assert int(state["qa_calls"]) == 0
    consumed = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"]
    if expected_code in {"candidate_id_mismatch", "slot_id_mismatch"}:
        assert consumed is True
    else:
        assert consumed is False


def test_non_expiring_standing_policy_validates_and_issues_short_lived_cycle_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    policy = standing_autonomy.validate_policy_artifact(Path(bundle["policy_path"]))
    assert policy["expires_at_utc"] is None
    Path(bundle["auth_path"]).unlink()

    auth_bundle = standing_autonomy.issue_cycle_authorization(
        Path(bundle["policy_path"]),
        Path(bundle["handoff_path"]),
        auth_root=tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles",
        report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles",
    )
    auth = json.loads(Path(auth_bundle["path"]).read_text(encoding="utf-8"))
    issued_at = datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc)
    expires_at = datetime.fromisoformat(str(auth["expires_at_utc"]).replace("Z", "+00:00"))
    assert expires_at > issued_at
    assert expires_at - issued_at <= timedelta(minutes=30)
    assert auth["consumed"] is False


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda policy: policy.__setitem__("report_type", "wrong"), "policy_report_type_mismatch"),
        (lambda policy: policy.__setitem__("schema_version", "v0"), "policy_schema_mismatch"),
        (lambda policy: policy.__setitem__("autonomy_enabled", False), "policy_autonomy_disabled"),
        (lambda policy: policy.__setitem__("live_generation_enabled", False), "policy_live_generation_disabled"),
        (lambda policy: policy.__setitem__("live_publishing_enabled", False), "policy_live_publishing_disabled"),
        (lambda policy: policy.__setitem__("kill_switch_enabled", False), "policy_kill_switch_disabled"),
        (lambda policy: policy.__setitem__("effective_at_utc", "2026-07-20T00:00:00Z"), "policy_effective_at_future_invalid"),
        (lambda policy: policy.__setitem__("expires_at_utc", "2026-07-18T00:00:00Z"), "policy_expired"),
        (lambda policy: policy.__setitem__("daily_spend_ceiling", 0.0), "policy_daily_spend_ceiling_invalid"),
    ],
)
def test_policy_validation_blocks_authorization_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    policy = json.loads(Path(bundle["policy_path"]).read_text(encoding="utf-8"))
    mutator(policy)
    _write_json(Path(bundle["policy_path"]), policy)

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.issue_cycle_authorization(Path(bundle["policy_path"]), Path(bundle["handoff_path"]), auth_root=tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles", report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles")

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda auth: auth.__setitem__("report_type", "wrong"), "authorization_report_type_mismatch"),
        (lambda auth: auth.__setitem__("schema_version", "v0"), "authorization_schema_mismatch"),
        (lambda auth: auth.__setitem__("one_slot", False), "authorization_one_slot_invalid"),
        (lambda auth: auth.__setitem__("one_candidate", False), "authorization_one_candidate_invalid"),
        (lambda auth: auth.__setitem__("one_asset", False), "authorization_one_asset_invalid"),
        (lambda auth: auth.__setitem__("one_platform", False), "authorization_one_platform_invalid"),
        (
            lambda auth: (
                auth.__setitem__("issued_at_utc", "2020-07-18T00:00:00Z"),
                auth.__setitem__("expires_at_utc", "2020-07-18T00:30:00Z"),
            ),
            "authorization_expired",
        ),
        (lambda auth: auth.__setitem__("provider_call_cap_per_cycle", 2), "provider_call_cap_invalid"),
        (lambda auth: auth.__setitem__("publish_action_cap_per_cycle", 2), "publish_action_cap_invalid"),
        (lambda auth: auth.__setitem__("retry_cap_per_cycle", 1), "retry_cap_invalid"),
        (lambda auth: auth.__setitem__("daily_spend_ceiling", 0.0), "daily_spend_cap_invalid"),
        (lambda auth: auth.__setitem__("kill_switch_enabled", False), "authorization_kill_switch_disabled"),
        (lambda auth: auth.__setitem__("publish_authorized", False), "publish_authorized_invalid"),
        (lambda auth: auth.__setitem__("consumed", True), "authorization_already_consumed"),
        (lambda auth: auth.__setitem__("slot_id", "wrong-slot"), "authorization_slot_mismatch"),
        (lambda auth: auth.__setitem__("candidate_id", "wrong"), "authorization_candidate_mismatch"),
        (lambda auth: auth.__setitem__("expected_output_directory", "../escape"), "expected_output_directory_escape"),
        (lambda auth: auth.__setitem__("allowed_output_extensions", [".gif"]), "allowed_output_extensions_invalid"),
        (lambda auth: auth.__setitem__("platform", "Facebook Page"), "platform_invalid"),
    ],
)
def test_live_authorization_rejections_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    auth = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    mutator(auth)
    _write_auth_json(Path(bundle["auth_path"]), auth)
    before = Path(bundle["auth_path"]).read_bytes()

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports")
    if kind == "error":
        assert value.code == expected_code
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == expected_code

    after = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    if expected_code == "authorization_already_consumed":
        assert after["consumed"] is True
    else:
        assert after["consumed"] is False


def test_duplicate_report_rejected_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    report_root = tmp_path / "reports"
    fixed = report_root / DATE / "lena_bounded_live_cycle_2026-07-18_010203.json"
    fixed.parent.mkdir(parents=True, exist_ok=True)
    fixed.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "_report_path", lambda day, stamp, report_root=report_root: fixed)

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        _run_cycle(bundle, simulate=False, report_root=report_root)

    assert exc_info.value.code == "report_already_exists"
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False


def test_existing_conflicting_output_blocks_before_authorization_consumption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    conflicting_image = Path(bundle["image_path"])
    _write_image(conflicting_image)

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports")
    if kind == "error":
        assert value.code == "expected_output_conflict"
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == "expected_output_conflict"

    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False


def test_live_concurrent_invocation_rejected_after_consumption_begins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    gate = threading.Event()
    release = threading.Event()
    original = higgsfield_executor.execute_approved_handoff_live_generation

    def waiting_executor(*args, **kwargs):
        gate.set()
        release.wait(timeout=5)
        return original(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(higgsfield_executor, "execute_approved_handoff_live_generation", waiting_executor)
    results: list[tuple[str, object]] = []

    def first_run():
        try:
            results.append(("first", _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports_a")))
        except Exception as exc:  # pragma: no cover - diagnostic
            results.append(("first-error", exc))

    thread = threading.Thread(target=first_run)
    thread.start()
    assert gate.wait(timeout=5), "first invocation never reached provider stage"

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports_b")

    release.set()
    thread.join(timeout=5)
    assert exc_info.value.code in {"authorization_consumption_in_progress", "authorization_already_consumed"}
    assert int(state["provider_calls"]) >= 1
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True


@pytest.mark.parametrize(
    "stage, error_code",
    [
        ("provider", "provider_generation_failed"),
        ("qa", "qa_rejected"),
        ("publish", "publish_failed"),
    ],
)
def test_live_failure_keeps_authorization_consumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, error_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)

    if stage == "provider":
        def fail_provider(*args, **kwargs):
            raise cycle.LenaBoundedLiveCycleError(error_code, "provider stage failed")
        monkeypatch.setattr(higgsfield_executor, "execute_approved_handoff_live_generation", fail_provider)
    elif stage == "qa":
        state["qa_disposition"] = "hard_stop"
        state["qa_overall"] = "fail"
    else:
        state["publish_error"] = cycle.LenaBoundedLiveCycleError("publish_failed", "publisher failed")

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports")
    if kind == "error":
        assert value.code == error_code
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == error_code
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True
    assert int(state["provider_calls"]) == (0 if stage == "provider" else 1)
    assert int(state["publish_calls"]) == (1 if stage == "publish" else 0)
    assert int(state["qa_calls"]) == (1 if stage in {"qa", "publish"} else 0)


def test_controlled_provider_failure_report_serializes_path_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch, controlled=True)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    claim_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / "failed_claim.json"
    receipt_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / "failed_receipt.json"
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "failed_manifest.json"

    def fail_provider_with_path_values(*args, **kwargs):
        state["provider_calls"] = int(state["provider_calls"]) + 1
        return {
            "ok": False,
            "failure_stage": "provider_output_parse_failure",
            "failure_error_text": "Failed to parse --json output as JSON",
            "claim_info": {
                "claim_path": claim_path,
                "claim_repo_path": claim_path.relative_to(tmp_path).as_posix(),
            },
            "claim_path": claim_path,
            "manifest_path": manifest_path,
            "receipt_info": {
                "receipt_path": receipt_path,
                "receipt_repo_path": receipt_path.relative_to(tmp_path).as_posix(),
            },
            "receipt_path": receipt_path,
            "receipt_repo_path": receipt_path.relative_to(tmp_path).as_posix(),
            "provider_submission_may_have_occurred": True,
            "subprocess_start_attempted": True,
            "provider_call_performed": True,
            "receipt_written": True,
        }

    monkeypatch.setattr(higgsfield_executor, "execute_approved_handoff_live_generation", fail_provider_with_path_values)

    report = _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports")

    assert report["ok"] is False
    assert report["failed_stage"] == "provider_generation"
    assert report["failure"]["code"] == "provider_output_parse_failure"
    assert report["provider_generation_result"]["claim_path"] == str(claim_path)
    assert report["provider_generation_result"]["claim_info"]["claim_path"] == str(claim_path)
    assert report["provider_generation_result"]["receipt_path"] == str(receipt_path)
    assert report["provider_generation_result"]["receipt_info"]["receipt_path"] == str(receipt_path)
    persisted = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
    assert persisted["provider_generation_result"]["claim_path"] == str(claim_path)
    assert persisted["provider_generation_result"]["receipt_info"]["receipt_path"] == str(receipt_path)
    assert int(state["provider_calls"]) == 1
    assert int(state["qa_calls"]) == 0
    assert int(state["publish_calls"]) == 0


def test_live_blocked_human_visual_review_stops_without_publish_or_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    state["qa_disposition"] = "blocked"
    state["qa_overall"] = "blocked"
    state["qa_reason_codes"] = ["human_visual_review_required"]
    state["qa_exact_next_allowed_action"] = "human_visual_review_required"

    report = _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports")

    assert report["ok"] is True
    assert report["qa_lifecycle_status"] == "awaiting_human_visual_review"
    assert report["next_allowed_action"] == "human_visual_review_required"
    assert report["publish_authorized"] is False
    assert report["publish_performed"] is False
    assert report["queue_mutated"] is False
    assert report["retry_executed"] is False
    assert int(state["provider_calls"]) == 1
    assert int(state["qa_calls"]) == 1
    assert int(state["publish_calls"]) == 0
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda auth: auth.__setitem__("candidate_artifact_path", "../escape.json"), "candidate_path_escape"),
        (lambda auth: auth.__setitem__("candidate_artifact_sha256", "0" * 64), "authorization_candidate_sha_mismatch"),
        (lambda auth: auth.__setitem__("prompt_sha256", "0" * 64), "authorization_prompt_sha_mismatch"),
        (lambda auth: auth.__setitem__("policy_artifact_path", "../policy.json"), "policy_path_escape"),
    ],
)
def test_live_binding_mismatches_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    _install_live_fakes(monkeypatch, bundle, tmp_path)
    auth = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    mutator(auth)
    _write_auth_json(Path(bundle["auth_path"]), auth)

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports")
    if kind == "error":
        assert value.code == expected_code
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == expected_code
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False


def test_issue_cycle_authorization_rejects_split_brain_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    auth_path.unlink()

    handoff_path = Path(bundle["handoff_path"])
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["structured_executor_inputs"]["selected_prompt_sha256"] = "f" * 64
    handoff["structured_executor_inputs"]["selected_prompt_text"] = "split-brain prompt"
    handoff["prompt_sha256"] = "f" * 64
    _write_json(handoff_path, handoff)

    provider_calls = {"count": 0}

    def fail_if_called(*args, **kwargs):
        provider_calls["count"] += 1
        raise AssertionError("provider executor should not be called")

    monkeypatch.setattr(higgsfield_executor, "execute_approved_handoff_live_generation", fail_if_called)

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.issue_cycle_authorization(
            Path(bundle["policy_path"]),
            handoff_path,
            auth_root=tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles",
            report_root=tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles",
        )
    assert exc_info.value.code == "handoff_prompt_binding_split_brain"
    assert provider_calls["count"] == 0
    assert not auth_path.exists()


def test_live_report_path_symlink_escape_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_bundle(tmp_path, monkeypatch)
    _install_live_fakes(monkeypatch, bundle, tmp_path)
    report_root = tmp_path / "reports"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks not supported")
    link = report_root / DATE
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation not permitted: {exc}")

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        _run_cycle(bundle, simulate=False, report_root=report_root)

    assert exc_info.value.code == "report_path_escape"
