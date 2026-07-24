from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tools import lena_bounded_live_cycle_v1 as live_cycle
from tools import lena_standing_autonomy_policy_v1 as standing_autonomy


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "pipeline" / "config" / "lena_standing_autonomy_policy_v1.json"
PREP_RUNNER = ROOT / "tools" / "strategy" / "lena_run_strategy_autonomy_prep_v1.py"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
LOCK_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "full_photo_autonomy"
CONTROLLED_RECIPE_ID = "hcr_012"
CONTROLLED_WARDROBE_ID = "wc_p050"


class FullPhotoAutonomyError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise FullPhotoAutonomyError(code, detail)


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullPhotoAutonomyError("artifact_missing_or_invalid", f"{path}: {exc}") from exc
    _require(isinstance(value, dict), "artifact_missing_or_invalid", f"{path} must contain a JSON object")
    return value


def _handoff_path(day: str) -> Path:
    return NEXT_ACTIONS / day / f"lena_next_live_image_handoff_{day}.json"


def _run_prep(day: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(PREP_RUNNER),
        "--date",
        day,
        "--recipes",
        CONTROLLED_RECIPE_ID,
        "--queue-limit",
        "1",
        "--controlled-photo-autonomy",
    ]
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    _require(proc.returncode == 0, "strategy_prep_failed", (proc.stderr or proc.stdout or "strategy prep failed")[-4000:])
    handoff_path = _handoff_path(day)
    _require(handoff_path.is_file(), "strategy_handoff_missing", f"strategy prep did not create {handoff_path}")
    return {"command": command, "handoff_path": handoff_path, "stdout": proc.stdout}


def _validate_controlled_handoff(handoff_path: Path) -> dict[str, Any]:
    handoff = _read_json(handoff_path)
    selected = handoff.get("selected_candidate")
    _require(isinstance(selected, dict), "controlled_candidate_missing", "handoff selected_candidate is missing")
    _require(selected.get("recipe_id") == CONTROLLED_RECIPE_ID, "controlled_recipe_mismatch", "handoff is outside hcr_012")
    _require(selected.get("wardrobe_outfit_id") == CONTROLLED_WARDROBE_ID, "controlled_wardrobe_mismatch", "handoff is outside wc_p050")
    _require(handoff.get("live_execution_authorized") is False, "handoff_pre_authorized", "strategy handoff must remain unapproved before standing authority issuance")
    _require(handoff.get("source_reconciliation_status") == "reconciled", "reconciliation_not_aligned", "controlled handoff requires deterministic reconciliation")
    _require(handoff.get("source_reconciliation_operator_review_required") is False, "reconciliation_requires_human", "controlled handoff requires no operator reconciliation")
    return handoff


def _acquire_lock(day: str) -> Path:
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    path = LOCK_ROOT / f"{day}.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise FullPhotoAutonomyError("cycle_already_running", f"controlled photo cycle lock already exists: {path}") from exc
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(f"pid={os.getpid()}\n")
    return path


def run_controlled_cycle(
    *,
    day: str,
    schedule_slot: str,
    policy_path: Path = POLICY_PATH,
    hold_for_publish: bool = False,
    auth_root: Path | None = None,
    prep_runner: Callable[[str], dict[str, Any]] = _run_prep,
    cycle_runner: Callable[..., dict[str, Any]] = live_cycle._run_live_cycle,
) -> dict[str, Any]:
    try:
        policy_result = standing_autonomy.validate_policy_artifact(policy_path)
    except standing_autonomy.StandingAutonomyPolicyError as exc:
        raise FullPhotoAutonomyError(exc.code, exc.detail) from exc
    policy = policy_result["artifact"]
    controlled = policy.get("controlled_photo_autonomy")
    _require(isinstance(controlled, dict) and controlled.get("enabled") is True, "controlled_autonomy_disabled", "controlled photo autonomy is disabled")
    _require(controlled.get("recipe_id") == CONTROLLED_RECIPE_ID, "controlled_recipe_policy_invalid", "policy recipe is not hcr_012")
    _require(controlled.get("wardrobe_outfit_id") == CONTROLLED_WARDROBE_ID, "controlled_wardrobe_policy_invalid", "policy wardrobe is not wc_p050")
    _require(schedule_slot in set(controlled.get("schedule_slots", [])), "schedule_slot_not_authorized", "invocation does not match an authorized schedule slot")
    _require(policy.get("emergency_stop") is not True, "emergency_stop_active", "controlled photo autonomy emergency stop is active")

    lock_path = _acquire_lock(day)
    try:
        prep = prep_runner(day)
        handoff_path = Path(prep["handoff_path"]).resolve()
        handoff = _validate_controlled_handoff(handoff_path)
        resolved_auth_root = auth_root or standing_autonomy.AUTH_ROOT
        candidate_id = str((handoff.get("selected_candidate") or {}).get("candidate_id") or "")
        _require(bool(candidate_id), "controlled_candidate_id_missing", "handoff selected_candidate is missing a candidate_id")
        used_candidate_ids = standing_autonomy.collect_daily_authorized_candidate_ids(resolved_auth_root, day)
        _require(
            candidate_id not in used_candidate_ids,
            "distinct_candidate_unavailable",
            f"candidate_id {candidate_id!r} was already authorized for another slot on {day}",
        )
        try:
            authorization = standing_autonomy.issue_cycle_authorization(
                policy_path,
                handoff_path,
                schedule_slot=schedule_slot,
                auth_root=auth_root,
            )
        except standing_autonomy.StandingAutonomyPolicyError as exc:
            raise FullPhotoAutonomyError(exc.code, exc.detail) from exc
        try:
            result = cycle_runner(
                authorization["path"],
                report_root=standing_autonomy.default_daily_report_root(),
                hold_for_publish=hold_for_publish,
            )
        except Exception as exc:
            result = {
                "ok": False,
                "autonomous_disposition": "operational_failure",
                "failure": {
                    "code": str(getattr(exc, "code", "controlled_cycle_failed")),
                    "detail": str(getattr(exc, "detail", str(exc))),
                },
                "publish_authorized": False,
                "human_review_required": False,
                "exceptional_escalation_required": True,
            }
        result["scheduler"] = {
            "mode": "controlled_full_photo_autonomy",
            "schedule_slot": schedule_slot,
            "recipe_id": CONTROLLED_RECIPE_ID,
            "wardrobe_outfit_id": CONTROLLED_WARDROBE_ID,
            "human_per_photo_authorization_required": False,
        }
        return result
    finally:
        lock_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the governed full-autonomous Lena photo lane.")
    parser.add_argument("--date", default=utc_date())
    parser.add_argument("--schedule-slot", default="morning", choices=("morning", "afternoon", "evening"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--acknowledge-provider-qa-and-publish", action="store_true")
    args = parser.parse_args()
    if not args.live or not args.acknowledge_provider_qa_and_publish:
        print(json.dumps({"ok": False, "error_code": "live_activation_not_acknowledged", "provider_called": False, "published": False}, sort_keys=True))
        return 2
    try:
        report = run_controlled_cycle(day=args.date, schedule_slot=args.schedule_slot)
    except FullPhotoAutonomyError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "detail": exc.detail}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
