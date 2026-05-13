# backup_labels.ps1 - copy review_labels.json to logs\backups with timestamp
 = 'C:\projects\ai\content_bot\logs\review_labels.json'
 = 'C:\projects\ai\content_bot\logs\backups'
if(-not (Test-Path )){ Write-Host 'NO_LABELS' ; exit 0 }
 = (Get-Date).ToString('yyyyMMddTHHmmss')
 = Join-Path  ("review_labels_.json")
Copy-Item -Path  -Destination  -Force
Write-Host "BACKED_UP "
