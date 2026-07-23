from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency guard
    Image = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
VALID_EXTS = IMAGE_EXTS | VIDEO_EXTS

# These are private/internal policy terms. They should never appear in public captions/prompts.
BANNED_PUBLIC_TERMS = [
    "ai",
    "a.i.",
    "artificial intelligence",
    "virtual influencer",
    "synthetic",
    "bot",
    "generated",
    "avatar",
    "fake",
    "computer generated",
    "cg",
    "cgi",
    "deepfake",
    "digital human",
    "not real",
]

DEFAULT_CAPTIONS = {"lena"}


@dataclass(frozen=True)
class QualityGateConfig:
    project_root: Path = Path(__file__).resolve().parents[1]
    library_root: Path | None = None
    publish_state_path: Path | None = None
    publish_logs_dir: Path | None = None
    image_min_bytes: int = 20_000
    image_max_bytes: int = 30 * 1024 * 1024
    video_min_bytes: int = 500_000
    video_max_bytes: int = 300 * 1024 * 1024
    min_width: int = 512
    min_height: int = 512
    max_width: int = 8192
    max_height: int = 8192
    # Instagram feed practical bounds. Reels/video can be 9:16, so video check is looser below.
    image_min_aspect: float = 0.70
    image_max_aspect: float = 1.91
    video_min_seconds: float = 7.0
    video_max_seconds: float = 15.0
    require_ffprobe_for_video: bool = True

    def __post_init__(self):
        root = Path(self.project_root).resolve()
        object.__setattr__(self, "project_root", root)
        if self.library_root is None:
            object.__setattr__(self, "library_root", root / "pipeline" / "higgsfield_library" / "lena")
        else:
            object.__setattr__(self, "library_root", Path(self.library_root).resolve())
        if self.publish_state_path is None:
            object.__setattr__(self, "publish_state_path", root / "pipeline" / "state" / "lena_r2_publish_state.json")
        else:
            object.__setattr__(self, "publish_state_path", Path(self.publish_state_path).resolve())
        if self.publish_logs_dir is None:
            object.__setattr__(self, "publish_logs_dir", root / "pipeline" / "publish_logs")
        else:
            object.__setattr__(self, "publish_logs_dir", Path(self.publish_logs_dir).resolve())


@dataclass
class QualityGateResult:
    ok: bool
    media_path: str
    media_type: str
    fingerprint: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def raise_for_errors(self) -> None:
        if not self.ok:
            raise RuntimeError("Lena publish quality gate failed: " + "; ".join(self.errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _banned_term_hits(text: str) -> list[str]:
    text = text or ""
    hits: list[str] = []
    for term in BANNED_PUBLIC_TERMS:
        if term in {"ai", "cg"}:
            pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        elif term == "a.i.":
            pattern = r"(?<![A-Za-z0-9])a\s*\.\s*i\s*\.?(?![A-Za-z0-9])"
        else:
            pattern = re.escape(term)
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(term)
    return sorted(set(hits))


_MAX_CAPTION_HASHTAGS = 3


def _hashtag_count(text: str) -> int:
    return len(re.findall(r"#\w+", text or ""))



_CAPTION_ACTIVITY_SIGNALS: dict = {
    "food": [
        "eating", "dinner", "snack", "breakfast",
        "lunch", "strawberry", "food",
    ],
    "coffee": [
        "coffee", "latte", "espresso",
        "iced coffee", "americano",
    ],
    "gym": [
        "gym", "workout", "fitness", "athletic",
        "earned",
    ],
    "dog": ["dog", "herby", "paw", "puppy"],
    "turtle": ["turtle", "tortoise"],
    "rain": ["rain", "rainy", "umbrella"],
    "airport": [
        "airport", "terminal", "boarding",
    ],
    "flowers": ["flower", "bouquet"],
    "record": ["record", "vinyl", "album"],
}

_SIGNAL_EVIDENCE_KEYWORDS: dict = {
    "food": [
        "food", "kitchen", "eating", "sink",
        "bowl", "plate", "snack",
    ],
    "coffee": [
        "coffee", "cafe", "cup", "drink", "latte",
    ],
    "gym": [
        "gym", "fitness", "athletic", "bench",
    ],
    "dog": ["dog", "herby"],
    "turtle": ["turtle"],
    "rain": [
        "rain", "wet", "overcast", "umbrella",
    ],
    "airport": [
        "airport", "terminal", "suitcase",
    ],
    "flowers": ["flower", "bouquet"],
    "record": ["record", "vinyl", "album"],
}


def _caption_scene_coherence_check(
    caption: str,
    scene_meta: dict,
) -> "tuple[list[str], list[str]]":
    """Return (errors, warnings) for caption vs scene_meta.

    errors   — hard contradictions that block publish
    warnings — soft mismatches that flag for review
    """
    errors: list[str] = []
    warnings: list[str] = []
    cap = (caption or "").lower()

    required = (
        scene_meta.get("required_visual_evidence") or []
    )
    forbidden = (
        scene_meta.get("forbidden_contradictions") or []
    )

    for contradiction in forbidden:
        c_lower = contradiction.lower()
        if c_lower.startswith("no ") or " without " in c_lower:
            continue
        kws = [
            w for w in c_lower.split()
            if len(w) > 3
        ]
        hits = [kw for kw in kws if kw in cap]
        if hits:
            errors.append(
                "caption conflicts with forbidden "
                f"contradiction '{contradiction}': "
                f"matched {hits}"
            )

    evidence_text = " ".join(required).lower()
    for activity, signals in _CAPTION_ACTIVITY_SIGNALS.items():
        if not any(s in cap for s in signals):
            continue
        needed = _SIGNAL_EVIDENCE_KEYWORDS.get(
            activity, []
        )
        if not any(kw in evidence_text for kw in needed):
            warnings.append(
                f"caption implies '{activity}' activity "
                "but scene evidence has no matching "
                f"context; evidence: {required}"
            )

    return errors, warnings


def caption_has_banned_terms(caption: str) -> bool:
    return bool(_banned_term_hits(caption))


def caption_is_default(caption: str) -> bool:
    normalized = re.sub(r"\s+", " ", (caption or "").strip()).lower()
    return normalized in DEFAULT_CAPTIONS


def _image_dimensions(path: Path) -> tuple[int | None, int | None, str | None]:
    if Image is None:
        return None, None, "Pillow is not installed; cannot verify image dimensions."
    try:
        with Image.open(path) as img:
            return int(img.width), int(img.height), None
    except Exception as exc:
        return None, None, f"Could not read image dimensions: {exc}"


def _ffprobe_duration(path: Path) -> tuple[float | None, str | None]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None, "ffprobe was not found on PATH; cannot verify video duration."
    try:
        proc = subprocess.run(
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
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return None, f"ffprobe failed: {exc}"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "unknown ffprobe error").strip()
        return None, f"ffprobe failed: {msg}"
    try:
        return float(proc.stdout.strip()), None
    except Exception:
        return None, f"Could not parse ffprobe duration output: {proc.stdout!r}"


def _collect_published_fingerprints(config: QualityGateConfig) -> set[str]:
    fingerprints: set[str] = set()
    state = _load_json(config.publish_state_path)
    if isinstance(state, dict):
        qg = state.get("quality_gate")
        if isinstance(qg, dict):
            values = qg.get("published_fingerprints") or qg.get("fingerprints") or []
            if isinstance(values, list):
                fingerprints.update(str(v) for v in values if v)
        for key in ("published_fingerprints", "fingerprints", "media_fingerprints"):
            values = state.get(key)
            if isinstance(values, list):
                fingerprints.update(str(v) for v in values if v)
            elif isinstance(values, dict):
                fingerprints.update(str(k) for k in values.keys() if k)
    logs_dir = config.publish_logs_dir
    if logs_dir.exists():
        for log_path in sorted(logs_dir.glob("*.json"))[-250:]:
            log = _load_json(log_path)
            if not isinstance(log, dict):
                continue

            # Only successful publish logs count as published fingerprints.
            # Failed Instagram/R2 attempts include quality_gate.fingerprint too,
            # but they must not block a retry.
            if log.get("ok") is not True:
                continue
            for key in ("fingerprint", "media_fingerprint", "sha256"):
                value = log.get(key)
                if value:
                    fingerprints.add(str(value))
            qg = log.get("quality_gate")
            if isinstance(qg, dict):
                value = qg.get("fingerprint")
                if value:
                    fingerprints.add(str(value))
    return fingerprints


def quality_gate_media(
    media_path: str | Path,
    caption: str,
    media_type: str | None = None,
    config: QualityGateConfig | None = None,
    scene_meta: dict | None = None,
) -> QualityGateResult:
    config = config or QualityGateConfig()
    path = Path(media_path).expanduser().resolve()
    ext = path.suffix.lower()
    inferred_type = "video" if ext in VIDEO_EXTS else "photo" if ext in IMAGE_EXTS else "unknown"
    media_type = (media_type or inferred_type).lower()
    result = QualityGateResult(ok=False, media_path=str(path), media_type=media_type)

    if not path.exists():
        result.errors.append(f"file does not exist: {path}")
        return result
    if not path.is_file():
        result.errors.append(f"path is not a file: {path}")
    if not _is_under(path, config.library_root):
        result.errors.append(f"file is outside Lena Higgsfield library: {config.library_root}")
    if ext not in VALID_EXTS:
        result.errors.append(f"invalid media extension: {ext}")
    if media_type == "video" and ext not in VIDEO_EXTS:
        result.errors.append(f"media_type=video but extension is not video: {ext}")
    if media_type in {"photo", "image"} and ext not in IMAGE_EXTS:
        result.errors.append(f"media_type=photo but extension is not image: {ext}")

    size = path.stat().st_size
    if ext in IMAGE_EXTS:
        if size < config.image_min_bytes:
            result.errors.append(f"image file is too small: {size} bytes")
        if size > config.image_max_bytes:
            result.errors.append(f"image file is too large: {size} bytes")
    elif ext in VIDEO_EXTS:
        if size < config.video_min_bytes:
            result.errors.append(f"video file is too small: {size} bytes")
        if size > config.video_max_bytes:
            result.errors.append(f"video file is too large: {size} bytes")

    if ext in IMAGE_EXTS:
        width, height, warning = _image_dimensions(path)
        result.width = width
        result.height = height
        if warning:
            result.errors.append(warning)
        if width and height:
            if width < config.min_width or height < config.min_height:
                result.errors.append(f"image dimensions are too small: {width}x{height}")
            if width > config.max_width or height > config.max_height:
                result.errors.append(f"image dimensions are too large: {width}x{height}")
            aspect = width / height
            if aspect < config.image_min_aspect or aspect > config.image_max_aspect:
                result.errors.append(f"image aspect ratio is outside sane feed bounds: {aspect:.3f}")

    if ext in VIDEO_EXTS:
        duration, warning = _ffprobe_duration(path)
        result.duration_seconds = duration
        if warning:
            if config.require_ffprobe_for_video:
                result.errors.append(warning)
            else:
                result.warnings.append(warning)
        if duration is not None:
            if duration < config.video_min_seconds or duration > config.video_max_seconds:
                result.errors.append(
                    f"video duration is outside expected range: {duration:.2f}s "
                    f"(expected {config.video_min_seconds:.1f}-{config.video_max_seconds:.1f}s)"
                )

    if caption_is_default(caption):
        result.errors.append("caption is the default placeholder 'Lena'")
    banned_hits = _banned_term_hits(caption)
    if banned_hits:
        result.errors.append("caption contains banned public terms: " + ", ".join(banned_hits))

    tag_count = _hashtag_count(caption)
    if tag_count > _MAX_CAPTION_HASHTAGS:
        result.errors.append(
            f"caption has too many hashtags: {tag_count} found, "
            f"max allowed is {_MAX_CAPTION_HASHTAGS}"
        )

    if scene_meta:
        c_errors, c_warns = _caption_scene_coherence_check(
            caption, scene_meta
        )
        for e in c_errors:
            result.errors.append(
                "scene coherence: " + e
            )
        for w in c_warns:
            result.warnings.append(
                "scene coherence: " + w
            )

    try:
        result.fingerprint = file_sha256(path)
        if result.fingerprint in _collect_published_fingerprints(config):
            result.errors.append("media is a duplicate of an already published fingerprint")
    except Exception as exc:
        result.errors.append(f"could not fingerprint media: {exc}")

    result.ok = not result.errors
    return result


def mark_published_fingerprint(
    media_path: str | Path,
    config: QualityGateConfig | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Record a successfully published media fingerprint in publish state.

    Call this only after the Instagram publish succeeds.
    """
    config = config or QualityGateConfig()
    path = Path(media_path).expanduser().resolve()
    fingerprint = file_sha256(path)
    state = _load_json(config.publish_state_path)
    if not isinstance(state, dict):
        state = {}
    qg = state.setdefault("quality_gate", {})
    values = qg.setdefault("published_fingerprints", [])
    if fingerprint not in values:
        values.append(fingerprint)
    media_records = qg.setdefault("published_media", [])
    record = {"path": str(path), "fingerprint": fingerprint}
    if extra:
        record.update(extra)
    if not any(isinstance(r, dict) and r.get("fingerprint") == fingerprint for r in media_records):
        media_records.append(record)
    _write_json_atomic(config.publish_state_path, state)
    return fingerprint


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate one Lena media file before publishing.")
    parser.add_argument("media_path")
    parser.add_argument("--caption", required=True)
    parser.add_argument("--media-type", choices=["photo", "image", "video"], default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    gate = quality_gate_media(args.media_path, args.caption, args.media_type)
    if args.json:
        print(json.dumps(gate.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("OK" if gate.ok else "FAILED")
        if gate.errors:
            print("Errors:")
            for item in gate.errors:
                print(f"  - {item}")
        if gate.warnings:
            print("Warnings:")
            for item in gate.warnings:
                print(f"  - {item}")
    raise SystemExit(0 if gate.ok else 2)
