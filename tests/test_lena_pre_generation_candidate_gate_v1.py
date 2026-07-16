import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strategy import lena_pre_generation_candidate_gate_v1 as gate
from tools.strategy import lena_human_presence_profile_v1 as lena_profile
from pipeline.presence import human_presence_prompt_plan_v1 as presence_plan


def scene(lane="city bench", pillar="everyday_lena", temperature="quiet", roles=None, **updates):
    value = {
        "lane": lane,
        "action": "sitting on a city bench with coffee",
        "environment": "a shaded city park edge",
        "details": "creased newspaper and fallen leaves",
        "camera": "candid vertical portrait",
        "lighting": "soft afternoon light",
        "caption": "five quiet minutes",
        "strategy_pillars": [pillar],
        "creative_temperature": temperature,
        "narrative_roles": roles or ["quiet_reset"],
        "choice_eligible": False,
        "payoff_eligible": False,
        "frame_evidence_objects": ["coffee cup", "newspaper"],
    }
    value.update(updates)
    return value


def recipe(recipe_id="hcr_test", pillar="everyday_lena", temperature="quiet", roles=None, **updates):
    value = {
        "id": recipe_id,
        "strategy_pillars": [pillar],
        "creative_temperature": temperature,
        "narrative_roles": roles or ["quiet_reset"],
        "choice_eligible": False,
        "payoff_eligible": False,
        "best_content_type": "photo+reel",
        "linked_hook_categories": ["quiet_personal"],
        "human_reason": "A believable pause during an ordinary city afternoon.",
        "scene_logic_contract": {"required_visual_evidence": ["bench", "coffee cup"]},
        "proof_priority": 1,
        "environment_id": "env_city_bench",
    }
    value.update(updates)
    return value


def hook(hook_id="hook_test", category="quiet_personal", score=40, **updates):
    value = {
        "id": hook_id,
        "category": category,
        "hook_text": "I needed this pause",
        "best_content_type": "photo+reel",
        "visual_pairing": "quiet city pause with coffee",
        "caption_followup": "No emergency. Just a breath.",
        "risk_notes": "none",
        "scores": {"total_score": score, "lena_voice_score": 9, "curiosity_score": 7},
    }
    value.update(updates)
    return value


def image(lane="city bench", slot="gate-pack000-00-photo", **updates):
    value = {
        "slot_id": slot,
        "lane": lane,
        "wardrobe_outfit_id": "wc_test",
        "pose_body_language_id": "pose_test",
        "pose_body_language_label": "relaxed seated pose",
        "effective_wardrobe_silhouette_class": "fitted_daywear",
        "soul_name": "Lena",
        "soul_version": "Soul 2.0",
        "soul_selection_mode": "provider_config_not_prompt_text",
        "camera_text": "50mm candid vertical",
        "lighting_text": "soft natural light",
        "image_prompt": "Lena in fitted daywear on a city bench with a coffee cup.",
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
    }
    value.update(updates)
    return value


def presence_image(plan: dict[str, object], lane="city bench", slot="gate-pack000-00-photo", **updates):
    value = image(lane, slot, **updates)
    value.update(
        {
            "reference_mode": " ".join(
                plan["body_presentation"]["selector_terms"][:2] + plan["viewer_relationship"]["selector_terms"][:2]
            ),
            "environment_name": " ".join(plan["viewer_relationship"]["selector_terms"]),
            "expression_gaze_id": " ".join(plan["gaze_arc"]["selector_terms"][:3]),
            "expression_gaze_label": " ".join(plan["gaze_arc"]["selector_terms"]),
            "expression_text": " ".join(plan["expression_arc"]["selector_terms"]),
            "camera_text": " ".join(plan["viewer_relationship"]["selector_terms"] + plan["movement_dynamics"]["selector_terms"]),
            "lighting_text": " ".join(plan["sensual_presence"]["selector_terms"]),
            "pose_body_language_label": " ".join(plan["movement_dynamics"]["selector_terms"]),
            "effective_wardrobe_silhouette_class": " ".join(plan["sensual_presence"]["selector_terms"]),
            "wardrobe_silhouette_class": " ".join(plan["body_presentation"]["selector_terms"]),
            "framing_text": " ".join(plan["body_presentation"]["selector_terms"]),
            "caption_seed": " ".join(plan["temporal_beats"]["selector_terms"]),
        }
    )
    return value


def curator(img=None, total=20, failure=None):
    return {"image": img or image(), "total_score": total, "failure_memory_flag": failure}


def authorities(scenes=None, recipes=None, hooks=None):
    scenes = [scene()] if scenes is None else scenes
    recipes = [recipe()] if recipes is None else recipes
    hooks = [hook()] if hooks is None else hooks
    return {
        "persona": {"canonical_niche": gate.CANONICAL_NICHE},
        "strategy": {
            "canonical_niche": gate.CANONICAL_NICHE,
            "motorcycle_role": {"existing_production_blocks_remain_authoritative": True},
            "high_heat_rules": {"swimwear_requires_context": ["beach", "pool", "resort", "boat", "spa"]},
        },
        "scene_bank": {"production_blocked_lanes": []},
        "scenes": {item["lane"]: item for item in scenes},
        "recipes": recipes,
        "hooks": {item["id"]: item for item in hooks},
        "input_provenance": [],
    }


def recent(*records):
    return {"records": list(records), "inputs": []}


def published(timestamp, temperature=None):
    value = {"evidence_class": "published_receipt", "publication_timestamp_utc": timestamp}
    if temperature is not None:
        value["creative_temperature"] = temperature
    return value


def select(auth=None, candidates=None, history=None):
    selected, reasons, _ = gate.select_candidate(
        auth or authorities(),
        candidates or [curator()],
        history or recent(),
    )
    return selected, reasons


def test_real_canonical_strategy_is_consumed_and_legacy_selectors_are_not_authority():
    loaded = gate.load_authorities()
    assert loaded["strategy"]["canonical_niche"] == gate.CANONICAL_NICHE
    assert tuple(item["path"] for item in loaded["input_provenance"]) == gate.AUTHORITY_PATHS
    assert all("legacy" not in path and "world_continuity" not in path for path in gate.AUTHORITY_PATHS)


def test_missing_canonical_identity_reference_contract_blocks(tmp_path):
    root = tmp_path
    for relative in gate.AUTHORITY_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = gate.ROOT / relative
        target.write_bytes(source.read_bytes())
    persona_path = root / gate.AUTHORITY_PATHS[0]
    persona = json.loads(persona_path.read_text())
    persona.pop("identity_rule")
    persona_path.write_text(json.dumps(persona), encoding="utf-8")
    with pytest.raises(gate.GateError) as error:
        gate.load_authorities(root)
    assert error.value.code == "invalid_identity_reference_contract"


def test_exactly_one_candidate_is_selected_without_operator_menu_or_alternates():
    auth = authorities(
        [scene(), scene("morning apartment")],
        [recipe()],
        [hook()],
    )
    selected, _ = select(auth, [curator(), curator(image("morning apartment", "gate-pack000-01-photo"))])
    assert selected["candidate_id"]
    assert "alternates" not in selected
    assert "operator_menu" not in selected


@pytest.mark.parametrize("lane", ["blocked lane", "motorcycle street glam"])
def test_blocked_and_motorcycle_scenes_are_excluded(lane):
    scn = scene(lane)
    auth = authorities([scn])
    if lane == "blocked lane":
        auth["scene_bank"]["production_blocked_lanes"] = [lane]
    selected, reasons = select(auth, [curator(image(lane))])
    assert selected is None
    assert any(item["reason"] in {"blocked_scene", "motorcycle_production_blocked"} for item in reasons)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"soul_name": "Someone Else"}, "identity_contract_failure"),
        ({"soul_version": None}, "identity_contract_failure"),
        ({"soul_selection_mode": "prompt_text"}, "identity_contract_failure"),
    ],
)
def test_identity_contract_failures_block(change, expected):
    selected, reasons = select(candidates=[curator(image(**change))])
    assert selected is None
    assert expected in {item["reason"] for item in reasons}


def test_pose_scene_contradiction_and_prompt_validation_failure_block():
    img = image()
    img["validation"]["pose_scene_match_pass"] = False
    selected, reasons = select(candidates=[curator(img)])
    assert selected is None
    assert "prompt_hard_validation_failure" in {item["reason"] for item in reasons}


@pytest.mark.parametrize(
    ("canonical_action", "generated_scene", "expected_code"),
    [
        ("walking toward the cafe", "standing stationary outside the cafe", "action_walk_vs_stationary"),
        ("glancing toward the window", "facing the camera with a direct confident gaze", "gaze_window_vs_camera"),
        ("pouring coffee into a mug", "a coffee mug resting on the counter", "prop_pouring_vs_resting"),
    ],
)
def test_material_scene_prompt_action_gaze_and_prop_contradictions_block(canonical_action, generated_scene, expected_code):
    scn = scene(action=canonical_action)
    img = image(image_prompt=f"Scene: {generated_scene}. Wardrobe: fitted daywear. Pose: relaxed stance. Expression: soft gaze. Camera: 50mm.")
    compatibility = gate._scene_prompt_compatibility(scn, img, recipe())
    assert expected_code in compatibility["material_contradictions"]
    selected, reasons = select(authorities([scn]), [curator(img)])
    assert selected is None
    assert "scene_prompt_material_contradiction" in {item["reason"] for item in reasons}


def test_noncontradictory_omission_is_allowed_and_summary_uses_only_package_proven_facts():
    scn = scene(action="pouring coffee while looking toward the window")
    auth = authorities([scn])
    generated_scene = "standing in a lived-in apartment kitchen in morning light"
    img = image(image_prompt=f"Scene: {generated_scene}. Wardrobe: fitted daywear. Pose: relaxed stance. Expression: soft gaze. Camera: 50mm.")
    selected, _ = select(auth, [curator(img)])
    assert selected is not None
    assert selected["activity"].rstrip(".") == generated_scene
    assert generated_scene in selected["concept_summary"]
    assert "pouring coffee" not in selected["concept_summary"]
    assert "window" not in selected["concept_summary"]


def test_required_mid_action_evidence_contradiction_reports_exact_blocker():
    scn = scene(action="standing in her apartment kitchen before breakfast")
    rec = recipe(
        scene_logic_contract={
            "required_visual_evidence": [
                "mid-action kitchen behavior such as pouring coffee or reaching into a cabinet"
            ]
        }
    )
    generated_scene = "standing beside the counter with a coffee mug resting on the counter"
    img = image(
        image_prompt=(
            f"Scene: {generated_scene}. Wardrobe: fitted daywear. "
            "Pose: relaxed stance. Expression: soft gaze. Camera: 50mm."
        )
    )
    selected, reasons = select(authorities([scn], [rec]), [curator(img)])
    assert selected is None
    assert "required_mid_action_evidence_contradicted" in {
        item["reason"] for item in reasons
    }


def test_curator_failure_memory_caution_loses_and_hard_excluded_candidates_never_enter_selection():
    safe = curator(image(slot="gate-pack000-01-photo"), total=10)
    cautioned = curator(image(slot="gate-pack000-00-photo"), total=99, failure="one recorded fail")
    selected, _ = select(candidates=[cautioned, safe])
    assert selected["slot_id"] == "gate-pack000-01-photo"
    assert gate.curate_top_prompts.__module__.endswith("lena_higgsfield_prompt_library_dryrun")


def test_high_heat_requires_sequence_evidence_and_rejects_consecutive_high_heat():
    scn = scene("pool terrace", "high_heat_glamour", "high_heat", ["experience"], environment="resort pool terrace")
    rec = recipe(pillar="high_heat_glamour", temperature="high_heat", roles=["experience"])
    auth = authorities([scn], [rec])
    selected, reasons = select(auth, [curator(image("pool terrace"))])
    assert selected is None
    assert "high_heat_sequence_unproven_or_consecutive" in {item["reason"] for item in reasons}
    selected, _ = select(auth, [curator(image("pool terrace"))], recent({"creative_temperature": "high_heat"}))
    assert selected is None


def test_high_heat_uses_latest_chronological_publication_only():
    scn = scene("pool terrace", "high_heat_glamour", "high_heat", ["experience"], environment="resort pool terrace")
    rec = recipe(pillar="high_heat_glamour", temperature="high_heat", roles=["experience"])
    auth = authorities([scn], [rec])
    candidate = curator(image("pool terrace"))
    history = recent(
        published("2026-07-12T12:00:00Z", "high_heat"),
        {"evidence_class": "prompt_memory", "creative_temperature": "quiet"},
        {"evidence_class": "higgsfield_manifest", "creative_temperature": "quiet"},
        published("2026-07-10T12:00:00Z", "quiet"),
    )
    selected, reasons = select(auth, [candidate], history)
    assert selected is None
    assert "high_heat_sequence_unproven_or_consecutive" in {item["reason"] for item in reasons}


def test_prompt_memory_and_manifest_cannot_establish_previous_publication_temperature():
    records = [
        {"evidence_class": "prompt_memory", "creative_temperature": "quiet"},
        {"evidence_class": "higgsfield_manifest", "creative_temperature": "high_heat"},
    ]
    assert gate._latest_published_temperature(records) == (None, None)


def test_unknown_latest_published_temperature_remains_unknown_and_blocks_high_heat():
    assert gate._latest_published_temperature([
        published("2026-07-10T00:00:00Z", "quiet"),
        published("2026-07-12T00:00:00Z"),
    ]) == (None, "2026-07-12T00:00:00Z")


def test_published_chronology_normalizes_timezone_offsets():
    assert gate._latest_published_temperature([
        published("2026-07-12T16:30:00Z", "quiet"),
        published("2026-07-12T12:00:00-05:00", "high_heat"),
    ]) == ("high_heat", "2026-07-12T12:00:00-05:00")


def test_contextual_swimwear_and_sexual_signal_stacking_are_hard_gates():
    scn = scene("studio swim", "high_heat_glamour", "high_heat", ["experience"], environment="plain studio")
    rec = recipe(pillar="high_heat_glamour", temperature="high_heat", roles=["experience"])
    auth = authorities([scn], [rec])
    prompt = "bikini cleavage low-rise micro mini sheer"
    selected, reasons = select(auth, [curator(image("studio swim", image_prompt=prompt))], recent({"creative_temperature": "quiet"}))
    codes = {item["reason"] for item in reasons}
    assert selected is None
    assert {"swimwear_context_missing", "sexual_signal_stacking"} <= codes


def test_recipe_requires_primary_pillar_temperature_role_photo_support_and_active_status():
    base = scene()
    invalid = [
        recipe("pillar", pillar="city_and_social_life"),
        recipe("temp", temperature="warm"),
        recipe("role", roles=["setup"]),
        recipe("video", best_content_type="video"),
        recipe("blocked", production_status="blocked"),
    ]
    selected, reasons = select(authorities([base], invalid), [curator()])
    assert selected is None
    assert "no_compatible_active_recipe" in {item["reason"] for item in reasons}


@pytest.mark.parametrize("category", ["meaningful_choice", "payoff", "callback", "consequence"])
def test_unsupported_state_dependent_hooks_are_excluded(category):
    rec = recipe(linked_hook_categories=[category])
    selected, reasons = select(authorities(recipes=[rec], hooks=[hook(category=category)]), [curator()])
    assert selected is None
    assert "no_safe_linked_hook" in {item["reason"] for item in reasons}


def test_unsafe_major_life_and_fake_emergency_hooks_are_excluded():
    bad = hook(caption_followup="A fake emergency and life-changing announcement")
    selected, _ = select(authorities(hooks=[bad]), [curator()])
    assert selected is None


def test_state_dependent_open_loop_is_excluded_but_self_contained_curiosity_can_survive():
    dependent = hook("co_dependent", "curiosity_open_loop", risk_notes="Open loop must receive a later payoff.")
    self_contained = hook("co_safe", "curiosity_open_loop", hook_text="The Better Idea Came Later", caption_followup="I should have expected that.", risk_notes="Do not imply an emergency.")
    rec = recipe(linked_hook_categories=["curiosity_open_loop"])
    selected, _ = select(authorities(recipes=[rec], hooks=[dependent, self_contained]), [curator()])
    assert selected["hook_id"] == "co_safe"
    assert selected["audience_choice_action"] == "none"
    assert selected["payoff_claimed"] is False


def test_real_canonical_open_loop_hook_contract_is_pinned():
    loaded = gate.load_authorities()
    canonical_hooks = loaded["hooks"]
    assert gate._hook_is_safe(canonical_hooks["co_001"], {}) is False
    assert gate._hook_is_safe(canonical_hooks["co_002"], {}) is True
    assert gate._hook_is_safe(canonical_hooks["co_003"], {}) is False


def test_published_quiet_is_not_overridden_by_later_nonpublication_high_heat():
    scn = scene(
        "pool terrace",
        "high_heat_glamour",
        "high_heat",
        ["experience"],
        environment="resort pool terrace",
    )
    rec = recipe(
        pillar="high_heat_glamour",
        temperature="high_heat",
        roles=["experience"],
    )
    history = recent(
        published("2026-07-12T12:00:00Z", "quiet"),
        {
            "evidence_class": "prompt_memory",
            "creative_temperature": "high_heat",
            "recorded_at": "2026-07-13T10:00:00Z",
        },
        {
            "evidence_class": "higgsfield_manifest",
            "creative_temperature": "high_heat",
            "recorded_at": "2026-07-13T11:00:00Z",
        },
    )
    assert gate._latest_published_temperature(history["records"]) == (
        "quiet",
        "2026-07-12T12:00:00Z",
    )
    selected, reasons = select(
        authorities([scn], [rec]),
        [curator(image("pool terrace"))],
        history,
    )
    assert selected is not None
    assert "high_heat_sequence_unproven_or_consecutive" not in {
        item["reason"] for item in reasons
    }


@pytest.mark.parametrize(
    "dimension",
    ["situational_specificity", "lived_in_detail", "character_fit", "followability", "higgsfield_curator_score", "hook_score"],
)
def test_substantive_quality_dimensions_affect_ranking(dimension):
    a = scene("lane a")
    b = scene("lane b")
    rec_a = recipe("rec_a")
    rec_b = recipe("rec_b")
    hk_a = hook("hook_a")
    hk_b = hook("hook_b")
    auth = authorities([a, b], [rec_a, rec_b], [hk_a, hk_b])
    candidates = [curator(image("lane a", "slot-a")), curator(image("lane b", "slot-b"))]
    selected, _ = select(auth, candidates)
    baseline = selected["slot_id"]
    # Verify the chosen record exposes every approved ranking axis; ordering is tested
    # independently through the public rank key to avoid fabricating canonical inputs.
    candidate_a = copy.deepcopy(selected)
    candidate_b = copy.deepcopy(selected)
    candidate_a["slot_id"] = "slot-a"
    candidate_b["slot_id"] = "slot-b"
    candidate_a["deterministic_noncreative_tiebreak"] = ["lane a", "rec_a", "hook_a", "slot-a"]
    candidate_b["deterministic_noncreative_tiebreak"] = ["lane b", "rec_b", "hook_b", "slot-b"]
    candidate_a["lane"], candidate_a["recipe_id"], candidate_a["hook_id"] = "lane a", "rec_a", "hook_a"
    candidate_b["lane"], candidate_b["recipe_id"], candidate_b["hook_id"] = "lane b", "rec_b", "hook_b"
    candidate_a["ranking_evidence"][dimension] = candidate_b["ranking_evidence"][dimension] + (1 if dimension not in {"recipe_proof_priority"} else -1)
    if dimension == "higgsfield_curator_score" or dimension in {"situational_specificity", "lived_in_detail", "character_fit", "followability", "hook_score"}:
        assert gate._rank_key(candidate_a) < gate._rank_key(candidate_b)
    assert baseline in {"slot-a", "slot-b"}


def test_physical_risk_and_recent_lane_outfit_environment_pose_repetition_affect_ranking():
    low = scene("lane low")
    high = scene("lane high")
    auth = authorities([low, high])
    candidates = [
        curator(image("lane low", "slot-low", pose_body_language_label="relaxed stance")),
        curator(image("lane high", "slot-high", pose_body_language_label="holding complex prop"), total=99),
    ]
    selected, _ = select(auth, candidates, recent({"lane": "lane high", "outfit_id": "wc_test", "environment_id": "env_city_bench", "pose_id": "pose_test"}))
    assert selected["slot_id"] == "slot-low"


def test_premium_restraint_is_substantive_ranking_evidence_before_tiebreak():
    restrained, _ = select(candidates=[curator(image())])
    lower = copy.deepcopy(restrained)
    higher = copy.deepcopy(restrained)
    lower["lane"], lower["slot_id"] = "alpha", "slot-a"
    higher["lane"], higher["slot_id"] = "zeta", "slot-z"
    lower["ranking_evidence"]["premium_visual_discipline"] = 1
    higher["ranking_evidence"]["premium_visual_discipline"] = 2
    assert gate._rank_key(higher) < gate._rank_key(lower)
    higher["ranking_evidence"]["premium_visual_discipline"] = 1
    assert gate._rank_key(lower) < gate._rank_key(higher)


def test_deterministic_noncreative_tiebreak_selects_one_after_substantive_tie():
    auth = authorities([scene("alpha"), scene("beta")])
    selected, _ = select(auth, [curator(image("beta", "slot-b")), curator(image("alpha", "slot-a"))])
    assert selected["lane"] == "alpha"
    assert selected["deterministic_noncreative_tiebreak"] == ["alpha", "hcr_test", "hook_test", "slot-a"]


def test_missing_noncritical_history_selects_medium_but_missing_critical_recipe_abstains():
    selected, _ = select(history=recent())
    core = gate._decision_core("a" * 40, "2026-07-13", authorities(), selected, [], recent(), {})
    assert core["candidate_status"] == "selected"
    assert core["confidence"] == "medium"
    selected, reasons = select(authorities(recipes=[]), [curator()])
    assert selected is None
    assert reasons


def test_decision_is_provider_false_has_no_menu_world_state_choice_or_side_effects():
    selected, rejected = select()
    core = gate._decision_core("b" * 40, "2026-07-13", authorities(), selected, rejected, recent(), {})
    encoded = json.dumps(core)
    assert core["provider_authorized"] is False
    assert core["side_effects_performed"] == []
    assert core["candidate"]["audience_choice_action"] == "none"
    assert core["candidate"]["payoff_claimed"] is False
    assert "operator_menu" not in encoded
    assert "open_choice_id" not in encoded


def test_matching_rerun_reuses_byte_identical_artifact_and_conflict_refuses_overwrite(tmp_path):
    selected, rejected = select()
    core = gate._decision_core("c" * 40, "2026-07-13", authorities(), selected, rejected, recent(), {})
    path, first, reused = gate.write_decision(core, tmp_path, "2026-07-13T12:00:00Z")
    original = path.read_bytes()
    same_path, second, reused = gate.write_decision(core, tmp_path, "2099-01-01T00:00:00Z")
    assert same_path == path and reused is True and second == first
    assert path.read_bytes() == original
    corrupted = json.loads(path.read_text())
    corrupted["decision_fingerprint_sha256"] = "0" * 64
    path.write_text(json.dumps(corrupted), encoding="utf-8")
    with pytest.raises(gate.GateError, match="refusing to overwrite"):
        gate.write_decision(core, tmp_path)


def test_required_recipe_binding_filters_on_canonical_recipe_selection_not_raw_prompt_candidates():
    scn_a = scene("lane a", pillar="p1")
    scn_b = scene("lane b", pillar="p2")
    rec_a = recipe("hcr_a", pillar="p1")
    rec_b = recipe("hcr_b", pillar="p2")
    auth = authorities([scn_a, scn_b], [rec_a, rec_b], [hook()])
    prompt_candidates = [
        curator(image("lane a", "slot-a")),
        curator(image("lane b", "slot-b")),
    ]

    selected, reasons, saw_required = gate.select_candidate(
        auth,
        prompt_candidates,
        recent(),
        required_recipe_id="hcr_b",
    )

    assert saw_required is True
    assert selected is not None
    assert selected["recipe_id"] == "hcr_b"
    assert "required_recipe_candidate_missing" in {item["reason"] for item in reasons}


def test_required_recipe_missing_raises_even_when_other_candidates_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(gate, "verify_authority_inputs_clean", lambda *args, **kwargs: None)
    auth = authorities([scene("lane a", pillar="p1")], [recipe("hcr_a", pillar="p1")], [hook()])
    prompt_candidates = [curator(image("lane a", "slot-a"))]

    with pytest.raises(gate.GateError) as error:
        gate.run_gate(
            "2026-07-14",
            tmp_path,
            required_recipe_id="hcr_missing",
            authority_loader=lambda: auth,
            recent_loader=recent,
            prompt_builder=lambda *_args: (prompt_candidates, {}),
        )

    assert error.value.code == "required_recipe_candidate_missing"


def test_required_recipe_unknown_raises_even_when_other_candidates_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(gate, "verify_authority_inputs_clean", lambda *args, **kwargs: None)
    auth = authorities([scene("lane a", pillar="p1")], [recipe("hcr_a", pillar="p1")], [hook()])
    prompt_candidates = [curator(image("lane a", "slot-a"))]

    with pytest.raises(gate.GateError) as error:
        gate.run_gate(
            "2026-07-14",
            tmp_path,
            required_recipe_id="hcr_unknown",
            authority_loader=lambda: auth,
            recent_loader=recent,
            prompt_builder=lambda *_args: (prompt_candidates, {}),
        )

    assert error.value.code == "required_recipe_candidate_missing"


def test_controlled_required_recipe_run_gate_surfaces_the_mirror_lane(tmp_path) -> None:
    path, decision, reused = gate.run_gate(
        "2026-07-15",
        tmp_path,
        required_recipe_id="hcr_012",
        verify_clean=False,
    )

    assert reused is False
    assert path.is_file()
    assert decision["candidate_status"] == "selected"
    assert decision["candidate"]["recipe_id"] == "hcr_012"
    assert decision["candidate"]["lane"] == "mirror outfit check"
    assert decision["candidate"]["environment_id"] == "env_v008"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda artifact: artifact["candidate"].update({"lane": "altered lane"}),
        lambda artifact: artifact["evidence"].update({"recipe_binding_semantics": "altered"}),
    ],
)
def test_altered_artifact_body_with_unchanged_stored_fingerprint_rejects_without_overwrite(tmp_path, mutation):
    selected, rejected = select()
    core = gate._decision_core("d" * 40, "2026-07-13", authorities(), selected, rejected, recent(), {})
    path, _, _ = gate.write_decision(core, tmp_path, "2026-07-13T12:00:00Z")
    artifact = json.loads(path.read_text())
    original_fingerprint = artifact["decision_fingerprint_sha256"]
    mutation(artifact)
    artifact["decision_fingerprint_sha256"] = original_fingerprint
    path.write_text(json.dumps(artifact), encoding="utf-8")
    altered_bytes = path.read_bytes()
    with pytest.raises(gate.GateError, match="refusing to overwrite"):
        gate.write_decision(core, tmp_path)
    assert path.read_bytes() == altered_bytes


def test_recipe_environment_is_compatibility_only_and_generated_environment_drives_contrast():
    rec = recipe(environment_id="recipe_env")
    candidate, _ = select(authorities(recipes=[rec]), [curator(image())], recent({"environment_id": "recipe_env"}))
    assert "environment_id" not in candidate
    assert candidate["ranking_evidence"]["feed_contrast"]["environment_repetitions"] == 0
    assert candidate["strategy_compatibility_evidence"]["recipe_environment_id"] == "recipe_env"
    proven, _ = select(
        authorities(recipes=[rec]),
        [curator(image(environment_id="recipe_env"))],
        recent({"environment_id": "recipe_env"}),
    )
    assert proven["environment_id"] == "recipe_env"
    assert proven["ranking_evidence"]["feed_contrast"]["environment_repetitions"] == 1
    assert proven["strategy_compatibility_evidence"]["generated_environment_exact_match"] is True


def test_historical_inputs_and_state_files_are_read_only(tmp_path):
    published = tmp_path / "pipeline/queue/published"
    published.mkdir(parents=True)
    item = published / "post.json"
    receipt = published / "post.json.receipt.json"
    item.write_text('{"lane":"city bench"}', encoding="utf-8")
    receipt.write_text('{"published":true}', encoding="utf-8")
    state = tmp_path / "pipeline/state"
    state.mkdir(parents=True)
    memory = state / "lena_prompt_memory.json"
    memory.write_text('{"recent":[{"lane":"coffee shop"}]}', encoding="utf-8")
    manifest = tmp_path / "pipeline/higgsfield_debug/2026-07-13/slot/result_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"lane":"rainy street","pose_body_language_id":"pose_1"}', encoding="utf-8")
    before = {path: path.read_bytes() for path in (item, receipt, memory, manifest)}
    loaded = gate.load_recent_content(tmp_path)
    assert len(loaded["records"]) == 3
    assert any(record["evidence_class"] == "higgsfield_manifest" for record in loaded["records"])
    assert before == {path: path.read_bytes() for path in before}


def test_only_exact_authority_inputs_are_checked_and_unrelated_dirty_content_is_ignored(monkeypatch):
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr(gate.subprocess, "run", lambda args, **kwargs: calls.append(args) or Result())
    gate.verify_authority_inputs_clean(("one.json", "two.json"))
    inspected = {args[-1] for args in calls}
    assert inspected == {"one.json", "two.json"}
    assert all("status" not in args for args in calls)


def test_modified_or_staged_authority_conflict_blocks(monkeypatch):
    class Result:
        returncode = 1

    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(gate.GateError) as error:
        gate.verify_authority_inputs_clean(("canonical.json",))
    assert error.value.code == "authority_conflict"


def test_source_contains_no_provider_network_generation_or_downstream_imports():
    source = Path(gate.__file__).read_text(encoding="utf-8")
    forbidden = (
        "requests.", "httpx.", "urllib.request", "higgsfield_lena_api_executor import",
        "build_story_video", "write_queue", "publish(", "approve(", "analytics mutation",
    )
    assert not any(term in source for term in forbidden)
    assert "provider_authorized\": False" in source


def test_real_prompt_builder_creates_exactly_one_ten_image_pack_in_memory():
    candidates, metadata = gate.build_prompt_candidates("2026-07-13", "23ce1d67")
    assert metadata["pack_count"] == 1
    assert metadata["prompt_count"] == 10
    assert len(metadata["prompt_identity_sha256"]) == 64
    assert len(candidates) <= 10
    assert all(item["image"]["slot_id"].endswith("-photo") for item in candidates)
    assert "human_presence" not in metadata


def test_build_prompt_candidates_threads_presence_contract_only_when_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, object]] = []
    images = [
        {"slot_id": f"slot-{index}", "image_prompt": f"prompt {index}"}
        for index in range(10)
    ]

    def fake_build_library_report(
        as_of_date: str,
        prefix: str,
        packs: int,
        count_per_pack: int,
        required_recipe_id: str = "",
        presence_contract=None,
    ):
        seen.append((required_recipe_id, presence_contract))
        return {
            "total_prompts": len(images),
            "pack_reports": [{"images": images}],
            "failure_memory_hard_excluded_patterns": [],
            "failure_memory_soft_flagged_patterns": [],
            "failure_memory_excluded_count": 0,
            "human_presence": (
                {"schema_version": "human_presence_prompt_plan_v1", "enabled": True}
                if presence_contract is not None
                else None
            ),
        }

    def fake_curate_top_prompts(library, limit):
        return {
            "selected": [{"image": images[0], "slot_id": images[0]["slot_id"]}],
            "excluded_count": 0,
            "failure_memory_hard_excluded_patterns": [],
            "failure_memory_soft_flagged_patterns": [],
            "failure_memory_excluded_count": 0,
        }

    monkeypatch.setattr(gate, "build_library_report", fake_build_library_report)
    monkeypatch.setattr(gate, "curate_top_prompts", fake_curate_top_prompts)

    selected, prompt_meta = gate.build_prompt_candidates("2026-07-15", "abcdef12", required_recipe_id="hcr_012")
    assert selected[0]["image"]["slot_id"] == "slot-0"
    assert seen == [("hcr_012", None)]
    assert "human_presence" not in prompt_meta

    seen.clear()
    contract = lena_profile.build_lena_presence_contract()
    selected, prompt_meta = gate.build_prompt_candidates(
        "2026-07-15",
        "abcdef12",
        required_recipe_id="hcr_012",
        presence_contract=contract,
    )
    assert selected[0]["image"]["slot_id"] == "slot-0"
    assert seen == [("hcr_012", contract)]
    assert prompt_meta["human_presence"]["schema_version"] == "human_presence_prompt_plan_v1"


def test_run_gate_threads_presence_contract_into_prompt_builder(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = lena_profile.build_lena_presence_contract()
    seen: dict[str, object] = {}
    auth = authorities([scene("alpha")], [recipe("hcr_a")], [hook("hook_a")])
    prompt_candidates = [curator(image("alpha", "slot-a"))]

    def prompt_builder(as_of_date, head8, required_recipe_id="", presence_contract=None):
        seen["presence_contract"] = presence_contract
        return prompt_candidates, {"prompt_identity_sha256": "a" * 64}

    monkeypatch.setattr(gate, "_git", lambda *args: "a" * 40)
    monkeypatch.setattr(gate, "verify_authority_inputs_clean", lambda *args, **kwargs: None)
    path, decision, reused = gate.run_gate(
        "2026-07-15",
        tmp_path,
        presence_contract=contract,
        verify_clean=False,
        authority_loader=lambda: auth,
        recent_loader=recent,
        prompt_builder=prompt_builder,
    )

    assert seen["presence_contract"] == contract
    assert reused is False
    assert path.is_file()
    assert decision["candidate_status"] == "selected"


def test_presence_enabled_selection_can_change_the_winner_between_equally_valid_candidates() -> None:
    contract = lena_profile.build_lena_presence_contract()
    compiled = presence_plan.compile_human_presence_prompt_plan(contract, medium="still_image")
    auth = authorities(
        [scene("alpha"), scene("beta")],
        [recipe("hcr_a"), recipe("hcr_b")],
        [hook("hook_a"), hook("hook_b")],
    )
    candidates = [
        curator(image("alpha", "slot-a")),
        curator(presence_image(compiled, lane="beta", slot="slot-b")),
    ]

    selected_default, _ = select(auth, candidates)
    selected_presence, _, _ = gate.select_candidate(
        auth,
        candidates,
        recent(),
        presence_contract=contract,
    )

    assert selected_default["slot_id"] == "slot-a"
    assert selected_presence["slot_id"] == "slot-b"
    assert selected_presence["human_presence_ranking"]["total_bonus"] > 0


def test_presence_requested_with_malformed_metadata_fails_closed() -> None:
    with pytest.raises(gate.GateError) as error:
        gate.select_candidate(
            authorities(),
            [curator()],
            recent(),
            presence_contract={"schema_version": "bad"},
        )

    assert error.value.code == "unknown_schema_version"
