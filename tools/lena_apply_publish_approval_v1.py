from __future__ import annotations

# Lena approval-application step -- the smallest explicit, fail-closed
# consumer of an already-recorded publish-approval artifact
# (tools/lena_record_publish_approval_v1.py's output).
#
# The human approval already happened (recorded, immutably, by
# lena_record_publish_approval_v1.py --record). This tool automates only
# the clerical step of copying that already-approved caption into the
# existing queue draft's top-level "caption" field -- nothing else.
#
# Deliberately separate from lena_record_publish_approval_v1.py: that
# module's own docstring states it "never edits the queue draft it reads."
# This tool exists precisely to do the one edit that module refuses to do,
# so that invariant stays true and unweakened there.
#
# Never writes into pipeline/queue/. Never sets approved_for_live_publish
# to anything other than false (it never touches that field at all). Never
# imports pipeline.posting_manager, tools.process_queue,
# pipeline.higgsfield_lena_api_executor, pipeline.kling_apilena_api_executor,
# any publisher/API module, requests, urllib, or pipeline.env_loader -- this
# module cannot publish, queue, generate, or call any network/API surface,
# by construction, not just by convention.
#
# The ONLY permitted mutation, ever, is the queue draft's top-level
# "caption" key. Every other field (post_id, slot_id, media_path,
# media_type, platforms, approved_for_live_publish, operator_review_required,
# metadata and everything inside it) is read back byte-identical from the
# parsed JSON and never touched.
#
# Idempotent: if the queue draft's caption already exactly equals the
# approved caption, this reports success and writes nothing. If a
# different, non-placeholder caption is already present, this fails closed
# -- it never overwrites an unknown caption.
#
# Defaults to dry-run (prints what would change, writes nothing); only
# --apply performs the one write.
#
# Run (dry-run, writes nothing):
#   python tools/lena_apply_publish_approval_v1.py --date 2026-07-09 --slot readypack0709-pack003-08-photo
# Run (applies the one caption write):
#   python tools/lena_apply_publish_approval_v1.py --date 2026-07-09 --slot readypack0709-pack003-08-photo --apply

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_build_publish_packet_v1 import (  # noqa: E402
    QUEUE_DRAFT_CAPTION_PLACEHOLDER,
    resolve_queue_draft_output_path,
)
from tools.lena_record_publish_approval_v1 import (  # noqa: E402
    resolve_approval_output_path,
)
from tools.lena_human_rejection_gate_v1 import (  # noqa: E402
    HumanRejectionGateError,
    assert_no_matching_human_rejection,
)
from tools.lena_publish_approval_binding_v1 import (  # noqa: E402
    resolve_approval_execution_bindings,
)


class ApplyApprovalError(Exception):
    """Raised for any hard-fail condition. Never caught silently -- main()
    reports it and exits non-zero. No file is ever written when this is
    raised."""


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    if not path.exists():
        raise ApplyApprovalError(f"{label} does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ApplyApprovalError(f"{label} failed to parse: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ApplyApprovalError(f"{label} did not contain a JSON object: {path}")
    return data


def check_apply_publish_approval(
    date_str: str,
    slot_id: str,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only. Raises ApplyApprovalError on any hard-fail condition.
    Writes nothing, ever. Returns a dict describing exactly what would
    change (empty list if the approval is already applied)."""
    approval_facts = resolve_approval_execution_bindings(
        date_str,
        slot_id,
        out_dir,
        require_live_publish_authorization=False,
        allow_caption_applied_queue_draft=False,
        error_cls=ApplyApprovalError,
    )
    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)
    approved_caption = approval_facts["approved_caption"]
    actual_hashtag_count = approval_facts["hashtag_count"]
    approved_by = approval_facts["approved_by"]

    queue_draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
    queue_draft = _load_json_object(queue_draft_path, "queue draft")

    approval_queue_draft_path = approval_facts["queue_draft_path"]
    if approval_queue_draft_path != str(queue_draft_path):
        raise ApplyApprovalError(
            f"approval queue_draft_path {approval_queue_draft_path!r} does not match the exact queue draft path "
            f"{str(queue_draft_path)!r}"
        )
    approval_publish_packet_path = approval_facts["publish_packet_path"]

    if queue_draft.get("slot_id") != slot_id:
        raise ApplyApprovalError(
            f"queue draft slot_id {queue_draft.get('slot_id')!r} does not match requested slot {slot_id!r}"
        )

    metadata = queue_draft.get("metadata") if isinstance(queue_draft.get("metadata"), dict) else None
    if metadata is None or metadata.get("queue_draft_only") is not True:
        raise ApplyApprovalError(
            "queue draft is missing metadata.queue_draft_only:true -- refusing to treat "
            "an unrecognized file as a real queue draft"
        )

    if queue_draft.get("approved_for_live_publish") is not False:
        raise ApplyApprovalError(
            f"queue draft approved_for_live_publish is {queue_draft.get('approved_for_live_publish')!r}, "
            "expected false -- refusing to touch an item that may already be live-approved"
        )

    current_caption = queue_draft.get("caption")
    already_applied = current_caption == approved_caption
    if not already_applied and current_caption != QUEUE_DRAFT_CAPTION_PLACEHOLDER:
        raise ApplyApprovalError(
            "queue draft caption is neither the placeholder nor the exact approved caption -- "
            "a different, non-placeholder caption is already present; refusing to overwrite it"
        )

    draft_publish_packet_path = metadata.get("publish_packet_path")
    if draft_publish_packet_path != approval_publish_packet_path:
        raise ApplyApprovalError(
            f"queue draft metadata.publish_packet_path {draft_publish_packet_path!r} does not match the approval's "
            f"publish_packet_path {approval_publish_packet_path!r}"
        )
    qa_path = metadata.get("qa_path")
    if not isinstance(qa_path, str) or not qa_path:
        raise ApplyApprovalError("queue draft metadata.qa_path is missing or empty")
    media_type = str(queue_draft.get("media_type") or "").lower().strip()
    image_path = Path(str(queue_draft["media_path"])) if media_type in {"photo", "image"} else None
    try:
        assert_no_matching_human_rejection(
            date_str=date_str,
            slot_id=slot_id,
            image_path=image_path,
            publish_packet_path=Path(approval_publish_packet_path),
            queue_draft_path=queue_draft_path,
            qa_path=Path(qa_path),
        )
    except HumanRejectionGateError as exc:
        raise ApplyApprovalError(str(exc)) from exc

    fields_that_would_change: List[str] = [] if already_applied else ["caption"]

    return {
        "date": date_str,
        "slot_id": slot_id,
        "approval_path": str(approval_path),
        "approval_sha256": approval_facts["approval_sha256"],
        "approval_binding_source": approval_facts["approval_binding_source"],
        "approval_correction_artifact_path": approval_facts["approval_correction_artifact_path"],
        "approval_correction_artifact_sha256": approval_facts["approval_correction_artifact_sha256"],
        "queue_draft_path": str(queue_draft_path),
        "approved_caption": approved_caption,
        "hashtag_count": actual_hashtag_count,
        "approved_by": approved_by,
        "already_applied": already_applied,
        "would_write": not already_applied,
        "fields_that_would_change": fields_that_would_change,
        "_queue_draft": queue_draft,
    }


def apply_publish_approval(checked: Dict[str, Any]) -> Optional[Path]:
    """Writes ONLY the queue draft's top-level 'caption' field, in place --
    every other key is read back byte-identical from the already-parsed
    JSON and re-serialized unchanged. Returns the path written, or None if
    the approval was already applied (idempotent no-op, zero writes)."""
    if checked["already_applied"]:
        return None
    queue_draft_path = Path(checked["queue_draft_path"])
    queue_draft = dict(checked["_queue_draft"])
    queue_draft["caption"] = checked["approved_caption"]
    queue_draft_path.write_text(
        json.dumps(queue_draft, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return queue_draft_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Applies an already-recorded Lena publish-approval caption into the "
            "matching queue draft's top-level 'caption' field -- the one clerical "
            "step lena_record_publish_approval_v1.py deliberately never performs. "
            "Defaults to dry-run (writes nothing); --apply performs the one write. "
            "Never touches pipeline/queue/, never sets approved_for_live_publish, "
            "never calls any provider/publish/API surface."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact slot_id, e.g. readypack0709-pack003-08-photo")
    parser.add_argument("--out-dir", default=None, help="Override the packet/queue-draft/approval output base directory.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the approved caption into the queue draft. Without this flag, only a dry-run summary is printed.",
    )
    args = parser.parse_args()

    out_dir: Optional[Path] = None
    if args.out_dir:
        candidate = Path(args.out_dir)
        out_dir = candidate if candidate.is_absolute() else (ROOT / candidate)

    try:
        checked = check_apply_publish_approval(args.date, args.slot_id, out_dir)
    except ApplyApprovalError as exc:
        print(json.dumps(
            {"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id, "files_written_this_run": []},
            indent=2,
        ))
        return 1

    report = {k: v for k, v in checked.items() if not k.startswith("_")}

    if not args.apply:
        print(json.dumps({"ok": True, "dry_run": True, "checked": report}, indent=2))
        return 0

    written_path = apply_publish_approval(checked)
    files_written = [str(written_path)] if written_path else []
    print(json.dumps({"ok": True, "dry_run": False, "checked": report, "files_written_this_run": files_written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
