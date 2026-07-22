from __future__ import annotations

import argparse
import inspect
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = ROOT / "tools" / "diagnostics"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DIAGNOSTICS) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS))

from lena_higgsfield_prompt_library_dryrun import (  # noqa: E402
    build_library_report,
    curate_top_prompts,
)
from pipeline.presence import human_presence_candidate_ranking_v1 as presence_ranking  # noqa: E402
from pipeline.prompting.lena_prompt_brain import ControlledProofLaneError  # noqa: E402
from pipeline.qa.lena_higgsfield_failure_memory import (  # noqa: E402
    compute_higgsfield_failure_memory,
)
from tools.strategy.lena_human_presence_profile_v1 import build_lena_presence_contract  # noqa: E402


SCHEMA_VERSION = "lena_pre_generation_candidate_gate_v1"
CANONICAL_NICHE = "Glamour, Choices, And Beautiful Trouble"
JSON_AUTHORITY_PATHS = (
    "pipeline/influencer_nodes/lena/persona.json",
    "pipeline/influencer_nodes/lena/lena_content_strategy_v1.json",
    "pipeline/prompt_banks/lena/lena_photo_scene_bank_v1.json",
    "pipeline/prompt_banks/lena/lena_high_caliber_prompt_recipe_bank_v1.json",
    "pipeline/prompt_banks/lena/strong_hook_bank_v1.json",
    "pipeline/prompt_banks/lena/lena_expression_gaze_bank_v1.json",
)
EXPRESSION_DERIVATION_REPO_PATH = "pipeline/prompting/lena_prompt_brain.py"
AUTHORITY_PATHS = JSON_AUTHORITY_PATHS + (EXPRESSION_DERIVATION_REPO_PATH,)
OUTPUT_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates"
DEFAULT_PRESENCE_PROFILE = "lena-default"
UNSUPPORTED_HOOK_CATEGORIES = {
    "meaningful_choice", "payoff", "callback", "consequence"
}
OPEN_LOOP_STATE_TERMS = (
    "later payoff", "future payoff", "later follow-up", "future follow-up",
    "follow-up is planned", "real follow-up", "open loop must", "before the decision",
)
SAFE_FOLLOWABILITY_ROLES = {
    "setup", "anticipation", "experience", "quiet_reset", "world_expansion"
}
MOTORCYCLE_TERMS = ("motorcycle", "moto", "cruiser", "chopper", "bike wash", "garage grease")
UNSAFE_TEXT_TERMS = (
    "pornographic", "sexual solicitation", "explicit sex", "fake emergency",
    "life-changing announcement", "pregnant", "married", "hospital emergency",
)


class GateError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _presence_observation(image: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": image.get("lane"),
        "scene_action": scene.get("action"),
        "activity": scene.get("action"),
        "reference_mode": image.get("reference_mode"),
        "camera_text": image.get("camera_text"),
        "lighting_text": image.get("lighting_text"),
        "environment_id": image.get("environment_id"),
        "environment_name": image.get("environment_name"),
        "expression_gaze_id": image.get("expression_gaze_id"),
        "expression_gaze_label": image.get("expression_gaze_label"),
        "expression_text": image.get("expression_text"),
        "pose_body_language_id": image.get("pose_body_language_id"),
        "pose_body_language_label": image.get("pose_body_language_label"),
        "wardrobe_silhouette_class": image.get("wardrobe_silhouette_class"),
        "effective_wardrobe_silhouette_class": image.get("effective_wardrobe_silhouette_class"),
        "framing_text": image.get("framing_text"),
        "caption_seed": image.get("caption_seed"),
    }


def _presence_selector_terms(plan: dict[str, Any], dimension: str) -> list[str]:
    allowed_terms_by_dimension = {
        "sensual_presence": {
            "gaze",
            "anticipation",
            "movement",
            "confidence",
            "timing",
            "reaction",
            "rhythm",
            "voice",
            "framing",
            "safe framing",
        },
        "body_presentation": {
            "safe framing",
            "reference mode",
            "realistic proportions",
            "anatomy continuity",
            "full body presence",
            "face priority",
            "dynamic motion framing",
            "required realistic",
            "continuity",
            "adult",
        },
    }
    section = plan.get(dimension, {})
    selector_terms = list(section.get("selector_terms", [])) if isinstance(section, dict) else []
    allowed = allowed_terms_by_dimension.get(dimension)
    if allowed is None:
        return selector_terms
    return [term for term in selector_terms if _normalize_text(term) in allowed]


def _presence_rank_order() -> list[str]:
    return [
        "no_failure_memory_caution",
        "lower_physical_interaction_risk",
        "premium_visual_discipline",
        "human_presence_alignment",
        "situational_specificity",
        "lived_in_detail",
        "character_fit",
        "followability",
        "recent_feed_contrast",
        "higgsfield_curator_score",
        "recipe_proof_priority",
        "canonical_hook_score",
    ]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise GateError("invalid_canonical_authority", f"{path} is not a JSON object")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def verify_authority_inputs_clean(paths: Iterable[str] = AUTHORITY_PATHS) -> None:
    for relative in paths:
        for cached in (False, True):
            args = ["diff", "--quiet"]
            if cached:
                args.append("--cached")
            args.extend(["HEAD", "--", relative])
            result = subprocess.run(["git", *args], cwd=ROOT, check=False)
            if result.returncode == 1:
                state = "staged" if cached else "modified"
                raise GateError("authority_conflict", f"canonical authority is {state}: {relative}")
            if result.returncode not in (0, 1):
                raise GateError("authority_check_failed", f"git could not inspect {relative}")


def load_authorities(root: Path = ROOT) -> dict[str, Any]:
    loaded = {relative: _read_json(root / relative) for relative in JSON_AUTHORITY_PATHS}
    persona, strategy, scene_bank, recipe_bank, hook_bank, expression_bank = loaded.values()
    if persona.get("canonical_niche") != CANONICAL_NICHE or strategy.get("canonical_niche") != CANONICAL_NICHE:
        raise GateError("invalid_canonical_authority", "persona and strategy canonical niches must agree")
    if persona.get("node_name") != "lena" or not persona.get("identity_rule") or not persona.get("core_standard"):
        raise GateError("invalid_identity_reference_contract", "canonical Lena identity contract is missing or contradictory")
    pillars = set(strategy.get("pillar_ids", []))
    temperatures = set(strategy.get("creative_temperatures", []))
    roles = set(strategy.get("narrative_roles", []))
    if not pillars or not temperatures or not roles:
        raise GateError("invalid_canonical_authority", "strategy enums are missing")

    scenes: dict[str, dict[str, Any]] = {}
    for scene in scene_bank.get("scenes", []):
        lane = scene.get("lane")
        if not lane or lane in scenes:
            raise GateError("invalid_canonical_authority", "scene lanes must be present and unique")
        _validate_strategy_item(scene, pillars, temperatures, roles, f"scene {lane}")
        scenes[lane] = scene

    recipes: list[dict[str, Any]] = []
    recipe_ids: set[str] = set()
    for recipe in recipe_bank.get("recipes", []):
        recipe_id = recipe.get("id")
        if not recipe_id or recipe_id in recipe_ids:
            raise GateError("invalid_canonical_authority", "recipe IDs must be present and unique")
        _validate_strategy_item(recipe, pillars, temperatures, roles, f"recipe {recipe_id}")
        recipe_ids.add(recipe_id)
        recipes.append(recipe)

    hooks: dict[str, dict[str, Any]] = {}
    categories = set(hook_bank.get("categories", []))
    for hook in hook_bank.get("hooks", []):
        hook_id = hook.get("id")
        if not hook_id or hook_id in hooks or hook.get("category") not in categories:
            raise GateError("invalid_canonical_authority", "hook IDs/categories must be valid and unique")
        hooks[hook_id] = hook
    if not scenes or not recipes or not hooks:
        raise GateError("invalid_canonical_authority", "canonical banks cannot be empty")
    return {
        "persona": persona,
        "strategy": strategy,
        "scene_bank": scene_bank,
        "recipe_bank": recipe_bank,
        "hook_bank": hook_bank,
        "expression_bank": expression_bank,
        "scenes": scenes,
        "recipes": recipes,
        "hooks": hooks,
        "input_provenance": [
            {"path": relative, "sha256": _sha256_file(root / relative), "semantics": "canonical authority"}
            for relative in AUTHORITY_PATHS
        ],
    }


def _validate_strategy_item(
    item: dict[str, Any], pillars: set[str], temperatures: set[str], roles: set[str], label: str
) -> None:
    item_pillars = item.get("strategy_pillars")
    item_roles = item.get("narrative_roles")
    if not item_pillars or not set(item_pillars) <= pillars:
        raise GateError("unknown_strategy_enum", f"{label} has invalid strategy_pillars")
    if item.get("creative_temperature") not in temperatures:
        raise GateError("unknown_strategy_enum", f"{label} has invalid creative_temperature")
    if not item_roles or not set(item_roles) <= roles:
        raise GateError("unknown_strategy_enum", f"{label} has invalid narrative_roles")


def load_recent_content(root: Path = ROOT) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    published_root = root / "pipeline" / "queue" / "published"
    for receipt_path in sorted(published_root.glob("*.json.receipt.json")):
        receipt = _read_json(receipt_path)
        inputs.append({"path": str(receipt_path.relative_to(root)), "sha256": _sha256_file(receipt_path), "semantics": "proves publication receipt only"})
        item_path = Path(str(receipt_path)[: -len(".receipt.json")])
        item: dict[str, Any] = {}
        if item_path.exists():
            item = _read_json(item_path)
            inputs.append({"path": str(item_path.relative_to(root)), "sha256": _sha256_file(item_path), "semantics": "proves its own recorded published-item fields"})
        publication_timestamp = receipt.get("timestamp_utc") or receipt.get("instagram_timestamp")
        records.append({
            "evidence_class": "published_receipt",
            **_exact_rotation_fields(item),
            "publication_timestamp_utc": publication_timestamp,
            "receipt_path": str(receipt_path.relative_to(root)),
        })

    memory_path = root / "pipeline" / "state" / "lena_prompt_memory.json"
    if memory_path.exists():
        memory = _read_json(memory_path)
        inputs.append({"path": str(memory_path.relative_to(root)), "sha256": _sha256_file(memory_path), "semantics": "proves recorded generation/rotation facts only"})
        for entry in memory.get("recent", []):
            if isinstance(entry, dict):
                records.append({"evidence_class": "prompt_memory", **_exact_rotation_fields(entry)})

    debug_root = root / "pipeline" / "higgsfield_debug"
    for manifest_path in sorted(debug_root.glob("*/*/result_manifest.json")):
        manifest = _read_json(manifest_path)
        inputs.append({"path": str(manifest_path.relative_to(root)), "sha256": _sha256_file(manifest_path), "semantics": "proves recorded Higgsfield generation history only"})
        records.append({"evidence_class": "higgsfield_manifest", **_exact_rotation_fields(manifest)})
    return {"records": records, "inputs": inputs}


def _exact_rotation_fields(value: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "lane": ("lane",),
        "outfit_id": ("outfit_id", "wardrobe_outfit_id"),
        "environment_id": ("environment_id",),
        "pose_id": ("pose_id", "pose_body_language_id"),
        "media_type": ("media_type", "media_kind"),
        "creative_temperature": ("creative_temperature",),
        "narrative_roles": ("narrative_roles",),
    }
    result: dict[str, Any] = {}
    for target, keys in aliases.items():
        for key in keys:
            if value.get(key) is not None:
                result[target] = value[key]
                break
    return result


def build_prompt_candidates(
    as_of_date: str,
    head8: str,
    required_recipe_id: str = "",
    presence_contract: dict[str, Any] | None = None,
    presence_plan: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prefix = f"lenagate{as_of_date.replace('-', '')}{head8}"
    try:
        library = build_library_report(
            as_of_date,
            prefix,
            1,
            10,
            required_recipe_id=required_recipe_id,
            presence_contract=presence_contract,
            presence_plan=presence_plan,
        )
    except Exception as exc:
        from pipeline.presence import human_presence_contract_v1 as presence_contract_module
        from pipeline.presence import human_presence_prompt_plan_v1 as presence_plan_module

        if isinstance(exc, presence_plan_module.HumanPresencePromptPlanError) or isinstance(
            exc,
            presence_contract_module.HumanPresenceContractError,
        ):
            raise GateError(exc.code, exc.detail) from exc
        raise
    images = [image for pack in library["pack_reports"] for image in pack["images"]]
    identities = [(image.get("slot_id"), image.get("image_prompt")) for image in images]
    if len(images) != 10 or len({slot for slot, _ in identities}) != 10 or any(not slot or not prompt for slot, prompt in identities):
        raise GateError("non_reproducible_prompt_identity", "the deterministic prompt pack did not expose ten unique prompt identities")
    curation = curate_top_prompts(library, 10)
    prompt_meta = {
        "pack_count": 1,
        "prompt_count": library["total_prompts"],
        "library_prefix": prefix,
        "prompt_identity_sha256": _sha256_bytes(_canonical_bytes(identities)),
        "curator_excluded_count": curation["excluded_count"],
        "failure_memory_hard_excluded_patterns": curation["failure_memory_hard_excluded_patterns"],
        "failure_memory_soft_flagged_patterns": curation["failure_memory_soft_flagged_patterns"],
        "failure_memory_excluded_count": curation["failure_memory_excluded_count"],
    }
    if library.get("human_presence") is not None:
        prompt_meta["human_presence"] = library["human_presence"]
    return curation["selected"], prompt_meta


def _supports_photo(value: Any) -> bool:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return "photo" in str(value or "").lower()


def _is_active_recipe(recipe: dict[str, Any]) -> bool:
    return recipe.get("production_status", "active") not in {"blocked", "inactive", "excluded"}


def _hook_is_safe(hook: dict[str, Any], recipe: dict[str, Any]) -> bool:
    if hook.get("category") in UNSUPPORTED_HOOK_CATEGORIES:
        return False
    if not _supports_photo(hook.get("best_content_type")):
        return False
    text = " ".join(str(hook.get(key, "")) for key in ("hook_text", "caption_followup", "risk_notes")).lower()
    if any(term in text for term in UNSAFE_TEXT_TERMS):
        return False
    if hook.get("category") == "curiosity_open_loop" and any(term in text for term in OPEN_LOOP_STATE_TERMS):
        return False
    if recipe.get("choice_eligible") and hook.get("category") == "meaningful_choice":
        return False
    return True


def _best_recipe(scene: dict[str, Any], recipes: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        recipe for recipe in recipes
        if _is_active_recipe(recipe)
        and _supports_photo(recipe.get("best_content_type"))
        and recipe["strategy_pillars"][0] == scene["strategy_pillars"][0]
        and recipe["creative_temperature"] == scene["creative_temperature"]
        and set(recipe["narrative_roles"]) & set(scene["narrative_roles"])
    ]
    return min(
        matches,
        key=lambda r: (
            not r.get("controlled_proof_lane", False),
            int(r.get("proof_priority", 999)),
            r["id"],
        ),
    ) if matches else None


def _best_hook(recipe: dict[str, Any], hooks: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    linked = [
        hook for hook in hooks.values()
        if hook.get("category") in recipe.get("linked_hook_categories", []) and _hook_is_safe(hook, recipe)
    ]
    return min(linked, key=lambda h: (-int(h.get("scores", {}).get("total_score", 0)), h["id"])) if linked else None


def _prompt_section(prompt: str, label: str, next_labels: tuple[str, ...]) -> str | None:
    boundary = "|".join(re.escape(next_label) for next_label in next_labels)
    match = re.search(rf"\b{re.escape(label)}:\s*(.*?)(?=\s+(?:{boundary}):|$)", prompt, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _scene_prompt_compatibility(
    scene: dict[str, Any], image: dict[str, Any], recipe: dict[str, Any] | None
) -> dict[str, Any]:
    prompt = str(image.get("image_prompt", ""))
    prompt_scene = _prompt_section(prompt, "Scene", ("Wardrobe", "Pose", "Expression", "Camera", "Framing", "Lighting", "Mood"))
    prompt_pose = _prompt_section(prompt, "Pose", ("Expression", "Camera", "Framing", "Lighting", "Mood")) or str(image.get("pose_body_language_label", ""))
    prompt_expression = _prompt_section(prompt, "Expression", ("Camera", "Framing", "Lighting", "Mood")) or str(image.get("expression_gaze_label", ""))
    actual = " ".join(part for part in (prompt, prompt_pose, prompt_expression) if part).lower()
    canonical_action = str(scene.get("action", "")).lower()
    contradictions: list[str] = []

    posture_pairs = (
        (r"\bwalk(?:ing|s)?\b", r"\b(?:standing|sitting|seated|stationary)\b", "action_walk_vs_stationary"),
        (r"\b(?:sitting|seated)\b", r"\bstanding\b", "posture_sitting_vs_standing"),
        (r"\bstanding\b", r"\b(?:sitting|seated)\b", "posture_standing_vs_sitting"),
        (r"\b(?:entering|walking into)\b", r"\b(?:leaving|walking away)\b", "orientation_entering_vs_leaving"),
        (r"\b(?:leaving|walking away)\b", r"\b(?:entering|walking into)\b", "orientation_leaving_vs_entering"),
    )
    for canonical_pattern, actual_pattern, code in posture_pairs:
        if re.search(canonical_pattern, canonical_action) and re.search(actual_pattern, actual):
            contradictions.append(code)

    canonical_window_gaze = "window" in canonical_action and any(term in canonical_action for term in ("glanc", "look", "gaze", "eyes"))
    actual_camera_gaze = any(term in actual for term in ("facing the camera", "toward the camera", "direct confident gaze", "eyes at the camera"))
    if canonical_window_gaze and actual_camera_gaze:
        contradictions.append("gaze_window_vs_camera")
    canonical_camera_gaze = "camera" in canonical_action and any(term in canonical_action for term in ("glanc", "look", "gaze", "facing"))
    actual_away_gaze = any(term in actual for term in ("looking away", "gazing away", "eyes toward the window", "glancing toward the window"))
    if canonical_camera_gaze and actual_away_gaze:
        contradictions.append("gaze_camera_vs_away")

    prop_resting = any(term in actual for term in ("resting on the counter", "sitting on the counter", "placed on the counter"))
    if "pouring" in canonical_action and prop_resting:
        contradictions.append("prop_pouring_vs_resting")
    if any(term in canonical_action for term in ("holding", "carrying")) and prop_resting:
        contradictions.append("prop_held_vs_resting")

    required_visual = (recipe or {}).get("scene_logic_contract", {}).get("required_visual_evidence", [])
    if any("mid-action" in str(requirement).lower() for requirement in required_visual) and prop_resting:
        contradictions.append("required_mid_action_evidence_contradicted")

    return {
        "prompt_scene": prompt_scene,
        "prompt_pose": prompt_pose,
        "prompt_expression": prompt_expression,
        "material_contradictions": sorted(set(contradictions)),
    }


def _latest_published_temperature(records: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    published: list[tuple[datetime, dict[str, Any]]] = []
    for record in records:
        if record.get("evidence_class") != "published_receipt" or not record.get("publication_timestamp_utc"):
            continue
        try:
            parsed = datetime.fromisoformat(str(record["publication_timestamp_utc"]).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                continue
            published.append((parsed.astimezone(timezone.utc), record))
        except ValueError:
            continue
    if not published:
        return None, None
    _, latest = max(published, key=lambda item: item[0])
    return latest.get("creative_temperature"), str(latest["publication_timestamp_utc"])


def _candidate_hard_gate(image: dict[str, Any], scene: dict[str, Any], blocked: set[str], strategy: dict[str, Any], recent: list[dict[str, Any]], recipe: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    lane = str(image.get("lane", ""))
    if lane in blocked:
        reasons.append("blocked_scene")
    if any(term in lane.lower() for term in MOTORCYCLE_TERMS) and strategy["motorcycle_role"]["existing_production_blocks_remain_authoritative"]:
        reasons.append("motorcycle_production_blocked")
    if image.get("soul_name") != "Lena" or not image.get("soul_version") or image.get("soul_selection_mode") != "provider_config_not_prompt_text":
        reasons.append("identity_contract_failure")
    validation = image.get("validation", {})
    required = (
        "framing_present", "wardrobe_casual_free", "scene_action_conflict_free",
        "soul_anchor_absent", "negative_prompt_disabled", "heavy_overcorrection_free",
        "pose_scene_match_pass",
    )
    if not all(validation.get(key) is True for key in required) or validation.get("low_hook_terms_found"):
        reasons.append("prompt_hard_validation_failure")
    prompt = str(image.get("image_prompt", "")).lower()
    if any(term in prompt for term in UNSAFE_TEXT_TERMS):
        reasons.append("unsafe_framing")
    temperature = scene["creative_temperature"]
    if temperature == "high_heat":
        previous_temperature, _ = _latest_published_temperature(recent)
        if previous_temperature is None or previous_temperature == "high_heat":
            reasons.append("high_heat_sequence_unproven_or_consecutive")
    if "swimwear" in prompt or "bikini" in prompt:
        context = " ".join((str(scene.get("environment", "")), str(scene.get("details", "")))).lower()
        if not any(
            re.search(rf"\b{re.escape(term)}\b", context)
            for term in strategy["high_heat_rules"]["swimwear_requires_context"]
        ):
            reasons.append("swimwear_context_missing")
    sexual_hits = sum(term in prompt for term in ("cleavage", "bikini", "low-rise", "micro mini", "sheer"))
    if sexual_hits >= 3:
        reasons.append("sexual_signal_stacking")
    if recipe is not None:
        material_contradictions = _scene_prompt_compatibility(scene, image, recipe)["material_contradictions"]
        if material_contradictions:
            reasons.append("scene_prompt_material_contradiction")
            reasons.extend(material_contradictions)
    return reasons


def _count_recent(records: list[dict[str, Any]], field: str, value: Any) -> int:
    return sum(1 for record in records if value is not None and record.get(field) == value)


def _substantive_scores(scene: dict[str, Any], recipe: dict[str, Any], hook: dict[str, Any], image: dict[str, Any], recent: list[dict[str, Any]], curator: dict[str, Any]) -> dict[str, Any]:
    contract = recipe.get("scene_logic_contract", {})
    required_visual = contract.get("required_visual_evidence", [])
    frame_objects = scene.get("frame_evidence_objects", [])
    specificity = sum(bool(scene.get(key)) for key in ("action", "environment", "details", "caption")) + bool(recipe.get("human_reason")) + min(3, len(required_visual)) + bool(scene.get("narrative_roles")) + bool(hook.get("visual_pairing"))
    lived_detail = bool(scene.get("details")) + min(3, len(frame_objects)) + min(3, len(required_visual)) + bool(image.get("wardrobe_outfit_id")) + bool(recipe.get("environment_id")) + bool(scene.get("action"))
    character_fit = len(set(scene["narrative_roles"]) & SAFE_FOLLOWABILITY_ROLES) + int(hook.get("scores", {}).get("lena_voice_score", 0))
    followability = len(set(scene["narrative_roles"]) & SAFE_FOLLOWABILITY_ROLES) + int(hook.get("scores", {}).get("curiosity_score", 0))
    interaction_risk = 1 if any(word in str(image.get("pose_body_language_label", "")).lower() for word in ("holding", "both hands", "interlocked", "complex")) else 0
    prompt_lower = str(image.get("image_prompt", "")).lower()
    sexuality_signals = sum(term in prompt_lower for term in ("cleavage", "bikini", "low-rise", "micro mini", "sheer"))
    premium_restraint = max(0, 2 - sexuality_signals)
    contrast = {
        "lane_repetitions": _count_recent(recent, "lane", image.get("lane")),
        "outfit_repetitions": _count_recent(recent, "outfit_id", image.get("wardrobe_outfit_id")),
        "environment_repetitions": _count_recent(recent, "environment_id", image.get("environment_id")),
        "pose_repetitions": _count_recent(recent, "pose_id", image.get("pose_body_language_id")),
    }
    return {
        "failure_memory_caution": bool(curator.get("failure_memory_flag")),
        "physical_interaction_risk": interaction_risk,
        "identity_consistency": "passed canonical Soul identity hard gate",
        "physical_world_credibility": "passed prompt scene/action and pose/scene hard gates",
        "premium_visual_discipline": premium_restraint,
        "balanced_sexuality": "passed sequencing, context, and signal-stacking hard gates",
        "situational_specificity": specificity,
        "lived_in_detail": lived_detail,
        "character_fit": character_fit,
        "followability": followability,
        "feed_contrast": contrast,
        "higgsfield_curator_score": int(curator.get("total_score", 0)),
        "recipe_proof_priority": int(recipe.get("proof_priority", 999)),
        "hook_score": int(hook.get("scores", {}).get("total_score", 0)),
    }


def _rank_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    score = candidate["ranking_evidence"]
    contrast = score["feed_contrast"]
    substantive = [
        score["failure_memory_caution"],
        score["physical_interaction_risk"],
        -score["premium_visual_discipline"],
    ]
    if "human_presence_bonus" in score:
        substantive.append(-score["human_presence_bonus"])
    substantive.extend(
        [
            -score["situational_specificity"],
            -score["lived_in_detail"],
            -score["character_fit"],
            -score["followability"],
            contrast["lane_repetitions"],
            contrast["outfit_repetitions"],
            contrast["environment_repetitions"],
            contrast["pose_repetitions"],
            -score["higgsfield_curator_score"],
            score["recipe_proof_priority"],
            -score["hook_score"],
        ]
    )
    tie = (candidate["lane"], candidate["recipe_id"], candidate["hook_id"], candidate["slot_id"])
    return tuple(substantive) + tie


def select_candidate(
    authorities: dict[str, Any],
    prompt_candidates: list[dict[str, Any]],
    recent: dict[str, Any],
    *,
    required_recipe_id: str = "",
    presence_contract: dict[str, Any] | None = None,
    presence_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bool]:
    rejected: Counter[str] = Counter()
    valid: list[dict[str, Any]] = []
    blocked = set(authorities["scene_bank"].get("production_blocked_lanes", []))
    saw_required_recipe = False
    if presence_plan is None and presence_contract is not None:
        from pipeline.presence import human_presence_contract_v1 as presence_contract_module
        from pipeline.presence import human_presence_prompt_plan_v1 as presence_plan_module

        try:
            presence_plan = presence_plan_module.compile_human_presence_prompt_plan(
                presence_contract,
                medium="still_image",
            )
        except (
            presence_plan_module.HumanPresencePromptPlanError,
            presence_contract_module.HumanPresenceContractError,
        ) as exc:
            raise GateError(exc.code, exc.detail) from exc
    for curator in prompt_candidates:
        image = curator.get("image", {})
        lane = image.get("lane")
        scene = authorities["scenes"].get(lane)
        if scene is None:
            rejected["unknown_canonical_scene"] += 1
            continue
        recipe = _best_recipe(scene, authorities["recipes"])
        controlled_proof_lane_allowed = (
            bool(required_recipe_id)
            and recipe is not None
            and recipe.get("id") == required_recipe_id
            and recipe.get("controlled_proof_lane", False)
        )
        candidate_blocked = blocked - {lane} if controlled_proof_lane_allowed else blocked
        reasons = _candidate_hard_gate(
            image,
            scene,
            candidate_blocked,
            authorities["strategy"],
            recent["records"],
            recipe,
        )
        if recipe is None:
            reasons.append("no_compatible_active_recipe")
        elif required_recipe_id and recipe["id"] != required_recipe_id:
            reasons.append("required_recipe_candidate_missing")
        else:
            saw_required_recipe = True
            if (
                required_recipe_id
                and recipe.get("controlled_proof_lane", False)
                and image.get("wardrobe_outfit_id") != recipe.get("wardrobe_outfit_id")
            ):
                reasons.append("required_recipe_wardrobe_mismatch")
        hook = _best_hook(recipe, authorities["hooks"]) if recipe else None
        if hook is None:
            reasons.append("no_safe_linked_hook")
        if presence_plan is not None:
            if image.get("human_presence") != presence_plan:
                reasons.append("human_presence_plan_mismatch")
        if reasons:
            rejected.update(set(reasons))
            continue
        prompt_sha = _sha256_bytes(image["image_prompt"].encode())
        scene_evidence = _scene_prompt_compatibility(scene, image, recipe)
        generated_environment_id = image.get("environment_id")
        candidate = {
            "candidate_id": f"{image['slot_id']}::{recipe['id']}::{hook['id']}",
            "slot_id": image["slot_id"],
            "scene_identity_field": "lane",
            "lane": lane,
            "activity": scene_evidence["prompt_scene"],
            "recipe_id": recipe["id"],
            "recipe_binding": "strategy compatibility",
            "hook_id": hook["id"],
            "primary_pillar": scene["strategy_pillars"][0],
            "supporting_pillar": scene["strategy_pillars"][1] if len(scene["strategy_pillars"]) > 1 else None,
            "creative_temperature": scene["creative_temperature"],
            "narrative_roles": scene["narrative_roles"],
            "choice_eligible": scene["choice_eligible"],
            "payoff_eligible": scene["payoff_eligible"],
            "audience_choice_action": "none",
            "payoff_claimed": False,
            "pose": image.get("pose_body_language_label"),
            "pose_body_language_id": image.get("pose_body_language_id"),
            "expression_gaze_id": image.get("expression_gaze_id"),
            "expression_gaze_label": image.get("expression_gaze_label"),
            "expression_canonical_text": image.get("expression_canonical_text"),
            "expression_text": image.get("expression_text"),
            "expression_safe_fallback_used": image.get("expression_safe_fallback_used"),
            "expression_safe_fallback_reason": image.get("expression_safe_fallback_reason"),
            "expression_scene_conflict_terms": image.get("expression_scene_conflict_terms"),
            "expression_derivation_scene_action": image.get(
                "expression_derivation_scene_action"
            ),
            "visual_style": image.get("effective_wardrobe_silhouette_class"),
            "wardrobe_outfit_id": image.get("wardrobe_outfit_id"),
            "environment_id": generated_environment_id,
            "camera_text": image.get("camera_text"),
            "lighting_text": image.get("lighting_text"),
            "concept_summary": " | ".join(
                part for part in (
                    scene_evidence["prompt_scene"], scene_evidence["prompt_pose"],
                    scene_evidence["prompt_expression"], image.get("camera_text"), image.get("lighting_text"),
                ) if part
            ),
            "hook_text": hook["hook_text"],
            "caption_seed": scene["caption"],
            "higgsfield_action": "informational dry-run only",
            "prompt_sha256": prompt_sha,
            "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {image['slot_id'].split('-')[0] if False else '{as_of_date}'} --slot-id {image['slot_id']}",
            "strategy_compatibility_evidence": {
                "recipe_environment_id": recipe.get("environment_id"),
                "recipe_wardrobe_outfit_id": recipe.get("wardrobe_outfit_id"),
                "generated_environment_exact_match": (
                    generated_environment_id == recipe.get("environment_id")
                    if generated_environment_id is not None and recipe.get("environment_id") is not None
                    else None
                ),
                "generated_wardrobe_exact_match": (
                    image.get("wardrobe_outfit_id") == recipe.get("wardrobe_outfit_id")
                    if image.get("wardrobe_outfit_id") is not None and recipe.get("wardrobe_outfit_id") is not None
                    else None
                ),
            },
        }
        if generated_environment_id is None:
            candidate.pop("environment_id")
        candidate["ranking_evidence"] = _substantive_scores(scene, recipe, hook, image, recent["records"], curator)
        if presence_plan is not None:
            try:
                candidate["human_presence_ranking"] = presence_ranking.score_candidate_presence_alignment(
                    presence_plan,
                    _presence_observation(image, scene),
                )
            except presence_ranking.HumanPresenceCandidateRankingError as exc:
                raise GateError(exc.code, exc.detail) from exc
            candidate["ranking_evidence"]["human_presence_bonus"] = candidate["human_presence_ranking"]["total_bonus"]
        candidate["deterministic_noncreative_tiebreak"] = [lane, recipe["id"], hook["id"], image["slot_id"]]
        candidate["_prompt"] = image["image_prompt"]
        valid.append(candidate)
    if not valid:
        return None, [{"reason": key, "candidate_count": value} for key, value in sorted(rejected.items())], saw_required_recipe
    selected = min(valid, key=_rank_key)
    return selected, [{"reason": key, "candidate_count": value} for key, value in sorted(rejected.items())], saw_required_recipe


def _critical_gap_notes(recent: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if not any(record.get("creative_temperature") for record in recent["records"]):
        notes.append("historical creative temperature is unknown; non-high-heat selection remains allowed")
    if not any(record.get("outfit_id") for record in recent["records"]):
        notes.append("recent outfit identity is unavailable; confidence reduced, selection remains allowed")
    if not recent["records"]:
        notes.append("recent content evidence is unavailable; selection remains allowed for non-state-dependent candidates")
    return notes


def _decision_core(authority_commit: str, as_of_date: str, authorities: dict[str, Any], candidate: dict[str, Any] | None, rejected: list[dict[str, Any]], recent: dict[str, Any], prompt_meta: dict[str, Any], *, required_recipe_id: str = "") -> dict[str, Any]:
    noncritical = _critical_gap_notes(recent)
    status = "selected" if candidate else "abstain"
    clean_candidate = None
    presence_enabled = prompt_meta.get("human_presence") is not None
    if candidate:
        clean_candidate = {key: value for key, value in candidate.items() if key != "_prompt" and value is not None}
        clean_candidate["exact_proposed_dry_run_command"] = clean_candidate["exact_proposed_dry_run_command"].replace("{as_of_date}", as_of_date)
    ranking_order = [
        "no_failure_memory_caution",
        "lower_physical_interaction_risk",
        "premium_visual_discipline",
    ]
    if presence_enabled:
        ranking_order.append("human_presence_alignment")
    ranking_order.extend([
        "situational_specificity",
        "lived_in_detail",
        "character_fit",
        "followability",
        "recent_feed_contrast",
        "higgsfield_curator_score",
        "recipe_proof_priority",
        "canonical_hook_score",
    ])
    result = {
        "schema_version": SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": as_of_date,
        "authority_commit": authority_commit,
        "strategy_contract": {"canonical_niche": CANONICAL_NICHE, "path": AUTHORITY_PATHS[1]},
        "input_provenance": authorities["input_provenance"] + recent["inputs"],
        "candidate_status": status,
        "final_action": "prepare_higgsfield_still_dry_run_for_review" if candidate else "abstain_no_generation_ready_candidate",
        "candidate": clean_candidate,
        "evidence": {
            "prompt_pack": prompt_meta,
            "recipe_binding_semantics": "strategy compatibility, not prompt provenance",
            "recent_content_evidence_semantics": "exact recorded fields only; missing fields remain unknown",
            "ranking_order": ranking_order,
            "tiebreak_label": "deterministic_noncreative_tiebreak",
        },
        "rejected_or_blocked_reasons": rejected,
        "confidence": "high" if candidate and not noncritical and not candidate["ranking_evidence"]["failure_memory_caution"] else ("medium" if candidate else "blocked"),
        "noncritical_evidence_gaps": noncritical,
        "failure_memory_inputs": {
            "semantics": "recorded structured QA/failure outcomes only",
            **{key: prompt_meta.get(key) for key in prompt_meta if key.startswith("failure_memory_")},
        },
        "recent_content_inputs": recent["inputs"],
        "expensive_video_boundary": "not evaluated; this gate selects an ordinary Higgsfield still only",
        "exact_next_allowed_action": clean_candidate.get("exact_proposed_dry_run_command") if clean_candidate else "none",
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    if required_recipe_id:
        result["required_recipe_id"] = required_recipe_id
    return result


def write_decision(decision_core: dict[str, Any], output_root: Path = OUTPUT_ROOT, generated_at_utc: str | None = None) -> tuple[Path, dict[str, Any], bool]:
    fingerprint = _sha256_bytes(_canonical_bytes(decision_core))
    decision = dict(decision_core)
    decision["generated_at_utc"] = generated_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    decision["decision_fingerprint_sha256"] = fingerprint
    head8 = decision["authority_commit"][:8]
    path = output_root / decision["as_of_date"] / f"lena_pre_generation_candidate_{head8}_{fingerprint[:12]}.json"
    payload = _canonical_bytes(decision)
    if path.exists():
        existing = _read_json(path)
        stored_fingerprint = existing.get("decision_fingerprint_sha256")
        stored_core = {
            key: value for key, value in existing.items()
            if key not in {"generated_at_utc", "decision_fingerprint_sha256"}
        }
        recomputed_fingerprint = _sha256_bytes(_canonical_bytes(stored_core))
        if stored_fingerprint != recomputed_fingerprint or recomputed_fingerprint != fingerprint:
            raise GateError("decision_artifact_conflict", f"refusing to overwrite conflicting artifact: {path}")
        return path, existing, True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path, decision, False


def run_gate(
    as_of_date: str,
    output_root: Path = OUTPUT_ROOT,
    *,
    required_recipe_id: str = "",
    presence_contract: dict[str, Any] | None = None,
    presence_plan: dict[str, Any] | None = None,
    verify_clean: bool = True,
    authority_loader: Callable[[], dict[str, Any]] | None = None,
    recent_loader: Callable[[], dict[str, Any]] | None = None,
    prompt_builder: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = build_prompt_candidates,
) -> tuple[Path, dict[str, Any], bool]:
    authority_commit = _git("rev-parse", "HEAD")
    if verify_clean:
        verify_authority_inputs_clean()
    authorities = authority_loader() if authority_loader else load_authorities()
    recent = recent_loader() if recent_loader else load_recent_content()
    if presence_plan is None and presence_contract is not None:
        from pipeline.presence import human_presence_contract_v1 as presence_contract_module
        from pipeline.presence import human_presence_prompt_plan_v1 as presence_plan_module

        try:
            presence_plan = presence_plan_module.compile_human_presence_prompt_plan(
                presence_contract,
                medium="still_image",
            )
        except (
            presence_plan_module.HumanPresencePromptPlanError,
            presence_contract_module.HumanPresenceContractError,
        ) as exc:
            raise GateError(exc.code, exc.detail) from exc
    call_kwargs = {}
    if required_recipe_id or presence_plan is not None:
        try:
            prompt_builder_signature = inspect.signature(prompt_builder)
        except (TypeError, ValueError):
            prompt_builder_signature = None
        if prompt_builder_signature is not None:
            accepts_required_recipe = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD or name == "required_recipe_id"
                for name, parameter in prompt_builder_signature.parameters.items()
            )
            if accepts_required_recipe and required_recipe_id:
                call_kwargs["required_recipe_id"] = required_recipe_id
            if presence_plan is not None:
                accepts_presence_contract = any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD or name == "presence_contract"
                    for name, parameter in prompt_builder_signature.parameters.items()
                )
                accepts_presence_plan = any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD or name == "presence_plan"
                    for name, parameter in prompt_builder_signature.parameters.items()
                )
                if accepts_presence_plan:
                    call_kwargs["presence_plan"] = presence_plan
                elif accepts_presence_contract:
                    call_kwargs["presence_contract"] = presence_contract
                else:
                    raise GateError(
                        "unsupported_presence_profile",
                        "the configured prompt builder does not accept a presence contract",
                    )
    try:
        candidates, prompt_meta = prompt_builder(as_of_date, authority_commit[:8], **call_kwargs)
    except ControlledProofLaneError as exc:
        raise GateError(exc.code, exc.detail) from exc
    candidate, rejected, saw_required_recipe = select_candidate(
        authorities,
        candidates,
        recent,
        required_recipe_id=required_recipe_id,
        presence_contract=presence_contract,
        presence_plan=presence_plan,
    )
    if required_recipe_id and not saw_required_recipe:
        raise GateError(
            "required_recipe_candidate_missing",
            f"no candidate available for required recipe {required_recipe_id!r}",
        )
    core = _decision_core(
        authority_commit,
        as_of_date,
        authorities,
        candidate,
        rejected,
        recent,
        prompt_meta,
        required_recipe_id=required_recipe_id,
    )
    return write_decision(core, output_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select Lena's next ordinary Higgsfield still candidate locally.")
    parser.add_argument("--date", required=True, help="Decision date (YYYY-MM-DD).")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_ROOT, help="Artifact root; defaults to the canonical strategy path.")
    parser.add_argument("--required-recipe-id", default="", help="Optional required recipe binding for canonical downstream handoff alignment.")
    parser.add_argument(
        "--presence-profile",
        default="",
        choices=("", DEFAULT_PRESENCE_PROFILE),
        help="Optional opt-in presence ranking profile; lena-default enables the deterministic HPE bonus path.",
    )
    args = parser.parse_args()
    presence_contract = None
    if args.presence_profile:
        if args.presence_profile != DEFAULT_PRESENCE_PROFILE:
            print(json.dumps({"candidate_status": "blocked", "reason": "unknown_presence_profile", "detail": args.presence_profile, "provider_authorized": False}, sort_keys=True))
            return 2
        presence_contract = build_lena_presence_contract()
    try:
        path, decision, reused = run_gate(
            args.date,
            args.out_dir,
            required_recipe_id=args.required_recipe_id,
            presence_contract=presence_contract,
        )
    except GateError as exc:
        print(json.dumps({"candidate_status": "blocked", "reason": exc.code, "detail": exc.detail, "provider_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps({"candidate_status": decision["candidate_status"], "candidate_id": (decision.get("candidate") or {}).get("candidate_id"), "artifact_path": str(path), "reused": reused, "provider_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
