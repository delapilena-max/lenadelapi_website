from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTER_SCRIPT = ROOT / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"
RETIRED_WRAPPER = ROOT / "setup_lena_3photo_scheduler_v1.ps1"
CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"


def _run_powershell(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_register_script_validate_only_emits_single_disabled_driver_plan() -> None:
    proc = _run_powershell(
        "-File",
        str(REGISTER_SCRIPT),
        "-ValidateOnly",
    )

    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["task_count"] == 1
    assert plan["task_name"] == CANONICAL_TASK_NAME
    assert plan["disabled_by_default"] is True
    assert plan["repo_root"] == str(ROOT)
    assert "lena_autonomy_scheduler_driver_run_v1.ps1" in plan["action"]["arguments"]
    assert plan["trigger"]["schedule_slots"] == ["morning", "afternoon", "evening"]
    assert plan["safeguards"]["no_daily_orchestrator"] is True
    assert plan["safeguards"]["no_fixed_publish_slot_tasks"] is True
    assert plan["safeguards"]["no_video_task"] is True


def test_retired_scheduler_setup_validate_only_delegates_to_canonical_plan() -> None:
    proc = _run_powershell(
        "-File",
        str(RETIRED_WRAPPER),
        "-ValidateOnly",
        "-PythonExe",
        sys.executable,
    )

    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["task_name"] == CANONICAL_TASK_NAME
    assert plan["disabled_by_default"] is True
    assert plan["task_count"] == 1


def test_retired_scheduler_setup_rejects_mutating_invocation() -> None:
    proc = _run_powershell(
        "-File",
        str(RETIRED_WRAPPER),
        "-PythonExe",
        sys.executable,
    )

    assert proc.returncode != 0
    combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    assert "retired" in combined.lower()
    assert "register_lena_autonomy_scheduler_task_v1.ps1" in combined
