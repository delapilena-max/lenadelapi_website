from __future__ import annotations

import copy
import json
from pathlib import Path

from pipeline.presence import human_presence_contract_v1 as hpe_contract
import tools.strategy.lena_build_content_packet_dryrun_v1 as packet_builder


def _recipe() -> dict:
    return {
        "id": "hcr_011",
        "scene_type": "mirror_fitcheck",
        "content_pillar": "style_and_getting_ready",
        "platform_fit": ["Instagram Feed", "Facebook Feed"],
        "best_content_type": "photo",
        "visual_hook_reason": "Strong mirror save.",
        "human_reason": "Quiet fit check.",
        "style_lighting": "Soft apartment light with realistic shadow falloff.",
        "subject_pose": "Checking earrings in the mirror.",
        "fashion_accessories": "fitted black top, gold hoops",
        "setting_background": "real apartment vanity mirror with natural clutter",
        "technical_keywords": "35mm lens, natural grain, handheld realism",
        "negative_constraints": "No identity drift.",
        "caption_draft": "the mirror said yes first",
        "scene_logic_contract": {"environment_realism_notes": "real apartment, no showroom"},
        "linked_hook_categories": ["mirror_fitcheck"],
        "production_proof_mode": False,
        "wardrobe_outfit_id": "wc_p081",
        "environment_id": "env_p001",
        "environment_context": "Environment: apartment vanity mirror.",
        "proof_control_role": "",
    }


def _hook() -> dict:
    return {
        "id": "cbn_001",
        "category": "mirror_fitcheck",
        "hook_text": "This Stayed In The Camera Roll For A Minute.",
        "caption_followup": "I stood there for a minute. So did the mirror.",
        "optional_reels_opening_line": "A quick mirror save.",
        "suggested_comment_reply_angle": "quiet second-opinion energy",
        "scores": {"total_score": 91},
    }


def test_build_packet_is_deterministic_and_safe() -> None:
    recipe = _recipe()
    hook = _hook()

    first = packet_builder.build_packet(copy.deepcopy(recipe), copy.deepcopy(hook), "highest score", "2026-07-14")
    second = packet_builder.build_packet(copy.deepcopy(recipe), copy.deepcopy(hook), "highest score", "2026-07-14")

    assert first == second
    assert first["dry_run"] is True
    assert first["report_type"] == "lena_content_packet_dryrun"
    assert first["schema_version"] == "v1"
    assert first["provider_call_enabled"] is False
    assert first["generation_call_performed"] is False
    assert first["publishing_approval"] == "not_approved"
    assert first["compact_kling_prompt_chars"] < 2500
    assert first["compact_provider_prompt_chars"] == first["compact_kling_prompt_chars"]
    assert first["provider_prompt_contract"]["provider_route"] == "higgsfield_forward_no_live"
    assert first["provider_prompt_contract"]["live_authority"] is False
    assert first["provider_prompt_contract"]["scene_logic_contract_present"] is True
    assert first["compact_provider_prompt_sha256"]
    assert first["caption_draft"] == "the mirror said yes first"
    assert first["caption_followup"] == "I stood there for a minute. So did the mirror."


def test_validate_packet_rejects_hashtags_in_public_fields() -> None:
    packet = packet_builder.build_packet(_recipe(), _hook(), "highest score", "2026-07-14")
    packet["caption_draft"] = "quiet fit check #mirror"

    output_path = Path(packet_builder.OUTPUT_BASE) / "2026-07-14" / "test.json"
    flags, errors = packet_builder.validate_packet(packet, str(output_path))

    assert flags["all_checks_passed"] is False
    assert any("hashtags not allowed in public fields" in error for error in errors)


def test_realism_contract_keeps_freckle_filter_plastic_and_identity_blocks() -> None:
    assert "fake freckles" in packet_builder.SKIN_REALISM_COMPACT.lower()
    assert "beauty-filter speckling" in packet_builder.SKIN_REALISM_COMPACT.lower()
    assert "plastic" in packet_builder.SKIN_REALISM_COMPACT.lower()
    assert "identity drift" in packet_builder.STRUCTURED_TECHNICAL_REALISM.lower()
    assert "plastic skin" in packet_builder.STRUCTURED_TECHNICAL_REALISM.lower() or "plastic" in packet_builder.STRUCTURED_TECHNICAL_REALISM.lower()


def test_proof_prompt_budget_no_longer_reserves_noninjected_overlay_text() -> None:
    wardrobe_entry = {
        "outfit_id": "wc_long",
        "prompt": "very long " * 300,
        "status": "approved",
    }
    env_entry = {"prompt_fragment": "detailed environment " * 120}

    assert packet_builder.compute_proof_prompt_budget(wardrobe_entry, env_entry) == 2499


def test_rebuild_packet_from_authoritative_sources_reproduces_prompt_preview(monkeypatch) -> None:
    recipe = _recipe()
    hook = _hook()
    packet = packet_builder.build_packet(copy.deepcopy(recipe), copy.deepcopy(hook), "highest score", "2026-07-14")

    monkeypatch.setattr(packet_builder, "load_json", lambda path: {
        packet_builder.RECIPE_BANK: {"recipes": [copy.deepcopy(recipe)]},
        packet_builder.HOOK_BANK: {"hooks": [copy.deepcopy(hook)]},
        packet_builder.WARDROBE_CATALOG: {"outfits": [{"outfit_id": "wc_p081", "status": "approved", "name": "Top", "prompt": "opaque fitted top", "style_lane": "going_out", "notes": ""}]},
        packet_builder.ENV_CATALOG: {"environments": [{"environment_id": "env_p001", "allowed_recipe_types": ["mirror_fitcheck", "style_and_getting_ready"], "prompt_fragment": "apartment vanity mirror", "name": "Vanity"}]},
    }[path])

    rebuilt = packet_builder.rebuild_packet_from_authoritative_sources(packet)

    assert rebuilt["compact_provider_prompt_preview"] == packet["compact_provider_prompt_preview"]
    assert rebuilt["compact_provider_prompt_sha256"] == packet["compact_provider_prompt_sha256"]


def test_proof_mode_prompt_includes_hpe_presence_profile() -> None:
    recipe = _recipe()
    recipe["production_proof_mode"] = True
    hook = _hook()

    packet = packet_builder.build_packet(copy.deepcopy(recipe), copy.deepcopy(hook), "highest score", "2026-07-14")

    assert "[Subject Presence]:" in packet["compact_provider_prompt_preview"]
    assert "Camera-aware, self-possessed, quietly sensual;" in packet["compact_provider_prompt_preview"]


def test_non_proof_mode_prompt_excludes_subject_presence_section() -> None:
    recipe = _recipe()
    hook = _hook()

    structured = packet_builder.build_structured_kling_prompt(copy.deepcopy(recipe), max_chars=2499)
    packet = packet_builder.build_packet(copy.deepcopy(recipe), copy.deepcopy(hook), "highest score", "2026-07-14")

    assert "[Subject Presence]:" not in structured
    assert "[Subject Presence]:" not in packet["compact_provider_prompt_preview"]


def test_proof_mode_prompt_excludes_failure_indicator_vocabulary() -> None:
    recipe = _recipe()
    recipe["production_proof_mode"] = True
    hook = _hook()

    packet = packet_builder.build_packet(copy.deepcopy(recipe), copy.deepcopy(hook), "highest score", "2026-07-14")
    prompt = packet["compact_provider_prompt_preview"]

    assert "failure_indicators." not in prompt
    assert not any(indicator in prompt for indicator in hpe_contract.presence_failure_indicators())


def test_structured_prompt_preserves_complete_hcr_011_cinematography_clause() -> None:
    recipe_bank = json.loads(Path(packet_builder.RECIPE_BANK).read_text(encoding="utf-8-sig"))
    recipe = next(item for item in recipe_bank["recipes"] if item["id"] == "hcr_011")

    prompt = packet_builder.build_structured_kling_prompt(recipe, max_chars=2499)

    assert "blue-hour ambient mixed with warm lamp fill, candid apartment realism, non-studio." in prompt
    assert "blue-hour ambient mixed with warm [Lighting/Style]:" not in prompt
    assert "non-studio. [Lighting/Style]:" in prompt
    assert "[Lighting/Style]: Face-first available light only." in prompt
    assert len(prompt) <= 2499
