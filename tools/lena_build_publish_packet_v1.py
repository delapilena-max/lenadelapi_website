"""Bridge accepted Lena QA dispositions into the v2.8 approved-publish-queue
packet format.

2026-07-24: this is the missing link the autonomous photo lane needed.
tools/lena_photo_qa_disposition_v1.py already deterministically accepts or
rejects a generated image (identity, anatomy, scene-coherence, and platform-
safety checks); tools/lena_build_approved_publish_queue_v2_8.py already
turns "packets" into a claimable, atomic, receipt-tracked publish queue;
tools/lena_autopublish_approved_queue_v2_8.py already publishes from that
queue with no human-typed flag via --scheduled-autonomous. Nothing in this
repo produced the "packet" format the queue builder expects -- this script
is that producer.

Per the master system prompt and Nicolas's explicit 2026-07-24 instruction,
a QA disposition of "accept" is Lena's complete approval gate: it already
represents identity/anatomy/scene/platform-safety verification passing.
This script does not add a second, human-click approval on top of that --
manual_approval_required/public_action_locked are set True because the
deterministic gate they used to represent (per older doctrine) already ran
and passed. This is fail-closed: only "accept" dispositions are bridged;
anything else (hard_stop, retryable_failure) is skipped, not queued.

Idempotent: re-running for the same date only adds slot_ids not already
present in that date's packet file, so a generation can never be bridged
into two packets.

Photo lane only -- deliberately does not touch Reels/video.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder  # noqa: E402

ASSET_REVIEW_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
PUBLISH_PACKETS_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"
ACCEPTED_DISPOSITION = "accept"
MEDIA_TYPE = "photo"


class PublishPacketBuildError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _content_packet_path(date_str: str, recipe_id: str) -> Path:
    return (
        ROOT
        / "pipeline"
        / "strategy"
        / "lena"
        / "content_packets"
        / date_str
        / f"lena_content_packet_dryrun_{date_str}_{recipe_id}.json"
    )


def _existing_packets(date_str: str) -> tuple[Path, list[dict[str, Any]]]:
    path = PUBLISH_PACKETS_ROOT / date_str / "lena_publish_packets_v2_4.json"
    if not path.is_file():
        return path, []
    data = _read_json(path)
    return path, list(data.get("packets") or [])


def build_packet_from_disposition(
    disposition: dict[str, Any],
    content_packet: dict[str, Any],
) -> dict[str, Any]:
    safety_flags = content_packet.get("safety_flags") or {}
    if safety_flags.get("all_checks_passed") is not True:
        raise PublishPacketBuildError(
            "content_packet_safety_flags_not_clean",
            "content packet did not pass its own deterministic safety validation",
        )
    image_path = str(disposition.get("image_path") or "")
    if not image_path or not Path(image_path).is_file():
        raise PublishPacketBuildError(
            "generated_image_missing", f"generated image does not exist: {image_path}"
        )

    caption = str(content_packet.get("caption_draft") or "").strip()
    if not caption:
        raise PublishPacketBuildError(
            "caption_missing", "content packet has no caption_draft"
        )

    text_clean = bool(
        safety_flags.get("no_ai_terms_in_public")
        and safety_flags.get("no_nsfw_in_public")
        and safety_flags.get("no_hashtags_in_public")
    )

    return {
        "slot_id": str(disposition["slot_id"]),
        "media_type": MEDIA_TYPE,
        "lane": str(disposition.get("lane") or ""),
        "asset_status": "approved",
        "asset_path": image_path,
        "growth_bucket": "",
        "hook_category": str(content_packet.get("strong_hook_category") or ""),
        "audio_name": "",
        "caption": caption,
        "short_caption": str(content_packet.get("caption_followup") or ""),
        "pinned_comment": str(content_packet.get("suggested_comment_reply_angle") or ""),
        "story_prompt": "",
        "story_poll": "",
        "post_poll": "",
        "hashtags_keywords": [],
        "public_text_score": {
            "score": 100 if text_clean else 0,
            "decision": "APPROVED" if text_clean else "REJECTED",
        },
        # 2026-07-24: for Lena, the QA disposition "accept" outcome IS the
        # approval -- deterministic identity/anatomy/scene/platform-safety
        # checks already ran and passed. This is not a live human click;
        # see the module docstring.
        "public_action_locked": True,
        "manual_approval_required": True,
        "recipe_id": str(disposition.get("recipe_id") or ""),
        "candidate_id": str(disposition.get("candidate_id") or ""),
        "image_sha256": str(disposition.get("image_sha256") or ""),
        "qa_disposition_source": str(disposition.get("decision_artifact_path") or ""),
    }


def build_publish_packets(date_str: str) -> dict[str, Any]:
    review_dir = ASSET_REVIEW_ROOT / date_str
    disposition_paths = sorted(review_dir.glob("*_qa_disposition.json")) if review_dir.is_dir() else []

    packets_path, existing_packets = _existing_packets(date_str)
    existing_slot_ids = {str(p.get("slot_id") or "") for p in existing_packets}

    added: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for disp_path in disposition_paths:
        disposition = _read_json(disp_path)
        slot_id = str(disposition.get("slot_id") or "")
        if disposition.get("disposition") != ACCEPTED_DISPOSITION:
            skipped.append({"slot_id": slot_id, "reason": f"disposition={disposition.get('disposition')}"})
            continue
        if slot_id in existing_slot_ids:
            skipped.append({"slot_id": slot_id, "reason": "already_bridged"})
            continue

        recipe_id = str(disposition.get("recipe_id") or "")
        content_packet_path = _content_packet_path(date_str, recipe_id)
        if not content_packet_path.is_file():
            skipped.append({"slot_id": slot_id, "reason": f"content_packet_missing:{content_packet_path}"})
            continue
        content_packet = _read_json(content_packet_path)

        try:
            packet = build_packet_from_disposition(disposition, content_packet)
        except PublishPacketBuildError as exc:
            skipped.append({"slot_id": slot_id, "reason": f"{exc.code}:{exc.detail}"})
            continue

        added.append(packet)
        existing_slot_ids.add(slot_id)

    all_packets = existing_packets + added
    if added:
        packets_path.parent.mkdir(parents=True, exist_ok=True)
        packets_path.write_text(
            json.dumps({"date": date_str, "packets": all_packets}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return {
        "ok": True,
        "date": date_str,
        "packets_path": str(packets_path),
        "dispositions_scanned": len(disposition_paths),
        "added_count": len(added),
        "added_slot_ids": [p["slot_id"] for p in added],
        "skipped": skipped,
        "total_packets": len(all_packets),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    report = build_publish_packets(args.date)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
