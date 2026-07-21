from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder  # noqa: E402
from tools.strategy import lena_execute_retry_decision_v1 as legacy_retry  # noqa: E402
from tools.strategy import lena_pose_provenance_v1 as pose_provenance  # noqa: E402
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff  # noqa: E402
from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits  # noqa: E402


SCHEMA_VERSION = "lena_provider_prompt_budget_audit_v1"
REPORT_TYPE = "lena_provider_prompt_budget_audit"
EXPECTED_GOVERNED_RECIPE_COUNT = 19
RECIPE_BANK_REPO_PATH = "pipeline/prompt_banks/lena/lena_high_caliber_prompt_recipe_bank_v1.json"
POSE_BANK_REPO_PATH = pose_provenance.POSE_AUTHORITY_REPO_PATH
EXPRESSION_BANK_REPO_PATH = pose_provenance.EXPRESSION_AUTHORITY_REPO_PATH
RECIPE_BANK = ROOT / RECIPE_BANK_REPO_PATH
POSE_BANK = ROOT / POSE_BANK_REPO_PATH
EXPRESSION_BANK = ROOT / EXPRESSION_BANK_REPO_PATH

FIRST_GENERATION = "first_generation"
ORDINARY_RETRY = "ordinary_retry"
TYPED_HAIR_RETRY = "typed_hair_retry"
LEGACY_BACKGROUND_RETRY = "legacy_background_retry"
LEGACY_HAIR_RETRY = "legacy_hair_retry"
RETRY_TYPES = (
    FIRST_GENERATION,
    ORDINARY_RETRY,
    TYPED_HAIR_RETRY,
    LEGACY_BACKGROUND_RETRY,
    LEGACY_HAIR_RETRY,
)


class PromptBudgetAuditError(RuntimeError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromptBudgetAuditError(f"could not read audit input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PromptBudgetAuditError(f"audit input must contain a JSON object: {path}")
    return value, raw


def _canonical_pose_entry(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise PromptBudgetAuditError("pose bank entries must be JSON objects")
    pose_id = value.get("pose_body_language_id")
    label = value.get("label", value.get("pose_body_language_label"))
    text = value.get("text", value.get("pose_text"))
    if not all(isinstance(item, str) and item for item in (pose_id, label, text)):
        raise PromptBudgetAuditError("every canonical pose requires a nonempty ID, label, and text")
    pose_provenance.validate_provider_body_text(
        text,
        label=f"canonical pose {pose_id}",
        max_chars=prompt_limits.PROVIDER_SECTION_BODY_MAX_CHARS,
    )
    return {
        "pose_body_language_id": pose_id,
        "pose_body_language_label": label,
        "pose_text": text,
    }


def _canonical_expression_entry(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise PromptBudgetAuditError("expression bank entries must be JSON objects")
    expression_id = value.get("expression_gaze_id")
    label = value.get("label", value.get("expression_gaze_label"))
    text = value.get("text", value.get("expression_text"))
    if not all(isinstance(item, str) and item for item in (expression_id, label, text)):
        raise PromptBudgetAuditError(
            "every canonical expression requires a nonempty ID, label, and text"
        )
    pose_provenance.validate_provider_body_text(
        text,
        label=f"canonical expression {expression_id}",
        max_chars=prompt_limits.PROVIDER_SECTION_BODY_MAX_CHARS,
    )
    return {
        "expression_gaze_id": expression_id,
        "expression_gaze_label": label,
        "expression_text": text,
    }


def _default_audit_expression_entry() -> dict[str, str]:
    bank, _ = _read_json_object(EXPRESSION_BANK)
    expressions = bank.get("combos")
    if not isinstance(expressions, list) or not expressions:
        raise PromptBudgetAuditError(
            "canonical expression bank must contain at least one expression"
        )
    canonical = [_canonical_expression_entry(item) for item in expressions]
    return max(
        canonical,
        key=lambda item: (len(item["expression_text"]), item["expression_gaze_id"]),
    )


def _retry_sections(
    base_sections: list[tuple[str, str]],
    retry_type: str,
) -> list[tuple[str, str]]:
    if retry_type not in RETRY_TYPES:
        raise PromptBudgetAuditError(f"unknown retry type: {retry_type}")
    sections = {label: body for label, body in base_sections if body}
    if retry_type == ORDINARY_RETRY:
        sections["Environment"] = retry_handoff.RETRY_ENVIRONMENT_TEXT
        sections["Cinematography"] = retry_handoff.RETRY_CINEMATOGRAPHY_TEXT
        sections["Technical"] = sections["Technical"] + retry_handoff.RETRY_TECHNICAL_APPEND
    elif retry_type == TYPED_HAIR_RETRY:
        sections["Technical"] = sections["Technical"] + " " + retry_handoff.HAIR_CROWN_CONSTRAINT
    elif retry_type == LEGACY_BACKGROUND_RETRY:
        sections["Technical"] = sections["Technical"] + " " + legacy_retry.BACKGROUND_IDENTITY_CONSTRAINT
    elif retry_type == LEGACY_HAIR_RETRY:
        sections["Technical"] = sections["Technical"] + " " + legacy_retry.HAIR_CROWN_CONSTRAINT
    return [
        (label, sections[label])
        for label in pose_provenance.PROVIDER_SECTION_ORDER
        if label in sections
    ]


def _render_zero_loss_prompt(sections: list[tuple[str, str]]) -> str:
    labels = tuple(label for label, _ in sections)
    complete = pose_provenance.PROVIDER_SECTION_ORDER
    without_presence = tuple(label for label in complete if label != "Subject Presence")
    if labels not in (complete, without_presence):
        raise PromptBudgetAuditError("zero-loss sections do not use the complete canonical order")
    for label, body in sections:
        pose_provenance.validate_provider_body_text(
            body,
            label=f"zero-loss provider section {label}",
            max_chars=prompt_limits.PROVIDER_SECTION_BODY_MAX_CHARS,
        )
        if not body:
            raise PromptBudgetAuditError(f"zero-loss provider section {label} is empty")
    return "\n".join(f"[{label}]: {body}" for label, body in sections)


def assemble_zero_loss_prompt(
    recipe: dict[str, Any],
    pose_entry: dict[str, Any],
    retry_type: str,
    expression_entry: dict[str, Any] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    canonical_pose = _canonical_pose_entry(pose_entry)
    canonical_expression = _canonical_expression_entry(
        expression_entry or _default_audit_expression_entry()
    )
    base_sections = packet_builder.build_zero_loss_prompt_sections_for_budget_audit(
        recipe,
        canonical_pose["pose_text"],
        canonical_expression["expression_text"],
    )
    sections = _retry_sections(base_sections, retry_type)
    return _render_zero_loss_prompt(sections), sections


def audit_recipe_pose(
    recipe: dict[str, Any],
    pose_entry: dict[str, Any],
    expression_entry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    recipe_id = recipe.get("id")
    if not isinstance(recipe_id, str) or not recipe_id:
        raise PromptBudgetAuditError("every governed recipe requires a nonempty ID")
    canonical_pose = _canonical_pose_entry(pose_entry)
    canonical_expression = _canonical_expression_entry(
        expression_entry or _default_audit_expression_entry()
    )
    base_sections = packet_builder.build_zero_loss_prompt_sections_for_budget_audit(
        recipe,
        canonical_pose["pose_text"],
        canonical_expression["expression_text"],
    )
    execution_budget = prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    rows = []
    for retry_type in RETRY_TYPES:
        sections = _retry_sections(base_sections, retry_type)
        prompt = _render_zero_loss_prompt(sections)
        prompt_bytes = prompt.encode("utf-8")
        prompt_length = len(prompt)
        body_lengths = {label: len(body) for label, body in sections}
        rows.append({
            "recipe_id": recipe_id,
            "pose_body_language_id": canonical_pose["pose_body_language_id"],
            "pose_body_language_label": canonical_pose["pose_body_language_label"],
            "expression_gaze_id": canonical_expression["expression_gaze_id"],
            "expression_gaze_label": canonical_expression["expression_gaze_label"],
            "retry_type": retry_type,
            "assembled_prompt_length": prompt_length,
            "assembled_prompt_utf8_bytes": len(prompt_bytes),
            "assembled_prompt_sha256": _sha256_bytes(prompt_bytes),
            "execution_budget": execution_budget,
            "execution_budget_classification": prompt_limits.TEMPORARY_REPOSITORY_EXECUTION_POLICY,
            "fits_execution_budget": prompt_length <= execution_budget,
            "execution_headroom_chars": execution_budget - prompt_length,
            "excess_chars": max(0, prompt_length - execution_budget),
            "parser_safety_limit": prompt_limits.PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS,
            "fits_parser_safety_limit": (
                prompt_length <= prompt_limits.PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS
            ),
            "section_lengths": {
                label: body_lengths.get(label, 0)
                for label in pose_provenance.PROVIDER_SECTION_ORDER
            },
            "zero_loss": True,
        })
    return rows


def _semantic_evidence(source: str, text: str, prompt: str) -> dict[str, Any]:
    encoded = text.encode("utf-8")
    return {
        "source": source,
        "text": text,
        "chars": len(text),
        "utf8_bytes": len(encoded),
        "sha256": _sha256_bytes(encoded),
        "present_in_zero_loss_prompt": text in prompt,
    }


def build_hcr_012_semantic_inventory(
    recipe: dict[str, Any],
    pose_entry: dict[str, Any],
    expression_entry: dict[str, Any],
) -> dict[str, Any]:
    if recipe.get("id") != "hcr_012":
        raise PromptBudgetAuditError("hcr_012 semantic inventory requires recipe hcr_012")
    prompt, _ = assemble_zero_loss_prompt(
        recipe,
        pose_entry,
        FIRST_GENERATION,
        expression_entry,
    )
    scene_logic = recipe.get("scene_logic_contract") or {}
    evidence = {
        "identity": (
            ("structured_subject_brief", "Identity is fixed: preserve her approved adult slim-thick hourglass body and face."),
            ("structured_subject_brief", "Do not reinterpret her as a different person."),
        ),
        "body_silhouette": (
            ("structured_subject_brief", "Keep full natural lifted bust, defined waist, and wide hips."),
        ),
        "wardrobe": (
            ("recipe.fashion_accessories", recipe["fashion_accessories"]),
        ),
        "environment_exclusions": (
            ("recipe.setting_background", recipe["setting_background"]),
            ("recipe.scene_logic_contract.environment_realism_notes", scene_logic["environment_realism_notes"]),
        ),
        "realism": (
            ("recipe.style_lighting", recipe["style_lighting"]),
            ("structured_technical_realism", packet_builder.STRUCTURED_TECHNICAL_REALISM),
        ),
        "anti_plastic_skin": (
            ("structured_technical_realism", "Avoid plastic skin, beauty-filter poreless retouching"),
            ("recipe.negative_constraints", "No poreless or plastic skin."),
        ),
        "anti_identity_drift": (
            ("structured_technical_realism", "identity drift"),
        ),
        "anti_slimming": (
            ("structured_subject_brief", "Do not slim her into petite, narrow-hipped proportions."),
            ("structured_technical_realism", "body-slimming drift"),
        ),
        "negative_constraints": (
            ("recipe.negative_constraints", recipe["negative_constraints"]),
        ),
    }
    concepts = {}
    for concept, sources in evidence.items():
        items = [_semantic_evidence(source, text, prompt) for source, text in sources]
        concepts[concept] = {
            "must_survive_authored_migration": True,
            "all_current_evidence_present": all(item["present_in_zero_loss_prompt"] for item in items),
            "evidence": items,
        }
    return {
        "recipe_id": "hcr_012",
        "required_concepts": concepts,
        "all_required_concepts_present": all(
            item["all_current_evidence_present"] for item in concepts.values()
        ),
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_retry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_recipe: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_retry[row["retry_type"]].append(row)
        by_recipe[row["recipe_id"]].append(row)
    retry_summary = []
    for retry_type in RETRY_TYPES:
        retry_rows = by_retry[retry_type]
        retry_summary.append({
            "retry_type": retry_type,
            "combination_count": len(retry_rows),
            "fit_count": sum(row["fits_execution_budget"] for row in retry_rows),
            "over_budget_count": sum(not row["fits_execution_budget"] for row in retry_rows),
            "minimum_length": min(row["assembled_prompt_length"] for row in retry_rows),
            "maximum_length": max(row["assembled_prompt_length"] for row in retry_rows),
            "maximum_excess_chars": max(row["excess_chars"] for row in retry_rows),
        })
    recipe_summary = []
    for recipe_id in sorted(by_recipe):
        recipe_rows = by_recipe[recipe_id]
        first_rows = [row for row in recipe_rows if row["retry_type"] == FIRST_GENERATION]
        recipe_summary.append({
            "recipe_id": recipe_id,
            "pose_count": len(first_rows),
            "first_generation_minimum_length": min(row["assembled_prompt_length"] for row in first_rows),
            "first_generation_maximum_length": max(row["assembled_prompt_length"] for row in first_rows),
            "first_generation_over_budget_count": sum(
                not row["fits_execution_budget"] for row in first_rows
            ),
            "all_paths_maximum_length": max(row["assembled_prompt_length"] for row in recipe_rows),
            "all_paths_maximum_excess_chars": max(row["excess_chars"] for row in recipe_rows),
            "all_paths_over_budget_count": sum(
                not row["fits_execution_budget"] for row in recipe_rows
            ),
        })
    return {
        "combination_count": len(rows),
        "fit_count": sum(row["fits_execution_budget"] for row in rows),
        "over_budget_count": sum(not row["fits_execution_budget"] for row in rows),
        "parser_safety_over_budget_count": sum(
            not row["fits_parser_safety_limit"] for row in rows
        ),
        "by_retry_type": retry_summary,
        "by_recipe": recipe_summary,
    }


def build_audit_report(
    *,
    recipe_bank_path: Path = RECIPE_BANK,
    pose_bank_path: Path = POSE_BANK,
    expression_bank_path: Path = EXPRESSION_BANK,
) -> dict[str, Any]:
    recipe_bank, recipe_bytes = _read_json_object(recipe_bank_path)
    pose_bank, pose_bytes = _read_json_object(pose_bank_path)
    expression_bank, expression_bytes = _read_json_object(expression_bank_path)
    recipes = recipe_bank.get("recipes")
    poses = pose_bank.get("combos")
    expressions = expression_bank.get("combos")
    if not isinstance(recipes, list) or len(recipes) != EXPECTED_GOVERNED_RECIPE_COUNT:
        raise PromptBudgetAuditError(
            f"expected {EXPECTED_GOVERNED_RECIPE_COUNT} governed recipes"
        )
    if not isinstance(poses, list) or not poses:
        raise PromptBudgetAuditError("canonical pose bank must contain at least one pose")
    if not isinstance(expressions, list) or not expressions:
        raise PromptBudgetAuditError(
            "canonical expression bank must contain at least one expression"
        )
    recipe_ids = [recipe.get("id") for recipe in recipes if isinstance(recipe, dict)]
    if len(recipe_ids) != len(set(recipe_ids)):
        raise PromptBudgetAuditError("governed recipe IDs must be unique")
    canonical_poses = [_canonical_pose_entry(item) for item in poses]
    pose_ids = [item["pose_body_language_id"] for item in canonical_poses]
    if len(pose_ids) != len(set(pose_ids)):
        raise PromptBudgetAuditError("canonical pose IDs must be unique")
    canonical_expressions = [_canonical_expression_entry(item) for item in expressions]
    # The matrix remains recipe x pose x route. Use the longest canonical
    # expression as a deterministic conservative budget probe.
    audit_expression = max(
        canonical_expressions,
        key=lambda item: (len(item["expression_text"]), item["expression_gaze_id"]),
    )

    rows = []
    for recipe in recipes:
        if not isinstance(recipe, dict):
            raise PromptBudgetAuditError("governed recipes must be JSON objects")
        for pose in canonical_poses:
            rows.extend(audit_recipe_pose(recipe, pose, audit_expression))
    hcr_012 = next((recipe for recipe in recipes if recipe.get("id") == "hcr_012"), None)
    if hcr_012 is None:
        raise PromptBudgetAuditError("governed recipe hcr_012 is missing")

    return {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "writes_runtime_artifacts": False,
        "provider_call_enabled": False,
        "generation_call_enabled": False,
        "limits": prompt_limits.limit_classification_report(),
        "inputs": {
            "recipe_bank": {
                "path": RECIPE_BANK_REPO_PATH,
                "sha256": _sha256_bytes(recipe_bytes),
                "recipe_count": len(recipes),
            },
            "pose_bank": {
                "path": POSE_BANK_REPO_PATH,
                "sha256": _sha256_bytes(pose_bytes),
                "pose_count": len(canonical_poses),
            },
            "expression_bank": {
                "path": EXPRESSION_BANK_REPO_PATH,
                "sha256": _sha256_bytes(expression_bytes),
                "expression_count": len(canonical_expressions),
                "audit_expression_gaze_id": audit_expression[
                    "expression_gaze_id"
                ],
                "selection_policy": "longest_canonical_expression_then_id",
            },
        },
        "retry_types": list(RETRY_TYPES),
        "summary": _summarize_rows(rows),
        "hcr_012_semantic_inventory": build_hcr_012_semantic_inventory(
            hcr_012,
            canonical_poses[0],
            audit_expression,
        ),
        "rows": rows,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only zero-loss Lena provider prompt budget audit."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    report = build_audit_report()
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
