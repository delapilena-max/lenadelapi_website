from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

PLATFORMS = "Instagram Feed,Facebook Page"


def run_step(label: str, cmd: list[str], dry_run: bool = False, skip_on_dry: bool = False) -> dict:
    if dry_run and skip_on_dry:
        print(f"[orchestrator] DRY-RUN skip: {label}")
        return {"label": label, "ok": True, "skipped": True, "reason": "dry_run"}
    print(f"\n[orchestrator] >>> {label}")
    print("  " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT), text=True)
    ok = result.returncode == 0
    status = "PASS" if ok else f"FAIL(rc={result.returncode})"
    print(f"[orchestrator] <<< {label}  {status}")
    return {"label": label, "ok": ok, "returncode": result.returncode}


def main() -> int:
    ap = argparse.ArgumentParser(description="Lena daily 3-photo orchestrator v1")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="Skip live generation; run rest without posting")
    args = ap.parse_args()

    day = args.date
    dr = args.dry_run
    started_at = datetime.now().isoformat(timespec="seconds")
    print(f"[orchestrator] date={day}  dry_run={dr}  started={started_at}")

    steps: list[dict] = []

    # Step 1 — generate 3 Kling slots (skip entirely on dry-run)
    gen_cmd = [PY, "tools/generation/lena_run_daily_kling_omni_live_v1.py",
               "--date", day,
               "--execute-live",
               "--confirm-daily-three-photo-kling-omni-live"]
    steps.append(run_step("generate", gen_cmd, dry_run=dr, skip_on_dry=True))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "generate")

    # Step 2 — quality gate + autonomous asset approval
    gate_cmd = [PY, "tools/lena_autonomous_asset_approval_gate_v2_6_1.py",
                "--date", day]
    steps.append(run_step("approval_gate", gate_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "approval_gate")

    # Step 3 — generate publish packets (captions, hashtags, metadata)
    packet_cmd = [PY, "tools/lena_publish_packet_director_generate_v2_4.py",
                  "--date", day]
    steps.append(run_step("packet_director", packet_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "packet_director")

    # Step 4 — build approved publish queue (Instagram Feed + Facebook Page)
    queue_cmd = [PY, "tools/lena_build_approved_publish_queue_v2_8.py",
                 "--date", day,
                 "--platforms", PLATFORMS]
    if dr:
        queue_cmd.append("--replace")
    steps.append(run_step("queue_build", queue_cmd))
    if not steps[-1]["ok"]:
        return _abort(steps, day, started_at, "queue_build")

    return _finish(steps, day, started_at, ok=True)


def _abort(steps: list, day: str, started_at: str, failed_at: str) -> int:
    print(f"\n[orchestrator] ABORTED at step: {failed_at}")
    _write_report(steps, day, started_at, ok=False, aborted_at=failed_at)
    return 1


def _finish(steps: list, day: str, started_at: str, ok: bool) -> int:
    print(f"\n[orchestrator] DONE  ok={ok}")
    _write_report(steps, day, started_at, ok=ok)
    return 0 if ok else 1


def _write_report(steps: list, day: str, started_at: str, ok: bool, aborted_at: str = "") -> None:
    outdir = ROOT / "pipeline" / "publishing" / "lena" / "orchestrator_reports" / day
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    report = {
        "ok": ok,
        "version": "v1.0",
        "date": day,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "aborted_at": aborted_at,
        "steps": steps,
    }
    path = outdir / f"orchestrator_report_{ts}_v1.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[orchestrator] report: {path}")


if __name__ == "__main__":
    sys.exit(main())
