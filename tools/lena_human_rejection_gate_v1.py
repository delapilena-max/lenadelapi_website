from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REJECTION_ROOT = ROOT / "pipeline" / "asset_review" / "lena"

SCHEMA_VERSION = "lena_human_rejection_v1"
QA_SCHEMA_VERSION = "lena_photo_qa_disposition_v1"
CLASSIFICATION = "identity_related_human_rejection"
EXACT_REASON = "Lena identity duplicated on background woman"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HumanRejectionGateError(RuntimeError):
    """Raised when a matching human-rejection artifact exists and must block."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise HumanRejectionGateError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HumanRejectionGateError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HumanRejectionGateError(f"{label} must be a JSON object: {path}")
    return value


def _require_sha256(raw: Any, label: str) -> str:
    value = str(raw or "")
    if not SHA256_RE.fullmatch(value):
        raise HumanRejectionGateError(f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_exact_path(raw: Any, expected: Path, label: str) -> None:
    if str(raw or "") != str(expected):
        raise HumanRejectionGateError(f"{label} {raw!r} does not match the exact required path {str(expected)!r}")


def _require_exact_file_sha(raw: Any, path: Path, label: str) -> None:
    expected_sha = _sha256_file(path)
    actual_sha = _require_sha256(raw, label)
    if actual_sha != expected_sha:
        raise HumanRejectionGateError(
            f"{label} {actual_sha!r} does not match the current file bytes at {path} ({expected_sha!r})"
        )


def _validate_artifact(
    artifact_path: Path,
    *,
    date_str: str,
    slot_id: str,
    image_path: Path,
    publish_packet_path: Path,
    queue_draft_path: Path,
    qa_path: Path,
) -> None:
    artifact = _load_json_object(artifact_path, "human rejection artifact")
    image_sha = _sha256_file(image_path)
    packet_path = publish_packet_path.resolve()
    draft_path = queue_draft_path.resolve()
    qa_path = qa_path.resolve()
    image_path = image_path.resolve()

    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise HumanRejectionGateError(
            f"human rejection artifact has unsupported schema_version {artifact.get('schema_version')!r}"
        )
    if artifact.get("influencer_id") != "lena":
        raise HumanRejectionGateError("human rejection artifact influencer_id must be 'lena'")
    if artifact.get("date") != date_str or artifact.get("slot_id") != slot_id:
        raise HumanRejectionGateError("human rejection artifact date/slot binding does not match this item")
    if artifact.get("image_sha256") != image_sha:
        raise HumanRejectionGateError("human rejection artifact image_sha256 does not match the current media bytes")
    if artifact.get("operator_reason") != EXACT_REASON:
        raise HumanRejectionGateError("human rejection artifact operator_reason does not match the exact required reason")
    if artifact.get("classification") != CLASSIFICATION:
        raise HumanRejectionGateError("human rejection artifact classification is invalid")
    if artifact.get("retryable") is not True:
        raise HumanRejectionGateError("human rejection artifact retryable must be true")
    if artifact.get("retry_attempt") != 1 or artifact.get("retry_cap") != 1:
        raise HumanRejectionGateError("human rejection artifact retry attempt/cap must remain exactly 1/1")
    if artifact.get("historical_artifacts_modified") != []:
        raise HumanRejectionGateError("human rejection artifact historical_artifacts_modified must be an empty list")

    _require_exact_path(artifact.get("publish_packet_path"), packet_path, "publish_packet_path")
    _require_exact_file_sha(artifact.get("publish_packet_sha256"), packet_path, "publish_packet_sha256")
    _require_exact_path(artifact.get("queue_draft_path"), draft_path, "queue_draft_path")
    _require_exact_file_sha(artifact.get("queue_draft_sha256"), draft_path, "queue_draft_sha256")
    _require_exact_path(artifact.get("qa_disposition_artifact_path"), qa_path, "qa_disposition_artifact_path")
    _require_exact_file_sha(
        artifact.get("qa_disposition_artifact_sha256"),
        qa_path,
        "qa_disposition_artifact_sha256",
    )

    qa = _load_json_object(qa_path, "QA disposition artifact")
    if qa.get("schema_version") != QA_SCHEMA_VERSION:
        raise HumanRejectionGateError(f"QA disposition schema_version {qa.get('schema_version')!r} is invalid")
    if qa.get("influencer_id") != "lena":
        raise HumanRejectionGateError("QA disposition influencer_id must be 'lena'")
    if qa.get("slot_id") != slot_id:
        raise HumanRejectionGateError("QA disposition slot_id does not match this item")
    if qa.get("image_path") != str(image_path):
        raise HumanRejectionGateError("QA disposition image_path does not match the current media path")
    if qa.get("image_sha256") != image_sha:
        raise HumanRejectionGateError("QA disposition image_sha256 does not match the current media bytes")
    if qa.get("disposition") != "accept":
        raise HumanRejectionGateError("QA disposition is not accepted")
    if qa.get("reviewer_type") != "bounded_visual_provider" or qa.get("provider_called") is not True:
        raise HumanRejectionGateError("QA disposition reviewer/provider state is invalid")
    if qa.get("reason_codes") != [] or qa.get("side_effects_performed") != []:
        raise HumanRejectionGateError("QA disposition reason_codes/side_effects_performed must both be empty lists")
    if qa.get("exact_next_allowed_action") != "existing_downstream_qa_and_human_review_gates_only":
        raise HumanRejectionGateError("QA disposition next allowed action is invalid")

    decision_path = Path(str(qa.get("decision_artifact_path") or "")).resolve()
    _require_exact_path(artifact.get("decision_artifact_path"), decision_path, "decision_artifact_path")
    decision = _load_json_object(decision_path, "decision artifact")
    decision_fingerprint = _require_sha256(
        artifact.get("decision_fingerprint_sha256"),
        "decision_fingerprint_sha256",
    )
    if qa.get("decision_fingerprint_sha256") != decision_fingerprint:
        raise HumanRejectionGateError("QA disposition decision_fingerprint_sha256 does not match the rejection artifact")
    if decision.get("as_of_date") != date_str:
        raise HumanRejectionGateError("decision artifact as_of_date does not match this item's date")
    if decision.get("decision_fingerprint_sha256") != decision_fingerprint:
        raise HumanRejectionGateError("decision artifact fingerprint does not match the rejection artifact")

    provenance = qa.get("generation_provenance")
    if not isinstance(provenance, dict):
        raise HumanRejectionGateError("QA disposition generation_provenance must be a JSON object")
    if provenance.get("date") != date_str:
        raise HumanRejectionGateError("QA disposition generation_provenance.date does not match this item's date")
    manifest_path = Path(str(provenance.get("manifest_path") or "")).resolve()
    _require_exact_file_sha(provenance.get("manifest_sha256"), manifest_path, "generation manifest sha256")
    manifest = _load_json_object(manifest_path, "generation manifest")
    if manifest.get("saved_image_path") != str(image_path):
        raise HumanRejectionGateError("generation manifest saved_image_path does not match the current media path")
    if manifest.get("prompt_sha256") != qa.get("prompt_sha256"):
        raise HumanRejectionGateError("generation manifest prompt_sha256 does not match the QA disposition")
    if manifest.get("provider_job_id") != provenance.get("provider_job_id"):
        raise HumanRejectionGateError("generation manifest provider_job_id does not match the QA disposition")
    if manifest.get("provider_status") != provenance.get("provider_status"):
        raise HumanRejectionGateError("generation manifest provider_status does not match the QA disposition")


def assert_no_matching_human_rejection(
    *,
    date_str: str,
    slot_id: str,
    image_path: Path | None,
    publish_packet_path: Path,
    queue_draft_path: Path,
    qa_path: Path,
    artifact_root: Path | None = None,
) -> None:
    if image_path is None:
        return
    artifact_root = artifact_root or DEFAULT_REJECTION_ROOT

    packet_path = publish_packet_path.resolve()
    draft_path = queue_draft_path.resolve()
    qa_path = qa_path.resolve()
    image_path = image_path.resolve()

    candidates = sorted((artifact_root / date_str).glob(f"{slot_id}__*_human_rejection.json"))
    if not candidates:
        return
    if len(candidates) != 1:
        raise HumanRejectionGateError(
            "multiple human rejection artifacts exist for this exact date/slot: "
            + ", ".join(str(path) for path in candidates)
        )

    artifact_path = candidates[0]
    try:
        _validate_artifact(
            artifact_path,
            date_str=date_str,
            slot_id=slot_id,
            image_path=image_path,
            publish_packet_path=packet_path,
            queue_draft_path=draft_path,
            qa_path=qa_path,
        )
    except HumanRejectionGateError as exc:
        raise HumanRejectionGateError(
            f"matching human rejection artifact blocks this item: {artifact_path}: {exc}"
        ) from exc

    raise HumanRejectionGateError(f"matching human rejection artifact blocks this item: {artifact_path}")
