from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.lena_higgsfield_generation_approval_v1 as approval_mod
import tools.lena_record_higgsfield_generation_approval_v1 as record_tool
from tools.lena_higgsfield_generation_approval_v1 import confirmation_phrase

DATE = "2026-07-14"
SLOT_ID = "readypack0709-pack003-08-photo-approval-test"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"


def _patch_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        approval_mod, "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(record_tool, "ROOT", tmp_path)


def _handoff_repo_path() -> str:
    return f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_live_image_handoff_{DATE}.json"


def _valid_handoff_report(*, prompt_sha: str) -> dict:
    handoff_repo_path = _handoff_repo_path()
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
        "expected_handoff_artifact_path": handoff_repo_path,
        "selected_prompt_input": {"prompt_sha256": prompt_sha},
        "selected_prompt_input_artifact_sha256": "a" * 64,
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
        },
    }


def _write_handoff(tmp_path: Path, *, prompt_sha: str = "b" * 64) -> Path:
    handoff_path = tmp_path / _handoff_repo_path()
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        json.dumps(_valid_handoff_report(prompt_sha=prompt_sha), indent=2), encoding="utf-8"
    )
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
