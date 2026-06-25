from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "pipeline" / "state" / "lena_prompt_memory.json"

VERSION = "v1.2.8.2_autonomous_human_life_director"

BANNED_PUBLIC_TERMS = [
    "ai", "a.i.", "artificial intelligence", "virtual influencer", "synthetic",
    "bot", "generated", "avatar", "fake", "computer generated", "cg", "cgi",
    "deepfake", "digital human", "not real",
]

VISUAL_BANS = [
    "No visible text, letters, numbers, symbols, signage, menus, book text, labels, logos, watermarks, UI overlays, phone screens, status bars, app frames, captions inside the image, or garbled marks anywhere.",
    "No readable or unreadable writing on clothing, products, walls, books, screens, streets, cars, packaging, mirrors, or background objects.",
    "Keep frame edges clean, especially the top edge: no random marks, fake interface bars, black phone borders, icons, floating symbols, or visual junk.",
    "No generic stock-photo setup. The image must feel like a real private camera-roll moment from Lena’s day.",
    "No boring default wardrobe. Avoid plain tank top plus basic jeans, bland library setups, random luxury flexing, or silly staged concepts.",
]

NEGATIVE_PROMPT = """
visible text, readable text, unreadable text, letters, numbers, symbols, signage, street sign, menu, book text,
poster, logo, watermark, label, brand mark, clothing logo, phone screen, app interface, UI overlay, status bar,
camera interface, browser bar, subtitles, caption text in image, garbled writing, pseudo letters, random marks,
top edge artifacts, frame border artifacts, extra fingers, missing fingers, warped hands, distorted face,
plastic skin, waxy skin, uncanny eyes, broken anatomy, duplicate limbs, background morphing, boring stock photo,
plain white tank top and basic blue jeans, library bookshelf background, fake luxury flex, alcohol-focused scene, unsafe party scene, explicit sexual content, explicit nudity, nude, pornographic content, fetish costume, fetish framing, identity-breaking costume, identity-breaking scenario,
reference image copy, seed image remake, pose clone, composition duplicate, black hair on Lena, bleached blonde hair, drastic hair color change, identity-breaking hair shift,
full suit, pantsuit, corporate blazer and trouser outfit, business suit, officewear, business-professional attire, frumpy shapeless outfit, oversized shapeless clothing,
heavy freckle clusters, blotchy facial spots, identity-breaking skin speckling, acne-like facial blotches,
slim model figure, skinny body, model-thin proportions, flat chest, narrow hips, boxy silhouette, no visible waist curve,
distorted anatomy, cartoon body proportions, warped body shape, exaggerated impossible bust or hip proportions,
crotch-focused framing, explicit genital emphasis, nude posing, explicit sexual posing, pornographic posing,
campus setting, classroom interior, school library shelves, lecture hall, walking-to-class scene framing, student narrative framing,
cheap clubwear energy, lingerie-bait framing, thirst-trap AI styling, trashy or discount-looking fashion framing,
hotel room interiors, hotel-looking staged backgrounds, hotel bed or hotel furniture in frame,
professional photography, studio lighting, high resolution, 8K, 4K, sharp focus, perfectly posed, DSLR, mirrorless, Canon, Sony, bokeh, shallow depth of field, beautiful, stunning, cinematic lighting, magazine quality, portrait mode, overly polished, portfolio lighting, commercial fashion shoot, editorial fashion shoot, model portfolio, photographer portfolio, luxury ad campaign, glossy editorial shoot, over-smoothed skin, airbrushed skin, sterile studio background, distorted text
""".strip()


DEFAULT_LIFE_BIBLE = {
    "persona": {
        "name": "Lena",
        "core": "classy luxury baddie / high-end fashion fit-check / beauty maintenance / fitness-glam influencer; elevated, polished, expensive-looking, platform-safe; visually magnetic, scroll-stopping; use the Lena element as face, body, hair, and identity reference; preserve her natural proportions from the reference element; platform-safe, confident, believable; always looks like a real woman with real appeal",
        "content_standard": "human-like in every way; every post must feel like it came from a real person with a real day; visual magnetism and attractiveness come first — Lena is the hook, the scene is the context",

    },
 "things_she_does": [ "casual cafe time and iced coffee out, no study framing", "gym sessions and athletic body photos", "errands and neighborhood daily routines", "Herby walks, play, and training sessions", "apartment routines and resets", "evening wind-down at home", "skincare and getting-ready routines", "outfit checks before leaving", "cooking simple dinner at home", "window-light selfies and candid apartment moments", "casual dance clips at home that require music before posting", "trying on new outfits and wondering what followers think", "platform-safe bold outfit selfies with stylish, confident poses", "fashion and soft glam moments", "nightlife or social scenes when platform-safe, non-explicit, and identity-consistent", "cosplay or themed creative looks when styled as creator/fashion/lifestyle content", "gaming desk and cozy creator moments", "outdoor walks, park paths, and city sidewalk moments", "eye-catching main-character scenes", "low-energy honest real-life moments", "mirror fit checks and full-body outfit snapshots", "bedroom and closet getting-ready routines", "street and errands baddie looks", "parked-car selfie-style shots, never while driving", "going-out looks and night-out getting-ready photos", "close-medium flirty body-forward photos with waist and hips clearly visible",
],
    "things_she_would_never_do": [
        "fake private jet or mansion flexing",
        "alcohol-focused scenes",
        "office-job cosplay",
        "brand-logo flexing",
        "signage-heavy streets or text-heavy backgrounds",
        "overly staged stock-photo model poses",
        "plain boring tank-top-and-jeans content as a main look",
        "plain boring white shirt and black yoga pants look",
        "reference image pose or background cloning and seed image remakes",
        "drastic hair color changes that break identity such as black hair or bleached blonde",
        "full suit, pantsuit, or corporate blazer-and-trouser business professional outfit",
        "officewear or business-professional styling that makes her look like a corporate employee",
        "frumpy, shapeless, or oversized coverage-first outfits that hide her figure and appeal",
        "safe-but-bland wardrobe with no visual hook, no flattering silhouette, no creator or lifestyle energy",
        "hide her curvy figure under shapeless, oversized, or heavily draped clothing",
        "appear in explicit, fetish, nude, or pornographic framing",
    ],
    "style": {
        "wardrobe": [
            "cropped leather jacket over a fitted bodysuit or satin cami with a mini skirt and heeled boots, soft glam makeup",
            "satin slip dress or fitted mini dress with strappy heels and delicate gold jewelry",
            "off-shoulder top or satin cami with high-waisted fitted trousers or a mini skirt and block heels",
            "cropped suede jacket over a ribbed crop top with high-waisted shorts or slim trousers and ankle boots",
            "fitted streetwear: cropped jacket or hoodie, bodysuit or fitted crop top, mini skirt or slim trousers, boots",
            "soft glam daytime look: fitted silk blouse or knit crop top, high-waisted midi skirt or slim trousers, heeled slides",
        ],
        "makeup": "natural polished glam, realistic skin texture, soft brows, neutral lips",
        "hair": "loose natural movement, soft waves or clean low-effort styling; warm brunette, chestnut, or auburn tones are acceptable with natural variation; avoid drastic black hair, blonde shifts, or hair changes that make her look like a different person",
        "body": "use the Lena element as the face, body, hair, and identity reference; preserve her natural proportions from the reference element; do not alter reference body proportions; tasteful skin exposure at shoulders, neckline, or arms as fits the scene; confident body language; never hide shape under shapeless or oversized clothing",
    },
  "slot_purpose": { "01": "mirror fit check, morning get-ready, home kitchen, outdoor walk, Herby walk, or honest start-of-day moment", "02": "outfit, getting-ready, errands, fashion, soft glam, or platform-safe bold look moment", "03": "dance, movement, cosplay/creative look, eye-catching fashion, or music-required creator moment", "04": "afternoon lifestyle, cafe/study, gym/wellness, Herby, social, culture, outdoor, or main-character moment", "05": "evening wind-down, night out/social energy, apartment reset, gaming/cozy creator moment, or soft night routine", },

    "autonomy_rules": [
        "avoid repeating lanes from recent memory",
        "avoid repeating same-day locations",
        "prefer ordinary believable life over fake luxury",
        "choose scenes that reduce text/signage risk",
        "reject anything with text, UI, symbols, jumble, weird edges, or generic stock-photo energy",
        "Lena is the primary subject; prioritize mirror fit checks, outfit checks, getting-ready moments, gym/athletic body photos, errands/street looks, going-out looks, flirty home photos, outdoor walks, night-out/social, gaming/cozy creator, low-energy honest days; apartment-only content must not dominate any batch",
        "Herby appears in roughly 20% of Lena photos overall; for 3-photo batches most days use 0 Herby slots with 1 max on occasional days; for 4-photo batches 0-1 max; do not default any slot to Herby every day",
        "do not recreate the reference image pose, outfit, background, lighting, framing, facial angle, or composition; every output must feel like a new candid moment from a different day",
        "every asset in the batch must be visually and conceptually distinct: different story beat, location or setting, body pose, face angle, camera distance, composition, wardrobe silhouette, lighting mood, activity, and emotional expression; technically good is not enough if it repeats the same formula",
        "every asset must have a visual hook first: attractiveness, confident pose, flattering silhouette, attitude, expression, motion, or lifestyle energy; technically realistic but not scroll-stopping is a failure",
        "Lena is a hot human lifestyle influencer — every image must read as visually magnetic, scroll-stopping, and attractive; she must always match the Lena element reference: preserve reference face, body, hair, and proportions; do not alter reference body proportions; platform-safe, confident, and believable; never bland, frumpy, overly covered, or sexless",
        "wardrobe must always look elevated, polished, and expensive — never cheap or generic: day/errands = sleek fitted casual with luxury-style details; night-out = polished glam, sleek heels, gold jewelry, glossy lip, structured blazer or fitted dress; home/cozy = body-aware fitted but refined; gym/wellness = premium athletic, flattering, no visible logos; mirror/fit-check = full look must read expensive and intentional",
        "wardrobe styling should be visually hooky and platform-safe sexy about 75% of the time: crop tops, off-shoulder tops, fitted bodysuits, mini skirts, fitted shorts, bodycon casual dresses, cutout knit tops, flattering athleisure, or open overshirt over fitted crop; 25% of outputs may be softer/cozy/wholesome for variety — still flattering and body-aware, not shapeless; sexy does not mean explicit, nude, fetish, or underwear/lingerie",
        "safety comes from tasteful framing, not boring wardrobe; never produce suits, pantsuits, officewear, or corporate professional styling",
    ],
}


SCENARIOS = [
	 {
        "lane": "gym athletic photo",
        "slot_family": ["04"],
        "setting": "local gym, plain painted wall, no branded logos on machines, no visible screens, neutral light",
        "story": "Lena hit the gym and caught a quick body photo mid-session.",
        "pose": "standing near a wall, gym bag on one shoulder, slight flush from the workout, hair in a low bun or pulled back naturally",
        "camera": "vertical candid portrait, realistic gym light, background slightly out of focus",
        "caption": "showed up and that counts #gym #fitness #gymday #fitlife #bodycheck #lifestyle",
    },

	 {
        "lane": "cafe casual hang",
        "slot_family": ["04"],
        "setting": "small cafe interior with warm light, wooden table, plain ceramic mug, no laptop, no menus, no chalkboards, no readable surfaces",
        "story": "Lena stopped for a cafe break and the vibe was worth a photo.",
        "pose": "sitting at the table, elbow resting on it, chin in hand, soft unfocused gaze away from camera",
        "camera": "vertical lifestyle shot, phone-captured framing, cafe warmth visible naturally out of focus in background",
        "caption": "coffee then decisions #cafe #coffeetime #softlife #lifestyle #dailyvibe",
    },
	 {
        "lane": "mirror fit check",
        "slot_family": ["01"],
        "setting": "clean apartment bedroom or entryway with full-length mirror, soft daylight or warm lamp, no visible phone UI in reflection, no readable text",
        "story": "Lena was doing a quick fit check before leaving and the outfit was worth a photo.",
        "pose": "full body visible in mirror, one hand adjusting outfit or touching hair, confident casual expression, slight body angle for flattering silhouette",
        "camera": "vertical phone photo taken in mirror, full outfit visible from head to mid-thigh or below, no phone visible in frame",
        "caption": "approved by nobody but me #fitcheck #ootd #outfitcheck #morningvibes #style",
    },
    {
        "lane": "morning window coffee",
        "slot_family": ["01"],
        "setting": "Lena’s apartment near a clean window with soft morning light, neutral curtains, ceramic mug, simple table, plants, no books, no labels, no screens",
        "story": "Lena took a quiet morning photo before the day got busy.",
        "pose": "standing near the window with one hand around a mug, shoulders relaxed, small sleepy smile, natural weight shift",
        "camera": "vertical phone photo from a friend-height angle, soft depth of field, candid but composed",
        "caption": "slow start, better light #morningvibe #softlife #lifestyle #dailyvibe #cozystyle #citymorning",
    },
    {
        "lane": "apartment reset",
        "slot_family": ["01", "04"],
        "setting": "clean apartment corner after tidying up, folded blanket, neutral sofa, warm lamp, plant, no books, no labels, no visible screens",
        "story": "Lena paused after resetting her apartment and made the ordinary moment look good.",
        "pose": "sitting casually on the arm of the sofa, one hand brushing hair back, relaxed real smile",
        "camera": "vertical lifestyle photo, slightly candid, natural phone camera realism",
        "caption": "resetting the room reset my brain #apartmentvibe #softlife #lifestyle #dailyvibe #cozyhome #quietmoments",
    },
    {
        "lane": "outfit before errands",
        "slot_family": ["02"],
        "setting": "simple apartment entryway with clean wall, small bench, coat hook with no labels, soft daylight, no mirror text, no signage",
        "story": "Lena snapped an outfit photo before leaving for errands.",
        "pose": "full outfit visible, one foot slightly forward, hand adjusting sleeve or bag strap, confident but casual",
        "camera": "vertical full-body phone photo taken by another person, no phone visible, clean framing",
        "caption": "errands but make it cute #ootd #outfitcheck #citystyle #everydaystyle #softglam #dailylook",
    },
    {
        "lane": "closet styling",
        "slot_family": ["02"],
        "setting": "organized closet area with neutral clothing shapes, soft rug, jewelry tray, no visible brand labels or text",
        "story": "Lena was choosing the last piece of the outfit before heading out.",
        "pose": "holding a jacket or small bag, hips angled, candid almost-laugh as if reacting to someone in the room",
        "camera": "vertical fashion-lifestyle portrait, full outfit visible, no mirror selfie, no screen",
        "caption": "changed my mind three times and this won #outfitcheck #ootd #styleinspo #softglam #dailylook #details",
    },
    {
        "lane": "home dance clip",
        "slot_family": ["03"],
        "setting": "Lena’s apartment living room with furniture pushed back, warm lamp, curtains, plant, clean wall, no screens, no text, no signage",
        "story": "Lena made a quick dance clip at home before posting later with music.",
        "pose": "full body ready to move, feet in frame, arms relaxed, confident playful expression",
        "camera": "vertical locked phone camera at chest height, full body visible, clean floor space",
        "caption": "saving this one for the right song #dancevibes #reels #dailyvibe #movement #softglam #homevibe",
        "video_motion": "10-second smooth social dance: step-touch footwork, shoulder accents, small hip pop, hair movement, playful hand gesture near face, clean ending pose. Music must be selected before publishing.",
    },
    {
        "lane": "museum quiet corner",
        "slot_family": ["04"],
        "setting": "quiet museum-like interior corner with plain textured wall, soft bench, abstract art shapes with no signatures, labels, plaques, or readable text",
        "story": "Lena found a quiet corner during an afternoon museum visit.",
        "pose": "standing with arms relaxed, chin slightly turned, thoughtful off-camera look",
        "camera": "vertical candid portrait, calm composition, no visible signage or wall labels",
        "caption": "came for the quiet #museumday #cityvibe #lifestyle #softglam #quietmoments #afternoon",
    },
    {
        "lane": "coffee walk",
        "slot_family": ["04"],
        "setting": "quiet tree-lined sidewalk or courtyard with blurred city background, no storefront signs, no license plates, no posters, no readable objects",
        "story": "Lena took a quick photo during a coffee walk.",
        "pose": "walking slowly with a plain unbranded cup, soft smile, coat or cardigan moving naturally",
        "camera": "vertical candid street-style photo with background safely blurred",
        "caption": "tiny walk fixed everything #coffeewalk #citystyle #lifestyle #dailyvibe #softlife #ootd",
    },
    {
        "lane": "simple dinner at home",
        "slot_family": ["05"],
        "setting": "small home kitchen or dining corner with warm light, simple plate, glass of water, linen napkin, no packaging, no bottle labels, no appliance screens",
        "story": "Lena made a simple dinner at home and took a warm evening photo.",
        "pose": "leaning against the counter or sitting at the small table, relaxed smile, one hand near plate or glass",
        "camera": "vertical warm lifestyle photo, realistic indoor light, intimate camera-roll feeling",
        "caption": "made dinner and called it a personality trait #homecooking #eveningvibe #softlife #lifestyle #cozyhome #dailyvibe",
    },
    {
        "lane": "evening skincare",
        "slot_family": ["05"],
        "setting": "bathroom vanity or bedroom dresser with warm clean light, plain bottles turned away or hidden, no labels, no mirror text, no phone UI",
        "story": "Lena ended the day with a quiet skincare moment.",
        "pose": "upper-body candid with hair clipped back, gentle smile, hand near cheek or holding a plain towel",
        "camera": "vertical intimate camera-roll portrait, soft realistic skin texture, no mirror selfie UI",
        "caption": "night routine doing the heavy lifting #skincarevibes #nightroutine #softlife #glow #eveningvibe #selfcare",
    },
 {
        "lane": "herby outdoor walk",
        "slot_family": ["01", "04"],
        "setting": "quiet tree-lined sidewalk or park path, soft natural light, no storefronts, no signage, no visible text anywhere, green foliage in background",
        "story": "Lena took Herby for a walk and someone caught a candid of the two of them.",
        "pose": "Lena walking or crouching beside Herby, leash relaxed in one hand, laughing softly or looking down at him with genuine affection",
        "camera": "vertical candid lifestyle photo, daylight, background path or greenery naturally blurred",
        "caption": "his walk his rules #herby #dogmom #dailywalk #fitlife #softlife #doglife",
    },
    {
        "lane": "bedroom getting ready",
        "slot_family": ["01", "02", "05"],
        "setting": "bedroom or walk-in closet, warm light, outfit visible on rack or chair, no labels, no readable text",
        "story": "Lena was mid-getting-ready and caught a quick photo before heading out.",
        "pose": "three-quarter body visible, adjusting outfit or earring, candid semi-posed expression, natural getting-ready energy",
        "camera": "vertical lifestyle portrait, warm bedroom light, realistic camera-roll energy",
        "caption": "in my getting ready era #gettingready #outfitcheck #ootd #morningvibe #softlife",
    },
    {
        "lane": "night out getting ready",
        "slot_family": ["02", "05"],
        "setting": "bedroom or bathroom vanity with warm evening light, mirror partially visible but no reflective text or UI, clean surfaces, no labels",
        "story": "Lena was getting ready to go out for the night and caught a quick photo mid-routine.",
        "pose": "side-profile or three-quarter turn, hair half-done or jewelry being put on, focused expression in a natural unposed moment",
        "camera": "vertical candid portrait, warm bathroom or bedroom light, intimate camera-roll energy",
        "caption": "almost ready #nightout #gettingready #softglam #outfitcheck #eveningvibes",
    },
    {
        "lane": "night out candid",
        "slot_family": ["04", "05"],
        "setting": "outdoor city scene at night or dim ambient indoor venue, background lights naturally out of focus, no readable signage, no visible bottles, no explicit content",
        "story": "Lena was out for the night and someone caught a genuine candid moment between places.",
        "pose": "walking, laughing, or looking slightly away from camera, confident body language, nighttime outfit and makeup",
        "camera": "vertical candid night photo, ambient low light, background naturally blurred, phone camera-roll energy",
        "caption": "good night good people #nightout #citynight #lifestyle #softglam #socialvibes",
    },
    {
        "lane": "cosplay creative look",
        "slot_family": ["02", "03", "04"],
        "setting": "clean neutral background or styled apartment space, no competing set dressing, no readable text or labels, focus entirely on the look",
        "story": "Lena shot a cosplay or themed creative look at home as a creator fashion moment.",
        "pose": "full outfit visible, confident character energy, styled pose that fits the look without being over-theatrical",
        "camera": "vertical portrait or full-body, clean framing, intentional creative lighting or natural window light",
        "caption": "she had a vision #cosplay #creativelook #ootd #creatorcontent #styleinspo",
    },
    {
        "lane": "bold outfit moment",
        "slot_family": ["02", "04"],
        "setting": "clean apartment wall or outdoor city backdrop with background safely blurred, no readable signage, no text anywhere",
        "story": "Lena wore something bold today and it needed a photo.",
        "pose": "full outfit visible, confident stance, small natural smile or direct-to-camera energy, one hand on hip or relaxed at side",
        "camera": "vertical full-body phone photo, clean framing, slight natural tilt for fashion-forward energy",
        "caption": "wore this and felt like the main character #boldoutfit #ootd #fashionmoment #softglam #outfitcheck",
    },
    {
        "lane": "gaming desk night",
        "slot_family": ["04", "05"],
        "setting": "Lena's gaming desk with warm lamp, monitor off or screen angled away, headset nearby, cozy low light, no visible UI or screen text",
        "story": "Lena settled in for a gaming or cozy creator night and took a quick photo.",
        "pose": "sitting at desk in relaxed position, headset on or resting around neck, soft expression, comfortable casual fit",
        "camera": "vertical intimate camera-roll portrait, warm desk lamp light, cozy background energy",
        "caption": "tonight's agenda #gamingnight #cozycreator #homevibe #softlife #gamergirl",
    },
    {
        "lane": "outdoor park walk",
        "slot_family": ["01", "04"],
        "setting": "open park path or grassy area, natural daylight, trees and greenery in background, no storefronts, no signage, no readable text anywhere",
        "story": "Lena went for a walk to clear her head and caught a candid outdoor moment.",
        "pose": "walking naturally or pausing mid-step, relaxed expression, casual outfit moving naturally",
        "camera": "vertical candid lifestyle photo, soft natural light, background greenery slightly out of focus",
        "caption": "needed this walk more than I knew #outdoors #parkday #softlife #citybreak #dailyvibe",
    },
    {
        "lane": "main character moment",
        "slot_family": ["02", "04"],
        "setting": "eye-catching outdoor or indoor scene with strong natural light, background cleanly blurred or composed, no readable text or signage",
        "story": "Lena was just living her life and the moment happened to look like a movie still.",
        "pose": "walking or standing with natural confidence, candid or barely-aware-of-the-camera energy, hair and outfit moving naturally",
        "camera": "vertical candid portrait or street-style shot, slightly editorial but still camera-roll believable",
        "caption": "main character behavior #maincharacter #lifestyle #ootd #softglam #dailyvibe",
    },
    {
        "lane": "low-energy honest day",
        "slot_family": ["01", "05"],
        "setting": "apartment couch or bedroom, soft low light, blanket visible, simple lived-in surfaces, no labels, no screens visible",
        "story": "Lena had a slow day and posted a genuinely real unproduced moment from it.",
        "pose": "sitting or half-lying on the couch, legs tucked up, candid relaxed expression, minimal makeup, comfortable loungewear",
        "camera": "vertical intimate camera-roll portrait, low warm light, slightly imperfect framing that reads as authentic",
        "caption": "not every day is a vibe and that is also fine #lowkey #honestday #softlife #cozyhome #reellife",
    },
    {
        "lane": "street errands baddie",
        "slot_family": ["04"],
        "setting": "quiet tree-lined sidewalk or plain urban backdrop, background safely blurred, no readable signs, no license plates",
        "story": "Lena was on errands and the outfit and light were too good not to stop for a photo.",
        "pose": "standing or mid-step, full outfit visible, confident casual stance, slight body angle",
        "camera": "vertical candid street-style photo, background blurred, phone-camera realism",
        "caption": "errands then what #ootd #streetstyle #citystyle #baddiecheck #dailylook",
    },
    {
        "lane": "parked car style",
        "slot_family": ["04"],
        "setting": "passenger seat or driver seat of parked car, neutral interior, soft window light, car is stationary",
        "story": "Lena caught a quick photo in the parked car before heading in.",
        "pose": "seated facing camera, face and upper body visible, confident relaxed expression",
        "camera": "vertical close-medium portrait, soft window light from one side, natural car-interior framing",
        "caption": "running errands looking like this #carselfie #ootd #baddie #dailylook",
    },
    {
        "lane": "looks expensive isn't",
        "slot_family": ["02", "04"],
        "setting": "clean apartment entryway or outdoor plain neutral backdrop, soft daylight, no visible labels or logos",
        "story": "Lena styled a look that reads expensive and had to capture it before walking out.",
        "pose": "full body or three-quarter, slight body angle, one hand touching outfit detail, confident direct expression",
        "camera": "vertical full-body portrait, soft daylight, intentional off-center framing",
        "caption": "looks expensive, isn't 💛 #looksexpensive #affordablestyle #ootd #fitcheck #stylingtips",
    },
    {
        "lane": "gym-to-glam reset",
        "slot_family": ["03", "04"],
        "setting": "gym near plain wall OR clean bedroom post-gym, no logos, no screens, transition lighting",
        "story": "Lena went from gym straight into glam and caught the transition energy.",
        "pose": "athletic body-forward stance with post-workout glow, OR getting-ready close-up mid-soft-glam",
        "camera": "vertical body portrait, realistic gym or bedroom light, candid confident energy",
        "caption": "gym then glam. that's the routine. 💪✨ #gymtoglam #postworkout #fitcheck #grwm #fitnessgirl",
    },
    {
        "lane": "pretty girl discipline",
        "slot_family": ["01", "02"],
        "setting": "gym wall, apartment vanity, or clean outdoor sidewalk — wherever the routine happens",
        "story": "Lena showed up for her routine today — gym, skincare, or a reset — and looked this good doing it.",
        "pose": "calm purposeful athletic or beauty pose, confident quiet expression, no over-performance",
        "camera": "vertical candid lifestyle portrait, realistic scene light, calm confident energy",
        "caption": "pretty girl discipline is real and it's quiet 🤍 #prettygirldiscipline #routine #selfcare #fitcheck",
    },
    {
        "lane": "soft glam routine",
        "slot_family": ["01", "05"],
        "setting": "bedroom vanity or bathroom counter, warm soft light, compact mirror nearby, no readable labels",
        "story": "Lena caught a beauty routine moment — a lip combo, skincare step, or soft glam application — that looked too good not to post.",
        "pose": "close-medium portrait, fingers near lips or cheek, glossy lip, glowing skin texture, warm beauty energy",
        "camera": "vertical close-medium beauty portrait, warm vanity or lamp light, real skin texture visible",
        "caption": "this lip combo has no business 💋 #softglam #lipcombos #beautycheck #glowup #makeuptips",
    },
    {
        "lane": "save vs splurge look",
        "slot_family": ["02", "04"],
        "setting": "clean apartment entryway or outdoor neutral backdrop, consistent background, soft daylight",
        "story": "Lena put together a polished look that achieves luxury energy without the price and had to share it.",
        "pose": "full body or three-quarter portrait, confident polished stance, slight body angle, expression sells the look",
        "camera": "vertical full-body portrait, clean light, editorial-casual confidence",
        "caption": "save vs splurge and the save wins 💛 #savevssplurge #affordableluxury #ootd #looksexpensive",
    },
]


SCENARIO_WARDROBE_HINTS: dict[str, str] = {
    "gym athletic photo":     "Gym: sports bra or crop top + leggings or bike shorts. Athletic and body-forward.",
    "cafe casual hang":       "Cafe: fitted top + jeans or mini skirt. Sneakers or sandals. Casual daytime.",
    "mirror fit check":       "Anything: full outfit readable in mirror. Fitted and body-aware — the photo is the fit check.",
    "morning window coffee":  "Home morning: fitted tank, off-shoulder knit, or fitted lounge set. Body-aware, relaxed.",
    "apartment reset":        "Home: fitted tank or off-shoulder knit + fitted shorts or soft pants. Attractive but relaxed.",
    "bedroom getting ready":  "Getting-ready: outfit mid-assembly or final look. Fitted and intentional. Warm bedroom light.",
    "coffee walk":            "Outdoor casual: fitted crop jacket + jeans or mini skirt. Sneakers or ankle boots.",
    "street errands baddie":  "Street: fitted crop top + jeans, mini skirt, or fitted cargo pants. Sneakers or slides.",
    "parked car style":       "Car: whatever she was wearing out. Outfit still visible in car framing.",
    "simple dinner at home":  "Home evening: fitted tank or off-shoulder top + fitted lounge bottoms. Body-aware casual.",
    "evening skincare":       "Nighttime routine: fitted tank or off-shoulder top. Hair clipped back naturally.",
    "herby outdoor walk":     "Outdoor: fitted crop jacket + jeans or mini, sneakers. Casual influencer park look.",
    "night out getting ready":"Night-out prep: mini dress or bodysuit + mini skirt mid-routine. Soft glam, heeled boots.",
    "night out candid":       "Night-out: fitted mini dress, satin cami, or bodysuit + mini skirt. Confident nighttime styling.",
    "outdoor park walk":      "Park: fitted crop jacket or long-sleeve + jeans or leggings. Sneakers or ankle boots.",
    "low-energy honest day":  "Cozy: fitted tank or off-shoulder top + fitted shorts. Real but still appealing.",
    "gaming desk night":      "Creator night: fitted tank or crop top + comfortable bottoms. Casual-cute.",
    "museum quiet corner":    "Cultural outing: fitted knit + slim jeans or midi skirt. Elevated casual, soft glam.",
    "home dance clip":        "Dance: fitted top or bodysuit + fitted bottoms that move well. Confident full-body energy.",
    "bold outfit moment":     "Bold look: full outfit visible at its most confident. Styled to stop the scroll.",
    "main character moment":  "Main character: confident posture, outfit shown fully, natural magnetism.",
    "outfit before errands":  "Errands: full outfit visible, casual influencer chic. Put-together but relaxed.",
    "closet styling":         "Styling: outfit visible mid-process. Confident casual energy.",
    "looks expensive isn't":  "Polished outfit that reads expensive: structured top, fitted trousers or mini, sleek low heel or flat, one minimal accessory. No visible logos. Neutral or earth-tone palette.",
    "gym-to-glam reset":     "Gym: fitted sports bra + high-waist leggings, gold hoops, post-workout glow. Post-gym: soft glam with glossy lip, fitted casual look.",
    "pretty girl discipline": "Athletic set at the gym OR polished soft glam getting-ready look. Intentional, minimal, fitted.",
    "soft glam routine":      "Face-forward: polished soft glam, glowing skin, glossy lip, small gold jewelry. One unbranded beauty product in hand.",
    "save vs splurge look":   "Polished outfit achieving luxury look: fitted silhouette, one elevated accessory, clean styling. No visible logos.",
}


def load_memory() -> dict:
    if MEMORY_PATH.exists():
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"recent": []}


def save_memory(memory: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_life_bible(memory: dict) -> dict:
    changed = False
    if "life_bible" not in memory or not isinstance(memory.get("life_bible"), dict):
        memory["life_bible"] = DEFAULT_LIFE_BIBLE.copy()
        changed = True
    else:
        bible = memory["life_bible"]
        # Always sync code-managed keys so CD edits take effect without manual cache clearing
        for k in ("style", "things_she_would_never_do", "autonomy_rules", "slot_purpose", "things_she_does"):
            if bible.get(k) != DEFAULT_LIFE_BIBLE.get(k):
                bible[k] = DEFAULT_LIFE_BIBLE[k]
                changed = True
        for k, v in DEFAULT_LIFE_BIBLE.items():
            if k not in bible:
                bible[k] = v
                changed = True
    if changed:
        save_memory(memory)
    return memory["life_bible"]


def clean_public_text(text: str) -> str:
    out = text or ""
    for term in BANNED_PUBLIC_TERMS:
        if term == "a.i.":
            pattern = r"(?<![A-Za-z0-9])a\s*\.\s*i\s*\.?(?![A-Za-z0-9])"
        else:
            pattern = r"(?<![A-Za-z0-9])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9])"
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def stable_index(key: str, length: int) -> int:
    if length <= 0:
        return 0
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16) % length


def slot_num(slot: dict) -> str:
    """
    Parse slot number from IDs like:
    2026-06-10-01-photo
    2026-06-10-03-video

    Important: do NOT capture month/day. The slot is the fourth dash-separated piece.
    """
    slot_id = str(slot.get("slot_id") or "")

    m = re.match(r"^\d{4}-\d{2}-\d{2}-(\d{2})-", slot_id)
    if m:
        return m.group(1)

    parts = slot_id.split("-")
    if len(parts) >= 5 and parts[3].isdigit():
        return parts[3].zfill(2)

    return "00"


def media_type(slot: dict) -> str:
    return str(slot.get("media_type") or slot.get("type") or "").lower()


def recent_lanes(memory: dict, days_limit: int = 7) -> set[str]:
    lanes = set()
    for item in memory.get("recent", [])[-30:]:
        lane = str(item.get("lane") or "").strip().lower()
        if lane:
            lanes.add(lane)
    return lanes


def scenario_allowed_by_life_bible(scenario: dict, bible: dict) -> tuple[bool, str]:
    lane = scenario["lane"].lower()
    text = " ".join([scenario.get("setting", ""), scenario.get("story", ""), lane]).lower()

    never = " | ".join(bible.get("things_she_would_never_do", [])).lower()

    hard_bad = [
        "private jet", "mansion", "alcohol-focused", "office", "logo flex",
        "hotel with no story", "fake friends", "text-heavy",
    ]
    for bad in hard_bad:
        if bad in text:
            return False, f"blocked hard bad concept: {bad}"

    # Avoid risky settings unless they are deliberately made text-safe.
    if any(risky in text for risky in ["bookstore", "menu", "signage-heavy"]):
        return False, "blocked text-risk environment"

    return True, "allowed by Lena life bible"


def choose_scenario(slot: dict, memory: dict, used_lanes: set[str]) -> dict:
    """
    v1.2.8.1 hard human-life lane selector.

    This never crashes because autonomy needs a safe human-like fallback.
    It uses Lena memory to avoid recent repeats, but it does not let a thin memory file
    prevent valid daily content from being created.
    """
    sn = slot_num(slot)
    lane_map = {s["lane"].lower(): s for s in SCENARIOS}
    recent = recent_lanes(memory)

    # These are Lena-life lanes, not random scenes.
    # Every slot has a believable reason to exist in her day.

    slot_lanes = {
        "01": [
            "morning window coffee",
            "apartment reset",
            "mirror fit check",
            "bedroom getting ready",
            "herby outdoor walk",
            "outdoor park walk",
            "low-energy honest day",
            "pretty girl discipline",
            "soft glam routine",
        ],
        "02": [
            "outfit before errands",
            "closet styling",
            "bold outfit moment",
            "night out getting ready",
            "cosplay creative look",
            "main character moment",
            "looks expensive isn't",
            "save vs splurge look",
        ],
        "03": [
            "home dance clip",
            "cosplay creative look",
            "gym-to-glam reset",
        ],
        "04": [
            "coffee walk",
            "museum quiet corner",
            "apartment reset",
            "cafe casual hang",
            "gym athletic photo",
            "street errands baddie",
            "parked car style",
            "herby outdoor walk",
            "outdoor park walk",
            "night out candid",
            "gaming desk night",
            "cosplay creative look",
            "bold outfit moment",
            "main character moment",
            "looks expensive isn't",
            "gym-to-glam reset",
        ],
        "05": [
            "simple dinner at home",
            "evening skincare",
            "bedroom getting ready",
            "gaming desk night",
            "night out getting ready",
            "night out candid",
            "low-energy honest day",
            "soft glam routine"
        ],
    }



    candidates = []
    for lane in slot_lanes.get(sn, []):
        scenario = lane_map.get(lane.lower())
        if not scenario:
            continue

        lane_key = scenario["lane"].lower()
        score = 0

        # Same-day uniqueness matters most.
        if lane_key in used_lanes:
            score += 10000

        # Recent memory should influence, not paralyze.
        if lane_key in recent:
            score += 500

        # Stable tiny variation so future dates do not always choose the first option.
        score += stable_index(f"{slot.get('slot_id')}:{lane_key}:human-life", 50)

        candidates.append((score, scenario))

    # Safe fallback by slot if something in config is missing.
    if not candidates:
        fallback_by_slot = {
            "01": "morning window coffee",
            "02": "outfit before errands",
            "03": "home dance clip",
            "04": "coffee walk",
            "05": "simple dinner at home",
        }
        fallback = fallback_by_slot.get(sn, "apartment reset")
        scenario = lane_map.get(fallback) or SCENARIOS[0]
        used_lanes.add(scenario["lane"].lower())
        return scenario

    candidates.sort(key=lambda x: x[0])
    chosen = candidates[0][1]
    used_lanes.add(chosen["lane"].lower())
    return chosen


def choose_wardrobe(slot: dict, bible: dict) -> str:
    options = bible.get("style", {}).get("wardrobe") or DEFAULT_LIFE_BIBLE["style"]["wardrobe"]
    return options[stable_index(str(slot.get("slot_id")) + ":wardrobe", len(options))]


def build_photo_prompt(slot: dict, scenario: dict, bible: dict) -> tuple[str, str, dict]:
    lane = scenario.get("lane", "")
    lane_wardrobe = SCENARIO_WARDROBE_HINTS.get(lane)
    wardrobe = lane_wardrobe.rstrip(".") if lane_wardrobe else choose_wardrobe(slot, bible)
    scene_note = ""

    prompt = f"""
Create a scroll-stopping vertical photo of Lena — a hot human lifestyle influencer. She must look visually magnetic, curvy feminine, and real. The image must feel like a genuine candid from her day.

Identity:
Lena: consistent adult woman, same face/hair/skin/proportions every time. Use reference image for identity only — do not recreate its pose, outfit, background, lighting, or framing. Every output is a new moment, not a remake. Warm brunette/chestnut/auburn hair; no drastic color or style changes.

Why this photo exists:
{scenario["story"]}

Scene:
{scenario["setting"]}

Wardrobe:
{wardrobe}. Diverse public lifestyle wardrobe; always mouthwatering sexy, seductive, body-conscious, visually hooky, and platform-safe. Match Lena element reference; do not alter reference body proportions. Avoid timid, boxy, shapeless, bulky, high-waist-hiding, officewear, underwear/lingerie, nudity, explicit/fetish/crotch framing. Fabric: ribbed knit, seams, folds, tension, wrinkles. Accessories: earrings, jewelry, hair tie.{scene_note}

Element identity:
Preserve Lena's saved Kling element identity, face, hairstyle, body look, proportions, and character consistency. Do not redesign her. The Lena element is the visual source of truth.

Pose:
{scenario["pose"]}

Camera:
{scenario["camera"]}. Pulled-back 3/4 or full-body framing — not close portrait. Natural phone photo from Lena's real life.

Realism:
Lived-in place: phone, dish towel, cutting board, water glass, clutter, warm imperfect lighting — not a showroom. Lena mid-moment: setting dinner down, tasting sauce, laughing at a text. Preserve pores; avoid freckle clusters.

Distinctiveness:
Every slot must differ in story beat, pose, face angle, composition, lighting, and expression. No formula repeats. Lena feels naturally present. Expression candid and varied: playful smirk, mid-laugh, surprised smile, teasing side-eye, or warm grin. Never a neutral seed-reference face.

Physical realism:
Lena stands beside counters, not intersecting them. Clear body/furniture separation, natural shadows, correct depth.
""".strip()

    meta = {
        "creative_director_version": VERSION,
        "lane": scenario["lane"],
        "human_story": scenario["story"],
        "life_bible_used": True,
        "why_this_fits_lena": "chosen from Lena life memory and allowed-life rules",
        "wardrobe_direction": wardrobe,
        "negative_prompt": NEGATIVE_PROMPT,
        "visual_rejection_rules": VISUAL_BANS,
        "manual_review_required": True,
        "reject_if": [
            "any text, letters, numbers, logos, UI, symbols, or garbled marks appear",
            "scene feels fake, boring, or outside Lena's normal life",
            "wardrobe looks generic, or plain tank-top-and-jeans",
            "hands, face, body, or frame edges contain artifacts",
            "freckle-like spot clusters, heavy speckling, identity-changing freckle patterns, acne-like blotches, or dark facial spots appear on Lena's skin; natural skin texture, pores, subtle redness, and realistic facial detail are acceptable",
            "plastic skin, airbrushed skin, poreless CGI skin, or glossy fake hair appears",
            "the image appears to be a copy, remake, near-duplicate, or pose/background clone of a seed or reference image",
            "hair color or hairstyle changes so much that Lena no longer looks like the same person",
            "Herby or any dog dominates the frame unless the slot is explicitly a Herby-focused slot",
            "the Lena + Herby composition uses the same indoor apartment-floor close portrait or cuddle framing as previous reference-style images",
            "the asset feels like the same seed image reused or the same accepted image repeated with minor changes",
            "the same pose or composition formula appears across more than one slot in the batch",
            "Lena appears pasted into a scene rather than naturally photographed as part of the moment",
            "the image falls into the same pretty standing portrait formula as another slot without a distinct story, location, or mood difference",
            "outfit is a full suit, pantsuit, corporate blazer-and-trouser combination, business suit, or officewear",
            "styling is business-professional or looks like corporate officewear rather than creator or lifestyle",
            "Lena looks frumpy, overly covered, or sexless in a way that hides her physical appeal",
            "image is technically realistic but has no visual hook, no eye-catch, no scroll-stopping quality",
            "no flattering body silhouette or confident body language is visible",
            "image is safe-but-boring: generic stock-photo professionalism with no creator or lifestyle energy",
            "outfit hides Lena's appeal through shapeless coverage rather than tasteful framing",
            "body is hidden under shapeless, oversized, or heavily draped clothing with no visible feminine silhouette",
            "outfit hides Lena's waist, hips, or shape; no hourglass or feminine body line is visible",
            "Lena's curvy figure is not apparent — proportions look flat, boxy, or androgynous",
            "Lena looks too slim, skinny, or model-thin — body lacks the thick curvy hourglass shape: no visible waist definition, flat hips, or narrow lower body",
            "Lena's body proportions look obese, chubby, plus-size, cartoonish, anatomically distorted, or impossibly exaggerated",
            "body, cleavage, hip, thigh, or waist emphasis becomes explicit, crotch-focused, fetish-framed, nude, pornographic, or sexually graphic",
            "image contains explicit, fetish, nude, or pornographic framing",
            "daytime or morning scene features cheap clubwear or discount-looking styling, explicit nightout styling, or looks inappropriate for the scene context",
            "night-out scene features corporate, business-professional, or bland styling rather than attractive nightlife looks",
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
        ],
    }

    return clean_public_text(prompt), clean_public_text(scenario["caption"]), meta


def build_video_prompts(slot: dict, scenario: dict, bible: dict) -> tuple[str, str, str, dict]:
    wardrobe = choose_wardrobe(slot, bible)

    seed = f"""
Create a full-body vertical seed image of Lena preparing to record a short dance clip at home.

Human continuity:
Preserve Lena's identity from the private reference image: same face, body proportions, hair, skin tone, and recognizable presence.

Why this clip exists:
{scenario["story"]}

Scene:
{scenario["setting"]}

Wardrobe:
{wardrobe}. Movement-friendly, stylish, believable at home, not costume-like.

Pose:
{scenario["pose"]}. Full body visible, feet in frame, hands relaxed and anatomically correct.

Hard visual rejection rules:
{VISUAL_BANS[0]}
{VISUAL_BANS[1]}
{VISUAL_BANS[2]}
""".strip()

    motion = f"""
Create a 10-second vertical dance video of Lena from the seed image.

Motion:
{scenario.get("video_motion", "smooth casual dance with natural body rhythm and clean ending pose")}

Continuity:
Keep Lena's face, body, outfit, hair, jewelry, and setting stable. No face drift, no body warping, no flicker, no extra limbs.

Camera:
Locked vertical phone camera, full body visible the whole time, hands and feet stay inside frame, no UI overlays.

Publishing:
This clip requires music selection before publishing. Silent dance clips are not final social content.
""".strip()

    meta = {
        "creative_director_version": VERSION,
        "lane": scenario["lane"],
        "human_story": scenario["story"],
        "life_bible_used": True,
        "music_required_before_publish": True,
        "silent_auto_publish_allowed": False,
        "wardrobe_direction": wardrobe,
        "negative_prompt": NEGATIVE_PROMPT,
        "visual_rejection_rules": VISUAL_BANS,
        "manual_review_required": True,
    }
    return clean_public_text(seed), clean_public_text(motion), clean_public_text(scenario["caption"]), meta


def upgrade_manifest(path: Path) -> dict:
    memory = load_memory()
    bible = ensure_life_bible(memory)

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    used_lanes: set[str] = set()
    summaries = []

    for slot in data.get("slots", []):
        forced = slot.pop("forced_lane", None)
        if forced:
            _lane_map = {s["lane"].lower(): s for s in SCENARIOS}
            scenario = _lane_map.get(forced.lower()) or choose_scenario(slot, memory, used_lanes)
            used_lanes.add(scenario["lane"].lower())
        else:
            scenario = choose_scenario(slot, memory, used_lanes)
        mtype = media_type(slot)
        meta = slot.setdefault("metadata", {})

        if mtype == "video":
            seed, motion, caption, new_meta = build_video_prompts(slot, scenario, bible)
            slot["image_prompt"] = seed
            slot["video_prompt"] = motion
            slot["negative_prompt"] = NEGATIVE_PROMPT
            slot["caption"] = caption
            meta.update(new_meta)
            meta["image_prompt"] = seed
            meta["video_prompt"] = motion
            meta["caption"] = caption
            summaries.append({
                "slot_id": slot.get("slot_id"),
                "media_type": mtype,
                "lane": scenario["lane"],
                "seed_prompt_chars": len(seed),
                "video_prompt_chars": len(motion),
            })
        else:
            prompt, caption, new_meta = build_photo_prompt(slot, scenario, bible)
            slot["image_prompt"] = prompt
            slot["negative_prompt"] = NEGATIVE_PROMPT
            slot["caption"] = caption
            meta.update(new_meta)
            meta["image_prompt"] = prompt
            meta["caption"] = caption
            summaries.append({
                "slot_id": slot.get("slot_id"),
                "media_type": mtype,
                "lane": scenario["lane"],
                "prompt_chars": len(prompt),
            })

        meta["detail_level"] = VERSION
        meta["background_policy"] = "memory_aware_human_life_no_text_no_ui"
        meta["autonomous_human_life_director"] = True

    data["creative_director_version"] = VERSION
    data["prompt_detail_version"] = VERSION
    data["life_bible_used"] = True
    data["autonomy_policy"] = {
        "uses_lena_prompt_memory": True,
        "every_slot_unique_lane": True,
        "scenarios_must_fit_lena_life": True,
        "recent_memory_lanes_avoided_when_possible": True,
        "human_like_in_every_way": True,
        "manual_review_required_before_publish": True,
        "no_text_no_ui_no_jumble": True,
    }
    data["creative_director_updated_at_utc"] = datetime.now(timezone.utc).isoformat()

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "ok": True,
        "path": str(path),
        "creative_director_version": VERSION,
        "changed_slots": len(data.get("slots", [])),
        "recent_memory_lanes": sorted(recent_lanes(memory)),
        "summaries": summaries,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: lena_creative_director_v1_2_8.py <daily_workorders.json>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"missing file: {path}"}, indent=2))
        return 1

    print(json.dumps(upgrade_manifest(path), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
