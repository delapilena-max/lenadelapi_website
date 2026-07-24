"""The single authoritative definition of a valid Lena provider prompt.

Every Lena generation -- manual proof, retry, or autonomous -- must satisfy
this contract before any provider spend. There is exactly one definition and
one validator; no prompt path may bypass it.

DOCTRINE (2026-07-24, identity/body block mandated same day)
--------------------------------------------------------------
1.  Identity is established by the trained Lena Soul, referenced in the
    prompt and attached to the provider command via --soul-id.
2.  CANONICAL_LENA_IDENTITY_BODY_BLOCK is Nicolas's exact, mandatory
    identity-and-body text (see below). It must appear verbatim in every
    [Subject] section, unaltered. It is the single authoritative source for
    Lena's described figure -- no recipe field may restate, weaken, or
    contradict it; recipes vary scene/outfit/pose/expression/mood/camera
    only.
3.  Positive instructions only. text2image_soul_v2 exposes no negative-prompt
    parameter, so "no X" is delivered as ordinary positive conditioning and
    can summon the very thing it names. Authored source data is positive; no
    runtime sanitizer rewrites anything (that would break zero-loss).
4.  Zero loss. Authored source text reaches the provider byte-for-byte.
    This module validates; it never mutates.

The varying creative dimensions -- scene, outfit, pose, action, expression,
mood, camera treatment, story concept -- are free. The structure is not.
"""
from __future__ import annotations

import re

# Nicolas's exact mandate, 2026-07-24. Verbatim -- do not paraphrase or
# reformat. This is the single authoritative source for Lena's described
# identity and figure; every prompt path embeds this same constant rather
# than a re-typed copy (so content and validation can never drift apart).
CANONICAL_LENA_IDENTITY_BODY_BLOCK = (
    "Lena is a recognizable adult woman and a striking, camera-dominant "
    "bombshell. Preserve her established face, warm brunette hair, "
    "feminine presence, and realistic anatomy. Her figure is a pronounced "
    "but believable slim-thick hourglass: a very small, tightly defined "
    "waist; broad, rounded hips; a large, full bubble butt; and thick, "
    "shapely thighs. The waist-to-hip contrast may feel almost "
    "exaggerated, but must remain anatomically credible, polished, and "
    "womanly rather than cartoonish or distorted. Clothing should fit and "
    "flatter her natural curves. Many images should use tasteful, "
    "intentional, platform-safe skin exposure and curve-emphasizing "
    "styling, while other images remain more covered for visual variety. "
    "Every result must unmistakably look like Lena and present her as "
    "confident, glamorous, feminine, and exceptionally attractive."
)

# Nicolas's ceiling for this contract (2026-07-24). The pre-existing
# repository execution-policy budget (4096 chars, in
# lena_provider_prompt_limits_v1.py) is stricter and still the active gate;
# this check exists so a future relaxation of that budget can never silently
# exceed Nicolas's own stated limit for this contract.
MAX_PROMPT_CHARS = 4500

# The canonical section order. Every prompt is these labels, in this order.
REQUIRED_SECTIONS = (
    "Subject",
    "Action",
    "Expression",
    "Environment",
    "Cinematography",
    "Lighting/Style",
    "Technical",
)
# Present in production prompts but permitted to be absent (HPE profile is
# opt-in per recipe).
OPTIONAL_SECTIONS = ("Subject Presence",)

SECTION_ORDER = (
    "Subject",
    "Subject Presence",
    "Action",
    "Expression",
    "Environment",
    "Cinematography",
    "Lighting/Style",
    "Technical",
)

MIN_SECTION_CHARS = 8

# Placeholder / unresolved-authority markers that must never reach a provider.
PLACEHOLDER_MARKERS = (
    "<full prompt>",
    "<prompt>",
    "<redacted",
    "tbd",
    "todo",
    "lorem ipsum",
    "placeholder",
    "authority required",
    "xxx",
    "{}",
)

# Negative constructions. Positive-only doctrine (see 2 above).
NEGATIVE_PATTERNS = (
    re.compile(r"(?:^|[.;]\s+)(no|never|avoid|don't|do not|without|nothing)\b", re.I),
    re.compile(r",\s*(no|not|never|avoid|without)\b", re.I),
    re.compile(r"\s+never\s+", re.I),
)

# Identity must be anchored to the Soul, not re-described.
IDENTITY_REQUIRED = re.compile(r"\blena\b", re.I)
SOUL_ANCHOR = re.compile(r"lena soul|soul", re.I)

# Direct contradictions of CANONICAL_LENA_IDENTITY_BODY_BLOCK. A recipe
# cannot omit the block (that's caught separately), but it could still
# undercut it elsewhere in the prompt (e.g. a pose/wardrobe line claiming
# a narrow or slim-hipped silhouette) -- these terms catch that.
IDENTITY_CONTRADICTION_TERMS = (
    "narrow hips", "narrow-hipped", "slim hips", "slim-hipped",
    "thigh gap", "flat butt", "flat chest", "petite frame",
    "boyish figure", "straight silhouette", "body-slimming",
)


class PromptContractError(ValueError):
    """Raised when a prompt violates the canonical contract."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def parse_sections(prompt: str) -> dict[str, str]:
    """Split a rendered provider prompt into {label: body}."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise PromptContractError("prompt_empty", "prompt is empty")
    found: dict[str, str] = {}
    for line in prompt.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\[([^\]]+)\]:\s*(.*)$", line)
        if not match:
            raise PromptContractError(
                "prompt_unstructured_line",
                f"every prompt line must be '[Section]: body'; got {line[:60]!r}",
            )
        found[match.group(1).strip()] = match.group(2).strip()
    if not found:
        raise PromptContractError("prompt_no_sections", "prompt contains no sections")
    return found


def validate_prompt_contract(prompt: str) -> dict[str, str]:
    """Validate a fully rendered provider prompt. Returns parsed sections.

    Raises PromptContractError on the first violation. Never mutates.
    """
    sections = parse_sections(prompt)

    unknown = [label for label in sections if label not in SECTION_ORDER]
    if unknown:
        raise PromptContractError(
            "prompt_unknown_section", f"unrecognised section(s): {unknown}"
        )

    missing = [label for label in REQUIRED_SECTIONS if label not in sections]
    if missing:
        raise PromptContractError(
            "prompt_missing_required_section",
            f"required section(s) absent: {missing}",
        )

    present_order = [label for label in sections]
    expected_order = [label for label in SECTION_ORDER if label in sections]
    if present_order != expected_order:
        raise PromptContractError(
            "prompt_section_order_invalid",
            f"sections must follow canonical order; got {present_order}",
        )

    for label in REQUIRED_SECTIONS:
        body = sections[label]
        if not body or len(body) < MIN_SECTION_CHARS:
            raise PromptContractError(
                "prompt_section_incomplete",
                f"section [{label}] is empty or too short to be real direction",
            )

    lowered = prompt.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            raise PromptContractError(
                "prompt_placeholder_present",
                f"prompt contains placeholder/unresolved marker {marker!r}",
            )

    for pattern in NEGATIVE_PATTERNS:
        match = pattern.search(prompt)
        if match:
            raise PromptContractError(
                "prompt_negative_wording",
                (
                    "positive-only doctrine: this model has no negative-prompt "
                    f"channel, so {match.group(0).strip()!r} would be sent as "
                    "positive conditioning"
                ),
            )

    if not IDENTITY_REQUIRED.search(sections["Subject"]):
        raise PromptContractError(
            "prompt_identity_missing", "[Subject] must name Lena"
        )
    if not SOUL_ANCHOR.search(sections["Subject"]):
        raise PromptContractError(
            "prompt_soul_anchor_missing",
            "[Subject] must anchor identity to the Lena Soul",
        )
    if CANONICAL_LENA_IDENTITY_BODY_BLOCK not in sections["Subject"]:
        raise PromptContractError(
            "prompt_canonical_identity_block_missing",
            "[Subject] must contain CANONICAL_LENA_IDENTITY_BODY_BLOCK verbatim",
        )

    for term in IDENTITY_CONTRADICTION_TERMS:
        if term in lowered:
            raise PromptContractError(
                "prompt_identity_contradiction",
                (
                    f"{term!r} contradicts CANONICAL_LENA_IDENTITY_BODY_BLOCK "
                    "and must not appear"
                ),
            )

    if len(prompt) > MAX_PROMPT_CHARS:
        raise PromptContractError(
            "prompt_exceeds_max_chars",
            f"prompt is {len(prompt)} chars, exceeds the {MAX_PROMPT_CHARS}-char contract ceiling",
        )

    return sections


def prompt_satisfies_contract(prompt: str) -> bool:
    """Non-raising convenience check."""
    try:
        validate_prompt_contract(prompt)
    except PromptContractError:
        return False
    return True
