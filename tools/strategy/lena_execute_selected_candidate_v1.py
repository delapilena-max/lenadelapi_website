from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.influencer_nodes.lena import autonomy_ladder  # noqa: E402
from pipeline import higgsfield_lena_api_executor as executor  # noqa: E402
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector  # noqa: E402


SCHEMA_VERSION = "lena_execute_selected_candidate_v1"
ACCEPTED_FINAL_ACTION = "prepare_higgsfield_still_dry_run_for_review"
EXECUTOR_RELATIVE_PATH = "pipeline/higgsfield_lena_api_executor.py"
EXECUTOR_PATH = ROOT / EXECUTOR_RELATIVE_PATH
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXECUTOR_DRY_RUN_HEADER = "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ==="
EXECUTOR_PROVIDER_ARGV_HEADER = "provider argv (would be invoked under --live; prompt redacted for display):"
EXECUTOR_DRY_RUN_SENTINEL = "=== RESULT: no subprocess call, no network call, no file written. Dry-run only. ==="


class ConsumerError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _git_environment() -> dict[str, str]:
    return {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}


def _effective_root(root: Path | None) -> Path:
    return (root or ROOT).resolve()


def _git_bytes(*args: str, root: Path | None = None) -> bytes:
    effective_root = _effective_root(root)
    result = subprocess.run(
        ["git", *args],
        cwd=effective_root,
        check=False,
        capture_output=True,
        env=_git_environment(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConsumerError("authority_commit_invalid", detail or "git validation failed")
    return result.stdout


def _worktree_bytes_match_commit(
    commit: str,
    relative: str,
    current: bytes,
    *,
    root: Path | None = None,
) -> bool:
    # The selector hashes raw checkout bytes, which may be LF or CRLF even
    # when Git sees the file as unchanged. Compare Git-cleaned content to the
    # commit blob while retaining the artifact's exact raw-byte SHA check.
    effective_root = _effective_root(root)
    cleaned = subprocess.run(
        ["git", "hash-object", f"--path={relative}", "--stdin"],
        cwd=effective_root,
        check=False,
        input=current,
        capture_output=True,
        env=_git_environment(),
    )
    if cleaned.returncode != 0:
        raise ConsumerError("authority_commit_invalid", f"git could not clean authority input: {relative}")
    committed_blob = _git_bytes(
        "rev-parse",
        f"{commit}:{relative}",
        root=effective_root,
    ).strip()
    return cleaned.stdout.strip() == committed_blob


def _read_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConsumerError("decision_artifact_missing", f"decision artifact does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConsumerError("decision_artifact_malformed", f"could not read decision artifact: {exc}") from exc
    if not isinstance(value, dict):
        raise ConsumerError("decision_artifact_malformed", "decision artifact must be a JSON object")
    return value


def _decision_core(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in artifact.items()
        if key not in {"generated_at_utc", "decision_fingerprint_sha256"}
    }


def _validate_shape(artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("schema_version") != selector.SCHEMA_VERSION:
        raise ConsumerError("wrong_schema_version", "artifact is not a Lena pre-generation candidate decision")
    if str(artifact.get("influencer_id", "")).lower() != "lena":
        raise ConsumerError("wrong_influencer", "artifact influencer_id must be Lena")
    if artifact.get("candidate_status") != "selected":
        raise ConsumerError("candidate_not_selected", "candidate_status must be selected")
    if artifact.get("final_action") != ACCEPTED_FINAL_ACTION:
        raise ConsumerError("wrong_final_action", f"final_action must be {ACCEPTED_FINAL_ACTION!r}")
    if artifact.get("provider_authorized") is not False:
        raise ConsumerError("unexpected_provider_authorization", "provider_authorized must be false")
    if artifact.get("side_effects_performed") != []:
        raise ConsumerError("unexpected_prior_side_effects", "side_effects_performed must be an empty list")

    candidate = artifact.get("candidate")
    if not isinstance(candidate, dict):
        raise ConsumerError("candidate_missing", "selected decision must contain one candidate object")
    as_of_date = artifact.get("as_of_date")
    try:
        if not isinstance(as_of_date, str):
            raise ValueError
        date.fromisoformat(as_of_date)
    except ValueError as exc:
        raise ConsumerError("decision_date_invalid", "as_of_date must be a valid ISO date") from exc
    required = (
        "candidate_id", "slot_id", "lane", "recipe_id", "hook_id",
        "prompt_sha256", "exact_proposed_dry_run_command",
    )
    missing = [key for key in required if not candidate.get(key)]
    if missing:
        raise ConsumerError("candidate_identity_missing", f"candidate is missing required fields: {', '.join(missing)}")
    non_strings = [key for key in required if not isinstance(candidate[key], str)]
    if non_strings:
        raise ConsumerError("candidate_identity_invalid", f"candidate fields must be strings: {', '.join(non_strings)}")

    expected_candidate_id = f"{candidate['slot_id']}::{candidate['recipe_id']}::{candidate['hook_id']}"
    if candidate["candidate_id"] != expected_candidate_id:
        raise ConsumerError("candidate_id_mismatch", "candidate_id does not match slot, recipe, and hook identities")
    if not SHA256_RE.fullmatch(str(candidate["prompt_sha256"])):
        raise ConsumerError("prompt_sha_invalid", "prompt_sha256 must be a lowercase SHA-256 digest")

    expected_action = (
        f"python {EXECUTOR_RELATIVE_PATH} --date {as_of_date} "
        f"--slot-id {candidate['slot_id']}"
    )
    if candidate["exact_proposed_dry_run_command"] != expected_action:
        raise ConsumerError("executor_action_mismatch", "proposed Higgsfield dry-run action is not exact")
    if artifact.get("exact_next_allowed_action") != expected_action:
        raise ConsumerError("executor_action_mismatch", "top-level next action does not match the candidate action")
    return candidate


def _validate_fingerprint(artifact: dict[str, Any]) -> tuple[dict[str, Any], str]:
    stored = artifact.get("decision_fingerprint_sha256")
    if not isinstance(stored, str) or not SHA256_RE.fullmatch(stored):
        raise ConsumerError("decision_fingerprint_missing", "decision fingerprint is missing or invalid")
    core = _decision_core(artifact)
    recomputed = _sha256_bytes(selector._canonical_bytes(core))
    if recomputed != stored:
        raise ConsumerError("decision_fingerprint_mismatch", "stored decision fingerprint does not match immutable body")
    return core, recomputed


def _validate_authority(artifact: dict[str, Any], *, root: Path | None = None) -> None:
    effective_root = _effective_root(root)
    git_bytes = (
        (lambda *args: _git_bytes(*args))
        if root is None
        else (lambda *args: _git_bytes(*args, root=effective_root))
    )
    commit = artifact.get("authority_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ConsumerError("authority_commit_invalid", "authority_commit must be a full commit hash")
    object_type = git_bytes("cat-file", "-t", commit).decode(
        "ascii", errors="replace"
    ).strip()
    if object_type != "commit":
        raise ConsumerError("authority_commit_invalid", "authority_commit must identify a commit object exactly")
    resolved_commit = git_bytes(
        "rev-parse",
        "--verify",
        f"{commit}^{{commit}}",
    ).decode("ascii", errors="replace").strip()
    if resolved_commit != commit:
        raise ConsumerError("authority_commit_invalid", "authority_commit did not resolve to the exact commit")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=effective_root,
        check=False,
        capture_output=True,
        env=_git_environment(),
    )
    if ancestor.returncode != 0:
        raise ConsumerError("authority_commit_not_ancestor", "decision authority commit is not an ancestor of current HEAD")

    provenance = artifact.get("input_provenance")
    if not isinstance(provenance, list):
        raise ConsumerError("authority_provenance_invalid", "input_provenance must be a list")
    for relative in selector.AUTHORITY_PATHS:
        matches = [item for item in provenance if isinstance(item, dict) and item.get("path") == relative]
        if len(matches) != 1:
            raise ConsumerError("authority_provenance_invalid", f"canonical authority must appear exactly once: {relative}")
        recorded = matches[0].get("sha256")
        if not isinstance(recorded, str) or not SHA256_RE.fullmatch(recorded):
            raise ConsumerError("authority_provenance_invalid", f"invalid recorded SHA for {relative}")
        current_path = effective_root / relative
        if not current_path.is_file():
            raise ConsumerError("stale_canonical_authority", f"canonical authority is missing: {relative}")
        current = current_path.read_bytes()
        if _sha256_bytes(current) != recorded:
            raise ConsumerError("stale_canonical_authority", f"canonical authority changed; fresh selection required: {relative}")
        worktree_matches = (
            _worktree_bytes_match_commit(commit, relative, current)
            if root is None
            else _worktree_bytes_match_commit(
                commit,
                relative,
                current,
                root=effective_root,
            )
        )
        if not worktree_matches:
            raise ConsumerError("authority_commit_hash_mismatch", f"canonical authority content does not match {commit}: {relative}")


def _rebuild_current_decision(
    artifact: dict[str, Any],
    *,
    root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    effective_root = _effective_root(root)
    try:
        authorities = selector.load_authorities(effective_root)
        recent = selector.load_recent_content(effective_root)
        required_recipe_id = str(artifact.get("required_recipe_id") or "")
        prompt_candidates, prompt_meta = selector.build_prompt_candidates(
            artifact["as_of_date"],
            artifact["authority_commit"][:8],
            required_recipe_id=required_recipe_id,
        )
        candidate, rejected, _ = selector.select_candidate(
            authorities,
            prompt_candidates,
            recent,
            required_recipe_id=required_recipe_id,
        )
    except selector.GateError as exc:
        raise ConsumerError("stale_decision", f"selector revalidation failed: {exc.code}: {exc.detail}") from exc
    if candidate is None:
        raise ConsumerError("stale_decision", "current decision-critical evidence no longer selects a candidate")
    fresh_core = selector._decision_core(
        artifact["authority_commit"],
        artifact["as_of_date"],
        authorities,
        candidate,
        rejected,
        recent,
        prompt_meta,
        required_recipe_id=required_recipe_id,
    )
    return fresh_core, candidate


def _validate_regenerated_candidate(
    artifact: dict[str, Any],
    stored_core: dict[str, Any],
    candidate: dict[str, Any],
    *,
    root: Path | None = None,
) -> tuple[dict[str, Any], str]:
    fresh_core, selected = (
        _rebuild_current_decision(artifact)
        if root is None
        else _rebuild_current_decision(artifact, root=root)
    )
    fresh_fingerprint = _sha256_bytes(selector._canonical_bytes(fresh_core))
    # Selector internals may contain tuples that JSON persists as arrays.
    # Its canonical-byte contract, not Python container identity, is authoritative.
    if (
        fresh_fingerprint != artifact["decision_fingerprint_sha256"]
        or selector._canonical_bytes(fresh_core) != selector._canonical_bytes(stored_core)
    ):
        raise ConsumerError("stale_decision", "current decision-critical evidence does not reproduce the stored decision")

    for field in (
        "candidate_id", "slot_id", "lane", "recipe_id", "hook_id",
        "prompt_sha256", "expression_gaze_id", "expression_gaze_label",
        "expression_canonical_text", "expression_text",
        "expression_safe_fallback_used", "expression_safe_fallback_reason",
        "expression_scene_conflict_terms", "expression_derivation_scene_action",
    ):
        if candidate.get(field) != selected.get(field):
            raise ConsumerError(f"{field}_mismatch", f"stored {field} does not match current deterministic selection")

    try:
        required_recipe_id = str(artifact.get("required_recipe_id") or "")
        if required_recipe_id:
            source = executor.resolve_prompt_source(
                artifact["as_of_date"],
                candidate["slot_id"],
                required_recipe_id=required_recipe_id,
            )
        else:
            source = executor.resolve_prompt_source(
                artifact["as_of_date"], candidate["slot_id"]
            )
    except executor.PromptSourceError as exc:
        raise ConsumerError("slot_mismatch", str(exc)) from exc
    image = source.get("image", {})
    prompt = image.get("image_prompt")
    if not isinstance(prompt, str) or not prompt:
        raise ConsumerError("regenerated_prompt_missing", "executor did not regenerate a prompt")
    if image.get("slot_id") != candidate["slot_id"]:
        raise ConsumerError("slot_mismatch", "executor-resolved slot does not match decision")
    if image.get("lane") != candidate["lane"]:
        raise ConsumerError("lane_mismatch", "executor-resolved lane does not match decision")
    if selected.get("_prompt") != prompt:
        raise ConsumerError("regenerated_prompt_mismatch", "selector and executor regenerated different prompt bytes")
    prompt_sha = _sha256_bytes(prompt.encode("utf-8"))
    if prompt_sha != candidate["prompt_sha256"]:
        raise ConsumerError("prompt_sha_mismatch", "regenerated prompt SHA does not match decision")

    validation = executor.validate_candidate(source, None)
    if validation.get("ok") is not True:
        raise ConsumerError("executor_candidate_invalid", json.dumps(validation.get("all_reasons", [])))
    argv = executor.build_provider_argv(prompt, executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID)
    if argv.count(prompt) != 1 or "--wait" not in argv or "--json" not in argv:
        raise ConsumerError("executor_contract_mismatch", "executor provider action could not be reconstructed exactly")
    return validation, fresh_fingerprint


def validate_selected_candidate_issuance(
    artifact: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    candidate = _validate_shape(artifact)
    stored_core, recomputed = _validate_fingerprint(artifact)
    if root is None:
        _validate_authority(artifact)
        executor_validation, fresh_fingerprint = _validate_regenerated_candidate(
            artifact,
            stored_core,
            candidate,
        )
    else:
        _validate_authority(artifact, root=root)
        executor_validation, fresh_fingerprint = _validate_regenerated_candidate(
            artifact,
            stored_core,
            candidate,
            root=root,
        )
    return {
        "candidate": candidate,
        "stored_core": stored_core,
        "recomputed_fingerprint_sha256": recomputed,
        "fresh_fingerprint_sha256": fresh_fingerprint,
        "executor_validation": executor_validation,
    }


def _delegate_executor_dry_run(as_of_date: str, slot_id: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(EXECUTOR_PATH),
        "--date",
        as_of_date,
        "--slot-id",
        slot_id,
    ]
    if "--live" in command:
        raise ConsumerError("live_delegation_forbidden", "dry-run delegation cannot contain --live")
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConsumerError("executor_dry_run_failed", str(exc)) from exc
    if result.returncode != 0:
        raise ConsumerError("executor_dry_run_failed", result.stderr.strip() or result.stdout.strip())
    stdout_validation = _validate_executor_dry_run_stdout(result.stdout, as_of_date, slot_id)
    return {
        "returncode": result.returncode,
        "dry_run": True,
        "live_flag_present": False,
        **stdout_validation,
    }


def _validate_executor_dry_run_stdout(stdout: str, as_of_date: str, slot_id: str) -> dict[str, Any]:
    if not isinstance(stdout, str) or not stdout:
        raise ConsumerError("executor_dry_run_output_invalid", "executor dry-run stdout is empty or non-text")
    lines = stdout.splitlines()
    if not lines or lines[0] != EXECUTOR_DRY_RUN_HEADER:
        raise ConsumerError("executor_dry_run_output_invalid", "executor dry-run header is missing or malformed")
    if lines[-1] != EXECUTOR_DRY_RUN_SENTINEL:
        raise ConsumerError("executor_dry_run_output_invalid", "executor no-provider/no-write sentinel is missing or malformed")

    expected_lines = (
        f"date                    : {as_of_date}",
        f"slot_id                 : {slot_id}",
        "validation ok           : True",
        EXECUTOR_PROVIDER_ARGV_HEADER,
        (
            f"proposed output path    : {executor.library_path(as_of_date, slot_id, '.png')} "
            "(extension confirmed only on real download)"
        ),
        f"proposed manifest path  : {executor.manifest_path(as_of_date, slot_id)}",
    )
    for expected in expected_lines:
        if lines.count(expected) != 1:
            raise ConsumerError(
                "executor_dry_run_output_invalid",
                f"executor dry-run output must contain exactly one bound line: {expected}",
            )
    if lines.count(EXECUTOR_DRY_RUN_HEADER) != 1 or lines.count(EXECUTOR_DRY_RUN_SENTINEL) != 1:
        raise ConsumerError("executor_dry_run_output_invalid", "executor dry-run boundary lines are duplicated")
    return {
        "stdout_contract_validated": True,
        "stdout_sha256": _sha256_bytes(stdout.encode("utf-8")),
        "date_bound": as_of_date,
        "slot_id_bound": slot_id,
        "no_provider_no_write_sentinel_validated": True,
    }


def _authorization_requirement(artifact: dict[str, Any], candidate: dict[str, Any]) -> str:
    return (
        "Separate explicit Nicolas authorization is required for one future live Higgsfield invocation bound to "
        f"decision_fingerprint={artifact['decision_fingerprint_sha256']}, "
        f"slot_id={candidate['slot_id']}, prompt_sha256={candidate['prompt_sha256']}. "
        "No retry, fallback, second candidate, batch generation, or prompt mutation is authorized."
    )


def evaluate_decision(
    artifact_path: Path,
    *,
    live_requested: bool = False,
    dry_run_delegate: Callable[[str, str], dict[str, Any]] = _delegate_executor_dry_run,
) -> dict[str, Any]:
    try:
        autonomy_ladder.assert_allowed(
            "lena_execute_selected_candidate_v1",
            level=1,
            action="candidate generation only",
        )
    except autonomy_ladder.AutonomyLadderError as exc:
        raise ConsumerError(exc.code, exc.detail) from exc

    artifact = _read_artifact(artifact_path)
    issuance = validate_selected_candidate_issuance(artifact)
    candidate = issuance["candidate"]
    recomputed = issuance["recomputed_fingerprint_sha256"]
    executor_validation = issuance["executor_validation"]
    fresh_fingerprint = issuance["fresh_fingerprint_sha256"]

    validation_results = {
        "shape_valid": True,
        "fingerprint_valid": recomputed == fresh_fingerprint == artifact["decision_fingerprint_sha256"],
        "authority_commit_valid": True,
        "authority_inputs_current": True,
        "deterministic_reselection_match": True,
        "executor_prompt_regeneration_match": True,
        "executor_candidate_validation": executor_validation,
        "executor_dry_run_delegated": False,
    }
    state = "ready_for_live_authorization" if live_requested else "ready_for_executor_dry_run"
    blockers: list[str] = []
    if live_requested:
        blockers.append("separate_explicit_nicolas_authorization_required")
    else:
        validation_results["executor_dry_run"] = dry_run_delegate(artifact["as_of_date"], candidate["slot_id"])
        validation_results["executor_dry_run_delegated"] = True

    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "influencer_id": "lena",
        "decision_artifact_path": str(artifact_path.resolve()),
        "decision_fingerprint_sha256": artifact["decision_fingerprint_sha256"],
        "authority_commit": artifact["authority_commit"],
        "candidate_id": candidate["candidate_id"],
        "slot_id": candidate["slot_id"],
        "lane": candidate["lane"],
        "recipe_id": candidate["recipe_id"],
        "hook_id": candidate["hook_id"],
        "prompt_sha256": candidate["prompt_sha256"],
        "executor_path": EXECUTOR_RELATIVE_PATH,
        "executor_action": candidate["exact_proposed_dry_run_command"],
        "validation_results": validation_results,
        "blockers": blockers,
        "live_requested": live_requested,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "exact_next_allowed_action": _authorization_requirement(artifact, candidate),
        "side_effects_performed": [],
    }


def _blocked_report(path: Path, live_requested: bool, exc: ConsumerError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "blocked",
        "influencer_id": "lena",
        "decision_artifact_path": str(path.resolve()),
        "decision_fingerprint_sha256": None,
        "authority_commit": None,
        "candidate_id": None,
        "slot_id": None,
        "lane": None,
        "recipe_id": None,
        "hook_id": None,
        "prompt_sha256": None,
        "executor_path": EXECUTOR_RELATIVE_PATH,
        "executor_action": None,
        "validation_results": {"error_code": exc.code, "error_detail": exc.detail},
        "blockers": [exc.code],
        "live_requested": live_requested,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "exact_next_allowed_action": "Create a fresh autonomous selector decision after resolving the blocker.",
        "side_effects_performed": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one selected Lena candidate and delegate Higgsfield dry-run only.")
    parser.add_argument("--decision-artifact", required=True, type=Path)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Design boundary only: reports the exact separate authorization required and never calls the provider.",
    )
    args = parser.parse_args()
    try:
        report = evaluate_decision(args.decision_artifact, live_requested=args.live)
    except ConsumerError as exc:
        print(json.dumps(_blocked_report(args.decision_artifact, args.live, exc), sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
