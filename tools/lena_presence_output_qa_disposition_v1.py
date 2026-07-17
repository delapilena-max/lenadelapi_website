from __future__ import annotations

import hashlib
import json
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
    """Canonical path for a presence output QA artifact.

    The path is validated before being returned. The helper rejects traversal,
    absolute paths, empty identifiers, and unreasonable image indexes.
    """

    if not isinstance(date_str, str) or not date_str:
        raise ValueError("date_str must be a non-empty string")
    if not isinstance(slot_id, str) or not slot_id:
        raise ValueError("slot_id must be a non-empty string")
    if not isinstance(image_index, int):
        raise ValueError("image_index must be an integer")
    if image_index < 0 or image_index > 99:
        raise ValueError("image_index must be between 0 and 99 inclusive")

    if not (
        len(date_str) == 10
        and date_str[4] == "-"
        and date_str[7] == "-"
        and date_str.replace("-", "").isdigit()
    ):
        raise ValueError("date_str must use YYYY-MM-DD format")
    if any(sep in date_str for sep in ("/", "\\")) or any(sep in slot_id for sep in ("/", "\\")):
        raise ValueError("date_str and slot_id may not contain path separators")
    if date_str in {".", ".."} or slot_id in {".", ".."}:
        raise ValueError("date_str and slot_id may not be dot-path components")
    if Path(date_str).is_absolute() or Path(slot_id).is_absolute():
        raise ValueError("date_str and slot_id may not be absolute paths")

    resolved_root = Path(output_root).resolve(strict=False)
    candidate = (resolved_root / date_str / slot_id / f"presence_qa_{slot_id}_{image_index:02d}.json").resolve(
        strict=False
    )
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:  # pragma: no cover - defensive path safety
        raise ValueError("resolved artifact path escapes the output root") from exc
    return candidate


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


def _extract_expected_plan_fingerprint(candidate_decision: dict[str, Any]) -> str | None:
    for key in (
        "plan_fingerprint_sha256",
        "expected_plan_fingerprint_sha256",
        "presence_plan_fingerprint_sha256",
    ):
        value = candidate_decision.get(key)
        if isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value):
            return value
    return None


def _source_artifacts(
    *,
    plan_path: str | None,
    candidate_decision_path: Path,
    manifest_path: Path,
    image_path: Path,
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {
        "plan_path": plan_path,
        "candidate_decision_path": str(candidate_decision_path),
        "manifest_path": str(manifest_path),
        "image_path": str(image_path),
    }
    return payload


def run_presence_output_qa(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    plan: dict[str, Any] | None,
    candidate_decision_path: Path,
    manifest_path: Path,
    image_path: Path,
    media_type: str = "still_image",
    output_root: Path | None = None,
    evaluated_at_utc: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Run presence output QA for a single still image.

    When ``plan`` is ``None`` (no HPE was requested for this slot), the
    artifact is written immediately without reading or hashing any source files.

    Otherwise the adapter:
    1. hashes and loads the candidate decision and manifest;
    2. hashes the generated image;
    3. extracts any independently stored expected plan fingerprint if present;
    4. evaluates the integrity bindings;
    5. writes the QA artifact.

    No approval artifacts are modified. No provider calls are made.
    """
    resolved_root = output_root if output_root is not None else OUTPUT_ROOT
    artifact_path = presence_output_qa_artifact_path(date_str, slot_id, image_index, resolved_root)

    source_artifacts = _source_artifacts(
        plan_path=None,
        candidate_decision_path=candidate_decision_path,
        manifest_path=manifest_path,
        image_path=image_path,
    )

    if plan is None:
        not_assessable_result = {
            "integrity_status": "not_assessable",
            "integrity_findings": [{"finding_code": "missing_required_input", "missing": ["plan"]}],
            "semantic_status": "not_evaluated",
            "semantic_findings": [],
            "binding_records": [
                {
                    "binding_name": "plan",
                    "binding_status": "not_assessable",
                    "observed_sha256": None,
                    "expected_sha256": None,
                    "verification_basis": "hpe_not_requested",
                    "source_path": None,
                    "details": {"reason": "hpe_not_requested"},
                },
                {
                    "binding_name": "candidate_decision",
                    "binding_status": "not_assessable",
                    "observed_sha256": None,
                    "expected_sha256": None,
                    "verification_basis": "hpe_not_requested",
                    "source_path": None,
                    "details": {"reason": "hpe_not_requested"},
                },
                {
                    "binding_name": "manifest",
                    "binding_status": "not_assessable",
                    "observed_sha256": None,
                    "expected_sha256": None,
                    "verification_basis": "hpe_not_requested",
                    "source_path": None,
                    "details": {"reason": "hpe_not_requested"},
                },
                {
                    "binding_name": "generated_image",
                    "binding_status": "not_assessable",
                    "observed_sha256": None,
                    "expected_sha256": None,
                    "verification_basis": "hpe_not_requested",
                    "source_path": None,
                    "details": {"reason": "hpe_not_requested"},
                },
            ],
        }
        artifact = build_presence_output_qa_artifact(
            integrity_result=not_assessable_result,
            source_artifacts=source_artifacts,
            evaluator_version=EVALUATOR_VERSION,
            generated_at_utc=evaluated_at_utc,
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

    expected_plan_fingerprint = _extract_expected_plan_fingerprint(candidate_decision)
    plan_source_path = str(candidate_decision_path) if expected_plan_fingerprint else None
    source_artifacts["plan_path"] = plan_source_path

    integrity_result = evaluate_still_image_presence_integrity(
        plan=plan,
        expected_plan_fingerprint_sha256=expected_plan_fingerprint,
        candidate_decision=candidate_decision,
        candidate_decision_sha256=cd_sha,
        expected_candidate_decision_sha256=None,
        manifest=manifest,
        manifest_sha256=mf_sha,
        expected_manifest_sha256=None,
        image_sha256=img_sha,
        expected_image_sha256=None,
        media_type=media_type,
        source_artifacts=source_artifacts,
    )

    artifact = build_presence_output_qa_artifact(
        integrity_result=integrity_result,
        source_artifacts=source_artifacts,
        evaluator_version=EVALUATOR_VERSION,
        generated_at_utc=evaluated_at_utc,
    )
    write_presence_output_qa_artifact_atomic(artifact_path, artifact)
    return artifact_path, artifact
