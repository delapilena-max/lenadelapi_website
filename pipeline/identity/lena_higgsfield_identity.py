from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Read-only Higgsfield identity-verification module -- the Higgsfield
# counterpart to the trust *concept* pipeline/identity/lena_identity.py
# provides for Kling, deliberately architected the same way Kling's own
# chain actually works: a real live-provider check happens ONCE, here, and
# leaves a durable evidence file behind; nothing downstream (preflight or
# otherwise) makes a live provider call itself. This module is not wired
# into tools/lena_preflight.py yet -- that is a separate, later, explicitly
# approved step.
#
# Verifies identity provenance for ONE already-existing, already-completed
# Higgsfield render. Never generates, never spends credit, never retries a
# job. Exactly two read-only provider CLI calls per verification:
#   higgsfield generate get <provider_job_id> --json
#   higgsfield soul-id get <custom_reference_id> --json
# Neither call creates or mutates anything provider-side.
#
# Fails closed (raises HiggsfieldIdentityVerificationError) on any mismatch
# or missing data -- never falls back to trusting self-reported local
# metadata alone, and never silently downgrades a failed check into a
# warning. Writes exactly one new evidence file
# (pipeline/higgsfield_debug/<date>/<slot_id>/identity_verification.json);
# never modifies the original generation manifest.

HIGGSFIELD_CLI_BINARY = "higgsfield"
EXPECTED_JOB_STATUS = "completed"
EXPECTED_SOUL_STATUS = "completed"
EXPECTED_SOUL_NAME = "Lena"
EXPECTED_SOUL_TYPE = "soul_2"

SCHEMA_VERSION = "1"

ROOT = Path(__file__).resolve().parents[2]
HIGGSFIELD_DEBUG_ROOT = ROOT / "pipeline" / "higgsfield_debug"


class HiggsfieldIdentityVerificationError(Exception):
    """Raised for any hard-fail condition during identity verification.
    Never caught silently by this module -- callers must treat this as a
    hard block."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_higgsfield_json(argv_tail: List[str]) -> Any:
    """Runs a read-only `higgsfield <argv_tail> --json` command and returns
    the parsed JSON. Resolves the executable via shutil.which() at the
    subprocess boundary, mirroring pipeline/higgsfield_lena_api_executor.py's
    own Windows PATHEXT fix (a bare "higgsfield" via subprocess.run(shell=False)
    does not resolve higgsfield.CMD on Windows). Raises
    HiggsfieldIdentityVerificationError on any spawn/parse/non-zero-exit
    failure -- never returns a partial or guessed result."""
    resolved_binary = shutil.which(HIGGSFIELD_CLI_BINARY)
    if not resolved_binary:
        raise HiggsfieldIdentityVerificationError(
            f"Could not resolve {HIGGSFIELD_CLI_BINARY!r} via shutil.which() -- "
            "the Higgsfield CLI does not appear to be on PATH."
        )
    argv = [resolved_binary, *argv_tail, "--json"]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, shell=False, check=False)
    except OSError as exc:
        raise HiggsfieldIdentityVerificationError(
            f"Failed to spawn the Higgsfield CLI process ({resolved_binary!r}): {exc}"
        ) from exc

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-2000:]
        raise HiggsfieldIdentityVerificationError(
            f"'higgsfield {' '.join(argv_tail)}' exited {result.returncode}. "
            f"stderr (tail): {stderr_tail}"
        )

    try:
        return json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise HiggsfieldIdentityVerificationError(
            f"Failed to parse 'higgsfield {' '.join(argv_tail)}' --json output as JSON: {exc}"
        ) from exc


def verify_higgsfield_identity(
    *,
    slot_id: str,
    provider_job_id: str,
    expected_job_type: str,
    expected_custom_reference_id: str,
    expected_prompt_sha256: str,
    manifest_path: Path,
    saved_image_path: Path,
) -> Dict[str, Any]:
    """Read-only. Verifies identity provenance for one already-existing
    Higgsfield render by cross-checking real, live provider data against
    the expected values supplied by the caller. Raises
    HiggsfieldIdentityVerificationError fail-closed on ANY mismatch or
    missing data. Returns a dict of verified evidence on success -- does
    not write anything itself; see build_identity_verification_evidence()
    and verify_and_record_higgsfield_identity() below for persistence."""
    checks_passed: List[str] = []

    # Local manifest must exist and be a real object -- fail closed before
    # making any network call at all if the thing we're trying to verify
    # isn't even present locally.
    if not manifest_path.exists():
        raise HiggsfieldIdentityVerificationError(f"manifest does not exist: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise HiggsfieldIdentityVerificationError(
            f"failed to parse manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise HiggsfieldIdentityVerificationError(f"manifest {manifest_path} did not contain a JSON object")
    checks_passed.append("manifest_exists_and_parses")

    manifest_slot_id = manifest.get("slot_id")
    if manifest_slot_id != slot_id:
        raise HiggsfieldIdentityVerificationError(
            f"manifest slot_id {manifest_slot_id!r} does not match expected {slot_id!r}"
        )
    checks_passed.append("manifest_slot_id_matches")

    manifest_provider_job_id = manifest.get("provider_job_id")
    if manifest_provider_job_id != provider_job_id:
        raise HiggsfieldIdentityVerificationError(
            f"manifest provider_job_id {manifest_provider_job_id!r} does not match expected "
            f"{provider_job_id!r}"
        )
    checks_passed.append("manifest_provider_job_id_matches")

    manifest_custom_reference_id = manifest.get("custom_reference_id")
    if manifest_custom_reference_id != expected_custom_reference_id:
        raise HiggsfieldIdentityVerificationError(
            f"manifest custom_reference_id {manifest_custom_reference_id!r} does not match "
            f"expected {expected_custom_reference_id!r}"
        )
    checks_passed.append("manifest_custom_reference_id_matches")

    manifest_job_type = manifest.get("job_type")
    if manifest_job_type != expected_job_type:
        raise HiggsfieldIdentityVerificationError(
            f"manifest job_type {manifest_job_type!r} does not match expected {expected_job_type!r}"
        )
    checks_passed.append("manifest_job_type_matches")

    # Local image must actually exist on disk.
    if not saved_image_path.exists():
        raise HiggsfieldIdentityVerificationError(f"local saved image does not exist: {saved_image_path}")
    checks_passed.append("local_image_exists")

    # Live provider job lookup -- the real, current provider record.
    job = _run_higgsfield_json(["generate", "get", provider_job_id])
    if not isinstance(job, dict):
        raise HiggsfieldIdentityVerificationError("'higgsfield generate get' did not return a JSON object")
    checks_passed.append("provider_job_lookup_succeeded")

    job_id = job.get("id")
    if job_id != provider_job_id:
        raise HiggsfieldIdentityVerificationError(
            f"provider job id {job_id!r} does not match requested {provider_job_id!r}"
        )
    checks_passed.append("provider_job_id_matches")

    job_status = job.get("status")
    if job_status != EXPECTED_JOB_STATUS:
        raise HiggsfieldIdentityVerificationError(
            f"provider job status is {job_status!r}, expected {EXPECTED_JOB_STATUS!r}"
        )
    checks_passed.append("provider_job_status_completed")

    job_type = job.get("job_type")
    if job_type != expected_job_type:
        raise HiggsfieldIdentityVerificationError(
            f"provider job_type {job_type!r} does not match expected {expected_job_type!r}"
        )
    checks_passed.append("provider_job_type_matches")

    params = job.get("params") if isinstance(job.get("params"), dict) else {}
    provider_custom_reference_id = params.get("custom_reference_id")
    if provider_custom_reference_id != expected_custom_reference_id:
        raise HiggsfieldIdentityVerificationError(
            f"provider custom_reference_id {provider_custom_reference_id!r} does not match "
            f"expected {expected_custom_reference_id!r}"
        )
    checks_passed.append("provider_custom_reference_id_matches")

    provider_prompt = params.get("prompt")
    if not isinstance(provider_prompt, str) or not provider_prompt:
        raise HiggsfieldIdentityVerificationError("provider job response has no usable 'params.prompt'")
    provider_prompt_sha256 = hashlib.sha256(provider_prompt.encode("utf-8")).hexdigest()
    if provider_prompt_sha256 != expected_prompt_sha256:
        raise HiggsfieldIdentityVerificationError(
            f"provider prompt re-hashes to {provider_prompt_sha256}, expected {expected_prompt_sha256}"
        )
    checks_passed.append("provider_prompt_sha256_matches")

    width = params.get("width")
    height = params.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise HiggsfieldIdentityVerificationError(
            f"provider job response has no usable width/height (got {width!r}x{height!r})"
        )
    checks_passed.append("provider_dimensions_present")

    # Live Soul reference lookup -- independently confirms the reference id
    # really is named "Lena", not just assumed from a local constant.
    soul = _run_higgsfield_json(["soul-id", "get", expected_custom_reference_id])
    if not isinstance(soul, dict):
        raise HiggsfieldIdentityVerificationError("'higgsfield soul-id get' did not return a JSON object")
    checks_passed.append("soul_lookup_succeeded")

    soul_id = soul.get("id")
    if soul_id != expected_custom_reference_id:
        raise HiggsfieldIdentityVerificationError(
            f"soul-id response id {soul_id!r} does not match requested {expected_custom_reference_id!r}"
        )
    checks_passed.append("soul_id_matches")

    soul_name = soul.get("name")
    if soul_name != EXPECTED_SOUL_NAME:
        raise HiggsfieldIdentityVerificationError(f"soul name is {soul_name!r}, expected {EXPECTED_SOUL_NAME!r}")
    checks_passed.append("soul_name_is_lena")

    soul_type = soul.get("type")
    if soul_type != EXPECTED_SOUL_TYPE:
        raise HiggsfieldIdentityVerificationError(f"soul type is {soul_type!r}, expected {EXPECTED_SOUL_TYPE!r}")
    checks_passed.append("soul_type_is_soul_2")

    soul_status = soul.get("status")
    if soul_status != EXPECTED_SOUL_STATUS:
        raise HiggsfieldIdentityVerificationError(
            f"soul status is {soul_status!r}, expected {EXPECTED_SOUL_STATUS!r}"
        )
    checks_passed.append("soul_status_completed")

    # Local image hash -- captured now, at verification time, from the file
    # currently on disk. This is explicitly NOT proof the bytes are
    # identical to what the provider originally returned: no fresh
    # re-download/re-hash of the provider's own result_url was performed as
    # part of this check. It is only a snapshot of the local file's current
    # content, recorded so a *future* check could detect if the local file
    # changes after this point -- see local_image_sha256_provenance below.
    local_image_sha256 = hashlib.sha256(saved_image_path.read_bytes()).hexdigest()
    checks_passed.append("local_image_sha256_captured_not_verified_against_provider_bytes")

    return {
        "provider": "higgsfield",
        "slot_id": slot_id,
        "provider_job_id": provider_job_id,
        "provider_job_status": job_status,
        "job_type": job_type,
        "custom_reference_id": provider_custom_reference_id,
        "soul_name": soul_name,
        "soul_type": soul_type,
        "soul_status": soul_status,
        "prompt_sha256": provider_prompt_sha256,
        "width": width,
        "height": height,
        "local_image_path": str(saved_image_path),
        "local_image_sha256": local_image_sha256,
        "local_image_sha256_provenance": (
            "Captured from the local file at verification time. This is NOT a "
            "proof of byte-identity with the original provider-downloaded "
            "image -- no fresh re-download/re-hash of the provider's result_url "
            "was performed during this verification. It only proves what the "
            "local file's content was at this exact verification timestamp."
        ),
        "checks_passed": checks_passed,
    }


def build_identity_verification_evidence(date_str: str, verified: Dict[str, Any]) -> Dict[str, Any]:
    """Pure function, no I/O. Shapes the final evidence-file schema from a
    successful verify_higgsfield_identity() result. Contains only safe,
    non-sensitive evidence -- no raw signed URLs, tokens, cookies, or API
    keys anywhere in this shape."""
    return {
        "schema_version": SCHEMA_VERSION,
        "verified_at_utc": _utc_now(),
        "provider": verified["provider"],
        "date": date_str,
        "slot_id": verified["slot_id"],
        "provider_job_id": verified["provider_job_id"],
        "provider_job_status": verified["provider_job_status"],
        "job_type": verified["job_type"],
        "custom_reference_id": verified["custom_reference_id"],
        "soul_name": verified["soul_name"],
        "soul_type": verified["soul_type"],
        "prompt_sha256": verified["prompt_sha256"],
        "width": verified["width"],
        "height": verified["height"],
        "local_image_path": verified["local_image_path"],
        "local_image_sha256": verified["local_image_sha256"],
        "local_image_sha256_provenance": verified["local_image_sha256_provenance"],
        "verification_result": "pass",
        "checks_passed": verified["checks_passed"],
    }


def identity_verification_evidence_path(date_str: str, slot_id: str) -> Path:
    return HIGGSFIELD_DEBUG_ROOT / date_str / slot_id / "identity_verification.json"


def verify_and_record_higgsfield_identity(
    date_str: str,
    slot_id: str,
    manifest_path: Path,
) -> Path:
    """Reads the real manifest's own claimed identity fields (never
    fabricated), verifies them against live provider data via
    verify_higgsfield_identity(), and -- only on success -- writes exactly
    one new evidence file. Raises HiggsfieldIdentityVerificationError
    fail-closed, and writes nothing, if any check fails. Never modifies the
    original manifest at manifest_path."""
    if not manifest_path.exists():
        raise HiggsfieldIdentityVerificationError(f"manifest does not exist: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise HiggsfieldIdentityVerificationError(
            f"failed to parse manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise HiggsfieldIdentityVerificationError(f"manifest {manifest_path} did not contain a JSON object")

    provider_job_id = manifest.get("provider_job_id")
    job_type = manifest.get("job_type")
    custom_reference_id = manifest.get("custom_reference_id")
    prompt_sha256 = manifest.get("prompt_sha256")
    saved_image_path_raw = manifest.get("saved_image_path")

    for field_name, value in (
        ("provider_job_id", provider_job_id),
        ("job_type", job_type),
        ("custom_reference_id", custom_reference_id),
        ("prompt_sha256", prompt_sha256),
        ("saved_image_path", saved_image_path_raw),
    ):
        if not value:
            raise HiggsfieldIdentityVerificationError(
                f"manifest {manifest_path} is missing '{field_name}' -- refusing to fabricate a value."
            )

    verified = verify_higgsfield_identity(
        slot_id=slot_id,
        provider_job_id=str(provider_job_id),
        expected_job_type=str(job_type),
        expected_custom_reference_id=str(custom_reference_id),
        expected_prompt_sha256=str(prompt_sha256),
        manifest_path=manifest_path,
        saved_image_path=Path(str(saved_image_path_raw)),
    )

    evidence = build_identity_verification_evidence(date_str, verified)
    evidence_path = identity_verification_evidence_path(date_str, slot_id)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return evidence_path
