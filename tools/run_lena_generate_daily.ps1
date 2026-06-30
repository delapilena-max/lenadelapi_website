param(
  [switch]$NoJitter
)

$ErrorActionPreference = "Stop"
if (-not $Root) {
  $Root = "C:\projects\ai\content_bot"
}
if (-not $Python) {
  $Python = Join-Path $Root ".venv\Scripts\python.exe"
}
Set-Location $Root

Set-Location "C:\projects\ai\content_bot"

$env:CONTENT_BOT_GENERATION_BACKEND = "kling_direct"
$env:CONTENT_BOT_FAL_KLING_ENABLED = "0"
$env:CONTENT_BOT_PUBLISH_BACKEND = "instagram_graph"
$env:CONTENT_BOT_KLING_DIRECT_ENABLED = "1"
$env:KLING_VIDEO_MODEL_NAME = "kling-v2-1-master"
$env:KLING_VIDEO_DURATION_SECONDS = "10"

# Target daily batch: 4 photos + 1 dance video.
# Video may require seed + video work, so allow several Kling jobs.
$env:CONTENT_BOT_KLING_MAX_SLOTS = "5"

$logDir = "C:\projects\ai\content_bot\pipeline\automation_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$transcript = Join-Path $logDir "lena_generate_direct_$stamp.txt"

Start-Transcript -Path $transcript -Force

try {
  if (-not $NoJitter) {
    $delayMinutes = Get-Random -Minimum 0 -Maximum 21
    Write-Host "Daily generation jitter delay: $delayMinutes minutes"
    Start-Sleep -Seconds ($delayMinutes * 60)
  } else {
    Write-Host "NoJitter enabled; starting generation immediately."
  }

  Write-Host "STEP 1: prepare daily workorders"
  & $Python ".\tools\lena_prepare_daily_workorders_brain.py"
  $PrepareExitCode = $LASTEXITCODE
  if ($PrepareExitCode -ne 0) {
    Write-Host ("Daily workorder preparation returned exit code {0}; attempting contract enforcement." -f $PrepareExitCode)
  }


  Write-Host "STEP 1A: validate Lena Influencer Node v1.3"
  & $Python ".\tools\lena_node_validate_v1_3.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Lena Influencer Node v1.3 validation failed."
  }

  Write-Host "STEP 1B: enforce daily workorder contract"
  $WorkorderPath = Join-Path $Root ("pipeline\kling_workorders\{0}\daily_workorders.json" -f (Get-Date -Format "yyyy-MM-dd"))
  & $Python ".\tools\lena_enforce_daily_workorder_contract.py" $WorkorderPath
  if ($LASTEXITCODE -ne 0) {
    throw "Daily workorder contract enforcement failed."
  }

  Write-Host "STEP 1C: Influencer Node v1.3"
  & $Python ".\tools\lena_influencer_node_v1_3.py" $WorkorderPath
  if ($LASTEXITCODE -ne 0) {
    throw "Influencer Node v1.3 failed."
  }


  Write-Host "STEP 1C2: apply growth layer v1.3.1"
  & $Python ".\tools\lena_apply_growth_layer_v1_3_1.py" $WorkorderPath
  if ($LASTEXITCODE -ne 0) {
    throw "Growth layer v1.3.1 failed."
  }

  Write-Host "STEP 1C3: apply growth monetization v1.4"
  & $Python ".\tools\lena_apply_reel_overlay_brief_v1_4.py" $WorkorderPath
  if ($LASTEXITCODE -ne 0) {
    throw "Growth Monetization v1.4 failed."
  }

  Write-Host "STEP 1D: credit guard v1.3"
  & $Python ".\tools\lena_credit_guard_v1_3.py" $WorkorderPath
  if ($LASTEXITCODE -ne 0) {
    throw "Lena credit guard failed; generation blocked before Kling spend."
  }

  Write-Host "STEP 2: run Kling direct executor"
  & $Python ".\tools\run_lena_kling_direct.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Kling direct executor failed."
  }

  Write-Host "STEP 3: package Kling outputs"
  & $Python ".\tools\lena_package_kling_outputs.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Kling output packaging failed."
  }

  Write-Host "STEP 4: preflight"
  & $Python ".\tools\lena_preflight.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Lena preflight failed."
  }

  Write-Host "Generation chain complete."
}
finally {
  Stop-Transcript
}
