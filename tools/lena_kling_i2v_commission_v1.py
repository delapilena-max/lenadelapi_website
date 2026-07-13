from __future__ import annotations

# Minimal, narrow Kling image-to-video commissioning runner for Lena -- v1.
#
# Purpose (narrow, explicit): take exactly one already-approved Lena still
# image plus one exact, hand-supplied motion prompt, and submit exactly one
# Kling image-to-video generation under a clearly test-scoped video
# identity -- distinct from, and never confused with, the source photo's
# own identity.
#
# HISTORICAL EVIDENCE THIS IS BUILT FROM (all confirmed via direct
# read-only inspection of real, already-committed repo artifacts -- never
# guessed):
#   - pipeline/strategy/lena/kling_video_results/2026-06-30/
#     kling_video_result_2026-06-30_podclip_20260630_01_901327158671446020.json
#     -- a REAL succeeded Kling image-to-video job:
#       provider_endpoint: "https://api-singapore.klingai.com/v1/videos/image2video"
#       model: "kling-v2-1-master"
#       task_status: "succeed"
#       seed_image_ref: a real, already-public R2 URL (not a local upload,
#         not base64) -- confirming this Kling route takes a public image
#         URL, not direct file upload.
#   - pipeline/config/kling_video_model_policy_v1.json -- confirms
#     "kling-v2-1-master completed a live image-to-video submit on
#     2026-07-01 for this account" and that "kling-v3-0-turbo was rejected
#     by the live API on 2026-07-01 for this account".
#   - The historical submission module this evidence came from
#     (tools/strategy/lena_submit_kling_video_payload_v1.py) no longer
#     exists on disk and has ZERO git history (never committed) -- it is
#     not recoverable. This module is a NEW, narrower implementation, not
#     a recreation of that missing module by name or assumption.
#   - The exact literal JSON request body field names used by that missing
#     module are NOT recoverable from current repo evidence (the
#     corresponding payload-dryrun artifact is also gone). REQUEST_PAYLOAD
#     below is reconstructed from Kling's documented image2video contract
#     shape, not copied from a recovered historical payload -- this is
#     stated explicitly, not glossed over.
#   - pipeline/kling_apilena_api_executor.py's transport/auth primitives
#     (_build_jwt/_auth_header/_http_json/_download_file/
#     _sanitize_reference_url) are real, already-proven, already-live Kling
#     transport code (used for real photo submissions) -- reused here
#     directly, never reimplemented. That module's own photo-submission
#     logic, its production workorder I/O, and its own API_BASE
#     ("https://api.klingai.com") are untouched and not imported --  only
#     the generic transport helpers are reused. Video uses a different,
#     historically-proven regional host (api-singapore.klingai.com).
#   - pipeline/renderer/kling.py is a separate, disconnected legacy
#     prototype (Fal-LoRA-based identity, no dry-run default, no fail-closed
#     gates, raw env-var credential reads) -- inspected read-only for
#     historical context only, never imported or reused as an execution
#     path here.
#
# HARD SAFETY GATES (v1, all enforced by construction):
#   - --dry-run is the default; --live requires the flag explicitly.
#   - Exactly one source image, one motion prompt, one test video slot id
#     per invocation.
#   - At most one provider generation submission, ever, per invocation. No
#     retry, no second variation, no fallback model, no fallback endpoint,
#     no silent provider switching.
#   - Model is pinned to CONFIRMED_KLING_VIDEO_MODEL
#     ("kling-v2-1-master") -- no CLI override exists in v1.
#   - Endpoint is pinned to the historically-proven
#     CONFIRMED_KLING_VIDEO_ENDPOINT -- no CLI override exists in v1.
#   - This tool never uploads the source image anywhere. A public image URL
#     for the source, if one already exists (e.g. from a real prior
#     Instagram/R2 publish of that same asset), must be supplied explicitly
#     via --source-public-url; this tool creates no new public URL for
#     anything, ever. --live fails closed if no public URL is supplied.
#   - test_video_slot_id must be clearly test-scoped (contains the literal
#     "-motion-test-" marker) and must always differ from source_slot_id --
#     source identity and generated-video identity are never collapsed.
#   - An existing output (manifest, final video, OR a leftover .tmp
#     download) for a test_video_slot_id always fails closed -- no
#     overwrite path exists in v1.
#   - No queue/approval/publish/R2-upload/analytics/.env import anywhere in
#     this file.
#   - Never creates a queue item, approval record, or publish action of any
#     kind. Never claims "Motion Control" (a distinct Kling product surface
#     this tool does not use) and never claims full Rule Zero readiness --
#     this tool's own manifest is real provenance, not a Rule Zero pass.
#
# Run (dry-run, default, no provider/network call):
#   python tools/lena_kling_i2v_commission_v1.py --date 2026-07-09 \
#     --source-slot-id readypack0709-pack003-08-photo \
#     --source-path pipeline/higgsfield_library/lena/2026-07-09/readypack0709-pack003-08-photo_seed.png \
#     --test-video-slot-id readypack0709-pack003-08-motion-test-01 \
#     --motion-prompt-file <path to a text file containing the exact motion prompt>
#
# Run (live, exactly one real provider submission -- needs --live and
# --source-public-url explicitly):
#   ...same as above... --live --source-public-url https://.../already-public-image.png

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reused, never redefined -- the same confirmed, already-proven Kling
# transport/auth primitives the canonical photo executor already uses live.
from pipeline.kling_apilena_api_executor import (  # noqa: E402
    _auth_header,
    _http_json,
    _download_file,
    _sanitize_reference_url,
)

CONFIRMED_KLING_VIDEO_MODEL = "kling-v2-1-master"
CONFIRMED_KLING_VIDEO_HOST = "https://api-singapore.klingai.com"
CONFIRMED_KLING_VIDEO_ENDPOINT = f"{CONFIRMED_KLING_VIDEO_HOST}/v1/videos/image2video"
TEST_SCOPE_MARKER = "-motion-test-"

# Durable, already-committed publish-receipt convention this repo already
# uses (pipeline/queue/published/<slot_id>.json.receipt.json) -- reused
# read-only here, never written to.
SOURCE_RECEIPT_ROOT = ROOT / "pipeline" / "queue" / "published"

# v1 is pinned to exactly 5 seconds -- no arbitrary positive floats, and no
# int()-truncation drift (e.g. 5.9 silently becoming 5).
REQUIRED_DURATION_SECONDS = 5.0
REQUIRED_DURATION_PAYLOAD_VALUE = "5"

# Deliberately separate from any real production video path -- never
# collides with, and is never mistaken for, a real production seed/video.
COMMISSION_LIBRARY_ROOT = ROOT / "pipeline" / "kling_library" / "lena"
COMMISSION_DEBUG_ROOT = ROOT / "pipeline" / "kling_debug"
COMMISSION_SUBDIR_NAME = "i2v_commission_tests"

POLL_INTERVAL_SECONDS = 6
POLL_TIMEOUT_SECONDS = 600


_OPERATIONAL_URL_PATTERN = re.compile(r"https?://[^\s'\"<>\[\]{}]+")


def _sanitize_operational_error_text(value: Any) -> str:
    """Keep provider diagnostics while removing query-bearing URL secrets."""
    text = str(value)

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0)
        if urlsplit(url).query:
            return _sanitize_reference_url(url)
        return url

    return _OPERATIONAL_URL_PATTERN.sub(replace_url, text)


class KlingCommissionError(Exception):
    """Raised for any hard-fail condition. Always fails closed -- no file
    is ever written and no provider call is ever made when this is raised.
    `stage` names exactly which operational step failed, so the failure
    manifest can record it precisely instead of one generic bucket."""

    def __init__(
        self,
        message: str,
        stage: str = "unknown",
        partial_live_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(_sanitize_operational_error_text(message))
        self.stage = stage
        self.partial_live_state = dict(partial_live_state or {})


def _live_failure(
    message: str, stage: str, partial_live_state: Dict[str, Any]
) -> KlingCommissionError:
    partial_live_state["current_stage"] = stage
    return KlingCommissionError(
        message, stage=stage, partial_live_state=partial_live_state
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_receipt_path(source_slot_id: str) -> Path:
    """Deterministic, already-established repo convention -- never a new
    naming scheme invented for this tool."""
    return SOURCE_RECEIPT_ROOT / f"{source_slot_id}.json.receipt.json"


def _extract_receipt_media_url(receipt: Dict[str, Any]) -> Optional[str]:
    """Real schema, confirmed by direct inspection of a real receipt --
    never invented. Returns None if the expected nested path is absent."""
    try:
        return (
            receipt["publish_response"]["result"]
            ["instagram_result"]["media_url"]
        )
    except (KeyError, TypeError):
        return None


def validate_source_receipt_binding(
    source_slot_id: str,
    resolved_source_path: Path,
    proposed_public_url: str,
) -> Dict[str, Any]:
    """Proves proposed_public_url belongs to the selected source's own
    durable publish-receipt provenance chain. Every field must match
    exactly -- never substring matching, never a silent fallback."""
    receipt_path = source_receipt_path(source_slot_id)
    result: Dict[str, Any] = {
        "ok": False,
        "reasons": [],
        "receipt_path": str(receipt_path),
        "receipt_media_url": None,
    }

    if not receipt_path.exists():
        result["reasons"].append(
            f"durable source receipt not found: {receipt_path}"
        )
        return result

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["reasons"].append(
            f"durable source receipt could not be read/parsed: "
            f"{receipt_path}: {exc}"
        )
        return result

    receipt_post_id = receipt.get("post_id")
    if receipt_post_id != source_slot_id:
        result["reasons"].append(
            f"receipt post_id {receipt_post_id!r} does not match "
            f"source_slot_id {source_slot_id!r}"
        )

    receipt_media_path_raw = receipt.get("media_path")
    receipt_media_path_resolved = (
        Path(receipt_media_path_raw).resolve()
        if receipt_media_path_raw else None
    )
    if receipt_media_path_resolved != resolved_source_path:
        result["reasons"].append(
            f"receipt media_path {receipt_media_path_raw!r} does not "
            f"match selected source path {resolved_source_path}"
        )

    receipt_media_url = _extract_receipt_media_url(receipt)
    result["receipt_media_url"] = receipt_media_url
    if receipt_media_url is None:
        result["reasons"].append(
            "receipt has no publish_response.result.instagram_result."
            f"media_url field: {receipt_path}"
        )
    elif receipt_media_url != proposed_public_url:
        result["reasons"].append(
            "--source-public-url does not exactly match the receipt's "
            "own recorded media_url -- refusing an unproven public URL"
        )

    result["ok"] = not result["reasons"]
    return result


def _manifest_safe_source_url(url: Optional[str]) -> Optional[str]:
    """Sanitizes only when the URL carries query-string material (which may
    carry signing credentials). An unsigned URL (no query string) is safe
    to persist in full for audit -- this is not blanket redaction."""
    if not url:
        return url
    parsed = urlsplit(url)
    if parsed.query:
        return _sanitize_reference_url(url)
    return url


def validate_duration_seconds(duration_seconds: Any) -> Optional[str]:
    """v1 policy: exactly 5 seconds, no drift. Returns an error message if
    duration_seconds is not exactly REQUIRED_DURATION_SECONDS, else None."""
    if isinstance(duration_seconds, bool):
        return (
            f"duration_seconds must be a real number, not a bool: "
            f"{duration_seconds!r}"
        )
    try:
        as_float = float(duration_seconds)
    except (TypeError, ValueError):
        return f"duration_seconds must be a number -- got {duration_seconds!r}"
    if as_float != REQUIRED_DURATION_SECONDS:
        return (
            f"duration_seconds must be exactly {REQUIRED_DURATION_SECONDS!r} "
            f"seconds in v1 -- got {duration_seconds!r}"
        )
    return None


def validate_prompt_bytes(raw_bytes: bytes) -> Optional[str]:
    """v1 policy: reject a prompt file that ends with a trailing CR, LF, or
    CRLF byte rather than silently trimming it. The approved prompt and its
    SHA must be exact and byte-stable. Internal newlines are untouched."""
    if raw_bytes.endswith(b"\r\n"):
        return (
            "prompt file ends with a trailing CRLF byte sequence -- v1 "
            "requires exact prompt bytes and refuses to silently trim"
        )
    if raw_bytes.endswith(b"\n"):
        return (
            "prompt file ends with a trailing LF byte -- v1 requires "
            "exact prompt bytes and refuses to silently trim"
        )
    if raw_bytes.endswith(b"\r"):
        return (
            "prompt file ends with a trailing CR byte -- v1 requires "
            "exact prompt bytes and refuses to silently trim"
        )
    return None


def commission_output_paths(date_str: str, test_video_slot_id: str) -> Dict[str, Path]:
    video_dir = COMMISSION_LIBRARY_ROOT / date_str / COMMISSION_SUBDIR_NAME
    manifest_dir = COMMISSION_DEBUG_ROOT / date_str / COMMISSION_SUBDIR_NAME / test_video_slot_id
    return {
        "video_dir": video_dir,
        "video_stem": f"{test_video_slot_id}_video",
        "manifest_path": manifest_dir / "result_manifest.json",
    }


def _existing_output_paths(date_str: str, test_video_slot_id: str) -> list[Path]:
    """A finished manifest, a finished video, OR a leftover .tmp download
    all count as an existing output. No overwrite path exists in v1: any
    of these fails closed, unconditionally."""
    paths = commission_output_paths(date_str, test_video_slot_id)
    found: list[Path] = []
    if paths["manifest_path"].exists():
        found.append(paths["manifest_path"])
    for ext in (".mp4", ".mov", ".tmp"):
        candidate = paths["video_dir"] / f"{paths['video_stem']}{ext}"
        if candidate.exists():
            found.append(candidate)
    return found


def validate_test_video_slot_id(test_video_slot_id: str, source_slot_id: str) -> list[str]:
    reasons: list[str] = []
    if not test_video_slot_id:
        return ["missing test_video_slot_id"]
    if TEST_SCOPE_MARKER not in test_video_slot_id:
        reasons.append(
            f"test_video_slot_id {test_video_slot_id!r} does not contain the required "
            f"{TEST_SCOPE_MARKER!r} marker -- refusing an ambiguously-scoped identity."
        )
    if test_video_slot_id == source_slot_id:
        reasons.append(
            "test_video_slot_id must not equal source_slot_id -- source identity and "
            "generated-video identity must never be collapsed."
        )
    return reasons


def _looks_like_public_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_commission(
    date_str: str,
    source_slot_id: str,
    source_path: Path,
    test_video_slot_id: str,
    motion_prompt: str,
    duration_seconds: float,
    source_public_url: Optional[str],
    live: bool,
) -> Dict[str, Any]:
    """Never raises -- returns a dict with 'ok' plus every reason found, so
    the full picture can be reported before any provider call is even
    considered."""
    reasons: list[str] = []

    reasons.extend(validate_test_video_slot_id(test_video_slot_id, source_slot_id))

    if not source_slot_id:
        reasons.append("missing source_slot_id")

    resolved_source_path = source_path.resolve()
    source_sha256: Optional[str] = None
    if not resolved_source_path.exists():
        reasons.append(f"source image does not exist: {resolved_source_path}")
    else:
        source_sha256 = _sha256_file(resolved_source_path)

    if not motion_prompt or not motion_prompt.strip():
        reasons.append("missing or empty motion prompt")

    duration_error = validate_duration_seconds(duration_seconds)
    if duration_error:
        reasons.append(duration_error)

    existing_outputs = _existing_output_paths(date_str, test_video_slot_id) if test_video_slot_id else []
    if existing_outputs:
        reasons.append(
            f"output already exists for test_video_slot_id {test_video_slot_id!r}: "
            f"{[str(p) for p in existing_outputs]} -- v1 has no overwrite path; "
            "remove the prior artifact manually before retrying this exact identity"
        )

    if live:
        if not source_public_url:
            reasons.append(
                "BLOCKER: --live requires --source-public-url. The Kling image2video "
                "route (per real historical evidence) takes a public image URL, not a "
                "local file upload -- this tool never uploads the source image anywhere, "
                "so a genuinely already-existing, non-mutating public URL for this exact "
                "source image must be supplied explicitly."
            )
        elif not _looks_like_public_url(source_public_url):
            reasons.append(f"--source-public-url does not look like a real http(s) URL: {source_public_url!r}")

    # Source-receipt provenance binding: whenever a public URL is supplied
    # (live or not), it must be proven to belong to the selected source's
    # own durable publish-receipt chain -- never an arbitrary but
    # syntactically valid URL. Skipped only when no URL was given at all,
    # or when it already failed the basic shape check above.
    receipt_path_str: Optional[str] = None
    if source_public_url and _looks_like_public_url(source_public_url):
        binding = validate_source_receipt_binding(
            source_slot_id, resolved_source_path, source_public_url
        )
        receipt_path_str = binding["receipt_path"]
        if not binding["ok"]:
            reasons.extend(binding["reasons"])
    elif source_slot_id:
        receipt_path_str = str(source_receipt_path(source_slot_id))

    return {
        "ok": not reasons,
        "reasons": reasons,
        "date": date_str,
        "source_slot_id": source_slot_id,
        "source_path": str(resolved_source_path),
        "source_sha256": source_sha256,
        "test_video_slot_id": test_video_slot_id,
        "motion_prompt": motion_prompt,
        "motion_prompt_sha256": _sha256_text(motion_prompt) if motion_prompt else None,
        "duration_seconds": duration_seconds,
        "source_public_url": source_public_url,
        "source_public_url_sanitized": _manifest_safe_source_url(source_public_url),
        "source_receipt_path": receipt_path_str,
        "existing_outputs": [str(p) for p in existing_outputs],
    }


def build_request_payload(source_public_url: str, motion_prompt: str, duration_seconds: float) -> Dict[str, Any]:
    """Reconstructed from Kling's documented image2video contract shape --
    NOT copied from a recovered historical literal payload (that artifact
    no longer exists in this repo; see module docstring). Model and
    endpoint are the two fields with direct historical evidence
    (kling_video_result_...901327158671446020.json); the remaining field
    names follow Kling's documented image2video request contract.

    duration_seconds must be exactly REQUIRED_DURATION_SECONDS -- the
    payload's "duration" is always the pinned literal value, never derived
    via int() truncation of the argument, so no fractional input (e.g.
    5.9) can ever silently drift into a different submitted duration."""
    duration_error = validate_duration_seconds(duration_seconds)
    if duration_error:
        raise KlingCommissionError(duration_error, stage="duration_validation")
    return {
        "model_name": CONFIRMED_KLING_VIDEO_MODEL,
        "image": source_public_url,
        "prompt": motion_prompt,
        "duration": REQUIRED_DURATION_PAYLOAD_VALUE,
        "cfg_scale": 0.5,
        "mode": "std",
    }


def _ffprobe_video(path: Path) -> Dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise KlingCommissionError(
            "ffprobe is not available on PATH -- cannot measure real video metadata",
            stage="ffprobe_process_failure",
        )
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KlingCommissionError(
            f"ffprobe process failed to run on {path}: {exc}",
            stage="ffprobe_process_failure",
        ) from exc
    if proc.returncode != 0:
        raise KlingCommissionError(
            f"ffprobe failed on {path}: {proc.stderr.strip()[-2000:]}",
            stage="ffprobe_process_failure",
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise KlingCommissionError(
            f"ffprobe produced unparseable output for {path}: {exc}",
            stage="ffprobe_parse_failure",
        ) from exc
    try:
        if not isinstance(data, dict):
            raise TypeError("ffprobe root must be a JSON object")
        streams = data["streams"]
        fmt = data["format"]
        if not isinstance(streams, list):
            raise TypeError("ffprobe streams must be a list")
        if not isinstance(fmt, dict):
            raise TypeError("ffprobe format must be an object")
        video_streams = [
            stream for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ]
        duration_seconds = float(fmt["duration"])
    except (TypeError, ValueError, KeyError) as exc:
        raise KlingCommissionError(
            f"ffprobe metadata is malformed for {path}: {exc}",
            stage="ffprobe_parse_failure",
        ) from exc
    if not video_streams:
        raise KlingCommissionError(
            f"no video stream found in {path}", stage="ffprobe_parse_failure"
        )
    v0 = video_streams[0]
    return {
        "width": v0.get("width"),
        "height": v0.get("height"),
        "video_codec": v0.get("codec_name"),
        "duration_seconds": duration_seconds,
        "format_name": fmt.get("format_name"),
    }


def print_dry_run_report(validation: Dict[str, Any]) -> None:
    print("=== Kling I2V commission -- DRY RUN (no provider/network call) ===\n")
    print(f"date                    : {validation['date']}")
    print(f"source_slot_id          : {validation['source_slot_id']}")
    print(f"source_path             : {validation['source_path']}")
    print(f"source_sha256           : {validation['source_sha256']}")
    print(f"test_video_slot_id      : {validation['test_video_slot_id']}")
    print(f"motion_prompt_sha256    : {validation['motion_prompt_sha256']}")
    print(f"motion_prompt_length    : {len(validation['motion_prompt']) if validation['motion_prompt'] else None}")
    print(f"duration_seconds        : {validation['duration_seconds']}")
    print(f"model (pinned)          : {CONFIRMED_KLING_VIDEO_MODEL}")
    print(f"endpoint (pinned)       : {CONFIRMED_KLING_VIDEO_ENDPOINT}")
    print(
        "source_public_url (san): "
        f"{validation['source_public_url_sanitized'] or '<not supplied -- required for --live>'}"
    )
    print(f"source_receipt_path     : {validation['source_receipt_path']}")
    print(f"ok                      : {validation['ok']}")
    if validation["reasons"]:
        print(f"reasons                 : {validation['reasons']}")
    print()

    if validation["ok"]:
        # A public URL may not have been supplied for a pure dry-run --
        # show the proposed payload shape with a placeholder in that case,
        # never fabricating a real URL.
        placeholder_url = validation["source_public_url"] or "<source-public-url-required-for-live>"
        payload = build_request_payload(placeholder_url, validation["motion_prompt"], validation["duration_seconds"])
        payload_sha256 = _sha256_text(json.dumps(payload, sort_keys=True))
        paths = commission_output_paths(validation["date"], validation["test_video_slot_id"])
        print("proposed request payload (prompt/image redacted -- see fields above for real values):")
        redacted_payload = {
            **payload,
            "prompt": f"<redacted, len={len(payload['prompt'])}>",
            "image": validation["source_public_url_sanitized"] or placeholder_url,
        }
        print(f"  {json.dumps(redacted_payload, indent=2)}")
        print(f"proposed request payload sha256 (with real prompt/url as supplied): {payload_sha256}")
        print(f"proposed video dir      : {paths['video_dir']}")
        print(f"proposed video stem     : {paths['video_stem']}")
        print(f"proposed manifest path  : {paths['manifest_path']}")
    print()
    print("=== RESULT: no subprocess call, no network call, no download, no file written. Dry-run only. ===")


def submit_and_process_live(validation: Dict[str, Any]) -> Dict[str, Any]:
    """Exactly one provider generation submission, then poll, then download.
    Mirrors pipeline/kling_apilena_api_executor.py's real, already-proven
    transport (_auth_header/_http_json/_download_file), never reimplements
    it. Endpoint/model are the pinned, historically-confirmed constants --
    never chosen dynamically, never a fallback."""
    payload = build_request_payload(
        validation["source_public_url"], validation["motion_prompt"], validation["duration_seconds"]
    )
    payload_sha256 = _sha256_text(json.dumps(payload, sort_keys=True))
    partial_live_state: Dict[str, Any] = {
        "provider_submission_attempted": False,
        "provider_task_id": None,
        "provider_task_status": None,
        "submitted_at_utc": None,
        "provider_result_url_sanitized": None,
        "saved_video_path": None,
        "output_sha256": None,
        "width": None,
        "height": None,
        "video_codec": None,
        "measured_duration_seconds": None,
        "container": None,
        "request_payload_sha256": payload_sha256,
        "current_stage": "provider_submission",
    }

    print(f"[LIVE] endpoint: {CONFIRMED_KLING_VIDEO_ENDPOINT}")
    print(f"[LIVE] model: {CONFIRMED_KLING_VIDEO_MODEL}")
    print(f"[LIVE] source_public_url: {_sanitize_reference_url(validation['source_public_url'])}")

    partial_live_state["provider_submission_attempted"] = True
    try:
        submit = _http_json("POST", CONFIRMED_KLING_VIDEO_ENDPOINT, payload)
    except OSError as exc:
        raise _live_failure(
            f"Kling image2video submission network failure: {exc}",
            "provider_network_failure", partial_live_state,
        ) from exc
    except json.JSONDecodeError as exc:
        raise _live_failure(
            f"Kling image2video submission response parse failure: {exc}",
            "provider_response_parse_failure", partial_live_state,
        ) from exc
    if not submit.get("ok"):
        raise _live_failure(
            f"Kling image2video submission failed: status={submit.get('status')} "
            f"body={submit.get('raw', '')[:2000]}",
            "provider_http_failure", partial_live_state,
        )

    task_id = str(((submit.get("json") or {}).get("data") or {}).get("task_id") or "").strip()
    if not task_id:
        raise _live_failure(
            f"Kling image2video response did not include data.task_id: "
            f"{submit.get('raw', '')[:2000]}",
            "provider_response_parse_failure", partial_live_state,
        )
    partial_live_state["provider_task_id"] = task_id
    partial_live_state["submitted_at_utc"] = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    partial_live_state["current_stage"] = "polling"

    poll_url = f"{CONFIRMED_KLING_VIDEO_ENDPOINT}/{task_id}"
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    task_status = ""
    poll_data: Dict[str, Any] = {}
    while time.time() < deadline:
        try:
            poll = _http_json("GET", poll_url)
        except OSError as exc:
            raise _live_failure(
                f"Kling task poll network failure: {exc}",
                "polling_network_failure", partial_live_state,
            ) from exc
        except json.JSONDecodeError as exc:
            raise _live_failure(
                f"Kling task poll response parse failure: {exc}",
                "polling_response_parse_failure", partial_live_state,
            ) from exc
        if not poll.get("ok"):
            raise _live_failure(
                f"Kling task poll failed: status={poll.get('status')} "
                f"body={poll.get('raw', '')[:2000]}",
                "polling_failure", partial_live_state,
            )
        poll_data = (poll.get("json") or {}).get("data") or {}
        task_status = str(poll_data.get("task_status") or "").strip().lower()
        partial_live_state["provider_task_status"] = task_status or None
        print(f"[LIVE] poll task_id={task_id} status={task_status}")
        if task_status in {"succeed", "failed"}:
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        raise _live_failure(
            f"Task {task_id} did not complete within {POLL_TIMEOUT_SECONDS}s",
            "polling_failure", partial_live_state,
        )

    if task_status != "succeed":
        raise _live_failure(
            f"Task {task_id} finished with status {task_status!r}, not 'succeed'",
            "polling_failure", partial_live_state,
        )

    videos = ((poll_data.get("task_result") or {}).get("videos")) or []
    if not videos or not isinstance(videos, list):
        raise _live_failure(
            f"Task {task_id} succeeded but response had no task_result.videos: {poll_data!r}",
            "result_url_extraction_failure", partial_live_state,
        )
    result_url = videos[0].get("url")
    if not result_url:
        raise _live_failure(
            f"Task {task_id} succeeded but first video entry had no url: {videos[0]!r}",
            "result_url_extraction_failure", partial_live_state,
        )
    partial_live_state["provider_result_url_sanitized"] = _sanitize_reference_url(result_url)
    partial_live_state["current_stage"] = "download"

    paths = commission_output_paths(validation["date"], validation["test_video_slot_id"])
    tmp_path = paths["video_dir"] / f"{paths['video_stem']}.tmp"
    final_path = paths["video_dir"] / f"{paths['video_stem']}.mp4"
    downloaded = False
    try:
        _download_file(result_url, tmp_path)
        downloaded = True
        tmp_path.replace(final_path)
    except OSError as exc:
        stage = "finalization_failure" if downloaded else "download_failure"
        verb = "Finalizing downloaded" if downloaded else "Downloading"
        raise _live_failure(
            f"{verb} result video failed: {exc}", stage, partial_live_state
        ) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    partial_live_state["saved_video_path"] = str(final_path)
    partial_live_state["current_stage"] = "ffprobe"
    try:
        probed = _ffprobe_video(final_path)
    except KlingCommissionError as exc:
        exc.partial_live_state = {
            **partial_live_state,
            "current_stage": exc.stage,
        }
        raise
    partial_live_state.update({
        "width": probed["width"],
        "height": probed["height"],
        "video_codec": probed["video_codec"],
        "measured_duration_seconds": probed["duration_seconds"],
        "container": probed["format_name"],
        "current_stage": "output_hash",
    })

    try:
        output_sha256 = _sha256_file(final_path)
    except OSError as exc:
        raise _live_failure(
            f"Hashing output video failed: {exc}",
            "output_hash_failure", partial_live_state,
        ) from exc
    partial_live_state["output_sha256"] = output_sha256
    partial_live_state["current_stage"] = "complete"

    return {
        "task_id": task_id,
        "task_status": task_status,
        "result_url_sanitized": _sanitize_reference_url(result_url),
        "saved_video_path": str(final_path),
        "output_sha256": output_sha256,
        "width": probed["width"],
        "height": probed["height"],
        "video_codec": probed["video_codec"],
        "measured_duration_seconds": probed["duration_seconds"],
        "container": probed["format_name"],
        "request_payload": payload,
        "request_payload_sha256": payload_sha256,
        "submitted_at_utc": partial_live_state["submitted_at_utc"],
    }


def build_commission_manifest(
    validation: Dict[str, Any],
    live_result: Optional[Dict[str, Any]],
    failure_stage: Optional[str] = None,
    provider_error: Optional[str] = None,
    partial_live_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    manifest = {
        "generated_by": "tools/lena_kling_i2v_commission_v1.py",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "kling",
        "model": CONFIRMED_KLING_VIDEO_MODEL,
        "endpoint": CONFIRMED_KLING_VIDEO_ENDPOINT,
        "date": validation["date"],
        "test_video_slot_id": validation["test_video_slot_id"],
        "source_slot_id": validation["source_slot_id"],
        "source_path": validation["source_path"],
        "source_sha256": validation["source_sha256"],
        "motion_prompt": validation["motion_prompt"],
        "motion_prompt_sha256": validation["motion_prompt_sha256"],
        "duration_seconds_requested": validation["duration_seconds"],
        "source_receipt_path": validation.get("source_receipt_path"),
        "source_public_url_sanitized": validation.get("source_public_url_sanitized"),
        "mode": "live" if live_result is not None or failure_stage else "dry_run",
        "attempt_count": 1 if (live_result is not None or failure_stage) else 0,
        "motion_control_claimed": False,
        "rule_zero_claimed": False,
    }
    if live_result:
        # Never persist the raw source URL or raw prompt inside the stored
        # request_payload -- the exact hash below still proves the exact
        # request that was actually submitted, without leaking either.
        manifest.update({
            "request_payload": {
                **live_result["request_payload"],
                "prompt": "<see motion_prompt field above>",
                "image": "<see source_public_url_sanitized field above>",
            },
            "request_payload_sha256": live_result["request_payload_sha256"],
            "provider_task_id": live_result["task_id"],
            "provider_task_status": live_result["task_status"],
            "provider_result_url_sanitized": live_result["result_url_sanitized"],
            "submitted_at_utc": live_result["submitted_at_utc"],
            "saved_video_path": live_result["saved_video_path"],
            "output_sha256": live_result["output_sha256"],
            "width": live_result["width"],
            "height": live_result["height"],
            "video_codec": live_result["video_codec"],
            "measured_duration_seconds": live_result["measured_duration_seconds"],
            "container": live_result["container"],
            "failure_stage": None,
            "provider_error": None,
        })
    elif failure_stage:
        manifest.update({
            "failure_stage": failure_stage,
            "provider_error": provider_error,
        })
        if partial_live_state:
            manifest.update(partial_live_state)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Commissions exactly one Kling image-to-video generation from one approved "
            "Lena still image plus one exact motion prompt, under a clearly test-scoped "
            "video identity. Reuses pipeline/kling_apilena_api_executor.py's transport "
            "primitives -- never modifies that file. Defaults to dry-run; --live performs "
            "the one real provider submission."
        )
    )
    parser.add_argument("--date", required=True, help="e.g. 2026-07-09")
    parser.add_argument("--source-slot-id", required=True, dest="source_slot_id")
    parser.add_argument("--source-path", required=True, dest="source_path")
    parser.add_argument("--test-video-slot-id", required=True, dest="test_video_slot_id")
    parser.add_argument(
        "--motion-prompt-file", required=True, dest="motion_prompt_file",
        help="Path to a text file containing the exact motion prompt, byte-for-byte. "
             "Must NOT end with a trailing CR/LF/CRLF byte -- rejected, never trimmed.",
    )
    parser.add_argument(
        "--duration-seconds", type=float, default=REQUIRED_DURATION_SECONDS, dest="duration_seconds",
        help=f"Must be exactly {REQUIRED_DURATION_SECONDS!r} in v1 -- no other value is accepted.",
    )
    parser.add_argument(
        "--source-public-url", default=None, dest="source_public_url",
        help="An already-existing, non-mutating public URL for the exact source image. "
             "This tool never uploads the source anywhere -- required for --live only.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.dry_run and args.live:
        print("[ABORT] --dry-run and --live are mutually exclusive.")
        return 1
    live = bool(args.live)

    prompt_path = Path(args.motion_prompt_file)
    if not prompt_path.exists():
        print(f"[ABORT] --motion-prompt-file not found: {prompt_path}")
        return 1
    raw_prompt_bytes = prompt_path.read_bytes()
    prompt_byte_error = validate_prompt_bytes(raw_prompt_bytes)
    if prompt_byte_error:
        print(f"[ABORT] --motion-prompt-file {prompt_path}: {prompt_byte_error}")
        return 1
    motion_prompt = raw_prompt_bytes.decode("utf-8")

    validation = validate_commission(
        date_str=args.date,
        source_slot_id=args.source_slot_id,
        source_path=Path(args.source_path),
        test_video_slot_id=args.test_video_slot_id,
        motion_prompt=motion_prompt,
        duration_seconds=args.duration_seconds,
        source_public_url=args.source_public_url,
        live=live,
    )
    print_dry_run_report(validation)

    if not live:
        return 0 if validation["ok"] else 1

    if not validation["ok"]:
        print("[ABORT] Validation failed -- refusing to make any provider call.")
        return 1

    manifest_path = commission_output_paths(args.date, args.test_video_slot_id)["manifest_path"]
    try:
        live_result = submit_and_process_live(validation)
    except KlingCommissionError as exc:
        failure_stage = getattr(exc, "stage", "unknown")
        manifest = build_commission_manifest(
            validation,
            live_result=None,
            failure_stage=failure_stage,
            provider_error=str(exc),
            partial_live_state=getattr(exc, "partial_live_state", None),
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[FAILED] {exc}")
        print(f"[FAILED] failure manifest written: {manifest_path}")
        return 1

    manifest = build_commission_manifest(validation, live_result=live_result)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[LIVE] saved video      : {live_result['saved_video_path']}")
    print(f"[LIVE] manifest written : {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
