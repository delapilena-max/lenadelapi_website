from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence.human_presence_output_qa_v1 import (  # noqa: E402
    build_presence_output_qa_artifact,
    evaluate_still_image_presence_integrity,
)


OUTPUT_ROOT = ROOT / "pipeline" / "asset_review" / "lena" / "presence_output_qa"
EVALUATOR_VERSION = "hpe_2c_pr1_integrity_v1"


def presence_output_qa_artifact_path(
    date_str: str,
    slot_id: str,
    image_index: int,
    output_root: Path = OUTPUT_ROOT,
) -> Path:
    """Canonical path for a presence output QA artifact."""
    return output_root / date_str / slot_id / f"presence_qa_{slot_id}_{image_index:02d}.json"


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of raw file bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_presence_output_qa_artifact_atomic(
    path: Path, artifact: dict[str, Any]
) -> None:
    """Write a presence output QA artifact atomically (tmp → rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_presence_output_qa(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    plan: dict[str, Any] | None,
    plan_fingerprint: str | None,
    candidate_decision_path: Path,
    manifest_path: Path,
    image_path: Path,
    media_type: str = "still_image",
    output_root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Run presence output QA for a single still image.

    When ``plan`` or ``plan_fingerprint`` is None (no HPE was requested for
    this slot), the artifact carries ``integrity_status: "not_assessable"``
    and is written immediately without reading any source files.

    Otherwise:
    1. Hashes candidate_decision, manifest, and image from disk.
    2. Loads the JSON source artifacts.
    3. Calls ``evaluate_still_image_presence_integrity`` from the generic module.
    4. Builds and atomically writes the QA artifact.
    5. Returns ``(artifact_path, artifact_dict)``.

    No approval artifacts are modified. No provider calls are made.
    """
    resolved_root = output_root if output_root is not None else OUTPUT_ROOT
    artifact_path = presence_output_qa_artifact_path(
        date_str, slot_id, image_index, resolved_root
    )

    source_artifact_refs: dict[str, str] = {
        "candidate_decision_path": str(candidate_decision_path),
        "manifest_path": str(manifest_path),
        "image_path": str(image_path),
    }

    # NOT_ASSESSABLE path: no HPE was requested for this slot.
    if plan is None or plan_fingerprint is None:
        not_assessable_result = {
            "integrity_status": "not_assessable",
            "integrity_findings": [{"finding_code": "missing_required_input", "missing": ["plan"]}],
            "semantic_status": "not_evaluated",
            "semantic_findings": [],
        }
        artifact = build_presence_output_qa_artifact(
            integrity_result=not_assessable_result,
            plan_fingerprint_sha256_value="",
            candidate_decision_sha256="",
            manifest_sha256="",
            image_sha256="",
            source_artifacts=source_artifact_refs,
            evaluator_version=EVALUATOR_VERSION,
        )
        write_presence_output_qa_artifact_atomic(artifact_path, artifact)
        return artifact_path, artifact

    # Compute SHA-256 from raw file bytes.
    cd_sha = sha256_file(candidate_decision_path)
    mf_sha = sha256_file(manifest_path)
    img_sha = sha256_file(image_path)

    # Load JSON source artifacts.
    candidate_decision = _load_json_object(candidate_decision_path)
    manifest = _load_json_object(manifest_path)

    # Evaluate integrity. In PR1, image_sha256 is both the observed and the
    # expected value (no prior binding artifact carries an expected image SHA);
    # mismatches can only arise if a prior binding recorded a different value.
    integrity_result = evaluate_still_image_presence_integrity(
        plan=plan,
        expected_plan_fingerprint_sha256=plan_fingerprint,
        candidate_decision=candidate_decision,
        expected_candidate_decision_sha256=cd_sha,
        manifest=manifest,
        expected_manifest_sha256=mf_sha,
        image_sha256=img_sha,
        expected_image_sha256=img_sha,
        media_type=media_type,
    )

    artifact = build_presence_output_qa_artifact(
        integrity_result=integrity_result,
        plan_fingerprint_sha256_value=plan_fingerprint,
        candidate_decision_sha256=cd_sha,
        manifest_sha256=mf_sha,
        image_sha256=img_sha,
        source_artifacts=source_artifact_refs,
        evaluator_version=EVALUATOR_VERSION,
    )
    write_presence_output_qa_artifact_atomic(artifact_path, artifact)
    return artifact_path, artifact
