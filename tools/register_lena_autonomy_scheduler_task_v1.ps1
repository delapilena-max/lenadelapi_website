<#
.SYNOPSIS
    Registers the one canonical Windows Scheduled Task that drives Lena's
    controlled photo autonomy scheduler.

.DESCRIPTION
    The canonical scheduler architecture is a single driver task that
    fires every minute and lets the Python driver decide whether any
    morning, afternoon, or evening transition is due. This script can
    emit a non-mutating registration plan or register the task itself.

    Validate-only mode never touches Task Scheduler. It emits the exact
    single-task plan as JSON so source and deployment validation can stay
    read-only.

.PARAMETER TaskName
    Scheduled task name. Defaults to 'Lena Autonomy Scheduler Driver'.

.PARAMETER RepoRoot
    Repository root the task's action runs from. Defaults to this
    script's own grandparent directory.

.PARAMETER PythonExe
    Credentialed Python interpreter path, forwarded to the run wrapper.

.PARAMETER UserId
    Account the task runs as (S4U, no stored password). Defaults to the
    account currently registering the task.

.PARAMETER Force
    Overwrite an existing task with the same name.

.PARAMETER ValidateOnly
    Emit the canonical single-task registration plan as JSON and exit
    without touching Task Scheduler.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'Lena Autonomy Scheduler Driver',
    [string]$RepoRoot = '',
    [string]$PythonExe = 'C:\Python314\python.exe',
    [string]$UserId = "$env:USERDOMAIN\$env:USERNAME",
    [switch]$Force,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
}
else {
    $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
}
$WrapperPath = Join-Path $RepoRoot 'tools\lena_autonomy_scheduler_driver_run_v1.ps1'
$DriverModulePath = Join-Path $RepoRoot 'tools\lena_autonomy_scheduler_driver_v1.py'

if (-not (Test-Path -LiteralPath $WrapperPath -PathType Leaf)) {
    Write-Error "Canonical scheduler wrapper not found: $WrapperPath"
    exit 1
}

if (-not (Test-Path -LiteralPath $DriverModulePath -PathType Leaf)) {
    Write-Error "Canonical scheduler driver module not found: $DriverModulePath"
    exit 1
}

$ArgumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$WrapperPath`" -PythonExe `"$PythonExe`" -RepoRoot `"$RepoRoot`""

$Plan = [ordered]@{
    report_type = 'lena_autonomy_scheduler_task_registration_plan'
    schema_version = 'v1'
    task_count = 1
    task_name = $TaskName
    disabled_by_default = $true
    repo_root = $RepoRoot
    python_exe = $PythonExe
    run_wrapper_path = $WrapperPath
    driver_module_path = $DriverModulePath
    action = [ordered]@{
        execute = 'powershell.exe'
        arguments = $ArgumentList
        working_directory = $RepoRoot
    }
    trigger = [ordered]@{
        type = 'poll_every_minute'
        repetition_interval_minutes = 1
        scheduling_decision = 'driver_internal'
        schedule_slots = @('morning', 'afternoon', 'evening')
    }
    safeguards = [ordered]@{
        no_daily_orchestrator = $true
        no_fixed_publish_slot_tasks = $true
        no_video_task = $true
    }
}

if ($ValidateOnly) {
    $Plan | ConvertTo-Json -Depth 6
    exit 0
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument $ArgumentList `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType S4U `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -WakeToRun:$false

if ($PSCmdlet.ShouldProcess($TaskName, 'Register-ScheduledTask')) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Description 'Polls every minute and lets the Lena autonomy scheduler driver decide whether a photo generation or publish transition is due.' `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Force:$Force | Out-Null

    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    Write-Host "Registered canonical task and forced disabled state: $TaskName"
}
else {
    Write-Host "[WhatIf] Would register canonical disabled-by-default task: $TaskName"
}
