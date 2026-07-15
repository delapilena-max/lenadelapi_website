from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.lena_strategy_autonomy_run_v1 as runner


DATE = "2026-07-14"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def test_default_invocation_runs_only_strategy_prep_and_records_truthful_safe_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(runner, "now_ts", lambda: "010203")
    monkeypatch.setattr(runner, "datetime", type("FakeDateTime", (), {"now": staticmethod(lambda: __import__("datetime").datetime(2026, 7, 14, 1, 2, 3))}))

    prep_report_path = runner.NEXT_ACTIONS / DATE / f"lena_strategy_autonomy_prep_{DATE}.json"
    _write_json(
        prep_report_path,
        {
            "summary": {
                "recommended_recipe_id": "hcr_011",
                "queue_recipes": ["hcr_011", "hcr_005"],
                "next_live_image_handoff_path": "pipeline/strategy/lena/next_actions/2026-07-14/lena_next_live_image_handoff_2026-07-14.json",
                "next_live_image_handoff_markdown_path": "pipeline/strategy/lena/next_actions/2026-07-14/lena_next_live_image_handoff_2026-07-14.md",
                "strategy_gate_blocked": True,
                "strategy_gate_reasons": ["quarantined_surface"],
                "video_payload_count": 0,
                "video_seed_available_count": 0,
                "video_transport_ready_count": 0,
                "video_live_ready_count": 0,
                "continuity_alert_count": 0,
                "preferred_rotation_recipe_ids": [],
                "deprioritized_rotation_recipe_ids": [],
                "active_engagement_signal_classes": [],
                "engagement_preferred_recipe_ids": [],
                "winner_post_count": 0,
                "pending_metrics_count": 0,
                "post_outcome_preferred_recipe_ids": [],
                "broader_autonomous_generation_ready": False,
            }
        },
    )

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:
        calls.append((label, cmd))
        assert ".env" not in " ".join(cmd)
        return {
            "label": label,
            "cmd": cmd,
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"report_path": str(prep_report_path)}),
            "stderr": "",
        }

    monkeypatch.setattr(runner, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["runner", "--date", DATE, "--queue-limit", "6"])

    assert runner.main() == 0

    assert [label for label, _cmd in calls] == ["strategy_autonomy_prep"]
    prep_cmd = calls[0][1]
    assert prep_cmd[:2] == [runner.PY, str(runner.RUNNER)]
    assert prep_cmd[-4:] == ["--date", DATE, "--queue-limit", "6"]
    assert "--refresh-meta-feedback" not in prep_cmd
    assert "meta_refresh" not in " ".join(prep_cmd).lower()

    report_path = runner.NEXT_ACTIONS / DATE / "lena_strategy_autonomy_run_010203.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["version"] == "v1"
    assert report["date"] == DATE
    assert report["args"]["refresh_meta_feedback"] is False
    assert report["args"]["queue_limit"] == 6
    assert report["steps"] == [
        {
            "label": "strategy_autonomy_prep",
            "ok": True,
            "returncode": 0,
            "cmd": prep_cmd,
        }
    ]
    assert report["strategy_prep_report"] == str(prep_report_path)
    assert report["summary"]["strategy_gate_blocked"] is True
    assert report["next_live_image_handoff_report"].endswith(".json")
    assert "meta_feedback_summary" not in report
    assert "queue promotion" not in json.dumps(report).lower()
    assert "publish" not in json.dumps(report["summary"]).lower()


def test_meta_refresh_runs_only_with_explicit_flag_and_passes_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(runner, "now_ts", lambda: "111111")

    prep_report_path = runner.NEXT_ACTIONS / DATE / f"lena_strategy_autonomy_prep_{DATE}.json"
    _write_json(prep_report_path, {"summary": {}})

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:
        calls.append((label, cmd))
        if label == "meta_feedback_refresh":
            return {
                "label": label,
                "cmd": cmd,
                "returncode": 0,
                "ok": True,
                "stdout": json.dumps(
                    {
                        "report_path": "pipeline/strategy/lena/next_actions/2026-07-14/meta_refresh.json",
                        "metrics_updated": 4,
                        "comments_logged": 9,
                        "candidate_post_count": 3,
                        "changed_dates": [DATE],
                    }
                ),
                "stderr": "",
            }
        return {
            "label": label,
            "cmd": cmd,
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"report_path": str(prep_report_path)}),
            "stderr": "",
        }

    monkeypatch.setattr(runner, "run_step", fake_run_step)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--date",
            DATE,
            "--queue-limit",
            "5",
            "--refresh-meta-feedback",
            "--meta-max-posts",
            "7",
            "--meta-comments-limit",
            "11",
        ],
    )

    assert runner.main() == 0

    assert [label for label, _cmd in calls] == ["meta_feedback_refresh", "strategy_autonomy_prep"]
    refresh_cmd = calls[0][1]
    assert refresh_cmd == [
        runner.PY,
        str(runner.META_REFRESH),
        "--max-posts",
        "7",
        "--comments-limit",
        "11",
        "--queue-limit",
        "5",
    ]

    report = json.loads((runner.NEXT_ACTIONS / DATE / "lena_strategy_autonomy_run_111111.json").read_text(encoding="utf-8"))
    assert report["meta_feedback_summary"] == {
        "ok": True,
        "report_path": "pipeline/strategy/lena/next_actions/2026-07-14/meta_refresh.json",
        "metrics_updated": 4,
        "comments_logged": 9,
        "candidate_post_count": 3,
        "changed_dates": [DATE],
    }


def test_child_failure_propagates_truthfully_and_preserves_report_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "NEXT_ACTIONS", tmp_path / "pipeline" / "strategy" / "lena" / "next_actions")
    monkeypatch.setattr(runner, "now_ts", lambda: "222222")

    def fake_run_step(label: str, cmd: list[str]) -> dict:
        return {
            "label": label,
            "cmd": cmd,
            "returncode": 9,
            "ok": False,
            "stdout": "",
            "stderr": "prep failed truthfully",
        }

    monkeypatch.setattr(runner, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["runner", "--date", DATE, "--recipes", "hcr_011,hcr_005", "--queue-limit", "4"])

    assert runner.main() == 1

    report = json.loads((runner.NEXT_ACTIONS / DATE / "lena_strategy_autonomy_run_222222.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["args"]["recipes"] == "hcr_011,hcr_005"
    assert report["steps"][0]["returncode"] == 9
    assert "stdout" not in report
    assert report["stderr"] == "prep failed truthfully"
