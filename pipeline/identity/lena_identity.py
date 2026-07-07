from __future__ import annotations

import os
from typing import Optional, Tuple, Dict

# Single source of truth for Lena photo identity resolution.
#
# Consolidates element-id cleaning, expected/forbidden element resolution, the
# manual-override fail-closed guard, and the allowed photo reference-mode
# contract that were previously duplicated across:
#   - pipeline/kling_apilena_api_executor.py
#   - tools/lena_preflight.py
#   - pipeline/lena_production_job.py
#
# See pipeline/change_notes/lena_agentic_pivot_changelog.md (2026-07-05, Batch 2).

# --- Allowed photo reference-mode contract ---------------------------------
# The only values a Lena photo queue item's metadata may carry for these
# fields. tools/lena_preflight.py enforces these against generated output;
# nothing else should redefine this list separately.
ALLOWED_PHOTO_IDENTITY_BINDINGS = {
    "validated_kling_api_lena_element",
    "validated_kling_ui_lena_element",
    "validated_kling_ui_lena_element_only",
}
REQUIRED_REFERENCE_BINDING_MODE = "kling_omni_element_only_photo"
REQUIRED_REFERENCE_SOURCE_POLICY = "kling_live_ui_element_only"
REQUIRED_SEED_SOURCE = "fresh_kling_omni_public_api_image_generation"

EXPECTED_PHOTO_ELEMENT_ENV_VAR = "KLING_LENA_ELEMENT_UI_ID"
EXPECTED_PHOTO_ELEMENT_NAME_ENV_VAR = "KLING_LENA_ELEMENT_NAME"
DEFAULT_PHOTO_ELEMENT_NAME = "APILENA"

REQUIRED_REFERENCE_SOURCE_ELEMENT_ID_SOURCE = EXPECTED_PHOTO_ELEMENT_ENV_VAR

# Env vars that identify non-photo (studio/podcast) elements which must never
# resolve as the photo lane's identity.
FORBIDDEN_PHOTO_ELEMENT_ENV_VARS = (
    "KLING_STUDIO_ELEMENT_ASSET_ID",
    "KLING_STUDIO_ELEMENT_UI_ID",
    "KLING_PODCAST_STUDIO_ELEMENT_ASSET_ID",
    "KLING_PODCAST_STUDIO_ELEMENT_UI_ID",
)

# Env vars whose presence must hard-fail the live photo lane -- manual
# reference-image overrides that previously let stale/manual URLs silently
# outrank the live Kling element lookup (containment finding, 2026-07-05).
FORBIDDEN_MANUAL_OVERRIDE_ENV_VARS = (
    "KLING_LENA_ELEMENT_IMAGE_URLS_JSON",
    "KLING_LENA_ELEMENT_IMAGE_URLS",
)


def clean_element_id(value: object) -> str:
    """Normalize a Kling element id: strip quotes/whitespace and a leading 'u_'."""
    raw = str(value or "").strip().strip('"').strip("'")
    if raw.startswith("u_"):
        raw = raw[2:]
    return raw


def resolve_expected_photo_element() -> Optional[Tuple[str, str]]:
    """Return (env_var_name, numeric_id) for the current approved Lena photo
    element, or None if it isn't configured."""
    raw = clean_element_id(os.environ.get(EXPECTED_PHOTO_ELEMENT_ENV_VAR, ""))
    if raw.isdigit():
        return EXPECTED_PHOTO_ELEMENT_ENV_VAR, raw
    return None


def require_expected_photo_element() -> Tuple[str, str]:
    """Same as resolve_expected_photo_element but raises if unset, for callers
    that must fail closed rather than warn (e.g. the executor's backend name
    and any script about to spend generation credit)."""
    resolved = resolve_expected_photo_element()
    if not resolved:
        raise RuntimeError(
            f"{EXPECTED_PHOTO_ELEMENT_ENV_VAR} is required. Lena photo generation is "
            "APILENA UI element only."
        )
    return resolved


def expected_photo_element_name() -> str:
    return (
        str(os.environ.get(EXPECTED_PHOTO_ELEMENT_NAME_ENV_VAR, DEFAULT_PHOTO_ELEMENT_NAME)).strip()
        or DEFAULT_PHOTO_ELEMENT_NAME
    )


def forbidden_photo_element_ids() -> Dict[str, str]:
    """Return {numeric_id: env_var_name} for studio/podcast elements that must
    never resolve as the photo lane's identity."""
    forbidden: Dict[str, str] = {}
    for name in FORBIDDEN_PHOTO_ELEMENT_ENV_VARS:
        raw = clean_element_id(os.environ.get(name, ""))
        if raw.isdigit():
            forbidden[raw] = name
    return forbidden


def assert_no_manual_reference_override() -> None:
    """Hard-fail if a manual reference-image override env var is set."""
    for name in FORBIDDEN_MANUAL_OVERRIDE_ENV_VARS:
        if str(os.environ.get(name, "")).strip():
            raise RuntimeError(
                f"{name} is set. Manual Lena reference-image override is disabled "
                "for the live photo lane. Unset this variable before running generation."
            )
