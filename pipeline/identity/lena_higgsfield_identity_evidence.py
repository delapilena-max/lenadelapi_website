from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from pipeline.identity import lena_higgsfield_identity as identity


class LenaIdentityEvidenceError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_evidence_path(date_str: str, slot_id: str) -> Path:
    return identity.identity_verification_evidence_path(date_str, slot_id)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaIdentityEvidenceError(code, detail)


def _required_string(manifest: dict[str, Any], field_name: str) -> str:
    value = manifest.get(field_name)
    if not isinstance(value, str) or not value:
        raise LenaIdentityEvidenceError(
            f"manifest_{field_name}_missing",
            f"manifest {field_name!r} must be a non-empty string",
        )
    return value


def _inspect_image_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise LenaIdentityEvidenceError(
            "generated_image_invalid",
            f"generated image bytes could not be inspected: {path}: {exc}",
        ) from exc
    return int(width), int(height)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(subvalue) for key, subvalue in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    return True


def _evidence_reuse_fingerprint(evidence: dict[str, Any]) -> dict[str, Any]:
    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): _normalize(subvalue)
                for key, subvalue in value.items()
                if key not in {"verified_at_utc", "created_at_utc"}
            }
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        return value

    return _normalize(evidence)


def _validate_authority_references(
    *,
    reference_authority_artifact: Path,
    reference_authority_sha256: str,
    identity_references: list[tuple[Path, str]],
) -> None:
    if not reference_authority_artifact.is_file():
        raise LenaIdentityEvidenceError(
            "reference_authority_missing",
            f"reference authority artifact is missing: {reference_authority_artifact}",
        )
    observed_authority_sha = sha256_file(reference_authority_artifact)
    if observed_authority_sha != reference_authority_sha256:
        raise LenaIdentityEvidenceError(
            "reference_authority_sha_mismatch",
            "reference authority SHA-256 does not match the bound value",
        )
    if not identity_references:
        raise LenaIdentityEvidenceError("identity_reference_missing", "at least one identity reference is required")
    for reference_path, expected_sha in identity_references:
        if not Path(reference_path).is_file():
            raise LenaIdentityEvidenceError(
                "identity_reference_missing",
                f"identity reference is missing: {reference_path}",
            )
        if sha256_file(Path(reference_path)) != expected_sha:
            raise LenaIdentityEvidenceError(
                "identity_reference_sha_mismatch",
                f"identity reference SHA-256 mismatch: {reference_path}",
            )


def build_local_identity_evidence(
    *,
    date_str: str,
    slot_id: str,
    manifest: dict[str, Any],
    image_path: Path,
    image_sha256: str,
    identity_evidence_path: Path | None = None,
    reference_authority_artifact: Path | None = None,
    reference_authority_sha256: str | None = None,
    identity_references: list[tuple[Path, str]] | None = None,
) -> tuple[Path, dict[str, Any], bool]:
    image_path = Path(image_path).resolve()
    if not image_path.is_file():
        raise LenaIdentityEvidenceError("generated_image_missing", f"generated image is missing: {image_path}")
    if sha256_file(image_path) != image_sha256:
        raise LenaIdentityEvidenceError("generated_image_sha_mismatch", "generated image SHA-256 changed before identity evidence write")
    if not isinstance(manifest, dict):
        raise LenaIdentityEvidenceError("manifest_invalid", "manifest must be a JSON object")

    provider = _required_string(manifest, "provider")
    _require(provider == "higgsfield", "manifest_provider_mismatch", "manifest provider must be exactly 'higgsfield'")
    manifest_date = _required_string(manifest, "date")
    _require(manifest_date == date_str, "manifest_date_mismatch", "manifest date does not match requested date")
    manifest_slot_id = _required_string(manifest, "slot_id")
    _require(manifest_slot_id == slot_id, "manifest_slot_id_mismatch", "manifest slot_id does not match requested slot")
    provider_status = _required_string(manifest, "provider_status")
    _require(provider_status == identity.EXPECTED_JOB_STATUS, "manifest_provider_status_mismatch", "manifest provider_status must be exactly 'completed'")
    provider_job_id = _required_string(manifest, "provider_job_id")
    job_type = _required_string(manifest, "job_type")
    _require(job_type == identity.EXPECTED_JOB_TYPE, "manifest_job_type_mismatch", "manifest job_type does not match the approved Higgsfield job type")
    custom_reference_id = _required_string(manifest, "custom_reference_id")
    _require(
        custom_reference_id == identity.CURRENT_LENA_SOUL_ID,
        "identity_current_soul_id_invalid",
        "manifest custom_reference_id is not the current Lena Soul ID",
    )
    soul_id = _required_string(manifest, "soul_id")
    _require(
        soul_id == custom_reference_id,
        "manifest_soul_id_mismatch",
        "manifest soul_id must match custom_reference_id",
    )
    soul_name = _required_string(manifest, "cli_soul_name")
    _require(soul_name == identity.EXPECTED_SOUL_NAME, "manifest_cli_soul_name_mismatch", "manifest cli_soul_name must be exactly 'Lena'")
    soul_type = _required_string(manifest, "cli_soul_type")
    _require(soul_type == identity.EXPECTED_SOUL_TYPE, "manifest_cli_soul_type_mismatch", "manifest cli_soul_type must be exactly 'soul_2'")
    prompt_sha256 = _required_string(manifest, "prompt_sha256")
    _require(
        re.fullmatch(r"[0-9a-f]{64}", prompt_sha256) is not None,
        "manifest_prompt_sha256_invalid",
        "manifest prompt_sha256 must be a lowercase SHA-256 hex digest",
    )
    manifest_image_path = Path(_required_string(manifest, "saved_image_path"))
    _require(
        manifest_image_path.resolve() == image_path,
        "manifest_saved_image_path_mismatch",
        "manifest saved_image_path does not resolve to the generated image being verified",
    )
    manifest_image_sha256 = _required_string(manifest, "saved_image_sha256")
    _require(
        manifest_image_sha256 == image_sha256,
        "manifest_saved_image_sha256_mismatch",
        "manifest saved_image_sha256 does not match the generated image SHA-256",
    )
    width, height = _inspect_image_dimensions(image_path)
    _require(
        width == identity.EXPECTED_WIDTH and height == identity.EXPECTED_HEIGHT,
        "generated_image_dimensions_mismatch",
        f"generated image dimensions {width}x{height} do not match approved Higgsfield dimensions {identity.EXPECTED_WIDTH}x{identity.EXPECTED_HEIGHT}",
    )
    if reference_authority_artifact is not None:
        _validate_authority_references(
            reference_authority_artifact=Path(reference_authority_artifact),
            reference_authority_sha256=str(reference_authority_sha256 or ""),
            identity_references=list(identity_references or []),
        )

    evidence_path = Path(identity_evidence_path) if identity_evidence_path is not None else identity.identity_verification_evidence_path(date_str, slot_id)
    verified = {
        "provider": provider,
        "slot_id": manifest_slot_id,
        "provider_job_id": provider_job_id,
        "provider_job_status": provider_status,
        "job_type": job_type,
        "custom_reference_id": custom_reference_id,
        "soul_id": soul_id,
        "soul_name": soul_name,
        "soul_type": soul_type,
        "prompt_sha256": prompt_sha256,
        "width": width,
        "height": height,
        "local_image_path": str(image_path),
        "local_image_sha256": image_sha256,
        "local_image_sha256_provenance": (
            "Captured from the local file after provider success and before downstream accounting. "
            "This is local provenance, not a fresh provider re-download."
        ),
        "checks_passed": [
            "provider_success_manifest_present",
            "generated_image_exists",
            "local_image_sha256_matches",
            "manifest_saved_image_sha256_matches",
            "approved_custom_reference_id",
            "actual_image_dimensions_match",
        ],
    }
    evidence = _json_safe(identity.build_identity_verification_evidence(date_str, verified))
    evidence["source_manifest"] = _json_safe(manifest)
    if reference_authority_artifact is not None:
        evidence["reference_authority_artifact"] = str(Path(reference_authority_artifact))
        evidence["reference_authority_sha256"] = str(reference_authority_sha256)
        evidence["identity_references"] = [
            {"path": str(Path(path)), "sha256": sha256}
            for path, sha256 in list(identity_references or [])
        ]

    if evidence_path.exists():
        try:
            existing = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LenaIdentityEvidenceError(
                "identity_evidence_existing_invalid",
                f"existing identity evidence is not valid JSON: {evidence_path}: {exc}",
            ) from exc
        if not isinstance(existing, dict):
            raise LenaIdentityEvidenceError(
                "identity_evidence_existing_invalid",
                f"existing identity evidence must be a JSON object: {evidence_path}",
            )
        if _evidence_reuse_fingerprint(existing) != _evidence_reuse_fingerprint(evidence):
            raise LenaIdentityEvidenceError(
                "identity_evidence_already_exists",
                f"refusing to overwrite existing identity evidence: {evidence_path}",
            )
        evidence = existing
        written = False
    else:
        written = _write_json_atomic(evidence_path, evidence)
    observed = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    if observed.get("verification_result") != "pass":
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence did not record a pass")
    if observed.get("provider") != "higgsfield":
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence provider mismatch")
    if observed.get("slot_id") != slot_id:
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence slot_id mismatch")
    if observed.get("custom_reference_id") not in identity.APPROVED_CUSTOM_REFERENCE_IDS:
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence custom_reference_id is not approved")
    if observed.get("custom_reference_id") != identity.CURRENT_LENA_SOUL_ID:
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence custom_reference_id is not the current Lena Soul ID")
    if observed.get("soul_id") != observed.get("custom_reference_id"):
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence soul_id must match custom_reference_id")
    if observed.get("local_image_sha256") != image_sha256:
        raise LenaIdentityEvidenceError("identity_evidence_validation_failed", "identity evidence image SHA-256 mismatch")
    return evidence_path, evidence, written
