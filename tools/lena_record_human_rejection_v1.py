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

from tools import lena_photo_qa_disposition_v1 as disposition  # noqa: E402

SCHEMA_VERSION = "lena_human_rejection_v1"
RETRY_SCHEMA_VERSION = "lena_bounded_retry_plan_v1"
EXACT_REASON = "Lena identity duplicated on background woman"
CLASSIFICATION = "identity_related_human_rejection"
NEXT_ATTEMPT = (
    "same concept with prompt/scene adjusted to prevent background-person identity duplication"
)
MAX_RETRIES = 1
DEFAULT_OUTPUT_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RejectionError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def rejection_artifact_path(date_str: str, slot_id: str, image_sha: str, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    return output_root / date_str / f"{slot_id}__{image_sha}_human_rejection.json"


def retry_plan_artifact_path(date_str: str, slot_id: str, image_sha: str, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    return output_root / date_str / f"{slot_id}__{image_sha}_bounded_retry_plan.json"


def _validate_source(
    date_str: str, slot_id: str, image_sha: str, disposition_path: Path, disposition_sha: str
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
        "disposition": "accept",
        "reviewer_type": "bounded_visual_provider",
        "provider_called": True,
        "reason_codes": [],
        "side_effects_performed": [],
        "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
    }
    mismatches = [key for key, value in exact.items() if source.get(key) != value]
    provenance = source.get("generation_provenance")
    if mismatches or not isinstance(provenance, dict) or provenance.get("date") != date_str:
        raise RejectionError("QA disposition is not an accepted, fully bound artifact for the requested date/slot/image")

    image_path = _contained_file(source.get("image_path"), "generated image")
    if _sha256_file(image_path) != image_sha:
        raise RejectionError("generated image SHA-256 does not match the requested/disposition image SHA-256")
    decision_path = _contained_file(source.get("decision_artifact_path"), "decision artifact")
    manifest_path = _contained_file(provenance.get("manifest_path"), "result manifest")
    manifest_sha = provenance.get("manifest_sha256")
    if not SHA256_RE.fullmatch(str(manifest_sha)) or _sha256_file(manifest_path) != manifest_sha:
        raise RejectionError("result manifest SHA-256 does not match the disposition binding")

    try:
        decision, candidate = disposition._validate_decision(decision_path)
        image = disposition._inspect_image(image_path, generated=True)
        manifest = disposition._validate_manifest(manifest_path, decision, candidate, image)
    except disposition.BoundaryError as exc:
        raise RejectionError(f"source provenance validation failed: {exc.code}: {exc.detail}") from exc
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


def build_rejection_and_retry_plan(
    *, date_str: str, slot_id: str, image_sha: str, disposition_path: Path,
    disposition_sha: str, publish_packet_path: Path, queue_draft_path: Path,
    reason: str, output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    if reason != EXACT_REASON:
        raise RejectionError(f"operator reason must exactly equal {EXACT_REASON!r}")
    source, decision, manifest, decision_path, manifest_path = _validate_source(
        date_str, slot_id, image_sha, disposition_path.resolve(), disposition_sha
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
        "classification": CLASSIFICATION,
        "retryable": True,
        "retry_attempt": prior_count + 1,
        "retry_cap": MAX_RETRIES,
        "historical_artifacts_modified": [],
    }
    rejection_sha = hashlib.sha256(
        json.dumps(rejection, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    retry = {
        "schema_version": RETRY_SCHEMA_VERSION,
        "influencer_id": "lena",
        "planned_at_utc": now,
        "date": date_str,
        "slot_id": slot_id,
        "retry_attempt": prior_count + 1,
        "retry_cap": MAX_RETRIES,
        "same_concept": True,
        "next_attempt_instruction": NEXT_ATTEMPT,
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
    return rejection, retry, rejection_path, retry_path


def _write_pair(rejection: dict[str, Any], retry: dict[str, Any], rejection_path: Path, retry_path: Path) -> None:
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    if rejection_path.exists() or retry_path.exists():
        raise RejectionError("refusing to overwrite an existing rejection or retry-plan artifact")
    temp_paths: list[Path] = []
    try:
        for target, value in ((rejection_path, rejection), (retry_path, retry)):
            fd, raw = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            os.close(fd)
            temp = Path(raw)
            temp.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            temp_paths.append(temp)
        os.replace(temp_paths[0], rejection_path)
        os.replace(temp_paths[1], retry_path)
    finally:
        for temp in temp_paths:
            temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one bound human rejection and plan one capped retry.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--qa-disposition", type=Path, required=True)
    parser.add_argument("--qa-disposition-sha256", required=True)
    parser.add_argument("--publish-packet", type=Path, required=True)
    parser.add_argument("--queue-draft", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--write-artifacts", action="store_true")
    args = parser.parse_args()
    try:
        rejection, retry, rejection_path, retry_path = build_rejection_and_retry_plan(
            date_str=args.date, slot_id=args.slot, image_sha=args.image_sha256,
            disposition_path=args.qa_disposition, disposition_sha=args.qa_disposition_sha256,
            publish_packet_path=args.publish_packet, queue_draft_path=args.queue_draft,
            reason=args.reason,
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
