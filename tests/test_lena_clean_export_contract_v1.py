from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tools.lena_scrub_media_metadata_v1 import resolve_clean_output_path, scrub_image_metadata
from tools.lena_verify_clean_export_v1 import (
    CleanExportVerificationError,
    resolve_clean_provenance_sidecar_path,
    verify_clean_export,
)
from tools.lena_promote_to_queue_v1 import (
    PromoteError,
    _apply_clean_export_fields,
    _validate_clean_export,
)


def _make_source_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(path, format="PNG")
    return path


def _make_clean_pair(tmp_path: Path, name: str = "asset_seed.png") -> Path:
    """Real source + a real scrubber-produced derivative/sidecar (not
    fabricated JSON) -- exercises the actual scrub_image_metadata() code
    path, same as the real-asset validation already reported separately."""
    source = _make_source_png(tmp_path / name)
    scrub_image_metadata(source)
    return source


# 1. valid clean derivative + matching sidecar permits promotion eligibility
def test_valid_clean_export_verifies(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path)
    facts = verify_clean_export(source)
    assert facts["verified_clean_after_scrub"] is True
    assert Path(facts["clean_derivative_path"]) == resolve_clean_output_path(source)
    assert facts["source_path"] == str(source)


# 2. missing derivative rejects
def test_missing_derivative_rejects(tmp_path: Path) -> None:
    source = _make_source_png(tmp_path / "no_derivative.png")
    with pytest.raises(CleanExportVerificationError, match="clean derivative does not exist"):
        verify_clean_export(source)


# 3. missing sidecar rejects
def test_missing_sidecar_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "missing_sidecar.png")
    sidecar_path = resolve_clean_provenance_sidecar_path(resolve_clean_output_path(source))
    sidecar_path.unlink()
    with pytest.raises(CleanExportVerificationError, match="provenance sidecar does not exist"):
        verify_clean_export(source)


# 4. mismatched source hash rejects
def test_mismatched_source_hash_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "bad_source_hash.png")
    sidecar_path = resolve_clean_provenance_sidecar_path(resolve_clean_output_path(source))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["source_sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(CleanExportVerificationError, match="source_sha256"):
        verify_clean_export(source)


# 5. mismatched output hash rejects
def test_mismatched_output_hash_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "bad_output_hash.png")
    sidecar_path = resolve_clean_provenance_sidecar_path(resolve_clean_output_path(source))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["output_sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(CleanExportVerificationError, match="output_sha256"):
        verify_clean_export(source)


# 6. verified_clean_after_scrub != true rejects
def test_verified_clean_flag_false_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "not_verified.png")
    sidecar_path = resolve_clean_provenance_sidecar_path(resolve_clean_output_path(source))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["verified_clean_after_scrub"] = False
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(CleanExportVerificationError, match="verified_clean_after_scrub"):
        verify_clean_export(source)


def test_verified_clean_flag_truthy_but_not_literal_true_rejects(tmp_path: Path) -> None:
    """"true" (string) or 1 (int) must not be accepted -- only the literal
    boolean True satisfies the contract."""
    source = _make_clean_pair(tmp_path, "truthy_not_true.png")
    sidecar_path = resolve_clean_provenance_sidecar_path(resolve_clean_output_path(source))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["verified_clean_after_scrub"] = 1
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(CleanExportVerificationError, match="verified_clean_after_scrub"):
        verify_clean_export(source)


# 7. clean derivative equal to raw source rejects
def test_derivative_equal_to_source_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _make_source_png(tmp_path / "self_pointing.png")
    monkeypatch.setattr(
        "tools.lena_verify_clean_export_v1.resolve_clean_output_path",
        lambda p: p,
    )
    with pytest.raises(CleanExportVerificationError, match="same path as the source"):
        verify_clean_export(source)


# 8. unsupported media rejects
def test_unsupported_media_type_rejects(tmp_path: Path) -> None:
    source = tmp_path / "not_media.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(CleanExportVerificationError, match="unsupported media type"):
        verify_clean_export(source)


def test_nonexistent_source_rejects(tmp_path: Path) -> None:
    with pytest.raises(CleanExportVerificationError, match="does not exist"):
        verify_clean_export(tmp_path / "ghost.png")


# 9. queue media path becomes verified clean derivative path
# 10. raw source path remains preserved separately as provenance
def test_apply_clean_export_fields_sets_media_path_and_preserves_source(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "queue_item.png")
    facts = verify_clean_export(source)

    promoted_item = {
        "media_path": str(source),
        "metadata": {"queue_draft_only": False},
    }
    _apply_clean_export_fields(promoted_item, facts)

    assert promoted_item["media_path"] == facts["clean_derivative_path"]
    assert promoted_item["media_path"] != str(source)
    assert promoted_item["metadata"]["source_asset_path"] == str(source)
    assert promoted_item["metadata"]["source_asset_sha256"] == facts["source_sha256"]
    assert promoted_item["metadata"]["clean_export_derivative_sha256"] == facts["clean_derivative_sha256"]
    assert promoted_item["metadata"]["clean_export_sidecar_path"] == facts["clean_provenance_sidecar_path"]
    assert promoted_item["metadata"]["clean_export_verified"] is True


# 11. historical/raw-only item does not silently pass
# 12. no fallback to raw source occurs
def test_validate_clean_export_wrapper_rejects_historical_raw_only_item(tmp_path: Path) -> None:
    """Simulates a historical queue draft that predates the clean-export
    contract: media_path points at a real file, but no clean derivative was
    ever produced for it. Must fail closed via PromoteError, never fall
    back to treating the raw source as eligible."""
    raw_only_source = _make_source_png(tmp_path / "historical_raw_only.png")
    queue_draft = {"media_path": str(raw_only_source)}

    with pytest.raises(PromoteError, match="clean-export verification failed"):
        _validate_clean_export(queue_draft)

    # The raw source itself must remain completely untouched by the failed
    # verification attempt.
    assert raw_only_source.exists()
    assert resolve_clean_output_path(raw_only_source).exists() is False


def test_validate_clean_export_wrapper_succeeds_for_real_pair(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "wrapper_success.png")
    queue_draft = {"media_path": str(source)}
    facts = _validate_clean_export(queue_draft)
    assert facts["verified_clean_after_scrub"] is True
    assert facts["clean_derivative_path"] == str(resolve_clean_output_path(source))
