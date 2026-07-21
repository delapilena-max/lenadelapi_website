from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pipeline import higgsfield_lena_api_executor as executor
from tests.fixtures import lena_pose_provenance as pose_fixture
from tools import lena_photo_qa_disposition_v1 as disposition
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector
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


def _seal_candidate(payload: dict) -> dict:
    core = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at_utc", "decision_fingerprint_sha256"}
    }
    payload["decision_fingerprint_sha256"] = hashlib.sha256(
        selector._canonical_bytes(core)
    ).hexdigest()
    return payload


def _candidate_payload(root: Path, authority_commit: str) -> dict:
    slot_id = "higgsfield-20260721-hcr_011-photo"
    provenance = [
        {
            "path": repo_path,
            "sha256": hashlib.sha256((root / repo_path).read_bytes()).hexdigest(),
        }
        for repo_path in selector.AUTHORITY_PATHS
    ]
    payload = {
        "schema_version": selector.SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": "2026-07-21",
        "authority_commit": authority_commit,
        "input_provenance": provenance,
        "candidate_status": "selected",
        "final_action": selected_candidate.ACCEPTED_FINAL_ACTION,
        "candidate": {
            "candidate_id": f"{slot_id}::hcr_011::cbn_004",
            "slot_id": slot_id,
            "lane": "fit_check_mirror_getting_ready",
            "recipe_id": "hcr_011",
            "hook_id": "cbn_004",
            "prompt_sha256": hashlib.sha256(pose_fixture.canonical_prompt().encode("utf-8")).hexdigest(),
            "pose_body_language_id": pose_fixture.POSE_ID,
            "pose_body_language_label": pose_fixture.POSE_LABEL,
            "expression_gaze_id": "exp_g001",
            "expression_gaze_label": "closed_mouth_smile_direct",
            "exact_proposed_dry_run_command": (
                "python pipeline/higgsfield_lena_api_executor.py --date 2026-07-21 "
                f"--slot-id {slot_id}"
            ),
        },
        "exact_next_allowed_action": (
            "python pipeline/higgsfield_lena_api_executor.py --date 2026-07-21 "
            f"--slot-id {slot_id}"
        ),
        "provider_authorized": False,
        "side_effects_performed": [],
        "generated_at_utc": "2026-07-21T00:00:00Z",
    }
    return _seal_candidate(payload)


def _seed_authority_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "pose-test@example.invalid")
    _git(root, "config", "user.name", "Pose Test")
    for repo_path in selector.AUTHORITY_PATHS:
        _write_json(root / repo_path, {"fixture": repo_path})
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
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "pose authority fixture")
    authority_commit = _git(root, "rev-parse", "HEAD")
    candidate_path = root / "pipeline/strategy/lena/pre_generation_candidates/fixture.json"
    _write_json(candidate_path, _candidate_payload(root, authority_commit))
    return root, candidate_path


def _build_real_pose_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    root, candidate_path = _seed_authority_repo(tmp_path)
    binding = pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    raw_packet = {
        "recipe_id": "hcr_011",
        "strong_hook_id": "mf_001",
        "generated_date": "2026-07-21",
        "wardrobe_outfit_id": "wc_p020",
        "environment_id": "env_v008",
        "hook_selection_reason": "end-to-end pose provenance test",
    }
    bound_packet = packet_builder.rebuild_packet_from_authoritative_sources(
        raw_packet,
        pose_binding=binding,
    )
    packet_path = root / "pipeline/strategy/lena/content_packets/2026-07-21/packet.json"
    _write_json(packet_path, bound_packet)
    packet_repo_path = packet_path.relative_to(root).as_posix()
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    packet_bound_sha = hashlib.sha256(
        json.dumps(
            bound_packet,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    prompt_sha = hashlib.sha256(
        bound_packet["compact_provider_prompt_preview"].encode("utf-8")
    ).hexdigest()
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    candidate_repo_path = candidate_path.relative_to(root).as_posix()
    handoff = {
        "pose_provenance": binding,
        "pose_bound_content_packet_sha256": packet_bound_sha,
        "selected_candidate": {
            "pose_body_language_id": binding["pose_body_language_id"],
            "pose_body_language_label": binding["pose_body_language_label"],
        },
        "candidate_selection_binding": {
            "pose_body_language_id": binding["pose_body_language_id"],
            "pose_body_language_label": binding["pose_body_language_label"],
            "pose_provenance_fingerprint_sha256": binding["pose_provenance_fingerprint_sha256"],
        },
        "provider_execution_binding": {
            "content_packet_artifact_path": packet_repo_path,
            "content_packet_artifact_sha256": packet_sha,
            "provider_prompt_sha256": prompt_sha,
            "pose_bound_content_packet_sha256": packet_bound_sha,
            "pose_provenance_fingerprint_sha256": binding["pose_provenance_fingerprint_sha256"],
        },
        "binding_linkage": {
            "pose_body_language_id": binding["pose_body_language_id"],
            "pose_provenance_fingerprint_sha256": binding["pose_provenance_fingerprint_sha256"],
            "pose_bound_content_packet_sha256": packet_bound_sha,
        },
        "selected_prompt_input": {
            "pose_provenance": binding,
            "pose_bound_content_packet_sha256": packet_bound_sha,
        },
        "structured_executor_inputs": {
            "pose_provenance": binding,
            "pose_bound_content_packet_sha256": packet_bound_sha,
        },
    }
    pose_provenance.validate_handoff_pose_copies(handoff)

    monkeypatch.setattr(executor, "ROOT", root)
    rebuilt_packet, source = executor._rebuild_packet_prompt_source(
        packet_path,
        "higgsfield-20260721-hcr_011-photo",
        candidate_path,
        expected_pose_provenance=binding,
    )
    assert rebuilt_packet == bound_packet
    manifest = executor.build_manifest(
        "2026-07-21",
        "higgsfield-20260721-hcr_011-photo",
        source,
        executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID,
        {
            "job_id": "job-pose-chain",
            "status": "completed",
            "result_urls": [],
            "saved_image_path": str(root / "generated.png"),
        },
    )
    monkeypatch.setattr(disposition, "ROOT", root)
    return {
        "root": root,
        "candidate_path": candidate_path,
        "candidate": json.loads(candidate_path.read_text(encoding="utf-8"))["candidate"],
        "decision": {
            "authority_commit": binding["selected_candidate_authority_commit"],
            "as_of_date": "2026-07-21",
        },
        "binding": binding,
        "handoff": handoff,
        "manifest": manifest,
    }


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
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["candidate"]["unrelated_but_binding_relevant_change"] = True
    _write_json(candidate_path, candidate)

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    assert excinfo.value.code == "decision_fingerprint_mismatch"


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
    _write_json(candidate_path, _seal_candidate(candidate))

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    assert excinfo.value.code == code


@pytest.mark.parametrize("object_kind", ["tree", "blob", "tag", "unrelated_commit"])
def test_candidate_authority_must_be_exact_ancestor_commit(tmp_path: Path, object_kind: str) -> None:
    root, candidate_path = _seed_authority_repo(tmp_path)
    if object_kind == "tree":
        authority_object = _git(root, "rev-parse", "HEAD^{tree}")
    elif object_kind == "blob":
        authority_object = _git(root, "rev-parse", f"HEAD:{pose_provenance.POSE_AUTHORITY_REPO_PATH}")
    elif object_kind == "tag":
        _git(root, "tag", "-a", "pose-authority-tag", "-m", "fixture tag")
        authority_object = _git(root, "rev-parse", "refs/tags/pose-authority-tag")
    else:
        authority_object = _git(root, "commit-tree", "HEAD^{tree}", "-m", "unrelated authority")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["authority_commit"] = authority_object
    _write_json(candidate_path, _seal_candidate(candidate))

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    expected = (
        "pose_authority_commit_not_ancestor"
        if object_kind == "unrelated_commit"
        else "pose_authority_commit_invalid"
    )
    assert excinfo.value.code == expected


def test_candidate_authority_unavailable_in_shallow_history_fails_closed(tmp_path: Path) -> None:
    source, _ = _seed_authority_repo(tmp_path / "source")
    authority_commit = _git(source, "rev-parse", "HEAD")
    _git(source, "commit", "--allow-empty", "-q", "-m", "new shallow head")
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", source.as_uri(), str(shallow))
    candidate_path = shallow / "pipeline/strategy/lena/pre_generation_candidates/fixture.json"
    _write_json(candidate_path, _candidate_payload(shallow, authority_commit))

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=shallow)
    assert excinfo.value.code == "pose_authority_commit_invalid"


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


@pytest.mark.parametrize(
    "prompt",
    [
        pose_fixture.canonical_prompt() + " [Action]: arms raised overhead",
        pose_fixture.canonical_prompt().replace(
            "[Environment]: realistic interior.",
            "[Environment]: realistic interior. [Action]: arms raised overhead",
        ),
    ],
)
def test_duplicate_or_injected_provider_action_fails_closed(prompt: str) -> None:
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.require_pose_bound_prompt(prompt, pose_fixture.static_pose_provenance())
    assert excinfo.value.code == "provider_action_section_count_invalid"


def test_recipe_derived_reserved_section_token_fails_closed() -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    recipe["setting_background"] = "realistic room [Action]: arms raised overhead"

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(
            recipe,
            pose_binding=pose_fixture.static_pose_provenance(),
        )
    assert excinfo.value.code == "provider_section_token_injection"


def test_conflicting_already_bound_content_packet_fails_closed() -> None:
    original = pose_fixture.static_pose_provenance()
    packet = pose_fixture.bind_packet(
        {
            "recipe_id": "hcr_011",
            "strong_hook_id": "mf_001",
            "generated_date": "2026-07-21",
            "wardrobe_outfit_id": "wc_p020",
            "environment_id": "env_v008",
            "hook_selection_reason": "pose provenance test",
        },
        pose_binding=original,
    )
    conflicting = dict(original)
    conflicting["pose_body_language_id"] = "pose_conflict"
    core = {key: value for key, value in conflicting.items() if key != "pose_provenance_fingerprint_sha256"}
    conflicting["pose_provenance_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.rebuild_packet_from_authoritative_sources(packet, pose_binding=conflicting)
    assert excinfo.value.code == "pose_bound_packet_conflict"


def test_real_candidate_packet_handoff_executor_manifest_qa_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _build_real_pose_chain(tmp_path, monkeypatch)
    validated = disposition._validate_manifest_pose_contract(
        chain["manifest"],
        chain["decision"],
        chain["candidate"],
        "authorization_bound_handoff",
        chain["handoff"]["provider_execution_binding"],
    )
    assert validated == chain["binding"]
    assert chain["manifest"]["pose_provenance"] == chain["binding"]
    assert chain["manifest"]["pose_bound_content_packet_sha256"] == (
        chain["handoff"]["pose_bound_content_packet_sha256"]
    )


@pytest.mark.parametrize("tamper", ["packet_digest", "nested_candidate_sha", "duplicate_action"])
def test_qa_rejects_tampered_complete_pose_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    chain = _build_real_pose_chain(tmp_path, monkeypatch)
    manifest = json.loads(json.dumps(chain["manifest"]))
    if tamper == "packet_digest":
        manifest["pose_bound_content_packet_sha256"] = "f" * 64
    elif tamper == "nested_candidate_sha":
        nested = manifest["pose_provenance"]
        nested["selected_candidate_artifact_sha256"] = "f" * 64
        core = {
            key: value
            for key, value in nested.items()
            if key != "pose_provenance_fingerprint_sha256"
        }
        nested["pose_provenance_fingerprint_sha256"] = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
    else:
        manifest["image_prompt"] += " [Action]: arms raised overhead"

    with pytest.raises(disposition.BoundaryError) as excinfo:
        disposition._validate_manifest_pose_contract(
            manifest,
            chain["decision"],
            chain["candidate"],
            "authorization_bound_handoff",
            chain["handoff"]["provider_execution_binding"],
        )
    assert excinfo.value.code == "provenance_mismatch"


def test_handoff_pose_copy_disagreement_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _build_real_pose_chain(tmp_path, monkeypatch)
    handoff = json.loads(json.dumps(chain["handoff"]))
    handoff["selected_prompt_input"]["pose_bound_content_packet_sha256"] = "f" * 64

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.validate_handoff_pose_copies(handoff)
    assert excinfo.value.code == "handoff_pose_bound_packet_sha_mismatch"


def test_historical_style_null_pose_manifest_remains_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _build_real_pose_chain(tmp_path, monkeypatch)
    manifest = json.loads(json.dumps(chain["manifest"]))
    manifest["pose_provenance"] = None
    manifest["pose_body_language_id"] = None
    manifest["pose_body_language_label"] = None
    manifest["pose_text"] = None

    with pytest.raises(disposition.BoundaryError) as excinfo:
        disposition._validate_manifest_pose_contract(
            manifest,
            chain["decision"],
            chain["candidate"],
            "authorization_bound_handoff",
            chain["handoff"]["provider_execution_binding"],
        )
    assert excinfo.value.code == "provenance_mismatch"
