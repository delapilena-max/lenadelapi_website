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


def _proof_run(
    tmp_path: Path,
    *,
    live_presence_semantic_review: bool = False,
    semantic_provider=None,
    controlled_proof: bool = True,
):
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
        controlled_proof=controlled_proof,
        live_presence_semantic_review=live_presence_semantic_review,
        semantic_provider=semantic_provider,
        dry_run=True,
    )
    return proof, image_path, manifest_path


def _proof_identity(
    *,
    proof: dict[str, Any],
    image_path: Path,
    candidate_path: Path,
    prompt_path: Path,
    handoff_path: Path,
    receipt_path: Path,
    provider_job_id: str,
    repository: str = "delapilena-max/lenadelapi_website",
    pr_number: int = 81,
    reviewed_head_sha: str = "1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
) -> dict[str, Any]:
    authority_commit = proof["authority_commit"]
    slot_id = str(proof.get("selected_candidate_slot_id") or proof.get("slot_id") or SLOT_ID)
    return {
        "final_ci": {
            "repository": repository,
            "pr_number": pr_number,
            "reviewed_head_sha": reviewed_head_sha,
            "merge_commit_sha": authority_commit,
            "authority_commit": authority_commit,
        },
        "human_review": {
            "candidate_artifact_path": candidate_path.resolve().as_posix(),
            "candidate_artifact_sha256": proof["selected_candidate_artifact_sha256"],
            "reviewed_image_path": image_path.resolve().as_posix(),
            "reviewed_image_sha256": proof["image_sha256"],
            "handoff_artifact_path": handoff_path.resolve().as_posix(),
            "handoff_artifact_sha256": hashlib.sha256(handoff_path.read_bytes()).hexdigest(),
            "execution_receipt_artifact_path": receipt_path.resolve().as_posix(),
            "execution_receipt_artifact_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "provider_job_id": provider_job_id,
            "slot_id": slot_id,
            "prompt_sha256": proof["prompt_package"]["image_prompt_sha256"],
            "authority_commit": authority_commit,
        },
        "manual_semantic_review": {
            "candidate_artifact_path": candidate_path.resolve().as_posix(),
            "candidate_artifact_sha256": proof["selected_candidate_artifact_sha256"],
            "reviewed_image_path": image_path.resolve().as_posix(),
            "reviewed_image_sha256": proof["image_sha256"],
            "execution_receipt_artifact_path": receipt_path.resolve().as_posix(),
            "execution_receipt_artifact_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "provider_job_id": provider_job_id,
            "slot_id": slot_id,
            "prompt_sha256": proof["prompt_package"]["image_prompt_sha256"],
            "authority_commit": authority_commit,
        },
        "ordinary_lane_proof": {
            "candidate_artifact_path": candidate_path.resolve().as_posix(),
            "candidate_artifact_sha256": proof["selected_candidate_artifact_sha256"],
            "reviewed_image_path": image_path.resolve().as_posix(),
            "reviewed_image_sha256": proof["image_sha256"],
            "prompt_sha256": proof["prompt_package"]["image_prompt_sha256"],
            "slot_id": slot_id,
            "authority_commit": authority_commit,
        },
    }


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
    assert normalized["required_checks"][0]["conclusion"] == "pass"
    success_normalized = closure_evidence.validate_final_ci_confirmation_artifact(
        closure_evidence.build_final_ci_confirmation_artifact(
            repository="delapilena-max/lenadelapi_website",
            pr_number=81,
            reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            required_checks=[
                {"check_name": "build", "conclusion": "success"},
                {"check_name": "main_ci_check", "conclusion": "success"},
            ],
            evidence_source="github_checks_api",
            authority_commit_expected="689a490133b991f5a947dd4c980f0af5fc85e09b",
            authority_commit_final="689a490133b991f5a947dd4c980f0af5fc85e09b",
            evidence_collected_at_utc="2026-07-18T00:00:00Z",
        ),
        expected_repository="delapilena-max/lenadelapi_website",
        expected_pr_number=81,
        expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
        expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
    )
    assert all(entry["conclusion"] == "pass" for entry in success_normalized["required_checks"])

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="repository mismatch"):
        closure_evidence.validate_final_ci_confirmation_artifact(
            artifact,
            expected_repository="other/repo",
            expected_pr_number=81,
            expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
            expected_merge_commit_sha="689a490133b991f5a947dd4c980f0af5fc85e09b",
            expected_authority_commit="689a490133b991f5a947dd4c980f0af5fc85e09b",
        )


@pytest.mark.parametrize(
    "conclusion,expected_verified",
    [
        ("success", True),
        ("pass", True),
        ("failure", False),
        ("fail", False),
        ("cancelled", False),
        ("skipped", False),
        ("pending", False),
        ("neutral", False),
        ("timed_out", False),
        ("action_required", False),
        ("stale", False),
        ("startup_failure", False),
    ],
)
def test_final_ci_conclusions_normalize_canonically_and_only_success_verifies(
    tmp_path: Path,
    conclusion: str,
    expected_verified: bool,
) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")

    ci_artifact = closure_evidence.build_final_ci_confirmation_artifact(
        repository="delapilena-max/lenadelapi_website",
        pr_number=81,
        reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        merge_commit_sha=proof["authority_commit"],
        required_checks=[
            {"check_name": "build", "conclusion": conclusion},
            {"check_name": "main_ci_check", "conclusion": conclusion},
        ],
        evidence_source="github_checks_api",
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
    )
    normalized = closure_evidence.validate_final_ci_confirmation_artifact(
        ci_artifact,
        expected_repository="delapilena-max/lenadelapi_website",
        expected_pr_number=81,
        expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        expected_merge_commit_sha=proof["authority_commit"],
        expected_authority_commit=proof["authority_commit"],
    )
    expected_normalized = "pass" if conclusion in {"success", "pass"} else conclusion
    assert all(entry["conclusion"] == expected_normalized for entry in normalized["required_checks"])

    output_root = tmp_path / "proof"
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
        proof_identity=_proof_identity(
            proof=proof,
            image_path=image_path,
            candidate_path=candidate_path,
            prompt_path=prompt_path,
            handoff_path=handoff,
            receipt_path=receipt,
            provider_job_id="job-123",
        ),
    )
    assert report["mandatory_condition_results"]["final_ci_confirmation"] == ("verified" if expected_verified else "not_verified")


@pytest.mark.parametrize(
    "field,mutated_value,match",
    [
        ("repository", "other/repo", "repository mismatch"),
        ("pr_number", 82, "pr_number mismatch"),
        ("reviewed_head_sha", "f" * 40, "reviewed_head_sha mismatch"),
        ("merge_commit_sha", "e" * 40, "merge_commit_sha mismatch"),
        ("authority_commit", "d" * 40, "authority_commit_expected mismatch"),
    ],
)
def test_final_ci_verifier_binds_expected_identity_values(
    tmp_path: Path,
    field: str,
    mutated_value: Any,
    match: str,
) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")

    ci_artifact = closure_evidence.build_final_ci_confirmation_artifact(
        repository="delapilena-max/lenadelapi_website",
        pr_number=81,
        reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        merge_commit_sha=proof["authority_commit"],
        required_checks=[
            {"check_name": "build", "conclusion": "success"},
            {"check_name": "main_ci_check", "conclusion": "success"},
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
        output_root=tmp_path / "proof",
    )

    proof_identity = _proof_identity(
        proof=proof,
        image_path=image_path,
        candidate_path=candidate_path,
        prompt_path=prompt_path,
        handoff_path=handoff,
        receipt_path=receipt,
        provider_job_id="job-123",
    )
    proof_identity["final_ci"][field] = mutated_value

    with pytest.raises(closure_evidence.ClosureEvidenceError, match=match):
        closure_verifier.verify_closure_report(
            output_root=tmp_path / "proof",
            authority_commit_expected=proof["authority_commit"],
            require_clean_authority=False,
            dry_run=True,
            proof_identity=proof_identity,
        )


@pytest.mark.parametrize("mutation_kind", ["null", "missing"])
def test_final_ci_missing_or_null_conclusions_do_not_verify(tmp_path: Path, mutation_kind: str) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")

    ci_artifact = closure_evidence.build_final_ci_confirmation_artifact(
        repository="delapilena-max/lenadelapi_website",
        pr_number=81,
        reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        merge_commit_sha=proof["authority_commit"],
        required_checks=[
            {"check_name": "build", "conclusion": "success"},
            {"check_name": "main_ci_check", "conclusion": "success"},
        ],
        evidence_source="github_checks_api",
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
    )
    for entry in ci_artifact["required_checks"]:
        if mutation_kind == "null":
            entry["conclusion"] = None
        else:
            entry.pop("conclusion", None)
    normalized = closure_evidence.validate_final_ci_confirmation_artifact(
        ci_artifact,
        expected_repository="delapilena-max/lenadelapi_website",
        expected_pr_number=81,
        expected_reviewed_head_sha="1bba68a11a56e352f4c61fb2ea1cd81cc023cb9f",
        expected_merge_commit_sha=proof["authority_commit"],
        expected_authority_commit=proof["authority_commit"],
    )
    assert all(entry["conclusion"] is None for entry in normalized["required_checks"])

    closure_evidence.write_final_ci_confirmation_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=ci_artifact,
        output_root=tmp_path / "proof",
    )
    report = closure_verifier.verify_closure_report(
        output_root=tmp_path / "proof",
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
        proof_identity=_proof_identity(
            proof=proof,
            image_path=image_path,
            candidate_path=candidate_path,
            prompt_path=prompt_path,
            handoff_path=handoff,
            receipt_path=receipt,
            provider_job_id="job-123",
        ),
    )
    assert report["mandatory_condition_results"]["final_ci_confirmation"] == "not_verified"


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
        authority_commit_expected="a" * 40,
        authority_commit_final="a" * 40,
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
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
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
        proof_identity=_proof_identity(
            proof=proof,
            image_path=image_path,
            candidate_path=candidate_path,
            prompt_path=tmp_path / "prompt.txt",
            handoff_path=handoff,
            receipt_path=receipt,
            provider_job_id="job-123",
        ),
    )

    assert report["mandatory_condition_results"]["human_evidence_review"] == "not_verified"


@pytest.mark.parametrize(
    "mutation",
    ["provider_job_id", "handoff_artifact", "handoff_artifact_sha256", "reviewed_image"],
)
def test_human_review_sidecar_binding_rejects_foreign_execution_context(tmp_path: Path, mutation: str) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    output_root = tmp_path / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    other_image = tmp_path / "other-image.png"
    _tiny_png(other_image)
    other_handoff = tmp_path / "other-handoff.json"
    other_handoff.write_text("other-handoff\n", encoding="utf-8")
    other_receipt = tmp_path / "other-receipt.json"
    other_receipt.write_text("other-receipt\n", encoding="utf-8")

    reviewed_image_path = image_path
    reviewed_image_sha256 = proof["image_sha256"]
    handoff_path = handoff
    handoff_sha256 = hashlib.sha256(handoff.read_bytes()).hexdigest()
    provider_job_id = "job-123"
    if mutation == "provider_job_id":
        provider_job_id = "job-foreign"
    elif mutation == "handoff_artifact":
        handoff_path = other_handoff
        handoff_sha256 = hashlib.sha256(other_handoff.read_bytes()).hexdigest()
    elif mutation == "handoff_artifact_sha256":
        pass
    elif mutation == "reviewed_image":
        reviewed_image_path = other_image
        reviewed_image_sha256 = hashlib.sha256(other_image.read_bytes()).hexdigest()
    else:
        raise AssertionError(mutation)

    human_artifact = closure_evidence.build_human_evidence_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=reviewed_image_path,
        reviewed_image_sha256=reviewed_image_sha256,
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=proof["selected_candidate_artifact_sha256"],
        handoff_artifact_path=handoff_path,
        handoff_artifact_sha256=handoff_sha256,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
        provider_job_id=provider_job_id,
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
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

    proof_identity = _proof_identity(
        proof=proof,
        image_path=image_path,
        candidate_path=candidate_path,
        prompt_path=prompt_path,
        handoff_path=handoff,
        receipt_path=receipt,
        provider_job_id="job-123",
    )
    if mutation == "handoff_artifact_sha256":
        proof_identity["human_review"]["handoff_artifact_sha256"] = "f" * 64

    with pytest.raises(closure_verifier.HPEClosureVerificationError, match="does not match the proof context"):
        closure_verifier.verify_closure_report(
            output_root=output_root,
            authority_commit_expected=proof["authority_commit"],
            require_clean_authority=False,
            dry_run=True,
            proof_identity=proof_identity,
        )


def test_human_review_duplicate_sidecars_fail_closed(tmp_path: Path) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    output_root = tmp_path / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    human_artifact = closure_evidence.build_human_evidence_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=proof["image_sha256"],
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=proof["selected_candidate_artifact_sha256"],
        handoff_artifact_path=handoff,
        handoff_artifact_sha256=hashlib.sha256(handoff.read_bytes()).hexdigest(),
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
        provider_job_id="job-123",
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
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
    duplicate_path = output_root / DATE / SLOT_ID / "dup" / f"lena_hpe_human_evidence_review_{SLOT_ID}_00.json"
    duplicate_path.parent.mkdir(parents=True, exist_ok=True)
    conflicting_artifact = dict(human_artifact)
    conflicting_artifact["provider_job_id"] = "job-conflict"
    duplicate_path.write_text(json.dumps(conflicting_artifact, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    with pytest.raises(closure_verifier.HPEClosureVerificationError, match="multiple lena_hpe_human_evidence_review sidecars were found"):
        closure_verifier.verify_closure_report(
            output_root=output_root,
            authority_commit_expected=proof["authority_commit"],
            require_clean_authority=False,
            dry_run=True,
            proof_identity=_proof_identity(
                proof=proof,
                image_path=image_path,
                candidate_path=candidate_path,
                prompt_path=prompt_path,
                handoff_path=handoff,
                receipt_path=receipt,
                provider_job_id="job-123",
            ),
        )


def test_manual_semantic_review_acceptance_can_satisfy_semantic_receipt(tmp_path: Path) -> None:
    proof, image_path, manifest_path = _proof_run(tmp_path)
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
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
        provider_job_id="job-123",
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
        proof_identity=_proof_identity(
            proof=proof,
            image_path=image_path,
            candidate_path=candidate_path,
            prompt_path=prompt_path,
            handoff_path=handoff,
            receipt_path=receipt,
            provider_job_id="job-123",
        ),
    )

    assert report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == "verified"


@pytest.mark.parametrize("mutation", ["execution_receipt_artifact", "reviewed_image", "provider_job_id"])
def test_manual_semantic_review_sidecar_binding_rejects_foreign_execution_context(tmp_path: Path, mutation: str) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    output_root = tmp_path / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")
    other_receipt = tmp_path / "other-receipt.json"
    other_receipt.write_text("other-receipt\n", encoding="utf-8")
    other_image = tmp_path / "other-image.png"
    _tiny_png(other_image)

    reviewed_image_path = image_path
    reviewed_image_sha256 = proof["image_sha256"]
    execution_receipt_path = receipt
    execution_receipt_sha256 = hashlib.sha256(receipt.read_bytes()).hexdigest()
    provider_job_id = "job-123"
    if mutation == "execution_receipt_artifact":
        execution_receipt_path = other_receipt
        execution_receipt_sha256 = hashlib.sha256(other_receipt.read_bytes()).hexdigest()
    elif mutation == "reviewed_image":
        reviewed_image_path = other_image
        reviewed_image_sha256 = hashlib.sha256(other_image.read_bytes()).hexdigest()
    elif mutation == "provider_job_id":
        provider_job_id = "job-foreign"
    else:
        raise AssertionError(mutation)

    manual_artifact = closure_evidence.build_manual_semantic_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=reviewed_image_path,
        reviewed_image_sha256=reviewed_image_sha256,
        prompt_artifact_path=prompt_path,
        prompt_sha256=prompt_sha,
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=proof["selected_candidate_artifact_sha256"],
        execution_receipt_artifact_path=execution_receipt_path,
        execution_receipt_artifact_sha256=execution_receipt_sha256,
        provider_job_id=provider_job_id,
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
        disposition="accepted_for_hpe_closure",
        assessment=[
            {"aspect_id": aspect, "status": "verified", "detail": "observed and acceptable"}
            for aspect in closure_evidence.MANUAL_SEMANTIC_ASPECT_IDS
        ],
        findings=[],
        confirmation_statement=closure_evidence.MANUAL_SEMANTIC_CONFIRMATION_STATEMENT,
        evidence_source=closure_evidence.MANUAL_SEMANTIC_EVIDENCE_SOURCE,
    )
    closure_evidence.write_manual_semantic_review_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=manual_artifact,
        output_root=output_root,
    )

    with pytest.raises(closure_verifier.HPEClosureVerificationError, match="does not match the proof context"):
        closure_verifier.verify_closure_report(
            output_root=output_root,
            authority_commit_expected=proof["authority_commit"],
            require_clean_authority=False,
            dry_run=True,
            proof_identity=_proof_identity(
                proof=proof,
                image_path=image_path,
                candidate_path=candidate_path,
                prompt_path=prompt_path,
                handoff_path=handoff,
                receipt_path=receipt,
                provider_job_id="job-123",
            ),
        )


def test_manual_semantic_review_rejects_foreign_receipt_sha(tmp_path: Path) -> None:
    proof, image_path, _ = _proof_run(tmp_path)
    output_root = tmp_path / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")

    manual_artifact = closure_evidence.build_manual_semantic_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=proof["image_sha256"],
        prompt_artifact_path=prompt_path,
        prompt_sha256=prompt_sha,
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=proof["selected_candidate_artifact_sha256"],
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
        provider_job_id="job-123",
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

    proof_identity = _proof_identity(
        proof=proof,
        image_path=image_path,
        candidate_path=candidate_path,
        prompt_path=prompt_path,
        handoff_path=handoff,
        receipt_path=receipt,
        provider_job_id="job-123",
    )
    proof_identity["manual_semantic_review"]["execution_receipt_artifact_sha256"] = "f" * 64

    with pytest.raises(closure_verifier.HPEClosureVerificationError, match="receipt sha256 does not match the proof context"):
        closure_verifier.verify_closure_report(
            output_root=output_root,
            authority_commit_expected=proof["authority_commit"],
            require_clean_authority=False,
            dry_run=True,
            proof_identity=proof_identity,
        )


@pytest.mark.parametrize(
    "evidence_source",
    ["provider", "provider_semantic_review", "structural_qa", "", None],
)
def test_manual_semantic_review_rejects_non_manual_source_labels(
    tmp_path: Path,
    evidence_source: str | None,
) -> None:
    reviewed = tmp_path / "reviewed.png"
    prompt = tmp_path / "prompt.txt"
    candidate = tmp_path / "candidate.json"
    receipt = tmp_path / "receipt.json"
    _tiny_png(reviewed)
    prompt.write_text("prompt\n", encoding="utf-8")
    candidate.write_text("candidate\n", encoding="utf-8")
    receipt.write_text("receipt\n", encoding="utf-8")
    reviewed_sha = hashlib.sha256(reviewed.read_bytes()).hexdigest()
    prompt_sha = hashlib.sha256(prompt.read_bytes()).hexdigest()
    candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()

    artifact = closure_evidence.build_manual_semantic_review_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=reviewed,
        reviewed_image_sha256=reviewed_sha,
        prompt_artifact_path=prompt,
        prompt_sha256=prompt_sha,
        candidate_artifact_path=candidate,
        candidate_artifact_sha256=candidate_sha,
        execution_receipt_artifact_path=receipt,
        execution_receipt_artifact_sha256=receipt_sha,
        provider_job_id="job-123",
        authority_commit_expected="a" * 40,
        authority_commit_final="a" * 40,
        disposition="accepted_for_hpe_closure",
        assessment=[
            {"aspect_id": aspect, "status": "verified", "detail": "observed and acceptable"}
            for aspect in closure_evidence.MANUAL_SEMANTIC_ASPECT_IDS
        ],
        findings=[],
        confirmation_statement=closure_evidence.MANUAL_SEMANTIC_CONFIRMATION_STATEMENT,
        evidence_source=closure_evidence.MANUAL_SEMANTIC_EVIDENCE_SOURCE,
    )
    mutated = dict(artifact)
    mutated["evidence_source"] = evidence_source

    with pytest.raises(closure_evidence.ClosureEvidenceError, match="evidence_source mismatch"):
        closure_evidence.validate_manual_semantic_review_artifact(mutated)


def test_ordinary_lane_proof_requires_qualified_evidence(tmp_path: Path) -> None:
    proof, image_path, _ = _proof_run(tmp_path, controlled_proof=False)
    output_root = tmp_path / "proof"
    candidate_path = Path(proof["selected_candidate_artifact_path"]).resolve()
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(proof["prompt_package"]["image_prompt"], encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text("handoff\n", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("receipt\n", encoding="utf-8")

    proof_identity = _proof_identity(
        proof=proof,
        image_path=image_path,
        candidate_path=candidate_path,
        prompt_path=prompt_path,
        handoff_path=handoff,
        receipt_path=receipt,
        provider_job_id="job-123",
    )

    not_verified_report = closure_verifier.verify_closure_report(
        output_root=output_root,
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
        proof_identity=proof_identity,
    )
    assert not_verified_report["mandatory_condition_results"]["ordinary_lane_proof"] == "not_verified"
    assert not_verified_report["mandatory_condition_results"]["provider_free_controlled_proof"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }

    ordinary_slot_id = str(proof.get("selected_candidate_slot_id") or proof.get("slot_id") or SLOT_ID)
    ordinary_artifact = closure_evidence.build_ordinary_lane_proof_artifact(
        reviewer_operator_id="nicolas",
        reviewed_image_path=image_path,
        reviewed_image_sha256=proof["image_sha256"],
        prompt_artifact_path=prompt_path,
        prompt_sha256=proof["prompt_package"]["image_prompt_sha256"],
        candidate_artifact_path=candidate_path,
        candidate_artifact_sha256=proof["selected_candidate_artifact_sha256"],
        slot_id=ordinary_slot_id,
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
        disposition="accepted_for_hpe_closure",
        findings=[],
        confirmation_statement=closure_evidence.ORDINARY_LANE_PROOF_CONFIRMATION_STATEMENT,
    )
    closure_evidence.write_ordinary_lane_proof_artifact(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        artifact=ordinary_artifact,
        output_root=output_root,
    )

    verified_report = closure_verifier.verify_closure_report(
        output_root=output_root,
        authority_commit_expected=proof["authority_commit"],
        require_clean_authority=False,
        dry_run=True,
        proof_identity=proof_identity,
    )
    assert verified_report["mandatory_condition_results"]["ordinary_lane_proof"] == "verified"
    assert verified_report["mandatory_condition_results"]["provider_free_controlled_proof"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }
    assert verified_report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }


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
        authority_commit_expected=proof["authority_commit"],
        authority_commit_final=proof["authority_commit"],
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
        provider_job_id="job-123",
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
        proof_identity=_proof_identity(
            proof=proof,
            image_path=image_path,
            candidate_path=candidate_path,
            prompt_path=prompt_path,
            handoff_path=handoff,
            receipt_path=receipt,
            provider_job_id="job-123",
        ),
    )

    assert report["mandatory_condition_results"]["human_evidence_review"] == "verified"
    assert report["mandatory_condition_results"]["controlled_live_semantic_proof_receipt"] == "verified"
    assert report["mandatory_condition_results"]["final_ci_confirmation"] == "verified"
    assert report["mandatory_condition_results"]["ordinary_lane_proof"] == {
        "status": "not_applicable",
        "reason": closure_schema.LANE_NOT_APPLICABLE_REASON,
    }
    assert report["closure_status"] == "verified"
