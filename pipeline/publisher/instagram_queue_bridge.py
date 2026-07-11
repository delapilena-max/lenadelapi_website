from __future__ import annotations

import json
import os
import shutil
import subprocess
import importlib
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

from pipeline.env_loader import load_env_once

load_env_once()

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "pipeline" / "config" / "lena_kling_contract.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_verify_clean_export_v1 import (  # noqa: E402
    CleanExportVerificationError,
    verify_clean_export,
)

# Instagram's own documented feed-photo aspect-ratio range (width/height),
# per Meta's Content Publishing API reference
# (developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)
# and corroborated by third-party integrators: 4:5 (portrait) to 1.91:1
# (landscape); square (1:1) is within range. An image outside this range is
# unsafe to submit as a feed photo -- 2026-07-10's readypack0709-pack003-08-photo
# live publish (1152x2048, 9:16 = 0.5625, ~2-3% headroom above the head) is the
# real, confirmed incident this gate exists to prevent: the source image itself
# was not defective, but its aspect ratio was far outside this range with no
# margin to survive Instagram's own presentation, and the head was cut off.
MIN_FEED_PHOTO_ASPECT_RATIO = 0.8
MAX_FEED_PHOTO_ASPECT_RATIO = 1.91

# Reel duration ceiling -- provider-neutral policy owner (2026-07-11).
# Deliberately None. The historical 7-second value this replaces
# (pipeline/config/lena_kling_contract.json's max_video_duration_seconds)
# was a Kling clip-length artifact, never a confirmed real Instagram Reels
# duration policy -- keeping it would have wrongly rejected any genuine
# Reel-length video. No real Instagram Reels duration limit is encoded
# here: picking one requires explicit, separately-authorized confirmation
# of Meta's actual current policy, not a guess made inside this change.
# Until that number is confirmed and set here, duration is still measured
# and required to be a valid, readable value (see the video branch below)
# -- just not upper-bounded. Set to a real integer only once authorized.
INSTAGRAM_REEL_MAX_DURATION_SECONDS: Optional[float] = None


def _duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        ).strip()
        return float(out)
    except Exception:
        return None


def _validate_static_image_engine_and_prompt(meta: Dict[str, Any], specs: Dict[str, Any], media_type_label: str) -> None:
    """Provider-aware image-engine dispatch + image_prompt presence check,
    shared by any static-image media type (feed photo and Story). Never
    touches aspect ratio -- that stays the sole responsibility of the
    feed-photo branch in _validate_contract(). Same default/fail-closed
    dispatch pattern tools/lena_preflight.py already established: an item
    with no metadata.provider predates this field and defaults to "kling"
    for backward compatibility; an explicit but unrecognized provider value
    is a hard fail, never a silent fallback to Kling; provider is never
    inferred from image_engine or auto-detected any other way."""
    image_engines_by_provider = specs.get("image_engine_by_provider") or {}
    provider_raw = meta.get("provider")
    provider = str(provider_raw).lower().strip() if provider_raw else "kling"
    if provider not in image_engines_by_provider:
        raise ValueError(
            f"Lena contract violation: unsupported/unrecognized metadata.provider {provider_raw!r} -- "
            "no image_engine mapping for this provider, refusing to silently fall back to Kling"
        )
    expected_engine = image_engines_by_provider[provider]
    if str(meta.get("image_engine") or "").lower() != str(expected_engine).lower():
        raise ValueError(
            f"Lena contract violation: {media_type_label} must use {expected_engine} for provider {provider!r}"
        )
    if not meta.get("image_prompt"):
        raise ValueError(f"Lena contract violation: {media_type_label} missing image_prompt")


def _validate_downstream_clean_export(payload: Dict[str, Any]) -> None:
    """Fail-closed downstream clean-export gate (2026-07-11). Runs before
    any media-type-specific branch in _validate_contract(), for every media
    type -- clean-export is a universal outward-publishing requirement, not
    a photo-only or Story-only one.

    Does NOT merely trust metadata.clean_export_verified:true as a claim.
    Independently re-verifies, right now, against the real files on disk,
    by calling the exact same tools/lena_verify_clean_export_v1.py::
    verify_clean_export() the promotion step already uses -- every hash is
    recomputed fresh here, never carried over from promotion time. This
    catches both tampering (the clean derivative file was modified after
    promotion) and staleness (the metadata claims are stale/wrong), not
    just absence.

    Also independently confirms the queue item's actual media_path equals
    the freshly-recomputed clean derivative path -- this is what prevents
    "metadata claims clean but media_path points elsewhere" from ever
    reaching a provider/upload call.

    Raises ValueError (this module's existing contract-violation exception
    shape -- no new exception type introduced) on any hard-fail condition.
    There is no code path in this function that falls back to the raw
    source; a failure here always means "do not publish this payload",
    never "publish the raw source instead"."""
    meta = payload.get("metadata") or {}

    if meta.get("clean_export_verified") is not True:
        raise ValueError(
            "Lena contract violation: metadata.clean_export_verified is not the literal "
            f"boolean true (got {meta.get('clean_export_verified')!r}) -- refusing to publish"
        )

    source_asset_path_raw = meta.get("source_asset_path")
    if not source_asset_path_raw:
        raise ValueError(
            "Lena contract violation: metadata.source_asset_path is missing -- cannot "
            "independently re-verify the clean-export contract"
        )
    source_asset_path = Path(str(source_asset_path_raw))

    media_path_raw = payload.get("media_path")
    if not media_path_raw:
        raise ValueError("Lena contract violation: media_path is missing")
    queued_media_path = Path(str(media_path_raw)).resolve()

    # Independent, fresh re-verification against the real files on disk.
    # verify_clean_export() itself already enforces: source exists, media
    # type supported, derivative path != source path, derivative exists,
    # sidecar exists/parses, sidecar source_sha256/output_sha256 match the
    # recomputed hashes, verified_clean_after_scrub is literal true. No
    # part of this is re-implemented here -- reusing the one existing gate
    # rather than duplicating its logic.
    try:
        facts = verify_clean_export(source_asset_path)
    except CleanExportVerificationError as exc:
        raise ValueError(
            f"Lena contract violation: downstream clean-export re-verification failed: {exc}"
        ) from exc

    if Path(facts["clean_derivative_path"]).resolve() != queued_media_path:
        raise ValueError(
            "Lena contract violation: queue media_path does not equal the independently "
            f"re-verified clean derivative path (media_path={queued_media_path}, "
            f"re-verified derivative={facts['clean_derivative_path']}) -- refusing, no "
            "fallback to the raw source"
        )

    # Cross-check the queue item's own recorded claims against the fresh
    # re-verification -- catches metadata that was correct at promotion
    # time but has since gone stale or been tampered with, even in cases
    # where the files on disk right now would otherwise still pass
    # verify_clean_export() on their own.
    stored_source_sha256 = meta.get("source_asset_sha256")
    if stored_source_sha256 and stored_source_sha256 != facts["source_sha256"]:
        raise ValueError(
            "Lena contract violation: metadata.source_asset_sha256 "
            f"{stored_source_sha256!r} does not match the recomputed source hash "
            f"{facts['source_sha256']!r}"
        )
    stored_derivative_sha256 = meta.get("clean_export_derivative_sha256")
    if stored_derivative_sha256 and stored_derivative_sha256 != facts["clean_derivative_sha256"]:
        raise ValueError(
            "Lena contract violation: metadata.clean_export_derivative_sha256 "
            f"{stored_derivative_sha256!r} does not match the recomputed derivative hash "
            f"{facts['clean_derivative_sha256']!r}"
        )


def _validate_contract(payload: Dict[str, Any]) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))
    specs = contract["required_media_specs"]
    caption_rules = contract.get("caption_rules") or contract.get("caption_quality") or {}

    platforms = payload.get("platforms")
    if platforms != ["instagram"]:
        raise ValueError(f"Lena contract violation: platforms must be ['instagram'], got {platforms}")

    media_path = Path(str(payload.get("media_path") or ""))
    if not media_path.exists():
        raise ValueError(f"Lena contract violation: media_path missing: {media_path}")

    # Fail-closed clean-export gate (2026-07-11) -- universal across every
    # media type, runs before any type-specific branch below and before any
    # media-staging/upload/Graph API call happens anywhere downstream of
    # this function. See _validate_downstream_clean_export()'s own
    # docstring for exactly what it independently re-verifies and why.
    _validate_downstream_clean_export(payload)

    caption = str(payload.get("caption") or "")
    hashtag_count = len(re.findall(r"(?<!\\w)#[A-Za-z0-9_]+", caption))
    min_hashtags = int(caption_rules.get("min_hashtags", 5))
    max_hashtags = int(caption_rules.get("max_hashtags", 9))
    if hashtag_count < min_hashtags or hashtag_count > max_hashtags:
        raise ValueError(f"Lena contract violation: caption must contain {min_hashtags}-{max_hashtags} hashtags")

    meta = payload.get("metadata") or {}
    if meta.get("avatar_nickname") != "Lena":
        raise ValueError("Lena contract violation: metadata.avatar_nickname must be Lena")

    media_type = str(payload.get("media_type") or "").lower()

    if media_type in {"photo", "image"}:
        _validate_static_image_engine_and_prompt(meta, specs, "photo")

        # Instagram-safe aspect-ratio gate (2026-07-10, added after a real live
        # incident -- see the MIN/MAX_FEED_PHOTO_ASPECT_RATIO constants' comment
        # above). Deliberately reads the ACTUAL image file's real pixel
        # dimensions via PIL, never metadata.resolution alone -- metadata is
        # self-reported and, for Kling items built through this pipeline's own
        # queue-draft builder, is not even always present (see
        # lena_build_publish_packet_v1.build_queue_draft()'s own documented
        # asymmetry). Only ever reads the file; never resizes, crops, converts,
        # or otherwise modifies it -- this is a validation gate, not a
        # transformation. Fails closed if the image can't be opened at all
        # (corrupt/unreadable/missing file), same as every other check in this
        # function.
        try:
            with Image.open(media_path) as im:
                img_width, img_height = im.size
        except Exception as exc:
            raise ValueError(f"Lena contract violation: could not read image dimensions from {media_path}: {exc}")
        if img_width <= 0 or img_height <= 0:
            raise ValueError(f"Lena contract violation: photo has invalid dimensions {img_width}x{img_height}")
        aspect_ratio = img_width / img_height
        if not (MIN_FEED_PHOTO_ASPECT_RATIO <= aspect_ratio <= MAX_FEED_PHOTO_ASPECT_RATIO):
            raise ValueError(
                f"Lena contract violation: photo dimensions {img_width}x{img_height} (aspect ratio "
                f"{aspect_ratio:.4f}) are outside Instagram's accepted feed-photo range "
                f"({MIN_FEED_PHOTO_ASPECT_RATIO}-{MAX_FEED_PHOTO_ASPECT_RATIO}) -- unsafe to publish, "
                "Instagram may crop or reject this image"
            )
        return

    if media_type in {"story", "stories"}:
        # Instagram Story-safe static-image contract (2026-07-10): a
        # separate, explicit branch -- not a broad exception layered onto
        # the feed-photo branch above -- so the feed aspect-ratio gate can
        # never be accidentally bypassed for a payload that is actually a
        # feed photo. Reuses the identical provider-aware engine/image_prompt
        # checks the feed-photo branch uses, but deliberately never applies
        # MIN_FEED_PHOTO_ASPECT_RATIO/MAX_FEED_PHOTO_ASPECT_RATIO: Instagram
        # Stories natively accept the existing, unmodified 9:16 Lena asset --
        # that range exists specifically for feed IMAGE posts, not Stories.
        # No resize/crop/convert/mutation of any kind; media_path existence
        # is already checked above, shared across every media type.
        _validate_static_image_engine_and_prompt(meta, specs, "story")
        return

    if media_type in {"video", "reel"}:
        # Provider-neutral video/Reel contract (2026-07-11) -- replaces the
        # legacy Kling-coupled branch. Requires only fields the current,
        # provider-neutral Rule Zero video resolver
        # (tools/lena_build_publish_packet_v1.py::resolve_packet_inputs_video())
        # actually produces. avatar_nickname is already checked above,
        # universally, for every media type -- not re-checked here.
        #
        # Deliberately does NOT require seed_image_path, seed_image_engine,
        # video_engine, motion_control, fps, or a specific resolution
        # string. None of those are produced by the current canonical
        # resolver; requiring them would silently resurrect a dependency on
        # a historical, disconnected video mechanism this contract never
        # actually validated real code against (confirmed by direct
        # read-only audit: build_queue_draft() never set any of those
        # fields for any provider).
        if not meta.get("video_prompt"):
            raise ValueError("Lena contract violation: video missing video_prompt")

        dur = _duration(media_path)
        if dur is None:
            raise ValueError("Lena contract violation: could not verify video duration")
        if INSTAGRAM_REEL_MAX_DURATION_SECONDS is not None and dur > INSTAGRAM_REEL_MAX_DURATION_SECONDS:
            raise ValueError(
                f"Lena contract violation: video duration {dur:.2f}s exceeds the "
                f"configured Reel policy ceiling of {INSTAGRAM_REEL_MAX_DURATION_SECONDS}s"
            )
        return

    raise ValueError(f"Lena contract violation: unsupported media_type={media_type!r}")


def validate_post_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    _validate_contract(payload)
    return {
        "ok": True,
        "platforms": payload.get("platforms"),
        "media_type": str(payload.get("media_type", "")).lower().strip(),
        "media_path": str(payload.get("media_path") or ""),
    }


def _graph_route_available() -> bool:
    return bool(
        (os.environ.get("INSTAGRAM_GRAPH_ACCESS_TOKEN") or os.environ.get("META_INSTAGRAM_ACCESS_TOKEN"))
        and (os.environ.get("INSTAGRAM_GRAPH_USER_ID") or os.environ.get("META_IG_USER_ID"))
    )


def _load_adapter(module_name: str):
    return importlib.import_module(module_name)


def publish_post(payload: Dict[str, Any]) -> Dict[str, Any]:
    _validate_contract(payload)

    if _graph_route_available():
        graph_adapter = _load_adapter("pipeline.publisher.instagram_graph_adapter")
        result = graph_adapter.publish_post(payload)
        return {
            "ok": True,
            "backend": "instagram_graph",
            "route": "graph_api",
            "kind": str(payload.get("media_type") or "").lower().strip(),
            "post_id": payload.get("post_id"),
            "instagram_result": result,
        }

    instagram_adapter = _load_adapter("pipeline.publisher.instagram_adapter")
    media_path = Path(str(payload["media_path"]))
    media_type = str(payload.get("media_type", "")).lower().strip()
    caption = str(payload.get("caption") or "")

    if media_type in {"photo", "image", "jpg", "jpeg", "png"}:
        result = instagram_adapter.publish_feed_photo(media_path, caption)
        return {
            "ok": True,
            "backend": "instagram",
            "kind": "photo",
            "post_id": payload.get("post_id"),
            "instagram_result": result,
        }

    result = instagram_adapter.publish_reel(media_path, caption)
    return {
        "ok": True,
        "backend": "instagram",
        "kind": "reel",
        "post_id": payload.get("post_id"),
        "instagram_result": result,
    }
