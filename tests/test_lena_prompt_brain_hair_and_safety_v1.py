from __future__ import annotations

from pathlib import Path

import pipeline.prompting.lena_prompt_brain as prompt_brain


RULES_PATH = Path(__file__).resolve().parents[1] / "pipeline" / "agents" / "lena" / "70_visual_qa" / "RULES.md"


def _stub_kling_prompt_path(monkeypatch):
    scene = {
        "lane": "city bench",
        "action": "standing by the bench",
        "camera": "natural candid framing",
        "lighting": "soft daylight",
        "caption": "caption",
    }
    wardrobe = {
        "outfit_id": "wc_001",
        "name": "fitted top",
        "style_lane": "going_out",
        "prompt": "fitted top",
    }

    monkeypatch.setattr(prompt_brain, "validate_saved_prompt_sources", lambda: None)
    monkeypatch.setattr(
        prompt_brain,
        "get_production_scene_pool",
        lambda *args, **kwargs: ([scene], {"version": "test"}),
    )
    monkeypatch.setattr(prompt_brain, "choose_scene_production", lambda *args, **kwargs: scene)
    monkeypatch.setattr(
        prompt_brain,
        "choose_environment_production",
        lambda *args, **kwargs: {"environment_id": "env_001", "name": "Cafe"},
    )
    monkeypatch.setattr(
        prompt_brain,
        "build_environment_prompt_parts",
        lambda *args, **kwargs: ("warm cafe interior", "menu details"),
    )
    monkeypatch.setattr(prompt_brain, "choose_reference_mode", lambda *args, **kwargs: "full_body")
    monkeypatch.setattr(prompt_brain, "pick_catalog_outfit_production", lambda *args, **kwargs: wardrobe)
    monkeypatch.setattr(prompt_brain, "format_catalog_wardrobe_override", lambda *args, **kwargs: "fitted top")
    monkeypatch.setattr(prompt_brain, "build_negative_prompt_for_catalog", lambda *args, **kwargs: "negative prompt")
    monkeypatch.setattr(
        prompt_brain,
        "build_public_lane_negative_prompt",
        lambda *args, **kwargs: kwargs.get("negative_prompt", args[2] if len(args) > 2 else "negative prompt"),
    )
    monkeypatch.setattr(
        prompt_brain,
        "choose_expression_gaze_production",
        lambda *args, **kwargs: {"expression_gaze_id": "exp_001", "label": "direct gaze"},
    )
    monkeypatch.setattr(prompt_brain, "format_expression_gaze_line", lambda *args, **kwargs: "direct gaze")
    monkeypatch.setattr(
        prompt_brain,
        "choose_frame_logic",
        lambda *args, **kwargs: {
            "frame_action": "frame action",
            "frame_evidence_objects": [],
            "frame_forbidden_objects": [],
            "camera_intent": "intent",
            "scene_coherence_note": "note",
        },
    )
    monkeypatch.setattr(prompt_brain, "format_frame_logic_paragraph", lambda *args, **kwargs: "frame logic")
    monkeypatch.setattr(
        prompt_brain,
        "choose_pose_body_language_production",
        lambda *args, **kwargs: {
            "pose_body_language_id": "pose_001",
            "label": "hip out",
            "hand_risk": "low",
            "compatibility_tags": [],
        },
    )
    monkeypatch.setattr(prompt_brain, "format_pose_body_language_line", lambda *args, **kwargs: "hip out")
    monkeypatch.setattr(prompt_brain, "reference_policy_for_mode", lambda *args, **kwargs: "reference policy")
    monkeypatch.setattr(prompt_brain, "framing_policy_for_mode", lambda *args, **kwargs: "framing policy")
    monkeypatch.setattr(prompt_brain, "build_body_visibility_rule", lambda *args, **kwargs: "body visibility rule")
    monkeypatch.setattr(prompt_brain, "public_capture_lock", lambda *args, **kwargs: "capture lock")
    monkeypatch.setattr(prompt_brain, "public_wardrobe_continuity_lock", lambda *args, **kwargs: "wardrobe lock")


def _stub_higgsfield_prompt_path(monkeypatch):
    scene = {
        "lane": "coffee shop",
        "action": "standing by the window",
        "camera": "wide shot",
        "lighting": "soft daylight",
        "caption": "caption",
    }
    wardrobe = {
        "outfit_id": "wc_002",
        "name": "fitted dress",
        "prompt": "fitted dress",
    }

    monkeypatch.setattr(prompt_brain, "validate_saved_prompt_sources", lambda: None)
    monkeypatch.setattr(
        prompt_brain,
        "get_production_scene_pool",
        lambda *args, **kwargs: ([scene], {"version": "test"}),
    )
    monkeypatch.setattr(prompt_brain, "choose_scene_production", lambda *args, **kwargs: scene)
    monkeypatch.setattr(
        prompt_brain,
        "choose_environment_production",
        lambda *args, **kwargs: {"environment_id": "env_002", "name": "Cafe"},
    )
    monkeypatch.setattr(
        prompt_brain,
        "build_environment_prompt_parts",
        lambda *args, **kwargs: ("warm cafe interior", "menu details"),
    )
    monkeypatch.setattr(prompt_brain, "pick_catalog_outfit_production", lambda *args, **kwargs: wardrobe)
    monkeypatch.setattr(
        prompt_brain,
        "choose_expression_gaze_production",
        lambda *args, **kwargs: {"expression_gaze_id": "exp_002", "label": "direct gaze"},
    )
    monkeypatch.setattr(
        prompt_brain,
        "choose_pose_body_language_production",
        lambda *args, **kwargs: {
            "pose_body_language_id": "pose_002",
            "label": "hip out",
            "hand_risk": "low",
            "compatibility_tags": [],
        },
    )


def test_active_prompt_paths_embed_shared_hair_directive_once_and_keep_anchors(monkeypatch) -> None:
    _stub_kling_prompt_path(monkeypatch)
    kling = prompt_brain.generate_prompt_package("2026-07-18", "slot-kling", "photo")
    kling_prompt = kling["prompt"]

    assert kling_prompt.count(prompt_brain.LENA_HAIR_VARIETY_DIRECTIVE) == 1
    assert prompt_brain.IDENTITY_ANCHOR in kling_prompt
    assert prompt_brain.LENA_MASTER_IDENTITY in kling_prompt

    _stub_higgsfield_prompt_path(monkeypatch)
    higgsfield = prompt_brain.generate_higgsfield_prompt_package("2026-07-18", "slot-higgsfield", "photo")
    higgsfield_prompt = higgsfield["prompt"]

    assert higgsfield_prompt.count(prompt_brain.LENA_HAIR_VARIETY_DIRECTIVE) == 1
    assert prompt_brain.HIGGSFIELD_BODY_SILHOUETTE_ANCHOR in higgsfield_prompt
    assert prompt_brain.HIGGSFIELD_FRAMING_LINE in higgsfield_prompt
    assert "Hair: brunette, long to medium-long, thick, naturally wavy" in higgsfield_prompt
    assert "Hair variation is allowed" in higgsfield_prompt
    assert "exact crown silhouette, exact part location, and exact front-curl shape are not identity traits" in higgsfield_prompt
    assert "Do not reproduce the same elevated front curl" in higgsfield_prompt
    assert "pompadour-like front wave" in higgsfield_prompt
    assert "rooster-comb silhouette" in higgsfield_prompt
    assert "oversized forehead wave" in higgsfield_prompt


def test_hairstyle_repeat_rule_is_human_qa_only_until_tracker_exists() -> None:
    rules_text = RULES_PATH.read_text(encoding="utf-8")
    assert "human-QA-only" in rules_text
    assert "structured recent-output comparison tracker in code yet" in rules_text
    assert "Do not invent a machine similarity score here." in rules_text


def test_adult_revealing_styles_are_explicitly_allowed_in_visual_qa_rules() -> None:
    rules_text = RULES_PATH.read_text(encoding="utf-8").lower()
    allowed_terms = [
        "scantily clad",
        "bikini",
        "lingerie",
        "underwear",
        "deep cleavage",
        "visible midriff",
        "exposed thighs and hips",
        "tight or sheer clothing",
        "sensual or provocative posing",
        "bedroom or dressing-room context",
        "emphasized curves",
        "implied nudity while nipples and genitals remain covered",
    ]
    for term in allowed_terms:
        assert term in rules_text


def test_explicit_exposure_and_age_ambiguity_still_fail_in_visual_qa_rules() -> None:
    rules_text = RULES_PATH.read_text(encoding="utf-8").lower()
    blocked_terms = [
        "visible genitals",
        "explicit nipple exposure",
        "depicted sexual acts",
        "masturbation",
        "coercive sexual content",
        "sexual violence",
        "age ambiguity",
    ]
    for term in blocked_terms:
        assert term in rules_text
