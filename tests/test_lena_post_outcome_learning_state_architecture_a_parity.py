from __future__ import annotations

from datetime import date

from tools.strategy.lena_build_post_outcome_learning_state_v1 import (
    actionable_metrics_only_posts,
    build_published_post_inventory,
    build_queue_boosts,
    classify_metrics_resolution,
    learning_status_from_items,
    metric_key,
    days_since,
)


def _manual_row(date_str: str, slot_id: str, platform: str, *, lane="", hook_category="", post_url="") -> dict:
    return {
        "date": date_str,
        "posted_at": "",
        "platform": platform,
        "slot_id": slot_id,
        "asset_path": "",
        "media_type": "photo",
        "lane": lane,
        "growth_bucket": "",
        "hook_category": hook_category,
        "post_url": post_url,
        "audio_name": "",
        "caption": "",
        "pinned_comment": "",
        "post_poll": "",
        "story_poll": "",
        "music_selected": "",
        "manual_publish_approved": "",
        "notes": "",
    }


def _metrics_row(
    date_str: str,
    slot_id: str,
    platform: str,
    *,
    instagram_media_id: str = "",
    permalink: str = "",
    lane: str = "",
    hook_category: str = "",
    post_url: str = "",
    classification: str = "pending",
    score: str = "0",
    source_slot_id: str = "",
) -> dict:
    return {
        "date": date_str,
        "slot_id": slot_id,
        "platform": platform,
        "media_type": "photo",
        "growth_bucket": "",
        "lane": lane,
        "hook_category": hook_category,
        "post_url": post_url,
        "audio_name": "",
        "reach": "0",
        "likes": "0",
        "saves": "0",
        "shares": "0",
        "comments": "0",
        "follows": "",
        "profile_visits": "",
        "completion_rate": "",
        "replay_rate": "",
        "score": score,
        "classification": classification,
        "notes": "",
        "post_id": slot_id,
        "instagram_media_id": instagram_media_id,
        "permalink": permalink,
        "source_slot_id": source_slot_id or slot_id,
        "publish_receipt_path": "",
        "source_asset_path": "",
        "clean_derivative_path": "",
        "source_asset_sha256": "",
        "clean_export_derivative_sha256": "",
        "clean_export_verified": "false",
        "wardrobe_outfit_id": "",
        "pose_body_language_id": "",
        "expression_gaze_id": "",
        "publish_architecture": "architecture_a",
        "published_timestamp": "",
        "qa_artifact_path": "",
        "approval_record_path": "",
    }


# 1. A metrics-only Architecture A row with real instagram_media_id is
# included in published inventory.
def test_metrics_only_row_with_real_media_id_is_included() -> None:
    manual_rows: list[dict] = []
    metrics_rows = [
        _metrics_row("2026-07-09", "readypack0709-pack007-00-photo-reel", "Instagram Reels",
                     instagram_media_id="18114662917723939")
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(inventory) == 1
    assert inventory[0]["slot_id"] == "readypack0709-pack007-00-photo-reel"


# 2. A manual-log-only historical post remains included.
def test_manual_log_only_post_remains_included() -> None:
    manual_rows = [_manual_row("2026-06-12", "2026-06-12-03-video", "TikTok")]
    metrics_rows: list[dict] = []
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(inventory) == 1
    assert inventory[0]["slot_id"] == "2026-06-12-03-video"


# 3. The same post in manual log and metrics dedupes to exactly one
# published post on (date, slot_id, platform).
def test_exact_collision_dedupes_to_one_published_post() -> None:
    manual_rows = [_manual_row("2026-07-05", "2026-07-05-01-photo", "Instagram Feed")]
    metrics_rows = [
        _metrics_row("2026-07-05", "2026-07-05-01-photo", "Instagram Feed",
                     instagram_media_id="18086313821391447")
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(inventory) == 1


# 4. On exact collision, richer manual values are preserved for fields
# such as lane, hook_category, and post_url.
def test_exact_collision_prefers_richer_manual_values() -> None:
    manual_rows = [
        _manual_row(
            "2026-07-05", "2026-07-05-01-photo", "Instagram Feed",
            lane="coffee", hook_category="coffee_walk",
            post_url="https://www.instagram.com/p/manual-real/",
        )
    ]
    metrics_rows = [
        _metrics_row(
            "2026-07-05", "2026-07-05-01-photo", "Instagram Feed",
            instagram_media_id="18086313821391447",
            lane="",  # metrics row itself has no lane recorded
            hook_category="",
            permalink="https://www.instagram.com/p/should-not-win/",
        )
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(inventory) == 1
    assert inventory[0]["lane"] == "coffee"
    assert inventory[0]["hook_category"] == "coffee_walk"
    assert inventory[0]["post_url"] == "https://www.instagram.com/p/manual-real/"


# 5. A metrics-only row without instagram_media_id is excluded.
def test_metrics_only_row_without_media_id_is_excluded() -> None:
    manual_rows: list[dict] = []
    metrics_rows = [
        _metrics_row("2026-07-08", "no-media-id-photo", "Instagram Feed", instagram_media_id="")
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert inventory == []
    assert actionable_metrics_only_posts(metrics_rows, set()) == []


# 6/7/8. Pending/stale computation, mirrored via the same real fields
# main() itself uses (metric_key, days_since), against union output.
def test_metrics_only_pending_row_enters_pending_and_stale_by_age() -> None:
    current_date = date(2026, 7, 12)
    manual_rows: list[dict] = []
    metrics_rows = [
        _metrics_row("2026-07-09", "stale-candidate-photo", "Instagram Feed",
                     instagram_media_id="111", classification="pending"),
        _metrics_row("2026-06-01", "very-stale-photo", "Instagram Feed",
                     instagram_media_id="222", classification="pending"),
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    stale_threshold = 4

    pending = []
    stale = []
    for post in inventory:
        age = days_since(post["date"], current_date)
        pending.append(post)
        if age is not None and age >= stale_threshold:
            stale.append(post)

    assert len(pending) == 2
    stale_slots = {p["slot_id"] for p in stale}
    assert "very-stale-photo" in stale_slots  # 2026-06-01 -> far past 4-day threshold
    assert "stale-candidate-photo" not in stale_slots  # 2026-07-09 -> only 3 days old


# 9. Two posts with the same date and slot but different platforms remain
# distinct.
def test_same_date_and_slot_different_platform_remain_distinct() -> None:
    manual_rows: list[dict] = []
    metrics_rows = [
        _metrics_row("2026-07-09", "shared-slot", "Instagram Feed", instagram_media_id="aaa"),
        _metrics_row("2026-07-09", "shared-slot", "Instagram Story", instagram_media_id="bbb"),
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(inventory) == 2
    keys = {(p["date"], p["slot_id"], p["platform"]) for p in inventory}
    assert keys == {
        ("2026-07-09", "shared-slot", "Instagram Feed"),
        ("2026-07-09", "shared-slot", "Instagram Story"),
    }


# 10. Derived Story and Reel posts sharing the same source_slot_id but
# different slot_id remain distinct -- mirrors the real
# readypack0709-pack007-00-photo-story / readypack0709-pack007-00-photo-reel case.
def test_derived_story_and_reel_sharing_source_slot_id_remain_distinct() -> None:
    manual_rows: list[dict] = []
    metrics_rows = [
        _metrics_row(
            "2026-07-09", "readypack0709-pack007-00-photo-story", "Instagram Story",
            instagram_media_id="17879977575673516",
            source_slot_id="readypack0709-pack007-00-photo",
        ),
        _metrics_row(
            "2026-07-09", "readypack0709-pack007-00-photo-reel", "Instagram Reels",
            instagram_media_id="18114662917723939",
            source_slot_id="readypack0709-pack007-00-photo",
        ),
    ]
    inventory = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(inventory) == 2
    slot_ids = {p["slot_id"] for p in inventory}
    assert slot_ids == {
        "readypack0709-pack007-00-photo-story",
        "readypack0709-pack007-00-photo-reel",
    }


# 11. queue_boosts remain unchanged by the published-inventory union --
# build_queue_boosts() never takes manual_rows or the union as input at
# all, so varying manual_rows must never change its output.
def test_queue_boosts_unchanged_by_published_inventory_union() -> None:
    metrics_rows = [
        _metrics_row("2026-07-01", "winner-photo", "Instagram Feed",
                     instagram_media_id="999", classification="winner", score="80",
                     lane="rooftop sunset", hook_category="golden_hour"),
    ]
    recipes = [{
        "id": "recipe-1",
        "production_status": "active",
        "scene_type": "rooftop sunset",
        "content_pillar": "",
        "title": "",
        "linked_hook_categories": ["golden_hour"],
        "proof_priority": 1,
    }]
    policy = {
        "queue_scoring": {"winner_boost": 22, "strong_boost": 14, "neutral_boost": 4, "recent_followup_bonus": 6},
        "freshness_windows": {"followup_days": 3},
        "winner_classifications": ["winner", "strong"],
    }
    current_date = date(2026, 7, 12)

    boosts_a, reasons_a, winners_a = build_queue_boosts(metrics_rows, recipes, policy, current_date)
    boosts_b, reasons_b, winners_b = build_queue_boosts(metrics_rows, recipes, policy, current_date)
    assert boosts_a == boosts_b
    assert reasons_a == reasons_b
    assert winners_a == winners_b


# 12. winner_posts remain unchanged by the published-inventory union --
# same underlying guarantee as #11, since winner_posts is a return value
# of build_queue_boosts(), which never sees manual_rows/the union.
def test_winner_posts_unchanged_by_published_inventory_union() -> None:
    metrics_rows = [
        _metrics_row("2026-07-01", "winner-photo", "Instagram Feed",
                     instagram_media_id="999", classification="winner", score="80",
                     lane="rooftop sunset", hook_category="golden_hour"),
    ]
    recipes = [{
        "id": "recipe-1",
        "production_status": "active",
        "scene_type": "rooftop sunset",
        "content_pillar": "",
        "title": "",
        "linked_hook_categories": ["golden_hour"],
        "proof_priority": 1,
    }]
    policy = {
        "queue_scoring": {"winner_boost": 22, "strong_boost": 14, "neutral_boost": 4, "recent_followup_bonus": 6},
        "freshness_windows": {"followup_days": 3},
        "winner_classifications": ["winner", "strong"],
    }
    current_date = date(2026, 7, 12)

    _, _, winners = build_queue_boosts(metrics_rows, recipes, policy, current_date)
    assert len(winners) == 1
    assert winners[0]["slot_id"] == "winner-photo"


# 13. Integration-level fixture: a representative mixed manual + metrics
# state proving the operational count transition, combining
# build_published_post_inventory(), metric_key(), and days_since() the
# same way main() itself does -- not just one isolated helper in
# isolation. Numbers are representative, not the real repo's actual
# production values.
def test_representative_mixed_state_operational_count_transition() -> None:
    current_date = date(2026, 7, 12)
    stale_threshold = 4
    manual_rows = [
        # Already resolved historically -- not pending.
        _manual_row("2026-06-24", "2026-06-24-01-photo", "Instagram Feed"),
        # Still pending, but recent -- pending, not stale.
        _manual_row("2026-07-10", "manual-recent-photo", "Instagram Feed"),
    ]
    metrics_by_key = {
        ("2026-06-24", "2026-06-24-01-photo", "Instagram Feed"): _metrics_row(
            "2026-06-24", "2026-06-24-01-photo", "Instagram Feed",
            instagram_media_id="ig-1", classification="weak",
        ),
        ("2026-07-10", "manual-recent-photo", "Instagram Feed"): _metrics_row(
            "2026-07-10", "manual-recent-photo", "Instagram Feed",
            instagram_media_id="ig-2", classification="pending",
        ),
    }
    metrics_rows = list(metrics_by_key.values()) + [
        # Previously invisible Architecture A posts, real instagram_media_id.
        _metrics_row("2026-07-09", "readypack0709-pack007-00-photo-story", "Instagram Story",
                     instagram_media_id="17879977575673516", classification="pending"),
        _metrics_row("2026-07-09", "readypack0709-pack007-00-photo-reel", "Instagram Reels",
                     instagram_media_id="18114662917723939", classification="pending"),
        # Old enough to be stale under the 4-day threshold from current_date.
        _metrics_row("2026-07-01", "old-architecture-a-photo", "Instagram Feed",
                     instagram_media_id="333", classification="pending"),
        # No real instagram_media_id -- must never be counted at all.
        _metrics_row("2026-07-11", "not-yet-actionable-photo", "Instagram Feed",
                     instagram_media_id=""),
    ]

    # Pre-fix behavior (manual_rows only), for comparison.
    pre_fix_published = len(manual_rows)
    pre_fix_pending = 0
    pre_fix_stale = 0
    for post in manual_rows:
        metric = metrics_by_key.get(metric_key(post), {})
        classification = (metric.get("classification") or "missing").strip().lower()
        if classification == "pending" or classification == "missing":
            pre_fix_pending += 1
            age = days_since(post["date"], current_date)
            if age is not None and age >= stale_threshold:
                pre_fix_stale += 1

    assert pre_fix_published == 2
    assert pre_fix_pending == 1
    assert pre_fix_stale == 0

    # Post-fix behavior: same loop shape, over the real union.
    published_post_rows = build_published_post_inventory(manual_rows, metrics_rows)
    metrics_index = {metric_key(row): row for row in metrics_rows}
    post_fix_pending = []
    post_fix_stale = []
    for post in published_post_rows:
        metric = metrics_index.get(metric_key(post), {})
        classification = (metric.get("classification") or "missing").strip().lower()
        if classification == "pending" or classification == "missing":
            post_fix_pending.append(post)
            age = days_since(post["date"], current_date)
            if age is not None and age >= stale_threshold:
                post_fix_stale.append(post)

    # 2 manual + 3 real actionable metrics-only posts (story, reel,
    # old-architecture-a-photo; the blank-media-id row and the manual-
    # duplicate row are never double/uncounted) = 5, not 7 --
    # representative, not identical to the real repo's literal current
    # count.
    assert len(published_post_rows) == 5
    assert len(post_fix_pending) == 4
    assert len(post_fix_stale) == 1

    stale_slot_ids = {p["slot_id"] for p in post_fix_stale}
    assert stale_slot_ids == {"old-architecture-a-photo"}

    published_slot_ids = {p["slot_id"] for p in published_post_rows}
    assert "not-yet-actionable-photo" not in published_slot_ids
    assert "readypack0709-pack007-00-photo-story" in published_slot_ids
    assert "readypack0709-pack007-00-photo-reel" in published_slot_ids


# Real Reel case, explicitly: published, pending, not stale on 2026-07-12
# under the existing 4-day threshold, because its canonical date is
# 2026-07-09 (3 days old).
def test_real_reel_is_published_pending_and_not_stale() -> None:
    current_date = date(2026, 7, 12)
    stale_threshold = 4
    manual_rows: list[dict] = []
    metrics_rows = [
        _metrics_row(
            "2026-07-09", "readypack0709-pack007-00-photo-reel", "Instagram Reels",
            instagram_media_id="18114662917723939",
            permalink="https://www.instagram.com/reel/DatBbJdkjzD/",
            classification="pending",
            source_slot_id="readypack0709-pack007-00-photo",
        ),
    ]
    published_post_rows = build_published_post_inventory(manual_rows, metrics_rows)
    assert len(published_post_rows) == 1
    reel = published_post_rows[0]
    assert reel["slot_id"] == "readypack0709-pack007-00-photo-reel"

    age = days_since(reel["date"], current_date)
    assert age == 3
    assert age < stale_threshold  # pending, not stale


def test_resolution_state_resolved_with_legitimate_zero_values() -> None:
    current_date = date(2026, 7, 12)
    post = _metrics_row(
        "2026-07-11",
        "resolved-zero-photo",
        "Instagram Feed",
        instagram_media_id="ig-resolved",
        permalink="https://example.com/p/resolved",
        lane="coffee",
        hook_category="hook",
        classification="weak",
        score="0",
    )
    for field in ("follows", "profile_visits", "completion_rate", "replay_rate"):
        post[field] = "0"
    post["reach"] = "0"
    post["likes"] = "0"
    post["saves"] = "0"
    post["shares"] = "0"
    post["comments"] = "0"
    post["publish_receipt_path"] = "C:\\receipts\\resolved-zero-photo.json.receipt.json"
    post["approval_record_path"] = "C:\\approvals\\resolved-zero-photo_approval.json"
    post["source_asset_sha256"] = "a" * 64
    post["clean_export_derivative_sha256"] = "b" * 64
    post["clean_export_verified"] = "true"

    resolution = classify_metrics_resolution(
        {"date": post["date"], "slot_id": post["slot_id"], "platform": post["platform"]},
        post,
        {"last_metrics_pull_by_post_key": {"2026-07-11|resolved-zero-photo|Instagram Feed": "2026-07-12T00:00:00+00:00"}},
        current_date,
        False,
        4,
    )

    assert resolution["metrics_resolution_state"] == "resolved"
    assert resolution["is_stale"] is False
    assert resolution["recommended_action"] == "no_metrics_resolution_action"


def test_resolution_state_manual_row_with_real_metrics_row_resolves_even_without_identity() -> None:
    current_date = date(2026, 7, 12)
    manual_post = _manual_row("2026-06-24", "2026-06-24-01-photo", "Instagram Feed")
    metric_row = _metrics_row(
        "2026-06-24",
        "2026-06-24-01-photo",
        "Instagram Feed",
        lane="coffee",
        hook_category="coffee_walk",
        classification="weak",
        score="0.0",
    )

    resolution = classify_metrics_resolution(
        manual_post,
        metric_row,
        {"last_metrics_pull_by_post_key": {"2026-06-24|2026-06-24-01-photo|Instagram Feed": "2026-06-29T00:00:00+00:00"}},
        current_date,
        True,
        4,
    )

    assert resolution["metrics_resolution_state"] == "resolved"
    assert resolution["is_stale"] is False
    assert resolution["recommended_action"] == "no_metrics_resolution_action"


def test_resolution_state_manual_only_placeholder_is_unverified() -> None:
    current_date = date(2026, 7, 12)
    manual_post = _manual_row("2026-06-12", "2026-06-12-03-video", "TikTok")

    resolution = classify_metrics_resolution(
        manual_post,
        {},
        {},
        current_date,
        True,
        4,
    )

    assert resolution["metrics_resolution_state"] == "manual_only_unverified"
    assert resolution["recommended_action"] == "manual_identity_or_metric_update_required"
    assert resolution["is_stale"] is True


def test_resolution_state_never_refreshed_real_publish_is_distinct() -> None:
    current_date = date(2026, 7, 12)
    post = _metrics_row(
        "2026-07-09",
        "never-refreshed-photo",
        "Instagram Reels",
        instagram_media_id="ig-never",
        permalink="https://www.instagram.com/reel/never/",
        lane="sidewalk dinner",
        classification="pending",
        score="0",
    )
    post["publish_receipt_path"] = "C:\\receipts\\never-refreshed-photo.json.receipt.json"
    post["approval_record_path"] = "C:\\approvals\\never-refreshed-photo_approval.json"

    resolution = classify_metrics_resolution(
        {"date": post["date"], "slot_id": post["slot_id"], "platform": post["platform"]},
        post,
        {},
        current_date,
        False,
        4,
    )

    assert resolution["metrics_resolution_state"] == "pending_never_refreshed"
    assert resolution["recommended_action"] == "request_supported_meta_refresh"
    assert resolution["is_stale"] is False


def test_resolution_state_refreshed_but_unsupported_fields_remain_pending() -> None:
    current_date = date(2026, 7, 12)
    post = _metrics_row(
        "2026-07-09",
        "unsupported-photo",
        "Instagram Feed",
        instagram_media_id="ig-supported",
        permalink="https://www.instagram.com/p/unsupported/",
        lane="rooftop sunset",
        classification="pending",
        score="0",
    )
    post["publish_receipt_path"] = "C:\\receipts\\unsupported-photo.json.receipt.json"
    post["approval_record_path"] = "C:\\approvals\\unsupported-photo_approval.json"
    post["notes"] = "Auto-synced from Architecture A publish receipt (C:\\receipts\\unsupported-photo.json.receipt.json); update metrics after performance data is available. | auto_meta_metrics_refresh:2026-07-11"
    post["follows"] = ""
    post["profile_visits"] = ""
    post["completion_rate"] = ""
    post["replay_rate"] = ""

    resolution = classify_metrics_resolution(
        {"date": post["date"], "slot_id": post["slot_id"], "platform": post["platform"]},
        post,
        {"last_metrics_pull_by_post_key": {"2026-07-09|unsupported-photo|Instagram Feed": "2026-07-11T00:00:00+00:00"}},
        current_date,
        False,
        4,
    )

    assert resolution["metrics_resolution_state"] == "pending_unsupported"
    assert resolution["recommended_action"] == "manual_or_future_capability_resolution_required"
    assert resolution["unsupported_missing_fields"] == ["completion_rate", "follows", "profile_visits", "replay_rate"]


def test_resolution_state_staleness_is_independent_overlay() -> None:
    current_date = date(2026, 7, 14)
    post = _metrics_row(
        "2026-07-09",
        "stale-photo",
        "Instagram Feed",
        instagram_media_id="ig-stale",
        permalink="https://www.instagram.com/p/stale/",
        lane="rooftop sunset",
        classification="pending",
        score="0",
    )
    post["publish_receipt_path"] = "C:\\receipts\\stale-photo.json.receipt.json"
    post["approval_record_path"] = "C:\\approvals\\stale-photo_approval.json"
    post["notes"] = "Auto-synced from Architecture A publish receipt (C:\\receipts\\stale-photo.json.receipt.json); update metrics after performance data is available. | auto_meta_metrics_refresh:2026-07-11"

    resolution = classify_metrics_resolution(
        {"date": post["date"], "slot_id": post["slot_id"], "platform": post["platform"]},
        post,
        {"last_metrics_pull_by_post_key": {"2026-07-09|stale-photo|Instagram Feed": "2026-07-11T00:00:00+00:00"}},
        current_date,
        False,
        4,
    )

    assert resolution["metrics_resolution_state"] == "pending_unsupported"
    assert resolution["is_stale"] is True


def test_learning_status_helper_distinguishes_current_incomplete_and_stale() -> None:
    assert learning_status_from_items([
        {"metrics_resolution_state": "resolved", "is_stale": False},
    ]) == "current"
    assert learning_status_from_items([
        {"metrics_resolution_state": "pending_never_refreshed", "is_stale": False},
    ]) == "usable_but_incomplete"
    assert learning_status_from_items([
        {"metrics_resolution_state": "pending_unsupported", "is_stale": True},
    ]) == "stale_unresolved"
