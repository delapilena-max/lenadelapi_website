from __future__ import annotations

# Lena queue-promotion tool -- the missing explicit state transition between
# an already-recorded, already-applied publish approval and a real, live
# queue item under pipeline/queue/.
#
# Chain this tool completes:
#   build (lena_build_publish_packet_v1.py --queue-draft)
#   -> record approval (lena_record_publish_approval_v1.py --record)
#   -> apply approval (lena_apply_publish_approval_v1.py --apply)
#   -> PROMOTE (this tool)
#   -> publish later (tools/process_queue.py --live, unchanged, untouched)
#
# Deliberately a small, separate, dedicated tool -- promotion behavior is not
# added to lena_record_publish_approval_v1.py, lena_apply_publish_approval_v1.py,
# or tools/process_queue.py. Those tools' own docstrings/invariants stay
# unweakened.
#
# Re-validates everything from first principles rather than trusting the
# queue draft's self-reported fields:
#   1. Re-loads and re-checks the immutable approval artifact (every rule
#      lena_apply_publish_approval_v1.py already enforces, duplicated here on
#      purpose -- promotion must not assume the approval was ever re-read
#      since it was recorded).
#   2. Re-loads and re-checks the queue draft itself (caption already
#      applied, still a draft, still operator-review-required, still
#      metadata.queue_draft_only:true).
#   3. Re-runs the existing, unmodified provider resolver (Rule Zero --
#      resolve_packet_inputs() for kling, resolve_packet_inputs_higgsfield()
#      for higgsfield) and cross-checks its real output against the queue
#      draft's own metadata, field by field. A queue draft can never promote
#      on self-reported metadata alone; any drift between the resolver's
#      real answer and the draft's stored answer fails closed.
#
# The ONLY three fields this tool ever changes, on an otherwise byte-for-byte
# copy of the queue draft:
#   approved_for_live_publish: false -> true
#   operator_review_required:  true  -> false
#   metadata.queue_draft_only: true  -> false
# Caption, post_id, slot_id, media_path, media_type, platforms, provider,
# provider_job_id, custom_reference_id, resolution, activity, pose,
# visual_style, image_prompt, image_engine, avatar identity fields, and every
# other existing key are read back byte-identical and never touched.
#
# Never modifies the approval artifact. Never modifies the source queue
# draft. Idempotent: if the target queue item already exists and is
# semantically identical to the expected promoted item, this reports success
# and writes nothing; if it exists and differs, this fails closed and never
# overwrites it.
#
# Defaults to dry-run (validates everything, writes nothing); only --promote
# performs the one write. Provider is always explicit (--provider, default
# "kling" for backward-compatible parity with the other tools in this
# chain) -- never auto-detected from the queue draft's own metadata, never a
# silent cross-provider fallback.
#
# Never imports pipeline.posting_manager, tools.process_queue,
# pipeline.higgsfield_lena_api_executor, pipeline.kling_apilena_api_executor,
# any publisher/API module, requests, urllib, or pipeline.env_loader -- this
# module cannot publish, generate, or call any network/API surface, by
# construction, not just by convention.
#
# Run (dry-run, writes nothing):
#   python tools/lena_promote_to_queue_v1.py --date 2026-07-09 --slot readypack0709-pack003-08-photo --provider higgsfield
# Run (writes the promoted queue item to pipeline/queue/<slot_id>.json):
#   python tools/lena_promote_to_queue_v1.py --date 2026-07-09 --slot readypack0709-pack003-08-photo --provider higgsfield --promote

import argparse
import copy
import hashlib
import json
import sys
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
    resolve_queue_draft_output_path,
)
from tools.lena_record_publish_approval_v1 import (  # noqa: E402
    MAX_HASHTAGS_PER_CAPTION,
    REQUIRED_CONFIRM_PHRASE,
    _count_hashtags,
    resolve_approval_output_path,
)

# Explicit provider -> resolver map. No auto-detection, no fallback: an
# unrecognized provider string is simply not a key here and fails closed.
PROVIDER_RESOLVERS = {
    "kling": resolve_packet_inputs,
    "higgsfield": resolve_packet_inputs_higgsfield,
}

# The exact, and only, three fields promotion ever changes. Order matches
# the order they're described everywhere else in this module/docs.
PROMOTED_STATE_FIELDS: tuple = (
    "approved_for_live_publish",
    "operator_review_required",
    "metadata.queue_draft_only",
)


class PromoteError(Exception):
    """Raised for any hard-fail condition. Never caught silently -- main()
    reports it and exits non-zero. No file is ever written when this is
    raised."""


def resolve_promoted_queue_output_path(slot_id: str, queue_root: Optional[Path] = None) -> Path:
    """Target path for the real, live queue item. Defaults to the real
    pipeline/queue/ directory (LIVE_QUEUE_ROOT); queue_root exists only so
    scratch/function-level tests can point this at a temporary directory
    instead -- production callers must never pass it."""
    base = queue_root if queue_root is not None else LIVE_QUEUE_ROOT
    return base / f"{slot_id}.json"


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    if not path.exists():
        raise PromoteError(f"{label} does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PromoteError(f"{label} failed to parse: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PromoteError(f"{label} did not contain a JSON object: {path}")
    return data


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_approval(approval: Dict[str, Any], date_str: str, slot_id: str) -> Dict[str, Any]:
    """Re-checks every rule lena_apply_publish_approval_v1.py already
    enforces against the same immutable approval artifact. Read-only; raises
    PromoteError on any hard-fail condition."""
    if approval.get("source_date") != date_str:
        raise PromoteError(
            f"approval source_date {approval.get('source_date')!r} does not match requested date {date_str!r}"
        )
    if approval.get("post_id") != slot_id:
        raise PromoteError(
            f"approval post_id {approval.get('post_id')!r} does not match requested slot {slot_id!r}"
        )

    approved_caption = approval.get("approved_caption")
    if not approved_caption or not str(approved_caption).strip():
        raise PromoteError("approval's approved_caption is missing or empty")

    actual_hashtag_count = _count_hashtags(approved_caption)
    stored_hashtag_count = approval.get("hashtag_count")
    if actual_hashtag_count != stored_hashtag_count:
        raise PromoteError(
            f"approval hashtag_count {stored_hashtag_count!r} does not match the actual "
            f"hashtag count ({actual_hashtag_count}) found in approved_caption"
        )
    if not (1 <= actual_hashtag_count <= MAX_HASHTAGS_PER_CAPTION):
        raise PromoteError(
            f"hashtag count {actual_hashtag_count} is not between 1 and {MAX_HASHTAGS_PER_CAPTION} inclusive"
        )

    approved_by = approval.get("approved_by")
    if not approved_by or not str(approved_by).strip():
        raise PromoteError("approval's approved_by is missing or empty")

    approval_statement = approval.get("approval_statement")
    if approval_statement != REQUIRED_CONFIRM_PHRASE:
        raise PromoteError(
            f"approval_statement {approval_statement!r} does not exactly match "
            f"the required phrase {REQUIRED_CONFIRM_PHRASE!r}"
        )

    # Same optional-but-enforced-if-present rule lena_apply_publish_approval_v1.py
    # already uses: not one of this checker's own required inputs, but if
    # present it must be true.
    if "manual_one_off_confirmed" in approval and approval.get("manual_one_off_confirmed") is not True:
        raise PromoteError("approval's manual_one_off_confirmed is present but not true")

    if approval.get("promotion_status") != "not_yet_promoted":
        raise PromoteError(
            f"approval promotion_status {approval.get('promotion_status')!r} is not "
            "'not_yet_promoted' -- refusing to promote an item that may already have "
            "been promoted or published"
        )

    return {
        "approved_caption": approved_caption,
        "hashtag_count": actual_hashtag_count,
        "approved_by": approved_by,
        "approval_statement": approval_statement,
        "approved_at_utc": approval.get("approved_at_utc"),
    }


def _validate_queue_draft(
    queue_draft: Dict[str, Any],
    slot_id: str,
    provider: str,
    approved_caption: str,
    approval_hashtag_count: int,
) -> None:
    """Read-only. Raises PromoteError on any hard-fail condition."""
    if queue_draft.get("slot_id") != slot_id:
        raise PromoteError(
            f"queue draft slot_id {queue_draft.get('slot_id')!r} does not match requested slot {slot_id!r}"
        )

    draft_caption = queue_draft.get("caption")
    if draft_caption == QUEUE_DRAFT_CAPTION_PLACEHOLDER:
        raise PromoteError(
            "queue draft caption is still the unedited placeholder -- run "
            "tools/lena_apply_publish_approval_v1.py --apply first"
        )
    if draft_caption != approved_caption:
        raise PromoteError(
            "queue draft caption does not exactly equal the approval's approved_caption -- "
            "run tools/lena_apply_publish_approval_v1.py --apply first"
        )

    actual_hashtag_count = _count_hashtags(str(draft_caption or ""))
    if actual_hashtag_count != approval_hashtag_count:
        raise PromoteError(
            f"queue draft caption has {actual_hashtag_count} hashtags, approval declares "
            f"{approval_hashtag_count} -- refusing to promote a caption/approval mismatch"
        )

    if queue_draft.get("approved_for_live_publish") is not False:
        raise PromoteError(
            f"queue draft approved_for_live_publish is {queue_draft.get('approved_for_live_publish')!r}, "
            "expected false -- refusing to promote an item that may already be live-approved"
        )
    if queue_draft.get("operator_review_required") is not True:
        raise PromoteError(
            f"queue draft operator_review_required is {queue_draft.get('operator_review_required')!r}, "
            "expected true"
        )

    metadata = queue_draft.get("metadata") if isinstance(queue_draft.get("metadata"), dict) else None
    if metadata is None:
        raise PromoteError("queue draft is missing a metadata object")
    if metadata.get("queue_draft_only") is not True:
        raise PromoteError(
            "queue draft is missing metadata.queue_draft_only:true -- refusing to treat "
            "an unrecognized file as a real queue draft"
        )

    # Provider presence/consistency. Kling drafts never carry metadata.provider
    # at all (see lena_build_publish_packet_v1.build_queue_draft()'s own
    # comment: "absent entirely for the existing Kling path") -- that is the
    # established, correct shape, not a defect. A Higgsfield draft always
    # carries it. Either way the effective --provider must agree with what
    # the draft actually declares.
    draft_provider = metadata.get("provider")
    if draft_provider is not None:
        if draft_provider != provider:
            raise PromoteError(
                f"queue draft metadata.provider {draft_provider!r} does not match "
                f"requested --provider {provider!r}"
            )
    elif provider != "kling":
        raise PromoteError(
            "queue draft has no metadata.provider, which is only valid for the "
            f"implicit Kling default -- --provider {provider!r} was explicitly requested"
        )

    if not queue_draft.get("media_path"):
        raise PromoteError("queue draft is missing media_path")
    media_path = Path(str(queue_draft["media_path"]))
    if not media_path.exists():
        raise PromoteError(f"queue draft media_path does not exist on disk: {media_path}")

    media_type = str(queue_draft.get("media_type") or "").lower().strip()
    if media_type not in {"photo", "image", "story", "stories"}:
        raise PromoteError(
            f"queue draft media_type {queue_draft.get('media_type')!r} is not supported by this "
            "tool yet -- only photo/image/story queue drafts can be re-validated via the existing "
            "packet resolvers (resolve_packet_inputs()/resolve_packet_inputs_higgsfield() have "
            "no video path). media_type itself is never rewritten/normalized here -- read back "
            "byte-identical, same as every other field this tool never touches."
        )

    platforms = queue_draft.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise PromoteError(f"queue draft platforms must be a non-empty list, got {platforms!r}")

    for required_meta in ("avatar_nickname", "image_engine", "image_prompt", "activity", "pose", "visual_style"):
        if not metadata.get(required_meta):
            raise PromoteError(f"queue draft metadata is missing required field: {required_meta}")
    if provider == "higgsfield" and not metadata.get("resolution"):
        raise PromoteError("queue draft metadata is missing required field: resolution")


def _revalidate_with_resolver(
    date_str: str,
    slot_id: str,
    provider: str,
    queue_draft: Dict[str, Any],
    out_dir: Optional[Path],
    source_slot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Rule Zero / provider revalidation. Re-runs the existing, unmodified
    resolver (which itself re-runs the existing, unmodified _resolve_qa()
    gate) and cross-checks its real output against the queue draft's own
    metadata, field by field. Never trusts the draft's self-reported values
    alone. Raises PromoteError on any hard-fail condition, including any
    single field mismatch.

    source_slot_id (2026-07-10, optional, explicit-only, default None):
    the identity used to call the resolver. When omitted, defaults to
    slot_id -- byte-identical to every call site and every queue item that
    existed before this parameter, none of which have ever needed it.
    Exists only for a queue item whose own promotion/approval identity
    (slot_id) deliberately differs from the real generation it was
    rendered from -- e.g. a Story repackaging of an existing photo slot,
    kept under a distinct slot_id specifically so it can never collide
    with a future feed-photo promotion of the same underlying render (see
    pipeline/publisher/instagram_queue_bridge.py's feed-photo aspect-ratio
    gate, which such a render would fail anyway, but the identity
    separation is generic, not slot-specific). Never inferred/auto-detected
    -- an operator or caller must explicitly assert it, same discipline as
    --provider."""
    resolver = PROVIDER_RESOLVERS.get(provider)
    if resolver is None:
        raise PromoteError(
            f"unknown provider {provider!r} -- no resolver mapping (fails closed, never auto-detected)"
        )

    effective_source_slot_id = source_slot_id or slot_id

    try:
        resolved = resolver(date_str, effective_source_slot_id, out_dir)
    except ResolveError as exc:
        raise PromoteError(f"Rule Zero / provider revalidation failed: {exc}") from exc

    metadata = queue_draft.get("metadata") or {}
    mismatches: List[str] = []

    def _check(label: str, resolved_value: Any, draft_value: Any) -> None:
        if resolved_value != draft_value:
            mismatches.append(f"{label}: resolver={resolved_value!r} draft={draft_value!r}")

    # Compared against the queue draft's own self-reported
    # metadata.source_slot_id, falling back to the top-level slot_id --
    # for every existing queue item (Kling or Higgsfield, built via
    # lena_build_publish_packet_v1.build_queue_draft(), which always sets
    # metadata["source_slot_id"] = resolved["slot_id"]) these two values
    # are always identical, so this fallback is a no-op there. Only a
    # queue item whose slot_id was deliberately kept distinct from its
    # generation source (and which must therefore carry a real, differing
    # metadata.source_slot_id) exercises the non-fallback branch.
    _check(
        "slot_id",
        resolved.get("slot_id"),
        metadata.get("source_slot_id") or queue_draft.get("slot_id"),
    )
    _check("image_engine", resolved.get("image_engine"), metadata.get("image_engine"))
    _check("media_path", resolved.get("image_path"), queue_draft.get("media_path"))
    _check("image_prompt", resolved.get("image_prompt"), metadata.get("image_prompt"))
    _check("activity", resolved.get("activity"), metadata.get("activity"))
    _check("pose", resolved.get("pose"), metadata.get("pose"))
    _check("visual_style", resolved.get("visual_style"), metadata.get("visual_style"))

    if provider == "higgsfield":
        _check("provider", resolved.get("provider"), metadata.get("provider"))
        _check("custom_reference_id", resolved.get("custom_reference_id"), metadata.get("custom_reference_id"))
        _check("resolution", resolved.get("resolution"), metadata.get("resolution"))
        debug_artifacts = resolved.get("debug_artifacts") or {}
        _check("provider_job_id", debug_artifacts.get("provider_job_id"), metadata.get("provider_job_id"))

    if mismatches:
        raise PromoteError(
            "Rule Zero / provider revalidation found drift between the queue draft's "
            "self-reported metadata and the real resolver output -- refusing to promote "
            "on self-reported data alone: " + "; ".join(mismatches)
        )

    return resolved


def check_promote_to_queue(
    date_str: str,
    slot_id: str,
    provider: str,
    out_dir: Optional[Path] = None,
    queue_root: Optional[Path] = None,
    source_slot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only. Raises PromoteError on any hard-fail condition. Writes
    nothing, ever. Returns a dict describing exactly what would change
    (empty list if already promoted).

    source_slot_id: optional, explicit-only, default None (falls back to
    slot_id -- see _revalidate_with_resolver()'s docstring). Never used for
    approval_path/queue_draft_path/target_path -- those remain keyed by
    slot_id exactly as before; only the resolver call is affected."""
    if not provider or provider not in PROVIDER_RESOLVERS:
        raise PromoteError(
            f"unknown provider {provider!r} -- must be one of {sorted(PROVIDER_RESOLVERS)} "
            "(fails closed, never auto-detected)"
        )

    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)
    approval = _load_json_object(approval_path, "approval artifact")
    approval_facts = _validate_approval(approval, date_str, slot_id)

    queue_draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
    queue_draft = _load_json_object(queue_draft_path, "queue draft")
    _validate_queue_draft(
        queue_draft,
        slot_id,
        provider,
        approval_facts["approved_caption"],
        approval_facts["hashtag_count"],
    )

    resolved = _revalidate_with_resolver(date_str, slot_id, provider, queue_draft, out_dir, source_slot_id=source_slot_id)

    promoted_item = copy.deepcopy(queue_draft)
    promoted_item["approved_for_live_publish"] = True
    promoted_item["operator_review_required"] = False
    promoted_item["metadata"]["queue_draft_only"] = False

    target_path = resolve_promoted_queue_output_path(slot_id, queue_root)

    already_promoted = False
    would_write = True
    fields_that_would_change: List[str] = list(PROMOTED_STATE_FIELDS)

    if target_path.exists():
        existing = _load_json_object(target_path, "existing target queue item")
        if existing == promoted_item:
            already_promoted = True
            would_write = False
            fields_that_would_change = []
        else:
            raise PromoteError(
                f"target queue item already exists at {target_path} and differs from the "
                "expected promoted item -- refusing to overwrite an existing, non-identical "
                "queue item"
            )

    return {
        "date": date_str,
        "slot_id": slot_id,
        "provider": provider,
        "approval_path": str(approval_path),
        "approval_sha256": _sha256_file(approval_path),
        "queue_draft_path": str(queue_draft_path),
        "queue_draft_sha256": _sha256_file(queue_draft_path),
        "target_queue_path": str(target_path),
        "approved_by": approval_facts["approved_by"],
        "approved_at_utc": approval_facts["approved_at_utc"],
        "approval_statement": approval_facts["approval_statement"],
        "caption_sha256": _sha256_text(approval_facts["approved_caption"]),
        "resolver_qa_overall": resolved.get("qa_overall"),
        "fields_that_would_change": fields_that_would_change,
        "would_write": would_write,
        "already_promoted": already_promoted,
        "_promoted_item": promoted_item,
        "_target_path": target_path,
    }


def promote_to_queue(checked: Dict[str, Any]) -> Optional[Path]:
    """Writes the promoted queue item to its target path ONLY if it isn't
    already there in the exact expected form. Returns the path written, or
    None if the promotion was already applied (idempotent no-op, zero
    writes). The source queue draft and the approval artifact are never
    opened for writing anywhere in this module."""
    if checked["already_promoted"] or not checked["would_write"]:
        return None
    target_path = checked["_target_path"]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(checked["_promoted_item"], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promotes an already-approved, already-applied Lena queue draft into a real "
            "queue item under pipeline/queue/. Re-validates the immutable approval artifact, "
            "the queue draft, and re-runs the existing provider resolver (Rule Zero) before "
            "writing -- never trusts the draft's self-reported metadata alone. Defaults to "
            "dry-run (writes nothing); --promote performs the one write. Only three fields "
            "ever change: approved_for_live_publish, operator_review_required, "
            "metadata.queue_draft_only. Idempotent; fails closed on any existing, "
            "non-identical target."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact slot_id, e.g. readypack0709-pack003-08-photo")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_RESOLVERS),
        default="kling",
        help=(
            "Explicit provider selector (default: kling, preserved for backward "
            "compatibility with the rest of this chain). Never auto-detected from the "
            "queue draft's own metadata, never falls back across providers."
        ),
    )
    parser.add_argument("--out-dir", default=None, help="Override the packet/queue-draft/approval output base directory.")
    parser.add_argument(
        "--queue-dir",
        default=None,
        help=(
            "Override the target live-queue directory. Testing only -- production callers "
            "must never pass this; default is the real pipeline/queue/."
        ),
    )
    parser.add_argument(
        "--source-slot",
        default=None,
        dest="source_slot_id",
        help=(
            "Optional, explicit-only override for the identity used to call the Rule Zero "
            "provider resolver. Defaults to --slot when omitted -- every existing item is "
            "unaffected. Only needed when --slot (the queue item's own promotion identity) "
            "deliberately differs from the real generation slot it was rendered from (e.g. a "
            "Story repackaging of an existing photo render). Never auto-detected."
        ),
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Write the promoted queue item. Without this flag, only a dry-run summary is printed.",
    )
    args = parser.parse_args()

    out_dir: Optional[Path] = None
    if args.out_dir:
        candidate = Path(args.out_dir)
        out_dir = candidate if candidate.is_absolute() else (ROOT / candidate)

    queue_root: Optional[Path] = None
    if args.queue_dir:
        candidate = Path(args.queue_dir)
        queue_root = candidate if candidate.is_absolute() else (ROOT / candidate)

    try:
        checked = check_promote_to_queue(
            args.date, args.slot_id, args.provider, out_dir, queue_root, source_slot_id=args.source_slot_id
        )
    except PromoteError as exc:
        print(json.dumps(
            {"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id, "files_written_this_run": []},
            indent=2,
        ))
        return 1

    report = {k: v for k, v in checked.items() if not k.startswith("_")}

    if not args.promote:
        print(json.dumps({"ok": True, "dry_run": True, "checked": report}, indent=2))
        return 0

    written_path = promote_to_queue(checked)
    files_written = [str(written_path)] if written_path else []
    print(json.dumps({"ok": True, "dry_run": False, "checked": report, "files_written_this_run": files_written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
