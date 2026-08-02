from __future__ import annotations

from typing import Any, Mapping

from pipeline.media_properties.json_authority_v1 import (
    Issue,
    JsonAuthorityError,
    atomic_write_json,
    canonical_json_bytes,
    canonical_sha256,
)


PROPERTY_ID = "lena"
SCHEMA_VERSION = "lena_video_artifact_v1"
PLAN_COMPILER_VERSION = "lena_video_plan_compiler_v1"
HIGGSFIELD_COMPILER_VERSION = "lena_video_higgsfield_compiler_v1"
CHARACTER_ELEMENT_UUID = "6a842337-ef20-4cb9-a0ff-04fa5eb8f8d3"
CHARACTER_ELEMENT_TOKEN = f"@[Lena]({CHARACTER_ELEMENT_UUID})"

LenaVideoContractError = JsonAuthorityError


def compilation_fingerprint(value: Any) -> str:
    return canonical_sha256(
        value,
        excluded_fields={
            "compilation_timestamp",
            "deterministic_compilation_fingerprint",
        },
    )


def zero_activity_counters() -> dict[str, int]:
    return {
        "network_calls": 0,
        "provider_calls": 0,
        "generation_actions": 0,
        "publishing_actions": 0,
        "scheduler_actions": 0,
        "photo_lane_modifications": 0,
        "video_execution_actions": 0,
    }


def structured_failure(
    report_type: str,
    error: LenaVideoContractError,
    *,
    counters: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "report_type": report_type,
        "errors": [issue.to_dict() for issue in error.issues],
        "counters": dict(counters or zero_activity_counters()),
    }


__all__ = [
    "CHARACTER_ELEMENT_TOKEN",
    "CHARACTER_ELEMENT_UUID",
    "HIGGSFIELD_COMPILER_VERSION",
    "Issue",
    "LenaVideoContractError",
    "PROPERTY_ID",
    "PLAN_COMPILER_VERSION",
    "SCHEMA_VERSION",
    "atomic_write_json",
    "canonical_json_bytes",
    "canonical_sha256",
    "compilation_fingerprint",
    "structured_failure",
    "zero_activity_counters",
]
