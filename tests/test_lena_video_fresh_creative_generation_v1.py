from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from pipeline.media_properties.lena.video import fresh_creative_generation as video_gen
from pipeline.media_properties.lena.video.artifacts import ARTIFACT_FILES, SOURCE_TYPES, VideoArtifactStore
from pipeline.media_properties.lena.video.compiler import compile_video
from pipeline.media_properties.lena.video.contracts import CHARACTER_ELEMENT_TOKEN, canonical_json_bytes, canonical_sha256
from pipeline.media_properties.lena.video.validation import validate_source_for_compilation


def _artifacts(slug: str, date: str = "2026-08-04", seed: str | None = None) -> dict[str, dict]:
    return video_gen.build_canonical_source_artifacts(
        video_slug=slug,
        governed_date=date,
        user_seed=seed,
    )


def _write_sources(tmp_path: Path, artifacts: dict[str, dict]) -> Path:
    root = tmp_path / artifacts["lena_video_spec_v1"]["video_id"]
    video_gen.write_source_artifacts(root, artifacts)
    return root


def test_two_different_video_ids_produce_different_canonical_source_json() -> None:
    first = _artifacts("example_001", seed="night market dessert choice")
    second = _artifacts("example_002", seed="night market dessert choice")

    assert first["lena_video_spec_v1"]["video_id"] != second["lena_video_spec_v1"]["video_id"]
    assert canonical_json_bytes(first["lena_video_spec_v1"]) != canonical_json_bytes(second["lena_video_spec_v1"])


def test_generated_source_artifacts_validate_through_canonical_validator() -> None:
    artifacts = _artifacts("validation_example", seed="SpaceX coastal launch")
    result = video_gen.validate_canonical_sources(artifacts)

    assert result["ok"] is True
    assert result["errors"] == []


def test_written_package_uses_canonical_file_names_and_compiler(tmp_path: Path) -> None:
    artifacts = _artifacts("spacex_launch_001", seed="SpaceX coastal launch")
    root = _write_sources(tmp_path, artifacts)
    store = VideoArtifactStore(root)
    sources = store.load_sources()
    assert validate_source_for_compilation(sources) == []
    plan, compiled = compile_video(root)

    assert plan["artifact_type"] == "lena_video_generation_plan_v1"
    assert compiled["artifact_type"] == "lena_higgsfield_compiled_request_v1"
    assert compiled["exact_compiled_prompt"].startswith(CHARACTER_ELEMENT_TOKEN)
    assert compiled["execution_authorized"] is False
    for artifact_type in SOURCE_TYPES:
        assert (root / ARTIFACT_FILES[artifact_type]).is_file()


def test_different_concepts_produce_different_canonical_compiled_prompts(tmp_path: Path) -> None:
    launch_root = _write_sources(tmp_path, _artifacts("spacex_launch_001", seed="SpaceX coastal launch"))
    balcony_root = _write_sources(tmp_path, _artifacts("rain_balcony_001", seed="rainy balcony reset"))
    _, launch = compile_video(launch_root)
    _, balcony = compile_video(balcony_root)

    assert video_gen.prompt_sha256(launch) != video_gen.prompt_sha256(balcony)
    assert "rocket" in launch["exact_compiled_prompt"].lower()
    assert "rain" in balcony["exact_compiled_prompt"].lower()


def test_different_dates_produce_separate_fixture_roots(tmp_path: Path) -> None:
    day_one = _write_sources(tmp_path / "fixtures", _artifacts("date_separated_video", date="2026-08-04", seed="rainy balcony reset"))
    day_two = _write_sources(tmp_path / "fixtures", _artifacts("date_separated_video", date="2026-08-05", seed="rainy balcony reset"))

    assert "2026-08-04" in day_one.name
    assert "2026-08-05" in day_two.name
    assert day_one != day_two


def test_prior_compiled_prompt_cannot_authorize_new_video_create(tmp_path: Path) -> None:
    artifacts = _artifacts("spacex_pilot_001", seed="SpaceX coastal launch")
    root = _write_sources(tmp_path / "original", artifacts)
    _, original_request = compile_video(root)
    prior_attempt = video_gen.build_attempt_record(
        compiled_request=original_request,
        attempt_number=1,
    )

    new_artifacts = _artifacts("spacex_production_002", date="2026-08-05", seed="SpaceX coastal launch")
    new_root = _write_sources(tmp_path / "new", new_artifacts)
    _, _ = compile_video(new_root)
    reused_request = dict(original_request)
    reused_request["video_id"] = new_artifacts["lena_video_spec_v1"]["video_id"]
    reused_request["governed_date"] = "2026-08-05"

    with pytest.raises(video_gen.LenaVideoCreativeError) as excinfo:
        video_gen.validate_prompt_reuse(
            prior_attempt=prior_attempt,
            proposed_compiled_request=reused_request,
            operation="new_provider_create",
        )
    assert excinfo.value.code == "prompt_reuse_blocked"


def test_qa_rejected_attempt_requires_new_attempt_record_and_prompt(tmp_path: Path) -> None:
    original_root = _write_sources(tmp_path / "original", _artifacts("qa_rejected_video", seed="SpaceX coastal launch"))
    _, original_request = compile_video(original_root)
    rejected_attempt = video_gen.build_attempt_record(
        compiled_request=original_request,
        attempt_number=1,
    )
    rejected_attempt["qa_result"] = "qa_rejected"
    rejected_attempt["provider_job_id"] = "provider-job-1"

    with pytest.raises(video_gen.LenaVideoCreativeError) as excinfo:
        video_gen.build_attempt_record(
            compiled_request=original_request,
            attempt_number=2,
            superseded_attempt=rejected_attempt,
            previous_qa_findings=["pointing direction failed"],
            exact_creative_changes=[],
        )
    assert excinfo.value.code == "qa_rejected_attempt_prompt_reuse_blocked"

    repaired_root = _write_sources(tmp_path / "repaired", _artifacts("qa_rejected_video", seed="rainy balcony reset"))
    _, repaired_request = compile_video(repaired_root)
    repaired_attempt = video_gen.build_attempt_record(
        compiled_request=repaired_request,
        attempt_number=2,
        superseded_attempt=rejected_attempt,
        previous_qa_findings=["pointing direction failed"],
        exact_creative_changes=["changed concept to remove fragile pointing geometry"],
    )
    assert repaired_attempt["superseded_attempt_id"] == rejected_attempt["attempt_id"]
    assert repaired_attempt["compiled_prompt_sha256"] != rejected_attempt["compiled_prompt_sha256"]


def test_same_job_reconciliation_preserves_original_prompt(tmp_path: Path) -> None:
    root = _write_sources(tmp_path, _artifacts("same_job_video", seed="night market dessert choice"))
    _, request = compile_video(root)
    attempt = video_gen.build_attempt_record(compiled_request=request, attempt_number=1)
    attempt["provider_job_id"] = "provider-job-1"

    result = video_gen.validate_prompt_reuse(
        prior_attempt=attempt,
        proposed_compiled_request=request,
        operation="same_ambiguous_submission_reconciliation",
    )

    assert result["ok"] is True
    assert video_gen.prompt_sha256(request) == attempt["compiled_prompt_sha256"]


def test_deterministic_recompile_of_same_attempt_is_byte_identical(tmp_path: Path) -> None:
    root = _write_sources(tmp_path, _artifacts("deterministic_video", seed="rainy balcony reset"))

    first = compile_video(root)[1]
    second = compile_video(root)[1]

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["exact_compiled_prompt"].encode("utf-8") == second["exact_compiled_prompt"].encode("utf-8")


def test_daily_novelty_rules_reject_repeated_environment_gesture_and_hook() -> None:
    candidate = _artifacts("novelty_video", seed="night market dessert choice")
    history = [video_gen.novelty_profile(candidate)]

    result = video_gen.run_novelty_governor(candidate, history)

    assert result["ok"] is False
    assert "consecutive_reuse:environment" in result["rejection_reasons"]
    assert "consecutive_reuse:principal_gesture" in result["rejection_reasons"]
    assert "consecutive_reuse:hook_structure" in result["rejection_reasons"]


def test_static_lena_identity_remains_stable_across_different_prompts(tmp_path: Path) -> None:
    first = compile_video(_write_sources(tmp_path, _artifacts("identity_video_1", seed="night market dessert choice")))[1]
    second = compile_video(_write_sources(tmp_path, _artifacts("identity_video_2", seed="rainy balcony reset")))[1]

    assert first["exact_compiled_prompt"].startswith(CHARACTER_ELEMENT_TOKEN)
    assert second["exact_compiled_prompt"].startswith(CHARACTER_ELEMENT_TOKEN)
    assert first["character_element_token"] == second["character_element_token"]


def test_no_provider_or_network_calls_occur(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _blocked_socket(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("network access is forbidden in this offline generator")

    monkeypatch.setattr(socket, "socket", _blocked_socket)
    artifacts = _artifacts("offline_only_video", seed="rainy balcony reset")
    root = _write_sources(tmp_path, artifacts)
    _, compiled = video_gen.compile_canonical_video_package(root)

    assert (root / "lena_higgsfield_compiled_request_v1.json").is_file()
    assert compiled["provider_arguments"]["execution_mode"] == "disabled"
    assert compiled["execution_authorized"] is False


def test_three_offline_examples_have_distinct_prompt_hashes(tmp_path: Path) -> None:
    examples = [
        compile_video(_write_sources(tmp_path, _artifacts("example_01_spacex", seed="SpaceX coastal launch")))[1],
        compile_video(_write_sources(tmp_path, _artifacts("example_02_market", seed="night market dessert choice")))[1],
        compile_video(_write_sources(tmp_path, _artifacts("example_03_balcony", seed="rainy balcony reset")))[1],
    ]
    hashes = {video_gen.prompt_sha256(item) for item in examples}
    assert len(hashes) == 3


def test_fresh_generator_does_not_define_parallel_provider_compiler_or_schema_helpers() -> None:
    module_text = Path(video_gen.__file__).read_text(encoding="utf-8")

    assert "def compile_provider_request" not in module_text
    assert "def canonical_json_bytes" not in module_text
    assert "ATTEMPT_SCHEMA_VERSION" not in module_text
    assert "pipeline.video" not in module_text
    assert 'model": "seedance' not in module_text.lower()


def test_cli_builds_canonical_package_without_generation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from tools import lena_build_fresh_video_package_v1 as cli

    rc = cli.main(
        [
            "--video-slug",
            "cli_example",
            "--governed-date",
            "2026-08-04",
            "--user-seed",
            "rainy balcony reset",
            "--out-root",
            str(tmp_path),
            "--write",
            "--compile",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert output["provider_call_performed"] is False
    assert output["generation_performed"] is False
    assert output["queue_created"] is False
    assert output["publication_performed"] is False
    assert output["character_element_token_first"] is True
    assert output["canonical_source_validation"]["ok"] is True
    assert canonical_sha256(json.loads(Path(output["video_root"], "lena_higgsfield_compiled_request_v1.json").read_text(encoding="utf-8"))) == output["request_sha256"]
