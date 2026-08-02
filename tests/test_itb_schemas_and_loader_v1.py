from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.media_properties.interstitial_travel_bureau.artifacts import (
    ARTIFACT_FILES,
    SCHEMA_FILES,
    EpisodeStore,
    LocalSchemaStore,
)
from pipeline.media_properties.interstitial_travel_bureau.contracts import ITBContractError
from tests.itb_helpers import PACKAGE_ROOT, PILOT_ROOT, copy_pilot, read_json, write_json


def _refs(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                yield child
            yield from _refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _refs(child)


def test_every_required_schema_is_registered_and_uses_local_refs():
    assert len(ARTIFACT_FILES) == 14
    store = LocalSchemaStore()
    for artifact_type, filename in SCHEMA_FILES.items():
        schema = store.load(filename)
        assert schema["$id"] == filename
        assert artifact_type in ARTIFACT_FILES
        assert all("://" not in ref and not ref.startswith(("/", "\\")) for ref in _refs(schema))


def test_every_pilot_artifact_passes_its_schema():
    artifacts = EpisodeStore(PILOT_ROOT).load_all()
    assert set(artifacts) == set(ARTIFACT_FILES)
    assert all(item.sha256 for item in artifacts.values())


def test_unknown_field_fails_closed(tmp_path: Path):
    root = copy_pilot(tmp_path)
    path = root / "bureau_canon_v1.json"
    value = read_json(path)
    value["surprise"] = True
    write_json(path, value)
    with pytest.raises(ITBContractError) as error:
        EpisodeStore(root).load("bureau_canon_v1")
    assert "schema_unknown_field" in {item.code for item in error.value.issues}


def test_invalid_json_returns_precise_syntax_error(tmp_path: Path):
    root = copy_pilot(tmp_path)
    (root / "bureau_canon_v1.json").write_text("{", encoding="utf-8")
    with pytest.raises(ITBContractError) as error:
        EpisodeStore(root).load("bureau_canon_v1")
    assert error.value.issues[0].code == "json_syntax_invalid"


def test_path_traversal_is_rejected():
    with pytest.raises(ITBContractError) as error:
        EpisodeStore(PILOT_ROOT).safe_path("../bureau_canon_v1.json")
    assert error.value.issues[0].code == "artifact_path_traversal"


def test_symlink_escape_is_rejected(tmp_path: Path):
    root = copy_pilot(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target.json").write_text("{}", encoding="utf-8")
    link = root / "escape"
    try:
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            if sys.platform != "win32":
                raise
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert created.returncode == 0, created.stderr
        with pytest.raises(ITBContractError) as error:
            EpisodeStore(root).safe_path("escape/target.json")
        assert error.value.issues[0].code in {"artifact_path_escape", "artifact_symlink_forbidden"}
    finally:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            os.rmdir(link)


def test_schema_resolver_rejects_network_and_traversal():
    store = LocalSchemaStore()
    for reference in ("https://example.invalid/schema.json", "../escape.schema.json"):
        with pytest.raises(ITBContractError):
            store.resolve(reference, "bureau_canon_v1.schema.json")
