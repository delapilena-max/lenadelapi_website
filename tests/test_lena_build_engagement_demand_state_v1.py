from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import tools.strategy.lena_build_engagement_demand_state_v1 as engagement


DATE = "2026-07-14"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [",".join(headers)] + [",".join(row) for row in rows]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def _policy(signals_path: str, state_path: str) -> dict:
    return {
        "signals_path": signals_path,
        "state_path": state_path,
        "minimum_signal_count_to_activate": 2,
        "max_signal_count_per_class_for_scoring": 3,
        "default_primary_boost": 10,
        "default_secondary_boost": 4,
        "signal_class_map": {
            "routine_request": {
                "preferred_recipe_ids": ["hcr_004"],
                "secondary_recipe_ids": ["hcr_007"],
                "notes": "routine note",
            },
            "outfit_request": {
                "preferred_recipe_ids": ["hcr_002"],
                "secondary_recipe_ids": ["hcr_008"],
                "notes": "outfit note",
            },
            "unknown_ignored": {
                "preferred_recipe_ids": ["hcr_999"],
                "secondary_recipe_ids": [],
                "notes": "ignored",
            },
        },
    }


def test_build_boosts_applies_minimums_caps_and_world_state_adjustments() -> None:
    policy = _policy("signals.csv", "state.json")
    world_state = {
        "continuity_snapshot": {
            "recent_counts": {
                "public_or_fitness_share": 0.2,
                "home_share": 0.6,
            }
        }
    }
    rows = [
        {"signal_class": "routine_request"},
        {"signal_class": "routine_request"},
        {"signal_class": "routine_request"},
        {"signal_class": "routine_request"},
        {"signal_class": "outfit_request"},
        {"signal_class": "outfit_request"},
        {"signal_class": "single_ignored"},
    ]

    boosts, reasons, active = engagement.build_boosts(policy, world_state, rows)

    assert active == ["outfit_request", "routine_request"]
    assert boosts["hcr_004"] == 36  # capped at 3 -> 30 + 6 home-overuse bump
    assert boosts["hcr_007"] == 12
    assert boosts["hcr_002"] == 24  # 20 + 4 public-needed bump
    assert boosts["hcr_008"] == 10  # 8 + 2 public-needed bump
    assert reasons["hcr_004"] == ["engagement demand: routine_request x4"]
    assert reasons["hcr_002"] == ["engagement demand: outfit_request x2"]
    assert "hcr_999" not in boosts


def test_latest_world_state_prefers_exact_date_then_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engagement, "NEXT_ACTIONS", tmp_path / "next_actions")
    dated = engagement.NEXT_ACTIONS / DATE / f"lena_world_state_{DATE}.json"
    fallback = engagement.NEXT_ACTIONS / "2026-07-13" / "lena_world_state_2026-07-13.json"
    _write_json(fallback, {"report_type": "fallback"})
    _write_json(dated, {"report_type": "dated"})

    assert engagement.latest_world_state(DATE)["report_type"] == "dated"
    dated.unlink()
    assert engagement.latest_world_state(DATE)["report_type"] == "fallback"


def test_canonical_state_payload_is_stable() -> None:
    payload = engagement.canonical_state(
        {
            "generated_at": "2026-07-14T12:00:00+00:00",
            "date": DATE,
            "signal_count": 3,
            "active_signal_classes": ["outfit_request"],
            "queue_boosts": {
                "boost_by_recipe_id": {"hcr_002": 24},
                "preferred_recipe_ids": ["hcr_002"],
            },
        },
        Path("pipeline/state/lena_engagement_demand_state_v1.json"),
    )
    assert payload == {
        "version": "v1",
        "updated_at": "2026-07-14T12:00:00+00:00",
        "date": DATE,
        "signal_count": 3,
        "active_signal_classes": ["outfit_request"],
        "boost_by_recipe_id": {"hcr_002": 24},
        "preferred_recipe_ids": ["hcr_002"],
        "state_path": "pipeline/state/lena_engagement_demand_state_v1.json",
    }


def test_main_writes_report_and_safe_flags_without_mutating_queues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    next_actions = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions"
    policy_path = tmp_path / "pipeline" / "influencer_nodes" / "lena" / "policy.json"
    signals_path = tmp_path / "pipeline" / "analytics" / "signals.csv"
    state_path = "pipeline/state/lena_engagement_demand_state_v1.json"
    world_state_path = next_actions / DATE / f"lena_world_state_{DATE}.json"

    _write_json(policy_path, _policy("pipeline/analytics/signals.csv", state_path))
    _write_json(
        world_state_path,
        {
            "artifacts": {"world_state_report": str(world_state_path)},
            "continuity_snapshot": {"recent_counts": {"public_or_fitness_share": 0.2, "home_share": 0.4}},
        },
    )
    _write_csv(
        signals_path,
        ["signal_class"],
        [["outfit_request"], ["outfit_request"], ["routine_request"], ["routine_request"]],
    )

    monkeypatch.setattr(engagement, "ROOT", tmp_path)
    monkeypatch.setattr(engagement, "NEXT_ACTIONS", next_actions)
    monkeypatch.setattr(engagement, "POLICY_PATH", policy_path)
    monkeypatch.setattr(
        engagement,
        "datetime",
        type("FakeDateTime", (), {"now": staticmethod(lambda tz=None: datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc if tz else None))}),
    )
    monkeypatch.setattr(sys, "argv", ["engagement", "--date", DATE])

    assert engagement.main() == 0

    report_path = next_actions / DATE / f"lena_engagement_demand_state_{DATE}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_type"] == "lena_engagement_demand_state"
    assert report["version"] == "v1"
    assert report["active_signal_classes"] == ["outfit_request", "routine_request"]
    assert report["queue_boosts"]["preferred_recipe_ids"][0] == "hcr_002"
    assert report["safe_operations"] == {
        "api_call_made": False,
        "generation_call_performed": False,
        "upload_performed": False,
        "queue_mutated": False,
        "publish_performed": False,
        "credentials_read": False,
    }
    canonical_path = tmp_path / state_path
    assert json.loads(canonical_path.read_text(encoding="utf-8"))["state_path"] == state_path
    assert not (tmp_path / "pipeline" / "queue").exists()
