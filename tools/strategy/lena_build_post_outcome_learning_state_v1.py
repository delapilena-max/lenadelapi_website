from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
PROMPTS = ROOT / "pipeline" / "prompt_banks" / "lena"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"

POLICY_PATH = NODE / "post_outcome_learning_policy_v1.json"
RECIPE_BANK_PATH = PROMPTS / "lena_high_caliber_prompt_recipe_bank_v1.json"
FOLLOWUP_POLICY_PATH = NODE / "followup_post_decision_policy_v1_7.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_date(value: str) -> date_cls | None:
    try:
        return date_cls.fromisoformat((value or "").strip()[:10])
    except Exception:
        return None


def days_since(value: str, current_date: date_cls) -> int | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    return (current_date - parsed).days


def active_recipes() -> list[dict]:
    bank = read_json(RECIPE_BANK_PATH)
    recipes = [
        recipe for recipe in bank.get("recipes", [])
        if recipe.get("production_status") != "test_only"
    ]
    recipes.sort(
        key=lambda recipe: (
            recipe.get("proof_priority") is None,
            recipe.get("proof_priority", 999),
            recipe.get("id", ""),
        )
    )
    return recipes


def metric_key(row: dict) -> tuple[str, str, str]:
    return (
        row.get("date", ""),
        row.get("slot_id", ""),
        row.get("platform", ""),
    )


def numeric(value: str) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def hook_match_score(metric_row: dict, recipe: dict) -> int:
    score = 0
    hook = (metric_row.get("hook_category") or "").strip().lower()
    lane = (metric_row.get("lane") or "").strip().lower()
    bucket = (metric_row.get("growth_bucket") or "").strip().lower()
    scene_blob = " ".join(
        [
            recipe.get("scene_type", ""),
            recipe.get("content_pillar", ""),
            recipe.get("title", ""),
            " ".join(recipe.get("linked_hook_categories", [])),
        ]
    ).lower()

    if hook and hook in [item.lower() for item in recipe.get("linked_hook_categories", [])]:
        score += 3
    if lane and lane in scene_blob:
        score += 2
    if bucket and bucket in scene_blob:
        score += 1
    return score


def build_queue_boosts(
    metrics_rows: list[dict],
    recipes: list[dict],
    policy: dict,
    current_date: date_cls,
) -> tuple[dict[str, int], dict[str, list[str]], list[dict]]:
    score_cfg = policy.get("queue_scoring", {})
    followup_days = int(policy.get("freshness_windows", {}).get("followup_days", 3))
    winner_classes = set(policy.get("winner_classifications", ["winner", "strong"]))

    boosts: dict[str, int] = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    winner_rows: list[dict] = []

    sorted_rows = sorted(
        metrics_rows,
        key=lambda row: (
            row.get("date", ""),
            numeric(row.get("score")),
        ),
        reverse=True,
    )

    for row in sorted_rows:
        classification = (row.get("classification") or "").strip().lower()
        if classification not in winner_classes and classification != "neutral":
            continue

        base = 0
        if classification == "winner":
            base = int(score_cfg.get("winner_boost", 22))
        elif classification == "strong":
            base = int(score_cfg.get("strong_boost", 14))
        elif classification == "neutral":
            base = int(score_cfg.get("neutral_boost", 4))

        if base <= 0:
            continue

        age = days_since(row.get("date", ""), current_date)
        recent_bonus = int(score_cfg.get("recent_followup_bonus", 6)) if age is not None and age <= followup_days else 0

        matched_any = False
        for recipe in recipes:
            match_score = hook_match_score(row, recipe)
            if match_score <= 0:
                continue
            matched_any = True
            recipe_id = recipe.get("id", "")
            recipe_boost = base * match_score + recent_bonus
            boosts[recipe_id] += recipe_boost
            reasons[recipe_id].append(
                f"post outcome: {classification} metric on lane={row.get('lane','')} hook={row.get('hook_category','')} score={row.get('score','0')}"
            )

        if matched_any and classification in {"winner", "strong"}:
            winner_rows.append(
                {
                    "date": row.get("date", ""),
                    "platform": row.get("platform", ""),
                    "slot_id": row.get("slot_id", ""),
                    "lane": row.get("lane", ""),
                    "hook_category": row.get("hook_category", ""),
                    "score": row.get("score", ""),
                    "classification": classification,
                }
            )

    return dict(boosts), dict(reasons), winner_rows


def actionable_metrics_only_posts(metrics_rows: list[dict], manual_keys: set[tuple]) -> list[dict]:
    """Metrics-only Architecture A published posts: included only when they
    carry a real, actionable instagram_media_id (never a placeholder/blank
    one), and only when the same canonical (date, slot_id, platform)
    identity isn't already represented by a manual-log row -- manual-log
    rows always win on exact collision, this never overwrites them."""
    seen: set[tuple] = set()
    posts: list[dict] = []
    for row in metrics_rows:
        key = metric_key(row)
        if key in manual_keys or key in seen:
            continue
        instagram_media_id = (row.get("instagram_media_id") or "").strip()
        if not instagram_media_id:
            continue
        seen.add(key)
        posts.append({
            "date": row.get("date", ""),
            "platform": row.get("platform", ""),
            "slot_id": row.get("slot_id", ""),
            "lane": row.get("lane", ""),
            "hook_category": row.get("hook_category", ""),
            "post_url": row.get("permalink", "") or row.get("post_url", ""),
        })
    return posts


def build_published_post_inventory(manual_rows: list[dict], metrics_rows: list[dict]) -> list[dict]:
    """Union of manual-log published posts and metrics-only Architecture A
    published posts, deduped on the canonical (date, slot_id, platform)
    key -- source_slot_id is never part of this identity, so a Story and a
    Reel derived from the same source photo remain distinct published
    posts. Manual-log rows are never modified or merged; a metrics-only
    row is only ever added under a key no manual row already occupies."""
    manual_keys = {metric_key(row) for row in manual_rows}
    return list(manual_rows) + actionable_metrics_only_posts(metrics_rows, manual_keys)


def canonical_state(report: dict, state_path: Path) -> dict:
    queue = report.get("queue_boosts", {})
    return {
        "version": "v1",
        "updated_at": report.get("generated_at", ""),
        "date": report.get("date", ""),
        "published_post_count": report.get("published_post_count", 0),
        "metrics_row_count": report.get("metrics_row_count", 0),
        "winner_post_count": len(report.get("winner_posts", [])),
        "pending_metrics_count": len(report.get("pending_metrics_posts", [])),
        "stale_pending_metrics_count": len(report.get("stale_pending_metrics_posts", [])),
        "boost_by_recipe_id": queue.get("boost_by_recipe_id", {}),
        "preferred_recipe_ids": queue.get("preferred_recipe_ids", []),
        "state_path": str(state_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Lena's canonical post-outcome learning state."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for output folder")
    parser.add_argument("--manual-post-log-path", default="", help="Optional override CSV path for manual post log.")
    parser.add_argument("--post-metrics-path", default="", help="Optional override CSV path for post metrics.")
    args = parser.parse_args()

    policy = read_json(POLICY_PATH)
    followup_policy = read_json(FOLLOWUP_POLICY_PATH)
    current_date = parse_date(args.date) or date_cls.fromisoformat(utc_date())

    manual_path = Path(args.manual_post_log_path) if args.manual_post_log_path else ROOT / Path(policy["manual_post_log_path"])
    metrics_path = Path(args.post_metrics_path) if args.post_metrics_path else ROOT / Path(policy["post_metrics_path"])
    publish_state_path = ROOT / Path(policy["publish_state_path"])
    state_path = ROOT / Path(policy["state_path"])

    manual_rows = read_csv(manual_path)
    metrics_rows = read_csv(metrics_path)
    publish_state = read_json(publish_state_path) if publish_state_path.is_file() else {}
    recipes = active_recipes()

    metrics_by_key = {metric_key(row): row for row in metrics_rows}
    pending_classes = set(policy.get("pending_classifications", ["pending"]))
    stale_threshold = int(policy.get("freshness_windows", {}).get("metrics_stale_days", 4))

    pending_metrics_posts: list[dict] = []
    stale_pending_metrics_posts: list[dict] = []
    published_posts: list[dict] = []

    # Published-post inventory (2026-07-12): union of manual-log posts and
    # metrics-only Architecture A posts with a real, actionable
    # instagram_media_id -- closes the gap where a real, already-published
    # Architecture A post (e.g. a Reel/Story with no manual-log entry) was
    # previously invisible to published_post_count/pending/stale tracking,
    # even though Meta-refresh candidate discovery and recipe/winner
    # scoring already treat metrics rows as first-class.
    published_post_rows = build_published_post_inventory(manual_rows, metrics_rows)

    for post in published_post_rows:
        key = metric_key(post)
        metric = metrics_by_key.get(key, {})
        classification = (metric.get("classification") or "missing").strip().lower()
        post_summary = {
            "date": post.get("date", ""),
            "platform": post.get("platform", ""),
            "slot_id": post.get("slot_id", ""),
            "lane": post.get("lane", ""),
            "hook_category": post.get("hook_category", ""),
            "post_url": post.get("post_url", ""),
            "classification": classification,
            "score": metric.get("score", ""),
        }
        published_posts.append(post_summary)

        if classification in pending_classes or classification == "missing":
            pending_metrics_posts.append(post_summary)
            age = days_since(post.get("date", ""), current_date)
            if age is not None and age >= stale_threshold:
                stale_pending_metrics_posts.append(post_summary)

    boost_by_recipe_id, reasons_by_recipe, winner_posts = build_queue_boosts(
        metrics_rows,
        recipes,
        policy,
        current_date,
    )

    preferred_recipe_ids = [
        recipe_id
        for recipe_id, _ in sorted(boost_by_recipe_id.items(), key=lambda item: (-item[1], item[0]))
    ]

    signal_followup_map = followup_policy.get("signals_to_followups", {})
    class_counts = Counter((row.get("classification") or "").strip().lower() for row in metrics_rows)
    operational_alerts: list[str] = []
    if len(stale_pending_metrics_posts) >= int(policy.get("operational_alerts", {}).get("stale_pending_metrics_threshold", 1)):
        operational_alerts.append("Some published posts are still missing resolved metrics updates.")

    report_path = NEXT_ACTIONS / args.date / f"lena_post_outcome_learning_state_{args.date}.json"
    report = {
        "report_type": "lena_post_outcome_learning_state",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "date": args.date,
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "published_post_count": len(published_post_rows),
        "metrics_row_count": len(metrics_rows),
        "metrics_classification_counts": dict(class_counts),
        "winner_posts": winner_posts,
        "pending_metrics_posts": pending_metrics_posts,
        "stale_pending_metrics_posts": stale_pending_metrics_posts,
        "queue_boosts": {
            "boost_by_recipe_id": boost_by_recipe_id,
            "reasons_by_recipe": reasons_by_recipe,
            "preferred_recipe_ids": preferred_recipe_ids,
        },
        "followup_policy_hints": signal_followup_map,
        "operational_alerts": operational_alerts,
        "source_paths": {
            "manual_post_log": str(manual_path),
            "post_metrics": str(metrics_path),
            "publish_state": str(publish_state_path),
        },
        "publish_state_summary": {
            "published_fingerprint_count": len(
                publish_state.get("quality_gate", {}).get("published_fingerprints", [])
            ),
            "published_media_count": len(
                publish_state.get("quality_gate", {}).get("published_media", [])
            ),
        },
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
                "published_post_count": len(published_post_rows),
                "winner_post_count": len(winner_posts),
                "pending_metrics_count": len(pending_metrics_posts),
                "preferred_recipe_ids": preferred_recipe_ids,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
