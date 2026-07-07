"""
pipeline.scheduler
==================

Small in-process scheduler for content_bot / Lena nodes.

This module is intentionally dependency-free and safe to import repeatedly.
It is not a replacement for Windows Task Scheduler or a daemon supervisor. It
is the lightweight ICM-facing layer that lets the orchestrator register jobs and
call ``run_pending()`` after a successful maintenance/backup cycle.

Features:
- idempotent job registration
- JSON config support
- interval handling with persisted wall-clock state
- structured run results
- exceptions contained so the orchestrator stays alive
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import importlib
import json
import logging
import os
import time
import traceback

LOGGER = logging.getLogger(__name__)

PIPELINE_DIR = Path(os.environ.get("CONTENT_BOT_PIPELINE_DIR", Path(__file__).resolve().parent)).resolve()
REPO_ROOT = Path(os.environ.get("CONTENT_BOT_ROOT", PIPELINE_DIR.parent)).resolve()
DEFAULT_CONFIG_PATH = PIPELINE_DIR / "config" / "scheduler_config.json"
DEFAULT_STATE_PATH = PIPELINE_DIR / "state" / "scheduler_state.json"

JobCallable = Callable[[], Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class Job:
    name: str
    func: JobCallable
    interval_seconds: int
    enabled: bool = True
    run_on_start: bool = False
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_run_monotonic: Optional[float] = None
    last_run_utc: Optional[str] = None
    next_run_monotonic: Optional[float] = None

    def due(self, now_monotonic: Optional[float] = None, now_utc: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        now_monotonic = now_monotonic if now_monotonic is not None else time.monotonic()
        now_utc = now_utc or utc_now()

        if self.last_run_utc:
            last = parse_utc(self.last_run_utc)
            if last and (now_utc - last).total_seconds() >= max(1, int(self.interval_seconds)):
                return True

        if self.last_run_monotonic is None:
            if self.run_on_start and not self.last_run_utc:
                return True
            if self.next_run_monotonic is None:
                self.next_run_monotonic = now_monotonic + max(1, int(self.interval_seconds))
            return now_monotonic >= self.next_run_monotonic

        next_due = self.next_run_monotonic
        if next_due is None:
            next_due = self.last_run_monotonic + max(1, int(self.interval_seconds))
            self.next_run_monotonic = next_due
        return now_monotonic >= next_due

    def mark_ran(self, now_monotonic: Optional[float] = None) -> None:
        now_monotonic = now_monotonic if now_monotonic is not None else time.monotonic()
        self.last_run_monotonic = now_monotonic
        self.last_run_utc = utc_now().isoformat()
        self.next_run_monotonic = now_monotonic + max(1, int(self.interval_seconds))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "run_on_start": self.run_on_start,
            "description": self.description,
            "metadata": self.metadata,
            "last_run_utc": self.last_run_utc,
            "due": self.due(),
        }


_JOBS: Dict[str, Job] = {}
_CONFIG: Dict[str, Any] = {}
_STATE_LOADED = False


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        LOGGER.warning("Could not read JSON %s: %s", path, exc)
        return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def load_config(path: Optional[os.PathLike[str] | str] = None) -> Dict[str, Any]:
    """Load scheduler configuration from JSON. Safe to call repeatedly."""
    global _CONFIG
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.is_absolute():
        cfg_path = PIPELINE_DIR / cfg_path
    default: Dict[str, Any] = {
        "enabled": True,
        "state_file": str(DEFAULT_STATE_PATH),
        "jobs": {},
        "posting": {},
        "schedule": {},
        "backup": {},
    }
    data = _read_json(cfg_path, default)
    if not isinstance(data, dict):
        data = {}
    merged = {**default, **data}
    for section in ("jobs", "posting", "schedule", "backup"):
        if not isinstance(merged.get(section), dict):
            merged[section] = {}
    _CONFIG = merged
    return _CONFIG


def get_config() -> Dict[str, Any]:
    return _CONFIG or load_config()


def _state_path() -> Path:
    raw = get_config().get("state_file") or str(DEFAULT_STATE_PATH)
    path = Path(str(raw))
    if not path.is_absolute():
        path = PIPELINE_DIR / path
    return path


def _load_state_once() -> None:
    global _STATE_LOADED
    if _STATE_LOADED:
        return
    _STATE_LOADED = True
    state = _read_json(_state_path(), {})
    jobs_state = state.get("jobs", {}) if isinstance(state, dict) else {}
    if not isinstance(jobs_state, dict):
        return
    for name, payload in jobs_state.items():
        job = _JOBS.get(name)
        if job and isinstance(payload, dict):
            job.last_run_utc = payload.get("last_run_utc")


def _save_state() -> None:
    payload = {
        "updated_utc": utc_now().isoformat(),
        "jobs": {
            name: {
                "last_run_utc": job.last_run_utc,
                "interval_seconds": job.interval_seconds,
                "enabled": job.enabled,
            }
            for name, job in sorted(_JOBS.items())
        },
    }
    _write_json_atomic(_state_path(), payload)


def register_job(
    name: str,
    func: JobCallable,
    *,
    interval_seconds: Optional[int] = None,
    enabled: Optional[bool] = None,
    run_on_start: Optional[bool] = None,
    description: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Job:
    """Register or update a job by name. Repeated registration is idempotent."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("job name must be a non-empty string")
    if not callable(func):
        raise ValueError(f"job {name!r} function must be callable")

    cfg = get_config()
    job_cfg = cfg.get("jobs", {}).get(name, {})
    if not isinstance(job_cfg, dict):
        job_cfg = {}

    raw_interval = interval_seconds if interval_seconds is not None else job_cfg.get("interval_seconds", 3600)
    try:
        interval = max(1, int(raw_interval))
    except Exception:
        interval = 3600

    previous = _JOBS.get(name)
    job = Job(
        name=name,
        func=func,
        interval_seconds=interval,
        enabled=truthy(enabled if enabled is not None else job_cfg.get("enabled", True)),
        run_on_start=truthy(run_on_start if run_on_start is not None else job_cfg.get("run_on_start", False)),
        description=description or str(job_cfg.get("description", "")),
        metadata=metadata or {},
    )
    if previous:
        job.last_run_monotonic = previous.last_run_monotonic
        job.last_run_utc = previous.last_run_utc
        job.next_run_monotonic = previous.next_run_monotonic
    _JOBS[name] = job
    return job


def clear_jobs() -> None:
    _JOBS.clear()


def get_job(name: str) -> Optional[Job]:
    return _JOBS.get(name)


def list_jobs() -> List[Dict[str, Any]]:
    _load_state_once()
    return [job.to_dict() for job in sorted(_JOBS.values(), key=lambda j: j.name)]


def import_jobs(module_name: str = "pipeline.scheduler_jobs") -> Dict[str, Any]:
    """Import a module that registers jobs. Safe to call repeatedly."""
    load_config()
    try:
        module = importlib.import_module(module_name)
        imported_name = module_name
    except ModuleNotFoundError:
        if module_name.startswith("pipeline."):
            imported_name = module_name.split(".", 1)[1]
            module = importlib.import_module(imported_name)
        else:
            raise
    if hasattr(module, "register_jobs") and callable(module.register_jobs):
        module.register_jobs()
    return {"ok": True, "module": imported_name, "jobs": list_jobs()}


def run_pending(*, force: bool = False, max_jobs: Optional[int] = None) -> Dict[str, Any]:
    """Run due jobs and return a structured result payload."""
    _load_state_once()
    if not truthy(get_config().get("enabled", True)):
        return {
            "ok": True,
            "ran": 0,
            "skipped": len(_JOBS),
            "jobs": [],
            "message": "scheduler disabled by config",
            "timestamp_utc": utc_now().isoformat(),
        }

    now_mono = time.monotonic()
    now = utc_now()
    ran = 0
    skipped = 0
    results: List[Dict[str, Any]] = []

    for name, job in sorted(list(_JOBS.items())):
        if not job.enabled:
            skipped += 1
            results.append({"job": name, "status": "skipped", "reason": "disabled"})
            continue
        if max_jobs is not None and ran >= max_jobs:
            skipped += 1
            results.append({"job": name, "status": "skipped", "reason": "max_jobs_reached"})
            continue
        if not force and not job.due(now_mono, now):
            skipped += 1
            results.append({"job": name, "status": "skipped", "reason": "not_due"})
            continue

        started = utc_now().isoformat()
        try:
            payload = job.func()
            job.mark_ran(now_mono)
            ran += 1
            results.append({
                "job": name,
                "status": "success",
                "started_utc": started,
                "finished_utc": utc_now().isoformat(),
                "result": payload,
            })
        except Exception as exc:
            job.mark_ran(now_mono)
            ran += 1
            LOGGER.exception("scheduled job failed: %s", name)
            results.append({
                "job": name,
                "status": "error",
                "started_utc": started,
                "finished_utc": utc_now().isoformat(),
                "error": str(exc),
                "traceback": traceback.format_exc(limit=12),
            })

    _save_state()
    return {
        "ok": all(item.get("status") != "error" for item in results),
        "ran": ran,
        "skipped": skipped,
        "jobs": results,
        "timestamp_utc": utc_now().isoformat(),
    }


load_config()
