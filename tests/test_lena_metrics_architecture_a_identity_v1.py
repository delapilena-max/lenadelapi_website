from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import tools.lena_sync_architecture_a_receipts_to_metrics_v1 as sync_mod
from tools.lena_sync_architecture_a_receipts_to_metrics_v1 import (
    METRIC_FIELDS,
    LEGACY_METRIC_FIELDS,
    NEW_CREATIVE_PROVENANCE_FIELDS,
    build_identity_fields,
    derive_date,
    derive_platform_label,
    resolve_canonical_provenance,
    sync_all,
    upsert_metrics_row,
    read_csv,
    write_csv,
    _historical_nested_instagram_media_id,
)
from tools.lena_meta_refresh_feedback_v1 import (
    apply_fetched_metrics,
    candidate_posts,
    metric_success,
    resolve_structured_post_id,
    parse_post_id,
    row_has_unknown_scoring_inputs,
)
import tools.lena_repair_architecture_a_legacy_zero_placeholders_v1 as repair_mod
from tools.lena_repair_architecture_a_legacy_zero_placeholders_v1 import (
    FIELDS_TO_BLANK,
    TARGET_KEYS,
    PreconditionError,
    build_repaired_candidate,
    verify_postconditions,
    verify_preconditions,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _real_receipt(post_id: str = "readypack-test-01-photo") -> dict:
    """Shaped exactly like a real, already-committed Architecture A
    receipt (pipeline/queue/published/readypack0709-pack007-00-photo-
    story.json.receipt.json), fields renamed only for isolation."""
    return {
        "caption": "test caption\n\n#test",
        "instagram_media_id": "17879977575673516",
        "instagram_media_type": "IMAGE",
        "instagram_timestamp": "2026-07-10T21:31:17+0000",
        "media_path": "C:\\fake\\path\\seed.png",
        "media_type": "story",
        "permalink": "https://www.instagram.com/stories/lenadelapineapple.official/123",
        "platforms": ["instagram"],
        "post_file": "C:\\fake\\queue\\test.json",
        "post_id": post_id,
        "published_post_path": "",  # filled per-test
        "status": "published",
        "timestamp_utc": "2026-07-10T21:31:19+00:00",
    }


def _promoted_queue_item(post_id: str, clean_export_verified: bool = True) -> dict:
    metadata = {
        "avatar_nickname": "Lena",
        "source_date": "2026-07-11",
        "source_slot_id": post_id,
    }
    if clean_export_verified:
        metadata.update({
            "source_asset_path": "C:\\fake\\assets\\raw_seed.png",
            "source_asset_sha256": "a" * 64,
            "clean_export_derivative_sha256": "b" * 64,
            "clean_export_verified": True,
            "clean_export_sidecar_path": "C:\\fake\\assets\\raw_seed_clean_provenance.json",
        })
        media_path = "C:\\fake\\assets\\raw_seed_clean.png"
    else:
        media_path = "C:\\fake\\assets\\raw_seed.png"
    return {
        "post_id": post_id,
        "slot_id": post_id,
        "media_path": media_path,
        "media_type": "story",
        "platforms": ["instagram"],
        "caption": "test caption\n\n#test",
        "approved_for_live_publish": True,
        "operator_review_required": False,
        "metadata": metadata,
    }


# 4. Architecture A receipt identity can populate the structured metrics identity
# 5. post_id remains preserved
# 6. slot_id remains preserved
# 8. permalink is preserved when available
# 9. publish receipt path is preserved when available
def test_build_identity_fields_from_real_receipt_shape(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "readypack-test-01-photo.json.receipt.json"
    queue_item_path = published_dir / "readypack-test-01-photo.json"

    receipt = _real_receipt("readypack-test-01-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("readypack-test-01-photo"))

    identity = build_identity_fields(receipt, receipt_path)

    assert identity["post_id"] == "readypack-test-01-photo"
    assert identity["slot_id"] == "readypack-test-01-photo"
    assert identity["instagram_media_id"] == "17879977575673516"
    assert identity["permalink"] == "https://www.instagram.com/stories/lenadelapineapple.official/123"
    assert identity["publish_receipt_path"] == str(receipt_path)
    assert identity["date"] == "2026-07-11"
    assert identity["platform"] == "Instagram Story"


# 7. output/source identity is not silently rewritten
def test_source_slot_id_falls_back_to_slot_id_when_absent(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-02-photo.json.receipt.json"
    receipt = _real_receipt("test-02-photo")
    _write_json(receipt_path, receipt)
    # No sibling queue item at all -- source_slot_id must fall back to
    # slot_id, never be fabricated as something else.
    identity = build_identity_fields(receipt, receipt_path)
    assert identity["source_slot_id"] == "test-02-photo"
    assert identity["slot_id"] == "test-02-photo"


# 10. clean-export provenance is attached only when actually available
def test_clean_export_provenance_attached_when_verified(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-03-photo.json.receipt.json"
    queue_item_path = published_dir / "test-03-photo.json"
    receipt = _real_receipt("test-03-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("test-03-photo", clean_export_verified=True))

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["clean_export_verified"] == "true"
    assert identity["source_asset_path"] == "C:\\fake\\assets\\raw_seed.png"
    assert identity["clean_derivative_path"] == "C:\\fake\\assets\\raw_seed_clean.png"
    assert identity["source_asset_sha256"] == "a" * 64
    assert identity["clean_export_derivative_sha256"] == "b" * 64


# 11. missing provenance does not create fake values
def test_clean_export_provenance_absent_for_pre_contract_item(tmp_path: Path) -> None:
    """Mirrors the real, currently-committed pre-clean-export-contract item
    (readypack0709-pack003-08-photo.json) -- media_path is the raw source,
    no clean_export_verified field exists at all."""
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-04-photo.json.receipt.json"
    queue_item_path = published_dir / "test-04-photo.json"
    receipt = _real_receipt("test-04-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("test-04-photo", clean_export_verified=False))

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["clean_export_verified"] == "false"
    assert identity["clean_derivative_path"] == ""
    assert identity["source_asset_path"] == ""
    assert identity["source_asset_sha256"] == ""
    assert identity["clean_export_derivative_sha256"] == ""


def test_missing_queue_item_produces_no_fabricated_provenance(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-05-photo.json.receipt.json"
    receipt = _real_receipt("test-05-photo")
    receipt["published_post_path"] = str(published_dir / "does_not_exist.json")
    _write_json(receipt_path, receipt)

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["source_asset_path"] == ""
    assert identity["clean_export_verified"] == "false"
    assert identity["date"] == ""  # no metadata.source_date, no YYYY-MM-DD prefix in slot_id


def test_derive_date_prefers_source_date_then_slot_prefix() -> None:
    assert derive_date("anything", {"source_date": "2026-07-09"}) == "2026-07-09"
    assert derive_date("2026-07-05-01-photo", {}) == "2026-07-05"
    assert derive_date("readypack0709-pack003-08-photo", {}) == ""  # never a guess


def test_derive_platform_label_from_media_type() -> None:
    assert derive_platform_label("photo") == "Instagram Feed"
    assert derive_platform_label("story") == "Instagram Story"
    assert derive_platform_label("stories") == "Instagram Story"
    assert derive_platform_label("video") == "Instagram Reels"
    assert derive_platform_label("reel") == "Instagram Reels"


# QA/approval join proof
def test_resolve_canonical_provenance_finds_real_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_review_root = tmp_path / "asset_review" / "lena"
    approval_root = tmp_path / "publish_packets" / "lena"
    monkeypatch.setattr(sync_mod, "ASSET_REVIEW_ROOT", asset_review_root)
    monkeypatch.setattr(sync_mod, "APPROVAL_ROOT", approval_root)

    date_str, slot_id = "2026-07-11", "test-06-photo"
    qa_path = asset_review_root / date_str / f"{slot_id}_qa.json"
    approval_path = approval_root / date_str / f"{slot_id}_approval.json"
    _write_json(qa_path, {"overall": "pass"})
    _write_json(approval_path, {"post_id": slot_id})

    provenance = resolve_canonical_provenance(date_str, slot_id)
    assert provenance["qa_artifact_path"] == str(qa_path)
    assert provenance["approval_record_path"] == str(approval_path)


def test_resolve_canonical_provenance_reports_none_when_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_mod, "ASSET_REVIEW_ROOT", tmp_path / "asset_review" / "lena")
    monkeypatch.setattr(sync_mod, "APPROVAL_ROOT", tmp_path / "publish_packets" / "lena")
    provenance = resolve_canonical_provenance("2026-07-11", "nonexistent-slot")
    assert provenance["qa_artifact_path"] is None
    assert provenance["approval_record_path"] is None


# 3. historical rows missing new columns still load safely
# 12. no historical artifact is rewritten (source files untouched by this test)
def test_historical_csv_rows_load_and_survive_upsert(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.csv"
    with metrics_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEGACY_METRIC_FIELDS)
        writer.writeheader()
        writer.writerow({
            "date": "2026-06-24", "slot_id": "2026-06-24-01-photo", "platform": "Instagram Feed",
            "media_type": "photo", "growth_bucket": "engagement", "lane": "coffee",
            "hook_category": "coffee_walk", "post_url": "https://example.com/p/abc",
            "audio_name": "", "reach": "0", "likes": "0", "saves": "0", "shares": "0",
            "comments": "0", "follows": "0", "profile_visits": "0", "completion_rate": "0.0",
            "replay_rate": "0.0", "score": "0.0", "classification": "weak",
            "notes": "Auto-synced from posted queue q_abc; historical row.",
        })

    rows = read_csv(metrics_path)
    assert len(rows) == 1
    assert rows[0]["classification"] == "weak"  # loads fine with legacy-only header

    identity = {
        "date": "2026-07-11", "slot_id": "different-slot", "platform": "Instagram Feed",
        "media_type": "photo", "post_id": "different-slot", "instagram_media_id": "999",
        "permalink": "", "source_slot_id": "different-slot", "publish_receipt_path": "",
        "source_asset_path": "", "clean_derivative_path": "", "source_asset_sha256": "",
        "clean_export_derivative_sha256": "", "clean_export_verified": "false",
    }
    rows, is_new = upsert_metrics_row(rows, identity)
    assert is_new is True
    assert len(rows) == 2

    write_csv(metrics_path, rows)
    reloaded = read_csv(metrics_path)
    assert len(reloaded) == 2
    historical = next(r for r in reloaded if r["slot_id"] == "2026-06-24-01-photo")
    # Every original value preserved byte-identical; new columns present but blank.
    assert historical["classification"] == "weak"
    assert historical["notes"] == "Auto-synced from posted queue q_abc; historical row."
    assert historical.get("instagram_media_id", "") == ""


def test_upsert_never_overwrites_existing_identity_with_blank(tmp_path: Path) -> None:
    rows = [{
        "date": "2026-07-11", "slot_id": "test-07-photo", "platform": "Instagram Feed",
        "instagram_media_id": "111", "permalink": "https://real.example/1",
    }]
    identity = {
        "date": "2026-07-11", "slot_id": "test-07-photo", "platform": "Instagram Feed",
        "media_type": "photo", "post_id": "", "instagram_media_id": "", "permalink": "",
        "source_slot_id": "", "publish_receipt_path": "", "source_asset_path": "",
        "clean_derivative_path": "", "source_asset_sha256": "", "clean_export_derivative_sha256": "",
        "clean_export_verified": "false",
    }
    rows, is_new = upsert_metrics_row(rows, identity)
    assert is_new is False
    assert rows[0]["instagram_media_id"] == "111"  # not blanked out
    assert rows[0]["permalink"] == "https://real.example/1"


# End-to-end sync_all over isolated fixtures
def test_sync_all_dry_run_does_not_write(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    metrics_path = tmp_path / "metrics.csv"
    receipt_path = published_dir / "test-08-photo.json.receipt.json"
    queue_item_path = published_dir / "test-08-photo.json"
    receipt = _real_receipt("test-08-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("test-08-photo"))

    result = sync_all(published_dir, metrics_path, apply=False)
    assert result["receipts_scanned"] == 1
    assert result["created"] == 1
    assert not metrics_path.exists()  # dry-run: no write


def test_sync_all_apply_writes_metrics_csv(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    metrics_path = tmp_path / "metrics.csv"
    receipt_path = published_dir / "test-09-photo.json.receipt.json"
    queue_item_path = published_dir / "test-09-photo.json"
    receipt = _real_receipt("test-09-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("test-09-photo"))

    result = sync_all(published_dir, metrics_path, apply=True)
    assert result["created"] == 1
    assert metrics_path.exists()
    rows = read_csv(metrics_path)
    assert len(rows) == 1
    assert rows[0]["instagram_media_id"] == "17879977575673516"
    assert rows[0]["classification"] == "pending"
    assert rows[0]["follows"] == ""
    assert rows[0]["profile_visits"] == ""
    assert rows[0]["completion_rate"] == ""
    assert rows[0]["replay_rate"] == ""
    assert rows[0]["score"] == "0"


def test_unknown_unfetched_metrics_do_not_turn_architecture_a_pending_row_weak(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-cross-tool-01-photo.json.receipt.json"
    queue_item_path = published_dir / "test-cross-tool-01-photo.json"
    receipt = _real_receipt("test-cross-tool-01-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("test-cross-tool-01-photo"))

    identity = build_identity_fields(receipt, receipt_path)
    rows, is_new = upsert_metrics_row([], identity)

    assert is_new is True
    assert len(rows) == 1
    pre_refresh_row = rows[0]

    assert pre_refresh_row["reach"] == "0"
    assert pre_refresh_row["likes"] == "0"
    assert pre_refresh_row["saves"] == "0"
    assert pre_refresh_row["shares"] == "0"
    assert pre_refresh_row["comments"] == "0"
    assert pre_refresh_row["follows"] == ""
    assert pre_refresh_row["profile_visits"] == ""
    assert pre_refresh_row["completion_rate"] == ""
    assert pre_refresh_row["replay_rate"] == ""
    assert pre_refresh_row["score"] == "0"
    assert pre_refresh_row["classification"] == "pending"

    fetched = {
        "metric_results": {
            "reach": metric_success(0),
            "likes": metric_success(0),
            "saves": metric_success(0),
            "shares": metric_success(0),
            "comments": metric_success(0),
            "profile_visits": {"ok": False, "reason": "never fetched"},
            "completion_rate": {"ok": False, "reason": "never fetched"},
            "replay_rate": {"ok": False, "reason": "never fetched"},
        }
    }

    merged = apply_fetched_metrics(dict(pre_refresh_row), fetched, is_new_row=True)

    assert merged["reach"] == "0"
    assert merged["likes"] == "0"
    assert merged["saves"] == "0"
    assert merged["shares"] == "0"
    assert merged["comments"] == "0"
    assert merged["follows"] == ""
    assert merged["profile_visits"] == ""
    assert merged["completion_rate"] == ""
    assert merged["replay_rate"] == ""
    assert merged["score"] == ""
    assert merged["classification"] == "pending"
    assert merged["score"] != "0.0"
    assert merged["classification"] != "weak"


# 1. structured platform media ID is preferred over notes regex
def test_resolve_structured_post_id_prefers_structured_field() -> None:
    post_row = {"date": "2026-07-11", "slot_id": "test-10-photo", "platform": "Instagram Feed", "notes": "post_id:LEGACY123"}
    metric_index = {
        ("2026-07-11", "test-10-photo", "Instagram Feed"): {"instagram_media_id": "STRUCTURED456"},
    }
    assert resolve_structured_post_id(post_row, metric_index) == "STRUCTURED456"


# 2. historical notes regex fallback still works
def test_resolve_structured_post_id_falls_back_to_notes_regex() -> None:
    post_row = {"date": "2026-06-12", "slot_id": "2026-06-12-03-video", "platform": "TikTok", "notes": "post_id:18139386292538988"}
    metric_index = {}  # no structured row at all -- purely historical
    assert resolve_structured_post_id(post_row, metric_index) == "18139386292538988"
    assert resolve_structured_post_id(post_row, metric_index) == parse_post_id(post_row["notes"])


def test_candidate_posts_uses_structured_precedence_end_to_end() -> None:
    post_rows = [{
        "date": "2026-07-11", "slot_id": "test-11-photo", "platform": "Instagram Feed",
        "post_url": "https://real.example/1", "posted_at": "2026-07-11T10:00:00", "notes": "post_id:STALE",
    }]
    metric_rows = [{
        "date": "2026-07-11", "slot_id": "test-11-photo", "platform": "Instagram Feed",
        "instagram_media_id": "FRESH789",
    }]
    candidates = candidate_posts(post_rows, metric_rows, days_back=365, max_posts=10)
    assert len(candidates) == 1
    assert candidates[0]["_post_id"] == "FRESH789"


# 13/14/15. no network call, no publish, no queue mutation -- structural
# guarantee: sync_mod imports no `requests`/publisher/queue-processing
# module, and every test above operates purely on tmp_path fixtures.


def _real_receipt_with_nested_media_id(post_id: str, nested_id: str = "18154201054431808") -> dict:
    """Shaped exactly like the real, already-committed historical receipt
    (pipeline/queue/published/2026-07-07-03-photo.json.receipt.json): no
    top-level instagram_media_id/permalink field at all, but the real
    platform ID is present nested at publish_response.result.
    instagram_result.instagram_media_id."""
    return {
        "caption": "test caption\n\n#test",
        "media_path": "C:\\fake\\path\\seed.png",
        "media_type": "photo",
        "platforms": ["instagram"],
        "post_file": "C:\\fake\\queue\\test.json",
        "post_id": post_id,
        "publish_response": {
            "backend": "pipeline.publisher.instagram_queue_bridge",
            "ok": True,
            "result": {
                "backend": "instagram_graph",
                "instagram_result": {
                    "backend": "instagram_graph",
                    "instagram_media_id": nested_id,
                    "media_type": "photo",
                    "ok": True,
                    "post_id": post_id,
                },
                "kind": "photo",
                "ok": True,
                "post_id": post_id,
            },
        },
        "status": "published",
        "timestamp_utc": "2026-07-07T17:00:17.789500+00:00",
    }


# 1. top-level instagram_media_id remains preferred when present
def test_nested_media_id_fallback_never_overrides_top_level_field() -> None:
    receipt = _real_receipt("test-nested-01-photo")  # has top-level instagram_media_id
    receipt["publish_response"] = {
        "result": {"instagram_result": {"instagram_media_id": "SHOULD_NOT_WIN"}}
    }
    assert build_identity_fields(receipt, Path("fake.json.receipt.json"))["instagram_media_id"] == "17879977575673516"


# 2/6. historical nested instagram_media_id is used only when top-level is absent
def test_historical_nested_media_id_used_only_when_top_level_absent(tmp_path: Path) -> None:
    receipt_path = tmp_path / "published" / "2026-07-07-03-photo.json.receipt.json"
    receipt = _real_receipt_with_nested_media_id("2026-07-07-03-photo")
    assert "instagram_media_id" not in receipt  # real shape: no top-level field at all
    identity = build_identity_fields(receipt, receipt_path)
    assert identity["instagram_media_id"] == "18154201054431808"


# 3. blank remains blank when neither ID path exists
def test_media_id_stays_blank_when_neither_path_exists(tmp_path: Path) -> None:
    receipt_path = tmp_path / "published" / "test-nested-02-photo.json.receipt.json"
    receipt = _real_receipt_with_nested_media_id("test-nested-02-photo")
    del receipt["publish_response"]
    identity = build_identity_fields(receipt, receipt_path)
    assert identity["instagram_media_id"] == ""


# 4. no arbitrary deep-search fallback exists -- only the exact known
# historical shape is supported, not any other nesting depth/key name
def test_historical_nested_fallback_does_not_deep_search_arbitrary_shapes() -> None:
    off_path_receipt = {
        "publish_response": {"instagram_media_id": "WRONG_DEPTH"},  # missing .result
    }
    assert _historical_nested_instagram_media_id(off_path_receipt) == ""

    wrong_key_receipt = {
        "publish_response": {"result": {"some_other_result": {"instagram_media_id": "WRONG_KEY"}}},
    }
    assert _historical_nested_instagram_media_id(wrong_key_receipt) == ""

    non_string_receipt = {
        "publish_response": {"result": {"instagram_result": {"instagram_media_id": 12345}}},
    }
    assert _historical_nested_instagram_media_id(non_string_receipt) == ""


# 5. output-slot QA artifact is preferred when present
def test_qa_provenance_prefers_output_slot_over_source_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_review_root = tmp_path / "asset_review" / "lena"
    monkeypatch.setattr(sync_mod, "ASSET_REVIEW_ROOT", asset_review_root)
    monkeypatch.setattr(sync_mod, "APPROVAL_ROOT", tmp_path / "publish_packets" / "lena")

    date_str, slot_id, source_slot_id = "2026-07-09", "readypack0709-pack007-00-photo-story", "readypack0709-pack007-00-photo"
    output_qa_path = asset_review_root / date_str / f"{slot_id}_qa.json"
    source_qa_path = asset_review_root / date_str / f"{source_slot_id}_qa.json"
    _write_json(output_qa_path, {"overall": "pass", "note": "output slot"})
    _write_json(source_qa_path, {"overall": "pass", "note": "source slot"})

    provenance = resolve_canonical_provenance(date_str, slot_id, source_slot_id)
    assert provenance["qa_artifact_path"] == str(output_qa_path)


# 6/9. source_slot_id QA artifact is used only when output-slot QA is
# absent -- mirrors the real readypack0709-pack007-00-photo-story case
def test_qa_provenance_falls_back_to_source_slot_when_output_slot_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_review_root = tmp_path / "asset_review" / "lena"
    monkeypatch.setattr(sync_mod, "ASSET_REVIEW_ROOT", asset_review_root)
    monkeypatch.setattr(sync_mod, "APPROVAL_ROOT", tmp_path / "publish_packets" / "lena")

    date_str, slot_id, source_slot_id = "2026-07-09", "readypack0709-pack007-00-photo-story", "readypack0709-pack007-00-photo"
    source_qa_path = asset_review_root / date_str / f"{source_slot_id}_qa.json"
    _write_json(source_qa_path, {"overall": "pass"})
    # No QA artifact written under slot_id (the output/Story slot) at all.

    provenance = resolve_canonical_provenance(date_str, slot_id, source_slot_id)
    assert provenance["qa_artifact_path"] == str(source_qa_path)


# 7/8/9. source-slot QA fallback never changes canonical output identity;
# slot_id, post_id, and source_slot_id all stay exactly as resolved by
# build_identity_fields, independent of which slot the QA evidence was
# actually found under
def test_source_slot_qa_fallback_does_not_alter_output_identity(tmp_path: Path) -> None:
    receipt_path = tmp_path / "published" / "readypack0709-pack007-00-photo-story.json.receipt.json"
    queue_item_path = tmp_path / "published" / "readypack0709-pack007-00-photo-story.json"
    receipt = _real_receipt("readypack0709-pack007-00-photo-story")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    queue_item = _promoted_queue_item("readypack0709-pack007-00-photo-story")
    queue_item["metadata"]["source_slot_id"] = "readypack0709-pack007-00-photo"
    _write_json(queue_item_path, queue_item)

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["slot_id"] == "readypack0709-pack007-00-photo-story"
    assert identity["post_id"] == "readypack0709-pack007-00-photo-story"
    assert identity["source_slot_id"] == "readypack0709-pack007-00-photo"


# 10. missing QA evidence remains None rather than fabricated, even with
# a real, differing source_slot_id supplied
def test_qa_provenance_none_when_neither_output_nor_source_slot_has_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_mod, "ASSET_REVIEW_ROOT", tmp_path / "asset_review" / "lena")
    monkeypatch.setattr(sync_mod, "APPROVAL_ROOT", tmp_path / "publish_packets" / "lena")
    provenance = resolve_canonical_provenance("2026-07-09", "nonexistent-output-slot", "nonexistent-source-slot")
    assert provenance["qa_artifact_path"] is None


# 11. missing approval record remains absent -- no source-slot fallback
# exists for approval records (only QA gets one), matching the real
# 2026-07-07-03-photo gap
def test_approval_record_has_no_source_slot_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_review_root = tmp_path / "asset_review" / "lena"
    approval_root = tmp_path / "publish_packets" / "lena"
    monkeypatch.setattr(sync_mod, "ASSET_REVIEW_ROOT", asset_review_root)
    monkeypatch.setattr(sync_mod, "APPROVAL_ROOT", approval_root)

    date_str, slot_id, source_slot_id = "2026-07-09", "output-slot", "source-slot"
    # An approval record exists only under the source slot -- must NOT be
    # picked up for the output slot's approval_record_path.
    _write_json(approval_root / date_str / f"{source_slot_id}_approval.json", {"post_id": source_slot_id})

    provenance = resolve_canonical_provenance(date_str, slot_id, source_slot_id)
    assert provenance["approval_record_path"] is None


# 12. missing permalink remains blank -- matches the real
# 2026-07-07-03-photo receipt, which has no permalink field anywhere
def test_missing_permalink_stays_blank(tmp_path: Path) -> None:
    receipt_path = tmp_path / "published" / "2026-07-07-03-photo.json.receipt.json"
    receipt = _real_receipt_with_nested_media_id("2026-07-07-03-photo")
    assert "permalink" not in receipt  # real shape: genuinely absent
    identity = build_identity_fields(receipt, receipt_path)
    assert identity["permalink"] == ""


# --- creative-provenance propagation (2026-07-11) ---------------------------
#
# wardrobe_outfit_id / pose_body_language_id / expression_gaze_id / lane
# sourced only from the real queue-item metadata that
# tools/lena_build_publish_packet_v1.py's build_queue_draft() already
# writes -- never inferred from image_prompt/pose text/caption, never
# fuzzy-matched, never recipe_id.

def _promoted_queue_item_with_provenance(
    post_id: str,
    wardrobe_outfit_id=None,
    pose_body_language_id=None,
    expression_gaze_id=None,
    activity=None,
) -> dict:
    metadata = {
        "avatar_nickname": "Lena",
        "source_date": "2026-07-11",
        "source_slot_id": post_id,
        # Deliberately contains text overlapping real pose/expression
        # labels, to prove propagation never parses this field.
        "pose": "weight shift onto one hip, closed mouth smile direct",
        "image_prompt": "a real test prompt: weight_shift_one_hip, closed_mouth_smile_direct",
    }
    if wardrobe_outfit_id is not None:
        metadata["wardrobe_outfit_id"] = wardrobe_outfit_id
    if pose_body_language_id is not None:
        metadata["pose_body_language_id"] = pose_body_language_id
    if expression_gaze_id is not None:
        metadata["expression_gaze_id"] = expression_gaze_id
    if activity is not None:
        metadata["activity"] = activity
    return {
        "post_id": post_id,
        "slot_id": post_id,
        "media_path": "C:\\fake\\assets\\raw_seed.png",
        "media_type": "photo",
        "platforms": ["instagram"],
        "caption": "test caption\n\n#test",
        "approved_for_live_publish": True,
        "operator_review_required": False,
        "metadata": metadata,
    }


# 1. wardrobe_outfit_id propagates from queue metadata into metrics row.
# 2. pose_body_language_id propagates from queue metadata into metrics row.
# 3. expression_gaze_id propagates from queue metadata into metrics row.
# 4. metadata.activity propagates into the existing metrics `lane` column.
def test_creative_provenance_propagates_when_present(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-cp-01-photo.json.receipt.json"
    queue_item_path = published_dir / "test-cp-01-photo.json"
    receipt = _real_receipt("test-cp-01-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(
        queue_item_path,
        _promoted_queue_item_with_provenance(
            "test-cp-01-photo",
            wardrobe_outfit_id="wc_p006",
            pose_body_language_id="pose_p018",
            expression_gaze_id="exp_g013",
            activity="rooftop sunset",
        ),
    )

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["wardrobe_outfit_id"] == "wc_p006"
    assert identity["pose_body_language_id"] == "pose_p018"
    assert identity["expression_gaze_id"] == "exp_g013"
    assert identity["lane"] == "rooftop sunset"


# 6. Missing wardrobe_outfit_id remains blank.
# 7. Missing pose_body_language_id remains blank.
# 8. Missing expression_gaze_id remains blank.
# 9. No pose ID is inferred from pose free text.
# 10. No expression ID is inferred from prompt text.
def test_creative_provenance_stays_blank_when_absent_and_never_inferred(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-cp-02-photo.json.receipt.json"
    queue_item_path = published_dir / "test-cp-02-photo.json"
    receipt = _real_receipt("test-cp-02-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    # No wardrobe_outfit_id/pose_body_language_id/expression_gaze_id/activity
    # passed -- but metadata.pose and metadata.image_prompt both contain
    # real pose/expression label text (see helper above).
    _write_json(queue_item_path, _promoted_queue_item_with_provenance("test-cp-02-photo"))

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["wardrobe_outfit_id"] == ""
    assert identity["pose_body_language_id"] == ""
    assert identity["expression_gaze_id"] == ""
    assert identity["lane"] == ""


# 11. No recipe_id is introduced.
def test_creative_provenance_never_introduces_recipe_id() -> None:
    assert "recipe_id" not in METRIC_FIELDS
    assert "recipe_id" not in NEW_CREATIVE_PROVENANCE_FIELDS


# 5. Existing nonblank historical lane values are preserved (never
# overwritten, even with a different real value from queue metadata).
def test_upsert_never_overwrites_nonblank_historical_lane(tmp_path: Path) -> None:
    rows = [{
        "date": "2026-07-11", "slot_id": "test-cp-03-photo", "platform": "Instagram Feed",
        "lane": "coffee",  # real, pre-existing historical value
    }]
    identity = {
        "date": "2026-07-11", "slot_id": "test-cp-03-photo", "platform": "Instagram Feed",
        "media_type": "photo", "lane": "rooftop sunset",  # different real value
        "wardrobe_outfit_id": "", "pose_body_language_id": "", "expression_gaze_id": "",
        "post_id": "", "instagram_media_id": "", "permalink": "",
        "source_slot_id": "", "publish_receipt_path": "", "source_asset_path": "",
        "clean_derivative_path": "", "source_asset_sha256": "", "clean_export_derivative_sha256": "",
        "clean_export_verified": "false",
    }
    rows, is_new = upsert_metrics_row(rows, identity)
    assert is_new is False
    assert rows[0]["lane"] == "coffee"  # untouched, not overwritten


# Blank historical lane IS filled in from real queue metadata.
def test_upsert_fills_blank_historical_lane(tmp_path: Path) -> None:
    rows = [{
        "date": "2026-07-11", "slot_id": "test-cp-04-photo", "platform": "Instagram Feed",
        "lane": "",
    }]
    identity = {
        "date": "2026-07-11", "slot_id": "test-cp-04-photo", "platform": "Instagram Feed",
        "media_type": "photo", "lane": "rooftop sunset",
        "wardrobe_outfit_id": "wc_p006", "pose_body_language_id": "pose_p018", "expression_gaze_id": "exp_g013",
        "post_id": "", "instagram_media_id": "", "permalink": "",
        "source_slot_id": "", "publish_receipt_path": "", "source_asset_path": "",
        "clean_derivative_path": "", "source_asset_sha256": "", "clean_export_derivative_sha256": "",
        "clean_export_verified": "false",
    }
    rows, is_new = upsert_metrics_row(rows, identity)
    assert is_new is False
    assert rows[0]["lane"] == "rooftop sunset"
    assert rows[0]["wardrobe_outfit_id"] == "wc_p006"
    assert rows[0]["pose_body_language_id"] == "pose_p018"
    assert rows[0]["expression_gaze_id"] == "exp_g013"


# 12. Existing structured identity behavior remains unchanged.
# 13/14. Existing clean-export provenance behavior remains unchanged.
def test_creative_provenance_slice_preserves_existing_identity_and_clean_export(tmp_path: Path) -> None:
    published_dir = tmp_path / "published"
    receipt_path = published_dir / "test-cp-05-photo.json.receipt.json"
    queue_item_path = published_dir / "test-cp-05-photo.json"
    receipt = _real_receipt("test-cp-05-photo")
    receipt["published_post_path"] = str(queue_item_path)
    _write_json(receipt_path, receipt)
    _write_json(queue_item_path, _promoted_queue_item("test-cp-05-photo", clean_export_verified=False))

    identity = build_identity_fields(receipt, receipt_path)
    assert identity["post_id"] == "test-cp-05-photo"
    assert identity["slot_id"] == "test-cp-05-photo"
    assert identity["source_slot_id"] == "test-cp-05-photo"
    assert identity["instagram_media_id"] == "17879977575673516"
    assert identity["permalink"] == "https://www.instagram.com/stories/lenadelapineapple.official/123"
    assert identity["publish_receipt_path"] == str(receipt_path)
    assert identity["clean_export_verified"] == "false"
    assert identity["source_asset_path"] == ""
    assert identity["clean_derivative_path"] == ""
    assert identity["source_asset_sha256"] == ""
    assert identity["clean_export_derivative_sha256"] == ""


# 15. Existing historical rows load successfully when the new creative
# columns are absent from the CSV header (legacy-only header, no
# wardrobe_outfit_id/pose_body_language_id/expression_gaze_id columns at all).
# 16. Existing historical legacy-field values remain semantically unchanged
# after a write.
# 17. No duplicate rows are created.
def test_historical_csv_without_creative_columns_loads_and_survives_upsert(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.csv"
    with metrics_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEGACY_METRIC_FIELDS)
        writer.writeheader()
        writer.writerow({
            "date": "2026-06-24", "slot_id": "2026-06-24-01-photo", "platform": "Instagram Feed",
            "media_type": "photo", "growth_bucket": "engagement", "lane": "coffee",
            "hook_category": "coffee_walk", "post_url": "https://example.com/p/abc",
            "audio_name": "", "reach": "0", "likes": "0", "saves": "0", "shares": "0",
            "comments": "0", "follows": "0", "profile_visits": "0", "completion_rate": "0.0",
            "replay_rate": "0.0", "score": "0.0", "classification": "weak",
            "notes": "Auto-synced from posted queue q_abc; historical row.",
        })

    rows = read_csv(metrics_path)
    assert len(rows) == 1
    assert rows[0]["lane"] == "coffee"  # loads fine with a legacy-only header

    identity = {
        "date": "2026-07-11", "slot_id": "different-slot", "platform": "Instagram Feed",
        "media_type": "photo", "post_id": "different-slot", "instagram_media_id": "999",
        "permalink": "", "source_slot_id": "different-slot", "publish_receipt_path": "",
        "source_asset_path": "", "clean_derivative_path": "", "source_asset_sha256": "",
        "clean_export_derivative_sha256": "", "clean_export_verified": "false",
        "lane": "rooftop sunset", "wardrobe_outfit_id": "wc_p006",
        "pose_body_language_id": "pose_p018", "expression_gaze_id": "exp_g013",
    }
    rows, is_new = upsert_metrics_row(rows, identity)
    assert is_new is True
    assert len(rows) == 2  # no duplicate -- exactly one new row appended

    write_csv(metrics_path, rows)
    reloaded = read_csv(metrics_path)
    assert len(reloaded) == 2
    historical = next(r for r in reloaded if r["slot_id"] == "2026-06-24-01-photo")
    # Every original legacy value preserved byte-identical; new creative
    # columns present but blank for the untouched historical row.
    assert historical["lane"] == "coffee"
    assert historical["classification"] == "weak"
    assert historical["notes"] == "Auto-synced from posted queue q_abc; historical row."
    assert historical.get("wardrobe_outfit_id", "") == ""
    assert historical.get("pose_body_language_id", "") == ""
    assert historical.get("expression_gaze_id", "") == ""

    new_row = next(r for r in reloaded if r["slot_id"] == "different-slot")
    assert new_row["lane"] == "rooftop sunset"
    assert new_row["wardrobe_outfit_id"] == "wc_p006"
    assert new_row["pose_body_language_id"] == "pose_p018"
    assert new_row["expression_gaze_id"] == "exp_g013"
    assert new_row["follows"] == ""
    assert new_row["profile_visits"] == ""
    assert new_row["completion_rate"] == ""
    assert new_row["replay_rate"] == ""
    assert new_row["classification"] == "pending"


# 18/19/20. No network call, no Meta call, no real CSV mutation during
# tests -- structural guarantee: this module imports no requests/Meta/
# publisher surface, and every test above operates purely on tmp_path
# fixtures, never pipeline/analytics/lena_post_metrics_v1_6_1.csv or any
# other real repo path.


# --- Legacy existing-row zero-placeholder repair (2026-07-12) --------------
#
# Regression guard for the real blind spot discovered during Gap B scoping:
# c7134c62 only fixed how BRAND-NEW rows are created. It did nothing for
# rows that already existed before that fix landed, which still carry
# literal "0" placeholders for follows/profile_visits/completion_rate/
# replay_rate -- fields no fetch path has ever actually measured. Directly
# reproduced: row_has_unknown_scoring_inputs() incorrectly reports such a
# row as fully known, letting a future refresh silently compute a real
# score from never-measured data (the same "unknown treated as zero"
# failure mode as the original incident, via a different vector).

def _real_shaped_metric_row(
    date: str, slot_id: str, platform: str, media_type: str = "photo",
    *, follows="0", profile_visits="0", completion_rate="0", replay_rate="0",
    reach="0", likes="0", saves="0", shares="0", comments="0",
    score="0", classification="pending",
) -> dict:
    """Shaped exactly like a real Architecture A row created before
    c7134c62 -- same field set real rows carry, fields renamed/parameterized
    only for isolation. Never touches the real repo CSV."""
    return {
        "date": date, "slot_id": slot_id, "platform": platform, "media_type": media_type,
        "growth_bucket": "", "lane": "rooftop sunset", "hook_category": "",
        "post_url": f"https://www.instagram.com/p/{slot_id}/", "audio_name": "",
        "reach": reach, "likes": likes, "saves": saves, "shares": shares, "comments": comments,
        "follows": follows, "profile_visits": profile_visits,
        "completion_rate": completion_rate, "replay_rate": replay_rate,
        "score": score, "classification": classification,
        "notes": (
            f"Auto-synced from Architecture A publish receipt "
            f"(C:\\fake\\queue\\published\\{slot_id}.json.receipt.json); "
            "update metrics after performance data is available. | "
            "auto_meta_metrics_refresh:2026-07-11"
        ),
        "post_id": slot_id, "instagram_media_id": f"ig-{slot_id}",
        "permalink": f"https://www.instagram.com/p/{slot_id}/",
        "source_slot_id": slot_id,
        "publish_receipt_path": f"C:\\fake\\queue\\published\\{slot_id}.json.receipt.json",
        "source_asset_path": "", "clean_derivative_path": "",
        "source_asset_sha256": "", "clean_export_derivative_sha256": "",
        "clean_export_verified": "false",
        "wardrobe_outfit_id": "wc_p006", "pose_body_language_id": "", "expression_gaze_id": "",
    }


def _six_row_fixture() -> list:
    """Mirrors the real repo's exact 6-row shape: 2 non-target historical
    rows (blank identity, never touched by this repair) + the 4 real
    proven-affected Architecture A target rows."""
    non_target_1 = {
        **_real_shaped_metric_row("2026-06-12", "2026-06-12-03-video", "TikTok", media_type="video"),
        "post_id": "", "instagram_media_id": "", "permalink": "", "source_slot_id": "",
        "publish_receipt_path": "", "notes": "Initial manual post log; update metrics after performance data is available.",
    }
    non_target_2 = {
        **_real_shaped_metric_row(
            "2026-06-24", "2026-06-24-01-photo", "Instagram Feed",
            completion_rate="0.0", replay_rate="0.0", score="0.0", classification="weak",
        ),
        "post_id": "", "instagram_media_id": "", "permalink": "", "source_slot_id": "",
        "publish_receipt_path": "",
        "notes": "Auto-synced from posted queue q_a13bb81ef320a7; update metrics after performance data is available. | auto_meta_metrics_refresh:2026-06-29",
    }
    targets = [_real_shaped_metric_row(date, slot_id, platform) for date, slot_id, platform in TARGET_KEYS]
    return [non_target_1, non_target_2] + targets


# 1/9. The repaired candidate rows satisfy row_has_unknown_scoring_inputs()
# is True, and only the four approved fields on the four target rows change.
def test_repair_blanks_only_legacy_placeholder_fields_on_target_rows() -> None:
    rows = _six_row_fixture()
    candidate_rows, cell_changes = build_repaired_candidate(rows)

    assert len(cell_changes) == 16
    changed_fields = {c["field"] for c in cell_changes}
    assert changed_fields == set(FIELDS_TO_BLANK)
    for change in cell_changes:
        assert change["old"] == "0"
        assert change["new"] == ""
        assert tuple(change["key"]) in TARGET_KEYS

    postcondition_report = verify_postconditions(rows, candidate_rows)
    assert postcondition_report["ok"] is True
    assert postcondition_report["total_changed_cells"] == 16

    candidate_by_key = {(r["date"], r["slot_id"], r["platform"]): r for r in candidate_rows}
    for key in TARGET_KEYS:
        repaired_row = candidate_by_key[key]
        for field in FIELDS_TO_BLANK:
            assert repaired_row[field] == ""
        assert row_has_unknown_scoring_inputs(repaired_row) is True


# 6. Confirmed real-zero fields (reach/likes/saves/shares/comments) and
# score/classification are untouched by the repair.
def test_repair_leaves_confirmed_real_fields_untouched() -> None:
    rows = _six_row_fixture()
    candidate_rows, _ = build_repaired_candidate(rows)
    candidate_by_key = {(r["date"], r["slot_id"], r["platform"]): r for r in candidate_rows}
    original_by_key = {(r["date"], r["slot_id"], r["platform"]): r for r in rows}
    for key in TARGET_KEYS:
        for field in ("reach", "likes", "saves", "shares", "comments", "score", "classification", "notes"):
            assert candidate_by_key[key][field] == original_by_key[key][field]


# 7. An unrelated non-target row (byte-identical, including one that also
# happens to carry "0" in the same four fields) remains fully untouched.
def test_repair_leaves_unrelated_non_target_row_byte_identical() -> None:
    rows = _six_row_fixture()
    candidate_rows, _ = build_repaired_candidate(rows)
    non_target_keys = [
        ("2026-06-12", "2026-06-12-03-video", "TikTok"),
        ("2026-06-24", "2026-06-24-01-photo", "Instagram Feed"),
    ]
    candidate_by_key = {(r["date"], r["slot_id"], r["platform"]): r for r in candidate_rows}
    original_by_key = {(r["date"], r["slot_id"], r["platform"]): r for r in rows}
    for key in non_target_keys:
        assert candidate_by_key[key] == original_by_key[key]


# 8. Unexpected existing values fail closed -- verify_postconditions()
# rejects a candidate that touched a field/row it shouldn't have.
def test_verify_postconditions_fails_closed_on_unapproved_change() -> None:
    rows = _six_row_fixture()
    candidate_rows, _ = build_repaired_candidate(rows)
    # Tamper with the candidate: touch an unapproved field on a target row.
    for row in candidate_rows:
        if (row["date"], row["slot_id"], row["platform"]) == TARGET_KEYS[0]:
            row["reach"] = "999"
    with pytest.raises(PreconditionError):
        verify_postconditions(rows, candidate_rows)


def test_verify_postconditions_fails_closed_on_non_target_row_touched() -> None:
    rows = _six_row_fixture()
    candidate_rows, _ = build_repaired_candidate(rows)
    candidate_rows[0]["follows"] = ""  # non-target row incorrectly touched
    with pytest.raises(PreconditionError):
        verify_postconditions(rows, candidate_rows)


# 5/8. Wrong hash / wrong row shape fail closed at the precondition
# boundary -- exercised against isolated tmp_path files, never the real
# repo CSV.
def test_verify_preconditions_fails_closed_on_wrong_csv_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metrics_path = tmp_path / "lena_post_metrics_v1_6_1.csv"
    sync_mod.write_csv(metrics_path, _six_row_fixture())
    monkeypatch.setattr(repair_mod, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(repair_mod, "_current_git_head", lambda: repair_mod.EXPECTED_HEAD)

    with pytest.raises(PreconditionError, match="sha256"):
        verify_preconditions()


def test_verify_preconditions_fails_closed_on_missing_target_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metrics_path = tmp_path / "lena_post_metrics_v1_6_1.csv"
    rows = _six_row_fixture()
    # Wrong row shape: drop one of the four target rows entirely.
    rows = [r for r in rows if (r["date"], r["slot_id"], r["platform"]) != TARGET_KEYS[0]]
    sync_mod.write_csv(metrics_path, rows)
    monkeypatch.setattr(repair_mod, "METRICS_PATH", metrics_path)
    monkeypatch.setattr(repair_mod, "_current_git_head", lambda: repair_mod.EXPECTED_HEAD)
    monkeypatch.setattr(
        repair_mod, "_sha256_of",
        lambda path: repair_mod.EXPECTED_CSV_SHA256 if path == metrics_path else repair_mod._sha256_of(path),
    )

    with pytest.raises(PreconditionError):
        verify_preconditions()


def test_verify_preconditions_fails_closed_on_wrong_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repair_mod, "_current_git_head", lambda: "deadbeef")
    with pytest.raises(PreconditionError, match="git_head"):
        verify_preconditions()
