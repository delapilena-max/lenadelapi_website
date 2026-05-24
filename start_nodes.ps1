# start_nodes.ps1
$venvPython = ".\.venv\Scripts\python.exe"
$script = ".\nodes\ai_lady_instagram\poster_selenium_run.py"
$video = "C:\full\path\to\video.mp4"
$caption = "Automated post from node"

# number of nodes
$nodes = 5
$baseProfile = ".\nodes\profiles"
New-Item -ItemType Directory -Path $baseProfile -Force | Out-Null

# create profile folders if missing
for ($i=1; $i -le $nodes; $i++) {
    $p = Join-Path $baseProfile ("node" + $i)
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

# function to start a node process
function Start-Node($i) {
    $profile = Join-Path $baseProfile ("node" + $i)
    $log = Join-Path (Resolve-Path ".\logs") ("node" + $i + ".supervisor.log")
    $args = "$script `"$profile`" `"$video`" `"$caption`""
    $startInfo = @{
        FilePath = $venvPython
        ArgumentList = $args
        RedirectStandardOutput = $true
        RedirectStandardError = $true
        NoNewWindow = $false
    }
    $proc = Start-Process @startInfo -PassThru
    "$((Get-Date).ToString()) Started node $i PID $($proc.Id)" | Out-File -FilePath $log -Append
    return @{ Proc = $proc; Profile = $profile; Log = $log; Attempts = 0 }
}

# start nodes staggered
$nodesState = @()
for ($i=1; $i -le $nodes; $i++) {
    $state = Start-Node $i
    $nodesState += $state
    Start-Sleep -Seconds 45
}

# monitor loop: restart failed processes up to 3 times
while ($true) {
    for ($idx=0; $idx -lt $nodesState.Count; $idx++) {
        $s = $nodesState[$idx]
        if ($s.Proc.HasExited) {
            $exit = $s.Proc.ExitCode
            $msg = "$((Get-Date).ToString()) Node $($idx+1) exited with code $exit (attempts $($s.Attempts))"
            $msg | Out-File -FilePath $s.Log -Append
            if ($s.Attempts -lt 3) {
                $s.Attempts++
                $backoff = [math]::Pow(2, $s.Attempts) * 10
                "$((Get-Date).ToString()) Restarting node $($idx+1) after $backoff seconds" | Out-File -FilePath $s.Log -Append
                Start-Sleep -Seconds $backoff
                $new = Start-Node ($idx+1)
                $nodesState[$idx] = $new
            } else {
                "$((Get-Date).ToString()) Node $($idx+1) reached max attempts. Not restarting." | Out-File -FilePath $s.Log -Append
            }
        }
    }
    Start-Sleep -Seconds 20
}
