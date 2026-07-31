<#
.SYNOPSIS
    Compatibility wrapper for the retired three-task Lena scheduler setup.

.DESCRIPTION
    The old fixed publish-slot task architecture is retired. The
    canonical scheduler is a single Windows task named
    'Lena Autonomy Scheduler Driver' that invokes the repository-local
    driver wrapper once per minute.

    This compatibility surface is fail-closed for any live scheduler
    mutation. In validate-only mode it delegates to the canonical
    registration-plan generator so older references can still emit the
    current one-task plan without touching Task Scheduler.
#>

[CmdletBinding()]
param(
    [string]$TaskName = 'Lena Autonomy Scheduler Driver',
    [string]$PythonExe = 'C:\Python314\python.exe',
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$CanonicalScript = Join-Path $RepoRoot 'tools\register_lena_autonomy_scheduler_task_v1.ps1'

if (-not (Test-Path -LiteralPath $CanonicalScript -PathType Leaf)) {
    Write-Error "Canonical scheduler registration script not found: $CanonicalScript"
    exit 1
}

if (-not $ValidateOnly) {
    Write-Error (
        "setup_lena_3photo_scheduler_v1.ps1 is retired. Use tools\register_lena_autonomy_scheduler_task_v1.ps1 " +
        "for the canonical single-task scheduler surface. Re-run this retired wrapper with -ValidateOnly only."
    )
    exit 1
}

& $CanonicalScript -ValidateOnly -TaskName $TaskName -RepoRoot $RepoRoot -PythonExe $PythonExe
exit $LASTEXITCODE
