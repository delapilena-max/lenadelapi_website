from __future__ import annotations

"""
Lena World-State Builder v1

Builds a continuity-aware life snapshot from approved Lena strategy assets
plus realism-memory history. Outputs:
1. a dated world-state report under pipeline/strategy/lena/next_actions/{date}/
2. a rolling canonical state file under pipeline/state/

Safe: no API calls, no generation, no upload, no publish, no queue mutation.
"""

import argparse
import json
from collections import Counter
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
PROMPTS = ROOT / "pipeline" / "prompt_banks" / "lena"
STATE_DIR = ROOT / "pipeline" / "state"
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"

POLICY_PATH = NODE / "world_continuity_policy_v1.json"
PERSONA_PATH = NODE / "persona.json"
CADENCE_PATH = NODE / "daily_cadence.json"
BUCKETS_PATH = NODE / "content_buckets.json"
GEN_POLICY_PATH = ROOT / "pipeline" / "config" / "lena_generation_policy.json"
REALISM_POLICY_PATH = NODE / "life_engine_realism_memory_policy_v1.json"
RECIPE_BANK_PATH = PROMPTS / "lena_high_caliber_prompt_recipe_bank_v1.json"
WARDROBE_PATH = PROMPTS / "lena_wardrobe_catalog_v1.json"
ENV_PATH = PROMPTS / "lena_environment_catalog_v1.json"


HOME_HINTS = (
    "apartment",
    "bedroom",
    "bathroom",
    "hallway",
    "living room",
    "entryway",
    "mirror",
    "vanity",
    "kitchen",
    "balcony",
)
FITNESS_HINTS = ("gym", "workout", "athletic", "fitness")
PUBLIC_HINTS = (
    "street",
    "coffee",
    "sidewalk",
    "doorway",
    "rooftop",
    "restaurant",
    "elevator",
    "staircase",
    "garage",
    "parking",
    "night",
    "city",
    "venue",
)


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def latest_dated_file(base_dir: Path, pattern: str, date_str: str) -> Path | None:
    dated = base_dir / date_str / pattern.format(date=date_str)
    if dated.is_file():
        return dated
    candidates = sorted(base_dir.glob(f"*/{pattern.format(date='*')}"))
    return candidates[-1] if candidates else None


def parse_iso_date(date_str: str) -> date_cls:
    return date_cls.fromisoformat(date_str)


def season_for_date(day: date_cls) -> str:
    if day.month in {12, 1, 2}:
        return "winter"
    if day.month in {3, 4, 5}:
        return "spring"
    if day.month in {6, 7, 8}:
        return "summer"
    return "fall"


def load_memory_entries(realism_policy: dict) -> list[dict]:
    rel_path = realism_policy.get("memory_path", "")
    if not rel_path:
        return []
    memory_path = ROOT / Path(rel_path)
    if not memory_path.is_file():
        return []
    memory = read_json(memory_path)
    return memory.get("entries", [])


def active_recipes(recipe_bank: dict) -> list[dict]:
    items = [
        recipe for recipe in recipe_bank.get("recipes", [])
        if recipe.get("production_status") != "test_only"
    ]
    items.sort(
        key=lambda recipe: (
            not recipe.get("controlled_proof_lane", False),
            recipe.get("proof_priority") is None,
            recipe.get("proof_priority", 999),
            recipe.get("id", ""),
        )
    )
    return items


def as_map(items: list[dict], key: str) -> dict[str, dict]:
    return {item.get(key, ""): item for item in items if item.get(key)}


def classify_context(recipe: dict, env: dict) -> str:
    text = " ".join(
        [
            recipe.get("scene_type", ""),
            recipe.get("title", ""),
            recipe.get("content_pillar", ""),
            env.get("name", ""),
            env.get("production_lane", ""),
            env.get("prompt_fragment", ""),
        ]
    ).lower()
    if any(token in text for token in FITNESS_HINTS):
        return "fitness"
    if any(token in text for token in HOME_HINTS):
        return "home"
    if any(token in text for token in PUBLIC_HINTS):
        return "public"
    return "unknown"


def enrich_entry(
    entry: dict,
    recipes_by_id: dict[str, dict],
    outfits_by_id: dict[str, dict],
    envs_by_id: dict[str, dict],
) -> dict:
    recipe = recipes_by_id.get(entry.get("recipe_id", ""), {})
    outfit = outfits_by_id.get(entry.get("outfit_id", ""), {})
    env = envs_by_id.get(entry.get("environment_id", ""), {})
    return {
        "task_id": entry.get("task_id", ""),
        "date": entry.get("date", ""),
        "logged_at": entry.get("logged_at", ""),
        "qa_status": entry.get("qa_status", ""),
        "recipe_id": entry.get("recipe_id", ""),
        "recipe_title": recipe.get("title", ""),
        "scene_type": recipe.get("scene_type", ""),
        "content_pillar": recipe.get("content_pillar", ""),
        "production_proof_mode": recipe.get("production_proof_mode", False),
        "proof_priority": recipe.get("proof_priority"),
        "outfit_id": entry.get("outfit_id", ""),
        "outfit_name": outfit.get("name", ""),
        "style_lane": outfit.get("style_lane", ""),
        "occasion": outfit.get("occasion", ""),
        "environment_id": entry.get("environment_id", ""),
        "environment_name": env.get("name", ""),
        "environment_lane": env.get("production_lane", ""),
        "context_class": classify_context(recipe, env),
    }


def sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda item: (item.get("date", ""), item.get("logged_at", "")))


def summarize_recent(recent: list[dict], balance_window: int) -> dict:
    scene_counts = Counter(item.get("scene_type", "") for item in recent if item.get("scene_type"))
    pillar_counts = Counter(item.get("content_pillar", "") for item in recent if item.get("content_pillar"))
    recipe_counts = Counter(item.get("recipe_id", "") for item in recent if item.get("recipe_id"))
    outfit_counts = Counter(item.get("outfit_id", "") for item in recent if item.get("outfit_id"))
    env_counts = Counter(item.get("environment_id", "") for item in recent if item.get("environment_id"))
    env_lane_counts = Counter(item.get("environment_lane", "") for item in recent if item.get("environment_lane"))
    style_counts = Counter(item.get("style_lane", "") for item in recent if item.get("style_lane"))
    context_window = recent[-balance_window:] if balance_window and recent else recent
    context_counts = Counter(item.get("context_class", "unknown") for item in context_window)
    total_context = sum(context_counts.values()) or 1
    return {
        "scene_type_counts": dict(scene_counts),
        "content_pillar_counts": dict(pillar_counts),
        "recipe_counts": dict(recipe_counts),
        "outfit_counts": dict(outfit_counts),
        "environment_counts": dict(env_counts),
        "environment_lane_counts": dict(env_lane_counts),
        "style_lane_counts": dict(style_counts),
        "context_counts": dict(context_counts),
        "home_share": round(context_counts.get("home", 0) / total_context, 3),
        "public_or_fitness_share": round(
            (context_counts.get("public", 0) + context_counts.get("fitness", 0)) / total_context,
            3,
        ),
    }


def latest_step_report(date_str: str) -> dict:
    path = latest_dated_file(
        NEXT_ACTIONS,
        "lena_next_generation_step_{date}.json",
        date_str,
    )
    return read_json(path) if path and path.is_file() else {}


def continuity_alerts(summary: dict, policy: dict, recent: list[dict]) -> list[str]:
    soft_caps = policy["anti_repetition"]["soft_caps"]
    targets = policy["context_mix_targets"]
    alerts: list[str] = []

    if summary["home_share"] > targets["max_home_share_in_balance_window"]:
        alerts.append(
            "Home-coded scenes are overrepresented in the recent balance window; next broader rotation should push outside-world or gym lanes."
        )
    if summary["public_or_fitness_share"] < targets["min_public_or_fitness_share_in_balance_window"]:
        alerts.append(
            "Public-world and fitness evidence is too thin in the recent balance window; Lena needs more outside-life proof."
        )
    if summary["environment_lane_counts"].get("mirror_fitcheck", 0) > soft_caps["mirror_lane_in_balance_window"]:
        alerts.append(
            "Mirror-fitcheck usage is too concentrated right now; continue proofing only as a debug lane and rotate broader content away from mirrors."
        )
    proof_count = sum(1 for item in recent if item.get("production_proof_mode"))
    if proof_count > soft_caps["proof_mode_in_balance_window"]:
        alerts.append(
            "Proof-mode lanes are crowding the recent memory window; broader queue slots should favor non-proof public or lifestyle lanes."
        )
    return alerts


def candidate_row(
    recipe: dict,
    outfit: dict,
    env: dict,
    recent: list[dict],
    summary: dict,
    policy: dict,
    locked_recipe_id: str,
) -> dict:
    scoring = policy["candidate_scoring"]
    soft_caps = policy["anti_repetition"]["soft_caps"]
    context_targets = policy["context_mix_targets"]

    recipe_id = recipe.get("id", "")
    scene_type = recipe.get("scene_type", "")
    content_pillar = recipe.get("content_pillar", "")
    outfit_id = outfit.get("outfit_id", "")
    env_id = env.get("environment_id", "")
    env_lane = env.get("production_lane", "")
    style_lane = outfit.get("style_lane", "")
    context_class = classify_context(recipe, env)
    proof_mode = recipe.get("production_proof_mode", False)

    last = recent[-1] if recent else {}
    score = 100
    reasons: list[str] = []
    blocked = False

    recipe_count = summary["recipe_counts"].get(recipe_id, 0)
    scene_count = summary["scene_type_counts"].get(scene_type, 0)
    outfit_count = summary["outfit_counts"].get(outfit_id, 0)
    env_count = summary["environment_counts"].get(env_id, 0)
    env_lane_count = summary["environment_lane_counts"].get(env_lane, 0)
    style_count = summary["style_lane_counts"].get(style_lane, 0)
    pillar_count = summary["content_pillar_counts"].get(content_pillar, 0)

    if policy["anti_repetition"]["avoid_back_to_back_same_recipe"] and recipe_id == last.get("recipe_id"):
        score -= scoring["same_recipe_penalty"]
        reasons.append("same recipe as the latest reviewed memory entry")
    if policy["anti_repetition"]["avoid_back_to_back_same_scene_type"] and scene_type == last.get("scene_type"):
        score -= scoring["same_scene_type_penalty"]
        reasons.append("same scene type as the latest reviewed memory entry")
    if policy["anti_repetition"]["avoid_back_to_back_same_environment_id"] and env_id == last.get("environment_id"):
        score -= scoring["same_environment_penalty"]
        reasons.append("same environment as the latest reviewed memory entry")
    if policy["anti_repetition"]["avoid_back_to_back_same_outfit_id"] and outfit_id == last.get("outfit_id"):
        score -= scoring["same_outfit_penalty"]
        reasons.append("same outfit as the latest reviewed memory entry")

    if recipe_count >= soft_caps["same_recipe_in_recent_window"]:
        score -= scoring["same_recipe_penalty"]
        reasons.append(f"recipe already appears {recipe_count} time(s) in the recent memory window")
    if scene_count >= soft_caps["same_scene_type_in_recent_window"]:
        score -= scoring["same_scene_type_penalty"]
        reasons.append(f"scene type already appears {scene_count} time(s) in the recent memory window")
    if env_count >= soft_caps["same_environment_id_in_recent_window"]:
        score -= scoring["same_environment_penalty"]
        reasons.append(f"environment already appears {env_count} time(s) in the recent memory window")
    if outfit_count >= soft_caps["same_outfit_id_in_recent_window"]:
        score -= scoring["same_outfit_penalty"]
        reasons.append(f"outfit already appears {outfit_count} time(s) in the recent memory window")
    if env_lane_count >= soft_caps["same_environment_lane_in_recent_window"]:
        score -= scoring["same_environment_lane_penalty"]
        reasons.append(f"environment lane '{env_lane}' is already concentrated")
    if style_count >= soft_caps["same_style_lane_in_recent_window"]:
        score -= scoring["same_style_lane_penalty"]
        reasons.append(f"style lane '{style_lane}' is already concentrated")
    if pillar_count >= soft_caps["same_content_pillar_in_recent_window"]:
        score -= scoring["same_content_pillar_penalty"]
        reasons.append(f"content pillar '{content_pillar}' is already concentrated")

    if env_lane == "mirror_fitcheck" and env_lane_count >= soft_caps["mirror_lane_in_balance_window"]:
        score -= scoring["mirror_lane_penalty"]
        reasons.append("mirror lane is already overused in the current balance window")

    proof_count = sum(1 for item in recent if item.get("production_proof_mode"))
    if proof_mode and proof_count >= soft_caps["proof_mode_in_balance_window"]:
        score -= scoring["proof_mode_overuse_penalty"]
        reasons.append("proof-mode lane is already overused in the current balance window")
    if not proof_mode:
        score += scoring["non_proof_rotation_bonus"]
        reasons.append("helps reopen broader non-proof wardrobe and environment rotation")

    if context_class == "home" and summary["home_share"] > context_targets["max_home_share_in_balance_window"]:
        score -= scoring["home_overuse_penalty"]
        reasons.append("home-coded scenes are already overrepresented")
    if context_class in {"public", "fitness"} and summary["public_or_fitness_share"] < context_targets["min_public_or_fitness_share_in_balance_window"]:
        score += scoring["public_balance_bonus"]
        reasons.append("improves outside-world proof for Lena's life arc")

    if pillar_count == 0:
        score += scoring["fresh_content_pillar_bonus"]
        reasons.append("fresh content pillar in the recent memory window")
    if style_count == 0:
        score += scoring["fresh_style_lane_bonus"]
        reasons.append("fresh style lane in the recent memory window")

    proof_priority = recipe.get("proof_priority")
    if isinstance(proof_priority, int):
        bonus = max(0, scoring["proof_priority_bonus_ceiling"] - proof_priority + 1)
        if bonus:
            score += bonus
            reasons.append(f"recipe-bank proof priority {proof_priority}")

    if locked_recipe_id and recipe_id == locked_recipe_id:
        reasons.append("currently locked as the immediate proof/debug lane")

    if outfit.get("status") == "rejected" or env.get("status") == "rejected":
        blocked = True
        reasons.append("linked outfit or environment is rejected in catalog metadata")

    if score < 55:
        blocked = True

    return {
        "recipe_id": recipe_id,
        "title": recipe.get("title", ""),
        "scene_type": scene_type,
        "content_pillar": content_pillar,
        "outfit_id": outfit_id,
        "outfit_name": outfit.get("name", ""),
        "environment_id": env_id,
        "environment_name": env.get("name", ""),
        "style_lane": style_lane,
        "environment_lane": env_lane,
        "context_class": context_class,
        "production_proof_mode": proof_mode,
        "controlled_proof_lane": recipe.get("controlled_proof_lane", False),
        "proof_priority": proof_priority,
        "score": score,
        "blocked": blocked,
        "reasons": reasons,
    }


def canonical_state_payload(
    report: dict,
    state_path: Path,
) -> dict:
    controls = report.get("queue_rotation_controls", {})
    state_path_value = state_path.relative_to(ROOT).as_posix() if state_path.is_absolute() else state_path.as_posix()
    return {
        "version": "v1",
        "updated_at": report.get("generated_at", ""),
        "date": report.get("date", ""),
        "season": report.get("calendar", {}).get("season", ""),
        "latest_reviewed_recipe_id": report.get("continuity_snapshot", {}).get("last_recipe_id", ""),
        "latest_reviewed_outfit_id": report.get("continuity_snapshot", {}).get("last_outfit_id", ""),
        "latest_reviewed_environment_id": report.get("continuity_snapshot", {}).get("last_environment_id", ""),
        "continuity_alerts": report.get("continuity_alerts", []),
        "blocked_recipe_ids": controls.get("blocked_recipe_ids", []),
        "deprioritized_recipe_ids": controls.get("deprioritized_recipe_ids", []),
        "preferred_rotation_recipe_ids": controls.get("prefer_recipe_ids", []),
        "recent_counts": report.get("continuity_snapshot", {}).get("recent_counts", {}),
        "state_path": state_path_value,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Lena's canonical continuity/world-state report."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for output folder")
    args = parser.parse_args()

    policy = read_json(POLICY_PATH)
    persona = read_json(PERSONA_PATH)
    cadence = read_json(CADENCE_PATH)
    buckets = read_json(BUCKETS_PATH)
    gen_policy = read_json(GEN_POLICY_PATH)
    realism_policy = read_json(REALISM_POLICY_PATH)
    recipe_bank = read_json(RECIPE_BANK_PATH)
    wardrobe = read_json(WARDROBE_PATH)
    environments = read_json(ENV_PATH)

    recipes = active_recipes(recipe_bank)
    recipes_by_id = as_map(recipes, "id")
    outfits_by_id = as_map(wardrobe.get("outfits", []), "outfit_id")
    envs_by_id = as_map(environments.get("environments", []), "environment_id")

    memory_entries = sort_entries(load_memory_entries(realism_policy))
    recent_window_size = int(policy.get("recent_memory_window", 10))
    balance_window = int(policy.get("balance_window", 8))
    recent = [
        enrich_entry(entry, recipes_by_id, outfits_by_id, envs_by_id)
        for entry in memory_entries[-recent_window_size:]
    ]
    summary = summarize_recent(recent, balance_window)
    alerts = continuity_alerts(summary, policy, recent)

    next_step = latest_step_report(args.date)
    recommendation = next_step.get("recommendation", {})
    locked_recipe_id = recommendation.get("recommended_recipe_id", "")

    candidates = []
    for recipe in recipes:
        outfit = outfits_by_id.get(recipe.get("wardrobe_outfit_id", ""), {})
        env = envs_by_id.get(recipe.get("environment_id", ""), {})
        candidates.append(
            candidate_row(
                recipe,
                outfit,
                env,
                recent,
                summary,
                policy,
                locked_recipe_id,
            )
        )

    broader_candidates = [
        row for row in candidates
        if row["recipe_id"] != locked_recipe_id and not row["blocked"]
    ]
    broader_candidates.sort(
        key=lambda row: (
            not row.get("controlled_proof_lane", False),
            -row["score"],
            row["proof_priority"] is None,
            row["proof_priority"] or 999,
            row["recipe_id"],
        )
    )

    queue_policy = policy["queue_rotation_policy"]
    blocked_recipe_ids = [row["recipe_id"] for row in candidates if row["blocked"]]
    deprioritized_recipe_ids = [
        row["recipe_id"]
        for row in candidates
        if not row["blocked"] and row["score"] < queue_policy["deprioritize_if_score_below"]
    ]
    prefer_recipe_ids = [
        row["recipe_id"] for row in broader_candidates[: queue_policy["prefer_top_n"]]
    ]
    reasons_by_recipe = {
        row["recipe_id"]: row["reasons"][:4]
        for row in candidates
        if row["reasons"]
    }

    target_day = parse_iso_date(args.date)
    state_path = ROOT / Path(policy["state_path"])
    out_dir = NEXT_ACTIONS / args.date
    report_path = out_dir / f"lena_world_state_{args.date}.json"

    continuity_snapshot = {
        "recent_window_size": recent_window_size,
        "balance_window": balance_window,
        "recent_entries": recent,
        "last_recipe_id": recent[-1]["recipe_id"] if recent else "",
        "last_outfit_id": recent[-1]["outfit_id"] if recent else "",
        "last_environment_id": recent[-1]["environment_id"] if recent else "",
        "last_scene_type": recent[-1]["scene_type"] if recent else "",
        "recent_counts": summary,
    }

    report = {
        "report_type": "lena_world_state",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "date": args.date,
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "calendar": {
            "season": season_for_date(target_day),
            "month": target_day.month,
            "day_of_week": target_day.strftime("%A"),
        },
        "persona_positioning": persona.get("public_positioning", ""),
        "identity_rule": persona.get("identity_rule", ""),
        "daily_slots": cadence.get("daily_posts", 0),
        "content_mix_targets": buckets.get("buckets", {}),
        "generation_policy": gen_policy.get("anti_repetition", {}),
        "continuity_alerts": alerts,
        "continuity_snapshot": continuity_snapshot,
        "immediate_locked_proof_lane": {
            "recipe_id": recommendation.get("recommended_recipe_id", ""),
            "outfit_id": recommendation.get("recommended_outfit_id", ""),
            "environment_id": recommendation.get("recommended_environment_id", ""),
            "action_type": recommendation.get("action_type", ""),
            "next_live_gate": recommendation.get("next_live_gate", ""),
        },
        "broader_rotation_candidates": broader_candidates[: policy["rotation_preview_limit"]],
        "queue_rotation_controls": {
            "blocked_recipe_ids": blocked_recipe_ids,
            "deprioritized_recipe_ids": deprioritized_recipe_ids,
            "prefer_recipe_ids": prefer_recipe_ids,
            "reasons_by_recipe": reasons_by_recipe,
        },
        "artifacts": {
            "world_state_report": str(report_path),
            "canonical_state_path": str(state_path),
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

    state_payload = canonical_state_payload(report, state_path)
    write_json(report_path, report)
    write_json(state_path, state_payload)

    print(
        json.dumps(
            {
                "ok": True,
                "output_path": str(report_path),
                "canonical_state_path": str(state_path),
                "continuity_alert_count": len(alerts),
                "prefer_recipe_ids": prefer_recipe_ids,
                "deprioritized_recipe_ids": deprioritized_recipe_ids,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
