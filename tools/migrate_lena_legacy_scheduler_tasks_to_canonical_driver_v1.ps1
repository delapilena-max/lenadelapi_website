<#
.SYNOPSIS
    Prepare or apply the disabled migration from four legacy Lena photo
    scheduler tasks to the canonical single driver task.

.DESCRIPTION
    This script is intentionally fail-closed.
    Validate-only mode emits a JSON plan and never touches Task Scheduler,
    writes no receipts, exports no XML, creates no backups, and performs
    zero task mutations.

    Apply mode requires an elevated Administrator session, verifies the
    exact disabled legacy task state, exports legacy XML before any
    mutation, records XML hashes, creates or updates exactly one disabled
    canonical task, verifies the canonical disabled state, and only then
    retires the legacy tasks. If a cryptographically bound prior receipt
    proves an authorized resumable state, apply mode resumes
    deterministically from that state. Rollback restores all four legacy
    definitions disabled.

.PARAMETER RepoRoot
    Canonical repository root. Defaults to the script's own grandparent
    directory.

.PARAMETER PythonExe
    Canonical deployment interpreter path.

.PARAMETER OutputRoot
    Root directory for apply-mode backups and receipts. Must resolve
    outside the repository root.

.PARAMETER ValidateOnly
    Emit the migration plan JSON without writing files or mutating Task
    Scheduler.

.PARAMETER Apply
    Execute the migration after all guards pass.

.PARAMETER TaskSnapshotPath
    Optional JSON snapshot used for validate-only tests instead of live
    Task Scheduler queries.

.PARAMETER PriorReceiptPath
    Optional receipt from a prior interrupted migration attempt. The
    receipt must match this script's contract hash and governed XML
    backup hashes before any resumable state is trusted.
#>

[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$PythonExe = 'C:\Python314\python.exe',
    [string]$OutputRoot = '',
    [switch]$ValidateOnly,
    [switch]$Apply,
    [string]$TaskSnapshotPath = '',
    [string]$PriorReceiptPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ValidateOnly -and -not $Apply) {
    $ValidateOnly = $true
}
if ($ValidateOnly -and $Apply) {
    Write-Error 'Specify exactly one of -ValidateOnly or -Apply.'
    exit 1
}

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
}
else {
    $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
}

$CanonicalTaskName = 'Lena Autonomy Scheduler Driver'
$LegacyRepoRoot = 'C:\projects\ai\lenadelapi_website_autopublish_fix'
$LegacyPrincipal = [ordered]@{
    user_id = 'Nicolas'
    logon_type = 'Interactive'
    run_level = 'Limited'
}
$LegacySpecs = @(
    [ordered]@{
        task_name = 'Lena Daily Orchestrator'
        state = 'Disabled'
        execute = 'C:\Python314\python.exe'
        arguments = 'tools\lena_daily_orchestrator_v1.py'
        working_directory = $LegacyRepoRoot
        principal = $LegacyPrincipal
    },
    [ordered]@{
        task_name = 'Lena Publish Morning Slot'
        state = 'Disabled'
        execute = 'cmd.exe'
        arguments = "/c `"$LegacyRepoRoot\RUN_LENA_PUBLISH_MORNING_SLOT.bat`""
        working_directory = $LegacyRepoRoot
        principal = $LegacyPrincipal
    },
    [ordered]@{
        task_name = 'Lena Publish Afternoon Slot'
        state = 'Disabled'
        execute = 'cmd.exe'
        arguments = "/c `"$LegacyRepoRoot\RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat`""
        working_directory = $LegacyRepoRoot
        principal = $LegacyPrincipal
    },
    [ordered]@{
        task_name = 'Lena Publish Evening Slot'
        state = 'Disabled'
        execute = 'cmd.exe'
        arguments = "/c `"$LegacyRepoRoot\RUN_LENA_PUBLISH_EVENING_SLOT.bat`""
        working_directory = $LegacyRepoRoot
        principal = $LegacyPrincipal
    }
)
$AllowedResumeStages = @(
    'canonical_registered_disabled',
    'legacy_retirement_started',
    'legacy_retired'
)

function ConvertTo-CanonicalJson {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Value,
        [int]$Depth = 12
    )
    return ($Value | ConvertTo-Json -Depth $Depth -Compress)
}

function Get-Sha256Hex {
    param([string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-XmlSha256 {
    param([string]$XmlText)
    return Get-Sha256Hex -Text $XmlText
}

function Test-IsPathWithinRoot {
    param([string]$Path, [string]$Root)
    if (-not $Path -or -not $Root) {
        return $false
    }
    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    return $fullPath.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or $fullPath.Equals($fullRoot, [StringComparison]::OrdinalIgnoreCase)
}

function Resolve-OutputRoot {
    if ($OutputRoot) {
        return [IO.Path]::GetFullPath($OutputRoot)
    }
    if ($env:LOCALAPPDATA) {
        return [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'LenaSchedulerMigration'))
    }
    if ($env:TEMP) {
        return [IO.Path]::GetFullPath((Join-Path $env:TEMP 'LenaSchedulerMigration'))
    }
    throw 'Unable to resolve an output root outside the repository.'
}

function Resolve-PowerShellHostCandidate {
    param([string]$Candidate)
    if (-not $Candidate) {
        return $null
    }
    if ([IO.Path]::IsPathRooted($Candidate)) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return [IO.Path]::GetFullPath($Candidate)
        }
        return $null
    }
    $command = Get-Command -Name $Candidate -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $command -or -not $command.Source) {
        return $null
    }
    return [string]$command.Source
}

function Resolve-CurrentPowerShellHost {
    param(
        [string]$CurrentProcessPath = '',
        [string]$Edition = '',
        [string[]]$FallbackCandidates = @()
    )
    if (-not $CurrentProcessPath) {
        try {
            $process = Get-Process -Id $PID -ErrorAction Stop
            if ($process.Path) {
                $CurrentProcessPath = [string]$process.Path
            }
        }
        catch {
            $CurrentProcessPath = ''
        }
    }
    $resolvedCurrent = Resolve-PowerShellHostCandidate -Candidate $CurrentProcessPath
    if ($resolvedCurrent) {
        return $resolvedCurrent
    }
    if (-not $Edition) {
        $Edition = [string]$PSVersionTable.PSEdition
    }
    $candidates = @()
    if (@($FallbackCandidates).Count -gt 0) {
        $candidates = @($FallbackCandidates)
    }
    elseif ($Edition -eq 'Desktop') {
        $candidates = @('powershell.exe')
    }
    else {
        $candidates = @('pwsh', 'pwsh.exe')
    }
    foreach ($candidate in $candidates) {
        $resolved = Resolve-PowerShellHostCandidate -Candidate $candidate
        if ($resolved) {
            return $resolved
        }
    }
    $candidateText = if ($candidates.Count -gt 0) { $candidates -join ', ' } else { '<none>' }
    throw "Unable to resolve a valid PowerShell host for edition '$Edition'. CurrentProcessPath='$CurrentProcessPath'; candidates=$candidateText"
}

function Invoke-PowerShellChildProcess {
    param(
        [string]$HostPath,
        [string]$WorkingDirectory,
        [string]$FilePath,
        [string[]]$Arguments = @()
    )
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        Push-Location -LiteralPath $WorkingDirectory
        try {
            & $HostPath -NoProfile -ExecutionPolicy Bypass -File $FilePath @Arguments 1> $stdoutPath 2> $stderrPath
            $exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
        }
        finally {
            Pop-Location
        }
        return [ordered]@{
            host_path = $HostPath
            exit_code = $exitCode
            stdout = [IO.File]::ReadAllText($stdoutPath)
            stderr = [IO.File]::ReadAllText($stderrPath)
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-CanonicalPlan {
    $registerScript = Join-Path $RepoRoot 'tools\register_lena_autonomy_scheduler_task_v1.ps1'
    if (-not (Test-Path -LiteralPath $registerScript -PathType Leaf)) {
        throw "Canonical registration script not found: $registerScript"
    }
    $hostPath = Resolve-CurrentPowerShellHost
    $result = Invoke-PowerShellChildProcess -HostPath $hostPath -WorkingDirectory $RepoRoot -FilePath $registerScript -Arguments @('-ValidateOnly', '-RepoRoot', $RepoRoot, '-PythonExe', $PythonExe)
    if ($result.exit_code -ne 0) {
        throw ("Canonical registration plan generation failed via '{0}' with exit code {1}. stderr: {2} stdout: {3}" -f $result.host_path, $result.exit_code, $result.stderr.Trim(), $result.stdout.Trim())
    }
    if (-not $result.stdout.Trim()) {
        throw ("Canonical registration plan generation returned no stdout via '{0}'." -f $result.host_path)
    }
    return $result.stdout | ConvertFrom-Json
}

function Get-TaskField {
    param([object]$Task, [string]$Name)
    if ($null -eq $Task) { return $null }
    if ($Task -is [System.Collections.IDictionary]) {
        return $Task[$Name]
    }
    $property = $Task.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function ConvertTo-NormalizedActionList {
    param([object[]]$Actions)
    return @($Actions | ForEach-Object {
        [ordered]@{
            execute = [string](Get-TaskField $_ 'execute')
            arguments = [string](Get-TaskField $_ 'arguments')
            working_directory = [string](Get-TaskField $_ 'working_directory')
        }
    })
}

function ConvertTo-NormalizedPrincipal {
    param([object]$Principal)
    return [ordered]@{
        user_id = [string](Get-TaskField $Principal 'user_id')
        logon_type = [string](Get-TaskField $Principal 'logon_type')
        run_level = [string](Get-TaskField $Principal 'run_level')
    }
}

function Get-LiveTaskSnapshot {
    param([string[]]$TaskNames)
    $rows = @()
    foreach ($name in $TaskNames) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            $rows += [ordered]@{
                task_name = $name
                present = $false
            }
            continue
        }
        $info = Get-ScheduledTaskInfo -TaskName $name
        $actions = @($task.Actions | ForEach-Object {
            [ordered]@{
                execute = [string]$_.Execute
                arguments = [string]$_.Arguments
                working_directory = [string]$_.WorkingDirectory
            }
        })
        $rows += [ordered]@{
            task_name = $name
            present = $true
            enabled = [bool]$task.Settings.Enabled
            state = [string]$task.State
            user_id = [string]$task.Principal.UserId
            logon_type = [string]$task.Principal.LogonType
            run_level = [string]$task.Principal.RunLevel
            actions = $actions
            last_run_time = $info.LastRunTime.ToUniversalTime().ToString('o')
            last_task_result = [uint32]$info.LastTaskResult
            next_run_time = $info.NextRunTime.ToUniversalTime().ToString('o')
        }
    }
    return $rows
}

function Get-TaskSnapshot {
    param([string[]]$TaskNames)
    if ($TaskSnapshotPath) {
        return (Get-Content -LiteralPath $TaskSnapshotPath -Raw | ConvertFrom-Json)
    }
    return Get-LiveTaskSnapshot -TaskNames $TaskNames
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-TaskByName {
    param([object[]]$Snapshot, [string]$TaskName)
    $matches = @($Snapshot | Where-Object { [string](Get-TaskField $_ 'task_name') -eq $TaskName })
    if ($matches.Count -eq 0) {
        return $null
    }
    return $matches[0]
}

function Test-ActionMatches {
    param([object]$Expected, [object[]]$Actions)
    if (@($Actions).Count -ne 1) { return $false }
    $action = $Actions[0]
    return ([string](Get-TaskField $action 'execute') -eq [string](Get-TaskField $Expected 'execute')) `
        -and ([string](Get-TaskField $action 'arguments') -eq [string](Get-TaskField $Expected 'arguments')) `
        -and ([string](Get-TaskField $action 'working_directory') -eq [string](Get-TaskField $Expected 'working_directory'))
}

function Test-PrincipalMatches {
    param([object]$Expected, [object]$Task)
    return ([string](Get-TaskField $Task 'user_id') -eq [string](Get-TaskField $Expected 'user_id')) `
        -and ([string](Get-TaskField $Task 'logon_type') -eq [string](Get-TaskField $Expected 'logon_type')) `
        -and ([string](Get-TaskField $Task 'run_level') -eq [string](Get-TaskField $Expected 'run_level'))
}

function Get-ContractDescriptor {
    param([object]$CanonicalPlan)
    return [ordered]@{
        report_type = 'lena_scheduler_legacy_to_canonical_driver_migration_contract'
        schema_version = 'v1'
        repo_root = $RepoRoot
        python_exe = $PythonExe
        canonical_task_name = $CanonicalTaskName
        canonical_action = [ordered]@{
            execute = [string]$CanonicalPlan.action.execute
            arguments = [string]$CanonicalPlan.action.arguments
            working_directory = [string]$CanonicalPlan.action.working_directory
        }
        legacy_specs = @($LegacySpecs | ForEach-Object {
            [ordered]@{
                task_name = $_.task_name
                state = $_.state
                execute = $_.execute
                arguments = $_.arguments
                working_directory = $_.working_directory
                principal = $_.principal
            }
        })
    }
}

function Get-ContractHash {
    param([object]$ContractDescriptor)
    return Get-Sha256Hex -Text (ConvertTo-CanonicalJson -Value $ContractDescriptor)
}

function ConvertTo-StableArray {
    param([object]$Value)
    if ($null -eq $Value) {
        return @()
    }
    if ($Value -is [Array]) {
        return $Value
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $items = New-Object System.Collections.Generic.List[object]
        foreach ($item in $Value) {
            $items.Add($item)
        }
        return $items.ToArray()
    }
    return @($Value)
}

function Get-ReceiptProofMaterial {
    param([object]$Receipt)
    return [ordered]@{
        report_type = [string](Get-TaskField $Receipt 'report_type')
        schema_version = [string](Get-TaskField $Receipt 'schema_version')
        stage = [string](Get-TaskField $Receipt 'stage')
        contract_sha256 = [string](Get-TaskField $Receipt 'contract_sha256')
        repo_root = [string](Get-TaskField $Receipt 'repo_root')
        python_exe = [string](Get-TaskField $Receipt 'python_exe')
        pre_backups = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'pre_backups')
        canonical_pre = Get-TaskField $Receipt 'canonical_pre'
        canonical_post = Get-TaskField $Receipt 'canonical_post'
        legacy_tasks_removed = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'legacy_tasks_removed')
        changes = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'changes')
        rollback = Get-TaskField $Receipt 'rollback'
        post_state = ConvertTo-StableArray -Value (Get-TaskField $Receipt 'post_state')
    }
}

function Add-ReceiptProof {
    param([System.Collections.IDictionary]$Receipt)
    $material = Get-ReceiptProofMaterial -Receipt $Receipt
    $Receipt['proof_sha256'] = Get-Sha256Hex -Text (ConvertTo-CanonicalJson -Value $material)
    return $Receipt
}

function Get-InnerExceptionDetails {
    param([Exception]$Exception)
    $details = New-Object System.Collections.Generic.List[object]
    $current = $Exception.InnerException
    while ($null -ne $current) {
        $details.Add([ordered]@{
            exception_type = $current.GetType().FullName
            message = [string]$current.Message
        })
        $current = $current.InnerException
    }
    return ConvertTo-StableArray -Value $details
}

function New-StructuredFailureReport {
    param(
        [System.Management.Automation.ErrorRecord]$ErrorRecord,
        [string]$StageIdentifier,
        [System.Collections.IDictionary]$MutationCounters
    )
    $invocation = $ErrorRecord.InvocationInfo
    return [ordered]@{
        report_type = 'lena_scheduler_legacy_to_canonical_driver_failure'
        schema_version = 'v1'
        stage_identifier = $StageIdentifier
        generated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        exception_type = $ErrorRecord.Exception.GetType().FullName
        message = [string]$ErrorRecord.Exception.Message
        fully_qualified_error_id = [string]$ErrorRecord.FullyQualifiedErrorId
        category_info = [string]$ErrorRecord.CategoryInfo
        script_name = [string]$invocation.ScriptName
        script_line_number = $invocation.ScriptLineNumber
        offset_in_line = $invocation.OffsetInLine
        line = [string]$invocation.Line
        position_message = [string]$invocation.PositionMessage
        script_stack_trace = [string]$ErrorRecord.ScriptStackTrace
        inner_exceptions = @(Get-InnerExceptionDetails -Exception $ErrorRecord.Exception)
        mutation_counters = [ordered]@{
            scheduler_mutations_performed = [int](Get-TaskField $MutationCounters 'scheduler_mutations_performed')
            task_start_operations_performed = [int](Get-TaskField $MutationCounters 'task_start_operations_performed')
            task_enable_operations_performed = [int](Get-TaskField $MutationCounters 'task_enable_operations_performed')
            backup_writes_performed = [int](Get-TaskField $MutationCounters 'backup_writes_performed')
            receipt_writes_performed = [int](Get-TaskField $MutationCounters 'receipt_writes_performed')
        }
    }
}

function Get-ValidatedPriorReceipt {
    param([string]$Path, [string]$ContractHash)
    if (-not $Path) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Prior receipt not found: $Path"
    }
    $receipt = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ([string](Get-TaskField $receipt 'report_type') -ne 'lena_scheduler_legacy_to_canonical_driver_migration_receipt') {
        throw "Prior receipt report_type is invalid: $Path"
    }
    if ([string](Get-TaskField $receipt 'schema_version') -ne 'v1') {
        throw "Prior receipt schema_version is invalid: $Path"
    }
    if ([string](Get-TaskField $receipt 'contract_sha256') -ne $ContractHash) {
        throw "Prior receipt contract hash mismatch: $Path"
    }
    $stage = [string](Get-TaskField $receipt 'stage')
    if ($AllowedResumeStages -notcontains $stage) {
        throw "Prior receipt stage is not resumable: $stage"
    }
    $backups = @(Get-TaskField $receipt 'pre_backups')
    if (@($backups).Count -lt 4) {
        throw "Prior receipt does not contain all legacy backups: $Path"
    }
    foreach ($spec in $LegacySpecs) {
        $backup = @($backups | Where-Object { [string](Get-TaskField $_ 'task_name') -eq $spec.task_name })
        if ($backup.Count -ne 1) {
            throw "Prior receipt backup set is incomplete for $($spec.task_name): $Path"
        }
        $xmlPath = [string](Get-TaskField $backup[0] 'xml_path')
        $xmlHash = [string](Get-TaskField $backup[0] 'xml_sha256')
        if (-not $xmlPath -or -not $xmlHash) {
            throw "Prior receipt backup record is incomplete for $($spec.task_name): $Path"
        }
        if (-not (Test-Path -LiteralPath $xmlPath -PathType Leaf)) {
            throw "Prior receipt backup XML is missing for $($spec.task_name): $xmlPath"
        }
        $actualHash = Get-XmlSha256 -XmlText (Get-Content -LiteralPath $xmlPath -Raw)
        if ($actualHash -ne $xmlHash) {
            throw "Prior receipt backup XML hash mismatch for $($spec.task_name): $xmlPath"
        }
    }
    return $receipt
}

function Export-TaskXmlToPath {
    param([string]$TaskName, [string]$Path)
    $xmlText = Export-ScheduledTask -TaskName $TaskName
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $xmlText, [Text.Encoding]::UTF8)
    return [ordered]@{
        task_name = $TaskName
        xml_path = $Path
        xml_sha256 = Get-XmlSha256 -XmlText $xmlText
    }
}

function Restore-TaskDefinitionDisabled {
    param([string]$TaskName, [string]$XmlPath)
    $xml = Get-Content -LiteralPath $XmlPath -Raw
    Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
}

function Invoke-Rollback {
    param(
        [object[]]$PreBackups,
        [string]$CanonicalTaskName,
        [string]$RollbackReceiptPath,
        [bool]$CanonicalExistedBefore
    )
    $restoreLog = New-Object System.Collections.Generic.List[object]
    foreach ($spec in $LegacySpecs) {
        $backup = @($PreBackups | Where-Object { [string](Get-TaskField $_ 'task_name') -eq $spec.task_name })
        if ($backup.Count -ne 1) {
            throw "Rollback failed: missing legacy backup for $($spec.task_name)"
        }
        Restore-TaskDefinitionDisabled -TaskName $spec.task_name -XmlPath ([string](Get-TaskField $backup[0] 'xml_path'))
        $restoreLog.Add([ordered]@{
            task_name = $spec.task_name
            restored_from = [string](Get-TaskField $backup[0] 'xml_path')
            restored_disabled = $true
        })
    }

    $canonicalBackup = @($PreBackups | Where-Object { [string](Get-TaskField $_ 'task_name') -eq $CanonicalTaskName })
    if ($canonicalBackup.Count -eq 1) {
        Restore-TaskDefinitionDisabled -TaskName $CanonicalTaskName -XmlPath ([string](Get-TaskField $canonicalBackup[0] 'xml_path'))
        $restoreLog.Add([ordered]@{
            task_name = $CanonicalTaskName
            restored_from = [string](Get-TaskField $canonicalBackup[0] 'xml_path')
            restored_disabled = $true
        })
    }
    elseif (-not $CanonicalExistedBefore) {
        $task = Get-ScheduledTask -TaskName $CanonicalTaskName -ErrorAction SilentlyContinue
        if ($null -ne $task) {
            Unregister-ScheduledTask -TaskName $CanonicalTaskName -Confirm:$false
            $restoreLog.Add([ordered]@{
                task_name = $CanonicalTaskName
                restored_from = ''
                removed_to_restore_absence = $true
            })
        }
    }

    $receipt = [ordered]@{
        report_type = 'lena_scheduler_legacy_to_canonical_driver_rollback_receipt'
        schema_version = 'v1'
        rolled_back_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        restored_tasks = ConvertTo-StableArray -Value $restoreLog
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $RollbackReceiptPath -Encoding utf8
}

function New-CanonicalAction {
    param([object]$CanonicalPlan)
    return New-ScheduledTaskAction -Execute $CanonicalPlan.action.execute -Argument $CanonicalPlan.action.arguments -WorkingDirectory $CanonicalPlan.action.working_directory
}

function New-CanonicalTrigger {
    return New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration ([TimeSpan]::MaxValue)
}

function New-CanonicalPrincipal {
    return New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest
}

function New-CanonicalSettings {
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -WakeToRun:$false
    $settings.Enabled = $false
    return $settings
}

function Build-Plan {
    $canonicalPlan = Get-CanonicalPlan
    $contractDescriptor = Get-ContractDescriptor -CanonicalPlan $canonicalPlan
    $contractHash = Get-ContractHash -ContractDescriptor $contractDescriptor
    $taskNames = @($LegacySpecs | ForEach-Object { $_.task_name }) + @($CanonicalTaskName)
    $snapshot = @(Get-TaskSnapshot -TaskNames $taskNames)
    $blockers = New-Object System.Collections.Generic.List[object]
    $legacyState = New-Object System.Collections.Generic.List[object]
    $resumeState = [ordered]@{
        prior_receipt_path = $PriorReceiptPath
        prior_receipt_valid = $false
        authorized = $false
        stage = ''
        resume_mode = 'none'
        deterministic_recovery = $false
        detail = ''
    }
    $priorReceipt = $null
    if ($PriorReceiptPath) {
        try {
            $priorReceipt = Get-ValidatedPriorReceipt -Path $PriorReceiptPath -ContractHash $contractHash
            $resumeState['prior_receipt_valid'] = $true
            $resumeState['stage'] = [string](Get-TaskField $priorReceipt 'stage')
        }
        catch {
            $blockers.Add([ordered]@{
                code = 'prior_receipt_invalid'
                detail = $_.Exception.Message
            })
        }
    }

    foreach ($spec in $LegacySpecs) {
        $task = Get-TaskByName -Snapshot $snapshot -TaskName $spec.task_name
        $present = [bool](Get-TaskField $task 'present')
        $enabled = if ($present) { [bool](Get-TaskField $task 'enabled') } else { $null }
        $state = if ($present) { [string](Get-TaskField $task 'state') } else { '' }
        $actionsMatch = if ($present) { Test-ActionMatches -Expected $spec -Actions @(Get-TaskField $task 'actions') } else { $false }
        $principalMatch = if ($present) { Test-PrincipalMatches -Expected $spec.principal -Task $task } else { $false }
        $firstAction = if ($present) { @((Get-TaskField $task 'actions'))[0] } else { $null }
        $obsoleteRepoRootMatch = if ($present -and $null -ne $firstAction) { [string](Get-TaskField $firstAction 'working_directory') -eq $LegacyRepoRoot } else { $false }
        $exactDisabledMatch = $present -and (-not $enabled) -and ($state -eq $spec.state) -and $actionsMatch -and $principalMatch
        $stateRecord = [ordered]@{
            task_name = $spec.task_name
            present = $present
            enabled = $enabled
            state = $state
            expected_disabled = $true
            actions_match = $actionsMatch
            principal_match = $principalMatch
            obsolete_repo_root_match = $obsoleteRepoRootMatch
            exact_disabled_match = $exactDisabledMatch
        }
        $legacyState.Add($stateRecord)
    }

    $canonicalAction = [ordered]@{
        execute = [string]$canonicalPlan.action.execute
        arguments = [string]$canonicalPlan.action.arguments
        working_directory = [string]$canonicalPlan.action.working_directory
    }
    $canonicalTask = Get-TaskByName -Snapshot $snapshot -TaskName $CanonicalTaskName
    $canonicalState = [ordered]@{
        present = [bool](Get-TaskField $canonicalTask 'present')
        enabled = if ((Get-TaskField $canonicalTask 'present')) { [bool](Get-TaskField $canonicalTask 'enabled') } else { $null }
        state = if ((Get-TaskField $canonicalTask 'present')) { [string](Get-TaskField $canonicalTask 'state') } else { '' }
        actions_match = if ((Get-TaskField $canonicalTask 'present')) { Test-ActionMatches -Expected $canonicalAction -Actions @(Get-TaskField $canonicalTask 'actions') } else { $false }
    }
    $canonicalReadyForResume = $canonicalState.present -and (-not $canonicalState.enabled) -and $canonicalState.actions_match

    if ($canonicalState.present -and $canonicalState.enabled) {
        $blockers.Add([ordered]@{
            code = 'canonical_task_enabled_unexpected'
            detail = 'Canonical task must remain disabled during migration.'
        })
    }
    if ($canonicalState.present -and -not $canonicalState.actions_match) {
        $blockers.Add([ordered]@{
            code = 'canonical_task_action_mismatch'
            detail = 'Existing canonical task does not match the canonical deployment plan.'
        })
    }

    $allLegacyExact = $true
    $legacyMissingNames = New-Object System.Collections.Generic.List[string]
    foreach ($stateRecord in $legacyState) {
        if (-not $stateRecord.present) {
            $allLegacyExact = $false
            $legacyMissingNames.Add([string]$stateRecord.task_name)
            continue
        }
        if ($stateRecord.enabled) {
            $blockers.Add([ordered]@{
                code = 'legacy_task_not_disabled'
                detail = "Legacy task must remain disabled: $($stateRecord.task_name)"
            })
            $allLegacyExact = $false
        }
        if ($stateRecord.state -ne 'Disabled') {
            $blockers.Add([ordered]@{
                code = 'legacy_task_state_mismatch'
                detail = "Legacy task state mismatch: $($stateRecord.task_name)"
            })
            $allLegacyExact = $false
        }
        if (-not $stateRecord.actions_match) {
            $blockers.Add([ordered]@{
                code = 'legacy_task_action_mismatch'
                detail = "Legacy task action mismatch: $($stateRecord.task_name)"
            })
            $allLegacyExact = $false
        }
        if (-not $stateRecord.principal_match) {
            $blockers.Add([ordered]@{
                code = 'legacy_task_principal_mismatch'
                detail = "Legacy task principal mismatch: $($stateRecord.task_name)"
            })
            $allLegacyExact = $false
        }
    }

    if ($legacyMissingNames.Count -gt 0) {
        if ($resumeState['prior_receipt_valid'] -and $AllowedResumeStages -contains $resumeState['stage'] -and $canonicalReadyForResume) {
            $allPresentOrMissingOnly = $true
            foreach ($stateRecord in $legacyState) {
                if ($stateRecord.present -and -not $stateRecord.exact_disabled_match) {
                    $allPresentOrMissingOnly = $false
                }
            }
            if ($allPresentOrMissingOnly) {
                $resumeState['authorized'] = $true
                $resumeState['resume_mode'] = 'legacy_retirement_replay'
                $resumeState['deterministic_recovery'] = $true
                $resumeState['detail'] = 'Cryptographically bound prior receipt proves canonical disabled state and complete legacy backups.'
            }
            else {
                $blockers.Add([ordered]@{
                    code = 'legacy_task_partial_state_not_resumable'
                    detail = 'Prior receipt exists, but current present legacy tasks do not exactly match the governed disabled contract.'
                })
            }
        }
        else {
            foreach ($taskName in $legacyMissingNames) {
                $blockers.Add([ordered]@{
                    code = 'legacy_task_missing'
                    detail = "Legacy task missing without authorized resumable receipt: $taskName"
                })
            }
        }
    }

    $plannedOutputRoot = Resolve-OutputRoot
    $outputOutsideRepo = -not (Test-IsPathWithinRoot -Path $plannedOutputRoot -Root $RepoRoot)
    if (-not $outputOutsideRepo) {
        $blockers.Add([ordered]@{
            code = 'output_root_inside_repo'
            detail = "Migration output root must stay outside the repository: $plannedOutputRoot"
        })
    }
    $backupRoot = Join-Path $plannedOutputRoot ("scheduler_task_migration_{0}" -f $contractHash.Substring(0, 12))
    $backupPaths = @($LegacySpecs | ForEach-Object {
        [ordered]@{
            task_name = $_.task_name
            xml_path = Join-Path $backupRoot ("pre_{0}.xml" -f ($_.task_name -replace '[^A-Za-z0-9]+', '_'))
        }
    })
    $canonicalPrePath = Join-Path $backupRoot ("pre_{0}.xml" -f ($CanonicalTaskName -replace '[^A-Za-z0-9]+', '_'))
    $canonicalPostPath = Join-Path $backupRoot ("post_{0}.xml" -f ($CanonicalTaskName -replace '[^A-Za-z0-9]+', '_'))
    $receiptPath = Join-Path $backupRoot 'migration_receipt.json'
    $rollbackReceiptPath = Join-Path $backupRoot 'rollback_receipt.json'

    $applyGuards = [ordered]@{
        validate_only_non_mutating = $true
        backup_legacy_xml_before_change = $true
        record_xml_hashes = $true
        create_or_update_single_canonical_driver = $true
        canonical_task_must_be_disabled = $true
        verify_canonical_task_before_legacy_removal = $true
        remove_legacy_only_after_new_task_verified = $true
        apply_requires_elevated_execution = $true
        unexpected_state_fails_closed = $true
        no_task_enable_or_start = $true
        no_video_task_touched = $true
        resumable_state_requires_receipt = $true
    }

    $planMode = 'validate_only'
    if ($Apply) {
        $planMode = 'apply'
    }

    $legacyStateArray = @($legacyState.ToArray())
    $blockerArray = @($blockers.ToArray())
    $snapshotArray = @($snapshot)
    $governedLegacyArray = @($LegacySpecs)
    $backupPathArray = @($backupPaths)
    $mutationCounters = [ordered]@{
        scheduler_mutations_performed = 0
        task_start_operations_performed = 0
        task_enable_operations_performed = 0
        backup_writes_performed = 0
        receipt_writes_performed = 0
    }
    $runtimeCapabilities = [ordered]@{
        provider_calls = $false
        publishing = $false
        queue_mutation = $false
        media_generation = $false
        anthropic = $false
        video = $false
    }
    $plan = [ordered]@{}
    $plan['report_type'] = 'lena_scheduler_legacy_to_canonical_driver_migration_plan'
    $plan['schema_version'] = 'v1'
    $plan['mode'] = $planMode
    $plan['repo_root'] = $RepoRoot
    $plan['python_exe'] = $PythonExe
    $plan['contract_sha256'] = $contractHash
    $plan['canonical_task_name'] = $CanonicalTaskName
    $plan['canonical_replacement_count'] = 1
    $plan['canonical_plan'] = $canonicalPlan
    $plan['legacy_expected_repo_root'] = $LegacyRepoRoot
    $plan['governed_legacy_task_count'] = 4
    $plan['governed_legacy_tasks'] = $governedLegacyArray
    $plan['legacy_tasks'] = $legacyStateArray
    $plan['canonical_task_state'] = $canonicalState
    $plan['resumable_state'] = $resumeState
    $plan['backup_root'] = $backupRoot
    $plan['backup_paths'] = $backupPathArray
    $plan['canonical_pre_backup_path'] = $canonicalPrePath
    $plan['canonical_post_backup_path'] = $canonicalPostPath
    $plan['receipt_path'] = $receiptPath
    $plan['rollback_receipt_path'] = $rollbackReceiptPath
    $plan['output_root_outside_repo'] = $outputOutsideRepo
    $plan['apply_guards'] = $applyGuards
    $plan['planned_operations'] = @(
        'export legacy XML backups and hashes',
        'create or update the canonical task disabled',
        'verify canonical disabled state and canonical launcher',
        'retire only the governed legacy tasks',
        'write receipt and rollback instructions'
    )
    $plan['mutation_counters'] = $mutationCounters
    $plan['runtime_capabilities'] = $runtimeCapabilities
    $plan['legacy_snapshot'] = $snapshotArray
    $plan['blockers'] = $blockerArray
    $plan['ok'] = ($blockers.Count -eq 0)
    return $plan
}

if ($MyInvocation.InvocationName -eq '.') {
    return
}

$plan = Build-Plan
if ($ValidateOnly) {
    if (-not $plan.ok) {
        [Console]::Error.WriteLine(
            'Validate-only blockers: ' + (
                @($plan.blockers | ForEach-Object {
                    '{0}: {1}' -f $_.code, $_.detail
                }) -join '; '
            )
        )
    }
    $plan | ConvertTo-Json -Depth 10
    exit $(if ($plan.ok) { 0 } else { 1 })
}

if (-not $Apply) {
    Write-Error 'Apply mode was not selected.'
    exit 1
}
if (-not (Test-IsAdministrator)) {
    Write-Error 'Apply mode requires an elevated Administrator session.'
    exit 1
}
if (-not $plan.ok) {
    $plan | ConvertTo-Json -Depth 10
    exit 1
}

$resolvedOutputRoot = Resolve-OutputRoot
$currentStage = 'preflight'
$applyMutationCounters = [ordered]@{
    scheduler_mutations_performed = 0
    task_start_operations_performed = 0
    task_enable_operations_performed = 0
    backup_writes_performed = 0
    receipt_writes_performed = 0
}
$receipt = $null
$receiptPath = ''
$rollbackPath = ''
try {
    if (Test-IsPathWithinRoot -Path $resolvedOutputRoot -Root $RepoRoot) {
        throw "OutputRoot must remain outside the repository: $resolvedOutputRoot"
    }
    $currentStage = 'backup-root preparation'
    [IO.Directory]::CreateDirectory($resolvedOutputRoot) | Out-Null
    $runRoot = Join-Path $resolvedOutputRoot ("scheduler_task_migration_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
    [IO.Directory]::CreateDirectory($runRoot) | Out-Null

    $preBackups = New-Object System.Collections.Generic.List[object]
    $canonicalExistingBefore = ($plan.canonical_task_state.present -eq $true)
    $currentStage = 'legacy-state verification'
    foreach ($spec in $LegacySpecs) {
        $stateRecord = @($plan.legacy_tasks | Where-Object { $_.task_name -eq $spec.task_name })[0]
        if ($stateRecord.present) {
            $currentStage = 'XML export'
            $preBackups.Add((Export-TaskXmlToPath -TaskName $spec.task_name -Path (Join-Path $runRoot ("pre_{0}.xml" -f ($spec.task_name -replace '[^A-Za-z0-9]+', '_')))))
            $applyMutationCounters.backup_writes_performed++
            $currentStage = 'legacy-state verification'
        }
        elseif ($plan.resumable_state.authorized) {
            $receipt = Get-ValidatedPriorReceipt -Path $PriorReceiptPath -ContractHash $plan.contract_sha256
            $existingBackup = @((Get-TaskField $receipt 'pre_backups') | Where-Object { [string](Get-TaskField $_ 'task_name') -eq $spec.task_name })[0]
            $preBackups.Add([ordered]@{
                task_name = [string](Get-TaskField $existingBackup 'task_name')
                xml_path = [string](Get-TaskField $existingBackup 'xml_path')
                xml_sha256 = [string](Get-TaskField $existingBackup 'xml_sha256')
            })
        }
    }

    $canonicalExisting = Get-ScheduledTask -TaskName $CanonicalTaskName -ErrorAction SilentlyContinue
    if ($null -ne $canonicalExisting) {
        $currentStage = 'XML export'
        $preBackups.Add((Export-TaskXmlToPath -TaskName $CanonicalTaskName -Path (Join-Path $runRoot ("pre_{0}.xml" -f ($CanonicalTaskName -replace '[^A-Za-z0-9]+', '_')))))
        $applyMutationCounters.backup_writes_performed++
        $currentStage = 'legacy-state verification'
    }

    $currentStage = 'backup hashing'
    $preBackupArray = ConvertTo-StableArray -Value $preBackups
    $currentStage = 'receipt writing'
    $receipt = [ordered]@{
        report_type = 'lena_scheduler_legacy_to_canonical_driver_migration_receipt'
        schema_version = 'v1'
        stage = 'pre_mutation_backups_complete'
        contract_sha256 = $plan.contract_sha256
        repo_root = $RepoRoot
        python_exe = $PythonExe
        applied_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        pre_state = @($plan.legacy_snapshot)
        pre_backups = $preBackupArray
        canonical_pre = @($preBackupArray | Where-Object { $_.task_name -eq $CanonicalTaskName })
        canonical_post = $null
        legacy_tasks_removed = @()
        changes = @()
        post_state = @()
        rollback = [ordered]@{
            legacy_xml_paths = @($preBackupArray | Where-Object { $_.task_name -ne $CanonicalTaskName } | ForEach-Object { $_.xml_path })
            canonical_pre_xml_paths = @($preBackupArray | Where-Object { $_.task_name -eq $CanonicalTaskName } | ForEach-Object { $_.xml_path })
            canonical_post_xml_path = Join-Path $runRoot ("post_{0}.xml" -f ($CanonicalTaskName -replace '[^A-Za-z0-9]+', '_'))
            restore_legacy_disabled_commands = @($LegacySpecs | ForEach-Object { "Register-ScheduledTask -TaskName `"$($_.task_name)`" -Xml (Get-Content -Raw `"$((Join-Path $runRoot ("pre_{0}.xml" -f ($_.task_name -replace '[^A-Za-z0-9]+', '_'))))`") -Force; Disable-ScheduledTask -TaskName `"$($_.task_name)`"" })
            restore_canonical_pre_or_remove = 'If a canonical pre-backup exists, restore it disabled. Otherwise remove the canonical task to restore prior absence.'
        }
    }
    Add-ReceiptProof -Receipt $receipt | Out-Null
    $receiptPath = Join-Path $runRoot 'migration_receipt.json'
    $rollbackPath = Join-Path $runRoot 'rollback_receipt.json'
    $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    $applyMutationCounters.receipt_writes_performed++
}
catch {
    $failureReport = New-StructuredFailureReport -ErrorRecord $_ -StageIdentifier $currentStage -MutationCounters $applyMutationCounters
    [Console]::Error.WriteLine((ConvertTo-CanonicalJson -Value $failureReport))
    throw
}

try {
    $currentStage = 'canonical-plan resolution'
    $canonicalPlan = $plan.canonical_plan
    $canonicalAlreadyReady = $plan.canonical_task_state.present -and (-not $plan.canonical_task_state.enabled) -and $plan.canonical_task_state.actions_match
    if (-not $canonicalAlreadyReady) {
        $currentStage = 'canonical registration'
        $action = New-CanonicalAction -CanonicalPlan $canonicalPlan
        $trigger = New-CanonicalTrigger
        $principal = New-CanonicalPrincipal
        $settings = New-CanonicalSettings

        Register-ScheduledTask -TaskName $CanonicalTaskName -Description 'Polls every minute and lets the Lena autonomy scheduler driver decide whether a photo generation or publish transition is due.' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        $applyMutationCounters.scheduler_mutations_performed++
        Disable-ScheduledTask -TaskName $CanonicalTaskName | Out-Null
        $receipt.stage = 'canonical_registered_disabled'
        $receipt.changes = @($receipt.changes) + @('Registered or updated canonical task', 'Forced canonical task disabled')
        $currentStage = 'receipt writing'
        Add-ReceiptProof -Receipt $receipt | Out-Null
        $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
        $applyMutationCounters.receipt_writes_performed++
    }
    else {
        $receipt.stage = 'canonical_registered_disabled'
        $receipt.changes = @($receipt.changes) + @('Resumed from prior receipt with canonical task already present and disabled')
        $currentStage = 'receipt writing'
        Add-ReceiptProof -Receipt $receipt | Out-Null
        $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
        $applyMutationCounters.receipt_writes_performed++
    }

    $currentStage = 'canonical verification'
    $canonicalVerify = Get-ScheduledTask -TaskName $CanonicalTaskName -ErrorAction Stop
    if ([bool]$canonicalVerify.Settings.Enabled) {
        throw 'Canonical task verification failed: task is not disabled.'
    }
    $canonicalActions = @($canonicalVerify.Actions | ForEach-Object {
        [ordered]@{
            execute = [string]$_.Execute
            arguments = [string]$_.Arguments
            working_directory = [string]$_.WorkingDirectory
        }
    })
    if (-not (Test-ActionMatches -Expected ([ordered]@{
                execute = [string]$canonicalPlan.action.execute
                arguments = [string]$canonicalPlan.action.arguments
                working_directory = [string]$canonicalPlan.action.working_directory
            }) -Actions $canonicalActions)) {
        throw 'Canonical task verification failed: action mismatch after registration.'
    }
    $currentStage = 'XML export'
    $canonicalPost = Export-TaskXmlToPath -TaskName $CanonicalTaskName -Path (Join-Path $runRoot ("post_{0}.xml" -f ($CanonicalTaskName -replace '[^A-Za-z0-9]+', '_')))
    $applyMutationCounters.backup_writes_performed++
    $receipt.canonical_post = $canonicalPost
    $receipt.rollback.canonical_post_xml_path = $canonicalPost.xml_path
    $receipt.stage = 'legacy_retirement_started'
    $receipt.changes = @($receipt.changes) + @('Verified canonical task disabled before legacy retirement')
    $currentStage = 'receipt writing'
    Add-ReceiptProof -Receipt $receipt | Out-Null
    $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    $applyMutationCounters.receipt_writes_performed++

    $currentStage = 'legacy retirement'
    foreach ($spec in $LegacySpecs) {
        $task = Get-ScheduledTask -TaskName $spec.task_name -ErrorAction SilentlyContinue
        if ($null -ne $task) {
            Unregister-ScheduledTask -TaskName $spec.task_name -Confirm:$false
            $applyMutationCounters.scheduler_mutations_performed++
            $receipt.legacy_tasks_removed = @($receipt.legacy_tasks_removed) + @($spec.task_name)
            $currentStage = 'receipt writing'
            Add-ReceiptProof -Receipt $receipt | Out-Null
            $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
            $applyMutationCounters.receipt_writes_performed++
            $currentStage = 'legacy retirement'
        }
    }

    $receipt.stage = 'legacy_retired'
    $receipt.changes = @($receipt.changes) + @('Retired only the four governed disabled legacy tasks')
    $postNames = @($LegacySpecs | ForEach-Object { $_.task_name }) + @($CanonicalTaskName)
    $receipt.post_state = @(Get-LiveTaskSnapshot -TaskNames $postNames)
    $currentStage = 'receipt writing'
    Add-ReceiptProof -Receipt $receipt | Out-Null
    $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    $applyMutationCounters.receipt_writes_performed++

    $receipt | ConvertTo-Json -Depth 10
}
catch {
    $failureReport = New-StructuredFailureReport -ErrorRecord $_ -StageIdentifier $currentStage -MutationCounters $applyMutationCounters
    if ($null -ne $receipt) {
        $receipt.changes = @($receipt.changes) + @("Failure: $($_.Exception.Message)")
        $receipt.failure = $failureReport
    }
    if ($null -ne $receipt -and $receiptPath) {
        try {
            $currentStage = 'receipt writing'
            Add-ReceiptProof -Receipt $receipt | Out-Null
            $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8
            $applyMutationCounters.receipt_writes_performed++
        }
        catch {
        }
    }
    [Console]::Error.WriteLine((ConvertTo-CanonicalJson -Value $failureReport))
    $currentStage = 'rollback preparation'
    Invoke-Rollback -PreBackups (ConvertTo-StableArray -Value $preBackups) -CanonicalTaskName $CanonicalTaskName -RollbackReceiptPath $rollbackPath -CanonicalExistedBefore $canonicalExistingBefore
    throw
}
