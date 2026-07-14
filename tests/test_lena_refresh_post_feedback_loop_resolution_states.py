from __future__ import annotations

import tools.lena_refresh_post_feedback_loop_v1 as mod


def _item(
    date: str,
    slot_id: str,
    platform: str,
    *,
    state: str,
    stale: bool = False,
    reason: str = "",
) -> dict:
    return {
        "date": date,
        "slot_id": slot_id,
        "platform": platform,
        "metrics_resolution_state": state,
        "is_stale": stale,
        "metrics_resolution_reason": reason,
        "recommended_action": {
            "resolved": "no_metrics_resolution_action",
            "manual_only_unverified": "manual_identity_or_metric_update_required",
            "pending_never_refreshed": "request_supported_meta_refresh",
            "pending_refreshable": "request_supported_meta_refresh",
            "pending_unsupported": "manual_or_future_capability_resolution_required",
            "refresh_failed": "retry_or_escalate_refresh",
        }[state],
        "classification": "pending" if state != "resolved" else "weak",
    }


def test_build_recommended_actions_maps_each_state_to_a_distinct_action() -> None:
    outcome = {
        "metrics_resolution_posts": [
            _item("2026-06-12", "manual", "TikTok", state="manual_only_unverified", stale=True),
            _item("2026-07-09", "never", "Instagram Reels", state="pending_never_refreshed", stale=False),
            _item("2026-07-09", "refresh", "Instagram Feed", state="pending_refreshable", stale=True),
            _item("2026-07-09", "unsupported", "Instagram Feed", state="pending_unsupported", stale=True),
            _item("2026-07-09", "failed", "Instagram Feed", state="refresh_failed", stale=False),
            _item("2026-07-11", "resolved", "Instagram Feed", state="resolved", stale=False),
        ],
        "stale_pending_metrics_posts": [
            _item("2026-06-12", "manual", "TikTok", state="manual_only_unverified", stale=True),
            _item("2026-07-09", "refresh", "Instagram Feed", state="pending_refreshable", stale=True),
            _item("2026-07-09", "unsupported", "Instagram Feed", state="pending_unsupported", stale=True),
        ],
        "queue_boosts": {"preferred_recipe_ids": []},
        "winner_posts": [],
    }

    actions = mod.build_metrics_resolution_actions(outcome)
    action_labels = [item["action"] for item in actions]

    assert "manual_identity_or_metric_update_required" in action_labels
    assert action_labels.count("request_supported_meta_refresh") == 2
    assert "manual_or_future_capability_resolution_required" in action_labels
    assert "retry_or_escalate_refresh" in action_labels
    assert "no_metrics_resolution_action" not in action_labels


def test_build_recommended_actions_does_not_request_identical_refresh_for_unsupported_rows() -> None:
    outcome = {
        "metrics_resolution_posts": [
            _item("2026-07-09", "unsupported", "Instagram Feed", state="pending_unsupported", stale=True),
        ],
        "stale_pending_metrics_posts": [
            _item("2026-07-09", "unsupported", "Instagram Feed", state="pending_unsupported", stale=True),
        ],
        "queue_boosts": {"preferred_recipe_ids": []},
        "winner_posts": [],
    }

    actions = mod.build_recommended_actions({}, outcome, {"queue_recipe_ids": []}, {"signals_to_followups": {}}, {"freshness_windows": {"followup_days": 3}})
    labels = [item["action"] for item in actions]

    assert "manual_or_future_capability_resolution_required" in labels
    assert "request_supported_meta_refresh" not in labels


def test_learning_status_distinguishes_current_incomplete_and_stale_unresolved() -> None:
    current = {"metrics_resolution_posts": [_item("2026-07-11", "resolved", "Instagram Feed", state="resolved")]}
    incomplete = {"metrics_resolution_posts": [_item("2026-07-11", "never", "Instagram Feed", state="pending_never_refreshed")]}
    stale = {"metrics_resolution_posts": [_item("2026-07-09", "unsupported", "Instagram Feed", state="pending_unsupported", stale=True)]}

    assert mod.learning_status_from_outcome(current) == "current"
    assert mod.learning_status_from_outcome(incomplete) == "usable_but_incomplete"
    assert mod.learning_status_from_outcome(stale) == "stale_unresolved"
