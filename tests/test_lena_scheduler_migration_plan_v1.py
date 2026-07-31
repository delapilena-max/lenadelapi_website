from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "migrate_lena_legacy_scheduler_tasks_to_canonical_driver_v1.ps1"
REGISTER_SCRIPT = ROOT / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"
CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"
LEGACY_REPO_ROOT = r"C:\projects\ai\lenadelapi_website_autopublish_fix"
SECRET_SENTINEL = "TEST_META_PAGE_ACCESS_TOKEN_SHOULD_NOT_APPEAR"
INVALID_DURATION = "P99999999DT23H59M59S"
LEGACY_TASKS = [
    "Lena Daily Orchestrator",
    "Lena Publish Morning Slot",
    "Lena Publish Afternoon Slot",
    "Lena Publish Evening Slot",
]
LEGACY_PRINCIPAL = {
    "user_id": "Nicolas",
    "logon_type": "Interactive",
    "run_level": "Limited",
}
PYTHON_EXE = str(Path(r"C:\Python314\python.exe") if Path(r"C:\Python314\python.exe").exists() else Path(sys.executable))


def _powershell_runtime() -> str | None:
    if sys.platform.startswith("win"):
        return shutil.which("powershell.exe") or shutil.which("pwsh")
    return shutil.which("pwsh")


def _run_powershell(*args: str) -> subprocess.CompletedProcess[str]:
    runtime = _powershell_runtime()
    if not runtime:
        raise RuntimeError("No compatible PowerShell runtime is available")
    return _run_powershell_host(runtime, *args)


def _run_powershell_host(host_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [host_path, "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_powershell_command(command: str) -> subprocess.CompletedProcess[str]:
    return _run_powershell("-Command", command)


def _process_debug(proc: subprocess.CompletedProcess[str], label: str) -> str:
    command = " ".join(str(part) for part in proc.args)
    return (
        f"{label} failed\n"
        f"command: {command}\n"
        f"returncode: {proc.returncode}\n"
        f"stderr:\n{proc.stderr}\n"
        f"stdout:\n{proc.stdout}"
    )


def _assert_json_success(proc: subprocess.CompletedProcess[str], label: str) -> dict:
    assert proc.returncode == 0, _process_debug(proc, label)
    assert proc.stdout.strip(), _process_debug(proc, label)
    return json.loads(proc.stdout)


def _assert_failed_process(
    proc: subprocess.CompletedProcess[str], label: str, expected_text: str | None = None
) -> None:
    assert proc.returncode != 0, _process_debug(proc, label)
    assert proc.stderr.strip(), _process_debug(proc, label)
    if expected_text is not None:
        combined = proc.stderr + proc.stdout
        assert expected_text in combined, _process_debug(proc, label)


def _legacy_task(
    name: str,
    execute: str,
    arguments: str,
    *,
    enabled: bool = False,
    state: str = "Disabled",
    user_id: str = "Nicolas",
    logon_type: str = "Interactive",
    run_level: str = "Limited",
) -> dict:
    return {
        "task_name": name,
        "present": True,
        "enabled": enabled,
        "state": state,
        "user_id": user_id,
        "logon_type": logon_type,
        "run_level": run_level,
        "actions": [
            {
                "execute": execute,
                "arguments": arguments,
                "working_directory": LEGACY_REPO_ROOT,
            }
        ],
    }


def _snapshot_payload() -> list[dict]:
    return [
        _legacy_task(
            "Lena Daily Orchestrator",
            r"C:\Python314\python.exe",
            r"tools\lena_daily_orchestrator_v1.py",
        ),
        _legacy_task(
            "Lena Publish Morning Slot",
            "cmd.exe",
            r'/c "C:\projects\ai\lenadelapi_website_autopublish_fix\RUN_LENA_PUBLISH_MORNING_SLOT.bat"',
        ),
        _legacy_task(
            "Lena Publish Afternoon Slot",
            "cmd.exe",
            r'/c "C:\projects\ai\lenadelapi_website_autopublish_fix\RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat"',
        ),
        _legacy_task(
            "Lena Publish Evening Slot",
            "cmd.exe",
            r'/c "C:\projects\ai\lenadelapi_website_autopublish_fix\RUN_LENA_PUBLISH_EVENING_SLOT.bat"',
        ),
        {
            "task_name": CANONICAL_TASK_NAME,
            "present": False,
        },
    ]


def _write_snapshot(path: Path, payload: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _validate_only_plan(
    tmp_path: Path,
    *,
    payload: list[dict] | None = None,
    output_root: Path | None = None,
    prior_receipt_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = _snapshot_payload() if payload is None else payload
    snapshot_path = _write_snapshot(tmp_path / "snapshot.json", payload)
    output_root = tmp_path / "planned_output" if output_root is None else output_root
    args = [
        "-File",
        str(SCRIPT),
        "-ValidateOnly",
        "-RepoRoot",
        str(ROOT),
        "-PythonExe",
        PYTHON_EXE,
        "-TaskSnapshotPath",
        str(snapshot_path),
        "-OutputRoot",
        str(output_root),
    ]
    if prior_receipt_path is not None:
        args.extend(["-PriorReceiptPath", str(prior_receipt_path)])
    return _run_powershell(*args)


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
    return _assert_json_success(proc, "canonical validate-only registration plan")


def _contract_sha256(plan: dict) -> str:
    return str(plan["contract_sha256"])


def _json_sha256(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _powershell_receipt_proof_sha256(receipt_path: Path) -> str:
    literal_path = str(receipt_path).replace("'", "''")
    proc = _run_powershell(
        "-Command",
        (
            f"$receipt = Get-Content -LiteralPath '{literal_path}' -Raw | ConvertFrom-Json; "
            "$material = [ordered]@{"
            "report_type = [string]$receipt.report_type; "
            "schema_version = [string]$receipt.schema_version; "
            "stage = [string]$receipt.stage; "
            "contract_sha256 = [string]$receipt.contract_sha256; "
            "repo_root = [string]$receipt.repo_root; "
            "python_exe = [string]$receipt.python_exe; "
            "pre_backups = @($receipt.pre_backups); "
            "canonical_pre = $receipt.canonical_pre; "
            "canonical_post = $receipt.canonical_post; "
            "legacy_tasks_removed = @($receipt.legacy_tasks_removed); "
            "changes = @($receipt.changes); "
            "rollback = $receipt.rollback; "
            "post_state = @($receipt.post_state) "
            "}; "
            "$json = $material | ConvertTo-Json -Depth 12 -Compress; "
            "$sha = [System.Security.Cryptography.SHA256]::Create(); "
            "try { "
            "$bytes = [Text.Encoding]::UTF8.GetBytes($json); "
            "([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() "
            "} finally { $sha.Dispose() }"
        ),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _write_backup_xml(backups_dir: Path, task_name: str) -> tuple[str, str]:
    xml_path = backups_dir / f"{task_name.replace(' ', '_')}.xml"
    xml_text = (
        "<Task>"
        f"<RegistrationInfo><URI>{task_name}</URI></RegistrationInfo>"
        f"<Actions><Exec><Command>{task_name}</Command></Exec></Actions>"
        "</Task>"
    )
    xml_path.write_text(xml_text, encoding="utf-8")
    return str(xml_path), hashlib.sha256(xml_text.encode("utf-8")).hexdigest()


def _write_prior_receipt(
    tmp_path: Path,
    *,
    contract_sha256: str,
    stage: str = "legacy_retirement_started",
    legacy_tasks_removed: list[str] | None = None,
    canonical_present: bool = True,
    tamper_contract_hash: bool = False,
) -> Path:
    backups_dir = tmp_path / "prior_backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    pre_backups: list[dict] = []
    for task_name in LEGACY_TASKS:
        xml_path, xml_sha = _write_backup_xml(backups_dir, task_name)
        pre_backups.append(
            {
                "task_name": task_name,
                "xml_path": xml_path,
                "xml_sha256": xml_sha,
            }
        )

    canonical_pre = []
    canonical_post = None
    if canonical_present:
        xml_path, xml_sha = _write_backup_xml(backups_dir, CANONICAL_TASK_NAME)
        canonical_pre = [
            {
                "task_name": CANONICAL_TASK_NAME,
                "xml_path": xml_path,
                "xml_sha256": xml_sha,
            }
        ]
        canonical_post = {
            "task_name": CANONICAL_TASK_NAME,
            "xml_path": xml_path,
            "xml_sha256": xml_sha,
        }

    receipt = {
        "report_type": "lena_scheduler_legacy_to_canonical_driver_migration_receipt",
        "schema_version": "v1",
        "stage": stage,
        "contract_sha256": "0" * 64 if tamper_contract_hash else contract_sha256,
        "repo_root": str(ROOT),
        "python_exe": PYTHON_EXE,
        "pre_backups": pre_backups,
        "canonical_pre": canonical_pre,
        "canonical_post": canonical_post,
        "legacy_tasks_removed": legacy_tasks_removed or ["Lena Daily Orchestrator"],
        "changes": ["Resumed from prior receipt"],
        "rollback": {
            "legacy_xml_paths": [item["xml_path"] for item in pre_backups],
            "canonical_pre_xml_paths": [item["xml_path"] for item in canonical_pre],
            "canonical_post_xml_path": canonical_post["xml_path"] if canonical_post else "",
        },
        "post_state": [],
    }
    path = tmp_path / "prior_receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    receipt["proof_sha256"] = _powershell_receipt_proof_sha256(path)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _assert_trigger_contract(xml_text: str) -> None:
    assert "<Interval>PT1M</Interval>" in xml_text
    assert "<Duration>" not in xml_text
    assert INVALID_DURATION not in xml_text


def _powershell_hosts() -> dict[str, str]:
    hosts: dict[str, str] = {}
    desktop = shutil.which("powershell.exe")
    if desktop:
        hosts["desktop"] = desktop
    core = shutil.which("pwsh") or shutil.which("pwsh.exe")
    if core:
        hosts["core"] = core
    return hosts


def _powershell_single_quote(text: str) -> str:
    return text.replace("'", "''")


def _extract_json_lines(text: str) -> list[dict]:
    payloads: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            payloads.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return payloads


def _replace_test_is_administrator(source: str) -> str:
    updated, count = re.subn(
        (
            r"function Test-IsAdministrator \{\r?\n"
            r"    \$identity = \[Security\.Principal\.WindowsIdentity\]::GetCurrent\(\)\r?\n"
            r"    \$principal = \[Security\.Principal\.WindowsPrincipal\]::new\(\$identity\)\r?\n"
            r"    return \$principal\.IsInRole\(\[Security\.Principal\.WindowsBuiltInRole\]::Administrator\)\r?\n"
            r"\}"
        ),
        "function Test-IsAdministrator {\n    return $true\n}",
        source,
        count=1,
    )
    assert count == 1
    return updated


def _run_list_subexpression_probe(host_path: str) -> subprocess.CompletedProcess[str]:
    command = """
$ErrorActionPreference = 'Stop'
try {
    $preBackups = New-Object System.Collections.Generic.List[object]
    $preBackups.Add([ordered]@{ task_name = 'A'; xml_path = 'x'; xml_sha256 = 'x' }) | Out-Null
    [pscustomobject]@{
        ok = $true
        count = @($preBackups).Count
        edition = [string]$PSVersionTable.PSEdition
        version = [string]$PSVersionTable.PSVersion
    } | ConvertTo-Json -Compress
}
catch {
    [pscustomobject]@{
        ok = $false
        exception_type = $_.Exception.GetType().FullName
        message = [string]$_.Exception.Message
        edition = [string]$PSVersionTable.PSEdition
        version = [string]$PSVersionTable.PSVersion
    } | ConvertTo-Json -Compress
    exit 1
}
"""
    return _run_powershell_host(host_path, "-Command", command)


def _run_mocked_apply(
    tmp_path: Path,
    *,
    source_text: str | None = None,
    failure_mode: str = "",
    host_path: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict, Path]:
    source_text = _source() if source_text is None else source_text
    source_text = _replace_test_is_administrator(source_text)

    snapshot_path = _write_snapshot(tmp_path / "mock_snapshot.json", _snapshot_payload())
    output_root = tmp_path / "mock_apply_output"
    summary_path = tmp_path / "mock_summary.json"
    source_copy = tmp_path / "mocked_apply_source.ps1"
    source_copy.write_text(source_text, encoding="utf-8")
    wrapper_path = tmp_path / "run_mocked_apply.ps1"
    wrapper_path.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:META_PAGE_ACCESS_TOKEN = '{SECRET_SENTINEL}'
$global:MockTaskStore = @{{}}
$global:MockOperationLog = New-Object System.Collections.Generic.List[object]
$global:FailureMode = '{_powershell_single_quote(failure_mode)}'

function Add-MockOperation {{
    param(
        [string]$Operation,
        [string]$TaskName = '',
        [object]$Details = $null
    )
    $entry = [ordered]@{{
        operation = $Operation
        task_name = $TaskName
        details = $Details
    }}
    $global:MockOperationLog.Add($entry) | Out-Null
}}

function New-MockTaskFromParts {{
    param(
        [string]$TaskName,
        [bool]$Enabled,
        [string]$State,
        [object[]]$Actions,
        [object]$Principal,
        [object]$Settings
    )
    return [pscustomobject]@{{
        TaskName = $TaskName
        State = $State
        Actions = $Actions
        Principal = $Principal
        Settings = $Settings
    }}
}}

function Get-MockPropertyValue {{
    param(
        [object]$Item,
        [string]$Name,
        [object]$Default = $null
    )
    $property = $Item.PSObject.Properties[$Name]
    if ($null -eq $property) {{
        return $Default
    }}
    return $property.Value
}}

function New-MockTaskFromSnapshot {{
    param([object]$Item)
    $actions = @()
    foreach ($action in @(Get-MockPropertyValue -Item $Item -Name 'actions' -Default @())) {{
        $actions += [pscustomobject]@{{
            Execute = [string](Get-MockPropertyValue -Item $action -Name 'execute' -Default '')
            Arguments = [string](Get-MockPropertyValue -Item $action -Name 'arguments' -Default '')
            WorkingDirectory = [string](Get-MockPropertyValue -Item $action -Name 'working_directory' -Default '')
        }}
    }}
    $principal = [pscustomobject]@{{
        UserId = [string](Get-MockPropertyValue -Item $Item -Name 'user_id' -Default '')
        LogonType = [string](Get-MockPropertyValue -Item $Item -Name 'logon_type' -Default '')
        RunLevel = [string](Get-MockPropertyValue -Item $Item -Name 'run_level' -Default '')
    }}
    $settings = [pscustomobject]@{{
        Enabled = [bool](Get-MockPropertyValue -Item $Item -Name 'enabled' -Default $false)
    }}
    return New-MockTaskFromParts -TaskName ([string](Get-MockPropertyValue -Item $Item -Name 'task_name' -Default '')) -Enabled ([bool](Get-MockPropertyValue -Item $Item -Name 'enabled' -Default $false)) -State ([string](Get-MockPropertyValue -Item $Item -Name 'state' -Default '')) -Actions $actions -Principal $principal -Settings $settings
}}

function Initialize-MockTaskStore {{
    param([string]$SnapshotPath)
    foreach ($item in (Get-Content -LiteralPath $SnapshotPath -Raw | ConvertFrom-Json)) {{
        if ([bool](Get-MockPropertyValue -Item $item -Name 'present' -Default $false)) {{
            $global:MockTaskStore[[string]$item.task_name] = New-MockTaskFromSnapshot -Item $item
        }}
    }}
}}

function Get-StringTypeName {{
    param([object]$Value)
    if ($null -eq $Value) {{
        return '<null>'
    }}
    return $Value.GetType().FullName
}}

function ConvertTo-MockActionArray {{
    param([object]$Value)
    if ($null -eq $Value) {{
        return @()
    }}
    if ($Value -is [Array]) {{
        return @($Value)
    }}
    return @($Value)
}}

function ConvertTo-MockStableArray {{
    param([object]$Value)
    if ($null -eq $Value) {{
        return @()
    }}
    if ($Value -is [Array]) {{
        return $Value
    }}
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {{
        $items = New-Object System.Collections.Generic.List[object]
        foreach ($item in $Value) {{
            $items.Add($item) | Out-Null
        }}
        return $items.ToArray()
    }}
    return @($Value)
}}

function ConvertTo-MockTaskSummary {{
    param([object]$Task)
    return [ordered]@{{
        task_name = [string]$Task.TaskName
        enabled = [bool]$Task.Settings.Enabled
        state = [string]$Task.State
        actions = @($Task.Actions | ForEach-Object {{
            [ordered]@{{
                execute = [string]$_.Execute
                arguments = [string]$_.Arguments
                working_directory = [string]$_.WorkingDirectory
            }}
        }})
        principal = [ordered]@{{
            user_id = [string]$Task.Principal.UserId
            logon_type = [string]$Task.Principal.LogonType
            run_level = [string]$Task.Principal.RunLevel
        }}
    }}
}}

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

function Get-ScheduledTask {{
    [CmdletBinding()]
    param([string]$TaskName)
    Add-MockOperation -Operation 'Get-ScheduledTask' -TaskName $TaskName -Details ([ordered]@{{
        task_name_type = Get-StringTypeName -Value $TaskName
        error_action = [string]$ErrorActionPreference
    }})
    if ([string]::IsNullOrEmpty($TaskName)) {{
        return @($global:MockTaskStore.Values)
    }}
    if ($global:MockTaskStore.ContainsKey($TaskName)) {{
        return $global:MockTaskStore[$TaskName]
    }}
    if ($ErrorActionPreference -eq 'Stop') {{
        throw "Mock task missing: $TaskName"
    }}
    return $null
}}

function Export-ScheduledTask {{
    [CmdletBinding()]
    param([string]$TaskName)
    Add-MockOperation -Operation 'Export-ScheduledTask' -TaskName $TaskName -Details ([ordered]@{{
        task_name_type = Get-StringTypeName -Value $TaskName
    }})
    if (-not $global:MockTaskStore.ContainsKey($TaskName)) {{
        throw "Mock export missing task: $TaskName"
    }}
    $task = $global:MockTaskStore[$TaskName]
    $action = @($task.Actions)[0]
    return "<Task><RegistrationInfo><URI>$TaskName</URI></RegistrationInfo><Principals><Principal><UserId>$($task.Principal.UserId)</UserId><LogonType>$($task.Principal.LogonType)</LogonType><RunLevel>$($task.Principal.RunLevel)</RunLevel></Principal></Principals><Actions><Exec><Command>$($action.Execute)</Command><Arguments>$($action.Arguments)</Arguments><WorkingDirectory>$($action.WorkingDirectory)</WorkingDirectory></Exec></Actions></Task>"
}}

function Get-ScheduledTaskInfo {{
    [CmdletBinding()]
    param([string]$TaskName)
    Add-MockOperation -Operation 'Get-ScheduledTaskInfo' -TaskName $TaskName
    if (-not $global:MockTaskStore.ContainsKey($TaskName)) {{
        if ($ErrorActionPreference -eq 'Stop') {{
            throw "Mock task info missing: $TaskName"
        }}
        return $null
    }}
    $now = Get-Date '2026-07-31T10:30:00Z'
    return [pscustomobject]@{{
        LastRunTime = $now.AddMinutes(-1)
        LastTaskResult = 0
        NextRunTime = $now.AddMinutes(1)
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
        [string]$Xml,
        [switch]$Force
    )
    Add-MockOperation -Operation 'Register-ScheduledTask' -TaskName $TaskName -Details ([ordered]@{{
        xml_mode = $PSBoundParameters.ContainsKey('Xml')
        action_type = Get-StringTypeName -Value $Action
        trigger_type = Get-StringTypeName -Value $Trigger
        trigger_interval = if ($null -ne $Trigger -and $null -ne $Trigger.RepetitionInterval) {{ if ($Trigger.RepetitionInterval.TotalMinutes -eq 1) {{ 'PT1M' }} else {{ [string]$Trigger.RepetitionInterval }} }} else {{ $null }}
        trigger_has_repetition_duration = if ($null -ne $Trigger) {{ [bool]$Trigger.HasRepetitionDuration }} else {{ $false }}
        trigger_duration = if ($null -ne $Trigger -and $Trigger.HasRepetitionDuration) {{ [System.Xml.XmlConvert]::ToString([timespan]$Trigger.RepetitionDuration) }} else {{ $null }}
        principal_type = Get-StringTypeName -Value $Principal
        settings_type = Get-StringTypeName -Value $Settings
    }})
    if ($global:FailureMode -eq 'throw_on_register' -and -not $PSBoundParameters.ContainsKey('Xml') -and $TaskName -eq '{CANONICAL_TASK_NAME}') {{
        $inner = [System.InvalidOperationException]::new('mock inner failure')
        throw [System.Exception]::new('mock canonical registration failure', $inner)
    }}
    if ($PSBoundParameters.ContainsKey('Xml')) {{
        [xml]$xmlDoc = $Xml
        $actionObject = [pscustomobject]@{{
            Execute = [string]$xmlDoc.Task.Actions.Exec.Command
            Arguments = [string]$xmlDoc.Task.Actions.Exec.Arguments
            WorkingDirectory = [string]$xmlDoc.Task.Actions.Exec.WorkingDirectory
        }}
        $principalObject = [pscustomobject]@{{
            UserId = [string]$xmlDoc.Task.Principals.Principal.UserId
            LogonType = [string]$xmlDoc.Task.Principals.Principal.LogonType
            RunLevel = [string]$xmlDoc.Task.Principals.Principal.RunLevel
        }}
        $settingsObject = [pscustomobject]@{{ Enabled = $false }}
        $task = New-MockTaskFromParts -TaskName $TaskName -Enabled $false -State 'Disabled' -Actions @($actionObject) -Principal $principalObject -Settings $settingsObject
        $global:MockTaskStore[$TaskName] = $task
        return $task
    }}
    $actions = ConvertTo-MockActionArray -Value $Action
    $task = New-MockTaskFromParts -TaskName $TaskName -Enabled ([bool]$Settings.Enabled) -State 'Disabled' -Actions $actions -Principal $Principal -Settings $Settings
    $task.Settings.Enabled = [bool]$Settings.Enabled
    $global:MockTaskStore[$TaskName] = $task
    return $task
}}

function Disable-ScheduledTask {{
    [CmdletBinding()]
    param([string]$TaskName)
    Add-MockOperation -Operation 'Disable-ScheduledTask' -TaskName $TaskName
    if (-not $global:MockTaskStore.ContainsKey($TaskName)) {{
        throw "Mock disable missing task: $TaskName"
    }}
    $task = $global:MockTaskStore[$TaskName]
    $task.Settings.Enabled = $false
    $task.State = 'Disabled'
    return $task
}}

function Unregister-ScheduledTask {{
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
    param([string]$TaskName)
    Add-MockOperation -Operation 'Unregister-ScheduledTask' -TaskName $TaskName
    if ($global:MockTaskStore.ContainsKey($TaskName)) {{
        $global:MockTaskStore.Remove($TaskName) | Out-Null
    }}
}}

Initialize-MockTaskStore -SnapshotPath '{_powershell_single_quote(str(snapshot_path))}'
$exitCode = 0
$caughtMessage = ''
$caughtType = ''
try {{
    & '{_powershell_single_quote(str(source_copy))}' -Apply -RepoRoot '{_powershell_single_quote(str(ROOT))}' -PythonExe '{_powershell_single_quote(PYTHON_EXE)}' -TaskSnapshotPath '{_powershell_single_quote(str(snapshot_path))}' -OutputRoot '{_powershell_single_quote(str(output_root))}' | Out-String | Set-Content -LiteralPath '{_powershell_single_quote(str(tmp_path / "script_stdout.txt"))}' -Encoding utf8
}}
catch {{
    $exitCode = 1
    $caughtMessage = [string]$_.Exception.Message
    $caughtType = $_.Exception.GetType().FullName
}}
$taskStates = @($global:MockTaskStore.Values | Sort-Object TaskName | ForEach-Object {{ ConvertTo-MockTaskSummary -Task $_ }})
$canonicalTask = if ($global:MockTaskStore.ContainsKey('{CANONICAL_TASK_NAME}')) {{ $global:MockTaskStore['{CANONICAL_TASK_NAME}'] }} else {{ $null }}
$canonicalXml = ''
if ($null -ne $canonicalTask) {{
    $action = @($canonicalTask.Actions)[0]
    $registerEntry = @($global:MockOperationLog | Where-Object {{ $_.operation -eq 'Register-ScheduledTask' -and $_.task_name -eq '{CANONICAL_TASK_NAME}' }} | Select-Object -First 1)[0]
    $triggerInterval = if ($null -ne $registerEntry) {{ [string]$registerEntry.details.trigger_interval }} else {{ '' }}
    $durationXml = if ($null -ne $registerEntry -and $registerEntry.details.trigger_has_repetition_duration) {{ '<Duration>' + [string]$registerEntry.details.trigger_duration + '</Duration>' }} else {{ '' }}
    $enabledText = if ([bool]$canonicalTask.Settings.Enabled) {{ 'true' }} else {{ 'false' }}
    $canonicalXml = "<Task><Triggers><TimeTrigger><Repetition><Interval>$triggerInterval</Interval>$durationXml</Repetition></TimeTrigger></Triggers><Settings><Enabled>$enabledText</Enabled></Settings><Actions><Exec><Command>$($action.Execute)</Command><Arguments>$($action.Arguments)</Arguments><WorkingDirectory>$($action.WorkingDirectory)</WorkingDirectory></Exec></Actions></Task>"
}}
$summary = [ordered]@{{
    exit_code = $exitCode
    caught_message = $caughtMessage
    caught_type = $caughtType
    operation_log = [object[]](ConvertTo-MockStableArray -Value $global:MockOperationLog)
    remaining_task_names = @($taskStates | ForEach-Object {{ $_.task_name }})
    task_states = $taskStates
    run_roots = @((Get-ChildItem -LiteralPath '{_powershell_single_quote(str(output_root))}' -Directory -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {{ $_.FullName }}))
    canonical_xml = $canonicalXml
}}
$summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath '{_powershell_single_quote(str(summary_path))}' -Encoding utf8
exit $exitCode
""",
        encoding="utf-8",
    )
    runtime = host_path or _powershell_runtime()
    assert runtime is not None
    proc = _run_powershell_host(runtime, "-File", str(wrapper_path))
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    return proc, summary, output_root


def _single_run_root(output_root: Path) -> Path:
    run_roots = [path for path in output_root.iterdir() if path.is_dir()]
    assert len(run_roots) == 1
    return run_roots[0]


def test_migration_validate_only_plan_identifies_four_legacy_tasks_precisely(tmp_path: Path) -> None:
    proc = _validate_only_plan(tmp_path)
    plan = _assert_json_success(proc, "migration validate-only plan")

    assert plan["ok"] is True
    assert plan["canonical_task_name"] == CANONICAL_TASK_NAME
    assert plan["governed_legacy_task_count"] == 4
    assert [item["task_name"] for item in plan["legacy_tasks"]] == LEGACY_TASKS
    assert plan["canonical_replacement_count"] == 1
    assert plan["canonical_plan"]["task_count"] == 1
    assert plan["canonical_plan"]["disabled_by_default"] is True
    assert plan["canonical_plan"]["trigger"]["repetition_interval"] == "PT1M"
    assert plan["canonical_plan"]["trigger"]["repetition_duration_mode"] == "indefinite"
    assert plan["canonical_plan"]["trigger"]["repetition_duration_element"] == "omitted"
    assert plan["canonical_plan"]["trigger"]["stop_at_duration_end"] is False
    assert plan["canonical_task_state"]["present"] is False
    assert plan["runtime_capabilities"] == {
        "provider_calls": False,
        "publishing": False,
        "queue_mutation": False,
        "media_generation": False,
        "anthropic": False,
        "video": False,
    }
    assert INVALID_DURATION not in json.dumps(plan)


def test_migration_plan_governs_exact_old_checkout_paths_and_principals(tmp_path: Path) -> None:
    proc = _validate_only_plan(tmp_path)
    plan = _assert_json_success(proc, "migration validate-only principal/path plan")

    assert plan["legacy_expected_repo_root"] == LEGACY_REPO_ROOT
    for spec in plan["governed_legacy_tasks"]:
        assert spec["working_directory"] == LEGACY_REPO_ROOT
        assert spec["principal"] == LEGACY_PRINCIPAL
    for item in plan["legacy_tasks"]:
        assert item["principal_match"] is True
        assert item["actions_match"] is True
        assert item["exact_disabled_match"] is True


def test_enabled_legacy_task_fails_closed(tmp_path: Path) -> None:
    payload = _snapshot_payload()
    payload[1]["enabled"] = True

    proc = _validate_only_plan(tmp_path, payload=payload)
    _assert_failed_process(proc, "enabled legacy task fail-closed case", "legacy_task_not_disabled")


def test_missing_legacy_task_without_prior_receipt_fails_closed(tmp_path: Path) -> None:
    payload = _snapshot_payload()
    payload[2]["present"] = False

    proc = _validate_only_plan(tmp_path, payload=payload)
    _assert_failed_process(proc, "missing legacy task fail-closed case", "legacy_task_missing")


def test_missing_legacy_task_with_valid_prior_receipt_authorizes_deterministic_resume(tmp_path: Path) -> None:
    first_proc = _validate_only_plan(tmp_path / "plan_seed")
    first_plan = _assert_json_success(first_proc, "seed validate-only plan")
    prior_receipt = _write_prior_receipt(
        tmp_path,
        contract_sha256=_contract_sha256(first_plan),
    )

    payload = _snapshot_payload()
    payload[0]["present"] = False
    payload[-1] = {
        "task_name": CANONICAL_TASK_NAME,
        "present": True,
        "enabled": False,
        "state": "Disabled",
        "actions": [
            {
                "execute": _canonical_plan()["action"]["execute"],
                "arguments": _canonical_plan()["action"]["arguments"],
                "working_directory": _canonical_plan()["action"]["working_directory"],
            }
        ],
    }

    proc = _validate_only_plan(tmp_path / "resume_case", payload=payload, prior_receipt_path=prior_receipt)
    plan = _assert_json_success(proc, "resumable validate-only plan")

    assert plan["ok"] is True
    assert plan["resumable_state"]["prior_receipt_valid"] is True
    assert plan["resumable_state"]["authorized"] is True
    assert plan["resumable_state"]["resume_mode"] == "legacy_retirement_replay"
    assert plan["resumable_state"]["deterministic_recovery"] is True


def test_tampered_prior_receipt_fails_closed(tmp_path: Path) -> None:
    first_proc = _validate_only_plan(tmp_path / "plan_seed")
    first_plan = _assert_json_success(first_proc, "seed validate-only plan for tampered receipt")
    prior_receipt = _write_prior_receipt(
        tmp_path,
        contract_sha256=_contract_sha256(first_plan),
        tamper_contract_hash=True,
    )

    payload = _snapshot_payload()
    payload[0]["present"] = False
    payload[-1] = {
        "task_name": CANONICAL_TASK_NAME,
        "present": True,
        "enabled": False,
        "state": "Disabled",
        "actions": [
            {
                "execute": _canonical_plan()["action"]["execute"],
                "arguments": _canonical_plan()["action"]["arguments"],
                "working_directory": _canonical_plan()["action"]["working_directory"],
            }
        ],
    }

    proc = _validate_only_plan(tmp_path / "tampered_case", payload=payload, prior_receipt_path=prior_receipt)
    _assert_failed_process(proc, "tampered prior receipt fail-closed case", "prior_receipt_invalid")


def test_validate_only_performs_zero_writes_and_plans_external_paths(tmp_path: Path) -> None:
    output_root = tmp_path / "outside_reports"
    proc = _validate_only_plan(tmp_path, output_root=output_root)
    plan = _assert_json_success(proc, "zero-write validate-only plan")

    assert plan["mutation_counters"] == {
        "scheduler_mutations_performed": 0,
        "task_start_operations_performed": 0,
        "task_enable_operations_performed": 0,
        "backup_writes_performed": 0,
        "receipt_writes_performed": 0,
    }
    assert plan["output_root_outside_repo"] is True
    assert Path(plan["backup_root"]).is_absolute()
    assert str(output_root) in plan["backup_root"]
    assert not output_root.exists()
    assert Path(plan["receipt_path"]).parent == Path(plan["backup_root"])
    assert Path(plan["rollback_receipt_path"]).parent == Path(plan["backup_root"])


def test_canonical_replacement_is_exact_and_disabled(tmp_path: Path) -> None:
    proc = _validate_only_plan(tmp_path)
    plan = _assert_json_success(proc, "canonical replacement validate-only plan")
    canonical = _canonical_plan()

    assert plan["canonical_replacement_count"] == 1
    assert plan["canonical_plan"]["task_name"] == CANONICAL_TASK_NAME
    assert plan["canonical_plan"]["action"]["arguments"] == canonical["action"]["arguments"]
    assert plan["canonical_plan"]["action"]["working_directory"] == str(ROOT)
    assert plan["canonical_plan"]["trigger"] == canonical["trigger"]
    assert plan["apply_guards"]["canonical_task_must_be_disabled"] is True
    assert plan["apply_guards"]["verify_canonical_task_before_legacy_removal"] is True


def test_windows_powershell_desktop_reproduces_generic_list_array_subexpression_failure_when_available() -> None:
    host_path = _powershell_hosts().get("desktop")
    if host_path is None:
        pytest.skip("Windows PowerShell Desktop is not available on this runner")

    proc = _run_list_subexpression_probe(host_path)
    payload = json.loads(proc.stdout.strip())

    assert proc.returncode != 0, _process_debug(proc, "desktop array-subexpression repro")
    assert payload["ok"] is False
    assert payload["edition"] == "Desktop"
    assert payload["exception_type"] == "System.ArgumentException"
    assert payload["message"] == "Argument types do not match"


def test_powershell_core_records_generic_list_array_subexpression_behavior_when_available() -> None:
    host_path = _powershell_hosts().get("core")
    if host_path is None:
        pytest.skip("PowerShell Core is not available on this runner")

    proc = _run_list_subexpression_probe(host_path)
    payload = json.loads(proc.stdout.strip())

    assert payload["edition"] == "Core"
    if proc.returncode == 0:
        assert payload["ok"] is True
        assert payload["count"] == 1
    else:
        assert payload["ok"] is False
        assert payload["exception_type"] == "System.ArgumentException"
        assert payload["message"] == "Argument types do not match"


def test_mocked_apply_reproduces_historical_pre_backups_failure_before_mutation_on_desktop(tmp_path: Path) -> None:
    host_path = _powershell_hosts().get("desktop")
    if host_path is None:
        pytest.skip("Windows PowerShell Desktop is not available on this runner")

    reverted_source = _source().replace("        pre_backups = $preBackupArray", "        pre_backups = @($preBackups)", 1)
    assert reverted_source != _source()

    proc, summary, output_root = _run_mocked_apply(tmp_path, source_text=reverted_source, host_path=host_path)
    assert proc.returncode != 0, _process_debug(proc, "mocked historical apply failure")

    failure_reports = [
        payload
        for payload in _extract_json_lines(proc.stderr)
        if payload.get("report_type") == "lena_scheduler_legacy_to_canonical_driver_failure"
    ]
    assert len(failure_reports) == 1, _process_debug(proc, "mocked historical apply failure")
    failure = failure_reports[0]
    assert failure["stage_identifier"] == "receipt writing"
    assert failure["exception_type"] == "System.ArgumentException"
    assert failure["message"] == "Argument types do not match"
    assert failure["script_name"].endswith("mocked_apply_source.ps1")
    assert failure["script_line_number"] > 0
    assert failure["mutation_counters"] == {
        "scheduler_mutations_performed": 0,
        "task_start_operations_performed": 0,
        "task_enable_operations_performed": 0,
        "backup_writes_performed": 4,
        "receipt_writes_performed": 0,
    }
    assert SECRET_SENTINEL not in proc.stderr
    assert SECRET_SENTINEL not in proc.stdout

    operations = [entry["operation"] for entry in summary["operation_log"]]
    assert operations.count("Export-ScheduledTask") == 4
    assert "Register-ScheduledTask" not in operations
    assert "Disable-ScheduledTask" not in operations
    assert "Unregister-ScheduledTask" not in operations
    assert sorted(summary["remaining_task_names"]) == sorted(LEGACY_TASKS)

    run_root = _single_run_root(output_root)
    backup_names = sorted(path.name for path in run_root.glob("pre_*.xml"))
    assert backup_names == [
        "pre_Lena_Daily_Orchestrator.xml",
        "pre_Lena_Publish_Afternoon_Slot.xml",
        "pre_Lena_Publish_Evening_Slot.xml",
        "pre_Lena_Publish_Morning_Slot.xml",
    ]
    assert not (run_root / "migration_receipt.json").exists()
    assert not (run_root / "rollback_receipt.json").exists()


def test_mocked_apply_succeeds_with_stable_array_conversion_and_preserves_stage_order(tmp_path: Path) -> None:
    proc, summary, output_root = _run_mocked_apply(tmp_path)
    assert proc.returncode == 0, _process_debug(proc, "mocked apply success")

    run_root = _single_run_root(output_root)
    receipt = json.loads((run_root / "migration_receipt.json").read_text(encoding="utf-8-sig"))

    assert receipt["stage"] == "legacy_retired"
    assert receipt["legacy_tasks_removed"] == LEGACY_TASKS
    assert len(receipt["pre_backups"]) == 4
    assert receipt["canonical_post"]["task_name"] == CANONICAL_TASK_NAME
    assert "failure" not in receipt
    assert SECRET_SENTINEL not in json.dumps(receipt)
    assert not (run_root / "rollback_receipt.json").exists()

    operations = summary["operation_log"]
    register_index = next(
        index
        for index, entry in enumerate(operations)
        if entry["operation"] == "Register-ScheduledTask"
        and entry["task_name"] == CANONICAL_TASK_NAME
        and not entry["details"]["xml_mode"]
    )
    canonical_post_export_index = next(
        index
        for index, entry in enumerate(operations)
        if entry["operation"] == "Export-ScheduledTask" and entry["task_name"] == CANONICAL_TASK_NAME
    )
    first_unregister_index = next(
        index for index, entry in enumerate(operations) if entry["operation"] == "Unregister-ScheduledTask"
    )
    assert register_index < canonical_post_export_index < first_unregister_index

    export_entries = [entry for entry in operations if entry["operation"] == "Export-ScheduledTask"]
    assert all(entry["details"]["task_name_type"] == "System.String" for entry in export_entries)
    register_entry = operations[register_index]
    assert register_entry["details"]["action_type"] not in {
        "<null>",
        "System.Collections.Generic.List`1[System.Object]",
    }
    assert register_entry["details"]["trigger_type"] not in {
        "<null>",
        "System.Collections.Generic.List`1[System.Object]",
    }
    assert register_entry["details"]["trigger_interval"] == "PT1M"
    assert register_entry["details"]["trigger_has_repetition_duration"] is False
    assert register_entry["details"]["trigger_duration"] is None

    assert summary["remaining_task_names"] == [CANONICAL_TASK_NAME]
    assert len(summary["task_states"]) == 1
    assert summary["task_states"][0]["task_name"] == CANONICAL_TASK_NAME
    assert summary["task_states"][0]["enabled"] is False
    assert summary["task_states"][0]["state"] == "Disabled"
    _assert_trigger_contract(summary["canonical_xml"])
    assert "Start-ScheduledTask" not in json.dumps(summary)
    assert "Enable-ScheduledTask" not in json.dumps(summary)


def test_mocked_apply_failure_reports_stage_location_and_omits_secret_values(tmp_path: Path) -> None:
    proc, summary, output_root = _run_mocked_apply(tmp_path, failure_mode="throw_on_register")
    assert proc.returncode != 0, _process_debug(proc, "mocked apply structured failure")

    failure_reports = [
        payload
        for payload in _extract_json_lines(proc.stderr)
        if payload.get("report_type") == "lena_scheduler_legacy_to_canonical_driver_failure"
    ]
    assert len(failure_reports) == 1, _process_debug(proc, "mocked apply structured failure")
    failure = failure_reports[0]
    assert failure["stage_identifier"] == "canonical registration"
    assert failure["exception_type"] == "System.Exception"
    assert failure["message"] == "mock canonical registration failure"
    assert failure["script_name"].endswith("run_mocked_apply.ps1")
    assert failure["script_line_number"] > 0
    assert "mock canonical registration failure" in failure["line"]
    assert failure["inner_exceptions"] == [
        {
            "exception_type": "System.InvalidOperationException",
            "message": "mock inner failure",
        }
    ]
    assert failure["mutation_counters"] == {
        "scheduler_mutations_performed": 0,
        "task_start_operations_performed": 0,
        "task_enable_operations_performed": 0,
        "backup_writes_performed": 4,
        "receipt_writes_performed": 1,
    }
    assert SECRET_SENTINEL not in proc.stderr
    assert SECRET_SENTINEL not in proc.stdout

    run_root = _single_run_root(output_root)
    receipt = json.loads((run_root / "migration_receipt.json").read_text(encoding="utf-8-sig"))
    rollback = json.loads((run_root / "rollback_receipt.json").read_text(encoding="utf-8-sig"))
    assert receipt["failure"]["stage_identifier"] == "canonical registration"
    assert rollback["report_type"] == "lena_scheduler_legacy_to_canonical_driver_rollback_receipt"
    assert [item["task_name"] for item in rollback["restored_tasks"]] == LEGACY_TASKS
    assert sorted(summary["remaining_task_names"]) == sorted(LEGACY_TASKS)


def test_source_resolves_current_host_before_fallback_and_avoids_literal_child_powershell() -> None:
    source = _source()

    assert "function Resolve-CurrentPowerShellHost" in source
    assert "Get-Process -Id $PID" in source
    assert "$hostPath = Resolve-CurrentPowerShellHost" in source
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $registerScript" not in source
    assert "Invoke-PowerShellChildProcess" in source


def test_source_declares_desktop_and_core_powerShell_host_fallbacks() -> None:
    source = _source()

    assert "@('powershell.exe')" in source
    assert "@('pwsh', 'pwsh.exe')" in source
    assert 'Unable to resolve a valid PowerShell host for edition' in source


def test_dot_sourced_helper_reports_core_host_on_current_runtime() -> None:
    proc = _run_powershell_command(
        f". '{SCRIPT}'; Resolve-CurrentPowerShellHost | Write-Output"
    )
    assert proc.returncode == 0, _process_debug(proc, "current host resolver")
    assert proc.stdout.strip(), _process_debug(proc, "current host resolver")
    if sys.platform.startswith("win"):
        assert proc.stdout.strip().lower().endswith(("pwsh.exe", "powershell.exe"))
    else:
        assert proc.stdout.strip().lower().endswith("pwsh")


def test_dot_sourced_helper_fails_closed_when_no_host_can_be_resolved() -> None:
    proc = _run_powershell_command(
        f". '{SCRIPT}'; try {{ Resolve-CurrentPowerShellHost -CurrentProcessPath 'C:\\definitely-missing\\not-a-real-host.exe' -Edition Core -FallbackCandidates @('definitely-not-a-real-pwsh-host') | Out-Null; exit 0 }} catch {{ Write-Error $_.Exception.Message; exit 1 }}"
    )
    _assert_failed_process(proc, "missing host resolution", "Unable to resolve a valid PowerShell host")


def test_source_emits_stderr_summary_for_validate_only_blockers() -> None:
    source = _source()
    assert "Validate-only blockers:" in source


def test_source_requires_elevation_and_backups_before_mutation() -> None:
    source = _source()

    assert "Apply mode requires an elevated Administrator session." in source
    assert "backup_legacy_xml_before_change = $true" in source
    assert "[TimeSpan]::MaxValue" not in source
    assert INVALID_DURATION not in source
    assert source.index("$preBackups.Add((Export-TaskXmlToPath") < source.index("Register-ScheduledTask -TaskName $CanonicalTaskName")
    assert source.index("Register-ScheduledTask -TaskName $CanonicalTaskName") < source.index("Unregister-ScheduledTask -TaskName $spec.task_name -Confirm:$false")


def test_source_verifies_canonical_before_legacy_retirement_and_records_stages() -> None:
    source = _source()

    assert "pre_mutation_backups_complete" in source
    assert "canonical_registered_disabled" in source
    assert "legacy_retirement_started" in source
    assert "legacy_retired" in source
    assert "Canonical task verification failed: task is not disabled." in source
    assert "Canonical task verification failed: action mismatch after registration." in source
    assert "stage_identifier = $StageIdentifier" in source
    assert "backup-root preparation" in source
    assert "legacy-state verification" in source
    assert "backup hashing" in source
    assert "receipt writing" in source
    assert "rollback preparation" in source
    assert "Canonical trigger interval contract mismatch" in source
    assert "Canonical trigger duration contract mismatch" in source
    assert source.index("$receipt.stage = 'legacy_retirement_started'") < source.index("Unregister-ScheduledTask -TaskName $spec.task_name -Confirm:$false")


def test_source_has_no_task_enable_or_start_commands() -> None:
    source = _source()

    assert "Start-ScheduledTask" not in source
    assert "Enable-ScheduledTask" not in source
    assert "no_task_enable_or_start = $true" in source


def test_source_has_rollback_restore_contract() -> None:
    source = _source()

    assert "function Invoke-Rollback" in source
    assert "function Restore-TaskDefinitionDisabled" in source
    assert "Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null" in source
    assert "Disable-ScheduledTask -TaskName $TaskName | Out-Null" in source
    assert "rollback_receipt.json" in source
    assert "restore_legacy_disabled_commands" in source


def test_source_uses_stable_array_conversion_for_receipt_and_rollback_collections() -> None:
    source = _source()

    assert "function ConvertTo-StableArray" in source
    assert "pre_backups = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'pre_backups')" in source
    assert "legacy_tasks_removed = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'legacy_tasks_removed')" in source
    assert "changes = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'changes')" in source
    assert "post_state = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'post_state')" in source
    assert "restored_tasks = ConvertTo-StableArray -Value $restoreLog" in source
    assert "pre_backups = @($preBackups)" not in source
    assert "restored_tasks = @($restoreLog)" not in source


def test_source_structured_failure_report_omits_direct_secret_loading() -> None:
    source = _source()

    assert "function New-StructuredFailureReport" in source
    assert "fully_qualified_error_id = [string]$ErrorRecord.FullyQualifiedErrorId" in source
    assert "script_line_number = $invocation.ScriptLineNumber" in source
    assert "inner_exceptions = @(Get-InnerExceptionDetails -Exception $ErrorRecord.Exception)" in source
    assert "META_PAGE_ACCESS_TOKEN" not in source


def test_source_has_no_video_task_handling_or_provider_capability() -> None:
    source = _source()

    assert "Lena Video" not in source
    assert "no_video_task_touched = $true" in source
    assert "provider_calls = $false" in source
    assert "publishing = $false" in source
    assert "queue_mutation = $false" in source
    assert "media_generation = $false" in source
    assert "anthropic = $false" in source
    assert "Invoke-RestMethod" not in source
    assert "Invoke-WebRequest" not in source


def test_failed_execution_reports_process_details_instead_of_json_decode_noise(tmp_path: Path) -> None:
    proc = _run_powershell(
        "-File",
        str(SCRIPT),
        "-ValidateOnly",
        "-RepoRoot",
        str(ROOT),
        "-PythonExe",
        PYTHON_EXE,
        "-TaskSnapshotPath",
        str(tmp_path / "missing_snapshot.json"),
    )
    with_exception = None
    try:
        _assert_json_success(proc, "expected failing subprocess")
    except AssertionError as exc:
        with_exception = str(exc)
    assert with_exception is not None
    assert "returncode:" in with_exception
    assert "stderr:" in with_exception
    assert "stdout:" in with_exception
