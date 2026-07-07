from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Structured visual QA artifact for Lena photo proofs.
#
# This formalizes what has so far been prose judgments in handoff .md files (e.g.
# "acceptable pass" / "rejected" verdicts written by hand) into a machine-readable
# record with a fixed checklist, so a QA verdict can be produced, stored, and later
# consumed by a repair step instead of re-derived from memory each time.
#
# This module does not perform QA itself -- there is no automated vision model wired
# in yet. It defines the schema, builds an "unreviewed" scaffold pointing at the real
# artifacts for a slot, and validates a filled-in result for internal consistency.
#
# See pipeline/change_notes/lena_agentic_pivot_changelog.md (2026-07-05, Batch 4).
# See pipeline/agents/lena/70_visual_qa/RULES.md for the production_scoring block
# added in schema v2 (2026-07-06): hook strength / outfit variety / sexy-safe
# styling / scene variety, per the corrected production standard.

SCHEMA_VERSION = "2"

# schema_version values that predate the production_scoring block. Records
# stamped with one of these are validated under the original (v1) rules only --
# production_scoring is not required and its absence is not an error. Existing
# on-disk QA files are never rewritten to "2"; this only affects newly-built
# templates going forward.
LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING = {"1"}

ROOT = Path(__file__).resolve().parents[2]
ASSET_REVIEW_ROOT = ROOT / "pipeline" / "asset_review" / "lena"

ALLOWED_STATUS_VALUES = {"pass", "fail", "not_applicable", "unreviewed"}
ALLOWED_OVERALL_VALUES = {"pass", "fail", "unreviewed"}
ALLOWED_HOOK_STRENGTH_VALUES = {"weak", "moderate", "strong", "unreviewed"}
ALLOWED_VARIETY_STATUS_VALUES = {"pass", "fail", "not_yet_measured", "unreviewed"}

# Ordered checklist. Each entry: (field_key, human_label).
QA_CHECKLIST_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("identity_fidelity", "Identity fidelity (matches the current approved Lena element)"),
    ("face_realism_anti_generic_drift", "Face realism / anti-generic drift"),
    ("skin_realism_no_invented_marks", "Skin realism / no invented freckles or face-mark drift"),
    ("wardrobe_class_fidelity", "Wardrobe class fidelity vs. catalog outfit (diagnostic only -- does NOT gate overall pass/fail; see 70_visual_qa/RULES.md)"),
    ("public_scene_clothing_continuity", "Public-scene clothing continuity (no bra/crop/underwear drift)"),
    ("outerwear_underlayer_correctness", "Outerwear-underlayer correctness (when the outfit has a shell layer)"),
    ("body_shape_continuity", "Body-shape continuity (hips/waist/thighs per identity contract)"),
    ("hands_anatomy_sanity", "Hands / anatomy sanity"),
    ("environment_realism_scene_coherence", "Environment realism / scene coherence"),
    ("caption_scene_coherence", "Caption-scene coherence (placeholder -- not a strong check yet)"),
)
QA_CHECKLIST_KEYS = tuple(key for key, _ in QA_CHECKLIST_FIELDS)

# Production QA standard correction (2026-07-06): exact wardrobe-catalog match is
# diagnostic-only, not a production gate. See pipeline/agents/lena/70_visual_qa/
# RULES.md's "Production QA standard correction" section for the full doctrine.
DIAGNOSTIC_ONLY_CHECKLIST_KEYS: Tuple[str, ...] = ("wardrobe_class_fidelity",)
HARD_GATING_CHECKLIST_KEYS: Tuple[str, ...] = tuple(
    key for key in QA_CHECKLIST_KEYS if key not in DIAGNOSTIC_ONLY_CHECKLIST_KEYS
)

# production_scoring (schema v2, 2026-07-06): a sibling block to "checklist",
# scoring the corrected production standard directly (hook strength / outfit
# variety / sexy-but-platform-safe styling / scene variety) instead of exact
# wardrobe-catalog match. Kept separate from QA_CHECKLIST_FIELDS because these
# are a different kind of judgment (holistic/subjective, and two of them are
# not even properties of a single render -- see below), not because they are
# less important.
#
# Gating rules (see validate_qa_result()):
#   - hook_strength == "weak" forces overall: fail. "moderate"/"strong" pass.
#   - styling_sexy_platform_safe == "fail" forces overall: fail.
#   - outfit_variety_vs_recent_posts and scene_variety_vs_recent_posts are
#     ADVISORY ONLY -- no history-comparison tracker exists yet (not built in
#     this change), so neither field can force overall regardless of status.
PRODUCTION_SCORING_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("hook_strength", "Hook strength (attention-grabbing pose/expression/framing/eye-line -- 'weak' forces overall: fail)"),
    ("styling_sexy_platform_safe", "Sexy-but-platform-safe styling of the ACTUAL produced outfit ('fail' forces overall: fail)"),
    ("outfit_variety_vs_recent_posts", "Outfit variety vs. recent published posts (advisory only -- no history tracker built yet)"),
    ("scene_variety_vs_recent_posts", "Scene/environment variety vs. recent published posts (advisory only -- no history tracker built yet)"),
)
PRODUCTION_SCORING_KEYS = tuple(key for key, _ in PRODUCTION_SCORING_FIELDS)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def qa_artifact_path(date_str: str, slot_id: str) -> Path:
    return ASSET_REVIEW_ROOT / date_str / f"{slot_id}_qa.json"


def build_qa_template(slot: Dict[str, Any], date_str: str) -> Dict[str, Any]:
    """Build an "unreviewed" scaffold for a slot. Does not judge anything -- every
    checklist field starts as "unreviewed" for a human (or Claude, looking at the
    actual rendered image) to fill in. Stamped with the current SCHEMA_VERSION
    ("2"), which includes the production_scoring block -- existing on-disk "1"
    files are never touched or migrated."""
    metadata = slot.get("metadata") if isinstance(slot.get("metadata"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "slot_id": slot.get("slot_id"),
        "date": date_str,
        "media_type": slot.get("media_type"),
        "wardrobe_outfit_id": metadata.get("wardrobe_outfit_id"),
        "environment_id": metadata.get("environment_id"),
        "reviewed_by": None,
        "reviewed_at_utc": None,
        "checklist": {
            key: {"status": "unreviewed", "notes": ""} for key in QA_CHECKLIST_KEYS
        },
        "production_scoring": {
            "hook_strength": {"score": "unreviewed", "notes": ""},
            "styling_sexy_platform_safe": {"status": "unreviewed", "notes": ""},
            "outfit_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": ""},
            "scene_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": ""},
        },
        "overall": "unreviewed",
        "failure_reasons": [],
        "created_at_utc": _utc_now(),
    }


def save_qa_template(slot: Dict[str, Any], date_str: str, force: bool = False) -> Path:
    """Write the scaffold to pipeline/asset_review/lena/<date>/<slot_id>_qa.json.
    Never overwrites an existing (possibly already-reviewed) file unless force=True."""
    slot_id = str(slot.get("slot_id") or "")
    if not slot_id:
        raise ValueError("slot is missing slot_id")
    path = qa_artifact_path(date_str, slot_id)
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_qa_template(slot, date_str), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_qa_result(date_str: str, slot_id: str) -> Optional[Dict[str, Any]]:
    path = qa_artifact_path(date_str, slot_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_qa_result(qa: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Check a filled-in QA result for internal consistency. This is the guard against
    a false-green QA verdict: overall cannot be "pass" while any checklist item is
    "fail", and overall must be "fail" if any item failed."""
    errors: List[str] = []

    checklist = qa.get("checklist")
    if not isinstance(checklist, dict):
        errors.append("missing or invalid 'checklist' object")
        checklist = {}

    for key in QA_CHECKLIST_KEYS:
        entry = checklist.get(key)
        if not isinstance(entry, dict):
            errors.append(f"checklist.{key} is missing or not an object")
            continue
        status = entry.get("status")
        if status not in ALLOWED_STATUS_VALUES:
            errors.append(f"checklist.{key}.status={status!r} is not one of {sorted(ALLOWED_STATUS_VALUES)}")

    overall = qa.get("overall")
    if overall not in ALLOWED_OVERALL_VALUES:
        errors.append(f"overall={overall!r} is not one of {sorted(ALLOWED_OVERALL_VALUES)}")

    # Only hard-gating fields can force a false-green failure -- diagnostic-only
    # fields (currently just wardrobe_class_fidelity) may be "fail" while overall
    # is "pass". See DIAGNOSTIC_ONLY_CHECKLIST_KEYS above.
    any_failed = any(
        isinstance(checklist.get(key), dict) and checklist[key].get("status") == "fail"
        for key in HARD_GATING_CHECKLIST_KEYS
    )
    if any_failed and overall != "fail":
        errors.append("a checklist item is 'fail' but overall is not 'fail' -- false-green verdict")
    if overall == "fail" and not qa.get("failure_reasons"):
        errors.append("overall is 'fail' but failure_reasons is empty")
    if overall == "pass" and any_failed:
        errors.append("overall is 'pass' while a checklist item is 'fail'")

    # production_scoring (schema v2). Required only for records not stamped with a
    # legacy pre-v2 schema_version -- absence on a "1" record is not an error.
    requires_production_scoring = (
        qa.get("schema_version") not in LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING
    )
    production_scoring_forces_fail = False

    if requires_production_scoring:
        production_scoring = qa.get("production_scoring")
        if not isinstance(production_scoring, dict):
            errors.append(
                "missing or invalid 'production_scoring' object "
                "(required unless schema_version is a legacy pre-v2 version)"
            )
            production_scoring = {}

        hook_entry = production_scoring.get("hook_strength")
        if not isinstance(hook_entry, dict):
            errors.append("production_scoring.hook_strength is missing or not an object")
        else:
            hook_score = hook_entry.get("score")
            if hook_score not in ALLOWED_HOOK_STRENGTH_VALUES:
                errors.append(
                    f"production_scoring.hook_strength.score={hook_score!r} is not one of "
                    f"{sorted(ALLOWED_HOOK_STRENGTH_VALUES)}"
                )
            if hook_score == "weak":
                production_scoring_forces_fail = True

        styling_entry = production_scoring.get("styling_sexy_platform_safe")
        if not isinstance(styling_entry, dict):
            errors.append("production_scoring.styling_sexy_platform_safe is missing or not an object")
        else:
            styling_status = styling_entry.get("status")
            if styling_status not in ALLOWED_STATUS_VALUES:
                errors.append(
                    f"production_scoring.styling_sexy_platform_safe.status={styling_status!r} is not "
                    f"one of {sorted(ALLOWED_STATUS_VALUES)}"
                )
            if styling_status == "fail":
                production_scoring_forces_fail = True

        # outfit_variety_vs_recent_posts / scene_variety_vs_recent_posts: advisory
        # only. Their status is validated for shape, but can NEVER contribute to
        # production_scoring_forces_fail -- no history-comparison tracker exists
        # yet, so gating on these would be gating on an unmeasured signal.
        for variety_key in ("outfit_variety_vs_recent_posts", "scene_variety_vs_recent_posts"):
            variety_entry = production_scoring.get(variety_key)
            if not isinstance(variety_entry, dict):
                errors.append(f"production_scoring.{variety_key} is missing or not an object")
            else:
                variety_status = variety_entry.get("status")
                if variety_status not in ALLOWED_VARIETY_STATUS_VALUES:
                    errors.append(
                        f"production_scoring.{variety_key}.status={variety_status!r} is not one of "
                        f"{sorted(ALLOWED_VARIETY_STATUS_VALUES)}"
                    )

    if production_scoring_forces_fail and overall != "fail":
        errors.append(
            "production_scoring has a gating failure (hook_strength=='weak' or "
            "styling_sexy_platform_safe=='fail') but overall is not 'fail' -- false-green verdict"
        )
    if overall == "pass" and production_scoring_forces_fail:
        errors.append("overall is 'pass' while production_scoring has a gating failure")

    return (len(errors) == 0, errors)
