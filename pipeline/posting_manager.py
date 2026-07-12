"""
pipeline.posting_manager
========================

Queue-driven posting manager for Lena / content_bot nodes.

Responsibilities:
- read post JSONs from pipeline/queue
- validate schema, media existence, extension, and size limits
- support photo and video posts
- generate safe captions when missing
- retry publish attempts up to max_attempts
- move processed JSONs to pipeline/queue/published
- move malformed/failed JSONs to pipeline/queue/failed
- respect dry-run mode by avoiding external calls and queue mutation
- emit structured results and feedback JSONL entries

The actual social network uploader is adapter-driven. In production, configure
``publisher_backend`` to an existing adapter/module or to a webhook. For smoke
tests and local validation, use ``local``; it writes receipts and treats the
post as published without hitting an external service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import hashlib
import importlib
import json
import os
import shutil
import traceback
import urllib.error
import urllib.request

try:  # package import
    from .feedback.collector import FeedbackCollector
except Exception:  # script/direct import fallback
    from feedback.collector import FeedbackCollector  # type: ignore

try:  # package import
    from .lena_job_state import apply_transition as apply_job_state_transition
    from .lena_job_state import load_snapshot as load_job_state_snapshot
    from .lena_job_state import save_snapshot as save_job_state_snapshot
except Exception:  # script/direct import fallback
    from lena_job_state import apply_transition as apply_job_state_transition  # type: ignore
    from lena_job_state import load_snapshot as load_job_state_snapshot  # type: ignore
    from lena_job_state import save_snapshot as save_job_state_snapshot  # type: ignore

PIPELINE_DIR = Path(os.environ.get("CONTENT_BOT_PIPELINE_DIR", Path(__file__).resolve().parent)).resolve()
REPO_ROOT = Path(os.environ.get("CONTENT_BOT_ROOT", PIPELINE_DIR.parent)).resolve()
DEFAULT_CONFIG_PATH = PIPELINE_DIR / "config" / "posting_config.json"

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
RESERVED_QUEUE_DIRS = {"published", "failed", "archive", "_archive", "in_flight", "__pycache__"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def default_config() -> Dict[str, Any]:
    return {
        "queue_dir": "queue",
        "published_dir": "queue/published",
        "failed_dir": "queue/failed",
        "in_flight_dir": "queue/in_flight",
        "receipt_dir": "queue/receipts",
        "feedback_file": "feedback/feedback.jsonl",
        "max_posts_per_run": 3,
        "max_attempts": 3,
        "dry_run": True,
        "publisher_backend": "local",
        "publisher_module": "pipeline.publisher.publisher",
        "webhook_url": "",
        "platforms": ["instagram", "tiktok", "youtube"],
        "allowed_photo_extensions": sorted(PHOTO_EXTENSIONS),
        "allowed_video_extensions": sorted(VIDEO_EXTENSIONS),
        "max_photo_mb": 25,
        "max_video_mb": 512,
        "move_media_with_json": False,
        "caption": {
            "default_hashtags": ["#Lena", "#Lifestyle", "#DailyVibes"],
            "fallback_templates": [
                "A little moment worth sharing ✨",
                "Soft glow, good energy, and a tiny reset ✨",
                "Keeping it simple and cute today ✨",
            ],
        },
    }


def load_config(path: Optional[os.PathLike[str] | str] = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.is_absolute():
        cfg_path = PIPELINE_DIR / cfg_path
    cfg = default_config()
    loaded = read_json(cfg_path, {})
    if isinstance(loaded, dict):
        # shallow merge is enough for top-level; merge nested caption safely
        caption = {**cfg.get("caption", {}), **loaded.get("caption", {})} if isinstance(loaded.get("caption"), dict) else cfg.get("caption", {})
        cfg.update({k: v for k, v in loaded.items() if k != "caption"})
        cfg["caption"] = caption
    if "CONTENT_BOT_POSTING_DRY_RUN" in os.environ:
        cfg["dry_run"] = truthy(os.environ.get("CONTENT_BOT_POSTING_DRY_RUN"))
    if "CONTENT_BOT_PUBLISH_BACKEND" in os.environ:
        cfg["publisher_backend"] = os.environ.get("CONTENT_BOT_PUBLISH_BACKEND", cfg["publisher_backend"])
    return cfg


def resolve_under_pipeline(path_value: str | os.PathLike[str]) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p
    return (PIPELINE_DIR / p).resolve()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ValidatedPost:
    post_file: Path
    raw: Dict[str, Any]
    post_id: str
    media_path: Path
    media_type: str
    caption: str
    platforms: List[str]
    attempts_so_far: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PostValidationError(Exception):
    pass


class PublishError(Exception):
    pass


class PostingManager:
    def __init__(self, config_path: Optional[os.PathLike[str] | str] = None, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or load_config(config_path)
        self.queue_dir = resolve_under_pipeline(str(self.config.get("queue_dir", "queue")))
        self.published_dir = resolve_under_pipeline(str(self.config.get("published_dir", "queue/published")))
        self.failed_dir = resolve_under_pipeline(str(self.config.get("failed_dir", "queue/failed")))
        self.in_flight_dir = resolve_under_pipeline(str(self.config.get("in_flight_dir", "queue/in_flight")))
        self.receipt_dir = resolve_under_pipeline(str(self.config.get("receipt_dir", "queue/receipts")))
        feedback_file = self.config.get("feedback_file") or "feedback/feedback.jsonl"
        self.feedback = FeedbackCollector(feedback_file)

    def ensure_dirs(self) -> None:
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.published_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        self.in_flight_dir.mkdir(parents=True, exist_ok=True)
        self.receipt_dir.mkdir(parents=True, exist_ok=True)

    def list_post_files(self) -> List[Path]:
        self.ensure_dirs()
        files: List[Path] = []
        for path in self.queue_dir.glob("*.json"):
            if path.parent.name.lower() in RESERVED_QUEUE_DIRS:
                continue
            files.append(path)
        return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))

    def _extract_post_id(self, data: Dict[str, Any], post_file: Path) -> str:
        for key in ("post_id", "id", "episode_id", "content_id", "request_id", "slug"):
            value = data.get(key)
            if value:
                return str(value)
        return post_file.stem

    def _candidate_media_paths(self, data: Dict[str, Any], post_file: Path) -> List[Path]:
        values: List[Any] = []
        for key in (
            "media_path", "media", "file", "path", "asset_path", "output_path",
            "video_path", "photo_path", "image_path", "filename", "final_video", "final_image",
        ):
            if data.get(key):
                values.append(data.get(key))
        if isinstance(data.get("assets"), list):
            for item in data["assets"]:
                if isinstance(item, dict):
                    for key in ("path", "file", "media_path", "url"):
                        if item.get(key):
                            values.append(item[key])
                elif item:
                    values.append(item)
        if isinstance(data.get("media"), dict):
            for key in ("path", "file", "media_path", "video_path", "photo_path", "image_path"):
                if data["media"].get(key):
                    values.append(data["media"][key])

        candidates: List[Path] = []
        for value in values:
            text = str(value).strip()
            if not text or text.startswith("http://") or text.startswith("https://"):
                continue
            p = Path(text)
            if p.is_absolute():
                candidates.append(p)
            else:
                candidates.extend([
                    (post_file.parent / p).resolve(),
                    (PIPELINE_DIR / p).resolve(),
                    (REPO_ROOT / p).resolve(),
                ])

        # Last-resort sibling inference for ep_001.json + ep_001.mp4/jpg.
        for ext in sorted(PHOTO_EXTENSIONS | VIDEO_EXTENSIONS):
            candidates.append(post_file.with_suffix(ext))
        return candidates

    def _resolve_media_path(self, data: Dict[str, Any], post_file: Path) -> Path:
        seen: set[str] = set()
        for candidate in self._candidate_media_paths(data, post_file):
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():
                return candidate
        raise PostValidationError("media file missing or no valid media_path in post JSON")

    def _infer_media_type(self, data: Dict[str, Any], media_path: Path) -> str:
        raw = data.get("media_type") or data.get("type") or data.get("kind") or data.get("content_type")
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            # Explicit Story classification (2026-07-10) -- must stay distinct
            # from "photo", never collapsed into it. Only reachable via an
            # explicit media_type/type/kind/content_type value; the
            # extension-based fallback below is intentionally left
            # photo/video-only, unchanged, so a bare .png with no explicit
            # media_type still infers "photo" exactly as before.
            if normalized in {"story", "stories"}:
                return "story"
            if normalized in {"photo", "image", "jpg", "jpeg", "png", "webp"}:
                return "photo"
            if normalized in {"reel", "reels"}:
                return "reel"
            if normalized in {"video", "short", "mp4", "mov", "m4v", "webm"}:
                return "video"
        ext = media_path.suffix.lower()
        if ext in set(self.config.get("allowed_photo_extensions", sorted(PHOTO_EXTENSIONS))):
            return "photo"
        if ext in set(self.config.get("allowed_video_extensions", sorted(VIDEO_EXTENSIONS))):
            return "video"
        raise PostValidationError(f"unsupported media extension: {ext or '(none)'}")

    def _validate_size(self, media_path: Path, media_type: str) -> None:
        size = media_path.stat().st_size
        if size <= 0:
            raise PostValidationError("media file is empty")
        is_video_like = media_type in {"video", "reel", "story"}
        limit_mb = float(
            self.config.get("max_video_mb" if is_video_like else "max_photo_mb", 512 if is_video_like else 25)
        )
        if size > limit_mb * 1024 * 1024:
            raise PostValidationError(f"media file exceeds {limit_mb:g} MB limit")

    def generate_caption(self, data: Dict[str, Any], media_type: str) -> str:
        for key in ("caption", "text", "description"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        title = str(data.get("title") or data.get("topic") or "").strip()
        caption_cfg = self.config.get("caption", {}) if isinstance(self.config.get("caption"), dict) else {}
        templates = caption_cfg.get("fallback_templates") or ["A little moment worth sharing ✨"]
        base = str(templates[0])
        if title:
            base = f"{title}. {base}"
        hashtags = data.get("hashtags") or caption_cfg.get("default_hashtags") or []
        if isinstance(hashtags, str):
            hashtags_text = hashtags.strip()
        elif isinstance(hashtags, list):
            hashtags_text = " ".join(str(h).strip() for h in hashtags if str(h).strip())
        else:
            hashtags_text = ""
        caption = (base + ("\n\n" + hashtags_text if hashtags_text else "")).strip()
        return caption[:2200]

    def _extract_platforms(self, data: Dict[str, Any]) -> List[str]:
        value = data.get("platforms") or data.get("targets") or self.config.get("platforms") or []
        if isinstance(value, str):
            platforms = [value]
        elif isinstance(value, Sequence):
            platforms = [str(v) for v in value if str(v).strip()]
        else:
            platforms = []
        return [p.strip().lower() for p in platforms if p.strip()]

    def validate_post(self, post_file: Path) -> ValidatedPost:
        data = read_json(post_file)
        if not isinstance(data, dict):
            raise PostValidationError("malformed JSON or root is not an object")
        post_id = self._extract_post_id(data, post_file)
        media_path = self._resolve_media_path(data, post_file)
        media_type = self._infer_media_type(data, media_path)
        self._validate_size(media_path, media_type)
        platforms = self._extract_platforms(data)
        if not platforms:
            raise PostValidationError("no target platforms configured")
        attempts = int(data.get("publish_attempts") or data.get("attempts") or 0)
        caption = self.generate_caption(data, media_type)
        if not caption:
            raise PostValidationError("caption generation failed")
        # Preserve the original queue JSON's metadata (avatar_nickname, image_engine,
        # image_prompt, etc.) instead of discarding it -- downstream contract validation
        # (e.g. instagram_queue_bridge._validate_contract) depends on these fields.
        original_metadata = data.get("metadata")
        metadata: Dict[str, Any] = dict(original_metadata) if isinstance(original_metadata, dict) else {}
        metadata.update({
            "media_size_bytes": media_path.stat().st_size,
            "media_sha256": sha256_file(media_path),
        })
        return ValidatedPost(
            post_file=post_file,
            raw=data,
            post_id=post_id,
            media_path=media_path,
            media_type=media_type,
            caption=caption,
            platforms=platforms,
            attempts_so_far=attempts,
            metadata=metadata,
        )

    def _safe_destination(self, directory: Path, source: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        candidate = directory / source.name
        if not candidate.exists():
            return candidate
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return directory / f"{source.stem}.{stamp}{source.suffix}"

    def _is_live_queue_path(self, post_file: Path) -> bool:
        try:
            return post_file.resolve().parent == self.queue_dir.resolve()
        except Exception:
            return False

    def _claim_destination(self, post_file: Path) -> Path:
        return self.in_flight_dir / post_file.name

    def _claim_queue_item(self, post_file: Path) -> Dict[str, Any]:
        source = post_file.resolve()
        if not self._is_live_queue_path(source):
            return {"status": "not_live_queue", "claimed_path": str(source)}

        claimed_path = self._claim_destination(source)
        claimed_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(str(source), str(claimed_path))
        except FileNotFoundError:
            return {
                "status": "skipped",
                "reason": "claimed_elsewhere" if claimed_path.exists() else "missing_queue_item",
                "post_file": str(source),
                "claimed_path": str(claimed_path) if claimed_path.exists() else None,
            }
        except FileExistsError:
            return {
                "status": "skipped",
                "reason": "claimed_elsewhere",
                "post_file": str(source),
                "claimed_path": str(claimed_path),
            }

        try:
            source.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            try:
                claimed_path.unlink()
            except Exception:
                pass
            raise

        return {
            "status": "claimed",
            "source_path": str(source),
            "claimed_path": str(claimed_path),
        }

    def _move_post(self, post: ValidatedPost, destination_dir: Path, receipt: Dict[str, Any]) -> Path:
        dest = self._safe_destination(destination_dir, post.post_file)
        shutil.move(str(post.post_file), str(dest))
        receipt_path = dest.with_suffix(dest.suffix + ".receipt.json")
        receipt = {**receipt, "published_post_path": str(dest)}
        write_json_atomic(receipt_path, receipt)
        if truthy(self.config.get("move_media_with_json", False)):
            media_dest = self._safe_destination(destination_dir, post.media_path)
            if post.media_path.exists():
                shutil.move(str(post.media_path), str(media_dest))
        return dest

    def _record_published_job_state_transition(
        self,
        post: ValidatedPost,
        published_post_path: Path,
        publish_response: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            snapshot = load_job_state_snapshot(post.post_id)
            if not isinstance(snapshot, dict):
                return {"status": "skipped", "reason": "missing_snapshot", "post_id": post.post_id}

            current_state = str(snapshot.get("current_state") or "")
            if current_state != "queued":
                return {
                    "status": "skipped",
                    "reason": "unexpected_state",
                    "post_id": post.post_id,
                    "current_state": current_state,
                }

            updated = apply_job_state_transition(
                snapshot,
                "published_pending_learning",
                note="Successful publish receipt recorded by PostingManager.process_one().",
            )

            artifact_paths = dict(updated.get("artifact_paths") or {})
            receipt_path = published_post_path.with_suffix(published_post_path.suffix + ".receipt.json")
            artifact_paths["queue_item"] = str(published_post_path)
            artifact_paths["publish_receipt"] = str(receipt_path)
            updated["artifact_paths"] = artifact_paths

            artifact_evidence = set(updated.get("artifact_evidence") or [])
            artifact_evidence.update({"queue_item", "publish_receipt"})
            updated["artifact_evidence"] = sorted(str(item) for item in artifact_evidence if str(item).strip())

            ig_result = ((publish_response or {}).get("result") or {}).get("instagram_result") or {}
            platform_media_id = ig_result.get("instagram_media_id")
            if platform_media_id:
                updated["platform_media_id"] = str(platform_media_id)

            save_job_state_snapshot(updated)
            return {
                "status": "updated",
                "post_id": post.post_id,
                "canonical_job_id": updated.get("canonical_job_id"),
                "current_state": updated.get("current_state"),
            }
        except Exception as exc:
            return {
                "status": "error",
                "post_id": post.post_id,
                "error": str(exc),
            }

    def _write_local_receipt(self, post: ValidatedPost, dry_run: bool = False) -> Dict[str, Any]:
        payload = {
            "ok": True,
            "backend": "local",
            "dry_run": dry_run,
            "post_id": post.post_id,
            "media_type": post.media_type,
            "media_path": str(post.media_path),
            "caption": post.caption,
            "platforms": post.platforms,
            "timestamp_utc": utc_now(),
        }
        if not dry_run:
            receipt_path = self.receipt_dir / f"{post.post_id}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
            write_json_atomic(receipt_path, payload)
        return payload

    def _publish_via_webhook(self, post: ValidatedPost) -> Dict[str, Any]:
        url = str(self.config.get("webhook_url") or os.environ.get("CONTENT_BOT_WEBHOOK_URL") or "").strip()
        if not url:
            raise PublishError("webhook backend selected but no webhook_url configured")
        body = json.dumps({
            "post_id": post.post_id,
            "media_path": str(post.media_path),
            "media_type": post.media_type,
            "caption": post.caption,
            "platforms": post.platforms,
            "metadata": post.metadata,
        }).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return {"ok": 200 <= response.status < 300, "backend": "webhook", "status": response.status, "response": raw[:4000]}
        except urllib.error.HTTPError as exc:
            raise PublishError(f"webhook HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:1000]}") from exc
        except Exception as exc:
            raise PublishError(f"webhook publish failed: {exc}") from exc

    def _publish_via_module(self, post: ValidatedPost) -> Dict[str, Any]:
        module_name = str(self.config.get("publisher_module") or "pipeline.publisher.publisher")
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            if module_name.startswith("pipeline."):
                module = importlib.import_module(module_name.split(".", 1)[1])
            else:
                raise PublishError(f"publisher module not found: {module_name}")
        payload = {
            "post_id": post.post_id,
            "media_path": str(post.media_path),
            "media_type": post.media_type,
            "caption": post.caption,
            "platforms": post.platforms,
            "metadata": post.metadata,
            "raw": post.raw,
        }
        for name in ("publish_post", "publish", "dispatch_post", "dispatch"):
            fn = getattr(module, name, None)
            if callable(fn):
                result = fn(payload)
                return {"ok": True if result is None else bool(result.get("ok", True) if isinstance(result, dict) else result), "backend": module_name, "result": result}
        cls = getattr(module, "Publisher", None)
        if cls is not None:
            instance = cls()
            if hasattr(instance, "publish") and callable(instance.publish):
                result = instance.publish(payload)
                return {"ok": True if result is None else bool(result.get("ok", True) if isinstance(result, dict) else result), "backend": module_name, "result": result}
        raise PublishError(f"publisher module {module_name} has no supported publish callable")

    def publish(self, post: ValidatedPost, *, dry_run: bool) -> Dict[str, Any]:
        if dry_run:
            return self._write_local_receipt(post, dry_run=True)
        backend = str(self.config.get("publisher_backend") or "local").strip().lower()
        if backend in {"local", "noop", "receipt"}:
            return self._write_local_receipt(post, dry_run=False)
        if backend == "webhook":
            return self._publish_via_webhook(post)
        if backend in {"module", "auto", "publisher"}:
            return self._publish_via_module(post)
        raise PublishError(f"unknown publisher_backend: {backend}")

    def _record_failure_json(self, post_file: Path, error: str) -> Dict[str, Any]:
        data = read_json(post_file, {})
        if not isinstance(data, dict):
            data = {}
        data["last_error"] = error
        data["failed_at_utc"] = utc_now()
        data["publish_attempts"] = int(data.get("publish_attempts") or data.get("attempts") or 0)
        write_json_atomic(post_file, data)
        return data

    def process_one(self, post_file: Path, *, dry_run: bool, media_types: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        media_type_filter = {m.lower() for m in media_types or []}
        original_post_file = Path(post_file)
        working_post_file = original_post_file

        if not dry_run:
            claim_result = self._claim_queue_item(original_post_file)
            if claim_result.get("status") == "skipped":
                return {
                    "status": "skipped",
                    "reason": claim_result.get("reason"),
                    "post_file": str(original_post_file),
                    "claimed_path": claim_result.get("claimed_path"),
                }
            if claim_result.get("status") == "claimed":
                working_post_file = Path(str(claim_result["claimed_path"]))

        try:
            post = self.validate_post(working_post_file)
            if media_type_filter and post.media_type not in media_type_filter:
                return {"status": "skipped", "reason": "media_type_filter", "post_file": str(original_post_file), "media_type": post.media_type}
            max_attempts = max(1, int(self.config.get("max_attempts", 3)))
            if post.attempts_so_far >= max_attempts:
                raise PostValidationError(f"max attempts already reached ({post.attempts_so_far}/{max_attempts})")

            attempt_errors: List[str] = []
            publish_response: Optional[Dict[str, Any]] = None
            for attempt in range(post.attempts_so_far + 1, max_attempts + 1):
                try:
                    post.raw["publish_attempts"] = attempt
                    publish_response = self.publish(post, dry_run=dry_run)
                    if not publish_response.get("ok", False):
                        raise PublishError(str(publish_response))
                    break
                except Exception as exc:
                    attempt_errors.append(str(exc))
                    post.raw["last_error"] = str(exc)
                    post.raw["publish_attempts"] = attempt
                    if not dry_run:
                        write_json_atomic(post.post_file, post.raw)
            else:
                raise PublishError("; ".join(attempt_errors) or "publish failed")

            # Flatten the useful Instagram fields out of the nested publish response
            # for easy top-level access in the receipt. Safe .get() chains so other
            # backends (local/webhook) and dry-runs (publish_response shape differs
            # or is absent) never break this.
            ig_result = ((publish_response or {}).get("result") or {}).get("instagram_result") or {}

            receipt = {
                "status": "dry_run" if dry_run else "published",
                "post_id": post.post_id,
                "post_file": str(post.post_file),
                "media_path": str(post.media_path),
                "media_type": post.media_type,
                "platforms": post.platforms,
                "caption": post.caption,
                "caption_variant": (post.metadata or {}).get("caption_variant"),
                "instagram_media_id": ig_result.get("instagram_media_id"),
                "permalink": ig_result.get("permalink"),
                "instagram_media_type": ig_result.get("instagram_media_type"),
                "instagram_timestamp": ig_result.get("instagram_timestamp"),
                "publish_response": publish_response,
                "timestamp_utc": utc_now(),
            }
            moved_to: Optional[Path] = None
            job_state_result: Optional[Dict[str, Any]] = None
            if not dry_run:
                moved_to = self._move_post(post, self.published_dir, receipt)
                job_state_result = self._record_published_job_state_transition(post, moved_to, publish_response)
            event = self.feedback.success(
                event_type="post_published" if not dry_run else "post_dry_run",
                post_id=post.post_id,
                post_file=str(original_post_file),
                metadata={
                    **receipt,
                    "moved_to": str(moved_to) if moved_to else None,
                    "job_state_result": job_state_result,
                },
            )
            return {
                "status": "success" if not dry_run else "dry_run",
                "post_id": post.post_id,
                "post_file": str(original_post_file),
                "moved_to": str(moved_to) if moved_to else None,
                "media_type": post.media_type,
                "feedback_event_id": event["event_id"],
                "publish_response": publish_response,
                "job_state_result": job_state_result,
            }
        except Exception as exc:
            error = str(exc)
            moved_to = None
            if not dry_run:
                try:
                    self._record_failure_json(working_post_file, error)
                    dest = self._safe_destination(self.failed_dir, working_post_file)
                    shutil.move(str(working_post_file), str(dest))
                    moved_to = str(dest)
                except Exception as move_exc:
                    error = f"{error}; failed to move to failed/: {move_exc}"
            event = self.feedback.failure(
                event_type="post_failed" if not dry_run else "post_dry_run_failed",
                error=error,
                post_file=str(original_post_file),
                metadata={"moved_to": moved_to, "traceback": traceback.format_exc(limit=8)},
            )
            return {
                "status": "failed" if not dry_run else "dry_run_failed",
                "post_file": str(original_post_file),
                "error": error,
                "moved_to": moved_to,
                "feedback_event_id": event["event_id"],
            }

    def process_queue(
        self,
        *,
        max_posts: Optional[int] = None,
        dry_run: Optional[bool] = None,
        media_types: Optional[Iterable[str]] = None,
        date_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.ensure_dirs()
        effective_dry_run = truthy(self.config.get("dry_run", True)) if dry_run is None else bool(dry_run)
        limit = int(max_posts if max_posts is not None else self.config.get("max_posts_per_run", 3))
        limit = max(0, limit)
        processed: List[Dict[str, Any]] = []
        scanned = 0
        attempted = 0

        for post_file in self.list_post_files():
            scanned += 1
            if date_prefix and not post_file.stem.startswith(date_prefix):
                processed.append({
                    "status": "skipped",
                    "reason": "date_prefix_filter",
                    "post_file": str(post_file),
                    "date_prefix": date_prefix,
                })
                continue
            if attempted >= limit:
                break
            result = self.process_one(post_file, dry_run=effective_dry_run, media_types=media_types)
            if result.get("status") == "skipped":
                processed.append(result)
                continue
            attempted += 1
            processed.append(result)

        success_count = sum(1 for r in processed if r.get("status") in {"success", "dry_run"})
        failed_count = sum(1 for r in processed if r.get("status") in {"failed", "dry_run_failed"})
        skipped_count = sum(1 for r in processed if r.get("status") == "skipped")
        payload = {
            "ok": failed_count == 0,
            "dry_run": effective_dry_run,
            "queue_dir": str(self.queue_dir),
            "published_dir": str(self.published_dir),
            "failed_dir": str(self.failed_dir),
            "scanned": scanned,
            "attempted": attempted,
            "processed": processed,
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "date_prefix": date_prefix,
            "timestamp_utc": utc_now(),
        }
        self.feedback.append(event_type="queue_processed", status="success" if payload["ok"] else "failure", metadata=payload)
        return payload


def process_queue(**kwargs: Any) -> Dict[str, Any]:
    return PostingManager().process_queue(**kwargs)


if __name__ == "__main__":
    result = process_queue()
    print(json.dumps(result, ensure_ascii=False, indent=2))
