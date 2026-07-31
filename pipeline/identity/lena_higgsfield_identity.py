from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pipeline.identity import lena_higgsfield_soul_cinema_contract_v1 as soul_cinema_contract

# Read-only Higgsfield identity-verification module -- the Higgsfield
# authority for Higgsfield generations. A real live-provider check happens
# ONCE, here, and
# leaves a durable evidence file behind. tools/lena_preflight.py reads and
# validates that evidence file LOCALLY (validate_local_identity_evidence()
# below) -- it never makes a live provider call itself.
#
# Two independent verification paths live in this module:
#   1. verify_higgsfield_identity() / verify_and_record_higgsfield_identity()
#      -- makes the real, one-time, read-only provider calls
#      (`higgsfield generate get`, `higgsfield soul-id get`) and writes the
#      evidence file. Never generates, never spends credit, never retries a
#      job.
#   2. validate_local_identity_evidence() -- LOCAL ONLY, zero network calls.
#      Reads the evidence file (1) already wrote and checks it for internal
#      consistency against this module's canonical expected Lena identity
#      constants and the queue item's own claimed metadata. This is what
#      tools/lena_preflight.py calls.
#
# Both fail closed on any mismatch or missing data -- neither falls back to
# trusting self-reported local metadata alone, and neither silently
# downgrades a failed check into a warning. Path (1) writes exactly one new
# evidence file; never modifies the original generation manifest. Path (2)
# writes nothing, ever.

HIGGSFIELD_CLI_BINARY = "higgsfield"
EXPECTED_JOB_STATUS = "completed"
EXPECTED_SOUL_STATUS = "completed"
EXPECTED_SOUL_NAME = "Lena"
EXPECTED_SOUL_TYPE = "soul_2"
EXPECTED_JOB_TYPE = soul_cinema_contract.MODEL
CURRENT_LENA_SOUL_ID = soul_cinema_contract.CUSTOM_REFERENCE_ID
HISTORICAL_JOB_TYPES = frozenset({"text2image_soul_v2"})
APPROVED_JOB_TYPES = frozenset({EXPECTED_JOB_TYPE, *HISTORICAL_JOB_TYPES})
# These are real, provider-confirmed Lena Soul ids -- not interchangeable
# by convenience, but each genuinely valid for evidence recorded while it
# was the account's live Soul. The account's live Soul id rotated after the
# original 2026-07-09/10 confirmation, again after the 2026-07-12
# confirmation, again on 2026-07-23 (re-confirmed via `higgsfield soul-id
# list --json` that day), and again later the same day when Nicolas erased
# the account's Souls and retrained a fresh Lena Soul 2.0 because the
# 2026-07-23 id did not visually match Lena in either of the two real
# generations run under it -- only the fourth id below is present on the
# account today.
# Historical evidence recorded under prior ids remains genuinely correct for
# what was actually verified at that time and must never be rewritten to
# match current provider truth.
# pipeline/higgsfield_lena_api_executor.py::DEFAULT_LENA_CUSTOM_REFERENCE_ID
# is the separate, singular default used for NEW live submissions -- it is
# always exactly the current id, never chosen from this set. This set
# exists only for read-only, local evidence validation below.
APPROVED_CUSTOM_REFERENCE_IDS = {
    "1f1200e4-1cc9-4504-ac1c-3304b687e3c1",  # historical Lena Soul id (2026-07-09/10 confirmation)
    "90a293d7-f3af-4377-8751-3304a27b6f31",  # historical Lena Soul id (2026-07-12 confirmation; produced the canonical reference photo)
    "e45ec580-a6db-4063-a9b2-f9163856daae",  # historical Lena Soul id (2026-07-20 - 2026-07-23; did not visually match Lena, retired same-day)
    "79119c27-64fc-47f8-9ff3-c174d12932aa",  # current live Lena Soul id (retrained 2026-07-23)
}
# The approved still-photo proof lane currently runs 9:16 at Higgsfield
# quality "2k". The real returned Lena photo on 2026-07-31 resolved to
# 1152x2048, and downstream identity/QA verification must validate against
# the measured provider output rather than a stale square assumption.
EXPECTED_WIDTH = 1152
EXPECTED_HEIGHT = 2048

SCHEMA_VERSION = "1"
REQUIRED_EVIDENCE_FIELDS = (
    "schema_version", "verified_at_utc", "provider", "date", "slot_id",
    "provider_job_id", "provider_job_status", "job_type",
    "custom_reference_id", "soul_id", "soul_name", "soul_type", "prompt_sha256",
    "width", "height", "local_image_path", "local_image_sha256",
    "verification_result", "checks_passed",
)

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
        "soul_id": provider_custom_reference_id,
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
        "soul_id": verified["soul_id"],
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
    soul_id = manifest.get("soul_id")
    prompt_sha256 = manifest.get("prompt_sha256")
    saved_image_path_raw = manifest.get("saved_image_path")

    for field_name, value in (
        ("provider_job_id", provider_job_id),
        ("job_type", job_type),
        ("custom_reference_id", custom_reference_id),
        ("soul_id", soul_id),
        ("prompt_sha256", prompt_sha256),
        ("saved_image_path", saved_image_path_raw),
    ):
        if not value:
            raise HiggsfieldIdentityVerificationError(
                f"manifest {manifest_path} is missing '{field_name}' -- refusing to fabricate a value."
            )
    if str(soul_id) != str(custom_reference_id):
        raise HiggsfieldIdentityVerificationError(
            f"manifest {manifest_path} soul_id {soul_id!r} does not match custom_reference_id {custom_reference_id!r}"
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


def validate_local_identity_evidence(
    date_str: str,
    slot_id: str,
    media_path: Path,
    meta: Dict[str, Any],
) -> List[str]:
    """Read-only, LOCAL ONLY -- makes zero network/provider calls. Reads the
    already-written pipeline/higgsfield_debug/<date>/<slot_id>/
    identity_verification.json evidence file (produced once, earlier, by
    verify_and_record_higgsfield_identity()) and checks it for internal
    consistency against this module's canonical expected Lena identity
    constants and the queue item's own claimed metadata/media path.

    Never raises -- returns a list of human-readable failure reasons (an
    empty list means every check passed), matching
    tools/lena_preflight.py's own accumulate-all-failures style (its
    require()/bad list) rather than stopping at the first problem.

    Does NOT re-verify against the live provider -- that already happened,
    once, when the evidence file was written. This function only checks
    that the evidence file (a) is well-formed, (b) recorded a real pass,
    (c) matches the approved Lena identity constants, (d) is consistent
    with what this specific queue item itself claims, and (e) the local
    image file hasn't changed since verification (via a local re-hash,
    which is NOT a check against the original provider-downloaded bytes --
    see local_image_sha256_provenance in the evidence file itself)."""
    reasons: List[str] = []
    evidence_path = identity_verification_evidence_path(date_str, slot_id)

    if not evidence_path.exists():
        return [f"no Higgsfield identity_verification.json for this slot: {evidence_path}"]

    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [f"failed to parse {evidence_path}: {exc}"]

    if not isinstance(evidence, dict):
        return [f"{evidence_path} did not contain a JSON object"]

    missing_keys = [k for k in REQUIRED_EVIDENCE_FIELDS if k not in evidence]
    if missing_keys:
        return [f"{evidence_path} is missing required field(s): {missing_keys}"]

    if evidence.get("schema_version") != SCHEMA_VERSION:
        reasons.append(
            f"identity_verification.json schema_version {evidence.get('schema_version')!r} "
            f"is not the expected {SCHEMA_VERSION!r}"
        )

    if evidence.get("verification_result") != "pass":
        reasons.append(
            f"identity_verification.json verification_result is "
            f"{evidence.get('verification_result')!r}, not 'pass'"
        )

    if evidence.get("provider") != "higgsfield":
        reasons.append(
            f"identity_verification.json provider is {evidence.get('provider')!r}, expected 'higgsfield'"
        )

    if evidence.get("slot_id") != slot_id:
        reasons.append(
            f"identity_verification.json slot_id {evidence.get('slot_id')!r} does not match {slot_id!r}"
        )

    if evidence.get("job_type") not in APPROVED_JOB_TYPES:
        reasons.append(
            f"identity_verification.json job_type {evidence.get('job_type')!r} "
            "is not an approved Lena Higgsfield job type"
        )

    if evidence.get("custom_reference_id") not in APPROVED_CUSTOM_REFERENCE_IDS:
        reasons.append(
            f"identity_verification.json custom_reference_id {evidence.get('custom_reference_id')!r} "
            f"is not one of the approved Lena reference ids {sorted(APPROVED_CUSTOM_REFERENCE_IDS)!r}"
        )
    if evidence.get("soul_id") != evidence.get("custom_reference_id"):
        reasons.append("identity_verification.json soul_id does not match custom_reference_id")

    if evidence.get("soul_name") != EXPECTED_SOUL_NAME:
        reasons.append(
            f"identity_verification.json soul_name {evidence.get('soul_name')!r} is not {EXPECTED_SOUL_NAME!r}"
        )

    if evidence.get("soul_type") != EXPECTED_SOUL_TYPE:
        reasons.append(
            f"identity_verification.json soul_type {evidence.get('soul_type')!r} is not {EXPECTED_SOUL_TYPE!r}"
        )

    if evidence.get("width") != EXPECTED_WIDTH or evidence.get("height") != EXPECTED_HEIGHT:
        reasons.append(
            f"identity_verification.json dimensions {evidence.get('width')}x{evidence.get('height')} "
            f"do not match the approved Higgsfield resolution {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}"
        )

    # Cross-check against the queue item's own self-reported metadata --
    # ties this specific queue item to this specific evidence file, rather
    # than trusting that any evidence file at this path is relevant to it.
    meta_provider_job_id = meta.get("provider_job_id")
    if meta_provider_job_id and evidence.get("provider_job_id") != meta_provider_job_id:
        reasons.append(
            f"identity_verification.json provider_job_id {evidence.get('provider_job_id')!r} does not "
            f"match this queue item's own metadata.provider_job_id {meta_provider_job_id!r}"
        )

    meta_custom_reference_id = meta.get("custom_reference_id")
    if meta_custom_reference_id and evidence.get("custom_reference_id") != meta_custom_reference_id:
        reasons.append(
            f"identity_verification.json custom_reference_id does not match this queue item's own "
            f"metadata.custom_reference_id {meta_custom_reference_id!r}"
        )
    meta_soul_id = meta.get("soul_id")
    if meta_soul_id and evidence.get("soul_id") != meta_soul_id:
        reasons.append(
            f"identity_verification.json soul_id does not match this queue item's own "
            f"metadata.soul_id {meta_soul_id!r}"
        )

    meta_image_prompt = meta.get("image_prompt")
    if meta_image_prompt:
        recomputed_prompt_sha256 = hashlib.sha256(str(meta_image_prompt).encode("utf-8")).hexdigest()
        if recomputed_prompt_sha256 != evidence.get("prompt_sha256"):
            reasons.append(
                "this queue item's own metadata.image_prompt re-hashes to a different value than "
                "identity_verification.json's recorded prompt_sha256 -- prompt text may have changed "
                "since verification"
            )

    # Local image existence + current-content re-hash -- both purely local,
    # zero network. Catches the file being swapped/modified after
    # verification. This is NOT a check against the original
    # provider-downloaded bytes (see the evidence file's own
    # local_image_sha256_provenance disclosure) -- only against what the
    # evidence itself recorded at verification time.
    evidence_image_path = Path(str(evidence.get("local_image_path") or ""))
    if not evidence_image_path.exists():
        reasons.append(f"identity_verification.json's local_image_path does not exist: {evidence_image_path}")
    else:
        current_sha256 = hashlib.sha256(evidence_image_path.read_bytes()).hexdigest()
        if current_sha256 != evidence.get("local_image_sha256"):
            reasons.append(
                "local image SHA-256 no longer matches the hash captured in identity_verification.json "
                "-- the file may have been modified or replaced since verification"
            )

    try:
        media_path_matches = evidence_image_path.resolve() == media_path.resolve()
    except OSError:
        media_path_matches = str(evidence_image_path) == str(media_path)
    if not media_path_matches:
        reasons.append(
            f"identity_verification.json's local_image_path ({evidence_image_path}) does not match "
            f"this queue item's own media_path ({media_path})"
        )

    return reasons
