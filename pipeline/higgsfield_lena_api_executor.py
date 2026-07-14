from __future__ import annotations

# Dedicated, safety-gated Higgsfield CLI executor for Lena -- v1.
#
# Architecture (approved 2026-07-09/10, after a real, authenticated CLI
# contract inspection -- see pipeline/prompting/lena_prompt_brain.py's
# Higgsfield section and the accepted 5-candidate readiness pack):
#
#   Lena prompt package -> this executor -> official `higgsfield` CLI
#   subprocess -> one generation job -> --wait --json result -> parse
#   provider response -> download result image -> save deterministic local
#   artifact -> write sanitized result manifest.
#
# This is a dedicated Higgsfield-only executor, not a generic provider
# abstraction -- it does not share code with, and never imports from,
# pipeline/kling_apilena_api_executor.py. It does not modify prompt
# generation (pipeline/prompting/lena_prompt_brain.py) or any diagnostic
# tool; it only reads their already-committed, already-validated output.
#
# CONFIRMED REAL PROVIDER CONTRACT (authenticated `higgsfield` CLI v1.1.10,
# `model get text2image_soul_v2 --json`, inspected read-only this session --
# not guessed):
#   job_type: text2image_soul_v2
#   params:   prompt (string, required), custom_reference_id (string|null),
#             aspect_ratio (enum incl. "9:16", default "1:1"),
#             image_references (array, max 1), quality (enum "1.5k"/"2k").
#   No Prompt Enhancer parameter exists in this schema -- see doctrine note
#   below. No negative-prompt parameter exists either.
#   Lena's confirmed Soul: name="Lena", type="soul_2",
#   id=90a293d7-f3af-4377-8751-3304a27b6f31 (`soul-id list --json`,
#   re-confirmed 2026-07-12 -- the provider account's live Soul ID rotated
#   at some point after the original 2026-07-09/10 confirmation; the prior
#   id, 1f1200e4-1cc9-4504-ac1c-3304b687e3c1, is no longer present on the
#   account and is preserved only as historical fact in already-recorded
#   manifests/evidence -- never used as a default for new live submissions).
#
# PROMPT ENHANCER DOCTRINE: the authenticated schema for text2image_soul_v2
# exposes no enhancer-shaped parameter at all (searched for enhance/
# enhancer/enhance_prompt/prompt_enhancer/improve_prompt/rewrite_prompt/
# prompt_magic -- none present). This executor therefore does NOT invent an
# enhancer flag, does NOT claim to force Prompt Enhancer OFF, and does NOT
# fail startup over its absence. It simply is not a controllable parameter
# on this model/CLI version.
#
# NEGATIVE PROMPT DOCTRINE: no negative-prompt parameter exists either.
# Omission is the correct (and only possible) behavior -- never invented,
# never sent.
#
# SOUL ID DOCTRINE: custom_reference_id is identity/config metadata, not a
# secret (OAuth credentials remain entirely owned by the `higgsfield` CLI's
# own local credentials file -- this module never reads, writes, or prints
# them). Per explicit architecture decision, Lena's Soul ID is NOT stored in
# .env; it is a documented constant here with an explicit CLI override.
#
# HARD SAFETY GATES (v1, all enforced by construction):
#   - --dry-run is the default; --live requires the flag explicitly.
#   - Exactly one --slot-id per invocation. No batch flag exists in v1.
#   - At most one provider subprocess call, ever, per invocation. No retry,
#     no reroll, no fallback generation.
#   - No queue/publish/R2 import anywhere in this file.
#   - No .env read or write (no pipeline.env_loader import -- nothing
#     Higgsfield-related lives in .env).
#   - No OAuth credential file is read, written, or printed by this module.
#   - No secret/token/cookie is ever printed; result URLs are sanitized
#     before any print/log/manifest write.
#   - The exact final prompt text is never rewritten, shortened, or
#     hand-composed -- it is reproduced only via the same committed
#     generator functions already used to build the accepted prompt.
#
# Run (dry-run, default, no provider/network call):
#   python pipeline/higgsfield_lena_api_executor.py --date 2026-07-09 --slot-id readypack0709-pack000-05-photo
#
# Run (live, exactly one real provider call -- needs --live explicitly):
#   python pipeline/higgsfield_lena_api_executor.py --date 2026-07-09 --slot-id readypack0709-pack000-05-photo --live

import argparse
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = ROOT / "tools" / "diagnostics"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

# Reuses the already-committed, already-validated pack builder/report --
# the single source of truth for what a photo-dump-pack slot's final
# image_prompt and metadata actually are. Never reimplemented here.
from lena_higgsfield_photo_dump_dryrun import build_report  # noqa: E402

# Reuses the already-committed hard-exclusion gate -- the exact same
# validation the accepted 5-candidate readiness pack was screened with.
# Never loosened or recomputed here.
from lena_higgsfield_prompt_library_dryrun import _hard_exclude_reasons  # noqa: E402


# --- Confirmed provider contract constants (see module docstring) ----------

HIGGSFIELD_CLI_BINARY = "higgsfield"
HIGGSFIELD_IMAGE_JOB_TYPE = "text2image_soul_v2"
HIGGSFIELD_ASPECT_RATIO = "9:16"

# Confirmed once during the authenticated contract-inspection session
# (2026-07-09/10 later session). Not re-verified per invocation -- calling
# `higgsfield version` here would be an extra CLI call beyond the one
# approved generation call this executor is allowed to make.
HIGGSFIELD_CLI_CONFIRMED_VERSION = "1.1.10"

# Lena's confirmed Soul (`higgsfield soul-id list --json`, authenticated,
# re-confirmed 2026-07-12 -- the account's live Soul ID rotated since the
# original 2026-07-09/10 confirmation; the prior id
# 1f1200e4-1cc9-4504-ac1c-3304b687e3c1 is no longer present on the
# provider account). Non-secret identity/config metadata, not read from or
# written to .env (see SOUL ID DOCTRINE above). This is the single, current
# default used for every NEW live submission -- it is never chosen from a
# set, and historical evidence recorded under the prior id remains valid
# historical fact (see pipeline/identity/lena_higgsfield_identity.py's
# APPROVED_CUSTOM_REFERENCE_IDS for the separate, read-only evidence-side
# policy that accepts either id).
DEFAULT_LENA_CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
CONFIRMED_LENA_SOUL_NAME = "Lena"
CONFIRMED_LENA_SOUL_TYPE = "soul_2"

# Exact count_per_pack used to generate the accepted 2026-07-09 readiness
# pack (library_prefix="readypack0709", packs=12, count_per_pack=10). This
# is not a general-purpose default -- it is the one confirmed value needed
# to deterministically reproduce those exact slots. See resolve_prompt_source.
KNOWN_PHOTO_DUMP_PACK_COUNT = 10
POSE_BANK_PATH = ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_pose_body_language_bank_v1.json"

_PACK_SLOT_ID_PATTERN = re.compile(
    r"^(?P<library_prefix>[A-Za-z0-9]+)-pack(?P<pack_index>\d{3})-"
    r"(?P<image_index>\d{2})-(?P<media_type>photo|video)$"
)

_POSE_SEGMENT_PATTERN = re.compile(r"Pose:\s*(.*?)\s*Expression:", flags=re.S)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


class PromptSourceError(Exception):
    """Raised whenever the exact prompt source for a slot_id cannot be
    deterministically and unambiguously resolved. Always fails closed --
    this executor never falls back to a guessed, hand-written, or
    bare-single-package prompt when the real source is ambiguous."""


class ProviderCallError(Exception):
    """Raised for any provider subprocess/parse/download failure. Always
    fails closed -- never leaves a failed job looking like a successful
    artifact."""


# --- Prompt-source resolution ----------------------------------------------

def resolve_prompt_source(date_str: str, slot_id: str) -> dict:
    """Reproduces the exact accepted image package for slot_id, using only
    the already-committed generator/report code. Only one source shape is
    supported in v1: a photo-dump-pack slot_id
    ('<library_prefix>-pack<NNN>-<NN>-photo'), matching how the 5 accepted
    readiness candidates were actually generated
    (generate_higgsfield_photo_dump_pack via build_report). A bare/direct
    single-slot origin is deliberately NOT supported in v1: the same
    slot_id shape is ambiguous between the two origins, and this executor
    fails closed rather than guessing which one produced a given slot_id."""
    match = _PACK_SLOT_ID_PATTERN.match(slot_id)
    if not match:
        raise PromptSourceError(
            f"slot_id {slot_id!r} does not match the supported photo-dump "
            "pack naming pattern '<prefix>-pack<NNN>-<NN>-photo'. Direct "
            "single-slot resolution is not implemented in this v1 executor "
            "(ambiguous source -- fails closed rather than guessing)."
        )
    library_prefix = match.group("library_prefix")
    pack_index = match.group("pack_index")
    slot_prefix = f"{library_prefix}-pack{pack_index}"

    pack_report = build_report(date_str, slot_prefix, KNOWN_PHOTO_DUMP_PACK_COUNT)
    for image in pack_report["images"]:
        if image["slot_id"] == slot_id:
            return {
                "resolver": "photo_dump_pack",
                "slot_prefix": slot_prefix,
                "pack_count": KNOWN_PHOTO_DUMP_PACK_COUNT,
                "image": image,
                "pack_variety_warnings": pack_report["variety_warnings"],
            }

    raise PromptSourceError(
        f"slot_id {slot_id!r} not found after regenerating pack "
        f"{slot_prefix!r} at count={KNOWN_PHOTO_DUMP_PACK_COUNT} for date "
        f"{date_str!r}. Refusing to fall back to a bare "
        "generate_higgsfield_prompt_package() call -- that would silently "
        "reproduce a different prompt than the one actually accepted."
    )


def _extract_pose_text(prompt: str) -> str:
    match = _POSE_SEGMENT_PATTERN.search(prompt)
    return match.group(1) if match else ""


def _canonical_pose_text(image: dict[str, Any]) -> str:
    pose_id = str(image.get("pose_body_language_id") or "").strip()
    if not pose_id:
        return ""
    try:
        bank = json.loads(POSE_BANK_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ""
    for item in bank.get("combos", []):
        if not isinstance(item, dict) or item.get("pose_body_language_id") != pose_id:
            continue
        text = item.get("text")
        return text.strip() if isinstance(text, str) else ""
    return ""


# --- Safety-gate validation (dry-run and pre-live) --------------------------

def validate_candidate(source: dict, expected_prompt_path: Optional[Path]) -> dict:
    """Runs every check that must pass before a provider call is even
    considered. Returns a dict with 'ok' plus every reason found -- never
    raises itself, so callers can report a full picture before failing."""
    image = source["image"]
    reasons: list[str] = []

    hard_exclude_reasons = _hard_exclude_reasons(image)
    reasons.extend(hard_exclude_reasons)

    prompt_matches_expected: Optional[bool] = None
    if expected_prompt_path is not None:
        if not expected_prompt_path.exists():
            reasons.append(f"--expected-prompt-file not found: {expected_prompt_path}")
            prompt_matches_expected = False
        else:
            # Exact byte-for-byte comparison. No whitespace normalization,
            # no stripping beyond reading the file's raw bytes -- per
            # explicit instruction. Regenerated prompt is encoded utf-8 to
            # match, since generate_higgsfield_prompt_package() always
            # produces a plain Python str.
            expected_bytes = expected_prompt_path.read_bytes()
            actual_bytes = image["image_prompt"].encode("utf-8")
            prompt_matches_expected = expected_bytes == actual_bytes
            if not prompt_matches_expected:
                reasons.append(
                    "regenerated image_prompt does not byte-for-byte match "
                    f"--expected-prompt-file ({len(actual_bytes)} bytes "
                    f"regenerated vs {len(expected_bytes)} bytes expected)"
                )

    return {
        "ok": not reasons,
        "hard_exclude_reasons": hard_exclude_reasons,
        "prompt_matches_expected": prompt_matches_expected,
        "all_reasons": reasons,
    }


def render_dry_run_contract(
    date_str: str,
    slot_id: str,
    source: dict,
    custom_reference_id: str,
    expected_prompt_path: Optional[Path] = None,
) -> dict[str, Any]:
    validation = validate_candidate(source, expected_prompt_path)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        print_dry_run_report(date_str, slot_id, source, custom_reference_id, validation)
    return {
        "stdout": output.getvalue(),
        "validation": validation,
        "ok": validation["ok"],
        "date": date_str,
        "slot_id": slot_id,
    }


# --- Provider argv construction ---------------------------------------------

def build_provider_argv(prompt: str, custom_reference_id: str) -> list[str]:
    """Constructed as a list, never shell-concatenated text. subprocess is
    invoked with this list and shell=False."""
    return [
        HIGGSFIELD_CLI_BINARY,
        "generate",
        "create",
        HIGGSFIELD_IMAGE_JOB_TYPE,
        "--prompt",
        prompt,
        "--custom_reference_id",
        custom_reference_id,
        "--aspect_ratio",
        HIGGSFIELD_ASPECT_RATIO,
        "--wait",
        "--json",
    ]


def _redacted_argv_for_display(argv: list[str], prompt: str) -> list[str]:
    """Never expose the full prompt in any printed/logged command string --
    only its length. The real argv (unredacted) is used for the actual
    subprocess call; this is display-only."""
    redacted = list(argv)
    for i, item in enumerate(redacted):
        if item == prompt:
            redacted[i] = f"<redacted, len={len(prompt)}>"
    return redacted


# --- Result parsing / sanitization ------------------------------------------

def _sanitize_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        return "<no url>"
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path[:24]}...<redacted len={len(url)}>"


def _canonical_result_urls(obj: Any) -> list[str]:
    """Extracts only the canonical top-level 'result_url' field(s) from a
    completed Higgsfield job response -- never recurses into nested
    structures. Evidence (2026-07-10, real completed text2image_soul_v2 job,
    via the safe read-only `generate list --image --json` lookup): a job
    object has exactly one real generation output, 'result_url' (the
    full-res image), alongside 'min_result_url' (a thumbnail -- not treated
    as a result) and an unrelated 'params.style.url' (the style preset's own
    CDN thumbnail, not a generation output at all). The prior implementation
    walked the entire JSON tree for any http(s)-looking string and counted
    all three, incorrectly triggering the ">1 result URL" fail-closed path
    on every successful job. This function reads only the top-level
    'result_url' key -- 'min_result_url' and anything nested (params, style,
    or otherwise) is never inspected, so it can never be mistaken for a
    result.

    The raw shape of `generate create ... --wait --json` itself was not
    captured this session (the live run's stdout was not persisted before
    the prior version aborted), so this defensively accepts either a single
    job object or a list containing job objects (matching `generate list`'s
    shape) -- but in both cases only ever reads 'result_url' at the top
    level of each candidate object."""
    if isinstance(obj, dict):
        candidates = [obj]
    elif isinstance(obj, list):
        candidates = [item for item in obj if isinstance(item, dict)]
    else:
        candidates = []

    urls: list[str] = []
    for candidate in candidates:
        value = candidate.get("result_url")
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            urls.append(value)

    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def _find_first_str_field(obj: Any, keys: tuple[str, ...]) -> Optional[str]:
    """Best-effort, shallow-then-nested lookup for a job id/status style
    field. Not schema-confirmed (same caveat as _collect_result_urls) --
    used only for informational manifest fields, never for control flow
    that could mask a real failure."""
    if isinstance(obj, dict):
        for key in keys:
            v = obj.get(key)
            if isinstance(v, str) and v:
                return v
        for v in obj.values():
            found = _find_first_str_field(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_first_str_field(item, keys)
            if found:
                return found
    return None


def _detect_image_extension(data: bytes) -> str:
    """Never blindly rename bytes as .png. Sniffs real magic bytes."""
    if data.startswith(_PNG_MAGIC):
        return ".png"
    if data.startswith(_JPEG_MAGIC):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def _download(url: str, destination: Path) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "content-bot-higgsfield/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        data = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return data


# --- Paths -------------------------------------------------------------------

def library_path(date_str: str, slot_id: str, extension: str) -> Path:
    return ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed{extension}"


def manifest_path(date_str: str, slot_id: str) -> Path:
    return ROOT / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"


# --- Manifest ------------------------------------------------------------

def build_manifest(
    date_str: str,
    slot_id: str,
    source: dict,
    custom_reference_id: str,
    live_result: Optional[dict],
) -> dict:
    image = source["image"]
    prompt = image["image_prompt"]
    prompt_bytes = prompt.encode("utf-8")

    manifest = {
        "provider": "higgsfield",
        "cli_version": HIGGSFIELD_CLI_CONFIRMED_VERSION,
        "job_type": HIGGSFIELD_IMAGE_JOB_TYPE,
        "date": date_str,
        "slot_id": slot_id,
        "source_resolver": source["resolver"],
        "source_slot_prefix": source["slot_prefix"],
        "source_pack_count": source["pack_count"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "custom_reference_id": custom_reference_id,
        "cli_soul_name": CONFIRMED_LENA_SOUL_NAME,
        "cli_soul_type": CONFIRMED_LENA_SOUL_TYPE,
        "aspect_ratio": HIGGSFIELD_ASPECT_RATIO,
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "prompt_length": len(prompt),
        "image_prompt": prompt,
        "package_soul_name": image.get("soul_name"),
        "package_soul_version": image.get("soul_version"),
        "package_soul_selection_mode": image.get("soul_selection_mode"),
        "lane": image.get("lane"),
        "wardrobe_outfit_id": image.get("wardrobe_outfit_id"),
        "wardrobe_outfit_name": image.get("wardrobe_outfit_name"),
        "wardrobe_silhouette_class": image.get("wardrobe_silhouette_class"),
        "effective_wardrobe_silhouette_class": image.get("effective_wardrobe_silhouette_class"),
        "text_surface_risk_terms_found": image.get("text_surface_risk_terms_found", []),
        "pose_body_language_id": image.get("pose_body_language_id"),
        "pose_body_language_label": image.get("pose_body_language_label"),
        "pose_text": _canonical_pose_text(image),
        # Persisted (2026-07-10) so a real, non-fabricated visual_style
        # (f"{camera_text}; {lighting_text}", matching the Kling package
        # builder's own convention) can be built later without re-parsing
        # the "Camera: .../Lighting: ..." sentences out of image_prompt.
        # None (not a fabricated default) if the source package predates
        # this field -- same optional-field convention as pose_body_
        # language_id/expression_gaze_id above.
        "camera_text": image.get("camera_text"),
        "lighting_text": image.get("lighting_text"),
        "expression_gaze_id": image.get("expression_gaze_id"),
        "expression_gaze_label": image.get("expression_gaze_label"),
        "expression_text": image["validation"]["final_expression_text"],
        "expression_safe_fallback_used": image["validation"]["expression_safe_fallback_used"],
        "expression_safe_fallback_reason": image["validation"]["expression_safe_fallback_reason"],
        "expression_scene_conflict_terms": image["validation"][
            "expression_scene_gaze_conflict_terms_found"
        ],
        "hard_exclude_reasons": _hard_exclude_reasons(image),
        "pack_variety_warnings": source["pack_variety_warnings"],
        "live_attempt_count": 1 if live_result else 0,
        "retry_count": 0,
    }

    if live_result:
        manifest.update(
            {
                "provider_job_id": live_result.get("job_id"),
                "provider_status": live_result.get("status"),
                "result_urls_sanitized": [_sanitize_url(u) for u in live_result.get("result_urls", [])],
                "result_url_count": len(live_result.get("result_urls", [])),
                "saved_image_path": live_result.get("saved_image_path"),
                "image_format_detected": live_result.get("image_format_detected"),
            }
        )

    retry_contract = image.get("retry_execution_contract")
    if isinstance(retry_contract, dict):
        manifest["retry_execution_contract"] = retry_contract

    return manifest


def _load_retry_decision_source(retry_decision_artifact: Path) -> tuple[str, str, dict, Path]:
    from tools.strategy import lena_execute_retry_decision_v1 as retry_consumer  # noqa: E402

    artifact, source = retry_consumer.load_retry_execution_source(retry_decision_artifact)
    return str(artifact["as_of_date"]), str(artifact["retry_slot_id"]), source, retry_decision_artifact.resolve()


# --- Live execution ----------------------------------------------------------

def run_live(date_str: str, slot_id: str, source: dict, custom_reference_id: str) -> dict:
    image = source["image"]
    prompt = image["image_prompt"]
    argv = build_provider_argv(prompt, custom_reference_id)

    # Windows fix (2026-07-10): subprocess.run([...], shell=False) calls
    # CreateProcess directly, which does not perform PATHEXT resolution the
    # way a shell or shutil.which() does -- a bare "higgsfield" fails with
    # FileNotFoundError ([WinError 2]) when the real executable on PATH is
    # higgsfield.CMD. Resolve the actual executable path once, here, right
    # at the subprocess boundary, and swap only argv[0] -- the logical
    # provider command contract (build_provider_argv()) is unchanged.
    resolved_binary = shutil.which(HIGGSFIELD_CLI_BINARY)
    if not resolved_binary:
        raise ProviderCallError(
            f"Could not resolve {HIGGSFIELD_CLI_BINARY!r} via shutil.which() -- "
            "the Higgsfield CLI does not appear to be on PATH."
        )
    resolved_argv = [resolved_binary, *argv[1:]]

    print(f"[LIVE] resolved executable: {resolved_binary}")
    print(f"[LIVE] invoking: {_redacted_argv_for_display(resolved_argv, prompt)}")
    try:
        result = subprocess.run(resolved_argv, capture_output=True, text=True, shell=False, check=False)
    except OSError as exc:
        # Narrow catch: only the process-spawn boundary itself, not the
        # whole function. A spawn failure must fail through the executor's
        # controlled error path, not surface as an uncaught traceback.
        raise ProviderCallError(
            f"Failed to spawn the Higgsfield CLI process ({resolved_binary!r}): {exc}"
        ) from exc

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-2000:]
        raise ProviderCallError(
            f"higgsfield generate create exited {result.returncode}. "
            f"stderr (tail): {stderr_tail}"
        )

    stdout = result.stdout or ""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProviderCallError(
            f"Failed to parse --json output as JSON: {exc}. "
            f"stdout length was {len(stdout)} chars."
        ) from exc

    job_id = _find_first_str_field(parsed, ("job_id", "id"))
    status = _find_first_str_field(parsed, ("status",))
    result_urls = _canonical_result_urls(parsed)

    if not result_urls:
        raise ProviderCallError(
            "No canonical result_url found in provider response -- "
            "refusing to proceed. Only the top-level 'result_url' field is "
            "treated as a generation output; no other field (including "
            "'min_result_url' or anything nested) is considered."
        )
    if len(result_urls) > 1:
        raise ProviderCallError(
            f"Provider response contained {len(result_urls)} distinct "
            "top-level result_url values where exactly one job (and "
            "therefore exactly one result_url) was expected. This executor "
            "refuses to silently pick one. Manual review required."
        )

    result_url = result_urls[0]
    try:
        image_bytes = _download(result_url, ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.tmp")
    except Exception as exc:
        raise ProviderCallError(f"Download of result image failed: {exc}") from exc

    extension = _detect_image_extension(image_bytes)
    final_path = library_path(date_str, slot_id, extension)
    tmp_path = ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.tmp"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(final_path)

    return {
        "job_id": job_id,
        "status": status,
        "result_urls": result_urls,
        "saved_image_path": str(final_path),
        "image_format_detected": extension,
    }


# --- Reporting ---------------------------------------------------------------

def print_dry_run_report(date_str: str, slot_id: str, source: dict, custom_reference_id: str, validation: dict) -> None:
    image = source["image"]
    prompt = image["image_prompt"]
    argv = build_provider_argv(prompt, custom_reference_id)

    print("=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===\n")
    print(f"date                    : {date_str}")
    print(f"slot_id                 : {slot_id}")
    print(f"source resolver         : {source['resolver']} (slot_prefix={source['slot_prefix']!r}, pack_count={source['pack_count']})")
    print(f"job_type                : {HIGGSFIELD_IMAGE_JOB_TYPE}")
    print(f"custom_reference_id     : {custom_reference_id}")
    print(f"cli soul identity       : name={CONFIRMED_LENA_SOUL_NAME!r} type={CONFIRMED_LENA_SOUL_TYPE!r}")
    print(f"aspect_ratio            : {HIGGSFIELD_ASPECT_RATIO}")
    print(f"prompt_length           : {len(prompt)} chars")
    print(f"prompt_sha256           : {hashlib.sha256(prompt.encode('utf-8')).hexdigest()}")
    print(f"prompt_matches_expected : {validation['prompt_matches_expected']}")
    print(f"hard_exclude_reasons    : {validation['hard_exclude_reasons']}")
    print(f"validation ok           : {validation['ok']}")
    print()
    print("provider argv (would be invoked under --live; prompt redacted for display):")
    print(f"  {_redacted_argv_for_display(argv, prompt)}")
    print()
    print(f"proposed output path    : {library_path(date_str, slot_id, '.png')} (extension confirmed only on real download)")
    print(f"proposed manifest path  : {manifest_path(date_str, slot_id)}")
    print()
    print("=== RESULT: no subprocess call, no network call, no file written. Dry-run only. ===")


# --- Main ----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="e.g. 2026-07-09")
    parser.add_argument("--slot-id", dest="slot_id")
    parser.add_argument("--retry-decision-artifact", type=Path)
    parser.add_argument(
        "--custom-reference-id", dest="custom_reference_id",
        default=DEFAULT_LENA_CUSTOM_REFERENCE_ID,
        help="Higgsfield Soul custom_reference_id (default: Lena's confirmed Soul ID)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--expected-prompt-file", dest="expected_prompt_file", default=None,
        help="If given, hard-fail before any provider call unless the regenerated "
             "image_prompt matches this file byte-for-byte.",
    )
    args = parser.parse_args()

    if args.dry_run and args.live:
        print("[ABORT] --dry-run and --live are mutually exclusive.")
        return 1
    live = bool(args.live)

    expected_prompt_path = Path(args.expected_prompt_file) if args.expected_prompt_file else None

    if args.retry_decision_artifact is not None:
        if args.date or args.slot_id:
            print("[ABORT] --retry-decision-artifact is mutually exclusive with --date/--slot-id.")
            return 1
        if expected_prompt_path is not None:
            print("[ABORT] --expected-prompt-file is not supported with --retry-decision-artifact.")
            return 1
        try:
            date_str, slot_id, source, _ = _load_retry_decision_source(args.retry_decision_artifact)
        except Exception as exc:
            print(f"[ABORT] {exc}")
            return 1
    else:
        if not args.date or not args.slot_id:
            print("[ABORT] either --retry-decision-artifact or both --date and --slot-id are required.")
            return 1
        date_str = args.date
        slot_id = args.slot_id
        try:
            source = resolve_prompt_source(date_str, slot_id)
        except PromptSourceError as exc:
            print(f"[ABORT] {exc}")
            return 1

    validation = validate_candidate(source, expected_prompt_path)

    if not live:
        print_dry_run_report(date_str, slot_id, source, args.custom_reference_id, validation)
        return 0 if validation["ok"] else 1

    # --live: run every dry-run validation first.
    print_dry_run_report(date_str, slot_id, source, args.custom_reference_id, validation)
    if not validation["ok"]:
        print("[ABORT] Validation failed -- refusing to make a provider call.")
        return 1

    try:
        live_result = run_live(date_str, slot_id, source, args.custom_reference_id)
    except ProviderCallError as exc:
        print(f"[FAILED] {exc}")
        print("[FAILED] No manifest written, no artifact saved as successful.")
        return 1

    manifest = build_manifest(date_str, slot_id, source, args.custom_reference_id, live_result)
    mpath = manifest_path(date_str, slot_id)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[LIVE] saved image     : {live_result['saved_image_path']}")
    print(f"[LIVE] manifest written: {mpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
