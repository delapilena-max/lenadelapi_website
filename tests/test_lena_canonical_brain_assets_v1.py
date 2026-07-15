from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path

import pytest


MODULE = importlib.import_module("pipeline.influencer_nodes.lena.canonical_brain_assets")
ROOT = Path(__file__).resolve().parents[1]


def test_all_required_canonical_assets_are_listed() -> None:
    report = MODULE.load_canonical_brain_assets()
    assets = {asset["asset_id"]: asset for asset in report["assets"]}

    assert report["dirty_workspace_dependency"] is False
    assert report["canonical_brain_assets_status"] == "ready"
    assert report["missing_required_assets"] == []

    assert set(assets) == {
        "prompt_brain",
        "persona",
        "identity",
        "higgsfield_identity",
        "content_strategy",
        "world_continuity_policy",
        "life_engine_realism_memory_policy",
        "engagement_selection_policy",
        "strategy_autonomy_gate_policy",
        "generation_policy",
        "dialogue_prompt",
        "prompt_banks_lena",
        "realism_memory_state",
    }

    for asset in assets.values():
        assert asset["required"] is True
        assert asset["category"]
        assert asset["path"]
        assert asset["exists"] is True


def test_hashes_are_computed_for_files_and_directory_assets_are_safe() -> None:
    report = MODULE.load_canonical_brain_assets()
    assets = {asset["asset_id"]: asset for asset in report["assets"]}

    prompt_brain = assets["prompt_brain"]
    assert prompt_brain["sha256"] == hashlib.sha256(
        (ROOT / prompt_brain["path"]).read_bytes()
    ).hexdigest()

    prompt_bank = assets["prompt_banks_lena"]
    assert prompt_bank["kind"] == "directory"
    assert prompt_bank["sha256"]
    assert len(prompt_bank["sha256"]) == 64


def test_missing_required_assets_fail_closed_without_touching_runtime_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "LENA_ROOT", tmp_path / "pipeline" / "influencer_nodes" / "lena")
    monkeypatch.setattr(MODULE, "PROMPT_BANK_ROOT", tmp_path / "pipeline" / "prompt_banks" / "lena")

    report = MODULE.load_canonical_brain_assets()

    assert report["canonical_brain_assets_status"] == "missing_required_assets"
    assert report["dirty_workspace_dependency"] is False
    assert report["missing_required_assets"]
    assert set(report["missing_required_assets"]) == {
        "prompt_brain",
        "persona",
        "identity",
        "higgsfield_identity",
        "content_strategy",
        "world_continuity_policy",
        "life_engine_realism_memory_policy",
        "engagement_selection_policy",
        "strategy_autonomy_gate_policy",
        "generation_policy",
        "dialogue_prompt",
        "prompt_banks_lena",
        "realism_memory_state",
    }


def test_loader_does_not_depend_on_dirty_workspace_or_execution_helpers() -> None:
    source = Path(MODULE.__file__).read_text(encoding="utf-8")
    assert "C:\\projects\\ai\\content_bot" not in source
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    )
    blocked_prefixes = ("tools.", "pipeline.publisher", "pipeline.queue", "pipeline.approvals")
    assert not any(
        module.startswith(prefix)
        for module in imported_modules
        for prefix in blocked_prefixes
    )

    summary = MODULE.canonical_brain_assets_summary()
    assert summary == {
        "canonical_brain_assets_status": "ready",
        "missing_required_assets": [],
        "dirty_workspace_dependency": False,
    }
