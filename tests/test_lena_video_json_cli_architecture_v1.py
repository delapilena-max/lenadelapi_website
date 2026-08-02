from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tests.lena_video_json_test_support import PILOT_ROOT, ROOT, copy_pilot


VIDEO_PACKAGE = ROOT / "pipeline" / "media_properties" / "lena" / "video"
CLI_MODULES = (
    "tools.lena_video_validate_v1",
    "tools.lena_video_compile_higgsfield_v1",
)


def _run(*arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        [sys.executable, "-B", "-m", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, json.loads(completed.stdout)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_validate_cli_returns_structured_json_and_zero_counters() -> None:
    completed, report = _run(
        "tools.lena_video_validate_v1",
        "--video-root",
        str(PILOT_ROOT),
        "--validate-only",
    )

    assert completed.returncode == 0
    assert report["exit_code"] == 0
    assert report["ok"] is True
    assert report["validate_only"] is True
    assert set(report["counters"].values()) == {0}


def test_cli_argument_failure_is_structured_and_uses_contract_exit_code() -> None:
    completed, report = _run("tools.lena_video_validate_v1", "--validate-only")

    assert completed.returncode == 2
    assert report["exit_code"] == 2
    assert report["ok"] is False
    assert report["errors"][0]["code"] == "cli_arguments_invalid"
    assert set(report["counters"].values()) == {0}


def test_compile_cli_without_output_performs_no_write(tmp_path: Path) -> None:
    root = copy_pilot(tmp_path)
    before = _snapshot(root)

    completed, report = _run(
        "tools.lena_video_compile_higgsfield_v1",
        "--video-root",
        str(root),
    )

    assert completed.returncode == 0
    assert report["write_requested"] is False
    assert report["writes"] == []
    assert report["execution_authorized"] is False
    assert report["prompt_char_count"] == 3997
    assert report["prompt_char_budget"] == 4096
    assert report["prompt_char_headroom"] == 99
    assert _snapshot(root) == before


def test_compile_validate_only_ignores_explicit_output_and_writes_nothing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    output.mkdir()

    completed, report = _run(
        "tools.lena_video_compile_higgsfield_v1",
        "--video-root",
        str(PILOT_ROOT),
        "--output",
        str(output),
        "--validate-only",
    )

    assert completed.returncode == 0
    assert report["validate_only"] is True
    assert report["write_requested"] is True
    assert report["writes"] == []
    assert list(output.iterdir()) == []


def test_compile_cli_writes_only_two_files_to_explicit_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    output.mkdir()

    first, report = _run(
        "tools.lena_video_compile_higgsfield_v1",
        "--video-root",
        str(PILOT_ROOT),
        "--output",
        str(output),
    )
    second, second_report = _run(
        "tools.lena_video_compile_higgsfield_v1",
        "--video-root",
        str(PILOT_ROOT),
        "--output",
        str(output),
    )

    assert first.returncode == second.returncode == 0
    assert {path.name for path in output.iterdir()} == {
        "lena_video_generation_plan_v1.json",
        "lena_higgsfield_compiled_request_v1.json",
    }
    assert [item["result"] for item in report["writes"]] == ["written", "written"]
    assert [item["result"] for item in second_report["writes"]] == [
        "idempotent_match",
        "idempotent_match",
    ]


def test_cli_help_is_structured_json() -> None:
    for module in CLI_MODULES:
        completed, report = _run(module, "--help")
        assert completed.returncode == 0
        assert report["report_type"] == "lena_video_cli_help_v1"
        assert report["ok"] is True
        assert report["usage"].startswith("usage:")


def test_repository_policy_is_three_photos_plus_one_separate_video() -> None:
    generation = json.loads(
        (ROOT / "pipeline/config/lena_generation_policy.json").read_text(
            encoding="utf-8-sig"
        )
    )
    cadence = json.loads(
        (ROOT / "pipeline/influencer_nodes/lena/daily_cadence.json").read_text(
            encoding="utf-8-sig"
        )
    )

    assert generation["content_mix"]["daily_target"] == {"photos": 3, "videos": 1}
    assert generation["generation"]["video_generation_enabled"] is False
    assert generation["generation"]["video_compiled_requests_authorize_execution"] is False
    assert generation["generation"]["video_prompt_execution_policy_max_chars"] == 4096
    assert cadence["daily_posts"] == 4
    assert [
        slot for slot in cadence["slot_strategy"].values() if slot["media_type"] == "video"
    ] == [cadence["slot_strategy"]["03"]]
    assert sum(
        slot["media_type"] == "photo" for slot in cadence["slot_strategy"].values()
    ) == 3


def test_dependency_direction_has_no_domain_coupling_or_cycles() -> None:
    modules = {
        path.stem: path
        for path in VIDEO_PACKAGE.glob("*.py")
        if path.name != "__init__.py"
    }
    graph: dict[str, set[str]] = {name: set() for name in modules}

    for name, path in modules.items():
        source = path.read_text(encoding="utf-8")
        assert "interstitial_travel_bureau" not in source
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                dependency = (node.module or "").split(".", 1)[0]
                if dependency in modules:
                    graph[name].add(dependency)

    neutral_source = (
        ROOT / "pipeline/media_properties/json_authority_v1.py"
    ).read_text(encoding="utf-8")
    assert "interstitial_travel_bureau" not in neutral_source
    assert "media_properties.lena" not in neutral_source

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        assert name not in visiting, f"circular dependency at {name}: {graph}"
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in graph:
        visit(name)


def test_library_and_cli_modules_have_no_execution_or_network_imports() -> None:
    paths = list(VIDEO_PACKAGE.glob("*.py")) + [
        ROOT / "tools/lena_video_cli_support_v1.py",
        ROOT / "tools/lena_video_validate_v1.py",
        ROOT / "tools/lena_video_compile_higgsfield_v1.py",
    ]
    forbidden = {"requests", "httpx", "socket", "subprocess", "urllib", "anthropic"}

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden), (path, imported & forbidden)


def test_clis_remain_thin_adapters_over_library_functions() -> None:
    for name in (
        "lena_video_validate_v1.py",
        "lena_video_compile_higgsfield_v1.py",
    ):
        source = (ROOT / "tools" / name).read_text(encoding="utf-8")
        assert len(source.splitlines()) < 170
        assert "pipeline.media_properties.lena.video" in source
        assert "provider_arguments" not in source
        assert "exact_compiled_prompt" not in source
