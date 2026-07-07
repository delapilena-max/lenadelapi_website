from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict

from pipeline.env_loader import load_env_once
from pipeline.lena_contract_workflow import package_ready_outputs
from pipeline.identity import lena_identity


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "pipeline" / "queue"
load_env_once(ROOT)


def _target_date() -> str:
    return os.environ.get("LENA_PRODUCTION_DATE") or os.environ.get("LENA_PREFLIGHT_DATE") or date.today().isoformat()


def _queue_items(date_str: str) -> list[Path]:
    return sorted(p for p in QUEUE.glob(f"{date_str}-*.json") if p.is_file())


def _kling_backend_name() -> str:
    # Batch 2 (2026-07-05): fail-closed check now owned by
    # pipeline/identity/lena_identity.py instead of a local copy.
    lena_identity.require_expected_photo_element()
    return "kling_apilena_api_only"


def run_lena_production() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": True,
        "component": "lena_production",
        "backend": _kling_backend_name(),
        "steps": []
    }
    target_date = _target_date()
    result["target_date"] = target_date

    prepare_proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "lena_prepare_daily_workorders_brain.py"),
            "--date",
            target_date,
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    manifest_path = ROOT / "pipeline" / "kling_workorders" / target_date / "daily_workorders.json"
    result["steps"].append({
        "step": "prepare_daily_production_manifest",
        "ok": prepare_proc.returncode == 0 and manifest_path.exists(),
        "path": str(manifest_path),
        "returncode": prepare_proc.returncode,
        "stdout_tail": prepare_proc.stdout[-4000:],
        "stderr_tail": prepare_proc.stderr[-4000:],
    })
    if prepare_proc.returncode != 0 or not manifest_path.exists():
        result["ok"] = False
        result["state"] = "FAILED_PREPARING_DAILY_WORKORDERS"
        return result

    generate_enabled = os.environ.get("CONTENT_BOT_KLING_EXECUTE", "0").lower() in {"1", "true", "yes"}

    if generate_enabled:
        try:
            from pipeline.kling_apilena_api_executor import run_executor as run_kling_api_production

            parsed_result = run_kling_api_production(target_date)
            step_name = "kling_apilena_api_generation"
            result["steps"].append({
                "step": step_name,
                "ok": bool(parsed_result.get("ok")),
                "result": parsed_result,
            })
        except Exception as exc:
            result["steps"].append({
                "step": "kling_generation",
                "ok": False,
                "error": str(exc)
            })
    else:
        result["steps"].append({
            "step": "kling_generation",
            "ok": True,
            "status": "skipped",
            "reason": "CONTENT_BOT_KLING_EXECUTE is not enabled"
        })

    packaged = package_ready_outputs(target_date)
    result["steps"].append({
        "step": "package_completed_kling_outputs",
        "ok": packaged.get("ok", False),
        "result": packaged
    })

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "lena_preflight.py")],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        env={**os.environ, "LENA_PREFLIGHT_DATE": target_date},
    )

    queue_items = _queue_items(target_date)
    preflight_ok = proc.returncode == 0
    queue_ready = preflight_ok and len(queue_items) > 0

    result["steps"].append({
        "step": "contract_preflight",
        "ok": preflight_ok,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:]
    })

    result["queue_items"] = [str(p) for p in queue_items]
    result["queue_item_count"] = len(queue_items)
    result["preflight_passed"] = preflight_ok
    result["queue_ready_for_posting"] = queue_ready
    result["ok"] = all(bool(step.get("ok")) for step in result["steps"])

    if queue_ready:
        result["state"] = "READY_TO_POST"
    elif packaged.get("waiting"):
        result["state"] = "WAITING_FOR_KLING_ASSETS"
    else:
        result["state"] = "WAITING_FOR_KLING_GENERATION"

    return result


def main() -> int:
    result = run_lena_production()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
