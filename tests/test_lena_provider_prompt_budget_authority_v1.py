from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import json
import os
import subprocess
import sys
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
    assert execution["value"] == 2499
    assert execution["classification"] == prompt_limits.TEMPORARY_REPOSITORY_EXECUTION_POLICY
    assert "repository" in execution["description"].lower()
    assert execution["provider"] == "higgsfield"

    kling = classifications["kling_omni_payload_prompt_policy_max_chars"]
    assert kling["value"] == 2499
    assert kling["provider"] == "kling_omni"
    assert kling["provider_required"] is False
    assert set(kling["known_consumers"]) == {
        "tools/strategy/lena_build_kling_payload_dryrun_v1.py",
        "tools/strategy/lena_submit_kling_payload_v1.py",
        "tools/strategy/lena_build_content_batch_review_report_v1.py",
    }

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
        inspect.signature(packet_builder.build_structured_kling_prompt)
        .parameters["max_chars"]
        .default
        == prompt_limits.HIGGSFIELD_PROMPT_EXECUTION_POLICY_MAX_CHARS
    )


def test_active_kling_consumers_use_central_limits_without_numeric_duplicates() -> None:
    def load_worktree_module(name: str, relative_path: str):
        path = audit.ROOT / relative_path
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        original_sys_path = list(sys.path)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = original_sys_path
        return module

    kling_payload = load_worktree_module(
        "budget_review_kling_payload",
        "tools/strategy/lena_build_kling_payload_dryrun_v1.py",
    )
    kling_submit = load_worktree_module(
        "budget_review_kling_submit",
        "tools/strategy/lena_submit_kling_payload_v1.py",
    )
    batch_review = load_worktree_module(
        "budget_review_batch_report",
        "tools/strategy/lena_build_content_batch_review_report_v1.py",
    )

    assert (
        inspect.signature(kling_payload.fit_prompt_parts).parameters["max_chars"].default
        == prompt_limits.KLING_OMNI_PAYLOAD_PROMPT_POLICY_MAX_CHARS
    )
    assert batch_review.prompt_char_stats([
        {"compact_kling_prompt_chars": prompt_limits.KLING_OMNI_PAYLOAD_PROMPT_POLICY_MAX_CHARS},
    ])["all_under_2500"] is True
    assert batch_review.prompt_char_stats([
        {"compact_kling_prompt_chars": prompt_limits.KLING_OMNI_PAYLOAD_PROMPT_POLICY_MAX_CHARS + 1},
    ])["all_under_2500"] is False

    consumer_paths = (
        Path(kling_payload.__file__),
        Path(kling_submit.__file__),
        Path(batch_review.__file__),
        audit.ROOT / "tools" / "lena_influencer_node_v1_3.py",
    )
    forbidden_by_file = {
        "lena_build_kling_payload_dryrun_v1.py": {2499, 2500},
        "lena_submit_kling_payload_v1.py": {2499, 2500},
        "lena_build_content_batch_review_report_v1.py": {2499, 2500},
        "lena_influencer_node_v1_3.py": {1900, 2500},
    }
    for path in consumer_paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        integer_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and not isinstance(node.value, bool)
        }
        assert integer_literals.isdisjoint(forbidden_by_file[path.name]), path


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

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no-output audit attempted filesystem mutation")

    monkeypatch.setattr(audit, "write_report", forbidden)
    monkeypatch.setattr(audit.tempfile, "mkstemp", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert audit.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"read_only": True}

    monkeypatch.undo()
    output = tmp_path / "prompt-budget-audit.json"
    assert audit.write_report({"read_only": True}, output) == output.resolve()
    assert json.loads(output.read_text(encoding="utf-8")) == {"read_only": True}
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize(
    "output",
    (
        audit.ROOT / "prompt-budget-audit.json",
        Path(r"C:\projects\ai\content_bot\lenadelapi_website_autonomous_live\prompt-budget-audit.json"),
        Path(r"C:\projects\ai\content_bot\lenadelapi_website_pose_provenance_fix\prompt-budget-audit.json"),
        Path.home() / "prompt-budget-audit.json",
        Path("..") / "prompt-budget-audit.json",
    ),
)
def test_auditor_rejects_every_non_temporary_output(output: Path) -> None:
    with pytest.raises(audit.PromptBudgetAuditError):
        audit.write_report({"read_only": True}, output)


def test_auditor_requires_an_existing_temporary_parent(tmp_path: Path) -> None:
    output = tmp_path / "missing" / "prompt-budget-audit.json"
    with pytest.raises(audit.PromptBudgetAuditError):
        audit.write_report({"read_only": True}, output)
    assert not output.parent.exists()


def test_auditor_rejects_temporary_symlink_escape(tmp_path: Path) -> None:
    link = tmp_path / "escape"
    try:
        link.symlink_to(audit.ROOT, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    with pytest.raises(audit.PromptBudgetAuditError):
        audit.write_report({"read_only": True}, link / "prompt-budget-audit.json")


def test_auditor_rejects_temporary_windows_junction_escape(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction test")
    junction = tmp_path / "junction-escape"
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(audit.ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"directory junction creation is unavailable: {proc.stderr.strip()}")
    try:
        with pytest.raises(audit.PromptBudgetAuditError):
            audit.write_report(
                {"read_only": True},
                junction / "prompt-budget-audit.json",
            )
    finally:
        junction.rmdir()


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


def _build_packet_production_matrix() -> list[dict]:
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
    rows = []
    for recipe in recipes:
        for pose in poses:
            packet = packet_builder.build_packet(
                copy.deepcopy(recipe),
                copy.deepcopy(hook),
                "deterministic production-entry regression",
                "2026-07-21",
                pose_binding=_pose_binding(pose),
            )
            prompt = packet["compact_provider_prompt_preview"]
            rows.append({
                "recipe_id": recipe["id"],
                "pose_body_language_id": pose["pose_body_language_id"],
                "selected_production_budget": packet["compact_provider_prompt_budget"],
                "provider_prompt": prompt,
                "provider_prompt_sha256": packet["compact_provider_prompt_sha256"],
                "provider_prompt_chars": packet["compact_provider_prompt_chars"],
                "pose_provenance": packet["pose_provenance"],
                "generation_pose_contract": packet["generation_pose_contract"],
                "provider_prompt_contract": packet["provider_prompt_contract"],
            })
    return rows


def test_build_packet_production_matrix_matches_reviewed_parent_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Packet IDs, hook/caption copy, date-derived planning fields, and social
    # metadata are excluded because they do not influence provider prompt bytes,
    # budget selection, or pose binding. The production entry point still builds
    # them; the stable projection retains every prompt and pose authority field.
    monkeypatch.setattr(
        packet_builder,
        "save_packet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("production matrix attempted to write a packet")
        ),
    )
    rows = _build_packet_production_matrix()
    assert len(rows) == 342
    proof_budgets = {
        (row["recipe_id"], row["selected_production_budget"])
        for row in rows
        if row["recipe_id"] in {"hcr_007", "hcr_011", "hcr_012"}
    }
    assert proof_budgets == {
        (
            recipe_id,
            prompt_limits.HIGGSFIELD_PROOF_PACKET_PROMPT_BUDGET_WITH_ENVIRONMENT_CHARS,
        )
        for recipe_id in ("hcr_007", "hcr_011", "hcr_012")
    }
    for row in rows:
        prompt = row["provider_prompt"]
        assert row["provider_prompt_chars"] == len(prompt)
        assert row["provider_prompt_sha256"] == hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest()

    matrix = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    assert hashlib.sha256(matrix).hexdigest() == (
        "f42ad244b6484c9b03633051e341291c44d2d413d6b479afffa1e6dba4df5fc5"
    )
