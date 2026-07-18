from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

import tools.lena_bounded_live_cycle_v1 as cycle


DATE = "2026-07-18"
SLOT_ID = "higgsfield-20260718-hcr_099-photo"
CANDIDATE_ID = f"{SLOT_ID}::hcr_099::cbn_001"
CAPTION = "single-command bounded live cycle"


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


def _patch_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cycle, "ROOT", tmp_path)
    monkeypatch.setattr(cycle, "AUTH_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles")
    monkeypatch.setattr(cycle, "REPORT_ROOT", tmp_path / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles")


def _build_bundle(
    tmp_path: Path,
    *,
    date_str: str = DATE,
    slot_id: str = SLOT_ID,
    candidate_id: str = CANDIDATE_ID,
    platform: str = "Instagram Feed",
    caption: str = CAPTION,
    expires_at_utc: str = "2099-07-18T00:00:00+00:00",
    consumed: bool = False,
    provider_call_limit: int = 1,
    publish_action_limit: int = 1,
    retry_cap: int = 0,
    hard_spend_cap_usd: float = 0.0,
    kill_switch: bool = True,
    publish_authorized: bool = False,
    provider_calls_performed: int = 0,
    publish_calls_performed: int = 0,
    retries_performed: int = 0,
    qa_disposition: str = "accept",
    qa_status: str = "approved",
):
    candidate_path = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / date_str / "lena_pre_generation_candidate_selected.json"
    candidate = {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": date_str,
        "authority_commit": "b" * 40,
        "candidate_status": "selected",
        "final_action": "prepare_higgsfield_still_dry_run_for_review",
        "candidate": {
            "candidate_id": candidate_id,
            "slot_id": slot_id,
            "lane": "bounded-live",
            "recipe_id": "hcr_099",
            "hook_id": "cbn_001",
            "prompt_sha256": "c" * 64,
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date_str} --slot-id {slot_id}",
        },
        "decision_fingerprint_sha256": "d" * 64,
        "generated_at_utc": "2026-07-18T00:01:00Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    _write_json(candidate_path, candidate)

    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.png"
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
        "generation_claim_artifact_path": "pipeline/approvals/lena/generation/placeholder.json",
        "generation_execution_receipt_path": "pipeline/approvals/lena/generation/placeholder.json",
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

    qa_path = tmp_path / "pipeline" / "asset_review" / "lena" / "presence_output_qa" / date_str / slot_id / f"presence_qa_{slot_id}_00.json"
    qa_artifact = {
        "report_type": "lena_presence_output_qa",
        "schema_version": "v2",
        "slot_id": slot_id,
        "date": date_str,
        "disposition": qa_disposition,
        "overall": qa_status,
        "provider_job_id": "job-123",
        "image_sha256": _sha(image_path),
        "qa_inputs": {"binding_error": None},
    }
    _write_json(qa_path, qa_artifact)

    auth_path = tmp_path / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / date_str / f"lena_bounded_live_cycle_authorization_{date_str}_{slot_id}.json"
    auth = {
        "report_type": "lena_bounded_live_cycle_authorization",
        "schema_version": "v1",
        "date": date_str,
        "slot_id": slot_id,
        "candidate_id": candidate_id,
        "asset_path": str(image_path),
        "asset_sha256": _sha(image_path),
        "platform": platform,
        "caption": caption,
        "single_use": True,
        "one_slot": True,
        "one_candidate": True,
        "one_asset": True,
        "one_platform": True,
        "consumed": consumed,
        "consumed_at_utc": None,
        "expires_at_utc": expires_at_utc,
        "provider_call_limit": provider_call_limit,
        "publish_action_limit": publish_action_limit,
        "retry_cap": retry_cap,
        "hard_spend_cap_usd": hard_spend_cap_usd,
        "kill_switch": kill_switch,
        "publish_authorized": publish_authorized,
        "provider_calls_performed": provider_calls_performed,
        "publish_calls_performed": publish_calls_performed,
        "retries_performed": retries_performed,
        "candidate_artifact_path": str(candidate_path),
        "candidate_artifact_sha256": _sha(candidate_path),
        "provider_generation_receipt_path": str(receipt_path),
        "provider_generation_receipt_sha256": _sha(receipt_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha(manifest_path),
        "qa_artifact_path": str(qa_path),
        "qa_artifact_sha256": _sha(qa_path),
    }
    _write_json(auth_path, auth)

    return {
        "auth_path": auth_path,
        "auth": auth,
        "candidate_path": candidate_path,
        "candidate": candidate,
        "receipt_path": receipt_path,
        "receipt": receipt,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "image_path": image_path,
        "qa_path": qa_path,
        "qa": qa_artifact,
    }


def _patch_bundle_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_roots(monkeypatch, tmp_path)


def test_simulation_success_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_bundle_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path)

    report = cycle.run_cycle(bundle["auth_path"], simulate=True, report_root=cycle.REPORT_ROOT)

    assert report["ok"] is True
    assert report["simulation_mode"] is True
    assert [stage["stage"] for stage in report["stage_coverage"]] == list(cycle.AUTHORISED_STAGES)
    assert report["provider_calls_performed"] == 0
    assert report["publish_calls_performed"] == 0
    assert report["retries_performed"] == 0
    assert report["authorization_consumed"] is True
    assert report["child_artifacts"]["candidate"]["sha256"] == _sha(bundle["candidate_path"])
    assert report["child_artifacts"]["provider_generation_receipt"]["sha256"] == _sha(bundle["receipt_path"])
    assert report["child_artifacts"]["manifest"]["sha256"] == _sha(bundle["manifest_path"])
    assert report["child_artifacts"]["generated_asset"]["sha256"] == _sha(bundle["image_path"])
    assert report["child_artifacts"]["qa_artifact"]["sha256"] == _sha(bundle["qa_path"])
    assert report["child_artifacts"]["package_artifact"]["path"].endswith(".json")
    assert report["child_artifacts"]["publish_receipt_artifact"]["path"].endswith(".json")
    assert report["child_artifacts"]["analytics_handoff_artifact"]["path"].endswith(".json")
    assert "simulation_command" in report
    assert "proposed_live_command" in report


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (lambda auth: auth.__setitem__("expires_at_utc", "2020-07-18T00:00:00+00:00"), "authorization_expired"),
        (lambda auth: auth.__setitem__("slot_id", "wrong-slot"), "slot_id_mismatch"),
        (lambda auth: auth.__setitem__("candidate_id", "wrong"), "candidate_id_mismatch"),
        (lambda auth: auth.__setitem__("asset_path", str(Path(auth["asset_path"]).with_name("wrong.png"))), "manifest_image_mismatch"),
        (lambda auth: auth.__setitem__("platform", "Facebook Page"), "platform_mismatch"),
        (lambda auth: auth.__setitem__("consumed", True), "authorization_already_consumed"),
        (lambda auth: auth.__setitem__("provider_call_limit", 2), "provider_call_limit_invalid"),
        (lambda auth: auth.__setitem__("publish_action_limit", 2), "publish_action_limit_invalid"),
        (lambda auth: auth.__setitem__("retry_cap", 1), "retry_cap_invalid"),
        (lambda auth: auth.__setitem__("hard_spend_cap_usd", 5.0), "hard_spend_cap_invalid"),
        (lambda auth: auth.__setitem__("kill_switch", False), "authorization_kill_switch_disabled"),
        (lambda auth: auth.__setitem__("publish_authorized", True), "publish_authorized_invalid"),
        (lambda auth: auth.__setitem__("provider_calls_performed", 1), "authorization_provider_calls_not_zero"),
        (lambda auth: auth.__setitem__("publish_calls_performed", 1), "authorization_publish_calls_not_zero"),
        (lambda auth: auth.__setitem__("retries_performed", 1), "authorization_retries_not_zero"),
    ],
)
def test_authorization_rejections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator, expected_code: str) -> None:
    _patch_bundle_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path)
    auth = json.loads(bundle["auth_path"].read_text(encoding="utf-8"))
    mutator(auth)
    if auth.get("asset_path") and auth["asset_path"] != bundle["auth"]["asset_path"]:
        other_image = tmp_path / "pipeline" / "higgsfield_library" / "lena" / "other_asset.png"
        _write_image(other_image)
        auth["asset_path"] = str(other_image)
        auth["asset_sha256"] = _sha(other_image)
    bundle["auth_path"].write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        cycle.run_cycle(bundle["auth_path"], simulate=True, report_root=cycle.REPORT_ROOT)

    assert exc_info.value.code == expected_code


def test_duplicate_report_rejected_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_bundle_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path)
    fixed_report = cycle.REPORT_ROOT / DATE / f"lena_bounded_live_cycle_{DATE}_123456.json"
    fixed_report.parent.mkdir(parents=True, exist_ok=True)
    fixed_report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "_report_path", lambda day, stamp, report_root=cycle.REPORT_ROOT: fixed_report)

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        cycle.run_cycle(bundle["auth_path"], simulate=True, report_root=cycle.REPORT_ROOT)

    assert exc_info.value.code == "report_already_exists"


def test_provider_failure_stops_later_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_bundle_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path)
    auth = json.loads(bundle["auth_path"].read_text(encoding="utf-8"))
    auth["provider_generation_receipt_sha256"] = "0" * 64
    bundle["auth_path"].write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    later_calls: list[str] = []

    def _later(*args, **kwargs):
        later_calls.append("called")
        raise AssertionError("later stage should not run")

    monkeypatch.setattr(cycle, "_build_package", _later)
    monkeypatch.setattr(cycle, "_build_publish_receipt", _later)
    monkeypatch.setattr(cycle, "_build_analytics_handoff", _later)

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        cycle.run_cycle(bundle["auth_path"], simulate=True, report_root=cycle.REPORT_ROOT)

    assert exc_info.value.code == "provider_receipt_binding_invalid_sha_mismatch"
    assert later_calls == []


def test_qa_failure_stops_later_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_bundle_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path, qa_disposition="hard_stop", qa_status="rejected")
    later_calls: list[str] = []

    def _later(*args, **kwargs):
        later_calls.append("called")
        raise AssertionError("later stage should not run")

    monkeypatch.setattr(cycle, "_build_package", _later)
    monkeypatch.setattr(cycle, "_build_publish_receipt", _later)
    monkeypatch.setattr(cycle, "_build_analytics_handoff", _later)

    with pytest.raises(cycle.LenaBoundedLiveCycleError) as exc_info:
        cycle.run_cycle(bundle["auth_path"], simulate=True, report_root=cycle.REPORT_ROOT)

    assert exc_info.value.code == "qa_failure"
    assert later_calls == []


def test_final_receipt_binds_every_artifact_and_action(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_bundle_roots(monkeypatch, tmp_path)
    bundle = _build_bundle(tmp_path)

    report = cycle.run_cycle(bundle["auth_path"], simulate=True, report_root=cycle.REPORT_ROOT)

    assert report["authorization_artifact_path"] == str(bundle["auth_path"])
    assert report["authorized_scope"]["slot_id"] == SLOT_ID
    assert report["authorized_scope"]["candidate_id"] == CANDIDATE_ID
    assert report["authorized_scope"]["platform"] == "Instagram Feed"
    assert report["captions"]["caption"] == CAPTION
    assert set(report["child_artifacts"]) == {
        "candidate",
        "provider_generation_receipt",
        "manifest",
        "generated_asset",
        "qa_artifact",
        "package_artifact",
        "publish_receipt_artifact",
        "analytics_handoff_artifact",
    }
    assert report["child_artifacts"]["provider_generation_receipt"]["path"] == str(bundle["receipt_path"])
    assert report["child_artifacts"]["manifest"]["path"] == str(bundle["manifest_path"])
    assert report["child_artifacts"]["generated_asset"]["path"] == str(bundle["image_path"])
    assert report["child_artifacts"]["qa_artifact"]["path"] == str(bundle["qa_path"])
    assert report["provider_calls_performed"] == 0
    assert report["publish_calls_performed"] == 0
    assert report["retries_performed"] == 0
    assert report["safeguards"]["kill_switch"] is True
