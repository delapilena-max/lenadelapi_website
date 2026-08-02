from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .contracts import ITBContractError, Issue, PROPERTY_ID, canonical_sha256


PACKAGE_ROOT = Path(__file__).resolve().parent
SCHEMA_ROOT = PACKAGE_ROOT / "schemas"

ARTIFACT_FILES: dict[str, str] = {
    "bureau_canon_v1": "bureau_canon_v1.json",
    "bureau_creative_genome_v1": "bureau_creative_genome_v1.json",
    "bureau_concept_card_v1": "bureau_concept_card_v1.json",
    "bureau_world_dossier_v1": "bureau_world_dossier_v1.json",
    "bureau_entity_sheet_v1": "bureau_entity_sheet_v1.json",
    "bureau_audio_plan_v1": "bureau_audio_plan_v1.json",
    "bureau_episode_script_v1": "bureau_episode_script_v1.json",
    "bureau_visual_sequence_v1": "bureau_visual_sequence_v1.json",
    "bureau_generation_plan_v1": "bureau_generation_plan_v1.json",
    "bureau_compiled_request_v1": "bureau_compiled_request_v1.json",
    "bureau_episode_manifest_v1": "bureau_episode_manifest_v1.json",
    "bureau_episode_qa_v1": "bureau_episode_qa_v1.json",
    "bureau_continuity_ledger_v1": "bureau_continuity_ledger_v1.json",
    "bureau_episode_learning_v1": "bureau_episode_learning_v1.json",
}
SCHEMA_FILES = {key: f"{key}.schema.json" for key in ARTIFACT_FILES}


@dataclass(frozen=True)
class LoadedArtifact:
    path: Path
    relative_path: str
    data: dict[str, Any]
    sha256: str

    @property
    def artifact_id(self) -> str:
        return self.data["artifact_id"]

    @property
    def artifact_type(self) -> str:
        return self.data["artifact_type"]


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


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    if pointer in ("", "/"):
        return current
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


class LocalSchemaStore:
    def __init__(self, schema_root: Path = SCHEMA_ROOT):
        self.root = schema_root.resolve(strict=True)
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, filename: str) -> dict[str, Any]:
        pure = PurePosixPath(filename)
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1:
            raise ITBContractError(
                _issue(
                    "schema_reference_not_local",
                    "Schema references must name one repository-controlled schema file.",
                    source_file=filename,
                )
            )
        if filename not in self._cache:
            path = (self.root / filename).resolve(strict=True)
            if not path.is_relative_to(self.root) or path.is_symlink():
                raise ITBContractError(
                    _issue("schema_reference_escape", "Schema reference escaped the schema root.", source_file=filename)
                )
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ITBContractError(_issue("schema_not_object", "Schema must be a JSON object.", source_file=filename))
            self._cache[filename] = value
        return self._cache[filename]

    def resolve(self, reference: str, current_filename: str) -> tuple[dict[str, Any], str]:
        if "://" in reference or reference.startswith(("/", "\\")):
            raise ITBContractError(
                _issue("schema_reference_network_forbidden", "Only local schema references are allowed.", source_file=reference)
            )
        filename, marker, fragment = reference.partition("#")
        target_filename = filename or current_filename
        target = self.load(target_filename)
        if marker and fragment:
            try:
                target = _json_pointer(target, fragment)
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise ITBContractError(
                    _issue("schema_reference_missing", "Local schema reference does not resolve.", source_file=reference)
                ) from exc
        return target, target_filename


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


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
    if isinstance(expected_type, list):
        valid_type = any(_matches_type(value, item) for item in expected_type)
    elif isinstance(expected_type, str):
        valid_type = _matches_type(value, expected_type)
    else:
        valid_type = True
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


class EpisodeStore:
    def __init__(self, episode_root: Path):
        source_root = episode_root.absolute()
        is_junction = getattr(source_root, "is_junction", lambda: False)
        if source_root.is_symlink() or is_junction():
            raise ITBContractError(_issue("episode_root_unsafe", "Episode root must be a real directory, not a symlink or junction.", stage="load", source_file=str(episode_root)))
        self.root = source_root.resolve(strict=True)
        if not self.root.is_dir():
            raise ITBContractError(_issue("episode_root_unsafe", "Episode root must be a real directory, not a symlink.", stage="load", source_file=str(episode_root)))
        self.schemas = LocalSchemaStore()

    def safe_path(self, relative_path: str, *, must_exist: bool = True) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise ITBContractError(_issue("artifact_path_traversal", "Artifact path must remain beneath the episode root.", stage="load", source_file=relative_path))
        candidate = self.root.joinpath(*pure.parts)
        try:
            resolved = candidate.resolve(strict=must_exist)
        except OSError as exc:
            raise ITBContractError(_issue("artifact_path_missing", "Artifact path could not be resolved.", stage="load", source_file=relative_path)) from exc
        if not resolved.is_relative_to(self.root):
            raise ITBContractError(_issue("artifact_path_escape", "Artifact path resolves outside the episode root.", stage="load", source_file=relative_path))
        current = self.root
        for part in pure.parts:
            current = current / part
            is_junction = getattr(current, "is_junction", lambda: False)
            if current.exists() and (current.is_symlink() or is_junction()):
                raise ITBContractError(_issue("artifact_symlink_forbidden", "Artifact paths must not traverse symbolic links.", stage="load", source_file=relative_path))
        return resolved

    def load(self, artifact_type: str) -> LoadedArtifact:
        if artifact_type not in ARTIFACT_FILES:
            raise ITBContractError(_issue("artifact_type_unknown", "Unknown ITB artifact type.", stage="load", actual=artifact_type))
        relative = ARTIFACT_FILES[artifact_type]
        path = self.safe_path(relative)
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ITBContractError(_issue("artifact_bom_forbidden", "ITB authority JSON must be UTF-8 without BOM.", stage="syntax", source_file=relative))
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ITBContractError(_issue("json_syntax_invalid", "Artifact is not valid UTF-8 JSON.", stage="syntax", source_file=relative, actual=str(exc))) from exc
        if not isinstance(value, dict):
            raise ITBContractError(_issue("artifact_not_object", "Production artifacts must be JSON objects.", stage="syntax", source_file=relative))
        artifact_id = value.get("artifact_id") if isinstance(value.get("artifact_id"), str) else None
        schema_filename = SCHEMA_FILES[artifact_type]
        schema = self.schemas.load(schema_filename)
        issues = validate_schema_instance(value, schema, store=self.schemas, schema_filename=schema_filename, source_file=relative, artifact_id=artifact_id)
        if issues:
            raise ITBContractError(issues)
        if value.get("artifact_type") != artifact_type:
            raise ITBContractError(_issue("artifact_type_mismatch", "Artifact type does not match its governed filename.", stage="load", artifact_id=artifact_id, expected=artifact_type, actual=value.get("artifact_type"), source_file=relative))
        return LoadedArtifact(path=path, relative_path=relative, data=value, sha256=canonical_sha256(value))

    def load_all(self) -> dict[str, LoadedArtifact]:
        return {artifact_type: self.load(artifact_type) for artifact_type in ARTIFACT_FILES}


def validate_cross_artifact_authority(artifacts: Mapping[str, LoadedArtifact]) -> list[Issue]:
    issues: list[Issue] = []
    by_id: dict[str, LoadedArtifact] = {}
    property_ids = set()
    episode_ids = set()
    for loaded in artifacts.values():
        if loaded.artifact_id in by_id:
            issues.append(_issue("duplicate_artifact_id", "Artifact IDs must be unique.", stage="authority", artifact_id=loaded.artifact_id, source_file=loaded.relative_path))
        by_id[loaded.artifact_id] = loaded
        property_ids.add(loaded.data["property_id"])
        episode_ids.add(loaded.data["episode_id"])
    if property_ids != {PROPERTY_ID}:
        issues.append(_issue("property_id_mismatch", "All episode artifacts must use the ITB property ID.", stage="authority", expected=[PROPERTY_ID], actual=sorted(property_ids)))
    if len(episode_ids) != 1:
        issues.append(_issue("episode_id_mismatch", "All artifacts in an episode root must share one episode ID.", stage="authority", actual=sorted(episode_ids)))
    graph: dict[str, list[str]] = {item_id: [] for item_id in by_id}
    for loaded in artifacts.values():
        refs = loaded.data.get("upstream_artifacts", [])
        for index, reference in enumerate(refs):
            ref_id = reference["artifact_id"]
            upstream = by_id.get(ref_id)
            if upstream is None:
                issues.append(_issue("upstream_artifact_missing", "Referenced upstream artifact is absent.", stage="authority", artifact_id=loaded.artifact_id, field_path=f"$/upstream_artifacts/{index}", actual=ref_id, source_file=loaded.relative_path))
                continue
            if reference["sha256"] != upstream.sha256:
                issues.append(_issue("upstream_sha256_mismatch", "Upstream artifact changed after this artifact was authored or compiled.", stage="authority", artifact_id=loaded.artifact_id, field_path=f"$/upstream_artifacts/{index}/sha256", expected=upstream.sha256, actual=reference["sha256"], source_file=loaded.relative_path, correction="Revalidate and deterministically recompile downstream artifacts."))
            graph[loaded.artifact_id].append(ref_id)
            if loaded.data["created_at"] < upstream.data["created_at"]:
                issues.append(
                    _issue(
                        "upstream_created_after_downstream",
                        "Downstream artifact timestamp precedes its upstream authority.",
                        stage="authority",
                        artifact_id=loaded.artifact_id,
                        field_path="$/created_at",
                        expected=f">= {upstream.data['created_at']}",
                        actual=loaded.data["created_at"],
                        source_file=loaded.relative_path,
                    )
                )
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        if node in visiting:
            issues.append(_issue("circular_artifact_reference", "Artifact authority graph contains a cycle.", stage="authority", artifact_id=node))
            return
        if node in visited:
            return
        visiting.add(node)
        for upstream in graph.get(node, []):
            walk(upstream)
        visiting.remove(node)
        visited.add(node)

    for artifact_id in graph:
        walk(artifact_id)
    return issues


def find_artifact_by_id(
    artifacts: Mapping[str, LoadedArtifact], artifact_id: str
) -> LoadedArtifact | None:
    return next((loaded for loaded in artifacts.values() if loaded.artifact_id == artifact_id), None)
