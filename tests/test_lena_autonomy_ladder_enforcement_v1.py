from __future__ import annotations

import hashlib
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
RELEASED_POLICY_RELATIVE_PATH = Path("pipeline/influencer_nodes/lena/approved_queue_auto_publisher_policy_v2_8.json")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")).hexdigest()


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
        "expression_provenance_fingerprint_sha256": "2" * 64,
    }


def _released_policy_payload(
    *,
    enabled: bool = True,
    authority_commit: str = "a" * 40,
    expires_at_utc: str = "2026-12-31T23:59:59Z",
    policy_id: str = "lena_approved_queue_auto_publisher_policy_v2_8",
    policy_version: str = "v2.8.0",
    repository_name: str = "delapilena-max/lenadelapi_website",
    autonomous_policy_state: str = "enabled",
) -> dict[str, object]:
    return {
        "version": "v2.9.1_auto_queue_publisher",
        "policy_id": policy_id,
        "policy_version": policy_version,
        "repository_name": repository_name,
        "authority_version": "main",
        "authority_commit": authority_commit,
        "autonomous_mode": "scheduled_autonomous",
        "autonomous_enabled": enabled,
        "autonomous_enabled_by_default": False,
        "autonomous_policy_state": autonomous_policy_state if enabled else "disabled_by_default",
        "policy_effective_at_utc": "2026-07-19T00:00:00Z",
        "policy_expires_at_utc": expires_at_utc,
        "approved_slots": ["morning", "afternoon", "evening"],
        "hard_item_limit_per_invocation": 1,
        "queue_claim_lease_seconds": 1800,
        "max_attempts_per_row": 3,
        "autonomous_queue_platforms": ["Instagram Feed", "Facebook Page"],
        "manual_live_mode_unchanged": True,
        "manual_live_flags": ["--live", "--i-understand-this-can-publish"],
        "autonomous_mode_requires_distinct_policy_gate": True,
        "require_queue_build_before_first_publish_slot": True,
        "require_clean_export_revalidation": True,
        "require_atomic_queue_claim": True,
        "require_platform_receipts": True,
        "require_idempotent_post_log_sync": True,
        "allow_replies": False,
        "allow_dms": False,
        "allow_outreach": False,
        "safety": {
            "auto_replying": False,
            "auto_dm_sending": False,
            "auto_outreach": False,
            "delete_after_publish": False,
            "duplicate_prevention": True,
            "already_posted_skip": True,
            "bounded_retries": True,
            "crash_recovery": True,
            "stale_claim_handling": True,
            "partial_platform_failure_fail_closed": True,
        },
        "publish_mode": "explicit_live_connector_required",
        "queue_enabled": True,
        "autopublish_enabled": False,
        "live_posting_requires_explicit_flags": True,
        "required_live_flags": ["--live", "--i-understand-this-can-publish"],
    }


def _released_contract_payload(*, policy_path: Path, policy_payload: dict[str, object]) -> dict[str, object]:
    policy_sha256 = _normalized_sha256(policy_path)
    return {
        "version": "v1.0.0",
        "schema_version": "lena_autonomy_ladder_v1",
        "node_name": "Lena",
        "node_role": "Node 1 of the autonomous media engine",
        "purpose": "Define the operating contract for Lena as the first node in the autonomy ladder.",
        "publish_freeze": {
            "active": False,
            "scope": "Level 3 autonomous publishing is now governed by the approved autonomous publishing policy.",
            "frozen_surfaces": [],
        },
        "autonomy_rules": {
            "auto_approval_forbidden": True,
            "implicit_escalation_forbidden": True,
            "generation_approval_does_not_imply_posting_approval": True,
        },
        "level_3_authority": {
            "policy_id": policy_payload["policy_id"],
            "policy_path": RELEASED_POLICY_RELATIVE_PATH.as_posix(),
            "policy_sha256": policy_sha256,
            "policy_version": policy_payload["policy_version"],
            "repository_name": policy_payload["repository_name"],
            "authority_version": policy_payload["authority_version"],
            "authority_commit": policy_payload["authority_commit"],
            "autonomous_mode": policy_payload["autonomous_mode"],
            "autonomous_enabled": policy_payload["autonomous_enabled"],
            "autonomous_enabled_by_default": policy_payload["autonomous_enabled_by_default"],
            "autonomous_policy_state": policy_payload["autonomous_policy_state"],
            "approved_slots": policy_payload["approved_slots"],
            "hard_item_limit_per_invocation": policy_payload["hard_item_limit_per_invocation"],
            "queue_claim_lease_seconds": policy_payload["queue_claim_lease_seconds"],
            "max_attempts_per_row": policy_payload["max_attempts_per_row"],
            "autonomous_queue_platforms": policy_payload["autonomous_queue_platforms"],
            "manual_live_mode_unchanged": policy_payload["manual_live_mode_unchanged"],
            "autonomous_mode_requires_distinct_policy_gate": policy_payload["autonomous_mode_requires_distinct_policy_gate"],
            "require_queue_build_before_first_publish_slot": policy_payload["require_queue_build_before_first_publish_slot"],
            "require_clean_export_revalidation": policy_payload["require_clean_export_revalidation"],
            "require_atomic_queue_claim": policy_payload["require_atomic_queue_claim"],
            "require_platform_receipts": policy_payload["require_platform_receipts"],
            "require_idempotent_post_log_sync": policy_payload["require_idempotent_post_log_sync"],
            "allow_replies": policy_payload["allow_replies"],
            "allow_dms": policy_payload["allow_dms"],
            "allow_outreach": policy_payload["allow_outreach"],
            "duplicate_prevention": policy_payload["safety"]["duplicate_prevention"],
            "already_posted_skip": policy_payload["safety"]["already_posted_skip"],
            "bounded_retries": policy_payload["safety"]["bounded_retries"],
            "crash_recovery": policy_payload["safety"]["crash_recovery"],
            "stale_claim_handling": policy_payload["safety"]["stale_claim_handling"],
            "partial_platform_failure_fail_closed": policy_payload["safety"]["partial_platform_failure_fail_closed"],
            "live_posting_requires_explicit_flags": policy_payload["live_posting_requires_explicit_flags"],
            "required_live_flags": policy_payload["required_live_flags"],
        },
        "levels": [
            {"level": 0, "name": "dry_run_no_live", "enabled": True, "status": "active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
            {"level": 1, "name": "candidate_generation_only", "enabled": True, "status": "active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
            {"level": 2, "name": "live_higgsfield_generation_with_explicit_approval", "enabled": True, "status": "active", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
            {
                "level": 3,
                "name": "bounded_autonomous_posting",
                "enabled": True,
                "status": "active",
                "future_placeholder": False,
                "disabled_by_publish_freeze": False,
                "allowed_actions": [
                    "human-approved posting preparation",
                    "manual publish review",
                    "approved queue construction",
                    "connector dispatch after explicit human approval",
                ],
                "forbidden_actions": [
                    "autonomous posting",
                    "auto-approval",
                    "implicit escalation",
                    "queue promotion without separate human approval",
                ],
                "required_artifacts": [
                    "publish packet",
                    "approved queue item",
                    "connector payload",
                    "post log or closure report",
                    "manual publish approval",
                ],
                "approval_requirements": {
                    "human_posting_approval_required": True,
                    "per_item_or_batch_approval_required": True,
                    "separate_from_generation_approval": True,
                },
                "failure_handling": [
                    "require approved autonomous policy binding before autonomous publishing",
                    "stop on any missing approval artifact",
                    "never infer posting approval from generation approval",
                ],
                "tests_required": [
                    "publish queue policy tests",
                    "manual approval gate tests",
                ],
            },
            {"level": 4, "name": "bounded_autonomous_posting", "enabled": False, "status": "future_only", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
            {"level": 5, "name": "multi_node_autonomous_media_engine", "enabled": False, "status": "future_only", "allowed_actions": [], "forbidden_actions": [], "required_artifacts": [], "approval_requirements": {}, "failure_handling": [], "tests_required": []},
        ],
    }


def _write_released_policy_tree(
    tmp_path: Path,
    *,
    enabled: bool = True,
    authority_commit: str = "a" * 40,
    expires_at_utc: str = "2026-12-31T23:59:59Z",
    malformed_policy_text: str | None = None,
    repository_name: str = "delapilena-max/lenadelapi_website",
    policy_id: str = "lena_approved_queue_auto_publisher_policy_v2_8",
) -> tuple[Path, Path]:
    policy_path = tmp_path / RELEASED_POLICY_RELATIVE_PATH
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    if malformed_policy_text is not None:
        policy_path.write_text(malformed_policy_text, encoding="utf-8")
    else:
        policy = _released_policy_payload(
            enabled=enabled,
            authority_commit=authority_commit,
            expires_at_utc=expires_at_utc,
            repository_name=repository_name,
            policy_id=policy_id,
        )
        _write_json(policy_path, policy)

    contract_path = tmp_path / "pipeline" / "influencer_nodes" / "lena" / "autonomy_ladder_v1.json"
    contract_payload = _released_contract_payload(
        policy_path=policy_path,
        policy_payload=_released_policy_payload(
            enabled=enabled,
            authority_commit=authority_commit,
            expires_at_utc=expires_at_utc,
            repository_name=repository_name,
            policy_id=policy_id,
        ),
    )
    _write_json(contract_path, contract_payload)
    return contract_path, policy_path


def _patch_released_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(autonomy_ladder, "ROOT", tmp_path)
    monkeypatch.setattr(
        autonomy_ladder,
        "CONTRACT_PATH",
        tmp_path / "pipeline" / "influencer_nodes" / "lena" / "autonomy_ladder_v1.json",
    )


def _patch_git_head(monkeypatch: pytest.MonkeyPatch, commit: str, *, ancestor_pairs: set[tuple[str, str]] | None = None) -> None:
    allowed = set(ancestor_pairs or {(commit, commit)})

    class FakeProcess:
        def __init__(self, cmd):
            self.cmd = cmd
            self.returncode = 0

        def communicate(self):
            if list(self.cmd[:3]) == ["git", "rev-parse", "HEAD"]:
                return commit, ""
            if list(self.cmd[:3]) == ["git", "merge-base", "--is-ancestor"]:
                pair = (self.cmd[3], self.cmd[4])
                if pair in allowed:
                    return "", ""
                self.returncode = 1
                return "", ""
            raise AssertionError(f"unexpected git command: {self.cmd}")

    def fake_popen(cmd, *args, **kwargs):
        return FakeProcess(cmd)

    monkeypatch.setattr(autonomy_ladder.subprocess, "Popen", fake_popen)


def test_contract_loads_from_committed_json_and_exposes_authority() -> None:
    contract = autonomy_ladder.load_contract()
    summary = autonomy_ladder.contract_summary(contract)

    assert contract["schema_version"] == "lena_autonomy_ladder_v1"
    assert contract["publish_freeze"]["active"] is False
    assert summary["publish_freeze_active"] is False
    assert summary["active_levels"] == [0, 1, 2, 3]
    assert summary["level_3_enabled"] is True
    assert summary["level_3_authority_policy_id"] == "lena_approved_queue_auto_publisher_policy_v2_8"
    assert summary["level_3_authority_policy_path"] == "pipeline/influencer_nodes/lena/approved_queue_auto_publisher_policy_v2_8.json"
    assert autonomy_ladder.get_level(contract, 3)["enabled"] is True
    assert autonomy_ladder.get_level(contract, 3)["disabled_by_publish_freeze"] is False
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


def test_level_three_is_real_and_binds_to_replacement_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_released_tree(monkeypatch, tmp_path)
    _write_released_policy_tree(tmp_path)
    _patch_git_head(monkeypatch, "b" * 40, ancestor_pairs={("a" * 40, "b" * 40)})

    contract = autonomy_ladder.load_contract()
    assert contract["publish_freeze"]["active"] is False
    assert contract["level_3_authority"]["policy_id"] == "lena_approved_queue_auto_publisher_policy_v2_8"
    assert contract["level_3_authority"]["policy_path"] == RELEASED_POLICY_RELATIVE_PATH.as_posix()

    validated = autonomy_ladder.assert_allowed(
        "publish_queue",
        level=3,
        action="human-approved posting preparation",
    )

    assert validated["level_3_authority"]["policy_id"] == "lena_approved_queue_auto_publisher_policy_v2_8"


@pytest.mark.parametrize(
    ("policy_mutation", "expected_code"),
    [
        ({"autonomous_enabled": False}, "level_3_policy_disabled"),
        ({"policy_expires_at_utc": "2020-01-01T00:00:00Z"}, "level_3_policy_expired"),
        ({"policy_expires_at_utc": "NOT-A-DATE"}, "level_3_policy_expiry_malformed"),
        ({"policy_expires_at_utc": "2099-12-31T23:59:59"}, "level_3_policy_expiry_malformed"),
        ({"authority_commit": "c" * 40}, "level_3_policy_stale"),
        ({"policy_id": "wrong-policy"}, "level_3_policy_unauthorized"),
        ({"repository_name": "some-other-repo"}, "level_3_policy_unauthorized"),
    ],
)
def test_level_three_replacement_policy_failures_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy_mutation: dict[str, object],
    expected_code: str,
) -> None:
    _patch_released_tree(monkeypatch, tmp_path)
    contract_path, policy_path = _write_released_policy_tree(
        tmp_path,
        enabled=bool(policy_mutation.get("autonomous_enabled", True)),
        authority_commit=str(policy_mutation.get("authority_commit", "a" * 40)),
        expires_at_utc=str(policy_mutation.get("policy_expires_at_utc", "2026-12-31T23:59:59Z")),
        repository_name=str(policy_mutation.get("repository_name", "delapilena-max/lenadelapi_website")),
        policy_id=str(policy_mutation.get("policy_id", "lena_approved_queue_auto_publisher_policy_v2_8")),
    )
    # Rebuild the policy with the full default payload and then mutate the one target field.
    payload = _released_policy_payload()
    payload.update(policy_mutation)
    _write_json(policy_path, payload)
    _write_json(contract_path, _released_contract_payload(policy_path=policy_path, policy_payload=payload))

    if expected_code == "level_3_policy_stale":
        _patch_git_head(monkeypatch, "b" * 40, ancestor_pairs={("a" * 40, "b" * 40)})
    else:
        _patch_git_head(monkeypatch, "a" * 40)

    with pytest.raises(autonomy_ladder.AutonomyLadderError) as error:
        autonomy_ladder.assert_allowed(
            "publish_queue",
            level=3,
            action="human-approved posting preparation",
        )

    assert error.value.code == expected_code


def test_level_three_replacement_policy_missing_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_released_tree(monkeypatch, tmp_path)
    contract_path, policy_path = _write_released_policy_tree(tmp_path)
    policy_path.unlink()
    _patch_git_head(monkeypatch, "a" * 40)

    with pytest.raises(autonomy_ladder.AutonomyLadderError) as error:
        autonomy_ladder.load_contract()

    assert error.value.code == "level_3_policy_missing"


def test_level_three_replacement_policy_malformed_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_released_tree(monkeypatch, tmp_path)
    _write_released_policy_tree(
        tmp_path,
        malformed_policy_text="{not valid json",
    )
    _patch_git_head(monkeypatch, "a" * 40)

    with pytest.raises(autonomy_ladder.AutonomyLadderError) as error:
        autonomy_ladder.load_contract()

    assert error.value.code == "level_3_policy_malformed"


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
