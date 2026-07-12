from __future__ import annotations

# Lena manual one-off preflight -- a narrow, explicit validation mode for a
# single, genuinely human-approved manual post. Deliberately separate from,
# and never touching, tools/lena_preflight.py: that script's default
# behavior (the automated 3-photo daily-batch scan over the real
# pipeline/queue/ directory) is completely unchanged by this file's
# existence -- this module is never imported by it, and never imports it
# (importing tools/lena_preflight.py would execute its entire top-level
# script body immediately, including its own sys.exit(1) on failure -- it
# is not a library module, so it is never imported here).
#
# This is NOT a generic bypass. There is no --skip-daily-count,
# --ignore-errors, or --force flag anywhere in this module. The only way to
# reach a passing result is to supply real, on-disk, schema-valid evidence
# of an explicit human approval (manual_one_off_confirmed: true on the
# immutable approval artifact, plus every other approval/queue-draft/
# Rule-Zero check already enforced elsewhere in this chain) for EXACTLY one
# named slot. The aggregate 3-photo daily-count requirement is the one and
# only thing this mode omits, and only after every per-item check below has
# already passed -- and the output says so explicitly, every time.
#
# Architecture: reuses (imports, does not duplicate) the approval-artifact
# validation, queue-draft validation, and Rule Zero / provider-resolver
# revalidation already proven in tools/lena_promote_to_queue_v1.py
# (_validate_approval, _validate_queue_draft, _revalidate_with_resolver) --
# the exact same checks a real promotion would run, applied here purely
# read-only. This module adds only the remaining per-item checks
# tools/lena_preflight.py's automated scan also performs but
# lena_promote_to_queue_v1.py does not: avatar_nickname/platforms exact
# match against the real contract, generic-caption-pattern rejection, the
# contract-driven image_engine allow-list, the photo-resolution allow-list,
# and provider identity evidence (Higgsfield: the existing, unmodified
# pipeline.identity.lena_higgsfield_identity.validate_local_identity_evidence();
# Kling: the same inline checks tools/lena_preflight.py performs, duplicated
# here on purpose because lena_preflight.py has no importable function for
# them -- see the module-level comment above for why that script can never
# be imported).
#
# Never writes anything, anywhere, ever -- there is no write function in
# this module at all. Never promotes. Never publishes. Never generates.
# Never calls Higgsfield, Kling, or Anthropic. Never imports
# pipeline.posting_manager, tools.process_queue,
# pipeline.higgsfield_lena_api_executor, pipeline.kling_apilena_api_executor,
# requests, or urllib. Reads (never writes) `.env` only to resolve the same
# KLING_LENA_ELEMENT_* identity env vars tools/lena_preflight.py itself
# reads for Kling identity comparison -- required for Kling per-item
# parity, never touched for Higgsfield.
#
# One narrow, disclosed exception (2026-07-12): pipeline.publisher.
# instagram_queue_bridge is imported for its pure, read-only
# _validate_contract() function only (the "higgsfield_derived_shortform"
# per-item branch uses it to prove the Reel bridge contract would pass).
# That module's own network-capable code
# (instagram_graph_adapter/publish_post) is lazy-loaded via importlib only
# inside publish_post(), never at import time and never called from here --
# importing instagram_queue_bridge does not import requests or reach any
# network-capable code. Still true: nothing in this module ever publishes.
#
# Run:
#   python tools/lena_manual_one_off_preflight_v1.py --date 2026-07-09 --slot readypack0709-pack003-08-photo --provider higgsfield

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.env_loader import load_env_once  # noqa: E402
from pipeline.identity import lena_identity  # noqa: E402
from pipeline.identity import lena_higgsfield_identity  # noqa: E402
from pipeline.publisher import instagram_queue_bridge  # noqa: E402

from tools.lena_verify_clean_export_v1 import (  # noqa: E402
    CleanExportVerificationError,
    verify_clean_export,
)

from tools.lena_promote_to_queue_v1 import (  # noqa: E402
    PROVIDER_RESOLVERS,
    PromoteError,
    _load_json_object,
    _revalidate_with_resolver,
    _validate_approval,
    _validate_queue_draft,
)
from tools.lena_build_publish_packet_v1 import (  # noqa: E402
    resolve_queue_draft_output_path,
)
from tools.lena_record_publish_approval_v1 import (  # noqa: E402
    resolve_approval_output_path,
)

load_env_once(ROOT)

CONTRACT_PATH = ROOT / "pipeline" / "config" / "lena_kling_contract.json"
APILENA_DEBUG_ROOT = ROOT / "pipeline" / "kling_debug" / "apilena_api"

_contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))
_required_specs = _contract["required_media_specs"]
_daily = _contract["daily_autonomy"]
_caption_rules = _contract.get("caption_rules") or _contract.get("caption_quality", {})

REQUIRED_PLATFORM = _daily.get("platforms", ["instagram"])
REQUIRED_AVATAR = _contract["persona"]["required_avatar_nickname"]
IMAGE_ENGINES_BY_PROVIDER = _required_specs["image_engine_by_provider"]
MIN_HASHTAGS = int(_caption_rules.get("min_hashtags", 1))
MAX_HASHTAGS = int(_caption_rules.get("max_hashtags", 3))

# Duplicated from tools/lena_preflight.py on purpose -- that script is a
# top-level script with no importable functions/constants (importing it
# executes its whole body, including its own sys.exit()), so its per-item
# contract values are reproduced here rather than imported. If
# lena_preflight.py's own values ever change, this module must be updated
# to match -- there is no shared source of truth today.
ALLOWED_PHOTO_RESOLUTIONS_BY_PROVIDER = {
    "kling": {"1080p", "1080x1920", "1920x1080"},
    "higgsfield": {"1152x2048"},
}

GENERIC_CAPTION_PATTERNS = [
    "episode 001",
    "episode 002",
    "episode 003",
    "episode 004",
    "episode 005",
    "a little moment worth sharing",
    "check out my new post",
    "new episode",
    "daily vibes",
]


class ManualOneOffPreflightError(Exception):
    """Raised for any hard-fail condition. Never caught silently -- main()
    reports it and exits non-zero. This module never writes a file under
    any condition, pass or fail."""


def _validate_kling_identity_evidence(
    queue_draft: Dict[str, Any],
    date_str: str,
    slot_id: str,
    metadata: Dict[str, Any],
) -> None:
    """Mirrors tools/lena_preflight.py's inline Kling identity-evidence
    block exactly (same fields, same payload-truth verification against
    submit_payload.json/live_apilena_lookup_response.json) -- duplicated,
    not imported, for the reason documented at the top of this module."""
    if str(metadata.get("photo_identity_binding") or "") not in lena_identity.ALLOWED_PHOTO_IDENTITY_BINDINGS:
        raise ManualOneOffPreflightError("photo must be stamped with a validated Lena element binding")
    if str(metadata.get("reference_binding_mode") or "") != lena_identity.REQUIRED_REFERENCE_BINDING_MODE:
        raise ManualOneOffPreflightError(f"photo must use {lena_identity.REQUIRED_REFERENCE_BINDING_MODE} binding mode")
    if str(metadata.get("reference_source_policy") or "") != lena_identity.REQUIRED_REFERENCE_SOURCE_POLICY:
        raise ManualOneOffPreflightError(f"photo must declare {lena_identity.REQUIRED_REFERENCE_SOURCE_POLICY} reference policy")
    if str(metadata.get("reference_source_element_id_source") or "") != lena_identity.REQUIRED_REFERENCE_SOURCE_ELEMENT_ID_SOURCE:
        raise ManualOneOffPreflightError(f"photo must resolve from {lena_identity.REQUIRED_REFERENCE_SOURCE_ELEMENT_ID_SOURCE}")
    if metadata.get("reference_image_path"):
        raise ManualOneOffPreflightError("photo must not carry legacy reference_image_path")
    if str(metadata.get("seed_source") or "") != lena_identity.REQUIRED_SEED_SOURCE:
        raise ManualOneOffPreflightError(f"photo must use {lena_identity.REQUIRED_SEED_SOURCE} seed source")

    actual_photo_element = lena_identity.clean_element_id(metadata.get("lena_element_ui_numeric_id"))
    expected_photo_element = lena_identity.resolve_expected_photo_element()
    if expected_photo_element:
        expected_source, expected_element = expected_photo_element
        if actual_photo_element != expected_element:
            raise ManualOneOffPreflightError(
                f"photo element mismatch, expected {expected_source}={expected_element}, "
                f"got {actual_photo_element or '[missing]'}"
            )
    else:
        raise ManualOneOffPreflightError("no KLING_LENA_* element id found in env for strict comparison")

    forbidden_photo_elements = lena_identity.forbidden_photo_element_ids()
    if actual_photo_element and actual_photo_element in forbidden_photo_elements:
        raise ManualOneOffPreflightError(
            f"photo resolved to forbidden studio element {forbidden_photo_elements[actual_photo_element]}={actual_photo_element}"
        )

    submit_payload_path = APILENA_DEBUG_ROOT / date_str / slot_id / "submit_payload.json"
    lookup_response_path = APILENA_DEBUG_ROOT / date_str / slot_id / "live_apilena_lookup_response.json"
    if submit_payload_path.exists():
        try:
            submit_payload = json.loads(submit_payload_path.read_text(encoding="utf-8-sig"))
        except Exception:
            submit_payload = None
        if submit_payload is not None and submit_payload.get("image_list"):
            raise ManualOneOffPreflightError(
                f"submitted payload contains non-empty image_list, element_list-only "
                f"contract violated: {submit_payload_path}"
            )
        if not lookup_response_path.exists():
            raise ManualOneOffPreflightError(
                f"no live_apilena_lookup_response.json alongside submit_payload.json -- photo "
                f"identity may have bypassed the live element lookup via a manual env "
                f"image-source override: {submit_payload_path}"
            )
    # else: matches lena_preflight.py's own behavior -- a missing
    # submit_payload.json is only a WARN there, never a hard fail; this
    # stricter one-off mode does not upgrade it to a hard fail either, to
    # stay a faithful per-item mirror rather than a new, different gate.


def _validate_derived_shortform_contract_per_item(
    queue_draft: Dict[str, Any],
    resolved: Dict[str, Any],
    date_str: str,
    evidence_slot_id: str,
) -> None:
    """Per-item checks specific to the "higgsfield_derived_shortform"
    provider (2026-07-12) -- a Reel/Story composed locally from an approved
    Higgsfield photo + an approved music track
    (tools/lena_prepare_story_video_v1.py), never a distinct provider
    video-generation call. Reuses every existing validator unchanged;
    duplicates none. Raises ManualOneOffPreflightError on any hard-fail
    condition.

    `resolved` is resolve_packet_inputs_higgsfield_derived_shortform()'s own
    output (already independently re-verified against the real source
    photo and the real prepared short-form asset) -- every identity fact
    used below comes from there, never from the queue draft's own
    self-reported metadata, matching this whole chain's "never trust
    self-reported data alone" discipline."""
    metadata = queue_draft.get("metadata") or {}

    media_type = str(queue_draft.get("media_type") or "").lower().strip()
    if media_type != "reel":
        raise ManualOneOffPreflightError(
            f"higgsfield_derived_shortform provider requires media_type='reel', got {media_type!r}"
        )

    # Identity evidence (2026-07-12): reuses the existing, unmodified
    # lena_higgsfield_identity.validate_local_identity_evidence() -- but
    # against the SOURCE PHOTO's own path and independently-re-resolved
    # identity fields, never the Reel's own media_path/metadata (which
    # describe the derived video, not the photo). This is the exact
    # category-error fix this whole provider key exists for.
    identity_check_meta = {
        "provider_job_id": (resolved.get("debug_artifacts") or {}).get("provider_job_id"),
        "custom_reference_id": resolved.get("custom_reference_id"),
        "image_prompt": resolved.get("image_prompt"),
    }
    reasons = lena_higgsfield_identity.validate_local_identity_evidence(
        date_str, evidence_slot_id, Path(str(resolved["source_image_path"])), identity_check_meta,
    )
    if reasons:
        raise ManualOneOffPreflightError(
            "Higgsfield source-photo identity evidence failed: " + "; ".join(reasons)
        )

    # Clean-export chain (2026-07-12): tools/lena_promote_to_queue_v1.py's
    # own verify_clean_export() re-verification is already reused unmodified
    # at actual PROMOTION time for every provider -- but the manual one-off
    # PREFLIGHT mode has never called it for any provider until now. Reused
    # here, unmodified, so a derived-shortform Reel's preflight result
    # genuinely proves the full chain up to (not including) the live Graph
    # call, not just the pre-promotion subset every other provider's
    # preflight proves.
    media_path = Path(str(queue_draft.get("media_path") or ""))
    try:
        clean_export_facts = verify_clean_export(media_path)
    except CleanExportVerificationError as exc:
        raise ManualOneOffPreflightError(f"clean-export verification failed: {exc}") from exc

    # Reel bridge contract (2026-07-12): proves this item would actually
    # pass pipeline.publisher.instagram_queue_bridge._validate_contract() --
    # reused unmodified, called against the exact promoted-item shape real
    # promotion would produce (media_path -> verified clean derivative,
    # clean-export provenance populated), built entirely in memory here.
    # Nothing is written anywhere by this simulation.
    simulated_promoted = copy.deepcopy(queue_draft)
    simulated_promoted["media_path"] = clean_export_facts["clean_derivative_path"]
    simulated_promoted["metadata"]["source_asset_path"] = clean_export_facts["source_path"]
    simulated_promoted["metadata"]["source_asset_sha256"] = clean_export_facts["source_sha256"]
    simulated_promoted["metadata"]["clean_export_derivative_sha256"] = clean_export_facts["clean_derivative_sha256"]
    simulated_promoted["metadata"]["clean_export_verified"] = True
    try:
        instagram_queue_bridge._validate_contract(simulated_promoted)
    except ValueError as exc:
        raise ManualOneOffPreflightError(f"Reel bridge contract validation failed: {exc}") from exc


def _validate_contract_per_item(
    queue_draft: Dict[str, Any],
    provider: str,
    date_str: str,
    slot_id: str,
    source_slot_id: Optional[str] = None,
    resolved: Optional[Dict[str, Any]] = None,
) -> None:
    """The remaining per-item checks tools/lena_preflight.py's automated
    scan performs that lena_promote_to_queue_v1.py's reused validation does
    not already cover: avatar/platform exact match, generic-caption
    rejection, contract-driven image_engine allow-list, photo-resolution
    allow-list, and provider identity evidence.

    source_slot_id (2026-07-10, optional, explicit-only, default None):
    used ONLY for the two generation-provenance evidence lookups at the
    bottom of this function (Kling's submit_payload.json/
    live_apilena_lookup_response.json, Higgsfield's
    identity_verification.json) -- both are real records of what the
    provider actually did at generation time, filed under the generation
    slot, never the derived queue item's own bookkeeping identity. Falls
    back to slot_id when omitted, matching every other check in this
    function -- byte-identical behavior for every item validated before
    this parameter existed. Every other check above (avatar/platform/
    caption/image_engine/resolution) reads only queue_draft/metadata
    fields, never a slot-keyed file path, so none of them are affected.

    resolved (2026-07-12, optional, default None): only ever populated (by
    check_manual_one_off_preflight()) and only ever read when
    provider == "higgsfield_derived_shortform" -- see the early guard
    immediately below. Every other provider's behavior is completely
    unaffected: this function reaches the exact same, byte-identical code
    it always has for "kling"/"higgsfield"/"video"."""
    effective_evidence_slot_id = source_slot_id or slot_id
    metadata = queue_draft.get("metadata") or {}

    # Generic checks (avatar/platform/caption pattern) apply universally --
    # run for every provider, including "higgsfield_derived_shortform",
    # before any provider-specific branching below.
    if metadata.get("avatar_nickname") != REQUIRED_AVATAR:
        raise ManualOneOffPreflightError(
            f"metadata.avatar_nickname must be {REQUIRED_AVATAR!r}, got {metadata.get('avatar_nickname')!r}"
        )
    if queue_draft.get("platforms") != REQUIRED_PLATFORM:
        raise ManualOneOffPreflightError(
            f"platforms must be {REQUIRED_PLATFORM!r}, got {queue_draft.get('platforms')!r}"
        )

    caption_lower = str(queue_draft.get("caption") or "").lower()
    for pattern in GENERIC_CAPTION_PATTERNS:
        if pattern in caption_lower:
            raise ManualOneOffPreflightError(f"generic/repetitive caption pattern found: {pattern!r}")

    if provider == "higgsfield_derived_shortform":
        if resolved is None:
            raise ManualOneOffPreflightError(
                "higgsfield_derived_shortform provider requires the resolved Rule Zero output -- "
                "internal caller error, not a data problem"
            )
        _validate_derived_shortform_contract_per_item(
            queue_draft, resolved, date_str, effective_evidence_slot_id
        )
        return

    expected_engine = IMAGE_ENGINES_BY_PROVIDER.get(provider)
    if expected_engine is None:
        raise ManualOneOffPreflightError(f"no image_engine mapping for provider {provider!r} in contract")
    if str(metadata.get("image_engine") or "").lower() != expected_engine.lower():
        raise ManualOneOffPreflightError(
            f"metadata.image_engine must be {expected_engine!r} for provider {provider!r}, "
            f"got {metadata.get('image_engine')!r}"
        )

    # Resolution is only ever stamped into a queue draft for Higgsfield --
    # see lena_build_publish_packet_v1.build_queue_draft()'s own comment
    # ("absent entirely for the existing Kling path"). A Kling draft built
    # through this same pipeline has no resolution field to check, matching
    # the identical, pre-existing asymmetry lena_promote_to_queue_v1.py's
    # own required-field list already enforces (resolution required only
    # for higgsfield). Checked when present for either provider; never
    # fabricated when absent.
    resolution = metadata.get("resolution")
    if resolution is not None:
        allowed_resolutions = ALLOWED_PHOTO_RESOLUTIONS_BY_PROVIDER.get(provider, set())
        if str(resolution).lower() not in allowed_resolutions:
            raise ManualOneOffPreflightError(
                f"resolution must be one of {sorted(allowed_resolutions)} for provider "
                f"{provider!r}, got {resolution!r}"
            )
    elif provider == "higgsfield":
        raise ManualOneOffPreflightError("higgsfield queue draft is missing metadata.resolution")

    media_path = Path(str(queue_draft.get("media_path") or ""))
    if provider == "kling":
        _validate_kling_identity_evidence(queue_draft, date_str, effective_evidence_slot_id, metadata)
    elif provider == "higgsfield":
        reasons = lena_higgsfield_identity.validate_local_identity_evidence(
            date_str, effective_evidence_slot_id, media_path, metadata
        )
        if reasons:
            raise ManualOneOffPreflightError("Higgsfield identity evidence failed: " + "; ".join(reasons))


def check_manual_one_off_preflight(
    date_str: str,
    slot_id: str,
    provider: str,
    out_dir: Optional[Path] = None,
    source_slot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only. Raises ManualOneOffPreflightError on any hard-fail
    condition. Never writes a file, under any condition. Validates exactly
    one named item end-to-end (approval, queue draft, Rule Zero / resolver
    revalidation, and every remaining per-item preflight-parity check) and
    deliberately never evaluates the aggregate daily-count requirements.

    source_slot_id (2026-07-10, optional, explicit-only, default None):
    forwarded to _revalidate_with_resolver() (Rule Zero) AND to
    _validate_contract_per_item() (Kling/Higgsfield generation-provenance
    identity evidence) unchanged -- see their docstrings. Defaults to
    slot_id in both; every item validated before this parameter existed is
    unaffected. approval_path/queue_draft_path and every other identity
    check in this function remain keyed by slot_id (the queue item's own
    bookkeeping identity), never source_slot_id."""
    if "," in slot_id or ";" in slot_id:
        raise ManualOneOffPreflightError(
            f"exactly one slot_id is required; ambiguous multi-slot input is not supported: {slot_id!r}"
        )
    if not provider or provider not in PROVIDER_RESOLVERS:
        raise ManualOneOffPreflightError(
            f"unknown provider {provider!r} -- must be one of {sorted(PROVIDER_RESOLVERS)} "
            "(fails closed, never auto-detected)"
        )

    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)
    try:
        approval = _load_json_object(approval_path, "approval artifact")
        approval_facts = _validate_approval(approval, date_str, slot_id)
    except PromoteError as exc:
        raise ManualOneOffPreflightError(str(exc)) from exc

    if approval.get("manual_one_off_confirmed") is not True:
        raise ManualOneOffPreflightError(
            "approval's manual_one_off_confirmed is not exactly true -- this mode requires "
            "explicit, positive proof of a genuine manual one-off approval, not merely its absence"
        )

    queue_draft_path = resolve_queue_draft_output_path(date_str, slot_id, out_dir)
    try:
        queue_draft = _load_json_object(queue_draft_path, "queue draft")
        _validate_queue_draft(
            queue_draft, slot_id, provider, approval_facts["approved_caption"], approval_facts["hashtag_count"],
        )
    except PromoteError as exc:
        raise ManualOneOffPreflightError(str(exc)) from exc

    try:
        resolved = _revalidate_with_resolver(
            date_str, slot_id, provider, queue_draft, out_dir, source_slot_id=source_slot_id
        )
    except PromoteError as exc:
        raise ManualOneOffPreflightError(str(exc)) from exc

    _validate_contract_per_item(
        queue_draft, provider, date_str, slot_id, source_slot_id=source_slot_id, resolved=resolved,
    )

    return {
        "ok": True,
        "mode": "manual_one_off",
        "date": date_str,
        "slot_id": slot_id,
        "provider": provider,
        "manual_one_off_confirmed": True,
        "approved_by": approval_facts["approved_by"],
        "approved_at_utc": approval_facts["approved_at_utc"],
        "approval_statement": approval_facts["approval_statement"],
        "hashtag_count": approval_facts["hashtag_count"],
        "resolver_qa_overall": resolved.get("qa_overall"),
        "per_item_checks": "all passed",
        "daily_batch_requirements_evaluated": False,
        "daily_batch_requirements_skipped_reason": (
            "explicit human-approved one-off (manual_one_off_confirmed=true on the immutable "
            "approval artifact) -- this validates exactly one item, not the aggregate daily batch"
        ),
        "not_a_complete_daily_batch": True,
        "note": (
            "This is a single-item manual one-off validation, not a daily-batch readiness result. "
            "It does not imply photos_per_day/videos_per_day requirements are met, and it does not "
            "promote or publish anything."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validates exactly one explicitly human-approved Lena manual one-off post -- every "
            "approval/queue-draft/Rule-Zero/per-item check the automated daily-batch preflight "
            "would run, minus only the aggregate 3-photo daily-count requirement. Requires real, "
            "on-disk proof of manual_one_off_confirmed:true; there is no generic bypass flag. "
            "Never writes anything. tools/lena_preflight.py's own default behavior is completely "
            "unaffected by this tool's existence."
        )
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", required=True, dest="slot_id", help="exact, single slot_id")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_RESOLVERS),
        default="kling",
        help="Explicit provider selector (default: kling). Never auto-detected.",
    )
    parser.add_argument("--out-dir", default=None, help="Override the packet/queue-draft/approval output base directory.")
    parser.add_argument(
        "--source-slot",
        default=None,
        dest="source_slot_id",
        help=(
            "Optional, explicit-only override for the identity used to call the Rule Zero "
            "provider resolver. Defaults to --slot when omitted. Only needed when --slot "
            "deliberately differs from the real generation slot it was rendered from."
        ),
    )
    args = parser.parse_args()

    out_dir: Optional[Path] = None
    if args.out_dir:
        candidate = Path(args.out_dir)
        out_dir = candidate if candidate.is_absolute() else (ROOT / candidate)

    try:
        result = check_manual_one_off_preflight(
            args.date, args.slot_id, args.provider, out_dir, source_slot_id=args.source_slot_id
        )
    except ManualOneOffPreflightError as exc:
        print(json.dumps(
            {
                "ok": False,
                "mode": "manual_one_off",
                "error": str(exc),
                "date": args.date,
                "slot_id": args.slot_id,
                "daily_batch_requirements_evaluated": False,
            },
            indent=2,
        ))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
