from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


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


class JsonAuthorityError(RuntimeError):
    def __init__(self, issues: Issue | Sequence[Issue]):
        values = (issues,) if isinstance(issues, Issue) else tuple(issues)
        if not values:
            raise ValueError("JsonAuthorityError requires at least one issue")
        self.issues = values
        super().__init__(values[0].message)


def _issue(
    code: str,
    message: str,
    *,
    stage: str = "schema",
    artifact_id: str | None = None,
    field_path: str | None = None,
    expected: Any = None,
    actual: Any = None,
    source_file: str | None = None,
    correction: str | None = None,
) -> Issue:
    return Issue(
        code=code,
        stage=stage,
        message=message,
        artifact_id=artifact_id,
        field_path=field_path,
        expected=expected,
        actual=actual,
        source_file=source_file,
        suggested_correction=correction,
    )


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
        raise JsonAuthorityError(
            Issue(
                code="canonical_float_forbidden",
                stage="canonicalization",
                message="Canonical authority JSON uses integers for exact numeric values.",
                field_path=path,
                actual=value,
                suggested_correction="Use integer milliseconds, cents, or basis points.",
            )
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_canonical_value(item, f"{path}/{index}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise JsonAuthorityError(
                    Issue(
                        code="canonical_non_string_key",
                        stage="canonicalization",
                        message="Canonical JSON object keys must be strings.",
                        field_path=path,
                        actual=type(key).__name__,
                    )
                )
            _validate_canonical_value(item, f"{path}/{key}")
        return
    raise JsonAuthorityError(
        Issue(
            code="canonical_value_unsupported",
            stage="canonicalization",
            message="Value cannot be represented by the canonical JSON contract.",
            field_path=path,
            actual=type(value).__name__,
        )
    )


def canonical_json_bytes(value: Any, *, excluded_fields: Iterable[str] = ()) -> bytes:
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


def atomic_write_json(output_path: Path, value: Any) -> str:
    path = output_path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    parent = path.parent.resolve(strict=True)
    if path.exists() and path.is_symlink():
        raise JsonAuthorityError(
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
        if path.read_bytes() == encoded:
            return "idempotent_match"
        raise JsonAuthorityError(
            Issue(
                code="output_collision",
                stage="write",
                message="Output already exists with different content.",
                source_file=str(path),
                suggested_correction="Choose a new explicit output path.",
            )
        )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent, prefix=f".{path.name}.", suffix=".tmp"
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


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    if pointer in ("", "/"):
        return current
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


class LocalSchemaStore:
    def __init__(self, schema_root: Path):
        self.root = schema_root.resolve(strict=True)
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, filename: str) -> dict[str, Any]:
        pure = PurePosixPath(filename)
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1:
            raise JsonAuthorityError(
                _issue(
                    "schema_reference_not_local",
                    "Schema references must name one repository-controlled schema file.",
                    source_file=filename,
                )
            )
        if filename not in self._cache:
            path = (self.root / filename).resolve(strict=True)
            if not path.is_relative_to(self.root):
                raise JsonAuthorityError(
                    _issue(
                        "schema_reference_escape",
                        "Schema reference escaped the schema root.",
                        source_file=filename,
                    )
                )
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise JsonAuthorityError(
                    _issue("schema_not_object", "Schema must be a JSON object.", source_file=filename)
                )
            self._cache[filename] = value
        return self._cache[filename]

    def resolve(self, reference: str, current_filename: str) -> tuple[dict[str, Any], str]:
        if "://" in reference or reference.startswith(("/", "\\")):
            raise JsonAuthorityError(
                _issue(
                    "schema_reference_network_forbidden",
                    "Only local schema references are allowed.",
                    source_file=reference,
                )
            )
        filename, marker, fragment = reference.partition("#")
        target_filename = filename or current_filename
        target = self.load(target_filename)
        if marker and fragment:
            try:
                target = _json_pointer(target, fragment)
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise JsonAuthorityError(
                    _issue(
                        "schema_reference_missing",
                        "Local schema reference does not resolve.",
                        source_file=reference,
                    )
                ) from exc
        return target, target_filename


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def validate_schema_instance(
    value: Any,
    schema: Mapping[str, Any],
    *,
    store: LocalSchemaStore,
    schema_filename: str,
    source_file: str,
    artifact_id: str | None = None,
    pointer: str = "$",
) -> list[Issue]:
    issues: list[Issue] = []
    reference = schema.get("$ref")
    if isinstance(reference, str):
        resolved, resolved_filename = store.resolve(reference, schema_filename)
        return validate_schema_instance(
            value,
            resolved,
            store=store,
            schema_filename=resolved_filename,
            source_file=source_file,
            artifact_id=artifact_id,
            pointer=pointer,
        )
    expected_type = schema.get("type")
    valid_type = (
        any(_matches_type(value, item) for item in expected_type)
        if isinstance(expected_type, list)
        else _matches_type(value, expected_type)
        if isinstance(expected_type, str)
        else True
    )
    if not valid_type:
        return [
            _issue(
                "schema_type_mismatch",
                "Value does not match the schema type.",
                artifact_id=artifact_id,
                field_path=pointer,
                expected=expected_type,
                actual=type(value).__name__,
                source_file=source_file,
            )
        ]
    if "const" in schema and value != schema["const"]:
        issues.append(_issue("schema_const_mismatch", "Value does not match the required constant.", artifact_id=artifact_id, field_path=pointer, expected=schema["const"], actual=value, source_file=source_file))
    if "enum" in schema and value not in schema["enum"]:
        issues.append(_issue("schema_enum_mismatch", "Value is outside the governed enum.", artifact_id=artifact_id, field_path=pointer, expected=schema["enum"], actual=value, source_file=source_file))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            issues.append(_issue("schema_string_too_short", "String is shorter than allowed.", artifact_id=artifact_id, field_path=pointer, expected=schema.get("minLength"), actual=len(value), source_file=source_file))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            issues.append(_issue("schema_string_too_long", "String is longer than allowed.", artifact_id=artifact_id, field_path=pointer, expected=schema["maxLength"], actual=len(value), source_file=source_file))
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            issues.append(_issue("schema_pattern_mismatch", "String does not match the governed pattern.", artifact_id=artifact_id, field_path=pointer, expected=schema["pattern"], actual=value, source_file=source_file))
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            issues.append(_issue("schema_number_too_small", "Integer is below the allowed minimum.", artifact_id=artifact_id, field_path=pointer, expected=schema["minimum"], actual=value, source_file=source_file))
        if "maximum" in schema and value > schema["maximum"]:
            issues.append(_issue("schema_number_too_large", "Integer exceeds the allowed maximum.", artifact_id=artifact_id, field_path=pointer, expected=schema["maximum"], actual=value, source_file=source_file))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            issues.append(_issue("schema_array_too_short", "Array has fewer items than required.", artifact_id=artifact_id, field_path=pointer, expected=schema.get("minItems"), actual=len(value), source_file=source_file))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            issues.append(_issue("schema_array_too_long", "Array has more items than allowed.", artifact_id=artifact_id, field_path=pointer, expected=schema["maxItems"], actual=len(value), source_file=source_file))
        if schema.get("uniqueItems"):
            canonical = [canonical_sha256(item) for item in value]
            if len(canonical) != len(set(canonical)):
                issues.append(_issue("schema_array_not_unique", "Array items must be unique.", artifact_id=artifact_id, field_path=pointer, source_file=source_file))
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                issues.extend(validate_schema_instance(item, item_schema, store=store, schema_filename=schema_filename, source_file=source_file, artifact_id=artifact_id, pointer=f"{pointer}/{index}"))
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                issues.append(_issue("schema_required_field_missing", "Required field is missing.", artifact_id=artifact_id, field_path=f"{pointer}/{key}", expected="present", actual="missing", source_file=source_file))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    issues.append(_issue("schema_unknown_field", "Unknown field is not permitted.", artifact_id=artifact_id, field_path=f"{pointer}/{key}", source_file=source_file, correction="Remove the field or introduce it in a future schema version."))
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, Mapping):
                issues.extend(validate_schema_instance(value[key], child_schema, store=store, schema_filename=schema_filename, source_file=source_file, artifact_id=artifact_id, pointer=f"{pointer}/{key}"))
    return issues
