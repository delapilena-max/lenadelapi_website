"""Pre-provider prompt hygiene tests.

text2image_soul_v2 has no negative-prompt parameter (confirmed read-only via
`higgsfield model get text2image_soul_v2 --json`). Every clause in the prompt
is therefore delivered as positive conditioning, so naming an unwanted object
at all -- even as "no open jeans" -- puts that object in front of the model.

These tests assert the assembled provider prompt names none of the unwanted
items and carries no negative clause constructions. Fully offline.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder

# Exact unwanted items, per operator instruction 2026-07-24.
FORBIDDEN_SUBSTRINGS = (
    "open jean",
    "exposed zipper",
    "underwear",
    "belly jewelry",
    "cleavage",
    "midriff",
    "wardrobe malfunction",
    "black background",
    "black/empty",
)

# Negative-clause constructions that must not survive into the prompt.
FORBIDDEN_CONSTRUCTIONS = (
    ", no ",
    ", not ",
    ", never ",
    " never ",
    "no black",
    "avoid ",
)


def _assert_clean(text: str, label: str) -> None:
    lowered = text.lower()
    for token in FORBIDDEN_SUBSTRINGS:
        assert token not in lowered, f"{label} names the unwanted item {token!r}: {text[:300]!r}"
    for token in FORBIDDEN_CONSTRUCTIONS:
        assert token not in lowered, f"{label} contains negative construction {token!r}: {text[:300]!r}"


@pytest.mark.parametrize(
    "constant_name",
    ["STRUCTURED_SUBJECT_BRIEF", "STRUCTURED_TECHNICAL_REALISM", "PROVIDER_PROMPT_REQUIRED_GUARDRAILS"],
)
def test_prompt_constants_are_positive_only(constant_name: str) -> None:
    _assert_clean(getattr(packet_builder, constant_name), constant_name)


def test_guardrails_state_the_required_positive_framing() -> None:
    # 2026-07-24: the guardrails no longer force one specific garment (a
    # blanket "crew-neck top and high-rise jeans" on every image) -- that
    # fought recipes' own locked wardrobe. Wardrobe now varies per recipe;
    # only genuinely universal platform-safety/framing requirements remain.
    text = packet_builder.PROVIDER_PROMPT_REQUIRED_GUARDRAILS.lower()

    assert "complete head and face visible" in text
    assert "natural apartment environment" in text
    assert "face-led composition" in text
    assert "tasteful" in text
    assert "platform-safe" in text


def test_subject_brief_embeds_the_canonical_identity_body_block() -> None:
    """2026-07-24: Nicolas's mandate reverses the prior no-body-description
    doctrine -- CANONICAL_LENA_IDENTITY_BODY_BLOCK is now required verbatim
    in every [Subject], carrying explicit figure description on purpose."""
    from pipeline.prompting import lena_canonical_prompt_contract_v1 as contract

    text = packet_builder.STRUCTURED_SUBJECT_BRIEF

    assert "lena soul" in text.lower()
    assert contract.CANONICAL_LENA_IDENTITY_BODY_BLOCK in text


def test_no_runtime_sanitizer_exists() -> None:
    """Positive wording is authored into the source banks, never produced by a
    runtime transform. A sanitizer would rewrite prompts on the way to the
    provider and break the zero-loss byte-exact contract, so its absence is
    itself part of the contract."""
    assert not hasattr(packet_builder, "strip_negative_clauses")

    source = Path(packet_builder.__file__).read_text(encoding="utf-8")
    assert "strip_negative_clauses" not in source


def test_prompt_assembly_passes_recipe_fields_through_untransformed() -> None:
    """Zero-loss: assembly may concatenate authored text, never rewrite it."""
    source = inspect.getsource(packet_builder._assemble_structured_prompt_sections)

    for mutator in (".replace(", "re.sub(", "strip_negative", ".translate("):
        assert mutator not in source, f"assembly must not transform text ({mutator})"
