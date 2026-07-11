from __future__ import annotations

from datetime import date, timedelta

import tools.lena_meta_refresh_feedback_v1 as mod


def _manual_row(
    *,
    day: str,
    slot_id: str,
    platform: str = "Instagram Feed",
    post_url: str = "https://example.com/p/1",
    posted_at: str = "2026-07-11T10:00:00",
    notes: str = "",
) -> dict:
    return {
        "date": day,
        "posted_at": posted_at,
        "platform": platform,
        "slot_id": slot_id,
        "asset_path": "",
        "media_type": "photo",
        "lane": "coffee",
        "growth_bucket": "engagement",
        "hook_category": "hook",
        "post_url": post_url,
        "audio_name": "",
        "caption": "caption",
        "pinned_comment": "",
        "post_poll": "",
        "story_poll": "",
        "music_selected": "true",
        "manual_publish_approved": "true",
        "notes": notes,
    }


def _metric_row(
    *,
    day: str,
    slot_id: str,
    platform: str = "Instagram Feed",
    instagram_media_id: str = "",
    post_url: str = "",
    posted_lane: str = "",
) -> dict:
    return {
        "date": day,
        "slot_id": slot_id,
        "platform": platform,
        "media_type": "photo",
        "growth_bucket": "",
        "lane": posted_lane,
        "hook_category": "",
        "post_url": post_url,
        "audio_name": "",
        "reach": "0",
        "likes": "0",
        "saves": "0",
        "shares": "0",
        "comments": "0",
        "follows": "0",
        "profile_visits": "0",
        "completion_rate": "0",
        "replay_rate": "0",
        "score": "0",
        "classification": "pending",
        "notes": "",
        "post_id": slot_id,
        "instagram_media_id": instagram_media_id,
        "permalink": post_url,
    }


def test_architecture_a_metrics_only_row_with_real_media_id_is_discovered() -> None:
    candidates = mod.candidate_posts(
        [],
        [
            _metric_row(
                day="2026-07-07",
                slot_id="2026-07-07-03-photo",
                instagram_media_id="18154201054431808",
                post_url="",
                posted_lane="rooftop sunset",
            )
        ],
        days_back=365,
        max_posts=10,
    )

    assert len(candidates) == 1
    assert candidates[0]["slot_id"] == "2026-07-07-03-photo"
    assert candidates[0]["_post_id"] == "18154201054431808"
    assert candidates[0]["lane"] == "rooftop sunset"


def test_manual_log_only_post_without_metrics_row_remains_discovered() -> None:
    candidates = mod.candidate_posts(
        [_manual_row(day="2026-07-11", slot_id="manual-only", notes="post_id:LEGACY123")],
        [],
        days_back=365,
        max_posts=10,
    )

    assert len(candidates) == 1
    assert candidates[0]["slot_id"] == "manual-only"
    assert candidates[0]["_post_id"] == "LEGACY123"


def test_same_post_present_in_both_sources_produces_exactly_one_candidate() -> None:
    day = "2026-07-11"
    slot_id = "shared-post"
    candidates = mod.candidate_posts(
        [_manual_row(day=day, slot_id=slot_id, notes="post_id:STALE")],
        [_metric_row(day=day, slot_id=slot_id, instagram_media_id="FRESH789", post_url="https://real.example/1")],
        days_back=365,
        max_posts=10,
    )

    assert len(candidates) == 1
    assert candidates[0]["_post_id"] == "FRESH789"
    assert candidates[0]["posted_at"] == "2026-07-11T10:00:00"


def test_deduplication_uses_stable_date_slot_platform_identity() -> None:
    metric_rows = [
        _metric_row(day="2026-07-11", slot_id="dup-slot", platform="Instagram Feed", instagram_media_id="ID1"),
        _metric_row(day="2026-07-11", slot_id="dup-slot", platform="Instagram Story", instagram_media_id="ID2"),
    ]

    candidates = mod.candidate_posts([], metric_rows, days_back=365, max_posts=10)

    assert len(candidates) == 2
    assert {(row["date"], row["slot_id"], row["platform"]) for row in candidates} == {
        ("2026-07-11", "dup-slot", "Instagram Feed"),
        ("2026-07-11", "dup-slot", "Instagram Story"),
    }


def test_days_back_applies_across_union() -> None:
    today = date.today()
    recent = today.isoformat()
    stale = (today - timedelta(days=30)).isoformat()

    candidates = mod.candidate_posts(
        [_manual_row(day=recent, slot_id="recent-manual", notes="post_id:RECENT")],
        [_metric_row(day=stale, slot_id="stale-metric", instagram_media_id="STALE1")],
        days_back=7,
        max_posts=10,
    )

    assert [row["slot_id"] for row in candidates] == ["recent-manual"]


def test_max_posts_applies_across_union() -> None:
    candidates = mod.candidate_posts(
        [
            _manual_row(day="2026-07-09", slot_id="manual-1", posted_at="2026-07-09T10:00:00", notes="post_id:M1"),
            _manual_row(day="2026-07-10", slot_id="manual-2", posted_at="2026-07-10T10:00:00", notes="post_id:M2"),
        ],
        [_metric_row(day="2026-07-11", slot_id="metric-1", instagram_media_id="MID1")],
        days_back=365,
        max_posts=2,
    )

    assert [row["slot_id"] for row in candidates] == ["metric-1", "manual-2"]


def test_metrics_placeholder_row_without_usable_real_identity_is_not_actionable() -> None:
    candidates = mod.candidate_posts(
        [],
        [_metric_row(day="2026-07-11", slot_id="placeholder", instagram_media_id="", post_url="https://placeholder.example/p/1")],
        days_back=365,
        max_posts=10,
    )

    assert candidates == []


def test_legacy_manual_notes_fallback_remains_preserved() -> None:
    candidates = mod.candidate_posts(
        [_manual_row(day="2026-07-11", slot_id="legacy-manual", notes="post_id:18139386292538988")],
        [],
        days_back=365,
        max_posts=10,
    )

    assert len(candidates) == 1
    assert candidates[0]["_post_id"] == "18139386292538988"


def test_no_recipe_id_or_strategy_dependency_is_introduced() -> None:
    candidate = mod.build_metrics_candidate_row(
        _metric_row(day="2026-07-11", slot_id="metrics-only", instagram_media_id="MID2", posted_lane="coffee")
    )

    assert "recipe_id" not in candidate
    assert candidate["_post_id"] == "MID2"
