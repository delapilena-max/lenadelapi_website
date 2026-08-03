from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.voice.lena_elevenlabs_executor_v1 import ElevenLabsExecutionError, execute
from pipeline.voice.lena_elevenlabs_voice_contract_v1 import build_video_voice_manifest


def _write_packet(tmp_path: Path) -> Path:
    spec = {
        "schema_version": "lena_video_prompt_v1",
        "slot_id": "lena-executor-test",
        "character_id": "lena",
        "shots": [{"shot_id": "shot_01", "duration_seconds": 4, "dialogue_segment": "This is Lena speaking naturally."}],
    }
    packet = build_video_voice_manifest(spec)["voice_packets"][0]
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    return path


def test_executor_is_dry_run_by_default_and_makes_no_provider_call(tmp_path: Path) -> None:
    result = execute(_write_packet(tmp_path), tmp_path / "out")
    assert result["status"] == "dry_run_ready"
    assert result["provider_call_count"] == 0
    assert (tmp_path / "out/shot_01_voice_result.json").is_file()
    assert not (tmp_path / "out/shot_01.mp3").exists()


def test_live_executor_requires_environment_bound_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_LENA_VOICE_ID", raising=False)
    with pytest.raises(ElevenLabsExecutionError):
        execute(_write_packet(tmp_path), tmp_path / "out", live=True)


def test_executor_rejects_non_governed_packet(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({"schema_version": "unknown"}), encoding="utf-8")
    with pytest.raises(ElevenLabsExecutionError):
        execute(packet, tmp_path / "out")
