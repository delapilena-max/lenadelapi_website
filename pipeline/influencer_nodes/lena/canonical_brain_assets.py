from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[3]
LENA_ROOT = ROOT / "pipeline" / "influencer_nodes" / "lena"
PROMPT_BANK_ROOT = ROOT / "pipeline" / "prompt_banks" / "lena"


@dataclass(frozen=True)
class CanonicalBrainAsset:
    asset_id: str
    path: str
    exists: bool
    required: bool
    sha256: str | None
    category: str
    kind: str


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _directory_tree_sha256(path: Path, root: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_dir():
        raise NotADirectoryError(path)

    entries: list[str] = []
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = _relative_path(file_path, root)
        entries.append(f"{rel}\0{_sha256_file(file_path)}")
    return _sha256_bytes("\n".join(entries).encode("utf-8"))


def _build_asset(
    *,
    asset_id: str,
    path: Path,
    category: str,
    required: bool,
    kind: str = "file",
) -> CanonicalBrainAsset:
    exists = path.exists()
    sha256: str | None
    if not exists:
        sha256 = None
    elif kind == "directory":
        sha256 = _directory_tree_sha256(path, ROOT)
    else:
        sha256 = _sha256_file(path)
    return CanonicalBrainAsset(
        asset_id=asset_id,
        path=_relative_path(path, ROOT),
        exists=exists,
        required=required,
        sha256=sha256,
        category=category,
        kind=kind,
    )


def canonical_brain_asset_specs() -> list[dict[str, object]]:
    return [
        {
            "asset_id": "prompt_brain",
            "path": ROOT / "pipeline" / "prompting" / "lena_prompt_brain.py",
            "category": "prompt_brain",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "persona",
            "path": LENA_ROOT / "persona.json",
            "category": "persona",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "higgsfield_identity",
            "path": ROOT / "pipeline" / "identity" / "lena_higgsfield_identity.py",
            "category": "identity",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "character_doctrine",
            "path": ROOT / "pipeline" / "identity" / "lena_character_doctrine_v1.json",
            "category": "identity",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "content_strategy",
            "path": LENA_ROOT / "lena_content_strategy_v1.json",
            "category": "strategy",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "world_continuity_policy",
            "path": LENA_ROOT / "world_continuity_policy_v1.json",
            "category": "policy",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "life_engine_realism_memory_policy",
            "path": LENA_ROOT / "life_engine_realism_memory_policy_v1.json",
            "category": "policy",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "engagement_selection_policy",
            "path": LENA_ROOT / "engagement_selection_policy_v1.json",
            "category": "policy",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "strategy_autonomy_gate_policy",
            "path": LENA_ROOT / "strategy_autonomy_gate_policy_v1.json",
            "category": "policy",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "generation_policy",
            "path": ROOT / "pipeline" / "config" / "lena_generation_policy.json",
            "category": "policy",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "dialogue_prompt",
            "path": ROOT / "pipeline" / "input" / "dialogue" / "prompt.txt",
            "category": "dialogue",
            "required": True,
            "kind": "file",
        },
        {
            "asset_id": "prompt_banks_lena",
            "path": PROMPT_BANK_ROOT,
            "category": "prompt_bank",
            "required": True,
            "kind": "directory",
        },
        {
            "asset_id": "realism_memory_state",
            "path": ROOT / "pipeline" / "state" / "lena_life_engine_realism_memory_v1.json",
            "category": "memory",
            "required": True,
            "kind": "file",
        },
    ]


def load_canonical_brain_assets() -> dict[str, object]:
    assets = [
        asdict(
            _build_asset(
                asset_id=str(spec["asset_id"]),
                path=Path(spec["path"]),
                category=str(spec["category"]),
                required=bool(spec["required"]),
                kind=str(spec["kind"]),
            )
        )
        for spec in canonical_brain_asset_specs()
    ]
    missing_required_assets = [
        asset["asset_id"]
        for asset in assets
        if asset["required"] and not asset["exists"]
    ]
    status = "ready" if not missing_required_assets else "missing_required_assets"
    return {
        "canonical_brain_assets_status": status,
        "missing_required_assets": missing_required_assets,
        "dirty_workspace_dependency": False,
        "assets": assets,
    }


def canonical_brain_assets_summary() -> dict[str, object]:
    report = load_canonical_brain_assets()
    return {
        "canonical_brain_assets_status": report["canonical_brain_assets_status"],
        "missing_required_assets": report["missing_required_assets"],
        "dirty_workspace_dependency": False,
    }

