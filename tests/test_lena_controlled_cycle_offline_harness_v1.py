"""Offline, real-code integration test for the controlled full-photo-autonomy cycle.

Drives the REAL controlled cycle end-to-end -- real strategy prep, real
standing-authorization issuance, real standing-autonomy generation
approval/claim/receipt lineage, real photo QA disposition wiring, real
clean-export, real queue admission code -- with ONLY the three genuine
external-effect seams stubbed:

  1. pipeline.higgsfield_lena_api_executor.run_live
        (the Higgsfield generation network call; spends credits for real)
  2. tools.lena_photo_qa_disposition_v1.call_anthropic_structured_visual_tool
        (the Anthropic visual-QA network call; spends credits for real)
  3. tools.lena_autopublish_approved_queue_v2_8._run_connector
        (the real Instagram / Facebook publisher subprocess; posts publicly)

No real provider call, no real Anthropic call, no real publish, ever.

This test necessarily operates against the real repository tree rather than
tmp_path: the strategy-prep subprocess chain
(tools/strategy/lena_run_strategy_autonomy_prep_v1.py and its ~10 sibling
tools) resolves recipe/wardrobe/pose/expression banks and prior learning
state relative to the repo root, not an injectable root. Rebuilding an
isolated synthetic equivalent of that whole chain (candidate gate, batch
builder, reconciliation, world/engagement state, etc.) would be materially
larger than the lineage gap this test exists to guard -- see
tests/fixtures/lena_retry_lineage.py for the scale such a synthetic rebuild
takes for just the retry sub-slice. Instead, this test uses a reserved,
clearly-fake date (2099-01-01) that can never collide with real production
usage, and unconditionally removes every artifact it creates in a fixture
teardown, whether the test passes or fails.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

import pipeline.higgsfield_lena_api_executor as executor
import pipeline.identity.lena_higgsfield_identity as identity
import tools.lena_autopublish_approved_queue_v2_8 as autopublish
import tools.lena_bounded_live_cycle_v1 as live_cycle
import tools.lena_full_photo_autonomy_v1 as autonomy
import tools.lena_photo_qa_disposition_v1 as photo_qa
import tools.lena_standing_autonomy_policy_v1 as standing_autonomy

ROOT = Path(__file__).resolve().parents[1]
TEST_DAY = "2099-01-01"

_DAY_SCOPED_PATHS = [
    ROOT / "pipeline/approvals/lena/bounded_live_cycles" / TEST_DAY,
    ROOT / "pipeline/approvals/lena/generation" / TEST_DAY,
    ROOT / "pipeline/approvals/lena/retry_generation" / TEST_DAY,
    ROOT / "pipeline/autonomy/lena/bounded_live_cycles" / TEST_DAY,
    ROOT / "pipeline/higgsfield_debug" / TEST_DAY,
    ROOT / "pipeline/higgsfield_library/lena" / TEST_DAY,
    ROOT / "pipeline/asset_review/lena/presence_output_qa" / TEST_DAY,
    ROOT / "pipeline/asset_review/lena/hpe_closure/presence_output_qa" / TEST_DAY,
    ROOT / "pipeline/publishing/lena/approved_queue_claims" / TEST_DAY,
    ROOT / "pipeline/publishing/lena/approved_queue_receipts" / TEST_DAY,
    ROOT / "pipeline/publishing/lena/dispatch_reports" / TEST_DAY,
    ROOT / "pipeline/publishing/lena/dispatch_outbox" / TEST_DAY,
    ROOT / "pipeline/strategy/lena/next_actions" / TEST_DAY,
    ROOT / "pipeline/strategy/lena/pre_generation_candidates" / TEST_DAY,
    ROOT / "pipeline/strategy/lena/content_packets" / TEST_DAY,
    ROOT / "pipeline/strategy/lena/reconciliations" / TEST_DAY,
]
_LOCK_PATH = ROOT / "pipeline/autonomy/lena/full_photo_autonomy" / f"{TEST_DAY}.lock"

# Not day-scoped: the world-state and engagement-demand strategy-prep steps
# each maintain a single rolling "latest state" file (see their policy
# artifacts' state_path) that every invocation overwrites regardless of which
# date was requested. Snapshot and restore these exactly, rather than delete,
# so a real production state file is never lost to a test run.
_ROLLING_STATE_PATHS = [
    ROOT / "pipeline/state/lena_world_state_v1.json",
    ROOT / "pipeline/state/lena_engagement_demand_state_v1.json",
]


def _remove_day_scoped_artifacts() -> None:
    for path in _DAY_SCOPED_PATHS:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    if _LOCK_PATH.exists():
        _LOCK_PATH.unlink()
    for qcsv in (ROOT / "pipeline/publishing/lena/approved_queue").glob(f"*{TEST_DAY}*"):
        qcsv.unlink()


@pytest.fixture
def clean_test_day():
    """Guarantee TEST_DAY is pristine before and after the test, pass or fail.

    Also snapshots and restores the two non-day-scoped rolling state files
    that strategy prep unconditionally overwrites on every invocation.
    """
    _remove_day_scoped_artifacts()
    snapshots: dict[Path, bytes | None] = {
        path: (path.read_bytes() if path.exists() else None) for path in _ROLLING_STATE_PATHS
    }
    (ROOT / "pipeline/autonomy/lena/bounded_live_cycles").mkdir(parents=True, exist_ok=True)
    try:
        yield TEST_DAY
    finally:
        _remove_day_scoped_artifacts()
        for path, original in snapshots.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)


def _fake_run_live(date_str, slot_id, source, custom_reference_id):
    buf = io.BytesIO()
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), (198, 168, 150)).save(buf, format="PNG")
    image_bytes = buf.getvalue()
    ext = executor._detect_image_extension(image_bytes)
    final_path = executor.library_path(date_str, slot_id, ext)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(image_bytes)
    return {
        "job_id": "harness-job-0001",
        "status": "completed",
        "result_urls": ["https://offline.harness.invalid/result.png"],
        "saved_image_path": str(final_path),
        "image_format_detected": ext,
        "subprocess_start_attempted": True,
        "provider_submission_may_have_occurred": True,
    }


def _fake_anthropic_tool(*, images, system_prompt, user_text, tool_name,
                          tool_schema, provider, model, timeout_seconds, max_tokens):
    observations = {
        key: {"status": "pass", "reason_codes": [], "notes": "offline harness: pass"}
        for key in photo_qa.VISUAL_OBSERVATION_KEYS
    }
    return {"schema_version": photo_qa.VISUAL_SCHEMA_VERSION, "observations": observations}


def _fake_run_connector(row, *, dry_run=False):
    payload = autopublish._connector_payload(row)
    outbox = autopublish.DISPATCH_OUTBOX / row.get("date", "")
    outbox.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in row.get("platform", "platform"))
    payload_path = outbox / f"{row.get('queue_id')}_{safe}_payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "ok": True,
        "posted": True,
        "post_id": "harness-post-0001",
        "post_url": "https://offline.harness.invalid/p/harness-post-0001",
        "posted_at": f"{TEST_DAY}T15:00:00Z",
        "payload": str(payload_path),
        "returncode": 0,
        "connector": row.get("connector_path", ""),
    }


def test_controlled_cycle_reaches_provider_boundary_with_real_lineage(
    clean_test_day, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real controlled hcr_012/wc_p050 cycle, offline, with only the three
    genuine external-effect seams stubbed. Proves the standing-autonomy
    generation approval/claim/receipt lineage is issued and consumed without
    any human/manual approval artifact, and that the cycle reaches (and
    passes through) the stubbed provider boundary rather than dying earlier
    on a lineage mismatch.
    """
    monkeypatch.setattr(executor, "run_live", _fake_run_live)
    monkeypatch.setattr(photo_qa, "call_anthropic_structured_visual_tool", _fake_anthropic_tool)
    monkeypatch.setattr(autopublish, "_run_connector", _fake_run_connector)

    report = autonomy.run_controlled_cycle(day=TEST_DAY, schedule_slot="morning")

    assert report.get("provider_calls_performed", 0) >= 1, (
        f"cycle never reached the stubbed provider boundary: {report.get('failure')}"
    )
    assert report.get("failed_stage") != "provider_generation" or report.get("ok") is True, (
        f"cycle failed inside provider_generation (lineage bug): {report.get('failure')}"
    )

    approval_dir = ROOT / "pipeline/approvals/lena/generation" / TEST_DAY
    approval_files = list(approval_dir.glob("*_higgsfield_standing_autonomy_generation_approval.json"))
    assert approval_files, "no standing-autonomy generation approval artifact was written"
    approval_record = json.loads(approval_files[0].read_text(encoding="utf-8"))
    assert approval_record["authorization_identity_mode"] == "standing_autonomy_policy"
    assert approval_record["operator_id"] == standing_autonomy.AUTHORIZATION_ISSUER
    assert approval_record["operator_id"] != "nicolas"

    claim_files = list(approval_dir.glob("*_higgsfield_generation_claim.json"))
    assert claim_files, "no generation claim artifact was written"
    claim_record = json.loads(claim_files[0].read_text(encoding="utf-8"))
    assert claim_record["report_type"] == "lena_higgsfield_standing_autonomy_generation_claim"
    assert claim_record["operator_id"] == standing_autonomy.AUTHORIZATION_ISSUER

    assert report.get("publish_performed") in (True, None)
    if report.get("ok") is True:
        assert report.get("publish_performed") is True
        assert report.get("queue_mutated") is True


def test_manual_approval_validator_still_rejects_standing_autonomy_shaped_record(
    clean_test_day,
) -> None:
    """The manual, human-only validator must keep rejecting anything that
    isn't a genuine manually-issued approval -- including a well-formed
    standing-autonomy record -- with the exact same error as before this
    change (no weakening of the manual path).
    """
    import tools.lena_higgsfield_generation_approval_v1 as canonical_approval
    import tools.lena_higgsfield_standing_autonomy_generation_approval_v1 as standing_generation_approval

    forged = {
        "report_type": standing_generation_approval.APPROVAL_REPORT_TYPE,
        "schema_version": standing_generation_approval.APPROVAL_SCHEMA_VERSION,
        "approval_type": standing_generation_approval.APPROVAL_TYPE,
        "operator_id": "lena_autonomy_controller",
        "authorization_identity_mode": "standing_autonomy_policy",
    }
    forged_path = ROOT / "pipeline/approvals/lena/generation" / TEST_DAY / "forged_manual_approval.json"
    forged_path.parent.mkdir(parents=True, exist_ok=True)
    forged_path.write_text(json.dumps(forged, indent=2), encoding="utf-8")

    with pytest.raises(canonical_approval.HiggsfieldGenerationApprovalError) as exc_info:
        canonical_approval.validate_generation_approval_artifact(forged_path, require_not_expired=False)
    assert exc_info.value.code == "approval_report_type_mismatch"


def test_standing_autonomy_validator_rejects_cross_lane_recipe(clean_test_day) -> None:
    """A well-formed standing-autonomy approval whose bound recipe is outside
    hcr_012 must fail closed -- proves cross-lane substitution is caught.
    """
    import tools.lena_higgsfield_standing_autonomy_generation_approval_v1 as standing_generation_approval

    forged = {
        "report_type": standing_generation_approval.APPROVAL_REPORT_TYPE,
        "schema_version": standing_generation_approval.APPROVAL_SCHEMA_VERSION,
        "approval_type": standing_generation_approval.APPROVAL_TYPE,
        "operator_id": "lena_autonomy_controller",
        "authorization_identity_mode": "standing_autonomy_policy",
        "approved_at_utc": f"{TEST_DAY}T00:00:00+00:00",
        "expires_at_utc": f"{TEST_DAY}T00:30:00+00:00",
        "date": TEST_DAY,
        "slot_id": "some-slot",
        "recipe_id": "hcr_999",
        "wardrobe_outfit_id": "wc_p050",
        "credits_may_be_spent_acknowledged": True,
        "authorized_attempts": 1,
        "upload_authorized": False,
        "queue_promotion_authorized": False,
        "publish_authorized": False,
        "scheduling_authorized": False,
        "analytics_mutation_authorized": False,
    }
    forged_path = ROOT / "pipeline/approvals/lena/generation" / TEST_DAY / "cross_lane.json"
    forged_path.parent.mkdir(parents=True, exist_ok=True)
    forged_path.write_text(json.dumps(forged, indent=2), encoding="utf-8")

    with pytest.raises(standing_generation_approval.HiggsfieldStandingAutonomyGenerationApprovalError) as exc_info:
        standing_generation_approval.validate_standing_autonomy_generation_approval_artifact(
            forged_path, require_not_expired=False
        )
    assert exc_info.value.code == "approval_recipe_invalid"


def test_standing_autonomy_validator_rejects_missing_approval_artifact(clean_test_day) -> None:
    import tools.lena_higgsfield_standing_autonomy_generation_approval_v1 as standing_generation_approval

    missing_path = ROOT / "pipeline/approvals/lena/generation" / TEST_DAY / "does_not_exist.json"
    with pytest.raises(standing_generation_approval.HiggsfieldStandingAutonomyGenerationApprovalError):
        standing_generation_approval.validate_standing_autonomy_generation_approval_artifact(
            missing_path, require_not_expired=False
        )
