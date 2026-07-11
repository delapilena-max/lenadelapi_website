from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tools.lena_scrub_media_metadata_v1 import resolve_clean_output_path, scrub_image_metadata
from pipeline.publisher.instagram_queue_bridge import (
    _validate_contract,
    _validate_downstream_clean_export,
)


def _make_source_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(50, 60, 70)).save(path, format="PNG")
    return path


def _make_clean_pair(tmp_path: Path, name: str = "asset_seed.png") -> Path:
    """Real source + a real scrubber-produced derivative/sidecar -- same
    fixture pattern as tests/test_lena_clean_export_contract_v1.py, kept
    independent here rather than imported, so this test file never depends
    on internal helpers of the promotion-layer test module."""
    source = _make_source_png(tmp_path / name)
    scrub_image_metadata(source)
    return source


def _valid_metadata(source: Path, clean_path: Path) -> dict:
    import hashlib

    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    return {
        "clean_export_verified": True,
        "source_asset_path": str(source),
        "source_asset_sha256": sha(source),
        "clean_export_derivative_sha256": sha(clean_path),
    }


def _valid_payload(source: Path) -> dict:
    clean_path = resolve_clean_output_path(source)
    return {
        "media_path": str(clean_path),
        "metadata": _valid_metadata(source, clean_path),
    }


# 1. genuinely verified clean queue item passes contract validation
def test_genuinely_verified_clean_item_passes(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path)
    payload = _valid_payload(source)
    _validate_downstream_clean_export(payload)  # must not raise


# 2. clean_export_verified missing rejects
def test_missing_clean_export_verified_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "missing_flag.png")
    payload = _valid_payload(source)
    del payload["metadata"]["clean_export_verified"]
    with pytest.raises(ValueError, match="clean_export_verified"):
        _validate_downstream_clean_export(payload)


# 3. false or truthy-but-not-literal-true rejects
@pytest.mark.parametrize("bad_value", [False, 1, "true", None])
def test_clean_export_verified_non_true_rejects(tmp_path: Path, bad_value) -> None:
    source = _make_clean_pair(tmp_path, f"non_true_{bad_value}.png")
    payload = _valid_payload(source)
    payload["metadata"]["clean_export_verified"] = bad_value
    with pytest.raises(ValueError, match="clean_export_verified"):
        _validate_downstream_clean_export(payload)


# 4. missing derivative rejects
def test_missing_derivative_rejects(tmp_path: Path) -> None:
    source = _make_source_png(tmp_path / "no_derivative.png")  # scrubber never run
    clean_path = resolve_clean_output_path(source)
    payload = {
        "media_path": str(clean_path),
        "metadata": {
            "clean_export_verified": True,
            "source_asset_path": str(source),
        },
    }
    with pytest.raises(ValueError, match="clean-export re-verification failed"):
        _validate_downstream_clean_export(payload)


# 5. missing sidecar rejects
def test_missing_sidecar_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "missing_sidecar.png")
    clean_path = resolve_clean_output_path(source)
    sidecar_path = clean_path.with_name(clean_path.stem + "_provenance.json")
    sidecar_path.unlink()
    payload = _valid_payload(source)
    with pytest.raises(ValueError, match="clean-export re-verification failed"):
        _validate_downstream_clean_export(payload)


# 6. derivative hash mismatch rejects (tampering after promotion)
def test_derivative_tampered_after_promotion_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "tampered_derivative.png")
    payload = _valid_payload(source)
    clean_path = resolve_clean_output_path(source)
    # Simulate tampering: the derivative file is modified after promotion,
    # so its bytes on disk no longer match the sidecar's recorded hash.
    with clean_path.open("ab") as fh:
        fh.write(b"\x00tampered")
    with pytest.raises(ValueError, match="clean-export re-verification failed"):
        _validate_downstream_clean_export(payload)


# 7. source hash mismatch rejects where source is available
def test_source_tampered_after_promotion_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "tampered_source.png")
    payload = _valid_payload(source)
    with source.open("ab") as fh:
        fh.write(b"\x00tampered")
    with pytest.raises(ValueError, match="clean-export re-verification failed"):
        _validate_downstream_clean_export(payload)


def test_stale_metadata_source_hash_rejects_even_if_files_untouched(tmp_path: Path) -> None:
    """A subtler tampering case: the real files on disk are untouched and
    would pass verify_clean_export() on their own, but the queue item's own
    recorded metadata.source_asset_sha256 has gone stale/been edited --
    must still reject via the cross-check against the fresh re-verification."""
    source = _make_clean_pair(tmp_path, "stale_metadata.png")
    payload = _valid_payload(source)
    payload["metadata"]["source_asset_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source_asset_sha256"):
        _validate_downstream_clean_export(payload)


def test_stale_metadata_derivative_hash_rejects_even_if_files_untouched(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "stale_derivative_metadata.png")
    payload = _valid_payload(source)
    payload["metadata"]["clean_export_derivative_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="clean_export_derivative_sha256"):
        _validate_downstream_clean_export(payload)


# 8. queue media_path pointing at raw source rejects
def test_media_path_pointing_at_raw_source_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "media_path_is_raw.png")
    payload = _valid_payload(source)
    payload["media_path"] = str(source)  # tampered/misconfigured: points at raw source
    with pytest.raises(ValueError, match="does not equal the independently"):
        _validate_downstream_clean_export(payload)


# 9. queue media_path pointing at a different file than the verified derivative rejects
def test_media_path_pointing_elsewhere_rejects(tmp_path: Path) -> None:
    source = _make_clean_pair(tmp_path, "media_path_elsewhere.png")
    payload = _valid_payload(source)
    decoy = tmp_path / "decoy.png"
    Image.new("RGB", (2, 2)).save(decoy, format="PNG")
    payload["media_path"] = str(decoy)
    with pytest.raises(ValueError, match="does not equal the independently"):
        _validate_downstream_clean_export(payload)


# 10. no raw-source fallback occurs
def test_no_fallback_to_raw_source_on_any_failure(tmp_path: Path) -> None:
    """Every failure path above raises before returning -- there is no
    return value or side effect that could cause a caller to treat the raw
    source as an acceptable substitute. This test enumerates several
    failure payloads and confirms every one raises ValueError, never
    silently returning None/True."""
    source = _make_source_png(tmp_path / "no_fallback.png")  # no derivative at all
    payload = {
        "media_path": str(source),  # deliberately the raw source itself
        "metadata": {
            "clean_export_verified": True,
            "source_asset_path": str(source),
        },
    }
    with pytest.raises(ValueError):
        _validate_downstream_clean_export(payload)


# 11. historical pre-contract queue item fails closed
def test_historical_pre_contract_item_fails_closed(tmp_path: Path) -> None:
    """A queue item shaped like one written before this contract existed:
    plain media_path pointing at a raw asset, no clean-export metadata at
    all. Must reject, not silently pass through."""
    source = _make_source_png(tmp_path / "historical_item.png")
    payload = {
        "media_path": str(source),
        "metadata": {"avatar_nickname": "Lena"},
    }
    with pytest.raises(ValueError, match="clean_export_verified"):
        _validate_downstream_clean_export(payload)


# 12. existing valid non-live test fixtures remain unaffected where applicable
def test_full_validate_contract_story_branch_passes_with_clean_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration check: a fully valid Story payload (real contract file,
    unmodified) passes _validate_contract() end-to-end once clean-export
    metadata is present and genuinely verifiable -- proves the new gate is
    wired in without breaking the pre-existing, unrelated per-media-type
    checks (engine/prompt/platform/hashtags)."""
    source = _make_clean_pair(tmp_path, "story_integration.png")
    clean_path = resolve_clean_output_path(source)

    payload = {
        "platforms": ["instagram"],
        "media_path": str(clean_path),
        "media_type": "story",
        "caption": "soft light today #vibes",
        "metadata": {
            **_valid_metadata(source, clean_path),
            "avatar_nickname": "Lena",
            "image_engine": "kling_image_3.0",
            "image_prompt": "a real prompt",
        },
    }
    _validate_contract(payload)  # must not raise
