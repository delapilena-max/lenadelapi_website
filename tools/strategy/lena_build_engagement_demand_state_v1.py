from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"

POLICY_PATH = NODE / "engagement_selection_policy_v1.json"
WORLD_STATE_PATTERN = "lena_world_state_*.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def latest_world_state(date_str: str) -> dict:
    dated = NEXT_ACTIONS / date_str / f"lena_world_state_{date_str}.json"
    if dated.is_file():
        return read_json(dated)
    candidates = sorted(NEXT_ACTIONS.glob(f"*/{WORLD_STATE_PATTERN}"))
    if not candidates:
        return {}
    return read_json(candidates[-1])


def read_signals(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_boosts(policy: dict, world_state: dict, rows: list[dict]) -> tuple[dict[str, int], dict[str, list[str]], list[str]]:
    class_counts = Counter(row.get("signal_class", "unknown") for row in rows if row.get("signal_class"))
    signal_map = policy.get("signal_class_map", {})
    min_count = int(policy.get("minimum_signal_count_to_activate", 1))
    max_count = int(policy.get("max_signal_count_per_class_for_scoring", 3))
    default_primary = int(policy.get("default_primary_boost", 14))
    default_secondary = int(policy.get("default_secondary_boost", 7))

    recent_counts = world_state.get("continuity_snapshot", {}).get("recent_counts", {})
    public_needed = recent_counts.get("public_or_fitness_share", 1) < 0.375
    home_overuse = recent_counts.get("home_share", 0) > 0.5

    boosts: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    active_classes: list[str] = []

    for signal_class, count in class_counts.items():
        if count < min_count:
            continue
        config = signal_map.get(signal_class)
        if not config:
            continue

        active_classes.append(signal_class)
        strength = min(count, max_count)
        primary_boost = default_primary * strength
        secondary_boost = default_secondary * strength

        for recipe_id in config.get("preferred_recipe_ids", []):
            recipe_boost = primary_boost
            if signal_class == "routine_request" and recipe_id == "hcr_004" and home_overuse:
                recipe_boost += 6
            if signal_class in {"outfit_request", "compliment", "flirty"} and public_needed:
                recipe_boost += 4
            boosts[recipe_id] += recipe_boost
            reasons[recipe_id].append(
                f"engagement demand: {signal_class} x{count}"
            )

        for recipe_id in config.get("secondary_recipe_ids", []):
            recipe_boost = secondary_boost
            if signal_class in {"outfit_request", "flirty"} and public_needed:
                recipe_boost += 2
            boosts[recipe_id] += recipe_boost
            reasons[recipe_id].append(
                f"secondary engagement demand: {signal_class} x{count}"
            )

    return dict(boosts), dict(reasons), sorted(active_classes)


def canonical_state(report: dict, state_path: Path) -> dict:
    queue = report.get("queue_boosts", {})
    return {
        "version": "v1",
        "updated_at": report.get("generated_at", ""),
        "date": report.get("date", ""),
        "signal_count": report.get("signal_count", 0),
        "active_signal_classes": report.get("active_signal_classes", []),
        "boost_by_recipe_id": queue.get("boost_by_recipe_id", {}),
        "preferred_recipe_ids": queue.get("preferred_recipe_ids", []),
        "state_path": str(state_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Lena's engagement-demand state so audience signals can influence recipe selection."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for output folder")
    parser.add_argument(
        "--signals-path",
        default="",
        help="Optional override CSV path for engagement signals.",
    )
    args = parser.parse_args()

    policy = read_json(POLICY_PATH)
    world_state = latest_world_state(args.date)

    signals_path = Path(args.signals_path) if args.signals_path else ROOT / Path(policy["signals_path"])
    rows = read_signals(signals_path)
    class_counts = Counter(row.get("signal_class", "unknown") for row in rows if row.get("signal_class"))
    boost_by_recipe_id, reasons_by_recipe, active_classes = build_boosts(policy, world_state, rows)

    preferred_recipe_ids = [
        recipe_id
        for recipe_id, _ in sorted(boost_by_recipe_id.items(), key=lambda item: (-item[1], item[0]))
    ]

    state_path = ROOT / Path(policy["state_path"])
    out_dir = NEXT_ACTIONS / args.date
    report_path = out_dir / f"lena_engagement_demand_state_{args.date}.json"

    report = {
        "report_type": "lena_engagement_demand_state",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "date": args.date,
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "source_signals_path": str(signals_path),
        "source_world_state": world_state.get("artifacts", {}).get("world_state_report", ""),
        "signal_count": len(rows),
        "signal_class_counts": dict(class_counts),
        "active_signal_classes": active_classes,
        "queue_boosts": {
            "boost_by_recipe_id": boost_by_recipe_id,
            "reasons_by_recipe": reasons_by_recipe,
            "preferred_recipe_ids": preferred_recipe_ids,
        },
        "recommendations": [
            config.get("notes", "")
            for signal_class, config in policy.get("signal_class_map", {}).items()
            if signal_class in active_classes and config.get("notes")
        ],
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
    }

    write_json(report_path, report)
    write_json(state_path, canonical_state(report, state_path))

    print(
        json.dumps(
            {
                "ok": True,
                "output_path": str(report_path),
                "canonical_state_path": str(state_path),
                "signal_count": len(rows),
                "active_signal_classes": active_classes,
                "preferred_recipe_ids": preferred_recipe_ids,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
