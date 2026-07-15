from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.strategy.lena_audit_autonomous_generation_readiness_v1 as readiness


DATE = "2026-07-14"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _recipe_bank(path: Path) -> None:
    _write_json(
        path,
        {
            "recipes": [
                {
                    "id": "hcr_001",
                    "title": "Ready lane",
                    "scene_type": "rooftop",
                    "content_pillar": "identity",
                    "production_status": "active",
                    "proof_priority": 1,
                    "scene_logic_contract": {"required_visual_evidence": ["doorway"]},
                },
                {
                    "id": "hcr_002",
                    "title": "Missing packet lane",
                    "scene_type": "mirror",
                    "content_pillar": "trust",
                    "production_status": "active",
                    "proof_priority": 2,
                    "scene_logic_contract": {"required_visual_evidence": ["mirror"]},
                },
                {
                    "id": "hcr_test",
                    "title": "Test only lane",
                    "scene_type": "gym",
                    "content_pillar": "reach",
                    "production_status": "test_only",
                    "proof_priority": 99,
                    "scene_logic_contract": {"required_visual_evidence": ["bench"]},
                },
            ]
        },
    )


def _memory_policy(memory_path: str) -> dict:
    return {
        "memory_path": memory_path,
        "autonomy_gate": {
            "required_before_broader_autonomous_generation": [
                "three wins",
                "two face wins",
                "two garment wins",
                "four memory entries",
            ],
            "autonomous_publishing_unlocked": False,
        },
    }


def _gate_policy() -> dict:
    return {
        "require_all_priority_lanes_ready": True,
        "critical_blocker_reasons": [
            "recipe_missing",
            "recipe_scene_contract_missing",
            "packet_missing",
            "payload_missing",
            "payload_scene_contract_missing",
            "master_identity_missing",
            "blocked_terms_present",
            "payload_headroom_too_low",
        ],
        "critical_warning_reasons": [
            "style_bank_randomized_wardrobe",
            "environment_not_recipe_locked",
        ],
    }


def _memory_entries() -> list[dict]:
    return [
        {
            "qa_status": "approved",
            "skin_face_realism_notes": ["face reads believable"],
            "wardrobe_construction_notes": ["single garment continuity held"],
        },
        {
            "qa_status": "publishable",
            "skin_face_realism_notes": ["believable face-skin realism"],
            "wardrobe_construction_notes": ["dress continuity held"],
        },
        {
            "qa_status": "publishable_quality",
            "skin_face_realism_notes": [],
            "wardrobe_construction_notes": ["single garment continuity held"],
        },
        {
            "qa_status": "approved",
            "skin_face_realism_notes": [],
            "wardrobe_construction_notes": [],
        },
    ]


def test_grade_lane_fails_closed_and_preserves_warning_details() -> None:
    grade, reasons = readiness.grade_lane(
        {
            "recipe_present": True,
            "scene_logic_contract_in_recipe": True,
            "packet_present": False,
            "payload_present": True,
            "payload_scene_contract_present": False,
            "master_identity_body_present": False,
            "blocked_terms_absent": False,
            "payload_headroom": 12,
            "style_source": "style_bank",
            "environment_controlled": False,
        }
    )

    assert grade == "blocked"
    assert reasons[:5] == [
        "packet_missing",
        "payload_scene_contract_missing",
        "master_identity_missing",
        "blocked_terms_present",
        "payload_headroom_too_low",
    ]
    assert "style_bank_randomized_wardrobe" in reasons
    assert "environment_not_recipe_locked" in reasons
    assert "payload_headroom_narrow" in reasons


def test_default_priority_recipes_excludes_test_only_and_sorts_by_proof_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_bank = tmp_path / "recipe_bank.json"
    _recipe_bank(recipe_bank)
    monkeypatch.setattr(readiness, "RECIPE_BANK", recipe_bank)

    assert readiness.default_priority_recipes() == ["hcr_001", "hcr_002"]


def test_build_memory_progress_enforces_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory_file = tmp_path / "pipeline" / "state" / "memory.json"
    _write_json(memory_file, {"entries": _memory_entries()})
    memory_policy = tmp_path / "memory_policy.json"
    _write_json(memory_policy, _memory_policy("pipeline/state/memory.json"))

    monkeypatch.setattr(readiness, "ROOT", tmp_path)
    monkeypatch.setattr(readiness, "MEMORY_POLICY", memory_policy)

    progress = readiness.build_memory_progress()
    assert progress["wins_logged"] == 4
    assert progress["face_skin_wins_logged"] == 4
    assert progress["garment_stability_wins_logged"] == 3
    assert progress["memory_entries_logged"] == 4
    assert progress["broader_autonomous_generation_ready"] is True
    assert progress["autonomous_publishing_unlocked"] is False


def test_build_strategy_gate_status_aggregates_critical_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_policy = tmp_path / "gate.json"
    _write_json(gate_policy, _gate_policy())
    monkeypatch.setattr(readiness, "GATE_POLICY", gate_policy)

    status = readiness.build_strategy_gate_status(
        [
            {
                "recipe_id": "hcr_001",
                "title": "Blocked lane",
                "autonomy_grade": "blocked",
                "autonomy_reasons": [
                    "packet_missing",
                    "style_bank_randomized_wardrobe",
                ],
            },
            {
                "recipe_id": "hcr_002",
                "title": "Ready lane",
                "autonomy_grade": "ready",
                "autonomy_reasons": [],
            },
        ],
        {"broader_autonomous_generation_ready": False},
    )

    assert status["blocked"] is True
    assert status["block_reasons"] == [
        "aggregate_readiness_below_threshold",
        "critical_lane_failures_present",
        "not_all_priority_lanes_ready",
    ]
    assert status["blocked_lane_ids"] == ["hcr_001"]
    assert status["critical_blocker_hits"][0]["reasons"] == ["packet_missing"]
    assert status["critical_warning_hits"][0]["reasons"] == ["style_bank_randomized_wardrobe"]


def test_build_report_marks_missing_artifacts_blocked_and_emits_safe_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe_bank = tmp_path / "pipeline" / "prompt_banks" / "lena" / "bank.json"
    _recipe_bank(recipe_bank)
    memory_file = tmp_path / "pipeline" / "state" / "memory.json"
    _write_json(memory_file, {"entries": _memory_entries()})
    memory_policy = tmp_path / "pipeline" / "influencer_nodes" / "lena" / "memory_policy.json"
    _write_json(memory_policy, _memory_policy("pipeline/state/memory.json"))
    gate_policy = tmp_path / "pipeline" / "influencer_nodes" / "lena" / "gate.json"
    _write_json(gate_policy, _gate_policy())

    packet_dir = tmp_path / "pipeline" / "strategy" / "lena" / "content_packets" / DATE
    _write_json(
        packet_dir / f"lena_content_packet_dryrun_{DATE}_hcr_001.json",
        {
            "compact_kling_prompt_chars": 2400,
            "provider_prompt_contract": {
                "prompt_chars": 2440,
                "prompt_headroom": 59,
                "scene_logic_contract_present": True,
                "master_identity_body_present": True,
                "blocked_terms_absent": True,
                "outfit_controlled": True,
                "environment_controlled": True,
            },
            "wardrobe_outfit_id": "wc_001",
            "environment_id": "env_001",
            "content_pillar": "identity",
        },
    )

    monkeypatch.setattr(readiness, "ROOT", tmp_path)
    monkeypatch.setattr(readiness, "RECIPE_BANK", recipe_bank)
    monkeypatch.setattr(readiness, "MEMORY_POLICY", memory_policy)
    monkeypatch.setattr(readiness, "GATE_POLICY", gate_policy)
    monkeypatch.setattr(readiness, "PACKET_BASE", packet_dir.parent)

    report = readiness.build_report(DATE, ["hcr_001", "hcr_002"])
    assert report["lane_status_counts"] == {"ready_with_warnings": 1, "blocked": 1}
    assert report["lanes_ready"] == []
    assert report["lanes_ready_with_warnings"] == ["hcr_001"]
    assert report["lanes_blocked"] == ["hcr_002"]
    missing_lane = next(lane for lane in report["lanes"] if lane["recipe_id"] == "hcr_002")
    assert missing_lane["autonomy_grade"] == "blocked"
    assert "packet_missing" in missing_lane["autonomy_reasons"]
    assert "payload_missing" in missing_lane["autonomy_reasons"]
    assert report["safe_operations"] == {
        "api_call_made": False,
        "generation_call_performed": False,
        "upload_performed": False,
        "queue_mutated": False,
        "publish_performed": False,
        "credentials_read": False,
    }
    assert report["strategy_gate"]["blocked"] is True
    ready_lane = next(lane for lane in report["lanes"] if lane["recipe_id"] == "hcr_001")
    assert ready_lane["payload_path"].endswith(f"lena_content_packet_dryrun_{DATE}_hcr_001.json")
    assert ready_lane["provider_prompt_surface_status"] == ""


def test_save_report_writes_date_scoped_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness, "OUTPUT_BASE", tmp_path / "next_actions")
    path = readiness.save_report({"report_type": "lena_autonomous_generation_readiness_audit"}, DATE)
    assert path == tmp_path / "next_actions" / DATE / f"lena_autonomous_generation_readiness_audit_{DATE}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["report_type"] == "lena_autonomous_generation_readiness_audit"
