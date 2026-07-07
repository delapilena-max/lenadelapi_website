from __future__ import annotations

# Lena publish-approval checker -- Batch 1 (read-only checker, no writes).
#
# Design doc: pipeline/agents/lena/95_publish_gate/{AGENT,RULES,INPUTS,OUTPUTS}.md.
# This is Batch 1 only, per that folder's RULES.md and the approved scoping pass:
# resolve a slot's real packet/queue-draft/QA artifacts, run every hard-fail check
# from RULES.md, and print a JSON dry-run summary of the approval record that WOULD
# be written later. This batch writes nothing -- no approval artifact, no queue
# draft edit, no queue-directory write. --record and --force are NOT implemented in
# this batch (see RULES.md "Human approval required" -- writing the actual approval
# artifact is a separate, later, explicitly-approved step).
#
# Never writes into pipeline/queue/, never moves or copies anything there, never
# edits the queue draft it reads. Never imports pipeline.posting_manager,
# tools.process_queue, pipeline.kling_apilena_api_executor, any publisher/API
# module, requests, urllib, or pipeline.env_loader -- this module cannot publish,
# queue, or call any network/API surface, by construction, not just by convention.
#
# Reuses (imports, does not duplicate) tools.lena_build_publish_packet_v1's
# resolve_packet_inputs(), resolve_packet_output_path(),
# resolve_queue_draft_output_path(), QUEUE_DRAFT_CAPTION_PLACEHOLDER, and
# LIVE_QUEUE_ROOT -- so the placeholder string and the live-queue guard can never
# silently drift out of sync between the two tools.

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_build_publish_packet_v1 import (  # noqa: E402
    LIVE_QUEUE_ROOT,
    QUEUE_DRAFT_CAPTION_PLACEHOLDER,
    ResolveError,
    resolve_packet_inputs,
    resolve_packet_output_path,
    resolve_queue_draft_output_path,
)

DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"
MAX_HASHTAGS_PER_CAPTION = 3
REQUIRED_CONFIRM_PHRASE = "I approve this for live publish"


class ApprovalCheckError(Exception):
    """Raised for any hard-fail condition in approval-record resolution/
    validation. Never caught silently -- main() reports it and exits
    non-zero. Batch 1 never writes any file, on success or failure."""


def resolve_approval_output_path(date_str: str, slot_id: str, out_dir: Optional[Path] = None) -> Path:
    base = out_dir if out_dir is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_approval.json"


def _assert_not_inside_live_queue(path: Path) -> None:
    """Same guard concept as tools.lena_build_publish_packet_v1's own --
    duplicated as a standalone function here (rather than imported) so this
    checker's own hard-fail message is specific to queue-draft location, not
    output-path selection. Raises before anything else in the check that
    calls it."""
    resolved_target = path.resolve()
    live_queue = LIVE_QUEUE_ROOT.resolve()
    if resolved_target == live_queue or live_queue in resolved_target.parents:
        raise ApprovalCheckError(
            f"queue draft is located inside the live queue directory {live_queue}: "
            f"{resolved_target}. A queue draft must never live in pipeline/queue/ -- "
            "this approval cannot be recorded against it."
        )


def _count_hashtags(caption: str) -> int:
    return sum(1 for token in caption.split() if token.startswith("#"))


def _resolve_queue_draft(
    date_str: str,
    slot_id: str,
    out_dir: Optional[Path],
    explicit_path: Optional[str],
) -> Dict[str, Any]:
    if explicit_path:
        candidate = Path(explicit_path)
        queue_draft_path = candidate if candidate.is_absolute() else (ROOT / candidate)
    else:
        queue_draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)

    _assert_not_inside_live_queue(queue_draft_path)

    if not queue_draft_path.exists():
        raise ApprovalCheckError(
            f"no queue draft found at {queue_draft_path} -- an approval cannot be "
            "recorded without the queue draft it approves. Build one first with "
            "tools/lena_build_publish_packet_v1.py --queue-draft."
        )

    try:
        queue_draft = json.loads(queue_draft_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ApprovalCheckError(f"queue draft exists but failed to parse: {queue_draft_path}: {exc}") from exc

    if not isinstance(queue_draft, dict):
        raise ApprovalCheckError(f"queue draft at {queue_draft_path} is not a JSON object")

    metadata = queue_draft.get("metadata") if isinstance(queue_draft.get("metadata"), dict) else {}
    if metadata.get("queue_draft_only") is not True:
        raise ApprovalCheckError(
            f"queue draft at {queue_draft_path} is missing metadata.queue_draft_only:true -- "
            "refusing to treat an unrecognized file as a real queue draft"
        )

    return {"path": str(queue_draft_path), "data": queue_draft}


def _validate_caption(approved_caption: str) -> int:
    if approved_caption.strip() == QUEUE_DRAFT_CAPTION_PLACEHOLDER:
        raise ApprovalCheckError(
            "approved caption is still the queue-draft placeholder -- the operator "
            "must supply the real, final caption text, not the unedited placeholder"
        )
    hashtag_count = _count_hashtags(approved_caption)
    if hashtag_count > MAX_HASHTAGS_PER_CAPTION:
        raise ApprovalCheckError(
            f"approved caption has {hashtag_count} hashtags, more than the "
            f"{MAX_HASHTAGS_PER_CAPTION} allowed"
        )
    return hashtag_count


def _validate_operator_fields(approved_by: str, confirm: str) -> None:
    if not approved_by or not approved_by.strip():
        raise ApprovalCheckError("--approved-by must not be empty -- operator approval must be attributed")
    if confirm != REQUIRED_CONFIRM_PHRASE:
        raise ApprovalCheckError(
            f"--confirm did not exactly match the required phrase "
            f"{REQUIRED_CONFIRM_PHRASE!r} -- unclear operator approval"
        )


def check_publish_approval(
    date_str: str,
    slot_id: str,
    approved_caption: str,
    approved_by: str,
    confirm: str,
    platforms: List[str],
    out_dir: Optional[Path],
    queue_draft_path_override: Optional[str],
) -> Dict[str, Any]:
    """Read-only. Raises ApprovalCheckError on any hard-fail condition.
    Writes nothing, ever -- no approval artifact, no queue-draft edit, no
    queue-directory write."""
    try:
        resolved = resolve_packet_inputs(date_str, slot_id, out_dir)
    except ResolveError as exc:
        raise ApprovalCheckError(f"packet-input resolution failed (QA not pass, or other resolver hard-fail): {exc}") from exc

    packet_path = Path(resolved["intended_packet_output_path"])
    if not packet_path.exists():
        raise ApprovalCheckError(
            f"no publish packet found at {packet_path} -- an approval cannot be "
            "recorded without the packet it approves. Build one first with "
            "tools/lena_build_publish_packet_v1.py."
        )

    # QA overall==pass was already enforced inside resolve_packet_inputs() via
    # ResolveError above; re-assert explicitly here for a clear, dedicated
    # message rather than relying solely on the wrapped resolver error.
    if resolved.get("qa_overall") != "pass":
        raise ApprovalCheckError(
            f"QA overall='{resolved.get('qa_overall')}' (not 'pass') at {resolved['qa_path']} -- "
            "cannot record approval for a non-passing render"
        )

    queue_draft = _resolve_queue_draft(date_str, slot_id, out_dir, queue_draft_path_override)
    hashtag_count = _validate_caption(approved_caption)
    _validate_operator_fields(approved_by, confirm)

    approval_output_path = resolve_approval_output_path(date_str, slot_id, out_dir)

    future_approval_record = {
        "post_id": slot_id,
        "source_date": date_str,
        "publish_packet_path": str(packet_path),
        "queue_draft_path": queue_draft["path"],
        "qa_path": resolved["qa_path"],
        "qa_overall": resolved["qa_overall"],
        "approved_caption": approved_caption,
        "hashtag_count": hashtag_count,
        "platforms": platforms,
        "approved_by": approved_by,
        "approval_statement": confirm,
        "approved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "manual_one_off_confirmed": True,
        "generated_by": "tools/lena_record_publish_approval_v1.py",
        "promotion_status": "not_yet_promoted",
    }

    promotion_instructions = (
        "To promote this post to the live queue, by hand:\n"
        f"1. Copy {queue_draft['path']} to pipeline/queue/{slot_id}.json\n"
        "2. Replace its \"caption\" field with the approved_caption above\n"
        f"3. Run: python tools/process_queue.py --live --media-type photo --date {date_str}"
    )

    return {
        "date": date_str,
        "slot_id": slot_id,
        "publish_packet_path": str(packet_path),
        "queue_draft_path": queue_draft["path"],
        "qa_path": resolved["qa_path"],
        "qa_overall": resolved["qa_overall"],
        "future_approval_output_path": str(approval_output_path),
        "future_approval_output_already_exists": approval_output_path.exists(),
        "future_approval_record": future_approval_record,
        "promotion_instructions": promotion_instructions,
        "files_written_this_run": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Batch 1: read-only checker for a future Lena publish-approval "
            "record. Resolves and validates a slot's real packet/queue-draft/QA "
            "artifacts, runs every hard-fail rule, and prints a dry-run summary "
            "of the approval record that would be written later. Writes nothing "
            "-- no approval artifact, no queue-draft edit, no pipeline/queue/ "
            "write. --record/--force are not implemented in this batch."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact slot_id, e.g. 2026-07-07-03-photo")
    parser.add_argument("--approved-caption", required=True, dest="approved_caption")
    parser.add_argument("--approved-by", required=True, dest="approved_by")
    parser.add_argument("--confirm", required=True, help=f"must exactly equal: {REQUIRED_CONFIRM_PHRASE!r}")
    parser.add_argument("--platform", action="append", dest="platforms", default=None, help="repeatable; default instagram")
    parser.add_argument("--queue-draft-path", default=None, dest="queue_draft_path")
    parser.add_argument("--out-dir", default=None, help="Override the packet/queue-draft/approval output base directory.")
    args = parser.parse_args()

    out_dir: Optional[Path] = None
    if args.out_dir:
        candidate = Path(args.out_dir)
        out_dir = candidate if candidate.is_absolute() else (ROOT / candidate)

    platforms = args.platforms or ["instagram"]

    try:
        summary = check_publish_approval(
            args.date,
            args.slot_id,
            args.approved_caption,
            args.approved_by,
            args.confirm,
            platforms,
            out_dir,
            args.queue_draft_path,
        )
    except ApprovalCheckError as exc:
        print(json.dumps(
            {"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id, "files_written_this_run": []},
            indent=2,
        ))
        return 1

    print(json.dumps({"ok": True, "dry_run": True, "checked": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
