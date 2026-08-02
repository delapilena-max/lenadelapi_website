from __future__ import annotations

from typing import Any, Mapping

from pathlib import Path

from .artifacts import EpisodeStore, LoadedArtifact, validate_schema_instance
from .contracts import (
    COMPILER_VERSION,
    PROPERTY_ID,
    ITBContractError,
    canonical_sha256,
    compilation_fingerprint,
)
from .validation import validate_source_for_compilation


SOURCE_TYPES = (
    "bureau_canon_v1",
    "bureau_creative_genome_v1",
    "bureau_concept_card_v1",
    "bureau_world_dossier_v1",
    "bureau_entity_sheet_v1",
    "bureau_audio_plan_v1",
    "bureau_episode_script_v1",
    "bureau_visual_sequence_v1",
    "bureau_continuity_ledger_v1",
)


def compile_world_to_script_context(
    canon: Mapping[str, Any],
    concept: Mapping[str, Any],
    world: Mapping[str, Any],
    entity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "bureau_identity": canon["property_identity"],
        "narrator_doctrine": canon["narrator_doctrine"],
        "comedy_doctrine": canon["comedy_doctrine"],
        "episode_concept": concept["episode_concept"],
        "impossible_rule": concept["impossible_rule"],
        "bureau_procedure": concept["bureau_procedure"],
        "world": {
            "name": world["destination_or_phenomenon"],
            "classification_code": world["classification_code"],
            "rules": world["physics_or_metaphysical_rules"],
            "locations": world["locations_or_states"],
            "survival_instructions": world["survival_instructions"],
        },
        "entity": {
            "entity_id": entity["entity_id"],
            "observable_form": entity["observable_form"],
            "movement": entity["movement"],
            "danger_mechanics": entity["danger_mechanics"],
            "continuity_tokens": entity["continuity_tokens"],
        },
        "user_locks": concept["user_input"]["locked_elements"],
        "user_forbidden_elements": concept["user_forbidden_elements"],
    }


def compile_script_to_visual_context(
    script: Mapping[str, Any],
    world: Mapping[str, Any],
    entity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "title": script["title"],
        "narration_segments": script["narration_segments"],
        "world_locations": world["locations_or_states"],
        "world_palette": world["visual_palette"],
        "world_soundscape": world["soundscape"],
        "entity_continuity_tokens": entity["continuity_tokens"],
        "entity_allowed_states": entity["allowed_states"],
        "shot_appearance_rules": entity["shot_specific_appearance_rules"],
    }


def compile_visual_to_generation_plan(
    visual: LoadedArtifact,
    entity: LoadedArtifact,
    continuity_ledger: LoadedArtifact,
    *,
    cost_ceiling_cents: int,
    attempt_ceiling: int,
) -> dict[str, Any]:
    data = visual.data
    created_at = max(
        visual.data["created_at"],
        entity.data["created_at"],
        continuity_ledger.data["created_at"],
    )
    shot_requests = []
    asset_map = {"image": "still_image", "video": "motion_clip", "graphic": "instructional_graphic", "hybrid": "hybrid_clip"}
    for shot in data["shots"]:
        shot_requests.append(
            {
                "shot_id": shot["shot_id"],
                "asset_type": asset_map[shot["generation_intent"]],
                "aspect_ratio": "9:16",
                "duration_ms": shot["duration_ms"],
                "prompt_components": {
                    "environment": shot["environment"],
                    "subject": shot["subject"],
                    "action": shot["action"],
                    "camera": f"{shot['camera']}; {shot['framing']}; {shot['lens_behavior']}",
                    "lighting": shot["lighting"],
                    "materials": shot["materials"],
                    "palette": shot["palette"],
                },
                "negative_constraints": shot["negative_constraints"],
                "image_dependencies": [],
                "video_dependencies": [],
                "audio_dependencies": [shot["narration_segment_id"]],
                "continuity_anchors": shot["continuity_tokens"],
                "motion_contract": {
                    "subject_motion": shot["movement"],
                    "camera_motion": shot["camera"],
                    "temporal_behavior": shot["transition"],
                },
                "output_requirements": ["clean_master", "preserve_source_lineage", "no_embedded_credentials"],
                "qa_requirements": ["semantic_visual_review", "entity_continuity", "shot_role_fidelity", "caption_safe_composition"],
            }
        )
    return {
        "schema_version": "itb_artifact_v1",
        "artifact_type": "bureau_generation_plan_v1",
        "artifact_id": f"{data['episode_id']}_generation_plan_v1",
        "property_id": PROPERTY_ID,
        "episode_id": data["episode_id"],
        "created_at": created_at,
        "generator_version": COMPILER_VERSION,
        "upstream_artifacts": [
            {"artifact_id": visual.artifact_id, "sha256": visual.sha256},
            {"artifact_id": entity.artifact_id, "sha256": entity.sha256},
            {
                "artifact_id": continuity_ledger.artifact_id,
                "sha256": continuity_ledger.sha256,
            },
        ],
        "validation_status": "validated",
        "source_episode_id": data["episode_id"],
        "aspect_ratio": "9:16",
        "cost_ceiling_cents": cost_ceiling_cents,
        "attempt_ceiling_per_asset": attempt_ceiling,
        "capability_requirements": ["deterministic_seed_support", "portrait_aspect_ratio", "shot_duration_control", "source_lineage_receipt"],
        "shot_requests": shot_requests,
    }


def _ordered_prompt(request: Mapping[str, Any]) -> str:
    parts = request["prompt_components"]
    motion = request["motion_contract"]
    anchors = ", ".join(request["continuity_anchors"])
    materials = ", ".join(parts["materials"])
    palette = ", ".join(parts["palette"])
    return (
        f"[Environment] {parts['environment']}\n"
        f"[Subject] {parts['subject']}\n"
        f"[Action] {parts['action']}\n"
        f"[Camera] {parts['camera']}\n"
        f"[Lighting] {parts['lighting']}\n"
        f"[Materials] {materials}\n"
        f"[Palette] {palette}\n"
        f"[Motion] Subject: {motion['subject_motion']}; Camera: {motion['camera_motion']}; Temporal: {motion['temporal_behavior']}\n"
        f"[Continuity] {anchors}"
    )


def compile_plan_to_request(plan: LoadedArtifact) -> dict[str, Any]:
    data = plan.data
    requests = []
    operation_map = {"still_image": "generate_still", "motion_clip": "generate_motion", "instructional_graphic": "render_graphic", "hybrid_clip": "generate_hybrid"}
    for request in data["shot_requests"]:
        prompt = _ordered_prompt(request)
        negative = "; ".join(request["negative_constraints"])
        requests.append(
            {
                "shot_id": request["shot_id"],
                "exact_compiled_prompt": prompt,
                "exact_negative_prompt": negative,
                "request_payload": {
                    "interface_version": "itb_compiled_request_interface_v1",
                    "operation": operation_map[request["asset_type"]],
                    "prompt": prompt,
                    "negative_prompt": negative,
                    "aspect_ratio": request["aspect_ratio"],
                    "duration_ms": request["duration_ms"],
                },
                "dimensions": {"aspect_ratio": request["aspect_ratio"], "orientation": "portrait"},
                "duration_ms": request["duration_ms"],
                "cost_ceiling_cents": data["cost_ceiling_cents"],
                "attempt_ceiling": data["attempt_ceiling_per_asset"],
                "output_location": f"outputs/{request['shot_id']}",
            }
        )
    compiled: dict[str, Any] = {
        "schema_version": "itb_artifact_v1",
        "artifact_type": "bureau_compiled_request_v1",
        "artifact_id": f"{data['episode_id']}_compiled_request_v1",
        "property_id": PROPERTY_ID,
        "episode_id": data["episode_id"],
        "created_at": data["created_at"],
        "generator_version": COMPILER_VERSION,
        "upstream_artifacts": [{"artifact_id": plan.artifact_id, "sha256": plan.sha256}],
        "compiler_version": COMPILER_VERSION,
        "source_json_references": [{"artifact_id": plan.artifact_id, "sha256": plan.sha256}],
        "provider": "unassigned_provider_interface",
        "model": "unassigned_model",
        "shot_requests": requests,
        "compilation_timestamp": data["created_at"],
        "deterministic_compilation_fingerprint": "0" * 64,
        "execution_authorized": False,
    }
    compiled["deterministic_compilation_fingerprint"] = compilation_fingerprint(compiled)
    return compiled


def _validate_generated(
    store: EpisodeStore,
    value: dict[str, Any],
    artifact_type: str,
    filename: str,
) -> None:
    schema_filename = f"{artifact_type}.schema.json"
    issues = validate_schema_instance(
        value,
        store.schemas.load(schema_filename),
        store=store.schemas,
        schema_filename=schema_filename,
        source_file=filename,
        artifact_id=value["artifact_id"],
    )
    if issues:
        raise ITBContractError(issues)


def compile_episode(episode_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    store = EpisodeStore(episode_root)
    sources = {artifact_type: store.load(artifact_type) for artifact_type in SOURCE_TYPES}
    issues = validate_source_for_compilation(sources)
    if issues:
        raise ITBContractError(issues)
    plan = compile_visual_to_generation_plan(
        sources["bureau_visual_sequence_v1"],
        sources["bureau_entity_sheet_v1"],
        sources["bureau_continuity_ledger_v1"],
        cost_ceiling_cents=0,
        attempt_ceiling=1,
    )
    _validate_generated(
        store, plan, "bureau_generation_plan_v1", "bureau_generation_plan_v1.json"
    )
    loaded_plan = LoadedArtifact(
        path=episode_root / "bureau_generation_plan_v1.json",
        relative_path="bureau_generation_plan_v1.json",
        data=plan,
        sha256=canonical_sha256(plan),
    )
    compiled = compile_plan_to_request(loaded_plan)
    _validate_generated(
        store,
        compiled,
        "bureau_compiled_request_v1",
        "bureau_compiled_request_v1.json",
    )
    return plan, compiled
