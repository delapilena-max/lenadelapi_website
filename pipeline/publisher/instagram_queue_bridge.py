from __future__ import annotations

import json
import os
import shutil
import subprocess
import importlib
import re
from pathlib import Path
from typing import Any, Dict

from pipeline.env_loader import load_env_once

load_env_once()

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "pipeline" / "config" / "lena_kling_contract.json"


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
        # Provider-aware image-engine dispatch (2026-07-10): "image_engine" alone used
        # to always mean Kling (specs["image_engine"], a flat single value). Real
        # Higgsfield photos legitimately use a different, real engine string
        # (higgsfield_text2image_soul_v2) -- the old flat check rejected every
        # Higgsfield photo unconditionally, mislabeling it as a Kling contract
        # violation. Reuses the same image_engine_by_provider map and default/fail-
        # closed dispatch pattern tools/lena_preflight.py already established: an
        # item with no metadata.provider predates this field and defaults to
        # "kling" for backward compatibility; an explicit but unrecognized provider
        # value is a hard fail, never a silent fallback to Kling; provider is never
        # inferred from image_engine or auto-detected any other way.
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
                f"Lena contract violation: photo must use {expected_engine} for provider {provider!r}"
            )
        if not meta.get("image_prompt"):
            raise ValueError("Lena contract violation: photo missing image_prompt")
        return

    if media_type in {"video", "reel"}:
        seed = Path(str(meta.get("seed_image_path") or ""))
        if not seed.exists():
            raise ValueError(f"Lena contract violation: missing seed image: {seed}")
        if str(meta.get("seed_image_engine") or "").lower() != specs["image_engine"]:
            raise ValueError("Lena contract violation: video seed must be Kling Image 3.0")
        if str(meta.get("video_engine") or "").lower() != specs["video_engine"]:
            raise ValueError("Lena contract violation: video must be Kling Video 3.0")
        motion_confirmed = meta.get("motion_control") is True
        motion_requested = meta.get("motion_control_requested") is True
        if not motion_confirmed and not motion_requested:
            raise ValueError("Lena contract violation: video must request or confirm motion control")
        if int(meta.get("fps") or 0) != int(specs["video_fps"]):
            raise ValueError("Lena contract violation: video must be 30fps")
        if str(meta.get("resolution") or "").lower() not in {"1080p", "1080x1920", "1920x1080"}:
            raise ValueError("Lena contract violation: video must be 1080p")
        if not meta.get("image_prompt") or not meta.get("video_prompt"):
            raise ValueError("Lena contract violation: video missing image_prompt or video_prompt")

        dur = _duration(media_path)
        if dur is None:
            raise ValueError("Lena contract violation: could not verify video duration")
        if dur > int(specs["max_video_duration_seconds"]):
            raise ValueError(f"Lena contract violation: video duration {dur:.2f}s exceeds max")
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
