from __future__ import annotations

import argparse
import json
import hashlib
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.publishers import lena_meta_publish_common_v2_9 as publish_common

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "pipeline" / "publishing" / "lena" / "go_live_readiness"
POLICY_PATH = (
    ROOT / "pipeline" / "influencer_nodes" / "lena"
    / "approved_queue_auto_publisher_policy_v2_8.json"
)
MANIFEST_PATH = (
    ROOT / "pipeline" / "influencer_nodes" / "lena"
    / "approved_queue_auto_publisher_manifest_v2_8.json"
)
BATCH_GATES = (
    "RUN_LENA_PUBLISH_MORNING_SLOT.bat",
    "RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat",
    "RUN_LENA_PUBLISH_EVENING_SLOT.bat",
)
SLOT_SPECS = {
    "morning": "09:00",
    "afternoon": "14:00",
    "evening": "19:30",
}
PRODUCTION_ROOT_ENV_KEYS = (
    "LENA_AUTOPUBLISH_PRODUCTION_ROOT",
    "CONTENT_BOT_ROOT",
)
PYTHON_EXE_ENV_KEYS = (
    "LENA_AUTOPUBLISH_PYTHON_EXE",
    "CONTENT_BOT_PYTHON_EXE",
    "PYTHON_EXE",
)
REQUIRED_PUBLISH_ENV_KEYS = (
    "META_PAGE_ACCESS_TOKEN",
    "META_INSTAGRAM_ACCESS_TOKEN",
    "META_IG_USER_ID",
    "META_FACEBOOK_PAGE_ID",
    "META_GRAPH_API_VERSION",
    "R2_ACCOUNT_ID",
    "R2_BUCKET_NAME",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_PUBLIC_BASE_URL",
    "LENA_MEDIA_PUBLIC_BASE_URL",
    "LENA_MEDIA_PUBLIC_LOCAL_DIR",
)


class ReadinessError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ReadinessError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(code, f"{label} must be a JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ReadinessError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _parse_iso_utc(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("naive timestamp")
    return value.astimezone(timezone.utc)


def _resolve_production_root(raw: str | None = None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    for env_key in PRODUCTION_ROOT_ENV_KEYS:
        env_value = os.environ.get(env_key, "").strip()
        if env_value:
            return Path(env_value).expanduser().resolve()
    raise ReadinessError(
        "production_root_missing",
        "explicit --production-root or CONTENT_BOT_ROOT/LENA_AUTOPUBLISH_PRODUCTION_ROOT is required",
    )


def _resolve_python_exe(raw: str | None = None) -> tuple[Path, str]:
    if raw:
        return Path(raw).expanduser().resolve(), "cli"
    for env_key in PYTHON_EXE_ENV_KEYS:
        env_value = os.environ.get(env_key, "").strip()
        if env_value:
            return Path(env_value).expanduser().resolve(), f"env:{env_key}"
    return Path(sys.executable).resolve(), "current_runtime"


def _git_command(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _git_state(root: Path) -> dict[str, Any]:
    status = _git_command(root, "status", "--short")
    head = _git_command(root, "rev-parse", "HEAD")
    branch = _git_command(root, "branch", "--show-current")
    origin_main = _git_command(root, "rev-parse", "origin/main")
    return {
        "branch": branch,
        "head": head,
        "origin_main": origin_main,
        "clean": not bool(status.strip()),
        "status_lines": [line for line in status.splitlines() if line.strip()],
        "head_matches_origin_main": head == origin_main,
    }


def _probe_python_interpreter(python_exe: Path, production_root: Path) -> dict[str, Any]:
    if not python_exe.is_file():
        return {
            "ok": False,
            "reason": "python_executable_missing",
            "python_exe": str(python_exe),
        }
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(production_root)
        if not env.get("PYTHONPATH")
        else str(production_root) + os.pathsep + env["PYTHONPATH"]
    )
    proc = subprocess.run(
        [
            str(python_exe),
            "-c",
            (
                "import json, sys; "
                "from tools.publishers import lena_meta_publish_common_v2_9 as publish_common; "
                "print(json.dumps({"
                "'ok': True, "
                "'executable': sys.executable, "
                "'module': publish_common.__name__"
                "}))"
            ),
        ],
        cwd=str(production_root),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "reason": "python_import_probe_failed",
            "python_exe": str(python_exe),
            "returncode": proc.returncode,
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        }
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        parsed = {}
    return {
        "ok": True,
        "reason": "",
        "python_exe": str(python_exe),
        "returncode": proc.returncode,
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        "parsed": parsed if isinstance(parsed, dict) else {},
    }


def _env_presence_report(production_root: Path, process_env: dict[str, str]) -> dict[str, Any]:
    dotenv_path = production_root / ".env"
    dotenv_vars = publish_common.parse_dotenv(dotenv_path)
    env_map = publish_common.load_env_map(production_root)
    key_map = env_map.get("key_map", {}) if isinstance(env_map, dict) else {}
    entries: list[dict[str, Any]] = []
    for env_key in REQUIRED_PUBLISH_ENV_KEYS:
        present_in_process = bool(process_env.get(env_key))
        present_in_dotenv = bool(dotenv_vars.get(env_key))
        config_keys = [
            config_key for config_key, env_keys in key_map.items()
            if env_key in [str(item) for item in (env_keys or [])]
        ]
        entries.append(
            {
                "env_var": env_key,
                "present_in_process": present_in_process,
                "present_in_dotenv": present_in_dotenv,
                "config_keys": config_keys,
                "present": present_in_process or present_in_dotenv,
            }
        )
    missing = [entry["env_var"] for entry in entries if not entry["present"]]
    return {
        "dotenv_path": str(dotenv_path),
        "dotenv_present": dotenv_path.is_file(),
        "env_map_path": str(production_root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json"),
        "env_map_present": (production_root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json").is_file(),
        "entries": entries,
        "missing": missing,
        "ok": not missing,
    }


def _sanitize_config_status(status: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for key, value in status.get("checks", {}).items():
        checks[key] = {"ok": bool(value.get("ok", False))}
        if key in {"local_config_exists", "dotenv_sources", "r2_configured"} and value.get("path"):
            checks[key]["path"] = value.get("path", "")
        if key == "dotenv_sources":
            checks[key]["sources"] = value.get("sources", [])
    readiness = status.get("readiness", {})
    return {
        "ok": bool(status.get("ok", False)),
        "version": status.get("version", ""),
        "config_path": status.get("config_path", ""),
        "checks": checks,
        "readiness": {
            "auth_mode": readiness.get("auth_mode", ""),
            "instagram_ready": bool(readiness.get("instagram_ready", False)),
            "facebook_ready": bool(readiness.get("facebook_ready", False)),
            "media_host_ready": bool(readiness.get("media_host_ready", False)),
            "media_host_method": readiness.get("media_host_method", ""),
        },
    }


def _policy_summary(production_root: Path, git_head: str) -> dict[str, Any]:
    path = production_root / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json"
    policy = _read_json_object(path, code="autonomous_policy_missing_or_invalid", label="autonomous publish policy artifact")
    blockers: list[dict[str, str]] = []

    def ensure(ok: bool, code: str, detail: str) -> None:
        if not ok:
            blockers.append({"code": code, "detail": detail})

    ensure(policy.get("policy_id") == "lena_approved_queue_auto_publisher_policy_v2_8", "autonomous_policy_id_invalid", "policy_id must match the autonomous queue publisher contract")
    ensure(policy.get("policy_version") == "v2.8.0", "autonomous_policy_version_invalid", "policy_version must be v2.8.0")
    ensure(policy.get("autonomous_mode") == "scheduled_autonomous", "autonomous_mode_invalid", "policy must describe the scheduled autonomous mode")
    ensure(policy.get("autonomous_enabled") is False, "autonomous_policy_enabled_unexpected", "autonomous publishing must remain disabled by policy until explicit activation")
    ensure(policy.get("autonomous_enabled_by_default") is False, "autonomous_policy_default_enabled", "autonomous mode must be disabled by default")
    ensure(policy.get("manual_live_mode_unchanged") is True, "manual_live_mode_changed", "manual-live behavior must remain unchanged")
    ensure(policy.get("autonomous_mode_requires_distinct_policy_gate") is True, "autonomous_policy_distinct_gate_missing", "scheduled autonomous mode must require a distinct policy gate")
    ensure(policy.get("repository_name") == "delapilena-max/lenadelapi_website", "autonomous_policy_repository_invalid", "repository_name must bind the Lena repo")
    ensure(str(policy.get("authority_version") or "").strip() == "main", "autonomous_policy_authority_version_invalid", "authority_version must be main")
    ensure(str(policy.get("authority_commit") or "").strip() == git_head, "autonomous_policy_stale", "autonomous policy must match the current repository authority")
    ensure(int(policy.get("hard_item_limit_per_invocation", 0)) == 1, "autonomous_policy_item_limit_invalid", "hard_item_limit_per_invocation must be one")
    ensure(set(str(item).strip().lower() for item in policy.get("approved_slots", [])) == {"morning", "afternoon", "evening"}, "autonomous_policy_slots_invalid", "approved_slots must be morning, afternoon, and evening")
    ensure(int(policy.get("queue_claim_lease_seconds", 0)) > 0, "autonomous_policy_claim_lease_invalid", "queue_claim_lease_seconds must be positive")
    ensure(int(policy.get("max_attempts_per_row", 0)) > 0, "autonomous_policy_retry_cap_invalid", "max_attempts_per_row must be positive")
    ensure(policy.get("allow_replies") is False and policy.get("allow_dms") is False and policy.get("allow_outreach") is False, "autonomous_policy_outreach_invalid", "replies, DMs, and outreach must remain disabled")
    ensure(policy.get("require_queue_build_before_first_publish_slot") is True, "autonomous_policy_queue_build_invalid", "queue build must be required before the first slot")
    ensure(policy.get("require_clean_export_revalidation") is True, "autonomous_policy_clean_export_invalid", "clean-export revalidation must be required")
    ensure(policy.get("require_atomic_queue_claim") is True, "autonomous_policy_claim_required_invalid", "atomic queue claim must be required")
    ensure(policy.get("require_platform_receipts") is True, "autonomous_policy_receipts_required_invalid", "platform receipts must be required")
    ensure(policy.get("require_idempotent_post_log_sync") is True, "autonomous_policy_sync_required_invalid", "post-log sync must be required")
    ensure(bool(policy.get("autonomous_queue_platforms", [])), "autonomous_policy_platforms_missing", "autonomous_queue_platforms must be non-empty")
    expires_raw = str(policy.get("policy_expires_at_utc") or "").strip()
    if not expires_raw:
        blockers.append({"code": "autonomous_policy_expiry_missing", "detail": "policy_expires_at_utc is required"})
    else:
        try:
            expiry = _parse_iso_utc(expires_raw)
            if expiry <= _now_utc():
                blockers.append({"code": "autonomous_policy_expired", "detail": f"policy has expired at {expires_raw}"})
        except Exception as exc:
            blockers.append({"code": "autonomous_policy_expiry_malformed", "detail": f"policy_expires_at_utc not valid ISO-8601 UTC: {expires_raw!r}: {exc}"})
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "blockers": blockers,
        "disabled_by_policy": policy.get("autonomous_enabled") is False,
        "autonomous_mode": policy.get("autonomous_mode", ""),
        "approved_slots": policy.get("approved_slots", []),
        "autonomous_queue_platforms": policy.get("autonomous_queue_platforms", []),
        "expires_at_utc": expires_raw,
    }


def _manifest_summary(production_root: Path) -> dict[str, Any]:
    path = production_root / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_manifest_v2_8.json"
    manifest = _read_json_object(path, code="autonomous_manifest_missing_or_invalid", label="autonomous publish manifest artifact")
    boundary = manifest.get("boundary", {})
    operations = manifest.get("operations", {})
    safety = manifest.get("safety", {})
    blockers: list[dict[str, str]] = []

    def ensure(ok: bool, code: str, detail: str) -> None:
        if not ok:
            blockers.append({"code": code, "detail": detail})

    ensure(boundary.get("auto_queue_building") is True, "autonomous_manifest_queue_building_invalid", "manifest must allow queue building")
    ensure(boundary.get("auto_publish_queue") is False, "autonomous_manifest_autopublish_invalid", "manifest must keep autonomous publishing guarded")
    ensure(boundary.get("scheduled_autonomous_mode") == "separate_policy_gate_required", "autonomous_manifest_mode_invalid", "manifest must require a separate policy gate")
    ensure(boundary.get("autonomous_enabled_by_default") is False, "autonomous_manifest_default_enabled", "manifest must state autonomous mode is disabled by default")
    ensure(boundary.get("manual_live_mode_unchanged") is True, "autonomous_manifest_manual_live_changed", "manual-live mode must remain unchanged")
    ensure(boundary.get("autonomous_publish_requires_distinct_policy") is True, "autonomous_manifest_distinct_policy_missing", "manifest must require a distinct autonomous policy")
    ensure(boundary.get("live_posting_requires_explicit_flags") is True, "autonomous_manifest_explicit_flags_missing", "manifest must require explicit live posting flags")
    ensure(boundary.get("auto_replying") is False and boundary.get("auto_dm_sending") is False and boundary.get("auto_outreach") is False, "autonomous_manifest_outreach_invalid", "manifest must keep replies, DMs, and outreach disabled")
    ensure(operations.get("queue_claim") == "atomic_slot_claim", "autonomous_manifest_claim_invalid", "manifest must define atomic slot claim")
    ensure(int(operations.get("slot_limit_per_invocation", 0)) == 1, "autonomous_manifest_slot_limit_invalid", "manifest must cap each invocation to one slot")
    ensure(sorted(str(s).lower() for s in operations.get("slot_keywords", [])) == ["afternoon", "evening", "morning"], "autonomous_manifest_slots_invalid", "manifest must document morning, afternoon, and evening")
    ensure(operations.get("require_queue_build_before_first_slot") is True, "autonomous_manifest_queue_build_invalid", "queue build must be required before the first slot")
    ensure(operations.get("require_clean_export_revalidation_before_dispatch") is True, "autonomous_manifest_clean_export_invalid", "clean-export revalidation must be required")
    ensure(operations.get("require_platform_receipts") is True, "autonomous_manifest_receipts_invalid", "platform receipts must be required")
    ensure(operations.get("require_idempotent_post_log_sync") is True, "autonomous_manifest_sync_invalid", "post-log sync must be required")
    ensure(safety.get("queue_building_allowed") is True, "autonomous_manifest_queue_building_disallowed", "queue building must remain allowed")
    ensure(safety.get("duplicate_prevention") is True, "autonomous_manifest_duplicate_prevention_invalid", "duplicate prevention must remain on")
    ensure(safety.get("already_posted_skip") is True, "autonomous_manifest_already_posted_skip_invalid", "already-posted skip must remain on")
    ensure(safety.get("bounded_retries") is True, "autonomous_manifest_bounded_retries_invalid", "bounded retries must remain on")
    ensure(safety.get("crash_recovery") is True, "autonomous_manifest_crash_recovery_invalid", "crash recovery must remain on")
    ensure(safety.get("stale_claim_handling") is True, "autonomous_manifest_stale_claim_invalid", "stale claim handling must remain on")
    ensure(safety.get("partial_platform_failure_fail_closed") is True, "autonomous_manifest_partial_failure_invalid", "partial platform failures must fail closed")
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "blockers": blockers,
    }


def _wrapper_summary() -> dict[str, Any]:
    slots = []
    blockers: list[dict[str, str]] = []
    for name, slot in zip(BATCH_GATES, SLOT_SPECS.keys(), strict=True):
        path = ROOT / name
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        has_pause = "pause" in text.lower()
        has_scheduled_autonomous = "--scheduled-autonomous" in text
        has_slot_keyword = f"--slot-keyword {slot}" in text
        has_hardcoded_temp_root = "lenadelapi_website_hpe2" in text.lower()
        has_required_root_env = "LENA_AUTOPUBLISH_PRODUCTION_ROOT" in text or "CONTENT_BOT_ROOT" in text
        has_required_python_env = "LENA_AUTOPUBLISH_PYTHON_EXE" in text or "CONTENT_BOT_PYTHON_EXE" in text
        slot_blockers = []
        if not path.exists():
            slot_blockers.append("batch_wrapper_missing")
        if has_pause:
            slot_blockers.append("pause_present")
        if not has_scheduled_autonomous:
            slot_blockers.append("scheduled_autonomous_missing")
        if not has_slot_keyword:
            slot_blockers.append("slot_keyword_missing")
        if has_hardcoded_temp_root:
            slot_blockers.append("temp_worktree_hardcoded")
        if not has_required_root_env:
            slot_blockers.append("production_root_env_contract_missing")
        if not has_required_python_env:
            slot_blockers.append("python_exe_env_contract_missing")
        if slot_blockers:
            blockers.append({"slot_keyword": slot, "code": "scheduler_wrapper_invalid", "detail": ", ".join(slot_blockers)})
        slots.append(
            {
                "slot_keyword": slot,
                "path": str(path),
                "exists": path.exists(),
                "has_pause": has_pause,
                "has_scheduled_autonomous": has_scheduled_autonomous,
                "has_slot_keyword": has_slot_keyword,
                "has_hardcoded_temp_root": has_hardcoded_temp_root,
                "has_root_env_contract": has_required_root_env,
                "has_python_env_contract": has_required_python_env,
            }
        )
    return {"slots": slots, "blockers": blockers}


def _core_autonomous_command(
    production_root: Path,
    python_exe: Path,
    slot_keyword: str,
) -> str:
    return (
        f"\"{python_exe.as_posix()}\" -m tools.lena_autopublish_approved_queue_v2_8 "
        f"--scheduled-autonomous --slot-keyword {slot_keyword} --limit 1 "
        f"--autonomous-policy {production_root.joinpath('pipeline', 'influencer_nodes', 'lena', 'approved_queue_auto_publisher_policy_v2_8.json').as_posix()}"
    )


def _cron_command(root: Path, python_exe: Path, slot_keyword: str) -> str:
    return f"cd {root.as_posix()} && {_core_autonomous_command(root, python_exe, slot_keyword)}"


def _scheduler_specs(production_root: Path, python_exe: Path) -> dict[str, Any]:
    cron = []
    systemd = []
    windows = []
    for slot_keyword, local_time in SLOT_SPECS.items():
        core_command = _core_autonomous_command(production_root, python_exe, slot_keyword)
        command = _cron_command(production_root, python_exe, slot_keyword)
        cron.append(
            {
                "slot_keyword": slot_keyword,
                "schedule": f"daily {local_time}",
                "command": command,
                "core_command": core_command,
                "working_directory": str(production_root),
                "concurrency": "single_run_claim_required",
                "timeout_seconds": 10800,
                "timezone_assumption": "system_local_timezone",
            }
        )
        systemd.append(
            {
                "slot_keyword": slot_keyword,
                "on_calendar": f"*-*-* {local_time}:00",
                "exec_start": core_command,
                "working_directory": str(production_root),
                "concurrency": "single_run_claim_required",
                "timeout_seconds": 10800,
                "timezone_assumption": "system_local_timezone",
                "core_command": core_command,
            }
        )
        windows.append(
            {
                "slot_keyword": slot_keyword,
                "execute": str(python_exe),
                "arguments": (
                    f"-m tools.lena_autopublish_approved_queue_v2_8 "
                    f"--scheduled-autonomous --slot-keyword {slot_keyword} --limit 1 "
                    f"--autonomous-policy {production_root.joinpath('pipeline', 'influencer_nodes', 'lena', 'approved_queue_auto_publisher_policy_v2_8.json').as_posix()}"
                ),
                "working_directory": str(production_root),
                "principal": "dedicated account with stored credentials",
                "logon_type": "Password_or_S4U_not_InteractiveToken",
                "enabled_state": "disabled_until_explicit_activation_review",
                "trigger": f"daily at {local_time}",
                "timezone_assumption": "system_local_timezone",
                "concurrency": "single_run_claim_required",
                "timeout_seconds": 10800,
                "core_command": core_command,
            }
        )
    return {"cron": cron, "systemd": systemd, "windows_task_scheduler": windows}


def _safe_validation_commands(production_root: Path, python_exe: Path) -> list[str]:
    policy_path = production_root / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json"
    commands = [
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_go_live_readiness_v1 --production-root {production_root.as_posix()} --python-exe {python_exe.as_posix()}',
        f'"{python_exe.as_posix()}" -m tools.lena_validate_approved_queue_autopublisher_v2_8',
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_approved_queue_v2_8 --scheduled-autonomous --dry-run --slot-keyword morning --limit 1 --autonomous-policy {policy_path.as_posix()}',
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_approved_queue_v2_8 --scheduled-autonomous --dry-run --slot-keyword afternoon --limit 1 --autonomous-policy {policy_path.as_posix()}',
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_approved_queue_v2_8 --scheduled-autonomous --dry-run --slot-keyword evening --limit 1 --autonomous-policy {policy_path.as_posix()}',
    ]
    return commands


def _later_enablement_commands(production_root: Path, python_exe: Path) -> list[str]:
    commands = [
        "Enable-ScheduledTask -TaskName 'Lena Daily Orchestrator'",
        "Enable-ScheduledTask -TaskName 'Lena Publish Morning Slot'",
        "Enable-ScheduledTask -TaskName 'Lena Publish Afternoon Slot'",
        "Enable-ScheduledTask -TaskName 'Lena Publish Evening Slot'",
    ]
    commands.extend(
        _core_autonomous_command(production_root, python_exe, slot_keyword)
        for slot_keyword in SLOT_SPECS
    )
    return commands


def _operator_checklist(report: dict[str, Any]) -> list[dict[str, Any]]:
    production_root = report["production_root"]
    python_exe = report["python_exe"]
    return [
        {
            "step": 1,
            "title": "Confirm production root and interpreter",
            "requires_user": True,
            "notes": "Set or confirm the production-root and interpreter environment contract before any scheduled run.",
            "validation_commands": report["safe_validation_commands"][:2],
        },
        {
            "step": 2,
            "title": "Check publisher readiness",
            "requires_user": False,
            "notes": "Run the readiness tool and confirm Instagram, Facebook, and media-host checks are green.",
            "validation_commands": [report["safe_validation_commands"][0]],
        },
        {
            "step": 3,
            "title": "Check scheduler adapter safety",
            "requires_user": False,
            "notes": "Verify the checked-in batch adapters are root-explicit, non-interactive, and slot-specific.",
            "validation_commands": [
                f'"{python_exe}" -m tools.lena_validate_approved_queue_autopublisher_v2_8',
            ],
        },
        {
            "step": 4,
            "title": "Review deployment adapter specs",
            "requires_user": True,
            "notes": "Confirm the generated cron, systemd, and Windows Task Scheduler specs point at the same bounded core command.",
            "commands": [
                report["scheduler_specs"]["cron"][0]["command"],
                report["scheduler_specs"]["systemd"][0]["exec_start"],
                report["scheduler_specs"]["windows_task_scheduler"][0]["arguments"],
            ],
        },
        {
            "step": 5,
            "title": "Keep autonomous policy disabled until explicit activation review",
            "requires_user": True,
            "notes": "Do not enable the autonomous policy or the scheduled tasks until the blockers are cleared and review is granted.",
            "requires_interactive_token": False,
        },
        {
            "step": 6,
            "title": "Enable tasks one at a time after approval",
            "requires_user": True,
            "notes": "Enable only one Lena task at a time; if a later rollback is needed, disable before changing anything else.",
            "enablement_commands": report["later_enablement_commands"][:4],
        },
    ]


def _build_report(
    production_root: Path,
    python_exe: Path,
    python_source: str,
    root_source: str,
    day: str,
) -> dict[str, Any]:
    git_state = _git_state(production_root)
    python_probe = _probe_python_interpreter(python_exe, production_root)
    process_env = dict(os.environ)
    config_status = publish_common.config_status(False, root=production_root)
    config_checks = config_status.get("checks", {})
    config_readiness = config_status.get("readiness", {})
    env_report = _env_presence_report(production_root, process_env)
    policy = _policy_summary(production_root, git_state["head"])
    manifest = _manifest_summary(production_root)
    wrappers = _wrapper_summary()
    scheduler_specs = _scheduler_specs(production_root, python_exe)
    safe_validation_commands = _safe_validation_commands(production_root, python_exe)
    later_enablement_commands = _later_enablement_commands(production_root, python_exe)

    blockers: list[dict[str, Any]] = []
    if not git_state["clean"]:
        blockers.append({"code": "repository_dirty", "detail": "production repository has uncommitted changes"})
    if not git_state["head_matches_origin_main"]:
        blockers.append({"code": "repository_head_mismatch", "detail": "HEAD must match origin/main before go-live"})
    if not python_probe["ok"]:
        blockers.append({"code": python_probe["reason"], "detail": "python interpreter import probe failed"})
    publisher_config_ready = (
        bool(config_checks.get("local_config_exists", {}).get("ok", False))
        and bool(config_checks.get("dotenv_sources", {}).get("ok", False))
        and bool(config_readiness.get("instagram_ready", False))
        and bool(config_readiness.get("facebook_ready", False))
        and bool(config_readiness.get("media_host_ready", False))
    )
    if not publisher_config_ready:
        blockers.append({"code": "publisher_config_not_ready", "detail": "Instagram, Facebook, media host, local config, and dotenv sources must all be ready"})
    if not env_report["ok"]:
        blockers.append({"code": "environment_visibility_issue", "detail": "required environment variables are missing from the production context"})
    if policy["blockers"]:
        blockers.extend(policy["blockers"])
    if manifest["blockers"]:
        blockers.extend(manifest["blockers"])
    if wrappers["blockers"]:
        blockers.extend(wrappers["blockers"])

    overall_result = "ready_for_explicit_activation_review" if not blockers else "blocked"
    report = {
        "report_type": "lena_autopublish_go_live_readiness",
        "schema_version": "v1",
        "generated_at_utc": _timestamp(),
        "repo_root": str(ROOT),
        "production_root": str(production_root),
        "production_root_source": root_source,
        "python_exe": str(python_exe),
        "python_exe_source": python_source,
        "git": git_state,
        "python_probe": python_probe,
        "publisher_config": _sanitize_config_status(config_status),
        "publisher_config_ready": publisher_config_ready,
        "environment_contract": env_report,
        "policy": policy,
        "manifest": manifest,
        "scheduler_wrappers": wrappers,
        "scheduler_specs": scheduler_specs,
        "safe_validation_commands": safe_validation_commands,
        "later_enablement_commands": later_enablement_commands,
        "operator_checklist": _operator_checklist(
            {
                "production_root": str(production_root),
                "python_exe": str(python_exe),
                "safe_validation_commands": safe_validation_commands,
                "scheduler_specs": scheduler_specs,
                "later_enablement_commands": later_enablement_commands,
            }
        ),
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "blockers": blockers,
        "overall_result": overall_result,
    }
    return report


def _report_path(production_root: Path, day: str, stamp: str) -> Path:
    return (
        production_root
        / "pipeline" / "publishing" / "lena" / "go_live_readiness"
        / day
        / f"lena_autopublish_go_live_readiness_{day}_{stamp}.json"
    )


def _markdown_path(json_path: Path) -> Path:
    return json_path.with_suffix(".md")


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Lena Autopublish Go-Live Readiness",
        "",
        f"- Result: `{report['overall_result']}`",
        f"- Production root: `{report['production_root']}`",
        f"- Python: `{report['python_exe']}`",
        f"- Git HEAD: `{report['git']['head']}`",
        f"- Origin main: `{report['git']['origin_main']}`",
        f"- Clean worktree: `{report['git']['clean']}`",
        "",
        "## Operator Checklist",
    ]
    for item in report["operator_checklist"]:
        lines.append(f"### Step {item['step']}: {item['title']}")
        lines.append(f"- Requires user: `{item.get('requires_user', False)}`")
        lines.append(f"- Notes: {item['notes']}")
        for command in item.get("validation_commands", []):
            lines.append(f"- Validation: `{command}`")
        for command in item.get("commands", []):
            lines.append(f"- Command: `{command}`")
        for command in item.get("enablement_commands", []):
            lines.append(f"- Enablement: `{command}`")
        lines.append("")
    lines.extend(
        [
            "## Safe Validation Commands",
            "",
        ]
    )
    for command in report["safe_validation_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(
        [
            "",
            "## Later Enablement Commands",
            "",
        ]
    )
    for command in report["later_enablement_commands"]:
        lines.append(f"- `{command}`")
    lines.extend(
        [
            "",
            "## Blockers",
            "",
        ]
    )
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- `{blocker['code']}`: {blocker['detail']}")
    else:
        lines.append("- none")
    lines.extend(["", f"Provider calls: `{report['provider_calls_performed']}`", f"Publish calls: `{report['publish_calls_performed']}`"])
    return "\n".join(lines) + "\n"


def save_report(report: dict[str, Any], production_root: Path, day: str, stamp: str) -> tuple[Path, Path]:
    json_path = _report_path(production_root, day, stamp)
    md_path = _markdown_path(json_path)
    _write_text_atomic(json_path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    _write_text_atomic(md_path, _render_markdown(report))
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Lena autopublish go-live prerequisites without enabling autonomy."
    )
    parser.add_argument("--production-root", default="", help="Explicit production repository root")
    parser.add_argument("--python-exe", default="", help="Interpreter used for read-only import and readiness probes")
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat(), help="Readiness date label")
    args = parser.parse_args(argv)

    root_source = "cli" if args.production_root else ("env" if any(os.environ.get(key, "").strip() for key in PRODUCTION_ROOT_ENV_KEYS) else "current_runtime")
    production_root = _resolve_production_root(args.production_root or None)
    python_exe, python_source = _resolve_python_exe(args.python_exe or None)
    stamp = _now_utc().strftime("%Y%m%dT%H%M%SZ")
    report = _build_report(production_root, python_exe, python_source, root_source, args.date)
    json_path, md_path = save_report(report, production_root, args.date, stamp)
    summary = {
        "ok": report["overall_result"] == "ready_for_explicit_activation_review",
        "overall_result": report["overall_result"],
        "report_path": str(json_path),
        "checklist_path": str(md_path),
        "blockers": report["blockers"],
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
