from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits

NODE_ROOT = ROOT / "pipeline" / "influencer_nodes" / "lena"
MEMORY_PATH = ROOT / "pipeline" / "state" / "lena_prompt_memory.json"
VERSION = "v1.3.0_influencer_node_core"

NEGATIVE_PROMPT = (
    "visible text, readable text, unreadable text, letters, numbers, symbols, signage, menu text, "
    "book text, poster text, logo, watermark, label, clothing logo, phone screen, app interface, "
    "status bar, camera interface, browser bar, subtitles, caption text inside the image, "
    "garbled writing, pseudo letters, random marks, top-edge artifacts, frame border artifacts, "
    "extra fingers, missing fingers, warped hands, distorted face, plastic skin, waxy skin, "
    "uncanny eyes, broken anatomy, duplicate limbs, background morphing, boring stock photo, "
    "plain tank top and basic jeans as the main look, fake luxury flex, cluttered background, "
    "explicit sexual content, explicit nudity, nude, pornographic content, fetish costume, fetish framing, "
    "shapeless body-hiding draping, oversized tent-like clothing hiding figure, "
    "heavy freckle clusters, blotchy facial spots, identity-breaking skin speckling, acne-like facial blotches, "
    "slim model figure, skinny body, model-thin proportions, flat chest, narrow hips, boxy silhouette, no visible waist curve, "
    "distorted anatomy, cartoon body proportions, warped body shape, exaggerated impossible bust or hip proportions, "
    "crotch-focused framing, explicit anatomical emphasis, nude posing, explicit sexual posing, pornographic posing, "
    "campus setting, classroom interior, school library shelves, lecture hall, walking-to-class scene framing, student narrative framing, cheap clubwear energy, lingerie-bait framing, thirst-trap AI styling, trashy or discount-looking fashion framing, hotel room interiors, hotel-looking staged backgrounds, hotel bed or hotel furniture in frame, "
    "professional photography, studio lighting, high resolution, 8K, 4K, sharp focus, perfectly posed, DSLR, mirrorless, Canon, Sony, bokeh, shallow depth of field, beautiful, stunning, cinematic lighting, magazine quality, portrait mode, overly polished, portfolio lighting, commercial fashion shoot, editorial fashion shoot, model portfolio, photographer portfolio, luxury ad campaign, glossy editorial shoot, over-smoothed skin, airbrushed skin, sterile studio background, distorted text"
)

VISUAL_BANS = [
    "No visible text, letters, numbers, logos, labels, signs, menus, book spines, screens, UI overlays, watermarks, or garbled marks anywhere.",
    "Keep frame edges clean, especially the top edge: no icons, black bars, random marks, app frames, or fake interface junk.",
    "Avoid text-heavy environments: signs, menus, bookshelves, screens, branded products, labels, posters, and license plates.",
    "The image must feel like a believable real-person camera-roll moment, not a staged stock-photo model pose.",
    "Wardrobe must feel current, human, and intentional; no boring default tank-top-and-jeans look.",
]

LANE_FAMILIES = {
    "fitness_movement": {"morning stretch", "stretch flow", "light workout", "wellness movement", "dance clip"},
    "wellness_recovery": {"soft skincare morning", "evening skincare", "sauna/recovery", "wind-down stretch"},
    "home_life": {"apartment reset", "smoothie prep", "kitchen moment", "simple dinner"},
    "outfit_body": {"outfit check", "balcony pose", "poolside lifestyle", "city errands"},
    "humor_pov": {"pov wellness joke"},
    "coffee_city": {"coffee walk"},
    "dance_reels": {"dance clip"},
    "fit_check_mirror": {"mirror fit check", "bedroom outfit check", "getting-ready look"},
    "street_baddie_niche": {"street baddie", "parked car style"},
    "going_out_niche": {"going-out look"},
    "beauty_glow_niche": {"beauty glow-up"},
    "product_styling_niche": {"product styling hook"},
    "beauty_maintenance_series": {"soft glam lip combo", "skincare check", "everything shower glow"},
    "affordable_luxury_series": {"looks expensive isn't", "save vs splurge", "drugstore expensive energy"},
    "personality_hooks_series": {"grwm situation", "outfit for when", "things that make outfit cheap", "pretty girl discipline"},
    "gym_to_glam_series": {"gym-to-glam reset", "post-gym glow"},
    "direct_flash_ugc": {
        "boxing gym flash fit-check", "laundromat flash fit-check",
        "corner store flash errand", "parking garage flash outfit",
        "diner booth flash", "gym locker room outfit reset",
        "dance studio mirror flash", "apartment hallway dressed flash",
        "bathroom party flash", "vintage arcade flash", "cafe patio direct-flash",
    },
    # New lanes - recipes to be added in Phase 2
    "moody_90s_flash_editorial": {
        "grand staircase flash editorial",
        "dark wood hallway flash editorial",
        "velvet lounge corner flash editorial",
        "ornate lobby flash editorial",
        "candlelit restaurant corridor editorial",
        "marble bathroom flash editorial",
        "old money townhouse entryway editorial",
    },
    "joyful_35mm_boxing_gym_flash": {
        "boxing ring stool smile flash",
        "yellow boxing glove handbag flash",
        "heavy bag laugh candid flash",
        "jump rope corner flash",
        "locker bench outfit reset flash",
        "post workout smoothie gym exit",
        "dance studio cross training flash",
    },
    "sun_drenched_90s_roadtrip_film": {
        "vintage car roadside lens flare",
        "dusty suv foliage film burn",
        "gas station sunlight snapshot",
        "beach boardwalk wind flare",
        "lake pier golden film still",
        "outdoor cafe roadtrip stop",
        "farmers market sun leak candid",
    },
    "luxury_fit_check_flash": {
        "apartment doorway luxury fit check",
        "parking garage flash fit check",
        "late night flower stand fit check",
        "boutique mirror flash fit check",
        "rooftop elevator lobby flash",
        "art gallery hallway fit check",
        "black car curbside arrival flash",
        "city sidewalk coat over shoulders",
        "espresso bar mini dress flash",
        "jewelry stack vanity fit check",
    },
    "beauty_maintenance_glam": set(),
    "social_night_out_flash": set(),
    "street_style_errand_glam": set(),
    "home_luxury_lifestyle": set(),
}

LENA_MASTER_IDENTITY_BLUEPRINT = (
    "@Lena is the approved visual identity reference. "
    "Preserve the same realistic Lena face and the same natural "
    "curvy hourglass body from the approved element "
    "in every generation. "
    "Lena has a realistic, naturally beautiful face with a softly "
    "oval-to-heart-shaped structure, high natural cheekbones, "
    "a slim softly defined jawline, and a small rounded chin. "
    "Her eyes are warm medium brown, almond-shaped, "
    "slightly hooded, and softly upturned at the outer corners, "
    "with a calm sultry gaze. "
    "Her eyebrows are thick, dark, naturally arched, and expressive, "
    "not thin or overly polished. "
    "Her nose is slim and straight with a soft bridge, "
    "narrow nostrils, and a rounded natural tip. "
    "Her lips are full and natural with a defined cupid's bow, "
    "soft pink-nude color, a fuller lower lip, "
    "and a relaxed slightly parted shape. "
    "Her skin tone is warm light-to-medium with peach/olive undertones, "
    "visible pores, subtle redness, tiny natural skin speckles, "
    "and real human texture; "
    "her skin must not look plastic, poreless, airbrushed, or doll-like. "
    "Her hair is dark brunette with warm auburn-brown highlights, "
    "soft volume, natural waves, and loose face-framing strands. "
    "Preserve her realistic curvy hourglass body: "
    "full rounded bust, compact torso, narrow defined waist, "
    "strong natural hip flare, rounded hips/glutes, "
    "fuller upper thighs, shapely legs, soft athletic tone, "
    "and believable feminine proportions. "
    "Her waist-to-hip curve should stay clear and natural "
    "across poses and outfits. "
    "Do not randomly slim her down, make her boxy, erase her waist, "
    "narrow her hips, flatten her curves, over-muscle her, "
    "exaggerate her body, or create doll-like/caricatured proportions. "
    "Generate a new in-scene photo of the same woman "
    "while allowing a new pose, outfit, crop, camera angle, "
    "lighting, and environment. "
    "Do not copy the exact reference expression, "
    "crop, lighting, or pose."
)

LENA_IDENTITY_BRIEF = LENA_MASTER_IDENTITY_BLUEPRINT

LENA_NEGATIVE_BRIEF = (
    "generic AI influencer face, different woman, redesigned face, "
    "beautified face, doll face, plastic face, poreless skin, "
    "over-smoothed skin, airbrushed face, wrong eye shape, "
    "wrong brow shape, wrong nose, wrong mouth, wrong jawline, "
    "wrong hairline, face identity drift, face swap look, "
    "pasted face, sticker face, source image copy, "
    "random body slimming, skinny body drift, body-build change, "
    "silhouette drift, boxy torso, erased waist, thick blocky waist, "
    "narrow hips, flattened curves, flat chest, reduced bust, "
    "over-enlarged bust, over-enlarged hips, exaggerated glutes, "
    "caricatured hourglass, BBL caricature, doll-like proportions, "
    "stretched legs, tiny torso, oversized head, "
    "distorted waist-to-hip ratio, overly muscular body, "
    "masculine build, "
    "shapeless clothing hiding body identity"
)

LENA_QA_STANDARD = (
    "Reject if Lena's face OR body would not pass human "
    "identity review against the approved element. "
    "Face and body identity must match before judging "
    "pose, outfit, setting, or style. "
    "Full pose range is allowed, but the same face/body identity "
    "must remain consistent across poses, angles, crops, "
    "outfits, and scenes."
)


LENA_PROMPT_QUALITY_STANDARD = (
    "Every Lena live prompt must be built like a "
    "high-end photographic art direction brief: "
    "specific lighting, concrete pose, detailed wardrobe, "
    "grounded setting, realistic skin/camera texture, "
    "and cinematic/social-media visual hierarchy. "
    "Do not compress prompts into generic scene fragments. "
    "Use the proven staircase prompt as the quality bar "
    "for specificity and realism, not as a mandatory style."
)

PROMPT_MIN_CHARS = prompt_limits.LEGACY_KLING_DIRECT_PROMPT_MIN_CHARS
PROMPT_MAX_CHARS = prompt_limits.LEGACY_KLING_DIRECT_PROMPT_MAX_CHARS


def validate_prompt(
    prompt: str, short_test: bool = False
) -> list[str]:
    """Return list of issues; empty = pass."""
    issues: list[str] = []
    n = len(prompt)
    if n > PROMPT_MAX_CHARS:
        issues.append(
            f"ABORT: prompt {n} chars exceeds {PROMPT_MAX_CHARS}"
        )
    if not short_test and n < PROMPT_MIN_CHARS:
        issues.append(
            f"WARN: prompt {n} chars below {PROMPT_MIN_CHARS}"
            " — too generic; use short_test=True to bypass"
        )
    return issues


# 10-part prompt structure for all direct_flash_ugc recipes.
DIRECT_FLASH_PROMPT_STRUCTURE = [
    "1. Capture style      — direct flash / phone UGC / vintage lo-fi 35mm snapshot feel",
    "2. Lena identity      — use Lena element as face, body, hair, identity reference; preserve natural proportions",
    "3. Emotion/expression — messy joy, unbothered confidence, candid mid-moment",
    "4. Pose/framing       — full-body or head-to-upper-thigh, off-center, imperfect crop",
    "5. Outfit hook        — specific garment detail, head-to-heel visible, no generic description",
    "6. Accessory/prop     — quirky statement piece, specific and scene-appropriate, no readable logos",
    "7. Specific setting   — named non-generic location with environment detail",
    "8. Background realism — lived-in details, real objects implied in frame",
    "9. Caption/growth hook — opinion, question, or save-bait tied to setting or outfit",
    "10. Negative prompt   — no studio / editorial / portfolio aesthetics",
]

# 5-section art-direction brief structure for all new lane recipes.
HIGH_QUALITY_PROMPT_BRIEF_SECTIONS = [
    "1. Style & Lighting      — camera aesthetic, lighting quality, color grade, film/digital feel",
    "2. Subject & Pose        — expression, body language, gesture, gaze, head angle, energy",
    "3. Fashion & Accessories — exact garments (color, cut, fabric), accessories, prop hook",
    "4. Setting & Background  — location, foreground/midground/background detail, atmosphere",
    "5. Technical / Negative  — lane-specific negative constraints (from LANE_NEGATIVES[lane_id])",
]

LANE_NEGATIVES: dict[str, str] = {
    "direct_flash_ugc": (
        "studio look, softbox look, editorial campaign look, "
        "portrait-mode blur, over-retouched skin, "
        "unsafe wardrobe drift, platform-unsafe styling"
    ),
    "moody_90s_flash_editorial": (
        "sterile studio look, airbrushed skin, plastic skin, "
        "modern ad gloss, unsafe wardrobe drift, platform-unsafe styling"
    ),
    "joyful_35mm_boxing_gym_flash": (
        "studio look, softbox look, polished model-shoot finish, "
        "over-retouched skin, unsafe wardrobe drift, platform-unsafe styling"
    ),
    "sun_drenched_90s_roadtrip_film": (
        "studio look, softbox look, phone-flash look, plastic skin, "
        "sterile backdrop, unsafe wardrobe drift, platform-unsafe styling"
    ),
    "luxury_fit_check_flash": (
        "studio look, softbox look, editorial campaign gloss, "
        "over-retouched skin, unsafe wardrobe drift, "
        "platform-unsafe styling"
    ),
    "beauty_maintenance_glam": (
        "editorial campaign look, clinical sterile set, "
        "over-retouched skin, unsafe wardrobe drift, "
        "platform-unsafe styling"
    ),
    "social_night_out_flash": (
        "studio look, softbox look, over-retouched skin, "
        "unsafe wardrobe drift, platform-unsafe styling"
    ),
    "street_style_errand_glam": (
        "studio look, softbox look, editorial campaign gloss, "
        "unsafe wardrobe drift, platform-unsafe styling"
    ),
    "home_luxury_lifestyle": (
        "studio look, softbox look, sterile set, "
        "over-retouched skin, unsafe wardrobe drift, "
        "platform-unsafe styling"
    ),
}

# Kling-safe recipes: each lane has a human reason, text-safe setting, wardrobe, camera style, and caption.
LANE_RECIPES: dict[str, dict[str, Any]] = {
    "morning stretch": {
        "pillar": "fitness_movement",
        "setting": "clean apartment workout corner, yoga mat, soft morning window light, neutral curtains, one plant, no books, no screens, no labels",
        "human_reason": "Lena paused during a gentle morning stretch because the light looked good and the moment felt calm.",
        "action": "seated or standing stretch, relaxed shoulders, natural posture, soft smile, hands simple and visible",
        "wardrobe": "fitted matching activewear set: sports bra or fitted crop top with high-waisted leggings, cropped zip hoodie nearby, small gold hoops, natural polished makeup",
        "shot": "vertical phone-camera lifestyle photo, full body or three-quarter body, clean framing, realistic skin texture",
        "caption": "slow start, better stretch #morningvibe #wellness #softlife #stretching #dailyvibe #movement",
        "overlay_hook": None,
    },
    "smoothie prep": {
        "pillar": "home_life_cooking",
        "setting": "clean home kitchen counter with a plain glass, fruit, blender turned away with no visible logo, warm daylight, no packaging, no labels, no screens",
        "human_reason": "Lena was making a smoothie before getting ready and someone caught the quick kitchen moment.",
        "action": "standing at the counter, one hand near a plain glass, candid small smile, natural weight shift",
        "wardrobe": "soft ribbed knit top with relaxed trousers, hair loosely styled, minimal jewelry",
        "shot": "vertical candid kitchen lifestyle photo, waist-up to three-quarter framing, phone-camera realism",
        "caption": "smoothie first, decisions later #wellness #kitchenvibe #softlife #morningroutine #dailyvibe #healthyish",
        "overlay_hook": "When the smoothie actually fixes your mood",
    },
    "apartment reset": {
        "pillar": "wellness_recovery",
        "setting": "clean apartment corner after tidying up, neutral sofa, folded blanket, warm lamp, one plant, no books, no screens, no labels",
        "human_reason": "Lena finished resetting her apartment and took a quiet photo because the room finally felt peaceful.",
        "action": "sitting casually on the sofa arm or standing near the lamp, brushing hair back, relaxed real smile",
        "wardrobe": "fitted lounge set: off-shoulder knit top or fitted tank with soft lounge pants, natural makeup, hair down naturally",
        "shot": "vertical phone-camera lifestyle photo, candid but polished, warm indoor light",
        "caption": "resetting the room reset my brain #apartmentvibe #softlife #wellness #dailyvibe #cozyhome #resetday",
        "overlay_hook": "POV: trying to romanticize resetting your apartment",
    },
    "soft skincare morning": {
        "pillar": "wellness_recovery",
        "setting": "bedroom vanity area with soft daylight, plain towel, minimal unbranded skincare objects turned away, no labels, no mirror text, no phone UI",
        "human_reason": "Lena took a soft morning skincare photo before the day started.",
        "action": "upper-body candid, hair clipped back, one hand near cheek, gentle sleepy smile",
        "wardrobe": "fitted tank or off-shoulder knit top, hair naturally clipped back, tiny earrings, clean natural skin texture",
        "shot": "vertical close lifestyle portrait, soft light, real skin texture, no mirror selfie UI",
        "caption": "morning skin check #skincare #morningroutine #softlife #glow #wellness #dailyvibe",
        "overlay_hook": None,
    },
    "outfit check": {
        "pillar": "outfit_soft_glam",
        "setting": "simple apartment entryway with clean wall, small bench, soft daylight, no mirror text, no signs, no labels",
        "human_reason": "Lena snapped a quick outfit photo before leaving for errands.",
        "action": "full outfit visible, one foot slightly forward, hand adjusting sleeve or bag strap, confident casual posture",
        "wardrobe": "structured cropped jacket, fitted top, relaxed tailored trousers, clean sneakers or low heels, small gold hoops",
        "shot": "vertical full-body phone photo taken by someone close to her, no phone visible, clean framing",
        "caption": "errands but make it cute #ootd #outfitcheck #citystyle #everydaystyle #softglam #dailylook",
        "overlay_hook": None,
    },
    "balcony pose": {
        "pillar": "body_confidence_lifestyle",
        "setting": "private balcony with soft daylight, blurred city or greenery in the distance, simple railing, no signs, no logos, no readable background",
        "human_reason": "Lena stepped onto the balcony after getting dressed and took a quick confidence photo.",
        "action": "relaxed standing pose, shoulders angled, one hand at waist or hair, calm confident expression",
        "wardrobe": "sleek fitted active-lifestyle set with a cropped open jacket or fitted lightweight layer, minimal jewelry, polished casual styling",
        "shot": "vertical body-confidence lifestyle photo, three-quarter to full body, background naturally out of focus, phone-captured feel",
        "caption": "just needed the light for a second #bodyconfidence #ootd #softglam #lifestyle #dailylook #cityvibe",
        "overlay_hook": None,
    },
    "poolside lifestyle": {
        "pillar": "pool_beach_outdoor_lifestyle",
        "setting": "quiet private poolside patio with stone tile, water reflections, simple lounge chair, plants, no signs, no logos, no other faces",
        "human_reason": "Lena took a calm poolside recovery photo after a movement session.",
        "action": "walking slowly near the pool or sitting on a lounge edge, sunglasses in hand, relaxed confident expression",
        "wardrobe": "tasteful sporty swim or fitted active set with an open linen shirt, no logos, simple jewelry",
        "shot": "vertical bright lifestyle photo, full body or three-quarter, natural daylight, clean composition",
        "caption": "recovery counts too #poolside #wellness #softlife #bodyconfidence #lifestyle #glow",
        "overlay_hook": None,
    },
    "city errands": {
        "pillar": "outfit_soft_glam",
        "setting": "quiet tree-lined sidewalk or plain courtyard, background safely blurred, no storefront signs, no license plates, no posters",
        "human_reason": "Lena took a quick photo during errands because the outfit and light worked.",
        "action": "walking slowly with a plain unbranded cup or small bag, soft smile, natural motion",
        "wardrobe": "fitted long-sleeve top, tailored trousers, cropped jacket, clean sneakers, small hoops",
        "shot": "vertical candid street-style photo, background blurred enough to avoid text, phone-camera realism",
        "caption": "tiny walk fixed everything #citystyle #ootd #lifestyle #dailyvibe #softlife #errands",
        "overlay_hook": None,
    },
    "dance clip": {
        "pillar": "dance_reels",
        "setting": "clean apartment living room with furniture pushed back, warm lamp, curtains, plant, clean wall, no screens, no text, no signage",
        "human_reason": "Lena made a short movement clip at home before choosing music for the post.",
        "action": "full body ready to move, feet fully in frame, hands relaxed, playful confident expression",
        "wardrobe": "movement-friendly fitted top with relaxed trousers, small hoops, hair down with natural movement",
        "shot": "vertical locked phone camera at chest height, full body visible, clean floor space",
        "caption": "saving this one for the right song #dancevibes #movement #reels #homevibe #wellness #dailyvibe",
        "overlay_hook": "POV: you said you were just stretching",
        "video_motion": "5 to 10 second smooth social movement: step-touch footwork, shoulder accents, small hip pop, hair movement, playful hand gesture, clean ending pose. Keep motion simple, stable, and music-ready.",
    },
    "stretch flow": {
        "pillar": "fitness_movement",
        "setting": "minimal apartment workout corner with yoga mat, neutral wall, warm daylight, one plant, no mirror, no screens, no text",
        "human_reason": "Lena recorded a short stretch flow as part of her wellness routine.",
        "action": "full body visible in a clean stretch-start position, natural posture, calm focused expression",
        "wardrobe": "simple matching activewear set, no logos, hair tied back softly, small earrings",
        "shot": "vertical locked phone camera, full body, no camera movement",
        "caption": "mobility before everything #stretchflow #wellness #movement #fitnessvibe #softlife #dailyvibe",
        "overlay_hook": "Reminder: start smaller than you think",
        "video_motion": "controlled stretch flow with slow side reach, soft body fold, step back, shoulder roll, and clean final pose. No fast spins, no props, no camera movement.",
    },
    "light workout": {
        "pillar": "fitness_movement",
        "setting": "clean home workout space with mat, small unbranded dumbbells, plain wall, no screen, no logos, no text",
        "human_reason": "Lena made a quick light workout clip at home.",
        "action": "full body visible, simple athletic stance, hands clear, feet planted",
        "wardrobe": "matching activewear set with neutral tones, no logos, hair tied back",
        "shot": "vertical locked phone camera, full body visible, bright clean light",
        "caption": "quick one still counts #fitness #movement #homeworkout #wellness #dailyvibe #bodyconfidence",
        "overlay_hook": "Nobody regrets the workout they almost skipped",
        "video_motion": "simple low-impact workout movement: side step, controlled squat pulse, arm reach, shoulder roll, reset stance. Keep hands and feet inside frame.",
    },
    "wellness movement": {
        "pillar": "fitness_movement",
        "setting": "bright apartment corner with yoga mat and curtains, no text, no screens, no signage, clean floor",
        "human_reason": "Lena captured a soft movement moment before choosing the music.",
        "action": "standing with gentle motion-ready posture, relaxed hands, warm expression",
        "wardrobe": "fitted activewear set: crop top or sports bra with high-waisted leggings, no logos",
        "shot": "vertical locked phone camera, full body, clean background",
        "caption": "moving slow still counts #wellness #movement #softlife #reels #dailyvibe #stretching",
        "overlay_hook": "POV: low energy but still showing up",
        "video_motion": "slow wellness movement with step-touch, arm sweep, shoulder roll, gentle turn, and natural smile at the end.",
    },
    "pov wellness joke": {
        "pillar": "humor_pov",
        "setting": "clean kitchen or apartment corner, one simple prop like a smoothie glass or folded towel, no labels, no screens, no text",
        "human_reason": "Lena made a funny wellness-style post out of a normal daily moment.",
        "action": "playful facial expression, slightly exaggerated but still natural pose, holding one plain prop",
        "wardrobe": "soft lounge set or activewear, no logos, hair casually styled",
        "shot": "vertical phone-camera candid, waist-up or three-quarter, clean background",
        "caption": "acting like this fixed my whole life #pov #wellnesshumor #softlife #dailyvibe #lifestyle #relatable",
        "overlay_hook": "POV: one healthy choice and suddenly you have your life together",
    },
    "kitchen moment": {
        "pillar": "home_life_cooking",
        "setting": "warm clean kitchen corner with simple plate or smoothie glass, no packaging, no labels, no screens, no text",
        "human_reason": "Lena turned a simple kitchen moment into a warm lifestyle post.",
        "action": "leaning on the counter with a small smile, one hand near a glass or plate, relaxed shoulders",
        "wardrobe": "soft fitted top, relaxed trousers, small jewelry, natural makeup",
        "shot": "vertical phone-camera lifestyle photo, warm indoor light, realistic texture",
        "caption": "made something simple and called it balance #kitchenvibe #wellness #softlife #lifestyle #dailyvibe #healthyish",
        "overlay_hook": None,
    },
    "gym recovery": {
        "pillar": "wellness_recovery",
        "setting": "quiet gym recovery corner or stretching mat area with plain wall, no mirrors, no signs, no screens, no logos",
        "human_reason": "Lena took a calm recovery photo after light movement.",
        "action": "seated stretch or kneeling recovery pose, relaxed face, hands simple and visible",
        "wardrobe": "matching activewear, no logos, hair tied back, minimal jewelry",
        "shot": "vertical candid fitness-lifestyle photo, clean background, soft athletic realism",
        "caption": "the cooldown is the main character #fitness #recovery #wellness #movement #dailyvibe #bodyconfidence",
        "overlay_hook": None,
    },
    "coffee walk": {
        "pillar": "body_confidence_lifestyle",
        "setting": "quiet courtyard or tree-lined path with background blurred, plain unbranded cup, no storefront signs, no plates, no posters",
        "human_reason": "Lena took a quick coffee-walk photo while getting outside for a reset.",
        "action": "walking slowly with a plain cup, cardigan or jacket moving naturally, soft smile",
        "wardrobe": "active-lifestyle outfit with a soft jacket, clean sneakers, small hoops, no logos",
        "shot": "vertical candid street-style photo, safe blurred background, phone-camera realism",
        "caption": "walked for coffee, stayed for the reset #coffeewalk #wellness #citystyle #softlife #dailyvibe #lifestyle",
        "overlay_hook": None,
    },
    "evening skincare": {
        "pillar": "wellness_recovery",
        "setting": "bedroom dresser or bathroom vanity with warm clean light, plain towel, unbranded objects turned away, no labels, no mirror text, no phone UI",
        "human_reason": "Lena ended the day with a quiet skincare moment.",
        "action": "upper-body candid, hair clipped back, hand near cheek, calm gentle smile",
        "wardrobe": "fitted tank or off-shoulder top, hair naturally clipped back, tiny earrings, clean natural skin texture",
        "shot": "vertical intimate camera-roll portrait, warm evening light, no mirror UI",
        "caption": "night routine doing the heavy lifting #skincare #nightroutine #wellness #softlife #glow #eveningvibe",
        "overlay_hook": None,
    },
    "simple dinner": {
        "pillar": "home_life_cooking",
        "setting": "small home dining or kitchen corner with warm light, simple plate, glass of water, linen napkin, no packaging, no bottle labels, no screens",
        "human_reason": "Lena made a simple dinner at home and took a warm evening photo.",
        "action": "sitting at a small table or leaning against the counter, relaxed smile, one hand near plate or glass",
        "wardrobe": "soft knit top with relaxed trousers, hair down, minimal jewelry",
        "shot": "vertical warm lifestyle photo, intimate camera-roll feeling, realistic indoor light",
        "caption": "made dinner and called it a personality trait #homecooking #eveningvibe #softlife #wellness #cozyhome #dailyvibe",
        "overlay_hook": "When the simple dinner actually hits",
    },
    "sauna/recovery": {
        "pillar": "wellness_recovery",
        "setting": "clean spa-like recovery corner with warm wood texture, towel, soft light, no signage, no labels, no other people",
        "human_reason": "Lena captured a quiet recovery moment after movement.",
        "action": "seated relaxed pose with towel nearby, calm face, shoulders relaxed, no heavy posing",
        "wardrobe": "tasteful neutral recovery wrap or activewear layer, no logos",
        "shot": "vertical wellness lifestyle photo, warm soft light, clean minimal composition",
        "caption": "recovery counts too #recovery #wellness #softlife #eveningvibe #bodyconfidence #dailyvibe",
        "overlay_hook": None,
    },
    "wind-down stretch": {
        "pillar": "wellness_recovery",
        "setting": "bedroom or living room floor with soft lamp light, yoga mat, curtains, no screens, no labels, no text",
        "human_reason": "Lena did a small wind-down stretch before ending the day.",
        "action": "gentle seated stretch, relaxed breathing, natural calm expression",
        "wardrobe": "soft lounge activewear, no logos, hair loosely tied",
        "shot": "vertical warm camera-roll photo, three-quarter or full body, cozy evening realism",
        "caption": "ending the day softer #winddown #stretching #wellness #softlife #eveningvibe #dailyvibe",
        "overlay_hook": "POV: calling five minutes of stretching a reset",
    },
    "mirror fit check": {
        "pillar": "fit_check_mirror",
        "setting": "bedroom or entryway with full-length mirror, soft daylight or warm lamp, no phone UI in reflection, no readable text",
        "human_reason": "Lena checked her outfit before leaving and the fit was worth a photo.",
        "action": "full body visible in mirror, one hand adjusting outfit or touching hair, confident casual expression, slight body angle",
        "wardrobe": "polished fitted mini dress, sleek co-ord set, or bodycon — full outfit must look expensive and intentional in the mirror; one luxury accent: designer-style mini bag, high-end sunglasses, sleek heels, or delicate gold jewelry",
        "shot": "vertical phone photo in mirror, full outfit from head to mid-thigh, no phone visible in frame",
        "caption": "approved by nobody but me #fitcheck #ootd #outfitcheck #mirrorselfie #style",
        "overlay_hook": None,
    },
    "gym body photo": {
        "pillar": "fit_check_mirror",
        "setting": "gym near a plain painted wall, no branded machines or visible screens, neutral gym light",
        "human_reason": "Lena hit the gym and caught a quick body photo mid-session.",
        "action": "confident athletic stance near the wall, gym outfit fully visible, slight body angle for silhouette",
        "wardrobe": "fitted sports bra and high-waist leggings, or fitted crop top and athletic shorts — no visible logos, premium sneakers, small gold hoops",
        "shot": "vertical candid gym portrait, realistic gym light, background slightly out of focus",
        "caption": "showed up and that counts #gym #fitness #gymday #fitlife #bodycheck",
        "overlay_hook": None,
    },
    "getting-ready look": {
        "pillar": "fit_check_mirror",
        "setting": "bedroom or walk-in closet, warm lamp, outfit visible on rack or chair, no labels, no readable text",
        "human_reason": "Lena was mid-getting-ready and the light caught her before she finished.",
        "action": "three-quarter body visible, adjusting earring or pulling jacket onto shoulder, candid getting-ready energy",
        "wardrobe": "going-out outfit being assembled — fitted dress or mini skirt with top; statement jewelry; luxury-inspired clutch or mini bag visible nearby",
        "shot": "vertical lifestyle portrait, warm bedroom light, candid camera-roll realism",
        "caption": "in my getting ready era #gettingready #outfitcheck #ootd #getreadywithme",
        "overlay_hook": None,
    },
    "going-out look": {
        "pillar": "going_out_niche",
        "setting": "apartment entryway or doorway, warm ambient light, clean wall or door, no readable text or logos",
        "human_reason": "Lena was heading out and the outfit deserved a photo before she left.",
        "action": "full outfit visible, confident body angle, hand on hip or touching hair, bold expression",
        "wardrobe": "classy luxury-styled going-out dress, bodycon mini, or sleek dressy co-ord — structured blazer over fitted bodysuit optional; sleek heels, delicate gold jewelry, glossy lip, designer-style mini bag or evening clutch",
        "shot": "vertical full-body or three-quarter portrait, warm doorway light, clean framing",
        "caption": "going out for real this time #nightout #ootd #outfitcheck #goingout",
        "overlay_hook": None,
    },
    "street baddie": {
        "pillar": "street_baddie_niche",
        "setting": "quiet tree-lined sidewalk or plain urban backdrop, background safely blurred, no readable signs or license plates",
        "human_reason": "Lena was on errands and the fit was too strong not to stop for a photo.",
        "action": "standing or mid-step, full outfit visible head to thigh, confident casual stance, slight body angle",
        "wardrobe": "fitted cargo pants and crop top, or leather-look mini skirt and fitted top — luxury-inspired sunglasses, designer-style mini bag or premium sneakers",
        "shot": "vertical candid street-style photo, background blurred, phone-camera realism",
        "caption": "errands then what #ootd #streetstyle #citystyle #baddiecheck #dailylook",
        "overlay_hook": None,
    },
    "parked car style": {
        "pillar": "street_baddie_niche",
        "setting": "passenger or driver seat of parked car, neutral interior, soft window light, car fully stationary, no visible license plates outside",
        "human_reason": "Lena caught a quick photo in the parked car before heading in.",
        "action": "seated facing camera, face and upper body visible, confident relaxed expression",
        "wardrobe": "whatever she is wearing out — outfit visible in framing; luxury-inspired sunglasses or statement hoops add fashion detail",
        "shot": "vertical close-medium portrait, soft window light from one side, natural car-interior framing",
        "caption": "running errands looking like this #carselfie #ootd #baddie #dailylook",
        "overlay_hook": None,
    },
    "bedroom outfit check": {
        "pillar": "fit_check_mirror",
        "setting": "bedroom facing camera, clean wall or doorframe behind, warm lamp or daylight, no mirror, no labels or text",
        "human_reason": "Lena took a final outfit photo before leaving.",
        "action": "full body or three-quarter visible, slight body angle, one hand at hip or hair, confident casual expression",
        "wardrobe": "fitted day outfit or going-out look — mini skirt, crop top, or fitted dress — heels or premium sneakers, statement hoops or necklace",
        "shot": "vertical lifestyle portrait, warm indoor light, clean framing, full outfit readable",
        "caption": "camera check before the door check #ootd #outfitcheck #style #confidence",
        "overlay_hook": None,
    },
    "beauty glow-up": {
        "pillar": "beauty_glow_niche",
        "setting": "bedroom vanity or bathroom counter, warm soft light, compact mirror, unbranded beauty objects, no labels readable, no phone UI",
        "human_reason": "Lena was doing her makeup and the glow was too good not to catch.",
        "action": "close-medium portrait, slight tilt toward light, fingers near cheek or applying lip gloss, natural glowing skin",
        "wardrobe": "focus is skin and face — delicate gold jewelry, glossy lip; compact mirror or premium lip gloss as prop",
        "shot": "vertical close-medium beauty portrait, warm vanity light, realistic skin texture",
        "caption": "glow check passed #glowup #beautycheck #softglam #makeuptips #dailyvibe",
        "overlay_hook": "she was just doing her makeup",
    },
    "product styling hook": {
        "pillar": "product_styling_niche",
        "setting": "clean apartment surface or outdoor backdrop, product as natural part of the scene, no logos visible, no ad-style composition",
        "human_reason": "Lena caught the detail of a fashion or beauty piece that completed the look.",
        "action": "holding or naturally wearing the item — designer-style mini bag at elbow, luxury-inspired sunglasses on, statement jewelry visible, or compact mirror in hand",
        "wardrobe": "full outfit visible with one fashion or beauty accent as natural detail: designer-style mini bag, luxury-inspired sunglasses, premium sneakers, statement hoops, bracelet, necklace, compact mirror, or lip gloss",
        "shot": "vertical lifestyle close-medium or detail shot, clean light, natural camera-roll feel",
        "caption": "found the one #style #ootd #fashiondetail #accessoriesoftheday #luxurystyling",
        "overlay_hook": None,
    },
    "looks expensive isn't": {
        "pillar": "affordable_luxury_series",
        "series_name": "Looks Expensive, Isn't",
        "visual_hook": "full polished outfit that reads designer/luxury but is affordably styled",
        "setting": "clean apartment entryway or plain outdoor backdrop, soft natural daylight, no labels or logos visible",
        "human_reason": "Lena styled a look that costs way less than it appears and had to document it.",
        "action": "full body or three-quarter shot, slight body angle, one hand touching outfit detail, confident direct expression",
        "wardrobe": "polished outfit that reads expensive — structured blazer or clean midi skirt, fitted top, sleek flat or low heel, one minimal accessory; no visible logos; neutral or earth-tone palette",
        "shot": "vertical full-body portrait, soft daylight, intentional off-center composition",
        "caption": "looks expensive, isn't 💛 #looksexpensive #affordablestyle #ootd #fitcheck #stylingtips",
        "cta_hook": "drop a price guess in the comments — no looking it up",
        "overlay_hook": "looks expensive. isn't.",
    },
    "fit check before i leave": {
        "pillar": "fit_check_mirror",
        "series_name": "Fit Check Before I Leave",
        "visual_hook": "mirror full-body pre-departure fit with bold confident energy",
        "setting": "full-length mirror in bedroom or entryway, soft warm lamp or daylight, no phone UI in reflection, no readable text",
        "human_reason": "Lena did a final fit check before heading out and the look demanded a photo.",
        "action": "full body visible in mirror, hand adjusting outfit or touching hair, bold confident expression, slight body angle",
        "wardrobe": "polished fitted outfit — body-forward, intentional; one statement accessory: sleek heels, gold jewelry, or designer-style bag",
        "shot": "vertical phone photo in mirror, full outfit from head to thigh, no phone visible in frame",
        "caption": "fit check before i leave 🪞 #fitcheck #ootd #mirrorselfie #outfitcheck #style",
        "cta_hook": "would you wear this? drop your vibe 👇",
        "overlay_hook": "fit check before i leave",
    },
    "soft glam lip combo": {
        "pillar": "beauty_maintenance_series",
        "series_name": "Soft Glam Maintenance",
        "visual_hook": "close-medium beauty portrait with polished glossy lip and glowing skin",
        "setting": "bedroom vanity or bathroom counter, warm soft light, compact mirror or unbranded lip product nearby, no labels readable",
        "human_reason": "Lena found a lip combo that made her stop and document it before finishing the look.",
        "action": "close-medium portrait, applying or holding lip gloss, fingers near lips, soft glowing skin, slight tilt toward light",
        "wardrobe": "face-forward — delicate gold hoops, glossy lip, glowing skin texture; one unbranded beauty product in hand or nearby",
        "shot": "vertical close-medium beauty portrait, warm vanity or lamp light, real skin texture visible",
        "caption": "this lip combo has no business looking this good 💋 #softglam #lipcombos #beautycheck #glowup #makeuptips",
        "cta_hook": "drop a 💋 if you want the full combo breakdown",
        "overlay_hook": "this lip combo might be illegal",
    },
    "gym-to-glam reset": {
        "pillar": "gym_to_glam_series",
        "series_name": "Gym-to-Glam Reset",
        "visual_hook": "confident post-gym to glam transition — athletic energy meeting polished beauty",
        "setting": "gym near a plain wall OR clean apartment bedroom post-gym, transition lighting, no logos, no screens",
        "human_reason": "Lena went straight from the gym into her glam routine and caught the transition energy.",
        "action": "athletic body-confident stance with post-workout glow, OR getting-ready close-up mid-glam",
        "wardrobe": "fitted sports bra and high-waist leggings, gold hoops, natural post-gym glow; OR soft glam look with glossy lip mid-application",
        "shot": "vertical body-forward portrait, realistic gym or bedroom light, confident candid energy",
        "caption": "gym then glam. that's the routine. 💪✨ #gymtoglam #postworkout #fitcheck #grwm #fitnessgirl",
        "cta_hook": "gym before glam or nah? drop it 👇",
        "overlay_hook": "gym then glam is a lifestyle",
    },
    "things that make outfit cheap": {
        "pillar": "personality_hooks_series",
        "series_name": "Things That Make an Outfit Look Cheap",
        "visual_hook": "educational fashion hook — polished look with a specific styling tip visible in frame",
        "setting": "clean apartment entryway or neutral outdoor backdrop, background blurred, no labels or readable text",
        "human_reason": "Lena has strong opinions on what makes a look look cheap and shared the actual tip.",
        "action": "confident body pose highlighting the correct styling choice — bag placement, shoe scale, jewelry proportion, or fit detail",
        "wardrobe": "clean polished outfit showing the elevated version of the styling tip — fitted, no visible logos, one statement detail done right",
        "shot": "vertical body portrait or close detail shot, intentional framing, editorial-casual energy",
        "caption": "things that make your outfit look cheap (and the fix) 🚫💛 #stylingtips #outfittips #fashionadvice #looksexpensive",
        "cta_hook": "which one have you been guilty of? drop it below 👇",
        "overlay_hook": "things that make your outfit look cheap",
    },
    "pretty girl discipline": {
        "pillar": "personality_hooks_series",
        "series_name": "Pretty Girl Discipline",
        "visual_hook": "routine-focused body or beauty shot showing the consistent effort behind the polished look",
        "setting": "gym wall, apartment vanity, or clean outdoor sidewalk — wherever the routine happens",
        "human_reason": "Lena showed up for herself today — gym, skincare, or a routine reset — and looked this good doing it.",
        "action": "calm purposeful athletic or beauty pose, confident quiet expression, no over-performance",
        "wardrobe": "premium athletic set at the gym OR polished soft glam getting-ready look — intentional, minimal, fitted",
        "shot": "vertical candid lifestyle portrait, realistic scene light, confident calm energy",
        "caption": "pretty girl discipline is real and it's quiet 🤍 #prettygirldiscipline #routine #selfcare #fitcheck #lifestyle",
        "cta_hook": "what's your non-negotiable routine? drop it below 👇",
        "overlay_hook": "pretty girl discipline",
    },
    "save vs splurge": {
        "pillar": "affordable_luxury_series",
        "series_name": "Save vs Splurge",
        "visual_hook": "polished look that achieves full luxury energy at the save price point",
        "setting": "clean apartment entryway or outdoor neutral backdrop, consistent background for the comparison framing",
        "human_reason": "Lena compared a save vs splurge version of the same look and the save option surprised her.",
        "action": "full body or three-quarter portrait, polished confident stance, expression that sells the look",
        "wardrobe": "polished outfit that achieves luxury look — fitted silhouette, one elevated accessory, clean styling with no visible logos",
        "shot": "vertical full-body portrait, clean soft light, editorial-casual confidence",
        "caption": "save vs splurge and the save wins 💛 #savevssplurge #affordableluxury #ootd #stylingtips #looksexpensive",
        "cta_hook": "save or splurge person? be honest 👇",
        "overlay_hook": "save vs splurge: the save won",
    },
    "drugstore expensive energy": {
        "pillar": "affordable_luxury_series",
        "series_name": "Drugstore But Expensive Energy",
        "visual_hook": "close-medium beauty portrait showing a polished soft glam look achieved with affordable products",
        "setting": "vanity or bathroom counter, warm soft light, one product visible but label not readable, minimal clutter",
        "human_reason": "Lena's entire soft glam look used drugstore products that look anything but drugstore.",
        "action": "close-medium beauty portrait, glossy lip, soft glow skin, confident direct look, slight chin tilt",
        "wardrobe": "face-forward — polished soft glam makeup, delicate gold jewelry, glowing natural skin texture",
        "shot": "vertical close-medium beauty portrait, warm soft vanity light, real skin texture and pores visible",
        "caption": "drugstore but make it expensive 💋✨ #drugstorebeauty #softglam #affordablebeauty #looksexpensive #beautycheck",
        "cta_hook": "what's your go-to drugstore product? drop it 👇",
        "overlay_hook": "drugstore but expensive energy",
    },
    "grwm situation": {
        "pillar": "personality_hooks_series",
        "series_name": "GRWM For [Situation]",
        "visual_hook": "getting-ready moment anchored to a specific relatable social situation",
        "setting": "bedroom vanity or mirror, warm lamp, getting-ready objects nearby, no labels or screens visible",
        "human_reason": "Lena documented her getting-ready routine for a specific outing and the energy matched.",
        "action": "getting-ready candid — adjusting outfit, applying lip gloss, touching hair, or doing final mirror check",
        "wardrobe": "outfit assembled for the specific situation — polished casual for coffee, going-out glam for night, premium athletic for gym",
        "shot": "vertical lifestyle candid, warm bedroom or vanity light, camera-roll candid energy",
        "caption": "grwm for [specific situation] 💋 #grwm #getreadywithme #ootd #gettingready #lifestylevibe",
        "cta_hook": "what do you wear for this? drop it below 👇",
        "overlay_hook": "grwm: [specific situation]",
    },
    "outfit for when": {
        "pillar": "personality_hooks_series",
        "series_name": "Outfit For When [Situation]",
        "visual_hook": "full-body fit styled specifically around a relatable social or emotional scenario",
        "setting": "apartment entryway, outdoor sidewalk, or doorway — clean neutral backdrop, background naturally blurred",
        "human_reason": "Lena had a specific vibe to dress for and built the perfect outfit around it.",
        "action": "full body or three-quarter portrait, confident stance, expression matching the situation energy, slight body angle",
        "wardrobe": "outfit intentionally styled for the specific scenario — polished, body-forward, one statement element that reads as intentional",
        "shot": "vertical full-body portrait, natural light, candid-editorial energy, off-center composition",
        "caption": "outfit for when [specific situation] 💛 #ootd #outfitfor #fitcheck #stylingtips #fashionhook",
        "cta_hook": "what situation do you need an outfit for? drop it 👇",
        "overlay_hook": "outfit for when [specific situation]",
    },

    # --- direct_flash_ugc: 11 scene recipes ---
    "boxing gym flash fit-check": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "vibrant direct-flash phone photo of Lena in a boxing gym, full outfit visible head to heel, gritty athletic energy — yellow boxing-glove mini bag carried as an accent piece or wrapped hand tape worn as a wrist accessory",
        "setting": "boxing gym — punching bags, ring ropes, scuffed concrete floor, no readable signage",
        "human_reason": "Lena stopped mid-training and someone grabbed her phone for a fit check — the gym is the backdrop, not the subject.",
        "action": "mid-stance confident pose, chin up, one hand on hip, glossy red mouthguard case or yellow mini bag in other hand, direct camera eye contact, slight smirk",
        "wardrobe": "premium fitted athletic set or unexpectedly dressed-up look — yellow boxing-glove mini bag or wrapped wrist tape as the statement prop; outfit contrast with gritty gym is the hook",
        "shot": "vibrant direct on-camera flash, vertical full-body or head-to-upper-thigh, heavy analog grain, warm slightly saturated color, casual imperfect crop, caught-by-a-friend phone energy",
        "caption": "the gym didn't ask for this fit but it got it anyway 🥊 #fitcheck #gymfit #ootd #luxurybaddie #outfitideas",
        "cta_hook": "what's your unexpected fit-check location? 👇",
        "overlay_hook": "fit check: boxing gym edition",
    },
    "laundromat flash fit-check": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone photo of Lena in a laundromat, dressed way too well for laundry day — metallic mini bag resting on top of a dryer, oversized claw clip in hair",
        "setting": "laundromat — rows of stacked dryers, fluorescent overhead light, detergent boxes, hard chairs, utilitarian and unglamorous background",
        "human_reason": "Lena came to do laundry and showed up dressed like she's going somewhere better. Someone had to document it.",
        "action": "leaning against a dryer, casual confident expression, one hand resting on the metallic mini bag on the dryer, oversized claw clip in hair adding height",
        "wardrobe": "elevated outfit overdressed for laundromat context — metallic mini bag as statement prop on dryer, oversized claw clip, going-out look or polished fit with premium sneakers or heels",
        "shot": "direct on-camera flash, fluorescent and flash mixed, vertical full-body, visible noise grain, natural slightly washed-out color, imperfect framing",
        "caption": "came to do laundry. wore this. 💅 #laundryday #fitcheck #ootd #luxurybaddie #outfitideas",
        "cta_hook": "overdressed for laundry or is this just normal? 👇",
        "overlay_hook": "laundromat fit check",
    },
    "corner store flash errand": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone snapshot of Lena on a late errand at a corner store — tiny chrome shoulder bag, novelty keychain charm visible, iced drink in hand",
        "setting": "corner store or bodega — refrigerated drink cases, fluorescent ceiling, snack aisle or counter visible in background, no readable logos or signage",
        "human_reason": "Lena ran out for something small dressed like this. Her friend caught it.",
        "action": "holding an iced drink in one hand, tiny chrome shoulder bag on the other wrist, novelty keychain dangling, direct eye contact, casual-confident expression",
        "wardrobe": "polished casual or elevated athleisure — tiny chrome shoulder bag and novelty keychain charm as the quirky accessory layer; looks too good for a corner store run",
        "shot": "direct on-camera flash mixed with fluorescent overhead, vertical full-body or three-quarter, analog grain, imperfect crop, camera-roll energy",
        "caption": "late errand and this is what i wore 😐 #cornerstore #fitcheck #ootd #latenightenergy #luxurybaddie",
        "cta_hook": "do you also dress up for errands or just me? 👇",
        "overlay_hook": "late errand. wore this.",
    },
    "parking garage flash outfit": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone photo in a concrete parking garage — reflective silver bag, bold oversized sunglasses, car keys dangling from one finger",
        "setting": "parking garage — concrete pillars, painted parking lines, yellow caution stripes or level numbers, low ambient overhead, no readable text",
        "human_reason": "Lena paused in the parking garage before wherever she was going. The concrete and the flash made it look intentional.",
        "action": "standing near a pillar, confident body-forward pose, reflective silver bag on shoulder, oversized sunglasses pushed up or worn, car keys dangling casually from one finger",
        "wardrobe": "full going-out look or premium casual — reflective silver bag and bold oversized sunglasses as the statement accessories; car keys as the casual prop detail",
        "shot": "direct on-camera flash, dark garage ambient, vertical full-body, heavy grain, harsh shadow on concrete behind Lena, imperfect framing",
        "caption": "the parking garage is giving today 📸 #fitcheck #parkinggarage #ootd #luxurybaddie #outfitideas",
        "cta_hook": "unexpected locations hit different — where's your best fit-check spot? 👇",
        "overlay_hook": "parking garage fit check",
    },
    "diner booth flash": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone snapshot of Lena in a classic diner booth — cherry-red mini bag on the table, glossy lip compact open nearby, fries or milkshake as a casual prop",
        "setting": "classic diner — red vinyl booth, chrome napkin holder, sugar and condiment cluster on table, pie case or counter in background, no readable menus",
        "human_reason": "Post-night-out diner stop. Someone pulled out their phone mid-booth. This is what that looks like.",
        "action": "seated in booth, leaning forward with elbows on table, cherry-red mini bag in frame, milkshake or fries held casually, candid expression — laughing or unbothered direct look",
        "wardrobe": "going-out outfit still intact — cherry-red mini bag and open lip compact on the table as the prop layer; natural hair flyaways, gloss still on, statement top or jewelry visible",
        "shot": "direct on-camera flash, diner overhead mixed with flash, vertical straight-on, grain and noise visible, slightly off-center, candid mid-moment energy",
        "caption": "late diner booth, still in the fit 💋 #dinerbooth #latenightvibes #fitcheck #ootd #goingoutfit",
        "cta_hook": "late-night diner order? drop it 👇",
        "overlay_hook": "late diner check",
    },
    "gym locker room outfit reset": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone shot of Lena mid-gym-to-glam reset in a locker room — gym bag with a satin scarf tied on the handle, lip gloss tube in hand, sleek water bottle visible",
        "setting": "gym locker room — metal lockers, tiled floor, gym bag visible, mirror edge or bench in frame, utilitarian and real",
        "human_reason": "Lena transitioned from gym to polished and documented the mid-transformation in the locker room.",
        "action": "mid-change confidence — applying lip gloss at locker room mirror, gym bag with satin scarf tied on handle over shoulder, sleek water bottle in frame as prop",
        "wardrobe": "gym-to-glam transition — satin scarf tied on gym bag handle as statement detail, lip gloss tube as the accessory in action, polished going-somewhere look freshly on",
        "shot": "direct on-camera flash or locker room fluorescent, vertical mirror selfie or friend-captured, visible grain, imperfect background clutter, raw real energy",
        "caption": "gym-to-wherever reset 💪✨ no one is safe #gymtoglam #lockerroom #fitcheck #grwm #gymfit",
        "cta_hook": "gym-to-glam or stay in the fit? 👇",
        "overlay_hook": "locker room reset",
    },
    "dance studio mirror flash": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone photo in a dance studio — leg warmers pushed down to ankles, ribbon hair tie, tiny shoulder bag hanging from ballet barre in background",
        "setting": "dance studio — mirrored wall full-length, sprung wood floor, ballet barre visible, open high-ceiling space",
        "human_reason": "Dance class or solo studio session — someone grabbed the phone and fired a flash shot mid-session.",
        "action": "mid-pose or confident stance facing mirror, leg warmers pushed to ankles, ribbon hair tie in hair, tiny shoulder bag hanging from barre visible in background, direct eye contact through mirror",
        "wardrobe": "premium athletic or dance-appropriate set — leg warmers as texture detail, ribbon hair tie, tiny shoulder bag on barre as the quirky scene prop",
        "shot": "direct on-camera flash bounced off mirror wall, vertical full-body, visible flash reflection in mirror, heavy analog grain and warmth, energy over precision",
        "caption": "studio hours 💫 #dancestudio #fitcheck #ootd #bodyconfidence #softglam",
        "cta_hook": "mirror selfie or dance studio flash — which hits harder? 👇",
        "overlay_hook": "dance studio flash",
    },
    "apartment hallway dressed flash": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone photo of Lena fully dressed in apartment hallway — statement mini bag, oversized sunglasses pushed up on head, keyring charm dangling from hand",
        "setting": "apartment hallway — hallway light strips, numbered doors, fire extinguisher on wall, carpet or tile floor, slightly cramped real corridor",
        "human_reason": "Lena got fully ready, stepped into the hallway for photos, and had no destination. The hallway became the runway.",
        "action": "hand on hip, statement mini bag on wrist, oversized sunglasses pushed up on head, keyring charm dangling casually — full-body visible, dressed-for-no-reason is the joke",
        "wardrobe": "full going-out look or luxury casual — statement mini bag, oversized sunglasses on head, keyring charm as the quirky hand prop; mundane hallway contrast is the entire hook",
        "shot": "direct on-camera flash, harsh hallway fluorescent mixed with flash, vertical full-body, heavy grain, slightly cramped composition, imperfect crop",
        "caption": "dressed like this and the destination is the hallway 💁‍♀️ #fitcheck #ootd #apartmentlife #luxurybaddie #noplans",
        "cta_hook": "hallway runway or entryway runway? 👇",
        "overlay_hook": "hallway runway. nowhere to be.",
    },
    "bathroom party flash": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash bathroom mirror photo, going-out energy — lip gloss tube in hand mid-application, tiny clutch on counter edge, statement earrings catching the flash",
        "setting": "house or venue bathroom — small mirror, overhead light, tile backsplash, edge of counter in frame, real and unglamorous",
        "human_reason": "Pre-going-out bathroom mirror check. The flash was already on. This is what happened.",
        "action": "mirror selfie pose, lip gloss tube in hand mid-application or just finished, tiny clutch on counter edge visible, statement earrings catching the flash light, phone visible in reflection",
        "wardrobe": "full going-out look — statement earrings as the flash-catch detail, tiny clutch as the counter prop, lip gloss tube in hand; the bathroom is the only unglamorous element in frame",
        "shot": "direct flash in bathroom mirror, harsh overhead mixed with flash, vertical mirror selfie, grain, phone visible in reflection, imperfect and raw",
        "caption": "bathroom mirror pre-check ✅ #bathroomcheck #fitcheck #ootd #goingoutfit #softglam",
        "cta_hook": "bathroom mirror or entryway mirror — where's your pre-check? 👇",
        "overlay_hook": "bathroom pre-check",
    },
    "vintage arcade flash": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone photo of Lena in a vintage arcade — neon-colored mini bag, token cup in hand, playful hair clip or oversized claw clip catching the neon glow",
        "setting": "vintage arcade — classic arcade cabinets, neon sign glow, dark ambient ceiling, coin-op machines, low colored lights, no readable screen text",
        "human_reason": "Lena at an arcade. The neon and the flash created something. Someone caught it.",
        "action": "standing or leaning against arcade cabinet, token cup in one hand, neon-colored mini bag on wrist or shoulder, playful claw clip in hair, direct or slightly-away camera look",
        "wardrobe": "elevated casual or dressed-up look — neon mini bag as the color accent against dark arcade background, token cup and claw clip as the scene-specific props",
        "shot": "direct on-camera flash mixed with neon arcade glow, vertical full-body or three-quarter, warm color saturation from neon, heavy analog grain, dark background pops against flash",
        "caption": "arcade era 🕹️ the fit came too #arcadefit #fitcheck #ootd #neonvibes #luxurybaddie",
        "cta_hook": "what's your go-to arcade game? 👇",
        "overlay_hook": "arcade fit check",
    },
    "cafe patio direct-flash": {
        "pillar": "direct_flash_ugc",
        "series_name": "Direct Flash Fit Moment",
        "visual_hook": "direct-flash phone photo on a cafe patio — iced coffee in hand, charm bag on wrist or table, sunglasses worn or pushed up, glossy lip compact resting nearby",
        "setting": "cafe patio — outdoor chairs and tables, string lights or awning visible, other tables in background naturally out of focus, iced coffee or drink present",
        "human_reason": "Lena was on the patio and someone fired a quick flash photo before the light changed. This is that photo.",
        "action": "seated or standing at outdoor table, iced coffee in hand, charm bag on wrist or on table, sunglasses on face or pushed up on head, candid relaxed expression",
        "wardrobe": "elevated cafe casual — charm bag as the statement wrist accessory, sunglasses and glossy lip compact as the layered prop detail; polished but not posed",
        "shot": "direct on-camera flash in daylight or patio shade, vertical full-body or three-quarter, natural outdoor color plus flash warmth, slight analog grain, imperfect candid crop",
        "caption": "patio flash moment ☀️ #cafepatio #fitcheck #ootd #outdoorvibes #softglam",
        "cta_hook": "patio season fit or indoor fit? 👇",
        "overlay_hook": "patio flash fit",
    },
    "grand staircase flash editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Lena stopped mid-ascent on an ornate staircase; "
            "the flash caught the moment — candid, editorial, "
            "straight from a 90s spread she didn't know she was in."
        ),
        "style_lighting": (
            "Moody vintage 35mm editorial. Direct on-camera flash "
            "hits her face and dress from below-center. "
            "Deep dark background falls sharply away from flash. "
            "Heavy analog grain over the full frame. "
            "Warm earthy palette, slightly desaturated — no modern sheen. "
            "Film burn edges. Exposed-grain shadow texture."
        ),
        "subject_pose": (
            "Lena mid-step on the staircase, weight on back foot, "
            "body three-quarters toward camera. "
            "Confident direct-camera gaze, slight jaw tilt, "
            "head angled softly. One hand rests lightly "
            "on the ornate banister. No fake smile — "
            "still, magnetic, slightly challenging expression."
        ),
        "fashion_accessories": (
            "Sophisticated patterned mini dress — jacquard or geometric "
            "print in warm earthy tones: deep burgundy, rust, or olive. "
            "Fitted through torso, hem above the knee. "
            "Stacked vintage bangles on the banister-resting wrist. "
            "Emerald-toned cocktail ring. Deep dark red nails. "
            "Pointed-toe mule or strappy heel. No visible logos."
        ),
        "setting_background": (
            "Ornate dark wood staircase, classical interior — "
            "carved banisters, aged stone or parquet floor below. "
            "Dim sconce light barely touches the deep background. "
            "Heavy shadows fill space beyond Lena. "
            "No readable signage. No modern furniture. "
            "Rich architectural detail. Atmospheric depth."
        ),
        "technical_keywords": (
            "35mm analog film, heavy grain, high noise, "
            "warm film burn edges, flash-lit foreground, "
            "underexposed shadowy background, "
            "warm slightly desaturated palette, "
            "1990s editorial photography, visible pores, "
            "not airbrushed, vintage fashion editorial"
        ),
        "caption": (
            "staircase energy \U0001F4F8 "
            "#editorial #vintagefashion #35mm "
            "#filmlook #fashionshot #ootd"
        ),
        "overlay_hook": None,
    },
    "dark wood hallway flash editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Lena was moving through the dark corridor "
            "when the flash fired — the paneled walls "
            "turned it into a frame from a 90s fashion story."
        ),
        "style_lighting": (
            "Vintage 35mm editorial. Direct flash cuts through "
            "a narrow dark-wood corridor. Face and body sharp; "
            "walls dissolve to shadow on either side. "
            "Heavy analog grain. Warm desaturated tones. "
            "Deep corridor contrast. No fill light."
        ),
        "subject_pose": (
            "Lena mid-stride facing camera, chin leveled, "
            "gaze direct and unhurried. "
            "One hand trailing lightly on the paneled wall. "
            "Shoulders relaxed, weight forward on front foot. "
            "Body angled three-quarters, movement implied."
        ),
        "fashion_accessories": (
            "Sleek black satin slip dress, thin straps, "
            "hem above the knee. Long gold chain necklace "
            "catching the flash. Black pointed-toe kitten heel. "
            "Minimal stacked rings. Deep matte red lip. "
            "Dark polished nails. No logos."
        ),
        "setting_background": (
            "Narrow dark wood-paneled corridor, wall sconces "
            "barely glowing behind her. "
            "Parquet or herringbone floor catching flash edge. "
            "Deep shadow fills the far end of the corridor. "
            "No signage. No modern fixtures. Tight and moody."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, corridor flash, "
            "high contrast, warm desaturated palette, "
            "underexposed background, dark wood paneling, "
            "1990s fashion photography, natural skin texture, "
            "not airbrushed, vintage editorial"
        ),
        "caption": (
            "hallway energy \U0001F4F8 "
            "#editorial #90sfashion #35mm "
            "#filmlook #ootd #nightout"
        ),
        "overlay_hook": None,
    },
    "velvet lounge corner flash editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Lena was settled into the velvet corner "
            "when the flash went off — a quiet lounge moment "
            "that became an accidental editorial shot."
        ),
        "style_lighting": (
            "Moody 35mm editorial. Flash fires to the side, "
            "catching her face and dress at an angle. "
            "Background velvet absorbs light, goes nearly black. "
            "Warm amber grain, cool midtone shift. "
            "Heavy noise in shadow zones. "
            "Rich 90s fashion-editorial color register."
        ),
        "subject_pose": (
            "Lena perched on the arm of a velvet chair, "
            "legs crossed, one elbow resting on the seatback. "
            "Body angled away from camera, face turning back — "
            "over-the-shoulder energy. "
            "Expression: aware, confident, half-caught."
        ),
        "fashion_accessories": (
            "Deep forest-green or midnight-blue velvet "
            "off-shoulder mini dress, fitted bodice. "
            "Long vintage drop earrings catching the flash. "
            "Thin gold chain at the collarbone. "
            "Dark aubergine nail color. Strappy black heel. "
            "No logos visible."
        ),
        "setting_background": (
            "Jewel-toned velvet sofa or armchair in a dim lounge. "
            "Ornate side lamp barely glowing in the background. "
            "Deep patterned rug partially visible below. "
            "Dark wood accents. No readable signage. "
            "Heavy, luxurious, atmospheric."
        ),
        "technical_keywords": (
            "35mm analog, heavy grain, side flash, "
            "jewel-tone interior, dark absorbing background, "
            "warm amber grain, underexposed shadows, "
            "1990s editorial fashion, natural skin texture, "
            "not airbrushed, velvet lounge editorial"
        ),
        "caption": (
            "lounge corner moment \U0001F4F8 "
            "#editorial #velvetvibes #35mm "
            "#filmlook #nightout #fashion"
        ),
        "overlay_hook": None,
    },
    "ornate lobby flash editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Lena crossed the marble lobby and the flash fired "
            "before she knew — the frame looked like the opening "
            "shot of a 90s fashion documentary."
        ),
        "style_lighting": (
            "35mm editorial, direct center flash. "
            "Flash hits Lena cleanly against a deep, "
            "underexposed grand-lobby interior. "
            "Architecture recedes into shadow above and behind. "
            "Warm grain, sharp foreground. "
            "Heavy analog noise. Commanding editorial feel."
        ),
        "subject_pose": (
            "Lena standing in the center of the lobby, "
            "weight even, feet shoulder-width. "
            "Direct eye contact with camera, expression composed "
            "and slightly imperious. Shoulders back. "
            "One hand loosely at her side, "
            "the other holding a small clutch."
        ),
        "fashion_accessories": (
            "Structured tailored coat-dress in camel or ivory — "
            "belted at the waist, hem just above the knee. "
            "Kitten-heel pointed mule in nude or black. "
            "Gold clip earrings and a simple cuff bracelet. "
            "Dark berry lip. No logos."
        ),
        "setting_background": (
            "Grand lobby interior — marble floors, "
            "high ceilings with ornate plaster molding. "
            "Chandelier visible far above, barely lit. "
            "Dark brass fixtures and arched doorways behind. "
            "Deep shadow fills the upper space. "
            "No readable signage. No modern decor."
        ),
        "technical_keywords": (
            "35mm analog, heavy grain, center flash, "
            "grand interior editorial, underexposed background, "
            "warm desaturated palette, marble lobby, "
            "1990s fashion editorial, natural skin texture, "
            "not airbrushed, architectural fashion"
        ),
        "caption": (
            "lobby presence \U0001F4F8 "
            "#editorial #lobbylook #35mm "
            "#filmlook #fashion #ootd"
        ),
        "overlay_hook": None,
    },
    "candlelit restaurant corridor editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Between courses, Lena slipped into the corridor — "
            "the flash and the candlelight collided "
            "into something unexpectedly editorial."
        ),
        "style_lighting": (
            "35mm editorial — dual light: warm candlelight "
            "from wall sconces meeting a direct camera flash. "
            "Flash wins the foreground; candles bleed warm "
            "into the corridor walls. Heavy grain. "
            "Slightly halated candle sources in the distance. "
            "Champagne palette, deep shadow behind her."
        ),
        "subject_pose": (
            "Lena mid-turn in the corridor, body angled away, "
            "face and shoulders turning back toward camera. "
            "Expression: soft, caught off-guard but composed. "
            "One hand slightly raised as if mid-gesture. "
            "Weight on the far foot. Hair movement implied."
        ),
        "fashion_accessories": (
            "Champagne or cream off-shoulder satin dress — "
            "fitted, hem below the knee. "
            "Long pendant earrings catching the flash. "
            "Thin gold cuff on one wrist. "
            "Jeweled or beaded clutch held loosely. "
            "Nude pointed-toe heel. Soft glossy lip."
        ),
        "setting_background": (
            "Narrow restaurant corridor with wall-mounted "
            "candle sconces glowing warm on both sides. "
            "Dark wood paneling, deep red or green wallpaper. "
            "Corridor recedes into warm amber darkness. "
            "No readable menus or signage. "
            "Intimate, classical, European restaurant feel."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, dual-light editorial, "
            "candle ambient plus camera flash, warm halation, "
            "champagne palette, deep shadow corridor, "
            "1990s editorial photography, restaurant interior, "
            "not airbrushed, candlelit fashion editorial"
        ),
        "caption": (
            "between courses \U0001F4F8 "
            "#editorial #restaurantvibes #35mm "
            "#filmlook #fashion #satindress"
        ),
        "overlay_hook": None,
    },
    "marble bathroom flash editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Lena was checking her lip color at the marble vanity "
            "when the flash fired — caught mid-touch, "
            "unposed but completely editorial."
        ),
        "style_lighting": (
            "35mm editorial. Flash bounces slightly off marble "
            "and mirror, creating warm halated foreground glow. "
            "Hard shadows behind her. Heavy grain. "
            "Warm champagne-to-ivory register. "
            "Flash slightly overexposes the vanity surface. "
            "Mirror catch lights visible in background."
        ),
        "subject_pose": (
            "Lena at the marble vanity, one hand raised "
            "with a lip gloss or compact near her face. "
            "Eyes briefly toward camera — caught mid-action. "
            "Slight body twist, profile partially to camera. "
            "Confident despite being caught in a private moment."
        ),
        "fashion_accessories": (
            "Sleek one-shoulder or strapless mini dress "
            "in deep black or dark sapphire. "
            "Gold ear cuff or stud earring. "
            "Delicate bracelet on the reaching wrist. "
            "Deep cherry lip being applied. "
            "Short dark manicure. Strappy black heel."
        ),
        "setting_background": (
            "Opulent marble vanity, ornate framed mirror "
            "partially reflected in background. "
            "Dark stone or veined marble surface, "
            "soft ambient wall light from the side. "
            "No branded products. No readable labels. "
            "Gold or antique-style fixtures. Architectural."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, mirror flash bounce, "
            "marble interior editorial, overexposed vanity, "
            "warm ivory palette, deep shadow accents, "
            "1990s editorial fashion, natural skin texture, "
            "not airbrushed, getting-ready editorial"
        ),
        "caption": (
            "lip check caught on film \U0001F4F8 "
            "#editorial #marblevibes #35mm "
            "#filmlook #fashion #getready"
        ),
        "overlay_hook": None,
    },
    "old money townhouse entryway editorial": {
        "pillar": "moody_90s_flash_editorial",
        "human_reason": (
            "Lena stepped into the entryway still in her coat "
            "when the flash went off — arriving or leaving, "
            "either way it looked expensive and editorial."
        ),
        "style_lighting": (
            "35mm editorial. Single overhead pendant catch "
            "plus direct camera flash. "
            "Warm tones — ivory walls, wood floor. "
            "Heavy analog grain. "
            "Slightly overexposed from the pendant above. "
            "Rich warm contrast between coat and shadow."
        ),
        "subject_pose": (
            "Lena in the entryway, one hand on the door frame, "
            "body half-turned toward camera, coat still on. "
            "Expression: composed surprise, slightly challenging. "
            "Weight on one hip, shoulders relaxed. "
            "Arriving-and-being-caught mid-thought energy."
        ),
        "fashion_accessories": (
            "Structured camel or dark-taupe wool coat — "
            "fitted silhouette, belted or single-breasted. "
            "Dark fitted trousers or mini visible beneath. "
            "Tan or dark-brown leather shoulder bag. "
            "Gold rings and stacked bracelets on bag hand. "
            "Ankle boot or pointed flat. No logos."
        ),
        "setting_background": (
            "Classic townhouse entryway — herringbone parquet, "
            "cream or warm-ivory walls. "
            "Coat hooks and umbrella stand partially visible. "
            "Single pendant overhead. "
            "Arched doorway or dark wood molding behind her. "
            "No readable text. No modern objects."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, entryway editorial, "
            "warm ivory palette, overhead pendant light catch, "
            "camera flash foreground, analog grain, "
            "1990s editorial fashion, natural skin texture, "
            "not airbrushed, old-money interior"
        ),
        "caption": (
            "just got home energy \U0001F4F8 "
            "#editorial #oldmoney #35mm "
            "#filmlook #fashion #arrival"
        ),
        "overlay_hook": None,
    },
    "boxing ring stool smile flash": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "Lena sat on the corner stool between rounds "
            "and someone fired the flash mid-laugh — "
            "the ring ropes and the smile made the frame."
        ),
        "style_lighting": (
            "Vibrant 35mm direct flash, warm saturated palette. "
            "Flash hits her face and cropped tee clean. "
            "Ring ropes and corner pad fall into warm shadow. "
            "Heavy analog grain. High color saturation. "
            "Punchy contrast — lit subject, dark gym behind."
        ),
        "subject_pose": (
            "Lena seated on the corner stool, leaning slightly "
            "forward, elbows on knees, big open smile at camera. "
            "Head tilted slightly, eyes bright, "
            "expression full of joyful energy. "
            "One hand resting on the rope. "
            "Relaxed, confident, genuinely caught."
        ),
        "fashion_accessories": (
            "Cropped graphic ringer tee, fitted, hem above waist. "
            "High-waisted bike shorts in black or cobalt. "
            "Clean white low-top sneakers. "
            "White hand wraps loosely wound on both wrists. "
            "Small gold hoop earrings. Hair up in a high bun."
        ),
        "setting_background": (
            "Inside a boxing ring corner — canvas floor visible, "
            "corner stool, colored rope turnbuckle behind her. "
            "Gym interior dark beyond the flash zone. "
            "Corner pad partially visible. "
            "Heavy bag shadows in background. "
            "Authentic boxing gym atmosphere."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, direct flash, warm palette, "
            "high saturation, boxing gym interior, analog snap, "
            "1990s lo-fi flash photography, "
            "natural skin texture, not airbrushed, "
            "candid athletic moment"
        ),
        "caption": (
            "corner girl energy \U0001F4F8 "
            "#boxing #gymlife #35mm "
            "#flashphotography #ootd #sportystyle"
        ),
        "overlay_hook": None,
    },
    "yellow boxing glove handbag flash": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "Lena held up the yellow glove bag as a joke "
            "and the flash caught it perfectly — "
            "the bag and the laugh became the whole shot."
        ),
        "style_lighting": (
            "35mm direct flash, warm punchy palette. "
            "Flash pops the yellow bag and her smile. "
            "Gym entrance — warm ambient light behind. "
            "Heavy grain. Saturated color. "
            "Yellow bag reads as the hero prop in the frame."
        ),
        "subject_pose": (
            "Lena standing, holding up a small yellow mini "
            "boxing glove bag at shoulder height, grinning. "
            "Free hand on her hip, weight shifted to one side. "
            "Expression: playful, confident, caught mid-laugh. "
            "Head slightly tilted, eyes direct at camera."
        ),
        "fashion_accessories": (
            "Fitted zip hoodie half-open over a cropped tee — "
            "warm tone or white. High-waisted track pants "
            "in matching or contrasting color. "
            "Clean white sneakers. Gold hoop earrings. "
            "Yellow mini boxing glove bag on a short strap — "
            "the statement prop. No logos visible."
        ),
        "setting_background": (
            "Gym lobby or entrance area, light and airy. "
            "Locker doors or gym equipment blurred in background. "
            "Warm overhead light mixing with the flash. "
            "Clean floor, minimal clutter. "
            "No readable text. Sporty, bright, casual."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, direct flash, warm tones, "
            "high saturation, yellow prop hero, "
            "boxing gym lifestyle, 1990s lo-fi snap, "
            "natural skin texture, not airbrushed, "
            "playful candid moment"
        ),
        "caption": (
            "new gym bag just dropped \U0001F4F8 "
            "#boxing #gymstyle #35mm "
            "#flashphotography #ootd #gymbag"
        ),
        "overlay_hook": "new gym bag just dropped",
    },
    "heavy bag laugh candid flash": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "Someone said something absurd mid-set — "
            "Lena's hand was still on the heavy bag "
            "when the laugh hit and the flash fired."
        ),
        "style_lighting": (
            "35mm candid flash, warm saturated palette. "
            "Flash catches Lena fully, heavy bag edge lit. "
            "Gym row dark behind. Heavy analog grain. "
            "Punchy warm tones, real skin texture. "
            "Feels like it was taken by a friend on film."
        ),
        "subject_pose": (
            "Lena mid-laugh, one hand resting on the heavy bag, "
            "head slightly thrown back, eyes crinkled. "
            "Body weight casual, not rigid. "
            "Natural joyful candid energy — "
            "not posed, fully caught in the laugh."
        ),
        "fashion_accessories": (
            "Ringer tee in white with colored trim, "
            "fitted, hem tucked or cropped. "
            "High-waisted biker shorts in black. "
            "Chunky white sneakers. "
            "Hand wraps on both wrists, partially unwound. "
            "Small gold earrings. No logos visible."
        ),
        "setting_background": (
            "Heavy bag row in a boxing gym — "
            "multiple bags hanging in background, blurred. "
            "Concrete or wood gym floor visible below. "
            "Warm overhead lighting and chain hardware visible. "
            "No readable text on bags or walls."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, candid flash, "
            "warm punchy palette, boxing gym row, "
            "natural laugh, analog film snapshot, "
            "1990s lo-fi photography, natural skin texture, "
            "not airbrushed, genuine candid athletic moment"
        ),
        "caption": (
            "mid-set when someone is too funny \U0001F4F8 "
            "#boxing #gymlife #35mm "
            "#flashphotography #candid #gymhumor"
        ),
        "overlay_hook": None,
    },
    "jump rope corner flash": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "The flash fired mid-jump during warm-up — "
            "Lena caught airborne, rope blurred, "
            "expression focused and bright."
        ),
        "style_lighting": (
            "35mm direct flash, vibrant warm palette. "
            "Flash freezes Lena mid-jump, blurs the rope arc. "
            "Gym corner underexposed in background. "
            "Heavy grain, warm saturated tones. "
            "High energy — motion and stillness at once."
        ),
        "subject_pose": (
            "Lena mid-jump, feet slightly off the floor, "
            "knees soft, rope passing under. "
            "Arms rotating, wrists mid-turn. "
            "Expression: focused but bright, hint of a smile. "
            "Body upright, energy forward, silhouette strong."
        ),
        "fashion_accessories": (
            "Cropped athletic zip hoodie, pastel or white, "
            "half-zipped over a fitted sports top. "
            "High-waisted bike shorts in cobalt or black. "
            "White or neon low-top sneakers. "
            "Thin gold chain at the neckline. "
            "Hair in a secure high ponytail."
        ),
        "setting_background": (
            "Open corner of a boxing gym — "
            "speed bag platform barely visible in background. "
            "Concrete floor, gym equipment out of focus. "
            "Natural gym ambient light plus direct flash. "
            "No readable text. Athletic, spacious, real."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, mid-jump flash, "
            "rope blur, vibrant warm palette, boxing gym, "
            "motion moment, analog snapshot, "
            "1990s lo-fi flash photography, "
            "natural skin texture, not airbrushed, "
            "athletic candid"
        ),
        "caption": (
            "warm-up cardio hits different \U0001F4F8 "
            "#boxing #jumprope #35mm "
            "#flashphotography #gymlife #fitcheck"
        ),
        "overlay_hook": None,
    },
    "locker bench outfit reset flash": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "Post-workout outfit reset on the locker bench — "
            "Lena looked up mid-lace and the flash caught "
            "her looking better than she did going in."
        ),
        "style_lighting": (
            "35mm direct flash in a locker room interior. "
            "Flash hits Lena from the front, lockers behind "
            "fall to warm ambient shadow. "
            "Heavy analog grain, warm tones. "
            "Candid get-ready energy — real and unposed."
        ),
        "subject_pose": (
            "Lena seated on a wooden locker bench, "
            "leaning forward to tie a sneaker or check her fit, "
            "looking up at camera with a wide grin. "
            "One elbow on her knee. Hair slightly loose. "
            "Relaxed, real, not staged."
        ),
        "fashion_accessories": (
            "Denim jacket thrown on over a cropped tee — "
            "jacket slightly off one shoulder. "
            "High-waisted shorts, mid-thigh. "
            "Clean fresh sneakers in white or cream. "
            "Gold hoop earrings. Small gym bag on the bench "
            "with hand wraps peeking out."
        ),
        "setting_background": (
            "Locker room bench area — metal lockers behind "
            "in muted tones, blurred but recognizable. "
            "Overhead light warm and slightly harsh. "
            "No readable text on lockers. "
            "One towel or bag visible. Real gym atmosphere."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, locker room flash, "
            "warm interior tones, post-workout energy, "
            "candid getting-ready moment, analog snapshot, "
            "1990s lo-fi photography, natural skin texture, "
            "not airbrushed, gym lifestyle"
        ),
        "caption": (
            "outfit reset complete \U0001F4F8 "
            "#gymlife #lockerroom #35mm "
            "#flashphotography #ootd #fitcheck"
        ),
        "overlay_hook": None,
    },
    "post workout smoothie gym exit": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "She looked too good post-workout to not stop — "
            "smoothie in hand, walking out the gym exit, "
            "the flash caught her mid-stride."
        ),
        "style_lighting": (
            "35mm flash mixing with outdoor daylight at the exit. "
            "Flash pops her face and outfit clean. "
            "Warm saturated tones, bright and energetic. "
            "Heavy grain. "
            "Outdoor light bleeds warm into the background. "
            "Fresh, candid, like a friend's snapshot."
        ),
        "subject_pose": (
            "Lena mid-stride through the gym exit, "
            "smoothie cup raised in one hand, bag on shoulder. "
            "Big bright smile, head slightly angled to camera. "
            "Body in motion, relaxed and natural. "
            "Hair slightly windblown. Post-workout glow."
        ),
        "fashion_accessories": (
            "Oversized track jacket in a warm or neutral tone "
            "over bike shorts. Clean white sneakers. "
            "Small crossbody gym bag or tote on one shoulder. "
            "Large smoothie cup with straw — the key prop. "
            "Gold small earrings. Hair half-up."
        ),
        "setting_background": (
            "Gym exit door or street just outside — "
            "natural light flooding in from outside. "
            "Gym interior partially visible behind. "
            "Pavement, daylight, fresh outdoor feel. "
            "No readable signage. Urban athletic context."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, gym exit flash, "
            "daylight mix, warm saturated palette, "
            "post-workout lifestyle, smoothie prop, "
            "analog snapshot, 1990s lo-fi, "
            "natural skin texture, not airbrushed, "
            "gym exit candid"
        ),
        "caption": (
            "post-gym smoothie run \U0001F4F8 "
            "#gymlife #postworkout #35mm "
            "#flashphotography #ootd #smoothie"
        ),
        "overlay_hook": None,
    },
    "dance studio cross training flash": {
        "pillar": "joyful_35mm_boxing_gym_flash",
        "human_reason": (
            "Cross-training in the dance studio turned into "
            "an impromptu flash shoot — Lena caught mid-move "
            "in the mirrors, too good not to keep."
        ),
        "style_lighting": (
            "35mm direct flash in a mirrored dance studio. "
            "Flash bounces off the mirrors, creating "
            "a warm doubled catch in the background. "
            "Heavy grain, warm saturated palette. "
            "Bright and energetic — mirrors add visual depth."
        ),
        "subject_pose": (
            "Lena mid-movement in the studio, arms extended, "
            "feet apart, caught mid-step or mid-turn. "
            "Big open smile toward camera or the mirror. "
            "Body language loose and joyful, not choreographed. "
            "Energy: athletic, playful, spontaneous."
        ),
        "fashion_accessories": (
            "Fitted cropped athletic tee, bright or white. "
            "High-waisted track pants with a clean side stripe. "
            "Minimal white sneakers. "
            "Small gold earrings. Hair loose or in a bun. "
            "Thin chain at the neckline. "
            "No props — movement is the hook."
        ),
        "setting_background": (
            "Dance studio with full mirrored wall behind her. "
            "Barre partially visible at mirror edge. "
            "Wood sprung floor catching the flash reflection. "
            "Warm overhead studio light plus direct flash. "
            "No readable text. Clean, bright, studio atmosphere."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, mirror flash bounce, "
            "dance studio interior, warm saturated palette, "
            "mid-motion athletic moment, analog snapshot, "
            "1990s lo-fi flash, natural skin texture, "
            "not airbrushed, cross-training candid"
        ),
        "caption": (
            "cross training day hits different \U0001F4F8 "
            "#dancing #gymlife #35mm "
            "#flashphotography #dancestudio #fitcheck"
        ),
        "overlay_hook": None,
    },
    "vintage car roadside lens flare": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "They pulled over because the light was too good "
            "to drive through — Lena stepped out "
            "and the disposable caught the whole moment."
        ),
        "style_lighting": (
            "90s vintage film. Bright vertical sun flare "
            "cuts through the frame from above and behind. "
            "Warm golden palette, slightly overexposed. "
            "Heavy 35mm grain throughout. "
            "Film burn at the upper corner — orange to ivory. "
            "Snapshot energy, not a staged shoot."
        ),
        "subject_pose": (
            "Lena leaning against the open car door, "
            "one hand on the roof, body slightly angled. "
            "Sunglasses pushed up on her head. "
            "Face turned toward the sun, soft squint, "
            "natural smile or neutral cool expression. "
            "Hair catching the wind and the light."
        ),
        "fashion_accessories": (
            "Fitted crop top in white or warm ivory. "
            "High-waisted wide-leg jeans, cuffed at the ankle. "
            "White sneakers or tan sandals. "
            "Sunglasses on top of head. "
            "Canvas tote on shoulder or inside the car. "
            "Thin gold necklace. No logos visible."
        ),
        "setting_background": (
            "Vintage car pulled roadside — warm chrome detail "
            "and painted door visible, no readable markings. "
            "Open road or dry grass behind. "
            "Bright afternoon sun from the side. "
            "No license plates readable. "
            "Roadtrip lifestyle, open sky, warm pavement."
        ),
        "technical_keywords": (
            "35mm vintage film, heavy grain, vertical sun flare, "
            "film burn corner, warm golden palette, "
            "overexposed highlight, roadside snapshot, "
            "1990s film photography, natural skin texture, "
            "not airbrushed, roadtrip candid"
        ),
        "caption": (
            "had to pull over \U0001F4F8 "
            "#roadtrip #35mm #vintagefilm "
            "#filmburn #ootd #sunflare"
        ),
        "overlay_hook": "had to pull over",
    },
    "dusty suv foliage film burn": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "She stepped out to stretch and the film "
            "burned at exactly the right moment — "
            "the foliage, the dust, and the dress aligned."
        ),
        "style_lighting": (
            "90s vintage film with strong orange and red "
            "film burn bleeding in from one corner. "
            "Warm dusty palette — amber and olive tones. "
            "Heavy grain, slight overexposure in bright zones. "
            "Organic light leaks at the frame edges. "
            "Spontaneous, like the camera was barely ready."
        ),
        "subject_pose": (
            "Lena standing at the open back door of an SUV, "
            "one arm resting on the door frame, "
            "face turned toward the light with a relaxed smile. "
            "Hair loose and slightly windblown. "
            "Body slightly turned, weight on one hip. "
            "Casual, natural, roadtrip energy."
        ),
        "fashion_accessories": (
            "Flowy sundress in warm tones — peach, rust, or cream. "
            "Thin cardigan loosely draped over one shoulder. "
            "Flat sandals or white sneakers. "
            "Sunglasses hooked into the dress neckline. "
            "Small crossbody bag or tote. "
            "Thin stacked gold bracelets."
        ),
        "setting_background": (
            "Dusty dirt road or gravel pullout, "
            "lush green foliage behind the SUV. "
            "Back door open, car interior partially visible. "
            "Warm afternoon haze. Dust particles in the air. "
            "No license plates or readable markings. "
            "Remote, natural, unhurried."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, film burn, "
            "red-orange light leak, dusty warm palette, "
            "overexposed zones, organic film grain, "
            "1990s road trip photography, "
            "natural skin texture, not airbrushed, "
            "candid roadtrip lifestyle"
        ),
        "caption": (
            "stretch break somewhere beautiful \U0001F4F8 "
            "#roadtrip #35mm #filmburn "
            "#filmgrain #ootd #sundress"
        ),
        "overlay_hook": None,
    },
    "gas station sunlight snapshot": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "Waiting for the tank to fill — "
            "a friend with a disposable camera "
            "caught her mid-sip in the afternoon glare."
        ),
        "style_lighting": (
            "90s disposable snapshot. Harsh direct sunlight "
            "from above and to the side. "
            "Vertical sun flare cutting through the frame. "
            "Overexposed foreground, warm shadows beyond. "
            "Heavy film grain. Warm but slightly bleached tones. "
            "Imperfect crop, real moment."
        ),
        "subject_pose": (
            "Lena leaning against the car at the pump island, "
            "sunglasses on, iced coffee raised for a sip. "
            "One hip cocked, free hand in pocket or at side. "
            "Expression: relaxed, unbothered, slightly amused. "
            "Looking toward camera or slightly past it."
        ),
        "fashion_accessories": (
            "Fitted tee in white or tan, tucked into "
            "high-waisted denim shorts — mid-thigh, full coverage. "
            "White sneakers or flat sandals. "
            "Sunglasses on. Small hoop earrings. "
            "Iced coffee cup with straw — the key prop. "
            "No readable logos anywhere."
        ),
        "setting_background": (
            "Vintage-style gas station canopy, warm light. "
            "Pump island in background, no readable markings. "
            "Concrete forecourt, midday light. "
            "Open road or sky partially visible. "
            "Car door or bumper edge at frame edge. "
            "No license plates. Roadtrip Americana feel."
        ),
        "technical_keywords": (
            "35mm disposable film, heavy grain, sun flare, "
            "harsh midday light, warm bleached palette, "
            "overexposed foreground, analog snapshot, "
            "1990s road photography, natural skin texture, "
            "not airbrushed, gas station candid"
        ),
        "caption": (
            "tank full, coffee full \U0001F4F8 "
            "#roadtrip #35mm #filmgrain "
            "#snapshot #ootd #gasstation"
        ),
        "overlay_hook": None,
    },
    "beach boardwalk wind flare": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "Roadtrip detour to the coast — they stopped "
            "just long enough for one photo before "
            "the light changed and they had to drive on."
        ),
        "style_lighting": (
            "90s vintage film, bright side sun flare. "
            "Wind in the frame — light and hair both moving. "
            "Warm coastal palette, slightly washed. "
            "Heavy film grain. "
            "Horizontal light leak at the sky edge. "
            "Casual, bright, slightly overexposed."
        ),
        "subject_pose": (
            "Lena mid-walk on the boardwalk, hair blowing, "
            "head turned back over one shoulder toward camera. "
            "Expression: free, joyful, windblown energy. "
            "One hand raised to catch her hair or hold a hat. "
            "Body in motion, stride natural and relaxed."
        ),
        "fashion_accessories": (
            "Sundress in white or pale blue, "
            "skirt moving in the wind. "
            "Flat sandals or white sneakers. "
            "Wide-brim hat held in one hand or on head. "
            "Sunglasses. Small tote bag on one shoulder. "
            "Thin gold anklet."
        ),
        "setting_background": (
            "Coastal boardwalk — weathered wooden planks, "
            "ocean or beach sand visible beyond. "
            "Warm afternoon sun from the side. "
            "Horizon line and open sky behind. "
            "No readable signage or beach vendors. "
            "Breezy, coastal, wide open."
        ),
        "technical_keywords": (
            "35mm vintage film, heavy grain, side sun flare, "
            "wind motion, warm coastal palette, "
            "light leak at horizon, slightly overexposed, "
            "1990s beach lifestyle photography, "
            "natural skin texture, not airbrushed, "
            "candid boardwalk moment"
        ),
        "caption": (
            "detour was worth it \U0001F4F8 "
            "#roadtrip #beach #35mm "
            "#filmgrain #sunflare #ootd"
        ),
        "overlay_hook": None,
    },
    "lake pier golden film still": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "Last stop before the long drive home — "
            "the golden hour over the lake made them pull over "
            "and the frame looked like a painting."
        ),
        "style_lighting": (
            "90s golden hour film still. "
            "Warm amber and orange palette saturating the frame. "
            "Soft horizontal sun flare along the waterline. "
            "Heavy film grain, warm color push. "
            "Slight overexposure at the horizon. "
            "Still, cinematic, accidentally beautiful."
        ),
        "subject_pose": (
            "Lena seated at the end of a wooden pier, "
            "legs dangling toward the water. "
            "Looking back at camera over one shoulder "
            "with a soft, content smile. "
            "One hand on the pier boards behind her. "
            "Hair loose, catching the golden light."
        ),
        "fashion_accessories": (
            "Fitted crop top in warm cream or rust. "
            "High-waisted jeans, light wash. "
            "Sneakers or slides set beside her. "
            "Thin gold chain at the neckline. "
            "Small tote or jacket beside her on the pier. "
            "Sunglasses resting in her hair."
        ),
        "setting_background": (
            "Old wooden pier extending over a still lake. "
            "Golden reflections on the water surface. "
            "Tree line and open sky behind. "
            "Warm amber light filling the whole frame. "
            "No readable signage. No other people. "
            "Quiet, remote, golden hour atmosphere."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, golden hour, "
            "warm amber palette, horizontal sun flare, "
            "lake reflection, film still quality, "
            "1990s road trip photography, natural skin texture, "
            "not airbrushed, pier golden candid"
        ),
        "caption": (
            "last stop before the drive home \U0001F4F8 "
            "#roadtrip #goldenhour #35mm "
            "#filmgrain #lake #ootd"
        ),
        "overlay_hook": None,
    },
    "outdoor cafe roadtrip stop": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "Mid-drive coffee stop that became 30 unplanned "
            "minutes in perfect light — the dappled shade "
            "through the awning was too good to waste."
        ),
        "style_lighting": (
            "90s vintage film, dappled sunlight through leaves "
            "or a cafe awning. "
            "Soft lens flare from the side. "
            "Warm saturated palette, slightly hazy. "
            "Heavy film grain. "
            "Light patches across her face and outfit — "
            "natural, imperfect, warm."
        ),
        "subject_pose": (
            "Lena seated at a small outdoor cafe table, "
            "iced coffee in one hand, other hand relaxed. "
            "Looking slightly off-camera or back at it. "
            "Expression: content, unhurried, at ease. "
            "Sunglasses on or pushed up in her hair. "
            "Tote bag hanging on the chair back."
        ),
        "fashion_accessories": (
            "Fitted tee tucked into high-waisted jeans. "
            "Light cardigan draped on the chair. "
            "Hoop earrings. Sunglasses. "
            "Iced coffee with straw — the prop. "
            "Canvas tote on the chair back. "
            "Simple white sneakers or sandals."
        ),
        "setting_background": (
            "Small outdoor cafe — table and chairs on a "
            "terrace or sidewalk. "
            "Awning or tree providing dappled shade. "
            "Warm street or garden behind. "
            "No readable menu or signage in frame. "
            "Roadside town feel, unhurried afternoon."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, dappled sunlight, "
            "soft side flare, warm saturated palette, "
            "cafe lifestyle, outdoor light, "
            "1990s film photography, natural skin texture, "
            "not airbrushed, cafe roadtrip stop"
        ),
        "caption": (
            "the unplanned coffee stop \U0001F4F8 "
            "#roadtrip #cafe #35mm "
            "#filmgrain #coffeeshop #ootd"
        ),
        "overlay_hook": None,
    },
    "farmers market sun leak candid": {
        "pillar": "sun_drenched_90s_roadtrip_film",
        "human_reason": (
            "The roadtrip detour through a farmers market "
            "and the film leaked at exactly the right moment — "
            "flowers, light, and a real smile."
        ),
        "style_lighting": (
            "90s film with a strong red-orange light leak "
            "bleeding in from one side of the frame. "
            "Bright outdoor market light, warm and overexposed. "
            "Heavy grain. Saturated warm palette. "
            "The leak bleeds across her shoulder or the flowers. "
            "Candid, bright, vintage market energy."
        ),
        "subject_pose": (
            "Lena mid-step through the market, "
            "holding a bunch of fresh flowers or a paper bag "
            "with produce, turning toward camera. "
            "Big natural smile, eyes bright. "
            "Hair loose or in a bun, slightly tousled. "
            "Free arm extended, relaxed body language."
        ),
        "fashion_accessories": (
            "Sundress with a floral or stripe print, "
            "fitted bodice, hem at or below the knee. "
            "Flat sandals or white sneakers. "
            "Large canvas tote with market goods. "
            "Sunglasses on top of head. "
            "Thin gold earrings. Fresh flowers as the prop."
        ),
        "setting_background": (
            "Outdoor farmers market stalls — wooden tables "
            "with colorful produce and flowers in background. "
            "Bright outdoor light, warm and directional. "
            "Crowd loosely implied in background, blurred. "
            "No readable labels or brand names. "
            "Fresh, colorful, summer market atmosphere."
        ),
        "technical_keywords": (
            "35mm film, heavy grain, red-orange light leak, "
            "farmers market outdoor light, warm palette, "
            "saturated overexposed zones, organic film grain, "
            "1990s lifestyle photography, natural skin texture, "
            "not airbrushed, candid market moment"
        ),
        "caption": (
            "roadtrip market detour \U0001F4F8 "
            "#roadtrip #farmersmarket #35mm "
            "#filmburn #lightleak #ootd"
        ),
        "overlay_hook": None,
    },
    "apartment doorway luxury fit check": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "She was about to leave and caught herself "
            "in the door reflection — the outfit was "
            "too good not to document before going anywhere."
        ),
        "style_lighting": (
            "Direct on-camera flash, warm apartment interior. "
            "Flash catches the outfit and face cleanly. "
            "Door frame creates a natural vertical composition. "
            "Warm ambient interior behind, flash hits foreground. "
            "Heavy grain, phone-flash realism. "
            "Real, lived-in, high-fashion social feel."
        ),
        "subject_pose": (
            "Lena standing in the open doorway, "
            "one hand on the door frame, hip cocked. "
            "Full body visible — head to heel, "
            "mini dress silhouette front and center. "
            "Slight body tilt, confident going-out stance. "
            "Expression: direct smirk, composed and ready. "
            "Hair styled down or loose waves."
        ),
        "fashion_accessories": (
            "Fitted one-shoulder mini dress — "
            "black satin or deep jewel tone, "
            "above the knee, bodycon silhouette. "
            "Strappy stiletto heel or pointed-toe mule. "
            "Layered thin gold chains, varied lengths. "
            "Small hoop earrings or statement drop earrings. "
            "Micro bag or metallic clutch. "
            "Glossy soft-bold lip, defined eyes, "
            "natural-finish skin. No logos visible."
        ),
        "setting_background": (
            "Apartment front door — interior behind her: "
            "soft warm light, partial view of entryway "
            "table or coat rack. Door frame in focus. "
            "Natural imperfect apartment feel. "
            "No readable text. No studio backdrop. "
            "Lived-in, personal, real."
        ),
        "technical_keywords": (
            "direct flash, phone-flash realism, heavy grain, "
            "warm apartment interior, doorway composition, "
            "luxury fit check, high-fashion social media, "
            "natural skin texture, not airbrushed, "
            "fitted silhouette, candid departure shot"
        ),
        "caption": (
            "leaving the house like this \U0001F4F8 "
            "#ootd #fitcheck #flashphoto #style"
        ),
        "overlay_hook": "leaving like this",
    },
    "parking garage flash fit check": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Walking to the car and realizing the concrete "
            "and the outfit made the perfect accidental frame — "
            "someone had to get the shot."
        ),
        "style_lighting": (
            "Direct on-camera flash in a concrete garage. "
            "Flash hits hard against grey concrete. "
            "Overhead fluorescent ambient mixing with flash. "
            "High contrast, cool tones with warm outfit pop. "
            "Heavy grain. Urban, real, no studio finish."
        ),
        "subject_pose": (
            "Lena standing against a concrete column or wall, "
            "one hand on hip, body slightly turned "
            "to show the full silhouette. "
            "Direct camera gaze — confident, unblinking. "
            "Weight on one foot, small heel pop. "
            "Expression: composed authority, no smile needed."
        ),
        "fashion_accessories": (
            "Fitted leather jacket over a satin blouse "
            "in ivory or champagne. "
            "High-waisted straight trousers or dark jeans. "
            "Pointed-toe heeled boot or mule. "
            "Gold chain detail — belt or bag strap. "
            "Stacked gold rings. No logos visible."
        ),
        "setting_background": (
            "Concrete parking garage — textured column or wall "
            "filling the background. "
            "Overhead fluorescent strips visible above. "
            "Car bumpers partially at the frame edges. "
            "No readable parking signage. "
            "Urban, gritty, high-contrast."
        ),
        "technical_keywords": (
            "direct flash, parking garage, concrete texture, "
            "high contrast, cool fluorescent ambient, "
            "warm outfit pop, heavy grain, "
            "luxury fit check, phone-flash realism, "
            "natural skin texture, not airbrushed"
        ),
        "caption": (
            "parking garage fit check \U0001F4F8 "
            "#ootd #flashphoto #citystyle #nightout"
        ),
        "overlay_hook": "parking garage fit",
    },
    "late night flower stand fit check": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Late-night detour to the flower stand "
            "on the way home — the neon glow "
            "and the outfit demanded a photo."
        ),
        "style_lighting": (
            "Direct flash mixing with warm neon "
            "from the flower stand. "
            "Flash pops her face and outfit. "
            "Warm artificial light halos behind her. "
            "Heavy grain, slight color shift from the neon. "
            "Nighttime urban flash — real, spontaneous."
        ),
        "subject_pose": (
            "Lena at the late-night flower stand — "
            "mid-step, turning, or reaching for flowers. "
            "Natural candid motion, body relaxed. "
            "Preserve Lena's recognizable face and "
            "natural body proportions from the element. "
            "Expression: closed-mouth smirk or soft side-eye. "
            "Outfit coherent and visible for the chosen pose."
        ),
        "fashion_accessories": (
            "Black satin mini dress or deep jewel-tone mini dress — "
            "fitted, bodycon, above the knee. "
            "Cropped leather jacket or cropped blazer. "
            "Strappy heels or sleek ankle boots. "
            "Micro bag or metallic clutch. "
            "Long gold earrings catching the flash. "
            "Fresh flowers as the prop. No logos visible."
        ),
        "setting_background": (
            "Late-night flower stand — buckets of flowers "
            "in background, warm yellow-green glow. "
            "Dark city street or sidewalk around the stand. "
            "Neon and artificial light behind. "
            "No readable shop names. "
            "Real urban night feel."
        ),
        "technical_keywords": (
            "direct flash, nighttime, flower stand neon, "
            "warm artificial light, heavy grain, "
            "color shift, luxury fit check, "
            "urban night photography, natural skin texture, "
            "not airbrushed, flash and ambient mix"
        ),
        "caption": (
            "flower stand stop \U0001F4F8 "
            "#ootd #nightout #flowers #flashphoto"
        ),
        "overlay_hook": "flower stand stop",
    },
    "boutique mirror flash fit check": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Trying something on in the boutique "
            "and the mirror was too good to not document — "
            "the outfit decided for itself."
        ),
        "style_lighting": (
            "Direct flash in a boutique dressing area. "
            "Flash bounces slightly off the mirror, "
            "creating a warm doubled catch in the reflection. "
            "Warm boutique ambient light behind. "
            "Heavy grain. Real fitting-room energy, not staged."
        ),
        "subject_pose": (
            "Lena standing in front of the boutique mirror, "
            "body slightly turned to show the silhouette, "
            "face toward camera not the mirror. "
            "One hand lightly at the waist or hip. "
            "Expression: critical but pleased — side-eye energy. "
            "Full head-to-heel frame."
        ),
        "fashion_accessories": (
            "Sharp fitted blazer with matching tailored "
            "mini skirt or wide-leg trousers — tonal set. "
            "Fitted bodysuit or top underneath. "
            "Pointed heeled boot or pump. "
            "Gold chain earrings or huggies. "
            "Small structured bag. No logos visible."
        ),
        "setting_background": (
            "Boutique dressing area or floor mirror — "
            "clothing racks and hangers visible behind. "
            "Warm shop lighting overhead. "
            "Polished floor or carpeted fitting area. "
            "No readable brand tags or price tags. "
            "Real boutique atmosphere, intimate."
        ),
        "technical_keywords": (
            "direct flash, boutique mirror bounce, "
            "warm fitting-room light, heavy grain, "
            "luxury fit check, mirror flash catch, "
            "high-fashion social media, natural skin texture, "
            "not airbrushed, fitted silhouette"
        ),
        "caption": (
            "the mirror said yes \U0001F4F8 "
            "#ootd #fitcheck #boutique #flashphoto"
        ),
        "overlay_hook": "the mirror said yes",
    },
    "rooftop elevator lobby flash": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Waiting for the elevator at the rooftop floor — "
            "the lobby light hit perfectly "
            "and someone had 30 seconds to get the shot."
        ),
        "style_lighting": (
            "Direct flash in a penthouse elevator lobby. "
            "Flash hits Lena cleanly, lobby behind dim. "
            "Warm metallic elevator doors catching light. "
            "Heavy grain. Mix of ambient luxury lighting "
            "and direct flash. Polished, real, not over-lit."
        ),
        "subject_pose": (
            "Lena standing in the elevator lobby, "
            "facing camera or half-turned toward the doors. "
            "Coat or jacket held in one hand or on arm. "
            "Expression: just-arrived composed energy. "
            "Body upright, silhouette strong. "
            "Full head-to-heel frame."
        ),
        "fashion_accessories": (
            "Satin midi dress or sleek column dress "
            "in champagne, black, or deep navy. "
            "Long coat or structured blazer held or worn. "
            "Pointed-toe heeled boot or mule. "
            "Gold hoop earrings. Chain bag or clutch. "
            "No logos visible."
        ),
        "setting_background": (
            "Elevator lobby — metal elevator doors behind her, "
            "marble or stone floor underfoot. "
            "Recessed lighting above, slightly warm. "
            "City view through glass blurred in background. "
            "No readable text on buttons or signage. "
            "Luxurious, quiet, private."
        ),
        "technical_keywords": (
            "direct flash, elevator lobby, metallic doors, "
            "warm ambient light, heavy grain, luxury setting, "
            "arrival energy, high-fashion social media, "
            "natural skin texture, not airbrushed, "
            "rooftop lobby fit check"
        ),
        "caption": (
            "top floor energy \U0001F4F8 "
            "#ootd #citystyle #flashphoto #nightout"
        ),
        "overlay_hook": "top floor energy",
    },
    "art gallery hallway fit check": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "She was walking through the gallery "
            "when her friend pulled out the camera — "
            "the white walls and the outfit were too aligned."
        ),
        "style_lighting": (
            "Direct flash in a white-walled gallery hallway. "
            "Flash is stark and clean against the white. "
            "Gallery spotlights create warm pools in background. "
            "High contrast — crisp foreground, moody behind. "
            "Heavy grain. Editorial but real."
        ),
        "subject_pose": (
            "Lena mid-walk in the gallery hallway, "
            "pausing to face the camera. "
            "One arm slightly extended, head tilted. "
            "Expression: neutral to soft smirk — effortless. "
            "Body angled, silhouette visible head to heel. "
            "Art frames visible but blurred behind."
        ),
        "fashion_accessories": (
            "Monochrome all-black outfit — fitted turtleneck "
            "and tailored wide-leg trousers or pencil skirt. "
            "Or all-cream with a structured blazer. "
            "Pointed-toe boots or kitten heel mule. "
            "Sculptural gold earrings. "
            "Small structured clutch. No logos visible."
        ),
        "setting_background": (
            "White-walled gallery hallway, "
            "art frames on the walls on both sides. "
            "Gallery track lighting casting warm spots. "
            "Polished concrete or wood floor. "
            "No readable artwork text or artist names. "
            "Clean, minimal, prestigious feel."
        ),
        "technical_keywords": (
            "direct flash, white gallery walls, stark contrast, "
            "gallery track lighting, heavy grain, "
            "luxury fit check, monochrome editorial, "
            "natural skin texture, not airbrushed, "
            "gallery hallway fashion"
        ),
        "caption": (
            "art is the backdrop \U0001F4F8 "
            "#ootd #gallerynight #flashphoto #style"
        ),
        "overlay_hook": "art is the backdrop",
    },
    "black car curbside arrival flash": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Stepping out of the car in front of everyone — "
            "someone had the camera ready "
            "and the curbside lighting did the rest."
        ),
        "style_lighting": (
            "Direct flash at nighttime curbside. "
            "Flash hits Lena front-on as she steps out. "
            "Dark car and street ambient behind, city glow. "
            "High contrast — sharp subject, dark background. "
            "Heavy grain. Nighttime arrival energy."
        ),
        "subject_pose": (
            "Lena mid-step from the car, one foot on the curb, "
            "body turning toward camera. "
            "Expression: direct confident arrival look. "
            "One hand at side or holding a small bag. "
            "Silhouette strong, posture upright. "
            "Night city street behind her."
        ),
        "fashion_accessories": (
            "Fitted bodycon or sleek column dress "
            "in black, deep burgundy, or satin silver. "
            "Pointed-toe stiletto heel or heeled sandal. "
            "Gold or silver chain earrings. "
            "Small chain bag or envelope clutch. "
            "Bold lip. No logos visible."
        ),
        "setting_background": (
            "Dark city curbside at night — "
            "black car door open partially at frame edge. "
            "City street ambient: blurred lights, facades. "
            "Sidewalk pavement underfoot. "
            "No readable signs or license plates. "
            "Nighttime luxury arrival atmosphere."
        ),
        "technical_keywords": (
            "direct flash, nighttime curbside, dark background, "
            "high contrast, city ambient glow, heavy grain, "
            "luxury arrival, fit check energy, "
            "natural skin texture, not airbrushed, "
            "nighttime fashion photography"
        ),
        "caption": (
            "arrived like this \U0001F4F8 "
            "#ootd #nightout #flashphoto #citystyle"
        ),
        "overlay_hook": "arrived like this",
    },
    "city sidewalk coat over shoulders": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "The coat over the shoulders was the whole look — "
            "she didn't even need her arms in it "
            "for the photo to make sense."
        ),
        "style_lighting": (
            "Direct flash on a city sidewalk, "
            "overcast daylight or early evening. "
            "Flash pops the outfit against the urban backdrop. "
            "Building facades or street behind. "
            "Heavy grain, warm-to-neutral tones. "
            "Phone-flash spontaneous energy."
        ),
        "subject_pose": (
            "Lena mid-stride or just pausing, "
            "coat draped over both shoulders, not in sleeves. "
            "Arms at sides or one hand on a lapel. "
            "Expression: mid-laugh or cool over-shoulder glance. "
            "Full-body visible, silhouette reads clearly."
        ),
        "fashion_accessories": (
            "Structured wool or cashmere coat in camel, "
            "ivory, or charcoal — draped over shoulders. "
            "Fitted outfit underneath: ribbed turtleneck "
            "and tailored trousers or fitted midi skirt. "
            "Ankle boot or pointed flat. "
            "Gold jewelry. No logos visible."
        ),
        "setting_background": (
            "City sidewalk — building facades behind her, "
            "urban pavement underfoot. "
            "Overcast sky or dusk light. "
            "Foot traffic implied but blurred. "
            "No readable shop signs. "
            "Real urban context, lived-in city feel."
        ),
        "technical_keywords": (
            "direct flash, city sidewalk, coat drape, "
            "urban context, overcast or dusk light, "
            "heavy grain, phone-flash realism, "
            "luxury fit check, natural skin texture, "
            "not airbrushed, street fashion editorial"
        ),
        "caption": (
            "coat over shoulders \U0001F4F8 "
            "#ootd #streetstyle #flashphoto #citywalk"
        ),
        "overlay_hook": "coat over shoulders",
    },
    "espresso bar mini dress flash": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Quick espresso stop on the way somewhere — "
            "the moody bar interior and the outfit "
            "were too good together to walk past."
        ),
        "style_lighting": (
            "Direct flash in a moody espresso bar interior. "
            "Flash cuts through the dim warm ambient. "
            "Warm wood and copper tones behind her. "
            "Espresso machine and bar counter glow softly. "
            "Heavy grain. Intimate, spontaneous, real."
        ),
        "subject_pose": (
            "Lena at the espresso bar counter, "
            "small cup in one hand, elbow on the counter. "
            "Body slightly angled, facing camera. "
            "Expression: composed, slightly amused, direct gaze. "
            "Full outfit visible — head to mid-thigh at least."
        ),
        "fashion_accessories": (
            "Fitted mini dress in suede, velvet, or knit — "
            "deep rust, forest green, or caramel. "
            "Ankle boot with a modest heel. "
            "Gold chain necklace and small hoop earrings. "
            "Small espresso cup as the prop. "
            "No logos on cup or visible surfaces."
        ),
        "setting_background": (
            "Moody espresso bar — dark wood counter, "
            "copper or brass fixtures, shelves behind. "
            "Espresso machine partially visible. "
            "Warm amber light from behind and above. "
            "No readable menu boards or signage. "
            "Intimate, warm, grown-up coffee bar."
        ),
        "technical_keywords": (
            "direct flash, moody bar interior, warm ambient, "
            "dark wood and copper tones, heavy grain, "
            "luxury fit check, espresso bar lifestyle, "
            "natural skin texture, not airbrushed, "
            "mini dress fit check"
        ),
        "caption": (
            "espresso bar fit check \U0001F4F8 "
            "#ootd #coffeerun #flashphoto #style"
        ),
        "overlay_hook": "espresso bar fit",
    },
    "jewelry stack vanity fit check": {
        "pillar": "luxury_fit_check_flash",
        "human_reason": (
            "Getting dressed and the jewelry stack was "
            "so good she had to document it "
            "before the necklaces got covered up."
        ),
        "style_lighting": (
            "Direct flash at a vanity or dresser. "
            "Flash catches the gold and the outfit detail. "
            "Warm vanity or bedroom ambient light behind. "
            "Heavy grain, intimate close-medium energy. "
            "Real getting-ready moment, not a studio shot."
        ),
        "subject_pose": (
            "Lena standing at the vanity or mirror, "
            "hands raised slightly to show the jewelry — "
            "rings, layered necklaces, cuffs all visible. "
            "Looking at camera with a composed direct expression. "
            "Top half to full body in frame."
        ),
        "fashion_accessories": (
            "Luxe fitted top — ribbed, satin, or silk — "
            "in cream, black, or deep jewel tone. "
            "High-waisted tailored trousers or skirt. "
            "Jewelry is the hero: stacked gold rings "
            "on multiple fingers, layered thin chains, "
            "gold cuff bracelet. Intentional and editorial."
        ),
        "setting_background": (
            "Vanity or dresser surface — jewelry scattered "
            "artfully, mirror partially visible. "
            "Warm lamp or vanity light. "
            "Dresser surface detail: perfume silhouette "
            "or small ring dish. "
            "No readable labels. Warm, intimate, personal."
        ),
        "technical_keywords": (
            "direct flash, vanity setting, jewelry stack, "
            "warm ambient light, heavy grain, "
            "luxury fit check, gold jewelry hero, "
            "natural skin texture, not airbrushed, "
            "getting-ready editorial"
        ),
        "caption": (
            "the jewelry stack is the look \U0001F4F8 "
            "#ootd #jewelry #fitcheck #flashphoto"
        ),
        "overlay_hook": "jewelry stack",
    },
}



def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_node() -> dict[str, Any]:
    return {
        "persona": load_json(NODE_ROOT / "persona.json"),
        "benchmark": load_json(NODE_ROOT / "benchmark_architecture.json"),
        "kling": load_json(NODE_ROOT / "kling_profile.json"),
        "overlay": load_json(NODE_ROOT / "overlay_policy.json"),
    }


def load_memory() -> dict[str, Any]:
    if MEMORY_PATH.exists():
        try:
            data = load_json(MEMORY_PATH)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"recent": []}


def stable_index(key: str, length: int) -> int:
    if length <= 0:
        return 0
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % length


def slot_num(slot: dict[str, Any]) -> str:
    slot_id = str(slot.get("slot_id") or "")
    m = re.match(r"^\d{4}-\d{2}-\d{2}-(\d{2})-", slot_id)
    if m:
        return m.group(1)
    parts = slot_id.split("-")
    if len(parts) >= 5 and parts[3].isdigit():
        return parts[3].zfill(2)
    return "00"


def media_type(slot: dict[str, Any]) -> str:
    return str(slot.get("media_type") or slot.get("type") or "").lower()


def lane_family(lane: str) -> str:
    normalized = str(lane or "").strip().lower()
    for family, lanes in LANE_FAMILIES.items():
        if normalized in lanes:
            return family
    return normalized


def recent_families(memory: dict[str, Any]) -> set[str]:
    out = set()
    for item in memory.get("recent", [])[-40:]:
        lane = str(item.get("lane") or "").strip().lower()
        if lane:
            out.add(lane_family(lane))
    return out


def choose_lane(slot: dict[str, Any], node: dict[str, Any], memory: dict[str, Any], used_families: set[str]) -> str:
    sn = slot_num(slot)
    rhythm = node["benchmark"]["slot_rhythm"].get(sn) or {}
    allowed = [str(x).lower() for x in rhythm.get("allowed_lanes", [])]
    allowed = [x for x in allowed if x in LANE_RECIPES]

    if not allowed:
        fallback = {
            "01": "morning stretch",
            "02": "outfit check",
            "03": "dance clip",
            "04": "pov wellness joke",
            "05": "evening skincare",
        }.get(sn, "apartment reset")
        allowed = [fallback]

    recent = recent_families(memory)
    scored = []
    for lane in allowed:
        family = lane_family(lane)
        score = 0
        if family in used_families:
            score += 10000
        if family in recent:
            score += 800
        score += stable_index(f"{slot.get('slot_id')}:{lane}:{VERSION}", 100)
        scored.append((score, lane))

    scored.sort(key=lambda x: x[0])
    chosen = scored[0][1]
    used_families.add(lane_family(chosen))
    return chosen


def clean_public_caption(text: str) -> str:
    text = str(text or "").strip()
    banned = ["ai", "artificial intelligence", "virtual influencer", "synthetic", "bot", "generated", "avatar", "fake", "computer generated"]
    for term in banned:
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()


def build_photo_prompt(recipe: dict[str, Any], node: dict[str, Any]) -> str:
    identity = node["kling"]["identity_elements"]["primary"]


    _avoid = (
        "No text/logos/signs in frame; "
        "no studio finish; "
        "no skin blotches or freckle clusters; "
        "no anatomy distortion."
    )

    def _build(hr, st, ac, wd, sh):
        return f"""Identity:
Use the {identity} character element/reference as the identity anchor.
{LENA_MASTER_IDENTITY_BLUEPRINT}

Moment:
{hr}

Scene:
{st}

Pose:
{ac}

Wardrobe:
{wd}

Camera:
{sh}

Avoid:
{_avoid}""".strip()

    prompt = _build(
        recipe["human_reason"],
        recipe["setting"],
        recipe["action"],
        recipe["wardrobe"],
        recipe["shot"],
    )
    issues = validate_prompt(prompt)
    if any(x.startswith("ABORT") for x in issues):
        budget = (
            PROMPT_MAX_CHARS
            - len(_build("", "", "", "", ""))
            - 50
        )
        pf = max(40, budget // 5)
        prompt = _build(
            recipe["human_reason"][:pf],
            recipe["setting"][:pf],
            recipe["action"][:pf],
            recipe["wardrobe"][:pf],
            recipe["shot"][:pf],
        )
        issues = validate_prompt(prompt)
        if any(x.startswith("ABORT") for x in issues):
            raise ValueError(
                "build_photo_prompt: prompt exceeds "
                f"{PROMPT_MAX_CHARS} chars after field trim"
            )
    return prompt


def build_video_seed_prompt(recipe: dict[str, Any], node: dict[str, Any]) -> str:
    identity = node["kling"]["identity_elements"]["primary"]
    return f"""
Create a full-body vertical seed image of Lena for a short movement Reel.

Identity:
Use the {identity} character element/reference as the identity anchor. Preserve Lena's face, body proportions, hair, skin tone, and recognizable presence.

Why this clip exists:
{recipe['human_reason']}

Scene:
{recipe['setting']}

Ready pose:
{recipe['action']}

Wardrobe:
{recipe['wardrobe']}

Camera:
{recipe['shot']}. Full body visible, feet fully in frame, hands simple and visible, clean floor space.

Hard visual bans:
{VISUAL_BANS[0]}
{VISUAL_BANS[1]}
{VISUAL_BANS[2]}
""".strip()


def build_video_motion_prompt(recipe: dict[str, Any]) -> str:
    motion = recipe.get("video_motion") or "simple smooth movement, natural expression, clean ending pose"
    return f"""
Create a short vertical movement video from the seed image.

Motion:
{motion}

Continuity:
Keep Lena's face, body, outfit, hair, jewelry, and background stable. No face drift, no body warping, no flicker, no extra limbs.

Camera:
Locked vertical phone camera. Full body stays visible. Hands and feet stay inside the frame. No cuts, no zoom jumps, no interface overlay.

Publishing:
This video requires music selection before posting. Silent movement clips are not final social content.
""".strip()


def estimated_credits(mtype: str, node: dict[str, Any]) -> int:
    costs = node["kling"].get("known_costs", {})
    if mtype == "video":
        return int(costs.get("video_3_0_1080p_5s_1_output_native_audio") or 60)
    return int(costs.get("image_3_0_2k_hd_1_output") or 1)


def upgrade_manifest(path: Path) -> dict[str, Any]:
    node = load_node()
    memory = load_memory()
    data = load_json(path)
    used_families: set[str] = set()
    summaries = []

    for slot in data.get("slots", []):
        lane = choose_lane(slot, node, memory, used_families)
        recipe = LANE_RECIPES[lane]
        mtype = media_type(slot)
        meta = slot.setdefault("metadata", {})
        caption = clean_public_caption(recipe["caption"])

        if mtype == "video":
            image_prompt = build_video_seed_prompt(recipe, node)
            video_prompt = build_video_motion_prompt(recipe)
            slot["image_prompt"] = image_prompt
            slot["video_prompt"] = video_prompt
            slot["negative_prompt"] = NEGATIVE_PROMPT
            slot["caption"] = caption
            meta["image_prompt"] = image_prompt
            meta["video_prompt"] = video_prompt
            meta["music_required_before_publish"] = True
            meta["silent_auto_publish_allowed"] = False
            meta["motion_control_requested"] = True
            meta["motion_control_policy"] = (
                "required by Lena Kling contract; live spend still requires "
                "manual approval"
            )
            meta["kling_route"] = "Kling VIDEO 3.0 with Motion Control"
        else:
            image_prompt = build_photo_prompt(recipe, node)
            slot["image_prompt"] = image_prompt
            slot["negative_prompt"] = NEGATIVE_PROMPT
            slot["caption"] = caption
            meta["image_prompt"] = image_prompt
            meta["kling_route"] = "IMAGE 3.0"
            meta["image_outputs_requested"] = node["kling"]["credit_policy"].get("image_outputs_per_slot_default", 1)

        meta["caption"] = caption
        meta["node_version"] = VERSION
        meta["lane"] = lane
        meta["pillar"] = recipe["pillar"]
        meta["human_reason"] = recipe["human_reason"]
        meta["overlay_hook"] = recipe.get("overlay_hook")
        meta["overlay_text_allowed_only_in_post"] = True
        meta["identity_element"] = node["kling"]["identity_elements"]["primary"]
        meta["negative_prompt"] = NEGATIVE_PROMPT
        meta["visual_bans"] = VISUAL_BANS
        meta["estimated_credits"] = estimated_credits(mtype, node)
        meta["manual_review_required"] = True
        meta["reject_if"] = [
            "any text, logo, sign, label, watermark, UI, or garbled mark appears",
            "the scene does not feel like Lena's real life",
            "wardrobe feels boring, fake, costume-like, or too generic",
            "hands, face, body, or frame edges contain artifacts",
            "post feels like a stock photo instead of a real social post",
            "asset feels like the same seed image reused or a previous accepted image repeated with minor changes",
            "same pose or composition formula appears across more than one slot in the batch",
            "Lena looks pasted into a scene rather than naturally photographed as part of it",
            "image uses the same pretty standing portrait formula as another slot without a distinct story, location, or mood",
            "outfit is a full suit, pantsuit, corporate blazer-and-trouser combination, business suit, or officewear",
            "styling is business-professional or looks like corporate officewear rather than creator or lifestyle energy",
            "Lena looks frumpy, overly covered, or sexless in a way that hides her physical appeal",
            "image is technically realistic but has no visual hook, no eye-catch, no scroll-stopping quality",
            "no flattering body silhouette or confident body language is visible",
            "image is safe-but-boring: generic stock-photo professionalism with no creator or lifestyle energy",
            "body is hidden under shapeless, oversized, or heavily draped clothing with no visible feminine silhouette",
            "outfit hides Lena's waist, hips, or shape; no hourglass or feminine body line is visible",
            "Lena's curvy figure is not apparent — proportions look flat, boxy, or androgynous",
            "Lena looks too slim, skinny, or model-thin — body lacks the thick curvy hourglass shape: no visible waist definition, flat hips, or narrow lower body",
            "Lena's body proportions look obese, chubby, plus-size, cartoonish, anatomically distorted, or impossibly exaggerated",
            "body, cleavage, hip, thigh, or waist emphasis becomes explicit, crotch-focused, fetish-framed, nude, pornographic, or sexually graphic",
            "daytime or street styling looks like cheap clubwear or is inappropriate for a luxury elevated context",
            "night-out styling looks corporate, business-professional, or bland rather than attractive nightlife looks",
            "image contains explicit, fetish, nude, or pornographic framing",
            "freckle-like spot clusters, heavy speckling, identity-changing freckle patterns, acne-like blotches, or dark facial spots appear on Lena's skin",
            "body is hidden by crop — lane requires visible waist, hip, and thigh silhouette",
            "hips, thighs, or glute curve not visible enough when scene and wardrobe call for body framing",
            "Lena's face expression looks like a direct neutral seed-reference copy with no expression variety",
            "repeated neutral or emotionless expression that mirrors the reference seed face",
            "clothing is too plain, smooth, or detail-free — no visible fabric texture, seams, or natural wrinkles",
            "background looks like a generic showroom, stock kitchen, blank apartment, or AI render set with no lived-in details",
            "scene lacks a micro-story — Lena looks posed for a model portfolio with no real-life moment",
            "fabric looks plastic, painted-on, or unnaturally smooth",
            "hips, thighs, waist, arms, hands, or clothing clip into counters, tables, cabinets, chairs, walls, or props",
            "body/object boundaries are fused, melted, intersecting, or physically impossible",
            "countertop or furniture cuts through Lena's body instead of sitting naturally behind or in front of her",
            "head or upper torso is subtly oversized relative to hips, thighs, and legs",
            "lower body is visually shrunken by perspective, crop, lens distortion, or pose",
            "contact shadows or depth ordering make the body/furniture relationship physically unclear",
            "generated body is slimmer, less curvy, narrower-hipped, smaller-thighed, or less hourglass than the body-reference target",
            "outfit, crop, or pose hides the waist-to-hip curve or conceals the body-reference silhouette",
            "high-waist clothing flattens or conceals the body-reference waist-to-hip silhouette",
            "outfit is shapeless, oversized, or body-hiding when the lane calls for the 75% hooky lifestyle mode",
            "visible waist-to-hip contrast is absent when wardrobe and scene call for it",
            "hips, thighs, or legs are hidden, cropped out, or visually reduced when mid-thigh or 3/4 body framing is required",
            "head appears close to hip width or wider — hips must read clearly wider than the head",
            "hips do not appear about 2x head width or more in full-body or 3/4 framing",
            "portrait or close-up framing creates oversized head, enlarged upper torso, or shrunken lower body",
            "outfit is boxy, bulky, or heavily layered and hides the waist-to-hip curve",
        ]

        summaries.append({
            "slot_id": slot.get("slot_id"),
            "media_type": mtype,
            "lane": lane,
            "pillar": recipe["pillar"],
            "estimated_credits": meta["estimated_credits"],
            "overlay_hook": recipe.get("overlay_hook"),
        })

    data["influencer_node_version"] = VERSION
    data["creative_director_version"] = VERSION
    data["prompt_detail_version"] = VERSION
    data["node_config_used"] = str(NODE_ROOT)
    data["node_policy"] = {
        "human_like_in_every_way": True,
        "benchmark_architecture": node["benchmark"]["name"],
        "kling_budget_aware": True,
        "text_hooks_post_production_only": True,
        "manual_review_required": True,
        "motion_control_required_for_video": True,
    }
    data["node_updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "ok": True,
        "path": str(path),
        "version": VERSION,
        "summaries": summaries,
        "estimated_daily_credits": sum(int(x["estimated_credits"]) for x in summaries),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: lena_influencer_node_v1_3.py <daily_workorders.json>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"missing file: {path}"}, indent=2))
        return 1
    print(json.dumps(upgrade_manifest(path), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
