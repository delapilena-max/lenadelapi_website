from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import higgsfield_lena_api_executor as executor
from tests.fixtures import lena_pose_provenance as pose_fixture
from tools import lena_higgsfield_generation_approval_v1 as generation_approval
from tools import lena_photo_qa_disposition_v1 as disposition
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_build_next_live_image_handoff_v1 as handoff_builder
from tools.strategy import lena_execute_retry_decision_v1 as legacy_retry
from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector
from tools.strategy import lena_pose_provenance_v1 as pose_provenance
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff
from tools.strategy import lena_reconciliation_contract_v1 as reconciliation_contract


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_hand_built_candidate_contracts(request, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name.startswith("test_production_selector_"):
        return

    def validate_fixture_issuance(
        artifact: dict,
        *,
        root: Path | None = None,
        freshness_mode: str = selected_candidate.FRESHNESS_MODE_CURRENT,
    ) -> dict:
        if freshness_mode not in {
            selected_candidate.FRESHNESS_MODE_CURRENT,
            selected_candidate.FRESHNESS_MODE_STORED_SNAPSHOT,
        }:
            raise selected_candidate.ConsumerError(
                "freshness_mode_invalid",
                f"unsupported selected-candidate freshness mode: {freshness_mode}",
            )
        candidate = selected_candidate._validate_shape(artifact)
        stored_core, recomputed = selected_candidate._validate_fingerprint(artifact)
        selected_candidate._validate_authority(artifact, root=root)
        return {
            "candidate": candidate,
            "stored_core": stored_core,
            "recomputed_fingerprint_sha256": recomputed,
            "fresh_fingerprint_sha256": recomputed,
            "executor_validation": {"ok": True},
        }

    monkeypatch.setattr(
        selected_candidate,
        "validate_selected_candidate_issuance",
        validate_fixture_issuance,
    )


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
            "expression_canonical_text": pose_fixture.EXPRESSION_TEXT,
            "expression_text": pose_fixture.EXPRESSION_TEXT,
            "expression_safe_fallback_used": False,
            "expression_safe_fallback_reason": None,
            "expression_scene_conflict_terms": [],
            "expression_derivation_scene_action": "standing in a controlled studio portrait",
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
    for repo_path in (*selector.AUTHORITY_PATHS, pose_provenance.POSE_AUTHORITY_REPO_PATH):
        if repo_path == pose_provenance.EXPRESSION_DERIVATION_REPO_PATH:
            target = root / repo_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / repo_path, target)
        elif repo_path == pose_provenance.EXPRESSION_AUTHORITY_REPO_PATH:
            target = root / repo_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / repo_path, target)
        else:
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


def _seed_production_selector_repo(tmp_path: Path) -> tuple[Path, Path, dict]:
    root = tmp_path / "selector-repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "pose-test@example.invalid")
    _git(root, "config", "user.name", "Pose Test")
    authority_paths = dict.fromkeys(
        (
            *selector.AUTHORITY_PATHS,
            pose_provenance.POSE_AUTHORITY_REPO_PATH,
            "pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json",
        )
    )
    for repo_path in authority_paths:
        target = root / repo_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / repo_path, target)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "canonical selector authority fixture")
    authority_commit = _git(root, "rev-parse", "HEAD")
    authorities = selector.load_authorities(root)
    recent = selector.load_recent_content(root)
    candidate = None
    for as_of_date in ("2026-07-21", "2026-07-20", "2026-07-19", "2026-07-18", "2026-07-17"):
        prompt_candidates, prompt_meta = selector.build_prompt_candidates(
            as_of_date,
            authority_commit[:8],
            required_recipe_id="hcr_012",
        )
        candidate, rejected, _ = selector.select_candidate(
            authorities,
            prompt_candidates,
            recent,
            required_recipe_id="hcr_012",
        )
        if candidate is not None:
            break
    assert candidate is not None
    core = selector._decision_core(
        authority_commit,
        as_of_date,
        authorities,
        candidate,
        rejected,
        recent,
        prompt_meta,
        required_recipe_id="hcr_012",
    )
    candidate_path, artifact, _ = selector.write_decision(
        core,
        output_root=root / "pipeline/strategy/lena/pre_generation_candidates",
        generated_at_utc="2026-07-21T00:00:00Z",
    )
    return root, candidate_path, artifact


def _raw_packet_for_candidate(candidate: dict, date_str: str, reason: str) -> dict:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = packet_builder.select_recipe(recipe_bank, candidate["recipe_id"])
    environment_catalog = packet_builder.load_json(packet_builder.ENV_CATALOG)
    environment = next(
        entry
        for entry in environment_catalog["environments"]
        if recipe["scene_type"] in entry.get("allowed_recipe_types", [])
        or recipe["content_pillar"] in entry.get("allowed_recipe_types", [])
    )
    wardrobe_catalog = packet_builder.load_json(packet_builder.WARDROBE_CATALOG)
    wardrobe = next(
        (
            entry
            for entry in wardrobe_catalog["outfits"]
            if entry.get("outfit_id") == candidate.get("wardrobe_outfit_id")
        ),
        next(
            entry
            for entry in wardrobe_catalog["outfits"]
            if entry.get("status") not in {"rejected", "high_risk"}
        ),
    )
    return {
        "recipe_id": candidate["recipe_id"],
        "strong_hook_id": candidate["hook_id"],
        "generated_date": date_str,
        "wardrobe_outfit_id": wardrobe["outfit_id"],
        "environment_id": environment["environment_id"],
        "hook_selection_reason": reason,
    }


def _build_real_pose_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    root, candidate_path, artifact = _seed_production_selector_repo(tmp_path)
    binding = pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    expression_binding = pose_provenance.build_candidate_expression_provenance(
        candidate_path,
        root=root,
    )
    candidate = artifact["candidate"]
    date_str = artifact["as_of_date"]
    raw_packet = _raw_packet_for_candidate(
        candidate,
        date_str,
        "end-to-end pose provenance test",
    )
    bound_packet = packet_builder.rebuild_packet_from_authoritative_sources(
        raw_packet,
        pose_binding=binding,
        expression_binding=expression_binding,
    )
    packet_path = root / (
        f"pipeline/strategy/lena/content_packets/{date_str}/"
        f"lena_content_packet_dryrun_{date_str}_{candidate['recipe_id']}.json"
    )
    _write_json(packet_path, bound_packet)
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    candidate_repo_path = candidate_path.relative_to(root).as_posix()
    next_actions = root / "pipeline/strategy/lena/next_actions" / date_str
    learning_path = next_actions / f"lena_post_outcome_learning_state_{date_str}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{date_str}.json"
    queue_path = next_actions / f"lena_autonomous_generation_queue_dryrun_{date_str}.json"
    reconciliation_path = root / (
        f"pipeline/strategy/lena/reconciliations/{date_str}/"
        "lena_generation_reconciliation_fixture.json"
    )
    learning_summary = {
        "learning_status": "current",
        "current_count": 1,
        "usable_but_incomplete_count": 0,
        "stale_unresolved_count": 0,
        "manual_or_future_capability_required_count": 0,
    }
    learning = {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": date_str,
        "published_post_count": 1,
        "pending_metrics_posts": [],
        "stale_pending_metrics_posts": [],
        "winner_posts": [{"recipe_id": candidate["recipe_id"]}],
        "queue_boosts": {"preferred_recipe_ids": [candidate["recipe_id"]]},
        "metrics_resolution_summary": learning_summary,
    }
    recommendation = {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": date_str,
        "learning_artifact_path": str(learning_path),
        "learning_status": "current",
        "learning_status_label": "learning_current",
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": 1,
        "learning_pending_metrics_count": 0,
        "learning_stale_pending_metrics_count": 0,
        "learning_resolution_state_summary": learning_summary,
        "learning_required_follow_up_action": "no_follow_up_required",
        "learning_winner_post_count": 1,
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": candidate["recipe_id"],
            "recommended_outfit_id": raw_packet["wardrobe_outfit_id"],
            "recommended_environment_id": raw_packet["environment_id"],
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids"],
            "next_live_gate": "review",
        },
    }
    queue = {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "date": date_str,
        "dry_run": True,
        "proof_lane_lock_active": False,
        "queue_slots": [
            {
                "recipe_id": candidate["recipe_id"],
                "title": "Production selector pose chain",
                "scene_type": bound_packet["scene_type"],
                "autonomy_grade": "ready",
                "payload_headroom": 100,
                "outfit_used": raw_packet["wardrobe_outfit_id"],
                "environment_used": raw_packet["environment_id"],
                "priority_score": 1,
                "proof_lane_locked": False,
                "why": ["production selector provenance test"],
            }
        ],
    }
    _write_json(learning_path, learning)
    _write_json(recommendation_path, recommendation)
    _write_json(queue_path, queue)
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    reconciliation = {
        "report_type": "lena_generation_reconciliation",
        "schema_version": "lena_generation_reconciliation_v1",
        "date": date_str,
        "generated_at": "2026-07-21T00:00:00+00:00",
        "source_revision": artifact["authority_commit"][:8],
        "source_revision_commit": artifact["authority_commit"],
        "source_artifacts": {
            "learning": {
                "source_artifact_path": learning_path.relative_to(root).as_posix(),
                "source_artifact_sha256": hashlib.sha256(learning_path.read_bytes()).hexdigest(),
            },
            "recommendation": {
                "source_artifact_path": recommendation_path.relative_to(root).as_posix(),
                "source_artifact_sha256": hashlib.sha256(recommendation_path.read_bytes()).hexdigest(),
            },
            "selected_candidate": {
                "source_artifact_path": candidate_repo_path,
                "source_artifact_sha256": candidate_sha,
            },
        },
        "learning_status": "current",
        "recommendation_recipe_id": candidate["recipe_id"],
        "recommendation_outfit_id": raw_packet["wardrobe_outfit_id"],
        "recommendation_environment_id": raw_packet["environment_id"],
        "recommendation_action_type": "collect_first_controlled_proof",
        "selected_candidate_id": candidate["candidate_id"],
        "selected_candidate_recipe_id": candidate["recipe_id"],
        "selected_candidate_slot_id": candidate["slot_id"],
        "selected_candidate_hook_id": candidate["hook_id"],
        "selected_candidate_prompt_sha256": candidate["prompt_sha256"],
        "divergence_status": "aligned",
        "resolution_policy": "selected_candidate_authoritative",
        "reconciliation_status": "reconciled",
        "operator_review_required": False,
        "final_reconciled_candidate_id": candidate["candidate_id"],
        "final_reconciled_candidate_recipe_id": candidate["recipe_id"],
        "final_reconciled_candidate_slot_id": candidate["slot_id"],
        "final_reconciled_candidate_hook_id": candidate["hook_id"],
        "final_reconciled_candidate_prompt_sha256": candidate["prompt_sha256"],
        "final_reconciled_candidate_artifact_path": candidate_repo_path,
        "final_reconciled_candidate_artifact_sha256": candidate_sha,
        "exact_next_allowed_action": "build_next_live_image_handoff",
        "next_allowed_action": {"status": "reconciled", "action": "build_next_live_image_handoff"},
        "dirty_workspace_dependency": False,
        "shadow_mode_only": True,
        "provider_call_performed": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "queue_mutated": False,
        "publish_performed": False,
        "blocking_reasons": [],
    }
    _write_json(reconciliation_path, reconciliation)
    monkeypatch.setattr(handoff_builder, "ROOT", root)
    monkeypatch.setattr(handoff_builder, "NEXT_ACTIONS", root / "pipeline/strategy/lena/next_actions")
    monkeypatch.setattr(handoff_builder, "CONTENT_PACKETS", root / "pipeline/strategy/lena/content_packets")
    monkeypatch.setattr(handoff_builder, "PRE_GENERATION_CANDIDATES", root / "pipeline/strategy/lena/pre_generation_candidates")
    monkeypatch.setattr(reconciliation_contract, "ROOT", root)
    handoff = handoff_builder.build_handoff(
        date_str,
        reconciliation_path.relative_to(root).as_posix(),
    )
    handoff_path, _ = handoff_builder.save_handoff(handoff, date_str)
    monkeypatch.setattr(generation_approval, "ROOT", root)
    handoff_facts = generation_approval.inspect_handoff_artifact(handoff_path)
    assert handoff_facts["pose_provenance"] == binding

    monkeypatch.setattr(executor, "ROOT", root)
    validated_handoff, source, _, _ = executor._validate_handoff_packet(handoff_path)
    assert validated_handoff == handoff
    assert source["image"]["image_prompt"] == bound_packet["compact_provider_prompt_preview"]
    manifest = executor.build_manifest(
        date_str,
        candidate["slot_id"],
        source,
        executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID,
        {
            "job_id": "job-pose-chain",
            "status": "completed",
            "result_urls": [],
            "saved_image_path": str(root / "generated.png"),
            "image_format_detected": ".png",
        },
    )
    monkeypatch.setattr(disposition, "ROOT", root)
    monkeypatch.setattr(disposition, "POSE_BANK_PATH", root / pose_provenance.POSE_AUTHORITY_REPO_PATH)
    monkeypatch.setattr(disposition, "EXPRESSION_BANK_PATH", root / pose_provenance.EXPRESSION_AUTHORITY_REPO_PATH)
    monkeypatch.setattr(
        disposition,
        "WARDROBE_CATALOG_PATH",
        root / "pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json",
    )
    monkeypatch.setattr(
        disposition,
        "RECIPE_BANK_PATH",
        root / "pipeline/prompt_banks/lena/lena_high_caliber_prompt_recipe_bank_v1.json",
    )
    monkeypatch.setattr(disposition, "PROMPT_BRAIN_PATH", root / pose_provenance.EXPRESSION_DERIVATION_REPO_PATH)
    return {
        "root": root,
        "candidate_path": candidate_path,
        "candidate": candidate,
        "decision": artifact,
        "binding": binding,
        "expression_binding": expression_binding,
        "packet": bound_packet,
        "handoff": handoff,
        "executor_source": source,
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


def test_production_selector_rejects_resealed_alternate_valid_pose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, candidate_path, artifact = _seed_production_selector_repo(tmp_path)
    binding = pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    expression_binding = pose_provenance.build_candidate_expression_provenance(
        candidate_path,
        root=root,
    )
    authority = json.loads(
        (root / pose_provenance.POSE_AUTHORITY_REPO_PATH).read_text(encoding="utf-8")
    )
    alternate = next(
        entry
        for entry in authority["combos"]
        if entry["pose_body_language_id"] != binding["pose_body_language_id"]
    )
    tampered = json.loads(json.dumps(artifact))
    tampered["candidate"]["pose_body_language_id"] = alternate["pose_body_language_id"]
    tampered["candidate"]["pose"] = alternate["label"]
    _write_json(candidate_path, _seal_candidate(tampered))

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_pose_provenance(candidate_path, root=root)
    assert excinfo.value.code == "stale_decision"

    packet = _raw_packet_for_candidate(
        artifact["candidate"],
        artifact["as_of_date"],
        "resealed candidate rejection test",
    )
    packet_path = root / "packet.json"
    bound_packet = packet_builder.rebuild_packet_from_authoritative_sources(
        packet,
        pose_binding=binding,
        expression_binding=expression_binding,
    )
    _write_json(packet_path, bound_packet)
    monkeypatch.setattr(executor, "ROOT", root)
    with pytest.raises(executor.HandoffArtifactError) as executor_exc:
        executor._rebuild_packet_prompt_source(
            packet_path,
            artifact["candidate"]["slot_id"],
            candidate_path,
            expected_pose_provenance=binding,
            expected_expression_provenance=expression_binding,
        )
    assert executor_exc.value.code == "handoff_pose_provenance_mismatch"

    recommendation = {
        "learning_status": "current",
        "learning_published_post_count": 1,
        "learning_pending_metrics_count": 0,
        "learning_stale_pending_metrics_count": 0,
        "learning_resolution_state_summary": {"learning_status": "current"},
        "learning_required_follow_up_action": "no_follow_up_required",
        "recommendation": {"recommended_recipe_id": artifact["candidate"]["recipe_id"]},
    }
    learning = {
        "published_post_count": 1,
        "pending_metrics_posts": [],
        "stale_pending_metrics_posts": [],
        "metrics_resolution_summary": {"learning_status": "current"},
    }
    queue = {
        "proof_lane_lock_active": False,
        "queue_slots": [
            {
                "recipe_id": artifact["candidate"]["recipe_id"],
                "environment_used": packet["environment_id"],
                "outfit_used": packet["wardrobe_outfit_id"],
            }
        ],
    }
    monkeypatch.setattr(handoff_builder, "ROOT", root)
    monkeypatch.setattr(handoff_builder, "load_report", lambda *args, **kwargs: recommendation)
    monkeypatch.setattr(handoff_builder, "load_learning_report", lambda *args, **kwargs: (root / "learning.json", learning))
    monkeypatch.setattr(handoff_builder, "load_queue_report", lambda *args, **kwargs: (root / "queue.json", queue))
    monkeypatch.setattr(
        handoff_builder,
        "load_reconciled_selected_candidate_report",
        lambda *args, **kwargs: (candidate_path, tampered),
    )
    monkeypatch.setattr(handoff_builder, "content_packet_path", lambda *args, **kwargs: packet_path)
    monkeypatch.setattr(handoff_builder, "load_content_packet_report", lambda *args, **kwargs: bound_packet)
    monkeypatch.setattr(
        handoff_builder.reconciliation_contract,
        "build_handoff_reconciliation_provenance",
        lambda **kwargs: {
            "final_candidate": {
                "recipe_id": artifact["candidate"]["recipe_id"],
                "slot_id": artifact["candidate"]["slot_id"],
            }
        },
    )
    with pytest.raises(handoff_builder.HandoffBuildError, match="stale_decision"):
        handoff_builder.build_handoff(artifact["as_of_date"], "reconciliation.json")


def test_production_selector_rejects_resealed_alternate_valid_expression(tmp_path: Path) -> None:
    root, candidate_path, artifact = _seed_production_selector_repo(tmp_path)
    binding = pose_provenance.build_candidate_expression_provenance(candidate_path, root=root)
    authority = json.loads(
        (root / pose_provenance.EXPRESSION_AUTHORITY_REPO_PATH).read_text(encoding="utf-8")
    )
    alternate = next(
        entry
        for entry in authority["combos"]
        if entry["expression_gaze_id"] != binding["expression_gaze_id"]
    )
    tampered = json.loads(json.dumps(artifact))
    tampered["candidate"].update(
        {
            "expression_gaze_id": alternate["expression_gaze_id"],
            "expression_gaze_label": alternate["label"],
            "expression_canonical_text": alternate["text"],
            "expression_text": alternate["text"],
            "expression_safe_fallback_used": False,
            "expression_safe_fallback_reason": None,
            "expression_scene_conflict_terms": [],
        }
    )
    _write_json(candidate_path, _seal_candidate(tampered))

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_expression_provenance(candidate_path, root=root)
    assert excinfo.value.code == "stale_decision"


def test_candidate_expression_authority_rejects_worktree_bank_drift(tmp_path: Path) -> None:
    root, candidate_path, _ = _seed_production_selector_repo(tmp_path)
    binding = pose_provenance.build_candidate_expression_provenance(candidate_path, root=root)
    assert binding["expression_gaze_id"]
    bank_path = root / pose_provenance.EXPRESSION_AUTHORITY_REPO_PATH
    bank_path.write_text(bank_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.build_candidate_expression_provenance(candidate_path, root=root)
    assert excinfo.value.code in {
        "pose_authority_worktree_drift",
        "expression_authority_worktree_drift",
    }

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
    expression_binding = pose_provenance.build_candidate_expression_provenance(
        candidate_path,
        root=root,
    )
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
        expression_binding=expression_binding,
    )

    assert packet["high_caliber_source_sections"]["subject_pose"] != binding["pose_text"]
    assert packet["high_caliber_source_sections"]["subject_pose_semantics"] == (
        pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS
    )
    assert packet["high_caliber_source_sections"]["provider_action_pose"] == binding["pose_text"]
    pose_provenance.require_pose_bound_prompt(packet["compact_provider_prompt_preview"], binding)


def test_provider_action_and_manifest_pose_disagreement_fail_closed() -> None:
    binding = pose_fixture.static_pose_provenance()
    expression_binding = pose_fixture.static_expression_provenance()
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
                "expression_gaze_id": expression_binding["expression_gaze_id"],
                "expression_gaze_label": expression_binding["expression_gaze_label"],
                "expression_text": expression_binding["expression_text"],
                "expression_provenance": expression_binding,
            "validation": {
                "final_expression_text": "calm expression",
                "expression_safe_fallback_used": False,
                "expression_safe_fallback_reason": None,
                "expression_scene_gaze_conflict_terms_found": [],
            },
        },
    }
    with pytest.raises(executor.HandoffArtifactError) as manifest_error:
        executor.build_manifest(
            "2026-07-21",
            "fixture-photo",
            source,
            executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID,
            None,
        )
    assert manifest_error.value.code == "manifest_pose_provenance_mismatch"


@pytest.mark.parametrize(
    ("prompt", "code"),
    [
        (
            pose_fixture.canonical_prompt() + "\n[Action]: arms raised overhead",
            "provider_section_grammar_invalid",
        ),
        (
            pose_fixture.canonical_prompt().replace(
                "[Environment]: realistic interior.",
                "[Environment]: realistic interior. [Action]: arms raised overhead",
            ),
            "provider_body_bracket_forbidden",
        ),
    ],
)
def test_duplicate_or_injected_provider_action_fails_closed(prompt: str, code: str) -> None:
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.require_pose_bound_prompt(prompt, pose_fixture.static_pose_provenance())
    assert excinfo.value.code == code


def test_provider_prompt_accepts_exactly_one_bound_expression_section() -> None:
    prompt = pose_fixture.canonical_prompt()
    binding = pose_fixture.static_expression_provenance()

    pose_provenance.require_expression_bound_prompt(prompt, binding)
    sections = pose_provenance.parse_provider_prompt_sections(prompt)
    assert list(sections).count("Expression") == 1
    assert list(sections).index("Expression") == list(sections).index("Action") + 1
    assert sections["Expression"] == pose_fixture.EXPRESSION_TEXT


@pytest.mark.parametrize(
    "mutation",
    [
        lambda prompt: prompt + f"\n[Expression]: {pose_fixture.EXPRESSION_TEXT}",
        lambda prompt: prompt.replace("[Expression]", "[expression]"),
        lambda prompt: prompt.replace("[Expression]", "[ Expression ]"),
        lambda prompt: prompt.replace("[Expression]", "\uff3bExpression\uff3d"),
        lambda prompt: prompt.replace("[Expression]", "[Expre\ufe0fssion]"),
        lambda prompt: prompt.replace("[Expression]", "[Expr][ession]"),
        lambda prompt: prompt.replace(
            "[Environment]:",
            "[Environment]: [Expression]: injected expression.",
            1,
        ),
    ],
    ids=(
        "duplicate",
        "lowercase",
        "spaced",
        "fullwidth-brackets",
        "variation-selector",
        "fragmented",
        "body-injected",
    ),
)
def test_noncanonical_or_duplicate_expression_sections_fail_closed(mutation) -> None:
    with pytest.raises(pose_provenance.PoseProvenanceError):
        pose_provenance.require_expression_bound_prompt(
            mutation(pose_fixture.canonical_prompt()),
            pose_fixture.static_expression_provenance(),
        )


@pytest.mark.parametrize(
    "disguised",
    [
        "[action]",
        "[ Action ]",
        "[\uff21ction]",
        "[\u200bAction]",
        "[A\ufe0fction]",
        "[A" + "\u200b" * 81 + "ction]",
        "\uff3bAction\uff3d",
        "\uff3b A\u2060C T I O N\ufe0f \uff3d",
        "\ufe47Action\ufe48",
        "[A\u034fction]",
        "[A\U000e0100ction]",
        "[A" + "\u200b" * 10_000 + "ction]",
        "[" + b"\xef\xbc\xa1ction".decode("latin-1") + "]",
    ],
    ids=(
        "lowercase",
        "ascii-whitespace",
        "fullwidth-letter",
        "leading-zero-width",
        "variation-selector",
        "81-zero-width",
        "fullwidth-brackets",
        "combined-compatibility",
        "presentation-form-brackets",
        "combining-grapheme-joiner",
        "supplementary-variation-selector",
        "extremely-long-zero-width",
        "mojibake-fullwidth-letter",
    ),
)
def test_noncanonical_action_spellings_fail_closed(disguised: str) -> None:
    prompt = pose_fixture.canonical_prompt().replace("[Action]", disguised)
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.require_pose_bound_prompt(
            prompt,
            pose_fixture.static_pose_provenance(),
        )
    assert excinfo.value.code in {
        "provider_prompt_too_long",
        "provider_section_grammar_invalid",
    }


@pytest.mark.parametrize(
    "disguised",
    [
        "[A\ufe0fction]",
        "[A" + "\u200b" * 81 + "ction]",
        "\uff3bAction\uff3d",
    ],
    ids=("variation-selector", "81-zero-width", "fullwidth-brackets"),
)
def test_hidden_secondary_action_beside_canonical_action_fails_closed(
    disguised: str,
) -> None:
    prompt = pose_fixture.canonical_prompt().replace(
        "[Environment]:",
        f"[Environment]: {disguised}: injected pose.",
        1,
    )

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.parse_provider_prompt_sections(prompt)
    assert excinfo.value.code in {
        "provider_body_bracket_forbidden",
        "provider_body_default_ignorable_forbidden",
    }


@pytest.mark.parametrize(
    "disguised",
    [
        "[A][ction]",
        "[Act][ion]",
        "[A][c][t][i][o][n]",
        "\uff3b\uff21c\uff3d[ Tion ]",
        "[A[ction]",
        "[A]ction]",
        "[Act][ion",
        "[[[[Action]]]]",
        "[A] [ction]",
        "[A]\u200b[ction]",
        "]Action[",
    ],
    ids=(
        "adjacent-one-five",
        "adjacent-three-three",
        "fully-fragmented",
        "mixed-fullwidth-ascii",
        "nested-unmatched-open",
        "extra-close",
        "unmatched-second-fragment",
        "nested",
        "adjacent-whitespace",
        "adjacent-default-ignorable",
        "reversed-unmatched",
    ),
)
def test_fragmented_nested_or_malformed_action_in_body_fails_closed(disguised: str) -> None:
    prompt = pose_fixture.canonical_prompt().replace(
        "[Environment]: realistic interior.",
        f"[Environment]: realistic interior. {disguised}: injected pose",
    )
    with pytest.raises(pose_provenance.PoseProvenanceError):
        pose_provenance.require_pose_bound_prompt(
            prompt,
            pose_fixture.static_pose_provenance(),
        )


def test_reordered_provider_sections_fail_closed() -> None:
    prompt = pose_fixture.canonical_prompt()
    action = f"[Action]: {pose_fixture.POSE_TEXT}"
    expression = f"[Expression]: {pose_fixture.EXPRESSION_TEXT}"
    prompt = prompt.replace(f"{action}\n{expression}", f"{expression}\n{action}")

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.require_pose_bound_prompt(
            prompt,
            pose_fixture.static_pose_provenance(),
        )
    assert excinfo.value.code == "provider_section_grammar_invalid"


@pytest.mark.parametrize(
    "section",
    ["Subject", "Environment", "Cinematography", "Lighting/Style", "Technical"],
)
def test_reserved_action_in_any_provider_body_fails_closed(section: str) -> None:
    marker = f"[{section}]:"
    prompt = pose_fixture.canonical_prompt().replace(
        marker,
        f"{marker} [Action]: injected pose.",
        1,
    )
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.require_pose_bound_prompt(
            prompt,
            pose_fixture.static_pose_provenance(),
        )
    assert excinfo.value.code == "provider_body_bracket_forbidden"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_canonical_provider_sections_accept_lf_and_crlf(newline: str) -> None:
    prompt = pose_fixture.canonical_prompt().replace("\n", newline)
    pose_provenance.require_pose_bound_prompt(
        prompt,
        pose_fixture.static_pose_provenance(),
    )


@pytest.mark.parametrize(
    "disguised",
    [
        "[Action]",
        "[A\ufe0fction]",
        "[A" + "\u200b" * 81 + "ction]",
        "\uff3bAction\uff3d",
        "\uff3b a\u2060 c t i o n\ufe0f \uff3d",
    ],
)
def test_recipe_derived_reserved_section_token_fails_closed(disguised: str) -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    recipe["setting_background"] = f"realistic room {disguised}: arms raised overhead"

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(
            recipe,
            pose_binding=pose_fixture.static_pose_provenance(),
            expression_binding=pose_fixture.static_expression_provenance(),
        )
    assert excinfo.value.code in {
        "provider_body_bracket_forbidden",
        "provider_body_default_ignorable_forbidden",
    }


def test_unbound_recipe_subject_pose_reserved_section_fails_closed() -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    recipe["subject_pose"] = "canonical pose [A\ufe0fction]: injected pose"

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(recipe)
    assert excinfo.value.code == "provider_body_default_ignorable_forbidden"


@pytest.mark.parametrize("field", tuple(packet_builder.PROVIDER_RECIPE_FIELD_LIMITS))
def test_every_recipe_derived_provider_body_rejects_fragmented_headers(field: str) -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    value = "plain text [A][ction]: injected pose"
    if field == "environment_realism_notes":
        recipe["scene_logic_contract"] = dict(recipe.get("scene_logic_contract") or {})
        recipe["scene_logic_contract"][field] = value
    else:
        recipe[field] = value

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(
            recipe,
            pose_binding=pose_fixture.static_pose_provenance(),
            expression_binding=pose_fixture.static_expression_provenance(),
        )
    assert excinfo.value.code == "provider_body_bracket_forbidden"


@pytest.mark.parametrize("field", tuple(packet_builder.PROVIDER_RECIPE_FIELD_LIMITS))
@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "left\u2028middle\u2029right"])
def test_every_recipe_provider_body_rejects_unicode_line_separators(
    field: str,
    separator: str,
) -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    value = f"ordinary text {separator} ordinary text"
    if field == "environment_realism_notes":
        recipe["scene_logic_contract"] = dict(recipe.get("scene_logic_contract") or {})
        recipe["scene_logic_contract"][field] = value
    else:
        recipe[field] = value

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(
            recipe,
            pose_binding=pose_fixture.static_pose_provenance(),
            expression_binding=pose_fixture.static_expression_provenance(),
        )
    assert excinfo.value.code == "provider_body_line_separator_forbidden"


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u2028middle\u2029"])
def test_first_generation_and_retry_reconstruction_reject_line_separators(
    separator: str,
) -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    recipe["setting_background"] = f"left{separator}right"
    with pytest.raises(pose_provenance.PoseProvenanceError) as first_generation:
        packet_builder.build_structured_provider_prompt(
            recipe,
            pose_binding=pose_fixture.static_pose_provenance(),
            expression_binding=pose_fixture.static_expression_provenance(),
        )
    assert first_generation.value.code == "provider_body_line_separator_forbidden"

    unsafe_prompt = pose_fixture.canonical_prompt().replace(
        "[Environment]: realistic interior.",
        f"[Environment]: realistic{separator}interior.",
    )
    with pytest.raises(retry_handoff.RetryHandoffError) as ordinary_retry:
        retry_handoff._replace_sections(unsafe_prompt)
    assert ordinary_retry.value.code == "provider_body_line_separator_forbidden"

    with pytest.raises(retry_handoff.RetryHandoffError) as hair_retry:
        retry_handoff._build_hair_crown_retry_prompt(unsafe_prompt, 4096)
    assert hair_retry.value.code == "provider_body_line_separator_forbidden"

    with pytest.raises(legacy_retry.RetryDecisionError) as legacy_retry_error:
        legacy_retry._mutate_prompt_for_retry(unsafe_prompt)
    assert legacy_retry_error.value.code == "provider_body_line_separator_forbidden"


@pytest.mark.parametrize(
    "value",
    [" leading", "trailing ", "two  spaces", "nonbreaking\u00a0space", "em\u2003space"],
)
def test_provider_body_rejects_whitespace_that_construction_would_rewrite(value: str) -> None:
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.validate_provider_body_text(
            value,
            label="fixture body",
            max_chars=100,
        )
    assert excinfo.value.code == "provider_body_whitespace_noncanonical"


def test_over_limit_recipe_body_rejects_before_unicode_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    limit = packet_builder.PROVIDER_RECIPE_FIELD_LIMITS["setting_background"]
    recipe["setting_background"] = "[" * (limit + 1)
    monkeypatch.setattr(
        pose_provenance,
        "_normalize_provider_body_for_detection",
        lambda *args, **kwargs: pytest.fail("over-limit body reached Unicode normalization"),
    )

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(recipe)
    assert excinfo.value.code == "provider_body_too_long"


def test_aggregate_recipe_body_limit_rejects_before_unicode_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    for field, limit in packet_builder.PROVIDER_RECIPE_FIELD_LIMITS.items():
        if field == "environment_realism_notes":
            recipe["scene_logic_contract"] = dict(recipe.get("scene_logic_contract") or {})
            recipe["scene_logic_contract"][field] = "x" * limit
        else:
            recipe[field] = "x" * limit
    monkeypatch.setattr(
        pose_provenance,
        "_normalize_provider_body_for_detection",
        lambda *args, **kwargs: pytest.fail("over-limit aggregate reached Unicode normalization"),
    )

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        packet_builder.build_structured_prompt_sections(recipe)
    assert excinfo.value.code == "provider_body_aggregate_too_long"


def test_nested_prompt_validation_normalizes_each_body_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = "[" * 700 + "Action" + "]" * 700
    prompt = pose_fixture.canonical_prompt().replace(
        "[Environment]: realistic interior.",
        f"[Environment]: realistic interior. {nested}",
    )
    original_normalize = pose_provenance._normalize_provider_body_for_detection
    normalized_lengths: list[int] = []

    def counted_normalize(value: str) -> str:
        normalized_lengths.append(len(value))
        return original_normalize(value)

    monkeypatch.setattr(pose_provenance, "_normalize_provider_body_for_detection", counted_normalize)

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.parse_provider_prompt_sections(prompt)
    assert excinfo.value.code == "provider_body_bracket_forbidden"
    assert len(normalized_lengths) <= len(pose_provenance.PROVIDER_SECTION_ORDER)
    assert sum(normalized_lengths) <= len(prompt)


def test_extremely_long_nested_prompt_rejects_before_body_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = pose_fixture.canonical_prompt() + "[" * 10_000 + "]" * 10_000
    monkeypatch.setattr(
        pose_provenance,
        "_normalize_provider_body_for_detection",
        lambda *args, **kwargs: pytest.fail("over-limit prompt reached body normalization"),
    )

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.parse_provider_prompt_sections(prompt)
    assert excinfo.value.code == "provider_prompt_too_long"


def test_over_limit_prompt_checks_length_before_any_scan_or_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class InstrumentedPrompt(str):
        def __len__(self) -> int:
            events.append("len")
            return super().__len__()

        def strip(self, *args, **kwargs):
            events.append("strip")
            return super().strip(*args, **kwargs)

        def replace(self, *args, **kwargs):
            events.append("replace")
            return super().replace(*args, **kwargs)

        def split(self, *args, **kwargs):
            events.append("split")
            return super().split(*args, **kwargs)

    monkeypatch.setattr(
        pose_provenance,
        "_normalize_provider_body_for_detection",
        lambda *args, **kwargs: pytest.fail("over-limit prompt reached normalization"),
    )
    prompt = InstrumentedPrompt(" " * (pose_provenance.PROVIDER_PROMPT_MAX_CHARS + 904))

    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.parse_provider_prompt_sections(prompt)
    assert excinfo.value.code == "provider_prompt_too_long"
    assert events == ["len"]


@pytest.mark.parametrize(
    "prompt",
    [
        " " * (pose_provenance.PROVIDER_PROMPT_MAX_CHARS + 1),
        "[" * (pose_provenance.PROVIDER_PROMPT_MAX_CHARS + 1),
        "\ufdfa" * (pose_provenance.PROVIDER_PROMPT_MAX_CHARS + 1),
    ],
    ids=("whitespace", "malformed", "nfkc-expanding"),
)
def test_all_over_limit_prompt_shapes_reject_before_normalization(
    prompt: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pose_provenance,
        "_normalize_provider_body_for_detection",
        lambda *args, **kwargs: pytest.fail("over-limit prompt reached normalization"),
    )
    with pytest.raises(pose_provenance.PoseProvenanceError) as excinfo:
        pose_provenance.parse_provider_prompt_sections(prompt)
    assert excinfo.value.code == "provider_prompt_too_long"


def test_exact_prompt_limit_and_bounded_whitespace_follow_normal_validation() -> None:
    exactly_at_limit = "x" * pose_provenance.PROVIDER_PROMPT_MAX_CHARS
    with pytest.raises(pose_provenance.PoseProvenanceError) as malformed:
        pose_provenance.parse_provider_prompt_sections(exactly_at_limit)
    assert malformed.value.code == "provider_section_grammar_invalid"

    bounded_whitespace = " " * pose_provenance.PROVIDER_PROMPT_MAX_CHARS
    with pytest.raises(pose_provenance.PoseProvenanceError) as missing:
        pose_provenance.parse_provider_prompt_sections(bounded_whitespace)
    assert missing.value.code == "provider_prompt_missing"


def test_body_nfkc_is_detection_only() -> None:
    original = "Cafe\u0301 portrait"
    validated = pose_provenance.validate_provider_body_text(
        original,
        label="fixture body",
        max_chars=100,
    )
    assert validated == original
    prompt = pose_provenance.serialize_provider_prompt_sections([
        (label, validated if label == "Action" else "canonical body")
        for label in pose_provenance.PROVIDER_SECTION_ORDER
    ])
    assert f"[Action]: {original}" in prompt
    assert pose_provenance.parse_provider_prompt_sections(prompt)["Action"] == original


def test_recipe_fields_reach_section_serialization_without_whitespace_rewrite() -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    recipe["scene_logic_contract"] = dict(recipe.get("scene_logic_contract") or {})
    expected = {
        "subject_pose": "Pose Cafe\u0301 exactly",
        "fashion_accessories": "Accessory Cafe\u0301 exactly",
        "setting_background": "Setting Cafe\u0301 exactly",
        "environment_realism_notes": "Realism Cafe\u0301 exactly",
        "technical_keywords": "Camera Cafe\u0301 exactly",
        "style_lighting": "Lighting Cafe\u0301 exactly",
        "negative_constraints": "Constraint Cafe\u0301 exactly",
    }
    for field, value in expected.items():
        if field == "environment_realism_notes":
            recipe["scene_logic_contract"][field] = value
        else:
            recipe[field] = value

    sections = packet_builder.build_structured_prompt_sections(recipe)
    assert all(packet_builder.clean_fragment(body) == body for _, body in sections)
    serialized = pose_provenance.serialize_provider_prompt_sections(sections)
    for value in expected.values():
        assert value in serialized


def test_governed_recipe_inputs_satisfy_plain_text_policy() -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipes = recipe_bank.get("recipes") or recipe_bank.get("prompt_recipes") or []
    for recipe in recipes:
        sections = packet_builder.build_structured_prompt_sections(
            dict(recipe),
            pose_binding=pose_fixture.static_pose_provenance(),
            expression_binding=pose_fixture.static_expression_provenance(),
        )
        assert all(packet_builder.clean_fragment(body) == body for _, body in sections)


def test_real_recipe_emits_one_exact_canonical_action() -> None:
    recipe_bank = packet_builder.load_json(packet_builder.RECIPE_BANK)
    recipe = dict(packet_builder.select_recipe(recipe_bank, "hcr_011"))
    prompt = packet_builder.build_structured_provider_prompt(
        recipe,
        pose_binding=pose_fixture.static_pose_provenance(),
        expression_binding=pose_fixture.static_expression_provenance(),
    )

    assert prompt.count("[Action]") == 1
    pose_provenance.require_pose_bound_prompt(
        prompt,
        pose_fixture.static_pose_provenance(),
    )


def test_conflicting_already_bound_content_packet_fails_closed() -> None:
    original = pose_fixture.static_pose_provenance()
    packet = pose_fixture.authoritatively_bind_packet(
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
        packet_builder.rebuild_packet_from_authoritative_sources(
            packet,
            pose_binding=conflicting,
            expression_binding=pose_fixture.static_expression_provenance(),
        )
    assert excinfo.value.code == "pose_bound_packet_conflict"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda packet: packet.update(compact_provider_prompt_sha256="f" * 64),
        lambda packet: packet.update(compact_provider_prompt_chars=0),
        lambda packet: packet.update(compact_provider_prompt_preview=packet["compact_provider_prompt_preview"].replace(pose_fixture.POSE_TEXT, "arms raised overhead")),
        lambda packet: packet.update(compact_provider_prompt_budget=1),
        lambda packet: packet["provider_prompt_contract"].update(prompt_chars=0),
        lambda packet: packet["provider_prompt_contract"].update(pose_binding_status="unbound"),
        lambda packet: packet["provider_prompt_contract"].update(pose_authority_source="wrong"),
        lambda packet: packet["generation_pose_contract"].update(status="unbound"),
        lambda packet: packet["high_caliber_source_sections"].update(provider_action_pose="arms raised overhead"),
        lambda packet: packet["high_caliber_source_sections"].update(subject_pose_semantics="authoritative"),
    ],
)
def test_every_retained_bound_packet_integrity_field_fails_on_conflict(mutation) -> None:
    binding = pose_fixture.static_pose_provenance()
    packet = pose_fixture.authoritatively_bind_packet(
        {
            "recipe_id": "hcr_011",
            "strong_hook_id": "mf_001",
            "generated_date": "2026-07-21",
            "wardrobe_outfit_id": "wc_p020",
            "environment_id": "env_v008",
            "hook_selection_reason": "bound packet integrity test",
        },
        pose_binding=binding,
    )
    mutation(packet)

    with pytest.raises(pose_provenance.PoseProvenanceError):
        packet_builder.rebuild_packet_from_authoritative_sources(
            packet,
            pose_binding=binding,
            expression_binding=pose_fixture.static_expression_provenance(),
        )


def test_production_selector_candidate_packet_handoff_executor_manifest_qa_chain(
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
    assert validated == {
        "pose_provenance": chain["binding"],
        "expression_provenance": chain["expression_binding"],
    }
    assert chain["manifest"]["pose_provenance"] == chain["binding"]
    assert chain["manifest"]["pose_bound_content_packet_sha256"] == (
        chain["handoff"]["pose_bound_content_packet_sha256"]
    )
    prompt = chain["packet"]["compact_provider_prompt_preview"]
    assert chain["handoff"]["structured_executor_inputs"]["selected_prompt_text"] == prompt
    assert chain["executor_source"]["image"]["image_prompt"] == prompt
    assert chain["manifest"]["image_prompt"] == prompt
    assert chain["manifest"]["prompt_sha256"] == hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()


def test_production_pose_and_expression_chain_advances_past_expression_qa(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _build_real_pose_chain(tmp_path, monkeypatch)
    disposition._validate_manifest_pose_contract(
        chain["manifest"],
        chain["decision"],
        chain["candidate"],
        "authorization_bound_handoff",
        chain["handoff"]["provider_execution_binding"],
    )
    chain["manifest"].pop("effective_wardrobe_silhouette_class", None)
    image_path = Path(chain["manifest"]["saved_image_path"])
    image_path.write_bytes(b"pose provenance QA fixture")
    manifest_path = chain["root"] / "generated_manifest.json"
    _write_json(manifest_path, chain["manifest"])

    with pytest.raises(disposition.BoundaryError) as excinfo:
        disposition._validate_manifest(
            manifest_path,
            chain["decision"],
            chain["candidate"],
            {"path": str(image_path), "format": "PNG"},
            "authorization_bound_handoff",
            provider_binding=chain["handoff"]["provider_execution_binding"],
        )
    assert excinfo.value.code == "provenance_mismatch"
    assert "expression" not in excinfo.value.detail.casefold()
    assert "effective_wardrobe_silhouette_class" in excinfo.value.detail


def test_production_pose_expression_and_wardrobe_manifest_passes_real_qa_ingestion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _build_real_pose_chain(tmp_path, monkeypatch)
    image_path = Path(chain["manifest"]["saved_image_path"])
    image_path.write_bytes(b"complete provenance QA fixture")
    manifest_path = chain["root"] / "generated_manifest_complete.json"
    _write_json(manifest_path, chain["manifest"])

    validated = disposition._validate_manifest(
        manifest_path,
        chain["decision"],
        chain["candidate"],
        {"path": str(image_path), "format": "PNG"},
        "authorization_bound_handoff",
        provider_binding=chain["handoff"]["provider_execution_binding"],
    )
    assert validated["effective_wardrobe_silhouette_class"] == chain["candidate"]["visual_style"]
    assert validated["pose_provenance"] == chain["binding"]
    assert validated["expression_provenance"] == chain["expression_binding"]


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
