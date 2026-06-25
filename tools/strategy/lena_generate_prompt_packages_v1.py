"""
Lena Prompt Package Generator v1

Reads approved idea cards + creative review, merges refinements, and generates
structured prompt packages for human review.

Safe: no API calls, no workorders, no Instagram, no Facebook, no R2, no pipeline wiring.
"""

import argparse
import json
import os
import sys
from datetime import date

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT            = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IDEA_CARDS_BASE = os.path.join(ROOT, "pipeline", "strategy", "lena", "idea_cards")
PACKAGES_BASE   = os.path.join(ROOT, "pipeline", "strategy", "lena", "prompt_packages")

# ---------------------------------------------------------------------------
# Lena character anchor — injected into every video and image prompt
# ---------------------------------------------------------------------------

LENA_CHARACTER_ANCHOR = (
    "Lena: luxury lifestyle and high-end fashion fit-check influencer, soft-glam beauty maintenance and fitness-glam aesthetic. "
    "Warm apartment filled with plants. Small-to-medium dog. Turtle. "
    "Gaming setup visible in background. Chaotic but polished lifestyle energy."
)

# ---------------------------------------------------------------------------
# Quality guardrails — applied to every package
# ---------------------------------------------------------------------------

QUALITY_GUARDRAILS = [
    "Natural skin texture with visible pores and subtle imperfections",
    "Scene-appropriate lighting — no unmotivated golden hour unless it fits the scene",
    "Intentional off-center composition — avoid dead-center symmetry",
    "Clear visual hierarchy — subject is always the dominant element",
    "Lived-in apartment details: plants visible, cozy but real, not catalog-perfect",
    "Lena-specific anchors must appear in frame (see lena_world_anchors field)",
    "Soft glam aesthetic: polished but not sterile, warm not clinical",
    "Camera energy matches format: handheld for chaotic/GRWM, steadier for aesthetic/reset",
    "OpenArt/Seedance-compatible prompt structure — no Higgsfield or Google Flow specific syntax",
    "Phone-captured UGC feel — ordinary handheld framing, not studio or editorial",
    "Natural room light: apartment lamp, window light, or real bathroom light — no studio lighting",
    "Imperfect crop preferred over centered perfection — casual social media composition",
    "Slight motion blur in non-focal areas acceptable; preferred over overly crisp staged detail",
    "Visible pores, subtle redness, unretouched skin texture — no plastic smoothing or poreless result"
]

NEGATIVE_PROMPT_NOTES = [
    "No plastic or poreless skin",
    "No generic golden-hour lighting without narrative reason",
    "No dead-center perfect symmetry",
    "No over-detailed cluttered background competing with the subject",
    "No generic perfect influencer face — Lena has character, warmth, subtle imperfection",
    "No unmotivated shallow depth of field",
    "No over-saturated colors",
    "No sterile or catalog-clean apartment — lived-in is correct",
    "No heavy AI post-processing artifacts or uncanny smoothing",
    "No uniform or flat lighting",
    "No professional photography look, no DSLR or mirrorless quality, no studio lighting",
    "No bokeh, no sharp focus perfection, no 4K, 8K, or high resolution descriptor",
    "No cinematic grading, magazine quality, portfolio shoot, commercial or editorial fashion shoot",
    "No portrait mode smoothing, no perfectly posed result, no model portfolio look",
    "No beautiful or stunning descriptor language in positive prompt sections"
]

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Overlay text sequence extractor
# ---------------------------------------------------------------------------

def extract_overlays(card: dict, review: dict) -> list:
    """Build ordered text overlay sequence from card data and review refinements."""
    refinements = review.get("refinements", {})
    overlays = []

    # 1. Opening hook card
    hook = refinements.get("hook_text_corrected") or card.get("hook_text", "")
    if hook:
        overlays.append({"position": "opening", "text": hook})

    # 2. Scan story_sequence for explicit text card lines
    for beat in card.get("story_sequence", []):
        lower = beat.lower()
        for marker in ["text card: ", "text overlay: "]:
            if marker in lower:
                idx = lower.index(marker) + len(marker)
                raw = beat[idx:].strip().strip("'\"")
                if raw and raw not in [o["text"] for o in overlays]:
                    overlays.append({"position": "beat", "text": raw})
                break

    # 3. Confirmed payoff text from review (flagship) or payoff field
    payoff_confirmed = refinements.get("payoff_confirmed")
    if payoff_confirmed and payoff_confirmed not in [o["text"] for o in overlays]:
        overlays.append({"position": "payoff", "text": payoff_confirmed})
    elif not payoff_confirmed:
        # Try to pull a clean payoff line from the payoff field
        payoff_raw = card.get("payoff", "")
        # Only use it as an overlay if it contains a direct quote pattern
        if payoff_raw and ('"' in payoff_raw or "'" in payoff_raw):
            for quote_char in ['"', "'"]:
                start = payoff_raw.find(quote_char)
                end = payoff_raw.rfind(quote_char)
                if start != end:
                    extracted = payoff_raw[start + 1:end]
                    if extracted and extracted not in [o["text"] for o in overlays]:
                        overlays.append({"position": "payoff", "text": extracted})
                    break

    return overlays

# ---------------------------------------------------------------------------
# Audio direction
# ---------------------------------------------------------------------------

def build_audio_direction(card: dict) -> str:
    raw = card.get("suggested_audio_style", "")
    return raw if raw else (
        "Trending audio appropriate to format energy. "
        "Check current TikTok/Reels trending sounds at time of production."
    )

# ---------------------------------------------------------------------------
# Overlay text sequence extractor (shared)
# ---------------------------------------------------------------------------

def build_overlay_sequence(card: dict, review: dict) -> list:
    refinements = review.get("refinements", {})
    hook = refinements.get("hook_text_corrected") or card.get("hook_text", "")
    payoff = refinements.get("payoff_confirmed", "")
    overlays = []
    if hook:
        overlays.append(hook)
    if payoff and payoff != hook:
        overlays.append(payoff)
    return overlays

# ---------------------------------------------------------------------------
# FLAGSHIP builder — scene-by-scene structure
# ---------------------------------------------------------------------------

# Scene detail templates keyed by deviation keyword.
# Each deviation in approved_story_deviations is matched by keyword.
_DEVIATION_SCENES = {
    "turtle": {
        "scene_name": "Deviation 1 — Turtle on Keyboard",
        "duration_target": "2-3 seconds",
        "visual_description": (
            "Turtle on the keyboard. Keys depressed. Lena's hands stop. "
            "Turtle is unconcerned. Plants visible in background."
        ),
        "character_action": (
            "Genuine reaction — caught off guard, somewhere between amused and defeated. "
            "Does not immediately remove the turtle."
        ),
        "camera_direction": (
            "Hard cut from the desk wide shot. Tight shot on keyboard with turtle. "
            "Quick cut to Lena's face reaction. Do not linger."
        ),
        "overlay_text": "",
        "purpose_of_scene": (
            "First disruption. Sets the comedic tone. "
            "The turtle has no agenda except existing on the keyboard."
        )
    },
    "dog": {
        "scene_name": "Deviation 2 — Dog Interruption",
        "duration_target": "2-3 seconds",
        "visual_description": (
            "Dog at Lena's feet or pushing against her arm. "
            "She is clearly not going anywhere. Apartment floor visible."
        ),
        "character_action": (
            "Lena looks at dog. Dog wins. "
            "She stops attempting to return to the original plan."
        ),
        "camera_direction": (
            "Cut slightly faster than Scene 2. "
            "Wide enough to show dog and Lena interaction. One reaction beat."
        ),
        "overlay_text": "",
        "purpose_of_scene": (
            "Second disruption. Escalates the chaos. "
            "Dog is emotional support that was not requested but is now mandatory."
        )
    },
    "plant": {
        "scene_name": "Deviation 3 — Plant Audit",
        "duration_target": "2-3 seconds",
        "visual_description": (
            "Lena near her plant collection, examining one plant closely. "
            "Multiple plants visible in frame. Watering can nearby or in hand."
        ),
        "character_action": (
            "Fully committed to the audit. The original plan no longer exists to her. "
            "Expression: genuine concern for the plant, zero concern for the deadline."
        ),
        "camera_direction": (
            "Cut is faster than Scene 3. Slightly tighter on plant and Lena's hands. "
            "A brief plant close-up is acceptable but do not linger."
        ),
        "overlay_text": "",
        "purpose_of_scene": (
            "Third disruption. The spiral deepens. "
            "Lena has fully pivoted to a different universe of tasks."
        )
    },
    "game": {
        "scene_name": "Deviation 4 — Game Update",
        "duration_target": "2-3 seconds",
        "visual_description": (
            "Gaming setup screen shows a download or update notification. "
            "Lena is back at the desk — but for a completely different reason."
        ),
        "character_action": (
            "Looks at screen. Looks at camera. Shrugs. Sits down. "
            "The plan is over. This is the point of no return."
        ),
        "camera_direction": (
            "Fastest cut so far. Quick reaction beat — do not linger. "
            "Screen and Lena's face both visible in one shot if possible."
        ),
        "overlay_text": "",
        "purpose_of_scene": (
            "Fourth and final disruption. The acceleration peaks. "
            "The game update is the moment of total surrender."
        )
    }
}


def _match_deviation_template(deviation_text: str) -> dict:
    text_lower = deviation_text.lower()
    for keyword, template in _DEVIATION_SCENES.items():
        if keyword in text_lower:
            return dict(template)
    return {
        "scene_name": deviation_text,
        "duration_target": "2-3 seconds",
        "visual_description": deviation_text,
        "character_action": "Lena reacts. The plan is delayed further.",
        "camera_direction": "Hard cut. Keep it short.",
        "overlay_text": "",
        "purpose_of_scene": "Additional disruption beat."
    }


def build_scene_prompts_flagship(card: dict, review: dict) -> list:
    refinements = review.get("refinements", {})
    approved_beats = refinements.get("approved_story_deviations", [])
    payoff_text = refinements.get("payoff_confirmed", "The plan was a dream. I am a woman of the moment.")

    scenes = []

    # Scene 1: The Confident Plan (opening)
    scenes.append({
        "scene_number": 1,
        "scene_name": "The Confident Plan",
        "duration_target": "3-4 seconds",
        "visual_description": (
            "Lena at her desk in her warm, plant-filled apartment. "
            "Morning or early afternoon light. Gaming setup visible in background. "
            "Desk is organized — a notable contrast to what follows."
        ),
        "character_action": (
            "Lena looks directly to camera with quiet confidence. "
            "The plan exists and it is real. Text card appears."
        ),
        "camera_direction": (
            "Medium shot, slightly off-center. Stable and calm. "
            "This is the baseline before the chaos arrives."
        ),
        "overlay_text": refinements.get("hook_text_corrected") or card.get("hook_text", ""),
        "purpose_of_scene": (
            "Establish the stakes. The plan must feel specific and real. "
            "Lena must look like she genuinely believes it will happen."
        )
    })

    # Scenes 2–N: Approved deviations
    for beat in approved_beats:
        n = len(scenes) + 1
        tmpl = _match_deviation_template(beat)
        tmpl["scene_number"] = n
        scenes.append(tmpl)

    # Final scene: The Couch Payoff
    scenes.append({
        "scene_number": len(scenes) + 1,
        "scene_name": "Payoff — The Couch",
        "duration_target": "4-5 seconds (hold longer than the deviation scenes)",
        "visual_description": (
            "Evening. Lena on the couch in the warm apartment. "
            "Turtle visible nearby. Dog at her feet. Gaming setup glowing softly in the background. "
            "Plants present. Nothing from the plan was completed. Everything else happened."
        ),
        "character_action": (
            "Lena looks at camera with complete peace. Not embarrassment — peace. "
            "She is at one with not having done the thing. Expression: amused self-awareness."
        ),
        "camera_direction": (
            "This shot is calmer and slightly longer than all preceding scenes. "
            "Let it breathe. The stillness is the contrast to the accelerating cuts. "
            "Off-center. Warm lamp light. Plants and turtle visible in frame."
        ),
        "overlay_text": payoff_text,
        "purpose_of_scene": (
            "Emotional resolution. The chaos is over. Lena is fine. "
            "The viewer is validated. The overlay text lands the punchline."
        )
    })

    return scenes


def build_master_video_prompt(card: dict, review: dict) -> dict:
    refinements = review.get("refinements", {})
    return {
        "overall_direction": (
            "Short-form comedy mini-story. Lena announces an ambitious plan. "
            "Four consecutive disruptions derail it completely. "
            "She ends the day on the couch, at peace, having done nothing on the list "
            "and everything else. Tone: chaotic-but-chill, self-aware, warm."
        ),
        "character_world": LENA_CHARACTER_ANCHOR,
        "style": (
            "Warm apartment lighting throughout. Plants, dog, turtle, and gaming setup "
            "are supporting characters — they must appear but not clutter the frame. "
            "Lived-in and specific. Not catalog-clean. Natural skin texture and "
            "realistic lighting. Soft glam is present but not the focus of this format."
        ),
        "pacing": (
            "Opening scene is stable and calm. Each deviation scene cuts faster than the last. "
            "The four disruptions accelerate. The final couch payoff is longer and slower by contrast. "
            "No dead space. Every clip earns its screen time."
        ),
        "emotional_arc": (
            "Confidence → first disruption (amused) → second disruption (resigned) → "
            "third disruption (fully off-track) → fourth disruption (point of no return) → "
            "peace. The viewer should laugh and feel seen."
        )
    }


def build_flagship_cover_image_prompt() -> str:
    return (
        "Lena on the couch in her warm, plant-filled apartment. Evening. "
        "Slightly exhausted but completely at peace — mild defeat, total acceptance. "
        "Turtle visible nearby on the floor. Dog curled at her feet. "
        "Gaming setup glowing softly in the background. Several plants in frame. "
        "Expression: amused self-awareness. Nothing got done. She is fine with this. "
        "Warm lamp light, not overhead. Off-center composition. "
        "Subject dominant. Background lived-in and specific, not cluttered. "
        "Natural skin texture. Soft glam present but understated. "
        "Mood: warm, authentic, slightly chaotic. Not catalog-clean."
    )


def build_flagship_package(card: dict, review: dict, index: int, run_date: str) -> dict:
    refinements   = review.get("refinements", {})
    hook_final    = refinements.get("hook_text_corrected") or card.get("hook_text", "")
    caption_final = card.get("caption_draft", "")
    package_id    = f"pkg_{str(index).zfill(3)}_{run_date.replace('-', '')}"

    return {
        "package_id":            package_id,
        "idea_id":               card["idea_id"],
        "title":                 card["title"],
        "format_id":             card["format_id"],
        "format_name":           card["format_name"],
        "format_classification": "flagship",
        "source_review_status":  review.get("review_status", "unknown"),
        "hook_text_final":       hook_final,
        "caption_final":         caption_final,
        "master_video_prompt":   build_master_video_prompt(card, review),
        "scene_prompts":         build_scene_prompts_flagship(card, review),
        "cover_image_prompt":    build_flagship_cover_image_prompt(),
        "audio_direction":       build_audio_direction(card),
        "overlay_text_sequence": build_overlay_sequence(card, review),
        "edit_notes":            [
            refinements.get("edit_guidance", "Keep the edit tight. Four deviations maximum."),
            "Cuts accelerate through deviations. Final couch shot holds longer by contrast.",
            "Every scene is one visual beat. No scene repeats information from the previous one.",
            "Lena's reaction in each deviation should be genuine and slightly different — amused, resigned, committed, surrendered.",
            "Plants, turtle, dog, and gaming setup support the joke. They must be visible but must not clutter the frame."
        ],
        "lena_world_anchors":    card.get("lena_world_anchors", []),
        "quality_guardrails":    QUALITY_GUARDRAILS,
        "negative_prompt_notes": NEGATIVE_PROMPT_NOTES,
        "approval_status":       "cleared_for_prompt_package"
    }

# ---------------------------------------------------------------------------
# Standard builder (staple / occasional)
# ---------------------------------------------------------------------------

def build_video_prompt(card: dict, review: dict) -> str:
    refinements = review.get("refinements", {})
    corrected_notes = refinements.get("production_notes_corrected")
    production_direction = " ".join(corrected_notes) if corrected_notes else card.get("video_prompt_notes", "")

    lines = [
        f"CHARACTER: {LENA_CHARACTER_ANCHOR}",
        f"OPENING SHOT: {card.get('first_frame', '')}",
        f"SEQUENCE: {' / '.join(card.get('story_sequence', []))}",
        f"VISUAL STYLE: {card.get('visual_prompt_notes', '')}",
        f"PRODUCTION DIRECTION: {production_direction}",
        f"AUDIO REFERENCE: {card.get('suggested_audio_style', '')}",
    ]
    edit_guidance = refinements.get("edit_guidance", "")
    if edit_guidance:
        lines.append(f"EDIT GUIDANCE: {edit_guidance}")
    return "\n".join(lines)


def build_image_prompt(card: dict, review: dict) -> str:
    classification = review.get("format_classification", "staple")
    if classification == "occasional":
        cover_moment = (
            "Turtle in sharp foreground focus, low angle. Lena slightly soft-focus in background, "
            "ring light glowing, looking directly at camera with amused defeat. "
            "Intentionally off-center composition. The turtle is the main character of this frame."
        )
    else:
        cover_moment = (
            "Lena in a mirror shot — soft glam fully done, bag in hand, plant wall visible behind her. "
            "Phone in hand showing the time. Expression: confident, running late, somehow ready. "
            "Morning light. This is the made-it energy frame."
        )
    lines = [
        f"CHARACTER: {LENA_CHARACTER_ANCHOR}",
        f"COVER SCENE: {cover_moment}",
        f"REFERENCE FIRST FRAME: {card.get('first_frame', '')}",
        f"VISUAL STYLE: {card.get('visual_prompt_notes', '')}",
        "MOOD: Warm, authentic, slightly chaotic. Not catalog-clean.",
        "COMPOSITION: Off-center. Subject dominant. Background supports, does not compete.",
    ]
    return "\n".join(lines)


def build_standard_edit_notes(card: dict, review: dict) -> list:
    refinements = review.get("refinements", {})
    notes = []
    corrected = refinements.get("production_notes_corrected")
    if corrected:
        notes.extend(corrected)
    else:
        video_notes = card.get("video_prompt_notes", "")
        if video_notes:
            notes.append(video_notes)
    if not notes:
        notes.append("Follow story sequence beat-by-beat. No dead space. Every clip earns its screen time.")
    return notes


def build_standard_package(card: dict, review: dict, index: int, run_date: str) -> dict:
    refinements   = review.get("refinements", {})
    hook_final    = refinements.get("hook_text_corrected") or card.get("hook_text", "")
    caption_final = card.get("caption_draft", "")
    package_id    = f"pkg_{str(index).zfill(3)}_{run_date.replace('-', '')}"

    return {
        "package_id":            package_id,
        "idea_id":               card["idea_id"],
        "title":                 card["title"],
        "format_id":             card["format_id"],
        "format_name":           card["format_name"],
        "format_classification": review.get("format_classification", "unclassified"),
        "source_review_status":  review.get("review_status", "unknown"),
        "hook_text_final":       hook_final,
        "caption_final":         caption_final,
        "video_prompt":          build_video_prompt(card, review),
        "image_prompt":          build_image_prompt(card, review),
        "audio_direction":       build_audio_direction(card),
        "overlay_text_sequence": build_overlay_sequence(card, review),
        "edit_notes":            build_standard_edit_notes(card, review),
        "lena_world_anchors":    card.get("lena_world_anchors", []),
        "quality_guardrails":    QUALITY_GUARDRAILS,
        "negative_prompt_notes": NEGATIVE_PROMPT_NOTES,
        "approval_status":       "cleared_for_prompt_package"
    }

# ---------------------------------------------------------------------------
# Package dispatcher
# ---------------------------------------------------------------------------

def build_package(card: dict, review: dict, index: int, run_date: str) -> dict:
    if review.get("format_classification") == "flagship":
        return build_flagship_package(card, review, index, run_date)
    return build_standard_package(card, review, index, run_date)

# ---------------------------------------------------------------------------
# Save + validate
# ---------------------------------------------------------------------------

def save_output(packages: list, run_date: str) -> str:
    output_dir = os.path.join(PACKAGES_BASE, run_date)
    os.makedirs(output_dir, exist_ok=True)
    filename   = f"lena_prompt_packages_{run_date}_dry_run.json"
    filepath   = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "generated_date":   run_date,
            "generator":        "lena_generate_prompt_packages_v1",
            "mode":             "dry_run",
            "total_packages":   len(packages),
            "packages":         packages
        }, f, indent=2, ensure_ascii=False)

    return filepath


def validate_output(filepath: str) -> tuple[bool, list]:
    common = [
        "package_id", "idea_id", "title", "format_id", "format_name",
        "format_classification", "source_review_status", "hook_text_final",
        "caption_final", "audio_direction", "overlay_text_sequence",
        "edit_notes", "lena_world_anchors", "quality_guardrails",
        "negative_prompt_notes", "approval_status"
    ]
    flagship_only  = ["master_video_prompt", "scene_prompts", "cover_image_prompt"]
    standard_only  = ["video_prompt", "image_prompt"]

    errors = []
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    for pkg in data.get("packages", []):
        pid = pkg.get("package_id", "?")
        missing = [k for k in common if k not in pkg]
        if pkg.get("format_classification") == "flagship":
            missing += [k for k in flagship_only if k not in pkg]
            # Validate scene_prompts structure
            scenes = pkg.get("scene_prompts", [])
            if not isinstance(scenes, list) or len(scenes) == 0:
                missing.append("scene_prompts[non-empty list]")
            else:
                scene_fields = ["scene_number", "scene_name", "duration_target",
                                "visual_description", "character_action",
                                "camera_direction", "overlay_text", "purpose_of_scene"]
                for s in scenes:
                    sf_missing = [f for f in scene_fields if f not in s]
                    if sf_missing:
                        missing.append(f"scene {s.get('scene_number','?')} missing: {sf_missing}")
        else:
            missing += [k for k in standard_only if k not in pkg]
        if missing:
            errors.append(f"{pid}: {missing}")

    return (len(errors) == 0), errors

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(packages: list, output_path: str, valid: bool, errors: list):
    print()
    print("=" * 64)
    print("  LENA PROMPT PACKAGE GENERATOR v1 — DRY RUN COMPLETE")
    print("=" * 64)
    print(f"  Output     : {output_path}")
    print(f"  Validation : {'VALID' if valid else 'INVALID — see errors below'}")
    print(f"  Packages   : {len(packages)}")
    print()
    print("  PACKAGES GENERATED")
    print("  " + "-" * 60)
    for pkg in packages:
        clf = pkg["format_classification"].upper()
        print(f"  [{clf:<10}]  {pkg['title']}")
        print(f"               id: {pkg['package_id']}  |  review: {pkg['source_review_status']}")
        overlays = pkg.get("overlay_text_sequence", [])
        if overlays:
            print(f"               overlays: {len(overlays)} text cards")
        anchors = pkg.get("lena_world_anchors", [])
        print(f"               anchors: {', '.join(anchors)}")
        print()
    if errors:
        print("  VALIDATION ERRORS")
        for e in errors:
            print(f"    {e}")
        print()
    print("  NO workorders created.  NO API calls made.")
    print("  NO publishing triggered.  NO Instagram / Facebook / R2 touched.")
    print("=" * 64)
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Lena Prompt Package Generator v1 — dry run")
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y-%m-%d"),
        help="Date of the idea cards to process (YYYY-MM-DD). Defaults to today."
    )
    args     = parser.parse_args()
    run_date = args.date

    cards_dir   = os.path.join(IDEA_CARDS_BASE, run_date)
    cards_path  = os.path.join(cards_dir, f"lena_idea_cards_{run_date}_dry_run.json")
    review_path = os.path.join(cards_dir, f"lena_idea_cards_{run_date}_creative_review.json")

    print(f"[lena_generate_prompt_packages_v1] Date: {run_date}")
    print(f"[lena_generate_prompt_packages_v1] Loading idea cards  : {cards_path}")
    cards_data = load_json(cards_path)

    print(f"[lena_generate_prompt_packages_v1] Loading review file : {review_path}")
    review_data = load_json(review_path)

    card_index      = {c["idea_id"]: c for c in cards_data["cards"]}
    cleared_reviews = [r for r in review_data["reviews"] if r.get("cleared_for_prompt_package")]

    print(f"[lena_generate_prompt_packages_v1] Cards cleared for prompting: {len(cleared_reviews)}")

    packages = []
    for idx, review in enumerate(cleared_reviews, start=1):
        idea_id = review["idea_id"]
        card    = card_index.get(idea_id)
        if not card:
            print(f"  [WARN] idea_id {idea_id} not found in cards file — skipping")
            continue
        pkg = build_package(card, review, idx, run_date)
        packages.append(pkg)
        print(f"  Built: {pkg['package_id']} — {pkg['title']}")

    print(f"[lena_generate_prompt_packages_v1] Saving output...")
    output_path = save_output(packages, run_date)

    print(f"[lena_generate_prompt_packages_v1] Validating output...")
    valid, errors = validate_output(output_path)

    print_summary(packages, output_path, valid, errors)


if __name__ == "__main__":
    main()
