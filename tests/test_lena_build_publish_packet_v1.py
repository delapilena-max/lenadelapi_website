"""Focused offline tests for the QA-disposition -> publish-packet bridge.

Proves the missing link in the unattended path:
  QA disposition (accept) -> publish packet -> safe_packet() accepts it
Fully offline: no provider calls, no network, no Instagram/Facebook calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.lena_build_publish_packet_v1 as bridge
import tools.lena_build_approved_publish_queue_v2_8 as queue_builder

DATE = "2026-07-24"
SLOT_ID = "lenagate20260724testcommit-pack000-00-photo"
RECIPE_ID = "hcr_012"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _disposition(disposition: str = "accept", *, slot_id: str = SLOT_ID) -> dict:
    return {
        "schema_version": "lena_photo_qa_disposition_v1",
        "influencer_id": "lena",
        "decision_artifact_path": "pipeline/strategy/lena/reconciliations/2026-07-24/fake.json",
        "candidate_id": "lenagate20260724testcommit-pack000-00-photo::hcr_012::mf_001",
        "slot_id": slot_id,
        "lane": "face_priority_getting_ready",
        "recipe_id": RECIPE_ID,
        "hook_id": "mf_001",
        "image_path": "",  # filled in by tests that need a real file
        "image_sha256": "a" * 64,
        "disposition": disposition,
        "reason_codes": [],
    }


def _content_packet(*, all_checks_passed: bool = True) -> dict:
    return {
        "report_type": "lena_content_packet_dryrun",
        "recipe_id": RECIPE_ID,
        "caption_draft": "was only checking the neckline.",
        "caption_followup": "I stood there for a minute. So did the mirror.",
        "suggested_comment_reply_angle": "The mirror and I are in a complicated relationship.",
        "strong_hook_category": "mirror_fitcheck",
        "safety_flags": {
            "all_checks_passed": all_checks_passed,
            "no_ai_terms_in_public": True,
            "no_nsfw_in_public": True,
            "no_hashtags_in_public": True,
        },
    }


def _patch_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "ROOT", tmp_path)
    monkeypatch.setattr(bridge, "ASSET_REVIEW_ROOT", tmp_path / "pipeline" / "asset_review" / "lena")
    monkeypatch.setattr(bridge, "PUBLISH_PACKETS_ROOT", tmp_path / "pipeline" / "publish_packets" / "lena")


def _write_disposition(tmp_path: Path, disposition: dict) -> Path:
    path = tmp_path / "pipeline" / "asset_review" / "lena" / DATE / f"{disposition['slot_id']}__aa_qa_disposition.json"
    _write_json(path, disposition)
    return path


def _write_content_packet(tmp_path: Path, packet: dict) -> Path:
    path = (
        tmp_path
        / "pipeline"
        / "strategy"
        / "lena"
        / "content_packets"
        / DATE
        / f"lena_content_packet_dryrun_{DATE}_{RECIPE_ID}.json"
    )
    _write_json(path, packet)
    return path


def _write_image(tmp_path: Path, slot_id: str = SLOT_ID) -> Path:
    path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{slot_id}_seed.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes")
    return path


def test_accept_disposition_with_clean_packet_is_bridged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition()
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    _write_content_packet(tmp_path, _content_packet())

    report = bridge.build_publish_packets(DATE)

    assert report["ok"] is True
    assert report["added_count"] == 1
    assert report["added_slot_ids"] == [SLOT_ID]
    assert report["skipped"] == []

    packets_path = tmp_path / "pipeline" / "publish_packets" / "lena" / DATE / "lena_publish_packets_v2_4.json"
    assert packets_path.is_file()
    saved = json.loads(packets_path.read_text(encoding="utf-8"))
    assert len(saved["packets"]) == 1
    packet = saved["packets"][0]
    assert packet["slot_id"] == SLOT_ID
    assert packet["asset_status"] == "approved"
    assert packet["asset_path"] == str(image_path)
    assert packet["caption"] == "was only checking the neckline."
    assert packet["public_text_score"] == {"score": 100, "decision": "APPROVED"}
    assert packet["public_action_locked"] is True
    assert packet["manual_approval_required"] is True
    assert packet["media_type"] == "photo"


@pytest.mark.parametrize("disposition_value", ["hard_stop", "retryable_failure"])
def test_non_accept_disposition_is_never_bridged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disposition_value: str
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition(disposition_value)
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    _write_content_packet(tmp_path, _content_packet())

    report = bridge.build_publish_packets(DATE)

    assert report["added_count"] == 0
    assert report["skipped"] == [{"slot_id": SLOT_ID, "reason": f"disposition={disposition_value}"}]
    packets_path = tmp_path / "pipeline" / "publish_packets" / "lena" / DATE / "lena_publish_packets_v2_4.json"
    assert not packets_path.is_file()


def test_unclean_content_packet_is_not_bridged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition()
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    _write_content_packet(tmp_path, _content_packet(all_checks_passed=False))

    report = bridge.build_publish_packets(DATE)

    assert report["added_count"] == 0
    assert report["skipped"][0]["slot_id"] == SLOT_ID
    assert "content_packet_safety_flags_not_clean" in report["skipped"][0]["reason"]


def test_missing_content_packet_is_skipped_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition()
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    # No content packet written.

    report = bridge.build_publish_packets(DATE)

    assert report["ok"] is True
    assert report["added_count"] == 0
    assert "content_packet_missing" in report["skipped"][0]["reason"]


def test_missing_generated_image_is_skipped_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    disp = _disposition()
    disp["image_path"] = str(tmp_path / "does_not_exist_seed.png")
    _write_disposition(tmp_path, disp)
    _write_content_packet(tmp_path, _content_packet())

    report = bridge.build_publish_packets(DATE)

    assert report["added_count"] == 0
    assert "generated_image_missing" in report["skipped"][0]["reason"]


def test_rerunning_the_same_date_never_duplicates_a_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition()
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    _write_content_packet(tmp_path, _content_packet())

    first = bridge.build_publish_packets(DATE)
    second = bridge.build_publish_packets(DATE)

    assert first["added_count"] == 1
    assert second["added_count"] == 0
    assert second["skipped"] == [{"slot_id": SLOT_ID, "reason": "already_bridged"}]
    packets_path = tmp_path / "pipeline" / "publish_packets" / "lena" / DATE / "lena_publish_packets_v2_4.json"
    saved = json.loads(packets_path.read_text(encoding="utf-8"))
    assert len(saved["packets"]) == 1


def test_two_accepted_dispositions_both_bridge_independently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_a = _write_image(tmp_path, slot_id="slot-a")
    image_b = _write_image(tmp_path, slot_id="slot-b")
    disp_a = _disposition(slot_id="slot-a")
    disp_a["image_path"] = str(image_a)
    disp_b = _disposition(slot_id="slot-b")
    disp_b["image_path"] = str(image_b)
    _write_disposition(tmp_path, disp_a)
    _write_disposition(tmp_path, disp_b)
    _write_content_packet(tmp_path, _content_packet())

    report = bridge.build_publish_packets(DATE)

    assert report["added_count"] == 2
    assert set(report["added_slot_ids"]) == {"slot-a", "slot-b"}


# --------------------------------------------------------------------------
# Integration: bridged packet must satisfy the EXISTING, already-tested
# queue builder's own acceptance gate -- proves the schemas actually match,
# not just that the bridge believes they do.
# --------------------------------------------------------------------------

def test_bridged_packet_satisfies_the_existing_queue_builder_safe_packet_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition()
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    _write_content_packet(tmp_path, _content_packet())
    bridge.build_publish_packets(DATE)

    packets_path = tmp_path / "pipeline" / "publish_packets" / "lena" / DATE / "lena_publish_packets_v2_4.json"
    saved = json.loads(packets_path.read_text(encoding="utf-8"))
    packet = saved["packets"][0]

    policy = {
        "require_asset_status": "approved",
        "minimum_public_text_score": 85,
        "require_asset_file_exists": True,
        "require_public_action_locked": True,
        "require_manual_approval_required": True,
    }
    ok, reasons = queue_builder.safe_packet(packet, policy)
    assert ok is True, reasons


def test_rejected_text_packet_is_refused_by_the_existing_queue_builder_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    image_path = _write_image(tmp_path)
    disp = _disposition()
    disp["image_path"] = str(image_path)
    _write_disposition(tmp_path, disp)
    unclean_but_still_all_checks = _content_packet()
    unclean_but_still_all_checks["safety_flags"]["no_ai_terms_in_public"] = False
    _write_content_packet(tmp_path, unclean_but_still_all_checks)
    bridge.build_publish_packets(DATE)

    packets_path = tmp_path / "pipeline" / "publish_packets" / "lena" / DATE / "lena_publish_packets_v2_4.json"
    saved = json.loads(packets_path.read_text(encoding="utf-8"))
    packet = saved["packets"][0]
    assert packet["public_text_score"]["decision"] == "REJECTED"

    policy = {
        "require_asset_status": "approved",
        "minimum_public_text_score": 85,
        "require_asset_file_exists": True,
        "require_public_action_locked": True,
        "require_manual_approval_required": True,
    }
    ok, reasons = queue_builder.safe_packet(packet, policy)
    assert ok is False
    assert "public_text_not_approved" in reasons
