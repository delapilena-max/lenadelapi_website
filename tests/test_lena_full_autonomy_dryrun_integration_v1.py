from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import lena_generation_qa_package_dryrun_v1 as generation_cycle
from tools import lena_full_autonomy_dryrun_integration_v1 as cycle


DATE = "2026-07-18"
REPORT_ROOT = Path("pipeline") / "autonomy" / "lena" / "dry_run_cycles"
STRATEGY_REPORT_ROOT = Path("pipeline") / "strategy" / "lena" / "next_actions"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def _aggregate_report_path(tmp_path: Path, stamp: str = "010203") -> Path:
    return tmp_path / REPORT_ROOT / DATE / f"lena_full_autonomy_dry_run_cycle_{DATE}_{stamp}.json"


def _strategy_report_path(tmp_path: Path, stamp: str = "010203") -> Path:
    return tmp_path / STRATEGY_REPORT_ROOT / DATE / f"lena_strategy_autonomy_run_{stamp}.json"


def _generation_report_path(tmp_path: Path, stamp: str = "010203") -> Path:
    return tmp_path / REPORT_ROOT / DATE / f"lena_generation_qa_package_dry_run_cycle_{DATE}_{stamp}.json"


def _default_args(tmp_path: Path) -> list[str]:
    return [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(tmp_path / "qa.json"),
        "--report-root",
        str(tmp_path / REPORT_ROOT),
        "--generation-report-root",
        str(tmp_path / REPORT_ROOT),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--image-root",
        str(tmp_path / "pipeline" / "higgsfield_library" / "lena"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa"),
        "--packet-root",
        str(tmp_path / "pipeline" / "strategy" / "lena" / "publish_packets"),
    ]


def _strategy_report(*, ok: bool = True) -> dict:
    return {
        "ok": ok,
        "version": "v1",
        "date": DATE,
        "started_at": "2026-07-18T01:02:03",
        "finished_at": "2026-07-18T01:02:04",
        "steps": [
            {
                "label": "strategy_autonomy_prep",
                "ok": ok,
                "returncode": 0 if ok else 7,
                "cmd": ["python", "tools/strategy/lena_run_strategy_autonomy_prep_v1.py", "--date", DATE],
            }
        ],
        "summary": {
            "recommended_recipe_id": "hcr_011",
            "queue_recipes": ["hcr_011", "hcr_005"],
            "broader_autonomous_generation_ready": True,
            "strategy_gate_blocked": False,
        },
    }


def _generation_report(
    *,
    report_path: str,
    ok: bool = True,
    stage_order: list[str] | None = None,
    publishing_authorized: bool = False,
    provider_calls_performed: int = 0,
    publish_calls_performed: int = 0,
    retries_performed: int = 0,
) -> dict:
    stages = stage_order or [
        "approved_candidate_resolution",
        "generation_result_intake",
        "image_qa_validation",
        "caption_package_creation",
    ]
    stage_payloads = {
        "approved_candidate_resolution": {"stage": "approved_candidate_resolution", "status": "pass", "mode": "autonomous"},
        "generation_result_intake": {"stage": "generation_result_intake", "status": "pass", "mode": "autonomous"},
        "image_qa_validation": {"stage": "image_qa_validation", "status": "pass", "mode": "manual_or_fixture_bound"},
        "caption_package_creation": {"stage": "caption_package_creation", "status": "pass", "mode": "autonomous"},
    }
    report = {
        "ok": ok,
        "version": "v1",
        "report_type": "lena_generation_qa_package_dry_run_cycle",
        "date": DATE,
        "started_at": "2026-07-18T01:02:03",
        "finished_at": "2026-07-18T01:02:04",
        "report_path": report_path,
        "publishing_authorized": publishing_authorized,
        "provider_calls_performed": provider_calls_performed,
        "publish_calls_performed": publish_calls_performed,
        "retries_performed": retries_performed,
        "prompt_binding_verified": False,
        "verified_lineage": {
            "approval_artifact_path": "pipeline/approvals/lena/generation/2026-07-18/approval.json",
            "approval_artifact_sha256": "a" * 64,
            "candidate_artifact_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-18/candidate.json",
            "candidate_artifact_sha256_expected": "b" * 64,
            "candidate_artifact_sha256_actual": "b" * 64,
        },
        "asserted_lineage": {
            "prompt_sha256": "c" * 64,
            "authority_commit": "d" * 40,
        },
        "unverified_bindings": ["generation_result_prompt_binding"],
        "approval_artifact": "pipeline/approvals/lena/generation/2026-07-18/approval.json",
        "approval_sha256": "a" * 64,
        "candidate_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-18/candidate.json",
        "candidate_sha256": "b" * 64,
        "candidate_sha256_expected": "b" * 64,
        "candidate_id": "candidate-1",
        "slot_id": "slot-1",
        "prompt_sha256": "c" * 64,
        "manifest_path": "pipeline/higgsfield_debug/2026-07-18/slot-1/lena_hpe_output_qa_manifest.json",
        "manifest_sha256": "e" * 64,
        "image_path": "pipeline/higgsfield_library/lena/2026-07-18/slot-1_seed.png",
        "image_sha256": "f" * 64,
        "qa_artifact": "pipeline/asset_review/lena/hpe_closure/presence_output_qa/2026-07-18/slot-1/presence_qa_slot-1_00.json",
        "qa_artifact_sha256": "1" * 64,
        "packet_path": "pipeline/strategy/lena/publish_packets/2026-07-18/lena_content_packet_dryrun_2026-07-18_hcr_011.json",
        "packet_sha256": "2" * 64,
        "stages": [stage_payloads[name] for name in stages],
    }
    if not ok:
        report["failed_stage"] = "image_qa_validation"
        report["error"] = {"code": "qa_not_passed", "detail": "photo QA artifact must pass before packaging"}
        report["stages"] = report["stages"][:2]
        report["generation_failed_stage"] = "image_qa_validation"
    return report


def _patch_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cycle, "REPORTS", tmp_path / REPORT_ROOT)
    monkeypatch.setattr(cycle, "STRATEGY_REPORT_ROOT", tmp_path / STRATEGY_REPORT_ROOT)
    monkeypatch.setattr(cycle, "GENERATION_REPORT_ROOT", tmp_path / REPORT_ROOT)
    monkeypatch.setattr(generation_cycle, "DEFAULT_REPORTS_ROOT", tmp_path / REPORT_ROOT)
    monkeypatch.setattr(generation_cycle, "DEFAULT_MANIFEST_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    monkeypatch.setattr(generation_cycle, "DEFAULT_IMAGE_ROOT", tmp_path / "pipeline" / "higgsfield_library" / "lena")
    monkeypatch.setattr(generation_cycle, "DEFAULT_QA_ROOT", tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa")


def test_successful_chain_records_child_receipts_and_full_stage_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "010203")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T01:02:03")

    strategy_report_path = _strategy_report_path(tmp_path)
    strategy_report = _strategy_report()
    generation_report_path = _generation_report_path(tmp_path)
    generation_report = _generation_report(report_path=str(generation_report_path))

    def _normalized_command_tokens(cmd: list[str]) -> list[str]:
        normalized: list[str] = []
        for part in cmd:
            lowered = part.lower()
            if lowered.endswith((".py", ".exe", ".cmd", ".bat")):
                normalized.append(Path(part).name.lower())
            else:
                normalized.append(lowered)
        return normalized

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        tokens = _normalized_command_tokens(cmd)
        assert not any(token == "provider" or token.startswith("--provider") for token in tokens)
        assert not any(token == "publish" or token.startswith("--publish") for token in tokens)
        if label == "strategy_preparation":
            _write_json(strategy_report_path, strategy_report)
            return {
                "label": label,
                "cmd": cmd,
                "cmd_text": subprocess.list2cmdline(cmd),
                "returncode": 0,
                "ok": True,
                "stdout": json.dumps({"report_path": str(strategy_report_path)}),
                "stderr": "",
            }
        assert label == "analytics_intake_sync"
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"ok": True, "receipts_scanned": 3, "created": 1, "updated": 2}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: dict(generation_report))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    assert cycle.main() == 0

    report = json.loads(_aggregate_report_path(tmp_path).read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["publishing_authorized"] is False
    assert report["provider_calls_performed"] == 0
    assert report["publish_calls_performed"] == 0
    assert report["retries_performed"] == 0
    assert report["prompt_binding_verified"] is False
    assert report["asserted_lineage"]["prompt_sha256"] == "c" * 64
    assert report["asserted_lineage"]["authority_commit"] == "d" * 40
    assert report["child_receipts"]["strategy"]["path"] == str(strategy_report_path)
    assert report["child_receipts"]["generation"]["path"] == str(generation_report_path)
    assert report["stages"][0]["stage"] == "strategy_preparation"
    assert report["stages"][0]["command"]
    assert "lena_strategy_autonomy_run_v1.py" in report["stages"][0]["command"]
    assert [item["stage"] for item in report["stages"][1:5]] == [
        "approved_candidate_resolution",
        "generation_result_intake",
        "image_qa_validation",
        "caption_package_creation",
    ]
    assert report["stages"][5]["stage"] == "analytics_intake_sync"
    assert "lena_sync_architecture_a_receipts_to_metrics_v1.py" in report["stages"][5]["command"]
    assert report["analytics_summary"]["receipts_scanned"] == 3


def test_strategy_failure_stops_generation_half(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "040506")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T04:05:06")

    strategy_report_path = _strategy_report_path(tmp_path, "040506")
    _write_json(strategy_report_path, _strategy_report(ok=False))
    calls: list[str] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        calls.append(label)
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 7,
            "ok": False,
            "stdout": json.dumps({"report_path": str(strategy_report_path)}),
            "stderr": "strategy failed",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: (_ for _ in ()).throw(AssertionError("generation stage should not run")))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    assert cycle.main() == 1
    assert calls == ["strategy_preparation"]
    report = json.loads(_aggregate_report_path(tmp_path, "040506").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "strategy_preparation"
    assert len(report["stages"]) == 1


def test_generation_failure_stops_analytics_intake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "070809")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T07:08:09")

    strategy_report_path = _strategy_report_path(tmp_path, "070809")
    _write_json(strategy_report_path, _strategy_report())
    generation_report_path = _generation_report_path(tmp_path, "070809")
    generation_report = _generation_report(report_path=str(generation_report_path), ok=False)

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        assert label == "strategy_preparation"
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"report_path": str(strategy_report_path)}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: dict(generation_report))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    assert cycle.main() == 1
    report = json.loads(_aggregate_report_path(tmp_path, "070809").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "image_qa_validation"
    assert report["generation_failed_stage"] == "image_qa_validation"
    assert [item["stage"] for item in report["stages"]] == [
        "strategy_preparation",
        "approved_candidate_resolution",
        "generation_result_intake",
    ]


def test_analytics_failure_is_recorded_and_later_activity_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "101112")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T10:11:12")

    strategy_report_path = _strategy_report_path(tmp_path, "101112")
    _write_json(strategy_report_path, _strategy_report())
    generation_report_path = _generation_report_path(tmp_path, "101112")
    generation_report = _generation_report(report_path=str(generation_report_path))
    calls: list[str] = []

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        calls.append(label)
        if label == "strategy_preparation":
            return {
                "label": label,
                "cmd": cmd,
                "cmd_text": subprocess.list2cmdline(cmd),
                "returncode": 0,
                "ok": True,
                "stdout": json.dumps({"report_path": str(strategy_report_path)}),
                "stderr": "",
            }
        assert label == "analytics_intake_sync"
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 5,
            "ok": False,
            "stdout": "",
            "stderr": "analytics failed",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: dict(generation_report))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    assert cycle.main() == 1
    assert calls == ["strategy_preparation", "analytics_intake_sync"]
    report = json.loads(_aggregate_report_path(tmp_path, "101112").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["failed_stage"] == "analytics_intake_sync"
    assert len(report["stages"]) == 6


def test_child_receipt_sha_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "131415")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T13:14:15")

    strategy_report_path = _strategy_report_path(tmp_path, "131415")
    _write_json(strategy_report_path, _strategy_report())
    generation_report_path = _generation_report_path(tmp_path, "131415")
    generation_report = _generation_report(report_path=str(generation_report_path))
    tampered = {"done": False}

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        if label == "strategy_preparation":
            return {
                "label": label,
                "cmd": cmd,
                "cmd_text": subprocess.list2cmdline(cmd),
                "returncode": 0,
                "ok": True,
                "stdout": json.dumps({"report_path": str(strategy_report_path)}),
                "stderr": "",
            }
        assert label == "analytics_intake_sync"
        if not tampered["done"]:
            payload = json.loads(generation_report_path.read_text(encoding="utf-8"))
            payload["provider_calls_performed"] = 1
            generation_report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
            tampered["done"] = True
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"ok": True, "receipts_scanned": 1}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: dict(generation_report))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    with pytest.raises(cycle.LenaFullAutonomyDryRunError, match="generation report SHA-256 no longer matches its bound bytes"):
        cycle.main()


def test_generation_stage_order_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "161718")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T16:17:18")

    strategy_report_path = _strategy_report_path(tmp_path, "161718")
    _write_json(strategy_report_path, _strategy_report())
    generation_report_path = _generation_report_path(tmp_path, "161718")
    bad_report = _generation_report(
        report_path=str(generation_report_path),
        stage_order=[
            "generation_result_intake",
            "approved_candidate_resolution",
            "image_qa_validation",
            "caption_package_creation",
        ],
    )

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"report_path": str(strategy_report_path)}) if label == "strategy_preparation" else json.dumps({"ok": True, "receipts_scanned": 2}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: dict(bad_report))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    with pytest.raises(cycle.LenaFullAutonomyDryRunError, match="stage order mismatch"):
        cycle.main()


@pytest.mark.parametrize(
    "field,value,code,match_text",
    [
        ("publishing_authorized", True, "publishing_authorized_must_be_false", "generation report must keep publishing_authorized false"),
        ("provider_calls_performed", 1, "provider_calls_performed_not_zero", "generation report must not record provider calls"),
        ("publish_calls_performed", 1, "publish_calls_performed_not_zero", "generation report must not record publish calls"),
        ("retries_performed", 1, "retries_performed_not_zero", "generation report must not record retries"),
    ],
)
def test_child_truthfulness_gates_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: int | bool,
    code: str,
    match_text: str,
) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "192021")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T19:20:21")

    strategy_report_path = _strategy_report_path(tmp_path, "192021")
    _write_json(strategy_report_path, _strategy_report())
    generation_report_path = _generation_report_path(tmp_path, "192021")
    bad_report = _generation_report(report_path=str(generation_report_path))
    bad_report[field] = value

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"report_path": str(strategy_report_path)}) if label == "strategy_preparation" else json.dumps({"ok": True}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: dict(bad_report))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    with pytest.raises(cycle.LenaFullAutonomyDryRunError, match=match_text):
        cycle.main()


def test_duplicate_aggregate_receipt_fails_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "222324")
    report_path = _aggregate_report_path(tmp_path, "222324")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def no_run_step(label: str, cmd: list[str]) -> dict[str, object]:  # pragma: no cover - defensive
        calls.append(label)
        raise AssertionError("no stages should run once the aggregate receipt exists")

    monkeypatch.setattr(cycle, "run_step", no_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: (_ for _ in ()).throw(AssertionError("generation stage should not run")))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    with pytest.raises(cycle.LenaFullAutonomyDryRunError, match="aggregate receipt already exists"):
        cycle.main()
    assert calls == []


def test_report_root_symlink_escape_is_rejected_before_any_stage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    report_link = tmp_path / "report_link"
    try:
        report_link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported in this environment")
    monkeypatch.setattr(sys, "argv", [
        "cycle",
        "--date",
        DATE,
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--qa-artifact",
        str(tmp_path / "qa.json"),
        "--report-root",
        str(report_link),
        "--generation-report-root",
        str(tmp_path / REPORT_ROOT),
        "--manifest-root",
        str(tmp_path / "pipeline" / "higgsfield_debug"),
        "--image-root",
        str(tmp_path / "pipeline" / "higgsfield_library" / "lena"),
        "--qa-root",
        str(tmp_path / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa"),
        "--packet-root",
        str(tmp_path / "pipeline" / "strategy" / "lena" / "publish_packets"),
    ])
    with pytest.raises(cycle.LenaFullAutonomyDryRunError) as exc_info:
        cycle.main()

    assert exc_info.value.code == "strategy_report_path_escape"


def test_strategy_child_report_path_escape_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(monkeypatch, tmp_path)
    monkeypatch.setattr(cycle, "now_stamp", lambda: "252627")
    monkeypatch.setattr(cycle, "now_iso", lambda: "2026-07-18T25:26:27")

    def fake_run_step(label: str, cmd: list[str]) -> dict[str, object]:
        return {
            "label": label,
            "cmd": cmd,
            "cmd_text": subprocess.list2cmdline(cmd),
            "returncode": 0,
            "ok": True,
            "stdout": json.dumps({"report_path": str(tmp_path / "outside" / "strategy.json")}) if label == "strategy_preparation" else json.dumps({"ok": True}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "run_step", fake_run_step)
    monkeypatch.setattr(generation_cycle, "run_cycle", lambda args: (_ for _ in ()).throw(AssertionError("generation stage should not run")))
    monkeypatch.setattr(sys, "argv", _default_args(tmp_path))

    with pytest.raises(cycle.LenaFullAutonomyDryRunError, match="resolved strategy report escapes declared root"):
        cycle.main()
