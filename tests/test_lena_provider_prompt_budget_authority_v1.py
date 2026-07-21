from __future__ import annotations

import copy
import hashlib
import inspect
import json
from collections import Counter
from pathlib import Path

import pytest

from tests.fixtures.lena_pose_provenance import static_pose_provenance
from tools.strategy import lena_audit_autonomous_generation_readiness_v1 as readiness
from tools.strategy import lena_audit_provider_prompt_budget_v1 as audit
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder
from tools.strategy import lena_pose_provenance_v1 as pose_provenance
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
    execution = classifications["temporary_provider_prompt_execution_max_chars"]
    assert execution["value"] == 2499
    assert execution["classification"] == prompt_limits.TEMPORARY_REPOSITORY_EXECUTION_POLICY
    assert "repository" in execution["description"].lower()

    assert pose_provenance.PROVIDER_PROMPT_MAX_CHARS == prompt_limits.PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS
    assert pose_provenance.PROVIDER_SECTION_BODY_MAX_CHARS == prompt_limits.PROVIDER_SECTION_BODY_MAX_CHARS
    assert packet_builder.STRUCTURED_SECTION_MAX is prompt_limits.LEGACY_STRUCTURED_SECTION_MAX_CHARS
    assert packet_builder.PROVIDER_RECIPE_FIELD_LIMITS is prompt_limits.PROVIDER_RECIPE_FIELD_MAX_CHARS
    assert (
        packet_builder.PROVIDER_RECIPE_AGGREGATE_MAX_CHARS
        == prompt_limits.PROVIDER_RECIPE_INPUT_AGGREGATE_MAX_CHARS
    )
    assert readiness.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW == prompt_limits.RETRY_PROMPT_HEADROOM_HARD_BLOCK_BELOW
    assert readiness.PAYLOAD_HEADROOM_WARNING_BELOW == prompt_limits.RETRY_PROMPT_HEADROOM_WARNING_BELOW
    assert (
        inspect.signature(packet_builder.build_structured_kling_prompt)
        .parameters["max_chars"]
        .default
        == prompt_limits.TEMPORARY_PROVIDER_PROMPT_EXECUTION_MAX_CHARS
    )


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
    assert first["assembled_prompt_length"] > first["execution_budget"]
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


def test_hcr_012_is_over_budget_and_carries_required_migration_inventory(
    governed_report: dict,
) -> None:
    rows = [row for row in governed_report["rows"] if row["recipe_id"] == "hcr_012"]
    first_generation = [row for row in rows if row["retry_type"] == audit.FIRST_GENERATION]
    assert len(first_generation) == 18
    assert all(row["execution_budget"] == 2499 for row in first_generation)
    assert all(row["fits_execution_budget"] is False for row in first_generation)

    inventory = governed_report["hcr_012_semantic_inventory"]
    assert inventory["all_required_concepts_present"] is True
    assert set(inventory["required_concepts"]) == {
        "identity",
        "body_silhouette",
        "wardrobe",
        "environment_exclusions",
        "realism",
        "anti_plastic_skin",
        "anti_identity_drift",
        "anti_slimming",
        "negative_constraints",
    }
    assert all(
        concept["must_survive_authored_migration"]
        and concept["all_current_evidence_present"]
        for concept in inventory["required_concepts"].values()
    )


def test_default_cli_is_stdout_only_and_explicit_temp_output_is_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(audit, "build_audit_report", lambda: {"read_only": True})
    monkeypatch.setattr(
        audit,
        "write_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected write")),
    )
    assert audit.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"read_only": True}

    monkeypatch.undo()
    output = tmp_path / "prompt-budget-audit.json"
    assert audit.write_report({"read_only": True}, output) == output.resolve()
    assert json.loads(output.read_text(encoding="utf-8")) == {"read_only": True}


def test_current_production_prompt_matrix_matches_reviewed_parent_baseline() -> None:
    recipes, poses = _banks()
    rows = []
    for recipe in recipes:
        for pose in poses:
            prompt = packet_builder.build_structured_kling_prompt(
                recipe,
                pose_binding=_pose_binding(pose),
            )
            rows.append([
                recipe["id"],
                pose["pose_body_language_id"],
                len(prompt),
                hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            ])
    matrix = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    assert len(rows) == 342
    assert hashlib.sha256(matrix).hexdigest() == (
        "57c3fa4d19e35c2092296d2fda5c8a5af3bfab67308f8da731da7e3fae8f693a"
    )
