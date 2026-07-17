from __future__ import annotations

import hashlib
import json
from typing import Any

from pipeline.presence import human_presence_prompt_plan_v1 as prompt_plan


SCHEMA_VERSION = "human_presence_candidate_ranking_v1"
SCORING_VERSION = "v1"
MAX_BONUS_PER_DIMENSION = 3
_PRESENCE_SELECTOR_ALLOWLISTS = {
    "sensual_presence": {
        "gaze",
        "anticipation",
        "movement",
        "confidence",
        "timing",
        "reaction",
        "rhythm",
        "voice",
        "framing",
        "safe framing",
    },
    "body_presentation": {
        "safe framing",
        "reference mode",
        "realistic proportions",
        "anatomy continuity",
        "full body presence",
        "face priority",
        "dynamic motion framing",
        "required realistic",
        "continuity",
        "adult",
    },
}


class HumanPresenceCandidateRankingError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise HumanPresenceCandidateRankingError(code, detail)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _normalize_text(value: Any) -> str:
    text = " ".join(str(value or "").replace("-", " ").replace("_", " ").split())
    return text.strip().lower()


def _field_map(observation: dict[str, Any], field_names: tuple[str, ...]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for field in field_names:
        value = observation.get(field)
        if value in (None, "", [], {}):
            continue
        mapped[field] = _normalize_text(value)
    return mapped


def _score_dimension(
    *,
    dimension: str,
    selector_terms: list[str],
    observation: dict[str, Any],
    field_names: tuple[str, ...],
) -> dict[str, Any]:
    fields = _field_map(observation, field_names)
    matched_selector_terms: list[str] = []
    matched_observed_fields: list[dict[str, Any]] = []
    unmatched_selector_terms: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()

    for raw_term in selector_terms:
        term = _normalize_text(raw_term)
        if not term:
            continue

        matched_field = None
        for field, field_text in fields.items():
            if term in field_text:
                matched_field = field
                break

        if matched_field is None:
            unmatched_selector_terms.append(term)
            continue

        pair = (term, matched_field)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        matched_selector_terms.append(term)
        matched_observed_fields.append(
            {
                "selector_term": term,
                "observed_field": matched_field,
                "observed_value": observation.get(matched_field),
            }
        )

    bonus = min(MAX_BONUS_PER_DIMENSION, len(matched_selector_terms))
    return {
        "dimension": dimension,
        "bonus": bonus,
        "selector_terms": [term for term in selector_terms if _normalize_text(term)],
        "matched_selector_terms": matched_selector_terms,
        "matched_observed_fields": matched_observed_fields,
        "unmatched_selector_terms": unmatched_selector_terms,
        "observed_fields": {field: observation.get(field) for field in field_names if field in observation},
    }


def _presence_selector_terms(plan: dict[str, Any], dimension: str) -> list[str]:
    section = plan.get(dimension, {})
    selector_terms = list(section.get("selector_terms", [])) if isinstance(section, dict) else []
    allowed = _PRESENCE_SELECTOR_ALLOWLISTS.get(dimension)
    if allowed is None:
        return selector_terms
    return [term for term in selector_terms if _normalize_text(term) in allowed]


def plan_fingerprint_sha256(plan: dict[str, Any]) -> str:
    _require(isinstance(plan, dict), "invalid_presence_plan", "plan must be a JSON object")
    _require(
        plan.get("schema_version") == prompt_plan.SCHEMA_VERSION,
        "invalid_presence_plan",
        "plan schema version is not human_presence_prompt_plan_v1",
    )
    return hashlib.sha256(_canonical_bytes(plan)).hexdigest()


def score_candidate_presence_alignment(
    plan: dict[str, Any],
    observation: dict[str, Any],
) -> dict[str, Any]:
    _require(isinstance(plan, dict), "invalid_presence_plan", "plan must be a JSON object")
    _require(isinstance(observation, dict), "invalid_presence_observation", "observation must be a JSON object")
    fingerprint = plan_fingerprint_sha256(plan)

    dimension_sources: dict[str, tuple[str, ...]] = {
        "viewer_relationship": (
            "lane",
            "scene_action",
            "activity",
            "reference_mode",
            "camera_text",
            "lighting_text",
            "environment_id",
            "environment_name",
        ),
        "gaze_arc": (
            "expression_gaze_id",
            "expression_gaze_label",
            "expression_text",
            "scene_action",
            "activity",
            "camera_text",
        ),
        "expression_arc": (
            "expression_gaze_id",
            "expression_gaze_label",
            "expression_text",
            "pose_body_language_id",
            "pose_body_language_label",
            "scene_action",
            "activity",
        ),
        "performance_actions": (
            "pose_body_language_id",
            "pose_body_language_label",
            "scene_action",
            "activity",
        ),
        "movement_dynamics": (
            "pose_body_language_id",
            "pose_body_language_label",
            "reference_mode",
            "camera_text",
            "lighting_text",
        ),
        "sensual_presence": (
            "expression_gaze_id",
            "expression_gaze_label",
            "expression_text",
            "pose_body_language_id",
            "pose_body_language_label",
            "reference_mode",
            "camera_text",
            "lighting_text",
            "framing_text",
        ),
        "body_presentation": (
            "reference_mode",
            "camera_text",
            "framing_text",
        ),
        "temporal_beats": (
            "scene_action",
            "activity",
            "reference_mode",
            "camera_text",
            "caption_seed",
        ),
    }

    dimension_results: dict[str, dict[str, Any]] = {}
    for dimension, field_names in dimension_sources.items():
        section = plan.get(dimension, {})
        selector_terms = _presence_selector_terms(plan, dimension)
        dimension_results[dimension] = _score_dimension(
            dimension=dimension,
            selector_terms=selector_terms,
            observation=observation,
            field_names=field_names,
        )

    dimension_bonuses = {
        dimension: result["bonus"]
        for dimension, result in dimension_results.items()
    }
    matched_selector_terms = [
        term
        for result in dimension_results.values()
        for term in result["matched_selector_terms"]
    ]
    unmatched_dimensions = [
        dimension
        for dimension, result in dimension_results.items()
        if result["bonus"] == 0
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "scoring_version": SCORING_VERSION,
        "enabled": True,
        "plan_schema_version": plan.get("schema_version"),
        "plan_fingerprint_sha256": fingerprint,
        "observation_fingerprint_sha256": hashlib.sha256(_canonical_bytes(observation)).hexdigest(),
        "total_bonus": sum(dimension_bonuses.values()),
        "dimension_bonuses": dimension_bonuses,
        "dimension_results": dimension_results,
        "matched_selector_terms": matched_selector_terms,
        "unmatched_dimensions": unmatched_dimensions,
    }
