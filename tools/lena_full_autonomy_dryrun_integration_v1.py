from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tools import lena_generation_qa_package_dryrun_v1 as generation_cycle
from tools import lena_strategy_analytics_dryrun_cycle_v1 as strategy_cycle


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
REPORTS = generation_cycle.DEFAULT_REPORTS_ROOT
STRATEGY_REPORT_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
GENERATION_REPORT_ROOT = generation_cycle.DEFAULT_REPORTS_ROOT

AGGREGATE_STAGES = (
    "strategy_preparation",
    "approved_candidate_resolution",
    "generation_result_intake",
    "image_qa_validation",
    "caption_package_creation",
    "analytics_intake_sync",
)
GENERATION_STAGE_ORDER = (
    "approved_candidate_resolution",
    "generation_result_intake",
    "image_qa_validation",
    "caption_package_creation",
)


class LenaFullAutonomyDryRunError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_stamp() -> str:
    return datetime.now().strftime("%H%M%S")


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaFullAutonomyDryRunError(code, detail)


def _ensure_path_within_root(
    path: Path,
    root: Path,
    *,
    code: str,
    label: str,
    must_exist: bool,
) -> Path:
    root_resolved = root.resolve(strict=False)
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(root_resolved):
        raise LenaFullAutonomyDryRunError(
            code,
            f"resolved {label} escapes declared root: {resolved} (root: {root_resolved})",
        )
    if must_exist and not resolved.exists():
        raise LenaFullAutonomyDryRunError(code, f"{label} does not exist: {resolved}")
    return resolved


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise LenaFullAutonomyDryRunError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LenaFullAutonomyDryRunError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LenaFullAutonomyDryRunError(code, f"{label} must be a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise LenaFullAutonomyDryRunError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    temp_path = path.with_name(f"{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _validate_iso_date(raw_date: str) -> str:
    try:
        return date.fromisoformat(raw_date).isoformat()
    except ValueError as exc:
        raise LenaFullAutonomyDryRunError("invalid_date", f"invalid --date value {raw_date!r}: expected YYYY-MM-DD") from exc


def _report_path(day: str, stamp: str, report_root: Path = REPORTS) -> Path:
    return report_root / day / f"lena_full_autonomy_dry_run_cycle_{day}_{stamp}.json"


def _ensure_report_path_within_root(path: Path, report_root: Path = REPORTS) -> Path:
    return _ensure_path_within_root(
        path,
        report_root,
        code="report_path_escape",
        label="aggregate receipt",
        must_exist=False,
    )


def _self_command(args: argparse.Namespace) -> str:
    cmd = [
        PY,
        str(Path(__file__).resolve()),
        "--date",
        args.date,
        "--approval-artifact",
        str(args.approval_artifact),
        "--qa-artifact",
        str(args.qa_artifact),
    ]
    if args.manifest_artifact:
        cmd.extend(["--manifest-artifact", str(args.manifest_artifact)])
    if args.recipes:
        cmd.extend(["--recipes", args.recipes])
    cmd.extend(["--queue-limit", str(args.queue_limit)])
    return subprocess.list2cmdline(cmd)


def run_step(label: str, cmd: list[str]) -> dict[str, Any]:
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
        "cmd_text": subprocess.list2cmdline(cmd),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _parse_json_stdout(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw or not raw.startswith("{"):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bind_report(path: Path, *, root: Path, code: str, label: str) -> tuple[Path, str, dict[str, Any]]:
    resolved = _ensure_path_within_root(path, root, code=code, label=label, must_exist=True)
    report = _read_json_object(resolved, code=f"{code}_invalid", label=label)
    sha256 = _sha256_file(resolved)
    return resolved, sha256, report


def _validate_step_sequence(
    report: dict[str, Any],
    expected: tuple[str, ...],
    *,
    code: str,
    label: str,
) -> None:
    items = report.get(label)
    _require(isinstance(items, list), code, f"{label} must be a list")
    actual = [str(item.get("stage") or item.get("label") or "") for item in items if isinstance(item, dict)]
    if report.get("ok", False):
        _require(actual == list(expected), code, f"{label} stage order mismatch: {actual}")
    else:
        _require(
            actual == list(expected[: len(actual)]),
            code,
            f"{label} stage order mismatch: {actual}",
        )


def _copy_generation_lineage(report: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_verified_lineage": report.get("verified_lineage", {}),
        f"{prefix}_asserted_lineage": report.get("asserted_lineage", {}),
        f"{prefix}_unverified_bindings": report.get("unverified_bindings", []),
        f"{prefix}_prompt_binding_verified": report.get("prompt_binding_verified", False),
    }


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    args.date = _validate_iso_date(args.date)
    started_at = now_iso()
    stamp = now_stamp()
    output_path = _report_path(args.date, stamp, args.report_root)
    _ensure_report_path_within_root(output_path, args.report_root)
    if output_path.exists():
        raise LenaFullAutonomyDryRunError("report_already_exists", f"aggregate receipt already exists: {output_path}")

    stages: list[dict[str, Any]] = []
    child_receipts: dict[str, dict[str, Any]] = {}
    strategy_report_path: Path | None = None
    strategy_report_sha256 = ""
    generation_report_path: Path | None = None
    generation_report_sha256 = ""
    strategy_step = {}
    generation_report: dict[str, Any] = {}
    analytics_step: dict[str, Any] = {}

    strategy_cmd = strategy_cycle.build_strategy_command(args.date, args.queue_limit, args.recipes)
    strategy_step = run_step("strategy_preparation", strategy_cmd)
    strategy_report_payload = _parse_json_stdout(strategy_step.get("stdout", ""))
    if strategy_report_payload.get("report_path"):
        strategy_report_path, strategy_report_sha256, strategy_report = _bind_report(
            Path(str(strategy_report_payload["report_path"])),
            root=STRATEGY_REPORT_ROOT,
            code="strategy_report_path_escape",
            label="strategy report",
        )
        _require(strategy_report.get("steps", []), "strategy_report_missing_steps", "strategy report is missing steps")
        _validate_step_sequence(strategy_report, ("strategy_autonomy_prep",), code="strategy_step_order_mismatch", label="steps")
        child_receipts["strategy"] = {
            "path": str(strategy_report_path),
            "sha256": strategy_report_sha256,
            "report_type": strategy_report.get("report_type", "lena_strategy_autonomy_run"),
            "ok": bool(strategy_report.get("ok", False)),
        }
    else:
        strategy_report = {}

    stages.append(
        {
            "stage": "strategy_preparation",
            "status": "pass" if strategy_step.get("ok") else "fail",
            "ok": strategy_step.get("ok", False),
            "command": strategy_step.get("cmd_text", ""),
            "report_path": str(strategy_report_path) if strategy_report_path else "",
            "report_sha256": strategy_report_sha256,
            "strategy_summary": strategy_report.get("summary", {}),
        }
    )
    if not strategy_step.get("ok", False):
        return _finalize_report(
            ok=False,
            args=args,
            started_at=started_at,
            output_path=output_path,
            stages=stages,
            strategy_step=strategy_step,
            generation_report=generation_report,
            strategy_report_path=strategy_report_path,
            strategy_report_sha256=strategy_report_sha256,
            generation_report_path=generation_report_path,
            generation_report_sha256=generation_report_sha256,
            analytics_step=analytics_step,
            child_receipts=child_receipts,
            failed_stage="strategy_preparation",
        )

    gen_args = argparse.Namespace(
        date=args.date,
        approval_artifact=args.approval_artifact,
        qa_artifact=args.qa_artifact,
        manifest_artifact=args.manifest_artifact,
        report_root=args.generation_report_root,
        manifest_root=args.manifest_root,
        image_root=args.image_root,
        qa_root=args.qa_root,
        packet_root=args.packet_root,
    )
    generation_report = generation_cycle.run_cycle(gen_args)
    generation_report_path = _ensure_path_within_root(
        Path(str(generation_report["report_path"])),
        GENERATION_REPORT_ROOT,
        code="generation_report_path_escape",
        label="generation report",
        must_exist=False,
    )
    _write_json_atomic(generation_report_path, generation_report)
    generation_report_path, generation_report_sha256, generation_report = _bind_report(
        generation_report_path,
        root=GENERATION_REPORT_ROOT,
        code="generation_report_path_escape",
        label="generation report",
    )
    _validate_step_sequence(
        generation_report,
        GENERATION_STAGE_ORDER,
        code="generation_stage_order_mismatch",
        label="stages",
    )
    _require(bool(generation_report.get("publishing_authorized") is False), "publishing_authorized_must_be_false", "generation report must keep publishing_authorized false")
    _require(int(generation_report.get("provider_calls_performed", 0)) == 0, "provider_calls_performed_not_zero", "generation report must not record provider calls")
    _require(int(generation_report.get("publish_calls_performed", 0)) == 0, "publish_calls_performed_not_zero", "generation report must not record publish calls")
    _require(int(generation_report.get("retries_performed", 0)) == 0, "retries_performed_not_zero", "generation report must not record retries")
    child_receipts["generation"] = {
        "path": str(generation_report_path),
        "sha256": generation_report_sha256,
        "report_type": generation_report.get("report_type", "lena_generation_qa_package_dry_run_cycle"),
        "ok": bool(generation_report.get("ok", False)),
    }
    stages.extend(
        {
            "stage": item.get("stage", ""),
            "status": item.get("status", "pass"),
            "ok": item.get("status", "pass") == "pass",
            "mode": item.get("mode", ""),
            "source_receipt_path": str(generation_report_path),
            "source_receipt_sha256": generation_report_sha256,
        }
        for item in generation_report.get("stages", [])
    )
    if not generation_report.get("ok", False):
        return _finalize_report(
            ok=False,
            args=args,
            started_at=started_at,
            output_path=output_path,
            stages=stages,
            strategy_step=strategy_step,
            generation_report=generation_report,
            strategy_report_path=strategy_report_path,
            strategy_report_sha256=strategy_report_sha256,
            generation_report_path=generation_report_path,
            generation_report_sha256=generation_report_sha256,
            analytics_step=analytics_step,
            child_receipts=child_receipts,
            failed_stage=str(generation_report.get("failed_stage") or "generation_qa_package"),
        )

    analytics_cmd = strategy_cycle.build_analytics_sync_command()
    analytics_step = run_step("analytics_intake_sync", analytics_cmd)
    stages.append(
        {
            "stage": "analytics_intake_sync",
            "status": "pass" if analytics_step.get("ok") else "fail",
            "ok": analytics_step.get("ok", False),
            "command": analytics_step.get("cmd_text", ""),
            "stdout": analytics_step.get("stdout", ""),
            "stderr": analytics_step.get("stderr", ""),
        }
    )
    if not analytics_step.get("ok", False):
        return _finalize_report(
            ok=False,
            args=args,
            started_at=started_at,
            output_path=output_path,
            stages=stages,
            strategy_step=strategy_step,
            generation_report=generation_report,
            strategy_report_path=strategy_report_path,
            strategy_report_sha256=strategy_report_sha256,
            generation_report_path=generation_report_path,
            generation_report_sha256=generation_report_sha256,
            analytics_step=analytics_step,
            child_receipts=child_receipts,
            failed_stage="analytics_intake_sync",
        )

    _verify_child_receipt_bindings(
        child_receipts=child_receipts,
        strategy_report_path=strategy_report_path,
        strategy_report_sha256=strategy_report_sha256,
        generation_report_path=generation_report_path,
        generation_report_sha256=generation_report_sha256,
    )

    return _finalize_report(
        ok=True,
        args=args,
        started_at=started_at,
        output_path=output_path,
        stages=stages,
        strategy_step=strategy_step,
        generation_report=generation_report,
        strategy_report_path=strategy_report_path,
        strategy_report_sha256=strategy_report_sha256,
        generation_report_path=generation_report_path,
        generation_report_sha256=generation_report_sha256,
        analytics_step=analytics_step,
        child_receipts=child_receipts,
    )


def _verify_child_receipt_bindings(
    *,
    child_receipts: dict[str, dict[str, Any]],
    strategy_report_path: Path | None,
    strategy_report_sha256: str,
    generation_report_path: Path | None,
    generation_report_sha256: str,
) -> None:
    if strategy_report_path is not None:
        _require(
            _sha256_file(strategy_report_path) == strategy_report_sha256,
            "strategy_report_sha_mismatch",
            "strategy report SHA-256 no longer matches its bound bytes",
        )
    if generation_report_path is not None:
        _require(
            _sha256_file(generation_report_path) == generation_report_sha256,
            "generation_report_sha_mismatch",
            "generation report SHA-256 no longer matches its bound bytes",
        )
    _require(bool(child_receipts), "child_receipts_missing", "aggregate receipt must bind child receipts")


def _finalize_report(
    *,
    ok: bool,
    args: argparse.Namespace,
    started_at: str,
    output_path: Path,
    stages: list[dict[str, Any]],
    strategy_step: dict[str, Any],
    generation_report: dict[str, Any],
    strategy_report_path: Path | None,
    strategy_report_sha256: str,
    generation_report_path: Path | None,
    generation_report_sha256: str,
    analytics_step: dict[str, Any],
    child_receipts: dict[str, dict[str, Any]],
    failed_stage: str = "",
) -> dict[str, Any]:
    strategy_summary = {}
    if strategy_report_path and strategy_report_path.exists():
        try:
            strategy_summary = _read_json_object(
                strategy_report_path,
                code="strategy_report_read_failed",
                label="strategy report",
            ).get("summary", {})
        except LenaFullAutonomyDryRunError:
            strategy_summary = {}

    report: dict[str, Any] = {
        "ok": ok,
        "version": "v1",
        "report_type": "lena_full_autonomy_dry_run_integration",
        "date": args.date,
        "started_at": started_at,
        "finished_at": now_iso(),
        "dry_run_command": _self_command(args),
        "report_path": str(output_path),
        "publishing_authorized": False,
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "safeguards": {
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "publishing_authorized": False,
            "retries_performed": 0,
            "retry_cap": 0,
            "hard_spend_cap_usd": 0,
            "duplicate_rejection": "report_path_must_not_exist",
            "kill_switch": "no_live_command_paths",
            "fail_closed_stage_handling": True,
            "receipt_creation": "aggregate_receipt_json",
            "recurring_scheduler": False,
            "meta_refresh_performed": False,
        },
        "child_receipts": child_receipts,
        "verified_lineage": {
            "strategy_report_path": str(strategy_report_path) if strategy_report_path else "",
            "strategy_report_sha256": strategy_report_sha256,
            "generation_report_path": str(generation_report_path) if generation_report_path else "",
            "generation_report_sha256": generation_report_sha256,
        },
        "asserted_lineage": {},
        "unverified_bindings": [],
        "strategy_summary": strategy_summary,
        "generation_summary": generation_report.get("verified_lineage", {}),
        "analytics_summary": _parse_json_stdout(analytics_step.get("stdout", "")),
        "stages": stages,
        "stage_coverage": stages,
        "strategy_step": strategy_step,
        "generation_report_path": str(generation_report_path) if generation_report_path else "",
        "generation_report_sha256": generation_report_sha256,
        "analytics_step": analytics_step,
        "strategy_report_path": str(strategy_report_path) if strategy_report_path else "",
    }
    report["verified_lineage"].update(_copy_generation_lineage(generation_report, "generation"))
    if generation_report:
        report["asserted_lineage"] = generation_report.get("asserted_lineage", {})
        report["unverified_bindings"] = generation_report.get("unverified_bindings", [])
        report["prompt_binding_verified"] = generation_report.get("prompt_binding_verified", False)
        report["approval_artifact"] = generation_report.get("approval_artifact", "")
        report["approval_sha256"] = generation_report.get("approval_sha256", "")
        report["candidate_path"] = generation_report.get("candidate_path", "")
        report["candidate_sha256"] = generation_report.get("candidate_sha256", "")
        report["candidate_sha256_expected"] = generation_report.get("candidate_sha256_expected", "")
        report["candidate_id"] = generation_report.get("candidate_id", "")
        report["slot_id"] = generation_report.get("slot_id", "")
        report["prompt_sha256"] = generation_report.get("prompt_sha256", "")
        report["manifest_path"] = generation_report.get("manifest_path", "")
        report["manifest_sha256"] = generation_report.get("manifest_sha256", "")
        report["image_path"] = generation_report.get("image_path", "")
        report["image_sha256"] = generation_report.get("image_sha256", "")
        report["qa_artifact"] = generation_report.get("qa_artifact", "")
        report["qa_artifact_sha256"] = generation_report.get("qa_artifact_sha256", "")
        report["packet_path"] = generation_report.get("packet_path", "")
        report["packet_sha256"] = generation_report.get("packet_sha256", "")

    if not ok:
        report["failed_stage"] = failed_stage
        if generation_report and not generation_report.get("ok", True):
            report["generation_failed_stage"] = generation_report.get("failed_stage", "")
            report["generation_error"] = generation_report.get("error", {})
        if strategy_step and not strategy_step.get("ok", True):
            report["strategy_error"] = {
                "returncode": strategy_step.get("returncode", 1),
                "stdout": strategy_step.get("stdout", ""),
                "stderr": strategy_step.get("stderr", ""),
            }

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Lena full autonomy dry-run integration wrapper.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--approval-artifact", type=Path, required=True)
    parser.add_argument("--qa-artifact", type=Path, required=True)
    parser.add_argument("--manifest-artifact", type=Path)
    parser.add_argument("--report-root", type=Path, default=REPORTS)
    parser.add_argument("--generation-report-root", type=Path, default=GENERATION_REPORT_ROOT)
    parser.add_argument("--manifest-root", type=Path, default=generation_cycle.DEFAULT_MANIFEST_ROOT)
    parser.add_argument("--image-root", type=Path, default=generation_cycle.DEFAULT_IMAGE_ROOT)
    parser.add_argument("--qa-root", type=Path, default=generation_cycle.DEFAULT_QA_ROOT)
    parser.add_argument("--packet-root", type=Path, default=generation_cycle.DEFAULT_PACKET_ROOT)
    parser.add_argument("--recipes", default="")
    parser.add_argument("--queue-limit", type=int, default=6)
    args = parser.parse_args()

    report = run_cycle(args)
    report_path = Path(report["report_path"])
    _ensure_report_path_within_root(report_path, args.report_root)
    _write_json_atomic(report_path, report)
    print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "failed_stage": report.get("failed_stage", "")}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
