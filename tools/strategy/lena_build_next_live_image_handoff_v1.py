from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.influencer_nodes.lena import autonomy_ladder
from pipeline.identity import lena_higgsfield_soul_cinema_contract_v1 as soul_cinema_contract
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_pose_provenance_v1 as pose_provenance
from tools.strategy import lena_reconciliation_contract_v1 as reconciliation_contract

NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
CONTENT_PACKETS = ROOT / "pipeline" / "strategy" / "lena" / "content_packets"
PRE_GENERATION_CANDIDATES = ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates"

REPO_EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
EXECUTION_OWNER = "claude"
PROVIDER = "higgsfield"
EXECUTOR_TYPE = "higgsfield_cli"
MEDIA_CONTENT_TYPE = "image"
SLOT_MEDIA_TYPE = "photo"
MODEL = soul_cinema_contract.MODEL
ASPECT_RATIO = soul_cinema_contract.ASPECT_RATIO
NEGATIVE_PROMPT_ENABLED = False
DEFAULT_CUSTOM_REFERENCE_ID = soul_cinema_contract.CUSTOM_REFERENCE_ID
SOUL_NAME = "Lena"
SOUL_TYPE = "Soul 2.0"
REVIEWED_LANE_BINDING_ALIASES = {
    "readypack lane": {"parking_garage_flash"},
    "parking_garage_flash": {"readypack lane"},
}
PROMPT_FAMILY_CANDIDATE_SELECTION = "prompt_library_candidate"
PROMPT_FAMILY_PROVIDER_EXECUTION = "compact_provider_prompt"


class HandoffBuildError(SystemExit):
    """Fail-closed builder error."""


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dated_path(base: Path, date_str: str, filename: str) -> Path:
    return base / date_str / filename


def next_step_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_generation_step_{date_str}.json")


def queue_dry_run_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_autonomous_generation_queue_dryrun_{date_str}.json")


def handoff_json_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_live_image_handoff_{date_str}.json")


def handoff_markdown_path(date_str: str) -> Path:
    return dated_path(NEXT_ACTIONS, date_str, f"lena_next_live_image_handoff_{date_str}.md")


def content_packet_path(date_str: str, recipe_id: str) -> Path:
    return dated_path(
        CONTENT_PACKETS,
        date_str,
        f"lena_content_packet_dryrun_{date_str}_{recipe_id}.json",
    )


def canonical_slot_id(date_str: str, recipe_id: str) -> str:
    return f"higgsfield-{date_str.replace('-', '')}-{recipe_id}-photo"


def learning_path_from_recommendation(recommendation: dict) -> Path:
    return Path(str(recommendation.get("learning_artifact_path", "")).strip())


def selected_candidate_directory(date_str: str) -> Path:
    return PRE_GENERATION_CANDIDATES / date_str


def load_selected_candidate_report(date_str: str) -> tuple[Path, dict]:
    base = selected_candidate_directory(date_str)
    if not base.is_dir():
        raise HandoffBuildError(
            "[ABORT] missing_selected_candidate: "
            f"missing selected candidate directory: {base}"
        )
    selected: list[tuple[str, Path, dict]] = []
    for path in sorted(base.glob("lena_pre_generation_candidate_*.json")):
        try:
            report = read_json(path)
        except Exception:
            continue
        if (
            report.get("schema_version") == "lena_pre_generation_candidate_gate_v1"
            and report.get("candidate_status") == "selected"
        ):
            selected.append((str(report.get("generated_at_utc", "")), path, report))
    if not selected:
        raise HandoffBuildError(
            "[ABORT] missing_selected_candidate: "
            f"no selected candidate artifact found for {date_str}"
        )
    if len(selected) != 1:
        selected_paths = ", ".join(str(path) for _, path, _ in sorted(selected, key=lambda item: (item[0], item[1].name)))
        raise HandoffBuildError(
            "[ABORT] ambiguous_selected_candidate: "
            f"multiple selected candidate artifacts found for {date_str}: {selected_paths}"
        )
    _, path, report = selected[0]
    return path, report


def load_reconciled_selected_candidate_report(date_str: str, reconciliation_artifact_path: str) -> tuple[Path, dict]:
    _reconciliation_path, reconciliation_report, _reconciliation_sha256 = reconciliation_contract.load_reconciliation_report(
        reconciliation_artifact_path,
        date_str=date_str,
    )
    source_artifacts = reconciliation_report.get("source_artifacts", {})
    selected_source = source_artifacts.get("selected_candidate", {}) if isinstance(source_artifacts, dict) else {}
    selected_path_value = str(selected_source.get("source_artifact_path", "")).strip() if isinstance(selected_source, dict) else ""
    _require(
        bool(selected_path_value),
        "reconciliation_selected_candidate_missing",
        "reconciliation selected candidate source path is missing",
    )
    selected_path = Path(selected_path_value)
    if not selected_path.is_absolute():
        selected_path = ROOT / selected_path
    selected_path = selected_path.resolve()
    _require(
        selected_path.is_relative_to(ROOT.resolve()),
        "selected_candidate_path_escape",
        f"reconciliation selected candidate path escapes repo root: {selected_path}",
    )
    _require(
        selected_path.is_file(),
        "missing_selected_candidate",
        f"selected candidate artifact from reconciliation does not exist: {selected_path}",
    )
    selected_candidate = read_json(selected_path)
    _require(
        selected_candidate.get("schema_version") == "lena_pre_generation_candidate_gate_v1",
        "selected_candidate_schema_invalid",
        "reconciled selected candidate artifact has invalid schema_version",
    )
    _require(
        selected_candidate.get("candidate_status") == "selected",
        "selected_candidate_status_invalid",
        "reconciled selected candidate artifact is not selected",
    )
    expected_sha = str(selected_source.get("source_artifact_sha256", "")).strip() if isinstance(selected_source, dict) else ""
    _require(
        sha256_file(selected_path) == expected_sha,
        "reconciliation_source_drift",
        "reconciliation selected candidate source sha does not match artifact bytes",
    )
    return selected_path, selected_candidate


def repo_relative_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def handoff_executor_command(handoff_artifact_path: str, *, live: bool = False) -> str:
    parts = [
        "python",
        REPO_EXECUTOR_PATH,
        "--handoff-artifact",
        handoff_artifact_path,
    ]
    if live:
        parts.append("--live")
    return " ".join(parts)


def handoff_executor_argv(handoff_artifact_path: str, *, live: bool = False) -> list[str]:
    argv = [
        "python",
        REPO_EXECUTOR_PATH,
        "--handoff-artifact",
        handoff_artifact_path,
    ]
    if live:
        argv.append("--live")
    return argv


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise HandoffBuildError(f"[ABORT] {code}: {message}")


def _handoff_cross_field_binding_split_brain_error(
    *,
    slot_id: str,
    candidate_id: str,
    source_selected_candidate_artifact_path: str,
    source_selected_candidate_artifact_sha256: str,
    selected_candidate_prompt_sha256: str,
    selected_prompt_input_prompt_sha256: str,
    structured_executor_inputs_selected_prompt_sha256: str,
    selected_candidate_lane: str,
    selected_prompt_input_lane: str,
    dual_binding_contract: dict[str, Any] | None = None,
) -> tuple[str, str] | None:
    binding_context = {
        "slot_id": slot_id,
        "candidate_id": candidate_id,
        "source_selected_candidate_artifact_path": source_selected_candidate_artifact_path,
        "source_selected_candidate_artifact_sha256": source_selected_candidate_artifact_sha256,
        "selected_candidate_prompt_sha256": selected_candidate_prompt_sha256,
        "selected_prompt_input_prompt_sha256": selected_prompt_input_prompt_sha256,
        "structured_executor_inputs_selected_prompt_sha256": structured_executor_inputs_selected_prompt_sha256,
        "selected_candidate_lane": selected_candidate_lane,
        "selected_prompt_input_lane": selected_prompt_input_lane,
    }
    if isinstance(dual_binding_contract, dict):
        binding_context["dual_binding_contract"] = dual_binding_contract
        candidate_binding = dual_binding_contract.get("candidate_selection_binding")
        provider_binding = dual_binding_contract.get("provider_execution_binding")
        linkage = dual_binding_contract.get("binding_linkage")
        if not isinstance(candidate_binding, dict) or not isinstance(provider_binding, dict) or not isinstance(linkage, dict):
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)

        required_candidate_keys = (
            "selected_candidate_artifact_path",
            "selected_candidate_artifact_sha256",
            "candidate_id",
            "slot_id",
            "recipe_id",
            "candidate_prompt_sha256",
            "candidate_lane",
            "source_prompt_family",
        )
        required_provider_keys = (
            "content_packet_artifact_path",
            "content_packet_artifact_sha256",
            "recipe_id",
            "slot_id",
            "provider_prompt_sha256",
            "provider_lane",
            "source_prompt_family",
            "provider",
        )
        required_linkage_keys = (
            "recommendation_artifact_path",
            "recommendation_artifact_sha256",
            "queue_artifact_path",
            "queue_artifact_sha256",
            "selected_candidate_artifact_path",
            "selected_candidate_artifact_sha256",
            "content_packet_artifact_path",
            "content_packet_artifact_sha256",
            "recipe_id",
            "slot_id",
            "candidate_id",
            "outfit_id",
            "environment_id",
            "candidate_lane",
            "provider_lane",
            "candidate_prompt_family",
            "provider_prompt_family",
            "prompt_family_relationship",
        )
        if any(not str(candidate_binding.get(key, "")).strip() for key in required_candidate_keys):
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if any(not str(provider_binding.get(key, "")).strip() for key in required_provider_keys):
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if any(not str(linkage.get(key, "")).strip() for key in required_linkage_keys):
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)

        if candidate_binding.get("selected_candidate_artifact_path") != binding_context["source_selected_candidate_artifact_path"]:
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if candidate_binding.get("selected_candidate_artifact_sha256") != binding_context["source_selected_candidate_artifact_sha256"]:
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if provider_binding.get("content_packet_artifact_path") != linkage.get("content_packet_artifact_path"):
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if provider_binding.get("content_packet_artifact_sha256") != linkage.get("content_packet_artifact_sha256"):
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if candidate_binding.get("candidate_lane") != linkage.get("candidate_lane") or provider_binding.get("provider_lane") != linkage.get("provider_lane"):
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if candidate_binding.get("candidate_id") != candidate_id or candidate_binding.get("slot_id") != slot_id:
            return "handoff_dual_binding_slot_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if linkage.get("candidate_id") != candidate_id:
            return "handoff_dual_binding_slot_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if candidate_binding.get("recipe_id") != linkage.get("recipe_id") or provider_binding.get("recipe_id") != linkage.get("recipe_id"):
            return "handoff_dual_binding_recipe_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if provider_binding.get("slot_id") != linkage.get("slot_id") or candidate_binding.get("slot_id") != linkage.get("slot_id"):
            return "handoff_dual_binding_slot_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if linkage.get("selected_candidate_artifact_path") != candidate_binding.get("selected_candidate_artifact_path"):
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if linkage.get("selected_candidate_artifact_sha256") != candidate_binding.get("selected_candidate_artifact_sha256"):
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if linkage.get("content_packet_artifact_sha256") != provider_binding.get("content_packet_artifact_sha256"):
            return "handoff_dual_binding_artifact_sha_mismatch", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if linkage.get("candidate_prompt_family") != PROMPT_FAMILY_CANDIDATE_SELECTION or linkage.get("provider_prompt_family") != PROMPT_FAMILY_PROVIDER_EXECUTION:
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        if candidate_binding.get("source_prompt_family") != PROMPT_FAMILY_CANDIDATE_SELECTION or provider_binding.get("source_prompt_family") != PROMPT_FAMILY_PROVIDER_EXECUTION:
            return "handoff_dual_binding_linkage_missing", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
        return None
    prompt_values = {
        value
        for value in (
            selected_candidate_prompt_sha256,
            selected_prompt_input_prompt_sha256,
            structured_executor_inputs_selected_prompt_sha256,
        )
        if value
    }
    if len(prompt_values) > 1:
        return "handoff_prompt_binding_split_brain", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
    candidate_lane = selected_candidate_lane.strip()
    prompt_input_lane = selected_prompt_input_lane.strip()
    if candidate_lane and prompt_input_lane:
        if candidate_lane != prompt_input_lane and prompt_input_lane not in REVIEWED_LANE_BINDING_ALIASES.get(candidate_lane, set()):
            return "handoff_lane_binding_split_brain", json.dumps(binding_context, indent=2, ensure_ascii=True, sort_keys=True)
    return None


def load_report(
    path: Path,
    *,
    expected_report_type: str,
    expected_date: str,
    require_date: bool = True,
) -> dict:
    _require(path.is_file(), "missing_artifact", f"missing required artifact: {path}")
    try:
        report = read_json(path)
    except Exception as exc:  # pragma: no cover
        raise HandoffBuildError(f"[ABORT] unreadable_artifact: {path}: {exc}") from exc
    _require(
        report.get("report_type") == expected_report_type,
        "wrong_report_type",
        f"{path} has report_type {report.get('report_type')!r}, expected {expected_report_type!r}",
    )
    report_date = str(report.get("date", "")).strip()
    if require_date or report_date:
        _require(
            report_date == expected_date,
            "date_mismatch",
            f"{path} has date {report_date!r}, expected {expected_date!r}",
        )
    return report


def load_content_packet_report(path: Path, expected_date: str, expected_recipe_id: str) -> dict:
    _require(path.is_file(), "missing_artifact", f"missing required artifact: {path}")
    try:
        report = read_json(path)
    except Exception as exc:  # pragma: no cover
        raise HandoffBuildError(f"[ABORT] unreadable_artifact: {path}: {exc}") from exc
    _require(
        report.get("report_type") == "lena_content_packet_dryrun",
        "wrong_report_type",
        f"{path} has report_type {report.get('report_type')!r}, expected 'lena_content_packet_dryrun'",
    )
    _require(
        str(report.get("generated_date", "")).strip() == expected_date,
        "packet_date_mismatch",
        f"{path} has generated_date {report.get('generated_date')!r}, expected {expected_date!r}",
    )
    _require(
        str(report.get("recipe_id", "")).strip() == expected_recipe_id,
        "packet_recipe_mismatch",
        f"{path} has recipe_id {report.get('recipe_id')!r}, expected {expected_recipe_id!r}",
    )
    prompt = str(report.get("compact_provider_prompt_preview", "")).strip()
    _require(
        bool(prompt),
        "packet_prompt_missing",
        f"{path} does not contain a compact_provider_prompt_preview",
    )
    return report


def load_learning_report(recommendation: dict, expected_date: str) -> tuple[Path, dict]:
    learning_path = learning_path_from_recommendation(recommendation)
    _require(
        learning_path.is_file(),
        "missing_learning_artifact",
        f"recommendation references a missing learning artifact: {learning_path}",
    )
    learning = load_report(
        learning_path,
        expected_report_type="lena_post_outcome_learning_state",
        expected_date=expected_date,
    )
    return learning_path, learning


def load_queue_report(date_str: str) -> tuple[Path, dict]:
    path = queue_dry_run_path(date_str)
    queue_report = load_report(
        path,
        expected_report_type="lena_autonomous_generation_queue_dryrun",
        expected_date=date_str,
        require_date=False,
    )
    queue_slots = queue_report.get("queue_slots", [])
    _require(
        isinstance(queue_slots, list) and queue_slots,
        "empty_queue_report",
        f"{path} has no queue_slots",
    )
    head = queue_slots[0]
    _require(
        isinstance(head, dict),
        "queue_head_invalid",
        f"{path} queue head is not a JSON object",
    )
    return path, queue_report


def build_handoff(
    date_str: str,
    reconciliation_artifact_path: str,
    reconciliation_decision_artifact_path: str | None = None,
) -> dict:
    try:
        autonomy_ladder.assert_allowed(
            "lena_build_next_live_image_handoff_v1",
            level=0,
            action="dry-run handoff construction",
        )
    except autonomy_ladder.AutonomyLadderError as exc:
        raise HandoffBuildError(f"[ABORT] {exc.code}: {exc.detail}") from exc
    try:
        generation_reference = soul_cinema_contract.load_generation_reference_binding()
    except soul_cinema_contract.SoulCinemaContractError as exc:
        raise HandoffBuildError(f"[ABORT] {exc.code}: {exc.detail}") from exc

    recommendation_path = next_step_path(date_str)
    recommendation = load_report(
        recommendation_path,
        expected_report_type="lena_next_generation_step",
        expected_date=date_str,
    )
    recommendation_body = recommendation.get("recommendation", {})
    _require(
        isinstance(recommendation_body, dict),
        "missing_recommendation_body",
        f"{recommendation_path} has no recommendation object",
    )

    learning_path, learning = load_learning_report(recommendation, date_str)
    queue_path, queue_report = load_queue_report(date_str)
    selected_candidate_path_value, selected_candidate = load_reconciled_selected_candidate_report(
        date_str,
        reconciliation_artifact_path,
    )
    selected_candidate_body = selected_candidate.get("candidate", {})
    if not isinstance(selected_candidate_body, dict):
        selected_candidate_body = {}
    selected_candidate_id = str(selected_candidate_body.get("candidate_id", "")).strip()
    selected_candidate_slot_id = str(selected_candidate_body.get("slot_id", "")).strip()
    selected_candidate_recipe_id = str(selected_candidate_body.get("recipe_id", "")).strip()
    selected_candidate_hook_id = str(selected_candidate_body.get("hook_id", "")).strip()
    selected_candidate_prompt_sha256 = str(selected_candidate_body.get("prompt_sha256", "")).strip()

    learning_summary = learning.get("metrics_resolution_summary", {})
    _require(
        isinstance(learning_summary, dict),
        "missing_learning_summary",
        f"{learning_path} has no metrics_resolution_summary object",
    )
    _require(
        learning_summary.get("learning_status") == recommendation.get("learning_status"),
        "learning_status_mismatch",
        "recommendation learning_status does not match the authoritative learning artifact",
    )
    _require(
        int(recommendation.get("learning_published_post_count", -1))
        == int(learning.get("published_post_count", -1)),
        "learning_published_post_count_mismatch",
        "recommendation published count does not match the learning artifact",
    )
    _require(
        int(recommendation.get("learning_pending_metrics_count", -1))
        == len(learning.get("pending_metrics_posts", [])),
        "learning_pending_metrics_count_mismatch",
        "recommendation pending count does not match the learning artifact",
    )
    _require(
        int(recommendation.get("learning_stale_pending_metrics_count", -1))
        == len(learning.get("stale_pending_metrics_posts", [])),
        "learning_stale_pending_metrics_count_mismatch",
        "recommendation stale count does not match the learning artifact",
    )
    _require(
        recommendation.get("learning_resolution_state_summary", {}) == learning_summary,
        "learning_resolution_summary_mismatch",
        "recommendation learning summary does not match the learning artifact",
    )
    expected_follow_up = {
        "current": "no_follow_up_required",
        "usable_but_incomplete": "complete_missing_metrics_or_refresh_learning",
        "stale_unresolved": "refresh_or_resolve_stale_unresolved_posts",
        "manual_or_future_capability_required": "manual_or_future_capability_resolution_required",
        "unavailable": "rebuild_and_pass_an_explicit_learning_artifact",
    }.get(str(recommendation.get("learning_status", "")).strip(), "rebuild_and_pass_an_explicit_learning_artifact")
    _require(
        recommendation.get("learning_required_follow_up_action", "") == expected_follow_up,
        "learning_follow_up_mismatch",
        "recommendation follow-up action does not match the learning status",
    )

    queue_slots = queue_report.get("queue_slots", [])
    queue_head = queue_slots[0]
    _require(
        queue_head.get("recipe_id") == recommendation_body.get("recommended_recipe_id"),
        "queue_head_mismatch",
        "queue head recipe does not match the recommendation",
    )
    proof_lane_lock = queue_report.get("proof_lane_lock", {})
    if queue_report.get("proof_lane_lock_active"):
        _require(
            proof_lane_lock.get("recipe_id") == queue_head.get("recipe_id"),
            "proof_lane_lock_mismatch",
            "active proof lane lock does not match queue head",
        )

    reconciliation_provenance = reconciliation_contract.build_handoff_reconciliation_provenance(
        date_str=date_str,
        recommendation_recipe_id=str(recommendation_body.get("recommended_recipe_id", "")).strip(),
        selected_candidate_path=selected_candidate_path_value,
        selected_candidate_report=selected_candidate,
        selected_candidate_body=selected_candidate_body,
        reconciliation_artifact_path=reconciliation_artifact_path,
        reconciliation_decision_artifact_path=reconciliation_decision_artifact_path,
    )
    final_reconciled = reconciliation_provenance["final_candidate"]
    recipe_id = str(final_reconciled["recipe_id"]).strip()
    slot_id = str(final_reconciled["slot_id"]).strip()
    packet_path = content_packet_path(date_str, recipe_id)
    packet = load_content_packet_report(packet_path, date_str, recipe_id)
    try:
        pose_binding = pose_provenance.build_candidate_pose_provenance(
            selected_candidate_path_value,
            root=ROOT,
        )
        expression_binding = pose_provenance.build_candidate_expression_provenance(
            selected_candidate_path_value,
            root=ROOT,
        )
        bound_packet = packet_builder.rebuild_packet_from_authoritative_sources(
            packet,
            pose_binding=pose_binding,
            expression_binding=expression_binding,
        )
        prompt_text = str(bound_packet.get("compact_provider_prompt_preview", "")).strip()
        pose_provenance.require_pose_bound_prompt(prompt_text, pose_binding)
        pose_provenance.require_expression_bound_prompt(
            prompt_text,
            expression_binding,
        )
    except (pose_provenance.PoseProvenanceError, SystemExit) as exc:
        raise HandoffBuildError(f"[ABORT] pose_provenance_invalid: {exc}") from exc
    prompt_sha256 = sha256_bytes(prompt_text.encode("utf-8"))
    pose_bound_packet_sha256 = sha256_bytes(
        json.dumps(
            bound_packet,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    )
    pose_fingerprint = pose_binding["pose_provenance_fingerprint_sha256"]
    expression_fingerprint = expression_binding[
        "expression_provenance_fingerprint_sha256"
    ]
    candidate_selection_binding = {
        "selected_candidate_artifact_path": repo_relative_path(selected_candidate_path_value),
        "selected_candidate_artifact_sha256": sha256_file(selected_candidate_path_value),
        "candidate_id": selected_candidate_id,
        "slot_id": selected_candidate_slot_id,
        "recipe_id": selected_candidate_recipe_id,
        "candidate_prompt_sha256": selected_candidate_prompt_sha256,
        "candidate_lane": str(selected_candidate_body.get("lane", "")).strip(),
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_body_language_label": pose_binding["pose_body_language_label"],
        "pose_provenance_fingerprint_sha256": pose_fingerprint,
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_gaze_label": expression_binding["expression_gaze_label"],
        "expression_provenance_fingerprint_sha256": expression_fingerprint,
        "source_prompt_family": PROMPT_FAMILY_CANDIDATE_SELECTION,
    }
    provider_execution_binding = {
        "content_packet_artifact_path": repo_relative_path(packet_path),
        "content_packet_artifact_sha256": sha256_file(packet_path),
        "recipe_id": recipe_id,
        "slot_id": slot_id,
        "provider_prompt_sha256": prompt_sha256,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha256,
        "pose_provenance_fingerprint_sha256": pose_fingerprint,
        "expression_bound_content_packet_sha256": pose_bound_packet_sha256,
        "expression_provenance_fingerprint_sha256": expression_fingerprint,
        "provider_lane": str(packet.get("scene_type", "")).strip(),
        "source_prompt_family": PROMPT_FAMILY_PROVIDER_EXECUTION,
        "provider": PROVIDER,
        "model": MODEL,
        "generation_reference": generation_reference,
    }
    binding_linkage = {
        "recommendation_artifact_path": repo_relative_path(recommendation_path),
        "recommendation_artifact_sha256": sha256_file(recommendation_path),
        "queue_artifact_path": repo_relative_path(queue_path),
        "queue_artifact_sha256": sha256_file(queue_path),
        "selected_candidate_artifact_path": repo_relative_path(selected_candidate_path_value),
        "selected_candidate_artifact_sha256": sha256_file(selected_candidate_path_value),
        "content_packet_artifact_path": repo_relative_path(packet_path),
        "content_packet_artifact_sha256": sha256_file(packet_path),
        "recipe_id": recipe_id,
        "slot_id": slot_id,
        "candidate_id": selected_candidate_id,
        "outfit_id": str(packet.get("wardrobe_outfit_id", "")).strip(),
        "environment_id": str(packet.get("environment_id", "")).strip(),
        "candidate_lane": str(selected_candidate_body.get("lane", "")).strip(),
        "provider_lane": str(packet.get("scene_type", "")).strip(),
        "candidate_prompt_family": PROMPT_FAMILY_CANDIDATE_SELECTION,
        "provider_prompt_family": PROMPT_FAMILY_PROVIDER_EXECUTION,
        "pose_body_language_id": pose_binding["pose_body_language_id"],
        "pose_provenance_fingerprint_sha256": pose_fingerprint,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha256,
        "expression_gaze_id": expression_binding["expression_gaze_id"],
        "expression_provenance_fingerprint_sha256": expression_fingerprint,
        "expression_bound_content_packet_sha256": pose_bound_packet_sha256,
        "prompt_family_relationship": "candidate prompt family and provider prompt family are intentionally distinct for the same recipe/slot chain",
    }

    split_brain_error = _handoff_cross_field_binding_split_brain_error(
        slot_id=slot_id,
        candidate_id=selected_candidate_id,
        source_selected_candidate_artifact_path=repo_relative_path(selected_candidate_path_value),
        source_selected_candidate_artifact_sha256=sha256_file(selected_candidate_path_value),
        selected_candidate_prompt_sha256=selected_candidate_prompt_sha256,
        selected_prompt_input_prompt_sha256=prompt_sha256,
        structured_executor_inputs_selected_prompt_sha256=prompt_sha256,
        selected_candidate_lane=str(selected_candidate_body.get("lane", "")).strip(),
        selected_prompt_input_lane=str(packet.get("scene_type", "")).strip(),
        dual_binding_contract={
            "candidate_selection_binding": candidate_selection_binding,
            "provider_execution_binding": provider_execution_binding,
            "binding_linkage": binding_linkage,
        },
    )
    if split_brain_error is not None:
        code, detail = split_brain_error
        _require(False, code, detail)

    _require(
        str(packet.get("environment_id", "")).strip() == str(queue_head.get("environment_used", "")).strip(),
        "packet_environment_mismatch",
        "queue head environment does not match the selected content packet",
    )
    _require(
        str(packet.get("wardrobe_outfit_id", "")).strip() == str(queue_head.get("outfit_used", "")).strip(),
        "packet_outfit_mismatch",
        "queue head outfit does not match the selected content packet",
    )
    _require(
        packet.get("provider_prompt_contract", {}).get("provider_route") == "higgsfield_forward_no_live",
        "packet_provider_route_mismatch",
        "selected content packet is not bound to the Higgsfield-forward no-live route",
    )
    _require(
        packet.get("provider_prompt_contract", {}).get("live_authority") is False,
        "packet_live_authority_invalid",
        "selected content packet must remain no-live authority only",
    )

    handoff_json_rel_path = repo_relative_path(handoff_json_path(date_str))
    handoff_md_rel_path = repo_relative_path(handoff_markdown_path(date_str))
    dry_run_command = handoff_executor_command(handoff_json_rel_path)
    live_command = handoff_executor_command(handoff_json_rel_path, live=True)
    report = {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "date": date_str,
        "created_at": iso_now(),
        "execution_owner": EXECUTION_OWNER,
        "provider": PROVIDER,
        "executor_type": EXECUTOR_TYPE,
        "generation_reference": generation_reference,
        "repo_executor_path": REPO_EXECUTOR_PATH,
        "media_content_type": MEDIA_CONTENT_TYPE,
        "slot_media_type": SLOT_MEDIA_TYPE,
        "expected_handoff_artifact_path": handoff_json_rel_path,
        "expected_handoff_markdown_path": handoff_md_rel_path,
        "selected_slot_id": slot_id,
        "selected_recipe_id": recipe_id,
        "selected_candidate": {
            "artifact_path": repo_relative_path(selected_candidate_path_value),
            "artifact_sha256": sha256_file(selected_candidate_path_value),
            "candidate_id": selected_candidate_id,
            "slot_id": selected_candidate_slot_id,
            "recipe_id": selected_candidate_recipe_id,
            "prompt_sha256": selected_candidate_prompt_sha256,
            "source_prompt_family": PROMPT_FAMILY_CANDIDATE_SELECTION,
            "schema_version": selected_candidate.get("schema_version", ""),
            "candidate_status": selected_candidate.get("candidate_status", ""),
            "lane": str(selected_candidate_body.get("lane") or packet.get("scene_type") or ""),
            "wardrobe_outfit_id": str(selected_candidate_body.get("wardrobe_outfit_id") or packet.get("wardrobe_outfit_id") or ""),
            "effective_wardrobe_silhouette_class": str(selected_candidate_body.get("visual_style") or ""),
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_body_language_label": pose_binding["pose_body_language_label"],
            "expression_gaze_id": expression_binding["expression_gaze_id"],
            "expression_gaze_label": expression_binding["expression_gaze_label"],
        },
        "candidate_selection_binding": candidate_selection_binding,
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_sha256": pose_bound_packet_sha256,
        "expression_provenance": expression_binding,
        "expression_bound_content_packet_sha256": pose_bound_packet_sha256,
        "selected_lane": packet.get("scene_type", ""),
        "selected_hook_id": selected_candidate_hook_id,
        "selected_hook_text": packet.get("hook_text", ""),
        "selected_caption_seed": packet.get("caption_draft", ""),
        "source_reconciliation_artifact_path": reconciliation_provenance["reconciliation"]["source_artifact_path"],
        "source_reconciliation_artifact_sha256": reconciliation_provenance["reconciliation"]["source_artifact_sha256"],
        "source_reconciliation_schema_version": reconciliation_provenance["reconciliation"]["schema_version"],
        "source_reconciliation_report_type": reconciliation_provenance["reconciliation"]["report_type"],
        "source_reconciliation_status": reconciliation_provenance["reconciliation"]["reconciliation_status"],
        "source_reconciliation_operator_review_required": reconciliation_provenance["reconciliation"]["operator_review_required"],
        "source_reconciliation_divergence_status": reconciliation_provenance["reconciliation"]["divergence_status"],
        "source_reconciliation_resolution_policy": reconciliation_provenance["reconciliation"]["resolution_policy"],
        "source_reconciliation_exact_next_allowed_action": reconciliation_provenance["reconciliation"]["exact_next_allowed_action"],
        "source_reconciliation_decision_artifact_path": (
            reconciliation_provenance["decision"]["source_artifact_path"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_artifact_sha256": (
            reconciliation_provenance["decision"]["source_artifact_sha256"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_id": (
            reconciliation_provenance["decision"]["decision_id"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_operator_id": (
            reconciliation_provenance["decision"]["operator_id"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_expires_at_utc": (
            reconciliation_provenance["decision"]["expires_at_utc"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_authority_scope": (
            reconciliation_provenance["decision"]["authority_scope"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_live_generation_authorized": (
            reconciliation_provenance["decision"]["live_generation_authorized"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_publishing_authorized": (
            reconciliation_provenance["decision"]["publishing_authorized"] if reconciliation_provenance["decision"] else None
        ),
        "source_reconciliation_decision_next_allowed_action": (
            reconciliation_provenance["decision"]["next_allowed_action"] if reconciliation_provenance["decision"] else None
        ),
        "reconciled_candidate": reconciliation_provenance["final_candidate"],
        "source_recommendation_artifact_path": repo_relative_path(recommendation_path),
        "source_recommendation_artifact_sha256": sha256_file(recommendation_path),
        "source_learning_artifact_path": repo_relative_path(learning_path),
        "source_learning_artifact_sha256": sha256_file(learning_path),
        "source_queue_dry_run_artifact_path": repo_relative_path(queue_path),
        "source_queue_dry_run_artifact_sha256": sha256_file(queue_path),
        "source_selected_candidate_artifact_path": repo_relative_path(selected_candidate_path_value),
        "source_selected_candidate_artifact_sha256": sha256_file(selected_candidate_path_value),
        "selected_prompt_input_artifact_path": repo_relative_path(packet_path),
        "selected_prompt_input_artifact_sha256": sha256_file(packet_path),
        "selected_prompt_input": {
            "artifact_path": repo_relative_path(packet_path),
            "artifact_sha256": sha256_file(packet_path),
            "selected_candidate_artifact_path": repo_relative_path(selected_candidate_path_value),
            "selected_candidate_artifact_sha256": sha256_file(selected_candidate_path_value),
            "artifact_report_type": packet.get("report_type", ""),
            "packet_id": packet.get("packet_id", ""),
            "prompt_sha256": prompt_sha256,
            "prompt_text": prompt_text,
            "prompt_text_status": "available",
            "prompt_text_available": True,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha256,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": pose_bound_packet_sha256,
            "exact_proposed_dry_run_command": dry_run_command,
            "lane": packet.get("scene_type", ""),
            "recipe_id": packet.get("recipe_id", ""),
            "hook_id": packet.get("strong_hook_id", ""),
            "hook_text": packet.get("hook_text", ""),
            "caption_seed": packet.get("caption_draft", ""),
            "activity": pose_binding["pose_text"],
            "expression_text": expression_binding["expression_text"],
            "source_prompt_family": PROMPT_FAMILY_PROVIDER_EXECUTION,
            "concept_summary": " | ".join(
                part
                for part in (
                    packet.get("scene_type", ""),
                    pose_binding["pose_text"],
                    packet.get("high_caliber_source_sections", {}).get("style_lighting", ""),
                )
                if part
            ),
        },
        "structured_executor_inputs": {
            "date": date_str,
            "slot_id": slot_id,
            "repo_executor_path": REPO_EXECUTOR_PATH,
            "provider": PROVIDER,
            "executor_type": EXECUTOR_TYPE,
            "model": MODEL,
            "aspect_ratio": ASPECT_RATIO,
            "custom_reference_id": DEFAULT_CUSTOM_REFERENCE_ID,
            "negative_prompt_enabled": NEGATIVE_PROMPT_ENABLED,
            "quality": soul_cinema_contract.QUALITY,
            "generation_reference": generation_reference,
            "soul_metadata": {
                "name": SOUL_NAME,
                "type": SOUL_TYPE,
                "custom_reference_id": DEFAULT_CUSTOM_REFERENCE_ID,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_input_artifact_path": repo_relative_path(packet_path),
            "selected_prompt_input_artifact_sha256": sha256_file(packet_path),
            "selected_candidate_artifact_path": repo_relative_path(selected_candidate_path_value),
            "selected_candidate_artifact_sha256": sha256_file(selected_candidate_path_value),
            "selected_prompt_sha256": prompt_sha256,
            "selected_prompt_text": prompt_text,
            "selected_prompt_text_status": "available",
            "selected_prompt_text_available": True,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": pose_bound_packet_sha256,
            "expression_provenance": expression_binding,
            "expression_bound_content_packet_sha256": pose_bound_packet_sha256,
            "source_prompt_family": PROMPT_FAMILY_PROVIDER_EXECUTION,
            "handoff_artifact_path": handoff_json_rel_path,
            "handoff_markdown_path": handoff_md_rel_path,
            "expected_image_path": repo_relative_path(
                ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.png"
            ),
            "expected_manifest_path": repo_relative_path(
                ROOT / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"
            ),
            "dry_run_command": dry_run_command,
            "dry_run_argv": handoff_executor_argv(handoff_json_rel_path),
            "live_command": live_command,
            "live_argv": handoff_executor_argv(handoff_json_rel_path, live=True),
            "executor_byte_match_required_for_live": True,
            "executor_byte_match_proven": False,
            "live_execution_authorized": False,
            "generation_approval_required": True,
            "manual_operator_approval_required": True,
            "provider_call_performed": False,
            "generation_performed": False,
            "publish_authorized": False,
            "manual_publish_review_required": True,
            "reconciliation_artifact_path": reconciliation_provenance["reconciliation"]["source_artifact_path"],
            "reconciliation_artifact_sha256": reconciliation_provenance["reconciliation"]["source_artifact_sha256"],
            "reconciliation_status": reconciliation_provenance["reconciliation"]["reconciliation_status"],
            "reconciliation_divergence_status": reconciliation_provenance["reconciliation"]["divergence_status"],
            "reconciliation_operator_review_required": reconciliation_provenance["reconciliation"]["operator_review_required"],
            "reconciliation_resolution_policy": reconciliation_provenance["reconciliation"]["resolution_policy"],
            "reconciliation_decision_artifact_path": (
                reconciliation_provenance["decision"]["source_artifact_path"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_artifact_sha256": (
                reconciliation_provenance["decision"]["source_artifact_sha256"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_id": (
                reconciliation_provenance["decision"]["decision_id"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_operator_id": (
                reconciliation_provenance["decision"]["operator_id"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_expires_at_utc": (
                reconciliation_provenance["decision"]["expires_at_utc"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_authority_scope": (
                reconciliation_provenance["decision"]["authority_scope"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_live_generation_authorized": (
                reconciliation_provenance["decision"]["live_generation_authorized"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_publishing_authorized": (
                reconciliation_provenance["decision"]["publishing_authorized"] if reconciliation_provenance["decision"] else None
            ),
            "reconciliation_decision_next_allowed_action": (
                reconciliation_provenance["decision"]["next_allowed_action"] if reconciliation_provenance["decision"] else None
            ),
        },
        "provider_execution_binding": provider_execution_binding,
        "binding_linkage": binding_linkage,
        "source_recommendation": {
            "action_type": recommendation_body.get("action_type", ""),
            "recommended_recipe_id": recommendation_body.get("recommended_recipe_id", ""),
            "recommended_outfit_id": recommendation_body.get("recommended_outfit_id", ""),
            "recommended_environment_id": recommendation_body.get("recommended_environment_id", ""),
            "next_live_gate": recommendation_body.get("next_live_gate", ""),
            "learning_status": recommendation.get("learning_status", ""),
            "learning_status_label": recommendation.get("learning_status_label", ""),
            "learning_required_follow_up_action": recommendation.get("learning_required_follow_up_action", ""),
            "learning_signal_used": recommendation_body.get("learning_signal_used", []),
        },
        "queue_head": {
            "recipe_id": queue_head.get("recipe_id", ""),
            "title": queue_head.get("title", ""),
            "scene_type": queue_head.get("scene_type", ""),
            "autonomy_grade": queue_head.get("autonomy_grade", ""),
            "payload_headroom": queue_head.get("payload_headroom"),
            "outfit_used": queue_head.get("outfit_used", ""),
            "environment_used": queue_head.get("environment_used", ""),
            "priority_score": queue_head.get("priority_score"),
            "proof_lane_locked": queue_head.get("proof_lane_locked", False),
            "why": queue_head.get("why", []),
        },
        "learning_status": recommendation.get("learning_status", ""),
        "learning_status_label": recommendation.get("learning_status_label", ""),
        "learning_follow_up_action": recommendation.get("learning_required_follow_up_action", ""),
        "learning_published_post_count": recommendation.get("learning_published_post_count", 0),
        "learning_pending_metrics_count": recommendation.get("learning_pending_metrics_count", 0),
        "learning_stale_pending_metrics_count": recommendation.get("learning_stale_pending_metrics_count", 0),
        "learning_resolution_state_summary": recommendation.get("learning_resolution_state_summary", {}),
        "learning_state_category": recommendation.get("learning_status", "unavailable"),
        "packet_state": "packet_valid_for_claude_review",
        "dry_run_executor_contract_state": "ready",
        "live_execution_state": "blocked",
        "live_blockers": [
            "manual_operator_approval_required",
            "generation_approval_required",
        ],
        "live_execution_authorized": False,
        "generation_approval_required": True,
        "manual_operator_approval_required": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "publish_authorized": False,
        "manual_publish_review_required": True,
        "learning_current": recommendation.get("learning_status") == "current",
        "learning_usable_but_incomplete": recommendation.get("learning_status") == "usable_but_incomplete",
        "learning_stale_unresolved": recommendation.get("learning_status") == "stale_unresolved",
        "learning_manual_or_future_capability_required": recommendation.get("learning_status")
        == "manual_or_future_capability_required",
        "learning_unavailable": recommendation.get("learning_status") == "unavailable",
        "validation": {
            "recommendation_artifact_valid": True,
            "learning_artifact_valid": True,
            "queue_artifact_valid": True,
            "selected_candidate_valid": True,
            "selected_prompt_input_valid": True,
            "candidate_selection_binding_valid": True,
            "provider_execution_binding_valid": True,
            "binding_linkage_valid": True,
            "queue_head_matches_recommendation": True,
            "selected_prompt_input_matches_queue_head": True,
            "selected_prompt_input_matches_repo_executor": True,
            "prompt_text_available": True,
            "live_prompt_byte_check_required": True,
            "handoff_artifact_path": handoff_json_rel_path,
            "handoff_markdown_path": handoff_md_rel_path,
            "live_execution_authorized": False,
            "dry_run_executor_contract_state": "ready",
            "live_execution_state": "blocked",
            "reconciliation_provenance_valid": True,
            "reconciliation_decision_required": reconciliation_provenance["reconciliation"]["decision_required"],
        },
    }
    try:
        pose_provenance.validate_handoff_pose_copies(report)
        pose_provenance.validate_handoff_expression_copies(report)
    except pose_provenance.PoseProvenanceError as exc:
        raise HandoffBuildError(f"[ABORT] {exc.code}: {exc.detail}") from exc
    try:
        soul_cinema_contract.validate_generation_reference_binding(
            report.get("generation_reference")
        )
        soul_cinema_contract.validate_generation_reference_binding(
            report.get("structured_executor_inputs", {}).get("generation_reference")
        )
    except soul_cinema_contract.SoulCinemaContractError as exc:
        raise HandoffBuildError(f"[ABORT] {exc.code}: {exc.detail}") from exc
    return report


def write_markdown(path: Path, report: dict) -> None:
    structured = report["structured_executor_inputs"]
    recommendation = report["source_recommendation"]
    queue_head = report["queue_head"]
    lines = [
        "# Lena Next Live Image Handoff",
        "",
        f"Date: `{report['date']}`",
        f"Generated: `{report['created_at']}`",
        "",
        "## Identity",
        "",
        f"- report_type: `{report['report_type']}`",
        f"- schema_version: `{report['schema_version']}`",
        f"- execution_owner: `{report['execution_owner']}`",
        f"- provider: `{report['provider']}`",
        f"- executor_type: `{report['executor_type']}`",
        f"- repo_executor_path: `{report['repo_executor_path']}`",
        f"- selected_slot_id: `{report['selected_slot_id']}`",
        f"- media_content_type: `{report['media_content_type']}`",
        f"- slot_media_type: `{report['slot_media_type']}`",
        "",
        "## Commands",
        "",
        f"- Claude review command: `{structured['dry_run_command']}`",
        f"- Claude live command: `{structured['live_command']}`",
        f"- dry-run argv: `{json.dumps(structured['dry_run_argv'])}`",
        f"- live argv: `{json.dumps(structured['live_argv'])}`",
        "",
        "## Source Artifacts",
        "",
        f"- recommendation: `{report['source_recommendation_artifact_path']}`",
        f"- learning: `{report['source_learning_artifact_path']}`",
        f"- queue dry run: `{report['source_queue_dry_run_artifact_path']}`",
        f"- selected candidate: `{report['source_selected_candidate_artifact_path']}`",
        f"- selected candidate id: `{report['selected_candidate']['candidate_id']}`",
        f"- selected candidate recipe: `{report['selected_candidate']['recipe_id']}`",
        f"- generation reference: `{structured['generation_reference']['reference_image_path']}`",
        f"- generation reference SHA-256: `{structured['generation_reference']['reference_image_sha256']}`",
        f"- reconciliation artifact: `{report['source_reconciliation_artifact_path']}`",
        f"- reconciliation decision artifact: `{report['source_reconciliation_decision_artifact_path']}`",
        f"- selected prompt input: `{report['selected_prompt_input_artifact_path']}`",
        f"- expected handoff artifact: `{report['expected_handoff_artifact_path']}`",
        f"- expected handoff markdown: `{report['expected_handoff_markdown_path']}`",
        "",
        "## Readiness",
        "",
        f"- packet state: `{report['packet_state']}`",
        f"- dry-run executor contract state: `{report['dry_run_executor_contract_state']}`",
        f"- live execution state: `{report['live_execution_state']}`",
        f"- live execution authorized: `{report['live_execution_authorized']}`",
        f"- generation approval required: `{report['generation_approval_required']}`",
        f"- manual operator approval required: `{report['manual_operator_approval_required']}`",
        f"- provider call performed: `{report['provider_call_performed']}`",
        f"- generation performed: `{report['generation_performed']}`",
        f"- publish authorized: `{report['publish_authorized']}`",
        f"- manual publish review required: `{report['manual_publish_review_required']}`",
        "",
        "## Learning",
        "",
        f"- learning status: `{report['learning_status']}`",
        f"- learning follow-up: `{report['learning_follow_up_action']}`",
        f"- learning counts: published=`{report['learning_published_post_count']}` pending=`{report['learning_pending_metrics_count']}` stale=`{report['learning_stale_pending_metrics_count']}`",
        f"- learning summary: `{json.dumps(report['learning_resolution_state_summary'], ensure_ascii=False)}`",
        "",
        "## Recommendation",
        "",
        f"- action_type: `{recommendation['action_type']}`",
        f"- recommended recipe: `{recommendation['recommended_recipe_id']}`",
        f"- recommended outfit: `{recommendation['recommended_outfit_id']}`",
        f"- recommended environment: `{recommendation['recommended_environment_id']}`",
        f"- next_live_gate: `{recommendation['next_live_gate']}`",
        f"- learning signal used: `{json.dumps(recommendation['learning_signal_used'], ensure_ascii=False)}`",
        "",
        "## Queue Head",
        "",
        f"- recipe: `{queue_head['recipe_id']}`",
        f"- title: `{queue_head['title']}`",
        f"- scene_type: `{queue_head['scene_type']}`",
        f"- outfit: `{queue_head['outfit_used']}`",
        f"- environment: `{queue_head['environment_used']}`",
        f"- proof_lane_locked: `{queue_head['proof_lane_locked']}`",
        "",
        "## Prompt Identity",
        "",
        f"- selected prompt sha256: `{report['selected_prompt_input']['prompt_sha256']}`",
        f"- selected candidate sha256: `{report['selected_candidate']['artifact_sha256']}`",
        f"- selected hook text: `{report['selected_hook_text']}`",
        f"- selected caption seed: `{report['selected_caption_seed']}`",
        f"- selected prompt text status: `{report['selected_prompt_input']['prompt_text_status']}`",
        f"- prompt text available: `{report['selected_prompt_input']['prompt_text_available']}`",
        f"- exact proposed dry run command: `{report['selected_prompt_input']['exact_proposed_dry_run_command']}`",
        f"- soul metadata: `{json.dumps(structured['soul_metadata'], ensure_ascii=False)}`",
        f"- negative_prompt_enabled: `{structured['negative_prompt_enabled']}`",
        f"- expected image path: `{structured['expected_image_path']}`",
        f"- expected manifest path: `{structured['expected_manifest_path']}`",
        f"- handoff artifact path: `{structured['handoff_artifact_path']}`",
        f"- handoff markdown path: `{structured['handoff_markdown_path']}`",
        "",
        "## Live Boundary",
        "",
        "- This packet is valid for Claude review.",
        "- Live generation still needs separate operator approval.",
        "- The handoff builder does not call providers or mutate queues.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_handoff(report: dict, date_str: str) -> tuple[Path, Path]:
    out_dir = NEXT_ACTIONS / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = handoff_json_path(date_str)
    md_path = handoff_markdown_path(date_str)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(md_path, report)
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic Lena next-live-image handoff packet.")
    parser.add_argument("--date", default=utc_date(), help="UTC date for output folder")
    parser.add_argument(
        "--reconciliation-artifact",
        required=True,
        help="Path to the reconciliation artifact consumed by the handoff builder",
    )
    parser.add_argument(
        "--reconciliation-decision-artifact",
        default=None,
        help="Optional operator reconciliation decision artifact path for divergent cases",
    )
    args = parser.parse_args()

    try:
        report = build_handoff(
            args.date,
            args.reconciliation_artifact,
            args.reconciliation_decision_artifact,
        )
    except HandoffBuildError as exc:
        print(str(exc))
        return 1
    except reconciliation_contract.ReconciliationContractError as exc:
        print(f"[ABORT] {exc.code}: {exc.detail}")
        return 1
    except autonomy_ladder.AutonomyLadderError as exc:
        print(f"[ABORT] {exc.code}: {exc.detail}")
        return 1
    json_path, md_path = save_handoff(report, args.date)
    print(
        json.dumps(
            {
                "ok": True,
                "report_path": str(json_path),
                "markdown_path": str(md_path),
                "date": args.date,
                "selected_slot_id": report["selected_slot_id"],
                "packet_state": report["packet_state"],
                "dry_run_executor_contract_state": report["dry_run_executor_contract_state"],
                "live_execution_state": report["live_execution_state"],
                "live_execution_authorized": report["live_execution_authorized"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
