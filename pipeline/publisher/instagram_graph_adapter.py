"""
Instagram direct publisher adapter for the Instagram API with Instagram Login.

This adapter is designed for content_bot's PostingManager module backend.
It expects a payload dict with:
  - post_id
  - media_path
  - media_type: photo|image|video|reel
  - caption
  - raw: optional source queue JSON

Required environment variables:
  INSTAGRAM_GRAPH_ACCESS_TOKEN
  INSTAGRAM_GRAPH_USER_ID

Optional environment variables:
  INSTAGRAM_GRAPH_API_VERSION=v25.0
  CONTENT_BOT_PUBLIC_MEDIA_BASE_URL=https://media.example.com/content-bot
  CONTENT_BOT_PUBLIC_MEDIA_ROOT=pipeline/public_media
  CONTENT_BOT_IG_VIDEO_MEDIA_TYPE=REELS
  CONTENT_BOT_IG_SHARE_TO_FEED=true
  CONTENT_BOT_IG_POLL_TIMEOUT_SECONDS=900
  CONTENT_BOT_IG_POLL_INTERVAL_SECONDS=10

Important: Instagram's API fetches media by public HTTPS URL. If the queue JSON
already contains a public URL, this adapter uses it. Otherwise it stages a copy
under CONTENT_BOT_PUBLIC_MEDIA_ROOT and constructs a URL from
CONTENT_BOT_PUBLIC_MEDIA_BASE_URL. That root still must be served publicly.

Clean-export defense-in-depth (2026-07-11): publish_post() independently
re-verifies the clean-export contract (tools/lena_verify_clean_export_v1.py)
before doing anything else -- including before resolving a public media URL
or building any Meta request. This is a deliberate second gate: the
canonical path (pipeline/publisher/instagram_queue_bridge.py::
_validate_contract()) already enforces this, but this module's functions
are public and importable directly (a real, present example:
tools/instagram_publish_smoke.py calls publish_post() here without going
through the bridge at all). See _validate_clean_export_before_publish()'s
own docstring for exactly what it checks and why. There is no bypass flag.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import quote, urlsplit
from datetime import datetime, timezone
import json
import mimetypes
import os
import shutil
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_verify_clean_export_v1 import (  # noqa: E402
    CleanExportVerificationError,
    verify_clean_export,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
PUBLIC_URL_KEYS = (
    "public_media_url",
    "public_url",
    "media_url",
    "source_url",
    "remote_url",
    "cdn_url",
    "url",
    "image_url",
    "video_url",
)


class InstagramPublishError(RuntimeError):
    """Raised when Instagram publishing cannot continue."""


ENV_ALIASES = {
    "INSTAGRAM_GRAPH_ACCESS_TOKEN": ("INSTAGRAM_GRAPH_ACCESS_TOKEN", "META_INSTAGRAM_ACCESS_TOKEN"),
    "INSTAGRAM_GRAPH_USER_ID": ("INSTAGRAM_GRAPH_USER_ID", "META_IG_USER_ID"),
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_token(value: Optional[str]) -> str:
    return (value or "").strip().strip('"').strip("'")


def _api_version() -> str:
    return (os.environ.get("INSTAGRAM_GRAPH_API_VERSION") or "v25.0").strip().strip("/")


def _api_base() -> str:
    # Instagram Login route uses graph.instagram.com, not graph.facebook.com.
    return f"https://graph.instagram.com/{_api_version()}"


def _required_env(name: str) -> str:
    candidates = ENV_ALIASES.get(name, (name,))
    for candidate in candidates:
        value = _clean_token(os.environ.get(candidate))
        if value:
            return value
    alias_note = ""
    if len(candidates) > 1:
        alias_note = f" (accepted aliases: {', '.join(candidates)})"
    raise InstagramPublishError(f"missing required environment variable: {name}{alias_note}")


def _is_https_url(value: Any) -> bool:
    text = str(value or "").strip()
    return text.lower().startswith("https://")


def _first_public_url_from_mapping(mapping: Dict[str, Any]) -> Optional[str]:
    for key in PUBLIC_URL_KEYS:
        value = mapping.get(key)
        if _is_https_url(value):
            return str(value).strip()

    media = mapping.get("media")
    if isinstance(media, dict):
        found = _first_public_url_from_mapping(media)
        if found:
            return found

    assets = mapping.get("assets")
    if isinstance(assets, list):
        for item in assets:
            if isinstance(item, dict):
                found = _first_public_url_from_mapping(item)
                if found:
                    return found
            elif _is_https_url(item):
                return str(item).strip()
    return None


def _public_url_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    found = _first_public_url_from_mapping(payload)
    if found:
        return found
    raw = payload.get("raw")
    if isinstance(raw, dict):
        found = _first_public_url_from_mapping(raw)
        if found:
            return found
    return None


def _repo_root_from_this_file() -> Path:
    # pipeline/publisher/instagram_graph_adapter.py -> repo root
    return Path(__file__).resolve().parents[2]


def _stage_local_media(media_path: Path, post_id: str) -> str:
    base_url = str(os.environ.get("CONTENT_BOT_PUBLIC_MEDIA_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        try:
            from pipeline.media_host.r2_uploader import upload_file_to_r2

            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            safe_post_id = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(post_id or media_path.stem))[:80]
            key = f"lena/queue-media/{stamp}/{safe_post_id}{media_path.suffix.lower()}"
            uploaded = upload_file_to_r2(media_path, key)
            public_url = str(uploaded.get("public_url") or "").strip()
            if public_url.lower().startswith("https://"):
                return public_url
        except Exception:
            pass

    if not base_url:
        raise InstagramPublishError(
            "No public HTTPS media URL found. Add public_media_url/media_url to the queue JSON, "
            "or set CONTENT_BOT_PUBLIC_MEDIA_BASE_URL and serve CONTENT_BOT_PUBLIC_MEDIA_ROOT publicly, "
            "or configure R2_PUBLIC_BASE_URL + other R2_* vars for automatic upload."
        )
    if not base_url.lower().startswith("https://"):
        raise InstagramPublishError("CONTENT_BOT_PUBLIC_MEDIA_BASE_URL must start with https://")

    root_value = os.environ.get("CONTENT_BOT_PUBLIC_MEDIA_ROOT") or "pipeline/public_media"
    root = Path(root_value)
    if not root.is_absolute():
        root = (_repo_root_from_this_file() / root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    media_path = media_path.resolve()
    try:
        rel = media_path.relative_to(root)
        return f"{base_url}/{quote(rel.as_posix())}"
    except ValueError:
        safe_post_id = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(post_id or media_path.stem))[:80]
        destination = root / f"{safe_post_id}{media_path.suffix.lower()}"
        if destination.resolve() != media_path:
            shutil.copy2(media_path, destination)
        rel = destination.relative_to(root)
        return f"{base_url}/{quote(rel.as_posix())}"


def resolve_public_media_url(payload: Dict[str, Any]) -> str:
    url = _public_url_from_payload(payload)
    if url:
        return url
    media_path_value = payload.get("media_path") or payload.get("path") or payload.get("file")
    if not media_path_value:
        raise InstagramPublishError("payload has no public URL and no media_path")
    media_path = Path(str(media_path_value)).expanduser()
    if not media_path.exists():
        raise InstagramPublishError(f"media_path does not exist: {media_path}")
    return _stage_local_media(media_path, str(payload.get("post_id") or media_path.stem))


def _request_json(method: str, url: str, *, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None, timeout: int = 60) -> Dict[str, Any]:
    try:
        response = requests.request(method, url, params=params, data=data, timeout=timeout)
    except Exception as exc:
        raise InstagramPublishError(f"Instagram request failed before response: {exc}") from exc

    try:
        payload = response.json()
    except Exception:
        payload = {"raw_text": response.text[:4000]}

    if response.status_code >= 400:
        raise InstagramPublishError(f"Instagram HTTP {response.status_code}: {json.dumps(payload, ensure_ascii=False)[:2000]}")
    return payload


def _media_url_extension(media_url: str) -> str:
    """Best-effort file extension (lowercase, with leading dot) from a
    media URL's path component -- strips any query string/fragment first.
    Pure, no I/O, no network. Returns "" if the URL has no extension."""
    return Path(urlsplit(media_url).path).suffix.lower()


def create_media_container(*, ig_user_id: str, access_token: str, media_url: str, media_type: str, caption: str) -> Dict[str, Any]:
    normalized = str(media_type or "photo").strip().lower()
    endpoint = f"{_api_base()}/{ig_user_id}/media"
    data: Dict[str, Any] = {
        "caption": caption or "",
        "access_token": access_token,
    }

    if normalized in {"photo", "image", "jpg", "jpeg", "png", "webp"}:
        data["image_url"] = media_url
    elif normalized in {"story", "stories"}:
        # Instagram Story branch (2026-07-10, extended same day to support
        # video Stories -- tools/lena_prepare_story_video_v1.py composes a
        # real music-backed MP4 Story asset). A Story can be a static image
        # (the original, still-default behavior) or a real video; the only
        # reliable discriminator available at this function's boundary is
        # the media URL's own file extension -- this function receives no
        # local Path, only the already-resolved media_url string. Reuses
        # this module's own pre-existing VIDEO_EXTENSIONS set (defined
        # above, previously unused) rather than inventing a new list or
        # widening create_media_container()'s signature. Video Stories send
        # video_url; image Stories are completely unchanged and still send
        # image_url. Neither branch ever sets REELS media_type or
        # share_to_feed -- those stay exclusive to the video/reel branch
        # below, which this change does not touch.
        if _media_url_extension(media_url) in VIDEO_EXTENSIONS:
            data["video_url"] = media_url
        else:
            data["image_url"] = media_url
        data["media_type"] = "STORIES"
    elif normalized in {"video", "reel", "reels", "mp4", "mov", "m4v"}:
        data["video_url"] = media_url
        data["media_type"] = os.environ.get("CONTENT_BOT_IG_VIDEO_MEDIA_TYPE", "REELS")
        if _truthy(os.environ.get("CONTENT_BOT_IG_SHARE_TO_FEED", "true")):
            data["share_to_feed"] = "true"
    else:
        raise InstagramPublishError(f"unsupported media_type for Instagram: {media_type}")

    created = _request_json("POST", endpoint, data=data)
    if not created.get("id"):
        raise InstagramPublishError(f"Instagram did not return a creation id: {created}")
    return created


def get_container_status(*, creation_id: str, access_token: str) -> Dict[str, Any]:
    endpoint = f"{_api_base()}/{creation_id}"
    return _request_json(
        "GET",
        endpoint,
        params={"fields": "id,status,status_code", "access_token": access_token},
        timeout=30,
    )


def wait_for_container_if_needed(*, creation_id: str, access_token: str, media_type: str) -> Dict[str, Any]:
    normalized = str(media_type or "").lower()
    if normalized not in {"video", "reel", "reels", "mp4", "mov", "m4v"}:
        return {"status_code": "SKIPPED", "reason": "photo containers do not require polling"}

    timeout_seconds = int(os.environ.get("CONTENT_BOT_IG_POLL_TIMEOUT_SECONDS", "900"))
    interval_seconds = max(2, int(os.environ.get("CONTENT_BOT_IG_POLL_INTERVAL_SECONDS", "10")))
    deadline = time.time() + timeout_seconds
    last: Dict[str, Any] = {}

    while time.time() < deadline:
        last = get_container_status(creation_id=creation_id, access_token=access_token)
        status_code = str(last.get("status_code") or last.get("status") or "").upper()
        if status_code in {"FINISHED", "PUBLISHED"}:
            return last
        if status_code in {"ERROR", "EXPIRED"}:
            raise InstagramPublishError(f"Instagram media container failed: {last}")
        time.sleep(interval_seconds)

    raise InstagramPublishError(f"Instagram media container did not finish before timeout. Last status: {last}")


def publish_media_container(*, ig_user_id: str, access_token: str, creation_id: str) -> Dict[str, Any]:
    endpoint = f"{_api_base()}/{ig_user_id}/media_publish"

    max_attempts = int(os.environ.get("INSTAGRAM_MEDIA_PUBLISH_RETRIES", "8"))
    delay_seconds = int(os.environ.get("INSTAGRAM_MEDIA_PUBLISH_RETRY_DELAY_SECONDS", "12"))

    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            published = _request_json("POST", endpoint, data={"creation_id": creation_id, "access_token": access_token})
            if not published.get("id"):
                raise InstagramPublishError(f"Instagram did not return a published media id: {published}")
            return published
        except InstagramPublishError as exc:
            last_error = exc
            msg = str(exc)

            # Instagram sometimes reports the container as finished but rejects immediate publish.
            # Error 9007 / subcode 2207027 means: media exists, but publish is a few seconds too early.
            retryable_not_ready = (
                "2207027" in msg
                or "Media ID is not available" in msg
                or "media is not ready for publishing" in msg
                or "please wait for a moment" in msg
            )

            if not retryable_not_ready or attempt >= max_attempts:
                raise

            time.sleep(delay_seconds)

    raise InstagramPublishError(f"Instagram media publish failed after retries: {last_error}")


def _validate_clean_export_before_publish(payload: Dict[str, Any]) -> None:
    """Fail-closed defense-in-depth gate (2026-07-11). The lowest-level
    chokepoint in this module -- runs as the very first thing publish_post()
    does, before any env var is read, before resolve_public_media_url() is
    called, and before create_media_container() can ever be reached. This is
    the last line of defense for any caller that reaches publish_post()
    directly, without going through pipeline/publisher/
    instagram_queue_bridge.py's own _validate_contract()/
    _validate_downstream_clean_export() first -- a real, present example
    being tools/instagram_publish_smoke.py.

    Does NOT treat metadata.clean_export_verified as sufficient evidence on
    its own -- reuses the same tools/lena_verify_clean_export_v1.py::
    verify_clean_export() every other clean-export gate in this repo uses,
    which recomputes every hash from the real files on disk right now. No
    hashing or sidecar logic is reimplemented here.

    Raises InstagramPublishError (this module's own existing exception type
    -- no new exception type introduced) on any hard-fail condition. There
    is no fallback to a raw source or to an unverified media_url/public URL
    anywhere in this function, and no bypass flag exists."""
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    source_asset_path_raw = metadata.get("source_asset_path")
    if not source_asset_path_raw:
        raise InstagramPublishError(
            "clean-export verification failed: metadata.source_asset_path is missing -- "
            "cannot independently verify this payload's media before publishing"
        )
    source_asset_path = Path(str(source_asset_path_raw))

    media_path_raw = payload.get("media_path")
    if not media_path_raw:
        raise InstagramPublishError(
            "clean-export verification failed: media_path is missing -- refusing to "
            "resolve a public URL for unverifiable media"
        )
    queued_media_path = Path(str(media_path_raw)).resolve()

    try:
        facts = verify_clean_export(source_asset_path)
    except CleanExportVerificationError as exc:
        raise InstagramPublishError(f"clean-export verification failed: {exc}") from exc

    if Path(facts["clean_derivative_path"]).resolve() != queued_media_path:
        raise InstagramPublishError(
            "clean-export verification failed: media_path does not equal the "
            f"independently re-verified clean derivative path (media_path="
            f"{queued_media_path}, re-verified derivative={facts['clean_derivative_path']}) "
            "-- refusing, no fallback to raw source"
        )


def publish_post(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Publish one content_bot queue payload to Instagram."""
    _validate_clean_export_before_publish(payload)
    access_token = _required_env("INSTAGRAM_GRAPH_ACCESS_TOKEN")
    ig_user_id = _required_env("INSTAGRAM_GRAPH_USER_ID")
    media_type = str(payload.get("media_type") or payload.get("type") or "photo")
    caption = str(payload.get("caption") or "")[:2200]
    post_id = str(payload.get("post_id") or payload.get("id") or "instagram_post")
    media_url = resolve_public_media_url(payload)

    created = create_media_container(
        ig_user_id=ig_user_id,
        access_token=access_token,
        media_url=media_url,
        media_type=media_type,
        caption=caption,
    )
    creation_id = str(created["id"])
    status = wait_for_container_if_needed(creation_id=creation_id, access_token=access_token, media_type=media_type)
    published = publish_media_container(ig_user_id=ig_user_id, access_token=access_token, creation_id=creation_id)

    # Provenance enrichment: look up the PUBLISHED media object (not the creation/
    # container id) for its permalink/media_type/timestamp. Read-only GET, non-fatal --
    # the publish above already succeeded regardless of whether this lookup works.
    instagram_media_id = published.get("id") if isinstance(published, dict) else None

    permalink = None
    instagram_media_type = None
    instagram_timestamp = None

    if instagram_media_id:
        try:
            media_obj = _request_json(
                "GET",
                f"{_api_base()}/{instagram_media_id}",
                params={
                    "fields": "id,permalink,media_type,timestamp",
                    "access_token": access_token,
                },
                timeout=30,
            )
            permalink = media_obj.get("permalink")
            instagram_media_type = media_obj.get("media_type")
            instagram_timestamp = media_obj.get("timestamp")
        except Exception:
            # Non-fatal: the publish already succeeded.
            pass

    return {
        "ok": True,
        "backend": "instagram_graph",
        "route": "instagram_login",
        "post_id": post_id,
        "ig_user_id": ig_user_id,
        "media_type": media_type,
        "media_url": media_url,
        "creation_id": creation_id,
        "container_status": status,
        "instagram_media_id": instagram_media_id,
        "permalink": permalink,
        "instagram_media_type": instagram_media_type,
        "instagram_timestamp": instagram_timestamp,
        "created_response": created,
        "published_response": published,
        "timestamp_utc": _utc_now(),
    }


def publish(payload: Dict[str, Any]) -> Dict[str, Any]:
    return publish_post(payload)
