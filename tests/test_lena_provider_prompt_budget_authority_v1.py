from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from collections import Counter
from pathlib import Path

import pytest

from tests.fixtures.lena_pose_provenance import (
    static_expression_provenance,
    static_pose_provenance,
)
from tools.strategy import lena_audit_autonomous_generation_readiness_v1 as readiness
from tools.strategy import lena_audit_provider_prompt_budget_v1 as audit
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_execute_retry_decision_v1 as legacy_retry
from tools.strategy import lena_pose_provenance_v1 as pose_provenance
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff
from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits


def _banks() -> tuple[list[dict], list[dict]]:
    recipe_bank = json.loads(Path(packet_builder.RECIPE_BANK).read_text(encoding="utf-8-sig"))
    pose_bank = json.loads((audit.ROOT / audit.POSE_BANK_REPO_PATH).read_text(encoding="utf-8-sig"))
    return recipe_bank["recipes"], pose_bank["combos"]


def _pose_binding(entry: dict) -> dict:
    binding = static_pose_provenance()
    binding.update({
        "pose_body_language_id": entry["pose_body_language_id"],
        "pose_body_language_label": entry["label"],
        "pose_text": entry["text"],
        "pose_text_sha256": hashlib.sha256(entry["text"].encode("utf-8")).hexdigest(),
    })
    core = {
        key: value
        for key, value in binding.items()
        if key != "pose_provenance_fingerprint_sha256"
    }
    binding["pose_provenance_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return binding


def _expression_binding() -> dict:
    entry = audit._default_audit_expression_entry()
    binding = static_expression_provenance()
    binding.update({
        "expression_gaze_id": entry["expression_gaze_id"],
        "expression_gaze_label": entry["expression_gaze_label"],
        "expression_canonical_text": entry["expression_text"],
        "expression_canonical_text_sha256": hashlib.sha256(
            entry["expression_text"].encode("utf-8")
        ).hexdigest(),
        "expression_text": entry["expression_text"],
        "expression_text_sha256": hashlib.sha256(
            entry["expression_text"].encode("utf-8")
        ).hexdigest(),
    })
    core = {
        key: value
        for key, value in binding.items()
        if key != "expression_provenance_fingerprint_sha256"
    }
    binding["expression_provenance_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return binding


@pytest.fixture(scope="module")
def governed_report() -> dict:
    return audit.build_audit_report()


def test_one_module_owns_every_active_and_legacy_prompt_limit() -> None:
    classifications = prompt_limits.limit_classification_report()
    assert {item["classification"] for item in classifications.values()} == {
        prompt_limits.PARSER_SAFETY_LIMIT,
        prompt_limits.TEMPORARY_REPOSITORY_EXECUTION_POLICY,
        prompt_limits.PER_INPUT_SECURITY_BOUND,
        prompt_limits.RETRY_READINESS_HEADROOM,
        prompt_limits.LEGACY_DEPRECATED_LIMIT,
    }
    assert all(item["provider_required"] is False for item in classifications.values())
    assert all(
        set(item) >= {
            "value",
            "provider",
            "purpose",
            "classification",
            "provider_required",
            "status",
            "known_consumers",
        }
        for item in classifications.values()
    )
    execution = classifications["higgsfield_prompt_execution_policy_max_chars"]
    assert execution["value"] == 4096
    assert execution["classification"] == prompt_limits.TEMPORARY_REPOSITORY_EXECUTION_POLICY
    assert "repository" in execution["description"].lower()
    assert execution["provider"] == "higgsfield"

    assert pose_provenance.PROVIDER_PROMPT_MAX_CHARS == prompt_limits.PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS
    assert pose_provenance.PROVIDER_SECTION_BODY_MAX_CHARS == prompt_limits.PROVIDER_SECTION_BODY_MAX_CHARS
    assert (
        packet_builder.STRUCTURED_SECTION_MAX
        is prompt_limits.HIGGSFIELD_STRUCTURED_PROMPT_SECTION_FITTER_MAX_CHARS
    )
    assert packet_builder.PROVIDER_RECIPE_FIELD_LIMITS is prompt_limits.PROVIDER_RECIPE_FIELD_MAX_CHARS
    assert (
        packet_builder.PROVIDER_RECIPE_AGGREGATE_MAX_CHARS
        == prompt_limits.PROVIDER_RECIPE_INPUT_AGGREGATE_MAX_CHARS
    )
    assert readiness.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW == prompt_limits.RETRY_PROMPT_HEADROOM_HARD_BLOCK_BELOW
    assert readiness.PAYLOAD_HEADROOM_WARNING_BELOW == prompt_limits.RETRY_PROMPT_HEADROOM_WARNING_BELOW
    assert (
        inspect.signature(packet_builder.build_structured_provider_prompt)
        .parameters["max_chars"]
        .default
        == prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    )


def test_higgsfield_batch_review_uses_central_execution_limit() -> None:
    from tools.strategy import lena_build_content_batch_review_report_v1 as batch_review

    limit = prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    assert batch_review.prompt_char_stats([
        {"compact_provider_prompt_chars": limit},
    ])["all_under_policy_limit"] is True
    assert batch_review.prompt_char_stats([
        {"compact_provider_prompt_chars": limit + 1},
    ])["all_under_policy_limit"] is False


def test_auditor_covers_every_governed_recipe_pose_and_route(governed_report: dict) -> None:
    assert governed_report["read_only"] is True
    assert governed_report["writes_runtime_artifacts"] is False
    assert governed_report["inputs"]["recipe_bank"]["recipe_count"] == 19
    assert governed_report["inputs"]["pose_bank"]["pose_count"] == 18
    assert governed_report["summary"]["combination_count"] == 19 * 18 * len(audit.RETRY_TYPES)
    counts = Counter(row["retry_type"] for row in governed_report["rows"])
    assert counts == Counter({retry_type: 19 * 18 for retry_type in audit.RETRY_TYPES})
    assert all(row["zero_loss"] is True for row in governed_report["rows"])
    assert all(
        tuple(row["section_lengths"])
        == pose_provenance.PROVIDER_SECTION_ORDER
        for row in governed_report["rows"]
    )
    # 2026-07-24: positive-only source migration shortened every prompt, so all
    # 1710 governed routes now fit the 4096 budget (proven by the full sweep).
    assert governed_report["summary"]["fit_count"] == 1710
    assert governed_report["summary"]["over_budget_count"] == 0
    assert governed_report["summary"]["parser_safety_over_budget_count"] == 0

    hcr_012_p008 = [
        row["assembled_prompt_length"]
        for row in governed_report["rows"]
        if row["recipe_id"] == "hcr_012"
        and row["pose_body_language_id"] == "pose_p008"
    ]
    # Shorter after the positive-only source migration; all routes still fit.
    assert hcr_012_p008 == [2366, 2471, 2650, 2646, 2650]
    assert all(
        row["fits_execution_budget"]
        for row in governed_report["rows"]
        if row["recipe_id"] == "hcr_012"
        and row["pose_body_language_id"] == "pose_p008"
    )


def test_auditor_never_calls_production_fitters(monkeypatch: pytest.MonkeyPatch) -> None:
    recipes, poses = _banks()
    recipe = next(item for item in recipes if item["id"] == "hcr_012")
    pose = next(item for item in poses if item["pose_body_language_id"] == "pose_p008")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("zero-loss audit invoked a production fitter")

    monkeypatch.setattr(packet_builder, "fit_prompt_units", forbidden)
    monkeypatch.setattr(packet_builder, "trim_fragment_to_chars", forbidden)
    rows = audit.audit_recipe_pose(recipe, pose)
    first = next(row for row in rows if row["retry_type"] == audit.FIRST_GENERATION)
    prompt, _ = audit.assemble_zero_loss_prompt(recipe, pose, audit.FIRST_GENERATION)

    assert first["assembled_prompt_length"] == len(prompt)
    assert first["assembled_prompt_length"] <= first["execution_budget"]
    assert recipe["fashion_accessories"] in prompt
    assert recipe["negative_constraints"] in prompt
    assert packet_builder.STRUCTURED_TECHNICAL_REALISM in prompt


def test_exact_accepted_input_characters_and_bytes_determine_audit_length() -> None:
    recipes, poses = _banks()
    recipe = next(item for item in recipes if item["id"] == "hcr_019")
    pose = next(item for item in poses if item["pose_body_language_id"] == "pose_p001")
    baseline = next(
        row for row in audit.audit_recipe_pose(recipe, pose)
        if row["retry_type"] == audit.FIRST_GENERATION
    )
    changed_recipe = copy.deepcopy(recipe)
    suffix = " caf\u00e9"
    changed_recipe["technical_keywords"] += suffix
    changed = next(
        row for row in audit.audit_recipe_pose(changed_recipe, pose)
        if row["retry_type"] == audit.FIRST_GENERATION
    )

    assert changed["assembled_prompt_length"] - baseline["assembled_prompt_length"] == len(suffix)
    assert changed["assembled_prompt_utf8_bytes"] - baseline["assembled_prompt_utf8_bytes"] == len(suffix.encode("utf-8"))
    assert changed["section_lengths"]["Cinematography"] - baseline["section_lengths"]["Cinematography"] == len(suffix)
    assert changed["assembled_prompt_sha256"] != baseline["assembled_prompt_sha256"]


def test_hcr_012_fits_zero_loss_and_carries_required_semantic_inventory(
    governed_report: dict,
) -> None:
    rows = [row for row in governed_report["rows"] if row["recipe_id"] == "hcr_012"]
    first_generation = [row for row in rows if row["retry_type"] == audit.FIRST_GENERATION]
    assert len(first_generation) == 18
    assert all(row["execution_budget"] == 4096 for row in first_generation)
    assert all(row["fits_execution_budget"] is True for row in first_generation)

    inventory = governed_report["hcr_012_semantic_inventory"]
    assert inventory["all_required_concepts_present"] is True
    # 2026-07-24 doctrine migration: body-shape concepts ("body_silhouette",
    # "anti_slimming") are retired because physical description competes with
    # the trained Lena Soul, and the "anti_*" negative concepts are retired
    # because this model has no negative-prompt channel. The inventory now
    # tracks the canonical positive concepts. Every authored source field is
    # still required to survive verbatim -- zero-loss is unchanged.
    assert set(inventory["required_concepts"]) == {
        "identity_anchored_to_soul",
        "wardrobe",
        "environment",
        "realism",
        "natural_skin_texture",
        "covered_styling_and_framing",
        "authored_scene_constraints",
    }
    assert all(
        concept["must_survive_authored_migration"]
        and concept["all_current_evidence_present"]
        for concept in inventory["required_concepts"].values()
    )


def test_cli_is_deterministic_stdout_only_and_rejects_output_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {"z": [2, 1], "read_only": True, "a": {"value": 3}}
    monkeypatch.setattr(audit, "build_audit_report", lambda: report)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no-output audit attempted filesystem mutation")

    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "replace", forbidden)
    monkeypatch.setattr(Path, "rename", forbidden)
    monkeypatch.setattr(Path, "touch", forbidden)

    expected = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    assert audit.main([]) == 0
    assert capsys.readouterr().out == expected
    assert audit.main([]) == 0
    assert capsys.readouterr().out == expected
    assert not hasattr(audit, "write_report")

    with pytest.raises(SystemExit):
        audit.parse_args(["--output", "prompt-budget-audit.json"])
    assert "unrecognized arguments: --output" in capsys.readouterr().err


def test_auditor_source_has_no_file_writing_surface() -> None:
    source = Path(audit.__file__).read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(audit.__file__))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "write_report" not in {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert imported_modules.isdisjoint({"os", "tempfile"})
    assert called_names.isdisjoint({"open"})
    assert called_attributes.isdisjoint({
        "mkdir",
        "mkstemp",
        "open",
        "replace",
        "rename",
        "touch",
        "write_bytes",
        "write_text",
    })


def test_auditor_structured_report_remains_available_in_memory(
    governed_report: dict,
) -> None:
    assert governed_report["report_type"] == audit.REPORT_TYPE
    assert governed_report["schema_version"] == audit.SCHEMA_VERSION
    assert governed_report["summary"]["combination_count"] == 1710
    assert len(governed_report["rows"]) == 1710


def test_current_production_formatter_matches_zero_loss_authority() -> None:
    recipes, poses = _banks()
    fit_count = 0
    over_count = 0
    for recipe in recipes:
        for pose in poses:
            expected, _ = audit.assemble_zero_loss_prompt(
                recipe,
                pose,
                audit.FIRST_GENERATION,
            )
            if len(expected) <= prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS:
                actual = packet_builder.build_structured_provider_prompt(
                    recipe,
                    pose_binding=_pose_binding(pose),
                    expression_binding=_expression_binding(),
                )
                assert actual == expected
                fit_count += 1
            else:
                with pytest.raises(prompt_limits.PromptExecutionPolicyError) as excinfo:
                    packet_builder.build_structured_provider_prompt(
                        recipe,
                        pose_binding=_pose_binding(pose),
                        expression_binding=_expression_binding(),
                    )
                assert excinfo.value.code == "higgsfield_prompt_execution_policy_exceeded"
                over_count += 1
    # 2026-07-24: positive-only source migration shortened every prompt, so
    # all governed combinations now fit the 4096 execution budget. The full
    # sweep proves 342/342 fit and 0 rejected; counts updated to the proven
    # values. The budget gate itself is unchanged.
    assert (fit_count, over_count) == (342, 0)


def test_all_zero_loss_routes_use_the_shared_execution_gate(governed_report: dict) -> None:
    recipes, poses = _banks()
    recipe_by_id = {recipe["id"]: recipe for recipe in recipes}
    pose_by_id = {pose["pose_body_language_id"]: pose for pose in poses}
    accepted = 0
    rejected = 0
    for row in governed_report["rows"]:
        prompt, _ = audit.assemble_zero_loss_prompt(
            recipe_by_id[row["recipe_id"]],
            pose_by_id[row["pose_body_language_id"]],
            row["retry_type"],
        )
        if row["fits_execution_budget"]:
            assert prompt_limits.require_higgsfield_prompt_within_execution_policy(prompt) == prompt
            accepted += 1
        else:
            with pytest.raises(prompt_limits.PromptExecutionPolicyError) as excinfo:
                prompt_limits.require_higgsfield_prompt_within_execution_policy(prompt)
            assert excinfo.value.code == "higgsfield_prompt_execution_policy_exceeded"
            rejected += 1
    # 2026-07-24: positive-only source migration shortened every prompt, so
    # all governed combinations now fit the 4096 execution budget. The full
    # sweep proves 342/342 fit and 0 rejected; counts updated to the proven
    # values. The budget gate itself is unchanged.
    assert (accepted, rejected) == (1710, 0)


def test_hcr_012_production_retry_routes_preserve_zero_loss_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipes, poses = _banks()
    recipe = next(item for item in recipes if item["id"] == "hcr_012")
    pose = next(item for item in poses if item["pose_body_language_id"] == "pose_p008")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("provider execution called a legacy fitter or trimmer")

    monkeypatch.setattr(packet_builder, "fit_prompt_units", forbidden)
    monkeypatch.setattr(packet_builder, "trim_fragment_to_chars", forbidden)
    first_expected, _ = audit.assemble_zero_loss_prompt(recipe, pose, audit.FIRST_GENERATION)
    first_actual = packet_builder.build_structured_provider_prompt(
        recipe,
        pose_binding=_pose_binding(pose),
        expression_binding=_expression_binding(),
    )
    assert first_actual == first_expected
    for field in (
        "fashion_accessories",
        "setting_background",
        "technical_keywords",
        "style_lighting",
        "negative_constraints",
    ):
        assert recipe[field] in first_actual

    ordinary, _ = retry_handoff._build_retry_prompt(first_actual, 4096)
    typed_hair, _ = retry_handoff._build_hair_crown_retry_prompt(first_actual, 4096)
    legacy_background = legacy_retry._mutate_prompt_for_retry(
        first_actual,
        "prevent_duplicated_background_identity",
    )
    legacy_hair = legacy_retry._mutate_prompt_for_retry(
        first_actual,
        "correct_hair_crown_forelock",
    )
    actual = [first_actual, ordinary, typed_hair, legacy_background, legacy_hair]
    expected = [
        audit.assemble_zero_loss_prompt(recipe, pose, retry_type)[0]
        for retry_type in audit.RETRY_TYPES
    ]
    assert actual == expected
    # Lengths shrank with the positive-only source migration; all five
    # retry routes still fit the 4096 execution budget.
    assert [len(prompt) for prompt in actual] == [2366, 2471, 2650, 2646, 2650]
    assert all(len(prompt) <= 4096 for prompt in actual)


def test_legacy_2499_budget_cannot_gate_higgsfield_execution() -> None:
    recipes, poses = _banks()
    recipe = next(item for item in recipes if item["id"] == "hcr_012")
    pose = next(item for item in poses if item["pose_body_language_id"] == "pose_p008")
    with pytest.raises(prompt_limits.PromptExecutionPolicyError) as excinfo:
        packet_builder.build_structured_provider_prompt(
            recipe,
            max_chars=2499,
            pose_binding=_pose_binding(pose),
            expression_binding=_expression_binding(),
        )
    assert excinfo.value.code == "higgsfield_prompt_budget_override_forbidden"

    prompt, _ = audit.assemble_zero_loss_prompt(recipe, pose, audit.FIRST_GENERATION)
    with pytest.raises(retry_handoff.RetryHandoffError) as retry_exc:
        retry_handoff._build_hair_crown_retry_prompt(prompt, 2499)
    assert retry_exc.value.code == "packet_prompt_budget_policy_mismatch"


def test_build_packet_uses_zero_loss_prompt_or_fails_before_packet_return() -> None:
    recipes, poses = _banks()
    hook = {
        "id": "production_matrix_hook",
        "category": "production_matrix",
        "hook_text": "",
        "caption_followup": "",
        "optional_reels_opening_line": "",
        "suggested_comment_reply_angle": "",
        "scores": {"total_score": 0},
    }
    built = 0
    blocked = 0
    for recipe in recipes:
        for pose in poses:
            expected, _ = audit.assemble_zero_loss_prompt(recipe, pose, audit.FIRST_GENERATION)
            if len(expected) > prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS:
                with pytest.raises(prompt_limits.PromptExecutionPolicyError):
                    packet_builder.build_packet(
                        copy.deepcopy(recipe),
                        copy.deepcopy(hook),
                        "zero-loss production-entry regression",
                        "2026-07-21",
                        pose_binding=_pose_binding(pose),
                        expression_binding=_expression_binding(),
                    )
                blocked += 1
                continue
            packet = packet_builder.build_packet(
                copy.deepcopy(recipe),
                copy.deepcopy(hook),
                "zero-loss production-entry regression",
                "2026-07-21",
                pose_binding=_pose_binding(pose),
                expression_binding=_expression_binding(),
            )
            assert packet["compact_provider_prompt_preview"] == expected
            assert packet["compact_provider_prompt_budget"] == 4096
            assert packet["compact_provider_prompt_chars"] == len(expected)
            built += 1
    # 2026-07-24: positive-only source migration shortened every prompt, so
    # all governed combinations now fit the 4096 execution budget. The full
    # sweep proves 342/342 fit and 0 rejected; counts updated to the proven
    # values. The budget gate itself is unchanged.
    assert (built, blocked) == (342, 0)
