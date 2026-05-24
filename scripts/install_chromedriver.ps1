Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$driversDir = Join-Path -Path $PSScriptRoot -ChildPath "..\drivers"
if (-not (Test-Path $driversDir)) { New-Item -ItemType Directory -Path $driversDir -Force | Out-Null }

function Get-ChromeVersion {
    $paths = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            try { return (& "$p" --version) -replace 'Google Chrome\s*','' }
            catch { }
        }
    }

    $found = Get-ChildItem "C:\Program Files","C:\Program Files (x86)" -Recurse -Filter chrome.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        try { return (& "$($found.FullName)" --version) -replace 'Google Chrome\s*','' }
        catch { }
    }

    try {
        $reg = Get-Item "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue
        if ($reg) { return $reg.VersionInfo.FileVersion }
    } catch { }

    return $null
}

$chromeVer = Get-ChromeVersion
if (-not $chromeVer) {
    Write-Host "Could not auto-detect Chrome. Open Chrome -> chrome://version and paste the version (e.g. 114.0.5735.199)."
    $chromeVer = Read-Host "Paste Chrome version"
    if (-not $chromeVer) { Write-Error "No Chrome version provided. Exiting."; exit 1 }
}

$major = $chromeVer.Split('.')[0]
Write-Host "Detected Chrome version: $chromeVer (major: $major)"

$latestUrl = "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$major"
try {
    $release = Invoke-RestMethod -Uri $latestUrl -UseBasicParsing
} catch {
    Write-Error "Could not resolve ChromeDriver release for major version $major. Check your internet connection or paste a valid Chrome version."
    exit 1
}
Write-Host "Resolved ChromeDriver release: $release"

$zipUrl = "https://chromedriver.storage.googleapis.com/$release/chromedriver_win32.zip"
$zipPath = Join-Path $driversDir "chromedriver_$release.zip"

Write-Host "Downloading $zipUrl ..."
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

Write-Host "Extracting to $driversDir ..."
Expand-Archive -Path $zipPath -DestinationPath $driversDir -Force
Remove-Item $zipPath -Force

$driverExe = Join-Path $driversDir "chromedriver.exe"
if (-not (Test-Path $driverExe)) {
    Write-Error "chromedriver.exe not found after extraction."
    exit 1
}

Write-Host "Chromedriver installed at: $driverExe"
& "$driverExe" --version
Write-Host "Done. To use the driver in the poster script set CHROMEDRIVER_PATH to the above path or leave default .\drivers\chromedriver.exe"
