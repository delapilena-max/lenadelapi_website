from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.itb_helpers import PILOT_ROOT, copy_pilot


def _run(*args: str, cwd: Path | None = None):
    return subprocess.run([sys.executable, "-B", "-m", *args], cwd=cwd or Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)


def test_every_cli_help_is_structured_json():
    for module in ("tools.itb_validate_episode_v1", "tools.itb_compile_episode_v1", "tools.itb_novelty_check_v1", "tools.itb_inspect_episode_v1"):
        result = _run(module, "--help")
        report = json.loads(result.stdout)
        assert result.returncode == 0
        assert report["ok"] is True
        assert report["report_type"] == "itb_cli_help_v1"


def test_validate_and_inspect_validate_only_are_read_only():
    validate = _run("tools.itb_validate_episode_v1", "--episode-root", str(PILOT_ROOT), "--validate-only")
    inspect = _run("tools.itb_inspect_episode_v1", "--episode-root", str(PILOT_ROOT), "--validate-only")
    assert validate.returncode == inspect.returncode == 0
    assert json.loads(validate.stdout)["counters"]["network_calls"] == 0
    assert len(json.loads(inspect.stdout)["artifacts"]) == 14


def test_compile_without_output_mutates_nothing(tmp_path: Path):
    root = copy_pilot(tmp_path)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    result = _run("tools.itb_compile_episode_v1", "--episode-root", str(root), "--validate-only")
    after = {path.name: path.read_bytes() for path in root.iterdir()}
    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["writes"] == []
    assert before == after


def test_novelty_cli_returns_zero_activity():
    result = _run("tools.itb_novelty_check_v1", "--episode-root", str(PILOT_ROOT), "--ledger", str(PILOT_ROOT), "--validate-only")
    report = json.loads(result.stdout)
    assert result.returncode == 0
    assert report["disposition"] == "approve"
    assert all(value == 0 for value in report["counters"].values())


def test_invalid_cli_arguments_return_json_and_meaningful_exit():
    result = _run("tools.itb_validate_episode_v1", "--validate-only")
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["errors"][0]["code"] == "cli_arguments_invalid"


def test_missing_episode_root_returns_structured_json_for_every_cli(tmp_path: Path):
    missing_root = tmp_path / "missing_episode"
    for module in (
        "tools.itb_validate_episode_v1",
        "tools.itb_compile_episode_v1",
        "tools.itb_novelty_check_v1",
        "tools.itb_inspect_episode_v1",
    ):
        result = _run(module, "--episode-root", str(missing_root), "--validate-only")
        report = json.loads(result.stdout)
        assert result.returncode == 1
        assert result.stderr == ""
        assert report["ok"] is False
        assert report["errors"][0]["code"] == "episode_root_unavailable"
        assert all(value == 0 for value in report["counters"].values())
