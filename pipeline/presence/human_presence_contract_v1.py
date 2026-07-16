from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _is_valid_git_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_GIT_SHA_RE.match(value))


class HumanPresenceContractError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HumanPresenceContractError(code, detail)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Generic, character-agnostic enum vocabularies.
#
# These describe PERFORMANCE MECHANICS, never a specific person's identity,
# body, or choreography. A character profile (a per-character adapter
# module, one per influencer) selects from this vocabulary and supplies its
# own character-specific body morphology and defaults; it must never need
# to extend this module's code to do so. See the body-presentation axis
# constants below (``BUST_EMPHASIS_LEVELS``, ``WAIST_HIP_CONTRAST_LEVELS``,
# etc.) for the generic/character-specific split for body presentation
# specifically.
# ---------------------------------------------------------------------------

VIEWER_RELATIONSHIP_MODES = (
    "one_person_intimate",
    "direct_address_performance",
    "ambient_unaware",
)
VIEWER_AWARENESS_LEVELS = ("fully_aware", "half_aware_glancing", "unaware")
EMOTIONAL_DISTANCE_LEVELS = ("intimate", "warm_approachable", "reserved", "distant")
INVITATION_LEVELS = ("none", "subtle", "clear", "overt")
PERFORMANCE_LEVELS = ("candid", "lightly_performed", "performed", "theatrical")

GAZE_START_FOCUS = ("off_camera_activity", "downward_or_aside", "middle_distance", "already_on_camera")
GAZE_DISCOVERY_TRIGGERS = (
    "sound_cue",
    "internal_thought",
    "movement_completion",
    "viewer_initiated",
    "none_already_aware",
)
GAZE_RECOGNITION_BEHAVIORS = (
    "soft_realization",
    "playful_surprise",
    "confident_acknowledgment",
    "shy_flicker",
)
GAZE_HOLD_INTENSITIES = ("brief", "moderate", "sustained", "prolonged_charged")
GAZE_RELEASE_BEHAVIORS = ("look_away_soft", "look_away_playful", "hold_to_fade", "return_to_activity")

EXPRESSION_START_STATES = ("neutral_focused", "content_private", "mildly_amused", "concentrating")
EXPRESSION_RECOGNITION_TRANSITIONS = ("slow_bloom", "quick_spark", "delayed_realization", "instant_light_up")
EXPRESSION_PEAK_STATES = (
    "warm_smile",
    "playful_smirk",
    "soft_intimate_smile",
    "laughing",
    "sultry_confident",
)
EXPRESSION_RELEASE_STATES = (
    "settling_smile",
    "lingering_amusement",
    "returning_to_neutral",
    "shy_look_down",
)

PERFORMANCE_ACTION_VOCABULARY = (
    "look_back",
    "turn_toward_camera",
    "hair_play",
    "laughter",
    "weight_shift",
    "stepping_closer",
    "leaning_in",
    "adjusting_clothing_naturally",
    "walking_with_a_simple_prop",
    "small_reaction_gesture",
    "none",
)
OBJECT_INTERACTIONS = (
    "none",
    "simple_prop_hold",
    "clothing_adjustment",
    "environment_touch",
    "phone_or_device",
    "drink_or_cup",
)
MOVEMENT_MOTIVATIONS = (
    "responding_to_viewer",
    "internal_impulse",
    "environmental_cue",
    "narrative_beat",
    "none_static",
)

WEIGHT_TRANSFER_MODES = ("shift_to_one_leg", "step_and_settle", "turn_with_hip_rotation", "static_grounded")
ASYMMETRY_LEVELS = ("symmetrical", "slight_asymmetry", "pronounced_asymmetry")
MOVEMENT_AMPLITUDES = ("micro", "subtle", "moderate", "full_body")
MOVEMENT_QUALITIES = ("fluid", "natural_relaxed", "deliberate_controlled", "hesitant")
BREATH_BODY_COUPLING_MODES = ("visible_breath_on_settle", "subtle_chest_rise", "not_emphasized")

SPEECH_ADDRESS_MODES = ("direct_to_viewer", "internal_monologue", "narrated_aside", "silent_performance")
SPEECH_PACING_MODES = ("relaxed", "conversational", "quick_playful", "deliberate_slow")
SPEECH_PAUSE_PATTERNS = ("natural_thinking_pause", "comedic_beat_pause", "breath_pause", "none")
LAUGHTER_BEHAVIORS = ("none", "soft_chuckle", "genuine_laugh", "suppressed_smile_laugh")

# Sensual presence must be built from performance qualities, never from
# exposure or sexual keywords -- "exposure"/"keywords" are deliberately not
# members of this vocabulary, so a caller cannot construct a valid contract
# that claims exposure itself as a source of sensual presence.
SENSUAL_PRESENCE_TIERS = (
    "none",
    "understated_confidence",
    "natural_sensual_presence",
    "overt_sensual_presence",
)
SENSUAL_PRESENCE_SOURCES = (
    "gaze",
    "anticipation",
    "movement",
    "confidence",
    "voice",
    "framing",
    "timing",
)
# "high" is intentionally absent: exposure/styling may never be the dominant
# driver of a sensual read. This is a structural guarantee, not a runtime
# check against a forbidden value -- the value literally cannot be
# constructed from this vocabulary.
SENSUAL_EXPOSURE_DEPENDENCY_LEVELS = ("none", "low", "moderate")
VIEWER_TENSION_LEVELS = ("none", "light_awareness", "charged_anticipation")
CONFIDENCE_LEVELS = ("shy", "comfortable", "confident", "commanding")

WARDROBE_BODY_INTERACTIONS = (
    "fabric_tension_visible",
    "loose_fit_no_tension",
    "structured_shapewear_effect",
    "natural_drape",
)
FRAMING_INTENTS = (
    "full_body_presence",
    "upper_body_intimate",
    "face_priority",
    "dynamic_motion_framing",
)

# Generic body-presentation AXES. The engine defines these axes; it never
# defines what value a specific character has on them. Any character's
# profile adapter supplies its own values here without requiring any
# change to this module.
BUST_EMPHASIS_LEVELS = ("understated", "moderate", "pronounced")
WAIST_HIP_CONTRAST_LEVELS = ("minimal", "moderate", "defined", "pronounced")
HIP_GLUTE_EMPHASIS_LEVELS = ("understated", "moderate", "pronounced")
PROPORTION_REALISM_LEVELS = ("stylized", "realistic", "required_realistic")
SILHOUETTE_SHAPE_CLASSES = (
    "slim_athletic",
    "athletic_toned",
    "hourglass_voluptuous",
    "curvy_soft",
    "petite_balanced",
)

ACTION_ENTRY_MODES = ("mid_activity", "fresh_entry", "continuation_from_prior_beat")
VIEWER_DISCOVERY_TIMINGS = ("early_beat", "mid_beat", "late_beat", "withheld_until_climax")
CONNECTION_PEAK_MODES = (
    "brief_acknowledgment",
    "sustained_engagement",
    "playful_tension_peak",
    "intimate_held_moment",
)
RELEASE_OR_EXIT_MODES = ("soft_release", "playful_release", "unresolved_lingering", "hard_cut_away")

# Fixed, closed vocabulary of presence failure indicators. This is defined
# here as the canonical list; a future QA consumer (not built in this
# change) would check generated output against these, never invent new
# indicators ad hoc.
PRESENCE_FAILURE_INDICATORS = (
    "dead_or_unfocused_eyes",
    "frozen_expression",
    "mannequin_pose",
    "unmotivated_movement",
    "continuous_camera_stare",
    "robotic_dialogue",
    "repeated_gesture_loop",
    "abrupt_motion_start_or_stop",
    "face_body_emotion_mismatch",
    "no_viewer_recognition_event",
    "sexual_styling_without_personality",
)

REQUIRED_TOP_LEVEL_SECTIONS = (
    "viewer_relationship",
    "gaze_arc",
    "expression_arc",
    "performance_actions",
    "movement_dynamics",
    "speech_behavior",
    "sensual_presence",
    "body_presentation",
    "temporal_beats",
    "character_doctrine_provenance",
)


def _require_enum(value: Any, allowed: tuple[str, ...], field_path: str) -> None:
    _require(
        isinstance(value, str) and value in allowed,
        "unknown_enum_value",
        f"{field_path} must be one of {allowed!r}, got {value!r}",
    )


def _require_bool(value: Any, field_path: str) -> None:
    _require(isinstance(value, bool), "invalid_field_type", f"{field_path} must be a boolean")


def _validate_viewer_relationship(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "viewer_relationship must be a JSON object")
    _require_enum(section.get("mode"), VIEWER_RELATIONSHIP_MODES, "viewer_relationship.mode")
    _require_enum(section.get("awareness"), VIEWER_AWARENESS_LEVELS, "viewer_relationship.awareness")
    _require_enum(
        section.get("emotional_distance"), EMOTIONAL_DISTANCE_LEVELS, "viewer_relationship.emotional_distance"
    )
    _require_enum(section.get("invitation_level"), INVITATION_LEVELS, "viewer_relationship.invitation_level")
    _require_enum(section.get("performance_level"), PERFORMANCE_LEVELS, "viewer_relationship.performance_level")


def _validate_gaze_arc(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "gaze_arc must be a JSON object")
    _require_enum(section.get("start_focus"), GAZE_START_FOCUS, "gaze_arc.start_focus")
    _require_enum(section.get("discovery_trigger"), GAZE_DISCOVERY_TRIGGERS, "gaze_arc.discovery_trigger")
    _require_enum(
        section.get("recognition_behavior"), GAZE_RECOGNITION_BEHAVIORS, "gaze_arc.recognition_behavior"
    )
    _require_enum(section.get("hold_intensity"), GAZE_HOLD_INTENSITIES, "gaze_arc.hold_intensity")
    _require_enum(section.get("release_behavior"), GAZE_RELEASE_BEHAVIORS, "gaze_arc.release_behavior")


def _validate_expression_arc(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "expression_arc must be a JSON object")
    _require_enum(section.get("start_state"), EXPRESSION_START_STATES, "expression_arc.start_state")
    _require_enum(
        section.get("recognition_transition"),
        EXPRESSION_RECOGNITION_TRANSITIONS,
        "expression_arc.recognition_transition",
    )
    _require_enum(section.get("peak_state"), EXPRESSION_PEAK_STATES, "expression_arc.peak_state")
    _require_enum(section.get("release_state"), EXPRESSION_RELEASE_STATES, "expression_arc.release_state")


def _validate_performance_actions(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "performance_actions must be a JSON object")
    _require_enum(
        section.get("primary_action"), PERFORMANCE_ACTION_VOCABULARY, "performance_actions.primary_action"
    )
    _require_enum(
        section.get("secondary_action"), PERFORMANCE_ACTION_VOCABULARY, "performance_actions.secondary_action"
    )
    _require_enum(
        section.get("object_interaction"), OBJECT_INTERACTIONS, "performance_actions.object_interaction"
    )
    _require_enum(
        section.get("movement_motivation"), MOVEMENT_MOTIVATIONS, "performance_actions.movement_motivation"
    )
    _require_bool(
        section.get("settling_motion_required"), "performance_actions.settling_motion_required"
    )


def _validate_movement_dynamics(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "movement_dynamics must be a JSON object")
    _require_enum(section.get("weight_transfer"), WEIGHT_TRANSFER_MODES, "movement_dynamics.weight_transfer")
    _require_enum(section.get("asymmetry_level"), ASYMMETRY_LEVELS, "movement_dynamics.asymmetry_level")
    _require_enum(
        section.get("movement_amplitude"), MOVEMENT_AMPLITUDES, "movement_dynamics.movement_amplitude"
    )
    _require_enum(section.get("movement_quality"), MOVEMENT_QUALITIES, "movement_dynamics.movement_quality")
    _require_bool(section.get("continuity_required"), "movement_dynamics.continuity_required")
    _require_enum(
        section.get("breath_body_coupling"),
        BREATH_BODY_COUPLING_MODES,
        "movement_dynamics.breath_body_coupling",
    )


def _validate_speech_behavior(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "speech_behavior must be a JSON object")
    _require_enum(section.get("address_mode"), SPEECH_ADDRESS_MODES, "speech_behavior.address_mode")
    _require_enum(section.get("pacing"), SPEECH_PACING_MODES, "speech_behavior.pacing")
    _require_enum(section.get("pause_pattern"), SPEECH_PAUSE_PATTERNS, "speech_behavior.pause_pattern")
    _require_bool(section.get("breath_visibility"), "speech_behavior.breath_visibility")
    _require_enum(section.get("laughter_behavior"), LAUGHTER_BEHAVIORS, "speech_behavior.laughter_behavior")
    _require_bool(section.get("self_correction_allowed"), "speech_behavior.self_correction_allowed")
    _require_bool(section.get("reaction_before_dialogue"), "speech_behavior.reaction_before_dialogue")


def _validate_sensual_presence(section: Any, *, adult_character_required: bool) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "sensual_presence must be a JSON object")
    tier = section.get("tier")
    _require_enum(tier, SENSUAL_PRESENCE_TIERS, "sensual_presence.tier")

    sources = section.get("sources")
    _require(isinstance(sources, list), "invalid_field_type", "sensual_presence.sources must be a list")
    _require(
        set(sources).issubset(set(SENSUAL_PRESENCE_SOURCES)),
        "unknown_enum_value",
        f"sensual_presence.sources must be a subset of {SENSUAL_PRESENCE_SOURCES!r}, got {sources!r}",
    )
    if tier != "none":
        _require(
            bool(sources),
            "sensual_presence_missing_sources",
            "sensual_presence.sources must be non-empty when tier is not 'none' -- "
            "sensual presence must come from performance qualities, not exposure alone",
        )
        # This is the mandatory adult-only gate: a non-"none" sensual tier
        # may never validate unless the character profile has separately
        # confirmed adult presentation. Sensuality can raise this
        # requirement's stakes but can never satisfy it -- the flag must
        # already be true, supplied by body_presentation independently.
        _require(
            adult_character_required is True,
            "sensual_mode_requires_adult_character",
            "sensual_presence.tier other than 'none' requires body_presentation.adult_character_required to be true",
        )

    _require_enum(
        section.get("exposure_dependency"),
        SENSUAL_EXPOSURE_DEPENDENCY_LEVELS,
        "sensual_presence.exposure_dependency",
    )
    _require_enum(section.get("viewer_tension"), VIEWER_TENSION_LEVELS, "sensual_presence.viewer_tension")
    _require_enum(section.get("confidence_level"), CONFIDENCE_LEVELS, "sensual_presence.confidence_level")


def _validate_body_presentation(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "body_presentation must be a JSON object")
    _require_bool(section.get("adult_character_required"), "body_presentation.adult_character_required")

    silhouette = section.get("silhouette_profile")
    _require(
        isinstance(silhouette, dict), "invalid_field_type", "body_presentation.silhouette_profile must be a JSON object"
    )
    _require_enum(
        silhouette.get("bust_emphasis"), BUST_EMPHASIS_LEVELS, "body_presentation.silhouette_profile.bust_emphasis"
    )
    _require_enum(
        silhouette.get("waist_hip_contrast"),
        WAIST_HIP_CONTRAST_LEVELS,
        "body_presentation.silhouette_profile.waist_hip_contrast",
    )
    _require_enum(
        silhouette.get("hip_glute_emphasis"),
        HIP_GLUTE_EMPHASIS_LEVELS,
        "body_presentation.silhouette_profile.hip_glute_emphasis",
    )
    _require_enum(
        silhouette.get("proportion_realism"),
        PROPORTION_REALISM_LEVELS,
        "body_presentation.silhouette_profile.proportion_realism",
    )
    _require_enum(
        silhouette.get("silhouette_shape_class"),
        SILHOUETTE_SHAPE_CLASSES,
        "body_presentation.silhouette_profile.silhouette_shape_class",
    )

    _require_enum(
        section.get("wardrobe_body_interaction"),
        WARDROBE_BODY_INTERACTIONS,
        "body_presentation.wardrobe_body_interaction",
    )
    _require_bool(
        section.get("anatomy_continuity_required"), "body_presentation.anatomy_continuity_required"
    )
    _require(
        section.get("anatomy_continuity_required") is True,
        "anatomy_continuity_must_remain_required",
        "body_presentation.anatomy_continuity_required must always be true -- this is a hard "
        "identity/safety guarantee that no presence profile may relax",
    )
    _require_bool(
        section.get("gravity_and_soft_tissue_realism"), "body_presentation.gravity_and_soft_tissue_realism"
    )
    _require_enum(section.get("framing_intent"), FRAMING_INTENTS, "body_presentation.framing_intent")


def _validate_temporal_beats(section: Any) -> None:
    _require(isinstance(section, dict), "invalid_field_type", "temporal_beats must be a JSON object")
    _require_enum(section.get("action_entry"), ACTION_ENTRY_MODES, "temporal_beats.action_entry")
    _require_enum(
        section.get("viewer_discovery"), VIEWER_DISCOVERY_TIMINGS, "temporal_beats.viewer_discovery"
    )
    _require_enum(section.get("connection_peak"), CONNECTION_PEAK_MODES, "temporal_beats.connection_peak")
    _require_enum(section.get("release_or_exit"), RELEASE_OR_EXIT_MODES, "temporal_beats.release_or_exit")


def _validate_character_doctrine_provenance(section: Any) -> None:
    _require(
        isinstance(section, dict), "invalid_field_type", "character_doctrine_provenance must be a JSON object"
    )
    path_value = section.get("source_doctrine_artifact_path")
    sha_value = section.get("source_doctrine_artifact_sha256")
    _require(
        isinstance(path_value, str) and path_value.strip(),
        "doctrine_provenance_missing",
        "character_doctrine_provenance.source_doctrine_artifact_path must be a non-empty string",
    )
    _require(
        isinstance(sha_value, str) and len(sha_value) == 64,
        "doctrine_provenance_missing",
        "character_doctrine_provenance.source_doctrine_artifact_sha256 must be a 64-character sha256",
    )
    _require(
        isinstance(section.get("doctrine_version"), str) and section["doctrine_version"].strip(),
        "doctrine_provenance_missing",
        "character_doctrine_provenance.doctrine_version must be a non-empty string",
    )
    _require(
        _is_valid_git_sha(section.get("doctrine_authored_against_repository_revision")),
        "doctrine_provenance_missing",
        "character_doctrine_provenance.doctrine_authored_against_repository_revision must be a 40-character lowercase git sha",
    )

    resolved_path = (ROOT / path_value).resolve()
    try:
        resolved_path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise HumanPresenceContractError(
            "doctrine_provenance_path_outside_repository",
            f"character_doctrine_provenance path escapes the repository root: {path_value}",
        ) from exc

    _require(
        resolved_path.is_file(),
        "doctrine_provenance_stale",
        f"character_doctrine_provenance references a doctrine artifact that no longer exists on disk: {path_value}",
    )
    live_sha256 = _sha256_bytes(resolved_path.read_bytes())
    _require(
        live_sha256 == sha_value,
        "doctrine_provenance_stale",
        "character_doctrine_provenance.source_doctrine_artifact_sha256 no longer matches the live doctrine "
        "file -- the doctrine changed since this binding was recorded and must be re-validated, not trusted",
    )


_SECTION_VALIDATORS = {
    "viewer_relationship": _validate_viewer_relationship,
    "gaze_arc": _validate_gaze_arc,
    "expression_arc": _validate_expression_arc,
    "performance_actions": _validate_performance_actions,
    "movement_dynamics": _validate_movement_dynamics,
    "speech_behavior": _validate_speech_behavior,
    "body_presentation": _validate_body_presentation,
    "temporal_beats": _validate_temporal_beats,
    "character_doctrine_provenance": _validate_character_doctrine_provenance,
}


def validate_presence_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a Human Presence Engine contract instance.

    This is the single generic validation entry point every character
    profile adapter must call. A character-specific adapter must never
    re-implement or duplicate any rule defined here -- it only supplies data.

    Fails closed (raises ``HumanPresenceContractError``) on: any unknown
    enum value, any missing/malformed section, a sensual-presence tier that
    is not "none" without ``body_presentation.adult_character_required``
    being true, and stale/mismatched character-doctrine provenance.

    Returns the validated payload unchanged on success.
    """
    _require(isinstance(payload, dict), "invalid_field_type", "presence contract payload must be a JSON object")
    _require(
        payload.get("schema_version") == "human_presence_contract_v1",
        "unknown_schema_version",
        "unexpected human presence contract schema_version",
    )

    for section_name in REQUIRED_TOP_LEVEL_SECTIONS:
        _require(
            section_name in payload,
            "missing_required_section",
            f"missing required section: {section_name}",
        )

    for section_name in REQUIRED_TOP_LEVEL_SECTIONS:
        if section_name == "sensual_presence":
            continue
        _SECTION_VALIDATORS[section_name](payload[section_name])

    # Validated after body_presentation so the adult-character gate can be
    # cross-checked. This is the ONLY place sensual_presence and
    # body_presentation interact: a one-way requirement (sensual tier
    # requires adult confirmation), never the reverse, and never a scoring
    # interaction. Safety (adult confirmation, anatomy continuity) is
    # decided entirely within body_presentation and cannot be raised or
    # lowered by anything in sensual_presence.
    body_presentation = payload["body_presentation"]
    adult_character_required = bool(body_presentation.get("adult_character_required"))
    _validate_sensual_presence(
        payload["sensual_presence"], adult_character_required=adult_character_required
    )

    return payload


def presence_failure_indicators() -> tuple[str, ...]:
    return PRESENCE_FAILURE_INDICATORS
