from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
AUTH_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "bounded_live_cycles"
REPORT_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles"

AUTHORISED_STAGES = (
    "authorization_validation",
    "approved_candidate_resolution",
    "provider_generation_evidence",
    "image_qa",
    "caption_package_creation",
    "publish_receipt",
    "analytics_handoff",
)


class LenaBoundedLiveCycleError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaBoundedLiveCycleError(code, detail)


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
        raise LenaBoundedLiveCycleError(code, f"resolved {label} escapes declared root: {resolved} (root: {root_resolved})")
    if must_exist and not resolved.exists():
        raise LenaBoundedLiveCycleError(code, f"{label} does not exist: {resolved}")
    return resolved


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise LenaBoundedLiveCycleError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LenaBoundedLiveCycleError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LenaBoundedLiveCycleError(code, f"{label} must be a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise LenaBoundedLiveCycleError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _validate_iso_datetime(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LenaBoundedLiveCycleError("authorization_expiry_invalid", f"expires_at_utc must be ISO-8601: {raw!r}") from exc
    if dt.tzinfo is None:
        raise LenaBoundedLiveCycleError("authorization_expiry_invalid", "expires_at_utc must include timezone information")
    return dt.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _report_path(day: str, stamp: str, report_root: Path = REPORT_ROOT) -> Path:
    return report_root / day / f"lena_bounded_live_cycle_{day}_{stamp}.json"


def _subreport_path(day: str, slot_id: str, suffix: str, report_root: Path = REPORT_ROOT) -> Path:
    return report_root / day / slot_id / f"lena_bounded_live_cycle_{suffix}_{day}.json"


def _self_command(day: str, auth_artifact: Path, simulate: bool) -> str:
    cmd = [
        PY,
        str(Path(__file__).resolve()),
        "--date",
        day,
        "--authorization-artifact",
        str(auth_artifact),
    ]
    if simulate:
        cmd.append("--simulate")
    return subprocess.list2cmdline(cmd)


def _authorization_artifact_path(date_str: str, slot_id: str) -> Path:
    return AUTH_ROOT / date_str / f"lena_bounded_live_cycle_authorization_{date_str}_{slot_id}.json"


def _validate_authorization_artifact(auth_path: Path) -> dict[str, Any]:
    auth_path = _ensure_path_within_root(
        auth_path,
        AUTH_ROOT,
        code="authorization_path_escape",
        label="authorization artifact",
        must_exist=True,
    )
    auth = _read_json_object(auth_path, code="authorization_missing_or_invalid", label="authorization artifact")
    _require(auth.get("report_type") == "lena_bounded_live_cycle_authorization", "authorization_report_type_mismatch", "authorization artifact report_type must be lena_bounded_live_cycle_authorization")
    _require(auth.get("schema_version") == "v1", "authorization_schema_mismatch", "authorization artifact schema_version must be v1")
    _require(auth.get("single_use") is True, "authorization_single_use_invalid", "authorization must be single-use")
    _require(auth.get("consumed") is False, "authorization_already_consumed", "authorization has already been consumed")
    _require(auth.get("kill_switch") is True, "authorization_kill_switch_disabled", "kill switch must be enabled")
    _require(int(auth.get("provider_call_limit", 0)) == 1, "provider_call_limit_invalid", "provider call limit must be one")
    _require(int(auth.get("publish_action_limit", 0)) == 1, "publish_action_limit_invalid", "publish action limit must be one")
    _require(int(auth.get("retry_cap", -1)) == 0, "retry_cap_invalid", "retry cap must be zero")
    _require(float(auth.get("hard_spend_cap_usd", -1.0)) == 0.0, "hard_spend_cap_invalid", "hard spend cap must be zero")
    _require(auth.get("publish_authorized") is False, "publish_authorized_invalid", "publishing must be denied by default")
    _require(str(auth.get("platform") or "") == "Instagram Feed", "platform_mismatch", "authorization platform must be Instagram Feed")

    expiry = _validate_iso_datetime(str(auth.get("expires_at_utc") or ""))
    _require(expiry > _now_utc(), "authorization_expired", "authorization has expired")
    required_text_fields = ("date", "slot_id", "candidate_id", "asset_path", "platform", "caption")
    missing = [key for key in required_text_fields if not str(auth.get(key) or "").strip()]
    _require(not missing, "authorization_missing_fields", f"authorization missing required fields: {', '.join(missing)}")
    _require(auth.get("one_slot") is True, "authorization_one_slot_invalid", "authorization must be scoped to one slot")
    _require(auth.get("one_candidate") is True, "authorization_one_candidate_invalid", "authorization must be scoped to one candidate")
    _require(auth.get("one_asset") is True, "authorization_one_asset_invalid", "authorization must be scoped to one asset")
    _require(auth.get("one_platform") is True, "authorization_one_platform_invalid", "authorization must be scoped to one platform")
    _require(int(auth.get("provider_calls_performed", 0)) == 0, "authorization_provider_calls_not_zero", "authorization must start with zero provider calls")
    _require(int(auth.get("publish_calls_performed", 0)) == 0, "authorization_publish_calls_not_zero", "authorization must start with zero publish calls")
    _require(int(auth.get("retries_performed", 0)) == 0, "authorization_retries_not_zero", "authorization must start with zero retries")

    return {
        "path": auth_path,
        "sha256": _sha256_file(auth_path),
        "artifact": auth,
        "expires_at_utc": expiry.isoformat(),
    }


def _validate_bound_artifact(path_value: str, sha_value: str, *, root: Path, code: str, label: str) -> dict[str, Any]:
    resolved = _ensure_path_within_root(Path(path_value), root, code=code, label=label, must_exist=True)
    observed_sha = _sha256_file(resolved)
    _require(observed_sha == sha_value, f"{code}_sha_mismatch", f"{label} SHA-256 does not match the bound value")
    return {
        "path": resolved,
        "sha256": observed_sha,
        "artifact": _read_json_object(resolved, code=f"{code}_invalid", label=label),
    }


def _ensure_report_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise LenaBoundedLiveCycleError("report_already_exists", f"aggregate receipt already exists: {path}")


def _stage_summary(stage: str, ok: bool, **data: Any) -> dict[str, Any]:
    return {"stage": stage, "ok": ok, **data}


def _build_package(auth: dict[str, Any], provider: dict[str, Any], qa: dict[str, Any], package_path: Path) -> tuple[Path, dict[str, Any]]:
    payload = {
        "report_type": "lena_bounded_live_cycle_package",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slot_id": auth["artifact"]["slot_id"],
        "candidate_id": auth["artifact"]["candidate_id"],
        "platform": auth["artifact"]["platform"],
        "caption": auth["artifact"]["caption"],
        "asset_path": auth["artifact"]["asset_path"],
        "asset_sha256": auth["artifact"]["asset_sha256"],
        "provider_generation_receipt_path": str(provider["path"]),
        "provider_generation_receipt_sha256": provider["sha256"],
        "manifest_path": str(provider["artifact"]["manifest_path"]),
        "manifest_sha256": provider["artifact"]["manifest_sha256"],
        "generated_image_path": str(provider["artifact"]["generated_image_path"]),
        "generated_image_sha256": provider["artifact"]["generated_image_sha256"],
        "qa_artifact_path": str(qa["path"]),
        "qa_artifact_sha256": qa["sha256"],
        "publishing_authorized": False,
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
    }
    _write_json_atomic(package_path, payload)
    payload["package_artifact_path"] = str(package_path)
    payload["package_artifact_sha256"] = _sha256_file(package_path)
    return package_path, payload


def _build_publish_receipt(auth: dict[str, Any], package: dict[str, Any], publish_path: Path) -> tuple[Path, dict[str, Any]]:
    payload = {
        "report_type": "lena_bounded_live_cycle_publish_receipt",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slot_id": auth["artifact"]["slot_id"],
        "candidate_id": auth["artifact"]["candidate_id"],
        "platform": auth["artifact"]["platform"],
        "caption": package["caption"],
        "asset_path": package["asset_path"],
        "asset_sha256": package["asset_sha256"],
        "package_artifact_path": package["package_artifact_path"],
        "package_artifact_sha256": package["package_artifact_sha256"],
        "publish_calls_performed": 0,
        "publishing_authorized": False,
        "published": False,
        "simulation_only": True,
    }
    _write_json_atomic(publish_path, payload)
    payload["publish_receipt_artifact_path"] = str(publish_path)
    payload["publish_receipt_artifact_sha256"] = _sha256_file(publish_path)
    return publish_path, payload


def _build_analytics_handoff(auth: dict[str, Any], package: dict[str, Any], publish: dict[str, Any], analytics_path: Path) -> tuple[Path, dict[str, Any]]:
    payload = {
        "report_type": "lena_bounded_live_cycle_analytics_handoff",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slot_id": auth["artifact"]["slot_id"],
        "candidate_id": auth["artifact"]["candidate_id"],
        "platform": auth["artifact"]["platform"],
        "publish_receipt_artifact_path": str(publish["path"]),
        "publish_receipt_artifact_sha256": publish["sha256"],
        "package_artifact_path": package["package_artifact_path"],
        "package_artifact_sha256": package["package_artifact_sha256"],
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "analytics_mutation_performed": False,
        "simulation_only": True,
    }
    _write_json_atomic(analytics_path, payload)
    payload["analytics_handoff_artifact_path"] = str(analytics_path)
    payload["analytics_handoff_artifact_sha256"] = _sha256_file(analytics_path)
    return analytics_path, payload


def run_cycle(auth_artifact: Path, *, simulate: bool = True, report_root: Path = REPORT_ROOT) -> dict[str, Any]:
    auth = _validate_authorization_artifact(auth_artifact)
    auth_data = auth["artifact"]
    day = str(auth_data["date"])

    started_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = datetime.now().strftime("%H%M%S")
    report_path = _report_path(day, stamp, report_root)
    _ensure_path_within_root(report_path, report_root, code="report_path_escape", label="aggregate receipt", must_exist=False)
    _ensure_report_dir(report_path)

    stages: list[dict[str, Any]] = []
    stages.append(_stage_summary("authorization_validation", True, authorization_artifact_path=str(auth["path"]), authorization_artifact_sha256=auth["sha256"]))

    candidate = _validate_bound_artifact(
        str(auth_data["candidate_artifact_path"]),
        str(auth_data["candidate_artifact_sha256"]),
        root=ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
        code="candidate_binding_invalid",
        label="candidate artifact",
    )
    candidate_artifact = candidate["artifact"]
    resolved_candidate = candidate_artifact.get("candidate") if isinstance(candidate_artifact.get("candidate"), dict) else candidate_artifact
    candidate_id = str(resolved_candidate.get("candidate_id") or "")
    slot_id = str(resolved_candidate.get("slot_id") or "")
    _require(candidate_id == str(auth_data["candidate_id"]), "candidate_id_mismatch", "candidate_id does not match authorization")
    _require(slot_id == str(auth_data["slot_id"]), "slot_id_mismatch", "slot_id does not match authorization")
    stages.append(_stage_summary("approved_candidate_resolution", True, candidate_artifact_path=str(candidate["path"]), candidate_artifact_sha256=candidate["sha256"]))
    provider = _validate_bound_artifact(
        str(auth_data["provider_generation_receipt_path"]),
        str(auth_data["provider_generation_receipt_sha256"]),
        root=ROOT / "pipeline" / "approvals" / "lena" / "generation",
        code="provider_receipt_binding_invalid",
        label="provider generation receipt",
    )
    manifest = _validate_bound_artifact(
        str(auth_data["manifest_path"]),
        str(auth_data["manifest_sha256"]),
        root=ROOT / "pipeline" / "higgsfield_debug",
        code="manifest_binding_invalid",
        label="generation manifest",
    )
    image = _ensure_path_within_root(Path(str(auth_data["asset_path"])), ROOT / "pipeline" / "higgsfield_library" / "lena", code="asset_path_invalid", label="generated asset", must_exist=True)
    image_sha = _sha256_file(image)
    _require(image_sha == str(auth_data["asset_sha256"]), "asset_sha_mismatch", "generated asset SHA-256 does not match authorization")
    _require(str(manifest["artifact"].get("saved_image_path") or "") == str(image), "manifest_image_mismatch", "manifest saved image does not match authorization asset")
    stages.append(_stage_summary(
        "provider_generation_evidence",
        True,
        provider_generation_receipt_path=str(provider["path"]),
        provider_generation_receipt_sha256=provider["sha256"],
        manifest_path=str(manifest["path"]),
        manifest_sha256=manifest["sha256"],
        generated_image_path=str(image),
        generated_image_sha256=image_sha,
        provider_calls_performed=0 if simulate else 1,
    ))
    qa = _validate_bound_artifact(
        str(auth_data["qa_artifact_path"]),
        str(auth_data["qa_artifact_sha256"]),
        root=ROOT / "pipeline" / "asset_review" / "lena" / "presence_output_qa",
        code="qa_binding_invalid",
        label="QA artifact",
    )
    qa_artifact = qa["artifact"]
    qa_status = str(qa_artifact.get("disposition") or qa_artifact.get("overall") or qa_artifact.get("status") or "").lower()
    _require(qa_status not in {"hard_stop", "fail", "rejected"}, "qa_failure", "QA artifact indicates failure")
    stages.append(_stage_summary("image_qa", True, qa_artifact_path=str(qa["path"]), qa_artifact_sha256=qa["sha256"]))
    package_path = _subreport_path(day, str(auth_data["slot_id"]), "package", report_root)
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path, package = _build_package(auth, provider, qa, package_path)
    package_sha = _sha256_file(package_path)
    stages.append(_stage_summary("caption_package_creation", True, package_artifact_path=str(package_path), package_artifact_sha256=package_sha))
    publish_path = _subreport_path(day, str(auth_data["slot_id"]), "publish_receipt", report_root)
    publish_path, publish = _build_publish_receipt(auth, package, publish_path)
    publish_sha = _sha256_file(publish_path)
    stages.append(_stage_summary("publish_receipt", True, publish_receipt_artifact_path=str(publish_path), publish_receipt_artifact_sha256=publish_sha))
    analytics_path = _subreport_path(day, str(auth_data["slot_id"]), "analytics_handoff", report_root)
    analytics_path, analytics = _build_analytics_handoff(auth, package, {"path": publish_path, "sha256": publish_sha, "artifact": publish}, analytics_path)
    analytics_sha = _sha256_file(analytics_path)
    stages.append(_stage_summary("analytics_handoff", True, analytics_handoff_artifact_path=str(analytics_path), analytics_handoff_artifact_sha256=analytics_sha))
    finished_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report: dict[str, Any] = {
        "ok": True,
        "version": "v1",
        "report_type": "lena_bounded_live_cycle",
        "simulation_mode": simulate,
        "date": day,
        "started_at": started_at,
        "finished_at": finished_at,
        "authorization_artifact_path": str(auth["path"]),
        "authorization_artifact_sha256": auth["sha256"],
        "authorization_consumed": True,
        "authorization_consumed_at_utc": finished_at,
        "authorization_state_before": {
            "single_use": True,
            "consumed": False,
        },
        "authorization_state_after": {
            "single_use": True,
            "consumed": True,
            "consumed_at_utc": finished_at,
        },
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "safeguards": {
            "single_use": True,
            "one_slot": True,
            "one_candidate": True,
            "one_asset": True,
            "one_platform": True,
            "provider_call_limit": 1,
            "publish_action_limit": 1,
            "retry_cap": 0,
            "hard_spend_cap_usd": 0,
            "kill_switch": True,
            "duplicate_rejection": "report_path_must_not_exist",
            "no_scheduler": True,
            "no_second_provider_call": True,
            "no_second_publish_call": True,
            "analytics_triggered_rerun_blocked": True,
        },
        "authorized_scope": {
            "slot_id": auth_data["slot_id"],
            "candidate_id": auth_data["candidate_id"],
            "asset_path": auth_data["asset_path"],
            "platform": auth_data["platform"],
        },
        "captions": {
            "caption": auth_data["caption"],
        },
        "child_artifacts": {
            "candidate": {"path": str(candidate["path"]), "sha256": candidate["sha256"]},
            "provider_generation_receipt": {"path": str(provider["path"]), "sha256": provider["sha256"]},
            "manifest": {"path": str(manifest["path"]), "sha256": manifest["sha256"]},
            "generated_asset": {"path": str(image), "sha256": image_sha},
            "qa_artifact": {"path": str(qa["path"]), "sha256": qa["sha256"]},
            "package_artifact": {"path": str(package_path), "sha256": package_sha},
            "publish_receipt_artifact": {"path": str(publish_path), "sha256": publish_sha},
            "analytics_handoff_artifact": {"path": str(analytics_path), "sha256": analytics_sha},
        },
        "stages": stages,
        "stage_coverage": stages,
        "audited_live_paths": {
            "provider_generation": "pipeline/higgsfield_lena_api_executor.py + tools/strategy/lena_execute_approved_live_generation_v1.py",
            "image_qa": "tools/lena_photo_qa_disposition_v1.py",
            "caption_package_creation": "wrapper-built package artifact",
            "publishing": "tools/publishers/lena_publish_instagram_feed_v2_8.py or tools/publishers/lena_publish_facebook_page_v2_8.py",
            "receipt": "provider generation receipt plus aggregate cycle receipt",
            "analytics": "wrapper-built read-only analytics handoff artifact",
        },
        "simulation_command": _self_command(day, auth["path"], True),
        "proposed_live_command": _self_command(day, auth["path"], False),
    }
    report["finished_stage"] = "analytics_handoff"
    _write_json_atomic(report_path, report)
    report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Lena bounded live cycle scaffold from one operator command.")
    parser.add_argument("--authorization-artifact", type=Path, required=True)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    args = parser.parse_args()

    if args.live and args.simulate:
        parser.error("--simulate and --live are mutually exclusive")
    if not args.live and not args.simulate:
        args.simulate = True

    try:
        report = run_cycle(args.authorization_artifact, simulate=not args.live, report_root=args.report_root)
    except LenaBoundedLiveCycleError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1

    print(json.dumps({"ok": True, "report": report, "report_path": report["report_path"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
