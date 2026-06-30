from __future__ import annotations

from datetime import datetime
import hashlib
import random
import re
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
    "Lena Delapi with consistent approved reference identity, natural skin texture, "
    "soft flyaway hair, expressive candid face, and a balanced curvy silhouette. "
    "Keep face and body faithful to the approved reference element."
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
    "body into a slimmer silhouette in side angles or standing poses. "
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
    "unretouched phone-camera skin with visible pores on cheeks, nose, and forehead, "
    "fine facial texture, faint lower-lid and under-eye texture, subtle redness, "
    "tiny tone variation, tiny forehead texture, soft natural under-eye darkness, "
    "small natural nose shine, realistic skin oil balance, natural asymmetry, "
    "and one or two tiny natural blemish-scale imperfections. "
    "No skin blur, no denoised skin, and no softened pore detail. "
    "Micro detail: tiny peach-fuzz edge highlights, individual brow hairs, "
    "real eyelashes with small shadows, imperfect lip texture, a few stray hair strands, "
    "slight mouth-corner creasing, faint smile-line softness, normal eyelid fold depth, "
    "subtle tear-trough transition, natural philtrum and lip-edge definition, "
    "uneven natural catchlights, and scene-light falloff across the face. "
    "Preserve Lena's reference-accurate facial beauty marks only, in the same fixed positions, "
    "same side of the face, and roughly the same size and count as the reference. "
    "Treat those marks as exact identity anchors tied to the same relative locations around the "
    "eyes, nose, mouth, cheeks, and lower face as in the reference. "
    "If the reference beauty marks are subtle, keep them subtle and sparse. "
    "Do not move them, mirror them, multiply them, enlarge them, or turn them into a different pattern than the reference. "
    "If facial marks appear, they should stay faithful to the reference image rather than being restyled. "
    "Not plastic, not waxy, not over-smoothed, not CGI, not glossy doll skin. "
    "No beauty-filter skin, no airbrushed mannequin skin, "
    "no polished beauty-campaign finish, no commercial skin retouch look, "
    "no foundation-ad finish, no new non-reference freckle clusters, "
    "no new mole placements, and no decorative beauty-filter speckling that changes her identity. "
    "No baby-face stylization, no oversized irises, no porcelain doll facial finish, "
    "and no smoothed influencer-face retouch geometry."
)

HAND_REALISM = (
    "Hands should read as natural human hands with five fingers on each hand, "
    "correct thumb placement, believable knuckle joints, realistic nail scale, "
    "relaxed wrists, and simple candid hand posing. "
    "Avoid complex interlocked fingers, overlapping hand tangles, mannequin hands, "
    "melted fingers, fused fingers, twisted wrists, or broken-looking joints."
)

MAIN_REFERENCE_POLICY = (
    "Preserve Lena's provided facial identity, skin tone, body proportions, silhouette, posture, clothing fit, hands, legs, waist-to-hip shape, and overall likeness from the uploaded reference imagery. "
    "Use supplemental angle references only when a specific pose, camera angle, or body orientation is needed."
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

NEGATIVE_PROMPT = (
    "low quality, blurry, distorted face, changed face, identity drift, "
    "unrealistic body proportions, deformed hands, extra fingers, "
    "missing fingers, fused fingers, melted fingers, tangled fingers, "
    "broken knuckles, twisted wrists, bad thumb placement, mannequin hands, "
    "bad anatomy, crossed eyes, "
    "unnaturally long fingers, elongated slender fingers, "
    "glossy plastic fake nails, uniform white press-on nails, "
    "overly manicured nails, doll-like fingers, rubbery fingers, "
    "stiff posed fingers, airbrushed hand skin, "
    "harsh face distortion, waxy skin, plastic skin, over-smoothed skin, "
    "airbrushed skin, beauty filter skin, mannequin skin, poreless face, "
    "CGI face, 3D-rendered face, glossy doll skin, synthetic smooth face, "
    "skin blur, denoised skin, softened pore detail, blurred skin texture, "
    "beauty-retouched face, foundation-ad skin, "
    "porcelain doll face, baby-face stylization, oversized irises, inflated lips, "
    "over-clean facial geometry, glam retouch face, "
    "random added freckles, extra freckle-like speckles, "
    "decorative freckle mask, beauty-filter speckling, moved beauty marks, mirrored beauty marks, "
    "multiplied beauty marks, enlarged beauty marks, new non-reference mole placements, "
    "new non-reference heavy freckle clusters, "
    "skinny body, petite frame, narrow hips, inward-pulled hip points, narrow pelvis, thin thighs, "
    "slim runway model proportions, wasp waist, bulky thighs, thickened torso, "
    "exaggerated heavy lower body, flat chest, "
    "belly button piercing, navel jewelry, navel ring, "
    "bike shorts, compression shorts, hot pants, underwear-like shorts, "
    "bra as outerwear, lingerie in public, bikini top as streetwear, "
    "underwear visible as clothing in outdoor or street settings, "
    "uncanny expression, cartoon, anime, doll-like, "
    "hotel room, luxury suite, hospitality decor, showroom interior, "
    "upholstered hotel headboard, nightstand hotel telephone, commercial beauty ad lighting, "
    "editorial glam campaign lighting, polished resort room, overly glossy specular skin, "
    "watermark, text overlay, logo, duplicate person, extra limbs, "
    "navel piercing, belly button jewelry"
)

MIDRIFF_COVERAGE_NEGATIVE_SUFFIX = (
    "exposed belly button, visible navel, bare navel, midriff gap, "
    "gap between top hem and waistband, visible stomach with full-length top, "
    "hoodie floating above waistband, ultra-cropped hoodie, cropped quarter-zip, "
    "cropped pullover, cropped sweater, cropped long-sleeve top, "
    "bikini-like crop top, bra top under open shirt, bralette substituted for "
    "tank top, bandeau under open button-down, micro-cami ending above waistband"
)


def catalog_outfit_midriff_must_stay_covered(entry: dict | None) -> bool:
    if not entry:
        return False
    prompt = (entry.get("prompt") or "").lower()
    if any(
        token in prompt
        for token in ["crop", "cropped", "bralette", "bikini"]
    ):
        return False
    if "dress" in prompt:
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


def build_negative_prompt_for_catalog(entry: dict | None) -> str:
    negative = NEGATIVE_PROMPT
    if catalog_outfit_midriff_must_stay_covered(entry):
        negative = f"{negative}, {MIDRIFF_COVERAGE_NEGATIVE_SUFFIX}"
    return negative

PUBLIC_WARDROBE_RULE = (
    "Wardrobe for public and street settings must read as real outerwear: "
    "fitted top, bodysuit, blouse, dress, coordinated crop top, jacket, or layering. "
    "Do not show bra, bra-like top, lingerie, bikini top, or underwear as public outerwear "
    "in street, cafe, campus, outdoor, errand, park, or sidewalk scenes."
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


_PRODUCTION_EXCLUDE_CATEGORIES = {"cozy", "fitness"}
_PRODUCTION_BLOCKED_TERMS = [
    "hoodie", "jogger", "joggers", "sweatpants",
    "pajama", "pajamas", "biker shorts", "bike shorts",
    "bralette", "bodysuit", "jumpsuit",
    "quarter-zip", "turtleneck", "mock-neck", "mock neck",
    "puffer vest",
]


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
            "bikini-like top, or underwear-like garment. A slight natural "
            "waistband reveal is acceptable if the pose or styling makes it "
            "plausible, but do not shrink a normal top into an extreme "
            "micro-crop or bra-band-only drift. "
        )
    if has_base_layer and has_open_layer:
        layered_guard = (
            "If an open overshirt or jacket is layered over a cami, tank, or "
            "tee, the base layer must stay a real everyday top with normal "
            "side coverage and waistband-length coverage, not a bralette, "
            "bandeau, bikini top, sports bra, triangle bra, or micro-crop. "
        )
    return (
        "Wardrobe override — use this catalog outfit for clothing only: "
        f"{prompt}. "
        f"{fit_guard}"
        f"{layered_guard}"
        "Lena's face, hair, body, skin tone, and identity come from the "
        "approved character element/reference images, not the outfit text."
    )


PHOTO_SCENES = [
    {"lane":"morning apartment","action":"standing barefoot in her kitchen while pouring coffee into a ceramic mug, glancing toward the window like she is still waking up","environment":"a lived-in apartment kitchen with warm wood shelves, a half-open linen curtain, a small bowl of oranges, and morning light sliding across the counter","details":"steam from the coffee, one loose strand of hair near her cheek, a phone face-down on the counter, soft shadows on the wall","camera":"candid editorial lifestyle photo, 50mm lens, shallow depth of field, waist-up composition","lighting":"early morning natural window light, warm highlights, gentle contrast","caption":"coffee first, personality later"},
    {"lane":"apartment doorway","action":"leaving through the apartment doorway, looking back over her shoulder with a half-smile like she almost forgot something but went anyway","environment":"a lived-in apartment entryway with a coat rack hung with jackets in the foreground, a small entry table with keys and mail, a potted plant near the door, warm interior light spilling into the hallway in the background","details":"tote bag over her shoulder, keys in one hand, a jacket draped over her arm, soft shadow from the doorframe","camera":"full-body candid lifestyle portrait, 35mm lens, natural candid framing from just outside the door","lighting":"warm apartment interior light mixing with cool hallway light, soft natural split on her face","caption":"leaving on the first try today"},
    {"lane":"coffee shop","action":"leaning against a small cafe window counter, holding an iced coffee and smiling like someone just made a quiet joke","environment":"a narrow neighborhood coffee shop with mismatched two-top tables and a scratched wooden pickup counter in the foreground, handwritten menu board and pastry case in the midground, condensation on the front window with blurred street and foot traffic beyond","details":"iced coffee condensation ring on the counter in the foreground, receipt and straw wrapper beside the cup, tote bag hooked on the stool, silver spoon on the saucer, soft window reflection in the glass","camera":"candid street-style cafe photo, 50mm lens, soft background blur","lighting":"cloudy daylight through glass, neutral tones, realistic skin highlights","caption":"quick coffee turned into a whole little reset"},
    {"lane":"rainy street","action":"walking across a wet city sidewalk while looking back over her shoulder, one hand holding her coat closed","environment":"a rainy downtown street with glossy pavement, blurred headlights, muted storefronts, and a dark umbrella passing behind her","details":"tiny raindrops on her coat, reflective puddles, wind lifting a few strands of hair, soft bokeh lights","camera":"handheld street photo, 85mm lens, full-body candid, natural motion blur, not cinematic grading","lighting":"overcast blue-gray daylight with warm reflections from shop windows","caption":"rain always makes errands feel more dramatic"},
    {"lane":"rooftop sunset","action":"standing near a rooftop railing at sunset, turning slightly toward the camera with relaxed confidence","environment":"a city rooftop with low lounge furniture, concrete planters, skyline in the background, and warm sunset haze","details":"gold light along her hair, subtle wind movement, glass of sparkling water on a side table, skyline softly blurred","camera":"candid outdoor portrait, 70mm lens, medium shot, shallow depth of field, natural light","lighting":"golden-hour backlight, warm rim light, soft face fill","caption":"stayed for the light"},
    {"lane":"bookstore","action":"standing between tall bookstore shelves, holding one book open while her eyes lift toward the camera","environment":"an independent bookstore with warm lamps, narrow aisles, stacked novels, wood floors, and a small reading chair in the background","details":"paper texture, a receipt tucked into the book, soft dust in the light, one hand resting on the shelf","camera":"quiet cinematic portrait, 50mm lens, natural framing through shelves","lighting":"warm indoor lamp light with soft shadows","caption":"went in for one book and immediately lied to myself"},
    {"lane":"grocery run","action":"standing beside a small grocery cart, reaching for fresh flowers while glancing down with a half-smile","environment":"a bright neighborhood market with produce crates, eucalyptus bundles, handwritten price signs, and soft morning activity behind her","details":"green stems in her hand, canvas tote bag, oranges and lemons nearby, realistic aisle clutter","camera":"documentary lifestyle photo, 35mm lens, candid mid-shot","lighting":"clean natural store light mixed with daylight from front windows","caption":"flowers were not on the list but here we are"},
    {"lane":"car moment","action":"sitting in the passenger seat of a parked car, looking out the window with one hand near her cheek","environment":"foreground dashboard and worn console details, neutral leather interior in the midground, blurred city street through rain-specked windshield in the background","details":"seatbelt strap, faint reflection on the window, lip gloss catching light, phone cable near the console","camera":"intimate candid portrait, 50mm lens from driver-side angle","lighting":"soft overcast window light, muted tones","caption":"parked for five minutes and somehow reset my whole mood"},
    {"lane":"studio desk","action":"sitting at a cluttered-but-curated desk with a laptop open, chin resting lightly on one hand, looking focused but calm, like she framed this angle on purpose","environment":"a lived-in home workspace with a large monitor in the background, scattered notebooks and sticky notes around the frame, warm desk lamp in the foreground, wall of pinned inspiration softly blurred behind","details":"tangled cable at the desk edge, sticky notes with scrawled reminders, open notebook with crossed-out lines, iced coffee condensation ring on the desk surface, laptop screen glow on her face","camera":"modern creator workspace portrait, 35mm lens, medium composition","lighting":"late afternoon window light mixed with a warm desk lamp","caption":"pretending this is organized because the lamp is cute"},
    {"lane":"night out","action":"standing near a bathroom mirror at a low-lit lounge, checking one earring while looking at her reflection","environment":"an upscale lounge restroom with dark marble, warm sconces, brushed brass fixtures, and a blurred doorway behind her","details":"mirror smudges, lipstick in one hand, soft highlights on jewelry, slight motion blur from the room behind her","camera":"flash-adjacent nightlife editorial photo, 35mm lens, mirror composition","lighting":"warm low light, soft mirror reflections, controlled highlights","caption":"one last mirror check"},
    {"lane":"skincare evening","action":"standing at a bathroom sink with a white towel around her shoulders, pressing moisturizer gently into one cheek","environment":"a calm apartment bathroom with frosted glass, a small plant, neutral stone counter, and warm mirror light","details":"dewy skin texture, tiny water droplets near the sink, open moisturizer jar, soft robe fabric","camera":"close-up beauty lifestyle portrait, 85mm lens, natural skin detail","lighting":"soft warm bathroom light, realistic highlights on skin","caption":"night routine doing the heavy lifting"},
    {"lane":"airport day","action":"walking through an airport terminal with a small suitcase, turning slightly as if someone called her name","environment":"a modern terminal with glass walls, polished floors, gate signs blurred in the background, and early morning travelers passing behind her","details":"passport wallet in hand, coffee cup in suitcase side pocket, moving walkway reflections, realistic travel fatigue","camera":"travel street-style photo, 35mm lens, full-body candid shot","lighting":"cool airport daylight mixed with overhead lighting","caption":"airport coffee counts as a personality trait"},
    {"lane":"gym cooldown","action":"sitting on a bench after a workout, tying her sneaker while looking down with a calm focused expression","environment":"a boutique fitness studio with worn rubber flooring, soft mirrors, towels stacked nearby, and sunlight from high windows","details":"slight flyaways, natural post-workout skin glow, water bottle on the floor, realistic fabric folds","camera":"candid wellness lifestyle photo, 50mm lens, low angle","lighting":"clean morning studio light, soft reflections in the mirror","caption":"the part where you just sit for a minute"},
    {"lane":"laundry day","action":"leaning against a washing machine in a quiet laundromat, folding a white tee and laughing to herself","environment":"a retro laundromat with laundry basket and folded clothes in the foreground, chrome machines in the midground, checker tile floor and fluorescent ceiling lights blurred toward the background window","details":"laundry basket, dryer glow, quarters on top of the machine, a paperback book nearby","camera":"cinematic slice-of-life photo, 35mm lens, natural candid framing","lighting":"mixed fluorescent and daylight, realistic color balance","caption":"romanticizing laundry because someone has to"},
    {"lane":"museum afternoon","action":"standing in front of a large abstract painting, arms loosely crossed, studying it with a thoughtful expression","environment":"a quiet modern art museum gallery with polished concrete floors, white walls, soft benches, and visitors blurred in the distance","details":"gallery card beside painting, soft footsteps implied, simple jewelry, calm posture","camera":"quiet handheld portrait, 50mm lens, natural museum composition, candid visitor feel","lighting":"soft museum track lighting, clean neutral tones","caption":"came for the quiet"},
    {"lane":"late kitchen snack","action":"standing in the kitchen at night, eating a strawberry over the sink and smiling like she got caught","environment":"a dim apartment kitchen with one under-cabinet light on, dark window reflection, marble counter, and a half-open fridge glow","details":"bowl of strawberries, loose hair, bare shoulders under a cardigan, reflection in the window","camera":"intimate night lifestyle photo, 50mm lens, close candid framing","lighting":"warm kitchen practical light with soft fridge glow","caption":"standing over the sink counts as dinner sometimes"},
    {"lane":"flower shop","action":"standing outside a flower shop holding a wrapped bouquet, looking down at the flowers with a soft smile","environment":"a small storefront with buckets of tulips and ranunculus, faded awning, old brick wall, and morning pedestrians blurred behind her","details":"brown paper bouquet wrap, ribbon ends, petals near the sidewalk, soft wind in her hair","camera":"candid street photo, 85mm lens, shallow background blur, natural morning light","lighting":"bright but soft morning light, gentle skin highlights","caption":"bought flowers for the apartment and maybe also for my mood"},
    {"lane":"record store","action":"flipping through vinyl records, pausing with one sleeve halfway pulled out and a curious look","environment":"a moody record shop with narrow aisles, posters on the wall, warm lamps, and stacks of albums around her","details":"fingertips on album sleeve, soft dust, vintage speakers in the background, tote bag on her shoulder","camera":"grainy candid phone photo, 35mm lens, natural side angle, warm store light","lighting":"warm low store lighting, subtle film-like grain","caption":"found three records and zero self-control"},
    {"lane":"mirror outfit check","action":"taking a mirror outfit check in a softly lit bedroom, phone held low enough that her face is still visible","environment":"a clean but lived-in bedroom with a standing mirror, linen bedding, a chair with clothes draped over it, and late afternoon light on the floor","details":"slight mirror dust, jewelry tray, boots near the wall, realistic phone reflection","camera":"realistic mirror photo, natural proportions, full outfit visible, not overly posed","lighting":"late afternoon window light, soft warm tones","caption":"this was supposed to be the quick outfit check"},
    {"lane":"city bench","action":"sitting on a city bench with one leg crossed, holding a paper coffee cup and watching people pass","environment":"a tree-lined city block, coffee cup and tote strap in the foreground, worn city bench in the midground, brownstones and parked bikes softly blurred in the background","details":"wind moving her hair, coffee lid detail, tote bag beside her, small sun patches through leaves","camera":"street-style lifestyle portrait, 85mm lens, natural candid framing","lighting":"dappled late morning sunlight, soft shadows","caption":"five quiet minutes before the day started asking for things"},
    {"lane":"elevator moment","action":"standing in an elevator, looking at the camera reflection with a calm unreadable expression","environment":"an elevator with phone and handrail in the foreground, brushed metal walls with smudged finger marks in the midground, warm overhead lights and scuffed mirrored panel in the background","details":"one hand holding a small bag, realistic metal reflections, slight motion blur from elevator movement","camera":"mirror-like editorial candid, 35mm lens, centered composition","lighting":"warm overhead elevator light softened by reflection","caption":"elevator lighting had one job and somehow did it"},
]


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
        "Reference mode: close-up face detail. Preserve Lena's facial identity, skin tone, hairline, eye shape, brows, cheekbones, mouth shape, and natural skin texture from the uploaded close face reference. "
        "Prioritize facial realism, hair detail, skin detail, and expression consistency."
    ),
    "upper_body": (
        "Reference mode: upper-body lifestyle. Preserve Lena's facial identity plus her upper-body proportions, shoulders, waistline, hands, posture, jewelry placement, and clothing fit from the uploaded reference imagery. "
        "Use body proportions naturally without forcing a full-body pose."
    ),
    "full_body": (
        "Reference mode: full-body fashion/lifestyle. Preserve Lena's facial identity "
        "plus her full-body proportions, defined waist without shrinking her frame, "
        "visibly wider hips, fuller thighs, rounded lower-body silhouette, "
        "long legs, hands, feet, posture, and clothing fit from the uploaded reference imagery. "
        "Keep her athletic-curvy proportions consistent, attractive, realistic, "
        "fully clothed, and editorial. Do not slim her down."
    ),
    "video_body": (
        "Reference mode: video continuity. Preserve Lena's facial identity, body proportions, posture, hands, legs, clothing fit, and silhouette from the uploaded reference imagery so the seed image can animate naturally. "
        "Prioritize stable identity, stable body proportions, believable posture, and subtle realistic movement."
    ),
}


REFERENCE_PRIORITY = {
    "face_detail": ["close_up.jpeg", "lena_reference.jpeg", "body_ref.png"],
    "upper_body": ["body_ref.png", "lena_reference.jpeg", "close_up.jpeg"],
    "full_body": ["body_ref.png", "lena_reference.jpeg", "close_up.jpeg"],
    "video_body": ["body_ref.png", "lena_reference.jpeg", "close_up.jpeg"],
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

    scene = rng.choice(PHOTO_SCENES)
    outfit = rng.choice(OUTFITS)
    camera_extra = rng.choice(CAMERA_EXTRAS)

    reference_mode = choose_reference_mode(media_type, scene)
    reference_policy = reference_policy_for_mode(reference_mode)
    framing_policy = framing_policy_for_mode(reference_mode)
    body_descriptor = LENA_MASTER_IDENTITY

    image_prompt = (
        f"{IDENTITY_ANCHOR} {reference_policy} {body_descriptor} {framing_policy} "
        f"Scene: {scene['action']}. "
        f"Wardrobe: she is wearing {outfit}. {PUBLIC_WARDROBE_RULE} "
        f"Environment: {scene['environment']}. "
        f"Small details: {scene['details']}. "
        f"Camera and composition: {scene['camera']}, {camera_extra}. "
        f"Lighting: {scene['lighting']}. "
        f"Face and skin: {SKIN_REALISM}. "
        f"Hands: {HAND_REALISM}. "
        f"Keep her identity consistent, make the moment feel specific, lived-in, candid, and emotionally believable."
    )

    caption = _clean_public_text(scene["caption"])
    caption = f"{caption}\n\n{_hashtags(rng, scene['lane'], 3)}"

    package = {
        "slot_id": slot_id,
        "media_type": media_type,
        "lane": scene["lane"],
        "reference_mode": reference_mode,
        "reference_priority": reference_priority_for_mode(reference_mode),
        "image_prompt": _clean_public_text(image_prompt),
        "prompt": _clean_public_text(image_prompt),
        "positive_prompt": _clean_public_text(image_prompt),
        "negative_prompt": NEGATIVE_PROMPT,
        "caption": caption,
        "public_language_policy": {
            "never_mention_artificial_origin": True,
            "banned_terms": BANNED_PUBLIC_TERMS,
        },
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
        package["duration_seconds"] = 10

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


def apply_prompt_package_to_slot(slot: Dict[str, Any], package: Dict[str, Any]) -> Dict[str, Any]:
    media_type = package["media_type"]

    for key in ["prompt", "positive_prompt", "image_prompt", "negative_prompt", "caption"]:
        slot[key] = package[key]

    if media_type == "video":
        slot["seed_image_prompt"] = package["seed_image_prompt"]
        slot["video_prompt"] = package["video_prompt"]
        slot["motion_prompt"] = package["motion_prompt"]
        slot["duration_seconds"] = 10
        slot["max_video_seconds"] = 10

    meta = slot.setdefault("metadata", {})
    meta["prompt_brain_version"] = "lena_prompt_brain_v1_1"
    meta["lane"] = package["lane"]
    meta["reference_mode"] = package.get("reference_mode")
    meta["reference_priority"] = package.get("reference_priority")
    meta["image_prompt"] = package["image_prompt"]
    meta["negative_prompt"] = package["negative_prompt"]
    meta["caption"] = package["caption"]
    meta["public_language_policy"] = package["public_language_policy"]

    if media_type == "video":
        meta["video_prompt"] = package["video_prompt"]
        meta["motion_prompt"] = package["motion_prompt"]
        meta["duration_seconds"] = 10

    return slot
