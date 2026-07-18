from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STRATEGY_RUNNER = ROOT / "tools" / "lena_strategy_autonomy_run_v1.py"
ANALYTICS_SYNC = ROOT / "tools" / "lena_sync_architecture_a_receipts_to_metrics_v1.py"
REPORTS = ROOT / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"

AUTONOMOUS_STAGES = [
    "strategy_autonomy_run_dry_run",
    "analytics_intake_sync_dry_run",
]
MANUAL_STAGES = [
    "live_meta_refresh",
    "provider_generation",
    "image_qa",
    "caption_package_completion",
    "publishing",
    "publish_receipt",
    "live_analytics_refresh",
    "recurring_scheduler",
]


def now_ts() -> str:
    return datetime.now().strftime("%H%M%S")


def command_text(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd)


def run_step(label: str, cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "label": label,
        "cmd": cmd,
        "cmd_text": command_text(cmd),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def report_path(day: str, stamp: str) -> Path:
    return REPORTS / day / f"lena_strategy_analytics_dry_run_cycle_{day}_{stamp}.json"


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"dry-run cycle report already exists: {path}")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_json_stdout(text: str) -> dict:
    raw = (text or "").strip()
    if not raw or not raw.startswith("{"):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_strategy_command(day: str, queue_limit: int, recipes: str) -> list[str]:
    cmd = [
        PY,
        str(STRATEGY_RUNNER),
        "--date",
        day,
        "--queue-limit",
        str(queue_limit),
    ]
    if recipes:
        cmd.extend(["--recipes", recipes])
    return cmd


def build_analytics_sync_command() -> list[str]:
    return [PY, str(ANALYTICS_SYNC)]


def build_self_command(day: str, queue_limit: int, recipes: str) -> str:
    cmd = [
        PY,
        str(Path(__file__).resolve()),
        "--date",
        day,
        "--queue-limit",
        str(queue_limit),
    ]
    if recipes:
        cmd.extend(["--recipes", recipes])
    return command_text(cmd)


def stage_coverage(strategy_step: dict, analytics_step: dict) -> list[dict]:
    return [
        {
            "stage": "strategy_preparation",
            "label": strategy_step["label"],
            "executed": True,
            "command": strategy_step["cmd_text"],
            "run_mode": "dry_run",
            "provider_free": True,
            "publishing_free": True,
        },
        {
            "stage": "analytics_intake_sync",
            "label": analytics_step["label"],
            "executed": True,
            "command": analytics_step["cmd_text"],
            "run_mode": "dry_run",
            "apply_flag": False,
            "provider_free": True,
            "publishing_free": True,
        },
    ]


def validate_iso_date_or_exit(raw_date: str) -> str:
    try:
        parsed = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise SystemExit(f"invalid --date value {raw_date!r}: expected YYYY-MM-DD") from exc
    return parsed.isoformat()


def ensure_report_path_within_reports(path: Path) -> None:
    reports_root = REPORTS.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(reports_root):
        raise SystemExit(f"resolved report path escapes reports root: {resolved_path}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the Lena strategy-to-analytics dry-run cycle from one operator command."
    )
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--recipes", default="")
    ap.add_argument("--queue-limit", type=int, default=6)
    args = ap.parse_args()

    args.date = validate_iso_date_or_exit(args.date)

    started_at = datetime.now().isoformat(timespec="seconds")
    stamp = now_ts()
    output_path = report_path(args.date, stamp)
    ensure_report_path_within_reports(output_path)
    if output_path.exists():
        raise FileExistsError(f"dry-run cycle report already exists: {output_path}")

    steps: list[dict] = []

    strategy_cmd = build_strategy_command(args.date, args.queue_limit, args.recipes)
    strategy_step = run_step("strategy_autonomy_run_dry_run", strategy_cmd)
    steps.append(strategy_step)
    if not strategy_step["ok"]:
        payload = {
            "ok": False,
            "version": "v1",
            "date": args.date,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "args": vars(args),
            "report_path": str(output_path),
            "assumptions": {
                "strategy_runner": "invokes the existing strategy runner and does not audit its internals",
            },
            "dry_run_command": build_self_command(args.date, args.queue_limit, args.recipes),
            "safeguards": {
                "provider_calls_performed": 0,
                "publish_calls_performed": 0,
                "retry_cap": 0,
                "hard_spend_cap_usd": 0,
                "duplicate_rejection": "report_path_must_not_exist",
                "kill_switch": "no_live_command_paths",
                "qa_fail_closed": True,
                "fail_closed_stage_handling": True,
                "recurring_scheduler": False,
                "receipt_creation": "wrapper_report_json",
            },
            "stage_coverage": [],
            "stages": steps,
            "manual_stages": MANUAL_STAGES,
            "autonomous_stages": AUTONOMOUS_STAGES,
            "out_of_scope": [
                "provider_generation",
                "image_qa",
                "caption_package_completion",
                "publishing",
                "publish_receipt",
                "live_analytics_refresh",
                "recurring_scheduler",
            ],
            "failed_stage": strategy_step["label"],
        }
        write_report(output_path, payload)
        print(json.dumps({"ok": False, "report_path": str(output_path), "failed_stage": strategy_step["label"]}, indent=2))
        return 1

    strategy_payload = parse_json_stdout(strategy_step["stdout"])
    strategy_report_path = strategy_payload.get("report_path", "")
    strategy_report = {}
    if strategy_report_path:
        try:
            strategy_report = json.loads(Path(strategy_report_path).read_text(encoding="utf-8-sig"))
        except Exception:
            strategy_report = {}

    analytics_cmd = build_analytics_sync_command()
    analytics_step = run_step("analytics_intake_sync_dry_run", analytics_cmd)
    steps.append(analytics_step)
    analytics_payload = parse_json_stdout(analytics_step["stdout"])
    if not analytics_step["ok"]:
        payload = {
            "ok": False,
            "version": "v1",
            "date": args.date,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "args": vars(args),
            "report_path": str(output_path),
            "assumptions": {
                "strategy_runner": "invokes the existing strategy runner and does not audit its internals",
            },
            "dry_run_command": build_self_command(args.date, args.queue_limit, args.recipes),
            "safeguards": {
                "provider_calls_performed": 0,
                "publish_calls_performed": 0,
                "retry_cap": 0,
                "hard_spend_cap_usd": 0,
                "duplicate_rejection": "report_path_must_not_exist",
                "kill_switch": "no_live_command_paths",
                "qa_fail_closed": True,
                "fail_closed_stage_handling": True,
                "recurring_scheduler": False,
                "receipt_creation": "wrapper_report_json",
            },
            "stage_coverage": [],
            "stages": steps,
            "strategy_report_path": strategy_report_path,
            "strategy_summary": strategy_report.get("summary", {}),
            "analytics_summary": analytics_payload,
            "manual_stages": MANUAL_STAGES,
            "autonomous_stages": AUTONOMOUS_STAGES,
            "out_of_scope": [
                "provider_generation",
                "image_qa",
                "caption_package_completion",
                "publishing",
                "publish_receipt",
                "live_analytics_refresh",
                "recurring_scheduler",
            ],
            "failed_stage": analytics_step["label"],
        }
        write_report(output_path, payload)
        print(json.dumps({"ok": False, "report_path": str(output_path), "failed_stage": analytics_step["label"]}, indent=2))
        return 1

    payload = {
        "ok": True,
        "version": "v1",
        "date": args.date,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "report_path": str(output_path),
        "assumptions": {
            "strategy_runner": "invokes the existing strategy runner and does not audit its internals",
        },
        "dry_run_command": build_self_command(args.date, args.queue_limit, args.recipes),
        "safeguards": {
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "retry_cap": 0,
            "hard_spend_cap_usd": 0,
            "duplicate_rejection": "report_path_must_not_exist",
            "kill_switch": "no_live_command_paths",
            "qa_fail_closed": True,
            "fail_closed_stage_handling": True,
            "recurring_scheduler": False,
            "receipt_creation": "wrapper_report_json",
        },
        "stage_coverage": stage_coverage(strategy_step, analytics_step),
        "stages": [
            {
                "label": strategy_step["label"],
                "ok": strategy_step["ok"],
                "returncode": strategy_step["returncode"],
                "cmd": strategy_step["cmd"],
                "cmd_text": strategy_step["cmd_text"],
                "report_path": strategy_report_path,
                "report_summary": strategy_report.get("summary", {}),
            },
            {
                "label": analytics_step["label"],
                "ok": analytics_step["ok"],
                "returncode": analytics_step["returncode"],
                "cmd": analytics_step["cmd"],
                "cmd_text": analytics_step["cmd_text"],
                "stdout": analytics_step["stdout"],
                "stderr": analytics_step["stderr"],
                "analytics_summary": analytics_payload,
            },
        ],
        "strategy_report_path": strategy_report_path,
        "strategy_summary": strategy_report.get("summary", {}),
        "analytics_summary": analytics_payload,
        "autonomous_stages": AUTONOMOUS_STAGES,
        "manual_stages": MANUAL_STAGES,
        "out_of_scope": [
            "provider_generation",
            "image_qa",
            "caption_package_completion",
            "publishing",
            "publish_receipt",
            "live_analytics_refresh",
            "recurring_scheduler",
        ],
    }
    write_report(output_path, payload)
    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(output_path),
                "strategy_report_path": strategy_report_path,
                "analytics_receipts_scanned": analytics_payload.get("receipts_scanned", 0),
                "analytics_created": analytics_payload.get("created", 0),
                "analytics_updated": analytics_payload.get("updated", 0),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
