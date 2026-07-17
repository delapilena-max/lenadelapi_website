from __future__ import annotations

from copy import deepcopy
from typing import Any

from pipeline.presence import human_presence_contract_v1 as hpe


SCHEMA_VERSION = "human_presence_prompt_plan_v1"
MEDIA_INTERPRETATIONS = ("still_image", "motion")


class HumanPresencePromptPlanError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HumanPresencePromptPlanError(code, detail)


def _normalize_medium(medium: str) -> str:
    value = str(medium or "").strip().lower()
    if value not in MEDIA_INTERPRETATIONS:
        raise HumanPresencePromptPlanError(
            "unknown_medium_interpretation",
            f"medium must be one of {MEDIA_INTERPRETATIONS!r}, got {medium!r}",
        )
    return value


def _clean_terms(*values: str) -> list[str]:
    terms: list[str] = []
    for value in values:
        text = " ".join(part for part in str(value or "").replace("-", "_").split("_") if part).strip()
        if text and text not in terms:
            terms.append(text)
    return terms


def _enum_terms(value: str, *extra_terms: str) -> list[str]:
    terms = _clean_terms(value)
    for term in extra_terms:
        clean = str(term or "").strip().lower()
        if clean and clean not in terms:
            terms.append(clean)
    return terms


def _section_record(contract_section: dict[str, Any], directive: str, selector_terms: list[str]) -> dict[str, Any]:
    return {
        "contract": deepcopy(contract_section),
        "directive": directive,
        "selector_terms": selector_terms,
    }


def _viewer_relationship_section(section: dict[str, Any]) -> dict[str, Any]:
    mode = str(section["mode"])
    awareness = str(section["awareness"])
    emotional_distance = str(section["emotional_distance"])
    invitation_level = str(section["invitation_level"])
    performance_level = str(section["performance_level"])
    directive = (
        f"viewer relationship: {mode.replace('_', ' ')}; "
        f"awareness {awareness.replace('_', ' ')}; "
        f"distance {emotional_distance.replace('_', ' ')}; "
        f"invitation {invitation_level.replace('_', ' ')}; "
        f"performance {performance_level.replace('_', ' ')}"
    )
    selector_terms = _clean_terms(
        mode,
        awareness,
        emotional_distance,
        invitation_level,
        performance_level,
        "viewer",
        "direct address",
        "approachable",
        "warm",
        "intimate",
    )
    return _section_record(section, directive, selector_terms)


def _gaze_arc_section(section: dict[str, Any]) -> dict[str, Any]:
    start_focus = str(section["start_focus"])
    discovery_trigger = str(section["discovery_trigger"])
    recognition_behavior = str(section["recognition_behavior"])
    hold_intensity = str(section["hold_intensity"])
    release_behavior = str(section["release_behavior"])
    directive = (
        f"gaze arc: begin from {start_focus.replace('_', ' ')}; "
        f"discover through {discovery_trigger.replace('_', ' ')}; "
        f"recognition reads as {recognition_behavior.replace('_', ' ')}; "
        f"hold intensity {hold_intensity.replace('_', ' ')}; "
        f"release as {release_behavior.replace('_', ' ')}"
    )
    selector_terms = _clean_terms(
        start_focus,
        discovery_trigger,
        recognition_behavior,
        hold_intensity,
        release_behavior,
        "gaze",
        "eye contact",
        "playful",
        "confident",
        "surprise",
        "recognition",
        "hold",
        "release",
    )
    return _section_record(section, directive, selector_terms)


def _expression_arc_section(section: dict[str, Any]) -> dict[str, Any]:
    start_state = str(section["start_state"])
    recognition_transition = str(section["recognition_transition"])
    peak_state = str(section["peak_state"])
    release_state = str(section["release_state"])
    directive = (
        f"expression arc: start {start_state.replace('_', ' ')}; "
        f"transition {recognition_transition.replace('_', ' ')}; "
        f"peak {peak_state.replace('_', ' ')}; "
        f"release {release_state.replace('_', ' ')}"
    )
    selector_terms = _clean_terms(
        start_state,
        recognition_transition,
        peak_state,
        release_state,
        "expression",
        "smile",
        "smirk",
        "warm",
        "playful",
        "confident",
        "spark",
        "bloom",
    )
    return _section_record(section, directive, selector_terms)


def _performance_actions_section(section: dict[str, Any]) -> dict[str, Any]:
    primary_action = str(section["primary_action"])
    secondary_action = str(section["secondary_action"])
    object_interaction = str(section["object_interaction"])
    movement_motivation = str(section["movement_motivation"])
    settling_motion_required = bool(section["settling_motion_required"])
    directive = (
        f"actions: primary {primary_action.replace('_', ' ')}; "
        f"secondary {secondary_action.replace('_', ' ')}; "
        f"object interaction {object_interaction.replace('_', ' ')}; "
        f"movement motivated by {movement_motivation.replace('_', ' ')}; "
        f"settling motion required {settling_motion_required}"
    )
    selector_terms = _clean_terms(
        primary_action,
        secondary_action,
        object_interaction,
        movement_motivation,
        "hair",
        "weight shift",
        "turn toward camera",
        "leaning in",
        "look back",
        "reaction",
        "gesture",
        "settle",
    )
    return _section_record(section, directive, selector_terms)


def _movement_dynamics_section(section: dict[str, Any]) -> dict[str, Any]:
    weight_transfer = str(section["weight_transfer"])
    asymmetry_level = str(section["asymmetry_level"])
    movement_amplitude = str(section["movement_amplitude"])
    movement_quality = str(section["movement_quality"])
    breath_body_coupling = str(section["breath_body_coupling"])
    directive = (
        f"movement: weight transfer {weight_transfer.replace('_', ' ')}; "
        f"asymmetry {asymmetry_level.replace('_', ' ')}; "
        f"amplitude {movement_amplitude.replace('_', ' ')}; "
        f"quality {movement_quality.replace('_', ' ')}; "
        f"breath-body coupling {breath_body_coupling.replace('_', ' ')}"
    )
    selector_terms = _clean_terms(
        weight_transfer,
        asymmetry_level,
        movement_amplitude,
        movement_quality,
        breath_body_coupling,
        "natural",
        "relaxed",
        "subtle",
        "fluid",
        "breath",
        "shift",
        "turn",
    )
    return _section_record(section, directive, selector_terms)


def _speech_behavior_section(section: dict[str, Any], medium: str) -> dict[str, Any]:
    address_mode = str(section["address_mode"])
    pacing = str(section["pacing"])
    pause_pattern = str(section["pause_pattern"])
    laughter_behavior = str(section["laughter_behavior"])
    breath_visibility = bool(section["breath_visibility"])
    self_correction_allowed = bool(section["self_correction_allowed"])
    reaction_before_dialogue = bool(section["reaction_before_dialogue"])
    if medium == "still_image":
        medium_note = (
            "still image interpretation: a silent pre-response beat, with the reaction "
            "readable through timing and expression rather than spoken dialogue"
        )
    else:
        medium_note = (
            "motion interpretation: preserve the speech rhythm, pause pattern, and "
            "reaction timing across the full arc"
        )
    directive = (
        f"speech/reaction: {address_mode.replace('_', ' ')}; "
        f"pacing {pacing.replace('_', ' ')}; "
        f"pause {pause_pattern.replace('_', ' ')}; "
        f"laughter {laughter_behavior.replace('_', ' ')}; "
        f"breath visibility {breath_visibility}; "
        f"self-correction allowed {self_correction_allowed}; "
        f"reaction before dialogue {reaction_before_dialogue}; "
        f"{medium_note}"
    )
    selector_terms = _clean_terms(
        address_mode,
        pacing,
        pause_pattern,
        laughter_behavior,
        "reaction",
        "dialogue",
        "rhythm",
        "pause",
        "silent",
        "direct",
        "viewer",
        "conversational",
        "chuckle",
    )
    return _section_record(section, directive, selector_terms)


def _sensual_presence_section(section: dict[str, Any]) -> dict[str, Any]:
    tier = str(section["tier"])
    sources = [str(item) for item in section["sources"]]
    exposure_dependency = str(section["exposure_dependency"])
    viewer_tension = str(section["viewer_tension"])
    confidence_level = str(section["confidence_level"])
    directive = (
        f"sensual presence: tier {tier.replace('_', ' ')}; "
        f"sources {', '.join(source.replace('_', ' ') for source in sources)}; "
        f"exposure dependency {exposure_dependency.replace('_', ' ')}; "
        f"viewer tension {viewer_tension.replace('_', ' ')}; "
        f"confidence {confidence_level.replace('_', ' ')}"
    )
    selector_terms = _clean_terms(
        tier,
        *sources,
        exposure_dependency,
        viewer_tension,
        confidence_level,
        "gaze",
        "movement",
        "confidence",
        "timing",
        "voice",
        "framing",
    )
    return _section_record(section, directive, selector_terms)


def _body_presentation_section(section: dict[str, Any]) -> dict[str, Any]:
    silhouette = section["silhouette_profile"]
    framing_intent = str(section["framing_intent"])
    directive = (
        "body presentation: adult character required; "
        f"silhouette profile {silhouette['silhouette_shape_class'].replace('_', ' ')}; "
        f"framing intent {framing_intent.replace('_', ' ')}; "
        "anatomy continuity and realistic proportions remain mandatory"
    )
    selector_terms = _clean_terms(
        silhouette["bust_emphasis"],
        silhouette["waist_hip_contrast"],
        silhouette["hip_glute_emphasis"],
        silhouette["proportion_realism"],
        silhouette["silhouette_shape_class"],
        framing_intent,
        "adult",
        "anatomy continuity",
        "realistic proportions",
        "full body presence",
        "upper body intimate",
        "face priority",
        "dynamic motion framing",
    )
    return _section_record(section, directive, selector_terms)


def _temporal_beats_section(section: dict[str, Any]) -> dict[str, Any]:
    action_entry = str(section["action_entry"])
    viewer_discovery = str(section["viewer_discovery"])
    connection_peak = str(section["connection_peak"])
    release_or_exit = str(section["release_or_exit"])
    directive = (
        f"temporal beats: entry {action_entry.replace('_', ' ')}; "
        f"viewer discovery {viewer_discovery.replace('_', ' ')}; "
        f"connection peak {connection_peak.replace('_', ' ')}; "
        f"release or exit {release_or_exit.replace('_', ' ')}"
    )
    selector_terms = _clean_terms(
        action_entry,
        viewer_discovery,
        connection_peak,
        release_or_exit,
        "mid activity",
        "mid beat",
        "sustained engagement",
        "playful release",
    )
    return _section_record(section, directive, selector_terms)


def _prompt_text_from_plan(plan: dict[str, Any], medium: str) -> str:
    viewer = plan["viewer_relationship"]["directive"]
    gaze = plan["gaze_arc"]["directive"]
    expression = plan["expression_arc"]["directive"]
    actions = plan["performance_actions"]["directive"]
    movement = plan["movement_dynamics"]["directive"]
    speech = plan["speech_behavior"]["directive"]
    sensual = plan["sensual_presence"]["directive"]
    body = plan["body_presentation"]["directive"]
    temporal = plan["temporal_beats"]["directive"]
    failure_indicators = ", ".join(
        str(item).replace("_", " ") for item in plan.get("failure_indicators", []) if str(item).strip()
    )
    failure_avoidance = (
        f"presence-failure avoidance: avoid {failure_indicators}"
        if failure_indicators
        else "presence-failure avoidance: avoid dead or unfocused eyes, frozen expression, mannequin pose, face-body emotion mismatch, and sexual styling without personality"
    )
    if medium == "still_image":
        return (
            "Presence direction: "
            f"{viewer}. {gaze}. {expression}. {actions}. {movement}. "
            f"{speech}. {sensual}. {body}. {temporal}. {failure_avoidance}."
        )
    return (
        "Presence direction: "
        f"{viewer}. {gaze}. {expression}. {actions}. {movement}. "
        f"{speech}. {sensual}. {body}. {temporal}. {failure_avoidance}."
    )


def compile_human_presence_prompt_plan(contract: dict[str, Any], *, medium: str) -> dict[str, Any]:
    validated = deepcopy(hpe.validate_presence_contract(contract))
    medium_value = _normalize_medium(medium)

    plan = {
        "schema_version": SCHEMA_VERSION,
        "medium_interpretation": medium_value,
        "viewer_relationship": _viewer_relationship_section(validated["viewer_relationship"]),
        "gaze_arc": _gaze_arc_section(validated["gaze_arc"]),
        "expression_arc": _expression_arc_section(validated["expression_arc"]),
        "performance_actions": _performance_actions_section(validated["performance_actions"]),
        "movement_dynamics": _movement_dynamics_section(validated["movement_dynamics"]),
        "speech_behavior": _speech_behavior_section(validated["speech_behavior"], medium_value),
        "sensual_presence": _sensual_presence_section(validated["sensual_presence"]),
        "body_presentation": _body_presentation_section(validated["body_presentation"]),
        "temporal_beats": _temporal_beats_section(validated["temporal_beats"]),
        "failure_indicators": list(hpe.presence_failure_indicators()),
        "character_doctrine_provenance": deepcopy(validated["character_doctrine_provenance"]),
    }

    selector_bias_terms = {
        "scene": _clean_terms(
            *plan["viewer_relationship"]["selector_terms"],
            *plan["temporal_beats"]["selector_terms"],
        ),
        "expression_gaze": _clean_terms(
            *plan["viewer_relationship"]["selector_terms"],
            *plan["gaze_arc"]["selector_terms"],
            *plan["expression_arc"]["selector_terms"],
            *plan["sensual_presence"]["selector_terms"],
        ),
        "pose_body_language": _clean_terms(
            *plan["performance_actions"]["selector_terms"],
            *plan["movement_dynamics"]["selector_terms"],
            *plan["body_presentation"]["selector_terms"],
            *plan["temporal_beats"]["selector_terms"],
        ),
        "reference_mode": _clean_terms(
            *plan["body_presentation"]["selector_terms"],
            *plan["viewer_relationship"]["selector_terms"],
            *plan["temporal_beats"]["selector_terms"],
        ),
        "wardrobe": _clean_terms(
            *plan["body_presentation"]["selector_terms"],
            *plan["sensual_presence"]["selector_terms"],
            *plan["viewer_relationship"]["selector_terms"],
        ),
    }
    plan["selector_bias_terms"] = selector_bias_terms
    plan["selector_weight_adjustments_changed"] = any(selector_bias_terms.values())
    plan["prompt_text"] = _prompt_text_from_plan(plan, medium_value)

    return plan
