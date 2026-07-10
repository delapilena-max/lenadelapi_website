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
#
# Schema v3 (2026-07-08, Visual Hook / Allure Hard Gate): six more
# production_scoring fields (allure_level, it_girl_energy,
# body_visibility_score, outfit_hook_score, pose_attitude_score,
# feed_worthy_reason) force a technically-coherent-but-boring/generic/non-
# alluring/non-"Lena-feed-worthy" image to fail even when every original
# checklist item and hook_strength/styling_sexy_platform_safe pass. See
# 70_visual_qa/RULES.md's "Visual Hook / Allure hard gate" section.
#
# Schema v4 (2026-07-10, head framing safety margin): one new hard-gating
# checklist field, head_framing_safety_margin -- added after a real live
# incident (readypack0709-pack003-08-photo, published 2026-07-10, Instagram
# media 18054323045770081): the source image's head was technically inside
# frame (full head/hair/face/eyes all present) but with only ~2-3% headroom
# margin, and the live post rendered with the head cut off. This field
# judges the RENDERED SOURCE IMAGE ITSELF -- whether headroom is comfortably
# safe, not merely technically non-clipped. It is deliberately separate from,
# and does not duplicate or predict, the Instagram feed-photo aspect-ratio
# gate added the same day in pipeline/publisher/instagram_queue_bridge.py
# (which checks whether the image's *shape* is valid for Instagram feed
# publishing, a platform-compatibility question). The two protections are
# independent and both required: this field can fail a perfectly
# feed-ratio-compatible image that still has unsafe framing, and the bridge
# gate can fail a perfectly-framed image whose shape is simply the wrong
# ratio for feed photos.

SCHEMA_VERSION = "4"

# schema_version values that predate the production_scoring block. Records
# stamped with one of these are validated under the original (v1) rules only --
# production_scoring is not required and its absence is not an error. Existing
# on-disk QA files are never rewritten to "2"; this only affects newly-built
# templates going forward.
LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING = {"1"}

# schema_version values that predate the Visual Hook / Allure Gate fields
# (allure_level, it_girl_energy, body_visibility_score, outfit_hook_score,
# pose_attitude_score, feed_worthy_reason). Both "1" (predates
# production_scoring entirely) and "2" (has production_scoring, but only the
# original hook_strength/styling_sexy_platform_safe/variety fields) are exempt
# -- existing "1" and "2" QA files on disk are never migrated or rewritten and
# must keep validating exactly as they did before this patch.
LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE = {"1", "2"}

# schema_version values that predate the pose_action_scene_compliance
# checklist field (2026-07-10). Backward-compatibility fix, found and
# corrected the same day the field was added: the base `checklist` loop in
# validate_qa_result() has never had a legacy-exemption mechanism the way
# production_scoring/the Allure Gate fields do, so adding this field to
# QA_CHECKLIST_FIELDS silently broke validation of every pre-existing QA
# record on disk (8 real records, all schema_version "1" or "2" -- none are
# "3", so no new SCHEMA_VERSION bump is needed; the existing "1"/"2"
# boundary already exactly separates old from new). Existing "1"/"2" QA
# files on disk are never migrated or rewritten -- this only changes
# whether the field's *absence* is treated as an error for them. If a
# legacy record happens to already have this field (e.g. a future manual
# edit), it is still fully validated normally, including gating overall on
# a "fail" status -- the exemption applies only to outright absence.
LEGACY_SCHEMA_VERSIONS_WITHOUT_POSE_ACTION_SCENE_COMPLIANCE = {"1", "2"}

# schema_version values that predate the head_framing_safety_margin
# checklist field (2026-07-10, schema v4). Unlike
# LEGACY_SCHEMA_VERSIONS_WITHOUT_POSE_ACTION_SCENE_COMPLIANCE (which only
# needed to exempt "1"/"2" because no real "3" record existed yet with that
# gap at the time it was added), real "3" records already exist on disk
# (including the Candidate C incident record itself) without this new
# field -- so "3" must be exempt here too, alongside "1" and "2". This is
# why this addition bumps SCHEMA_VERSION to "4" rather than reusing the
# same-day, no-bump pattern: only newly-built "4" records are required to
# answer this field. Existing "1"/"2"/"3" QA files on disk are never
# migrated or rewritten -- this only changes whether the field's outright
# *absence* is treated as an error for them. If a legacy record happens to
# already have this field, it is still fully validated normally, including
# gating overall on a "fail" status -- the exemption covers absence only.
LEGACY_SCHEMA_VERSIONS_WITHOUT_HEAD_FRAMING_SAFETY_MARGIN = {"1", "2", "3"}

ROOT = Path(__file__).resolve().parents[2]
ASSET_REVIEW_ROOT = ROOT / "pipeline" / "asset_review" / "lena"

ALLOWED_STATUS_VALUES = {"pass", "fail", "not_applicable", "unreviewed"}
ALLOWED_OVERALL_VALUES = {"pass", "fail", "unreviewed"}
ALLOWED_HOOK_STRENGTH_VALUES = {"weak", "moderate", "strong", "unreviewed"}
ALLOWED_VARIETY_STATUS_VALUES = {"pass", "fail", "not_yet_measured", "unreviewed"}
ALLOWED_ALLURE_LEVEL_VALUES = {"none", "mild", "strong", "unreviewed"}
ALLOWED_BODY_VISIBILITY_SCORE_VALUES = {"low", "medium", "high", "unreviewed"}
# outfit_hook_score / pose_attitude_score reuse the same weak/moderate/strong
# scale as hook_strength (ALLOWED_HOOK_STRENGTH_VALUES) -- deliberately not a
# separate 1-10 numeric scale, to keep validation simple and consistent with
# the one scoring scale the schema already uses.

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
    # Added 2026-07-10 (Nicolas, explicit approval), first proven example: two
    # consecutive real Higgsfield renders of the exact same accepted prompt
    # ("sitting on a city bench," pose_p012) rendered Lena standing, not
    # seated. General semantic-compliance field, not a special-cased
    # "city_bench -> must be seated" rule: does the rendered physical state
    # or action match what the intended scene explicitly requires, rather
    # than merely looking stylistically similar (seated vs standing, holding
    # an object vs not, walking vs a static contradictory pose, a mirror
    # selfie without coherent mirror/phone logic, eating without coherent
    # food/table interaction, driving without coherent car/seat/steering
    # interaction, etc.). Hard-gating by construction: it is a plain member
    # of QA_CHECKLIST_KEYS, not listed in DIAGNOSTIC_ONLY_CHECKLIST_KEYS, so
    # it is automatically included in HARD_GATING_CHECKLIST_KEYS and in
    # validate_qa_result()'s existing false-green loop below. Correction
    # (2026-07-10, same day): adding this field DID silently break
    # validation of every pre-existing QA record on disk, since the base
    # checklist-presence loop had no legacy-exemption mechanism -- see
    # LEGACY_SCHEMA_VERSIONS_WITHOUT_POSE_ACTION_SCENE_COMPLIANCE above and
    # its use in validate_qa_result() for the narrow fix.
    ("pose_action_scene_compliance", "Pose/action-scene compliance (rendered physical state/action must not contradict what the scene explicitly requires, e.g. seated vs standing, holding vs not holding, walking vs static, mirror/eating/driving logic)"),
    # Added 2026-07-10 (schema v4), after a real live incident -- see the
    # SCHEMA_VERSION comment block above and
    # LEGACY_SCHEMA_VERSIONS_WITHOUT_HEAD_FRAMING_SAFETY_MARGIN. Hard-gating
    # by construction: a plain member of QA_CHECKLIST_KEYS, not listed in
    # DIAGNOSTIC_ONLY_CHECKLIST_KEYS, so it is automatically included in
    # HARD_GATING_CHECKLIST_KEYS and in validate_qa_result()'s existing
    # false-green loop below.
    #
    # PASS requires: full head visibly inside the frame; hair fully visible;
    # face visible; both eyes visible when naturally expected from the pose;
    # no accidental clipping of skull, hairline, or top of head; enough
    # visible top margin that the framing is comfortably safe, not merely
    # technically non-clipped.
    #
    # FAIL includes: top of head clipped; hair cut off by the frame edge;
    # forehead/hairline cropped unintentionally; face outside frame; eyes
    # outside frame; framing so tight against the top edge that there is
    # effectively no safety margin; a composition that would obviously be
    # unsafe for normal platform presentation.
    #
    # Judges the rendered source image itself -- deliberately NOT responsible
    # for predicting undocumented Instagram crop behavior; that is the
    # separate, independent job of the Instagram feed-photo aspect-ratio gate
    # in pipeline/publisher/instagram_queue_bridge.py. Do not conflate the two.
    ("head_framing_safety_margin", "Head framing safety margin (full head/hair/face/eyes inside frame with comfortable safety margin, not merely technically non-clipped)"),
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
#   - (schema v3+ only, see LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE)
#     allure_level == "none" forces overall: fail.
#   - (schema v3+ only) it_girl_energy == "fail" forces overall: fail.
#   - (schema v3+ only) body_visibility_score / outfit_hook_score /
#     pose_attitude_score are ADVISORY ONLY for this first patch -- validated
#     for allowed values, never force overall by themselves. Meant to force
#     structured reviewer attention without over-constraining the system
#     before real usage data.
#   - (schema v3+ only) feed_worthy_reason must be a non-empty string once the
#     record is finalized (overall is "pass" or "fail", not "unreviewed") --
#     forces the reviewer to answer "would this stop someone scrolling, and
#     why or why not?" explicitly rather than leaving it implicit in scores.
PRODUCTION_SCORING_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("hook_strength", "Hook strength (attention-grabbing pose/expression/framing/eye-line -- 'weak' forces overall: fail)"),
    ("styling_sexy_platform_safe", "Sexy-but-platform-safe styling of the ACTUAL produced outfit ('fail' forces overall: fail)"),
    ("outfit_variety_vs_recent_posts", "Outfit variety vs. recent published posts (advisory only -- no history tracker built yet)"),
    ("scene_variety_vs_recent_posts", "Scene/environment variety vs. recent published posts (advisory only -- no history tracker built yet)"),
    ("allure_level", "Allure level: none/mild/strong -- schema v3+ only, 'none' forces overall: fail"),
    ("it_girl_energy", "IT-girl / main-character energy: pass/fail -- schema v3+ only, 'fail' forces overall: fail"),
    ("body_visibility_score", "Body visibility (bust/waist/hips/thighs): low/medium/high -- schema v3+ only, advisory"),
    ("outfit_hook_score", "Outfit hook strength: weak/moderate/strong -- schema v3+ only, advisory"),
    ("pose_attitude_score", "Pose attitude/confidence: weak/moderate/strong -- schema v3+ only, advisory"),
    ("feed_worthy_reason", "Free-text answer to 'would this stop someone scrolling, and why or why not?' -- schema v3+ only, required non-empty once finalized"),
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
    ("4"), which includes the production_scoring block, the Visual Hook /
    Allure Gate fields, and the head_framing_safety_margin checklist field --
    existing on-disk "1"/"2"/"3" files are never touched or migrated."""
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
            "allure_level": {"level": "unreviewed", "notes": ""},
            "it_girl_energy": {"status": "unreviewed", "notes": ""},
            "body_visibility_score": {"score": "unreviewed", "notes": ""},
            "outfit_hook_score": {"score": "unreviewed", "notes": ""},
            "pose_attitude_score": {"score": "unreviewed", "notes": ""},
            "feed_worthy_reason": "",
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

    schema_version = qa.get("schema_version")
    for key in QA_CHECKLIST_KEYS:
        entry = checklist.get(key)
        if entry is None and key == "pose_action_scene_compliance" and (
            schema_version in LEGACY_SCHEMA_VERSIONS_WITHOUT_POSE_ACTION_SCENE_COMPLIANCE
        ):
            # Legacy record predates this field entirely -- absence is not
            # an error. If the field IS present (even on a "1"/"2" record),
            # it falls through to normal validation below, including
            # gating -- this exemption covers outright absence only.
            continue
        if entry is None and key == "head_framing_safety_margin" and (
            schema_version in LEGACY_SCHEMA_VERSIONS_WITHOUT_HEAD_FRAMING_SAFETY_MARGIN
        ):
            # Legacy ("1"/"2"/"3") record predates this field entirely --
            # absence is not an error. If the field IS present on a legacy
            # record, it falls through to normal validation below, including
            # gating -- this exemption covers outright absence only.
            continue
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

        # Visual Hook / Allure Gate (schema v3+ only, see
        # LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE). Existing "1"/"2" records
        # never reach this block and are completely unaffected.
        requires_allure_gate_fields = (
            qa.get("schema_version") not in LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE
        )
        if requires_allure_gate_fields:
            allure_entry = production_scoring.get("allure_level")
            if not isinstance(allure_entry, dict):
                errors.append("production_scoring.allure_level is missing or not an object")
            else:
                allure_level = allure_entry.get("level")
                if allure_level not in ALLOWED_ALLURE_LEVEL_VALUES:
                    errors.append(
                        f"production_scoring.allure_level.level={allure_level!r} is not one of "
                        f"{sorted(ALLOWED_ALLURE_LEVEL_VALUES)}"
                    )
                if allure_level == "none":
                    production_scoring_forces_fail = True

            it_girl_entry = production_scoring.get("it_girl_energy")
            if not isinstance(it_girl_entry, dict):
                errors.append("production_scoring.it_girl_energy is missing or not an object")
            else:
                it_girl_status = it_girl_entry.get("status")
                if it_girl_status not in ALLOWED_STATUS_VALUES:
                    errors.append(
                        f"production_scoring.it_girl_energy.status={it_girl_status!r} is not one of "
                        f"{sorted(ALLOWED_STATUS_VALUES)}"
                    )
                if it_girl_status == "fail":
                    production_scoring_forces_fail = True

            # body_visibility_score / outfit_hook_score / pose_attitude_score:
            # advisory only for this first patch -- validated for allowed
            # values, but deliberately cannot force overall by themselves. The
            # goal is structured reviewer attention, not over-constraining the
            # system before real usage data exists.
            for score_key, allowed_values in (
                ("body_visibility_score", ALLOWED_BODY_VISIBILITY_SCORE_VALUES),
                ("outfit_hook_score", ALLOWED_HOOK_STRENGTH_VALUES),
                ("pose_attitude_score", ALLOWED_HOOK_STRENGTH_VALUES),
            ):
                score_entry = production_scoring.get(score_key)
                if not isinstance(score_entry, dict):
                    errors.append(f"production_scoring.{score_key} is missing or not an object")
                else:
                    score_value = score_entry.get("score")
                    if score_value not in allowed_values:
                        errors.append(
                            f"production_scoring.{score_key}.score={score_value!r} is not one of "
                            f"{sorted(allowed_values)}"
                        )

            # feed_worthy_reason: required non-empty once the record is
            # finalized (overall is "pass" or "fail", not "unreviewed") --
            # forces the reviewer to answer "would this stop someone
            # scrolling, and why or why not?" explicitly. Drafts/templates
            # (overall == "unreviewed") are exempt, matching the existing
            # failure_reasons-only-required-on-fail convention below.
            if overall in {"pass", "fail"}:
                feed_worthy_reason = production_scoring.get("feed_worthy_reason")
                if not isinstance(feed_worthy_reason, str) or not feed_worthy_reason.strip():
                    errors.append(
                        "production_scoring.feed_worthy_reason must be a non-empty string for a "
                        "finalized (pass/fail) schema-3+ QA record"
                    )

    if production_scoring_forces_fail and overall != "fail":
        errors.append(
            "production_scoring has a gating failure (hook_strength=='weak', "
            "styling_sexy_platform_safe=='fail', allure_level=='none', or "
            "it_girl_energy=='fail') but overall is not 'fail' -- false-green verdict"
        )
    if overall == "pass" and production_scoring_forces_fail:
        errors.append("overall is 'pass' while production_scoring has a gating failure")

    return (len(errors) == 0, errors)
