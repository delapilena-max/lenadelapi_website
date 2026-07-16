from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff


DATE = "2026-07-13"
RECIPE_ID = "hcr_006"
SLOT_ID = f"higgsfield-20260713-{RECIPE_ID}-photo"
EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
HANDOFF_PATH = f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"
HANDOFF_MD_PATH = f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.md"
HANDOFF_COMMAND = f"python {EXECUTOR_PATH} --handoff-artifact {HANDOFF_PATH}"
LIVE_COMMAND = f"{HANDOFF_COMMAND} --live"
PROMPT_INPUT_PATH = f"pipeline/strategy/lena/content_packets/{DATE}/lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
SELECTED_CANDIDATE_PATH = f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/lena_pre_generation_candidate_selected.json"
PROMPT_TEXT = "Scene: candlelit arrival. Wardrobe: structured black set. Lighting: realistic low-light skin texture."


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _learning_payload(status: str) -> tuple[dict, str]:
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
                "proof_lane_locked": True,
            }
        ],
    }


def _packet_payload(prompt_text: str = PROMPT_TEXT) -> dict:
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
        "platform_targets": ["Instagram Feed"],
        "best_content_type": "photo",
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


def _selected_candidate_payload(recipe_id: str = RECIPE_ID, slot_id: str = SLOT_ID, *, generated_at_utc: str = "2026-07-14T12:34:57Z") -> dict:
    prompt_sha = hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
    candidate_id = f"{slot_id}::{recipe_id}::cbn_004"
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
        "candidate_status": "selected",
        "candidate": {
            "candidate_id": candidate_id,
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


def _build_fixture_tree(tmp_root: Path, *, learning_status: str = "current", recipe_id: str = RECIPE_ID, prompt_text: str = PROMPT_TEXT, selected_recipe_id: str | None = None) -> tuple[Path, Path, Path, Path, Path]:
    next_actions = tmp_root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    packets = tmp_root / "pipeline" / "strategy" / "lena" / "content_packets" / DATE
    pre_generation = tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    packet_path = packets / f"lena_content_packet_dryrun_{DATE}_{recipe_id}.json"
    selected_path = pre_generation / "lena_pre_generation_candidate_selected.json"

    learning, _follow_up = _learning_payload(learning_status)
    _write_json(learning_path, learning)
    _write_json(recommendation_path, _recommendation_payload(learning_path, learning_status))
    _write_json(queue_path, _queue_payload(recipe_id))
    _write_json(packet_path, _packet_payload(prompt_text))
    _write_json(selected_path, _selected_candidate_payload(selected_recipe_id or recipe_id))
    return recommendation_path, learning_path, queue_path, packet_path, selected_path


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(handoff, "ROOT", tmp_path)
    monkeypatch.setattr(handoff, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(handoff, "CONTENT_PACKETS", tmp_path / "pipeline" / "strategy" / "lena" / "content_packets")
    monkeypatch.setattr(handoff, "PRE_GENERATION_CANDIDATES", tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates")


def test_build_handoff_creates_matching_json_and_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, _, packet_path, _ = _build_fixture_tree(tmp_path)
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
    assert report["expected_handoff_artifact_path"] == HANDOFF_PATH
    assert report["expected_handoff_markdown_path"] == HANDOFF_MD_PATH
    assert report["selected_prompt_input_artifact_path"] == PROMPT_INPUT_PATH
    assert report["selected_prompt_input"]["artifact_path"] == PROMPT_INPUT_PATH
    assert report["selected_prompt_input"]["artifact_sha256"] == hashlib.sha256(packet_path.read_bytes()).hexdigest()
    assert report["selected_prompt_input"]["prompt_sha256"] == hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
    assert report["selected_prompt_input"]["prompt_text"] == PROMPT_TEXT
    assert report["selected_prompt_input"]["prompt_text_available"] is True
    assert report["selected_prompt_input"]["prompt_text_status"] == "available"
    assert report["selected_prompt_input"]["packet_id"] == f"cpkt_20260713_{RECIPE_ID}"
    assert report["selected_prompt_input"]["exact_proposed_dry_run_command"] == HANDOFF_COMMAND
    assert report["source_selected_candidate_artifact_path"] == SELECTED_CANDIDATE_PATH
    assert report["selected_candidate"]["artifact_path"] == SELECTED_CANDIDATE_PATH
    assert report["selected_candidate"]["artifact_sha256"] == hashlib.sha256(
        (tmp_path / SELECTED_CANDIDATE_PATH).read_bytes()
    ).hexdigest()
    assert report["selected_candidate"]["candidate_id"] == f"{SLOT_ID}::{RECIPE_ID}::cbn_004"
    assert report["selected_candidate"]["slot_id"] == SLOT_ID
    assert report["selected_candidate"]["recipe_id"] == RECIPE_ID
    assert report["selected_candidate"]["prompt_sha256"] == hashlib.sha256(PROMPT_TEXT.encode("utf-8")).hexdigest()
    assert report["selected_prompt_input"]["selected_candidate_artifact_path"] == SELECTED_CANDIDATE_PATH
    assert report["structured_executor_inputs"]["dry_run_command"] == HANDOFF_COMMAND
    assert report["structured_executor_inputs"]["live_command"] == LIVE_COMMAND
    assert report["structured_executor_inputs"]["dry_run_argv"] == ["python", EXECUTOR_PATH, "--handoff-artifact", HANDOFF_PATH]
    assert report["structured_executor_inputs"]["live_argv"] == ["python", EXECUTOR_PATH, "--handoff-artifact", HANDOFF_PATH, "--live"]
    assert report["structured_executor_inputs"]["model"] == "text2image_soul_v2"
    assert report["structured_executor_inputs"]["aspect_ratio"] == "9:16"
    assert report["packet_state"] == "packet_valid_for_claude_review"
    assert report["dry_run_executor_contract_state"] == "ready"
    assert report["live_execution_state"] == "blocked"
    assert report["live_execution_authorized"] is False
    assert report["generation_approval_required"] is True
    assert report["manual_operator_approval_required"] is True
    assert report["provider_call_performed"] is False
    assert report["generation_performed"] is False
    assert report["learning_status"] == "current"
    assert report["queue_head"]["recipe_id"] == RECIPE_ID
    assert report["validation"]["selected_candidate_valid"] is True
    assert report["validation"]["selected_prompt_input_valid"] is True
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    markdown = md_path.read_text(encoding="utf-8")
    for expected in [HANDOFF_COMMAND, LIVE_COMMAND, SLOT_ID, report["selected_prompt_input"]["prompt_sha256"], report["selected_candidate"]["candidate_id"], str(SELECTED_CANDIDATE_PATH), "packet_valid_for_claude_review"]:
        assert expected in markdown


@pytest.mark.parametrize(
    "status,label,follow_up",
    [
        ("current", "learning_current", "no_follow_up_required"),
        ("usable_but_incomplete", "learning_degraded_incomplete", "complete_missing_metrics_or_refresh_learning"),
        ("stale_unresolved", "learning_stale_unresolved", "refresh_or_resolve_stale_unresolved_posts"),
        ("manual_or_future_capability_required", "learning_manual_or_future_capability_required", "manual_or_future_capability_resolution_required"),
    ],
)
def test_learning_status_is_carried_truthfully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, label: str, follow_up: str) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, learning_status=status)
    report = handoff.build_handoff(DATE)
    assert report["learning_status"] == status
    assert report["source_recommendation"]["learning_status_label"] == label
    assert report["learning_follow_up_action"] == follow_up
    assert report["learning_state_category"] == status


def test_queue_or_recommendation_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, queue_path, _, _ = _build_fixture_tree(tmp_path)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue["queue_slots"][0]["recipe_id"] = "hcr_999"
    _write_json(queue_path, queue)
    with pytest.raises(SystemExit, match="queue_head_mismatch"):
        handoff.build_handoff(DATE)


def test_selected_candidate_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, selected_recipe_id="hcr_008")
    with pytest.raises(SystemExit, match="selected_candidate_recommendation_mismatch"):
        handoff.build_handoff(DATE)


def test_missing_selected_candidate_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, _, _, selected_path = _build_fixture_tree(tmp_path)
    selected_path.unlink()
    with pytest.raises(SystemExit, match="missing_selected_candidate"):
        handoff.build_handoff(DATE)


def test_multiple_selected_candidates_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)
    extra_selected = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE / "lena_pre_generation_candidate_extra.json"
    _write_json(extra_selected, _selected_candidate_payload(generated_at_utc="2026-07-14T13:00:00Z"))
    with pytest.raises(SystemExit, match="ambiguous_selected_candidate"):
        handoff.build_handoff(DATE)


def test_malformed_and_non_selected_candidate_artifacts_are_ignored_when_one_selected_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, _, _, selected_path = _build_fixture_tree(tmp_path)
    candidate_dir = selected_path.parent
    (candidate_dir / "lena_pre_generation_candidate_malformed.json").write_text("{not-json", encoding="utf-8")
    _write_json(candidate_dir / "lena_pre_generation_candidate_abstain.json", {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": "085620d1a1dcf6fb647a3111b0b00f7ed652738c",
        "candidate_status": "abstain",
        "candidate": None,
        "decision_fingerprint_sha256": "6" * 64,
        "generated_at_utc": "2026-07-14T14:00:00Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    })
    report = handoff.build_handoff(DATE)
    assert report["source_selected_candidate_artifact_path"] == SELECTED_CANDIDATE_PATH


def test_missing_learning_artifact_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    recommendation_path, learning_path, _, _, _ = _build_fixture_tree(tmp_path)
    learning_path.unlink()
    assert recommendation_path.is_file()
    with pytest.raises(SystemExit, match="missing_learning_artifact"):
        handoff.build_handoff(DATE)


def test_missing_content_packet_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)
    packet_path = tmp_path / "pipeline" / "strategy" / "lena" / "content_packets" / DATE / f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
    packet_path.unlink()
    with pytest.raises(SystemExit, match="missing_artifact"):
        handoff.build_handoff(DATE)


def test_packet_outfit_or_environment_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _, _, _, packet_path, _ = _build_fixture_tree(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["environment_id"] = "env_wrong"
    _write_json(packet_path, packet)
    with pytest.raises(SystemExit, match="packet_environment_mismatch"):
        handoff.build_handoff(DATE)
