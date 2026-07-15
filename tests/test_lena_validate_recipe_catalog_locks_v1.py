from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _copy_script(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "tools" / "strategy" / "lena_validate_recipe_catalog_locks_v1.py"
    target = tmp_path / "tools" / "strategy" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _catalog_payloads(*, missing_env: bool = False) -> tuple[dict, dict, dict]:
    recipes = {
        "recipes": [
            {
                "id": "hcr_001",
                "production_status": "active",
                "wardrobe_outfit_id": "wc_001",
                "environment_id": "" if missing_env else "env_001",
                "wardrobe_allow_high_risk": False,
                "scene_type": "mirror selfie",
                "content_pillar": "trust",
                "proof_priority": 1,
            },
            {
                "id": "hcr_test",
                "production_status": "test_only",
                "wardrobe_outfit_id": "wc_001",
                "environment_id": "env_001",
                "scene_type": "mirror selfie",
                "content_pillar": "trust",
                "proof_priority": 99,
            },
        ]
    }
    wardrobe = {
        "outfits": [
            {"outfit_id": "wc_001", "status": "approved"},
        ]
    }
    envs = {
        "environments": [
            {"environment_id": "env_001", "allowed_recipe_types": ["mirror selfie", "trust"]},
        ]
    }
    return recipes, wardrobe, envs


def test_validator_passes_clean_locked_catalogs(tmp_path: Path) -> None:
    script = _copy_script(tmp_path)
    recipes, wardrobe, envs = _catalog_payloads()
    _write_json(tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_high_caliber_prompt_recipe_bank_v1.json", recipes)
    _write_json(tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_wardrobe_catalog_v1.json", wardrobe)
    _write_json(tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_environment_catalog_v1.json", envs)

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "RECIPE CATALOG LOCK VALIDATION: PASSED" in result.stdout
    assert "NO API call.  NO generation.  NO upload." in result.stdout
    assert "NO publish.   NO queue.       NO schedule." in result.stdout


def test_validator_fails_closed_on_missing_environment_binding(tmp_path: Path) -> None:
    script = _copy_script(tmp_path)
    recipes, wardrobe, envs = _catalog_payloads(missing_env=True)
    _write_json(tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_high_caliber_prompt_recipe_bank_v1.json", recipes)
    _write_json(tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_wardrobe_catalog_v1.json", wardrobe)
    _write_json(tmp_path / "pipeline" / "prompt_banks" / "lena" / "lena_environment_catalog_v1.json", envs)

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "FAIL  TC05  all active recipes have environment_id" in result.stdout
    assert "RECIPE CATALOG LOCK VALIDATION: FAILED" in result.stdout
