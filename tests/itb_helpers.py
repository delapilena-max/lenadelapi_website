from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pipeline.media_properties.interstitial_travel_bureau.contracts import (
    canonical_sha256,
    compilation_fingerprint,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "pipeline" / "media_properties" / "interstitial_travel_bureau"
PILOT_ROOT = PACKAGE_ROOT / "pilots" / "pilot_001"
ARTIFACT_ORDER = (
    "bureau_canon_v1.json",
    "bureau_creative_genome_v1.json",
    "bureau_concept_card_v1.json",
    "bureau_world_dossier_v1.json",
    "bureau_entity_sheet_v1.json",
    "bureau_audio_plan_v1.json",
    "bureau_episode_script_v1.json",
    "bureau_visual_sequence_v1.json",
    "bureau_generation_plan_v1.json",
    "bureau_compiled_request_v1.json",
    "bureau_episode_qa_v1.json",
    "bureau_episode_manifest_v1.json",
    "bureau_continuity_ledger_v1.json",
    "bureau_episode_learning_v1.json",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_pilot(tmp_path: Path) -> Path:
    target = tmp_path / "episode"
    shutil.copytree(PILOT_ROOT, target)
    return target


def refresh_authority_hashes(root: Path) -> None:
    hashes: dict[str, str] = {}
    for filename in ARTIFACT_ORDER:
        path = root / filename
        value = read_json(path)
        for reference in value["upstream_artifacts"]:
            if reference["artifact_id"] in hashes:
                reference["sha256"] = hashes[reference["artifact_id"]]
        if value["artifact_type"] == "bureau_compiled_request_v1":
            for reference in value["source_json_references"]:
                if reference["artifact_id"] in hashes:
                    reference["sha256"] = hashes[reference["artifact_id"]]
            value["deterministic_compilation_fingerprint"] = compilation_fingerprint(value)
        write_json(path, value)
        hashes[value["artifact_id"]] = canonical_sha256(value)


def error_codes(report: dict[str, Any]) -> set[str]:
    return {item["code"] for item in report["errors"]}
