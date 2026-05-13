# create_task.ps1 - Register AI Lady nightly batch as a Windows Scheduled Task
# Run ONCE from an Admin PowerShell window.

$taskName    = "AILady_NightlyBatch"
$scriptPath  = "C:\projects\ai\content_bot\run_nightly.ps1"
$triggerTime = "03:00AM"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing task: $taskName"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory "C:\projects\ai\content_bot"

$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host ""
Write-Host "Task '$taskName' registered. Fires daily at $triggerTime"
Write-Host "Logs -> C:\projects\ai\content_bot\nightly_run.log"
Write-Host ""
Write-Host "Test immediately : Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Remove task      : Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
