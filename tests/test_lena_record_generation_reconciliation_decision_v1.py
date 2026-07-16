from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE = importlib.import_module("tools.strategy.lena_record_generation_reconciliation_decision_v1")

DATE = "2026-07-15"
SOURCE_REVISION = "d07fcbf3"
SOURCE_REVISION_COMMIT = "d07fcbf37b1e383ae0c68694c4a1d2a0b921838d"
RECOMMENDATION_RECIPE_ID = "hcr_011"
SELECTED_RECIPE_ID = "hcr_006"
SLOT_ID = "lenagate20260715d07fcbf3-pack000-00-photo"
SELECTED_CANDIDATE_ID = f"{SLOT_ID}::{SELECTED_RECIPE_ID}::cbn_004"
SELECTED_PROMPT_SHA256 = hashlib.sha256(b"selected-candidate-prompt").hexdigest()
OPERATOR_ID = "operator_01"
EXPECTED_CONFIRMATION = (
    f"I approve reconciling Lena recommendation {RECOMMENDATION_RECIPE_ID} "
    f"to selected candidate {SELECTED_RECIPE_ID} "
    f"for slot {SLOT_ID}. "
    "This decision authorizes handoff preparation only and does not authorize live generation or publishing."
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _patch_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "DECISIONS_ROOT", tmp_path / "pipeline" / "strategy" / "lena" / "reconciliation_decisions")


def _materialize_sources(tmp_path: Path) -> dict[str, Path]:
    learning_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_post_outcome_learning_state_{DATE}.json"
    recommendation_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / DATE / f"lena_next_generation_step_{DATE}.json"
    candidate_path = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates" / DATE / "lena_pre_generation_candidate_d07fcbf3_53ba138728e8.json"

    _write_json(
        learning_path,
        {
            "report_type": "lena_post_outcome_learning_state",
            "schema_version": "v1",
            "date": DATE,
            "learning_status": "current",
        },
    )
    _write_json(
        recommendation_path,
        {
            "report_type": "lena_next_generation_step",
            "schema_version": "v1",
            "date": DATE,
            "recommendation": {
                "recommended_recipe_id": RECOMMENDATION_RECIPE_ID,
                "recommended_outfit_id": "wc_p059",
                "recommended_environment_id": "env_p001",
                "action_type": "collect_first_controlled_proof",
            },
        },
    )
    _write_json(
        candidate_path,
        {
            "schema_version": "lena_pre_generation_candidate_gate_v1",
            "influencer_id": "lena",
            "as_of_date": DATE,
            "authority_commit": SOURCE_REVISION_COMMIT,
            "candidate_status": "selected",
            "candidate": {
                "candidate_id": SELECTED_CANDIDATE_ID,
                "slot_id": SLOT_ID,
                "lane": "parking_garage_flash",
                "recipe_id": SELECTED_RECIPE_ID,
                "hook_id": "cbn_004",
                "prompt_sha256": SELECTED_PROMPT_SHA256,
                "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {DATE} --slot-id {SLOT_ID}",
            },
            "decision_fingerprint_sha256": "5" * 64,
            "generated_at_utc": "2026-07-15T12:34:57Z",
            "provider_authorized": False,
            "side_effects_performed": [],
        },
    )
    return {
        "learning": learning_path,
        "recommendation": recommendation_path,
        "selected_candidate": candidate_path,
    }


def _build_reconciliation_payload(
    tmp_path: Path,
    *,
    selected_recipe_id: str = SELECTED_RECIPE_ID,
    selected_candidate_id: str = SELECTED_CANDIDATE_ID,
    selected_slot_id: str = SLOT_ID,
    reconciliation_status: str = "operator_review_required",
    operator_review_required: bool = True,
    divergence_status: str = "recipe_mismatch",
    resolution_policy: str = "explicit_operator_reconciliation_required",
    source_reconciliation_sha256: str | None = None,
    final_reconciled_candidate_id: str | None = None,
    final_reconciled_candidate_recipe_id: str | None = None,
    final_reconciled_candidate_slot_id: str | None = None,
) -> tuple[Path, dict, dict[str, Path]]:
    sources = _materialize_sources(tmp_path)
    learning_sha = MODULE.sha256_file(sources["learning"])
    recommendation_sha = MODULE.sha256_file(sources["recommendation"])
    candidate_sha = MODULE.sha256_file(sources["selected_candidate"])
    reconciliation_path = tmp_path / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE / "lena_generation_reconciliation_fixture.json"
    payload = {
        "report_type": "lena_generation_reconciliation",
        "schema_version": "lena_generation_reconciliation_v1",
        "date": DATE,
        "source_artifacts": {
            "learning": {
                "source_artifact_path": sources["learning"].relative_to(tmp_path).as_posix(),
                "source_artifact_sha256": learning_sha,
            },
            "recommendation": {
                "source_artifact_path": sources["recommendation"].relative_to(tmp_path).as_posix(),
                "source_artifact_sha256": recommendation_sha,
            },
            "selected_candidate": {
                "source_artifact_path": sources["selected_candidate"].relative_to(tmp_path).as_posix(),
                "source_artifact_sha256": candidate_sha,
            },
        },
        "learning_status": "current",
        "recommendation_recipe_id": RECOMMENDATION_RECIPE_ID,
        "recommendation_outfit_id": "wc_p059",
        "recommendation_environment_id": "env_p001",
        "recommendation_action_type": "collect_first_controlled_proof",
        "selected_candidate_id": selected_candidate_id,
        "selected_candidate_recipe_id": selected_recipe_id,
        "selected_candidate_slot_id": selected_slot_id,
        "selected_candidate_hook_id": "cbn_004",
        "selected_candidate_prompt_sha256": SELECTED_PROMPT_SHA256,
        "divergence_status": divergence_status,
        "resolution_policy": resolution_policy,
        "reconciliation_status": reconciliation_status,
        "operator_review_required": operator_review_required,
        "final_reconciled_candidate_id": final_reconciled_candidate_id,
        "final_reconciled_candidate_recipe_id": final_reconciled_candidate_recipe_id,
        "final_reconciled_candidate_slot_id": final_reconciled_candidate_slot_id,
    }
    if source_reconciliation_sha256 is not None:
        payload["source_reconciliation_artifact_sha256"] = source_reconciliation_sha256
    _write_json(reconciliation_path, payload)
    return reconciliation_path, payload, sources


def _fixed_now() -> datetime:
    return datetime(2026, 7, 15, 12, 34, 56, tzinfo=timezone.utc)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_operator_decision_records_authority_and_reuses_identical_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, _ = _build_reconciliation_payload(tmp_path)
    monkeypatch.setattr(MODULE, "iso_now", _fixed_now)

    report = MODULE.build_generation_reconciliation_decision(
        str(reconciliation_path),
        OPERATOR_ID,
        SELECTED_CANDIDATE_ID,
        SELECTED_RECIPE_ID,
        SLOT_ID,
        EXPECTED_CONFIRMATION,
    )
    path, written, reused = MODULE.write_report(report, DATE)
    second_path, second_written, second_reused = MODULE.write_report(report, DATE)

    assert report["report_type"] == "lena_generation_reconciliation_decision"
    assert report["schema_version"] == "lena_generation_reconciliation_decision_v1"
    assert report["date"] == DATE
    assert report["generated_at_utc"] == "2026-07-15T12:34:56+00:00"
    assert report["expires_at_utc"] == "2026-07-15T13:04:56+00:00"
    assert report["operator_id"] == OPERATOR_ID
    assert report["source_reconciliation_artifact_path"].endswith("pipeline/strategy/lena/reconciliations/2026-07-15/lena_generation_reconciliation_fixture.json")
    assert report["source_reconciliation_artifact_sha256"] == MODULE.sha256_file(reconciliation_path)
    assert report["selected_candidate_id"] == SELECTED_CANDIDATE_ID
    assert report["selected_recipe_id"] == SELECTED_RECIPE_ID
    assert report["selected_slot_id"] == SLOT_ID
    assert report["selected_prompt_sha256"] == SELECTED_PROMPT_SHA256
    assert report["divergence_status"] == "recipe_mismatch"
    assert report["resolution_policy"] == "explicit_operator_reconciliation_required"
    assert report["confirmation_phrase"] == EXPECTED_CONFIRMATION
    assert report["confirmation_phrase_sha256"] == hashlib.sha256(EXPECTED_CONFIRMATION.encode("utf-8")).hexdigest()
    assert report["final_reconciled_candidate_id"] == SELECTED_CANDIDATE_ID
    assert report["final_reconciled_recipe_id"] == SELECTED_RECIPE_ID
    assert report["final_reconciled_slot_id"] == SLOT_ID
    assert report["authority_scope"] == "handoff_preparation_only"
    assert report["live_generation_authorized"] is False
    assert report["publishing_authorized"] is False
    assert report["exact_next_allowed_action"] == "build_next_live_image_handoff"
    assert report["decision_identity_sha256"] == report["decision_id"]
    assert report["side_effect_flags"] == {
        "provider_call_performed": False,
        "generation_performed": False,
        "live_generation_authorized": False,
        "publishing_authorized": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "queue_mutated": False,
        "publish_performed": False,
    }
    assert path == second_path
    assert written["decision_id"] == second_written["decision_id"]
    assert reused is False
    assert second_reused is True
    assert path == tmp_path / "pipeline" / "strategy" / "lena" / "reconciliation_decisions" / DATE / f"lena_generation_reconciliation_decision_{report['decision_id'][:12]}.json"
    assert _read_json(path) == report
    assert len(list((tmp_path / "pipeline" / "strategy" / "lena" / "reconciliation_decisions" / DATE).glob("*.json"))) == 1


@pytest.mark.parametrize(
    ("selected_candidate_id", "selected_recipe_id", "selected_slot_id", "error_code"),
    [
        ("wrong-candidate", SELECTED_RECIPE_ID, SLOT_ID, "selected_candidate_mismatch"),
        (SELECTED_CANDIDATE_ID, "hcr_999", SLOT_ID, "selected_recipe_mismatch"),
        (SELECTED_CANDIDATE_ID, SELECTED_RECIPE_ID, "wrong-slot", "selected_slot_mismatch"),
    ],
)
def test_selection_fields_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selected_candidate_id: str,
    selected_recipe_id: str,
    selected_slot_id: str,
    error_code: str,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, _ = _build_reconciliation_payload(tmp_path)

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            selected_candidate_id,
            selected_recipe_id,
            selected_slot_id,
            EXPECTED_CONFIRMATION,
        )

    assert exc.value.code == error_code


@pytest.mark.parametrize(
    ("confirmation", "error_code"),
    [
        ("wrong phrase", "confirmation_phrase_mismatch"),
        (EXPECTED_CONFIRMATION + " extra", "confirmation_phrase_mismatch"),
    ],
)
def test_confirmation_phrase_must_match_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
    error_code: str,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, _ = _build_reconciliation_payload(tmp_path)

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            confirmation,
        )

    assert exc.value.code == error_code


@pytest.mark.parametrize(
    ("reconciliation_status", "operator_review_required", "divergence_status", "error_code"),
    [
        ("reconciled", False, "aligned", "reconciliation_status_invalid"),
        ("operator_review_required", True, "aligned", "reconciliation_already_aligned"),
        ("operator_review_required", False, "recipe_mismatch", "reconciliation_not_operator_reviewable"),
    ],
)
def test_status_and_alignment_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reconciliation_status: str,
    operator_review_required: bool,
    divergence_status: str,
    error_code: str,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, _ = _build_reconciliation_payload(
        tmp_path,
        reconciliation_status=reconciliation_status,
        operator_review_required=operator_review_required,
        divergence_status=divergence_status,
    )

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )

    assert exc.value.code == error_code


def test_reconciliation_sha_drift_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, payload, _ = _build_reconciliation_payload(
        tmp_path,
        source_reconciliation_sha256="0" * 64,
    )

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )

    assert exc.value.code == "reconciliation_sha_mismatch"
    assert payload["source_reconciliation_artifact_sha256"] == "0" * 64


def test_present_and_correct_reconciliation_sha_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, payload, _ = _build_reconciliation_payload(tmp_path)
    payload["source_reconciliation_artifact_sha256"] = MODULE._reconciliation_source_sha(payload)
    _write_json(reconciliation_path, payload)

    report = MODULE.build_generation_reconciliation_decision(
        str(reconciliation_path),
        OPERATOR_ID,
        SELECTED_CANDIDATE_ID,
        SELECTED_RECIPE_ID,
        SLOT_ID,
        EXPECTED_CONFIRMATION,
    )

    assert report["source_reconciliation_artifact_sha256"] == MODULE.sha256_file(reconciliation_path)
    assert report["decision_identity_sha256"] == report["decision_id"]


@pytest.mark.parametrize("artifact_key", ["recommendation", "selected_candidate"])
def test_source_artifact_drift_for_recommendation_and_candidate_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_key: str,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, sources = _build_reconciliation_payload(tmp_path)
    target = sources[artifact_key]
    payload = _read_json(target)
    if artifact_key == "recommendation":
        payload["recommendation"]["recommended_recipe_id"] = "hcr_999"
    else:
        payload["candidate"]["recipe_id"] = "hcr_999"
    _write_json(target, payload)

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )

    assert exc.value.code == "source_artifact_drift"


@pytest.mark.parametrize(
    ("mutator", "error_code"),
    [
        (
            lambda payload: payload.update(
                {
                    "final_reconciled_candidate_id": SELECTED_CANDIDATE_ID,
                    "final_reconciled_candidate_recipe_id": SELECTED_RECIPE_ID,
                    "final_reconciled_candidate_slot_id": SLOT_ID,
                }
            ),
            "reconciliation_already_resolved",
        ),
        (lambda payload: payload.update({"operator_review_required": True, "selected_candidate_recipe_id": "hcr_007"}), "selected_recipe_mismatch"),
    ],
)
def test_missing_or_tampered_reconciliation_data_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator,
    error_code: str,
) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, payload, _ = _build_reconciliation_payload(tmp_path)
    mutator(payload)
    _write_json(reconciliation_path, payload)

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )

    assert exc.value.code == error_code


def test_path_escape_and_malformed_json_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    malformed = tmp_path / "pipeline" / "strategy" / "lena" / "reconciliations" / DATE / "bad.json"
    _write_text(malformed, "{")
    with pytest.raises(MODULE.ReconciliationDecisionError) as malformed_exc:
        MODULE.build_generation_reconciliation_decision(
            str(malformed),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )
    assert malformed_exc.value.code == "malformed_json"

    escape_path = tmp_path / "outside.json"
    _write_json(escape_path, {"report_type": "lena_generation_reconciliation", "schema_version": "lena_generation_reconciliation_v1"})
    with pytest.raises(MODULE.ReconciliationDecisionError) as escape_exc:
        MODULE.build_generation_reconciliation_decision(
            str(Path("..") / "outside.json"),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )
    assert escape_exc.value.code == "repository_path_invalid"


def test_invalid_operator_and_expiration_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, _ = _build_reconciliation_payload(tmp_path)

    with pytest.raises(MODULE.ReconciliationDecisionError) as operator_exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            " ",
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
        )
    assert operator_exc.value.code == "operator_id_invalid"

    with pytest.raises(MODULE.ReconciliationDecisionError) as expires_exc:
        MODULE.build_generation_reconciliation_decision(
            str(reconciliation_path),
            OPERATOR_ID,
            SELECTED_CANDIDATE_ID,
            SELECTED_RECIPE_ID,
            SLOT_ID,
            EXPECTED_CONFIRMATION,
            expires_at="2026-07-15T12:00:00+00:00",
        )
    assert expires_exc.value.code == "decision_expiration_invalid"


def test_conflicting_second_decision_for_same_reconciliation_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_layout(monkeypatch, tmp_path)
    reconciliation_path, _, _ = _build_reconciliation_payload(tmp_path)
    monkeypatch.setattr(MODULE, "iso_now", _fixed_now)

    report = MODULE.build_generation_reconciliation_decision(
        str(reconciliation_path),
        OPERATOR_ID,
        SELECTED_CANDIDATE_ID,
        SELECTED_RECIPE_ID,
        SLOT_ID,
        EXPECTED_CONFIRMATION,
    )
    MODULE.write_report(report, DATE)

    conflicting = copy.deepcopy(report)
    conflicting["confirmation_phrase"] = EXPECTED_CONFIRMATION + " conflict"
    conflicting["confirmation_phrase_sha256"] = hashlib.sha256(conflicting["confirmation_phrase"].encode("utf-8")).hexdigest()
    conflicting["decision_identity_sha256"] = hashlib.sha256(b"different").hexdigest()
    conflicting["decision_id"] = conflicting["decision_identity_sha256"]

    with pytest.raises(MODULE.ReconciliationDecisionError) as exc:
        MODULE.write_report(conflicting, DATE)

    assert exc.value.code == "decision_identity_conflict"


def test_module_is_report_only_and_does_not_import_live_executor_or_approval_modules() -> None:
    source = Path(MODULE.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_roots = {
        "pipeline.higgsfield_lena_api_executor",
        "tools.lena_higgsfield_generation_approval_v1",
        "tools.strategy.lena_execute_approved_live_generation_v1",
        "tools.lena_photo_qa_disposition_v1",
        "tools.strategy.lena_run_generated_asset_qa_v1",
        "tools.strategy.lena_prepare_higgsfield_retry_handoff_v1",
        "tools.strategy.lena_execute_retry_decision_v1",
    }

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert forbidden_roots.isdisjoint(imported)
