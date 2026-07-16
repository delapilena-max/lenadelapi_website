from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pipeline.influencer_nodes.lena import autonomy_ladder
from pipeline import higgsfield_lena_api_executor as executor
from tools import lena_build_approved_publish_queue_v2_8 as publish_queue
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools import lena_higgsfield_retry_generation_approval_v1 as retry_approval
from tools import lena_photo_qa_disposition_v1 as photo_qa
from tools.strategy import lena_build_next_live_image_handoff_v1 as handoff_builder
from tools.strategy import lena_reconciliation_contract_v1 as reconciliation_contract
from tools.strategy import lena_execute_retry_decision_v1 as retry_decision
from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _fake_handoff_facts() -> dict:
    return {
        "report": {
            "report_type": "lena_next_live_image_handoff",
            "schema_version": "v1",
        },
        "handoff_repo_path": "pipeline/strategy/lena/next_actions/2026-07-13/lena_next_live_image_handoff_2026-07-13.json",
        "handoff_sha256": "a" * 64,
        "date": "2026-07-13",
        "slot_id": "higgsfield-20260713-hcr_006-photo",
        "prompt_sha256": "b" * 64,
        "soul_name": "Lena",
        "soul_type": "Soul 2.0",
        "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
    }


def _fake_retry_facts() -> dict:
    return {
        "artifact": {
            "report_type": "lena_higgsfield_retry_handoff_v1",
            "schema_version": "v1",
        },
        "retry_handoff_repo_path": "pipeline/strategy/lena/retry_handoffs/2026-07-13/sample.json",
        "retry_handoff_sha256": "c" * 64,
        "date": "2026-07-13",
        "slot_id": "higgsfield-20260713-hcr_006-retry01-photo",
        "prompt_sha256": "d" * 64,
        "original_slot_id": "higgsfield-20260713-hcr_006-photo",
        "source_handoff_artifact_path": "pipeline/strategy/lena/next_actions/2026-07-13/lena_next_live_image_handoff_2026-07-13.json",
        "source_handoff_artifact_sha256": "e" * 64,
        "source_execution_receipt_path": "pipeline/approvals/lena/generation/2026-07-13/higgsfield-20260713-hcr_006-photo_higgsfield_generation_execution_receipt.json",
        "source_execution_receipt_sha256": "f" * 64,
        "provider": "Higgsfield",
        "executor": "Higgsfield CLI repo adapter",
        "model": "text2image_soul_v2",
        "aspect_ratio": "9:16",
        "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
        "soul_name": "Lena",
        "soul_type": "Soul 2.0",
        "retry_handoff_fingerprint_sha256": "1" * 64,
    }


def test_contract_loads_from_committed_json_and_exposes_authority() -> None:
    contract = autonomy_ladder.load_contract()
    summary = autonomy_ladder.contract_summary(contract)

    assert contract["schema_version"] == "lena_autonomy_ladder_v1"
    assert contract["publish_freeze"]["active"] is True
    assert summary["publish_freeze_active"] is True
    assert summary["active_levels"] == [0, 1, 2]
    assert autonomy_ladder.get_level(contract, 3)["disabled_by_publish_freeze"] is True
    assert autonomy_ladder.get_level(contract, 4)["status"] == "future_only"
    assert autonomy_ladder.get_level(contract, 5)["enabled"] is False

    serialized = json.dumps(contract, sort_keys=True)
    assert "C:\\projects\\ai\\content_bot" not in serialized
    assert "content_bot_pr_clean" not in serialized

    with pytest.raises(TypeError):
        autonomy_ladder.load_contract(Path("override.json"))  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ("not json", "contract_malformed"),
        (json.dumps({"schema_version": "lena_autonomy_ladder_v1"}), "contract_invalid"),
    ],
)
def test_missing_or_malformed_contract_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str, expected_code: str) -> None:
    contract_path = tmp_path / "autonomy_ladder_v1.json"
    contract_path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", contract_path)

    with pytest.raises(autonomy_ladder.AutonomyLadderError) as error:
        autonomy_ladder.load_contract()

    assert error.value.code == expected_code


def test_level_three_is_real_but_blocked_by_publish_freeze() -> None:
    with pytest.raises(autonomy_ladder.AutonomyLadderBlocked) as error:
        autonomy_ladder.assert_allowed(
            "publish_queue",
            level=3,
            action="human-approved posting preparation",
        )

    assert error.value.code == "publish_freeze_active"
    assert error.value.report["contract"]["publish_freeze_active"] is True
    assert error.value.report["contract"]["level_3_disabled_by_publish_freeze"] is True

    with pytest.raises(TypeError):
        autonomy_ladder.assert_allowed(
            "publish_queue",
            level=3,
            action="human-approved posting preparation",
            allow_when_publish_freeze_active=True,  # type: ignore[call-arg]
        )


def test_level_two_approval_records_do_not_grant_posting_authority() -> None:
    generation_record = approval.build_generation_approval_record(
        _fake_handoff_facts(),
        operator_id=approval.CANONICAL_OPERATOR_ID,
        confirmation=approval.confirmation_phrase("higgsfield-20260713-hcr_006-photo"),
    )
    retry_record = retry_approval.build_retry_generation_approval_record(
        _fake_retry_facts(),
        operator_id=approval.CANONICAL_OPERATOR_ID,
        confirmation=retry_approval.confirmation_phrase("higgsfield-20260713-hcr_006-retry01-photo"),
    )

    for record in (generation_record, retry_record):
        assert record["upload_authorized"] is False
        assert record["queue_promotion_authorized"] is False
        assert record["publish_authorized"] is False
        assert record["analytics_mutation_authorized"] is False


def test_handoff_builder_blocks_before_loading_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract_path = tmp_path / "missing_autonomy_ladder.json"
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", contract_path)
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("handoff load_report must not be reached when the ladder is missing")

    monkeypatch.setattr(handoff_builder, "load_report", forbidden)

    with pytest.raises(handoff_builder.HandoffBuildError) as error:
        handoff_builder.build_handoff(
            "2026-07-13",
            "pipeline/strategy/lena/reconciliations/2026-07-13/lena_generation_reconciliation_fixture.json",
        )

    assert "contract_missing" in str(error.value)


def test_selected_candidate_blocks_before_reading_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract_path = tmp_path / "missing_autonomy_ladder.json"
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", contract_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("selected-candidate artifact read must not be reached when the ladder is missing")

    monkeypatch.setattr(selected_candidate, "_read_artifact", forbidden)

    with pytest.raises(selected_candidate.ConsumerError) as error:
        selected_candidate.evaluate_decision(tmp_path / "decision.json")

    assert error.value.code == "contract_missing"


def test_retry_decision_blocks_before_reading_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract_path = tmp_path / "missing_autonomy_ladder.json"
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", contract_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("retry lineage validation must not be reached when the ladder is missing")

    monkeypatch.setattr(retry_decision, "_validate_correction_artifact", forbidden)

    with pytest.raises(retry_decision.RetryDecisionError) as error:
        retry_decision.evaluate_retry_correction(correction_artifact_path=tmp_path / "correction.json")

    assert error.value.code == "contract_missing"


def test_executor_blocks_before_provider_or_claim_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract_path = tmp_path / "missing_autonomy_ladder.json"
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", contract_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("live provider path must not be reached when the ladder is missing")

    monkeypatch.setattr(executor, "run_live", forbidden)
    monkeypatch.setattr(sys, "argv", [
        "executor",
        "--date",
        "2026-07-13",
        "--slot-id",
        "higgsfield-20260713-hcr_006-photo",
        "--handoff-artifact",
        str(tmp_path / "handoff.json"),
        "--approval-artifact",
        str(tmp_path / "approval.json"),
        "--live",
    ])

    assert executor.main() == 1


def test_publish_queue_blocks_before_writing_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    contract_path = tmp_path / "missing_autonomy_ladder.json"
    monkeypatch.setattr(autonomy_ladder, "CONTRACT_PATH", contract_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("queue write must not be reached when the ladder is missing")

    monkeypatch.setattr(publish_queue, "write_csv", forbidden)
    monkeypatch.setattr(sys, "argv", ["publish-queue", "--date", "2026-07-13"])

    assert publish_queue.main() == 1
    output = capsys.readouterr().out
    assert "contract_missing" in output
