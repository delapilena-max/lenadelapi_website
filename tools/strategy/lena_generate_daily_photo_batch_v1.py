"""
Lena Daily Photo Batch Generator v1

Generates a dry-run daily photo production plan for 7 Lena images per day.
No images are generated. No providers are called. No publishing occurs.

Safe: no image generation, no OpenArt/Kling calls, no credits spent,
no R2 upload, no publishing, no Instagram/Facebook/Reels,
no publisher file modification, not connected to any automatic queue.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT           = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STRATEGY_BASE  = os.path.join(ROOT, "pipeline", "strategy", "lena")
BATCHES_BASE   = os.path.join(ROOT, "pipeline", "workorders", "lena", "photo_batches")

PILLARS_PATH   = os.path.join(STRATEGY_BASE, "content_pillars.json")
FORMATS_PATH   = os.path.join(STRATEGY_BASE, "viral_format_library.json")

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def pillar_index(pillars_data: dict) -> dict:
    return {p["id"]: p for p in pillars_data.get("pillars", [])}

# ---------------------------------------------------------------------------
# Shared prompt components
# ---------------------------------------------------------------------------

LENA_CHARACTER_BASE = (
    "Photorealistic Lena — luxury lifestyle and high-end fashion fit-check influencer, soft-glam beauty maintenance and fitness-glam aesthetic, same face, same hairstyle, "
    "same outfit, same apartment across all images. "
    "Natural skin texture, visible pores, subtle imperfections, "
    "soft glam but not plastic, warm expressive eyes. "
    "Lived-in apartment: plants everywhere, gaming setup visible, "
    "dog and turtle present or implied. "
    "Realistic candid composition, intentional off-center framing, "
    "not dead-center, not over-polished, keeps a casual phone-camera feel. "
    "Looks like a real creator filming at home, not a brand shoot. "
    "Ordinary phone photo feel: casual handheld framing, natural room light, apartment lamp or window light. "
    "No HDR processing, no portrait mode smoothing, no studio lighting. "
    "Slight motion blur in non-focal areas is acceptable. Natural phone compression. Imperfect crop preferred over centered perfection."
)

NEGATIVE_PROMPT = (
    "No plastic or poreless skin. "
    "No generic golden-hour lighting without narrative reason. "
    "No dead-center perfect symmetry. "
    "No over-detailed cluttered background competing with the subject. "
    "No generic perfect influencer face — Lena has character, warmth, subtle imperfection. "
    "No unmotivated shallow depth of field. "
    "No over-saturated colors. "
    "No sterile or catalog-clean apartment. "
    "No heavy AI post-processing artifacts or uncanny smoothing. "
    "No uniform or flat lighting. "
    "No posed brand-shoot stiffness. "
    "No professional photography look, studio lighting, DSLR or mirrorless quality, bokeh, 4K, 8K, high resolution, or sharp-focus perfection. "
    "No cinematic grading, magazine quality, commercial fashion shoot, editorial shoot, portfolio look, or model portfolio posing. "
    "No portrait mode smoothing, no overly polished or perfectly posed result. "
    "No beautiful or stunning descriptor language in positive prompt sections."
)

TEXTURE_QUALITY_NOTES = (
    "Natural skin texture is a quality gate requirement. "
    "Visible pores and subtle imperfections are correct. "
    "If output has plastic skin or poreless smoothing, regenerate before review. "
    "Soft glam should read as real makeup on real skin, not CGI skin. "
    "Compensate for any reference quality issues with stronger texture prompt weight."
)

OUTFIT_CONTINUITY = (
    "Same outfit, hairstyle, and soft glam level as the selfie_face_anchor image for this batch. "
    "Minor variation acceptable (sleeves pushed up, hair slightly different) "
    "but character identity must be immediately recognizable across all 7 images."
)

SCENE_CONTINUITY = (
    "Same apartment throughout. Same plant density, same gaming setup position, "
    "same general lighting temperature. "
    "Apartment does not have to be identical in every detail — "
    "lived-in variation is correct — but the space must feel like the same home."
)

# ---------------------------------------------------------------------------
# Photo slot definitions
# ---------------------------------------------------------------------------

def build_photo_slots(run_date: str, pillars: dict) -> list:
    date_compact = run_date.replace("-", "")

    slots = [
        # ------------------------------------------------------------------
        # 1. SELFIE FACE ANCHOR
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_01",
            "slot_type":           "selfie_face_anchor",
            "title":               "Selfie Face Anchor — Identity Reference",
            "content_pillar":      "soft_glam",
            "visual_goal": (
                "Establish Lena's face, hairstyle, and soft glam level for this batch. "
                "This is the identity reference image. All other images should be "
                "recognizably the same person."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 close-to-medium selfie. Lena holding phone slightly above eye level, "
                "looking into camera with warm, direct confidence. Natural apartment lighting — "
                "window light or soft lamp, not ring light. Soft glam: light foundation, subtle eye, "
                "clear lip or soft nude. Hair natural or loosely styled. "
                "Background: apartment plants and soft living room blur. "
                "Expression: relaxed, warm, present. Off-center composition. "
                "This image should feel like an honest, unposed creator moment, not a headshot."
            ),
            "negative_prompt":        NEGATIVE_PROMPT,
            "composition_notes":      "Medium shot to close-up. Slightly off-center. Natural tilt, not perfectly upright.",
            "texture_quality_notes":  TEXTURE_QUALITY_NOTES,
            "angle_compensation_notes": (
                "If reference angle is slightly unflattering, compensate with warmer lighting "
                "and stronger texture detail. Do not over-smooth. Character over perfection."
            ),
            "outfit_continuity_notes": (
                "This image sets the outfit and style for the full batch. "
                "Choose a casual-but-put-together look: oversized soft top, denim, or loungewear with a detail."
            ),
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "just her 🌿",
            "required_visual_evidence": [
                "Lena's face and soft glam makeup visible",
                'apartment interior behind her (plants, window, or room context)',
                'natural phone-held framing angle',
                'warm window or lamp light on face',
            ],
            "forbidden_contradictions": [
                'outdoor location',
                'studio lighting or ring light glow in eyes',
                'no apartment context behind her',
                'blank white or gray studio background',
            ],
            "caption_intent": 'identity anchor — honest unposed creator face to open the batch',
            "environment_realism_notes": 'apartment plants and soft living room blur behind; window light or soft lamp',
            "photo_realism_notes": 'handheld slightly above eye level, off-center, natural tilt, no ring light',
            "body_visibility_requirement": 'medium to close shot; face primary; shoulders and neckline visible',
            "qa_rejection_criteria": [
                'no apartment context visible',
                'studio lighting or professional backdrop',
                'outdoor setting',
                'ring light reflection in eyes',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },

        # ------------------------------------------------------------------
        # 2. APARTMENT LIFESTYLE
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_02",
            "slot_type":           "apartment_lifestyle",
            "title":               "Apartment Lifestyle — Morning or Afternoon Moment",
            "content_pillar":      "plant_apartment",
            "visual_goal": (
                "Capture Lena in her natural apartment habitat — "
                "the cozy, chaotic, plant-filled world she lives in. "
                "Should feel like a genuine moment, not a styled shoot."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 lifestyle image of Lena in her apartment, "
                "seated on the couch or near the window with an iced coffee or warm drink. "
                "Several houseplants visible — hanging, shelved, on windowsill. "
                "Natural morning or afternoon light through the window. "
                "Lena looks relaxed, slightly distracted, like she paused mid-thought. "
                "Laptop or journal nearby but not the focus. "
                "Composition: environmental — Lena is part of the space, not dominating it. "
                "Warm, lived-in, aspirational-but-real apartment energy."
            ),
            "negative_prompt":        NEGATIVE_PROMPT,
            "composition_notes": (
                "Environmental composition. Lena occupies 40-60% of frame. "
                "Plants, apartment details, and light fill the rest. Off-center."
            ),
            "texture_quality_notes":  TEXTURE_QUALITY_NOTES,
            "angle_compensation_notes": (
                "If reference shows an awkward angle, reframe so the plant collection "
                "and window light anchor the image and draw attention away from the angle."
            ),
            "outfit_continuity_notes": OUTFIT_CONTINUITY,
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "the apartment is thriving. i am also doing okay. 🌿",
            "required_visual_evidence": [
                'apartment interior',
                'houseplants visible (multiple preferred)',
                'drink or beverage nearby (iced coffee or warm drink)',
                'natural window or lamp light',
                'couch, floor, or window as setting',
            ],
            "forbidden_contradictions": [
                'outdoor location',
                'bare or plant-free room',
                'studio lighting',
                'cafe or public setting',
                'no drink or apartment prop',
            ],
            "caption_intent": 'natural apartment habitat moment — cozy, plant-filled, unposed',
            "environment_realism_notes": 'multiple houseplants hanging/shelved/on windowsill; laptop or journal nearby; warm morning or afternoon light',
            "photo_realism_notes": 'environmental composition; Lena occupies 40-60% of frame; plants and light fill the rest',
            "body_visibility_requirement": 'waist-up or three-quarter; seated or near window; environmental framing',
            "qa_rejection_criteria": [
                'outdoor location',
                'no plants visible',
                'cafe or public interior setting',
                'sterile apartment without lived-in details',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },

        # ------------------------------------------------------------------
        # 3. DOG MOMENT
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_03",
            "slot_type":           "dog_moment",
            "title":               "Dog Moment — Candid Pet Interruption",
            "content_pillar":      "pet_moments",
            "visual_goal": (
                "Capture the dog as a natural, unplanned participant in Lena's day. "
                "Should feel like a genuine interruption or cuddle moment, "
                "not a posed pet photo."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 candid image of Lena with her small-to-medium dog. "
                "Dog is leaning against her, in her lap, or nudging into frame. "
                "Lena's expression: fond, slightly exasperated, or laughing. "
                "Not a posed pet portrait — this is a real moment caught mid-scroll or mid-work. "
                "Apartment floor or couch visible. Plants in background. "
                "Natural apartment lighting. Dog as the clear co-subject. "
                "Camera angle slightly lower, as if Lena is holding the phone at her side or lap. "
                "Composition: both Lena and dog visible, dog dominant or equal."
            ),
            "negative_prompt": (
                f"{NEGATIVE_PROMPT} "
                "No professional pet photography staging. No forced poses. "
                "No overly bright studio lighting."
            ),
            "composition_notes": (
                "Low-to-mid angle. Both Lena and dog in frame. "
                "Dog at or near camera level if possible. Natural handheld feel."
            ),
            "texture_quality_notes":  TEXTURE_QUALITY_NOTES,
            "angle_compensation_notes": (
                "Lower angles and dog presence naturally compensate for reference quality issues. "
                "Let the dog be the visual anchor. Lena's reaction is the emotional anchor."
            ),
            "outfit_continuity_notes": OUTFIT_CONTINUITY,
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "he needed me. i was available. 🐾",
            "required_visual_evidence": [
                'dog clearly visible in frame',
                'both Lena and dog visible',
                'apartment floor or couch as setting',
                'plants in background',
                'natural apartment lighting',
            ],
            "forbidden_contradictions": [
                'no dog visible in frame',
                'dog barely visible or out of frame',
                'outdoor dog park without apartment context',
                'posed professional pet portrait staging',
                'studio or bright artificial lighting',
            ],
            "caption_intent": 'dog as natural unplanned participant — genuine interruption or cuddle',
            "environment_realism_notes": 'apartment floor or couch; plants visible; dog leaning, in lap, or nudging into frame',
            "photo_realism_notes": 'camera angle slightly lower; handheld side or lap feel; dog as co-subject',
            "body_visibility_requirement": "both Lena and dog in frame; dog at or near camera level; Lena's reaction visible",
            "qa_rejection_criteria": [
                'no dog visible',
                'dog is barely a background element',
                'outdoor or non-apartment setting',
                'professional pet photography staging',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },

        # ------------------------------------------------------------------
        # 4. TURTLE MOMENT
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_04",
            "slot_type":           "turtle_moment",
            "title":               "Turtle Moment — The Novelty Differentiator",
            "content_pillar":      "pet_moments",
            "visual_goal": (
                "Highlight the turtle as Lena's rare, unexpected pet. "
                "Turtle is the differentiator — lean into it for comments and saves. "
                "Should feel surprising and delightful, not posed or performative."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 image of Lena and her turtle. "
                "Turtle is on the floor, a surface, or near Lena's hand. "
                "Lena is looking at the turtle with amused curiosity or affection. "
                "Camera close enough that the turtle is clearly visible and identifiable. "
                "Apartment details in background: plants, desk, lived-in surfaces. "
                "Natural lighting. Composition: turtle as the visual surprise, "
                "Lena as the emotional reaction. "
                "Do not make the turtle look threatening or strange — it is a companion."
            ),
            "negative_prompt": (
                f"{NEGATIVE_PROMPT} "
                "No overly dramatic wildlife photography style. "
                "No dark or moody turtle-as-object framing."
            ),
            "composition_notes": (
                "Turtle must be clearly visible. "
                "Tighter composition than the dog moment — turtle is smaller. "
                "Lena and turtle both in frame. Off-center."
            ),
            "texture_quality_notes":  TEXTURE_QUALITY_NOTES,
            "angle_compensation_notes": (
                "Turtle novelty carries this image. "
                "If Lena reference angle is imperfect, tight composition and turtle presence compensate."
            ),
            "outfit_continuity_notes": OUTFIT_CONTINUITY,
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "he does not care about my schedule and i respect it 🐢",
            "required_visual_evidence": [
                'turtle clearly visible and identifiable',
                'both Lena and turtle in frame',
                'apartment details in background',
                'natural apartment lighting',
                'close enough framing to see turtle clearly',
            ],
            "forbidden_contradictions": [
                'no turtle visible in frame',
                'turtle barely visible or too small',
                'outdoor or wildlife photography setting',
                'dark or moody turtle-as-object framing',
                'studio or artificial lighting',
            ],
            "caption_intent": 'turtle as surprising differentiator — delight and novelty, not performance',
            "environment_realism_notes": "turtle on floor, surface, or near Lena's hand; apartment desk, plants, or lived-in surfaces",
            "photo_realism_notes": "tighter composition than dog moment; turtle at or near camera level; Lena's reaction visible",
            "body_visibility_requirement": "both Lena and turtle in frame; Lena's expression of amused curiosity visible",
            "qa_rejection_criteria": [
                'no turtle visible',
                'turtle too small or unclear to identify',
                'outdoor or wildlife setting',
                'Lena not reacting to turtle',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },

        # ------------------------------------------------------------------
        # 5. GOING-OUT STYLE CHECK
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_05",
            "slot_type":           "going_out_style_check",
            "title":               "Going-Out Style Check — Classy Luxury Look",
            "content_pillar":      "going_out_fashion",
            "visual_goal": (
                "Show Lena in a polished going-out look — elevated, expensive-looking, "
                "platform-safe. Apartment entryway or full-length mirror fit check. "
                "Classy luxury baddie energy: sleek heels, gold jewelry, glossy lip."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 image of Lena in a polished going-out look, "
                "standing in apartment entryway or checking full outfit in a full-length mirror. "
                "Classy luxury-styled dress or sleek dressy co-ord — fitted and body-forward. "
                "Sleek heels, delicate gold jewelry, glossy lip. "
                "One hand on hip or touching hair, confident bold expression, "
                "ready-to-leave energy. "
                "Warm ambient apartment light. "
                "No readable text or logos. No phone UI visible in any reflection."
            ),
            "negative_prompt": (
                f"{NEGATIVE_PROMPT} "
                "No cheap clubwear or discount-looking styling. "
                "No lingerie or underwear framing. "
                "No campus, class, study, or PR student framing."
            ),
            "composition_notes": (
                "Full body or three-quarter portrait — outfit must read expensive "
                "and intentional from head to thigh. "
                "Warm doorway or mirror framing. Heels and jewelry clearly visible."
            ),
            "texture_quality_notes":  TEXTURE_QUALITY_NOTES,
            "angle_compensation_notes": (
                "Luxury styling detail (heels, jewelry, glossy lip) compensates for "
                "any reference angle issues. "
                "Shift composition focus toward outfit and styling if facial angle is slightly off."
            ),
            "outfit_continuity_notes": OUTFIT_CONTINUITY,
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "going out looking like this. that\'s it. that\'s the post. 💋",
            "required_visual_evidence": [
                'going-out outfit visible (sleek dress, co-ord, or elevated look)',
                'heels or elevated shoes visible',
                'gold jewelry visible',
                'apartment entryway or mirror context',
                'warm ambient apartment light',
            ],
            "forbidden_contradictions": [
                'casual daytime outfit',
                'athletic wear or gym outfit',
                'outdoor street without apartment entryway',
                'no heels or elevated shoes',
                'lingerie or explicit styling',
            ],
            "caption_intent": 'polished luxury going-out look — the reveal moment before leaving',
            "environment_realism_notes": 'apartment entryway or full-length mirror; warm ambient light; no readable text or logos',
            "photo_realism_notes": 'full body or three-quarter; outfit readable from head to thigh; heels and jewelry clearly visible',
            "body_visibility_requirement": 'full body or three-quarter; heels, jewelry, glossy lip all visible; outfit reads expensive',
            "qa_rejection_criteria": [
                'casual or athletic outfit inconsistent with going-out caption',
                'no heels visible',
                'outdoor or public setting without entryway context',
                'cheap or discount-looking styling',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },

        # ------------------------------------------------------------------
        # 6. PLANT OR GAMING DETAIL
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_06",
            "slot_type":           "plant_or_gaming_detail",
            "title":               "Gaming Desk Detail — Night Aesthetic",
            "content_pillar":      "gaming_desk",
            "visual_goal": (
                "Show Lena's gaming setup as an aesthetic anchor — "
                "the cozy tech-meets-glam corner that defines her apartment identity. "
                "This is an atmosphere-first image."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 image of Lena near or at her gaming setup in the evening. "
                "Monitor glow softly visible, RGB accent lighting or warm desk lamp creating atmosphere. "
                "Lena is not in full gaming mode — she is transitioning: "
                "sitting sideways in the chair, looking at phone, or mid-skincare-at-the-desk. "
                "Plants visible nearby or reflected in monitor. "
                "Snack or drink on the desk surface. "
                "Ambient lighting dominates — warm and cozy, not harsh. "
                "Composition: Lena and setup in frame, setup provides the mood."
            ),
            "negative_prompt": (
                f"{NEGATIVE_PROMPT} "
                "No over-saturated RGB rainbow lighting. "
                "No aggressively masculine gamer aesthetic. "
                "No dark moody gaming den — Lena's setup is cozy and glam, not aggressive."
            ),
            "composition_notes": (
                "Environmental shot. Setup and Lena share the frame. "
                "Monitor glow as a light source is intentional. "
                "Off-center, slightly wider than other slots."
            ),
            "texture_quality_notes":  TEXTURE_QUALITY_NOTES,
            "angle_compensation_notes": (
                "Ambient lighting and monitor glow carry this image aesthetically. "
                "If reference quality is lower, let the gaming setup atmosphere do the visual work."
            ),
            "outfit_continuity_notes": (
                f"{OUTFIT_CONTINUITY} "
                "Evening variation acceptable: hair down, cozy layer added."
            ),
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "productive night or cozy night. the setup does not judge. 🎮",
            "required_visual_evidence": [
                'gaming setup visible (monitor, desk, or RGB/lamp glow)',
                'cozy atmosphere (warm lamp or ambient glow)',
                'Lena near or at the setup',
                'plants visible nearby or reflected',
                'apartment evening context',
            ],
            "forbidden_contradictions": [
                'no gaming setup or desk visible',
                'outdoor or public setting',
                'bright studio or harsh lighting',
                'aggressive neon RGB rainbow without cozy quality',
                'bare room without gaming context',
            ],
            "caption_intent": 'gaming setup as cozy aesthetic anchor — the tech-meets-glam corner',
            "environment_realism_notes": 'monitor glow, RGB accent or warm desk lamp, plants nearby, snack or drink on desk',
            "photo_realism_notes": 'environmental shot; setup and Lena share frame; monitor glow as light source',
            "body_visibility_requirement": 'Lena and setup both in frame; Lena not in full gaming mode — transitional moment',
            "qa_rejection_criteria": [
                'no gaming setup or desk visible',
                'outdoor or non-apartment setting',
                'Lena not near or at the setup',
                'aggressive gaming den aesthetic without cozy quality',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },

        # ------------------------------------------------------------------
        # 7. EXPERIMENTAL TREND STYLE TEST
        # ------------------------------------------------------------------
        {
            "photo_id":            f"lena_photo_{date_compact}_07",
            "slot_type":           "experimental_trend_style_test",
            "title":               "Experimental Style Test — Relatable Chaos Format",
            "content_pillar":      "relatable_chaos",
            "visual_goal": (
                "Test a slightly different format, angle, or energy from the rest of the batch. "
                "This slot is for creative variation — what happens if Lena tries something slightly off-script. "
                "Relatable chaos energy, honest and unposed."
            ),
            "prompt": (
                f"{LENA_CHARACTER_BASE} "
                "Vertical 9:16 image of Lena in a candid, slightly chaotic moment. "
                "She might be mid-action: checking something on her phone with a dramatic expression, "
                "looking at the camera like she is about to say something but hasn't yet, "
                "or reacting to something offscreen with amused disbelief. "
                "Apartment fully visible — plants, clutter, lived-in surfaces. "
                "No attempt to clean up or stage the background. "
                "Natural whatever-light-is-happening lighting. "
                "Expression is the subject, not the setup. "
                "This image should feel like a screenshot from a story, not a planned post."
            ),
            "negative_prompt": (
                f"{NEGATIVE_PROMPT} "
                "No staged candid poses. "
                "No carefully curated background. "
                "No 'trying too hard to look casual' energy."
            ),
            "composition_notes": (
                "This slot is the most experimental. "
                "Off-center, tilted, or slightly unusual angle acceptable. "
                "Story-frame aesthetic. Raw energy over polish."
            ),
            "texture_quality_notes": (
                f"{TEXTURE_QUALITY_NOTES} "
                "For this slot specifically: slightly lower technical polish is acceptable "
                "if the expression and energy are strong. Authenticity > perfection here."
            ),
            "angle_compensation_notes": (
                "This slot is designed to absorb angle variation. "
                "Imperfect reference angles are less problematic here — "
                "raw and real is the aesthetic goal."
            ),
            "outfit_continuity_notes": OUTFIT_CONTINUITY,
            "scene_continuity_notes":  SCENE_CONTINUITY,
            "caption_seed":            "the vibe is a process 😭",
            "required_visual_evidence": [
                'apartment environment visible (plants, clutter, lived-in surfaces)',
                'expressive or candid face visible',
                'natural apartment light (whatever is available)',
                'unstaged or slightly chaotic background',
            ],
            "forbidden_contradictions": [
                'carefully curated or cleaned-up background',
                'outdoor or public setting',
                'studio lighting or professional backdrop',
                'overly posed or stiff composition',
                'no visible apartment context',
            ],
            "caption_intent": 'candid chaotic moment — raw expression over polish, story-screenshot energy',
            "environment_realism_notes": 'apartment fully visible — plants, clutter, lived-in surfaces; no attempt to clean up',
            "photo_realism_notes": 'off-center or tilted; story-frame aesthetic; slightly unusual angle acceptable; raw energy',
            "body_visibility_requirement": 'expression is primary subject; upper body or full body; experimental framing acceptable',
            "qa_rejection_criteria": [
                'no apartment context visible',
                'outdoor or non-apartment setting',
                'staged or perfectly composed shot inconsistent with experimental intent',
                'no candid or expressive element',
            ],
            "platform_fit":            ["instagram", "facebook"],
        },
    ]

    # Inject shared status fields into every slot
    for slot in slots:
        slot["approval_status"]                  = "draft_review_required"
        slot["generation_status"]                = "not_generated"
        slot["publishing_approval"]              = "not_approved"
        slot["provider_call_enabled"]            = False
        slot["generation_call_performed"]        = False
        slot["credits_spent"]                    = False

    return slots

# ---------------------------------------------------------------------------
# Batch builder
# ---------------------------------------------------------------------------

EVIDENCE_REQUIRED_SLOT_FIELDS = [
    "required_visual_evidence",
    "forbidden_contradictions",
    "caption_intent",
    "environment_realism_notes",
    "photo_realism_notes",
    "body_visibility_requirement",
    "qa_rejection_criteria",
]


def validate_slot_evidence_present(
    slots: list,
) -> None:
    """Raise ValueError if any slot is missing
    required scene evidence contract fields.
    """
    for slot in slots:
        st = slot.get("slot_type", "unknown")
        for field in EVIDENCE_REQUIRED_SLOT_FIELDS:
            if not slot.get(field):
                raise ValueError(
                    f"Slot {st!r} missing "
                    f"required field: {field!r}"
                )


def build_batch(batch_id: str, run_date: str, photo_slots: list) -> dict:
    return {
        "batch_id":                             batch_id,
        "date":                                 run_date,
        "node":                                 "lena",
        "production_mode":                      "photo_first",
        "daily_photo_target":                   7,
        "photo_slots":                          photo_slots,
        "video_generation_paused":              True,
        "kling_generation_paused":              True,
        "audio_generation_required":            False,
        "publishing_approval":                  "not_approved",
        "requires_human_review_before_publish": True,
        "provider_call_enabled":                False,
        "generation_call_performed":            False,
        "credits_spent":                        False,
        "created_at":                           datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_batch(batch: dict, run_date: str) -> str:
    output_dir = os.path.join(BATCHES_BASE, run_date)
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{batch['batch_id']}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)
    return filepath

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate(filepath: str) -> tuple[bool, list]:
    required_batch = [
        "batch_id", "date", "node", "production_mode", "daily_photo_target",
        "photo_slots", "video_generation_paused", "kling_generation_paused",
        "audio_generation_required", "publishing_approval",
        "requires_human_review_before_publish", "provider_call_enabled",
        "generation_call_performed", "credits_spent", "created_at",
    ]
    required_slot = [
        "photo_id", "slot_type", "title", "content_pillar", "visual_goal",
        "prompt", "negative_prompt", "composition_notes", "texture_quality_notes",
        "angle_compensation_notes", "outfit_continuity_notes", "scene_continuity_notes",
        "caption_seed", "platform_fit",
        "required_visual_evidence", "forbidden_contradictions",
        "caption_intent", "environment_realism_notes",
        "photo_realism_notes", "body_visibility_requirement",
        "qa_rejection_criteria",
        "approval_status", "generation_status", "publishing_approval",
        "provider_call_enabled", "generation_call_performed", "credits_spent",
    ]
    errors = []
    with open(filepath, encoding="utf-8") as f:
        batch = json.load(f)

    missing = [k for k in required_batch if k not in batch]
    if missing:
        errors.append(f"Batch missing fields: {missing}")

    if batch.get("provider_call_enabled") is not False:
        errors.append("batch.provider_call_enabled must be false")
    if batch.get("generation_call_performed") is not False:
        errors.append("batch.generation_call_performed must be false")
    if batch.get("credits_spent") is not False:
        errors.append("batch.credits_spent must be false")
    if batch.get("publishing_approval") != "not_approved":
        errors.append(f"batch.publishing_approval must be 'not_approved'")
    if batch.get("video_generation_paused") is not True:
        errors.append("video_generation_paused must be true")
    if batch.get("kling_generation_paused") is not True:
        errors.append("kling_generation_paused must be true")

    slots = batch.get("photo_slots", [])
    if len(slots) != 7:
        errors.append(f"photo_slots must contain 7 entries, got {len(slots)}")

    for slot in slots:
        missing_slot = [k for k in required_slot if k not in slot]
        if missing_slot:
            errors.append(f"Slot '{slot.get('slot_type')}' missing fields: {missing_slot}")
        if slot.get("publishing_approval") != "not_approved":
            errors.append(f"Slot '{slot.get('slot_type')}' publishing_approval must be 'not_approved'")
        if slot.get("generation_status") != "not_generated":
            errors.append(f"Slot '{slot.get('slot_type')}' generation_status must be 'not_generated'")
        if slot.get("approval_status") != "draft_review_required":
            errors.append(f"Slot '{slot.get('slot_type')}' approval_status must be 'draft_review_required'")

    return (len(errors) == 0), errors

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(batch: dict, filepath: str, valid: bool, errors: list):
    slots = batch.get("photo_slots", [])
    approval_counts  = {}
    generation_counts = {}
    for s in slots:
        a = s.get("approval_status", "unknown")
        g = s.get("generation_status", "unknown")
        approval_counts[a]   = approval_counts.get(a, 0) + 1
        generation_counts[g] = generation_counts.get(g, 0) + 1

    print()
    print("=" * 64)
    print("  LENA DAILY PHOTO BATCH GENERATOR v1 — BATCH COMPLETE")
    print("=" * 64)
    print(f"  Output path              : {filepath}")
    print(f"  batch_id                 : {batch['batch_id']}")
    print(f"  date                     : {batch['date']}")
    print(f"  production_mode          : {batch['production_mode']}")
    print(f"  daily_photo_target       : {batch['daily_photo_target']}")
    print(f"  photo slots built        : {len(slots)}")
    print(f"  video_generation_paused  : {batch['video_generation_paused']}")
    print(f"  kling_generation_paused  : {batch['kling_generation_paused']}")
    print(f"  provider_call_enabled    : {batch['provider_call_enabled']}")
    print(f"  generation_call_performed: {batch['generation_call_performed']}")
    print(f"  credits_spent            : {batch['credits_spent']}")
    print(f"  publishing_approval      : {batch['publishing_approval']}")
    print()
    print("  APPROVAL STATUS COUNTS:")
    for status, count in approval_counts.items():
        print(f"    {status}: {count}")
    print()
    print("  GENERATION STATUS COUNTS:")
    for status, count in generation_counts.items():
        print(f"    {status}: {count}")
    print()
    print("  SLOTS:")
    for slot in slots:
        print(f"    [{slot['photo_id']}] {slot['slot_type']:35s} pillar: {slot['content_pillar']}")
    print(f"  JSON validation          : {'VALID' if valid else 'INVALID'}")
    if errors:
        print()
        print("  VALIDATION ERRORS:")
        for e in errors:
            print(f"    {e}")
    print()
    print("  NO images generated.    NO OpenArt call.    NO Kling call.")
    print("  NO credits spent.       NO R2 upload.")
    print("  NO publishing.          NO Instagram / Facebook / Reels.")
    print("  NO publisher files modified.  NOT queued for automatic generation.")
    print("=" * 64)
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Lena Daily Photo Batch Generator v1 — dry run"
    )
    parser.add_argument(
        "--date",
        default="2026-06-14",
        help="Batch date (YYYY-MM-DD). Default: 2026-06-14."
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Batch ID override. Default: lena_photo_batch_001_YYYYMMDD."
    )
    args = parser.parse_args()

    run_date    = args.date
    date_compact = run_date.replace("-", "")
    batch_id    = args.batch_id or f"lena_photo_batch_001_{date_compact}"

    print(f"[lena_generate_daily_photo_batch_v1] Date     : {run_date}")
    print(f"[lena_generate_daily_photo_batch_v1] Batch ID : {batch_id}")

    print(f"[lena_generate_daily_photo_batch_v1] Loading strategy files...")
    pillars_data = load_json(PILLARS_PATH)
    _formats_data = load_json(FORMATS_PATH)  # loaded for context, not yet used in v1
    pillars = pillar_index(pillars_data)
    print(f"[lena_generate_daily_photo_batch_v1] Pillars loaded: {len(pillars)}")

    print(f"[lena_generate_daily_photo_batch_v1] Building photo slots...")
    photo_slots = build_photo_slots(run_date, pillars)
    print(f"[lena_generate_daily_photo_batch_v1] Slots built: {len(photo_slots)}")

    print(f"[lena_generate_daily_photo_batch_v1] Building batch...")
    batch = build_batch(batch_id, run_date, photo_slots)

    print(f"[lena_generate_daily_photo_batch_v1] Saving...")
    filepath = save_batch(batch, run_date)

    print(f"[lena_generate_daily_photo_batch_v1] Validating...")
    valid, errors = validate(filepath)

    print_summary(batch, filepath, valid, errors)


if __name__ == "__main__":
    main()
