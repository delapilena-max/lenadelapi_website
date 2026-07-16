from __future__ import annotations

import pytest

from pipeline.prompting.lena_prompt_brain import (
    HIGGSFIELD_BODY_SILHOUETTE_ANCHOR,
    HIGGSFIELD_FRAMING_LINE,
)
from tools.diagnostics import lena_higgsfield_photo_dump_dryrun as photo_dump
from tools.diagnostics import lena_higgsfield_prompt_library_dryrun as prompt_library


DATE = "2026-07-15"


def _base_package(prompt: str) -> dict:
    return {
        "image_prompt": prompt,
        "negative_prompt_enabled": False,
        "photo_dump_low_hook_terms_found": [],
        "photo_dump_hook_terms_found": ["hook"],
        "photo_dump_mood_hook_terms_found": [],
        "photo_dump_hook_pass": True,
        "photo_dump_pose_scene_match_pass": True,
        "photo_dump_pose_scene_mismatch_terms_found": [],
    }


def _canonical_prompt(extra_tail: str = "") -> str:
    return (
        f"{HIGGSFIELD_FRAMING_LINE} "
        f"{HIGGSFIELD_BODY_SILHOUETTE_ANCHOR} "
        "Scene: neutral studio-adjacent realism. "
        "Wardrobe: tailored dress. "
        "Pose: balanced stance. "
        "Expression: calm direct gaze. "
        "Camera: 50mm lifestyle portrait. "
        "Lighting: soft natural light. "
        f"Mood: candid and realistic.{extra_tail}"
    )


def test_canonical_anchor_does_not_trip_heavy_overcorrection() -> None:
    validation = photo_dump._validate_image(_base_package(_canonical_prompt()))

    assert validation["heavy_overcorrection_free"] is True
    assert validation["heavy_overcorrection_terms_found"] == []


def test_genuine_overcorrection_prompt_is_still_excluded() -> None:
    validation = photo_dump._validate_image(
        _base_package(_canonical_prompt(" fuller thighs beyond the canonical anchor."))
    )

    assert validation["heavy_overcorrection_free"] is False
    assert "fuller thighs" in validation["heavy_overcorrection_terms_found"]


def test_laundromat_prompt_remains_hard_excluded() -> None:
    pack = photo_dump.build_report(DATE, "lenagate20260715085620d1-pack000", 10)
    laundromat_image = pack["images"][5]
    assert laundromat_image["lane"] == "laundry day"
    assert "laundromat" in laundromat_image["image_prompt"].lower()
    assert "laundromat" in laundromat_image["validation"]["low_hook_terms_found"]

    reasons = prompt_library._hard_exclude_reasons(laundromat_image)

    assert any("laundromat" in reason for reason in reasons)


def test_curator_can_select_a_valid_prompt_and_keep_laundromat_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prompt_library,
        "compute_higgsfield_failure_memory",
        lambda: {
            "pattern_counts": {},
            "hard_excluded_patterns": [],
            "soft_flagged_patterns": [],
            "skipped": [],
        },
    )

    library = prompt_library.build_library_report(DATE, "lenagate20260715085620d1", 1, 10)
    curation = prompt_library.curate_top_prompts(library, 1)

    assert len(curation["selected"]) == 1
    assert curation["selected"][0]["image"]["slot_id"].startswith("lenagate20260715085620d1-pack000")
    assert curation["candidate_count"] > 0
