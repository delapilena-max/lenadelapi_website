import copy
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.strategy import lena_execute_selected_candidate_v1 as consumer
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector


@pytest.fixture(scope="module")
def canonical_decision(tmp_path_factory):
    output = tmp_path_factory.mktemp("selected_decision")
    authority_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    provenance = []
    for relative in selector.AUTHORITY_PATHS:
        current = (ROOT / relative).read_bytes()
        provenance.append(
            {
                "path": relative,
                "sha256": consumer._sha256_bytes(current),
                "semantics": "canonical authority",
            }
        )
    candidate = {
        "candidate_id": "synthetic-pack000-00-photo::hcr_fixture::cbn_fixture",
        "slot_id": "synthetic-pack000-00-photo",
        "lane": "synthetic lane",
        "recipe_id": "hcr_fixture",
        "hook_id": "cbn_fixture",
        "prompt_sha256": consumer._sha256_bytes(b"synthetic prompt bytes"),
        "exact_proposed_dry_run_command": (
            "python pipeline/higgsfield_lena_api_executor.py --date 2026-07-13 "
            "--slot-id synthetic-pack000-00-photo"
        ),
    }
    core = {
        "schema_version": selector.SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": "2026-07-13",
        "authority_commit": authority_commit,
        "strategy_contract": {
            "canonical_niche": selector.CANONICAL_NICHE,
            "path": selector.AUTHORITY_PATHS[1],
        },
        "input_provenance": provenance,
        "candidate_status": "selected",
        "final_action": consumer.ACCEPTED_FINAL_ACTION,
        "candidate": candidate,
        "evidence": {
            "prompt_pack": {
                "pack_count": 1,
                "prompt_count": 1,
                "library_prefix": "synthetic",
                "prompt_identity_sha256": consumer._sha256_bytes(b"synthetic identity"),
                "curator_excluded_count": 0,
                "failure_memory_hard_excluded_patterns": [],
                "failure_memory_soft_flagged_patterns": [],
                "failure_memory_excluded_count": 0,
            },
            "recipe_binding_semantics": "strategy compatibility, not prompt provenance",
            "recent_content_evidence_semantics": "synthetic test fixture",
            "ranking_order": [],
            "tiebreak_label": "deterministic_noncreative_tiebreak",
        },
        "rejected_or_blocked_reasons": [],
        "confidence": "high",
        "noncritical_evidence_gaps": [],
        "failure_memory_inputs": {
            "semantics": "synthetic test fixture",
            "failure_memory_hard_excluded_patterns": [],
            "failure_memory_soft_flagged_patterns": [],
            "failure_memory_excluded_count": 0,
        },
        "recent_content_inputs": [],
        "expensive_video_boundary": "not evaluated; this gate selects an ordinary Higgsfield still only",
        "exact_next_allowed_action": candidate["exact_proposed_dry_run_command"],
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    artifact = dict(core)
    artifact["generated_at_utc"] = "2026-07-13T00:00:00Z"
    artifact["decision_fingerprint_sha256"] = consumer._sha256_bytes(
        selector._canonical_bytes(core)
    )
    path = output / "synthetic_selected_decision.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path, artifact


@pytest.fixture(autouse=True)
def synthetic_selection_runtime(monkeypatch, canonical_decision):
    artifact = canonical_decision[1]
    stored_core = consumer._decision_core(artifact)
    selected = dict(artifact["candidate"])
    selected["_prompt"] = "synthetic prompt bytes"
    source = {
        "resolver": "synthetic_test",
        "slot_prefix": "synthetic",
        "pack_count": 1,
        "image": {
            "slot_id": selected["slot_id"],
            "lane": selected["lane"],
            "image_prompt": selected["_prompt"],
        },
    }
    monkeypatch.setattr(consumer, "_rebuild_current_decision", lambda value: (stored_core, dict(selected)))
    monkeypatch.setattr(consumer.executor, "resolve_prompt_source", lambda date, slot: source)
    monkeypatch.setattr(
        consumer.executor,
        "validate_candidate",
        lambda source, expected_prompt_path: {
            "ok": True,
            "all_reasons": [],
            "prompt_matches_expected": True,
            "hard_exclude_reasons": [],
        },
    )
    monkeypatch.setattr(
        consumer.executor,
        "build_provider_argv",
        lambda prompt, custom_reference_id: [
            "higgsfield",
            "images",
            "generate",
            "--wait",
            "--json",
            prompt,
        ],
    )


def write_artifact(tmp_path, artifact, name="decision.json"):
    path = tmp_path / name
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def refingerprint(artifact):
    core = consumer._decision_core(artifact)
    artifact["decision_fingerprint_sha256"] = consumer._sha256_bytes(selector._canonical_bytes(core))
    return artifact


def accepted(path, **kwargs):
    return consumer.evaluate_decision(
        path,
        dry_run_delegate=lambda date, slot: {
            "returncode": 0,
            "dry_run": True,
            "live_flag_present": False,
            "date": date,
            "slot": slot,
        },
        **kwargs,
    )


def authentic_executor_stdout(date, slot):
    source = consumer.executor.resolve_prompt_source(date, slot)
    validation = consumer.executor.validate_candidate(source, None)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        consumer.executor.print_dry_run_report(
            date,
            slot,
            source,
            consumer.executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID,
            validation,
        )
    return output.getvalue()


def assert_blocked(path, code=None):
    with pytest.raises(consumer.ConsumerError) as error:
        accepted(path)
    if code:
        assert error.value.code == code
    return error.value


def test_valid_selected_artifact_is_accepted_and_exactly_bound(canonical_decision):
    path, artifact = canonical_decision
    report = accepted(path)
    candidate = artifact["candidate"]
    assert report["state"] == "ready_for_executor_dry_run"
    assert report["candidate_id"] == candidate["candidate_id"]
    assert report["slot_id"] == candidate["slot_id"]
    assert report["lane"] == candidate["lane"]
    assert report["recipe_id"] == candidate["recipe_id"]
    assert report["hook_id"] == candidate["hook_id"]
    assert report["prompt_sha256"] == candidate["prompt_sha256"]
    assert report["decision_fingerprint_sha256"] == artifact["decision_fingerprint_sha256"]


@pytest.mark.parametrize("status", ["abstain", "blocked", "not_selected"])
def test_non_selected_statuses_reject(canonical_decision, tmp_path, status):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact["candidate_status"] = status
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), "candidate_not_selected")


def test_null_candidate_rejects(canonical_decision, tmp_path):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact["candidate"] = None
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), "candidate_missing")


@pytest.mark.parametrize("invalid_date", [None, "2026-99-99"])
def test_invalid_decision_date_rejects(canonical_decision, tmp_path, invalid_date):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact["as_of_date"] = invalid_date
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), "decision_date_invalid")


def test_non_string_candidate_identity_rejects(canonical_decision, tmp_path):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact["candidate"]["lane"] = ["coffee shop"]
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), "candidate_identity_invalid")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("provider_authorized", True, "unexpected_provider_authorization"),
        ("side_effects_performed", ["provider_call"], "unexpected_prior_side_effects"),
        ("influencer_id", "other", "wrong_influencer"),
        ("schema_version", "wrong", "wrong_schema_version"),
        ("final_action", "generate_one", "wrong_final_action"),
    ],
)
def test_invalid_top_level_contract_rejects(canonical_decision, tmp_path, field, value, code):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact[field] = value
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), code)


@pytest.mark.parametrize("payload", ["{", "[]", "null"])
def test_malformed_or_non_object_artifact_rejects(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_text(payload, encoding="utf-8")
    assert_blocked(path, "decision_artifact_malformed")


def test_missing_artifact_rejects(tmp_path):
    assert_blocked(tmp_path / "missing.json", "decision_artifact_missing")


def test_missing_or_wrong_stored_fingerprint_rejects(canonical_decision, tmp_path):
    missing = copy.deepcopy(canonical_decision[1])
    missing.pop("decision_fingerprint_sha256")
    assert_blocked(write_artifact(tmp_path, missing, "missing.json"), "decision_fingerprint_missing")
    wrong = copy.deepcopy(canonical_decision[1])
    wrong["decision_fingerprint_sha256"] = "0" * 64
    assert_blocked(write_artifact(tmp_path, wrong, "wrong.json"), "decision_fingerprint_mismatch")


def test_altered_immutable_body_with_unchanged_fingerprint_rejects(canonical_decision, tmp_path):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact["evidence"]["recipe_binding_semantics"] = "tampered"
    assert_blocked(write_artifact(tmp_path, artifact), "decision_fingerprint_mismatch")


def test_authority_commit_must_be_full_real_commit(canonical_decision, tmp_path):
    artifact = copy.deepcopy(canonical_decision[1])
    artifact["authority_commit"] = "not-a-commit"
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), "authority_commit_invalid")


def test_authority_commit_ancestor_rule_is_fail_closed(canonical_decision, monkeypatch):
    artifact = canonical_decision[1]
    monkeypatch.setattr(
        consumer,
        "_git_bytes",
        lambda *args: b"commit\n" if args[:2] == ("cat-file", "-t") else (artifact["authority_commit"] + "\n").encode(),
    )

    class Result:
        returncode = 1

    monkeypatch.setattr(consumer.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(consumer.ConsumerError) as error:
        consumer._validate_authority(artifact)
    assert error.value.code == "authority_commit_not_ancestor"


def test_stale_canonical_hash_rejects(canonical_decision, tmp_path):
    artifact = copy.deepcopy(canonical_decision[1])
    authority = next(
        item for item in artifact["input_provenance"]
        if item["path"] == selector.AUTHORITY_PATHS[0]
    )
    authority["sha256"] = "0" * 64
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), "stale_canonical_authority")


def test_duplicate_or_missing_canonical_provenance_rejects(canonical_decision, tmp_path):
    duplicate = copy.deepcopy(canonical_decision[1])
    target = next(item for item in duplicate["input_provenance"] if item["path"] == selector.AUTHORITY_PATHS[0])
    duplicate["input_provenance"].append(copy.deepcopy(target))
    refingerprint(duplicate)
    assert_blocked(write_artifact(tmp_path, duplicate, "duplicate.json"), "authority_provenance_invalid")
    missing = copy.deepcopy(canonical_decision[1])
    missing["input_provenance"] = [item for item in missing["input_provenance"] if item["path"] != selector.AUTHORITY_PATHS[0]]
    refingerprint(missing)
    assert_blocked(write_artifact(tmp_path, missing, "missing.json"), "authority_provenance_invalid")


def test_unrelated_dirty_worktree_does_not_block(canonical_decision):
    report = accepted(canonical_decision[0])
    assert report["validation_results"]["authority_inputs_current"] is True
    source = Path(consumer.__file__).read_text(encoding="utf-8")
    assert "git status" not in source
    assert "diff --quiet" not in source


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda c: c.update(candidate_id="wrong"), "candidate_id_mismatch"),
        (lambda c: c.update(prompt_sha256="not-a-sha"), "prompt_sha_invalid"),
        (lambda c: c.update(exact_proposed_dry_run_command="python wrong.py"), "executor_action_mismatch"),
    ],
)
def test_candidate_identity_and_action_self_mismatch_rejects(canonical_decision, tmp_path, mutation, code):
    artifact = copy.deepcopy(canonical_decision[1])
    mutation(artifact["candidate"])
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact), code)


@pytest.mark.parametrize("field", ["slot_id", "lane", "recipe_id", "hook_id", "prompt_sha256"])
def test_candidate_binding_changes_reject_against_reselection(canonical_decision, tmp_path, field):
    artifact = copy.deepcopy(canonical_decision[1])
    candidate = artifact["candidate"]
    candidate[field] = "0" * 64 if field == "prompt_sha256" else f"changed-{field}"
    if field in {"slot_id", "recipe_id", "hook_id"}:
        candidate["candidate_id"] = f"{candidate['slot_id']}::{candidate['recipe_id']}::{candidate['hook_id']}"
    if field == "slot_id":
        action = f"python {consumer.EXECUTOR_RELATIVE_PATH} --date {artifact['as_of_date']} --slot-id {candidate['slot_id']}"
        candidate["exact_proposed_dry_run_command"] = action
        artifact["exact_next_allowed_action"] = action
    refingerprint(artifact)
    assert_blocked(write_artifact(tmp_path, artifact))


def test_regenerated_prompt_mismatch_rejects(canonical_decision, monkeypatch):
    artifact = canonical_decision[1]
    stored_core = consumer._decision_core(artifact)
    selected = copy.deepcopy(artifact["candidate"])
    selected["_prompt"] = "different prompt bytes"
    monkeypatch.setattr(consumer, "_rebuild_current_decision", lambda value: (stored_core, selected))
    with pytest.raises(consumer.ConsumerError) as error:
        consumer._validate_regenerated_candidate(artifact, stored_core, artifact["candidate"])
    assert error.value.code == "regenerated_prompt_mismatch"


def test_changed_decision_critical_evidence_blocks_as_stale(canonical_decision, monkeypatch):
    artifact = canonical_decision[1]
    stored_core = consumer._decision_core(artifact)
    changed_core = copy.deepcopy(stored_core)
    changed_core["candidate"]["lane"] = "different published-sequence choice"
    selected = copy.deepcopy(artifact["candidate"])
    monkeypatch.setattr(consumer, "_rebuild_current_decision", lambda value: (changed_core, selected))
    with pytest.raises(consumer.ConsumerError) as error:
        consumer._validate_regenerated_candidate(artifact, stored_core, artifact["candidate"])
    assert error.value.code == "stale_decision"


def test_unchanged_decision_critical_evidence_preserves_readiness(canonical_decision):
    report = accepted(canonical_decision[0])
    assert report["validation_results"]["deterministic_reselection_match"] is True
    assert report["validation_results"]["executor_prompt_regeneration_match"] is True


def test_exact_executor_action_is_reconstructed_and_dry_run_is_default(canonical_decision):
    calls = []

    def delegate(date, slot):
        calls.append((date, slot))
        return {"returncode": 0, "dry_run": True, "live_flag_present": False}

    report = consumer.evaluate_decision(canonical_decision[0], dry_run_delegate=delegate)
    assert calls == [(canonical_decision[1]["as_of_date"], canonical_decision[1]["candidate"]["slot_id"])]
    assert report["executor_action"] == canonical_decision[1]["candidate"]["exact_proposed_dry_run_command"]
    assert report["live_requested"] is False
    assert report["validation_results"]["executor_dry_run_delegated"] is True


def test_real_delegate_accepts_authentic_executor_output_without_live(canonical_decision, monkeypatch):
    calls = []
    date = canonical_decision[1]["as_of_date"]
    slot = canonical_decision[1]["candidate"]["slot_id"]

    class Result:
        returncode = 0
        stdout = authentic_executor_stdout(date, slot)
        stderr = ""

    monkeypatch.setattr(consumer.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or Result())
    result = consumer._delegate_executor_dry_run(date, slot)
    command, kwargs = calls[0]
    assert command[1] == str(consumer.EXECUTOR_PATH)
    assert command[-4:] == ["--date", date, "--slot-id", slot]
    assert "--live" not in command
    assert kwargs["check"] is False
    assert result["returncode"] == 0
    assert result["dry_run"] is True
    assert result["live_flag_present"] is False
    assert result["stdout_contract_validated"] is True
    assert result["date_bound"] == date
    assert result["slot_id_bound"] == slot
    assert result["no_provider_no_write_sentinel_validated"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda stdout, date, slot: "",
        lambda stdout, date, slot: "dry run",
        lambda stdout, date, slot: stdout.replace(
            f"date                    : {date}", "date                    : 2099-01-01"
        ),
        lambda stdout, date, slot: stdout.replace(
            f"slot_id                 : {slot}", "slot_id                 : wrong-slot"
        ),
        lambda stdout, date, slot: stdout.replace(consumer.EXECUTOR_DRY_RUN_SENTINEL, ""),
        lambda stdout, date, slot: " ".join(stdout.splitlines()),
    ],
    ids=["empty", "arbitrary", "wrong-date", "wrong-slot", "missing-sentinel", "malformed-lines"],
)
def test_zero_exit_malformed_executor_output_rejects(canonical_decision, monkeypatch, mutation):
    date = canonical_decision[1]["as_of_date"]
    slot = canonical_decision[1]["candidate"]["slot_id"]

    class Result:
        returncode = 0
        stdout = mutation(authentic_executor_stdout(date, slot), date, slot)
        stderr = ""

    calls = []
    monkeypatch.setattr(consumer.subprocess, "run", lambda *args, **kwargs: calls.append(args) or Result())
    with pytest.raises(consumer.ConsumerError) as error:
        consumer._delegate_executor_dry_run(date, slot)
    assert error.value.code == "executor_dry_run_output_invalid"
    assert len(calls) == 1


def test_nonzero_executor_exit_still_rejects_without_retry(canonical_decision, monkeypatch):
    date = canonical_decision[1]["as_of_date"]
    slot = canonical_decision[1]["candidate"]["slot_id"]

    class Result:
        returncode = 1
        stdout = authentic_executor_stdout(date, slot)
        stderr = "executor failed"

    calls = []
    monkeypatch.setattr(consumer.subprocess, "run", lambda *args, **kwargs: calls.append(args) or Result())
    with pytest.raises(consumer.ConsumerError) as error:
        consumer._delegate_executor_dry_run(date, slot)
    assert error.value.code == "executor_dry_run_failed"
    assert len(calls) == 1


def test_live_is_design_only_and_never_delegates(canonical_decision):
    def forbidden(*args):
        raise AssertionError("executor must not be delegated for --live in this slice")

    report = consumer.evaluate_decision(canonical_decision[0], live_requested=True, dry_run_delegate=forbidden)
    assert report["state"] == "ready_for_live_authorization"
    assert report["blockers"] == ["separate_explicit_nicolas_authorization_required"]
    assert report["live_requested"] is True
    assert report["provider_authorized"] is False
    assert report["provider_called"] is False
    assert report["generation_performed"] is False
    assert report["side_effects_performed"] == []


def test_authorization_requirement_is_exactly_candidate_bound(canonical_decision):
    report = accepted(canonical_decision[0])
    requirement = report["exact_next_allowed_action"]
    assert report["decision_fingerprint_sha256"] in requirement
    assert report["slot_id"] in requirement
    assert report["prompt_sha256"] in requirement
    assert "Separate explicit Nicolas authorization" in requirement
    assert "No retry" in requirement


def test_no_provider_generation_retry_fallback_or_downstream_side_effect_path_exists():
    source = Path(consumer.__file__).read_text(encoding="utf-8")
    assert "executor.run_live" not in source
    assert "requests." not in source
    assert "httpx." not in source
    assert "urllib.request" not in source
    assert "write_queue" not in source
    assert "publish(" not in source
    assert "approve(" not in source
    assert "analytics" not in source
    assert "learning" not in source
    assert "dotenv" not in source
    assert "retry" not in source.lower().replace("no retry", "")
    fallback_scan = source.lower().replace("no retry, fallback", "")
    for provenance_field in (
        "expression_safe_fallback_used",
        "expression_safe_fallback_reason",
    ):
        fallback_scan = fallback_scan.replace(provenance_field, "")
    assert "fallback" not in fallback_scan


def test_cli_emits_one_machine_readable_blocked_report(monkeypatch, capsys, tmp_path):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["consumer", "--decision-artifact", str(missing)])
    assert consumer.main() == 2
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    report = json.loads(lines[0])
    assert report["state"] == "blocked"
    assert report["provider_authorized"] is False
    assert report["provider_called"] is False
    assert report["generation_performed"] is False
    assert report["side_effects_performed"] == []


def test_recipe_remains_compatibility_evidence_not_generated_provenance(canonical_decision):
    report = accepted(canonical_decision[0])
    assert report["recipe_id"] == canonical_decision[1]["candidate"]["recipe_id"]
    encoded = json.dumps(report)
    assert "recipe_environment_id" not in encoded
    assert "generated_environment" not in encoded
