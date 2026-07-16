from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NEXT_ACTIONS = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"
AUDIT_SCRIPT = ROOT / "tools" / "strategy" / "lena_audit_autonomous_generation_readiness_v1.py"
RECIPE_BANK = ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_high_caliber_prompt_recipe_bank_v1.json"
WORLD_STATE_PATTERN = "lena_world_state_{date}.json"
ENGAGEMENT_DEMAND_PATTERN = "lena_engagement_demand_state_{date}.json"
POST_OUTCOME_PATTERN = "lena_post_outcome_learning_state_{date}.json"


LANE_GOALS = {
    "hcr_011": ["face_skin_win", "garment_stability_win", "home_realism"],
    "hcr_012": ["face_skin_win", "home_realism", "deterministic_lane"],
    "hcr_007": ["face_skin_win", "home_realism", "environment_realism"],
    "hcr_005": ["garment_stability_win", "public_world", "deterministic_lane"],
    "hcr_002": ["public_world", "street_realism", "deterministic_lane"],
    "hcr_010": ["public_world", "street_realism", "deterministic_lane"],
    "hcr_008": ["garment_stability_win", "aspirational_realism", "deterministic_lane"],
}


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_date_bound_json(
    path: Path,
    expected_date: str,
    *,
    label: str,
) -> dict:
    data = read_json(path)
    actual_date = str(data.get("date", "")).strip()
    if expected_date and actual_date and actual_date != expected_date:
        raise SystemExit(
            f"[ABORT] {label}_date_mismatch: expected {expected_date}, got {actual_date} from {path}"
        )
    return data


def recipe_meta_map() -> dict[str, dict]:
    if not RECIPE_BANK.is_file():
        return {}
    try:
        data = read_json(RECIPE_BANK)
    except Exception:
        return {}
    return {
        recipe.get("id", ""): recipe
        for recipe in data.get("recipes", [])
        if recipe.get("id")
    }


def latest_audit(date_str: str) -> Path:
    dated = NEXT_ACTIONS / date_str / f"lena_autonomous_generation_readiness_audit_{date_str}.json"
    if dated.is_file():
        return dated
    candidates = sorted(
        NEXT_ACTIONS.glob("*/lena_autonomous_generation_readiness_audit_*.json")
    )
    if not candidates:
        raise SystemExit(
            "[ABORT] No readiness audit found. Run "
            "lena_audit_autonomous_generation_readiness_v1.py first."
        )
    return candidates[-1]


def latest_next_step(date_str: str) -> Path | None:
    dated = NEXT_ACTIONS / date_str / f"lena_next_generation_step_{date_str}.json"
    if dated.is_file():
        return dated
    candidates = sorted(NEXT_ACTIONS.glob("*/lena_next_generation_step_*.json"))
    return candidates[-1] if candidates else None


def latest_world_state(date_str: str) -> Path | None:
    dated = NEXT_ACTIONS / date_str / WORLD_STATE_PATTERN.format(date=date_str)
    if dated.is_file():
        return dated
    candidates = sorted(NEXT_ACTIONS.glob("*/lena_world_state_*.json"))
    return candidates[-1] if candidates else None


def latest_engagement_demand(date_str: str) -> Path | None:
    dated = NEXT_ACTIONS / date_str / ENGAGEMENT_DEMAND_PATTERN.format(date=date_str)
    if dated.is_file():
        return dated
    candidates = sorted(NEXT_ACTIONS.glob("*/lena_engagement_demand_state_*.json"))
    return candidates[-1] if candidates else None


def latest_post_outcome(date_str: str) -> Path | None:
    dated = NEXT_ACTIONS / date_str / POST_OUTCOME_PATTERN.format(date=date_str)
    if dated.is_file():
        return dated
    candidates = sorted(NEXT_ACTIONS.glob("*/lena_post_outcome_learning_state_*.json"))
    return candidates[-1] if candidates else None


def lane_priority_boosts(
    memory_progress: dict,
    recipe_id: str,
    recipe_meta: dict | None = None,
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    goals = LANE_GOALS.get(recipe_id, [])
    recipe_meta = recipe_meta or {}

    if memory_progress.get("face_skin_wins_logged", 0) < 2 and "face_skin_win" in goals:
        score += 30
        reasons.append("fills face/skin win deficit")
    if memory_progress.get("garment_stability_wins_logged", 0) < 2 and "garment_stability_win" in goals:
        score += 25
        reasons.append("fills garment-stability win deficit")
    if memory_progress.get("wins_logged", 0) < 3 and "public_world" in goals:
        score += 18
        reasons.append("helps reach broader publishable-win count in public-world lane")
    if "deterministic_lane" in goals:
        score += 12
        reasons.append("already deterministic at packet/payload layer")
    if "home_realism" in goals:
        score += 8
        reasons.append("supports believable home-life continuity")
    if "street_realism" in goals:
        score += 8
        reasons.append("supports believable outside-world continuity")
    if "environment_realism" in goals:
        score += 6
        reasons.append("useful for lived-in environment proof")
    if "aspirational_realism" in goals:
        score += 5
        reasons.append("keeps aspirational lane grounded")
    proof_priority = recipe_meta.get("proof_priority")
    if isinstance(proof_priority, int):
        boost = max(0, 14 - proof_priority)
        if boost:
            score += boost
            reasons.append(
                f"recipe bank proof priority {proof_priority}"
            )
    if recipe_meta.get("production_proof_mode", False):
        score += 5
        reasons.append("marked as an active proof-mode lane")
    return score, reasons


def continuity_adjustment(
    recipe_id: str,
    world_state: dict | None,
) -> tuple[int, list[str]]:
    if not world_state:
        return 0, []
    controls = world_state.get("queue_rotation_controls", {})
    blocked = set(controls.get("blocked_recipe_ids", []))
    deprioritized = set(controls.get("deprioritized_recipe_ids", []))
    preferred = set(controls.get("prefer_recipe_ids", []))
    reasons_by_recipe = controls.get("reasons_by_recipe", {})

    score = 0
    reasons: list[str] = []

    if recipe_id in preferred:
        score += 20
        reasons.append("preferred by current world-state rotation controls")
    if recipe_id in deprioritized:
        score -= 18
        reasons.append("deprioritized by current world-state rotation controls")
    if recipe_id in blocked:
        score -= 45
        reasons.append("temporarily blocked by current continuity pressure")

    for reason in reasons_by_recipe.get(recipe_id, [])[:2]:
        reason_text = f"world-state note: {reason}"
        if reason_text not in reasons:
            reasons.append(reason_text)

    return score, reasons


def engagement_adjustment(
    recipe_id: str,
    engagement_demand: dict | None,
) -> tuple[int, list[str]]:
    if not engagement_demand:
        return 0, []
    queue_boosts = engagement_demand.get("queue_boosts", {})
    boost_map = queue_boosts.get("boost_by_recipe_id", {})
    reasons_map = queue_boosts.get("reasons_by_recipe", {})

    boost = int(boost_map.get(recipe_id, 0) or 0)
    reasons = [f"engagement-state note: {item}" for item in reasons_map.get(recipe_id, [])[:2]]
    return boost, reasons


def post_outcome_adjustment(
    recipe_id: str,
    post_outcome: dict | None,
) -> tuple[int, list[str]]:
    if not post_outcome:
        return 0, []
    queue_boosts = post_outcome.get("queue_boosts", {})
    boost_map = queue_boosts.get("boost_by_recipe_id", {})
    reasons_map = queue_boosts.get("reasons_by_recipe", {})
    boost = int(boost_map.get(recipe_id, 0) or 0)
    reasons = [f"post-outcome note: {item}" for item in reasons_map.get(recipe_id, [])[:2]]
    return boost, reasons


def build_queue(
    audit: dict,
    date_str: str,
    limit: int,
    world_state: dict | None = None,
    engagement_demand: dict | None = None,
    post_outcome: dict | None = None,
) -> list[dict]:
    memory = audit["memory_progress"]
    recipe_meta_by_id = recipe_meta_map()
    lanes = []

    for lane in audit["lanes"]:
        grade = lane["autonomy_grade"]
        if grade not in {"ready", "ready_with_warnings"}:
            continue

        base = 100 if grade == "ready" else 80
        recipe_meta = recipe_meta_by_id.get(lane["recipe_id"], {})
        score, reasons = lane_priority_boosts(
            memory,
            lane["recipe_id"],
            recipe_meta,
        )
        continuity_score, continuity_reasons = continuity_adjustment(
            lane["recipe_id"],
            world_state,
        )
        score += continuity_score
        reasons.extend(continuity_reasons)
        engagement_score, engagement_reasons = engagement_adjustment(
            lane["recipe_id"],
            engagement_demand,
        )
        score += engagement_score
        reasons.extend(engagement_reasons)
        post_outcome_score, post_outcome_reasons = post_outcome_adjustment(
            lane["recipe_id"],
            post_outcome,
        )
        score += post_outcome_score
        reasons.extend(post_outcome_reasons)

        penalty = 0
        if lane["payload_headroom"] is not None and lane["payload_headroom"] < 50:
            penalty += 10
            reasons.append("payload headroom still somewhat narrow")

        total = base + score - penalty
        lanes.append(
            {
                "recipe_id": lane["recipe_id"],
                "title": lane["title"],
                "scene_type": lane["scene_type"],
                "autonomy_grade": grade,
                "payload_headroom": lane["payload_headroom"],
                "outfit_used": lane["outfit_used"],
                "environment_used": lane["environment_used"],
                "proof_priority": recipe_meta.get("proof_priority"),
                "production_proof_mode": recipe_meta.get("production_proof_mode", False),
                "controlled_proof_lane": recipe_meta.get("controlled_proof_lane", False),
                "priority_score": total,
                "why": reasons or lane["autonomy_reasons"],
                "recommended_packet_command": (
                    "python tools/strategy/lena_build_content_packet_dryrun_v1.py "
                    f"--recipe {lane['recipe_id']} --date {date_str}"
                ),
                "recommended_handoff_command": (
                    "python tools/strategy/lena_build_next_live_image_handoff_v1.py "
                    f"--date {date_str}"
                ),
            }
        )

    lanes.sort(
        key=lambda row: (
            not row.get("controlled_proof_lane", False),
            -row["priority_score"],
            row["proof_priority"] is None,
            row["proof_priority"] or 999,
            row["payload_headroom"] is None,
            -(row["payload_headroom"] or 0),
            row["recipe_id"],
        )
    )
    return lanes[:limit]


def build_rotation_preview(
    audit: dict,
    date_str: str,
    world_state: dict | None = None,
    engagement_demand: dict | None = None,
    post_outcome: dict | None = None,
    *,
    exclude_recipe_id: str = "",
    exclude_outfit_id: str = "",
    limit: int = 4,
) -> list[dict]:
    queue_candidates = build_queue(
        audit,
        date_str,
        limit=50,
        world_state=world_state,
        engagement_demand=engagement_demand,
        post_outcome=post_outcome,
    )
    non_proof_candidates = [
        row for row in queue_candidates
        if not row.get("production_proof_mode", False)
    ]
    candidate_pool = non_proof_candidates or queue_candidates
    preview: list[dict] = []
    seen_outfits: set[str] = set()

    for row in candidate_pool:
        if exclude_recipe_id and row["recipe_id"] == exclude_recipe_id:
            continue
        if exclude_outfit_id and row["outfit_used"] == exclude_outfit_id:
            continue
        if row["outfit_used"] in seen_outfits:
            continue

        preview.append(
            {
                "recipe_id": row["recipe_id"],
                "title": row["title"],
                "scene_type": row["scene_type"],
                "outfit_used": row["outfit_used"],
                "environment_used": row["environment_used"],
                "payload_headroom": row["payload_headroom"],
                "proof_priority": row.get("proof_priority"),
                "priority_score": row["priority_score"],
                "why": row["why"],
            }
        )
        seen_outfits.add(row["outfit_used"])
        if len(preview) >= limit:
            break

    return preview


def apply_proof_lane_lock(queue: list[dict], proof_lane_lock: dict) -> list[dict]:
    locked_recipe_id = proof_lane_lock.get("recipe_id", "")
    if not locked_recipe_id:
        return queue

    locked_row = None
    remainder: list[dict] = []
    for row in queue:
        if row["recipe_id"] == locked_recipe_id and locked_row is None:
            locked_row = dict(row)
            continue
        remainder.append(row)

    if locked_row is None:
        return queue

    why = list(locked_row.get("why", []))
    lock_reason = "matches current proof-lane lock from next-step recommendation"
    if lock_reason not in why:
        why.insert(0, lock_reason)
    locked_row["why"] = why
    locked_row["proof_lane_locked"] = True
    return [locked_row] + remainder


def should_apply_proof_lane_lock(audit: dict, proof_lane_lock: dict) -> bool:
    locked_recipe_id = str(proof_lane_lock.get("recipe_id", "")).strip()
    action_type = str(proof_lane_lock.get("action_type", "")).strip()
    broader_ready = bool(
        audit.get("memory_progress", {}).get("broader_autonomous_generation_ready", False)
    )
    if not locked_recipe_id:
        return False
    if not broader_ready:
        return True
    return action_type in {
        "collect_first_controlled_proof",
        "face_priority_skin_realism_proof_lane",
    }


def save_report(report: dict, date_str: str) -> Path:
    out_dir = NEXT_ACTIONS / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lena_autonomous_generation_queue_dryrun_{date_str}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a dry-run autonomous generation queue from readiness + realism-memory state."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for output folder")
    parser.add_argument("--limit", type=int, default=4, help="How many queue slots to include")
    parser.add_argument(
        "--engagement-demand-path",
        default="",
        help="Optional explicit engagement-demand report path override.",
    )
    parser.add_argument(
        "--post-outcome-path",
        default="",
        help="Optional explicit post-outcome report path override.",
    )
    args = parser.parse_args()

    audit_path = latest_audit(args.date)
    audit = read_date_bound_json(audit_path, args.date, label="readiness_audit")
    world_state_path = latest_world_state(args.date)
    world_state = (
        read_date_bound_json(world_state_path, args.date, label="world_state")
        if world_state_path
        else {}
    )
    engagement_demand_path = (
        Path(args.engagement_demand_path)
        if args.engagement_demand_path
        else latest_engagement_demand(args.date)
    )
    engagement_demand = (
        read_date_bound_json(
            engagement_demand_path,
            args.date,
            label="engagement_demand",
        )
        if engagement_demand_path
        else {}
    )
    post_outcome_path = (
        Path(args.post_outcome_path)
        if args.post_outcome_path
        else latest_post_outcome(args.date)
    )
    post_outcome = (
        read_date_bound_json(
            post_outcome_path,
            args.date,
            label="post_outcome",
        )
        if post_outcome_path
        else {}
    )
    queue_full = build_queue(
        audit,
        args.date,
        max(args.limit, 50),
        world_state=world_state,
        engagement_demand=engagement_demand,
        post_outcome=post_outcome,
    )
    next_step_path = latest_next_step(args.date)
    next_step = (
        read_date_bound_json(next_step_path, args.date, label="next_generation_step")
        if next_step_path
        else {}
    )
    recommendation = next_step.get("recommendation", {})
    proof_lane_lock = {
        "action_type": recommendation.get("action_type", ""),
        "recipe_id": recommendation.get("recommended_recipe_id", ""),
        "outfit_id": recommendation.get("recommended_outfit_id", ""),
        "environment_id": recommendation.get("recommended_environment_id", ""),
        "next_live_gate": recommendation.get("next_live_gate", ""),
    }
    proof_lane_lock_active = should_apply_proof_lane_lock(audit, proof_lane_lock)
    queue = (
        apply_proof_lane_lock(queue_full, proof_lane_lock)
        if proof_lane_lock_active
        else queue_full
    )[:args.limit]
    rotation_preview = build_rotation_preview(
        audit,
        args.date,
        world_state=world_state,
        engagement_demand=engagement_demand,
        post_outcome=post_outcome,
        exclude_recipe_id=proof_lane_lock["recipe_id"] if proof_lane_lock_active else "",
        exclude_outfit_id=proof_lane_lock["outfit_id"] if proof_lane_lock_active else "",
        limit=4,
    )

    report = {
        "report_type": "lena_autonomous_generation_queue_dryrun",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "source_readiness_audit": str(audit_path),
        "broader_autonomous_generation_ready": audit["memory_progress"].get(
            "broader_autonomous_generation_ready", False
        ),
        "autonomous_publishing_unlocked": audit["memory_progress"].get(
            "autonomous_publishing_unlocked", False
        ),
        "proof_lane_lock": proof_lane_lock,
        "proof_lane_lock_active": proof_lane_lock_active,
        "queue_policy": {
            "default_order_source": "recipe bank controlled proof lane + proof_priority + readiness score + world-state continuity pressure + engagement demand pressure + post outcome pressure",
            "rotation_preview_prefers_non_proof_mode": True,
            "proof_lane_lock_suppressed_when_broader_ready": True,
        },
        "source_world_state": str(world_state_path) if world_state_path else "",
        "source_engagement_demand": str(engagement_demand_path) if engagement_demand_path else "",
        "source_post_outcome": str(post_outcome_path) if post_outcome_path else "",
        "rotation_guardrail": (
            "A locked proof lane is a temporary realism-debug lane, not the broader wardrobe "
            "rotation. Once broader autonomous generation is ready, queue order should reopen outfit/"
            "environment spread instead of force-pinning the proof lane."
        ),
        "queue_slots": queue,
        "post_proof_rotation_preview": rotation_preview,
        "memory_progress": audit["memory_progress"],
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
    }

    output_path = save_report(report, args.date)
    print(
        json.dumps(
            {
                "ok": True,
                "output_path": str(output_path),
                "broader_autonomous_generation_ready": report["broader_autonomous_generation_ready"],
                "autonomous_publishing_unlocked": report["autonomous_publishing_unlocked"],
                "queue_recipes": [row["recipe_id"] for row in queue],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
