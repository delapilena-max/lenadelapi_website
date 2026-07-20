from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pipeline import higgsfield_lena_api_executor as executor
from tests.fixtures import lena_pose_provenance as pose_fixture
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_pose_provenance_v1 as pose_provenance


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _seed_authority_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "pose-test@example.invalid")
    _git(root, "config", "user.name", "Pose Test")
    bank_path = root / pose_provenance.POSE_AUTHORITY_REPO_PATH
    _write_json(
        bank_path,
        {
            "version": "1",
            "combos": [
                {
                    "pose_body_language_id": pose_fixture.POSE_ID,
                    "label": pose_fixture.POSE_LABEL,
                    "text": pose_fixture.POSE_TEXT,
                }
            ],
        },
    )
    _git(root, "add", pose_provenance.POSE_AUTHORITY_REPO_PATH)
    _git(root, "commit", "-q", "-m", "pose authority fixture")
    authority_commit = _git(root, "rev-parse", "HEAD")
    candidate_path = root / "pipeline/strategy/lena/pre_generation_candidates/fixture.json"
    _write_json(
        candidate_path,
        {
            "schema_version": "lena_pre_generation_candidate_gate_v1",
            "authority_commit": authority_commit,
            "candidate_status": "selected",
            "candidate": {
                "candidate_id": "fixture-candidate",
                "pose_body_language_id": pose_fixture.POSE_ID,
                "pose_body_language_label": pose_fixture.POSE_LABEL,
            },
        },
    )
    return root, candidate_path


def test_candidate_pose_authority_is_git_bound_and_tamper_evident(tmp_path: Path) -> None:
    root, candidate_path = _seed_authority_repo(tmp_path)
    binding = pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)

    assert binding["pose_body_language_id"] == pose_fixture.POSE_ID
    assert binding["pose_body_language_label"] == pose_fixture.POSE_LABEL
    assert binding["pose_text"] == pose_fixture.POSE_TEXT
    assert binding["selected_candidate_artifact_sha256"] == hashlib.sha256(candidate_path.read_bytes()).hexdigest()

    bank_path = root / pose_provenance.POSE_AUTHORITY_REPO_PATH
    bank_path.write_text(bank_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    assert excinfo.value.code == "pose_authority_worktree_drift"


def test_candidate_changed_after_pose_authority_issuance_fails_hash_binding(tmp_path: Path) -> None:
    root, candidate_path = _seed_authority_repo(tmp_path)
    binding = pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["candidate"]["unrelated_but_binding_relevant_change"] = True
    _write_json(candidate_path, candidate)
    changed_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.validate_pose_provenance(
            binding,
            expected_candidate_sha256=changed_sha,
        )
    assert excinfo.value.code == "pose_candidate_sha_mismatch"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda candidate: candidate["candidate"].pop("pose_body_language_id"), "pose_identity_missing"),
        (lambda candidate: candidate["candidate"].update({"pose_body_language_label": "wrong"}), "pose_label_mismatch"),
    ],
)
def test_candidate_pose_missing_or_mismatched_fails_closed(tmp_path: Path, mutation, code: str) -> None:
    root, candidate_path = _seed_authority_repo(tmp_path)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    mutation(candidate)
    _write_json(candidate_path, candidate)

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    assert excinfo.value.code == code


def test_bound_packet_uses_canonical_pose_and_marks_recipe_pose_non_authoritative(tmp_path: Path) -> None:
    root, candidate_path = _seed_authority_repo(tmp_path)
    binding = pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    packet = packet_builder.rebuild_packet_from_authoritative_sources(
        {
            "recipe_id": "hcr_011",
            "strong_hook_id": "mf_001",
            "generated_date": "2026-07-21",
            "wardrobe_outfit_id": "wc_p020",
            "environment_id": "env_v008",
            "hook_selection_reason": "pose provenance test",
        },
        pose_binding=binding,
    )

    assert packet["high_caliber_source_sections"]["subject_pose"] != binding["pose_text"]
    assert packet["high_caliber_source_sections"]["subject_pose_semantics"] == (
        pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS
    )
    assert packet["high_caliber_source_sections"]["provider_action_pose"] == binding["pose_text"]
    pose_provenance.require_pose_bound_prompt(packet["compact_provider_prompt_preview"], binding)


def test_provider_action_and_manifest_pose_disagreement_fail_closed() -> None:
    binding = pose_fixture.static_pose_provenance()
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.require_pose_bound_prompt(
            pose_fixture.canonical_prompt().replace(pose_fixture.POSE_TEXT, "a different pose"),
            binding,
        )
    assert excinfo.value.code == "provider_action_pose_mismatch"

    source = {
        "resolver": "fixture",
        "slot_prefix": "fixture",
        "pack_count": 1,
        "pack_variety_warnings": [],
        "image": {
            "slot_id": "fixture-photo",
            "image_prompt": pose_fixture.canonical_prompt(),
            "pose_body_language_id": "wrong",
            "pose_body_language_label": binding["pose_body_language_label"],
            "pose_text": binding["pose_text"],
            "pose_provenance": binding,
            "validation": {
                "final_expression_text": "calm expression",
                "expression_safe_fallback_used": False,
                "expression_safe_fallback_reason": None,
                "expression_scene_gaze_conflict_terms_found": [],
            },
        },
    }
    with pytest.raises(executor.HandoffArtifactError) as manifest_error:
        executor.build_manifest("2026-07-21", "fixture-photo", source, "fixture-soul", None)
    assert manifest_error.value.code == "manifest_pose_provenance_mismatch"
