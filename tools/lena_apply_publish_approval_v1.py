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
    MAX_HASHTAGS_PER_CAPTION,
    REQUIRED_CONFIRM_PHRASE,
    _count_hashtags,
    resolve_approval_output_path,
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
    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)
    approval = _load_json_object(approval_path, "approval artifact")

    if approval.get("post_id") != slot_id:
        raise ApplyApprovalError(
            f"approval post_id {approval.get('post_id')!r} does not match requested slot {slot_id!r}"
        )
    if approval.get("source_date") != date_str:
        raise ApplyApprovalError(
            f"approval source_date {approval.get('source_date')!r} does not match requested date {date_str!r}"
        )

    approved_caption = approval.get("approved_caption")
    if not approved_caption or not str(approved_caption).strip():
        raise ApplyApprovalError("approval's approved_caption is missing or empty")

    actual_hashtag_count = _count_hashtags(approved_caption)
    stored_hashtag_count = approval.get("hashtag_count")
    if actual_hashtag_count != stored_hashtag_count:
        raise ApplyApprovalError(
            f"approval hashtag_count {stored_hashtag_count!r} does not match the actual "
            f"hashtag count ({actual_hashtag_count}) found in approved_caption"
        )
    if not (1 <= actual_hashtag_count <= MAX_HASHTAGS_PER_CAPTION):
        raise ApplyApprovalError(
            f"hashtag count {actual_hashtag_count} is not between 1 and {MAX_HASHTAGS_PER_CAPTION} inclusive"
        )

    approved_by = approval.get("approved_by")
    if not approved_by or not str(approved_by).strip():
        raise ApplyApprovalError("approval's approved_by is missing or empty")

    approval_statement = approval.get("approval_statement")
    if approval_statement != REQUIRED_CONFIRM_PHRASE:
        raise ApplyApprovalError(
            f"approval_statement {approval_statement!r} does not exactly match "
            f"the required phrase {REQUIRED_CONFIRM_PHRASE!r}"
        )

    # manual_one_off_confirmed is part of the established schema (see the
    # one real precedent, 2026-07-05-01-photo_approval.json) -- only
    # enforced if present, since it's not one of this checker's own
    # required inputs; absence would be a schema question for the recorder,
    # not something this consumer should silently paper over either way.
    if "manual_one_off_confirmed" in approval and approval.get("manual_one_off_confirmed") is not True:
        raise ApplyApprovalError("approval's manual_one_off_confirmed is present but not true")

    if approval.get("promotion_status") != "not_yet_promoted":
        raise ApplyApprovalError(
            f"approval promotion_status {approval.get('promotion_status')!r} is not "
            "'not_yet_promoted' -- refusing to apply a caption for an item that may "
            "already have been promoted or published"
        )

    queue_draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
    queue_draft = _load_json_object(queue_draft_path, "queue draft")

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

    fields_that_would_change: List[str] = [] if already_applied else ["caption"]

    return {
        "date": date_str,
        "slot_id": slot_id,
        "approval_path": str(approval_path),
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
