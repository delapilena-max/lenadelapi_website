"""
Lena Dry-Run Idea Card Generator v1

Reads the Lena strategy foundation files and generates a batch of scored
content idea cards for human review. Writes nothing to the publishing pipeline.

Safe: no workorders, no Instagram, no Facebook, no R2, no publisher calls.
"""

import json
import os
import sys
from datetime import date

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STRATEGY_DIR = os.path.join(ROOT, "pipeline", "strategy", "lena")

FORMAT_LIBRARY_PATH  = os.path.join(STRATEGY_DIR, "viral_format_library.json")
SCORE_SCHEMA_PATH    = os.path.join(STRATEGY_DIR, "lena_viral_score_schema.json")
PILLARS_PATH         = os.path.join(STRATEGY_DIR, "content_pillars.json")
PLAYBOOK_PATH        = os.path.join(STRATEGY_DIR, "organic_growth_playbook.md")

OUTPUT_BASE = os.path.join(STRATEGY_DIR, "idea_cards")

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        print(f"[ERROR] Missing foundation file: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_playbook(path: str) -> str:
    if not os.path.isfile(path):
        print(f"[ERROR] Missing playbook: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------------------------
# Idea card definitions
# One card per format. Angle chosen from repeatable_angles[0] unless noted.
# ---------------------------------------------------------------------------

IDEA_CARDS_RAW = [
    {
        "format_id": "grwm_before_class",
        "content_pillar": "soft_glam",
        "title": "GRWM: 48 Minutes to Get Ready and Look Like This",
        "first_frame": "Phone screen close-up: 7:12am alarm. Text overlay slides in: 'you have 48 minutes. let's go'",
        "hook_text": "POV: you have 48 minutes to get ready and look this good",
        "open_loop": "Can she get fully ready AND make it on time? The clock is already running.",
        "problem_or_tension": "An hour to be somewhere and Lena is starting from zero — bed hair, no makeup, not dressed.",
        "story_sequence": [
            "Alarm close-up, Lena's shocked face",
            "Messy starting state — bed hair, oversized tee, plant wall in background",
            "Speed-run skincare: cleanser, SPF, moisturizer in 90 seconds",
            "Soft glam fast-cut: tinted moisturizer, brow pencil, lip liner, mascara",
            "Outfit pick — one confident grab from the closet",
            "Bag grab, shoes on, out the door",
            "Out the door — text card: '3 minutes to spare'"
        ],
        "payoff": "She makes it. Soft glam intact. 48 minutes, zero compromises.",
        "caption_draft": "pov: 48 minutes, a glam moment, and not one alarm went off on purpose 🫠 #grwm #getreadywithme #softglam #luxurybaddie",
        "visual_prompt_notes": "Morning light, warm apartment. Plant wall visible behind mirror. Clean but lived-in. Soft focus on makeup products. Fast cuts — no single clip longer than 2 seconds.",
        "video_prompt_notes": "Handheld energy. Mirror POV for makeup. Wide shot for outfit reveal. End on door-close or confident exit shot.",
        "suggested_audio_style": "Trending upbeat morning audio or fast-paced lo-fi. Must sync cuts to beat drops.",
        "share_reason": "'this is literally me every single morning' — the time pressure and chaotic calm combination is universally relatable",
        "save_reason": "Viewers save the skincare speed-run sequence as a reference. The 48-minute structure is aspirational and practical.",
        "comment_trigger": "Comments will be people confessing their own morning chaos timelines and asking what products she used.",
        "lena_world_anchors": ["soft_glam", "luxury_lifestyle_fashion", "relatable_chaos", "fit_check"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 9,
            "first_frame_curiosity": 9,
            "open_loop": 9,
            "lena_world_specificity": 9,
            "identity_resonance": 8,
            "shareability": 9,
            "caption_clarity": 9,
            "edit_density": 9,
            "emotional_reaction": 8,
            "repeatability": 9
        },
        "rerun_potential": "high",
        "notes": "Strongest format in the library for first-frame urgency. Time-pressure angle is universally relatable and repeatably available across any outing. Soft glam speed-run is the save trigger."
    },
    {
        "format_id": "dance_break_before_studying",
        "content_pillar": "dance_lifestyle",
        "title": "One Dance Break Before the Deadline (It Was Not One)",
        "first_frame": "Lena at desk, head resting on open planner, laptop open. Text overlay: 'me, about to be so productive'",
        "hook_text": "Me convincing myself one dance break will fix everything. It fixed everything.",
        "open_loop": "The song drops — what happens to the studying?",
        "problem_or_tension": "To-do list open. Lena cannot start. One song becomes the solution and the problem.",
        "story_sequence": [
            "Desk shot: stressed face, open planner, cursor blinking on blank doc",
            "Song drops — instant posture change",
            "Dance break in apartment living room — plants visible, gaming setup in background",
            "Energy builds through the second verse — full apartment dance break",
            "Song ends. Back at desk.",
            "Text card: 'the to-do list still isn't done but I feel amazing'"
        ],
        "payoff": "Nothing got done. Lena is at peace with this. Viewer laughs and relates.",
        "caption_draft": "the dance break was mandatory for my energy levels 💃✨ (the list is still untouched) #dancebreak #productivitycheck #reels",
        "visual_prompt_notes": "Transition from tight desk shot to wide living room. Plants and gaming setup both visible. Natural light or warm lamp light.",
        "video_prompt_notes": "Sync the beat drop to the posture-change cut. The shift from slumped-at-desk to standing-dancing should be one hard cut, no transition. End on static desk shot for comedic contrast.",
        "suggested_audio_style": "Current trending TikTok/Reels sound. Must have a clear drop moment to sync the cut.",
        "share_reason": "'sending this to my group chat' — the failed productivity arc is universally relatable across all audiences",
        "save_reason": "Lower save potential — this is a share and comment format, not a save format.",
        "comment_trigger": "'this is literally me rn', 'what song is this', 'I needed this energy' — three reliable comment categories in one video",
        "lena_world_anchors": ["dance_lifestyle", "luxury_lifestyle_fashion", "relatable_chaos", "confident_personality"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 9,
            "first_frame_curiosity": 7,
            "open_loop": 7,
            "lena_world_specificity": 8,
            "identity_resonance": 8,
            "shareability": 9,
            "caption_clarity": 9,
            "edit_density": 8,
            "emotional_reaction": 9,
            "repeatability": 9
        },
        "rerun_potential": "high",
        "notes": "Beat-drop sync is the production priority. The desk-to-dance energy shift in one hard cut is the differentiating moment. Caption punchline ('still untouched') is the share trigger."
    },
    {
        "format_id": "apartment_plant_chaos_reset",
        "content_pillar": "plant_apartment",
        "title": "Sunday Reset: The Apartment Was a Crime Scene",
        "first_frame": "Wide shot: full apartment chaos. Clothes on every surface, dog toys everywhere, three half-drunk water bottles. Text overlay: 'the situation'",
        "hook_text": "resetting the apartment after a week that simply won",
        "open_loop": "Can this level of chaos actually become the cozy aesthetic apartment she posts about?",
        "problem_or_tension": "The apartment reached critical chaos levels. Lena cannot function. The plants are judging her.",
        "story_sequence": [
            "Wide chaos shot — no shame, full inventory",
            "Cleaning montage — fast cuts, satisfying tidying",
            "Plant check: watering, pruning, rotating toward window",
            "Turtle spotted near the plant shelf — chaos agent confirmed",
            "Final reset wide shot: clean surfaces, candle lit, plants gleaming",
            "Lena sitting in the reset space with coffee — text card: 'we are so back'"
        ],
        "payoff": "The apartment is transformed. The plants thrived. The turtle is fine. The chaos is gone until Tuesday.",
        "caption_draft": "the reset was needed. the plants agreed. the turtle did not help. 🌿✨ #sundayreset #planttok #apartmentlife",
        "visual_prompt_notes": "Start wide and messy. Cleaning montage should use consistent camera angle for before/after payoff. Plant watering sequence can be slower and more cinematic — this is the aesthetic moment. End on the same wide angle as the opening for the contrast payoff.",
        "video_prompt_notes": "Before/after structure requires matching shot angles. Turtle cameo should be natural — don't move it. Plant close-ups are high-save content, linger slightly longer here than elsewhere.",
        "suggested_audio_style": "Calming lo-fi or trending 'reset' audio. Slower tempo than the dance or GRWM formats.",
        "share_reason": "'tag someone whose apartment looks like the before' — the chaos before-shot is the share trigger",
        "save_reason": "High save potential — the plant care sequence and reset routine are aspirational. Viewers save cozy reset content to revisit.",
        "comment_trigger": "'the plants judging her' gets comments, turtle cameo gets comments, 'we are so back' caption energy gets response comments",
        "lena_world_anchors": ["plant_apartment", "wellness_reset", "relatable_chaos", "luxury_lifestyle_fashion"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 8,
            "first_frame_curiosity": 8,
            "open_loop": 7,
            "lena_world_specificity": 10,
            "identity_resonance": 9,
            "shareability": 8,
            "caption_clarity": 9,
            "edit_density": 8,
            "emotional_reaction": 8,
            "repeatability": 9
        },
        "rerun_potential": "high",
        "notes": "Lena-world specificity is the ceiling here — plants + turtle + big apartment is uniquely hers. Turtle cameo during the reset is the differentiation moment no other creator can replicate."
    },
    {
        "format_id": "pov_luxury_fit_check_no_plans",
        "content_pillar": "luxury_lifestyle",
        "title": "POV: I Look Like I Have Plans. I Do Not.",
        "first_frame": "Full-body mirror or doorway shot — polished luxury outfit, gold jewelry, glossy lip. Text card fades in: 'POV: got fully dressed like this and have absolutely nowhere to go'",
        "hook_text": "POV: dressed like I have plans. I do not.",
        "open_loop": "Where is she going in that? She is going nowhere. The outfit is the event.",
        "problem_or_tension": "Lena put together a full luxury fit — expensive-looking, intentional, head to heel — with no destination on the schedule. The mirror approved it. That is enough.",
        "story_sequence": [
            "Full-body mirror or doorway reveal — classy luxury look, confident direct expression",
            "Slow outfit detail pan: shoe, bag, earring, glossy lip close-up",
            "Lena checks phone — no plans, expression unbothered",
            "Walk to apartment entryway — hand on hip, ready-to-leave energy",
            "She turns back inside — text card: 'the fit deserved to exist. it existed.'"
        ],
        "payoff": "The look happened. The apartment witnessed it. No destination required. The viewer is inspired and mildly jealous.",
        "caption_draft": "dressed like I have plans 💋 the plans are staying home looking like this #ootd #fitcheck #looksexpensive #luxurybaddie",
        "visual_prompt_notes": "Full-body mirror shot or doorway framing — apartment entryway or bedroom, clean and uncluttered. Outfit must read expensive and intentional from head to heel: structured piece, sleek shoe or heel, one statement accessory, glossy lip. No visible logos or readable text. Warm soft light.",
        "video_prompt_notes": "Play it straight — the fit is real, the humor is the non-destination revealed gradually. Detail pan clips slow and intentional. End on apartment interior to land the no-plans payoff. No winking at camera.",
        "suggested_audio_style": "Confident trending audio — something that matches a real going-out OOTD energy to maximize the contrast with the no-plans reveal.",
        "share_reason": "'sending this to my fashion group chat' — fully dressed with no plans is aspirational and universally relatable; 'where are you going?' comment bait drives engagement",
        "save_reason": "High save potential — luxury outfit details and expensive-looking styling are aspirational. Viewers save mirror fit check content for outfit reference and style inspo.",
        "comment_trigger": "'where are you going dressed like that?' is the primary comment. Outfit detail questions follow. 'Same energy' reactions from viewers who also get dressed for nowhere.",
        "lena_world_anchors": ["luxury_lifestyle_fashion", "fit_check", "affordable_luxury", "confident_personality"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 9,
            "first_frame_curiosity": 9,
            "open_loop": 8,
            "lena_world_specificity": 9,
            "identity_resonance": 9,
            "shareability": 9,
            "caption_clarity": 9,
            "edit_density": 7,
            "emotional_reaction": 8,
            "repeatability": 10
        },
        "rerun_potential": "high",
        "notes": "Repeatable luxury fit-check format with built-in comment bait and share hook. Dressed-for-no-reason is a universal experience that lands across all audiences. Outfit detail pan clips are saveable. Works with any new luxury look — high repeatability ceiling."
    },
    {
        "format_id": "turtle_dog_interruption",
        "content_pillar": "relatable_chaos",
        "title": "Was Recording. Turtle Had Other Plans.",
        "first_frame": "Lena mid-recording setup — ring light on, outfit ready, speaking to camera. Turtle walks into frame from lower left.",
        "hook_text": "she did not care that I was recording",
        "open_loop": "What does the turtle do next? The viewer cannot scroll — they have to find out.",
        "problem_or_tension": "Lena is mid-content-creation. The turtle has entered the scene with zero context and zero respect for the schedule.",
        "story_sequence": [
            "Lena mid-recording, professional energy",
            "Turtle enters frame — Lena's reaction is genuinely caught off guard",
            "Lena tries to continue recording — turtle continues existing in frame",
            "Dog appears, investigates the turtle",
            "Lena gives up and addresses the audience: 'this is fine'",
            "Final frame: turtle in foreground, Lena in background looking at camera"
        ],
        "payoff": "Content did not get made. The pets won. The clip that resulted is better than the original content would have been.",
        "caption_draft": "she saw the ring light and chose violence 🐢 #turtlelife #petmom #contentcreatorproblems",
        "visual_prompt_notes": "Ring light environment — realistic content creation setup visible. The turtle entry shot is the key frame. Do not stage the turtle movement — let it happen and film the reaction. Dog investigation is a bonus second beat.",
        "video_prompt_notes": "Do not script this. If a turtle-interruption opportunity occurs: film everything, react authentically, edit for the best reaction moments. The authentic surprise is the asset.",
        "suggested_audio_style": "Trending comedic or chaotic audio. Sound effect at the moment of turtle entry works well.",
        "share_reason": "'i am sending this to everyone i know' — turtle interruption is novel enough that viewers feel like they discovered something rare",
        "save_reason": "Low save potential — this is a pure share and comment format.",
        "comment_trigger": "Turtle comments are a separate community. 'What kind of turtle?', turtle name requests, and turtle owner solidarity comments are all reliable.",
        "lena_world_anchors": ["relatable_chaos", "confident_personality"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 8,
            "first_frame_curiosity": 9,
            "open_loop": 9,
            "lena_world_specificity": 10,
            "identity_resonance": 8,
            "shareability": 10,
            "caption_clarity": 9,
            "edit_density": 7,
            "emotional_reaction": 10,
            "repeatability": 7
        },
        "rerun_potential": "medium",
        "notes": "Highest shareability and emotional reaction scores in the batch. Repeatability is lower because turtle interruptions cannot be reliably manufactured — film when they happen. The turtle is Lena's strongest differentiator."
    },
    {
        "format_id": "gaming_desk_night_routine",
        "content_pillar": "gaming_desk",
        "title": "Night Routine When the 'Decompress' Session Was 3 Hours",
        "first_frame": "Gaming setup shot — monitors glowing, dim room, snack visible. Text overlay: '11:47pm. decompressing.'",
        "hook_text": "my night routine as someone who considers gaming a form of self-care",
        "open_loop": "What does her actual wind-down look like after a long gaming session? Is there a routine at all?",
        "problem_or_tension": "It's nearly midnight. Lena has been 'decompressing' since 8pm. The night routine needs to happen.",
        "story_sequence": [
            "Gaming setup ambient shot — the glow, the snacks, the energy",
            "Lena finally closes the laptop or sets down the controller",
            "Skincare while standing at the monitor (multitasking era)",
            "Plants checked: quick watering of the desk plant",
            "Turtle confirmed present and safe",
            "Lights dim — cozy transition to bed-adjacent space",
            "Final shot: soft lamp, plant silhouette, Lena looking peaceful. Text: 'tomorrow we are so productive'"
        ],
        "payoff": "The night routine happened. It took 20 minutes. The gaming session took 3 hours. Balance is subjective.",
        "caption_draft": "decompressing. have been decompressing for 3 hours. the routine still happened though 🎮✨ #nightroutine #gamergirlvibes #cozynight",
        "visual_prompt_notes": "RGB desk glow as the opening anchor. Warm lamp transition for the wind-down. Plant silhouette in the final shot is the aesthetic payoff. Dark and cozy throughout — this is not a bright morning routine.",
        "video_prompt_notes": "The contrast between gaming-glow shots and warm-lamp shots carries the visual arc. Skincare while standing at the desk is a funny specific detail — make sure it's in frame. Turtle check can be a 2-second clip.",
        "suggested_audio_style": "Lo-fi night energy — slower BPM than daytime formats. Trending cozy/night audio.",
        "share_reason": "'this is my every night' — the 3-hour 'decompress' is a universal gaming experience that non-gamers also recognize as procrastination",
        "save_reason": "High save potential — night routines are one of the highest-save content categories. Viewers return to cozy aesthetic content.",
        "comment_trigger": "'decompressing' in quotes gets comments from gamers who recognize the bit. 'What game?' is reliable. The plant/turtle check sequence gets wholesome comments.",
        "lena_world_anchors": ["gaming_desk", "wellness_reset", "plant_apartment", "luxury_lifestyle_fashion"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 9,
            "first_frame_curiosity": 8,
            "open_loop": 7,
            "lena_world_specificity": 9,
            "identity_resonance": 9,
            "shareability": 8,
            "caption_clarity": 9,
            "edit_density": 8,
            "emotional_reaction": 8,
            "repeatability": 9
        },
        "rerun_potential": "high",
        "notes": "Second-highest save potential in the batch after the plant reset. The 'decompressing' caption is reusable across multiple night routine angles. Gaming identity content has a loyal comment community."
    },
    {
        "format_id": "outfit_check_running_late",
        "content_pillar": "soft_glam",
        "title": "Outfit Check: Built This for a Day I Didn't Leave the Apartment",
        "first_frame": "Mirror shot — Lena fully dressed and polished. Phone in hand shows the time: 2:14pm. No plans.",
        "hook_text": "outfit check but the only place I'm going is the plant corner",
        "open_loop": "Why is she dressed like this for nowhere? The viewer needs to know.",
        "problem_or_tension": "Lena got fully dressed and ready with nowhere to go. The outfit is the content now.",
        "story_sequence": [
            "Mirror shot reveal — dressed, glam, phone showing 2pm",
            "Slow outfit spin",
            "Close-up on a specific detail: shoes, bag, earrings",
            "Lena walks to the plant corner — this is the destination",
            "Plant watering in the fit",
            "Sits on the couch in the apartment — text card: 'served no one. loved it.'"
        ],
        "payoff": "The outfit happened. It served the apartment. The plants appreciated it. The commitment is the joke.",
        "caption_draft": "got dressed for the apartment. the apartment deserved it 💅 #ootd #outfitcheck #fitcheck",
        "visual_prompt_notes": "Mirror shot framing must be clean — apartment visible in background but not cluttered. Plant corner shot is the payoff visual. Natural light for the outfit detail close-ups. Soft glam is polished even in the casual context.",
        "video_prompt_notes": "The joke lives in the contrast between the outfit quality and the non-destination. Play it straight — no winking. The text card payoff lands harder when the rest of the clip is sincere.",
        "suggested_audio_style": "Confident trending audio — something that matches the energy of a real going-out OOTD, which makes the apartment destination funnier.",
        "share_reason": "'me every single weekend' — getting dressed with nowhere to go is a widely shared experience, especially among WFH and student demographics",
        "save_reason": "Medium save potential — the outfit itself is saveable for reference. Style details are a save trigger.",
        "comment_trigger": "'what are you wearing?' and 'this is me' are the two reliable comment types. The apartment-as-destination bit will get 'the plants are lucky' comments.",
        "lena_world_anchors": ["soft_glam", "plant_apartment", "relatable_chaos"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 9,
            "first_frame_curiosity": 8,
            "open_loop": 8,
            "lena_world_specificity": 8,
            "identity_resonance": 8,
            "shareability": 9,
            "caption_clarity": 9,
            "edit_density": 8,
            "emotional_reaction": 8,
            "repeatability": 9
        },
        "rerun_potential": "high",
        "notes": "The 'nowhere to go' angle is the differentiator from standard OOTD. Lena's plant apartment grounds the joke. Strong repeatable format — many outfit + absurd destination combinations available."
    },
    {
        "format_id": "supposed_to_be_productive_ministory",
        "content_pillar": "relatable_chaos",
        "title": "The Plan Was Ambitious. I Was Not.",
        "first_frame": "Lena at desk, confident look to camera. Text card: 'I had a very organized plan for today.' Beat. Cut to: turtle on the keyboard.",
        "hook_text": "I had a plan. the turtle had a different plan.",
        "open_loop": "How does a productivity plan survive a turtle, a dog, a game update, and a plant audit? (It doesn't.)",
        "problem_or_tension": "Lena had a full day planned. The apartment, its inhabitants, and her own brain had other intentions.",
        "story_sequence": [
            "Confident opener: the plan stated with specificity",
            "First deviation: turtle on keyboard — recording stopped",
            "Second deviation: dog needed emotional support, urgently",
            "Third deviation: one of the plants looked 'a little sad' — full plant audit initiated",
            "Fourth deviation: game update downloaded itself, seemed rude not to play",
            "Evening: Lena on couch, none of the plan completed, everything else done",
            "Text card payoff: 'the plan was a dream. I am a woman of the moment.'"
        ],
        "payoff": "Nothing from the list happened. Everything else happened instead. Lena is at peace. The viewer is validated.",
        "caption_draft": "the plan was ambitious. i was not. tomorrow though 😭 #productivity #relatable #lifestylevibes #planttok",
        "visual_prompt_notes": "Each deviation needs a dedicated shot: turtle on keyboard (specific), dog at her feet refusing to let her leave (specific), plant audit in progress (multiple plants visible), game menu on screen. Specificity is what makes this funny instead of generic.",
        "video_prompt_notes": "Each distraction is a beat. Hard cut between the 'plan announced' moment and the first disruption. The deviations accelerate — each one slightly faster cut than the last. The final couch shot should be calm and long by contrast.",
        "suggested_audio_style": "Comedic trending audio or a 'failing gracefully' type sound. The audio should match the chaotic-but-chill energy.",
        "share_reason": "'sending this to my accountability partner to explain my day' — this format is built to be sent as a confession or a 'same' reaction",
        "save_reason": "Low-medium save potential — this is a share and comment format primarily.",
        "comment_trigger": "'the plant audit got me', 'the turtle on the keyboard is everything', 'what was the plan?' — three independent comment hooks in one video",
        "lena_world_anchors": ["relatable_chaos", "luxury_lifestyle_fashion", "plant_apartment", "gaming_desk", "confident_personality"],
        "platform_fit": {"instagram_reels": "primary", "tiktok": "primary"},
        "scores": {
            "format_familiarity": 8,
            "first_frame_curiosity": 9,
            "open_loop": 9,
            "lena_world_specificity": 10,
            "identity_resonance": 9,
            "shareability": 10,
            "caption_clarity": 9,
            "edit_density": 9,
            "emotional_reaction": 10,
            "repeatability": 9
        },
        "rerun_potential": "high",
        "notes": "Highest Lena-world specificity, shareability, and emotional reaction scores in the batch. The multi-distraction structure pulls from every pillar simultaneously. Strongest overall card for comment volume."
    }
]

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_total(scores: dict) -> int:
    return sum(scores.values())


def approval_recommendation(total: int, threshold: int) -> str:
    if total >= threshold:
        return "approve_for_prompting"
    elif total >= threshold - 10:
        return "revise"
    return "reject"

# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------

def build_cards(raw_cards: list, format_library: dict, pillars: dict, schema: dict) -> list:
    threshold = schema["approval_threshold"]
    format_index = {f["format_id"]: f for f in format_library["formats"]}
    pillar_index = {p["id"]: p for p in pillars["pillars"]}

    cards = []
    for idx, raw in enumerate(raw_cards, start=1):
        fmt = format_index.get(raw["format_id"], {})
        pillar = pillar_index.get(raw["content_pillar"], {})

        scores = raw["scores"]
        total = compute_total(scores)
        recommendation = approval_recommendation(total, threshold)

        idea_id = f"lena_{str(idx).zfill(3)}_{date.today().strftime('%Y%m%d')}"

        card = {
            "idea_id": idea_id,
            "format_id": raw["format_id"],
            "format_name": fmt.get("format_name", raw["format_id"]),
            "content_pillar": raw["content_pillar"],
            "pillar_name": pillar.get("name", raw["content_pillar"]),
            "title": raw["title"],
            "first_frame": raw["first_frame"],
            "hook_text": raw["hook_text"],
            "open_loop": raw["open_loop"],
            "problem_or_tension": raw["problem_or_tension"],
            "story_sequence": raw["story_sequence"],
            "payoff": raw["payoff"],
            "caption_draft": raw["caption_draft"],
            "visual_prompt_notes": raw["visual_prompt_notes"],
            "video_prompt_notes": raw["video_prompt_notes"],
            "suggested_audio_style": raw["suggested_audio_style"],
            "share_reason": raw["share_reason"],
            "save_reason": raw["save_reason"],
            "comment_trigger": raw["comment_trigger"],
            "lena_world_anchors": raw["lena_world_anchors"],
            "platform_fit": raw["platform_fit"],
            "scores": scores,
            "total_score": total,
            "approval_threshold": threshold,
            "approval_recommendation": recommendation,
            "rerun_potential": raw["rerun_potential"],
            "notes": raw["notes"]
        }
        cards.append(card)

    return cards

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_output(cards: list) -> str:
    today = date.today().strftime("%Y-%m-%d")
    output_dir = os.path.join(OUTPUT_BASE, today)
    os.makedirs(output_dir, exist_ok=True)

    filename = f"lena_idea_cards_{today}_dry_run.json"
    filepath = os.path.join(output_dir, filename)

    output = {
        "generated_date": today,
        "generator": "lena_generate_idea_cards_v1",
        "mode": "dry_run",
        "total_cards": len(cards),
        "approval_threshold": cards[0]["approval_threshold"] if cards else 70,
        "cards": cards
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return filepath

# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(cards: list, output_path: str):
    approved = [c for c in cards if c["approval_recommendation"] == "approve_for_prompting"]
    revise   = [c for c in cards if c["approval_recommendation"] == "revise"]
    rejected = [c for c in cards if c["approval_recommendation"] == "reject"]

    sorted_cards = sorted(cards, key=lambda c: c["total_score"], reverse=True)

    print()
    print("=" * 64)
    print("  LENA IDEA CARD GENERATOR v1 — DRY RUN COMPLETE")
    print("=" * 64)
    print(f"  Output: {output_path}")
    print(f"  Cards generated : {len(cards)}")
    print(f"  Approved        : {len(approved)}")
    print(f"  Revise          : {len(revise)}")
    print(f"  Rejected        : {len(rejected)}")
    print()
    print("  TOP 3 IDEAS BY SCORE")
    print("  " + "-" * 60)
    for card in sorted_cards[:3]:
        rec_label = {
            "approve_for_prompting": "APPROVE",
            "revise": "REVISE",
            "reject": "REJECT"
        }.get(card["approval_recommendation"], card["approval_recommendation"])
        print(f"  [{card['total_score']:>3}/100] [{rec_label:<7}] {card['title']}")
    print()
    print("  ALL CARDS")
    print("  " + "-" * 60)
    for card in sorted_cards:
        rec_label = {
            "approve_for_prompting": "APPROVE",
            "revise": "REVISE",
            "reject": "REJECT"
        }.get(card["approval_recommendation"], card["approval_recommendation"])
        print(f"  [{card['total_score']:>3}/100] [{rec_label:<7}] {card['title']}")
    print()
    print("  NO workorders created. NO publishing triggered.")
    print("  NO Instagram, Facebook, or R2 touched.")
    print("=" * 64)
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("[lena_generate_idea_cards_v1] Loading foundation files...")

    format_library = load_json(FORMAT_LIBRARY_PATH)
    score_schema   = load_json(SCORE_SCHEMA_PATH)
    pillars        = load_json(PILLARS_PATH)
    _playbook      = load_playbook(PLAYBOOK_PATH)  # validate it exists

    print(f"  Formats loaded  : {len(format_library['formats'])}")
    print(f"  Pillars loaded  : {len(pillars['pillars'])}")
    print(f"  Score threshold : {score_schema['approval_threshold']}")
    print(f"  Playbook        : present")

    print("[lena_generate_idea_cards_v1] Building idea cards...")
    cards = build_cards(IDEA_CARDS_RAW, format_library, pillars, score_schema)

    print("[lena_generate_idea_cards_v1] Saving output...")
    output_path = save_output(cards)

    print_summary(cards, output_path)


if __name__ == "__main__":
    main()
