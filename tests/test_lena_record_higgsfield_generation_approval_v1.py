from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

import tools.lena_higgsfield_generation_approval_v1 as approval_mod
import tools.lena_record_higgsfield_generation_approval_v1 as record_tool
import tools.strategy.lena_reconciliation_contract_v1 as reconciliation_contract
from tests.fixtures import lena_pose_provenance as pose_fixture
from tools.lena_higgsfield_generation_approval_v1 import confirmation_phrase

DATE = "2026-07-14"
SLOT_ID = "readypack0709-pack003-08-photo-approval-test"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"


def _selected_candidate_repo_path() -> str:
    return f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/lena_pre_generation_candidate_selected.json"


def _selected_candidate_payload() -> dict:
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "authority_commit": "a" * 40,
        "candidate_status": "selected",
        "generated_at_utc": "2026-07-14T12:00:00+00:00",
        "candidate": {
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_004",
            "slot_id": SLOT_ID,
            "recipe_id": "hcr_011",
            "prompt_sha256": "b" * 64,
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
        },
    }


def _selected_candidate_sha() -> str:
    return hashlib.sha256(
        json.dumps(_selected_candidate_payload(), indent=2).replace("\n", os.linesep).encode("utf-8")
    ).hexdigest()


def _patch_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        approval_mod, "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_path)
    monkeypatch.setattr(record_tool, "ROOT", tmp_path)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _handoff_repo_path() -> str:
    return f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"


def _valid_handoff_report(*, prompt_sha: str) -> dict:
    handoff_repo_path = _handoff_repo_path()
    selected_candidate_repo_path = _selected_candidate_repo_path()
    selected_candidate_sha = _selected_candidate_sha()
    pose_binding = pose_fixture.static_pose_provenance(
        candidate_path=selected_candidate_repo_path,
        candidate_sha256=selected_candidate_sha,
    )
    pose_bound_packet_sha = "4" * 64
    return {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "created_at": "2026-07-14T12:00:00+00:00",
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
        "selected_slot_id": SLOT_ID,
        "selected_recipe_id": "hcr_011",
        "expected_handoff_artifact_path": handoff_repo_path,
        "source_selected_candidate_artifact_path": selected_candidate_repo_path,
        "source_selected_candidate_artifact_sha256": selected_candidate_sha,
        "selected_candidate": {
            "artifact_path": selected_candidate_repo_path,
            "artifact_sha256": selected_candidate_sha,
            "candidate_id": f"{SLOT_ID}::hcr_011::cbn_004",
            "slot_id": SLOT_ID,
            "recipe_id": "hcr_011",
            "prompt_sha256": prompt_sha,
            "schema_version": "lena_pre_generation_candidate_gate_v1",
            "candidate_status": "selected",
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
        },
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha,
        "selected_prompt_input_artifact_sha256": "a" * 64,
        "selected_prompt_input": {
            "prompt_sha256": prompt_sha,
            "selected_candidate_artifact_path": selected_candidate_repo_path,
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha,
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
            "slot_id": SLOT_ID,
            "handoff_artifact_path": handoff_repo_path,
            "soul_metadata": {
                "name": "Lena",
                "type": "Soul 2.0",
                "custom_reference_id": CUSTOM_REFERENCE_ID,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_sha256": prompt_sha,
            "selected_candidate_artifact_path": selected_candidate_repo_path,
            "selected_candidate_artifact_sha256": selected_candidate_sha,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha,
        },
    }


def _write_handoff(tmp_path: Path, *, prompt_sha: str = "b" * 64) -> Path:
    handoff_path = tmp_path / _handoff_repo_path()
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    selected_candidate_path = tmp_path / _selected_candidate_repo_path()
    selected_candidate_path.parent.mkdir(parents=True, exist_ok=True)
    selected_candidate_path.write_text(
        json.dumps(_selected_candidate_payload(), indent=2), encoding="utf-8"
    )
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
    }
    _write_json(queue_path, queue_report)
    recommendation_path.write_text(json.dumps(recommendation_report, indent=2), encoding="utf-8")
    reconciliation_report = {
        "report_type": "lena_generation_reconciliation",
        "schema_version": "lena_generation_reconciliation_v1",
        "date": DATE,
        "generated_at": "2026-07-14T12:00:00+00:00",
        "source_revision": "2ed48fd2",
        "source_revision_commit": "2ed48fd29215ffc499b64f15255f6c4038bf484a",
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
                "source_artifact_path": _selected_candidate_repo_path(),
                "source_artifact_sha256": _selected_candidate_sha(),
            },
        },
        "learning_status": "current",
        "recommendation_recipe_id": "hcr_011",
        "recommendation_outfit_id": "wc_p059",
        "recommendation_environment_id": "env_p001",
        "recommendation_action_type": "collect_first_controlled_proof",
        "selected_candidate_id": f"{SLOT_ID}::hcr_011::cbn_004",
        "selected_candidate_recipe_id": "hcr_011",
        "selected_candidate_slot_id": SLOT_ID,
        "selected_candidate_hook_id": "cbn_004",
        "selected_candidate_prompt_sha256": prompt_sha,
        "divergence_status": "aligned",
        "resolution_policy": "selected_candidate_authoritative",
        "reconciliation_status": "reconciled",
        "operator_review_required": False,
        "final_reconciled_candidate_id": f"{SLOT_ID}::hcr_011::cbn_004",
        "final_reconciled_candidate_recipe_id": "hcr_011",
        "final_reconciled_candidate_slot_id": SLOT_ID,
        "final_reconciled_candidate_hook_id": "cbn_004",
        "final_reconciled_candidate_prompt_sha256": prompt_sha,
        "final_reconciled_candidate_artifact_path": _selected_candidate_repo_path(),
        "final_reconciled_candidate_artifact_sha256": _selected_candidate_sha(),
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
    handoff_report = _valid_handoff_report(prompt_sha=prompt_sha)
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
    handoff_path.write_text(json.dumps(handoff_report, indent=2), encoding="utf-8")
    return handoff_path


def _run(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["record_tool", *args])
    return record_tool.main()


def test_recording_succeeds_and_writes_expected_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)

    code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "nicolas",
        "--confirm", confirmation_phrase(SLOT_ID),
    )
    assert code == 0

    expected_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_approval.json"
    assert expected_path.is_file()
    record = json.loads(expected_path.read_text(encoding="utf-8"))
    assert record["operator_id"] == "nicolas"
    assert record["slot_id"] == SLOT_ID
    assert record["authorized_attempts"] == 1
    assert record["upload_authorized"] is False
    assert record["queue_promotion_authorized"] is False
    assert record["publish_authorized"] is False
    assert record["analytics_mutation_authorized"] is False

    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] is True
    assert stdout["files_written_this_run"] == [str(expected_path)]


def test_recording_refuses_wrong_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)

    code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "not_nicolas",
        "--confirm", confirmation_phrase(SLOT_ID),
    )
    assert code == 1
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] is False
    assert stdout["error_code"] == "approval_operator_mismatch"
    assert stdout["files_written_this_run"] == []

    approvals_dir = tmp_path / "pipeline" / "approvals"
    assert not approvals_dir.exists()


def test_recording_refuses_wrong_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)

    code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "nicolas",
        "--confirm", "yes I approve",
    )
    assert code == 1
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["error_code"] == "approval_confirmation_mismatch"
    assert stdout["files_written_this_run"] == []


def test_recording_refuses_invalid_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = tmp_path / _handoff_repo_path()
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps({"report_type": "wrong_type"}), encoding="utf-8")

    code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "nicolas",
        "--confirm", confirmation_phrase(SLOT_ID),
    )
    assert code == 1
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["error_code"] == "handoff_report_type_mismatch"
    assert stdout["files_written_this_run"] == []
    assert not (tmp_path / "pipeline" / "approvals").exists()


def test_recording_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)

    first_code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "nicolas",
        "--confirm", confirmation_phrase(SLOT_ID),
    )
    capsys.readouterr()
    assert first_code == 0

    second_code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "nicolas",
        "--confirm", confirmation_phrase(SLOT_ID),
    )
    assert second_code == 1
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["error_code"] == "approval_already_exists"


def test_recording_aborts_cleanly_on_missing_reconciliation_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_root(tmp_path, monkeypatch)
    handoff_path = _write_handoff(tmp_path)
    reconciliation_path = tmp_path / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE / "lena_generation_reconciliation_fixture.json"
    reconciliation_path.unlink()

    code = _run(
        monkeypatch,
        "--handoff-artifact", str(handoff_path),
        "--operator-id", "nicolas",
        "--confirm", confirmation_phrase(SLOT_ID),
    )
    assert code == 1
    captured = capsys.readouterr()
    assert f"[ABORT] missing_reconciliation_artifact: missing required artifact: {reconciliation_path}" in captured.out
    assert "Traceback" not in captured.err
    expected_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_approval.json"
    assert not expected_path.exists()


def test_recording_tool_never_imports_executor_or_provider_modules() -> None:
    source = Path(record_tool.__file__).read_text(encoding="utf-8")
    import_lines = [
        line for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined = "\n".join(import_lines).lower()
    for forbidden in (
        "higgsfield_lena_api_executor", "kling_apilena_api_executor",
        "subprocess", "urllib", "requests", "boto3",
    ):
        assert forbidden not in joined, f"forbidden import found: {forbidden}"


def test_module_never_invokes_subprocess_or_network() -> None:
    source = Path(approval_mod.__file__).read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import urllib",
        "from urllib",
        "urllib.",
        "import requests",
        "from requests",
        "requests.",
    ):
        assert forbidden not in lowered
