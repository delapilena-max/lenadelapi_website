from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from pipeline.video import lena_video_creative_generation_v1 as video_gen


def _spec(video_id: str, date: str = "2026-08-04", slot: str = "morning", seed: str | None = None) -> dict:
    return video_gen.build_provisional_video_json(
        video_id=video_id,
        governed_date=date,
        daily_slot=slot,
        user_seed=seed,
        current_video_policy={
            "duration_seconds": 8,
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "audio_enabled": True,
        },
    )


def test_two_different_video_ids_produce_different_creative_json() -> None:
    first = _spec("lena-video-001", seed="night market dessert choice")
    second = _spec("lena-video-002", seed="night market dessert choice")

    assert first["video_id"] != second["video_id"]
    assert video_gen.sha256_json(first) != video_gen.sha256_json(second)


def test_different_concepts_produce_different_compiled_prompts() -> None:
    launch = video_gen.compile_provider_request(_spec("spacex-launch-001", seed="SpaceX coastal launch"))
    balcony = video_gen.compile_provider_request(_spec("rain-balcony-001", seed="rainy balcony reset"))

    assert launch["prompt_sha256"] != balcony["prompt_sha256"]
    assert "SpaceX" in launch["prompt_text"]
    assert "rain" in balcony["prompt_text"].lower()


def test_different_dates_produce_separate_production_artifacts(tmp_path: Path) -> None:
    day_one = _spec("date-separated-video", date="2026-08-04", seed="rainy balcony reset")
    day_two = _spec("date-separated-video", date="2026-08-05", seed="rainy balcony reset")

    paths_one = video_gen.production_artifact_paths(tmp_path, day_one)
    paths_two = video_gen.production_artifact_paths(tmp_path, day_two)

    assert "2026-08-04" in paths_one["creative_json"]
    assert "2026-08-05" in paths_two["creative_json"]
    assert paths_one["creative_json"] != paths_two["creative_json"]


def test_prior_compiled_prompt_cannot_authorize_new_video_create() -> None:
    original_spec = _spec("spacex-pilot-001", seed="SpaceX coastal launch")
    original_request = video_gen.compile_provider_request(original_spec)
    prior_attempt = video_gen.build_attempt_artifact(
        spec=original_spec,
        compiled_request=original_request,
        attempt_number=1,
    )

    new_spec = _spec("spacex-production-002", date="2026-08-05", seed="SpaceX coastal launch")
    reused_request = dict(original_request)
    reused_request["video_id"] = new_spec["video_id"]

    with pytest.raises(video_gen.LenaVideoCreativeError) as excinfo:
        video_gen.validate_prompt_reuse(
            prior_attempt=prior_attempt,
            proposed_spec=new_spec,
            proposed_request=reused_request,
            operation="new_provider_create",
        )
    assert excinfo.value.code == "prompt_reuse_blocked"


def test_qa_rejected_attempt_requires_new_attempt_json_and_prompt() -> None:
    original_spec = _spec("qa-rejected-video", seed="SpaceX coastal launch")
    original_request = video_gen.compile_provider_request(original_spec)
    rejected_attempt = video_gen.build_attempt_artifact(
        spec=original_spec,
        compiled_request=original_request,
        attempt_number=1,
    )
    rejected_attempt["qa_result"] = "qa_rejected"
    rejected_attempt["provider_job_id"] = "provider-job-1"

    with pytest.raises(video_gen.LenaVideoCreativeError) as excinfo:
        video_gen.build_attempt_artifact(
            spec=original_spec,
            compiled_request=original_request,
            attempt_number=2,
            superseded_attempt=rejected_attempt,
            previous_qa_findings=["pointing direction failed"],
            exact_creative_changes=[],
        )
    assert excinfo.value.code == "qa_rejected_attempt_prompt_reuse_blocked"

    repaired_spec = _spec("qa-rejected-video", seed="rainy balcony reset")
    repaired_request = video_gen.compile_provider_request(repaired_spec)
    repaired_attempt = video_gen.build_attempt_artifact(
        spec=repaired_spec,
        compiled_request=repaired_request,
        attempt_number=2,
        superseded_attempt=rejected_attempt,
        previous_qa_findings=["pointing direction failed"],
        exact_creative_changes=["changed concept to remove fragile pointing geometry"],
    )
    assert repaired_attempt["superseded_attempt_id"] == rejected_attempt["attempt_id"]
    assert repaired_attempt["new_prompt_sha256"] != rejected_attempt["new_prompt_sha256"]


def test_same_job_reconciliation_preserves_original_prompt() -> None:
    spec = _spec("same-job-video", seed="night market dessert choice")
    request = video_gen.compile_provider_request(spec)
    attempt = video_gen.build_attempt_artifact(spec=spec, compiled_request=request, attempt_number=1)
    attempt["provider_job_id"] = "provider-job-1"

    result = video_gen.validate_prompt_reuse(
        prior_attempt=attempt,
        proposed_spec=spec,
        proposed_request=request,
        operation="same_ambiguous_submission_reconciliation",
    )

    assert result["ok"] is True
    assert request["prompt_sha256"] == attempt["new_prompt_sha256"]


def test_deterministic_recompile_of_same_attempt_is_byte_identical() -> None:
    spec = _spec("deterministic-video", seed="rainy balcony reset")

    first = video_gen.compile_provider_request(spec, attempt_id="deterministic-video-attempt-001")
    second = video_gen.compile_provider_request(json.loads(json.dumps(spec)), attempt_id="deterministic-video-attempt-001")

    assert video_gen.canonical_json_bytes(first) == video_gen.canonical_json_bytes(second)
    assert first["prompt_text"].encode("utf-8") == second["prompt_text"].encode("utf-8")


def test_daily_novelty_rules_reject_repeated_environment_gesture_and_hook() -> None:
    candidate = _spec("novelty-video", seed="night market dessert choice")
    history = [
        {
            **candidate,
            "video_id": "previous-video",
        }
    ]

    result = video_gen.run_novelty_governor(candidate, history)

    assert result["ok"] is False
    assert "consecutive_reuse:environment" in result["rejection_reasons"]
    assert "consecutive_reuse:principal_gesture" in result["rejection_reasons"]
    assert "consecutive_reuse:hook_structure" in result["rejection_reasons"]


def test_static_lena_identity_remains_stable_across_different_prompts() -> None:
    first = video_gen.compile_provider_request(_spec("identity-video-1", seed="night market dessert choice"))
    second = video_gen.compile_provider_request(_spec("identity-video-2", seed="rainy balcony reset"))

    assert first["prompt_text"].startswith(video_gen.LENA_ELEMENT_TOKEN)
    assert second["prompt_text"].startswith(video_gen.LENA_ELEMENT_TOKEN)
    assert video_gen.STATIC_IDENTITY_LINE in first["prompt_text"]
    assert video_gen.STATIC_IDENTITY_LINE in second["prompt_text"]
    assert first["lena_character_element_uuid"] == second["lena_character_element_uuid"]


def test_no_provider_or_network_calls_occur(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _blocked_socket(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("network access is forbidden in this offline generator")

    monkeypatch.setattr(socket, "socket", _blocked_socket)
    spec = _spec("offline-only-video", seed="rainy balcony reset")
    written = video_gen.write_video_package(tmp_path, spec)

    assert Path(written["paths"]["creative_json"]).is_file()
    compiled = json.loads(Path(written["paths"]["compiled_request"]).read_text(encoding="utf-8"))
    assert compiled["provider_call_authorized"] is False
    assert compiled["queue_authorized"] is False
    assert compiled["publication_authorized"] is False


def test_three_offline_examples_have_distinct_prompt_hashes() -> None:
    examples = [
        video_gen.compile_provider_request(_spec("example-01-spacex", seed="SpaceX coastal launch")),
        video_gen.compile_provider_request(_spec("example-02-market", seed="night market dessert choice")),
        video_gen.compile_provider_request(_spec("example-03-balcony", seed="rainy balcony reset")),
    ]
    hashes = {item["prompt_sha256"] for item in examples}
    assert len(hashes) == 3
