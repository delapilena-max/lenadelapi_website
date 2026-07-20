from __future__ import annotations

import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "pipeline" / "influencer_nodes" / "lena" / "autonomy_ladder_v1.json"
LEVELS = (0, 1, 2, 3, 4, 5)
LEVEL_3_POLICY_ID = "lena_approved_queue_auto_publisher_policy_v2_8"
LEVEL_3_POLICY_VERSION = "v2.8.0"
LEVEL_3_POLICY_PATH = Path("pipeline/influencer_nodes/lena/approved_queue_auto_publisher_policy_v2_8.json")
LEVEL_3_APPROVED_SLOTS = ("morning", "afternoon", "evening")
LEVEL_3_APPROVED_PLATFORMS = ("Facebook Page", "Instagram Feed")
LEVEL_3_REQUIRED_LIVE_FLAGS = ("--i-understand-this-can-publish", "--live")


class AutonomyLadderError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class AutonomyLadderBlocked(AutonomyLadderError):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        tool_name: str,
        level: int | None,
        action: str,
        contract: dict[str, Any],
    ) -> None:
        super().__init__(code, detail)
        self.tool_name = tool_name
        self.level = level
        self.action = action
        self.contract = contract

    @property
    def report(self) -> dict[str, Any]:
        return {
            "ok": False,
            "blocked": True,
            "error_code": self.code,
            "error": self.detail,
            "tool_name": self.tool_name,
            "level": self.level,
            "action": self.action,
            "contract": contract_summary(self.contract),
        }


def _read_contract() -> dict[str, Any]:
    path = CONTRACT_PATH
    if not path.is_file():
        raise AutonomyLadderError("contract_missing", f"autonomy ladder contract is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutonomyLadderError("contract_malformed", f"autonomy ladder contract is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AutonomyLadderError("contract_malformed", f"autonomy ladder contract must be a JSON object: {path}")
    return payload


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise AutonomyLadderError(code, detail)


def _resolve_repo_relative_path(raw: str) -> Path:
    path = Path(str(raw).replace("\\", "/").strip())
    _require(bool(str(path).strip()), "contract_invalid", "level 3 authority must define a policy_path")
    resolved = path if path.is_absolute() else (ROOT / path)
    try:
        resolved = resolved.resolve(strict=False)
    except OSError as exc:
        raise AutonomyLadderError("contract_invalid", f"level 3 authority policy_path is not resolvable: {raw!r}: {exc}") from exc
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise AutonomyLadderError("contract_invalid", f"level 3 authority policy_path must stay within the repository root: {raw!r}") from exc
    return resolved


def _is_git_ancestor(repo_root: Path, ancestor_commit: str, descendant_commit: str) -> bool:
    try:
        process = subprocess.Popen(
            ["git", "merge-base", "--is-ancestor", ancestor_commit, descendant_commit],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _stdout, _stderr = process.communicate()
        return process.returncode == 0
    except Exception:
        return False


def _policy_required_set(values: list[Any] | tuple[Any, ...] | set[Any]) -> set[str]:
    return {str(value).strip() for value in values if str(value).strip()}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_level_three_authority(binding: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(binding, dict), "contract_invalid", "level 3 authority must be a JSON object")
    policy_path_raw = binding.get("policy_path")
    _require(isinstance(policy_path_raw, str) and policy_path_raw.strip(), "contract_invalid", "level 3 authority must define policy_path")
    policy_path = _resolve_repo_relative_path(policy_path_raw)
    _require(policy_path.is_file(), "level_3_policy_missing", f"level 3 authority policy does not exist: {policy_path}")
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutonomyLadderError("level_3_policy_malformed", f"level 3 authority policy is not valid JSON: {policy_path}: {exc}") from exc
    if not isinstance(policy, dict):
        raise AutonomyLadderError("level_3_policy_malformed", f"level 3 authority policy must be a JSON object: {policy_path}")

    expected_sha = binding.get("policy_sha256")
    _require(isinstance(expected_sha, str) and expected_sha.strip(), "contract_invalid", "level 3 authority must define policy_sha256")
    actual_sha = _sha256_file(policy_path)
    _require(expected_sha.lower() == actual_sha.lower(), "level_3_policy_unauthorized", "level 3 authority policy_sha256 must match the bound policy artifact")

    _require(policy.get("policy_id") == LEVEL_3_POLICY_ID, "level_3_policy_unauthorized", "level 3 authority policy_id must match the approved queue publisher policy")
    _require(policy.get("policy_version") == LEVEL_3_POLICY_VERSION, "level_3_policy_unauthorized", "level 3 authority policy_version must remain v2.8.0")
    _require(policy.get("repository_name") == "delapilena-max/lenadelapi_website", "level_3_policy_unauthorized", "level 3 authority policy must bind the Lena repository")
    _require(policy.get("autonomous_mode") == "scheduled_autonomous", "level_3_policy_unauthorized", "level 3 authority policy must describe the scheduled autonomous mode")
    _require(policy.get("autonomous_enabled") is True, "level_3_policy_disabled", "level 3 authority policy must be enabled")
    _require(policy.get("autonomous_enabled_by_default") is False, "level_3_policy_unauthorized", "level 3 authority policy must remain disabled by default")
    _require(policy.get("autonomous_policy_state") == "enabled", "level_3_policy_unauthorized", "level 3 authority policy state must be enabled")
    _require(policy.get("manual_live_mode_unchanged") is True, "level_3_policy_unauthorized", "manual-live behavior must remain unchanged")
    _require(policy.get("autonomous_mode_requires_distinct_policy_gate") is True, "level_3_policy_unauthorized", "scheduled autonomous mode must require a distinct policy gate")
    _require(policy.get("require_queue_build_before_first_publish_slot") is True, "level_3_policy_unauthorized", "queue build must be required before the first publish slot")
    _require(policy.get("require_clean_export_revalidation") is True, "level_3_policy_unauthorized", "clean-export revalidation must be required")
    _require(policy.get("require_atomic_queue_claim") is True, "level_3_policy_unauthorized", "atomic queue claim must be required")
    _require(policy.get("require_platform_receipts") is True, "level_3_policy_unauthorized", "platform receipts must be required")
    _require(policy.get("require_idempotent_post_log_sync") is True, "level_3_policy_unauthorized", "idempotent post-log sync must be required")
    _require(policy.get("allow_replies") is False, "level_3_policy_unauthorized", "replies must remain disabled")
    _require(policy.get("allow_dms") is False, "level_3_policy_unauthorized", "DMs must remain disabled")
    _require(policy.get("allow_outreach") is False, "level_3_policy_unauthorized", "outreach must remain disabled")
    _require(_policy_required_set(policy.get("approved_slots", [])) == set(LEVEL_3_APPROVED_SLOTS), "level_3_policy_unauthorized", "approved_slots must be morning, afternoon, and evening")
    _require(int(policy.get("hard_item_limit_per_invocation", 0)) == 1, "level_3_policy_unauthorized", "hard_item_limit_per_invocation must be one")
    _require(int(policy.get("queue_claim_lease_seconds", 0)) > 0, "level_3_policy_unauthorized", "queue_claim_lease_seconds must be positive")
    _require(int(policy.get("max_attempts_per_row", 0)) > 0, "level_3_policy_unauthorized", "max_attempts_per_row must be positive")
    _require(_policy_required_set(policy.get("autonomous_queue_platforms", [])) == set(LEVEL_3_APPROVED_PLATFORMS), "level_3_policy_unauthorized", "autonomous_queue_platforms must remain Instagram Feed and Facebook Page only")
    _require(policy.get("live_posting_requires_explicit_flags") is True, "level_3_policy_unauthorized", "live posting must require explicit flags")
    _require(_policy_required_set(policy.get("required_live_flags", [])) == set(LEVEL_3_REQUIRED_LIVE_FLAGS), "level_3_policy_unauthorized", "required live flags must remain --live and --i-understand-this-can-publish")

    expires_raw = str(policy.get("policy_expires_at_utc") or "").strip()
    _require(bool(expires_raw), "level_3_policy_expiry_missing", "level 3 authority policy_expires_at_utc is required")
    try:
        expiry = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AutonomyLadderError("level_3_policy_expiry_malformed", f"level 3 authority policy_expires_at_utc is not valid ISO-8601 UTC: {expires_raw!r}: {exc}") from exc
    if expiry.tzinfo is None:
        raise AutonomyLadderError("level_3_policy_expiry_malformed", "level 3 authority policy_expires_at_utc must be timezone-aware UTC")
    if expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise AutonomyLadderError("level_3_policy_expired", f"level 3 authority policy has expired at {expires_raw}")

    authority_version = str(binding.get("authority_version") or "").strip()
    _require(authority_version == "main", "level_3_policy_unauthorized", "level 3 authority must remain bound to authority_version=main")
    authority_commit = str(binding.get("authority_commit") or "").strip()
    _require(bool(authority_commit), "level_3_policy_unauthorized", "level 3 authority must define authority_commit")
    _require(str(policy.get("authority_commit") or "").strip() == authority_commit, "level_3_policy_unauthorized", "level 3 authority commit must match the approved policy artifact")
    _require(_is_git_ancestor(ROOT, authority_commit, _git_head(ROOT)), "level_3_policy_stale", "level 3 authority policy commit must be an ancestor of the current repository head")

    return policy


def _git_head(repo_root: Path) -> str:
    try:
        process = subprocess.Popen(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _stderr = process.communicate()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, ["git", "rev-parse", "HEAD"], output=stdout)
        return stdout.strip()
    except Exception as exc:
        raise AutonomyLadderError("contract_invalid", f"unable to read repository head for level 3 policy validation: {repo_root}") from exc


def _validate_level(level: dict[str, Any], number: int) -> None:
    _require(level.get("level") == number, "contract_invalid", f"level {number} is malformed")
    _require(isinstance(level.get("name"), str) and level["name"].strip(), "contract_invalid", f"level {number} must have a name")
    _require(isinstance(level.get("enabled"), bool), "contract_invalid", f"level {number} must have an enabled flag")
    _require(isinstance(level.get("status"), str) and level["status"].strip(), "contract_invalid", f"level {number} must have a status")
    _require(isinstance(level.get("allowed_actions"), list), "contract_invalid", f"level {number} must define allowed_actions")
    _require(isinstance(level.get("forbidden_actions"), list), "contract_invalid", f"level {number} must define forbidden_actions")
    _require(isinstance(level.get("required_artifacts"), list), "contract_invalid", f"level {number} must define required_artifacts")
    _require(isinstance(level.get("approval_requirements"), dict), "contract_invalid", f"level {number} must define approval_requirements")
    _require(isinstance(level.get("failure_handling"), list), "contract_invalid", f"level {number} must define failure_handling")
    _require(isinstance(level.get("tests_required"), list), "contract_invalid", f"level {number} must define tests_required")


def _validate_contract(payload: dict[str, Any]) -> None:
    _require(payload.get("version") == "v1.0.0", "contract_invalid", "autonomy ladder version must remain v1.0.0")
    _require(payload.get("schema_version") == "lena_autonomy_ladder_v1", "contract_invalid", "unexpected autonomy ladder schema_version")
    _require(payload.get("node_name") == "Lena", "contract_invalid", "unexpected node_name")
    _require(payload.get("node_role") == "Node 1 of the autonomous media engine", "contract_invalid", "unexpected node_role")

    publish_freeze = payload.get("publish_freeze")
    _require(isinstance(publish_freeze, dict), "contract_invalid", "publish_freeze must be a JSON object")
    _require(isinstance(publish_freeze.get("active"), bool), "contract_invalid", "publish_freeze active flag must be boolean")
    _require(isinstance(publish_freeze.get("scope"), str) and publish_freeze["scope"].strip(), "contract_invalid", "publish_freeze scope is missing")
    _require(isinstance(publish_freeze.get("frozen_surfaces"), list), "contract_invalid", "publish_freeze frozen_surfaces must be a list")

    autonomy_rules = payload.get("autonomy_rules")
    _require(isinstance(autonomy_rules, dict), "contract_invalid", "autonomy_rules must be a JSON object")
    _require(autonomy_rules.get("auto_approval_forbidden") is True, "contract_invalid", "auto-approval must stay forbidden")
    _require(autonomy_rules.get("implicit_escalation_forbidden") is True, "contract_invalid", "implicit escalation must stay forbidden")
    _require(
        autonomy_rules.get("generation_approval_does_not_imply_posting_approval") is True,
        "contract_invalid",
        "generation approval must never imply posting approval",
    )

    levels = payload.get("levels")
    _require(isinstance(levels, list) and len(levels) == 6, "contract_invalid", "autonomy ladder must define six levels")
    by_number: dict[int, dict[str, Any]] = {}
    for level in levels:
        _require(isinstance(level, dict), "contract_invalid", "each autonomy level must be a JSON object")
        number = level.get("level")
        _require(isinstance(number, int), "contract_invalid", "each autonomy level must have an integer level")
        _require(number in LEVELS, "contract_invalid", f"unsupported autonomy level {number!r}")
        _require(number not in by_number, "contract_invalid", f"duplicate autonomy level {number!r}")
        _validate_level(level, number)
        by_number[number] = level

    _require(set(by_number) == set(LEVELS), "contract_invalid", "autonomy ladder levels 0-5 must all be present")

    for number in (0, 1, 2):
        level = by_number[number]
        _require(level.get("enabled") is True, "contract_invalid", f"level {number} must remain enabled")
        _require(level.get("status") == "active", "contract_invalid", f"level {number} must remain active")

    level3 = by_number[3]
    if publish_freeze.get("active") is True:
        _require(level3.get("enabled") is False, "contract_invalid", "level 3 must remain disabled while publish freeze is active")
        _require(level3.get("status") == "frozen_real_mode", "contract_invalid", "level 3 must remain a frozen real mode")
        _require(level3.get("future_placeholder") is False, "contract_invalid", "level 3 must not be a future placeholder")
        _require(level3.get("disabled_by_publish_freeze") is True, "contract_invalid", "level 3 must be disabled by publish freeze")
        _require(level3.get("disabled_reason") == "publish_freeze_active", "contract_invalid", "level 3 disable reason must remain publish_freeze_active")
    else:
        _require(level3.get("enabled") is True, "contract_invalid", "level 3 must be enabled when publish freeze is lifted")
        _require(level3.get("status") == "active", "contract_invalid", "level 3 must be active when publish freeze is lifted")
        _require(level3.get("future_placeholder") is False, "contract_invalid", "level 3 must not be a future placeholder")
        _require(level3.get("disabled_by_publish_freeze") is False, "contract_invalid", "level 3 must no longer be disabled by publish freeze")
        _require(not str(level3.get("disabled_reason", "")).strip(), "contract_invalid", "level 3 disable reason must be removed when publish freeze is lifted")
        binding = payload.get("level_3_authority")
        policy = _validate_level_three_authority(binding)
        _require(isinstance(binding, dict), "contract_invalid", "level 3 must define a level_3_authority binding")
        _require(binding.get("policy_id") == policy.get("policy_id"), "contract_invalid", "level 3 authority policy_id must match the policy artifact")
        _require(binding.get("policy_version") == policy.get("policy_version"), "contract_invalid", "level 3 authority policy_version must match the policy artifact")
        _require(
            binding.get("policy_path") == LEVEL_3_POLICY_PATH.as_posix(),
            "contract_invalid",
            "level 3 authority policy_path must be repository-relative and normalized",
        )

    for number in (4, 5):
        level = by_number[number]
        _require(level.get("enabled") is False, "contract_invalid", f"level {number} must remain disabled")
        _require(level.get("status") == "future_only", "contract_invalid", f"level {number} must remain future-only")


def load_contract() -> dict[str, Any]:
    payload = _read_contract()
    _validate_contract(payload)
    return payload


def contract_summary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = payload if payload is not None else load_contract()
    levels = contract.get("levels", [])
    level_3 = next((level for level in levels if isinstance(level, dict) and level.get("level") == 3), {})
    level_3_authority = contract.get("level_3_authority", {}) if isinstance(contract.get("level_3_authority", {}), dict) else {}
    active_levels = [
        int(level.get("level"))
        for level in levels
        if isinstance(level, dict) and level.get("enabled") is True
    ]
    return {
        "contract_path": str(CONTRACT_PATH),
        "version": contract.get("version"),
        "schema_version": contract.get("schema_version"),
        "publish_freeze_active": bool(contract.get("publish_freeze", {}).get("active")),
        "active_levels": active_levels,
        "level_3_enabled": bool(level_3.get("enabled")),
        "level_3_disabled_by_publish_freeze": bool(level_3.get("disabled_by_publish_freeze")),
        "level_3_authority_policy_id": level_3_authority.get("policy_id", ""),
        "level_3_authority_policy_path": level_3_authority.get("policy_path", ""),
    }


def get_level(contract: dict[str, Any], number: int) -> dict[str, Any]:
    for level in contract.get("levels", []):
        if isinstance(level, dict) and level.get("level") == number:
            return level
    raise AutonomyLadderError("contract_invalid", f"autonomy level {number} is missing")


def blocked_report(exc: AutonomyLadderBlocked) -> dict[str, Any]:
    return exc.report


def assert_allowed(
    tool_name: str,
    *,
    level: int,
    action: str,
) -> dict[str, Any]:
    contract = load_contract()
    level_data = get_level(contract, level)
    if level in (4, 5):
        raise AutonomyLadderBlocked(
            "future_level_disabled",
            f"autonomy level {level} is future-only and cannot execute",
            tool_name=tool_name,
            level=level,
            action=action,
            contract=contract,
        )
    if level == 3:
        publish_freeze = contract.get("publish_freeze", {})
        if publish_freeze.get("active") is True:
            raise AutonomyLadderBlocked(
                "publish_freeze_active",
                "publish freeze is active, so level 3 posting remains blocked",
                tool_name=tool_name,
                level=level,
                action=action,
                contract=contract,
            )
    if level_data.get("enabled") is not True:
        raise AutonomyLadderBlocked(
            "level_disabled",
            f"autonomy level {level} is disabled",
            tool_name=tool_name,
            level=level,
            action=action,
            contract=contract,
        )
    if action not in set(level_data.get("allowed_actions", [])):
        raise AutonomyLadderBlocked(
            "action_not_allowed",
            f"{tool_name} is not allowed to perform {action!r} at autonomy level {level}",
            tool_name=tool_name,
            level=level,
            action=action,
            contract=contract,
        )
    if action in set(level_data.get("forbidden_actions", [])):
        raise AutonomyLadderBlocked(
            "action_forbidden",
            f"{tool_name} is forbidden from performing {action!r} at autonomy level {level}",
            tool_name=tool_name,
            level=level,
            action=action,
            contract=contract,
        )
    return contract
