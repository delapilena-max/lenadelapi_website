from __future__ import annotations

# Lena publish-approval checker -- Batch 2 (approval-artifact writing, non-clobber).
#
# Design doc: pipeline/agents/lena/95_publish_gate/{AGENT,RULES,INPUTS,OUTPUTS}.md.
# Batch 1 (read-only checker, all hard-fail rules) is unchanged below -- every check
# still runs exactly as before, writing nothing, on every invocation regardless of
# --record. Batch 2 adds: an OPTIONAL --record flag that, only when passed and only
# after every Batch 1 check has already passed, writes the approval-decision
# artifact to pipeline/publish_packets/lena/<date>/<slot_id>_approval.json (or under
# --out-dir), non-clobber by default (--force required to overwrite that exact
# file, never a directory).
#
# Still has no --live/--publish/--approve-and-publish/queue-promotion flag of any
# kind. --record only ever writes the one approval-artifact file under the packet
# output directory (default pipeline/publish_packets/lena/), never
# pipeline/queue/. A hard guard (_assert_not_inside_live_queue, reused from Batch 1)
# is applied to the approval-artifact output path itself before any write, catching
# --out-dir pipeline/queue and --out-dir pipeline/queue/anything -- on top of the
# Batch 1 guard already applied to the queue-draft path, which independently aborts
# the whole check (before write_approval_record is ever called) under the same
# --out-dir conditions.
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
    resolve_packet_inputs_higgsfield,
    resolve_packet_output_path,
    resolve_queue_draft_output_path,
)

DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"
MAX_HASHTAGS_PER_CAPTION = 3

# Two-field approval model (2026-07-10): caption approval and live-publish
# authorization are two independent human decisions, previously conflated
# into one required phrase. REQUIRED_CAPTION_CONFIRM_PHRASE authorizes only
# recording the approved caption and applying it to the queue draft --
# never promotion, never live queue placement, never publishing.
# REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE remains required only for promotion
# (tools/lena_promote_to_queue_v1.py) and is never inferred, auto-populated,
# or copied from caption approval -- it must be absent/null/empty until
# explicitly given. Legacy artifacts recorded before this split (a single
# "approval_statement" field equal to the live-publish phrase) remain valid
# under a read-only compatibility path in lena_apply_publish_approval_v1.py
# and lena_promote_to_queue_v1.py -- never rewritten, never migrated.
REQUIRED_CAPTION_CONFIRM_PHRASE = "I approve this caption"
REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE = "I approve this for live publish"


class ApprovalCheckError(Exception):
    """Raised for any hard-fail condition in approval-record resolution/
    validation. Never caught silently -- main() reports it and exits
    non-zero. Batch 1's checks never write any file, on success or
    failure -- only write_approval_record() (Batch 2) ever writes, and only
    after every one of these checks has already passed."""


class ApprovalWriteError(Exception):
    """Raised for a hard-fail condition when writing the approval artifact
    (already exists without --force, output path inside pipeline/queue/, or
    a directory at that path). No file is written when this is raised."""


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


def _validate_operator_fields(
    approved_by: str, caption_confirm: str, live_publish_confirm: Optional[str]
) -> None:
    if not approved_by or not approved_by.strip():
        raise ApprovalCheckError("--approved-by must not be empty -- operator approval must be attributed")
    if caption_confirm != REQUIRED_CAPTION_CONFIRM_PHRASE:
        raise ApprovalCheckError(
            f"--confirm did not exactly match the required caption-approval phrase "
            f"{REQUIRED_CAPTION_CONFIRM_PHRASE!r} -- unclear operator approval"
        )
    # live_publish_confirm is genuinely optional -- None/absent means live
    # publish is not yet authorized, which is a valid, expected state for a
    # caption-only approval, never an error. Only a *supplied-but-wrong*
    # value is rejected -- fails closed rather than silently accepting a
    # garbled live-publish claim.
    if live_publish_confirm is not None and live_publish_confirm != REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE:
        raise ApprovalCheckError(
            f"--live-publish-confirm was supplied but did not exactly match the required phrase "
            f"{REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE!r} -- omit this flag entirely if live publish "
            "is not yet authorized; never supply a near-miss value"
        )


def check_publish_approval(
    date_str: str,
    slot_id: str,
    approved_caption: str,
    approved_by: str,
    caption_confirm: str,
    platforms: List[str],
    out_dir: Optional[Path],
    queue_draft_path_override: Optional[str],
    provider: str = "kling",
    source_slot_id: Optional[str] = None,
    live_publish_confirm: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only. Raises ApprovalCheckError on any hard-fail condition.
    Writes nothing, ever -- no approval artifact, no queue-draft edit, no
    queue-directory write.

    Provider dispatch (2026-07-10), matching tools/lena_build_publish_packet_v1.py
    and tools/lena_preflight.py's own established pattern: explicit
    --provider only, default "kling" for backward compatibility, no
    auto-detection, no silent cross-provider fallback. "higgsfield" reuses
    the existing, unmodified resolve_packet_inputs_higgsfield() (which
    itself still gates on the same unmodified Rule Zero/_resolve_qa()) --
    resolver logic is not duplicated here.

    source_slot_id (2026-07-10, optional, explicit-only, default None):
    the identity used to call the resolver (and, consequently, to locate
    the publish packet Markdown, since that path is derived inside the
    same resolver call). Defaults to slot_id when omitted -- byte-identical
    to every approval recorded before this parameter existed. Only needed
    when slot_id (the approval/queue-draft identity being recorded) is
    deliberately distinct from the real generation slot it was rendered
    from -- see tools/lena_promote_to_queue_v1.py's
    _revalidate_with_resolver() docstring for the full rationale (same
    concept, same fallback discipline, mirrored here so an approval can be
    recorded under that same distinct identity in the first place). Never
    auto-detected.

    live_publish_confirm (2026-07-10, optional, default None): if supplied,
    must exactly equal REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE. Recording an
    approval NEVER requires this -- caption approval and live-publish
    authorization are independent. When omitted, the artifact's
    live_publish_statement field is written as null, meaning live publish
    is not yet authorized; promotion (lena_promote_to_queue_v1.py) is the
    only place that value is ever required to be the real phrase. Never
    inferred from caption_confirm."""
    resolver = resolve_packet_inputs_higgsfield if provider == "higgsfield" else resolve_packet_inputs
    effective_source_slot_id = source_slot_id or slot_id
    try:
        resolved = resolver(date_str, effective_source_slot_id, out_dir)
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
    _validate_operator_fields(approved_by, caption_confirm, live_publish_confirm)

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
        # Two-field model (2026-07-10): caption_approval_statement
        # authorizes recording/applying the caption only.
        # live_publish_statement is independent, never inferred/copied from
        # caption_confirm, and null unless explicitly supplied -- only
        # promotion requires it to be the real phrase.
        "caption_approval_statement": caption_confirm,
        "live_publish_statement": live_publish_confirm,
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


def write_approval_record(checked: Dict[str, Any], force: bool) -> Path:
    """Writes the approval artifact ONLY -- never the queue draft, never
    anything under pipeline/queue/. Only called from main() when --record is
    passed, and only after check_publish_approval() has already succeeded
    (every Batch 1 hard-fail rule already passed)."""
    output_path = Path(checked["future_approval_output_path"])

    try:
        _assert_not_inside_live_queue(output_path)
    except ApprovalCheckError as exc:
        raise ApprovalWriteError(str(exc)) from exc

    if output_path.exists() and not force:
        raise ApprovalWriteError(
            f"approval artifact already exists at {output_path} -- pass --force to "
            "overwrite this exact file (non-clobber default)"
        )
    if output_path.exists() and output_path.is_dir():
        raise ApprovalWriteError(f"refusing to write: {output_path} is a directory, not a file")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(checked["future_approval_record"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Batch 2: checker + optional writer for a Lena publish-approval "
            "record. Resolves and validates a slot's real packet/queue-draft/QA "
            "artifacts, runs every hard-fail rule, and prints a summary of the "
            "approval record. Without --record, writes nothing (dry-run only). "
            "With --record, writes the approval artifact ONLY -- never the queue "
            "draft, never anything under pipeline/queue/."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact slot_id, e.g. 2026-07-07-03-photo")
    parser.add_argument(
        "--provider",
        choices=["kling", "higgsfield"],
        default="kling",
        help=(
            "Explicit provider selector (default: kling, preserved for backward "
            "compatibility). Never auto-detected, never falls back across "
            "providers -- an invalid value is rejected by argparse itself."
        ),
    )
    parser.add_argument("--approved-caption", required=True, dest="approved_caption")
    parser.add_argument("--approved-by", required=True, dest="approved_by")
    parser.add_argument(
        "--confirm",
        required=True,
        help=(
            f"Caption-approval confirmation, must exactly equal: {REQUIRED_CAPTION_CONFIRM_PHRASE!r}. "
            "Authorizes recording/applying the caption only -- never promotion or live publish."
        ),
    )
    parser.add_argument(
        "--live-publish-confirm",
        default=None,
        dest="live_publish_confirm",
        help=(
            f"Optional. If supplied, must exactly equal: {REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE!r}. "
            "Omit entirely if live publish is not yet authorized -- this is the normal, expected "
            "state for a caption-only approval. Only lena_promote_to_queue_v1.py ever requires this."
        ),
    )
    parser.add_argument("--platform", action="append", dest="platforms", default=None, help="repeatable; default instagram")
    parser.add_argument("--queue-draft-path", default=None, dest="queue_draft_path")
    parser.add_argument(
        "--source-slot",
        default=None,
        dest="source_slot_id",
        help=(
            "Optional, explicit-only override for the identity used to call the Rule Zero "
            "provider resolver (and locate the publish packet). Defaults to --slot when "
            "omitted -- every existing approval is unaffected. Only needed when --slot (the "
            "approval/queue-draft identity being recorded) deliberately differs from the real "
            "generation slot it was rendered from. Never auto-detected."
        ),
    )
    parser.add_argument("--out-dir", default=None, help="Override the packet/queue-draft/approval output base directory.")
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write the approval artifact. Without this flag, only a dry-run summary is printed; nothing is written.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing approval artifact at its exact resolved path. Never touches a directory. Only meaningful with --record.",
    )
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
            provider=args.provider,
            source_slot_id=args.source_slot_id,
            live_publish_confirm=args.live_publish_confirm,
        )
    except ApprovalCheckError as exc:
        print(json.dumps(
            {"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id, "files_written_this_run": []},
            indent=2,
        ))
        return 1

    if not args.record:
        print(json.dumps({"ok": True, "dry_run": True, "checked": summary}, indent=2))
        return 0

    try:
        approval_path = write_approval_record(summary, args.force)
    except ApprovalWriteError as exc:
        summary["files_written_this_run"] = []
        print(json.dumps(
            {
                "ok": False,
                "error": str(exc),
                "date": args.date,
                "slot_id": args.slot_id,
                "checked": summary,
            },
            indent=2,
        ))
        return 1

    summary["files_written_this_run"] = [str(approval_path)]
    print(json.dumps({"ok": True, "dry_run": False, "checked": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
