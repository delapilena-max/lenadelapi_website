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
#   4. Re-verifies the clean-export contract (2026-07-11,
#      tools/lena_verify_clean_export_v1.py::verify_clean_export()) against
#      the queue draft's raw media_path: a verified clean derivative +
#      provenance sidecar must exist and match (every hash recomputed from
#      disk, never trusted from the sidecar alone). This is what makes the
#      clean derivative -- never the raw provider/source asset -- eligible
#      to become the queue item's publish media path.
#
# Fields this tool changes, on an otherwise byte-for-byte copy of the queue
# draft:
#   approved_for_live_publish: false -> true
#   operator_review_required:  true  -> false
#   metadata.queue_draft_only: true  -> false
#   media_path: raw source asset path -> verified clean-export derivative
#     path (2026-07-11, clean-export contract). ONLY changed after
#     tools/lena_verify_clean_export_v1.py::verify_clean_export() proves, by
#     recomputing every hash from the real files on disk, that a clean
#     derivative + provenance sidecar for the draft's raw media_path exist
#     and match. If that verification fails for any reason, promotion fails
#     closed -- media_path is never left pointing at the raw source, there
#     is no bypass flag, and the raw source is never silently treated as
#     already clean.
#   metadata.source_asset_path / metadata.source_asset_sha256 /
#   metadata.clean_export_derivative_sha256 /
#   metadata.clean_export_sidecar_path / metadata.clean_export_verified /
#   metadata.clean_export_generated_by / metadata.clean_export_created_at_utc:
#     new provenance fields (2026-07-11) recording the raw source asset
#     separately, so it remains internally traceable even though it is no
#     longer the queue item's publish media path. Only fields the scrubber's
#     own sidecar schema actually produces are surfaced here -- no fabricated
#     "scrubber version" field, since the current sidecar schema has none.
# Caption, post_id, slot_id, media_type, platforms, provider,
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
    resolve_packet_inputs_higgsfield_derived_shortform,
    resolve_packet_inputs_video,
    resolve_queue_draft_output_path,
)
from tools.lena_record_publish_approval_v1 import (  # noqa: E402
    resolve_approval_output_path,
)
from tools.lena_verify_clean_export_v1 import (  # noqa: E402
    CleanExportVerificationError,
    verify_clean_export,
)
from tools.lena_human_rejection_gate_v1 import (  # noqa: E402
    HumanRejectionGateError,
    assert_no_matching_human_rejection,
)
from tools.lena_publish_approval_binding_v1 import (  # noqa: E402
    _count_hashtags,
    _validate_approval_shape,
    resolve_approval_execution_bindings,
)

# Explicit provider -> resolver map. No auto-detection, no fallback: an
# unrecognized provider string is simply not a key here and fails closed.
#
# "video" (2026-07-11) is a resolver-selection key, not a generation-provider
# identity -- it selects resolve_packet_inputs_video(), the provider-neutral
# video/Reel resolver. The real generation-provider identity (if any) for a
# video asset is a separate, optional data field inside that resolver's own
# output (resolved["provider"]), never conflated with this dispatch key, and
# never defaulted to Kling or any other specific provider.
#
# "higgsfield_derived_shortform" (2026-07-12) is a third, distinct dispatch
# key -- for a Reel/Story composed LOCALLY from an approved Higgsfield photo
# + an approved music track (tools/lena_prepare_story_video_v1.py), never
# from a distinct provider video-generation call. Selects
# resolve_packet_inputs_higgsfield_derived_shortform(), which revalidates
# the source photo through the existing, unmodified Higgsfield resolver and
# separately re-verifies the prepared short-form asset's own provenance --
# see that function's own module comment for the full chain. Deliberately a
# separate key from "higgsfield" (a photo item) and "video" (a
# provider-generated video item): neither of those resolvers' cross-check
# shapes are correct for a locally-composed derived asset.
PROVIDER_RESOLVERS = {
    "kling": resolve_packet_inputs,
    "higgsfield": resolve_packet_inputs_higgsfield,
    "video": resolve_packet_inputs_video,
    "higgsfield_derived_shortform": resolve_packet_inputs_higgsfield_derived_shortform,
}

# The three original state-transition fields promotion changes. Order
# matches the order they're described everywhere else in this module/docs.
PROMOTED_STATE_FIELDS: tuple = (
    "approved_for_live_publish",
    "operator_review_required",
    "metadata.queue_draft_only",
)

# Clean-export contract fields (2026-07-11) promotion additionally changes,
# only after verify_clean_export() passes. See the module docstring above
# for exactly what each field means and why media_path is included here.
CLEAN_EXPORT_PROMOTED_FIELDS: tuple = (
    "media_path",
    "metadata.source_asset_path",
    "metadata.source_asset_sha256",
    "metadata.clean_export_derivative_sha256",
    "metadata.clean_export_sidecar_path",
    "metadata.clean_export_verified",
    "metadata.clean_export_generated_by",
    "metadata.clean_export_created_at_utc",
)


class PromoteError(Exception):
    """Raised for any hard-fail condition. Never caught silently -- main()
    reports it and exits non-zero. No file is ever written when this is
    raised."""


def _validate_approval(approval: Dict[str, Any], date_str: str, slot_id: str) -> Dict[str, Any]:
    """Compatibility shim for tools that import promotion's approval
    validator directly. Promotion itself now uses the shared native-or-
    corrected approval binding path; this helper preserves the historical
    dict-in/dict-out contract for other read-only validators."""
    return _validate_approval_shape(
        approval,
        date_str,
        slot_id,
        require_live_publish_authorization=True,
        require_bound_files_exist=False,
        error_cls=PromoteError,
    )


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
    elif provider not in {"kling", "video"}:
        # "video" (2026-07-11) joins "kling" here for the same reason: the
        # provider-neutral video resolver (resolve_packet_inputs_video())
        # never requires metadata.provider either -- it's an optional,
        # never-defaulted data field, not a dispatch requirement. A video
        # draft with no metadata.provider is exactly as valid as a Kling
        # draft with none.
        raise PromoteError(
            "queue draft has no metadata.provider, which is only valid for the "
            f"implicit kling/video default -- --provider {provider!r} was explicitly requested"
        )

    if not queue_draft.get("media_path"):
        raise PromoteError("queue draft is missing media_path")
    media_path = Path(str(queue_draft["media_path"]))
    if not media_path.exists():
        raise PromoteError(f"queue draft media_path does not exist on disk: {media_path}")

    media_type = str(queue_draft.get("media_type") or "").lower().strip()
    if media_type not in {"photo", "image", "story", "stories", "video", "reel"}:
        raise PromoteError(
            f"queue draft media_type {queue_draft.get('media_type')!r} is not supported by this "
            "tool -- only photo/image/story/video/reel queue drafts can be re-validated via the "
            "existing packet resolvers. media_type itself is never rewritten/normalized here -- "
            "read back byte-identical, same as every other field this tool never touches."
        )

    platforms = queue_draft.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise PromoteError(f"queue draft platforms must be a non-empty list, got {platforms!r}")

    if media_type in {"video", "reel"}:
        # Provider-neutral video/Reel required fields (2026-07-11) -- matches
        # exactly what resolve_packet_inputs_video()/build_queue_draft()'s
        # video branch actually produce. Never requires image_engine/
        # image_prompt/activity/pose/visual_style/resolution -- those are
        # the photo/Higgsfield contract, not the video one.
        for required_meta in ("avatar_nickname", "video_prompt"):
            if not metadata.get(required_meta):
                raise PromoteError(f"queue draft metadata is missing required field: {required_meta}")
    else:
        for required_meta in ("avatar_nickname", "image_engine", "image_prompt", "activity", "pose", "visual_style"):
            if not metadata.get(required_meta):
                raise PromoteError(f"queue draft metadata is missing required field: {required_meta}")
        if provider == "higgsfield" and not metadata.get("resolution"):
            raise PromoteError("queue draft metadata is missing required field: resolution")


def _validate_clean_export(queue_draft: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only. Re-derives and re-verifies the clean-export derivative +
    provenance sidecar for the queue draft's raw media_path via
    tools/lena_verify_clean_export_v1.py::verify_clean_export() -- every
    hash is recomputed from the real files on disk, never trusted from the
    sidecar alone. Raises PromoteError (not the lower-level
    CleanExportVerificationError) so promotion has one single error-handling
    surface, matching every other validation step in this module. No bypass
    flag exists; there is no code path that skips this check."""
    media_path = Path(str(queue_draft.get("media_path") or ""))
    try:
        return verify_clean_export(media_path)
    except CleanExportVerificationError as exc:
        raise PromoteError(f"clean-export verification failed: {exc}") from exc


def _apply_clean_export_fields(promoted_item: Dict[str, Any], clean_export_facts: Dict[str, Any]) -> None:
    """Mutates promoted_item in place: points media_path at the verified
    clean derivative and records the raw source separately as provenance
    metadata. Pure field assignment, no I/O, no validation -- callers must
    have already run _validate_clean_export()/verify_clean_export()
    successfully before calling this. Split out from check_promote_to_queue()
    so this exact contract (queue media path == clean derivative; raw
    source preserved only as provenance) is independently unit-testable."""
    promoted_item["media_path"] = clean_export_facts["clean_derivative_path"]
    promoted_item["metadata"]["source_asset_path"] = clean_export_facts["source_path"]
    promoted_item["metadata"]["source_asset_sha256"] = clean_export_facts["source_sha256"]
    promoted_item["metadata"]["clean_export_derivative_sha256"] = clean_export_facts["clean_derivative_sha256"]
    promoted_item["metadata"]["clean_export_sidecar_path"] = clean_export_facts["clean_provenance_sidecar_path"]
    promoted_item["metadata"]["clean_export_verified"] = True
    promoted_item["metadata"]["clean_export_generated_by"] = clean_export_facts["generated_by"]
    promoted_item["metadata"]["clean_export_created_at_utc"] = clean_export_facts["created_at_utc"]


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
    if provider == "video":
        # Provider-neutral video/Reel cross-check (2026-07-11) -- compares
        # against resolve_packet_inputs_video()'s own output shape
        # (video_path, not image_path; video_prompt, not image_engine/
        # image_prompt). image_prompt/provider/video_engine are optional in
        # that resolver's output, so they're only cross-checked when the
        # queue draft actually declares one -- an absent-on-both-sides value
        # is not a mismatch.
        _check("media_path", resolved.get("video_path"), queue_draft.get("media_path"))
        _check("video_prompt", resolved.get("video_prompt"), metadata.get("video_prompt"))
        _check("activity", resolved.get("activity"), metadata.get("activity"))
        _check("pose", resolved.get("pose"), metadata.get("pose"))
        _check("visual_style", resolved.get("visual_style"), metadata.get("visual_style"))
        if metadata.get("image_prompt") or resolved.get("image_prompt"):
            _check("image_prompt", resolved.get("image_prompt"), metadata.get("image_prompt"))
        if metadata.get("provider") or resolved.get("provider"):
            _check("provider", resolved.get("provider"), metadata.get("provider"))
        if metadata.get("video_engine") or resolved.get("video_engine"):
            _check("video_engine", resolved.get("video_engine"), metadata.get("video_engine"))
    elif provider == "higgsfield_derived_shortform":
        # Derived short-form Reel/Story cross-check (2026-07-12) -- compares
        # against resolve_packet_inputs_higgsfield_derived_shortform()'s own
        # output shape. Deliberately compares the queue draft's media_path
        # against the resolved PREPARED VIDEO path, never the source
        # photo's path -- comparing against the photo (what the plain
        # "higgsfield" branch below would do) is the exact category error
        # this dispatch key exists to fix. The generic slot_id check above
        # (outside this if/elif chain) already cross-checks
        # resolved["slot_id"] (the source photo slot) against
        # metadata.source_slot_id, unchanged.
        _check("media_path", resolved.get("prepared_video_path"), queue_draft.get("media_path"))
        _check("prepared_video_sha256", resolved.get("prepared_video_sha256"), metadata.get("prepared_video_sha256"))
        _check("selected_track_id", resolved.get("selected_track_id"), metadata.get("selected_track_id"))
        _check("selected_track_sha256", resolved.get("selected_track_sha256"), metadata.get("selected_track_sha256"))
        _check("source_image_path", resolved.get("source_image_path"), metadata.get("source_image_path"))
        _check("source_image_sha256", resolved.get("source_image_sha256"), metadata.get("source_image_sha256"))
    else:
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

    approval_facts = resolve_approval_execution_bindings(
        date_str,
        slot_id,
        out_dir,
        require_live_publish_authorization=True,
        allow_caption_applied_queue_draft=True,
        error_cls=PromoteError,
    )
    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)

    queue_draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
    queue_draft = _load_json_object(queue_draft_path, "queue draft")
    approval_queue_draft_path = approval_facts["queue_draft_path"]
    if approval_queue_draft_path != str(queue_draft_path):
        raise PromoteError(
            f"approval queue_draft_path {approval_queue_draft_path!r} does not match the exact queue draft path "
            f"{str(queue_draft_path)!r}"
        )
    approval_publish_packet_path = approval_facts["publish_packet_path"]
    _validate_queue_draft(
        queue_draft,
        slot_id,
        provider,
        approval_facts["approved_caption"],
        approval_facts["hashtag_count"],
    )
    metadata = queue_draft.get("metadata") if isinstance(queue_draft.get("metadata"), dict) else {}
    draft_publish_packet_path = metadata.get("publish_packet_path")
    if draft_publish_packet_path != approval_publish_packet_path:
        raise PromoteError(
            f"queue draft metadata.publish_packet_path {draft_publish_packet_path!r} does not match the approval's "
            f"publish_packet_path {approval_publish_packet_path!r}"
        )
    qa_path = metadata.get("qa_path")
    if not isinstance(qa_path, str) or not qa_path:
        raise PromoteError("queue draft metadata.qa_path is missing or empty")
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
        raise PromoteError(str(exc)) from exc

    resolved = _revalidate_with_resolver(date_str, slot_id, provider, queue_draft, out_dir, source_slot_id=source_slot_id)

    clean_export_facts = _validate_clean_export(queue_draft)

    promoted_item = copy.deepcopy(queue_draft)
    promoted_item["approved_for_live_publish"] = True
    promoted_item["operator_review_required"] = False
    promoted_item["metadata"]["queue_draft_only"] = False
    # Clean-export contract (2026-07-11): the queue item's publish media
    # path becomes the verified clean derivative, never the raw source. The
    # raw source is preserved separately as provenance metadata -- see the
    # module docstring for the full invariant this enforces.
    _apply_clean_export_fields(promoted_item, clean_export_facts)

    target_path = resolve_promoted_queue_output_path(slot_id, queue_root)

    already_promoted = False
    would_write = True
    fields_that_would_change: List[str] = list(PROMOTED_STATE_FIELDS) + list(CLEAN_EXPORT_PROMOTED_FIELDS)

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
        "approval_sha256": approval_facts["approval_sha256"],
        "approval_binding_source": approval_facts["approval_binding_source"],
        "approval_correction_artifact_path": approval_facts["approval_correction_artifact_path"],
        "approval_correction_artifact_sha256": approval_facts["approval_correction_artifact_sha256"],
        "queue_draft_path": str(queue_draft_path),
        "queue_draft_sha256": _sha256_file(queue_draft_path),
        "target_queue_path": str(target_path),
        "approved_by": approval_facts["approved_by"],
        "approved_at_utc": approval_facts["approved_at_utc"],
        "approval_statement": approval_facts["approval_statement"],
        "caption_approval_statement": approval_facts["caption_approval_statement"],
        "live_publish_statement": approval_facts["live_publish_statement"],
        "caption_sha256": _sha256_text(approval_facts["approved_caption"]),
        "resolver_qa_overall": resolved.get("qa_overall"),
        "clean_export": clean_export_facts,
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
            "dry-run (writes nothing); --promote performs the one write. Also re-verifies the "
            "clean-export contract (tools/lena_verify_clean_export_v1.py) and, only on success, "
            "points media_path at the verified clean derivative instead of the raw source, "
            "preserving the raw source separately as provenance metadata. Idempotent; fails "
            "closed on any existing, non-identical target, or if clean-export verification "
            "fails."
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
