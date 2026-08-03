from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "lena_video_creative_generation_v1"
ATTEMPT_SCHEMA_VERSION = "lena_video_attempt_v1"
INFLUENCER_ID = "lena"
LENA_CHARACTER_ELEMENT_UUID = "6a842337-ef20-4cb9-a0ff-04fa5eb8f8d3"
LENA_ELEMENT_TOKEN = f"@[Lena]({LENA_CHARACTER_ELEMENT_UUID})"
STATIC_IDENTITY_LINE = (
    "Verified adult Lena through the saved Character Element; preserve stable face geometry, "
    "body proportions, natural eyes, skin texture, hairline, hair motion, hands, and fingers."
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLE_ROOT = ROOT / "pipeline" / "video" / "lena" / "examples"

REQUIRED_CREATIVE_FIELDS = (
    "video_id",
    "governed_date",
    "daily_slot",
    "concept",
    "hook",
    "business_intent",
    "environment",
    "wardrobe",
    "hpe_timeline",
    "camera_contract",
    "audio_plan",
    "caption_intent",
    "provider_neutral_plan",
    "assumptions",
)

NOVELTY_COMPARE_FIELDS = (
    "concept",
    "environment",
    "wardrobe",
    "principal_gesture",
    "emotional_arc",
    "camera_grammar",
    "hook_structure",
    "cta",
    "audio_use",
    "ending_pose",
)

CONSECUTIVE_LOCKOUT_FIELDS = (
    "environment",
    "principal_gesture",
    "outfit_family",
    "hook_structure",
    "camera_movement",
    "emotional_payoff",
)


class LenaVideoCreativeError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaVideoCreativeError(code, detail)


def _as_non_empty_text(value: Any, *, code: str, label: str) -> str:
    text = str(value or "").strip()
    _require(bool(text), code, f"{label} is required")
    return text


def build_llm_instruction_authority() -> dict[str, Any]:
    return {
        "schema_version": "lena_video_creative_generator_instruction_v1",
        "purpose": "Produce provisional structured JSON for one new Lena video; never authorize execution.",
        "output_mode": "structured_json_only",
        "inputs": [
            "static_lena_character_authority",
            "current_video_policy",
            "current_business_revenue_intent",
            "continuity_and_learning_ledger",
            "recent_content_history",
            "current_user_seed",
            "prohibited_repetition_lockouts",
            "current_platform_needs",
        ],
        "required_outputs": list(REQUIRED_CREATIVE_FIELDS),
        "may_not": [
            "validate its own output as authoritative",
            "calculate trusted hashes",
            "authorize execution",
            "reuse a prior compiled prompt",
            "silently change locked user input",
            "mutate the learning ledger",
            "call providers",
            "publish or queue content",
        ],
        "freshness_rule": (
            "Every new provider create call requires a fresh per-video creative JSON authority "
            "and a fresh deterministic compiled prompt bound to video_id, governed_date, and daily_slot."
        ),
    }


@dataclass(frozen=True)
class CreativeTemplate:
    concept: str
    hook: str
    business_intent: str
    environment: str
    outfit_family: str
    wardrobe: str
    principal_gesture: str
    emotional_arc: str
    camera_grammar: str
    camera_movement: str
    hook_structure: str
    cta: str
    audio_use: str
    ending_pose: str
    emotional_payoff: str


TEMPLATES = (
    CreativeTemplate(
        concept="SpaceX coastal launch spectator awe",
        hook="The rocket clears the horizon behind Lena before she reacts.",
        business_intent="Reach-first cinematic Reel demonstrating premium Lena video production.",
        environment="Florida public coastal launch-viewing lawn with water, boardwalk, rail, and distant rocket plume.",
        outfit_family="coastal sporty casual",
        wardrobe="medium-blue fastened jean shorts, opaque deep sea-green long-sleeve rash guard, off-white lace-up shoes",
        principal_gesture="small aligned point toward the visible rocket plume",
        emotional_arc="held anticipation to bright awe to settled wonder",
        camera_grammar="rear smartphone vertical companion shot with head-to-shoes framing",
        camera_movement="subtle handheld micro-reframe",
        hook_structure="spectacle reveal before Lena reaction",
        cta="Would you watch this launch in person?",
        audio_use="coastal breeze, sparse crowd, delayed low rocket rumble, restrained music bed",
        ending_pose="upright watching the safe climb",
        emotional_payoff="settled wonder",
    ),
    CreativeTemplate(
        concept="night-market dessert choice flirt challenge",
        hook="Lena spots two desserts and silently makes the comments choose.",
        business_intent="Comment-driving lifestyle Reel built for playful parasocial engagement.",
        environment="busy outdoor night market dessert stall with warm practical lights and shallow crowd movement.",
        outfit_family="date-night street glam",
        wardrobe="black ribbed square-neck top, cream cropped jacket, dark fitted skirt, low white sneakers",
        principal_gesture="two-option palm reveal between dessert trays",
        emotional_arc="curious scan to mischievous smile to playful decision pressure",
        camera_grammar="close companion walk-and-talk framing with dessert insert cut-ins represented in one continuous shot",
        camera_movement="slow side-step orbit",
        hook_structure="choice prompt before payoff",
        cta="Pick left or right.",
        audio_use="market ambience, paper tray rustle, soft laugh breath, no dialogue",
        ending_pose="half-smile holding both choices in frame",
        emotional_payoff="playful comment bait",
    ),
    CreativeTemplate(
        concept="rainy apartment balcony reset",
        hook="Lena pauses her chaotic morning when rain turns the balcony into a private reset.",
        business_intent="Save-driving intimacy Reel emphasizing calm, beauty, and repeatable ritual.",
        environment="small apartment balcony after rain with plants, wet railing, city lights, and warm indoor spill.",
        outfit_family="cozy elevated lounge",
        wardrobe="soft oat cropped cardigan over fitted taupe tank, high-waist charcoal lounge shorts, cream socks",
        principal_gesture="slow mug lift and shoulder-softening exhale",
        emotional_arc="frazzled start to private calm to grounded confidence",
        camera_grammar="locked vertical doorway frame looking out to balcony",
        camera_movement="nearly static with a tiny human handheld sway",
        hook_structure="chaos-to-calm transformation",
        cta="Save this for your next reset.",
        audio_use="rain, ceramic mug touch, quiet room tone, soft no-lyric music",
        ending_pose="leaning on railing with mug near chest",
        emotional_payoff="grounded reset",
    ),
)


def _choose_template(video_id: str, user_seed: str | None) -> CreativeTemplate:
    seed = (user_seed or video_id).lower()
    if "spacex" in seed or "launch" in seed or "rocket" in seed:
        return TEMPLATES[0]
    if "market" in seed or "dessert" in seed or "choice" in seed:
        return TEMPLATES[1]
    if "rain" in seed or "balcony" in seed or "reset" in seed:
        return TEMPLATES[2]
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(TEMPLATES)
    return TEMPLATES[index]


def build_provisional_video_json(
    *,
    video_id: str,
    governed_date: str,
    daily_slot: str,
    user_seed: str | None = None,
    static_lena_character_authority: dict[str, Any] | None = None,
    current_video_policy: dict[str, Any] | None = None,
    current_business_intent: str | None = None,
    continuity_and_learning_ledger: dict[str, Any] | None = None,
    recent_content_history: list[dict[str, Any]] | None = None,
    prohibited_repetition_lockouts: list[str] | None = None,
    current_platform_needs: list[str] | None = None,
) -> dict[str, Any]:
    video_id = _as_non_empty_text(video_id, code="video_id_missing", label="video_id")
    governed_date = _as_non_empty_text(governed_date, code="governed_date_missing", label="governed_date")
    daily_slot = _as_non_empty_text(daily_slot, code="daily_slot_missing", label="daily_slot")
    template = _choose_template(video_id, user_seed)
    policy = current_video_policy or {}
    duration = int(policy.get("duration_seconds", 8))
    resolution = str(policy.get("resolution", "720p"))
    aspect_ratio = str(policy.get("aspect_ratio", "9:16"))
    platform_needs = current_platform_needs or ["reels_primary", "comment_or_save_intent"]

    hpe_timeline = [
        {"time_window": "0-2s", "action": f"establish hook: {template.hook}", "human_presence_goal": "clear attention shift"},
        {"time_window": "2-4s", "action": f"body beat: {template.principal_gesture} begins", "human_presence_goal": "readable motive"},
        {"time_window": "4-6s", "action": f"complete gesture: {template.principal_gesture}", "human_presence_goal": "single completed action"},
        {"time_window": "6-8s", "action": f"resolve: {template.ending_pose}", "human_presence_goal": template.emotional_payoff},
    ]
    if duration != 8:
        hpe_timeline[-1]["time_window"] = f"6-{duration}s"

    spec = {
        "schema_version": SCHEMA_VERSION,
        "authority_state": "provisional_requires_validation",
        "influencer_id": INFLUENCER_ID,
        "video_id": video_id,
        "governed_date": governed_date,
        "daily_slot": daily_slot,
        "concept": template.concept if user_seed is None else f"{template.concept} :: {user_seed.strip()}",
        "hook": template.hook,
        "business_intent": current_business_intent or template.business_intent,
        "environment": template.environment,
        "wardrobe": template.wardrobe,
        "outfit_family": template.outfit_family,
        "principal_gesture": template.principal_gesture,
        "emotional_arc": template.emotional_arc,
        "camera_contract": {
            "grammar": template.camera_grammar,
            "movement": template.camera_movement,
            "framing": "vertical social video; Lena remains the dominant subject; action relationship must be visually legible",
        },
        "camera_grammar": template.camera_grammar,
        "camera_movement": template.camera_movement,
        "audio_plan": template.audio_use,
        "caption_intent": {
            "cta": template.cta,
            "hook_structure": template.hook_structure,
            "platform_needs": platform_needs,
        },
        "provider_neutral_plan": {
            "duration_seconds": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "audio_enabled": bool(policy.get("audio_enabled", True)),
            "model_family": "provider_neutral_video",
            "no_provider_create_authority": True,
        },
        "hpe_timeline": hpe_timeline,
        "ending_pose": template.ending_pose,
        "hook_structure": template.hook_structure,
        "cta": template.cta,
        "audio_use": template.audio_use,
        "emotional_payoff": template.emotional_payoff,
        "assumptions": [
            "Static Lena identity authority is referenced, not regenerated.",
            "This provisional JSON is not execution authority.",
            "Separate novelty, schema, cross-artifact, compilation, inspection, cost, and paid authorization gates are required.",
        ],
        "source_inputs_summary": {
            "has_static_lena_character_authority": static_lena_character_authority is not None,
            "has_learning_ledger": continuity_and_learning_ledger is not None,
            "recent_history_count": len(recent_content_history or []),
            "prohibited_repetition_lockouts": prohibited_repetition_lockouts or [],
            "current_user_seed": user_seed,
        },
    }
    return spec


def validate_video_spec(spec: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(spec, dict), "spec_not_object", "video spec must be a JSON object")
    _require(spec.get("schema_version") == SCHEMA_VERSION, "spec_schema_mismatch", "unexpected video spec schema")
    _require(spec.get("authority_state") == "provisional_requires_validation", "spec_authority_state_invalid", "spec must remain provisional")
    for field in REQUIRED_CREATIVE_FIELDS:
        _require(field in spec, f"{field}_missing", f"{field} is required")
        _require(spec[field] not in ("", None, [], {}), f"{field}_empty", f"{field} must not be empty")
    _require(isinstance(spec.get("hpe_timeline"), list), "hpe_timeline_not_list", "hpe_timeline must be a list")
    _require(len(spec["hpe_timeline"]) >= 4, "hpe_timeline_too_short", "hpe_timeline must contain executable beats")
    plan = spec.get("provider_neutral_plan")
    _require(isinstance(plan, dict), "provider_plan_not_object", "provider_neutral_plan must be a JSON object")
    _require(plan.get("no_provider_create_authority") is True, "provider_plan_authorizes_create", "provider plan must not authorize create")
    return {"ok": True, "spec_sha256": sha256_json(spec)}


def _flatten_prompt_lines(spec: dict[str, Any]) -> list[str]:
    plan = spec["provider_neutral_plan"]
    timeline = " ".join(
        f"{beat['time_window']}: {beat['action']} ({beat['human_presence_goal']})."
        for beat in spec["hpe_timeline"]
    )
    return [
        LENA_ELEMENT_TOKEN,
        f"[Format] Exactly {plan['duration_seconds']} seconds, {plan['resolution']} portrait {plan['aspect_ratio']}, one continuous premium social-video shot.",
        f"[Identity] {STATIC_IDENTITY_LINE}",
        f"[Concept] {spec['concept']}",
        f"[Hook] {spec['hook']}",
        f"[Business Intent] {spec['business_intent']}",
        f"[Environment] {spec['environment']}",
        f"[Wardrobe] {spec['wardrobe']}",
        f"[Camera] {spec['camera_contract']['grammar']}; {spec['camera_contract']['movement']}; {spec['camera_contract']['framing']}.",
        f"[Human Presence Timeline] {timeline}",
        f"[Audio] {spec['audio_plan']}",
        f"[Caption Intent] {spec['caption_intent']['cta']} Hook structure: {spec['caption_intent']['hook_structure']}.",
        "[Hard constraints] Use the bound Lena Character Element; no unrelated reference asset; no publication authority; no queue authority; one provider create call only after separate paid authorization.",
    ]


def compile_provider_request(spec: dict[str, Any], *, attempt_id: str | None = None) -> dict[str, Any]:
    validation = validate_video_spec(spec)
    prompt_text = "\n".join(_flatten_prompt_lines(spec))
    provider_request = {
        "schema_version": "lena_compiled_video_provider_request_v1",
        "influencer_id": INFLUENCER_ID,
        "video_id": spec["video_id"],
        "governed_date": spec["governed_date"],
        "daily_slot": spec["daily_slot"],
        "attempt_id": attempt_id,
        "model_family": "seedance_2_0_mini_or_compatible_web_workflow",
        "duration_seconds": spec["provider_neutral_plan"]["duration_seconds"],
        "resolution": spec["provider_neutral_plan"]["resolution"],
        "aspect_ratio": spec["provider_neutral_plan"]["aspect_ratio"],
        "audio_enabled": spec["provider_neutral_plan"]["audio_enabled"],
        "lena_character_element_uuid": LENA_CHARACTER_ELEMENT_UUID,
        "prompt_text": prompt_text,
        "prompt_sha256": sha256_text(prompt_text),
        "prompt_utf8_bytes": len(prompt_text.encode("utf-8")),
        "prompt_transport_proof": {
            "character_element_token_first": prompt_text.startswith(LENA_ELEMENT_TOKEN),
            "first_token": LENA_ELEMENT_TOKEN,
        },
        "provider_call_authorized": False,
        "queue_authorized": False,
        "publication_authorized": False,
    }
    plan = {
        "video_id": spec["video_id"],
        "governed_date": spec["governed_date"],
        "daily_slot": spec["daily_slot"],
        "concept": spec["concept"],
        "environment": spec["environment"],
        "wardrobe": spec["wardrobe"],
        "provider_neutral_plan": deepcopy(spec["provider_neutral_plan"]),
    }
    request_without_hashes = deepcopy(provider_request)
    request_sha = sha256_json(request_without_hashes)
    provider_request["request_sha256"] = request_sha
    provider_request["plan_sha256"] = sha256_json(plan)
    provider_request["creative_spec_sha256"] = validation["spec_sha256"]
    provider_request["fingerprint_sha256"] = sha256_json(
        {
            "creative_spec_sha256": provider_request["creative_spec_sha256"],
            "prompt_sha256": provider_request["prompt_sha256"],
            "request_sha256": provider_request["request_sha256"],
            "plan_sha256": provider_request["plan_sha256"],
        }
    )
    return provider_request


def production_artifact_paths(root: Path, spec: dict[str, Any], *, attempt_number: int = 1) -> dict[str, str]:
    base = root / str(spec["governed_date"]) / str(spec["video_id"]) / f"attempt_{attempt_number:03d}"
    return {
        "creative_json": str(base / "creative_spec.json"),
        "compiled_request": str(base / "compiled_request.json"),
        "provider_prompt": str(base / "provider_prompt.txt"),
        "attempt_artifact": str(base / "attempt.json"),
    }


def run_novelty_governor(candidate: dict[str, Any], history: list[dict[str, Any]], *, lookback: int = 30) -> dict[str, Any]:
    validate_video_spec(candidate)
    recent = list(history or [])[:lookback]
    reasons: list[str] = []
    if recent:
        previous = recent[0]
        for field in CONSECUTIVE_LOCKOUT_FIELDS:
            if str(candidate.get(field, "")).strip().lower() == str(previous.get(field, "")).strip().lower():
                reasons.append(f"consecutive_reuse:{field}")
    for field in NOVELTY_COMPARE_FIELDS:
        same_count = sum(
            1
            for item in recent
            if str(candidate.get(field, "")).strip().lower() == str(item.get(field, "")).strip().lower()
        )
        if same_count >= 3:
            reasons.append(f"excessive_30_day_repetition:{field}:{same_count}")
    return {
        "ok": not reasons,
        "lookback_count": len(recent),
        "rejection_reasons": reasons,
        "compared_fields": list(NOVELTY_COMPARE_FIELDS),
        "consecutive_lockout_fields": list(CONSECUTIVE_LOCKOUT_FIELDS),
    }


def build_attempt_artifact(
    *,
    spec: dict[str, Any],
    compiled_request: dict[str, Any],
    attempt_number: int,
    superseded_attempt: dict[str, Any] | None = None,
    previous_qa_findings: list[str] | None = None,
    exact_creative_changes: list[str] | None = None,
    attempt_authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require(attempt_number >= 1, "attempt_number_invalid", "attempt number must be positive")
    validate_video_spec(spec)
    _require(compiled_request.get("video_id") == spec["video_id"], "attempt_video_mismatch", "compiled request video_id mismatch")
    _require(compiled_request.get("prompt_sha256") == sha256_text(compiled_request["prompt_text"]), "attempt_prompt_sha_mismatch", "compiled prompt sha mismatch")
    superseded_id = None
    previous_job_id = None
    if superseded_attempt:
        superseded_id = superseded_attempt.get("attempt_id")
        previous_job_id = superseded_attempt.get("provider_job_id")
    attempt_id = f"{spec['video_id']}-attempt-{attempt_number:03d}"
    artifact = {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "video_id": spec["video_id"],
        "governed_date": spec["governed_date"],
        "daily_slot": spec["daily_slot"],
        "attempt_number": attempt_number,
        "superseded_attempt_id": superseded_id,
        "previous_provider_job_id": previous_job_id,
        "previous_qa_findings": previous_qa_findings or [],
        "exact_creative_changes": exact_creative_changes or [],
        "compiled_prompt": compiled_request["prompt_text"],
        "new_prompt_sha256": compiled_request["prompt_sha256"],
        "new_request_sha256": compiled_request["request_sha256"],
        "attempt_authorization": attempt_authorization or {
            "provider_create_authorized": False,
            "authorized_attempts": 0,
            "retry_count": 0,
        },
        "retry_count": int((attempt_authorization or {}).get("retry_count", 0)),
        "provider_job_id": None,
        "qa_result": None,
    }
    if superseded_attempt and superseded_attempt.get("qa_result") == "qa_rejected":
        old_prompt_sha = superseded_attempt.get("new_prompt_sha256")
        _require(
            artifact["new_prompt_sha256"] != old_prompt_sha,
            "qa_rejected_attempt_prompt_reuse_blocked",
            "QA-rejected attempts require a new attempt artifact and a new compiled prompt for any new create call",
        )
    return artifact


def validate_prompt_reuse(
    *,
    prior_attempt: dict[str, Any],
    proposed_spec: dict[str, Any],
    proposed_request: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    validate_video_spec(proposed_spec)
    allowed_same_attempt_ops = {
        "same_provider_job_recovery",
        "same_ambiguous_submission_reconciliation",
        "same_result_download_or_validation",
        "deterministic_recompile_same_attempt",
    }
    prior_prompt_sha = prior_attempt.get("new_prompt_sha256") or prior_attempt.get("prompt_sha256")
    proposed_prompt_sha = proposed_request.get("prompt_sha256")
    same_prompt = prior_prompt_sha == proposed_prompt_sha
    same_video_identity = (
        prior_attempt.get("video_id") == proposed_spec.get("video_id")
        and prior_attempt.get("governed_date") == proposed_spec.get("governed_date")
        and prior_attempt.get("daily_slot") == proposed_spec.get("daily_slot")
    )

    if operation in allowed_same_attempt_ops and same_video_identity and same_prompt:
        return {"ok": True, "reuse_allowed_for": operation}

    if operation == "new_provider_create":
        blockers = []
        if same_prompt:
            blockers.append("compiled_prompt_reused_for_new_create")
        if not same_video_identity:
            blockers.append("video_date_or_slot_differs")
        if prior_attempt.get("qa_result") == "qa_rejected":
            blockers.append("prior_attempt_was_qa_rejected")
        if blockers:
            raise LenaVideoCreativeError("prompt_reuse_blocked", ", ".join(blockers))
        return {"ok": True, "reuse_allowed_for": "new_provider_create_with_fresh_prompt"}

    raise LenaVideoCreativeError("prompt_reuse_operation_not_allowed", f"operation is not allowed: {operation}")


def write_video_package(
    root: Path,
    spec: dict[str, Any],
    *,
    attempt_number: int = 1,
    superseded_attempt: dict[str, Any] | None = None,
    previous_qa_findings: list[str] | None = None,
    exact_creative_changes: list[str] | None = None,
) -> dict[str, Any]:
    compiled = compile_provider_request(spec, attempt_id=f"{spec['video_id']}-attempt-{attempt_number:03d}")
    attempt = build_attempt_artifact(
        spec=spec,
        compiled_request=compiled,
        attempt_number=attempt_number,
        superseded_attempt=superseded_attempt,
        previous_qa_findings=previous_qa_findings,
        exact_creative_changes=exact_creative_changes,
    )
    paths = production_artifact_paths(root, spec, attempt_number=attempt_number)
    for raw_path in paths.values():
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Path(paths["creative_json"]).write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(paths["compiled_request"]).write_text(json.dumps(compiled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(paths["provider_prompt"]).write_text(compiled["prompt_text"], encoding="utf-8")
    Path(paths["attempt_artifact"]).write_text(json.dumps(attempt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "paths": paths,
        "creative_spec_sha256": sha256_json(spec),
        "prompt_sha256": compiled["prompt_sha256"],
        "request_sha256": compiled["request_sha256"],
        "plan_sha256": compiled["plan_sha256"],
        "fingerprint_sha256": compiled["fingerprint_sha256"],
    }
