from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path

import pytest


builder = importlib.import_module("tools.strategy.lena_build_autonomous_generation_eligibility_shadow_v1")
canonical_assets = importlib.import_module("pipeline.influencer_nodes.lena.canonical_brain_assets")
autonomy_ladder = importlib.import_module("pipeline.influencer_nodes.lena.autonomy_ladder")

DATE = "2026-07-15"
RECIPE_ID = "hcr_011"
SLOT_ID = f"higgsfield-20260715-{RECIPE_ID}-photo"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(canonical_assets, "ROOT", tmp_path)
    monkeypatch.setattr(canonical_assets, "LENA_ROOT", tmp_path / "pipeline" / "influencer_nodes" / "lena")
    monkeypatch.setattr(canonical_assets, "PROMPT_BANK_ROOT", tmp_path / "pipeline" / "prompt_banks" / "lena")
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", tmp_path / "pipeline" / "influencer_nodes" / "lena" / "autonomy_ladder_v1.json")


def _materialize_canonical_assets(tmp_path: Path) -> None:
    root = tmp_path
    lena_root = root / "pipeline" / "influencer_nodes" / "lena"
    prompt_bank_root = root / "pipeline" / "prompt_banks" / "lena"
    state_root = root / "pipeline" / "state"
    input_root = root / "pipeline" / "input" / "dialogue"
    identity_root = root / "pipeline" / "identity"
    config_root = root / "pipeline" / "config"
    prompting_root = root / "pipeline" / "prompting"

    _write_text(prompting_root / "lena_prompt_brain.py", "PROMPT_BRAIN = True\n")
    _write_json(lena_root / "persona.json", {"persona": "Lena", "voice": "warm"})
    _write_text(identity_root / "lena_identity.py", "EXPECTED_WIDTH = 1024\nEXPECTED_HEIGHT = 1024\n")
    _write_text(identity_root / "lena_higgsfield_identity.py", "EXPECTED_JOB_TYPE = 'higgsfield_text2image'\nEXPECTED_SOUL_NAME = 'Lena'\nEXPECTED_SOUL_TYPE = 'Soul 2.0'\nAPPROVED_CUSTOM_REFERENCE_IDS = {'ref'}\n")
    _write_json(identity_root / "lena_character_doctrine_v1.json", {"version": "v1"})
    _write_json(lena_root / "lena_content_strategy_v1.json", {"version": "v1"})
    _write_json(lena_root / "world_continuity_policy_v1.json", {"version": "v1"})
    _write_json(lena_root / "life_engine_realism_memory_policy_v1.json", {"version": "v1", "memory_path": "pipeline/state/lena_life_engine_realism_memory_v1.json"})
    _write_json(lena_root / "engagement_selection_policy_v1.json", {"version": "v1"})
    _write_json(lena_root / "strategy_autonomy_gate_policy_v1.json", {"version": "v1"})
    _write_json(config_root / "lena_generation_policy.json", {"version": "v1"})
    _write_text(input_root / "prompt.txt", "Seed prompt\n")
    _write_json(prompt_bank_root / "placeholder.json", {"id": "placeholder"})
    _write_json(state_root / "lena_life_engine_realism_memory_v1.json", {"entries": []})
    _write_json(
        autonomy_ladder.CONTRACT_PATH,
        {
            "version": "v1.0.0",
            "schema_version": "lena_autonomy_ladder_v1",
            "node_name": "Lena",
            "node_role": "Node 1 of the autonomous media engine",
            "publish_freeze": {
                "active": True,
                "scope": "publish paths remain frozen while shadow eligibility matures",
                "frozen_surfaces": ["posting"],
            },
            "autonomy_rules": {
                "auto_approval_forbidden": True,
                "implicit_escalation_forbidden": True,
                "generation_approval_does_not_imply_posting_approval": True,
            },
            "levels": [
                {"level": 0, "name": "l0", "enabled": True, "status": "active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
                {"level": 1, "name": "l1", "enabled": True, "status": "active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
                {"level": 2, "name": "l2", "enabled": True, "status": "active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
                {"level": 3, "name": "l3", "enabled": False, "status": "frozen_real_mode", "future_placeholder": False, "disabled_by_publish_freeze": True, "disabled_reason": "publish_freeze_active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
                {"level": 4, "name": "l4", "enabled": False, "status": "future_only", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
                {"level": 5, "name": "l5", "enabled": False, "status": "future_only", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
            ],
        },
    )


def _strategy_prep_payload(
    date_str: str,
    recipe_id: str = RECIPE_ID,
    *,
    handoff_path: str | None = None,
) -> dict:
    return {
        "report_type": "lena_strategy_autonomy_prep",
        "version": "v1",
        "date": date_str,
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "recipe_ids": [recipe_id],
        "queue_limit": 6,
        "status": "completed",
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
        "summary": {
            "strategy_gate_blocked": False,
            "recommended_recipe_id": recipe_id,
            "queue_recipes": [recipe_id],
            "next_live_image_handoff_path": handoff_path
            or f"pipeline/strategy/lena/next_actions/{date_str}/lena_next_live_image_handoff_{date_str}.json",
            "broader_autonomous_generation_ready": True,
            "learning_status": "current",
        },
    }


def _next_step_payload(date_str: str, recipe_id: str = RECIPE_ID) -> dict:
    return {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": date_str,
        "learning_status": "current",
        "learning_required_follow_up_action": "no_follow_up_required",
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": recipe_id,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "next_live_gate": "review",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids"],
        },
    }


def _handoff_payload(date_str: str, recipe_id: str = RECIPE_ID, *, live_execution_authorized: bool = False) -> dict:
    slot_id = f"higgsfield-{date_str.replace('-', '')}-{recipe_id}-photo"
    return {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "date": date_str,
        "created_at": "2026-07-15T12:00:00+00:00",
        "execution_owner": "claude",
        "provider": "higgsfield",
        "executor_type": "higgsfield_cli",
        "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
        "selected_slot_id": slot_id,
        "selected_recipe_id": recipe_id,
        "packet_state": "packet_valid_for_claude_review",
        "dry_run_executor_contract_state": "ready",
        "live_execution_state": "blocked",
        "live_execution_authorized": live_execution_authorized,
        "generation_approval_required": True,
        "manual_operator_approval_required": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "publish_authorized": False,
        "manual_publish_review_required": True,
        "selected_prompt_input_artifact_path": f"pipeline/strategy/lena/next_actions/{date_str}/lena_next_live_image_handoff_{date_str}.json",
        "selected_prompt_input": {
            "prompt_sha256": hashlib.sha256(b"shadow-mode prompt").hexdigest(),
        },
        "structured_executor_inputs": {
            "provider": "higgsfield",
            "executor_type": "higgsfield_cli",
            "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
            "model": "text2image_soul_v2",
            "aspect_ratio": "9:16",
            "negative_prompt_enabled": False,
            "live_execution_authorized": live_execution_authorized,
            "date": date_str,
            "slot_id": slot_id,
            "handoff_artifact_path": f"pipeline/strategy/lena/next_actions/{date_str}/lena_next_live_image_handoff_{date_str}.json",
            "soul_metadata": {
                "name": "Lena",
                "type": "Soul 2.0",
                "custom_reference_id": "ref",
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_sha256": hashlib.sha256(b"shadow-mode prompt").hexdigest(),
            "generation_approval_required": True,
            "manual_operator_approval_required": True,
            "provider_call_performed": False,
            "generation_performed": False,
            "publish_authorized": False,
            "manual_publish_review_required": True,
        },
    }


def _build_fixture_tree(
    tmp_path: Path,
    *,
    include_strategy_prep: bool = True,
    include_next_step: bool = True,
    include_handoff: bool = True,
    canonical_missing_asset: str | None = None,
    live_execution_authorized: bool = False,
    strategy_prep_payload: dict | None = None,
) -> None:
    _materialize_canonical_assets(tmp_path)
    if canonical_missing_asset:
        target = {
            "prompt_brain": tmp_path / "pipeline" / "prompting" / "lena_prompt_brain.py",
            "persona": tmp_path / "pipeline" / "influencer_nodes" / "lena" / "persona.json",
            "identity": tmp_path / "pipeline" / "identity" / "lena_identity.py",
            "higgsfield_identity": tmp_path / "pipeline" / "identity" / "lena_higgsfield_identity.py",
            "content_strategy": tmp_path / "pipeline" / "influencer_nodes" / "lena" / "lena_content_strategy_v1.json",
            "world_continuity_policy": tmp_path / "pipeline" / "influencer_nodes" / "lena" / "world_continuity_policy_v1.json",
            "life_engine_realism_memory_policy": tmp_path / "pipeline" / "influencer_nodes" / "lena" / "life_engine_realism_memory_policy_v1.json",
            "engagement_selection_policy": tmp_path / "pipeline" / "influencer_nodes" / "lena" / "engagement_selection_policy_v1.json",
            "strategy_autonomy_gate_policy": tmp_path / "pipeline" / "influencer_nodes" / "lena" / "strategy_autonomy_gate_policy_v1.json",
            "generation_policy": tmp_path / "pipeline" / "config" / "lena_generation_policy.json",
            "dialogue_prompt": tmp_path / "pipeline" / "input" / "dialogue" / "prompt.txt",
            "prompt_banks_lena": tmp_path / "pipeline" / "prompt_banks" / "lena",
            "realism_memory_state": tmp_path / "pipeline" / "state" / "lena_life_engine_realism_memory_v1.json",
        }[canonical_missing_asset]
        if target.is_dir():
            for child in target.iterdir():
                if child.is_file():
                    child.unlink()
        elif target.exists():
            target.unlink()

    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    if include_strategy_prep:
        _write_json(
            next_actions / f"lena_strategy_autonomy_prep_{DATE}.json",
            strategy_prep_payload or _strategy_prep_payload(DATE),
        )
    if include_next_step:
        _write_json(next_actions / f"lena_next_generation_step_{DATE}.json", _next_step_payload(DATE))
    if include_handoff:
        _write_json(next_actions / f"lena_next_live_image_handoff_{DATE}.json", _handoff_payload(DATE, live_execution_authorized=live_execution_authorized))


def _file_snapshot(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def test_builder_creates_only_the_expected_shadow_report_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)
    before = _file_snapshot(tmp_path)

    report = builder.build_autonomous_generation_eligibility_shadow(DATE)
    path = builder.write_report(report, DATE)

    after = _file_snapshot(tmp_path)
    assert after - before == {Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_autonomous_generation_eligibility_shadow_{DATE}.json"}
    assert path == tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_autonomous_generation_eligibility_shadow_{DATE}.json"
    assert report["report_type"] == "lena_autonomous_generation_eligibility_shadow"
    assert report["eligibility_status"] == "autonomous_eligibility_passed"
    assert report["dirty_workspace_dependency"] is False
    assert report["shadow_mode_only"] is True
    assert report["provider_call_performed"] is False
    assert report["approval_consumed"] is False
    assert report["claims_written"] is False
    assert report["receipts_written"] is False
    assert report["queue_mutated"] is False
    assert report["publish_performed"] is False


def test_missing_inputs_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, include_strategy_prep=False, include_next_step=False, include_handoff=False)

    report = builder.build_autonomous_generation_eligibility_shadow(DATE)

    assert report["eligibility_status"] == "autonomous_eligibility_pending"
    assert "strategy_prep_consistent" in report["blocking_reasons"]
    assert "next_generation_step_consistent" in report["blocking_reasons"]
    assert "live_image_handoff_review_only" in report["blocking_reasons"]
    assert report["authority_state"]["provider_execution_frozen"] is True
    assert report["authority_state"]["publish_frozen"] is True
    assert report["next_allowed_action"]["action"] == "resolve_missing_eligibility_inputs"


def test_missing_canonical_assets_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path, canonical_missing_asset="prompt_brain")

    report = builder.build_autonomous_generation_eligibility_shadow(DATE)

    assert report["eligibility_status"] == "autonomous_eligibility_pending"
    assert "canonical_brain_manifest_ready" in report["blocking_reasons"]
    assert report["source_artifacts"]["canonical_brain_assets"]["missing_required_assets"] == ["prompt_brain"]
    assert report["next_allowed_action"]["action"] == "rebuild_missing_canonical_artifact"


def test_valid_mocked_inputs_pass_while_authority_remains_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(
        tmp_path,
        strategy_prep_payload=_strategy_prep_payload(
            DATE,
            handoff_path=str(
                tmp_path
                / "pipeline"
                / "strategy"
                / "lena"
                / "next_actions"
                / DATE
                / f"lena_next_live_image_handoff_{DATE}.json"
            ),
        ),
    )

    report = builder.build_autonomous_generation_eligibility_shadow(DATE)

    assert report["eligibility_status"] == "autonomous_eligibility_passed"
    assert report["blocking_reasons"] == []
    assert report["authority_state"]["manual_approval_pending"] is True
    assert report["authority_state"]["autonomous_eligibility_passed"] is True
    assert report["authority_state"]["autonomous_eligibility_pending"] is False
    assert report["authority_state"]["provider_execution_frozen"] is True
    assert report["authority_state"]["publish_frozen"] is True
    assert report["authority_state"]["live_execution_authorized"] is False
    assert report["authority_state"]["publish_authorized"] is False
    assert report["next_allowed_action"]["action"] == "await_explicit_provider_authorization"


def test_loader_and_builder_do_not_import_provider_publish_or_queue_helpers() -> None:
    builder_source = Path(builder.__file__).read_text(encoding="utf-8")
    tree = ast.parse(builder_source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    blocked_modules = {
        "tools.lena_higgsfield_generation_approval_v1",
        "tools.lena_photo_qa_disposition_v1",
        "pipeline.publisher",
        "pipeline.queue",
        "pipeline.approvals",
        "pipeline.qa",
    }
    assert not imported_modules.intersection(blocked_modules)

    forbidden_tokens = {
        "build_generation_approval_record",
        "build_generation_claim_record",
        "build_generation_execution_receipt_record",
        "write_generation_claim_atomic",
        "write_generation_execution_receipt_atomic",
        "provider_submission_may_have_occurred",
    }
    assert not any(token in builder_source for token in forbidden_tokens)


def test_source_artifacts_include_paths_and_hashes_where_possible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    _build_fixture_tree(tmp_path)

    report = builder.build_autonomous_generation_eligibility_shadow(DATE)
    source_artifacts = report["source_artifacts"]

    assert source_artifacts["strategy_prep"]["source_artifact_path"].endswith(f"lena_strategy_autonomy_prep_{DATE}.json")
    assert source_artifacts["next_generation_step"]["source_artifact_path"].endswith(f"lena_next_generation_step_{DATE}.json")
    assert source_artifacts["live_image_handoff"]["source_artifact_path"].endswith(f"lena_next_live_image_handoff_{DATE}.json")
    assert source_artifacts["canonical_brain_assets"]["dirty_workspace_dependency"] is False
    assert source_artifacts["canonical_brain_assets"]["canonical_brain_assets_status"] == "ready"
    assert len(source_artifacts["strategy_prep"]["source_artifact_sha256"]) == 64
    assert len(source_artifacts["next_generation_step"]["source_artifact_sha256"]) == 64
    assert len(source_artifacts["live_image_handoff"]["source_artifact_sha256"]) == 64
    assert len(source_artifacts["autonomy_ladder"]["source_artifact_sha256"]) == 64

