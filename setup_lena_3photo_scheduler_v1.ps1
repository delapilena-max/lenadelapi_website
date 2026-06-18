<#
.SYNOPSIS
    Creates four Lena 3-photo/day Windows Scheduled Tasks, all DISABLED by default.

.DESCRIPTION
    Task schedule:
      06:30 AM  Lena Daily Orchestrator     - generate, approve, packets, queue build
      09:00 AM  Lena Publish Morning Slot   - post morning slot to IG + FB
      02:00 PM  Lena Publish Afternoon Slot
      07:30 PM  Lena Publish Evening Slot

    All tasks are created DISABLED. Nothing runs automatically after this script.
    Enable individually when ready for go-live.

.NOTES
    Must run as Administrator (required for Register-ScheduledTask).
    Re-run with -Force to overwrite existing tasks.

.PARAMETER Force
    Overwrite tasks if they already exist.

.EXAMPLE
    # Syntax validation only - does not register anything:
    powershell.exe -NoProfile -Command "& { $null = [System.Management.Automation.Language.Parser]::ParseFile('setup_lena_3photo_scheduler_v1.ps1', [ref]$null, [ref]$null) }"

    # Register all four tasks (disabled) - must be Admin:
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File setup_lena_3photo_scheduler_v1.ps1

    # Enable tasks individually when approved for go-live:
    #   Enable-ScheduledTask -TaskName 'Lena Daily Orchestrator'
    #   Enable-ScheduledTask -TaskName 'Lena Publish Morning Slot'
    #   Enable-ScheduledTask -TaskName 'Lena Publish Afternoon Slot'
    #   Enable-ScheduledTask -TaskName 'Lena Publish Evening Slot'

    # Verify task states:
    #   Get-ScheduledTask | Where-Object { $_.TaskName -like 'Lena *' } |
    #       Select-Object TaskName, State | Format-Table -AutoSize

    # Remove all four tasks if needed:
    #   foreach ($n in @('Lena Daily Orchestrator','Lena Publish Morning Slot','Lena Publish Afternoon Slot','Lena Publish Evening Slot')) {
    #       Unregister-ScheduledTask -TaskName $n -Confirm:$false
    #   }
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Paths ─────────────────────────────────────────────────────────────────────
$ROOT   = 'C:\projects\ai\content_bot'
$PYTHON = "$ROOT\.venv\Scripts\python.exe"
$LOGDIR = "$ROOT\logs\scheduler"

# ── Guard: must be Administrator ──────────────────────────────────────────────
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'This script must be run as Administrator to register Scheduled Tasks.'
    exit 1
}

# ── Ensure log directory exists ───────────────────────────────────────────────
if (-not (Test-Path $LOGDIR)) {
    New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null
    Write-Host "Created log directory: $LOGDIR"
}

# ── Helper ────────────────────────────────────────────────────────────────────
function Register-LenaTask {
    param(
        [string]$Name,
        [string]$Description,
        $Action,
        $Trigger
    )

    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
        -StartWhenAvailable `
        -MultipleInstances  IgnoreNew `
        -WakeToRun:$false

    if ($PSCmdlet.ShouldProcess($Name, 'Register-ScheduledTask')) {
        Register-ScheduledTask `
            -TaskName    $Name `
            -Description $Description `
            -Action      $Action `
            -Trigger     $Trigger `
            -Settings    $settings `
            -Force:$Force | Out-Null

        Disable-ScheduledTask -TaskName $Name | Out-Null
        Write-Host "  [CREATED DISABLED]  $Name"
    }
    else {
        Write-Host "  [WhatIf] Would create (disabled): $Name"
    }
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '========================================================'
Write-Host '  Lena 3-photo/day Scheduler Setup v1'
Write-Host '  All tasks created DISABLED. Nothing runs yet.'
Write-Host "  Root: $ROOT"
Write-Host '========================================================'
Write-Host ''

# ── Task 1: Daily Orchestrator (06:30 AM) ─────────────────────────────────────
# Runs lena_daily_orchestrator_v1.py: Kling generation, approval gate,
# packet director, queue build. Enable only when autonomous generation approved.
#   Enable-ScheduledTask -TaskName 'Lena Daily Orchestrator'
Register-LenaTask `
    -Name        'Lena Daily Orchestrator' `
    -Description 'Lena daily: Kling 3-photo generation, approval gate, packets, queue build. DISABLED.' `
    -Action      (New-ScheduledTaskAction `
        -Execute          $PYTHON `
        -Argument         'tools\lena_daily_orchestrator_v1.py' `
        -WorkingDirectory $ROOT) `
    -Trigger     (New-ScheduledTaskTrigger -Daily -At '06:30AM')

# ── Task 2: Morning Publish (09:00 AM) ────────────────────────────────────────
# Posts morning slot to Instagram Feed + Facebook Page via BAT wrapper.
#   Enable-ScheduledTask -TaskName 'Lena Publish Morning Slot'
$morningBat = '/c "' + $ROOT + '\RUN_LENA_PUBLISH_MORNING_SLOT.bat"'
Register-LenaTask `
    -Name        'Lena Publish Morning Slot' `
    -Description 'Lena morning publish slot (Instagram Feed + Facebook Page). DISABLED.' `
    -Action      (New-ScheduledTaskAction `
        -Execute          'cmd.exe' `
        -Argument         $morningBat `
        -WorkingDirectory $ROOT) `
    -Trigger     (New-ScheduledTaskTrigger -Daily -At '09:00AM')

# ── Task 3: Afternoon Publish (02:00 PM) ──────────────────────────────────────
#   Enable-ScheduledTask -TaskName 'Lena Publish Afternoon Slot'
$afternoonBat = '/c "' + $ROOT + '\RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat"'
Register-LenaTask `
    -Name        'Lena Publish Afternoon Slot' `
    -Description 'Lena afternoon publish slot (Instagram Feed + Facebook Page). DISABLED.' `
    -Action      (New-ScheduledTaskAction `
        -Execute          'cmd.exe' `
        -Argument         $afternoonBat `
        -WorkingDirectory $ROOT) `
    -Trigger     (New-ScheduledTaskTrigger -Daily -At '02:00PM')

# ── Task 4: Evening Publish (07:30 PM) ────────────────────────────────────────
#   Enable-ScheduledTask -TaskName 'Lena Publish Evening Slot'
$eveningBat = '/c "' + $ROOT + '\RUN_LENA_PUBLISH_EVENING_SLOT.bat"'
Register-LenaTask `
    -Name        'Lena Publish Evening Slot' `
    -Description 'Lena evening publish slot (Instagram Feed + Facebook Page). DISABLED.' `
    -Action      (New-ScheduledTaskAction `
        -Execute          'cmd.exe' `
        -Argument         $eveningBat `
        -WorkingDirectory $ROOT) `
    -Trigger     (New-ScheduledTaskTrigger -Daily -At '07:30PM')

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Done. Four tasks created, all DISABLED.'
Write-Host ''
Write-Host 'To verify:'
Write-Host "  Get-ScheduledTask | Where-Object { `$_.TaskName -like 'Lena *' } | Select-Object TaskName, State | Format-Table -AutoSize"
Write-Host ''
Write-Host 'To enable (one at a time, when approved):'
Write-Host "  Enable-ScheduledTask -TaskName 'Lena Daily Orchestrator'"
Write-Host "  Enable-ScheduledTask -TaskName 'Lena Publish Morning Slot'"
Write-Host "  Enable-ScheduledTask -TaskName 'Lena Publish Afternoon Slot'"
Write-Host "  Enable-ScheduledTask -TaskName 'Lena Publish Evening Slot'"
Write-Host ''
