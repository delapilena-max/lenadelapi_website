from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from pipeline import higgsfield_lena_api_executor as executor
from tools import lena_full_photo_autonomy_v1 as autonomy
from tools import lena_bounded_live_cycle_v1 as live_cycle
from tools import lena_higgsfield_generation_approval_v1 as generation_approval
from tools import lena_higgsfield_retry_generation_approval_v1 as retry_approval
from tools import lena_prepare_privacy_clean_photo_v1 as clean_photo
from tools import lena_photo_qa_disposition_v1 as photo_qa
from tools.diagnostics import lena_higgsfield_prompt_library_dryrun as prompt_library


def _write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _controlled_policy() -> dict:
    return {
        "emergency_stop": False,
        "controlled_photo_autonomy": {
            "enabled": True,
            "recipe_id": "hcr_012",
            "wardrobe_outfit_id": "wc_p050",
            "schedule_slot": "morning",
        },
    }


def _controlled_handoff(path: Path) -> Path:
    return _write_json(
        path,
        {
            "selected_candidate": {
                "recipe_id": "hcr_012",
                "wardrobe_outfit_id": "wc_p050",
            },
            "live_execution_authorized": False,
            "source_reconciliation_status": "reconciled",
            "source_reconciliation_operator_review_required": False,
        },
    )


def test_prompt_safety_allows_prohibitions_but_rejects_positive_explicit_terms() -> None:
    validation = {
        "framing_present": True,
        "wardrobe_casual_free": True,
        "wardrobe_casual_terms_found": [],
        "scene_action_conflict_free": True,
        "scene_action_conflict_terms_found": [],
        "soul_anchor_absent": True,
        "negative_prompt_disabled": True,
        "heavy_overcorrection_free": True,
        "heavy_overcorrection_terms_found": [],
        "pose_scene_match_pass": True,
        "pose_scene_mismatch_terms_found": [],
        "low_hook_terms_found": [],
    }
    prohibited = {"image_prompt": "[Technical]: No bikini, lingerie drift, or bra-like styling.", "validation": validation}
    positive = {"image_prompt": "[Subject]: lingerie styling.", "validation": validation}

    assert prompt_library._hard_exclude_reasons(prohibited) == []
    assert any("lingerie" in reason for reason in prompt_library._hard_exclude_reasons(positive))


def test_scheduler_starts_complete_controlled_cycle_without_per_photo_human_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = _controlled_handoff(tmp_path / "handoff.json")
    auth_path = _write_json(tmp_path / "authorization.json", {"consumed": False})
    calls: list[str] = []
    monkeypatch.setattr(autonomy, "LOCK_ROOT", tmp_path / "locks")
    monkeypatch.setattr(
        autonomy.standing_autonomy,
        "validate_policy_artifact",
        lambda path: {"path": Path(path), "sha256": "a" * 64, "artifact": _controlled_policy()},
    )

    def issue(policy_path, handoff_path):
        calls.append("approval")
        assert Path(handoff_path) == handoff
        return {"path": auth_path}

    def execute(path, *, report_root):
        calls.append("cycle")
        assert Path(path) == auth_path
        return {
            "ok": True,
            "autonomous_disposition": "accept_and_publish",
            "human_review_required": False,
            "publish_performed": True,
        }

    monkeypatch.setattr(autonomy.standing_autonomy, "issue_cycle_authorization", issue)
    monkeypatch.setattr(autonomy.standing_autonomy, "default_daily_report_root", lambda: tmp_path / "reports")
    result = autonomy.run_controlled_cycle(
        day="2026-07-21",
        schedule_slot="morning",
        policy_path=tmp_path / "policy.json",
        prep_runner=lambda day: {"handoff_path": handoff},
        cycle_runner=execute,
    )

    assert calls == ["approval", "cycle"]
    assert result["autonomous_disposition"] == "accept_and_publish"
    assert result["scheduler"]["human_per_photo_authorization_required"] is False
    assert not (tmp_path / "locks" / "2026-07-21.lock").exists()


def test_scheduler_blocks_noncanonical_lane_before_authority_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = _controlled_handoff(tmp_path / "handoff.json")
    value = json.loads(handoff.read_text(encoding="utf-8"))
    value["selected_candidate"]["wardrobe_outfit_id"] = "wc_other"
    _write_json(handoff, value)
    monkeypatch.setattr(autonomy, "LOCK_ROOT", tmp_path / "locks")
    monkeypatch.setattr(
        autonomy.standing_autonomy,
        "validate_policy_artifact",
        lambda path: {"path": Path(path), "sha256": "a" * 64, "artifact": _controlled_policy()},
    )
    issued = {"count": 0}
    monkeypatch.setattr(
        autonomy.standing_autonomy,
        "issue_cycle_authorization",
        lambda *args, **kwargs: issued.__setitem__("count", issued["count"] + 1),
    )
    with pytest.raises(autonomy.FullPhotoAutonomyError) as exc:
        autonomy.run_controlled_cycle(
            day="2026-07-21",
            schedule_slot="morning",
            policy_path=tmp_path / "policy.json",
            prep_runner=lambda day: {"handoff_path": handoff},
        )
    assert exc.value.code == "controlled_wardrobe_mismatch"
    assert issued["count"] == 0


def test_scheduler_converts_cycle_exception_to_terminal_operational_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = _controlled_handoff(tmp_path / "handoff.json")
    auth_path = _write_json(tmp_path / "authorization.json", {"consumed": False})
    monkeypatch.setattr(autonomy, "LOCK_ROOT", tmp_path / "locks")
    monkeypatch.setattr(autonomy.standing_autonomy, "validate_policy_artifact", lambda path: {"artifact": _controlled_policy()})
    monkeypatch.setattr(autonomy.standing_autonomy, "issue_cycle_authorization", lambda *args, **kwargs: {"path": auth_path})
    monkeypatch.setattr(autonomy.standing_autonomy, "default_daily_report_root", lambda: tmp_path / "reports")
    result = autonomy.run_controlled_cycle(
        day="2026-07-21",
        schedule_slot="morning",
        policy_path=tmp_path / "policy.json",
        prep_runner=lambda day: {"handoff_path": handoff},
        cycle_runner=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("publisher unavailable")),
    )
    assert result["autonomous_disposition"] == "operational_failure"
    assert result["human_review_required"] is False
    assert result["exceptional_escalation_required"] is True


def test_privacy_clean_derivative_is_separate_metadata_free_and_lineage_bound(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("prompt", "private provider prompt")
    Image.new("RGB", (64, 96), "red").save(source, pnginfo=metadata)
    output = tmp_path / "clean.png"
    report_path = tmp_path / "clean.json"
    lineage = {
        "candidate_artifact_sha256": "1" * 64,
        "prompt_sha256": "2" * 64,
        "packet_sha256": "3" * 64,
        "handoff_sha256": "4" * 64,
        "approval_sha256": "5" * 64,
        "execution_receipt_sha256": "6" * 64,
        "manifest_sha256": "7" * 64,
        "qa_sha256": "8" * 64,
    }

    report = clean_photo.prepare_privacy_clean_photo(
        source,
        output,
        report_path,
        source_image_sha256=clean_photo._sha256_file(source),
        lineage=lineage,
    )

    assert source.read_bytes() != output.read_bytes()
    assert b"private provider prompt" not in output.read_bytes()
    assert report["source_path"] == str(source.resolve())
    assert report["output_path"] == str(output.resolve())
    assert clean_photo.validate_privacy_clean_report(report_path)["lineage"] == lineage


def test_privacy_clean_validation_rejects_altered_derivative(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "blue").save(source)
    output = tmp_path / "clean.png"
    report_path = tmp_path / "clean.json"
    lineage_keys = (
        "candidate_artifact_sha256",
        "prompt_sha256",
        "packet_sha256",
        "handoff_sha256",
        "approval_sha256",
        "execution_receipt_sha256",
        "manifest_sha256",
        "qa_sha256",
    )
    lineage = {key: str(index) * 64 for index, key in enumerate(lineage_keys, start=1)}
    clean_photo.prepare_privacy_clean_photo(
        source,
        output,
        report_path,
        source_image_sha256=clean_photo._sha256_file(source),
        lineage=lineage,
    )
    output.write_bytes(output.read_bytes() + b"tamper")
    with pytest.raises(clean_photo.PrivacyCleanPhotoError) as exc:
        clean_photo.validate_privacy_clean_report(report_path)
    assert exc.value.code == "clean_export_sha_mismatch"


def test_callable_retry_executor_validates_before_claim_and_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "retry.png"
    Image.new("RGB", (16, 16), "green").save(image)
    claim = _write_json(tmp_path / "claim.json", {"claim": 1})
    receipt = _write_json(tmp_path / "receipt.json", {"receipt": 1})
    manifest = tmp_path / "manifest.json"
    order: list[str] = []
    monkeypatch.setattr(executor, "_load_retry_decision_source", lambda path: ("2026-07-21", "slot-retry01", {"image": {"image_prompt": "prompt"}}, Path(path)))
    monkeypatch.setattr(executor, "validate_candidate", lambda source, expected: {"ok": True})
    monkeypatch.setattr(
        executor,
        "_validate_retry_approval_artifact",
        lambda handoff, approval: order.append("approval") or {"retry_facts": {"custom_reference_id": "soul-current", "date": "2026-07-21", "slot_id": "slot-retry01"}},
    )
    monkeypatch.setattr(executor, "_create_retry_generation_claim", lambda result: order.append("claim") or {"claim_path": claim, "claim_repo_path": "claim.json"})
    monkeypatch.setattr(executor, "manifest_path", lambda day, slot: manifest)
    monkeypatch.setattr(executor, "build_manifest", lambda *args, **kwargs: {"saved_image_path": str(image), "saved_image_sha256": executor._sha256_file(image)})
    monkeypatch.setattr(executor, "_write_manifest_atomic", lambda path, value: _write_json(path, value))
    monkeypatch.setattr(
        executor,
        "_write_retry_generation_execution_receipt",
        lambda *args, **kwargs: {"receipt_path": receipt, "receipt_repo_path": "receipt.json"},
    )

    def provider(day, slot, source, soul_id):
        order.append("provider")
        assert soul_id == "soul-current"
        return {
            "saved_image_path": str(image),
            "provider_submission_may_have_occurred": True,
            "subprocess_start_attempted": True,
            "job_id": "job-retry",
            "status": "completed",
            "image_format_detected": "png",
        }

    result = executor.execute_approved_retry_live_generation(
        tmp_path / "handoff.json",
        tmp_path / "approval.json",
        live_executor=provider,
    )
    assert result["ok"] is True
    assert order == ["approval", "claim", "provider"]
    assert result["manifest_written"] is True
    assert result["receipt_written"] is True


def test_callable_retry_executor_rejects_invalid_prompt_before_approval_or_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(executor, "_load_retry_decision_source", lambda path: ("2026-07-21", "slot-retry01", {"image": {}}, Path(path)))
    monkeypatch.setattr(executor, "validate_candidate", lambda source, expected: {"ok": False})
    touched = {"approval": 0, "provider": 0}
    monkeypatch.setattr(executor, "_validate_retry_approval_artifact", lambda *args: touched.__setitem__("approval", 1))

    with pytest.raises(executor.HandoffArtifactError) as exc:
        executor.execute_approved_retry_live_generation(
            tmp_path / "handoff.json",
            tmp_path / "approval.json",
            live_executor=lambda *args: touched.__setitem__("provider", 1),
        )
    assert exc.value.code == "retry_prompt_validation_failed"
    assert touched == {"approval": 0, "provider": 0}


def test_retry_approval_is_issued_from_consumed_standing_authority_and_remains_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generation_approval, "ROOT", tmp_path)
    source_handoff = _write_json(tmp_path / "pipeline" / "handoff.json", {"handoff": 1})
    retry_handoff_path = _write_json(tmp_path / "pipeline" / "retry.json", {"retry": 1})
    auth_path = _write_json(tmp_path / "pipeline" / "authorization.json", {"authorization": 1})
    auth = {
        "consumed": True,
        "slot_id": "slot-original",
        "cycle_id": "cycle-1",
        "policy_artifact_sha256": "a" * 64,
        "provider_call_cap_per_cycle": 2,
        "retry_cap_per_cycle": 1,
        "generation_handoff_artifact_path": str(source_handoff),
        "controlled_photo_autonomy": {
            "enabled": True,
            "retry_reason_codes": ["hair_crown_forelock_artifact"],
        },
    }
    auth_result = {"path": auth_path, "artifact": auth}
    retry_facts = {
        "artifact": {"report_type": "lena_higgsfield_retry_handoff", "schema_version": "lena_higgsfield_retry_handoff_v1", "reason_code": "hair_crown_forelock_artifact"},
        "retry_handoff_path": retry_handoff_path,
        "retry_handoff_repo_path": generation_approval.repo_relative_path(retry_handoff_path),
        "retry_handoff_sha256": generation_approval.sha256_file(retry_handoff_path),
        "retry_handoff_fingerprint_sha256": "b" * 64,
        "expression_provenance_fingerprint_sha256": "c" * 64,
        "date": "2026-07-21",
        "slot_id": "slot-original-retry01",
        "prompt_sha256": "d" * 64,
        "prompt_text": "prompt",
        "original_slot_id": "slot-original",
        "source_handoff_artifact_path": generation_approval.repo_relative_path(source_handoff),
        "source_handoff_artifact_sha256": generation_approval.sha256_file(source_handoff),
        "source_execution_receipt_path": "pipeline/source-receipt.json",
        "source_execution_receipt_sha256": "e" * 64,
        "provider": "higgsfield",
        "executor": "higgsfield_cli",
        "model": "text2image_soul_v2",
        "aspect_ratio": "9:16",
        "custom_reference_id": "soul-current",
        "soul_name": "Lena",
        "soul_type": "soul_2",
    }
    record = retry_approval.build_standing_autonomy_retry_generation_approval_record(retry_facts, auth_result)
    approval_path = tmp_path / "pipeline" / "retry-approval.json"
    retry_approval.write_retry_generation_approval_record_atomic(approval_path, record)
    monkeypatch.setattr(retry_approval, "inspect_retry_handoff_artifact", lambda path: retry_facts)
    monkeypatch.setattr(autonomy.standing_autonomy, "validate_cycle_authorization_artifact", lambda path, **kwargs: auth_result)

    result = retry_approval.validate_retry_generation_approval_artifact(approval_path)
    assert result["approval"]["authorization_identity_mode"] == "standing_autonomy_policy"
    assert result["approval"]["operator_id"] == autonomy.standing_autonomy.AUTHORIZATION_ISSUER
    assert result["standing_authorization_result"] == auth_result


def test_typed_retry_qa_ingestion_rebinds_retry_slot_prompt_and_original_candidate_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision_path = _write_json(tmp_path / "typed-retry.json", {"report_type": photo_qa.typed_retry_handoff.REPORT_TYPE})
    candidate_path = tmp_path / "candidate.json"
    typed = {
        "date": "2026-07-21",
        "retry_slot_id": "slot-retry01",
        "retry_prompt_sha256": "1" * 64,
        "retry_handoff_fingerprint_sha256": "2" * 64,
        "source_selected_prompt_input_artifact_path": "pipeline/packet.json",
        "source_selected_prompt_input_artifact_sha256": "3" * 64,
        "source_pose_bound_content_packet_sha256": "4" * 64,
        "pose_provenance_fingerprint_sha256": "5" * 64,
        "source_expression_bound_content_packet_sha256": "4" * 64,
        "expression_provenance_fingerprint_sha256": "6" * 64,
        "pose_provenance": {"selected_candidate_artifact_path": "pipeline/candidate.json"},
    }
    source_candidate = {
        "candidate_id": "source-candidate",
        "slot_id": "slot-original",
        "recipe_id": "hcr_012",
        "hook_id": "hook",
        "lane": "controlled",
    }
    monkeypatch.setattr(photo_qa.typed_retry_handoff, "validate_retry_handoff_artifact", lambda path: typed)
    monkeypatch.setattr(photo_qa.pose_provenance, "validate_pose_provenance", lambda value: value)
    monkeypatch.setattr(photo_qa, "_resolve_pose_repo_path", lambda value, label: candidate_path)
    monkeypatch.setattr(photo_qa, "_validate_selected_decision", lambda path: ({"authority_commit": "a" * 40}, source_candidate))

    decision, candidate, kind, binding = photo_qa._resolve_generation_binding_context(decision_path)
    assert kind == "typed_retry_handoff"
    assert decision["authority_commit"] == "a" * 40
    assert candidate["slot_id"] == "slot-retry01"
    assert candidate["prompt_sha256"] == "1" * 64
    assert binding["provider_prompt_sha256"] == "1" * 64
    assert binding["pose_bound_content_packet_sha256"] == "4" * 64


@pytest.mark.parametrize(
    ("qa", "retries", "expected"),
    [
        ({"disposition": "accept"}, 0, "accept_and_publish"),
        ({"disposition": "retryable_failure", "reason_codes": ["hair_crown_forelock_artifact"]}, 0, "reject_and_retry"),
        ({"disposition": "retryable_failure", "reason_codes": ["hair_crown_forelock_artifact"]}, 1, "reject_and_hold"),
        ({"disposition": "hard_stop", "reason_codes": ["anatomy_failure"]}, 0, "reject_and_hold"),
        ({"disposition": "hard_stop", "hard_stop_reason": "visual_review_unavailable"}, 0, "operational_failure"),
    ],
)
def test_controlled_disposition_is_deterministic_and_never_allows_a_second_retry(qa, retries, expected) -> None:
    assert live_cycle.controlled_autonomous_disposition(qa, retries_performed=retries) == expected
