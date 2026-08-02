from __future__ import annotations

from copy import deepcopy

from pipeline.media_properties.interstitial_travel_bureau.artifacts import EpisodeStore
from pipeline.media_properties.interstitial_travel_bureau.novelty import evaluate_novelty, genome_snapshot
from tests.itb_helpers import PILOT_ROOT


def _entry(episode_id: str, snapshot: dict, lockouts=None):
    return {
        "episode_id": episode_id,
        "creative_genome": deepcopy(snapshot),
        "future_lockouts": list(lockouts or []),
    }


def test_current_episode_entry_is_excluded_from_comparison():
    genome = EpisodeStore(PILOT_ROOT).load("bureau_creative_genome_v1").data
    report = evaluate_novelty(genome, [_entry("itb_ep_001", genome_snapshot(genome))], proposed_episode_id="itb_ep_001")
    assert report["disposition"] == "approve"
    assert report["episodes_compared"] == 0


def test_more_than_two_major_dimensions_from_previous_two_rejects():
    genome = EpisodeStore(PILOT_ROOT).load("bureau_creative_genome_v1").data
    snapshot = genome_snapshot(genome)
    different = {key: f"different_{key}" for key in snapshot}
    different["instruction_verbs"] = ["different_verb"]
    for key in ("environment_family", "hazard_family", "entity_silhouette"):
        different[key] = snapshot[key]
    report = evaluate_novelty(genome, [_entry("itb_ep_998", different)], proposed_episode_id="itb_ep_001")
    assert report["disposition"] == "reject"
    assert report["overlap_by_episode"][0]["overlap_count"] == 3


def test_similarity_is_limited_to_last_thirty_entries():
    genome = EpisodeStore(PILOT_ROOT).load("bureau_creative_genome_v1").data
    snapshot = genome_snapshot(genome)
    entries = [_entry(f"itb_ep_{index:03d}", snapshot) for index in range(2, 34)]
    report = evaluate_novelty(genome, entries, proposed_episode_id="itb_ep_001")
    assert report["episodes_compared"] == 30
    assert report["maximum_similarity_basis_points"] == 10000


def test_active_lockout_rejects_with_explanation():
    genome = EpisodeStore(PILOT_ROOT).load("bureau_creative_genome_v1").data
    snapshot = genome_snapshot(genome)
    for field in snapshot:
        snapshot[field] = ["other"] if field == "instruction_verbs" else f"other_{field}"
    report = evaluate_novelty(genome, [_entry("itb_ep_998", snapshot, ["premature_reflection"])], proposed_episode_id="itb_ep_001")
    assert report["disposition"] == "reject"
    assert report["lockout_violations"] == ["premature_reflection"]
    assert report["semantic_review_still_required"] is True
