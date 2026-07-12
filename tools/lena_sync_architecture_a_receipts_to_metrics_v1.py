from __future__ import annotations

# Lena Architecture A receipt -> metrics identity/provenance sync (2026-07-11).
#
# Closes the most load-bearing broken join found in the metrics/learning
# audit: publish receipt -> platform media ID -> metrics row currently
# depends on a human hand-typing "post_id:<id>" into a free-text notes
# field, later regex-parsed back out. This tool reads Architecture A's
# real, already-produced receipts (pipeline/queue/published/*.json.
# receipt.json) and the promoted queue item written alongside each one,
# and attaches structured identity/provenance fields onto the existing
# metrics CSV row -- it does not create a new store, does not recompute
# clean-export verification, and does not touch Architecture B's separate
# queue/CSV format at all.
#
# Read-only against every canonical artifact it consumes (receipts, queue
# items, QA/approval paths) -- the only file this tool ever writes is the
# existing pipeline/analytics/lena_post_metrics_v1_6_1.csv, and only when
# --apply is passed (defaults to dry-run, matching every other tool in
# this session's Reel-parity/clean-export chain).
#
# Never fabricates a value: any field genuinely absent from the real
# receipt/queue-item stays blank, never guessed. Never promotes a queue
# item, never re-verifies or weakens clean-export doctrine -- it only
# reads metadata.clean_export_verified/source_asset_path/clean_export_
# derivative_sha256 that tools/lena_promote_to_queue_v1.py's own,
# unmodified contract already wrote.

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_DIR = ROOT / "pipeline" / "queue" / "published"
METRICS = ROOT / "pipeline" / "analytics" / "lena_post_metrics_v1_6_1.csv"
ASSET_REVIEW_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
APPROVAL_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"

# Legacy schema (unchanged, same order) plus new structured identity/
# provenance columns (2026-07-11), appended at the end. csv.DictReader
# keys by header name, not position, so every historical row continues to
# load correctly regardless of column order; appending (not inserting)
# keeps a human diff of the CSV header minimal.
LEGACY_METRIC_FIELDS = [
    "date", "slot_id", "platform", "media_type", "growth_bucket", "lane", "hook_category",
    "post_url", "audio_name", "reach", "likes", "saves", "shares", "comments", "follows",
    "profile_visits", "completion_rate", "replay_rate", "score", "classification", "notes",
]
NEW_IDENTITY_FIELDS = [
    "post_id",
    "instagram_media_id",
    "permalink",
    "source_slot_id",
    "publish_receipt_path",
    "source_asset_path",
    "clean_derivative_path",
    "source_asset_sha256",
    "clean_export_derivative_sha256",
    "clean_export_verified",
]
# Creative-provenance columns (2026-07-11): sourced only from the real
# Architecture A queue-item metadata that tools/lena_build_publish_packet_v1.py
# already forwards there (never inferred from prompt/pose/caption text, never
# fuzzy-matched, never a recipe_id). Brand-new columns -- no historical row
# has ever had real data here, so they follow the exact same additive,
# never-overwrite-nonempty-with-blank convergence semantics as
# NEW_IDENTITY_FIELDS. `lane` is deliberately NOT listed here: it is a
# pre-existing LEGACY_METRIC_FIELDS column that may already carry real
# hand-entered historical data, so it gets its own, stricter
# fill-only-when-blank handling in upsert_metrics_row() instead.
NEW_CREATIVE_PROVENANCE_FIELDS = [
    "wardrobe_outfit_id",
    "pose_body_language_id",
    "expression_gaze_id",
]
METRIC_FIELDS = LEGACY_METRIC_FIELDS + NEW_IDENTITY_FIELDS + NEW_CREATIVE_PROVENANCE_FIELDS

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in METRIC_FIELDS} for row in rows])


def metric_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (row.get("date", ""), row.get("slot_id", ""), row.get("platform", ""))


def derive_date(slot_id: str, queue_item_metadata: Dict[str, Any]) -> str:
    """Never invented: prefers metadata.source_date (a real field
    build_queue_draft() already writes for every provider), falls back to
    a literal YYYY-MM-DD prefix already embedded in the slot_id (an
    existing, pre-established naming convention for date-prefixed slots).
    Returns "" -- not a guess -- if neither is real."""
    source_date = queue_item_metadata.get("source_date")
    if source_date:
        return str(source_date)
    match = DATE_PREFIX_RE.match(slot_id or "")
    return match.group(1) if match else ""


def derive_platform_label(media_type: str) -> str:
    """Architecture A only ever publishes to Instagram (instagram_queue_
    bridge.py hard-requires platforms == ["instagram"]) -- this derives the
    same human-readable platform label convention Architecture B's real
    rows already use in this exact CSV, from the receipt's own real
    media_type. Never invented; media_type absence is impossible for a
    real receipt (posting_manager.py always writes it)."""
    normalized = (media_type or "").strip().lower()
    if normalized in {"story", "stories"}:
        return "Instagram Story"
    if normalized in {"video", "reel", "reels"}:
        return "Instagram Reels"
    return "Instagram Feed"


def find_queue_item(receipt: Dict[str, Any], receipt_path: Path) -> Optional[Dict[str, Any]]:
    """The promoted queue item is always written alongside its own receipt
    (pipeline/posting_manager.py::_move_post()) -- same directory, same
    stem minus the trailing ".receipt". Read-only; returns None (not a
    guess) if genuinely absent."""
    candidates = []
    published_post_path = receipt.get("published_post_path")
    if published_post_path:
        candidates.append(Path(published_post_path))
    # receipt_path is "<slot_id>.json.receipt.json" -> queue item is
    # "<slot_id>.json" in the same directory.
    candidates.append(receipt_path.with_suffix("").with_suffix(""))
    for candidate in candidates:
        if candidate.exists():
            try:
                return read_json(candidate)
            except Exception:
                continue
    return None


def resolve_canonical_provenance(
    date_str: str, slot_id: str, source_slot_id: str = ""
) -> Dict[str, Optional[str]]:
    """Read-only lookup of existing canonical artifacts reachable via
    (date, slot_id), using the same path conventions
    pipeline/qa/lena_photo_qa.py::qa_artifact_path() and
    tools/lena_record_publish_approval_v1.py::resolve_approval_output_path()
    already establish (mirrored here, not imported, to keep this tool
    fully self-contained and independent of the Reel-parity file set).
    Never invents a path; reports None for any artifact that doesn't
    actually exist on disk rather than guessing one does.

    QA provenance only (2026-07-11): a Story repackaging of an existing
    photo render is deliberately kept under its own distinct slot_id (see
    tools/lena_promote_to_queue_v1.py's source_slot_id doctrine), so its
    real QA record lives under the TRUE source slot, not the output slot.
    If the output slot's own QA artifact isn't found, and source_slot_id
    is real and actually differs from slot_id, fall back to looking up QA
    evidence under source_slot_id -- locating existing evidence only, never
    changing which slot is the canonical identity of this row. Approval
    records get no such fallback: an approval is always recorded against
    the item that was actually approved for live publish, never inferred
    from a different slot."""
    if not date_str or not slot_id:
        return {"qa_artifact_path": None, "approval_record_path": None}
    qa_path = ASSET_REVIEW_ROOT / date_str / f"{slot_id}_qa.json"
    qa_artifact_path = str(qa_path) if qa_path.exists() else None
    if qa_artifact_path is None and source_slot_id and source_slot_id != slot_id:
        source_qa_path = ASSET_REVIEW_ROOT / date_str / f"{source_slot_id}_qa.json"
        if source_qa_path.exists():
            qa_artifact_path = str(source_qa_path)
    approval_path = APPROVAL_ROOT / date_str / f"{slot_id}_approval.json"
    return {
        "qa_artifact_path": qa_artifact_path,
        "approval_record_path": str(approval_path) if approval_path.exists() else None,
    }


def _historical_nested_instagram_media_id(receipt: Dict[str, Any]) -> str:
    """Fallback only (2026-07-11): some older receipts (e.g.
    2026-07-07-03-photo, predating the flat top-level instagram_media_id
    field) only carry the real ID nested at publish_response.result.
    instagram_result.instagram_media_id. Supports exactly that one known
    historical shape -- no arbitrary recursive/deep search, no free-text
    parsing, no guessing from permalink. Returns "" (never a guess) if
    that exact path isn't a real string."""
    publish_response = receipt.get("publish_response")
    if not isinstance(publish_response, dict):
        return ""
    result = publish_response.get("result")
    if not isinstance(result, dict):
        return ""
    instagram_result = result.get("instagram_result")
    if not isinstance(instagram_result, dict):
        return ""
    value = instagram_result.get("instagram_media_id")
    return value if isinstance(value, str) and value else ""


def build_identity_fields(receipt: Dict[str, Any], receipt_path: Path) -> Dict[str, Any]:
    """Pure function (given already-loaded receipt/receipt_path), except
    for the one real filesystem read to locate the sibling queue item.
    Never mutates anything. Returns the exact set of CSV-column-shaped
    fields this tool ever writes."""
    queue_item = find_queue_item(receipt, receipt_path) or {}
    metadata = queue_item.get("metadata") if isinstance(queue_item.get("metadata"), dict) else {}

    slot_id = receipt.get("post_id") or queue_item.get("slot_id") or ""
    date_str = derive_date(slot_id, metadata)
    media_type = receipt.get("media_type") or queue_item.get("media_type") or ""
    platform = derive_platform_label(media_type)
    source_slot_id = metadata.get("source_slot_id") or slot_id

    # A pre-clean-export-contract item's media_path is the raw source,
    # NEVER a verified clean derivative -- only report clean_derivative_path
    # when the queue item's own metadata genuinely confirms verification,
    # exactly matching tools/lena_promote_to_queue_v1.py's own contract.
    # Never recomputed or reinterpreted here -- this tool consumes
    # already-established provenance, it does not become a new clean-export
    # authority.
    clean_export_verified = metadata.get("clean_export_verified") is True
    clean_derivative_path = queue_item.get("media_path") if clean_export_verified else ""

    return {
        "date": date_str,
        "slot_id": slot_id,
        "platform": platform,
        "media_type": media_type,
        # Creative provenance (2026-07-11): sourced only from the real
        # queue-item metadata that tools/lena_build_publish_packet_v1.py's
        # build_queue_draft() already writes -- never inferred from
        # image_prompt/pose text/caption, never fuzzy-matched, never
        # recipe_id. `lane` reads metadata.activity specifically: the prior
        # audit confirmed build_queue_draft() forwards the resolver's real
        # lane/scene value into metadata["activity"] (naming drift, not
        # loss) -- there is no separate metadata["lane"] key written by any
        # current provider path. Absent entirely on historical
        # pre-provenance queue items; left "" (never guessed).
        "lane": metadata.get("activity") or "",
        "wardrobe_outfit_id": metadata.get("wardrobe_outfit_id") or "",
        "pose_body_language_id": metadata.get("pose_body_language_id") or "",
        "expression_gaze_id": metadata.get("expression_gaze_id") or "",
        "post_id": receipt.get("post_id") or "",
        "instagram_media_id": (
            receipt.get("instagram_media_id")
            or _historical_nested_instagram_media_id(receipt)
            or ""
        ),
        "permalink": receipt.get("permalink") or "",
        "source_slot_id": source_slot_id,
        "publish_receipt_path": str(receipt_path),
        "source_asset_path": metadata.get("source_asset_path") or "",
        "clean_derivative_path": clean_derivative_path,
        "source_asset_sha256": metadata.get("source_asset_sha256") or "",
        "clean_export_derivative_sha256": metadata.get("clean_export_derivative_sha256") or "",
        "clean_export_verified": "true" if clean_export_verified else "false",
    }


def upsert_metrics_row(
    metric_rows: List[Dict[str, Any]], identity: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], bool]:
    """Never overwrites an existing non-empty field with a blank one, and
    never rewrites performance metric values (reach/likes/.../score/
    classification) at all -- only the structured identity/provenance
    fields this sync exists to attach. A genuinely new row (no existing
    (date, slot_id, platform) match) is created with only the metrics
    that are intentionally known-at-creation seeded to placeholders;
    unsupported or unmeasured outcome fields remain blank/unknown."""
    key = metric_key(identity)
    for idx, row in enumerate(metric_rows):
        if metric_key(row) == key:
            updated = dict(row)
            for field in NEW_IDENTITY_FIELDS + NEW_CREATIVE_PROVENANCE_FIELDS:
                if identity.get(field):
                    updated[field] = identity[field]
            if identity.get("media_type") and not updated.get("media_type"):
                updated["media_type"] = identity["media_type"]
            # `lane` is a pre-existing legacy column that may already carry
            # real historical data (hand-entered or from an earlier real
            # ingestion path) -- stricter than the identity/creative-
            # provenance fields above: fill it in only when the existing
            # row's lane is genuinely blank, and never touch (let alone
            # overwrite) an already-nonblank historical value, even with a
            # different real value from queue metadata.
            if identity.get("lane") and not (updated.get("lane") or "").strip():
                updated["lane"] = identity["lane"]
            metric_rows[idx] = updated
            return metric_rows, False

    new_row = {field: identity.get(field, "") for field in METRIC_FIELDS}
    for placeholder_field in (
        "reach", "likes", "saves", "shares", "comments", "score",
    ):
        new_row[placeholder_field] = "0"
    new_row["classification"] = "pending"
    new_row["post_url"] = identity.get("permalink") or ""
    new_row["notes"] = (
        "Auto-synced from Architecture A publish receipt "
        f"({identity.get('publish_receipt_path', '')}); "
        "update metrics after performance data is available."
    )
    metric_rows.append(new_row)
    return metric_rows, True


def sync_all(published_dir: Path, metrics_path: Path, apply: bool) -> Dict[str, Any]:
    if not published_dir.exists():
        return {"ok": True, "receipts_scanned": 0, "created": 0, "updated": 0, "synced": []}

    metric_rows = read_csv(metrics_path)
    synced: List[Dict[str, Any]] = []
    created = 0
    updated = 0

    for receipt_path in sorted(published_dir.glob("*.receipt.json")):
        try:
            receipt = read_json(receipt_path)
        except Exception as exc:
            synced.append({"receipt": str(receipt_path), "ok": False, "error": str(exc)})
            continue

        identity = build_identity_fields(receipt, receipt_path)
        provenance = resolve_canonical_provenance(
            identity["date"], identity["slot_id"], identity["source_slot_id"]
        )
        metric_rows, is_new = upsert_metrics_row(metric_rows, identity)
        created += 1 if is_new else 0
        updated += 0 if is_new else 1
        synced.append({
            "receipt": str(receipt_path),
            "ok": True,
            "created": is_new,
            "date": identity["date"],
            "slot_id": identity["slot_id"],
            "platform": identity["platform"],
            "instagram_media_id": identity["instagram_media_id"],
            "clean_export_verified": identity["clean_export_verified"],
            "qa_artifact_path": provenance["qa_artifact_path"],
            "approval_record_path": provenance["approval_record_path"],
        })

    if apply:
        write_csv(metrics_path, metric_rows)

    return {
        "ok": True,
        "metrics_csv": str(metrics_path),
        "receipts_scanned": len(synced),
        "created": created,
        "updated": updated,
        "synced": synced,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only-by-default sync of real Architecture A publish receipts "
            "(pipeline/queue/published/*.json.receipt.json) into the existing "
            "Lena metrics CSV's structured identity/provenance fields. Never "
            "recomputes clean-export verification, never touches Architecture "
            "B's queue/CSV format, never fabricates a missing value. Defaults "
            "to dry-run; --apply performs the one write."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Write the updated metrics CSV. Without this flag, only a summary is printed.")
    args = parser.parse_args()

    result = sync_all(PUBLISHED_DIR, METRICS, apply=args.apply)
    print(json.dumps({**result, "dry_run": not args.apply}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
