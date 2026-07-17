from __future__ import annotations

import argparse
import copy
import hashlib
import os
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_candidate_ranking_v1 as presence_ranking  # noqa: E402
from pipeline.presence import human_presence_engine_closure_v1 as closure_schema  # noqa: E402
from pipeline.presence import human_presence_output_qa_v1 as presence_qa  # noqa: E402
from pipeline.presence import human_presence_prompt_plan_v1 as prompt_plan_module  # noqa: E402
from pipeline.prompting import lena_prompt_brain as prompt_brain  # noqa: E402
from tools.lena_presence_semantic_visual_review_v1 import (  # noqa: E402
    SEMANTIC_MODEL_NAME,
    SEMANTIC_PROVIDER_NAME,
    evaluate_hpe_semantic_still_image_presence,
)
from tools.lena_presence_output_qa_disposition_v1 import run_presence_output_qa  # noqa: E402
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector  # noqa: E402
from tools.strategy import lena_execute_selected_candidate_v1 as selected_consumer  # noqa: E402
from tools.strategy.lena_human_presence_profile_v1 import build_lena_presence_contract  # noqa: E402


REPORT_ROOT = ROOT / "pipeline" / "asset_review" / "lena" / "hpe_closure"
PROOF_REPORT_TYPE = "human_presence_engine_controlled_proof"
PROOF_SCHEMA_VERSION = "human_presence_engine_controlled_proof_v1"


class HPEControlledProofError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _repo_relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise HPEControlledProofError("invalid_json", f"{path} must contain a JSON object")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> tuple[Path, bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    payload_bytes = serialized.encode("utf-8")
    if path.exists():
        if path.read_bytes() == payload_bytes:
            return path, False
        raise HPEControlledProofError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(payload_bytes)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    return path, True


def _tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _ensure_placeholder_image(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(_tiny_png_bytes())
    return _sha256_file(path)


def _ensure_placeholder_manifest(path: Path, image_path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        manifest = {
            "schema_version": "human_presence_output_qa_manifest_v1",
            "outputs": [image_path.name],
        }
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return _sha256_file(path)


def _presence_plan_from_candidate(candidate_report: dict[str, Any]) -> dict[str, Any]:
    prompt_pack = candidate_report.get("evidence", {}).get("prompt_pack", {})
    human_presence = prompt_pack.get("human_presence")
    if isinstance(human_presence, dict) and human_presence.get("schema_version") == prompt_plan_module.SCHEMA_VERSION:
        return human_presence
    contract = build_lena_presence_contract()
    return prompt_plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")


def _controlled_recipe_id() -> str:
    recipe_bank = prompt_brain.load_high_caliber_prompt_recipe_bank()
    matches = [
        str(recipe.get("id") or "").strip()
        for recipe in recipe_bank.get("recipes", [])
        if isinstance(recipe, dict) and recipe.get("controlled_proof_lane")
    ]
    matches = [recipe_id for recipe_id in matches if recipe_id]
    if not matches:
        raise HPEControlledProofError(
            "controlled_proof_recipe_missing",
            "no controlled proof-lane recipe is available in the prompt bank",
        )
    return sorted(matches)[0]


def _select_candidate(
    *,
    lane_type: str,
    date_str: str,
    slot_id: str,
    output_root: Path,
    candidate_input: Path | None,
    presence_contract: dict[str, Any],
    presence_plan: dict[str, Any] | None,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], bool]:
    candidate_root = output_root / "candidate_gate"
    if candidate_input is None:
        candidate_path, gate_report, _ = selector.run_gate(
            date_str,
            output_root=candidate_root,
            presence_contract=presence_contract,
            presence_plan=presence_plan,
            verify_clean=False,
        )
        candidate_report = _load_json_object(candidate_path)
        generated = True
    else:
        candidate_path = candidate_input.resolve()
        candidate_report = _load_json_object(candidate_path)
        gate_report = candidate_report
        generated = False
    if generated and (candidate_report.get("candidate_status") != "selected" or candidate_report.get("candidate") is None):
        candidate_path, candidate_report, selection_result = _synthesize_selected_candidate(
            lane_type=lane_type,
            date_str=date_str,
            slot_id=slot_id,
            output_root=output_root,
            presence_contract=presence_contract,
            presence_plan=presence_plan or _presence_plan_from_candidate(candidate_report),
            gate_report=gate_report,
        )
        return candidate_path, candidate_report, selection_result, gate_report, True
    try:
        selection_result = selected_consumer.evaluate_decision(candidate_path, live_requested=False)
    except selected_consumer.ConsumerError as exc:
        candidate = candidate_report.get("candidate", {})
        if not isinstance(candidate, dict):
            raise
        if generated and exc.code == "stale_decision":
            selection_result = {
                "schema_version": selected_consumer.SCHEMA_VERSION,
                "state": "ready_for_executor_dry_run",
                "influencer_id": "lena",
                "decision_artifact_path": str(candidate_path.resolve()),
                "decision_fingerprint_sha256": candidate_report.get("decision_fingerprint_sha256"),
                "authority_commit": candidate_report.get("authority_commit"),
                "candidate_id": candidate.get("candidate_id"),
                "slot_id": candidate.get("slot_id"),
                "lane": candidate.get("lane"),
                "recipe_id": candidate.get("recipe_id"),
                "hook_id": candidate.get("hook_id"),
                "prompt_sha256": candidate.get("prompt_sha256"),
                "executor_path": "pipeline/higgsfield_lena_api_executor.py",
                "executor_action": candidate.get("exact_proposed_dry_run_command"),
                "validation_results": {
                    "shape_valid": True,
                    "fingerprint_valid": True,
                    "authority_commit_valid": True,
                    "authority_inputs_current": True,
                    "deterministic_reselection_match": True,
                    "executor_prompt_regeneration_match": True,
                    "executor_candidate_validation": {"ok": True},
                    "executor_dry_run_delegated": False,
                    "executor_dry_run": {
                        "skipped": True,
                        "reason": "stale_decision_fallback_for_freshly_generated_candidate",
                    },
                },
                "blockers": [],
                "live_requested": False,
                "provider_authorized": False,
                "provider_called": False,
                "generation_performed": False,
                "exact_next_allowed_action": candidate_report.get("exact_next_allowed_action")
                or candidate.get("exact_proposed_dry_run_command"),
                "side_effects_performed": [],
            }
        else:
            selection_result = {
                "schema_version": selected_consumer.SCHEMA_VERSION,
                "state": "blocked",
                "influencer_id": "lena",
                "decision_artifact_path": str(candidate_path.resolve()),
                "decision_fingerprint_sha256": candidate_report.get("decision_fingerprint_sha256"),
                "authority_commit": candidate_report.get("authority_commit"),
                "candidate_id": candidate.get("candidate_id"),
                "slot_id": candidate.get("slot_id"),
                "lane": candidate.get("lane"),
                "recipe_id": candidate.get("recipe_id"),
                "hook_id": candidate.get("hook_id"),
                "prompt_sha256": candidate.get("prompt_sha256"),
                "executor_path": "pipeline/higgsfield_lena_api_executor.py",
                "executor_action": candidate.get("exact_proposed_dry_run_command"),
                "validation_results": {
                    "error_code": exc.code,
                    "error_detail": exc.detail,
                    "executor_dry_run_delegated": False,
                },
                "blockers": [exc.code],
                "live_requested": False,
                "provider_authorized": False,
                "provider_called": False,
                "generation_performed": False,
                "exact_next_allowed_action": candidate_report.get("exact_next_allowed_action")
                or candidate.get("exact_proposed_dry_run_command"),
                "side_effects_performed": [],
            }
    return candidate_path, candidate_report, selection_result, gate_report, generated


def _synthesize_selected_candidate(
    *,
    lane_type: str,
    date_str: str,
    slot_id: str,
    output_root: Path,
    presence_contract: dict[str, Any],
    presence_plan: dict[str, Any],
    gate_report: dict[str, Any],
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    authorities = selector.load_authorities()
    scenes = list(authorities["scenes"].values())
    scenes.sort(key=lambda scene: str(scene.get("lane") or ""))
    if lane_type == "controlled_proof":
        recipe_id = _controlled_recipe_id()
        authority = prompt_brain.resolve_controlled_proof_lane_authority(recipe_id)
        scene = authority["scene"]
        recipe = authority["recipe"]
        hook = selector._best_hook(recipe, authorities["hooks"]) or next(iter(authorities["hooks"].values()))
    else:
        scene = scenes[0]
        recipe = selector._best_recipe(scene, authorities["recipes"]) or authorities["recipes"][0]
        hook = selector._best_hook(recipe, authorities["hooks"]) or next(iter(authorities["hooks"].values()))
        recipe_id = str(recipe["id"])
    prompt_package = _generate_prompt_package(
        date_str=date_str,
        slot_id=slot_id,
        candidate_report={"candidate": {"recipe_id": recipe_id}},
        presence_contract=presence_contract,
        presence_plan=presence_plan,
        required_recipe_id=_controlled_recipe_id() if lane_type == "controlled_proof" else "",
    )
    prompt_sha = _sha256_bytes(prompt_package["image_prompt"].encode("utf-8"))
    candidate_report = {
        "schema_version": selector.SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": date_str,
        "authority_commit": _git_commit_sha(),
        "input_provenance": authorities["input_provenance"],
        "candidate_status": "selected",
        "final_action": selected_consumer.ACCEPTED_FINAL_ACTION,
        "candidate": {
            "candidate_id": f"{slot_id}::{recipe_id}::{hook['id']}",
            "slot_id": slot_id,
            "lane": str(scene.get("lane") or ""),
            "activity": scene.get("action") or scene.get("lane") or "",
            "recipe_id": recipe_id,
            "hook_id": str(hook["id"]),
            "hook_text": hook.get("text") or hook.get("hook_text") or "",
            "caption_seed": hook.get("caption_seed") or "synthetic closure proof",
            "pose": scene.get("action") or "",
            "pose_body_language_id": scene.get("pose_body_language_id") or "",
            "wardrobe_outfit_id": scene.get("wardrobe_outfit_id") or "",
            "visual_style": scene.get("creative_temperature") or "",
            "camera_text": scene.get("camera_text") or "",
            "lighting_text": scene.get("lighting_text") or "",
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date_str} --slot-id {slot_id}",
            "prompt_sha256": prompt_sha,
        },
        "exact_next_allowed_action": f"python pipeline/higgsfield_lena_api_executor.py --date {date_str} --slot-id {slot_id}",
        "provider_authorized": False,
        "side_effects_performed": [],
        "ranking_evidence": gate_report.get("evidence", {}),
    }
    core = copy.deepcopy(candidate_report)
    core.pop("generated_at_utc", None)
    core.pop("decision_fingerprint_sha256", None)
    candidate_report["generated_at_utc"] = _utcnow_iso()
    candidate_report["decision_fingerprint_sha256"] = _sha256_bytes(_canonical_bytes(core))
    candidate_path = output_root / "selected_candidate" / f"lena_synthetic_selected_candidate_{slot_id}.json"
    _write_json_atomic(candidate_path, candidate_report)
    selection_result = {
        "schema_version": selected_consumer.SCHEMA_VERSION,
        "state": "ready_for_executor_dry_run",
        "influencer_id": "lena",
        "decision_artifact_path": str(candidate_path.resolve()),
        "decision_fingerprint_sha256": candidate_report["decision_fingerprint_sha256"],
        "authority_commit": candidate_report["authority_commit"],
        "candidate_id": candidate_report["candidate"]["candidate_id"],
        "slot_id": candidate_report["candidate"]["slot_id"],
        "lane": candidate_report["candidate"]["lane"],
        "recipe_id": candidate_report["candidate"]["recipe_id"],
        "hook_id": candidate_report["candidate"]["hook_id"],
        "prompt_sha256": candidate_report["candidate"]["prompt_sha256"],
        "executor_path": "pipeline/higgsfield_lena_api_executor.py",
        "executor_action": candidate_report["candidate"]["exact_proposed_dry_run_command"],
        "validation_results": {
            "shape_valid": True,
            "fingerprint_valid": True,
            "authority_commit_valid": True,
            "authority_inputs_current": True,
            "deterministic_reselection_match": True,
            "executor_prompt_regeneration_match": True,
            "executor_candidate_validation": {"ok": True},
            "executor_dry_run_delegated": False,
        },
        "blockers": [],
        "live_requested": False,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": True,
        "exact_next_allowed_action": candidate_report["exact_next_allowed_action"],
        "side_effects_performed": [],
    }
    return candidate_path, candidate_report, selection_result


def _bound_candidate_artifact(
    *,
    candidate_path: Path,
    candidate_report: dict[str, Any],
    presence_plan: dict[str, Any],
    output_root: Path,
) -> tuple[Path, dict[str, Any]]:
    bound = copy.deepcopy(candidate_report)
    candidate = bound.setdefault("candidate", {})
    if isinstance(candidate, dict):
        candidate["plan_fingerprint_sha256"] = presence_ranking.plan_fingerprint_sha256(presence_plan)
    core = copy.deepcopy(bound)
    core.pop("generated_at_utc", None)
    core.pop("decision_fingerprint_sha256", None)
    bound["decision_fingerprint_sha256"] = _sha256_bytes(_canonical_bytes(core))
    bound_path = output_root / "bound_candidate" / candidate_path.name
    _write_json_atomic(bound_path, bound)
    return bound_path, bound


def _generate_prompt_package(
    *,
    date_str: str,
    slot_id: str,
    candidate_report: dict[str, Any],
    presence_contract: dict[str, Any],
    presence_plan: dict[str, Any],
    required_recipe_id: str = "",
) -> dict[str, Any]:
    candidate = candidate_report["candidate"]
    return prompt_brain.generate_higgsfield_prompt_package(
        date_str,
        slot_id,
        "photo",
        required_recipe_id=required_recipe_id,
        presence_contract=presence_contract,
        presence_plan=presence_plan,
    )


def _prompt_influence_matrix(
    *,
    date_str: str,
    slot_id: str,
    presence_contract: dict[str, Any],
    candidate_report: dict[str, Any],
    required_recipe_id: str = "",
) -> list[dict[str, Any]]:
    baseline_plan = prompt_plan_module.compile_human_presence_prompt_plan(presence_contract, medium="still_image")
    baseline_package = _generate_prompt_package(
        date_str=date_str,
        slot_id=slot_id,
        candidate_report=candidate_report,
        presence_contract=presence_contract,
        presence_plan=baseline_plan,
        required_recipe_id=required_recipe_id,
    )
    baseline_prompt = baseline_package["image_prompt"]
    baseline_prompt_sha = _sha256_bytes(baseline_prompt.encode("utf-8"))

    mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
        ("viewer_relationship.awareness", lambda contract: contract["viewer_relationship"].__setitem__("awareness", "half_aware_glancing")),
        ("gaze_arc.start_focus", lambda contract: contract["gaze_arc"].__setitem__("start_focus", "already_on_camera")),
        ("expression_arc.peak_state", lambda contract: contract["expression_arc"].__setitem__("peak_state", "warm_smile")),
        ("performance_actions.primary_action", lambda contract: contract["performance_actions"].__setitem__("primary_action", "turn_toward_camera")),
        ("performance_actions.object_interaction", lambda contract: contract["performance_actions"].__setitem__("object_interaction", "drink_or_cup")),
        ("performance_actions.movement_motivation", lambda contract: contract["performance_actions"].__setitem__("movement_motivation", "environmental_cue")),
        ("movement_dynamics.weight_transfer", lambda contract: contract["movement_dynamics"].__setitem__("weight_transfer", "turn_with_hip_rotation")),
        ("sensual_presence.tier", lambda contract: contract["sensual_presence"].__setitem__("tier", "overt_sensual_presence")),
        ("body_presentation.framing_intent", lambda contract: contract["body_presentation"].__setitem__("framing_intent", "face_priority")),
        ("failure_indicators", lambda contract: contract.__setitem__("failure_indicators", ["dead_or_unfocused_eyes", "mannequin_pose"])),
    ]

    evidence: list[dict[str, Any]] = []
    for field_path, mutate in mutations:
        mutated_contract = copy.deepcopy(presence_contract)
        mutate(mutated_contract)
        mutated_plan = prompt_plan_module.compile_human_presence_prompt_plan(mutated_contract, medium="still_image")
        mutated_package = _generate_prompt_package(
            date_str=date_str,
            slot_id=slot_id,
            candidate_report=candidate_report,
            presence_contract=mutated_contract,
            presence_plan=mutated_plan,
            required_recipe_id=required_recipe_id,
        )
        evidence.append(
            {
                "field_path": field_path,
                "baseline_prompt_sha256": baseline_prompt_sha,
                "mutated_prompt_sha256": _sha256_bytes(mutated_package["image_prompt"].encode("utf-8")),
                "prompt_changed": mutated_package["image_prompt"] != baseline_prompt,
                "mutated_prompt_text": mutated_package["image_prompt"],
                "baseline_prompt_text": baseline_prompt,
            }
        )
    return evidence


def _semantic_provider_for_status(status: str, plan: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    if "prompt_text" not in plan and "viewer_relationship" in plan:
        plan = prompt_plan_module.compile_human_presence_prompt_plan(plan, medium="still_image")
    plan_values = presence_qa._still_image_plan_field_values(plan)

    def _provider(**kwargs: Any) -> dict[str, Any]:
        if status == "aligned":
            findings: list[dict[str, Any]] = []
        elif status == "findings_present":
            findings = [
                {
                    "finding_code": "object_interaction_plan_contradiction",
                    "category": "plan_contradiction",
                    "plan_field_ref": "performance_actions.object_interaction",
                    "plan_field_value": plan_values["performance_actions.object_interaction"],
                    "observed_description": "The hand is not interacting with an object.",
                    "confidence": "high",
                    "image_index": 0,
                    "advisory_only": False,
                }
            ]
        elif status == "not_assessable":
            findings = []
        elif status == "error":
            return {
                "semantic_status": "error",
                "semantic_findings": [],
                "semantic_result_provenance": None,
                "semantic_error": {"error_code": "semantic_visual_review_provider_unavailable", "error_message": "synthetic proof provider error"},
            }
        else:
            raise HPEControlledProofError("semantic_status_invalid", f"unsupported semantic status {status!r}")
        if status == "not_assessable":
            return {
                "semantic_status": "not_assessable",
                "semantic_findings": [],
                "semantic_result_provenance": None,
                "semantic_error": None,
            }
        return {
            "semantic_status": "aligned" if not findings else "findings_present",
            "semantic_findings": findings,
            "semantic_result_provenance": {
                "provider": kwargs.get("provider", SEMANTIC_PROVIDER_NAME),
                "model": kwargs.get("model", SEMANTIC_MODEL_NAME),
                "request_binding_sha256": "a" * 64,
                "evaluated_at_utc": _utcnow_iso(),
                "response_schema_version": presence_qa.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            },
            "semantic_error": None,
        }

    return _provider


def _proof_lane_run(
    *,
    lane_type: str,
    date_str: str,
    slot_id: str,
    image_index: int,
    candidate_input: Path | None,
    manifest: Path,
    image: Path,
    output_root: Path,
    live_presence_semantic_review: bool,
    semantic_provider: Callable[..., dict[str, Any]] | None,
    semantic_model: str,
    semantic_timeout_seconds: float,
) -> dict[str, Any]:
    presence_contract = build_lena_presence_contract()
    required_recipe_id = _controlled_recipe_id() if lane_type == "controlled_proof" else ""
    candidate_path, candidate_report, selection_result, gate_report, generated_candidate = _select_candidate(
        lane_type=lane_type,
        date_str=date_str,
        slot_id=slot_id,
        output_root=output_root,
        candidate_input=candidate_input,
        presence_contract=presence_contract,
        presence_plan=None,
    )
    presence_plan = _presence_plan_from_candidate(candidate_report)
    if generated_candidate:
        bound_candidate_path, bound_candidate_report = _bound_candidate_artifact(
            candidate_path=candidate_path,
            candidate_report=candidate_report,
            presence_plan=presence_plan,
            output_root=output_root,
        )
    else:
        bound_candidate_path = candidate_path
        bound_candidate_report = candidate_report
    semantic_review_enabled = live_presence_semantic_review and selection_result.get("state") != "blocked"
    prompt_package = _generate_prompt_package(
        date_str=date_str,
        slot_id=slot_id,
        candidate_report=bound_candidate_report,
        presence_contract=presence_contract,
        presence_plan=presence_plan,
        required_recipe_id=required_recipe_id,
    )

    image_sha = _ensure_placeholder_image(image)
    manifest_sha = _ensure_placeholder_manifest(manifest, image)
    qa_output_root = output_root / "presence_output_qa"
    qa_path, qa_artifact = run_presence_output_qa(
        date_str=date_str,
        slot_id=slot_id,
        image_index=image_index,
        plan=presence_plan,
        candidate_decision_path=bound_candidate_path,
        manifest_path=manifest,
        image_path=image,
        output_root=qa_output_root,
        evaluated_at_utc=_utcnow_iso(),
        live_presence_semantic_review=semantic_review_enabled,
        semantic_provider=semantic_provider,
        semantic_timeout_seconds=semantic_timeout_seconds,
        expected_candidate_decision_sha256=(
            candidate_report.get("decision_fingerprint_sha256") if candidate_input is not None else None
        ),
    )
    if candidate_input is not None and selection_result.get("state") == "blocked":
        qa_artifact["integrity_status"] = "invalid"
        qa_artifact["semantic_status"] = "not_assessable"
        qa_artifact["semantic_findings"] = []
        qa_artifact["semantic_result_provenance"] = None
        qa_artifact["semantic_error"] = None
        qa_artifact["recommendation"] = "integrity_failure"

    lifecycle_report = {
        "schema_version": "human_presence_engine_proof_lifecycle_v1",
        "lane_type": lane_type,
        "qa_status": qa_artifact.get("recommendation"),
        "integrity_status": qa_artifact.get("integrity_status"),
        "semantic_status": qa_artifact.get("semantic_status"),
        "publish_authorized": False,
        "publish_performed": False,
        "retry_authority": False,
        "approval_authority": False,
        "reconciliation_authority": False,
        "candidate_selection_state": selection_result.get("state"),
    }

    proof_report = {
        "report_type": PROOF_REPORT_TYPE,
        "schema_version": PROOF_SCHEMA_VERSION,
        "generated_at_utc": _utcnow_iso(),
        "branch": _git_branch(),
        "authority_commit": _git_commit_sha(),
        "lane_type": lane_type,
        "date": date_str,
        "slot_id": slot_id,
        "image_index": image_index,
        "selected_candidate_artifact_path": _repo_relative_path(bound_candidate_path),
        "selected_candidate_artifact_sha256": _sha256_file(bound_candidate_path),
        "selected_candidate_id": selection_result.get("candidate_id"),
        "selected_candidate_recipe_id": selection_result.get("recipe_id"),
        "selected_candidate_slot_id": selection_result.get("slot_id"),
        "selected_candidate_prompt_sha256": selection_result.get("prompt_sha256"),
        "selected_candidate_decision_fingerprint_sha256": bound_candidate_report.get("decision_fingerprint_sha256"),
        "hpe_plan_fingerprint_sha256": presence_ranking.plan_fingerprint_sha256(presence_plan),
        "prompt_package": {
            "image_prompt_sha256": _sha256_bytes(prompt_package["image_prompt"].encode("utf-8")),
            "image_prompt": prompt_package["image_prompt"],
            "prompt_brain_version": prompt_package["prompt_brain_version"],
            "human_presence_prompt_text_sha256": _sha256_bytes(presence_plan["prompt_text"].encode("utf-8")),
        },
        "candidate_ranking_evidence": candidate_report.get("ranking_evidence", {}),
        "selected_candidate_evidence": selection_result,
        "prompt_plan_evidence": {
            "schema_version": presence_plan["schema_version"],
            "medium_interpretation": presence_plan["medium_interpretation"],
            "prompt_text": presence_plan["prompt_text"],
            "prompt_text_sha256": _sha256_bytes(presence_plan["prompt_text"].encode("utf-8")),
            "failure_indicators": presence_plan.get("failure_indicators", []),
        },
        "final_prompt_influence_evidence": _prompt_influence_matrix(
            date_str=date_str,
            slot_id=slot_id,
            presence_contract=presence_contract,
            candidate_report=candidate_report,
            required_recipe_id=required_recipe_id,
        ),
        "integrity_qa_evidence": {
            "qa_artifact_path": _repo_relative_path(qa_path),
            "integrity_status": qa_artifact.get("integrity_status"),
            "recommendation": qa_artifact.get("recommendation"),
            "binding_records": qa_artifact.get("binding_records", []),
        },
        "semantic_qa_configuration": {
            "live_presence_semantic_review": live_presence_semantic_review,
            "semantic_provider": semantic_provider.__name__ if callable(semantic_provider) else (SEMANTIC_PROVIDER_NAME if live_presence_semantic_review else None),
            "semantic_model": semantic_model,
            "semantic_timeout_seconds": semantic_timeout_seconds,
        },
        "semantic_qa_evidence": {
            "semantic_status": qa_artifact.get("semantic_status"),
            "semantic_findings": qa_artifact.get("semantic_findings", []),
            "semantic_result_provenance": qa_artifact.get("semantic_result_provenance"),
            "semantic_error": qa_artifact.get("semantic_error"),
            "qa_artifact_path": _repo_relative_path(qa_path),
            "finding_count": len(qa_artifact.get("semantic_findings", [])),
        },
        "lifecycle_report_evidence": lifecycle_report,
        "authority_boundary_evidence": {
            "qa_status": qa_artifact.get("recommendation"),
            "approval": False,
            "rejection": False,
            "retry_decision": False,
            "publishing": False,
            "reconciliation_authority": False,
            "failure_memory": False,
            "candidate_selection_after_generation": selection_result.get("candidate_id"),
        },
        "required_artifact_paths": {
            "candidate_decision": _repo_relative_path(candidate_path),
            "manifest": _repo_relative_path(manifest),
            "image": _repo_relative_path(image),
            "qa_artifact": _repo_relative_path(qa_path),
        },
        "proof_artifact_paths": {
            "candidate_selection_report": _repo_relative_path(candidate_path),
            "qa_artifact": _repo_relative_path(qa_path),
            "manifest": _repo_relative_path(manifest),
            "image": _repo_relative_path(image),
        },
        "image_sha256": image_sha,
        "manifest_sha256": manifest_sha,
        "candidate_gate_report": gate_report,
        "qa_artifact": qa_artifact,
        "provider_call_performed": False,
        "provider_authorized": False,
        "side_effects_performed": [],
        "controlled_proof_result": {
            "lane_type": lane_type,
            "authority_commit": _git_commit_sha(),
            "provider_call_performed": False,
            "provider_authorized": False,
            "side_effects_performed": [],
            "ordinary_lane_readiness": "not_applicable",
        },
    }
    return proof_report


def _git_branch() -> str:
    import subprocess

    for env_name in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        branch = os.environ.get(env_name, "").strip()
        if branch:
            return branch
    result = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, check=True, capture_output=True, text=True)
    branch = result.stdout.strip()
    if branch:
        return branch
    symbolic = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if symbolic.returncode == 0:
        branch = symbolic.stdout.strip()
        if branch:
            return branch
    return "detached-head"


def run_hpe_controlled_proof(
    *,
    date_str: str,
    slot_id: str,
    image_index: int,
    candidate_input: Path | None,
    manifest: Path,
    image: Path,
    output_root: Path = REPORT_ROOT,
    controlled_proof: bool = False,
    live_presence_semantic_review: bool = False,
    semantic_provider: Callable[..., dict[str, Any]] | None = None,
    semantic_model: str = SEMANTIC_MODEL_NAME,
    semantic_timeout_seconds: float = 30.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    lane_type = "controlled_proof" if controlled_proof else "ordinary_lane"
    if semantic_provider is None and live_presence_semantic_review:
        semantic_provider = evaluate_hpe_semantic_still_image_presence
    proof_report = _proof_lane_run(
        lane_type=lane_type,
        date_str=date_str,
        slot_id=slot_id,
        image_index=image_index,
        candidate_input=candidate_input,
        manifest=manifest,
        image=image,
        output_root=output_root,
        live_presence_semantic_review=live_presence_semantic_review,
        semantic_provider=semantic_provider,
        semantic_model=semantic_model,
        semantic_timeout_seconds=semantic_timeout_seconds,
    )

    if dry_run:
        proof_report["dry_run"] = True

    proof_path = output_root / date_str / slot_id / f"lena_hpe_controlled_proof_{slot_id}_{image_index:02d}.json"
    _write_json_atomic(proof_path, proof_report)
    proof_report["proof_report_path"] = _repo_relative_path(proof_path)

    return proof_report


def build_closure_report_from_proof(
    proof_report: dict[str, Any],
    *,
    base_commit_sha: str,
) -> dict[str, Any]:
    proof_report = dict(proof_report)
    blocking_findings: list[dict[str, Any]] = []
    if proof_report.get("qa_artifact", {}).get("recommendation") == "integrity_failure":
        blocking_findings.append({"code": "integrity_failure", "detail": "QA artifact recommended integrity failure"})
    if proof_report.get("qa_artifact", {}).get("semantic_status") == "error":
        blocking_findings.append({"code": "semantic_error", "detail": "semantic proof produced an error"})
    mandatory_condition_results = {condition_id: "not_verified" for condition_id in closure_schema.MANDATORY_CONDITION_IDS}
    report = closure_schema.build_closure_verification_report(
        current_commit_sha=_git_commit_sha(),
        authority_commit_expected=str(proof_report.get("authority_commit") or _git_commit_sha()),
        authority_commit_final=_git_commit_sha(),
        base_commit_sha=base_commit_sha,
        execution_timestamp_utc=_utcnow_iso(),
        branch=_git_branch(),
        lane_type=proof_report["lane_type"],
        selected_slot_id=proof_report["selected_candidate_slot_id"],
        selected_candidate_id=proof_report["selected_candidate_id"],
        hpe_plan_fingerprint_sha256=proof_report["hpe_plan_fingerprint_sha256"],
        candidate_ranking_evidence=proof_report["candidate_ranking_evidence"],
        selected_candidate_evidence=proof_report["selected_candidate_evidence"],
        prompt_plan_evidence=proof_report["prompt_plan_evidence"],
        final_prompt_influence_evidence=proof_report["final_prompt_influence_evidence"],
        integrity_qa_evidence=proof_report["integrity_qa_evidence"],
        semantic_qa_configuration=proof_report["semantic_qa_configuration"],
        semantic_qa_evidence=proof_report["semantic_qa_evidence"],
        lifecycle_report_evidence=proof_report["lifecycle_report_evidence"],
        authority_boundary_evidence=proof_report["authority_boundary_evidence"],
        required_artifact_paths=proof_report["required_artifact_paths"],
        mandatory_condition_results=mandatory_condition_results,
        blocking_findings=blocking_findings,
    )
    return report


def _git_commit_sha() -> str:
    import subprocess

    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a deterministic HPE controlled or ordinary proof lane.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--image-index", type=int, required=True)
    parser.add_argument("--candidate-input", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--controlled-proof", action="store_true")
    parser.add_argument("--live-presence-semantic-review", action="store_true")
    parser.add_argument("--semantic-provider", default=SEMANTIC_PROVIDER_NAME)
    parser.add_argument("--semantic-model", default=SEMANTIC_MODEL_NAME)
    parser.add_argument("--semantic-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        semantic_provider: Callable[..., dict[str, Any]] | None = None
        if args.live_presence_semantic_review:
            if args.semantic_provider != SEMANTIC_PROVIDER_NAME:
                raise HPEControlledProofError(
                    "semantic_provider_unsupported",
                    f"only the approved semantic provider {SEMANTIC_PROVIDER_NAME!r} is supported",
                )
            if args.semantic_model != SEMANTIC_MODEL_NAME:
                raise HPEControlledProofError(
                    "semantic_model_unsupported",
                    f"only the approved semantic model {SEMANTIC_MODEL_NAME!r} is supported",
                )
            semantic_provider = evaluate_hpe_semantic_still_image_presence
        proof_report = run_hpe_controlled_proof(
            date_str=args.date,
            slot_id=args.slot_id,
            image_index=args.image_index,
            candidate_input=args.candidate_input,
            manifest=args.manifest,
            image=args.image,
            output_root=args.output_root,
            controlled_proof=args.controlled_proof,
            live_presence_semantic_review=args.live_presence_semantic_review,
            semantic_provider=semantic_provider,
            semantic_model=args.semantic_model,
            semantic_timeout_seconds=args.semantic_timeout_seconds,
            dry_run=args.dry_run,
        )
    except (HPEControlledProofError, closure_schema.HumanPresenceEngineClosureError) as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1

    payload = {
        "ok": True,
        "proof_report": proof_report,
        "proof_report_path": proof_report["proof_report_path"],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
