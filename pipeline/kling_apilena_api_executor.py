from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.env_loader import load_env_once
from pipeline.lena_generation_signature import current_image_generation_signature
from pipeline.identity import lena_identity
from pipeline.reference_images.lena import apilena_reference_guard
from pipeline.prompting.lena_prompt_brain import (
    CORE_NEGATIVE_TERMS,
    STYLE_REALISM_NEGATIVE_TERMS,
    PUBLIC_SAFETY_NEGATIVE_TERMS,
    PUBLIC_LANE_SAFETY_TERMS,
    BODY_ANATOMY_NEGATIVE_TERMS,
    OUTFIT_SPECIFIC_SUBSTITUTION_TERMS,
)

load_env_once(ROOT)

WORKORDER_ROOT = ROOT / "pipeline" / "kling_workorders"
DEBUG_ROOT = ROOT / "pipeline" / "kling_debug" / "apilena_api"

API_BASE = os.environ.get("KLING_BASE_API_URL", "https://api.klingai.com").rstrip("/")
IMAGE_SUBMIT_URL = os.environ.get("KLING_IMAGE_API_URL", f"{API_BASE}/v1/images/generations")
IMAGE_MODEL_NAME = str(os.environ.get("KLING_IMAGE_MODEL_NAME", "")).strip()
# Reference-by-URL photo mode (Variant B, proven live 2026-07-07): condition on the
# APILENA reference image URL via image_list on the omni-image endpoint, no element_list.
OMNI_IMAGE_SUBMIT_URL = os.environ.get("KLING_OMNI_IMAGE_API_URL", f"{API_BASE}/v1/images/omni-image")
REFERENCE_IMAGE_MODEL_NAME = str(os.environ.get("KLING_REFERENCE_IMAGE_MODEL_NAME", "kling-v3-omni")).strip()
ELEMENTS_LIST_URL_TEMPLATE = str(
    os.environ.get(
        "KLING_ELEMENTS_LIST_URL_TEMPLATE",
        "https://kling.ai/api/elements"
        "?__NS_hxfalcon=HUDR_sFnX-FFuAW5VsfDNK0XOP6snthhLcvIxjxBz8_r61UvYFIc7AGaHwcmlb_Lw36QFxBn0Bj4EKN4Zb24e3VuXscYogNAE2VgjPwO2jii43de2oR63LL1hZW0okM8dUmYrH6VQSB7Y7ZSTIxoF0X7LUSWUr1pXnbkf6P4o8SqzzdFR6IIMKBvrgRoI4U6ivRMLenA12ccSYtqQsn85UO-V55wKLh87pmyfVY92xLhp0NmoDeVRSd7WLKYmDQ6daAjf2SWOQKAmtmaan4dMahw7O5IOYSTE-KEf1giGl3BVGkkxlPDAaIvA9ba31qDGPnaMwazeDrI_T_P6CnKicFIx-G2TUOy20_rwbOAD-8MlO4S1C5i2v0k8qzW-02lU9ktkBbSpasUP26JUG0vPlbaSMDesq9nzy7TO7_HdxPfHDdU2dsBVZFgK0CGNqxTHb-TzosJgwfG0wdcbT3ZozJSooclx33aamQmi_uuWqLz9CFHDsZtjpOgnKDSJ61it07gSbpetVYTfLGht7TbljxyRbVBl95krWPUOynEXDpjxFd4kyGEhSs5QcUXZKzuC8KuqoS6WWyd7FhPy6tRF-lNzMwpmduEOikZKg5JAOnjRHg-aWamPJY08wPyxL-2yLFi3W-2pFdZePSmNHWVKPKqSPP8raE0iIi3to6_2Vbsg6yhapqoKbBLJ7e3e1yIzu6ALf8JCNyMI932TJMfkdfPPqn0iYrf4ng8VGSMs5gLywGp0iuQ4UJ7gBQ..$HE_d5ca52373572dd0a53009fba19201e5b709f9e9e9e9ff90632248e4dbf2cfe46419b009f05c8a044e5c8a0769e"
        "&caver=2&official=false&pageNum={page_num}&pageSize=40&favored=false&sortDirection=DESC&dirParamId=&type=ALL"
    )
).strip()
ELEMENTS_LOOKUP_MAX_PAGES = int(os.environ.get("KLING_ELEMENTS_LOOKUP_MAX_PAGES", "3") or "3")
ELEMENTS_SEARCH_URL = str(
    os.environ.get(
        "KLING_ELEMENTS_SEARCH_URL",
        "https://kling.ai/api/elements/search"
        "?__NS_hxfalcon=HUDR_sFnX-FFuAW5VsfDNK0XOP6snthhLcvIxjxBz8_r61UvYFIc7AGaHwcmlb_Lw36QFxBn0Bj4EKN4Zb24e3VuXscYogNAE2VgjPwO2jii43de2oR63LL1hZW0okM8dUmYrH6VQSB7Y7ZSTIxoF0X7LUSWUr1pXnbkf6P4o8SqzzdFR6IIMKBvrgRoI4U6ivRMLenA12ccSYtqQsn85UO-V55wKLh87pmyfVY92xLhp0NmoDeVRSd7WLKYmDQ6daAjf2SWOQKAmtmaan4dMahw7O5IOYSTE-KEf1giGl3BVGkkxlPDAaIvA9ba31qDGPnaMwazeDrI_T_P6CnKicFIx-G2TUOy20_rwbOAD-8MlO4S1C5i2v0k8qzW-02lU9ktkBbSpasUP26JUG0vDlbaSMDesq9nzy7TO7_HdxPfHDdU2dsBVZFgK0CGNqxTHb-TzosJgwfG0wdcbT3ZozJSooclx33aamQmi_uuWqLz9CFHDsZtjpOgnKDSJ61it07gSbpetVYTfLGht7TbljxyRbVBl95krWPUOynEXDpjxFd4kyGEhSoNTcUXZKziC8KuqoS6WWyd7FhPy6tRF-v5zMwpmdugOikZKg5JAOnjRHg-aWamPJY08wPyxL-2yLFi3W-2pFdZePSmNHWVKPKqSPP8raE0iIi3to6_2Vbsg6yhapqoKbBLJ7e3e1yIzu6ALf8JCNyMI932TJMfkdfPPqn0iYrf4ng8VGSMs5gLywGp0J-Q4UJ7gBQ..$HE_908f177270538a631045dafbe857a86a0fdadbdbdbda11437761cc08fe39635629d845da408de501a08de533db"
        "&caver=2&type=ALL&belongType=USER&pcursor=1&pageSize=500&keyword="
    )
).strip()
ELEMENTS_SEARCH_KWW = str(
    os.environ.get(
        "KLING_ELEMENTS_SEARCH_KWW",
        "+/PIG9bS+90zD8/40D8eZA8nPIPn8Y+0cEGf8f+e8f8nPhG/LAG0clw/WFG0zYP0+f+/qhG9G7PAQY+fHU+0zD8eLEPArF+0cAP0DIPeWFP0L7w/bD+nGhGALhP0PIGAHhP9z0GAZFP/Ph+AH98/L9GADh+0DhG0ZMwnQD+/YYGfQY8erFGfPEP9GAPfGM+eP980Q0+0GUPBcAPAG7PnQYPZ==",
    )
).strip()
NEGATIVE_PROMPT = os.environ.get(
    "KLING_NEGATIVE_PROMPT",
    "low quality, blurry, distorted face, extra fingers, deformed hands, watermark, text overlay, identity drift",
)
# Batch 3 (2026-07-05): budgets for compacting the prompt-brain's already-built
# slot["image_prompt"] / slot["negative_prompt"] down to a size Kling will accept.
# 2499 matches the existing working assumption already used elsewhere in this repo
# (tools/strategy/lena_build_content_packet_dryrun_v1.py's build_structured_kling_prompt).
PROMPT_MAX_CHARS = int(os.environ.get("CONTENT_BOT_KLING_PROMPT_MAX_CHARS", "2499") or "2499")
NEGATIVE_PROMPT_MAX_CHARS = int(os.environ.get("CONTENT_BOT_KLING_NEGATIVE_PROMPT_MAX_CHARS", "2499") or "2499")
POLL_INTERVAL_SECONDS = int(os.environ.get("CONTENT_BOT_KLING_POLL_INTERVAL_SECONDS", "6") or "6")
POLL_TIMEOUT_SECONDS = int(os.environ.get("CONTENT_BOT_KLING_POLL_TIMEOUT_SECONDS", "600") or "600")
LIVE_LENA_UI_ID = str(os.environ.get(lena_identity.EXPECTED_PHOTO_ELEMENT_ENV_VAR, "")).strip()
LIVE_LENA_NAME = lena_identity.expected_photo_element_name()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _trim_text(value: str, max_chars: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].strip()
    return clipped or text[:max_chars]


def _extract_labeled_section(text: str, label: str, next_labels: Iterable[str]) -> str:
    source = str(text or "")
    pattern = re.compile(re.escape(label) + r"\s*(.+?)(?=" + "|".join(re.escape(item) for item in next_labels) + r"|$)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(source)
    if not match:
        return ""
    return " ".join(match.group(1).split()).strip(" .")


def _slot_metadata(slot: Dict[str, Any]) -> Dict[str, Any]:
    metadata = slot.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


# Batch 3 (2026-07-05): sentence-level keyword groups used to decide which clauses
# of the prompt-brain's already-built slot["image_prompt"] must survive compaction.
# This does not re-derive wardrobe/continuity/identity logic -- that logic already
# ran in pipeline/prompting/lena_prompt_brain.py at workorder-prep time and produced
# the text these keywords are scanning. This only decides what to keep vs. trim.
_SAFETY_KEYWORD_GROUPS: Dict[str, tuple] = {
    "wardrobe_selection": ("wardrobe override", "use this catalog outfit"),
    "identity": ("identity", "current lena", "current approved", "approved character element", "same recognizable woman"),
    "eye_color": ("eye color", "eyes must stay", "iris", "hazel", "amber"),
    "skin_no_freckle": ("freckle", "mole", "beauty mark", "pore-dot", "pore dot", "beauty-filter", "beauty filter"),
    # Batch 5d (2026-07-06): bare "crop" removed -- it matched "Do not crop awkwardly
    # through hands or face" (a camera-framing instruction) as a false positive,
    # letting wardrobe_continuity_present read true with zero real continuity content
    # surviving. Replaced with the actual multi-word garment/continuity phrases the
    # source prompt uses ("crop top", "cropped tank", "crop gap", "floating hem",
    # "two real separate garments", "full-length to the waistband", etc.) so this group
    # can only be satisfied by genuine continuity-lock language.
    "wardrobe_continuity": (
        "continuity lock", "tucked", "waistband", "underbust", "bodysuit", "one-piece",
        "torso fabric", "crop top", "cropped tank", "crop gap", "bra top", "bra-band",
        "two-piece", "two real separate garments", "underwear", "lingerie",
        "underlayer", "outerwear", "floating hem", "floating high above",
        "full-length to the waistband", "named hem length",
    ),
    "public_scene_lock": ("public-scene lock", "selfie", "phone held", "front-camera"),
    "hands": ("hands", "finger", "knuckle", "thumb", "wrist"),
    "body_shape": ("hip", "pelvis", "thigh", "waist", "silhouette", "hourglass"),
    # Batch 5 (2026-07-06): added after the 2026-07-06 proof render showed the source
    # prompt's Scene:/Environment:/Lighting: language (confirmed present in
    # slot["image_prompt"]) was being dropped entirely under a tight budget, producing
    # a plain-background render with no specified setting. These are the literal
    # section-label markers pipeline/prompting/lena_prompt_brain.py already writes.
    "scene_environment": (
        "scene:", "environment:", "small details:", "camera and composition",
        "capture source", "lighting:",
    ),
}

# Priority order for which category gets first claim on the char budget. Explicitly
# named in the Batch 3 containment scope: identity/eye_color (base identity),
# skin_no_freckle (no-invented-freckles policy), wardrobe_continuity (public-scene
# wardrobe continuity + outerwear-underlayer). scene_environment sits right after
# those so the specified setting can no longer be silently sacrificed, while still
# yielding to the explicitly-mandated safety categories above it. body_shape stays
# last because its source language is the most verbose (LENA_MASTER_IDENTITY) and
# would otherwise crowd out shorter categories under a tight budget.
_SAFETY_KEYWORD_PRIORITY = (
    "wardrobe_selection",
    "identity",
    "eye_color",
    "skin_no_freckle",
    "wardrobe_continuity",
    "scene_environment",
    "public_scene_lock",
    "hands",
    "body_shape",
)

# Batch 5b (2026-07-06): a real proof render showed the priority reorder above was
# not sufficient -- wardrobe_selection/identity/eye_color/skin_no_freckle/
# wardrobe_continuity alone already consumed nearly the entire 2499-char budget for
# a verbose slot, leaving no room for Scene:/Environment: content regardless of where
# scene_environment sits in the priority order. A first fix reserved a 600-char floor
# for both Scene: and Environment:, which fixed the framing failure but starved
# wardrobe_continuity entirely (confirmed by functional test).
#
# Batch 5c (2026-07-06): narrowed further -- the floor now covers only Scene: (the
# single most essential scene anchor, ~153 chars for the slot that exposed this bug),
# sized to 200 chars for headroom on slightly longer Scene: sentences elsewhere.
# Environment: is back in the normal scene_environment priority pass, unchanged,
# alongside Lighting:/Small details:/Camera and composition:/Capture source:. File-local
# constant only, no env override, per scope. The 2499 PROMPT_MAX_CHARS cap is unchanged.
_SCENE_FLOOR_KEYWORDS = ("scene:",)
SCENE_FLOOR_CHARS = 200

# Batch 5d (2026-07-06): with the Scene: floor in place, wardrobe_continuity_present
# was discovered to be a false positive (matched "Do not crop awkwardly through hands
# or face" via a bare "crop" keyword, not real continuity content). Fixed by removing
# "crop" from _SAFETY_KEYWORD_GROUPS["wardrobe_continuity"] and replacing it with
# specific multi-word phrases. Once trustworthy, the signal showed continuity was
# truly absent -- the real continuity sentences no longer fit under the tighter
# budget after the Scene: floor was added.
#
# Batch 5e (2026-07-06): a second, separate, equally narrow reserved floor -- covers
# only the single shortest essential continuity-lock sentence ("Skirt-set continuity
# lock: keep the named top and skirt as two real separate garments.", 86 chars).
# "continuity lock" is precise: verified to match only that one sentence in this
# slot's source prompt. File-local constant, no env override. Does not touch the
# Scene: floor, PROMPT_MAX_CHARS, or identity logic.
_CONTINUITY_FLOOR_KEYWORDS = ("continuity lock",)
CONTINUITY_FLOOR_CHARS = 110

# Batch 6 (2026-07-06): a full_body proof render on a different slot (same outfit,
# different framing) showed the source prompt's framing directive -- "Framing should
# clearly show her full silhouette, outfit fit, waist-to-hip shape, legs, posture,
# hands, and shoes when the scene allows." (135 chars) -- was not surviving
# compaction, leaving the render cropped to a bust shot despite full_body reference
# mode. It only matched the lowest-priority body_shape group (via the substring
# "waist" in "waist-to-hip") and lost the budget competition. A third, separate,
# equally narrow reserved floor. "framing should" is precise: it is the literal
# opening of this one sentence type, not a broad body-shape keyword like "waist".
_FRAMING_FLOOR_KEYWORDS = ("framing should",)
FRAMING_FLOOR_CHARS = 160

# Batch 7 (2026-07-06): two consecutive same-slot proof renders substituted a
# different, unrelated covering garment (trench+scarf, then a turtleneck sweater) for
# the specified sleeveless tank top, despite a verified-correct submitted prompt both
# times -- recurring generation-model non-compliance, not a compaction bug. The fix
# lives upstream in pipeline/prompting/lena_prompt_brain.py (a new
# "Garment-obedience lock:" sentence, silhouette-class-scoped to sleeveless-top +
# skirt outfits). This fourth reserved floor guarantees that new sentence survives
# compaction the same way Scene:/continuity/framing already do. "garment-obedience
# lock" is precise -- the literal opening of this one sentence, written as a single
# self-contained sentence upstream specifically so one floor keyword captures the
# whole prohibition list, not just the opening clause.
_GARMENT_OBEDIENCE_FLOOR_KEYWORDS = ("garment-obedience lock",)
GARMENT_OBEDIENCE_FLOOR_CHARS = 300

# Frame-logic floor (2026-07-07): pipeline/prompting/lena_prompt_brain.py now inserts
# a "Frame logic:" paragraph (frame_action, supporting/forbidden objects, camera
# intent, body-visibility rule, coherence note) right after the Scene: sentence, so
# every render is a specific believable moment instead of just "Lena in a place."
# Unlike the single-sentence Garment-obedience lock above, this paragraph is written
# as several short sentences (one per labeled clause), so one keyword cannot capture
# the whole thing the way "garment-obedience lock" does -- each clause needs its own
# matching keyword in the tuple. Split into two floors, same narrow/additive style as
# every floor above, so the two hard-requirement clauses (the action beat itself, and
# the forbidden-object list that keeps alcohol/props non-focal) get first claim on
# their budget ahead of the three supporting/quality clauses, rather than losing out
# to them by pure source-order accident (the compactor otherwise walks sentences in
# original order, and "Avoid:" sits after "Supporting objects"/"Camera intent"/"Body
# visibility" in the source text).
_FRAME_LOGIC_ACTION_FORBIDDEN_FLOOR_KEYWORDS = ("frame logic:", "avoid:")
FRAME_LOGIC_ACTION_FORBIDDEN_FLOOR_CHARS = 450

# Second, lower-priority floor for the remaining frame-logic clauses (supporting
# objects, camera intent, body-visibility rule -- including its seated/table-
# occlusion note when present -- and the closing coherence note). Applied after the
# floor above so it only claims budget left over from the two hard-requirement
# clauses first.
_FRAME_LOGIC_SUPPORT_FLOOR_KEYWORDS = (
    "supporting objects in frame:",
    "camera intent:",
    "body visibility:",
    "this scene is seated or leaning at furniture",
    "do not add any extra prop beyond that furniture",
    "this should read as",
)
FRAME_LOGIC_SUPPORT_FLOOR_CHARS = 650

# Expression/gaze floor (2026-07-07): pipeline/prompting/lena_prompt_brain.py's
# expression/gaze diversity layer inserts one short "Expression: ..." sentence
# right after EXPRESSION_REALISM, so nearby renders don't all share the same facial
# performance. A real 200-slot survival test showed it was dropped in 200/200 cases
# under the real 2499-char cap (and 198/200 even before the frame-logic floors above
# existed) -- it has never had a reserved floor, unlike every other labeled prompt
# section. "expression:" is precise: verified to match only this one sentence type
# (case-insensitive; the pre-existing EXPRESSION_REALISM constant's own text never
# contains a bare "expression:" with a trailing colon). All 15 current bank entries
# measure 74-125 chars; 180 gives comfortable margin for future entries without
# reserving more budget than needed.
_EXPRESSION_GAZE_FLOOR_KEYWORDS = ("expression:",)
EXPRESSION_GAZE_FLOOR_CHARS = 180

# Batch 7b (2026-07-06): the positive garment-obedience lock above has a reserved
# floor and survives; a same-order reorder of these matching anti-substitution
# negative terms did not help (a real functional test showed zero present in the
# compact negative prompt) -- the base NEGATIVE_PROMPT constant alone (2734 chars)
# already exceeds NEGATIVE_PROMPT_MAX_CHARS, so source-order position never mattered.
#
# Batch 7c (2026-07-06): this tuple is now also used by
# _build_compact_negative_prompt() as a genuine reserved floor (see
# NEGATIVE_GARMENT_OBEDIENCE_FLOOR_CHARS below), not just a receipt-verification list.
_GARMENT_OBEDIENCE_NEGATIVE_TERMS = (
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
)
# All 11 terms joined total 350 chars; 380 gives small margin without eating much of
# the 2499-char negative budget (~15%).
NEGATIVE_GARMENT_OBEDIENCE_FLOOR_CHARS = 380

# Negative-prompt budget repair (2026-07-06). The base NEGATIVE_PROMPT constant
# alone (2696 chars after pipeline/prompting/lena_prompt_brain.py's tiering pass)
# still exceeds NEGATIVE_PROMPT_MAX_CHARS (2499), so first-N-fit order still gives
# no guarantee to anything outside the one existing garment-obedience floor above.
# These six additional reserved floors extend the exact same mechanism -- narrow,
# additive, matched on precise term sets imported directly from lena_prompt_brain.py
# (not re-typed here, to avoid the drift risk a second hand-copied list would add) --
# to the remaining protection classes identified in the 2026-07-06 budget-repair
# design memo. Applied strictly after the existing garment-obedience floor so that
# floor's available budget (and its proven 11/11 survival behavior) is completely
# unchanged by this addition.
CORE_NEGATIVE_FLOOR_CHARS = 350
STYLE_REALISM_FLOOR_CHARS = 550
PUBLIC_SAFETY_FLOOR_CHARS = 450
OUTFIT_SPECIFIC_SUBSTITUTION_FLOOR_CHARS = 400
BODY_ANATOMY_FLOOR_CHARS = 750

_CORE_NEGATIVE_TERMS_LOWER = {t.lower() for t in CORE_NEGATIVE_TERMS}
_STYLE_REALISM_TERMS_LOWER = {t.lower() for t in STYLE_REALISM_NEGATIVE_TERMS}
_PUBLIC_SAFETY_TERMS_LOWER = {t.lower() for t in (PUBLIC_SAFETY_NEGATIVE_TERMS + PUBLIC_LANE_SAFETY_TERMS)}
_BODY_ANATOMY_TERMS_LOWER = {t.lower() for t in BODY_ANATOMY_NEGATIVE_TERMS}
_OUTFIT_SPECIFIC_SUBSTITUTION_TERMS_LOWER = {t.lower() for t in OUTFIT_SPECIFIC_SUBSTITUTION_TERMS}


def _split_sentences(text: str) -> list[str]:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _dedupe_terms(terms: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(term.strip())
    return deduped


def _build_compact_prompt(slot: Dict[str, Any]) -> str:
    """Compact the prompt-brain's already-built slot prompt down to PROMPT_MAX_CHARS.
    Selection is priority-tiered by safety category (see _SAFETY_KEYWORD_PRIORITY) so a
    verbose category (e.g. body-shape language) cannot crowd out a shorter, explicitly
    mandated one (e.g. the no-invented-freckles policy) before descriptive filler is
    considered. Final assembly restores original sentence order for readability. Does
    not rebuild a parallel prompt from raw metadata fields -- source of truth is
    slot["image_prompt"]."""
    source_prompt = str(
        slot.get("image_prompt") or slot.get("positive_prompt") or slot.get("prompt") or ""
    ).strip()
    if not source_prompt:
        raise RuntimeError(
            f"slot {slot.get('slot_id')!r} has no image_prompt from the prompt-brain "
            "workorder-prep step. Refusing to fall back to a generic rebuilt prompt."
        )

    sentences = _split_sentences(source_prompt)
    sentence_groups = [
        {group for group, kws in _SAFETY_KEYWORD_GROUPS.items() if any(kw in sentence.lower() for kw in kws)}
        for sentence in sentences
    ]

    kept_indices: set[int] = set()
    overrides: Dict[int, str] = {}
    total_len = 0

    def _try_add(idx: int) -> None:
        nonlocal total_len
        if idx in kept_indices:
            return
        added_len = len(sentences[idx]) + (1 if kept_indices else 0)
        if total_len + added_len <= PROMPT_MAX_CHARS:
            kept_indices.add(idx)
            total_len += added_len

    def _apply_reserved_floor(keywords: tuple, floor_chars: int) -> int:
        """Guarantee sentences matching `keywords` survive up to `floor_chars`, even if
        higher-priority safety categories below would otherwise consume the whole
        budget first. Trims (via the existing word-boundary trimmer) rather than drops
        a sentence that doesn't fit whole within the floor. Returns chars consumed."""
        nonlocal total_len
        floor_start_len = total_len
        floor_budget = min(floor_chars, PROMPT_MAX_CHARS - total_len)
        for idx, sentence in enumerate(sentences):
            if idx in kept_indices:
                continue
            if not any(kw in sentence.lower() for kw in keywords):
                continue
            separator_len = 1 if kept_indices else 0
            remaining_floor = floor_budget - (total_len - floor_start_len) - separator_len
            if remaining_floor <= 0:
                continue
            if len(sentence) <= remaining_floor:
                kept_indices.add(idx)
                total_len += len(sentence) + separator_len
                continue
            if remaining_floor < 20:
                continue  # not enough room left to keep a meaningful fragment
            trimmed = _trim_text(sentence, remaining_floor)
            if not trimmed:
                continue
            kept_indices.add(idx)
            overrides[idx] = trimmed
            total_len += len(trimmed) + separator_len
        return total_len - floor_start_len

    # Reserved floor pass (Batch 5c): guarantee the Scene: sentence survives even if
    # the higher-priority safety categories below would otherwise consume the whole
    # budget first. Environment: is not part of this floor -- it competes in the
    # normal scene_environment priority pass below.
    _apply_reserved_floor(_SCENE_FLOOR_KEYWORDS, SCENE_FLOOR_CHARS)

    # Reserved floor pass (Batch 5e): guarantee the single shortest essential
    # garment-continuity sentence survives ("Skirt-set continuity lock: keep the named
    # top and skirt as two real separate garments.", 86 chars). "continuity lock" is a
    # precise marker -- verified to match only that one sentence in the source prompt,
    # not the broader wardrobe_continuity keyword set (which stays in the normal
    # priority pass below, unchanged).
    _apply_reserved_floor(_CONTINUITY_FLOOR_KEYWORDS, CONTINUITY_FLOOR_CHARS)

    # Reserved floor pass (Batch 6): guarantee the framing-directive sentence survives
    # ("Framing should clearly show her full silhouette, outfit fit, waist-to-hip
    # shape, legs, posture, hands, and shoes when the scene allows.", 135 chars).
    # "framing should" is precise -- the literal opening of this one sentence type,
    # not the broad body_shape keyword set (which stays in the normal priority pass,
    # unchanged).
    _apply_reserved_floor(_FRAMING_FLOOR_KEYWORDS, FRAMING_FLOOR_CHARS)

    # Reserved floor pass (Batch 7): guarantee the garment-obedience sentence
    # survives ("Garment-obedience lock: the named sleeveless top must remain the
    # visible top garment exactly as specified, and must not be substituted with a
    # sweater, turtleneck, blouse, cardigan, jacket, blazer, coat, or scarf, or
    # replaced with long sleeves or a high neckline.", 262 chars). Only present when
    # the catalog entry is a sleeveless-top + skirt outfit -- absent otherwise, which
    # is expected and correct (not a bug).
    _apply_reserved_floor(_GARMENT_OBEDIENCE_FLOOR_KEYWORDS, GARMENT_OBEDIENCE_FLOOR_CHARS)

    # Reserved floor pass (Frame-logic, 2026-07-07): guarantee the frame-logic
    # paragraph's two hard-requirement clauses (the "Frame logic:" action beat and
    # the "Avoid:" forbidden-object list) survive first, then the remaining
    # supporting clauses (evidence objects, camera intent, body-visibility rule,
    # coherence note) claim whatever budget is left. See the constant definitions
    # above for why this needed two keyword sets instead of the single-keyword
    # pattern used by the Garment-obedience lock floor.
    _apply_reserved_floor(_FRAME_LOGIC_ACTION_FORBIDDEN_FLOOR_KEYWORDS, FRAME_LOGIC_ACTION_FORBIDDEN_FLOOR_CHARS)
    _apply_reserved_floor(_FRAME_LOGIC_SUPPORT_FLOOR_KEYWORDS, FRAME_LOGIC_SUPPORT_FLOOR_CHARS)

    # Reserved floor pass (Expression/gaze, 2026-07-07): guarantee the one short
    # "Expression: ..." sentence survives -- it previously had no floor at all and
    # was measured dropped in effectively every real slot.
    _apply_reserved_floor(_EXPRESSION_GAZE_FLOOR_KEYWORDS, EXPRESSION_GAZE_FLOOR_CHARS)

    for group in _SAFETY_KEYWORD_PRIORITY:
        for idx, groups in enumerate(sentence_groups):
            if group in groups:
                _try_add(idx)

    # Any must-keep sentence not covered by the priority sweep above (shouldn't
    # normally happen since every group is listed in _SAFETY_KEYWORD_PRIORITY).
    for idx, groups in enumerate(sentence_groups):
        if groups:
            _try_add(idx)

    # Fill remaining budget with descriptive/trimmable sentences, original order.
    for idx, groups in enumerate(sentence_groups):
        if not groups:
            _try_add(idx)

    return " ".join(overrides.get(i, sentences[i]) for i in sorted(kept_indices)).strip()


def _build_compact_negative_prompt(slot: Dict[str, Any]) -> str:
    """Transport the full slot["negative_prompt"] built by the prompt brain, deduped,
    trimmed to NEGATIVE_PROMPT_MAX_CHARS only if it doesn't fit -- not reduced to a
    fixed generic term list or substring scanning.

    Batch 7c (2026-07-06): the base NEGATIVE_PROMPT constant alone (2734 chars) already
    exceeds NEGATIVE_PROMPT_MAX_CHARS, so first-N-fit order never gave the
    garment-obedience anti-substitution terms (or any other public-lane extra_bits,
    repo-wide -- tracked separately) any room. This reserves a small floor for exactly
    the garment-obedience terms, trimming the lowest-priority tail of the base list if
    needed, rather than reordering (already tried in Batch 7b, didn't work because the
    base list alone overflows the budget).

    Negative-prompt budget repair (2026-07-06): six more reserved floors added below
    the garment-obedience one, in the same narrow/additive style, covering the other
    protection classes identified in the budget-repair design memo (core identity/
    face, style-realism/anti-cartoon, public clothing safety, outfit-specific
    substitution, body/anatomy). Applied strictly after the garment-obedience floor
    so its available budget and proven 11/11 survival behavior are unchanged."""
    source_negative = str(slot.get("negative_prompt") or NEGATIVE_PROMPT or "").strip()
    terms = _dedupe_terms(t.strip() for t in source_negative.split(",") if t.strip())

    kept: list[str] = []
    total_len = 0

    def _try_add_term(term: str, limit: int) -> bool:
        nonlocal total_len
        added_len = len(term) + (2 if kept else 0)  # ", " separator
        if total_len + added_len <= limit:
            kept.append(term)
            total_len += added_len
            return True
        return False

    def _apply_negative_floor(term_set_lower: set, floor_chars: int) -> int:
        """Reserve up to floor_chars for terms whose lowercase form is in
        term_set_lower, narrow and additive, mirroring the garment-obedience floor
        above exactly. Terms not present in `terms` simply consume none of the
        floor -- this never forces consumption, only caps it. Returns chars used."""
        nonlocal total_len
        floor_start_len = total_len
        floor_budget = min(floor_chars, NEGATIVE_PROMPT_MAX_CHARS - total_len)
        for term in terms:
            if term in kept:
                continue
            if term.lower() not in term_set_lower:
                continue
            remaining = floor_budget - (total_len - floor_start_len)
            if remaining <= 0:
                continue
            added_len = len(term) + (2 if kept else 0)
            if added_len <= remaining:
                kept.append(term)
                total_len += added_len
        return total_len - floor_start_len

    # Existing garment-obedience floor (Batch 7c) -- unchanged, applied first so its
    # available budget is identical to current production behavior regardless of the
    # new floors added below.
    reserved_lower = {t.lower() for t in _GARMENT_OBEDIENCE_NEGATIVE_TERMS}
    floor_budget = min(NEGATIVE_GARMENT_OBEDIENCE_FLOOR_CHARS, NEGATIVE_PROMPT_MAX_CHARS)
    for term in terms:
        if term.lower() in reserved_lower:
            _try_add_term(term, floor_budget)

    # New reserved floors (negative-prompt budget repair, 2026-07-06).
    _apply_negative_floor(_CORE_NEGATIVE_TERMS_LOWER, CORE_NEGATIVE_FLOOR_CHARS)
    _apply_negative_floor(_STYLE_REALISM_TERMS_LOWER, STYLE_REALISM_FLOOR_CHARS)
    _apply_negative_floor(_PUBLIC_SAFETY_TERMS_LOWER, PUBLIC_SAFETY_FLOOR_CHARS)
    _apply_negative_floor(_OUTFIT_SPECIFIC_SUBSTITUTION_TERMS_LOWER, OUTFIT_SPECIFIC_SUBSTITUTION_FLOOR_CHARS)
    _apply_negative_floor(_BODY_ANATOMY_TERMS_LOWER, BODY_ANATOMY_FLOOR_CHARS)

    for term in terms:
        if term in kept:
            continue
        _try_add_term(term, NEGATIVE_PROMPT_MAX_CHARS)

    return ", ".join(kept)


def _build_prompt_receipt(
    slot: Dict[str, Any],
    compact_prompt: str,
    compact_negative: str,
) -> Dict[str, Any]:
    """Small auditable record of what the compaction step actually did, saved
    alongside submit_payload.json for debugging -- not a copy of the full prompt text."""
    metadata = _slot_metadata(slot)
    source_prompt = str(
        slot.get("image_prompt") or slot.get("positive_prompt") or slot.get("prompt") or ""
    ).strip()
    source_negative = str(slot.get("negative_prompt") or NEGATIVE_PROMPT or "").strip()
    source_negative_terms = _dedupe_terms(t.strip() for t in source_negative.split(",") if t.strip())
    compact_negative_terms = [t.strip() for t in compact_negative.split(",") if t.strip()]

    lowered_prompt = compact_prompt.lower()
    groups_present = sorted(
        group
        for group, keywords in _SAFETY_KEYWORD_GROUPS.items()
        if any(kw in lowered_prompt for kw in keywords)
    )
    return {
        "slot_id": slot.get("slot_id"),
        "wardrobe_outfit_id": metadata.get("wardrobe_outfit_id"),
        "wardrobe_silhouette_class": metadata.get("wardrobe_silhouette_class"),
        "environment_id": metadata.get("environment_id"),
        "endpoint_used": IMAGE_SUBMIT_URL,
        "source_prompt_chars": len(source_prompt),
        "compact_prompt_chars": len(compact_prompt),
        "safety_keyword_groups_present_in_final_prompt": groups_present,
        "wardrobe_selection_sentence_present": "wardrobe_selection" in groups_present,
        "wardrobe_continuity_present": "wardrobe_continuity" in groups_present,
        "outerwear_underlayer_language_present": any(
            kw in lowered_prompt for kw in ("tucked", "waistband", "continuity lock", "underlayer")
        ),
        "skin_no_freckle_policy_present": "skin_no_freckle" in groups_present,
        # Batch 5 (2026-07-06): explicit, named record of whether the source
        # Scene:/Environment:/Lighting: language survived compaction -- this was the
        # exact gap that caused the 2026-07-06 proof render's framing/background
        # failure. Do not infer this from safety_keyword_groups_present alone.
        "scene_environment_present": "scene_environment" in groups_present,
        # Batch 5c (2026-07-06): reserved-floor specific fields. As of Batch 5c the
        # guaranteed floor covers Scene: only (not Environment:, which reverted to the
        # normal scene_environment priority pass after starving wardrobe_continuity in
        # Batch 5b). Computed by rescanning the final compact prompt for Scene:
        # sentences (or their trimmed remnants), not by threading internal build-time
        # state out of _build_compact_prompt -- keeps the receipt independently
        # verifiable from the two final strings alone, same as every other field here.
        "scene_environment_floor_reserved_chars": SCENE_FLOOR_CHARS,
        "scene_environment_floor_chars_used": (
            _scene_floor_chars_used := sum(
                len(sentence)
                for sentence in _split_sentences(compact_prompt)
                if any(kw in sentence.lower() for kw in _SCENE_FLOOR_KEYWORDS)
            )
        ),
        "scene_environment_survived_via_reserved_floor": _scene_floor_chars_used > 0,
        # Batch 5e (2026-07-06): mirrors the scene_environment_floor_* fields above,
        # but for the single reserved continuity-lock sentence. Same independent-
        # verification approach: rescans the final compact prompt rather than trusting
        # internal build-time state.
        "wardrobe_continuity_floor_reserved_chars": CONTINUITY_FLOOR_CHARS,
        "wardrobe_continuity_floor_chars_used": (
            _continuity_floor_chars_used := sum(
                len(sentence)
                for sentence in _split_sentences(compact_prompt)
                if any(kw in sentence.lower() for kw in _CONTINUITY_FLOOR_KEYWORDS)
            )
        ),
        "wardrobe_continuity_survived_via_reserved_floor": _continuity_floor_chars_used > 0,
        # Batch 6 (2026-07-06): mirrors the two reserved-floor field groups above, for
        # the framing-directive sentence ("Framing should clearly show her full
        # silhouette..."). Same independent-verification approach.
        "framing_directive_present": any(
            kw in lowered_prompt for kw in _FRAMING_FLOOR_KEYWORDS
        ),
        "framing_directive_floor_reserved_chars": FRAMING_FLOOR_CHARS,
        "framing_directive_floor_chars_used": (
            _framing_floor_chars_used := sum(
                len(sentence)
                for sentence in _split_sentences(compact_prompt)
                if any(kw in sentence.lower() for kw in _FRAMING_FLOOR_KEYWORDS)
            )
        ),
        "framing_directive_survived_via_reserved_floor": _framing_floor_chars_used > 0,
        # Batch 7 (2026-07-06): mirrors the fields above, for the garment-obedience
        # lock. "present" is expected False for non-sleeveless-top-skirt outfits --
        # that's correct, not a bug.
        "garment_obedience_lock_present": any(
            kw in lowered_prompt for kw in _GARMENT_OBEDIENCE_FLOOR_KEYWORDS
        ),
        "garment_obedience_floor_reserved_chars": GARMENT_OBEDIENCE_FLOOR_CHARS,
        "garment_obedience_floor_chars_used": (
            _garment_obedience_floor_chars_used := sum(
                len(sentence)
                for sentence in _split_sentences(compact_prompt)
                if any(kw in sentence.lower() for kw in _GARMENT_OBEDIENCE_FLOOR_KEYWORDS)
            )
        ),
        "garment_obedience_survived_via_reserved_floor": _garment_obedience_floor_chars_used > 0,
        # Batch 7b (2026-07-06): explicit, separate truth for the negative-prompt side
        # of the garment-obedience fix -- do not infer this from the positive lock's
        # fields above, they are tracked independently because they can (and did)
        # diverge.
        "garment_obedience_negative_terms_matched": (
            _go_neg_matched := [
                term for term in _GARMENT_OBEDIENCE_NEGATIVE_TERMS if term in compact_negative.lower()
            ]
        ),
        "garment_obedience_negative_terms_survived_count": len(_go_neg_matched),
        "garment_obedience_negative_terms_total": len(_GARMENT_OBEDIENCE_NEGATIVE_TERMS),
        "garment_obedience_negative_terms_present": len(_go_neg_matched) > 0,
        # Batch 7c (2026-07-06): the reserved-floor mechanism itself, distinct from the
        # match-list above -- reports what was actually reserved/used, not just which
        # terms ended up present.
        "negative_garment_obedience_floor_reserved_chars": NEGATIVE_GARMENT_OBEDIENCE_FLOOR_CHARS,
        "negative_garment_obedience_floor_chars_used": len(", ".join(_go_neg_matched)),
        # Negative-prompt budget repair (2026-07-06): one matched/reserved/used/
        # survived block per new floor, in the same independently-verifiable style
        # as the garment-obedience block above -- each rescans the final
        # compact_negative string directly rather than trusting internal
        # compaction-time state.
        "negative_core_terms_matched": (
            _core_neg_matched := [t for t in CORE_NEGATIVE_TERMS if t.lower() in compact_negative.lower()]
        ),
        "negative_core_terms_survived_count": len(_core_neg_matched),
        "negative_core_terms_total": len(CORE_NEGATIVE_TERMS),
        "negative_core_terms_present": len(_core_neg_matched) > 0,
        "negative_core_floor_reserved_chars": CORE_NEGATIVE_FLOOR_CHARS,
        "negative_core_floor_chars_used": len(", ".join(_core_neg_matched)),
        "negative_core_survived_via_reserved_floor": len(_core_neg_matched) > 0,
        "negative_style_realism_terms_matched": (
            _style_neg_matched := [t for t in STYLE_REALISM_NEGATIVE_TERMS if t.lower() in compact_negative.lower()]
        ),
        "negative_style_realism_terms_survived_count": len(_style_neg_matched),
        "negative_style_realism_terms_total": len(STYLE_REALISM_NEGATIVE_TERMS),
        "negative_style_realism_terms_present": len(_style_neg_matched) > 0,
        "negative_style_realism_floor_reserved_chars": STYLE_REALISM_FLOOR_CHARS,
        "negative_style_realism_floor_chars_used": len(", ".join(_style_neg_matched)),
        "negative_style_realism_survived_via_reserved_floor": len(_style_neg_matched) > 0,
        "negative_public_safety_terms_matched": (
            _public_safety_neg_matched := [
                t for t in (PUBLIC_SAFETY_NEGATIVE_TERMS + PUBLIC_LANE_SAFETY_TERMS)
                if t.lower() in compact_negative.lower()
            ]
        ),
        "negative_public_safety_terms_survived_count": len(_public_safety_neg_matched),
        "negative_public_safety_terms_total": len(PUBLIC_SAFETY_NEGATIVE_TERMS) + len(PUBLIC_LANE_SAFETY_TERMS),
        "negative_public_safety_terms_present": len(_public_safety_neg_matched) > 0,
        "negative_public_safety_floor_reserved_chars": PUBLIC_SAFETY_FLOOR_CHARS,
        "negative_public_safety_floor_chars_used": len(", ".join(_public_safety_neg_matched)),
        "negative_public_safety_survived_via_reserved_floor": len(_public_safety_neg_matched) > 0,
        # Batch 7c's garment-obedience terms are a separate, already-covered class --
        # this floor covers the *other* outfit classes (dress/bodysuit/skirt/shorts/
        # outerwear substitution). "present" is expected False whenever none of those
        # classes applies to this outfit -- that's correct, not a bug, same as the
        # positive-side garment_obedience_lock_present field above.
        "negative_outfit_specific_terms_matched": (
            _outfit_specific_neg_matched := [
                t for t in OUTFIT_SPECIFIC_SUBSTITUTION_TERMS if t.lower() in compact_negative.lower()
            ]
        ),
        "negative_outfit_specific_terms_survived_count": len(_outfit_specific_neg_matched),
        "negative_outfit_specific_terms_total": len(OUTFIT_SPECIFIC_SUBSTITUTION_TERMS),
        "negative_outfit_specific_terms_present": len(_outfit_specific_neg_matched) > 0,
        "negative_outfit_specific_floor_reserved_chars": OUTFIT_SPECIFIC_SUBSTITUTION_FLOOR_CHARS,
        "negative_outfit_specific_floor_chars_used": len(", ".join(_outfit_specific_neg_matched)),
        "negative_outfit_specific_survived_via_reserved_floor": len(_outfit_specific_neg_matched) > 0,
        "negative_body_anatomy_terms_matched": (
            _body_anatomy_neg_matched := [t for t in BODY_ANATOMY_NEGATIVE_TERMS if t.lower() in compact_negative.lower()]
        ),
        "negative_body_anatomy_terms_survived_count": len(_body_anatomy_neg_matched),
        "negative_body_anatomy_terms_total": len(BODY_ANATOMY_NEGATIVE_TERMS),
        "negative_body_anatomy_terms_present": len(_body_anatomy_neg_matched) > 0,
        "negative_body_anatomy_floor_reserved_chars": BODY_ANATOMY_FLOOR_CHARS,
        "negative_body_anatomy_floor_chars_used": len(", ".join(_body_anatomy_neg_matched)),
        "negative_body_anatomy_survived_via_reserved_floor": len(_body_anatomy_neg_matched) > 0,
        # Optional-fill tier: whatever compact terms aren't claimed by any floor
        # above. Not a guarantee -- reported for budget transparency, not protection.
        # Deliberately computed from *actual* chars used by the floors above for
        # this specific render, not the floors' nominal caps -- the caps sum to more
        # than NEGATIVE_PROMPT_MAX_CHARS by design (garment-obedience and
        # outfit-specific are rarely both fully populated at once), so a cap-based
        # subtraction can go negative and would be misleading here.
        "negative_optional_fill_reserved_chars": max(
            0,
            NEGATIVE_PROMPT_MAX_CHARS
            - len(", ".join(_go_neg_matched))
            - len(", ".join(_core_neg_matched))
            - len(", ".join(_style_neg_matched))
            - len(", ".join(_public_safety_neg_matched))
            - len(", ".join(_outfit_specific_neg_matched))
            - len(", ".join(_body_anatomy_neg_matched)),
        ),
        "negative_optional_fill_terms_included": (
            _optional_fill_terms := [
                t for t in compact_negative_terms
                if t not in _go_neg_matched
                and t not in _core_neg_matched
                and t not in _style_neg_matched
                and t not in _public_safety_neg_matched
                and t not in _outfit_specific_neg_matched
                and t not in _body_anatomy_neg_matched
            ]
        ),
        "negative_optional_fill_chars_used": len(", ".join(_optional_fill_terms)),
        "negative_optional_fill_terms_included_count": len(_optional_fill_terms),
        "public_scene_lock_present": "public_scene_lock" in groups_present,
        "hands_policy_present": "hands" in groups_present,
        "source_negative_prompt_chars": len(source_negative),
        "compact_negative_prompt_chars": len(compact_negative),
        "negative_terms_source_unique_count": len(source_negative_terms),
        "negative_terms_final_count": len(compact_negative_terms),
        "negative_prompt_fully_preserved": len(compact_negative_terms) >= len(source_negative_terms),
        # Batch 4 (2026-07-05): explicit budget-truthfulness fields. Do not infer
        # "fully preserved" from char counts alone -- state plainly whether the
        # source was trimmed and by how many terms, so this receipt cannot be
        # misread as a claim of full preservation when the budget cut it short.
        "negative_prompt_original_chars": len(source_negative),
        "negative_prompt_final_chars": len(compact_negative),
        "negative_prompt_trimmed_due_to_budget": len(compact_negative_terms) < len(source_negative_terms),
        "negative_prompt_terms_survived": len(compact_negative_terms),
        "negative_prompt_terms_dropped": max(0, len(source_negative_terms) - len(compact_negative_terms)),
        "timestamp_utc": _utc_now(),
    }


def _debug_dir(date_str: str, slot_id: str) -> Path:
    path = DEBUG_ROOT / date_str / slot_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _build_jwt(ak: str, sk: str) -> str:
    now = int(time.time())
    payload = {"iss": ak, "exp": now + 1800, "nbf": now - 5}
    try:
        import jwt as pyjwt

        return pyjwt.encode(payload, sk, algorithm="HS256")
    except Exception:
        header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
        body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing = f"{header}.{body}".encode("utf-8")
        signature = _b64url(hmac.new(sk.encode("utf-8"), signing, hashlib.sha256).digest())
        return f"{header}.{body}.{signature}"


def _auth_header() -> Dict[str, str]:
    ak = str(os.environ.get("KLING_AK") or os.environ.get("KLING_ACCESS_KEY") or "").strip()
    sk = str(os.environ.get("KLING_SK") or os.environ.get("KLING_SECRET_KEY") or "").strip()
    if ak and sk:
        return {"Authorization": f"Bearer {_build_jwt(ak, sk)}"}
    web_token = str(os.environ.get("KLING_WEB_TOKEN", "")).strip()
    if web_token:
        return {"Authorization": f"Bearer {web_token}"}
    raise RuntimeError("Missing Kling credentials. Need KLING_WEB_TOKEN or KLING_AK/KLING_SK.")


def _web_token_header() -> Dict[str, str]:
    web_token = str(os.environ.get("KLING_WEB_TOKEN", "")).strip()
    if not web_token:
        raise RuntimeError("Missing KLING_WEB_TOKEN for live APILENA element lookup.")
    return {"Authorization": f"Bearer {web_token}"}


def _live_elements_headers() -> Dict[str, str]:
    cookie_header = str(os.environ.get("KLING_WEB_COOKIE_HEADER", "")).strip()
    headers: Dict[str, str] = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-001",
        "kww": ELEMENTS_SEARCH_KWW,
        "priority": "u=1, i",
        "referer": "https://kling.ai/app/user-assets/principal/elements",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "time-zone": "America/Chicago",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    }
    if cookie_header:
        headers["cookie"] = cookie_header
        return headers
    return {**headers, **_web_token_header()}


def _http_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "content-bot-apilena/1.0",
        **_auth_header(),
    }
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, data=body, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": response.status,
                "url": url,
                "json": json.loads(raw) if raw else {},
                "raw": raw,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = None
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "json": parsed,
            "raw": raw,
        }


def _http_json_with_headers(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "content-bot-apilena/1.0",
        **headers,
    }
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, headers=merged, data=body, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": response.status,
                "url": url,
                "json": json.loads(raw) if raw else {},
                "raw": raw,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = None
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "json": parsed,
            "raw": raw,
        }


def _manual_live_image_urls() -> list[str]:
    # Batch 2 (2026-07-05): guard now owned by pipeline/identity/lena_identity.py
    # instead of a local copy. See pipeline/change_notes/lena_agentic_pivot_changelog.md.
    lena_identity.assert_no_manual_reference_override()
    return []


def _extract_live_element_urls(element: Dict[str, Any]) -> list[str]:
    urls: list[str] = []
    resources = element.get("resources")
    if isinstance(resources, list):
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            for key in ("resource", "url", "imageUrl", "src", "cover"):
                value = resource.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    urls.append(value)
    cover = element.get("cover")
    if isinstance(cover, str) and cover.startswith("http"):
        urls.append(cover)
    extra = element.get("extraInfo")
    if isinstance(extra, dict):
        urls.extend(_collect_image_urls(extra))
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _resolve_live_apilena_image_urls(slot_id: str, date_str: str) -> Dict[str, Any]:
    manual_urls = _manual_live_image_urls()
    if manual_urls:
        return {"ok": True, "source": "manual_env", "image_urls": manual_urls[:4]}

    debug_dir = _debug_dir(date_str, slot_id)
    headers = _live_elements_headers()
    attempts: list[Dict[str, Any]] = []
    matched: Optional[Dict[str, Any]] = None
    last_payload: Dict[str, Any] = {}
    try:
        for page_num in range(1, max(1, ELEMENTS_LOOKUP_MAX_PAGES) + 1):
            url = ELEMENTS_LIST_URL_TEMPLATE.format(page_num=page_num)
            response = requests.get(url, headers=headers, timeout=30)
            lookup = {
                "ok": response.ok,
                "status": response.status_code,
                "url": url,
                "json": response.json() if response.text else {},
                "raw": response.text,
            }
            payload = (lookup.get("json") or {}).get("data") or {}
            items = payload.get("elementsList") or []
            attempts.append(
                {
                    "kind": "elements_list",
                    "page_num": page_num,
                    "ok": lookup["ok"],
                    "status": lookup["status"],
                    "url": url,
                    "user_count": payload.get("userCount"),
                    "all_user_count": payload.get("allUserCount"),
                    "elements_count": len(items) if isinstance(items, list) else 0,
                }
            )
            if not lookup["ok"]:
                continue
            last_payload = payload if isinstance(payload, dict) else {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                item_name = str(item.get("name") or "").strip().lower()
                if item_id == LIVE_LENA_UI_ID or item_name == LIVE_LENA_NAME.lower():
                    matched = item
                    break
            if matched:
                break

        if not matched:
            response = requests.get(ELEMENTS_SEARCH_URL, headers=headers, timeout=30)
            lookup = {
                "ok": response.ok,
                "status": response.status_code,
                "url": ELEMENTS_SEARCH_URL,
                "json": response.json() if response.text else {},
                "raw": response.text,
            }
            payload = (lookup.get("json") or {}).get("data") or {}
            items = payload.get("elementsList") or []
            attempts.append(
                {
                    "kind": "legacy_search",
                    "ok": lookup["ok"],
                    "status": lookup["status"],
                    "url": ELEMENTS_SEARCH_URL,
                    "user_count": payload.get("userCount"),
                    "all_user_count": payload.get("allUserCount"),
                    "elements_count": len(items) if isinstance(items, list) else 0,
                }
            )
            if lookup["ok"]:
                last_payload = payload if isinstance(payload, dict) else {}
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id") or "").strip()
                    item_name = str(item.get("name") or "").strip().lower()
                    if item_id == LIVE_LENA_UI_ID or item_name == LIVE_LENA_NAME.lower():
                        matched = item
                        break
    except Exception as exc:
        return {"ok": False, "status": "live_apilena_lookup_error", "error": str(exc)}

    _save_json(
        debug_dir / "live_apilena_lookup_response.json",
        {
            "matched": bool(matched),
            "live_lena_ui_id": LIVE_LENA_UI_ID,
            "live_lena_name": LIVE_LENA_NAME,
            "attempts": attempts,
            "matched_element": matched,
            "last_payload": last_payload,
        },
    )
    if not matched:
        return {
            "ok": False,
            "status": "live_apilena_not_found_in_user_elements",
            "debug_path": str(debug_dir / "live_apilena_lookup_response.json"),
            "user_count": last_payload.get("userCount"),
            "all_user_count": last_payload.get("allUserCount"),
        }
    image_urls = _extract_live_element_urls(matched)
    if len(image_urls) < 1:
        return {
            "ok": False,
            "status": "live_apilena_has_no_image_urls",
            "debug_path": str(debug_dir / "live_apilena_lookup_response.json"),
        }
    return {
        "ok": True,
        "source": "kling_user_elements_api",
        "image_urls": image_urls[:4],
        "debug_path": str(debug_dir / "live_apilena_lookup_response.json"),
    }


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "content-bot-apilena/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        destination.write_bytes(response.read())


def _load_manifest(date_str: str) -> Dict[str, Any]:
    path = WORKORDER_ROOT / date_str / "daily_workorders.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing production manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_slot(date_str: str, slot_id: str, slot: Dict[str, Any]) -> None:
    path = WORKORDER_ROOT / date_str / f"{slot_id}.json"
    path.write_text(json.dumps(slot, indent=2, ensure_ascii=False), encoding="utf-8")


def _collect_image_urls(obj: Any) -> list[str]:
    urls: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"url", "image_url", "origin_url"} and isinstance(child, str) and child.startswith("http"):
                    urls.append(child)
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(obj)
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _sanitize_reference_url(url: str) -> str:
    """Log-safe form of a URL: scheme+host + short path prefix only, never the full
    path or query (which may carry signing). Never emit the raw URL to logs/output."""
    if not isinstance(url, str) or not url:
        return "<no url>"
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path[:16]}...<redacted len={len(url)}>"


def build_reference_url_photo_payload(
    slot: Dict[str, Any], image_urls: Iterable[str]
) -> Dict[str, Any]:
    """Single source of truth for the Lena reference-by-URL photo payload (Variant B,
    proven live 2026-07-07). Pure and no-network. Uses model_name=kling-v3-omni, sends
    the APILENA reference URL in image_list, omits element_list, and omits
    negative_prompt for this first patched validation (matching the successful live
    test). Raises if no usable https reference URL is present, or LenaReferenceGuardError
    if the built payload somehow lacks a visual reference."""
    reference_url = ""
    for candidate in image_urls or []:
        s = str(candidate).strip()
        if s.lower().startswith(("http://", "https://")):
            reference_url = s
            break
    if not reference_url:
        # Never send a local C:\ path or empty ref to Kling.
        raise ValueError("No usable https APILENA reference URL for reference-by-URL payload.")

    compact_prompt = _build_compact_prompt(slot)
    payload: Dict[str, Any] = {
        "model_name": REFERENCE_IMAGE_MODEL_NAME,
        "prompt": compact_prompt,
        "aspect_ratio": "9:16",
        "n": 1,
        "image_list": [{"image": reference_url}],
    }
    # Safety gates: no element_list, and the reference guard must pass on the final payload.
    if "element_list" in payload:
        raise RuntimeError("reference-by-URL payload must not contain element_list")
    apilena_reference_guard.assert_lena_visual_references_present(payload)
    return payload


def _submit_photo(slot: Dict[str, Any], date_str: str) -> Dict[str, Any]:
    slot_id = str(slot.get("slot_id") or "")
    if not slot_id:
        return {"ok": False, "status": "missing_slot_id"}
    expected_path = Path(slot["expected_assets"]["seed_image_path"])
    debug_dir = _debug_dir(date_str, slot_id)
    element_id = lena_identity.clean_element_id(LIVE_LENA_UI_ID)
    if not element_id:
        return {"ok": False, "slot_id": slot_id, "status": "missing_apilena_element_id"}
    live_images = _resolve_live_apilena_image_urls(slot_id, date_str)
    if not live_images.get("ok"):
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": live_images.get("status", "live_apilena_image_urls_unresolved"),
            "debug_path": live_images.get("debug_path"),
            "error": live_images.get("error"),
        }
    image_urls = [str(url).strip() for url in (live_images.get("image_urls") or []) if str(url).strip().startswith("http")]
    if not image_urls:
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": "live_apilena_image_urls_empty",
            "debug_path": live_images.get("debug_path"),
        }

    try:
        compact_prompt = _build_compact_prompt(slot)
        # Telemetry only for the receipt -- NOT placed in the payload (negative_prompt
        # is omitted for this first patched validation, matching the live test).
        compact_negative = _build_compact_negative_prompt(slot)
    except Exception as exc:
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": "prompt_build_failed",
            "error": str(exc),
        }

    try:
        payload = build_reference_url_photo_payload(slot, image_urls)
    except apilena_reference_guard.LenaReferenceGuardError as exc:
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": "reference_guard_blocked",
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": "reference_payload_build_failed",
            "error": str(exc),
        }

    # Defense in depth: never submit a Lena payload without a visual reference, and
    # never a payload carrying element_list without one.
    apilena_reference_guard.assert_lena_visual_references_present(payload)

    _save_json(debug_dir / "submit_payload.json", payload)
    _save_json(
        debug_dir / "prompt_receipt.json",
        _build_prompt_receipt(slot, compact_prompt, compact_negative),
    )
    submit = _http_json("POST", OMNI_IMAGE_SUBMIT_URL, payload)
    _save_json(
        debug_dir / "submit_response.json",
        {"ok": submit["ok"], "status": submit["status"], "url": submit["url"], "json": submit.get("json"), "raw": submit.get("raw", "")},
    )
    if not submit["ok"]:
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": "submit_failed",
            "http_status": submit["status"],
            "debug_path": str(debug_dir / "submit_response.json"),
        }
    submit_json = submit.get("json") or {}
    data = submit_json.get("data") or {}
    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        return {
            "ok": False,
            "slot_id": slot_id,
            "status": "missing_task_id",
            "debug_path": str(debug_dir / "submit_response.json"),
        }

    poll_url = f"{OMNI_IMAGE_SUBMIT_URL.rstrip('/')}/{task_id}"
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    last_json: Dict[str, Any] = {}
    while time.time() < deadline:
        polled = _http_json("GET", poll_url)
        last_json = polled.get("json") or {}
        _save_json(
            debug_dir / "poll_response.json",
            {"ok": polled["ok"], "status": polled["status"], "url": polled["url"], "json": last_json, "raw": polled.get("raw", "")},
        )
        if not polled["ok"]:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        pdata = last_json.get("data") or {}
        status = str(pdata.get("task_status") or "").strip().lower()
        if status == "succeed":
            urls = _collect_image_urls((pdata.get("task_result") or {}).get("images") or pdata.get("task_result") or {})
            if not urls:
                return {
                    "ok": False,
                    "slot_id": slot_id,
                    "status": "succeeded_no_image_url",
                    "task_id": task_id,
                    "debug_path": str(debug_dir / "poll_response.json"),
                }
            _download_file(urls[0], expected_path)
            reference_url_sanitized = _sanitize_reference_url(
                payload["image_list"][0]["image"]
            )
            metadata = slot.setdefault("metadata", {})
            metadata["generated_image_signature"] = current_image_generation_signature(slot)
            metadata["photo_identity_binding"] = "validated_kling_api_lena_reference_url"
            metadata["reference_binding_mode"] = "kling_omni_image_reference_by_url"
            metadata["reference_source_policy"] = "kling_live_apilena_resource_url_in_image_list"
            metadata["reference_source_element_id_source"] = "KLING_LENA_ELEMENT_UI_ID"
            metadata["reference_source_element_id"] = LIVE_LENA_UI_ID
            metadata["lena_element_ui_numeric_id"] = element_id
            metadata["lena_element_id_source"] = "KLING_LENA_ELEMENT_UI_ID"
            metadata["reference_url_sanitized"] = reference_url_sanitized
            metadata["seed_source"] = "fresh_kling_omni_image_reference_by_url_generation"
            metadata["reference_source_notice"] = "This generation conditions on the APILENA element's hosted reference image URL sent in image_list; element_list omitted."
            _write_slot(date_str, slot_id, slot)
            _save_json(
                debug_dir / "result_manifest.json",
                {
                    "slot_id": slot_id,
                    "task_id": task_id,
                    "task_status": status,
                    "saved_image_paths": [str(expected_path)],
                    "output_image_urls_sanitized": [_sanitize_reference_url(u) for u in urls],
                    "reference_url_sanitized": reference_url_sanitized,
                    "element_id": element_id,
                    "element_name": LIVE_LENA_NAME,
                    "provider_endpoint": OMNI_IMAGE_SUBMIT_URL,
                    "payload_has_image_list": True,
                    "payload_no_element_list": True,
                    "payload_no_negative_prompt": True,
                    "model_name": REFERENCE_IMAGE_MODEL_NAME,
                    "live_apilena_image_count": len(image_urls),
                    "timestamp_utc": _utc_now(),
                },
            )
            return {
                "ok": True,
                "slot_id": slot_id,
                "status": "downloaded",
                "task_id": task_id,
                "path": str(expected_path),
                "debug_path": str(debug_dir / "result_manifest.json"),
                "output_image_urls_sanitized": [_sanitize_reference_url(u) for u in urls],
            }
        if status == "failed":
            return {
                "ok": False,
                "slot_id": slot_id,
                "status": "task_failed",
                "task_id": task_id,
                "task_status_msg": str(pdata.get("task_status_msg") or ""),
                "debug_path": str(debug_dir / "poll_response.json"),
            }
        time.sleep(POLL_INTERVAL_SECONDS)
    return {
        "ok": False,
        "slot_id": slot_id,
        "status": "poll_timeout",
        "task_id": task_id,
        "debug_path": str(debug_dir / "poll_response.json"),
    }


def run_executor(date_str: Optional[str] = None) -> Dict[str, Any]:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    manifest = _load_manifest(date_str)
    max_slots = int(os.environ.get("CONTENT_BOT_KLING_MAX_SLOTS", "0") or "0")
    # Batch 4b (2026-07-06): optional single-slot_id filter for a controlled proof
    # render. Only changes which slot(s) this loop considers -- does not touch
    # prompt building, identity resolution, payload construction, or publishing.
    target_slot_id = str(os.environ.get("CONTENT_BOT_KLING_TARGET_SLOT_ID", "")).strip()
    execute = str(os.environ.get("CONTENT_BOT_KLING_EXECUTE", "0")).lower() in {"1", "true", "yes"}
    results: list[Dict[str, Any]] = []
    processed = 0

    for slot in manifest.get("slots", []):
        if max_slots > 0 and processed >= max_slots:
            break
        if str(slot.get("media_type") or "").strip().lower() != "photo":
            continue
        if target_slot_id and str(slot.get("slot_id") or "") != target_slot_id:
            continue
        if not execute:
            live_images = _resolve_live_apilena_image_urls(str(slot.get("slot_id") or f"{date_str}-dryrun"), date_str)
            results.append(
                {
                    "ok": bool(live_images.get("ok")),
                    "slot_id": slot.get("slot_id"),
                    "status": "ready_no_spend" if live_images.get("ok") else live_images.get("status", "live_apilena_image_urls_unresolved"),
                    "element_id": lena_identity.clean_element_id(LIVE_LENA_UI_ID),
                    "element_name": LIVE_LENA_NAME,
                    "provider_endpoint": OMNI_IMAGE_SUBMIT_URL,
                    "payload_has_image_list": True,
                    "payload_no_element_list": True,
                    "live_apilena_image_count": len(live_images.get("image_urls") or []),
                    "debug_path": live_images.get("debug_path"),
                }
            )
            processed += 1
            continue
        results.append(_submit_photo(slot, date_str))
        processed += 1

    return {
        "ok": all(bool(item.get("ok")) for item in results) if results else False,
        "backend": "kling_apilena_api_only",
        "execute": execute,
        "live_lena_ui_id": LIVE_LENA_UI_ID,
        "live_lena_name": LIVE_LENA_NAME,
        "provider_endpoint": OMNI_IMAGE_SUBMIT_URL,
        "date": date_str,
        "processed_slots": processed,
        "results": results,
        "timestamp_utc": _utc_now(),
    }


def main() -> int:
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    result = run_executor(date_str)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
