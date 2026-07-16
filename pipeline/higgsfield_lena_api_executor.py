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
#   Lena's confirmed Soul: name="Lena", type="Soul 2.0",
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
# Run (live, exact approved path only):
#   python pipeline/higgsfield_lena_api_executor.py --handoff-artifact <packet> --approval-artifact <approval> --live

import argparse
import copy
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

from pipeline.influencer_nodes.lena import autonomy_ladder  # noqa: E402

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
HANDOFF_REPORT_TYPE = "lena_next_live_image_handoff"
HANDOFF_SCHEMA_VERSION = "v1"
HANDOFF_EXECUTION_OWNER = "claude"
HANDOFF_EXECUTOR_TYPE = "higgsfield_cli"

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
CONFIRMED_LENA_SOUL_TYPE = "Soul 2.0"

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

    def __init__(
        self,
        message: str,
        *,
        stage: str = "provider_failure",
        subprocess_start_attempted: bool = False,
        provider_submission_may_have_occurred: bool = False,
        provider_job_id: str | None = None,
        provider_status: str | None = None,
        output_path: str | None = None,
        image_format_detected: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.subprocess_start_attempted = subprocess_start_attempted
        self.provider_submission_may_have_occurred = provider_submission_may_have_occurred
        self.provider_job_id = provider_job_id
        self.provider_status = provider_status
        self.output_path = output_path
        self.image_format_detected = image_format_detected


class HandoffArtifactError(Exception):
    """Raised when a Claude/Higgsfield handoff artifact fails validation."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


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


def _validate_handoff_packet(handoff_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    report = _load_handoff_report(handoff_path)
    date_str = str(report["date"]).strip()
    slot_id = str(report["selected_slot_id"]).strip()
    structured = report.get("structured_executor_inputs", {})
    _require_handoff(isinstance(structured, dict), "handoff_missing_executor_inputs", f"{handoff_path} has no structured_executor_inputs object")

    _require_handoff(structured.get("model") == HIGGSFIELD_IMAGE_JOB_TYPE, "handoff_model_mismatch", f"{handoff_path} model must be {HIGGSFIELD_IMAGE_JOB_TYPE!r}")
    _require_handoff(structured.get("aspect_ratio") == HIGGSFIELD_ASPECT_RATIO, "handoff_aspect_mismatch", f"{handoff_path} aspect_ratio must be {HIGGSFIELD_ASPECT_RATIO!r}")
    _require_handoff(structured.get("provider") == HIGGSFIELD_CLI_BINARY, "handoff_provider_mismatch", f"{handoff_path} provider must be {HIGGSFIELD_CLI_BINARY!r}")
    _require_handoff(structured.get("executor_type") == HANDOFF_EXECUTOR_TYPE, "handoff_executor_type_mismatch", f"{handoff_path} executor_type must be {HANDOFF_EXECUTOR_TYPE!r}")
    _require_handoff(structured.get("repo_executor_path") == "pipeline/higgsfield_lena_api_executor.py", "handoff_repo_executor_path_mismatch", f"{handoff_path} repo_executor_path must be pipeline/higgsfield_lena_api_executor.py")
    _require_handoff(structured.get("negative_prompt_enabled") is False, "handoff_negative_prompt_enabled", f"{handoff_path} must keep negative_prompt_enabled false")
    _require_handoff(structured.get("live_execution_authorized") is False, "handoff_live_not_authorized", f"{handoff_path} must keep live_execution_authorized false")
    _require_handoff(report.get("live_execution_authorized") is False, "handoff_live_not_authorized", f"{handoff_path} must keep live_execution_authorized false")
    _require_handoff(report.get("generation_approval_required") is True, "handoff_generation_approval_required", f"{handoff_path} must require generation approval")
    _require_handoff(report.get("manual_operator_approval_required") is True, "handoff_manual_operator_approval_required", f"{handoff_path} must require manual operator approval")
    _require_handoff(report.get("provider_call_performed") is False, "handoff_provider_call_performed", f"{handoff_path} must not claim provider call performed")
    _require_handoff(report.get("generation_performed") is False, "handoff_generation_performed", f"{handoff_path} must not claim generation performed")
    _require_handoff(report.get("publish_authorized") is False, "handoff_publish_authorized", f"{handoff_path} must not claim publish authorization")
    _require_handoff(report.get("manual_publish_review_required") is True, "handoff_manual_publish_review_required", f"{handoff_path} must keep manual publish review required")
    _require_handoff(report.get("packet_state") == "packet_valid_for_claude_review", "handoff_packet_state_invalid", f"{handoff_path} packet_state must remain review-only")
    _require_handoff(report.get("dry_run_executor_contract_state") == "ready", "handoff_contract_state_invalid", f"{handoff_path} dry_run_executor_contract_state must be ready")
    _require_handoff(report.get("live_execution_state") == "blocked", "handoff_live_state_invalid", f"{handoff_path} live_execution_state must remain blocked")

    soul = structured.get("soul_metadata", {})
    _require_handoff(isinstance(soul, dict), "handoff_missing_soul_metadata", f"{handoff_path} has no soul_metadata object")
    _require_handoff(soul.get("name") == CONFIRMED_LENA_SOUL_NAME, "handoff_soul_name_mismatch", f"{handoff_path} soul name mismatch")
    _require_handoff(soul.get("type") == CONFIRMED_LENA_SOUL_TYPE, "handoff_soul_type_mismatch", f"{handoff_path} soul type mismatch")
    _require_handoff(soul.get("custom_reference_id") == DEFAULT_LENA_CUSTOM_REFERENCE_ID, "handoff_soul_reference_mismatch", f"{handoff_path} custom_reference_id mismatch")
    _require_handoff(soul.get("identity_is_prompt_instruction") is False, "handoff_soul_prompt_instruction_invalid", f"{handoff_path} soul identity must remain metadata")

    handoff_rel = _repo_relative_path(handoff_path)
    expected_dry = f"python pipeline/higgsfield_lena_api_executor.py --handoff-artifact {handoff_rel}"
    expected_live = f"{expected_dry} --live"
    _require_handoff(structured.get("dry_run_command") == expected_dry, "handoff_dry_run_command_mismatch", f"{handoff_path} dry_run_command must be {expected_dry!r}")
    _require_handoff(structured.get("live_command") == expected_live, "handoff_live_command_mismatch", f"{handoff_path} live_command must be {expected_live!r}")
    _require_handoff(structured.get("dry_run_argv") == ["python", "pipeline/higgsfield_lena_api_executor.py", "--handoff-artifact", handoff_rel], "handoff_dry_run_argv_mismatch", f"{handoff_path} dry_run_argv must match the repo-adapter handoff command")
    _require_handoff(structured.get("live_argv") == ["python", "pipeline/higgsfield_lena_api_executor.py", "--handoff-artifact", handoff_rel, "--live"], "handoff_live_argv_mismatch", f"{handoff_path} live_argv must match the blocked live command")

    recommendation_path = _resolve_repo_path(report.get("source_recommendation_artifact_path", ""))
    learning_path = _resolve_repo_path(report.get("source_learning_artifact_path", ""))
    queue_path = _resolve_repo_path(report.get("source_queue_dry_run_artifact_path", ""))
    packet_path = _resolve_repo_path(report.get("selected_prompt_input_artifact_path", ""))
    for label, path_value in (
        ("recommendation", recommendation_path),
        ("learning", learning_path),
        ("queue", queue_path),
        ("selected prompt input", packet_path),
    ):
        _require_handoff(path_value.is_file(), "handoff_missing_source_artifact", f"{handoff_path} missing required {label} artifact: {path_value}")

    _require_handoff(report.get("source_recommendation_artifact_sha256") == _sha256_file(recommendation_path), "handoff_recommendation_sha_mismatch", f"{handoff_path} recommendation sha mismatch")
    _require_handoff(report.get("source_learning_artifact_sha256") == _sha256_file(learning_path), "handoff_learning_sha_mismatch", f"{handoff_path} learning sha mismatch")
    _require_handoff(report.get("source_queue_dry_run_artifact_sha256") == _sha256_file(queue_path), "handoff_queue_sha_mismatch", f"{handoff_path} queue sha mismatch")
    _require_handoff(report.get("selected_prompt_input_artifact_sha256") == _sha256_file(packet_path), "handoff_candidate_artifact_sha_mismatch", f"{handoff_path} selected prompt input artifact sha mismatch")

    recommendation = load_report(recommendation_path, expected_report_type="lena_next_generation_step", expected_date=date_str)
    learning_path_loaded, learning = load_learning_report(recommendation, date_str)
    queue_loaded_path, queue_report = load_queue_report(date_str)
    packet_report = load_content_packet_report(packet_path, date_str)
    from tools.lena_higgsfield_generation_approval_v1 import (  # noqa: E402
        validate_selected_candidate_binding,
    )

    selected_candidate_binding = validate_selected_candidate_binding(report)

    _require_handoff(learning_path_loaded == learning_path, "handoff_learning_path_mismatch", f"{handoff_path} learning artifact path mismatch")
    _require_handoff(queue_loaded_path == queue_path, "handoff_queue_path_mismatch", f"{handoff_path} queue artifact path mismatch")
    _require_handoff(recommendation.get("learning_status") == learning.get("metrics_resolution_summary", {}).get("learning_status"), "handoff_learning_status_mismatch", f"{handoff_path} learning status mismatch")
    _require_handoff(int(recommendation.get("learning_published_post_count", -1)) == int(learning.get("published_post_count", -1)), "handoff_learning_published_count_mismatch", f"{handoff_path} learning published count mismatch")
    _require_handoff(int(recommendation.get("learning_pending_metrics_count", -1)) == len(learning.get("pending_metrics_posts", [])), "handoff_learning_pending_count_mismatch", f"{handoff_path} learning pending count mismatch")
    _require_handoff(int(recommendation.get("learning_stale_pending_metrics_count", -1)) == len(learning.get("stale_pending_metrics_posts", [])), "handoff_learning_stale_count_mismatch", f"{handoff_path} learning stale count mismatch")
    _require_handoff(recommendation.get("learning_resolution_state_summary", {}) == learning.get("metrics_resolution_summary", {}), "handoff_learning_summary_mismatch", f"{handoff_path} learning resolution summary mismatch")
    _require_handoff(report.get("source_recommendation", {}).get("recommended_recipe_id") == recommendation.get("recommendation", {}).get("recommended_recipe_id"), "handoff_recommendation_recipe_mismatch", f"{handoff_path} recommendation recipe mismatch")

    queue_head = queue_report.get("queue_slots", [])[0]
    _require_handoff(queue_head.get("recipe_id") == recommendation.get("recommendation", {}).get("recommended_recipe_id"), "handoff_queue_head_mismatch", f"{handoff_path} queue head mismatch")
    _require_handoff(
        selected_candidate_binding["selected_candidate_recipe_id"] == recommendation.get("recommendation", {}).get("recommended_recipe_id"),
        "selected_candidate_recommendation_mismatch",
        "selected candidate recipe does not match the next-generation recommendation",
    )
    _require_handoff(packet_report.get("recipe_id") == queue_head.get("recipe_id"), "handoff_candidate_recipe_mismatch", f"{handoff_path} selected prompt input recipe mismatch")
    _require_handoff(packet_report.get("packet_id") == report.get("selected_prompt_input", {}).get("packet_id"), "handoff_candidate_id_mismatch", f"{handoff_path} selected prompt input packet id mismatch")
    _require_handoff(packet_report.get("strong_hook_id") == report.get("selected_prompt_input", {}).get("hook_id"), "handoff_hook_id_mismatch", f"{handoff_path} selected prompt input hook id mismatch")
    _require_handoff(packet_report.get("hook_text") == report.get("selected_prompt_input", {}).get("hook_text"), "handoff_hook_text_mismatch", f"{handoff_path} selected prompt input hook text mismatch")
    _require_handoff(packet_report.get("caption_draft") == report.get("selected_prompt_input", {}).get("caption_seed"), "handoff_caption_seed_mismatch", f"{handoff_path} selected prompt input caption seed mismatch")
    _require_handoff(report.get("selected_prompt_input", {}).get("exact_proposed_dry_run_command") == expected_dry, "handoff_candidate_command_mismatch", f"{handoff_path} selected prompt input dry-run command mismatch")

    rebuilt_packet, source = _rebuild_packet_prompt_source(packet_path)
    image = source.get("image", {})
    prompt = image.get("image_prompt")
    _require_handoff(isinstance(prompt, str) and bool(prompt), "handoff_prompt_missing", f"{handoff_path} executor could not regenerate prompt bytes")
    regenerated_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    expected_sha = str(report.get("selected_prompt_input", {}).get("prompt_sha256", ""))
    _require_handoff(expected_sha and regenerated_sha == expected_sha, "handoff_prompt_sha_mismatch", f"{handoff_path} regenerated prompt SHA does not match packet expectation")
    _require_handoff(str(packet_report.get("compact_provider_prompt_sha256", "")).strip() == regenerated_sha, "handoff_prompt_candidate_sha_mismatch", f"{handoff_path} prompt input sha mismatch")
    _require_handoff(image.get("slot_id") == slot_id, "handoff_slot_mismatch", f"{handoff_path} regenerated slot mismatch")
    _require_handoff(image.get("lane") == report.get("selected_prompt_input", {}).get("lane"), "handoff_lane_mismatch", f"{handoff_path} regenerated lane mismatch")
    _require_handoff(image.get("soul_name") == CONFIRMED_LENA_SOUL_NAME, "handoff_soul_name_mismatch", f"{handoff_path} regenerated soul name mismatch")
    _require_handoff(image.get("soul_version") == CONFIRMED_LENA_SOUL_TYPE, "handoff_soul_version_mismatch", f"{handoff_path} regenerated soul version mismatch")
    _require_handoff(image.get("soul_selection_mode") == "provider_config_not_prompt_text", "handoff_soul_selection_mode_mismatch", f"{handoff_path} regenerated soul selection mode mismatch")
    _require_handoff(image.get("negative_prompt_enabled") is False, "handoff_negative_prompt_enabled", f"{handoff_path} regenerated prompt must keep negative_prompt disabled")
    _require_handoff(report.get("selected_prompt_input", {}).get("artifact_sha256") == _sha256_file(packet_path), "handoff_candidate_artifact_sha_mismatch", f"{handoff_path} selected prompt input artifact sha mismatch")
    _require_handoff(packet_report.get("compact_provider_prompt_preview") == prompt, "handoff_prompt_text_mismatch", f"{handoff_path} selected prompt input text mismatch")
    _require_handoff(rebuilt_packet.get("compact_provider_prompt_preview") == prompt, "handoff_rebuilt_prompt_text_mismatch", f"{handoff_path} rebuilt prompt text mismatch")
    validation = validate_candidate(source, None)
    _require_handoff(validation["ok"], "handoff_prompt_validation_failed", f"{handoff_path} regenerated prompt does not satisfy the existing dry-run validation gates")
    _require_handoff(report.get("selected_prompt_input_artifact_path") == report.get("selected_prompt_input", {}).get("artifact_path"), "handoff_candidate_path_mismatch", f"{handoff_path} selected prompt input path mismatch")
    _require_handoff(report.get("selected_prompt_input_artifact_path") == _repo_relative_path(packet_path), "handoff_candidate_path_mismatch", f"{handoff_path} selected prompt input path mismatch")
    _require_handoff(report.get("expected_handoff_artifact_path") == _repo_relative_path(handoff_path), "handoff_artifact_path_mismatch", f"{handoff_path} packet path mismatch")
    _require_handoff(report.get("expected_handoff_markdown_path") == _repo_relative_path(_handoff_markdown_path(date_str)), "handoff_markdown_path_mismatch", f"{handoff_path} markdown path mismatch")
    _require_handoff(structured.get("date") == date_str, "handoff_date_mismatch", f"{handoff_path} structured date mismatch")
    _require_handoff(structured.get("handoff_artifact_path") == _repo_relative_path(handoff_path), "handoff_artifact_path_mismatch", f"{handoff_path} structured packet path mismatch")
    _require_handoff(structured.get("handoff_markdown_path") == _repo_relative_path(_handoff_markdown_path(date_str)), "handoff_markdown_path_mismatch", f"{handoff_path} structured markdown path mismatch")
    _require_handoff(structured.get("expected_image_path") == _repo_relative_path(
        ROOT
        / "pipeline"
        / "higgsfield_library"
        / "lena"
        / date_str
        / f"{slot_id}_seed.png"
    ), "handoff_expected_image_path_mismatch", f"{handoff_path} expected image path mismatch")
    _require_handoff(structured.get("expected_manifest_path") == _repo_relative_path(
        ROOT
        / "pipeline"
        / "higgsfield_debug"
        / date_str
        / slot_id
        / "result_manifest.json"
    ), "handoff_expected_manifest_path_mismatch", f"{handoff_path} expected manifest path mismatch")

    packet_validation = {
        "handoff_artifact_path": _repo_relative_path(handoff_path),
        "handoff_validation_passed": True,
        "date": date_str,
        "slot_id": slot_id,
        "selected_prompt_sha256": expected_sha,
        "regenerated_prompt_sha256": regenerated_sha,
        "prompt_sha_match": True,
        "selected_candidate_binding_valid": True,
        "provider_model_aspect_soul_agreement": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "live_execution_authorized": False,
        "hand_off_state": report.get("live_execution_state"),
    }
    return report, source, packet_validation, validation


def print_handoff_dry_run_report(
    handoff_path: Path,
    report: dict,
    source: dict,
    custom_reference_id: str,
    packet_validation: dict,
    validation: dict,
) -> None:
    image = source["image"]
    prompt = image["image_prompt"]
    argv = build_provider_argv(prompt, custom_reference_id)

    print("=== Higgsfield Lena executor -- HANDOFF DRY RUN (no provider/network call) ===\n")
    print(f"handoff artifact path  : {packet_validation['handoff_artifact_path']}")
    print(f"handoff validation     : {packet_validation['handoff_validation_passed']}")
    print(f"date                    : {report['date']}")
    print(f"slot_id                 : {report['selected_slot_id']}")
    print(f"expected prompt sha256  : {packet_validation['selected_prompt_sha256']}")
    print(f"regenerated prompt sha256: {packet_validation['regenerated_prompt_sha256']}")
    print(f"prompt sha match        : {packet_validation['prompt_sha_match']}")
    print(f"provider/model/aspect/soul agreement : {packet_validation['provider_model_aspect_soul_agreement']}")
    print(f"provider_call_performed : {packet_validation['provider_call_performed']}")
    print(f"generation_performed    : {packet_validation['generation_performed']}")
    print(f"live_execution_authorized: {packet_validation['live_execution_authorized']}")
    print()
    print_dry_run_report(report["date"], report["selected_slot_id"], source, custom_reference_id, validation)


# --- Generation-approval binding (validation only; no consumption) ---------
#
# Reuses tools/lena_higgsfield_generation_approval_v1.py (Nicolas-only,
# 30-minute-TTL, single-authorized-attempt approval artifacts, immutable and
# separate from the handoff packet) -- never reimplemented here. Imported
# lazily, matching this file's existing convention for tools.* imports (see
# _load_retry_decision_source above). This executor only ever VALIDATES and
# REPORTS an approval artifact's validity/binding; it never marks an
# approval consumed and never lets a valid approval unlock --live, since no
# atomic single-use consumption (claim/receipt) mechanism exists yet.

def _validate_approval_artifact(handoff_path: Path, approval_path: Path) -> dict[str, Any]:
    from tools.lena_higgsfield_generation_approval_v1 import (  # noqa: E402
        HiggsfieldGenerationApprovalError,
        validate_generation_approval_artifact,
    )

    try:
        result = validate_generation_approval_artifact(approval_path)
    except HiggsfieldGenerationApprovalError as exc:
        raise HandoffArtifactError(exc.code, exc.detail) from exc

    bound_handoff_path = result["handoff_facts"]["handoff_path"]
    if bound_handoff_path.resolve() != handoff_path.resolve():
        raise HandoffArtifactError(
            "approval_handoff_binding_mismatch",
            f"approval artifact {approval_path} is bound to a different handoff "
            f"artifact ({bound_handoff_path}) than the one supplied via "
            f"--handoff-artifact ({handoff_path})",
        )
    return result


def print_approval_validation_report(approval_path: Path, approval_result: dict[str, Any]) -> None:
    approval = approval_result["approval"]
    scope = approval_result["scope_summary"]
    print()
    print("=== Higgsfield generation approval -- validation (no consumption) ===")
    print(f"approval artifact path  : {approval_result['approval_repo_path']}")
    print(f"approval artifact sha256: {approval_result['approval_sha256']}")
    print(f"operator_id              : {approval.get('operator_id')}")
    print(f"approved_at_utc          : {approval_result['approved_at_utc']}")
    print(f"expires_at_utc           : {approval_result['expires_at_utc']}")
    print(f"is_expired               : {approval_result['is_expired']}")
    print(f"authorized_attempts      : {scope['authorized_attempts']}")
    print(f"upload_authorized        : {scope['upload_authorized']}")
    print(f"queue_promotion_authorized: {scope['queue_promotion_authorized']}")
    print(f"publish_authorized       : {scope['publish_authorized']}")
    print(f"analytics_mutation_authorized: {scope['analytics_mutation_authorized']}")
    print("approval-handoff binding : confirmed exact match to supplied --handoff-artifact")
    print("consumption_state        : validation_only (dry-run never consumes approval)")


def _sanitize_operational_error_text(value: Any) -> str:
    text = str(value)
    return re.sub(
        r"https?://[^\s'\"<>\[\]{}]+",
        lambda match: _sanitize_url(match.group(0)),
        text,
    )


def _create_generation_claim(approval_result: dict[str, Any]) -> dict[str, Any]:
    from tools.lena_higgsfield_generation_approval_v1 import (  # noqa: E402
        build_generation_claim_record,
        claim_output_path,
        write_generation_claim_atomic,
    )

    handoff_facts = approval_result["handoff_facts"]
    path = claim_output_path(handoff_facts["date"], handoff_facts["slot_id"])
    record = build_generation_claim_record(approval_result)
    write_generation_claim_atomic(path, record)
    return {
        "claim_path": path.resolve(),
        "claim_repo_path": _repo_relative_path(path),
        "claim_record": record,
    }


def _write_generation_execution_receipt(
    claim_path: Path,
    approval_result: dict[str, Any],
    *,
    outcome: str,
    failure_stage: str | None,
    error_text: str | None,
    subprocess_start_attempted: bool,
    provider_submission_may_have_occurred: bool,
    provider_job_id: str | None,
    provider_status: str | None,
    output_path: str | None,
    image_format_detected: str | None,
    actual_manifest_path: str | None,
) -> dict[str, Any]:
    from tools.lena_higgsfield_generation_approval_v1 import (  # noqa: E402
        build_generation_execution_receipt_record,
        receipt_output_path,
        write_generation_execution_receipt_atomic,
    )

    handoff_facts = approval_result["handoff_facts"]
    path = receipt_output_path(handoff_facts["date"], handoff_facts["slot_id"])
    record = build_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome=outcome,
        failure_stage=failure_stage,
        error_text=error_text,
        subprocess_start_attempted=subprocess_start_attempted,
        provider_submission_may_have_occurred=provider_submission_may_have_occurred,
        provider_job_id=provider_job_id,
        provider_status=provider_status,
        output_path=output_path,
        image_format_detected=image_format_detected,
        actual_manifest_path=actual_manifest_path,
    )
    write_generation_execution_receipt_atomic(path, record)
    return {
        "receipt_path": path.resolve(),
        "receipt_repo_path": _repo_relative_path(path),
        "receipt_record": record,
    }


def execute_approved_handoff_live_generation(
    context: dict[str, Any],
    *,
    custom_reference_id: str | None = None,
    live_executor: Callable[[str, str, dict, str], dict] | None = None,
) -> dict[str, Any]:
    """Execute one approved live generation using a validated context.

    The caller is responsible for validating the handoff and approval
    artifacts and for providing the resolved execution context. This helper
    keeps the claim/receipt/manifest lifecycle in one place so wrappers can
    stay thin without duplicating execution semantics.
    """
    approval_result = context["approval_result"]
    handoff_facts = approval_result["handoff_facts"]
    date_str = str(context["date"])
    slot_id = str(context["slot_id"])
    source = context["source"]
    resolved_custom_reference_id = custom_reference_id or str(context["custom_reference_id"])
    manifest_repo_path = context["manifest_path"]

    claim_info = _create_generation_claim(approval_result)
    claim_path = Path(claim_info["claim_path"])

    result: dict[str, Any] = {
        "ok": False,
        "date": date_str,
        "slot_id": slot_id,
        "recipe_id": str(context["recipe_id"]),
        "selected_slot_id": slot_id,
        "selected_recipe_id": str(context.get("recipe_id") or ""),
        "claim_info": claim_info,
        "claim_path": claim_path.resolve(),
        "claim_repo_path": claim_info["claim_repo_path"],
        "manifest_path": Path(manifest_repo_path).resolve(),
        "manifest_repo_path": _repo_relative_path(Path(manifest_repo_path)),
        "receipt_info": None,
        "receipt_path": None,
        "receipt_repo_path": None,
        "live_result": None,
        "provider_submission_may_have_occurred": False,
        "subprocess_start_attempted": False,
        "provider_call_performed": False,
        "generation_performed": False,
        "manifest_written": False,
        "claim_written": True,
        "receipt_written": False,
        "failure_stage": None,
        "failure_error_text": None,
        "failure_provider_job_id": None,
        "failure_provider_status": None,
        "failure_output_path": None,
        "failure_image_format_detected": None,
        "publish_authorized": False,
        "publish_performed": False,
        "queue_mutated": False,
        "qa_run": False,
        "retry_executed": False,
        "dirty_workspace_dependency": False,
    }

    live_executor = live_executor or run_live

    try:
        live_result = live_executor(date_str, slot_id, source, resolved_custom_reference_id)
    except Exception as exc:
        failure_stage = getattr(exc, "stage", "provider_failure")
        subprocess_start_attempted = bool(getattr(exc, "subprocess_start_attempted", False))
        provider_submission_may_have_occurred = bool(getattr(exc, "provider_submission_may_have_occurred", False))
        provider_job_id = getattr(exc, "provider_job_id", None)
        provider_status = getattr(exc, "provider_status", None)
        output_path = getattr(exc, "output_path", None)
        image_format_detected = getattr(exc, "image_format_detected", None)
        result.update(
            {
                "provider_submission_may_have_occurred": provider_submission_may_have_occurred,
                "subprocess_start_attempted": subprocess_start_attempted,
                "provider_call_performed": provider_submission_may_have_occurred,
                "failure_stage": failure_stage,
                "failure_error_text": _sanitize_operational_error_text(exc),
                "failure_provider_job_id": provider_job_id,
                "failure_provider_status": provider_status,
                "failure_output_path": output_path,
                "failure_image_format_detected": image_format_detected,
            }
        )
        try:
            receipt_info = _write_generation_execution_receipt(
                claim_path,
                approval_result,
                outcome="execution_failed",
                failure_stage=failure_stage,
                error_text=result["failure_error_text"],
                subprocess_start_attempted=subprocess_start_attempted,
                provider_submission_may_have_occurred=provider_submission_may_have_occurred,
                provider_job_id=provider_job_id,
                provider_status=provider_status,
                output_path=output_path,
                image_format_detected=image_format_detected,
                actual_manifest_path=None,
            )
        except Exception as receipt_exc:
            result["receipt_info"] = None
            result["receipt_written"] = False
            result["failure_error_text"] = (
                f"{result['failure_error_text']} (receipt write failed: {_sanitize_operational_error_text(receipt_exc)})"
            )
            return result

        result.update(
            {
                "receipt_info": receipt_info,
                "receipt_path": receipt_info["receipt_path"],
                "receipt_repo_path": receipt_info["receipt_repo_path"],
                "receipt_written": True,
            }
        )
        return result

    result["live_result"] = live_result
    result["provider_submission_may_have_occurred"] = bool(live_result.get("provider_submission_may_have_occurred"))
    result["subprocess_start_attempted"] = bool(live_result.get("subprocess_start_attempted"))
    result["provider_call_performed"] = bool(live_result.get("provider_submission_may_have_occurred"))
    result["generation_performed"] = bool(live_result.get("saved_image_path"))

    receipt_info = _write_generation_execution_receipt(
        claim_path,
        approval_result,
        outcome="success",
        failure_stage=None,
        error_text=None,
        subprocess_start_attempted=result["subprocess_start_attempted"],
        provider_submission_may_have_occurred=result["provider_submission_may_have_occurred"],
        provider_job_id=live_result.get("job_id"),
        provider_status=live_result.get("status"),
        output_path=live_result.get("saved_image_path"),
        image_format_detected=live_result.get("image_format_detected"),
        actual_manifest_path=_repo_relative_path(Path(manifest_repo_path)),
    )
    manifest = build_manifest(
        date_str,
        slot_id,
        source,
        resolved_custom_reference_id,
        live_result,
        claim_repo_path=claim_info["claim_repo_path"],
        receipt_repo_path=receipt_info["receipt_repo_path"],
    )
    manifest_path_obj = Path(manifest_repo_path)
    manifest_path_obj.parent.mkdir(parents=True, exist_ok=True)
    manifest_path_obj.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    result.update(
        {
            "ok": True,
            "receipt_info": receipt_info,
            "receipt_path": receipt_info["receipt_path"],
            "receipt_repo_path": receipt_info["receipt_repo_path"],
            "receipt_written": True,
            "manifest_record": manifest,
            "manifest_written": True,
        }
    )
    return result


def _validate_retry_approval_artifact(retry_handoff_path: Path, approval_path: Path) -> dict[str, Any]:
    from tools.lena_higgsfield_retry_generation_approval_v1 import (  # noqa: E402
        HiggsfieldRetryGenerationApprovalError,
        validate_retry_generation_approval_artifact,
    )

    try:
        result = validate_retry_generation_approval_artifact(approval_path)
    except HiggsfieldRetryGenerationApprovalError as exc:
        raise HandoffArtifactError(exc.code, exc.detail) from exc

    bound_retry_path = result["retry_facts"]["retry_handoff_path"]
    if bound_retry_path.resolve() != retry_handoff_path.resolve():
        raise HandoffArtifactError(
            "approval_retry_handoff_binding_mismatch",
            f"retry approval artifact {approval_path} is bound to a different retry "
            f"handoff artifact ({bound_retry_path}) than the one supplied via "
            f"--retry-decision-artifact ({retry_handoff_path})",
        )
    return result


def print_retry_approval_validation_report(approval_path: Path, approval_result: dict[str, Any]) -> None:
    approval = approval_result["approval"]
    scope = approval_result["scope_summary"]
    print()
    print("=== Higgsfield retry generation approval -- validation (no consumption) ===")
    print(f"approval artifact path  : {approval_result['approval_repo_path']}")
    print(f"approval artifact sha256: {approval_result['approval_sha256']}")
    print(f"operator_id              : {approval.get('operator_id')}")
    print(f"approved_at_utc          : {approval_result['approved_at_utc']}")
    print(f"expires_at_utc           : {approval_result['expires_at_utc']}")
    print(f"is_expired               : {approval_result['is_expired']}")
    print(f"authorized_attempts      : {scope['authorized_attempts']}")
    print(f"upload_authorized        : {scope['upload_authorized']}")
    print(f"queue_promotion_authorized: {scope['queue_promotion_authorized']}")
    print(f"publish_authorized       : {scope['publish_authorized']}")
    print(f"scheduling_authorized    : {scope['scheduling_authorized']}")
    print(f"analytics_mutation_authorized: {scope['analytics_mutation_authorized']}")
    print("approval-retry binding   : confirmed exact match to supplied --retry-decision-artifact")
    print("consumption_state        : validation_only (dry-run never consumes approval)")


def _create_retry_generation_claim(approval_result: dict[str, Any]) -> dict[str, Any]:
    from tools.lena_higgsfield_retry_generation_approval_v1 import (  # noqa: E402
        HiggsfieldRetryGenerationApprovalError,
        build_retry_generation_claim_record,
        claim_output_path,
        receipt_output_path,
        write_retry_generation_claim_atomic,
    )

    retry_facts = approval_result["retry_facts"]
    claim_path = claim_output_path(retry_facts["date"], retry_facts["slot_id"])
    receipt_path = receipt_output_path(retry_facts["date"], retry_facts["slot_id"])
    if receipt_path.exists():
        raise HiggsfieldRetryGenerationApprovalError(
            "retry_generation_already_consumed",
            f"retry approval is already consumed because an execution receipt already exists: {receipt_path}",
        )
    record = build_retry_generation_claim_record(approval_result)
    write_retry_generation_claim_atomic(claim_path, record)
    return {
        "claim_path": claim_path.resolve(),
        "claim_repo_path": _repo_relative_path(claim_path),
        "claim_record": record,
    }


def _write_retry_generation_execution_receipt(
    claim_path: Path,
    approval_result: dict[str, Any],
    *,
    outcome: str,
    failure_stage: str | None,
    error_text: str | None,
    subprocess_start_attempted: bool,
    provider_submission_may_have_occurred: bool,
    provider_job_id: str | None,
    provider_status: str | None,
    output_path: str | None,
    image_format_detected: str | None,
    actual_manifest_path: str | None,
) -> dict[str, Any]:
    from tools.lena_higgsfield_retry_generation_approval_v1 import (  # noqa: E402
        build_retry_generation_execution_receipt_record,
        receipt_output_path,
        write_retry_generation_execution_receipt_atomic,
    )

    retry_facts = approval_result["retry_facts"]
    path = receipt_output_path(retry_facts["date"], retry_facts["slot_id"])
    record = build_retry_generation_execution_receipt_record(
        claim_path,
        approval_result,
        outcome=outcome,
        failure_stage=failure_stage,
        error_text=error_text,
        subprocess_start_attempted=subprocess_start_attempted,
        provider_submission_may_have_occurred=provider_submission_may_have_occurred,
        provider_job_id=provider_job_id,
        provider_status=provider_status,
        output_path=output_path,
        image_format_detected=image_format_detected,
        actual_manifest_path=actual_manifest_path,
    )
    write_retry_generation_execution_receipt_atomic(path, record)
    return {
        "receipt_path": path.resolve(),
        "receipt_repo_path": _repo_relative_path(path),
        "receipt_record": record,
    }


# --- Handoff packet helpers -------------------------------------------------

def _require_handoff(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HandoffArtifactError(code, detail)


def _repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_repo_path(path_value: str) -> Path:
    raw = str(path_value or "").strip()
    _require_handoff(bool(raw), "handoff_path_missing", "required repository path is missing")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _handoff_json_path(date_str: str) -> Path:
    return ROOT / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_next_live_image_handoff_{date_str}.json"


def _handoff_markdown_path(date_str: str) -> Path:
    return ROOT / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_next_live_image_handoff_{date_str}.md"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_report(
    path: Path,
    *,
    expected_report_type: str,
    expected_date: str,
    require_date: bool = True,
) -> dict[str, Any]:
    _require_handoff(path.is_file(), "handoff_missing_artifact", f"missing required artifact: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive fail closed
        raise HandoffArtifactError("handoff_unreadable_artifact", f"{path}: {exc}") from exc
    _require_handoff(isinstance(report, dict), "handoff_malformed_artifact", f"{path} must contain a JSON object")
    _require_handoff(
        report.get("report_type") == expected_report_type,
        "handoff_wrong_report_type",
        f"{path} has report_type {report.get('report_type')!r}, expected {expected_report_type!r}",
    )
    report_date = str(report.get("date", "")).strip()
    if require_date or report_date:
        _require_handoff(
            report_date == expected_date,
            "handoff_date_mismatch",
            f"{path} has date {report_date!r}, expected {expected_date!r}",
        )
    return report


def load_learning_report(recommendation: dict[str, Any], expected_date: str) -> tuple[Path, dict[str, Any]]:
    learning_path = _resolve_repo_path(str(recommendation.get("learning_artifact_path", "")))
    _require_handoff(
        learning_path.is_file(),
        "handoff_missing_learning_artifact",
        f"recommendation references a missing learning artifact: {learning_path}",
    )
    learning = load_report(
        learning_path,
        expected_report_type="lena_post_outcome_learning_state",
        expected_date=expected_date,
    )
    return learning_path, learning


def load_queue_report(expected_date: str) -> tuple[Path, dict[str, Any]]:
    path = ROOT / "pipeline" / "strategy" / "lena" / "next_actions" / expected_date / f"lena_autonomous_generation_queue_dryrun_{expected_date}.json"
    queue_report = load_report(
        path,
        expected_report_type="lena_autonomous_generation_queue_dryrun",
        expected_date=expected_date,
        require_date=False,
    )
    queue_slots = queue_report.get("queue_slots", [])
    _require_handoff(
        isinstance(queue_slots, list) and bool(queue_slots),
        "handoff_empty_queue_report",
        f"{path} has no queue_slots",
    )
    head = queue_slots[0]
    _require_handoff(
        isinstance(head, dict),
        "handoff_queue_head_invalid",
        f"{path} queue head is not a JSON object",
    )
    return path.resolve(), queue_report


def load_content_packet_report(path: Path, expected_date: str) -> dict[str, Any]:
    _require_handoff(path.is_file(), "handoff_missing_artifact", f"missing required artifact: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive fail closed
        raise HandoffArtifactError("handoff_unreadable_artifact", f"{path}: {exc}") from exc
    _require_handoff(isinstance(report, dict), "handoff_malformed_artifact", f"{path} must contain a JSON object")
    _require_handoff(
        report.get("report_type") == "lena_content_packet_dryrun",
        "handoff_wrong_report_type",
        f"{path} has report_type {report.get('report_type')!r}, expected 'lena_content_packet_dryrun'",
    )
    _require_handoff(
        str(report.get("generated_date", "")).strip() == expected_date,
        "handoff_date_mismatch",
        f"{path} has generated_date {report.get('generated_date')!r}, expected {expected_date!r}",
    )
    _require_handoff(
        isinstance(report.get("compact_provider_prompt_preview"), str)
        and bool(str(report.get("compact_provider_prompt_preview", "")).strip()),
        "handoff_packet_prompt_missing",
        f"{path} must contain a compact_provider_prompt_preview",
    )
    return report


def _rebuild_packet_prompt_source(packet_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder  # noqa: E402

    packet_report = load_content_packet_report(packet_path, str(json.loads(packet_path.read_text(encoding="utf-8")).get("generated_date", "")).strip())
    rebuilt_packet = packet_builder.rebuild_packet_from_authoritative_sources(packet_report)
    prompt = str(rebuilt_packet.get("compact_provider_prompt_preview", "")).strip()
    _require_handoff(
        bool(prompt),
        "handoff_prompt_missing",
        f"{packet_path} rebuilt packet did not produce a prompt",
    )
    slot_id = f"higgsfield-{packet_report['generated_date'].replace('-', '')}-{packet_report['recipe_id']}-photo"
    source = {
        "resolver": "content_packet_dryrun",
        "slot_prefix": packet_report["recipe_id"],
        "pack_count": 1,
        "pack_variety_warnings": [],
        "image": {
            "slot_id": slot_id,
            "lane": packet_report.get("scene_type", ""),
            "wardrobe_outfit_id": packet_report.get("wardrobe_outfit_id"),
            "environment_id": packet_report.get("environment_id"),
            "pose_body_language_id": None,
            "pose_body_language_label": packet_report.get("high_caliber_source_sections", {}).get("subject_pose", ""),
            "effective_wardrobe_silhouette_class": packet_report.get("content_pillar", ""),
            "soul_name": CONFIRMED_LENA_SOUL_NAME,
            "soul_version": CONFIRMED_LENA_SOUL_TYPE,
            "soul_selection_mode": "provider_config_not_prompt_text",
            "camera_text": packet_report.get("high_caliber_source_sections", {}).get("technical_keywords", ""),
            "lighting_text": packet_report.get("high_caliber_source_sections", {}).get("style_lighting", ""),
            "negative_prompt_enabled": False,
            "image_prompt": prompt,
            "validation": {
                "framing_present": True,
                "wardrobe_casual_free": True,
                "wardrobe_casual_terms_found": [],
                "scene_action_conflict_free": True,
                "scene_action_conflict_terms_found": [],
                "soul_anchor_absent": True,
                "negative_prompt_disabled": True,
                "heavy_overcorrection_free": True,
                "heavy_overcorrection_terms_found": [],
                "pose_scene_match_pass": True,
                "pose_scene_mismatch_terms_found": [],
                "low_hook_terms_found": [],
                "final_expression_text": "",
                "expression_safe_fallback_used": False,
                "expression_safe_fallback_reason": "",
                "expression_scene_gaze_conflict_terms_found": [],
            },
        },
    }
    return packet_report, source


def _load_handoff_report(handoff_path: Path) -> dict[str, Any]:
    _require_handoff(handoff_path.is_file(), "handoff_missing_artifact", f"missing required handoff artifact: {handoff_path}")
    try:
        report = json.loads(handoff_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive fail closed
        raise HandoffArtifactError("handoff_unreadable_artifact", f"{handoff_path}: {exc}") from exc
    _require_handoff(isinstance(report, dict), "handoff_malformed_artifact", f"{handoff_path} must contain a JSON object")
    _require_handoff(report.get("report_type") == HANDOFF_REPORT_TYPE, "handoff_wrong_report_type", f"{handoff_path} has report_type {report.get('report_type')!r}, expected {HANDOFF_REPORT_TYPE!r}")
    _require_handoff(report.get("schema_version") == HANDOFF_SCHEMA_VERSION, "handoff_wrong_schema_version", f"{handoff_path} has schema_version {report.get('schema_version')!r}, expected {HANDOFF_SCHEMA_VERSION!r}")
    _require_handoff(report.get("execution_owner") == HANDOFF_EXECUTION_OWNER, "handoff_execution_owner_mismatch", f"{handoff_path} execution_owner must be {HANDOFF_EXECUTION_OWNER!r}")
    _require_handoff(report.get("provider") == HIGGSFIELD_CLI_BINARY, "handoff_provider_mismatch", f"{handoff_path} provider must be {HIGGSFIELD_CLI_BINARY!r}")
    _require_handoff(report.get("executor_type") == HANDOFF_EXECUTOR_TYPE, "handoff_executor_type_mismatch", f"{handoff_path} executor_type must be {HANDOFF_EXECUTOR_TYPE!r}")
    _require_handoff(report.get("date"), "handoff_date_missing", f"{handoff_path} must include a date")
    _require_handoff(report.get("selected_slot_id"), "handoff_slot_missing", f"{handoff_path} must include a selected_slot_id")
    return report


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
    *,
    claim_repo_path: str | None = None,
    receipt_repo_path: str | None = None,
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
        if claim_repo_path:
            manifest["generation_claim_artifact_path"] = claim_repo_path
        if receipt_repo_path:
            manifest["generation_execution_receipt_path"] = receipt_repo_path

    retry_contract = image.get("retry_execution_contract")
    if isinstance(retry_contract, dict):
        manifest["retry_execution_contract"] = retry_contract

    return manifest


def _load_retry_decision_source(retry_decision_artifact: Path) -> tuple[str, str, dict, Path]:
    payload = json.loads(retry_decision_artifact.read_text(encoding="utf-8-sig"))
    schema_version = payload.get("schema_version")

    if schema_version == "lena_higgsfield_retry_handoff_v1":
        from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff  # noqa: E402

        artifact = retry_handoff.load_retry_execution_source(retry_decision_artifact)
        handoff_path = _resolve_repo_path(str(artifact["source_handoff_artifact_path"]))
        _, source, _, _ = _validate_handoff_packet(handoff_path)
        retry_source = copy.deepcopy(source)
        retry_source["resolver"] = "retry_handoff"
        retry_source["slot_prefix"] = str(artifact["original_slot_id"])
        retry_source["pack_count"] = 1
        retry_source["image"]["slot_id"] = artifact["retry_slot_id"]
        retry_source["image"]["image_prompt"] = artifact["retry_prompt_text"]
        retry_source["image"]["prompt_sha256"] = artifact["retry_prompt_sha256"]
        retry_source["image"]["retry_execution_contract"] = {
            "schema_version": schema_version,
            "retry_handoff_fingerprint_sha256": artifact["retry_handoff_fingerprint_sha256"],
            "retry_attempt": artifact["retry_attempt"],
            "retry_cap": artifact["retry_cap"],
            "retry_purpose": artifact["retry_purpose"],
            "original_slot_id": artifact["original_slot_id"],
            "retry_slot_id": artifact["retry_slot_id"],
            "source_handoff_artifact_path": artifact["source_handoff_artifact_path"],
            "source_handoff_artifact_sha256": artifact["source_handoff_artifact_sha256"],
            "source_selected_prompt_input_artifact_path": artifact["source_selected_prompt_input_artifact_path"],
            "source_selected_prompt_input_artifact_sha256": artifact["source_selected_prompt_input_artifact_sha256"],
            "source_execution_receipt_path": artifact["source_execution_receipt_path"],
            "source_execution_receipt_sha256": artifact["source_execution_receipt_sha256"],
            "source_manifest_path": artifact["source_manifest_path"],
            "source_manifest_sha256": artifact["source_manifest_sha256"],
            "source_output_image_path": artifact["source_output_image_path"],
            "source_output_image_sha256": artifact["source_output_image_sha256"],
            "source_original_prompt_sha256": artifact["source_original_prompt_sha256"],
            "retry_constraints": artifact["retry_constraints"],
        }
        return str(artifact["date"]), str(artifact["retry_slot_id"]), retry_source, retry_decision_artifact.resolve()

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
            "the Higgsfield CLI does not appear to be on PATH.",
            stage="subprocess_start_failure",
            subprocess_start_attempted=False,
            provider_submission_may_have_occurred=False,
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
            ,
            stage="subprocess_start_failure",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=False,
        ) from exc

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-2000:]
        raise ProviderCallError(
            f"higgsfield generate create exited {result.returncode}. "
            f"stderr (tail): {stderr_tail}"
            ,
            stage="provider_rejection",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
        )

    stdout = result.stdout or ""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProviderCallError(
            f"Failed to parse --json output as JSON: {exc}. "
            f"stdout length was {len(stdout)} chars."
            ,
            stage="provider_output_parse_failure",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
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
            ,
            stage="provider_output_invalid",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id=job_id,
            provider_status=status,
        )
    if len(result_urls) > 1:
        raise ProviderCallError(
            f"Provider response contained {len(result_urls)} distinct "
            "top-level result_url values where exactly one job (and "
            "therefore exactly one result_url) was expected. This executor "
            "refuses to silently pick one. Manual review required."
            ,
            stage="provider_output_invalid",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id=job_id,
            provider_status=status,
        )

    result_url = result_urls[0]
    try:
        image_bytes = _download(result_url, ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str / f"{slot_id}_seed.tmp")
    except Exception as exc:
        raise ProviderCallError(
            f"Download of result image failed: {exc}",
            stage="download_failure",
            subprocess_start_attempted=True,
            provider_submission_may_have_occurred=True,
            provider_job_id=job_id,
            provider_status=status,
        ) from exc

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
        "subprocess_start_attempted": True,
        "provider_submission_may_have_occurred": True,
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
    parser.add_argument("--handoff-artifact", type=Path)
    parser.add_argument(
        "--approval-artifact", type=Path, dest="approval_artifact", default=None,
        help="Optional, only valid together with --handoff-artifact. A recorded "
             "generation-approval artifact (tools/lena_record_higgsfield_generation_"
             "approval_v1.py) to validate and, under --live, consume through an "
             "atomic single-use claim/receipt contract.",
    )
    parser.add_argument(
        "--retry-approval-artifact", type=Path, dest="retry_approval_artifact", default=None,
        help="Optional, only valid together with --retry-decision-artifact when the "
             "artifact is a lena_higgsfield_retry_handoff_v1 retry handoff. A "
             "recorded retry-generation approval artifact "
             "(tools/lena_record_higgsfield_retry_generation_approval_v1.py) to "
             "validate and, under --live, consume through an atomic single-use "
             "retry claim/receipt contract.",
    )
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

    if args.approval_artifact is not None and args.handoff_artifact is None:
        print("[ABORT] --approval-artifact requires --handoff-artifact.")
        return 1
    if args.retry_approval_artifact is not None and args.retry_decision_artifact is None:
        print("[ABORT] --retry-approval-artifact requires --retry-decision-artifact.")
        return 1
    if args.approval_artifact is not None and args.retry_approval_artifact is not None:
        print("[ABORT] --approval-artifact and --retry-approval-artifact are mutually exclusive.")
        return 1

    try:
        if args.live or args.approval_artifact is not None or args.retry_approval_artifact is not None:
            autonomy_ladder.assert_allowed(
                "pipeline_higgsfield_lena_api_executor",
                level=2,
                action="explicit per-slot human approval consumption",
            )
        else:
            autonomy_ladder.assert_allowed(
                "pipeline_higgsfield_lena_api_executor",
                level=0,
                action="dry-run strategy prep",
            )
    except autonomy_ladder.AutonomyLadderError as exc:
        print(f"[ABORT] {exc.code}: {exc.detail}")
        return 1

    if args.handoff_artifact is not None:
        if args.retry_decision_artifact is not None or args.date or args.slot_id:
            print("[ABORT] --handoff-artifact is mutually exclusive with --retry-decision-artifact and --date/--slot-id.")
            return 1
        if expected_prompt_path is not None:
            print("[ABORT] --expected-prompt-file is not supported with --handoff-artifact.")
            return 1
        try:
            report, source, packet_validation, validation = _validate_handoff_packet(args.handoff_artifact)
        except HandoffArtifactError as exc:
            print(f"[ABORT] {exc.code}: {exc.detail}")
            return 1

        print_handoff_dry_run_report(args.handoff_artifact, report, source, args.custom_reference_id, packet_validation, validation)

        approval_result = None
        approval_error: Optional[HandoffArtifactError] = None
        if args.approval_artifact is not None:
            try:
                approval_result = _validate_approval_artifact(args.handoff_artifact, args.approval_artifact)
                print_approval_validation_report(args.approval_artifact, approval_result)
            except HandoffArtifactError as exc:
                approval_error = exc
                print(f"[ABORT] approval validation failed: {exc.code}: {exc.detail}")

        if not live:
            if approval_error is not None:
                return 1
            return 0 if validation["ok"] else 1

        if approval_error is not None:
            return 1
        if args.approval_artifact is None:
            print(
                "[ABORT] --live with --handoff-artifact requires a valid "
                "--approval-artifact. The handoff remains review-only and is never "
                "rewritten into live authorization."
            )
            return 1
        from tools.lena_higgsfield_generation_approval_v1 import claim_output_path, receipt_output_path  # noqa: E402

        execution_context = {
            "date": report["date"],
            "slot_id": report["selected_slot_id"],
            "recipe_id": report["selected_recipe_id"],
            "handoff_report": report,
            "source": source,
            "packet_validation": packet_validation,
            "validation": validation,
            "approval_result": approval_result,
            "claim_path": claim_output_path(report["date"], report["selected_slot_id"]),
            "receipt_path": receipt_output_path(report["date"], report["selected_slot_id"]),
            "manifest_path": manifest_path(report["date"], report["selected_slot_id"]),
            "handoff_artifact": args.handoff_artifact,
            "approval_artifact": args.approval_artifact,
            "custom_reference_id": args.custom_reference_id,
        }
        try:
            execution_result = execute_approved_handoff_live_generation(
                execution_context,
                custom_reference_id=args.custom_reference_id,
                live_executor=run_live,
            )
        except Exception as exc:
            code = getattr(exc, "code", "generation_claim_creation_failed")
            print(f"[ABORT] claim creation failed: {code}: {exc}")
            return 1
        if not execution_result["ok"]:
            print(f"[FAILED] {execution_result['failure_error_text']}")
            if execution_result.get("receipt_written"):
                receipt_info = execution_result["receipt_info"] or {}
                receipt_repo_path = receipt_info.get("receipt_repo_path") or execution_result.get("receipt_repo_path")
                print(f"[FAILED] execution receipt written: {receipt_repo_path}")
            else:
                print("[FAILED] claim retained but execution receipt could not be written.")
            print("[FAILED] Claim retained; manual reconciliation or a new approval is required.")
            return 1

        live_result = execution_result["live_result"] or {}
        claim_info = execution_result["claim_info"] or {}
        receipt_info = execution_result["receipt_info"] or {}
        manifest_repo_path = execution_result["manifest_repo_path"]
        print(f"[LIVE] saved image     : {live_result['saved_image_path']}")
        print(f"[LIVE] claim written    : {claim_info['claim_repo_path']}")
        print(f"[LIVE] receipt written  : {receipt_info['receipt_repo_path']}")
        print(f"[LIVE] manifest written: {manifest_repo_path}")
        return 0

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
        retry_approval_error: Optional[HandoffArtifactError] = None
        if args.retry_decision_artifact is not None and args.retry_approval_artifact is not None:
            try:
                retry_approval_result = _validate_retry_approval_artifact(
                    args.retry_decision_artifact, args.retry_approval_artifact
                )
                print_retry_approval_validation_report(args.retry_approval_artifact, retry_approval_result)
            except HandoffArtifactError as exc:
                retry_approval_error = exc
                print(f"[ABORT] retry approval validation failed: {exc.code}: {exc.detail}")
        if retry_approval_error is not None:
            return 1
        return 0 if validation["ok"] else 1

    if args.retry_decision_artifact is not None:
        print_dry_run_report(date_str, slot_id, source, args.custom_reference_id, validation)
        retry_approval_result = None
        retry_approval_error: Optional[HandoffArtifactError] = None
        if args.retry_approval_artifact is not None:
            try:
                retry_approval_result = _validate_retry_approval_artifact(
                    args.retry_decision_artifact, args.retry_approval_artifact
                )
                print_retry_approval_validation_report(args.retry_approval_artifact, retry_approval_result)
            except HandoffArtifactError as exc:
                retry_approval_error = exc
                print(f"[ABORT] retry approval validation failed: {exc.code}: {exc.detail}")
        if retry_approval_error is not None:
            return 1
        if args.retry_approval_artifact is None:
            print(
                "[ABORT] --live with --retry-decision-artifact requires a valid "
                "--retry-approval-artifact. The retry handoff remains review-only "
                "and is never rewritten into live authorization."
            )
            return 1
        try:
            claim_info = _create_retry_generation_claim(retry_approval_result)
        except Exception as exc:
            code = getattr(exc, "code", "retry_generation_claim_creation_failed")
            print(f"[ABORT] retry claim creation failed: {code}: {exc}")
            return 1
        claim_path = Path(claim_info["claim_path"])
        manifest_repo_path = _repo_relative_path(manifest_path(date_str, slot_id))
        try:
            live_result = run_live(date_str, slot_id, source, args.custom_reference_id)
        except ProviderCallError as exc:
            try:
                receipt_info = _write_retry_generation_execution_receipt(
                    claim_path,
                    retry_approval_result,
                    outcome="execution_failed",
                    failure_stage=exc.stage,
                    error_text=_sanitize_operational_error_text(exc),
                    subprocess_start_attempted=exc.subprocess_start_attempted,
                    provider_submission_may_have_occurred=exc.provider_submission_may_have_occurred,
                    provider_job_id=exc.provider_job_id,
                    provider_status=exc.provider_status,
                    output_path=exc.output_path,
                    image_format_detected=exc.image_format_detected,
                    actual_manifest_path=None,
                )
            except Exception as receipt_exc:
                print(f"[FAILED] {exc}")
                print(
                    "[FAILED] retry claim retained but execution receipt could not be "
                    f"written: {getattr(receipt_exc, 'code', 'retry_generation_execution_receipt_write_failed')}: {receipt_exc}"
                )
                print("[FAILED] Manual reconciliation required before any new retry approval is used.")
                return 1
            print(f"[FAILED] {exc}")
            print(f"[FAILED] retry execution receipt written: {receipt_info['receipt_repo_path']}")
            print("[FAILED] Retry claim retained; manual reconciliation or a new retry approval is required.")
            return 1
        try:
            receipt_info = _write_retry_generation_execution_receipt(
                claim_path,
                retry_approval_result,
                outcome="success",
                failure_stage=None,
                error_text=None,
                subprocess_start_attempted=bool(live_result.get("subprocess_start_attempted")),
                provider_submission_may_have_occurred=bool(live_result.get("provider_submission_may_have_occurred")),
                provider_job_id=live_result.get("job_id"),
                provider_status=live_result.get("status"),
                output_path=live_result.get("saved_image_path"),
                image_format_detected=live_result.get("image_format_detected"),
                actual_manifest_path=manifest_repo_path,
            )
        except Exception as receipt_exc:
            print(
                "[FAILED] live retry generation succeeded, but retry execution receipt creation "
                f"failed: {getattr(receipt_exc, 'code', 'retry_generation_execution_receipt_write_failed')}: {receipt_exc}"
            )
            print("[FAILED] Retry claim retained; manual reconciliation required before any new retry approval is used.")
            return 1
        manifest = build_manifest(
            date_str,
            slot_id,
            source,
            args.custom_reference_id,
            live_result,
            claim_repo_path=claim_info["claim_repo_path"],
            receipt_repo_path=receipt_info["receipt_repo_path"],
        )
        mpath = manifest_path(date_str, slot_id)
        try:
            mpath.parent.mkdir(parents=True, exist_ok=True)
            mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            print(
                "[FAILED] retry execution receipt written but manifest creation failed: "
                f"{_sanitize_operational_error_text(exc)}"
            )
            print("[FAILED] Retry claim and receipt were retained. No provider retry was attempted.")
            return 1
        print(f"[LIVE] saved image     : {live_result['saved_image_path']}")
        print(f"[LIVE] retry claim written   : {claim_info['claim_repo_path']}")
        print(f"[LIVE] retry receipt written : {receipt_info['receipt_repo_path']}")
        print(f"[LIVE] manifest written: {mpath}")
        return 0

    print_dry_run_report(date_str, slot_id, source, args.custom_reference_id, validation)
    print(
        "[ABORT] raw --date/--slot-id --live is forbidden. The only permitted live "
        "still-image command is: python pipeline/higgsfield_lena_api_executor.py "
        "--handoff-artifact <packet> --approval-artifact <approval> --live"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
