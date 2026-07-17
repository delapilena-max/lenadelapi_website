from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_output_qa_v1 as qa_module
from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools.strategy import lena_run_generated_asset_qa_v1 as lifecycle
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


STATUSES = ("not_evaluated", "not_assessable", "aligned", "findings_present", "error")


def _compiled_plan() -> dict[str, object]:
    return plan_module.compile_human_presence_prompt_plan(lena_profile.build_lena_presence_contract(), medium="still_image")


def _write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    path.write_text(data, encoding="utf-8")
    import hashlib

    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _base_payloads(tmp_path: Path) -> dict[str, Path]:
    account = tmp_path / "pipeline" / "strategy" / "lena" / "live_generation_accounting" / "2026-07-17" / "lena_live_generation_accounting_2026-07-17_slot.json"
    decision = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / "2026-07-17" / "lena_pre_generation_candidate_selected.json"
    approval_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / "2026-07-17" / "slot_higgsfield_generation_approval.json"
    manifest = tmp_path / "pipeline" / "higgsfield_debug" / "2026-07-17" / "slot" / "result_manifest.json"
    image = tmp_path / "pipeline" / "higgsfield_debug" / "2026-07-17" / "slot" / "result.png"
    claim = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / "2026-07-17" / "slot_higgsfield_generation_claim.json"
    receipt = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / "2026-07-17" / "slot_higgsfield_generation_execution_receipt.json"
    for path in (account, decision, approval_path, manifest, image, claim, receipt):
        path.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\xaeB`\x82")
    return {
        "account": account,
        "decision": decision,
        "approval": approval_path,
        "manifest": manifest,
        "image": image,
        "claim": claim,
        "receipt": receipt,
    }


def _install_approval_monkeypatch(monkeypatch: pytest.MonkeyPatch, paths: dict[str, Path]) -> None:
    monkeypatch.setattr(lifecycle.autonomy_ladder, "assert_allowed", lambda *args, **kwargs: None)
    monkeypatch.setattr(lifecycle, "_load_accounting_report", lambda *_args, **_kwargs: _accounting_report(paths))
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *_args, **_kwargs: {"approval": {"report_type": approval.APPROVAL_REPORT_TYPE, "schema_version": approval.APPROVAL_SCHEMA_VERSION}})

    def build_claim(_: dict[str, object]) -> dict[str, object]:
        return {
            "report_type": approval.CLAIM_REPORT_TYPE,
            "schema_version": approval.CLAIM_SCHEMA_VERSION,
            "claim_type": approval.CLAIM_TYPE,
            "date": "2026-07-17",
            "slot_id": "slot",
            "approved_at_utc": "2026-07-17T00:00:00Z",
            "claim_written_at_utc": "2026-07-17T00:00:00Z",
        }

    def build_receipt(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "report_type": approval.RECEIPT_REPORT_TYPE,
            "schema_version": approval.RECEIPT_SCHEMA_VERSION,
            "receipt_type": approval.RECEIPT_TYPE,
            "date": "2026-07-17",
            "slot_id": "slot",
            "approved_at_utc": "2026-07-17T00:00:00Z",
            "receipt_written_at_utc": "2026-07-17T00:00:00Z",
            "provider_job_id": "job",
            "provider_status": "completed",
            "output_path": str(paths["image"].resolve()),
            "image_format_detected": "png",
            "actual_manifest_path": paths["manifest"].resolve().as_posix(),
        }

    monkeypatch.setattr(approval, "build_generation_claim_record", build_claim)
    monkeypatch.setattr(approval, "build_generation_execution_receipt_record", build_receipt)
    monkeypatch.setattr(lifecycle.qa_disposition, "write_disposition_artifact", lambda artifact, output_root=None: (output_root / "qa.json", artifact, True))


def _accounting_report(paths: dict[str, Path]) -> dict[str, object]:
    return {
        "report_type": "lena_live_generation_accounting",
        "schema_version": "v1",
        "date": "2026-07-17",
        "slot_id": "slot",
        "recipe_id": "hcr_012",
        "approval_artifact": str(paths["approval"]),
        "executor_result_manifest": str(paths["manifest"]),
        "generated_output_paths": {"saved_image_path": str(paths["image"].resolve()), "manifest_path": paths["manifest"].resolve().as_posix()},
        "generation_claim_artifact": paths["claim"].resolve().as_posix(),
        "generation_receipt_artifact": paths["receipt"].resolve().as_posix(),
        "live_generation_accounted": True,
        "publish_authorized": False,
        "publish_performed": False,
        "queue_mutated": False,
        "qa_disposition_required": True,
        "claim_written": True,
        "receipt_written": True,
        "subprocess_start_attempted": False,
        "provider_submission_may_have_occurred": False,
    }


def _decision_report(plan: dict[str, object]) -> dict[str, object]:
    return {
        "evidence": {"prompt_pack": {"human_presence": plan}},
        "candidate_status": "selected",
        "candidate": {"slot_id": "slot", "recipe_id": "hcr_012", "candidate_id": "candidate", "prompt_sha256": "a" * 64},
    }


def _qa_runner(**_: object) -> dict[str, object]:
    return {
        "report_type": "lena_photo_qa",
        "schema_version": "lena_photo_qa_v1",
        "disposition": "accept",
        "qa_status": "accept",
        "retry_eligible": False,
    }


def _presence_runner(status: str):
    def _runner(**_: object) -> tuple[Path, dict[str, object]]:
        return (
            Path("presence.json"),
            {
                "report_type": qa_module.REPORT_TYPE,
                "schema_version": qa_module.SCHEMA_VERSION_V2,
                "medium": "still_image",
                "evaluator_version": "hpe_2c_pr3_integrity_semantic_v1",
                "generated_at_utc": "2026-07-17T00:00:00Z",
                "integrity_status": "not_assessable",
                "integrity_findings": [{"finding_code": "missing_required_input", "dimension": "integrity", "severity": "info"}],
                "semantic_status": status,
                "semantic_findings": [],
                "semantic_result_provenance": None if status in {"not_evaluated", "not_assessable"} else {"provider": "anthropic"},
                "semantic_error": None if status != "error" else {"error_code": "semantic_visual_review_invalid_payload", "error_message": "boom"},
                "binding_records": [],
                "source_artifacts": {},
                "recommendation": "not_assessable",
            },
        )

    return _runner


def test_lifecycle_control_outcomes_remain_identical_across_injected_hpe_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _compiled_plan()
    paths = _base_payloads(tmp_path)
    _install_approval_monkeypatch(monkeypatch, paths)
    _write_json(paths["account"], _accounting_report(paths))
    _write_json(paths["decision"], _decision_report(plan))
    _write_json(paths["approval"], {"report_type": approval.APPROVAL_REPORT_TYPE, "schema_version": approval.APPROVAL_SCHEMA_VERSION, "approval_type": approval.APPROVAL_TYPE, "operator_id": approval.CANONICAL_OPERATOR_ID, "approved_at_utc": "2026-07-17T00:00:00Z", "expires_at_utc": "2026-07-17T00:30:00Z", "handoff_artifact_path": "x", "handoff_artifact_sha256": "a" * 64, "handoff_report_type": approval.HANDOFF_REPORT_TYPE, "handoff_schema_version": approval.HANDOFF_SCHEMA_VERSION, "date": "2026-07-17", "slot_id": "slot", "prompt_sha256": "a" * 64, "provider": approval.APPROVAL_PROVIDER, "executor": approval.APPROVAL_EXECUTOR, "model": approval.MODEL, "aspect_ratio": approval.ASPECT_RATIO, "soul_name": approval.SOUL_NAME, "soul_type": approval.SOUL_TYPE, "custom_reference_id": "ref", "confirmation_statement": approval.confirmation_phrase("slot"), "reconciliation": {}, "reconciled_candidate": {}, "reconciliation_decision": {}, "credits_may_be_spent_acknowledged": True, "authorized_attempts": 1, "upload_authorized": False, "queue_promotion_authorized": False, "publish_authorized": False, "analytics_mutation_authorized": False, "immutability": "immutable_once_written", "authorization_identity_mode": "procedural_local_authorization_record_only"})
    _write_json(paths["manifest"], {"provider": "higgsfield", "date": "2026-07-17", "slot_id": "slot", "provider_status": "completed", "saved_image_path": str(paths["image"].resolve()), "generation_claim_artifact_path": paths["claim"].resolve().as_posix(), "generation_execution_receipt_path": paths["receipt"].resolve().as_posix(), "provider_job_id": "job", "image_format_detected": "png"})
    _write_json(paths["claim"], {"report_type": approval.CLAIM_REPORT_TYPE, "schema_version": approval.CLAIM_SCHEMA_VERSION, "claim_type": approval.CLAIM_TYPE, "date": "2026-07-17", "slot_id": "slot", "approved_at_utc": "2026-07-17T00:00:00Z", "claim_written_at_utc": "2026-07-17T00:00:00Z"})
    _write_json(paths["receipt"], {"report_type": approval.RECEIPT_REPORT_TYPE, "schema_version": approval.RECEIPT_SCHEMA_VERSION, "receipt_type": approval.RECEIPT_TYPE, "date": "2026-07-17", "slot_id": "slot", "approved_at_utc": "2026-07-17T00:00:00Z", "receipt_written_at_utc": "2026-07-17T00:00:00Z", "provider_job_id": "job", "provider_status": "completed", "output_path": str(paths["image"].resolve()), "image_format_detected": "png", "actual_manifest_path": paths["manifest"].resolve().as_posix()})

    baseline: dict[str, object] | None = None
    for status in STATUSES:
        qa_output_root = tmp_path / "qa" / status
        lifecycle_output_root = tmp_path / "lifecycle" / status
        report = lifecycle.evaluate_generated_asset_qa_lifecycle(
            live_generation_accounting_artifact=paths["account"],
            decision_artifact=paths["decision"],
            identity_reference_authority_artifact=paths["approval"],
            identity_reference_authority_sha256=approval.sha256_file(paths["approval"]),
            identity_references=[(paths["approval"], approval.sha256_file(paths["approval"]))],
            qa_runner=_qa_runner,
            human_presence_output_qa_runner=_presence_runner(status),
            qa_output_root=qa_output_root,
            lifecycle_output_root=lifecycle_output_root,
            live_presence_semantic_review=False,
        )
        assert report["human_presence_output_qa_state"]["semantic_status"] == status
        assert report["human_presence_output_qa_state"]["authority"] == "evidence_only"
        assert report["qa_status"] == "accept"
        assert report["retry_recommended"] is False
        assert report["publish_authorized"] is False
        assert report["publish_performed"] is False
        assert report["queue_mutated"] is False
        assert report["next_allowed_action"] == "await_publish_authorization"
        assert report["human_presence_output_qa_state"]["semantic_status"] == status
        projection = {
            "qa_status": report["qa_status"],
            "retry_recommended": report["retry_recommended"],
            "publish_authorized": report["publish_authorized"],
            "publish_performed": report["publish_performed"],
            "queue_mutated": report["queue_mutated"],
            "next_allowed_action": report["next_allowed_action"],
            "retry_decision_artifact": report["retry_decision_artifact"],
            "retry_handoff_artifact": report["retry_handoff_artifact"],
        }
        if baseline is None:
            baseline = projection
        else:
            assert projection == baseline
