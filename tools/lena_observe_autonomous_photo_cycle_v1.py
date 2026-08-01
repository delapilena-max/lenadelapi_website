from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import lena_autonomy_daily_schedule_v1 as schedule_mod

CANONICAL_TASK_NAME = "Lena Autonomy Scheduler Driver"
SOUL_ID = "79119c27-64fc-47f8-9ff3-c174d12932aa"
TERMINAL_WATCH_RESULTS = {
    "autonomous_cycle_completed",
    "cycle_not_due_before_timeout",
    "cycle_failed",
    "scheduler_disabled",
    "evidence_inconsistent",
}

TaskProbe = Callable[[str], dict[str, Any]]
EventProbe = Callable[[str, int], list[dict[str, Any]]]


class ObserverError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ObserverError(code, detail)


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(schedule_mod.TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=schedule_mod.TZ)
    return value.astimezone(schedule_mod.TZ)


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=schedule_mod.TZ)
    return value.astimezone(schedule_mod.TZ)


def _artifact_time(payload: dict[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        value = payload.get(key)
        parsed = _parse_timestamp(value if isinstance(value, str) else None)
        if parsed is not None:
            return parsed
    return None


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ObserverError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ObserverError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObserverError(code, f"{label} must be a JSON object: {path}")
    return value


def _read_json_object_if_present(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _resolve_artifact_path(deployment_root: Path, raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return (deployment_root / path).resolve()


def _repo_relative_path(deployment_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(deployment_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _run_powershell_json(script: str) -> Any:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    return json.loads(stdout) if stdout else None


def default_task_probe(task_name: str) -> dict[str, Any]:
    escaped = task_name.replace("'", "''")
    payload = _run_powershell_json(
        f"""
$ErrorActionPreference = 'Stop'
try {{
  $task = Get-ScheduledTask -TaskName '{escaped}' -ErrorAction Stop
  $info = Get-ScheduledTaskInfo -TaskName '{escaped}' -ErrorAction Stop
  [pscustomobject]@{{
    present = $true
    task_name = $task.TaskName
    task_path = $task.TaskPath
    enabled = [bool]$task.Settings.Enabled
    state = [string]$task.State
    last_task_result = $info.LastTaskResult
    last_run_time = if ($info.LastRunTime -and $info.LastRunTime.Year -gt 1900) {{ $info.LastRunTime.ToString('o') }} else {{ $null }}
    next_run_time = if ($info.NextRunTime -and $info.NextRunTime.Year -gt 1900) {{ $info.NextRunTime.ToString('o') }} else {{ $null }}
    actions = @(
      foreach ($action in $task.Actions) {{
        [pscustomobject]@{{
          execute = [string]$action.Execute
          arguments = [string]$action.Arguments
          working_directory = [string]$action.WorkingDirectory
        }}
      }}
    )
  }} | ConvertTo-Json -Depth 6
}} catch {{
  [pscustomobject]@{{
    present = $false
    task_name = '{escaped}'
    error = $_.Exception.Message
  }} | ConvertTo-Json -Depth 6
}}
""".strip()
    )
    return payload if isinstance(payload, dict) else {"present": False, "task_name": task_name}


def default_event_probe(task_name: str, max_events: int = 120) -> list[dict[str, Any]]:
    escaped = task_name.replace("'", "''")
    payload = _run_powershell_json(
        f"""
$ErrorActionPreference = 'Stop'
$events = Get-WinEvent -LogName 'Microsoft-Windows-TaskScheduler/Operational' -MaxEvents {max_events} |
  Where-Object {{ $_.Message -like '*{escaped}*' }}
@(
  foreach ($event in $events) {{
    $xml = [xml]$event.ToXml()
    $data = [ordered]@{{}}
    foreach ($node in $xml.Event.EventData.Data) {{
      $data[$node.Name] = [string]$node.'#text'
    }}
    $taskNameValue = if ($data.Contains('TaskName')) {{ [string]$data['TaskName'] }} else {{ '' }}
    $instanceValue = if ($data.Contains('TaskInstanceId')) {{ [string]$data['TaskInstanceId'] }} elseif ($data.Contains('InstanceId')) {{ [string]$data['InstanceId'] }} else {{ '' }}
    $actionValue = if ($data.Contains('ActionName')) {{ [string]$data['ActionName'] }} elseif ($data.Contains('Path')) {{ [string]$data['Path'] }} else {{ '' }}
    $resultValue = if ($data.Contains('ResultCode') -and [string]$data['ResultCode'] -ne '') {{ [int]$data['ResultCode'] }} else {{ $null }}
    [pscustomobject]@{{
      event_id = [int]$event.Id
      record_id = [int64]$event.RecordId
      time_created = $event.TimeCreated.ToString('o')
      task_name = $taskNameValue
      instance_id = $instanceValue
      action_name = $actionValue
      result_code = $resultValue
      raw = $data
    }}
  }}
) | ConvertTo-Json -Depth 8
""".strip()
    )
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _group_task_runs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    ordered = sorted(events, key=lambda item: int(item.get("record_id", 0)))
    for event in ordered:
        instance_id = str(event.get("instance_id") or f"record-{event.get('record_id')}")
        run = grouped.setdefault(
            instance_id,
            {
                "instance_id": instance_id,
                "task_name": event.get("task_name"),
                "event_ids": [],
                "automatic_time_trigger": False,
                "started": False,
                "completed": False,
                "action_name": None,
                "result_code": None,
                "first_event_time": None,
                "last_event_time": None,
            },
        )
        event_time = _parse_timestamp(str(event.get("time_created") or ""))
        run["event_ids"].append(int(event.get("event_id", 0)))
        if event_time is not None:
            if run["first_event_time"] is None or event_time < run["first_event_time"]:
                run["first_event_time"] = event_time
            if run["last_event_time"] is None or event_time > run["last_event_time"]:
                run["last_event_time"] = event_time
        event_id = int(event.get("event_id", 0))
        if event_id == 107:
            run["automatic_time_trigger"] = True
        elif event_id == 100:
            run["started"] = True
        elif event_id == 102:
            run["completed"] = True
        elif event_id == 200 and event.get("action_name"):
            run["action_name"] = event["action_name"]
        elif event_id == 201:
            run["action_name"] = event.get("action_name") or run.get("action_name")
            run["result_code"] = event.get("result_code")
            run["completed"] = True
    runs = list(grouped.values())
    runs.sort(
        key=lambda item: (
            item["last_event_time"] or datetime.min.replace(tzinfo=schedule_mod.TZ),
            item["instance_id"],
        ),
        reverse=True,
    )
    return runs


def _slot_id_for(schedule: dict[str, Any], day: str, slot: str, deployment_root: Path) -> str | None:
    auth_dir = deployment_root / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / day
    if auth_dir.is_dir():
        for path in sorted(auth_dir.glob(f"lena_bounded_live_cycle_authorization_{day}_*.json")):
            payload = _read_json_object_if_present(path)
            if isinstance(payload, dict) and str(payload.get("schedule_slot") or "") == slot:
                slot_id = str(payload.get("slot_id") or "").strip()
                if slot_id:
                    return slot_id
    prefix = f"lenagate{day.replace('-', '')}"
    return f"{prefix}-{slot}"


def _load_scheduler_state(deployment_root: Path, day: str, slot: str) -> tuple[Path, dict[str, Any]]:
    path = deployment_root / "pipeline" / "autonomy" / "lena" / "scheduler_driver" / day / f"{slot}_state.json"
    return path, _read_json_object_if_present(path) or {"status": "not_started"}


def _load_scheduler_receipts(deployment_root: Path, day: str, slot: str) -> list[dict[str, Any]]:
    directory = deployment_root / "pipeline" / "autonomy" / "lena" / "scheduler_driver" / day
    if not directory.is_dir():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{slot}_*.json")):
        if path.name.endswith("_state.json"):
            continue
        payload = _read_json_object_if_present(path)
        if not isinstance(payload, dict):
            continue
        receipts.append(
            {
                "path": path,
                "relative_path": _repo_relative_path(deployment_root, path),
                "payload": payload,
                "recorded_at": _artifact_time(payload, "recorded_at"),
            }
        )
    receipts.sort(key=lambda item: item["recorded_at"] or datetime.min.replace(tzinfo=schedule_mod.TZ))
    return receipts


def _load_authorization(deployment_root: Path, day: str, slot_id: str) -> dict[str, Any] | None:
    path = deployment_root / "pipeline" / "approvals" / "lena" / "bounded_live_cycles" / day / f"lena_bounded_live_cycle_authorization_{day}_{slot_id}.json"
    payload = _read_json_object_if_present(path)
    if payload is None:
        return None
    return {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload}


def _load_generation_artifacts(deployment_root: Path, day: str, slot_id: str) -> dict[str, Any]:
    root = deployment_root / "pipeline" / "approvals" / "lena" / "generation" / day
    manual_approval_path = root / f"{slot_id}_higgsfield_generation_approval.json"
    standing_approval_path = root / f"{slot_id}_higgsfield_standing_autonomy_generation_approval.json"
    claim_path = root / f"{slot_id}_higgsfield_generation_claim.json"
    receipt_path = root / f"{slot_id}_higgsfield_generation_execution_receipt.json"
    return {
        "manual_approval": {"path": manual_approval_path, "relative_path": _repo_relative_path(deployment_root, manual_approval_path), "payload": _read_json_object_if_present(manual_approval_path)},
        "standing_approval": {"path": standing_approval_path, "relative_path": _repo_relative_path(deployment_root, standing_approval_path), "payload": _read_json_object_if_present(standing_approval_path)},
        "claim": {"path": claim_path, "relative_path": _repo_relative_path(deployment_root, claim_path), "payload": _read_json_object_if_present(claim_path)},
        "execution_receipt": {"path": receipt_path, "relative_path": _repo_relative_path(deployment_root, receipt_path), "payload": _read_json_object_if_present(receipt_path)},
    }


def _load_manifest(deployment_root: Path, day: str, slot_id: str) -> dict[str, Any] | None:
    path = deployment_root / "pipeline" / "higgsfield_debug" / day / slot_id / "result_manifest.json"
    payload = _read_json_object_if_present(path)
    if payload is None:
        return None
    return {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload}


def _load_identity_verification(deployment_root: Path, day: str, slot_id: str) -> dict[str, Any] | None:
    path = deployment_root / "pipeline" / "higgsfield_debug" / day / slot_id / "identity_verification.json"
    payload = _read_json_object_if_present(path)
    if payload is None:
        return None
    return {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload}


def _load_qa_disposition(deployment_root: Path, day: str, slot_id: str) -> dict[str, Any] | None:
    root = deployment_root / "pipeline" / "asset_review" / "lena" / day
    if not root.is_dir():
        return None
    for path in sorted(root.glob(f"{slot_id}__*_qa_disposition.json")):
        payload = _read_json_object_if_present(path)
        if isinstance(payload, dict):
            return {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload}
    return None


def _load_publish_packet_entry(deployment_root: Path, day: str, slot_id: str) -> dict[str, Any] | None:
    path = deployment_root / "pipeline" / "publish_packets" / "lena" / day / "lena_publish_packets_v2_4.json"
    payload = _read_json_object_if_present(path)
    if payload is None:
        return None
    packets = payload.get("packets")
    if not isinstance(packets, list):
        return None
    for packet in packets:
        if isinstance(packet, dict) and str(packet.get("slot_id") or "") == slot_id:
            return {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": packet}
    return None


def _load_clean_provenance(deployment_root: Path, packet: dict[str, Any] | None) -> dict[str, Any] | None:
    if packet is None:
        return None
    payload = packet["payload"]
    path = _resolve_artifact_path(deployment_root, str(payload.get("clean_export_report_path") or ""))
    if path is None:
        return None
    clean_payload = _read_json_object_if_present(path)
    if clean_payload is None:
        return None
    return {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": clean_payload}


def _queue_rows_for_slot(deployment_root: Path, day: str, slot_id: str) -> list[dict[str, Any]]:
    path = deployment_root / "pipeline" / "publishing" / "lena" / "approved_queue" / day / "lena_approved_publish_queue_v2_8.csv"
    rows = _load_csv_rows(path)
    results = []
    for row in rows:
        if str(row.get("slot_id") or "") != slot_id:
            continue
        results.append({"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": row})
    return results


def _publish_receipts_for_slot(deployment_root: Path, day: str, slot_id: str) -> list[dict[str, Any]]:
    root = deployment_root / "pipeline" / "publishing" / "lena" / "approved_queue_receipts" / day / slot_id
    if not root.is_dir():
        return []
    receipts = []
    for path in sorted(root.glob("*_publish_receipt.json")):
        payload = _read_json_object_if_present(path)
        if isinstance(payload, dict):
            receipts.append({"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload})
    return receipts


def _dispatch_reports_for_slot(deployment_root: Path, day: str, slot_id: str) -> list[dict[str, Any]]:
    root = deployment_root / "pipeline" / "publishing" / "lena" / "dispatch_reports" / day
    if not root.is_dir():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(root.glob("approved_queue_autopublish_report_*.json")):
        payload = _read_json_object_if_present(path)
        if not isinstance(payload, dict):
            continue
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        for item in results:
            if isinstance(item, dict) and str(item.get("slot_id") or "") == slot_id:
                reports.append({"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload, "result": item})
                break
    return reports


def _latest_scheduler_driver_day(deployment_root: Path) -> str | None:
    root = deployment_root / "pipeline" / "autonomy" / "lena" / "scheduler_driver"
    if not root.is_dir():
        return None
    days = sorted(child.name for child in root.iterdir() if child.is_dir())
    return days[-1] if days else None


def _latest_execution_receipt(deployment_root: Path) -> dict[str, Any] | None:
    root = deployment_root / "pipeline" / "approvals" / "lena" / "generation"
    if not root.is_dir():
        return None
    latest: dict[str, Any] | None = None
    latest_time: datetime | None = None
    for path in root.rglob("*_higgsfield_generation_execution_receipt.json"):
        payload = _read_json_object_if_present(path)
        if not isinstance(payload, dict):
            continue
        recorded_at = _artifact_time(payload, "receipt_written_at_utc")
        if latest is None or (recorded_at is not None and (latest_time is None or recorded_at > latest_time)):
            latest = {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload}
            latest_time = recorded_at
    return latest


def _latest_queue_row(deployment_root: Path) -> dict[str, Any] | None:
    root = deployment_root / "pipeline" / "publishing" / "lena" / "approved_queue"
    if not root.is_dir():
        return None
    latest: dict[str, Any] | None = None
    latest_time: datetime | None = None
    for path in root.rglob("lena_approved_publish_queue_v2_8.csv"):
        for row in _load_csv_rows(path):
            created = _parse_timestamp(str(row.get("created_at") or ""))
            if latest is None or (created is not None and (latest_time is None or created > latest_time)):
                latest = {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": row}
                latest_time = created
    return latest


def _latest_publish_receipt(deployment_root: Path) -> dict[str, Any] | None:
    root = deployment_root / "pipeline" / "publishing" / "lena" / "approved_queue_receipts"
    if not root.is_dir():
        return None
    latest: dict[str, Any] | None = None
    latest_time: datetime | None = None
    for path in root.rglob("*_publish_receipt.json"):
        payload = _read_json_object_if_present(path)
        if not isinstance(payload, dict):
            continue
        captured = _artifact_time(payload, "captured_at_utc")
        if latest is None or (captured is not None and (latest_time is None or captured > latest_time)):
            latest = {"path": path, "relative_path": _repo_relative_path(deployment_root, path), "payload": payload}
            latest_time = captured
    return latest


def _next_governed_slot(now: datetime) -> dict[str, Any]:
    for day_offset in range(0, 3):
        day = (now.date() + timedelta(days=day_offset)).isoformat()
        schedule = schedule_mod.compute_daily_schedule(day)
        for slot in schedule_mod.SLOT_ORDER:
            generation_at = schedule_mod.generation_at(schedule, slot)
            publish_at = schedule_mod.publish_at(schedule, slot)
            if now <= publish_at:
                return {
                    "date": day,
                    "schedule_slot": slot,
                    "generation_at": generation_at.isoformat(),
                    "publish_at": publish_at.isoformat(),
                    "due_now": now >= generation_at,
                    "schedule_fingerprint_sha256": schedule["fingerprint_sha256"],
                }
    raise ObserverError("no_future_slot", "failed to compute a future governed slot within the next three schedule days")


def _runs_in_window(runs: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    selected = []
    for run in runs:
        last_event_time = run.get("last_event_time")
        if not isinstance(last_event_time, datetime):
            continue
        if start <= last_event_time <= end:
            selected.append(run)
    return selected


def _issue(stage: str, code: str, detail: str, *, artifact_path: str | None = None, timestamp: str | None = None) -> dict[str, Any]:
    item = {"stage": stage, "code": code, "detail": detail}
    if artifact_path:
        item["artifact_path"] = artifact_path
    if timestamp:
        item["timestamp"] = timestamp
    return item


def _build_stage(stage: str, status: str, *, artifact_path: str | None = None, summary: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"stage": stage, "status": status}
    if artifact_path:
        payload["artifact_path"] = artifact_path
    if summary:
        payload["summary"] = summary
    if extra:
        payload.update(extra)
    return payload


def _stage_from_optional_payload(stage: str, record: dict[str, Any] | None, *, report_type_key: str = "report_type") -> dict[str, Any]:
    if record is None:
        return _build_stage(stage, "missing")
    payload = record["payload"]
    summary = str(payload.get(report_type_key) or payload.get("schema_version") or "present")
    return _build_stage(stage, "present", artifact_path=record["relative_path"], summary=summary)


def _max_timestamp(left: datetime, right: datetime | None) -> datetime:
    if right is None:
        return left
    return right if right > left else left


def _observe_slot(
    deployment_root: Path,
    *,
    day: str,
    schedule_slot: str,
    now: datetime,
    task_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    schedule = schedule_mod.compute_daily_schedule(day)
    generation_at = schedule_mod.generation_at(schedule, schedule_slot)
    publish_at = schedule_mod.publish_at(schedule, schedule_slot)
    slot_id = _slot_id_for(schedule, day, schedule_slot, deployment_root)
    _require(slot_id is not None, "slot_id_unresolved", f"could not resolve slot_id for {day} {schedule_slot}")

    state_path, state_payload = _load_scheduler_state(deployment_root, day, schedule_slot)
    scheduler_receipts = _load_scheduler_receipts(deployment_root, day, schedule_slot)
    authorization = _load_authorization(deployment_root, day, slot_id)
    generation = _load_generation_artifacts(deployment_root, day, slot_id)
    manifest = _load_manifest(deployment_root, day, slot_id)
    identity = _load_identity_verification(deployment_root, day, slot_id)
    qa = _load_qa_disposition(deployment_root, day, slot_id)
    packet = _load_publish_packet_entry(deployment_root, day, slot_id)
    clean = _load_clean_provenance(deployment_root, packet)
    queue_rows = _queue_rows_for_slot(deployment_root, day, slot_id)
    publish_receipts = _publish_receipts_for_slot(deployment_root, day, slot_id)
    dispatch_reports = _dispatch_reports_for_slot(deployment_root, day, slot_id)

    observed_end = now
    if publish_receipts:
        observed_end = _max_timestamp(observed_end, _artifact_time(publish_receipts[-1]["payload"], "captured_at_utc"))
    elif qa is not None:
        observed_end = _max_timestamp(observed_end, _artifact_time(qa["payload"], "generated_at_utc"))
    relevant_runs = _runs_in_window(task_runs, generation_at - timedelta(minutes=2), observed_end + timedelta(minutes=2))
    automatic_successful_runs = [
        run for run in relevant_runs
        if run.get("automatic_time_trigger") and int(run.get("result_code") or 0) == 0
    ]

    issues: list[dict[str, Any]] = []
    chain = [
        _build_stage(
            "scheduler_driver_state",
            "present" if state_path.exists() else "missing",
            artifact_path=_repo_relative_path(deployment_root, state_path),
            summary=str(state_payload.get("status") or "not_started"),
            extra={"generation_at": generation_at.isoformat(), "publish_at": publish_at.isoformat()},
        ),
        _build_stage(
            "scheduler_task_runs",
            "present" if relevant_runs else "missing",
            summary=f"{len(automatic_successful_runs)} automatic successful run(s) in slot window",
        ),
        _stage_from_optional_payload("standing_cycle_authorization", authorization),
        _stage_from_optional_payload("standing_generation_approval", generation["standing_approval"] if generation["standing_approval"]["payload"] else None),
        _stage_from_optional_payload("manual_generation_approval", generation["manual_approval"] if generation["manual_approval"]["payload"] else None),
        _stage_from_optional_payload("generation_execution_receipt", generation["execution_receipt"] if generation["execution_receipt"]["payload"] else None),
        _stage_from_optional_payload("provider_manifest", manifest),
        _stage_from_optional_payload("identity_verification", identity, report_type_key="schema_version"),
        _stage_from_optional_payload("autonomous_local_qa", qa, report_type_key="schema_version"),
        _stage_from_optional_payload("publish_packet", packet, report_type_key="slot_id"),
        _stage_from_optional_payload("clean_derivative_provenance", clean, report_type_key="schema_version"),
        _build_stage("queue_admission", "present" if queue_rows else "missing", artifact_path=queue_rows[0]["relative_path"] if queue_rows else None, summary=f"{len(queue_rows)} queue row(s)"),
        _build_stage("automatic_publish_receipt", "present" if publish_receipts else "missing", artifact_path=publish_receipts[0]["relative_path"] if publish_receipts else None, summary=f"{len(publish_receipts)} publish receipt(s)"),
        _build_stage("dispatch_report", "present" if dispatch_reports else "missing", artifact_path=dispatch_reports[0]["relative_path"] if dispatch_reports else None, summary=f"{len(dispatch_reports)} matching report(s)"),
    ]

    if generation["manual_approval"]["payload"] is not None:
        issues.append(
            _issue(
                "generation_approval",
                "manual_generation_approval_present",
                "manual generation approval is not unattended proof",
                artifact_path=_repo_relative_path(deployment_root, generation["manual_approval"]["path"]),
            )
        )

    exec_payload = generation["execution_receipt"]["payload"]
    if exec_payload is not None:
        if str(exec_payload.get("custom_reference_id") or "") != SOUL_ID:
            issues.append(
                _issue(
                    "generation_execution",
                    "soul_id_mismatch",
                    f"expected Soul ID {SOUL_ID}",
                    artifact_path=_repo_relative_path(deployment_root, generation["execution_receipt"]["path"]),
                )
            )
        if str(exec_payload.get("outcome") or "") != "success":
            issues.append(
                _issue(
                    "generation_execution",
                    "generation_receipt_not_success",
                    f"generation outcome is {exec_payload.get('outcome')!r}",
                    artifact_path=_repo_relative_path(deployment_root, generation["execution_receipt"]["path"]),
                    timestamp=str(exec_payload.get("receipt_written_at_utc") or ""),
                )
            )
        handoff_path = _resolve_artifact_path(deployment_root, str(exec_payload.get("handoff_artifact_path") or ""))
        expected_handoff_sha = str(exec_payload.get("handoff_artifact_sha256") or "")
        if handoff_path is not None and handoff_path.is_file() and expected_handoff_sha:
            current_handoff_sha = _sha256_file(handoff_path)
            if current_handoff_sha != expected_handoff_sha:
                issues.append(
                    _issue(
                        "strategy_preparation",
                        "handoff_sha_mismatch",
                        "current handoff artifact content no longer matches the SHA bound into execution evidence",
                        artifact_path=_repo_relative_path(deployment_root, handoff_path),
                    )
                )

    manifest_payload = manifest["payload"] if manifest is not None else None
    if manifest_payload is not None:
        if int(manifest_payload.get("live_attempt_count", 0)) != 1:
            issues.append(
                _issue(
                    "generation_count",
                    "unexpected_generation_attempt_count",
                    f"expected exactly one generation attempt, saw {manifest_payload.get('live_attempt_count')!r}",
                    artifact_path=manifest["relative_path"],
                )
            )
        if str(manifest_payload.get("soul_id") or "") != SOUL_ID:
            issues.append(_issue("generation_manifest", "manifest_soul_id_mismatch", f"expected Soul ID {SOUL_ID}", artifact_path=manifest["relative_path"]))

    identity_payload = identity["payload"] if identity is not None else None
    if identity_payload is not None:
        if str(identity_payload.get("verification_result") or "") != "pass":
            issues.append(_issue("identity_verification", "identity_verification_failed", "identity verification did not pass", artifact_path=identity["relative_path"]))
        if str(identity_payload.get("soul_id") or "") != SOUL_ID:
            issues.append(_issue("identity_verification", "identity_soul_id_mismatch", f"expected Soul ID {SOUL_ID}", artifact_path=identity["relative_path"]))
        if exec_payload is not None and str(identity_payload.get("local_image_sha256") or "") != str(exec_payload.get("generated_image_sha256") or ""):
            issues.append(_issue("identity_verification", "identity_image_sha_mismatch", "identity verification SHA does not match generation receipt SHA", artifact_path=identity["relative_path"]))

    qa_payload = qa["payload"] if qa is not None else None
    if qa_payload is not None:
        if str(qa_payload.get("disposition") or "") != "accept":
            issues.append(_issue("autonomous_local_qa", "qa_rejected", f"QA disposition is {qa_payload.get('disposition')!r}", artifact_path=qa["relative_path"]))
        if str(((qa_payload.get("qa_inputs") or {}).get("qa_mode") or qa_payload.get("qa_mode") or "")) != "autonomous_local":
            issues.append(_issue("autonomous_local_qa", "qa_mode_invalid", "QA mode must be autonomous_local", artifact_path=qa["relative_path"]))
        if (qa_payload.get("provider_called") is True) or (((qa_payload.get("visual_judgment_source") or {}).get("provider_called")) is True):
            issues.append(_issue("autonomous_local_qa", "anthropic_or_external_provider_called", "QA artifact shows an external provider call", artifact_path=qa["relative_path"]))

    if authorization is not None:
        auth_payload = authorization["payload"]
        external_visual = ((auth_payload.get("controlled_photo_autonomy") or {}).get("external_visual_diagnostic") or {})
        if external_visual.get("enabled") is True:
            issues.append(_issue("authorization", "external_visual_diagnostic_enabled", "external visual diagnostic must remain disabled for unattended proof", artifact_path=authorization["relative_path"]))
        allowed_media_types = auth_payload.get("allowed_media_types") or []
        if list(allowed_media_types) != ["photo"]:
            issues.append(_issue("authorization", "non_photo_media_scope", "authorization media scope is not photo-only", artifact_path=authorization["relative_path"]))

    packet_payload = packet["payload"] if packet is not None else None
    clean_payload = clean["payload"] if clean is not None else None
    if packet_payload is not None and clean_payload is not None:
        if clean_payload.get("verified_clean") is not True:
            issues.append(_issue("clean_derivative", "clean_derivative_not_verified", "clean derivative provenance is not verified clean", artifact_path=clean["relative_path"]))
        if str(clean_payload.get("source_sha256") or "") != str(packet_payload.get("source_asset_sha256") or ""):
            issues.append(_issue("clean_derivative", "source_sha_mismatch", "clean derivative source SHA does not match the publish packet source SHA", artifact_path=clean["relative_path"]))
        if str(clean_payload.get("output_sha256") or "") != str(packet_payload.get("asset_sha256") or ""):
            issues.append(_issue("clean_derivative", "output_sha_mismatch", "clean derivative output SHA does not match the publish packet clean asset SHA", artifact_path=clean["relative_path"]))

    posted_rows = [row for row in queue_rows if str(row["payload"].get("publish_state") or "") == "posted"]
    nonterminal_rows = [row for row in queue_rows if str(row["payload"].get("publish_state") or "") != "posted"]
    if len(queue_rows) > 1:
        issues.append(_issue("duplicate_prevention", "duplicate_queue_rows", f"expected at most one queue row for {slot_id}, saw {len(queue_rows)}", artifact_path=queue_rows[0]["relative_path"]))
    if nonterminal_rows and publish_receipts:
        issues.append(_issue("duplicate_prevention", "eligible_duplicate_row_remains", "a non-posted queue row remains after publish evidence", artifact_path=nonterminal_rows[0]["relative_path"]))

    if publish_receipts:
        if len(publish_receipts) != 1:
            issues.append(_issue("automatic_publish_receipt", "unexpected_receipt_count", f"expected exactly one publish receipt, saw {len(publish_receipts)}", artifact_path=publish_receipts[0]["relative_path"]))
        receipt_payload = publish_receipts[0]["payload"]
        if receipt_payload.get("posted") is not True:
            issues.append(_issue("automatic_publish_receipt", "receipt_not_posted", "publish receipt does not record a posted result", artifact_path=publish_receipts[0]["relative_path"]))
        if not str(receipt_payload.get("post_id") or "").strip() or not str(receipt_payload.get("post_url") or "").strip():
            issues.append(_issue("automatic_publish_receipt", "receipt_missing_post_identity", "publish receipt is missing post_id or post_url", artifact_path=publish_receipts[0]["relative_path"]))
        verification = ((((receipt_payload.get("provider_result") or {}).get("extra") or {}).get("media") or {}).get("pre_container_media_verification") or {})
        if verification.get("ok") is not True:
            issues.append(_issue("media_host_verification", "host_verification_failed", "pre-container media verification did not succeed", artifact_path=publish_receipts[0]["relative_path"]))
        if queue_rows:
            row_payload = queue_rows[0]["payload"]
            if str(row_payload.get("asset_sha256") or "") and str(verification.get("sha256") or "") and str(row_payload.get("asset_sha256") or "") != str(verification.get("sha256") or ""):
                issues.append(_issue("media_host_verification", "host_sha_mismatch", "host verification SHA does not match the queue row clean asset SHA", artifact_path=publish_receipts[0]["relative_path"]))
            notes = str(row_payload.get("notes") or "")
            if "receipt_reconciled_from_dispatch_report" in notes or receipt_payload.get("reconciled_from_dispatch_report") is True:
                issues.append(_issue("automatic_publish_receipt", "manual_reconciliation_detected", "receipt was reconciled from a dispatch report and does not prove unattended automatic receipt writing", artifact_path=publish_receipts[0]["relative_path"]))

    if dispatch_reports and not publish_receipts:
        issues.append(_issue("automatic_publish_receipt", "automatic_receipt_missing", "publish evidence exists only in dispatch reporting; automatic governed receipt is missing", artifact_path=dispatch_reports[0]["relative_path"]))

    latest_scheduler_receipt = scheduler_receipts[-1]["payload"] if scheduler_receipts else None
    failure_receipts = [
        receipt for receipt in scheduler_receipts
        if str((receipt["payload"] or {}).get("receipt_kind") or "") in {"generation_failure", "publish_failure"}
    ]
    if failure_receipts:
        latest_failure = failure_receipts[-1]
        failure_payload = (latest_failure["payload"].get("result") or {})
        issues.append(
            _issue(
                "scheduler_driver_poll_result",
                str((failure_payload.get("failure") or {}).get("code") or f"{latest_failure['payload'].get('receipt_kind')}_reported"),
                str((failure_payload.get("failure") or {}).get("detail") or "scheduler receipt recorded a terminal failure"),
                artifact_path=latest_failure["relative_path"],
                timestamp=str(latest_failure["payload"].get("recorded_at") or ""),
            )
        )

    if failure_receipts and exec_payload is not None and str(exec_payload.get("outcome") or "") == "success":
        issues.append(
            _issue(
                "scheduler_driver_poll_result",
                "conflicting_generation_outcomes",
                "scheduler driver recorded a terminal failure receipt, but later execution evidence claims success for the same slot",
                artifact_path=failure_receipts[-1]["relative_path"],
            )
        )
    elif state_payload.get("status") == "generation_failed" and exec_payload is not None and str(exec_payload.get("outcome") or "") == "success":
        issues.append(_issue("scheduler_driver_poll_result", "conflicting_generation_outcomes", "scheduler driver state says generation_failed but execution receipt says success", artifact_path=_repo_relative_path(deployment_root, state_path)))

    if publish_receipts and not automatic_successful_runs:
        issues.append(_issue("scheduler_task_runs", "manual_start_or_missing_time_trigger", "no automatic time-triggered successful scheduler run was observed in the slot window", artifact_path="Microsoft-Windows-TaskScheduler/Operational"))

    if relevant_runs and any((run.get("result_code") not in (None, 0)) for run in relevant_runs):
        bad_run = next(run for run in relevant_runs if run.get("result_code") not in (None, 0))
        issues.append(
            _issue(
                "scheduler_task_runs",
                "scheduler_nonzero_result",
                f"scheduler action completed with result code {bad_run.get('result_code')}",
                artifact_path="Microsoft-Windows-TaskScheduler/Operational",
                timestamp=(bad_run.get("last_event_time") or now).isoformat(),
            )
        )

    conflict_codes = {
        "handoff_sha_mismatch",
        "conflicting_generation_outcomes",
        "duplicate_queue_rows",
        "host_sha_mismatch",
        "source_sha_mismatch",
        "output_sha_mismatch",
        "identity_image_sha_mismatch",
    }
    structural_conflict = any(issue["code"] in conflict_codes for issue in issues)
    publish_complete = bool(publish_receipts and posted_rows)
    unattended_ready = bool(
        authorization is not None
        and generation["standing_approval"]["payload"] is not None
        and exec_payload is not None
        and identity_payload is not None
        and qa_payload is not None
        and packet_payload is not None
        and clean_payload is not None
        and publish_receipts
    )

    if structural_conflict:
        classification = "evidence_inconsistent"
    elif unattended_ready and not issues:
        classification = "autonomous_cycle_completed"
    elif issues:
        classification = "cycle_failed"
    else:
        classification = "waiting_for_more_evidence" if now >= generation_at else "not_due_yet"

    dispatch_result = dispatch_reports[0]["result"] if dispatch_reports else None
    summary = {
        "day": day,
        "schedule_slot": schedule_slot,
        "slot_id": slot_id,
        "generation_at": generation_at.isoformat(),
        "publish_at": publish_at.isoformat(),
        "due_now": now >= generation_at,
        "state_path": _repo_relative_path(deployment_root, state_path),
        "state_status": state_payload.get("status"),
        "relevant_scheduler_runs": len(relevant_runs),
        "automatic_successful_scheduler_runs": len(automatic_successful_runs),
        "classification": classification,
        "issues": issues,
        "evidence_chain": chain,
        "authorization_mode": (authorization or {}).get("payload", {}).get("authorization_mode"),
        "most_recent_scheduler_receipt": scheduler_receipts[-1]["relative_path"] if scheduler_receipts else None,
        "dispatch_report_path": dispatch_reports[0]["relative_path"] if dispatch_reports else None,
        "dispatch_publish_posted": bool(dispatch_result and ((dispatch_result.get("result") or {}).get("posted") is True)),
        "publish_receipt_path": publish_receipts[0]["relative_path"] if publish_receipts else None,
    }
    return summary


def build_snapshot(
    *,
    deployment_root: Path,
    now: datetime | None = None,
    task_name: str = CANONICAL_TASK_NAME,
    task_probe: TaskProbe = default_task_probe,
    event_probe: EventProbe = default_event_probe,
) -> dict[str, Any]:
    resolved_now = _normalize_now(now)
    task = task_probe(task_name)
    events = event_probe(task_name, 120)
    task_runs = _group_task_runs(events)
    next_slot = _next_governed_slot(resolved_now)
    target_observation = _observe_slot(
        deployment_root,
        day=next_slot["date"],
        schedule_slot=next_slot["schedule_slot"],
        now=resolved_now,
        task_runs=task_runs,
    )

    latest_day = _latest_scheduler_driver_day(deployment_root)
    latest_observation = None
    if latest_day is not None:
        for slot in reversed(schedule_mod.SLOT_ORDER):
            state_path, state_payload = _load_scheduler_state(deployment_root, latest_day, slot)
            if state_path.exists() or state_payload.get("status") != "not_started":
                latest_observation = _observe_slot(
                    deployment_root,
                    day=latest_day,
                    schedule_slot=slot,
                    now=resolved_now,
                    task_runs=task_runs,
                )
                break

    latest_completed_run = next((run for run in task_runs if run.get("completed")), None)
    snapshot = {
        "observer_mode": "snapshot",
        "observed_at": resolved_now.isoformat(),
        "deployment_root": str(deployment_root.resolve()),
        "task_name": task_name,
        "scheduler": {
            "present": bool(task.get("present")),
            "enabled": bool(task.get("enabled")),
            "state": task.get("state"),
            "last_task_result": task.get("last_task_result"),
            "last_run_time": task.get("last_run_time"),
            "next_run_time": task.get("next_run_time"),
            "actions": task.get("actions") or [],
            "latest_completed_run": {
                "instance_id": latest_completed_run.get("instance_id"),
                "automatic_time_trigger": latest_completed_run.get("automatic_time_trigger"),
                "result_code": latest_completed_run.get("result_code"),
                "action_name": latest_completed_run.get("action_name"),
                "last_event_time": latest_completed_run.get("last_event_time").isoformat() if latest_completed_run and latest_completed_run.get("last_event_time") else None,
                "event_ids": latest_completed_run.get("event_ids") if latest_completed_run else [],
            } if latest_completed_run else None,
            "recent_run_count": len(task_runs),
        },
        "next_governed_slot": next_slot,
        "slot_currently_due": bool(next_slot["due_now"]),
        "current_cycle": target_observation,
        "latest_observed_cycle": latest_observation,
        "most_recent_generation": _latest_execution_receipt(deployment_root),
        "most_recent_queue_row": _latest_queue_row(deployment_root),
        "most_recent_publish_receipt": _latest_publish_receipt(deployment_root),
        "observer_contract": {
            "read_only": True,
            "network_calls_permitted": False,
            "mutation_permitted": False,
            "provider_calls_permitted": False,
            "publish_calls_permitted": False,
            "queue_mutations_permitted": False,
        },
    }
    return snapshot


def watch_next_due_slot(
    *,
    deployment_root: Path,
    timeout_seconds: int,
    poll_seconds: int,
    now: datetime | None = None,
    task_name: str = CANONICAL_TASK_NAME,
    task_probe: TaskProbe = default_task_probe,
    event_probe: EventProbe = default_event_probe,
) -> dict[str, Any]:
    started_at = _normalize_now(now)
    deadline = started_at + timedelta(seconds=timeout_seconds)
    while True:
        snapshot = build_snapshot(
            deployment_root=deployment_root,
            now=None,
            task_name=task_name,
            task_probe=task_probe,
            event_probe=event_probe,
        )
        scheduler = snapshot["scheduler"]
        current_cycle = snapshot["current_cycle"]
        due_now = bool(snapshot["slot_currently_due"])
        if not scheduler["present"] or not scheduler["enabled"]:
            return {
                "observer_mode": "watch",
                "terminal_result": "scheduler_disabled",
                "observed_at": snapshot["observed_at"],
                "snapshot": snapshot,
            }
        classification = str(current_cycle.get("classification") or "")
        if classification == "autonomous_cycle_completed":
            return {
                "observer_mode": "watch",
                "terminal_result": "autonomous_cycle_completed",
                "observed_at": snapshot["observed_at"],
                "snapshot": snapshot,
            }
        if classification == "evidence_inconsistent":
            return {
                "observer_mode": "watch",
                "terminal_result": "evidence_inconsistent",
                "observed_at": snapshot["observed_at"],
                "snapshot": snapshot,
            }
        if due_now and classification == "cycle_failed":
            return {
                "observer_mode": "watch",
                "terminal_result": "cycle_failed",
                "observed_at": snapshot["observed_at"],
                "snapshot": snapshot,
            }
        current_time = _normalize_now(None)
        if current_time >= deadline:
            return {
                "observer_mode": "watch",
                "terminal_result": "cycle_not_due_before_timeout" if not due_now else "cycle_failed",
                "observed_at": snapshot["observed_at"],
                "snapshot": snapshot,
            }
        time.sleep(max(1, poll_seconds))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only observer for Lena autonomous photo scheduler evidence.")
    parser.add_argument("--deployment-root", required=True, help="Live deployment checkout to observe without modification.")
    parser.add_argument("--mode", choices=("snapshot", "watch"), default="snapshot")
    parser.add_argument("--task-name", default=CANONICAL_TASK_NAME)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--now", default=None, help="Optional ISO datetime override for testing.")
    args = parser.parse_args(argv)

    deployment_root = Path(args.deployment_root).expanduser().resolve()
    _require(deployment_root.is_dir(), "deployment_root_missing", f"deployment root does not exist: {deployment_root}")
    parsed_now = datetime.fromisoformat(args.now) if args.now else None

    if args.mode == "snapshot":
        result = build_snapshot(
            deployment_root=deployment_root,
            now=parsed_now,
            task_name=args.task_name,
        )
    else:
        result = watch_next_due_slot(
            deployment_root=deployment_root,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            now=parsed_now,
            task_name=args.task_name,
        )
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
