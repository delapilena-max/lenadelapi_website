from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "pipeline" / "influencer_nodes" / "lena" / "autonomy_ladder_v1.json"
LEVELS = (0, 1, 2, 3, 4, 5)


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


def _read_contract(path: Path | None = None) -> dict[str, Any]:
    path = path or CONTRACT_PATH
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
    _require(publish_freeze.get("active") is True, "contract_invalid", "publish_freeze must remain active")
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
    _require(level3.get("enabled") is False, "contract_invalid", "level 3 must remain disabled while publish freeze is active")
    _require(level3.get("status") == "frozen_real_mode", "contract_invalid", "level 3 must remain a frozen real mode")
    _require(level3.get("future_placeholder") is False, "contract_invalid", "level 3 must not be a future placeholder")
    _require(level3.get("disabled_by_publish_freeze") is True, "contract_invalid", "level 3 must be disabled by publish freeze")
    _require(level3.get("disabled_reason") == "publish_freeze_active", "contract_invalid", "level 3 disable reason must remain publish_freeze_active")

    for number in (4, 5):
        level = by_number[number]
        _require(level.get("enabled") is False, "contract_invalid", f"level {number} must remain disabled")
        _require(level.get("status") == "future_only", "contract_invalid", f"level {number} must remain future-only")


def load_contract(path: Path | None = None) -> dict[str, Any]:
    payload = _read_contract(path)
    _validate_contract(payload)
    return payload


def contract_summary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = payload if payload is not None else load_contract()
    levels = contract.get("levels", [])
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
        "level_3_disabled_by_publish_freeze": bool(
            next((level for level in levels if isinstance(level, dict) and level.get("level") == 3), {}).get("disabled_by_publish_freeze")
        ),
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
    allow_when_publish_freeze_active: bool = False,
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
        if publish_freeze.get("active") is True and not allow_when_publish_freeze_active:
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
