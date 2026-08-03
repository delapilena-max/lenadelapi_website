from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

SCHEMA_VERSION = "lena_elevenlabs_voice_contract_v1"
PROVIDER = "elevenlabs"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_SETTINGS = {
    "stability": 0.55,
    "similarity_boost": 0.85,
    "style": 0.25,
    "use_speaker_boost": True,
    "speed": 1.0,
}
ALLOWED_MODELS = {
    "eleven_multilingual_v2",
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
}
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class VoiceContractError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise VoiceContractError(code, detail)


def _number(value: Any, path: str, minimum: float, maximum: float) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), "invalid_voice_setting", f"{path} must be numeric")
    numeric = float(value)
    _require(minimum <= numeric <= maximum, "invalid_voice_setting", f"{path} must be between {minimum} and {maximum}")
    return numeric


def canonical_voice_profile() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "character_id": "lena",
        "voice_id_env": "ELEVENLABS_LENA_VOICE_ID",
        "api_key_env": "ELEVENLABS_API_KEY",
        "model_id": DEFAULT_MODEL_ID,
        "output_format": DEFAULT_OUTPUT_FORMAT,
        "voice_settings": deepcopy(DEFAULT_SETTINGS),
        "continuity": {
            "audio_first_required": True,
            "same_voice_id_across_shots": True,
            "timestamps_required": True,
            "lip_sync_source": "elevenlabs_alignment",
        },
    }


def validate_voice_profile(profile: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(profile, dict), "invalid_profile", "voice profile must be a JSON object")
    _require(profile.get("schema_version") == SCHEMA_VERSION, "unknown_schema_version", "unexpected voice profile schema_version")
    _require(profile.get("provider") == PROVIDER, "unsupported_provider", "Lena's governed voice provider must be elevenlabs")
    _require(profile.get("character_id") == "lena", "wrong_character", "voice profile must be bound to Lena")
    for field in ("voice_id_env", "api_key_env"):
        value = profile.get(field)
        _require(isinstance(value, str) and bool(_ENV_NAME_RE.fullmatch(value)), "invalid_environment_binding", f"{field} must name an environment variable")
    _require(profile.get("model_id") in ALLOWED_MODELS, "unsupported_model", "unsupported ElevenLabs model_id")
    output_format = profile.get("output_format")
    _require(isinstance(output_format, str) and output_format.startswith(("mp3_", "pcm_", "ulaw_")), "invalid_output_format", "unsupported ElevenLabs output format")

    settings = profile.get("voice_settings")
    _require(isinstance(settings, dict), "invalid_voice_settings", "voice_settings must be a JSON object")
    normalized = deepcopy(profile)
    normalized_settings = normalized["voice_settings"]
    normalized_settings["stability"] = _number(settings.get("stability"), "voice_settings.stability", 0.0, 1.0)
    normalized_settings["similarity_boost"] = _number(settings.get("similarity_boost"), "voice_settings.similarity_boost", 0.0, 1.0)
    normalized_settings["style"] = _number(settings.get("style"), "voice_settings.style", 0.0, 1.0)
    normalized_settings["speed"] = _number(settings.get("speed"), "voice_settings.speed", 0.7, 1.2)
    _require(isinstance(settings.get("use_speaker_boost"), bool), "invalid_voice_setting", "voice_settings.use_speaker_boost must be boolean")

    continuity = profile.get("continuity")
    _require(isinstance(continuity, dict), "invalid_continuity", "continuity must be a JSON object")
    for field in ("audio_first_required", "same_voice_id_across_shots", "timestamps_required"):
        _require(continuity.get(field) is True, "voice_continuity_weakened", f"continuity.{field} must remain true")
    _require(continuity.get("lip_sync_source") == "elevenlabs_alignment", "invalid_lip_sync_source", "lip sync must use ElevenLabs alignment evidence")
    return normalized


def build_voice_packet(video_spec: dict[str, Any], shot: dict[str, Any], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    validated_profile = validate_voice_profile(profile or canonical_voice_profile())
    _require(isinstance(video_spec, dict), "invalid_video_spec", "video_spec must be a JSON object")
    _require(video_spec.get("schema_version") == "lena_video_prompt_v1", "unknown_video_schema", "video spec must use lena_video_prompt_v1")
    _require(video_spec.get("character_id") == "lena", "wrong_character", "video spec must be for Lena")
    _require(isinstance(shot, dict), "invalid_shot", "shot must be a JSON object")
    shot_id = shot.get("shot_id")
    text = shot.get("dialogue_segment")
    _require(isinstance(shot_id, str) and shot_id.strip(), "missing_shot_id", "shot_id is required")
    _require(isinstance(text, str) and text.strip(), "missing_dialogue", f"{shot_id} requires dialogue_segment")
    duration = shot.get("duration_seconds")
    _require(isinstance(duration, (int, float)) and not isinstance(duration, bool) and 1 <= float(duration) <= 20, "invalid_shot_duration", f"{shot_id}.duration_seconds must be between 1 and 20")
    max_words = max(4, int(float(duration) * 3.2))
    _require(len(text.split()) <= max_words, "dialogue_too_long", f"{shot_id} dialogue exceeds the conservative {max_words}-word timing budget")

    request_payload = {
        "text": text.strip(),
        "model_id": validated_profile["model_id"],
        "voice_settings": validated_profile["voice_settings"],
    }
    canonical = json.dumps(request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "lena_elevenlabs_voice_packet_v1",
        "slot_id": video_spec.get("slot_id"),
        "shot_id": shot_id,
        "character_id": "lena",
        "provider": PROVIDER,
        "voice_id_env": validated_profile["voice_id_env"],
        "api_key_env": validated_profile["api_key_env"],
        "output_format": validated_profile["output_format"],
        "request_payload": request_payload,
        "request_sha256": hashlib.sha256(canonical).hexdigest(),
        "expected_duration_seconds": float(duration),
        "timestamps_required": True,
        "generation_order": "audio_before_video",
    }


def build_video_voice_manifest(video_spec: dict[str, Any], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    shots = video_spec.get("shots") if isinstance(video_spec, dict) else None
    _require(isinstance(shots, list) and shots, "missing_shots", "video spec requires at least one shot")
    packets = [build_voice_packet(video_spec, shot, profile=profile) for shot in shots]
    return {
        "schema_version": "lena_elevenlabs_voice_manifest_v1",
        "slot_id": video_spec.get("slot_id"),
        "character_id": "lena",
        "provider": PROVIDER,
        "audio_first_required": True,
        "voice_packet_count": len(packets),
        "voice_packets": packets,
    }
