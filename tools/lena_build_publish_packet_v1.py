from __future__ import annotations

# Lena publish-packet builder -- Batch 1 (read-only resolver + hard-fail checks).
#
# Design doc: pipeline/agents/lena/90_content_packet/{AGENT,RULES,INPUTS,OUTPUTS}.md.
# This is Batch 1 only, per that folder's RULES.md and the approved scoping pass:
# resolve a slot's real artifacts (workorder, rendered image, QA verdict, optional
# debug/result manifest) and hard-fail cleanly if anything required is missing or
# not QA-passed. It creates NO output files -- no publish packet, no queue draft,
# nothing under pipeline/publish_packets/ or pipeline/queue/. Packet writing is a
# separate, later, explicitly-approved batch.
#
# Deliberately does NOT reuse tools/lena_review_proof_render_v1.py's
# build_review_bundle(), because that function calls
# pipeline.qa.lena_photo_qa.save_qa_template(), which WRITES an "unreviewed" QA
# scaffold file to disk if one doesn't already exist for the slot (save_qa_template()
# only skips writing when the path already exists -- force=False is not "never
# writes", it's "never overwrites"). That side effect is correct for a *review*
# helper (whose job is to scaffold QA files for a reviewer to fill in) but wrong for
# a *packet builder* that must hard-fail cleanly, with zero filesystem writes, when a
# slot has no QA verdict yet. This module re-implements the read-only parts of that
# lookup (workorder/slot resolution, image-path resolution) itself and uses only
# pipeline.qa.lena_photo_qa.load_qa_result() (pure read, returns None if missing) and
# validate_qa_result() (pure function, no I/O) -- never save_qa_template().
#
# Read-only. Never imports pipeline.env_loader (does not read .env). Never imports
# pipeline.posting_manager, tools.process_queue, pipeline.kling_apilena_api_executor,
# requests, or urllib -- this module cannot publish, queue, or call any network/API
# surface, by construction, not just by convention.

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.qa import lena_photo_qa  # noqa: E402

WORKORDER_ROOT = ROOT / "pipeline" / "kling_workorders"
APILENA_DEBUG_ROOT = ROOT / "pipeline" / "kling_debug" / "apilena_api"
PUBLISH_PACKET_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"


class ResolveError(Exception):
    """Raised for any hard-fail condition in slot/QA resolution. Never caught
    silently -- main() reports it and exits non-zero. No file is ever written
    before or after this is raised."""


def _load_daily_manifest(date_str: str) -> Dict[str, Any]:
    path = WORKORDER_ROOT / date_str / "daily_workorders.json"
    if not path.exists():
        raise ResolveError(f"no daily_workorders.json for {date_str}: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ResolveError(f"failed to parse {path}: {exc}") from exc


def _resolve_slot(manifest: Dict[str, Any], slot_id: str) -> Dict[str, Any]:
    slots = manifest.get("slots") if isinstance(manifest.get("slots"), list) else []
    for slot in slots:
        if isinstance(slot, dict) and slot.get("slot_id") == slot_id:
            return slot
    raise ResolveError(f"slot_id '{slot_id}' not found in this date's daily_workorders.json")


def _resolve_image_path(slot: Dict[str, Any]) -> Path:
    expected_assets = slot.get("expected_assets") if isinstance(slot.get("expected_assets"), dict) else {}
    raw = expected_assets.get("seed_image_path") or expected_assets.get("final_photo_path")
    if not raw:
        raise ResolveError("slot has no expected_assets.seed_image_path or final_photo_path")
    image_path = Path(str(raw))
    if not image_path.exists():
        raise ResolveError(f"rendered image does not exist on disk: {image_path}")
    return image_path


def _resolve_qa(date_str: str, slot_id: str) -> Dict[str, Any]:
    qa_path = lena_photo_qa.qa_artifact_path(date_str, slot_id)
    if not qa_path.exists():
        raise ResolveError(
            f"no QA verdict exists for this slot: {qa_path} -- "
            "cannot build a packet ahead of QA (90_content_packet/RULES.md Rule zero)"
        )
    qa_result = lena_photo_qa.load_qa_result(date_str, slot_id)
    if not isinstance(qa_result, dict):
        raise ResolveError(f"QA file exists but failed to load/parse: {qa_path}")

    ok, errors = lena_photo_qa.validate_qa_result(qa_result)
    if not ok:
        raise ResolveError(
            f"QA verdict at {qa_path} is internally inconsistent (false-green guard): "
            + "; ".join(errors)
        )

    overall = qa_result.get("overall")
    if overall != "pass":
        raise ResolveError(
            f"QA verdict overall='{overall}' (not 'pass') at {qa_path} -- "
            "cannot build a packet for a non-passing render (90_content_packet/RULES.md Rule zero)"
        )

    return qa_result


def _resolve_optional_debug_artifacts(date_str: str, slot_id: str) -> Dict[str, Any]:
    debug_dir = APILENA_DEBUG_ROOT / date_str / slot_id
    result_manifest_path = debug_dir / "result_manifest.json"
    prompt_receipt_path = debug_dir / "prompt_receipt.json"

    result_manifest_task_id: Optional[str] = None
    if result_manifest_path.exists():
        try:
            manifest = json.loads(result_manifest_path.read_text(encoding="utf-8-sig"))
            if isinstance(manifest, dict):
                result_manifest_task_id = manifest.get("task_id") or manifest.get("id")
        except Exception:
            result_manifest_task_id = None

    return {
        "result_manifest_path": str(result_manifest_path),
        "result_manifest_exists": result_manifest_path.exists(),
        "result_manifest_task_id": result_manifest_task_id,
        "prompt_receipt_path": str(prompt_receipt_path),
        "prompt_receipt_exists": prompt_receipt_path.exists(),
    }


def resolve_packet_inputs(date_str: str, slot_id: str) -> Dict[str, Any]:
    """Read-only. Raises ResolveError on any hard-fail condition. Writes nothing,
    ever -- no QA scaffold, no packet, no queue draft."""
    manifest = _load_daily_manifest(date_str)
    slot = _resolve_slot(manifest, slot_id)
    image_path = _resolve_image_path(slot)
    qa_result = _resolve_qa(date_str, slot_id)
    debug_artifacts = _resolve_optional_debug_artifacts(date_str, slot_id)

    metadata = slot.get("metadata") if isinstance(slot.get("metadata"), dict) else {}
    intended_packet_path = PUBLISH_PACKET_ROOT / date_str / f"LENA_PUBLISH_PACKET_{slot_id}.md"

    return {
        "date": date_str,
        "slot_id": slot_id,
        "image_path": str(image_path),
        "qa_path": str(lena_photo_qa.qa_artifact_path(date_str, slot_id)),
        "qa_overall": qa_result.get("overall"),
        "qa_hook_strength": (qa_result.get("production_scoring") or {}).get("hook_strength", {}).get("score"),
        "qa_styling_sexy_platform_safe": (qa_result.get("production_scoring") or {})
        .get("styling_sexy_platform_safe", {})
        .get("status"),
        "workorder_caption": slot.get("caption"),
        "wardrobe_outfit_id": metadata.get("wardrobe_outfit_id"),
        "wardrobe_outfit_name": metadata.get("wardrobe_outfit_name"),
        "environment_id": metadata.get("environment_id"),
        "environment_name": metadata.get("environment_name"),
        "lane": metadata.get("lane"),
        "reference_binding_mode": metadata.get("reference_binding_mode"),
        "debug_artifacts": debug_artifacts,
        "intended_packet_output_path": str(intended_packet_path),
        "intended_packet_output_already_exists": intended_packet_path.exists(),
        "files_written_this_run": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Batch 1: read-only resolver for the future Lena publish-packet "
            "builder. Resolves and validates a slot's real artifacts. Writes "
            "nothing -- no packet, no queue draft, no QA scaffold."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact slot_id, e.g. 2026-07-07-03-photo")
    args = parser.parse_args()

    try:
        summary = resolve_packet_inputs(args.date, args.slot_id)
    except ResolveError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id}, indent=2))
        return 1

    print(json.dumps({"ok": True, "resolved": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
