@'
# run_poster.ps1
$ErrorActionPreference = "Stop"
# Change to the directory where this script lives
Set-Location -Path $PSScriptRoot

# Environment overrides (edit if you want different defaults)
$env:POSTER_HEADLESS = "true"
$env:POSTER_CONFIDENCE_THRESHOLD = "0.8"

# Ensure logs directory exists
$logDir = Join-Path $PSScriptRoot "nodes\ai_lady_instagram\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

# Run the poster (use full python path if needed)
python nodes\ai_lady_instagram\poster_retry.py "A day in the life" >> (Join-Path $logDir "scheduled_run.log") 2>&1

exit $LASTEXITCODE
'@ | Out-File -FilePath .\run_poster.ps1 -Encoding utf8 -Force

# Run the wrapper immediately (non-elevated)
powershell -ExecutionPolicy Bypass -File .\run_poster.ps1
