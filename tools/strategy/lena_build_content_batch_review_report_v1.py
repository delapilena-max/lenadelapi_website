"""
Lena Content Batch Review Report v1

Reads the latest (or specified) batch manifest and packet files.
Produces a human-readable console summary and a JSON report file.

Safe: no API calls, no image generation, no video generation,
no R2, no Instagram, no Facebook, no queue modification,
no publishing, no scheduling, no staging or committing.
No recipe bank modified. No hook bank modified. No packet files modified.
"""

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTPUT_BASE = os.path.join(
    ROOT, "pipeline", "strategy", "lena", "content_packets"
)
MANIFEST_PREFIX = "lena_content_packet_batch_manifest_dryrun_"
REPORT_PREFIX = "lena_content_batch_review_report_"

CAPTION_FIELDS = [
    "hook_text",
    "caption_draft",
    "caption_followup",
    "optional_reels_opening_line",
    "suggested_comment_reply_angle",
]


def find_latest_date_dir():
    if not os.path.isdir(OUTPUT_BASE):
        print(f"[ERROR] Output base not found: {OUTPUT_BASE}")
        sys.exit(1)
    dirs = sorted(
        d for d in os.listdir(OUTPUT_BASE)
        if os.path.isdir(os.path.join(OUTPUT_BASE, d)) and len(d) == 10
    )
    if not dirs:
        print(f"[ERROR] No date directories under: {OUTPUT_BASE}")
        sys.exit(1)
    return dirs[-1]


def load_json_file(path):
    if not os.path.isfile(path):
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_manifest(date_str):
    date_dir = os.path.join(OUTPUT_BASE, date_str)
    fname = f"{MANIFEST_PREFIX}{date_str}.json"
    manifest_path = os.path.join(date_dir, fname)
    return load_json_file(manifest_path), manifest_path, date_dir


def load_packets(manifest, date_dir):
    packets = {}
    missing = []
    for entry in manifest.get("packets", []):
        rid = entry.get("recipe_id", "unknown")
        raw_path = entry.get("output_path", "")
        candidates = [raw_path]
        if raw_path:
            candidates.append(
                os.path.join(date_dir, os.path.basename(raw_path))
            )
        loaded = False
        for p in candidates:
            if p and os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    packets[rid] = json.load(f)
                loaded = True
                break
        if not loaded:
            missing.append(rid)
    return packets, missing


def hook_category_distribution(manifest_packets):
    dist = {}
    for p in manifest_packets:
        cat = p.get("hook_category", "unknown")
        dist[cat] = dist.get(cat, 0) + 1
    return dist


def pillar_distribution(packets):
    dist = {}
    for p in packets.values():
        pillar = p.get("content_pillar", "unknown")
        dist[pillar] = dist.get(pillar, 0) + 1
    return dist


def platform_coverage(packets):
    seen = set()
    for p in packets.values():
        for plat in p.get("platform_targets", []):
            seen.add(plat)
    return sorted(seen)


def prompt_char_stats(manifest_packets):
    chars = [
        p.get("compact_kling_prompt_chars", 0)
        for p in manifest_packets
        if p.get("compact_kling_prompt_chars")
    ]
    if not chars:
        return None
    return {
        "min": min(chars),
        "max": max(chars),
        "avg": round(statistics.mean(chars), 1),
        "all_under_2500": all(c < 2500 for c in chars),
    }


def safety_summary(packets, manifest_packets):
    all_passed = all(p.get("validation_passed") for p in manifest_packets)
    flag_failures = {}
    for rid, pkt in packets.items():
        flags = pkt.get("safety_flags", {})
        for k, v in flags.items():
            if k == "all_checks_passed":
                continue
            if not v:
                flag_failures.setdefault(rid, []).append(k)
    return all_passed, flag_failures


def missing_field_warnings(packets):
    warnings = {}
    for rid, pkt in packets.items():
        empty = [f for f in CAPTION_FIELDS if not pkt.get(f, "").strip()]
        if empty:
            warnings[rid] = empty
    return warnings


def content_variety_notes(manifest_packets, packets):
    notes = []
    scene_types = [p.get("scene_type", "") for p in manifest_packets]
    unique_scenes = len(set(scene_types))
    total = len(scene_types)
    if unique_scenes < total:
        dupes = [
            s for s in set(scene_types)
            if scene_types.count(s) > 1
        ]
        notes.append(
            f"Duplicate scene types found: {dupes}. "
            "Ideal batch has all unique scene types."
        )
    else:
        notes.append(
            f"All {total} scene types are unique -- good variety."
        )

    cat_dist = hook_category_distribution(manifest_packets)
    heavy = {c: n for c, n in cat_dist.items() if n >= 3}
    if heavy:
        notes.append(
            "Hook category concentration: "
            + ", ".join(f"{c}={n}" for c, n in sorted(heavy.items()))
            + ". Consider spreading hooks across more categories in "
            "future batches."
        )
    else:
        notes.append(
            "Hook categories reasonably distributed across batch."
        )

    indoor = [
        s for s in scene_types
        if any(
            kw in s
            for kw in ("apartment", "mirror", "home", "kitchen", "gym")
        )
    ]
    outdoor = [
        s for s in scene_types
        if any(
            kw in s
            for kw in (
                "street", "parking", "rooftop", "staircase", "errand",
                "grocery", "walk", "doorway"
            )
        )
    ]
    notes.append(
        f"Scene setting mix: ~{len(indoor)} indoor/gym, "
        f"~{len(outdoor)} outdoor/transitional."
    )

    pillars = pillar_distribution(packets)
    if len(pillars) <= 2:
        notes.append(
            f"Low pillar diversity: only {list(pillars.keys())}. "
            "Consider adding variety in future batches."
        )
    else:
        notes.append(
            f"Pillar coverage: {len(pillars)} distinct pillars -- "
            + ", ".join(pillars.keys()) + "."
        )

    return notes


def human_review_notes(
    manifest, manifest_packets, packets,
    missing_packets, flag_failures, field_warnings,
    prompt_stats, cat_dist,
):
    notes = []

    if manifest.get("total_failed", 0) > 0:
        notes.append(
            f"CRITICAL: {manifest['total_failed']} packet(s) failed "
            "validation. Do not use for generation."
        )
    else:
        notes.append(
            "All packets passed validation. Safe to proceed to human "
            "review of caption and hook copy quality."
        )

    if missing_packets:
        notes.append(
            f"WARNING: {len(missing_packets)} packet file(s) could not "
            f"be read: {missing_packets}. Re-run batch builder."
        )

    if flag_failures:
        for rid, flags in flag_failures.items():
            notes.append(
                f"Flag failure in {rid}: {flags}. Inspect before use."
            )

    if field_warnings:
        for rid, fields in field_warnings.items():
            notes.append(
                f"Empty caption/copy fields in {rid}: {fields}. "
                "Review before publishing."
            )

    if prompt_stats and not prompt_stats["all_under_2500"]:
        notes.append(
            "WARNING: One or more compact Kling prompts exceed 2500 "
            "chars. Trim before generation."
        )

    heavy_cats = {c: n for c, n in cat_dist.items() if n >= 4}
    if heavy_cats:
        notes.append(
            "Hook category imbalance: "
            + str(heavy_cats)
            + ". Future batches should rotate categories more broadly."
        )

    notes.append(
        "Review hook_text + caption_draft pairs for voice consistency "
        "before generation. Lena tone: warm, dry, self-aware, "
        "platform-safe."
    )
    notes.append(
        "Review compact_kling_prompt_preview per packet before "
        "submitting to Kling. Check scene realism and identity language."
    )
    notes.append(
        "No image has been generated. No API call was made. "
        "This report is a pre-generation planning artifact only."
    )

    return notes


def build_report(
    manifest, manifest_path, date_dir, date_str,
    packets, missing_packets,
):
    mp = manifest.get("packets", [])

    cat_dist = hook_category_distribution(mp)
    pillars = pillar_distribution(packets)
    platforms = platform_coverage(packets)
    prompt_stats = prompt_char_stats(mp)
    all_val_passed, flag_failures = safety_summary(packets, mp)
    field_warnings = missing_field_warnings(packets)
    variety_notes = content_variety_notes(mp, packets)

    review_notes = human_review_notes(
        manifest, mp, packets,
        missing_packets, flag_failures, field_warnings,
        prompt_stats, cat_dist,
    )

    used_hook_ids = manifest.get("used_hook_ids", [])
    repeated = [
        h for h in used_hook_ids
        if sum(1 for p in mp if p.get("strong_hook_id") == h) > 1
    ]

    return {
        "report_type": "lena_content_batch_review_report",
        "report_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "publishing_approval": "not_approved",
        "batch": {
            "batch_id": manifest.get("batch_id"),
            "batch_date": date_str,
            "batch_path": date_dir,
            "manifest_path": manifest_path,
            "generator": manifest.get("generator"),
        },
        "volume": {
            "total_requested": manifest.get("total_requested"),
            "total_generated": manifest.get("total_generated"),
            "total_passed": manifest.get("total_passed"),
            "total_failed": manifest.get("total_failed"),
            "packets_readable": len(packets),
            "packets_missing": missing_packets,
        },
        "hook_integrity": {
            "repeated_hooks": repeated,
            "repeated_hook_count": len(repeated),
            "used_hook_ids": sorted(used_hook_ids),
            "hook_category_distribution": cat_dist,
        },
        "recipe_coverage": {
            "recipe_ids": [p.get("recipe_id") for p in mp],
            "scene_types": [p.get("scene_type") for p in mp],
        },
        "prompt_stats": prompt_stats,
        "safety": {
            "all_validation_passed": all_val_passed,
            "flag_failures_by_packet": flag_failures,
        },
        "content_variety": {
            "pillar_distribution": pillars,
            "platform_coverage": platforms,
            "hook_category_distribution": cat_dist,
            "variety_notes": variety_notes,
        },
        "missing_field_warnings": field_warnings,
        "human_review_notes": review_notes,
    }


def save_report(report, date_str):
    out_dir = os.path.join(OUTPUT_BASE, date_str)
    os.makedirs(out_dir, exist_ok=True)
    fname = f"{REPORT_PREFIX}{date_str}.json"
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=True)
    return fpath


def print_report(report):
    b = report["batch"]
    v = report["volume"]
    hi = report["hook_integrity"]
    ps = report["prompt_stats"] or {}
    sf = report["safety"]
    cv = report["content_variety"]
    mfw = report["missing_field_warnings"]

    sep = "=" * 68
    thin = "-" * 68

    print()
    print(sep)
    print("  LENA CONTENT BATCH REVIEW REPORT v1")
    print(sep)
    print(f"  batch_id   : {b['batch_id']}")
    print(f"  date       : {b['batch_date']}")
    print(f"  path       : {b['batch_path']}")
    print()

    print("  VOLUME")
    print(thin)
    print(f"  requested  : {v['total_requested']}")
    print(f"  generated  : {v['total_generated']}")
    print(f"  passed     : {v['total_passed']}")
    print(f"  failed     : {v['total_failed']}")
    print(f"  readable   : {v['packets_readable']}")
    missing = v["packets_missing"]
    if missing:
        print(f"  MISSING    : {missing}")
    print()

    print("  HOOK INTEGRITY")
    print(thin)
    repeated = hi["repeated_hooks"]
    print(f"  repeated hooks : {repeated if repeated else 'none'}")
    print(f"  hook IDs used  : {hi['used_hook_ids']}")
    print("  category dist  :")
    for cat, n in sorted(hi["hook_category_distribution"].items()):
        bar = "#" * n
        print(f"    {cat:<30} {bar} ({n})")
    print()

    print("  PROMPT STATS")
    print(thin)
    if ps:
        print(f"  chars min  : {ps['min']}")
        print(f"  chars max  : {ps['max']}")
        print(f"  chars avg  : {ps['avg']}")
        ok = "YES" if ps["all_under_2500"] else "NO -- ACTION REQUIRED"
        print(f"  all <2500  : {ok}")
    else:
        print("  (no prompt stats available)")
    print()

    print("  SAFETY")
    print(thin)
    ok = "ALL PASSED" if sf["all_validation_passed"] else "FAILURES PRESENT"
    print(f"  validation : {ok}")
    if sf["flag_failures_by_packet"]:
        for rid, flags in sf["flag_failures_by_packet"].items():
            print(f"  [FAIL] {rid}: {flags}")
    print()

    print("  CONTENT VARIETY")
    print(thin)
    print(f"  pillars    : {cv['pillar_distribution']}")
    print(f"  platforms  : {cv['platform_coverage']}")
    for note in cv["variety_notes"]:
        print(f"  - {note}")
    print()

    if mfw:
        print("  MISSING FIELD WARNINGS")
        print(thin)
        for rid, fields in mfw.items():
            print(f"  {rid}: {fields}")
        print()

    print("  HUMAN REVIEW NOTES")
    print(thin)
    for note in report["human_review_notes"]:
        print(f"  - {note}")
    print()

    print("  SAFETY STATEMENT")
    print(thin)
    print("  NO API calls made.       NO image generated.")
    print("  NO video generated.      NO R2 upload.")
    print("  NO queue modified.       NO Instagram/Facebook touched.")
    print("  NO publishing.           NO scheduling.")
    print("  NO recipe bank modified. NO hook bank modified.")
    print("  NO packet files modified.")
    print(sep)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Lena Content Batch Review Report v1 -- dry run"
    )
    parser.add_argument(
        "--date",
        default=None,
        help=(
            "Batch date directory to review (YYYY-MM-DD). "
            "Defaults to latest available."
        ),
    )
    args = parser.parse_args()

    if args.date:
        date_str = args.date
    else:
        date_str = find_latest_date_dir()

    print(
        f"[lena_build_content_batch_review_report_v1] "
        f"date : {date_str}"
    )

    manifest, manifest_path, date_dir = load_manifest(date_str)
    print(
        f"[lena_build_content_batch_review_report_v1] "
        f"manifest : {os.path.basename(manifest_path)}"
    )

    packets, missing_packets = load_packets(manifest, date_dir)
    print(
        f"[lena_build_content_batch_review_report_v1] "
        f"packets loaded : {len(packets)} / "
        f"{len(manifest.get('packets', []))}"
    )
    if missing_packets:
        print(
            f"[WARN] packets not readable: {missing_packets}"
        )

    report = build_report(
        manifest, manifest_path, date_dir, date_str,
        packets, missing_packets,
    )

    report_path = save_report(report, date_str)
    print(
        f"[lena_build_content_batch_review_report_v1] "
        f"report written : {report_path}"
    )

    print_report(report)

    failed = report["volume"]["total_failed"]
    if failed:
        print(f"[ERROR] {failed} packet(s) failed validation.")
        sys.exit(1)

    print(
        f"[OK] Review report complete. "
        f"{report['volume']['total_passed']} packets passed. "
        f"Report written to ignored output path."
    )


if __name__ == "__main__":
    main()
