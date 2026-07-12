from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import tools.lena_higgsfield_prompt_isolation_test_v1 as mod
from tools.lena_higgsfield_prompt_isolation_test_v1 import (
    MAX_VARIANTS_PER_INVOCATION,
    PromptIsolationTestError,
    ProviderCallError,
    resolve_source_seed_path,
    test_output_paths as compute_test_output_paths,
    validate_test_slot_id,
    validate_variant,
    validate_variants,
    build_test_manifest,
    submit_variant_live,
)


def _write_source_seed(tmp_root: Path, date_str: str, source_slot_id: str) -> Path:
    lib_dir = tmp_root / "pipeline" / "higgsfield_library" / "lena" / date_str
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"{source_slot_id}_seed.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake-seed-bytes")
    return path


def _variant(
    test_slot_id="readypack0709-pack004-08-wardrobe-test-a",
    source_slot_id="readypack0709-pack004-08-photo",
    image_prompt="Full-body ... Wardrobe: cobalt blue satin bias-cut mini dress ... Mood: confident.",
    wardrobe_id="wc_p008",
    variant_label="cobalt_blue_satin_bias_cut",
) -> dict:
    return {
        "test_slot_id": test_slot_id,
        "source_slot_id": source_slot_id,
        "image_prompt": image_prompt,
        "wardrobe_id": wardrobe_id,
        "variant_label": variant_label,
    }


def _patch_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Common fixture wiring: isolate ROOT/TEST_LIBRARY_ROOT/TEST_DEBUG_ROOT
    under tmp_path so no test ever touches the real repo tree."""
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    lib_root = tmp_path / "pipeline" / "higgsfield_library" / "lena"
    monkeypatch.setattr(mod, "TEST_LIBRARY_ROOT", lib_root)
    monkeypatch.setattr(mod, "TEST_DEBUG_ROOT", tmp_path / "pipeline" / "higgsfield_debug")
    return lib_root


# --- test_slot_id scoping -----------------------------------------------

def test_test_slot_id_rejects_production_pack_shape() -> None:
    reasons = validate_test_slot_id("readypack0709-pack004-08-photo")
    assert any("production pack-slot" in r for r in reasons)


def test_test_slot_id_rejects_missing_test_marker() -> None:
    reasons = validate_test_slot_id("readypack0709-pack004-08-wardrobe-variant-a")
    assert any("-test-" in r for r in reasons)


def test_test_slot_id_accepts_clearly_scoped_identity() -> None:
    reasons = validate_test_slot_id("readypack0709-pack004-08-wardrobe-test-a")
    assert reasons == []


# --- source lineage -------------------------------------------------------

def test_resolve_source_seed_path_finds_real_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")
    path = resolve_source_seed_path("2026-07-09", "readypack0709-pack004-08-photo")
    assert path.exists()
    assert path.name == "readypack0709-pack004-08-photo_seed.png"


def test_resolve_source_seed_path_fails_closed_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    with pytest.raises(PromptIsolationTestError, match="source lineage missing"):
        resolve_source_seed_path("2026-07-09", "nonexistent-slot")


# --- per-variant validation ------------------------------------------------

def test_validate_variant_passes_with_real_lineage_and_scoped_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is True
    assert result["reasons"] == []
    assert result["source_seed_sha256"] is not None
    assert result["prompt_sha256"] is not None


def test_validate_variant_fails_closed_on_missing_source_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    # No seed file written for the source_slot_id.
    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is False
    assert any("source lineage" in r for r in result["reasons"])


def test_validate_variant_fails_closed_on_duplicate_test_slot_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    seen = {"readypack0709-pack004-08-wardrobe-test-a"}
    result = validate_variant("2026-07-09", _variant(), seen)
    assert result["ok"] is False
    assert any("duplicate test_slot_id" in r for r in result["reasons"])


def test_validate_variant_fails_on_missing_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    variant = _variant()
    variant["image_prompt"] = ""
    result = validate_variant("2026-07-09", variant, set())
    assert result["ok"] is False
    assert any("image_prompt" in r for r in result["reasons"])


# --- no-overwrite-path collision tests (v1: no bypass exists at all) -------

def test_validate_variant_fails_closed_on_existing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib_root = _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    manifest_dir = (
        tmp_path / "pipeline" / "higgsfield_debug" / "2026-07-09"
        / "prompt_isolation_tests" / "readypack0709-pack004-08-wardrobe-test-a"
    )
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "result_manifest.json").write_text("{}", encoding="utf-8")

    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is False
    assert any("already exists" in r for r in result["reasons"])
    assert any("result_manifest.json" in r for r in result["reasons"])


def test_validate_variant_fails_closed_on_existing_final_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib_root = _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    image_dir = lib_root / "2026-07-09" / "prompt_isolation_tests"
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / "readypack0709-pack004-08-wardrobe-test-a_seed.png").write_bytes(b"existing")

    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is False
    assert any("already exists" in r for r in result["reasons"])


def test_validate_variant_fails_closed_on_leftover_tmp_from_prior_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale .tmp left behind by some earlier, different invocation must
    never be silently reused or silently removed -- it counts as an
    existing output and fails closed, just like a finished manifest/image."""
    lib_root = _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    image_dir = lib_root / "2026-07-09" / "prompt_isolation_tests"
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / "readypack0709-pack004-08-wardrobe-test-a_seed.tmp").write_bytes(b"stale-partial-download")

    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is False
    assert any("already exists" in r for r in result["reasons"])
    assert any(".tmp" in r for r in result["reasons"])


def test_no_overwrite_flag_exists_anywhere_in_validate_variant_signature() -> None:
    import inspect
    sig = inspect.signature(validate_variant)
    assert "allow_overwrite" not in sig.parameters
    sig2 = inspect.signature(validate_variants)
    assert "allow_overwrite" not in sig2.parameters


def test_cli_has_no_allow_overwrite_flag() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "--allow-overwrite" not in source
    assert "allow_overwrite" not in source


# --- invocation-level validation (max variants, aggregate) -----------------

def test_validate_variants_fails_closed_over_max_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    variants = [
        _variant(test_slot_id=f"readypack0709-pack004-08-wardrobe-test-{c}")
        for c in "abcd"
    ]
    assert len(variants) == MAX_VARIANTS_PER_INVOCATION + 1
    result = validate_variants("2026-07-09", variants)
    assert result["ok"] is False
    assert any("exceeds the maximum" in r for r in result["reasons"])
    assert result["variant_results"] == []


def test_validate_variants_passes_for_three_real_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    variants = [
        _variant(test_slot_id="readypack0709-pack004-08-wardrobe-test-a", wardrobe_id="wc_p008"),
        _variant(test_slot_id="readypack0709-pack004-08-wardrobe-test-b", wardrobe_id="wc_p010"),
        _variant(test_slot_id="readypack0709-pack004-08-wardrobe-test-c", wardrobe_id="wc_p020"),
    ]
    result = validate_variants("2026-07-09", variants)
    assert result["ok"] is True
    assert len(result["variant_results"]) == 3
    assert all(r["ok"] for r in result["variant_results"])


def test_validate_variants_empty_list_is_not_ok() -> None:
    result = validate_variants("2026-07-09", [])
    assert result["ok"] is False


# --- prompt preservation ---------------------------------------------------

def test_prompt_text_preserved_byte_for_byte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    exact_prompt = "Exact prompt text with Wardrobe: cobalt blue satin bias-cut mini dress; unchanged elsewhere."
    variant = _variant(image_prompt=exact_prompt)
    result = validate_variant("2026-07-09", variant, set())
    assert result["image_prompt"] == exact_prompt
    assert result["prompt_sha256"] == hashlib.sha256(exact_prompt.encode("utf-8")).hexdigest()


# --- manifest content -------------------------------------------------------

def test_build_test_manifest_records_lineage_identity_and_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is True

    manifest = build_test_manifest("2026-07-09", result, mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID, live_result=None)
    assert manifest["test_slot_id"] == "readypack0709-pack004-08-wardrobe-test-a"
    assert manifest["source_slot_id"] == "readypack0709-pack004-08-photo"
    assert manifest["wardrobe_id"] == "wc_p008"
    assert manifest["image_prompt"] == result["image_prompt"]
    assert manifest["prompt_sha256"] == result["prompt_sha256"]
    assert manifest["cli_soul_name"] == mod.CONFIRMED_LENA_SOUL_NAME
    assert manifest["custom_reference_id"] == mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID
    assert manifest["live_attempt_count"] == 0
    assert "provider_job_id" not in manifest


def test_build_test_manifest_includes_live_fields_when_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    result = validate_variant("2026-07-09", _variant(), set())
    live_result = {
        "job_id": "job-123",
        "status": "completed",
        "result_urls": ["https://example.com/result.png"],
        "saved_image_path": "C:\\fake\\path.png",
        "image_format_detected": ".png",
        "output_sha256": "a" * 64,
    }
    manifest = build_test_manifest("2026-07-09", result, mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID, live_result)
    assert manifest["provider_job_id"] == "job-123"
    assert manifest["live_attempt_count"] == 1
    assert manifest["output_sha256"] == "a" * 64
    # Never a raw, unsanitized URL in the manifest.
    assert manifest["result_urls_sanitized"][0] != "https://example.com/result.png"


# --- temp-file exception safety (submit_variant_live) ----------------------

def test_failed_download_cleans_up_its_own_tmp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a live submission where the provider subprocess succeeds
    and returns a real result_url, but the download itself fails partway
    (after _download has already written some bytes to the .tmp path).
    submit_variant_live() must remove that .tmp file itself before
    re-raising, in a finally -- never leaving a stale .tmp behind from its
    own failed attempt."""
    lib_root = _patch_roots(tmp_path, monkeypatch)
    _write_source_seed(tmp_path, "2026-07-09", "readypack0709-pack004-08-photo")

    result = validate_variant("2026-07-09", _variant(), set())
    assert result["ok"] is True

    paths = compute_test_output_paths("2026-07-09", result["test_slot_id"])
    tmp_path_expected = paths["image_dir"] / f"{paths['image_stem']}.tmp"

    def _fake_download(url: str, destination: Path) -> bytes:
        # Simulate a partial write followed by a failure -- exactly what a
        # real interrupted download would leave behind.
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"partial-bytes-then-failure")
        raise OSError("simulated network failure mid-download")

    monkeypatch.setattr(mod, "shutil", mod.shutil)
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "C:\\fake\\higgsfield.exe")
    monkeypatch.setattr(mod, "_download", _fake_download)

    fake_completed = type(
        "FakeCompletedProcess", (),
        {"returncode": 0, "stdout": json.dumps({
            "job_id": "job-abc", "status": "completed",
            "result_url": "https://example.com/result.png",
        }), "stderr": ""},
    )()
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: fake_completed)

    assert not tmp_path_expected.exists()
    with pytest.raises(ProviderCallError, match="Download of result image failed"):
        submit_variant_live("2026-07-09", result, mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID)

    # The .tmp file this exact failed attempt created must be gone.
    assert not tmp_path_expected.exists()
    # And no final image was ever produced.
    assert list(paths["image_dir"].glob("*")) == [] if paths["image_dir"].exists() else True


# --- reuse-not-duplicate structural guarantees ------------------------------

def test_reuses_executor_constants_never_redefines_them() -> None:
    import pipeline.higgsfield_lena_api_executor as executor_mod
    assert mod.HIGGSFIELD_CLI_BINARY is executor_mod.HIGGSFIELD_CLI_BINARY
    assert mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID is executor_mod.DEFAULT_LENA_CUSTOM_REFERENCE_ID
    assert mod.build_provider_argv is executor_mod.build_provider_argv
    assert mod._PACK_SLOT_ID_PATTERN is executor_mod._PACK_SLOT_ID_PATTERN


def _import_lines(source: str) -> list[str]:
    return [
        line for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]


def test_never_imports_queue_publish_analytics_or_env_modules() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    imports = "\n".join(_import_lines(source))
    for forbidden in (
        "posting_manager", "instagram_queue_bridge", "instagram_graph_adapter",
        "process_queue", "lena_promote_to_queue", "lena_record_publish_approval",
        "env_loader",
    ):
        assert forbidden not in imports, f"forbidden import found: {forbidden}"


def test_does_not_import_or_call_resolve_prompt_source() -> None:
    assert not hasattr(mod, "resolve_prompt_source")
