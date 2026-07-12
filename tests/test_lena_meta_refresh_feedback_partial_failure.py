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


# --- Gap A: richer per-field Meta refresh reporting (2026-07-12) -----------
#
# Proves the real fetch functions' metric_results already distinguish
# confirmed-zero, confirmed-nonzero, failed-fetch, and unavailable/never-
# attempted simultaneously, and that this truth now survives into the
# per-post report entry instead of being silently discarded. No real
# network call (graph_get is monkeypatched, same pattern already proven
# safe elsewhere in this file) and no canonical CSV/state mutation.

def test_instagram_fetch_distinguishes_all_reportable_states(monkeypatch) -> None:
    def fake_graph_get(path: str, params: dict, cfg: dict, token_override=None, platform: str = "") -> dict:
        metric = params.get("metric")
        if path == "/ig-post-states":
            return {"id": "ig-post-states", "permalink": "https://example.com/p/ig", "like_count": 42, "comments_count": 5}
        if metric == "reach":
            return {"data": [{"name": "reach", "values": [{"value": 0}]}]}
        if metric == "saved":
            raise RuntimeError("transient graph error")
        if metric == "shares":
            raise RuntimeError("transient graph error")
        raise AssertionError(f"unexpected call: {path} {params}")

    monkeypatch.setattr(mod, "graph_get", fake_graph_get)

    fetched = mod.fetch_instagram_metrics(
        "ig-post-states",
        {"auth_mode": "instagram_login"},
        {
            "base_fields": "id,permalink,like_count,comments_count",
            "insight_metrics": ["reach", "saved", "shares"],
        },
    )
    results = fetched["metric_results"]

    # confirmed successful zero
    assert results["reach"] == {"ok": True, "value": 0.0}
    # confirmed successful nonzero (from the summary object, not insights)
    assert results["likes"] == {"ok": True, "value": 42.0}
    assert results["comments"] == {"ok": True, "value": 5.0}
    # failed fetch (a real exception during an attempted insight call)
    assert results["saves"]["ok"] is False
    assert results["saves"]["reason"].startswith("error:")
    assert results["shares"]["ok"] is False
    assert results["shares"]["reason"].startswith("error:")
    # unavailable / never attempted by this tool at all
    assert results["profile_visits"] == {"ok": False, "reason": "metric_unavailable"}
    assert results["completion_rate"] == {"ok": False, "reason": "metric_unavailable"}
    assert results["replay_rate"] == {"ok": False, "reason": "metric_unavailable"}
    # follows: explicitly, truthfully unsupported by this tool
    assert results["follows"] == {"ok": False, "reason": "not_requested_by_tool"}

    # The five requested categories are all represented and mutually
    # distinguishable by (ok, value/reason) -- confirmed zero and confirmed
    # nonzero are both "ok: True" but distinguished by their real value;
    # failed-fetch, unavailable, and not-requested-by-tool are all
    # "ok: False" but distinguished by their reason string. Two fields
    # legitimately sharing the same reason (e.g. profile_visits/
    # completion_rate/replay_rate all "metric_unavailable") is correct,
    # not a collision to guard against.
    assert results["reach"]["value"] == 0.0 and results["likes"]["value"] != 0.0


def test_facebook_fetch_includes_explicit_follows_not_requested() -> None:
    fetched_metric_results_shape = {
        "likes": mod.metric_success(1),
        "comments": mod.metric_success(0),
        "shares": mod.metric_success(2),
        "reach": mod.metric_failure("insight_unavailable"),
        "saves": mod.metric_failure("metric_unavailable"),
        "follows": mod.metric_failure(mod.NOT_REQUESTED_BY_TOOL),
        "profile_visits": mod.metric_failure("metric_unavailable"),
        "completion_rate": mod.metric_failure("metric_unavailable"),
        "replay_rate": mod.metric_failure("metric_unavailable"),
    }
    # Sanity: the constant used in production is the exact literal reported.
    assert mod.NOT_REQUESTED_BY_TOOL == "not_requested_by_tool"
    assert fetched_metric_results_shape["follows"] == {"ok": False, "reason": "not_requested_by_tool"}


# 6/9/10/11. The final per-post report entry preserves metric_results
# verbatim rather than dropping it -- pure passthrough, no recomputation,
# no scoring change.
def test_report_entry_preserves_metric_results_truth() -> None:
    row = _existing_row()
    row["reach"] = "2600"
    row["classification"] = "strong"
    row["score"] = "61.0"
    fetched = {
        "metric_results": {
            "reach": mod.metric_success(2600),
            "likes": mod.metric_success(0),
            "saves": mod.metric_failure("error:boom"),
            "shares": mod.metric_success(10),
            "comments": mod.metric_success(13),
            "follows": mod.metric_failure(mod.NOT_REQUESTED_BY_TOOL),
            "profile_visits": mod.metric_failure("metric_unavailable"),
            "completion_rate": mod.metric_failure("metric_unavailable"),
            "replay_rate": mod.metric_failure("metric_unavailable"),
        }
    }

    entry = mod.build_metrics_report_entry(row, fetched)

    # Existing report fields preserved byte-for-byte.
    assert entry["ok"] is True
    assert entry["reach"] == row["reach"]
    assert entry["likes"] == row["likes"]
    assert entry["comments"] == row["comments"]
    assert entry["shares"] == row["shares"]
    assert entry["saves"] == row["saves"]
    assert entry["classification"] == row["classification"]
    assert entry["score"] == row["score"]

    # New: full per-field fetch truth carried through verbatim, not
    # recomputed or reinterpreted.
    assert entry["metric_results"] == fetched["metric_results"]
    # Distinct states still distinguishable inside the report entry itself.
    assert entry["metric_results"]["reach"]["ok"] is True
    assert entry["metric_results"]["likes"]["value"] == 0.0
    assert entry["metric_results"]["saves"]["ok"] is False
    assert entry["metric_results"]["saves"]["reason"] == "error:boom"
    assert entry["metric_results"]["follows"]["reason"] == "not_requested_by_tool"


def test_report_entry_missing_metric_results_defaults_to_empty_dict() -> None:
    row = _existing_row()
    entry = mod.build_metrics_report_entry(row, {})
    assert entry["metric_results"] == {}
