from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import lena_human_rejection_gate_v1 as rejection_gate  # noqa: E402
from tools import lena_photo_qa_disposition_v1 as disposition  # noqa: E402

SCHEMA_VERSION = "lena_human_rejection_v1"
RETRY_SCHEMA_VERSION = "lena_bounded_retry_plan_v1"
RETRY_CORRECTION_SCHEMA_VERSION = "lena_bounded_retry_plan_correction_v1"
EXACT_REASON = "Lena identity duplicated on background woman"
CLASSIFICATION = "identity_related_human_rejection"
NEXT_ATTEMPT = (
    "same concept with prompt/scene adjusted to prevent background-person identity duplication"
)
MAX_RETRIES = 1
DEFAULT_OUTPUT_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BACKGROUND_IDENTITY_REASON_CODE = "background_identity_duplication"
HAIR_CROWN_REASON_CODE = "hair_crown_forelock_artifact"
CORRECTION_CONTRACTS: dict[str, dict[str, Any]] = {
    BACKGROUND_IDENTITY_REASON_CODE: {
        "reason_code": BACKGROUND_IDENTITY_REASON_CODE,
        "operator_reason": EXACT_REASON,
        "classification": CLASSIFICATION,
        "mutation_type": "prevent_duplicated_background_identity",
        "correction_scope": "background_identity_only",
        "next_attempt_instruction": NEXT_ATTEMPT,
        "deterministic_qa_status_required": "accept",
        "deterministic_qa_blocker": None,
        "missing_immutable_provenance": [],
    },
    HAIR_CROWN_REASON_CODE: {
        "reason_code": HAIR_CROWN_REASON_CODE,
        "operator_reason": "Hair crown contains an unwanted raised forelock or vertical tuft",
        "classification": "visual_artifact_human_rejection",
        "mutation_type": "correct_hair_crown_forelock",
        "correction_scope": "hair_only",
        "next_attempt_instruction": "same concept with only the crown/forelock hair artifact corrected",
        "deterministic_qa_status_required": "blocked",
        "deterministic_qa_blocker": "generation_manifest_defect",
        "missing_immutable_provenance": [
            "expression_gaze_id",
            "expression_gaze_label",
            "expression_text",
        ],
    },
}


class RejectionError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _serialize_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RejectionError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RejectionError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RejectionError(f"{label} must be a JSON object: {path}")
    return value


def _contained_file(raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise RejectionError(f"{label} must be a nonempty path")
    path = Path(raw)
    path = path if path.is_absolute() else ROOT / path
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(ROOT.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise RejectionError(f"{label} must be an existing repository-contained file: {path}") from exc
    if not resolved.is_file():
        raise RejectionError(f"{label} must be a file: {resolved}")
    return resolved


def _load_repo_json(path: Path, label: str) -> dict[str, Any]:
    return _read_object(_contained_file(str(path), label), label)


def correction_contract_for_reason(reason: str, reason_code: str | None = None) -> dict[str, Any]:
    if reason_code is None:
        matches = [
            contract
            for contract in CORRECTION_CONTRACTS.values()
            if contract["operator_reason"] == reason
        ]
        if len(matches) != 1:
            raise RejectionError("operator reason does not match any allowlisted correction contract")
        return matches[0]
    contract = CORRECTION_CONTRACTS.get(reason_code)
    if contract is None:
        raise RejectionError(f"unknown rejection reason code: {reason_code!r}")
    if reason != contract["operator_reason"]:
        raise RejectionError(
            f"operator reason must exactly equal {contract['operator_reason']!r} for reason_code {reason_code!r}"
        )
    return contract


def rejection_artifact_path(date_str: str, slot_id: str, image_sha: str, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    return output_root / date_str / f"{slot_id}__{image_sha}_human_rejection.json"


def retry_plan_artifact_path(date_str: str, slot_id: str, image_sha: str, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    return output_root / date_str / f"{slot_id}__{image_sha}_bounded_retry_plan.json"


def retry_plan_correction_artifact_path(date_str: str, slot_id: str, image_sha: str, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    return output_root / date_str / f"{slot_id}__{image_sha}_bounded_retry_plan_correction.json"


def _validate_source(
    date_str: str, slot_id: str, image_sha: str, disposition_path: Path, disposition_sha: str,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path]:
    if not SHA256_RE.fullmatch(image_sha):
        raise RejectionError("image_sha256 must be exactly 64 lowercase hexadecimal characters")
    if not SHA256_RE.fullmatch(disposition_sha) or _sha256_file(disposition_path) != disposition_sha:
        raise RejectionError("QA disposition SHA-256 does not match the expected artifact bytes")
    source = _read_object(disposition_path, "QA disposition")
    expected_path = disposition.disposition_artifact_path(source).resolve()
    if disposition_path.resolve() != expected_path:
        raise RejectionError(f"QA disposition path does not match its canonical slot/image binding: {expected_path}")
    exact = {
        "schema_version": disposition.SCHEMA_VERSION,
        "influencer_id": "lena",
        "slot_id": slot_id,
        "image_sha256": image_sha,
        "side_effects_performed": [],
    }
    mismatches = [key for key, value in exact.items() if source.get(key) != value]
    provenance = source.get("generation_provenance")
    if mismatches or not isinstance(provenance, dict) or provenance.get("date") != date_str:
        raise RejectionError("QA disposition is not a fully bound artifact for the requested date/slot/image")
    if contract["deterministic_qa_status_required"] == "accept":
        accepted = {
            "disposition": "accept",
            "reviewer_type": "bounded_visual_provider",
            "provider_called": True,
            "reason_codes": [],
            "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
        }
        if [key for key, value in accepted.items() if source.get(key) != value]:
            raise RejectionError("QA disposition is not an accepted, fully bound artifact for the requested date/slot/image")
    else:
        if source.get("disposition") != contract["deterministic_qa_status_required"]:
            raise RejectionError("QA disposition status does not match the correction contract")
        if source.get("hard_stop_reason") != contract["deterministic_qa_blocker"]:
            raise RejectionError("QA disposition blocker does not match the correction contract")
        qa_inputs = source.get("qa_inputs")
        if not isinstance(qa_inputs, dict):
            raise RejectionError("QA disposition qa_inputs must record the blocked provenance context")
        missing = qa_inputs.get("missing_immutable_provenance")
        if missing != contract["missing_immutable_provenance"]:
            raise RejectionError("QA disposition missing immutable provenance does not match the correction contract")

    image_path = _contained_file(source.get("image_path"), "generated image")
    if _sha256_file(image_path) != image_sha:
        raise RejectionError("generated image SHA-256 does not match the requested/disposition image SHA-256")
    decision_path = _contained_file(source.get("decision_artifact_path"), "decision artifact")
    manifest_path = _contained_file(provenance.get("manifest_path"), "result manifest")
    manifest_sha = provenance.get("manifest_sha256")
    if not SHA256_RE.fullmatch(str(manifest_sha)) or _sha256_file(manifest_path) != manifest_sha:
        raise RejectionError("result manifest SHA-256 does not match the disposition binding")

    decision, candidate = disposition._validate_decision(decision_path)
    image = disposition._inspect_image(image_path, generated=True)
    try:
        manifest = disposition._validate_manifest(manifest_path, decision, candidate, image)
    except disposition.BoundaryError as exc:
        if contract["deterministic_qa_status_required"] != "blocked":
            raise RejectionError(f"source provenance validation failed: {exc.code}: {exc.detail}") from exc
        manifest = _read_object(manifest_path, "result manifest")
    decision_fingerprint = source.get("decision_fingerprint_sha256")
    if (
        decision.get("as_of_date") != date_str
        or candidate.get("slot_id") != slot_id
        or decision.get("decision_fingerprint_sha256") != decision_fingerprint
        or manifest.get("provider_job_id") != provenance.get("provider_job_id")
        or manifest.get("provider_status") != provenance.get("provider_status")
        or manifest.get("prompt_sha256") != source.get("prompt_sha256")
        or manifest.get("saved_image_path") != str(image_path)
    ):
        raise RejectionError("decision, manifest, image, or provider job binding does not match the QA disposition")
    return source, decision, manifest, decision_path, manifest_path


def _validate_publish_packet_and_queue_draft(
    *,
    date_str: str,
    slot_id: str,
    image_sha: str,
    publish_packet_path: Path,
    queue_draft_path: Path,
    disposition_path: Path,
    source: dict[str, Any],
    decision: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[Path, str, Path, str]:
    publish_packet_path = _contained_file(str(publish_packet_path), "publish packet")
    queue_draft_path = _contained_file(str(queue_draft_path), "queue draft")
    publish_packet_sha = _sha256_file(publish_packet_path)
    queue_draft_sha = _sha256_file(queue_draft_path)
    queue_draft = _load_repo_json(queue_draft_path, "queue draft")

    if queue_draft.get("post_id") != slot_id or queue_draft.get("slot_id") != slot_id:
        raise RejectionError("queue draft post_id/slot_id does not match the requested slot")
    if queue_draft.get("approved_for_live_publish") is not False:
        raise RejectionError("queue draft approved_for_live_publish must still be false")
    if queue_draft.get("operator_review_required") is not True:
        raise RejectionError("queue draft operator_review_required must still be true")

    metadata = queue_draft.get("metadata")
    if not isinstance(metadata, dict):
        raise RejectionError("queue draft metadata must be a JSON object")
    if metadata.get("queue_draft_only") is not True:
        raise RejectionError("queue draft metadata.queue_draft_only must be true")
    if metadata.get("source_date") != date_str or metadata.get("source_slot_id") != slot_id:
        raise RejectionError("queue draft source_date/source_slot_id does not match the requested slot lineage")
    if metadata.get("publish_packet_path") != str(publish_packet_path):
        raise RejectionError("queue draft metadata.publish_packet_path does not match the explicit publish packet input")
    if metadata.get("qa_path") != str(disposition_path):
        raise RejectionError("queue draft metadata.qa_path does not match the explicit QA disposition input")
    if metadata.get("qa_overall") != "pass":
        raise RejectionError("queue draft metadata.qa_overall must be 'pass'")

    media_type = str(queue_draft.get("media_type") or "").lower().strip()
    if media_type not in {"photo", "image"}:
        raise RejectionError("queue draft media_type must be photo/image for this human rejection flow")
    image_path = _contained_file(queue_draft.get("media_path"), "queue draft media path")
    if image_path != _contained_file(source.get("image_path"), "generated image"):
        raise RejectionError("queue draft media_path does not match the QA disposition image path")
    if _sha256_file(image_path) != image_sha:
        raise RejectionError("queue draft media path bytes do not match the requested image SHA-256")

    decision_fingerprint = source.get("decision_fingerprint_sha256")
    if decision.get("decision_fingerprint_sha256") != decision_fingerprint:
        raise RejectionError("decision fingerprint lineage drifted before queue-draft validation")
    if manifest.get("saved_image_path") != str(image_path):
        raise RejectionError("manifest saved_image_path does not match the queue draft media path")

    return publish_packet_path, publish_packet_sha, queue_draft_path, queue_draft_sha


def _count_lineage_rejections(output_root: Path, slot_id: str, decision_fingerprint: str) -> int:
    count = 0
    for path in output_root.glob(f"*/{slot_id}__*_human_rejection.json"):
        value = _read_object(path, "existing human rejection")
        if (
            value.get("schema_version") == SCHEMA_VERSION
            and value.get("slot_id") == slot_id
            and value.get("decision_fingerprint_sha256") == decision_fingerprint
        ):
            count += 1
    return count


def _compose_retry_plan(
    *,
    now: str,
    date_str: str,
    slot_id: str,
    retry_attempt: int,
    decision_path: Path,
    decision_fingerprint: str,
    publish_packet_path: Path,
    publish_packet_sha: str,
    queue_draft_path: Path,
    queue_draft_sha: str,
    manifest_path: Path,
    manifest_sha: str,
    image_path: str,
    image_sha: str,
    manifest: dict[str, Any],
    rejection_path: Path,
    rejection_sha: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": RETRY_SCHEMA_VERSION,
        "influencer_id": "lena",
        "planned_at_utc": now,
        "date": date_str,
        "slot_id": slot_id,
        "retry_attempt": retry_attempt,
        "retry_cap": MAX_RETRIES,
        "same_concept": True,
        "next_attempt_instruction": contract["next_attempt_instruction"],
        "reason_code": contract["reason_code"],
        "mutation_type": contract["mutation_type"],
        "correction_scope": contract["correction_scope"],
        "deterministic_qa_status": contract["deterministic_qa_status_required"],
        "deterministic_qa_blocker": contract["deterministic_qa_blocker"],
        "missing_immutable_provenance": list(contract["missing_immutable_provenance"]),
        "original_decision_artifact_path": str(decision_path),
        "original_decision_artifact_sha256": _sha256_file(decision_path),
        "decision_fingerprint_sha256": decision_fingerprint,
        "original_publish_packet_path": str(publish_packet_path),
        "original_publish_packet_sha256": publish_packet_sha,
        "original_queue_draft_path": str(queue_draft_path),
        "original_queue_draft_sha256": queue_draft_sha,
        "original_manifest_path": str(manifest_path),
        "original_manifest_sha256": manifest_sha,
        "original_image_path": image_path,
        "original_image_sha256": image_sha,
        "original_provider_job_evidence": {
            "provider": manifest["provider"],
            "provider_job_id": manifest["provider_job_id"],
            "provider_status": manifest["provider_status"],
            "job_type": manifest["job_type"],
        },
        "human_rejection_artifact_path": str(rejection_path.resolve()),
        "human_rejection_artifact_sha256": rejection_sha,
        "action": "plan_only_no_provider_call",
        "forbidden_side_effects": [
            "higgsfield", "anthropic", "queue", "approval", "promotion", "publish",
            "r2", "analytics", ".env", "cleanup", "historical_evidence_mutation",
        ],
    }


def build_rejection_and_retry_plan(
    *, date_str: str, slot_id: str, image_sha: str, disposition_path: Path,
    disposition_sha: str, publish_packet_path: Path, queue_draft_path: Path,
    reason: str, reason_code: str | None = None, output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    contract = correction_contract_for_reason(reason, reason_code)
    source, decision, manifest, decision_path, manifest_path = _validate_source(
        date_str, slot_id, image_sha, disposition_path.resolve(), disposition_sha, contract
    )
    publish_packet_path, publish_packet_sha, queue_draft_path, queue_draft_sha = _validate_publish_packet_and_queue_draft(
        date_str=date_str,
        slot_id=slot_id,
        image_sha=image_sha,
        publish_packet_path=publish_packet_path,
        queue_draft_path=queue_draft_path,
        disposition_path=disposition_path.resolve(),
        source=source,
        decision=decision,
        manifest=manifest,
    )
    rejection_path = rejection_artifact_path(date_str, slot_id, image_sha, output_root)
    retry_path = retry_plan_artifact_path(date_str, slot_id, image_sha, output_root)
    if rejection_path.exists() or retry_path.exists():
        raise RejectionError("rejection or retry-plan artifact already exists for this exact image lineage")
    prior_count = _count_lineage_rejections(output_root, slot_id, source["decision_fingerprint_sha256"])
    if prior_count >= MAX_RETRIES:
        raise RejectionError("bounded retry cap exceeded for this exact concept/slot/image lineage")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rejection = {
        "schema_version": SCHEMA_VERSION,
        "influencer_id": "lena",
        "recorded_at_utc": now,
        "date": date_str,
        "slot_id": slot_id,
        "image_sha256": image_sha,
        "publish_packet_path": str(publish_packet_path),
        "publish_packet_sha256": publish_packet_sha,
        "queue_draft_path": str(queue_draft_path),
        "queue_draft_sha256": queue_draft_sha,
        "qa_disposition_artifact_path": str(disposition_path.resolve()),
        "qa_disposition_artifact_sha256": disposition_sha,
        "decision_artifact_path": str(decision_path),
        "decision_fingerprint_sha256": source["decision_fingerprint_sha256"],
        "operator_reason": reason,
        "reason_code": contract["reason_code"],
        "classification": contract["classification"],
        "mutation_type": contract["mutation_type"],
        "correction_scope": contract["correction_scope"],
        "deterministic_qa_status": contract["deterministic_qa_status_required"],
        "deterministic_qa_blocker": contract["deterministic_qa_blocker"],
        "missing_immutable_provenance": list(contract["missing_immutable_provenance"]),
        "retryable": True,
        "retry_attempt": prior_count + 1,
        "retry_cap": MAX_RETRIES,
        "historical_artifacts_modified": [],
    }
    rejection_sha = hashlib.sha256(_serialize_json_bytes(rejection)).hexdigest()
    retry = _compose_retry_plan(
        now=now,
        date_str=date_str,
        slot_id=slot_id,
        retry_attempt=prior_count + 1,
        decision_path=decision_path,
        decision_fingerprint=source["decision_fingerprint_sha256"],
        publish_packet_path=publish_packet_path,
        publish_packet_sha=publish_packet_sha,
        queue_draft_path=queue_draft_path,
        queue_draft_sha=queue_draft_sha,
        manifest_path=manifest_path,
        manifest_sha=source["generation_provenance"]["manifest_sha256"],
        image_path=source["image_path"],
        image_sha=image_sha,
        manifest=manifest,
        rejection_path=rejection_path,
        rejection_sha=rejection_sha,
        contract=contract,
    )
    return rejection, retry, rejection_path, retry_path


def build_retry_plan_sha_correction(
    *, rejection_artifact_path: Path, invalid_retry_plan_path: Path,
) -> tuple[dict[str, Any], Path]:
    rejection_artifact_path = _contained_file(str(rejection_artifact_path), "existing rejection artifact")
    invalid_retry_plan_path = _contained_file(str(invalid_retry_plan_path), "existing invalid retry plan")
    rejection = _read_object(rejection_artifact_path, "existing rejection artifact")
    if rejection.get("schema_version") != SCHEMA_VERSION:
        raise RejectionError("existing rejection artifact schema_version is invalid for retry-plan recovery")
    date_str = str(rejection.get("date") or "")
    slot_id = str(rejection.get("slot_id") or "")
    image_sha = str(rejection.get("image_sha256") or "")
    if not date_str or not slot_id or not SHA256_RE.fullmatch(image_sha):
        raise RejectionError("existing rejection artifact date/slot/image binding is incomplete")

    qa_path = _contained_file(rejection.get("qa_disposition_artifact_path"), "QA disposition artifact")
    qa = _read_object(qa_path, "QA disposition artifact")
    image_path = _contained_file(qa.get("image_path"), "generated image")
    publish_packet_path = _contained_file(rejection.get("publish_packet_path"), "publish packet")
    queue_draft_path = _contained_file(rejection.get("queue_draft_path"), "queue draft")
    try:
        rejection_gate._validate_artifact(
            rejection_artifact_path,
            date_str=date_str,
            slot_id=slot_id,
            image_path=image_path,
            publish_packet_path=publish_packet_path,
            queue_draft_path=queue_draft_path,
            qa_path=qa_path,
        )
    except rejection_gate.HumanRejectionGateError as exc:
        raise RejectionError(f"existing rejection artifact is not valid for retry-plan recovery: {exc}") from exc

    contract = correction_contract_for_reason(
        str(rejection.get("operator_reason") or ""),
        str(rejection.get("reason_code") or "") or None,
    )
    source, decision, manifest, decision_path, manifest_path = _validate_source(
        date_str, slot_id, image_sha, qa_path, str(rejection["qa_disposition_artifact_sha256"]), contract
    )
    publish_packet_path, publish_packet_sha, queue_draft_path, queue_draft_sha = _validate_publish_packet_and_queue_draft(
        date_str=date_str,
        slot_id=slot_id,
        image_sha=image_sha,
        publish_packet_path=publish_packet_path,
        queue_draft_path=queue_draft_path,
        disposition_path=qa_path,
        source=source,
        decision=decision,
        manifest=manifest,
    )

    expected_retry_path = retry_plan_artifact_path(date_str, slot_id, image_sha, invalid_retry_plan_path.parents[1]).resolve()
    if invalid_retry_plan_path.resolve() != expected_retry_path:
        raise RejectionError("existing invalid retry plan path does not match the canonical lineage binding")
    invalid_retry = _read_object(invalid_retry_plan_path, "existing invalid retry plan")
    if invalid_retry.get("schema_version") != RETRY_SCHEMA_VERSION:
        raise RejectionError("existing invalid retry plan schema_version is invalid for retry-plan recovery")
    if invalid_retry.get("retry_attempt") != 1 or invalid_retry.get("retry_cap") != 1:
        raise RejectionError("existing invalid retry plan retry attempt/cap must remain exactly 1/1")
    planned_at_utc = str(invalid_retry.get("planned_at_utc") or "")
    if not planned_at_utc:
        raise RejectionError("existing invalid retry plan planned_at_utc is required for retry-plan recovery")

    actual_rejection_sha = _sha256_file(rejection_artifact_path)
    embedded_rejection_sha = str(invalid_retry.get("human_rejection_artifact_sha256") or "")
    if not SHA256_RE.fullmatch(embedded_rejection_sha):
        raise RejectionError("existing invalid retry plan human_rejection_artifact_sha256 is malformed")
    if embedded_rejection_sha == actual_rejection_sha:
        raise RejectionError("existing invalid retry plan already matches the exact rejection file SHA-256")

    expected_retry = _compose_retry_plan(
        now=planned_at_utc,
        date_str=date_str,
        slot_id=slot_id,
        retry_attempt=1,
        decision_path=decision_path,
        decision_fingerprint=source["decision_fingerprint_sha256"],
        publish_packet_path=publish_packet_path,
        publish_packet_sha=publish_packet_sha,
        queue_draft_path=queue_draft_path,
        queue_draft_sha=queue_draft_sha,
        manifest_path=manifest_path,
        manifest_sha=source["generation_provenance"]["manifest_sha256"],
        image_path=source["image_path"],
        image_sha=image_sha,
        manifest=manifest,
        rejection_path=rejection_artifact_path,
        rejection_sha=actual_rejection_sha,
        contract=contract,
    )
    normalized_retry = dict(invalid_retry)
    normalized_retry["human_rejection_artifact_sha256"] = actual_rejection_sha
    if normalized_retry != expected_retry:
        keys = sorted(set(normalized_retry) | set(expected_retry))
        mismatches = [key for key in keys if normalized_retry.get(key) != expected_retry.get(key)]
        raise RejectionError(
            "retry-plan recovery is only allowed for the demonstrated rejection-file SHA mismatch; "
            f"other retry-plan defects are present: {', '.join(mismatches)}"
        )

    correction_path = retry_plan_correction_artifact_path(
        date_str, slot_id, image_sha, invalid_retry_plan_path.parents[1]
    )
    if correction_path.exists():
        raise RejectionError("retry-plan correction artifact already exists for this exact image lineage")
    correction = {
        "schema_version": RETRY_CORRECTION_SCHEMA_VERSION,
        "influencer_id": "lena",
        "corrected_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "date": date_str,
        "slot_id": slot_id,
        "retry_attempt": 1,
        "retry_cap": 1,
        "same_concept": True,
        "next_attempt_instruction": contract["next_attempt_instruction"],
        "reason_code": contract["reason_code"],
        "mutation_type": contract["mutation_type"],
        "correction_scope": contract["correction_scope"],
        "deterministic_qa_status": contract["deterministic_qa_status_required"],
        "deterministic_qa_blocker": contract["deterministic_qa_blocker"],
        "missing_immutable_provenance": list(contract["missing_immutable_provenance"]),
        "original_decision_artifact_path": str(decision_path),
        "original_decision_artifact_sha256": _sha256_file(decision_path),
        "decision_fingerprint_sha256": source["decision_fingerprint_sha256"],
        "original_publish_packet_path": str(publish_packet_path),
        "original_publish_packet_sha256": publish_packet_sha,
        "original_queue_draft_path": str(queue_draft_path),
        "original_queue_draft_sha256": queue_draft_sha,
        "original_manifest_path": str(manifest_path),
        "original_manifest_sha256": source["generation_provenance"]["manifest_sha256"],
        "original_image_path": source["image_path"],
        "original_image_sha256": image_sha,
        "original_provider_job_evidence": expected_retry["original_provider_job_evidence"],
        "valid_human_rejection_artifact_path": str(rejection_artifact_path.resolve()),
        "valid_human_rejection_artifact_sha256": actual_rejection_sha,
        "invalid_retry_plan_artifact_path": str(invalid_retry_plan_path.resolve()),
        "invalid_retry_plan_artifact_sha256": _sha256_file(invalid_retry_plan_path),
        "invalid_retry_plan_embedded_rejection_sha256": embedded_rejection_sha,
        "supersedes_invalid_retry_plan_for_execution_only": True,
        "preserves_immutable_historical_artifacts": True,
        "action": "correction_record_only_no_provider_call",
        "recovery_reason": "human_rejection_artifact_sha256_mismatch_only",
        "historical_artifacts_modified": [],
        "forbidden_side_effects": expected_retry["forbidden_side_effects"],
    }
    return correction, correction_path


def _write_json_artifact(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RejectionError(f"refusing to overwrite an existing artifact: {path}")
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(raw)
    try:
        temp.write_bytes(_serialize_json_bytes(value))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _write_pair(rejection: dict[str, Any], retry: dict[str, Any], rejection_path: Path, retry_path: Path) -> None:
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    if rejection_path.exists() or retry_path.exists():
        raise RejectionError("refusing to overwrite an existing rejection or retry-plan artifact")
    _write_json_artifact(rejection_path, rejection)
    try:
        _write_json_artifact(retry_path, retry)
    except Exception:
        rejection_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one bound human rejection and plan one capped retry.")
    parser.add_argument("--date")
    parser.add_argument("--slot")
    parser.add_argument("--image-sha256")
    parser.add_argument("--qa-disposition", type=Path)
    parser.add_argument("--qa-disposition-sha256")
    parser.add_argument("--publish-packet", type=Path)
    parser.add_argument("--queue-draft", type=Path)
    parser.add_argument("--reason")
    parser.add_argument("--reason-code")
    parser.add_argument("--recover-existing-retry-plan-sha-mismatch", action="store_true")
    parser.add_argument("--existing-rejection-artifact", type=Path)
    parser.add_argument("--existing-invalid-retry-plan", type=Path)
    parser.add_argument("--write-artifacts", action="store_true")
    args = parser.parse_args()
    try:
        if args.recover_existing_retry_plan_sha_mismatch:
            if args.existing_rejection_artifact is None or args.existing_invalid_retry_plan is None:
                raise RejectionError(
                    "recovery mode requires --existing-rejection-artifact and --existing-invalid-retry-plan"
                )
            correction, correction_path = build_retry_plan_sha_correction(
                rejection_artifact_path=args.existing_rejection_artifact,
                invalid_retry_plan_path=args.existing_invalid_retry_plan,
            )
            if args.write_artifacts:
                _write_json_artifact(correction_path, correction)
            print(json.dumps({
                "status": "recovery_planned" if not args.write_artifacts else "recovery_written",
                "retry_plan_correction_artifact_path": str(correction_path.resolve()),
                "retry_attempt": correction["retry_attempt"],
                "retry_cap": correction["retry_cap"],
            }, sort_keys=True))
        else:
            required = {
                "--date": args.date,
                "--slot": args.slot,
                "--image-sha256": args.image_sha256,
                "--qa-disposition": args.qa_disposition,
                "--qa-disposition-sha256": args.qa_disposition_sha256,
                "--publish-packet": args.publish_packet,
                "--queue-draft": args.queue_draft,
                "--reason": args.reason,
            }
            missing = [flag for flag, value in required.items() if value is None]
            if missing:
                raise RejectionError("record mode is missing required arguments: " + ", ".join(missing))
            rejection, retry, rejection_path, retry_path = build_rejection_and_retry_plan(
                date_str=args.date, slot_id=args.slot, image_sha=args.image_sha256,
                disposition_path=args.qa_disposition, disposition_sha=args.qa_disposition_sha256,
                publish_packet_path=args.publish_packet, queue_draft_path=args.queue_draft,
                reason=args.reason, reason_code=args.reason_code,
            )
            if args.write_artifacts:
                _write_pair(rejection, retry, rejection_path, retry_path)
            print(json.dumps({
                "status": "planned" if not args.write_artifacts else "written",
                "rejection_artifact_path": str(rejection_path.resolve()),
                "retry_plan_artifact_path": str(retry_path.resolve()),
                "retry_attempt": retry["retry_attempt"],
                "retry_cap": retry["retry_cap"],
            }, sort_keys=True))
        return 0
    except RejectionError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
