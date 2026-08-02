from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from pipeline.media_properties.interstitial_travel_bureau.artifacts import EpisodeStore
from pipeline.media_properties.interstitial_travel_bureau.validation import (
    validate_episode_root,
    validate_loaded_episode,
)
from tests.itb_helpers import PILOT_ROOT


def test_pilot_001_passes_generic_episode_pipeline():
    report = validate_episode_root(PILOT_ROOT)
    assert report["ok"] is True
    assert report["artifacts_validated"] == 14
    assert report["errors"] == []
    assert all(value == 0 for value in report["counters"].values())


def test_pilot_locked_direction_and_diversity_are_preserved():
    artifacts = EpisodeStore(PILOT_ROOT).load_all()
    script = artifacts["bureau_episode_script_v1"].data
    visual = artifacts["bureau_visual_sequence_v1"].data
    audio = artifacts["bureau_audio_plan_v1"].data
    assert script["selected_hook"] == "Your reflection should not be waiting for you."
    assert audio["narrator_profile"]["register"] == "warm_bureau_baritone"
    assert visual["target_duration_ms"] == 60000
    assert len(visual["shots"]) == 11
    assert len({shot["environment"] for shot in visual["shots"]}) >= 3
    assert len({shot["camera"] for shot in visual["shots"]}) >= 3


def test_extended_short_profile_requires_explicit_user_lock():
    artifacts = EpisodeStore(PILOT_ROOT).load_all()
    concept = artifacts["bureau_concept_card_v1"]
    concept_data = deepcopy(concept.data)
    concept_data["user_input"]["locked_elements"] = [
        lock
        for lock in concept_data["user_input"]["locked_elements"]
        if lock["field_path"] != "/bureau_visual_sequence_v1/sequence_profile"
    ]
    artifacts["bureau_concept_card_v1"] = replace(concept, data=concept_data)

    issues = validate_loaded_episode(artifacts)

    assert "extended_profile_user_lock_missing" in {issue.code for issue in issues}


def test_pilot_has_no_generation_or_provider_claims():
    store = EpisodeStore(PILOT_ROOT)
    manifest = store.load("bureau_episode_manifest_v1").data
    learning = store.load("bureau_episode_learning_v1").data
    compiled = store.load("bureau_compiled_request_v1").data
    assert manifest["lifecycle_state"] == "pre_generation"
    assert manifest["generated_assets"] == []
    assert manifest["provider_jobs"] == []
    assert manifest["total_cost_cents"] == 0
    assert learning["platform"] == "none"
    assert compiled["execution_authorized"] is False


def test_compiled_example_prompt_is_concrete_and_ordered():
    compiled = EpisodeStore(PILOT_ROOT).load("bureau_compiled_request_v1").data
    prompt = compiled["shot_requests"][0]["exact_compiled_prompt"]
    assert prompt.startswith("[Environment] mirror_customs_hall\n[Subject]")
    assert "[Motion]" in prompt
    assert "amber_eye_catchlight" in prompt
    assert "cinematic" not in prompt.lower()
