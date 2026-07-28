from __future__ import annotations

import contextlib
import hashlib
import io
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

import pipeline.lena_publish_quality_gate as qg_mod
import tools.lena_governed_publish_pipeline_v1 as gpp
import tools.lena_reels_live_preflight_readonly as preflight_mod
from pipeline.publisher import instagram_graph_adapter

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")


# ---------------------------------------------------------------------------
# Hard structural guarantees for this entire file:
#   - zero real network calls (requests.request / Session.request raise, and
#     the raise is recorded BEFORE it fires so the teardown assert catches
#     it even if application code swallows the exception somewhere)
#   - the real .env on this machine (which holds real Instagram/R2
#     credentials) is never loaded into the test process's environment
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network_no_real_env(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[tuple, dict]] = []

    def _blocked(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError(f"network call attempted during test: args={args} kwargs={kwargs}")

    monkeypatch.setattr(requests, "request", _blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
    monkeypatch.setattr("pipeline.env_loader.load_env_once", lambda *a, **k: {})
    monkeypatch.setattr("pipeline.env_loader.load_env", lambda *a, **k: {})

    yield calls
    assert calls == [], f"network calls were attempted during this test: {calls}"


# ---------------------------------------------------------------------------
# Root isolation: every real-repo-state path this module touches (caption
# bank, blocked-terms file, publish state/logs, asset-review scan roots,
# standing-authorization file, execution-claim directory) is redirected
# under tmp_path. No test in this file reads or writes anything under the
# real repo's pipeline/ tree.
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "outputs").mkdir(parents=True)
    (repo_root / "pipeline" / "publish_logs").mkdir(parents=True)
    (repo_root / "pipeline" / "asset_review").mkdir(parents=True)
    monkeypatch.setattr(gpp, "REPO_ROOT", repo_root)

    bank_path = tmp_path / "caption_bank.json"
    blocked_path = tmp_path / "blocked_terms.json"
    blocked_path.write_text(
        json.dumps({"blocked_public_terms": ["aiwatermark", "syntheticmedia"]}), encoding="utf-8"
    )
    monkeypatch.setattr(gpp, "CAPTION_BANK_PATH", bank_path)
    monkeypatch.setattr(gpp, "BLOCKED_TERMS_PATH", blocked_path)

    lane_root = tmp_path / "lane_autonomy"
    monkeypatch.setattr(gpp, "LANE_AUTONOMY_ROOT", lane_root)
    monkeypatch.setattr(gpp, "LANE_AUTONOMY_CLAIM_ROOT", lane_root / "claims")
    monkeypatch.setattr(
        gpp, "STANDING_AUTHORIZATION_PATH",
        lane_root / "lena_reels_standing_lane_autonomy_authorization.json",
    )

    fake_qg_config = qg_mod.QualityGateConfig(
        publish_state_path=tmp_path / "quality_gate_state.json",
        publish_logs_dir=tmp_path / "quality_gate_logs",
    )
    monkeypatch.setattr(qg_mod, "QualityGateConfig", lambda *a, **k: fake_qg_config)

    return tmp_path


def _write_bank(bank_path: Path, entries: list[dict]) -> None:
    bank_path.write_text(json.dumps({"version": "v1", "captions": entries}, indent=2), encoding="utf-8")


def _default_bank_entries(n_available: int = 3) -> list[dict]:
    entries = [{"id": "cb_used", "text": "already used caption", "status": "used"}]
    for i in range(n_available):
        entries.append({"id": f"cb_avail_{i}", "text": f"available caption number {i}", "status": "available"})
    return entries


def _make_source_video(path: Path, duration: float = 2.0, width: int = 640, height: int = 1136) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=24",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True, capture_output=True, timeout=60,
    )
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSTAGRAM_GRAPH_ACCESS_TOKEN", "fake-test-token")
    monkeypatch.setenv("INSTAGRAM_GRAPH_USER_ID", "fake-test-igid")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "fake")
    monkeypatch.setenv("R2_ACCOUNT_ID", "fake")
    monkeypatch.setenv("R2_BUCKET_NAME", "fake")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://fake.example.com")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "fake")


def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "INSTAGRAM_GRAPH_ACCESS_TOKEN", "META_INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_GRAPH_USER_ID", "META_IG_USER_ID",
        "R2_ACCESS_KEY_ID", "R2_ACCOUNT_ID", "R2_BUCKET_NAME",
        "R2_PUBLIC_BASE_URL", "R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_passing_status_sidecar(asset_dir: Path, stem: str, **overrides) -> Path:
    """The new mandatory production-QA / HPE-proof gate reads this sidecar.
    Tests that need a publish-eligible asset must write one with both
    fields literally True."""
    payload = {"production_qa_passed": True, "hpe_proof_verified": True}
    payload.update(overrides)
    sidecar_path = asset_dir / f"{stem}.status.json"
    sidecar_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar_path


@pytest.fixture
def valid_asset(isolated_roots: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A complete, real (not fabricated) valid asset: a real ffmpeg-produced
    source video, real scrub + clean-export verification exercised through
    the actual (unmodified) stage functions, a caption bank with an
    eligible caption, fake-but-present credentials, a passing production-QA
    / HPE-proof sidecar, no duplicate markers."""
    _set_fake_credentials(monkeypatch)
    asset_dir = isolated_roots / "asset_review" / "reel_asset_one"
    source = _make_source_video(asset_dir / "reel_asset_one_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(3))
    sidecar = _write_passing_status_sidecar(asset_dir, "reel_asset_one_review")
    return {"asset_dir": asset_dir, "source": source, "sidecar": sidecar}


def _claim_files(claim_root: Path) -> list[Path]:
    return list(claim_root.glob("*.claim.json")) if claim_root.exists() else []


def _claim(slot_id: str = "recovery-slot", **overrides) -> dict:
    kwargs = dict(
        asset_dir=Path("/tmp/recovery_asset"), source_path=Path("/tmp/recovery_asset/src.mp4"),
        source_sha256="a" * 64, caption_bank_id="cb1", caption_text="hello caption",
        fingerprint="b" * 64, approval_mode="autonomous",
    )
    kwargs.update(overrides)
    return gpp.claim_execution(slot_id, **kwargs)


def _run_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["lena_governed_publish_pipeline_v1.py", *argv])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = gpp.main()
    return exit_code, buf.getvalue()


# Module-level (not nested) so multiprocessing's fork start method can run it
# directly in the child process. Relies on the parent's monkeypatched
# gpp.LANE_AUTONOMY_CLAIM_ROOT being inherited via the OS fork() copy of the
# whole process image -- no re-patching needed in the child.
def _mp_claim_worker(slot_id: str, results_dir: str) -> None:
    try:
        gpp.claim_execution(
            slot_id,
            asset_dir=Path("/tmp/mp_asset"), source_path=Path("/tmp/mp_asset/src.mp4"),
            source_sha256="a" * 64, caption_bank_id="cb1", caption_text="hello",
            fingerprint="b" * 64, approval_mode="manual",
        )
        outcome = "ok"
    except gpp.PipelineError:
        outcome = "rejected"
    except Exception as exc:  # pragma: no cover - diagnostic aid only
        outcome = f"error:{exc}"
    Path(results_dir, f"{os.getpid()}.result").write_text(outcome, encoding="utf-8")


# === 0. Structural: this module stays independent of the photo lane =========

def test_module_does_not_import_photo_lane_modules() -> None:
    source_text = Path(gpp.__file__).read_text(encoding="utf-8")
    for token in ("lena_bounded_live_cycle", "lena_standing_autonomy_policy", "lena_higgsfield_generation_approval"):
        assert token not in source_text, f"lena_governed_publish_pipeline_v1.py must not couple to photo-lane module {token!r}"


# === 1. Standing Reels-lane autonomy authorization ==========================

def test_autonomous_mode_blocked_without_any_standing_authorization(isolated_roots: Path, valid_asset: dict) -> None:
    with pytest.raises(gpp.PipelineError, match="no standing Reels lane-autonomy authorization exists"):
        gpp.run_publish(valid_asset["asset_dir"], "autonomous")
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []


@requires_ffmpeg
def test_autonomous_mode_blocked_with_nonexistent_standing_authorization_path(valid_asset: dict) -> None:
    fake_path = gpp.LANE_AUTONOMY_ROOT / "does_not_exist.json"
    with pytest.raises(gpp.PipelineError, match="no standing Reels lane-autonomy authorization exists"):
        gpp.run_publish(valid_asset["asset_dir"], "autonomous", standing_authorization_artifact=fake_path)
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []


def test_issue_and_validate_standing_authorization_roundtrip(isolated_roots: Path) -> None:
    issued = gpp.issue_standing_lane_autonomy_authorization(ttl_seconds=600)
    assert issued["revoked"] is False
    assert gpp.STANDING_AUTHORIZATION_PATH.exists()

    validated = gpp.validate_standing_lane_autonomy_authorization()
    assert validated["authorization_mode"] == gpp.STANDING_AUTONOMY_MODE
    assert validated["report_type"] == gpp.STANDING_AUTONOMY_REPORT_TYPE


def test_issue_refuses_to_overwrite_existing_authorization_without_force(isolated_roots: Path) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    with pytest.raises(gpp.PipelineError, match="already exists"):
        gpp.issue_standing_lane_autonomy_authorization()
    gpp.issue_standing_lane_autonomy_authorization(force=True)  # must not raise


def test_standing_authorization_ttl_exceeding_max_rejected_at_issuance(isolated_roots: Path) -> None:
    with pytest.raises(gpp.PipelineError, match="ttl_seconds"):
        gpp.issue_standing_lane_autonomy_authorization(ttl_seconds=gpp.STANDING_AUTONOMY_MAX_TTL_SECONDS + 1)


def test_revoke_standing_authorization_blocks_future_validation(isolated_roots: Path) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    gpp.validate_standing_lane_autonomy_authorization()  # sanity: valid before revoke

    revoked = gpp.revoke_standing_lane_autonomy_authorization()
    assert revoked["revoked"] is True
    with pytest.raises(gpp.PipelineError, match="revoked"):
        gpp.validate_standing_lane_autonomy_authorization()


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda a: a.update(revoked=True), "revoked"),
        (lambda a: a.update(kill_switch_enabled=False), "kill_switch_enabled"),
        (lambda a: a.update(platform="Facebook Page"), "platform"),
        (lambda a: a.update(report_type="something_else"), "report_type"),
        (lambda a: a.update(schema_version="v2"), "schema_version"),
        (lambda a: a.update(authorization_mode="manual_override"), "authorization_mode"),
        (lambda a: a.update(authorization_issuer="someone_else"), "authorization_issuer"),
    ],
)
def test_tampered_standing_authorization_rejected(isolated_roots: Path, mutate, match: str) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    data = json.loads(gpp.STANDING_AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    mutate(data)
    gpp.STANDING_AUTHORIZATION_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(gpp.PipelineError, match=match):
        gpp.validate_standing_lane_autonomy_authorization()


def test_standing_authorization_future_issued_at_rejected(isolated_roots: Path) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    data = json.loads(gpp.STANDING_AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    future = datetime.now(timezone.utc) + timedelta(days=1)
    data["issued_at_utc"] = future.isoformat().replace("+00:00", "Z")
    gpp.STANDING_AUTHORIZATION_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(gpp.PipelineError, match="future"):
        gpp.validate_standing_lane_autonomy_authorization()


def test_expired_standing_authorization_rejected(isolated_roots: Path) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    data = json.loads(gpp.STANDING_AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    issued = datetime.now(timezone.utc) - timedelta(days=40)
    data["issued_at_utc"] = issued.isoformat().replace("+00:00", "Z")
    data["expires_at_utc"] = (issued + timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    gpp.STANDING_AUTHORIZATION_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(gpp.PipelineError, match="expired"):
        gpp.validate_standing_lane_autonomy_authorization()


def test_standing_authorization_excessive_ttl_rejected_at_validation_even_if_tampered(isolated_roots: Path) -> None:
    gpp.issue_standing_lane_autonomy_authorization(ttl_seconds=600)
    data = json.loads(gpp.STANDING_AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    issued = datetime.now(timezone.utc) - timedelta(seconds=1)
    data["issued_at_utc"] = issued.isoformat().replace("+00:00", "Z")
    data["expires_at_utc"] = (
        issued + timedelta(seconds=gpp.STANDING_AUTONOMY_MAX_TTL_SECONDS + 3600)
    ).isoformat().replace("+00:00", "Z")
    gpp.STANDING_AUTHORIZATION_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(gpp.PipelineError, match="TTL exceeds"):
        gpp.validate_standing_lane_autonomy_authorization()


@requires_ffmpeg
def test_standing_authorization_reusable_across_multiple_assets_not_single_use(
    isolated_roots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This is the core behavioral change from Phase 3: one standing
    authorization must survive and remain valid across multiple, different
    assets' successful publishes -- it is durable and lane-level, not
    single-use or asset-specific."""
    gpp.issue_standing_lane_autonomy_authorization()
    _set_fake_credentials(monkeypatch)
    monkeypatch.setattr(
        instagram_graph_adapter, "publish_post",
        lambda payload: {"ok": True, "instagram_media_id": f"id_{payload['post_id']}", "permalink": "https://instagram.com/reel/x/"},
    )
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(5))

    for i in range(2):
        asset_dir = isolated_roots / "asset_review" / f"reel_asset_multi_{i}"
        # duration varies per asset so the two clean derivatives are not
        # byte-identical (ffmpeg's synthetic testsrc is fully deterministic
        # given the same params) -- otherwise the duplicate-fingerprint gate
        # would correctly, but confusingly for this test, treat the second
        # "different" asset as a re-publish of the first.
        _make_source_video(asset_dir / f"reel_asset_multi_{i}_review.mp4", duration=2.0 + i * 0.5)
        _write_passing_status_sidecar(asset_dir, f"reel_asset_multi_{i}_review")
        result = gpp.run_publish(asset_dir, "autonomous")
        assert result["approval_mode"] == "autonomous"

    still_valid = gpp.validate_standing_lane_autonomy_authorization()
    assert still_valid["revoked"] is False


# === 2. Per-asset, single-use execution claim ================================

@requires_ffmpeg
def test_execution_claim_created_and_closed_for_successful_autonomous_publish(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    fake_result = {"ok": True, "instagram_media_id": "abc", "permalink": "https://instagram.com/reel/abc/"}
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", lambda payload: fake_result)

    result = gpp.run_publish(valid_asset["asset_dir"], "autonomous")
    claim_path = Path(result["execution_claim_path"])
    assert claim_path.exists()
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["state"] == "closed"
    assert claim["publish_result"]["instagram_media_id"] == "abc"

    sidecar = json.loads(valid_asset["sidecar"].read_text(encoding="utf-8"))
    assert sidecar["instagram_published"] is True
    assert sidecar["publish_result"]["instagram_media_id"] == "abc"


def test_concurrent_second_execution_claim_rejected_sequential(isolated_roots: Path) -> None:
    kwargs = dict(
        asset_dir=isolated_roots, source_path=isolated_roots / "x.mp4", source_sha256="a" * 64,
        caption_bank_id="cb1", caption_text="hello", fingerprint="b" * 64, approval_mode="manual",
    )
    first = gpp.claim_execution("dup-slot", **kwargs)
    assert first["path"].exists()
    with pytest.raises(gpp.PipelineError, match="execution claim already exists"):
        gpp.claim_execution("dup-slot", **kwargs)
    assert len(_claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT)) == 1


def test_real_multiprocess_concurrent_claim_only_one_wins(isolated_roots: Path) -> None:
    """Real, OS-level concurrency coverage for the atomic claim -- separate
    processes (not threads, not a mocked lock), all racing to claim the
    same slot_id at once. Exactly one must win."""
    ctx = multiprocessing.get_context("fork")
    results_dir = isolated_roots / "mp_results"
    results_dir.mkdir()
    slot_id = "mp-concurrent-slot"
    n = 8

    procs = [ctx.Process(target=_mp_claim_worker, args=(slot_id, str(results_dir))) for _ in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    outcomes = [p.read_text(encoding="utf-8") for p in sorted(results_dir.glob("*.result"))]
    assert len(outcomes) == n, f"expected {n} worker results, got {outcomes}"
    assert outcomes.count("ok") == 1, f"expected exactly one winner, got: {outcomes}"
    assert outcomes.count("rejected") == n - 1

    claim_files = _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT)
    assert len(claim_files) == 1


# === 3. Mandatory gates unchanged/enforced ===================================

@requires_ffmpeg
def test_scrub_provenance_failure_blocks_publish_and_creates_no_claim(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(source_path: Path) -> dict:
        raise gpp.PipelineError("clean export failed: simulated scrub failure for test")

    monkeypatch.setattr(gpp, "run_clean_export", _boom)

    with pytest.raises(gpp.PipelineError, match="offline proof gate did not pass"):
        gpp.run_publish(valid_asset["asset_dir"], "manual", confirm_publish="whatever")

    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []


@requires_ffmpeg
def test_missing_credentials_blocks_autonomous_publish_via_unchanged_gate(
    isolated_roots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset_dir = isolated_roots / "asset_review" / "no_creds_asset"
    _make_source_video(asset_dir / "no_creds_asset_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(3))
    _write_passing_status_sidecar(asset_dir, "no_creds_asset_review")

    gpp.issue_standing_lane_autonomy_authorization()  # issuance itself needs no credentials
    _clear_credentials(monkeypatch)

    with pytest.raises(gpp.PipelineError, match="offline proof gate did not pass"):
        gpp.run_publish(asset_dir, "autonomous")
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []


@requires_ffmpeg
def test_duplicate_asset_rejected_via_sidecar_flag(valid_asset: dict) -> None:
    asset_dir = valid_asset["asset_dir"]
    _write_passing_status_sidecar(asset_dir, "reel_asset_one_review", instagram_published=True)

    proof = gpp.run_offline_proof_gate(asset_dir, valid_asset["source"])
    assert proof["proof_gate_passed"] is False
    assert proof["stages"]["duplicate_check_pre"]["is_duplicate"] is True

    with pytest.raises(gpp.PipelineError, match="offline proof gate did not pass"):
        gpp.run_publish(asset_dir, "manual", confirm_publish="anything")
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []


@requires_ffmpeg
def test_duplicate_asset_rejected_via_fingerprint_store(valid_asset: dict) -> None:
    asset_dir = valid_asset["asset_dir"]
    proof1 = gpp.run_offline_proof_gate(asset_dir, valid_asset["source"])
    assert proof1["proof_gate_passed"] is True
    clean_path = Path(proof1["stages"]["clean_export"]["clean_derivative_path"])

    from pipeline.lena_publish_quality_gate import mark_published_fingerprint, QualityGateConfig
    mark_published_fingerprint(clean_path, config=QualityGateConfig())

    proof2 = gpp.run_offline_proof_gate(asset_dir, valid_asset["source"])
    assert proof2["proof_gate_passed"] is False
    assert proof2["stages"]["duplicate_check_final"]["already_in_fingerprint_store"] is True


# === 4. Production QA + HPE proof gate =======================================

@requires_ffmpeg
def test_qa_hpe_gate_blocks_when_sidecar_missing(isolated_roots: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_fake_credentials(monkeypatch)
    asset_dir = isolated_roots / "asset_review" / "no_sidecar_asset"
    _make_source_video(asset_dir / "no_sidecar_asset_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(3))

    proof = gpp.run_offline_proof_gate(asset_dir, asset_dir / "no_sidecar_asset_review.mp4")
    assert proof["proof_gate_passed"] is False
    assert "no status.json sidecar" in proof["stages"]["production_qa_and_hpe_proof"]["error"]


@requires_ffmpeg
@pytest.mark.parametrize(
    "sidecar_data,expected_snippet",
    [
        ({"production_qa_passed": False, "hpe_proof_verified": True}, "production_qa_passed"),
        ({"production_qa_passed": True, "hpe_proof_verified": False}, "hpe_proof_verified"),
        ({"production_qa_passed": True}, "hpe_proof_verified"),
        ({"hpe_proof_verified": True}, "production_qa_passed"),
        ({"production_qa_passed": "yes", "hpe_proof_verified": True}, "production_qa_passed"),
    ],
)
def test_qa_hpe_gate_blocks_on_incomplete_or_falsy_proof(
    isolated_roots: Path, monkeypatch: pytest.MonkeyPatch, sidecar_data: dict, expected_snippet: str,
) -> None:
    _set_fake_credentials(monkeypatch)
    asset_dir = isolated_roots / "asset_review" / "bad_qa_asset"
    _make_source_video(asset_dir / "bad_qa_asset_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(3))
    (asset_dir / "bad_qa_asset_review.status.json").write_text(json.dumps(sidecar_data), encoding="utf-8")

    proof = gpp.run_offline_proof_gate(asset_dir, asset_dir / "bad_qa_asset_review.mp4")
    assert proof["proof_gate_passed"] is False
    assert expected_snippet in proof["stages"]["production_qa_and_hpe_proof"]["error"]


@requires_ffmpeg
def test_qa_hpe_gate_passes_with_valid_sidecar(valid_asset: dict) -> None:
    proof = gpp.run_offline_proof_gate(valid_asset["asset_dir"], valid_asset["source"])
    assert "error" not in proof["stages"]["production_qa_and_hpe_proof"]
    assert proof["stages"]["production_qa_and_hpe_proof"]["production_qa_passed"] is True


# === 5. Crash recovery ========================================================

def test_reconcile_recent_claimed_state_recommends_wait(isolated_roots: Path) -> None:
    claim = _claim()
    rec = gpp.reconcile_stale_execution_claim(claim["path"])
    assert rec["action"] == "wait"


def test_reconcile_stale_claimed_state_recommends_manual_verification_crash_before_upload(
    isolated_roots: Path,
) -> None:
    """Simulates a crash before the network publish call ever fired, or a
    crash immediately after Graph API container creation but before any
    local result was recorded -- both leave state='claimed' with no
    publish_result and are genuinely indistinguishable from local state
    alone. reconcile_stale_execution_claim() must never guess; it must
    require a human to check the account directly."""
    claim = _claim()
    data = json.loads(claim["path"].read_text(encoding="utf-8"))
    old = datetime.now(timezone.utc) - timedelta(seconds=gpp.STALE_CLAIM_THRESHOLD_SECONDS + 60)
    data["claimed_at_utc"] = old.isoformat().replace("+00:00", "Z")
    claim["path"].write_text(json.dumps(data), encoding="utf-8")

    rec = gpp.reconcile_stale_execution_claim(claim["path"])
    assert rec["action"] == "manual_verification_required"
    assert "check the Instagram account directly" in rec["reason"]


def test_reconcile_published_pending_closure_recommends_complete_pending_closure_crash_after_publish(
    isolated_roots: Path,
) -> None:
    claim = _claim()
    gpp.mark_claim_published(
        claim["path"], {"instagram_media_id": "media123", "permalink": "https://instagram.com/reel/media123/"}
    )
    rec = gpp.reconcile_stale_execution_claim(claim["path"])
    assert rec["action"] == "complete_pending_closure"
    assert "media123" in rec["reason"]


def test_reconcile_closed_claim_recommends_no_action(isolated_roots: Path) -> None:
    claim = _claim()
    gpp.mark_claim_published(claim["path"], {"instagram_media_id": "media123"})
    gpp.close_execution_claim(claim["path"])
    rec = gpp.reconcile_stale_execution_claim(claim["path"])
    assert rec["action"] == "none"


@requires_ffmpeg
def test_complete_pending_closure_finishes_bookkeeping_after_simulated_crash(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch, _no_network_no_real_env: list,
) -> None:
    """Crash-after-publish-but-before-fingerprint/closure-write scenario:
    publish_post() already succeeded (recorded here via mark_claim_published,
    standing in for the real call that would have happened), then the
    process is treated as having crashed. Recovery must finish bookkeeping
    using only the claim's own recorded result -- zero network calls."""
    asset_dir = valid_asset["asset_dir"]
    proof = gpp.run_offline_proof_gate(asset_dir, valid_asset["source"])
    assert proof["proof_gate_passed"] is True
    caption_stage = proof["stages"]["caption_selection"]
    clean_path = Path(proof["stages"]["clean_export"]["clean_derivative_path"])

    claim = gpp.claim_execution(
        asset_dir.name, asset_dir=asset_dir, source_path=valid_asset["source"],
        source_sha256=gpp._sha256_file(valid_asset["source"]), caption_bank_id=caption_stage["bank_id"],
        caption_text=caption_stage["text"], fingerprint=gpp._sha256_file(clean_path), approval_mode="manual",
    )
    claim_path = claim["path"]

    fake_result = {"ok": True, "instagram_media_id": "crash_media_id", "permalink": "https://instagram.com/reel/crash/"}
    gpp.mark_claim_published(claim_path, fake_result)

    def _forbidden(*a, **k):
        raise AssertionError("recovery must never call publish_post again")
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", _forbidden)

    rec = gpp.reconcile_stale_execution_claim(claim_path)
    assert rec["action"] == "complete_pending_closure"
    outcome = gpp.complete_pending_closure(claim_path)
    assert outcome["ok"] is True

    final_claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert final_claim["state"] == "closed"

    sidecar = json.loads(valid_asset["sidecar"].read_text(encoding="utf-8"))
    assert sidecar["instagram_published"] is True
    assert sidecar["publish_result"]["instagram_media_id"] == "crash_media_id"

    from pipeline.lena_publish_quality_gate import QualityGateConfig, _collect_published_fingerprints
    fp = gpp._sha256_file(clean_path)
    assert fp in _collect_published_fingerprints(QualityGateConfig())
    assert _no_network_no_real_env == []


def test_complete_pending_closure_rejects_wrong_state(isolated_roots: Path) -> None:
    claim = _claim()  # state == "claimed", not "published_pending_closure"
    with pytest.raises(gpp.PipelineError, match="published_pending_closure"):
        gpp.complete_pending_closure(claim["path"])


@requires_ffmpeg
def test_stale_claim_reconciliation_never_calls_publish_post(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch, _no_network_no_real_env: list,
) -> None:
    def _forbidden(*a, **k):
        raise AssertionError("reconciliation must never call publish_post")
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", _forbidden)

    claim = _claim(asset_dir=valid_asset["asset_dir"], source_path=valid_asset["source"])
    old = datetime.now(timezone.utc) - timedelta(seconds=gpp.STALE_CLAIM_THRESHOLD_SECONDS + 1)
    data = json.loads(claim["path"].read_text(encoding="utf-8"))
    data["claimed_at_utc"] = old.isoformat().replace("+00:00", "Z")
    claim["path"].write_text(json.dumps(data), encoding="utf-8")

    rec = gpp.reconcile_stale_execution_claim(claim["path"])
    assert rec["action"] == "manual_verification_required"
    assert _no_network_no_real_env == []


# === 6. Caption inventory: warn at 2 remaining, fail closed only at 0 =======

def test_inventory_warning_triggers_exactly_at_threshold(isolated_roots: Path) -> None:
    asset_dir = isolated_roots / "asset_review" / "inv3"
    asset_dir.mkdir(parents=True)
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(3))  # 3 eligible -> 2 remain after selection
    result = gpp.select_caption(asset_dir)
    assert result["inventory"]["remaining_available_after_selection"] == 2
    assert result["inventory"]["low_inventory_warning"] is True
    assert result["inventory"]["exhausted_after_selection"] is False


def test_inventory_warning_not_triggered_above_threshold(isolated_roots: Path) -> None:
    asset_dir = isolated_roots / "asset_review" / "inv4"
    asset_dir.mkdir(parents=True)
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(4))  # 4 eligible -> 3 remain after selection
    result = gpp.select_caption(asset_dir)
    assert result["inventory"]["remaining_available_after_selection"] == 3
    assert result["inventory"]["low_inventory_warning"] is False


def test_inventory_exhausted_after_selection_only_at_zero(isolated_roots: Path) -> None:
    asset_dir = isolated_roots / "asset_review" / "inv1"
    asset_dir.mkdir(parents=True)
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(1))  # 1 eligible -> 0 remain after selection
    result = gpp.select_caption(asset_dir)
    assert result["inventory"]["remaining_available_after_selection"] == 0
    assert result["inventory"]["exhausted_after_selection"] is True
    assert result["inventory"]["low_inventory_warning"] is True


@requires_ffmpeg
def test_autonomous_publish_succeeds_at_low_inventory_warning_not_blocked(
    isolated_roots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_fake_credentials(monkeypatch)
    gpp.issue_standing_lane_autonomy_authorization()
    asset_dir = isolated_roots / "asset_review" / "warn_asset"
    _make_source_video(asset_dir / "warn_asset_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(3))  # warns, does not exhaust
    _write_passing_status_sidecar(asset_dir, "warn_asset_review")

    fake_result = {"ok": True, "instagram_media_id": "warn_ok", "permalink": "https://instagram.com/reel/warn/"}
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", lambda payload: fake_result)
    result = gpp.run_publish(asset_dir, "autonomous")
    assert result["instagram_media_id"] == "warn_ok"


@requires_ffmpeg
def test_autonomous_publish_blocked_at_exhaustion(isolated_roots: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_fake_credentials(monkeypatch)
    gpp.issue_standing_lane_autonomy_authorization()
    asset_dir = isolated_roots / "asset_review" / "exhaust_asset"
    _make_source_video(asset_dir / "exhaust_asset_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(1))  # exhausts after selection
    _write_passing_status_sidecar(asset_dir, "exhaust_asset_review")

    with pytest.raises(gpp.PipelineError, match="caption_bank_exhausted"):
        gpp.run_publish(asset_dir, "autonomous")
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []


@requires_ffmpeg
def test_manual_publish_not_blocked_even_at_exhaustion_only_warned(
    isolated_roots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_fake_credentials(monkeypatch)
    asset_dir = isolated_roots / "asset_review" / "manual_exhaust_asset"
    _make_source_video(asset_dir / "manual_exhaust_asset_review.mp4")
    _write_bank(gpp.CAPTION_BANK_PATH, _default_bank_entries(1))
    _write_passing_status_sidecar(asset_dir, "manual_exhaust_asset_review")

    proof = gpp.run_offline_proof_gate(asset_dir, asset_dir / "manual_exhaust_asset_review.mp4")
    assert proof["caption_bank_exhausted_after_selection"] is True
    assert proof["proof_gate_passed"] is True  # manual mode: a human is present, never blocked by inventory

    caption_text = proof["stages"]["caption_selection"]["text"]
    fake_result = {"ok": True, "instagram_media_id": "manual_exhaust_ok", "permalink": "https://instagram.com/reel/manual/"}
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", lambda payload: fake_result)
    result = gpp.run_publish(asset_dir, "manual", confirm_publish=caption_text)
    assert result["instagram_media_id"] == "manual_exhaust_ok"


def test_caption_bank_full_exhaustion_selection_error_unchanged(isolated_roots: Path) -> None:
    """Pre-existing behavior (nothing eligible at all in the bank) is
    unchanged by this task."""
    _write_bank(gpp.CAPTION_BANK_PATH, [{"id": "cb001", "text": "only one", "status": "used"}])
    with pytest.raises(gpp.PipelineError, match="no available, non-duplicate, non-blocked caption"):
        gpp.select_caption(None)


# === 7. Preflight / publisher route and caption consistency =================

@requires_ffmpeg
def test_preflight_uses_same_route_and_credential_aliases_as_real_publisher(valid_asset: dict) -> None:
    context = gpp.resolve_reels_publish_context(valid_asset["asset_dir"])
    assert context["api_base"] == instagram_graph_adapter._api_base()
    assert context["credential_env_aliases"] == instagram_graph_adapter.ENV_ALIASES
    assert preflight_mod.resolve_reels_publish_context is gpp.resolve_reels_publish_context


@requires_ffmpeg
def test_preflight_caption_preview_matches_real_selection(valid_asset: dict) -> None:
    context = gpp.resolve_reels_publish_context(valid_asset["asset_dir"])
    direct = gpp.select_caption(valid_asset["asset_dir"])
    assert context["caption_preview"]["bank_id"] == direct["bank_id"]
    assert context["caption_preview"]["text"] == direct["text"]


def test_preflight_source_has_no_hardcoded_golden_hour_state() -> None:
    source_text = Path(preflight_mod.__file__).read_text(encoding="utf-8")
    forbidden = [
        "Golden hour did the rest.",
        "golden_hour_colonnade",
        "lena_meta_publish_common",
        "EXPECT_SHA",
        "ASSET_REL",
        "CAPTION     =",
    ]
    for token in forbidden:
        assert token not in source_text, f"preflight script still hardcodes {token!r}"


@requires_ffmpeg
def test_live_token_check_reuses_real_publisher_request_helper(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = gpp.resolve_reels_publish_context(valid_asset["asset_dir"])
    seen: dict = {}

    def _fake_request_json(method, url, **kwargs):
        seen["method"] = method
        seen["url"] = url
        return {"id": "fake_me_id"}

    monkeypatch.setattr(instagram_graph_adapter, "_request_json", _fake_request_json)
    result = preflight_mod.check_live_login_token(context)
    assert result == {"ok": True, "me_id": "fake_me_id", "raw": {"id": "fake_me_id"}}
    assert seen["method"] == "GET"
    assert seen["url"] == f"{instagram_graph_adapter._api_base()}/me"


@requires_ffmpeg
def test_live_token_check_reports_missing_credentials_without_calling_anything(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_credentials(monkeypatch)
    context = gpp.resolve_reels_publish_context(valid_asset["asset_dir"])
    result = preflight_mod.check_live_login_token(context)
    assert result["ok"] is False
    assert result["reason"] == "missing_credentials"


@requires_ffmpeg
def test_zero_real_network_calls_across_full_offline_flow(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch, _no_network_no_real_env: list,
) -> None:
    monkeypatch.setattr(instagram_graph_adapter, "_request_json", lambda *a, **k: {"id": "fake_me_id"})
    report = preflight_mod.run_preflight(valid_asset["asset_dir"], check_live_token=True)
    assert report["results"]["3. Live Instagram Login /me validation"] is True
    assert report["all_green"] is True
    assert _no_network_no_real_env == []


# === 8. The actual CLI, run offline, in both manual and authorized-autonomous modes

@requires_ffmpeg
def test_cli_offline_proof_mode_real_entrypoint(valid_asset: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, output = _run_cli(monkeypatch, ["--mode", "offline-proof", "--asset-dir", str(valid_asset["asset_dir"])])
    assert exit_code == 0
    payload = json.loads(output)
    assert payload["proof_gate_passed"] is True


@requires_ffmpeg
def test_cli_publish_manual_mode_wrong_confirmation_blocked(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch, _no_network_no_real_env: list,
) -> None:
    exit_code, output = _run_cli(monkeypatch, [
        "--mode", "publish", "--approval-mode", "manual",
        "--asset-dir", str(valid_asset["asset_dir"]), "--confirm-publish", "this is not the real caption",
    ])
    assert exit_code == 1
    payload = json.loads(output)
    assert payload["ok"] is False
    assert "did not exactly match" in payload["error"]
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []
    assert _no_network_no_real_env == []


@requires_ffmpeg
def test_cli_publish_manual_mode_correct_confirmation_succeeds(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    proof = gpp.run_offline_proof_gate(valid_asset["asset_dir"], valid_asset["source"])
    caption_text = proof["stages"]["caption_selection"]["text"]
    fake_result = {"ok": True, "instagram_media_id": "cli_manual_id", "permalink": "https://instagram.com/reel/cli_manual/"}
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", lambda payload: fake_result)

    exit_code, output = _run_cli(monkeypatch, [
        "--mode", "publish", "--approval-mode", "manual",
        "--asset-dir", str(valid_asset["asset_dir"]), "--confirm-publish", caption_text,
    ])
    assert exit_code == 0
    payload = json.loads(output)
    assert payload["ok"] is True
    assert payload["result"]["instagram_media_id"] == "cli_manual_id"


@requires_ffmpeg
def test_cli_publish_autonomous_mode_blocked_without_standing_authorization(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch, _no_network_no_real_env: list,
) -> None:
    exit_code, output = _run_cli(monkeypatch, [
        "--mode", "publish", "--approval-mode", "autonomous", "--asset-dir", str(valid_asset["asset_dir"]),
    ])
    assert exit_code == 1
    payload = json.loads(output)
    assert payload["ok"] is False
    assert "no standing Reels lane-autonomy authorization exists" in payload["error"]
    assert _claim_files(gpp.LANE_AUTONOMY_CLAIM_ROOT) == []
    assert _no_network_no_real_env == []


@requires_ffmpeg
def test_cli_publish_autonomous_mode_succeeds_with_standing_authorization(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpp.issue_standing_lane_autonomy_authorization()
    fake_result = {"ok": True, "instagram_media_id": "cli_auto_id", "permalink": "https://instagram.com/reel/cli_auto/"}
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", lambda payload: fake_result)

    exit_code, output = _run_cli(monkeypatch, [
        "--mode", "publish", "--approval-mode", "autonomous", "--asset-dir", str(valid_asset["asset_dir"]),
    ])
    assert exit_code == 0
    payload = json.loads(output)
    assert payload["ok"] is True
    assert payload["result"]["instagram_media_id"] == "cli_auto_id"
    assert payload["result"]["approval_mode"] == "autonomous"


def test_cli_issue_and_revoke_standing_authorization_in_process(isolated_roots: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, output = _run_cli(monkeypatch, ["--mode", "issue-standing-authorization"])
    assert exit_code == 0
    payload = json.loads(output)
    assert payload["revoked"] is False
    assert gpp.STANDING_AUTHORIZATION_PATH.exists()

    exit_code2, output2 = _run_cli(monkeypatch, ["--mode", "revoke-standing-authorization"])
    assert exit_code2 == 0
    payload2 = json.loads(output2)
    assert payload2["revoked"] is True


@requires_ffmpeg
def test_cli_reconcile_claim_mode_completes_pending_closure(
    valid_asset: dict, monkeypatch: pytest.MonkeyPatch, _no_network_no_real_env: list,
) -> None:
    proof = gpp.run_offline_proof_gate(valid_asset["asset_dir"], valid_asset["source"])
    caption_stage = proof["stages"]["caption_selection"]
    clean_path = Path(proof["stages"]["clean_export"]["clean_derivative_path"])
    claim = gpp.claim_execution(
        valid_asset["asset_dir"].name, asset_dir=valid_asset["asset_dir"], source_path=valid_asset["source"],
        source_sha256=gpp._sha256_file(valid_asset["source"]), caption_bank_id=caption_stage["bank_id"],
        caption_text=caption_stage["text"], fingerprint=gpp._sha256_file(clean_path), approval_mode="manual",
    )
    gpp.mark_claim_published(claim["path"], {"instagram_media_id": "cli_recover_id"})

    def _forbidden(*a, **k):
        raise AssertionError("reconcile-claim CLI mode must never call publish_post")
    monkeypatch.setattr(instagram_graph_adapter, "publish_post", _forbidden)

    exit_code, output = _run_cli(monkeypatch, ["--mode", "reconcile-claim", "--claim-path", str(claim["path"])])
    assert exit_code == 0
    payload = json.loads(output)
    assert payload["action"] == "complete_pending_closure"
    assert payload["completed"]["ok"] is True
    assert _no_network_no_real_env == []


def test_cli_real_subprocess_issue_and_revoke_standing_authorization(tmp_path: Path) -> None:
    """One genuine, literal OS-process invocation of the actual CLI file
    (not gpp.main() called in-process) -- proves the script itself is a
    valid, runnable entrypoint. Restricted to issue/revoke-standing-
    authorization, which never call bind_credentials()/load_env_once() and
    therefore can never load the real repo's .env (with its real Instagram/
    R2 secrets) or make any network call, however invoked. The path is
    pointed at an isolated tmp file via --standing-authorization-path so
    nothing is written under the real repo tree, and the subprocess env is
    stripped down to just PATH as an extra safety margin."""
    cli_script = Path(gpp.__file__).resolve()
    standing_path = tmp_path / "isolated_standing_auth.json"
    clean_env = {"PATH": os.environ.get("PATH", "")}

    issue = subprocess.run(
        [sys.executable, str(cli_script), "--mode", "issue-standing-authorization",
         "--standing-authorization-path", str(standing_path)],
        capture_output=True, text=True, timeout=30, env=clean_env, cwd=str(tmp_path),
    )
    assert issue.returncode == 0, issue.stderr
    payload = json.loads(issue.stdout)
    assert payload["revoked"] is False
    assert standing_path.exists()

    revoke = subprocess.run(
        [sys.executable, str(cli_script), "--mode", "revoke-standing-authorization",
         "--standing-authorization-path", str(standing_path)],
        capture_output=True, text=True, timeout=30, env=clean_env, cwd=str(tmp_path),
    )
    assert revoke.returncode == 0, revoke.stderr
    payload2 = json.loads(revoke.stdout)
    assert payload2["revoked"] is True
