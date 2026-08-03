from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.voice.lena_elevenlabs_voice_contract_v1 import (
    VoiceContractError,
    build_video_voice_manifest,
    canonical_voice_profile,
    validate_voice_profile,
)


def _video_spec() -> dict:
    return {
        "schema_version": "lena_video_prompt_v1",
        "slot_id": "lena-test-reel",
        "character_id": "lena",
        "voice": {
            "provider": "elevenlabs",
            "profile": "lena_elevenlabs_voice_contract_v1",
            "audio_first_required": True,
            "timestamps_required": True,
        },
        "shots": [
            {
                "shot_id": "shot_01",
                "duration_seconds": 4,
                "dialogue_segment": "I almost returned this until I styled it like this.",
            },
            {
                "shot_id": "shot_02",
                "duration_seconds": 4,
                "dialogue_segment": "The jacket needed a cleaner shape underneath.",
            },
        ],
        "generation": {"generate_audio_before_video": True},
    }


def test_canonical_profile_is_environment_bound_and_audio_first() -> None:
    profile = validate_voice_profile(canonical_voice_profile())
    assert profile["provider"] == "elevenlabs"
    assert profile["voice_id_env"] == "ELEVENLABS_LENA_VOICE_ID"
    assert profile["api_key_env"] == "ELEVENLABS_API_KEY"
    assert profile["continuity"]["audio_first_required"] is True
    assert profile["continuity"]["timestamps_required"] is True


def test_manifest_compiles_one_deterministic_packet_per_shot() -> None:
    first = build_video_voice_manifest(_video_spec())
    second = build_video_voice_manifest(_video_spec())
    assert first == second
    assert first["voice_packet_count"] == 2
    assert [item["shot_id"] for item in first["voice_packets"]] == ["shot_01", "shot_02"]
    assert all(item["generation_order"] == "audio_before_video" for item in first["voice_packets"])
    assert all(len(item["request_sha256"]) == 64 for item in first["voice_packets"])


def test_dialogue_timing_budget_fails_closed() -> None:
    spec = _video_spec()
    spec["shots"][0]["duration_seconds"] = 1
    spec["shots"][0]["dialogue_segment"] = "This dialogue is deliberately much too long for a one second generated shot."
    with pytest.raises(VoiceContractError) as error:
        build_video_voice_manifest(spec)
    assert error.value.code == "dialogue_too_long"


def test_voice_continuity_cannot_be_weakened() -> None:
    profile = canonical_voice_profile()
    profile["continuity"]["timestamps_required"] = False
    with pytest.raises(VoiceContractError) as error:
        validate_voice_profile(profile)
    assert error.value.code == "voice_continuity_weakened"


def test_example_video_json_compiles() -> None:
    root = Path(__file__).resolve().parents[1]
    example = json.loads((root / "pipeline/examples/lena_video_prompt_v1.example.json").read_text(encoding="utf-8"))
    manifest = build_video_voice_manifest(example)
    assert manifest["voice_packet_count"] == 3
