from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

"""
Minimal canonical durable Lena job-state layer.

Scope of this module:
- define the canonical state model
- persist one JSON snapshot per logical Lena job under pipeline/state/lena_jobs/
- validate explicit state transitions
- derive a best-evidence snapshot from existing A-side artifacts without
  mutating those artifacts

Important limitations:
- atomic writes protect individual snapshot-file updates, but they do not
  provide true logical-job leases or cross-process locking
- no scrubber integration lives here
- no queue mutation or publish action lives here
- no publisher, orchestrator, or scheduler replacement lives here
"""

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = ROOT / "pipeline"
DEFAULT_JOB_STATE_DIR = PIPELINE_DIR / "state" / "lena_jobs"

SCHEMA_VERSION = "lena_job_state_v1"
VALID_STATES = (
    "planned",
    "generating",
    "qa_required",
    "approved",
    "clean_export_required",
    "clean_export_verified",
    "queued",
    "published_pending_learning",
    "complete",
    "hard_stopped",
)

ALLOWED_TRANSITIONS = {
    "planned": {"planned", "generating"},
    "generating": {"generating", "qa_required", "hard_stopped"},
    "qa_required": {"qa_required", "approved", "generating", "hard_stopped"},
    "approved": {"approved", "clean_export_required"},
    "clean_export_required": {"clean_export_required", "clean_export_verified", "hard_stopped"},
    "clean_export_verified": {"clean_export_verified", "queued"},
    "queued": {"queued", "published_pending_learning", "hard_stopped"},
    "published_pending_learning": {"published_pending_learning", "complete"},
    "complete": {"complete"},
    "hard_stopped": {"hard_stopped"},
}

STATE_OWNER_BY_STATE = {
    "planned": "planning",
    "generating": "generation",
    "qa_required": "qa",
    "approved": "approval",
    "clean_export_required": "clean_export",
    "clean_export_verified": "clean_export",
    "queued": "queue",
    "published_pending_learning": "learning",
    "complete": "learning",
    "hard_stopped": "manual_review",
}

ARTIFACT_PATH_KEYS = (
    "strategy_artifact",
    "workorder",
    "provider_manifest",
    "generated_source_asset",
    "qa_result",
    "repair_record",
    "approval_artifact",
    "publish_packet",
    "clean_derivative",
    "clean_export_verification_artifact",
    "queue_item",
    "publish_receipt",
    "metrics_state",
    "learning_state",
)


class JobStateError(ValueError):
    pass


class StateTransitionError(JobStateError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def _sanitize_file_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("._") or "job"


def _normalize_path(path: Optional[Path], *, root: Path) -> Optional[str]:
    if not path:
        return None
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path.resolve())


def _first_non_empty(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def derive_canonical_job_id(
    *,
    source_slot_id: Optional[str] = None,
    output_slot_id: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    platform_media_id: Optional[str] = None,
    workorder_id: Optional[str] = None,
) -> str:
    """
    Smallest practical canonical identity rule for current A-side content:
    1. output_slot_id when present
    2. else source_slot_id
    3. else provider_job_id with a provider- prefix
    4. else platform_media_id with a platform- prefix
    5. else workorder_id with a workorder- prefix

    The snapshot keeps the other identifiers alongside this one. The goal is
    to join current identifiers, not replace them with a brand-new scheme.
    source_slot_id remains provenance; the canonical identity needs to track
    the distinct output job that can be queued or published under its own id.
    """
    if output_slot_id and str(output_slot_id).strip():
        return str(output_slot_id).strip()
    if source_slot_id and str(source_slot_id).strip():
        return str(source_slot_id).strip()
    if provider_job_id and str(provider_job_id).strip():
        return f"provider-{str(provider_job_id).strip()}"
    if platform_media_id and str(platform_media_id).strip():
        return f"platform-{str(platform_media_id).strip()}"
    if workorder_id and str(workorder_id).strip():
        return f"workorder-{str(workorder_id).strip()}"
    raise JobStateError(
        "canonical job identity requires at least one stable identifier "
        "(source_slot_id, output_slot_id, provider_job_id, platform_media_id, or workorder_id)"
    )


def snapshot_path_for_job(
    canonical_job_id: str,
    *,
    state_dir: Optional[Path] = None,
) -> Path:
    return (state_dir or DEFAULT_JOB_STATE_DIR) / f"{_sanitize_file_stem(canonical_job_id)}.json"


def validate_state_name(state: str) -> None:
    if state not in VALID_STATES:
        raise JobStateError(f"invalid Lena job state {state!r}; expected one of {list(VALID_STATES)}")


def validate_transition(from_state: str, to_state: str) -> None:
    validate_state_name(from_state)
    validate_state_name(to_state)
    allowed = ALLOWED_TRANSITIONS[from_state]
    if to_state not in allowed:
        raise StateTransitionError(f"invalid Lena job state transition: {from_state!r} -> {to_state!r}")


def create_snapshot(
    *,
    canonical_job_id: Optional[str] = None,
    source_slot_id: Optional[str] = None,
    output_slot_id: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    platform_media_id: Optional[str] = None,
    workorder_id: Optional[str] = None,
    current_state: str = "planned",
    previous_state: Optional[str] = None,
    current_owner: Optional[str] = None,
    attempt_counters_by_stage: Optional[Dict[str, int]] = None,
    hard_stop_reason: Optional[str] = None,
    originating_stage: Optional[str] = None,
    failure_classification: Optional[str] = None,
    retryable: Optional[bool] = None,
    manual_intervention_required: Optional[bool] = None,
    attempts_exhausted: Optional[bool] = None,
    artifact_paths: Optional[Dict[str, Optional[str]]] = None,
    artifact_evidence: Optional[Iterable[str]] = None,
    notes: Optional[Iterable[str]] = None,
    state_source: str = "explicit",
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
    state_transitioned_at: Optional[str] = None,
) -> Dict[str, Any]:
    validate_state_name(current_state)
    if previous_state is not None:
        validate_state_name(previous_state)
    if state_source not in {"explicit", "derived"}:
        raise JobStateError("state_source must be 'explicit' or 'derived'")

    now = utc_now_iso()
    resolved_job_id = canonical_job_id or derive_canonical_job_id(
        source_slot_id=source_slot_id,
        output_slot_id=output_slot_id,
        provider_job_id=provider_job_id,
        platform_media_id=platform_media_id,
        workorder_id=workorder_id,
    )
    normalized_artifacts = {key: None for key in ARTIFACT_PATH_KEYS}
    if artifact_paths:
        for key, value in artifact_paths.items():
            if key in normalized_artifacts and value:
                normalized_artifacts[key] = str(value)

    return {
        "schema_version": SCHEMA_VERSION,
        "canonical_job_id": resolved_job_id,
        "source_slot_id": _first_non_empty(source_slot_id),
        "output_slot_id": _first_non_empty(output_slot_id),
        "provider_job_id": _first_non_empty(provider_job_id),
        "platform_media_id": _first_non_empty(platform_media_id),
        "workorder_id": _first_non_empty(workorder_id),
        "current_state": current_state,
        "previous_state": previous_state,
        "state_source": state_source,
        "state_transitioned_at": state_transitioned_at or now,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
        "current_owner": current_owner or STATE_OWNER_BY_STATE[current_state],
        "attempt_counters_by_stage": dict(attempt_counters_by_stage or {}),
        "hard_stop_reason": hard_stop_reason,
        "originating_stage": originating_stage,
        "failure_classification": failure_classification,
        "retryable": retryable,
        "manual_intervention_required": manual_intervention_required,
        "attempts_exhausted": attempts_exhausted,
        "artifact_paths": normalized_artifacts,
        "artifact_evidence": sorted({str(item) for item in (artifact_evidence or []) if str(item).strip()}),
        "notes": [str(item) for item in (notes or []) if str(item).strip()],
    }


def save_snapshot(snapshot: Dict[str, Any], *, state_dir: Optional[Path] = None) -> Path:
    validate_state_name(str(snapshot.get("current_state") or ""))
    canonical_job_id = str(snapshot.get("canonical_job_id") or "").strip()
    if not canonical_job_id:
        raise JobStateError("snapshot missing canonical_job_id")
    path = snapshot_path_for_job(canonical_job_id, state_dir=state_dir)
    payload = deepcopy(snapshot)
    payload["updated_at"] = utc_now_iso()
    _write_json_atomic(path, payload)
    return path


def load_snapshot(
    canonical_job_id: str,
    *,
    state_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    path = snapshot_path_for_job(canonical_job_id, state_dir=state_dir)
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else None


def apply_transition(
    snapshot: Dict[str, Any],
    to_state: str,
    *,
    current_owner: Optional[str] = None,
    hard_stop_reason: Optional[str] = None,
    originating_stage: Optional[str] = None,
    failure_classification: Optional[str] = None,
    retryable: Optional[bool] = None,
    manual_intervention_required: Optional[bool] = None,
    attempts_exhausted: Optional[bool] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    next_snapshot = deepcopy(snapshot)
    from_state = str(next_snapshot.get("current_state") or "")
    validate_transition(from_state, to_state)

    timestamp = utc_now_iso()
    next_snapshot["previous_state"] = from_state
    next_snapshot["current_state"] = to_state
    next_snapshot["current_owner"] = current_owner or STATE_OWNER_BY_STATE[to_state]
    next_snapshot["updated_at"] = timestamp
    next_snapshot["state_transitioned_at"] = timestamp

    if to_state == "hard_stopped":
        next_snapshot["hard_stop_reason"] = hard_stop_reason
        next_snapshot["originating_stage"] = originating_stage or from_state
        next_snapshot["failure_classification"] = failure_classification
        next_snapshot["retryable"] = retryable
        next_snapshot["manual_intervention_required"] = manual_intervention_required
        next_snapshot["attempts_exhausted"] = attempts_exhausted
    else:
        if hard_stop_reason is not None:
            next_snapshot["hard_stop_reason"] = hard_stop_reason
        if originating_stage is not None:
            next_snapshot["originating_stage"] = originating_stage
        if failure_classification is not None:
            next_snapshot["failure_classification"] = failure_classification
        if retryable is not None:
            next_snapshot["retryable"] = retryable
        if manual_intervention_required is not None:
            next_snapshot["manual_intervention_required"] = manual_intervention_required
        if attempts_exhausted is not None:
            next_snapshot["attempts_exhausted"] = attempts_exhausted

    if note:
        next_snapshot.setdefault("notes", []).append(str(note))
    return next_snapshot


def _iter_workorder_manifests(root: Path) -> Iterable[Path]:
    return sorted((root / "pipeline" / "kling_workorders").glob("*/daily_workorders.json"))


def _find_workorder_slot(root: Path, slot_id: str) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
    for path in _iter_workorder_manifests(root):
        payload = _read_json(path, {})
        for slot in payload.get("slots", []):
            if isinstance(slot, dict) and slot.get("slot_id") == slot_id:
                return path, slot
    return None, None


def _find_first_glob(root: Path, pattern: str) -> Optional[Path]:
    matches = sorted(root.glob(pattern))
    return matches[0] if matches else None


def _find_matching_receipt(root: Path, slot_id: str) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
    for receipt_path in sorted(root.glob("pipeline/queue/**/*.json.receipt.json")):
        payload = _read_json(receipt_path, {})
        if not isinstance(payload, dict):
            continue
        if _first_non_empty(payload.get("post_id")) == slot_id:
            return receipt_path, payload
    return None, None


def _extract_publish_receipt_platform_media_id(payload: Dict[str, Any]) -> Optional[str]:
    direct = _first_non_empty(payload.get("instagram_media_id"))
    if direct:
        return direct
    publish_response = payload.get("publish_response") or {}
    result = publish_response.get("result") if isinstance(publish_response, dict) else {}
    instagram_result = result.get("instagram_result") if isinstance(result, dict) else {}
    if isinstance(instagram_result, dict):
        return _first_non_empty(instagram_result.get("instagram_media_id"))
    return None


def _qa_explicit_hard_stop(qa_payload: Dict[str, Any]) -> bool:
    haystack = json.dumps(qa_payload, ensure_ascii=False).lower()
    return "hard stop" in haystack or "hard_stop" in haystack


def _derive_state_from_artifacts(collected: Dict[str, Any]) -> tuple[str, str, Optional[str], Optional[str], Optional[bool], Optional[bool], list[str]]:
    notes: list[str] = []
    queue_observed = collected["artifacts"].get("queue_item") is not None
    publish_receipt = collected["artifact_payloads"].get("publish_receipt")
    publish_packet = collected["artifacts"].get("publish_packet") is not None
    qa_payload = collected["artifact_payloads"].get("qa_result")
    result_manifest = collected["artifact_payloads"].get("provider_manifest")
    source_asset = collected["artifacts"].get("generated_source_asset") is not None

    if isinstance(publish_receipt, dict):
        if not collected["artifacts"].get("clean_export_verification_artifact"):
            notes.append(
                "Published artifact observed, but no clean_export_verified evidence exists in the canonical state layer."
            )
        return (
            "published_pending_learning",
            STATE_OWNER_BY_STATE["published_pending_learning"],
            None,
            None,
            None,
            None,
            notes,
        )

    if queue_observed:
        notes.append(
            "Queue artifact observed, but canonical queued state is withheld because clean_export_verified evidence is missing."
        )
        if publish_packet or (isinstance(qa_payload, dict) and qa_payload.get("overall") == "pass"):
            return (
                "clean_export_required",
                STATE_OWNER_BY_STATE["clean_export_required"],
                None,
                None,
                None,
                None,
                notes,
            )

    if publish_packet:
        return (
            "clean_export_required",
            STATE_OWNER_BY_STATE["clean_export_required"],
            None,
            None,
            None,
            None,
            notes,
        )

    if isinstance(qa_payload, dict):
        overall = str(qa_payload.get("overall") or "").lower()
        if overall == "pass":
            return ("approved", STATE_OWNER_BY_STATE["approved"], None, None, None, None, notes)
        if overall == "fail":
            if _qa_explicit_hard_stop(qa_payload):
                failure_reasons = qa_payload.get("failure_reasons") or []
                reason = failure_reasons[0] if isinstance(failure_reasons, list) and failure_reasons else "QA hard stop"
                return (
                    "hard_stopped",
                    STATE_OWNER_BY_STATE["hard_stopped"],
                    str(reason),
                    "qa",
                    False,
                    True,
                    notes,
                )
            return ("qa_required", STATE_OWNER_BY_STATE["qa_required"], None, None, None, None, notes)
        return ("qa_required", STATE_OWNER_BY_STATE["qa_required"], None, None, None, None, notes)

    if isinstance(result_manifest, dict):
        task_status = str(result_manifest.get("task_status") or result_manifest.get("status") or "").lower()
        if task_status in {"queued", "pending", "running", "processing", "submitted", "in_progress"}:
            return ("generating", STATE_OWNER_BY_STATE["generating"], None, None, None, None, notes)
        if task_status in {"failed", "error", "cancelled", "canceled", "rejected"}:
            return (
                "hard_stopped",
                STATE_OWNER_BY_STATE["hard_stopped"],
                f"Provider task status: {task_status}",
                "generation",
                False,
                True,
                notes,
            )
        if task_status in {"succeed", "succeeded", "success", "finished", "complete"}:
            return ("qa_required", STATE_OWNER_BY_STATE["qa_required"], None, None, None, None, notes)

    if source_asset:
        return ("qa_required", STATE_OWNER_BY_STATE["qa_required"], None, None, None, None, notes)
    if collected["artifacts"].get("workorder"):
        return ("planned", STATE_OWNER_BY_STATE["planned"], None, None, None, None, notes)
    return ("planned", STATE_OWNER_BY_STATE["planned"], None, None, None, None, notes)


def derive_snapshot_from_artifacts(
    *,
    root: Optional[Path] = None,
    canonical_job_id: Optional[str] = None,
    source_slot_id: Optional[str] = None,
    output_slot_id: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    platform_media_id: Optional[str] = None,
    workorder_id: Optional[str] = None,
) -> Dict[str, Any]:
    repo_root = (root or ROOT).resolve()
    source_lookup_ids = [
        candidate
        for candidate in (_first_non_empty(source_slot_id), _first_non_empty(output_slot_id))
        if candidate
    ]
    publish_lookup_ids = [
        candidate
        for candidate in (_first_non_empty(output_slot_id), _first_non_empty(source_slot_id))
        if candidate
    ]

    artifacts: Dict[str, Optional[str]] = {key: None for key in ARTIFACT_PATH_KEYS}
    artifact_payloads: Dict[str, Any] = {}
    evidence: set[str] = set()
    attempt_counters: Dict[str, int] = {}

    if source_lookup_ids or publish_lookup_ids:
        workorder_path = None
        workorder_slot = None
        for lookup_slot_id in source_lookup_ids:
            workorder_path, workorder_slot = _find_workorder_slot(repo_root, lookup_slot_id)
            if workorder_path and isinstance(workorder_slot, dict):
                break
        if workorder_path and isinstance(workorder_slot, dict):
            artifacts["workorder"] = _normalize_path(workorder_path, root=repo_root)
            artifact_payloads["workorder"] = workorder_slot
            evidence.add("workorder")
            workorder_id = _first_non_empty(workorder_id, workorder_slot.get("workorder_id"))
            source_slot_id = _first_non_empty(source_slot_id, workorder_slot.get("slot_id"))
            output_slot_id = _first_non_empty(output_slot_id, workorder_slot.get("slot_id"))

            expected_assets = workorder_slot.get("expected_assets") or {}
            generated_source_asset = _first_non_empty(
                expected_assets.get("final_photo_path"),
                expected_assets.get("final_video_path"),
                expected_assets.get("seed_image_path"),
            )
            if generated_source_asset:
                asset_path = Path(str(generated_source_asset))
                artifacts["generated_source_asset"] = _normalize_path(asset_path, root=repo_root)

        qa_path = None
        for lookup_slot_id in source_lookup_ids:
            qa_path = _find_first_glob(repo_root, f"pipeline/asset_review/lena/*/{lookup_slot_id}_qa.json")
            if qa_path:
                break
        if qa_path:
            qa_payload = _read_json(qa_path, {})
            artifacts["qa_result"] = _normalize_path(qa_path, root=repo_root)
            artifact_payloads["qa_result"] = qa_payload
            evidence.add("qa_result")

        publish_packet_path = None
        for lookup_slot_id in publish_lookup_ids:
            publish_packet_path = _find_first_glob(repo_root, f"pipeline/publish_packets/lena/**/*{lookup_slot_id}*.md")
            if publish_packet_path:
                break
        if publish_packet_path:
            artifacts["publish_packet"] = _normalize_path(publish_packet_path, root=repo_root)
            evidence.add("publish_packet")

        for lookup_slot_id in publish_lookup_ids:
            queue_path = None
            for queue_pattern in (
                f"pipeline/queue/{lookup_slot_id}.json",
                f"pipeline/queue/published/{lookup_slot_id}.json",
                f"pipeline/queue/failed/{lookup_slot_id}*.json",
            ):
                queue_path = _find_first_glob(repo_root, queue_pattern)
                if queue_path:
                    break
            if queue_path:
                queue_payload = _read_json(queue_path, {})
                artifacts["queue_item"] = _normalize_path(queue_path, root=repo_root)
                artifact_payloads["queue_item"] = queue_payload
                evidence.add("queue_item")
                if isinstance(queue_payload, dict):
                    attempts = queue_payload.get("publish_attempts")
                    if isinstance(attempts, int):
                        attempt_counters["queue_publish"] = attempts
                    source_slot_id = _first_non_empty(source_slot_id, queue_payload.get("slot_id"))
                    output_slot_id = _first_non_empty(output_slot_id, queue_payload.get("post_id"))
                    provider_job_id = _first_non_empty(
                        provider_job_id,
                        (queue_payload.get("metadata") or {}).get("source_task_id"),
                    )
                break

        receipt_path = None
        receipt_payload = None
        for lookup_slot_id in publish_lookup_ids:
            receipt_path, receipt_payload = _find_matching_receipt(repo_root, lookup_slot_id)
            if receipt_path and isinstance(receipt_payload, dict):
                break
        if receipt_path and isinstance(receipt_payload, dict):
            artifacts["publish_receipt"] = _normalize_path(receipt_path, root=repo_root)
            artifact_payloads["publish_receipt"] = receipt_payload
            evidence.add("publish_receipt")
            output_slot_id = _first_non_empty(output_slot_id, receipt_payload.get("post_id"))
            platform_media_id = _first_non_empty(
                platform_media_id,
                _extract_publish_receipt_platform_media_id(receipt_payload),
            )

        for lookup_slot_id in source_lookup_ids:
            result_path = None
            for result_pattern in (
                f"pipeline/kling_debug/**/{lookup_slot_id}/result_manifest.json",
                f"pipeline/higgsfield_debug/**/{lookup_slot_id}/result_manifest.json",
            ):
                result_path = _find_first_glob(repo_root, result_pattern)
                if result_path:
                    break
            if result_path:
                result_payload = _read_json(result_path, {})
                artifacts["provider_manifest"] = _normalize_path(result_path, root=repo_root)
                artifact_payloads["provider_manifest"] = result_payload
                evidence.add("provider_manifest")
                if isinstance(result_payload, dict):
                    provider_job_id = _first_non_empty(provider_job_id, result_payload.get("task_id"))
                    saved_image_paths = result_payload.get("saved_image_paths") or []
                    if saved_image_paths and not artifacts["generated_source_asset"]:
                        artifacts["generated_source_asset"] = _normalize_path(
                            Path(str(saved_image_paths[0])),
                            root=repo_root,
                        )
                break

    learning_state_path = repo_root / "pipeline" / "state" / "lena_post_outcome_learning_state_v1.json"
    if learning_state_path.exists():
        artifacts["learning_state"] = _normalize_path(learning_state_path, root=repo_root)

    derived_state, owner, hard_stop_reason, originating_stage, retryable, manual_intervention_required, notes = _derive_state_from_artifacts(
        {"artifacts": artifacts, "artifact_payloads": artifact_payloads}
    )

    final_job_id = canonical_job_id or derive_canonical_job_id(
        source_slot_id=source_slot_id,
        output_slot_id=output_slot_id,
        provider_job_id=provider_job_id,
        platform_media_id=platform_media_id,
        workorder_id=workorder_id,
    )

    return create_snapshot(
        canonical_job_id=final_job_id,
        source_slot_id=source_slot_id,
        output_slot_id=output_slot_id,
        provider_job_id=provider_job_id,
        platform_media_id=platform_media_id,
        workorder_id=workorder_id,
        current_state=derived_state,
        current_owner=owner,
        attempt_counters_by_stage=attempt_counters,
        hard_stop_reason=hard_stop_reason,
        originating_stage=originating_stage,
        failure_classification="artifact_derived" if derived_state == "hard_stopped" else None,
        retryable=retryable,
        manual_intervention_required=manual_intervention_required,
        artifact_paths=artifacts,
        artifact_evidence=sorted(evidence),
        notes=notes,
        state_source="derived",
    )
