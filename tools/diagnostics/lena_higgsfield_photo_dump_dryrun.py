from __future__ import annotations

# Local, no-call diagnostic for a cohesive multi-image Lena Higgsfield
# "photo-dump" prompt pack (2026-07-08). Builds N in-memory Higgsfield-native
# prompt packages via generate_higgsfield_photo_dump_pack() -- one call per
# image to the same generate_higgsfield_prompt_package() builder already used
# by tools/diagnostics/lena_higgsfield_payload_dryrun.py -- and reports pack-
# level distribution/variety plus per-image metadata and validation counts.
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
#     explicitly, so Nicolas can manually copy/test one into Higgsfield.
#
# Run (summary only):
#   python tools/diagnostics/lena_higgsfield_photo_dump_dryrun.py --date 2026-07-08 --slot-prefix pack01 --count 10
#
# Run (with full prompt text):
#   python tools/diagnostics/lena_higgsfield_photo_dump_dryrun.py --date 2026-07-08 --slot-prefix pack01 --count 10 --show-prompts

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# In-memory only: builds the real Higgsfield-native photo-dump pack to report
# on below. No network/subprocess/Higgsfield SDK import, no file writes --
# same hard constraints as the rest of this script.
from pipeline.prompting.lena_prompt_brain import (
    generate_higgsfield_photo_dump_pack,
    HIGGSFIELD_FRAMING_LINE,
    HIGGSFIELD_WARDROBE_CASUAL_BLOCK_TERMS,
    HIGGSFIELD_SCENE_ACTION_CONFLICT_TERMS,
    HIGGSFIELD_POSE_REINFORCEMENT_LINE,
    HIGGSFIELD_EXPRESSION_REINFORCEMENT_LINE,
    HIGGSFIELD_PHOTO_DUMP_MIN_COUNT,
    HIGGSFIELD_PHOTO_DUMP_MAX_COUNT,
    HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT,
    HIGGSFIELD_PHOTO_DUMP_POSE_VARIANTS,
)

# A photo-dump pack should show real pose variety, not one clone repeated
# across every image.
HIGGSFIELD_PHOTO_DUMP_MIN_DISTINCT_POSES = 3

ACTIVE_PROVIDER = "higgsfield"
LEGACY_PROVIDER_STATUS = (
    "kling: legacy/historical/archive-compatibility only -- not the active "
    "generation path; not extended or optimized for going forward"
)

# Detection-only list, for reporting purposes in this diagnostic. Deliberately
# NOT imported from lena_prompt_brain.py -- this list is diagnostic-only and
# never injected into any prompt.
#
# Reworked 2026-07-09 (Nicolas direction change, new evidence), updated again
# same day: on 2026-07-08 this list existed to confirm a forced heavy
# body/hip-geometry block stayed removed, and included ordinary
# body-description terms like "wide hips" for that purpose. Nicolas has since
# reversed that decision -- real motorcycle-lane output showed Lena's
# hips/body silhouette drifting narrow, and a reusable
# HIGGSFIELD_BODY_SILHOUETTE_ANCHOR (in lena_prompt_brain.py) is now always
# present in every Higgsfield prompt, using exactly this kind of language
# ("visibly wide hips", "fuller hip flare", "waist-to-hip curve", etc.) on
# purpose. "wide hips" was removed for this reason on 2026-07-09. Later the
# same day, Nicolas's "fit-curvy medium frame" correction (target: not
# skinny/runway-thin, not plus-size) added "fuller upper thighs"/"fuller
# thighs" to the approved anchor itself, so "fuller thighs" is now removed
# from this list too -- it is no longer overcorrection, it is the approved
# target body language. This list now only detects genuine
# anatomical-distortion/overcorrection language that was never part of the
# approved anchor -- impossible or cartoonish anatomy, exaggerated/fake
# proportions, extreme distortion, or fetishized wording -- not the normal,
# expected, now-required body-shape description.
HEAVY_BODY_OVERCORRECTION_TERMS = (
    "strong waist-to-hip contrast",
    "not narrow",
    "not slim-hipped",
    "outside curve of her hips",
    "impossible anatomy",
    "cartoonish proportions",
    "exaggerated fake proportions",
    "extreme body distortion",
    "unrealistic hip size",
    "fetishized proportions",
)


def _extract_wardrobe_segment(prompt: str) -> str:
    """Isolate the 'Wardrobe: ... Pose:' segment so the casual-term check below
    matches the actual sanitizer's scope (wardrobe text only) instead of
    false-flagging legitimate scene/environment words that happen to share a
    substring with a wardrobe-casual block term. Same approach as the
    single-image diagnostic (lena_higgsfield_payload_dryrun.py)."""
    match = re.search(r"Wardrobe:\s*(.*?)\s*Pose:", prompt, flags=re.S)
    return match.group(1) if match else ""


def _validate_image(package: dict) -> dict:
    prompt = package["image_prompt"]
    lower = prompt.lower()
    wardrobe_segment_lower = _extract_wardrobe_segment(prompt).lower()

    wardrobe_terms_found = [
        term for term in HIGGSFIELD_WARDROBE_CASUAL_BLOCK_TERMS if term in wardrobe_segment_lower
    ]
    scene_conflict_terms_found = [
        term for term in HIGGSFIELD_SCENE_ACTION_CONFLICT_TERMS if term in lower
    ]
    heavy_terms_found = [
        term for term in HEAVY_BODY_OVERCORRECTION_TERMS if term in lower
    ]

    return {
        "framing_present": HIGGSFIELD_FRAMING_LINE in prompt,
        "wardrobe_casual_free": not wardrobe_terms_found,
        "wardrobe_casual_terms_found": wardrobe_terms_found,
        "scene_action_conflict_free": not scene_conflict_terms_found,
        "scene_action_conflict_terms_found": scene_conflict_terms_found,
        # Photo-dump images have their pose line swapped for one of
        # HIGGSFIELD_PHOTO_DUMP_POSE_VARIANTS (see generate_higgsfield_
        # photo_dump_pack's pose-substitution step) -- check for either the
        # original single-image line or one of the variants, since either
        # represents a real full-body/hip-forward pose reinforcement.
        "pose_reinforcement_present": (
            HIGGSFIELD_POSE_REINFORCEMENT_LINE in prompt
            or any(variant in prompt for variant in HIGGSFIELD_PHOTO_DUMP_POSE_VARIANTS)
        ),
        "expression_reinforcement_present": HIGGSFIELD_EXPRESSION_REINFORCEMENT_LINE in prompt,
        "soul_anchor_absent": "Use my trained Soul" not in prompt,
        "negative_prompt_disabled": package["negative_prompt_enabled"] is False,
        "heavy_overcorrection_free": not heavy_terms_found,
        "heavy_overcorrection_terms_found": heavy_terms_found,
        # Computed by generate_higgsfield_photo_dump_pack() itself (the
        # pack-builder's own retry/accept decision), read back here for
        # reporting only -- not recomputed independently.
        "low_hook_terms_found": package.get("photo_dump_low_hook_terms_found", []),
        "hook_terms_found": package.get("photo_dump_hook_terms_found", []),
        "mood_hook_terms_found": package.get("photo_dump_mood_hook_terms_found", []),
        "hook_pass": package.get("photo_dump_hook_pass", False),
        "pose_scene_match_pass": package.get("photo_dump_pose_scene_match_pass", False),
        "pose_scene_mismatch_terms_found": package.get(
            "photo_dump_pose_scene_mismatch_terms_found", []
        ),
    }


def build_report(date_str: str, slot_prefix: str, count: int) -> dict:
    pack = generate_higgsfield_photo_dump_pack(date_str, slot_prefix, count=count)

    per_image = []
    for idx, package in enumerate(pack["images"]):
        validation = _validate_image(package)
        per_image.append(
            {
                "index": idx,
                "slot_id": package["slot_id"],
                "lane": package["lane"],
                "wardrobe_outfit_id": package.get("wardrobe_outfit_id"),
                "wardrobe_outfit_name": package.get("wardrobe_outfit_name"),
                "wardrobe_silhouette_class": package.get("wardrobe_silhouette_class"),
                "pose_body_language_id": package.get("pose_body_language_id"),
                "pose_body_language_label": package.get("pose_body_language_label"),
                "photo_dump_pose_variant": package.get("photo_dump_pose_variant"),
                "expression_gaze_id": package.get("expression_gaze_id"),
                "expression_gaze_label": package.get("expression_gaze_label"),
                "prompt_length": len(package["image_prompt"]),
                "negative_prompt_enabled": package["negative_prompt_enabled"],
                "soul_name": package["soul_name"],
                "soul_version": package["soul_version"],
                "soul_selection_mode": package["soul_selection_mode"],
                "validation": validation,
                "image_prompt": package["image_prompt"],
            }
        )

    lengths = [item["prompt_length"] for item in per_image]
    n = len(per_image)

    def _count(key: str) -> int:
        return sum(1 for item in per_image if item["validation"][key])

    return {
        "date": date_str,
        "slot_prefix": slot_prefix,
        "active_provider": ACTIVE_PROVIDER,
        "legacy_provider_status": LEGACY_PROVIDER_STATUS,
        "requested_count": pack["requested_count"],
        "count": pack["count"],
        "count_clamped": pack["count_clamped"],
        "count_valid_range": (HIGGSFIELD_PHOTO_DUMP_MIN_COUNT, HIGGSFIELD_PHOTO_DUMP_MAX_COUNT),
        "lane_cap": pack["lane_cap"],
        "silhouette_cap": pack["silhouette_cap"],
        "lane_distribution": pack["lane_distribution"],
        "wardrobe_silhouette_distribution": pack["wardrobe_silhouette_distribution"],
        "pose_variant_distribution": pack["pose_variant_distribution"],
        "distinct_pose_variant_count": len(pack["pose_variant_distribution"]),
        "pose_variant_warning": (
            None
            if len(pack["pose_variant_distribution"]) >= HIGGSFIELD_PHOTO_DUMP_MIN_DISTINCT_POSES
            else (
                f"only {len(pack['pose_variant_distribution'])} distinct pose "
                f"variant(s) in this pack, below the minimum of "
                f"{HIGGSFIELD_PHOTO_DUMP_MIN_DISTINCT_POSES}"
            )
        ),
        "variety_warnings": pack["variety_warnings"],
        "prompt_length_min": min(lengths) if lengths else 0,
        "prompt_length_avg": (sum(lengths) // n) if n else 0,
        "prompt_length_max": max(lengths) if lengths else 0,
        "validation_counts": {
            "framing_present": (_count("framing_present"), n),
            "wardrobe_casual_free": (_count("wardrobe_casual_free"), n),
            "scene_action_conflict_free": (_count("scene_action_conflict_free"), n),
            "pose_reinforcement_present": (_count("pose_reinforcement_present"), n),
            "expression_reinforcement_present": (_count("expression_reinforcement_present"), n),
            "soul_anchor_absent": (_count("soul_anchor_absent"), n),
            "negative_prompt_disabled": (_count("negative_prompt_disabled"), n),
            "heavy_overcorrection_free": (_count("heavy_overcorrection_free"), n),
            "hook_pass": (_count("hook_pass"), n),
            "pose_scene_match_pass": (_count("pose_scene_match_pass"), n),
        },
        "images": per_image,
    }


def print_report(report: dict, show_prompts: bool) -> None:
    print("=== Higgsfield photo-dump pack -- LOCAL NO-CALL DRY RUN ===\n")
    print(f"date                        : {report['date']}")
    print(f"slot_prefix                 : {report['slot_prefix']}")
    print(f"active provider             : {report['active_provider']}")
    print(f"legacy provider status      : {report['legacy_provider_status']}")
    print()
    print(f"requested count             : {report['requested_count']}")
    print(f"actual count (after clamp)  : {report['count']}")
    if report["count_clamped"]:
        lo, hi = report["count_valid_range"]
        print(f"  NOTE: requested count was outside the normal [{lo}, {hi}] range and was clamped.")
    print()
    print(f"lane cap (soft)             : {report['lane_cap']}")
    print(f"silhouette cap (soft)       : {report['silhouette_cap']}")
    print(f"lane distribution           : {report['lane_distribution']}")
    print(f"wardrobe silhouette distrib : {report['wardrobe_silhouette_distribution']}")
    print(f"pose variant distribution   : {report['pose_variant_distribution']}")
    print(f"distinct pose variants      : {report['distinct_pose_variant_count']} "
          f"(minimum required: {HIGGSFIELD_PHOTO_DUMP_MIN_DISTINCT_POSES})")
    if report["pose_variant_warning"]:
        print(f"  !! {report['pose_variant_warning']}")
    if report["variety_warnings"]:
        print("variety warnings:")
        for warning in report["variety_warnings"]:
            print(f"  - {warning}")
    else:
        print("variety warnings            : none")
    print()
    print(f"prompt length min/avg/max   : {report['prompt_length_min']} / "
          f"{report['prompt_length_avg']} / {report['prompt_length_max']} chars")
    print()
    print("validation counts (N/N across pack):")
    n = report["images"] and len(report["images"]) or 0
    labels = {
        "framing_present": "full-body/head-to-shoes/three-quarter framing present",
        "wardrobe_casual_free": "wardrobe blocked casual/shape-hiding terms absent",
        "scene_action_conflict_free": "scene/action/expression conflict terms absent",
        "pose_reinforcement_present": "hip-forward pose reinforcement present",
        "expression_reinforcement_present": "direct-gaze/confident expression reinforcement present",
        "soul_anchor_absent": "Soul prompt-text leak absent",
        "negative_prompt_disabled": "negative prompt disabled",
        "heavy_overcorrection_free": "heavy body-overcorrection terms absent",
        "hook_pass": "high-hook pass (low-hook absent AND >=1 content-specific hook term, mood terms excluded)",
        "pose_scene_match_pass": "pose text matches scene (no sitting/standing or mirror/no-mirror contradiction)",
    }
    for key, label in labels.items():
        count, total = report["validation_counts"][key]
        print(f"  {label:<58}: {count}/{total}")
    print()

    print("per-image metadata:")
    for item in report["images"]:
        print(f"  [{item['index']}] slot_id={item['slot_id']} lane={item['lane']!r}")
        print(f"      wardrobe: {item['wardrobe_outfit_id']} / {item['wardrobe_outfit_name']!r} "
              f"(silhouette={item['wardrobe_silhouette_class']!r})")
        print(f"      pose: {item['pose_body_language_id']} ({item['pose_body_language_label']!r}) "
              f"[bank draw, tracking only]")
        print(f"      photo-dump pose variant used in final prompt: {item['photo_dump_pose_variant']!r}")
        print(f"      expression: {item['expression_gaze_id']} ({item['expression_gaze_label']!r})")
        print(f"      prompt_length={item['prompt_length']} chars, "
              f"negative_prompt_enabled={item['negative_prompt_enabled']}")
        print(f"      soul_name={item['soul_name']!r} soul_version={item['soul_version']!r} "
              f"soul_selection_mode={item['soul_selection_mode']!r}")
        v = item["validation"]
        print(f"      validation: framing={v['framing_present']} "
              f"wardrobe_casual_free={v['wardrobe_casual_free']} "
              f"scene_conflict_free={v['scene_action_conflict_free']} "
              f"pose_reinforced={v['pose_reinforcement_present']} "
              f"expression_reinforced={v['expression_reinforcement_present']} "
              f"soul_leak_absent={v['soul_anchor_absent']} "
              f"neg_prompt_disabled={v['negative_prompt_disabled']} "
              f"heavy_overcorrection_free={v['heavy_overcorrection_free']} "
              f"hook_pass={v['hook_pass']} "
              f"pose_scene_match_pass={v['pose_scene_match_pass']}")
        print(f"      content-specific hook terms found: {v['hook_terms_found']}")
        print(f"      mood-only hook terms found (not counted toward pass): {v['mood_hook_terms_found']}")
        if v["low_hook_terms_found"]:
            print(f"      !! low-hook terms found: {v['low_hook_terms_found']}")
        if v["wardrobe_casual_terms_found"]:
            print(f"      !! wardrobe casual terms found: {v['wardrobe_casual_terms_found']}")
        if v["scene_action_conflict_terms_found"]:
            print(f"      !! scene/action conflict terms found: {v['scene_action_conflict_terms_found']}")
        if v["heavy_overcorrection_terms_found"]:
            print(f"      !! heavy overcorrection terms found: {v['heavy_overcorrection_terms_found']}")
        if v["pose_scene_mismatch_terms_found"]:
            print(f"      !! pose/scene mismatch: {v['pose_scene_mismatch_terms_found']}")
    print()

    if show_prompts:
        print("=== FULL PROMPT TEXT (--show-prompts) ===\n")
        for item in report["images"]:
            print(f"--- [{item['index']}] {item['slot_id']} (lane={item['lane']}) ---")
            print(item["image_prompt"])
            print()

    print("=== RESULT: no subprocess call, no network call, no Higgsfield CLI/SDK use, "
          "no Kling executor import/call, no file written. Dry-run only. ===")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="pack date, e.g. 2026-07-08")
    parser.add_argument(
        "--slot-prefix", required=True, dest="slot_prefix",
        help="slot_id prefix for this pack, e.g. pack01",
    )
    parser.add_argument(
        "--count", type=int, default=HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT,
        help=f"number of images (normal range {HIGGSFIELD_PHOTO_DUMP_MIN_COUNT}-"
             f"{HIGGSFIELD_PHOTO_DUMP_MAX_COUNT}, clamped if outside; default "
             f"{HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--show-prompts", action="store_true",
        help="also print full numbered prompt text for each image (still stdout-only, no writes)",
    )
    args = parser.parse_args()

    report = build_report(args.date, args.slot_prefix, args.count)
    print_report(report, show_prompts=args.show_prompts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
