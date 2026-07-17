from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_contract_v1 as hpe_contract
from pipeline.presence import human_presence_engine_closure_v1 as closure_schema
from pipeline.presence import human_presence_output_qa_v1 as presence_qa
from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from tools import lena_hpe_closure_verification_v1 as closure_verifier
from tools import lena_run_hpe_controlled_proof_v1 as proof_mod
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


DATE = "2026-07-17"
SLOT_ID = "closure-proof-slot-00"


def _tiny_png(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.write_bytes(png_bytes)
    import hashlib

    return hashlib.sha256(png_bytes).hexdigest()


def _write_manifest(path: Path, image_name: str) -> str:
    payload = {"schema_version": "human_presence_output_qa_manifest_v1", "outputs": [image_name]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline_contract() -> dict[str, Any]:
    return lena_profile.build_lena_presence_contract()


def _closure_report_template() -> dict[str, Any]:
    results = {condition_id: "verified" for condition_id in closure_schema.MANDATORY_CONDITION_IDS}
    return closure_schema.build_closure_verification_report(
        current_commit_sha="a" * 40,
        authority_commit_expected="a" * 40,
        authority_commit_final="a" * 40,
        base_commit_sha="b" * 40,
        execution_timestamp_utc="2026-07-17T12:00:00Z",
        branch="codex/hpe-closure-pr4",
        lane_type="controlled_proof",
        selected_slot_id=SLOT_ID,
        selected_candidate_id=f"{SLOT_ID}::hcr_012::cbn_004",
        hpe_plan_fingerprint_sha256="c" * 64,
        candidate_ranking_evidence={"ranking": True},
        selected_candidate_evidence={"selection": True},
        prompt_plan_evidence={"prompt": True},
        final_prompt_influence_evidence=[{"field_path": "viewer_relationship.awareness", "prompt_changed": True}],
        integrity_qa_evidence={"integrity": True},
        semantic_qa_configuration={"live_presence_semantic_review": False},
        semantic_qa_evidence={"semantic_status": "not_evaluated"},
        lifecycle_report_evidence={"qa_status": "not_assessable"},
        authority_boundary_evidence={"qa_status": "not_assessable"},
        required_artifact_paths={"candidate_decision": "x.json"},
        mandatory_condition_results=results,
        blocking_findings=[],
    )


def test_failure_indicators_stay_qa_only_and_do_not_change_provider_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _baseline_contract()
    baseline = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")
    baseline_values = presence_qa._still_image_plan_field_values(baseline)

    monkeypatch.setattr(
        hpe_contract,
        "presence_failure_indicators",
        lambda: ("dead_or_unfocused_eyes", "mannequin_pose", "sexual_styling_without_personality"),
    )
    mutated = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")
    mutated_values = presence_qa._still_image_plan_field_values(mutated)

    assert mutated["prompt_text"] == baseline["prompt_text"]
    assert mutated["selector_bias_terms"] == baseline["selector_bias_terms"]
    assert mutated["failure_indicators"] != baseline["failure_indicators"]
    assert mutated_values["failure_indicators.dead_or_unfocused_eyes"] is True
    assert mutated_values["failure_indicators.mannequin_pose"] is True
    assert baseline_values["failure_indicators.frozen_expression"] is True
    assert mutated_values["failure_indicators.frozen_expression"] is False


def test_closure_schema_requires_mandatory_conditions_and_derives_not_verified() -> None:
    report = _closure_report_template()
    assert report["closure_status"] == "verified"

    report["mandatory_condition_results"]["human_evidence_review"] = "not_verified"
    report["closure_status"] = "not_verified"
    validated = closure_schema.validate_closure_verification_report(report)
    assert validated["closure_status"] == "not_verified"
    assert validated["mandatory_condition_results"]["human_evidence_review"] == "not_verified"

    invalid = _closure_report_template()
    invalid["mandatory_condition_results"]["human_evidence_review"] = "not_applicable"
    with pytest.raises(closure_schema.HumanPresenceEngineClosureError):
        closure_schema.validate_closure_verification_report(invalid)


def test_controlled_proof_produces_bounded_proof_artifact_only(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    proof = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "proof",
        controlled_proof=True,
        live_presence_semantic_review=False,
        dry_run=True,
    )

    proof_path = Path(proof["proof_report_path"])
    closure_path = proof_path.with_name(f"lena_hpe_closure_verification_{SLOT_ID}_00.json")
    assert proof["authority_commit"] == proof["controlled_proof_result"]["authority_commit"]
    assert proof["provider_call_performed"] is False
    assert proof["provider_authorized"] is False
    assert proof["side_effects_performed"] == []
    assert proof["controlled_proof_result"]["ordinary_lane_readiness"] == "not_applicable"
    assert proof_path.is_file()
    assert not closure_path.exists()


def test_verifier_recomputes_hashes_and_writes_not_verified_closure_report(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    proof = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "proof",
        controlled_proof=True,
        live_presence_semantic_review=False,
        dry_run=True,
    )

    report = closure_verifier.verify_closure_report(
        output_root=tmp_path / "proof",
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=False,
    )

    assert report["closure_status"] == "not_verified"
    assert report["mandatory_condition_results"]["connected_path_runtime_verification"] == "verified"
    assert report["mandatory_condition_results"]["provider_free_controlled_proof"] == "verified"
    assert report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == "not_verified"
    assert report["mandatory_condition_results"]["human_evidence_review"] == "not_verified"

    closure_path = tmp_path / "proof" / DATE / SLOT_ID / f"lena_hpe_closure_verification_{SLOT_ID}_00.json"
    assert closure_path.is_file()
    assert json.loads(closure_path.read_text(encoding="utf-8")) == report


def test_verifier_falls_back_when_origin_main_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    proof = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "proof",
        controlled_proof=True,
        live_presence_semantic_review=False,
        dry_run=True,
    )

    original_merge_base = closure_verifier._git_merge_base

    def _raise_merge_base(left: str, right: str) -> str:
        if (left, right) == ("HEAD", "origin/main"):
            raise subprocess.CalledProcessError(128, ["git", "merge-base", left, right])
        return original_merge_base(left, right)

    monkeypatch.setattr(closure_verifier, "_git_merge_base", _raise_merge_base)

    report = closure_verifier.verify_closure_report(
        output_root=tmp_path / "proof",
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
    )

    assert report["closure_status"] == "not_verified"
    assert len(report["base_commit_sha"]) == 40


def test_verifier_rejects_head_mismatch(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "proof",
        controlled_proof=True,
        live_presence_semantic_review=False,
        dry_run=True,
    )

    with pytest.raises(closure_verifier.HPEClosureVerificationError, match="current HEAD"):
        closure_verifier.verify_closure_report(
            output_root=tmp_path / "proof",
            authority_commit_expected="f" * 40,
            require_clean_authority=False,
            dry_run=True,
        )
