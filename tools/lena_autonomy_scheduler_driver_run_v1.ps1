<#
.SYNOPSIS
    Single invocation wrapper for tools/lena_autonomy_scheduler_driver_v1.py.

.DESCRIPTION
    This is the command the "Lena Autonomy Scheduler Driver" Windows
    Scheduled Task actually runs, once per minute. It does no scheduling
    logic itself -- the Python driver decides whether anything is due.
    This wrapper only:
      - fixes the working directory to the repository root, so the
        driver's own package-relative imports (`from tools import ...`)
        resolve correctly regardless of how Task Scheduler invokes it;
      - runs the driver via `-m` (module mode), matching how it is
        invoked in every test and manual run in this repo;
      - appends timestamped stdout/stderr to a per-day log file so a
        once-a-minute background task leaves an inspectable trail;
      - never echoes environment variables or file contents, so no
        credential ever reaches the log.

.PARAMETER PythonExe
    Path to the credentialed Python interpreter. Defaults to the
    interpreter this repository's tests and manual runs have used
    (C:\Python314\python.exe, with tzdata installed for zoneinfo).

.PARAMETER RepoRoot
    Repository root to run from. Defaults to this script's own
    grandparent directory (tools/.. ) so the wrapper works regardless of
    where it is copied from, as long as it stays inside the repo.
#>

param(
    [string]$PythonExe = 'C:\Python314\python.exe',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location -Path $RepoRoot

$logDir = Join-Path $RepoRoot 'logs\scheduler'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logPath = Join-Path $logDir ("lena_autonomy_scheduler_{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

$stamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')
"[$stamp] invoking driver" | Add-Content -Path $logPath -Encoding utf8

try {
    $output = & $PythonExe -m tools.lena_autonomy_scheduler_driver_v1 2>&1
    $exitCode = $LASTEXITCODE
    $output | Add-Content -Path $logPath -Encoding utf8
    "[$stamp] exit code $exitCode" | Add-Content -Path $logPath -Encoding utf8
    exit $exitCode
}
catch {
    "[$stamp] wrapper error: $($_.Exception.Message)" | Add-Content -Path $logPath -Encoding utf8
    exit 1
}
