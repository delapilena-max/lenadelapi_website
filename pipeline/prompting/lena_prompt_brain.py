from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict

BANNED_PUBLIC_TERMS = [
    "AI",
    "artificial intelligence",
    "virtual influencer",
    "synthetic",
    "digital human",
    "bot",
    "generated",
    "avatar",
    "fake",
    "computer generated",
]

IDENTITY_ANCHOR = (
    "Lena Delapi, using the current approved Lena character element as the only identity source of truth. "
    "Match the current Lena element exactly for face, eyes, brows, mouth, jawline, skin tone, hair color, hairline, "
    "hairstyle family, and overall adult facial geometry. "
    "Her eyes must stay deep dark brown exactly like the current approved close-up reference, never hazel, never amber, never green-gray, and never lightened. "
    "Do not reinterpret her into a rounder, thinner, younger, wider-smiling, more generic, or more glam substitute face. "
    "Do not beautify away her actual likeness. Keep the same recognizable woman from the current Lena element."
)

LENA_MASTER_IDENTITY = (
    "Identity fixed: preserve Lena's approved adult slim-thick "
    "hourglass body across every outfit, pose, scene, and camera angle. "
    "Full natural bust, small defined waist without shrinking her frame, "
    "visibly wide hips, toned upper thighs, soft realistic hip curve, "
    "consistent slightly wide pelvis breadth, a slightly wider-set hip span from the front and 3/4 view, "
    "a touch more lateral hip breadth, a slightly fuller outer-thigh and upper-glute read, "
    "and balanced curvy proportions. "
    "Do not reinterpret her as a different person. "
    "Do not slim her down, make her petite, narrow-hipped, "
    "thin-legged, straight-hipped, runway-model, or waif-like. "
    "Do not narrow her pelvis, collapse her hip width, pull her hip points inward, or taper her lower "
    "body into a slimmer silhouette in side angles, standing poses, or seated poses. "
    "Her lower body should still read full through the outer hips and upper thighs even under jeans, skirts, and dresses; "
    "do not straighten her into a narrow column from waist to hem. "
    "A slight natural inner-thigh separation is acceptable in neutral standing poses "
    "when the stance supports it, but never as an anatomical distortion. "
    "Do not over-thicken her hips, thighs, or torso beyond the approved "
    "reference proportions either. Keep her attractive, toned, curvy, "
    "and realistic -- never shrunken, never exaggerated, never bulky. "
    "Wardrobe must fit over her existing curvy proportions "
    "and must not reshape her into a thinner body. "
    "Outfit, pose, lighting, and action may change; "
    "face and body proportions may not."
)

SKIN_REALISM = (
    "unretouched phone-camera skin with subtle real texture, clear natural complexion, "
    "faint lower-lid and under-eye detail, soft natural tone variation, gentle natural asymmetry, "
    "and believable skin depth without decorative texture artifacts. "
    "No skin blur, no denoised skin, no softened pore detail, and no pore-dot pattern. "
    "Micro detail: tiny peach-fuzz edge highlights, individual brow hairs, "
    "real eyelashes with small shadows, imperfect lip texture, a few stray hair strands, "
    "slight mouth-corner creasing, faint smile-line softness, normal eyelid fold depth, "
    "subtle tear-trough transition, natural philtrum and lip-edge definition, "
    "uneven natural catchlights, and scene-light falloff across the face. "
    "Face detail comes from the current Lena character element; keep the facial surface faithful to that element. "
    "Preserve only the exact tiny beauty marks and natural skin details already visible in the current Lena element, with no increase in count or density. "
    "Do not invent freckles, any visible freckle field, dotted cheek speckling, nose-bridge speckles, fake pore dots, or new mole placements. "
    "Keep her eye color exactly as it appears in the current Lena element: deep dark brown irises, not hazel, not amber, not green-gray, and not lightened. "
    "Not plastic, not waxy, not over-smoothed, not CGI, not glossy doll skin. "
    "No beauty-filter skin, no airbrushed mannequin skin, "
    "no polished beauty-campaign finish, no commercial skin retouch look, "
    "no foundation-ad finish, and no decorative beauty-filter surface pattern that changes her identity. "
    "No baby-face stylization, no oversized irises, no porcelain doll facial finish, "
    "and no smoothed influencer-face retouch geometry. "
    "Preserve her adult sexy face structure: refined but natural nose shape, realistic lip volume, natural cheek width, "
    "and a believable jawline that does not widen under smile. "
    "Expressions can vary naturally across images, but avoid huge grins or any smile that unnaturally widens her jaw or lower face. "
    "Soft smile or slightly parted lips are fine; no veneer-ad grin, no filler-look lips, and no teenified or doll-like face read."
)

PHOTO_REALISM = (
    "Photograph realism: this should read like a real camera capture, not beauty-ad retouch. "
    "Natural exposure rolloff, true skin color variation, slight sensor grain when appropriate, "
    "realistic shadow transitions, subtle lens falloff, authentic depth of field, and non-plastic facial rendering. "
    "Avoid polished campaign perfection, over-lit studio gloss, synthetic facial symmetry, oversized irises, "
    "or veneer-perfect smile styling. "
    "Face must stay reference-faithful rather than idealized into a generic pretty influencer face."
)

EXPRESSION_REALISM = (
    "Expression realism: keep her facial expressions versatile and human across images. "
    "Use neutral looks, soft smiles, playful looks, thoughtful looks, and confident expressions when appropriate, "
    "but avoid huge grins or expression geometry that widens the face unnaturally."
)

PHONE_OBJECT_REALISM = (
    "Real-world coherence: the image must make physical and social sense at a glance. "
    "No impossible prop logic, no lipstick or makeup items fused into fingers or palms, no floating accessories, "
    "no broken glassware, and no objects intersecting hands. "
    "If a phone appears, it must obey real camera logic with correct front/back orientation, believable grip, "
    "correct reflection behavior, and no impossible screen content or malformed device geometry. "
    "No bathroom-mirror vanity grammar, elevator reflection gimmicks, or fake getting-ready props in public social scenes."
)

SOCIAL_HOOK_FLAVOR = (
    "Taste profile: believable social-life energy with real-feed hook appeal, not sterile editorial staging. "
    "The image should feel like a flattering but human post from an actual outing, dinner, drinks, coffee stop, "
    "city errand, or candid in-between moment. "
    "When the scene allows, use socially legible context cues like menu corners, table clutter, water glasses, "
    "dessert plates, receipts, sidewalk texture, chair backs, nearby people in blur, window reflections, "
    "or lived-in venue imperfections. Keep it sexy, socially plausible, and scroll-stopping without looking fabricated."
)

HAND_REALISM = (
    "Hands should read as natural human hands with five fingers on each hand, "
    "correct thumb placement, believable knuckle joints, realistic nail scale, "
    "relaxed wrists, and simple candid hand posing. "
    "Avoid complex interlocked fingers, overlapping hand tangles, mannequin hands, "
    "melted fingers, fused fingers, twisted wrists, broken-looking joints, hands clipping through "
    "doorframes or walls, fingers intersecting glassware or furniture, or arms merging into nearby objects."
)

MAIN_REFERENCE_POLICY = (
    "Preserve Lena's facial identity, skin tone, body proportions, silhouette, posture, clothing fit, hands, legs, waist-to-hip shape, and overall likeness from the current approved Lena character element. "
    "Use only the current approved Lena element as the identity source of truth."
)

LENA_BODY_DESCRIPTOR = (
    "Lena has a realistic, highly photogenic slim-thick feminine silhouette: "
    "full natural bust, small defined waist without shrinking her frame, "
    "visibly wide hips, toned upper thighs, soft rounded hip curve, "
    "consistent slightly wide pelvis breadth, slightly wider-set hip points, a touch more lateral hip width, "
    "and a slightly fuller outer-thigh and upper-glute read, long toned legs, graceful shoulders, "
    "and balanced curvy proportions. "
    "A slight natural inner-thigh separation can appear in neutral standing poses "
    "when anatomically plausible. "
    "Her proportions should look attractive, consistent, realistic, "
    "fully clothed, and editorial: clear hourglass waist-to-hip shape, "
    "natural posture, believable hands and legs, "
    "no exaggerated cartoon proportions, not slim, not petite, not bulky."
)

# Negative-prompt budget repair (2026-07-06). The prior single flat
# NEGATIVE_PROMPT string measured 2734 chars against the executor's 2499-char
# cap -- an overflow before any outfit-specific/public-lane term was even
# added, meaning first-N-fit compaction silently dropped whatever fell past
# the budget with no priority given to any category. Restructured into five
# tiers so the executor (pipeline/kling_apilena_api_executor.py) can apply a
# narrow reserved floor per tier, the same pattern already proven on the
# positive-prompt side. NEGATIVE_PROMPT below is reconstructed as the exact
# concatenation of all five tiers, in the same order as before, so its value
# and every consumer of it are unaffected by this refactor.
#
# Two terms were dropped as confirmed exact-concept duplicates found by direct
# audit: "navel piercing" (duplicate of "belly button piercing") and "belly
# button jewelry" (duplicate of "navel jewelry"). No other term was removed,
# reworded, or reordered across categories -- every other term from the prior
# flat list is preserved, just grouped by protection class instead of left in
# one undifferentiated string.
CORE_NEGATIVE_TERMS = (
    "low quality", "blurry", "distorted face", "changed face", "identity drift",
    "wrong eye color for the current Lena element", "altered iris color", "brightened irises",
    "pale irises", "desaturated irises", "hazel eyes", "amber eyes", "green eyes", "gray eyes",
    "light eyes", "gray-green eyes",
    "watermark", "text overlay", "logo", "duplicate person", "extra limbs",
)

STYLE_REALISM_NEGATIVE_TERMS = (
    "harsh face distortion", "waxy skin", "plastic skin", "over-smoothed skin", "airbrushed skin",
    "beauty filter skin", "mannequin skin", "poreless face", "CGI face", "3D-rendered face",
    "glossy doll skin", "synthetic smooth face", "skin blur", "denoised skin", "softened pore detail",
    "blurred skin texture", "beauty-retouched face", "foundation-ad skin", "porcelain doll face",
    "baby-face stylization", "oversized irises", "inflated lips", "over-clean facial geometry",
    "glam retouch face", "uncanny expression", "cartoon", "anime", "doll-like",
    "overly glossy specular skin",
)

PUBLIC_SAFETY_NEGATIVE_TERMS = (
    "belly button piercing", "navel jewelry", "navel ring",
    "bike shorts", "compression shorts", "hot pants", "underwear-like shorts",
    "bra as outerwear", "lingerie in public", "bikini top as streetwear",
    "underwear visible as clothing in outdoor or street settings",
)

BODY_ANATOMY_NEGATIVE_TERMS = (
    "unrealistic body proportions",
    "deformed hands", "extra fingers", "missing fingers", "fused fingers", "melted fingers",
    "tangled fingers", "broken knuckles", "twisted wrists", "bad thumb placement", "mannequin hands",
    "bad anatomy", "crossed eyes", "unnaturally long fingers", "elongated slender fingers",
    "glossy plastic fake nails", "uniform white press-on nails", "overly manicured nails",
    "doll-like fingers", "rubbery fingers", "stiff posed fingers", "airbrushed hand skin",
    "skinny body", "petite frame", "narrow hips", "inward-pulled hip points", "narrow pelvis",
    "thin thighs", "slim runway model proportions", "wasp waist", "bulky thighs", "thickened torso",
    "exaggerated heavy lower body", "flat chest", "reduced bust volume", "reduced hip volume",
    "thinned seated body",
)

OPTIONAL_FILL_NEGATIVE_TERMS = (
    "random added freckles", "light freckling", "visible freckle field", "extra freckle-like speckles",
    "decorative freckle mask", "beauty-filter speckling", "fake pore dots", "pore-dot mask",
    "moved beauty marks", "mirrored beauty marks", "multiplied beauty marks", "enlarged beauty marks",
    "new non-reference mole placements", "new non-reference heavy freckle clusters",
    "overstretched smile", "widened smiling face", "broad cartoon grin", "jaw widened by smile",
    "puffed smile cheeks", "pinched doll nose", "filler-look lips", "overly plumped lips",
    "teenified face", "generic instagram face",
    "hand through wall", "hand through door", "arm clipping through doorframe",
    "fingers intersecting glass", "limb clipping through furniture", "object-merging hands",
    "hotel room", "luxury suite", "hospitality decor", "showroom interior",
    "upholstered hotel headboard", "nightstand hotel telephone", "commercial beauty ad lighting",
    "editorial glam campaign lighting", "polished resort room",
)

# Union of every outfit-conditional substitution term from the dress / crop-top /
# bodysuit / skirt / shorts / outerwear branches of build_public_lane_negative_prompt()
# below, exposed as a named constant purely so the executor can use it as a
# reserved-floor matching set. Deliberately duplicated (not refactored out of)
# the inline lists below -- this keeps build_public_lane_negative_prompt's own
# assembly logic byte-for-byte unchanged, at the cost of needing to keep this
# constant in sync if those inline lists ever change. Does NOT include the
# sleeveless-top-and-skirt garment-obedience terms, which are a separate,
# already-floor-protected class (kling_apilena_api_executor.py's
# _GARMENT_OBEDIENCE_NEGATIVE_TERMS) left untouched by this repair.
OUTFIT_SPECIFIC_SUBSTITUTION_TERMS = (
    "dress split into top and skirt", "cutout dress drift", "two-piece outfit replacing dress",
    "crop top when full-length top is specified", "cropped sweater replacing named top",
    "turtleneck crop top replacing named top", "bra-band silhouette replacing named top",
    "bodysuit rendered as bra top", "bodysuit rendered as sports bra", "bodysuit rendered as crop top",
    "bodysuit hem floating above waistband", "exposed stomach when bodysuit is specified",
    "separated bra band and jeans waistband when bodysuit is specified",
    "dress replacing separate top and skirt", "bodycon tube skirt replacing named skirt",
    "soft knit skirt replacing structured skirt", "denim skirt replaced with jersey or knit bodycon skirt",
    "bike shorts replacing named shorts", "biker shorts replacing named shorts",
    "shapewear shorts replacing named shorts", "underwear-like shorts replacing named shorts",
    "hot pants replacing tailored shorts",
    "coat over bra top", "trench coat over bra top", "blazer over bralette", "jacket over bra",
    "visible stomach under outerwear", "midriff exposed under outerwear",
    "underbust exposed under open coat",
)

# The clothing-safety subset of build_public_lane_negative_prompt()'s always-added
# public-lane extras (selfie-framing terms excluded -- those are a composition
# preference, not a clothing-safety protection, and are covered by the optional
# fill tier). Same duplication rationale as OUTFIT_SPECIFIC_SUBSTITUTION_TERMS
# above: exposed for the executor's reserved-floor matching without touching the
# inline assembly logic below.
PUBLIC_LANE_SAFETY_TERMS = (
    "bra top", "bikini-like bodice", "triangle top",
    "separated top and skirt when dress is specified",
    "underbust exposed in public", "bare midriff in public when dress is specified",
)

NEGATIVE_PROMPT = ", ".join(
    CORE_NEGATIVE_TERMS
    + STYLE_REALISM_NEGATIVE_TERMS
    + PUBLIC_SAFETY_NEGATIVE_TERMS
    + BODY_ANATOMY_NEGATIVE_TERMS
    + OPTIONAL_FILL_NEGATIVE_TERMS
)

MIDRIFF_COVERAGE_NEGATIVE_SUFFIX = (
    "unplanned midriff gap on a full-coverage outfit, full-length top shrinking into a crop, "
    "gap between top hem and waistband when the outfit specifies coverage, "
    "hoodie floating above waistband, ultra-cropped hoodie, cropped quarter-zip, "
    "cropped pullover, cropped sweater, cropped long-sleeve top, "
    "bikini-like crop top replacing a real top, bra top under open shirt, bralette substituted for "
    "tank top, bandeau under open button-down, micro-cami ending above waistband"
)


def _catalog_prompt_lower(entry: dict | None) -> str:
    return str((entry or {}).get("prompt") or "").lower()


def catalog_outfit_is_bodysuit(entry: dict | None) -> bool:
    return "bodysuit" in _catalog_prompt_lower(entry)


def catalog_outfit_has_outerwear_shell(entry: dict | None) -> bool:
    prompt = _catalog_prompt_lower(entry)
    return any(
        token in prompt
        for token in [
            "coat",
            "trench",
            "blazer",
            "jacket",
            "overshirt",
            "open shirt",
            "open blouse",
            "cardigan",
        ]
    )


def catalog_outfit_has_explicit_full_base_layer(entry: dict | None) -> bool:
    prompt = _catalog_prompt_lower(entry)
    if "dress" in prompt:
        return True
    full_length_tokens = [
        "tee",
        "t-shirt",
        "tshirt",
        "shirt",
        "blouse",
        "sweater",
        "turtleneck",
        "quarter-zip",
        "quarter zip",
        "pullover",
        "long-sleeve",
        "long sleeve",
        "bodysuit",
        "tank",
        "tank top",
        "cami",
        "top",
    ]
    if not any(token in prompt for token in full_length_tokens):
        return False
    return not any(
        token in prompt
        for token in [
            "crop",
            "cropped",
            "bralette",
            "bikini",
            "bandeau",
            "bra top",
            "micro-cami",
        ]
    )


def catalog_outfit_public_outerwear_needs_underlayer(entry: dict | None) -> bool:
    if not entry:
        return False
    return (
        catalog_outfit_has_outerwear_shell(entry)
        and not catalog_outfit_has_explicit_full_base_layer(entry)
    )


def catalog_outfit_midriff_must_stay_covered(entry: dict | None) -> bool:
    if not entry:
        return False
    prompt = _catalog_prompt_lower(entry)
    if catalog_outfit_is_bodysuit(entry):
        return True
    if any(
        token in prompt
        for token in ["crop", "cropped", "cutout"]
    ):
        return False
    if any(token in prompt for token in ["low-rise", "low rise"]):
        return False
    if "dress" in prompt:
        return True
    if catalog_outfit_public_outerwear_needs_underlayer(entry):
        return True
    return any(
        token in prompt
        for token in [
            "top", "tee", "tank", "turtleneck", "pullover",
            "quarter-zip", "shirt", "blouse", "sweater",
            "long-sleeve", "long sleeve", "cami",
            "mock-neck", "mock neck", "bodysuit",
        ]
    )


# Batch 7 (2026-07-06): two consecutive same-slot proof renders on a sleeveless-tank
# + mini-skirt public outfit (wc_p082) substituted a different, unrelated covering
# garment (trench+scarf, then a turtleneck sweater) despite a verified-correct
# submitted prompt. The existing Skirt-set continuity lock covers fabric/coverage
# nuances (crop vs. full-length, shapewear-look) but never explicitly forbade
# substituting the whole garment class for outerwear. Narrow, silhouette-class-scoped
# fix: only the sleeveless/tank-top + skirt class, not a blanket rule.
def catalog_outfit_is_sleeveless_top_skirt_set(entry: dict | None) -> bool:
    """True for a public two-piece outfit: a sleeveless/tank-style top paired with a
    separate skirt. Deliberately narrow -- does not match shirt/blouse/knit/sweater
    tops, which are not the silhouette class implicated in the proof failures."""
    prompt = _catalog_prompt_lower(entry)
    if "skirt" not in prompt:
        return False
    if "crop" in prompt or "cropped" in prompt:
        return False
    return any(
        token in prompt
        for token in ("tank", "halter", "sleeveless", "strapless", "one-shoulder", "off-shoulder")
    )


def build_negative_prompt_for_catalog(entry: dict | None) -> str:
    negative = NEGATIVE_PROMPT
    if catalog_outfit_midriff_must_stay_covered(entry):
        negative = f"{negative}, {MIDRIFF_COVERAGE_NEGATIVE_SUFFIX}"
    return negative


def build_public_lane_negative_prompt(entry: dict | None, lane: str, negative: str) -> str:
    if lane not in PUBLIC_SOCIAL_LANES:
        return negative

    extra_bits = [
        "mirror selfie",
        "bathroom selfie",
        "phone held toward camera",
        "phone visible in foreground",
        "arm-extended selfie framing",
        "front-camera selfie",
        "selfie composition instead of friend-shot",
        "bra top",
        "bikini-like bodice",
        "triangle top",
        "separated top and skirt when dress is specified",
        "underbust exposed in public",
        "bare midriff in public when dress is specified",
    ]

    prompt = str((entry or {}).get("prompt") or "").lower()

    # Batch 7b (2026-07-06): moved ahead of every other conditional block. The
    # negative-prompt compactor keeps terms in source order until the char budget
    # runs out (no floor mechanism on the negative side yet) -- these terms were
    # previously appended last, inside the skirt block, and none of them survived a
    # real compaction test. Placing them here, immediately after the base list, gives
    # them the same first-N-fit priority as the base selfie/bra-top protections,
    # without adding a new mechanism.
    if catalog_outfit_is_sleeveless_top_skirt_set(entry):
        extra_bits.extend([
            "turtleneck replacing sleeveless top",
            "turtleneck sweater replacing named top",
            "trench coat replacing named top",
            "peacoat replacing named top",
            "cardigan replacing named top",
            "blazer replacing named top",
            "scarf replacing named top",
            "long sleeves replacing sleeveless top",
            "winter coat over outfit",
            "puffer jacket over outfit",
            "layered coat replacing named outfit",
        ])

    if "dress" in prompt:
        extra_bits.extend([
            "dress split into top and skirt",
            "cutout dress drift",
            "two-piece outfit replacing dress",
        ])
    if (
        any(token in prompt for token in ["top", "halter", "tank", "tee", "shirt", "blouse", "cami", "knit", "sweater"])
        and "crop" not in prompt
        and "cropped" not in prompt
    ):
        extra_bits.extend([
            "crop top when full-length top is specified",
            "cropped sweater replacing named top",
            "turtleneck crop top replacing named top",
            "bra-band silhouette replacing named top",
        ])
    if "bodysuit" in prompt:
        extra_bits.extend([
            "bodysuit rendered as bra top",
            "bodysuit rendered as sports bra",
            "bodysuit rendered as crop top",
            "bodysuit hem floating above waistband",
            "exposed stomach when bodysuit is specified",
            "separated bra band and jeans waistband when bodysuit is specified",
        ])
    if "skirt" in prompt:
        extra_bits.extend([
            "dress replacing separate top and skirt",
            "bodycon tube skirt replacing named skirt",
            "soft knit skirt replacing structured skirt",
        ])
        if "denim" in prompt:
            extra_bits.append("denim skirt replaced with jersey or knit bodycon skirt")
    if "shorts" in prompt:
        extra_bits.extend([
            "bike shorts replacing named shorts",
            "biker shorts replacing named shorts",
            "shapewear shorts replacing named shorts",
            "underwear-like shorts replacing named shorts",
            "hot pants replacing tailored shorts",
        ])
    if catalog_outfit_has_outerwear_shell(entry):
        extra_bits.extend([
            "coat over bra top",
            "trench coat over bra top",
            "blazer over bralette",
            "jacket over bra",
            "visible stomach under outerwear",
            "midriff exposed under outerwear",
            "underbust exposed under open coat",
        ])

    return f"{negative}, {', '.join(extra_bits)}"

PUBLIC_WARDROBE_RULE = (
    "Wardrobe must read as intentional real fashion for the setting: sexy, model-like, graceful, stylish, believable, "
    "and appropriate to the scene rather than accidental underwear, swimwear, or garment failure. "
    "In public scenes like restaurants, bars, patios, sidewalks, hotel lobbies, elevators, shops, and transit, "
    "the main visible garment must read as deliberate public-facing fashion. Intentional skin is allowed when the outfit calls for it; "
    "do not turn unrelated garments into a bikini, bra, lingerie set, or half-dressed improv."
)

PUBLIC_SOCIAL_LANES = {
    "night out",
    "dinner booth",
    "wine bar patio",
    "brunch patio",
    "sidewalk dinner",
    "lobby cocktail bar",
    "coffee shop",
    "bookstore",
    "flower shop",
    "record store",
    "museum afternoon",
    "city bench",
    "rooftop sunset",
    "elevator moment",
    "laundry day",
}

VISIBLE_TORSO_GARMENT_TERMS = (
    "dress", "top", "tee", "shirt", "blouse", "sweater", "knit",
    "cami", "tank", "bodysuit", "corset", "cardigan", "halter",
    "strapless", "one-shoulder", "off-shoulder"
)

OUTER_LAYER_ONLY_TERMS = (
    "coat", "trench", "blazer", "jacket",
)

SEXY_PUBLIC_PRIMARY_TERMS = (
    "mini dress", "mini skirt", "scoop-neck", "scoop neck", "square-neck", "square neckline",
    "v-neck", "v neckline", "off-shoulder", "one-shoulder", "wrap mini dress",
    "slip dress", "blazer dress", "asymmetric neckline", "asymmetric wrap", "fitted mini dress",
    "tank top", "fitted tank", "blazer vest", "tailored high-waist wide-leg shorts",
    "bodysuit", "corset-style fashion top", "halter fashion top", "halter knit top",
    "strapless corset-style", "mesh sleeves", "satin midi skirt", "denim maxi skirt",
    "leather mini skirt", "low-rise", "low-slung", "side slit", "knee-high boots",
)

SEXY_PUBLIC_SECONDARY_TERMS = (
    "fitted", "satin", "silk-look", "silky", "velvet", "bias-cut", "side slit",
    "strappy", "body-skimming", "curve-skimming", "open blazer", "open jacket",
    "straight jeans", "wide-leg trousers", "maxi skirt", "cardigan worn buttoned",
    "cargo maxi skirt", "open shoulders", "structured seams", "real waistband",
)

TOO_SAFE_PUBLIC_TERMS = (
    "button-down shirt", "button-front shirt", "button-front top",
    "plain white tee", "crew-neck tee", "oversized white button-down",
    "corporate", "office", "businesslike", "business-like",
)

STYLE_BANK = [
    # ------------------------------------------------------------------ COZY/APARTMENT
    {
        "category": "cozy",
        "outfit": "a sage green matching lounge set — a short-sleeve fitted crop top and relaxed shorts in a soft French terry fabric",
        "hair": "freshly washed loose waves, slightly damp, falling naturally past the shoulders",
        "makeup": "bare skin, just SPF tint and clear gloss",
        "accessories": "single dainty gold chain, bare feet",
    },
    {
        "category": "cozy",
        "outfit": "an oatmeal waffle-knit two-piece — a boxy short-sleeve top and wide-leg matching trousers",
        "hair": "messy low bun with soft face-framing pieces falling out",
        "makeup": "soft brow gel and peachy gloss only",
        "accessories": "no accessories",
    },
    {
        "category": "cozy",
        "outfit": "an oversized lavender university crewneck sweatshirt and black biker shorts",
        "hair": "high messy bun secured with a fabric scrunchie, a few flyaway strands",
        "makeup": "no makeup, post-shower dewy skin",
        "accessories": "white crew socks, no jewelry",
    },
    {
        "category": "cozy",
        "outfit": "a beige ribbed spaghetti-strap matching set — a scoop-neck crop top and wide-leg pants in a stretchy rib knit",
        "hair": "air-dried wavy hair falling loosely, slight natural texture",
        "makeup": "mascara and a tinted nudish lip gloss",
        "accessories": "tiny gold hoop earrings",
    },
    {
        "category": "cozy",
        "outfit": "a dusty rose satin pajama-style set — a short-sleeve button-front top with a chest pocket and straight-leg matching trousers",
        "hair": "half-up loose twist, soft and undone",
        "makeup": "lip balm only, fresh clean skin",
        "accessories": "single thin gold ring",
    },
    {
        "category": "cozy",
        "outfit": "a cloud gray full-zip oversized hoodie and matching straight-leg joggers in a cotton-blend fleece",
        "hair": "low loose twin braids, slightly messy",
        "makeup": "bare-skin natural look, no product",
        "accessories": "white chunky sneakers visible",
    },
    {
        "category": "cozy",
        "outfit": "an off-white flowy cropped open-front cardigan over a fitted white ribbed bralette and white bike shorts",
        "hair": "loose second-day waves tucked behind one ear",
        "makeup": "mascara and a barely-there nude gloss",
        "accessories": "two layered dainty gold necklaces",
    },
    {
        "category": "cozy",
        "outfit": "a faded lilac vintage-style fitted crop tee and cream high-waisted biker shorts",
        "hair": "textured half-up, pulled loosely with a thin elastic",
        "makeup": "fresh skin, brow gel, soft mascara",
        "accessories": "white hair scrunchie on wrist",
    },
    {
        "category": "cozy",
        "outfit": "a soft pink terrycloth short-sleeve romper with a relaxed boxy fit and button placket",
        "hair": "effortless top-knot bun, slightly lopsided",
        "makeup": "dewy skin and clear gloss",
        "accessories": "no jewelry",
    },
    {
        "category": "cozy",
        "outfit": "an army green oversized short-sleeved button-down worn open over a white fitted ribbed bralette and matching army green joggers",
        "hair": "high messy bun with flyaways and a few face-framing strands",
        "makeup": "skin-first: concealer only, brushed brows",
        "accessories": "small gold hoop, slim gold watch",
    },
    {
        "category": "cozy",
        "outfit": "a cream ribbed short-shorts co-ord set — scoop-neck crop top and matching high-waist shorts in a tight rib knit",
        "hair": "beach waves loose and slightly tousled",
        "makeup": "soft blush and mascara",
        "accessories": "layered thin gold chains at the collarbone",
    },
    {
        "category": "cozy",
        "outfit": "a charcoal seamless matching athletic set — a high-neck fitted bralette and flare leggings",
        "hair": "hair slicked back into a clean low ponytail",
        "makeup": "no makeup, natural skin",
        "accessories": "tiny gold stud earrings",
    },
    {
        "category": "cozy",
        "outfit": "a blush satin cami top and matching wide-leg satin trousers in a fluid drape",
        "hair": "loose low twist, soft and romantic",
        "makeup": "barely-there makeup, slightly glossy lip",
        "accessories": "no jewelry, bare feet",
    },
    {
        "category": "cozy",
        "outfit": (
            "a fitted white zip-up hoodie in medium-weight cotton "
            "French terry sweatshirt fabric, flat non-quilted fabric surface, "
            "hem meeting or slightly overlapping the high waistband "
            "with no bare navel visible, softly shaped at the waist "
            "without squeezing it, paired with matching high-waist fitted "
            "white French terry joggers with a visible waistband, "
            "tapered leg, side seams, soft fabric drape, natural wrinkles, "
            "and a close but not skintight fit; "
            "clean white sneakers, small gold bracelet; "
            "not shorts, not hot pants, not leggings, not underwear, "
            "not puffer, not bulky outerwear, "
            "no exposed belly button, no visible navel"
        ),
        "hair": (
            "Lena's signature rich dark auburn-brown hair, "
            "long voluminous loose curls falling over her shoulders "
            "and chest, a few front pieces softly pinned back, "
            "hair visibly down, no blonde hair, no bleached highlights, "
            "no bun, no messy updo, no ponytail"
        ),
        "makeup": "soft natural makeup, peachy gloss",
        "accessories": "small gold chain bracelet",
    },
    {
        "category": "cozy",
        "outfit": "a rust-orange oversized French terry pullover hoodie and black athletic shorts",
        "hair": "high bun with flyaways, a strand or two across her forehead",
        "makeup": "mascara and clean skin",
        "accessories": "clean white low-top sneakers visible",
    },
    # ------------------------------------------------------------------ ELEVATED CASUAL
    {
        "category": "elevated_casual",
        "outfit": "wide-leg camel linen trousers with a light crease, a fitted black ribbed scoop-neck top tucked in, and a brown leather belt",
        "hair": "loose low ponytail with soft volume at the crown",
        "makeup": "defined brow, warm brown lip, subtle glow",
        "accessories": "gold hoops, slim gold watch",
    },
    {
        "category": "elevated_casual",
        "outfit": "a butter-yellow linen co-ord set — a relaxed short-sleeve button-front shirt and matching wide-leg shorts",
        "hair": "half-up loose twist, natural texture",
        "makeup": "light bronzy flush, mascara, soft satin lip",
        "accessories": "thin leather sandals implied",
    },
    {
        "category": "elevated_casual",
        "outfit": "a black high-waisted midi skirt with a subtle slit and a fitted white V-neck tee half-tucked in",
        "hair": "face-framing waves, loose and easy",
        "makeup": "soft glam — light foundation, peachy cheek, mascara",
        "accessories": "gold layered necklaces and a simple ring",
    },
    {
        "category": "elevated_casual",
        "outfit": "light-wash wide-leg jeans with a clean hem and a pale green fitted scoop-neck tank tucked in",
        "hair": "air-dried wavy hair, middle part, slightly tousled",
        "makeup": "tinted moisturizer, soft lip, brow gel",
        "accessories": "delicate gold chain, small hoop earrings",
    },
    {
        "category": "elevated_casual",
        "outfit": "a tailored off-white linen blazer worn as a jacket with matching high-waisted trousers and a simple white V-neck underneath",
        "hair": "sleek low bun, pulled back cleanly",
        "makeup": "defined brow, mauve lip, polished natural",
        "accessories": "gold watch",
    },
    {
        "category": "elevated_casual",
        "outfit": "a chocolate brown fitted knit midi dress with a slight flare at the hem and a subtle V-neck",
        "hair": "loose second-day waves pulled over one shoulder",
        "makeup": "soft bronze eye, warm brown gloss",
        "accessories": "small gold hoops, layered gold chain",
    },
    {
        "category": "elevated_casual",
        "outfit": "stone-gray straight-leg tailored trousers and an oversized white button-down shirt, half-tucked and slightly wrinkled",
        "hair": "relaxed low ponytail with a few face-framing strands loose",
        "makeup": "barely-there, skin-first, tinted lip",
        "accessories": "loafers implied",
    },
    {
        "category": "elevated_casual",
        "outfit": "a forest green satin slip skirt (midi) and a fitted white ribbed tank top, slightly cropped",
        "hair": "beach-texture waves, loose and lived-in",
        "makeup": "soft glow, mascara, nude lip",
        "accessories": "gold hoops, delicate ring stack",
    },
    {
        "category": "elevated_casual",
        "outfit": "navy blue tailored wide-leg trousers with a thin pinstripe and a fitted white ribbed scoop-neck long-sleeve",
        "hair": "blown out with volume, soft movement",
        "makeup": "defined brow, soft peach lip, fresh skin",
        "accessories": "slim gold chain, small gold hoops",
    },
    {
        "category": "elevated_casual",
        "outfit": "a cream oversized blazer worn as a mini dress, belted loosely, with a black bralette visible and black biker shorts underneath",
        "hair": "high straight ponytail, sleek",
        "makeup": "bold brow, glossy lip",
        "accessories": "chunky gold rings on multiple fingers",
    },
    {
        "category": "elevated_casual",
        "outfit": "a dusty rose floral-print midi wrap skirt and a fitted white sleeveless ribbed top",
        "hair": "loose waves down, natural movement",
        "makeup": "soft blush, peachy gloss",
        "accessories": "tiny gold stud earrings",
    },
    {
        "category": "elevated_casual",
        "outfit": "dark olive wide-leg cargo-style pants with visible pockets and a fitted white waffle-knit long-sleeve",
        "hair": "slightly loose side braid, casual and undone",
        "makeup": "skin-first, tinted gloss",
        "accessories": "black baseball cap, small gold hoop",
    },
    {
        "category": "elevated_casual",
        "outfit": "mid-wash boyfriend jeans with a slight roll at the ankle and a pale blue fitted quarter-zip pullover",
        "hair": "relaxed half-up with gentle waves falling down",
        "makeup": "soft brow, barely-there gloss",
        "accessories": "small gold hoop earrings",
    },
    {
        "category": "elevated_casual",
        "outfit": "a burgundy midi satin pleated skirt and a fitted black scoop-neck long-sleeve tucked in",
        "hair": "curled loose hair, falling down",
        "makeup": "defined mascara, berry-toned lip",
        "accessories": "gold layered chains",
    },
    {
        "category": "elevated_casual",
        "outfit": "dusty blue relaxed cotton trousers and a fitted white cropped button-down shirt tied loosely at the waist",
        "hair": "low messy bun with face-framing pieces",
        "makeup": "soft natural skin, light mascara",
        "accessories": "woven straw tote implied",
    },
    # ------------------------------------------------------------------ FITNESS / ATHLEISURE
    {
        "category": "fitness",
        "outfit": "an all-black form-fitting set — a high-neck sports bra and high-waist full-length leggings in a smooth nylon blend",
        "hair": "high tight ponytail, no flyaways",
        "makeup": "no makeup, post-workout dewy skin",
        "accessories": "black sports watch",
    },
    {
        "category": "fitness",
        "outfit": "a sage green matching athletic set — a strappy low-back bralette and high-waist leggings in a four-way stretch fabric",
        "hair": "messy high bun with flyaway strands",
        "makeup": "light mascara and a clear gloss",
        "accessories": "white running shoes implied",
    },
    {
        "category": "fitness",
        "outfit": "a dusty mauve sports bra and matching bike shorts with an oversized white zip-up hoodie worn open over it",
        "hair": "low messy bun, slightly damp-looking",
        "makeup": "barely-there skin-first look",
        "accessories": "white earbuds looped around neck",
    },
    {
        "category": "fitness",
        "outfit": "navy blue fitted athletic shorts and a fitted white racerback sports bra with a navy lightweight quarter-zip jacket unzipped",
        "hair": "high ponytail, clean and pulled back",
        "makeup": "skin-forward, natural",
        "accessories": "small gold studs",
    },
    {
        "category": "fitness",
        "outfit": "a bright cobalt blue two-piece athletic set — a fitted scoop-neck bralette and matching high-waist flare leggings",
        "hair": "loose high bun, slightly imperfect",
        "makeup": "minimal, clear gloss",
        "accessories": "white fabric headband",
    },
    {
        "category": "fitness",
        "outfit": "charcoal biker shorts and a faded gray oversized graphic tee knotted loosely at the hip",
        "hair": "side braid, loose and messy",
        "makeup": "no makeup, fresh clean skin",
        "accessories": "black ankle socks, clean white sneakers visible",
    },
    {
        "category": "fitness",
        "outfit": "a blush pink fitted ribbed athletic set — a scoop-neck crop top and matching high-waist flare leggings in a soft stretch fabric",
        "hair": "freshly washed loose waves, down",
        "makeup": "dewy skin and soft mascara",
        "accessories": "small gold hoops",
    },
    {
        "category": "fitness",
        "outfit": "olive green athletic shorts and a fitted white cotton crop tee with a slightly raw hem",
        "hair": "high bun with a fabric scrunchie",
        "makeup": "skin-only, no product",
        "accessories": "slides implied",
    },
    {
        "category": "fitness",
        "outfit": "a black seamless high-neck bralette and slate-gray high-waist full-length leggings with an oatmeal oversized fleece crewneck pullover",
        "hair": "half-up loose, slightly messy",
        "makeup": "mascara only",
        "accessories": "small thin gold hoop",
    },
    {
        "category": "fitness",
        "outfit": "a steel blue matching woven-knit shorts set — relaxed shorts and a matching fitted crewneck pullover",
        "hair": "loose high bun, imperfect and easy",
        "makeup": "barely-there makeup",
        "accessories": "white crew socks and sneakers implied",
    },
    # ------------------------------------------------------------------ STREET / ERRAND
    {
        "category": "street",
        "outfit": "mid-wash vintage straight-leg jeans with a slight fade at the knee and a cropped chocolate brown faux-leather jacket over a simple white fitted tee",
        "hair": "loose waves down, natural movement",
        "makeup": "defined brow, nude gloss",
        "accessories": "small gold hoops, mini leather crossbody bag",
    },
    {
        "category": "street",
        "outfit": "black baggy cargo pants with multiple pockets and a fitted heather-gray long-sleeve ribbed top",
        "hair": "low loose bun with face-framing pieces",
        "makeup": "skin-first, tinted gloss",
        "accessories": "dark brown baseball cap, small black bag",
    },
    {
        "category": "street",
        "outfit": "light gray jogger-style jeans with a relaxed fit and an oversized camel sherpa-lined jacket worn open over a white ribbed crop tee",
        "hair": "side-parted voluminous waves",
        "makeup": "soft glam, peachy cheek",
        "accessories": "small gold studs, canvas tote",
    },
    {
        "category": "street",
        "outfit": "dark-wash slim-fit jeans and a fitted black ribbed turtleneck under a long open camel trench coat",
        "hair": "sleek high ponytail, pulled tight",
        "makeup": "defined brow, mauve lip",
        "accessories": "black leather gloves implied",
    },
    {
        "category": "street",
        "outfit": "stone-gray wide-leg jeans with a slight taper at the ankle, a washed white graphic baby tee, and a light-wash denim overshirt worn unbuttoned",
        "hair": "half-up messy bun with face pieces",
        "makeup": "mascara and lip balm",
        "accessories": "white sneakers",
    },
    {
        "category": "street",
        "outfit": "cobalt blue wide-leg jeans and a fitted white quarter-zip pullover with a thin white puffer vest layered over it",
        "hair": "loose second-day waves, slight windblown texture",
        "makeup": "barely-there, fresh",
        "accessories": "white wireless earbuds",
    },
    {
        "category": "street",
        "outfit": "tan linen wide-leg trousers with a natural crease and a fitted black-and-white horizontal-stripe long-sleeve",
        "hair": "relaxed braid over one shoulder",
        "makeup": "soft brow, clear gloss",
        "accessories": "woven basket bag, small gold hoops",
    },
    {
        "category": "street",
        "outfit": "high-waisted black faux-leather leggings and a soft ivory oversized mock-neck ribbed knit sweater",
        "hair": "sleek low ponytail, clean",
        "makeup": "defined brow, nude lip",
        "accessories": "caramel brown shoulder bag, black ankle boots implied",
    },
    {
        "category": "street",
        "outfit": "medium-wash wide-leg jeans and a fitted off-white ribbed tank with an open olive-green military-style field jacket over it",
        "hair": "loose textured waves, parted slightly off-center",
        "makeup": "barely-there, natural",
        "accessories": "small gold chain, canvas tote",
    },
    {
        "category": "street",
        "outfit": "rust-brown corduroy wide-leg pants and a cream fitted long-sleeve ribbed crop top",
        "hair": "low messy bun, casual and easy",
        "makeup": "warm-toned soft glam — bronzed cheek, warm nude lip",
        "accessories": "small gold hoop earrings, tan lace-up boots implied",
    },
    {
        "category": "street",
        "outfit": "all-black athleisure errand look — form-fit flare leggings, a fitted cropped zip hoodie, and clean black sneakers",
        "hair": "high ponytail, clean and polished",
        "makeup": "mascara only",
        "accessories": "small black sporty crossbody",
    },
    {
        "category": "street",
        "outfit": "black straight-cut mom jeans and a fitted white scoop-neck tee under an oversized tan faux-leather biker jacket",
        "hair": "slightly wavy, middle part, down",
        "makeup": "soft glam, peachy gloss",
        "accessories": "small gold hoops, mini shoulder bag",
    },
    {
        "category": "street",
        "outfit": "dark navy wide-leg sailor-style trousers with gold-tone button details and a fitted white-and-navy thin horizontal-stripe ribbed top",
        "hair": "low loose ponytail, clean",
        "makeup": "soft natural makeup, coral gloss",
        "accessories": "loafers implied",
    },
    {
        "category": "street",
        "outfit": "faded khaki cargo trousers with side pockets and a fitted washed-gray long-sleeve crop tee",
        "hair": "textured half-up half-down, slightly undone",
        "makeup": "bare skin, no product",
        "accessories": "backwards black cap, white minimalist sneakers",
    },
    {
        "category": "street",
        "outfit": "denim-on-denim: dark-wash fitted straight-leg jeans and a lighter-wash oversized cropped denim jacket with a simple white fitted tee underneath",
        "hair": "loose second-day waves, natural and easy",
        "makeup": "mascara and lip balm",
        "accessories": "thin gold chain",
    },
    # ------------------------------------------------------------------ GOING OUT / EVENING
    {
        "category": "going_out",
        "outfit": "a fitted chocolate-brown satin mini dress with thin straps and a subtle cowl neckline",
        "hair": "sleek blow-out with volume, falls just past the shoulders",
        "makeup": "full soft glam — soft cat liner, peachy gloss, warm blush",
        "accessories": "small gold hoops, strappy heeled sandals implied",
    },
    {
        "category": "going_out",
        "outfit": "a cream silky bias-cut midi slip dress with a subtle V-neck and a thin fine-knit cardigan draped over the shoulders",
        "hair": "loose romantic waves, voluminous",
        "makeup": "soft glam, nude satin lip",
        "accessories": "layered gold chains, low kitten heels implied",
    },
    {
        "category": "going_out",
        "outfit": "a black fitted bodycon mini dress in a stretchy ribbed knit with a square neckline",
        "hair": "high voluminous ponytail, sleek at the roots",
        "makeup": "defined liner, deep berry lip",
        "accessories": "gold ring stack, small evening clutch",
    },
    {
        "category": "going_out",
        "outfit": "a dusty sage green going-out co-ord — a fitted halter top and matching high-waist wide-leg shorts in a silky fabric",
        "hair": "second-day waves with a slight crease, pulled over one shoulder",
        "makeup": "peachy glam, mascara, light blush",
        "accessories": "gold hoops",
    },
    {
        "category": "going_out",
        "outfit": "a midnight navy satin slip skirt (midi length) and a fitted off-white silk-look button-front top tucked in smoothly",
        "hair": "sleek low bun, precise and polished",
        "makeup": "dramatic mascara, nude liner, gloss",
        "accessories": "delicate gold necklace",
    },
    {
        "category": "going_out",
        "outfit": "a burnt orange fitted scoop-neck knit mini dress with a slight stretch and a clean straight hem",
        "hair": "voluminous loose curls, full and bouncy",
        "makeup": "warm glam — bronzed eye, terracotta lip",
        "accessories": "small gold hoops, thin gold anklet",
    },
    {
        "category": "going_out",
        "outfit": "a cream lace bodysuit with a scoop neck tucked into high-waisted black tailored trousers with a wide leg",
        "hair": "loose romantic curls falling down",
        "makeup": "natural glam, champagne shimmer eye",
        "accessories": "layered gold chains",
    },
    {
        "category": "going_out",
        "outfit": "a forest green sleek cowl-neck midi dress in a fluid jersey, fitted through the bodice with a soft drape",
        "hair": "half-up with gentle curls falling",
        "makeup": "smoky brown eye, nude gloss",
        "accessories": "diamond-look stud earrings",
    },
    {
        "category": "going_out",
        "outfit": "an ivory off-shoulder fitted mini dress with a slight ruffle at the hem in a stretch cotton-blend",
        "hair": "freshly styled loose waves",
        "makeup": "soft dewy glam, soft pink lip",
        "accessories": "thin gold body chain, small hoops",
    },
    {
        "category": "going_out",
        "outfit": "a cobalt blue form-fitting long-sleeve mini dress in a stretch ribbed knit",
        "hair": "sleek middle-part blow-out, straight",
        "makeup": "bold liner, nude lip",
        "accessories": "gold hoops, thin strap heeled sandals implied",
    },
    {
        "category": "going_out",
        "outfit": "a black faux-leather high-waist mini skirt and a fitted black spaghetti-strap top",
        "hair": "loose voluminous curls",
        "makeup": "defined eye, deep red lip",
        "accessories": "layered gold chains, gold ring stack, small hoop",
    },
    {
        "category": "going_out",
        "outfit": "a taupe fitted mock-neck knit midi dress in a soft ribbed fabric",
        "hair": "side-swept voluminous blow-out",
        "makeup": "soft glam — glow, defined brow, pink mauve lip",
        "accessories": "gold chain bracelet",
    },
    {
        "category": "going_out",
        "outfit": "a dusty pink lace-trim satin cami top tucked into matching wide-leg satin trousers in a fluid ivory-blush tone",
        "hair": "loose romantic waves, soft",
        "makeup": "dewy glam, soft pink gloss",
        "accessories": "small gold studs",
    },
    {
        "category": "going_out",
        "outfit": "a chocolate brown velvet mini skirt and a fitted caramel ribbed long-sleeve top with a subtle scoop neck",
        "hair": "high soft ponytail with a few strands framing the face",
        "makeup": "copper-brown eye, nude satin lip",
        "accessories": "gold hoop earrings",
    },
    {
        "category": "going_out",
        "outfit": "a sleek black blazer dress belted at the waist with a thin gold chain belt, worn with nothing underneath",
        "hair": "high sleek ponytail with volume at the crown",
        "makeup": "strong glam — liner, glossy lip, structured blush",
        "accessories": "strappy heeled sandals implied",
    },
    # ------------------------------------------------------------------ CREATOR / WORK
    {
        "category": "creator",
        "outfit": "an oversized soft lavender vintage crewneck sweatshirt and black fitted biker shorts",
        "hair": "messy top-knot bun, slightly lopsided",
        "makeup": "no makeup, natural creator morning look",
        "accessories": "iced drink implied nearby",
    },
    {
        "category": "creator",
        "outfit": "cream wide-leg linen trousers and a thin navy ribbed tank with an open cream linen cardigan draped loosely over",
        "hair": "relaxed low bun with face-framing pieces",
        "makeup": "soft natural, light mascara, tinted gloss",
        "accessories": "small gold studs, AirPods",
    },
    {
        "category": "creator",
        "outfit": "loose gray marl sweatpants and a fitted charcoal long-sleeve crop top in a soft cotton",
        "hair": "high messy bun, casual",
        "makeup": "mascara only",
        "accessories": "layered thin gold necklaces",
    },
    {
        "category": "creator",
        "outfit": "a washed sage green oversized graphic tee tucked loosely into the waistband of light gray biker shorts",
        "hair": "half-up loose twist, natural texture",
        "makeup": "barely-there skin-forward look",
        "accessories": "single thin gold ring",
    },
    {
        "category": "creator",
        "outfit": "beige corduroy wide-leg trousers and a fitted white ribbed turtleneck",
        "hair": "sleek low ponytail, clean",
        "makeup": "defined brow, nude gloss",
        "accessories": "thin gold chain, small gold hoops",
    },
    {
        "category": "creator",
        "outfit": "black high-waist athletic leggings and an oversized denim blue crewneck sweatshirt with a slightly worn cuff",
        "hair": "high bun with flyaways, relaxed",
        "makeup": "bare skin, no product",
        "accessories": "AirPods or phone visible",
    },
    {
        "category": "creator",
        "outfit": "a soft rose matching lounge two-piece — a boxy short-sleeve crop top and wide-leg matching trousers in a modal blend",
        "hair": "loose second-day waves, down and easy",
        "makeup": "tinted SPF and mascara only",
        "accessories": "small gold hoop",
    },
    {
        "category": "creator",
        "outfit": "a fitted forest green long-sleeve ribbed top and high-waist light-wash jeans with a slight flare",
        "hair": "relaxed side braid, undone at the end",
        "makeup": "soft glam, warm peach lip",
        "accessories": "small gold hoops, canvas tote visible",
    },
    {
        "category": "creator",
        "outfit": "an oversized vintage washed crewneck tee with a faded graphic, tied at the corner, and high-waist black straight-leg jeans",
        "hair": "low messy bun with face-framing pieces falling forward",
        "makeup": "mascara and nude gloss",
        "accessories": "gold ring stack",
    },
    {
        "category": "creator",
        "outfit": "a dusty blue oversized quarter-zip pullover and beige high-waist wide-leg tailored trousers",
        "hair": "loose textured waves, down",
        "makeup": "barely-there, natural skin",
        "accessories": "small gold hoop, laptop bag implied",
    },
    {
        "category": "creator",
        "outfit": "a pale yellow cotton button-down shirt worn open over a fitted white tank, half-tucked into mid-wash straight-leg jeans",
        "hair": "loose half-up half-down, soft waves",
        "makeup": "soft brow, peachy gloss",
        "accessories": "white sneakers",
    },
    {
        "category": "creator",
        "outfit": "a black ribbed scoop-neck long-sleeve top and light gray tailored jogger-style trousers with a clean hem",
        "hair": "sleek low ponytail, pulled back",
        "makeup": "soft defined makeup, warm blush",
        "accessories": "slim gold watch, small gold hoops",
    },
]

OUTFITS = [s["outfit"] for s in STYLE_BANK]


def pick_style(rng=None) -> dict:
    """Return a random STYLE_BANK entry using the given RNG (or a fresh one)."""
    _rng = rng if rng is not None else random.Random()
    return _rng.choice(STYLE_BANK)


_WARDROBE_CATALOG_CACHE: dict | None = None


def load_wardrobe_catalog() -> dict:
    global _WARDROBE_CATALOG_CACHE
    if _WARDROBE_CATALOG_CACHE is None:
        _WARDROBE_CATALOG_CACHE = json.loads(
            WARDROBE_CATALOG_PATH.read_text(encoding="utf-8")
        )
    return _WARDROBE_CATALOG_CACHE


CATALOG_PUBLIC_BLOCKED_RISK_TAGS = {
    "body_hide_risk",
    "identity_drift_risk",
    "gymwear_drift_risk",
    "lingerie_risk",
    "public_context_risk",
    "leggings_public_risk",
    "biker_shorts_risk",
}

CATALOG_PUBLIC_BLOCKED_TERMS = [
    "bralette",
    "bra",
    "lingerie",
    "underwear",
    "bikini",
    "bandeau",
    "puffer vest",
    "hoodie",
    "sweatshirt",
]

PUBLIC_ONLY_LINGERIE_DRIFT_TERMS = [
    "lace-trim",
    "lace trim",
    "lace-inset",
    "lace inset",
]

LANE_STYLE_LANE_ALLOWLIST = {
    "morning apartment": {"cozy", "elevated_casual"},
    "late kitchen snack": {"cozy", "elevated_casual"},
    "apartment doorway": {"elevated_casual", "going_out"},
    "coffee shop": {"elevated_casual", "street"},
    "rainy street": {"street", "elevated_casual"},
    "rooftop sunset": {"going_out", "elevated_casual"},
    "bookstore": {"street", "elevated_casual"},
    "car moment": {"going_out", "elevated_casual"},
    "night out": {"going_out"},
    "skincare evening": {"elevated_casual"},
    "laundry day": {"cozy", "elevated_casual", "street"},
    "museum afternoon": {"elevated_casual", "street"},
    "flower shop": {"street", "elevated_casual"},
    "record store": {"street", "elevated_casual"},
    "mirror outfit check": {"going_out", "elevated_casual", "cozy"},
    "city bench": {"street", "elevated_casual"},
    "elevator moment": {"going_out", "elevated_casual"},
    "dinner booth": {"going_out", "elevated_casual"},
    "wine bar patio": {"going_out", "elevated_casual"},
    "brunch patio": {"going_out", "elevated_casual", "street"},
    "sidewalk dinner": {"going_out", "elevated_casual"},
    "lobby cocktail bar": {"going_out", "elevated_casual"},
}

LANE_WARDROBE_PRODUCTION_ALLOWLIST: dict[str, set[str]] = {
    "morning apartment": {"apartment_elevated"},
    "late kitchen snack": {"apartment_elevated"},
    "apartment doorway": {"apartment_elevated", "mirror_fitcheck", "street_glam", "going_out"},
    "mirror outfit check": {"mirror_fitcheck", "apartment_elevated", "going_out"},
    "skincare evening": {"beauty_selfie_vanity", "apartment_elevated"},
    "coffee shop": {"cafe_styled", "street_glam"},
    "bookstore": {"cafe_styled", "street_glam"},
    "brunch patio": {"street_glam", "cafe_styled", "going_out"},
    "flower shop": {"street_glam"},
    "record store": {"street_glam"},
    "museum afternoon": {"cafe_styled", "street_glam"},
    "city bench": {"street_glam"},
    "laundry day": {"apartment_elevated"},
    "car moment": {"car_elevator", "going_out"},
    "elevator moment": {"car_elevator", "going_out"},
    "rooftop sunset": {"rooftop_night_city", "going_out"},
    "night out": {"going_out", "editorial_flash"},
    "dinner booth": {"going_out"},
    "wine bar patio": {"going_out"},
    "sidewalk dinner": {"going_out", "street_glam"},
    "lobby cocktail bar": {"going_out"},
    "gym cooldown": {"gym_glam"},
}

LANE_CAPTURE_LOGIC = {
    "apartment doorway": "Capture source: candid friend-shot from a few feet away in the hall, natural eye-height perspective.",
    "coffee shop": "Capture source: candid friend-shot from a nearby seat or counter edge, clearly a real human-taken photo rather than an impossible floating camera.",
    "rainy street": "Capture source: handheld candid shot by a friend standing on the sidewalk, believable street-photo timing.",
    "rooftop sunset": "Capture source: real friend-shot candid from a nearby standing position, not a drone or impossible overhead angle.",
    "bookstore": "Capture source: quiet candid photo taken by a friend across the aisle at normal standing height.",
    "car moment": "Capture source: phone propped on the dashboard or driver-side console timer, with a believable in-car angle and no invisible photographer.",
    "night out": "Capture source: candid friend-shot near the venue entrance or just inside the room, clearly human-taken and never dependent on a mirror gimmick.",
    "skincare evening": "Capture source: bathroom mirror or counter-level phone timer shot with clear home-bathroom logic.",
    "laundry day": "Capture source: candid friend-shot from the laundromat aisle at normal standing height.",
    "museum afternoon": "Capture source: candid friend-shot from a few feet away in the gallery, natural visitor perspective.",
    "flower shop": "Capture source: candid friend-shot on the sidewalk outside the storefront, natural standing perspective.",
    "record store": "Capture source: candid friend-shot from the next aisle over, natural documentary angle.",
    "mirror outfit check": "Capture source: candid getting-ready photo from a friend standing nearby; avoid phone-forward mirror grammar and keep the face readable.",
    "city bench": "Capture source: candid friend-shot from the sidewalk a few feet away, believable street-life perspective.",
    "elevator moment": "Capture source: candid hallway or elevator-bank photo from a friend a few feet away, never a reflection gimmick or mirror selfie.",
    "dinner booth": "Capture source: friend-shot from across the table, with an obvious seated restaurant perspective and no impossible floating angle.",
    "wine bar patio": "Capture source: candid friend-shot from the adjacent chair or standing beside the table, natural nightlife perspective.",
    "brunch patio": "Capture source: friend-shot from the other side of the brunch table or just beside it, clearly human-taken and socially plausible.",
    "sidewalk dinner": "Capture source: candid friend-shot from a few steps away on the sidewalk, natural city-night timing.",
    "lobby cocktail bar": "Capture source: candid friend-shot from across the small bar table, believable phone-camera composition in low light.",
}

SOCIAL_PRIORITY_LANES = {
    "coffee shop",
    "rooftop sunset",
    "car moment",
    "night out",
    "mirror outfit check",
    "elevator moment",
    "dinner booth",
    "wine bar patio",
    "brunch patio",
    "sidewalk dinner",
    "lobby cocktail bar",
}


def choose_scene_production(scene_pool: list[dict], rng: random.Random) -> dict:
    bank = load_photo_scene_bank()
    priority_lanes = {
        str(item).strip().lower()
        for item in bank.get("social_priority_lanes", [])
        if str(item).strip()
    } or SOCIAL_PRIORITY_LANES
    weighted: list[dict] = []
    for scene in scene_pool:
        lane = str(scene.get("lane") or "").strip().lower()
        weight = 4 if lane in priority_lanes else 1
        weighted.extend([scene] * weight)
    return rng.choice(weighted or scene_pool)


def public_capture_lock(lane: str) -> str:
    if lane not in PUBLIC_SOCIAL_LANES:
        return ""
    return (
        "Public-scene lock: this must read as a normal real-world human-taken social photo, not a selfie. "
        "Do not put a phone in Lena's hand or in the foreground unless the scene explicitly requires a phone. "
        "Do not use mirror-selfie grammar, front-camera framing, or an arm-extended selfie pose."
    )


def public_wardrobe_continuity_lock(entry: dict, lane: str) -> str:
    if lane not in PUBLIC_SOCIAL_LANES:
        return ""
    prompt = str(entry.get("prompt") or "").lower()
    if "dress" in prompt:
        return (
            "Dress continuity lock: keep the specified dress as one continuous real public dress with full bodice continuity. "
            "No bra-top reinterpretation, no triangle-bikini bodice drift, no separated top-and-skirt reading, "
            "no exposed underbust, and no exposed midriff created by garment splitting."
        )
    if "bodysuit" in prompt:
        return (
            "Bodysuit continuity lock: keep the named bodysuit as a real one-piece torso garment tucked into the waistband. "
            "The fabric must stay continuous from neckline through the torso into the jeans, skirt, or trousers, with full side coverage. "
            "Do not reinterpret it as a bra top, sports bra, cropped tank, bra-band silhouette, or floating hem above the waistband. "
            "No exposed underbust, no exposed stomach, and no fake two-piece separation unless the catalog explicitly names a crop top."
        )
    if (
        "skirt" in prompt
        and any(token in prompt for token in ["top", "halter", "tank", "tee", "shirt", "blouse", "cami", "knit", "sweater"])
        and "crop" not in prompt
        and "cropped" not in prompt
    ):
        lock = (
            "Skirt-set continuity lock: keep the named top and skirt as two real separate garments. "
            "The top must stay full-length to the waistband unless the catalog explicitly names a crop top. "
            "The skirt must keep its stated fabric, visible waistband, and named hem length instead of turning into a dress, leggings, or a generic bodycon tube skirt. "
            "Do not expose underbust or stomach by shrinking the top, and do not swap denim or structured skirt fabric into soft knit shapewear-looking material."
        )
        if catalog_outfit_is_sleeveless_top_skirt_set(entry):
            # Single self-contained sentence on purpose: the executor's compaction
            # step splits on sentence boundaries, and a reserved floor can only
            # reliably key on one marker matching one whole sentence. Keeping the
            # prohibition list in the same sentence as the "Garment-obedience lock:"
            # marker guarantees they survive or drop together.
            lock += (
                " Garment-obedience lock: the named sleeveless top must remain the visible top garment exactly as specified, "
                "and must not be substituted with a sweater, turtleneck, blouse, cardigan, jacket, blazer, coat, or scarf, "
                "or replaced with long sleeves or a high neckline."
            )
        return lock
    if (
        "shorts" in prompt
        and any(token in prompt for token in ["top", "one-shoulder", "one shoulder", "tank", "tee", "shirt", "blouse", "cami", "knit", "sweater"])
        and "bike shorts" not in prompt
        and "biker shorts" not in prompt
    ):
        return (
            "Shorts-set continuity lock: keep the named top and shorts as two real separate garments. "
            "The top must keep its intended neckline and stay full-length to the waistband unless a crop top is explicitly named. "
            "The shorts must read as real public shorts with the stated rise, pleats, waistband, and hem shape instead of turning into bike shorts, shapewear shorts, underwear, or hot pants."
        )
    if catalog_outfit_has_outerwear_shell(entry):
        if catalog_outfit_public_outerwear_needs_underlayer(entry):
            return (
                "Outerwear continuity lock: the coat, trench, blazer, jacket, cardigan, or overshirt must have a real fitted full-length top underneath. "
                "Add a simple opaque waistband-length top if the catalog text did not name one. "
                "The underlayer must cover underbust, stomach, and navel, and must never read as a bra, bralette, bandeau, bikini top, or micro-crop."
            )
        return (
            "Outerwear continuity lock: keep the named underlayer as a real opaque public top under the outerwear. "
            "The top must stay full-length to the waistband and cover underbust, stomach, and navel. "
            "Do not reinterpret the underlayer as a bra, bralette, bandeau, bikini top, or micro-crop."
        )
    if (
        any(token in prompt for token in ["top", "halter", "tank", "tee", "shirt", "blouse", "cami", "knit", "sweater"])
        and "crop" not in prompt
        and "cropped" not in prompt
    ):
        return (
            "Top continuity lock: keep the named top as real public clothing with its intended neckline, shoulder treatment, and full torso coverage to the waistband. "
            "Do not reinterpret it as a bra top, bikini-like top, cropped sweater, micro-crop, or lingerie-coded garment."
        )
    return (
        "Public outfit continuity lock: keep the specified garment classes as real public clothing. "
        "Do not reinterpret them as lingerie, a bra top, swimwear, shapewear, or a half-dressed look."
    )


def catalog_outfit_silhouette_class(entry: dict | None) -> str:
    prompt = _catalog_prompt_lower(entry)
    if "dress" in prompt:
        if "maxi dress" in prompt:
            return "maxi_dress"
        if "midi dress" in prompt:
            return "midi_dress"
        return "mini_or_short_dress"
    if "bodysuit" in prompt:
        return "bodysuit_denim_or_bottoms"
    if "maxi skirt" in prompt:
        return "maxi_skirt_set"
    if "midi skirt" in prompt:
        return "midi_skirt_set"
    if "mini skirt" in prompt:
        return "mini_skirt_set"
    if "jeans" in prompt or "denim" in prompt:
        return "jeans_based"
    if "trousers" in prompt or "wide-leg" in prompt:
        return "trouser_based"
    if "shorts" in prompt:
        return "tailored_shorts_set"
    if "leggings" in prompt:
        return "athleisure_or_lounge"
    if "tank" in prompt or "halter" in prompt or "strapless" in prompt or "one-shoulder" in prompt or "off-shoulder" in prompt:
        return "statement_top"
    return "other_modern_fashion"


def _prompt_has_visible_public_torso_garment(prompt: str) -> bool:
    lower = prompt.lower()
    if any(term in lower for term in VISIBLE_TORSO_GARMENT_TERMS):
        return True
    if any(term in lower for term in OUTER_LAYER_ONLY_TERMS):
        return (
            any(term in lower for term in ("over a", "over an", "over the", "with a", "with an", "layered over"))
            and any(term in lower for term in ("cami", "tank", "tee", "shirt", "blouse", "dress", "sweater", "knit"))
        )
    return False


def _public_sexy_bias_weight(entry: dict) -> int:
    prompt = str(entry.get("prompt", "")).lower()
    score = 1
    primary_hits = sum(1 for term in SEXY_PUBLIC_PRIMARY_TERMS if term in prompt)
    secondary_hits = sum(1 for term in SEXY_PUBLIC_SECONDARY_TERMS if term in prompt)
    safe_hits = sum(1 for term in TOO_SAFE_PUBLIC_TERMS if term in prompt)

    score += primary_hits * 3
    score += secondary_hits * 2
    score -= safe_hits * 4

    modern_variety_terms = [
        "bodysuit", "jeans", "trousers", "maxi skirt", "midi skirt", "mini skirt",
        "tank top", "halter", "one-shoulder", "off-shoulder", "strapless",
        "corset-style fashion top", "mesh sleeves", "cardigan worn buttoned",
        "leather mini skirt", "denim maxi skirt", "cargo maxi skirt",
        "knee-high boots", "sneakers", "ankle boots",
    ]
    score += sum(2 for term in modern_variety_terms if term in prompt)

    if "dress" in prompt:
        score += 1
    if "mini" in prompt:
        score += 2
    if "fitted" in prompt:
        score += 2
    if "scoop-neck" in prompt or "square-neck" in prompt or "v-neck" in prompt:
        score += 2
    if "corporate" in prompt or "office" in prompt or "businesslike" in prompt:
        score -= 8

    return max(1, score)


# Visual Hook / Allure Gate (2026-07-08, minimal additive pass): the wardrobe
# catalog's own body_visibility/coverage_level/style_lane fields already exist
# on every entry but were never read by selection -- only style_lane's
# allowlist/blocklist role and risk_tags/status were consulted. This adds a
# small additive weight bonus using that already-authored data, universally
# across every lane (not just PUBLIC_SOCIAL_LANES, unlike
# _public_sexy_bias_weight above). Weights against, never hard-bans --
# existing safety filters (rejected/high_risk status, blocked risk tags,
# blocked terms) remain the only exclusion mechanism; this function can only
# shift the odds within the already-safe candidate pool.
def _body_visibility_hook_weight(entry: dict) -> int:
    weight = 0
    body_visibility = entry.get("body_visibility")
    if body_visibility == "full_body":
        weight += 3
    elif body_visibility == "three_quarter":
        weight += 2
    elif body_visibility == "waist_to_head":
        weight -= 2
    if entry.get("coverage_level") == "partial":
        weight += 2
    if entry.get("style_lane") in {"going_out", "street"}:
        weight += 1
    return weight


LANE_SCENE_FIT_ALLOWLIST: dict[str, set[str]] = {
    "morning apartment": {"apartment_morning"},
    "late kitchen snack": {"apartment_morning", "skincare_evening"},
    "apartment doorway": {"apartment_morning", "mirror_fitcheck", "street", "errand"},
    "mirror outfit check": {"mirror_fitcheck", "apartment_morning"},
    "coffee shop": {"coffee_shop"},
    "brunch patio": {"coffee_shop", "street", "dinner_social"},
    "flower shop": {"street", "errand"},
    "record store": {"street", "errand"},
    "museum afternoon": {"street", "errand", "campus"},
    "laundry day": {"apartment_morning", "errand"},
    "car moment": {"street", "errand", "night_out", "dinner_social"},
    "wine bar patio": {"night_out", "dinner_social"},
    "lobby cocktail bar": {"night_out", "dinner_social"},
    "rooftop sunset": {"night_out", "dinner_social"},
    "gym cooldown": {"gym"},
}

LANE_OCCASION_ALLOWLIST: dict[str, set[str]] = {
    "morning apartment": {"apartment", "daily"},
    "late kitchen snack": {"apartment"},
    "apartment doorway": {"apartment", "daily", "street"},
    "mirror outfit check": {"apartment", "daily"},
    "coffee shop": {"daily", "street"},
    "brunch patio": {"daily", "going_out", "dinner_social"},
    "flower shop": {"daily", "street", "errand"},
    "record store": {"daily", "street", "errand"},
    "museum afternoon": {"daily", "street"},
    "laundry day": {"apartment", "daily"},
    "car moment": {"daily", "street", "night_out", "dinner_social"},
    "wine bar patio": {"night_out", "dinner_social", "going_out"},
    "lobby cocktail bar": {"night_out", "dinner_social", "going_out"},
    "rooftop sunset": {"night_out", "dinner_social", "going_out"},
    "gym cooldown": {"gym"},
}


def _outfit_matches_lane_context(entry: dict, lane: str) -> bool:
    scene_fit = {str(item).strip() for item in entry.get("scene_fit", []) if str(item).strip()}
    occasion = str(entry.get("occasion") or "").strip()

    allowed_scene_fit = LANE_SCENE_FIT_ALLOWLIST.get(lane, set())
    allowed_occasion = LANE_OCCASION_ALLOWLIST.get(lane, set())

    if allowed_scene_fit and scene_fit:
        if scene_fit.intersection(allowed_scene_fit):
            return True
        if occasion and occasion in allowed_occasion:
            return True
        return False

    if allowed_occasion and occasion:
        return occasion in allowed_occasion

    return True


def pick_catalog_outfit_production(lane: str, reference_mode: str = "upper_body", rng=None) -> dict:
    _rng = rng if rng is not None else random.Random()
    catalog = load_wardrobe_catalog()
    allowed_style_lanes = LANE_STYLE_LANE_ALLOWLIST.get(
        lane, {"going_out", "elevated_casual", "street"}
    )
    preferred_production_lanes = LANE_WARDROBE_PRODUCTION_ALLOWLIST.get(lane, set())
    safe_candidates = []
    preferred_candidates = []
    for entry in catalog.get("outfits", []):
        if entry.get("status") in {"rejected", "high_risk"}:
            continue
        if not _outfit_matches_lane_context(entry, lane):
            continue
        if entry.get("style_lane") not in allowed_style_lanes:
            continue
        if any(tag in CATALOG_PUBLIC_BLOCKED_RISK_TAGS for tag in entry.get("risk_tags", [])):
            continue
        prompt = str(entry.get("prompt", ""))
        lower = prompt.lower()
        if any(term in lower for term in CATALOG_PUBLIC_BLOCKED_TERMS):
            continue
        if lane in PUBLIC_SOCIAL_LANES and any(term in lower for term in PUBLIC_ONLY_LINGERIE_DRIFT_TERMS):
            continue
        if lane in PUBLIC_SOCIAL_LANES and reference_mode == "upper_body":
            if not _prompt_has_visible_public_torso_garment(prompt):
                continue
        safe_candidates.append(entry)
        if str(entry.get("production_lane") or "").strip() in preferred_production_lanes:
            preferred_candidates.append(entry)

    candidate_source = preferred_candidates if preferred_candidates else safe_candidates
    safe_pool = []
    for entry in candidate_source:
        weight = 1
        if lane in PUBLIC_SOCIAL_LANES:
            weight = _public_sexy_bias_weight(entry)
        elif str(entry.get("production_lane") or "").strip() in preferred_production_lanes:
            weight += 2
        # Visual Hook / Allure Gate (2026-07-08): additive, applies to every
        # lane, never zeroes out a candidate -- floored at 1 below.
        weight += _body_visibility_hook_weight(entry)
        weight = max(1, weight)
        safe_pool.extend([entry] * weight)

    if not safe_pool:
        raise SystemExit(
            f"[ABORT] pick_catalog_outfit_production: no safe wardrobe catalog entries remain for lane '{lane}'."
        )

    return _rng.choice(safe_pool)


_PRODUCTION_EXCLUDE_CATEGORIES = {"cozy", "fitness", "creator", "street"}
_PRODUCTION_BLOCKED_TERMS = [
    "hoodie", "jogger", "joggers", "sweatpants",
    "pajama", "pajamas", "biker shorts", "bike shorts",
    "bralette", "bodysuit", "jumpsuit",
    "quarter-zip", "turtleneck", "mock-neck", "mock neck",
    "puffer vest", "sports bra", "baby tee", "crop tee", "crop top",
    "cropped zip hoodie", "worn open over", "nothing underneath",
    "cropped ", "slightly cropped", "tank", "sleeveless", "spaghetti-strap", "spaghetti strap",
]

ROOT = Path(__file__).resolve().parents[2]
WARDROBE_CATALOG_PATH = (
    ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_wardrobe_catalog_v1.json"
)
ENVIRONMENT_CATALOG_PATH = (
    ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_environment_catalog_v1.json"
)
PHOTO_SCENE_BANK_PATH = (
    ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_photo_scene_bank_v1.json"
)
EXPRESSION_GAZE_BANK_PATH = (
    ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_expression_gaze_bank_v1.json"
)
FRAME_LOGIC_BANK_PATH = (
    ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_frame_logic_bank_v1.json"
)
POSE_BODY_LANGUAGE_BANK_PATH = (
    ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_pose_body_language_bank_v1.json"
)
KLING_WORKORDERS_ROOT = ROOT / "pipeline" / "kling_workorders"

_PHOTO_SCENE_BANK_CACHE: dict | None = None
_ENVIRONMENT_CATALOG_CACHE: dict | None = None
_PROMPT_SOURCE_VALIDATED = False


def load_photo_scene_bank() -> dict:
    global _PHOTO_SCENE_BANK_CACHE
    if _PHOTO_SCENE_BANK_CACHE is None:
        if not PHOTO_SCENE_BANK_PATH.exists():
            raise SystemExit(
                f"[ABORT] Saved photo scene bank missing: {PHOTO_SCENE_BANK_PATH}"
            )
        _PHOTO_SCENE_BANK_CACHE = json.loads(
            PHOTO_SCENE_BANK_PATH.read_text(encoding="utf-8")
        )
    return _PHOTO_SCENE_BANK_CACHE


def get_production_scene_pool() -> tuple[list[dict], dict]:
    bank = load_photo_scene_bank()
    blocked = {
        str(item).strip().lower()
        for item in bank.get("production_blocked_lanes", [])
        if str(item).strip()
    }
    scenes = [
        dict(scene)
        for scene in bank.get("scenes", [])
        if str(scene.get("lane") or "").strip().lower() not in blocked
    ]
    return scenes, bank


# --- Expression/gaze diversity layer (2026-07-07) ----------------------------
#
# Adds controlled variety to facial performance (expression, camera-relationship
# gaze, head/pose cue) without touching identity. Deliberately kept separate from
# scene selection: each scene's "action" field still describes the physical pose
# and setting-specific business, but no longer has to also carry the *only*
# expression/gaze the render will ever use for that lane. This layer supplies one
# additional short line, filtered by a lane-compatibility tag so it never
# contradicts the scene's own action (e.g. never pairs a low-motion sink/skincare
# beat with "caught mid-laugh"), and avoided against whatever expression_gaze_id
# was used on the most recent real workorders on disk so nearby slots don't repeat
# the same performance.

_EXPRESSION_GAZE_BANK_CACHE: dict | None = None

# Compatibility tags: "calm_quiet" (still/low-motion, indoor-personal beats),
# "candid_playful" (everyday errands/social, light motion), "going_out_social"
# (dressed-up dining/nightlife/social lanes), "in_motion" (walking/transit/mid-step
# lanes). A lane may allow more than one tag; a combo may be tagged with more than
# one tag. This mirrors the existing LANE_STYLE_LANE_ALLOWLIST /
# LANE_ENVIRONMENT_ALLOWLIST pattern already used for wardrobe/environment
# selection, applied here to keep expression/gaze from fighting the scene's action.
LANE_EXPRESSION_TAG_ALLOWLIST: dict[str, set[str]] = {
    "morning apartment": {"calm_quiet", "candid_playful"},
    "apartment doorway": {"in_motion", "candid_playful"},
    "coffee shop": {"candid_playful"},
    "rainy street": {"in_motion"},
    "rooftop sunset": {"going_out_social", "candid_playful"},
    "bookstore": {"calm_quiet"},
    "grocery run": {"candid_playful"},
    "car moment": {"calm_quiet"},
    "studio desk": {"calm_quiet"},
    "night out": {"going_out_social"},
    "dinner booth": {"going_out_social"},
    "wine bar patio": {"going_out_social"},
    "brunch patio": {"going_out_social", "candid_playful"},
    "sidewalk dinner": {"going_out_social", "in_motion"},
    "lobby cocktail bar": {"going_out_social"},
    "skincare evening": {"calm_quiet"},
    "airport day": {"in_motion"},
    "gym cooldown": {"calm_quiet"},
    "laundry day": {"candid_playful", "calm_quiet"},
    "museum afternoon": {"calm_quiet"},
    "late kitchen snack": {"candid_playful"},
    "flower shop": {"candid_playful"},
    "record store": {"candid_playful"},
    "mirror outfit check": {"calm_quiet", "going_out_social"},
    "city bench": {"calm_quiet", "candid_playful"},
    "elevator moment": {"in_motion", "calm_quiet"},
}
DEFAULT_EXPRESSION_TAGS = {"calm_quiet", "candid_playful", "going_out_social", "in_motion"}

# How many of the most recent real workorder slots (across the most recent dated
# folders under pipeline/kling_workorders/) to scan when avoiding a repeat
# expression_gaze_id. Small and cheap -- reads real on-disk artifacts, no new
# persistent state file.
EXPRESSION_RECENCY_LOOKBACK_SLOTS = 6
EXPRESSION_RECENCY_LOOKBACK_DATES = 5


def load_expression_gaze_bank() -> dict:
    global _EXPRESSION_GAZE_BANK_CACHE
    if _EXPRESSION_GAZE_BANK_CACHE is None:
        if not EXPRESSION_GAZE_BANK_PATH.exists():
            raise SystemExit(
                f"[ABORT] Saved expression/gaze bank missing: {EXPRESSION_GAZE_BANK_PATH}"
            )
        _EXPRESSION_GAZE_BANK_CACHE = json.loads(
            EXPRESSION_GAZE_BANK_PATH.read_text(encoding="utf-8")
        )
    return _EXPRESSION_GAZE_BANK_CACHE


def _recent_expression_gaze_ids(
    lookback_dates: int = EXPRESSION_RECENCY_LOOKBACK_DATES,
    lookback_slots: int = EXPRESSION_RECENCY_LOOKBACK_SLOTS,
) -> set[str]:
    """Read-only scan of the most recent real daily_workorders.json files already
    on disk for whatever expression_gaze_id each slot's metadata recorded. Returns
    an empty set if none found or the workorders root doesn't exist yet -- this
    must never hard-fail prompt generation just because history is thin."""
    if not KLING_WORKORDERS_ROOT.exists():
        return set()

    date_dirs = sorted(
        (p for p in KLING_WORKORDERS_ROOT.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )[:lookback_dates]

    seen: list[str] = []
    for date_dir in date_dirs:
        manifest_path = date_dir / "daily_workorders.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for slot in manifest.get("slots", []):
            metadata = slot.get("metadata") if isinstance(slot.get("metadata"), dict) else {}
            expression_gaze_id = str(metadata.get("expression_gaze_id") or "").strip()
            if expression_gaze_id:
                seen.append(expression_gaze_id)

    # Most-recent-first; keep only the lookback window.
    return set(seen[-lookback_slots:]) if seen else set()


# Visual Hook / Allure Gate (2026-07-08, pose/expression attitude follow-up):
# every expression/gaze combo now carries an attitude_level field
# (neutral/moderate/high). This is an additive weight bonus only, same
# pattern as _body_visibility_hook_weight()/_environment_allure_weight()
# added in the wardrobe/environment weighting patch -- it never excludes an
# entry, it only shifts the odds within the already tag/lane-filtered pool.
ATTITUDE_LEVEL_WEIGHT_BONUS = {"neutral": 0, "moderate": 2, "high": 4}


def _expression_attitude_weight(entry: dict) -> int:
    return 1 + ATTITUDE_LEVEL_WEIGHT_BONUS.get(str(entry.get("attitude_level") or "neutral"), 0)


def choose_expression_gaze_production(
    rng: random.Random,
    lane: str | None = None,
    recent_used: set[str] | None = None,
) -> dict:
    """Selects one expression/gaze/head-pose combo. Filters by lane-compatibility
    tag (so it never contradicts the scene's own action) and, when possible,
    avoids whatever expression_gaze_id was used on nearby recent slots. Falls
    back gracefully (recency filter relaxed, then tag filter relaxed) rather than
    hard-failing production over cosmetic variety. Weights toward higher
    attitude_level entries additively (see _expression_attitude_weight) --
    never hard-bans neutral entries."""
    bank = load_expression_gaze_bank()
    combos = [dict(c) for c in bank.get("combos", [])]
    if not combos:
        raise SystemExit(f"[ABORT] Expression/gaze bank has no combos: {EXPRESSION_GAZE_BANK_PATH}")

    allowed_tags = LANE_EXPRESSION_TAG_ALLOWLIST.get(str(lane or "").strip().lower(), DEFAULT_EXPRESSION_TAGS)
    tag_filtered = [
        c for c in combos
        if allowed_tags.intersection(set(c.get("compatibility_tags") or []))
    ] or combos

    recent_used = recent_used if recent_used is not None else _recent_expression_gaze_ids()
    non_recent = [c for c in tag_filtered if c.get("expression_gaze_id") not in recent_used]

    pool = non_recent or tag_filtered
    weighted = []
    for entry in pool:
        weighted.extend([entry] * _expression_attitude_weight(entry))
    return rng.choice(weighted or pool)


def format_expression_gaze_line(entry: dict) -> str:
    text = _clean_sentence_fragment(entry.get("text", ""))
    if not text:
        return ""
    return f"Expression: {text}."


def load_environment_catalog() -> dict:
    global _ENVIRONMENT_CATALOG_CACHE
    if _ENVIRONMENT_CATALOG_CACHE is None:
        _ENVIRONMENT_CATALOG_CACHE = json.loads(
            ENVIRONMENT_CATALOG_PATH.read_text(encoding="utf-8")
        )
    return _ENVIRONMENT_CATALOG_CACHE


LANE_ENVIRONMENT_ALLOWLIST: dict[str, set[str]] = {
    "morning apartment": {"apartment_elevated"},
    "late kitchen snack": {"apartment_elevated"},
    "apartment doorway": {"apartment_elevated", "going_out"},
    "mirror outfit check": {"mirror_fitcheck"},
    "skincare evening": {"beauty_selfie_vanity", "apartment_elevated"},
    "coffee shop": {"street_glam"},
    "brunch patio": {"street_glam", "going_out"},
    "bookstore": {"street_glam"},
    "flower shop": {"street_glam"},
    "record store": {"street_glam"},
    "museum afternoon": {"street_glam"},
    "city bench": {"street_glam"},
    "grocery run": {"street_glam"},
    "airport day": {"street_glam", "editorial_flash"},
    "rainy street": {"street_glam", "editorial_flash"},
    "rooftop sunset": {"rooftop_night_city"},
    "night out": {"going_out", "editorial_flash"},
    "dinner booth": {"going_out"},
    "wine bar patio": {"going_out"},
    "sidewalk dinner": {"going_out", "street_glam"},
    "lobby cocktail bar": {"going_out"},
    "car moment": {"car_elevator"},
    "elevator moment": {"car_elevator"},
    "gym cooldown": {"gym_glam"},
    "laundry day": {"apartment_elevated"},
}


def _clean_sentence_fragment(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" .,;:")


# Visual Hook / Allure Gate (2026-07-08, minimal additive pass): every
# environment catalog entry already carries a rich, hand-authored "mood"
# field (e.g. "city night energy, main character, going-out social"), but
# choose_environment_production() never read it -- selection was a flat,
# unweighted rng.choice() over the lane-allowed pool. This adds an additive
# weight bonus for moods matching allure/confidence/going-out language,
# mirroring the same weighted-pool pattern choose_scene_production() already
# uses for social_priority_lanes. Nightlife/rooftop/lounge/patio moods are
# explicitly INCLUDED in the keyword list (weighted toward, not away from) --
# per doctrine, nightlife/social settings are not risky, they are a strong
# allure signal.
ENVIRONMENT_ALLURE_MOOD_KEYWORDS = (
    "main character", "confident", "going-out", "going out", "glam",
    "editorial", "body as hero", "outfit as hero", "fashion", "rooftop",
    "city-night", "city night", "lounge", "date-night", "date night", "patio",
)


def _environment_allure_weight(entry: dict) -> int:
    mood = str(entry.get("mood") or "").lower()
    hits = sum(1 for keyword in ENVIRONMENT_ALLURE_MOOD_KEYWORDS if keyword in mood)
    return 1 + min(hits, 3) * 2


def choose_environment_production(scene: dict, rng: random.Random) -> dict | None:
    catalog = load_environment_catalog()
    lane = str(scene.get("lane") or "").strip().lower()
    allowed_lanes = LANE_ENVIRONMENT_ALLOWLIST.get(lane, set())
    pool = []
    for entry in catalog.get("environments", []):
        if str(entry.get("status") or "").lower() == "rejected":
            continue
        production_lane = str(entry.get("production_lane") or "").strip()
        if allowed_lanes and production_lane not in allowed_lanes:
            continue
        pool.append(entry)
    if not pool:
        raise SystemExit(
            f"[ABORT] No active environment catalog candidates remain for scene lane '{lane}'."
        )
    weighted = []
    for entry in pool:
        weighted.extend([entry] * _environment_allure_weight(entry))
    return dict(rng.choice(weighted or pool))


def build_environment_prompt_parts(scene: dict, env_entry: dict | None) -> tuple[str, str]:
    scene_environment = _clean_sentence_fragment(scene.get("environment", ""))
    scene_details = _clean_sentence_fragment(scene.get("details", ""))

    # Keep one coherent world per render.
    # The saved scene bank already defines both the place and the scene-detail grammar.
    # Do not inject extra environment-catalog realism text here, because it can collide
    # with the actual scene lane and produce mixed-location prompts.
    return scene_environment, scene_details


# --- Frame-logic layer (2026-07-07) ------------------------------------------
#
# Adds explicit scene-coherence "frame logic" per lane: a clarifying action beat,
# concrete supporting/forbidden objects, a camera-intent line, and a coherence
# note, folded into one short paragraph inserted into the final image prompt so
# every render is a specific believable moment, not just "Lena in a place."
# Deliberately does not restate or override the scene bank's own "action" field --
# it clarifies and supports whatever beat that scene already describes, per lane,
# via lena_frame_logic_bank_v1.json. Body-visibility wording is derived here from
# the already-chosen reference_mode (face_detail/upper_body/full_body/video_body)
# rather than stored per-lane, so it always matches the actual framing decision
# for this slot instead of a static guess.

_FRAME_LOGIC_BANK_CACHE: dict | None = None


def load_frame_logic_bank() -> dict:
    global _FRAME_LOGIC_BANK_CACHE
    if _FRAME_LOGIC_BANK_CACHE is None:
        if not FRAME_LOGIC_BANK_PATH.exists():
            raise SystemExit(
                f"[ABORT] Saved frame-logic bank missing: {FRAME_LOGIC_BANK_PATH}"
            )
        _FRAME_LOGIC_BANK_CACHE = json.loads(
            FRAME_LOGIC_BANK_PATH.read_text(encoding="utf-8")
        )
    return _FRAME_LOGIC_BANK_CACHE


BODY_VISIBILITY_RULE_BY_REFERENCE_MODE: dict[str, str] = {
    "full_body": (
        "Body visibility: keep bust, waist, hips, and upper thighs visible and "
        "unobstructed by any prop; do not let a bag, jacket, or framing choice "
        "intentionally hide her waist-to-thigh silhouette."
    ),
    "upper_body": (
        "Body visibility: keep bust and waist clearly visible; hips may fall "
        "outside a waist-up crop naturally, but do not add a prop specifically "
        "to block them."
    ),
    "face_detail": (
        "Body visibility: not the priority in this close framing; do not force "
        "full-body content, and do not use any prop to obscure her face, "
        "neckline, or shoulders."
    ),
    "video_body": (
        "Body visibility: keep bust, waist, and upper hips visible enough to "
        "support stable motion continuity across the clip."
    ),
}

SEATED_OR_TABLE_OCCLUSION_NOTE = (
    "This scene is seated or leaning at furniture; hips and thighs may be "
    "naturally out of view behind a table, desk, or bench -- that is acceptable "
    "and is not a coverage violation. Do not add any extra prop beyond that "
    "furniture to hide the waist or hips further."
)


def choose_frame_logic(lane: str) -> dict:
    """Read-only lookup of the frame-logic bank entry for `lane`, falling back to
    the bank's own default entry if the lane is missing. Never hard-fails
    production over a missing lane -- every currently active production lane is
    covered, and the default keeps the paragraph coherent for any future one."""
    bank = load_frame_logic_bank()
    lanes = bank.get("lanes", {})
    entry = lanes.get(str(lane or "").strip().lower())
    if not entry:
        entry = bank.get("default_frame_logic", {})
    return dict(entry)


def build_body_visibility_rule(reference_mode: str, frame_logic: dict) -> str:
    rule = BODY_VISIBILITY_RULE_BY_REFERENCE_MODE.get(
        reference_mode, BODY_VISIBILITY_RULE_BY_REFERENCE_MODE["upper_body"]
    )
    if frame_logic.get("seated_or_table_occlusion_ok"):
        rule = f"{rule} {SEATED_OR_TABLE_OCCLUSION_NOTE}"
    return rule


def format_frame_logic_paragraph(frame_logic: dict, reference_mode: str) -> str:
    action = _clean_sentence_fragment(frame_logic.get("frame_action", ""))
    evidence = [
        str(item).strip() for item in frame_logic.get("frame_evidence_objects", [])
        if str(item).strip()
    ]
    forbidden = [
        str(item).strip() for item in frame_logic.get("frame_forbidden_objects", [])
        if str(item).strip()
    ]
    camera_intent = _clean_sentence_fragment(frame_logic.get("camera_intent", ""))
    coherence_note = _clean_sentence_fragment(frame_logic.get("scene_coherence_note", ""))
    body_rule = build_body_visibility_rule(reference_mode, frame_logic)

    sentences = []
    if action:
        sentences.append(f"Frame logic: {action}.")
    if evidence:
        sentences.append(f"Supporting objects in frame: {', '.join(evidence)}.")
    if camera_intent:
        sentences.append(f"Camera intent: {camera_intent}.")
    if body_rule:
        sentences.append(body_rule)
    if forbidden:
        sentences.append(f"Avoid: {', '.join(forbidden)}.")
    if coherence_note:
        sentences.append(f"This should read as {coherence_note}.")

    return " ".join(sentences)


# --- Pose/body-language rotation layer (2026-07-08) --------------------------
#
# Adds controlled variety to physical stance/body language so nearby renders
# don't all repeat the same weight-square-on "model pose." Modeled directly on
# the expression/gaze layer above: one short "Pose: ..." line, filtered by lane
# compatibility (LANE_POSE_TAG_ALLOWLIST) and by the already-chosen
# reference_mode, with a recency guard against nearby real workorders. Never
# restates or overrides the scene bank's own "action" field -- it is a
# lightweight physical-stance modifier layered on top of whatever the scene's
# action already describes, the same relationship frame logic has to Scene:.
# Per the approved audit + compaction-simulation report, entries are kept short
# (target 50-80 chars, hard max ~90) specifically because the compaction
# budget was already tight before this layer existed.

_POSE_BODY_LANGUAGE_BANK_CACHE: dict | None = None

# Lane -> physical-compatibility tags this lane supports, beyond the always-
# allowed "universal" tag (every lane implicitly allows "universal" combos).
# Grounded directly in the real per-lane scene action text (lena_photo_scene_
# bank_v1.json) and the frame-logic bank's seated_or_table_occlusion_ok flags,
# not guessed: "seated" = the scene action itself says sitting/seated;
# "leaning_ok" = the scene action already has her leaning against counter/
# railing/appliance, or the setting plainly supports it without hiding her
# waist; "low_hand_risk" = a scene where a small reach/adjust gesture is
# already contextually normal (drink, laptop, menu, records, bag); "in_motion"
# = the scene action itself is already walking, not standing/seated.
LANE_POSE_TAG_ALLOWLIST: dict[str, set[str]] = {
    "morning apartment": set(),
    "apartment doorway": {"in_motion"},
    "coffee shop": {"leaning_ok", "low_hand_risk"},
    "rainy street": {"in_motion"},
    "rooftop sunset": {"leaning_ok"},
    "bookstore": set(),
    "grocery run": {"low_hand_risk"},
    "car moment": {"seated"},
    "studio desk": {"seated", "low_hand_risk"},
    "night out": set(),
    "dinner booth": {"seated", "low_hand_risk"},
    "wine bar patio": {"leaning_ok"},
    "brunch patio": {"seated", "low_hand_risk"},
    "sidewalk dinner": {"in_motion"},
    "lobby cocktail bar": {"seated", "low_hand_risk"},
    "skincare evening": set(),
    "airport day": {"in_motion"},
    "gym cooldown": {"seated"},
    "laundry day": {"leaning_ok"},
    "museum afternoon": set(),
    "late kitchen snack": {"leaning_ok"},
    "flower shop": set(),
    "record store": {"low_hand_risk"},
    "mirror outfit check": set(),
    "city bench": {"seated", "low_hand_risk"},
    "elevator moment": set(),
}

# Same lookback shape as the expression/gaze recency guard -- read-only scan
# of real on-disk daily_workorders.json files, no new persistent state file.
POSE_RECENCY_LOOKBACK_SLOTS = 6
POSE_RECENCY_LOOKBACK_DATES = 5


def load_pose_body_language_bank() -> dict:
    global _POSE_BODY_LANGUAGE_BANK_CACHE
    if _POSE_BODY_LANGUAGE_BANK_CACHE is None:
        if not POSE_BODY_LANGUAGE_BANK_PATH.exists():
            raise SystemExit(
                f"[ABORT] Saved pose/body-language bank missing: {POSE_BODY_LANGUAGE_BANK_PATH}"
            )
        _POSE_BODY_LANGUAGE_BANK_CACHE = json.loads(
            POSE_BODY_LANGUAGE_BANK_PATH.read_text(encoding="utf-8")
        )
    return _POSE_BODY_LANGUAGE_BANK_CACHE


def _recent_pose_ids(
    lookback_dates: int = POSE_RECENCY_LOOKBACK_DATES,
    lookback_slots: int = POSE_RECENCY_LOOKBACK_SLOTS,
) -> set[str]:
    """Read-only scan of the most recent real daily_workorders.json files already
    on disk for whatever pose_body_language_id each slot's metadata recorded.
    Returns an empty set if none found -- must never hard-fail prompt
    generation just because history is thin. Mirrors
    _recent_expression_gaze_ids() exactly."""
    if not KLING_WORKORDERS_ROOT.exists():
        return set()

    date_dirs = sorted(
        (p for p in KLING_WORKORDERS_ROOT.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )[:lookback_dates]

    seen: list[str] = []
    for date_dir in date_dirs:
        manifest_path = date_dir / "daily_workorders.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for slot in manifest.get("slots", []):
            metadata = slot.get("metadata") if isinstance(slot.get("metadata"), dict) else {}
            pose_id = str(metadata.get("pose_body_language_id") or "").strip()
            if pose_id:
                seen.append(pose_id)

    return set(seen[-lookback_slots:]) if seen else set()


# Visual Hook / Allure Gate (2026-07-08, pose/expression attitude follow-up):
# every pose/body-language combo now carries an attitude_level field
# (neutral/moderate/high), same additive-weight pattern as
# _expression_attitude_weight() above -- never excludes an entry, only shifts
# the odds within the already tag/mode/recency-filtered pool.
def _pose_attitude_weight(entry: dict) -> int:
    return 1 + ATTITUDE_LEVEL_WEIGHT_BONUS.get(str(entry.get("attitude_level") or "neutral"), 0)


def choose_pose_body_language_production(
    rng: random.Random,
    lane: str | None = None,
    reference_mode: str | None = None,
    recent_used: set[str] | None = None,
) -> dict:
    """Selects one pose/body-language combo. Filters by lane-compatibility tag
    (never contradicts the scene's own action -- e.g. never picks a seated pose
    for a lane whose action is walking) and by reference_mode (never picks a
    walking/seated full-body pose for a face_detail close crop). Falls back
    gracefully (recency relaxed, then reference_mode relaxed, then tag relaxed)
    rather than hard-failing production over cosmetic variety -- same pattern
    as choose_expression_gaze_production(). Weights toward higher
    attitude_level entries additively (see _pose_attitude_weight) -- never
    hard-bans neutral entries."""
    bank = load_pose_body_language_bank()
    combos = [dict(c) for c in bank.get("combos", [])]
    if not combos:
        raise SystemExit(f"[ABORT] Pose/body-language bank has no combos: {POSE_BODY_LANGUAGE_BANK_PATH}")

    allowed_tags = LANE_POSE_TAG_ALLOWLIST.get(str(lane or "").strip().lower(), set()) | {"universal"}
    tag_filtered = [
        c for c in combos
        if allowed_tags.intersection(set(c.get("compatibility_tags") or []))
    ] or combos

    mode_filtered = [
        c for c in tag_filtered
        if str(reference_mode or "") in (c.get("reference_mode_tags") or [])
    ] or tag_filtered

    recent_used = recent_used if recent_used is not None else _recent_pose_ids()
    non_recent = [c for c in mode_filtered if c.get("pose_body_language_id") not in recent_used]

    pool = non_recent or mode_filtered
    weighted = []
    for entry in pool:
        weighted.extend([entry] * _pose_attitude_weight(entry))
    return rng.choice(weighted or pool)


def format_pose_body_language_line(entry: dict) -> str:
    text = _clean_sentence_fragment(entry.get("text", ""))
    if not text:
        return ""
    return f"Pose: {text}."


def validate_saved_prompt_sources() -> None:
    global _PROMPT_SOURCE_VALIDATED
    if _PROMPT_SOURCE_VALIDATED:
        return

    bank = load_photo_scene_bank()
    scenes = bank.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        raise SystemExit("[ABORT] Saved photo scene bank has no scenes.")
    blocked_lanes = {
        str(item).strip().lower()
        for item in bank.get("production_blocked_lanes", [])
        if str(item).strip()
    }

    required_scene_keys = ("lane", "action", "environment", "details", "camera", "lighting", "caption")
    missing_scene_fields = []
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise SystemExit(f"[ABORT] Scene bank entry #{idx} is not an object.")
        for key in required_scene_keys:
            if not str(scene.get(key) or "").strip():
                missing_scene_fields.append(f"{scene.get('lane', f'index_{idx}')}:{key}")

    if missing_scene_fields:
        preview = ", ".join(missing_scene_fields[:10])
        raise SystemExit(
            f"[ABORT] Saved photo scene bank has incomplete scenes: {preview}"
        )

    env_catalog = load_environment_catalog()
    env_entries = [
        entry for entry in env_catalog.get("environments", [])
        if str(entry.get("status") or "").lower() != "rejected"
    ]
    if not env_entries:
        raise SystemExit("[ABORT] Environment catalog has no active entries.")

    missing_lane_mappings = []
    empty_environment_lanes = []
    for scene in scenes:
        lane = str(scene.get("lane") or "").strip().lower()
        if lane in blocked_lanes:
            continue
        allowed = LANE_ENVIRONMENT_ALLOWLIST.get(lane)
        if not allowed:
            missing_lane_mappings.append(lane)
            continue
        candidates = [
            entry for entry in env_entries
            if str(entry.get("production_lane") or "").strip() in allowed
        ]
        if not candidates:
            empty_environment_lanes.append(lane)

    if missing_lane_mappings:
        raise SystemExit(
            "[ABORT] Missing lane->environment mapping for saved scenes: "
            + ", ".join(sorted(set(missing_lane_mappings)))
        )

    if empty_environment_lanes:
        raise SystemExit(
            "[ABORT] Environment catalog has no active matches for scene lanes: "
            + ", ".join(sorted(set(empty_environment_lanes)))
        )

    _PROMPT_SOURCE_VALIDATED = True


def pick_style_production(rng=None) -> dict:
    """Production-safe STYLE_BANK draw.

    Excludes cozy/fitness categories and outfits with blocked terms.
    Target categories: elevated_casual, street, going_out, creator.
    """
    _rng = rng if rng is not None else random.Random()
    pool = [
        s for s in STYLE_BANK
        if s.get("category") not in _PRODUCTION_EXCLUDE_CATEGORIES
        and not any(
            term.lower() in s.get("outfit", "").lower()
            for term in _PRODUCTION_BLOCKED_TERMS
        )
    ]
    if not pool:
        raise SystemExit(
            "[ABORT] pick_style_production: filtered pool is empty -- "
            "no production-safe STYLE_BANK entries remain"
        )
    return _rng.choice(pool)


def get_production_style_pool() -> list[dict]:
    return [
        s for s in STYLE_BANK
        if s.get("category") not in _PRODUCTION_EXCLUDE_CATEGORIES
        and not any(
            term.lower() in s.get("outfit", "").lower()
            for term in _PRODUCTION_BLOCKED_TERMS
        )
    ]


def max_production_style_override_len() -> int:
    pool = get_production_style_pool()
    if not pool:
        raise SystemExit(
            "[ABORT] max_production_style_override_len: "
            "no production-safe STYLE_BANK entries remain"
        )
    return max(len(format_style_override(entry)) for entry in pool)


def format_style_override(entry: dict) -> str:
    """Return wardrobe-override prompt line for BodyLock generation.

    Prevents the model from defaulting to the anchor/reference image outfit.
    Inject this into the positive prompt before the scene description.
    """
    return (
        "Wardrobe override — do not reproduce the clothing or styling from the "
        "reference image; the complete look for this image is: "
        f"{entry['outfit']}. "
        f"Hair: {entry['hair']}. "
        f"Makeup: {entry['makeup']}. "
        f"Accessories: {entry['accessories']}. "
        "All wardrobe details are fully specified here — follow the prompt, "
        "not the reference image clothing."
    )


def _format_catalog_wardrobe_override_legacy(entry: dict) -> str:
    """Clothes-only wardrobe override for catalog entries.

    Catalog entries have no hair or makeup fields by design.
    Identity, face, hair, body, and skin tone come from the
    approved character element and reference images only.
    """
    return (
        "Wardrobe override — use this catalog outfit for clothing only: "
        f"{entry['prompt']}. "
        "If the outfit is a dress, it must render as one continuous "
        "one-piece dress from neckline to hem, not a separate top, "
        "not a separate skirt, with the waist area fully covered. "
        "Lena's face, hair, body, skin tone, and identity come from "
        "the approved character element/reference images, "
        "not the outfit text."
    )


def format_catalog_wardrobe_override(entry: dict) -> str:
    """Clothes-only wardrobe override for catalog entries.

    Catalog entries have no hair or makeup fields by design.
    Identity, face, hair, body, and skin tone come from the
    approved character element and reference images only.
    """
    prompt = entry["prompt"]
    lower = prompt.lower()
    fit_guard = ""
    layered_guard = ""
    outerwear_underlayer_guard = ""
    has_base_layer = any(
        token in lower
        for token in [
            "cami", "tank", "tank top", "tee", "t-shirt", "tshirt",
        ]
    )
    has_open_layer = any(
        token in lower
        for token in [
            "worn open", "layered over", "open over", "open button-down",
            "open button down", "open shirt", "open blouse",
            "field jacket over", "jacket over", "blazer over",
            "cardigan over", "draped loosely over",
        ]
    )
    if "dress" in lower:
        fit_guard = (
            "If the outfit is a dress, keep it as one continuous dress from "
            "neckline to hem, never a separated top/skirt or lingerie drift. "
        )
        if "subtle v-neck" in lower or "shallow v-neck" in lower:
            fit_guard += (
                "Keep the neckline as a modest shallow V, not a plunge, not a bra-like split, "
                "and not an exaggerated low-cut opening. "
            )
        if "long fitted sleeves" in lower or "long-sleeve" in lower or "long sleeve" in lower:
            fit_guard += (
                "Preserve the named long sleeves as actual sleeves on both arms. "
                "Do not convert the dress into halter, sleeveless, strappy, or shoulder-bare construction. "
            )
    elif "bodysuit" in lower:
        fit_guard = (
            "Keep the named bodysuit as a real one-piece garment with continuous torso coverage and a true tucked-in read at the waistband. "
            "Do not reinterpret it as a bra top, sports bra, bikini-like top, cropped tank, or floating hem above the jeans or skirt. "
            "The torso fabric must stay connected and body-conscious without exposing underbust, stomach, or a fake crop gap. "
        )
    elif (
        any(
            token in lower
            for token in [
                "top", "tee", "tank", "turtleneck", "pullover",
                "quarter-zip", "shirt", "blouse", "sweater",
                "long-sleeve", "long sleeve", "cami",
            ]
        )
        and "crop" not in lower
        and "cropped" not in lower
    ):
        fit_guard = (
            "Keep the named top's intended construction and overall coverage. "
            "Do not reinterpret it as a bra top, sports-bra-like top, "
            "bikini-like top, or underwear-like garment. The hem should read "
            "as a normal full-length everyday top that reaches the natural "
            "waistband area rather than floating high above it. Do not expose "
            "underbust, do not turn it into a bra-band silhouette, and do not "
            "shrink a normal top into an extreme micro-crop. "
        )
        if "long-sleeve" in lower or "long sleeve" in lower:
            fit_guard += (
                "Preserve the named long sleeves on both arms and keep the "
                "scoop-neck or other stated neckline modest and realistic, not "
                "strapless, halter, off-shoulder, or cut down into lingerie-like coverage. "
            )
        if "halter" in lower:
            fit_guard += (
                "If the named top is halter or high-neck, keep that neckline with open shoulders while still preserving full torso coverage to the waistband. "
                "Do not turn it into a cropped turtleneck, bra-band top, or shortened sweater. "
            )
    if has_base_layer and has_open_layer:
        layered_guard = (
            "If an open overshirt or jacket is layered over a cami, tank, or "
            "tee, the base layer must stay a real everyday top with normal "
            "side coverage and waistband-length coverage, not a bralette, "
            "bandeau, bikini top, sports bra, triangle bra, or micro-crop. "
        )
    if catalog_outfit_public_outerwear_needs_underlayer(entry):
        outerwear_underlayer_guard = (
            "If the look uses a coat, trench, blazer, jacket, cardigan, or overshirt as the main visible layer and no full base top is explicitly named, "
            "add a simple opaque fitted full-length everyday top underneath, visible as real public clothing, tucked or reaching the waistband, fully covering underbust, stomach, and navel. "
            "Never place a bra top, bralette, bandeau, bikini top, or micro-crop under public outerwear. "
        )
    return (
        "Wardrobe override — use this catalog outfit for clothing only: "
        f"{prompt}. "
        f"{fit_guard}"
        f"{layered_guard}"
        f"{outerwear_underlayer_guard}"
        "Lena's face, hair, body, skin tone, and identity come from the "
        "approved character element/reference images, not the outfit text."
    )


PHOTO_SCENES = [
    {"lane":"morning apartment","action":"standing barefoot in her kitchen while pouring coffee into a ceramic mug, glancing toward the window like she is still waking up","environment":"a lived-in apartment kitchen with warm wood shelves, a half-open linen curtain, a small bowl of oranges, and morning light sliding across the counter","details":"steam from the coffee, one loose strand of hair near her cheek, a phone face-down on the counter, soft shadows on the wall","camera":"candid editorial lifestyle photo, 50mm lens, shallow depth of field, waist-up composition","lighting":"early morning natural window light, warm highlights, gentle contrast","caption":"coffee first, personality later"},
    {"lane":"apartment doorway","action":"leaving through the apartment doorway, looking back over her shoulder with a half-smile like she almost forgot something but went anyway","environment":"a lived-in apartment entryway with a coat rack hung with jackets in the foreground, a small entry table with keys and mail, a potted plant near the door, warm interior light spilling into the hallway in the background","details":"tote bag over her shoulder, keys in one hand, a jacket draped over her arm, soft shadow from the doorframe","camera":"full-body candid lifestyle portrait, 35mm lens, natural candid framing from just outside the door","lighting":"warm apartment interior light mixing with cool hallway light, soft natural split on her face","caption":"leaving on the first try today"},
    {"lane":"coffee shop","action":"leaning against a small cafe window counter, holding an iced coffee and giving the camera a soft almost-smile like someone just made a quiet joke","environment":"a narrow neighborhood coffee shop with mismatched two-top tables and a scratched wooden pickup counter in the foreground, handwritten menu board and pastry case in the midground, condensation on the front window with blurred street and foot traffic beyond","details":"iced coffee condensation ring on the counter in the foreground, receipt and straw wrapper beside the cup, tote bag hooked on the stool, silver spoon on the saucer, soft window reflection in the glass","camera":"candid street-style cafe photo, 50mm lens, soft background blur","lighting":"cloudy daylight through glass, neutral tones, realistic skin highlights","caption":"quick coffee turned into a whole little reset"},
    {"lane":"rainy street","action":"walking across a wet city sidewalk while looking back over her shoulder, one hand holding her coat closed","environment":"a rainy downtown street with glossy pavement, blurred headlights, muted storefronts, and a dark umbrella passing behind her","details":"tiny raindrops on her coat, reflective puddles, wind lifting a few strands of hair, soft bokeh lights","camera":"handheld street photo, 85mm lens, full-body candid, natural motion blur, not cinematic grading","lighting":"overcast blue-gray daylight with warm reflections from shop windows","caption":"rain always makes errands feel more dramatic"},
    {"lane":"rooftop sunset","action":"standing near a rooftop railing at sunset, turning slightly toward the camera with relaxed confidence","environment":"a city rooftop with low lounge furniture, concrete planters, skyline in the background, and warm sunset haze","details":"gold light along her hair, subtle wind movement, glass of sparkling water on a side table, skyline softly blurred","camera":"candid outdoor portrait, 70mm lens, medium shot, shallow depth of field, natural light","lighting":"golden-hour backlight, warm rim light, soft face fill","caption":"stayed for the light"},
    {"lane":"bookstore","action":"standing between tall bookstore shelves, holding one book open while her eyes lift toward the camera","environment":"an independent bookstore with warm lamps, narrow aisles, stacked novels, wood floors, and a small reading chair in the background","details":"paper texture, a receipt tucked into the book, soft dust in the light, one hand resting on the shelf","camera":"quiet cinematic portrait, 50mm lens, natural framing through shelves","lighting":"warm indoor lamp light with soft shadows","caption":"went in for one book and immediately lied to myself"},
    {"lane":"grocery run","action":"standing beside a small grocery cart, reaching for fresh flowers while glancing down with a half-smile","environment":"a bright neighborhood market with produce crates, eucalyptus bundles, handwritten price signs, and soft morning activity behind her","details":"green stems in her hand, canvas tote bag, oranges and lemons nearby, realistic aisle clutter","camera":"documentary lifestyle photo, 35mm lens, candid mid-shot","lighting":"clean natural store light mixed with daylight from front windows","caption":"flowers were not on the list but here we are"},
    {"lane":"car moment","action":"sitting in the passenger seat of a parked car, looking out the window with one hand near her cheek","environment":"foreground dashboard and worn console details, neutral leather interior in the midground, blurred city street through rain-specked windshield in the background","details":"seatbelt strap, faint reflection on the window, lip gloss catching light, phone cable near the console","camera":"intimate candid portrait, 50mm lens from driver-side angle","lighting":"soft overcast window light, muted tones","caption":"parked for five minutes and somehow reset my whole mood"},
    {"lane":"studio desk","action":"sitting at a cluttered-but-curated desk with a laptop open, chin resting lightly on one hand, looking focused but calm, like she framed this angle on purpose","environment":"a lived-in home workspace with a large monitor in the background, scattered notebooks and sticky notes around the frame, warm desk lamp in the foreground, wall of pinned inspiration softly blurred behind","details":"tangled cable at the desk edge, sticky notes with scrawled reminders, open notebook with crossed-out lines, iced coffee condensation ring on the desk surface, laptop screen glow on her face","camera":"modern creator workspace portrait, 35mm lens, medium composition","lighting":"late afternoon window light mixed with a warm desk lamp","caption":"pretending this is organized because the lamp is cute"},
    {"lane":"night out","action":"stepping out near the entrance of a low-lit lounge, pausing with one hand at her side and a calm unreadable look toward the camera like someone caught her on the way in","environment":"a real city-night venue entrance with dark painted walls, soft doorway spill light, a host stand or velvet rope nearby, and blurred people moving behind her","details":"small clutch or mini bag, subtle jewelry highlights, scuffed sidewalk, a posted menu or sign near the door, and nightlife imperfections that feel real not staged","camera":"flash-adjacent nightlife social photo, 35mm lens, candid friend-shot composition, no mirror","lighting":"warm venue spill light mixed with city-night ambient light, realistic highlight rolloff, slight low-light grain","caption":"caught me on the way in"},
    {"lane":"dinner booth","action":"sitting in a restaurant booth with one elbow resting lightly on the table, holding a wine glass and looking calmly at the camera like the conversation just paused for a second","environment":"a busy evening bistro with dark booth seating, half-closed blinds, neon reflections in the window, and other diners blurred behind her","details":"water glass, dessert plate with a few bites left, folded napkin, menu corner, chair pattern, and subtle table clutter that feels used not staged","camera":"candid phone-camera dinner photo, 35mm lens feel, seated mid-shot from across the table","lighting":"warm restaurant practical lighting mixed with window reflections and slight low-light grain","caption":"the restaurant lighting was working harder than i was"},
    {"lane":"wine bar patio","action":"standing beside a small patio table with one hand around a stemmed glass, looking over with a soft unreadable expression like someone said her name mid-thought","environment":"a narrow city wine bar patio with metal cafe chairs, candlelight on tables, passing headlights, and a softly crowded sidewalk beyond","details":"half-finished drink, small appetizer plate, receipt folder, candle wax marks on the table, nearby people blurred in the background","camera":"nighttime candid social photo, realistic phone flash or ambient-phone capture, natural seated-standing angle from a friend nearby","lighting":"warm patio practicals, low ambient city light, believable highlight rolloff on skin and glass","caption":"just one drink and then suddenly it was a whole night"},
    {"lane":"brunch patio","action":"sitting at an outdoor brunch table with sunglasses pushed up in her hair, holding a coffee or mimosa while glancing toward the camera with a half-smile","environment":"a bright brunch patio with striped umbrellas, nearby tables, textured plates, and weekend foot traffic in soft blur behind her","details":"silverware on a folded napkin, glass water bottle, brunch plate in frame, phone face-down on the table, slight table clutter and sun patches","camera":"real social-feed brunch photo, natural friend-shot from the opposite side of the table, mid-shot with face and upper body clear","lighting":"soft daylight with mild shadow contrast, flattering but unretouched outdoor light","caption":"brunch is basically just daytime gossip with silverware"},
    {"lane":"sidewalk dinner","action":"walking away from a restaurant table set on a city sidewalk, looking back over her shoulder with one hand holding a small bag and the other brushing her hair","environment":"a lively sidewalk dining block with candlelit two-top tables, parked cars, menu stands, and warm storefront spill lighting","details":"table numbers, glassware, scuffed pavement, diners nearby, a chair pulled out awkwardly, and small imperfect venue details","camera":"candid street-night photo from a friend a few steps behind her, 35mm lens feel, natural movement","lighting":"mixed storefront glow and city-night ambient light, realistic shadow falloff, slight motion softness","caption":"stepped outside for two seconds and somehow stayed out"},
    {"lane":"lobby cocktail bar","action":"seated at a dark bar-height table, resting one hand under her jaw while the other loosely holds a cocktail glass, giving the camera a composed slightly amused look","environment":"a polished cocktail bar with low lamps, reflective dark wood, people moving in the background, and lived-in glassware on nearby tables","details":"coaster, cocktail napkin, menu tucked under one glass, ambient reflections, imperfect chair placement, subtle background patrons","camera":"low-light candid social portrait, friend-shot from across the small table, natural phone-camera framing","lighting":"warm bar light, controlled shadows, slight sensor grain, no polished ad finish","caption":"this looked more put together than the rest of my day"},
    {"lane":"skincare evening","action":"standing at a bathroom sink with a white towel around her shoulders, pressing moisturizer gently into one cheek","environment":"a calm apartment bathroom with frosted glass, a small plant, neutral stone counter, and warm mirror light","details":"dewy skin texture, tiny water droplets near the sink, open moisturizer jar, soft robe fabric","camera":"close-up beauty lifestyle portrait, 85mm lens, natural skin detail","lighting":"soft warm bathroom light, realistic highlights on skin","caption":"night routine doing the heavy lifting"},
    {"lane":"airport day","action":"walking through an airport terminal with a small suitcase, turning slightly as if someone called her name","environment":"a modern terminal with glass walls, polished floors, gate signs blurred in the background, and early morning travelers passing behind her","details":"passport wallet in hand, coffee cup in suitcase side pocket, moving walkway reflections, realistic travel fatigue","camera":"travel street-style photo, 35mm lens, full-body candid shot","lighting":"cool airport daylight mixed with overhead lighting","caption":"airport coffee counts as a personality trait"},
    {"lane":"gym cooldown","action":"sitting on a bench after a workout, tying her sneaker while looking down with a calm focused expression","environment":"a boutique fitness studio with worn rubber flooring, soft mirrors, towels stacked nearby, and sunlight from high windows","details":"slight flyaways, natural post-workout skin glow, water bottle on the floor, realistic fabric folds","camera":"candid wellness lifestyle photo, 50mm lens, low angle","lighting":"clean morning studio light, soft reflections in the mirror","caption":"the part where you just sit for a minute"},
    {"lane":"laundry day","action":"leaning against a washing machine in a quiet laundromat, folding a white tee and laughing to herself","environment":"a retro laundromat with laundry basket and folded clothes in the foreground, chrome machines in the midground, checker tile floor and fluorescent ceiling lights blurred toward the background window","details":"laundry basket, dryer glow, quarters on top of the machine, a paperback book nearby","camera":"cinematic slice-of-life photo, 35mm lens, natural candid framing","lighting":"mixed fluorescent and daylight, realistic color balance","caption":"romanticizing laundry because someone has to"},
    {"lane":"museum afternoon","action":"standing in front of a large abstract painting, arms loosely crossed, studying it with a thoughtful expression","environment":"a quiet modern art museum gallery with polished concrete floors, white walls, soft benches, and visitors blurred in the distance","details":"gallery card beside painting, soft footsteps implied, simple jewelry, calm posture","camera":"quiet handheld portrait, 50mm lens, natural museum composition, candid visitor feel","lighting":"soft museum track lighting, clean neutral tones","caption":"came for the quiet"},
    {"lane":"late kitchen snack","action":"standing in the kitchen at night, eating a strawberry over the sink and smiling like she got caught","environment":"a dim apartment kitchen with one under-cabinet light on, dark window reflection, marble counter, and a half-open fridge glow","details":"bowl of strawberries, loose hair, reflection in the window, one cabinet door slightly ajar","camera":"intimate night lifestyle photo, 50mm lens, close candid framing","lighting":"warm kitchen practical light with soft fridge glow","caption":"standing over the sink counts as dinner sometimes"},
    {"lane":"flower shop","action":"standing outside a flower shop holding a wrapped bouquet, looking down at the flowers with a soft smile","environment":"a small storefront with buckets of tulips and ranunculus, faded awning, old brick wall, and morning pedestrians blurred behind her","details":"brown paper bouquet wrap, ribbon ends, petals near the sidewalk, soft wind in her hair","camera":"candid street photo, 85mm lens, shallow background blur, natural morning light","lighting":"bright but soft morning light, gentle skin highlights","caption":"bought flowers for the apartment and maybe also for my mood"},
    {"lane":"record store","action":"flipping through vinyl records, pausing with one sleeve halfway pulled out and a curious look","environment":"a moody record shop with narrow aisles, posters on the wall, warm lamps, and stacks of albums around her","details":"fingertips on album sleeve, soft dust, vintage speakers in the background, tote bag on her shoulder","camera":"grainy candid phone photo, 35mm lens, natural side angle, warm store light","lighting":"warm low store lighting, subtle film-like grain","caption":"found three records and zero self-control"},
    {"lane":"mirror outfit check","action":"standing beside a bedroom mirror and adjusting one earring while glancing toward the camera like she is about to leave","environment":"a lived-in bedroom getting-ready corner with a mirror edge, dresser surface, draped clothes on a chair, and late afternoon light across the floor","details":"jewelry tray, boots near the wall, soft mirror dust at the edge only, and ordinary apartment clutter that keeps it human","camera":"natural getting-ready photo from a friend nearby, three-quarter composition, no full mirror dominance","lighting":"late afternoon window light, soft warm tones","caption":"almost ready and somehow still late"},
    {"lane":"city bench","action":"sitting on a city bench with one leg crossed, holding a paper coffee cup and watching people pass","environment":"a tree-lined city block, coffee cup and tote strap in the foreground, worn city bench in the midground, brownstones and parked bikes softly blurred in the background","details":"wind moving her hair, coffee lid detail, tote bag beside her, small sun patches through leaves","camera":"street-style lifestyle portrait, 85mm lens, natural candid framing","lighting":"dappled late morning sunlight, soft shadows","caption":"five quiet minutes before the day started asking for things"},
    {"lane":"elevator moment","action":"standing just outside the elevator doors with one hand on a small bag, turning slightly toward the camera with a calm unreadable expression","environment":"a real corridor outside an elevator bank with brushed metal doors, scuffed floor trim, warm overhead lights, and ordinary wall texture","details":"small bag in one hand, elevator call button panel, imperfect corridor reflections, slight motion softness from the doors","camera":"candid hallway photo from a friend a few feet away, 35mm lens, no reflection gimmick","lighting":"warm overhead corridor light with realistic shadow falloff","caption":"the hallway was doing more than the elevator"},
]

PRODUCTION_BLOCKED_LANES = {
    "late kitchen snack",
    "gym cooldown",
    "studio desk",
    "airport day",
    "grocery run",
    "apartment doorway",
    "skincare evening",
    "mirror outfit check",
    "elevator moment",
}


SCENE_EVIDENCE_CONTRACTS: dict = {
    'morning apartment': {
        'caption_intent': 'slow drowsy apartment start — coffee before anything else',
        'required_visual_evidence': [
            'kitchen or counter environment',
            'coffee mug or cup in frame',
            'morning window light visible',
            'apartment interior details',
        ],
        'forbidden_contradictions': [
            'outdoor location',
            'no beverage visible',
            'nighttime dark lighting',
            'sterile showroom kitchen',
            'bar or restaurant setting',
        ],
        'environment_realism_notes': 'warm wood surfaces, half-open curtain, morning light, small bowl of fruit or counter clutter',
        'photo_realism_notes': 'waist-up candid, shallow depth, steam from coffee, no ring light',
        'body_visibility_requirement': 'waist to head visible; arms and hands natural; mug in hand or nearby',
        'qa_rejection_criteria': [
            'no kitchen or home interior visible',
            'no beverage in frame',
            'outdoor or public setting',
            'nighttime or dark artificial lighting',
        ],
    },
    'apartment doorway': {
        'caption_intent': 'confident solo exit — rare first-try success energy',
        'required_visual_evidence': [
            'doorway or entry framing',
            'bag or tote over shoulder',
            'keys in hand or implied',
            'apartment interior light behind her',
        ],
        'forbidden_contradictions': [
            'mid-room apartment with no doorway',
            'seated or lying down',
            'outdoor street without apartment door',
            'no bag or exit prop visible',
        ],
        'environment_realism_notes': 'coat rack with worn jacket in foreground, small entry table with keys and mail, potted plant near door, hallway blurred in background',
        'photo_realism_notes': 'full-body candid from just outside door, natural split light, not over-posed',
        'body_visibility_requirement': 'full body or three-quarter; bag and outfit readable head to thigh',
        'qa_rejection_criteria': [
            'no doorway or entryway context',
            'no bag or exit prop',
            'seated apartment interior composition',
            'outdoor street without apartment door',
        ],
    },
    'coffee shop': {
        'caption_intent': 'unplanned extended coffee break — city girl reset',
        'required_visual_evidence': [
            'cafe or coffee shop interior',
            'coffee cup or iced drink in hand',
            'shop fixtures or window with street outside',
            'handwritten menu board or pastry case visible',
            'cafe environment details (receipt, bus tub, or counter clutter)',
        ],
        'forbidden_contradictions': [
            'home kitchen setting',
            'outdoor park without cafe context',
            'no drink visible',
            'library or office setting',
            'generic blank cafe with no counter or menu detail',
            'sterile showroom cafe',
            'cinematic commercial coffee ad look',
        ],
        'environment_realism_notes': 'foreground: iced coffee condensation ring, receipt, straw wrapper on counter; midground: Lena at pickup counter; background: handwritten menu board, pastry case, window condensation with blurred street beyond',
        'photo_realism_notes': '50mm handheld candid at counter, soft background blur, imperfect indoor cafe light mixed with window daylight, no ring light, slight phone-focus background blur',
        'body_visibility_requirement': 'waist-up; one hand holding drink; relaxed leaning posture',
        'qa_rejection_criteria': [
            'no cafe or coffee shop environment',
            'no beverage visible',
            'home or apartment setting',
            'outdoor-only with no shop context',
            'no counter, menu, or cafe prop visible',
            'generic or sterile cafe interior',
        ],
    },
    'rainy street': {
        'caption_intent': "outdoor errand made cinematic by rain — drama she didn't ask for",
        'required_visual_evidence': [
            'outdoor street or sidewalk',
            'wet pavement or rain-wet surfaces',
            'overcast or rain lighting',
            'city background or storefronts blurred',
            'rain-appropriate coat or clothing',
        ],
        'forbidden_contradictions': [
            'sunny bright day',
            'apartment interior',
            'gym or indoor setting',
            'dry pavement and clear sky',
            'no outdoor context',
        ],
        'environment_realism_notes': 'glossy wet pavement, blurred headlights, muted storefronts, dark umbrella passing',
        'photo_realism_notes': 'full-body handheld candid, real motion blur, rain on coat, reflective puddles, overcast natural color, no cinematic grading',
        'body_visibility_requirement': 'full body visible; coat closed; natural walking motion',
        'qa_rejection_criteria': [
            'no rain or wet surface visible',
            'sunny or bright daylight inconsistent with caption',
            'indoor or apartment location',
            'dry weather implied by caption',
        ],
    },
    'rooftop sunset': {
        'caption_intent': 'unhurried golden hour on city rooftop — lingered for the light',
        'required_visual_evidence': [
            'rooftop environment',
            'city skyline or urban view in background',
            'golden hour or warm sunset light',
            'outdoor elevated location feel',
        ],
        'forbidden_contradictions': [
            'apartment interior',
            'street level',
            'overcast gray sky',
            'nighttime without golden quality',
            'gym or indoor setting',
        ],
        'environment_realism_notes': 'concrete planters with weathered edges, worn lounge furniture, skyline background, warm sunset haze',
        'photo_realism_notes': '70mm candid outdoor portrait, warm natural rim light, shallow DOF, skyline softly blurred, no studio lighting, handheld feel',
        'body_visibility_requirement': 'medium shot; silhouette readable; golden light along hair and shoulders',
        'qa_rejection_criteria': [
            'no rooftop or elevated outdoor context',
            'no golden hour or warm light quality',
            'apartment interior setting',
            'nighttime without sunset quality',
        ],
    },
    'bookstore': {
        'caption_intent': 'browsing spiral — came for one book, browsed for an hour',
        'required_visual_evidence': [
            'bookstore environment',
            'shelves of books visible',
            'book in hand or being browsed',
            'warm lamp or bookstore lighting',
            'narrow aisle or shelf framing',
        ],
        'forbidden_contradictions': [
            'library without books for sale',
            'outdoor or street location',
            'no books visible',
            'bright studio lighting',
            'cafe without book shelves',
        ],
        'environment_realism_notes': 'warm lamps, narrow aisles, stacked novels, wood floors, reading chair blurred',
        'photo_realism_notes': '50mm quiet portrait through shelves, natural framing, warm lamp shadows',
        'body_visibility_requirement': 'waist-up or medium; book in hand; shelf depth visible behind her',
        'qa_rejection_criteria': [
            'no bookstore or book-shelf environment',
            'no book visible in frame',
            'outdoor or cafe setting',
            'institutional library rather than retail bookstore',
        ],
    },
    'grocery run': {
        'caption_intent': "spontaneous flower impulse buy mid-errand — the win she didn't plan",
        'required_visual_evidence': [
            'grocery store or market interior',
            'fresh flowers in hand or nearby',
            'produce or market items visible',
            'cart or basket nearby',
            'natural store light',
        ],
        'forbidden_contradictions': [
            'florist boutique without grocery context',
            'outdoor street without market',
            'no flowers visible',
            'apartment interior',
            'cafe setting',
        ],
        'environment_realism_notes': 'produce crates, eucalyptus bundles, handwritten price signs, realistic aisle clutter',
        'photo_realism_notes': 'documentary 35mm candid mid-shot, natural store + daylight mix',
        'body_visibility_requirement': 'waist-up minimum; hands holding flowers; tote bag on shoulder',
        'qa_rejection_criteria': [
            'no market or grocery environment',
            'no flowers in frame',
            'apartment or home setting',
            'outdoor street without market context',
        ],
    },
    'car moment': {
        'caption_intent': 'quiet reset in a parked car — micro-meditation between errands',
        'required_visual_evidence': [
            'car interior visible',
            'window light from outside',
            'seatbelt or dashboard implied',
            'neutral leather or car seat behind her',
        ],
        'forbidden_contradictions': [
            'driving or moving car',
            'outdoor street without car context',
            'apartment or home interior',
            'no car interior details',
            'public transit or bus',
        ],
        'environment_realism_notes': 'worn leather and console in foreground, soft dashboard shadows, city blurred through rain-specked glass in background',
        'photo_realism_notes': '50mm from driver-side angle, intimate, muted tones, soft overcast window light',
        'body_visibility_requirement': 'upper body visible; seatbelt natural; hand near cheek or on lap',
        'qa_rejection_criteria': [
            'no car interior visible',
            'outdoor street without car context',
            'driving situation',
            'apartment or home setting',
        ],
    },
    'studio desk': {
        'caption_intent': 'messy but aesthetic work setup — cute lamp does not equal productive',
        'required_visual_evidence': [
            'desk or workspace',
            'laptop or notebook visible',
            'desk lamp providing warm light',
            'coffee or drink nearby',
            'visible desk clutter (cables, sticky notes, scattered pens)',
            'creative work context',
        ],
        'forbidden_contradictions': [
            'outdoor or cafe without desk context',
            'bare blank table with nothing on it',
            'no laptop or work item',
            'clean empty desk without visible clutter',
            'apartment couch without desk',
            'gym or active setting',
        ],
        'environment_realism_notes': 'foreground: tangled cable, sticky notes, condensation ring; background: monitor, pinned inspiration wall blurred',
        'photo_realism_notes': '35mm candid creator portrait, late afternoon window + desk lamp mix, no ring light, handheld feel',
        'body_visibility_requirement': 'medium shot; chin resting on hand; laptop and desk surface readable',
        'qa_rejection_criteria': [
            'no desk or workspace visible',
            'no laptop or notebook or work prop',
            'outdoor or cafe-only setting',
            'standing rather than seated at desk',
        ],
    },
    'night out': {
        'caption_intent': 'pre-going-out mirror ritual at the venue — last details before the room sees you',
        'required_visual_evidence': [
            'mirror visible',
            'going-out outfit on',
            'lounge or venue restroom context',
            'warm sconce or venue lighting',
            'jewelry or makeup detail',
        ],
        'forbidden_contradictions': [
            'apartment bedroom without lounge feel',
            'casual daytime outfit',
            'bright clean bathroom',
            'hotel bathroom or hotel spa aesthetic',
            'sterile luxury restroom without lounge context',
            'no mirror in frame',
            'outdoor or street setting',
        ],
        'environment_realism_notes': 'dark marble, warm sconces, brushed brass fixtures, smudged mirror edge, used counter with lip product visible, blurred lounge doorway with nightlife noise implied beyond',
        'photo_realism_notes': 'flash-adjacent 35mm, mirror reflections, warm controlled highlights, no ring light, handheld mirror candid',
        'body_visibility_requirement': 'waist-up minimum; outfit and jewelry visible; mirror reflection present',
        'qa_rejection_criteria': [
            'no mirror visible',
            'apartment bedroom rather than lounge setting',
            'casual daytime outfit',
            'no going-out context',
        ],
    },
    'skincare evening': {
        'caption_intent': 'evening skincare ritual — the unseen work that maintains the look',
        'required_visual_evidence': [
            'bathroom environment',
            'sink or mirror visible',
            'skincare product in hand or on counter',
            'dewy or post-cleanse skin texture',
            'warm bathroom light',
        ],
        'forbidden_contradictions': [
            'outdoor or street setting',
            'gym or active setting',
            'no bathroom context',
            'no skincare product visible',
            'daytime bright light without bathroom context',
        ],
        'environment_realism_notes': 'frosted glass, small plant, neutral stone counter, warm mirror light',
        'photo_realism_notes': '85mm close-up beauty, realistic skin detail, water droplets, robe or towel fabric, no ring light, handheld bathroom feel',
        'body_visibility_requirement': 'close-up or waist-up; hands pressing product; dewy skin texture visible',
        'qa_rejection_criteria': [
            'no bathroom environment',
            'no skincare product or routine context',
            'outdoor or street setting',
            'daytime context inconsistent with night routine',
        ],
    },
    'airport day': {
        'caption_intent': 'early travel energy — tired but moving, coffee as armor',
        'required_visual_evidence': [
            'airport terminal environment',
            'gate signs or terminal architecture',
            'travel bag or suitcase',
            'coffee cup in hand or nearby',
            'travel outfit',
        ],
        'forbidden_contradictions': [
            'home or apartment interior',
            'outdoor park or street',
            'no airport context',
            'gym or casual home setting',
            'no travel prop',
        ],
        'environment_realism_notes': 'glass walls, polished floors, gate signs blurred, morning travelers passing',
        'photo_realism_notes': '35mm travel street-style, full-body candid, cool airport daylight + overhead lights',
        'body_visibility_requirement': 'full body or three-quarter; suitcase visible; travel outfit readable',
        'qa_rejection_criteria': [
            'no airport environment',
            'no travel bag or suitcase',
            'apartment or home setting',
            'outdoor non-transit location',
        ],
    },
    'gym cooldown': {
        'caption_intent': 'post-workout quiet moment — the earned rest, not the performance',
        'required_visual_evidence': [
            'gym or fitness studio environment',
            'workout or athletic outfit',
            'bench or gym surface',
            'post-workout detail (flyaways, natural glow)',
            'gym context (mirror, rubber floor, or equipment)',
        ],
        'forbidden_contradictions': [
            'outdoor park without gym context',
            'apartment interior',
            'going-out or glam outfit',
            'no gym environment',
            'pool or water setting',
        ],
        'environment_realism_notes': 'worn rubber gym flooring with scuff marks, soft mirrors, stacked towels with condensation on water bottle, sunlight from high windows',
        'photo_realism_notes': '50mm candid wellness photo, low angle, natural gym window light, no ring light, handheld feel',
        'body_visibility_requirement': 'waist-up while seated; athletic outfit visible; shoes on or tying',
        'qa_rejection_criteria': [
            'no gym or fitness environment',
            'glam outfit inconsistent with workout caption',
            'apartment or home setting',
            'no athletic or workout context',
        ],
    },
    'laundry day': {
        'caption_intent': 'making the mundane cinematic — romanticizing the boring chore',
        'required_visual_evidence': [
            'laundromat or laundry room environment',
            'washing machine or dryer visible',
            'laundry basket or clothes being folded',
            'casual comfortable outfit',
        ],
        'forbidden_contradictions': [
            'apartment bedroom without laundry context',
            'gym setting',
            'going-out or glam outfit',
            'outdoor park or cafe',
            'no laundry prop or machine',
        ],
        'environment_realism_notes': 'laundry basket and folded clothes in foreground, chrome machines in midground, checker tile floor with worn marks, fluorescent softened by daylight in background',
        'photo_realism_notes': '35mm handheld candid, natural mix of fluorescent and daylight color, no cinematic grading',
        'body_visibility_requirement': 'waist-up or three-quarter; hands folding or holding laundry; machine visible',
        'qa_rejection_criteria': [
            'no laundry machine or basket visible',
            'glam outfit inconsistent with laundry caption',
            'outdoor or cafe setting',
            'apartment room without laundry context',
        ],
    },
    'museum afternoon': {
        'caption_intent': 'solo culture afternoon — she came for the quiet, not the art',
        'required_visual_evidence': [
            'museum or gallery interior',
            'artwork or exhibit visible',
            'gallery lighting (track or soft overhead)',
            'cultural space feel',
        ],
        'forbidden_contradictions': [
            'outdoor park or street',
            'apartment interior',
            'cafe or coffee shop',
            'no artwork visible',
            'gym or active setting',
        ],
        'environment_realism_notes': 'polished concrete floors with worn sheen, white walls, soft benches, visitors blurred in distance -- foreground gallery card, background exhibit wall',
        'photo_realism_notes': '50mm handheld museum portrait, natural candid composition, soft museum track lighting, not editorial fashion',
        'body_visibility_requirement': 'standing; full or three-quarter body; painting or gallery wall behind',
        'qa_rejection_criteria': [
            'no museum or gallery environment',
            'no artwork or exhibit in frame',
            'outdoor or street setting',
            'cafe or home environment',
        ],
    },
    'late kitchen snack': {
        'caption_intent': 'too-tired-to-sit late night kitchen snack — honest and funny',
        'required_visual_evidence': [
            'kitchen environment',
            'food visible (bowl, plate, or snack item)',
            'sink or counter in frame',
            'low dim late-night kitchen lighting',
            'lived-in counter details',
        ],
        'forbidden_contradictions': [
            'outdoor scene',
            'bright daytime kitchen',
            'no food visible',
            'sterile showroom kitchen',
            'formal dining or restaurant setting',
            'going-out or glam outfit',
        ],
        'environment_realism_notes': 'under-cabinet light, dark window reflection, marble counter, half-open fridge glow',
        'photo_realism_notes': '50mm intimate night lifestyle, close candid, warm practical light and fridge glow',
        'body_visibility_requirement': 'waist-up; food in hand or bowl nearby; leaning posture over counter or sink',
        'qa_rejection_criteria': [
            'no kitchen or food visible',
            'bright outdoor or daytime lighting',
            'no counter or sink in frame',
            'formal dining or restaurant setting',
            'glam going-out outfit',
        ],
    },
    'flower shop': {
        'caption_intent': "impulse flower buy — the self-care that's also home care",
        'required_visual_evidence': [
            'flower shop exterior or street florist context',
            'wrapped bouquet or flowers in hand',
            'outdoor street or storefront',
            'morning soft light',
        ],
        'forbidden_contradictions': [
            'apartment interior without shop context',
            'grocery store interior',
            'no flowers visible',
            'gym or active setting',
            'nighttime or dark scene',
        ],
        'environment_realism_notes': 'buckets of tulips and ranunculus, faded awning, old brick wall, morning pedestrians blurred',
        'photo_realism_notes': '85mm candid street photo, shallow background blur, bright soft morning light, no ring light, handheld natural feel',
        'body_visibility_requirement': 'three-quarter or full body; flowers clearly held; shop exterior behind',
        'qa_rejection_criteria': [
            'no flowers visible',
            'apartment interior without shop context',
            'nighttime or dark lighting',
            'no florist or market environment',
        ],
    },
    'record store': {
        'caption_intent': 'browsing spiral in a vinyl shop — impulse buys and mood',
        'required_visual_evidence': [
            'record store or vinyl shop interior',
            'records or album sleeves in hand or nearby',
            'warm store lamp lighting',
            'narrow aisles or record racks visible',
        ],
        'forbidden_contradictions': [
            'bookstore without vinyl',
            'outdoor or street setting',
            'no records visible',
            'apartment interior',
            'bright studio or sterile space',
        ],
        'environment_realism_notes': 'moody narrow aisles in foreground, record racks and album stacks in midground, posters on wall and warm lamps in background',
        'photo_realism_notes': '35mm grainy candid phone photo, natural side angle, warm low store lighting, film grain, no ring light, handheld feel',
        'body_visibility_requirement': 'waist-up; hands on album sleeve; tote bag visible',
        'qa_rejection_criteria': [
            'no record store or vinyl shop environment',
            'no records or albums visible',
            'outdoor or street setting',
            'bookstore without vinyl context',
        ],
    },
    'mirror outfit check': {
        'caption_intent': '10-second outfit check that became 30 minutes — the mirror as obstacle',
        'required_visual_evidence': [
            'mirror visible',
            'bedroom or dressing area',
            'full outfit readable in reflection',
            'phone held low enough to see face',
            'bedroom details behind (linen, chair, clothes)',
        ],
        'forbidden_contradictions': [
            'lounge or venue mirror (night out scene)',
            'no mirror visible',
            'outdoor setting',
            'no outfit readable',
            'extremely close face-only crop with no outfit',
        ],
        'environment_realism_notes': 'standing mirror, linen bedding, clothes on chair, late afternoon light on floor',
        'photo_realism_notes': 'realistic mirror photo, natural proportions, no ring light in reflection',
        'body_visibility_requirement': 'full body in mirror; outfit from head to thigh; phone low but face visible',
        'qa_rejection_criteria': [
            'no mirror visible',
            'outdoor or public setting',
            'lounge or venue context instead of bedroom',
            'only face visible without outfit',
            'no bedroom details',
        ],
    },
    'city bench': {
        'caption_intent': 'stolen stillness on a city bench — the pause before the rush',
        'required_visual_evidence': [
            'outdoor city or park bench',
            'coffee cup in hand',
            'tree-lined street or park',
            'city environment visible',
        ],
        'forbidden_contradictions': [
            'apartment interior',
            'gym setting',
            'indoor bench or seat',
            'no coffee or drink visible',
            'nighttime without daytime context',
        ],
        'environment_realism_notes': 'worn bench in foreground, tree-lined city block in midground, brownstones and parked bikes blurred in background, early fall leaves on ground',
        'photo_realism_notes': '85mm candid handheld portrait, dappled late morning sunlight, natural street framing, no ring light',
        'body_visibility_requirement': 'waist-up seated; coffee cup in hand; legs crossed naturally visible',
        'qa_rejection_criteria': [
            'no outdoor or city environment',
            'indoor or apartment setting',
            'no coffee or drink visible',
            'nighttime without daytime context',
        ],
    },
    'elevator moment': {
        'caption_intent': 'the elevator as accidental portrait studio — found light in a mundane space',
        'required_visual_evidence': [
            'elevator interior',
            'brushed metal or mirrored elevator walls',
            'warm overhead elevator light',
            'reflection in metal panel',
        ],
        'forbidden_contradictions': [
            'stairwell without elevator context',
            'outdoor or street setting',
            'apartment room without elevator',
            'no metal or reflective surface',
            'bright full studio lighting',
        ],
        'environment_realism_notes': 'phone and handrail in foreground, brushed metal walls with smudged fingerprints in midground, overhead lights and scuffed mirrored panel in background',
        'photo_realism_notes': '35mm centered candid, warm overhead soft light, slight motion blur from elevator',
        'body_visibility_requirement': 'medium shot; hand holding small bag; elevator walls framing',
        'qa_rejection_criteria': [
            'no elevator context or metal walls',
            'outdoor or apartment setting',
            'stairwell without elevator',
            'no reflective surface visible',
        ],
    },
}

VIDEO_MOTIONS = [
    "slow 10-second video, subtle camera push-in, Lena shifts her weight naturally and gives a small real smile near the end",
    "slow 10-second handheld-style clip, tiny natural head movement, hair moving slightly, relaxed breathing, candid expression",
    "smooth 10-second cinematic motion, gentle camera drift from left to right, Lena glances away then back toward the camera",
    "10-second lifestyle reel clip, natural micro-movements in hands and face, soft environment motion in the background",
    "10-second close editorial clip, slight wind in hair, slow blink, relaxed posture, no exaggerated movement",
]

CAMERA_EXTRAS = [
    "high-end Instagram editorial style, realistic proportions, natural color grading",
    "documentary lifestyle realism, believable candid timing, not overly staged",
    "premium creator photo, subtle film grain, clean composition",
    "modern lifestyle campaign look, soft depth of field, realistic environmental detail",
    "natural candid social photo with editorial polish, detailed textures, believable body posture",
]

HASHTAG_BANK = [
    "#lifestyle", "#morninglight", "#citygirl", "#coffeemood", "#softstyle", "#streetstyle",
    "#dayinthelife", "#weekendmood", "#outfitdetails", "#quietmoments", "#apartmentlife",
    "#travelstyle", "#wellnessroutine", "#goldenhour", "#creatorlife", "#chicagostyle",
    "#neutralstyle", "#nightout", "#cafemood", "#citylights", "#everydaystyle"
]

LANE_HASHTAGS = {
    "morning apartment": ["#morninglight", "#apartmentlife", "#coffeemood", "#quietmoments", "#softstyle", "#dayinthelife", "#neutralstyle"],
    "apartment doorway": ["#outfitdetails", "#dayinthelife", "#softstyle", "#everydaystyle", "#citygirl", "#neutralstyle"],
    "coffee shop": ["#cafemood", "#coffeemood", "#citygirl", "#quietmoments", "#streetstyle", "#everydaystyle"],
    "rainy street": ["#streetstyle", "#citygirl", "#citylights", "#outfitdetails", "#everydaystyle", "#chicagostyle"],
    "rooftop sunset": ["#goldenhour", "#citylights", "#softstyle", "#outfitdetails", "#chicagostyle", "#lifestyle"],
    "bookstore": ["#quietmoments", "#dayinthelife", "#softstyle", "#everydaystyle", "#neutralstyle"],
    "grocery run": ["#dayinthelife", "#everydaystyle", "#citygirl", "#softstyle", "#quietmoments"],
    "car moment": ["#quietmoments", "#citygirl", "#dayinthelife", "#softstyle", "#everydaystyle"],
    "studio desk": ["#creatorlife", "#dayinthelife", "#quietmoments", "#softstyle", "#everydaystyle", "#neutralstyle"],
    "night out": ["#nightout", "#citylights", "#outfitdetails", "#streetstyle", "#chicagostyle"],
    "skincare evening": ["#wellnessroutine", "#quietmoments", "#apartmentlife", "#softstyle", "#nightout"],
    "airport day": ["#travelstyle", "#citygirl", "#dayinthelife", "#outfitdetails", "#everydaystyle"],
    "gym cooldown": ["#wellnessroutine", "#dayinthelife", "#softstyle", "#everydaystyle"],
    "laundry day": ["#dayinthelife", "#apartmentlife", "#everydaystyle", "#quietmoments"],
    "museum afternoon": ["#quietmoments", "#citygirl", "#softstyle", "#dayinthelife", "#neutralstyle"],
    "late kitchen snack": ["#apartmentlife", "#quietmoments", "#dayinthelife", "#softstyle"],
    "flower shop": ["#citygirl", "#softstyle", "#dayinthelife", "#streetstyle", "#quietmoments"],
    "record store": ["#citygirl", "#dayinthelife", "#softstyle", "#streetstyle"],
    "mirror outfit check": ["#outfitdetails", "#neutralstyle", "#softstyle", "#everydaystyle"],
    "city bench": ["#citygirl", "#streetstyle", "#coffeemood", "#quietmoments", "#everydaystyle"],
    "elevator moment": ["#outfitdetails", "#citygirl", "#streetstyle", "#everydaystyle"],
}


def _seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _clean_public_text(text: str) -> str:
    cleaned = text

    # Remove banned public terms only as standalone words/phrases.
    # Do not delete "ai" inside normal words like hair, details, portrait, maintain.
    for term in BANNED_PUBLIC_TERMS:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = cleaned.replace(" ,", ",").replace(" .", ".")
    return cleaned

def _hashtags(rng: random.Random, lane: str, count: int = 3) -> str:
    pool = LANE_HASHTAGS.get(lane, HASHTAG_BANK)
    count = min(count, len(pool))
    tags = rng.sample(pool, k=count)
    return " ".join(tags)



REFERENCE_MODE_POLICIES = {
    "face_detail": (
        "Reference mode: close-up face detail. Preserve Lena's facial identity, skin tone, hairline, eye shape, brows, cheekbones, mouth shape, and natural skin texture from the current Lena character element. "
        "Prioritize facial realism, hair detail, skin detail, and expression consistency."
    ),
    "upper_body": (
        "Reference mode: upper-body lifestyle. Preserve Lena's facial identity plus her upper-body proportions, shoulders, waistline, hands, posture, jewelry placement, and clothing fit from the current Lena character element. "
        "Use body proportions naturally without forcing a full-body pose."
    ),
    "full_body": (
        "Reference mode: full-body fashion/lifestyle. Preserve Lena's facial identity "
        "plus her full-body proportions, defined waist without shrinking her frame, "
        "visibly wider hips, fuller thighs, rounded lower-body silhouette, "
        "long legs, hands, feet, posture, and clothing fit from the current Lena character element. "
        "Keep her athletic-curvy proportions consistent, attractive, realistic, "
        "fully clothed, and editorial. Do not slim her down."
    ),
    "video_body": (
        "Reference mode: video continuity. Preserve Lena's facial identity, body proportions, posture, hands, legs, clothing fit, and silhouette from the current Lena character element so the seed image can animate naturally. "
        "Prioritize stable identity, stable body proportions, believable posture, and subtle realistic movement."
    ),
}


REFERENCE_PRIORITY = {
    "face_detail": ["kling_element_close_face", "kling_element_public_full_body", "kling_element_smile_upper_body"],
    "upper_body": ["kling_element_public_full_body", "kling_element_smile_upper_body", "kling_element_close_face"],
    "full_body": ["kling_element_public_full_body", "kling_element_smile_upper_body", "kling_element_relaxed_seated"],
    "video_body": ["kling_element_public_full_body", "kling_element_smile_upper_body", "kling_element_relaxed_seated"],
}


def choose_reference_mode(media_type: str, scene: dict) -> str:
    text = " ".join([
        str(media_type or ""),
        str(scene.get("lane") or ""),
        str(scene.get("action") or ""),
        str(scene.get("environment") or ""),
        str(scene.get("details") or ""),
        str(scene.get("camera") or ""),
        str(scene.get("lighting") or ""),
    ]).lower()

    if media_type == "video":
        return "video_body"

    face_terms = [
        "close-up", "close up", "beauty portrait", "skincare",
        "face detail", "headshot", "head-and-shoulders",
        "pressing moisturizer", "bathroom sink",
    ]

    full_body_terms = [
        "full-body", "full body", "head-to-toe", "walking", "standing",
        "sneakers", "boots", "feet", "shoes", "airport", "grocery cart",
        "city bench", "flower shop", "rainy street", "rooftop", "mirror outfit",
        "elevator", "laundromat", "gym", "museum", "record store",
    ]

    upper_body_terms = [
        "sitting", "seated", "desk", "cafe", "coffee shop", "kitchen",
        "bookstore", "car", "passenger seat", "laptop", "counter",
        "waist-up", "medium shot", "hands", "jewelry",
    ]

    if any(term in text for term in face_terms) and not any(term in text for term in full_body_terms):
        return "face_detail"

    if any(term in text for term in full_body_terms):
        return "full_body"

    if any(term in text for term in upper_body_terms):
        return "upper_body"

    return "upper_body"


def reference_policy_for_mode(mode: str) -> str:
    return REFERENCE_MODE_POLICIES.get(mode, REFERENCE_MODE_POLICIES["upper_body"])


def reference_priority_for_mode(mode: str) -> list[str]:
    return REFERENCE_PRIORITY.get(mode, REFERENCE_PRIORITY["upper_body"])


def framing_policy_for_mode(mode: str) -> str:
    if mode == "face_detail":
        return (
            "Framing should focus on face, hair, expression, skin texture, and close facial realism. "
            "Avoid forcing full-body composition for this mode."
        )

    if mode == "upper_body":
        return (
            "Framing should be waist-up or three-quarter lifestyle framing with natural hands, shoulders, waistline, jewelry, and clothing fit visible. "
            "Do not crop awkwardly through hands or face."
        )

    if mode == "full_body":
        return (
            "Framing should clearly show her full silhouette, outfit fit, waist-to-hip shape, legs, posture, hands, and shoes when the scene allows. "
            "Avoid cropped feet, warped legs, or wide-angle distortion."
        )

    if mode == "video_body":
        return (
            "Seed framing should show enough face, torso, posture, hands, and outfit to support stable natural motion. "
            "Avoid extreme close-ups unless the video concept specifically requires one."
        )

    return ""

def generate_prompt_package(date_str: str, slot_id: str, media_type: str, sequence_index: int | None = None) -> Dict[str, Any]:
    rng = random.Random(_seed(date_str, slot_id, media_type, str(sequence_index or "")))

    validate_saved_prompt_sources()
    production_scene_pool, scene_bank = get_production_scene_pool()
    if not production_scene_pool:
        raise SystemExit("[ABORT] No production-safe saved photo scenes remain.")

    scene = choose_scene_production(production_scene_pool, rng)
    environment_entry = choose_environment_production(scene, rng)
    environment_text, detail_text = build_environment_prompt_parts(scene, environment_entry)
    reference_mode = choose_reference_mode(media_type, scene)
    wardrobe_entry = pick_catalog_outfit_production(scene["lane"], reference_mode, rng)
    wardrobe_override = format_catalog_wardrobe_override(wardrobe_entry)
    negative_prompt = build_negative_prompt_for_catalog(wardrobe_entry)
    negative_prompt = build_public_lane_negative_prompt(wardrobe_entry, scene["lane"], negative_prompt)
    camera_extra = rng.choice(CAMERA_EXTRAS)
    capture_logic = LANE_CAPTURE_LOGIC.get(
        scene["lane"],
        "Capture source: real handheld candid or clearly motivated phone-timer framing, never an impossible floating camera.",
    )
    capture_lock = public_capture_lock(scene["lane"])
    wardrobe_continuity_lock = public_wardrobe_continuity_lock(wardrobe_entry, scene["lane"])
    expression_gaze_entry = choose_expression_gaze_production(rng, lane=scene["lane"])
    expression_gaze_line = format_expression_gaze_line(expression_gaze_entry)
    frame_logic = choose_frame_logic(scene["lane"])
    frame_logic_paragraph = format_frame_logic_paragraph(frame_logic, reference_mode)
    pose_body_language_entry = choose_pose_body_language_production(
        rng, lane=scene["lane"], reference_mode=reference_mode
    )
    pose_body_language_line = format_pose_body_language_line(pose_body_language_entry)

    reference_policy = reference_policy_for_mode(reference_mode)
    framing_policy = framing_policy_for_mode(reference_mode)
    body_descriptor = LENA_MASTER_IDENTITY

    image_prompt = (
        f"{IDENTITY_ANCHOR} {reference_policy} {body_descriptor} {framing_policy} "
        f"Scene: {scene['action']}. "
        f"{frame_logic_paragraph} "
        f"{pose_body_language_line} "
        f"Wardrobe: {wardrobe_override} {PUBLIC_WARDROBE_RULE} {wardrobe_continuity_lock} "
        "Do not substitute a different garment class, do not simplify the outfit into random basics, "
        "and do not replace the specified look with loungewear or underwear-coded clothing. "
        f"Environment: {environment_text}. "
        f"Small details: {detail_text}. "
        f"Camera and composition: {scene['camera']}, {camera_extra}. "
        f"{capture_logic} {capture_lock} "
        f"Lighting: {scene['lighting']}. "
        f"Face and skin: {SKIN_REALISM}. "
        f"{PHOTO_REALISM} "
        f"{EXPRESSION_REALISM} "
        f"{expression_gaze_line} "
        f"{PHONE_OBJECT_REALISM} "
        f"{SOCIAL_HOOK_FLAVOR} "
        f"Hands: {HAND_REALISM}. "
        f"Keep her identity consistent, make the moment feel specific, lived-in, candid, and emotionally believable."
    )

    caption = _clean_public_text(scene["caption"])
    caption = f"{caption}\n\n{_hashtags(rng, scene['lane'], 3)}"

    prompt_brain_version = "lena_prompt_brain_v1_9_frame_logic"

    package = {
        "slot_id": slot_id,
        "media_type": media_type,
        "lane": scene["lane"],
        "activity": scene["lane"],
        "pose": scene["action"],
        "visual_style": f"{scene['camera']}; {scene['lighting']}",
        "style_category": wardrobe_entry.get("style_lane"),
        "wardrobe_outfit_id": wardrobe_entry.get("outfit_id"),
        "wardrobe_outfit_name": wardrobe_entry.get("name"),
        "wardrobe_silhouette_class": catalog_outfit_silhouette_class(wardrobe_entry),
        "environment_id": environment_entry.get("environment_id") if environment_entry else None,
        "environment_name": environment_entry.get("name") if environment_entry else None,
        "environment_production_lane": environment_entry.get("production_lane") if environment_entry else None,
        "reference_mode": reference_mode,
        "reference_priority": reference_priority_for_mode(reference_mode),
        "scene_bank_version": scene_bank.get("version", "unknown"),
        "scene_bank_source": scene_bank.get("source", str(PHOTO_SCENE_BANK_PATH)),
        "expression_gaze_id": expression_gaze_entry.get("expression_gaze_id"),
        "expression_gaze_label": expression_gaze_entry.get("label"),
        "pose_body_language_id": pose_body_language_entry.get("pose_body_language_id"),
        "pose_body_language_label": pose_body_language_entry.get("label"),
        "pose_body_language_hand_risk": pose_body_language_entry.get("hand_risk"),
        "pose_body_language_compatibility_tags": pose_body_language_entry.get("compatibility_tags"),
        "frame_action": frame_logic.get("frame_action"),
        "frame_evidence_objects": frame_logic.get("frame_evidence_objects"),
        "frame_forbidden_objects": frame_logic.get("frame_forbidden_objects"),
        "camera_intent": frame_logic.get("camera_intent"),
        "body_visibility_rule": build_body_visibility_rule(reference_mode, frame_logic),
        "scene_coherence_note": frame_logic.get("scene_coherence_note"),
        "frame_logic_text": frame_logic_paragraph,
        "image_prompt": _clean_public_text(image_prompt),
        "prompt": _clean_public_text(image_prompt),
        "positive_prompt": _clean_public_text(image_prompt),
        "negative_prompt": negative_prompt,
        "caption": caption,
        "public_language_policy": {
            "never_mention_artificial_origin": True,
            "banned_terms": BANNED_PUBLIC_TERMS,
        },
        "prompt_brain_version": prompt_brain_version,
    }

    if media_type == "video":
        video_prompt = (
            f"{rng.choice(VIDEO_MOTIONS)}. "
            f"The scene is {scene['lane']}: {scene['action']}. "
            f"Maintain realistic facial movement, natural blinking, stable identity, believable body motion, "
            f"cinematic but restrained movement, no sudden cuts, no exaggerated gestures."
        )
        package["seed_image_prompt"] = package["image_prompt"]
        package["video_prompt"] = _clean_public_text(video_prompt)
        package["motion_prompt"] = package["video_prompt"]
        package["duration_seconds"] = 7

    _evidence = SCENE_EVIDENCE_CONTRACTS.get(scene["lane"], {})
    if _evidence:
        package["scene_evidence_contract"] = _evidence
        for _k in (
            "required_visual_evidence",
            "forbidden_contradictions",
            "caption_intent",
            "environment_realism_notes",
            "photo_realism_notes",
            "body_visibility_requirement",
            "qa_rejection_criteria",
        ):
            if _k in _evidence:
                package[_k] = _evidence[_k]

    return package


# --- Higgsfield-native prompt path (2026-07-08) -----------------------------
#
# Forward provider doctrine correction: Higgsfield is the active forward
# visual/video generation provider for Lena; Kling is legacy/historical
# infrastructure only (kept on disk for old workorders/receipts/assets, not
# extended). generate_prompt_package() above stays completely unchanged --
# it remains the real Kling-path builder for as long as any historical Kling
# artifact needs it. This is a separate, additive builder for the Higgsfield
# path, not a rewrite of the Kling one.
#
# Deliberately does NOT reuse generate_prompt_package()'s long identity/body/
# skin/realism paragraphs (IDENTITY_ANCHOR, LENA_MASTER_IDENTITY,
# REFERENCE_MODE_POLICIES, SKIN_REALISM, PHOTO_REALISM, EXPRESSION_REALISM,
# HAND_REALISM, PHONE_OBJECT_REALISM) or the tiered NEGATIVE_PROMPT
# machinery -- those exist specifically to fight Kling's weak reference-image
# conditioning. Per the manual Higgsfield findings, Soul 2.0 owns Lena's
# identity/body directly and applies no negative prompt by default, so this
# builder keeps the prompt short and limits itself to wardrobe silhouette,
# pose/body language, scene/environment, camera, lighting, and mood -- the
# things a prompt should still control even with Soul handling identity.
#
# Reuses the same provider-agnostic scene/wardrobe/environment/pose/
# expression selection functions the Kling path uses (choose_scene_production,
# pick_catalog_outfit_production, choose_environment_production,
# choose_pose_body_language_production, choose_expression_gaze_production) --
# these already live outside any Kling-specific code and already bias toward
# fitted/bodycon silhouettes (_public_sexy_bias_weight/_body_visibility_hook_weight)
# and high-attitude hip-shift poses (_pose_attitude_weight) for the reasons
# documented at each function's definition above. No new weighting mechanism
# is added here.
#
# Correction (2026-07-08, same day): Soul selection is NOT natural-language
# prompt content. Which Soul/character Higgsfield uses is a provider-config /
# CLI / MCP job-selection decision (e.g. which Soul ID a job is submitted
# against), not something to assert inside the prompt text itself. The prior
# version of this builder prepended a literal "Use my trained Soul 2.0
# character Lena." sentence to every prompt; that has been removed from the
# assembled text. The Soul name/version are still recorded, but only as
# package metadata (soul_name/soul_version/soul_selection_mode below), for a
# future executor to read and act on outside the prompt string.

HIGGSFIELD_SOUL_NAME = "Lena"
HIGGSFIELD_SOUL_VERSION = "Soul 2.0"
HIGGSFIELD_SOUL_SELECTION_MODE = "provider_config_not_prompt_text"

HIGGSFIELD_MOOD_HOOK = (
    "confident, main-character, IT-girl energy, scroll-stopping feed hook"
)

# Manual Higgsfield finding (2026-07-08): full-body/three-quarter framing
# reads best on this provider. Always included, short, no per-mode branching --
# unlike Kling's reference_mode system (face_detail/upper_body/full_body/
# video_body), which exists to match Kling's own weak per-shot-type
# conditioning. Deliberately not reusing framing_policy_for_mode()/
# REFERENCE_MODE_POLICIES here: those are long identity/body paragraphs
# scoped to Kling's needs, not a framing instruction.
HIGGSFIELD_FRAMING_LINE = (
    "Full-body three-quarter vertical 9:16 fashion photo, showing the "
    "complete outfit from head to shoes with a little space below the shoes."
)

# Bug found during manual-test sample review (2026-07-08, same day): the
# scene bank's own "camera" field (written for Kling, where medium-shot/
# waist-up framing is normal) can directly contradict HIGGSFIELD_FRAMING_LINE
# above -- e.g. "medium shot" or "waist-up composition" appearing right after
# a line that requires full-body head-to-shoes framing. Higgsfield-specific
# sanitizer: if the scene's camera text contains any conflicting crop/shot
# language, replace the whole camera line with a short safe fallback instead
# of trying to edit around the conflicting phrase. Does not touch the scene
# bank itself -- this is a Higgsfield-builder-side sanitization step only.
HIGGSFIELD_CAMERA_CONFLICT_TERMS = (
    "waist-up", "waist up", "chest-up", "chest up", "close-up", "close up",
    "tight crop", "medium shot", "cropped body", "portrait crop",
)

HIGGSFIELD_SAFE_CAMERA_TEXT = (
    "candid full-body fashion photo, 35mm or 50mm lens, vertical 9:16, "
    "natural friend-shot composition"
)


def _higgsfield_camera_conflicts_with_full_body(camera_text: str) -> bool:
    lower = str(camera_text or "").lower()
    return any(term in lower for term in HIGGSFIELD_CAMERA_CONFLICT_TERMS)


def _higgsfield_safe_camera_text(camera_text: str) -> str:
    if _higgsfield_camera_conflicts_with_full_body(camera_text):
        return HIGGSFIELD_SAFE_CAMERA_TEXT
    return camera_text


HIGGSFIELD_PROMPT_BRAIN_VERSION = "lena_prompt_brain_higgsfield_native_v1"


def generate_higgsfield_prompt_package(
    date_str: str, slot_id: str, media_type: str, sequence_index: int | None = None
) -> Dict[str, Any]:
    """Forward Higgsfield-native prompt builder. Short prompt, no negative
    prompt, no Kling-style identity/body/skin paragraphs -- Soul 2.0 owns
    Lena's identity/body. Soul selection is recorded as package metadata
    (soul_name/soul_version/soul_selection_mode) only, never as prompt text.
    See module-level comment above for the full rationale. Does not touch or
    call any Kling executor code."""
    rng = random.Random(
        _seed(date_str, slot_id, media_type, str(sequence_index or ""), "higgsfield")
    )

    validate_saved_prompt_sources()
    production_scene_pool, scene_bank = get_production_scene_pool()
    if not production_scene_pool:
        raise SystemExit("[ABORT] No production-safe saved photo scenes remain.")

    scene = choose_scene_production(production_scene_pool, rng)
    environment_entry = choose_environment_production(scene, rng)
    environment_text, detail_text = build_environment_prompt_parts(scene, environment_entry)
    reference_mode = choose_reference_mode(media_type, scene)
    wardrobe_entry = pick_catalog_outfit_production(scene["lane"], reference_mode, rng)
    expression_gaze_entry = choose_expression_gaze_production(rng, lane=scene["lane"])
    pose_body_language_entry = choose_pose_body_language_production(
        rng, lane=scene["lane"], reference_mode=reference_mode
    )

    wardrobe_text = _clean_sentence_fragment(str(wardrobe_entry.get("prompt", "")))
    pose_text = _clean_sentence_fragment(str(pose_body_language_entry.get("text", "")))
    expression_text = _clean_sentence_fragment(str(expression_gaze_entry.get("text", "")))
    scene_action = _clean_sentence_fragment(str(scene.get("action", "")))
    camera_text = _clean_sentence_fragment(str(scene.get("camera", "")))
    camera_text = _higgsfield_safe_camera_text(camera_text)
    lighting_text = _clean_sentence_fragment(str(scene.get("lighting", "")))

    image_prompt = _clean_public_text(
        f"{HIGGSFIELD_FRAMING_LINE} "
        f"Scene: {scene_action}, {environment_text}. "
        f"Wardrobe: {wardrobe_text}. "
        f"Pose: {pose_text}. "
        f"Expression: {expression_text}. "
        f"Camera: {camera_text}. "
        f"Lighting: {lighting_text}. "
        f"Mood: {HIGGSFIELD_MOOD_HOOK}."
    )

    caption = _clean_public_text(scene["caption"])
    caption = f"{caption}\n\n{_hashtags(rng, scene['lane'], 3)}"

    return {
        "slot_id": slot_id,
        "media_type": media_type,
        "provider": "higgsfield",
        "soul_name": HIGGSFIELD_SOUL_NAME,
        "soul_version": HIGGSFIELD_SOUL_VERSION,
        "soul_selection_mode": HIGGSFIELD_SOUL_SELECTION_MODE,
        "lane": scene["lane"],
        "activity": scene["lane"],
        "wardrobe_outfit_id": wardrobe_entry.get("outfit_id"),
        "wardrobe_outfit_name": wardrobe_entry.get("name"),
        "wardrobe_silhouette_class": catalog_outfit_silhouette_class(wardrobe_entry),
        "environment_id": environment_entry.get("environment_id") if environment_entry else None,
        "environment_name": environment_entry.get("name") if environment_entry else None,
        "pose_body_language_id": pose_body_language_entry.get("pose_body_language_id"),
        "pose_body_language_label": pose_body_language_entry.get("label"),
        "expression_gaze_id": expression_gaze_entry.get("expression_gaze_id"),
        "expression_gaze_label": expression_gaze_entry.get("label"),
        "reference_mode": reference_mode,
        "image_prompt": image_prompt,
        "prompt": image_prompt,
        "positive_prompt": image_prompt,
        "negative_prompt": "",
        "negative_prompt_enabled": False,
        "caption": caption,
        "public_language_policy": {
            "never_mention_artificial_origin": True,
            "banned_terms": BANNED_PUBLIC_TERMS,
        },
        "prompt_brain_version": HIGGSFIELD_PROMPT_BRAIN_VERSION,
    }


def apply_prompt_package_to_slot(slot: Dict[str, Any], package: Dict[str, Any]) -> Dict[str, Any]:
    media_type = package["media_type"]

    for key in ["prompt", "positive_prompt", "image_prompt", "negative_prompt", "caption"]:
        slot[key] = package[key]

    slot["activity"] = package.get("activity")
    slot["pose"] = package.get("pose")
    slot["visual_style"] = package.get("visual_style")

    if media_type == "video":
        slot["seed_image_prompt"] = package["seed_image_prompt"]
        slot["video_prompt"] = package["video_prompt"]
        slot["motion_prompt"] = package["motion_prompt"]
        slot["duration_seconds"] = 7
        slot["max_video_seconds"] = 7

    meta = slot.setdefault("metadata", {})
    meta["prompt_brain_version"] = package.get("prompt_brain_version", "lena_prompt_brain_v1_9_frame_logic")
    meta["activity"] = package.get("activity")
    meta["pose"] = package.get("pose")
    meta["visual_style"] = package.get("visual_style")
    meta["style_category"] = package.get("style_category")
    meta["wardrobe_outfit_id"] = package.get("wardrobe_outfit_id")
    meta["wardrobe_outfit_name"] = package.get("wardrobe_outfit_name")
    meta["wardrobe_silhouette_class"] = package.get("wardrobe_silhouette_class")
    meta["environment_id"] = package.get("environment_id")
    meta["environment_name"] = package.get("environment_name")
    meta["environment_production_lane"] = package.get("environment_production_lane")
    meta["lane"] = package["lane"]
    meta["reference_mode"] = package.get("reference_mode")
    meta["reference_priority"] = package.get("reference_priority")
    meta["scene_bank_version"] = package.get("scene_bank_version")
    meta["scene_bank_source"] = package.get("scene_bank_source")
    meta["expression_gaze_id"] = package.get("expression_gaze_id")
    meta["expression_gaze_label"] = package.get("expression_gaze_label")
    meta["pose_body_language_id"] = package.get("pose_body_language_id")
    meta["pose_body_language_label"] = package.get("pose_body_language_label")
    meta["pose_body_language_hand_risk"] = package.get("pose_body_language_hand_risk")
    meta["pose_body_language_compatibility_tags"] = package.get("pose_body_language_compatibility_tags")
    meta["frame_action"] = package.get("frame_action")
    meta["frame_evidence_objects"] = package.get("frame_evidence_objects")
    meta["frame_forbidden_objects"] = package.get("frame_forbidden_objects")
    meta["camera_intent"] = package.get("camera_intent")
    meta["body_visibility_rule"] = package.get("body_visibility_rule")
    meta["scene_coherence_note"] = package.get("scene_coherence_note")
    meta["frame_logic_text"] = package.get("frame_logic_text")
    meta["image_prompt"] = package["image_prompt"]
    meta["negative_prompt"] = package["negative_prompt"]
    meta["caption"] = package["caption"]
    meta["public_language_policy"] = package["public_language_policy"]
    if media_type == "video":
        meta["kling_route"] = "https://kling.ai/app/video/new"
        meta["estimated_credits"] = int(os.environ.get("LENA_ESTIMATED_VIDEO_CREDITS", "25"))
    else:
        meta["kling_route"] = "https://kling.ai/app/image/new"
        meta["estimated_credits"] = int(os.environ.get("LENA_ESTIMATED_PHOTO_CREDITS", "2"))

    if media_type == "video":
        meta["video_prompt"] = package["video_prompt"]
        meta["motion_prompt"] = package["motion_prompt"]
        meta["duration_seconds"] = 7

    return slot
