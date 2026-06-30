"""
Lena Content Packet Batch Builder -- Dry Run v1

Runs the single-packet dry-run builder across multiple recipes.
Enforces no repeated hook IDs within a batch.
Writes a manifest JSON for review.

Safe: no API calls, no image generation, no video generation,
no R2, no Instagram, no Facebook, no queue modification,
no publishing, no scheduling, no staging or committing.
No recipe bank modified. No hook bank modified.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from lena_build_content_packet_dryrun_v1 import (
    compute_proof_prompt_budget,
    load_json,
    select_recipe,
    select_environment_entry_for_recipe,
    select_wardrobe_entry,
    build_packet,
    validate_packet,
    save_packet,
    WARDROBE_CATALOG,
    ENV_CATALOG,
    RECIPE_BANK,
    HOOK_BANK,
    OUTPUT_BASE,
)

MANIFEST_PREFIX = "lena_content_packet_batch_manifest_dryrun_"


def all_recipe_ids(recipe_bank):
    return [r["id"] for r in recipe_bank["recipes"]]


def default_recipe_ids(recipe_bank):
    active_recipes = [
        r for r in recipe_bank["recipes"]
        if r.get("production_status") != "test_only"
    ]
    missing = [
        r["id"] for r in active_recipes
        if r.get("proof_priority") is None
    ]
    if missing:
        raise ValueError(
            "Active recipes missing proof_priority: "
            + ", ".join(sorted(missing))
        )

    ordered = sorted(
        active_recipes,
        key=lambda r: (r["proof_priority"], r["id"]),
    )
    return [r["id"] for r in ordered]


def select_hook_no_repeat(hook_bank, linked_cats, used_hook_ids):
    """
    Iterate linked_hook_categories in order.
    Within each category, try hooks sorted by score desc.
    Return first hook whose ID is not in used_hook_ids.
    """
    for cat in linked_cats:
        candidates = [
            h for h in hook_bank["hooks"]
            if h.get("category") == cat
        ]
        candidates.sort(
            key=lambda h: h.get("scores", {}).get("total_score", 0),
            reverse=True,
        )
        for hook in candidates:
            if hook["id"] not in used_hook_ids:
                score = hook["scores"]["total_score"]
                reason = (
                    f"highest available total_score ({score}) "
                    f"in linked category '{cat}' "
                    f"(no-repeat constraint applied)"
                )
                return hook, cat, reason
    return None, None, None


def build_manifest(
    batch_id,
    run_date,
    total_requested,
    entries,
    used_hook_ids,
):
    total_generated = len(entries)
    total_passed = sum(1 for e in entries if e["validation_passed"])
    total_failed = total_generated - total_passed
    return {
        "batch_id": batch_id,
        "generated_date": run_date,
        "generator": "lena_build_content_batch_dryrun_v1",
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "publishing_approval": "not_approved",
        "total_requested": total_requested,
        "total_generated": total_generated,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "used_hook_ids": list(used_hook_ids),
        "packets": entries,
    }


def compute_recipe_prompt_budget(recipe, wardrobe_catalog, env_catalog):
    outfit_id = recipe.get("wardrobe_outfit_id")
    env_id = recipe.get("environment_id")
    if not outfit_id:
        return None

    wardrobe_entry = select_wardrobe_entry(
        wardrobe_catalog,
        outfit_id,
        recipe.get("wardrobe_allow_high_risk", False),
        blocked_terms=recipe.get("wardrobe_blocked_terms", []),
    )
    env_entry = None
    if env_id:
        env_entry = select_environment_entry_for_recipe(
            env_catalog,
            env_id,
            recipe,
        )
    return compute_proof_prompt_budget(
        wardrobe_entry=wardrobe_entry,
        env_entry=env_entry,
    )


def save_manifest(manifest, run_date):
    out_dir = os.path.join(OUTPUT_BASE, run_date)
    os.makedirs(out_dir, exist_ok=True)
    fname = f"{MANIFEST_PREFIX}{run_date}.json"
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)
    return fpath


def print_table(rows):
    col_w = {
        "recipe_id": 9,
        "scene_type": 28,
        "hook_id": 8,
        "score": 5,
        "chars": 5,
        "val": 4,
        "file": 52,
    }
    header = (
        f"{'recipe_id':<{col_w['recipe_id']}}  "
        f"{'scene_type':<{col_w['scene_type']}}  "
        f"{'hook_id':<{col_w['hook_id']}}  "
        f"{'score':<{col_w['score']}}  "
        f"{'chars':<{col_w['chars']}}  "
        f"{'val':<{col_w['val']}}  "
        f"file"
    )
    sep = "-" * len(header)
    print()
    print(sep)
    print(header)
    print(sep)
    for r in rows:
        val_str = "PASS" if r["validation_passed"] else "FAIL"
        fname = os.path.basename(r["output_path"])
        print(
            f"{r['recipe_id']:<{col_w['recipe_id']}}  "
            f"{r['scene_type']:<{col_w['scene_type']}}  "
            f"{r['strong_hook_id']:<{col_w['hook_id']}}  "
            f"{r['hook_total_score']:<{col_w['score']}}  "
            f"{r['compact_kling_prompt_chars']:<{col_w['chars']}}  "
            f"{val_str:<{col_w['val']}}  "
            f"{fname}"
        )
    print(sep)


def main():
    parser = argparse.ArgumentParser(
        description="Lena Content Packet Batch Builder v1 -- dry run"
    )
    parser.add_argument(
        "--recipes",
        default=None,
        help=(
            "Comma-separated recipe IDs (e.g. hcr_001,hcr_002). "
            "Defaults to active recipes ordered by proof_priority."
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Override date (YYYY-MM-DD). Defaults to today UTC.",
    )
    args = parser.parse_args()

    run_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    batch_id = f"batch_{run_date.replace('-', '')}_dryrun"

    print(f"[lena_build_content_batch_dryrun_v1] date    : {run_date}")
    print(f"[lena_build_content_batch_dryrun_v1] batch   : {batch_id}")

    recipe_bank = load_json(RECIPE_BANK)
    hook_bank = load_json(HOOK_BANK)
    wardrobe_catalog = load_json(WARDROBE_CATALOG)
    env_catalog = load_json(ENV_CATALOG)

    if args.recipes:
        recipe_ids = [r.strip() for r in args.recipes.split(",") if r.strip()]
    else:
        recipe_ids = default_recipe_ids(recipe_bank)

    total_requested = len(recipe_ids)
    print(
        f"[lena_build_content_batch_dryrun_v1] "
        f"recipes : {total_requested}"
    )

    used_hook_ids = set()
    entries = []
    rows = []

    for recipe_id in recipe_ids:
        recipe = select_recipe(recipe_bank, recipe_id)

        if (
            recipe.get("production_status") == "test_only"
            and args.recipes is None
        ):
            print(
                f"[SKIP] {recipe_id}: production_status=test_only"
                f" -- excluded from default batch"
                f" (use --recipes {recipe_id} to force)"
            )
            continue

        linked_cats = recipe.get("linked_hook_categories", [])

        hook, cat_used, reason = select_hook_no_repeat(
            hook_bank, linked_cats, used_hook_ids
        )

        if hook is None:
            print(
                f"[WARN] {recipe_id}: no unused hook available "
                f"in categories {linked_cats} -- skipping"
            )
            continue

        prompt_budget = compute_recipe_prompt_budget(
            recipe,
            wardrobe_catalog,
            env_catalog,
        )
        packet = build_packet(
            recipe,
            hook,
            reason,
            run_date,
            prompt_budget=prompt_budget,
        )
        filepath = save_packet(packet, run_date, recipe_id)
        flags, errors = validate_packet(packet, filepath)
        packet["safety_flags"] = flags

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(packet, f, indent=2, ensure_ascii=True)

        used_hook_ids.add(hook["id"])
        passed = flags["all_checks_passed"]

        entry = {
            "packet_id": packet["packet_id"],
            "recipe_id": recipe_id,
            "scene_type": recipe["scene_type"],
            "hook_category": cat_used,
            "strong_hook_id": hook["id"],
            "hook_text": hook.get("hook_text", ""),
            "hook_total_score": hook["scores"]["total_score"],
            "output_path": filepath,
            "compact_kling_prompt_chars": packet["compact_kling_prompt_chars"],
            "validation_passed": passed,
            "validation_errors": errors,
        }
        entries.append(entry)
        rows.append(entry)

    manifest = build_manifest(
        batch_id, run_date, total_requested, entries, used_hook_ids
    )
    manifest_path = save_manifest(manifest, run_date)

    print_table(rows)

    total_passed = manifest["total_passed"]
    total_failed = manifest["total_failed"]
    total_generated = manifest["total_generated"]

    print()
    print("BATCH SUMMARY")
    print(f"  batch_id        : {batch_id}")
    print(f"  total requested : {total_requested}")
    print(f"  total generated : {total_generated}")
    print(f"  total passed    : {total_passed}")
    print(f"  total failed    : {total_failed}")
    print(f"  used_hook_ids   : {sorted(used_hook_ids)}")
    repeated = [
        h for h in used_hook_ids
        if sum(1 for e in entries if e["strong_hook_id"] == h) > 1
    ]
    print(f"  repeated hooks  : {repeated if repeated else 'none'}")
    print(f"  manifest        : {manifest_path}")
    print()
    print("SAFETY")
    print("  NO API calls made.       NO image generated.")
    print("  NO video generated.      NO R2 upload.")
    print("  NO queue modified.       NO Instagram/Facebook touched.")
    print("  NO publishing.           NO scheduling.")
    print("  NO recipe bank modified. NO hook bank modified.")
    print()

    if total_failed > 0:
        print(f"[ERROR] {total_failed} packet(s) failed validation.")
        sys.exit(1)

    print(f"[OK] All {total_generated} packets passed validation.")


if __name__ == "__main__":
    main()
