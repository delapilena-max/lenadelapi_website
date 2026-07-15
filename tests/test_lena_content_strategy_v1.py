import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline/influencer_nodes/lena"
PROMPTS = ROOT / "pipeline/prompt_banks/lena"

APPROVED_PILLARS = {
    "everyday_lena",
    "style_and_getting_ready",
    "beautiful_trouble",
    "city_and_social_life",
    "adventure_and_escape",
    "audience_choice_and_payoff",
    "high_heat_glamour",
}
TEMPERATURES = {"quiet", "warm", "glamorous", "high_heat"}
NARRATIVE_ROLES = {
    "setup", "choice", "anticipation", "experience", "consequence",
    "payoff", "aftermath", "quiet_reset", "world_expansion",
}
NEW_HOOK_CATEGORIES = {
    "curiosity_open_loop", "consequence", "meaningful_choice", "payoff",
    "adventure_escape", "situational_humor", "quiet_personal",
    "world_expansion", "callback",
}
SCENE_IDS = {
    "morning apartment", "apartment doorway", "coffee shop", "rainy street",
    "rooftop sunset", "bookstore", "grocery run", "car moment", "studio desk",
    "night out", "dinner booth", "wine bar patio", "brunch patio",
    "sidewalk dinner", "lobby cocktail bar", "skincare evening", "airport day",
    "gym cooldown", "laundry day", "museum afternoon", "late kitchen snack",
    "flower shop", "record store", "mirror outfit check", "city bench",
    "elevator moment", "motorcycle street glam", "heritage moto pinup",
    "antique cruiser editorial", "custom chopper eye candy", "garage grease glam",
    "bike wash bikini", "desert roadside cruiser",
}
BLOCKED_SCENES = {
    "airport day", "apartment doorway", "elevator moment", "grocery run",
    "gym cooldown", "late kitchen snack", "mirror outfit check", "skincare evening",
    "studio desk", "motorcycle street glam", "heritage moto pinup",
    "antique cruiser editorial", "custom chopper eye candy", "garage grease glam",
    "bike wash bikini", "desert roadside cruiser",
}
RECIPE_IDS = {f"hcr_{number:03d}" for number in range(1, 20)}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_strategy_metadata(item):
    assert item["strategy_pillars"]
    assert set(item["strategy_pillars"]) <= APPROVED_PILLARS
    assert item["creative_temperature"] in TEMPERATURES
    assert item["narrative_roles"]
    assert set(item["narrative_roles"]) <= NARRATIVE_ROLES
    assert isinstance(item["choice_eligible"], bool)
    assert isinstance(item["payoff_eligible"], bool)


def test_persona_encodes_approved_niche_promise_pillars_and_balance():
    persona = read_json(NODE / "persona.json")
    assert persona["canonical_niche"] == "Glamour, Choices, And Beautiful Trouble"
    assert persona["core_promise"]["summary"]
    assert set(persona["content_pillars"]) == APPROVED_PILLARS
    assert len(persona["content_pillars"]) == 7
    assert persona["content_pillar_definitions"]["high_heat_glamour"].endswith(
        "one pillar, never the whole account."
    )
    assert "not sexual in every post" in persona["anti_thirst_trap_rule"]


def test_strategy_contract_owns_complete_taxonomy_and_balance_doctrine():
    strategy = read_json(NODE / "lena_content_strategy_v1.json")
    assert set(strategy["pillar_ids"]) == APPROVED_PILLARS
    assert set(strategy["creative_temperatures"]) == TEMPERATURES
    assert set(strategy["narrative_roles"]) == NARRATIVE_ROLES
    balance = strategy["balance_rules"]
    assert balance["mode"] == "sequencing_not_percentage_quota"
    assert balance["no_consecutive_high_heat_posts"] is True
    assert balance["normal_lower_temperature_or_story_forward_spacing_posts"] == 2
    assert balance["publishing_quotas_added"] is False
    assert "pool" in strategy["high_heat_rules"]["swimwear_requires_context"]
    assert strategy["high_heat_rules"]["is_one_pillar_not_whole_account"] is True


def test_choice_payoff_limits_and_protected_topics_are_explicit():
    strategy = read_json(NODE / "lena_content_strategy_v1.json")
    choice = strategy["audience_choice_contract"]
    assert choice["followers_may_influence"] is True
    assert choice["followers_control_lena"] is False
    assert choice["maximum_unresolved_choices"] == 2
    assert set(choice["protected_poll_topics"]) == {
        "identity", "safety", "body_shape", "intimate_behavior", "major_life_claims"
    }
    payoff = strategy["payoff_contract"]
    assert payoff["normal_payoff_window_posts"] == {"minimum": 1, "maximum": 3}
    assert payoff["unresolved_choice_ceiling_posts"] == 5
    assert payoff["longer_arc_requires_explicit_designation"] is True


def test_every_scene_has_valid_metadata_without_id_or_block_changes():
    bank = read_json(PROMPTS / "lena_photo_scene_bank_v1.json")
    assert {scene["lane"] for scene in bank["scenes"]} == SCENE_IDS
    assert set(bank["production_blocked_lanes"]) == BLOCKED_SCENES
    for scene in bank["scenes"]:
        assert_strategy_metadata(scene)
    rainy_street = next(scene for scene in bank["scenes"] if scene["lane"] == "rainy street")
    assert rainy_street["strategy_pillars"][0] == "city_and_social_life"
    assert "adventure_and_escape" not in rainy_street["strategy_pillars"]
    motorcycle_scenes = {scene for scene in SCENE_IDS if "moto" in scene or "cruiser" in scene or "chopper" in scene or "garage" in scene or "bike wash" in scene}
    assert motorcycle_scenes <= BLOCKED_SCENES


def test_every_recipe_has_valid_metadata_without_id_changes_or_fabricated_lanes():
    bank = read_json(PROMPTS / "lena_high_caliber_prompt_recipe_bank_v1.json")
    assert {recipe["id"] for recipe in bank["recipes"]} == RECIPE_IDS
    for recipe in bank["recipes"]:
        assert_strategy_metadata(recipe)
        assert recipe["strategy_pillars"][0] not in {"adventure_and_escape", "high_heat_glamour"}
    strategy = read_json(NODE / "lena_content_strategy_v1.json")
    assert strategy["current_catalog_gaps"]["adventure_recipe_ids"] == []
    assert strategy["current_catalog_gaps"]["high_heat_recipe_ids"] == []


def test_hook_expansion_is_complete_unique_and_recipe_links_are_valid():
    hooks = read_json(PROMPTS / "strong_hook_bank_v1.json")
    categories = set(hooks["categories"])
    assert NEW_HOOK_CATEGORIES <= categories
    ids = [hook["id"] for hook in hooks["hooks"]]
    assert len(ids) == len(set(ids))
    required = {
        "id", "category", "hook_text", "word_count", "best_platforms",
        "best_content_type", "visual_pairing", "caption_followup",
        "optional_reels_opening_line", "suggested_comment_reply_angle",
        "scores", "risk_notes",
    }
    for category in NEW_HOOK_CATEGORIES:
        category_hooks = [hook for hook in hooks["hooks"] if hook["category"] == category]
        assert len(category_hooks) >= 3
        assert all(required <= hook.keys() for hook in category_hooks)
        assert all(hook["word_count"] == len(hook["hook_text"].split()) for hook in category_hooks)
    recipes = read_json(PROMPTS / "lena_high_caliber_prompt_recipe_bank_v1.json")
    assert set(recipes["valid_hook_categories"]) == categories
    for recipe in recipes["recipes"]:
        assert set(recipe["linked_hook_categories"]) <= categories


def test_source_caption_contracts_remain_hashtag_light_and_packet_safe() -> None:
    recipes = read_json(PROMPTS / "lena_high_caliber_prompt_recipe_bank_v1.json")
    hooks = read_json(PROMPTS / "strong_hook_bank_v1.json")

    for recipe in recipes["recipes"]:
        caption = recipe.get("caption_draft", "")
        hashtags = re.findall(r"#[A-Za-z0-9_]+", caption)
        assert hashtags == []
        assert len(hashtags) <= 3

    for hook in hooks["hooks"]:
        for field in (
            "caption_followup",
            "optional_reels_opening_line",
            "suggested_comment_reply_angle",
        ):
            hashtags = re.findall(r"#[A-Za-z0-9_]+", hook.get(field, "") or "")
            assert hashtags == []
            assert len(hashtags) <= 3


def test_historical_assets_authority_and_dormant_policy_boundaries_are_explicit():
    strategy = read_json(NODE / "lena_content_strategy_v1.json")
    history = strategy["historical_asset_policy"]
    assert history == {
        "existing_assets_remain_valid": True,
        "historical_assets_are_immutable": True,
        "strategy_change_is_prospective_only": True,
    }
    authority = strategy["authority_precedence"]
    assert "public identity" in authority["persona_json"]
    assert "temperature" in authority["lena_content_strategy_v1_json"]
    assert authority["scene_and_recipe_banks"].endswith("classification only.")
    assert "reusable hook patterns" in authority["strong_hook_bank_v1_json"]
    assert authority["dormant_untracked_policies"].startswith("Reference material only")
    assert authority["dormant_reference_paths"]


def test_future_world_state_fields_are_reserved_but_not_wired():
    bridge = read_json(NODE / "lena_content_strategy_v1.json")["future_world_state_bridge"]
    assert bridge["status"] == "reserved_not_wired"
    assert set(bridge["reserved_fields"]) == {
        "story_arc_id", "narrative_role", "open_choice_id", "choice_options",
        "choice_status", "opened_at_post_id", "selected_option",
        "payoff_due_after_posts", "payoff_post_id", "operator_override_reason",
    }
