from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.identity import lena_higgsfield_identity as identity
from pipeline.identity import lena_higgsfield_identity_evidence as local_identity_evidence
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools import lena_higgsfield_retry_generation_approval_v1 as retry_approval
from tools import lena_autopublish_approved_queue_v2_8 as autonomous_publisher
from tools import lena_photo_qa_disposition_v1 as photo_qa
from tools import lena_prepare_privacy_clean_photo_v1 as clean_photo
from tools import lena_standing_autonomy_policy_v1 as standing_autonomy
from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff
import pipeline.higgsfield_lena_api_executor as executor

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
AUTH_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "bounded_live_cycles"
REPORT_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles"
POLICY_ROOT = ROOT / "pipeline" / "config"
DEFAULT_POLICY_PATH = POLICY_ROOT / "lena_standing_autonomy_policy_v1.json"

AUTHORISED_STAGES = (
    "authorization_validation",
    "approved_candidate_resolution",
    "provider_generation_evidence",
    "image_qa",
    "caption_package_creation",
    "publish_receipt",
    "analytics_handoff",
)

LIVE_STAGES = (
    "authorization_validation",
    "authorization_consumption",
    "approved_candidate_resolution",
    "provider_generation",
    "image_qa",
    "caption_package_creation",
    "publish_action",
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


def _json_safe_report_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_report_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_report_value(nested) for nested in value]
    return value


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


def _validate_authorization_artifact(auth_path: Path, *, simulate: bool) -> dict[str, Any]:
    auth_path = _ensure_path_within_root(
        auth_path,
        AUTH_ROOT,
        code="authorization_path_escape",
        label="authorization artifact",
        must_exist=True,
    )
    auth_json = _read_json_object(auth_path, code="authorization_missing_or_invalid", label="authorization artifact")
    policy_path = Path(str(auth_json.get("policy_artifact_path") or DEFAULT_POLICY_PATH))
    try:
        policy_result = standing_autonomy.validate_policy_artifact(policy_path)
    except (standing_autonomy.StandingAutonomyPolicyError, executor.HandoffArtifactError) as exc:
        raise LenaBoundedLiveCycleError(exc.code, exc.detail) from exc
    handoff_raw = str(auth_json.get("generation_handoff_artifact_path") or "").strip()
    _require(handoff_raw, "handoff_artifact_path_missing", "generation_handoff_artifact_path is required")
    handoff_path = _ensure_path_within_root(
        Path(handoff_raw),
        ROOT,
        code="handoff_path_escape",
        label="generation handoff artifact",
        must_exist=True,
    )
    if handoff_report := standing_autonomy._read_json_object(
        handoff_path,
        code="handoff_missing_or_invalid",
        label="generation handoff artifact",
    ):
        if handoff_report.get("platform") is not None:
            _require(
                str(auth_json.get("platform") or "") == str(handoff_report.get("platform") or ""),
                "platform_invalid",
                "authorization platform must match handoff",
            )
    try:
        auth_result = standing_autonomy.validate_cycle_authorization_artifact(
            auth_path,
            policy_result=policy_result,
            handoff_report=handoff_report,
        )
    except standing_autonomy.StandingAutonomyPolicyError as exc:
        raise LenaBoundedLiveCycleError(exc.code, exc.detail) from exc
    auth = auth_result["artifact"]
    _require(auth.get("one_slot") is True, "authorization_one_slot_invalid", "authorization one_slot must be true")
    _require(auth.get("one_candidate") is True, "authorization_one_candidate_invalid", "authorization one_candidate must be true")
    _require(auth.get("one_asset") is True, "authorization_one_asset_invalid", "authorization one_asset must be true")
    _require(auth.get("one_platform") is True, "authorization_one_platform_invalid", "authorization one_platform must be true")
    _require(auth.get("consumed") is False, "authorization_already_consumed", "authorization has already been consumed")
    _require(auth.get("single_use") is True, "authorization_single_use_invalid", "authorization must be single-use")
    _require(auth.get("authorization_mode") == "standing_autonomy_policy", "authorization_mode_invalid", "authorization must use standing autonomy policy mode")
    _require(auth.get("authorization_issuer") == "lena_autonomy_controller", "authorization_issuer_invalid", "authorization issuer must be Lena autonomy controller")
    _require(auth.get("expected_output_directory"), "expected_output_directory_missing", "expected_output_directory is required")
    _require(auth.get("expected_output_stem"), "expected_output_stem_missing", "expected_output_stem is required")
    _require(
        isinstance(auth.get("allowed_output_extensions"), list)
        and auth.get("allowed_output_extensions") == list(approval.ALLOWED_OUTPUT_EXTENSIONS),
        "allowed_output_extensions_invalid",
        "allowed_output_extensions must match the approved extension set",
    )
    if handoff_report is not None and handoff_report.get("platform") is not None:
        _require(str(auth.get("platform") or "") == str(handoff_report.get("platform") or ""), "platform_invalid", "authorization platform must match handoff")
    _require(int(auth.get("provider_calls_performed", 0)) == 0, "authorization_provider_calls_not_zero", "authorization must start with zero provider calls")
    _require(int(auth.get("publish_calls_performed", 0)) == 0, "authorization_publish_calls_not_zero", "authorization must start with zero publish calls")
    _require(int(auth.get("retries_performed", 0)) == 0, "authorization_retries_not_zero", "authorization must start with zero retries")
    _require(auth.get("publish_authorized") is True, "publish_authorized_invalid", "publishing must be authorized for live execution")
    auth_result["handoff"] = {
        "path": handoff_path.resolve(),
        "sha256": standing_autonomy._sha256_file(handoff_path),
        "report": handoff_report,
    }
    auth_result["policy"] = policy_result
    auth_result["pre_consumption_sha256"] = _sha256_file(auth_path)
    return auth_result


def _validate_bound_artifact(path_value: str, sha_value: str, *, root: Path, code: str, label: str) -> dict[str, Any]:
    resolved = _ensure_path_within_root(Path(path_value), root, code=code, label=label, must_exist=True)
    observed_sha = _sha256_file(resolved)
    _require(observed_sha == sha_value, f"{code}_sha_mismatch", f"{label} SHA-256 does not match the bound value")
    return {
        "path": resolved,
        "sha256": observed_sha,
        "artifact": _read_json_object(resolved, code=f"{code}_invalid", label=label),
    }


def _resolve_candidate_artifact(candidate_artifact: dict[str, Any]) -> dict[str, Any]:
    resolved_candidate = candidate_artifact.get("candidate")
    if isinstance(resolved_candidate, dict):
        return resolved_candidate
    return candidate_artifact


def _authorized_output_paths(expected_output_directory: Path, expected_output_stem: str, allowed_output_extensions: list[str]) -> list[Path]:
    directory = _ensure_path_within_root(
        expected_output_directory,
        ROOT / "pipeline" / "higgsfield_library" / "lena",
        code="expected_output_directory_escape",
        label="expected output directory",
        must_exist=False,
    )
    _require(bool(expected_output_stem.strip()), "expected_output_stem_missing", "expected_output_stem is required")
    _require(
        isinstance(allowed_output_extensions, list)
        and allowed_output_extensions == list(approval.ALLOWED_OUTPUT_EXTENSIONS),
        "allowed_output_extensions_invalid",
        "allowed_output_extensions must match the approved extension set",
    )
    return [
        _ensure_path_within_root(
            directory / f"{expected_output_stem}{extension}",
            ROOT / "pipeline" / "higgsfield_library" / "lena",
            code="expected_output_path_escape",
            label="expected output path",
            must_exist=False,
        )
        for extension in allowed_output_extensions
    ]


def _ensure_report_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise LenaBoundedLiveCycleError("report_already_exists", f"aggregate receipt already exists: {path}")


def _stage_summary(stage: str, ok: bool, **data: Any) -> dict[str, Any]:
    return {"stage": stage, "ok": ok, **data}


def _qa_requires_human_visual_review(qa_artifact: dict[str, Any]) -> bool:
    reason_codes = qa_artifact.get("reason_codes")
    if isinstance(reason_codes, list) and "human_visual_review_required" in reason_codes:
        return True
    for field_name in ("exact_next_allowed_action", "next_allowed_action", "hard_stop_reason", "reason"):
        if str(qa_artifact.get(field_name) or "") == "human_visual_review_required":
            return True
    return False


def _qa_terminal_state(qa_artifact: dict[str, Any]) -> str:
    qa_status = str(qa_artifact.get("disposition") or qa_artifact.get("overall") or qa_artifact.get("status") or "").lower()
    if qa_status == "accept":
        return "accepted"
    if qa_status == "blocked" and _qa_requires_human_visual_review(qa_artifact):
        return "awaiting_human_visual_review"
    if qa_status in {"hard_stop", "fail", "rejected", "blocked"}:
        return "failed"
    return "failed"


def _build_package(
    auth: dict[str, Any],
    provider: dict[str, Any],
    qa: dict[str, Any],
    package_path: Path,
    *,
    generated_image_path: Path,
    generated_image_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    payload = {
        "report_type": "lena_bounded_live_cycle_package",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slot_id": auth["artifact"]["slot_id"],
        "candidate_id": auth["artifact"]["candidate_id"],
        "platform": auth["artifact"]["platform"],
        "caption": auth["artifact"]["caption"],
        "generated_image_path": str(generated_image_path),
        "generated_image_sha256": generated_image_sha256,
        "asset_path": str(generated_image_path),
        "asset_sha256": generated_image_sha256,
        "provider_generation_receipt_path": str(provider["path"]),
        "provider_generation_receipt_sha256": provider["sha256"],
        "manifest_path": str(provider["artifact"]["manifest_path"]),
        "manifest_sha256": provider["artifact"]["manifest_sha256"],
        "provider_generated_image_path": str(provider["artifact"]["generated_image_path"]),
        "provider_generated_image_sha256": provider["artifact"]["generated_image_sha256"],
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
        "generated_image_path": package["generated_image_path"],
        "generated_image_sha256": package["generated_image_sha256"],
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
        "generated_image_path": package["generated_image_path"],
        "generated_image_sha256": package["generated_image_sha256"],
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


def _authorization_lock_path(auth_path: Path) -> Path:
    return auth_path.with_name(f"{auth_path.name}.lock")


def _null_to_none(value: Any) -> Any:
    return None if value in ("", None) else value


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _load_reference_specs() -> tuple[Path, str, list[tuple[Path, str]]]:
    authority_path = ROOT / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json"
    authority = _read_json_object(
        authority_path,
        code="reference_authority_missing_or_invalid",
        label="reference authority artifact",
    )
    refs = authority.get("references")
    if not isinstance(refs, list) or not refs:
        raise LenaBoundedLiveCycleError("reference_authority_invalid", "reference authority must contain at least one reference")
    specs: list[tuple[Path, str]] = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        ref_path = item.get("path")
        ref_sha = item.get("sha256")
        if ref_path and ref_sha:
            specs.append((_ensure_path_within_root(Path(str(ref_path)), ROOT, code="reference_path_escape", label="reference artifact", must_exist=True), str(ref_sha)))
    if not specs:
        raise LenaBoundedLiveCycleError("reference_authority_invalid", "reference authority did not contain usable reference specs")
    return authority_path.resolve(), _sha256_file(authority_path), specs


def _controlled_photo_authority(auth: dict[str, Any]) -> dict[str, Any] | None:
    value = auth.get("artifact", {}).get("controlled_photo_autonomy")
    return dict(value) if isinstance(value, dict) and value.get("enabled") is True else None


def controlled_autonomous_disposition(qa_artifact: dict[str, Any], *, retries_performed: int) -> str:
    if qa_artifact.get("disposition") == "accept":
        return "accept_and_publish"
    if (
        retries_performed == 0
        and qa_artifact.get("disposition") == "retryable_failure"
        and qa_artifact.get("reason_codes") == ["hair_crown_forelock_artifact"]
    ):
        return "reject_and_retry"
    if qa_artifact.get("hard_stop_reason") in {"visual_review_unavailable", "corrupt_or_untrusted_evidence"}:
        return "operational_failure"
    return "reject_and_hold"


def _controlled_visual_qa_kwargs(
    auth: dict[str, Any],
    candidate_artifact: dict[str, Any],
    reference_authority_path: Path,
    *,
    decision_fingerprint: str | None = None,
) -> dict[str, Any]:
    controlled = _controlled_photo_authority(auth)
    if controlled is None:
        return {}
    configured_reference = (ROOT / str(controlled.get("identity_reference_authority_path") or "")).resolve()
    _require(configured_reference == reference_authority_path.resolve(), "controlled_reference_authority_mismatch", "controlled visual QA reference authority differs from the canonical authority")
    reference_authority = _read_json_object(reference_authority_path, code="reference_authority_missing_or_invalid", label="reference authority artifact")
    reference_set_sha = str(reference_authority.get("reference_set_sha256") or "")
    decision_fingerprint = str(decision_fingerprint or candidate_artifact.get("decision_fingerprint_sha256") or "")
    _require(len(decision_fingerprint) == 64, "controlled_candidate_fingerprint_missing", "controlled visual QA requires the selected candidate decision fingerprint")
    _require(len(reference_set_sha) == 64, "controlled_reference_set_sha_missing", "controlled visual QA requires the canonical reference-set SHA")
    qa_kwargs = {
        "qa_mode": str(controlled.get("qa_mode") or photo_qa.QA_MODE_AUTONOMOUS_LOCAL),
        "expected_decision_fingerprint": decision_fingerprint,
        "expected_reference_set_sha256": reference_set_sha,
    }
    diagnostic = controlled.get("external_visual_diagnostic")
    if isinstance(diagnostic, dict):
        authority_path = (ROOT / str(diagnostic.get("visual_model_authority_path") or "")).resolve()
        _ensure_path_within_root(authority_path, ROOT, code="visual_model_authority_escape", label="visual model authority", must_exist=True)
        qa_kwargs.update(
            {
                "external_visual_diagnostic_enabled": bool(diagnostic.get("enabled", False)),
                "external_visual_diagnostic_provider": str(diagnostic.get("provider") or ""),
                "external_visual_diagnostic_model": str(diagnostic.get("model") or ""),
                "external_visual_diagnostic_authority_artifact": authority_path,
                "external_visual_diagnostic_authority_sha256": _sha256_file(authority_path),
                "external_visual_diagnostic_authorized": bool(
                    diagnostic.get("enabled", False) and diagnostic.get("explicit_authorization_required") is not True
                ),
            }
        )
    return qa_kwargs


def _issue_controlled_retry_approval(auth: dict[str, Any], retry_handoff_path: Path) -> dict[str, Any]:
    retry_facts = retry_approval.inspect_retry_handoff_artifact(retry_handoff_path)
    record = retry_approval.build_standing_autonomy_retry_generation_approval_record(
        retry_facts,
        auth,
    )
    path = retry_approval.approval_output_path(retry_facts["date"], retry_facts["slot_id"])
    retry_approval.write_retry_generation_approval_record_atomic(path, record)
    return retry_approval.validate_retry_generation_approval_artifact(path)


def _identity_evidence_reuse_fingerprint(evidence: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise LenaBoundedLiveCycleError("identity_evidence_existing_invalid", "identity evidence must be a JSON object")

    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): _normalize(subvalue)
                for key, subvalue in value.items()
                if key not in {"verified_at_utc", "created_at_utc"}
            }
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        return value

    return _normalize(evidence)


def _build_local_identity_evidence(
    *,
    date_str: str,
    slot_id: str,
    manifest: dict[str, Any],
    image_path: Path,
    image_sha256: str,
    identity_evidence_path: Path,
) -> tuple[Path, dict[str, Any], bool]:
    try:
        return local_identity_evidence.build_local_identity_evidence(
            date_str=date_str,
            slot_id=slot_id,
            manifest=manifest,
            image_path=image_path,
            image_sha256=image_sha256,
            identity_evidence_path=identity_evidence_path,
        )
    except local_identity_evidence.LenaIdentityEvidenceError as exc:
        code = "recovery_identity_evidence_mismatch" if exc.code == "identity_evidence_already_exists" else exc.code
        raise LenaBoundedLiveCycleError(code, exc.detail) from exc


def _build_live_package(
    *,
    auth: dict[str, Any],
    approval_result: dict[str, Any],
    provider_result: dict[str, Any],
    qa_result: dict[str, Any],
    package_path: Path,
    publish_sidecar_path: Path,
    publish_sidecar_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    live_result = provider_result["live_result"]
    manifest = provider_result["manifest"]
    generated_image_path = Path(str(live_result["saved_image_path"]))
    package = {
        "report_type": "lena_bounded_live_cycle_package",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cycle_id": auth["artifact"].get("cycle_id"),
        "authorization_mode": auth["artifact"].get("authorization_mode", "standing_autonomy_policy"),
        "authorization_artifact_path": str(auth["path"]),
        "authorization_artifact_sha256": auth.get("pre_consumption_sha256", auth["sha256"]),
        "policy_artifact_path": str(auth["artifact"].get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(auth["artifact"].get("policy_artifact_sha256") or ""),
        "candidate_artifact_path": str(auth["artifact"]["candidate_artifact_path"]),
        "candidate_artifact_sha256": str(auth["artifact"]["candidate_artifact_sha256"]),
        "prompt_sha256": str(approval_result["handoff_facts"]["prompt_sha256"]),
        "slot_id": str(auth["artifact"]["slot_id"]),
        "platform": str(auth["artifact"]["platform"]),
        "caption": str(auth["artifact"]["caption"]),
        "media_type": "photo",
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
        "manifest_artifact_path": str(provider_result["manifest_path"]),
        "manifest_artifact_sha256": provider_result["manifest_sha256"],
        "generated_image_path": str(generated_image_path),
        "generated_image_sha256": provider_result["generated_image_sha256"],
        "qa_artifact_path": str(qa_result["path"]),
        "qa_artifact_sha256": qa_result["sha256"],
        "publish_sidecar_path": str(publish_sidecar_path),
        "publish_sidecar_sha256": publish_sidecar_sha256,
        "publishing_authorized": True,
        "provider_calls_performed": 1,
        "publish_calls_performed": 0,
        "retries_performed": 0,
    }
    _write_json_atomic(package_path, package)
    package["package_artifact_path"] = str(package_path)
    package["package_artifact_sha256"] = _sha256_file(package_path)
    return package_path, package


def _build_live_publish_sidecar(
    *,
    authorization: dict[str, Any],
    image_path: Path,
    caption: str,
    platform: str,
    controlled_lineage: dict[str, str] | None = None,
    clean_export_report: dict[str, Any] | None = None,
    publish_policy_result: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any], str]:
    sidecar_path = image_path.with_suffix(".status.json")
    payload = {
        "visual_status": "approved",
        "authorization_mode": "standing_autonomy_policy",
        "policy_id": authorization["artifact"].get("policy_id"),
        "policy_version": authorization["artifact"].get("policy_version"),
        "policy_sha256": authorization["artifact"].get("policy_artifact_sha256"),
        "cycle_id": authorization["artifact"].get("cycle_id"),
        "cycle_authorization_path": str(authorization["path"]),
        "cycle_authorization_sha256": authorization["sha256"],
        "qa_approved": True,
        "identity_verified": True,
        "duplicate_check_passed": True,
        "publish_authorized_by_policy": True,
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
        "publish_approved": True,
        "caption_approved": True,
        "caption_visual_match_approved": True,
        "publish_blocked_reason": "",
        "no_publish_without_explicit_future_approval": False,
        "instagram_published": False,
        "instagram_currently_live": False,
        "r2_uploaded": False,
        "queue_entry_created": False,
        "asset_path": _repo_relative(image_path),
        "caption": caption,
        "target_platform": platform,
    }
    if controlled_lineage is not None or clean_export_report is not None:
        _require(controlled_lineage is not None and clean_export_report is not None and publish_policy_result is not None, "clean_export_binding_incomplete", "controlled publish sidecar requires clean-export report, publication policy, and complete lineage")
        payload["generation_policy_id"] = payload["policy_id"]
        payload["generation_policy_sha256"] = payload["policy_sha256"]
        payload["policy_id"] = publish_policy_result["artifact"]["policy_id"]
        payload["policy_version"] = publish_policy_result["artifact"]["policy_version"]
        payload["policy_sha256"] = publish_policy_result["sha256"]
        payload.update(
            {
                "controlled_photo_autonomy": True,
                "asset_sha256": str(clean_export_report["output_sha256"]),
                "provider_original_path": str(clean_export_report["source_path"]),
                "provider_original_sha256": str(clean_export_report["source_sha256"]),
                "privacy_clean_verified": True,
                "clean_export_report_path": _repo_relative(Path(str(clean_export_report["report_path"]))),
                "clean_export_report_sha256": str(clean_export_report["report_sha256"]),
                "lineage": dict(controlled_lineage),
            }
        )
    _write_json_atomic(sidecar_path, payload)
    return sidecar_path, payload, _sha256_file(sidecar_path)


def _publisher_script_for_platform(platform: str) -> Path:
    if platform == "Instagram Feed":
        return ROOT / "tools" / "publishers" / "lena_publish_instagram_feed_v2_8.py"
    if platform == "Facebook Page":
        return ROOT / "tools" / "publishers" / "lena_publish_facebook_page_v2_8.py"
    raise LenaBoundedLiveCycleError("platform_mismatch", f"unsupported platform for live publishing: {platform}")


def _run_publisher(
    *,
    platform: str,
    payload_path: Path,
) -> dict[str, Any]:
    script = _publisher_script_for_platform(platform)
    proc = subprocess.run(
        [PY, str(script), "--payload", str(payload_path)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = (proc.stdout or "").strip()
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError as exc:
        raise LenaBoundedLiveCycleError("publish_output_invalid", f"publisher output was not valid JSON: {exc}") from exc
    if proc.returncode != 0:
        raise LenaBoundedLiveCycleError(
            "publish_failed",
            f"publisher exited {proc.returncode}: {json.dumps(parsed, ensure_ascii=True)}",
        )
    if not isinstance(parsed, dict):
        raise LenaBoundedLiveCycleError("publish_output_invalid", "publisher output must be a JSON object")
    return {
        "cmd": [PY, str(script), "--payload", str(payload_path)],
        "cmd_text": subprocess.list2cmdline([PY, str(script), "--payload", str(payload_path)]),
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": proc.stderr or "",
        "parsed": parsed,
    }


def _build_live_publish_receipt(
    *,
    auth: dict[str, Any],
    package_path: Path,
    package_sha256: str,
    publish_sidecar_path: Path,
    publish_sidecar_sha256: str,
    publisher_result: dict[str, Any],
    publish_receipt_path: Path,
) -> tuple[Path, dict[str, Any]]:
    payload = {
        "report_type": "lena_bounded_live_cycle_publish_receipt",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cycle_id": auth["artifact"].get("cycle_id"),
        "authorization_mode": auth["artifact"].get("authorization_mode", "standing_autonomy_policy"),
        "authorization_artifact_path": str(auth["path"]),
        "authorization_artifact_sha256": auth.get("pre_consumption_sha256", auth["sha256"]),
        "policy_artifact_path": str(auth["artifact"].get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(auth["artifact"].get("policy_artifact_sha256") or ""),
        "slot_id": str(auth["artifact"]["slot_id"]),
        "candidate_id": str(auth["artifact"]["candidate_id"]),
        "platform": str(auth["artifact"]["platform"]),
        "media_type": "photo",
        "caption": str(auth["artifact"]["caption"]),
        "package_artifact_path": str(package_path),
        "package_artifact_sha256": package_sha256,
        "publish_sidecar_path": str(publish_sidecar_path),
        "publish_sidecar_sha256": publish_sidecar_sha256,
        "publish_payload_path": str(publisher_result["payload_path"]),
        "publish_payload_sha256": publisher_result["payload_sha256"],
        "publish_calls_performed": 1,
        "provider_calls_performed": 1,
        "provider_calls_unchanged": True,
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
        "remote_post_id": publisher_result["parsed"].get("post_id") or publisher_result["parsed"].get("id"),
        "remote_post_url": publisher_result["parsed"].get("post_url", ""),
        "published_at_utc": publisher_result["parsed"].get("posted_at") or publisher_result["parsed"].get("published_at") or "",
        "publish_script": _repo_relative(_publisher_script_for_platform(str(auth["artifact"]["platform"]))),
        "returncode": publisher_result["returncode"],
        "stdout": publisher_result["stdout"],
        "stderr": publisher_result["stderr"],
        "publishing_authorized": True,
        "simulation_only": False,
    }
    _write_json_atomic(publish_receipt_path, payload)
    payload["publish_receipt_artifact_path"] = str(publish_receipt_path)
    payload["publish_receipt_artifact_sha256"] = _sha256_file(publish_receipt_path)
    return publish_receipt_path, payload


def _build_live_analytics_handoff(
    *,
    auth: dict[str, Any],
    package_path: Path,
    package_sha256: str,
    publish_receipt_path: Path,
    publish_receipt_sha256: str,
    analytics_handoff_path: Path,
) -> tuple[Path, dict[str, Any]]:
    payload = {
        "report_type": "lena_bounded_live_cycle_analytics_handoff",
        "schema_version": "v1",
        "created_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cycle_id": auth["artifact"].get("cycle_id"),
        "authorization_mode": auth["artifact"].get("authorization_mode", "standing_autonomy_policy"),
        "authorization_artifact_path": str(auth["path"]),
        "authorization_artifact_sha256": auth.get("pre_consumption_sha256", auth["sha256"]),
        "policy_artifact_path": str(auth["artifact"].get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(auth["artifact"].get("policy_artifact_sha256") or ""),
        "slot_id": str(auth["artifact"]["slot_id"]),
        "candidate_id": str(auth["artifact"]["candidate_id"]),
        "platform": str(auth["artifact"]["platform"]),
        "package_artifact_path": str(package_path),
        "package_artifact_sha256": package_sha256,
        "publish_receipt_artifact_path": str(publish_receipt_path),
        "publish_receipt_artifact_sha256": publish_receipt_sha256,
        "remote_post_id": _read_json_object(publish_receipt_path, code="publish_receipt_invalid", label="publish receipt").get("remote_post_id"),
        "provider_calls_performed": 1,
        "publish_calls_performed": 1,
        "analytics_mutation_performed": False,
        "simulation_only": False,
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
    }
    _write_json_atomic(analytics_handoff_path, payload)
    payload["analytics_handoff_artifact_path"] = str(analytics_handoff_path)
    payload["analytics_handoff_artifact_sha256"] = _sha256_file(analytics_handoff_path)
    return analytics_handoff_path, payload


def _consume_authorization_artifact(auth: dict[str, Any], *, cycle_id: str) -> dict[str, Any]:
    auth_path = Path(auth["path"])
    lock_path = _authorization_lock_path(auth_path)
    pre_consumption_sha256 = auth.get("pre_consumption_sha256", auth["sha256"])
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LenaBoundedLiveCycleError("authorization_consumption_in_progress", f"authorization is already being consumed: {auth_path}") from exc
    try:
        os.close(lock_fd)
        consumed_payload = dict(auth["artifact"])
        consumed_payload["consumed"] = True
        consumed_payload["consumed_at_utc"] = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
        consumed_payload["cycle_id"] = cycle_id
        consumed_payload["cycle_authorization_sha256"] = pre_consumption_sha256
        consumed_payload["authorization_consumption_implemented"] = True
        consumed_payload["authorization_consumed"] = True
        consumed_payload["authorization_state_after"] = {
            "single_use": True,
            "consumed": True,
            "consumed_at_utc": consumed_payload["consumed_at_utc"],
        }
        temp_path = auth_path.with_name(f"{auth_path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(consumed_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(str(temp_path), str(auth_path))
        return {
            **auth,
            "artifact": consumed_payload,
            "sha256": _sha256_file(auth_path),
            "pre_consumption_sha256": pre_consumption_sha256,
            "consumed_at_utc": consumed_payload["consumed_at_utc"],
            "cycle_id": cycle_id,
        }
    finally:
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass


def _validate_live_required_artifacts(auth: dict[str, Any]) -> dict[str, Any]:
    artifact = auth["artifact"]
    policy_path = _ensure_path_within_root(
        Path(str(artifact.get("policy_artifact_path") or "")),
        POLICY_ROOT,
        code="policy_path_escape",
        label="standing autonomy policy artifact",
        must_exist=True,
    )
    handoff_path = _ensure_path_within_root(
        Path(
            str(artifact.get("generation_handoff_artifact_path") or "")
        ),
        ROOT,
        code="handoff_path_escape",
        label="generation handoff artifact",
        must_exist=True,
    )
    candidate_path = _ensure_path_within_root(
        Path(str(artifact.get("candidate_artifact_path") or "")),
        ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
        code="candidate_path_escape",
        label="candidate artifact",
        must_exist=True,
    )
    expected_output_directory = _ensure_path_within_root(
        Path(str(artifact.get("expected_output_directory") or "")),
        ROOT / "pipeline" / "higgsfield_library" / "lena",
        code="expected_output_directory_escape",
        label="expected output directory",
        must_exist=False,
    )
    expected_output_stem = str(artifact.get("expected_output_stem") or "")
    allowed_output_extensions = list(artifact.get("allowed_output_extensions") or [])
    authorized_output_paths = _authorized_output_paths(expected_output_directory, expected_output_stem, allowed_output_extensions)
    return {
        "policy_path": policy_path,
        "handoff_path": handoff_path,
        "candidate_path": candidate_path,
        "expected_output_directory": expected_output_directory,
        "expected_output_stem": expected_output_stem,
        "allowed_output_extensions": allowed_output_extensions,
        "authorized_output_paths": authorized_output_paths,
    }


def _build_uncontrolled_autonomous_approval_result(
    auth: dict[str, Any], live_requirements: dict[str, Any]
) -> dict[str, Any]:
    """Legacy in-memory approval_result for standing-autonomy cycles outside
    the governed hcr_012/wc_p050 lane. Unchanged from the pre-existing
    behavior (never exercised against the real manual-approval lineage
    chain in production -- execute_approved_handoff_live_generation is
    always mocked wherever this path is tested). The controlled lane uses
    _issue_standing_autonomy_generation_approval instead, which issues a
    real, independently re-validated approval artifact.
    """
    artifact = auth["artifact"]
    handoff_report = auth["handoff"]["report"]
    handoff_path = live_requirements["handoff_path"]
    candidate_path = live_requirements["candidate_path"]
    candidate = handoff_report.get("selected_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    approval_artifact = dict(artifact)
    approval_artifact["operator_id"] = "lena_autonomy_controller"
    approval_artifact["provider"] = str(artifact.get("allowed_provider") or artifact.get("provider") or "Higgsfield")
    approval_artifact["executor"] = "Higgsfield CLI repo adapter"
    approval_artifact["model"] = str(
        artifact.get("allowed_model") or artifact.get("model") or approval.MODEL
    )
    approval_artifact["aspect_ratio"] = "9:16"
    approval_artifact["soul_name"] = str(artifact.get("allowed_soul") or artifact.get("soul_name") or "Lena")
    approval_artifact["soul_type"] = str(artifact.get("soul_type") or "Soul 2.0")
    approval_artifact["custom_reference_id"] = str(handoff_report.get("custom_reference_id") or artifact.get("custom_reference_id") or "")
    approval_artifact["generation_reference"] = handoff_report.get("generation_reference")
    approval_artifact["authorized_attempts"] = 1
    approval_artifact["upload_authorized"] = False
    approval_artifact["queue_promotion_authorized"] = False
    approval_artifact["publish_authorized"] = True
    approval_artifact["analytics_mutation_authorized"] = False
    approval_artifact["handoff_artifact_path"] = str(handoff_path)
    approval_artifact["handoff_artifact_sha256"] = _sha256_file(handoff_path)
    approval_artifact["handoff_report_type"] = str(handoff_report.get("report_type") or "lena_next_live_image_handoff")
    approval_artifact["handoff_schema_version"] = str(handoff_report.get("schema_version") or "v1")
    approval_artifact["reconciliation"] = handoff_report.get("reconciliation")
    approval_artifact["reconciled_candidate"] = handoff_report.get("selected_candidate")
    approval_artifact["reconciliation_decision"] = handoff_report.get("reconciliation_decision")
    handoff_facts = {
        "date": str(handoff_report.get("date") or artifact.get("date") or ""),
        "slot_id": str(handoff_report.get("selected_slot_id") or artifact.get("slot_id") or ""),
        "prompt_sha256": str(handoff_report.get("prompt_sha256") or artifact.get("prompt_sha256") or ""),
        "custom_reference_id": str(handoff_report.get("custom_reference_id") or artifact.get("custom_reference_id") or ""),
        "handoff_path": str(handoff_path),
        "handoff_repo_path": _repo_relative(handoff_path),
        "handoff_sha256": _sha256_file(handoff_path),
        "selected_candidate_path": str(handoff_report.get("selected_candidate_path") or artifact.get("candidate_artifact_path") or ""),
        "selected_candidate_sha256": str(handoff_report.get("selected_candidate_sha256") or artifact.get("candidate_artifact_sha256") or ""),
        "selected_candidate": candidate,
        "report": handoff_report,
        "reconciliation": handoff_report.get("reconciliation"),
        "reconciled_candidate": handoff_report.get("selected_candidate"),
        "reconciliation_decision": handoff_report.get("reconciliation_decision"),
        "soul_name": approval_artifact["soul_name"],
        "soul_type": approval_artifact["soul_type"],
    }
    return {
        "approval": approval_artifact,
        "approval_path": auth["path"],
        "approval_repo_path": str(auth["path"].relative_to(ROOT)),
        "approval_sha256": auth.get("pre_consumption_sha256", auth["sha256"]),
        "handoff_facts": handoff_facts,
        "approved_at_utc": auth["artifact"].get("issued_at_utc"),
        "expires_at_utc": auth["artifact"].get("expires_at_utc"),
        "is_expired": False,
        "scope_summary": {
            "authorized_attempts": 1,
            "upload_authorized": False,
            "queue_promotion_authorized": False,
            "publish_authorized": True,
            "analytics_mutation_authorized": False,
        },
        "authorization_mode": auth["artifact"].get("authorization_mode", "standing_autonomy_policy"),
        "policy_result": auth.get("policy"),
        "policy_path": auth.get("policy", {}).get("path") if isinstance(auth.get("policy"), dict) else None,
        "candidate_artifact_path": candidate_path,
    }


def _issue_standing_autonomy_generation_approval(
    auth: dict[str, Any], live_requirements: dict[str, Any]
) -> dict[str, Any]:
    """Issue, write, and validate a real standing-autonomy generation approval
    for the governed hcr_012/wc_p050 controlled lane.

    Replaces the previous in-memory-only approval_result for that lane: the
    executor's claim/receipt writers independently re-read and re-validate
    the approval artifact from disk (see lena_higgsfield_generation_approval_v1's
    manual lineage chain, which the standing-autonomy path must satisfy with
    its own parallel artifact rather than a hand-built dict impersonating
    one). Cycles outside the controlled lane fall back to the legacy
    in-memory behavior, unchanged.
    """
    if _controlled_photo_authority(auth) is None:
        return _build_uncontrolled_autonomous_approval_result(auth, live_requirements)

    from tools import lena_higgsfield_standing_autonomy_generation_approval_v1 as standing_generation_approval

    handoff_path = live_requirements["handoff_path"]
    candidate_path = live_requirements["candidate_path"]
    handoff_facts = standing_generation_approval.inspect_generation_handoff_for_standing_autonomy(
        handoff_path, candidate_path
    )
    record = standing_generation_approval.build_standing_autonomy_generation_approval_record(handoff_facts, auth)
    approval_path = standing_generation_approval.approval_output_path(handoff_facts["date"], handoff_facts["slot_id"])
    standing_generation_approval.write_standing_autonomy_generation_approval_record_atomic(approval_path, record)
    return standing_generation_approval.validate_standing_autonomy_generation_approval_artifact(
        approval_path, require_not_expired=False
    )


def _manifest_output_image_path(manifest: dict[str, Any], expected_directory: Path, expected_stem: str, allowed_output_extensions: list[str]) -> Path:
    saved_image = Path(str(manifest.get("saved_image_path") or ""))
    resolved = _ensure_path_within_root(
        saved_image,
        ROOT / "pipeline" / "higgsfield_library" / "lena",
        code="generated_image_path_escape",
        label="generated image path",
        must_exist=True,
    )
    _require(resolved.parent == expected_directory, "generated_image_directory_mismatch", "generated image directory does not match the authorized output directory")
    _require(resolved.stem == expected_stem, "generated_image_stem_mismatch", "generated image stem does not match the authorized output stem")
    _require(resolved.suffix in set(allowed_output_extensions), "generated_image_extension_mismatch", "generated image extension does not match the authorized output extensions")
    return resolved


def _artifact_evidence(path_value: Any) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(str(path_value)).resolve(strict=False)
    evidence: dict[str, Any] = {"path": str(path), "sha256": None}
    if path.is_file():
        evidence["sha256"] = _sha256_file(path)
    return evidence


def _provider_failure_evidence(provider_result: dict[str, Any]) -> dict[str, Any]:
    live_result = provider_result.get("live_result") if isinstance(provider_result.get("live_result"), dict) else {}
    claim = _artifact_evidence(provider_result.get("claim_path"))
    receipt = _artifact_evidence(provider_result.get("receipt_path"))
    manifest = _artifact_evidence(provider_result.get("manifest_path"))
    image_path_value = live_result.get("saved_image_path")
    if not image_path_value and manifest and Path(manifest["path"]).is_file():
        try:
            image_path_value = _read_json_object(Path(manifest["path"]), code="provider_manifest_missing_or_invalid", label="provider generation manifest").get("saved_image_path")
        except LenaBoundedLiveCycleError:
            image_path_value = None
    image = _artifact_evidence(image_path_value)
    provider_job_id = live_result.get("job_id")
    if not provider_job_id and receipt and Path(receipt["path"]).is_file():
        try:
            provider_job_id = _read_json_object(Path(receipt["path"]), code="provider_receipt_missing_or_invalid", label="provider generation receipt").get("provider_job_id")
        except LenaBoundedLiveCycleError:
            provider_job_id = None
    return {
        "provider_calls_performed": 1,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "provider_job_id": provider_job_id,
        "generated_image_path": image["path"] if image else None,
        "generated_image_sha256": image["sha256"] if image else None,
        "provider_generation_evidence": {
            "claim": claim,
            "receipt": receipt,
            "manifest": manifest,
            "generated_image": image,
        },
    }


def _validate_completed_provider_result(
    provider_result: dict[str, Any],
    *,
    live_requirements: dict[str, Any],
    approval_result: dict[str, Any],
    auth_data: dict[str, Any],
) -> dict[str, Any]:
    claim_path = Path(str(provider_result["claim_path"]))
    receipt_path = Path(str(provider_result["receipt_path"]))
    manifest_path = Path(str(provider_result["manifest_path"]))
    live_result = provider_result["live_result"] or {}
    provider_manifest = _read_json_object(manifest_path, code="provider_manifest_missing_or_invalid", label="provider generation manifest")
    provider_claim = _read_json_object(claim_path, code="provider_claim_missing_or_invalid", label="provider generation claim")
    provider_receipt = _read_json_object(receipt_path, code="provider_receipt_missing_or_invalid", label="provider generation receipt")
    generated_image_path = _manifest_output_image_path(
        provider_manifest,
        live_requirements["expected_output_directory"],
        live_requirements["expected_output_stem"],
        live_requirements["allowed_output_extensions"],
    )
    generated_image_sha256 = _sha256_file(generated_image_path)
    manifest_sha256 = _sha256_file(manifest_path)
    _require(str(provider_manifest.get("slot_id") or "") == str(auth_data["slot_id"]), "provider_manifest_slot_mismatch", "provider manifest slot_id mismatch")
    _require(str(provider_manifest.get("prompt_sha256") or "") == str(approval_result["handoff_facts"]["prompt_sha256"]), "provider_manifest_prompt_mismatch", "provider manifest prompt sha mismatch")
    _require(str(provider_manifest.get("provider_job_id") or "") == str(live_result.get("job_id") or provider_manifest.get("provider_job_id") or ""), "provider_manifest_job_mismatch", "provider manifest provider_job_id mismatch")
    _require(str(provider_receipt.get("provider_job_id") or "") == str(provider_manifest.get("provider_job_id") or ""), "provider_receipt_job_mismatch", "provider receipt provider_job_id mismatch")
    _require(str(provider_receipt.get("output_path") or "") == str(generated_image_path), "provider_receipt_output_mismatch", "provider receipt output_path mismatch")
    _require(str(provider_receipt.get("generated_image_sha256") or "") == generated_image_sha256, "provider_receipt_image_sha_mismatch", "provider receipt generated image sha mismatch")
    _require(str(provider_receipt.get("manifest_sha256") or "") == manifest_sha256, "provider_receipt_manifest_sha_mismatch", "provider receipt manifest sha mismatch")
    _require(str(provider_manifest.get("saved_image_path") or "") == str(generated_image_path), "provider_manifest_image_mismatch", "provider manifest saved image mismatch")
    _require(str(provider_manifest.get("saved_image_sha256") or "") == generated_image_sha256, "provider_manifest_image_sha_mismatch", "provider manifest image sha mismatch")
    return {
        "claim_path": claim_path,
        "receipt_path": receipt_path,
        "manifest_path": manifest_path,
        "live_result": live_result,
        "provider_manifest": provider_manifest,
        "provider_claim": provider_claim,
        "provider_receipt": provider_receipt,
        "generated_image_path": generated_image_path,
        "generated_image_sha256": generated_image_sha256,
        "manifest_sha256": manifest_sha256,
    }


def _validate_completed_retry_provider_result(
    provider_result: dict[str, Any],
    *,
    retry_facts: dict[str, Any],
) -> dict[str, Any]:
    _require(provider_result.get("ok") is True, "retry_provider_generation_failed", str(provider_result.get("failure_error_text") or "retry generation failed"))
    claim_path = Path(str(provider_result["claim_path"]))
    receipt_path = Path(str(provider_result["receipt_path"]))
    manifest_path_value = Path(str(provider_result["manifest_path"]))
    live_result = provider_result.get("live_result") or {}
    provider_manifest = _read_json_object(manifest_path_value, code="retry_manifest_missing_or_invalid", label="retry generation manifest")
    provider_claim = _read_json_object(claim_path, code="retry_claim_missing_or_invalid", label="retry generation claim")
    provider_receipt = _read_json_object(receipt_path, code="retry_receipt_missing_or_invalid", label="retry generation receipt")
    expected_directory = approval.expected_output_directory(retry_facts["date"])
    expected_stem = approval.expected_output_stem(retry_facts["slot_id"])
    generated_image_path = _manifest_output_image_path(
        provider_manifest,
        expected_directory,
        expected_stem,
        list(approval.ALLOWED_OUTPUT_EXTENSIONS),
    )
    generated_image_sha256 = _sha256_file(generated_image_path)
    _require(provider_manifest.get("slot_id") == retry_facts["slot_id"], "retry_manifest_slot_mismatch", "retry manifest slot does not match retry handoff")
    _require(provider_manifest.get("prompt_sha256") == retry_facts["prompt_sha256"], "retry_manifest_prompt_mismatch", "retry manifest prompt does not match retry handoff")
    _require(provider_manifest.get("saved_image_sha256") == generated_image_sha256, "retry_manifest_image_sha_mismatch", "retry manifest image SHA does not match current bytes")
    expected_retry_approval_path = retry_approval.approval_output_path(retry_facts["date"], retry_facts["slot_id"])
    _require(provider_receipt.get("approval_artifact_path") == retry_approval.repo_relative_path(expected_retry_approval_path), "retry_receipt_approval_path_mismatch", "retry receipt approval path is not canonical")
    _require(provider_receipt.get("retry_handoff_artifact_sha256") == retry_facts["retry_handoff_sha256"], "retry_receipt_handoff_mismatch", "retry receipt handoff SHA does not match")
    _require(provider_receipt.get("prompt_sha256") == retry_facts["prompt_sha256"], "retry_receipt_prompt_mismatch", "retry receipt prompt SHA does not match")
    _require(provider_receipt.get("output_path") == str(generated_image_path), "retry_receipt_output_mismatch", "retry receipt output path does not match")
    _require(provider_receipt.get("outcome") == "success", "retry_receipt_outcome_invalid", "retry receipt must record success")
    return {
        "claim_path": claim_path,
        "receipt_path": receipt_path,
        "manifest_path": manifest_path_value,
        "live_result": live_result,
        "provider_manifest": provider_manifest,
        "provider_claim": provider_claim,
        "provider_receipt": provider_receipt,
        "generated_image_path": generated_image_path,
        "generated_image_sha256": generated_image_sha256,
        "manifest_sha256": _sha256_file(manifest_path_value),
    }


def _build_fail_report(
    *,
    auth: dict[str, Any] | None,
    report_path: Path,
    started_at: str,
    cycle_id: str | None,
    stages: list[dict[str, Any]],
    failed_stage: str,
    error_code: str,
    error_detail: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = auth["artifact"] if auth else {}
    daily_usage_before = artifact.get("daily_usage_before") if auth else None
    daily_usage_after = artifact.get("daily_usage_after") if auth else None
    report: dict[str, Any] = {
        "ok": False,
        "version": "v1",
        "report_type": "lena_bounded_live_cycle",
        "simulation_mode": False if auth else True,
        "live_execution": bool(auth),
        "autonomous_execution": bool(auth),
        "authorization_mode": artifact.get("authorization_mode", "standing_autonomy_policy" if auth else ""),
        "date": str(artifact.get("date") or ""),
        "started_at": started_at,
        "finished_at": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "cycle_id": cycle_id,
        "authorization_artifact_path": str(auth["path"]) if auth else "",
        "authorization_artifact_sha256": auth["sha256"] if auth else "",
        "authorization_artifact_sha256_before_consumption": auth.get("pre_consumption_sha256") if auth else None,
        "policy_artifact_path": str(artifact.get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(artifact.get("policy_artifact_sha256") or ""),
        "authorization_consumption_implemented": bool(auth),
        "authorization_consumed": bool(auth and auth["artifact"].get("consumed") is True),
        "authorization_consumed_at_utc": auth.get("consumed_at_utc") if auth else None,
        "authorization_state_before": {
            "single_use": artifact.get("single_use", True),
            "consumed": bool(artifact.get("consumed", False)),
            "consumed_at_utc": _null_to_none(artifact.get("consumed_at_utc")),
        },
        "authorization_state_after": {
            "single_use": artifact.get("single_use", True),
            "consumed": bool(auth and auth["artifact"].get("consumed") is True),
            "consumed_at_utc": auth.get("consumed_at_utc") if auth else None,
        },
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "declared_spend_unit": artifact.get("spend_unit"),
        "actual_spend": None,
        "actual_spend_available": False,
        "daily_usage_before": daily_usage_before,
        "daily_usage_after": daily_usage_after,
        "stage_coverage": stages,
        "stages": stages,
        "failed_stage": failed_stage,
        "failure": {
            "code": error_code,
            "detail": error_detail,
        },
        "safeguards": {
            "single_use": True,
            "one_slot": True,
            "one_candidate": True,
            "one_asset": True,
            "one_platform": True,
            "provider_call_cap_per_cycle": int(artifact.get("provider_call_cap_per_cycle", 1)),
            "publish_action_cap_per_cycle": 1,
            "retry_cap_per_cycle": int(artifact.get("retry_cap_per_cycle", 0)),
            "daily_spend_ceiling": artifact.get("daily_spend_ceiling", 0),
            "spend_unit": artifact.get("spend_unit", ""),
            "kill_switch_enabled": artifact.get("kill_switch_enabled", False),
            "duplicate_rejection": "report_path_must_not_exist",
            "no_scheduler": not bool(artifact.get("controlled_photo_autonomy")),
            "no_second_provider_call": int(artifact.get("provider_call_cap_per_cycle", 1)) < 2,
            "no_second_publish_call": True,
            "analytics_triggered_rerun_blocked": True,
            "qa_required": True,
            "identity_verification_required": True,
        },
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
    }
    if extra:
        report.update(_json_safe_report_value(extra))
    _write_json_atomic(report_path, report)
    report["report_path"] = str(report_path)
    return report


def _run_live_cycle(auth_artifact: Path, *, report_root: Path, hold_for_publish: bool = False) -> dict[str, Any]:
    auth = _validate_authorization_artifact(auth_artifact, simulate=False)
    auth_data = auth["artifact"]
    day = str(auth_data["date"])
    started_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = datetime.now().strftime("%H%M%S")
    report_path = _report_path(day, stamp, report_root)
    _ensure_path_within_root(report_path, report_root, code="report_path_escape", label="aggregate receipt", must_exist=False)
    _ensure_report_dir(report_path)
    cycle_id = str(auth_data.get("cycle_id") or f"lena_bounded_live_cycle_{day}_{stamp}_{uuid.uuid4().hex[:8]}")
    stages: list[dict[str, Any]] = [
        _stage_summary(
            "authorization_validation",
            True,
            authorization_artifact_path=str(auth["path"]),
            authorization_artifact_sha256=auth["sha256"],
            policy_artifact_path=str(auth["policy"]["path"]),
            policy_artifact_sha256=auth["policy"]["sha256"],
        )
    ]

    live_requirements = _validate_live_required_artifacts(auth)
    for output_path in live_requirements["authorized_output_paths"]:
        _require(not output_path.exists(), "expected_output_conflict", f"authorized output path already exists: {output_path}")
    auth = _consume_authorization_artifact(auth, cycle_id=cycle_id)
    auth_data = auth["artifact"]
    stages.append(
        _stage_summary(
            "authorization_consumption",
            True,
            authorization_artifact_path=str(auth["path"]),
            authorization_artifact_sha256=auth["sha256"],
            authorization_artifact_sha256_before_consumption=auth["pre_consumption_sha256"],
            consumed_at_utc=auth["consumed_at_utc"],
            cycle_id=cycle_id,
        )
    )

    candidate_path = live_requirements["candidate_path"]
    candidate = _read_json_object(candidate_path, code="candidate_missing_or_invalid", label="candidate artifact")
    candidate_sha256 = _sha256_file(candidate_path)
    _require(candidate_sha256 == str(auth_data["candidate_artifact_sha256"]), "candidate_sha_mismatch", "candidate SHA-256 does not match the authorization binding")
    _require(candidate_path == Path(str(auth_data["candidate_artifact_path"])).resolve(), "candidate_path_mismatch", "candidate path does not match the authorization binding")
    resolved_candidate = _resolve_candidate_artifact(candidate)
    _require(str(resolved_candidate.get("candidate_id") or "") == str(auth_data["candidate_id"]), "candidate_id_mismatch", "candidate_id does not match the authorization binding")
    _require(str(resolved_candidate.get("slot_id") or "") == str(auth_data["slot_id"]), "slot_id_mismatch", "slot_id does not match the authorization binding")
    try:
        selected_candidate.validate_selected_candidate_issuance(candidate, root=ROOT)
    except selected_candidate.ConsumerError as exc:
        return _build_fail_report(
            auth=auth,
            report_path=report_path,
            started_at=started_at,
            cycle_id=cycle_id,
            stages=stages,
            failed_stage="approved_candidate_resolution",
            error_code=exc.code,
            error_detail=exc.detail,
        )
    stages.append(
        _stage_summary(
            "approved_candidate_resolution",
            True,
            candidate_artifact_path=str(candidate_path),
            candidate_artifact_sha256=candidate_sha256,
            policy_artifact_path=str(live_requirements["policy_path"]),
            policy_artifact_sha256=auth["policy"]["sha256"],
        )
    )

    approval_result = _issue_standing_autonomy_generation_approval(auth, live_requirements)
    _, provider_prompt_source, _, packet_validation = executor._validate_handoff_packet(live_requirements["handoff_path"])
    _require(packet_validation.get("ok") is True, "provider_source_validation_failed", "regenerated provider prompt source failed validation before provider execution")
    context = {
        "date": day,
        "slot_id": str(auth_data["slot_id"]),
        "recipe_id": str(auth["handoff"]["report"].get("selected_recipe_id") or auth_data.get("recipe_id") or ""),
        "handoff_report": auth["handoff"]["report"],
        "approval_result": approval_result,
        "source": provider_prompt_source,
        "claim_path": approval.claim_output_path(day, str(auth_data["slot_id"])),
        "receipt_path": approval.receipt_output_path(day, str(auth_data["slot_id"])),
        "manifest_path": executor.manifest_path(day, str(auth_data["slot_id"])),
        "handoff_artifact": live_requirements["handoff_path"],
        "approval_artifact": auth["path"],
        "custom_reference_id": str(auth_data["custom_reference_id"]),
    }

    try:
        provider_result = executor.execute_approved_handoff_live_generation(context, live_executor=executor.run_live)
    except Exception as exc:
        code = getattr(exc, "code", "provider_generation_failed")
        detail = getattr(exc, "detail", str(exc))
        return _build_fail_report(
            auth=auth,
            report_path=report_path,
            started_at=started_at,
            cycle_id=cycle_id,
            stages=stages,
            failed_stage="provider_generation",
            error_code=code,
            error_detail=detail,
        )

    if not provider_result.get("ok"):
        return _build_fail_report(
            auth=auth,
            report_path=report_path,
            started_at=started_at,
            cycle_id=cycle_id,
            stages=stages,
            failed_stage="provider_generation",
            error_code=str(provider_result.get("failure_stage") or "provider_generation_failed"),
            error_detail=str(provider_result.get("failure_error_text") or "provider generation failed"),
            extra={
                "provider_generation_result": provider_result,
            },
        )

    try:
        validated_provider = _validate_completed_provider_result(
            provider_result,
            live_requirements=live_requirements,
            approval_result=approval_result,
            auth_data=auth_data,
        )
    except LenaBoundedLiveCycleError as exc:
        return _build_fail_report(
            auth=auth,
            report_path=report_path,
            started_at=started_at,
            cycle_id=cycle_id,
            stages=stages,
            failed_stage="provider_generation_validation",
            error_code=exc.code,
            error_detail=exc.detail,
            extra=_provider_failure_evidence(provider_result),
        )
    claim_path = validated_provider["claim_path"]
    receipt_path = validated_provider["receipt_path"]
    manifest_path = validated_provider["manifest_path"]
    live_result = validated_provider["live_result"]
    provider_manifest = validated_provider["provider_manifest"]
    provider_claim = validated_provider["provider_claim"]
    provider_receipt = validated_provider["provider_receipt"]
    generated_image_path = validated_provider["generated_image_path"]
    generated_image_sha256 = validated_provider["generated_image_sha256"]
    provider_calls_performed = 1
    retries_performed = 0
    publish_handoff_path = live_requirements["handoff_path"]
    publish_approval_path = auth["path"]
    publish_approval_sha256 = auth["pre_consumption_sha256"]
    stages.append(
        _stage_summary(
            "provider_generation",
            True,
            provider_generation_claim_path=str(claim_path),
            provider_generation_claim_sha256=_sha256_file(claim_path),
            provider_generation_receipt_path=str(receipt_path),
            provider_generation_receipt_sha256=_sha256_file(receipt_path),
            provider_generation_manifest_path=str(manifest_path),
            provider_generation_manifest_sha256=_sha256_file(manifest_path),
            generated_image_path=str(generated_image_path),
            generated_image_sha256=generated_image_sha256,
            provider_calls_performed=1,
        )
    )

    try:
        identity_evidence_path = identity.identity_verification_evidence_path(day, str(auth_data["slot_id"]))
        identity_evidence_path, identity_evidence, identity_written = _build_local_identity_evidence(
            date_str=day,
            slot_id=str(auth_data["slot_id"]),
            manifest=provider_manifest,
            image_path=generated_image_path,
            image_sha256=generated_image_sha256,
            identity_evidence_path=identity_evidence_path,
        )
        reference_authority_path, reference_authority_sha256, reference_specs = _load_reference_specs()
        qa_artifact = photo_qa.evaluate_photo_qa_disposition(
            decision_path=auth["path"],
            manifest_path=manifest_path,
            image_path=generated_image_path,
            identity_evidence_path=identity_evidence_path,
            reference_specs=reference_specs,
            reference_authority_artifact=reference_authority_path,
            reference_authority_sha256=reference_authority_sha256,
            expected_image_sha256=generated_image_sha256,
            selected_candidate_freshness_mode=selected_candidate.FRESHNESS_MODE_STORED_SNAPSHOT,
            **_controlled_visual_qa_kwargs(auth, candidate, reference_authority_path),
        )
        qa_path, qa_written_artifact, _qa_written = photo_qa.write_disposition_artifact(qa_artifact)
    except Exception as exc:
        return _build_fail_report(
            auth=auth,
            report_path=report_path,
            started_at=started_at,
            cycle_id=cycle_id,
            stages=stages,
            failed_stage="automated_visual_qa",
            error_code=str(getattr(exc, "code", "automated_visual_qa_failed")),
            error_detail=str(getattr(exc, "detail", str(exc))),
            extra={"provider_calls_performed": 1, "retries_performed": 0},
        )
    qa_terminal_state = _qa_terminal_state(qa_written_artifact)
    controlled = _controlled_photo_authority(auth)
    if controlled is not None and qa_written_artifact.get("disposition") != "accept":
        retry_allowed = controlled_autonomous_disposition(qa_written_artifact, retries_performed=0) == "reject_and_retry"
        if retry_allowed:
            _require(int(auth_data.get("provider_call_cap_per_cycle", 0)) == 2, "retry_provider_cap_invalid", "controlled retry requires a two-call provider cap")
            _require(int(auth_data.get("retry_cap_per_cycle", 0)) == 1, "retry_cap_invalid", "controlled retry requires a one-retry cap")
            stages.append(
                _stage_summary(
                    "image_qa",
                    True,
                    disposition="reject_and_retry",
                    qa_artifact_path=str(qa_path),
                    qa_artifact_sha256=_sha256_file(qa_path),
                )
            )
            try:
                retry_preparation = retry_handoff.evaluate_retry_handoff(
                    handoff_artifact=live_requirements["handoff_path"],
                    execution_receipt=receipt_path,
                    write_artifact=True,
                    reason_code="hair_crown_forelock_artifact",
                )
                retry_handoff_path = Path(retry_preparation["retry_handoff_artifact_path"])
                retry_approval_result = _issue_controlled_retry_approval(auth, retry_handoff_path)
                retry_result = executor.execute_approved_retry_live_generation(
                    retry_handoff_path,
                    retry_approval_result["approval_path"],
                    live_executor=executor.run_live,
                )
                retry_facts = retry_approval_result["retry_facts"]
                retry_provider = _validate_completed_retry_provider_result(retry_result, retry_facts=retry_facts)
            except Exception as exc:
                return _build_fail_report(
                    auth=auth,
                    report_path=report_path,
                    started_at=started_at,
                    cycle_id=cycle_id,
                    stages=stages,
                    failed_stage="controlled_retry_execution",
                    error_code=str(getattr(exc, "code", "controlled_retry_failed")),
                    error_detail=str(getattr(exc, "detail", str(exc))),
                    extra={"provider_calls_performed": 2 if "retry_result" in locals() else 1, "retries_performed": 1},
                )
            provider_calls_performed = 2
            retries_performed = 1
            claim_path = retry_provider["claim_path"]
            receipt_path = retry_provider["receipt_path"]
            manifest_path = retry_provider["manifest_path"]
            provider_manifest = retry_provider["provider_manifest"]
            provider_claim = retry_provider["provider_claim"]
            provider_receipt = retry_provider["provider_receipt"]
            generated_image_path = retry_provider["generated_image_path"]
            generated_image_sha256 = retry_provider["generated_image_sha256"]
            publish_handoff_path = retry_handoff_path
            publish_approval_path = retry_approval_result["approval_path"]
            publish_approval_sha256 = retry_approval_result["approval_sha256"]
            identity_evidence_path = identity.identity_verification_evidence_path(day, retry_facts["slot_id"])
            identity_evidence_path, identity_evidence, identity_written = _build_local_identity_evidence(
                date_str=day,
                slot_id=retry_facts["slot_id"],
                manifest=provider_manifest,
                image_path=generated_image_path,
                image_sha256=generated_image_sha256,
                identity_evidence_path=identity_evidence_path,
            )
            qa_artifact = photo_qa.evaluate_photo_qa_disposition(
                decision_path=retry_handoff_path,
                manifest_path=manifest_path,
                image_path=generated_image_path,
                identity_evidence_path=identity_evidence_path,
                reference_specs=reference_specs,
                reference_authority_artifact=reference_authority_path,
                reference_authority_sha256=reference_authority_sha256,
                expected_image_sha256=generated_image_sha256,
                **_controlled_visual_qa_kwargs(
                    auth,
                    candidate,
                    reference_authority_path,
                    decision_fingerprint=retry_facts["retry_handoff_fingerprint_sha256"],
                ),
            )
            qa_path, qa_written_artifact, _qa_written = photo_qa.write_disposition_artifact(qa_artifact)
            qa_terminal_state = _qa_terminal_state(qa_written_artifact)
            stages.append(
                _stage_summary(
                    "controlled_retry",
                    True,
                    retry_handoff_path=str(retry_handoff_path),
                    retry_handoff_sha256=_sha256_file(retry_handoff_path),
                    retry_approval_path=str(retry_approval_result["approval_path"]),
                    retry_approval_sha256=retry_approval_result["approval_sha256"],
                    retry_claim_path=str(claim_path),
                    retry_receipt_path=str(receipt_path),
                    retry_manifest_path=str(manifest_path),
                    retry_image_path=str(generated_image_path),
                    retry_image_sha256=generated_image_sha256,
                )
            )
        if not retry_allowed or qa_written_artifact.get("disposition") != "accept":
            disposition = controlled_autonomous_disposition(qa_written_artifact, retries_performed=retries_performed)
            finished_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
            report = {
                "ok": disposition != "operational_failure",
                "version": "v2",
                "report_type": "lena_bounded_live_cycle",
                "live_execution": True,
                "autonomous_execution": True,
                "controlled_photo_autonomy": True,
                "date": day,
                "started_at": started_at,
                "finished_at": finished_at,
                "autonomous_disposition": disposition,
                "qa_lifecycle_status": str(qa_written_artifact.get("disposition") or "blocked"),
                "provider_calls_performed": provider_calls_performed,
                "publish_calls_performed": 0,
                "retries_performed": retries_performed,
                "publish_authorized": False,
                "publish_performed": False,
                "queue_mutated": False,
                "retry_executed": retries_performed == 1,
                "human_review_required": False,
                "exceptional_escalation_required": True,
                "qa_artifact": qa_written_artifact,
                "qa_artifact_path": str(qa_path),
                "qa_artifact_sha256": _sha256_file(qa_path),
                "stage_coverage": stages,
                "stages": stages,
            }
            _write_json_atomic(report_path, report)
            report["report_path"] = str(report_path)
            return report
    if qa_terminal_state == "awaiting_human_visual_review":
        finished_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
        report = {
            "ok": True,
            "version": "v1",
            "report_type": "lena_bounded_live_cycle",
            "live_execution": True,
            "simulation_mode": False,
            "autonomous_execution": True,
            "date": day,
            "started_at": started_at,
            "finished_at": finished_at,
            "authorization_artifact_path": str(auth["path"]),
            "authorization_artifact_sha256_before_consumption": auth["pre_consumption_sha256"],
            "authorization_artifact_sha256": auth["sha256"],
            "authorization_consumption_implemented": True,
            "authorization_consumed": True,
            "authorization_consumed_at_utc": auth["consumed_at_utc"],
            "provider_calls_performed": 1,
            "publish_calls_performed": 0,
            "retries_performed": 0,
            "qa_lifecycle_status": "awaiting_human_visual_review",
            "next_allowed_action": "human_visual_review_required",
            "publish_authorized": False,
            "publish_performed": False,
            "queue_mutated": False,
            "retry_executed": False,
            "child_artifacts": {
                "authorization_artifact": {"path": str(auth["path"]), "sha256": auth["pre_consumption_sha256"]},
                "candidate_artifact": {"path": str(candidate_path), "sha256": candidate_sha256},
                "provider_generation_claim": {"path": str(claim_path), "sha256": _sha256_file(claim_path)},
                "provider_generation_receipt": {"path": str(receipt_path), "sha256": _sha256_file(receipt_path)},
                "provider_generation_manifest": {"path": str(manifest_path), "sha256": _sha256_file(manifest_path)},
                "generated_asset": {"path": str(generated_image_path), "sha256": generated_image_sha256},
                "identity_evidence": {"path": str(identity_evidence_path), "sha256": _sha256_file(identity_evidence_path)},
                "qa_artifact": {"path": str(qa_path), "sha256": _sha256_file(qa_path)},
            },
            "qa_artifact": qa_written_artifact,
            "stage_coverage": stages,
            "stages": stages,
        }
        _write_json_atomic(report_path, report)
        report["report_path"] = str(report_path)
        return report
    _require(qa_terminal_state == "accepted", "qa_rejected", "photo QA did not accept the generated image")
    _require(str(qa_written_artifact.get("overall") or "pass") in {"pass", "approved"}, "qa_overall_invalid", "photo QA artifact did not pass overall")
    stages.append(
        _stage_summary(
            "image_qa",
            True,
            qa_artifact_path=str(qa_path),
            qa_artifact_sha256=_sha256_file(qa_path),
            identity_evidence_path=str(identity_evidence_path),
            identity_evidence_sha256=_sha256_file(identity_evidence_path),
        )
    )

    if controlled is not None:
        handoff_report = auth["handoff"]["report"]
        packet_sha = str(
            handoff_report.get("selected_prompt_input_artifact_sha256")
            or handoff_report.get("structured_executor_inputs", {}).get("selected_prompt_input_artifact_sha256")
            or ""
        )
        lineage = {
            "candidate_artifact_sha256": candidate_sha256,
            "prompt_sha256": str(provider_manifest["prompt_sha256"]),
            "packet_sha256": packet_sha,
            "handoff_sha256": _sha256_file(publish_handoff_path),
            "approval_sha256": publish_approval_sha256,
            "execution_receipt_sha256": _sha256_file(receipt_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "qa_sha256": _sha256_file(qa_path),
        }
        clean_dir = _ensure_path_within_root(
            report_root / day / str(auth_data["slot_id"]),
            report_root,
            code="clean_export_path_escape",
            label="privacy-clean export directory",
            must_exist=False,
        )
        clean_path = clean_dir / f"{auth_data['slot_id']}_publish_clean{generated_image_path.suffix.lower()}"
        clean_report_path = clean_dir / f"{auth_data['slot_id']}_publish_clean_provenance.json"
        clean_export = clean_photo.prepare_privacy_clean_photo(
            generated_image_path,
            clean_path,
            clean_report_path,
            source_image_sha256=generated_image_sha256,
            lineage=lineage,
        )
        publish_policy_result = autonomous_publisher._validate_policy_artifact(autonomous_publisher.POLICY_PATH)
        publish_sidecar_path, publish_sidecar, publish_sidecar_sha256 = _build_live_publish_sidecar(
            authorization=auth,
            image_path=clean_path,
            caption=str(auth_data["caption"]),
            platform=str(auth_data["platform"]),
            controlled_lineage=lineage,
            clean_export_report=clean_export,
            publish_policy_result=publish_policy_result,
        )
        admission = autonomous_publisher.admit_controlled_photo(
            day=day,
            slot_id=str(auth_data["slot_id"]),
            schedule_slot=str(auth_data["schedule_slot"]),
            platform=str(auth_data["platform"]),
            lane=str(resolved_candidate.get("lane") or ""),
            asset_path=clean_path,
            asset_sha256=str(clean_export["output_sha256"]),
            caption=str(auth_data["caption"]),
            lineage=lineage,
            clean_export_report_path=clean_report_path,
            clean_export_report_sha256=str(clean_export["report_sha256"]),
            policy_path=autonomous_publisher.POLICY_PATH,
        )
        stages.append(
            _stage_summary(
                "autonomous_queue_admission",
                True,
                queue_path=admission["queue_path"],
                queue_id=admission["queue_id"],
                clean_export_path=str(clean_path),
                clean_export_sha256=clean_export["output_sha256"],
                clean_export_report_path=str(clean_report_path),
                clean_export_report_sha256=clean_export["report_sha256"],
            )
        )
        if hold_for_publish:
            publish_result = None
            publish_performed = False
            publish_calls_performed = 0
            autonomous_disposition = "accept_and_hold_for_publish"
            stages.append(
                _stage_summary(
                    "scheduled_publish",
                    True,
                    held_for_publish=True,
                    schedule_slot=str(auth_data["schedule_slot"]),
                )
            )
        else:
            publish_result = autonomous_publisher.run_scheduled_autonomous(
                day=day,
                slot_keyword=str(auth_data["schedule_slot"]),
                limit=1,
                dry_run=False,
                policy_path=autonomous_publisher.POLICY_PATH,
            )
            _require(int(publish_result.get("posted_count", 0)) == 1, "autonomous_publish_not_completed", "scheduled autonomous publisher did not record exactly one posted item")
            _require(int(publish_result.get("publish_calls_performed", 0)) == 1, "autonomous_publish_count_invalid", "scheduled autonomous publisher must perform exactly one publish call")
            stages.append(_stage_summary("scheduled_publish", True, publish_report=publish_result))
            publish_performed = True
            publish_calls_performed = 1
            autonomous_disposition = "accept_and_publish"
        finished_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
        report = {
            "ok": True,
            "version": "v2",
            "report_type": "lena_bounded_live_cycle",
            "live_execution": True,
            "autonomous_execution": True,
            "controlled_photo_autonomy": True,
            "human_per_cycle_approval_required": False,
            "human_per_cycle_approval_present": False,
            "human_review_required": False,
            "date": day,
            "started_at": started_at,
            "finished_at": finished_at,
            "cycle_id": cycle_id,
            "autonomous_disposition": autonomous_disposition,
            "provider_calls_performed": provider_calls_performed,
            "publish_calls_performed": publish_calls_performed,
            "retries_performed": retries_performed,
            "qa_lifecycle_status": "accepted",
            "publish_authorized": True,
            "publish_performed": publish_performed,
            "queue_mutated": True,
            "retry_executed": retries_performed == 1,
            "provider_original": {"path": str(generated_image_path), "sha256": generated_image_sha256},
            "privacy_clean_derivative": {"path": str(clean_path), "sha256": clean_export["output_sha256"]},
            "clean_export_report": {"path": str(clean_report_path), "sha256": clean_export["report_sha256"]},
            "publish_sidecar": {"path": str(publish_sidecar_path), "sha256": publish_sidecar_sha256},
            "queue_admission": admission,
            "publish_result": publish_result,
            "qa_artifact": qa_written_artifact,
            "qa_artifact_path": str(qa_path),
            "qa_artifact_sha256": _sha256_file(qa_path),
            "lineage": lineage,
            "generation_handoff": {"path": str(publish_handoff_path), "sha256": _sha256_file(publish_handoff_path)},
            "generation_approval": {"path": str(publish_approval_path), "sha256": publish_approval_sha256},
            "child_artifacts": {
                "authorization_artifact": {"path": str(auth["path"]), "sha256": auth["pre_consumption_sha256"]},
                "candidate_artifact": {"path": str(candidate_path), "sha256": candidate_sha256},
                "provider_generation_claim": {"path": str(claim_path), "sha256": _sha256_file(claim_path)},
                "provider_generation_receipt": {"path": str(receipt_path), "sha256": _sha256_file(receipt_path)},
                "provider_generation_manifest": {"path": str(manifest_path), "sha256": _sha256_file(manifest_path)},
                "provider_original": {"path": str(generated_image_path), "sha256": generated_image_sha256},
                "identity_evidence": {"path": str(identity_evidence_path), "sha256": _sha256_file(identity_evidence_path)},
                "qa_artifact": {"path": str(qa_path), "sha256": _sha256_file(qa_path)},
                "privacy_clean_derivative": {"path": str(clean_path), "sha256": clean_export["output_sha256"]},
                "clean_export_report": {"path": str(clean_report_path), "sha256": clean_export["report_sha256"]},
                "generation_handoff": {"path": str(publish_handoff_path), "sha256": _sha256_file(publish_handoff_path)},
                "generation_approval": {"path": str(publish_approval_path), "sha256": publish_approval_sha256},
                "publish_sidecar": {"path": str(publish_sidecar_path), "sha256": publish_sidecar_sha256},
            },
            "stage_coverage": stages,
            "stages": stages,
        }
        _write_json_atomic(report_path, report)
        report["report_path"] = str(report_path)
        return report

    publish_sidecar_path, publish_sidecar, publish_sidecar_sha256 = _build_live_publish_sidecar(
        authorization=auth,
        image_path=generated_image_path,
        caption=str(auth_data["caption"]),
        platform=str(auth_data["platform"]),
    )
    package_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "package", report_root),
        report_root,
        code="package_path_escape",
        label="package artifact",
        must_exist=False,
    )
    package_path, package = _build_live_package(
        auth=auth,
        approval_result=approval_result,
        provider_result={
            "live_result": live_result,
            "manifest": provider_manifest,
            "manifest_path": manifest_path,
            "manifest_sha256": _sha256_file(manifest_path),
            "generated_image_sha256": generated_image_sha256,
        },
        qa_result={"path": qa_path, "sha256": _sha256_file(qa_path), "artifact": qa_written_artifact},
        package_path=package_path,
        publish_sidecar_path=publish_sidecar_path,
        publish_sidecar_sha256=publish_sidecar_sha256,
    )
    package_sha256 = _sha256_file(package_path)
    stages.append(
        _stage_summary(
            "caption_package_creation",
            True,
            package_artifact_path=str(package_path),
            package_artifact_sha256=package_sha256,
        )
    )

    publish_payload_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "publish_payload", report_root),
        report_root,
        code="publish_payload_path_escape",
        label="publish payload artifact",
        must_exist=False,
    )
    publish_payload = {
        "report_type": "lena_bounded_live_cycle_publish_payload",
        "schema_version": "v1",
        "cycle_id": cycle_id,
        "authorization_mode": "standing_autonomy_policy",
        "platform": str(auth_data["platform"]),
        "media_type": "photo",
        "slot_id": str(auth_data["slot_id"]),
        "candidate_id": str(auth_data["candidate_id"]),
        "caption": str(auth_data["caption"]),
        "asset_path": str(generated_image_path),
        "asset_sha256": generated_image_sha256,
        "generated_image_path": str(generated_image_path),
        "generated_image_sha256": generated_image_sha256,
        "package_artifact_path": str(package_path),
        "package_artifact_sha256": package_sha256,
        "publish_sidecar_path": str(publish_sidecar_path),
        "publish_sidecar_sha256": publish_sidecar_sha256,
        "policy_artifact_path": str(auth_data.get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(auth_data.get("policy_artifact_sha256") or ""),
        "cycle_authorization_path": str(auth["path"]),
        "cycle_authorization_sha256": auth["pre_consumption_sha256"],
    }
    _write_json_atomic(publish_payload_path, publish_payload)
    publish_payload_sha256 = _sha256_file(publish_payload_path)
    publisher_result = _run_publisher(platform=str(auth_data["platform"]), payload_path=publish_payload_path)
    publish_receipt_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "publish_receipt", report_root),
        report_root,
        code="publish_receipt_path_escape",
        label="publish receipt artifact",
        must_exist=False,
    )
    publish_receipt_path, publish_receipt = _build_live_publish_receipt(
        auth=auth,
        package_path=package_path,
        package_sha256=package_sha256,
        publish_sidecar_path=publish_sidecar_path,
        publish_sidecar_sha256=publish_sidecar_sha256,
        publisher_result={**publisher_result, "payload_path": publish_payload_path, "payload_sha256": publish_payload_sha256},
        publish_receipt_path=publish_receipt_path,
    )
    stages.append(
        _stage_summary(
            "publish_action",
            True,
            publish_receipt_artifact_path=str(publish_receipt_path),
            publish_receipt_artifact_sha256=_sha256_file(publish_receipt_path),
            publish_payload_path=str(publish_payload_path),
            publish_payload_sha256=publish_payload_sha256,
            remote_post_id=publish_receipt.get("remote_post_id"),
        )
    )

    analytics_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "analytics_handoff", report_root),
        report_root,
        code="analytics_path_escape",
        label="analytics handoff artifact",
        must_exist=False,
    )
    analytics_path, analytics = _build_live_analytics_handoff(
        auth=auth,
        package_path=package_path,
        package_sha256=package_sha256,
        publish_receipt_path=publish_receipt_path,
        publish_receipt_sha256=_sha256_file(publish_receipt_path),
        analytics_handoff_path=analytics_path,
    )
    stages.append(
        _stage_summary(
            "analytics_handoff",
            True,
            analytics_handoff_artifact_path=str(analytics_path),
            analytics_handoff_artifact_sha256=_sha256_file(analytics_path),
        )
    )

    finished_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    usage_before = auth_data.get("daily_usage_before") or {}
    usage_after = {
        "cycle_count": int(usage_before.get("cycle_count", 0)) + 1,
        "provider_calls_performed": int(usage_before.get("provider_calls_performed", 0)) + 1,
        "publish_calls_performed": int(usage_before.get("publish_calls_performed", 0)) + 1,
        "retries_performed": int(usage_before.get("retries_performed", 0)),
        "declared_spend_total": usage_before.get("declared_spend_total"),
        "spend_unit": usage_before.get("spend_unit"),
    }
    report = {
        "ok": True,
        "version": "v1",
        "report_type": "lena_bounded_live_cycle",
        "live_execution": True,
        "simulation_mode": False,
        "autonomous_execution": True,
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
        "authorization_mode": "standing_autonomy_policy",
        "date": day,
        "started_at": started_at,
        "finished_at": finished_at,
        "cycle_id": cycle_id,
        "policy_artifact_path": str(auth_data.get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(auth_data.get("policy_artifact_sha256") or ""),
        "authorization_artifact_path": str(auth["path"]),
        "authorization_artifact_sha256_before_consumption": auth["pre_consumption_sha256"],
        "authorization_artifact_sha256": auth["sha256"],
        "authorization_consumption_implemented": True,
        "authorization_consumed": True,
        "authorization_consumed_at_utc": auth["consumed_at_utc"],
        "authorization_state_before": {
            "single_use": True,
            "consumed": False,
            "consumed_at_utc": None,
        },
        "authorization_state_after": auth["artifact"].get("authorization_state_after", {
            "single_use": True,
            "consumed": True,
            "consumed_at_utc": auth["consumed_at_utc"],
        }),
        "provider_calls_performed": 1,
        "publish_calls_performed": 1,
        "retries_performed": 0,
        "declared_spend_unit": auth_data.get("spend_unit"),
        "actual_spend": auth_data.get("actual_spend"),
        "actual_spend_available": bool(auth_data.get("actual_spend") not in (None, "")),
        "daily_usage_before": usage_before,
        "daily_usage_after": usage_after,
        "safeguards": {
            "single_use": True,
            "one_slot": True,
            "one_candidate": True,
            "one_asset": True,
            "one_platform": True,
            "provider_call_cap_per_cycle": 1,
            "publish_action_cap_per_cycle": 1,
            "retry_cap_per_cycle": 0,
            "daily_spend_ceiling": auth_data.get("daily_spend_ceiling"),
            "spend_unit": auth_data.get("spend_unit"),
            "kill_switch_enabled": auth_data.get("kill_switch_enabled"),
            "duplicate_rejection": "report_path_must_not_exist",
            "no_scheduler": True,
            "no_second_provider_call": True,
            "no_second_publish_call": True,
            "analytics_triggered_rerun_blocked": True,
            "qa_required": True,
            "identity_verification_required": True,
        },
        "authorized_scope": {
            "slot_id": str(auth_data["slot_id"]),
            "candidate_id": str(auth_data["candidate_id"]),
            "platform": str(auth_data["platform"]),
            "asset_path": str(generated_image_path),
        },
        "child_artifacts": {
            "policy_artifact": {"path": str(live_requirements["policy_path"]), "sha256": auth["policy"]["sha256"]},
            "authorization_artifact": {"path": str(auth["path"]), "sha256": auth["pre_consumption_sha256"]},
            "handoff_artifact": {"path": str(live_requirements["handoff_path"]), "sha256": _sha256_file(live_requirements["handoff_path"])},
            "candidate_artifact": {"path": str(candidate_path), "sha256": candidate_sha256},
            "provider_generation_claim": {"path": str(claim_path), "sha256": _sha256_file(claim_path)},
            "provider_generation_receipt": {"path": str(receipt_path), "sha256": _sha256_file(receipt_path)},
            "provider_generation_manifest": {"path": str(manifest_path), "sha256": _sha256_file(manifest_path)},
            "generated_asset": {"path": str(generated_image_path), "sha256": generated_image_sha256},
            "identity_evidence": {"path": str(identity_evidence_path), "sha256": _sha256_file(identity_evidence_path)},
            "qa_artifact": {"path": str(qa_path), "sha256": _sha256_file(qa_path)},
            "publish_sidecar": {"path": str(publish_sidecar_path), "sha256": publish_sidecar_sha256},
            "publish_payload": {"path": str(publish_payload_path), "sha256": publish_payload_sha256},
            "package_artifact": {"path": str(package_path), "sha256": package_sha256},
            "publish_receipt_artifact": {"path": str(publish_receipt_path), "sha256": _sha256_file(publish_receipt_path)},
            "analytics_handoff_artifact": {"path": str(analytics_path), "sha256": _sha256_file(analytics_path)},
        },
        "provider_receipt": provider_receipt,
        "qa_artifact": qa_written_artifact,
        "package_artifact": package,
        "publish_receipt": publish_receipt,
        "analytics_handoff": analytics,
        "stage_coverage": stages,
        "stages": stages,
        "audited_live_paths": {
            "provider_generation": "pipeline.higgsfield_lena_api_executor.execute_approved_handoff_live_generation",
            "image_qa": "tools.lena_photo_qa_disposition_v1.evaluate_photo_qa_disposition",
            "caption_package_creation": "bounded live package builder",
            "publishing": "tools/publishers/lena_publish_instagram_feed_v2_8.py or tools/publishers/lena_publish_facebook_page_v2_8.py",
            "analytics": "bounded live analytics handoff artifact",
        },
    }
    _write_json_atomic(report_path, report)
    report["report_path"] = str(report_path)
    return report


def run_cycle(auth_artifact: Path, *, simulate: bool = True, report_root: Path = REPORT_ROOT) -> dict[str, Any]:
    if not simulate:
        return _run_live_cycle(auth_artifact, report_root=report_root)
    auth = _validate_authorization_artifact(auth_artifact, simulate=True)
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
    resolved_candidate = _resolve_candidate_artifact(candidate_artifact)
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
    manifest_saved_image = _ensure_path_within_root(
        Path(str(manifest["artifact"].get("saved_image_path") or "")),
        ROOT / "pipeline" / "higgsfield_library" / "lena",
        code="manifest_image_path_invalid",
        label="manifest saved image",
        must_exist=True,
    )
    image = manifest_saved_image
    image_sha = _sha256_file(image)
    _require(manifest_saved_image == image, "manifest_image_mismatch", "manifest saved image does not match authorization output binding")
    stages.append(_stage_summary(
        "provider_generation_evidence",
        True,
        provider_generation_receipt_path=str(provider["path"]),
        provider_generation_receipt_sha256=provider["sha256"],
        manifest_path=str(manifest["path"]),
        manifest_sha256=manifest["sha256"],
        generated_image_path=str(image),
        generated_image_sha256=image_sha,
        provider_calls_performed=0,
    ))
    qa = _validate_bound_artifact(
        str(auth_data["qa_artifact_path"]),
        str(auth_data["qa_artifact_sha256"]),
        root=ROOT / "pipeline" / "asset_review" / "lena" / "presence_output_qa",
        code="qa_binding_invalid",
        label="QA artifact",
    )
    qa_artifact = qa["artifact"]
    qa_terminal_state = _qa_terminal_state(qa_artifact)
    _require(
        qa_terminal_state in {"accepted", "awaiting_human_visual_review"},
        "qa_failure",
        "QA artifact indicates failure",
    )
    stages.append(_stage_summary("image_qa", True, qa_artifact_path=str(qa["path"]), qa_artifact_sha256=qa["sha256"]))
    package_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "package", report_root),
        report_root,
        code="package_path_escape",
        label="package artifact",
        must_exist=False,
    )
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_path, package = _build_package(
        auth,
        provider,
        qa,
        package_path,
        generated_image_path=image,
        generated_image_sha256=image_sha,
    )
    package_sha = _sha256_file(package_path)
    stages.append(_stage_summary("caption_package_creation", True, package_artifact_path=str(package_path), package_artifact_sha256=package_sha))
    publish_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "publish_receipt", report_root),
        report_root,
        code="publish_path_escape",
        label="publish receipt artifact",
        must_exist=False,
    )
    publish_path, publish = _build_publish_receipt(auth, package, publish_path)
    publish_sha = _sha256_file(publish_path)
    stages.append(_stage_summary("publish_receipt", True, publish_receipt_artifact_path=str(publish_path), publish_receipt_artifact_sha256=publish_sha))
    analytics_path = _ensure_path_within_root(
        _subreport_path(day, str(auth_data["slot_id"]), "analytics_handoff", report_root),
        report_root,
        code="analytics_path_escape",
        label="analytics handoff artifact",
        must_exist=False,
    )
    analytics_path, analytics = _build_analytics_handoff(auth, package, {"path": publish_path, "sha256": publish_sha, "artifact": publish}, analytics_path)
    analytics_sha = _sha256_file(analytics_path)
    stages.append(_stage_summary("analytics_handoff", True, analytics_handoff_artifact_path=str(analytics_path), analytics_handoff_artifact_sha256=analytics_sha))
    finished_at = _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report: dict[str, Any] = {
        "ok": True,
        "version": "v1",
        "report_type": "lena_bounded_live_cycle",
        "simulation_mode": simulate,
        "live_execution": False,
        "autonomous_execution": False,
        "authorization_mode": "standing_autonomy_policy",
        "date": day,
        "started_at": started_at,
        "finished_at": finished_at,
        "policy_artifact_path": str(auth_data.get("policy_artifact_path") or ""),
        "policy_artifact_sha256": str(auth_data.get("policy_artifact_sha256") or ""),
        "authorization_artifact_path": str(auth["path"]),
        "authorization_artifact_sha256_before_consumption": auth.get("pre_consumption_sha256", auth["sha256"]),
        "authorization_artifact_sha256": auth["sha256"],
        "authorization_consumption_implemented": False,
        "authorization_consumed": False,
        "authorization_consumed_at_utc": None,
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
        "authorization_state_before": {
            "single_use": True,
            "consumed": False,
            "consumed_at_utc": None,
        },
        "authorization_state_after": {
            "single_use": True,
            "consumed": False,
            "consumed_at_utc": None,
        },
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "declared_spend_unit": auth_data.get("spend_unit"),
        "actual_spend": None,
        "actual_spend_available": False,
        "daily_usage_before": auth_data.get("daily_usage_before"),
        "daily_usage_after": auth_data.get("daily_usage_before"),
        "safeguards": {
            "single_use": True,
            "one_slot": True,
            "one_candidate": True,
            "one_asset": True,
            "one_platform": True,
            "provider_call_cap_per_cycle": 1,
            "publish_action_cap_per_cycle": 1,
            "retry_cap_per_cycle": 0,
            "daily_spend_ceiling": auth_data.get("daily_spend_ceiling"),
            "spend_unit": auth_data.get("spend_unit"),
            "kill_switch_enabled": auth_data.get("kill_switch_enabled"),
            "duplicate_rejection": "report_path_must_not_exist",
            "no_scheduler": True,
            "no_second_provider_call": True,
            "no_second_publish_call": True,
            "analytics_triggered_rerun_blocked": True,
            "qa_required": True,
            "identity_verification_required": True,
        },
        "unimplemented_live_guards": [
            "atomic_authorization_consumption",
            "provider_execution",
            "publisher_execution",
        ],
        "authorized_scope": {
            "slot_id": auth_data["slot_id"],
            "candidate_id": auth_data["candidate_id"],
            "generated_image_path": str(image),
            "platform": auth_data["platform"],
        },
        "captions": {
            "caption": auth_data["caption"],
        },
        "child_artifacts": {
            "policy_artifact": {"path": str(auth_data.get("policy_artifact_path") or ""), "sha256": str(auth_data.get("policy_artifact_sha256") or "")},
            "authorization_artifact": {"path": str(auth["path"]), "sha256": auth["pre_consumption_sha256"]},
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
            "provider_generation": "pipeline/higgsfield_lena_api_executor.execute_approved_handoff_live_generation",
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
