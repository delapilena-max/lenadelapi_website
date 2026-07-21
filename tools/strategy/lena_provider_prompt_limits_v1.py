from __future__ import annotations

import copy
from types import MappingProxyType
from typing import Any


PARSER_SAFETY_LIMIT = "parser_safety_limit"
TEMPORARY_REPOSITORY_EXECUTION_POLICY = "temporary_repository_execution_policy"
PER_INPUT_SECURITY_BOUND = "per_input_security_bound"
RETRY_READINESS_HEADROOM = "retry_readiness_headroom"
LEGACY_DEPRECATED_LIMIT = "legacy_deprecated_limit"

# This is a repository parser bound, not a published provider limit.
PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS = 4096

# This temporary repository policy descends from the historical Kling packet
# budget. It must not be represented as a Higgsfield requirement.
TEMPORARY_PROVIDER_PROMPT_EXECUTION_MAX_CHARS = 2499

PROVIDER_SECTION_BODY_MAX_CHARS = 2048
PROVIDER_RECIPE_FIELD_MAX_CHARS = MappingProxyType({
    "subject_pose": 768,
    "fashion_accessories": 896,
    "setting_background": 768,
    "environment_realism_notes": 512,
    "technical_keywords": 320,
    "style_lighting": 640,
    "negative_constraints": 768,
})
PROVIDER_RECIPE_INPUT_AGGREGATE_MAX_CHARS = 4096

RETRY_PROMPT_HEADROOM_HARD_BLOCK_BELOW = 30
RETRY_PROMPT_HEADROOM_WARNING_BELOW = 70

# These values remain wired into legacy production fitting until a later
# recipe-migration and zero-loss compiler change removes them.
LEGACY_STRUCTURED_SECTION_MAX_CHARS = MappingProxyType({
    "Subject": 540,
    "Action": 330,
    "Environment": 360,
    "Cinematography": 230,
    "Lighting/Style": 300,
    "Technical": 500,
})
LEGACY_PROOF_PROMPT_BUDGET_WITH_ENVIRONMENT = 1780
LEGACY_PROOF_PROMPT_BUDGET_WITHOUT_ENVIRONMENT = 1940
LEGACY_STYLE_BANK_MIN_BASE_PROMPT_CHARS = 1700


_LIMIT_CLASSIFICATIONS = {
    "provider_prompt_parser_safety_max_chars": {
        "classification": PARSER_SAFETY_LIMIT,
        "value": PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS,
        "provider_required": False,
        "status": "active",
        "description": "Maximum complete prompt length accepted by the repository grammar parser.",
    },
    "temporary_provider_prompt_execution_max_chars": {
        "classification": TEMPORARY_REPOSITORY_EXECUTION_POLICY,
        "value": TEMPORARY_PROVIDER_PROMPT_EXECUTION_MAX_CHARS,
        "provider_required": False,
        "status": "temporary",
        "description": "Conservative repository execution budget pending separately proven provider authority.",
    },
    "provider_section_body_max_chars": {
        "classification": PER_INPUT_SECURITY_BOUND,
        "value": PROVIDER_SECTION_BODY_MAX_CHARS,
        "provider_required": False,
        "status": "active",
        "description": "Pre-normalization security bound for one canonical provider section body.",
    },
    "provider_recipe_field_max_chars": {
        "classification": PER_INPUT_SECURITY_BOUND,
        "value": dict(PROVIDER_RECIPE_FIELD_MAX_CHARS),
        "provider_required": False,
        "status": "active",
        "description": "Pre-normalization security bounds for recipe-derived provider inputs.",
    },
    "provider_recipe_input_aggregate_max_chars": {
        "classification": PER_INPUT_SECURITY_BOUND,
        "value": PROVIDER_RECIPE_INPUT_AGGREGATE_MAX_CHARS,
        "provider_required": False,
        "status": "active",
        "description": "Aggregate pre-normalization security bound for recipe-derived provider inputs.",
    },
    "retry_prompt_headroom_hard_block_below": {
        "classification": RETRY_READINESS_HEADROOM,
        "value": RETRY_PROMPT_HEADROOM_HARD_BLOCK_BELOW,
        "provider_required": False,
        "status": "active",
        "description": "Repository readiness hard block for remaining execution-budget headroom.",
    },
    "retry_prompt_headroom_warning_below": {
        "classification": RETRY_READINESS_HEADROOM,
        "value": RETRY_PROMPT_HEADROOM_WARNING_BELOW,
        "provider_required": False,
        "status": "active",
        "description": "Repository readiness warning for remaining execution-budget headroom.",
    },
    "legacy_structured_section_max_chars": {
        "classification": LEGACY_DEPRECATED_LIMIT,
        "value": dict(LEGACY_STRUCTURED_SECTION_MAX_CHARS),
        "provider_required": False,
        "status": "deprecated_but_still_enforced",
        "description": "Historical fitter budgets retained only to preserve current prompt output.",
    },
    "legacy_proof_prompt_budget_with_environment": {
        "classification": LEGACY_DEPRECATED_LIMIT,
        "value": LEGACY_PROOF_PROMPT_BUDGET_WITH_ENVIRONMENT,
        "provider_required": False,
        "status": "deprecated",
        "description": "Historical proof-packet budget superseded on the current locked rebuild path.",
    },
    "legacy_proof_prompt_budget_without_environment": {
        "classification": LEGACY_DEPRECATED_LIMIT,
        "value": LEGACY_PROOF_PROMPT_BUDGET_WITHOUT_ENVIRONMENT,
        "provider_required": False,
        "status": "deprecated",
        "description": "Historical proof-packet budget superseded on the current locked rebuild path.",
    },
    "legacy_style_bank_min_base_prompt_chars": {
        "classification": LEGACY_DEPRECATED_LIMIT,
        "value": LEGACY_STYLE_BANK_MIN_BASE_PROMPT_CHARS,
        "provider_required": False,
        "status": "legacy",
        "description": "Historical style-bank fitter floor outside the current locked catalog path.",
    },
}


def limit_classification_report() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_LIMIT_CLASSIFICATIONS)
