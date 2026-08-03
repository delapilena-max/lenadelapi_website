from __future__ import annotations

from typing import Any, Mapping

from .artifacts import SOURCE_TYPES, LoadedArtifact
from .contracts import (
    CHARACTER_ELEMENT_TOKEN,
    CHARACTER_ELEMENT_UUID,
    HIGGSFIELD_COMPILER_VERSION,
    PLAN_COMPILER_VERSION,
    compilation_fingerprint,
)


def _artifact_id(video_id: str, suffix: str) -> str:
    return f"{video_id.replace('-', '_')}_{suffix}"


def _timeline_text(hpe: Mapping[str, Any]) -> list[str]:
    return [
        (
            f"[{segment['start_ms'] // 1000}-{segment['end_ms'] // 1000}s] "
            f"{segment['provider_prompt_cue']}"
        )
        for segment in hpe["timeline"]
    ]


def _compile_prompt(sources: Mapping[str, LoadedArtifact]) -> str:
    character = sources["lena_video_character_authority_v1"].data
    spec = sources["lena_video_spec_v1"].data
    hpe = sources["lena_video_hpe_v1"].data
    environment = sources["lena_video_environment_v1"].data
    wardrobe = sources["lena_video_wardrobe_v1"].data
    camera = sources["lena_video_camera_v1"].data
    audio = sources["lena_video_audio_plan_v1"].data
    lines = [
        CHARACTER_ELEMENT_TOKEN,
        "[Format] Exactly 8 seconds, 720p portrait 9:16, one continuous premium social-video shot.",
        f"[Identity] {character['provider_prompt_cue']}",
        f"[Concept] {spec['provider_prompt_cue']}",
        f"[Environment] {environment['provider_prompt_cue']}",
        f"[Wardrobe] {wardrobe['provider_prompt_cue']}",
        f"[Camera] {camera['provider_prompt_cue']}",
        *_timeline_text(hpe),
        f"[Audio] {audio['provider_prompt_cue']}",
        f"[Hard constraints] {'; '.join(spec['hard_constraints'])}.",
    ]
    return "\n".join(lines)


def _negative_prompt(sources: Mapping[str, LoadedArtifact]) -> str:
    return "; ".join(sources["lena_video_spec_v1"].data["negative_constraints"])


def compile_generation_plan(
    sources: Mapping[str, LoadedArtifact],
) -> dict[str, Any]:
    policy = sources["lena_video_policy_v1"].data
    spec = sources["lena_video_spec_v1"].data
    hpe = sources["lena_video_hpe_v1"].data
    environment = sources["lena_video_environment_v1"].data
    wardrobe = sources["lena_video_wardrobe_v1"].data
    camera = sources["lena_video_camera_v1"].data
    audio = sources["lena_video_audio_plan_v1"].data
    created_at = max(item.data["created_at"] for item in sources.values())
    return {
        "schema_version": "lena_video_artifact_v1",
        "artifact_type": "lena_video_generation_plan_v1",
        "artifact_id": _artifact_id(spec["video_id"], "generation_plan_v1"),
        "property_id": "lena",
        "video_id": spec["video_id"],
        "governed_date": spec["governed_date"],
        "created_at": created_at,
        "generator_version": PLAN_COMPILER_VERSION,
        "upstream_artifacts": [
            {
                "artifact_id": sources[artifact_type].artifact_id,
                "sha256": sources[artifact_type].sha256,
            }
            for artifact_type in SOURCE_TYPES
        ],
        "validation_status": "validated",
        "character_element_requirement": {
            "uuid": CHARACTER_ELEMENT_UUID,
            "token": CHARACTER_ELEMENT_TOKEN,
            "direct_binding_required": True,
        },
        "duration_ms": policy["duration_ms"],
        "resolution": policy["resolution"],
        "aspect_ratio": policy["aspect_ratio"],
        "action_timeline": hpe["timeline"],
        "camera_requirements": camera["provider_neutral_requirements"],
        "environment_requirements": environment["provider_neutral_requirements"],
        "wardrobe_requirements": wardrobe["provider_neutral_requirements"],
        "sound_requirements": audio["provider_neutral_requirements"],
        "cost_ceiling_credits": policy["standard_credit_ceiling"],
        "attempt_authority": policy["attempt_authority"],
        "expected_output": "one identity-stable premium eight-second portrait video master",
        "qa_requirements": spec["qa_requirements"],
        "execution_authorized": False,
    }


def compile_higgsfield_request(
    plan: LoadedArtifact,
    sources: Mapping[str, LoadedArtifact],
) -> dict[str, Any]:
    prompt = _compile_prompt(sources)
    negative = _negative_prompt(sources)
    data = plan.data
    policy = sources["lena_video_policy_v1"].data
    request: dict[str, Any] = {
        "schema_version": "lena_video_artifact_v1",
        "artifact_type": "lena_higgsfield_compiled_request_v1",
        "artifact_id": _artifact_id(data["video_id"], "higgsfield_request_v1"),
        "property_id": "lena",
        "video_id": data["video_id"],
        "governed_date": data["governed_date"],
        "created_at": data["created_at"],
        "generator_version": HIGGSFIELD_COMPILER_VERSION,
        "upstream_artifacts": [
            {"artifact_id": plan.artifact_id, "sha256": plan.sha256}
        ],
        "source_artifacts": data["upstream_artifacts"],
        "source_plan_sha256": plan.sha256,
        "compiler_version": HIGGSFIELD_COMPILER_VERSION,
        "provider": "higgsfield",
        "model": "seedance_2_0",
        "character_element_token": CHARACTER_ELEMENT_TOKEN,
        "exact_compiled_prompt": prompt,
        "exact_negative_prompt": negative,
        "prompt_char_count": len(prompt),
        "prompt_char_budget": policy["higgsfield_prompt_execution_policy_max_chars"],
        "duration_ms": data["duration_ms"],
        "resolution": data["resolution"],
        "aspect_ratio": data["aspect_ratio"],
        "provider_arguments": {
            "character_element": CHARACTER_ELEMENT_TOKEN,
            "prompt": prompt,
            "negative_prompt": negative,
            "duration_seconds": 8,
            "resolution": data["resolution"],
            "aspect_ratio": data["aspect_ratio"],
            "enhance_prompt": False,
            "execution_mode": "disabled",
        },
        "cost_ceiling_credits": data["cost_ceiling_credits"],
        "attempt_authority": data["attempt_authority"],
        "compilation_timestamp": data["created_at"],
        "deterministic_compilation_fingerprint": "0" * 64,
        "execution_authorized": False,
    }
    request["deterministic_compilation_fingerprint"] = compilation_fingerprint(
        request
    )
    return request


__all__ = ["compile_generation_plan", "compile_higgsfield_request"]
