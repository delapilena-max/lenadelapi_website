from __future__ import annotations
import json
import sys

_LEGACY_FLAG = "--allow-legacy-openart-seedance"
if _LEGACY_FLAG not in sys.argv:
    print(json.dumps({
        "ok": False,
        "legacy_blocked": True,
        "script": "run_lena_provider_only_daily_v1_5_2.py",
        "message": (
            "This runner targets the OpenArt/Seedance provider pipeline, "
            "which is no longer the active Lena path. "
            "Use lena_strategy_autonomy_run_v1.py or lena_daily_orchestrator_v1.py instead."
        ),
        "use_instead": [
            "tools/lena_strategy_autonomy_run_v1.py",
            "tools/lena_daily_orchestrator_v1.py",
        ],
        "override_flag_required": _LEGACY_FLAG,
    }, indent=2))
    sys.exit(1)

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

def run(cmd: list[str], optional: bool = False) -> int:
    print("\n> " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0 and not optional:
        raise SystemExit(proc.returncode)
    return proc.returncode

def main() -> int:
    ap = argparse.ArgumentParser(description="Provider-only daily runner: generate/route OpenArt+Seedance workorders and stop before Kling.")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--allow-missing-workorder", action="store_true")
    args = ap.parse_args()

    workorder = ROOT / "pipeline" / "kling_workorders" / args.date / "daily_workorders.json"
    if not workorder.exists():
        msg = f"missing workorder: {workorder}"
        if args.allow_missing_workorder:
            print(json.dumps({"ok": False, "error": msg, "next": "Run existing generation planner or create daily_workorders.json first."}, indent=2))
            return 1
        print(msg)
        return 1

    steps = [
        [PY, "tools/lena_node_validate_v1_3.py"],
        [PY, "tools/lena_enforce_daily_workorder_contract.py", str(workorder)],
        [PY, "tools/lena_influencer_node_v1_3.py", str(workorder)],
        [PY, "tools/lena_apply_growth_layer_v1_3_1.py", str(workorder)],
        [PY, "tools/lena_apply_reel_overlay_brief_v1_4.py", str(workorder)],
    ]

    optional_steps = [
        [PY, "tools/lena_apply_decision_context_v1_4_1.py", str(workorder)],
    ]

    final_steps = [
        [PY, "tools/lena_route_provider_v1_5.py", str(workorder)],
        [PY, "tools/lena_prepare_openart_seedance_workorders_v1_5.py", str(workorder)],
        [PY, "tools/lena_enhance_openart_workorders_v1_5_2.py", "--date", args.date],
    ]

    for step in steps:
        run(step)
    for step in optional_steps:
        if (ROOT / step[1]).exists():
            run(step, optional=True)
        else:
            print(f"optional step missing, skipped: {step[1]}")
    for step in final_steps:
        run(step)

    out_dir = ROOT / "pipeline" / "provider_workorders" / "openart_seedance" / args.date
    print(json.dumps({
        "ok": True,
        "version": "v1.5.2",
        "mode": "provider_only_no_kling",
        "date": args.date,
        "workorder": str(workorder),
        "provider_workorder_dir": str(out_dir),
        "markdown": str(out_dir / "OPENART_SEEDANCE_MANUAL_WORKORDERS.md"),
        "stopped_before": "Kling direct executor"
    }, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
