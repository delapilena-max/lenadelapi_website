from __future__ import annotations

import json
import re
import socket
import subprocess
import urllib.request
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from pipeline.media_properties.lena.video.artifacts import VideoArtifactStore
from pipeline.media_properties.lena.video.compiler import compile_video
from pipeline.media_properties.lena.video.contracts import (
    CHARACTER_ELEMENT_TOKEN,
    LenaVideoContractError,
    canonical_json_bytes,
    canonical_sha256,
    compilation_fingerprint,
)
from pipeline.media_properties.lena.video.validation import validate_loaded_video
from tests.lena_video_json_test_support import (
    PILOT_ROOT,
    copy_pilot,
    read_artifact,
    write_artifact,
)
from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits


def _codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def test_repeated_compilation_is_byte_equivalent_and_matches_checked_in_outputs() -> None:
    plan_a, request_a = compile_video(PILOT_ROOT)
    plan_b, request_b = compile_video(PILOT_ROOT)
    checked_plan = json.loads(
        (PILOT_ROOT / "lena_video_generation_plan_v1.json").read_text(
            encoding="utf-8"
        )
    )
    checked_request = json.loads(
        (PILOT_ROOT / "lena_higgsfield_compiled_request_v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert canonical_json_bytes(plan_a) == canonical_json_bytes(plan_b)
    assert canonical_json_bytes(request_a) == canonical_json_bytes(request_b)
    assert plan_a == checked_plan
    assert request_a == checked_request
    assert canonical_sha256(plan_a) == "a219ca9f40b2210542a2ba67828b50dd830c46b59e3813e6018eec420f794970"
    assert canonical_sha256(request_a) == "6f80fc07960ddf4a15e62157ae9b3f75e4baf9166c25ef2fdd8985a0f45fcc36"


def test_generation_plan_is_provider_neutral_and_execution_disabled() -> None:
    plan, _ = compile_video(PILOT_ROOT)
    serialized = json.dumps(plan, sort_keys=True).lower()

    for provider in ("higgsfield", "seedance", "kling", "runway", "veo", "anthropic"):
        assert re.search(rf"\b{provider}\b", serialized) is None
    assert plan["generator_version"] == "lena_video_plan_compiler_v1"
    assert plan["execution_authorized"] is False
    assert plan["attempt_authority"]["authorized_attempts"] == 0


def test_compiled_request_has_exact_identity_format_and_spend_contract() -> None:
    _, request = compile_video(PILOT_ROOT)

    assert request["character_element_token"] == CHARACTER_ELEMENT_TOKEN
    assert request["provider_arguments"]["character_element"] == CHARACTER_ELEMENT_TOKEN
    assert request["duration_ms"] == 8000
    assert request["provider_arguments"]["duration_seconds"] == 8
    assert request["resolution"] == "720p"
    assert request["aspect_ratio"] == "9:16"
    assert request["cost_ceiling_credits"] == 36
    assert request["prompt_char_count"] == len(request["exact_compiled_prompt"])
    assert request["prompt_char_budget"] == 4096
    assert request["prompt_char_count"] <= request["prompt_char_budget"]
    assert request["attempt_authority"] == {
        "authorized_attempts": 0,
        "retry_authorized": False,
        "separate_authorization_required": True,
        "credit_ceiling_applies_to_all_attempts": True,
    }
    assert request["execution_authorized"] is False
    assert request["provider_arguments"]["execution_mode"] == "disabled"


def test_prompt_contains_full_executable_timeline_and_production_authority() -> None:
    _, request = compile_video(PILOT_ROOT)
    prompt = request["exact_compiled_prompt"]

    assert prompt.startswith(CHARACTER_ELEMENT_TOKEN + "\n")
    for beat in ("[0-2s]", "[2-4s]", "[4-6s]", "[6-8s]"):
        assert beat in prompt
    for required in (
        "torso shifts three centimeters",
        "one twelve-centimeter half-step",
        "one blink",
        "with no blink",
        "fifteen centimeters",
        "five centimeters",
        "eight kilometers",
        "fully fastened jean shorts",
        "12% headroom",
        "No dialogue, voice, or lip sync",
        "[Hard constraints]",
        "safe successful launch",
    ):
        assert required in prompt
    assert len(prompt) == 3997
    assert len(prompt) <= 4096


def test_negative_prompt_contains_quality_and_safety_rejections() -> None:
    _, request = compile_video(PILOT_ROOT)
    negative = request["exact_negative_prompt"].lower()

    for term in (
        "identity drift",
        "malformed hands",
        "reference-image clothing",
        "static posing",
        "frozen expression",
        "impossible camera orbit",
        "rocket too close",
        "explosion",
        "restricted launch pad access",
        "spacex sponsorship",
        "accidental sexualized framing",
        "provider demo aesthetic",
    ):
        assert term in negative


def test_fingerprint_excludes_only_declared_compilation_metadata() -> None:
    _, request = compile_video(PILOT_ROOT)
    changed_timestamp = deepcopy(request)
    changed_timestamp["compilation_timestamp"] = "2026-08-02T22:59:59Z"
    changed_model = deepcopy(request)
    changed_model["model"] = "different_model"

    assert compilation_fingerprint(request) == request[
        "deterministic_compilation_fingerprint"
    ]
    assert compilation_fingerprint(changed_timestamp) == compilation_fingerprint(request)
    assert compilation_fingerprint(changed_model) != compilation_fingerprint(request)


def test_prompt_budget_matches_shared_higgsfield_execution_policy() -> None:
    _, request = compile_video(PILOT_ROOT)

    assert request["prompt_char_budget"] == (
        prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    )
    assert request["prompt_char_budget"] - request["prompt_char_count"] == 99
    assert (
        request["prompt_char_budget"] - request["prompt_char_count"]
        >= prompt_limits.RETRY_PROMPT_HEADROOM_WARNING_BELOW
    )


def test_over_budget_authored_prompt_fails_before_output(
    tmp_path: Path,
) -> None:
    root = copy_pilot(tmp_path)
    spec = read_artifact(root, "lena_video_spec_v1")
    spec["provider_prompt_cue"] += " Additional visible production cue." * 4
    write_artifact(root, "lena_video_spec_v1", spec)
    spec_sha = canonical_sha256(spec)
    for artifact_type in (
        "lena_video_hpe_v1",
        "lena_video_environment_v1",
        "lena_video_wardrobe_v1",
        "lena_video_camera_v1",
        "lena_video_audio_plan_v1",
    ):
        value = read_artifact(root, artifact_type)
        value["upstream_artifacts"][0]["sha256"] = spec_sha
        write_artifact(root, artifact_type, value)

    with pytest.raises(LenaVideoContractError) as captured:
        compile_video(root)

    assert getattr(captured.value, "issues")[0].code == (
        "compiled_prompt_execution_policy_exceeded"
    )


def test_manually_rebound_plan_still_fails_exact_deterministic_comparison() -> None:
    artifacts = VideoArtifactStore(PILOT_ROOT).load_all()
    original = artifacts["lena_video_generation_plan_v1"]
    data = deepcopy(original.data)
    data["expected_output"] = "a manually altered but schema-valid output description"
    artifacts["lena_video_generation_plan_v1"] = replace(
        original,
        data=data,
        sha256=canonical_sha256(data),
    )

    assert "generation_plan_not_deterministic_output" in _codes(
        validate_loaded_video(artifacts)
    )


def test_recomputed_self_fingerprint_cannot_authorize_tampered_request() -> None:
    artifacts = VideoArtifactStore(PILOT_ROOT).load_all()
    original = artifacts["lena_higgsfield_compiled_request_v1"]
    data = deepcopy(original.data)
    data["exact_compiled_prompt"] += "\nManual ungoverned prompt addition."
    data["provider_arguments"]["prompt"] = data["exact_compiled_prompt"]
    data["deterministic_compilation_fingerprint"] = compilation_fingerprint(data)
    artifacts["lena_higgsfield_compiled_request_v1"] = replace(
        original,
        data=data,
        sha256=canonical_sha256(data),
    )

    codes = _codes(validate_loaded_video(artifacts))
    assert "compiled_fingerprint_mismatch" not in codes
    assert "compiled_request_not_deterministic_output" in codes


def test_compile_performs_zero_network_provider_or_process_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("external activity is forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)

    plan, request = compile_video(PILOT_ROOT)

    assert plan["execution_authorized"] is False
    assert request["execution_authorized"] is False
