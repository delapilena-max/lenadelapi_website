from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.media_properties.json_authority_v1 import validate_schema_instance

from .artifacts import LoadedArtifact, VideoArtifactStore
from .compilation import compile_generation_plan, compile_higgsfield_request
from .contracts import Issue, LenaVideoContractError, canonical_sha256
from .validation import validate_source_for_compilation


def _validate_generated(
    store: VideoArtifactStore,
    value: dict[str, Any],
    artifact_type: str,
) -> None:
    schema_filename = f"{artifact_type}.schema.json"
    issues = validate_schema_instance(
        value,
        store.schemas.load(schema_filename),
        store=store.schemas,
        schema_filename=schema_filename,
        source_file=f"{artifact_type}.json",
        artifact_id=value["artifact_id"],
    )
    if issues:
        raise LenaVideoContractError(issues)


def compile_video(video_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    store = VideoArtifactStore(video_root)
    sources = store.load_sources()
    issues = validate_source_for_compilation(sources)
    if issues:
        raise LenaVideoContractError(issues)
    plan = compile_generation_plan(sources)
    _validate_generated(store, plan, "lena_video_generation_plan_v1")
    loaded_plan = LoadedArtifact(
        path=video_root / "lena_video_generation_plan_v1.json",
        relative_path="lena_video_generation_plan_v1.json",
        data=plan,
        sha256=canonical_sha256(plan),
    )
    compiled = compile_higgsfield_request(loaded_plan, sources)
    if compiled["prompt_char_count"] > compiled["prompt_char_budget"]:
        raise LenaVideoContractError(
            Issue(
                code="compiled_prompt_execution_policy_exceeded",
                stage="compilation",
                message="Compiled prompt exceeds the governed Higgsfield execution budget.",
                artifact_id=compiled["artifact_id"],
                field_path="$/exact_compiled_prompt",
                expected=f"<= {compiled['prompt_char_budget']}",
                actual=compiled["prompt_char_count"],
            )
        )
    _validate_generated(store, compiled, "lena_higgsfield_compiled_request_v1")
    return plan, compiled


__all__ = ["compile_video"]
