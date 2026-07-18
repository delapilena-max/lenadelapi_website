from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from pipeline.qa import lena_photo_qa
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools import lena_generation_qa_package_dryrun_v1 as cycle
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder


DATE = "2026-07-18"
SLOT_ID = "lenagate202607176924dc10-pack000-00-photo"
RECIPE_ID = "hcr_011"
HOOK_ID = "cbn_001"
PROMPT_SHA = "e3baa48b5e0949d42008007c7182ab2a3ca36693a45dfc90e67d46878af065ae"
AUTHORITY_COMMIT = "b" * 40


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def _recipe_bank() -> dict:
    return {
        "recipes": [
            {
                "id": RECIPE_ID,
                "scene_type": "mirror_fitcheck",
                "content_pillar": "style_and_getting_ready",
                "platform_fit": ["Instagram Feed"],
                "best_content_type": "photo",
                "visual_hook_reason": "mirror hook",
                "human_reason": "private getting-ready energy",
                "style_lighting": "late afternoon light",
                "subject_pose": "adjusting one earring",
                "fashion_accessories": "dusty rose top and jeans",
                "setting_background": "bedroom mirror",
                "technical_keywords": "natural grain",
                "negative_constraints": "No identity drift.",
                "caption_draft": "mirror check",
                "scene_logic_contract": {"environment_realism_notes": "lived-in bedroom"},
                "production_proof_mode": True,
                "wardrobe_outfit_id": "wc_fixture",
                "environment_id": "env_fixture",
                "environment_context": "Environment: bedroom mirror.",
                "proof_control_role": "dry_run_only",
            }
        ]
    }


def _hook_bank() -> dict:
    return {
        "hooks": [
            {
                "id": HOOK_ID,
                "category": "mirror_fitcheck",
                "hook_text": "This Stayed In The Camera Roll For A Minute.",
                "caption_followup": "I stood there for a minute. So did the mirror.",
                "optional_reels_opening_line": "A quick mirror save.",
                "suggested_comment_reply_angle": "quiet second-opinion energy",
                "scores": {"total_score": 91},
            }
        ]
    }


def _approval_context(tmp_path: Path) -> dict[str, object]:
    approval_path = tmp_path / "approval.json"
    candidate_path = tmp_path / "candidate.json"
    handoff_path = tmp_path / "handoff.json"
    candidate = {
        "candidate_id": f"{SLOT_ID}::{RECIPE_ID}::{HOOK_ID}",
        "slot_id": SLOT_ID,
        "lane": "mirror outfit check",
        "recipe_id": RECIPE_ID,
        "hook_id": HOOK_ID,
        "prompt_sha256": PROMPT_SHA,
        "authority_commit": AUTHORITY_COMMIT,
        "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {SLOT_ID}",
    }
    _write_json(candidate_path, candidate)
    candidate_sha256 = cycle._sha256_file(candidate_path)
    handoff = {
        "selected_candidate_path": str(candidate_path),
        "selected_candidate_sha256": candidate_sha256,
        "selected_candidate": candidate,
        "handoff_path": str(handoff_path),
        "handoff_sha256": "d" * 64,
        "date": DATE,
        "slot_id": SLOT_ID,
        "prompt_sha256": PROMPT_SHA,
    }
    return {
        "approval_path": approval_path,
        "approval_sha256": "a" * 64,
        "approval_result": {
            "approval": {"operator_id": "nicolas"},
            "handoff_facts": handoff,
        },
        "candidate": candidate,
        "candidate_path": candidate_path,
        "candidate_sha256": candidate_sha256,
        "selected_candidate_sha256": candidate_sha256,
        "date": DATE,
        "slot_id": SLOT_ID,
        "prompt_sha256": PROMPT_SHA,
        "authority_commit": candidate["authority_commit"],
        "media_type": "photo",
        "handoff_path": handoff_path,
        "handoff_sha256": "d" * 64,
    }


def _manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "pipeline" / "higgsfield_debug" / DATE / SLOT_ID / "lena_hpe_output_qa_manifest.json"


def _image_path(tmp_path: Path) -> Path:
    return tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{SLOT_ID}_seed.png"


def _qa_pass_artifact(slot_id: str = SLOT_ID, date_str: str = DATE) -> dict:
    slot = {"slot_id": slot_id, "media_type": "photo", "metadata": {}}
    artifact = lena_photo_qa.build_qa_template(slot, date_str)
    for key in lena_photo_qa.QA_CHECKLIST_KEYS:
        artifact["checklist"][key]["status"] = "pass"
        artifact["checklist"][key]["notes"] = f"{key} passed"
    artifact["production_scoring"]["hook_strength"] = {"score": "moderate", "notes": "hook works"}
    artifact["production_scoring"]["styling_sexy_platform_safe"] = {"status": "pass", "notes": "adult non-explicit styling allowed"}
    artifact["production_scoring"]["outfit_variety_vs_recent_posts"] = {"status": "not_yet_measured", "notes": "advisory"}
    artifact["production_scoring"]["scene_variety_vs_recent_posts"] = {"status": "not_yet_measured", "notes": "advisory"}
    artifact["production_scoring"]["allure_level"] = {"level": "mild", "notes": "present"}
    artifact["production_scoring"]["it_girl_energy"] = {"status": "pass", "notes": "present"}
    artifact["production_scoring"]["body_visibility_score"] = {"score": "high", "notes": "present"}
    artifact["production_scoring"]["outfit_hook_score"] = {"score": "moderate", "notes": "present"}
    artifact["production_scoring"]["pose_attitude_score"] = {"score": "moderate", "notes": "present"}
    artifact["production_scoring"]["feed_worthy_reason"] = "adult styling is intentional and coherent"
    artifact["reviewed_by"] = "tester"
    artifact["reviewed_at_utc"] = "2026-07-18T00:00:00Z"
    artifact["overall"] = "pass"
    artifact["failure_reasons"] = []
    return artifact


def _qa_fail_artifact(slot_id: str = SLOT_ID, date_str: str = DATE) -> dict:
    artifact = _qa_pass_artifact(slot_id, date_str)
    artifact["production_scoring"]["styling_sexy_platform_safe"] = {"status": "fail", "notes": "explicit exposure"}
    artifact["overall"] = "fail"
    artifact["failure_reasons"] = ["explicit exposure"]
    return artifact


def _patch_cycle_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cycle, "DEFAULT_APPROVAL_ROOT", tmp_path / "pipeline" / "approvals" / "lena" / "generation")
    monkeypatch.setattr(cycle, "DEFAULT_CANDIDATE_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates")
    monkeypatch.setattr(cycle, "DEFAULT_MANIFEST_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    monkeypatch.setattr(cycle, "DEFAULT_IMAGE_ROOT", tmp_path / "pipeline" / "higgsfield_library" / "lena")
    monkeypatch.setattr(cycle, "DEFAULT_QA_ROOT", tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa")
    monkeypatch.setattr(cycle, "DEFAULT_REPORTS_ROOT", tmp_path / "pipeline" / "autonomy" / "lena" / "dry_run_cycles")


def _monkeypatch_success_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "010203")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T01:02:03")
    monkeypatch.setattr(cycle, "resolve_approved_candidate", lambda _path: _approval_context(tmp_path))
    monkeypatch.setattr(packet_builder, "load_json", lambda path: _recipe_bank() if Path(path) == Path(packet_builder.RECIPE_BANK) else _hook_bank())
    monkeypatch.setattr(cycle.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("wrapper must not spawn subprocesses")))


def _patch_packet_output_root(monkeypatch: pytest.MonkeyPatch, packet_root: Path) -> None:
    monkeypatch.setattr(packet_builder, "OUTPUT_BASE", str(packet_root))


def _write_valid_generation_result(
    tmp_path: Path,
    *,
    manifest_extra: dict[str, Any] | None = None,
    slot_id: str = SLOT_ID,
    date_str: str = DATE,
) -> tuple[Path, Path]:
    manifest_path = _manifest_path(tmp_path)
    image_path = _image_path(tmp_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"PNG")
    manifest = {
        "schema_version": "human_presence_output_qa_manifest_v1",
        "outputs": [f"{slot_id}_seed.png"],
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    _write_json(manifest_path, manifest)
    return manifest_path, image_path


def _write_qa_artifact(tmp_path: Path, artifact: dict) -> Path:
    qa_path = tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa" / DATE / SLOT_ID / f"presence_qa_{SLOT_ID}_00.json"
    return _write_json(qa_path, artifact)


def test_successful_chain_writes_report_and_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _monkeypatch_success_path(monkeypatch, tmp_path)
    packet_root = tmp_path / "packets"
    _patch_packet_output_root(monkeypatch, packet_root)
    manifest_path, _image_path = _write_valid_generation_result(tmp_path)
    qa_path = _write_qa_artifact(tmp_path, _qa_pass_artifact())

    report_root = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(qa_path),
        "--manifest-artifact",
        str(manifest_path),
        "--report-root",
        str(report_root),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena"),
        "--packet-root",
        str(packet_root),
    ])

    assert cycle.main() == 0

    report_path = report_root / DATE / "lena_generation_qa_package_dry_run_2026-07-18_010203.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["autonomous_stages"] == list(cycle.AUTONOMOUS_STAGES)
    assert report["manual_stages"] == list(cycle.MANUAL_STAGES)
    assert [item["stage"] for item in report["stages"]] == [
        "approved_candidate_resolution",
        "generation_result_intake",
        "image_qa_validation",
        "caption_package_creation",
    ]
    assert report["publishing_authorized"] is False
    assert report["safeguards"]["provider_calls_performed"] == 0
    assert report["safeguards"]["publish_calls_performed"] == 0
    assert report["safeguards"]["publishing_authorized"] is False
    assert report["safeguards"]["retries_performed"] == 0
    assert report["safeguards"]["retry_cap"] == 0
    assert report["safeguards"]["hard_spend_cap_usd"] == 0
    assert report["safeguards"]["recurring_scheduler"] is False
    assert report["prompt_binding_verified"] is False
    assert report["asserted_lineage"]["prompt_sha256"] == PROMPT_SHA
    assert report["asserted_lineage"]["authority_commit"] == AUTHORITY_COMMIT
    assert report["verified_lineage"]["approval_artifact_sha256"] == report["approval_sha256"]
    assert report["verified_lineage"]["candidate_artifact_sha256_expected"] == report["candidate_sha256_expected"]
    assert report["verified_lineage"]["candidate_artifact_sha256_actual"] == report["candidate_sha256"]
    assert report["verified_lineage"]["manifest_artifact_sha256"] == cycle._sha256_file(manifest_path)
    assert report["verified_lineage"]["image_artifact_sha256"] == cycle._sha256_file(_image_path)
    assert report["verified_lineage"]["qa_artifact_sha256"] == cycle._sha256_file(qa_path)
    assert report["verified_lineage"]["packet_artifact_sha256"] == report["packet_sha256"]
    packet_path = Path(report["packet_path"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["provider_call_enabled"] is False
    assert "[Subject Presence]:" in packet["compact_provider_prompt_preview"]
    assert packet["provider_prompt_contract"]["provider_route"] == "higgsfield_forward_no_live"


def test_missing_approval_fails_closed_before_later_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cycle, "now_stamp", lambda: "040506")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T04:05:06")

    calls: list[str] = []

    def missing_approval(_path: Path) -> dict[str, Any]:
        calls.append("approval")
        raise cycle.LenaGenerationQaPackageDryRunError("approval_missing", "approval artifact missing")

    monkeypatch.setattr(cycle, "resolve_approved_candidate", missing_approval)
    monkeypatch.setattr(cycle, "intake_generation_result", lambda **kwargs: (_ for _ in ()).throw(AssertionError("generation stage should not run")))
    monkeypatch.setattr(cycle, "validate_photo_qa_artifact", lambda **kwargs: (_ for _ in ()).throw(AssertionError("qa stage should not run")))
    monkeypatch.setattr(cycle, "build_caption_package", lambda **kwargs: (_ for _ in ()).throw(AssertionError("package stage should not run")))
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "missing-approval.json"),
        "--qa-artifact",
        str(tmp_path / "qa.json"),
        "--report-root",
        str(tmp_path / "reports"),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    assert cycle.main() == 1
    assert calls == ["approval"]
    report = json.loads((tmp_path / "reports" / DATE / "lena_generation_qa_package_dry_run_2026-07-18_040506.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "approved_candidate_resolution"
    assert report["stages"] == []


@pytest.mark.parametrize(
    "exc_code, exc_detail",
    [
        ("generation_result_missing", "result manifest missing"),
        ("manifest_output_binding_mismatch", "wrong image binding"),
    ],
)
def test_generation_result_failures_stop_later_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc_code: str, exc_detail: str
) -> None:
    _monkeypatch_success_path(monkeypatch, tmp_path)
    _patch_packet_output_root(monkeypatch, tmp_path / "packets")
    monkeypatch.setattr(
        cycle,
        "intake_generation_result",
        lambda **kwargs: (_ for _ in ()).throw(cycle.LenaGenerationQaPackageDryRunError(exc_code, exc_detail)),
    )
    monkeypatch.setattr(cycle, "validate_photo_qa_artifact", lambda **kwargs: (_ for _ in ()).throw(AssertionError("qa stage should not run")))
    monkeypatch.setattr(cycle, "build_caption_package", lambda **kwargs: (_ for _ in ()).throw(AssertionError("package stage should not run")))
    qa_path = _write_qa_artifact(tmp_path, _qa_pass_artifact())
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(qa_path),
        "--report-root",
        str(tmp_path / "reports"),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    assert cycle.main() == 1
    report = json.loads((tmp_path / "reports" / DATE / "lena_generation_qa_package_dry_run_2026-07-18_010203.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "generation_result_intake"
    assert [item["stage"] for item in report["stages"]] == ["approved_candidate_resolution"]


def test_qa_failure_stops_package_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _monkeypatch_success_path(monkeypatch, tmp_path)
    _patch_packet_output_root(monkeypatch, tmp_path / "packets")
    manifest_path, _image_path = _write_valid_generation_result(tmp_path)
    qa_path = _write_qa_artifact(tmp_path, _qa_fail_artifact())
    monkeypatch.setattr(cycle, "build_caption_package", lambda **kwargs: (_ for _ in ()).throw(AssertionError("package stage should not run")))
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(qa_path),
        "--manifest-artifact",
        str(manifest_path),
        "--report-root",
        str(tmp_path / "reports"),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    assert cycle.main() == 1
    report = json.loads((tmp_path / "reports" / DATE / "lena_generation_qa_package_dry_run_2026-07-18_010203.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "image_qa_validation"
    assert [item["stage"] for item in report["stages"]] == [
        "approved_candidate_resolution",
        "generation_result_intake",
    ]


def test_photo_qa_validate_allows_adult_non_explicit_styling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    artifact = _qa_pass_artifact()
    qa_path = _write_qa_artifact(tmp_path, artifact)
    result = cycle.validate_photo_qa_artifact(
        qa_artifact_path=qa_path,
        expected_slot_id=SLOT_ID,
        expected_date=DATE,
    )
    assert result["validation_passed"] is True


def test_photo_qa_validate_rejects_explicit_content_safety_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    artifact = _qa_fail_artifact()
    qa_path = _write_qa_artifact(tmp_path, artifact)
    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="styling_sexy_platform_safe"):
        cycle.validate_photo_qa_artifact(
            qa_artifact_path=qa_path,
            expected_slot_id=SLOT_ID,
            expected_date=DATE,
        )


def test_duplicate_packet_output_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _monkeypatch_success_path(monkeypatch, tmp_path)
    packet_root = tmp_path / "packets"
    _patch_packet_output_root(monkeypatch, packet_root)
    manifest_path, _image_path = _write_valid_generation_result(tmp_path)
    qa_path = _write_qa_artifact(tmp_path, _qa_pass_artifact())
    packet_path = packet_root / DATE / f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(qa_path),
        "--manifest-artifact",
        str(manifest_path),
        "--report-root",
        str(tmp_path / "reports"),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    assert cycle.main() == 1
    report = json.loads((tmp_path / "reports" / DATE / "lena_generation_qa_package_dry_run_2026-07-18_010203.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "caption_package_creation"


def test_no_provider_or_publishing_invocation_is_recorded_in_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _monkeypatch_success_path(monkeypatch, tmp_path)
    _patch_packet_output_root(monkeypatch, tmp_path / "packets")
    manifest_path, _image_path = _write_valid_generation_result(tmp_path)
    qa_path = _write_qa_artifact(tmp_path, _qa_pass_artifact())
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(qa_path),
        "--manifest-artifact",
        str(manifest_path),
        "--report-root",
        str(tmp_path / "reports"),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    assert cycle.main() == 0
    report = json.loads((tmp_path / "reports" / DATE / "lena_generation_qa_package_dry_run_2026-07-18_010203.json").read_text(encoding="utf-8"))
    assert report["publishing_authorized"] is False
    assert report["safeguards"]["provider_calls_performed"] == 0
    assert report["safeguards"]["publish_calls_performed"] == 0
    assert report["safeguards"]["publishing_authorized"] is False
    assert report["safeguards"]["retries_performed"] == 0
    assert report["safeguards"]["retry_cap"] == 0
    assert all(stage["stage"] != "retry" for stage in report["stages"])


def test_approval_artifact_path_escape_is_rejected_before_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    malicious = tmp_path / "outside" / "approval.json"
    malicious.parent.mkdir(parents=True, exist_ok=True)
    malicious.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("approval validator should not run")))

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="escapes declared root"):
        cycle.resolve_approved_candidate(malicious)


def test_candidate_sha_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    ctx = _approval_context(tmp_path)
    approval_path = ctx["approval_path"]
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text("{}", encoding="utf-8")
    bad_result = dict(ctx["approval_result"])
    bad_handoff = dict(ctx["approval_result"]["handoff_facts"])
    bad_handoff["selected_candidate_sha256"] = "f" * 64
    bad_result["handoff_facts"] = bad_handoff
    monkeypatch.setattr(approval, "validate_generation_approval_artifact", lambda *args, **kwargs: bad_result)

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="candidate_sha_mismatch"):
        cycle.resolve_approved_candidate(approval_path)


def test_manifest_path_escape_is_rejected_before_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    manifest_path = tmp_path / "escape" / "lena_hpe_output_qa_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        manifest_path,
        {
            "schema_version": "human_presence_output_qa_manifest_v1",
            "outputs": [f"{SLOT_ID}_seed.png"],
        },
    )
    image_root = tmp_path / "pipeline" / "higgsfield_library" / "lena"
    image_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="manifest_path_escape"):
        cycle.intake_generation_result(
            manifest_path=manifest_path,
            image_root=image_root,
            expected_date=DATE,
            expected_slot_id=SLOT_ID,
            expected_prompt_sha256=PROMPT_SHA,
            expected_candidate_id=f"{SLOT_ID}::{RECIPE_ID}::{HOOK_ID}",
            expected_candidate_sha256="c" * 64,
            expected_recipe_id=RECIPE_ID,
            expected_authority_commit=AUTHORITY_COMMIT,
            expected_media_type="photo",
        )


def test_image_path_escape_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / DATE / "slot" / "lena_hpe_output_qa_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        manifest_path,
        {
            "schema_version": "human_presence_output_qa_manifest_v1",
            "outputs": ["../../escape_seed.png"],
        },
    )
    image_root = tmp_path / "pipeline" / "higgsfield_library" / "lena"
    image_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="escapes declared root"):
        cycle.intake_generation_result(
            manifest_path=manifest_path,
            image_root=image_root,
            expected_date=DATE,
            expected_slot_id="../../escape",
            expected_prompt_sha256=PROMPT_SHA,
            expected_candidate_id=f"{SLOT_ID}::{RECIPE_ID}::{HOOK_ID}",
            expected_candidate_sha256="c" * 64,
            expected_recipe_id=RECIPE_ID,
            expected_authority_commit=AUTHORITY_COMMIT,
            expected_media_type="photo",
        )


def test_report_path_escape_is_rejected_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "_report_path", lambda day, stamp, report_root: tmp_path / "escape" / day / f"{stamp}.json")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T01:02:03")
    monkeypatch.setattr(cycle, "resolve_approved_candidate", lambda _path: (_ for _ in ()).throw(AssertionError("stages should not run")))
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(tmp_path / "qa.json"),
        "--report-root",
        str(tmp_path / "reports"),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--image-root",
        str(tmp_path / "pipeline" / "higgsfield_library" / "lena"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="escapes declared root"):
        cycle.main()
    report_root = tmp_path / "reports"
    assert not any(report_root.rglob("*.json"))


def test_prompt_binding_mismatch_when_binding_artifact_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    ctx = _approval_context(tmp_path)
    manifest_path, image_path = _write_valid_generation_result(tmp_path)
    _write_json(
        manifest_path,
        {
            "schema_version": "human_presence_output_qa_manifest_v1",
            "outputs": [f"{SLOT_ID}_seed.png"],
            "prompt_sha256": "0" * 64,
            "authority_commit": AUTHORITY_COMMIT,
            "candidate_id": ctx["candidate"]["candidate_id"],
            "slot_id": SLOT_ID,
            "recipe_id": RECIPE_ID,
            "media_type": "photo",
            "candidate_sha256": ctx["candidate_sha256"],
            "image_sha256": cycle._sha256_file(image_path),
        },
    )

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="does not match the expected binding"):
        cycle.intake_generation_result(
            manifest_path=manifest_path,
            image_root=tmp_path / "pipeline" / "higgsfield_library" / "lena",
            expected_date=DATE,
            expected_slot_id=SLOT_ID,
            expected_prompt_sha256=PROMPT_SHA,
            expected_candidate_id=ctx["candidate"]["candidate_id"],
            expected_candidate_sha256=ctx["candidate_sha256"],
            expected_recipe_id=RECIPE_ID,
            expected_authority_commit=AUTHORITY_COMMIT,
            expected_media_type="photo",
        )


def test_authority_mismatch_when_binding_artifact_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    ctx = _approval_context(tmp_path)
    manifest_path, image_path = _write_valid_generation_result(tmp_path)
    _write_json(
        manifest_path,
        {
            "schema_version": "human_presence_output_qa_manifest_v1",
            "outputs": [f"{SLOT_ID}_seed.png"],
            "prompt_sha256": PROMPT_SHA,
            "authority_commit": "0" * 40,
            "candidate_id": ctx["candidate"]["candidate_id"],
            "slot_id": SLOT_ID,
            "recipe_id": RECIPE_ID,
            "media_type": "photo",
            "candidate_sha256": ctx["candidate_sha256"],
            "image_sha256": cycle._sha256_file(image_path),
        },
    )

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="does not match the expected binding"):
        cycle.intake_generation_result(
            manifest_path=manifest_path,
            image_root=tmp_path / "pipeline" / "higgsfield_library" / "lena",
            expected_date=DATE,
            expected_slot_id=SLOT_ID,
            expected_prompt_sha256=PROMPT_SHA,
            expected_candidate_id=ctx["candidate"]["candidate_id"],
            expected_candidate_sha256=ctx["candidate_sha256"],
            expected_recipe_id=RECIPE_ID,
            expected_authority_commit=AUTHORITY_COMMIT,
            expected_media_type="photo",
        )


def test_packet_path_escape_through_recipe_id_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    packet_root = tmp_path / "packets"
    _patch_packet_output_root(monkeypatch, packet_root)
    malicious_recipe_id = "../../../../escape"
    recipe_bank = {
        "recipes": [
            {
                "id": malicious_recipe_id,
                "scene_type": "mirror_fitcheck",
                "content_pillar": "style_and_getting_ready",
                "platform_fit": ["Instagram Feed"],
                "best_content_type": "photo",
                "visual_hook_reason": "mirror hook",
                "human_reason": "private getting-ready energy",
                "style_lighting": "late afternoon light",
                "subject_pose": "adjusting one earring",
                "fashion_accessories": "dusty rose top and jeans",
                "setting_background": "bedroom mirror",
                "technical_keywords": "natural grain",
                "negative_constraints": "No identity drift.",
                "caption_draft": "mirror check",
                "scene_logic_contract": {"environment_realism_notes": "lived-in bedroom"},
                "production_proof_mode": True,
                "wardrobe_outfit_id": "wc_fixture",
                "environment_id": "env_fixture",
                "environment_context": "Environment: bedroom mirror.",
                "proof_control_role": "dry_run_only",
            }
        ]
    }
    hook_bank = {
        "hooks": [
            {
                "id": HOOK_ID,
                "category": "mirror_fitcheck",
                "hook_text": "This Stayed In The Camera Roll For A Minute.",
                "caption_followup": "I stood there for a minute. So did the mirror.",
                "optional_reels_opening_line": "A quick mirror save.",
                "suggested_comment_reply_angle": "quiet second-opinion energy",
                "scores": {"total_score": 91},
            }
        ]
    }

    def fake_load_json(path: Path) -> dict[str, Any]:
        if str(path).lower().endswith("strong_hook_bank_v1.json"):
            return hook_bank
        return recipe_bank

    monkeypatch.setattr(packet_builder, "load_json", fake_load_json)
    approval_context = _approval_context(tmp_path)
    approval_context["candidate"]["recipe_id"] = malicious_recipe_id
    approval_context["candidate_sha256"] = approval_context["selected_candidate_sha256"]
    approval_context["selected_candidate_sha256"] = approval_context["candidate_sha256"]
    qa_path = _write_qa_artifact(tmp_path, _qa_pass_artifact())

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="packet_path_escape"):
        cycle.build_caption_package(
            approval_context=approval_context,
            qa_context={"qa_artifact_path": qa_path, "qa_artifact_sha256": cycle._sha256_file(qa_path), "qa_artifact": _qa_pass_artifact(), "validation_passed": True},
            packet_root=packet_root,
        )


def test_duplicate_report_rejection_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "010203")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T01:02:03")
    report_root = tmp_path / "reports"
    report_path = report_root / DATE / "lena_generation_qa_package_dry_run_2026-07-18_010203.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "resolve_approved_candidate", lambda _path: (_ for _ in ()).throw(AssertionError("stages should not run")))
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(tmp_path / "qa.json"),
        "--report-root",
        str(report_root),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--image-root",
        str(tmp_path / "pipeline" / "higgsfield_library" / "lena"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa"),
        "--packet-root",
        str(tmp_path / "packets"),
    ])

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="dry-run cycle report already exists"):
        cycle.main()
    assert json.loads(report_path.read_text(encoding="utf-8")) == {}


def test_symlink_escape_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cycle_roots(monkeypatch, tmp_path)
    outside_root = tmp_path / "outside"
    outside_root.mkdir(parents=True, exist_ok=True)
    link_root = tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa" / DATE
    link_root.mkdir(parents=True, exist_ok=True)
    symlink_path = link_root / "symlinked"
    try:
        symlink_path.symlink_to(outside_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported in this environment")
    qa_path = symlink_path / f"presence_qa_{SLOT_ID}_00.json"
    qa_path.write_text("{}", encoding="utf-8")

    with pytest.raises(cycle.LenaGenerationQaPackageDryRunError, match="qa_path_escape"):
        cycle.validate_photo_qa_artifact(
            qa_artifact_path=qa_path,
            expected_slot_id=SLOT_ID,
            expected_date=DATE,
        )
