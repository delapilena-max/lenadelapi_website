from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pipeline.identity import lena_higgsfield_identity as identity
from tools import lena_bounded_live_cycle_v1 as cycle
from tools import lena_photo_qa_disposition_v1 as photo_qa
import pipeline.higgsfield_lena_api_executor as executor


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles"


@dataclass(frozen=True)
class RecoveryContract:
    date: str
    slot_id: str
    provider_job_id: str
    authorization_sha256: str
    original_authorization_sha256: str
    claim_sha256: str
    receipt_sha256: str
    manifest_sha256: str
    image_sha256: str


PRODUCTION_CONTRACT = RecoveryContract(
    date="2026-07-17",
    slot_id="lenagate202607176924dc10-pack000-00-photo",
    provider_job_id="97cc0b2f-5360-45db-943b-a7a146ca3590",
    authorization_sha256="41c0f618deea4e627c5b8bf37d91759e433bc46e6bab94991cfb3daec57c36db",
    original_authorization_sha256="166ee575033ce85f9912662e2de8f07579ed7359479d8669f886cabc1ec89c1c",
    claim_sha256="705382d841dc202e149ac3668f538c4efc791140bf8b70609a3c31b5a950d93e",
    receipt_sha256="2fc8fcfd9cc91c4a7b4d51389a1bd70d95e8597f2a833f4075c26c0299ce1007",
    manifest_sha256="56c0f251bf0367b809713e255edb3cf0997f0224b5c84ebfb2d6ac2a1e7dd82b",
    image_sha256="218834049bf77c07d8e4cf9273f4a82d0080b81fca4b94a52e01f1d7baecc7e8",
)


def _paths(contract: RecoveryContract, report_root: Path) -> dict[str, Path]:
    date_str = contract.date
    slot_id = contract.slot_id
    recovery_root = report_root / date_str / slot_id
    return {
        "authorization": ROOT / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / date_str / f"lena_bounded_live_cycle_authorization_{date_str}_{slot_id}.json",
        "claim": ROOT / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{slot_id}_higgsfield_generation_claim.json",
        "receipt": ROOT / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{slot_id}_higgsfield_generation_execution_receipt.json",
        "manifest": ROOT / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json",
        "image": ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.png",
        "identity": identity.identity_verification_evidence_path(date_str, slot_id),
        "attestation": recovery_root / f"lena_provider_integrity_recovery_attestation_{date_str}.json",
        "package": recovery_root / f"lena_bounded_live_cycle_package_{date_str}.json",
        "publish_payload": recovery_root / f"lena_bounded_live_cycle_publish_payload_{date_str}.json",
        "publish_receipt": recovery_root / f"lena_bounded_live_cycle_publish_receipt_{date_str}.json",
        "analytics": recovery_root / f"lena_bounded_live_cycle_analytics_handoff_{date_str}.json",
        "aggregate": recovery_root / f"lena_bounded_live_cycle_recovery_{date_str}.json",
    }


def _load_bound_json(path: Path, expected_sha: str, label: str) -> dict[str, Any]:
    cycle._ensure_path_within_root(path, ROOT, code=f"recovery_{label}_path_escape", label=label, must_exist=True)
    observed_sha = cycle._sha256_file(path)
    cycle._require(observed_sha == expected_sha, f"recovery_{label}_sha_mismatch", f"{label} SHA-256 does not match the recovery contract")
    return cycle._read_json_object(path, code=f"recovery_{label}_invalid", label=label)


def _assert_no_prior_downstream_evidence(paths: dict[str, Path], contract: RecoveryContract, report_root: Path) -> None:
    qa_root = photo_qa.OUTPUT_ROOT / contract.date
    qa_matches = list(qa_root.glob(f"{contract.slot_id}__*_qa_disposition.json")) if qa_root.exists() else []
    legacy_qa = photo_qa.OUTPUT_ROOT / "presence_output_qa" / contract.date / contract.slot_id
    cycle._require(not qa_matches and not legacy_qa.exists(), "recovery_prior_qa_evidence", "QA evidence already exists")
    for key in ("package", "publish_payload", "publish_receipt", "analytics", "aggregate"):
        cycle._require(not paths[key].exists(), f"recovery_prior_{key}_evidence", f"recovery {key} evidence already exists")
    cycle._require(not paths["image"].with_suffix(".status.json").exists(), "recovery_prior_publish_evidence", "publish sidecar already exists")
    day_root = report_root / contract.date
    if day_root.exists():
        for aggregate_path in day_root.glob("lena_bounded_live_cycle_*.json"):
            aggregate = cycle._read_json_object(aggregate_path, code="recovery_aggregate_invalid", label="bounded live aggregate receipt")
            if aggregate.get("ok") is True and (
                str(aggregate.get("authorized_scope", {}).get("slot_id") or aggregate.get("slot_id") or "") == contract.slot_id
            ):
                raise cycle.LenaBoundedLiveCycleError("recovery_completed_aggregate_exists", "a completed aggregate receipt already exists")


def _bound_recovery_qa_disposition_artifact(
    qa_artifact: dict[str, Any],
    *,
    contract: RecoveryContract,
    paths: dict[str, Path],
    authorization: dict[str, Any],
    identity_sha256: str,
    attestation_sha256: str,
) -> tuple[dict[str, Any], Path]:
    if not isinstance(qa_artifact, dict):
        raise cycle.LenaBoundedLiveCycleError("recovery_qa_disposition_invalid", "QA disposition artifact must be a JSON object")

    def _require_or_bind(container: dict[str, Any], key: str, expected: Any, *, label: str) -> None:
        actual = container.get(key)
        if actual not in (None, "", expected):
            raise cycle.LenaBoundedLiveCycleError(
                "recovery_qa_disposition_binding_mismatch",
                f"{label} does not match the recovery binding",
            )
        container[key] = expected

    bound = json.loads(json.dumps(qa_artifact))
    _require_or_bind(bound, "schema_version", photo_qa.SCHEMA_VERSION, label="schema_version")
    _require_or_bind(bound, "influencer_id", "lena", label="influencer_id")
    _require_or_bind(bound, "slot_id", contract.slot_id, label="slot_id")
    _require_or_bind(bound, "image_sha256", contract.image_sha256, label="image_sha256")
    _require_or_bind(bound, "candidate_id", authorization.get("candidate_id"), label="candidate_id")

    provenance = bound.get("generation_provenance")
    if provenance is None:
        provenance = {}
    elif not isinstance(provenance, dict):
        raise cycle.LenaBoundedLiveCycleError("recovery_qa_disposition_invalid", "generation_provenance must be a JSON object")
    else:
        provenance = dict(provenance)

    _require_or_bind(provenance, "date", contract.date, label="generation_provenance.date")
    _require_or_bind(provenance, "provider_job_id", contract.provider_job_id, label="generation_provenance.provider_job_id")
    _require_or_bind(provenance, "manifest_path", cycle._repo_relative(paths["manifest"]), label="generation_provenance.manifest_path")
    _require_or_bind(provenance, "manifest_sha256", contract.manifest_sha256, label="generation_provenance.manifest_sha256")
    _require_or_bind(provenance, "generated_image_path", cycle._repo_relative(paths["image"]), label="generation_provenance.generated_image_path")
    _require_or_bind(provenance, "generated_image_sha256", contract.image_sha256, label="generation_provenance.generated_image_sha256")
    _require_or_bind(provenance, "recovery_attestation_path", cycle._repo_relative(paths["attestation"]), label="generation_provenance.recovery_attestation_path")
    _require_or_bind(provenance, "recovery_attestation_sha256", attestation_sha256, label="generation_provenance.recovery_attestation_sha256")
    _require_or_bind(provenance, "identity_evidence_path", cycle._repo_relative(paths["identity"]), label="generation_provenance.identity_evidence_path")
    _require_or_bind(provenance, "identity_evidence_sha256", identity_sha256, label="generation_provenance.identity_evidence_sha256")
    bound["generation_provenance"] = provenance

    disposition_path = photo_qa.disposition_artifact_path(bound, photo_qa.OUTPUT_ROOT)
    return bound, disposition_path


def _validate_recovery_evidence(contract: RecoveryContract, report_root: Path) -> dict[str, Any]:
    paths = _paths(contract, report_root)
    authorization = _load_bound_json(paths["authorization"], contract.authorization_sha256, "authorization")
    claim = _load_bound_json(paths["claim"], contract.claim_sha256, "claim")
    receipt = _load_bound_json(paths["receipt"], contract.receipt_sha256, "receipt")
    manifest = _load_bound_json(paths["manifest"], contract.manifest_sha256, "manifest")
    cycle._ensure_path_within_root(paths["image"], ROOT / "pipeline" / "higgsfield_library" / "lena", code="recovery_image_path_escape", label="generated image", must_exist=True)
    cycle._require(cycle._sha256_file(paths["image"]) == contract.image_sha256, "recovery_image_sha_mismatch", "generated image SHA-256 does not match the recovery contract")

    cycle._require(authorization.get("single_use") is True and authorization.get("consumed") is True and authorization.get("authorization_consumed") is True, "recovery_authorization_not_consumed", "recovery requires the consumed original single-use authorization")
    cycle._require(str(authorization.get("cycle_authorization_sha256") or "") == contract.original_authorization_sha256, "recovery_original_authorization_sha_mismatch", "original pre-consumption authorization SHA-256 mismatch")
    cycle._require(str(authorization.get("authorization_mode") or "") == "standing_autonomy_policy", "recovery_authorization_mode_invalid", "authorization must use standing autonomy mode")
    cycle._require(int(authorization.get("provider_call_cap_per_cycle", 0)) == 1, "recovery_provider_cap_invalid", "provider cap must remain one")
    cycle._require(int(authorization.get("publish_action_cap_per_cycle", 0)) == 1, "recovery_publish_cap_invalid", "publish cap must remain one")
    cycle._require(int(authorization.get("retry_cap_per_cycle", -1)) == 0, "recovery_retry_cap_invalid", "retry cap must remain zero")
    cycle._require(str(authorization.get("slot_id") or "") == contract.slot_id, "recovery_authorization_slot_mismatch", "authorization slot mismatch")
    cycle._require(str(claim.get("approval_artifact_sha256") or "") == contract.original_authorization_sha256, "recovery_claim_authorization_mismatch", "claim is not bound to the original authorization")
    cycle._require(int(claim.get("authorized_attempts", 0)) == 1 and int(claim.get("consumed_attempt_number", 0)) == 1, "recovery_claim_attempt_count_invalid", "claim must record exactly one authorized and consumed attempt")
    cycle._require(str(receipt.get("claim_artifact_sha256") or "") == contract.claim_sha256, "recovery_receipt_claim_mismatch", "receipt claim SHA binding mismatch")
    cycle._require(receipt.get("outcome") == "success" and receipt.get("provider_submission_may_have_occurred") is True, "recovery_receipt_outcome_invalid", "receipt must record one successful provider submission")
    cycle._require(str(receipt.get("provider_job_id") or "") == contract.provider_job_id, "recovery_receipt_job_mismatch", "receipt provider job ID mismatch")
    cycle._require(str(manifest.get("provider_job_id") or "") == contract.provider_job_id, "recovery_manifest_job_mismatch", "manifest provider job ID mismatch")
    cycle._require(int(manifest.get("live_attempt_count", 0)) == 1 and int(manifest.get("retry_count", -1)) == 0, "recovery_manifest_attempt_count_invalid", "manifest must record exactly one provider attempt and zero retries")
    cycle._require(Path(str(receipt.get("output_path") or "")).resolve() == paths["image"].resolve(), "recovery_receipt_image_path_mismatch", "receipt output path mismatch")
    expected_manifest_repo_path = (Path("pipeline/higgsfield_debug") / contract.date / contract.slot_id / "result_manifest.json").as_posix()
    cycle._require(Path(str(receipt.get("actual_manifest_path") or "")).as_posix() == expected_manifest_repo_path, "recovery_receipt_manifest_path_mismatch", "receipt manifest path mismatch")
    cycle._require(Path(str(manifest.get("saved_image_path") or "")).resolve() == paths["image"].resolve(), "recovery_manifest_image_path_mismatch", "manifest image path mismatch")
    _assert_no_prior_downstream_evidence(paths, contract, report_root)
    return {"paths": paths, "authorization": authorization, "claim": claim, "receipt": receipt, "manifest": manifest}


def run_recovery(
    *,
    contract: RecoveryContract = PRODUCTION_CONTRACT,
    report_root: Path = REPORT_ROOT,
    qa_evaluator: Callable[..., dict[str, Any]] = photo_qa.evaluate_photo_qa_disposition,
    qa_writer: Callable[..., tuple[Path, dict[str, Any], bool]] = photo_qa.write_disposition_artifact,
    publisher: Callable[..., dict[str, Any]] = cycle._run_publisher,
) -> dict[str, Any]:
    evidence = _validate_recovery_evidence(contract, report_root)
    paths = evidence["paths"]
    authorization = evidence["authorization"]
    reference_authority_path, reference_authority_sha, reference_specs = cycle._load_reference_specs()
    handoff_path = Path(str(authorization.get("generation_handoff_artifact_path") or ""))
    cycle._require(cycle._sha256_file(handoff_path) == str(authorization.get("generation_handoff_artifact_sha256") or ""), "recovery_handoff_sha_mismatch", "handoff SHA binding mismatch")
    handoff_report, source, packet_validation, validation = executor._validate_handoff_packet(handoff_path)
    candidate_path = Path(str(authorization.get("candidate_artifact_path") or ""))
    cycle._require(cycle._sha256_file(candidate_path) == str(authorization.get("candidate_artifact_sha256") or ""), "recovery_candidate_sha_mismatch", "candidate SHA binding mismatch")

    auth = {
        "artifact": authorization,
        "path": paths["authorization"],
        "sha256": contract.authorization_sha256,
        "pre_consumption_sha256": contract.original_authorization_sha256,
        "consumed_at_utc": authorization.get("consumed_at_utc"),
        "handoff": {"path": handoff_path, "sha256": cycle._sha256_file(handoff_path), "report": handoff_report, "source": source, "packet_validation": packet_validation, "validation": validation},
        "policy": {"path": Path(str(authorization.get("policy_artifact_path"))), "sha256": str(authorization.get("policy_artifact_sha256") or "")},
    }
    live_requirements = {
        "handoff_path": handoff_path.resolve(),
        "candidate_path": candidate_path.resolve(),
        "expected_output_directory": paths["image"].parent,
        "expected_output_stem": paths["image"].stem,
        "allowed_output_extensions": list(authorization.get("allowed_output_extensions") or []),
    }
    approval_result = cycle._build_autonomous_approval_result(auth, live_requirements)
    _assert_no_prior_downstream_evidence(paths, contract, report_root)

    identity_path, _, _ = cycle._build_local_identity_evidence(
        date_str=contract.date,
        slot_id=contract.slot_id,
        manifest=evidence["manifest"],
        image_path=paths["image"],
        image_sha256=contract.image_sha256,
        identity_evidence_path=paths["identity"],
    )
    attestation = {
        "report_type": "lena_provider_integrity_recovery_attestation",
        "schema_version": "v1",
        "date": contract.date,
        "slot_id": contract.slot_id,
        "provider_job_id": contract.provider_job_id,
        "authorization_artifact_path": cycle._repo_relative(paths["authorization"]),
        "authorization_artifact_sha256": contract.authorization_sha256,
        "original_authorization_sha256": contract.original_authorization_sha256,
        "claim_artifact_path": cycle._repo_relative(paths["claim"]),
        "claim_artifact_sha256": contract.claim_sha256,
        "original_provider_receipt_path": cycle._repo_relative(paths["receipt"]),
        "original_provider_receipt_sha256": contract.receipt_sha256,
        "manifest_path": cycle._repo_relative(paths["manifest"]),
        "manifest_sha256": contract.manifest_sha256,
        "generated_image_path": cycle._repo_relative(paths["image"]),
        "generated_image_sha256": contract.image_sha256,
        "provider_calls_performed": 1,
        "provider_calls_during_recovery": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "resume_from_stage": "image_qa",
    }
    attestation_cmp = dict(attestation)
    attestation_cmp.pop("created_at_utc", None)
    if paths["attestation"].exists():
        existing_attestation = cycle._read_json_object(paths["attestation"], code="recovery_attestation_existing_invalid", label="recovery attestation")
        existing_cmp = dict(existing_attestation)
        existing_cmp.pop("created_at_utc", None)
        cycle._require(existing_cmp == attestation_cmp, "recovery_attestation_already_exists", "conflicting recovery attestation already exists")
        attestation = existing_attestation
    else:
        cycle._write_json_atomic(paths["attestation"], attestation)
    attestation_sha = cycle._sha256_file(paths["attestation"])
    qa_artifact = qa_evaluator(decision_path=paths["authorization"], manifest_path=paths["manifest"], image_path=paths["image"], identity_evidence_path=identity_path, reference_specs=reference_specs, reference_authority_artifact=reference_authority_path, reference_authority_sha256=reference_authority_sha, expected_image_sha256=contract.image_sha256)
    qa_artifact, expected_qa_path = _bound_recovery_qa_disposition_artifact(
        qa_artifact,
        contract=contract,
        paths=paths,
        authorization=authorization,
        identity_sha256=cycle._sha256_file(identity_path),
        attestation_sha256=attestation_sha,
    )
    qa_path, qa_record, _ = qa_writer(qa_artifact)
    cycle._require(qa_path.resolve() == expected_qa_path.resolve(), "recovery_qa_disposition_path_mismatch", "QA disposition path does not match the bound recovery artifact")
    cycle._require(str(qa_record.get("disposition") or "") == "accept", "qa_rejected", "photo QA did not accept the generated image")
    cycle._require(str(qa_record.get("overall") or "pass") in {"pass", "approved"}, "qa_overall_invalid", "photo QA artifact did not pass overall")

    sidecar_path, _, sidecar_sha = cycle._build_live_publish_sidecar(authorization=auth, image_path=paths["image"], caption=str(authorization["caption"]), platform=str(authorization["platform"]))
    provider_result = {"live_result": {"job_id": contract.provider_job_id, "status": "completed", "saved_image_path": str(paths["image"])}, "manifest": evidence["manifest"], "manifest_path": paths["manifest"], "manifest_sha256": contract.manifest_sha256, "generated_image_sha256": contract.image_sha256}
    package_path, _ = cycle._build_live_package(auth=auth, approval_result=approval_result, provider_result=provider_result, qa_result={"path": qa_path, "sha256": cycle._sha256_file(qa_path), "artifact": qa_record}, package_path=paths["package"], publish_sidecar_path=sidecar_path, publish_sidecar_sha256=sidecar_sha)
    package_sha = cycle._sha256_file(package_path)
    publish_payload = {"report_type": "lena_bounded_live_cycle_publish_payload", "schema_version": "v1", "cycle_id": authorization.get("cycle_id"), "authorization_mode": "standing_autonomy_policy", "platform": authorization["platform"], "media_type": "photo", "slot_id": contract.slot_id, "candidate_id": authorization["candidate_id"], "caption": authorization["caption"], "asset_path": str(paths["image"]), "asset_sha256": contract.image_sha256, "generated_image_path": str(paths["image"]), "generated_image_sha256": contract.image_sha256, "package_artifact_path": str(package_path), "package_artifact_sha256": package_sha, "publish_sidecar_path": str(sidecar_path), "publish_sidecar_sha256": sidecar_sha, "policy_artifact_path": authorization.get("policy_artifact_path"), "policy_artifact_sha256": authorization.get("policy_artifact_sha256"), "cycle_authorization_path": str(paths["authorization"]), "cycle_authorization_sha256": contract.original_authorization_sha256, "recovery_attestation_path": str(paths["attestation"]), "recovery_attestation_sha256": attestation_sha}
    cycle._write_json_atomic(paths["publish_payload"], publish_payload)
    publish_payload_sha = cycle._sha256_file(paths["publish_payload"])
    publisher_result = publisher(platform=str(authorization["platform"]), payload_path=paths["publish_payload"])
    _, publish_receipt = cycle._build_live_publish_receipt(auth=auth, package_path=package_path, package_sha256=package_sha, publish_sidecar_path=sidecar_path, publish_sidecar_sha256=sidecar_sha, publisher_result={**publisher_result, "payload_path": paths["publish_payload"], "payload_sha256": publish_payload_sha}, publish_receipt_path=paths["publish_receipt"])
    _, analytics = cycle._build_live_analytics_handoff(auth=auth, package_path=package_path, package_sha256=package_sha, publish_receipt_path=paths["publish_receipt"], publish_receipt_sha256=cycle._sha256_file(paths["publish_receipt"]), analytics_handoff_path=paths["analytics"])
    report = {"ok": True, "report_type": "lena_bounded_live_cycle", "version": "v1", "recovery_mode": True, "date": contract.date, "slot_id": contract.slot_id, "cycle_id": authorization.get("cycle_id"), "authorization_consumed": True, "provider_calls_performed": 1, "provider_calls_during_recovery": 0, "provider_job_id": contract.provider_job_id, "publish_calls_performed": 1, "retries_performed": 0, "generated_image_path": str(paths["image"]), "generated_image_sha256": contract.image_sha256, "recovery_attestation_path": str(paths["attestation"]), "recovery_attestation_sha256": attestation_sha, "qa_artifact": qa_record, "publish_receipt": publish_receipt, "analytics_handoff": analytics}
    cycle._write_json_atomic(paths["aggregate"], report)
    report["report_path"] = str(paths["aggregate"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume the one bound Lena generation from QA onward without provider access.")
    parser.add_argument("--live", action="store_true", help="Run QA and the single bounded publish action.")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("--live is required; validation-only recovery is not implemented")
    try:
        result = run_recovery()
    except cycle.LenaBoundedLiveCycleError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
