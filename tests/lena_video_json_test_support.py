from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from pipeline.media_properties.lena.video.artifacts import (
    LoadedArtifact,
    VideoArtifactStore,
)
from pipeline.media_properties.lena.video.contracts import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = (
    ROOT
    / "pipeline"
    / "media_properties"
    / "lena"
    / "video"
    / "pilots"
    / "spacex_launch_001"
)
SCHEMA_ROOT = ROOT / "pipeline" / "media_properties" / "lena" / "video" / "schemas"


def copy_pilot(tmp_path: Path) -> Path:
    destination = tmp_path / "spacex_launch_001"
    shutil.copytree(PILOT_ROOT, destination)
    return destination


def read_artifact(root: Path, artifact_type: str) -> dict[str, Any]:
    return json.loads(
        (root / f"{artifact_type}.json").read_text(encoding="utf-8")
    )


def write_artifact(root: Path, artifact_type: str, value: dict[str, Any]) -> None:
    (root / f"{artifact_type}.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def issue_codes(report: dict[str, Any]) -> set[str]:
    return {item["code"] for item in report["errors"]}


def mutated_loaded(
    root: Path,
    artifact_type: str,
    mutate: Callable[[dict[str, Any]], None],
    *,
    load_all: bool = False,
) -> dict[str, LoadedArtifact]:
    store = VideoArtifactStore(root)
    artifacts = store.load_all() if load_all else store.load_sources()
    original = artifacts[artifact_type]
    data = deepcopy(original.data)
    mutate(data)
    artifacts[artifact_type] = replace(
        original,
        data=data,
        sha256=canonical_sha256(data),
    )
    return artifacts
