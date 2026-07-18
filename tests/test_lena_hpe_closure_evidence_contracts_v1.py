from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_closure_evidence_v1 as closure_evidence
from pipeline.presence import human_presence_engine_closure_v1 as closure_schema
from tools import lena_hpe_closure_verification_v1 as closure_verifier
from tools import lena_run_hpe_controlled_proof_v1 as proof_mod


DATE = "2026-07-17"
SLOT_ID = "closure-evidence-slot-00"


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
    return hashlib.sha256(png_bytes).hexdigest()


def _write_manifest(path: Path, image_name: str) -> str:
    payload = {"schema_version": "human_presence_output_qa_manifest_v1", "outputs": [image_name]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proof_run(tmp_path: Path, *, live_presence_semantic_review: bool = False, semantic_provider=None):
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
        live_presence_semantic_review=live_presence_semantic_review,
        semantic_provider=semantic_provider,
        dry_run=True,
    )
    return proof, image_path, manifest_path


def _build_verified_report(lane_type: str, condition_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    results: dict[str, Any] = {condition_id: "verified" for condition_id in closure_schema.MANDATORY_CONDITION_IDS}
    if lane_type == "controlled_proof":
        results["ordinary_lane_proof"] = closure_schema.condition_result("not_applicable")
    else:
        results["provider_free_controlled_proof"] = closure_schema.condition_result("not_applicable")
        results["controlled_live_semantic_proof_receipt"] = closure_schema.condition_result("not_applicable")
    if condition_overrides:
        results.update(condition_overrides)
    report = closure_schema.build_closure_verification_report(
        current_commit_sha="a" * 40,
        authority_commit_expected="a" * 40,
        authority_commit_final="a" * 40,
        base_commit_sha="b" * 40,
        execution_timestamp_utc="2026-07-17T12:00:00Z",
        branch="codex/hpe-closure-contract-repair",
        lane_type=lane_type,
        selected_slot_id=SLOT_ID,
        selected_candidate_id=f"{SLOT_ID}::hcr_012::mf_001",
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
    return report


def test_lane_scoped_applicability_marks_inapplicable_conditions_explicitly() -> None:
    controlled = closure_schema.validate_closure_verification_report(_build_verified_report("controlled_proof"))
    ordinary = closure_schema.validate_closure_verification_report(_build_verified_report("ordinary_lane"))

    assert controlled["closure_status"] == "verified"
    assert controlled["mandatory_condition_results"]["ordinary_lane_proof"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }
    assert ordinary["closure_status"] == "verified"
    assert ordinary["mandatory_condition_results"]["provider_free_controlled_proof"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }
    assert ordinary["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }


def test_not_applicable_on_applicable_condition_is_rejected() -> None:
    invalid = _build_verified_report("controlled_proof")
    invalid["mandatory_condition_results"]["human_evidence_review"] = closure_schema.condition_result("not_applicable")

    with pytest.raises(closure_schema.HumanPresenceEngineClosureError, match="cannot be not_applicable"):
        closure_schema.validate_closure_verification_report(invalid)


def test_final_ci_confirmation_artifact_validation_requires_the_expected_checks(tmp_path: Path) -> None:
    artifact = closure_evidence.build_final_ci_confirmation_artifact(
        repository="delapilena-max/lenadelapi_website",
        pr_number=81,
        reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
        required_checks=[
            {"check_name": "build", "conclusion": "pass", "github_url": "https://github.com/example/build"},
            {"check_name": "main_ci_check", "conclusion": "pass", "check_run_id": 42},
        ],
        evidence_source="github_checks_api",
        authority_commit_expected="689a490133b991f5a947dd4c980f0af5fc85e09b",
        authority_commit_final="689a490133b991f5a947dd4c980f0af5fc85e09b",
        evidence_collected_at_utc="2026-07-18T00:00:00Z",
    )

    normalized = closure_evidence.validate_final_ci_confirmation_artifact(
        artifact,
        expected_repository="delapilena-max/lenadelapi_website",
        expected_pr_number=81,
        expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
        expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
    )
    assert normalized["required_checks"][0]["check_name"] == "build"

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="repository mismatch"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            artifact,
            expected_repository="other/repo",
            expected_pr_number=81,
            expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="pr_number mismatch"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            artifact,
            expected_repository="delapilena-max/lenadelapi_website",
            expected_pr_number=82,
            expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="reviewed_head_sha mismatch"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            artifact,
            expected_repository="delapilena-max/lenadelapi_website",
            expected_pr_number=81,
            expected_reviewed_head_sha="f" * 40,
            expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="merge_commit_sha mismatch"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            artifact,
            expected_repository="delapilena-max/lenadelapi_website",
            expected_pr_number=81,
            expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            expected_merge_commit_sha="f" * 40,
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="required_checks"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            closure_evidence.build_final_ci_confirmation_artifact(
                repository="delapilena-max/lenadelapi_website",
                pr_number=81,
                reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
                merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
                required_checks=[{"check_name": "build", "conclusion": "pass"}],
                evidence_source="github_checks_api",
                authority_commit_expected="689a490133b991f5a947dd4c980f0af5fc85e09b",
                authority_commit_final="689a490133b991f5a947dd4c980f0af5fc85e09b",
            ),
            expected_repository="delapilena-max/lenadelapi_website",
            expected_pr_number=81,
            expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="must pass"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            closure_evidence.build_final_ci_confirmation_artifact(
                repository="delapilena-max/lenadelapi_website",
                pr_number=81,
                reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
                merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
                required_checks=[
                    {"check_name": "build", "conclusion": "fail"},
                    {"check_name": "main_ci_check", "conclusion": "pass"},
                ],
                evidence_source="github_checks_api",
                authority_commit_expected="689a490133b991f5a947dd4c980f0af5fc85e09b",
                authority_commit_final="689a490133b991f5a947dd4c980f0af5fc85e09b",
            ),
            expected_repository="delapilena-max/lenadelapi_website",
            expected_pr_number=81,
            expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )


def test_human_review_artifact_requires_explicit_acceptance(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.png"
    candidate = tmp_path / "candidate.json"
    handoff = tmp_path / "handoff.json"
    receipt = tmp_path / "receipt.json"
    reviewed_sha = _tiny_png(reviewed)
    candidate.write_text("candidate\n", encoding="utf-8")
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt.write_text("receipt\n", encoding="utf-8")
    candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    handoff_sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()

    artifact = closure_evidence.build_human_evidence_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=reviewed,
        reviewed_image_sha256=reviewed_sha,
        candidate_artifact_path=candidate,
        candidate_artifact_sha256=candidate_sha,
        handoff_artifact_path=handoff,
        handoff_artifact_sha256=handoff_sha,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=receipt_sha,
        provider_job_id="job-123",
        disposition="accepted_for_hpe_closure",
        findings=[],
        confirmation_statement=closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT,
        publishing_authorized=False,
    )
    normalized = closure_evidence.validate_human_evidence_review_artifact(artifact)
    assert normalized["disposition"] == "accepted_for_hpe_closure"

    rejected = dict(artifact)
    rejected["disposition"] = "rejected"
    rejected["confirmation_statement"] = closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT
    normalized_rejected = closure_evidence.validate_human_evidence_review_artifact(rejected)
    assert normalized_rejected["disposition"] == "rejected"


def test_human_review_rejection_does_not_verify_closure(tmp_path: Path) -> None:
    proof, image_path, _ = _proof_run(tmp_path / "rejected-proof")
    output_root = tmp_path / "rejected-proof" / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    handoff = tmp_path / "handoff.json"
    receipt = tmp_path / "receipt.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt.write_text("receipt\n", encoding="utf-8")
    handoff_sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()

    rejected_artifact = closure_evidence.build_human_evidence_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=proof["image_sha256"],
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=proof["selected_candidate_artifact_sha256"],
        handoff_artifact_path=handoff,
        handoff_artifact_sha256=handoff_sha,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=receipt_sha,
        provider_job_id="job-123",
        disposition="rejected",
        findings=[{"code": "visual_mismatch", "detail": "review rejected"}],
        confirmation_statement=closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT,
        publishing_authorized=False,
    )
    closure_evidence.write_human_evidence_review_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=rejected_artifact,
        output_root=output_root,
    )

    report = closure_verifier.verify_closure_report(
        output_root=output_root,
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
    )

    assert report["mandatory_condition_results"]["human_evidence_review"] == "not_verified"


def test_manual_semantic_review_acceptance_can_satisfy_semantic_receipt(tmp_path: Path) -> None:
    proof, image_path, manifest_path = _proof_run(tmp_path)
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    image_sha = proof["image_sha256"]
    candidate_sha = proof["selected_candidate_artifact_sha256"]
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()

    manual_artifact = closure_evidence.build_manual_semantic_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=image_sha,
        prompt_artifact_path=prompt_path,
        prompt_sha256=prompt_sha,
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=candidate_sha,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=receipt_sha,
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
        disposition="accepted_for_hpe_closure",
        assessment=[
            {"aspect_id": aspect, "status": "verified", "detail": "observed and acceptable"}
            for aspect in closure_evidence.MANUAL_SEMANTIC_ASPECT_IDS
        ],
        findings=[],
        confirmation_statement=closure_evidence.MANUAL_SEMANTIC_CONFIRMATION_STATEMENT,
        evidence_source="manual_human_semantic_review",
    )
    manual_path = closure_evidence.manual_semantic_review_artifact_path(DATE, SLOT_ID, 0, tmp_path / "proof")
    manual_path.parent.mkdir(parents=True, exist_ok=True)
    manual_path.write_text(json.dumps(manual_artifact, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    report = closure_verifier.verify_closure_report(
        output_root=tmp_path / "proof",
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
    )

    assert report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == "verified"


def test_provider_backed_semantic_review_remains_supported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_semantic_provider(**_: Any) -> dict[str, Any]:
        return {
            "semantic_status": "aligned",
            "semantic_findings": [],
            "semantic_result_provenance": {
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "request_binding_sha256": "d" * 64,
                "evaluated_at_utc": "2026-07-18T00:00:00Z",
                "response_schema_version": "human_presence_semantic_visual_observations_v1",
            },
            "semantic_error": None,
        }

    proof, _, _ = _proof_run(tmp_path, live_presence_semantic_review=True, semantic_provider=fake_semantic_provider)
    report = closure_verifier.verify_closure_report(
        output_root=tmp_path / "proof",
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
    )

    assert report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == "verified"


def test_aggregate_closure_becomes_verified_only_when_all_applicable_evidence_is_present(tmp_path: Path) -> None:
    proof, image_path, _manifest_path = _proof_run(tmp_path)
    output_root = tmp_path / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
    handoff_sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
    candidate_sha = proof["selected_candidate_artifact_sha256"]
    image_sha = proof["image_sha256"]

    human_artifact = closure_evidence.build_human_evidence_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=image_sha,
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=candidate_sha,
        handoff_artifact_path=handoff,
        handoff_artifact_sha256=handoff_sha,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=receipt_sha,
        provider_job_id="job-123",
        disposition="accepted_for_hpe_closure",
        findings=[],
        confirmation_statement=closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT,
        publishing_authorized=False,
    )
    closure_evidence.write_human_evidence_review_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=human_artifact,
        output_root=output_root,
    )

    manual_artifact = closure_evidence.build_manual_semantic_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=image_sha,
        prompt_artifact_path=prompt_path,
        prompt_sha256=prompt_sha,
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=candidate_sha,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=receipt_sha,
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
        disposition="accepted_for_hpe_closure",
        assessment=[
            {"aspect_id": aspect, "status": "verified", "detail": "observed and acceptable"}
            for aspect in closure_evidence.MANUAL_SEMANTIC_ASPECT_IDS
        ],
        findings=[],
        confirmation_statement=closure_evidence.MANUAL_SEMANTIC_CONFIRMATION_STATEMENT,
        evidence_source="manual_human_semantic_review",
    )
    closure_evidence.write_manual_semantic_review_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=manual_artifact,
        output_root=output_root,
    )

    ci_artifact = closure_evidence.build_final_ci_confirmation_artifact(
        repository="delapilena-max/lenadelapi_website",
        pr_number=81,
        reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        merge_commit_sha=proof["authority_commit"],
        required_checks=[
            {"check_name": "build", "conclusion": "pass"},
            {"check_name": "main_ci_check", "conclusion": "pass"},
        ],
        evidence_source="github_checks_api",
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
    )
    closure_evidence.write_final_ci_confirmation_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=ci_artifact,
        output_root=output_root,
    )

    report = closure_verifier.verify_closure_report(
        output_root=output_root,
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
    )

    assert report["mandatory_condition_results"]["human_evidence_review"] == "verified"
    assert report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == "verified"
    assert report["mandatory_condition_results"]["final_ci_confirmation"] == "verified"
    assert report["mandatory_condition_results"]["ordinary_lane_proof"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }
    assert report["closure_status"] == "verified"
