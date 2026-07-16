from __future__ import annotations

import ast
import copy
import importlib
from pathlib import Path
from typing import Any

import pytest


hpe = importlib.import_module("pipeline.presence.human_presence_contract_v1")
lena_profile = importlib.import_module("tools.strategy.lena_human_presence_profile_v1")
doctrine = importlib.import_module("pipeline.identity.lena_character_doctrine_validate_v1")

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# A second, purely hypothetical influencer profile, built only for this test
# file, using nothing but the generic engine's public vocabulary. Proves the
# engine can support a materially different body archetype without any
# change to pipeline/presence/human_presence_contract_v1.py.
# ---------------------------------------------------------------------------
_HYPOTHETICAL_ATHLETIC_SILHOUETTE = {
    "bust_emphasis": "understated",
    "waist_hip_contrast": "minimal",
    "hip_glute_emphasis": "understated",
    "proportion_realism": "realistic",
    "silhouette_shape_class": "slim_athletic",
}


def _build_valid_contract(*, doctrine_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = copy.deepcopy(lena_profile.LENA_DEFAULT_PRESENCE_TEMPLATE)
    payload["character_doctrine_provenance"] = (
        doctrine_provenance if doctrine_provenance is not None else doctrine.doctrine_provenance()
    )
    return payload


def _build_hypothetical_second_profile_contract() -> dict[str, Any]:
    payload = _build_valid_contract()
    payload = copy.deepcopy(payload)
    payload["body_presentation"]["silhouette_profile"] = dict(_HYPOTHETICAL_ATHLETIC_SILHOUETTE)
    payload["sensual_presence"] = {
        "tier": "none",
        "sources": [],
        "exposure_dependency": "none",
        "viewer_tension": "none",
        "confidence_level": "comfortable",
    }
    return payload


# ---------------------------------------------------------------------------
# Valid contracts pass.
# ---------------------------------------------------------------------------


def test_lena_default_presence_template_is_a_valid_contract() -> None:
    payload = _build_valid_contract()
    validated = hpe.validate_presence_contract(payload)
    assert validated["schema_version"] == "human_presence_contract_v1"


def test_build_lena_presence_contract_succeeds_end_to_end() -> None:
    contract = lena_profile.build_lena_presence_contract()
    assert contract["body_presentation"]["silhouette_profile"] == lena_profile.LENA_SILHOUETTE_PROFILE
    assert contract["character_doctrine_provenance"]["source_doctrine_artifact_sha256"]


def test_build_lena_presence_contract_accepts_overrides_without_losing_defaults() -> None:
    contract = lena_profile.build_lena_presence_contract(
        overrides={"viewer_relationship": {"performance_level": "candid"}}
    )
    assert contract["viewer_relationship"]["performance_level"] == "candid"
    # Untouched sibling fields still carry the default template's values.
    assert contract["viewer_relationship"]["mode"] == "one_person_intimate"


def test_hypothetical_second_influencer_profile_validates_via_the_same_generic_engine() -> None:
    """Proves the generic contract supports a materially different body
    archetype and a fully desexualized presence configuration without any
    change to the engine module itself."""
    payload = _build_hypothetical_second_profile_contract()
    validated = hpe.validate_presence_contract(payload)
    assert validated["body_presentation"]["silhouette_profile"]["silhouette_shape_class"] == "slim_athletic"
    assert validated["sensual_presence"]["tier"] == "none"


# ---------------------------------------------------------------------------
# Unknown enum values / mechanics / actions / traits fail closed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "section,field,bad_value",
    [
        ("viewer_relationship", "mode", "broadcast_to_everyone"),
        ("viewer_relationship", "invitation_level", "extreme"),
        ("gaze_arc", "discovery_trigger", "telepathy"),
        ("expression_arc", "peak_state", "menacing_glare"),
        ("performance_actions", "primary_action", "teleportation"),
        ("performance_actions", "object_interaction", "weapon"),
        ("movement_dynamics", "weight_transfer", "levitation"),
        ("movement_dynamics", "movement_quality", "glitchy"),
        ("speech_behavior", "address_mode", "telepathic_broadcast"),
        ("speech_behavior", "laughter_behavior", "maniacal_cackle"),
        ("sensual_presence", "tier", "explicit"),
        ("sensual_presence", "exposure_dependency", "high"),
        ("body_presentation", "wardrobe_body_interaction", "clothing_removal"),
        ("body_presentation", "framing_intent", "extreme_closeup_body_part"),
        ("temporal_beats", "connection_peak", "nonconsensual_escalation"),
    ],
)
def test_unknown_enum_value_fails_closed(section: str, field: str, bad_value: str) -> None:
    payload = _build_valid_contract()
    payload[section][field] = bad_value
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "unknown_enum_value"


def test_unknown_sensual_presence_source_fails_closed() -> None:
    payload = _build_valid_contract()
    payload["sensual_presence"]["sources"] = ["gaze", "exposure"]
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "unknown_enum_value"


def test_sexual_keyword_source_is_structurally_unrepresentable() -> None:
    """'exposure' and 'sexual_keywords' are not members of
    SENSUAL_PRESENCE_SOURCES at all -- confirm this directly, since it is
    the actual enforcement mechanism (not a runtime deny-list check)."""
    assert "exposure" not in hpe.SENSUAL_PRESENCE_SOURCES
    assert "sexual_keywords" not in hpe.SENSUAL_PRESENCE_SOURCES
    assert "high" not in hpe.SENSUAL_EXPOSURE_DEPENDENCY_LEVELS


@pytest.mark.parametrize(
    "section_name",
    list(hpe.REQUIRED_TOP_LEVEL_SECTIONS),
)
def test_missing_required_section_fails_closed(section_name: str) -> None:
    payload = _build_valid_contract()
    del payload[section_name]
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "missing_required_section"
    assert section_name in exc_info.value.detail


def test_unknown_schema_version_fails_closed() -> None:
    payload = _build_valid_contract()
    payload["schema_version"] = "some_other_schema_v7"
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "unknown_schema_version"


# ---------------------------------------------------------------------------
# Stale / mismatched doctrine provenance fails closed.
# ---------------------------------------------------------------------------


def test_stale_doctrine_provenance_sha_fails_closed() -> None:
    payload = _build_valid_contract()
    payload["character_doctrine_provenance"]["source_doctrine_artifact_sha256"] = "0" * 64
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "doctrine_provenance_stale"


def test_missing_doctrine_file_at_bound_path_fails_closed() -> None:
    payload = _build_valid_contract()
    payload["character_doctrine_provenance"]["source_doctrine_artifact_path"] = (
        "pipeline/identity/does_not_exist_v1.json"
    )
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "doctrine_provenance_stale"


def test_path_traversal_in_doctrine_provenance_fails_closed() -> None:
    payload = _build_valid_contract()
    payload["character_doctrine_provenance"]["source_doctrine_artifact_path"] = (
        "../../../../etc/passwd"
    )
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "doctrine_provenance_path_outside_repository"


def test_malformed_doctrine_provenance_fields_fail_closed() -> None:
    payload = _build_valid_contract()
    payload["character_doctrine_provenance"]["doctrine_authored_against_repository_revision"] = "not-a-sha"
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "doctrine_provenance_missing"


# ---------------------------------------------------------------------------
# Sensual presence and safety are structurally independent.
# ---------------------------------------------------------------------------


def test_high_sensual_tier_does_not_bypass_adult_or_anatomy_requirements() -> None:
    payload = _build_valid_contract()
    payload["sensual_presence"]["tier"] = "overt_sensual_presence"
    payload["sensual_presence"]["sources"] = ["gaze", "confidence"]
    payload["body_presentation"]["adult_character_required"] = False
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "sensual_mode_requires_adult_character"


def test_anatomy_continuity_cannot_be_relaxed_regardless_of_sensual_tier() -> None:
    payload = _build_valid_contract()
    payload["sensual_presence"]["tier"] = "none"
    payload["sensual_presence"]["sources"] = []
    payload["body_presentation"]["anatomy_continuity_required"] = False
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "anatomy_continuity_must_remain_required"


def test_no_sensual_presence_is_perfectly_valid_and_unaffected_by_body_settings() -> None:
    """A 'none' sensual tier must validate cleanly regardless of body
    presentation settings -- proves the two concepts don't couple in
    either direction beyond the one documented one-way gate."""
    payload = _build_hypothetical_second_profile_contract()
    validated = hpe.validate_presence_contract(payload)
    assert validated["sensual_presence"]["tier"] == "none"
    assert validated["body_presentation"]["adult_character_required"] is True


def test_sensual_presence_requiring_nonempty_sources_when_tier_is_not_none() -> None:
    payload = _build_valid_contract()
    payload["sensual_presence"]["tier"] = "understated_confidence"
    payload["sensual_presence"]["sources"] = []
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        hpe.validate_presence_contract(payload)
    assert exc_info.value.code == "sensual_presence_missing_sources"


# ---------------------------------------------------------------------------
# Lena's voluptuous body profile is preserved; body morphology is
# character-specific, not universal.
# ---------------------------------------------------------------------------


def test_lena_silhouette_profile_matches_established_voluptuous_description() -> None:
    profile = lena_profile.lena_silhouette_profile()
    assert profile["bust_emphasis"] == "pronounced"
    assert profile["waist_hip_contrast"] == "pronounced"
    assert profile["hip_glute_emphasis"] == "pronounced"
    assert profile["proportion_realism"] == "required_realistic"
    assert profile["silhouette_shape_class"] == "hourglass_voluptuous"


def test_generic_engine_defines_axes_not_a_single_universal_body() -> None:
    """The engine module itself must define body-presentation AXES, not one
    fixed silhouette. If this constant existed as a single value instead of
    a tuple of options, the engine would be imposing one body on every
    character -- confirm the axis vocabularies are genuinely multi-valued."""
    assert len(hpe.SILHOUETTE_SHAPE_CLASSES) > 1
    # "hourglass_voluptuous" is one of several generic shape-class labels
    # the engine offers -- a category name, not Lena-specific hardcoded
    # data. Its presence alongside other, materially different classes is
    # exactly the point: the engine offers a menu, it does not pick one.
    assert "hourglass_voluptuous" in hpe.SILHOUETTE_SHAPE_CLASSES
    assert "slim_athletic" in hpe.SILHOUETTE_SHAPE_CLASSES
    assert "curvy_soft" in hpe.SILHOUETTE_SHAPE_CLASSES
    # The engine module's own source must not reference Lena (or any other
    # specific character) by name -- it only defines generic axes/labels.
    source = Path(hpe.__file__).read_text(encoding="utf-8")
    assert "lena" not in source.lower()


# ---------------------------------------------------------------------------
# Generic engine module has no consumers yet, no live-execution imports, and
# no absolute local paths -- existing generation behavior is unchanged.
# ---------------------------------------------------------------------------


def test_generic_contract_module_is_report_only_and_touches_no_live_surfaces() -> None:
    source = Path(hpe.__file__).read_text(encoding="utf-8")
    assert "C:\\projects\\ai\\content_bot" not in source

    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    blocked_prefixes = (
        "requests",
        "httpx",
        "urllib.request",
        "subprocess",
        "boto3",
        "pipeline.higgsfield_lena_api_executor",
        "tools.lena_higgsfield_generation_approval_v1",
        "tools.lena_build_approved_publish_queue_v2_8",
        "tools.strategy.lena_build_next_live_image_handoff_v1",
        "tools.strategy.lena_record_generation_reconciliation_decision_v1",
        "tools.strategy.lena_reconciliation_contract_v1",
        "pipeline.prompting.lena_prompt_brain",
        "tools.strategy.lena_pre_generation_candidate_gate_v1",
    )
    for module in imported_modules:
        assert not any(module.startswith(prefix) for prefix in blocked_prefixes), module


def test_lena_adapter_does_not_duplicate_generic_validation_logic() -> None:
    """The Lena adapter must call the generic validator, not re-implement
    its own enum/section checks."""
    source = Path(lena_profile.__file__).read_text(encoding="utf-8")
    assert "validate_presence_contract" in source
    # None of the generic vocabularies' names should be redefined
    # (re-declared as a new tuple) inside the adapter module.
    tree = ast.parse(source)
    assigned_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    generic_vocabulary_names = {
        "VIEWER_RELATIONSHIP_MODES",
        "SENSUAL_PRESENCE_TIERS",
        "SENSUAL_PRESENCE_SOURCES",
        "PRESENCE_FAILURE_INDICATORS",
        "SILHOUETTE_SHAPE_CLASSES",
    }
    assert not (assigned_names & generic_vocabulary_names)


def test_lena_adapter_touches_no_live_execution_surfaces() -> None:
    source = Path(lena_profile.__file__).read_text(encoding="utf-8")
    assert "C:\\projects\\ai\\content_bot" not in source
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    blocked_prefixes = (
        "requests",
        "httpx",
        "urllib.request",
        "subprocess",
        "boto3",
        "pipeline.higgsfield_lena_api_executor",
        "tools.lena_higgsfield_generation_approval_v1",
        "tools.lena_build_approved_publish_queue_v2_8",
        "tools.strategy.lena_build_next_live_image_handoff_v1",
        "tools.strategy.lena_record_generation_reconciliation_decision_v1",
        "tools.strategy.lena_reconciliation_contract_v1",
        "pipeline.prompting.lena_prompt_brain",
        "tools.strategy.lena_pre_generation_candidate_gate_v1",
    )
    for module in imported_modules:
        assert not any(module.startswith(prefix) for prefix in blocked_prefixes), module


def test_presence_failure_indicators_are_the_exact_required_list() -> None:
    assert set(hpe.presence_failure_indicators()) == {
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
    }


def test_doctrine_no_longer_confirming_adult_presentation_blocks_lena_profile_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_load_doctrine = doctrine.load_doctrine

    def _fake_load_doctrine():
        payload = original_load_doctrine()
        payload = copy.deepcopy(payload)
        payload["hard_identity_continuity"]["requirements"] = [
            r for r in payload["hard_identity_continuity"]["requirements"] if r != "adult_presentation_required"
        ]
        return payload

    monkeypatch.setattr(doctrine, "load_doctrine", _fake_load_doctrine)
    with pytest.raises(hpe.HumanPresenceContractError) as exc_info:
        lena_profile.build_lena_presence_contract()
    assert exc_info.value.code == "doctrine_does_not_confirm_adult_presentation"
