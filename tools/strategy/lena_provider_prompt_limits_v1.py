from __future__ import annotations

import copy
from types import MappingProxyType
from typing import Any


PARSER_SAFETY_LIMIT = "parser_safety_limit"
TEMPORARY_REPOSITORY_EXECUTION_POLICY = "temporary_repository_execution_policy"
PER_INPUT_SECURITY_BOUND = "per_input_security_bound"
RETRY_READINESS_HEADROOM = "retry_readiness_headroom"
LEGACY_DEPRECATED_LIMIT = "legacy_deprecated_limit"

# No numeric limit in this module is represented as provider-required. The
# provider field names the execution surface whose repository policy consumes it.
PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS = 4096
HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS = 4096

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

# Retained historical values document the retired fitter and proof-packet
# behavior. They are not active execution policy or provider constraints.
HIGGSFIELD_STRUCTURED_PROMPT_SECTION_FITTER_MAX_CHARS = MappingProxyType({
    "Subject": 540,
    "Action": 330,
    "Environment": 360,
    "Cinematography": 230,
    "Lighting/Style": 300,
    "Technical": 500,
})
HIGGSFIELD_PROOF_PACKET_PROMPT_BUDGET_WITH_ENVIRONMENT_CHARS = 1780
HIGGSFIELD_PROOF_PACKET_PROMPT_BUDGET_WITHOUT_ENVIRONMENT_CHARS = 1940
HIGGSFIELD_STYLE_BANK_PROMPT_MIN_BASE_CHARS = 1700


class PromptExecutionPolicyError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def require_higgsfield_prompt_length_within_execution_policy(prompt_length: int) -> int:
    if type(prompt_length) is not int or prompt_length < 0:
        raise PromptExecutionPolicyError(
            "higgsfield_prompt_length_invalid",
            "Higgsfield provider prompt length must be a nonnegative integer",
        )
    if prompt_length > HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS:
        raise PromptExecutionPolicyError(
            "higgsfield_prompt_execution_policy_exceeded",
            (
                f"zero-loss Higgsfield prompt is {prompt_length} characters; "
                "the temporary repository execution policy maximum is "
                f"{HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS}. Author the "
                "recipe to fit; truncation and automatic shortening are forbidden"
            ),
        )
    return prompt_length


def require_higgsfield_prompt_within_execution_policy(prompt: str) -> str:
    if not isinstance(prompt, str):
        raise PromptExecutionPolicyError(
            "higgsfield_prompt_type_invalid",
            "Higgsfield provider prompt must be a string",
        )
    require_higgsfield_prompt_length_within_execution_policy(len(prompt))
    return prompt


def _entry(
    *,
    value: Any,
    provider: str,
    purpose: str,
    classification: str,
    status: str,
    known_consumers: tuple[str, ...],
    description: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "provider": provider,
        "purpose": purpose,
        "classification": classification,
        "provider_required": False,
        "status": status,
        "known_consumers": list(known_consumers),
        "description": description,
    }


_LIMIT_CLASSIFICATIONS = {
    "provider_prompt_parser_safety_max_chars": _entry(
        value=PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS,
        provider="shared_provider_prompt_grammar",
        purpose="bound complete-prompt grammar parsing before full-string work",
        classification=PARSER_SAFETY_LIMIT,
        status="active",
        known_consumers=(
            "tools/strategy/lena_pose_provenance_v1.py",
            "tools/strategy/lena_audit_provider_prompt_budget_v1.py",
        ),
        description="Maximum complete prompt length accepted by the repository grammar parser.",
    ),
    "higgsfield_prompt_execution_policy_max_chars": _entry(
        value=HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS,
        provider="higgsfield",
        purpose="temporary repository execution budget for the Higgsfield-forward packet path",
        classification=TEMPORARY_REPOSITORY_EXECUTION_POLICY,
        status="temporary_active",
        known_consumers=(
            "tools/strategy/lena_build_content_packet_dryrun_v1.py",
            "tools/strategy/lena_audit_autonomous_generation_readiness_v1.py",
            "tools/strategy/lena_audit_provider_prompt_budget_v1.py",
            "tools/strategy/lena_prepare_higgsfield_retry_handoff_v1.py",
            "tools/strategy/lena_execute_retry_decision_v1.py",
        ),
        description="Temporary zero-loss repository execution budget; it is not a Higgsfield provider maximum.",
    ),
    "provider_section_body_max_chars": _entry(
        value=PROVIDER_SECTION_BODY_MAX_CHARS,
        provider="shared_provider_prompt_grammar",
        purpose="bound one canonical provider section body before normalization",
        classification=PER_INPUT_SECURITY_BOUND,
        status="active",
        known_consumers=(
            "tools/strategy/lena_pose_provenance_v1.py",
            "tools/strategy/lena_audit_provider_prompt_budget_v1.py",
        ),
        description="Pre-normalization security bound for one canonical provider section body.",
    ),
    "provider_recipe_field_max_chars": _entry(
        value=dict(PROVIDER_RECIPE_FIELD_MAX_CHARS),
        provider="higgsfield",
        purpose="bound each recipe-derived provider input before normalization",
        classification=PER_INPUT_SECURITY_BOUND,
        status="active",
        known_consumers=("tools/strategy/lena_build_content_packet_dryrun_v1.py",),
        description="Pre-normalization security bounds for recipe-derived provider inputs.",
    ),
    "provider_recipe_input_aggregate_max_chars": _entry(
        value=PROVIDER_RECIPE_INPUT_AGGREGATE_MAX_CHARS,
        provider="higgsfield",
        purpose="bound aggregate recipe-derived provider input before normalization",
        classification=PER_INPUT_SECURITY_BOUND,
        status="active",
        known_consumers=("tools/strategy/lena_build_content_packet_dryrun_v1.py",),
        description="Aggregate pre-normalization security bound for recipe-derived provider inputs.",
    ),
    "retry_prompt_headroom_hard_block_below": _entry(
        value=RETRY_PROMPT_HEADROOM_HARD_BLOCK_BELOW,
        provider="higgsfield",
        purpose="block retry preparation when execution-budget headroom is too small",
        classification=RETRY_READINESS_HEADROOM,
        status="active",
        known_consumers=(
            "tools/strategy/lena_audit_autonomous_generation_readiness_v1.py",
            "tools/strategy/lena_prepare_higgsfield_retry_handoff_v1.py",
        ),
        description="Repository readiness hard block for remaining execution-budget headroom.",
    ),
    "retry_prompt_headroom_warning_below": _entry(
        value=RETRY_PROMPT_HEADROOM_WARNING_BELOW,
        provider="higgsfield",
        purpose="warn when retry execution-budget headroom is low",
        classification=RETRY_READINESS_HEADROOM,
        status="active",
        known_consumers=(
            "tools/strategy/lena_audit_autonomous_generation_readiness_v1.py",
            "tools/strategy/lena_prepare_higgsfield_retry_handoff_v1.py",
        ),
        description="Repository readiness warning for remaining execution-budget headroom.",
    ),
    "higgsfield_structured_prompt_section_fitter_max_chars": _entry(
        value=dict(HIGGSFIELD_STRUCTURED_PROMPT_SECTION_FITTER_MAX_CHARS),
        provider="higgsfield",
        purpose="document retired per-section fitter output",
        classification=LEGACY_DEPRECATED_LIMIT,
        status="deprecated_not_used_for_provider_execution",
        known_consumers=(),
        description="Historical fitter budgets retained only for compatibility analysis.",
    ),
    "higgsfield_proof_packet_prompt_budget_with_environment_chars": _entry(
        value=HIGGSFIELD_PROOF_PACKET_PROMPT_BUDGET_WITH_ENVIRONMENT_CHARS,
        provider="higgsfield",
        purpose="document the retired proof-packet budget when an environment was bound",
        classification=LEGACY_DEPRECATED_LIMIT,
        status="deprecated_not_used_for_provider_execution",
        known_consumers=(),
        description="Historical proof-packet budget retained only for compatibility analysis.",
    ),
    "higgsfield_proof_packet_prompt_budget_without_environment_chars": _entry(
        value=HIGGSFIELD_PROOF_PACKET_PROMPT_BUDGET_WITHOUT_ENVIRONMENT_CHARS,
        provider="higgsfield",
        purpose="document the retired proof-packet budget when no environment was bound",
        classification=LEGACY_DEPRECATED_LIMIT,
        status="deprecated_not_used_for_provider_execution",
        known_consumers=(),
        description="Historical proof-packet budget retained only for compatibility analysis.",
    ),
    "higgsfield_style_bank_prompt_min_base_chars": _entry(
        value=HIGGSFIELD_STYLE_BANK_PROMPT_MIN_BASE_CHARS,
        provider="higgsfield",
        purpose="document the retired base-prompt floor after style-bank reservation",
        classification=LEGACY_DEPRECATED_LIMIT,
        status="deprecated_not_used_for_provider_execution",
        known_consumers=(),
        description="Historical style-bank floor retained only for compatibility analysis.",
    ),
}


def limit_classification_report() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_LIMIT_CLASSIFICATIONS)
