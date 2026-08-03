from __future__ import annotations

from typing import Any, Mapping

from pipeline.media_properties.json_authority_v1 import (
    Issue,
    JsonAuthorityError,
    atomic_write_json,
    canonical_json_bytes,
    canonical_sha256,
)


PROPERTY_ID = "interstitial_travel_bureau"
PROPERTY_NAME = "The Interstitial Travel Bureau"
SCHEMA_VERSION = "itb_creative_os_v1"
COMPILER_VERSION = "itb_deterministic_compiler_v1"
GENERATOR_VERSION = "itb_authored_pilot_v1"


ITBContractError = JsonAuthorityError


def compilation_fingerprint(value: Any) -> str:
    return canonical_sha256(
        value,
        excluded_fields={
            "compilation_timestamp",
            "deterministic_compilation_fingerprint",
        },
    )


def structured_failure(
    report_type: str,
    error: ITBContractError,
    *,
    counters: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "report_type": report_type,
        "errors": [issue.to_dict() for issue in error.issues],
        "counters": dict(counters or zero_activity_counters()),
    }


def zero_activity_counters() -> dict[str, int]:
    return {
        "network_calls": 0,
        "provider_calls": 0,
        "generation_actions": 0,
        "publishing_actions": 0,
        "scheduler_actions": 0,
        "lena_live_modifications": 0,
    }
