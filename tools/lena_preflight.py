from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

VIDEO_DURATION_TOLERANCE_SECONDS = 0.75

ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.env_loader import load_env_once
from pipeline.identity import lena_identity
from pipeline.identity import lena_higgsfield_identity

load_env_once(ROOT)

QUEUE = ROOT / "pipeline" / "queue"
WORKORDER_ROOT = ROOT / "pipeline" / "kling_workorders"
CONTRACT_PATH = ROOT / "pipeline" / "config" / "lena_kling_contract.json"
APILENA_DEBUG_ROOT = ROOT / "pipeline" / "kling_debug" / "apilena_api"
PREFLIGHT_DATE = os.environ.get("LENA_PREFLIGHT_DATE") or date.today().isoformat()

contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))

required_specs = contract["required_media_specs"]
daily = contract["daily_autonomy"]
caption_rules = contract.get("caption_rules", {})
if not caption_rules:
    caption_rules = contract.get("caption_quality", {})

REQUIRED_PLATFORM = daily.get("platforms", ["instagram"])
REQUIRED_AVATAR = contract["persona"]["required_avatar_nickname"]
# Provider-aware image-engine map (2026-07-10): "image_engine" stays
# unchanged for backward compatibility with pipeline/publisher/
# instagram_queue_bridge.py's own separate, still-Kling-only contract check
# (out of scope for this change) -- IMAGE_ENGINES_BY_PROVIDER is the new,
# additive key this script reads instead. A queue item with no
# metadata.provider defaults to "kling" (existing items predate this
# field); an explicit but unrecognized provider value is a hard fail, never
# a silent fallback to Kling.
IMAGE_ENGINES_BY_PROVIDER = required_specs["image_engine_by_provider"]
# Photo-resolution allow-list, now per provider. Kling's set is unchanged.
# Higgsfield's is the one real, measured resolution this pipeline has
# actually verified so far (see pipeline/identity/lena_higgsfield_identity.py's
# EXPECTED_WIDTH/EXPECTED_HEIGHT) -- never relabeled as a Kling resolution
# string.
ALLOWED_PHOTO_RESOLUTIONS_BY_PROVIDER = {
    "kling": {"1080p", "1080x1920", "1920x1080"},
    "higgsfield": {"1152x2048"},
}
IMAGE_ENGINE = required_specs["image_engine"]
VIDEO_ENGINE = required_specs["video_engine"]
VIDEO_RESOLUTION = required_specs["video_resolution"]
VIDEO_FPS = int(required_specs["video_fps"])
MAX_VIDEO_SECONDS = int(required_specs["max_video_duration_seconds"])
OPTIONAL_VIDEO_AUTONOMY_ENABLED = os.environ.get("LENA_AUTONOMOUS_INCLUDE_OPTIONAL_VIDEO", "").lower() in {"1", "true", "yes"}
SKIP_OPTIONAL_VIDEO_VALIDATION = int(daily.get("videos_per_day", 0) or 0) == 0 and not OPTIONAL_VIDEO_AUTONOMY_ENABLED

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

bad = []
warn = []


def load_workorder_slot(slot_id: str) -> dict:
    manifest_path = WORKORDER_ROOT / PREFLIGHT_DATE / "daily_workorders.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    for slot in manifest.get("slots", []):
        if slot.get("slot_id") == slot_id:
            return slot
    return {}


def video_duration_seconds(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None

    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        ).strip()
        return float(out)
    except Exception:
        return None


def require(condition: bool, message: str) -> None:
    if not condition:
        bad.append(message)


photo_count = 0
video_count = 0

for path in sorted(QUEUE.glob(f"{PREFLIGHT_DATE}-*.json")):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    meta = data.get("metadata") or {}
    slot_id = data.get("slot_id") or path.stem
    workorder_slot = load_workorder_slot(slot_id)
    workorder_meta = workorder_slot.get("metadata") or {}
    expected_assets = workorder_slot.get("expected_assets") or {}

    media_type = str(data.get("media_type") or "").lower().strip()
    media_path_raw = data.get("media_path")
    platforms = data.get("platforms")
    caption = str(data.get("caption") or "")

    if media_type in {"video", "reel"} and SKIP_OPTIONAL_VIDEO_VALIDATION:
        warn.append(f"{path.name}: optional video ignored in photo-baseline autonomy mode")
        continue

    require(platforms == REQUIRED_PLATFORM, f"{path.name}: platforms must be {REQUIRED_PLATFORM}, got {platforms}")

    if not media_path_raw:
        bad.append(f"{path.name}: missing media_path")
        continue

    media_path = Path(str(media_path_raw))
    require(media_path.exists(), f"{path.name}: media_path does not exist: {media_path}")

    require(meta.get("avatar_nickname") == REQUIRED_AVATAR, f"{path.name}: metadata.avatar_nickname must be {REQUIRED_AVATAR}")

    for required_meta in ["activity", "pose", "visual_style"]:
        require(bool(meta.get(required_meta)), f"{path.name}: missing metadata.{required_meta}")

    lowered_caption = caption.lower()
    for pattern in GENERIC_CAPTION_PATTERNS:
        require(pattern not in lowered_caption, f"{path.name}: generic/repetitive caption pattern found: {pattern!r}")

    hashtag_count = len(re.findall(r"(?<!\\w)#[A-Za-z0-9_]+", caption))
    require(hashtag_count >= int(caption_rules.get("min_hashtags", 5)), f"{path.name}: too few hashtags: {hashtag_count}")
    require(hashtag_count <= int(caption_rules.get("max_hashtags", 9)), f"{path.name}: too many hashtags: {hashtag_count}")

    if media_type in {"photo", "image"}:
        photo_count += 1

        # Provider dispatch (2026-07-10): an item with no metadata.provider
        # predates this field and continues to behave exactly as before --
        # defaults to "kling". An explicit but unrecognized provider value
        # is a hard fail, never a silent fallback to Kling or anywhere else.
        item_provider_raw = meta.get("provider")
        item_provider = str(item_provider_raw).lower().strip() if item_provider_raw else "kling"
        if item_provider not in IMAGE_ENGINES_BY_PROVIDER:
            bad.append(
                f"{path.name}: unsupported/unrecognized metadata.provider {item_provider_raw!r} -- "
                "no image_engine mapping for this provider, refusing to silently fall back to Kling"
            )

        expected_engine = IMAGE_ENGINES_BY_PROVIDER.get(item_provider)
        require(
            expected_engine is not None
            and str(meta.get("image_engine") or "").lower() == expected_engine.lower(),
            f"{path.name}: photo must use {expected_engine or '<no mapping for provider ' + repr(item_provider) + '>'} "
            f"(provider={item_provider!r})",
        )
        require(bool(meta.get("image_prompt")), f"{path.name}: photo missing metadata.image_prompt")
        allowed_resolutions = ALLOWED_PHOTO_RESOLUTIONS_BY_PROVIDER.get(item_provider, set())
        require(
            str(meta.get("resolution") or "").lower() in allowed_resolutions,
            f"{path.name}: photo resolution must be one of {sorted(allowed_resolutions)} "
            f"for provider {item_provider!r}",
        )

        if item_provider == "kling":
            require(
                str(meta.get("photo_identity_binding") or "") in lena_identity.ALLOWED_PHOTO_IDENTITY_BINDINGS,
                f"{path.name}: photo must be stamped with a validated Lena element binding",
            )
            require(
                str(meta.get("reference_binding_mode") or "") == lena_identity.REQUIRED_REFERENCE_BINDING_MODE,
                f"{path.name}: photo must use {lena_identity.REQUIRED_REFERENCE_BINDING_MODE} binding mode",
            )
            require(
                str(meta.get("reference_source_policy") or "") == lena_identity.REQUIRED_REFERENCE_SOURCE_POLICY,
                f"{path.name}: photo must declare {lena_identity.REQUIRED_REFERENCE_SOURCE_POLICY} reference policy",
            )
            require(
                str(meta.get("reference_source_element_id_source") or "") == lena_identity.REQUIRED_REFERENCE_SOURCE_ELEMENT_ID_SOURCE,
                f"{path.name}: photo must resolve from {lena_identity.REQUIRED_REFERENCE_SOURCE_ELEMENT_ID_SOURCE}",
            )
            require(
                not meta.get("reference_image_path"),
                f"{path.name}: photo must not carry legacy reference_image_path",
            )
            require(
                str(meta.get("seed_source") or "") == lena_identity.REQUIRED_SEED_SOURCE,
                f"{path.name}: photo must use {lena_identity.REQUIRED_SEED_SOURCE} seed source",
            )

            actual_photo_element = lena_identity.clean_element_id(meta.get("lena_element_ui_numeric_id"))
            expected_photo_element = lena_identity.resolve_expected_photo_element()
            if expected_photo_element:
                expected_source, expected_element = expected_photo_element
                require(
                    actual_photo_element == expected_element,
                    f"{path.name}: photo element mismatch, expected {expected_source}={expected_element}, got {actual_photo_element or '[missing]'}",
                )
            else:
                warn.append(f"{path.name}: no KLING_LENA_* element id found in env for strict comparison")

            forbidden_photo_elements = lena_identity.forbidden_photo_element_ids()
            if actual_photo_element and actual_photo_element in forbidden_photo_elements:
                require(
                    False,
                    f"{path.name}: photo resolved to forbidden studio element {forbidden_photo_elements[actual_photo_element]}={actual_photo_element}",
                )

            # Payload-truth verification: check what was actually submitted, not just
            # the self-reported metadata stamps above. See containment memo 2026-07-05.
            submit_payload_path = APILENA_DEBUG_ROOT / PREFLIGHT_DATE / slot_id / "submit_payload.json"
            lookup_response_path = APILENA_DEBUG_ROOT / PREFLIGHT_DATE / slot_id / "live_apilena_lookup_response.json"
            if submit_payload_path.exists():
                try:
                    submit_payload = json.loads(submit_payload_path.read_text(encoding="utf-8-sig"))
                except Exception:
                    submit_payload = None
                if submit_payload is not None:
                    require(
                        not submit_payload.get("image_list"),
                        f"{path.name}: submitted payload contains non-empty image_list, "
                        f"element_list-only contract violated: {submit_payload_path}",
                    )
                require(
                    lookup_response_path.exists(),
                    f"{path.name}: no live_apilena_lookup_response.json alongside submit_payload.json "
                    f"-- photo identity may have bypassed the live element lookup via a manual "
                    f"env image-source override: {submit_payload_path}",
                )
            else:
                warn.append(
                    f"{path.name}: no submit_payload.json found for payload-truth verification "
                    f"at {submit_payload_path}; metadata claims above are unverified"
                )

        elif item_provider == "higgsfield":
            # LOCAL ONLY -- no live Higgsfield provider call happens here or
            # anywhere else in this script. Reads the durable evidence file
            # a separate, earlier, explicitly-approved step
            # (verify_and_record_higgsfield_identity()) already wrote.
            higgsfield_identity_reasons = lena_higgsfield_identity.validate_local_identity_evidence(
                PREFLIGHT_DATE, slot_id, media_path, meta
            )
            for reason in higgsfield_identity_reasons:
                bad.append(f"{path.name}: {reason}")

    elif media_type in {"video", "reel"}:
        video_count += 1

        seed_image_path = (
            meta.get("seed_image_path")
            or expected_assets.get("seed_image_path")
            or workorder_meta.get("seed_image_path")
        )
        require(bool(seed_image_path), f"{path.name}: video missing seed image path")

        if seed_image_path:
            seed_path = Path(str(seed_image_path))
            require(seed_path.exists(), f"{path.name}: seed image path does not exist: {seed_path}")

        video_prompt = meta.get("video_prompt") or workorder_slot.get("video_prompt") or workorder_meta.get("video_prompt")
        image_prompt = meta.get("image_prompt") or workorder_slot.get("image_prompt") or workorder_meta.get("image_prompt")

        require(bool(image_prompt), f"{path.name}: video missing image prompt used for seed image")
        require(bool(video_prompt), f"{path.name}: video missing video prompt")

        motion_requested = meta.get("motion_control_requested")
        if motion_requested is None:
            motion_requested = workorder_meta.get("motion_control_requested")
        require(motion_requested is True, f"{path.name}: metadata.motion_control_requested must be true")

        if meta.get("motion_control") is not True:
            warn.append(f"{path.name}: true Motion Control not confirmed; current route is direct image2video")

        require(str(meta.get("resolution") or workorder_meta.get("resolution") or "").lower() in {"1080p", "1080x1920", "1920x1080"}, f"{path.name}: video resolution must be {VIDEO_RESOLUTION}")

        fps_value = meta.get("fps") or meta.get("video_fps") or workorder_meta.get("fps") or workorder_meta.get("video_fps")
        if fps_value is not None:
            require(int(fps_value or 0) == VIDEO_FPS, f"{path.name}: video fps must be {VIDEO_FPS}")
        else:
            warn.append(f"{path.name}: video fps metadata missing; duration will still be verified with ffprobe")

        actual_video_engine = str(meta.get("video_engine") or meta.get("video_model_name") or "").lower()
        if actual_video_engine and actual_video_engine != VIDEO_ENGINE:
            warn.append(f"{path.name}: video engine metadata is {actual_video_engine!r}; contract target is {VIDEO_ENGINE!r}")

        dur = video_duration_seconds(media_path)
        require(dur is not None, f"{path.name}: could not verify video duration with ffprobe")
        if dur is not None:
            require(dur <= (MAX_VIDEO_SECONDS + VIDEO_DURATION_TOLERANCE_SECONDS), f"{path.name}: video duration {dur:.2f}s exceeds {MAX_VIDEO_SECONDS}s plus tolerance")

    else:
        bad.append(f"{path.name}: unsupported media_type={media_type!r}")


print("LENA PREFLIGHT - CONTRACT ENFORCED")
required_photos = int(daily.get("photos_per_day", 0) or 0)
required_videos = int(daily.get("videos_per_day", 0) or 0)
max_videos = int(daily.get("videos_per_day_max", required_videos) or 0)
no_video_sub_for_photos = bool(daily.get("no_video_substitution_for_photos", False))

require(
    photo_count >= required_photos,
    f"daily queue incomplete: requires at least {required_photos} photo items, found {photo_count}",
)
require(
    video_count <= max_videos,
    f"daily queue invalid: allows at most {max_videos} video items, found {video_count}",
)
if required_videos > 0:
    require(
        video_count >= required_videos,
        f"daily queue incomplete: requires at least {required_videos} video items, found {video_count}",
    )
if no_video_sub_for_photos and photo_count < required_photos:
    require(
        False,
        "daily queue invalid: required photo slots are missing and videos cannot substitute for photos",
    )


print("contract:", CONTRACT_PATH)
print("queue:", QUEUE)
print("preflight_date:", PREFLIGHT_DATE)
print("photo_items:", photo_count)
print("video_items:", video_count)
print("required daily mix:", f"{daily['photos_per_day']} photos + max {daily['videos_per_day_max']} videos")
print("video contract:", f"{IMAGE_ENGINE} seed image -> {VIDEO_ENGINE} motion-control video")
print("required video:", f"{VIDEO_RESOLUTION}, {VIDEO_FPS}fps, <= {MAX_VIDEO_SECONDS}s")
print("warnings:", len(warn))
for item in warn:
    print("WARN:", item)
print("errors:", len(bad))
for item in bad:
    print("ERROR:", item)

if bad:
    sys.exit(1)

print("PASS")
