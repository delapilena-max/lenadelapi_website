from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

import pipeline.identity.lena_higgsfield_identity as identity
import tools.lena_bounded_live_cycle_v1 as cycle
import tools.lena_higgsfield_generation_approval_v1 as approval
import tools.lena_photo_qa_disposition_v1 as photo_qa
from tools.strategy import lena_execute_approved_live_generation_v1 as approved_live_generation


DATE = "2026-07-18"
SLOT_ID = "lenagate202607176924dc10-pack000-00-photo"
RECIPE_ID = "hcr_012"
HOOK_ID = "cbn_001"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
PROMPT_SHA = "186c0feb77d819cf1d001507dd56448e22057eeab5f2af33c83e0b464abdf640"
AUTHORITY_COMMIT = "6924dc10d7916b3bc91a87953ca3e319171e42fc"
CAPTION = "single-command bounded live cycle"
PLATFORM = "Instagram Feed"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _write_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), "white").save(path)
    return path


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        fixed = datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc)
        if tz is None:
            return fixed.replace(tzinfo=None)
        return fixed.astimezone(tz)


def _patch_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cycle, "ROOT", tmp_path)
    monkeypatch.setattr(cycle, "AUTH_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles")
    monkeypatch.setattr(cycle, "REPORT_ROOT", tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles")
    monkeypatch.setattr(identity, "HIGGSFIELD_DEBUG_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    monkeypatch.setattr(photo_qa, "OUTPUT_ROOT", tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa")


def _patch_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cycle, "datetime", _FixedDateTime)
    monkeypatch.setattr(cycle, "_now_utc", lambda: datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc))
    monkeypatch.setattr(identity, "_utc_now", lambda: datetime(2026, 7, 18, 1, 2, 3, tzinfo=timezone.utc))


def _candidate_path(tmp_path: Path, date_str: str = DATE) -> Path:
    return tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / date_str / "lena_pre_generation_candidate_selected.json"


def _approval_path(tmp_path: Path, date_str: str = DATE) -> Path:
    return tmp_path / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{SLOT_ID}_higgsfield_generation_approval.json"


def _handoff_path(tmp_path: Path, date_str: str = DATE) -> Path:
    return tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_next_live_image_handoff_{date_str}.json"


def _auth_path(tmp_path: Path, date_str: str = DATE, slot_id: str = SLOT_ID) -> Path:
    return tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / date_str / f"lena_bounded_live_cycle_authorization_{date_str}_{slot_id}.json"


def _build_live_bundle(
    tmp_path: Path,
    *,
    date_str: str = DATE,
    slot_id: str = SLOT_ID,
    platform: str = PLATFORM,
    publish_authorized: bool = True,
    hard_spend_cap_usd: float = 25.0,
    consumed: bool = False,
) -> dict[str, Path | dict]:
    candidate_path = _candidate_path(tmp_path, date_str)
    approval_path = _approval_path(tmp_path, date_str)
    handoff_path = _handoff_path(tmp_path, date_str)
    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.png"
    candidate = {
        "candidate_id": f"{slot_id}::{RECIPE_ID}::{HOOK_ID}",
        "slot_id": slot_id,
        "lane": "bounded-live",
        "recipe_id": RECIPE_ID,
        "hook_id": HOOK_ID,
        "prompt_sha256": PROMPT_SHA,
        "authority_commit": AUTHORITY_COMMIT,
        "final_action": "prepare_higgsfield_still_dry_run_for_review",
        "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date_str} --slot-id {slot_id}",
    }
    _write_json(candidate_path, candidate)
    _write_image(image_path)
    asset_sha256 = _sha(image_path)
    auth = {
        "report_type": "lena_bounded_live_cycle_authorization",
        "schema_version": "v1",
        "date": date_str,
        "slot_id": slot_id,
        "candidate_id": candidate["candidate_id"],
        "single_use": True,
        "one_slot": True,
        "one_candidate": True,
        "one_asset": True,
        "one_platform": True,
        "consumed": consumed,
        "consumed_at_utc": None,
        "expires_at_utc": "2099-07-18T00:00:00+00:00",
        "provider_call_cap": 1,
        "publish_action_cap": 1,
        "retry_cap": 0,
        "hard_spend_cap_usd": hard_spend_cap_usd,
        "kill_switch_enabled": True,
        "publish_authorized": publish_authorized,
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "asset_path": str(image_path),
        "asset_sha256": asset_sha256,
        "platform": platform,
        "caption": CAPTION,
        "generation_handoff_artifact_path": str(handoff_path),
        "generation_handoff_artifact_sha256": "4" * 64,
        "generation_approval_artifact_path": str(approval_path),
        "generation_approval_artifact_sha256": "5" * 64,
        "candidate_artifact_path": str(candidate_path),
        "candidate_artifact_sha256": _sha(candidate_path),
        "expected_output_directory": str(image_path.parent),
        "expected_output_stem": image_path.stem,
    }
    auth_path = _auth_path(tmp_path, date_str, slot_id)
    _write_json(auth_path, auth)

    handoff = {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "date": date_str,
        "selected_slot_id": slot_id,
        "selected_recipe_id": RECIPE_ID,
        "selected_candidate_path": str(candidate_path),
        "selected_candidate_sha256": _sha(candidate_path),
        "selected_candidate": candidate,
        "prompt_sha256": PROMPT_SHA,
        "custom_reference_id": CUSTOM_REFERENCE_ID,
        "live_execution_authorized": False,
        "generation_approval_required": True,
        "manual_operator_approval_required": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "publish_authorized": False,
        "manual_publish_review_required": True,
        "packet_state": "packet_valid_for_claude_review",
        "dry_run_executor_contract_state": "ready",
        "live_execution_state": "blocked",
        "structured_executor_inputs": {
            "date": date_str,
            "selected_slot_id": slot_id,
            "selected_recipe_id": RECIPE_ID,
            "selected_candidate_path": str(candidate_path),
            "selected_candidate_sha256": _sha(candidate_path),
            "prompt_sha256": PROMPT_SHA,
            "asset_path": str(image_path),
        },
    }
    _write_json(handoff_path, handoff)

    approval_artifact = {
        "report_type": "lena_higgsfield_generation_approval",
        "schema_version": "v1",
        "approval_type": "higgsfield_single_generation",
        "operator_id": "nicolas",
        "approved_at_utc": "2026-07-18T01:00:00+00:00",
        "expires_at_utc": "2026-07-18T01:30:00+00:00",
        "handoff_artifact_path": str(handoff_path),
        "handoff_artifact_sha256": _sha(handoff_path),
        "handoff_report_type": "lena_next_live_image_handoff",
        "handoff_schema_version": "v1",
        "date": date_str,
        "slot_id": slot_id,
        "prompt_sha256": PROMPT_SHA,
        "provider": "Higgsfield",
        "executor": "Higgsfield CLI repo adapter",
        "model": "text2image_soul_v2",
        "aspect_ratio": "9:16",
        "soul_name": "Lena",
        "soul_type": "Soul 2.0",
        "custom_reference_id": CUSTOM_REFERENCE_ID,
        "confirmation_statement": approval.confirmation_phrase(slot_id),
        "reconciliation": {"reconciliation_status": "reconciled"},
        "reconciled_candidate": candidate,
        "reconciliation_decision": {"decision": "selected_candidate_authoritative"},
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "analytics_mutation_authorized": False,
    }
    _write_json(approval_path, approval_artifact)

    return {
        "candidate_path": candidate_path,
        "candidate": candidate,
        "auth_path": auth_path,
        "auth": auth,
        "approval_path": approval_path,
        "approval": approval_artifact,
        "handoff_path": handoff_path,
        "handoff": handoff,
        "image_path": image_path,
    }


def _build_simulation_artifacts(tmp_path: Path, bundle: dict[str, Path | dict], *, qa_disposition: str = "accept", qa_overall: str = "pass") -> dict[str, Path | dict]:
    date_str = DATE
    slot_id = SLOT_ID
    image_path = bundle["image_path"]  # type: ignore[assignment]
    assert isinstance(image_path, Path)
    _write_image(image_path)
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"
    manifest = {
        "report_type": "lena_higgsfield_result_manifest",
        "schema_version": "v1",
        "date": date_str,
        "slot_id": slot_id,
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "saved_image_path": str(image_path),
        "generation_claim_artifact_path": str(tmp_path / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{slot_id}_higgsfield_generation_claim.json"),
        "generation_execution_receipt_path": str(tmp_path / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{slot_id}_higgsfield_generation_execution_receipt.json"),
    }
    _write_json(manifest_path, manifest)
    receipt_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{slot_id}_higgsfield_generation_execution_receipt.json"
    receipt = {
        "report_type": "lena_higgsfield_generation_execution_receipt",
        "schema_version": "v1",
        "slot_id": slot_id,
        "date": date_str,
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "output_path": str(image_path),
        "actual_manifest_path": str(manifest_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha(manifest_path),
        "generated_image_path": str(image_path),
        "generated_image_sha256": _sha(image_path),
        "subprocess_start_attempted": True,
        "provider_submission_may_have_occurred": True,
    }
    _write_json(receipt_path, receipt)
    claim_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / date_str / f"{slot_id}_higgsfield_generation_claim.json"
    claim = {
        "report_type": "lena_higgsfield_generation_claim",
        "schema_version": "v1",
        "slot_id": slot_id,
        "date": date_str,
        "claimed_at_utc": "2026-07-18T01:00:00+00:00",
        "consumed_attempt_number": 1,
        "state": "claimed_pending_receipt",
    }
    _write_json(claim_path, claim)
    qa_path = tmp_path / "pipeline" / "asset_review" / "lena" / "presence_output_qa" / date_str / slot_id / f"presence_qa_{slot_id}_00.json"
    qa_artifact = {
        "report_type": "lena_presence_output_qa",
        "schema_version": "v2",
        "slot_id": slot_id,
        "date": date_str,
        "disposition": qa_disposition,
        "overall": qa_overall,
        "provider_job_id": "job-123",
        "image_sha256": _sha(image_path),
        "generation_provenance": {"date": date_str},
        "production_scoring": {
            "styling_sexy_platform_safe": {"status": "pass", "notes": "adult non-explicit styling allowed"},
        },
    }
    _write_json(qa_path, qa_artifact)
    auth_path = Path(bundle["auth_path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth.update(
        {
            "provider_generation_receipt_path": str(receipt_path),
            "provider_generation_receipt_sha256": _sha(receipt_path),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha(manifest_path),
            "qa_artifact_path": str(qa_path),
            "qa_artifact_sha256": _sha(qa_path),
            "expected_output_directory": str(image_path.parent),
            "expected_output_stem": image_path.stem,
            "asset_sha256": _sha(image_path),
        }
    )
    _write_json(auth_path, auth)
    return {
        **bundle,
        "provider_generation_receipt_path": receipt_path,
        "provider_generation_receipt_sha256": _sha(receipt_path),
        "manifest_path": manifest_path,
        "manifest_sha256": _sha(manifest_path),
        "qa_artifact_path": qa_path,
        "qa_artifact_sha256": _sha(qa_path),
        "expected_output_directory": image_path.parent,
        "expected_output_stem": image_path.stem,
        "manifest": manifest,
        "receipt_path": receipt_path,
        "receipt": receipt,
        "claim_path": claim_path,
        "claim": claim,
        "qa_path": qa_path,
        "qa": qa_artifact,
    }


def _install_live_fakes(monkeypatch: pytest.MonkeyPatch, bundle: dict[str, Path | dict], tmp_path: Path, *, qa_disposition: str = "accept", qa_overall: str = "pass") -> dict[str, object]:
    state: dict[str, object] = {
        "provider_calls": 0,
        "publish_calls": 0,
        "provider_error": None,
        "publish_error": None,
        "qa_disposition": qa_disposition,
        "qa_overall": qa_overall,
        "qa_calls": 0,
        "provider_manifest_overrides": {},
        "publish_overrides": {},
        "reference_authority": tmp_path / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json",
    }
    _write_json(
        state["reference_authority"],  # type: ignore[arg-type]
        {
            "schema_version": "lena_identity_reference_authority_v1",
            "influencer_id": "lena",
            "authority_id": "lena_visual_reference_authority_v1",
            "authority_commit": AUTHORITY_COMMIT,
            "references": [
                {
                    "path": str(tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"),
                    "sha256": "a" * 64,
                }
            ],
        },
    )
    reference_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"
    _write_image(reference_path)

    approval_result = {
        "approval": bundle["approval"],
        "approval_path": bundle["approval_path"],
        "approval_repo_path": str(bundle["approval_path"]),
        "approval_sha256": _sha(bundle["approval_path"]),
        "handoff_facts": {
            "date": DATE,
            "slot_id": SLOT_ID,
            "prompt_sha256": PROMPT_SHA,
            "custom_reference_id": CUSTOM_REFERENCE_ID,
            "handoff_path": str(bundle["handoff_path"]),
            "handoff_sha256": _sha(bundle["handoff_path"]),
            "selected_candidate_path": str(bundle["candidate_path"]),
            "selected_candidate_sha256": _sha(bundle["candidate_path"]),
            "selected_candidate": bundle["candidate"],
        },
        "scope_summary": {
            "authorized_attempts": 1,
            "upload_authorized": False,
            "queue_promotion_authorized": False,
            "publish_authorized": False,
            "analytics_mutation_authorized": False,
        },
    }

    def fake_validate_generation_approval_artifact(path: Path, *args, **kwargs):
        assert path.resolve() == Path(bundle["approval_path"]).resolve()
        approval_payload = json.loads(path.read_text(encoding="utf-8"))
        expires_at = approval_payload.get("expires_at_utc")
        if expires_at:
            expires_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expires_dt.astimezone(timezone.utc) <= _FixedDateTime.now(timezone.utc):
                raise approval.HiggsfieldGenerationApprovalError("approval_expired", "approval expired")
        return approval_result

    def fake_execute_approved_live_generation(handoff_artifact: Path, approval_artifact: Path, *, live: bool = False, **kwargs):
        assert live is True
        assert handoff_artifact.resolve() == Path(bundle["handoff_path"]).resolve()
        assert approval_artifact.resolve() == Path(bundle["approval_path"]).resolve()
        state["provider_calls"] = int(state["provider_calls"]) + 1
        image_path = Path(bundle["image_path"])
        _write_image(image_path)
        manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "result_manifest.json"
        manifest = {
            "provider": "higgsfield",
            "job_type": "text2image_soul_v2",
            "date": DATE,
            "slot_id": SLOT_ID,
            "lane": "bounded-live",
            "prompt_sha256": PROMPT_SHA,
            "image_prompt": "live prompt",
            "provider_job_id": "job-123",
            "provider_status": "completed",
            "custom_reference_id": CUSTOM_REFERENCE_ID,
            "cli_soul_name": "Lena",
            "cli_soul_type": "Soul 2.0",
            "saved_image_path": str(image_path),
            "saved_image_sha256": _sha(image_path),
            "width": 64,
            "height": 64,
        }
        manifest.update(state["provider_manifest_overrides"])  # type: ignore[arg-type]
        _write_json(manifest_path, manifest)
        claim_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_claim.json"
        receipt_path = tmp_path / "pipeline" / "approvals" / "lena" / "generation" / DATE / f"{SLOT_ID}_higgsfield_generation_execution_receipt.json"
        claim = {
            "report_type": "lena_higgsfield_generation_claim",
            "schema_version": "v1",
            "slot_id": SLOT_ID,
            "date": DATE,
            "claimed_at_utc": "2026-07-18T01:00:00+00:00",
            "consumed_attempt_number": 1,
            "state": "claimed_pending_receipt",
        }
        receipt = {
            "report_type": "lena_higgsfield_generation_execution_receipt",
            "schema_version": "v1",
            "slot_id": SLOT_ID,
            "date": DATE,
            "provider_job_id": "job-123",
            "provider_status": "completed",
            "output_path": str(image_path),
            "actual_manifest_path": str(manifest_path),
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha(manifest_path),
            "generated_image_path": str(image_path),
            "generated_image_sha256": _sha(image_path),
            "subprocess_start_attempted": True,
            "provider_submission_may_have_occurred": True,
        }
        _write_json(claim_path, claim)
        _write_json(receipt_path, receipt)
        return {
            "ok": True,
            "date": DATE,
            "slot_id": SLOT_ID,
            "recipe_id": RECIPE_ID,
            "selected_slot_id": SLOT_ID,
            "selected_recipe_id": RECIPE_ID,
            "claim_path": claim_path,
            "receipt_path": receipt_path,
            "manifest_path": manifest_path,
            "claim_written": True,
            "receipt_written": True,
            "manifest_written": True,
            "provider_submission_may_have_occurred": True,
            "subprocess_start_attempted": True,
            "provider_call_performed": True,
            "generation_performed": True,
            "live_result": {
                "job_id": "job-123",
                "status": "completed",
                "saved_image_path": str(image_path),
                "image_format_detected": "png",
                "provider_submission_may_have_occurred": True,
                "subprocess_start_attempted": True,
            },
            "manifest_record": manifest,
            "receipt_info": {"receipt_path": receipt_path, "receipt_repo_path": str(receipt_path)},
        }

    def fake_load_reference_specs():
        return state["reference_authority"], _sha(Path(state["reference_authority"])), [(reference_path, _sha(reference_path))]  # type: ignore[arg-type]

    def fake_evaluate_photo_qa_disposition(**kwargs):
        state["qa_calls"] = int(state["qa_calls"]) + 1
        artifact = {
            "report_type": "lena_presence_output_qa",
            "schema_version": "v2",
            "slot_id": SLOT_ID,
            "date": DATE,
            "disposition": state["qa_disposition"],
            "overall": state["qa_overall"],
            "provider_job_id": "job-123",
            "image_sha256": _sha(bundle["image_path"]),
            "generation_provenance": {"date": DATE},
            "production_scoring": {
                "styling_sexy_platform_safe": {
                    "status": "pass" if state["qa_disposition"] == "accept" else "fail",
                    "notes": "adult non-explicit styling allowed" if state["qa_disposition"] == "accept" else "safety issue",
                }
            },
        }
        artifact.update(state["qa_artifact_overrides"]) if "qa_artifact_overrides" in state else None
        return artifact

    def fake_write_disposition_artifact(artifact: dict, output_root: Path | None = None):
        root = output_root or (tmp_path / "pipeline" / "asset_review" / "lena" / "presence_output_qa")
        path = root / DATE / SLOT_ID / f"presence_qa_{SLOT_ID}_00.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing == artifact:
                return path, existing, False
            raise photo_qa.CollisionError("corrupt_or_untrusted_evidence", f"conflicting QA disposition already exists; refusing overwrite: {path}")
        _write_json(path, artifact)
        return path, artifact, True

    def fake_run_publisher(*, platform: str, payload_path: Path) -> dict[str, object]:
        state["publish_calls"] = int(state["publish_calls"]) + 1
        assert platform == PLATFORM
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if state["publish_error"] is not None:
            raise state["publish_error"]  # type: ignore[misc]
        result = {
            "post_id": "post-123",
            "post_url": "https://example.invalid/post-123",
            "posted_at": "2026-07-18T01:02:03Z",
        }
        result.update(state["publish_overrides"])  # type: ignore[arg-type]
        result["payload_path"] = payload_path
        result["payload_sha256"] = _sha(payload_path)
        result["payload"] = payload
        result["cmd"] = ["publisher"]
        result["cmd_text"] = "publisher"
        result["returncode"] = 0
        result["stdout"] = json.dumps({"ok": True, **result}, default=str)
        result["stderr"] = ""
        result["parsed"] = {"ok": True, **result}
        return result

    monkeypatch.setattr(approval, "validate_generation_approval_artifact", fake_validate_generation_approval_artifact)
    monkeypatch.setattr(approved_live_generation, "execute_approved_live_generation", fake_execute_approved_live_generation)
    monkeypatch.setattr(cycle, "_load_reference_specs", fake_load_reference_specs)
    monkeypatch.setattr(photo_qa, "evaluate_photo_qa_disposition", fake_evaluate_photo_qa_disposition)
    monkeypatch.setattr(photo_qa, "write_disposition_artifact", fake_write_disposition_artifact)
    monkeypatch.setattr(cycle, "_run_publisher", fake_run_publisher)
    return state


def _run_cycle(bundle: dict[str, Path | dict], *, simulate: bool, report_root: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    return cycle.run_cycle(bundle["auth_path"], simulate=simulate, report_root=report_root)  # type: ignore[arg-type]


def _run_cycle_outcome(bundle: dict[str, Path | dict], *, simulate: bool, report_root: Path, monkeypatch: pytest.MonkeyPatch):
    try:
        return ("report", _run_cycle(bundle, simulate=simulate, report_root=report_root, monkeypatch=monkeypatch))
    except cycle.LenaBoundedLiveCycleError as exc:
        return ("error", exc)


def test_simulation_success_chain_and_reuse_without_consumption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path, publish_authorized=False, hard_spend_cap_usd=0.0)
    bundle = _build_simulation_artifacts(tmp_path, bundle)

    report_root_a = tmp_path / "reports_a"
    report_root_b = tmp_path / "reports_b"
    first = _run_cycle(bundle, simulate=True, report_root=report_root_a, monkeypatch=monkeypatch)
    second = _run_cycle(bundle, simulate=True, report_root=report_root_b, monkeypatch=monkeypatch)

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["simulation_mode"] is True
    assert first["provider_calls_performed"] == 0
    assert first["publish_calls_performed"] == 0
    assert first["authorization_consumption_implemented"] is False
    assert first["authorization_consumed"] is False
    assert second["authorization_consumed"] is False
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False
    assert first["report_path"].startswith(str(report_root_a))
    assert second["report_path"].startswith(str(report_root_b))
    assert [stage["stage"] for stage in first["stage_coverage"]] == list(cycle.AUTHORISED_STAGES)


def test_live_success_consumes_authorization_and_binds_all_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    auth_sha_before = _sha(Path(bundle["auth_path"]))
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    report = _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports", monkeypatch=monkeypatch)

    auth_after = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["live_execution"] is True
    assert report["simulation_mode"] is False
    assert report["authorization_consumption_implemented"] is True
    assert report["authorization_consumed"] is True
    assert auth_after["consumed"] is True
    assert auth_after["cycle_id"] == report["cycle_id"]
    assert auth_after["operator_authorization_sha256"] == auth_sha_before
    assert report["provider_calls_performed"] == 1
    assert report["publish_calls_performed"] == 1
    assert report["retries_performed"] == 0
    assert state["provider_calls"] == 1
    assert state["publish_calls"] == 1
    assert state["qa_calls"] == 1
    assert [stage["stage"] for stage in report["stage_coverage"]] == list(cycle.LIVE_STAGES)
    assert report["child_artifacts"]["candidate_artifact"]["sha256"] == _sha(Path(bundle["candidate_path"]))
    assert report["child_artifacts"]["generated_asset"]["sha256"] == _sha(Path(bundle["image_path"]))
    assert report["child_artifacts"]["provider_generation_manifest"]["path"].endswith("result_manifest.json")
    assert report["child_artifacts"]["publish_receipt_artifact"]["path"].endswith("lena_bounded_live_cycle_publish_receipt_2026-07-18.json")
    assert report["child_artifacts"]["analytics_handoff_artifact"]["path"].endswith("lena_bounded_live_cycle_analytics_handoff_2026-07-18.json")
    assert report["provider_receipt"]["provider_job_id"] == "job-123"
    assert report["publish_receipt"]["remote_post_id"] == "post-123"
    assert report["analytics_handoff"]["remote_post_id"] == "post-123"


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda auth: auth.__setitem__("report_type", "wrong"), "authorization_report_type_mismatch"),
        (lambda auth: auth.__setitem__("schema_version", "v0"), "authorization_schema_mismatch"),
        (lambda auth: auth.__setitem__("one_slot", False), "authorization_one_slot_invalid"),
        (lambda auth: auth.__setitem__("one_candidate", False), "authorization_one_candidate_invalid"),
        (lambda auth: auth.__setitem__("one_asset", False), "authorization_one_asset_invalid"),
        (lambda auth: auth.__setitem__("one_platform", False), "authorization_one_platform_invalid"),
        (lambda auth: auth.__setitem__("expires_at_utc", "2020-07-18T00:00:00+00:00"), "authorization_expired"),
        (lambda auth: auth.__setitem__("provider_call_cap", 2), "provider_call_cap_invalid"),
        (lambda auth: auth.__setitem__("publish_action_cap", 2), "publish_action_cap_invalid"),
        (lambda auth: auth.__setitem__("retry_cap", 1), "retry_cap_invalid"),
        (lambda auth: auth.__setitem__("hard_spend_cap_usd", 0.0), "hard_spend_cap_invalid"),
        (lambda auth: auth.__setitem__("kill_switch_enabled", False), "authorization_kill_switch_disabled"),
        (lambda auth: auth.__setitem__("publish_authorized", False), "publish_authorized_invalid"),
        (lambda auth: auth.__setitem__("consumed", True), "authorization_already_consumed"),
        (lambda auth: auth.__setitem__("slot_id", "wrong-slot"), "slot_id_mismatch"),
        (lambda auth: auth.__setitem__("candidate_id", "wrong"), "candidate_id_mismatch"),
        (lambda auth: auth.__setitem__("asset_path", "../escape.png"), "asset_path_escape"),
        (lambda auth: auth.__setitem__("platform", "Facebook Page"), "platform_mismatch"),
    ],
)
def test_live_authorization_rejections_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    auth = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    mutator(auth)
    _write_json(Path(bundle["auth_path"]), auth)
    auth_sha_before = _sha(Path(bundle["auth_path"]))
    before = Path(bundle["auth_path"]).read_bytes()
    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports", monkeypatch=monkeypatch)

    if kind == "error":
        if expected_code in {"slot_id_mismatch", "candidate_id_mismatch"}:
            assert value.code in {"slot_id_mismatch", "candidate_id_mismatch", "approval_expired", "candidate_sha_mismatch"}
        else:
            assert value.code == expected_code
        report = None
    else:
        report = value
        assert report["ok"] is False
        if expected_code not in {"slot_id_mismatch", "candidate_id_mismatch"}:
            assert report["failure"]["code"] == expected_code

    auth_after = json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))
    if expected_code in {
        "authorization_report_type_mismatch",
        "authorization_schema_mismatch",
        "authorization_one_slot_invalid",
        "authorization_one_candidate_invalid",
        "authorization_one_asset_invalid",
        "authorization_one_platform_invalid",
        "authorization_expired",
        "provider_call_cap_invalid",
        "publish_action_cap_invalid",
        "retry_cap_invalid",
        "hard_spend_cap_invalid",
        "authorization_kill_switch_disabled",
        "publish_authorized_invalid",
        "authorization_already_consumed",
        "asset_path_escape",
        "platform_mismatch",
    }:
        assert auth_after == json.loads(before.decode("utf-8"))
    else:
        assert auth_after["consumed"] is True
        assert auth_after["operator_authorization_sha256"] == auth_sha_before


def test_duplicate_report_rejected_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    report_root = tmp_path / "reports"
    fixed = report_root / DATE / "lena_bounded_live_cycle_2026-07-18_010203.json"
    fixed.parent.mkdir(parents=True, exist_ok=True)
    fixed.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "_report_path", lambda day, stamp, report_root=report_root: fixed)

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        _run_cycle(bundle, simulate=False, report_root=report_root, monkeypatch=monkeypatch)

    assert exc_info.value.code == "report_already_exists"
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is False


def test_live_concurrent_invocation_rejected_after_consumption_begins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)
    gate = threading.Event()
    release = threading.Event()
    original_provider = approved_live_generation.execute_approved_live_generation

    def waiting_provider(*args, **kwargs):
        gate.set()
        release.wait(timeout=5)
        return original_provider(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(approved_live_generation, "execute_approved_live_generation", waiting_provider)
    results: list[tuple[str, object]] = []

    def first_run():
        try:
            results.append(("first", _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports_a", monkeypatch=monkeypatch)))
        except Exception as exc:  # pragma: no cover - diagnostic
            results.append(("first-error", exc))

    thread = threading.Thread(target=first_run)
    thread.start()
    assert gate.wait(timeout=5), "first invocation never reached provider stage"

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        _run_cycle(bundle, simulate=False, report_root=tmp_path / "reports_b", monkeypatch=monkeypatch)

    release.set()
    thread.join(timeout=5)
    assert exc_info.value.code in {"authorization_consumption_in_progress", "authorization_already_consumed"}
    assert int(state["provider_calls"]) >= 1
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True


@pytest.mark.parametrize(
    "stage, error_code",
    [
        ("provider", "provider_generation_failed"),
        ("qa", "qa_rejected"),
        ("publish", "publish_failed"),
    ],
)
def test_live_failure_keeps_authorization_consumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, error_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    state = _install_live_fakes(monkeypatch, bundle, tmp_path)

    if stage == "provider":
        def fail_provider(*args, **kwargs):
            raise cycle.LenaBoundedLiveCycleError(error_code, "provider stage failed")
        monkeypatch.setattr(approved_live_generation, "execute_approved_live_generation", fail_provider)
    elif stage == "qa":
        state["qa_disposition"] = "hard_stop"
        state["qa_overall"] = "fail"
    else:
        state["publish_error"] = cycle.LenaBoundedLiveCycleError("publish_failed", "publisher failed")

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports", monkeypatch=monkeypatch)
    if kind == "error":
        assert value.code == error_code
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == error_code
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True
    assert int(state["provider_calls"]) == (0 if stage == "provider" else 1)
    assert int(state["publish_calls"]) == (1 if stage == "publish" else 0)
    assert int(state["qa_calls"]) == (1 if stage in {"qa", "publish"} else 0)


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda bundle: _write_json(Path(bundle["approval_path"]), {**json.loads(Path(bundle["approval_path"]).read_text(encoding="utf-8")), "expires_at_utc": "2026-07-18T00:30:00+00:00"}), "approval_expired"),
        (lambda bundle: _write_json(Path(bundle["candidate_path"]), {**json.loads(Path(bundle["candidate_path"]).read_text(encoding="utf-8")), "slot_id": "wrong"}), "candidate_sha_mismatch"),
        (lambda bundle: _write_json(Path(bundle["candidate_path"]), {**json.loads(Path(bundle["candidate_path"]).read_text(encoding="utf-8")), "candidate_id": "wrong"}), "candidate_sha_mismatch"),
    ],
)
def test_live_binding_mismatches_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    _install_live_fakes(monkeypatch, bundle, tmp_path)
    mutator(bundle)

    kind, value = _run_cycle_outcome(bundle, simulate=False, report_root=tmp_path / "reports", monkeypatch=monkeypatch)
    if kind == "error":
        assert value.code == expected_code
    else:
        assert value["ok"] is False
        assert value["failure"]["code"] == expected_code
    assert json.loads(Path(bundle["auth_path"]).read_text(encoding="utf-8"))["consumed"] is True


def test_live_report_path_symlink_escape_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    _patch_clock(monkeypatch)
    bundle = _build_live_bundle(tmp_path)
    _install_live_fakes(monkeypatch, bundle, tmp_path)
    report_root = tmp_path / "reports"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks not supported")
    link = report_root / DATE
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation not permitted: {exc}")

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        _run_cycle(bundle, simulate=False, report_root=report_root, monkeypatch=monkeypatch)

    assert exc_info.value.code == "report_path_escape"
