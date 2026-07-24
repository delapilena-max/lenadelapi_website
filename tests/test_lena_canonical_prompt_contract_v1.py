"""Canonical Lena prompt contract: definition, enforcement, and full sweep.

One authoritative contract governs every Lena provider prompt -- proof, retry,
and autonomous alike. These tests prove:

  * all 19 recipes x 18 poses (342 combinations) satisfy it;
  * no prompt path can reach a provider without passing it;
  * it validates and never rewrites, so zero-loss byte-exactness holds.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from pipeline.prompting import lena_canonical_prompt_contract_v1 as contract
from tests.fixtures.lena_pose_provenance import (
    static_expression_provenance,
    static_pose_provenance,
)
from tools.strategy import lena_audit_provider_prompt_budget_v1 as audit
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder

import pipeline.higgsfield_lena_api_executor as executor


def _banks():
    recipes = json.loads(Path(packet_builder.RECIPE_BANK).read_text(encoding="utf-8-sig"))["recipes"]
    poses = json.loads((audit.ROOT / audit.POSE_BANK_REPO_PATH).read_text(encoding="utf-8-sig"))["combos"]
    return recipes, poses


def _pose_binding(entry: dict) -> dict:
    binding = static_pose_provenance()
    binding.update({
        "pose_body_language_id": entry["pose_body_language_id"],
        "pose_body_language_label": entry["label"],
        "pose_text": entry["text"],
        "pose_text_sha256": hashlib.sha256(entry["text"].encode("utf-8")).hexdigest(),
    })
    core = {k: v for k, v in binding.items() if k != "pose_provenance_fingerprint_sha256"}
    binding["pose_provenance_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return binding


def _expression_binding() -> dict:
    return static_expression_provenance()


# --------------------------------------------------------------------------
# Full 342-combination sweep
# --------------------------------------------------------------------------

def test_all_342_recipe_pose_combinations_satisfy_the_canonical_contract() -> None:
    recipes, poses = _banks()
    assert len(recipes) == 19
    assert len(poses) == 18

    checked = 0
    violations: list[tuple[str, str, str]] = []
    for recipe in recipes:
        for pose in poses:
            prompt = packet_builder.build_structured_provider_prompt(
                recipe,
                pose_binding=_pose_binding(pose),
                expression_binding=_expression_binding(),
            )
            try:
                contract.validate_prompt_contract(prompt)
            except contract.PromptContractError as exc:
                violations.append((recipe["id"], pose["pose_body_language_id"], exc.code))
            checked += 1

    assert checked == 342
    assert violations == []


def test_every_combination_carries_all_required_sections() -> None:
    recipes, poses = _banks()
    for recipe in recipes:
        for pose in poses:
            prompt = packet_builder.build_structured_provider_prompt(
                recipe,
                pose_binding=_pose_binding(pose),
                expression_binding=_expression_binding(),
            )
            sections = contract.validate_prompt_contract(prompt)
            for label in contract.REQUIRED_SECTIONS:
                assert sections[label].strip(), f"{recipe['id']}/{label} empty"


# --------------------------------------------------------------------------
# Contract semantics
# --------------------------------------------------------------------------

def _valid_prompt() -> str:
    recipes, poses = _banks()
    return packet_builder.build_structured_provider_prompt(
        recipes[0], pose_binding=_pose_binding(poses[0]), expression_binding=_expression_binding()
    )


def test_contract_validates_a_real_production_prompt() -> None:
    contract.validate_prompt_contract(_valid_prompt())


def test_contract_never_mutates_the_prompt() -> None:
    """Zero-loss: validation must be pure inspection."""
    prompt = _valid_prompt()
    before = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    contract.validate_prompt_contract(prompt)
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == before


@pytest.mark.parametrize("missing", ["Subject", "Action", "Expression", "Environment", "Technical"])
def test_contract_rejects_a_missing_required_section(missing: str) -> None:
    prompt = _valid_prompt()
    kept = [ln for ln in prompt.split("\n") if not ln.startswith(f"[{missing}]:")]
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract("\n".join(kept))
    assert excinfo.value.code == "prompt_missing_required_section"


@pytest.mark.parametrize(
    "placeholder",
    ["<FULL PROMPT>", "TBD", "TODO", "placeholder", "authority required"],
)
def test_contract_rejects_placeholders(placeholder: str) -> None:
    prompt = _valid_prompt().replace("[Technical]: ", f"[Technical]: {placeholder} ")
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(prompt)
    assert excinfo.value.code == "prompt_placeholder_present"


@pytest.mark.parametrize(
    "negative",
    ["No open jeans.", "Never use a ring light.", "Avoid plastic skin.", ", no exposed zipper"],
)
def test_contract_rejects_negative_wording(negative: str) -> None:
    prompt = _valid_prompt().rstrip() + " " + negative
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(prompt)
    assert excinfo.value.code == "prompt_negative_wording"


def test_contract_requires_the_canonical_identity_body_block_verbatim() -> None:
    prompt = _valid_prompt()
    assert contract.CANONICAL_LENA_IDENTITY_BODY_BLOCK in prompt
    altered = prompt.replace(
        contract.CANONICAL_LENA_IDENTITY_BODY_BLOCK,
        contract.CANONICAL_LENA_IDENTITY_BODY_BLOCK.replace("bombshell", "woman"),
    )
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(altered)
    assert excinfo.value.code == "prompt_canonical_identity_block_missing"


def test_contract_rejects_missing_canonical_identity_body_block() -> None:
    prompt = _valid_prompt()
    stripped = prompt.replace(contract.CANONICAL_LENA_IDENTITY_BODY_BLOCK, "")
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(stripped)
    assert excinfo.value.code == "prompt_canonical_identity_block_missing"


@pytest.mark.parametrize(
    "term",
    ["narrow hips", "slim-hipped", "thigh gap", "flat butt", "petite frame"],
)
def test_contract_rejects_terms_that_contradict_the_canonical_identity_block(term: str) -> None:
    prompt = _valid_prompt().rstrip() + f" She has a {term} today."
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(prompt)
    assert excinfo.value.code == "prompt_identity_contradiction"


def test_contract_rejects_prompts_over_the_max_char_ceiling() -> None:
    prompt = _valid_prompt()
    padded = prompt[:-1] + (" filler word" * 400) + "."
    assert len(padded) > contract.MAX_PROMPT_CHARS
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(padded)
    assert excinfo.value.code == "prompt_exceeds_max_chars"


def test_contract_requires_identity_and_soul_anchor() -> None:
    prompt = _valid_prompt()
    stripped = "\n".join(
        "[Subject]: A woman standing in a room with everyday detail."
        if ln.startswith("[Subject]:") else ln
        for ln in prompt.split("\n")
    )
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(stripped)
    assert excinfo.value.code in {"prompt_identity_missing", "prompt_soul_anchor_missing"}


def test_contract_rejects_an_empty_section_body() -> None:
    prompt = _valid_prompt()
    blanked = "\n".join(
        "[Environment]: " if ln.startswith("[Environment]:") else ln
        for ln in prompt.split("\n")
    )
    with pytest.raises(contract.PromptContractError) as excinfo:
        contract.validate_prompt_contract(blanked)
    assert excinfo.value.code == "prompt_section_incomplete"


# --------------------------------------------------------------------------
# No prompt path may bypass the contract
# --------------------------------------------------------------------------

def test_executor_gates_every_live_generation_on_the_contract() -> None:
    """run_live must validate the contract before any provider work."""
    source = inspect.getsource(executor.run_live)
    assert "canonical_prompt_contract.validate_prompt_contract" in source

    contract_pos = source.index("canonical_prompt_contract.validate_prompt_contract")
    launcher_pos = source.index("resolve_provider_launcher")
    subprocess_pos = source.index("subprocess.run")
    assert contract_pos < launcher_pos, "contract gate must precede launcher resolution"
    assert contract_pos < subprocess_pos, "contract gate must precede any provider call"


def test_executor_rejects_a_contract_violating_prompt_before_spend(tmp_path, monkeypatch) -> None:
    # Isolate ROOT: run_live persists the submitted prompt to
    # pipeline/higgsfield_debug before the contract gate raises (the SHA
    # binding is checked/persisted first so its own, more specific failure
    # surfaces first -- see the executor's HARD GATE comment). Without this,
    # the test would write into the real repo's runtime artifacts.
    monkeypatch.setattr(executor, "ROOT", tmp_path)
    monkeypatch.setattr(
        executor.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )
    # A valid generation_reference binding and a matching prompt_sha256 are
    # required so execution reaches the prompt-contract gate this test
    # targets, rather than tripping the earlier (and unrelated)
    # generation-reference-binding or approval-SHA-binding checks first.
    invalid_prompt = "[Subject]: Lena Soul. No open jeans."
    source = {
        "image": {
            "image_prompt": invalid_prompt,
            "prompt_sha256": hashlib.sha256(invalid_prompt.encode("utf-8")).hexdigest(),
            "generation_reference": executor.soul_cinema_contract.load_generation_reference_binding(),
        }
    }

    with pytest.raises(executor.ProviderCallError) as excinfo:
        executor.run_live("2026-07-23", "slot", source, executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID)

    assert excinfo.value.stage.startswith("prompt_contract_")
    assert excinfo.value.subprocess_start_attempted is False
    assert excinfo.value.provider_submission_may_have_occurred is False


def test_production_prompt_builder_enforces_contract_when_fully_bound() -> None:
    source = inspect.getsource(packet_builder.build_structured_provider_prompt)
    assert "canonical_prompt_contract.validate_prompt_contract" in source


def test_no_runtime_sanitizer_exists() -> None:
    """A sanitizer would silently rewrite prompts and break zero-loss."""
    assert not hasattr(packet_builder, "strip_negative_clauses")
    source = Path(packet_builder.__file__).read_text(encoding="utf-8")
    assert "strip_negative_clauses" not in source
