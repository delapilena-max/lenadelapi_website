from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path

import pytest


builder = importlib.import_module("tools.strategy.lena_build_generation_reconciliation_v1")
canonical_assets = importlib.import_module("pipeline.influencer_nodes.lena.canonical_brain_assets")

DATE = "2026-07-15"
AUTHORITY_COMMIT = "d07fcbf37b1e383ae0c68694c4a1d2a0b921838d"
SOURCE_REVISION = AUTHORITY_COMMIT[:8]
RECOMMENDATION_RECIPE_ID = "hcr_011"
ALTERNATE_RECIPE_ID = "hcr_008"
SLOT_ID = f"lenagate{DATE.replace('-', '')}{SOURCE_REVISION}-pack000-04-photo"
CANDIDATE_ID = f"{SLOT_ID}::{RECOMMENDATION_RECIPE_ID}::cbn_004"
ALT_CANDIDATE_ID = f"{SLOT_ID}::{ALTERNATE_RECIPE_ID}::cbn_004"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(canonical_assets, "ROOT", tmp_path)
    monkeypatch.setattr(canonical_assets, "LENA_ROOT", tmp_path / "pipeline" / "influencer_nodes" / "lena")
    monkeypatch.setattr(canonical_assets, "PROMPT_BANK_ROOT", tmp_path / "pipeline" / "prompt_banks" / "lena")


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
    _write_text(
        identity_root / "lena_higgsfield_identity.py",
        "EXPECTED_JOB_TYPE = 'higgsfield_text2image'\nEXPECTED_SOUL_NAME = 'Lena'\nEXPECTED_SOUL_TYPE = 'Soul 2.0'\nAPPROVED_CUSTOM_REFERENCE_IDS = {'ref'}\n",
    )
    _write_json(identity_root / "lena_character_doctrine_v1.json", {"version": "v1"})
    _write_json(lena_root / "lena_content_strategy_v1.json", {"version": "v1"})
    _write_json(lena_root / "world_continuity_policy_v1.json", {"version": "v1"})
    _write_json(
        lena_root / "life_engine_realism_memory_policy_v1.json",
        {"version": "v1", "memory_path": "pipeline/state/lena_life_engine_realism_memory_v1.json"},
    )
    _write_json(lena_root / "engagement_selection_policy_v1.json", {"version": "v1"})
    _write_json(lena_root / "strategy_autonomy_gate_policy_v1.json", {"version": "v1"})
    _write_json(config_root / "lena_generation_policy.json", {"version": "v1"})
    _write_text(input_root / "prompt.txt", "Seed prompt\n")
    _write_json(prompt_bank_root / "placeholder.json", {"id": "placeholder"})
    _write_json(state_root / "lena_life_engine_realism_memory_v1.json", {"entries": []})
    _write_text(
        lena_root / "canonical_brain_assets.py",
        "# canonical brain asset manifest source file\n",
    )


def _learning_payload(*, status: str = "current", preferred_recipe_ids: list[str] | None = None) -> dict:
    preferred_recipe_ids = preferred_recipe_ids or [RECOMMENDATION_RECIPE_ID, ALTERNATE_RECIPE_ID]
    return {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "date": DATE,
        "generated_at": "2026-07-15T12:00:00+00:00",
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "status": "ok",
        "published_post_count": 3,
        "pending_metrics_posts": [],
        "stale_pending_metrics_posts": [],
        "winner_posts": [{"recipe_id": RECOMMENDATION_RECIPE_ID}],
        "queue_boosts": {"preferred_recipe_ids": preferred_recipe_ids},
        "metrics_resolution_summary": {
            "learning_status": status,
            "current_count": 1,
            "usable_but_incomplete_count": 0,
            "stale_unresolved_count": 0,
            "manual_or_future_capability_required_count": 0 if status == "current" else 1,
        },
        "learning_status": status,
        "learning_status_label": {
            "current": "learning_current",
            "usable_but_incomplete": "learning_degraded_incomplete",
            "stale_unresolved": "learning_stale_unresolved",
            "manual_or_future_capability_required": "learning_manual_or_future_capability_required",
        }.get(status, "learning_unavailable"),
        "learning_required_follow_up_action": {
            "current": "no_follow_up_required",
            "usable_but_incomplete": "complete_missing_metrics_or_refresh_learning",
            "stale_unresolved": "refresh_or_resolve_stale_unresolved_posts",
            "manual_or_future_capability_required": "manual_or_future_capability_resolution_required",
        }.get(status, "rebuild_and_pass_an_explicit_learning_artifact"),
    }


def _recommendation_payload(
    learning_path: Path,
    *,
    recipe_id: str = RECOMMENDATION_RECIPE_ID,
) -> dict:
    learning = _learning_payload()
    return {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "date": DATE,
        "learning_artifact_path": str(learning_path),
        "learning_status": learning["learning_status"],
        "learning_status_label": learning["learning_status_label"],
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_availability": "available",
        "learning_published_post_count": learning["published_post_count"],
        "learning_pending_metrics_count": len(learning["pending_metrics_posts"]),
        "learning_stale_pending_metrics_count": len(learning["stale_pending_metrics_posts"]),
        "learning_resolution_state_summary": learning["metrics_resolution_summary"],
        "learning_required_follow_up_action": learning["learning_required_follow_up_action"],
        "learning_winner_post_count": len(learning["winner_posts"]),
        "recommendation": {
            "action_type": "collect_first_controlled_proof",
            "recommended_recipe_id": recipe_id,
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "learning_signal_used": ["queue_boosts.preferred_recipe_ids", "winner_posts"],
            "next_live_gate": "review",
        },
    }


def _selected_candidate_payload(
    *,
    recipe_id: str = RECOMMENDATION_RECIPE_ID,
    candidate_id: str | None = None,
    selected: bool = True,
    include_body: bool = True,
) -> dict:
    slot_id = SLOT_ID
    candidate = {
        "candidate_id": candidate_id or f"{slot_id}::{recipe_id}::cbn_004",
        "slot_id": slot_id,
        "lane": "parking_garage_flash",
        "recipe_id": recipe_id,
        "hook_id": "cbn_004",
        "prompt_sha256": hashlib.sha256(b"shadow-mode prompt").hexdigest(),
        "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {slot_id}",
    }
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "influencer_id": "lena",
        "as_of_date": DATE,
        "authority_commit": AUTHORITY_COMMIT,
        "candidate_status": "selected" if selected else "abstain",
        "candidate": candidate if include_body else None,
        "decision_fingerprint_sha256": "5" * 64,
        "generated_at_utc": "2026-07-15T12:34:57Z",
        "provider_authorized": False,
        "side_effects_performed": [],
    }


def _fixture_tree(
    tmp_path: Path,
    *,
    recommendation_recipe_id: str = RECOMMENDATION_RECIPE_ID,
    selected_recipe_id: str = RECOMMENDATION_RECIPE_ID,
    selected_status: bool = True,
    include_candidate_body: bool = True,
    learning_status: str = "current",
) -> tuple[Path, Path, Path]:
    _materialize_canonical_assets(tmp_path)
    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE
    learning_path = next_actions / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = next_actions / f"lena_next_generation_step_{DATE}.json"
    selected_candidate_path = (
        tmp_path
        / "pipeline"
        / "strategy"
        / "lena"
        / "pre_generation_candidates"
        / DATE
        / "lena_pre_generation_candidate_d07fcbf3_53ba138728e8.json"
    )

    _write_json(learning_path, _learning_payload(status=learning_status))
    _write_json(recommendation_path, _recommendation_payload(learning_path, recipe_id=recommendation_recipe_id))
    _write_json(
        selected_candidate_path,
        _selected_candidate_payload(
            recipe_id=selected_recipe_id,
            selected=selected_status,
            include_body=include_candidate_body,
        ),
    )
    return learning_path, recommendation_path, selected_candidate_path


def _file_snapshot(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def test_builder_writes_reconciled_report_for_exact_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)
    before = _file_snapshot(tmp_path)

    report = builder.build_generation_reconciliation(
        DATE,
        str(learning_path),
        str(recommendation_path),
        str(selected_candidate_path),
    )
    output_path = builder.write_report(report, DATE)
    after = _file_snapshot(tmp_path)

    assert output_path == tmp_path / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE / f"lena_generation_reconciliation_{SOURCE_REVISION}_{report['reconciliation_fingerprint_sha256'][:12]}.json"
    assert report["report_type"] == "lena_generation_reconciliation"
    assert report["schema_version"] == "lena_generation_reconciliation_v1"
    assert report["date"] == DATE
    assert report["source_revision"] == SOURCE_REVISION
    assert report["source_revision_commit"] == AUTHORITY_COMMIT
    assert report["reconciliation_status"] == "reconciled"
    assert report["operator_review_required"] is False
    assert report["divergence_status"] == "aligned"
    assert report["resolution_policy"] == "selected_candidate_authoritative"
    assert report["final_reconciled_candidate_id"] == CANDIDATE_ID
    assert report["final_reconciled_candidate_recipe_id"] == RECOMMENDATION_RECIPE_ID
    assert report["exact_next_allowed_action"] == "build_next_live_image_handoff"
    assert report["next_allowed_action"]["action"] == "build_next_live_image_handoff"
    assert report["next_allowed_action"]["status"] == "reconciled"
    assert report["ranking_evidence"]["preferred_recipe_ids"] == [RECOMMENDATION_RECIPE_ID, ALTERNATE_RECIPE_ID]
    assert report["compatibility_evidence"]["recipe_match"] is True
    assert report["source_artifacts"]["canonical_brain_assets"]["canonical_brain_assets_status"] == "ready"
    assert report["source_artifacts"]["canonical_brain_assets"]["dirty_workspace_dependency"] is False
    assert report["source_artifacts"]["learning"]["source_artifact_path"].endswith(
        f"pipeline/strategy/lena/next_actions/{DATE}/lena_post_outcome_learning_state_{DATE}.json"
    )
    assert report["source_artifacts"]["recommendation"]["source_artifact_path"].endswith(
        f"pipeline/strategy/lena/next_actions/{DATE}/lena_next_generation_step_{DATE}.json"
    )
    assert report["source_artifacts"]["selected_candidate"]["source_artifact_path"].endswith(
        f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/lena_pre_generation_candidate_d07fcbf3_53ba138728e8.json"
    )
    assert len(report["source_artifacts"]["learning"]["source_artifact_sha256"]) == 64
    assert len(report["source_artifacts"]["recommendation"]["source_artifact_sha256"]) == 64
    assert len(report["source_artifacts"]["selected_candidate"]["source_artifact_sha256"]) == 64
    assert len(report["source_artifacts"]["canonical_brain_assets"]["source_artifact_sha256"]) == 64
    assert after - before == {
        Path("pipeline")
        / "strategy"
        / "lena"
        / "reconciliations"
        / DATE
        / f"lena_generation_reconciliation_{SOURCE_REVISION}_{report['reconciliation_fingerprint_sha256'][:12]}.json"
    }


def test_recipe_mismatch_requires_operator_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(
        tmp_path,
        recommendation_recipe_id=RECOMMENDATION_RECIPE_ID,
        selected_recipe_id=ALTERNATE_RECIPE_ID,
    )

    report = builder.build_generation_reconciliation(
        DATE,
        str(learning_path),
        str(recommendation_path),
        str(selected_candidate_path),
    )

    assert report["reconciliation_status"] == "operator_review_required"
    assert report["divergence_status"] == "recipe_mismatch"
    assert report["resolution_policy"] == "explicit_operator_reconciliation_required"
    assert report["operator_review_required"] is True
    assert report["final_reconciled_candidate_id"] is None
    assert report["exact_next_allowed_action"] == "create_operator_reconciliation_decision"
    assert report["next_allowed_action"]["action"] == "create_operator_reconciliation_decision"
    assert report["next_allowed_action"]["reason"] == "recommendation and selected candidate disagree on the recipe"
    assert report["blocking_reasons"] == ["recipe_mismatch"]
    assert report["compatibility_evidence"]["recipe_match"] is False
    assert report["compatibility_evidence"]["selected_candidate_recipe_id"] == ALTERNATE_RECIPE_ID


def test_report_loading_fails_closed_for_missing_learning_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)
    learning_path.unlink()

    with pytest.raises(builder.ReconciliationError) as excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )

    assert excinfo.value.code == "missing_required_input"


def test_report_loading_fails_closed_for_malformed_recommendation_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)
    recommendation_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(builder.ReconciliationError) as excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )

    assert excinfo.value.code == "malformed_json"


def test_report_loading_fails_closed_for_wrong_recommendation_schema_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
    recommendation["version"] = "v2"
    recommendation_path.write_text(json.dumps(recommendation, indent=2, ensure_ascii=True), encoding="utf-8")

    with pytest.raises(builder.ReconciliationError) as excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )

    assert excinfo.value.code == "wrong_schema_version"


def test_report_loading_fails_closed_for_missing_recommendation_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
    recommendation.pop("recommendation", None)
    recommendation_path.write_text(json.dumps(recommendation, indent=2, ensure_ascii=True), encoding="utf-8")

    with pytest.raises(builder.ReconciliationError) as excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )

    assert excinfo.value.code == "missing_required_field"


def test_report_loading_fails_for_wrong_date_and_candidate_body_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)

    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
    recommendation["date"] = "2026-07-14"
    recommendation_path.write_text(json.dumps(recommendation, indent=2, ensure_ascii=True), encoding="utf-8")
    with pytest.raises(builder.ReconciliationError) as wrong_date_excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )
    assert wrong_date_excinfo.value.code == "wrong_date"

    recommendation_path.write_text(
        json.dumps(_recommendation_payload(learning_path), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    selected_candidate = json.loads(selected_candidate_path.read_text(encoding="utf-8"))
    selected_candidate["candidate"] = None
    selected_candidate_path.write_text(json.dumps(selected_candidate, indent=2, ensure_ascii=True), encoding="utf-8")

    with pytest.raises(builder.ReconciliationError) as body_missing_excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )

    assert body_missing_excinfo.value.code == "candidate_body_missing"


def test_report_loading_fails_for_selected_candidate_status_and_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(
        tmp_path,
        selected_status=False,
    )

    with pytest.raises(builder.ReconciliationError) as status_excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )
    assert status_excinfo.value.code == "candidate_status_not_selected"

    outside_path = tmp_path.parent / "outside.json"
    outside_path.write_text("{}", encoding="utf-8")
    with pytest.raises(builder.ReconciliationError) as path_excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(outside_path),
            str(selected_candidate_path),
        )
    assert path_excinfo.value.code == "path_escape"


def test_sha256_computation_failure_is_reported_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    learning_path, recommendation_path, selected_candidate_path = _fixture_tree(tmp_path)

    def failing_read_bytes(path: Path) -> bytes:
        raise OSError("boom")

    monkeypatch.setattr(builder, "_read_bytes", failing_read_bytes)

    with pytest.raises(builder.ReconciliationError) as excinfo:
        builder.build_generation_reconciliation(
            DATE,
            str(learning_path),
            str(recommendation_path),
            str(selected_candidate_path),
        )

    assert excinfo.value.code == "sha256_computation_failed"


def test_builder_source_does_not_import_live_provider_or_publish_helpers() -> None:
    source = Path(builder.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
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
        "pipeline.higgsfield_lena_api_executor",
        "tools.lena_higgsfield_generation_approval_v1",
        "tools.lena_photo_qa_disposition_v1",
        "tools.strategy.lena_run_generated_asset_qa_v1",
        "pipeline.publisher",
        "pipeline.queue",
        "pipeline.approvals",
    }
    assert not imported_modules.intersection(blocked_modules)
    forbidden_tokens = {
        "run_live",
        "build_generation_approval_record",
        "write_generation_claim_atomic",
        "write_generation_execution_receipt_atomic",
        "publish_performed = True",
        "queue_mutated = True",
    }
    assert not any(token in source for token in forbidden_tokens)
