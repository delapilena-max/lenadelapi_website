from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
REGISTER_SCRIPT = ROOT / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"
RETIRED_WRAPPER = ROOT / "setup_lena_3photo_scheduler_v1.ps1"
DRIVER_WRAPPER = ROOT / "tools" / "lena_autonomy_scheduler_driver_run_v1.ps1"
CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"
PYTHON_EXE = str(Path(r"C:\Python314\python.exe") if Path(r"C:\Python314\python.exe").exists() else Path(sys.executable))
INVALID_DURATION = "P99999999DT23H59M59S"


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


def _canonical_plan() -> dict:
    proc = _run_powershell(
        "-File",
        str(REGISTER_SCRIPT),
        "-ValidateOnly",
        "-RepoRoot",
        str(ROOT),
        "-PythonExe",
        PYTHON_EXE,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _assert_repetition_contract(xml_text: str) -> ET.Element:
    task = ET.fromstring(xml_text)
    repetition = task.find("./Triggers/TimeTrigger/Repetition")
    assert repetition is not None
    interval = repetition.find("Interval")
    assert interval is not None
    assert interval.text == "PT1M"
    assert repetition.findall("Duration") == []
    return repetition


def _mock_registered_xml(tmp_path: Path) -> tuple[dict, str]:
    xml_path = tmp_path / "canonical_task_definition.xml"
    summary_path = tmp_path / "canonical_task_summary.json"
    source_copy = tmp_path / "register_lena_autonomy_scheduler_task_v1.ps1"
    source_copy.write_text(_register_source_text(), encoding="utf-8")
    wrapper_path = tmp_path / "run_mock_registration.ps1"
    wrapper_path.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$global:MockTask = $null

function New-ScheduledTaskAction {{
    [CmdletBinding()]
    param(
        [string]$Execute,
        [string]$Argument,
        [string]$WorkingDirectory
    )
    return [pscustomobject]@{{
        Execute = $Execute
        Arguments = $Argument
        WorkingDirectory = $WorkingDirectory
    }}
}}

function New-ScheduledTaskTrigger {{
    [CmdletBinding()]
    param(
        [switch]$Once,
        [datetime]$At,
        [timespan]$RepetitionInterval,
        [object]$RepetitionDuration = $null
    )
    return [pscustomobject]@{{
        Once = [bool]$Once
        At = $At
        RepetitionInterval = $RepetitionInterval
        RepetitionDuration = if ($PSBoundParameters.ContainsKey('RepetitionDuration')) {{ $RepetitionDuration }} else {{ $null }}
        HasRepetitionDuration = $PSBoundParameters.ContainsKey('RepetitionDuration')
    }}
}}

function New-ScheduledTaskPrincipal {{
    [CmdletBinding()]
    param(
        [string]$UserId,
        [string]$LogonType,
        [string]$RunLevel
    )
    return [pscustomobject]@{{
        UserId = $UserId
        LogonType = $LogonType
        RunLevel = $RunLevel
    }}
}}

function New-ScheduledTaskSettingsSet {{
    [CmdletBinding()]
    param(
        [switch]$AllowStartIfOnBatteries,
        [switch]$DontStopIfGoingOnBatteries,
        [switch]$StartWhenAvailable,
        [string]$MultipleInstances,
        [int]$RestartCount,
        [timespan]$RestartInterval,
        [timespan]$ExecutionTimeLimit,
        [switch]$WakeToRun
    )
    return [pscustomobject]@{{
        AllowStartIfOnBatteries = [bool]$AllowStartIfOnBatteries
        DontStopIfGoingOnBatteries = [bool]$DontStopIfGoingOnBatteries
        StartWhenAvailable = [bool]$StartWhenAvailable
        MultipleInstances = $MultipleInstances
        RestartCount = $RestartCount
        RestartInterval = $RestartInterval
        ExecutionTimeLimit = $ExecutionTimeLimit
        WakeToRun = [bool]$WakeToRun
        Enabled = $true
    }}
}}

function Register-ScheduledTask {{
    [CmdletBinding()]
    param(
        [string]$TaskName,
        [string]$Description,
        [object]$Action,
        [object]$Trigger,
        [object]$Principal,
        [object]$Settings,
        [switch]$Force
    )
    $global:MockTask = [pscustomobject]@{{
        TaskName = $TaskName
        Description = $Description
        Action = @($Action)
        Trigger = $Trigger
        Principal = $Principal
        Settings = $Settings
    }}
    return $global:MockTask
}}

function Disable-ScheduledTask {{
    [CmdletBinding()]
    param([string]$TaskName)
    if ($null -eq $global:MockTask -or $global:MockTask.TaskName -ne $TaskName) {{
        throw "Mock disable missing task: $TaskName"
    }}
    $global:MockTask.Settings.Enabled = $false
    return $global:MockTask
}}

& '{str(source_copy).replace("'", "''")}' -RepoRoot '{str(ROOT).replace("'", "''")}' -PythonExe '{PYTHON_EXE.replace("'", "''")}' -Force

$trigger = $global:MockTask.Trigger
$action = @($global:MockTask.Action)[0]
$intervalText = if ($trigger.RepetitionInterval.TotalMinutes -eq 1) {{ 'PT1M' }} else {{ [string]$trigger.RepetitionInterval }}
$durationXml = if ($trigger.HasRepetitionDuration) {{ '<Duration>' + [System.Xml.XmlConvert]::ToString([timespan]$trigger.RepetitionDuration) + '</Duration>' }} else {{ '' }}
$enabledText = if ([bool]$global:MockTask.Settings.Enabled) {{ 'true' }} else {{ 'false' }}
$xml = @"
<Task>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>$intervalText</Interval>
        $durationXml
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Settings>
    <Enabled>$enabledText</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>$($action.Execute)</Command>
      <Arguments>$($action.Arguments)</Arguments>
      <WorkingDirectory>$($action.WorkingDirectory)</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
$xml | Set-Content -LiteralPath '{str(xml_path).replace("'", "''")}' -Encoding utf8

$summary = [ordered]@{{
    task_name = [string]$global:MockTask.TaskName
    trigger_interval = $intervalText
    trigger_has_repetition_duration = [bool]$trigger.HasRepetitionDuration
    trigger_duration = if ($trigger.HasRepetitionDuration) {{ [System.Xml.XmlConvert]::ToString([timespan]$trigger.RepetitionDuration) }} else {{ $null }}
    task_enabled = [bool]$global:MockTask.Settings.Enabled
    action = [ordered]@{{
        execute = [string]$action.Execute
        arguments = [string]$action.Arguments
        working_directory = [string]$action.WorkingDirectory
    }}
    xml_path = '{str(xml_path).replace("'", "''")}'
}}
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath '{str(summary_path).replace("'", "''")}' -Encoding utf8
""",
        encoding="utf-8",
    )
    proc = _run_powershell("-File", str(wrapper_path))
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    return summary, xml_path.read_text(encoding="utf-8-sig")


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
    assert "repetition_interval = 'PT1M'" in source
    assert "repetition_duration_mode = 'indefinite'" in source
    assert "repetition_duration_element = 'omitted'" in source
    assert "stop_at_duration_end = $false" in source
    assert "function New-CanonicalTriggerPlan" in source
    assert "function New-CanonicalTrigger" in source
    assert "-RepetitionDuration" not in source
    assert "[TimeSpan]::MaxValue" not in source
    assert INVALID_DURATION not in source
    assert '-RepoRoot `"$RepoRoot`"' in source
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


def _assert_driver_wrapper_contract() -> None:
    source = DRIVER_WRAPPER.read_text(encoding="utf-8")
    assert "[string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)" in source
    assert "Set-Location -Path $RepoRoot" in source
    assert "publish_common.populate_process_env_from_canonical_secret_source(repo_root)" in source
    assert 'sys.argv = ["tools.lena_autonomy_scheduler_driver_v1"]' in source
    assert 'runpy.run_module("tools.lena_autonomy_scheduler_driver_v1", run_name="__main__")' in source


def test_register_script_validate_only_emits_single_disabled_driver_plan() -> None:
    runtime = _powershell_runtime()
    if runtime:
        plan = _canonical_plan()
        plan_json = json.dumps(plan, sort_keys=True)
        assert plan["task_count"] == 1
        assert plan["task_name"] == CANONICAL_TASK_NAME
        assert plan["disabled_by_default"] is True
        assert plan["repo_root"] == str(ROOT)
        assert plan["run_wrapper_path"] == str(DRIVER_WRAPPER)
        assert "lena_autonomy_scheduler_driver_run_v1.ps1" in plan["action"]["arguments"]
        assert plan["trigger"]["schedule_slots"] == ["morning", "afternoon", "evening"]
        assert plan["trigger"]["repetition_interval"] == "PT1M"
        assert plan["trigger"]["repetition_duration_mode"] == "indefinite"
        assert plan["trigger"]["repetition_duration_element"] == "omitted"
        assert plan["trigger"]["stop_at_duration_end"] is False
        assert plan["safeguards"]["no_daily_orchestrator"] is True
        assert plan["safeguards"]["no_fixed_publish_slot_tasks"] is True
        assert plan["safeguards"]["no_video_task"] is True
        assert INVALID_DURATION not in plan_json
    _assert_register_source_contract()
    _assert_driver_wrapper_contract()


def test_retired_scheduler_setup_validate_only_delegates_to_canonical_plan() -> None:
    runtime = _powershell_runtime()
    if runtime:
        proc = _run_powershell(
            "-File",
            str(RETIRED_WRAPPER),
            "-ValidateOnly",
            "-PythonExe",
            PYTHON_EXE,
        )
        assert proc.returncode == 0, proc.stderr
        plan = json.loads(proc.stdout)
        assert plan["task_name"] == CANONICAL_TASK_NAME
        assert plan["disabled_by_default"] is True
        assert plan["task_count"] == 1
        assert plan["run_wrapper_path"] == str(DRIVER_WRAPPER)
        assert plan["trigger"]["repetition_interval"] == "PT1M"
        assert plan["trigger"]["repetition_duration_mode"] == "indefinite"
        assert plan["trigger"]["repetition_duration_element"] == "omitted"
        assert INVALID_DURATION not in proc.stdout
    _assert_retired_wrapper_contract()
    _assert_register_source_contract()
    _assert_driver_wrapper_contract()


def test_retired_scheduler_setup_rejects_mutating_invocation() -> None:
    runtime = _powershell_runtime()
    if runtime:
        proc = _run_powershell(
            "-File",
            str(RETIRED_WRAPPER),
            "-PythonExe",
            PYTHON_EXE,
        )
        assert proc.returncode != 0
        combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
        assert "retired" in combined.lower()
        assert "register_lena_autonomy_scheduler_task_v1.ps1" in combined
    _assert_retired_wrapper_contract()
    _assert_driver_wrapper_contract()


def test_mocked_registration_emits_indefinite_repetition_without_duration(tmp_path: Path) -> None:
    summary, xml_text = _mock_registered_xml(tmp_path)
    repetition = _assert_repetition_contract(xml_text)

    assert summary["task_name"] == CANONICAL_TASK_NAME
    assert summary["trigger_interval"] == "PT1M"
    assert summary["trigger_has_repetition_duration"] is False
    assert summary["trigger_duration"] is None
    assert summary["task_enabled"] is False
    assert summary["action"]["execute"] == "powershell.exe"
    assert summary["action"]["working_directory"] == str(ROOT)
    assert "lena_autonomy_scheduler_driver_run_v1.ps1" in summary["action"]["arguments"]
    assert INVALID_DURATION not in xml_text
    assert "<Duration>" not in xml_text
    assert repetition.find("Interval").text == "PT1M"


def test_historical_invalid_duration_fixture_fails_contract_validation() -> None:
    invalid_xml = f"""
<Task>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1M</Interval>
        <Duration>{INVALID_DURATION}</Duration>
      </Repetition>
    </TimeTrigger>
  </Triggers>
</Task>
"""
    try:
        _assert_repetition_contract(invalid_xml)
    except AssertionError:
        return
    raise AssertionError("historical invalid repetition fixture unexpectedly passed validation")
