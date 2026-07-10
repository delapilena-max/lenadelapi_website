from __future__ import annotations

# Lena publish-packet builder -- Batch 3 (optional queue-draft JSON emission).
#
# Design doc: pipeline/agents/lena/90_content_packet/{AGENT,RULES,INPUTS,OUTPUTS}.md.
# Batches 1 (read-only resolver) and 2 (Markdown packet writing, non-clobber) are
# unchanged below. Batch 3 adds: an OPTIONAL --queue-draft flag that, only when
# passed, also writes a queue-shaped JSON draft alongside the Markdown packet --
# never to pipeline/queue/, always with approved_for_live_publish: false, always
# with a placeholder caption (never an auto-selected one).
#
# Still has no --live/--approve flag of any kind. --queue-draft only ever writes a
# draft file under the packet output directory (default pipeline/publish_packets/
# lena/), never the live queue directory that tools/process_queue.py/
# pipeline/posting_manager.py actually scan. A hard guard (_assert_not_inside_live_queue)
# resolves the intended queue-draft path and aborts -- writing NOTHING, including the
# Markdown packet -- if that path would land inside or equal pipeline/queue/, catching
# --out-dir pipeline/queue, --out-dir pipeline/queue/anything, and equivalent relative
# paths. See RULES.md's "must never do" list and "what must hard-fail" list.
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
# Never imports pipeline.env_loader (does not read .env). Never imports
# pipeline.posting_manager, tools.process_queue, pipeline.kling_apilena_api_executor,
# requests, or urllib -- this module cannot publish, queue, or call any network/API
# surface, by construction, not just by convention.

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Used only to measure the real, actual pixel dimensions of an already-saved
# Higgsfield image (no manifest field currently records this -- see
# resolve_packet_inputs_higgsfield() below). Never used to generate,
# transform, or re-save an image.
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from pipeline.qa import lena_photo_qa  # noqa: E402

# Reused, not reimplemented: the Higgsfield-aware resolver below builds on
# the same manifest-loading/image-resolution helpers the existing Higgsfield
# QA bridge already uses, so slot/manifest/image resolution logic for
# Higgsfield lives in exactly one place. Aliased to avoid confusion with
# this module's own ResolveError (same name, different module/meaning) --
# every bridge-raised error is re-raised as *this* module's ResolveError so
# callers only ever need to catch one exception type.
from lena_higgsfield_qa_bridge_v1 import (  # noqa: E402
    _manifest_path as _higgsfield_manifest_path,
    _load_manifest as _load_higgsfield_manifest,
    _resolve_image_path as _resolve_higgsfield_image_path,
    ResolveError as _HiggsfieldBridgeResolveError,
)

WORKORDER_ROOT = ROOT / "pipeline" / "kling_workorders"
APILENA_DEBUG_ROOT = ROOT / "pipeline" / "kling_debug" / "apilena_api"
DEFAULT_PUBLISH_PACKET_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"
LIVE_QUEUE_ROOT = ROOT / "pipeline" / "queue"

MAX_HASHTAGS_PER_CAPTION = 3
QUEUE_DRAFT_CAPTION_PLACEHOLDER = (
    "<PLACEHOLDER -- operator must choose a final caption from the publish "
    "packet before moving this into the live queue>"
)


class ResolveError(Exception):
    """Raised for any hard-fail condition in slot/QA resolution. Never caught
    silently -- main() reports it and exits non-zero. No file is ever written
    before or after this is raised."""


class PacketWriteError(Exception):
    """Raised for a hard-fail condition when writing the packet (e.g. the
    packet already exists and --force was not supplied). No file is written
    when this is raised."""


class QueueDraftGuardError(Exception):
    """Raised if the resolved queue-draft output path would land inside (or
    equal) the live pipeline/queue/ directory. Checked BEFORE any file is
    written this run -- including the Markdown packet -- so a bad --out-dir
    aborts the whole run with zero writes, not just the queue-draft part."""


class QueueDraftWriteError(Exception):
    """Raised for a hard-fail condition when writing the queue draft (e.g.
    it already exists and --force was not supplied). No file is written when
    this is raised."""


# --- Batch 1: read-only resolution (unchanged) ------------------------------

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


def resolve_packet_output_path(date_str: str, slot_id: str, out_dir: Optional[Path] = None) -> Path:
    base = out_dir if out_dir is not None else DEFAULT_PUBLISH_PACKET_ROOT
    return base / date_str / f"LENA_PUBLISH_PACKET_{slot_id}.md"


def resolve_packet_inputs(date_str: str, slot_id: str, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only. Raises ResolveError on any hard-fail condition. Writes nothing,
    ever -- no QA scaffold, no packet, no queue draft."""
    manifest = _load_daily_manifest(date_str)
    slot = _resolve_slot(manifest, slot_id)
    image_path = _resolve_image_path(slot)
    qa_result = _resolve_qa(date_str, slot_id)
    debug_artifacts = _resolve_optional_debug_artifacts(date_str, slot_id)

    metadata = slot.get("metadata") if isinstance(slot.get("metadata"), dict) else {}
    production_scoring = qa_result.get("production_scoring") or {}
    intended_packet_path = resolve_packet_output_path(date_str, slot_id, out_dir)

    # Contract fields required by instagram_queue_bridge._validate_contract() at
    # actual live-publish time. Sourced only from the real workorder slot's own
    # metadata -- never invented. A missing field here means the workorder itself
    # is incomplete, which is a hard-fail, not something to paper over with a
    # fabricated default (that would let a queue draft look valid while carrying
    # wrong/placeholder contract data all the way to the live publish attempt).
    avatar_nickname = metadata.get("avatar_nickname")
    if not avatar_nickname:
        raise ResolveError(
            f"slot '{slot_id}' metadata is missing avatar_nickname -- refusing to "
            "fabricate a value. Fix the workorder, don't patch the queue draft."
        )
    image_engine = metadata.get("image_engine")
    if not image_engine:
        raise ResolveError(
            f"slot '{slot_id}' metadata is missing image_engine -- refusing to "
            "fabricate a value. Fix the workorder, don't patch the queue draft."
        )
    image_prompt = metadata.get("image_prompt")
    if not image_prompt:
        raise ResolveError(
            f"slot '{slot_id}' metadata is missing image_prompt -- refusing to "
            "fabricate a value. Fix the workorder, don't patch the queue draft."
        )

    return {
        "date": date_str,
        "slot_id": slot_id,
        "image_path": str(image_path),
        "qa_path": str(lena_photo_qa.qa_artifact_path(date_str, slot_id)),
        "qa_overall": qa_result.get("overall"),
        "qa_publish_ready": qa_result.get("publish_ready"),
        "qa_publish_ready_reason": qa_result.get("publish_ready_reason"),
        "qa_hook_strength": production_scoring.get("hook_strength", {}).get("score"),
        "qa_styling_sexy_platform_safe": production_scoring.get("styling_sexy_platform_safe", {}).get("status"),
        "workorder_caption": slot.get("caption"),
        "wardrobe_outfit_id": metadata.get("wardrobe_outfit_id"),
        "wardrobe_outfit_name": metadata.get("wardrobe_outfit_name"),
        "environment_id": metadata.get("environment_id"),
        "environment_name": metadata.get("environment_name"),
        "lane": metadata.get("lane"),
        "activity": slot.get("activity") or metadata.get("activity"),
        "pose": slot.get("pose") or metadata.get("pose"),
        # Real Kling workorder slots already carry a genuine visual_style
        # value (pipeline/prompting/lena_prompt_brain.py's workorder-building
        # code sets both slot["visual_style"] and metadata["visual_style"]
        # from the package's own f"{camera}; {lighting}" value) -- this was
        # simply never read here before. Not a new/derived value.
        "visual_style": slot.get("visual_style") or metadata.get("visual_style"),
        "reference_binding_mode": metadata.get("reference_binding_mode"),
        "avatar_nickname": avatar_nickname,
        "image_engine": image_engine,
        "image_prompt": image_prompt,
        "debug_artifacts": debug_artifacts,
        "intended_packet_output_path": str(intended_packet_path),
        "intended_packet_output_already_exists": intended_packet_path.exists(),
        "files_written_this_run": [],
    }


# --- Batch 4: Higgsfield-aware resolver (read-only, reuses Rule Zero) -------
#
# This is the ONLY Higgsfield-specific addition. It does not duplicate QA
# gating (Rule zero) -- it calls the existing, unmodified _resolve_qa() --
# and does not duplicate manifest/image resolution -- it reuses
# lena_higgsfield_qa_bridge_v1.py's own helpers. Everything downstream
# (caption assembly, Markdown packet, optional queue-draft JSON, the live-
# queue guard) is the same provider-agnostic code the Kling path already
# uses, fed from the same generic `resolved` dict shape produced above.
#
# Fails closed (raises ResolveError, this module's own exception type -- a
# bridge-raised error is caught and re-raised as this type so callers only
# ever handle one exception) on: missing/unparseable/non-object manifest,
# a manifest whose own `slot_id` field does not exactly match the requested
# slot_id (never trusts a mismatched manifest), a missing/non-existent saved
# image, missing required provider/job/prompt metadata, or any Rule Zero
# failure (missing/invalid/inconsistent QA, or overall != "pass"). Never
# falls back to the Kling resolver for any reason.

def _resolve_higgsfield_visual_style(manifest: Dict[str, Any], date_str: str, slot_id: str) -> Optional[str]:
    """Read-only, local-only (no network, no provider call). Returns a real,
    non-fabricated visual_style string (f"{camera_text}; {lighting_text}",
    matching the Kling package builder's own convention), or None if no
    truthful source exists. Preferred source order, no other fallback:

    1. camera_text/lighting_text persisted directly in the manifest (renders
       generated after 2026-07-10, once pipeline/higgsfield_lena_api_executor.py's
       build_manifest() started persisting them).
    2. For historical renders only, a local visual_style_verification.json
       evidence file at pipeline/higgsfield_debug/<date>/<slot_id>/ --
       independently re-validated here, never trusted blindly: provider,
       date, and slot_id must match; the evidence's own
       original_prompt_sha256 must match THIS manifest's real prompt_sha256
       (ties the evidence to this exact render, not just a file that
       happens to sit at the expected path); regenerated_prompt_sha256 must
       equal original_prompt_sha256; prompt_hash_match must be True;
       verification_result must be "pass".

    No lane-based inference, no prompt-string parsing, no generic default --
    returns None (never a fabricated value) if neither source is valid."""
    camera_text = manifest.get("camera_text")
    lighting_text = manifest.get("lighting_text")
    if camera_text and lighting_text:
        return f"{camera_text}; {lighting_text}"

    evidence_path = ROOT / "pipeline" / "higgsfield_debug" / date_str / slot_id / "visual_style_verification.json"
    if not evidence_path.exists():
        return None
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(evidence, dict):
        return None

    if evidence.get("provider") != "higgsfield":
        return None
    if evidence.get("date") != date_str:
        return None
    if evidence.get("slot_id") != slot_id:
        return None
    if evidence.get("original_prompt_sha256") != manifest.get("prompt_sha256"):
        return None
    if evidence.get("regenerated_prompt_sha256") != evidence.get("original_prompt_sha256"):
        return None
    if evidence.get("prompt_hash_match") is not True:
        return None
    if evidence.get("verification_result") != "pass":
        return None

    evidence_camera_text = evidence.get("camera_text")
    evidence_lighting_text = evidence.get("lighting_text")
    if not evidence_camera_text or not evidence_lighting_text:
        return None

    return f"{evidence_camera_text}; {evidence_lighting_text}"


def resolve_packet_inputs_higgsfield(date_str: str, slot_id: str, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only. Higgsfield counterpart to resolve_packet_inputs(). Raises
    ResolveError on any hard-fail condition. Writes nothing, ever."""
    try:
        manifest = _load_higgsfield_manifest(date_str, slot_id)
    except _HiggsfieldBridgeResolveError as exc:
        raise ResolveError(str(exc)) from exc

    manifest_slot_id = manifest.get("slot_id")
    if manifest_slot_id != slot_id:
        raise ResolveError(
            f"Higgsfield manifest slot_id {manifest_slot_id!r} does not match requested "
            f"slot_id {slot_id!r} -- refusing to tie a mismatched manifest to this slot"
        )

    try:
        image_path = _resolve_higgsfield_image_path(manifest)
    except _HiggsfieldBridgeResolveError as exc:
        raise ResolveError(str(exc)) from exc

    # Required provider/job/prompt metadata -- sourced only from the real
    # manifest, same "fix the source, don't fabricate a value" discipline
    # the Kling resolver above already uses for avatar_nickname/image_engine/
    # image_prompt.
    provider = manifest.get("provider")
    if not provider:
        raise ResolveError(
            f"Higgsfield manifest for slot '{slot_id}' is missing 'provider' -- "
            "refusing to fabricate a value."
        )
    job_type = manifest.get("job_type")
    if not job_type:
        raise ResolveError(
            f"Higgsfield manifest for slot '{slot_id}' is missing 'job_type' -- "
            "refusing to fabricate a value."
        )
    cli_soul_name = manifest.get("cli_soul_name")
    if not cli_soul_name:
        raise ResolveError(
            f"Higgsfield manifest for slot '{slot_id}' is missing 'cli_soul_name' -- "
            "refusing to fabricate a value."
        )
    image_prompt = manifest.get("image_prompt")
    if not image_prompt:
        raise ResolveError(
            f"Higgsfield manifest for slot '{slot_id}' is missing 'image_prompt' -- "
            "refusing to fabricate a value."
        )
    custom_reference_id = manifest.get("custom_reference_id")
    if not custom_reference_id:
        raise ResolveError(
            f"Higgsfield manifest for slot '{slot_id}' is missing 'custom_reference_id' -- "
            "refusing to fabricate a value."
        )

    # Rule zero -- the existing, unmodified gate. Not duplicated here.
    qa_result = _resolve_qa(date_str, slot_id)

    production_scoring = qa_result.get("production_scoring") or {}
    intended_packet_path = resolve_packet_output_path(date_str, slot_id, out_dir)

    # Deterministic, non-fabricated image_engine value derived from the two
    # real fields above -- never a Kling-compatible-looking value.
    image_engine = f"higgsfield_{job_type}"

    # The manifest itself carries no width/height/resolution field (only
    # 'aspect_ratio', e.g. "9:16") -- measured directly from the real saved
    # image file instead of guessing from aspect_ratio, and never labeled as
    # a Kling resolution string (e.g. "1080x1920").
    try:
        with Image.open(image_path) as im:
            actual_width, actual_height = im.size
    except Exception as exc:
        raise ResolveError(
            f"could not read real pixel dimensions from {image_path}: {exc}"
        ) from exc
    resolution = f"{actual_width}x{actual_height}"

    debug_artifacts = {
        # Deliberately named distinctly from the Kling resolver's
        # result_manifest_path/result_manifest_task_id -- provider_job_id is
        # a real Higgsfield field, never presented as a Kling task_id.
        "higgsfield_manifest_path": str(_higgsfield_manifest_path(date_str, slot_id)),
        "higgsfield_manifest_exists": True,
        "provider_job_id": manifest.get("provider_job_id"),
        "provider_status": manifest.get("provider_status"),
    }

    return {
        "date": date_str,
        "slot_id": slot_id,
        "provider": "higgsfield",
        "image_path": str(image_path),
        "qa_path": str(lena_photo_qa.qa_artifact_path(date_str, slot_id)),
        "qa_overall": qa_result.get("overall"),
        "qa_publish_ready": qa_result.get("publish_ready"),
        "qa_publish_ready_reason": qa_result.get("publish_ready_reason"),
        "qa_hook_strength": production_scoring.get("hook_strength", {}).get("score"),
        "qa_styling_sexy_platform_safe": production_scoring.get("styling_sexy_platform_safe", {}).get("status"),
        # Higgsfield's manifest carries no operator-authored caption field --
        # left None (known gap, matches the QA bridge's own doctrine), never
        # invented. build_caption_options() already handles an empty/missing
        # base caption gracefully.
        "workorder_caption": manifest.get("workorder_caption"),
        "wardrobe_outfit_id": manifest.get("wardrobe_outfit_id"),
        "wardrobe_outfit_name": manifest.get("wardrobe_outfit_name"),
        # Higgsfield's manifest has no environment_id/environment_name field
        # (it has 'lane' instead) -- left None, same disclosed gap
        # lena_higgsfield_qa_bridge_v1.py's own known_gaps already documents.
        "environment_id": manifest.get("environment_id"),
        "environment_name": manifest.get("environment_name"),
        "lane": manifest.get("lane"),
        # There is no separate manifest "activity" field for Higgsfield --
        # pipeline/prompting/lena_prompt_brain.py's own
        # generate_higgsfield_prompt_package() (and its Kling counterpart)
        # already define activity as literally equal to the scene's lane
        # (`"activity": scene["lane"]`), it just never reaches the saved
        # manifest. Forwarding the manifest's real 'lane' value here matches
        # that existing, already-established equivalence -- not a new or
        # invented concept.
        "activity": manifest.get("lane"),
        "pose": manifest.get("pose_text"),
        "visual_style": _resolve_higgsfield_visual_style(manifest, date_str, slot_id),
        "reference_binding_mode": manifest.get("reference_binding_mode"),
        "avatar_nickname": cli_soul_name,
        "image_engine": image_engine,
        "image_prompt": image_prompt,
        "custom_reference_id": custom_reference_id,
        "resolution": resolution,
        "debug_artifacts": debug_artifacts,
        "intended_packet_output_path": str(intended_packet_path),
        "intended_packet_output_already_exists": intended_packet_path.exists(),
        "files_written_this_run": [],
    }


# --- Batch 2: caption-option assembly ----------------------------------------

def _split_workorder_caption(raw_caption: Optional[str]) -> Tuple[str, List[str]]:
    """Split a workorder caption (e.g. 'text\\n\\n#a #b #c') into (base_text,
    hashtags). Hashtags are capped at MAX_HASHTAGS_PER_CAPTION. Pure function,
    no I/O."""
    if not raw_caption:
        return "", []
    lines = str(raw_caption).splitlines()
    hashtags: List[str] = []
    body_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if all(tok.startswith("#") for tok in tokens):
            hashtags.extend(tok for tok in tokens if tok.startswith("#"))
        else:
            body_lines.append(stripped)
    return " ".join(body_lines).strip(), hashtags[:MAX_HASHTAGS_PER_CAPTION]


def _format_caption(base_text: str, hashtags: List[str]) -> str:
    tags = " ".join(hashtags[:MAX_HASHTAGS_PER_CAPTION])
    if tags:
        return f"{base_text}\n\n{tags}" if base_text else tags
    return base_text


def build_caption_options(resolved: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Deterministic, mechanical caption-option drafts grounded in the
    workorder's own caption and scene metadata. These are NOT creative
    copywriting -- no LLM/generation call is made here. Always label them as
    drafts the operator must review/edit, per RULES.md (never auto-select a
    caption). Returns 3-5 (label, text) pairs, each <=3 hashtags."""
    base_text, hashtags = _split_workorder_caption(resolved.get("workorder_caption"))
    lane = resolved.get("lane")
    wardrobe_name = resolved.get("wardrobe_outfit_name")
    environment_name = resolved.get("environment_name")

    options: List[Tuple[str, str]] = [
        ("Option A (workorder original)", _format_caption(base_text, hashtags)),
    ]

    if base_text and "." in base_text:
        shortened = base_text.split(".")[0].strip()
        if shortened and shortened != base_text:
            options.append(("Option B (shortened)", _format_caption(shortened, hashtags)))

    if lane:
        lane_text = f"{base_text} ({lane})" if base_text else str(lane)
        options.append(("Option C (lane-anchored)", _format_caption(lane_text, hashtags)))

    if wardrobe_name:
        wardrobe_text = f"{base_text} -- wearing {wardrobe_name}" if base_text else f"wearing {wardrobe_name}"
        options.append(("Option D (wardrobe-anchored)", _format_caption(wardrobe_text, hashtags)))

    if environment_name:
        env_text = f"{environment_name}. {base_text}" if base_text else str(environment_name)
        options.append(("Option E (scene-anchored)", _format_caption(env_text, hashtags)))

    while len(options) < 3:
        filler_label = f"Option {chr(65 + len(options))} (base)"
        options.append((filler_label, _format_caption(base_text, hashtags)))

    return options[:5]


# --- Batch 2: Markdown packet assembly ---------------------------------------

def build_packet_markdown(resolved: Dict[str, Any]) -> str:
    date_str = resolved["date"]
    slot_id = resolved["slot_id"]
    caption_options = build_caption_options(resolved)

    lines: List[str] = []

    # 1. Header
    lines.append(f"# Lena Publish Packet -- {slot_id}")
    lines.append("")
    lines.append(
        "**Status:** DRAFT / operator review required. **This packet does not "
        "approve or publish anything.** Nothing has been posted, scheduled, or "
        "queued. Manual approval only -- no auto-posting."
    )
    lines.append(
        f"**Prepared:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
        f"(auto-generated draft via `tools/lena_build_publish_packet_v1.py` -- "
        "caption/CTA/poll/pin text below are mechanical drafts, not final "
        "copy; review and edit before use)."
    )
    lines.append(
        f"**Slot:** `{slot_id}` -- **Date:** `{date_str}`."
    )
    lines.append("")

    # 2. Image
    lines.append("## 1. Image")
    lines.append("")
    lines.append(f"- **Path:** `{resolved['image_path']}`")
    lines.append(f"- **Lane / scene:** {resolved.get('lane') or 'unknown'}")
    if resolved.get("activity"):
        lines.append(f"- **Activity:** {resolved['activity']}")
    if resolved.get("pose"):
        lines.append(f"- **Pose:** {resolved['pose']}")
    if resolved.get("wardrobe_outfit_name") or resolved.get("wardrobe_outfit_id"):
        lines.append(
            f"- **Wardrobe:** {resolved.get('wardrobe_outfit_name') or 'unknown'} "
            f"(`{resolved.get('wardrobe_outfit_id') or 'unknown'}`)"
        )
    if resolved.get("environment_name") or resolved.get("environment_id"):
        lines.append(
            f"- **Environment:** {resolved.get('environment_name') or 'unknown'} "
            f"(`{resolved.get('environment_id') or 'unknown'}`)"
        )
    debug = resolved.get("debug_artifacts") or {}
    if debug.get("result_manifest_task_id"):
        lines.append(f"- **Source Kling task id:** `{debug['result_manifest_task_id']}`")
    if resolved.get("reference_binding_mode"):
        lines.append(f"- **Reference binding mode:** `{resolved['reference_binding_mode']}`")
    lines.append("")

    # 3. QA summary
    lines.append("## 2. QA summary")
    lines.append("")
    lines.append(f"- **Source:** `{resolved['qa_path']}`")
    lines.append(f"- **QA overall:** `{resolved.get('qa_overall')}`")
    lines.append(f"- **Hook strength:** `{resolved.get('qa_hook_strength')}`")
    lines.append(
        f"- **Styling sexy/platform-safe:** `{resolved.get('qa_styling_sexy_platform_safe')}`"
    )
    lines.append(f"- **QA `publish_ready`:** `{resolved.get('qa_publish_ready')}`")
    if resolved.get("qa_publish_ready_reason"):
        lines.append(f"- **`publish_ready_reason`:** {resolved['qa_publish_ready_reason']}")
    lines.append(
        "- **`publish_ready` in QA is a quality verdict, NOT a publish "
        "authorization.** Publishing still needs explicit operator sign-off "
        "(image + caption)."
    )
    lines.append("")

    # 4. Caption options
    lines.append(f"## 3. Caption options (auto-drafted, pick one; each <= {MAX_HASHTAGS_PER_CAPTION} hashtags)")
    lines.append("")
    for label, text in caption_options:
        lines.append(f"**{label}**")
        for text_line in text.splitlines():
            lines.append(f"> {text_line}" if text_line else ">")
        lines.append("")

    # 5. Soft CTA
    lines.append("## 4. Soft CTA (draft -- edit before use)")
    lines.append("")
    lines.append("> tell me what you think 👀")
    lines.append("")

    # 6. Story poll idea (optional)
    lines.append("## 5. Story poll idea (optional, draft)")
    lines.append("")
    lines.append('> Sticker poll over the image: **"love this or not?"**')
    lines.append("> Options: `🔥 love it` / `🤔 not sure`")
    lines.append("")

    # 7. Pinned comment idea (optional)
    lines.append("## 6. Pinned comment idea (optional, draft)")
    lines.append("")
    lines.append('> "okay this one might be my favorite 👀"')
    lines.append("")

    # 8. Platform notes
    lines.append("## 7. Platform notes")
    lines.append("")
    lines.append("**Instagram (primary)**")
    lines.append("- Crop as needed for feed vs. Reels/Story.")
    lines.append(f"- Hashtags kept to {MAX_HASHTAGS_PER_CAPTION}, in-caption or first comment.")
    lines.append("")
    lines.append("**Other platforms**")
    lines.append("- Review and adapt caption tone per platform before posting elsewhere.")
    lines.append("")

    # 9. Final operator approval checklist
    lines.append("## 8. Final operator approval checklist")
    lines.append("")
    lines.append("Nothing publishes until every box is deliberately checked by the operator:")
    lines.append("")
    lines.append("- [ ] Image approved -- identity + quality acceptable to post.")
    lines.append("- [ ] Platform-safety confirmed against the real QA verdict above.")
    lines.append("- [ ] Caption chosen and edited (auto-drafts above are starting points, not final copy).")
    lines.append(f"- [ ] Hashtags reviewed (<= {MAX_HASHTAGS_PER_CAPTION}, on-brand).")
    lines.append("- [ ] CTA / Story poll / pinned comment chosen or edited.")
    lines.append("- [ ] Platform(s) + crop chosen.")
    lines.append("- [ ] Post time chosen.")
    lines.append("- [ ] **Explicit \"approved to publish\" given by the operator.**")
    lines.append("- [ ] Confirmed this is a manual, one-off controlled post -- not batch, not scheduled, not auto.")
    lines.append("")

    # 10. Notes
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- This packet was auto-generated by `tools/lena_build_publish_packet_v1.py` "
        "from the real workorder and QA artifacts for this slot. Caption/CTA/poll/pin "
        "text are mechanical drafts, not creative copywriting -- review and rewrite "
        "before use."
    )
    lines.append(
        "- This packet does not set any queue or publish state. No `.env`, no "
        "scheduler, no batch, no auto-approve, no network/API call was involved in "
        "producing this file."
    )
    lines.append("")

    return "\n".join(lines)


def write_packet(resolved: Dict[str, Any], out_dir: Optional[Path], force: bool) -> Path:
    output_path = resolve_packet_output_path(resolved["date"], resolved["slot_id"], out_dir)
    if output_path.exists() and not force:
        raise PacketWriteError(
            f"packet already exists at {output_path} -- pass --force to overwrite "
            "this exact file (non-clobber default)"
        )
    if output_path.exists() and output_path.is_dir():
        raise PacketWriteError(f"refusing to write: {output_path} is a directory, not a file")

    markdown = build_packet_markdown(resolved)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


# --- Batch 3: optional queue-draft JSON emission -----------------------------

def resolve_queue_draft_output_path(date_str: str, slot_id: str, out_dir: Optional[Path] = None) -> Path:
    base = out_dir if out_dir is not None else DEFAULT_PUBLISH_PACKET_ROOT
    return base / date_str / f"{slot_id}_queue_draft.json"


def _assert_not_inside_live_queue(path: Path) -> None:
    """Hard guard: refuse to proceed if the resolved path is the live
    pipeline/queue/ directory itself or anything inside it. Catches
    --out-dir pipeline/queue, --out-dir pipeline/queue/anything, and
    equivalent relative paths, by resolving both sides to absolute paths
    before comparing. Raises before any file is written."""
    resolved_target = path.resolve()
    live_queue = LIVE_QUEUE_ROOT.resolve()
    if resolved_target == live_queue or live_queue in resolved_target.parents:
        raise QueueDraftGuardError(
            f"refusing to proceed: resolved path {resolved_target} is inside or equal to "
            f"the live queue directory {live_queue}. This tool must never write into "
            "pipeline/queue/ -- choose a different --out-dir."
        )


def build_queue_draft(resolved: Dict[str, Any], packet_output_path: Path) -> Dict[str, Any]:
    """Pure function, no I/O. Builds the queue-shaped draft dict. Always
    approved_for_live_publish: false, always a placeholder caption -- never
    an auto-selected one (RULES.md: never auto-select a caption)."""
    debug_artifacts = resolved.get("debug_artifacts") or {}
    metadata: Dict[str, Any] = {
        # Contract fields required by instagram_queue_bridge._validate_contract()
        # at live-publish time. resolve_packet_inputs() already hard-fails if any
        # of these are missing from the real workorder slot, so they are always
        # present here -- never a fabricated default.
        "avatar_nickname": resolved["avatar_nickname"],
        "image_engine": resolved["image_engine"],
        "image_prompt": resolved["image_prompt"],
        "publish_packet_path": str(packet_output_path),
        "qa_path": resolved.get("qa_path"),
        "qa_overall": resolved.get("qa_overall"),
        "source_date": resolved.get("date"),
        "source_slot_id": resolved.get("slot_id"),
        "generated_by": "tools/lena_build_publish_packet_v1.py",
        "queue_draft_only": True,
    }
    if debug_artifacts.get("result_manifest_task_id"):
        metadata["source_task_id"] = debug_artifacts["result_manifest_task_id"]
    if resolved.get("wardrobe_outfit_id"):
        metadata["wardrobe_outfit_id"] = resolved["wardrobe_outfit_id"]
    if resolved.get("reference_binding_mode"):
        metadata["reference_binding_mode"] = resolved["reference_binding_mode"]
    # Provider-agnostic enrichment forwarding (2026-07-10): both resolvers
    # already carry real activity/pose/visual_style values in `resolved`
    # (Kling: from the real workorder slot's own metadata; Higgsfield: from
    # the manifest's 'lane'/'pose_text', and visual_style from either the
    # manifest's own camera_text/lighting_text or a validated historical
    # visual_style_verification.json -- see
    # _resolve_higgsfield_visual_style()) -- this was simply never copied
    # into the queue draft's metadata before now. No fabricated default:
    # absent entirely if `resolved` doesn't have a real value.
    if resolved.get("activity"):
        metadata["activity"] = resolved["activity"]
    if resolved.get("pose"):
        metadata["pose"] = resolved["pose"]
    if resolved.get("visual_style"):
        metadata["visual_style"] = resolved["visual_style"]
    # Conditional, additive-only: absent entirely for the existing Kling path
    # (resolve_packet_inputs() never sets resolved["provider"]/
    # ["custom_reference_id"]/["resolution"], and debug_artifacts there never
    # carries "provider_job_id"), so a Kling-built draft is byte-identical to
    # before this change. Present, truthfully, only for a Higgsfield-built
    # draft -- never a fabricated or Kling-relabeled value.
    if resolved.get("provider"):
        metadata["provider"] = resolved["provider"]
    if debug_artifacts.get("provider_job_id"):
        metadata["provider_job_id"] = debug_artifacts["provider_job_id"]
    if resolved.get("custom_reference_id"):
        metadata["custom_reference_id"] = resolved["custom_reference_id"]
    if resolved.get("resolution"):
        metadata["resolution"] = resolved["resolution"]

    return {
        "post_id": resolved["slot_id"],
        # tools/lena_preflight.py resolves an item's identity via
        # `data.get("slot_id") or path.stem` -- for Kling this "just worked"
        # by convention only, because Kling queue-item filenames happen to be
        # date-prefixed to match slot_id exactly. Higgsfield slot IDs (e.g.
        # "readypack0709-pack003-08-photo") don't follow that filename
        # convention, so path.stem would resolve to the wrong identity and
        # preflight's Higgsfield identity-evidence lookup would look in the
        # wrong pipeline/higgsfield_debug/<date>/<slot_id>/ directory
        # entirely. Writing the real, exact slot_id explicitly here (not
        # derived from any filename, not a fallback, not post_id reused
        # under a different key) makes preflight resolve the correct
        # identity for either provider without relying on that filename
        # coincidence.
        "slot_id": resolved["slot_id"],
        "media_path": resolved["image_path"],
        "media_type": "photo",
        "platforms": ["instagram"],
        "caption": QUEUE_DRAFT_CAPTION_PLACEHOLDER,
        "approved_for_live_publish": False,
        "operator_review_required": True,
        "metadata": metadata,
    }


def write_queue_draft(
    resolved: Dict[str, Any],
    packet_output_path: Path,
    out_dir: Optional[Path],
    force: bool,
) -> Path:
    output_path = resolve_queue_draft_output_path(resolved["date"], resolved["slot_id"], out_dir)
    _assert_not_inside_live_queue(output_path)

    if output_path.exists() and not force:
        raise QueueDraftWriteError(
            f"queue draft already exists at {output_path} -- pass --force to overwrite "
            "this exact file (non-clobber default)"
        )
    if output_path.exists() and output_path.is_dir():
        raise QueueDraftWriteError(f"refusing to write: {output_path} is a directory, not a file")

    draft = build_queue_draft(resolved, packet_output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Batch 3: resolve a Lena slot's real artifacts and write the "
            "publish-packet Markdown draft, and optionally a queue-draft JSON. "
            "Never writes to pipeline/queue/, never sets any approval/publish "
            "state, never calls Kling/any API."
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
            "compatibility). Never auto-detected from whichever manifest happens "
            "to exist, and never falls back across providers -- an invalid value "
            "is rejected by argparse itself."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Override the publish-packet output base directory (default: pipeline/publish_packets/lena).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing packet/queue-draft file at its exact resolved output path. Never touches a directory.",
    )
    parser.add_argument(
        "--queue-draft",
        action="store_true",
        help=(
            "Also write a queue-shaped draft JSON alongside the Markdown packet. "
            "Never written to pipeline/queue/; placeholder caption; "
            "approved_for_live_publish always false."
        ),
    )
    args = parser.parse_args()

    out_dir: Optional[Path] = None
    if args.out_dir:
        candidate = Path(args.out_dir)
        out_dir = candidate if candidate.is_absolute() else (ROOT / candidate)

    # Guard check happens BEFORE any write this run (including the Markdown
    # packet) whenever --queue-draft is requested, so a bad --out-dir aborts
    # the whole run with zero files written anywhere, not just the queue-draft
    # part.
    if args.queue_draft:
        intended_queue_draft_path = resolve_queue_draft_output_path(args.date, args.slot_id, out_dir)
        try:
            _assert_not_inside_live_queue(intended_queue_draft_path)
        except QueueDraftGuardError as exc:
            print(json.dumps({"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id}, indent=2))
            return 1

    resolver = resolve_packet_inputs_higgsfield if args.provider == "higgsfield" else resolve_packet_inputs
    try:
        resolved = resolver(args.date, args.slot_id, out_dir)
    except ResolveError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id}, indent=2))
        return 1

    try:
        output_path = write_packet(resolved, out_dir, args.force)
    except PacketWriteError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "date": args.date, "slot_id": args.slot_id}, indent=2))
        return 1

    files_written = [str(output_path)]

    if args.queue_draft:
        try:
            queue_draft_path = write_queue_draft(resolved, output_path, out_dir, args.force)
        except (QueueDraftGuardError, QueueDraftWriteError) as exc:
            resolved["files_written_this_run"] = files_written
            print(json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "date": args.date,
                    "slot_id": args.slot_id,
                    "resolved": resolved,
                },
                indent=2,
            ))
            return 1
        files_written.append(str(queue_draft_path))

    resolved["files_written_this_run"] = files_written
    print(json.dumps({"ok": True, "resolved": resolved}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
