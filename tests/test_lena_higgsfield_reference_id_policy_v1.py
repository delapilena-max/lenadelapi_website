from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import pipeline.higgsfield_lena_api_executor as executor_mod
import pipeline.identity.lena_higgsfield_identity as identity_mod
import tools.lena_higgsfield_prompt_isolation_test_v1 as isolation_mod
from pipeline.higgsfield_lena_api_executor import (
    DEFAULT_LENA_CUSTOM_REFERENCE_ID,
    build_provider_argv,
)
from pipeline.identity.lena_higgsfield_identity import (
    APPROVED_CUSTOM_REFERENCE_IDS,
    validate_local_identity_evidence,
)

CURRENT_LIVE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
HISTORICAL_ID = "1f1200e4-1cc9-4504-ac1c-3304b687e3c1"


# 1/3/14. The canonical current live ID is the new id, singular, a plain
# string (never a set/collection), and the old id is not the default.
def test_default_reference_id_is_the_current_live_id_singular_scalar() -> None:
    assert DEFAULT_LENA_CUSTOM_REFERENCE_ID == CURRENT_LIVE_ID
    assert isinstance(DEFAULT_LENA_CUSTOM_REFERENCE_ID, str)
    assert DEFAULT_LENA_CUSTOM_REFERENCE_ID != HISTORICAL_ID


# 2. build_provider_argv() places exactly that id after --custom_reference_id.
def test_build_provider_argv_places_current_id_after_flag() -> None:
    argv = build_provider_argv("a test prompt", DEFAULT_LENA_CUSTOM_REFERENCE_ID)
    idx = argv.index("--custom_reference_id")
    assert argv[idx + 1] == CURRENT_LIVE_ID


# 4. The controlled isolation runner inherits the same current canonical id.
def test_isolation_runner_inherits_current_id_from_executor() -> None:
    assert isolation_mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID == CURRENT_LIVE_ID
    assert isolation_mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID is executor_mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID


# 5. The executor's current default is a member of the validator's
# approved-id set (never orphaned from evidence validation).
def test_executor_default_is_a_member_of_approved_evidence_ids() -> None:
    assert DEFAULT_LENA_CUSTOM_REFERENCE_ID in APPROVED_CUSTOM_REFERENCE_IDS


def test_approved_ids_set_contains_exactly_historical_and_current() -> None:
    assert APPROVED_CUSTOM_REFERENCE_IDS == {HISTORICAL_ID, CURRENT_LIVE_ID}


# --- local evidence validation ---------------------------------------------

def _write_evidence(
    debug_root: Path,
    date_str: str,
    slot_id: str,
    custom_reference_id: str,
    image_path: Path,
) -> None:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-verified-bytes")
    prompt = "fake verified prompt text"
    evidence = {
        "schema_version": identity_mod.SCHEMA_VERSION,
        "verified_at_utc": "2026-07-12T00:00:00+00:00",
        "provider": "higgsfield",
        "date": date_str,
        "slot_id": slot_id,
        "provider_job_id": "job-fake-123",
        "provider_job_status": identity_mod.EXPECTED_JOB_STATUS,
        "job_type": identity_mod.EXPECTED_JOB_TYPE,
        "custom_reference_id": custom_reference_id,
        "soul_name": identity_mod.EXPECTED_SOUL_NAME,
        "soul_type": identity_mod.EXPECTED_SOUL_TYPE,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "width": identity_mod.EXPECTED_WIDTH,
        "height": identity_mod.EXPECTED_HEIGHT,
        "local_image_path": str(image_path),
        "local_image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "verification_result": "pass",
        "checks_passed": ["fake_check"],
    }
    evidence_path = debug_root / date_str / slot_id / "identity_verification.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return prompt


# 6. Local durable evidence using the historical old id still passes.
def test_evidence_with_historical_id_still_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_mod, "HIGGSFIELD_DEBUG_ROOT", tmp_path)
    image_path = tmp_path / "seed.png"
    prompt = _write_evidence(tmp_path, "2026-07-09", "historical-slot", HISTORICAL_ID, image_path)

    reasons = validate_local_identity_evidence(
        "2026-07-09", "historical-slot", image_path,
        {"custom_reference_id": HISTORICAL_ID, "image_prompt": prompt},
    )
    assert reasons == []


# 7. Local durable evidence using the new current id passes.
def test_evidence_with_current_id_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_mod, "HIGGSFIELD_DEBUG_ROOT", tmp_path)
    image_path = tmp_path / "seed.png"
    prompt = _write_evidence(tmp_path, "2026-07-12", "current-slot", CURRENT_LIVE_ID, image_path)

    reasons = validate_local_identity_evidence(
        "2026-07-12", "current-slot", image_path,
        {"custom_reference_id": CURRENT_LIVE_ID, "image_prompt": prompt},
    )
    assert reasons == []


# 8. An unknown custom_reference_id fails closed.
def test_evidence_with_unknown_id_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity_mod, "HIGGSFIELD_DEBUG_ROOT", tmp_path)
    image_path = tmp_path / "seed.png"
    unknown_id = "00000000-0000-0000-0000-000000000000"
    prompt = _write_evidence(tmp_path, "2026-07-12", "unknown-id-slot", unknown_id, image_path)

    reasons = validate_local_identity_evidence(
        "2026-07-12", "unknown-id-slot", image_path,
        {"custom_reference_id": unknown_id, "image_prompt": prompt},
    )
    assert any("not one of the approved Lena reference ids" in r for r in reasons)


# 9. Evidence must still match the queue item's own identity metadata --
# an approved id alone is not enough if the queue item claims a different
# (also-approved) id than what the evidence actually recorded.
def test_evidence_must_match_queue_item_metadata_even_if_both_ids_are_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(identity_mod, "HIGGSFIELD_DEBUG_ROOT", tmp_path)
    image_path = tmp_path / "seed.png"
    # Evidence was really recorded under the current id...
    prompt = _write_evidence(tmp_path, "2026-07-12", "mismatch-slot", CURRENT_LIVE_ID, image_path)

    # ...but the queue item's own metadata claims the historical id instead.
    reasons = validate_local_identity_evidence(
        "2026-07-12", "mismatch-slot", image_path,
        {"custom_reference_id": HISTORICAL_ID, "image_prompt": prompt},
    )
    assert any(
        "does not match this queue item's own metadata.custom_reference_id" in r
        for r in reasons
    )


# 12. No dynamic provider lookup is introduced anywhere in the evidence
# validation path (structural guarantee, not just behavioral).
def test_validate_local_identity_evidence_never_calls_subprocess() -> None:
    import inspect
    source = inspect.getsource(validate_local_identity_evidence)
    assert "subprocess" not in source
    assert "soul-id" not in source
    assert "generate get" not in source


# 13. No new live-submission path exists that selects from the approved set
# -- the executor's build_provider_argv() takes a single id parameter, and
# APPROVED_CUSTOM_REFERENCE_IDS is never imported by the executor (a
# cross-reference comment mentioning the name is fine; an actual import or
# runtime use is not).
def test_executor_never_imports_the_approved_id_set() -> None:
    assert not hasattr(executor_mod, "APPROVED_CUSTOM_REFERENCE_IDS")
    import_lines = [
        line for line in Path(executor_mod.__file__).read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    assert not any("APPROVED_CUSTOM_REFERENCE_IDS" in line for line in import_lines)
