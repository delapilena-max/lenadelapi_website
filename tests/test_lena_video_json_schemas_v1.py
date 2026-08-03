from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.media_properties.json_authority_v1 import (
    JsonAuthorityError,
    LocalSchemaStore,
)
from pipeline.media_properties.lena.video.artifacts import (
    ARTIFACT_FILES,
    SCHEMA_FILES,
    VideoArtifactStore,
)
from pipeline.media_properties.lena.video.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from tests.lena_video_json_test_support import (
    PILOT_ROOT,
    SCHEMA_ROOT,
    copy_pilot,
    read_artifact,
    write_artifact,
)


def _walk_schema(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_schema(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_schema(child)


def test_complete_pilot_loads_all_fourteen_strict_artifacts() -> None:
    artifacts = VideoArtifactStore(PILOT_ROOT).load_all()

    assert len(ARTIFACT_FILES) == 14
    assert set(artifacts) == set(ARTIFACT_FILES)
    assert all(item.sha256 == canonical_sha256(item.data) for item in artifacts.values())


def test_every_object_schema_rejects_unknown_fields() -> None:
    schema_paths = [SCHEMA_ROOT / "common_defs_v1.schema.json"] + [
        SCHEMA_ROOT / filename for filename in SCHEMA_FILES.values()
    ]

    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        for node in _walk_schema(schema):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, (path, node)


def test_all_schema_references_are_local_and_resolvable() -> None:
    store = LocalSchemaStore(SCHEMA_ROOT)
    filenames = ["common_defs_v1.schema.json", *SCHEMA_FILES.values()]

    for filename in filenames:
        schema = store.load(filename)
        for node in _walk_schema(schema):
            reference = node.get("$ref")
            if not isinstance(reference, str):
                continue
            assert "://" not in reference
            assert ".." not in reference
            assert not reference.startswith(("/", "\\"))
            resolved, _ = store.resolve(reference, filename)
            assert isinstance(resolved, dict)


@pytest.mark.parametrize("artifact_type", tuple(ARTIFACT_FILES))
def test_unknown_root_field_is_rejected_for_each_artifact(
    tmp_path: Path,
    artifact_type: str,
) -> None:
    root = copy_pilot(tmp_path)
    value = read_artifact(root, artifact_type)
    value["unexpected_field"] = "must fail closed"
    write_artifact(root, artifact_type, value)

    with pytest.raises(JsonAuthorityError) as captured:
        VideoArtifactStore(root).load(artifact_type)

    assert "schema_unknown_field" in {issue.code for issue in captured.value.issues}


def test_canonical_serialization_and_hashing_ignore_key_order_only() -> None:
    first = {"b": [2, 3], "a": {"locked": True, "count": 1}}
    second = {"a": {"count": 1, "locked": True}, "b": [2, 3]}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_sha256(first) == canonical_sha256(second)
    assert canonical_sha256({**second, "b": [3, 2]}) != canonical_sha256(first)


def test_canonical_authority_rejects_floating_point_values() -> None:
    with pytest.raises(JsonAuthorityError) as captured:
        canonical_sha256({"duration_seconds": 8.0})

    assert captured.value.issues[0].code == "canonical_float_forbidden"


def test_schema_reference_traversal_and_network_references_fail_closed() -> None:
    store = LocalSchemaStore(SCHEMA_ROOT)

    with pytest.raises(JsonAuthorityError) as traversal:
        store.resolve("../outside.schema.json", "common_defs_v1.schema.json")
    with pytest.raises(JsonAuthorityError) as network:
        store.resolve("https://example.invalid/schema.json", "common_defs_v1.schema.json")

    assert traversal.value.issues[0].code == "schema_reference_not_local"
    assert network.value.issues[0].code == "schema_reference_network_forbidden"


def test_artifact_path_traversal_fails_closed() -> None:
    store = VideoArtifactStore(PILOT_ROOT)

    with pytest.raises(JsonAuthorityError) as captured:
        store.safe_path("../outside.json")

    assert captured.value.issues[0].code == "artifact_path_traversal"


def test_artifact_symlink_escape_fails_closed(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    link = root / "escape.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(JsonAuthorityError) as captured:
        VideoArtifactStore(root).safe_path("escape.json")

    assert captured.value.issues[0].code in {
        "artifact_path_escape",
        "artifact_symlink_forbidden",
    }


def test_schema_symlink_escape_fails_closed(tmp_path: Path) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    outside = tmp_path / "outside.schema.json"
    outside.write_text('{"type":"object"}\n', encoding="utf-8")
    link = schema_root / "escape.schema.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(JsonAuthorityError) as captured:
        LocalSchemaStore(schema_root).load("escape.schema.json")

    assert captured.value.issues[0].code == "schema_reference_escape"
