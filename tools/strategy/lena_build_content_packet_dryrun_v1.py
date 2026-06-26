"""
Lena Content Packet Builder -- Dry Run v1

Reads the high-caliber recipe bank and strong hook bank.
Selects one recipe + one hook. Builds a dry-run content packet.
Writes to pipeline/strategy/lena/content_packets/{date}/.

Safe: no API calls, no image generation, no video generation,
no R2, no Instagram, no Facebook, no queue modification,
no publishing, no scheduling, no staging or committing.
No recipe bank modified. No hook bank modified.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RECIPE_BANK = os.path.join(
    ROOT, "pipeline", "prompt_banks", "lena",
    "lena_high_caliber_prompt_recipe_bank_v1.json"
)
HOOK_BANK = os.path.join(
    ROOT, "pipeline", "prompt_banks", "lena",
    "strong_hook_bank_v1.json"
)
OUTPUT_BASE = os.path.join(
    ROOT, "pipeline", "strategy", "lena", "content_packets"
)

LENA_IDENTITY_BRIEF = (
    "Lena (Magdalena Delapi): luxury lifestyle and fit-check influencer, "
    "soft-glam aesthetic, real candid energy -- not a brand shoot. "
    "Natural skin texture, visible pores, realistic detail. "
    "Identity is fixed: preserve Lena's approved adult athletic-curvy "
    "hourglass body: fuller bust, defined waist without shrinking her frame, "
    "visibly wider hips, fuller thighs, soft realistic hip curve, "
    "and balanced curvy proportions. "
    "Do not reinterpret her as a different person. "
    "Do not slim her down, make her petite, narrow-hipped, "
    "thin-legged, runway-model, or waif-like. "
    "Wardrobe must fit over her existing curvy proportions "
    "and must not reshape her into a thinner body. "
    "Outfit, setting, pose, lighting, and action may change; "
    "face and body proportions may not. "
)

AI_TERMS = re.compile(
    r"\b(ai|bot|virtual|synthetic|fake|generated|prompt|algorithm|"
    r"chatgpt|claude|kling|chatbot|tool|llm)\b",
    re.I
)
NSFW_TERMS = re.compile(
    r"\b(escort|porn|nude|nsfw|fetish|adult service|onlyfans|"
    r"sex worker)\b",
    re.I
)
VALID_PLATFORMS = {
    "Facebook Feed", "Facebook Reels",
    "Instagram Feed", "Instagram Reels"
}
PUBLIC_FIELDS = [
    "hook_text",
    "caption_draft",
    "caption_followup",
    "optional_reels_opening_line",
    "suggested_comment_reply_angle",
]


def load_json(path):
    if not os.path.isfile(path):
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def select_recipe(bank, recipe_id):
    match = next((r for r in bank["recipes"] if r["id"] == recipe_id), None)
    if not match:
        available = [r["id"] for r in bank["recipes"]]
        print(f"[ERROR] Recipe '{recipe_id}' not found.")
        print(f"        Available: {available}")
        sys.exit(1)
    return match


def select_hook(hook_bank, linked_cats, hook_category):
    if hook_category:
        if hook_category not in linked_cats:
            print(
                f"[ERROR] --hook-category '{hook_category}' is not in "
                f"recipe's linked_hook_categories: {linked_cats}"
            )
            sys.exit(1)
        search_cats = [hook_category]
    else:
        search_cats = linked_cats

    candidates = [
        h for h in hook_bank["hooks"]
        if h.get("category") in search_cats
    ]
    if not candidates:
        print(f"[ERROR] No hooks found for categories: {search_cats}")
        sys.exit(1)

    candidates.sort(
        key=lambda h: h.get("scores", {}).get("total_score", 0),
        reverse=True
    )
    hook = candidates[0]
    cat_used = hook.get("category")
    score = hook["scores"]["total_score"]
    label = "requested" if hook_category else "linked"
    reason = (
        f"highest total_score ({score}) in {label} "
        f"category '{cat_used}'"
    )
    return hook, reason


def build_compact_kling_prompt(recipe):
    scene_label = recipe["scene_type"].replace("_", " ")
    pillar_label = recipe["content_pillar"].replace("_", " ")
    scene_prefix = (
        f"Scene: {scene_label}. Pillar: {pillar_label}. "
    )
    kling_notes = (
        recipe.get("provider_rendering_notes", {}).get("kling_omni", "")
    )
    prompt = LENA_IDENTITY_BRIEF + scene_prefix + kling_notes
    return prompt[:2499]


def derive_cta(recipe):
    bct = recipe.get("best_content_type", "")
    platforms = recipe.get("platform_fit", [])
    reels_count = sum(1 for p in platforms if "Reels" in p)
    feed_count = sum(1 for p in platforms if "Feed" in p)

    if "photo" in bct and "reel" not in bct:
        cta_type = "save"
        rationale = (
            "Photo on feed platforms -- save drives re-engagement "
            "over share at this pillar"
        )
    elif "reel" in bct and feed_count == 0:
        cta_type = "watch_to_end"
        rationale = (
            "Reels-only -- completion rate and replay signal "
            "feed distribution"
        )
    else:
        cta_type = "save"
        rationale = (
            "Photo+reel on mixed feed/Reels -- save is the primary "
            "metric for fit-check and editorial content"
        )
    return {"type": cta_type, "rationale": rationale}


def derive_metrics_hypothesis(recipe):
    cats = recipe.get("linked_hook_categories", [])
    vhr = recipe.get("visual_hook_reason", "")

    comment_bait_cats = {
        "mirror_fitcheck", "outfit_problem",
        "should_i_post_this", "playful_confession"
    }
    reach_cats = {"errand_attention", "casual_but_not", "gym_confidence"}

    if cats and any(c in comment_bait_cats for c in cats):
        primary = "saves"
        engagement = "comment_bait"
        mechanism = (
            "self-aware hook drives outfit-question and 'same' comments; "
            "fitcheck content saves well on feed"
        )
    elif cats and any(c in reach_cats for c in cats):
        primary = "reach"
        engagement = "relatable_scroll_stop"
        mechanism = (
            "errand/gym/casual energy is high-relatability -- "
            "reach over saves; candid framing reduces skip rate"
        )
    else:
        primary = "saves"
        engagement = "aspirational_reference"
        mechanism = vhr[:120] if vhr else "visual hook drives save intent"

    return {
        "primary_metric": primary,
        "expected_engagement_type": engagement,
        "scroll_stop_mechanism": mechanism,
        "platform_notes": (
            "Instagram Feed best performer for this hook category "
            "at top score tier; Facebook Feed secondary"
        ),
    }


def build_packet(recipe, hook, hook_reason, run_date):
    recipe_id = recipe["id"]
    packet_id = f"cpkt_{run_date.replace('-', '')}_{recipe_id}"
    kling_prompt = build_compact_kling_prompt(recipe)

    return {
        "packet_id": packet_id,
        "generated_date": run_date,
        "generator": "lena_build_content_packet_dryrun_v1",
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "publishing_approval": "not_approved",
        "recipe_id": recipe_id,
        "scene_type": recipe["scene_type"],
        "wardrobe_outfit_id": recipe.get("wardrobe_outfit_id"),
        "wardrobe_allow_high_risk": recipe.get("wardrobe_allow_high_risk", False),
        "wardrobe_notes": recipe.get("wardrobe_notes", ""),
        "content_pillar": recipe["content_pillar"],
        "platform_targets": recipe["platform_fit"],
        "best_content_type": recipe["best_content_type"],
        "visual_hook_reason": recipe.get("visual_hook_reason", ""),
        "high_caliber_source_sections": {
            "human_reason": recipe.get("human_reason", ""),
            "style_lighting": recipe.get("style_lighting", ""),
            "subject_pose": recipe.get("subject_pose", ""),
            "fashion_accessories": recipe.get("fashion_accessories", ""),
            "setting_background": recipe.get("setting_background", ""),
            "technical_keywords": recipe.get("technical_keywords", ""),
            "negative_constraints": recipe.get("negative_constraints", ""),
        },
        "compact_kling_prompt_preview": kling_prompt,
        "compact_kling_prompt_chars": len(kling_prompt),
        "strong_hook_id": hook["id"],
        "strong_hook_category": hook["category"],
        "hook_text": hook.get("hook_text", ""),
        "hook_total_score": hook["scores"]["total_score"],
        "hook_selection_reason": hook_reason,
        "caption_draft": recipe.get("caption_draft", ""),
        "caption_followup": hook.get("caption_followup", ""),
        "optional_reels_opening_line": hook.get(
            "optional_reels_opening_line", ""
        ),
        "suggested_comment_reply_angle": hook.get(
            "suggested_comment_reply_angle", ""
        ),
        "cta_recommendation": derive_cta(recipe),
        "metrics_hypothesis": derive_metrics_hypothesis(recipe),
        "safety_flags": {},
    }


def validate_packet(packet, output_path):
    errors = []
    flags = {}

    flags["dry_run_true"] = packet.get("dry_run") is True
    if not flags["dry_run_true"]:
        errors.append("dry_run must be true")

    flags["provider_call_enabled_false"] = (
        packet.get("provider_call_enabled") is False
    )
    if not flags["provider_call_enabled_false"]:
        errors.append("provider_call_enabled must be false")

    flags["recipe_exists"] = bool(packet.get("recipe_id"))

    flags["hook_category_linked"] = True  # enforced at selection

    bad_plat = [
        p for p in packet.get("platform_targets", [])
        if p not in VALID_PLATFORMS
    ]
    flags["platforms_valid"] = len(bad_plat) == 0
    if bad_plat:
        errors.append(f"invalid platforms: {bad_plat}")

    ai_hits = [
        f for f in PUBLIC_FIELDS
        if packet.get(f) and AI_TERMS.search(str(packet[f]))
    ]
    flags["no_ai_terms_in_public"] = len(ai_hits) == 0
    if ai_hits:
        errors.append(f"ai/banned terms in public fields: {ai_hits}")

    nsfw_hits = [
        f for f in PUBLIC_FIELDS
        if packet.get(f) and NSFW_TERMS.search(str(packet[f]))
    ]
    flags["no_nsfw_in_public"] = len(nsfw_hits) == 0
    if nsfw_hits:
        errors.append(f"nsfw terms in public fields: {nsfw_hits}")

    kling_len = packet.get("compact_kling_prompt_chars", 9999)
    flags["kling_prompt_under_2500"] = kling_len < 2500
    if kling_len >= 2500:
        errors.append(f"kling prompt too long: {kling_len} chars")

    norm = os.path.normpath(output_path)
    norm_base = os.path.normpath(OUTPUT_BASE)
    flags["output_path_valid"] = norm.startswith(norm_base)
    if not flags["output_path_valid"]:
        errors.append(f"output path not under content_packets/: {output_path}")

    flags["all_checks_passed"] = len(errors) == 0
    return flags, errors


def save_packet(packet, run_date, recipe_id):
    out_dir = os.path.join(OUTPUT_BASE, run_date)
    os.makedirs(out_dir, exist_ok=True)
    fname = f"lena_content_packet_dryrun_{run_date}_{recipe_id}.json"
    filepath = os.path.join(out_dir, fname)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(packet, f, indent=2, ensure_ascii=True)
    return filepath


def print_summary(packet, filepath, flags, errors):
    ok = "PASSED" if flags.get("all_checks_passed") else "FAILED"
    print()
    print("=" * 64)
    print("  LENA CONTENT PACKET BUILDER v1 -- DRY RUN COMPLETE")
    print("=" * 64)
    print(f"  Output path          : {filepath}")
    print(f"  packet_id            : {packet['packet_id']}")
    print(f"  recipe_id            : {packet['recipe_id']}")
    print(f"  scene_type           : {packet['scene_type']}")
    print(f"  content_pillar       : {packet['content_pillar']}")
    print(f"  platform_targets     : {packet['platform_targets']}")
    print(f"  best_content_type    : {packet['best_content_type']}")
    print()
    print(f"  Hook selected        : {packet['strong_hook_id']} "
          f"({packet['strong_hook_category']})")
    print(f"  Hook text            : {packet['hook_text']}")
    print(f"  Hook total_score     : {packet['hook_total_score']}")
    print(f"  Hook selection       : {packet['hook_selection_reason']}")
    print()
    print(f"  Caption draft        : {packet['caption_draft']}")
    print(f"  Caption followup     : {packet['caption_followup']}")
    print(f"  Reels opening line   : {packet['optional_reels_opening_line']}")
    print(f"  Reply angle          : {packet['suggested_comment_reply_angle']}")
    print(f"  CTA type             : {packet['cta_recommendation']['type']}")
    print(f"  Primary metric       : "
          f"{packet['metrics_hypothesis']['primary_metric']}")
    print()
    print(f"  Kling prompt chars   : {packet['compact_kling_prompt_chars']}")
    print(f"  Kling under 2500     : "
          f"{flags.get('kling_prompt_under_2500')}")
    print()
    print("  VALIDATION FLAGS:")
    for k, v in flags.items():
        mark = "OK  " if v else "FAIL"
        print(f"    [{mark}] {k}")
    print()
    if errors:
        print("  VALIDATION ERRORS:")
        for e in errors:
            print(f"    {e}")
    else:
        print(f"  VALIDATION: {ok} -- all checks clean")
    print()
    print("  NO API calls made.       NO image generated.")
    print("  NO video generated.      NO R2 upload.")
    print("  NO queue modified.       NO Instagram/Facebook touched.")
    print("  NO publishing.           NO scheduling.")
    print("  NO recipe bank modified. NO hook bank modified.")
    print("=" * 64)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Lena Content Packet Builder v1 -- dry run"
    )
    parser.add_argument(
        "--recipe", required=True,
        help="Recipe ID from recipe bank (e.g. hcr_001)"
    )
    parser.add_argument(
        "--hook-category", default=None,
        help=(
            "Hook category to prefer "
            "(must be in recipe's linked_hook_categories)"
        )
    )
    parser.add_argument(
        "--date", default=None,
        help="Override date (YYYY-MM-DD). Defaults to today UTC."
    )
    args = parser.parse_args()

    run_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(
        f"[lena_build_content_packet_dryrun_v1] "
        f"date   : {run_date}"
    )
    print(
        f"[lena_build_content_packet_dryrun_v1] "
        f"recipe : {args.recipe}"
    )
    if args.hook_category:
        print(
            f"[lena_build_content_packet_dryrun_v1] "
            f"hook-category : {args.hook_category}"
        )

    print("[lena_build_content_packet_dryrun_v1] Loading recipe bank...")
    recipe_bank = load_json(RECIPE_BANK)

    print("[lena_build_content_packet_dryrun_v1] Loading hook bank...")
    hook_bank = load_json(HOOK_BANK)

    recipe = select_recipe(recipe_bank, args.recipe)
    linked_cats = recipe.get("linked_hook_categories", [])
    print(
        f"[lena_build_content_packet_dryrun_v1] "
        f"Recipe: {recipe['scene_type']}"
    )
    print(
        f"[lena_build_content_packet_dryrun_v1] "
        f"Linked categories: {linked_cats}"
    )

    hook, hook_reason = select_hook(
        hook_bank, linked_cats, args.hook_category
    )
    print(
        f"[lena_build_content_packet_dryrun_v1] "
        f"Hook: {hook['id']} (score {hook['scores']['total_score']})"
    )

    print("[lena_build_content_packet_dryrun_v1] Building packet...")
    packet = build_packet(recipe, hook, hook_reason, run_date)

    print("[lena_build_content_packet_dryrun_v1] Saving...")
    filepath = save_packet(packet, run_date, args.recipe)

    print("[lena_build_content_packet_dryrun_v1] Validating...")
    flags, errors = validate_packet(packet, filepath)
    packet["safety_flags"] = flags

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(packet, f, indent=2, ensure_ascii=True)

    with open(filepath, encoding="utf-8") as f:
        json.load(f)  # confirm re-parses after safety_flags injected

    print_summary(packet, filepath, flags, errors)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
