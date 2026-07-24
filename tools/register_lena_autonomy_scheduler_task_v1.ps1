<#
.SYNOPSIS
    Registers the ONE Windows Scheduled Task that drives Lena's controlled
    photo autonomy: fires every minute, invokes the idempotent Python
    scheduler driver, which itself decides whether anything is due.

.DESCRIPTION
    Deliberately does NOT create three fixed-time tasks -- the actual
    posting minute is deterministically varied per day (see
    tools/lena_autonomy_daily_schedule_v1.py), so there is no single
    fixed clock time to register three tasks against. Instead this
    registers one task that polls every minute; the driver is a no-op on
    every poll except the ~6 minutes a day (3 slots x ~2 state
    transitions) where something is actually due.

    LogonType S4U runs the task under the given user account, whether or
    not that user is logged on, WITHOUT storing a password (S4U requires
    no credential). This script never prompts for or stores a password.

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

.EXAMPLE
    # Register (creates the task DISABLED -- enable explicitly when ready):
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\register_lena_autonomy_scheduler_task_v1.ps1

    # Enable when ready to go fully autonomous:
    Enable-ScheduledTask -TaskName 'Lena Autonomy Scheduler Driver'

    # Verify:
    Get-ScheduledTask -TaskName 'Lena Autonomy Scheduler Driver' | Select-Object TaskName, State
    Get-ScheduledTaskInfo -TaskName 'Lena Autonomy Scheduler Driver'

    # Remove:
    Unregister-ScheduledTask -TaskName 'Lena Autonomy Scheduler Driver' -Confirm:$false
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'Lena Autonomy Scheduler Driver',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonExe = 'C:\Python314\python.exe',
    [string]$UserId = "$env:USERDOMAIN\$env:USERNAME",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$wrapperPath = Join-Path $RepoRoot 'tools\lena_autonomy_scheduler_driver_run_v1.ps1'
if (-not (Test-Path $wrapperPath)) {
    Write-Error "Run wrapper not found: $wrapperPath"
    exit 1
}

$argumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperPath`" -PythonExe `"$PythonExe`" -RepoRoot `"$RepoRoot`""

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument $argumentList `
    -WorkingDirectory $RepoRoot

# Fires once "now", then repeats every minute forever -- the deterministic
# per-day publish minute lives inside the driver, not in this trigger.
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
        -TaskName    $TaskName `
        -Description 'Polls every minute; runs Lena controlled-photo-autonomy generation/publish only at each deterministic daily slot time. Idempotent no-op otherwise.' `
        -Action      $action `
        -Trigger     $trigger `
        -Principal   $principal `
        -Settings    $settings `
        -Force:$Force | Out-Null

    Write-Host "Registered task: $TaskName"
    Write-Host 'Task is created ENABLED per Register-ScheduledTask defaults; run:'
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
    Write-Host 'to confirm state, and Disable-ScheduledTask if you want it inert until you are ready.'
}
else {
    Write-Host "[WhatIf] Would register: $TaskName"
}
