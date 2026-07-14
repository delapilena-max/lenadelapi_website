from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import higgsfield_lena_api_executor as executor
from tools.strategy import lena_execute_retry_decision_v1 as retry_consumer


DATE = "2026-07-13"
ORIGINAL_SLOT = "lenagate2026071325ca9e1d-pack000-01-photo"
IMAGE_SHA = "ae53f875421f38750d85757a9dd7336691c9acd5cff555a3f51281e1f062e5a4"
CORRECTION = ROOT / "pipeline" / "asset_review" / "lena" / DATE / (
    f"{ORIGINAL_SLOT}__{IMAGE_SHA}_bounded_retry_plan_correction.json"
)


def test_committed_correction_builds_bounded_retry_decision_without_writing(tmp_path: Path) -> None:
    report = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
    )
    assert report["state"] == "ready_for_retry_executor_dry_run"
    assert report["original_slot_id"] == ORIGINAL_SLOT
    assert report["retry_slot_id"] == f"lenagate2026071325ca9e1d-pack000-01-retry01-photo"
    assert report["retry_attempt"] == report["retry_cap"] == 1
    assert report["validation_results"]["original_decision_validation"] is True
    assert report["validation_results"]["correction_lineage_validation"] is True
    assert report["validation_results"]["retry_prompt_mutation_validation"] is True
    dry_run = report["validation_results"]["executor_dry_run"]
    assert dry_run["dry_run"] is True
    assert dry_run["live_flag_present"] is False
    assert dry_run["validation"]["ok"] is True
    assert "retry_prompt_sha256=" in report["exact_next_allowed_action"]
    assert Path(report["retry_decision_artifact_path"]).exists() is False


def test_written_retry_decision_is_distinct_and_duplicate_safe(tmp_path: Path) -> None:
    written = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
        write_decision=True,
    )
    artifact_path = Path(written["retry_decision_artifact_path"])
    assert written["state"] == "retry_decision_written"
    assert artifact_path.is_file()

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == retry_consumer.SCHEMA_VERSION
    assert artifact["original_slot_id"] == ORIGINAL_SLOT
    assert artifact["retry_slot_id"] != ORIGINAL_SLOT
    assert artifact["lane"] == "night out"
    assert artifact["recipe_id"] == "hcr_006"
    assert artifact["hook_id"] == "cbn_004"
    assert artifact["prompt_mutation"]["mode"] == "scene_constraint_only"
    assert artifact["prompt_mutation"]["reason"] == retry_consumer.MUTATION_REASON
    assert retry_consumer.BACKGROUND_IDENTITY_CONSTRAINT in artifact["retry_prompt_text"]
    assert artifact["retry_prompt_text"].count(retry_consumer.BACKGROUND_IDENTITY_CONSTRAINT) == 1

    replay = retry_consumer.evaluate_retry_correction(
        retry_decision_artifact_path=artifact_path,
        output_root=tmp_path,
    )
    assert replay["retry_decision_fingerprint_sha256"] == written["retry_decision_fingerprint_sha256"]
    assert replay["validation_results"]["executor_dry_run"]["validation"]["ok"] is True

    with pytest.raises(retry_consumer.RetryDecisionError) as error:
        retry_consumer.evaluate_retry_correction(
            correction_artifact_path=CORRECTION,
            output_root=tmp_path,
        )
    assert error.value.code == "duplicate_retry_decision"


def test_written_retry_decision_reaches_real_executor_dry_run_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    written = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
        write_decision=True,
    )
    artifact_path = Path(written["retry_decision_artifact_path"])

    monkeypatch.setattr(
        sys,
        "argv",
        ["executor", "--retry-decision-artifact", str(artifact_path)],
    )
    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===" in stdout
    assert f"slot_id                 : {written['retry_slot_id']}" in stdout
    assert str(executor.manifest_path(DATE, written["retry_slot_id"])) in stdout
    assert "=== RESULT: no subprocess call, no network call, no file written. Dry-run only. ===" in stdout
    assert not executor.manifest_path(DATE, written["retry_slot_id"]).exists()


def test_tampered_retry_decision_fails_closed(tmp_path: Path) -> None:
    written = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
        write_decision=True,
    )
    artifact_path = Path(written["retry_decision_artifact_path"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["source_publish_packet_sha256"] = "0" * 64
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(retry_consumer.RetryDecisionError) as error:
        retry_consumer.evaluate_retry_correction(
            retry_decision_artifact_path=artifact_path,
            output_root=tmp_path,
        )
    assert error.value.code == "fingerprint_mismatch"


def test_tampered_retry_lineage_fails_before_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    written = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
        write_decision=True,
    )
    artifact_path = Path(written["retry_decision_artifact_path"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["source_retry_plan_correction_artifact_sha256"] = "0" * 64
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("live provider path must not be reached for a tampered retry lineage")

    monkeypatch.setattr(executor, "run_live", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        ["executor", "--retry-decision-artifact", str(artifact_path), "--live"],
    )
    assert executor.main() == 1
    stdout = capsys.readouterr().out
    assert "[ABORT]" in stdout
    assert "fingerprint" in stdout.lower()


def test_retry_attempt_two_is_impossible(tmp_path: Path) -> None:
    written = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
        write_decision=True,
    )
    artifact_path = Path(written["retry_decision_artifact_path"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["retry_attempt"] = 2
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(retry_consumer.RetryDecisionError) as error:
        retry_consumer.evaluate_retry_correction(
            retry_decision_artifact_path=artifact_path,
            output_root=tmp_path,
        )
    assert error.value.code == "retry_cap_invalid"


def test_no_write_default_performs_no_provider_or_file_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("provider path must not be reached during no-write retry planning")

    monkeypatch.setattr(executor, "run_live", forbidden)
    report = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=CORRECTION,
        output_root=tmp_path,
    )
    assert report["state"] == "ready_for_retry_executor_dry_run"
    assert list(tmp_path.rglob("*")) == []


def test_cli_emits_one_machine_readable_blocked_report(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["retry-consumer", "--correction-artifact", str(missing)])
    assert retry_consumer.main() == 2
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    report = json.loads(lines[0])
    assert report["state"] == "blocked"
    assert report["provider_authorized"] is False
    assert report["provider_called"] is False
    assert report["generation_performed"] is False
    assert report["side_effects_performed"] == []
