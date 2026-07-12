from __future__ import annotations

# One-time incident-remediation repair (2026-07-12) -- NOT a general-purpose
# production capability, not intended to be reused or extended.
#
# Background: the 2026-07-11 Meta-refresh incident exposed two defects
# (fixed at 4a8d2be0 and c7134c62). Bug 2's fix changed only how BRAND-NEW
# Architecture A metrics rows are created going forward. It did nothing for
# the four real rows that already existed before the fix landed -- those
# four rows still carry literal "0" placeholders in follows/profile_visits/
# completion_rate/replay_rate from the OLD upsert_metrics_row() convention,
# even though none of those four fields has ever actually been fetched by
# either Meta platform path (confirmed by direct code inspection: `follows`
# is referenced by no fetch call at all; profile_visits/completion_rate/
# replay_rate are permanently metric_unavailable in both fetch functions).
#
# Directly reproduced (read-only, no write) during Gap B scoping: because
# these four fields hold "0" instead of blank, row_has_unknown_scoring_
# inputs() incorrectly reports them as known, meaning a future live refresh
# could silently recompute a real score/classification from four values
# that were never actually measured -- the exact same "unknown treated as
# zero" failure mode as the original incident, via a different vector.
#
# This script repairs exactly that: it blanks those four fields on exactly
# the four proven-affected rows, identified only by their real, durable
# (date, slot_id, platform) identity -- never by row position. It never
# touches score/classification (already honestly repaired by the separate,
# earlier Restoration Step B), never touches any identity/provenance/
# creative-provenance/lane field, never touches any other row, and never
# touches the canonical CSV schema.
#
# Defaults to dry-run. --apply is required to write anything, and even
# then only after every precondition passes -- a candidate result is built
# and fully postcondition-checked in memory first; the real file is only
# ever replaced atomically (write to a temp candidate file, then
# os.replace()), never edited in place.

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from lena_sync_architecture_a_receipts_to_metrics_v1 import (  # noqa: E402
    METRIC_FIELDS,
    read_csv as sync_read_csv,
    write_csv as sync_write_csv,
)
from lena_meta_refresh_feedback_v1 import row_has_unknown_scoring_inputs  # noqa: E402

METRICS_PATH = ROOT / "pipeline" / "analytics" / "lena_post_metrics_v1_6_1.csv"
TMP_CANDIDATE_PATH = METRICS_PATH.with_suffix(".legacy_zero_repair_tmp.csv")

EXPECTED_HEAD = "966fa376"
EXPECTED_CSV_SHA256 = "e9e3c2b4274a99fd4ceb44a8c63203b190e35a65d850f0d916e313887f0f5e64"
EXPECTED_ROW_COUNT = 6

# Exact, durable, structured identity -- never row position, never a value
# pattern match. These are the four rows proven, by direct code/evidence
# inspection, to carry legacy pre-c7134c62 placeholder zeros.
TARGET_KEYS: Tuple[Tuple[str, str, str], ...] = (
    ("2026-07-05", "2026-07-05-01-photo", "Instagram Feed"),
    ("2026-07-07", "2026-07-07-03-photo", "Instagram Feed"),
    ("2026-07-09", "readypack0709-pack003-08-photo", "Instagram Feed"),
    ("2026-07-09", "readypack0709-pack007-00-photo-story", "Instagram Story"),
)

FIELDS_TO_BLANK = ("follows", "profile_visits", "completion_rate", "replay_rate")

# Exact pre-repair state every target row must currently show. Never
# blind-overwrites -- any target row whose real current values diverge
# from this exact expectation aborts the whole run.
EXPECTED_PRE_REPAIR_VALUES = {
    "follows": "0",
    "profile_visits": "0",
    "completion_rate": "0",
    "replay_rate": "0",
    "score": "0",
    "classification": "pending",
}

# Real, on-disk incident-evidence artifacts protected by this repair.
# The first three are the explicit "preserve, do not delete or rewrite"
# set named in pipeline/change_notes/NEXT_SESSION_START.md's incident
# checkpoint (that doc also records incident_lena_post_metrics_after_
# refresh_191355.csv's own SHA-256, confirmed matching below). The fourth
# (incident_lena_post_metrics_pre_step_b_restoration.csv) is a real,
# on-disk artifact from the same incident/recovery narrative -- created
# during the separate, earlier Restoration Step B -- not yet named in
# that checkpoint doc, but protected here anyway out of the same
# incident-evidence discipline, and reported distinctly as such.
INCIDENT_EVIDENCE = {
    "pipeline/analytics/lena_meta_feedback_reports/2026-07-11/lena_meta_feedback_refresh_191355.json": {
        "sha256": "c23c447914998699410845bc8cd90149d23374d654d669dcee9a950aa89bfb37",
        "size": 3172,
        "checkpoint_named": True,
    },
    "pipeline/state/lena_meta_feedback_ingestion_state_v1.json": {
        "sha256": "3c3d71210e169d39520886030c8c94b851dbf368b180fa269aaae1bebe03c721",
        "size": 932,
        "checkpoint_named": True,
    },
    "pipeline/analytics/lena_meta_feedback_reports/2026-07-11/incident_lena_post_metrics_after_refresh_191355.csv": {
        "sha256": "1599405b5f68be8e191bfcbb2ebc6e16e49cea05b1cd14bfdb135c98a12778f2",
        "size": 2213,
        "checkpoint_named": True,
    },
    "pipeline/analytics/lena_meta_feedback_reports/2026-07-11/incident_lena_post_metrics_pre_step_b_restoration.csv": {
        "sha256": "2e4b49a772df8f543cef10b902266a6b9c4eb654ea68ddffb80d55df397790e5",
        "size": 3399,
        "checkpoint_named": False,
    },
}


class PreconditionError(Exception):
    """Raised for any failed precondition. Never caught silently -- main()
    reports it and exits non-zero. No file is ever written when raised."""


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current_git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except Exception as exc:
        raise PreconditionError(f"could not read current git HEAD: {exc}") from exc


def _row_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (row.get("date", ""), row.get("slot_id", ""), row.get("platform", ""))


def verify_preconditions() -> Dict[str, Any]:
    """Read-only. Raises PreconditionError on any failed check. Returns a
    structured report of every check performed, for the dry-run report."""
    report: Dict[str, Any] = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            raise PreconditionError(f"{name}: {detail}")

    head = _current_git_head()
    check("git_head_matches_expected", head == EXPECTED_HEAD, f"expected {EXPECTED_HEAD}, got {head}")

    if not METRICS_PATH.exists():
        check("metrics_csv_exists", False, str(METRICS_PATH))
    check("metrics_csv_exists", True, str(METRICS_PATH))

    actual_sha256 = _sha256_of(METRICS_PATH)
    check(
        "metrics_csv_sha256_matches_expected",
        actual_sha256 == EXPECTED_CSV_SHA256,
        f"expected {EXPECTED_CSV_SHA256}, got {actual_sha256}",
    )

    with METRICS_PATH.open("r", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    check(
        "header_matches_canonical_34_columns",
        header == METRIC_FIELDS,
        f"expected {METRIC_FIELDS}, got {header}",
    )

    rows = sync_read_csv(METRICS_PATH)
    check("row_count_is_6", len(rows) == EXPECTED_ROW_COUNT, f"expected {EXPECTED_ROW_COUNT}, got {len(rows)}")

    rows_by_key: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        rows_by_key.setdefault(_row_key(row), []).append(row)

    for key in TARGET_KEYS:
        matches = rows_by_key.get(key, [])
        check(f"target_key_found_once:{key}", len(matches) == 1, f"found {len(matches)} matches for {key}")
        target_row = matches[0]
        for field, expected_value in EXPECTED_PRE_REPAIR_VALUES.items():
            actual_value = target_row.get(field)
            check(
                f"target_pre_value:{key}:{field}",
                actual_value == expected_value,
                f"expected {expected_value!r}, got {actual_value!r}",
            )

    for rel_path, evidence in INCIDENT_EVIDENCE.items():
        path = ROOT / rel_path
        exists = path.exists()
        check(f"incident_evidence_exists:{rel_path}", exists, "present" if exists else "file missing")
        if exists:
            actual_hash = _sha256_of(path)
            actual_size = path.stat().st_size
            check(
                f"incident_evidence_sha256:{rel_path}",
                actual_hash == evidence["sha256"],
                f"expected {evidence['sha256']}, got {actual_hash}",
            )
            check(
                f"incident_evidence_size:{rel_path}",
                actual_size == evidence["size"],
                f"expected {evidence['size']}, got {actual_size}",
            )

    report["ok"] = True
    report["git_head"] = head
    report["metrics_csv_sha256"] = actual_sha256
    report["row_count"] = len(rows)
    return report


def build_repaired_candidate(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pure function, no I/O. Returns (candidate_rows, cell_changes).
    Blanks FIELDS_TO_BLANK on exactly the TARGET_KEYS rows; every other
    row and every other field is returned byte-identical."""
    target_key_set = set(TARGET_KEYS)
    candidate_rows: List[Dict[str, Any]] = []
    cell_changes: List[Dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        key = _row_key(row)
        if key in target_key_set:
            for field in FIELDS_TO_BLANK:
                old_value = new_row.get(field, "")
                new_row[field] = ""
                if old_value != "":
                    cell_changes.append({"key": list(key), "field": field, "old": old_value, "new": ""})
        candidate_rows.append(new_row)
    return candidate_rows, cell_changes


def verify_postconditions(original_rows: List[Dict[str, Any]], candidate_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Read-only against both in-memory row lists. Raises PreconditionError
    (reused as the single failure type for this script) if any postcondition
    is violated. Returns a structured report."""
    report: Dict[str, Any] = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            raise PreconditionError(f"postcondition failed: {name}: {detail}")

    check("row_count_unchanged", len(original_rows) == len(candidate_rows) == EXPECTED_ROW_COUNT)

    target_key_set = set(TARGET_KEYS)
    original_by_key = {_row_key(r): r for r in original_rows}
    candidate_by_key = {_row_key(r): r for r in candidate_rows}
    check("same_keys", set(original_by_key) == set(candidate_by_key))

    total_changed_cells = 0
    unblocked_target_count = 0
    for key, cand in candidate_by_key.items():
        orig = original_by_key[key]
        is_target = key in target_key_set
        for field in METRIC_FIELDS:
            if orig.get(field) != cand.get(field):
                total_changed_cells += 1
                check(
                    f"changed_cell_is_approved:{key}:{field}",
                    is_target and field in FIELDS_TO_BLANK,
                    f"unexpected change on {'target' if is_target else 'non-target'} row, field {field}",
                )
                if is_target:
                    check(
                        f"changed_cell_is_zero_to_blank:{key}:{field}",
                        orig.get(field) == "0" and cand.get(field) == "",
                        f"expected '0' -> '', got {orig.get(field)!r} -> {cand.get(field)!r}",
                    )
        if is_target:
            check(f"reach_unchanged:{key}", orig.get("reach") == cand.get("reach"))
            check(f"likes_unchanged:{key}", orig.get("likes") == cand.get("likes"))
            check(f"saves_unchanged:{key}", orig.get("saves") == cand.get("saves"))
            check(f"shares_unchanged:{key}", orig.get("shares") == cand.get("shares"))
            check(f"comments_unchanged:{key}", orig.get("comments") == cand.get("comments"))
            check(f"score_unchanged:{key}", cand.get("score") == "0")
            check(f"classification_unchanged:{key}", cand.get("classification") == "pending")
            check(f"notes_unchanged:{key}", orig.get("notes") == cand.get("notes"))
            for field in (
                "post_id", "instagram_media_id", "permalink", "source_slot_id",
                "publish_receipt_path", "source_asset_path", "clean_derivative_path",
                "source_asset_sha256", "clean_export_derivative_sha256",
                "clean_export_verified", "wardrobe_outfit_id", "pose_body_language_id",
                "expression_gaze_id", "lane",
            ):
                check(f"identity_provenance_unchanged:{key}:{field}", orig.get(field) == cand.get(field))
            check(
                f"row_has_unknown_scoring_inputs_true:{key}",
                row_has_unknown_scoring_inputs(cand) is True,
            )
        else:
            check(f"non_target_row_byte_identical:{key}", orig == cand)

    check("exactly_16_cells_changed", total_changed_cells == 16, f"got {total_changed_cells}")

    report["ok"] = True
    report["total_changed_cells"] = total_changed_cells
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-time repair: blanks legacy '0' placeholders (follows/"
            "profile_visits/completion_rate/replay_rate) on exactly the "
            "four proven-affected Architecture A rows. Defaults to "
            "dry-run; --apply performs the one atomic write."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Perform the real atomic write. Without this flag, only a report is printed.")
    args = parser.parse_args()

    result: Dict[str, Any] = {"ok": False, "apply": args.apply}
    try:
        precondition_report = verify_preconditions()
        result["preconditions"] = precondition_report

        original_rows = sync_read_csv(METRICS_PATH)
        candidate_rows, cell_changes = build_repaired_candidate(original_rows)
        result["proposed_cell_changes"] = cell_changes

        postcondition_report = verify_postconditions(original_rows, candidate_rows)
        result["postconditions"] = postcondition_report

        candidate_sha256_source = "\n".join(
            ",".join(row.get(f, "") for f in METRIC_FIELDS) for row in candidate_rows
        )
        result["candidate_row_content_fingerprint_sha256"] = hashlib.sha256(
            candidate_sha256_source.encode("utf-8")
        ).hexdigest()

        if args.apply:
            sync_write_csv(TMP_CANDIDATE_PATH, candidate_rows)
            candidate_file_sha256 = _sha256_of(TMP_CANDIDATE_PATH)
            result["candidate_file_sha256"] = candidate_file_sha256
            import os
            os.replace(str(TMP_CANDIDATE_PATH), str(METRICS_PATH))
            result["applied"] = True
            result["final_csv_sha256"] = _sha256_of(METRICS_PATH)
        else:
            result["applied"] = False
            result["note"] = "dry-run only -- no file written. Pass --apply to perform the real write."

        result["ok"] = True
    except PreconditionError as exc:
        result["ok"] = False
        result["applied"] = False
        result["error"] = str(exc)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
