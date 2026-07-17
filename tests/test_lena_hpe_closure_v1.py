from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_engine_closure_v1 as closure_schema
from pipeline.presence import human_presence_contract_v1 as hpe_contract
from pipeline.presence import human_presence_output_qa_v1 as presence_qa
from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from pipeline.prompting import lena_prompt_brain as prompt_brain
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


@pytest.mark.parametrize(
    ("field_path", "mutator"),
    [
        ("viewer_relationship.awareness", lambda contract: contract["viewer_relationship"].__setitem__("awareness", "half_aware_glancing")),
        ("gaze_arc.start_focus", lambda contract: contract["gaze_arc"].__setitem__("start_focus", "already_on_camera")),
        ("expression_arc.peak_state", lambda contract: contract["expression_arc"].__setitem__("peak_state", "warm_smile")),
        ("performance_actions.primary_action", lambda contract: contract["performance_actions"].__setitem__("primary_action", "turn_toward_camera")),
        ("performance_actions.object_interaction", lambda contract: contract["performance_actions"].__setitem__("object_interaction", "drink_or_cup")),
        ("performance_actions.movement_motivation", lambda contract: contract["performance_actions"].__setitem__("movement_motivation", "environmental_cue")),
        ("movement_dynamics.weight_transfer", lambda contract: contract["movement_dynamics"].__setitem__("weight_transfer", "turn_with_hip_rotation")),
        ("sensual_presence.tier", lambda contract: contract["sensual_presence"].__setitem__("tier", "overt_sensual_presence")),
        ("body_presentation.framing_intent", lambda contract: contract["body_presentation"].__setitem__("framing_intent", "face_priority")),
    ],
)
def test_prompt_plan_axes_change_the_active_prompt_text(field_path: str, mutator) -> None:
    contract = _baseline_contract()
    baseline = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")

    mutated_contract = copy.deepcopy(contract)
    mutator(mutated_contract)
    mutated = plan_module.compile_human_presence_prompt_plan(mutated_contract, medium="still_image")

    assert mutated["prompt_text"] != baseline["prompt_text"]
    assert mutated["schema_version"] == baseline["schema_version"]
    assert mutated["medium_interpretation"] == baseline["medium_interpretation"]
    assert mutated["character_doctrine_provenance"] == baseline["character_doctrine_provenance"]
    assert field_path


def test_failure_indicators_influence_the_active_prompt_text(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _baseline_contract()
    baseline = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")
    monkeypatch.setattr(
        hpe_contract,
        "presence_failure_indicators",
        lambda: (
            "dead_or_unfocused_eyes",
            "mannequin_pose",
            "sexual_styling_without_personality",
        ),
    )
    mutated = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")

    assert "presence-failure avoidance" in baseline["prompt_text"]
    assert mutated["prompt_text"] != baseline["prompt_text"]
    assert "mannequin pose" in mutated["prompt_text"]


def test_closure_report_roundtrip_and_atomic_write(tmp_path: Path) -> None:
    report = closure_schema.build_closure_verification_report(
        current_commit_sha="a" * 40,
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
        controlled_proof_readiness="verified",
        ordinary_lane_readiness="not_applicable",
        required_artifact_paths={"candidate_decision": "x.json"},
        blocking_findings=[],
    )
    assert closure_schema.validate_closure_verification_report(report) is report

    output = tmp_path / "closure.json"
    written, created = proof_mod._write_json_atomic(output, report)
    assert created is True
    assert written == output
    written_again, created_again = proof_mod._write_json_atomic(output, report)
    assert written_again == output
    assert created_again is False

    conflict = copy.deepcopy(report)
    conflict["closure_status"] = "not_verified"
    with pytest.raises(proof_mod.HPEControlledProofError):
        proof_mod._write_json_atomic(output, conflict)


def test_controlled_and_ordinary_proof_orchestration(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    aligned_calls: list[dict[str, Any]] = []

    def semantic_provider(**kwargs: Any) -> dict[str, Any]:
        aligned_calls.append(kwargs)
        return {
            "semantic_status": "aligned",
            "semantic_findings": [],
            "semantic_result_provenance": {
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "request_binding_sha256": "a" * 64,
                "evaluated_at_utc": "2026-07-17T12:00:00Z",
                "response_schema_version": presence_qa.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            },
            "semantic_error": None,
        }

    controlled = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "controlled",
        controlled_proof=True,
        live_presence_semantic_review=True,
        semantic_provider=semantic_provider,
        dry_run=True,
    )

    assert len(aligned_calls) == 1
    assert controlled["lane_type"] == "controlled_proof"
    assert controlled["qa_artifact"]["semantic_status"] == "aligned"
    assert controlled["qa_artifact"]["integrity_status"] in {"valid", "not_assessable"}

    ordinary_calls: list[dict[str, Any]] = []

    def ordinary_semantic_provider(**kwargs: Any) -> dict[str, Any]:
        ordinary_calls.append(kwargs)
        return {
            "semantic_status": "aligned",
            "semantic_findings": [],
            "semantic_result_provenance": None,
            "semantic_error": None,
        }

    ordinary = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "ordinary",
        controlled_proof=False,
        live_presence_semantic_review=False,
        semantic_provider=ordinary_semantic_provider,
        dry_run=True,
    )

    assert ordinary_calls == []
    assert ordinary["lane_type"] == "ordinary_lane"
    assert ordinary["qa_artifact"]["semantic_status"] == "not_evaluated"


def test_integrity_block_skips_semantic_provider(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    generated = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=None,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "seed",
        controlled_proof=True,
        live_presence_semantic_review=False,
        dry_run=True,
    )
    candidate_path = Path(generated["selected_candidate_artifact_path"])
    tampered = json.loads(candidate_path.read_text(encoding="utf-8"))
    tampered["candidate"]["plan_fingerprint_sha256"] = "0" * 64
    candidate_path.write_text(json.dumps(tampered, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    calls: list[dict[str, Any]] = []

    def forbidden_provider(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "semantic_status": "aligned",
            "semantic_findings": [],
            "semantic_result_provenance": None,
            "semantic_error": None,
        }

    rerun = proof_mod.run_hpe_controlled_proof(
        date_str=DATE,
        slot_id=SLOT_ID,
        image_index=0,
        candidate_input=candidate_path,
        manifest=manifest_path,
        image=image_path,
        output_root=tmp_path / "blocked",
        controlled_proof=True,
        live_presence_semantic_review=True,
        semantic_provider=forbidden_provider,
        dry_run=True,
    )

    assert calls == []
    assert rerun["qa_artifact"]["integrity_status"] == "invalid"
    assert rerun["qa_artifact"]["semantic_status"] == "not_assessable"


def test_authority_state_is_invariant_across_semantic_statuses(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    manifest_path = tmp_path / "manifest.json"
    _tiny_png(image_path)
    _write_manifest(manifest_path, image_path.name)

    statuses = ["aligned", "findings_present", "error", "not_assessable", "not_evaluated"]
    reference: dict[str, Any] | None = None
    for status in statuses:
        proof = proof_mod.run_hpe_controlled_proof(
            date_str=DATE,
            slot_id=SLOT_ID,
            image_index=0,
            candidate_input=None,
            manifest=manifest_path,
            image=image_path,
            output_root=tmp_path / status,
            controlled_proof=False,
            live_presence_semantic_review=status != "not_evaluated",
            semantic_provider=proof_mod._semantic_provider_for_status(status, _baseline_contract()) if status != "not_evaluated" else None,
            dry_run=True,
        )
        summary = {
            "candidate_id": proof["selected_candidate_id"],
            "qa_status": proof["qa_artifact"]["recommendation"],
            "integrity_status": proof["qa_artifact"]["integrity_status"],
        }
        if reference is None:
            reference = summary
        else:
            assert summary == reference


def test_verifier_roundtrip_on_proof_report(tmp_path: Path) -> None:
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
    closure = closure_verifier.verify_closure_report(proof_path, base_commit_sha="b" * 40)
    assert closure["closure_status"] == "verified"
    assert closure_schema.validate_closure_verification_report(closure) is closure
