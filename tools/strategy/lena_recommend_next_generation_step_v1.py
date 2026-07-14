from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
POLICY = NODE / "life_engine_realism_memory_policy_v1.json"
RECIPE_BANK = (
    ROOT / "pipeline" / "prompt_banks" / "lena"
    / "lena_high_caliber_prompt_recipe_bank_v1.json"
)
WORLD_STATE = ROOT / "pipeline" / "state" / "lena_world_state_v1.json"
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
LEARNING_STATUSES = {
    "current",
    "usable_but_incomplete",
    "stale_unresolved",
    "manual_or_future_capability_required",
}
LEARNING_FOLLOW_UPS = {
    "current": "no_follow_up_required",
    "usable_but_incomplete": "complete_missing_metrics_or_refresh_learning",
    "stale_unresolved": "refresh_or_resolve_stale_unresolved_posts",
    "manual_or_future_capability_required": "manual_or_future_capability_resolution_required",
    "unavailable": "rebuild_and_pass_an_explicit_learning_artifact",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_recipe_bank() -> list[dict]:
    if not RECIPE_BANK.is_file():
        return []
    try:
        data = read_json(RECIPE_BANK)
    except Exception:
        return []
    return data.get("recipes", [])


def recipe_exists(recipe_id: str) -> bool:
    if not RECIPE_BANK.is_file():
        return False
    return any(r.get("id") == recipe_id for r in load_recipe_bank())


def get_recipe(recipe_id: str) -> dict | None:
    return next(
        (recipe for recipe in load_recipe_bank() if recipe.get("id") == recipe_id),
        None,
    )


def face_priority_proof_sequence() -> list[str]:
    recipes = load_recipe_bank()
    filtered = [
        recipe for recipe in recipes
        if recipe.get("production_status") != "test_only"
        and recipe.get("production_proof_mode", False)
        and recipe.get("content_pillar") == "face_priority_getting_ready"
    ]
    filtered.sort(
        key=lambda recipe: (
            recipe.get("proof_priority") is None,
            recipe.get("proof_priority", 999),
            recipe.get("id", ""),
        )
    )
    return [recipe.get("id", "") for recipe in filtered if recipe.get("id")]


def select_next_face_proof_lane(current_recipe_id: str) -> tuple[str, str, str]:
    available = face_priority_proof_sequence()
    if not available:
        return "", "", ""

    if current_recipe_id in available and len(available) > 1:
        current_index = available.index(current_recipe_id)
        selected_recipe_id = available[(current_index + 1) % len(available)]
    else:
        selected_recipe_id = available[0]

    recipe = get_recipe(selected_recipe_id) or {}
    return (
        selected_recipe_id,
        recipe.get("wardrobe_outfit_id", ""),
        recipe.get("environment_id", ""),
    )


def latest(entries: list[dict], *, predicate) -> dict | None:
    filtered = [e for e in entries if predicate(e)]
    if not filtered:
        return None
    filtered.sort(key=lambda e: (e.get("date", ""), e.get("logged_at", "")))
    return filtered[-1]


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


def build_autonomy_progress(policy: dict, entries: list[dict]) -> dict:
    wins = [
        e for e in entries
        if e.get("qa_status") in WIN_STATUSES
    ]
    garment_wins = [
        e for e in wins
        if any(
            "single garment" in note.lower()
            or "dress continuity held" in note.lower()
            for note in e.get("wardrobe_construction_notes", [])
        )
    ]
    gate = policy.get("autonomy_gate", {})
    broader_ready = (
        len(wins) >= 3
        and count_face_skin_wins(entries) >= 2
        and len(garment_wins) >= 2
        and len(entries) >= 4
    )
    return {
        "wins_logged": len(wins),
        "face_skin_wins_logged": count_face_skin_wins(entries),
        "garment_stability_wins_logged": len(garment_wins),
        "memory_entries_logged": len(entries),
        "required_before_broader_autonomous_generation": gate.get(
            "required_before_broader_autonomous_generation", []
        ),
        "autonomous_publishing_unlocked": gate.get(
            "autonomous_publishing_unlocked", False
        ),
        "broader_autonomous_generation_ready": broader_ready,
    }


def _normalized_learning_status(raw_status: str) -> str:
    status = str(raw_status or "").strip()
    if status in LEARNING_STATUSES:
        return status
    return "unavailable"


def _learning_follow_up_action(status: str) -> str:
    return LEARNING_FOLLOW_UPS.get(status, LEARNING_FOLLOW_UPS["unavailable"])


def load_learning_context(learning_artifact_path: str, expected_date: str) -> dict:
    path_text = str(learning_artifact_path or "").strip()
    unavailable = {
        "learning_artifact_path": path_text,
        "learning_artifact_valid": False,
        "learning_availability": "unavailable",
        "learning_status": "unavailable",
        "learning_status_label": "learning_unavailable",
        "learning_validation_state": "not_provided" if not path_text else "invalid",
        "learning_validation_error": (
            "learning_artifact_path_not_provided" if not path_text else "learning_artifact_unavailable"
        ),
        "learning_artifact_date": "",
        "learning_published_post_count": 0,
        "learning_pending_metrics_count": 0,
        "learning_stale_pending_metrics_count": 0,
        "learning_resolution_state_summary": {},
        "learning_required_follow_up_action": _learning_follow_up_action("unavailable"),
        "learning_preferred_recipe_ids": [],
        "learning_winner_post_count": 0,
    }
    if not path_text:
        return unavailable

    path = Path(path_text)
    if not path.is_file():
        return unavailable

    try:
        report = read_json(path)
    except Exception:
        unavailable["learning_validation_state"] = "unreadable"
        unavailable["learning_validation_error"] = "learning_artifact_unreadable"
        return unavailable

    if report.get("report_type") != "lena_post_outcome_learning_state":
        unavailable["learning_validation_state"] = "wrong_report_type"
        unavailable["learning_validation_error"] = "learning_artifact_wrong_report_type"
        return unavailable

    report_date = str(report.get("date", "")).strip()
    if expected_date and report_date and report_date != expected_date:
        unavailable["learning_validation_state"] = "date_mismatch"
        unavailable["learning_validation_error"] = "learning_artifact_date_mismatch"
        unavailable["learning_artifact_date"] = report_date
        return unavailable

    summary = report.get("metrics_resolution_summary")
    if not isinstance(summary, dict):
        unavailable["learning_validation_state"] = "missing_summary"
        unavailable["learning_validation_error"] = "learning_artifact_missing_metrics_resolution_summary"
        return unavailable

    status = _normalized_learning_status(summary.get("learning_status"))
    preferred_recipe_ids = [
        recipe_id
        for recipe_id in report.get("queue_boosts", {}).get("preferred_recipe_ids", [])
        if isinstance(recipe_id, str) and recipe_id.strip()
    ]
    return {
        "learning_artifact_path": str(path),
        "learning_artifact_valid": True,
        "learning_artifact_date": report_date or expected_date,
        "learning_availability": "available",
        "learning_status": status,
        "learning_status_label": {
            "current": "learning_current",
            "usable_but_incomplete": "learning_degraded_incomplete",
            "stale_unresolved": "learning_stale_unresolved",
            "manual_or_future_capability_required": "learning_manual_or_future_capability_required",
        }.get(status, "learning_unavailable"),
        "learning_validation_state": "valid",
        "learning_validation_error": "",
        "learning_published_post_count": int(report.get("published_post_count", 0) or 0),
        "learning_pending_metrics_count": len(report.get("pending_metrics_posts", [])),
        "learning_stale_pending_metrics_count": len(report.get("stale_pending_metrics_posts", [])),
        "learning_resolution_state_summary": summary,
        "learning_required_follow_up_action": _learning_follow_up_action(status),
        "learning_preferred_recipe_ids": preferred_recipe_ids,
        "learning_winner_post_count": len(report.get("winner_posts", [])),
    }


def apply_learning_signal(base_recommendation: dict, learning_context: dict) -> dict:
    recommendation = dict(base_recommendation)
    preferred = [
        recipe_id
        for recipe_id in learning_context.get("learning_preferred_recipe_ids", [])
        if recipe_exists(recipe_id)
    ]
    recommendation["learning_preferred_recipe_ids"] = preferred
    signal_used: list[str] = []
    if preferred:
        signal_used.append("queue_boosts.preferred_recipe_ids")
    if learning_context.get("learning_winner_post_count", 0):
        signal_used.append("winner_posts")
    if preferred and not str(recommendation.get("recommended_recipe_id", "")).strip():
        recommendation["recommended_recipe_id"] = preferred[0]
        signal_used.append("recommended_recipe_id_fallback")
    recommendation["learning_signal_used"] = signal_used
    return recommendation


def finalize_recommendation(recommendation: dict, learning_context: dict) -> dict:
    final = apply_learning_signal(recommendation, learning_context)
    if learning_context.get("learning_artifact_valid", False):
        final["learning_artifact_path"] = learning_context.get("learning_artifact_path", "")
        final["learning_artifact_valid"] = True
        final["learning_availability"] = learning_context.get("learning_availability", "available")
        final["learning_status"] = learning_context.get("learning_status", "unavailable")
        final["learning_status_label"] = learning_context.get("learning_status_label", "learning_unavailable")
        final["learning_validation_state"] = learning_context.get("learning_validation_state", "valid")
        final["learning_validation_error"] = learning_context.get("learning_validation_error", "")
        final["learning_artifact_date"] = learning_context.get("learning_artifact_date", "")
        final["learning_published_post_count"] = learning_context.get("learning_published_post_count", 0)
        final["learning_pending_metrics_count"] = learning_context.get("learning_pending_metrics_count", 0)
        final["learning_stale_pending_metrics_count"] = learning_context.get("learning_stale_pending_metrics_count", 0)
        final["learning_resolution_state_summary"] = learning_context.get("learning_resolution_state_summary", {})
        final["learning_required_follow_up_action"] = learning_context.get("learning_required_follow_up_action", "")
        final["learning_winner_post_count"] = learning_context.get("learning_winner_post_count", 0)
        final.setdefault("rationale", [])
        final["rationale"] = [
            f"Outcome learning is {final['learning_status'].replace('_', ' ')}."
        ] + (
            [f"Learning signal used: {', '.join(final['learning_signal_used'])}"]
            if final.get("learning_signal_used")
            else ["Learning is available but did not alter the selected recipe."]
        ) + list(final["rationale"])
    else:
        final["learning_artifact_path"] = learning_context.get("learning_artifact_path", "")
        final["learning_artifact_valid"] = False
        final["learning_availability"] = "unavailable"
        final["learning_status"] = "unavailable"
        final["learning_status_label"] = "learning_unavailable"
        final["learning_validation_state"] = learning_context.get("learning_validation_state", "invalid")
        final["learning_validation_error"] = learning_context.get("learning_validation_error", "learning_artifact_unavailable")
        final["learning_artifact_date"] = learning_context.get("learning_artifact_date", "")
        final["learning_published_post_count"] = 0
        final["learning_pending_metrics_count"] = 0
        final["learning_stale_pending_metrics_count"] = 0
        final["learning_resolution_state_summary"] = {}
        final["learning_required_follow_up_action"] = learning_context.get(
            "learning_required_follow_up_action",
            _learning_follow_up_action("unavailable"),
        )
        final["learning_winner_post_count"] = 0
        final["learning_signal_used"] = []
        final.setdefault("rationale", [])
        final["rationale"] = [
            "Outcome learning is unavailable for this recommendation."
        ] + list(final["rationale"])
    return final


def build_recommendation(
    policy: dict,
    entries: list[dict],
    world_state: dict | None = None,
    learning_context: dict | None = None,
) -> dict:
    progress = build_autonomy_progress(policy, entries)
    continuity_alerts = [
        str(item).lower() for item in (world_state or {}).get("continuity_alerts", [])
    ]
    preferred_rotation = [
        recipe_id
        for recipe_id in (world_state or {}).get("preferred_rotation_recipe_ids", [])
        if recipe_exists(recipe_id)
    ]
    blocked_recipe_ids = set((world_state or {}).get("blocked_recipe_ids", []))
    latest_reviewed_recipe_id = str((world_state or {}).get("latest_reviewed_recipe_id", "")).strip()
    learning_context = learning_context or load_learning_context("", "")

    if (
        progress.get("broader_autonomous_generation_ready", False)
        and preferred_rotation
        and latest_reviewed_recipe_id in blocked_recipe_ids
        and any("proof-mode lanes are crowding" in alert for alert in continuity_alerts)
    ):
        recipe_id = preferred_rotation[0]
        recipe = get_recipe(recipe_id) or {}
        outfit_id = recipe.get("wardrobe_outfit_id", "")
        environment_id = recipe.get("environment_id", "")
        status_counts = Counter(e.get("qa_status", "unknown") for e in entries)
        return finalize_recommendation({
            "action_type": "broader_rotation_resume",
            "status_counts": dict(status_counts),
            "recommended_recipe_id": recipe_id,
            "recommended_outfit_id": outfit_id,
            "recommended_environment_id": environment_id,
            "rationale": [
                "Broader autonomous generation is now ready from a realism-memory standpoint.",
                "Recent continuity state says proof-mode home lanes are overrepresented and should stop dominating the next move.",
                "The next efficient step is to carry the current realism standard into a broader public-world or fitness lane instead of spending another cycle on mirror-proof repetition.",
            ],
            "hold_constant_next": [
                "reference-true face and body proportions",
                "reference-true warm medium-brown hair with honey/caramel highlights",
                "visible pores and believable skin texture",
                "real-world environment logic and non-sterile scene detail",
            ],
            "refine_only_next": [
                "outfit and environment rotation",
                "public-world or lifestyle variety",
                "social-account believability across more of Lena's life",
                "same quality bar with broader scene coverage",
            ],
            "avoid_repeating": [
                "another home-coded mirror proof as the default next move",
                "proof-lane crowding in the recent memory window",
                "same-room repetition when broader variety is ready",
            ],
            "recommended_packet_command": (
                "python tools/strategy/lena_build_content_packet_dryrun_v1.py "
                f"--recipe {recipe_id} --date {utc_date()}"
            ),
            "recommended_payload_command": (
                "python tools/strategy/lena_build_kling_payload_dryrun_v1.py "
                f"--recipe {recipe_id} --date {utc_date()}"
            ),
            "next_live_gate": (
                "Ready to widen into the next non-proof rotation lane after Nicolas reviews the packet and payload."
            ),
        }, learning_context)

    latest_skin_iteration = latest(
        entries,
        predicate=lambda e: e.get("qa_status") == "strong_candidate_needs_skin_realism_review",
    )
    latest_reject = latest(
        entries,
        predicate=lambda e: e.get("qa_status") == "rejected",
    )

    if latest_skin_iteration:
        latest_same_lane_reject = latest(
            entries,
            predicate=lambda e: (
                e.get("qa_status") == "rejected"
                and e.get("outfit_id") == latest_skin_iteration.get("outfit_id")
                and e.get("environment_id") == latest_skin_iteration.get("environment_id")
            ),
        )
        latest_same_lane_notes = " ".join(
            (latest_same_lane_reject or {}).get("skin_face_realism_notes", [])
            + (latest_same_lane_reject or {}).get("body_proportion_notes", [])
        ).lower()
        if "believable territory" in latest_same_lane_notes:
            action_type = "anatomy_pose_repair_iteration"
            recipe_id = latest_skin_iteration.get("recipe_id")
            outfit_id = latest_skin_iteration.get("outfit_id")
            environment_id = latest_skin_iteration.get("environment_id")
            rationale = [
                "Face/skin realism has now crossed into believable territory in the latest reviewed run.",
                "The primary blocker is anatomy and pose stability, especially arm/hand integrity.",
                "The next move is to preserve the current face stack and simplify the pose/composition so anatomy has less room to fail."
            ]
            hold_constant = [
                "current face/skin prompt stack",
                "identity and facial likeness",
                f"apartment/home realism anchored by {environment_id}",
                "soft window plus warm lamp lighting",
            ]
            refine_only = [
                "both arms visible and anatomically complete",
                "one simple hand action only",
                "reduced lower-body exaggeration",
                "wardrobe fidelity back to the intended outfit lane",
            ]
            avoid_repeating = list(
                dict.fromkeys(
                    latest_skin_iteration.get("prompt_clues_that_hurt", [])
                    + ((latest_same_lane_reject or {}).get("prompt_clues_that_hurt", []))
                )
            )
            recommended_packet_cmd = ""
            recommended_payload_cmd = ""
            next_live_gate = (
                "Do not spend another run until the next packet explicitly simplifies pose/anatomy and preserves the current face stack."
            )
            status_counts = Counter(e.get("qa_status", "unknown") for e in entries)
            return finalize_recommendation({
                "action_type": action_type,
                "status_counts": dict(status_counts),
                "recommended_recipe_id": recipe_id,
                "recommended_outfit_id": outfit_id,
                "recommended_environment_id": environment_id,
                "rationale": rationale,
                "hold_constant_next": hold_constant,
                "refine_only_next": refine_only,
                "avoid_repeating": avoid_repeating,
                "recommended_packet_command": recommended_packet_cmd,
                "recommended_payload_command": recommended_payload_cmd,
                "next_live_gate": next_live_gate,
            }, learning_context)

        same_lane_rejects = [
            e for e in entries
            if e.get("qa_status") == "rejected"
            and e.get("outfit_id") == latest_skin_iteration.get("outfit_id")
            and e.get("environment_id") == latest_skin_iteration.get("environment_id")
            and e.get("date", "") >= latest_skin_iteration.get("date", "")
        ]
        if len(same_lane_rejects) >= 2:
            action_type = "face_priority_skin_realism_proof_lane"
            recipe_id, outfit_id, environment_id = select_next_face_proof_lane(
                latest_skin_iteration.get("recipe_id", "")
            )
            rationale = [
                "The same full-body mirror lane has now produced repeated rejects after the earlier strong candidate.",
                "Kling keeps trading realism for glam drift, body exaggeration, or wardrobe/composition drift in this lane.",
                "The next efficient move is a simpler face-priority proof shot that isolates skin realism and hand stability without overfitting to the same exact look."
            ]
            hold_constant = [
                "identity and face",
                "home-coded getting-ready realism",
                "soft window plus warm lamp lighting",
                "candid non-studio tone",
            ]
            refine_only = [
                "visible pores and fine facial texture without fake freckles",
                "natural under-eye and lip texture",
                "simple clean one-hand pose or cropped hands",
                "reduced body exaggeration by using waist-up or three-quarter framing",
                "non-red wardrobe continuity option if the current proof lane is visually overused",
            ]
            avoid_repeating = list(
                dict.fromkeys(
                    latest_skin_iteration.get("prompt_clues_that_hurt", [])
                    + [hint for e in same_lane_rejects for hint in e.get("prompt_clues_that_hurt", [])]
                )
            )
            if recipe_id:
                recommended_packet_cmd = (
                    "python tools/strategy/lena_build_content_packet_dryrun_v1.py "
                    f"--recipe {recipe_id} --date {utc_date()}"
                )
                recommended_payload_cmd = (
                    "python tools/strategy/lena_build_kling_payload_dryrun_v1.py "
                    f"--recipe {recipe_id} --date {utc_date()}"
                )
            else:
                recommended_packet_cmd = ""
                recommended_payload_cmd = ""
            next_live_gate = (
                "Do not spend another full-body mirror test before creating a simpler face-priority proof lane."
            )
            status_counts = Counter(e.get("qa_status", "unknown") for e in entries)
            return finalize_recommendation({
                "action_type": action_type,
                "status_counts": dict(status_counts),
                "recommended_recipe_id": recipe_id,
                "recommended_outfit_id": outfit_id,
                "recommended_environment_id": environment_id,
                "rationale": rationale,
                "hold_constant_next": hold_constant,
                "refine_only_next": refine_only,
                "avoid_repeating": avoid_repeating,
                "recommended_packet_command": recommended_packet_cmd,
                "recommended_payload_command": recommended_payload_cmd,
                "next_live_gate": next_live_gate,
            }, learning_context)

        action_type = "locked_lane_skin_realism_iteration"
        recipe_id = latest_skin_iteration.get("recipe_id")
        outfit_id = latest_skin_iteration.get("outfit_id")
        environment_id = latest_skin_iteration.get("environment_id")
        rationale = [
            "Body, garment continuity, and environment already proved out in this lane.",
            "Life-engine memory says face/skin realism is the only remaining gap.",
            "Changing outfit or environment now would throw away the strongest controlled test."
        ]
        hold_constant = [
            "identity and body proportions",
            f"recipe {recipe_id}",
            f"outfit {outfit_id}",
            f"environment {environment_id}",
            "mirror/apartment composition",
            "phone-camera candid tone",
        ]
        refine_only = [
            "visible pores and fine facial texture",
            "slight under-eye and lower-lid realism",
            "imperfect lip texture",
            "flyaway hair strands and brow/lash separation",
            "uneven natural catchlights and room-shadow falloff",
        ]
        avoid_repeating = list(
            dict.fromkeys(
                latest_skin_iteration.get("prompt_clues_that_hurt", [])
                + (latest_reject.get("prompt_clues_that_hurt", []) if latest_reject else [])
            )
        )
        recommended_packet_cmd = (
            "python tools/strategy/lena_build_content_packet_dryrun_v1.py "
            f"--recipe {recipe_id} --outfit-id {outfit_id} --env-id {environment_id} --date {utc_date()}"
        )
        recommended_payload_cmd = (
            "python tools/strategy/lena_build_kling_payload_dryrun_v1.py "
            f"--recipe {recipe_id} --date {utc_date()}"
        )
        next_live_gate = (
            "Ready for one controlled live Kling generation only after Nicolas approves "
            "this exact locked lane packet/payload review."
        )
    else:
        action_type = "collect_first_controlled_proof"
        recipe_id = outfit_id = environment_id = ""
        rationale = [
            "No strong candidate lane is logged yet.",
            "Need one believable real-account proof before autonomous selection can narrow variables."
        ]
        hold_constant = []
        refine_only = []
        avoid_repeating = []
        recommended_packet_cmd = ""
        recommended_payload_cmd = ""
        next_live_gate = "Not ready for live generation recommendation yet."

    status_counts = Counter(e.get("qa_status", "unknown") for e in entries)
    return finalize_recommendation({
        "action_type": action_type,
        "status_counts": dict(status_counts),
        "recommended_recipe_id": recipe_id,
        "recommended_outfit_id": outfit_id,
        "recommended_environment_id": environment_id,
        "rationale": rationale,
        "hold_constant_next": hold_constant,
        "refine_only_next": refine_only,
        "avoid_repeating": avoid_repeating,
        "recommended_packet_command": recommended_packet_cmd,
        "recommended_payload_command": recommended_payload_cmd,
        "next_live_gate": next_live_gate,
    }, learning_context)


def save_report(report: dict, date_str: str) -> Path:
    out_dir = OUTPUT_BASE / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"lena_next_generation_step_{date_str}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recommend the next controlled Lena generation step from realism memory."
    )
    parser.add_argument("--date", default=utc_date(), help="UTC date for output folder")
    parser.add_argument(
        "--learning-artifact-path",
        default="",
        help="Exact post-outcome learning artifact to use for this recommendation.",
    )
    args = parser.parse_args()

    policy = read_json(POLICY)
    memory_path = ROOT / policy["memory_path"]
    if not memory_path.is_file():
        raise SystemExit(f"[ABORT] realism memory not found: {memory_path}")

    state = read_json(memory_path)
    entries = state.get("entries", [])
    if not entries:
        raise SystemExit("[ABORT] realism memory has no entries yet")

    world_state = read_json(WORLD_STATE) if WORLD_STATE.is_file() else {}
    learning_context = load_learning_context(args.learning_artifact_path, args.date)
    recommendation = build_recommendation(policy, entries, world_state, learning_context)
    progress = build_autonomy_progress(policy, entries)
    report = {
        "report_type": "lena_next_generation_step",
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dry_run": True,
        "provider_call_enabled": False,
        "generation_call_performed": False,
        "api_call_made": False,
        "publishing_approval": "not_approved",
        "memory_path": str(memory_path),
        "entry_count": len(entries),
        "learning_artifact_path": learning_context.get("learning_artifact_path", ""),
        "learning_status": learning_context.get("learning_status", "unavailable"),
        "learning_availability": learning_context.get("learning_availability", "unavailable"),
        "learning_validation_state": learning_context.get("learning_validation_state", "invalid"),
        "learning_validation_error": learning_context.get("learning_validation_error", ""),
        "learning_published_post_count": learning_context.get("learning_published_post_count", 0),
        "learning_pending_metrics_count": learning_context.get("learning_pending_metrics_count", 0),
        "learning_stale_pending_metrics_count": learning_context.get("learning_stale_pending_metrics_count", 0),
        "learning_resolution_state_summary": learning_context.get("learning_resolution_state_summary", {}),
        "learning_required_follow_up_action": learning_context.get("learning_required_follow_up_action", ""),
        "learning_winner_post_count": learning_context.get("learning_winner_post_count", 0),
        "recommendation": recommendation,
        "autonomy_progress": progress,
        "safe_operations": {
            "api_call_made": False,
            "generation_call_performed": False,
            "upload_performed": False,
            "queue_mutated": False,
            "publish_performed": False,
            "credentials_read": False,
        },
    }

    path = save_report(report, args.date)
    print(json.dumps({
        "ok": True,
        "output_path": str(path),
        "action_type": recommendation["action_type"],
        "recommended_recipe_id": recommendation["recommended_recipe_id"],
        "recommended_outfit_id": recommendation["recommended_outfit_id"],
        "recommended_environment_id": recommendation["recommended_environment_id"],
        "next_live_gate": recommendation["next_live_gate"],
        "learning_artifact_path": recommendation.get("learning_artifact_path", ""),
        "learning_status": recommendation.get("learning_status", "unavailable"),
        "learning_availability": recommendation.get("learning_availability", "unavailable"),
        "learning_required_follow_up_action": recommendation.get("learning_required_follow_up_action", ""),
        "autonomy_progress": progress,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
