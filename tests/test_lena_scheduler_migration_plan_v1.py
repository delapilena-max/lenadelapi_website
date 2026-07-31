from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "migrate_lena_legacy_scheduler_tasks_to_canonical_driver_v1.ps1"
REGISTER_SCRIPT = ROOT / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"
CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"
LEGACY_REPO_ROOT = r"C:\projects\ai\lenadelapi_website_autopublish_fix"
LEGACY_TASKS = [
    "Lena Daily Orchestrator",
    "Lena Publish Morning Slot",
    "Lena Publish Afternoon Slot",
    "Lena Publish Evening Slot",
]
LEGACY_PRINCIPAL = {
    "user_id": "Nicolas",
    "logon_type": "Interactive",
    "run_level": "Limited",
}


def _powershell_runtime() -> str | None:
    if sys.platform.startswith("win"):
        return shutil.which("powershell.exe") or shutil.which("pwsh")
    return shutil.which("pwsh")


def _run_powershell(*args: str) -> subprocess.CompletedProcess[str]:
    runtime = _powershell_runtime()
    if not runtime:
        raise RuntimeError("No compatible PowerShell runtime is available")
    return subprocess.run(
        [runtime, "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_powershell_command(command: str) -> subprocess.CompletedProcess[str]:
    return _run_powershell("-Command", command)


def _process_debug(proc: subprocess.CompletedProcess[str], label: str) -> str:
    command = " ".join(str(part) for part in proc.args)
    return (
        f"{label} failed\n"
        f"command: {command}\n"
        f"returncode: {proc.returncode}\n"
        f"stderr:\n{proc.stderr}\n"
        f"stdout:\n{proc.stdout}"
    )


def _assert_json_success(proc: subprocess.CompletedProcess[str], label: str) -> dict:
    assert proc.returncode == 0, _process_debug(proc, label)
    assert proc.stdout.strip(), _process_debug(proc, label)
    return json.loads(proc.stdout)


def _assert_failed_process(
    proc: subprocess.CompletedProcess[str], label: str, expected_text: str | None = None
) -> None:
    assert proc.returncode != 0, _process_debug(proc, label)
    assert proc.stderr.strip(), _process_debug(proc, label)
    if expected_text is not None:
        combined = proc.stderr + proc.stdout
        assert expected_text in combined, _process_debug(proc, label)


def _legacy_task(
    name: str,
    execute: str,
    arguments: str,
    *,
    enabled: bool = False,
    state: str = "Disabled",
    user_id: str = "Nicolas",
    logon_type: str = "Interactive",
    run_level: str = "Limited",
) -> dict:
    return {
        "task_name": name,
        "present": True,
        "enabled": enabled,
        "state": state,
        "user_id": user_id,
        "logon_type": logon_type,
        "run_level": run_level,
        "actions": [
            {
                "execute": execute,
                "arguments": arguments,
                "working_directory": LEGACY_REPO_ROOT,
            }
        ],
    }


def _snapshot_payload() -> list[dict]:
    return [
        _legacy_task(
            "Lena Daily Orchestrator",
            r"C:\Python314\python.exe",
            r"tools\lena_daily_orchestrator_v1.py",
        ),
        _legacy_task(
            "Lena Publish Morning Slot",
            "cmd.exe",
            r'/c "C:\projects\ai\lenadelapi_website_autopublish_fix\RUN_LENA_PUBLISH_MORNING_SLOT.bat"',
        ),
        _legacy_task(
            "Lena Publish Afternoon Slot",
            "cmd.exe",
            r'/c "C:\projects\ai\lenadelapi_website_autopublish_fix\RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat"',
        ),
        _legacy_task(
            "Lena Publish Evening Slot",
            "cmd.exe",
            r'/c "C:\projects\ai\lenadelapi_website_autopublish_fix\RUN_LENA_PUBLISH_EVENING_SLOT.bat"',
        ),
        {
            "task_name": CANONICAL_TASK_NAME,
            "present": False,
        },
    ]


def _write_snapshot(path: Path, payload: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _validate_only_plan(
    tmp_path: Path,
    *,
    payload: list[dict] | None = None,
    output_root: Path | None = None,
    prior_receipt_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = _snapshot_payload() if payload is None else payload
    snapshot_path = _write_snapshot(tmp_path / "snapshot.json", payload)
    output_root = tmp_path / "planned_output" if output_root is None else output_root
    args = [
        "-File",
        str(SCRIPT),
        "-ValidateOnly",
        "-RepoRoot",
        str(ROOT),
        "-PythonExe",
        sys.executable,
        "-TaskSnapshotPath",
        str(snapshot_path),
        "-OutputRoot",
        str(output_root),
    ]
    if prior_receipt_path is not None:
        args.extend(["-PriorReceiptPath", str(prior_receipt_path)])
    return _run_powershell(*args)


def _canonical_plan() -> dict:
    proc = _run_powershell(
        "-File",
        str(REGISTER_SCRIPT),
        "-ValidateOnly",
        "-RepoRoot",
        str(ROOT),
        "-PythonExe",
        sys.executable,
    )
    return _assert_json_success(proc, "canonical validate-only registration plan")


def _contract_sha256(plan: dict) -> str:
    return str(plan["contract_sha256"])


def _json_sha256(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _powershell_receipt_proof_sha256(receipt_path: Path) -> str:
    literal_path = str(receipt_path).replace("'", "''")
    proc = _run_powershell(
        "-Command",
        (
            f"$receipt = Get-Content -LiteralPath '{literal_path}' -Raw | ConvertFrom-Json; "
            "$material = [ordered]@{"
            "report_type = [string]$receipt.report_type; "
            "schema_version = [string]$receipt.schema_version; "
            "stage = [string]$receipt.stage; "
            "contract_sha256 = [string]$receipt.contract_sha256; "
            "repo_root = [string]$receipt.repo_root; "
            "python_exe = [string]$receipt.python_exe; "
            "pre_backups = @($receipt.pre_backups); "
            "canonical_pre = $receipt.canonical_pre; "
            "canonical_post = $receipt.canonical_post; "
            "legacy_tasks_removed = @($receipt.legacy_tasks_removed); "
            "changes = @($receipt.changes); "
            "rollback = $receipt.rollback; "
            "post_state = @($receipt.post_state) "
            "}; "
            "$json = $material | ConvertTo-Json -Depth 12 -Compress; "
            "$sha = [System.Security.Cryptography.SHA256]::Create(); "
            "try { "
            "$bytes = [Text.Encoding]::UTF8.GetBytes($json); "
            "([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() "
            "} finally { $sha.Dispose() }"
        ),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _write_backup_xml(backups_dir: Path, task_name: str) -> tuple[str, str]:
    xml_path = backups_dir / f"{task_name.replace(' ', '_')}.xml"
    xml_text = (
        "<Task>"
        f"<RegistrationInfo><URI>{task_name}</URI></RegistrationInfo>"
        f"<Actions><Exec><Command>{task_name}</Command></Exec></Actions>"
        "</Task>"
    )
    xml_path.write_text(xml_text, encoding="utf-8")
    return str(xml_path), hashlib.sha256(xml_text.encode("utf-8")).hexdigest()


def _write_prior_receipt(
    tmp_path: Path,
    *,
    contract_sha256: str,
    stage: str = "legacy_retirement_started",
    legacy_tasks_removed: list[str] | None = None,
    canonical_present: bool = True,
    tamper_contract_hash: bool = False,
) -> Path:
    backups_dir = tmp_path / "prior_backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    pre_backups: list[dict] = []
    for task_name in LEGACY_TASKS:
        xml_path, xml_sha = _write_backup_xml(backups_dir, task_name)
        pre_backups.append(
            {
                "task_name": task_name,
                "xml_path": xml_path,
                "xml_sha256": xml_sha,
            }
        )

    canonical_pre = []
    canonical_post = None
    if canonical_present:
        xml_path, xml_sha = _write_backup_xml(backups_dir, CANONICAL_TASK_NAME)
        canonical_pre = [
            {
                "task_name": CANONICAL_TASK_NAME,
                "xml_path": xml_path,
                "xml_sha256": xml_sha,
            }
        ]
        canonical_post = {
            "task_name": CANONICAL_TASK_NAME,
            "xml_path": xml_path,
            "xml_sha256": xml_sha,
        }

    receipt = {
        "report_type": "lena_scheduler_legacy_to_canonical_driver_migration_receipt",
        "schema_version": "v1",
        "stage": stage,
        "contract_sha256": "0" * 64 if tamper_contract_hash else contract_sha256,
        "repo_root": str(ROOT),
        "python_exe": sys.executable,
        "pre_backups": pre_backups,
        "canonical_pre": canonical_pre,
        "canonical_post": canonical_post,
        "legacy_tasks_removed": legacy_tasks_removed or ["Lena Daily Orchestrator"],
        "changes": ["Resumed from prior receipt"],
        "rollback": {
            "legacy_xml_paths": [item["xml_path"] for item in pre_backups],
            "canonical_pre_xml_paths": [item["xml_path"] for item in canonical_pre],
            "canonical_post_xml_path": canonical_post["xml_path"] if canonical_post else "",
        },
        "post_state": [],
    }
    path = tmp_path / "prior_receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    receipt["proof_sha256"] = _powershell_receipt_proof_sha256(path)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_migration_validate_only_plan_identifies_four_legacy_tasks_precisely(tmp_path: Path) -> None:
    proc = _validate_only_plan(tmp_path)
    plan = _assert_json_success(proc, "migration validate-only plan")

    assert plan["ok"] is True
    assert plan["canonical_task_name"] == CANONICAL_TASK_NAME
    assert plan["governed_legacy_task_count"] == 4
    assert [item["task_name"] for item in plan["legacy_tasks"]] == LEGACY_TASKS
    assert plan["canonical_replacement_count"] == 1
    assert plan["canonical_plan"]["task_count"] == 1
    assert plan["canonical_plan"]["disabled_by_default"] is True
    assert plan["canonical_task_state"]["present"] is False
    assert plan["runtime_capabilities"] == {
        "provider_calls": False,
        "publishing": False,
        "queue_mutation": False,
        "media_generation": False,
        "anthropic": False,
        "video": False,
    }


def test_migration_plan_governs_exact_old_checkout_paths_and_principals(tmp_path: Path) -> None:
    proc = _validate_only_plan(tmp_path)
    plan = _assert_json_success(proc, "migration validate-only principal/path plan")

    assert plan["legacy_expected_repo_root"] == LEGACY_REPO_ROOT
    for spec in plan["governed_legacy_tasks"]:
        assert spec["working_directory"] == LEGACY_REPO_ROOT
        assert spec["principal"] == LEGACY_PRINCIPAL
    for item in plan["legacy_tasks"]:
        assert item["principal_match"] is True
        assert item["actions_match"] is True
        assert item["exact_disabled_match"] is True


def test_enabled_legacy_task_fails_closed(tmp_path: Path) -> None:
    payload = _snapshot_payload()
    payload[1]["enabled"] = True

    proc = _validate_only_plan(tmp_path, payload=payload)
    _assert_failed_process(proc, "enabled legacy task fail-closed case", "legacy_task_not_disabled")


def test_missing_legacy_task_without_prior_receipt_fails_closed(tmp_path: Path) -> None:
    payload = _snapshot_payload()
    payload[2]["present"] = False

    proc = _validate_only_plan(tmp_path, payload=payload)
    _assert_failed_process(proc, "missing legacy task fail-closed case", "legacy_task_missing")


def test_missing_legacy_task_with_valid_prior_receipt_authorizes_deterministic_resume(tmp_path: Path) -> None:
    first_proc = _validate_only_plan(tmp_path / "plan_seed")
    first_plan = _assert_json_success(first_proc, "seed validate-only plan")
    prior_receipt = _write_prior_receipt(
        tmp_path,
        contract_sha256=_contract_sha256(first_plan),
    )

    payload = _snapshot_payload()
    payload[0]["present"] = False
    payload[-1] = {
        "task_name": CANONICAL_TASK_NAME,
        "present": True,
        "enabled": False,
        "state": "Disabled",
        "actions": [
            {
                "execute": _canonical_plan()["action"]["execute"],
                "arguments": _canonical_plan()["action"]["arguments"],
                "working_directory": _canonical_plan()["action"]["working_directory"],
            }
        ],
    }

    proc = _validate_only_plan(tmp_path / "resume_case", payload=payload, prior_receipt_path=prior_receipt)
    plan = _assert_json_success(proc, "resumable validate-only plan")

    assert plan["ok"] is True
    assert plan["resumable_state"]["prior_receipt_valid"] is True
    assert plan["resumable_state"]["authorized"] is True
    assert plan["resumable_state"]["resume_mode"] == "legacy_retirement_replay"
    assert plan["resumable_state"]["deterministic_recovery"] is True


def test_tampered_prior_receipt_fails_closed(tmp_path: Path) -> None:
    first_proc = _validate_only_plan(tmp_path / "plan_seed")
    first_plan = _assert_json_success(first_proc, "seed validate-only plan for tampered receipt")
    prior_receipt = _write_prior_receipt(
        tmp_path,
        contract_sha256=_contract_sha256(first_plan),
        tamper_contract_hash=True,
    )

    payload = _snapshot_payload()
    payload[0]["present"] = False
    payload[-1] = {
        "task_name": CANONICAL_TASK_NAME,
        "present": True,
        "enabled": False,
        "state": "Disabled",
        "actions": [
            {
                "execute": _canonical_plan()["action"]["execute"],
                "arguments": _canonical_plan()["action"]["arguments"],
                "working_directory": _canonical_plan()["action"]["working_directory"],
            }
        ],
    }

    proc = _validate_only_plan(tmp_path / "tampered_case", payload=payload, prior_receipt_path=prior_receipt)
    _assert_failed_process(proc, "tampered prior receipt fail-closed case", "prior_receipt_invalid")


def test_validate_only_performs_zero_writes_and_plans_external_paths(tmp_path: Path) -> None:
    output_root = tmp_path / "outside_reports"
    proc = _validate_only_plan(tmp_path, output_root=output_root)
    plan = _assert_json_success(proc, "zero-write validate-only plan")

    assert plan["mutation_counters"] == {
        "scheduler_mutations_performed": 0,
        "task_start_operations_performed": 0,
        "task_enable_operations_performed": 0,
        "backup_writes_performed": 0,
        "receipt_writes_performed": 0,
    }
    assert plan["output_root_outside_repo"] is True
    assert Path(plan["backup_root"]).is_absolute()
    assert str(output_root) in plan["backup_root"]
    assert not output_root.exists()
    assert Path(plan["receipt_path"]).parent == Path(plan["backup_root"])
    assert Path(plan["rollback_receipt_path"]).parent == Path(plan["backup_root"])


def test_canonical_replacement_is_exact_and_disabled(tmp_path: Path) -> None:
    proc = _validate_only_plan(tmp_path)
    plan = _assert_json_success(proc, "canonical replacement validate-only plan")
    canonical = _canonical_plan()

    assert plan["canonical_replacement_count"] == 1
    assert plan["canonical_plan"]["task_name"] == CANONICAL_TASK_NAME
    assert plan["canonical_plan"]["action"]["arguments"] == canonical["action"]["arguments"]
    assert plan["canonical_plan"]["action"]["working_directory"] == str(ROOT)
    assert plan["apply_guards"]["canonical_task_must_be_disabled"] is True
    assert plan["apply_guards"]["verify_canonical_task_before_legacy_removal"] is True


def test_source_resolves_current_host_before_fallback_and_avoids_literal_child_powershell() -> None:
    source = _source()

    assert "function Resolve-CurrentPowerShellHost" in source
    assert "Get-Process -Id $PID" in source
    assert "$hostPath = Resolve-CurrentPowerShellHost" in source
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $registerScript" not in source
    assert "Invoke-PowerShellChildProcess" in source


def test_source_declares_desktop_and_core_powerShell_host_fallbacks() -> None:
    source = _source()

    assert "@('powershell.exe')" in source
    assert "@('pwsh', 'pwsh.exe')" in source
    assert 'Unable to resolve a valid PowerShell host for edition' in source


def test_dot_sourced_helper_reports_core_host_on_current_runtime() -> None:
    proc = _run_powershell_command(
        f". '{SCRIPT}'; Resolve-CurrentPowerShellHost | Write-Output"
    )
    assert proc.returncode == 0, _process_debug(proc, "current host resolver")
    assert proc.stdout.strip(), _process_debug(proc, "current host resolver")
    if sys.platform.startswith("win"):
        assert proc.stdout.strip().lower().endswith(("pwsh.exe", "powershell.exe"))
    else:
        assert proc.stdout.strip().lower().endswith("pwsh")


def test_dot_sourced_helper_fails_closed_when_no_host_can_be_resolved() -> None:
    proc = _run_powershell_command(
        f". '{SCRIPT}'; try {{ Resolve-CurrentPowerShellHost -CurrentProcessPath 'C:\\definitely-missing\\not-a-real-host.exe' -Edition Core -FallbackCandidates @('definitely-not-a-real-pwsh-host') | Out-Null; exit 0 }} catch {{ Write-Error $_.Exception.Message; exit 1 }}"
    )
    _assert_failed_process(proc, "missing host resolution", "Unable to resolve a valid PowerShell host")


def test_source_emits_stderr_summary_for_validate_only_blockers() -> None:
    source = _source()
    assert "Validate-only blockers:" in source


def test_source_requires_elevation_and_backups_before_mutation() -> None:
    source = _source()

    assert "Apply mode requires an elevated Administrator session." in source
    assert "backup_legacy_xml_before_change = $true" in source
    assert source.index("$preBackups.Add((Export-TaskXmlToPath") < source.index("Register-ScheduledTask -TaskName $CanonicalTaskName")
    assert source.index("Register-ScheduledTask -TaskName $CanonicalTaskName") < source.index("Unregister-ScheduledTask -TaskName $spec.task_name -Confirm:$false")


def test_source_verifies_canonical_before_legacy_retirement_and_records_stages() -> None:
    source = _source()

    assert "pre_mutation_backups_complete" in source
    assert "canonical_registered_disabled" in source
    assert "legacy_retirement_started" in source
    assert "legacy_retired" in source
    assert "Canonical task verification failed: task is not disabled." in source
    assert "Canonical task verification failed: action mismatch after registration." in source
    assert source.index("$receipt.stage = 'legacy_retirement_started'") < source.index("Unregister-ScheduledTask -TaskName $spec.task_name -Confirm:$false")


def test_source_has_no_task_enable_or_start_commands() -> None:
    source = _source()

    assert "Start-ScheduledTask" not in source
    assert "Enable-ScheduledTask" not in source
    assert "no_task_enable_or_start = $true" in source


def test_source_has_rollback_restore_contract() -> None:
    source = _source()

    assert "function Invoke-Rollback" in source
    assert "function Restore-TaskDefinitionDisabled" in source
    assert "Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null" in source
    assert "Disable-ScheduledTask -TaskName $TaskName | Out-Null" in source
    assert "rollback_receipt.json" in source
    assert "restore_legacy_disabled_commands" in source


def test_source_has_no_video_task_handling_or_provider_capability() -> None:
    source = _source()

    assert "Lena Video" not in source
    assert "no_video_task_touched = $true" in source
    assert "provider_calls = $false" in source
    assert "publishing = $false" in source
    assert "queue_mutation = $false" in source
    assert "media_generation = $false" in source
    assert "anthropic = $false" in source
    assert "Invoke-RestMethod" not in source
    assert "Invoke-WebRequest" not in source


def test_failed_execution_reports_process_details_instead_of_json_decode_noise(tmp_path: Path) -> None:
    proc = _run_powershell(
        "-File",
        str(SCRIPT),
        "-ValidateOnly",
        "-RepoRoot",
        str(ROOT),
        "-PythonExe",
        sys.executable,
        "-TaskSnapshotPath",
        str(tmp_path / "missing_snapshot.json"),
    )
    with_exception = None
    try:
        _assert_json_success(proc, "expected failing subprocess")
    except AssertionError as exc:
        with_exception = str(exc)
    assert with_exception is not None
    assert "returncode:" in with_exception
    assert "stderr:" in with_exception
    assert "stdout:" in with_exception
