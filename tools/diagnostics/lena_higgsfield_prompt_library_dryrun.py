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

from pipeline.prompting.lena_prompt_brain import (  # noqa: E402
    HIGGSFIELD_PHOTO_DUMP_MIN_COUNT,
    HIGGSFIELD_PHOTO_DUMP_MAX_COUNT,
    HIGGSFIELD_PHOTO_DUMP_DEFAULT_COUNT,
)

DEFAULT_PACKS = 3

# The validation-count keys reported by build_report(), reused verbatim here
# so the library aggregate matches the single-pack tool's own definitions.
VALIDATION_LABELS = {
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


def build_library_report(date_str: str, library_prefix: str, packs: int, count_per_pack: int) -> dict:
    pack_reports = []
    for pack_index in range(packs):
        slot_prefix = f"{library_prefix}-pack{pack_index:03d}"
        # count clamping to [MIN_COUNT, MAX_COUNT] happens inside
        # generate_higgsfield_photo_dump_pack() itself, via build_report() --
        # not reimplemented here.
        pack_report = build_report(date_str, slot_prefix, count_per_pack)
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

    return {
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
        "pack_reports": pack_reports,
    }


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
    print()

    print("aggregate validation counts (N/N across entire library):")
    for key, label in VALIDATION_LABELS.items():
        count, total = library["aggregate_validation_counts"][key]
        print(f"  {label:<58}: {count}/{total}")
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
                    f"silhouette={image['wardrobe_silhouette_class']!r}"
                )
                print(image["image_prompt"])
                print()

    print("=== RESULT: no subprocess call, no network call, no Higgsfield CLI/SDK use, "
          "no Kling executor import/call, no file written. Dry-run only. ===")


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
    args = parser.parse_args()

    if args.packs < 1:
        print("[ABORT] --packs must be at least 1")
        return 1

    library = build_library_report(args.date, args.library_prefix, args.packs, args.count_per_pack)
    print_library_report(library, show_prompts=args.show_prompts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
