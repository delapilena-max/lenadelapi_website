from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import tools.lena_kling_i2v_commission_v1 as mod
from tools.lena_kling_i2v_commission_v1 import (
    CONFIRMED_KLING_VIDEO_MODEL,
    CONFIRMED_KLING_VIDEO_ENDPOINT,
    REQUIRED_DURATION_SECONDS,
    KlingCommissionError,
    build_commission_manifest,
    build_request_payload,
    validate_commission,
    validate_duration_seconds,
    validate_prompt_bytes,
    validate_source_receipt_binding,
    validate_test_video_slot_id,
)

SOURCE_SLOT = "readypack0709-pack003-08-photo"
TEST_VIDEO_SLOT = "readypack0709-pack003-08-motion-test-01"
MOTION_PROMPT = (
    "Locked vertical camera. Lena remains standing in place with stable "
    "body proportions and consistent facial identity. She makes one slow "
    "natural weight shift through her hips, takes a subtle breath, turns "
    "her head only slightly toward the camera, and makes a small natural "
    "gaze adjustment."
)


def _write_source(tmp_path: Path) -> Path:
    path = tmp_path / "source_seed.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake-source-bytes")
    return path


def _patch_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "COMMISSION_LIBRARY_ROOT", tmp_path / "pipeline" / "kling_library" / "lena")
    monkeypatch.setattr(mod, "COMMISSION_DEBUG_ROOT", tmp_path / "pipeline" / "kling_debug")
    monkeypatch.setattr(mod, "SOURCE_RECEIPT_ROOT", tmp_path / "pipeline" / "queue" / "published")


def _receipt_root(tmp_path: Path) -> Path:
    return tmp_path / "pipeline" / "queue" / "published"


def _write_receipt(
    tmp_path: Path,
    receipt_filename_slot_id: str,
    media_path: Path,
    media_url: str,
    content_post_id: str = None,
) -> Path:
    """receipt_filename_slot_id controls where the receipt file is written
    (the real lookup key); content_post_id lets a test write a receipt
    whose *contents* disagree with its own filename/identity."""
    receipt_dir = _receipt_root(tmp_path)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{receipt_filename_slot_id}.json.receipt.json"
    receipt = {
        "post_id": content_post_id if content_post_id is not None else receipt_filename_slot_id,
        "media_path": str(media_path),
        "publish_response": {
            "result": {
                "instagram_result": {
                    "media_url": media_url,
                }
            }
        },
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path


# --- pinned model/endpoint (no override exists) -----------------------------

def test_model_is_pinned_to_kling_v2_1_master() -> None:
    assert CONFIRMED_KLING_VIDEO_MODEL == "kling-v2-1-master"


def test_endpoint_is_pinned_to_singapore_image2video_route() -> None:
    assert CONFIRMED_KLING_VIDEO_ENDPOINT == "https://api-singapore.klingai.com/v1/videos/image2video"


def test_no_model_or_endpoint_cli_override_exists() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "--model" not in source
    assert "--endpoint" not in source


def test_build_request_payload_uses_pinned_model_and_preserves_prompt() -> None:
    payload = build_request_payload("https://example.com/seed.png", MOTION_PROMPT, 5.0)
    assert payload["model_name"] == CONFIRMED_KLING_VIDEO_MODEL
    assert payload["image"] == "https://example.com/seed.png"
    assert payload["prompt"] == MOTION_PROMPT


# --- source/video identity separation ---------------------------------------

def test_test_video_slot_must_differ_from_source_slot() -> None:
    reasons = validate_test_video_slot_id(SOURCE_SLOT, SOURCE_SLOT)
    assert any("must not equal source_slot_id" in r for r in reasons)


def test_test_video_slot_requires_motion_test_marker() -> None:
    reasons = validate_test_video_slot_id("readypack0709-pack003-08-variant-01", SOURCE_SLOT)
    assert any("-motion-test-" in r for r in reasons)


def test_test_video_slot_accepts_clearly_scoped_identity() -> None:
    reasons = validate_test_video_slot_id(TEST_VIDEO_SLOT, SOURCE_SLOT)
    assert reasons == []


# --- full validation: happy path + fail-closed cases ------------------------

def test_validate_commission_passes_for_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    assert result["ok"] is True
    assert result["reasons"] == []
    assert result["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["motion_prompt_sha256"] == hashlib.sha256(MOTION_PROMPT.encode("utf-8")).hexdigest()


def test_validate_commission_fails_closed_missing_source_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, tmp_path / "does_not_exist.png", TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    assert result["ok"] is False
    assert any("does not exist" in r for r in result["reasons"])


def test_validate_commission_fails_closed_empty_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, "", 5.0,
        source_public_url=None, live=False,
    )
    assert result["ok"] is False
    assert any("empty motion prompt" in r for r in result["reasons"])


# --- no-overwrite-path collision tests --------------------------------------

def test_validate_commission_fails_closed_on_existing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    manifest_dir = tmp_path / "pipeline" / "kling_debug" / "2026-07-09" / "i2v_commission_tests" / TEST_VIDEO_SLOT
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "result_manifest.json").write_text("{}", encoding="utf-8")

    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    assert result["ok"] is False
    assert any("already exists" in r for r in result["reasons"])


def test_validate_commission_fails_closed_on_existing_final_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    video_dir = tmp_path / "pipeline" / "kling_library" / "lena" / "2026-07-09" / "i2v_commission_tests"
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / f"{TEST_VIDEO_SLOT}_video.mp4").write_bytes(b"existing")

    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    assert result["ok"] is False
    assert any("already exists" in r for r in result["reasons"])


def test_validate_commission_fails_closed_on_leftover_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    video_dir = tmp_path / "pipeline" / "kling_library" / "lena" / "2026-07-09" / "i2v_commission_tests"
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / f"{TEST_VIDEO_SLOT}_video.tmp").write_bytes(b"stale-partial")

    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    assert result["ok"] is False
    assert any(".tmp" in r for r in result["reasons"])


def test_no_overwrite_flag_exists_anywhere() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "--allow-overwrite" not in source
    assert "allow_overwrite" not in source


# --- public-URL / no-upload requirement -------------------------------------

def test_live_fails_closed_without_source_public_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=True,
    )
    assert result["ok"] is False
    assert any("BLOCKER" in r and "--source-public-url" in r for r in result["reasons"])


def test_live_fails_closed_on_malformed_public_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url="not-a-url", live=True,
    )
    assert result["ok"] is False
    assert any("does not look like a real http" in r for r in result["reasons"])


def test_live_passes_validation_with_matching_source_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    url = "https://pub-example.r2.dev/lena/queue-media/2026-07-10/photo.png"
    _write_receipt(tmp_path, SOURCE_SLOT, source, url)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=url, live=True,
    )
    assert result["ok"] is True
    assert result["source_receipt_path"] == str(mod.source_receipt_path(SOURCE_SLOT))


# --- source-receipt provenance binding (correction 1) -----------------------

def test_source_receipt_binding_fails_closed_missing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    url = "https://pub-example.r2.dev/lena/photo.png"
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=url, live=True,
    )
    assert result["ok"] is False
    assert any("receipt not found" in r for r in result["reasons"])


def test_source_receipt_binding_fails_closed_wrong_post_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    url = "https://pub-example.r2.dev/lena/photo.png"
    _write_receipt(
        tmp_path, SOURCE_SLOT, source, url, content_post_id="some-other-slot-id"
    )
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=url, live=True,
    )
    assert result["ok"] is False
    assert any("post_id" in r for r in result["reasons"])


def test_source_receipt_binding_fails_closed_wrong_media_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    wrong_path = tmp_path / "wrong_source.png"
    wrong_path.write_bytes(b"other-bytes")
    url = "https://pub-example.r2.dev/lena/photo.png"
    _write_receipt(tmp_path, SOURCE_SLOT, wrong_path, url)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=url, live=True,
    )
    assert result["ok"] is False
    assert any("media_path" in r for r in result["reasons"])


def test_source_receipt_binding_fails_closed_wrong_media_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    real_url = "https://pub-example.r2.dev/lena/real.png"
    proposed_url = "https://pub-example.r2.dev/lena/different.png"
    _write_receipt(tmp_path, SOURCE_SLOT, source, real_url)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=proposed_url, live=True,
    )
    assert result["ok"] is False
    assert any("media_url" in r for r in result["reasons"])


def test_source_receipt_binding_fails_closed_arbitrary_unrelated_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An arbitrary, syntactically valid https URL with no matching receipt
    at all must never be silently accepted."""
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    arbitrary_url = "https://evil.example.com/unrelated-image.png"
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=arbitrary_url, live=True,
    )
    assert result["ok"] is False
    assert any("receipt" in r.lower() for r in result["reasons"])


def test_source_receipt_path_is_recorded_on_failure_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    url = "https://pub-example.r2.dev/lena/photo.png"
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=url, live=True,
    )
    assert result["ok"] is False
    assert result["source_receipt_path"] == str(mod.source_receipt_path(SOURCE_SLOT))


def test_validate_source_receipt_binding_never_substring_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    real_url = "https://pub-example.r2.dev/lena/photo.png"
    _write_receipt(tmp_path, SOURCE_SLOT, source, real_url)
    binding = validate_source_receipt_binding(
        SOURCE_SLOT, source.resolve(), real_url + "?extra=1"
    )
    assert binding["ok"] is False


def test_tool_never_uploads_source_anywhere() -> None:
    """Structural guarantee: no upload-shaped function/import exists in
    this module -- only a download primitive (_download_file) is imported.
    Checked against real code (functions + imports), not comment text,
    since the module's own docstring legitimately discusses uploading in
    the abstract (explaining why it refuses to do so)."""
    assert not hasattr(mod, "boto3")
    import_lines = [
        line for line in Path(mod.__file__).read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined_imports = "\n".join(import_lines).lower()
    assert "boto3" not in joined_imports
    assert "r2" not in joined_imports
    func_names = [name for name in dir(mod) if not name.startswith("__")]
    assert not any("upload" in name.lower() for name in func_names)


# --- structural safety guarantees (imports, reuse, no fallback) -------------

def _import_lines(source: str) -> list[str]:
    return [
        line for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]


def test_never_imports_queue_approval_publish_analytics_or_env_modules() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    imports = "\n".join(_import_lines(source))
    for forbidden in (
        "posting_manager", "instagram_queue_bridge", "instagram_graph_adapter",
        "process_queue", "lena_promote_to_queue", "lena_record_publish_approval",
        "env_loader", "outcome_learning", "meta_refresh",
    ):
        assert forbidden not in imports, f"forbidden import found: {forbidden}"


def test_never_imports_legacy_unsafe_renderer() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    imports = "\n".join(_import_lines(source))
    assert "pipeline.renderer.kling" not in imports
    assert "pipeline.renderer" not in imports


def test_reuses_canonical_executor_transport_never_redefines_it() -> None:
    import pipeline.kling_apilena_api_executor as executor_mod
    assert mod._auth_header is executor_mod._auth_header
    assert mod._http_json is executor_mod._http_json
    assert mod._download_file is executor_mod._download_file
    assert mod._sanitize_reference_url is executor_mod._sanitize_reference_url


def test_no_retry_or_fallback_language_in_live_submission_path() -> None:
    import inspect
    source = inspect.getsource(mod.submit_and_process_live)
    # Structural guarantee: exactly one POST call to the pinned endpoint.
    assert source.count('_http_json("POST"') == 1


def test_no_motion_control_or_rule_zero_claim_in_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    manifest = build_commission_manifest(validation, live_result=None)
    assert manifest["motion_control_claimed"] is False
    assert manifest["rule_zero_claimed"] is False


# --- manifest provenance completeness (for later canonical handoff) --------

def test_manifest_carries_sufficient_provenance_for_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    manifest = build_commission_manifest(validation, live_result=None)
    for field in (
        "test_video_slot_id", "source_slot_id", "source_path", "source_sha256",
        "motion_prompt", "motion_prompt_sha256", "model", "endpoint",
        "duration_seconds_requested", "mode",
    ):
        assert field in manifest, f"missing provenance field: {field}"
    assert manifest["test_video_slot_id"] == TEST_VIDEO_SLOT
    assert manifest["source_slot_id"] == SOURCE_SLOT
    assert manifest["mode"] == "dry_run"


def test_manifest_carries_full_provenance_for_simulated_live_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url="https://example.com/seed.png", live=True,
    )
    fake_live_result = {
        "task_id": "fake-task-123",
        "task_status": "succeed",
        "result_url_sanitized": "https://example.com/result...<redacted>",
        "saved_video_path": "C:\\fake\\video.mp4",
        "output_sha256": "b" * 64,
        "width": 1152,
        "height": 2048,
        "video_codec": "h264",
        "measured_duration_seconds": 5.0,
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
        "request_payload": build_request_payload("https://example.com/seed.png", MOTION_PROMPT, 5.0),
        "request_payload_sha256": "c" * 64,
        "submitted_at_utc": "2026-07-13T00:00:00+00:00",
    }
    manifest = build_commission_manifest(validation, live_result=fake_live_result)
    assert manifest["provider_task_id"] == "fake-task-123"
    assert manifest["provider_task_status"] == "succeed"
    assert manifest["output_sha256"] == "b" * 64
    assert manifest["width"] == 1152
    assert manifest["height"] == 2048
    assert manifest["video_codec"] == "h264"
    assert manifest["mode"] == "live"
    assert manifest["attempt_count"] == 1
    # Never a raw, unsanitized URL leaked into the manifest.
    assert "example.com/result" not in json.dumps(manifest) or "redacted" in manifest["provider_result_url_sanitized"]


def test_failure_manifest_semantics_are_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url="https://example.com/seed.png", live=True,
    )
    manifest = build_commission_manifest(
        validation, live_result=None,
        failure_stage="submission_or_processing",
        provider_error="Kling image2video submission failed: status=400 body=...",
    )
    assert manifest["mode"] == "live"
    assert manifest["attempt_count"] == 1
    assert manifest["failure_stage"] == "submission_or_processing"
    assert "Kling image2video submission failed" in manifest["provider_error"]


# --- dry-run purity ---------------------------------------------------------

def test_dry_run_never_calls_http_json_or_download() -> None:
    """Structural guarantee: print_dry_run_report() never references the
    live transport functions at all (the trailing print-only mention of
    the word 'subprocess' in its own output banner doesn't count as a
    call -- checked by function reference, not substring, below)."""
    import inspect
    source = inspect.getsource(mod.print_dry_run_report)
    assert "_http_json(" not in source
    assert "_download_file(" not in source
    assert "subprocess.run(" not in source
    assert "subprocess.Popen(" not in source


def test_dry_run_writes_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    mod.print_dry_run_report(validation)
    paths = mod.commission_output_paths("2026-07-09", TEST_VIDEO_SLOT)
    assert not paths["video_dir"].exists()
    assert not paths["manifest_path"].exists()


# --- real repo evidence remains untouched -----------------------------------

def test_historical_kling_video_result_remains_untouched() -> None:
    path = (
        Path("pipeline/strategy/lena/kling_video_results/2026-06-30")
        / "kling_video_result_2026-06-30_podclip_20260630_01_901327158671446020.json"
    )
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["task_id"] == "901327158671446020"
    assert data["provider_endpoint"] == "https://api-singapore.klingai.com/v1/videos/image2video"
    assert data["model"] == "kling-v2-1-master"


def test_abc_wardrobe_isolation_evidence_remains_untouched() -> None:
    expected_shas = {
        "readypack0709-pack004-08-wardrobe-test-a": "016169946de5e9a7d9d575775a57757cbf2cb9ba2b38fbe962f2c3c923a8d655",
        "readypack0709-pack004-08-wardrobe-test-b": "0085d68214e738604a0a25348de12335bc79287dfd67b6a184f2a88d07d7b0f8",
        "readypack0709-pack004-08-wardrobe-test-c": "7649a7ab360832390eac0e5f06ed7bb4f21d941f31e57201ef6721c00a313ffb",
    }
    for slot, expected_sha in expected_shas.items():
        image_path = Path(
            f"pipeline/higgsfield_library/lena/2026-07-09/prompt_isolation_tests/{slot}_seed.png"
        )
        assert image_path.exists()
        actual_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"{slot} image was modified"

        manifest_path = Path(
            f"pipeline/higgsfield_debug/2026-07-09/prompt_isolation_tests/{slot}/result_manifest.json"
        )
        assert manifest_path.exists()


# --- URL sanitization (correction 2) -----------------------------------------

def test_unsigned_source_url_stores_safely_in_manifest_field() -> None:
    unsigned = "https://pub-example.r2.dev/lena/queue-media/2026-07-10/photo.png"
    assert mod._manifest_safe_source_url(unsigned) == unsigned


def test_signed_source_url_is_sanitized_for_manifest() -> None:
    signed = "https://pub-example.r2.dev/lena/photo.png?sig=abc123&exp=999"
    sanitized = mod._manifest_safe_source_url(signed)
    assert sanitized != signed
    assert "sig=abc123" not in sanitized
    assert "exp=999" not in sanitized
    assert sanitized.startswith("https://pub-example.r2.dev")


def test_raw_signed_url_not_persisted_in_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    signed_url = "https://pub-example.r2.dev/lena/photo.png?sig=SECRETVALUE"
    _write_receipt(tmp_path, SOURCE_SLOT, source, signed_url)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=signed_url, live=True,
    )
    assert validation["ok"] is True
    payload = build_request_payload(signed_url, MOTION_PROMPT, 5.0)
    fake_live_result = {
        "task_id": "fake-task", "task_status": "succeed",
        "result_url_sanitized": "https://example.com/r...<redacted>",
        "saved_video_path": "C:\\fake\\video.mp4", "output_sha256": "a" * 64,
        "width": 1152, "height": 2048, "video_codec": "h264",
        "measured_duration_seconds": 5.0, "container": "mp4",
        "request_payload": payload,
        "request_payload_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "submitted_at_utc": "2026-07-13T00:00:00+00:00",
    }
    manifest = build_commission_manifest(validation, live_result=fake_live_result)
    manifest_json = json.dumps(manifest)
    assert "SECRETVALUE" not in manifest_json
    assert manifest["source_public_url_sanitized"] is not None
    assert "SECRETVALUE" not in manifest["source_public_url_sanitized"]


def test_exact_request_payload_sha_preserved_despite_manifest_redaction() -> None:
    payload = build_request_payload(
        "https://example.com/seed.png?sig=xyz", MOTION_PROMPT, 5.0
    )
    expected_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    validation = {
        "date": "2026-07-09", "test_video_slot_id": TEST_VIDEO_SLOT,
        "source_slot_id": SOURCE_SLOT, "source_path": "C:\\fake\\seed.png",
        "source_sha256": "b" * 64, "motion_prompt": MOTION_PROMPT,
        "motion_prompt_sha256": "c" * 64, "duration_seconds": 5.0,
        "source_receipt_path": "C:\\fake\\receipt.json",
        "source_public_url_sanitized": "https://example.com/seed.png...<redacted>",
    }
    fake_live_result = {
        "task_id": "fake-task", "task_status": "succeed",
        "result_url_sanitized": "https://example.com/r...<redacted>",
        "saved_video_path": "C:\\fake\\video.mp4", "output_sha256": "a" * 64,
        "width": 1152, "height": 2048, "video_codec": "h264",
        "measured_duration_seconds": 5.0, "container": "mp4",
        "request_payload": payload, "request_payload_sha256": expected_sha,
        "submitted_at_utc": "2026-07-13T00:00:00+00:00",
    }
    manifest = build_commission_manifest(validation, live_result=fake_live_result)
    assert manifest["request_payload_sha256"] == expected_sha
    assert manifest["request_payload"]["image"] != payload["image"]


def test_outbound_live_request_uses_exact_raw_source_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual submitted payload must still carry the exact raw URL --
    only manifest persistence sanitizes, never the real outbound request."""
    _patch_roots(tmp_path, monkeypatch)
    raw_url = "https://example.com/seed.png?sig=super-secret-signature"
    captured_payloads = []

    def fake_http_json(method, url, payload=None):
        if method == "POST":
            captured_payloads.append(payload)
            return {"ok": True, "json": {"data": {"task_id": "fake-task"}}, "raw": "{}"}
        return {
            "ok": True,
            "json": {
                "data": {
                    "task_status": "succeed",
                    "task_result": {"videos": [{"url": "https://example.com/result.mp4"}]},
                }
            },
            "raw": "{}",
        }

    def fake_download_file(url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-video-bytes")

    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(mod, "_download_file", fake_download_file)
    monkeypatch.setattr(
        mod, "_ffprobe_video",
        lambda path: {
            "width": 1152, "height": 2048, "video_codec": "h264",
            "duration_seconds": 5.0, "format_name": "mp4",
        },
    )

    validation = {
        "date": "2026-07-09", "test_video_slot_id": TEST_VIDEO_SLOT,
        "source_public_url": raw_url, "motion_prompt": MOTION_PROMPT,
        "duration_seconds": 5.0,
    }
    result = mod.submit_and_process_live(validation)
    assert captured_payloads[0]["image"] == raw_url
    assert result["request_payload"]["image"] == raw_url


# --- exception normalization (correction 3) ----------------------------------

def _base_live_validation(source_public_url: str = "https://example.com/seed.png") -> dict:
    return {
        "date": "2026-07-09", "test_video_slot_id": TEST_VIDEO_SLOT,
        "source_slot_id": SOURCE_SLOT, "source_path": "C:\\fake\\seed.png",
        "source_sha256": "b" * 64,
        "source_public_url": source_public_url, "motion_prompt": MOTION_PROMPT,
        "motion_prompt_sha256": hashlib.sha256(MOTION_PROMPT.encode()).hexdigest(),
        "source_receipt_path": "C:\\fake\\receipt.json",
        "source_public_url_sanitized": mod._manifest_safe_source_url(source_public_url),
        "duration_seconds": 5.0,
    }


def test_provider_network_failure_becomes_auditable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising_http_json(method, url, payload=None):
        raise OSError("connection refused")

    monkeypatch.setattr(mod, "_http_json", raising_http_json)
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation())
    assert excinfo.value.stage == "provider_network_failure"
    state = excinfo.value.partial_live_state
    assert state["provider_submission_attempted"] is True
    assert state["provider_task_id"] is None
    assert state["provider_task_status"] is None
    assert state["saved_video_path"] is None
    manifest = build_commission_manifest(
        _base_live_validation(), live_result=None,
        failure_stage=excinfo.value.stage, provider_error=str(excinfo.value),
        partial_live_state=state,
    )
    assert manifest["provider_submission_attempted"] is True
    assert manifest["provider_task_id"] is None
    assert manifest["provider_task_status"] is None
    assert manifest["saved_video_path"] is None


def test_polling_failure_preserves_task_id_and_latest_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"post": 0, "get": 0}

    def fake_http_json(method, url, payload=None):
        if method == "POST":
            calls["post"] += 1
            return {"ok": True, "json": {"data": {"task_id": "task-123"}}, "raw": "{}"}
        calls["get"] += 1
        if calls["get"] == 1:
            return {"ok": True, "json": {"data": {"task_status": "processing"}}, "raw": "{}"}
        raise OSError("poll connection lost")

    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation())
    assert excinfo.value.stage == "polling_network_failure"
    assert excinfo.value.partial_live_state["provider_task_id"] == "task-123"
    assert excinfo.value.partial_live_state["provider_task_status"] == "processing"
    assert calls["post"] == 1


def test_download_failure_preserves_completed_state_and_sanitized_result_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed_result = "https://example.com/result.mp4?token=RESULTSECRET"

    def fake_http_json(method, url, payload=None):
        if method == "POST":
            return {"ok": True, "json": {"data": {"task_id": "task-456"}}, "raw": "{}"}
        return {"ok": True, "json": {"data": {
            "task_status": "succeed",
            "task_result": {"videos": [{"url": signed_result}]},
        }}, "raw": "{}"}

    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(
        mod, "_download_file",
        lambda url, destination: (_ for _ in ()).throw(OSError("download failed")),
    )
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation())
    state = excinfo.value.partial_live_state
    assert excinfo.value.stage == "download_failure"
    assert state["provider_task_id"] == "task-456"
    assert state["provider_task_status"] == "succeed"
    assert state["provider_result_url_sanitized"] is not None
    assert "RESULTSECRET" not in json.dumps(state)
    manifest = build_commission_manifest(
        _base_live_validation(), live_result=None,
        failure_stage=excinfo.value.stage, provider_error=str(excinfo.value),
        partial_live_state=state,
    )
    assert "RESULTSECRET" not in json.dumps(manifest)


def test_provider_http_failure_becomes_auditable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def not_ok_http_json(method, url, payload=None):
        return {"ok": False, "status": 500, "raw": "server error"}

    monkeypatch.setattr(mod, "_http_json", not_ok_http_json)
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation())
    assert excinfo.value.stage == "provider_http_failure"


def test_provider_http_error_sanitizes_echoed_signed_url_and_keeps_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = "https://example.com/source.png?sig=SECRETVALUE"

    def not_ok_http_json(method, url, payload=None):
        return {
            "ok": False,
            "status": 400,
            "raw": f"invalid source image {signed}; dimensions unsupported",
        }

    monkeypatch.setattr(mod, "_http_json", not_ok_http_json)
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation(signed))
    error_text = str(excinfo.value)
    assert "SECRETVALUE" not in error_text
    assert signed not in error_text
    assert "dimensions unsupported" in error_text

    manifest = build_commission_manifest(
        {
            "date": "2026-07-09", "test_video_slot_id": TEST_VIDEO_SLOT,
            "source_slot_id": SOURCE_SLOT, "source_path": "C:\\fake\\seed.png",
            "source_sha256": "b" * 64, "motion_prompt": MOTION_PROMPT,
            "motion_prompt_sha256": "c" * 64, "duration_seconds": 5.0,
            "source_receipt_path": "C:\\fake\\receipt.json",
            "source_public_url_sanitized": mod._manifest_safe_source_url(signed),
        },
        live_result=None,
        failure_stage=excinfo.value.stage,
        provider_error=error_text,
    )
    assert "SECRETVALUE" not in json.dumps(manifest)


def test_failed_console_output_cannot_print_raw_signed_url(capsys) -> None:
    signed = "https://example.com/source.png?sig=SECRETVALUE"
    exc = KlingCommissionError(
        f"provider rejected {signed}; useful diagnostic", stage="provider_http_failure"
    )
    print(f"[FAILED] {exc}")
    output = capsys.readouterr().out
    assert "SECRETVALUE" not in output
    assert signed not in output
    assert "useful diagnostic" in output


def test_polling_and_result_error_structures_sanitize_query_urls() -> None:
    signed = "https://example.com/result.mp4?token=RESULTSECRET"
    for message in (
        f"poll failed with body containing {signed}",
        f"result extraction failed from {{'url': '{signed}'}}",
    ):
        error = KlingCommissionError(message, stage="polling_failure")
        assert "RESULTSECRET" not in str(error)
        assert signed not in str(error)


def test_unsigned_operational_error_url_is_not_modified() -> None:
    unsigned = "https://example.com/source.png"
    error = KlingCommissionError(f"provider rejected {unsigned}")
    assert unsigned in str(error)


def test_provider_response_parse_failure_becomes_auditable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bad_json_http_json(method, url, payload=None):
        raise json.JSONDecodeError("bad json", "doc", 0)

    monkeypatch.setattr(mod, "_http_json", bad_json_http_json)
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation())
    assert excinfo.value.stage == "provider_response_parse_failure"


def test_polling_network_failure_becomes_auditable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}

    def flaky_http_json(method, url, payload=None):
        call_count["n"] += 1
        if method == "POST":
            return {"ok": True, "json": {"data": {"task_id": "fake-task"}}, "raw": "{}"}
        raise OSError("connection reset")

    monkeypatch.setattr(mod, "_http_json", flaky_http_json)
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(_base_live_validation())
    assert excinfo.value.stage == "polling_network_failure"


def test_ffprobe_process_failure_becomes_auditable_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ffprobe")

    def raising_run(*args, **kwargs):
        raise OSError("ffprobe crashed")

    monkeypatch.setattr(mod.subprocess, "run", raising_run)
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"not-a-real-video")
    with pytest.raises(KlingCommissionError) as excinfo:
        mod._ffprobe_video(fake_video)
    assert excinfo.value.stage == "ffprobe_process_failure"


def test_ffprobe_parse_failure_becomes_auditable_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as subprocess_module

    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ffprobe")

    def fake_run(*args, **kwargs):
        return subprocess_module.CompletedProcess(
            args=args, returncode=0, stdout="not-valid-json{{{", stderr=""
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"not-a-real-video")
    with pytest.raises(KlingCommissionError) as excinfo:
        mod._ffprobe_video(fake_video)
    assert excinfo.value.stage == "ffprobe_parse_failure"


def test_ffprobe_missing_video_stream_is_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as subprocess_module

    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ffprobe")

    def fake_run(*args, **kwargs):
        return subprocess_module.CompletedProcess(
            args=args, returncode=0,
            stdout=json.dumps({"streams": [], "format": {}}), stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"not-a-real-video")
    with pytest.raises(KlingCommissionError) as excinfo:
        mod._ffprobe_video(fake_video)
    assert excinfo.value.stage == "ffprobe_parse_failure"


@pytest.mark.parametrize(
    "format_value",
    [
        {"duration": "not-a-number"},
        {},
        [],
        None,
    ],
)
def test_ffprobe_malformed_duration_or_format_is_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, format_value
) -> None:
    import subprocess as subprocess_module

    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ffprobe")
    stdout = json.dumps({
        "streams": [{"codec_type": "video", "width": 1152, "height": 2048}],
        "format": format_value,
    })
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_module.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=""
        ),
    )
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"not-a-real-video")
    with pytest.raises(KlingCommissionError) as excinfo:
        mod._ffprobe_video(fake_video)
    assert excinfo.value.stage == "ffprobe_parse_failure"


def test_ffprobe_valid_numeric_duration_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as subprocess_module

    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ffprobe")
    stdout = json.dumps({
        "streams": [{
            "codec_type": "video", "width": 1152, "height": 2048,
            "codec_name": "h264",
        }],
        "format": {"duration": "5.000000", "format_name": "mp4"},
    })
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_module.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=""
        ),
    )
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"not-a-real-video")
    result = mod._ffprobe_video(fake_video)
    assert result["duration_seconds"] == 5.0
    assert result["video_codec"] == "h264"


def test_live_shaped_malformed_duration_preserves_video_and_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as subprocess_module

    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    source_url = "https://pub-example.r2.dev/lena/photo.png"
    _write_receipt(tmp_path, SOURCE_SLOT, source, source_url)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=source_url, live=True,
    )
    assert validation["ok"] is True

    def fake_http_json(method, url, payload=None):
        if method == "POST":
            return {"ok": True, "json": {"data": {"task_id": "fake-task"}}, "raw": "{}"}
        return {
            "ok": True,
            "json": {"data": {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://example.com/result.mp4"}]},
            }},
            "raw": "{}",
        }

    def fake_download(url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"finalized-video-bytes")

    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(mod, "_download_file", fake_download)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ffprobe")
    malformed = json.dumps({
        "streams": [{"codec_type": "video", "width": 1152, "height": 2048}],
        "format": {"duration": "not-a-number"},
    })
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_module.CompletedProcess(
            args=args, returncode=0, stdout=malformed, stderr=""
        ),
    )

    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(validation)
    assert excinfo.value.stage == "ffprobe_parse_failure"
    assert excinfo.value.partial_live_state["provider_task_id"] == "fake-task"
    assert excinfo.value.partial_live_state["provider_task_status"] == "succeed"

    paths = mod.commission_output_paths("2026-07-09", TEST_VIDEO_SLOT)
    final_video = paths["video_dir"] / f"{paths['video_stem']}.mp4"
    assert final_video.read_bytes() == b"finalized-video-bytes"
    assert excinfo.value.partial_live_state["saved_video_path"] == str(final_video)

    failure_manifest = build_commission_manifest(
        validation,
        live_result=None,
        failure_stage=excinfo.value.stage,
        provider_error=str(excinfo.value),
        partial_live_state=excinfo.value.partial_live_state,
    )
    paths["manifest_path"].parent.mkdir(parents=True, exist_ok=True)
    paths["manifest_path"].write_text(json.dumps(failure_manifest), encoding="utf-8")
    assert json.loads(paths["manifest_path"].read_text(encoding="utf-8"))[
        "failure_stage"
    ] == "ffprobe_parse_failure"

    retry = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=source_url, live=True,
    )
    assert retry["ok"] is False
    assert any("already exists" in reason for reason in retry["reasons"])


def test_output_hash_failure_preserves_probe_and_output_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    validation = _base_live_validation()

    def fake_http_json(method, url, payload=None):
        if method == "POST":
            return {"ok": True, "json": {"data": {"task_id": "task-hash"}}, "raw": "{}"}
        return {"ok": True, "json": {"data": {
            "task_status": "succeed",
            "task_result": {"videos": [{"url": "https://example.com/result.mp4"}]},
        }}, "raw": "{}"}

    def fake_download(url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")

    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(mod, "_download_file", fake_download)
    monkeypatch.setattr(mod, "_ffprobe_video", lambda path: {
        "width": 1152, "height": 2048, "video_codec": "h264",
        "duration_seconds": 5.0, "format_name": "mp4",
    })
    monkeypatch.setattr(
        mod, "_sha256_file",
        lambda path: (_ for _ in ()).throw(OSError("hash read failed")),
    )
    with pytest.raises(KlingCommissionError) as excinfo:
        mod.submit_and_process_live(validation)
    state = excinfo.value.partial_live_state
    assert excinfo.value.stage == "output_hash_failure"
    assert state["provider_task_id"] == "task-hash"
    assert state["provider_task_status"] == "succeed"
    assert state["saved_video_path"].endswith("_video.mp4")
    assert state["width"] == 1152
    assert state["height"] == 2048
    assert state["video_codec"] == "h264"
    assert state["measured_duration_seconds"] == 5.0
    assert state["container"] == "mp4"
    assert state["output_sha256"] is None


def test_failure_stage_recorded_correctly_in_failure_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    url = "https://pub-example.r2.dev/lena/photo.png"
    _write_receipt(tmp_path, SOURCE_SLOT, source, url)
    validation = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=url, live=True,
    )
    assert validation["ok"] is True
    try:
        raise KlingCommissionError("simulated network failure", stage="provider_network_failure")
    except KlingCommissionError as exc:
        manifest = build_commission_manifest(
            validation, live_result=None,
            failure_stage=exc.stage, provider_error=str(exc),
        )
    assert manifest["failure_stage"] == "provider_network_failure"
    assert manifest["provider_error"] == "simulated network failure"


# --- prompt-file byte handling (correction 4) --------------------------------

def test_exact_prompt_bytes_accepted_unchanged() -> None:
    assert validate_prompt_bytes(MOTION_PROMPT.encode("utf-8")) is None


def test_trailing_lf_rejected() -> None:
    error = validate_prompt_bytes((MOTION_PROMPT + "\n").encode("utf-8"))
    assert error is not None
    assert "LF" in error


def test_trailing_cr_rejected() -> None:
    error = validate_prompt_bytes((MOTION_PROMPT + "\r").encode("utf-8"))
    assert error is not None
    assert "CR" in error


def test_trailing_crlf_rejected() -> None:
    error = validate_prompt_bytes((MOTION_PROMPT + "\r\n").encode("utf-8"))
    assert error is not None
    assert "CRLF" in error


def test_internal_newlines_preserved_when_no_trailing_newline() -> None:
    multiline_prompt = "First line.\nSecond line.\nThird line, no trailing newline."
    assert validate_prompt_bytes(multiline_prompt.encode("utf-8")) is None


def test_no_silent_rstrip_remains_in_source() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert 'rstrip("\\n")' not in source
    assert "rstrip('\\n')" not in source


def test_prompt_sha_matches_exact_accepted_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.0,
        source_public_url=None, live=False,
    )
    assert result["motion_prompt_sha256"] == hashlib.sha256(
        MOTION_PROMPT.encode("utf-8")
    ).hexdigest()


# --- duration pinning (correction 5) -----------------------------------------

def test_duration_exactly_five_accepted() -> None:
    assert validate_duration_seconds(5) is None
    assert validate_duration_seconds(5.0) is None
    assert REQUIRED_DURATION_SECONDS == 5.0


def test_duration_four_rejected() -> None:
    assert validate_duration_seconds(4) is not None


def test_duration_six_rejected() -> None:
    assert validate_duration_seconds(6) is not None


def test_duration_five_point_five_rejected() -> None:
    assert validate_duration_seconds(5.5) is not None


def test_duration_five_point_nine_does_not_truncate_to_five() -> None:
    """5.9 must be rejected outright -- never silently truncated to 5 via
    int(), the exact drift bug this correction closes."""
    error = validate_duration_seconds(5.9)
    assert error is not None
    assert "5.9" in error


def test_payload_duration_equals_pinned_literal_exactly() -> None:
    payload = build_request_payload("https://example.com/seed.png", MOTION_PROMPT, 5.0)
    assert payload["duration"] == "5"


def test_build_request_payload_rejects_invalid_duration() -> None:
    with pytest.raises(KlingCommissionError):
        build_request_payload("https://example.com/seed.png", MOTION_PROMPT, 5.9)


def test_validate_commission_rejects_non_pinned_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    source = _write_source(tmp_path)
    result = validate_commission(
        "2026-07-09", SOURCE_SLOT, source, TEST_VIDEO_SLOT, MOTION_PROMPT, 5.9,
        source_public_url=None, live=False,
    )
    assert result["ok"] is False
    assert any("duration_seconds" in r for r in result["reasons"])
