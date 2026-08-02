from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PROPERTY_ID = "interstitial_travel_bureau"
PROPERTY_NAME = "The Interstitial Travel Bureau"
SCHEMA_VERSION = "itb_creative_os_v1"
COMPILER_VERSION = "itb_deterministic_compiler_v1"
GENERATOR_VERSION = "itb_authored_pilot_v1"


@dataclass(frozen=True)
class Issue:
    code: str
    stage: str
    message: str
    severity: str = "blocking"
    artifact_id: str | None = None
    field_path: str | None = None
    expected: Any = None
    actual: Any = None
    source_file: str | None = None
    suggested_correction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class ITBContractError(RuntimeError):
    def __init__(self, issues: Issue | Sequence[Issue]):
        values = (issues,) if isinstance(issues, Issue) else tuple(issues)
        if not values:
            raise ValueError("ITBContractError requires at least one issue")
        self.issues = values
        super().__init__(values[0].message)


def _without_fields(value: Any, excluded_fields: frozenset[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_fields(item, excluded_fields)
            for key, item in value.items()
            if key not in excluded_fields
        }
    if isinstance(value, list):
        return [_without_fields(item, excluded_fields) for item in value]
    return value


def _validate_canonical_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise ITBContractError(
            Issue(
                code="canonical_float_forbidden",
                stage="canonicalization",
                message="Canonical ITB JSON uses integers for exact numeric values.",
                field_path=path,
                actual=value,
                suggested_correction="Represent durations in milliseconds, money in cents, and ratios in basis points.",
            )
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_canonical_value(item, f"{path}/{index}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ITBContractError(
                    Issue(
                        code="canonical_non_string_key",
                        stage="canonicalization",
                        message="Canonical ITB JSON object keys must be strings.",
                        field_path=path,
                        actual=type(key).__name__,
                    )
                )
            _validate_canonical_value(item, f"{path}/{key}")
        return
    raise ITBContractError(
        Issue(
            code="canonical_value_unsupported",
            stage="canonicalization",
            message="Value cannot be represented by the ITB canonical JSON contract.",
            field_path=path,
            actual=type(value).__name__,
        )
    )


def canonical_json_bytes(
    value: Any,
    *,
    excluded_fields: Iterable[str] = (),
) -> bytes:
    """Serialize as UTF-8, no BOM/whitespace, sorted keys, LF-free canonical JSON."""
    normalized = _without_fields(value, frozenset(excluded_fields))
    _validate_canonical_value(normalized)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any, *, excluded_fields: Iterable[str] = ()) -> str:
    return hashlib.sha256(
        canonical_json_bytes(value, excluded_fields=excluded_fields)
    ).hexdigest()


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


def atomic_write_json(output_path: Path, value: Any) -> str:
    """Write only to an explicit path; identical existing output is idempotent."""
    path = output_path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    parent = path.parent.resolve(strict=True)
    if path.exists() and path.is_symlink():
        raise ITBContractError(
            Issue(
                code="output_symlink_forbidden",
                stage="write",
                message="Output path must not be a symbolic link.",
                source_file=str(path),
            )
        )
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    encoded = payload.encode("utf-8")
    if path.exists():
        existing = path.read_bytes()
        if existing == encoded:
            return "idempotent_match"
        raise ITBContractError(
            Issue(
                code="output_collision",
                stage="write",
                message="Output already exists with different content.",
                source_file=str(path),
                suggested_correction="Choose a new explicit output path.",
            )
        )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return "written"
