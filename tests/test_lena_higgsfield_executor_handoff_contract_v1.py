from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

import pipeline.higgsfield_lena_api_executor as executor
import tools.lena_higgsfield_generation_approval_v1 as approval_mod
import tools.strategy.lena_build_next_live_image_handoff_v1 as handoff_builder


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
    monkeypatch.setattr(approval_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        approval_mod,
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
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    content_packet_path = packets / f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
    packet_report = _content_packet_payload(prompt_text)

    _write_json(learning_path, _learning_payload())
    _write_json(recommendation_path, _recommendation_payload(learning_path))
    _write_json(queue_path, _queue_payload())
    _write_json(content_packet_path, packet_report)

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
