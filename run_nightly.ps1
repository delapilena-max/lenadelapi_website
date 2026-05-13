# run_nightly.ps1 - Nightly batch trigger for AI Lady node

Set-Location "C:\projects\ai\content_bot"

$envFile = ".\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.+)\s*$") {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
} else {
    Write-Error ".env file not found — aborting"
    exit 1
}

$python  = "C:\projects\ai\content_bot\.venv\Scripts\python.exe"
$script  = "C:\projects\ai\content_bot\batch_render.py"
$logFile = "C:\projects\ai\content_bot\nightly_run.log"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $logFile "[$timestamp] Nightly batch started"

& $python $script 2>&1 | Tee-Object -Append $logFile

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $logFile "[$timestamp] Nightly batch finished"
