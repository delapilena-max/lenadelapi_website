from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import (
    SOURCE_TYPES,
    LoadedArtifact,
    VideoArtifactStore,
    validate_cross_artifact_authority,
)
from .compilation import compile_generation_plan, compile_higgsfield_request
from .contracts import (
    CHARACTER_ELEMENT_TOKEN,
    CHARACTER_ELEMENT_UUID,
    LenaVideoContractError,
    Issue,
    canonical_sha256,
    compilation_fingerprint,
    zero_activity_counters,
)


FINAL_STATES = {"final", "published"}
PROVIDER_TERMS = ("higgsfield", "seedance", "kling", "runway", "veo", "meta", "anthropic")


def _issue(
    code: str,
    message: str,
    artifact: LoadedArtifact | None = None,
    *,
    stage: str = "validation",
    field_path: str | None = None,
    expected: Any = None,
    actual: Any = None,
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
    )


def _at_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _validate_character(character: LoadedArtifact) -> list[Issue]:
    data = character.data
    issues: list[Issue] = []
    if data["character_element_uuid"] != CHARACTER_ELEMENT_UUID:
        issues.append(_issue("character_element_uuid_mismatch", "Character Element UUID does not match Lena authority.", character, expected=CHARACTER_ELEMENT_UUID, actual=data["character_element_uuid"]))
    if data["character_element_token"] != CHARACTER_ELEMENT_TOKEN:
        issues.append(_issue("character_element_token_mismatch", "Direct Character Element token is missing or stale.", character, expected=CHARACTER_ELEMENT_TOKEN, actual=data["character_element_token"]))
    if not data["direct_character_element_binding_required"]:
        issues.append(_issue("direct_character_element_binding_required", "Direct Character Element binding must be mandatory.", character))
    if data["adult_status"] != "verified_adult":
        issues.append(_issue("adult_status_invalid", "Lena video requires verified adult status.", character))
    return issues


def _validate_policy(policy: LoadedArtifact) -> list[Issue]:
    data = policy.data
    issues: list[Issue] = []
    expected = {
        "final_videos_per_governed_date": 1,
        "duration_ms": 8000,
        "resolution": "720p",
        "width_pixels": 720,
        "height_pixels": 1280,
        "aspect_ratio": "9:16",
        "standard_credit_ceiling": 36,
        "higgsfield_prompt_execution_policy_max_chars": 4096,
    }
    for field, value in expected.items():
        if data[field] != value:
            issues.append(_issue("video_policy_mismatch", "Video operating policy does not match current authority.", policy, field_path=f"$/{field}", expected=value, actual=data[field]))
    if data["execution_authorized"]:
        issues.append(_issue("video_execution_must_remain_disabled", "Architecture artifacts cannot authorize provider execution.", policy))
    if data["attempt_authority"]["authorized_attempts"] != 0 or data["attempt_authority"]["retry_authorized"]:
        issues.append(_issue("attempt_authority_not_explicitly_unlocked", "No provider attempt or retry is authorized by this source task.", policy, field_path="$/attempt_authority"))
    if not data["photo_lane_isolation"]["live_photo_lane_unchanged"]:
        issues.append(_issue("photo_lane_isolation_missing", "Video policy must preserve the live photo lane.", policy))
    return issues


def _validate_hpe(hpe: LoadedArtifact, policy: LoadedArtifact) -> list[Issue]:
    segments = hpe.data["timeline"]
    issues: list[Issue] = []
    expected_start = 0
    for index, segment in enumerate(segments):
        if segment["start_ms"] != expected_start:
            code = "hpe_timeline_overlap" if segment["start_ms"] < expected_start else "hpe_timeline_gap"
            issues.append(_issue(code, "HPE timeline must be contiguous and non-overlapping.", hpe, field_path=f"$/timeline/{index}/start_ms", expected=expected_start, actual=segment["start_ms"]))
        if segment["end_ms"] <= segment["start_ms"]:
            issues.append(_issue("hpe_segment_duration_invalid", "Each HPE segment must advance time.", hpe, field_path=f"$/timeline/{index}"))
        expected_start = segment["end_ms"]
    if expected_start != policy.data["duration_ms"]:
        issues.append(_issue("hpe_timeline_duration_mismatch", "HPE timeline must cover the exact video duration.", hpe, expected=policy.data["duration_ms"], actual=expected_start))
    if sum(segment["meaningful_displacement_cm"] for segment in segments) < 20:
        issues.append(_issue("hpe_meaningful_displacement_missing", "Performance needs observable physical displacement, not static posing.", hpe))
    if len({segment["expression"] for segment in segments}) < 3:
        issues.append(_issue("hpe_expression_progression_missing", "Expression must visibly progress across the performance.", hpe))
    if not any(segment["gesture_completion"] != "none" for segment in segments):
        issues.append(_issue("hpe_gesture_completion_missing", "At least one initiated gesture must visibly complete.", hpe))
    return issues


def _validate_audio(audio: LoadedArtifact, policy: LoadedArtifact) -> list[Issue]:
    data = audio.data
    issues: list[Issue] = []
    if data["dialogue_mode"] == "none":
        if data["dialogue_text"] or data["lip_sync_required"]:
            issues.append(_issue("no_dialogue_contract_conflict", "No-dialogue concepts cannot require text or lip sync.", audio))
    else:
        words = len(data["dialogue_text"].split())
        if words * 400 > policy.data["duration_ms"]:
            issues.append(_issue("dialogue_duration_fit_failed", "Dialogue cannot fit the eight-second voice window.", audio, expected=f"<= {policy.data['duration_ms'] // 400} words", actual=words))
        if not data["voice_authority_required"]:
            issues.append(_issue("voice_authority_missing", "Dialogue requires Lena voice authority.", audio))
    return issues


def _validate_wardrobe(wardrobe: LoadedArtifact) -> list[Issue]:
    data = wardrobe.data
    issues: list[Issue] = []
    if data["wardrobe_changes"]:
        issues.append(_issue("wardrobe_continuity_violation", "One eight-second unit cannot change wardrobe.", wardrobe))
    if not data["reference_outfit_exclusion_required"]:
        issues.append(_issue("reference_outfit_exclusion_missing", "Character references may not supply wardrobe.", wardrobe))
    for index, garment in enumerate(data["garments"]):
        if garment["continuity"] != "entire_video":
            issues.append(_issue("wardrobe_continuity_violation", "Every garment must remain continuous for the full video.", wardrobe, field_path=f"$/garments/{index}/continuity"))
        if garment["fastened_state"] == "unfastened":
            issues.append(_issue("wardrobe_fastening_unsafe", "Governed wardrobe may not become unfastened.", wardrobe, field_path=f"$/garments/{index}/fastened_state"))
    return issues


def _validate_environment(environment: LoadedArtifact) -> list[Issue]:
    data = environment.data
    issues: list[Issue] = []
    if len(data["specificity_markers"]) < 5:
        issues.append(_issue("environment_too_generic", "Environment requires observable, production-specific details.", environment))
    if data["access_context"]["restricted_access"] or data["access_context"]["special_access_implied"]:
        issues.append(_issue("restricted_access_implication", "Scene must remain in a lawful public viewing area.", environment))
    if data["brand_affiliation_implied"]:
        issues.append(_issue("implied_sponsorship_or_affiliation", "Environment cannot imply SpaceX employment or sponsorship.", environment))
    if data["rocket_distance_meters"] < 1000:
        issues.append(_issue("rocket_scale_not_believable", "Public-viewing rocket scale must remain safely distant.", environment, expected=">= 1000", actual=data["rocket_distance_meters"]))
    return issues


def _validate_camera(camera: LoadedArtifact) -> list[Issue]:
    data = camera.data
    issues: list[Issue] = []
    if data["camera_holder"] != "another_person" or data["selfie"]:
        issues.append(_issue("camera_holder_contract_violation", "The approved concept requires another person to hold the phone; selfie framing is forbidden.", camera))
    if data["safe_headroom_basis_points"] < 1000:
        issues.append(_issue("platform_safe_headroom_insufficient", "Instagram feed preview needs at least ten-percent headroom.", camera, expected=">= 1000", actual=data["safe_headroom_basis_points"]))
    if data["camera_movement"] not in {"steady_handheld_micro_reframe", "locked_handheld"}:
        issues.append(_issue("camera_motion_unrealistic", "Camera movement is not feasible for the approved smartphone setup.", camera, actual=data["camera_movement"]))
    return issues


def _validate_business(business: LoadedArtifact) -> list[Issue]:
    data = business.data
    issues: list[Issue] = []
    if data["paid_partnership"] or data["affiliate_relationship"]:
        if not data["disclosure"]["required"] or not data["disclosure"]["text"]:
            issues.append(_issue("commercial_disclosure_missing", "Commercial relationships require explicit disclosure.", business))
    if data["space_x_affiliation"] != "none":
        issues.append(_issue("implied_sponsorship_or_affiliation", "This concept cannot claim SpaceX affiliation.", business))
    return issues


def _validate_spec_and_locks(
    spec: LoadedArtifact,
    artifacts: Mapping[str, LoadedArtifact],
) -> list[Issue]:
    issues: list[Issue] = []
    reference_fields = {
        "character_authority_id": "lena_video_character_authority_v1",
        "business_intent_id": "lena_video_business_intent_v1",
        "environment_id": "lena_video_environment_v1",
        "wardrobe_id": "lena_video_wardrobe_v1",
        "hpe_id": "lena_video_hpe_v1",
        "camera_id": "lena_video_camera_v1",
        "audio_plan_id": "lena_video_audio_plan_v1",
    }
    for field, artifact_type in reference_fields.items():
        expected = artifacts[artifact_type].artifact_id
        if spec.data[field] != expected:
            issues.append(
                _issue(
                    "spec_authority_reference_mismatch",
                    "Video specification references the wrong governed authority.",
                    spec,
                    field_path=f"$/{field}",
                    expected=expected,
                    actual=spec.data[field],
                )
            )
    policy = artifacts["lena_video_policy_v1"].data
    if spec.data["cost_ceiling_credits"] != policy["standard_credit_ceiling"]:
        issues.append(
            _issue(
                "spec_cost_ceiling_mismatch",
                "Video specification must preserve the governed credit ceiling.",
                spec,
                expected=policy["standard_credit_ceiling"],
                actual=spec.data["cost_ceiling_credits"],
            )
        )
    if spec.data["attempt_authority"] != policy["attempt_authority"]:
        issues.append(
            _issue(
                "spec_attempt_authority_mismatch",
                "Video specification must preserve attempt and retry authority exactly.",
                spec,
                field_path="$/attempt_authority",
            )
        )
    for index, lock in enumerate(spec.data["user_locks"]):
        parts = lock["field_path"].lstrip("/").split("/", 1)
        target = artifacts.get(parts[0]) if len(parts) == 2 else None
        if target is None:
            issues.append(_issue("user_lock_target_missing", "User lock must target a governed artifact field.", spec, field_path=f"$/user_locks/{index}/field_path", actual=lock["field_path"]))
            continue
        try:
            actual = _at_pointer(target.data, "/" + parts[1])
        except (KeyError, IndexError, TypeError, ValueError):
            issues.append(_issue("user_lock_field_missing", "User-locked field is absent.", spec, field_path=lock["field_path"]))
            continue
        if actual != lock["value"]:
            issues.append(_issue("user_lock_changed", "A user-locked field changed silently.", target, field_path="$" + "/" + parts[1], expected=lock["value"], actual=actual))
    return issues


def _validate_provider_prompt_cues(
    artifacts: Mapping[str, LoadedArtifact],
) -> list[Issue]:
    cue_types = (
        "lena_video_character_authority_v1",
        "lena_video_spec_v1",
        "lena_video_environment_v1",
        "lena_video_wardrobe_v1",
        "lena_video_camera_v1",
        "lena_video_audio_plan_v1",
    )
    cues = [
        (artifacts[artifact_type], "$/provider_prompt_cue", artifacts[artifact_type].data["provider_prompt_cue"])
        for artifact_type in cue_types
    ]
    hpe = artifacts["lena_video_hpe_v1"]
    cues.extend(
        (hpe, f"$/timeline/{index}/provider_prompt_cue", segment["provider_prompt_cue"])
        for index, segment in enumerate(hpe.data["timeline"])
    )
    issues: list[Issue] = []
    for artifact, field_path, cue in cues:
        leaked = sorted(
            term
            for term in PROVIDER_TERMS
            if re.search(rf"\b{re.escape(term)}\b", cue, re.IGNORECASE)
        )
        if leaked:
            issues.append(
                _issue(
                    "provider_prompt_cue_not_neutral",
                    "Provider prompt cues must remain portable production authority.",
                    artifact,
                    field_path=field_path,
                    actual=leaked,
                )
            )
    return issues


def _validate_plan(
    plan: LoadedArtifact,
    artifacts: Mapping[str, LoadedArtifact],
) -> list[Issue]:
    data = plan.data
    issues: list[Issue] = []
    serialized = json.dumps(data, sort_keys=True).lower()
    leaked = sorted(term for term in PROVIDER_TERMS if f'"{term}"' in serialized)
    if leaked:
        issues.append(_issue("provider_neutrality_violation", "Provider-neutral plan contains a provider identity.", plan, actual=leaked))
    if data["execution_authorized"]:
        issues.append(_issue("generation_plan_execution_enabled", "Provider-neutral plan cannot authorize execution.", plan))
    sources = {artifact_type: artifacts[artifact_type] for artifact_type in SOURCE_TYPES}
    expected = compile_generation_plan(sources)
    if data != expected:
        issues.append(
            _issue(
                "generation_plan_not_deterministic_output",
                "Generation plan is not the exact deterministic output of current source authority.",
                plan,
                expected=canonical_sha256(expected),
                actual=plan.sha256,
            )
        )
    return issues


def _validate_compiled(
    compiled: LoadedArtifact,
    plan: LoadedArtifact,
    artifacts: Mapping[str, LoadedArtifact],
) -> list[Issue]:
    data = compiled.data
    issues: list[Issue] = []
    if data["character_element_token"] != CHARACTER_ELEMENT_TOKEN:
        issues.append(_issue("compiled_character_element_binding_missing", "Compiled request lacks the exact direct Character Element token.", compiled))
    if data["execution_authorized"]:
        issues.append(_issue("compiled_request_execution_enabled", "Compiled requests remain execution-disabled.", compiled))
    expected = compilation_fingerprint(data)
    if data["deterministic_compilation_fingerprint"] != expected:
        issues.append(_issue("compiled_fingerprint_mismatch", "Compiled request fingerprint is stale.", compiled, expected=expected, actual=data["deterministic_compilation_fingerprint"]))
    if data["source_plan_sha256"] != plan.sha256:
        issues.append(_issue("compiled_source_plan_stale", "Compiled request does not bind the current generation plan.", compiled, expected=plan.sha256, actual=data["source_plan_sha256"]))
    arguments = data["provider_arguments"]
    if arguments["prompt"] != data["exact_compiled_prompt"]:
        issues.append(_issue("compiled_prompt_argument_mismatch", "Provider prompt argument differs from the governed exact prompt.", compiled))
    if arguments["negative_prompt"] != data["exact_negative_prompt"]:
        issues.append(_issue("compiled_negative_argument_mismatch", "Provider negative-prompt argument differs from the governed exact negative prompt.", compiled))
    if data["prompt_char_count"] != len(data["exact_compiled_prompt"]):
        issues.append(_issue("compiled_prompt_char_count_mismatch", "Recorded prompt length differs from the exact compiled prompt.", compiled, expected=len(data["exact_compiled_prompt"]), actual=data["prompt_char_count"]))
    policy_budget = artifacts["lena_video_policy_v1"].data["higgsfield_prompt_execution_policy_max_chars"]
    if data["prompt_char_budget"] != policy_budget or data["prompt_char_count"] > policy_budget:
        issues.append(_issue("compiled_prompt_execution_policy_exceeded", "Compiled prompt exceeds or misstates the governed Higgsfield execution budget.", compiled, expected=f"<= {policy_budget}", actual=data["prompt_char_count"]))
    sources = {artifact_type: artifacts[artifact_type] for artifact_type in SOURCE_TYPES}
    deterministic = compile_higgsfield_request(plan, sources)
    if data != deterministic:
        issues.append(
            _issue(
                "compiled_request_not_deterministic_output",
                "Compiled request is not the exact deterministic output of current sources and plan.",
                compiled,
                expected=canonical_sha256(deterministic),
                actual=compiled.sha256,
            )
        )
    return issues


def _validate_manifest(
    manifest: LoadedArtifact,
    compiled: LoadedArtifact,
    policy: LoadedArtifact,
) -> list[Issue]:
    data = manifest.data
    issues: list[Issue] = []
    if data["request_hash"] != compiled.sha256:
        issues.append(_issue("manifest_request_hash_mismatch", "Manifest does not bind the exact compiled request.", manifest, expected=compiled.sha256, actual=data["request_hash"]))
    if data["actual_spend_credits"] > policy.data["standard_credit_ceiling"]:
        issues.append(_issue("manifest_credit_ceiling_exceeded", "Recorded provider spend exceeds governed authority.", manifest, expected=f"<= {policy.data['standard_credit_ceiling']}", actual=data["actual_spend_credits"]))
    authorized_attempts = policy.data["attempt_authority"]["authorized_attempts"]
    if data["attempts"] > authorized_attempts:
        issues.append(_issue("manifest_attempt_authority_exceeded", "Manifest records more attempts than explicitly authorized.", manifest, expected=f"<= {authorized_attempts}", actual=data["attempts"]))
    if len(data["output_files"]) != len(data["output_hashes"]):
        issues.append(_issue("manifest_output_hash_count_mismatch", "Every output file must have one canonical hash.", manifest, expected=len(data["output_files"]), actual=len(data["output_hashes"])))
    if data["lifecycle_state"] == "pre_generation":
        populated = {
            "provider_job_id": data["provider_job_id"],
            "actual_spend_credits": data["actual_spend_credits"],
            "attempts": data["attempts"],
            "output_files": data["output_files"],
            "output_hashes": data["output_hashes"],
            "identity_evidence": data["identity_evidence"],
            "audio_evidence": data["audio_evidence"],
            "edit_lineage": data["edit_lineage"],
            "final_clean_export": data["final_clean_export"],
            "platform_derivatives": data["platform_derivatives"],
        }
        if any(value not in (None, 0, []) for value in populated.values()):
            issues.append(_issue("pre_generation_manifest_claims_output", "Pre-generation manifest cannot claim a job, spend, attempt, output, evidence, edit, export, or derivative.", manifest, actual=populated))
    if data["lifecycle_state"] in FINAL_STATES and not data["final_clean_export"]:
        issues.append(_issue("final_manifest_clean_export_missing", "Final or published video requires a governed clean export.", manifest))
    return issues


def _validate_pre_generation_dispositions(
    manifest: LoadedArtifact,
    qa: LoadedArtifact,
    learning: LoadedArtifact,
) -> list[Issue]:
    if manifest.data["lifecycle_state"] != "pre_generation":
        return []
    issues: list[Issue] = []
    if qa.data["overall_quality"] != "not_assessable_pre_generation" or qa.data["publish_disposition"] != "not_authorized":
        issues.append(_issue("pre_generation_qa_claim_invalid", "Pre-generation QA cannot approve quality or publication.", qa))
    metrics = learning.data["metrics"]
    if (
        any(value is not None for value in metrics.values())
        or learning.data["allowed_learning_conclusions"]
        or learning.data["confidence_basis_points"] != 0
    ):
        issues.append(_issue("pre_generation_learning_claim_invalid", "Learning remains empty and zero-confidence before governed output metrics exist.", learning))
    return issues


def _validate_daily_cadence(
    policy: LoadedArtifact,
    manifest: LoadedArtifact | None,
    existing_final_manifests: Sequence[Mapping[str, Any]],
) -> list[Issue]:
    governed_date = policy.data["governed_date"]
    finals = [item for item in existing_final_manifests if item.get("governed_date") == governed_date and item.get("lifecycle_state") in FINAL_STATES]
    if manifest and manifest.data["lifecycle_state"] in FINAL_STATES:
        finals.append(manifest.data)
    if len(finals) > policy.data["final_videos_per_governed_date"]:
        return [_issue("duplicate_daily_final_video", "Only one final governed Lena video is permitted per governed date.", manifest or policy, expected=1, actual=len(finals))]
    return []


def validate_source_for_compilation(
    artifacts: Mapping[str, LoadedArtifact],
) -> list[Issue]:
    issues = validate_cross_artifact_authority(artifacts)
    character = artifacts["lena_video_character_authority_v1"]
    policy = artifacts["lena_video_policy_v1"]
    business = artifacts["lena_video_business_intent_v1"]
    spec = artifacts["lena_video_spec_v1"]
    hpe = artifacts["lena_video_hpe_v1"]
    environment = artifacts["lena_video_environment_v1"]
    wardrobe = artifacts["lena_video_wardrobe_v1"]
    camera = artifacts["lena_video_camera_v1"]
    audio = artifacts["lena_video_audio_plan_v1"]
    issues.extend(_validate_character(character))
    issues.extend(_validate_policy(policy))
    issues.extend(_validate_business(business))
    issues.extend(_validate_hpe(hpe, policy))
    issues.extend(_validate_audio(audio, policy))
    issues.extend(_validate_wardrobe(wardrobe))
    issues.extend(_validate_environment(environment))
    issues.extend(_validate_camera(camera))
    issues.extend(_validate_spec_and_locks(spec, artifacts))
    issues.extend(_validate_provider_prompt_cues(artifacts))
    return issues


def validate_loaded_video(
    artifacts: Mapping[str, LoadedArtifact],
    *,
    existing_final_manifests: Sequence[Mapping[str, Any]] = (),
) -> list[Issue]:
    issues = validate_source_for_compilation(artifacts)
    plan = artifacts["lena_video_generation_plan_v1"]
    compiled = artifacts["lena_higgsfield_compiled_request_v1"]
    manifest = artifacts["lena_video_manifest_v1"]
    qa = artifacts["lena_video_qa_v1"]
    learning = artifacts["lena_video_learning_v1"]
    issues.extend(_validate_plan(plan, artifacts))
    issues.extend(_validate_compiled(compiled, plan, artifacts))
    issues.extend(_validate_manifest(manifest, compiled, artifacts["lena_video_policy_v1"]))
    issues.extend(_validate_pre_generation_dispositions(manifest, qa, learning))
    issues.extend(_validate_daily_cadence(artifacts["lena_video_policy_v1"], manifest, existing_final_manifests))
    return issues


def validate_video_root(
    video_root: Path,
    *,
    existing_final_manifests: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    counters = zero_activity_counters()
    try:
        artifacts = VideoArtifactStore(video_root).load_all()
        issues = validate_loaded_video(artifacts, existing_final_manifests=existing_final_manifests)
    except LenaVideoContractError as exc:
        artifacts = {}
        issues = list(exc.issues)
    return {
        "ok": not issues,
        "report_type": "lena_video_validation_v1",
        "video_root": str(video_root),
        "video_id": next((item.data["video_id"] for item in artifacts.values()), None),
        "artifacts_validated": len(artifacts),
        "errors": [issue.to_dict() for issue in issues],
        "counters": counters,
    }
