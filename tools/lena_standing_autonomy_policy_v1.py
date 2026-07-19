from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools import lena_higgsfield_generation_approval_v1 as approval
from tools.strategy.lena_build_next_live_image_handoff_v1 import _handoff_cross_field_binding_split_brain_error

ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "pipeline" / "config"
AUTH_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "bounded_live_cycles"
REPORT_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "bounded_live_cycles"

POLICY_REPORT_TYPE = "lena_standing_autonomy_policy"
POLICY_SCHEMA_VERSION = "v1"
AUTH_REPORT_TYPE = "lena_standing_autonomy_cycle_authorization"
AUTH_SCHEMA_VERSION = "v1"
AUTHORIZATION_MODE = "standing_autonomy_policy"
AUTHORIZATION_ISSUER = "lena_autonomy_controller"
AUTHORIZATION_TTL = timedelta(minutes=30)


class StandingAutonomyPolicyError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_json_without_keys(path: Path, excluded_keys: set[str]) -> str:
    payload = _read_json_object(path, code="canonical_hash_invalid", label="canonical hash artifact")
    for key in excluded_keys:
        payload.pop(key, None)
    data = (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    return _sha256_bytes(data)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise StandingAutonomyPolicyError(code, detail)


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise StandingAutonomyPolicyError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StandingAutonomyPolicyError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StandingAutonomyPolicyError(code, f"{label} must be a JSON object: {path}")
    return value


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
        raise StandingAutonomyPolicyError(code, f"resolved {label} escapes declared root: {resolved} (root: {root_resolved})")
    if must_exist and not resolved.exists():
        raise StandingAutonomyPolicyError(code, f"{label} does not exist: {resolved}")
    return resolved


def _validate_iso_datetime(raw: str, *, code: str, label: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StandingAutonomyPolicyError(code, f"{label} must be ISO-8601: {raw!r}") from exc
    if dt.tzinfo is None:
        raise StandingAutonomyPolicyError(code, f"{label} must include timezone information")
    return dt.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _authorized_output_paths(
    expected_output_directory: Path,
    expected_output_stem: str,
    allowed_output_extensions: list[str] | tuple[str, ...],
) -> list[Path]:
    output_root = ROOT / "pipeline" / "higgsfield_library" / "lena"
    directory = _ensure_path_within_root(
        expected_output_directory,
        output_root,
        code="expected_output_directory_escape",
        label="expected output directory",
        must_exist=False,
    )
    _require(bool(expected_output_stem.strip()), "expected_output_stem_missing", "expected_output_stem is required")
    _require(
        isinstance(allowed_output_extensions, (list, tuple)) and len(allowed_output_extensions) > 0 and all(str(item).strip().startswith(".") for item in allowed_output_extensions),
        "allowed_output_extensions_invalid",
        "allowed_output_extensions must be a non-empty list of file extensions",
    )
    paths = [directory / f"{expected_output_stem}{str(extension)}" for extension in allowed_output_extensions]
    for path in paths:
        _ensure_path_within_root(
            path,
            output_root,
            code="expected_output_path_escape",
            label="expected output path",
            must_exist=False,
        )
    return paths


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _normalized_repo_path_text(raw_path: str) -> str:
    return str(raw_path).replace("\\", "/").strip()


def _path_from_repo_text(raw_path: str) -> Path:
    path = Path(_normalized_repo_path_text(raw_path))
    return path if path.is_absolute() else ROOT / path


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise StandingAutonomyPolicyError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def default_policy_path() -> Path:
    return POLICY_ROOT / "lena_standing_autonomy_policy_v1.json"


def default_auth_path(date_str: str, slot_id: str) -> Path:
    return AUTH_ROOT / date_str / f"lena_bounded_live_cycle_authorization_{date_str}_{slot_id}.json"


def default_daily_report_root() -> Path:
    return REPORT_ROOT


def validate_policy_artifact(policy_path: Path) -> dict[str, Any]:
    policy_path = _ensure_path_within_root(
        policy_path,
        POLICY_ROOT,
        code="policy_path_escape",
        label="standing autonomy policy artifact",
        must_exist=True,
    )
    policy = _read_json_object(policy_path, code="policy_missing_or_invalid", label="standing autonomy policy artifact")
    _require(policy.get("report_type") == POLICY_REPORT_TYPE, "policy_report_type_mismatch", f"policy report_type must be {POLICY_REPORT_TYPE!r}")
    _require(policy.get("schema_version") == POLICY_SCHEMA_VERSION, "policy_schema_mismatch", f"policy schema_version must be {POLICY_SCHEMA_VERSION!r}")
    _require(str(policy.get("policy_id") or "").strip(), "policy_id_missing", "policy policy_id is required")
    _require(str(policy.get("policy_version") or "").strip(), "policy_version_missing", "policy policy_version is required")
    _require(policy.get("autonomy_enabled") is True, "policy_autonomy_disabled", "autonomy must be enabled")
    _require(policy.get("live_generation_enabled") is True, "policy_live_generation_disabled", "live generation must be enabled")
    _require(policy.get("live_publishing_enabled") is True, "policy_live_publishing_disabled", "live publishing must be enabled")
    _require(policy.get("kill_switch_enabled") is True, "policy_kill_switch_disabled", "kill switch must be enabled")
    _require(policy.get("allowed_provider") == "Higgsfield", "policy_provider_mismatch", "allowed_provider must be Higgsfield")
    _require(policy.get("allowed_model") == "text2image_soul_v2", "policy_model_mismatch", "allowed_model must be text2image_soul_v2")
    _require(policy.get("allowed_soul") == "Lena", "policy_soul_mismatch", "allowed_soul must be Lena")
    allowed_platforms = policy.get("allowed_platforms")
    _require(isinstance(allowed_platforms, list) and {"Instagram Feed", "Facebook Page"}.issubset(set(map(str, allowed_platforms))), "policy_platforms_invalid", "allowed_platforms must include Instagram Feed and Facebook Page")
    _require(int(policy.get("provider_call_cap_per_cycle", 0)) == 1, "policy_provider_call_cap_invalid", "provider_call_cap_per_cycle must be 1")
    _require(int(policy.get("publish_action_cap_per_cycle", 0)) == 1, "policy_publish_action_cap_invalid", "publish_action_cap_per_cycle must be 1")
    _require(int(policy.get("retry_cap_per_cycle", -1)) == 0, "policy_retry_cap_invalid", "retry_cap_per_cycle must be 0")
    _require(int(policy.get("maximum_cycles_per_day", 0)) > 0, "policy_maximum_cycles_per_day_invalid", "maximum_cycles_per_day must be positive")
    _require(int(policy.get("maximum_provider_calls_per_day", 0)) > 0, "policy_maximum_provider_calls_per_day_invalid", "maximum_provider_calls_per_day must be positive")
    _require(int(policy.get("maximum_publish_actions_per_day", 0)) > 0, "policy_maximum_publish_actions_per_day_invalid", "maximum_publish_actions_per_day must be positive")
    _require(float(policy.get("daily_spend_ceiling", 0)) > 0, "policy_daily_spend_ceiling_invalid", "daily_spend_ceiling must be positive")
    _require(str(policy.get("spend_unit") or "").strip(), "policy_spend_unit_missing", "spend_unit is required")
    allowed_media_types = policy.get("allowed_media_types")
    _require(isinstance(allowed_media_types, list) and "photo" in {str(item) for item in allowed_media_types}, "policy_media_types_invalid", "allowed_media_types must include photo")
    _require(policy.get("duplicate_content_rejection_enabled") is True, "policy_duplicate_rejection_disabled", "duplicate_content_rejection_enabled must be true")
    _require(policy.get("qa_required") is True, "policy_qa_required_invalid", "qa_required must be true")
    _require(policy.get("identity_verification_required") is True, "policy_identity_required_invalid", "identity_verification_required must be true")
    _require(policy.get("analytics_triggered_regeneration_disabled") is True, "policy_analytics_regeneration_invalid", "analytics_triggered_regeneration_disabled must be true")
    current_utc = _now_utc()
    effective_at = _validate_iso_datetime(str(policy.get("effective_at_utc") or ""), code="policy_effective_at_invalid", label="effective_at_utc")
    _require(effective_at <= current_utc, "policy_effective_at_future_invalid", "effective_at_utc must not be in the future")
    expires_raw = policy.get("expires_at_utc")
    expires_at = None
    if expires_raw not in (None, ""):
        expires_at = _validate_iso_datetime(str(expires_raw), code="policy_expires_at_invalid", label="expires_at_utc")
        _require(expires_at > current_utc, "policy_expired", "expires_at_utc must be after current UTC time")
        _require(expires_at > effective_at, "policy_expiry_order_invalid", "expires_at_utc must be after effective_at_utc")
    return {
        "path": policy_path.resolve(),
        "sha256": _sha256_file(policy_path),
        "artifact": policy,
        "effective_at_utc": effective_at.isoformat(),
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
    }


def _cycle_authorization_expires_at(policy_result: dict[str, Any]) -> str:
    current_utc = _now_utc().replace(microsecond=0)
    expiry = current_utc + AUTHORIZATION_TTL
    policy_expiry = policy_result.get("expires_at_utc")
    if policy_expiry:
        policy_expiry_dt = _validate_iso_datetime(str(policy_expiry), code="policy_expires_at_invalid", label="expires_at_utc")
        expiry = min(expiry, policy_expiry_dt)
    return expiry.isoformat().replace("+00:00", "Z")


def collect_daily_usage(report_root: Path, day: str) -> dict[str, Any]:
    root = _ensure_path_within_root(report_root, REPORT_ROOT, code="report_root_escape", label="bounded live report root", must_exist=True)
    day_root = root / day
    usage = {
        "cycle_count": 0,
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retries_performed": 0,
        "declared_spend_total": 0.0,
        "spend_unit": None,
        "files": [],
    }
    if not day_root.exists():
        return usage
    for path in sorted(day_root.rglob("*.json")):
        artifact = _read_json_object(path, code="daily_accounting_artifact_invalid", label="daily accounting artifact")
        if artifact.get("report_type") != "lena_bounded_live_cycle":
            continue
        if str(artifact.get("date") or "") != day:
            raise StandingAutonomyPolicyError("daily_accounting_date_mismatch", f"daily accounting artifact date mismatch: {path}")
        if artifact.get("live_execution") is not True and artifact.get("simulation_mode") is True:
            continue
        usage["cycle_count"] += 1
        usage["provider_calls_performed"] += int(artifact.get("provider_calls_performed", 0) or 0)
        usage["publish_calls_performed"] += int(artifact.get("publish_calls_performed", 0) or 0)
        usage["retries_performed"] += int(artifact.get("retries_performed", 0) or 0)
        spend = artifact.get("actual_spend") if artifact.get("actual_spend") is not None else artifact.get("actual_spend_usd")
        if spend not in (None, ""):
            try:
                usage["declared_spend_total"] += float(spend)
            except (TypeError, ValueError) as exc:
                raise StandingAutonomyPolicyError("daily_accounting_spend_invalid", f"daily accounting spend is not numeric in {path}") from exc
        spend_unit = artifact.get("spend_unit") or artifact.get("actual_spend_unit")
        if spend_unit not in (None, ""):
            if usage["spend_unit"] is None:
                usage["spend_unit"] = str(spend_unit)
            elif usage["spend_unit"] != str(spend_unit):
                raise StandingAutonomyPolicyError("daily_accounting_spend_unit_mismatch", f"daily accounting spend unit mismatch in {path}")
        usage["files"].append(str(path))
    return usage


def _prepare_authorization_scope(
    *,
    handoff_report: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    slot_id = str(handoff_report.get("selected_slot_id") or "")
    candidate = handoff_report.get("selected_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    candidate_path_text = _normalized_repo_path_text(str(handoff_report.get("selected_candidate_path") or candidate.get("artifact_path") or ""))
    candidate_path = _path_from_repo_text(candidate_path_text)
    candidate_sha256 = str(handoff_report.get("selected_candidate_sha256") or candidate.get("artifact_sha256") or "")
    selected_prompt_input = handoff_report.get("selected_prompt_input")
    selected_prompt_input = selected_prompt_input if isinstance(selected_prompt_input, dict) else {}
    structured = handoff_report.get("structured_executor_inputs")
    structured = structured if isinstance(structured, dict) else {}
    soul_metadata = structured.get("soul_metadata")
    soul_metadata = soul_metadata if isinstance(soul_metadata, dict) else {}
    prompt_sha256 = str(handoff_report.get("prompt_sha256") or selected_prompt_input.get("prompt_sha256") or candidate.get("prompt_sha256") or "")
    date_str = str(handoff_report.get("date") or "")
    expected_output_directory = handoff_report.get("expected_output_directory") or approval.expected_output_directory(date_str)
    expected_output_stem = handoff_report.get("expected_output_stem") or approval.expected_output_stem(slot_id)
    allowed_output_extensions = handoff_report.get("allowed_output_extensions") or list(approval.ALLOWED_OUTPUT_EXTENSIONS)
    if isinstance(expected_output_directory, str):
        expected_output_directory = Path(expected_output_directory)
    if not expected_output_directory.is_absolute():
        expected_output_directory = ROOT / expected_output_directory
    caption = str(handoff_report.get("caption") or selected_prompt_input.get("caption_seed") or handoff_report.get("selected_caption_seed") or "")
    custom_reference_id = str(
        handoff_report.get("custom_reference_id")
        or structured.get("custom_reference_id")
        or soul_metadata.get("custom_reference_id")
        or ""
    )
    candidate_selection_binding = handoff_report.get("candidate_selection_binding")
    candidate_selection_binding = candidate_selection_binding if isinstance(candidate_selection_binding, dict) else {}
    provider_execution_binding = handoff_report.get("provider_execution_binding")
    provider_execution_binding = provider_execution_binding if isinstance(provider_execution_binding, dict) else {}
    binding_linkage = handoff_report.get("binding_linkage")
    binding_linkage = binding_linkage if isinstance(binding_linkage, dict) else {}
    binding_error = _handoff_cross_field_binding_split_brain_error(
        slot_id=slot_id,
        candidate_id=str(candidate.get("candidate_id") or ""),
        source_selected_candidate_artifact_path=candidate_path_text,
        source_selected_candidate_artifact_sha256=candidate_sha256,
        selected_candidate_prompt_sha256=str(candidate.get("prompt_sha256") or ""),
        selected_prompt_input_prompt_sha256=str(selected_prompt_input.get("prompt_sha256") or ""),
        structured_executor_inputs_selected_prompt_sha256=str(structured.get("selected_prompt_sha256") or ""),
        selected_candidate_lane=str(candidate.get("lane") or ""),
        selected_prompt_input_lane=str(selected_prompt_input.get("lane") or ""),
        dual_binding_contract={
            "candidate_selection_binding": candidate_selection_binding,
            "provider_execution_binding": provider_execution_binding,
            "binding_linkage": binding_linkage,
        },
    )
    if binding_error is not None:
        code, detail = binding_error
        _require(False, code, detail)
    return {
        "date": date_str,
        "slot_id": slot_id,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_artifact_path": candidate_path.resolve(),
        "candidate_artifact_sha256": candidate_sha256,
        "prompt_sha256": prompt_sha256,
        "expected_output_directory": str(
            _ensure_path_within_root(
                Path(str(expected_output_directory)),
                ROOT / "pipeline" / "higgsfield_library" / "lena",
                code="expected_output_directory_escape",
                label="expected output directory",
                must_exist=False,
            )
        ),
        "expected_output_stem": str(expected_output_stem),
        "allowed_output_extensions": [str(extension) for extension in allowed_output_extensions],
        "platform": str(handoff_report.get("platform") or candidate.get("platform") or "Instagram Feed"),
        "caption": caption,
        "provider": str(policy["allowed_provider"]),
        "model": str(policy["allowed_model"]),
        "soul_name": str(policy["allowed_soul"]),
        "soul_type": "Soul 2.0",
        "custom_reference_id": custom_reference_id,
        "generation_handoff_artifact_path": str(Path(str(handoff_report.get("handoff_artifact_path") or handoff_report.get("selected_handoff_artifact_path") or ""))),
        "generation_handoff_artifact_sha256": str(handoff_report.get("handoff_sha256") or handoff_report.get("selected_handoff_sha256") or ""),
        "candidate_selection_binding": candidate_selection_binding,
        "provider_execution_binding": provider_execution_binding,
        "binding_linkage": binding_linkage,
        "selected_candidate": candidate,
    }


def issue_cycle_authorization(
    policy_artifact: Path,
    handoff_artifact: Path,
    *,
    auth_root: Path | None = None,
    report_root: Path | None = None,
) -> dict[str, Any]:
    policy_result = validate_policy_artifact(policy_artifact)
    handoff_path = _ensure_path_within_root(
        handoff_artifact,
        ROOT / "pipeline" / "strategy" / "lena" / "next_actions",
        code="handoff_path_escape",
        label="generation handoff artifact",
        must_exist=True,
    )
    raw_handoff = _read_json_object(handoff_path, code="handoff_missing_or_invalid", label="generation handoff artifact")
    raw_selected_candidate = raw_handoff.get("selected_candidate")
    raw_selected_candidate = raw_selected_candidate if isinstance(raw_selected_candidate, dict) else {}
    raw_selected_prompt_input = raw_handoff.get("selected_prompt_input")
    raw_selected_prompt_input = raw_selected_prompt_input if isinstance(raw_selected_prompt_input, dict) else {}
    raw_binding_error = _handoff_cross_field_binding_split_brain_error(
        slot_id=str(raw_handoff.get("selected_slot_id") or raw_handoff.get("slot_id") or ""),
        candidate_id=str(raw_selected_candidate.get("candidate_id") or raw_handoff.get("candidate_id") or ""),
        source_selected_candidate_artifact_path=str(
            raw_handoff.get("selected_candidate_path")
            or raw_selected_candidate.get("artifact_path")
            or raw_handoff.get("candidate_artifact_path")
            or ""
        ).replace("\\", "/"),
        source_selected_candidate_artifact_sha256=str(
            raw_handoff.get("selected_candidate_sha256")
            or raw_selected_candidate.get("artifact_sha256")
            or raw_handoff.get("candidate_artifact_sha256")
            or ""
        ),
        selected_candidate_prompt_sha256=str(raw_selected_candidate.get("prompt_sha256") or ""),
        selected_prompt_input_prompt_sha256=str(raw_selected_prompt_input.get("prompt_sha256") or raw_handoff.get("prompt_sha256") or ""),
        structured_executor_inputs_selected_prompt_sha256=str(
            (raw_handoff.get("structured_executor_inputs") or {}).get("selected_prompt_sha256") or ""
        ),
        selected_candidate_lane=str(raw_selected_candidate.get("lane") or ""),
        selected_prompt_input_lane=str(raw_selected_prompt_input.get("lane") or ""),
        dual_binding_contract={
            "candidate_selection_binding": raw_handoff.get("candidate_selection_binding"),
            "provider_execution_binding": raw_handoff.get("provider_execution_binding"),
            "binding_linkage": raw_handoff.get("binding_linkage"),
        },
    )
    if raw_binding_error is not None:
        code, detail = raw_binding_error
        _require(False, code, detail)
    raw_provider_binding = raw_handoff.get("provider_execution_binding")
    raw_provider_binding = raw_provider_binding if isinstance(raw_provider_binding, dict) else {}
    raw_provider_prompt_sha = _normalized_repo_path_text(str(raw_provider_binding.get("provider_prompt_sha256") or ""))
    raw_prompt_sha_values = {
        _normalized_repo_path_text(str(raw_handoff.get("prompt_sha256") or "")),
        _normalized_repo_path_text(str(raw_selected_prompt_input.get("prompt_sha256") or "")),
        _normalized_repo_path_text(str((raw_handoff.get("structured_executor_inputs") or {}).get("selected_prompt_sha256") or "")),
    }
    raw_prompt_sha_values.discard("")
    if raw_prompt_sha_values and (len(raw_prompt_sha_values) > 1 or raw_provider_prompt_sha not in raw_prompt_sha_values):
        _require(
            False,
            "handoff_prompt_binding_split_brain",
            json.dumps(
                {
                    "slot_id": str(raw_handoff.get("selected_slot_id") or raw_handoff.get("slot_id") or ""),
                    "candidate_id": str(raw_selected_candidate.get("candidate_id") or raw_handoff.get("candidate_id") or ""),
                    "provider_prompt_sha256": raw_provider_prompt_sha,
                    "raw_prompt_sha_values": sorted(raw_prompt_sha_values),
                    "selected_candidate_prompt_sha256": str(raw_selected_candidate.get("prompt_sha256") or ""),
                    "selected_prompt_input_prompt_sha256": str(raw_selected_prompt_input.get("prompt_sha256") or ""),
                    "structured_executor_inputs_selected_prompt_sha256": str((raw_handoff.get("structured_executor_inputs") or {}).get("selected_prompt_sha256") or ""),
                },
                indent=2,
                ensure_ascii=True,
                sort_keys=True,
            ),
        )
    from pipeline import higgsfield_lena_api_executor as executor

    handoff_report, source, packet_validation, validation = executor._validate_handoff_packet(handoff_path)
    scope = _prepare_authorization_scope(handoff_report=handoff_report, policy=policy_result["artifact"])
    day = scope["date"]
    slot_id = scope["slot_id"]
    candidate_path = _ensure_path_within_root(scope["candidate_artifact_path"], ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates", code="candidate_path_escape", label="candidate artifact", must_exist=True)
    candidate_path_text = _normalized_repo_path_text(str(handoff_report.get("selected_candidate_path") or raw_handoff.get("selected_candidate_path") or raw_selected_candidate.get("artifact_path") or raw_handoff.get("candidate_artifact_path") or ""))
    expected_output_directory = _ensure_path_within_root(
        Path(str(scope["expected_output_directory"])),
        ROOT / "pipeline" / "higgsfield_library" / "lena",
        code="expected_output_directory_escape",
        label="expected output directory",
        must_exist=False,
    )
    expected_output_stem = str(scope["expected_output_stem"])
    allowed_output_extensions = [str(item) for item in scope["allowed_output_extensions"]]
    for output_path in _authorized_output_paths(expected_output_directory, expected_output_stem, allowed_output_extensions):
        _require(not output_path.exists(), "expected_output_conflict", f"authorized output path already exists: {output_path}")
    report_root = report_root or REPORT_ROOT
    usage_before = collect_daily_usage(report_root, day)
    _require(usage_before["cycle_count"] < int(policy_result["artifact"]["maximum_cycles_per_day"]), "daily_cycle_cap_reached", "daily cycle cap reached")
    _require(usage_before["provider_calls_performed"] < int(policy_result["artifact"]["maximum_provider_calls_per_day"]), "daily_provider_call_cap_reached", "daily provider call cap reached")
    _require(usage_before["publish_calls_performed"] < int(policy_result["artifact"]["maximum_publish_actions_per_day"]), "daily_publish_action_cap_reached", "daily publish action cap reached")
    spend_unit = usage_before["spend_unit"] or str(policy_result["artifact"]["spend_unit"])
    _require(spend_unit == str(policy_result["artifact"]["spend_unit"]), "daily_spend_unit_mismatch", "existing daily accounting spend unit does not match policy")
    _require(usage_before["declared_spend_total"] < float(policy_result["artifact"]["daily_spend_ceiling"]), "daily_spend_cap_reached", "daily spend cap reached")

    auth_root = auth_root or AUTH_ROOT
    auth_path = default_auth_path(day, slot_id)
    auth_path = _ensure_path_within_root(auth_path, auth_root, code="authorization_path_escape", label="cycle authorization artifact", must_exist=False)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = auth_path.with_name(f"{auth_path.name}.lock")
    try:
        lock_fd = lock_path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise StandingAutonomyPolicyError("authorization_already_in_progress", f"authorization is already being issued: {auth_path}") from exc
    try:
        lock_fd.close()
        payload = {
            "report_type": AUTH_REPORT_TYPE,
            "schema_version": AUTH_SCHEMA_VERSION,
            "authorization_mode": AUTHORIZATION_MODE,
            "authorization_issuer": AUTHORIZATION_ISSUER,
            "policy_artifact_path": str(policy_result["path"]),
            "policy_artifact_sha256": policy_result["sha256"],
            "policy_id": str(policy_result["artifact"]["policy_id"]),
            "policy_version": str(policy_result["artifact"]["policy_version"]),
            "authorization_artifact_path": str(auth_path),
            "date": day,
            "slot_id": slot_id,
            "candidate_id": scope["candidate_id"],
            "candidate_artifact_path": str(candidate_path),
            "candidate_artifact_sha256": _sha256_file(candidate_path),
            "prompt_sha256": scope["prompt_sha256"],
            "candidate_selection_binding": scope["candidate_selection_binding"],
            "provider_execution_binding": scope["provider_execution_binding"],
            "binding_linkage": scope["binding_linkage"],
            "expected_output_directory": str(expected_output_directory),
            "expected_output_stem": expected_output_stem,
            "allowed_output_extensions": allowed_output_extensions,
            "platform": scope["platform"],
            "caption": scope["caption"],
            "provider": scope["provider"],
            "model": scope["model"],
            "soul_name": scope["soul_name"],
            "soul_type": scope["soul_type"],
            "custom_reference_id": scope["custom_reference_id"],
            "generation_handoff_artifact_path": str(handoff_path),
            "generation_handoff_artifact_sha256": _sha256_file(handoff_path),
            "single_use": True,
            "consumed": False,
            "consumed_at_utc": None,
            "one_slot": True,
            "one_candidate": True,
            "one_asset": True,
            "one_platform": True,
            "provider_call_cap_per_cycle": int(policy_result["artifact"]["provider_call_cap_per_cycle"]),
            "publish_action_cap_per_cycle": int(policy_result["artifact"]["publish_action_cap_per_cycle"]),
            "retry_cap_per_cycle": int(policy_result["artifact"]["retry_cap_per_cycle"]),
            "maximum_cycles_per_day": int(policy_result["artifact"]["maximum_cycles_per_day"]),
            "maximum_provider_calls_per_day": int(policy_result["artifact"]["maximum_provider_calls_per_day"]),
            "maximum_publish_actions_per_day": int(policy_result["artifact"]["maximum_publish_actions_per_day"]),
            "daily_spend_ceiling": float(policy_result["artifact"]["daily_spend_ceiling"]),
            "spend_unit": str(policy_result["artifact"]["spend_unit"]),
            "allowed_provider": str(policy_result["artifact"]["allowed_provider"]),
            "allowed_model": str(policy_result["artifact"]["allowed_model"]),
            "allowed_soul": str(policy_result["artifact"]["allowed_soul"]),
            "allowed_platforms": list(policy_result["artifact"]["allowed_platforms"]),
            "allowed_media_types": list(policy_result["artifact"]["allowed_media_types"]),
            "duplicate_content_rejection_enabled": True,
            "qa_required": True,
            "identity_verification_required": True,
            "analytics_triggered_regeneration_disabled": True,
            "kill_switch_enabled": True,
            "autonomy_enabled": True,
            "live_generation_enabled": True,
            "live_publishing_enabled": True,
            "publication_mode": "bounded_live_cycle",
            "daily_usage_before": {
                "cycle_count": usage_before["cycle_count"],
                "provider_calls_performed": usage_before["provider_calls_performed"],
                "publish_calls_performed": usage_before["publish_calls_performed"],
                "retries_performed": usage_before["retries_performed"],
                "declared_spend_total": usage_before["declared_spend_total"],
                "spend_unit": usage_before["spend_unit"] or str(policy_result["artifact"]["spend_unit"]),
            },
            "daily_usage_after": None,
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
            "operator_id": AUTHORIZATION_ISSUER,
            "publish_authorized": True,
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "retries_performed": 0,
            "policy_sha256_binding": policy_result["sha256"],
            "cycle_id": f"lena_standing_autonomy_cycle_{day}_{slot_id}_{uuid.uuid4().hex[:8]}",
            "issued_at_utc": _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "expires_at_utc": _cycle_authorization_expires_at(policy_result),
            "authorization_consumption_implemented": True,
            "authorization_consumed": False,
            "human_per_cycle_approval_required": False,
            "human_per_cycle_approval_present": False,
            "audited_inputs": {
                "handoff_artifact_path": str(handoff_path),
                "handoff_artifact_sha256": _sha256_file(handoff_path),
                "policy_artifact_path": str(policy_result["path"]),
                "policy_artifact_sha256": policy_result["sha256"],
                "candidate_artifact_path": str(candidate_path),
                "candidate_artifact_sha256": _sha256_file(candidate_path),
                "candidate_selection_binding": scope["candidate_selection_binding"],
                "provider_execution_binding": scope["provider_execution_binding"],
                "binding_linkage": scope["binding_linkage"],
                "expected_output_directory": str(expected_output_directory),
                "expected_output_stem": expected_output_stem,
                "allowed_output_extensions": allowed_output_extensions,
            },
        }
        canonical_auth_sha = _sha256_bytes((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))
        payload["authorization_artifact_sha256"] = canonical_auth_sha
        _write_json_atomic(auth_path, payload)
        return {
            "path": auth_path.resolve(),
            "sha256": canonical_auth_sha,
            "artifact": payload,
            "policy": policy_result,
            "handoff": {
                "path": handoff_path.resolve(),
                "sha256": _sha256_file(handoff_path),
                "report": handoff_report,
                "source": source,
                "packet_validation": packet_validation,
                "validation": validation,
            },
            "daily_usage_before": usage_before,
        }
    finally:
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass


def validate_cycle_authorization_artifact(
    auth_path: Path,
    *,
    policy_result: dict[str, Any] | None = None,
    handoff_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    auth_path = _ensure_path_within_root(
        auth_path,
        AUTH_ROOT,
        code="authorization_path_escape",
        label="cycle authorization artifact",
        must_exist=True,
    )
    auth = _read_json_object(auth_path, code="authorization_missing_or_invalid", label="cycle authorization artifact")
    _require(auth.get("report_type") == AUTH_REPORT_TYPE, "authorization_report_type_mismatch", f"authorization report_type must be {AUTH_REPORT_TYPE!r}")
    _require(auth.get("schema_version") == AUTH_SCHEMA_VERSION, "authorization_schema_mismatch", f"authorization schema_version must be {AUTH_SCHEMA_VERSION!r}")
    _require(auth.get("authorization_mode") == AUTHORIZATION_MODE, "authorization_mode_invalid", f"authorization_mode must be {AUTHORIZATION_MODE!r}")
    _require(auth.get("authorization_issuer") == AUTHORIZATION_ISSUER, "authorization_issuer_invalid", f"authorization_issuer must be {AUTHORIZATION_ISSUER!r}")
    _require(auth.get("single_use") is True, "authorization_single_use_invalid", "authorization must be single-use")
    _require(auth.get("consumed") is False, "authorization_already_consumed", "authorization has already been consumed")
    _require(auth.get("kill_switch_enabled") is True, "authorization_kill_switch_disabled", "kill switch must be enabled")
    _require(int(auth.get("provider_call_cap_per_cycle", 0)) == 1, "provider_call_cap_invalid", "provider call cap must be one")
    _require(int(auth.get("publish_action_cap_per_cycle", 0)) == 1, "publish_action_cap_invalid", "publish action cap must be one")
    _require(int(auth.get("retry_cap_per_cycle", -1)) == 0, "retry_cap_invalid", "retry cap must be zero")
    _require(int(auth.get("maximum_cycles_per_day", 0)) > 0, "daily_cycle_cap_invalid", "maximum_cycles_per_day must be positive")
    _require(int(auth.get("maximum_provider_calls_per_day", 0)) > 0, "daily_provider_call_cap_invalid", "maximum_provider_calls_per_day must be positive")
    _require(int(auth.get("maximum_publish_actions_per_day", 0)) > 0, "daily_publish_action_cap_invalid", "maximum_publish_actions_per_day must be positive")
    _require(float(auth.get("daily_spend_ceiling", 0)) > 0, "daily_spend_cap_invalid", "daily_spend_ceiling must be positive")
    _require(str(auth.get("spend_unit") or "").strip(), "spend_unit_missing", "spend_unit is required")
    _require(auth.get("duplicate_content_rejection_enabled") is True, "duplicate_content_rejection_disabled", "duplicate content rejection must be enabled")
    _require(auth.get("qa_required") is True, "qa_required_invalid", "qa_required must be true")
    _require(auth.get("identity_verification_required") is True, "identity_verification_required_invalid", "identity_verification_required must be true")
    _require(auth.get("analytics_triggered_regeneration_disabled") is True, "analytics_triggered_regeneration_disabled_invalid", "analytics_triggered_regeneration_disabled must be true")
    _require(auth.get("autonomy_enabled") is True, "autonomy_enabled_invalid", "autonomy must be enabled")
    _require(auth.get("live_generation_enabled") is True, "live_generation_enabled_invalid", "live_generation must be enabled")
    _require(auth.get("live_publishing_enabled") is True, "live_publishing_enabled_invalid", "live publishing must be enabled")
    _require(auth.get("provider") == "Higgsfield", "provider_mismatch", "provider must be Higgsfield")
    _require(auth.get("model") == "text2image_soul_v2", "model_mismatch", "model must be text2image_soul_v2")
    _require(auth.get("soul_name") == "Lena", "soul_mismatch", "soul_name must be Lena")
    _require(auth.get("platform") in {"Instagram Feed", "Facebook Page"}, "platform_invalid", "platform must be allowed by policy")
    if policy_result is not None:
        policy = policy_result["artifact"]
        _require(str(auth.get("policy_artifact_sha256") or "") == policy_result["sha256"], "policy_sha_mismatch", "policy artifact SHA does not match")
        _require(str(auth.get("policy_id") or "") == str(policy.get("policy_id") or ""), "policy_id_mismatch", "policy id does not match")
        _require(str(auth.get("policy_version") or "") == str(policy.get("policy_version") or ""), "policy_version_mismatch", "policy version does not match")
    _require(auth.get("authorization_artifact_path") == str(auth_path), "authorization_path_binding_mismatch", "authorization artifact path binding mismatch")
    canonical_sha = _sha256_json_without_keys(auth_path, {"authorization_artifact_sha256"})
    _require(str(auth.get("authorization_artifact_sha256") or "") == canonical_sha, "authorization_sha_mismatch", "authorization SHA does not match canonical artifact bytes")
    _require(str(auth.get("policy_artifact_path") or "").strip(), "policy_artifact_path_missing", "policy_artifact_path is required")
    _require(str(auth.get("generation_handoff_artifact_path") or "").strip(), "handoff_artifact_path_missing", "generation_handoff_artifact_path is required")
    _require(str(auth.get("candidate_artifact_path") or "").strip(), "candidate_artifact_path_missing", "candidate_artifact_path is required")
    _require(str(auth.get("prompt_sha256") or "").strip(), "prompt_sha256_missing", "prompt_sha256 is required")
    _require(str(auth.get("expected_output_directory") or "").strip(), "expected_output_directory_missing", "expected_output_directory is required")
    _require(str(auth.get("expected_output_stem") or "").strip(), "expected_output_stem_missing", "expected_output_stem is required")
    allowed_output_extensions = auth.get("allowed_output_extensions")
    _require(
        isinstance(allowed_output_extensions, list) and allowed_output_extensions == list(approval.ALLOWED_OUTPUT_EXTENSIONS),
        "allowed_output_extensions_invalid",
        "allowed_output_extensions must match the approved extension set",
    )
    _require(str(auth.get("cycle_id") or "").strip(), "cycle_id_missing", "cycle_id is required")
    _require(str(auth.get("date") or "").strip(), "date_missing", "date is required")
    _require(str(auth.get("slot_id") or "").strip(), "slot_id_missing", "slot_id is required")
    expiry = _validate_iso_datetime(str(auth.get("expires_at_utc") or ""), code="authorization_expiry_invalid", label="expires_at_utc")
    _require(expiry > _now_utc(), "authorization_expired", "authorization has expired")
    expected_output_directory = _ensure_path_within_root(
        Path(str(auth.get("expected_output_directory") or "")),
        ROOT / "pipeline" / "higgsfield_library" / "lena",
        code="expected_output_directory_escape",
        label="expected output directory",
        must_exist=False,
    )
    _authorized_output_paths(expected_output_directory, str(auth.get("expected_output_stem") or ""), allowed_output_extensions)
    if handoff_report is not None and handoff_report.get("platform") is not None:
        _require(
            str(auth.get("platform") or "") == str(handoff_report.get("platform") or ""),
            "platform_invalid",
            "authorization platform must match handoff",
        )
    if handoff_report is not None:
        selected_candidate = handoff_report.get("selected_candidate")
        selected_candidate = selected_candidate if isinstance(selected_candidate, dict) else {}
        selected_prompt_input = handoff_report.get("selected_prompt_input")
        selected_prompt_input = selected_prompt_input if isinstance(selected_prompt_input, dict) else {}
        selected_candidate_path_value = str(handoff_report.get("selected_candidate_path") or selected_candidate.get("artifact_path") or "")
        candidate_path_text = _normalized_repo_path_text(selected_candidate_path_value)
        selected_candidate_sha_value = str(handoff_report.get("selected_candidate_sha256") or selected_candidate.get("artifact_sha256") or "")
        selected_prompt_sha_value = str(handoff_report.get("prompt_sha256") or selected_prompt_input.get("prompt_sha256") or selected_candidate.get("prompt_sha256") or "")
        resolved_selected_candidate_path = _ensure_path_within_root(
            _path_from_repo_text(selected_candidate_path_value),
            ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
            code="candidate_path_escape",
            label="selected candidate artifact",
            must_exist=True,
        )
        resolved_handoff_path = _ensure_path_within_root(
            Path(str(auth.get("generation_handoff_artifact_path") or "")),
            ROOT / "pipeline" / "strategy" / "lena" / "next_actions",
            code="handoff_path_escape",
            label="generation handoff artifact",
            must_exist=True,
        )
        _require(
            str(auth.get("generation_handoff_artifact_sha256") or "") == _sha256_file(resolved_handoff_path),
            "handoff_sha_mismatch",
            "generation handoff SHA does not match the artifact bytes",
        )
        resolved_candidate_path = _ensure_path_within_root(
            Path(str(auth.get("candidate_artifact_path") or "")),
            ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates",
            code="candidate_path_escape",
            label="candidate artifact",
            must_exist=True,
        )
        _require(
            str(auth.get("candidate_artifact_path") or "") == str(resolved_selected_candidate_path),
            "authorization_candidate_path_mismatch",
            "authorization candidate path does not match handoff",
        )
    _require(
        str(auth.get("candidate_artifact_sha256") or "") == _sha256_file(resolved_candidate_path),
        "authorization_candidate_sha_mismatch",
        "authorization candidate SHA does not match the artifact bytes",
    )
    candidate_selection_binding = auth.get("candidate_selection_binding")
    provider_execution_binding = auth.get("provider_execution_binding")
    binding_linkage = auth.get("binding_linkage")
    _require(
        isinstance(candidate_selection_binding, dict),
        "authorization_candidate_selection_binding_missing",
        "authorization candidate_selection_binding must be present",
    )
    _require(
        isinstance(provider_execution_binding, dict),
        "authorization_provider_execution_binding_missing",
        "authorization provider_execution_binding must be present",
    )
    _require(
        isinstance(binding_linkage, dict),
        "authorization_binding_linkage_missing",
        "authorization binding_linkage must be present",
    )
    if handoff_report is not None:
        selected_prompt_input = handoff_report.get("selected_prompt_input")
        selected_prompt_input = selected_prompt_input if isinstance(selected_prompt_input, dict) else {}
        structured = handoff_report.get("structured_executor_inputs")
        structured = structured if isinstance(structured, dict) else {}
        _require(
            provider_execution_binding.get("content_packet_artifact_path") == str(handoff_report.get("selected_prompt_input_artifact_path") or selected_prompt_input.get("artifact_path") or ""),
            "authorization_provider_execution_path_mismatch",
            "authorization provider_execution_binding path does not match handoff",
        )
        _require(
            provider_execution_binding.get("provider_prompt_sha256") == str(selected_prompt_input.get("prompt_sha256") or ""),
            "authorization_provider_execution_prompt_sha_mismatch",
            "authorization provider_execution_binding prompt SHA does not match handoff",
        )
        _require(
            provider_execution_binding.get("provider_prompt_sha256") == str(structured.get("selected_prompt_sha256") or ""),
            "authorization_provider_execution_prompt_sha_mismatch",
            "authorization provider_execution_binding prompt SHA does not match handoff",
        )
        _require(
            _normalized_repo_path_text(str(handoff_report.get("prompt_sha256") or "")) == str(provider_execution_binding.get("provider_prompt_sha256") or ""),
            "authorization_provider_execution_prompt_sha_mismatch",
            "authorization provider_execution_binding prompt SHA does not match handoff",
        )
        _require(
            provider_execution_binding.get("provider_lane") == str(selected_prompt_input.get("lane") or ""),
            "authorization_provider_execution_lane_mismatch",
            "authorization provider_execution_binding lane does not match handoff",
        )
        _require(str(auth.get("date") or "") == str(handoff_report.get("date") or ""), "authorization_date_mismatch", "authorization date does not match handoff")
        _require(str(auth.get("slot_id") or "") == str(handoff_report.get("selected_slot_id") or ""), "authorization_slot_mismatch", "authorization slot_id does not match handoff")
        _require(str(auth.get("candidate_id") or "") == str(selected_candidate.get("candidate_id") or ""), "authorization_candidate_mismatch", "authorization candidate_id does not match handoff")
        _require(str(auth.get("candidate_artifact_sha256") or "") == selected_candidate_sha_value, "authorization_candidate_sha_mismatch", "authorization candidate SHA does not match handoff")
        _require(str(auth.get("prompt_sha256") or "") == selected_prompt_sha_value, "authorization_prompt_sha_mismatch", "authorization prompt SHA does not match handoff")
    return {
        "path": auth_path.resolve(),
        "sha256": canonical_sha,
        "artifact": auth,
        "expires_at_utc": expiry.isoformat(),
    }


def issue_cycle_authorization_report(
    policy_artifact: Path,
    handoff_artifact: Path,
    *,
    auth_root: Path | None = None,
    report_root: Path | None = None,
) -> dict[str, Any]:
    return issue_cycle_authorization(
        policy_artifact,
        handoff_artifact,
        auth_root=auth_root,
        report_root=report_root,
    )
