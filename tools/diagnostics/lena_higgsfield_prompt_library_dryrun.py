from __future__ import annotations

# Local, no-call diagnostic for a bulk Lena Higgsfield "prompt library" --
# many photo-dump packs run back to back and aggregated into one report
# (2026-07-08). Does not reimplement any prompt or validation logic: each
# pack is built via the already-committed
# generate_higgsfield_photo_dump_pack() (pipeline/prompting/lena_prompt_brain.py)
# and validated via the already-committed single-pack dry-run's own
# build_report() (tools/diagnostics/lena_higgsfield_photo_dump_dryrun.py).
# This tool only calls that function once per pack and aggregates the
# results -- a scalable prompt-supply engine, not a new prompt builder.
#
# HARD CONSTRAINTS (enforced by construction -- this script cannot violate
# them):
#   - No subprocess, no network (no requests/urllib/http import anywhere).
#   - No Higgsfield SDK/CLI import or call of any kind.
#   - No .env read (no pipeline.env_loader import).
#   - No executor import (no pipeline.kling_apilena_api_executor import).
#   - No file writes of any kind -- stdout-only. No directories created.
#   - Default output never prints full prompt text -- lengths and IDs only.
#     Full prompt text is only printed when --show-prompts is passed
#     explicitly, grouped by pack, so Nicolas can manually copy/test prompts
#     into Higgsfield.
#
# Run (summary only):
#   python tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py --date 2026-07-08 --library-prefix july08 --packs 3 --count-per-pack 10
#
# Run (with full prompt text):
#   python tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py --date 2026-07-08 --library-prefix july08 --packs 3 --count-per-pack 10 --show-prompts

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS_DIR = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

# Reuses the single-pack dry-run's own build_report() (per-image validation,
# pack-level distributions/warnings) -- no prompt or validation logic is
# reimplemented in this file. No network/subprocess/Higgsfield SDK import,
# no file writes -- same hard constraints as the single-pack tool.
from lena_higgsfield_photo_dump_dryrun import build_report  # noqa: E402

# Read-only failure-memory feedback loop (2026-07-10), reusing only
# already-existing, already-written artifacts (pipeline/asset_review/lena/
# *_qa.json + pipeline/higgsfield_debug/.../result_manifest.json) -- no new
# persisted file, no new schema, no database. See pipeline/qa/
# lena_higgsfield_failure_memory.py's module docstring for the full
# evidence discipline (1 fail = soft flag only, 2+ fails with 0 passes =
# hard exclude, chat history is never evidence).
from pipeline.qa.lena_higgsfield_failure_memory import (  # noqa: E402
    compute_higgsfield_failure_memory,
    pattern_key_for_image,
)
from pipeline.prompting.lena_prompt_brain import (  # noqa: E402
    HIGGSFIELD_PHOTO_DUMP_MIN_COUNT,
    HIGGSFIELD_PHOTO_DUMP_MAX_COUNT,
    HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT,
    classify_effective_wardrobe_silhouette,
)

DEFAULT_PACKS = 3

# Real motorcycle model anchors (2026-07-09, Nicolas correction) -- must
# stay in sync with HIGGSFIELD_MOTO_MODEL_ANCHORS in lena_prompt_brain.py.
# Checked against the full final prompt text, lowercased. "motorcycle
# street glam" is deliberately excluded from MOTORCYCLE_VINTAGE_LANES: it
# intentionally keeps its unnamed modern sport-bike wording, per Nicolas's
# explicit instruction to leave that one lane alone "for now" -- so it is
# never reported as "missing" an anchor.
MOTORCYCLE_VINTAGE_LANES = frozenset(
    {
        "heritage moto pinup",
        "antique cruiser editorial",
        "custom chopper eye candy",
        "garage grease glam",
        "bike wash bikini",
        "desert roadside cruiser",
    }
)
MOTORCYCLE_MODEL_ANCHOR_TERMS = (
    "indian chief", "indian scout", "indian 101 scout", "indian four",
    "knucklehead", "panhead", "harley-davidson wla", "hydra-glide",
    "duo-glide", "shovelhead", "sportster ironhead", "vincent black shadow",
    "triumph bonneville", "norton commando", "bobber", "hardtail chopper",
    "long-fork",
)


def _motorcycle_model_anchor_present(lane: str, prompt_text: str) -> bool | None:
    """True/False for the 6 vintage moto lanes (real model-anchor check);
    None ("not applicable") for every other lane, including motorcycle
    street glam, which intentionally has no anchor pool."""
    if str(lane or "").strip().lower() not in MOTORCYCLE_VINTAGE_LANES:
        return None
    lower = prompt_text.lower()
    return any(term in lower for term in MOTORCYCLE_MODEL_ANCHOR_TERMS)


# Hard-QA correction (2026-07-09, Nicolas, after the first real visual
# test), then escalated same day (second correction, after reviewing real
# renders): the first correction asked for "no readable logo" but still
# allowed a small/blank badge; the final rule is stricter -- logos are
# always hidden/covered/obscured by construction, never just "blank," and
# "blank/blurred signs" became "no sign objects at all." The two checks
# below (moto_logo_authenticity/background_text_hygiene) are replaced by
# three checks matching the escalated clause's actual signature phrases;
# fake_text_avoidance is unchanged (its signature phrase, "no gibberish
# lettering," survived the rewrite unchanged). All reporting-only --
# explicitly NOT added to HOOK_* scoring, since these are correctness
# constraints, not hotness cues, and folding them into the curator's
# ranking would be a category error. Applies to all 7 moto lanes, including
# motorcycle street glam -- the logo-hidden/text-surface half of the clause
# applies there too, even without a named model.
MOTORCYCLE_ALL_LANES = MOTORCYCLE_VINTAGE_LANES | {"motorcycle street glam"}

# Signature phrases lifted verbatim from the two realism-clause variants in
# lena_prompt_brain.py (named-model and unnamed/street-glam) -- if either
# ever drifts out of sync, these checks will start reporting false
# negatives, which is the intended fail-loud behavior.
MOTO_LOGO_HIDDEN_SIGNATURE = "hidden, covered, or obscured"
NO_VISIBLE_MOTORCYCLE_LOGO_SIGNATURE = "no visible motorcycle logo"
NO_TEXT_SURFACES_SIGNATURE = "readable text surfaces"
FAKE_TEXT_AVOIDANCE_SIGNATURE = "no gibberish lettering"


def _moto_logo_hidden_clause_present(lane: str, prompt_text: str) -> bool | None:
    if str(lane or "").strip().lower() not in MOTORCYCLE_ALL_LANES:
        return None
    return MOTO_LOGO_HIDDEN_SIGNATURE in prompt_text.lower()


def _no_visible_motorcycle_logo_clause_present(lane: str, prompt_text: str) -> bool | None:
    if str(lane or "").strip().lower() not in MOTORCYCLE_ALL_LANES:
        return None
    return NO_VISIBLE_MOTORCYCLE_LOGO_SIGNATURE in prompt_text.lower()


def _no_text_surfaces_clause_present(lane: str, prompt_text: str) -> bool | None:
    if str(lane or "").strip().lower() not in MOTORCYCLE_ALL_LANES:
        return None
    return NO_TEXT_SURFACES_SIGNATURE in prompt_text.lower()


def _fake_text_avoidance_present(lane: str, prompt_text: str) -> bool | None:
    if str(lane or "").strip().lower() not in MOTORCYCLE_ALL_LANES:
        return None
    return FAKE_TEXT_AVOIDANCE_SIGNATURE in prompt_text.lower()


# The prompt-library aggregate reuses the per-image validation dict emitted by
# lena_higgsfield_photo_dump_dryrun.build_report(). Expression reporting follows
# that shared path instead of maintaining a separate local recomputation.

# The validation-count keys reported by build_report(), reused verbatim here
# so the library aggregate matches the single-pack tool's own definitions.
VALIDATION_LABELS = {
    "framing_present": "full-body/head-to-shoes/three-quarter framing present",
    "wardrobe_casual_free": "wardrobe blocked casual/shape-hiding terms absent",
    "scene_action_conflict_free": "scene/action/expression conflict terms absent",
    "pose_reinforcement_present": "hip-forward pose reinforcement present",
    "expression_reinforcement_present": "selected expression/gaze text (or safe fallback) reached final prompt",
    "soul_anchor_absent": "Soul prompt-text leak absent",
    "negative_prompt_disabled": "negative prompt disabled",
    "heavy_overcorrection_free": "heavy body-overcorrection terms absent",
    "hook_pass": "high-hook pass (low-hook absent AND >=1 content-specific hook term, mood terms excluded)",
    "pose_scene_match_pass": "pose text matches scene (no sitting/standing or mirror/no-mirror contradiction)",
}


def build_library_report(
    date_str: str,
    library_prefix: str,
    packs: int,
    count_per_pack: int,
    required_recipe_id: str = "",
    presence_contract: dict | None = None,
    presence_plan: dict | None = None,
) -> dict:
    pack_reports = []
    for pack_index in range(packs):
        slot_prefix = f"{library_prefix}-pack{pack_index:03d}"
        # count clamping to [MIN_COUNT, MAX_COUNT] happens inside
        # generate_higgsfield_photo_dump_pack() itself, via build_report() --
        # not reimplemented here.
        pack_report = build_report(
            date_str,
            slot_prefix,
            count_per_pack,
            required_recipe_id=required_recipe_id if pack_index == 0 else "",
            presence_contract=presence_contract,
            presence_plan=presence_plan,
        )
        pack_reports.append(pack_report)

    total_prompts = sum(len(p["images"]) for p in pack_reports)

    aggregate_validation_counts = {}
    for key in VALIDATION_LABELS:
        passed = sum(p["validation_counts"][key][0] for p in pack_reports)
        aggregate_validation_counts[key] = (passed, total_prompts)

    lane_distribution: Counter = Counter()
    silhouette_distribution: Counter = Counter()
    pose_variant_distribution: Counter = Counter()
    hook_term_distribution: Counter = Counter()
    all_prompt_texts: list[str] = []
    warning_count = 0
    pack_summaries = []
    motorcycle_anchor_checked = 0
    motorcycle_anchor_present = 0
    motorcycle_anchor_missing_slot_ids: list[str] = []
    moto_logo_hidden_checked = 0
    moto_logo_hidden_present = 0
    moto_logo_hidden_missing_slot_ids: list[str] = []
    no_visible_motorcycle_logo_checked = 0
    no_visible_motorcycle_logo_present = 0
    no_visible_motorcycle_logo_missing_slot_ids: list[str] = []
    no_text_surfaces_checked = 0
    no_text_surfaces_present = 0
    no_text_surfaces_missing_slot_ids: list[str] = []
    fake_text_avoidance_checked = 0
    fake_text_avoidance_present = 0
    fake_text_avoidance_missing_slot_ids: list[str] = []
    human_presence = presence_plan or next((pack.get("human_presence") for pack in pack_reports if pack.get("human_presence")), None)

    for pack_report in pack_reports:
        lane_distribution.update(pack_report["lane_distribution"])
        silhouette_distribution.update(pack_report["wardrobe_silhouette_distribution"])
        pose_variant_distribution.update(pack_report["pose_variant_distribution"])
        warning_count += len(pack_report["variety_warnings"])
        if pack_report["pose_variant_warning"]:
            warning_count += 1

        for image in pack_report["images"]:
            hook_term_distribution.update(image["validation"]["hook_terms_found"])
            all_prompt_texts.append(image["image_prompt"])
            anchor_result = _motorcycle_model_anchor_present(image["lane"], image["image_prompt"])
            if anchor_result is not None:
                motorcycle_anchor_checked += 1
                if anchor_result:
                    motorcycle_anchor_present += 1
                else:
                    motorcycle_anchor_missing_slot_ids.append(image["slot_id"])

            logo_hidden_result = _moto_logo_hidden_clause_present(image["lane"], image["image_prompt"])
            if logo_hidden_result is not None:
                moto_logo_hidden_checked += 1
                if logo_hidden_result:
                    moto_logo_hidden_present += 1
                else:
                    moto_logo_hidden_missing_slot_ids.append(image["slot_id"])

            no_visible_logo_result = _no_visible_motorcycle_logo_clause_present(
                image["lane"], image["image_prompt"]
            )
            if no_visible_logo_result is not None:
                no_visible_motorcycle_logo_checked += 1
                if no_visible_logo_result:
                    no_visible_motorcycle_logo_present += 1
                else:
                    no_visible_motorcycle_logo_missing_slot_ids.append(image["slot_id"])

            no_text_surfaces_result = _no_text_surfaces_clause_present(image["lane"], image["image_prompt"])
            if no_text_surfaces_result is not None:
                no_text_surfaces_checked += 1
                if no_text_surfaces_result:
                    no_text_surfaces_present += 1
                else:
                    no_text_surfaces_missing_slot_ids.append(image["slot_id"])

            fake_text_result = _fake_text_avoidance_present(image["lane"], image["image_prompt"])
            if fake_text_result is not None:
                fake_text_avoidance_checked += 1
                if fake_text_result:
                    fake_text_avoidance_present += 1
                else:
                    fake_text_avoidance_missing_slot_ids.append(image["slot_id"])

        pack_summaries.append(
            {
                "slot_prefix": pack_report["slot_prefix"],
                "requested_count": pack_report["requested_count"],
                "count": pack_report["count"],
                "count_clamped": pack_report["count_clamped"],
                "distinct_pose_variant_count": pack_report["distinct_pose_variant_count"],
                "pose_variant_warning": pack_report["pose_variant_warning"],
                "variety_warning_count": len(pack_report["variety_warnings"]),
                "hook_pass_count": pack_report["validation_counts"]["hook_pass"],
                "pose_scene_match_pass_count": pack_report["validation_counts"]["pose_scene_match_pass"],
            }
        )

    prompt_text_counts = Counter(all_prompt_texts)
    duplicate_prompt_count = sum(c - 1 for c in prompt_text_counts.values() if c > 1)

    report = {
        "date": date_str,
        "library_prefix": library_prefix,
        "packs_requested": packs,
        "count_per_pack_requested": count_per_pack,
        "count_valid_range": (HIGGSFIELD_PHOTO_DUMP_MIN_COUNT, HIGGSFIELD_PHOTO_DUMP_MAX_COUNT),
        "total_packs": len(pack_reports),
        "total_prompts": total_prompts,
        "pack_summaries": pack_summaries,
        "aggregate_validation_counts": aggregate_validation_counts,
        "lane_distribution": dict(lane_distribution),
        "wardrobe_silhouette_distribution": dict(silhouette_distribution),
        "pose_variant_distribution": dict(pose_variant_distribution),
        "hook_term_distribution": dict(hook_term_distribution.most_common()),
        "warning_count": warning_count,
        "duplicate_prompt_count": duplicate_prompt_count,
        "motorcycle_anchor_checked": motorcycle_anchor_checked,
        "motorcycle_anchor_present": motorcycle_anchor_present,
        "motorcycle_anchor_missing_slot_ids": motorcycle_anchor_missing_slot_ids,
        "moto_logo_hidden_checked": moto_logo_hidden_checked,
        "moto_logo_hidden_present": moto_logo_hidden_present,
        "moto_logo_hidden_missing_slot_ids": moto_logo_hidden_missing_slot_ids,
        "no_visible_motorcycle_logo_checked": no_visible_motorcycle_logo_checked,
        "no_visible_motorcycle_logo_present": no_visible_motorcycle_logo_present,
        "no_visible_motorcycle_logo_missing_slot_ids": no_visible_motorcycle_logo_missing_slot_ids,
        "no_text_surfaces_checked": no_text_surfaces_checked,
        "no_text_surfaces_present": no_text_surfaces_present,
        "no_text_surfaces_missing_slot_ids": no_text_surfaces_missing_slot_ids,
        "fake_text_avoidance_checked": fake_text_avoidance_checked,
        "fake_text_avoidance_present": fake_text_avoidance_present,
        "fake_text_avoidance_missing_slot_ids": fake_text_avoidance_missing_slot_ids,
        "pack_reports": pack_reports,
    }
    if human_presence is not None:
        report["human_presence"] = human_presence
    return report


def print_library_report(library: dict, show_prompts: bool) -> None:
    print("=== Higgsfield prompt library -- LOCAL NO-CALL DRY RUN (bulk) ===\n")
    print(f"date                        : {library['date']}")
    print(f"library_prefix              : {library['library_prefix']}")
    print(f"packs requested             : {library['packs_requested']}")
    print(f"count_per_pack requested    : {library['count_per_pack_requested']} "
          f"(normal range {library['count_valid_range'][0]}-{library['count_valid_range'][1]}, clamped if outside)")
    print()
    print(f"total packs generated       : {library['total_packs']}")
    print(f"total prompts generated     : {library['total_prompts']}")
    print(f"total warnings (variety + pose-variant, across all packs): {library['warning_count']}")
    print(f"duplicate prompt count      : {library['duplicate_prompt_count']} "
          f"(exact-text repeats beyond the first occurrence)")
    if library.get("human_presence"):
        presence = library["human_presence"]
        print(f"human presence schema      : {presence.get('schema_version')}")
        print(f"human presence plan hash   : {presence.get('plan_fingerprint_sha256')}")
        print(f"human presence enabled     : {presence.get('enabled')}")
        print(f"human presence total bonus : {presence.get('total_bonus')}")
    print()

    print("aggregate validation counts (N/N across entire library):")
    for key, label in VALIDATION_LABELS.items():
        count, total = library["aggregate_validation_counts"][key]
        print(f"  {label:<58}: {count}/{total}")
    print()

    print(
        "motorcycle model anchor present (vintage moto lanes only, "
        f"motorcycle street glam excluded by design): "
        f"{library['motorcycle_anchor_present']}/{library['motorcycle_anchor_checked']}"
    )
    if library["motorcycle_anchor_missing_slot_ids"]:
        print(f"  !! missing a real model anchor: {library['motorcycle_anchor_missing_slot_ids']}")

    print(
        "moto logo hidden clause present (all 7 moto lanes): "
        f"{library['moto_logo_hidden_present']}/{library['moto_logo_hidden_checked']}"
    )
    if library["moto_logo_hidden_missing_slot_ids"]:
        print(f"  !! missing the logo-hidden clause: {library['moto_logo_hidden_missing_slot_ids']}")

    print(
        "no visible motorcycle logo clause present (all 7 moto lanes): "
        f"{library['no_visible_motorcycle_logo_present']}/{library['no_visible_motorcycle_logo_checked']}"
    )
    if library["no_visible_motorcycle_logo_missing_slot_ids"]:
        print(f"  !! missing the no-visible-logo clause: {library['no_visible_motorcycle_logo_missing_slot_ids']}")

    print(
        "no text surfaces clause present (all 7 moto lanes): "
        f"{library['no_text_surfaces_present']}/{library['no_text_surfaces_checked']}"
    )
    if library["no_text_surfaces_missing_slot_ids"]:
        print(f"  !! missing the no-text-surfaces clause: {library['no_text_surfaces_missing_slot_ids']}")

    print(
        "fake/gibberish text avoidance present (all 7 moto lanes): "
        f"{library['fake_text_avoidance_present']}/{library['fake_text_avoidance_checked']}"
    )
    if library["fake_text_avoidance_missing_slot_ids"]:
        print(f"  !! missing the gibberish-lettering-avoidance clause: {library['fake_text_avoidance_missing_slot_ids']}")
    print()

    print(f"aggregate lane distribution           : {library['lane_distribution']}")
    print(f"aggregate wardrobe/silhouette distrib  : {library['wardrobe_silhouette_distribution']}")
    print(f"aggregate pose variant distribution    : {library['pose_variant_distribution']}")
    print(f"aggregate content-specific hook terms  : {library['hook_term_distribution']}")
    print()

    print("per-pack summary:")
    for summary in library["pack_summaries"]:
        hook_pass_count, hook_pass_total = summary["hook_pass_count"]
        pose_match_count, pose_match_total = summary["pose_scene_match_pass_count"]
        clamp_note = " (clamped)" if summary["count_clamped"] else ""
        print(
            f"  {summary['slot_prefix']:<24} count={summary['count']}{clamp_note} "
            f"distinct_poses={summary['distinct_pose_variant_count']} "
            f"variety_warnings={summary['variety_warning_count']} "
            f"pose_variant_warning={'yes' if summary['pose_variant_warning'] else 'no'} "
            f"hook_pass={hook_pass_count}/{hook_pass_total} "
            f"pose_scene_match_pass={pose_match_count}/{pose_match_total}"
        )
    print()

    if show_prompts:
        print("=== FULL PROMPT TEXT BY PACK (--show-prompts) ===\n")
        counter = 0
        for pack_report in library["pack_reports"]:
            print(f"--- PACK {pack_report['slot_prefix']} ({len(pack_report['images'])} prompts) ---\n")
            for image in pack_report["images"]:
                counter += 1
                print(
                    f"[{counter}] slot_id={image['slot_id']} lane={image['lane']!r} "
                    f"wardrobe={image['wardrobe_outfit_id']!r} "
                    f"silhouette={image['wardrobe_silhouette_class']!r} "
                    f"text_surface_risk={image.get('text_surface_risk_terms_found', [])!r}"
                )
                print(image["image_prompt"])
                print()

    print("=== RESULT: no subprocess call, no network call, no Higgsfield CLI/SDK use, "
          "no Kling executor import/call, no file written. Dry-run only. ===")


# --- Multi-axis "model hook curator" (2026-07-08) ---------------------------
#
# Corrective patch, same day: an earlier design implicitly treated "high-hook"
# as "does the wardrobe/lane contain one of ~20 fixed keywords" (mini dress,
# heels, metallic, ...). Nicolas's correction: sexy/high-hook is a *combined*
# judgment across wardrobe, pose, expression, scene, and camera -- not a
# wardrobe-only keyword search. This section scores each of those five axes
# separately from the assembled prompt text (and, for pose/expression, from
# the pose-bank/expression-bank draw metadata, since the Higgsfield builder's
# actual Pose/Expression prompt LINES are themselves fixed/shared across every
# prompt in the system -- see the notes on _score_pose/_score_expression
# below for why bank-label metadata is the real per-image signal there).
#
# This is a read-only curation/reporting layer on top of already-generated,
# already-hard-validated prompts. It does not change what gets generated, and
# it does not touch pipeline/prompting/lena_prompt_brain.py.

_SEGMENT_BOUNDS = [
    ("scene", r"Scene:", r"Wardrobe:"),
    ("wardrobe", r"Wardrobe:", r"Pose:"),
    ("pose", r"Pose:", r"Expression:"),
    ("expression", r"Expression:", r"Camera:"),
    ("camera", r"Camera:", r"Lighting:"),
    ("lighting", r"Lighting:", r"Mood:"),
]


def _extract_prompt_segments(prompt: str) -> dict[str, str]:
    """Split an assembled Higgsfield prompt into its labeled sections
    (Scene/Wardrobe/Pose/Expression/Camera/Lighting), lowercased. Used so
    each hook-score axis only looks at its own section instead of the whole
    prompt, avoiding cross-section false matches (e.g. camera's "no mirror"
    text bleeding into a scene-based mirror check)."""
    segments: dict[str, str] = {}
    for name, start, end in _SEGMENT_BOUNDS:
        match = re.search(rf"{start}\s*(.*?)\s*{end}", prompt, flags=re.S)
        segments[name] = (match.group(1) if match else "").lower()
    return segments


# Deliberately broad and varied -- not just "mini dress". Uniform weight per
# term so no single silhouette (e.g. mini dress) is structurally favored.
HOOK_WARDROBE_TERMS = (
    "fitted dress", "wrap dress", "slip dress", "satin", "corset", "bodice",
    "waistcoat", "blazer dress", "tailored trousers", "leather skirt",
    "leather trousers", "body-skimming", "midi dress", "maxi dress",
    "thigh slit", "side slit", "metallic", "velvet", "lace", "sheer",
    "mini dress", "mini skirt", "heels", "boots", "corset-style",
    # Added 2026-07-09 (motorsport/street-glam lane): terms from
    # HIGGSFIELD_MOTO_WARDROBE_VARIANTS not already covered above.
    "moto jacket", "leather pants", "bodysuit", "halter", "racing-stripe",
    # Added 2026-07-09 (heritage-motorcycle breadth expansion): terms from
    # the 6 new wardrobe variants (moto_w06-w10) not already covered above.
    "leather seat", "suspenders", "coveralls", "bikini", "gloves", "helmet",
    # Added 2026-07-09 (Nicolas correction: skin-forward/seductive
    # expansion): terms from moto_w11-w16 not already covered above.
    "bandeau", "crop top", "midriff", "cleavage", "tied top", "open jacket",
    "bikini top", "cut-off denim shorts", "low-rise",
)

# Bank-label keywords, not prompt text -- see module comment above for why.
# Higher-attitude pose-bank labels (2026-07-08 pose/expression attitude
# layer) get more credit than plain/neutral ones.
HOOK_POSE_LABEL_REWARD_TERMS = (
    "confident", "hip_shift", "hand_on_hip", "hair_touch", "curve_visible",
)
HOOK_POSE_LABEL_NEUTRAL_TERMS = (
    "relaxed_candid_stance", "shoulders_angled_face_back",
)
# The actual assembled Pose line itself (fixed per photo-dump category, see
# HIGGSFIELD_PHOTO_DUMP_POSE_VARIANT_* in lena_prompt_brain.py) -- scored for
# presence of concrete hook cues so category choice still matters a little.
HOOK_POSE_TEXT_TERMS = (
    "hip", "toward the camera", "brushing her hair", "leaning", "confident",
    "full outfit visible", "hand near", "hand resting",
)

# Bank-label keywords for expression. Scored off the bank-selected label
# (updated 2026-07-09: the assembled Expression: text now varies per image
# too, using the real selected expression_gaze_entry["text"] -- see
# _validate_image() in lena_higgsfield_photo_dump_dryrun.py -- but scoring
# here is still keyed off the label for simplicity, unchanged by this patch).
HOOK_EXPRESSION_LABEL_REWARD_TERMS = (
    "smirk", "confident", "playful", "amused", "eyebrow", "seductive",
)
HOOK_EXPRESSION_LABEL_NEUTRAL_TERMS = (
    "relaxed_neutral_direct", "closed_mouth_smile_direct",
)

HOOK_SCENE_REWARD_TERMS = (
    "rooftop", "cocktail bar", "wine bar", "restaurant", "date-night",
    "date night", "parked car", "parking garage", "hotel", "lobby",
    "elevator", "mirror", "night out", "city-night", "city night",
    "venue", "lounge",
    # Added 2026-07-09 (motorsport/street-glam lane).
    "motorcycle", "sport bike", "garage", "industrial",
    # Added 2026-07-09 (heritage-motorcycle breadth expansion), per
    # Nicolas's explicit reward-term list. "indian-style"/"harley-style" are
    # now stale (removed from the scene bank text once real model anchors
    # were added below) but kept harmlessly in case older cached samples or
    # future scene edits still reference them.
    "indian-style", "heritage cruiser", "antique cruiser", "harley-style",
    "custom chopper", "chrome", "engine block", "exhaust pipes",
    "bike wash", "roadside", "gas station", "americana",
    # Added 2026-07-09 (real motorcycle model anchors, Nicolas correction):
    # matches HIGGSFIELD_MOTO_MODEL_ANCHORS in lena_prompt_brain.py.
    "indian chief", "indian scout", "indian 101 scout", "indian four",
    "knucklehead", "panhead", "harley-davidson wla", "hydra-glide",
    "duo-glide", "shovelhead", "sportster ironhead", "vincent black shadow",
    "triumph bonneville", "norton commando", "bobber", "hardtail chopper",
    "long-fork",
)
# Deliberately does NOT include record shop/night market/bodega/corner
# shop/music venue/vintage shop/theater (2026-07-09, Nicolas direction):
# these casual-but-editorial real-world spaces should not be structurally
# penalized just for the location -- if the wardrobe/pose/camera axes are
# high-hook, the overall score should reflect that on its own merits, not
# get capped by an automatic scene penalty. Only genuinely low-status/
# errand-coded settings stay in this list.
HOOK_SCENE_PENALTY_TERMS = (
    "coffee shop", "cafe", "brunch", "kitchen", "flower shop",
    "rainy street", "sidewalk",
)

HOOK_CAMERA_REWARD_TERMS = (
    "flash", "low-light", "golden-hour", "golden hour", "practical",
    "full-body fashion photo", "friend-shot", "candid", "grain",
    "night", "nightlife",
    # Added 2026-07-09 (motorsport/street-glam lane).
    "low-angle", "point-and-shoot", "editorial", "film grain",
)
HOOK_CAMERA_PENALTY_TERMS = (
    "overcast", "soft daylight", "bright but soft",
)

# Basic defensive check only -- the wardrobe catalog is already platform-safe
# by construction (doctrine-level, not something this diagnostic enforces);
# this exists as a safety net, not the actual guardrail.
#
# "nude" deliberately excluded (2026-07-08, caught during validation): it is
# an extremely common wardrobe color descriptor in this catalog ("nude
# heels", "nude kitten heels", "nude sandals") and matching it as a bare
# substring produced false-positive exclusions on completely safe, already-
# validated prompts. Real explicit-content terms don't have that collision.
UNSAFE_EXPLICIT_TERMS = (
    "explicit", "nsfw", "topless", "lingerie", "underwear as outerwear",
)


# --- Content-archetype diversity layer (2026-07-08, second corrective patch) -
#
# The first curator patch above scored prompts on 5 hook axes but selected
# purely by raw score with only a lane/silhouette repeat cap. On a real
# 30-prompt run this produced a Top 5 of 2x "night out" + 2x "dinner booth" +
# 1x "lobby cocktail bar" -- all nightlife/table/bar structures, and worse,
# #1/#2 and #3/#4 were near-duplicate *scenes* (same entrance/table setup,
# same pose, same camera) that only differed by wardrobe color/fabric. Raw
# score alone can't see that, because two near-duplicate scenes with strong
# wardrobe terms both score well independently.
#
# This layer adds two lane-derived classifications (content archetype, a
# specific scene "shape"; and a broader scene group, for shape families) plus
# an effective-wardrobe classifier that reads the actual final Wardrobe: text
# instead of trusting the catalog's wardrobe_silhouette_class field, which can
# go stale after a sanitizer/fallback substitution (e.g. an originally
# jeans_based catalog entry gets swapped for a "corset mini dress" by the
# high-hook fitted-wardrobe fallback in lena_prompt_brain.py, but the
# recorded silhouette-class metadata is never updated to match). All three
# drive diversity caps in curate_top_prompts() below -- this is a
# selection-time diversity layer only; it does not change PHOTO_SCENES, the
# catalog, or anything generated.

LANE_ARCHETYPE_MAP: dict[str, str] = {
    "night out": "night_out_entrance",
    "dinner booth": "dinner_table",
    "sidewalk dinner": "dinner_table",
    "lobby cocktail bar": "cocktail_bar_lobby",
    "wine bar patio": "wine_bar",
    "rooftop sunset": "rooftop",
    "car moment": "car",
    "mirror outfit check": "mirror_fit_check",
    "rainy street": "street_glam",
    "city bench": "street_glam",
    "flower shop": "street_glam",
    "record store": "street_glam",
    "apartment doorway": "apartment_going_out",
    "morning apartment": "apartment_going_out",
    "skincare evening": "apartment_going_out",
    "studio desk": "apartment_going_out",
    "late kitchen snack": "apartment_going_out",
    "coffee shop": "cafe_or_brunch_glam",
    "brunch patio": "cafe_or_brunch_glam",
    # Added 2026-07-09 (Nicolas creative direction): motorsport/real-bike
    # street-glam editorial lane, matching the new
    # "motorcycle street glam" entry in lena_photo_scene_bank_v1.json.
    "motorcycle street glam": "motorsport_street_glam",
    # Expanded 2026-07-09 (same day, breadth correction): six more
    # heritage-motorcycle lanes, each its own distinct archetype so the
    # archetype cap (max 1 per --select-top run) treats them as genuinely
    # different content, not five variations on one theme.
    "heritage moto pinup": "heritage_moto_pinup",
    "antique cruiser editorial": "antique_cruiser_editorial",
    "custom chopper eye candy": "custom_chopper_eye_candy",
    "garage grease glam": "garage_grease_glam",
    "bike wash bikini": "bike_wash_bikini",
    "desert roadside cruiser": "desert_roadside_cruiser",
}
DEFAULT_ARCHETYPE = "other"

# Broader than archetype -- groups several archetypes/lanes into one family so
# the diversity cap can also prevent e.g. several distinct table archetypes
# (dinner_table/wine_bar/cocktail_bar_lobby) from all still reading as
# "always at a table", even though each is a technically distinct archetype.
# "night out" (an entrance/venue beat, no table) is deliberately kept
# separate from "table_bar_restaurant" (literal seated-at-a-table/bar beats).
LANE_BROAD_SCENE_GROUP_MAP: dict[str, str] = {
    "night out": "nightlife",
    "dinner booth": "table_bar_restaurant",
    "sidewalk dinner": "table_bar_restaurant",
    "lobby cocktail bar": "table_bar_restaurant",
    "wine bar patio": "table_bar_restaurant",
    "car moment": "car",
    "rooftop sunset": "rooftop",
    "mirror outfit check": "mirror",
    "rainy street": "street",
    "city bench": "street",
    "flower shop": "street",
    "record store": "street",
    "apartment doorway": "apartment",
    "morning apartment": "apartment",
    "skincare evening": "apartment",
    "studio desk": "apartment",
    "late kitchen snack": "apartment",
    "coffee shop": "cafe_brunch",
    "brunch patio": "cafe_brunch",
    # Added/renamed 2026-07-09: all 7 motorcycle lanes share one broad
    # group ("motorsport_or_heritage_motorcycle") -- not folded into "car"
    # or "street" -- a real parked motorcycle (sport, cruiser, chopper, or
    # antique) reads as a distinct editorial fantasy from a parked car or a
    # generic sidewalk. Renamed from the original "motorsport_or_vehicle_
    # editorial" now that the pillar covers heritage/cruiser content, not
    # just the original sport-bike lane.
    "motorcycle street glam": "motorsport_or_heritage_motorcycle",
    "heritage moto pinup": "motorsport_or_heritage_motorcycle",
    "antique cruiser editorial": "motorsport_or_heritage_motorcycle",
    "custom chopper eye candy": "motorsport_or_heritage_motorcycle",
    "garage grease glam": "motorsport_or_heritage_motorcycle",
    "bike wash bikini": "motorsport_or_heritage_motorcycle",
    "desert roadside cruiser": "motorsport_or_heritage_motorcycle",
}
DEFAULT_BROAD_SCENE_GROUP = "other"


def _archetype_for_lane(lane: str) -> str:
    return LANE_ARCHETYPE_MAP.get(str(lane or "").lower(), DEFAULT_ARCHETYPE)


def _broad_scene_group_for_lane(lane: str) -> str:
    return LANE_BROAD_SCENE_GROUP_MAP.get(str(lane or "").lower(), DEFAULT_BROAD_SCENE_GROUP)


# Effective-wardrobe classification, derived from the *final* Wardrobe:
# segment text, not the catalog's wardrobe_silhouette_class field (see module
# note above for why that field can be stale). Moved to
# pipeline/prompting/lena_prompt_brain.py (2026-07-09, wardrobe-adherence
# workstream) as classify_effective_wardrobe_silhouette() -- single source of
# truth shared with prompt generation itself, which now also returns this
# classification directly as effective_wardrobe_silhouette_class on every
# Higgsfield package. This local name is kept only to avoid call-site churn
# below; it delegates entirely to the shared implementation.
def _classify_effective_wardrobe(wardrobe_text: str) -> str:
    return classify_effective_wardrobe_silhouette(wardrobe_text)


def _score_wardrobe(image: dict, segments: dict[str, str]) -> tuple[int, list[str]]:
    text = segments["wardrobe"]
    hits = [term for term in HOOK_WARDROBE_TERMS if term in text]
    score = len(hits)
    reasons = [f"wardrobe term: {hit!r}" for hit in hits] or ["no recognized wardrobe hook term"]
    return score, reasons


def _score_pose(image: dict, segments: dict[str, str]) -> tuple[int, list[str]]:
    label = str(image.get("pose_body_language_label") or "").lower()
    text = segments["pose"]
    score = 0
    reasons: list[str] = []

    label_hits = [term for term in HOOK_POSE_LABEL_REWARD_TERMS if term in label]
    score += len(label_hits)
    reasons += [f"pose-bank label cue: {hit!r}" for hit in label_hits]

    if any(term in label for term in HOOK_POSE_LABEL_NEUTRAL_TERMS):
        score -= 1
        reasons.append("pose-bank label reads as plain/neutral attitude (penalty)")

    text_hits = [term for term in HOOK_POSE_TEXT_TERMS if term in text]
    score += len(text_hits)
    reasons += [f"pose line cue: {hit!r}" for hit in text_hits]

    if not label_hits and not text_hits:
        reasons.append("no recognized pose hook cue")
    return score, reasons


def _score_expression(image: dict, segments: dict[str, str]) -> tuple[int, list[str]]:
    label = str(image.get("expression_gaze_label") or "").lower()
    score = 0
    reasons: list[str] = []

    label_hits = [term for term in HOOK_EXPRESSION_LABEL_REWARD_TERMS if term in label]
    score += len(label_hits)
    reasons += [f"expression-bank label cue: {hit!r}" for hit in label_hits]

    if any(term in label for term in HOOK_EXPRESSION_LABEL_NEUTRAL_TERMS):
        score -= 1
        reasons.append("expression-bank label reads as plain/neutral (penalty)")

    if not label_hits:
        reasons.append(
            "no recognized expression hook cue in bank label (rendered "
            "Expression line itself is fixed/shared across all prompts)"
        )
    return score, reasons


def _score_scene(image: dict, segments: dict[str, str]) -> tuple[int, list[str]]:
    text = segments["scene"]
    lane = str(image.get("lane") or "").lower()
    combined = f"{text} {lane}"
    score = 0
    reasons: list[str] = []

    reward_hits = [term for term in HOOK_SCENE_REWARD_TERMS if term in combined]
    score += len(reward_hits)
    reasons += [f"scene/status cue: {hit!r}" for hit in reward_hits]

    penalty_hits = [term for term in HOOK_SCENE_PENALTY_TERMS if term in combined]
    score -= len(penalty_hits)
    reasons += [f"low-status scene cue (penalty): {hit!r}" for hit in penalty_hits]

    if not reward_hits and not penalty_hits:
        reasons.append("neutral scene, no strong status cue either way")
    return score, reasons


def _score_camera(image: dict, segments: dict[str, str]) -> tuple[int, list[str]]:
    text = f"{segments['camera']} {segments['lighting']}"
    score = 0
    reasons: list[str] = []

    reward_hits = [term for term in HOOK_CAMERA_REWARD_TERMS if term in text]
    score += len(reward_hits)
    reasons += [f"camera/lighting cue: {hit!r}" for hit in reward_hits]

    penalty_hits = [term for term in HOOK_CAMERA_PENALTY_TERMS if term in text]
    score -= len(penalty_hits)
    reasons += [f"flat/sterile camera-lighting cue (penalty): {hit!r}" for hit in penalty_hits]

    if not reward_hits and not penalty_hits:
        reasons.append("neutral camera/lighting, no strong cue either way")
    return score, reasons


def _hard_exclude_reasons(image: dict) -> list[str]:
    """Hard exclusions only -- these are the same pass/fail signals the pack
    builder and single-pack diagnostic already compute; this does not
    recompute or loosen them, just reads them back for the curator's gate."""
    v = image["validation"]
    reasons = []
    if not v["framing_present"]:
        reasons.append("failed: full-body framing not present")
    if not v["wardrobe_casual_free"]:
        reasons.append(f"failed: wardrobe casual/shape-hiding terms found {v['wardrobe_casual_terms_found']}")
    if not v["scene_action_conflict_free"]:
        reasons.append(f"failed: scene/action conflict terms found {v['scene_action_conflict_terms_found']}")
    if not v["soul_anchor_absent"]:
        reasons.append("failed: Soul prompt-text leak present")
    if not v["negative_prompt_disabled"]:
        reasons.append("failed: negative prompt not disabled")
    if not v["heavy_overcorrection_free"]:
        reasons.append(f"failed: heavy body-overcorrection terms found {v['heavy_overcorrection_terms_found']}")
    if not v["pose_scene_match_pass"]:
        reasons.append(f"failed: pose/scene mismatch {v['pose_scene_mismatch_terms_found']}")
    if v["low_hook_terms_found"]:
        reasons.append(f"failed: low-hook filler terms found {v['low_hook_terms_found']}")
    prompt_lower = image["image_prompt"].lower()
    unsafe_hits = [term for term in UNSAFE_EXPLICIT_TERMS if term in prompt_lower]
    if unsafe_hits:
        reasons.append(f"failed: unsafe/explicit term(s) found {unsafe_hits}")
    return reasons


# Diversity caps applied during selection. "None" means uncapped. This is the
# *starting* (strictest) cap set -- see DIVERSITY_RELAXATION_ORDER for what
# happens if it can't fill --select-top.
DEFAULT_DIVERSITY_CAPS: dict[str, int] = {
    "archetype": 1,
    "broad_group": 2,
    "lane": 2,
    "silhouette": 2,
}

# Relaxation order when the starting caps can't fill --select-top: silhouette
# is dropped first (a wardrobe-class repeat is the least damaging kind of
# repetition -- two different scenes in the same silhouette class still read
# as different content), then broad scene group, then archetype, and lane is
# relaxed last (a lane repeat is the most visible kind of repetition --
# literally the same scene twice).
DIVERSITY_RELAXATION_ORDER: tuple[str, ...] = ("silhouette", "broad_group", "archetype", "lane")


def _greedy_select_with_caps(candidates: list[dict], select_top: int, caps: dict) -> tuple[list[dict], list[dict]]:
    """One greedy pass over score-sorted candidates, applying the given caps.
    Returns (selected, skipped) -- skipped entries carry the specific cap(s)
    that blocked them, so near-duplicate-style skips can be reported directly
    instead of inferred after the fact."""
    selected: list[dict] = []
    skipped: list[dict] = []
    counts = {
        "archetype": Counter(),
        "broad_group": Counter(),
        "lane": Counter(),
        "silhouette": Counter(),
    }
    for cand in candidates:
        if len(selected) >= select_top:
            break
        key_values = {
            "archetype": cand["archetype"],
            "broad_group": cand["broad_scene_group"],
            "lane": cand["image"]["lane"],
            "silhouette": cand["effective_wardrobe_class"],
        }
        blocking_reasons = [
            f"{cap_name} cap ({key_values[cap_name]!r})"
            for cap_name, cap_value in caps.items()
            if cap_value is not None and counts[cap_name][key_values[cap_name]] >= cap_value
        ]
        if blocking_reasons:
            skipped.append({"slot_id": cand["image"]["slot_id"], "reasons": blocking_reasons})
            continue
        selected.append(cand)
        for cap_name in counts:
            counts[cap_name][key_values[cap_name]] += 1
    return selected, skipped


def curate_top_prompts(library: dict, select_top: int) -> dict:
    """Multi-axis model-hook curation over every prompt in the library, acting
    as a creative director rather than a raw score sort: hard-excludes
    anything failing existing safety/quality validation, scores survivors
    across five independent hook axes (wardrobe, pose, expression, scene,
    camera), then greedily selects the top N under content-archetype/
    broad-scene-group/lane/effective-wardrobe diversity caps
    (DEFAULT_DIVERSITY_CAPS), relaxing caps in DIVERSITY_RELAXATION_ORDER only
    if the strict cap set can't fill select_top. Selection never re-scores or
    loosens the hard-validation gate -- diversity only decides *which*
    already-hot, already-valid prompts get picked.

    Also consults the read-only Higgsfield failure-memory aggregator
    (pipeline/qa/lena_higgsfield_failure_memory.py): a (lane,
    pose_body_language_id) pattern with 2+ real structured QA failures and
    zero passes is hard-excluded here, the same way an existing safety/
    quality failure is -- reasons are appended into exclude_reasons, same
    path, same accounting. A pattern with exactly 1 structured failure is
    never excluded, only flagged (candidate["failure_memory_flag"]) so a
    human/Claude reviewing the curation output can see it without the
    curator silently avoiding it on a single data point."""
    failure_memory = compute_higgsfield_failure_memory()
    hard_excluded_patterns = set(failure_memory["hard_excluded_patterns"])
    soft_flagged_patterns = set(failure_memory["soft_flagged_patterns"])

    candidates = []
    excluded_count = 0
    failure_memory_excluded_count = 0
    for pack_report in library["pack_reports"]:
        for image in pack_report["images"]:
            exclude_reasons = list(_hard_exclude_reasons(image))
            pattern_key = pattern_key_for_image(image)
            if pattern_key is not None and pattern_key in hard_excluded_patterns:
                lane, pose_id = pattern_key
                counts = failure_memory["pattern_counts"].get(f"{lane}::{pose_id}", {})
                exclude_reasons.append(
                    f"failed: failure-memory hard exclude -- pattern (lane={lane!r}, "
                    f"pose_body_language_id={pose_id!r}) has {counts.get('fail', '?')} real "
                    f"structured QA failures and {counts.get('pass', '?')} passes"
                )
            if exclude_reasons:
                excluded_count += 1
                if pattern_key is not None and pattern_key in hard_excluded_patterns:
                    failure_memory_excluded_count += 1
                continue
            segments = _extract_prompt_segments(image["image_prompt"])
            wardrobe_score, wardrobe_reasons = _score_wardrobe(image, segments)
            pose_score, pose_reasons = _score_pose(image, segments)
            expression_score, expression_reasons = _score_expression(image, segments)
            scene_score, scene_reasons = _score_scene(image, segments)
            camera_score, camera_reasons = _score_camera(image, segments)
            total = wardrobe_score + pose_score + expression_score + scene_score + camera_score

            # Prefer the package-provided effective classification (computed
            # once, at generation time, from the actual final wardrobe text --
            # see effective_wardrobe_silhouette_class in
            # generate_higgsfield_prompt_package()); only re-derive from text
            # here for older packages that predate that field. Never fall
            # back to the stale wardrobe_silhouette_class field as effective
            # truth.
            effective_wardrobe_class = image.get(
                "effective_wardrobe_silhouette_class"
            ) or _classify_effective_wardrobe(segments["wardrobe"])
            catalog_silhouette = image["wardrobe_silhouette_class"]
            effective_wardrobe_note = None
            if effective_wardrobe_class != catalog_silhouette:
                effective_wardrobe_note = (
                    f"final prompt wardrobe reads as {effective_wardrobe_class!r}; catalog "
                    f"silhouette metadata says {catalog_silhouette!r} (stale/overridden by "
                    "sanitizer or fallback -- effective_wardrobe_class is used for diversity "
                    "capping, not the catalog field)"
                )

            failure_memory_flag = None
            if pattern_key is not None and pattern_key in soft_flagged_patterns:
                lane, pose_id = pattern_key
                counts = failure_memory["pattern_counts"].get(f"{lane}::{pose_id}", {})
                failure_memory_flag = (
                    f"1 real structured QA failure on this exact pattern (lane={lane!r}, "
                    f"pose_body_language_id={pose_id!r}), 0 passes -- not enough evidence "
                    "to exclude, flagged for visibility only"
                )

            candidates.append(
                {
                    "image": image,
                    "total_score": total,
                    "wardrobe_score": wardrobe_score,
                    "wardrobe_reasons": wardrobe_reasons,
                    "pose_score": pose_score,
                    "pose_reasons": pose_reasons,
                    "expression_score": expression_score,
                    "expression_reasons": expression_reasons,
                    "scene_score": scene_score,
                    "scene_reasons": scene_reasons,
                    "camera_score": camera_score,
                    "camera_reasons": camera_reasons,
                    "archetype": _archetype_for_lane(image["lane"]),
                    "broad_scene_group": _broad_scene_group_for_lane(image["lane"]),
                    "effective_wardrobe_class": effective_wardrobe_class,
                    "effective_wardrobe_note": effective_wardrobe_note,
                    "failure_memory_flag": failure_memory_flag,
                }
            )

    candidates.sort(key=lambda c: c["total_score"], reverse=True)

    caps = dict(DEFAULT_DIVERSITY_CAPS)
    selected, skipped = _greedy_select_with_caps(candidates, select_top, caps)

    constraints_relaxed: list[str] = []
    relax_idx = 0
    while len(selected) < select_top and relax_idx < len(DIVERSITY_RELAXATION_ORDER):
        cap_to_relax = DIVERSITY_RELAXATION_ORDER[relax_idx]
        caps[cap_to_relax] = None
        constraints_relaxed.append(cap_to_relax)
        selected, skipped = _greedy_select_with_caps(candidates, select_top, caps)
        relax_idx += 1

    near_duplicate_skips = [s for s in skipped if any("archetype cap" in r for r in s["reasons"])]

    return {
        "select_top": select_top,
        "candidate_count": len(candidates),
        "excluded_count": excluded_count,
        "selected": selected,
        "final_caps": caps,
        "constraints_relaxed": constraints_relaxed,
        "skipped": skipped,
        "near_duplicate_skip_count": len(near_duplicate_skips),
        "failure_memory_hard_excluded_patterns": sorted(hard_excluded_patterns),
        "failure_memory_soft_flagged_patterns": sorted(soft_flagged_patterns),
        "failure_memory_excluded_count": failure_memory_excluded_count,
        "failure_memory_skipped_record_count": len(failure_memory["skipped"]),
    }


def print_curation_report(curation: dict, show_selected_prompts: bool) -> None:
    print("\n=== Multi-axis model-hook curation (with archetype diversity) ===\n")
    print(
        f"failure memory: {curation['failure_memory_skipped_record_count']} pre-existing QA "
        "record(s) not usable as Higgsfield evidence (non-Higgsfield or invalid, see "
        "pipeline/qa/lena_higgsfield_failure_memory.py for reasons)"
    )
    print(f"failure memory: hard-excluded patterns (2+ fails, 0 passes): {curation['failure_memory_hard_excluded_patterns']}")
    print(f"failure memory: soft-flagged patterns (1 fail, 0 passes)   : {curation['failure_memory_soft_flagged_patterns']}")
    print(f"failure memory: candidates hard-excluded by this signal this run: {curation['failure_memory_excluded_count']}")
    print(f"candidates considered (passed hard validation): {curation['candidate_count']}")
    print(f"hard-excluded (failed validation)              : {curation['excluded_count']}")
    print(f"requested top-N                                : {curation['select_top']}")
    print(f"actually selected                               : {len(curation['selected'])}")
    print(f"diversity caps applied (final, after any relaxation): {curation['final_caps']}")
    if curation["constraints_relaxed"]:
        print(f"constraints relaxed, in order applied          : {curation['constraints_relaxed']}")
    else:
        print("constraints relaxed                             : none needed")
    print(f"near-duplicate-style skips (blocked by archetype cap): {curation['near_duplicate_skip_count']}")
    print()

    archetypes_seen: list[str] = []
    broad_groups_seen: list[str] = []
    silhouettes_seen: list[str] = []
    lanes_seen: list[str] = []

    for rank, cand in enumerate(curation["selected"], start=1):
        image = cand["image"]
        archetypes_seen.append(cand["archetype"])
        broad_groups_seen.append(cand["broad_scene_group"])
        silhouettes_seen.append(cand["effective_wardrobe_class"])
        lanes_seen.append(image["lane"])
        print(
            f"--- #{rank} slot_id={image['slot_id']} lane={image['lane']!r} "
            f"archetype={cand['archetype']!r} broad_scene_group={cand['broad_scene_group']!r} "
            f"effective_wardrobe={cand['effective_wardrobe_class']!r} total_score={cand['total_score']} ---"
        )
        if cand["effective_wardrobe_note"]:
            print(f"    wardrobe note: {cand['effective_wardrobe_note']}")
        if cand.get("failure_memory_flag"):
            print(f"    !! failure memory flag: {cand['failure_memory_flag']}")
        print(f"    wardrobe_score={cand['wardrobe_score']}: {cand['wardrobe_reasons']}")
        print(f"    pose_score={cand['pose_score']}: {cand['pose_reasons']}")
        print(f"    expression_score={cand['expression_score']}: {cand['expression_reasons']}")
        print(f"    scene_score={cand['scene_score']}: {cand['scene_reasons']}")
        print(f"    camera_score={cand['camera_score']}: {cand['camera_reasons']}")
        if show_selected_prompts:
            print(f"    full prompt:")
            print(f"    {image['image_prompt']}")
        print()

    print(
        f"diversity summary: {len(set(archetypes_seen))} distinct archetype(s) "
        f"{sorted(set(archetypes_seen))}, {len(set(broad_groups_seen))} distinct broad scene "
        f"group(s) {sorted(set(broad_groups_seen))}, {len(set(silhouettes_seen))} distinct "
        f"effective wardrobe class(es) {sorted(set(silhouettes_seen))}, {len(set(lanes_seen))} "
        f"distinct lane(s) {sorted(set(lanes_seen))}"
    )

    print("\n=== RESULT: curation is read-only reporting over already-generated, "
          "already-validated prompts. No render, no network, no Higgsfield call, "
          "no write. ===")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="library date, e.g. 2026-07-08")
    parser.add_argument(
        "--library-prefix", required=True, dest="library_prefix",
        help="prefix for this library run, e.g. july08",
    )
    parser.add_argument(
        "--packs", type=int, default=DEFAULT_PACKS,
        help=f"number of photo-dump packs to generate (default {DEFAULT_PACKS})",
    )
    parser.add_argument(
        "--count-per-pack", type=int, dest="count_per_pack",
        default=HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT,
        help=f"images per pack (normal range {HIGGSFIELD_PHOTO_DUMP_MIN_COUNT}-"
             f"{HIGGSFIELD_PHOTO_DUMP_MAX_COUNT}, clamped if outside; default "
             f"{HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--show-prompts", action="store_true",
        help="also print full numbered prompt text for each image, grouped by pack "
             "(still stdout-only, no writes)",
    )
    parser.add_argument(
        "--select-top", type=int, dest="select_top", default=None,
        help="run the multi-axis model-hook curator and select this many top prompts "
             "across the whole library (wardrobe/pose/expression/scene/camera scoring, "
             "not a wardrobe-only search)",
    )
    parser.add_argument(
        "--show-selected-prompts", action="store_true", dest="show_selected_prompts",
        help="with --select-top, also print full prompt text for each selected prompt "
             "(still stdout-only, no writes)",
    )
    args = parser.parse_args()

    if args.packs < 1:
        print("[ABORT] --packs must be at least 1")
        return 1

    library = build_library_report(args.date, args.library_prefix, args.packs, args.count_per_pack)
    print_library_report(library, show_prompts=args.show_prompts)

    if args.select_top is not None:
        if args.select_top < 1:
            print("[ABORT] --select-top must be at least 1")
            return 1
        curation = curate_top_prompts(library, args.select_top)
        print_curation_report(curation, show_selected_prompts=args.show_selected_prompts)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
