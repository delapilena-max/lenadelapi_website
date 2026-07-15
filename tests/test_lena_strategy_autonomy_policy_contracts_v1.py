from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"


POST_OUTCOME_POLICY = NODE / "post_outcome_learning_policy_v1.json"
FOLLOWUP_POLICY = NODE / "followup_post_decision_policy_v1_7.json"
SCORING_MODEL = NODE / "post_metric_scoring_model_v1_6_1.json"
REALISM_POLICY = NODE / "life_engine_realism_memory_policy_v1.json"
AUTONOMY_GATE_POLICY = NODE / "strategy_autonomy_gate_policy_v1.json"
WORLD_CONTINUITY_POLICY = NODE / "world_continuity_policy_v1.json"
ENGAGEMENT_SELECTION_POLICY = NODE / "engagement_selection_policy_v1.json"
AUTONOMY_LADDER_CONTRACT = NODE / "autonomy_ladder_v1.json"
DAILY_CADENCE = NODE / "daily_cadence.json"
CONTENT_BUCKETS = NODE / "content_buckets.json"
GENERATION_POLICY = ROOT / "pipeline" / "config" / "lena_generation_policy.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_policy_files_parse_as_static_json_source() -> None:
    for path in (
        POST_OUTCOME_POLICY,
        FOLLOWUP_POLICY,
        SCORING_MODEL,
        REALISM_POLICY,
        AUTONOMY_GATE_POLICY,
        WORLD_CONTINUITY_POLICY,
        ENGAGEMENT_SELECTION_POLICY,
        AUTONOMY_LADDER_CONTRACT,
        DAILY_CADENCE,
        CONTENT_BUCKETS,
        GENERATION_POLICY,
    ):
        payload = _read_json(path)
        assert isinstance(payload, dict)
        assert "generated_at" not in payload
        assert "updated_at" not in payload


def test_post_outcome_policy_fields_and_cross_references_are_present() -> None:
    policy = _read_json(POST_OUTCOME_POLICY)
    scoring = _read_json(SCORING_MODEL)

    assert policy["version"] == "v1.0.0"
    assert policy["winner_classifications"] == ["winner", "strong"]
    assert policy["pending_classifications"] == ["pending"]
    assert policy["queue_scoring"]["winner_boost"] > policy["queue_scoring"]["strong_boost"] > policy["queue_scoring"]["neutral_boost"] > 0
    assert policy["freshness_windows"]["followup_days"] > 0
    assert policy["freshness_windows"]["metrics_stale_days"] >= policy["freshness_windows"]["followup_days"]
    assert policy["operational_alerts"]["stale_pending_metrics_threshold"] >= 1

    assert set(policy["winner_classifications"] + ["neutral", "weak"]).issubset(set(scoring["classification"]))
    assert policy["pending_classifications"] == ["pending"]

    for field in (
        "manual_post_log_path",
        "post_metrics_path",
        "publish_state_path",
        "state_path",
        "report_dir",
    ):
        assert isinstance(policy[field], str)
        assert ":" not in policy[field]
        assert "\\" not in policy[field]


def test_followup_policy_mappings_and_rules_are_nonempty_and_stable() -> None:
    policy = _read_json(FOLLOWUP_POLICY)

    assert policy["version"] == "v1.7.0"
    assert isinstance(policy["signals_to_followups"], dict)
    assert set(policy["signals_to_followups"]) == {
        "outfit_request",
        "routine_request",
        "audio_question",
        "flirty",
        "high_saves",
        "high_comments",
        "high_shares",
    }
    assert all(isinstance(value, str) and value.strip() for value in policy["signals_to_followups"].values())
    assert isinstance(policy["rules"], list)
    assert len(policy["rules"]) >= 3
    assert all(isinstance(rule, str) and rule.endswith(".") for rule in policy["rules"])


def test_scoring_model_thresholds_and_weights_are_internally_valid() -> None:
    model = _read_json(SCORING_MODEL)

    assert model["version"] == "v1.6.1"
    assert model["weights"]["follows"] > model["weights"]["shares"] > model["weights"]["comments"] > model["weights"]["likes"] > 0
    assert model["weights"]["completion_rate"] > model["weights"]["profile_visits"] > 0
    thresholds = model["classification"]
    assert thresholds["winner"] > thresholds["strong"] > thresholds["neutral"] > thresholds["weak"]
    assert thresholds["weak"] == 0


def test_realism_policy_fields_match_current_consumers_and_contain_no_secrets() -> None:
    policy = _read_json(REALISM_POLICY)
    serialized = json.dumps(policy, sort_keys=True)

    assert policy["version"] == "v1.0.0"
    assert policy["memory_path"] == "pipeline/state/lena_life_engine_realism_memory_v1.json"
    for field in (
        "task_id",
        "date",
        "recipe_id",
        "outfit_id",
        "environment_id",
        "provider",
        "qa_status",
        "skin_face_realism_notes",
        "wardrobe_construction_notes",
        "environment_realism_notes",
    ):
        assert field in policy["remember_after_generation_review"]
    assert set(policy["realism_axes"]) == {
        "face_skin_realism",
        "body_realism",
        "wardrobe_realism",
        "environment_realism",
        "account_realism",
    }
    assert policy["autonomy_gate"]["autonomous_publishing_unlocked"] is False
    assert len(policy["autonomy_gate"]["required_before_broader_autonomous_generation"]) >= 4
    assert not re.search(r"[A-Za-z]:\\\\", serialized)
    assert "api_key" not in serialized.lower()
    assert "token" not in serialized.lower()
    assert "secret" not in serialized.lower()


def test_strategy_gate_policy_matches_current_readiness_consumers() -> None:
    policy = _read_json(AUTONOMY_GATE_POLICY)

    assert policy["version"] == "v1.0.0"
    assert policy["require_all_priority_lanes_ready"] is True
    assert set(policy["critical_blocker_reasons"]) == {
        "recipe_missing",
        "recipe_scene_contract_missing",
        "packet_missing",
        "payload_missing",
        "payload_scene_contract_missing",
        "master_identity_missing",
        "blocked_terms_present",
        "payload_headroom_too_low",
    }
    assert set(policy["critical_warning_reasons"]) == {
        "style_bank_randomized_wardrobe",
        "environment_not_recipe_locked",
    }
    assert policy["soft_warning_reasons"] == ["payload_headroom_narrow"]


def test_world_continuity_policy_daily_cadence_content_buckets_and_generation_policy_are_static_and_complete() -> None:
    continuity = _read_json(WORLD_CONTINUITY_POLICY)
    cadence = _read_json(DAILY_CADENCE)
    buckets = _read_json(CONTENT_BUCKETS)
    generation = _read_json(GENERATION_POLICY)

    assert continuity["version"] == "v1.0.0"
    assert continuity["state_path"] == "pipeline/state/lena_world_state_v1.json"
    assert continuity["recent_memory_window"] >= continuity["balance_window"] >= 1
    assert continuity["rotation_preview_limit"] >= 1
    assert continuity["queue_rotation_policy"]["prefer_top_n"] >= 1
    assert continuity["queue_rotation_policy"]["deprioritize_if_score_below"] > 0
    soft_caps = continuity["anti_repetition"]["soft_caps"]
    assert soft_caps["mirror_lane_in_balance_window"] >= 1
    assert soft_caps["proof_mode_in_balance_window"] >= 1
    assert continuity["context_mix_targets"]["max_home_share_in_balance_window"] < 1
    assert continuity["context_mix_targets"]["min_public_or_fitness_share_in_balance_window"] > 0

    assert cadence["version"] == "v1.3.1"
    assert cadence["daily_posts"] == 5
    assert set(cadence["slot_strategy"]) == {"01", "02", "03", "04", "05"}
    assert cadence["slot_strategy"]["03"]["media_type"] == "video"
    assert cadence["slot_strategy"]["03"]["music_required"] is True

    assert buckets["version"] == "v1.3.1"
    assert set(buckets["buckets"]) == {"reach", "trust", "engagement", "identity"}
    assert all(buckets["buckets"][name]["rules"] for name in buckets["buckets"])

    assert generation["generation"]["image_engine"] == "higgsfield_text2image_soul_v2"
    assert generation["generation"]["video_engine"] == "kling_video_3.0"
    assert generation["caption_rules"]["hashtag_count_min"] == 0
    assert generation["caption_rules"]["hashtag_count_max"] == 3
    assert generation["caption_rules"]["hashtag_count_min"] <= generation["caption_rules"]["hashtag_count_max"] <= 3
    assert generation["safety"]["dry_run_until_preflight_passes"] is True


def test_engagement_selection_policy_ranges_and_paths_are_valid() -> None:
    policy = _read_json(ENGAGEMENT_SELECTION_POLICY)

    assert policy["version"] == "v1.0.0"
    assert policy["signals_path"] == "pipeline/analytics/lena_engagement_signals_v1_6.csv"
    assert policy["state_path"] == "pipeline/state/lena_engagement_demand_state_v1.json"
    assert policy["report_dir"] == "pipeline/strategy/lena/next_actions"
    assert policy["minimum_signal_count_to_activate"] >= 1
    assert policy["max_signal_count_per_class_for_scoring"] >= policy["minimum_signal_count_to_activate"]
    assert policy["default_primary_boost"] > policy["default_secondary_boost"] > 0
    assert {
        "outfit_request",
        "routine_request",
        "food_question",
        "flirty",
        "audio_question",
        "compliment",
    } == set(policy["signal_class_map"])
    for config in policy["signal_class_map"].values():
        assert isinstance(config["preferred_recipe_ids"], list)
        assert isinstance(config["secondary_recipe_ids"], list)
        assert isinstance(config["notes"], str) and config["notes"].strip()
