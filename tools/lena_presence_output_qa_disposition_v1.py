from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence.human_presence_output_qa_v1 import (  # noqa: E402
    HumanPresenceOutputQAError,
    SCHEMA_VERSION_V1,
    SCHEMA_VERSION_V2,
    build_presence_output_qa_artifact_v1,
    build_presence_output_qa_artifact_v2,
    evaluate_still_image_presence_integrity,
    validate_presence_output_qa_artifact,
)
from tools.lena_presence_semantic_visual_review_v1 import (  # noqa: E402
    evaluate_hpe_semantic_still_image_presence,
    SEMANTIC_MODEL_NAME,
    SEMANTIC_PROVIDER_NAME,
)


OUTPUT_ROOT = ROOT / "pipeline" / "asset_review" / "lena" / "presence_output_qa"
EVALUATOR_VERSION = "hpe_2c_pr3_integrity_semantic_v1"


class GeneratedAssetQaLifecycleError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


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
) -> tuple[Path, dict[str, Any], bool]:
    """Write a presence output QA artifact atomically without silent overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload_bytes = (payload + "\n").encode("utf-8")
    if path.exists():
        existing = path.read_bytes()
        if existing == payload_bytes:
            return path, json.loads(existing), False
        raise GeneratedAssetQaLifecycleError(
            "artifact_already_exists",
            f"refusing to overwrite existing artifact with different content: {path}",
        )
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(payload_bytes)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return path, artifact, True


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


def _semantic_not_evaluated() -> dict[str, Any]:
    return {
        "semantic_status": "not_evaluated",
        "semantic_findings": [],
        "semantic_result_provenance": None,
        "semantic_error": None,
        "_plan_values": {},
    }


def _semantic_not_assessable() -> dict[str, Any]:
    return {
        "semantic_status": "not_assessable",
        "semantic_findings": [],
        "semantic_result_provenance": None,
        "semantic_error": None,
        "_plan_values": {},
    }


def _semantic_error(error_code: str, error_message: str) -> dict[str, Any]:
    return {
        "semantic_status": "error",
        "semantic_findings": [],
        "semantic_result_provenance": None,
        "semantic_error": {
            "error_code": error_code,
            "error_message": error_message[:500],
        },
        "_plan_values": {},
    }


def _integrity_result_not_requested(source_artifacts: dict[str, str | None]) -> dict[str, Any]:
    return {
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
    live_presence_semantic_review: bool = False,
    semantic_provider: Any | None = None,
    semantic_timeout_seconds: float = 30.0,
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
        integrity_result = _integrity_result_not_requested(source_artifacts)
        artifact = build_presence_output_qa_artifact_v2(
            integrity_result=integrity_result,
            semantic_result=_semantic_not_evaluated(),
            source_artifacts=source_artifacts,
            evaluator_version=EVALUATOR_VERSION,
            generated_at_utc=evaluated_at_utc,
        )
        validated = validate_presence_output_qa_artifact(artifact)
        path, written_artifact, _ = write_presence_output_qa_artifact_atomic(artifact_path, validated)
        return path, written_artifact

    try:
        cd_sha = sha256_file(candidate_decision_path)
        mf_sha = sha256_file(manifest_path)
        img_sha = sha256_file(image_path)
        candidate_decision = _load_json_object(candidate_decision_path)
        manifest = _load_json_object(manifest_path)
        expected_plan_fingerprint = _extract_expected_plan_fingerprint(candidate_decision)
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
    except HumanPresenceOutputQAError as exc:
        if exc.code == "presence_output_unsupported_media":
            semantic_result = _semantic_not_assessable()
            artifact = build_presence_output_qa_artifact_v2(
                integrity_result=_integrity_result_not_requested(source_artifacts),
                semantic_result=semantic_result,
                source_artifacts=source_artifacts,
                evaluator_version=EVALUATOR_VERSION,
                generated_at_utc=evaluated_at_utc,
            )
            validated = validate_presence_output_qa_artifact(artifact)
            path, written_artifact, _ = write_presence_output_qa_artifact_atomic(artifact_path, validated)
            return path, written_artifact
        raise

    if semantic_provider is None:
        semantic_provider = evaluate_hpe_semantic_still_image_presence

    semantic_result = _semantic_not_evaluated()
    if live_presence_semantic_review:
        if integrity_result["integrity_status"] == "invalid":
            semantic_result = _semantic_not_assessable()
        else:
            semantic_result = semantic_provider(
                plan=plan,
                image_path=image_path,
                image_sha256=img_sha,
                image_index=image_index,
                provider=SEMANTIC_PROVIDER_NAME,
                model=SEMANTIC_MODEL_NAME,
                timeout_seconds=semantic_timeout_seconds,
            )

    artifact = build_presence_output_qa_artifact_v2(
        integrity_result=integrity_result,
        semantic_result=semantic_result,
        source_artifacts=source_artifacts,
        evaluator_version=EVALUATOR_VERSION,
        generated_at_utc=evaluated_at_utc,
    )
    validated = validate_presence_output_qa_artifact(artifact)
    path, written_artifact, _ = write_presence_output_qa_artifact_atomic(artifact_path, validated)
    return path, written_artifact
