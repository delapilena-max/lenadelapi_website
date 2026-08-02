from __future__ import annotations

import socket
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline.media_properties.interstitial_travel_bureau.artifacts import EpisodeStore
from pipeline.media_properties.interstitial_travel_bureau.compilers import (
    compile_episode,
    compile_plan_to_request,
    compile_script_to_visual_context,
    compile_visual_to_generation_plan,
    compile_world_to_script_context,
)
from pipeline.media_properties.interstitial_travel_bureau.contracts import (
    ITBContractError,
    atomic_write_json,
    canonical_json_bytes,
    compilation_fingerprint,
)
from tests.itb_helpers import PILOT_ROOT, read_json


def test_all_four_compiler_stages_are_connected():
    store = EpisodeStore(PILOT_ROOT)
    canon = store.load("bureau_canon_v1")
    concept = store.load("bureau_concept_card_v1")
    world = store.load("bureau_world_dossier_v1")
    entity = store.load("bureau_entity_sheet_v1")
    script = store.load("bureau_episode_script_v1")
    visual = store.load("bureau_visual_sequence_v1")
    ledger = store.load("bureau_continuity_ledger_v1")
    script_context = compile_world_to_script_context(canon.data, concept.data, world.data, entity.data)
    visual_context = compile_script_to_visual_context(script.data, world.data, entity.data)
    plan = compile_visual_to_generation_plan(
        visual,
        entity,
        ledger,
        cost_ceiling_cents=0,
        attempt_ceiling=1,
    )
    assert script_context["impossible_rule"] == concept.data["impossible_rule"]
    assert len(visual_context["narration_segments"]) == 11
    assert len(plan["shot_requests"]) == 11


def test_repeated_compilation_is_byte_equivalent_and_matches_pilot():
    first_plan, first_request = compile_episode(PILOT_ROOT)
    second_plan, second_request = compile_episode(PILOT_ROOT)
    assert canonical_json_bytes(first_plan) == canonical_json_bytes(second_plan)
    assert canonical_json_bytes(first_request) == canonical_json_bytes(second_request)
    assert first_plan == read_json(PILOT_ROOT / "bureau_generation_plan_v1.json")
    assert first_request == read_json(PILOT_ROOT / "bureau_compiled_request_v1.json")


def test_compilation_timestamp_is_excluded_from_fingerprint():
    _, compiled = compile_episode(PILOT_ROOT)
    changed = deepcopy(compiled)
    changed["compilation_timestamp"] = "2099-01-01T00:00:00Z"
    assert compilation_fingerprint(changed) == compiled["deterministic_compilation_fingerprint"]


def test_compiled_request_is_disabled_and_provider_unassigned():
    plan, compiled = compile_episode(PILOT_ROOT)
    assert compiled["execution_authorized"] is False
    assert compiled["provider"] == "unassigned_provider_interface"
    assert compiled["model"] == "unassigned_model"
    serialized_plan = str(plan).lower()
    assert not any(name in serialized_plan for name in ("higgsfield", "kling", "seedance", "veo", "runway", "elevenlabs"))


def test_compilation_performs_no_network_activity(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network activity attempted")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    plan, compiled = compile_episode(PILOT_ROOT)
    assert plan["cost_ceiling_cents"] == 0
    assert compiled["execution_authorized"] is False


def test_atomic_write_requires_explicit_noncolliding_output(tmp_path: Path):
    output = tmp_path / "result.json"
    assert atomic_write_json(output, {"ok": True}) == "written"
    assert atomic_write_json(output, {"ok": True}) == "idempotent_match"
    with pytest.raises(ITBContractError) as error:
        atomic_write_json(output, {"ok": False})
    assert error.value.issues[0].code == "output_collision"
