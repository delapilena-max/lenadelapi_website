from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
PRE_GENERATION_CANDIDATES = ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates"

REPO_EXECUTOR_PATH = "pipeline/higgsfield_lena_api_executor.py"
EXECUTION_OWNER = "claude"
PROVIDER = "higgsfield"
EXECUTOR_TYPE = "higgsfield_cli"
MEDIA_CONTENT_TYPE = "image"
SLOT_MEDIA_TYPE = "photo"
MODEL = "text2image_soul_v2"
ASPECT_RATIO = "9:16"
NEGATIVE_PROMPT_ENABLED = False
DEFAULT_CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
SOUL_NAME = "Lena"
SOUL_TYPE = "Soul 2.0"


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


def learning_path_from_recommendation(recommendation: dict) -> Path:
    return Path(str(recommendation.get("learning_artifact_path", "")).strip())


def selected_candidate_paths(date_str: str) -> list[Path]:
    directory = PRE_GENERATION_CANDIDATES / date_str
    if not directory.is_dir():
        return []
    return sorted(directory.glob("lena_pre_generation_candidate_*.json"))


def repo_relative_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def repo_executor_command(date_str: str, slot_id: str, *, live: bool = False) -> str:
    parts = [
        "python",
        REPO_EXECUTOR_PATH,
        "--date",
        date_str,
        "--slot-id",
        slot_id,
    ]
    if live:
        parts.append("--live")
    return " ".join(parts)


def repo_executor_argv(date_str: str, slot_id: str, *, live: bool = False) -> list[str]:
    argv = [
        "python",
        REPO_EXECUTOR_PATH,
        "--date",
        date_str,
        "--slot-id",
        slot_id,
    ]
    if live:
        argv.append("--live")
    return argv


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
    except Exception as exc:  # pragma: no cover - defensive fail closed
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


def load_candidate_report(path: Path, expected_date: str) -> dict:
    _require(path.is_file(), "missing_artifact", f"missing required artifact: {path}")
    try:
        report = read_json(path)
    except Exception as exc:  # pragma: no cover - defensive fail closed
        raise HandoffBuildError(f"[ABORT] unreadable_artifact: {path}: {exc}") from exc
    _require(
        report.get("schema_version") == "lena_pre_generation_candidate_gate_v1",
        "wrong_report_type",
        f"{path} has schema_version {report.get('schema_version')!r}, expected 'lena_pre_generation_candidate_gate_v1'",
    )
    report_date = str(report.get("as_of_date", "")).strip()
    _require(
        report_date == expected_date,
        "date_mismatch",
        f"{path} has as_of_date {report_date!r}, expected {expected_date!r}",
    )
    _require(
        report.get("candidate_status") == "selected",
        "candidate_not_selected",
        f"{path} is not a selected candidate artifact",
    )
    candidate = report.get("candidate")
    _require(
        isinstance(candidate, dict),
        "missing_selected_candidate",
        f"{path} does not contain a selected candidate object",
    )
    _require(
        candidate.get("candidate_id") and candidate.get("slot_id"),
        "candidate_identity_missing",
        f"{path} is missing candidate_id or slot_id",
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


def load_selected_candidate(date_str: str) -> tuple[Path, dict]:
    paths = selected_candidate_paths(date_str)
    _require(
        len(paths) == 1,
        "selected_candidate_ambiguity",
        f"expected exactly one selected-candidate artifact for {date_str}, found {len(paths)}",
    )
    path = paths[0]
    return path, load_candidate_report(path, date_str)


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


def build_handoff(date_str: str) -> dict:
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
    candidate_path, selected_candidate_report = load_selected_candidate(date_str)

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

    candidate = selected_candidate_report.get("candidate", {})
    slot_id = str(candidate.get("slot_id", "")).strip()
    _require(
        candidate.get("recipe_id") == queue_head.get("recipe_id"),
        "candidate_recipe_mismatch",
        "selected candidate recipe does not match queue head",
    )
    expected_command = repo_executor_command(date_str, slot_id)
    _require(
        str(candidate.get("exact_proposed_dry_run_command", "")).strip() == expected_command,
        "candidate_command_mismatch",
        "selected candidate does not point at the exact Higgsfield repo adapter dry-run command",
    )

    selected_prompt_text = selected_candidate_report.get("_prompt")
    prompt_text_available = isinstance(selected_prompt_text, str) and bool(selected_prompt_text.strip())

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
        "repo_executor_path": REPO_EXECUTOR_PATH,
        "media_content_type": MEDIA_CONTENT_TYPE,
        "slot_media_type": SLOT_MEDIA_TYPE,
        "expected_handoff_artifact_path": handoff_json_rel_path,
        "expected_handoff_markdown_path": handoff_md_rel_path,
        "selected_slot_id": slot_id,
        "selected_recipe_id": candidate.get("recipe_id", ""),
        "selected_lane": candidate.get("lane", ""),
        "selected_hook_id": candidate.get("hook_id", ""),
        "selected_hook_text": candidate.get("hook_text", ""),
        "selected_caption_seed": candidate.get("caption_seed", ""),
        "source_recommendation_artifact_path": repo_relative_path(recommendation_path),
        "source_recommendation_artifact_sha256": sha256_file(recommendation_path),
        "source_learning_artifact_path": repo_relative_path(learning_path),
        "source_learning_artifact_sha256": sha256_file(learning_path),
        "source_queue_dry_run_artifact_path": repo_relative_path(queue_path),
        "source_queue_dry_run_artifact_sha256": sha256_file(queue_path),
        "selected_prompt_input_artifact_path": repo_relative_path(candidate_path),
        "selected_prompt_input_artifact_sha256": sha256_file(candidate_path),
        "selected_prompt_input": {
            "artifact_path": repo_relative_path(candidate_path),
            "artifact_sha256": sha256_file(candidate_path),
            "candidate_id": candidate.get("candidate_id", ""),
            "decision_fingerprint_sha256": selected_candidate_report.get("decision_fingerprint_sha256", ""),
            "prompt_sha256": candidate.get("prompt_sha256", ""),
            "prompt_text": selected_prompt_text if prompt_text_available else None,
            "prompt_text_status": (
                "available" if prompt_text_available else "not_persisted_in_authoritative_artifact"
            ),
            "prompt_text_available": prompt_text_available,
            "exact_proposed_dry_run_command": candidate.get("exact_proposed_dry_run_command", ""),
            "lane": candidate.get("lane", ""),
            "recipe_id": candidate.get("recipe_id", ""),
            "hook_id": candidate.get("hook_id", ""),
            "hook_text": candidate.get("hook_text", ""),
            "caption_seed": candidate.get("caption_seed", ""),
            "activity": candidate.get("activity", ""),
            "concept_summary": candidate.get("concept_summary", ""),
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
            "soul_metadata": {
                "name": SOUL_NAME,
                "type": SOUL_TYPE,
                "custom_reference_id": DEFAULT_CUSTOM_REFERENCE_ID,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_input_artifact_path": repo_relative_path(candidate_path),
            "selected_prompt_input_artifact_sha256": sha256_file(candidate_path),
            "selected_prompt_sha256": candidate.get("prompt_sha256", ""),
            "selected_prompt_text": selected_prompt_text if prompt_text_available else None,
            "selected_prompt_text_status": (
                "available" if prompt_text_available else "not_persisted_in_authoritative_artifact"
            ),
            "selected_prompt_text_available": prompt_text_available,
            "handoff_artifact_path": handoff_json_rel_path,
            "handoff_markdown_path": handoff_md_rel_path,
            "expected_image_path": repo_relative_path(
                ROOT
                / "pipeline"
                / "higgsfield_library"
                / "lena"
                / date_str
                / f"{slot_id}_seed.png"
            ),
            "expected_manifest_path": repo_relative_path(
                ROOT
                / "pipeline"
                / "higgsfield_debug"
                / date_str
                / slot_id
                / "result_manifest.json"
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
        },
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
            "exact_prompt_text_not_persisted_in_authoritative_prompt_artifact",
            "manual_operator_approval_required",
            "generation_approval_required",
        ] if not prompt_text_available else [
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
            "queue_head_matches_recommendation": True,
            "candidate_matches_queue_head": True,
            "candidate_command_matches_repo_executor": True,
            "prompt_text_available": prompt_text_available,
            "live_prompt_byte_check_required": True,
            "handoff_artifact_path": handoff_json_rel_path,
            "handoff_markdown_path": handoff_md_rel_path,
            "live_execution_authorized": False,
            "dry_run_executor_contract_state": "ready",
            "live_execution_state": "blocked",
        },
    }
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
    args = parser.parse_args()

    report = build_handoff(args.date)
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
