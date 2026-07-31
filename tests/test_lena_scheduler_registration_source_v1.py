from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTER_SCRIPT = ROOT / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"
RETIRED_WRAPPER = ROOT / "setup_lena_3photo_scheduler_v1.ps1"
DRIVER_WRAPPER = ROOT / "tools" / "lena_autonomy_scheduler_driver_run_v1.ps1"
CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"


def _powershell_runtime() -> str | None:
    if sys.platform.startswith("win"):
        return shutil.which("powershell.exe") or shutil.which("pwsh")
    return shutil.which("pwsh")


def _run_powershell(*args: str) -> subprocess.CompletedProcess[str]:
    runtime = _powershell_runtime()
    if not runtime:
        raise RuntimeError("No compatible PowerShell runtime is available")
    return subprocess.run(
        [runtime, "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _register_source_text() -> str:
    return REGISTER_SCRIPT.read_text(encoding="utf-8")


def _wrapper_source_text() -> str:
    return RETIRED_WRAPPER.read_text(encoding="utf-8")


def _assert_register_source_contract() -> None:
    source = _register_source_text()
    assert "[string]$TaskName = 'Lena Autonomy Scheduler Driver'" in source
    assert "disabled_by_default = $true" in source
    assert "task_count = 1" in source
    assert "run_wrapper_path = $WrapperPath" in source
    assert "driver_module_path = $DriverModulePath" in source
    assert "execute = 'powershell.exe'" in source
    assert "schedule_slots = @('morning', 'afternoon', 'evening')" in source
    assert "type = 'poll_every_minute'" in source
    assert "no_daily_orchestrator = $true" in source
    assert "no_fixed_publish_slot_tasks = $true" in source
    assert "no_video_task = $true" in source
    assert "Disable-ScheduledTask -TaskName $TaskName" in source
    assert "RUN_LENA_PUBLISH_MORNING_SLOT.bat" not in source
    assert "RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat" not in source
    assert "RUN_LENA_PUBLISH_EVENING_SLOT.bat" not in source
    assert "Lena Daily Orchestrator" not in source


def _assert_retired_wrapper_contract() -> None:
    source = _wrapper_source_text()
    assert "[string]$TaskName = 'Lena Autonomy Scheduler Driver'" in source
    assert "register_lena_autonomy_scheduler_task_v1.ps1" in source
    assert "& $CanonicalScript -ValidateOnly -TaskName $TaskName -RepoRoot $RepoRoot -PythonExe $PythonExe" in source
    assert "setup_lena_3photo_scheduler_v1.ps1 is retired" in source
    assert "Re-run this retired wrapper with -ValidateOnly only." in source
    assert "Register-ScheduledTask" not in source
    assert "Enable-ScheduledTask" not in source
    assert "RUN_LENA_PUBLISH_MORNING_SLOT.bat" not in source
    assert "RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat" not in source
    assert "RUN_LENA_PUBLISH_EVENING_SLOT.bat" not in source


def test_register_script_validate_only_emits_single_disabled_driver_plan() -> None:
    runtime = _powershell_runtime()
    if runtime:
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
        assert plan["run_wrapper_path"] == str(DRIVER_WRAPPER)
        assert "lena_autonomy_scheduler_driver_run_v1.ps1" in plan["action"]["arguments"]
        assert plan["trigger"]["schedule_slots"] == ["morning", "afternoon", "evening"]
        assert plan["safeguards"]["no_daily_orchestrator"] is True
        assert plan["safeguards"]["no_fixed_publish_slot_tasks"] is True
        assert plan["safeguards"]["no_video_task"] is True
    _assert_register_source_contract()


def test_retired_scheduler_setup_validate_only_delegates_to_canonical_plan() -> None:
    runtime = _powershell_runtime()
    if runtime:
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
        assert plan["run_wrapper_path"] == str(DRIVER_WRAPPER)
    _assert_retired_wrapper_contract()
    _assert_register_source_contract()


def test_retired_scheduler_setup_rejects_mutating_invocation() -> None:
    runtime = _powershell_runtime()
    if runtime:
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
    _assert_retired_wrapper_contract()
