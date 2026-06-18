from __future__ import annotations
import argparse, csv, json, subprocess, sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
QUEUE_FIELDS = [
    "queue_id","date","created_at","slot_id","platform","media_type","lane","asset_status","asset_path",
    "caption","short_caption","pinned_comment","story_prompt","post_poll","keyword_notes",
    "public_text_score","public_text_decision","publish_state","publish_mode","connector_path",
    "post_url","posted_at","failure_reason","attempt_count","notes"
]

def qpath(day):
    return ROOT / "pipeline" / "publishing" / "lena" / "approved_queue" / day / "lena_approved_publish_queue_v2_8.csv"

def read_queue(day):
    path = qpath(day)
    if not path.exists():
        return path, []
    return path, list(csv.DictReader(path.open("r", encoding="utf-8")))

def write_queue(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
        wr.writeheader()
        wr.writerows([{k: r.get(k, "") for k in QUEUE_FIELDS} for r in rows])

def connector_payload(row):
    return {
        "queue_id": row.get("queue_id"),
        "date": row.get("date"),
        "platform": row.get("platform"),
        "slot_id": row.get("slot_id"),
        "asset_path": row.get("asset_path"),
        "media_type": row.get("media_type"),
        "caption": row.get("caption"),
        "pinned_comment": row.get("pinned_comment"),
        "story_prompt": row.get("story_prompt"),
        "post_poll": row.get("post_poll"),
        "keyword_notes": row.get("keyword_notes"),
        "lane": row.get("lane")
    }

def _parse_connector_stdout(raw: str) -> dict | None:
    """Parse connector stdout JSON.

    Try full-body first — handles pretty-printed (indent=2) multi-line output where
    the last line is just '}' and would fail on its own. Fall back to last-line for
    connectors that prefix diagnostic text before a single-line JSON result.
    Returns None if both attempts fail.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return json.loads(raw.splitlines()[-1])
    except Exception:
        pass
    return None


def run_connector(row, dry_run=False):
    connector = row.get("connector_path") or ""
    payload = connector_payload(row)
    outbox = ROOT / "pipeline" / "publishing" / "lena" / "dispatch_outbox" / row.get("date","")
    outbox.mkdir(parents=True, exist_ok=True)
    safe_platform = "".join(c if c.isalnum() or c in "-_" else "_" for c in row.get("platform","platform"))
    payload_path = outbox / f"{row.get('queue_id')}_{safe_platform}_payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if dry_run:
        return {"ok": True, "dry_run": True, "posted": False, "reason": "dry_run_preview_only_queue_not_mutated", "payload": str(payload_path)}

    if not connector:
        return {"ok": False, "posted": False, "reason": "missing_connector_path", "payload": str(payload_path)}
    cpath = ROOT / connector
    if not cpath.exists():
        return {"ok": False, "posted": False, "reason": f"connector_not_installed: {connector}", "payload": str(payload_path)}

    p = subprocess.run([PY, connector, "--payload", str(payload_path)], cwd=str(ROOT), capture_output=True, text=True)
    parsed = _parse_connector_stdout(p.stdout)
    if parsed is not None:
        data = parsed
    else:
        data = {"ok": False, "raw_stdout": p.stdout[-1000:], "stderr": p.stderr[-1000:]}
    data["returncode"] = p.returncode
    data["connector"] = connector
    data["payload"] = str(payload_path)
    if p.returncode != 0:
        data["ok"] = False
    return data

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--platforms", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--slot-keyword", default="", dest="slot_keyword")
    ap.add_argument("--max-attempts", type=int, default=3, dest="max_attempts")
    args = ap.parse_args()

    path, rows = read_queue(args.date)
    if not rows:
        print(json.dumps({"ok": False, "version": "v2.8.1", "error": f"missing/empty queue: {path}"}, indent=2))
        return 1

    platform_filter = set(p.strip().lower() for p in args.platforms.replace(";", ",").split(",") if p.strip())
    results, processed = [], 0
    writable_rows = [dict(r) for r in rows]

    for row in writable_rows:
        if row.get("publish_state") == "posted":
            continue
        if row.get("publish_state") not in ("queued", "failed", "ready_for_connector", "dry_run", ""):
            continue
        if platform_filter and row.get("platform","").lower() not in platform_filter:
            continue
        if args.limit and processed >= args.limit:
            continue
        if args.slot_keyword and args.slot_keyword.lower() not in row.get("slot_id","").lower():
            continue

        processed += 1
        result = run_connector(row, dry_run=args.dry_run)
        now = datetime.now().isoformat(timespec="seconds")

        if args.dry_run:
            # Critical repair: do NOT mutate queue state on dry-run.
            pass
        elif result.get("ok") and result.get("posted"):
            row["publish_state"] = "posted"
            row["posted_at"] = result.get("posted_at") or now
            row["post_url"] = result.get("post_url", "")
            row["failure_reason"] = ""
            row["attempt_count"] = "0"
            if result.get("post_id"):
                row["notes"] = f"post_id:{result['post_id']}"
        else:
            reason = result.get("reason", "connector_failed_or_not_configured")
            attempts = int(row.get("attempt_count") or 0) + 1
            row["attempt_count"] = str(attempts)
            if attempts >= args.max_attempts:
                row["publish_state"] = "abandoned"
            elif "connector_not_installed" in reason or reason == "missing_connector_path":
                row["publish_state"] = "ready_for_connector"
            else:
                row["publish_state"] = "failed"
            row["failure_reason"] = reason

        results.append({"queue_id": row.get("queue_id"), "platform": row.get("platform"), "slot_id": row.get("slot_id"), "result": result, "state_after": row.get("publish_state")})

    if not args.dry_run:
        write_queue(path, writable_rows)

    outdir = ROOT / "pipeline" / "publishing" / "lena" / "dispatch_reports" / args.date
    outdir.mkdir(parents=True, exist_ok=True)
    report = {
        "ok": True,
        "version": "v2.8.1",
        "date": args.date,
        "dry_run": args.dry_run,
        "queue_mutated": not args.dry_run,
        "processed": processed,
        "posted_count": sum(1 for r in results if r["state_after"] == "posted"),
        "ready_for_connector_count": sum(1 for r in results if r["state_after"] == "ready_for_connector"),
        "failed_count": sum(1 for r in results if r["state_after"] == "failed"),
        "queue_csv": str(path),
        "results": results
    }
    report_path = outdir / f"approved_queue_autopublish_report_{datetime.now().strftime('%H%M%S')}_v2_8_1.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["ok","version","date","dry_run","queue_mutated","processed","posted_count","ready_for_connector_count","failed_count","queue_csv"]} | {"report": str(report_path)}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
