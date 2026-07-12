from __future__ import annotations

import csv
from pathlib import Path

import tools.lena_meta_refresh_feedback_v1 as mod


CANONICAL_FIELDS_38 = [
    "date",
    "slot_id",
    "platform",
    "media_type",
    "growth_bucket",
    "lane",
    "hook_category",
    "post_url",
    "audio_name",
    "reach",
    "likes",
    "saves",
    "shares",
    "comments",
    "follows",
    "profile_visits",
    "completion_rate",
    "replay_rate",
    "score",
    "classification",
    "notes",
    "post_id",
    "instagram_media_id",
    "permalink",
    "source_slot_id",
    "publish_receipt_path",
    "source_asset_path",
    "clean_derivative_path",
    "source_asset_sha256",
    "clean_export_derivative_sha256",
    "clean_export_verified",
    "wardrobe_outfit_id",
    "pose_body_language_id",
    "expression_gaze_id",
    "publish_architecture",
    "published_timestamp",
    "qa_artifact_path",
    "approval_record_path",
]


def _write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def _canonical_row(slot_id: str, *, lane: str, post_url: str) -> dict:
    return {
        "date": "2026-07-09",
        "slot_id": slot_id,
        "platform": "Instagram Feed",
        "media_type": "photo",
        "growth_bucket": "",
        "lane": lane,
        "hook_category": "",
        "post_url": post_url,
        "audio_name": "",
        "reach": "0",
        "likes": "0",
        "saves": "0",
        "shares": "0",
        "comments": "0",
        "follows": "0",
        "profile_visits": "0",
        "completion_rate": "0",
        "replay_rate": "0",
        "score": "0",
        "classification": "pending",
        "notes": "pre-refresh",
        "post_id": slot_id,
        "instagram_media_id": f"ig-{slot_id}",
        "permalink": post_url,
        "source_slot_id": slot_id,
        "publish_receipt_path": f"C:\\receipts\\{slot_id}.json",
        "source_asset_path": f"C:\\assets\\{slot_id}.png",
        "clean_derivative_path": f"C:\\assets\\{slot_id}_clean.png",
        "source_asset_sha256": "a" * 64,
        "clean_export_derivative_sha256": "b" * 64,
        "clean_export_verified": "true",
        "wardrobe_outfit_id": "wc_p020",
        "pose_body_language_id": "pose_01",
        "expression_gaze_id": "expr_01",
        "publish_architecture": "architecture_a",
        "published_timestamp": "2026-07-09T12:00:00+0000",
        "qa_artifact_path": f"C:\\qa\\{slot_id}_qa.json",
        "approval_record_path": f"C:\\approvals\\{slot_id}_approval.json",
    }


def test_schema_preserving_round_trip_keeps_38_columns_and_order(tmp_path: Path) -> None:
    metrics_path = tmp_path / "lena_post_metrics_v1_6_1.csv"
    rows = [
        _canonical_row("slot-1", lane="rooftop sunset", post_url="https://example.com/p/1"),
        _canonical_row("slot-2", lane="sidewalk dinner", post_url="https://example.com/p/2"),
    ]
    _write_rows(metrics_path, CANONICAL_FIELDS_38, rows)

    existing_header = mod.read_csv_header(metrics_path)
    field_order = mod.stable_union_fields(existing_header, mod.METRIC_FIELDS)
    loaded = mod.read_csv(metrics_path)

    loaded[0]["reach"] = "2600"
    loaded[0]["likes"] = "81"
    loaded[0]["notes"] = "post-refresh"

    mod.write_csv(metrics_path, field_order, loaded)
    reloaded = mod.read_csv(metrics_path)

    assert len(_header(metrics_path)) == 38
    assert _header(metrics_path) == CANONICAL_FIELDS_38
    assert field_order == CANONICAL_FIELDS_38
    assert reloaded[0]["reach"] == "2600"
    assert reloaded[0]["likes"] == "81"
    assert reloaded[0]["notes"] == "post-refresh"
    assert reloaded[0]["post_id"] == "slot-1"
    assert reloaded[0]["instagram_media_id"] == "ig-slot-1"
    assert reloaded[0]["permalink"] == "https://example.com/p/1"
    assert reloaded[0]["source_slot_id"] == "slot-1"
    assert reloaded[0]["publish_receipt_path"] == "C:\\receipts\\slot-1.json"
    assert reloaded[0]["source_asset_path"] == "C:\\assets\\slot-1.png"
    assert reloaded[0]["clean_derivative_path"] == "C:\\assets\\slot-1_clean.png"
    assert reloaded[0]["source_asset_sha256"] == "a" * 64
    assert reloaded[0]["clean_export_derivative_sha256"] == "b" * 64
    assert reloaded[0]["clean_export_verified"] == "true"
    assert reloaded[0]["wardrobe_outfit_id"] == "wc_p020"
    assert reloaded[0]["pose_body_language_id"] == "pose_01"
    assert reloaded[0]["expression_gaze_id"] == "expr_01"
    assert reloaded[0]["publish_architecture"] == "architecture_a"
    assert reloaded[0]["published_timestamp"] == "2026-07-09T12:00:00+0000"
    assert reloaded[0]["qa_artifact_path"] == "C:\\qa\\slot-1_qa.json"
    assert reloaded[0]["approval_record_path"] == "C:\\approvals\\slot-1_approval.json"
    assert reloaded[1] == rows[1]


def test_schema_union_appends_missing_required_metric_fields_without_dropping_existing_order() -> None:
    existing = [
        "date",
        "slot_id",
        "platform",
        "post_id",
        "instagram_media_id",
        "permalink",
    ]

    fields = mod.stable_union_fields(existing, mod.METRIC_FIELDS)

    assert fields[: len(existing)] == existing
    assert len(fields) == len(set(existing + mod.METRIC_FIELDS))
    for field in mod.METRIC_FIELDS:
        assert field in fields

