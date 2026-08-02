from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import ITBContractError, Issue


NOVELTY_FIELDS = (
    "environment_family",
    "hazard_family",
    "entity_silhouette",
    "dominant_scale",
    "palette_family",
    "camera_grammar",
    "humor_mechanism",
    "opening_structure",
    "ending_reveal",
    "instruction_verbs",
    "emotional_flavor",
    "thumbnail_grammar",
)


def genome_snapshot(genome: Mapping[str, Any]) -> dict[str, Any]:
    return {field: genome[field] for field in NOVELTY_FIELDS}


def _normalized(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(sorted(value))
    return value


def _overlap_fields(
    proposed: Mapping[str, Any], previous: Mapping[str, Any]
) -> list[str]:
    return [
        field
        for field in NOVELTY_FIELDS
        if _normalized(proposed[field]) == _normalized(previous[field])
    ]


def evaluate_novelty(
    proposed_genome: Mapping[str, Any],
    ledger_entries: Sequence[Mapping[str, Any]],
    *,
    proposed_episode_id: str,
) -> dict[str, Any]:
    snapshot = genome_snapshot(proposed_genome)
    weights = proposed_genome["comparison_weights_basis_points"]
    weight_total = sum(weights[field] for field in NOVELTY_FIELDS)
    if weight_total != 10000:
        raise ITBContractError(
            Issue(
                code="novelty_weights_invalid",
                stage="novelty",
                message="Creative Genome comparison weights must total 10,000 basis points.",
                artifact_id=proposed_genome.get("artifact_id"),
                field_path="$/comparison_weights_basis_points",
                expected=10000,
                actual=weight_total,
            )
        )
    prior = [entry for entry in ledger_entries if entry["episode_id"] != proposed_episode_id][-30:]
    comparisons: list[dict[str, Any]] = []
    for entry in prior:
        overlap = _overlap_fields(snapshot, entry["creative_genome"])
        score = sum(weights[field] for field in overlap)
        comparisons.append(
            {
                "episode_id": entry["episode_id"],
                "overlap_fields": overlap,
                "overlap_count": len(overlap),
                "similarity_basis_points": score,
            }
        )
    lockouts = sorted(
        {
            tag
            for entry in prior
            for tag in entry["future_lockouts"]
            if tag in proposed_genome["novelty_tags"]
            or tag in proposed_genome["repetition_lockouts"]
        }
    )
    recent_violations = [item for item in comparisons[-2:] if item["overlap_count"] > 2]
    maximum_similarity = max(
        (item["similarity_basis_points"] for item in comparisons), default=0
    )
    reasons: list[str] = []
    if recent_violations:
        reasons.append("More than two major Creative Genome dimensions repeat from a previous-two episode.")
    if lockouts:
        reasons.append("The proposal violates active continuity-ledger lockouts.")
    if recent_violations or lockouts:
        disposition = "reject"
    elif maximum_similarity >= 5000:
        disposition = "revise"
        reasons.append("Thirty-episode weighted similarity reaches the revision threshold.")
    else:
        disposition = "approve"
        reasons.append("No previous-two repetition or lockout threshold is exceeded.")
    return {
        "ok": disposition == "approve",
        "report_type": "itb_novelty_check_v1",
        "episode_id": proposed_episode_id,
        "episodes_compared": len(comparisons),
        "comparison_window_limit": 30,
        "overlap_by_episode": comparisons,
        "maximum_similarity_basis_points": maximum_similarity,
        "lockout_violations": lockouts,
        "disposition": disposition,
        "reasons": reasons,
        "semantic_review_still_required": True,
    }
