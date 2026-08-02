from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .artifacts import EpisodeStore, LoadedArtifact, validate_cross_artifact_authority
from .contracts import ITBContractError, Issue, compilation_fingerprint, zero_activity_counters
from .novelty import evaluate_novelty


REQUIRED_SHOT_ROLES = {
    "instructional_diagram",
    "archival_observation",
    "impossible_wide",
    "intimate_detail",
    "iconic_thumbnail",
}
PROVIDER_NAMES = (
    "higgsfield",
    "kling",
    "seedance",
    "veo",
    "runway",
    "elevenlabs",
    "anthropic",
    "meta",
)
VAGUE_TERMS = {"creepy", "strange", "futuristic", "alien", "cinematic"}


def _issue(
    code: str,
    message: str,
    artifact: LoadedArtifact | None = None,
    *,
    stage: str = "validation",
    field_path: str | None = None,
    expected: Any = None,
    actual: Any = None,
    correction: str | None = None,
) -> Issue:
    return Issue(
        code=code,
        stage=stage,
        message=message,
        artifact_id=artifact.artifact_id if artifact else None,
        field_path=field_path,
        expected=expected,
        actual=actual,
        source_file=artifact.relative_path if artifact else None,
        suggested_correction=correction,
    )


def _at_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _validate_world(world: LoadedArtifact) -> list[Issue]:
    data = world.data
    issues: list[Issue] = []
    summary_words = re.findall(r"[A-Za-z0-9'-]+", data["summary"].lower())
    vague = sorted(VAGUE_TERMS.intersection(summary_words))
    if vague and len(data["specificity_markers"]) < 3:
        issues.append(_issue("generic_world_description", "Vague world language lacks concrete observable specification.", world, field_path="$/summary", actual=vague, correction="Name observable geometry, material behavior, motion, scale, and light."))
    if len({item["location_id"] for item in data["locations_or_states"]}) != len(data["locations_or_states"]):
        issues.append(_issue("duplicate_world_location", "World locations or states must have unique IDs.", world, field_path="$/locations_or_states"))
    return issues


def _validate_script_and_audio(script: LoadedArtifact, audio: LoadedArtifact) -> list[Issue]:
    issues: list[Issue] = []
    data = script.data
    if data["selected_hook"] not in data["hook_options"]:
        issues.append(_issue("selected_hook_not_offered", "Selected hook must be one of the governed hook options.", script, field_path="$/selected_hook"))
    words = sum(len(re.findall(r"\b[\w'-]+\b", item["text"])) for item in data["narration_segments"])
    allowed_words = audio.data["script_timing"]["maximum_words"]
    if words > allowed_words:
        issues.append(_issue("narration_too_long", "Narration exceeds the governed word budget.", script, field_path="$/narration_segments", expected=f"<= {allowed_words} words", actual=words))
    minimum_ms = words * 60000 // audio.data["pacing"]["words_per_minute"]
    if minimum_ms > data["timing_estimate_ms"]:
        issues.append(_issue("narration_duration_fit_failed", "Narration cannot fit the declared runtime at the governed pace.", script, expected=f">= {minimum_ms} ms", actual=data["timing_estimate_ms"]))
    return issues


def _validate_visual_sequence(
    visual: LoadedArtifact, script: LoadedArtifact, entity: LoadedArtifact
) -> list[Issue]:
    data = visual.data
    shots = data["shots"]
    issues: list[Issue] = []
    profile = data["sequence_profile"]
    count = len(shots)
    if profile == "standard_short" and not 7 <= count <= 10:
        issues.append(_issue("shot_count_invalid", "Standard shorts require 7-10 shots.", visual, field_path="$/shots", expected="7-10", actual=count))
    if profile == "approved_extended_short" and count != 11:
        issues.append(_issue("extended_shot_count_invalid", "The governed extended-short profile requires exactly 11 shots.", visual, field_path="$/shots", expected=11, actual=count))
    total = sum(item["duration_ms"] for item in shots)
    if total != data["target_duration_ms"] or not 45000 <= total <= 60000:
        issues.append(_issue("shot_duration_fit_failed", "Shot durations must sum exactly to a 45-60 second target.", visual, field_path="$/shots", expected=data["target_duration_ms"], actual=total))
    indices = [item["sequence_index"] for item in shots]
    if indices != list(range(1, count + 1)):
        issues.append(_issue("shot_sequence_not_contiguous", "Shot indices must be ordered and contiguous.", visual, field_path="$/shots/sequence_index", expected=list(range(1, count + 1)), actual=indices))
    roles = {item["role"] for item in shots}
    missing_roles = sorted(REQUIRED_SHOT_ROLES - roles)
    if missing_roles:
        issues.append(_issue("required_shot_roles_missing", "Visual sequence is missing required shot grammars.", visual, field_path="$/shots", actual=missing_roles))
    diversity = {
        "environments": len({item["environment"] for item in shots}),
        "scales": len({item["scale"] for item in shots}),
        "camera_grammars": len({item["camera"] for item in shots}),
    }
    if max(diversity.values()) < 3:
        issues.append(_issue("shot_diversity_insufficient", "Sequence needs at least three environments, scales, or camera grammars.", visual, field_path="$/shots", expected="one dimension >= 3", actual=diversity))
    segment_ids = {item["segment_id"] for item in script.data["narration_segments"]}
    unknown_segments = sorted({item["narration_segment_id"] for item in shots} - segment_ids)
    if unknown_segments:
        issues.append(_issue("shot_narration_reference_missing", "Shots reference unknown narration segments.", visual, actual=unknown_segments))
    allowed_tokens = set(entity.data["continuity_tokens"])
    allowed_states = set(entity.data["allowed_states"])
    for index, shot in enumerate(shots):
        if not set(shot["continuity_tokens"]).issubset(allowed_tokens):
            issues.append(_issue("entity_continuity_token_invalid", "Shot uses continuity tokens outside the entity authority.", visual, field_path=f"$/shots/{index}/continuity_tokens", expected=sorted(allowed_tokens), actual=shot["continuity_tokens"]))
        if shot["entity_state"] not in allowed_states:
            issues.append(_issue("entity_state_conflict", "Shot entity state conflicts with the entity sheet.", visual, field_path=f"$/shots/{index}/entity_state", expected=sorted(allowed_states), actual=shot["entity_state"]))
    if not any(item["thumbnail_eligible"] and item["role"] == "iconic_thumbnail" for item in shots):
        issues.append(_issue("iconic_thumbnail_missing", "An iconic thumbnail shot must be explicitly eligible.", visual))
    return issues


def _validate_generation_plan(plan: LoadedArtifact, visual: LoadedArtifact) -> list[Issue]:
    issues: list[Issue] = []
    data = plan.data
    if data["source_episode_id"] != visual.data["episode_id"]:
        issues.append(_issue("generation_plan_episode_mismatch", "Generation plan references a different episode.", plan, field_path="$/source_episode_id", expected=visual.data["episode_id"], actual=data["source_episode_id"]))
    request_ids = [item["shot_id"] for item in data["shot_requests"]]
    visual_ids = [item["shot_id"] for item in visual.data["shots"]]
    if request_ids != visual_ids:
        issues.append(_issue("generation_plan_shot_mismatch", "Provider-neutral plan must preserve exact visual-sequence shot order.", plan, expected=visual_ids, actual=request_ids))
    serialized = str(data).lower()
    leaked = sorted(name for name in PROVIDER_NAMES if name in serialized)
    if leaked:
        issues.append(_issue("provider_neutrality_violation", "Provider-neutral plan contains provider or platform assumptions.", plan, actual=leaked, correction="Express only capability requirements and shot semantics."))
    return issues


def _validate_compiled_request(compiled: LoadedArtifact, plan: LoadedArtifact) -> list[Issue]:
    issues: list[Issue] = []
    data = compiled.data
    if plan.data["validation_status"] != "validated":
        issues.append(_issue("compiled_before_source_validation", "Compiled request requires a validated provider-neutral plan.", compiled, expected="validated", actual=plan.data["validation_status"]))
    expected = compilation_fingerprint(data)
    if data["deterministic_compilation_fingerprint"] != expected:
        issues.append(_issue("compiled_fingerprint_mismatch", "Compiled request fingerprint is stale or invalid.", compiled, field_path="$/deterministic_compilation_fingerprint", expected=expected, actual=data["deterministic_compilation_fingerprint"]))
    return issues


def _validate_user_locks(concept: LoadedArtifact, artifacts: Mapping[str, LoadedArtifact]) -> list[Issue]:
    issues: list[Issue] = []
    for index, lock in enumerate(concept.data["user_input"]["locked_elements"]):
        parts = lock["field_path"].lstrip("/").split("/", 1)
        target = artifacts.get(parts[0])
        if target is None or len(parts) != 2:
            issues.append(_issue("user_lock_target_missing", "User lock must target a governed artifact type and field.", concept, field_path=f"$/user_input/locked_elements/{index}/field_path", actual=lock["field_path"]))
            continue
        try:
            actual = _at_pointer(target.data, "/" + parts[1])
        except (KeyError, IndexError, ValueError, TypeError):
            issues.append(_issue("user_lock_field_missing", "User-locked field does not exist in the target artifact.", concept, field_path=lock["field_path"]))
            continue
        if actual != lock["value"]:
            issues.append(_issue("user_lock_changed", "A user-locked value was not preserved.", target, field_path="$/" + parts[1], expected=lock["value"], actual=actual))
    return issues


def _validate_disclosure(concept: LoadedArtifact) -> list[Issue]:
    intent = concept.data["business_intent"]
    disclosure = intent["disclosure"]
    if intent["commercial"] and (not disclosure["required"] or not disclosure["text"]):
        return [_issue("commercial_disclosure_missing", "Commercial intent requires an explicit disclosure contract.", concept, field_path="$/business_intent/disclosure")]
    if disclosure["commercial_intent"] != intent["commercial"]:
        return [_issue("commercial_disclosure_mismatch", "Disclosure commercial-intent flag must match business intent.", concept)]
    return []


def _validate_non_imitation(concept: LoadedArtifact) -> list[Issue]:
    text = " ".join(
        str(concept.data[field])
        for field in ("episode_concept", "plain_language_hook", "user_forbidden_elements")
    ).lower()
    forbidden_phrases = ("in the style of", "imitate ", "copy of ", "franchise character")
    matched = [phrase.strip() for phrase in forbidden_phrases if phrase in text]
    if matched:
        return [_issue("imitation_or_copy_request", "Concept requests imitation or copied creative identity.", concept, actual=matched, correction="Describe original observable creative requirements without naming a creator or franchise.")]
    return []


def validate_loaded_episode(artifacts: Mapping[str, LoadedArtifact]) -> list[Issue]:
    issues = validate_cross_artifact_authority(artifacts)
    canon = artifacts["bureau_canon_v1"]
    genome = artifacts["bureau_creative_genome_v1"]
    concept = artifacts["bureau_concept_card_v1"]
    world = artifacts["bureau_world_dossier_v1"]
    entity = artifacts["bureau_entity_sheet_v1"]
    audio = artifacts["bureau_audio_plan_v1"]
    script = artifacts["bureau_episode_script_v1"]
    visual = artifacts["bureau_visual_sequence_v1"]
    plan = artifacts["bureau_generation_plan_v1"]
    compiled = artifacts["bureau_compiled_request_v1"]
    if canon.data["property_identity"]["name"] not in script.data["bureau_sign_off"]:
        issues.append(_issue("bureau_framing_missing", "Script sign-off must preserve explicit Bureau framing.", script, field_path="$/bureau_sign_off"))
    issues.extend(_validate_world(world))
    issues.extend(_validate_script_and_audio(script, audio))
    issues.extend(_validate_visual_sequence(visual, script, entity))
    issues.extend(_validate_generation_plan(plan, visual))
    issues.extend(_validate_compiled_request(compiled, plan))
    issues.extend(_validate_user_locks(concept, artifacts))
    issues.extend(_validate_disclosure(concept))
    issues.extend(_validate_non_imitation(concept))
    novelty = evaluate_novelty(genome.data, artifacts["bureau_continuity_ledger_v1"].data["entries"], proposed_episode_id=genome.data["episode_id"])
    if novelty["disposition"] == "reject":
        issues.append(_issue("creative_genome_novelty_rejected", "Creative Genome violates the deterministic novelty governor.", genome, actual=novelty))
    return issues


def validate_source_for_compilation(
    artifacts: Mapping[str, LoadedArtifact]
) -> list[Issue]:
    issues = validate_cross_artifact_authority(artifacts)
    canon = artifacts["bureau_canon_v1"]
    genome = artifacts["bureau_creative_genome_v1"]
    concept = artifacts["bureau_concept_card_v1"]
    world = artifacts["bureau_world_dossier_v1"]
    entity = artifacts["bureau_entity_sheet_v1"]
    audio = artifacts["bureau_audio_plan_v1"]
    script = artifacts["bureau_episode_script_v1"]
    visual = artifacts["bureau_visual_sequence_v1"]
    if canon.data["property_identity"]["name"] not in script.data["bureau_sign_off"]:
        issues.append(_issue("bureau_framing_missing", "Script sign-off must preserve explicit Bureau framing.", script, field_path="$/bureau_sign_off"))
    issues.extend(_validate_world(world))
    issues.extend(_validate_script_and_audio(script, audio))
    issues.extend(_validate_visual_sequence(visual, script, entity))
    issues.extend(_validate_user_locks(concept, artifacts))
    issues.extend(_validate_disclosure(concept))
    issues.extend(_validate_non_imitation(concept))
    novelty = evaluate_novelty(
        genome.data,
        artifacts["bureau_continuity_ledger_v1"].data["entries"],
        proposed_episode_id=genome.data["episode_id"],
    )
    if novelty["disposition"] == "reject":
        issues.append(_issue("creative_genome_novelty_rejected", "Creative Genome violates the deterministic novelty governor.", genome, actual=novelty))
    return issues


def validate_episode_root(episode_root: Path) -> dict[str, Any]:
    counters = zero_activity_counters()
    try:
        artifacts = EpisodeStore(episode_root).load_all()
        issues = validate_loaded_episode(artifacts)
    except ITBContractError as exc:
        issues = list(exc.issues)
        artifacts = {}
    return {
        "ok": not issues,
        "report_type": "itb_episode_validation_v1",
        "episode_root": str(episode_root),
        "episode_id": next((item.data["episode_id"] for item in artifacts.values()), None),
        "artifacts_validated": len(artifacts),
        "errors": [issue.to_dict() for issue in issues],
        "validation_stages": ["json_syntax", "json_schema", "cross_artifact_authority", "continuity", "shot_duration", "narration_duration", "shot_diversity", "creative_genome_novelty", "platform_aspect_ratio", "cost_and_attempt_ceilings", "user_lock_preservation", "commercial_disclosure", "provider_compilation_readiness"],
        "counters": counters,
    }
