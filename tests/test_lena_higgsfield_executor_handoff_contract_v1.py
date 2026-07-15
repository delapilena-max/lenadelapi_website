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
SLOT_ID = "lenagate2026071325ca9e1d-pack000-01-photo"
RECIPE_ID = "hcr_006"
HANDOFF_NAME = f"lena_next_live_image_handoff_{DATE}.json"
HANDOFF_MD_NAME = f"lena_next_live_image_handoff_{DATE}.md"
EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
LEGACY_DRY_RUN_COMMAND = f"python {EXECUTOR_PATH} --date {DATE} --slot-id {SLOT_ID}"
HANDOFF_COMMAND = f"python {EXECUTOR_PATH} --handoff-artifact pipeline/strategy/lena/next_actions/{DATE}/{HANDOFF_NAME}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_roots(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor, "ROOT", tmp_root)
    monkeypatch.setattr(handoff_builder, "ROOT", tmp_root)
    monkeypatch.setattr(handoff_builder, "NEXT_ACTIONS", tmp_root / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(
        handoff_builder,
        "PRE_GENERATION_CANDIDATES",
        tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
    )
    monkeypatch.setattr(approval_mod, "ROOT", tmp_root)
    monkeypatch.setattr(
        approval_mod, "DEFAULT_APPROVAL_ROOT",
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
    follow_up = {
        "current": "no_follow_up_required",
        "usable_but_incomplete": "complete_missing_metrics_or_refresh_learning",
        "stale_unresolved": "refresh_or_resolve_stale_unresolved_posts",
        "manual_or_future_capability_required": "manual_or_future_capability_resolution_required",
    }.get(status, "rebuild_and_pass_an_explicit_learning_artifact")
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
        "learning_published_post_count": 3,
        "learning_pending_metrics_count": 1,
        "learning_stale_pending_metrics_count": 1,
        "learning_resolution_state_summary": _learning_payload(status)["metrics_resolution_summary"],
        "learning_required_follow_up_action": follow_up,
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
            }
        ],
    }


def _candidate_payload(prompt_sha: str, command: str, lane: str) -> dict:
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
        "lane": lane,
        "lighting_text": "warm venue spill light mixed with city-night ambient light, realistic highlight rolloff, slight low-light grain",
        "narrative_roles": ["anticipation", "experience", "payoff"],
        "payoff_claimed": False,
        "payoff_eligible": True,
        "pose": "hair_touch_confident_gaze",
        "pose_body_language_id": "pose_p017",
        "primary_pillar": "beautiful_trouble",
        "prompt_sha256": prompt_sha,
        "ranking_evidence": {"identity_consistency": "passed canonical Soul identity hard gate"},
        "recipe_binding": "strategy compatibility",
        "recipe_id": RECIPE_ID,
        "scene_identity_field": "lane",
        "slot_id": SLOT_ID,
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


def _build_packet_fixture(tmp_root: Path, real_source: dict, monkeypatch: pytest.MonkeyPatch) -> Path:
    _patch_roots(tmp_root, monkeypatch)
    next_actions = tmp_root / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    prompt_dir = tmp_root / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    candidate_path = prompt_dir / "lena_pre_generation_candidate_25ca9e1d_128799286987.json"
    prompt = real_source["image"]["image_prompt"]
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    _write_json(learning_path, _learning_payload())
    _write_json(recommendation_path, _recommendation_payload(learning_path))
    _write_json(queue_path, _queue_payload())
    _write_json(candidate_path, _candidate_payload(prompt_sha, LEGACY_DRY_RUN_COMMAND, real_source["image"]["lane"]))

    packet = handoff_builder.build_handoff(DATE)
    packet_path, _ = handoff_builder.save_handoff(packet, DATE)
    assert packet_path.is_file()
    return packet_path


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
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
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
    assert "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===" in stdout


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda packet, _packet_path, _real_source: packet.__setitem__("execution_owner", "someone_else"), "handoff_execution_owner_mismatch"),
        (lambda packet, _packet_path, _real_source: packet.__setitem__("provider", "other"), "handoff_provider_mismatch"),
        (lambda packet, _packet_path, _real_source: packet.__setitem__("executor_type", "other"), "handoff_executor_type_mismatch"),
        (lambda packet, _packet_path, _real_source: packet.__setitem__("generation_performed", True), "handoff_generation_performed"),
        (lambda packet, _packet_path, _real_source: packet.__setitem__("publish_authorized", True), "handoff_publish_authorized"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"].__setitem__("negative_prompt_enabled", True), "handoff_negative_prompt_enabled"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"].__setitem__("model", "bad_model"), "handoff_model_mismatch"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"].__setitem__("aspect_ratio", "1:1"), "handoff_aspect_mismatch"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"]["soul_metadata"].__setitem__("name", "Not Lena"), "handoff_soul_name_mismatch"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"]["soul_metadata"].__setitem__("custom_reference_id", "wrong"), "handoff_soul_reference_mismatch"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"]["soul_metadata"].__setitem__("identity_is_prompt_instruction", True), "handoff_soul_prompt_instruction_invalid"),
        (lambda packet, _packet_path, _real_source: packet["selected_prompt_input"].__setitem__("prompt_sha256", "0" * 64), "handoff_expected_prompt_sha_missing_or_mismatch"),
        (lambda packet, _packet_path, _real_source: packet["selected_prompt_input"].pop("prompt_sha256", None), "handoff_expected_prompt_sha_missing_or_mismatch"),
        (lambda packet, _packet_path, _real_source: packet["structured_executor_inputs"].__setitem__("date", "2026-07-12"), "handoff_date_mismatch"),
    ],
)
def test_handoff_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutator,
    expected_code: str,
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    mutator(packet, packet_path, real_source)
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "[ABORT]" in stdout
    assert expected_code in stdout


def test_prompt_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    altered = copy.deepcopy(real_source)
    altered["image"]["image_prompt"] = altered["image"]["image_prompt"] + " drift"
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: altered)
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "handoff_prompt_sha_mismatch" in stdout


def test_source_artifact_sha_drift_rejects_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    queue_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_autonomous_generation_queue_dryrun_{DATE}.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue["queue_slots"][0]["priority_score"] = 999
    _write_json(queue_path, queue)
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path)])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "handoff_queue_sha_mismatch" in stdout


def test_handoff_live_rejected_without_separate_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(executor, "run_live", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live provider path must not be reached")))
    monkeypatch.setattr(sys, "argv", ["executor", "--handoff-artifact", str(packet_path), "--live"])

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert ("live_execution_authorized" in stdout) or ("not authorized" in stdout)
    assert "=== Higgsfield Lena executor -- HANDOFF DRY RUN (no provider/network call) ===" in stdout


def test_date_slot_dry_run_remains_compatible(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(sys, "argv", ["executor", "--date", DATE, "--slot-id", SLOT_ID])

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===" in stdout
    assert "provider argv" in stdout


def test_retry_decision_path_remains_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    fake_retry_artifact = tmp_path / "retry.json"
    fake_retry_artifact.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        executor,
        "_load_retry_decision_source",
        lambda path: (DATE, SLOT_ID, copy.deepcopy(real_source), Path(path)),
    )
    monkeypatch.setattr(sys, "argv", ["executor", "--retry-decision-artifact", str(fake_retry_artifact)])

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===" in stdout
    assert "provider argv" in stdout


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
    stdout = capsys.readouterr().out
    assert "--approval-artifact requires --handoff-artifact" in stdout


def test_dry_run_reports_valid_approval_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path)],
    )

    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield generation approval -- validation (no consumption) ===" in stdout
    assert "operator_id              : nicolas" in stdout
    assert "is_expired               : False" in stdout
    assert "authorized_attempts      : 1" in stdout
    assert "upload_authorized        : False" in stdout
    assert "publish_authorized       : False" in stdout
    assert "approval-handoff binding : confirmed exact match to supplied --handoff-artifact" in stdout


def test_live_blocked_with_consumption_not_implemented_even_with_valid_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(
        executor, "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live provider path must not be reached")),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path), "--live"],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "approval_consumption_contract_not_implemented" in stdout
    assert "=== Higgsfield generation approval -- validation (no consumption) ===" in stdout


def test_invalid_approval_reported_and_blocks_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["operator_id"] = "not_nicolas"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path)],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "approval validation failed" in stdout
    assert "approval_operator_mismatch" in stdout


def test_invalid_approval_also_blocks_live_without_generic_consumption_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
    approval_path = _build_approval_fixture(packet_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["operator_id"] = "not_nicolas"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    monkeypatch.setattr(executor, "resolve_prompt_source", lambda date, slot: copy.deepcopy(real_source))
    monkeypatch.setattr(
        executor, "run_live",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live provider path must not be reached")),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["executor", "--handoff-artifact", str(packet_path), "--approval-artifact", str(approval_path), "--live"],
    )

    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "approval_operator_mismatch" in stdout


def test_handoff_packet_paths_remain_repo_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_source = executor.resolve_prompt_source(DATE, SLOT_ID)
    packet_path = _build_packet_fixture(tmp_path, real_source, monkeypatch)
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
