from __future__ import annotations

from typing import Any

from pipeline.identity import lena_character_doctrine_validate_v1 as doctrine
from pipeline.presence import human_presence_contract_v1 as hpe

# ---------------------------------------------------------------------------
# Lena's body morphology, expressed purely as values along the GENERIC
# axes the engine defines (bust_emphasis, waist_hip_contrast,
# hip_glute_emphasis, proportion_realism, silhouette_shape_class). This
# module supplies the physique; pipeline/presence/human_presence_contract_v1.py
# defines what axes exist and validates them -- it has no knowledge that
# "Lena" or "voluptuous" exist. Preserves Lena's established highly
# voluptuous adult silhouette: full bust, prominent hips and glutes, a
# defined waist-to-hip contrast, and realistic (not stylized) proportions.
# ---------------------------------------------------------------------------
LENA_SILHOUETTE_PROFILE: dict[str, str] = {
    "bust_emphasis": "pronounced",
    "waist_hip_contrast": "pronounced",
    "hip_glute_emphasis": "pronounced",
    "proportion_realism": "required_realistic",
    "silhouette_shape_class": "hourglass_voluptuous",
}

# Default performance template for Lena. This is data the adapter owns;
# none of it re-implements the generic validator's rules -- it only
# supplies values from the engine's own vocabularies, which
# ``hpe.validate_presence_contract`` checks against the same constants this
# module imports rather than duplicating.
LENA_DEFAULT_PRESENCE_TEMPLATE: dict[str, Any] = {
    "schema_version": "human_presence_contract_v1",
    "viewer_relationship": {
        "mode": "one_person_intimate",
        "awareness": "fully_aware",
        "emotional_distance": "warm_approachable",
        "invitation_level": "clear",
        "performance_level": "lightly_performed",
    },
    "gaze_arc": {
        "start_focus": "off_camera_activity",
        "discovery_trigger": "internal_thought",
        "recognition_behavior": "playful_surprise",
        "hold_intensity": "sustained",
        "release_behavior": "look_away_playful",
    },
    "expression_arc": {
        "start_state": "content_private",
        "recognition_transition": "quick_spark",
        "peak_state": "playful_smirk",
        "release_state": "lingering_amusement",
    },
    "performance_actions": {
        "primary_action": "hair_play",
        "secondary_action": "weight_shift",
        "object_interaction": "none",
        "movement_motivation": "internal_impulse",
        "settling_motion_required": True,
    },
    "movement_dynamics": {
        "weight_transfer": "shift_to_one_leg",
        "asymmetry_level": "slight_asymmetry",
        "movement_amplitude": "subtle",
        "movement_quality": "natural_relaxed",
        "continuity_required": True,
        "breath_body_coupling": "subtle_chest_rise",
    },
    "speech_behavior": {
        "address_mode": "direct_to_viewer",
        "pacing": "conversational",
        "pause_pattern": "natural_thinking_pause",
        "breath_visibility": True,
        "laughter_behavior": "soft_chuckle",
        "self_correction_allowed": True,
        "reaction_before_dialogue": True,
    },
    "sensual_presence": {
        "tier": "natural_sensual_presence",
        "sources": ["gaze", "confidence", "movement", "timing"],
        "exposure_dependency": "low",
        "viewer_tension": "light_awareness",
        "confidence_level": "confident",
    },
    "body_presentation": {
        "adult_character_required": True,
        "silhouette_profile": dict(LENA_SILHOUETTE_PROFILE),
        "wardrobe_body_interaction": "fabric_tension_visible",
        "anatomy_continuity_required": True,
        "gravity_and_soft_tissue_realism": True,
        "framing_intent": "full_body_presence",
    },
    "temporal_beats": {
        "action_entry": "mid_activity",
        "viewer_discovery": "mid_beat",
        "connection_peak": "sustained_engagement",
        "release_or_exit": "playful_release",
    },
    # character_doctrine_provenance is injected at build time from the live
    # doctrine file -- never hard-coded here, so a stale binding is always
    # caught by the generic validator's re-hash check.
}


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _confirm_doctrine_supports_adult_and_voluptuous_claims() -> None:
    """Light cross-check only -- does not duplicate the generic validator's
    rules, and does not duplicate the doctrine's own validator. Confirms
    the doctrine this adapter binds to actually backs the claims this
    profile makes (adult presentation, body-identity continuity) before
    building a contract from it.
    """
    payload = doctrine.load_doctrine()
    requirements = payload["hard_identity_continuity"]["requirements"]
    if "adult_presentation_required" not in requirements:
        raise hpe.HumanPresenceContractError(
            "doctrine_does_not_confirm_adult_presentation",
            "Lena's character doctrine no longer lists adult_presentation_required; "
            "the Lena presence profile cannot claim an adult sensual mode without it",
        )
    if "stable_body_identity" not in requirements:
        raise hpe.HumanPresenceContractError(
            "doctrine_does_not_confirm_body_identity",
            "Lena's character doctrine no longer lists stable_body_identity; "
            "the Lena presence profile's silhouette claims depend on that continuity guarantee",
        )


def build_lena_presence_contract(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build and validate a Lena Human Presence Engine contract instance.

    Merges ``overrides`` onto ``LENA_DEFAULT_PRESENCE_TEMPLATE``, injects a
    freshly-computed doctrine provenance binding, and validates the result
    through the GENERIC engine validator
    (``human_presence_contract_v1.validate_presence_contract``) -- this
    function contains no independent validation logic of its own.
    """
    _confirm_doctrine_supports_adult_and_voluptuous_claims()

    payload = _deep_merge(LENA_DEFAULT_PRESENCE_TEMPLATE, overrides or {})
    payload["character_doctrine_provenance"] = doctrine.doctrine_provenance()

    return hpe.validate_presence_contract(payload)


def lena_silhouette_profile() -> dict[str, str]:
    return dict(LENA_SILHOUETTE_PROFILE)
