from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from pipeline.media_properties.json_authority_v1 import (
    LocalSchemaStore,
    validate_schema_instance,
)

from .contracts import (
    LenaVideoContractError,
    Issue,
    PROPERTY_ID,
    canonical_sha256,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
SCHEMA_ROOT = PACKAGE_ROOT / "schemas"

ARTIFACT_FILES: dict[str, str] = {
    "lena_video_character_authority_v1": "lena_video_character_authority_v1.json",
    "lena_video_policy_v1": "lena_video_policy_v1.json",
    "lena_video_business_intent_v1": "lena_video_business_intent_v1.json",
    "lena_video_spec_v1": "lena_video_spec_v1.json",
    "lena_video_hpe_v1": "lena_video_hpe_v1.json",
    "lena_video_environment_v1": "lena_video_environment_v1.json",
    "lena_video_wardrobe_v1": "lena_video_wardrobe_v1.json",
    "lena_video_camera_v1": "lena_video_camera_v1.json",
    "lena_video_audio_plan_v1": "lena_video_audio_plan_v1.json",
    "lena_video_generation_plan_v1": "lena_video_generation_plan_v1.json",
    "lena_higgsfield_compiled_request_v1": "lena_higgsfield_compiled_request_v1.json",
    "lena_video_manifest_v1": "lena_video_manifest_v1.json",
    "lena_video_qa_v1": "lena_video_qa_v1.json",
    "lena_video_learning_v1": "lena_video_learning_v1.json",
}
SCHEMA_FILES = {key: f"{key}.schema.json" for key in ARTIFACT_FILES}
SOURCE_TYPES = tuple(list(ARTIFACT_FILES)[:9])


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
    stage: str = "authority",
    artifact_id: str | None = None,
    field_path: str | None = None,
    expected: Any = None,
    actual: Any = None,
    source_file: str | None = None,
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
    )


class VideoArtifactStore:
    def __init__(self, video_root: Path):
        source_root = video_root.absolute()
        is_junction = getattr(source_root, "is_junction", lambda: False)
        if source_root.is_symlink() or is_junction():
            raise LenaVideoContractError(
                _issue(
                    "video_root_unsafe",
                    "Video root must be a real directory, not a symlink or junction.",
                    stage="load",
                    source_file=str(video_root),
                )
            )
        try:
            self.root = source_root.resolve(strict=True)
        except OSError as exc:
            raise LenaVideoContractError(
                _issue(
                    "video_root_unavailable",
                    "Video root does not exist or cannot be resolved safely.",
                    stage="load",
                    source_file=str(video_root),
                )
            ) from exc
        if not self.root.is_dir():
            raise LenaVideoContractError(
                _issue(
                    "video_root_unsafe",
                    "Video root must be a directory.",
                    stage="load",
                    source_file=str(video_root),
                )
            )
        self.schemas = LocalSchemaStore(SCHEMA_ROOT)

    def safe_path(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise LenaVideoContractError(
                _issue(
                    "artifact_path_traversal",
                    "Artifact path must remain beneath the video root.",
                    stage="load",
                    source_file=relative_path,
                )
            )
        candidate = self.root.joinpath(*pure.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise LenaVideoContractError(
                _issue(
                    "artifact_path_missing",
                    "Artifact path could not be resolved.",
                    stage="load",
                    source_file=relative_path,
                )
            ) from exc
        if not resolved.is_relative_to(self.root):
            raise LenaVideoContractError(
                _issue(
                    "artifact_path_escape",
                    "Artifact path resolves outside the video root.",
                    stage="load",
                    source_file=relative_path,
                )
            )
        current = self.root
        for part in pure.parts:
            current = current / part
            is_junction = getattr(current, "is_junction", lambda: False)
            if current.exists() and (current.is_symlink() or is_junction()):
                raise LenaVideoContractError(
                    _issue(
                        "artifact_symlink_forbidden",
                        "Artifact paths must not traverse symbolic links.",
                        stage="load",
                        source_file=relative_path,
                    )
                )
        return resolved

    def load(self, artifact_type: str) -> LoadedArtifact:
        if artifact_type not in ARTIFACT_FILES:
            raise LenaVideoContractError(
                _issue(
                    "artifact_type_unknown",
                    "Unknown Lena video artifact type.",
                    stage="load",
                    actual=artifact_type,
                )
            )
        relative = ARTIFACT_FILES[artifact_type]
        path = self.safe_path(relative)
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise LenaVideoContractError(
                _issue(
                    "artifact_bom_forbidden",
                    "Authority JSON must be UTF-8 without BOM.",
                    stage="syntax",
                    source_file=relative,
                )
            )
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise LenaVideoContractError(
                _issue(
                    "json_syntax_invalid",
                    "Artifact is not valid UTF-8 JSON.",
                    stage="syntax",
                    source_file=relative,
                    actual=str(exc),
                )
            ) from exc
        if not isinstance(value, dict):
            raise LenaVideoContractError(
                _issue(
                    "artifact_not_object",
                    "Production artifacts must be JSON objects.",
                    stage="syntax",
                    source_file=relative,
                )
            )
        schema_filename = SCHEMA_FILES[artifact_type]
        issues = validate_schema_instance(
            value,
            self.schemas.load(schema_filename),
            store=self.schemas,
            schema_filename=schema_filename,
            source_file=relative,
            artifact_id=value.get("artifact_id"),
        )
        if issues:
            raise LenaVideoContractError(issues)
        if value["artifact_type"] != artifact_type:
            raise LenaVideoContractError(
                _issue(
                    "artifact_type_mismatch",
                    "Artifact type does not match its governed filename.",
                    stage="load",
                    artifact_id=value["artifact_id"],
                    expected=artifact_type,
                    actual=value["artifact_type"],
                    source_file=relative,
                )
            )
        return LoadedArtifact(
            path=path,
            relative_path=relative,
            data=value,
            sha256=canonical_sha256(value),
        )

    def load_all(self) -> dict[str, LoadedArtifact]:
        return {artifact_type: self.load(artifact_type) for artifact_type in ARTIFACT_FILES}

    def load_sources(self) -> dict[str, LoadedArtifact]:
        return {artifact_type: self.load(artifact_type) for artifact_type in SOURCE_TYPES}


def validate_cross_artifact_authority(
    artifacts: Mapping[str, LoadedArtifact],
) -> list[Issue]:
    issues: list[Issue] = []
    by_id: dict[str, LoadedArtifact] = {}
    property_ids: set[str] = set()
    video_ids: set[str] = set()
    governed_dates: set[str] = set()
    for loaded in artifacts.values():
        if loaded.artifact_id in by_id:
            issues.append(
                _issue(
                    "duplicate_artifact_id",
                    "Artifact IDs must be unique.",
                    artifact_id=loaded.artifact_id,
                    source_file=loaded.relative_path,
                )
            )
        by_id[loaded.artifact_id] = loaded
        property_ids.add(loaded.data["property_id"])
        video_ids.add(loaded.data["video_id"])
        governed_dates.add(loaded.data["governed_date"])
    if property_ids != {PROPERTY_ID}:
        issues.append(_issue("property_id_mismatch", "All artifacts must use the Lena property ID.", expected=[PROPERTY_ID], actual=sorted(property_ids)))
    if len(video_ids) != 1:
        issues.append(_issue("video_id_mismatch", "All artifacts must share one video ID.", actual=sorted(video_ids)))
    if len(governed_dates) != 1:
        issues.append(_issue("governed_date_mismatch", "All artifacts must share one governed date.", actual=sorted(governed_dates)))
    graph: dict[str, list[str]] = {artifact_id: [] for artifact_id in by_id}
    for loaded in artifacts.values():
        for index, reference in enumerate(loaded.data["upstream_artifacts"]):
            upstream = by_id.get(reference["artifact_id"])
            if upstream is None:
                issues.append(_issue("upstream_artifact_missing", "Referenced upstream artifact is absent.", artifact_id=loaded.artifact_id, field_path=f"$/upstream_artifacts/{index}", actual=reference["artifact_id"], source_file=loaded.relative_path))
                continue
            graph[loaded.artifact_id].append(upstream.artifact_id)
            if reference["sha256"] != upstream.sha256:
                issues.append(_issue("upstream_sha256_mismatch", "Upstream authority changed after this artifact was authored or compiled.", artifact_id=loaded.artifact_id, field_path=f"$/upstream_artifacts/{index}/sha256", expected=upstream.sha256, actual=reference["sha256"], source_file=loaded.relative_path))
            if loaded.data["created_at"] < upstream.data["created_at"]:
                issues.append(_issue("upstream_created_after_downstream", "Downstream timestamp precedes upstream authority.", artifact_id=loaded.artifact_id, field_path="$/created_at", expected=f">= {upstream.data['created_at']}", actual=loaded.data["created_at"], source_file=loaded.relative_path))
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str) -> None:
        if node in visiting:
            issues.append(_issue("circular_artifact_reference", "Artifact authority graph contains a cycle.", artifact_id=node))
            return
        if node in visited:
            return
        visiting.add(node)
        for upstream in graph[node]:
            walk(upstream)
        visiting.remove(node)
        visited.add(node)

    for artifact_id in graph:
        walk(artifact_id)
    return issues
