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
    $bootstrap = @'
import os
import runpy
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
os.chdir(repo_root)
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from tools.publishers import lena_meta_publish_common_v2_9 as publish_common

publish_common.populate_process_env_from_canonical_secret_source(repo_root)
# Drop the wrapper's repo-root bootstrap argument before the driver
# module enters argparse under runpy.
sys.argv = ["tools.lena_autonomy_scheduler_driver_v1"]
runpy.run_module("tools.lena_autonomy_scheduler_driver_v1", run_name="__main__")
'@
    $output = $bootstrap | & $PythonExe - $RepoRoot 2>&1
    $exitCode = $LASTEXITCODE
    $output | Add-Content -Path $logPath -Encoding utf8
    "[$stamp] exit code $exitCode" | Add-Content -Path $logPath -Encoding utf8
    exit $exitCode
}
catch {
    "[$stamp] wrapper error: $($_.Exception.Message)" | Add-Content -Path $logPath -Encoding utf8
    exit 1
}
