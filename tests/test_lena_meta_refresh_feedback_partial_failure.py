from __future__ import annotations

import tools.lena_meta_refresh_feedback_v1 as mod


def _existing_row() -> dict:
    return {
        "date": "2026-07-11",
        "slot_id": "slot-01",
        "platform": "Instagram Feed",
        "media_type": "photo",
        "growth_bucket": "engagement",
        "lane": "coffee",
        "hook_category": "hook",
        "post_url": "https://example.com/p/1",
        "audio_name": "",
        "reach": "2400",
        "likes": "80",
        "saves": "17",
        "shares": "8",
        "comments": "12",
        "follows": "0",
        "profile_visits": "0",
        "completion_rate": "0.0",
        "replay_rate": "0.0",
        "score": "0",
        "classification": "pending",
        "notes": "",
    }


def _new_row() -> dict:
    return {
        "date": "2026-07-11",
        "slot_id": "slot-new",
        "platform": "Instagram Feed",
        "media_type": "photo",
        "growth_bucket": "",
        "lane": "",
        "hook_category": "",
        "post_url": "",
        "audio_name": "",
        "notes": "",
    }


def test_existing_nonzero_metric_survives_fetch_failure() -> None:
    row = _existing_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_success(2600),
            "likes": mod.metric_success(81),
            "saves": mod.metric_failure("error"),
            "shares": mod.metric_success(10),
            "comments": mod.metric_success(13),
            "profile_visits": mod.metric_failure("unsupported"),
            "completion_rate": mod.metric_failure("unsupported"),
            "replay_rate": mod.metric_failure("unsupported"),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=False)

    assert merged["reach"] == "2600"
    assert merged["saves"] == "17"
    assert merged["shares"] == "10"


def test_confirmed_real_zero_writes_as_zero() -> None:
    row = _existing_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_success(0),
            "likes": mod.metric_success(0),
            "saves": mod.metric_success(0),
            "shares": mod.metric_success(0),
            "comments": mod.metric_success(0),
            "profile_visits": mod.metric_success(0),
            "completion_rate": mod.metric_success(0),
            "replay_rate": mod.metric_success(0),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=False)

    assert merged["reach"] == "0"
    assert merged["saves"] == "0"
    assert merged["shares"] == "0"
    assert merged["completion_rate"] == "0.0"


def test_successful_nonzero_fetch_updates_normally() -> None:
    row = _existing_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_success(3000),
            "likes": mod.metric_success(95),
            "saves": mod.metric_success(20),
            "shares": mod.metric_success(11),
            "comments": mod.metric_success(14),
            "profile_visits": mod.metric_success(1),
            "completion_rate": mod.metric_success(0),
            "replay_rate": mod.metric_success(0),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=False)

    assert merged["reach"] == "3000"
    assert merged["likes"] == "95"
    assert merged["saves"] == "20"
    assert merged["shares"] == "11"


def test_mixed_success_failure_updates_successful_fields_only() -> None:
    row = _existing_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_success(2600),
            "likes": mod.metric_success(85),
            "saves": mod.metric_failure("error"),
            "shares": mod.metric_success(10),
            "comments": mod.metric_success(13),
            "profile_visits": mod.metric_failure("unsupported"),
            "completion_rate": mod.metric_failure("unsupported"),
            "replay_rate": mod.metric_failure("unsupported"),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=False)

    assert merged["reach"] == "2600"
    assert merged["likes"] == "85"
    assert merged["saves"] == "17"
    assert merged["shares"] == "10"
    assert merged["comments"] == "13"


def test_instagram_path_preserves_failed_insights(monkeypatch) -> None:
    def fake_graph_get(path: str, params: dict, cfg: dict, token_override=None, platform: str = "") -> dict:
        metric = params.get("metric")
        if path == "/ig-post-1":
            return {"id": "ig-post-1", "permalink": "https://example.com/p/ig", "like_count": 9, "comments_count": 4}
        if metric == "reach":
            raise RuntimeError("reach unavailable")
        if metric == "saved":
            return {"data": [{"name": "saved", "values": [{"value": 0}]}]}
        if metric == "shares":
            return {"data": [{"name": "shares", "values": [{"value": 5}]}]}
        if metric == "views":
            return {"data": [{"name": "views", "values": [{"value": 100}]}]}
        if metric == "total_interactions":
            return {"data": [{"name": "total_interactions", "values": [{"value": 22}]}]}
        raise AssertionError(f"unexpected call: {path} {params}")

    monkeypatch.setattr(mod, "graph_get", fake_graph_get)

    fetched = mod.fetch_instagram_metrics(
        "ig-post-1",
        {"auth_mode": "instagram_login"},
        {
            "base_fields": "id,permalink,like_count,comments_count",
            "insight_metrics": ["reach", "views", "saved", "shares", "total_interactions"],
        },
    )

    assert fetched["metric_results"]["likes"] == mod.metric_success(9)
    assert fetched["metric_results"]["comments"] == mod.metric_success(4)
    assert fetched["metric_results"]["reach"]["ok"] is False
    assert fetched["metric_results"]["saves"] == mod.metric_success(0)
    assert fetched["metric_results"]["shares"] == mod.metric_success(5)


def test_facebook_path_preserves_failed_insights(monkeypatch) -> None:
    def fake_graph_get(path: str, params: dict, cfg: dict, token_override=None, platform: str = "") -> dict:
        metric = params.get("metric")
        if path == "/fb-post-1":
            return {
                "permalink_url": "https://facebook.example/p/1",
                "reactions": {"summary": {"total_count": 7}},
                "comments": {"summary": {"total_count": 3}},
                "shares": {"count": 2},
            }
        if metric == "post_impressions_unique":
            raise RuntimeError("unique unavailable")
        if metric == "post_impressions":
            return {"data": [{"name": "post_impressions", "values": [{"value": 0}]}]}
        if metric == "post_engaged_users":
            return {"data": [{"name": "post_engaged_users", "values": [{"value": 11}]}]}
        raise AssertionError(f"unexpected call: {path} {params}")

    monkeypatch.setattr(mod, "graph_get", fake_graph_get)

    fetched = mod.fetch_facebook_metrics(
        "fb-post-1",
        {},
        {
            "base_fields": "id,permalink_url,reactions.summary(true).limit(0),comments.summary(true).limit(0),shares",
            "insight_metrics": ["post_impressions_unique", "post_impressions", "post_engaged_users"],
        },
    )

    assert fetched["metric_results"]["likes"] == mod.metric_success(7)
    assert fetched["metric_results"]["comments"] == mod.metric_success(3)
    assert fetched["metric_results"]["shares"] == mod.metric_success(2)
    assert fetched["metric_results"]["reach"] == mod.metric_success(0)


def test_new_row_leaves_failed_metric_blank_not_zero() -> None:
    row = _new_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_failure("error"),
            "likes": mod.metric_success(4),
            "saves": mod.metric_failure("error"),
            "shares": mod.metric_success(0),
            "comments": mod.metric_success(1),
            "profile_visits": mod.metric_failure("unsupported"),
            "completion_rate": mod.metric_failure("unsupported"),
            "replay_rate": mod.metric_failure("unsupported"),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=True)

    assert merged["reach"] == ""
    assert merged["saves"] == ""
    assert merged["shares"] == "0"


def test_new_row_remains_pending_when_scoring_required_metric_unknown() -> None:
    row = _new_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_failure("error"),
            "likes": mod.metric_success(4),
            "saves": mod.metric_success(1),
            "shares": mod.metric_success(0),
            "comments": mod.metric_success(1),
            "profile_visits": mod.metric_failure("unsupported"),
            "completion_rate": mod.metric_failure("unsupported"),
            "replay_rate": mod.metric_failure("unsupported"),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=True)

    assert merged["score"] == ""
    assert merged["classification"] == "pending"


def test_existing_row_score_uses_protected_merged_row() -> None:
    row = _existing_row()
    fetched = {
        "metric_results": {
            "reach": mod.metric_success(2600),
            "likes": mod.metric_success(85),
            "saves": mod.metric_failure("error"),
            "shares": mod.metric_success(10),
            "comments": mod.metric_success(13),
            "profile_visits": mod.metric_failure("unsupported"),
            "completion_rate": mod.metric_failure("unsupported"),
            "replay_rate": mod.metric_failure("unsupported"),
        }
    }

    merged = mod.apply_fetched_metrics(dict(row), fetched, is_new_row=False)
    expected = dict(row)
    expected["reach"] = "2600"
    expected["likes"] = "85"
    expected["saves"] = "17"
    expected["shares"] = "10"
    expected["comments"] = "13"
    expected_score, expected_classification = mod.score_row(expected)

    assert merged["score"] == expected_score
    assert merged["classification"] == expected_classification
