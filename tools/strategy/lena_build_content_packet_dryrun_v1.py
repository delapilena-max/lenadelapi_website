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
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from pipeline.prompting.lena_prompt_brain import (
    format_catalog_wardrobe_override,
    max_production_style_override_len,
)

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
WARDROBE_CATALOG = os.path.join(
    ROOT, "pipeline", "prompt_banks", "lena",
    "lena_wardrobe_catalog_v1.json"
)
ENV_CATALOG = os.path.join(
    ROOT, "pipeline", "prompt_banks", "lena",
    "lena_environment_catalog_v1.json"
)

LENA_IDENTITY_BRIEF = (
    "Lena (Magdalena Delapi): luxury lifestyle and fit-check influencer, "
    "soft-glam aesthetic, real candid energy -- not a brand shoot. "
    "Natural skin texture, visible pores, realistic detail. "
    "Hair must stay identity-consistent across generations: reference-true warm medium-brown base "
    "with clearly visible honey/caramel highlights and lighter face-framing pieces as seen in the approved reference photos. "
    "Hair should read dimensional, softly sunlit, and warm -- not flat dark brunette, not one-tone brown, not black-brown, "
    "not platinum or fully blonde, and not copper/auburn reinterpretation. "
    "Identity is fixed: preserve Lena's approved adult slim-thick "
    "hourglass body: full natural lifted bust with clear upper fullness consistent with the approved references, "
    "small defined waist without shrinking her frame, "
    "visibly wide hips, toned upper thighs, soft realistic hip curve, consistent "
    "slightly wide pelvis breadth, a slightly wider-set hip span from the front and 3/4 view, "
    "a touch more lateral hip breadth, and a slightly fuller outer-thigh and upper-glute read, "
    "and balanced curvy proportions. "
    "Do not reinterpret her as a different person. "
    "Do not slim her down, make her petite, narrow-hipped, "
    "thin-legged, straight-hipped, runway-model, or waif-like. "
    "Do not narrow her pelvis, collapse her hip width, pull her hip points inward, or taper her lower "
    "body into a slimmer silhouette in side angles or standing poses. "
    "A slight natural inner-thigh separation is acceptable in neutral standing poses "
    "when the stance supports it, but never as an anatomical distortion. "
    "Do not flatten, minimize, or reduce her bust into a smaller-chested fashion-model read. "
    "Do not over-thicken her hips, thighs, or torso beyond her approved "
    "reference proportions either. Keep her body attractive, toned, curvy, "
    "and realistic -- never shrunken, never exaggerated, never bulky. "
    "Wardrobe must fit over her existing curvy proportions "
    "and must not reshape her into a thinner body. "
    "Outfit, setting, pose, lighting, and action may change; "
    "face and body proportions may not. "
)

PROOF_MODE_IDENTITY_BRIEF = (
    "Lena (Magdalena Delapi): luxury lifestyle and fit-check influencer, "
    "soft-glam aesthetic, real candid energy -- not a brand shoot. "
    "Hair must stay identity-consistent across generations: reference-true warm medium-brown base "
    "with clearly visible honey/caramel highlights and lighter face-framing pieces as seen in the approved reference photos. "
    "Hair should read dimensional, softly sunlit, and warm -- not flat dark brunette, not one-tone brown, not black-brown, "
    "not platinum or fully blonde, and not copper/auburn reinterpretation. "
    "Identity is fixed: preserve Lena's approved adult slim-thick hourglass body "
    "and approved reference face exactly consistently: full natural lifted bust with visible upper fullness, small "
    "defined waist without shrinking her frame, visibly wide hips, toned upper thighs, "
    "balanced curvy proportions, and realistic limbs and hands. "
    "Do not reinterpret her as a different person. Do not slim her down into petite, "
    "narrow-hipped, thin-legged, runway-model proportions, and do not exaggerate her "
    "lower body into cartoon curves. Do not flatten, minimize, or reduce her bust into a smaller-chested read. "
    "Outfit, setting, pose, lighting, and action may change; "
    "face and body proportions may not. "
)

FACE_LIGHT_REALISM_PRIORITY = (
    "Face must read naturally lit, not cosmetically lit: imperfect cheek-to-jaw shadow falloff, "
    "slight under-eye shadow retention, subtle forehead tone variation, and non-uniform skin sheen. "
    "No evenly front-lit beauty-mask face. "
)

FACE_PRIORITY_FRAMING = (
    "Face-priority framing only: waist-up or chest-up mirror save, never full-body mirror pose, "
    "never full legs, and never the full dress hemline in frame. "
)

HPE_SUBJECT_PRESENCE_COMPACT = (
    "Camera-aware, self-possessed, quietly sensual; gaze, expression, posture, object interaction, "
    "viewer relationship, and framing read as a private getting-ready moment."
)

DRESS_CONTINUITY_PRIORITY = (
    "If the intended look is a dress, keep it as one continuous dress with no exposed midriff "
    "and never split it into a separate top and skirt. "
)

SKIN_REALISM_COMPACT = (
    "Unretouched phone-camera skin: visible pores on cheeks, nose, and forehead, "
    "fine facial texture, faint under-eye/lower-lid lines, slight redness, tiny tone unevenness, "
    "tiny forehead texture, soft natural under-eye darkness, small natural nose shine, "
    "real skin oil balance, normal asymmetry, and clear natural complexion. "
    "No skin blur, no denoised skin, no softened pore detail. Micro details: peach-fuzz edge light, "
    "individual brow hairs, real lashes with tiny shadows, imperfect lip texture, "
    "a slight crease at mouth corners, faint smile-line softness, normal eyelid fold depth, "
    "subtle tear-trough transition, natural philtrum and lip-edge definition, "
    "stray hair strands, uneven catchlights, room-shadow falloff on skin. "
    "Face detail comes from the Lena character element; keep the facial surface faithful to the approved references. "
    "No fake freckles, no new non-reference freckle clusters, no moved or multiplied beauty marks. "
    "No decorative beauty-filter surface pattern, "
    "no beauty-filter speckling, no beauty filter, no CGI face, "
    "not airbrushed, not poreless, not plastic or glossy. "
    "No polished beauty-campaign finish, no commercial skin retouch look, no foundation-ad finish. "
    "No baby-face stylization, no oversized irises, no porcelain doll facial finish, "
    "and no smoothed influencer-face retouch geometry. "
)

HAND_REALISM_COMPACT = (
    "Hands must look human and relaxed: five fingers on each hand, "
    "natural finger length, clean thumb placement, visible knuckle structure, "
    "real nail scale, relaxed wrist angles, no fused fingers, no melted hand overlap, "
    "no twisted wrists, no mannequin hands. Prefer one simple candid hand action only; "
    "avoid clasped hands or complex interlocked fingers. "
)

STRUCTURED_SUBJECT_BRIEF = (
    "Lena (Magdalena Delapi). Identity is fixed: preserve her approved adult "
    "slim-thick hourglass body and face. Do not reinterpret her as a different "
    "person. Do not slim her into petite, narrow-hipped proportions. Keep full "
    "natural lifted bust, defined waist, and wide hips. Hair stays reference-true "
    "warm medium-brown with visible honey/caramel highlights and lighter face-framing pieces."
)

STRUCTURED_TECHNICAL_REALISM = (
    "Photorealistic high-resolution image with visible pores, fine facial texture, "
    "natural under-eye retention, imperfect lip texture, tiny tone variation, "
    "stray hair strands, realistic catchlights, and scene-true shadow falloff. "
    "Face detail comes from the Lena character element; keep the facial surface faithful to the approved references. "
    "Hands remain anatomically correct with five fingers, believable knuckles, "
    "clean thumb placement, and relaxed wrists. Avoid plastic skin, beauty-filter "
    "poreless retouching, deformed hands, identity drift, body-slimming drift, "
    "or environment/wardrobe contradictions."
)

STRUCTURED_SECTION_MAX = {
    "[Subject]": 540,
    "[Action]": 330,
    "[Environment]": 360,
    "[Cinematography]": 230,
    "[Lighting/Style]": 300,
    "[Technical]": 500,
}

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
HASHTAG_TERMS = re.compile(r"#[A-Za-z0-9_]+")
VALID_PLATFORMS = {
    "Facebook Feed", "Facebook Reels",
    "Instagram Feed", "Instagram Reels"
}
REPORT_TYPE = "lena_content_packet_dryrun"
SCHEMA_VERSION = "v1"
PUBLIC_FIELDS = [
    "hook_text",
    "caption_draft",
    "caption_followup",
    "optional_reels_opening_line",
    "suggested_comment_reply_angle",
]
PACKET_BLOCKED_TERMS = (
    "goodtest1",
    "element_list",
    "/v1/images/generations",
    ".env.txt",
)
MASTER_IDENTITY_CHECKS = (
    "identity is fixed",
    "do not slim",
    "petite",
    "hourglass",
    "do not reinterpret",
    "full natural lifted bust",
    "slim-thick",
    "narrow-hipped",
    "defined waist",
    "wide hips",
)


def load_json(path):
    if not os.path.isfile(path):
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fit_prompt_sentences(parts, max_chars):
    chosen = []
    current = ""
    for raw_part in parts:
        part = (raw_part or "").strip()
        if not part:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", part)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = (
                f"{current} {sentence}".strip()
                if current else sentence
            )
            if len(candidate) <= max_chars:
                chosen.append(sentence)
                current = candidate
    return current


def fit_prompt_units(text, max_chars):
    text = clean_fragment(text)
    if not text:
        return ""

    current = ""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            break

        clause_current = ""
        clauses = [
            clause.strip()
            for clause in re.split(r"(?<=,)\s+|(?<=;)\s+", sentence)
            if clause.strip()
        ]
        for clause in clauses:
            clause_candidate = (
                f"{clause_current} {clause}".strip()
                if clause_current else clause
            )
            if len(clause_candidate) <= max_chars:
                clause_current = clause_candidate
                continue
            break
        current = clause_current
        break
    return current


def clean_fragment(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def trim_fragment_to_chars(text, max_chars):
    text = clean_fragment(text)
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].rstrip(",;: ")
    return clipped or text[:max_chars].rstrip(",;: ")


def check_master_identity(prompt: str) -> bool:
    prompt_lower = (prompt or "").lower()
    return all(marker in prompt_lower for marker in MASTER_IDENTITY_CHECKS)


def check_packet_blocked_terms(prompt: str) -> list[str]:
    prompt_lower = (prompt or "").lower()
    return [term for term in PACKET_BLOCKED_TERMS if term in prompt_lower]


def build_hpe_subject_presence(recipe) -> str:
    if not recipe.get("production_proof_mode", False):
        return ""
    return HPE_SUBJECT_PRESENCE_COMPACT


def build_structured_prompt_sections(recipe):
    subject_parts = [STRUCTURED_SUBJECT_BRIEF]
    fashion = clean_fragment(recipe.get("fashion_accessories", ""))
    if fashion:
        subject_parts.append(f"Wardrobe and accessories: {fashion}")
    subject = clean_fragment(" ".join(subject_parts))
    subject_presence = build_hpe_subject_presence(recipe)
    action = clean_fragment(recipe.get("subject_pose", ""))
    environment_note = recipe.get("scene_logic_contract", {}).get(
        "environment_realism_notes", ""
    )
    environment_parts = [recipe.get("setting_background", "")]
    if environment_note:
        environment_parts.append(f"Realism cues: {environment_note}")
    environment = clean_fragment(" ".join(part for part in environment_parts if part))
    cinematography = clean_fragment(recipe.get("technical_keywords", ""))
    lighting = clean_fragment(recipe.get("style_lighting", ""))
    technical_parts = [
        STRUCTURED_TECHNICAL_REALISM,
        recipe.get("negative_constraints", ""),
    ]
    technical = clean_fragment(" ".join(part for part in technical_parts if part))
    return [
        ("[Subject]", subject),
        ("[Subject Presence]", subject_presence),
        ("[Action]", action),
        ("[Environment]", environment),
        ("[Cinematography]", cinematography),
        ("[Lighting/Style]", lighting),
        ("[Technical]", technical),
    ]


def build_structured_kling_prompt(recipe, max_chars=2499):
    sections = build_structured_prompt_sections(recipe)
    built = []
    current = ""

    for label, body in sections:
        if not body:
            continue
        prefix = f"{label}: "
        remaining = max_chars - len(current) - (1 if current else 0) - len(prefix)
        if remaining <= 0:
            break
        section_cap = STRUCTURED_SECTION_MAX.get(label, remaining)
        trimmed = fit_prompt_units(body, min(remaining, section_cap))
        if not trimmed:
            trimmed = trim_fragment_to_chars(body, min(remaining, section_cap))
        if not trimmed:
            continue
        chunk = f"{prefix}{trimmed}".strip()
        candidate = f"{current} {chunk}".strip() if current else chunk
        if len(candidate) <= max_chars:
            built.append(chunk)
            current = candidate

    return " ".join(built).strip()


def compute_proof_prompt_budget(
    wardrobe_entry=None,
    env_entry=None,
    max_chars=2499,
):
    # The current dry-run packet builder tracks locked wardrobe/environment
    # bindings as deterministic inputs, but does not append the old provider-
    # specific overlay strings into the prompt preview itself.
    _ = wardrobe_entry, env_entry
    return max_chars


def compute_style_bank_prompt_budget(max_chars=2499):
    reserved = max_production_style_override_len() + 24
    budget = max_chars - reserved
    if budget < 1700:
        raise SystemExit(
            "[ABORT] style-bank reserved headroom leaves too little room "
            f"for the base Kling prompt ({budget} chars). "
            "Shorten the style-bank wardrobe override text before live use."
        )
    return budget


def select_recipe(bank, recipe_id):
    match = next((r for r in bank["recipes"] if r["id"] == recipe_id), None)
    if not match:
        available = [r["id"] for r in bank["recipes"]]
        print(f"[ERROR] Recipe '{recipe_id}' not found.")
        print(f"        Available: {available}")
        sys.exit(1)
    return match


def select_wardrobe_entry(
    catalog, outfit_id, allow_high_risk, blocked_terms=None
):
    entry = next(
        (o for o in catalog["outfits"] if o["outfit_id"] == outfit_id),
        None,
    )
    if entry is None:
        raise SystemExit(
            f"[ABORT] wardrobe outfit '{outfit_id}' not found "
            "in wardrobe catalog"
        )
    if entry["status"] == "rejected":
        raise SystemExit(
            f"[ABORT] wardrobe outfit '{outfit_id}' "
            "status=rejected -- hard blocked"
        )
    if entry["status"] == "high_risk" and not allow_high_risk:
        raise SystemExit(
            f"[ABORT] wardrobe outfit '{outfit_id}' "
            "status=high_risk but recipe wardrobe_allow_high_risk "
            "is false -- set it explicitly to allow"
        )
    lowered = " ".join(
        [
            str(entry.get("name") or ""),
            str(entry.get("prompt") or ""),
        ]
    ).lower()
    blocked_terms = [t.lower() for t in (blocked_terms or []) if t]
    blocked_hit = next((t for t in blocked_terms if t in lowered), None)
    if blocked_hit:
        raise SystemExit(
            f"[ABORT] wardrobe outfit '{outfit_id}' contains blocked "
            f"recipe term '{blocked_hit}' -- choose a different outfit for "
            "this lane"
        )
    return entry


def select_environment_entry(env_catalog, env_id, scene_type):
    entry = next(
        (e for e in env_catalog["environments"]
         if e["environment_id"] == env_id),
        None,
    )
    if entry is None:
        raise SystemExit(
            f"[ABORT] environment '{env_id}' not found "
            "in environment catalog"
        )
    if scene_type not in entry.get("allowed_recipe_types", []):
        raise SystemExit(
            f"[ABORT] environment '{env_id}' does not "
            f"permit scene_type '{scene_type}'"
        )
    return entry


def select_environment_entry_for_recipe(env_catalog, env_id, recipe):
    scene_type = recipe.get("scene_type")
    content_pillar = recipe.get("content_pillar")
    entry = next(
        (e for e in env_catalog["environments"]
         if e["environment_id"] == env_id),
        None,
    )
    if entry is None:
        raise SystemExit(
            f"[ABORT] environment '{env_id}' not found "
            "in environment catalog"
        )

    allowed = set(entry.get("allowed_recipe_types", []))
    if scene_type in allowed or content_pillar in allowed:
        return entry

    raise SystemExit(
        f"[ABORT] environment '{env_id}' does not permit "
        f"scene_type '{scene_type}' or content_pillar '{content_pillar}'"
    )


def build_safe_expansion_matrix(
    recipe,
    recipe_bank,
    wardrobe_catalog,
    env_catalog,
):
    lane_specs = recipe.get("safe_expansion_lanes", [])
    if not lane_specs:
        return []

    recipe_lookup = {
        r["id"]: r for r in recipe_bank.get("recipes", [])
    }
    matrix = []

    for spec in lane_specs:
        target_recipe = recipe_lookup.get(spec.get("recipe_id"))
        if target_recipe is None:
            raise SystemExit(
                f"[ABORT] expansion lane '{spec.get('lane_id')}' references "
                f"unknown recipe '{spec.get('recipe_id')}'"
            )

        env_options = []
        for env_id in spec.get("environment_ids", []):
            env_entry = select_environment_entry_for_recipe(
                env_catalog, env_id, target_recipe
            )
            env_options.append(
                {
                    "environment_id": env_entry["environment_id"],
                    "name": env_entry.get("name", ""),
                    "prompt_fragment": env_entry.get("prompt_fragment", ""),
                }
            )

        outfit_options = []
        for outfit_id in spec.get("outfit_ids", []):
            outfit_entry = select_wardrobe_entry(
                wardrobe_catalog,
                outfit_id,
                target_recipe.get("wardrobe_allow_high_risk", False),
                blocked_terms=target_recipe.get("wardrobe_blocked_terms", []),
            )
            outfit_options.append(
                {
                    "outfit_id": outfit_entry["outfit_id"],
                    "name": outfit_entry.get("name", ""),
                    "style_lane": outfit_entry.get("style_lane", ""),
                    "status": outfit_entry.get("status", ""),
                    "prompt": outfit_entry.get("prompt", ""),
                    "notes": outfit_entry.get("notes", ""),
                }
            )

        matrix.append(
            {
                "lane_id": spec.get("lane_id", ""),
                "priority": spec.get("priority"),
                "lane_family": spec.get("lane_family", ""),
                "lane_role": spec.get("lane_role", ""),
                "goal": spec.get("goal", ""),
                "guardrails": spec.get("guardrails", ""),
                "target_recipe": {
                    "recipe_id": target_recipe["id"],
                    "title": target_recipe.get("title", ""),
                    "scene_type": target_recipe.get("scene_type", ""),
                    "content_pillar": target_recipe.get("content_pillar", ""),
                },
                "environment_options": env_options,
                "outfit_options": outfit_options,
            }
        )

    return sorted(
        matrix,
        key=lambda lane: (
            lane.get("priority") is None,
            lane.get("priority", 999),
            lane.get("lane_id", ""),
        ),
    )


def select_hook(hook_bank, linked_cats, hook_category, hook_id=None):
    if hook_id:
        hook = next(
            (h for h in hook_bank["hooks"] if h.get("id") == hook_id),
            None,
        )
        if not hook:
            print(f"[ERROR] Hook '{hook_id}' not found.")
            sys.exit(1)
        if hook.get("category") not in linked_cats:
            print(
                f"[ERROR] --hook-id '{hook_id}' category "
                f"'{hook.get('category')}' is not in recipe's "
                f"linked_hook_categories: {linked_cats}"
            )
            sys.exit(1)
        score = hook["scores"]["total_score"]
        reason = (
            f"explicit hook_id '{hook_id}' selected "
            f"(category '{hook.get('category')}', score {score})"
        )
        return hook, reason

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


def build_compact_kling_prompt(recipe, max_chars=2499):
    structured = build_structured_kling_prompt(recipe, max_chars=max_chars)
    if structured:
        return structured

    scene_label = recipe["scene_type"].replace("_", " ")
    pillar_label = recipe["content_pillar"].replace("_", " ")
    scene_prefix = (
        f"Scene: {scene_label}. Pillar: {pillar_label}. "
    )
    kling_notes = (
        recipe.get("provider_rendering_notes", {}).get("kling_omni", "")
    )
    proof_mode = recipe.get("production_proof_mode", False)
    identity_brief = (
        PROOF_MODE_IDENTITY_BRIEF if proof_mode else LENA_IDENTITY_BRIEF
    )
    return fit_prompt_sentences(
        [
            identity_brief,
            FACE_LIGHT_REALISM_PRIORITY if proof_mode else "",
            (
                FACE_PRIORITY_FRAMING
                if recipe.get("content_pillar") == "face_priority_getting_ready"
                else ""
            ),
            build_hpe_subject_presence(recipe),
            DRESS_CONTINUITY_PRIORITY if proof_mode else "",
            SKIN_REALISM_COMPACT,
            scene_prefix,
            kling_notes,
            HAND_REALISM_COMPACT,
        ],
        max_chars=max_chars,
    )


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


def build_packet(
    recipe,
    hook,
    hook_reason,
    run_date,
    prompt_budget=None,
    expansion_matrix=None,
):
    recipe_id = recipe["id"]
    packet_id = f"cpkt_{run_date.replace('-', '')}_{recipe_id}"
    proof_mode = recipe.get("production_proof_mode", False)
    outfit_id = recipe.get("wardrobe_outfit_id")
    environment_id = recipe.get("environment_id")
    if prompt_budget is None:
        prompt_budget = 2499
        if proof_mode and outfit_id:
            prompt_budget = 1780 if environment_id else 1940
        elif not outfit_id:
            prompt_budget = compute_style_bank_prompt_budget()
    kling_prompt = build_compact_kling_prompt(
        recipe, max_chars=prompt_budget
    )
    provider_prompt_blocked_terms = check_packet_blocked_terms(kling_prompt)
    provider_prompt_contract = {
        "surface_status": "quarantined_provider_neutral_dry_run_packet",
        "provider_route": "higgsfield_forward_no_live",
        "live_authority": False,
        "prompt_chars": len(kling_prompt),
        "prompt_headroom": 2499 - len(kling_prompt),
        "scene_logic_contract_present": bool(recipe.get("scene_logic_contract", {})),
        "master_identity_body_present": check_master_identity(kling_prompt),
        "blocked_terms_absent": len(provider_prompt_blocked_terms) == 0,
        "blocked_terms_found": provider_prompt_blocked_terms,
        "outfit_controlled": bool(outfit_id),
        "environment_controlled": bool(environment_id),
    }
    provider_prompt_sha256 = hashlib.sha256(
        kling_prompt.encode("utf-8")
    ).hexdigest()

    locked_scene_context = recipe.get("scene_type", "scene_context")
    realism_iteration_plan = {
        "mode": (
            "locked_lane_skin_realism_iteration"
            if proof_mode and outfit_id and environment_id
            else "standard_dry_run_packet"
        ),
        "goal": (
            "Hold the active recipe/outfit/environment lane stable and refine only "
            "face and skin realism."
            if proof_mode and outfit_id and environment_id
            else "Build a safe dry-run packet for review."
        ),
        "locked_variables": (
            [
                "identity",
                "body proportions",
                "recipe_id",
                "scene_type",
                "wardrobe_outfit_id",
                "environment_id",
                locked_scene_context,
            ]
            if proof_mode and outfit_id and environment_id
            else []
        ),
        "allowed_refinements": (
            [
                "visible pores and fine facial texture",
                "lower-lid and under-eye realism",
                "lip texture and normal asymmetry",
                "flyaway hair strands and brow/lash separation",
                "uneven natural catchlights and room-shadow falloff",
            ]
            if proof_mode and outfit_id and environment_id
            else []
        ),
        "do_not_change_next": (
            [
                "body shape emphasis",
                "garment construction",
                "environment lane",
                "camera framing logic",
            ]
            if proof_mode and outfit_id and environment_id
            else []
        ),
    }

    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
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
        "prompt_structure_standard": "subject_action_environment_cinematography_lighting_technical_v1",
        "compact_kling_prompt_preview": kling_prompt,
        "compact_kling_prompt_chars": len(kling_prompt),
        "compact_kling_prompt_budget": prompt_budget,
        "compact_provider_prompt_preview": kling_prompt,
        "compact_provider_prompt_chars": len(kling_prompt),
        "compact_provider_prompt_budget": prompt_budget,
        "compact_provider_prompt_sha256": provider_prompt_sha256,
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
        "scene_logic_contract": recipe.get("scene_logic_contract", {}),
        "production_proof_mode": recipe.get("production_proof_mode", False),
        "environment_id": recipe.get("environment_id"),
        "environment_context": recipe.get("environment_context", ""),
        "proof_control_role": recipe.get("proof_control_role", ""),
        "safe_expansion_lanes": expansion_matrix or [],
        "realism_iteration_plan": realism_iteration_plan,
        "provider_prompt_contract": provider_prompt_contract,
        "safety_flags": {},
    }


def rebuild_packet_from_authoritative_sources(packet):
    recipe_bank = load_json(RECIPE_BANK)
    hook_bank = load_json(HOOK_BANK)
    wardrobe_catalog = load_json(WARDROBE_CATALOG)
    env_catalog = load_json(ENV_CATALOG)

    recipe = dict(select_recipe(recipe_bank, packet["recipe_id"]))
    wf_entry = None
    env_entry = None

    chosen_outfit_id = packet.get("wardrobe_outfit_id") or recipe.get("wardrobe_outfit_id")
    if chosen_outfit_id:
        wf_entry = select_wardrobe_entry(
            wardrobe_catalog,
            chosen_outfit_id,
            recipe.get("wardrobe_allow_high_risk", False),
            blocked_terms=recipe.get("wardrobe_blocked_terms", []),
        )
        recipe["wardrobe_outfit_id"] = chosen_outfit_id

    chosen_env_id = packet.get("environment_id") or recipe.get("environment_id")
    if chosen_env_id:
        env_entry = select_environment_entry_for_recipe(
            env_catalog, chosen_env_id, recipe
        )
        recipe["environment_id"] = chosen_env_id
        if packet.get("environment_context"):
            recipe["environment_context"] = packet["environment_context"]
        elif not recipe.get("environment_context"):
            recipe["environment_context"] = (
                f"Environment: {env_entry['prompt_fragment']} "
            )

    prompt_budget_override = None
    if wf_entry:
        prompt_budget_override = compute_proof_prompt_budget(
            wardrobe_entry=wf_entry,
            env_entry=env_entry,
        )

    expansion_matrix = build_safe_expansion_matrix(
        recipe,
        recipe_bank,
        wardrobe_catalog,
        env_catalog,
    )

    hook = next(
        (item for item in hook_bank["hooks"] if item.get("id") == packet["strong_hook_id"]),
        None,
    )
    if hook is None:
        raise SystemExit(
            f"[ABORT] Hook '{packet['strong_hook_id']}' not found."
        )

    return build_packet(
        recipe,
        hook,
        packet.get("hook_selection_reason", "authoritative source rebuild"),
        packet["generated_date"],
        prompt_budget=prompt_budget_override,
        expansion_matrix=expansion_matrix,
    )


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
    if not flags["recipe_exists"]:
        errors.append("recipe_id is required")

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

    hashtag_hits = [
        f for f in PUBLIC_FIELDS
        if packet.get(f) and HASHTAG_TERMS.search(str(packet[f]))
    ]
    flags["no_hashtags_in_public"] = len(hashtag_hits) == 0
    if hashtag_hits:
        errors.append(f"hashtags not allowed in public fields: {hashtag_hits}")

    provider_prompt_contract = packet.get("provider_prompt_contract", {})
    flags["provider_prompt_contract_present"] = isinstance(provider_prompt_contract, dict) and bool(provider_prompt_contract)
    if not flags["provider_prompt_contract_present"]:
        errors.append("provider_prompt_contract is required")

    flags["scene_logic_contract_present"] = bool(provider_prompt_contract.get("scene_logic_contract_present"))
    if not flags["scene_logic_contract_present"]:
        errors.append("scene_logic_contract must be present")

    flags["master_identity_body_present"] = bool(provider_prompt_contract.get("master_identity_body_present"))
    if not flags["master_identity_body_present"]:
        errors.append("master identity markers must remain present")

    flags["packet_blocked_terms_absent"] = bool(provider_prompt_contract.get("blocked_terms_absent"))
    if not flags["packet_blocked_terms_absent"]:
        errors.append(
            f"blocked packet terms present: {provider_prompt_contract.get('blocked_terms_found', [])}"
        )

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
    if packet.get("proof_control_role"):
        print(f"  Proof control role   : {packet['proof_control_role']}")
    if packet.get("safe_expansion_lanes"):
        print(f"  Expansion lanes      : {len(packet['safe_expansion_lanes'])}")
        for lane in packet["safe_expansion_lanes"]:
            print(
                "    - "
                f"{lane['lane_id']} -> "
                f"{lane['target_recipe']['recipe_id']} "
                f"({len(lane['environment_options'])} env / "
                f"{len(lane['outfit_options'])} outfits)"
            )
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
        "--hook-id", default=None,
        help=(
            "Exact hook ID from strong_hook_bank_v1.json "
            "(must belong to one of the recipe's linked_hook_categories)"
        )
    )
    parser.add_argument(
        "--date", default=None,
        help="Override date (YYYY-MM-DD). Defaults to today UTC."
    )
    parser.add_argument(
        "--outfit-id", default=None, dest="outfit_id",
        help=(
            "Production-proof outfit override (e.g. wc_p045). "
            "Rejected hard-aborts. Untested allowed in dry-run "
            "proof only. High-risk requires recipe "
            "wardrobe_allow_high_risk."
        ),
    )
    parser.add_argument(
        "--env-id", default=None, dest="env_id",
        help=(
            "Production-proof environment overlay (e.g. env_m012). "
            "Must exist in catalog and allow the recipe scene_type."
        ),
    )
    parser.add_argument(
        "--allow-style-bank-fallback",
        action="store_true",
        help=(
            "Legacy escape hatch. Allows recipes without a catalog outfit "
            "and environment lock to fall back to STYLE_BANK behavior. "
            "Disabled by default because it causes repetitive wardrobe and "
            "setting drift."
        ),
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
    if args.hook_id:
        print(
            f"[lena_build_content_packet_dryrun_v1] "
            f"hook-id : {args.hook_id}"
        )

    print("[lena_build_content_packet_dryrun_v1] Loading recipe bank...")
    recipe_bank = load_json(RECIPE_BANK)

    print("[lena_build_content_packet_dryrun_v1] Loading hook bank...")
    hook_bank = load_json(HOOK_BANK)

    print("[lena_build_content_packet_dryrun_v1] Loading wardrobe catalog...")
    wardrobe_catalog = load_json(WARDROBE_CATALOG)

    print("[lena_build_content_packet_dryrun_v1] Loading environment catalog...")
    env_catalog = load_json(ENV_CATALOG)

    recipe = dict(select_recipe(recipe_bank, args.recipe))
    wf_entry = None
    env_entry = None

    chosen_outfit_id = args.outfit_id or recipe.get("wardrobe_outfit_id")
    if chosen_outfit_id:
        wf_entry = select_wardrobe_entry(
            wardrobe_catalog,
            chosen_outfit_id,
            recipe.get("wardrobe_allow_high_risk", False),
            blocked_terms=recipe.get("wardrobe_blocked_terms", []),
        )
        recipe["wardrobe_outfit_id"] = chosen_outfit_id
        if args.outfit_id:
            recipe["production_proof_mode"] = True
            print(
                f"[lena_build_content_packet_dryrun_v1] "
                f"production-proof outfit override: {chosen_outfit_id} "
                f"(status={wf_entry['status']})"
            )
        else:
            print(
                f"[lena_build_content_packet_dryrun_v1] "
                f"recipe-locked outfit: {chosen_outfit_id} "
                f"(status={wf_entry['status']})"
            )

    chosen_env_id = args.env_id or recipe.get("environment_id")
    if chosen_env_id:
        env_entry = select_environment_entry_for_recipe(
            env_catalog, chosen_env_id, recipe
        )
        recipe["environment_id"] = chosen_env_id
        if args.env_id or not recipe.get("environment_context"):
            recipe["environment_context"] = (
                f"Environment: {env_entry['prompt_fragment']} "
            )
        if args.env_id:
            print(
                f"[lena_build_content_packet_dryrun_v1] "
                f"production-proof env override: {chosen_env_id}"
            )
        else:
            print(
                f"[lena_build_content_packet_dryrun_v1] "
                f"recipe-locked env: {chosen_env_id}"
            )

    if not args.allow_style_bank_fallback:
        missing_locks = []
        if not chosen_outfit_id:
            missing_locks.append("wardrobe_outfit_id")
        if not chosen_env_id:
            missing_locks.append("environment_id")
        if missing_locks:
            raise SystemExit(
                "[ABORT] STYLE_BANK fallback is blocked by default for this "
                f"builder. Recipe '{recipe['id']}' is missing: "
                f"{', '.join(missing_locks)}. "
                "Wire catalog locks into the recipe or pass explicit "
                "--outfit-id/--env-id for dry-run proof work. "
                "Use --allow-style-bank-fallback only as a legacy escape hatch."
            )
    else:
        print(
            "[lena_build_content_packet_dryrun_v1] WARNING: using legacy "
            "STYLE_BANK fallback path because "
            "--allow-style-bank-fallback was supplied."
        )

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
        hook_bank, linked_cats, args.hook_category, args.hook_id
    )
    prompt_budget_override = None
    if wf_entry:
        prompt_budget_override = compute_proof_prompt_budget(
            wardrobe_entry=wf_entry,
            env_entry=env_entry,
        )

    expansion_matrix = build_safe_expansion_matrix(
        recipe,
        recipe_bank,
        wardrobe_catalog,
        env_catalog,
    )

    print(
        f"[lena_build_content_packet_dryrun_v1] "
        f"Hook: {hook['id']} (score {hook['scores']['total_score']})"
    )

    print("[lena_build_content_packet_dryrun_v1] Building packet...")
    packet = build_packet(
        recipe,
        hook,
        hook_reason,
        run_date,
        prompt_budget=prompt_budget_override,
        expansion_matrix=expansion_matrix,
    )

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
