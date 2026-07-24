"""Single entry point for one unattended Lena publish cycle.

Meant to be invoked by an OS-level scheduler (e.g. Windows Task Scheduler)
three times a day, once per approved slot keyword (morning/afternoon/
evening). Chains the three steps that must run in order for
--scheduled-autonomous to have anything valid to publish:

  1. bridge any newly-accepted QA dispositions into publish packets
     (tools/lena_build_publish_packet_v1.py)
  2. rebuild today's approved queue from those packets
     (tools/lena_build_approved_publish_queue_v2_8.py)
  3. run the scheduled-autonomous publisher for exactly this slot
     (tools/lena_autopublish_approved_queue_v2_8.py --scheduled-autonomous)

Each step already fails closed on its own (see their own modules/tests);
this wrapper does not add new safety logic, it only sequences existing,
already-tested steps in the order run_scheduled_autonomous requires (it
refuses a missing or stale queue). A step failure aborts the cycle instead
of proceeding to the next step, so a queue-build failure can never be
followed by a publish attempt against stale or absent data.

photo lane only. No replies, DMs, or outreach anywhere in this chain.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import lena_build_publish_packet_v1 as packet_bridge  # noqa: E402
from tools import lena_autopublish_approved_queue_v2_8 as autopublish  # noqa: E402

PY = sys.executable
QUEUE_BUILDER_SCRIPT = ROOT / "tools" / "lena_build_approved_publish_queue_v2_8.py"
APPROVED_PLATFORMS = ["Instagram Feed", "Facebook Page"]


class PublishCycleError(RuntimeError):
    def __init__(self, stage: str, detail: str):
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.detail = detail


def run_publish_cycle(
    *,
    day: str,
    slot_keyword: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "date": day, "slot_keyword": slot_keyword, "dry_run": dry_run}

    try:
        bridge_report = packet_bridge.build_publish_packets(day)
    except Exception as exc:  # noqa: BLE001 -- stage must fail closed, not raise past the wrapper
        result["failed_stage"] = "build_publish_packets"
        result["error"] = str(exc)
        return result
    result["bridge_report"] = bridge_report

    # lena_build_approved_publish_queue_v2_8.py exposes its logic only
    # through main() (argparse + direct file I/O, no importable report
    # function) -- invoked as a subprocess, matching how this repo's own
    # autopublisher already chains tool scripts (see SYNC_POSTED above).
    proc = subprocess.run(
        [
            PY,
            str(QUEUE_BUILDER_SCRIPT),
            "--date",
            day,
            "--platforms",
            ",".join(APPROVED_PLATFORMS),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        queue_report = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        queue_report = None
    if proc.returncode != 0 or not isinstance(queue_report, dict) or not queue_report.get("ok"):
        result["failed_stage"] = "build_approved_publish_queue"
        result["error"] = queue_report if queue_report is not None else (proc.stderr or proc.stdout)
        return result
    result["queue_report"] = queue_report

    try:
        publish_report = autopublish.run_scheduled_autonomous(
            day=day,
            slot_keyword=slot_keyword,
            limit=1,
            dry_run=dry_run,
        )
    except autopublish.AutopublishError as exc:
        result["failed_stage"] = "run_scheduled_autonomous"
        result["error_code"] = exc.code
        result["error"] = exc.detail
        return result
    result["publish_report"] = publish_report

    result["ok"] = bool(publish_report.get("ok", True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--slot-keyword", required=True, choices=["morning", "afternoon", "evening"], dest="slot_keyword")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = run_publish_cycle(day=args.date, slot_keyword=args.slot_keyword, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
