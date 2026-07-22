from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits  # noqa: E402
RECIPE_BANK = (
    ROOT / "pipeline" / "prompt_banks" / "lena"
    / "lena_high_caliber_prompt_recipe_bank_v1.json"
)
MEMORY_POLICY = (
    ROOT / "pipeline" / "influencer_nodes" / "lena"
    / "life_engine_realism_memory_policy_v1.json"
)
GATE_POLICY = (
    ROOT / "pipeline" / "influencer_nodes" / "lena"
    / "strategy_autonomy_gate_policy_v1.json"
)
PACKET_BASE = ROOT / "pipeline" / "strategy" / "lena" / "content_packets"
OUTPUT_BASE = ROOT / "pipeline" / "strategy" / "lena" / "next_actions"

WIN_STATUSES = {
    "approved",
    "publishable",
    "publishable_quality",
    "strong_candidate_needs_skin_realism_review",
}
FACE_SKIN_POSITIVE_MARKERS = (
    "face/skin realism crossed into believable territory",
    "face reads believable",
    "believable face-skin realism",
    "face/skin realism crossed into believable territory and should be preserved",
)
FACE_SKIN_NEGATIVE_MARKERS = (
    "too polished",
    "fake freckle",
    "speckling",
    "airbrushed",
    "plastic",
)
# Compatibility aliases; authority lives in lena_provider_prompt_limits_v1.
PAYLOAD_HEADROOM_HARD_BLOCK_BELOW = (
    prompt_limits.RETRY_PROMPT_HEADROOM_HARD_BLOCK_BELOW
)
PAYLOAD_HEADROOM_WARNING_BELOW = (
    prompt_limits.RETRY_PROMPT_HEADROOM_WARNING_BELOW
)


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_recipes() -> tuple[dict, dict]:
    data = read_json(RECIPE_BANK)
    lookup = {recipe["id"]: recipe for recipe in data.get("recipes", [])}
    return data, lookup


def default_priority_recipes() -> list[str]:
    data, _ = load_recipes()
    active = [
        recipe for recipe in data.get("recipes", [])
        if recipe.get("production_status") != "test_only"
    ]
    active.sort(
        key=lambda recipe: (
            not recipe.get("controlled_proof_lane", False),
            recipe.get("proof_priority") is None,
            recipe.get("proof_priority", 999),
            recipe.get("id", ""),
        )
    )
    return [recipe["id"] for recipe in active]


def count_face_skin_wins(entries: list[dict]) -> int:
    count = 0
    for entry in entries:
        notes = " ".join(entry.get("skin_face_realism_notes", [])).lower()
        if any(marker in notes for marker in FACE_SKIN_POSITIVE_MARKERS):
            count += 1
            continue
        if entry.get("qa_status") not in WIN_STATUSES:
            continue
        if any(marker in notes for marker in FACE_SKIN_NEGATIVE_MARKERS):
            continue
        if entry.get("qa_status") in {"approved", "publishable", "publishable_quality"}:
            count += 1
    return count


def count_garment_wins(entries: list[dict]) -> int:
    count = 0
    for entry in entries:
        if entry.get("qa_status") not in WIN_STATUSES:
            continue
        notes = " ".join(entry.get("wardrobe_construction_notes", [])).lower()
        if "single garment" in notes or "dress continuity held" in notes:
            count += 1
    return count


def latest_artifact(base: Path, prefix: str, recipe_id: str, date: str) -> Path | None:
    dated = base / date / f"{prefix}_{date}_{recipe_id}.json"
    if dated.is_file():
        return dated
    candidates = sorted(base.glob(f"*/{prefix}_*_{recipe_id}.json"))
    return candidates[-1] if candidates else None


def grade_lane(row: dict) -> tuple[str, list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if not row["recipe_present"]:
        blockers.append("recipe_missing")
    if not row["scene_logic_contract_in_recipe"]:
        blockers.append("recipe_scene_contract_missing")
    if not row["packet_present"]:
        blockers.append("packet_missing")
    if not row["payload_present"]:
        blockers.append("payload_missing")
    if row["payload_present"] and not row["payload_scene_contract_present"]:
        blockers.append("payload_scene_contract_missing")
    if row["payload_present"] and not row["master_identity_body_present"]:
        blockers.append("master_identity_missing")
    if row["payload_present"] and not row["blocked_terms_absent"]:
        blockers.append("blocked_terms_present")
    if row["payload_present"] and row["payload_headroom"] < PAYLOAD_HEADROOM_HARD_BLOCK_BELOW:
        blockers.append("payload_headroom_too_low")

    if row["payload_present"] and row["style_source"] == "style_bank":
        warnings.append("style_bank_randomized_wardrobe")
    if row["payload_present"] and not row["environment_controlled"]:
        warnings.append("environment_not_recipe_locked")
    if row["payload_present"] and row["payload_headroom"] < PAYLOAD_HEADROOM_WARNING_BELOW:
        warnings.append("payload_headroom_narrow")

    if blockers:
        return "blocked", blockers + warnings
    if warnings:
        return "ready_with_warnings", warnings
    return "ready", []


def audit_lane(recipe_id: str, recipes: dict, date: str) -> dict:
    recipe = recipes.get(recipe_id)
    packet_path = latest_artifact(
        PACKET_BASE, "lena_content_packet_dryrun", recipe_id, date
    )
    packet = read_json(packet_path) if packet_path else {}
    provider_prompt_contract = packet.get("provider_prompt_contract", {})

    payload_chars = provider_prompt_contract.get(
        "prompt_chars",
        packet.get("compact_provider_prompt_chars", packet.get("compact_kling_prompt_chars")),
    )
    packet_chars = packet.get(
        "compact_provider_prompt_chars",
        packet.get("compact_kling_prompt_chars"),
    )
    proof_mode = packet.get("production_proof_mode", False)
    outfit_used = packet.get("wardrobe_outfit_id")
    env_used = packet.get("environment_id")
    style_source = "catalog_v1" if outfit_used else "style_bank"

    row = {
        "recipe_id": recipe_id,
        "recipe_present": recipe is not None,
        "title": recipe.get("title", "") if recipe else "",
        "scene_type": recipe.get("scene_type", "") if recipe else "",
        "content_pillar": recipe.get("content_pillar", "") if recipe else "",
        "scene_logic_contract_in_recipe": bool(recipe and recipe.get("scene_logic_contract")),
        "packet_present": packet_path is not None,
        "packet_path": str(packet_path) if packet_path else "",
        "packet_compact_chars": packet_chars,
        "packet_compact_headroom": (
            prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
            - packet_chars
            if isinstance(packet_chars, int)
            else None
        ),
        "payload_present": bool(packet_path and provider_prompt_contract),
        "payload_path": str(packet_path) if packet_path else "",
        "payload_chars": payload_chars,
        "payload_headroom": provider_prompt_contract.get(
            "prompt_headroom",
            (
                prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
                - payload_chars
                if isinstance(payload_chars, int)
                else None
            ),
        ),
        "payload_scene_contract_present": provider_prompt_contract.get("scene_logic_contract_present", False),
        "master_identity_body_present": provider_prompt_contract.get("master_identity_body_present", False),
        "blocked_terms_absent": provider_prompt_contract.get("blocked_terms_absent", False),
        "proof_mode": proof_mode,
        "style_source": style_source,
        "style_lane": packet.get("content_pillar", ""),
        "outfit_controlled": bool(outfit_used),
        "environment_controlled": bool(env_used),
        "outfit_used": outfit_used,
        "environment_used": env_used,
        "provider_prompt_surface_status": provider_prompt_contract.get("surface_status", ""),
    }

    grade, reasons = grade_lane(row)
    row["autonomy_grade"] = grade
    row["autonomy_reasons"] = reasons
    return row


def build_memory_progress() -> dict:
    policy = read_json(MEMORY_POLICY)
    state = read_json(ROOT / policy["memory_path"])
    entries = state.get("entries", [])
    wins = [e for e in entries if e.get("qa_status") in WIN_STATUSES]
    progress = {
        "wins_logged": len(wins),
        "face_skin_wins_logged": count_face_skin_wins(entries),
        "garment_stability_wins_logged": count_garment_wins(entries),
        "memory_entries_logged": len(entries),
        "required_before_broader_autonomous_generation": policy.get("autonomy_gate", {}).get(
            "required_before_broader_autonomous_generation", []
        ),
        "autonomous_publishing_unlocked": policy.get("autonomy_gate", {}).get(
            "autonomous_publishing_unlocked", False
        ),
    }
    progress["broader_autonomous_generation_ready"] = (
        progress["wins_logged"] >= 3
        and progress["face_skin_wins_logged"] >= 2
        and progress["garment_stability_wins_logged"] >= 2
        and progress["memory_entries_logged"] >= 4
    )
    return progress


def build_strategy_gate_status(lanes: list[dict], memory_progress: dict) -> dict:
    gate_policy = read_json(GATE_POLICY)
    critical_blockers = set(gate_policy.get("critical_blocker_reasons", []))
    critical_warnings = set(gate_policy.get("critical_warning_reasons", []))

    blocker_hits = []
    warning_hits = []
    blocked_lanes = []

    for lane in lanes:
        reasons = lane.get("autonomy_reasons", [])
        lane_hits = [reason for reason in reasons if reason in critical_blockers]
        warning_lane_hits = [reason for reason in reasons if reason in critical_warnings]
        if lane_hits:
            blocked_lanes.append(lane["recipe_id"])
            blocker_hits.append(
                {
                    "recipe_id": lane["recipe_id"],
                    "title": lane.get("title", ""),
                    "reasons": lane_hits,
                }
            )
        if warning_lane_hits:
            warning_hits.append(
                {
                    "recipe_id": lane["recipe_id"],
                    "title": lane.get("title", ""),
                    "reasons": warning_lane_hits,
                }
            )

    require_all_ready = gate_policy.get("require_all_priority_lanes_ready", True)
    all_lanes_ready = all(lane.get("autonomy_grade") == "ready" for lane in lanes)
    blocked = (
        not memory_progress.get("broader_autonomous_generation_ready", False)
        or bool(blocker_hits)
        or (require_all_ready and not all_lanes_ready)
    )

    block_reasons = []
    if not memory_progress.get("broader_autonomous_generation_ready", False):
        block_reasons.append("aggregate_readiness_below_threshold")
    if blocker_hits:
        block_reasons.append("critical_lane_failures_present")
    if require_all_ready and not all_lanes_ready:
        block_reasons.append("not_all_priority_lanes_ready")

    return {
        "policy_path": str(GATE_POLICY),
        "require_all_priority_lanes_ready": require_all_ready,
        "aggregate_readiness_met": memory_progress.get(
            "broader_autonomous_generation_ready", False
        ),
        "all_priority_lanes_ready": all_lanes_ready,
        "blocked": blocked,
        "block_reasons": block_reasons,
        "critical_blocker_hits": blocker_hits,
        "critical_warning_hits": warning_hits,
        "blocked_lane_ids": blocked_lanes,
    }


def build_report(date: str, recipe_ids: list[str]) -> dict:
    _, recipes = load_recipes()
    lanes = [audit_lane(recipe_id, recipes, date) for recipe_id in recipe_ids]
    status_counts = Counter(row["autonomy_grade"] for row in lanes)
    ready = [row["recipe_id"] for row in lanes if row["autonomy_grade"] == "ready"]
    ready_warn = [
        row["recipe_id"] for row in lanes if row["autonomy_grade"] == "ready_with_warnings"
    ]
    blocked = [row["recipe_id"] for row in lanes if row["autonomy_grade"] == "blocked"]
    memory_progress = build_memory_progress()
    strategy_gate = build_strategy_gate_status(lanes, memory_progress)

    return {
        "report_type": "lena_autonomous_generation_readiness_audit",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "priority_recipes": recipe_ids,
        "lane_status_counts": dict(status_counts),
        "lanes_ready": ready,
        "lanes_ready_with_warnings": ready_warn,
        "lanes_blocked": blocked,
        "memory_progress": memory_progress,
        "strategy_gate": strategy_gate,
        "lanes": lanes,
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
    }


def save_report(report: dict, date: str) -> Path:
    out_dir = OUTPUT_BASE / date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lena_autonomous_generation_readiness_audit_{date}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Lena priority lanes for autonomous generation readiness."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for lane artifact lookup")
    parser.add_argument(
        "--recipes",
        nargs="*",
        default=None,
        help=(
            "Priority recipe ids to audit (defaults to all active recipes ordered by "
            "controlled proof lane, then proof_priority)"
        ),
    )
    args = parser.parse_args()

    recipe_ids = args.recipes or default_priority_recipes()
    report = build_report(args.date, recipe_ids)
    output_path = save_report(report, args.date)
    print(
        json.dumps(
            {
                "ok": True,
                "output_path": str(output_path),
                "lane_status_counts": report["lane_status_counts"],
                "lanes_ready": report["lanes_ready"],
                "lanes_ready_with_warnings": report["lanes_ready_with_warnings"],
                "lanes_blocked": report["lanes_blocked"],
                "memory_progress": report["memory_progress"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
