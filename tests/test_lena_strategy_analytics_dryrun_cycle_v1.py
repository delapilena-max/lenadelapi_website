from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.lena_strategy_analytics_dryrun_cycle_v1 as cycle


DATE = "2026-07-18"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def test_dry_run_cycle_runs_strategy_then_analytics_and_records_safeguards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_root = tmp_path / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"
    monkeypatch.setattr(cycle, "REPORTS", reports_root)
    monkeypatch.setattr(cycle, "now_ts", lambda: "010203")

    strategy_report_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_strategy_autonomy_run_{DATE}.json"
    _write_json(
        strategy_report_path,
        {
            "ok": True,
            "summary": {
                "recommended_recipe_id": "hcr_011",
                "queue_recipes": ["hcr_011", "hcr_005"],
                "broader_autonomous_generation_ready": False,
                "strategy_gate_blocked": True,
            },
        },
    )

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:
        calls.append((label, cmd))
        if label == "strategy_autonomy_run_dry_run":
            return {
                "label": label,
                "cmd": cmd,
                "cmd_text": " ".join(cmd),
                "returncode": 0,
                "ok": True,
                "stdout": json.dumps({"report_path": str(strategy_report_path)}),
                "stderr": "",
            }
        assert label == "analytics_intake_sync_dry_run"
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": " ".join(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "metrics_csv": str(tmp_path / "pipeline" / "analytics" / "lena_post_metrics_v1_6_1.csv"),
                    "receipts_scanned": 3,
                    "created": 1,
                    "updated": 2,
                    "synced": [],
                }
            ),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["cycle", "--date", DATE, "--queue-limit", "4", "--recipes", "hcr_011,hcr_005"])

    assert cycle.main() == 0

    assert [label for label, _cmd in calls] == [
        "strategy_autonomy_run_dry_run",
        "analytics_intake_sync_dry_run",
    ]
    strategy_cmd = calls[0][1]
    assert strategy_cmd[:2] == [cycle.PY, str(cycle.STRATEGY_RUNNER)]
    assert strategy_cmd[2:] == ["--date", DATE, "--queue-limit", "4", "--recipes", "hcr_011,hcr_005"]

    analytics_cmd = calls[1][1]
    assert analytics_cmd == [cycle.PY, str(cycle.ANALYTICS_SYNC)]
    assert "--apply" not in analytics_cmd
    assert "publish" not in " ".join(analytics_cmd).lower()
    assert "provider" not in " ".join(analytics_cmd).lower()

    report_path = reports_root / DATE / "lena_strategy_analytics_dry_run_cycle_2026-07-18_010203.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["assumptions"]["strategy_runner"] == "invokes the existing strategy runner and does not audit its internals"
    assert report["dry_run_command"].endswith("--date 2026-07-18 --queue-limit 4 --recipes hcr_011,hcr_005")
    assert report["safeguards"] == {
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "retry_cap": 0,
        "hard_spend_cap_usd": 0,
        "duplicate_rejection": "report_path_must_not_exist",
        "kill_switch": "no_live_command_paths",
        "qa_fail_closed": True,
        "fail_closed_stage_handling": True,
        "recurring_scheduler": False,
        "receipt_creation": "wrapper_report_json",
    }
    assert report["autonomous_stages"] == cycle.AUTONOMOUS_STAGES
    assert report["manual_stages"] == cycle.MANUAL_STAGES
    assert report["out_of_scope"] == [
        "provider_generation",
        "image_qa",
        "caption_package_completion",
        "publishing",
        "publish_receipt",
        "live_analytics_refresh",
        "recurring_scheduler",
    ]
    assert [item["stage"] for item in report["stage_coverage"]] == [
        "strategy_preparation",
        "analytics_intake_sync",
    ]
    assert report["stage_coverage"][0]["provider_free"] is True
    assert report["stage_coverage"][1]["apply_flag"] is False
    assert report["strategy_summary"]["recommended_recipe_id"] == "hcr_011"
    assert report["analytics_summary"]["receipts_scanned"] == 3


def test_path_traversal_date_is_rejected_before_any_stage_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_root = tmp_path / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"
    monkeypatch.setattr(cycle, "REPORTS", reports_root)
    monkeypatch.setattr(cycle, "now_ts", lambda: "010203")

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:  # pragma: no cover - defensive
        calls.append((label, cmd))
        raise AssertionError("no stages should run after invalid date validation")

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["cycle", "--date", "../../2026-07-18"])

    with pytest.raises(SystemExit, match="invalid --date value"):
        cycle.main()

    assert calls == []


def test_analytics_failure_is_recorded_truthfully_and_stops_later_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_root = tmp_path / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"
    monkeypatch.setattr(cycle, "REPORTS", reports_root)
    monkeypatch.setattr(cycle, "now_ts", lambda: "040506")

    strategy_report_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_strategy_autonomy_run_{DATE}.json"
    _write_json(strategy_report_path, {"ok": True, "summary": {"recommended_recipe_id": "hcr_011"}})

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:
        calls.append((label, cmd))
        if label == "strategy_autonomy_run_dry_run":
            return {
                "label": label,
                "cmd": cmd,
                "cmd_text": " ".join(cmd),
                "returncode": 0,
                "ok": True,
                "stdout": json.dumps({"report_path": str(strategy_report_path)}),
                "stderr": "",
            }
        assert label == "analytics_intake_sync_dry_run"
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": " ".join(cmd),
            "returncode": 3,
            "ok": False,
            "stdout": "",
            "stderr": "analytics intake failed truthfully",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["cycle", "--date", DATE])

    assert cycle.main() == 1

    assert [label for label, _cmd in calls] == [
        "strategy_autonomy_run_dry_run",
        "analytics_intake_sync_dry_run",
    ]
    report_path = reports_root / DATE / "lena_strategy_analytics_dry_run_cycle_2026-07-18_040506.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "analytics_intake_sync_dry_run"
    assert len(report["stages"]) == 2
    assert report["stages"][0]["label"] == "strategy_autonomy_run_dry_run"
    assert report["stages"][1]["label"] == "analytics_intake_sync_dry_run"
    assert report["stages"][1]["returncode"] == 3
    assert report["strategy_summary"]["recommended_recipe_id"] == "hcr_011"
    assert report["safeguards"]["fail_closed_stage_handling"] is True
    assert report["safeguards"]["kill_switch"] == "no_live_command_paths"


def test_duplicate_report_path_fails_closed_before_running_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_root = tmp_path / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"
    monkeypatch.setattr(cycle, "REPORTS", reports_root)
    monkeypatch.setattr(cycle, "now_ts", lambda: "010203")

    existing = reports_root / DATE / "lena_strategy_analytics_dry_run_cycle_2026-07-18_010203.json"
    _write_json(existing, {"existing": True})

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:  # pragma: no cover - defensive
        calls.append((label, cmd))
        return {"label": label, "cmd": cmd, "returncode": 0, "ok": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["cycle", "--date", DATE])

    with pytest.raises(FileExistsError):
        cycle.main()

    assert calls == []


def test_child_failure_produces_failed_receipt_and_stops_before_analytics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_root = tmp_path / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"
    monkeypatch.setattr(cycle, "REPORTS", reports_root)
    monkeypatch.setattr(cycle, "now_ts", lambda: "090909")

    calls: list[tuple[str, list[str]]] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict:
        calls.append((label, cmd))
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": " ".join(cmd),
            "returncode": 7,
            "ok": False,
            "stdout": "",
            "stderr": "strategy step failed truthfully",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["cycle", "--date", DATE])

    assert cycle.main() == 1

    assert [label for label, _cmd in calls] == ["strategy_autonomy_run_dry_run"]
    report_path = reports_root / DATE / "lena_strategy_analytics_dry_run_cycle_2026-07-18_090909.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "strategy_autonomy_run_dry_run"
    assert report["safeguards"]["provider_calls_performed"] == 0
    assert report["safeguards"]["publish_calls_performed"] == 0
    assert report["safeguards"]["kill_switch"] == "no_live_command_paths"
    assert report["safeguards"]["fail_closed_stage_handling"] is True
