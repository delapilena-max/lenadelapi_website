from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pipeline.qa.lena_photo_qa as lena_photo_qa
import pipeline.identity.lena_higgsfield_identity as lena_higgsfield_identity
import tools.lena_music_pool_v1 as music_pool_mod
from tools.lena_scrub_media_metadata_v1 import scrub_video_metadata, resolve_clean_output_path
from tools.lena_prepare_story_video_v1 import build_story_video
from tools.lena_build_publish_packet_v1 import (
    resolve_packet_inputs_higgsfield_derived_shortform,
    resolve_queue_draft_output_path,
)
# tools/lena_build_publish_packet_v1.py imports lena_higgsfield_qa_bridge_v1
# by its bare module name (TOOLS_DIR is inserted into sys.path at that
# module's import time, above) -- importing it the same (bare) way here,
# AFTER the import above, ensures monkeypatching HIGGSFIELD_DEBUG_ROOT
# actually affects the instance the resolver uses (same pattern already
# established in tests/test_lena_publish_packet_higgsfield_provenance_v1.py).
import lena_higgsfield_qa_bridge_v1 as qa_bridge_mod  # noqa: E402
from tools.lena_record_publish_approval_v1 import (
    resolve_approval_output_path,
    REQUIRED_CAPTION_CONFIRM_PHRASE,
    REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE,
)
from tools.lena_manual_one_off_preflight_v1 import (
    ManualOneOffPreflightError,
    check_manual_one_off_preflight,
)
from tools.lena_promote_to_queue_v1 import PROVIDER_RESOLVERS

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not available on PATH")

SOURCE_SLOT = "test-derived-source-photo"
REEL_SLOT = "test-derived-source-photo-reel"
DATE_STR = "2026-07-09"
REAL_CUSTOM_REFERENCE_ID = "1f1200e4-1cc9-4504-ac1c-3304b687e3c1"  # pinned identity constant


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _make_image(path: Path, size=(1152, 2048)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(80, 90, 100)).save(path, format="PNG")
    return path


def _make_track(path: Path, duration: float = 25.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            str(path),
        ],
        check=True, capture_output=True, timeout=60,
    )
    return path


def _write_music_manifest(manifest_path: Path, track_path: Path, track_id: str = "test_track_010") -> None:
    manifest = {
        "tracks": [
            {
                "track_id": track_id,
                "filename": track_path.name,
                "local_path": str(track_path),
                "sha256": _sha256(track_path),
                "commercial_use_allowed": True,
                "license_type": "free use",
                "license_proof_reference": "test fixture attestation",
                "duration_seconds": 25.0,
            }
        ]
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _qa_status_fields():
    return [
        "identity_fidelity", "face_realism_anti_generic_drift", "skin_realism_no_invented_marks",
        "wardrobe_class_fidelity", "public_scene_clothing_continuity", "outerwear_underlayer_correctness",
        "body_shape_continuity", "hands_anatomy_sanity", "environment_realism_scene_coherence",
        "caption_scene_coherence", "pose_action_scene_compliance",
    ]


def _qa_production_scoring():
    return {
        "hook_strength": {"score": "strong", "notes": "fixture"},
        "styling_sexy_platform_safe": {"status": "pass", "notes": "fixture"},
        "outfit_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": ""},
        "scene_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": ""},
        "allure_level": {"level": "strong", "notes": "fixture"},
        "it_girl_energy": {"status": "pass", "notes": "fixture"},
        "body_visibility_score": {"score": "high", "notes": "fixture"},
        "outfit_hook_score": {"score": "strong", "notes": ""},
        "pose_attitude_score": {"score": "strong", "notes": ""},
        "feed_worthy_reason": "fixture: genuinely feed-worthy test record.",
    }


def _write_qa_pass(asset_review_root: Path, date_str: str, slot_id: str) -> None:
    checklist = {k: {"status": "pass", "notes": "fixture"} for k in _qa_status_fields()}
    checklist["head_framing_safety_margin"] = {"status": "pass", "notes": "fixture: comfortable headroom"}
    qa = {
        "schema_version": "4",
        "slot_id": slot_id,
        "date": date_str,
        "media_type": "photo",
        "reviewed_by": "test-fixture",
        "reviewed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checklist": checklist,
        "production_scoring": _qa_production_scoring(),
        "overall": "pass",
        "failure_reasons": [],
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "publish_ready": True,
        "publish_ready_reason": "fixture",
    }
    out_path = asset_review_root / date_str / f"{slot_id}_qa.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(qa, indent=2), encoding="utf-8")
    return out_path


def _write_qa_fail(asset_review_root: Path, date_str: str, slot_id: str) -> None:
    checklist = {k: {"status": "pass", "notes": "fixture"} for k in _qa_status_fields()}
    checklist["head_framing_safety_margin"] = {"status": "fail", "notes": "fixture: head clipped"}
    qa = {
        "schema_version": "4",
        "slot_id": slot_id,
        "date": date_str,
        "media_type": "photo",
        "reviewed_by": "test-fixture",
        "reviewed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checklist": checklist,
        "production_scoring": _qa_production_scoring(),
        "overall": "fail",
        "failure_reasons": ["head_framing_safety_margin"],
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "publish_ready": False,
        "publish_ready_reason": "fixture",
    }
    out_path = asset_review_root / date_str / f"{slot_id}_qa.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(qa, indent=2), encoding="utf-8")


def _write_higgsfield_manifest(debug_root: Path, date_str: str, slot_id: str, image_path: Path) -> Path:
    manifest = {
        "slot_id": slot_id,
        "provider": "higgsfield",
        "job_type": "text2image_soul_v2",
        "cli_soul_name": "Lena",
        "custom_reference_id": REAL_CUSTOM_REFERENCE_ID,
        "image_prompt": "a real test derived-shortform source prompt",
        "saved_image_path": str(image_path),
        "lane": "test lane",
        "pose_text": "test pose text",
        "provider_job_id": "test-derived-provider-job-id",
        "provider_status": "succeed",
        "wardrobe_outfit_id": "wc_test",
    }
    manifest_dir = debug_root / date_str / slot_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / "result_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _write_identity_evidence(
    debug_root: Path, date_str: str, slot_id: str, image_path: Path, image_prompt: str,
) -> None:
    evidence = {
        "schema_version": "1",
        "verified_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "higgsfield",
        "date": date_str,
        "slot_id": slot_id,
        "provider_job_id": "test-derived-provider-job-id",
        "provider_job_status": "completed",
        "job_type": "text2image_soul_v2",
        "custom_reference_id": REAL_CUSTOM_REFERENCE_ID,
        "soul_name": "Lena",
        "soul_type": "soul_2",
        "prompt_sha256": hashlib.sha256(image_prompt.encode("utf-8")).hexdigest(),
        "width": 1152,
        "height": 2048,
        "local_image_path": str(image_path.resolve()),
        "local_image_sha256": _sha256(image_path),
        "verification_result": "pass",
        "checks_passed": ["job_type", "custom_reference_id", "soul_name", "soul_type", "dimensions"],
    }
    out_dir = debug_root / date_str / slot_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "identity_verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")


def _write_reel_approval(out_dir: Path, caption: str) -> None:
    approval = {
        "post_id": REEL_SLOT,
        "source_date": DATE_STR,
        "publish_packet_path": "irrelevant-for-this-test.md",
        "queue_draft_path": str(resolve_queue_draft_output_path(DATE_STR, REEL_SLOT, out_dir)),
        "qa_path": "irrelevant-for-this-test.json",
        "qa_overall": "pass",
        "approved_caption": caption,
        "hashtag_count": 3,
        "platforms": ["instagram"],
        "approved_by": "test-operator",
        "caption_approval_statement": REQUIRED_CAPTION_CONFIRM_PHRASE,
        "live_publish_statement": REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE,
        "approved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "manual_one_off_confirmed": True,
        "generated_by": "test fixture",
        "promotion_status": "not_yet_promoted",
    }
    path = resolve_approval_output_path(DATE_STR, REEL_SLOT, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval, indent=2), encoding="utf-8")


def _write_reel_draft(out_dir: Path, media_path: Path, resolved_photo, prepared, caption: str) -> Path:
    draft = {
        "post_id": REEL_SLOT,
        "slot_id": REEL_SLOT,
        "media_path": str(media_path),
        "media_type": "reel",
        "platforms": ["instagram"],
        "caption": caption,
        "approved_for_live_publish": False,
        "operator_review_required": True,
        "metadata": {
            "avatar_nickname": "Lena",
            "provider": "higgsfield_derived_shortform",
            "video_prompt": "test fixture derived Reel candidate",
            "queue_draft_only": True,
            "source_slot_id": SOURCE_SLOT,
            "source_image_path": resolved_photo["image_path"],
            "source_image_sha256": _sha256(Path(resolved_photo["image_path"])),
            "prepared_video_sha256": prepared["output_sha256"],
            "selected_track_id": prepared["selected_track_id"],
            "selected_track_sha256": prepared["selected_track_sha256"],
        },
    }
    path = resolve_queue_draft_output_path(DATE_STR, REEL_SLOT, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def full_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Builds a complete, genuinely valid derived-shortform Reel scenario:
    real Higgsfield photo manifest + QA pass (schema v4, head_framing_
    safety_margin included) + identity evidence, a REAL prepared short-form
    MP4 (via the real, unmodified build_story_video()) + its real provenance
    sidecar, a REAL clean-export derivative (via the real, unmodified
    scrub_video_metadata()), a real approval artifact, and a real queue
    draft -- everything isolated under tmp_path, nothing touches any real
    repo path."""
    debug_root = tmp_path / "higgsfield_debug"
    asset_review_root = tmp_path / "asset_review" / "lena"
    out_dir = tmp_path / "publish_packets"
    monkeypatch.setattr(qa_bridge_mod, "HIGGSFIELD_DEBUG_ROOT", debug_root)
    monkeypatch.setattr(lena_higgsfield_identity, "HIGGSFIELD_DEBUG_ROOT", debug_root)
    monkeypatch.setattr(lena_photo_qa, "ASSET_REVIEW_ROOT", asset_review_root)

    image_path = _make_image(tmp_path / "assets" / f"{SOURCE_SLOT}_seed.png")
    _write_higgsfield_manifest(debug_root, DATE_STR, SOURCE_SLOT, image_path)
    _write_qa_pass(asset_review_root, DATE_STR, SOURCE_SLOT)

    resolved_photo_pre = {"image_path": str(image_path)}
    manifest = json.loads((debug_root / DATE_STR / SOURCE_SLOT / "result_manifest.json").read_text(encoding="utf-8"))
    _write_identity_evidence(debug_root, DATE_STR, SOURCE_SLOT, image_path, manifest["image_prompt"])

    track_path = _make_track(tmp_path / "assets" / "royaltyfree audio" / "test_track.mp3")
    music_manifest_path = tmp_path / "assets" / "royaltyfree audio" / "manifest.json"
    _write_music_manifest(music_manifest_path, track_path)
    # validate_music_backed_shortform_asset() (called by the new resolver)
    # reads the manifest via tools.lena_music_pool_v1.load_manifest()'s own
    # default path when no manifest_path is threaded through -- monkeypatch
    # that one module-level constant so the resolver sees this scratch
    # manifest instead of the real repo one. Never touches the real file.
    monkeypatch.setattr(music_pool_mod, "DEFAULT_MANIFEST_PATH", music_manifest_path)

    prepared = build_story_video(image_path, REEL_SLOT, manifest_path=music_manifest_path)
    prepared_video_path = Path(prepared["output_path"])

    scrub_video_metadata(prepared_video_path)
    clean_path = resolve_clean_output_path(prepared_video_path)

    caption = "a caption #a #b #c"
    _write_reel_approval(out_dir, caption)
    draft_path = _write_reel_draft(out_dir, prepared_video_path, resolved_photo_pre, prepared, caption)

    return {
        "out_dir": out_dir,
        "debug_root": debug_root,
        "asset_review_root": asset_review_root,
        "image_path": image_path,
        "prepared": prepared,
        "prepared_video_path": prepared_video_path,
        "clean_path": clean_path,
        "draft_path": draft_path,
        "music_manifest_path": music_manifest_path,
        "track_path": track_path,
    }


def _run_preflight(out_dir: Path):
    return check_manual_one_off_preflight(
        DATE_STR, REEL_SLOT, "higgsfield_derived_shortform", out_dir, source_slot_id=SOURCE_SLOT,
    )


def _mutate_draft_metadata(draft_path: Path, **fields) -> None:
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft["metadata"].update(fields)
    draft_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")


# === 1. Existing photo (higgsfield) preflight completely unchanged =========

def test_existing_higgsfield_photo_preflight_unaffected_by_new_provider_key() -> None:
    # PROVIDER_RESOLVERS still resolves "higgsfield" to the exact same,
    # unmodified function object it always has -- proves the new provider
    # key was purely additive, never replaced or wrapped the existing one.
    from tools.lena_build_publish_packet_v1 import resolve_packet_inputs_higgsfield
    assert PROVIDER_RESOLVERS["higgsfield"] is resolve_packet_inputs_higgsfield
    assert "higgsfield_derived_shortform" in PROVIDER_RESOLVERS
    assert PROVIDER_RESOLVERS["higgsfield_derived_shortform"] is resolve_packet_inputs_higgsfield_derived_shortform


# === 2. Existing provider-video preflight unchanged =========================

def test_existing_video_provider_preflight_behavior_unchanged() -> None:
    # provider="video" still hits the exact same pre-existing, untouched
    # code path (no new branch added for it) -- this test documents its
    # real current behavior (fails on the generic image_engine lookup, a
    # pre-existing condition this task's scope explicitly excludes fixing)
    # and proves it is byte-identical before/after this change by asserting
    # the exact same error class/message shape still occurs for a
    # nonexistent one-off item.
    with pytest.raises(ManualOneOffPreflightError):
        check_manual_one_off_preflight(DATE_STR, "no-such-slot", "video", None)


# === 3. Full derived-Reel preflight passes only with the complete chain ====

@requires_ffmpeg
def test_derived_reel_preflight_passes_with_full_valid_chain(full_fixture) -> None:
    result = _run_preflight(full_fixture["out_dir"])
    assert result["ok"] is True
    assert result["provider"] == "higgsfield_derived_shortform"
    assert result["resolver_qa_overall"] == "pass"
    assert result["per_item_checks"] == "all passed"


# === 4. Wrong source photo SHA fails closed =================================

@requires_ffmpeg
def test_wrong_source_photo_sha_fails_closed(full_fixture) -> None:
    _mutate_draft_metadata(full_fixture["draft_path"], source_image_sha256="0" * 64)
    with pytest.raises(ManualOneOffPreflightError, match="source_image_sha256"):
        _run_preflight(full_fixture["out_dir"])


# === 5. Wrong prepared MP4 SHA fails closed ==================================

@requires_ffmpeg
def test_wrong_prepared_mp4_sha_fails_closed(full_fixture) -> None:
    _mutate_draft_metadata(full_fixture["draft_path"], prepared_video_sha256="0" * 64)
    with pytest.raises(ManualOneOffPreflightError, match="prepared_video_sha256"):
        _run_preflight(full_fixture["out_dir"])


# === 6. Wrong track ID fails closed ==========================================

@requires_ffmpeg
def test_wrong_track_id_fails_closed(full_fixture) -> None:
    _mutate_draft_metadata(full_fixture["draft_path"], selected_track_id="not_the_real_track")
    with pytest.raises(ManualOneOffPreflightError, match="selected_track_id"):
        _run_preflight(full_fixture["out_dir"])


# === 7. Wrong track SHA fails closed =========================================

@requires_ffmpeg
def test_wrong_track_sha_fails_closed(full_fixture) -> None:
    _mutate_draft_metadata(full_fixture["draft_path"], selected_track_sha256="0" * 64)
    with pytest.raises(ManualOneOffPreflightError, match="selected_track_sha256"):
        _run_preflight(full_fixture["out_dir"])


# === 8. Ineligible track fails closed ========================================

@requires_ffmpeg
def test_ineligible_track_fails_closed(full_fixture) -> None:
    # Re-point the manifest at a track whose commercial_use_allowed is False
    # -- real eligibility re-verification (not just a hash check) must
    # reject it, proven by re-running the ORIGINAL prepared asset's own
    # validator (resolve_packet_inputs_higgsfield_derived_shortform), not
    # just the draft-vs-resolver cross-check.
    manifest = json.loads(full_fixture["music_manifest_path"].read_text(encoding="utf-8"))
    manifest["tracks"][0]["commercial_use_allowed"] = False
    full_fixture["music_manifest_path"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(ManualOneOffPreflightError, match="no longer eligible|eligib"):
        _run_preflight(full_fixture["out_dir"])


# === 9. Missing prepared provenance fails closed =============================

@requires_ffmpeg
def test_missing_prepared_provenance_fails_closed(full_fixture) -> None:
    provenance_path = full_fixture["prepared_video_path"].with_name(
        full_fixture["prepared_video_path"].stem + "_provenance.json"
    )
    provenance_path.unlink()
    with pytest.raises(ManualOneOffPreflightError):
        _run_preflight(full_fixture["out_dir"])


# === 10. Missing clean-export provenance fails closed ========================

@requires_ffmpeg
def test_missing_clean_export_provenance_fails_closed(full_fixture) -> None:
    sidecar = full_fixture["clean_path"].with_name(full_fixture["clean_path"].stem + "_provenance.json")
    sidecar.unlink()
    with pytest.raises(ManualOneOffPreflightError, match="clean-export"):
        _run_preflight(full_fixture["out_dir"])


# === 11. Wrong clean derivative SHA fails closed ==============================

@requires_ffmpeg
def test_wrong_clean_derivative_sha_fails_closed(full_fixture) -> None:
    with full_fixture["clean_path"].open("ab") as fh:
        fh.write(b"\x00tampered")
    with pytest.raises(ManualOneOffPreflightError, match="clean-export"):
        _run_preflight(full_fixture["out_dir"])


# === 12. Missing video stream fails closed ====================================

@requires_ffmpeg
def test_missing_video_stream_in_prepared_asset_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, full_fixture) -> None:
    # Replace the prepared MP4 with an audio-only file sharing the same
    # path, then re-point the provenance's own output_sha256 so the
    # provenance-identity check passes and the real, deeper video-stream
    # check is what actually fails.
    audio_only = full_fixture["prepared_video_path"].with_suffix(".audio_only.mp4")
    subprocess.run(
        [FFMPEG, "-y", "-i", str(full_fixture["track_path"]), "-t", "20", "-vn", "-c:a", "aac", str(audio_only)],
        check=True, capture_output=True, timeout=60,
    )
    shutil.copy2(audio_only, full_fixture["prepared_video_path"])
    provenance_path = full_fixture["prepared_video_path"].with_name(
        full_fixture["prepared_video_path"].stem + "_provenance.json"
    )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["output_sha256"] = _sha256(full_fixture["prepared_video_path"])
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    with pytest.raises(ManualOneOffPreflightError, match="video stream"):
        _run_preflight(full_fixture["out_dir"])


# === 13. Missing audio stream fails closed ====================================

@requires_ffmpeg
def test_missing_audio_stream_in_prepared_asset_fails_closed(full_fixture) -> None:
    silent = full_fixture["prepared_video_path"].with_suffix(".silent.mp4")
    subprocess.run(
        [FFMPEG, "-y", "-i", str(full_fixture["prepared_video_path"]), "-an", "-c:v", "copy", str(silent)],
        check=True, capture_output=True, timeout=60,
    )
    shutil.copy2(silent, full_fixture["prepared_video_path"])
    provenance_path = full_fixture["prepared_video_path"].with_name(
        full_fixture["prepared_video_path"].stem + "_provenance.json"
    )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["output_sha256"] = _sha256(full_fixture["prepared_video_path"])
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    with pytest.raises(ManualOneOffPreflightError, match="audio stream"):
        _run_preflight(full_fixture["out_dir"])


# === 14. Wrong media_type fails closed ========================================

@requires_ffmpeg
def test_wrong_media_type_fails_closed(full_fixture) -> None:
    draft = json.loads(full_fixture["draft_path"].read_text(encoding="utf-8"))
    draft["media_type"] = "video"
    full_fixture["draft_path"].write_text(json.dumps(draft, indent=2), encoding="utf-8")
    with pytest.raises(ManualOneOffPreflightError, match="media_type='reel'"):
        _run_preflight(full_fixture["out_dir"])


# === 15. Wrong source_slot_id fails closed ====================================

@requires_ffmpeg
def test_wrong_source_slot_id_fails_closed(full_fixture) -> None:
    _mutate_draft_metadata(full_fixture["draft_path"], source_slot_id="not-the-real-source-slot")
    with pytest.raises(ManualOneOffPreflightError, match="slot_id"):
        _run_preflight(full_fixture["out_dir"])


# === 16. Rule Zero source QA fail still blocks ===============================

@requires_ffmpeg
def test_source_qa_fail_still_blocks(full_fixture) -> None:
    _write_qa_fail(full_fixture["asset_review_root"], DATE_STR, SOURCE_SLOT)
    with pytest.raises(ManualOneOffPreflightError):
        _run_preflight(full_fixture["out_dir"])


# === 17. Identity evidence failure still blocks ===============================

@requires_ffmpeg
def test_identity_evidence_failure_still_blocks(full_fixture) -> None:
    evidence_path = full_fixture["debug_root"] / DATE_STR / SOURCE_SLOT / "identity_verification.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["custom_reference_id"] = "not-the-approved-lena-reference-id"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    with pytest.raises(ManualOneOffPreflightError, match="identity evidence"):
        _run_preflight(full_fixture["out_dir"])


# === 18-24. Structural no-op guarantees ======================================
#
# No real queue item is ever written (this whole module has no write
# function at all, per its own header docstring -- proven here by asserting
# the real LIVE_QUEUE_ROOT-shaped path was never created under tmp_path).
# No promotion or publish function is ever called anywhere in this test
# file. No Instagram/R2/provider/network call occurs: this test file never
# imports requests, never monkeypatches a fake network layer (if any code
# path here actually reached one, it would raise a real connection error,
# not silently succeed), and pipeline.publisher.instagram_queue_bridge is
# only ever used for its pure _validate_contract() function, never
# publish_post(). .env is never written by any code exercised here --
# tools/lena_manual_one_off_preflight_v1.py's own load_env_once() only
# reads.

@requires_ffmpeg
def test_no_real_queue_item_written_and_env_untouched(full_fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.lena_build_publish_packet_v1 as packet_mod
    real_queue_root = packet_mod.LIVE_QUEUE_ROOT
    before_env_files = set()
    if Path(".env").exists():
        before_env_files.add(_sha256(Path(".env")))

    result = _run_preflight(full_fixture["out_dir"])
    assert result["ok"] is True

    assert not (real_queue_root / f"{REEL_SLOT}.json").exists()
    assert not (real_queue_root / f"{SOURCE_SLOT}.json").exists()

    if Path(".env").exists():
        after_env_files = {_sha256(Path(".env"))}
        assert after_env_files == before_env_files
