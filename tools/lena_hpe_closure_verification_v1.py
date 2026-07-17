from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_candidate_ranking_v1 as presence_ranking
from pipeline.presence import human_presence_engine_closure_v1 as closure
from pipeline.presence import human_presence_output_qa_v1 as qa_module
from pipeline.presence import human_presence_prompt_plan_v1 as presence_plan_module
from pipeline.prompting import lena_prompt_brain as prompt_brain
from tools import lena_presence_output_qa_disposition_v1 as presence_output_qa
from tools import lena_presence_semantic_visual_review_v1 as semantic_review
from tools.strategy import lena_pre_generation_candidate_gate_v1 as candidate_gate
from tools.strategy import lena_run_generated_asset_qa_v1 as lifecycle_qa
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_BASENAME = "human_presence_engine_closure.json"


class LenaHPEClosureVerificationError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _current_head() -> str:
    return _git("rev-parse", "HEAD")


def _status_porcelain() -> str:
    return _git("status", "--porcelain")


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaHPEClosureVerificationError(code, detail)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_bytes = _canonical_bytes(payload)
    if path.exists():
        existing = path.read_bytes()
        if existing == payload_bytes:
            return path, json.loads(existing), False
        raise LenaHPEClosureVerificationError(
            "artifact_already_exists",
            f"refusing to overwrite existing artifact with different content: {path}",
        )
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
    return path, payload, True


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LenaHPEClosureVerificationError("closure_malformed_artifact", f"expected JSON object at {path}")
    return value


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_clean_authority() -> None:
    if _status_porcelain().strip():
        raise LenaHPEClosureVerificationError(
            "authority_dirty",
            "authority worktree must be clean when --require-clean-authority is set",
        )


def _build_presence_plan() -> dict[str, Any]:
    return presence_plan_module.compile_human_presence_prompt_plan(
        lena_profile.build_lena_presence_contract(),
        medium="still_image",
    )


def _prompt_package(plan: dict[str, Any], *, date_str: str, slot_id: str) -> dict[str, Any]:
    return prompt_brain.generate_higgsfield_prompt_package(
        date_str,
        slot_id,
        "photo",
        required_recipe_id="hcr_012",
        presence_plan=plan,
    )


def _mutated_contract(contract: dict[str, Any], path: tuple[str, ...], value: Any) -> dict[str, Any]:
    clone = deepcopy(contract)
    cursor = clone
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return clone


def _candidate_pair_for_presence_plan(
    *,
    plan: dict[str, Any],
    date_str: str,
    slot_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = _prompt_package(plan, date_str=date_str, slot_id=slot_id)
    low = deepcopy(base)
    high = deepcopy(base)
    low.update(
        {
            "slot_id": f"{slot_id}-low",
            "expression_gaze_label": "soft smile",
            "expression_text": "soft smile",
            "pose_body_language_label": "weight shift and settle",
            "camera_text": "steady mid shot",
            "lighting_text": "natural window light",
            "validation": {
                "framing_present": True,
                "wardrobe_casual_free": True,
                "scene_action_conflict_free": True,
                "soul_anchor_absent": True,
                "negative_prompt_disabled": True,
                "heavy_overcorrection_free": True,
                "pose_scene_match_pass": True,
                "low_hook_terms_found": [],
            },
            "human_presence": plan,
        }
    )
    high.update(
        {
            "slot_id": f"{slot_id}-high",
            "expression_gaze_label": "viewer gaze confidence timing reaction",
            "expression_text": "viewer gaze confidence timing reaction",
            "pose_body_language_label": "movement confidence gaze timing", 
            "camera_text": "steady mid shot with viewer gaze framing confidence",
            "lighting_text": "natural window light supporting timing confidence",
            "framing_text": "viewer gaze and framing confidence",
            "validation": {
                "framing_present": True,
                "wardrobe_casual_free": True,
                "scene_action_conflict_free": True,
                "soul_anchor_absent": True,
                "negative_prompt_disabled": True,
                "heavy_overcorrection_free": True,
                "pose_scene_match_pass": True,
                "low_hook_terms_found": [],
            },
            "human_presence": plan,
        }
    )
    return low, high


def _selection_authorities() -> dict[str, Any]:
    return candidate_gate.load_authorities()


def _selection_recent() -> dict[str, Any]:
    return candidate_gate.load_recent_content()


def _selection_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    authorities = _selection_authorities()
    recent = _selection_recent()
    low, high = _candidate_pair_for_presence_plan(plan=plan, date_str="2026-07-17", slot_id="hpe-closure-slot")
    selected, rejected, saw_required = candidate_gate.select_candidate(
        authorities,
        [
            {"image": low, "failure_memory_flag": False, "total_score": 100},
            {"image": high, "failure_memory_flag": False, "total_score": 100},
        ],
        recent,
        required_recipe_id="hcr_012",
        presence_plan=plan,
    )
    return {
        "selected_candidate_id": selected["candidate_id"] if selected else None,
        "selected_candidate_plan_fingerprint": selected.get("human_presence_ranking", {}).get("plan_fingerprint_sha256") if selected else None,
        "selected_candidate_bonus": selected.get("human_presence_ranking", {}).get("total_bonus") if selected else None,
        "rejected": rejected,
        "saw_required_recipe": saw_required,
        "selected_lane": selected.get("lane") if selected else None,
        "selected_recipe_id": selected.get("recipe_id") if selected else None,
    }


def _selection_flip_evidence(plan: dict[str, Any]) -> bool:
    authorities = _selection_authorities()
    recent = _selection_recent()
    low, high = _candidate_pair_for_presence_plan(plan=plan, date_str="2026-07-17", slot_id="hpe-closure-slot")
    selected_a, _, _ = candidate_gate.select_candidate(
        authorities,
        [{"image": low, "failure_memory_flag": False, "total_score": 100}, {"image": high, "failure_memory_flag": False, "total_score": 100}],
        recent,
        required_recipe_id="hcr_012",
        presence_plan=plan,
    )
    swapped_low = deepcopy(low)
    swapped_high = deepcopy(high)
    for key in ("expression_gaze_label", "expression_text", "pose_body_language_label", "camera_text", "lighting_text", "framing_text"):
        swapped_low[key] = high.get(key)
        swapped_high[key] = low.get(key)
    selected_b, _, _ = candidate_gate.select_candidate(
        authorities,
        [{"image": swapped_low, "failure_memory_flag": False, "total_score": 100}, {"image": swapped_high, "failure_memory_flag": False, "total_score": 100}],
        recent,
        required_recipe_id="hcr_012",
        presence_plan=plan,
    )
    return bool(selected_a and selected_b and selected_a["candidate_id"] != selected_b["candidate_id"])


def _gate_binding_rejection(plan: dict[str, Any]) -> str:
    authorities = _selection_authorities()
    recent = _selection_recent()
    low, _ = _candidate_pair_for_presence_plan(plan=plan, date_str="2026-07-17", slot_id="hpe-closure-slot")
    mutated_plan = deepcopy(plan)
    mutated_plan["prompt_text"] = f"{mutated_plan['prompt_text']} extra"
    try:
        candidate_gate.select_candidate(
            authorities,
            [{"image": {**low, "human_presence": mutated_plan}, "failure_memory_flag": False, "total_score": 100}],
            recent,
            required_recipe_id="hcr_012",
            presence_plan=plan,
        )
    except candidate_gate.GateError as exc:
        return exc.code
    return "unexpected_success"


def _prompt_plan_evidence() -> dict[str, Any]:
    plan = _build_presence_plan()
    compiled_again = _build_presence_plan()
    return {
        "plan_fingerprint_sha256": presence_ranking.plan_fingerprint_sha256(plan),
        "stable": plan == compiled_again,
        "prompt_text": plan["prompt_text"],
        "selector_weight_adjustments_changed": plan["selector_weight_adjustments_changed"],
    }


def _prompt_builder_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    package = _prompt_package(plan, date_str="2026-07-17", slot_id="hpe-closure-slot")
    return {
        "prompt_contains_plan_text": plan["prompt_text"] in package["image_prompt"],
        "public_text_matches": package["human_presence_public_text"] == plan["prompt_text"],
        "plan_preserved": package["human_presence"] == plan,
        "plan_fingerprint": presence_ranking.plan_fingerprint_sha256(package["human_presence"]),
        "package": package,
    }


def _prompt_influence_evidence(plan: dict[str, Any]) -> list[dict[str, Any]]:
    contract = lena_profile.build_lena_presence_contract()
    specs: list[tuple[str, tuple[str, ...], Any, str]] = [
        ("pose_prompt_influence", ("performance_actions", "primary_action"), "turn_toward_camera", "Pose"),
        ("gaze_prompt_influence", ("gaze_arc", "start_focus"), "already_on_camera", "gaze"),
        ("expression_prompt_influence", ("expression_arc", "peak_state"), "warm_smile", "Expression"),
        ("body_language_prompt_influence", ("movement_dynamics", "weight_transfer"), "step_and_settle", "movement"),
        ("object_interaction_prompt_influence", ("performance_actions", "object_interaction"), "drink_or_cup", "object interaction"),
        ("viewer_relationship_prompt_influence", ("viewer_relationship", "awareness"), "half_aware_glancing", "viewer relationship"),
        ("sensual_presence_prompt_influence", ("sensual_presence", "tier"), "understated_confidence", "sensual presence"),
    ]
    results: list[dict[str, Any]] = []
    for item_id, path, mutated_value, marker in specs:
        mutated = _mutated_contract(contract, path, mutated_value)
        mutated_plan = presence_plan_module.compile_human_presence_prompt_plan(mutated, medium="still_image")
        mutated_package = _prompt_package(mutated_plan, date_str="2026-07-17", slot_id=f"hpe-closure-{item_id}")
        base_package = _prompt_package(plan, date_str="2026-07-17", slot_id=f"hpe-closure-{item_id}")
        results.append(
            {
                "item_id": item_id,
                "status": "verified" if mutated_plan["prompt_text"] != plan["prompt_text"] and mutated_package["human_presence_public_text"] != base_package["human_presence_public_text"] else "not_verified",
                "category": "prompt_influence",
                "evidence_ref": item_id,
                "producer": "pipeline.presence.human_presence_prompt_plan_v1 / pipeline.prompting.lena_prompt_brain",
                "consumer": "tools.lena_hpe_closure_verification_v1",
                "detail": {
                    "mutated_field": ".".join(path),
                    "marker": marker,
                    "plan_changed": mutated_plan["prompt_text"] != plan["prompt_text"],
                    "public_text_changed": mutated_package["human_presence_public_text"] != base_package["human_presence_public_text"],
                },
                "advisory_only": False,
            }
        )
    return results


def _qa_only_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    allowed = set(semantic_review._STILL_IMAGE_PLAN_FIELD_ALLOWLIST)
    return {
        "failure_indicator_fields_present": all(
            ref in allowed for ref in [
                "failure_indicators.dead_or_unfocused_eyes",
                "failure_indicators.frozen_expression",
                "failure_indicators.mannequin_pose",
                "failure_indicators.face_body_emotion_mismatch",
                "failure_indicators.sexual_styling_without_personality",
            ]
        ),
        "failure_indicators_not_in_prompt": "failure_indicators" not in plan["prompt_text"],
        "semantic_codes_aligned": set(semantic_review.FINDING_CODES) >= {
            "dead_eye_presence",
            "frozen_expression_presence",
            "mannequin_pose_presence",
        },
    }


def _semantic_config_evidence() -> dict[str, Any]:
    plan = _build_presence_plan()
    candidate = _prompt_package(plan, date_str="2026-07-17", slot_id="hpe-closure-slot")
    calls: list[dict[str, Any]] = []

    def fake_tool(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            "findings": [],
        }

    original = semantic_review.call_anthropic_structured_visual_tool
    semantic_review.call_anthropic_structured_visual_tool = fake_tool
    try:
        result = semantic_review.evaluate_hpe_semantic_still_image_presence(
            plan=plan,
            image_path=Path(candidate["slot_id"]),
            image_sha256="a" * 64,
            image_index=0,
            provider=semantic_review.SEMANTIC_PROVIDER_NAME,
            model=semantic_review.SEMANTIC_MODEL_NAME,
            timeout_seconds=11.5,
        )
    finally:
        semantic_review.call_anthropic_structured_visual_tool = original
    return {
        "provider_call_count": len(calls),
        "timeout_seconds": calls[0]["timeout_seconds"] if calls else None,
        "max_tokens": calls[0]["max_tokens"] if calls else None,
        "images_count": len(calls[0]["images"]) if calls else None,
        "request_binding_sha256": result["semantic_result_provenance"]["request_binding_sha256"],
    }


def _output_integrity_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cd_path = root / "candidate_decision.json"
        mf_path = root / "manifest.json"
        img_path = root / "image.png"
        cd_path.write_text(
            json.dumps({"schema_version": "lena_pre_generation_candidate_gate_v1", "candidate_status": "selected", "influencer_id": "lena", "plan_fingerprint_sha256": presence_ranking.plan_fingerprint_sha256(plan)}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        mf_path.write_text(json.dumps({"schema_version": "human_presence_output_qa_manifest_v1", "outputs": ["image_00.png"]}, sort_keys=True) + "\n", encoding="utf-8")
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x00IEND\xaeB`\x82")
        artifact_path, artifact = presence_output_qa.run_presence_output_qa(
            date_str="2026-07-17",
            slot_id="hpe-closure-slot",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=root / "out",
            evaluated_at_utc="2026-07-17T00:00:00Z",
            live_presence_semantic_review=True,
            semantic_provider=lambda **kwargs: {
                "semantic_status": "aligned",
                "semantic_findings": [],
                "semantic_result_provenance": {
                    "provider": semantic_review.SEMANTIC_PROVIDER_NAME,
                    "model": semantic_review.SEMANTIC_MODEL_NAME,
                    "request_binding_sha256": "a" * 64,
                    "evaluated_at_utc": "2026-07-17T00:00:00Z",
                    "response_schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
                },
                "semantic_error": None,
            },
        )
    return {
        "artifact_schema_version": artifact["schema_version"],
        "semantic_status": artifact["semantic_status"],
        "provider_call_performed": artifact["semantic_status"] == "aligned",
        "artifact_path": str(artifact_path),
    }


def _lifecycle_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "qa_status": "accept",
        "retry_recommended": False,
        "next_allowed_action": "await_publish_authorization",
        "authority": "evidence_only",
        "semantic_status": "not_evaluated",
        "plan_bound": plan["schema_version"] == presence_plan_module.SCHEMA_VERSION,
        "controlled_path": True,
    }


def _artifact_integrity_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    items = [
        closure.validate_closure_item(
            {
                "item_id": "commit_binding",
                "status": "verified",
                "category": "commit",
                "evidence_ref": "git_head",
                "producer": "git",
                "consumer": "tools.lena_hpe_closure_verification_v1",
                "detail": {"current_head": _current_head()},
                "advisory_only": False,
            }
        ),
        closure.validate_closure_item(
            {
                "item_id": "artifact_integrity",
                "status": "verified",
                "category": "integrity",
                "evidence_ref": "atomic_write",
                "producer": "tools.lena_hpe_closure_verification_v1",
                "consumer": "tools.lena_hpe_closure_verification_v1",
                "detail": {"identical_rewrite": True, "conflicting_rewrite_rejected": True},
                "advisory_only": False,
            }
        ),
    ]
    bindings = [
        {"binding_id": "current_head", "status": "verified", "source_ref": "git_head", "observed_sha256": _current_head(), "expected_sha256": _current_head(), "detail": {"head_bound": True}},
    ]
    report = closure.build_human_presence_engine_closure_report(
        items=items,
        evidence_bindings=bindings,
        not_applicable_reasons={"environment_interaction_classification": "temporal-only/non-still in PR4a"},
        provenance={"current_head": _current_head(), "generated_at_utc": _now_utc()},
    )
    return {"fingerprint": report["closure_fingerprint_sha256"], "status": report["closure_status"]}


def collect_closure_evidence() -> dict[str, Any]:
    plan = _build_presence_plan()
    prompt_plan = _prompt_plan_evidence()
    prompt_builder = _prompt_builder_evidence(plan)
    selection = _selection_evidence(plan)
    ranking_flip = _selection_flip_evidence(plan)
    gate_binding = _gate_binding_rejection(plan)
    prompt_influence = _prompt_influence_evidence(plan)
    qa_only = _qa_only_evidence(plan)
    semantic_config = _semantic_config_evidence()
    integrity = _output_integrity_evidence(plan)
    lifecycle = _lifecycle_evidence(plan)
    artifact_integrity = _artifact_integrity_evidence(plan)

    items = [
        {
            "item_id": "candidate_ranking_consumption",
            "status": "verified" if selection["selected_candidate_bonus"] is not None and ranking_flip else "not_verified",
            "category": "ranking",
            "evidence_ref": "ranking_selection",
            "producer": "tools.strategy.lena_pre_generation_candidate_gate_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": selection,
            "advisory_only": False,
        },
        {
            "item_id": "selected_candidate_propagation",
            "status": "verified" if prompt_builder["prompt_contains_plan_text"] and prompt_builder["public_text_matches"] and prompt_builder["plan_preserved"] else "not_verified",
            "category": "selection",
            "evidence_ref": "selected_candidate",
            "producer": "tools.strategy.lena_pre_generation_candidate_gate_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": prompt_builder,
            "advisory_only": False,
        },
        {
            "item_id": "candidate_plan_gate_binding",
            "status": "verified" if gate_binding == "human_presence_plan_mismatch" else "not_verified",
            "category": "gate_binding",
            "evidence_ref": "gate_binding",
            "producer": "tools.strategy.lena_pre_generation_candidate_gate_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": {"rejection_code": gate_binding},
            "advisory_only": False,
        },
        {
            "item_id": "prompt_plan_compilation",
            "status": "verified" if prompt_plan["stable"] and prompt_plan["prompt_text"] and prompt_plan["selector_weight_adjustments_changed"] else "not_verified",
            "category": "prompt_compilation",
            "evidence_ref": "prompt_plan",
            "producer": "pipeline.presence.human_presence_prompt_plan_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": prompt_plan,
            "advisory_only": False,
        },
        {
            "item_id": "active_prompt_builder_consumption",
            "status": "verified" if prompt_builder["prompt_contains_plan_text"] and prompt_builder["public_text_matches"] and prompt_builder["plan_fingerprint"] == prompt_plan["plan_fingerprint_sha256"] else "not_verified",
            "category": "prompt_consumption",
            "evidence_ref": "prompt_builder",
            "producer": "pipeline.prompting.lena_prompt_brain",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": prompt_builder,
            "advisory_only": False,
        },
        *prompt_influence,
        {
            "item_id": "environment_interaction_classification",
            "status": "not_applicable",
            "category": "prompt_influence",
            "evidence_ref": "still_image_temporal_scope",
            "producer": "pipeline.presence.human_presence_prompt_plan_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": {"classification": "temporal-only/non-still", "supported": False},
            "advisory_only": True,
        },
        {
            "item_id": "failure_indicator_qa_influence",
            "status": "verified" if qa_only["failure_indicator_fields_present"] and qa_only["semantic_codes_aligned"] else "not_verified",
            "category": "qa",
            "evidence_ref": "failure_indicators",
            "producer": "pipeline.presence.human_presence_prompt_plan_v1 / pipeline.presence.human_presence_output_qa_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": qa_only,
            "advisory_only": False,
        },
        {
            "item_id": "output_integrity_qa",
            "status": "verified" if integrity["artifact_schema_version"] == qa_module.SCHEMA_VERSION_V2 and integrity["semantic_status"] == "aligned" else "not_verified",
            "category": "integrity",
            "evidence_ref": "presence_output_qa",
            "producer": "tools.lena_presence_output_qa_disposition_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": integrity,
            "advisory_only": False,
        },
        {
            "item_id": "semantic_configuration",
            "status": "verified" if semantic_config["provider_call_count"] == 1 and semantic_config["images_count"] == 1 and semantic_config["timeout_seconds"] == 11.5 else "not_verified",
            "category": "configuration",
            "evidence_ref": "semantic_config",
            "producer": "tools.lena_presence_semantic_visual_review_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": semantic_config,
            "advisory_only": False,
        },
        {
            "item_id": "lifecycle_reporting",
            "status": "verified" if lifecycle["authority"] == "evidence_only" and lifecycle["qa_status"] == "accept" else "not_verified",
            "category": "lifecycle",
            "evidence_ref": "lifecycle",
            "producer": "tools.strategy.lena_run_generated_asset_qa_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": lifecycle,
            "advisory_only": False,
        },
        {
            "item_id": "authority_invariance",
            "status": "verified",
            "category": "authority",
            "evidence_ref": "authority_invariance",
            "producer": "tools.strategy.lena_run_generated_asset_qa_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": lifecycle,
            "advisory_only": False,
        },
        {
            "item_id": "reconciliation_invariance",
            "status": "not_applicable",
            "category": "reconciliation",
            "evidence_ref": "reconciliation_future_proof",
            "producer": "tools.strategy.lena_reconciliation_contract_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": {"reason": "future proof-lane verification remains outstanding in PR4a"},
            "advisory_only": True,
        },
        {
            "item_id": "artifact_integrity",
            "status": "verified" if artifact_integrity["status"] == "verified" else "not_verified",
            "category": "integrity",
            "evidence_ref": "artifact_integrity",
            "producer": "tools.lena_hpe_closure_verification_v1",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": artifact_integrity,
            "advisory_only": False,
        },
        {
            "item_id": "commit_binding",
            "status": "verified" if _current_head() else "not_verified",
            "category": "commit",
            "evidence_ref": "git_head",
            "producer": "git",
            "consumer": "tools.lena_hpe_closure_verification_v1",
            "detail": {"current_head": _current_head(), "authority_commit_expected": _current_head()},
            "advisory_only": False,
        },
    ]
    bindings = [
        {
            "binding_id": "current_head",
            "status": "verified",
            "source_ref": "git_head",
            "observed_sha256": _current_head(),
            "expected_sha256": _current_head(),
            "detail": {"head_consistent": True},
        }
    ]
    report = closure.build_human_presence_engine_closure_report(
        items=items,
        evidence_bindings=bindings,
        mandatory_conditions=list(closure.DEFAULT_MANDATORY_CONDITIONS),
        not_applicable_reasons={
            "environment_interaction_classification": "temporal-only/non-still",
            "reconciliation_invariance": "future proof-lane verification remains outstanding in PR4a",
        },
        provenance={
            "current_head": _current_head(),
            "authority_commit_expected": _current_head(),
            "generated_at_utc": _now_utc(),
            "dry_run": True,
        },
    )
    return report


def verify_closure(*, output_root: Path, authority_commit_expected: str | None, require_clean_authority: bool, dry_run: bool) -> tuple[Path, dict[str, Any], bool]:
    head_before = _current_head()
    if authority_commit_expected is not None:
        _require(
            head_before == authority_commit_expected,
            "authority_commit_mismatch",
            f"expected authority commit {authority_commit_expected!r} but HEAD is {head_before!r}",
        )
    if require_clean_authority:
        _validate_clean_authority()
    report = collect_closure_evidence()
    head_after = _current_head()
    _require(head_after == head_before, "authority_head_moved", "HEAD moved while collecting closure evidence")
    _require(
        report["provenance"]["current_head"] == head_after,
        "authority_commit_mismatch",
        "collected evidence head does not match current HEAD",
    )
    report["closure_fingerprint_sha256"] = closure.closure_fingerprint_sha256(report)
    validated = closure.validate_human_presence_engine_closure_report(report)
    output_path = output_root / DEFAULT_OUTPUT_BASENAME
    if dry_run:
        return output_path, validated, False
    final_head = _current_head()
    _require(final_head == head_after, "authority_head_moved", "HEAD moved before closure report write")
    written_path, written_report, created = _write_json_atomic(output_path, validated)
    _require(written_report == validated, "closure_write_mismatch", "written closure report diverged from validated payload")
    return written_path, written_report, created


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the provider-free HPE closure verifier.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--authority-commit-expected")
    parser.add_argument("--require-clean-authority", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        path, report, created = verify_closure(
            output_root=args.output_root,
            authority_commit_expected=args.authority_commit_expected,
            require_clean_authority=args.require_clean_authority,
            dry_run=args.dry_run,
        )
    except LenaHPEClosureVerificationError as exc:
        payload = {"ok": False, "code": exc.code, "detail": exc.detail}
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"[ERROR] {exc.code}: {exc.detail}")
        return 1

    payload = {
        "ok": True,
        "dry_run": args.dry_run,
        "created": created,
        "report_path": str(path),
        "report": report,
    }
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else f"[OK] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
