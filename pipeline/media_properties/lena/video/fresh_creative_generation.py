from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ARTIFACT_FILES, SOURCE_TYPES
from .compiler import compile_video
from .contracts import (
    CHARACTER_ELEMENT_TOKEN,
    CHARACTER_ELEMENT_UUID,
    PROPERTY_ID,
    SCHEMA_VERSION,
    atomic_write_json,
    canonical_sha256,
    zero_activity_counters,
)
from .validation import validate_source_for_compilation


GENERATOR_VERSION = "lena_video_fresh_creative_author_v1"


class LenaVideoCreativeError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CreativeTemplate:
    seed_terms: tuple[str, ...]
    suffix: str
    concept: str
    hook: str
    setup: str
    payoff: str
    audience_growth_objective: str
    content_pillar: str
    desired_emotion: str
    product_identity: str
    cta_intent: str
    exact_location: str
    architecture: tuple[str, ...]
    materials: tuple[str, ...]
    practical_objects: tuple[str, ...]
    lighting_sources: tuple[str, ...]
    weather: tuple[str, ...]
    environmental_motion: tuple[str, ...]
    background_behavior: tuple[str, ...]
    social_context: str
    spatial_relationships: tuple[str, ...]
    realism_details: tuple[str, ...]
    rocket_distance_meters: int
    specificity_markers: tuple[str, ...]
    environment_cue: str
    garments: tuple[dict[str, str], ...]
    wardrobe_cue: str
    anticipation: str
    timeline: tuple[dict[str, Any], ...]
    final_settled_state: str
    camera_position: str
    framing: str
    camera_movement: str
    lens_behavior: str
    subject_scale: str
    background_scale: str
    camera_cue: str
    dialogue_mode: str
    dialogue_text: str
    voice_authority_required: bool
    timing: str
    music: str
    diegetic_sound: tuple[str, ...]
    ambience: tuple[str, ...]
    audio_cue: str
    provider_prompt_cue: str
    hard_constraints: tuple[str, ...]
    negative_constraints: tuple[str, ...]


def _timeline_segment(
    start_ms: int,
    end_ms: int,
    *,
    action: str,
    body_movement: str,
    meaningful_displacement_cm: int,
    gaze_target: str,
    expression: str,
    blink_count: int,
    breathing: str,
    weight_transfer: str,
    gesture_initiation: str,
    gesture_completion: str,
    recovery: str,
    camera_relationship: str,
    provider_prompt_cue: str,
) -> dict[str, Any]:
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "action": action,
        "body_movement": body_movement,
        "meaningful_displacement_cm": meaningful_displacement_cm,
        "gaze_target": gaze_target,
        "expression": expression,
        "blink_count": blink_count,
        "breathing": breathing,
        "weight_transfer": weight_transfer,
        "gesture_initiation": gesture_initiation,
        "gesture_completion": gesture_completion,
        "recovery": recovery,
        "camera_relationship": camera_relationship,
        "provider_prompt_cue": provider_prompt_cue,
    }


TEMPLATES: tuple[CreativeTemplate, ...] = (
    CreativeTemplate(
        seed_terms=("spacex", "launch", "rocket"),
        suffix="spacex_launch",
        concept="Lena watches a distant public rocket launch and makes the scale readable through one completed reaction.",
        hook="The small rocket is already rising behind Lena before she turns the viewer toward it.",
        setup="A companion-held vertical phone frames Lena at a lawful public coastal viewing area with the launch corridor over her shoulder.",
        payoff="Lena completes one clear gesture toward the distant climb, then settles into believable wonder instead of looping a pose.",
        audience_growth_objective="Earn rewatch through coherent spectacle scale, Lena identity stability, and a completed human action.",
        content_pillar="real_world_wonder",
        desired_emotion="Shared anticipation, delight, and physically grounded awe.",
        product_identity="Independent Lena editorial entertainment about witnessing a public launch from outside restricted property.",
        cta_intent="Invite viewers to name the last real-world moment that made them feel this level of awe.",
        exact_location=(
            "A lawful public coastal launch-viewing lawn with water, boardwalk, rail, sparse spectators, "
            "and the launch corridor several kilometers away beyond all restricted property."
        ),
        architecture=("low timber boardwalk behind Lena", "waist-high public safety rail", "small public shade pavilion behind camera"),
        materials=("weathered boardwalk planks", "galvanized rail posts", "coastal grass over sandy soil", "blue-gray water"),
        practical_objects=("folded spectator chair", "plain reusable water bottle", "small public safety sign", "two distant family vehicles"),
        lighting_sources=("low warm morning sun from camera-right", "soft open-sky fill", "bright distant plume that does not clip Lena's face"),
        weather=("clear humid coastal morning", "thin high cloud streaks", "light onshore breeze"),
        environmental_motion=("grass tips bend in breeze", "water ripples travel laterally", "hair ends move without hiding Lena's face", "distant rocket rises continuously"),
        background_behavior=("sparse spectators watch the launch", "no one crosses Lena's silhouette", "rocket remains distant and small"),
        social_context="Lena is one adult spectator in a lawful public crowd; no badge, uniform, restricted access, employment, or sponsorship is implied.",
        spatial_relationships=("Lena stands inside the public rail", "companion camera is about two and a half meters away", "launch horizon remains over her shoulder"),
        realism_details=("distant plume has atmospheric haze", "low-frequency sound feels delayed", "soft morning shadow matches the sun", "no accident or emergency is shown"),
        rocket_distance_meters=8000,
        specificity_markers=("coastal_viewing_lawn", "timber_boardwalk", "galvanized_safety_rail", "blue_gray_water", "distant_launch_haze"),
        environment_cue="Public coastal viewing lawn with water, rail, boardwalk, sparse spectators, morning haze, light breeze, and a small distant rocket rising with lengthening plume.",
        garments=(
            {
                "garment": "jean_shorts",
                "fit": "tasteful high-hip fit with full coverage and stable hems during the step",
                "material": "midweight washed cotton denim",
                "color": "medium ocean-blue wash with no logo",
                "fastened_state": "fully_fastened",
                "continuity": "entire_video",
                "movement_behavior": "denim folds naturally at the hips without riding up or changing shape",
            },
            {
                "garment": "rash_guard",
                "fit": "fitted long-sleeve athletic cut that remains opaque and secure",
                "material": "matte technical surf knit",
                "color": "deep sea-green with no brand mark",
                "fastened_state": "secured",
                "continuity": "entire_video",
                "movement_behavior": "fabric stretches naturally at shoulders and elbows without texture crawl",
            },
            {
                "garment": "low_profile_shoes",
                "fit": "close-fitting lace-up shoes suitable for firm lawn and boardwalk footing",
                "material": "matte canvas uppers with thin rubber soles",
                "color": "warm off-white with neutral laces",
                "fastened_state": "fully_fastened",
                "continuity": "entire_video",
                "movement_behavior": "both shoes stay grounded through the half-step and weight transfer",
            },
        ),
        wardrobe_cue="Medium-blue fully fastened jean shorts, opaque deep sea-green long-sleeve rash guard, and off-white low-profile shoes; no logos, accessories, wardrobe change, or reference clothing.",
        anticipation="Lena begins already oriented toward the distant launch path, shoulders loose, eyes active, and breath held for only the first beat.",
        timeline=(
            _timeline_segment(
                0,
                2000,
                action="The rocket is visible behind her; Lena releases a held breath and tracks it immediately.",
                body_movement="Her chin rises and torso leans forward three centimeters without locking her knees.",
                meaningful_displacement_cm=3,
                gaze_target="the distant ascending rocket over her shoulder",
                expression="focused_anticipation",
                blink_count=1,
                breathing="one held inhale releases into a quiet exhale",
                weight_transfer="balanced stance shifts toward both forefeet",
                gesture_initiation="right fingers uncurl beside her thigh",
                gesture_completion="right hand separates naturally from her leg",
                recovery="shoulders remain relaxed after the startle",
                camera_relationship="she stays launch-focused while her face remains readable to the companion camera",
                provider_prompt_cue="Rocket already rising behind Lena; she releases one held breath, lifts her chin, leans forward three centimeters, tracks the rocket, uncurls right fingers, and keeps her face readable.",
            ),
            _timeline_segment(
                2000,
                4000,
                action="Recognition becomes delight as Lena takes one short half-step toward the view.",
                body_movement="Her left foot advances twelve centimeters and shoulders rotate slightly toward the phone.",
                meaningful_displacement_cm=12,
                gaze_target="briefly the companion camera, then back to the rocket",
                expression="open_delight",
                blink_count=1,
                breathing="easy inhale accompanies the smile without a repeating gasp",
                weight_transfer="weight transfers from right foot to planted left foot",
                gesture_initiation="right elbow bends and forearm begins to lift",
                gesture_completion="forearm reaches chest height with a relaxed wrist",
                recovery="torso settles over the new stance",
                camera_relationship="one quick shared glance includes the camera operator without becoming a pose",
                provider_prompt_cue="Lena takes one twelve-centimeter half-step, transfers weight, smiles with one easy inhale, gives one quick companion glance, and lifts her right forearm to chest height.",
            ),
            _timeline_segment(
                4000,
                6000,
                action="Lena completes one clear pointing gesture toward the climbing rocket.",
                body_movement="Her right forearm extends on a shallow diagonal while head and sternum rise.",
                meaningful_displacement_cm=15,
                gaze_target="the small bright rocket and expanding plume",
                expression="bright_awe",
                blink_count=0,
                breathing="a natural exhale softens the jaw as the gesture reaches full extension",
                weight_transfer="weight remains grounded over the left foot with right heel light",
                gesture_initiation="right index finger extends only as the forearm approaches the target line",
                gesture_completion="the pointing line becomes readable, holds briefly, then relaxes",
                recovery="right elbow begins to soften before the beat ends",
                camera_relationship="the gesture leads viewer attention from Lena to the distant rocket while her face stays clear",
                provider_prompt_cue="Lena completes one readable point toward the small distant rocket, holds it briefly, then relaxes the finger as her elbow softens; face remains unobstructed.",
            ),
            _timeline_segment(
                6000,
                8000,
                action="Lena lowers her hand and watches the successful climb with settled wonder.",
                body_movement="Her arm returns to her side, shoulders lower, and torso returns upright.",
                meaningful_displacement_cm=5,
                gaze_target="rocket first, then a final half-second glance toward the companion",
                expression="settled_wonder",
                blink_count=1,
                breathing="one calm recovery inhale keeps chest and shoulders alive",
                weight_transfer="weight redistributes evenly across both feet",
                gesture_initiation="right elbow folds to begin the return",
                gesture_completion="right hand reaches relaxed neutral beside the shorts",
                recovery="movement resolves cleanly with no frozen grin or repeated point",
                camera_relationship="closing glance shares the awe while the launch remains context",
                provider_prompt_cue="Lena lowers the completed point, drops shoulders, returns upright, breathes once calmly, watches the safe climb, then gives the companion a final half-second glance.",
            ),
        ),
        final_settled_state="At eight seconds Lena is balanced, breathing naturally, right arm relaxed, and still watching the safe distant climb.",
        camera_position="Companion stands about two and a half meters away at Lena's front-right, holding a vertical rear phone at chest height.",
        framing="Three-quarter view from shoes through generous sky, with Lena's face clear and launch corridor over her shoulder.",
        camera_movement="steady_handheld_micro_reframe",
        lens_behavior="Natural main-camera perspective near a 24 to 28 millimeter full-frame equivalent, with no digital zoom or lens change.",
        subject_scale="Lena occupies about fifty-eight percent of frame height so face, hands, shoes, and the gesture remain readable.",
        background_scale="The rocket stays small, distant, and vertically progressive, never giant or moving toward camera.",
        camera_cue="Another person holds a rear phone vertically, 2.5 meters front-right at chest height, three-quarter head-to-shoes framing, clear face, distant rocket over shoulder, subtle handheld reframe, never selfie.",
        dialogue_mode="none",
        dialogue_text="",
        voice_authority_required=False,
        timing="No spoken line. Preserve one breath release near the first beat and one soft delighted exhale as the point completes.",
        music="Restrained warm two-note rise under natural ambience, resolving before eight seconds without overpowering Lena.",
        diegetic_sound=("coastal breeze through grass", "soft non-identifiable crowd reaction", "distant low launch rumble after visual delay", "subtle shoe and cloth movement"),
        ambience=("open coastal air", "quiet water-edge texture", "no close machinery or restricted-site communications"),
        audio_cue="No dialogue. Sync breath release, soft delighted exhale, foot and cloth motion, coastal breeze, sparse crowd, and delayed distant rumble under a restrained warm rise.",
        provider_prompt_cue="Lena watches a distant public rocket launch from a lawful coastal viewing area; action begins with the rocket visible, then one half-step, one completed point toward the rocket, and settled awe.",
        hard_constraints=("exact direct Lena Character Element", "one continuous coherent eight-second performance", "distant believable rocket scale", "safe successful launch", "companion rear smartphone only", "no restricted access or sponsorship implication"),
        negative_constraints=("identity drift", "malformed hands", "repeated breathing loop", "pointing away from the visible rocket", "rocket too close", "explosion", "selfie", "static pose", "wardrobe change", "embedded text or watermark"),
    ),
    CreativeTemplate(
        seed_terms=("market", "dessert", "choice"),
        suffix="night_market_dessert",
        concept="Lena turns a night-market dessert choice into a playful silent viewer challenge.",
        hook="Lena spots two dessert trays at once and makes the choice readable before smiling at the camera.",
        setup="A companion phone follows beside Lena through a warm outdoor dessert stall with shallow crowd motion.",
        payoff="She presents both options, waits one beat for the viewer's vote, and commits to a mischievous half-smile.",
        audience_growth_objective="Drive comments through a clean binary choice and a completed playful human beat.",
        content_pillar="playful_lifestyle",
        desired_emotion="Warm curiosity, flirt-safe playfulness, and comment-ready suspense.",
        product_identity="Independent Lena lifestyle entertainment about a public night-market dessert choice.",
        cta_intent="Ask viewers to pick left or right without claiming a commercial relationship.",
        exact_location="A busy but lawful outdoor night-market dessert lane with warm stall lights, paper trays, and crowd movement kept soft and non-identifiable.",
        architecture=("canvas vendor awning", "low dessert display counter", "string-light row", "open pedestrian lane"),
        materials=("paper dessert trays", "brushed metal tongs", "warm wood counter", "matte stone walkway"),
        practical_objects=("two dessert trays", "small napkin stack", "plain price cards with no readable brand", "paper takeout box"),
        lighting_sources=("warm stall bulbs", "soft overhead string lights", "cool distant street fill"),
        weather=("dry evening air", "light pedestrian breeze", "no rain"),
        environmental_motion=("stall lights flicker slightly", "crowd moves softly in background", "paper tray edge trembles as she lifts it", "hair ends move lightly"),
        background_behavior=("non-identifiable shoppers pass behind her", "vendor hands remain peripheral", "no one blocks Lena or stares into camera"),
        social_context="Lena is an adult customer in a public market; no employee role, sponsorship, or private access is implied.",
        spatial_relationships=("Lena stands one meter from the counter", "camera tracks at arm's length beside her", "dessert trays remain between Lena and the stall lights"),
        realism_details=("dessert steam is subtle", "paper trays bend lightly", "warm light shapes skin naturally", "background stays busy but readable"),
        rocket_distance_meters=1000,
        specificity_markers=("night_market_lane", "dessert_counter", "string_lights", "paper_trays", "warm_practicals"),
        environment_cue="Warm night-market dessert stall with canvas awning, string lights, paper trays, soft crowd motion, and a clear public customer context.",
        garments=(
            {"garment": "ribbed_top", "fit": "fitted square-neck top that stays opaque and secure", "material": "black ribbed knit", "color": "black", "fastened_state": "secured", "continuity": "entire_video", "movement_behavior": "rib texture follows shoulder turn without crawling"},
            {"garment": "cropped_jacket", "fit": "relaxed cropped jacket that stays on both shoulders", "material": "lightweight cotton twill", "color": "cream", "fastened_state": "secured", "continuity": "entire_video", "movement_behavior": "hem swings lightly as she presents the choices"},
            {"garment": "low_sneakers", "fit": "casual low sneakers suited for walking the market", "material": "matte canvas and rubber", "color": "white", "fastened_state": "fully_fastened", "continuity": "entire_video", "movement_behavior": "feet stay planted during the two-option reveal"},
        ),
        wardrobe_cue="Black ribbed square-neck top, cream cropped jacket, and white low sneakers; secure, opaque, logo-free, continuous, and free of reference clothing.",
        anticipation="Lena enters already scanning the dessert display, curious rather than posed, with shoulders angled toward the stall.",
        timeline=(
            _timeline_segment(0, 2000, action="Lena spots two dessert trays and slows her walk.", body_movement="Her shoulders angle toward the stall and her left hand lifts slightly.", meaningful_displacement_cm=6, gaze_target="left dessert tray then right dessert tray", expression="curious_scan", blink_count=1, breathing="small amused inhale", weight_transfer="walking weight settles into a balanced stop", gesture_initiation="left hand starts to hover over the first tray", gesture_completion="hand pauses above the options", recovery="chin dips to inspect details", camera_relationship="she stays focused on the dessert while profile remains readable", provider_prompt_cue="Lena slows at two dessert trays, scans left then right, lifts one hand slightly, settles from walking into a balanced stop, and gives one curious blink."),
            _timeline_segment(2000, 4000, action="She turns enough to include the viewer in the choice.", body_movement="Torso rotates fifteen degrees toward the companion phone while both hands rise.", meaningful_displacement_cm=8, gaze_target="the companion phone for one quick beat", expression="playful_question", blink_count=1, breathing="soft laugh breath without dialogue", weight_transfer="weight moves from back foot to front foot", gesture_initiation="both palms begin opening toward the trays", gesture_completion="palms arrive level with the two options", recovery="shoulders settle instead of continuing to sway", camera_relationship="one glance asks the viewer to choose without sustained posing", provider_prompt_cue="Lena rotates toward the phone, lifts both hands, opens her palms toward the two trays, gives one quick playful glance, and settles into the choice beat."),
            _timeline_segment(4000, 6000, action="The two-option reveal completes and holds long enough to read.", body_movement="Hands separate evenly between the trays and elbows stay relaxed.", meaningful_displacement_cm=10, gaze_target="left option, right option, then viewer", expression="mischievous_smile", blink_count=0, breathing="quiet controlled exhale", weight_transfer="balanced over both feet", gesture_initiation="right fingers extend to mark the second option", gesture_completion="both options are framed clearly at the same time", recovery="wrists soften after the reveal lands", camera_relationship="her face and both options remain visible together", provider_prompt_cue="Lena completes a two-option palm reveal, separates both hands evenly between the dessert trays, smiles mischievously, and keeps her face plus both choices visible."),
            _timeline_segment(6000, 8000, action="She commits to the playful pressure and waits for the vote.", body_movement="One shoulder dips and her chin tilts as the smile lands.", meaningful_displacement_cm=4, gaze_target="the viewer through the companion phone", expression="playful_decision_pressure", blink_count=1, breathing="small quiet laugh breath", weight_transfer="stance remains grounded", gesture_initiation="hands begin returning toward her center", gesture_completion="hands rest lightly near the tray edge", recovery="expression settles into a half-smile without freezing", camera_relationship="she gives the camera the final vote prompt while staying in the market scene", provider_prompt_cue="Lena lowers her hands near the tray edge, tilts her chin, gives one quiet laugh breath, and holds a half-smile that asks the viewer to pick left or right."),
        ),
        final_settled_state="At eight seconds Lena is grounded beside the counter, hands relaxed, and the two dessert choices remain visually legible.",
        camera_position="Companion phone tracks beside Lena at upper-chest height, close enough for dessert choices and her face.",
        framing="Medium vertical companion framing that keeps Lena's face, both hands, and both dessert options visible.",
        camera_movement="steady_handheld_micro_reframe",
        lens_behavior="Natural phone main-camera perspective with no zoom, lens switch, or impossible orbit.",
        subject_scale="Lena occupies about sixty percent of frame height while the dessert choices remain readable.",
        background_scale="The market background stays shallow and warm without swallowing the hands or trays.",
        camera_cue="Companion rear phone tracks beside Lena, medium vertical framing, face plus both dessert options visible, warm stall light, subtle handheld reframe, never selfie.",
        dialogue_mode="none",
        dialogue_text="",
        voice_authority_required=False,
        timing="No spoken line; use one soft laugh breath during the choice reveal and natural tray rustle.",
        music="Light warm percussive bed under market ambience, low enough that human movement remains primary.",
        diegetic_sound=("soft crowd murmur", "paper tray rustle", "vendor counter ambience", "quiet laugh breath"),
        ambience=("warm outdoor market room tone", "distant footsteps", "soft stall-light buzz"),
        audio_cue="No dialogue. Sync soft crowd, paper tray rustle, one laugh breath, and light warm rhythm under the two-option reveal.",
        provider_prompt_cue="Lena silently turns two night-market desserts into a viewer choice: scan both trays, include the camera, complete a two-palm reveal, then hold a playful half-smile.",
        hard_constraints=("exact direct Lena Character Element", "one continuous eight-second public market performance", "both dessert choices readable", "no commercial claim", "no selfie", "platform-safe framing"),
        negative_constraints=("identity drift", "malformed hands", "extra fingers", "unreadable dessert choices", "wardrobe change", "brand logos", "spoken dialogue", "selfie", "static pose", "embedded text or watermark"),
    ),
    CreativeTemplate(
        seed_terms=("rain", "balcony", "reset"),
        suffix="rainy_balcony_reset",
        concept="Lena turns a rainy balcony pause into a calm reset ritual with continuous human motion.",
        hook="Rain interrupts a rushed morning and Lena visibly chooses to slow down instead of perform for the camera.",
        setup="A companion phone watches from the apartment doorway while Lena steps onto a small plant-lined balcony.",
        payoff="She lifts a mug, exhales once, softens her shoulders, and settles into grounded confidence as rain continues outside.",
        audience_growth_objective="Create save-worthy calm through a complete micro-ritual rather than a static beauty pose.",
        content_pillar="quiet_reset",
        desired_emotion="Private calm, grounded confidence, and repeatable ritual.",
        product_identity="Independent Lena lifestyle entertainment about a rainy morning reset.",
        cta_intent="Invite viewers to save the reset idea for a future chaotic morning.",
        exact_location="A small private apartment balcony after rain with plants, wet rail, city lights, and warm indoor light spilling from the open doorway.",
        architecture=("narrow balcony rail", "sliding glass doorway", "small concrete balcony floor", "compact planter shelf"),
        materials=("wet painted metal rail", "ceramic mug", "matte concrete floor", "leafy potted plants"),
        practical_objects=("plain ceramic mug", "folded towel by doorway", "two potted herbs", "small balcony chair"),
        lighting_sources=("warm indoor doorway light", "soft gray rain sky", "diffuse city reflection on wet rail"),
        weather=("light rain tapering off", "cool damp air", "no storm or lightning"),
        environmental_motion=("raindrops slide on the rail", "plant leaves tremble lightly", "steam lifts from the mug", "hair ends move in damp air"),
        background_behavior=("distant windows glow softly", "no neighbors are identifiable", "rain texture remains gentle"),
        social_context="Lena is alone with a trusted companion filming from the doorway; no public bystander or brand context is involved.",
        spatial_relationships=("Lena stands just outside the doorway", "camera remains inside at chest height", "mug stays near her centerline", "rail remains beyond her hands"),
        realism_details=("wet rail catches soft reflections", "mug steam remains subtle", "shoulders visibly release tension", "rain ambience stays quiet"),
        rocket_distance_meters=1000,
        specificity_markers=("rainy_balcony", "wet_rail", "doorway_light", "potted_herbs", "ceramic_mug"),
        environment_cue="Small rainy apartment balcony with wet rail, potted plants, doorway light, soft city reflections, subtle mug steam, and gentle rain motion.",
        garments=(
            {"garment": "cropped_cardigan", "fit": "soft cropped cardigan that stays closed enough for secure movement", "material": "oat knit", "color": "warm oat", "fastened_state": "secured", "continuity": "entire_video", "movement_behavior": "knit shifts softly as shoulders relax"},
            {"garment": "fitted_tank", "fit": "fitted opaque tank under cardigan", "material": "matte cotton rib", "color": "taupe", "fastened_state": "secured", "continuity": "entire_video", "movement_behavior": "tank remains stable and opaque through the mug lift"},
            {"garment": "lounge_shorts", "fit": "high-waist relaxed lounge shorts with full coverage", "material": "charcoal brushed cotton", "color": "charcoal", "fastened_state": "fully_fastened", "continuity": "entire_video", "movement_behavior": "fabric drapes naturally without riding up"},
        ),
        wardrobe_cue="Soft oat cropped cardigan, opaque taupe fitted tank, and charcoal high-waist lounge shorts; secure, continuous, cozy, platform-safe, and logo-free.",
        anticipation="Lena starts tense at the doorway with mug in both hands, then chooses the balcony reset instead of a camera pose.",
        timeline=(
            _timeline_segment(0, 2000, action="Lena pauses at the doorway as rain becomes audible.", body_movement="Her shoulders sit slightly high and then begin to drop.", meaningful_displacement_cm=4, gaze_target="wet balcony rail", expression="frazzled_pause", blink_count=1, breathing="short breath slows into a controlled inhale", weight_transfer="weight shifts from back foot toward the balcony", gesture_initiation="both hands tighten lightly around the mug", gesture_completion="mug centers at chest height", recovery="jaw unclenches slightly", camera_relationship="she is aware of the companion but does not pose", provider_prompt_cue="Lena pauses at the doorway holding a mug, notices the rain, lowers tense shoulders slightly, shifts weight toward the balcony, and slows her breathing."),
            _timeline_segment(2000, 4000, action="She steps onto the balcony and lets the rain reset her pace.", body_movement="One foot advances and torso eases forward without leaning on the rail.", meaningful_displacement_cm=10, gaze_target="plants and wet rail", expression="softening_focus", blink_count=1, breathing="steady inhale through the step", weight_transfer="weight moves onto the forward foot", gesture_initiation="mug starts to lift from chest height", gesture_completion="mug reaches near chin height", recovery="elbows remain relaxed", camera_relationship="profile stays readable from the doorway camera", provider_prompt_cue="Lena takes one slow balcony step, moves weight forward, lifts the mug near chin height, scans the wet rail and plants, and visibly softens her focus."),
            _timeline_segment(4000, 6000, action="The reset ritual completes with one mug lift and one exhale.", body_movement="Shoulders drop, neck lengthens, and chin lowers slightly over the mug.", meaningful_displacement_cm=8, gaze_target="mug steam then rainy city beyond", expression="private_calm", blink_count=0, breathing="one long exhale, not a looping breath cycle", weight_transfer="balanced stance with both feet stable", gesture_initiation="mug tilts gently toward her lips", gesture_completion="mug returns to steady chest height without spilling", recovery="hands settle symmetrically around the mug", camera_relationship="the camera observes a private ritual rather than receiving a pose", provider_prompt_cue="Lena completes one mug lift, gives one long exhale, drops shoulders, lowers her chin, then returns the mug to chest height with both hands steady."),
            _timeline_segment(6000, 8000, action="She settles into grounded confidence while rain continues.", body_movement="Her spine stacks upright and one shoulder rolls back into rest.", meaningful_displacement_cm=5, gaze_target="rainy city lights beyond the balcony", expression="grounded_confidence", blink_count=1, breathing="calm recovery inhale keeps motion alive", weight_transfer="weight distributes evenly", gesture_initiation="thumbs relax against the mug", gesture_completion="mug remains steady near her centerline", recovery="small smile arrives naturally without freezing", camera_relationship="she gives no direct performance, only a quiet inclusive presence", provider_prompt_cue="Lena stands upright, relaxes both thumbs against the mug, gives one calm recovery inhale, lets a small smile arrive, and watches the rainy city without freezing."),
        ),
        final_settled_state="At eight seconds Lena stands balanced on the balcony with the mug steady, shoulders relaxed, and rain still moving around her.",
        camera_position="Companion phone remains just inside the doorway at chest height, looking outward to the balcony.",
        framing="Locked vertical doorway frame with Lena full upper body, mug, wet rail, and plants visible.",
        camera_movement="locked_handheld",
        lens_behavior="Natural phone perspective from the doorway with no zoom, orbit, or lens change.",
        subject_scale="Lena occupies about sixty-two percent of frame height while the balcony context remains visible.",
        background_scale="Balcony plants, rail, and city glow stay secondary to Lena's reset ritual.",
        camera_cue="Companion rear phone remains in the doorway, locked vertical handheld frame, Lena upper body plus mug, wet rail, plants, and rain visible, never selfie.",
        dialogue_mode="none",
        dialogue_text="",
        voice_authority_required=False,
        timing="No spoken line; one long exhale during the mug lift and quiet cloth motion as shoulders relax.",
        music="Soft no-lyric pad under rain and room tone, fading into calm by the end.",
        diegetic_sound=("gentle rain on metal rail", "soft ceramic mug touch", "quiet room tone", "small cardigan fabric movement"),
        ambience=("damp balcony air", "distant muted city texture", "warm indoor hush behind camera"),
        audio_cue="No dialogue. Sync gentle rain, ceramic mug touch, one long exhale, cloth shift, quiet room tone, and a soft no-lyric pad.",
        provider_prompt_cue="Lena turns a rainy balcony pause into a reset: doorway pause, one slow step, one mug lift with one long exhale, shoulder release, and grounded quiet smile.",
        hard_constraints=("exact direct Lena Character Element", "one continuous eight-second reset ritual", "one mug lift only", "no looping breathing", "companion doorway camera only", "platform-safe cozy wardrobe"),
        negative_constraints=("identity drift", "malformed hands", "extra fingers", "looping breath", "static pose", "wardrobe change", "selfie", "storm danger", "neighbor identification", "embedded text or watermark"),
    ),
)


COMMON_NEGATIVE_CONSTRAINTS = (
    "face drift",
    "body proportion drift",
    "plastic or waxy skin",
    "hair morphing",
    "malformed hands",
    "extra digits",
    "fused fingers",
    "reference-image clothing",
    "wardrobe leakage",
    "unfastened garments",
    "accidental sexualized framing",
    "cropped head",
    "insufficient headroom",
    "camera teleportation",
    "impossible camera orbit",
    "generic empty background",
    "bystander as featured subject",
    "provider demo aesthetic",
)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaVideoCreativeError(code, detail)


def _video_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    _require(bool(slug), "video_slug_empty", "video slug is required")
    return slug


def _artifact_id(video_id: str, suffix: str) -> str:
    return f"{video_id.replace('-', '_')}_{suffix}"


def _video_id(governed_date: str, slug: str) -> str:
    return f"lena_video_{governed_date}_{_video_slug(slug)}"


def _select_template(seed: str | None) -> CreativeTemplate:
    normalized = (seed or "").lower()
    for template in TEMPLATES:
        if any(term in normalized for term in template.seed_terms):
            return template
    if not normalized:
        return TEMPLATES[0]
    index = int(hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8], 16) % len(TEMPLATES)
    return TEMPLATES[index]


def build_llm_instruction_authority() -> dict[str, Any]:
    return {
        "artifact_type": "lena_video_creative_generator_instruction_v1",
        "generator_version": GENERATOR_VERSION,
        "purpose": "Produce provisional creative inputs that must become canonical Lena video A-N source artifacts before compilation.",
        "output_mode": "structured_json_only",
        "required_boundary": "no validation, provider compilation, provider create, queue, publish, or learning mutation authority",
        "may_not": [
            "define schemas",
            "compile provider requests",
            "calculate final request hashes or fingerprints",
            "authorize execution",
            "reuse a prior compiled prompt for a new provider create call",
            "substitute any Soul ID for the saved Lena Character Element",
        ],
        "canonical_namespace": "pipeline.media_properties.lena.video",
        "canonical_compiler": "pipeline.media_properties.lena.video.compiler.compile_video",
    }


def _base_artifact(artifact_type: str, *, video_id: str, governed_date: str, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "artifact_id": _artifact_id(video_id, artifact_type.removeprefix("lena_video_").removesuffix("_v1") + "_v1"),
        "property_id": PROPERTY_ID,
        "video_id": video_id,
        "governed_date": governed_date,
        "created_at": created_at,
        "generator_version": GENERATOR_VERSION,
        "upstream_artifacts": [],
    }


def _ref(artifact: Mapping[str, Any]) -> dict[str, str]:
    return {"artifact_id": str(artifact["artifact_id"]), "sha256": canonical_sha256(artifact)}


def _apply_upstream(artifact: dict[str, Any], upstreams: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    artifact["upstream_artifacts"] = [_ref(upstream) for upstream in upstreams]
    return artifact


def _common_attempt_authority() -> dict[str, Any]:
    return {
        "authorized_attempts": 0,
        "retry_authorized": False,
        "separate_authorization_required": True,
        "credit_ceiling_applies_to_all_attempts": True,
    }


def build_canonical_source_artifacts(
    *,
    governed_date: str,
    video_slug: str,
    user_seed: str | None = None,
    created_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    _require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", governed_date) is not None, "governed_date_invalid", "governed_date must be YYYY-MM-DD")
    template = _select_template(user_seed or video_slug)
    video_id = _video_id(governed_date, video_slug)
    timestamp = created_at or f"{governed_date}T00:00:00Z"

    character = _base_artifact("lena_video_character_authority_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
        "identity_name": "Lena",
        "adult_status": "verified_adult",
        "character_element_uuid": CHARACTER_ELEMENT_UUID,
        "character_element_token": CHARACTER_ELEMENT_TOKEN,
        "direct_character_element_binding_required": True,
        "face_authority": "Preserve Lena's verified adult facial identity, stable facial geometry, visible natural eyes, and no beautification-driven drift.",
        "body_authority": "Preserve Lena's established adult proportions and believable anatomy through all movement, including hands and fingers.",
        "hair_authority": "Keep Lena's hair identity stable in color, hairline, length, volume, and texture with only plausible physical motion.",
        "skin_authority": "Render natural skin texture, pores, tonal variation, and coherent light response without plastic smoothing.",
        "posture_camera_relationship": "Lena is aware a trusted companion is filming her, but the governed action leads the performance.",
        "wardrobe_doctrine": [
            "Wardrobe comes only from the governed wardrobe artifact, never from Character Element reference imagery.",
            "Garments remain continuous, secure, physically plausible, and platform safe for the full shot.",
            "Framing must not crop Lena into isolated body parts or create accidental sexualized emphasis.",
        ],
        "reference_image_clothing_exclusion": True,
        "prohibited_identity_drift": [
            "face replacement or facial geometry drift",
            "body proportion drift or limb-length changes",
            "hairline, hair color, or texture morphing",
            "skin texture loss or plastic smoothing",
            "malformed hands, fused fingers, or extra digits",
        ],
        "prohibited_provider_styling": [
            "provider-added glamour makeup not present in authority",
            "provider-added jewelry, logos, or branded styling",
            "reference-image wardrobe leakage",
            "generic influencer beauty-filter treatment",
        ],
        "provider_prompt_cue": "Verified adult Lena through exact direct Character Element binding: stable face geometry and body proportions, natural eyes, skin texture, hairline, hair motion, hands, and fingers; no beautification, reference clothing, or added styling drift.",
    }

    policy = _base_artifact("lena_video_policy_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
        "final_videos_per_governed_date": 1,
        "cadence_calculation": {
            "calendar_key": "governed_date",
            "timezone_status": "execution_timezone_requires_separate_authority",
            "final_states": ["final", "published"],
        },
        "duration_ms": 8000,
        "resolution": "720p",
        "width_pixels": 720,
        "height_pixels": 1280,
        "aspect_ratio": "9:16",
        "standard_credit_ceiling": 36,
        "higgsfield_prompt_execution_policy_max_chars": 4096,
        "provider_capability_requirements": [
            "direct binding to the exact governed Lena Character Element",
            "deterministic acceptance of an exact eight-second portrait request",
            "720p portrait output with auditable job and spend evidence",
            "temporal performance and controlled camera motion support",
        ],
        "direct_character_element_required": True,
        "preferred_initial_route": "higgsfield_seedance_2_0_when_direct_element_binding_supported",
        "voice_mode": "optional_by_concept",
        "temporal_hpe_required": True,
        "attempt_authority": _common_attempt_authority(),
        "duplicate_prevention": "reject_more_than_one_final_video_per_governed_date",
        "authorization_requirements": [
            "a separately granted execution authorization bound to the validated compiled request hash",
            "an explicitly governed attempt count and retry decision",
            "a provider route proven to support direct Lena Character Element binding",
            "a preflight proving aggregate authorized spend cannot exceed thirty-six credits",
        ],
        "photo_lane_isolation": {
            "live_photo_lane_unchanged": True,
            "photo_scheduler_not_consumed": True,
            "queues_publishers_credentials_not_consumed": True,
        },
        "execution_authorized": False,
    }

    business = _base_artifact("lena_video_business_intent_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
        "audience_growth_objective": template.audience_growth_objective,
        "content_pillar": template.content_pillar,
        "desired_emotion": template.desired_emotion,
        "revenue_intent": "future_optional",
        "affiliate_relationship": False,
        "commercial_relationship": "none",
        "product_identity": template.product_identity,
        "usage_rights": [
            "Use only newly generated Lena video output and separately cleared audio elements.",
            "Do not imply third-party sponsorship, approval, employment, or restricted access.",
            "Do not use bystander likenesses as identifiable featured subjects.",
        ],
        "paid_partnership": False,
        "space_x_affiliation": "none",
        "disclosure": {
            "required": False,
            "text": "",
            "reason": "No sponsorship, paid partnership, affiliate relationship, employment, endorsement, or provider-funded placement is claimed.",
        },
        "prohibited_claims": [
            "Lena represents a third-party brand or venue",
            "the scene documents a real dated event unless separately verified before publication",
            "restricted access, staff status, sponsorship, or endorsement",
            "future audience, revenue, or performance results are guaranteed",
        ],
        "cta_intent": template.cta_intent,
    }

    spec_id_targets = {
        "character": character["artifact_id"],
        "business": business["artifact_id"],
        "environment": _artifact_id(video_id, "environment_v1"),
        "wardrobe": _artifact_id(video_id, "wardrobe_v1"),
        "hpe": _artifact_id(video_id, "hpe_v1"),
        "camera": _artifact_id(video_id, "camera_v1"),
        "audio": _artifact_id(video_id, "audio_plan_v1"),
    }
    spec = _apply_upstream(
        _base_artifact("lena_video_spec_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
            "daily_slot": "daily_video_01",
            "concept": template.concept,
            "hook": template.hook,
            "setup": template.setup,
            "payoff": template.payoff,
            "platform": "instagram_reel",
            "character_authority_id": spec_id_targets["character"],
            "environment_id": spec_id_targets["environment"],
            "wardrobe_id": spec_id_targets["wardrobe"],
            "hpe_id": spec_id_targets["hpe"],
            "camera_id": spec_id_targets["camera"],
            "audio_plan_id": spec_id_targets["audio"],
            "temporal_performance": "Four contiguous two-second beats must visibly initiate, progress, complete, and recover without static posing or repeated motion loops.",
            "sound_intent": template.audio_cue,
            "dialogue_intent": "No dialogue unless explicitly carried by the canonical audio artifact; this fresh authority defaults to nonverbal performance.",
            "caption_intent": template.cta_intent,
            "business_intent_id": spec_id_targets["business"],
            "cost_ceiling_credits": 36,
            "attempt_authority": deepcopy(policy["attempt_authority"]),
            "provider_neutral_requirements": [
                "bind the exact governed Lena identity element directly",
                "render one continuous eight-second portrait shot without cuts or temporal resets",
                "preserve the complete governed performance, wardrobe, environment, camera, and sound contracts",
                "return auditable request, spend, output, and identity evidence before final disposition",
            ],
            "qa_requirements": [
                "unmistakable stable Lena identity in every assessable frame",
                "believable adult anatomy, natural hands, skin texture, and hair motion",
                "all four temporal performance beats visibly initiate, progress, complete, and recover",
                "wardrobe remains exact, secure, continuous, and free of reference-image leakage",
                "camera remains companion-held, natural, non-selfie, and free of impossible motion",
                "result must look like premium finished Lena content rather than a provider demonstration",
            ],
            "provider_prompt_cue": template.provider_prompt_cue,
            "hard_constraints": list(template.hard_constraints),
            "negative_constraints": list(dict.fromkeys((*template.negative_constraints, *COMMON_NEGATIVE_CONSTRAINTS))),
            "user_locks": [
                {"field_path": "/lena_video_character_authority_v1/character_element_uuid", "value": CHARACTER_ELEMENT_UUID},
                {"field_path": "/lena_video_policy_v1/final_videos_per_governed_date", "value": 1},
                {"field_path": "/lena_video_policy_v1/duration_ms", "value": 8000},
                {"field_path": "/lena_video_policy_v1/resolution", "value": "720p"},
                {"field_path": "/lena_video_policy_v1/aspect_ratio", "value": "9:16"},
                {"field_path": "/lena_video_policy_v1/standard_credit_ceiling", "value": 36},
                {"field_path": "/lena_video_environment_v1/access_context/restricted_access", "value": False},
                {"field_path": "/lena_video_camera_v1/camera_holder", "value": "another_person"},
                {"field_path": "/lena_video_camera_v1/selfie", "value": False},
                {"field_path": "/lena_video_wardrobe_v1/wardrobe_changes", "value": False},
                {"field_path": "/lena_video_spec_v1/concept", "value": template.concept},
            ],
        },
        (character, policy, business),
    )

    hpe = _apply_upstream(
        _base_artifact("lena_video_hpe_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
            "anticipation": template.anticipation,
            "timeline": [deepcopy(item) for item in template.timeline],
            "final_settled_state": template.final_settled_state,
        },
        (spec,),
    )
    environment = _apply_upstream(
        _base_artifact("lena_video_environment_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
            "exact_location": template.exact_location,
            "architecture": list(template.architecture),
            "materials": list(template.materials),
            "practical_objects": list(template.practical_objects),
            "lighting_sources": list(template.lighting_sources),
            "weather": list(template.weather),
            "environmental_motion": list(template.environmental_motion),
            "background_behavior": list(template.background_behavior),
            "social_context": template.social_context,
            "spatial_relationships": list(template.spatial_relationships),
            "realism_details": list(template.realism_details),
            "access_context": {
                "public_area": True,
                "restricted_access": False,
                "special_access_implied": False,
                "safety_boundary_visible": True,
            },
            "brand_affiliation_implied": False,
            "rocket_distance_meters": template.rocket_distance_meters,
            "specificity_markers": list(template.specificity_markers),
            "provider_neutral_requirements": [
                "show a specific believable location rather than a generic empty background",
                "preserve coherent light, weather, object, and human-scale relationships",
                "keep bystanders non-identifiable and secondary to Lena",
                "show no restricted access, private credential, sponsorship, accident, or emergency implication",
            ],
            "provider_prompt_cue": template.environment_cue,
        },
        (spec,),
    )
    wardrobe = _apply_upstream(
        _base_artifact("lena_video_wardrobe_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
            "garments": [deepcopy(item) for item in template.garments],
            "accessories": [],
            "public_safety_rules": [
                "all garments remain opaque, secure, and platform safe throughout motion",
                "camera framing avoids accidental sexualized emphasis",
                "footwear and garments remain physically suitable for the scene",
            ],
            "reference_outfit_exclusion_required": True,
            "reference_outfit_exclusions": [
                "ignore every garment, accessory, logo, color, and styling choice visible in Character Element reference imagery",
                "do not copy reference-image swimwear, lingerie, dresses, footwear, jewelry, or provider-added styling",
            ],
            "commercial_brand_declarations": [],
            "wardrobe_changes": False,
            "provider_neutral_requirements": [
                "render exactly the governed garments and no unlisted visible accessory",
                "keep every garment continuous, opaque, secure, and free of brand marks",
                "preserve physically plausible cloth response without leakage or sudden restyling",
                "exclude all Character Element reference-image clothing",
            ],
            "provider_prompt_cue": template.wardrobe_cue,
        },
        (spec,),
    )
    camera = _apply_upstream(
        _base_artifact("lena_video_camera_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
            "camera_holder": "another_person",
            "device_type": "smartphone_rear_camera",
            "camera_position": template.camera_position,
            "framing": template.framing,
            "safe_headroom_basis_points": 1200,
            "lens_behavior": template.lens_behavior,
            "camera_movement": template.camera_movement,
            "autofocus": "Continuous face-priority focus remains on Lena while the context stays legible; no focus pumping.",
            "exposure": "Exposure protects Lena's face and scene detail without abrupt gain shifts or artificial halos.",
            "subject_scale": template.subject_scale,
            "background_scale": template.background_scale,
            "caption_safe_areas": [
                "keep the top twelve percent free of Lena's head and essential scene action",
                "keep the lower fifteen percent free of hands, shoes, and completed gestures",
                "keep the right-side interface strip free of Lena's eyes and key action",
            ],
            "lena_camera_relationship": "Lena knows her companion is filming but performs through the governed action rather than sustained lens-facing posing.",
            "selfie": False,
            "provider_neutral_requirements": [
                "simulate a real companion-held vertical smartphone shot rather than selfie, tripod, drone, crane, or impossible orbit",
                "preserve face visibility, gesture readability, scene context, caption-safe areas, and headroom",
                "maintain coherent focus, exposure, lens perspective, subject scale, and background scale for all eight seconds",
            ],
            "provider_prompt_cue": template.camera_cue,
        },
        (spec,),
    )
    audio = _apply_upstream(
        _base_artifact("lena_video_audio_plan_v1", video_id=video_id, governed_date=governed_date, created_at=timestamp) | {
            "dialogue_mode": template.dialogue_mode,
            "dialogue_text": template.dialogue_text,
            "voice_authority_required": template.voice_authority_required,
            "timing": template.timing,
            "pronunciation": [],
            "lip_sync_required": template.dialogue_mode != "none",
            "music": template.music,
            "diegetic_sound": list(template.diegetic_sound),
            "ambience": list(template.ambience),
            "sound_hierarchy": [
                "Lena's breath and immediate physical movement",
                "scene-specific diegetic sound",
                "natural ambience",
                "restrained music bed",
            ],
            "mix_targets": [
                "integrated loudness suitable for premium vertical social playback without clipping",
                "preserve human motion transients and natural ambience",
                "keep music subordinate to Lena's human performance",
                "use no synthetic spoken voice unless dialogue mode explicitly requires it",
            ],
            "provider_neutral_requirements": [
                "align breath, gesture, clothing, and environment sounds to the governed timeline",
                "keep ambience natural and subordinate to Lena's human performance",
                "return separate auditable audio evidence before final quality disposition",
            ],
            "provider_prompt_cue": template.audio_cue,
        },
        (spec,),
    )

    return {
        "lena_video_character_authority_v1": character,
        "lena_video_policy_v1": policy,
        "lena_video_business_intent_v1": business,
        "lena_video_spec_v1": spec,
        "lena_video_hpe_v1": hpe,
        "lena_video_environment_v1": environment,
        "lena_video_wardrobe_v1": wardrobe,
        "lena_video_camera_v1": camera,
        "lena_video_audio_plan_v1": audio,
    }


def write_source_artifacts(video_root: Path, artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    video_root.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, str] = {}
    for artifact_type in SOURCE_TYPES:
        statuses[artifact_type] = atomic_write_json(video_root / ARTIFACT_FILES[artifact_type], artifacts[artifact_type])
    return statuses


def write_instruction_authority(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, build_llm_instruction_authority())


def compile_canonical_video_package(video_root: Path, *, write_generated: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    plan, compiled = compile_video(video_root)
    if write_generated:
        atomic_write_json(video_root / ARTIFACT_FILES["lena_video_generation_plan_v1"], plan)
        atomic_write_json(video_root / ARTIFACT_FILES["lena_higgsfield_compiled_request_v1"], compiled)
    return plan, compiled


def validate_canonical_sources(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    from .artifacts import LoadedArtifact

    loaded = {
        artifact_type: LoadedArtifact(
            path=Path(ARTIFACT_FILES[artifact_type]),
            relative_path=ARTIFACT_FILES[artifact_type],
            data=dict(artifacts[artifact_type]),
            sha256=canonical_sha256(artifacts[artifact_type]),
        )
        for artifact_type in SOURCE_TYPES
    }
    issues = validate_source_for_compilation(loaded)
    return {
        "ok": not issues,
        "errors": [issue.to_dict() for issue in issues],
        "counters": zero_activity_counters(),
    }


def prompt_sha256(compiled_request: Mapping[str, Any]) -> str:
    return hashlib.sha256(str(compiled_request["exact_compiled_prompt"]).encode("utf-8")).hexdigest()


def build_attempt_record(
    *,
    compiled_request: Mapping[str, Any],
    attempt_number: int,
    superseded_attempt: Mapping[str, Any] | None = None,
    previous_qa_findings: list[str] | None = None,
    exact_creative_changes: list[str] | None = None,
    attempt_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require(attempt_number >= 1, "attempt_number_invalid", "attempt number must be positive")
    authorization = dict(attempt_authorization or {"provider_create_authorized": False, "authorized_attempts": 0, "retry_count": 0})
    _require(not authorization.get("provider_create_authorized", False), "attempt_record_must_not_authorize_create", "offline attempt records cannot authorize provider creation")
    record = {
        "record_type": "lena_video_attempt_record_v1",
        "attempt_id": f"{compiled_request['video_id']}_attempt_{attempt_number:03d}",
        "video_id": compiled_request["video_id"],
        "governed_date": compiled_request["governed_date"],
        "attempt_number": attempt_number,
        "superseded_attempt_id": None if superseded_attempt is None else superseded_attempt.get("attempt_id"),
        "previous_provider_job_id": None if superseded_attempt is None else superseded_attempt.get("provider_job_id"),
        "previous_qa_findings": previous_qa_findings or [],
        "exact_creative_changes": exact_creative_changes or [],
        "compiled_request_sha256": canonical_sha256(compiled_request),
        "compiled_prompt_sha256": prompt_sha256(compiled_request),
        "source_plan_sha256": compiled_request["source_plan_sha256"],
        "deterministic_compilation_fingerprint": compiled_request["deterministic_compilation_fingerprint"],
        "attempt_authorization": authorization,
        "retry_count": int(authorization.get("retry_count", 0)),
        "provider_job_id": None,
        "qa_result": None,
    }
    if superseded_attempt and superseded_attempt.get("qa_result") == "qa_rejected":
        _require(
            record["compiled_prompt_sha256"] != superseded_attempt.get("compiled_prompt_sha256"),
            "qa_rejected_attempt_prompt_reuse_blocked",
            "QA-rejected attempts require a new compiled prompt for any new create call.",
        )
    return record


def validate_prompt_reuse(
    *,
    prior_attempt: Mapping[str, Any],
    proposed_compiled_request: Mapping[str, Any],
    operation: str,
) -> dict[str, Any]:
    allowed_same_attempt_ops = {
        "same_provider_job_recovery",
        "same_ambiguous_submission_reconciliation",
        "same_result_download_or_validation",
        "deterministic_recompile_same_attempt",
    }
    proposed_prompt_hash = prompt_sha256(proposed_compiled_request)
    same_prompt = prior_attempt.get("compiled_prompt_sha256") == proposed_prompt_hash
    same_video_identity = (
        prior_attempt.get("video_id") == proposed_compiled_request.get("video_id")
        and prior_attempt.get("governed_date") == proposed_compiled_request.get("governed_date")
    )
    if operation in allowed_same_attempt_ops and same_video_identity and same_prompt:
        return {"ok": True, "reuse_allowed_for": operation}
    if operation == "new_provider_create":
        blockers = []
        if same_prompt:
            blockers.append("compiled_prompt_reused_for_new_create")
        if not same_video_identity:
            blockers.append("video_date_or_identity_differs")
        if prior_attempt.get("qa_result") == "qa_rejected":
            blockers.append("prior_attempt_was_qa_rejected")
        if blockers:
            raise LenaVideoCreativeError("prompt_reuse_blocked", ", ".join(blockers))
        return {"ok": True, "reuse_allowed_for": "new_provider_create_with_fresh_prompt"}
    raise LenaVideoCreativeError("prompt_reuse_operation_not_allowed", f"operation is not allowed: {operation}")


def novelty_profile(source_artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    spec = source_artifacts["lena_video_spec_v1"]
    hpe = source_artifacts["lena_video_hpe_v1"]
    environment = source_artifacts["lena_video_environment_v1"]
    wardrobe = source_artifacts["lena_video_wardrobe_v1"]
    camera = source_artifacts["lena_video_camera_v1"]
    audio = source_artifacts["lena_video_audio_plan_v1"]
    return {
        "concept": spec["concept"],
        "environment": environment["exact_location"],
        "wardrobe": wardrobe["provider_prompt_cue"],
        "principal_gesture": hpe["timeline"][2]["gesture_completion"],
        "camera_grammar": camera["provider_prompt_cue"],
        "camera_movement": camera["camera_movement"],
        "hook_structure": spec["hook"],
        "cta": spec["caption_intent"],
        "audio_use": audio["provider_prompt_cue"],
        "ending_pose": hpe["final_settled_state"],
        "emotional_payoff": spec["payoff"],
    }


def run_novelty_governor(
    candidate_artifacts: Mapping[str, Mapping[str, Any]],
    history_profiles: list[Mapping[str, Any]],
    *,
    lookback: int = 30,
) -> dict[str, Any]:
    candidate = novelty_profile(candidate_artifacts)
    recent = list(history_profiles or [])[:lookback]
    reasons: list[str] = []
    consecutive_fields = ("environment", "principal_gesture", "hook_structure", "camera_movement", "emotional_payoff")
    compare_fields = tuple(candidate)
    if recent:
        previous = recent[0]
        for field in consecutive_fields:
            if str(candidate.get(field, "")).strip().lower() == str(previous.get(field, "")).strip().lower():
                reasons.append(f"consecutive_reuse:{field}")
    for field in compare_fields:
        same_count = sum(1 for item in recent if str(candidate.get(field, "")).strip().lower() == str(item.get(field, "")).strip().lower())
        if same_count >= 3:
            reasons.append(f"excessive_30_day_repetition:{field}:{same_count}")
    return {
        "ok": not reasons,
        "lookback_count": len(recent),
        "rejection_reasons": reasons,
        "compared_fields": list(compare_fields),
        "consecutive_lockout_fields": list(consecutive_fields),
    }
