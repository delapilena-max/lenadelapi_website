"""
Consolidated, reusable governed publish pipeline for Lena Reels.

Generalizes what was done by hand for the Golden-Hour Colonnade asset into
one tool usable on future assets. Fully automates the deterministic,
verifiable parts of the pipeline.

Offline stages (no network, no provider call), orchestrated by
run_offline_proof_gate():
  1. select_caption()                    -- pick an unused, non-blocked-term
                                             line from the human-curated
                                             caption bank; check it against
                                             every real caption-history
                                             source in the repo.
  2. run_clean_export()                  -- reuses
                                             tools/lena_scrub_media_metadata_v1.py.
  3. bind_credentials()                  -- resolves env vars via the
                                             adapter's own aliases;
                                             presence-only check, no network
                                             call to Meta to validate the
                                             token.
  4. check_production_qa_and_hpe_proof() -- requires the asset's status.json
                                             sidecar to record
                                             production_qa_passed=true and
                                             hpe_proof_verified=true. No
                                             sidecar, or either field not
                                             literally true, fails closed.
  5. run_duplicate_check()               -- shared quality-gate fingerprint
                                             store + per-asset sidecar
                                             instagram_published flag.

Two-tier authorization model for the publish stage (run_publish(), one real
network call):

  approval_mode="manual": requires --confirm-publish to equal, exactly, the
  proof gate's selected caption text -- a live, asset-specific human action
  performed at publish time. No standing authorization involved.

  approval_mode="autonomous": requires ONE durable, standing Reels-lane
  autonomy authorization (see issue_standing_lane_autonomy_authorization() /
  validate_standing_lane_autonomy_authorization()) -- issued once by a
  human, not per asset, with a long-but-bounded TTL (default 30 days, max 90
  days) and a kill switch. It is NOT single-use and is NOT asset-specific;
  it is the lane-level "autonomous Reels publishing is turned on" toggle.
  From that standing authority, a separate, single-use EXECUTION CLAIM is
  derived automatically for each asset (see claim_execution()) -- this is
  what is actually atomic and single-use, and it is what
  MUST be created before any upload or Graph call. There is still no
  autonomous path that runs without an active standing authorization, and
  there is still no path (manual or autonomous) that reaches a Graph call
  without first winning that asset's execution claim.

Crash recovery: the execution claim has three states (claimed ->
published_pending_closure -> closed). reconcile_stale_execution_claim()
inspects a claim and recommends exactly one of: wait (recent, may still be
in flight), complete_pending_closure (publish already succeeded per the
claim's own recorded result -- safe to finish bookkeeping with zero network
calls), or manual_verification_required (old and still unresolved -- must
never be auto-retried). See tools/lena_reels_execution_claim_recovery_runbook.md
for the operator-facing procedure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CAPTION_BANK_PATH = REPO_ROOT / "pipeline" / "influencer_nodes" / "lena" / "caption_bank_v1.json"
BLOCKED_TERMS_PATH = REPO_ROOT / "pipeline" / "influencer_nodes" / "lena" / "quality_blocked_terms_v2_1.json"
LEGACY_CAPTION_HISTORY_GLOBS = ["outputs/caption_*.txt"]

# Caption-bank inventory policy: warn (non-blocking, surfaced in the proof
# gate report) once this few or fewer unused/non-blocked captions remain
# after the current selection; fail closed for autonomous mode ONLY when a
# selection would leave the bank fully exhausted (0 remaining). Manual mode
# is never blocked by this -- a human is present and can see the warning.
CAPTION_BANK_WARN_THRESHOLD = 2

# ---------------------------------------------------------------------------
# Runtime data roots (not code). Referenced as bare module globals
# everywhere below (never captured as default-argument values) so tests can
# monkeypatch them to a tmp_path root without touching the real repo's
# pipeline/approvals/ directory.
# ---------------------------------------------------------------------------
LANE_AUTONOMY_ROOT = REPO_ROOT / "pipeline" / "approvals" / "lena" / "reels_lane_autonomy"
LANE_AUTONOMY_CLAIM_ROOT = LANE_AUTONOMY_ROOT / "claims"
STANDING_AUTHORIZATION_PATH = LANE_AUTONOMY_ROOT / "lena_reels_standing_lane_autonomy_authorization.json"

LANE_AUTONOMY_SCHEMA_VERSION = "v1"
LANE_AUTONOMY_ISSUER = "lena_autonomy_controller"

STANDING_AUTONOMY_REPORT_TYPE = "lena_reels_standing_lane_autonomy_authorization"
STANDING_AUTONOMY_MODE = "reels_lane_autonomy_standing_policy"
STANDING_AUTONOMY_DEFAULT_TTL_SECONDS = 30 * 24 * 3600
STANDING_AUTONOMY_MAX_TTL_SECONDS = 90 * 24 * 3600

# How long an execution claim may sit in state="claimed" with no recorded
# publish result before it is treated as needing manual verification instead
# of an automatic "still in flight" assumption.
STALE_CLAIM_THRESHOLD_SECONDS = 900


class PipelineError(RuntimeError):
    """Raised for any hard-fail condition in this pipeline."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Stage 1: caption selection
# ---------------------------------------------------------------------------

def _collect_used_caption_texts(extra_search_roots: Optional[list[Path]] = None) -> set[str]:
    """Bounded scan -- deliberately does NOT rglob the whole repo. This repo
    has dozens of large near-duplicate worktree copies and several venvs;
    an unbounded rglob() from REPO_ROOT is slow enough to time out. Only
    known, small, relevant directories are scanned."""
    used: set[str] = set()

    for txt_path in REPO_ROOT.glob("outputs/caption_*.txt"):
        try:
            used.add(txt_path.read_text(encoding="utf-8").strip())
        except Exception:
            continue

    for log_path in (REPO_ROOT / "pipeline" / "publish_logs").glob("*.json"):
        try:
            data = json.loads(log_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        cap = data.get("caption")
        if isinstance(cap, str) and cap.strip():
            used.add(cap.strip())

    search_roots = [REPO_ROOT / "pipeline" / "asset_review"]
    for extra in (extra_search_roots or []):
        search_roots.append(extra)

    for root in search_roots:
        if not root.exists():
            continue
        for status_path in root.rglob("*.status.json"):
            try:
                data = json.loads(status_path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            approved = data.get("approved_caption") or {}
            text = approved.get("text")
            if isinstance(text, str) and text.strip():
                used.add(text.strip())
            removed = data.get("removed_contradictory_entry") or {}
            orig = removed.get("original_caption_value")
            if isinstance(orig, str) and orig.strip():
                used.add(orig.strip())

    bank = json.loads(CAPTION_BANK_PATH.read_text(encoding="utf-8-sig"))
    for entry in bank.get("captions", []):
        if entry.get("status") == "used" and entry.get("text"):
            used.add(entry["text"].strip())

    return used


def _find_worktree_asset_review_root(asset_dir: Path) -> Optional[Path]:
    for parent in asset_dir.parents:
        candidate = parent / "pipeline" / "asset_review"
        if candidate.exists():
            return candidate
    return None


def _eligible_caption_entries(bank: dict[str, Any], blocked_terms: list[str], used_texts: set[str]) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for entry in bank.get("captions", []):
        if entry.get("status") != "available":
            continue
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        if text in used_texts:
            continue
        lowered = text.lower()
        if any(term in lowered for term in blocked_terms):
            continue
        eligible.append(entry)
    return eligible


def select_caption(asset_dir: Optional[Path] = None) -> dict[str, Any]:
    if not CAPTION_BANK_PATH.exists():
        raise PipelineError(f"caption bank not found: {CAPTION_BANK_PATH}")
    if not BLOCKED_TERMS_PATH.exists():
        raise PipelineError(f"blocked terms file not found: {BLOCKED_TERMS_PATH}")

    bank = json.loads(CAPTION_BANK_PATH.read_text(encoding="utf-8-sig"))
    blocked = json.loads(BLOCKED_TERMS_PATH.read_text(encoding="utf-8-sig"))
    blocked_terms = [t.lower() for t in blocked.get("blocked_public_terms", [])]

    extra_roots = []
    if asset_dir is not None:
        worktree_root = _find_worktree_asset_review_root(asset_dir)
        if worktree_root is not None:
            extra_roots.append(worktree_root)

    used_texts = _collect_used_caption_texts(extra_roots)
    eligible = _eligible_caption_entries(bank, blocked_terms, used_texts)

    if not eligible:
        raise PipelineError(
            "no available, non-duplicate, non-blocked caption remains in the caption bank -- "
            "a human needs to add and review new lines in "
            f"{CAPTION_BANK_PATH} before this pipeline can select one"
        )

    chosen = eligible[0]
    remaining_after = len(eligible) - 1
    return {
        "text": chosen["text"],
        "bank_id": chosen.get("id"),
        "source": str(CAPTION_BANK_PATH),
        "checked_against_count": len(used_texts),
        "blocked_terms_checked": True,
        "duplicate_found": False,
        "inventory": {
            "eligible_before_selection": len(eligible),
            "remaining_available_after_selection": remaining_after,
            "warn_threshold": CAPTION_BANK_WARN_THRESHOLD,
            "low_inventory_warning": remaining_after <= CAPTION_BANK_WARN_THRESHOLD,
            "exhausted_after_selection": remaining_after == 0,
        },
    }


# ---------------------------------------------------------------------------
# Stage 2: clean export
# ---------------------------------------------------------------------------

def run_clean_export(source_path: Path) -> dict[str, Any]:
    from tools.lena_scrub_media_metadata_v1 import resolve_clean_output_path, scrub_media_metadata, ScrubError
    from tools.lena_verify_clean_export_v1 import verify_clean_export, CleanExportVerificationError

    source_path = source_path.resolve()
    clean_path = resolve_clean_output_path(source_path)

    if clean_path.exists():
        # Idempotent: if a valid clean derivative already exists, verify and
        # reuse it instead of re-scrubbing (scrub_media_metadata refuses to
        # overwrite without --force anyway).
        try:
            facts = verify_clean_export(source_path)
            integrity = verify_content_and_metadata_integrity(source_path, Path(facts["clean_derivative_path"]))
            return {**facts, "reused_existing": True, "content_and_metadata_integrity": integrity}
        except CleanExportVerificationError:
            pass  # fall through and (re)scrub below

    try:
        report = scrub_media_metadata(source_path)
    except ScrubError as exc:
        raise PipelineError(f"clean export failed: {exc}") from exc

    try:
        facts = verify_clean_export(source_path)
    except CleanExportVerificationError as exc:
        raise PipelineError(f"clean export produced but failed re-verification: {exc}") from exc

    # Hard gate: independent content-identity + full-metadata-removal check.
    # A missing or invalid clean derivative/provenance sidecar already fails
    # closed above via verify_clean_export(); this additionally fails closed
    # if the derivative exists and is sidecar-valid but doesn't actually
    # hold identical media content, or still carries any non-structural tag.
    integrity = verify_content_and_metadata_integrity(source_path, Path(facts["clean_derivative_path"]))

    return {**facts, "reused_existing": False, "scrub_report": report, "content_and_metadata_integrity": integrity}


# ---------------------------------------------------------------------------
# Stage 2b: independent content-integrity + full-metadata-removal check.
#
# Runs every time, in addition to (not instead of) the repo's own
# verify_clean_export(). That function proves the sidecar's self-reported
# hashes and boolean flag are real. This function independently re-derives,
# via ffprobe, that (a) video/audio stream count, codecs, resolution,
# sample rate, channels, and duration are identical between source and
# clean derivative -- i.e. nothing but metadata changed -- and (b) the
# clean derivative carries no format or stream tags beyond the same minimal
# structural allowlist the scrubber itself enforces (major_brand,
# minor_version, compatible_brands, handler_name, vendor_id, encoder,
# language, creation_time). This is a general "no data survives scrubbing"
# check, not narrowed to AI-related substrings -- any tag outside that
# allowlist fails closed, whatever it is.
# ---------------------------------------------------------------------------

def _ffprobe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise PipelineError(f"ffprobe failed on {path}: {out.stderr.strip()[-2000:]}")
    return json.loads(out.stdout)


def verify_content_and_metadata_integrity(source_path: Path, clean_path: Path) -> dict[str, Any]:
    from tools.lena_scrub_media_metadata_v1 import VIDEO_BENIGN_TAG_KEYS

    src = _ffprobe(source_path)
    clean = _ffprobe(clean_path)

    src_streams = src.get("streams", [])
    clean_streams = clean.get("streams", [])
    if len(src_streams) != len(clean_streams):
        raise PipelineError(
            f"stream count changed during scrub: source={len(src_streams)} clean={len(clean_streams)} -- "
            "refusing (this could mean a stream, e.g. an embedded subtitle/data/attachment track, was silently dropped or added)"
        )

    stream_mismatches = []
    for i, (s, c) in enumerate(zip(src_streams, clean_streams)):
        if s.get("codec_type") != c.get("codec_type"):
            stream_mismatches.append(f"stream {i}: codec_type {s.get('codec_type')!r} != {c.get('codec_type')!r}")
            continue
        if s.get("codec_name") != c.get("codec_name"):
            stream_mismatches.append(f"stream {i}: codec_name {s.get('codec_name')!r} != {c.get('codec_name')!r}")
        if s.get("codec_type") == "video":
            for field in ("width", "height", "r_frame_rate"):
                if s.get(field) != c.get(field):
                    stream_mismatches.append(f"stream {i} ({field}): {s.get(field)!r} != {c.get(field)!r}")
        if s.get("codec_type") == "audio":
            for field in ("sample_rate", "channels"):
                if s.get(field) != c.get(field):
                    stream_mismatches.append(f"stream {i} ({field}): {s.get(field)!r} != {c.get(field)!r}")
        src_dur = float(s.get("duration", 0) or 0)
        clean_dur = float(c.get("duration", 0) or 0)
        if abs(src_dur - clean_dur) > 0.05:
            stream_mismatches.append(f"stream {i} duration: {src_dur} vs {clean_dur} (tolerance 0.05s)")

    src_format_dur = float(src.get("format", {}).get("duration", 0) or 0)
    clean_format_dur = float(clean.get("format", {}).get("duration", 0) or 0)
    if abs(src_format_dur - clean_format_dur) > 0.05:
        stream_mismatches.append(f"format duration: {src_format_dur} vs {clean_format_dur} (tolerance 0.05s)")

    if stream_mismatches:
        raise PipelineError(
            "content-integrity check failed -- clean derivative does not have identical media "
            f"content to the source: {stream_mismatches}"
        )

    # All-data-scrubbed check: not narrowed to AI-related substrings. Any
    # tag on the clean file outside the minimal structural allowlist fails
    # closed, whatever it is (GPS/location, device info, editor identifiers,
    # anything).
    clean_tags: dict[str, Any] = dict(clean.get("format", {}).get("tags", {}) or {})
    for stream in clean_streams:
        for k, v in (stream.get("tags") or {}).items():
            clean_tags[f"stream:{k}"] = v

    leftover = {k: v for k, v in clean_tags.items() if k.split(":")[-1] not in VIDEO_BENIGN_TAG_KEYS}
    if leftover:
        raise PipelineError(f"clean derivative still carries non-structural metadata: {leftover}")

    src_tags: dict[str, Any] = dict(src.get("format", {}).get("tags", {}) or {})
    for stream in src_streams:
        for k, v in (stream.get("tags") or {}).items():
            src_tags[f"stream:{k}"] = v

    return {
        "stream_count_matched": True,
        "streams_content_identical": True,
        "duration_matched_within_tolerance_seconds": 0.05,
        "source_tags_found": src_tags,
        "clean_tags_remaining": clean_tags,
        "all_non_structural_metadata_removed": True,
        "note": "clean_tags_remaining should only ever contain the minimal structural allowlist -- if it's non-empty and this function didn't raise, every key in it is one of the documented benign keys",
    }


# ---------------------------------------------------------------------------
# Stage 3: credential binding (presence only -- no network call to Meta)
# ---------------------------------------------------------------------------

def bind_credentials() -> dict[str, Any]:
    from pipeline.env_loader import load_env_once
    load_env_once(REPO_ROOT, override=True)

    from pipeline.publisher.instagram_graph_adapter import ENV_ALIASES, _clean_token

    resolved = {}
    missing = []
    for canonical, aliases in ENV_ALIASES.items():
        found_alias = None
        for alias in aliases:
            if _clean_token(os.environ.get(alias)):
                found_alias = alias
                break
        if found_alias:
            resolved[canonical] = found_alias
        else:
            missing.append(canonical)

    r2_keys = ["R2_ACCESS_KEY_ID", "R2_ACCOUNT_ID", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL", "R2_SECRET_ACCESS_KEY"]
    r2_missing = [k for k in r2_keys if not _clean_token(os.environ.get(k))]

    if missing or r2_missing:
        raise PipelineError(f"missing credentials: instagram={missing} r2={r2_missing}")

    return {"instagram_env_resolved_from": resolved, "r2_present": True, "network_validated": False}


# ---------------------------------------------------------------------------
# Stage 4: production QA + HPE (Human Presence Engine) creative-proof gate.
#
# Read-only. Requires the asset's *.status.json sidecar to exist and to
# record production_qa_passed=true and hpe_proof_verified=true (the literal
# boolean True, not merely truthy) -- these are the two upstream human/QA
# approvals every asset must already carry before this pipeline will
# consider it publish-eligible at all. This module does not perform QA or
# HPE verification itself and does not touch any HPE engineering code --
# it only reads a sidecar field two upstream processes are expected to set.
# ---------------------------------------------------------------------------

def check_production_qa_and_hpe_proof(status_json_path: Optional[Path]) -> dict[str, Any]:
    if status_json_path is None or not status_json_path.exists():
        raise PipelineError(
            "no status.json sidecar found for this asset -- production QA and HPE proof cannot "
            "be verified. A sidecar with production_qa_passed=true and hpe_proof_verified=true "
            "must exist before this asset is publish-eligible."
        )
    try:
        data = json.loads(status_json_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PipelineError(f"status.json sidecar is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError("status.json sidecar must be a JSON object")

    qa_passed = data.get("production_qa_passed")
    if qa_passed is not True:
        raise PipelineError(f"production_qa_passed is not true in status.json sidecar (got {qa_passed!r})")

    hpe_verified = data.get("hpe_proof_verified")
    if hpe_verified is not True:
        raise PipelineError(f"hpe_proof_verified is not true in status.json sidecar (got {hpe_verified!r})")

    return {
        "status_json_path": str(status_json_path),
        "production_qa_passed": True,
        "hpe_proof_verified": True,
    }


# ---------------------------------------------------------------------------
# Stage 5: duplicate prevention
# ---------------------------------------------------------------------------

def run_duplicate_check(clean_path: Path, status_json_path: Optional[Path]) -> dict[str, Any]:
    from pipeline.lena_publish_quality_gate import QualityGateConfig, _collect_published_fingerprints, file_sha256

    config = QualityGateConfig()
    fingerprint = file_sha256(clean_path)
    already_in_fingerprint_store = fingerprint in _collect_published_fingerprints(config)

    already_published_per_sidecar = False
    if status_json_path is not None and status_json_path.exists():
        try:
            data = json.loads(status_json_path.read_text(encoding="utf-8-sig"))
            already_published_per_sidecar = bool(data.get("instagram_published"))
        except Exception:
            pass

    is_duplicate = already_in_fingerprint_store or already_published_per_sidecar
    return {
        "fingerprint": fingerprint,
        "already_in_fingerprint_store": already_in_fingerprint_store,
        "already_published_per_sidecar": already_published_per_sidecar,
        "is_duplicate": is_duplicate,
    }


# ---------------------------------------------------------------------------
# Offline proof gate -- orchestrates stages 1-5, no network, no provider call
# ---------------------------------------------------------------------------

def find_source_mp4(asset_dir: Path) -> Path:
    candidates = [
        p for p in asset_dir.glob("*.mp4")
        if not p.stem.endswith("_clean")
    ]
    if len(candidates) != 1:
        raise PipelineError(
            f"expected exactly one non-clean .mp4 in {asset_dir}, found {len(candidates)}: {candidates} -- "
            "pass an explicit --source"
        )
    return candidates[0]


def run_offline_proof_gate(asset_dir: Path, source_path: Optional[Path] = None) -> dict[str, Any]:
    asset_dir = asset_dir.resolve()
    if not asset_dir.exists():
        raise PipelineError(f"asset dir does not exist: {asset_dir}")

    source_path = (source_path or find_source_mp4(asset_dir)).resolve()
    status_candidates = list(asset_dir.glob("*.status.json"))
    status_json_path = status_candidates[0] if status_candidates else None

    report: dict[str, Any] = {
        "schema_version": "lena_governed_publish_pipeline_offline_proof_gate_v1",
        "asset_dir": str(asset_dir),
        "source_path": str(source_path),
        "status_json_path": str(status_json_path) if status_json_path else None,
        "checked_at_utc": _now(),
        "network_calls_made": 0,
        "provider_calls_made": 0,
        "stages": {},
    }

    overall_pass = True

    # Cheap pre-check using just the sidecar flag, before doing any real work --
    # a fingerprint-based check happens for real below once the clean
    # derivative is guaranteed to exist and be re-verified.
    if status_json_path is not None and status_json_path.exists():
        try:
            existing = json.loads(status_json_path.read_text(encoding="utf-8-sig"))
        except Exception:
            existing = {}
        if existing.get("instagram_published"):
            report["stages"]["duplicate_check_pre"] = {
                "already_published_per_sidecar": True,
                "is_duplicate": True,
            }
            overall_pass = False
        else:
            report["stages"]["duplicate_check_pre"] = {
                "already_published_per_sidecar": False,
                "is_duplicate": False,
            }
    else:
        report["stages"]["duplicate_check_pre"] = {"note": "no status.json sidecar found for this asset yet"}

    try:
        report["stages"]["caption_selection"] = select_caption(asset_dir)
    except Exception as exc:
        report["stages"]["caption_selection"] = {"error": str(exc)}
        overall_pass = False

    try:
        report["stages"]["clean_export"] = run_clean_export(source_path)
    except Exception as exc:
        report["stages"]["clean_export"] = {"error": str(exc)}
        overall_pass = False

    try:
        report["stages"]["credential_binding"] = bind_credentials()
    except Exception as exc:
        report["stages"]["credential_binding"] = {"error": str(exc)}
        overall_pass = False

    try:
        report["stages"]["production_qa_and_hpe_proof"] = check_production_qa_and_hpe_proof(status_json_path)
    except Exception as exc:
        report["stages"]["production_qa_and_hpe_proof"] = {"error": str(exc)}
        overall_pass = False

    if "error" not in report["stages"].get("clean_export", {"error": True}):
        clean_path = Path(report["stages"]["clean_export"]["clean_derivative_path"])
        try:
            report["stages"]["duplicate_check_final"] = run_duplicate_check(clean_path, status_json_path)
            if report["stages"]["duplicate_check_final"]["is_duplicate"]:
                overall_pass = False
        except Exception as exc:
            report["stages"]["duplicate_check_final"] = {"error": str(exc)}
            overall_pass = False
    else:
        overall_pass = False

    caption_stage = report["stages"].get("caption_selection") or {}
    report["caption_bank_low_inventory_warning"] = bool(
        isinstance(caption_stage, dict) and (caption_stage.get("inventory") or {}).get("low_inventory_warning")
    )
    report["caption_bank_exhausted_after_selection"] = bool(
        isinstance(caption_stage, dict) and (caption_stage.get("inventory") or {}).get("exhausted_after_selection")
    )

    report["proof_gate_passed"] = overall_pass
    report["approval_still_required"] = True
    report["approval_mode_supported"] = ["manual", "autonomous"]
    report["approval_mode_not_implemented"] = []
    report["autonomous_mode_requires"] = (
        "an active, validated, durable standing Reels-lane autonomy authorization -- see "
        "issue_standing_lane_autonomy_authorization() / validate_standing_lane_autonomy_authorization() -- "
        "plus, automatically derived at publish time, a single-use execution claim for this asset "
        "(see claim_execution())."
    )

    out_path = asset_dir / f"offline_proof_gate_{_now().replace(':', '')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(out_path)
    return report


# ---------------------------------------------------------------------------
# Standing Reels-lane autonomy authorization -- durable, lane-level, NOT
# asset-specific and NOT single-use. Issued once (renewed periodically) by
# a human via issue_standing_lane_autonomy_authorization(); every autonomous
# publish attempt re-validates it fresh via
# validate_standing_lane_autonomy_authorization(). This is the fail-closed
# gate that replaces the old, removed per-asset "lane autonomy
# authorization" -- see claim_execution() below for the per-asset single-use
# artifact this standing authority is used to derive automatically.
#
# Trust model matches the rest of this repo's offline governance artifacts
# (e.g. the photo lane's standing-autonomy policy): plain local JSON, no
# cryptographic signing, enforced by strict schema/state validation -- not
# by an unforgeable signature. What makes this a real gate rather than a
# rubber stamp is that it must be issued as a deliberate, separate step
# before any autonomous publish attempt exists, is bounded in time (forcing
# periodic human reconfirmation), and can be revoked instantly via
# revoke_standing_lane_autonomy_authorization().
# ---------------------------------------------------------------------------

def _ensure_within_root(path: Path, root: Path, *, label: str) -> Path:
    resolved = path.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PipelineError(f"{label} path escapes required root: {resolved} (root: {root_resolved})") from exc
    return resolved


def _parse_iso_utc(raw: str, *, label: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PipelineError(f"{label} must be ISO-8601: {raw!r}") from exc
    if dt.tzinfo is None:
        raise PipelineError(f"{label} must include timezone information")
    return dt.astimezone(timezone.utc)


def issue_standing_lane_autonomy_authorization(
    *, ttl_seconds: int = STANDING_AUTONOMY_DEFAULT_TTL_SECONDS, force: bool = False,
) -> dict[str, Any]:
    """Issue the one durable standing Reels-lane autonomy authorization.
    Deliberate, human-run, lane-level -- not asset-specific, not per-post.
    Refuses to silently replace an existing standing authorization unless
    force=True (revoke_standing_lane_autonomy_authorization() is the normal
    way to retire one)."""
    if ttl_seconds <= 0 or ttl_seconds > STANDING_AUTONOMY_MAX_TTL_SECONDS:
        raise PipelineError(
            f"ttl_seconds={ttl_seconds} is invalid -- must be > 0 and <= {STANDING_AUTONOMY_MAX_TTL_SECONDS}"
        )
    if STANDING_AUTHORIZATION_PATH.exists() and not force:
        raise PipelineError(
            f"a standing authorization already exists at {STANDING_AUTHORIZATION_PATH} -- revoke it "
            "first via revoke_standing_lane_autonomy_authorization(), or pass force=True to replace it"
        )

    issued_dt = datetime.now(timezone.utc).replace(microsecond=0)
    expires_dt = issued_dt + timedelta(seconds=ttl_seconds)
    payload = {
        "schema_version": LANE_AUTONOMY_SCHEMA_VERSION,
        "report_type": STANDING_AUTONOMY_REPORT_TYPE,
        "authorization_mode": STANDING_AUTONOMY_MODE,
        "authorization_issuer": LANE_AUTONOMY_ISSUER,
        "platform": "Instagram Reels",
        "kill_switch_enabled": True,
        "revoked": False,
        "revoked_at_utc": None,
        "issued_at_utc": issued_dt.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": expires_dt.isoformat().replace("+00:00", "Z"),
    }
    STANDING_AUTHORIZATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    STANDING_AUTHORIZATION_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**payload, "standing_authorization_path": str(STANDING_AUTHORIZATION_PATH)}


def validate_standing_lane_autonomy_authorization(path: Optional[Path] = None) -> dict[str, Any]:
    """Read-only. Raises PipelineError on any hard-fail condition: missing
    file, malformed JSON, wrong schema/mode/issuer/platform, kill switch not
    enabled, revoked, malformed or missing timestamps, excessive TTL, or
    expiry. No bypass flag exists anywhere in this function, by design."""
    resolved_path = Path(path) if path is not None else STANDING_AUTHORIZATION_PATH
    resolved_path = _ensure_within_root(resolved_path, LANE_AUTONOMY_ROOT, label="standing lane-autonomy authorization")
    if not resolved_path.is_file():
        raise PipelineError(
            f"no standing Reels lane-autonomy authorization exists at {resolved_path} -- autonomous "
            "mode requires one to be issued first via issue_standing_lane_autonomy_authorization()"
        )
    try:
        auth = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PipelineError(f"standing lane-autonomy authorization is not valid JSON: {exc}") from exc
    if not isinstance(auth, dict):
        raise PipelineError("standing lane-autonomy authorization must be a JSON object")

    def _require(cond: bool, msg: str) -> None:
        if not cond:
            raise PipelineError(f"standing lane-autonomy authorization rejected: {msg}")

    _require(auth.get("report_type") == STANDING_AUTONOMY_REPORT_TYPE, "report_type mismatch")
    _require(auth.get("schema_version") == LANE_AUTONOMY_SCHEMA_VERSION, "schema_version mismatch")
    _require(auth.get("authorization_mode") == STANDING_AUTONOMY_MODE, "authorization_mode mismatch")
    _require(auth.get("authorization_issuer") == LANE_AUTONOMY_ISSUER, "authorization_issuer mismatch")
    _require(auth.get("platform") == "Instagram Reels", "platform must be 'Instagram Reels'")
    _require(auth.get("kill_switch_enabled") is True, "kill_switch_enabled must be true")
    _require(auth.get("revoked") is False, "standing authorization has been revoked")

    issued_raw = auth.get("issued_at_utc")
    expires_raw = auth.get("expires_at_utc")
    _require(isinstance(issued_raw, str) and bool(issued_raw.strip()), "issued_at_utc is required")
    _require(isinstance(expires_raw, str) and bool(expires_raw.strip()), "expires_at_utc is required")
    issued_dt = _parse_iso_utc(issued_raw, label="issued_at_utc")
    expires_dt = _parse_iso_utc(expires_raw, label="expires_at_utc")
    now = datetime.now(timezone.utc)
    _require(issued_dt <= now, "issued_at_utc is in the future -- clock skew or tampering")
    _require(expires_dt > issued_dt, "expires_at_utc must be after issued_at_utc")
    _require(
        (expires_dt - issued_dt).total_seconds() <= STANDING_AUTONOMY_MAX_TTL_SECONDS,
        f"authorization TTL exceeds the maximum allowed {STANDING_AUTONOMY_MAX_TTL_SECONDS}s",
    )
    _require(now < expires_dt, "standing lane-autonomy authorization has expired -- renew it")

    return {**auth, "_validated_path": str(resolved_path)}


def revoke_standing_lane_autonomy_authorization(path: Optional[Path] = None) -> dict[str, Any]:
    """Instant kill switch: marks the standing authorization revoked=True.
    Every subsequent validate_standing_lane_autonomy_authorization() call
    fails closed until a new one is issued."""
    resolved_path = Path(path) if path is not None else STANDING_AUTHORIZATION_PATH
    if not resolved_path.is_file():
        raise PipelineError(f"no standing authorization exists at {resolved_path} to revoke")
    data = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    data["revoked"] = True
    data["revoked_at_utc"] = _now()
    tmp_path = resolved_path.with_name(f"{resolved_path.name}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(resolved_path)
    return data


# ---------------------------------------------------------------------------
# Per-asset, single-use execution claim -- automatically derived at publish
# time (never issued ahead of time by a human, unlike the standing
# authorization above). This is both the atomic concurrency guard
# (os.open(..., O_CREAT | O_EXCL)) and the durable record used for crash
# recovery. Lifecycle: claimed -> published_pending_closure -> closed.
# ---------------------------------------------------------------------------

def _safe_slot_filename(slot_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in slot_id)[:150]


def _execution_claim_path(slot_id: str) -> Path:
    return LANE_AUTONOMY_CLAIM_ROOT / f"{_safe_slot_filename(slot_id)}.claim.json"


def claim_execution(
    slot_id: str,
    *,
    asset_dir: Path,
    source_path: Path,
    source_sha256: str,
    caption_bank_id: str,
    caption_text: str,
    fingerprint: str,
    approval_mode: str,
    standing_authorization: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Atomic, single-use execution claim -- MUST be created before any
    upload or Graph call for this asset. os.open(..., O_CREAT | O_EXCL) is
    the actual concurrency guard: a second, concurrent (or later, retried)
    call for the same slot_id fails closed here, before any network code
    path is reached. The claim file is never deleted/released by this
    module: once an asset is claimed, it is claimed permanently. Recovery
    after a genuine crash goes through reconcile_stale_execution_claim() /
    complete_pending_closure(), never through deleting this file."""
    LANE_AUTONOMY_CLAIM_ROOT.mkdir(parents=True, exist_ok=True)
    claim_path = _execution_claim_path(slot_id)
    try:
        fd = os.open(str(claim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise PipelineError(
            f"execution claim already exists for slot {slot_id!r} at {claim_path} -- refusing "
            "concurrent or duplicate publish. See reconcile_stale_execution_claim() and the "
            "crash-recovery runbook before ever touching this file by hand."
        ) from exc
    payload = {
        "schema_version": "v1",
        "report_type": "lena_reels_execution_claim",
        "state": "claimed",
        "approval_mode": approval_mode,
        "slot_id": slot_id,
        "asset_dir": str(asset_dir),
        "source_path": str(source_path),
        "source_sha256": source_sha256,
        "caption_bank_id": caption_bank_id,
        "caption_text": caption_text,
        "fingerprint": fingerprint,
        "standing_authorization_path": (standing_authorization or {}).get("path"),
        "standing_authorization_sha256": (standing_authorization or {}).get("sha256"),
        "claimed_at_utc": _now(),
        "pid": os.getpid(),
        "publish_result": None,
        "published_at_utc": None,
        "closed_at_utc": None,
    }
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2, ensure_ascii=True))
    except Exception:
        claim_path.unlink(missing_ok=True)
        raise
    return {"path": claim_path, "payload": payload}


def _rewrite_claim(claim_path: Path, **updates: Any) -> dict[str, Any]:
    current = json.loads(claim_path.read_text(encoding="utf-8-sig"))
    current.update(updates)
    tmp_path = claim_path.with_name(f"{claim_path.name}.tmp")
    tmp_path.write_text(json.dumps(current, indent=2, ensure_ascii=True), encoding="utf-8")
    tmp_path.replace(claim_path)
    return current


def mark_claim_published(claim_path: Path, publish_result: dict[str, Any]) -> dict[str, Any]:
    """Checkpoint written immediately after publish_post() returns
    successfully -- i.e. immediately after the one real, non-idempotent
    network action this whole pipeline performs. From this point on, crash
    recovery never needs to call publish_post() again:
    complete_pending_closure() finishes bookkeeping from what is recorded
    here alone."""
    return _rewrite_claim(
        claim_path,
        state="published_pending_closure",
        publish_result=publish_result,
        published_at_utc=_now(),
    )


def close_execution_claim(claim_path: Path) -> dict[str, Any]:
    return _rewrite_claim(claim_path, state="closed", closed_at_utc=_now())


def reconcile_stale_execution_claim(
    claim_path: Path, *, stale_after_seconds: int = STALE_CLAIM_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Read-only. Never mutates anything, never calls publish_post(), never
    makes a network call. Returns a structured recommendation; the caller
    (an operator, or complete_pending_closure()) decides what to do. See
    tools/lena_reels_execution_claim_recovery_runbook.md."""
    claim = json.loads(claim_path.read_text(encoding="utf-8-sig"))
    state = claim.get("state")
    if state == "closed":
        return {"action": "none", "reason": "execution claim is already closed", "claim": claim}
    if state == "published_pending_closure":
        media_id = (claim.get("publish_result") or {}).get("instagram_media_id")
        return {
            "action": "complete_pending_closure",
            "reason": (
                "publish_post() already succeeded and returned a real Instagram media id "
                f"({media_id}) -- safe to finish bookkeeping (fingerprint + sidecar + claim "
                "closure) without any further network call"
            ),
            "claim": claim,
        }
    if state == "claimed":
        claimed_at = _parse_iso_utc(claim["claimed_at_utc"], label="claimed_at_utc")
        age_seconds = (datetime.now(timezone.utc) - claimed_at).total_seconds()
        if age_seconds < stale_after_seconds:
            return {
                "action": "wait",
                "reason": f"claim is only {age_seconds:.0f}s old -- a publish attempt may still be in flight",
                "claim": claim,
            }
        return {
            "action": "manual_verification_required",
            "reason": (
                f"claim has been in state='claimed' for {age_seconds:.0f}s (>= {stale_after_seconds}s) "
                "with no recorded publish result -- it is NOT safe to infer whether the real Instagram "
                "publish call ever completed. An operator must check the Instagram account directly "
                "(or via the read-only preflight) for this asset's caption before doing anything else. "
                "Never retry by deleting this claim without that check -- see the crash-recovery runbook."
            ),
            "claim": claim,
        }
    raise PipelineError(f"execution claim has unrecognized state: {state!r}")


def _complete_closure(
    asset_dir: Path,
    clean_path: Path,
    caption_text: str,
    publish_result: dict[str, Any],
    approval_mode: str,
    slot_id: str,
    claim_path: Path,
) -> None:
    """Shared by both the happy path (_finalize_publish) and crash recovery
    (complete_pending_closure) -- there is exactly one implementation of
    exactly-once closure, never two that could silently diverge."""
    from pipeline.lena_publish_quality_gate import mark_published_fingerprint, QualityGateConfig
    mark_published_fingerprint(
        clean_path,
        config=QualityGateConfig(),
        extra={
            "media_type": "reel",
            "instagram_media_id": publish_result.get("instagram_media_id"),
            "permalink": publish_result.get("permalink"),
            "caption": caption_text,
            "published_at_utc": _now(),
            "approval_mode": approval_mode,
            "slot_id": slot_id,
            "execution_claim_path": str(claim_path),
        },
    )

    sidecar_candidates = list(Path(asset_dir).glob("*.status.json"))
    if sidecar_candidates:
        sidecar_path = sidecar_candidates[0]
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        data["instagram_published"] = True
        data["instagram_currently_live"] = True
        data["publish_result"] = {
            "published_at_utc": _now(),
            "instagram_media_id": publish_result.get("instagram_media_id"),
            "permalink": publish_result.get("permalink"),
            "caption": caption_text,
            "approval_mode": approval_mode,
        }
        tmp_path = sidecar_path.with_name(f"{sidecar_path.name}.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(sidecar_path)

    close_execution_claim(claim_path)


def complete_pending_closure(claim_path: Path) -> dict[str, Any]:
    """Safe, network-free crash recovery for the 'published_pending_closure'
    state: publish_post() is known (from the claim's own recorded result) to
    have already succeeded, so this finishes fingerprint + sidecar + claim
    closure using that recorded result. Never calls publish_post() again."""
    claim = json.loads(claim_path.read_text(encoding="utf-8-sig"))
    if claim.get("state") != "published_pending_closure":
        raise PipelineError(
            "complete_pending_closure() requires state='published_pending_closure', got "
            f"{claim.get('state')!r} -- call reconcile_stale_execution_claim() first"
        )
    from tools.lena_scrub_media_metadata_v1 import resolve_clean_output_path
    clean_path = resolve_clean_output_path(Path(claim["source_path"]))
    _complete_closure(
        Path(claim["asset_dir"]), clean_path, claim["caption_text"], claim["publish_result"],
        claim["approval_mode"], claim["slot_id"], claim_path,
    )
    return {"ok": True, "claim_path": str(claim_path)}


# ---------------------------------------------------------------------------
# Shared, single source of truth for the asset/credential/route/caption
# context used by BOTH run_publish() below and the read-only preflight
# (tools/lena_reels_live_preflight_readonly.py). Guarantees consistency by
# construction rather than by duplicated constants.
# ---------------------------------------------------------------------------

def resolve_reels_publish_context(asset_dir: Path, source_path: Optional[Path] = None) -> dict[str, Any]:
    """Read-only: makes no network call, does not scrub, does not
    select/consume/mark anything in the caption bank (select_caption() never
    writes), does not claim execution, does not touch any authorization."""
    from pipeline.publisher.instagram_graph_adapter import ENV_ALIASES as IG_ENV_ALIASES, _api_base

    asset_dir = asset_dir.resolve()
    resolved_source = (source_path or find_source_mp4(asset_dir)).resolve()

    caption_preview: Optional[dict[str, Any]] = None
    caption_preview_error: Optional[str] = None
    try:
        caption_preview = select_caption(asset_dir)
    except PipelineError as exc:
        caption_preview_error = str(exc)

    return {
        "asset_dir": str(asset_dir),
        "source_path": str(resolved_source),
        "source_sha256": _sha256_file(resolved_source),
        "platform": "Instagram Reels",
        "api_base": _api_base(),
        "credential_env_aliases": dict(IG_ENV_ALIASES),
        "caption_preview": caption_preview,
        "caption_preview_error": caption_preview_error,
    }


# ---------------------------------------------------------------------------
# Publish stage -- exists for reuse, not exercised by this file's __main__
# unless explicitly requested with --mode publish.
# ---------------------------------------------------------------------------

def _finalize_publish(
    asset_dir: Path,
    source_path: Path,
    clean_path: Path,
    caption_stage: dict[str, Any],
    *,
    approval_mode: str,
    slot_id: str,
    standing_authorization: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    fingerprint = _sha256_file(clean_path)
    caption_text = caption_stage["text"]

    # Atomic single-use execution claim -- MUST happen before any upload or
    # Graph call. Everything after this line touches the network.
    claim = claim_execution(
        slot_id,
        asset_dir=asset_dir,
        source_path=source_path,
        source_sha256=_sha256_file(source_path),
        caption_bank_id=caption_stage["bank_id"],
        caption_text=caption_text,
        fingerprint=fingerprint,
        approval_mode=approval_mode,
        standing_authorization=standing_authorization,
    )
    claim_path = claim["path"]

    from pipeline.env_loader import load_env_once
    load_env_once(REPO_ROOT, override=True)
    from pipeline.publisher.instagram_graph_adapter import publish_post, InstagramPublishError

    payload = {
        "post_id": f"lena_{slot_id}",
        "media_type": "reel",
        "caption": caption_text,
        "media_path": str(clean_path),
        "metadata": {"source_asset_path": str(source_path)},
        "platforms": ["instagram"],
    }
    try:
        result = publish_post(payload)
    except InstagramPublishError as exc:
        raise PipelineError(f"Instagram publish failed: {exc}") from exc

    # Checkpoint: the real network call succeeded. Record this BEFORE doing
    # any further bookkeeping so a crash from here on is always recoverable
    # via complete_pending_closure() without ever calling publish_post()
    # again.
    mark_claim_published(claim_path, result)
    _complete_closure(asset_dir, clean_path, caption_text, result, approval_mode, slot_id, claim_path)

    return {**result, "execution_claim_path": str(claim_path), "approval_mode": approval_mode}


def run_publish(
    asset_dir: Path,
    approval_mode: str,
    confirm_publish: Optional[str] = None,
    *,
    standing_authorization_artifact: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Real, single publish_post() call -- one network call, one provider call.

    approval_mode="manual" requires confirm_publish to equal, exactly, the
    proof gate's selected caption text -- a live, asset-specific human
    action, not a stored bit that could be set once and reused silently for
    different future content.

    approval_mode="autonomous" requires an active, validated, durable
    standing Reels-lane autonomy authorization (see
    issue_standing_lane_autonomy_authorization() /
    validate_standing_lane_autonomy_authorization()). If standing_
    authorization_artifact is not given, the canonical STANDING_AUTHORIZATION_PATH
    is used. From that standing authority, a single-use execution claim is
    derived automatically for this specific asset (see claim_execution()) --
    there is no autonomous path that runs without both. Autonomous mode
    additionally refuses if this selection would fully exhaust the caption
    bank (see CAPTION_BANK_WARN_THRESHOLD) -- it will not run itself
    completely dry unattended, though it does not block on a low-but-
    nonzero remaining count (that is surfaced as a warning only).
    """
    asset_dir = asset_dir.resolve()
    slot_id = asset_dir.name

    if approval_mode == "autonomous":
        standing_path = Path(standing_authorization_artifact) if standing_authorization_artifact else STANDING_AUTHORIZATION_PATH
        standing = validate_standing_lane_autonomy_authorization(standing_path)
        validated_path = Path(standing["_validated_path"])
        standing_ref = {"path": str(validated_path), "sha256": _sha256_file(validated_path)}

        source_path = find_source_mp4(asset_dir)
        proof = run_offline_proof_gate(asset_dir, source_path)
        if not proof["proof_gate_passed"]:
            raise PipelineError(
                f"offline proof gate did not pass -- refusing autonomous publish. Report: {proof['report_path']}"
            )

        caption_stage = proof["stages"].get("caption_selection") or {}
        if "error" in caption_stage:
            raise PipelineError(f"caption selection failed: {caption_stage['error']}")
        if (caption_stage.get("inventory") or {}).get("exhausted_after_selection"):
            raise PipelineError(
                "caption_bank_exhausted: this selection would leave zero unused, reviewed captions "
                f"in {CAPTION_BANK_PATH} -- refusing to run autonomous publish unattended; a human "
                "must add and review new lines before autonomous publishing can continue. This does "
                "not invent new captions."
            )

        clean_path = Path(proof["stages"]["clean_export"]["clean_derivative_path"])
        return _finalize_publish(
            asset_dir, source_path, clean_path, caption_stage,
            approval_mode="autonomous", slot_id=slot_id, standing_authorization=standing_ref,
        )

    if approval_mode != "manual":
        raise PipelineError(f"unknown approval_mode: {approval_mode!r}")

    proof = run_offline_proof_gate(asset_dir)
    if not proof["proof_gate_passed"]:
        raise PipelineError(f"offline proof gate did not pass -- refusing to publish. Report: {proof['report_path']}")

    caption_stage = proof["stages"]["caption_selection"]
    if confirm_publish != caption_stage["text"]:
        raise PipelineError(
            "confirm_publish did not exactly match the proof gate's selected caption -- "
            "refusing to publish. This is the human checkpoint; it must be given fresh, "
            "per asset, matching the exact text that will actually be posted."
        )

    clean_path = Path(proof["stages"]["clean_export"]["clean_derivative_path"])
    source_path = Path(proof["source_path"])
    return _finalize_publish(
        asset_dir, source_path, clean_path, caption_stage,
        approval_mode="manual", slot_id=slot_id,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", default=None, help="Required for --mode offline-proof/publish")
    parser.add_argument("--source", default=None, help="Explicit source .mp4 path (optional)")
    parser.add_argument(
        "--mode",
        choices=[
            "offline-proof",
            "publish",
            "issue-standing-authorization",
            "revoke-standing-authorization",
            "reconcile-claim",
        ],
        default="offline-proof",
    )
    parser.add_argument("--approval-mode", choices=["manual", "autonomous"], default="manual")
    parser.add_argument("--confirm-publish", default=None, help="Must exactly equal the selected caption text")
    parser.add_argument("--ttl-seconds", type=int, default=STANDING_AUTONOMY_DEFAULT_TTL_SECONDS)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--claim-path", default=None, help="Required for --mode reconcile-claim")
    parser.add_argument(
        "--standing-authorization-path", default=None,
        help="Override the standing authorization artifact path (isolated testing/ops use only)",
    )
    args = parser.parse_args()

    if args.standing_authorization_path:
        global STANDING_AUTHORIZATION_PATH
        STANDING_AUTHORIZATION_PATH = Path(args.standing_authorization_path)

    try:
        if args.mode == "issue-standing-authorization":
            record = issue_standing_lane_autonomy_authorization(ttl_seconds=args.ttl_seconds, force=args.force)
            print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
            return 0

        if args.mode == "revoke-standing-authorization":
            record = revoke_standing_lane_autonomy_authorization()
            print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
            return 0

        if args.mode == "reconcile-claim":
            if not args.claim_path:
                parser.error("--mode reconcile-claim requires --claim-path")
            recommendation = reconcile_stale_execution_claim(Path(args.claim_path))
            if recommendation["action"] == "complete_pending_closure":
                recommendation["completed"] = complete_pending_closure(Path(args.claim_path))
            print(json.dumps(recommendation, indent=2, ensure_ascii=False, default=str))
            return 0

        if not args.asset_dir:
            parser.error(f"--asset-dir is required for --mode {args.mode}")
        asset_dir = Path(args.asset_dir)
        source = Path(args.source) if args.source else None

        if args.mode == "offline-proof":
            report = run_offline_proof_gate(asset_dir, source)
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0 if report["proof_gate_passed"] else 1

        result = run_publish(asset_dir, args.approval_mode, args.confirm_publish)
        print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False, default=str))
        return 0
    except PipelineError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
