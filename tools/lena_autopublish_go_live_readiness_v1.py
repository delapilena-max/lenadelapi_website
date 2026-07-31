from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.publishers import lena_meta_publish_common_v2_9 as publish_common

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
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
REQUIRED_PUBLISH_ENV_KEYS = (
    "META_PAGE_ACCESS_TOKEN",
    "META_INSTAGRAM_ACCESS_TOKEN",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)

CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"
LEGACY_TASK_NAMES = (
    "Lena Daily Orchestrator",
    "Lena Publish Morning Slot",
    "Lena Publish Afternoon Slot",
    "Lena Publish Evening Slot",
)
REGISTER_SCRIPT_REL = Path("tools") / "register_lena_autonomy_scheduler_task_v1.ps1"
DRIVER_WRAPPER_REL = Path("tools") / "lena_autonomy_scheduler_driver_run_v1.ps1"
DRIVER_MODULE_REL = Path("tools") / "lena_autonomy_scheduler_driver_v1.py"


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
    def is_windows_absolute(value: str) -> bool:
        return bool(WINDOWS_ABSOLUTE_PATH_RE.match(value))

    def resolve_candidate(value: str) -> Path:
        expanded = os.path.expanduser(value)
        if is_windows_absolute(expanded):
            return Path(expanded)
        candidate = Path(expanded)
        if candidate.is_absolute():
            return candidate.resolve()
        which = shutil.which(value)
        if which:
            if is_windows_absolute(which):
                return Path(which)
            return Path(which).resolve()
        if any(sep in expanded for sep in ("\\", "/")):
            return candidate.resolve()
        return candidate.resolve()

    if raw:
        return resolve_candidate(raw), "cli"
    for env_key in PYTHON_EXE_ENV_KEYS:
        env_value = os.environ.get(env_key, "").strip()
        if env_value:
            return resolve_candidate(env_value), f"env:{env_key}"
    return Path(sys.executable).resolve(), "current_runtime"


def _git_command(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _git_state(root: Path) -> dict[str, Any]:
    status = _git_command(root, "status", "--short")
    head = _git_command(root, "rev-parse", "HEAD")
    branch = _git_command(root, "branch", "--show-current")
    origin_main = _git_command(root, "rev-parse", "origin/main")
    origin_main_ancestor_of_head = _git_is_ancestor(root, origin_main, head)
    head_ancestor_of_origin_main = _git_is_ancestor(root, head, origin_main)
    return {
        "branch": branch,
        "head": head,
        "origin_main": origin_main,
        "clean": not bool(status.strip()),
        "status_lines": [line for line in status.splitlines() if line.strip()],
        "head_matches_origin_main": head == origin_main,
        "origin_main_ancestor_of_head": origin_main_ancestor_of_head,
        "head_ancestor_of_origin_main": head_ancestor_of_origin_main,
    }


def _git_is_ancestor(root: Path, ancestor_commit: str, descendant_commit: str) -> bool:
    try:
        subprocess.check_output(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor_commit, descendant_commit],
            text=True,
        )
        return True
    except Exception:
        return False


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


def _required_runtime_env_keys(config_status: dict[str, Any], effective_cfg: dict[str, Any]) -> set[str]:
    required: set[str] = set()
    auth_mode = str(effective_cfg.get("auth_mode") or "").strip().lower()
    page_token = str(effective_cfg.get("page_access_token") or "").strip()
    instagram_token = str(effective_cfg.get("instagram_access_token") or "").strip()
    if not page_token and bool(effective_cfg.get("facebook_page_id")):
        required.add("META_PAGE_ACCESS_TOKEN")
    if not page_token and not instagram_token and auth_mode == "instagram_login":
        required.add("META_INSTAGRAM_ACCESS_TOKEN")
    return required


def _env_presence_report(
    production_root: Path,
    process_env: dict[str, str],
    config_status: dict[str, Any],
) -> dict[str, Any]:
    env_map_error = ""
    env_map_ok = False
    secret_source_error = ""
    secret_source_ok = False
    secret_source_path = str(publish_common.canonical_publisher_secret_source_path())
    secret_source_values: dict[str, str] = {}
    try:
        env_map = publish_common.load_env_map(production_root)
        env_map_ok = True
    except publish_common.ConfigContractError as exc:
        env_map_error = str(exc)
        env_map = {}
    try:
        secret_source = publish_common.load_canonical_publisher_secret_source(production_root)
        secret_source_ok = True
        secret_source_path = secret_source["path"]
        secret_source_values = dict(secret_source["values"])
    except publish_common.ConfigContractError as exc:
        secret_source_error = str(exc)
    try:
        effective_cfg = publish_common.load_config(production_root)
    except publish_common.ConfigContractError:
        effective_cfg = publish_common.load_file_config(production_root)
    key_map = env_map.get("key_map", {}) if isinstance(env_map, dict) else {}
    required_env_keys = _required_runtime_env_keys(config_status, effective_cfg) if env_map_ok else {"META_PAGE_ACCESS_TOKEN"}
    entries: list[dict[str, Any]] = []
    for env_key in REQUIRED_PUBLISH_ENV_KEYS:
        present_in_process = bool(process_env.get(env_key))
        present_in_secret_source = bool(secret_source_values.get(env_key))
        config_key = publish_common.ENV_VAR_TO_CONFIG_KEY.get(env_key, "")
        effective_config_present = bool(
            config_key
            and str(effective_cfg.get(config_key, "") or "").strip()
            and not publish_common._is_placeholder(effective_cfg.get(config_key))
        )
        config_keys = [
            config_key for config_key, env_keys in key_map.items()
            if env_key in [str(item) for item in (env_keys or [])]
        ]
        entries.append(
            {
                "env_var": env_key,
                "present_in_process": present_in_process,
                "present_in_secret_source": present_in_secret_source,
                "config_keys": config_keys,
                "required_by_runtime": env_key in required_env_keys,
                "effective_config_present": effective_config_present,
                "present": effective_config_present or present_in_secret_source or present_in_process,
            }
        )
    missing = [entry["env_var"] for entry in entries if entry["required_by_runtime"] and not entry["present"]]
    return {
        "secret_source_path": secret_source_path,
        "secret_source_present": secret_source_ok,
        "env_map_path": str(production_root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json"),
        "env_map_present": (production_root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json").is_file(),
        "env_map_contract_ok": env_map_ok,
        "env_map_error": env_map_error,
        "secret_source_authority": publish_common.CANONICAL_PUBLISHER_SECRET_SOURCE_AUTHORITY,
        "secret_source_contract_ok": secret_source_ok,
        "secret_source_error": secret_source_error,
        "required_env_vars": sorted(required_env_keys),
        "loaded_secret_keys": sorted(secret_source_values),
        "resolved_config_keys": sorted(
            key
            for key, value in effective_cfg.items()
            if not str(key).startswith("_")
            and str(value or "").strip()
            and not publish_common._is_placeholder(value)
        ),
        "entries": entries,
        "missing": missing,
        "ok": env_map_ok and secret_source_ok and not missing,
    }


def _sanitize_config_status(status: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for key, value in status.get("checks", {}).items():
        checks[key] = {"ok": bool(value.get("ok", False))}
        if key in {"local_config_exists", "dotenv_sources", "r2_configured", "env_map_contract", "canonical_secret_source"} and value.get("path"):
            checks[key]["path"] = value.get("path", "")
        if key == "dotenv_sources":
            checks[key]["sources"] = value.get("sources", [])
            checks[key]["loaded_keys"] = value.get("loaded_keys", [])
            checks[key]["authority"] = value.get("authority", "")
        if key == "env_map_contract":
            checks[key]["contract_id"] = value.get("contract_id", "")
            checks[key]["schema_version"] = value.get("schema_version", "")
            checks[key]["detail"] = value.get("detail", "")
        if key == "canonical_secret_source":
            checks[key]["authority"] = value.get("authority", "")
            checks[key]["governed_keys"] = value.get("governed_keys", [])
            checks[key]["loaded_keys"] = value.get("loaded_keys", [])
            checks[key]["detail"] = value.get("detail", "")
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

    autonomous_enabled = policy.get("autonomous_enabled")
    autonomous_enabled_by_default = policy.get("autonomous_enabled_by_default")
    autonomous_policy_state = str(policy.get("autonomous_policy_state") or "").strip()
    authority_commit = str(policy.get("authority_commit") or "").strip()
    authority_commit_is_ancestor = bool(authority_commit) and _git_is_ancestor(production_root, authority_commit, git_head)

    ensure(policy.get("policy_id") == "lena_approved_queue_auto_publisher_policy_v2_8", "autonomous_policy_id_invalid", "policy_id must match the autonomous queue publisher contract")
    ensure(policy.get("policy_version") == "v2.8.0", "autonomous_policy_version_invalid", "policy_version must be v2.8.0")
    ensure(policy.get("autonomous_mode") == "scheduled_autonomous", "autonomous_mode_invalid", "policy must describe the scheduled autonomous mode")
    ensure(isinstance(autonomous_enabled, bool), "autonomous_policy_enabled_flag_invalid", "autonomous_enabled must be a boolean")
    if isinstance(autonomous_enabled, bool):
        expected_policy_state = "enabled" if autonomous_enabled else "disabled_by_default"
        ensure(
            autonomous_policy_state == expected_policy_state,
            "autonomous_policy_state_invalid",
            f"autonomous_policy_state must match autonomous_enabled: expected {expected_policy_state!r}",
        )
    ensure(autonomous_enabled_by_default is False, "autonomous_policy_default_enabled", "autonomous mode must be disabled by default")
    ensure(policy.get("manual_live_mode_unchanged") is True, "manual_live_mode_changed", "manual-live behavior must remain unchanged")
    ensure(policy.get("autonomous_mode_requires_distinct_policy_gate") is True, "autonomous_policy_distinct_gate_missing", "scheduled autonomous mode must require a distinct policy gate")
    ensure(policy.get("repository_name") == "delapilena-max/lenadelapi_website", "autonomous_policy_repository_invalid", "repository_name must bind the Lena repo")
    ensure(str(policy.get("authority_version") or "").strip() == "main", "autonomous_policy_authority_version_invalid", "authority_version must be main")
    ensure(bool(authority_commit), "autonomous_policy_authority_commit_missing", "authority_commit is required")
    ensure(authority_commit_is_ancestor, "autonomous_policy_stale", "autonomous policy authority_commit must be an ancestor of the current HEAD")
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
        "autonomous_enabled": autonomous_enabled if isinstance(autonomous_enabled, bool) else None,
        "autonomous_enabled_by_default": autonomous_enabled_by_default if isinstance(autonomous_enabled_by_default, bool) else None,
        "autonomous_policy_state": autonomous_policy_state,
        "activation_permitted_by_policy": bool(autonomous_enabled) if isinstance(autonomous_enabled, bool) else False,
        "authority_commit": authority_commit,
        "authority_commit_is_ancestor": authority_commit_is_ancestor,
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


def _core_autonomous_command(production_root: Path, python_exe: Path, slot_keyword: str) -> str:
    return (
        f"\"{python_exe.as_posix()}\" -m tools.lena_autopublish_approved_queue_v2_8 "
        f"--scheduled-autonomous --slot-keyword {slot_keyword} --limit 1 "
        f"--autonomous-policy {production_root.joinpath('pipeline', 'influencer_nodes', 'lena', 'approved_queue_auto_publisher_policy_v2_8.json').as_posix()}"
    )


def _canonical_scheduler_definition(production_root: Path, python_exe: Path) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    register_script = production_root / REGISTER_SCRIPT_REL
    wrapper_path = production_root / DRIVER_WRAPPER_REL
    driver_module_path = production_root / DRIVER_MODULE_REL

    if not register_script.is_file():
        blockers.append({"code": "scheduler_register_script_missing", "detail": f"canonical registration script missing: {register_script}"})
    if not wrapper_path.is_file():
        blockers.append({"code": "scheduler_wrapper_missing", "detail": f"canonical driver wrapper missing: {wrapper_path}"})
    if not driver_module_path.is_file():
        blockers.append({"code": "scheduler_driver_module_missing", "detail": f"canonical driver module missing: {driver_module_path}"})
    if blockers:
        return {
            "ok": False,
            "register_script_path": str(register_script),
            "wrapper_path": str(wrapper_path),
            "driver_module_path": str(driver_module_path),
            "blockers": blockers,
        }

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(register_script),
        "-ValidateOnly",
        "-RepoRoot",
        str(production_root),
        "-PythonExe",
        str(python_exe),
    ]
    proc = subprocess.run(
        command,
        cwd=str(production_root),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        blockers.append(
            {
                "code": "scheduler_plan_failed",
                "detail": f"canonical registration plan failed with exit {proc.returncode}",
            }
        )
        return {
            "ok": False,
            "register_script_path": str(register_script),
            "wrapper_path": str(wrapper_path),
            "driver_module_path": str(driver_module_path),
            "plan_command": command,
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
            "blockers": blockers,
        }
    try:
        plan = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        blockers.append({"code": "scheduler_plan_not_json", "detail": f"canonical registration plan did not emit JSON: {exc}"})
        return {
            "ok": False,
            "register_script_path": str(register_script),
            "wrapper_path": str(wrapper_path),
            "driver_module_path": str(driver_module_path),
            "plan_command": command,
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
            "blockers": blockers,
        }

    def ensure(ok: bool, code: str, detail: str) -> None:
        if not ok:
            blockers.append({"code": code, "detail": detail})

    action = plan.get("action", {}) if isinstance(plan, dict) else {}
    safeguards = plan.get("safeguards", {}) if isinstance(plan, dict) else {}
    trigger = plan.get("trigger", {}) if isinstance(plan, dict) else {}
    arguments = str(action.get("arguments") or "")

    ensure(isinstance(plan, dict), "scheduler_plan_invalid", "canonical registration plan must be a JSON object")
    ensure(plan.get("task_count") == 1, "scheduler_task_count_invalid", "canonical registration plan must emit exactly one task")
    ensure(plan.get("task_name") == CANONICAL_TASK_NAME, "scheduler_task_name_invalid", f"canonical task must be {CANONICAL_TASK_NAME!r}")
    ensure(plan.get("disabled_by_default") is True, "scheduler_disabled_default_invalid", "canonical task must be disabled by default")
    ensure(str(plan.get("run_wrapper_path") or "") == str(wrapper_path), "scheduler_wrapper_binding_invalid", "canonical plan must target this checkout's driver wrapper")
    ensure(str(plan.get("driver_module_path") or "") == str(driver_module_path), "scheduler_driver_binding_invalid", "canonical plan must target this checkout's driver module")
    ensure(str(action.get("working_directory") or "") == str(production_root), "scheduler_working_directory_invalid", "canonical task must run from the explicit production root")
    ensure(str(action.get("execute") or "").lower() == "powershell.exe", "scheduler_execute_invalid", "canonical task must execute powershell.exe")
    ensure("lena_autonomy_scheduler_driver_run_v1.ps1" in arguments, "scheduler_wrapper_argument_missing", "canonical task must invoke the scheduler driver wrapper")
    ensure(f'-RepoRoot "{production_root}"' in arguments, "scheduler_repo_root_argument_missing", "canonical task must bind the explicit production root")
    ensure(trigger.get("type") == "poll_every_minute", "scheduler_trigger_invalid", "canonical task must use the per-minute driver trigger")
    ensure(trigger.get("schedule_slots") == ["morning", "afternoon", "evening"], "scheduler_slot_order_invalid", "canonical task must preserve the three daily photo slots")
    ensure(safeguards.get("no_daily_orchestrator") is True, "scheduler_daily_orchestrator_not_retired", "canonical task must not route through Daily Orchestrator")
    ensure(safeguards.get("no_fixed_publish_slot_tasks") is True, "scheduler_fixed_slot_tasks_not_retired", "canonical task must not use fixed publish-slot tasks")
    ensure(safeguards.get("no_video_task") is True, "scheduler_video_task_present", "canonical task must remain photo-only")

    return {
        "ok": not blockers,
        "register_script_path": str(register_script),
        "wrapper_path": str(wrapper_path),
        "driver_module_path": str(driver_module_path),
        "plan_command": command,
        "plan": plan,
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        "blockers": blockers,
    }


def _registered_task_deployment_status(production_root: Path, scheduler_definition: dict[str, Any]) -> dict[str, Any]:
    task_names = [CANONICAL_TASK_NAME, *LEGACY_TASK_NAMES]
    query_script = """
$names = @(
  'Lena Autonomy Scheduler Driver',
  'Lena Daily Orchestrator',
  'Lena Publish Morning Slot',
  'Lena Publish Afternoon Slot',
  'Lena Publish Evening Slot'
)
$rows = @()
foreach ($name in $names) {
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if ($null -eq $task) {
    $rows += [pscustomobject]@{
      task_name = $name
      present = $false
      enabled = $false
      state = 'NotRegistered'
      actions = @()
    }
    continue
  }
  $actions = @()
  foreach ($action in @($task.Actions)) {
    $actions += [pscustomobject]@{
      execute = [string]$action.Execute
      arguments = [string]$action.Arguments
      working_directory = [string]$action.WorkingDirectory
    }
  }
  $rows += [pscustomobject]@{
    task_name = $name
    present = $true
    enabled = [bool]$task.Settings.Enabled
    state = [string]$task.State
    repetition_interval = if (@($task.Triggers).Count -gt 0 -and $null -ne @($task.Triggers)[0].Repetition) { [string]@($task.Triggers)[0].Repetition.Interval } else { '' }
    repetition_duration = if (@($task.Triggers).Count -gt 0 -and $null -ne @($task.Triggers)[0].Repetition) { [string]@($task.Triggers)[0].Repetition.Duration } else { '' }
    stop_at_duration_end = if (@($task.Triggers).Count -gt 0 -and $null -ne @($task.Triggers)[0].Repetition) { [bool]@($task.Triggers)[0].Repetition.StopAtDurationEnd } else { $false }
    actions = $actions
  }
}
$rows | ConvertTo-Json -Depth 6 -Compress
"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", query_script],
        cwd=str(production_root),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return {
            "query_ok": False,
            "deployment_state": "query_unavailable",
            "activation_required": True,
            "tasks": [],
            "legacy_tasks_present": [],
            "stale_deployment_detected": False,
            "blockers": [
                {
                    "code": "scheduler_query_unavailable",
                    "detail": f"unable to query registered tasks (exit {proc.returncode})",
                }
            ],
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        }
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "query_ok": False,
            "deployment_state": "query_unavailable",
            "activation_required": True,
            "tasks": [],
            "legacy_tasks_present": [],
            "stale_deployment_detected": False,
            "blockers": [{"code": "scheduler_query_not_json", "detail": f"registered task query did not emit JSON: {exc}"}],
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        }

    tasks = parsed if isinstance(parsed, list) else []
    task_map = {
        str(item.get("task_name") or ""): item
        for item in tasks
        if isinstance(item, dict)
    }
    blockers: list[dict[str, str]] = []
    canonical = task_map.get(CANONICAL_TASK_NAME, {})
    canonical_present = bool(canonical.get("present"))
    canonical_enabled = bool(canonical.get("enabled")) if canonical_present else False
    legacy_tasks_present = [name for name in LEGACY_TASK_NAMES if task_map.get(name, {}).get("present")]
    plan = scheduler_definition.get("plan", {}) if isinstance(scheduler_definition, dict) else {}
    plan_action = plan.get("action", {}) if isinstance(plan, dict) else {}
    plan_trigger = plan.get("trigger", {}) if isinstance(plan, dict) else {}
    expected_execute = str(plan_action.get("execute") or "").lower()
    expected_working_directory = str(plan_action.get("working_directory") or "")
    expected_interval = str(plan_trigger.get("repetition_interval") or "")
    expected_duration_element = str(plan_trigger.get("repetition_duration_element") or "")
    expected_wrapper_token = "lena_autonomy_scheduler_driver_run_v1.ps1"
    expected_repo_arg = f'-RepoRoot "{production_root}"'
    canonical_action_matches = False
    canonical_trigger_matches = False
    serialization_deviation: dict[str, Any] | None = None
    if canonical_present:
        for action in canonical.get("actions", []):
            if not isinstance(action, dict):
                continue
            execute = str(action.get("execute") or "").lower()
            arguments = str(action.get("arguments") or "")
            working_directory = str(action.get("working_directory") or "")
            if (
                execute == expected_execute
                and working_directory == expected_working_directory
                and expected_wrapper_token in arguments
                and expected_repo_arg in arguments
            ):
                canonical_action_matches = True
                break
        observed_interval = str(canonical.get("repetition_interval") or "")
        observed_duration = str(canonical.get("repetition_duration") or "")
        observed_stop_at_duration_end = bool(canonical.get("stop_at_duration_end"))
        canonical_trigger_matches = (
            observed_interval == expected_interval
            and (
                (expected_duration_element == "omitted" and not observed_duration)
                or (expected_duration_element != "omitted")
            )
        )
        if (
            canonical_trigger_matches
            and expected_duration_element == "omitted"
            and not observed_duration
            and observed_stop_at_duration_end
        ):
            serialization_deviation = {
                "classification": "non_blocking_serialization_deviation",
                "repetition_interval": observed_interval,
                "repetition_duration_element": "omitted",
                "stop_at_duration_end": True,
                "detail": "StopAtDurationEnd is inert when the repetition duration element is omitted.",
            }
    else:
        observed_interval = ""
        observed_duration = ""
        observed_stop_at_duration_end = False
    canonical_matches_plan = canonical_action_matches and canonical_trigger_matches

    if canonical_present and legacy_tasks_present:
        blockers.append(
            {
                "code": "scheduler_mixed_canonical_and_legacy_state",
                "detail": "canonical task is present while governed legacy tasks are still registered",
            }
        )
    if legacy_tasks_present:
        if set(legacy_tasks_present) != set(LEGACY_TASK_NAMES):
            blockers.append(
                {
                    "code": "scheduler_legacy_task_set_incomplete",
                    "detail": "governed legacy task set must contain exactly the four expected disabled tasks before replacement",
                }
            )
        invalid_legacy = [
            name
            for name in legacy_tasks_present
            if bool(task_map.get(name, {}).get("enabled"))
            or str(task_map.get(name, {}).get("state") or "").strip().lower() != "disabled"
        ]
        if invalid_legacy:
            blockers.append(
                {
                    "code": "scheduler_legacy_task_state_invalid",
                    "detail": "governed legacy tasks must all remain disabled before replacement: " + ", ".join(invalid_legacy),
                }
            )
    if not canonical_present and not legacy_tasks_present:
        blockers.append(
            {
                "code": "scheduler_governed_tasks_missing",
                "detail": "canonical task is absent and no governed legacy tasks remain registered",
            }
        )

    if legacy_tasks_present:
        deployment_state = "stale_legacy_tasks_present"
    elif canonical_present and canonical_matches_plan and canonical_enabled:
        deployment_state = "canonical_driver_enabled"
    elif canonical_present and canonical_matches_plan and not canonical_enabled:
        deployment_state = "canonical_driver_disabled"
    elif canonical_present:
        deployment_state = "canonical_driver_mismatch"
    else:
        deployment_state = "canonical_driver_missing"

    if canonical_present and not canonical_matches_plan:
        blockers.append(
            {
                "code": "scheduler_canonical_task_mismatch",
                "detail": "canonical task launcher, working directory, or repetition contract does not match the registration plan",
            }
        )

    activation_required = deployment_state != "canonical_driver_enabled"
    return {
        "query_ok": True,
        "deployment_state": deployment_state,
        "activation_required": activation_required,
        "continuous_autonomy_active": deployment_state == "canonical_driver_enabled",
        "tasks": tasks,
        "canonical_task_present": canonical_present,
        "canonical_task_enabled": canonical_enabled,
        "canonical_task_matches_plan": canonical_matches_plan,
        "canonical_action_matches_plan": canonical_action_matches,
        "canonical_trigger_matches_plan": canonical_trigger_matches,
        "canonical_trigger_interval": observed_interval or None,
        "canonical_trigger_duration": observed_duration or None,
        "canonical_stop_at_duration_end": observed_stop_at_duration_end if canonical_present else None,
        "serialization_deviation": serialization_deviation,
        "legacy_tasks_present": legacy_tasks_present,
        "stale_deployment_detected": bool(legacy_tasks_present) or deployment_state == "canonical_driver_mismatch",
        "blockers": blockers,
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
    }


def _safe_validation_commands(production_root: Path, python_exe: Path) -> list[str]:
    policy_path = production_root / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json"
    commands = [
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_go_live_readiness_v1 --production-root {production_root.as_posix()} --python-exe {python_exe.as_posix()} --validate-only',
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{production_root.joinpath(REGISTER_SCRIPT_REL).as_posix()}" -ValidateOnly -RepoRoot "{production_root.as_posix()}" -PythonExe "{python_exe.as_posix()}"',
        f'cd /d "{production_root.as_posix()}" && "{python_exe.as_posix()}" -m tools.lena_autonomy_scheduler_driver_v1 --inspect-only',
        f'"{python_exe.as_posix()}" -m tools.lena_validate_approved_queue_autopublisher_v2_8',
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_approved_queue_v2_8 --scheduled-autonomous --dry-run --slot-keyword morning --limit 1 --autonomous-policy {policy_path.as_posix()}',
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_approved_queue_v2_8 --scheduled-autonomous --dry-run --slot-keyword afternoon --limit 1 --autonomous-policy {policy_path.as_posix()}',
        f'"{python_exe.as_posix()}" -m tools.lena_autopublish_approved_queue_v2_8 --scheduled-autonomous --dry-run --slot-keyword evening --limit 1 --autonomous-policy {policy_path.as_posix()}',
    ]
    return commands


def _later_enablement_commands(production_root: Path, python_exe: Path) -> list[str]:
    return [
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{production_root.joinpath(REGISTER_SCRIPT_REL).as_posix()}" -RepoRoot "{production_root.as_posix()}" -PythonExe "{python_exe.as_posix()}"',
        f"Enable-ScheduledTask -TaskName '{CANONICAL_TASK_NAME}'",
    ]


def _operator_checklist(report: dict[str, Any]) -> list[dict[str, Any]]:
    production_root = report["production_root"]
    python_exe = report["python_exe"]
    return [
        {
            "step": 1,
            "title": "Confirm production root and interpreter",
            "requires_user": True,
            "notes": "Set or confirm the production-root and interpreter environment contract before any scheduler replacement.",
            "validation_commands": report["safe_validation_commands"][:1],
        },
        {
            "step": 2,
            "title": "Emit the canonical scheduler plan",
            "requires_user": False,
            "notes": "Confirm the repository now models exactly one disabled-by-default scheduler-driver task with no fixed publish-slot tasks.",
            "validation_commands": [report["safe_validation_commands"][1]],
        },
        {
            "step": 3,
            "title": "Inspect the driver schedule without side effects",
            "requires_user": False,
            "notes": "Verify the single driver preserves the morning, afternoon, and evening photo cadence internally.",
            "validation_commands": [report["safe_validation_commands"][2]],
        },
        {
            "step": 4,
            "title": "Check publisher and connector readiness",
            "requires_user": True,
            "notes": "Run the read-only readiness report and confirm structural validity, credential visibility, connector readiness, and registered-task deployment state.",
            "validation_commands": [report["safe_validation_commands"][0], report["safe_validation_commands"][3]],
        },
        {
            "step": 5,
            "title": "Replace stale registered tasks only after approval",
            "requires_user": True,
            "notes": "Keep the current disabled legacy tasks unchanged in this task. Only after explicit approval should the disabled legacy tasks be replaced with the canonical single driver.",
            "enablement_commands": report["later_enablement_commands"],
        },
    ]


def _overall_result_for(report_blockers: list[dict[str, Any]], activation_required: bool, deployment_state: str) -> str:
    if report_blockers:
        return "blocked"
    if deployment_state == "canonical_driver_disabled" and activation_required:
        return "ready_for_bounded_photo_autonomy_proof"
    if not activation_required:
        return "active_deployment_present"
    if deployment_state == "stale_legacy_tasks_present":
        return "ready_for_disabled_scheduler_replacement"
    return "blocked"


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
    env_report = _env_presence_report(production_root, process_env, config_status)
    policy = _policy_summary(production_root, git_state["head"])
    manifest = _manifest_summary(production_root)
    scheduler_definition = _canonical_scheduler_definition(production_root, python_exe)
    registered_task_deployment_status = _registered_task_deployment_status(production_root, scheduler_definition)
    safe_validation_commands = _safe_validation_commands(production_root, python_exe)
    later_enablement_commands = _later_enablement_commands(production_root, python_exe)

    blockers: list[dict[str, Any]] = []
    if not git_state["clean"]:
        blockers.append({"code": "repository_dirty", "detail": "production repository has uncommitted changes"})
    head_contains_origin_main = bool(
        git_state.get("origin_main_ancestor_of_head", git_state["head_matches_origin_main"])
    )
    if not head_contains_origin_main:
        blockers.append({"code": "repository_head_mismatch", "detail": "HEAD must contain origin/main before go-live"})
    if not python_probe["ok"]:
        blockers.append({"code": python_probe["reason"], "detail": "python interpreter import probe failed"})
    publisher_config_ready = (
        bool(config_checks.get("env_map_contract", {}).get("ok", False))
        and bool(config_checks.get("canonical_secret_source", {}).get("ok", False))
        and
        bool(config_checks.get("local_config_exists", {}).get("ok", False))
        and bool(config_checks.get("dotenv_sources", {}).get("ok", False))
        and bool(config_readiness.get("instagram_ready", False))
        and bool(config_readiness.get("facebook_ready", False))
        and bool(config_readiness.get("media_host_ready", False))
    )
    if not publisher_config_ready:
        blockers.append({"code": "publisher_config_not_ready", "detail": "Instagram, Facebook, media host, local config, and dotenv sources must all be ready"})
    if not env_report.get("env_map_contract_ok", False):
        blockers.append({"code": "publisher_env_map_invalid", "detail": env_report.get("env_map_error", "publisher env map contract is invalid")})
    elif not env_report.get("secret_source_contract_ok", False):
        blockers.append({"code": "publisher_secret_source_invalid", "detail": env_report.get("secret_source_error", "canonical publisher secret source is invalid")})
    elif not env_report["ok"]:
        blockers.append({"code": "environment_visibility_issue", "detail": "required environment variables are missing from the production context"})
    if policy["blockers"]:
        blockers.extend(policy["blockers"])
    if manifest["blockers"]:
        blockers.extend(manifest["blockers"])
    if scheduler_definition["blockers"]:
        blockers.extend(scheduler_definition["blockers"])
    if registered_task_deployment_status["blockers"]:
        blockers.extend(registered_task_deployment_status["blockers"])

    activation_required = (
        not bool(policy.get("activation_permitted_by_policy"))
        or bool(registered_task_deployment_status.get("activation_required", True))
    )
    structural_valid = not any(
        blocker["code"] in {
            "repository_dirty",
            "repository_head_mismatch",
            "python_import_probe_failed",
            "python_executable_missing",
            "publisher_env_map_invalid",
            "publisher_secret_source_invalid",
            "autonomous_policy_id_invalid",
            "autonomous_policy_version_invalid",
            "autonomous_mode_invalid",
            "autonomous_policy_enabled_flag_invalid",
            "autonomous_policy_state_invalid",
            "autonomous_policy_default_enabled",
            "manual_live_mode_changed",
            "autonomous_policy_distinct_gate_missing",
            "autonomous_policy_repository_invalid",
            "autonomous_policy_authority_version_invalid",
            "autonomous_policy_authority_commit_missing",
            "autonomous_policy_stale",
            "autonomous_policy_item_limit_invalid",
            "autonomous_policy_slots_invalid",
            "autonomous_policy_claim_lease_invalid",
            "autonomous_policy_retry_cap_invalid",
            "autonomous_policy_outreach_invalid",
            "autonomous_policy_queue_build_invalid",
            "autonomous_policy_clean_export_invalid",
            "autonomous_policy_claim_required_invalid",
            "autonomous_policy_receipts_required_invalid",
            "autonomous_policy_sync_required_invalid",
            "autonomous_policy_platforms_missing",
            "autonomous_policy_expiry_missing",
            "autonomous_policy_expiry_malformed",
            "autonomous_policy_expired",
            "autonomous_manifest_queue_building_invalid",
            "autonomous_manifest_autopublish_invalid",
            "autonomous_manifest_mode_invalid",
            "autonomous_manifest_default_enabled",
            "autonomous_manifest_manual_live_changed",
            "autonomous_manifest_distinct_policy_missing",
            "autonomous_manifest_explicit_flags_missing",
            "autonomous_manifest_outreach_invalid",
            "autonomous_manifest_claim_invalid",
            "autonomous_manifest_slot_limit_invalid",
            "autonomous_manifest_slots_invalid",
            "autonomous_manifest_queue_build_invalid",
            "autonomous_manifest_clean_export_invalid",
            "autonomous_manifest_receipts_invalid",
            "autonomous_manifest_sync_invalid",
            "autonomous_manifest_queue_building_disallowed",
            "autonomous_manifest_duplicate_prevention_invalid",
            "autonomous_manifest_already_posted_skip_invalid",
            "autonomous_manifest_bounded_retries_invalid",
            "autonomous_manifest_crash_recovery_invalid",
            "autonomous_manifest_stale_claim_invalid",
            "autonomous_manifest_partial_failure_invalid",
            "scheduler_register_script_missing",
            "scheduler_wrapper_missing",
            "scheduler_driver_module_missing",
            "scheduler_plan_failed",
            "scheduler_plan_not_json",
            "scheduler_plan_invalid",
            "scheduler_task_count_invalid",
            "scheduler_task_name_invalid",
            "scheduler_disabled_default_invalid",
            "scheduler_wrapper_binding_invalid",
            "scheduler_driver_binding_invalid",
            "scheduler_working_directory_invalid",
            "scheduler_execute_invalid",
            "scheduler_wrapper_argument_missing",
            "scheduler_repo_root_argument_missing",
            "scheduler_trigger_invalid",
            "scheduler_slot_order_invalid",
            "scheduler_daily_orchestrator_not_retired",
            "scheduler_fixed_slot_tasks_not_retired",
            "scheduler_video_task_present",
        }
        for blocker in blockers
    )
    environment_visibility = {
        "ok": python_probe["ok"] and env_report.get("env_map_contract_ok", False) and env_report.get("secret_source_contract_ok", False) and env_report["ok"],
        "python_probe_ok": python_probe["ok"],
        "env_map_contract_ok": env_report.get("env_map_contract_ok", False),
        "secret_source_contract_ok": env_report.get("secret_source_contract_ok", False),
        "production_root": str(production_root),
        "python_exe": str(python_exe),
        "secret_source_path": env_report.get("secret_source_path", ""),
        "required_environment_keys": env_report.get("required_env_vars", []),
        "missing_environment_keys": env_report["missing"],
    }
    connector_readiness = {
        "ok": publisher_config_ready,
        "instagram_ready": bool(config_readiness.get("instagram_ready", False)),
        "facebook_ready": bool(config_readiness.get("facebook_ready", False)),
        "media_host_ready": bool(config_readiness.get("media_host_ready", False)),
        "auth_mode": config_readiness.get("auth_mode", ""),
    }
    credential_readiness = {
        "ok": env_report.get("env_map_contract_ok", False) and env_report.get("secret_source_contract_ok", False) and env_report["ok"],
        "missing": env_report["missing"],
        "required": env_report.get("required_env_vars", []),
        "entries": env_report["entries"],
    }
    scheduler_definition_readiness = {
        "ok": scheduler_definition["ok"],
        "blockers": scheduler_definition["blockers"],
        "plan": scheduler_definition.get("plan", {}),
        "register_script_path": scheduler_definition["register_script_path"],
    }
    activation_state = {
        "autonomous_enabled": policy.get("autonomous_enabled"),
        "autonomous_enabled_by_default": policy.get("autonomous_enabled_by_default"),
        "autonomous_policy_state": policy.get("autonomous_policy_state"),
        "activation_required": activation_required,
        "active_deployment_present": not activation_required,
        "continuous_autonomy_active": bool(registered_task_deployment_status.get("continuous_autonomy_active", False)),
        "bounded_photo_proof_executed": False,
    }
    overall_result = _overall_result_for(
        blockers,
        activation_required,
        str(registered_task_deployment_status.get("deployment_state") or ""),
    )
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
        "structural_validity": {"ok": structural_valid},
        "environment_visibility": environment_visibility,
        "connector_readiness": connector_readiness,
        "credential_readiness": credential_readiness,
        "environment_contract": env_report,
        "policy": policy,
        "manifest": manifest,
        "scheduler_definition_readiness": scheduler_definition_readiness,
        "registered_task_deployment_status": registered_task_deployment_status,
        "activation_state": activation_state,
        "safe_validation_commands": safe_validation_commands,
        "later_enablement_commands": later_enablement_commands,
        "operator_checklist": _operator_checklist(
            {
                "production_root": str(production_root),
                "python_exe": str(python_exe),
                "safe_validation_commands": safe_validation_commands,
                "later_enablement_commands": later_enablement_commands,
            }
        ),
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "queue_mutations_performed": 0,
        "task_mutations_performed": 0,
        "task_starts_performed": 0,
        "task_enables_performed": 0,
        "anthropic_calls_performed": 0,
        "video_actions_performed": 0,
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
        f"- Structural validity: `{report['structural_validity']['ok']}`",
        f"- Activation required: `{report['activation_state']['activation_required']}`",
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
            "## Registered Task Deployment Status",
            "",
        ]
    )
    deployment = report["registered_task_deployment_status"]
    lines.append(f"- Deployment state: `{deployment['deployment_state']}`")
    lines.append(f"- Canonical task present: `{deployment.get('canonical_task_present', False)}`")
    lines.append(f"- Canonical task matches plan: `{deployment.get('canonical_task_matches_plan', False)}`")
    lines.append(f"- Canonical task enabled: `{deployment.get('canonical_task_enabled', False)}`")
    lines.append(f"- Continuous autonomy active: `{report['activation_state'].get('continuous_autonomy_active', False)}`")
    if deployment.get("serialization_deviation"):
        lines.append(f"- Serialization deviation: `{deployment['serialization_deviation']['classification']}`")
    if deployment.get("legacy_tasks_present"):
        for task_name in deployment["legacy_tasks_present"]:
            lines.append(f"- Stale legacy task present: `{task_name}`")
    else:
        lines.append("- Stale legacy task present: none")
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
    lines.extend(
        [
            "",
            f"Provider calls: `{report['provider_calls_performed']}`",
            f"Publish calls: `{report['publish_calls_performed']}`",
            f"Queue mutations: `{report['queue_mutations_performed']}`",
            f"Task mutations: `{report['task_mutations_performed']}`",
            f"Anthropic calls: `{report['anthropic_calls_performed']}`",
            f"Video actions: `{report['video_actions_performed']}`",
        ]
    )
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
    parser.add_argument("--validate-only", "--read-only", action="store_true", dest="validate_only", help="Emit the full readiness report to stdout without writing any report artifacts")
    args = parser.parse_args(argv)

    root_source = "cli" if args.production_root else ("env" if any(os.environ.get(key, "").strip() for key in PRODUCTION_ROOT_ENV_KEYS) else "current_runtime")
    production_root = _resolve_production_root(args.production_root or None)
    python_exe, python_source = _resolve_python_exe(args.python_exe or None)
    stamp = _now_utc().strftime("%Y%m%dT%H%M%SZ")
    report = _build_report(production_root, python_exe, python_source, root_source, args.date)
    if args.validate_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["overall_result"] != "blocked" else 1

    json_path, md_path = save_report(report, production_root, args.date, stamp)
    summary = {
        "ok": report["overall_result"] != "blocked",
        "overall_result": report["overall_result"],
        "report_path": str(json_path),
        "checklist_path": str(md_path),
        "blockers": report["blockers"],
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "queue_mutations_performed": 0,
        "task_mutations_performed": 0,
        "task_starts_performed": 0,
        "task_enables_performed": 0,
        "anthropic_calls_performed": 0,
        "video_actions_performed": 0,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
