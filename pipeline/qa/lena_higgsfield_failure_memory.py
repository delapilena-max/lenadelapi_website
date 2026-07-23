from __future__ import annotations

# Read-only Higgsfield failure-memory aggregator for Lena's curator.
#
# Correlates two artifact types that already exist and are already written
# by already-committed code -- no new persisted file, no new schema, no
# database:
#   pipeline/asset_review/lena/<date>/<slot_id>_qa.json     (QA verdicts)
#   pipeline/higgsfield_debug/<date>/<slot_id>/result_manifest.json
#                                                            (generation metadata)
#
# Pattern key (v1, deliberately narrow): (lane, pose_body_language_id).
# Not wardrobe/expression/environment -- do not add those dimensions
# without direct implementation evidence they're needed (per explicit
# instruction).
#
# Evidence discipline (explicit, load-bearing):
#   - 1 structured fail, 0 pass  -> SOFT FLAG only, never excluded.
#   - 2+ structured fails, 0 pass -> HARD EXCLUDE.
#   - Any pass on the same pattern -> never hard-excluded, regardless of
#     fail count (a real counterexample means the pattern is not proven
#     unreliable).
#   - Only records with overall in {"pass","fail"} count as evidence.
#     "unreviewed" contributes nothing either way.
#   - Chat history / informal review is NEVER treated as evidence -- only
#     what is actually on disk in a real, schema-valid QA JSON file.
#   - A QA record with no matching Higgsfield manifest (e.g. a legacy
#     record) is skipped, not guessed -- recorded in `skipped` with an
#     explicit reason, never silently dropped.
#   - A QA record that fails to parse or fails lena_photo_qa.validate_qa_
#     result() is skipped, not counted as evidence, and recorded in
#     `skipped` with an explicit reason.
#
# This module does not modify pipeline/qa/lena_photo_qa.py, Rule Zero
# (tools/lena_build_publish_packet_v1.py), or the Higgsfield executor.

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pipeline.qa import lena_photo_qa

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSET_REVIEW_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
DEFAULT_HIGGSFIELD_DEBUG_ROOT = ROOT / "pipeline" / "higgsfield_debug"

PatternKey = Tuple[str, str]  # (lane, pose_body_language_id)

# Evidence thresholds -- explicit, load-bearing, not tunable without
# revisiting the evidence discipline in the module docstring above.
HARD_EXCLUDE_MIN_FAILS = 2
HARD_EXCLUDE_MAX_PASSES = 0  # any pass at all disqualifies a hard exclude


def _iter_qa_record_paths(asset_review_root: Path) -> List[Path]:
    """Every *_qa.json under pipeline/asset_review/lena/<date>/ -- does not
    match the *.attempt1_failed_*.json / *.attempt2_failed_*.json archive
    variants (those don't end in exactly '_qa.json'), and does not match
    the unrelated v2_6-era asset-approval-gate report files (different
    filenames entirely)."""
    if not asset_review_root.exists():
        return []
    return sorted(asset_review_root.glob("*/*_qa.json"))


def _manifest_path_for(qa_path: Path, higgsfield_debug_root: Path) -> Optional[Tuple[str, str, Path]]:
    """Derives (date_str, slot_id, manifest_path) from a QA record's own
    path shape (pipeline/asset_review/lena/<date>/<slot_id>_qa.json) --
    does not trust or require the QA JSON's own internal fields, since
    older schema versions don't reliably carry slot_id/date in a uniform
    way. Returns None if the path shape itself doesn't match (defensive,
    should not happen given _iter_qa_record_paths's glob)."""
    date_str = qa_path.parent.name
    filename = qa_path.name
    suffix = "_qa.json"
    if not filename.endswith(suffix):
        return None
    slot_id = filename[: -len(suffix)]
    manifest_path = higgsfield_debug_root / date_str / slot_id / "result_manifest.json"
    return date_str, slot_id, manifest_path


def compute_higgsfield_failure_memory(
    asset_review_root: Path = DEFAULT_ASSET_REVIEW_ROOT,
    higgsfield_debug_root: Path = DEFAULT_HIGGSFIELD_DEBUG_ROOT,
) -> Dict[str, Any]:
    """Read-only. Scans every real QA record, correlates the Higgsfield-
    sourced ones to their generation manifest, and aggregates pass/fail
    counts per (lane, pose_body_language_id). Returns a dict with
    pattern_counts, soft_flagged_patterns, hard_excluded_patterns, and a
    skipped list carrying an explicit reason for every record that did not
    contribute evidence."""
    pattern_counts: Dict[PatternKey, Dict[str, int]] = {}
    skipped: List[Dict[str, str]] = []
    contributing_records: List[Dict[str, Any]] = []

    for qa_path in _iter_qa_record_paths(asset_review_root):
        resolved = _manifest_path_for(qa_path, higgsfield_debug_root)
        if resolved is None:
            skipped.append({"qa_path": str(qa_path), "reason": "unexpected filename shape, not a *_qa.json record"})
            continue
        date_str, slot_id, manifest_path = resolved

        # Check manifest existence FIRST, purely from the path derived above
        # -- before ever parsing the QA JSON. This means a non-Higgsfield
        # legacy record is skipped with an accurate "not
        # Higgsfield" reason, not misreported as "invalid" just because it
        # predates a newer schema field. It also avoids spending validation
        # effort on records this aggregator can never use regardless.
        if not manifest_path.exists():
            skipped.append({
                "qa_path": str(qa_path),
                "reason": f"no Higgsfield result_manifest.json at {manifest_path} -- "
                          "not a Higgsfield-sourced record, "
                          "not Higgsfield failure evidence",
            })
            continue

        try:
            qa_result = json.loads(qa_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            skipped.append({"qa_path": str(qa_path), "reason": f"failed to parse QA JSON: {exc}"})
            continue

        if not isinstance(qa_result, dict):
            skipped.append({"qa_path": str(qa_path), "reason": "QA JSON did not contain an object"})
            continue

        ok, errors = lena_photo_qa.validate_qa_result(qa_result)
        if not ok:
            skipped.append({
                "qa_path": str(qa_path),
                "reason": f"QA record failed validate_qa_result(), not treated as evidence: {errors}",
            })
            continue

        overall = qa_result.get("overall")
        if overall not in ("pass", "fail"):
            skipped.append({"qa_path": str(qa_path), "reason": f"overall={overall!r}, not pass/fail -- no evidence to contribute"})
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            skipped.append({"qa_path": str(qa_path), "reason": f"failed to parse manifest {manifest_path}: {exc}"})
            continue

        if not isinstance(manifest, dict):
            skipped.append({"qa_path": str(qa_path), "reason": f"manifest at {manifest_path} did not contain an object"})
            continue

        lane = manifest.get("lane")
        pose_id = manifest.get("pose_body_language_id")
        if not lane or not pose_id:
            skipped.append({
                "qa_path": str(qa_path),
                "reason": f"manifest missing lane and/or pose_body_language_id (lane={lane!r}, pose_body_language_id={pose_id!r}) -- cannot form a pattern key, not guessed",
            })
            continue

        key: PatternKey = (str(lane), str(pose_id))
        counts = pattern_counts.setdefault(key, {"pass": 0, "fail": 0})
        counts[overall] += 1
        contributing_records.append({"qa_path": str(qa_path), "slot_id": slot_id, "date": date_str, "pattern_key": key, "overall": overall})

    soft_flagged: List[PatternKey] = []
    hard_excluded: List[PatternKey] = []
    for key, counts in pattern_counts.items():
        fails, passes = counts["fail"], counts["pass"]
        if fails >= HARD_EXCLUDE_MIN_FAILS and passes <= HARD_EXCLUDE_MAX_PASSES:
            hard_excluded.append(key)
        elif fails == 1 and passes == 0:
            soft_flagged.append(key)
        # fails==0, or (fails>=1 and passes>=1): neither soft-flagged nor
        # hard-excluded -- a real pass is a real counterexample.

    return {
        "pattern_counts": {f"{lane}::{pose_id}": counts for (lane, pose_id), counts in pattern_counts.items()},
        "soft_flagged_patterns": sorted(soft_flagged),
        "hard_excluded_patterns": sorted(hard_excluded),
        "contributing_records": contributing_records,
        "skipped": skipped,
    }


def pattern_key_for_image(image: Dict[str, Any]) -> Optional[PatternKey]:
    """Same key shape as compute_higgsfield_failure_memory(), derived from
    a curator candidate's own image dict (which already carries 'lane' and
    'pose_body_language_id' -- see tools/diagnostics/
    lena_higgsfield_photo_dump_dryrun.py's build_report()). Returns None if
    either field is missing, so callers can skip the check rather than
    guess a key."""
    lane = image.get("lane")
    pose_id = image.get("pose_body_language_id")
    if not lane or not pose_id:
        return None
    return (str(lane), str(pose_id))
