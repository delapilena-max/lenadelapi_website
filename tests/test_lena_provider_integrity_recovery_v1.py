from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from pipeline.identity import lena_higgsfield_identity as identity
from tools import lena_bounded_live_cycle_v1 as cycle
from tools import lena_photo_qa_disposition_v1 as photo_qa
from tools import lena_provider_integrity_recovery_v1 as recovery
import pipeline.higgsfield_lena_api_executor as executor


DATE = "2026-07-17"
SLOT = "lenagate202607176924dc10-pack000-00-photo"
JOB = "97cc0b2f-5360-45db-943b-a7a146ca3590"
ORIGINAL_AUTH_SHA = "a" * 64
SEEDED_IDENTITY_UTC = "2001-01-01T00:00:00+00:00"
CUSTOM_REFERENCE_ID = sorted(identity.APPROVED_CUSTOM_REFERENCE_IDS)[-1]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "white").save(path)


def _build_recovery_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    seed_partial_recovery_artifacts: bool = False,
) -> tuple[recovery.RecoveryContract, dict[str, Path], dict[str, int]]:
    monkeypatch.setattr(recovery, "ROOT", tmp_path)
    monkeypatch.setattr(cycle, "ROOT", tmp_path)
    monkeypatch.setattr(photo_qa, "OUTPUT_ROOT", tmp_path / "pipeline" / "asset_review" / "lena")
    monkeypatch.setattr(identity, "HIGGSFIELD_DEBUG_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    report_root = tmp_path / "reports"

    auth_path = tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / DATE / f"lena_bounded_live_cycle_authorization_{DATE}_{SLOT}.json"
    claim_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT}_higgsfield_generation_claim.json"
    receipt_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT}_higgsfield_generation_execution_receipt.json"
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT / "result_manifest.json"
    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT}_seed.png"
    handoff_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / "handoff.json"
    candidate_path = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE / "candidate.json"
    policy_path = tmp_path / "pipeline" / "config" / "lena_standing_autonomy_policy_v1.json"
    _write_image(image_path)
    _write_json(candidate_path, {"candidate_id": "candidate-1", "slot_id": SLOT})
    _write_json(handoff_path, {"report_type": "lena_next_live_image_handoff", "schema_version": "v1", "date": DATE, "selected_slot_id": SLOT, "selected_candidate": {"candidate_id": "candidate-1"}, "prompt_sha256": "b" * 64, "custom_reference_id": CUSTOM_REFERENCE_ID})
    _write_json(policy_path, {"report_type": "policy"})
    authorization = {
        "report_type": "lena_standing_autonomy_cycle_authorization", "schema_version": "v1", "authorization_mode": "standing_autonomy_policy", "authorization_issuer": "lena_autonomy_controller", "single_use": True, "consumed": True, "authorization_consumed": True, "consumed_at_utc": "2026-07-19T04:21:14Z", "cycle_authorization_sha256": ORIGINAL_AUTH_SHA, "date": DATE, "slot_id": SLOT, "candidate_id": "candidate-1", "candidate_artifact_path": str(candidate_path), "candidate_artifact_sha256": _sha(candidate_path), "generation_handoff_artifact_path": str(handoff_path), "generation_handoff_artifact_sha256": _sha(handoff_path), "expected_output_directory": str(image_path.parent), "expected_output_stem": image_path.stem, "allowed_output_extensions": [".png", ".jpg", ".webp", ".bin"], "provider_call_cap_per_cycle": 1, "publish_action_cap_per_cycle": 1, "retry_cap_per_cycle": 0, "policy_artifact_path": str(policy_path), "policy_artifact_sha256": _sha(policy_path), "platform": "Instagram Feed", "caption": "caption", "custom_reference_id": CUSTOM_REFERENCE_ID, "cycle_id": "cycle-1",
    }
    _write_json(auth_path, authorization)
    claim = {"report_type": "lena_higgsfield_generation_claim", "schema_version": "v1", "approval_artifact_sha256": ORIGINAL_AUTH_SHA, "authorized_attempts": 1, "consumed_attempt_number": 1, "date": DATE, "slot_id": SLOT}
    _write_json(claim_path, claim)
    manifest = {"provider": "higgsfield", "date": DATE, "slot_id": SLOT, "provider_job_id": JOB, "provider_status": "completed", "job_type": "text2image_soul_v2", "live_attempt_count": 1, "retry_count": 0, "prompt_sha256": "b" * 64, "saved_image_path": str(image_path), "saved_image_sha256": _sha(image_path), "image_format_detected": ".png", "custom_reference_id": CUSTOM_REFERENCE_ID, "cli_soul_name": "Lena", "cli_soul_type": "soul_2"}
    _write_json(manifest_path, manifest)
    receipt = {"report_type": "lena_higgsfield_generation_execution_receipt", "schema_version": "v1", "outcome": "success", "provider_submission_may_have_occurred": True, "claim_artifact_sha256": _sha(claim_path), "provider_job_id": JOB, "output_path": str(image_path), "actual_manifest_path": (Path("pipeline/higgsfield_debug") / DATE / SLOT / "result_manifest.json").as_posix()}
    _write_json(receipt_path, receipt)
    contract = recovery.RecoveryContract(DATE, SLOT, JOB, _sha(auth_path), ORIGINAL_AUTH_SHA, _sha(claim_path), _sha(receipt_path), _sha(manifest_path), _sha(image_path))

    def fake_validate(_path: Path):
        report = json.loads(handoff_path.read_text(encoding="utf-8"))
        source = {"resolver": "content_packet_dryrun", "slot_prefix": "hcr", "pack_count": 1, "pack_variety_warnings": [], "image": {"slot_id": SLOT, "lane": "bounded-live", "soul_name": "Lena", "soul_version": "Soul 2.0", "soul_selection_mode": "provider_config_not_prompt_text", "negative_prompt_enabled": False, "image_prompt": "prompt"}}
        return report, source, {"ok": True}, {"ok": True}

    state = {"provider": 0, "qa": 0, "publish": 0}
    monkeypatch.setattr(executor, "_validate_handoff_packet", fake_validate)
    monkeypatch.setattr(executor, "execute_approved_handoff_live_generation", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("provider execution is forbidden during recovery")))

    reference = tmp_path / "reference.json"
    _write_json(reference, {"references": []})
    monkeypatch.setattr(cycle, "_load_reference_specs", lambda: (reference, _sha(reference), []))
    paths = recovery._paths(contract, report_root)
    if seed_partial_recovery_artifacts:
        cycle._build_local_identity_evidence(
            date_str=DATE,
            slot_id=SLOT,
            manifest=manifest,
            image_path=image_path,
            image_sha256=_sha(image_path),
            identity_evidence_path=paths["identity"],
        )
        identity_record = json.loads(paths["identity"].read_text(encoding="utf-8"))
        identity_record["verified_at_utc"] = SEEDED_IDENTITY_UTC
        _write_json(paths["identity"], identity_record)
        _write_json(
            paths["attestation"],
            {
                "report_type": "lena_provider_integrity_recovery_attestation",
                "schema_version": "v1",
                "date": DATE,
                "slot_id": SLOT,
                "provider_job_id": JOB,
                "authorization_artifact_path": cycle._repo_relative(paths["authorization"]),
                "authorization_artifact_sha256": _sha(auth_path),
                "original_authorization_sha256": ORIGINAL_AUTH_SHA,
                "claim_artifact_path": cycle._repo_relative(paths["claim"]),
                "claim_artifact_sha256": _sha(claim_path),
                "original_provider_receipt_path": cycle._repo_relative(paths["receipt"]),
                "original_provider_receipt_sha256": _sha(receipt_path),
                "manifest_path": cycle._repo_relative(paths["manifest"]),
                "manifest_sha256": _sha(manifest_path),
                "generated_image_path": cycle._repo_relative(paths["image"]),
                "generated_image_sha256": _sha(image_path),
                "provider_calls_performed": 1,
                "provider_calls_during_recovery": 0,
                "publish_calls_performed": 0,
                "retries_performed": 0,
                "resume_from_stage": "image_qa",
            },
        )
    paths["report_root"] = report_root
    return contract, paths, state


def _run_valid(contract: recovery.RecoveryContract, paths: dict[str, Path], state: dict[str, int]) -> dict:
    def qa_evaluator(**_kwargs):
        state["qa"] += 1
        return {"slot_id": SLOT, "image_sha256": contract.image_sha256, "generation_provenance": {"date": DATE}, "disposition": "accept", "overall": "pass"}

    def qa_writer(artifact):
        path = photo_qa.OUTPUT_ROOT / DATE / f"{SLOT}__{contract.image_sha256}_qa_disposition.json"
        _write_json(path, artifact)
        return path, artifact, True

    def publisher(**_kwargs):
        state["publish"] += 1
        return {"parsed": {"post_id": "post-1", "post_url": "https://example.invalid/post-1", "posted_at": "2026-07-19T05:00:00Z"}, "returncode": 0, "stdout": "{}", "stderr": ""}

    return recovery.run_recovery(contract=contract, report_root=paths["report_root"], qa_evaluator=qa_evaluator, qa_writer=qa_writer, publisher=publisher)


def _run_with_custom_qa(
    contract: recovery.RecoveryContract,
    paths: dict[str, Path],
    state: dict[str, int],
    *,
    qa_evaluator,
    qa_writer,
) -> dict:
    def publisher(**_kwargs):
        state["publish"] += 1
        return {"parsed": {"post_id": "post-1", "post_url": "https://example.invalid/post-1", "posted_at": "2026-07-19T05:00:00Z"}, "returncode": 0, "stdout": "{}", "stderr": ""}

    return recovery.run_recovery(contract=contract, report_root=paths["report_root"], qa_evaluator=qa_evaluator, qa_writer=qa_writer, publisher=publisher)


def test_valid_recovery_skips_provider_and_reaches_one_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch, seed_partial_recovery_artifacts=True)
    identity_before = paths["identity"].read_bytes()

    original_write_json_atomic = cycle._write_json_atomic

    def guarded_write_json_atomic(path: Path, value: dict) -> None:
        if Path(path).resolve() == paths["identity"].resolve():
            raise AssertionError("identity evidence must be reused, not rewritten")
        original_write_json_atomic(path, value)

    monkeypatch.setattr(cycle, "_write_json_atomic", guarded_write_json_atomic)

    report = _run_valid(contract, paths, state)
    assert report["ok"] is True
    assert report["provider_calls_during_recovery"] == 0
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert report["retries_performed"] == 0
    assert state == {"provider": 0, "qa": 1, "publish": 1}
    assert paths["identity"].read_bytes() == identity_before
    assert json.loads(paths["identity"].read_text(encoding="utf-8"))["verified_at_utc"] == SEEDED_IDENTITY_UTC
    attestation = json.loads(paths["attestation"].read_text(encoding="utf-8"))
    assert attestation["original_provider_receipt_sha256"] == contract.receipt_sha256
    assert attestation["manifest_sha256"] == contract.manifest_sha256
    assert attestation["generated_image_sha256"] == contract.image_sha256


def test_missing_reference_fails_before_identity_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch)
    identity_calls = {"count": 0}

    def missing_reference_specs():
        raise cycle.LenaBoundedLiveCycleError("reference_path_escape", "reference artifact does not exist: missing")

    def spy_identity(**_kwargs):
        identity_calls["count"] += 1
        raise AssertionError("identity evidence should not be written when references are missing")

    monkeypatch.setattr(cycle, "_load_reference_specs", missing_reference_specs)
    monkeypatch.setattr(cycle, "_build_local_identity_evidence", spy_identity)
    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc:
        _run_valid(contract, paths, state)
    assert exc.value.code == "reference_path_escape"
    assert identity_calls["count"] == 0
    assert not paths["identity"].exists()
    assert not paths["attestation"].exists()
    assert state == {"provider": 0, "qa": 0, "publish": 0}


def test_recovery_reuses_matching_partial_identity_and_publishes_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch, seed_partial_recovery_artifacts=True)
    identity_before = paths["identity"].read_bytes()
    original_write_json_atomic = cycle._write_json_atomic
    identity_writes = {"count": 0}

    def guarded_write_json_atomic(path: Path, value: dict) -> None:
        if Path(path).resolve() == paths["identity"].resolve():
            identity_writes["count"] += 1
            raise AssertionError("matching partial identity evidence should be reused")
        original_write_json_atomic(path, value)

    monkeypatch.setattr(cycle, "_write_json_atomic", guarded_write_json_atomic)
    report = _run_valid(contract, paths, state)
    assert report["ok"] is True
    assert report["provider_calls_during_recovery"] == 0
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert identity_writes["count"] == 0
    assert paths["identity"].read_bytes() == identity_before
    assert state == {"provider": 0, "qa": 1, "publish": 1}


def test_recovery_binds_qa_disposition_artifact_from_trusted_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch, seed_partial_recovery_artifacts=True)

    def qa_evaluator(**_kwargs):
        state["qa"] += 1
        return {
            "schema_version": photo_qa.SCHEMA_VERSION,
            "influencer_id": "lena",
            "slot_id": None,
            "candidate_id": None,
            "image_sha256": None,
            "generation_provenance": {},
            "disposition": "accept",
            "overall": "pass",
        }

    def qa_writer(artifact):
        return photo_qa.write_disposition_artifact(artifact, photo_qa.OUTPUT_ROOT)

    report = _run_with_custom_qa(contract, paths, state, qa_evaluator=qa_evaluator, qa_writer=qa_writer)
    qa_path = photo_qa.OUTPUT_ROOT / DATE / f"{SLOT}__{contract.image_sha256}_qa_disposition.json"
    assert report["ok"] is True
    assert report["provider_calls_during_recovery"] == 0
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert state == {"provider": 0, "qa": 1, "publish": 1}
    assert qa_path.exists()
    qa_record = json.loads(qa_path.read_text(encoding="utf-8"))
    assert qa_record["schema_version"] == photo_qa.SCHEMA_VERSION
    assert qa_record["influencer_id"] == "lena"
    assert qa_record["slot_id"] == SLOT
    assert qa_record["image_sha256"] == contract.image_sha256
    assert qa_record["generation_provenance"]["date"] == DATE
    assert qa_record["generation_provenance"]["provider_job_id"] == JOB
    assert qa_record["generation_provenance"]["manifest_sha256"] == contract.manifest_sha256
    assert qa_record["generation_provenance"]["generated_image_sha256"] == contract.image_sha256
    assert qa_record["generation_provenance"]["recovery_attestation_sha256"] == _sha(paths["attestation"])
    assert qa_record["generation_provenance"]["identity_evidence_sha256"] == _sha(paths["identity"])


def test_recovery_rejects_conflicting_qa_disposition_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch)

    def qa_evaluator(**_kwargs):
        state["qa"] += 1
        return {
            "schema_version": photo_qa.SCHEMA_VERSION,
            "influencer_id": "lena",
            "slot_id": "not-the-slot",
            "candidate_id": "candidate-1",
            "image_sha256": contract.image_sha256,
            "generation_provenance": {"date": DATE},
            "disposition": "accept",
            "overall": "pass",
        }

    def qa_writer(_artifact):
        raise AssertionError("writer should not be reached when the QA disposition binding conflicts")

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc:
        _run_with_custom_qa(contract, paths, state, qa_evaluator=qa_evaluator, qa_writer=qa_writer)
    assert exc.value.code == "recovery_qa_disposition_binding_mismatch"
    assert state == {"provider": 0, "qa": 1, "publish": 0}


@pytest.mark.parametrize("target", ["image", "manifest", "receipt", "claim", "authorization"])
def test_recovery_rejects_artifact_sha_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch)
    paths[target].write_bytes(paths[target].read_bytes() + b"tamper")
    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc:
        _run_valid(contract, paths, state)
    assert exc.value.code == f"recovery_{target}_sha_mismatch"
    assert state == {"provider": 0, "qa": 0, "publish": 0}


def test_recovery_rejects_job_id_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch)
    receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    receipt["provider_job_id"] = "wrong-job"
    _write_json(paths["receipt"], receipt)
    contract = replace(contract, receipt_sha256=_sha(paths["receipt"]))
    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc:
        _run_valid(contract, paths, state)
    assert exc.value.code == "recovery_receipt_job_mismatch"
    assert state["publish"] == 0


@pytest.mark.parametrize("kind", ["qa", "package", "publish", "completed_aggregate"])
def test_recovery_rejects_prior_downstream_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch)
    if kind == "qa":
        _write_json(photo_qa.OUTPUT_ROOT / DATE / f"{SLOT}__{contract.image_sha256}_qa_disposition.json", {"disposition": "accept"})
    elif kind == "package":
        _write_json(paths["package"], {"ok": True, "slot_id": SLOT})
    elif kind == "publish":
        _write_json(paths["image"].with_suffix(".status.json"), {"published": False})
    else:
        _write_json(paths["report_root"] / DATE / "lena_bounded_live_cycle_prior.json", {"ok": True, "slot_id": SLOT})
    with pytest.raises(cycle.LenaBoundedLiveCycleError):
        _run_valid(contract, paths, state)
    assert state == {"provider": 0, "qa": 0, "publish": 0}


def test_recovery_rejects_mismatched_partial_identity_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract, paths, state = _build_recovery_bundle(tmp_path, monkeypatch, seed_partial_recovery_artifacts=True)
    identity_record = json.loads(paths["identity"].read_text(encoding="utf-8"))
    identity_record["local_image_sha256"] = "0" * 64
    _write_json(paths["identity"], identity_record)
    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc:
        _run_valid(contract, paths, state)
    assert exc.value.code == "recovery_identity_evidence_mismatch"
    assert state == {"provider": 0, "qa": 0, "publish": 0}
