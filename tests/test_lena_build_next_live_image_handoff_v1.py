from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff


DATE = "2026-07-13"
SLOT_ID = "lenagate2026071325ca9e1d-pack000-01-photo"
RECIPE_ID = "hcr_006"
EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
DRY_RUN_COMMAND = f"python {EXECUTOR_PATH} --date {DATE} --slot-id {SLOT_ID}"
LIVE_COMMAND = f"{DRY_RUN_COMMAND} --live"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _learning_payload(status: str) -> dict:
    follow_up = {
        "current": "no_follow_up_required",
        "usable_but_incomplete": "complete_missing_metrics_or_refresh_learning",
        "stale_unresolved": "refresh_or_resolve_stale_unresolved_posts",
        "manual_or_future_capability_required": "manual_or_future_capability_resolution_required",
    }.get(status, "rebuild_and_pass_an_explicit_learning_artifact")
    return {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": DATE,
        "published_post_count": 3,
        "pending_metrics_posts": [{}, {}],
        "stale_pending_metrics_posts": [{}],
        "winner_posts": [{"recipe_id": RECIPE_ID}],
        "queue_boosts": {"preferred_recipe_ids": [RECIPE_ID]},
        "metrics_resolution_summary": {
            "learning_status": status,
            "current_count": 1,
            "usable_but_incomplete_count": 1 if status == "usable_but_incomplete" else 0,
            "stale_unresolved_count": 1 if status == "stale_unresolved" else 0,
            "manual_or_future_capability_required_count": 1 if status == "manual_or_future_capability_required" else 0,
        },
    }, follow_up


def _recommendation_payload(learning_path: Path, status: str = "current") -> dict:
    learning, follow_up = _learning_payload(status)
    return {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_artifact_path": str(learning_path),
        "learning_status": status,
        "learning_status_label": {
            "current": "learning_current",
            "usable_but_incomplete": "learning_degraded_incomplete",
            "stale_unresolved": "learning_stale_unresolved",
            "manual_or_future_capability_required": "learning_manual_or_future_capability_required",
        }.get(status, "learning_unavailable"),
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": learning["published_post_count"],
        "learning_pending_metrics_count": len(learning["pending_metrics_posts"]),
        "learning_stale_pending_metrics_count": len(learning["stale_pending_metrics_posts"]),
        "learning_resolution_state_summary": learning["metrics_resolution_summary"],
        "learning_required_follow_up_action": follow_up,
        "learning_winner_post_count": len(learning["winner_posts"]),
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
            }
        ],
    }


def _candidate_payload(command: str = DRY_RUN_COMMAND) -> dict:
    candidate = {
        "activity": "stepping out near the entrance of a low-lit lounge.",
        "candidate_id": f"{SLOT_ID}::hcr_006::cbn_004",
        "caption_seed": "caught me on the way in",
        "choice_eligible": True,
        "concept_summary": "stepping out near the entrance of a low-lit lounge. | flash-adjacent nightlife social photo, 35mm lens.",
        "creative_temperature": "glamorous",
        "deterministic_noncreative_tiebreak": ["night out", "hcr_006", "cbn_004", SLOT_ID],
        "exact_proposed_dry_run_command": command,
        "hook_id": "cbn_004",
        "hook_text": "Tried To Dress Down. Failed.",
        "lane": "night out",
        "lighting_text": "warm venue spill light mixed with city-night ambient light, realistic highlight rolloff, slight low-light grain",
        "narrative_roles": ["anticipation", "experience", "payoff"],
        "payoff_claimed": False,
        "payoff_eligible": True,
        "pose": "hair_touch_confident_gaze",
        "pose_body_language_id": "pose_p017",
        "primary_pillar": "beautiful_trouble",
        "prompt_sha256": "48260be45ea28a236dabae2c34876e45aa21fef55e98bf2f63a22ac890b2ce2d",
        "ranking_evidence": {"identity_consistency": "passed canonical Soul identity hard gate"},
        "recipe_binding": "strategy compatibility",
        "recipe_id": RECIPE_ID,
        "scene_identity_field": "lane",
        "slot_id": SLOT_ID,
        "strategy_compatibility_evidence": {
            "generated_environment_exact_match": None,
            "generated_wardrobe_exact_match": False,
            "recipe_environment_id": "env_p001",
            "recipe_wardrobe_outfit_id": "wc_p059",
        },
        "supporting_pillar": "audience_choice_and_payoff",
        "visual_style": "skirt_set",
        "wardrobe_outfit_id": "wc_p017",
    }
    return {
        "as_of_date": DATE,
        "authority_commit": "25ca9e1d5bc00dd766ed3ec36bae4433e8769f02",
        "candidate": candidate,
        "candidate_status": "selected",
        "confidence": "medium",
        "decision_fingerprint_sha256": "12879928698742649ceb9bf817fc82cbad23947b8d9a42743b5fef3a69f05336",
        "evidence": {"recent_content_evidence_semantics": "exact recorded fields only; missing fields remain unknown"},
        "exact_next_allowed_action": command,
        "final_action": "prepare_higgsfield_still_dry_run_for_review",
        "generated_at_utc": "2026-07-14T03:26:44.255326Z",
        "influencer_id": "lena",
        "input_provenance": [],
        "noncritical_evidence_gaps": ["historical creative temperature is unknown; non-high-heat selection remains allowed"],
        "provider_authorized": False,
        "rejected_or_blocked_reasons": [],
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "side_effects_performed": [],
        "strategy_contract": {"canonical_niche": "Glamour, Choices, And Beautiful Trouble"},
    }


def _build_fixture_tree(tmp_root: Path, *, learning_status: str = "current", recipe_id: str = RECIPE_ID, command: str = DRY_RUN_COMMAND) -> tuple[Path, Path, Path, Path]:
    next_actions = tmp_root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    prompt_dir = tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    prompt_path = prompt_dir / "lena_pre_generation_candidate_25ca9e1d_128799286987.json"

    learning, _follow_up = _learning_payload(learning_status)
    _write_json(learning_path, learning)
    _write_json(recommendation_path, _recommendation_payload(learning_path, learning_status))
    _write_json(queue_path, _queue_payload(recipe_id))
    _write_json(prompt_path, _candidate_payload(command))
    return recommendation_path, learning_path, queue_path, prompt_path


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(handoff, "ROOT", tmp_path)
    monkeypatch.setattr(handoff, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(handoff, "PRE_GENERATION_CANDIDATES", tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates")


def test_build_handoff_creates_matching_json_and_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, _, prompt_path = _build_fixture_tree(tmp_path)
    monkeypatch.setattr(handoff, "iso_now", lambda: "2026-07-14T12:34:56+00:00")

    report = handoff.build_handoff(DATE)
    json_path, md_path = handoff.save_handoff(report, DATE)

    assert report["report_type"] == "lena_next_live_image_handoff"
    assert report["schema_version"] == "v1"
    assert report["date"] == DATE
    assert report["created_at"] == "2026-07-14T12:34:56+00:00"
    assert report["execution_owner"] == "claude"
    assert report["provider"] == "higgsfield"
    assert report["executor_type"] == "higgsfield_cli"
    assert report["repo_executor_path"] == EXECUTOR_PATH
    assert report["selected_slot_id"] == SLOT_ID
    assert report["media_content_type"] == "image"
    assert report["slot_media_type"] == "photo"
    assert report["selected_hook_text"] == "Tried To Dress Down. Failed."
    assert report["source_recommendation_artifact_path"].endswith(f"lena_next_generation_step_{DATE}.json")
    assert report["source_learning_artifact_path"].endswith(f"lena_post_outcome_learning_state_{DATE}.json")
    assert report["source_queue_dry_run_artifact_path"].endswith(f"lena_autonomous_generation_queue_dryrun_{DATE}.json")
    assert report["selected_prompt_input_artifact_path"] == str(prompt_path)
    assert report["selected_prompt_input"]["artifact_sha256"] == hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    assert report["selected_prompt_input"]["prompt_sha256"] == "48260be45ea28a236dabae2c34876e45aa21fef55e98bf2f63a22ac890b2ce2d"
    assert report["selected_prompt_input"]["prompt_text"] is None
    assert report["selected_prompt_input"]["prompt_text_available"] is False
    assert report["selected_prompt_input"]["prompt_text_status"] == "not_persisted_in_authoritative_artifact"
    assert report["structured_executor_inputs"]["dry_run_command"] == DRY_RUN_COMMAND
    assert report["structured_executor_inputs"]["live_command"] == LIVE_COMMAND
    assert report["structured_executor_inputs"]["dry_run_argv"] == ["python", EXECUTOR_PATH, "--date", DATE, "--slot-id", SLOT_ID]
    assert report["structured_executor_inputs"]["live_argv"] == ["python", EXECUTOR_PATH, "--date", DATE, "--slot-id", SLOT_ID, "--live"]
    assert report["structured_executor_inputs"]["model"] == "text2image_soul_v2"
    assert report["structured_executor_inputs"]["aspect_ratio"] == "9:16"
    assert report["structured_executor_inputs"]["negative_prompt_enabled"] is False
    assert report["structured_executor_inputs"]["soul_metadata"]["name"] == "Lena"
    assert report["structured_executor_inputs"]["soul_metadata"]["type"] == "soul_2"
    assert report["packet_state"] == "packet_valid_for_claude_review"
    assert report["dry_run_executor_contract_state"] == "ready"
    assert report["live_execution_state"] == "blocked"
    assert report["live_execution_authorized"] is False
    assert report["generation_approval_required"] is True
    assert report["manual_operator_approval_required"] is True
    assert report["provider_call_performed"] is False
    assert report["generation_performed"] is False
    assert report["publish_authorized"] is False
    assert report["manual_publish_review_required"] is True
    assert report["learning_status"] == "current"
    assert report["learning_follow_up_action"] == "no_follow_up_required"
    assert report["learning_resolution_state_summary"]["learning_status"] == "current"
    assert report["source_recommendation"]["learning_signal_used"] == ["queue_boosts.preferred_recipe_ids", "winner_posts"]
    assert report["queue_head"]["recipe_id"] == RECIPE_ID
    assert report["validation"]["live_prompt_byte_check_required"] is True
    assert report["validation"]["queue_head_matches_recommendation"] is True
    assert report["validation"]["candidate_command_matches_repo_executor"] is True
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    markdown = md_path.read_text(encoding="utf-8")
    for expected in [
        DRY_RUN_COMMAND,
        LIVE_COMMAND,
        SLOT_ID,
        "packet_valid_for_claude_review",
        "dry-run executor contract state",
        "manual operator approval required",
        "Tried To Dress Down. Failed.",
        "not_persisted_in_authoritative_artifact",
    ]:
        assert expected in markdown


def test_learning_status_is_carried_truthfully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    for status, label, follow_up in [
        ("current", "learning_current", "no_follow_up_required"),
        ("usable_but_incomplete", "learning_degraded_incomplete", "complete_missing_metrics_or_refresh_learning"),
        ("stale_unresolved", "learning_stale_unresolved", "refresh_or_resolve_stale_unresolved_posts"),
        ("manual_or_future_capability_required", "learning_manual_or_future_capability_required", "manual_or_future_capability_resolution_required"),
    ]:
        _build_fixture_tree(tmp_path, learning_status=status)
        report = handoff.build_handoff(DATE)
        assert report["learning_status"] == status
        assert report["source_recommendation"]["learning_status_label"] == label
        assert report["learning_follow_up_action"] == follow_up
        assert report["learning_state_category"] == status


def test_queue_or_recommendation_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, queue_path, _ = _build_fixture_tree(tmp_path)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue["queue_slots"][0]["recipe_id"] = "hcr_999"
    _write_json(queue_path, queue)
    with pytest.raises(SystemExit, match="queue_head_mismatch"):
        handoff.build_handoff(DATE)


def test_candidate_command_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, command="python wrong.py")
    with pytest.raises(SystemExit, match="candidate_command_mismatch"):
        handoff.build_handoff(DATE)


def test_missing_learning_artifact_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    recommendation_path, learning_path, _, _ = _build_fixture_tree(tmp_path)
    learning_path.unlink()
    assert recommendation_path.is_file()
    with pytest.raises(SystemExit, match="missing_learning_artifact"):
        handoff.build_handoff(DATE)


def test_missing_recommendation_artifact_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    recommendation_path, _, _, _ = _build_fixture_tree(tmp_path)
    recommendation_path.unlink()
    with pytest.raises(SystemExit, match="missing_artifact"):
        handoff.build_handoff(DATE)


def test_malformed_queue_artifact_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)
    queue_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    queue_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(SystemExit, match="unreadable_artifact"):
        handoff.build_handoff(DATE)


def test_date_mismatch_in_candidate_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)
    candidate_path = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE / "lena_pre_generation_candidate_25ca9e1d_128799286987.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["as_of_date"] = "2026-07-12"
    _write_json(candidate_path, candidate)
    with pytest.raises(SystemExit, match="date_mismatch"):
        handoff.build_handoff(DATE)
