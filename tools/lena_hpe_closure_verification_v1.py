from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_engine_closure_v1 as closure_schema  # noqa: E402
from pipeline.presence import human_presence_closure_evidence_v1 as closure_evidence  # noqa: E402
from tools.lena_run_hpe_controlled_proof_v1 import _load_json_object, _repo_relative_path, _sha256_file  # noqa: E402
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector  # noqa: E402


class HPEClosureVerificationError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_rev_parse(ref: str) -> str:
    result = subprocess.run(["git", "rev-parse", ref], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _git_merge_base(left: str, right: str) -> str:
    result = subprocess.run(["git", "merge-base", left, right], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _resolve_base_commit_sha() -> str:
    for base_ref in ("origin/main", "origin/HEAD"):
        try:
            return _git_merge_base("HEAD", base_ref)
        except subprocess.CalledProcessError:
            continue
    try:
        return _git_rev_parse("HEAD^")
    except subprocess.CalledProcessError:
        return _git_rev_parse("HEAD")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    payload_bytes = serialized.encode("utf-8")
    if path.exists():
        if path.read_bytes() == payload_bytes:
            return
        raise HPEClosureVerificationError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        handle.write(payload_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temp_path.replace(path)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
        except OSError:
            dir_fd = None
        try:
            if dir_fd is not None:
                os.fsync(dir_fd)
        finally:
            if dir_fd is not None:
                os.close(dir_fd)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _locate_proof_report(output_root: Path) -> Path:
    candidates = sorted(
        path for path in output_root.rglob("lena_hpe_controlled_proof_*.json") if path.is_file()
    )
    if not candidates:
        raise HPEClosureVerificationError("proof_report_missing", f"no controlled-proof report was found under {output_root}")
    if len(candidates) > 1:
        raise HPEClosureVerificationError("proof_report_ambiguous", "multiple controlled-proof reports were found")
    return candidates[0]


def _closure_report_path(output_root: Path, proof_report: dict[str, Any]) -> Path:
    return output_root / str(proof_report["date"]) / str(proof_report["slot_id"]) / (
        f"lena_hpe_closure_verification_{proof_report['slot_id']}_{int(proof_report['image_index']):02d}.json"
    )


def _normalise_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _proof_path_text(path_value: str | Path | None) -> str:
    if path_value is None:
        return ""
    return _normalise_path(str(path_value)).as_posix()


def _proof_text_value(value: Any) -> str:
    return str(value or "")


def _proof_sidecar_path(proof_report_path: Path, proof_report: dict[str, Any], prefix: str) -> Path:
    return proof_report_path.with_name(f"{prefix}_{proof_report['slot_id']}_{int(proof_report['image_index']):02d}.json")


def _validate_failure_indicators_qa_only(proof_report: dict[str, Any]) -> None:
    prompt_plan = proof_report.get("prompt_plan_evidence", {})
    if not isinstance(prompt_plan, dict):
        raise HPEClosureVerificationError("prompt_plan_invalid", "prompt_plan_evidence must be an object")
    prompt_text = str(prompt_plan.get("prompt_text") or "")
    if "presence-failure avoidance" in prompt_text:
        raise HPEClosureVerificationError("prompt_regression_detected", "failure indicators leaked into provider-facing prompt text")
    indicators = prompt_plan.get("failure_indicators")
    if not isinstance(indicators, list) or not all(isinstance(item, str) and item.strip() for item in indicators):
        raise HPEClosureVerificationError("prompt_plan_invalid", "failure indicators must remain a non-empty QA-only list")


def _validate_prompt_influence_evidence(proof_report: dict[str, Any]) -> None:
    evidence = proof_report.get("final_prompt_influence_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise HPEClosureVerificationError("prompt_influence_invalid", "final_prompt_influence_evidence must be a non-empty list")
    required_fields = {
        "viewer_relationship.awareness",
        "gaze_arc.start_focus",
        "expression_arc.peak_state",
        "performance_actions.primary_action",
        "performance_actions.object_interaction",
        "performance_actions.movement_motivation",
        "movement_dynamics.weight_transfer",
        "sensual_presence.tier",
        "body_presentation.framing_intent",
        "failure_indicators",
    }
    seen_fields = set()
    baseline_sha = None
    for entry in evidence:
        if not isinstance(entry, dict):
            raise HPEClosureVerificationError("prompt_influence_invalid", "prompt influence entries must be objects")
        field_path = str(entry.get("field_path") or "")
        if field_path not in required_fields:
            raise HPEClosureVerificationError("prompt_influence_invalid", f"unsupported prompt influence field {field_path!r}")
        seen_fields.add(field_path)
        entry_baseline = str(entry.get("baseline_prompt_sha256") or "")
        entry_mutated = str(entry.get("mutated_prompt_sha256") or "")
        if len(entry_baseline) != 64 or len(entry_mutated) != 64:
            raise HPEClosureVerificationError("prompt_influence_invalid", "prompt influence hashes must be sha256 values")
        if baseline_sha is None:
            baseline_sha = entry_baseline
        elif entry_baseline != baseline_sha:
            raise HPEClosureVerificationError("prompt_influence_invalid", "prompt influence baseline sha must be stable")
        if field_path == "failure_indicators":
            if entry.get("prompt_changed") is not False:
                raise HPEClosureVerificationError("prompt_influence_invalid", "failure indicators may not change the provider-facing prompt")
            if entry_baseline != entry_mutated:
                raise HPEClosureVerificationError("prompt_influence_invalid", "failure indicators must remain prompt-neutral")
        else:
            if entry.get("prompt_changed") is not True:
                raise HPEClosureVerificationError("prompt_influence_invalid", f"{field_path} must change the provider-facing prompt")
            if entry_baseline == entry_mutated:
                raise HPEClosureVerificationError("prompt_influence_invalid", f"{field_path} must change the provider-facing prompt sha256")
    if seen_fields != required_fields:
        raise HPEClosureVerificationError("prompt_influence_invalid", "prompt influence coverage is incomplete")


def _validate_artifact_hashes(proof_report: dict[str, Any]) -> None:
    artifact_paths = proof_report.get("required_artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise HPEClosureVerificationError("artifact_paths_invalid", "required_artifact_paths must be an object")
    candidate_path_value = str(proof_report.get("selected_candidate_artifact_path") or artifact_paths.get("candidate_decision") or "")
    candidate_path = _normalise_path(candidate_path_value)
    manifest_path = _normalise_path(str(artifact_paths.get("manifest") or ""))
    image_path = _normalise_path(str(artifact_paths.get("image") or ""))
    qa_path = _normalise_path(str(artifact_paths.get("qa_artifact") or ""))
    for path in (candidate_path, manifest_path, image_path, qa_path):
        if not path.is_file():
            raise HPEClosureVerificationError("artifact_missing", f"required artifact is missing: {path}")

    proof_candidate_sha = str(proof_report.get("selected_candidate_artifact_sha256") or "")
    proof_image_sha = str(proof_report.get("image_sha256") or "")
    proof_manifest_sha = str(proof_report.get("manifest_sha256") or "")
    proof_prompt_sha = str(proof_report.get("prompt_package", {}).get("image_prompt_sha256") or "")
    if _sha256_file(candidate_path) != proof_candidate_sha:
        raise HPEClosureVerificationError("artifact_integrity_mismatch", "candidate decision sha256 mismatch")
    if _sha256_file(image_path) != proof_image_sha:
        raise HPEClosureVerificationError("artifact_integrity_mismatch", "generated image sha256 mismatch")
    if _sha256_file(manifest_path) != proof_manifest_sha:
        raise HPEClosureVerificationError("artifact_integrity_mismatch", "manifest sha256 mismatch")
    if not proof_prompt_sha or len(proof_prompt_sha) != 64:
        raise HPEClosureVerificationError("artifact_integrity_mismatch", "prompt package sha256 is missing")

    qa_artifact = _load_json_object(qa_path)
    if qa_artifact != proof_report.get("qa_artifact"):
        raise HPEClosureVerificationError("artifact_integrity_mismatch", "qa artifact payload does not match the proof report")


def _load_optional_sidecar_artifact(
    *,
    proof_report_path: Path,
    proof_report: dict[str, Any],
    prefix: str,
) -> tuple[Path, dict[str, Any]] | None:
    pattern = f"{prefix}_{proof_report['slot_id']}_{int(proof_report['image_index']):02d}.json"
    candidates = sorted(path for path in proof_report_path.parent.rglob(pattern) if path.is_file())
    if not candidates:
        return None
    if len(candidates) > 1:
        raise HPEClosureVerificationError("sidecar_ambiguous", f"multiple {prefix} sidecars were found")
    return candidates[0], _load_json_object(candidates[0])


def _proof_identity_section(proof_identity: dict[str, Any] | None, section: str) -> dict[str, Any]:
    if not isinstance(proof_identity, dict):
        raise HPEClosureVerificationError("proof_identity_missing", f"{section} binding metadata is required")
    identity = proof_identity.get(section)
    if not isinstance(identity, dict):
        raise HPEClosureVerificationError("proof_identity_missing", f"{section} binding metadata is required")
    return identity


def _assert_expected_value(actual: Any, expected: Any, *, code: str, detail: str) -> None:
    if expected is None:
        raise HPEClosureVerificationError(code, detail)
    if actual != expected:
        raise HPEClosureVerificationError(code, detail)


def _normalised_repo_path(path_value: str | Path | None) -> str:
    if path_value is None:
        return ""
    path = Path(path_value)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path.as_posix()


def _validate_authority_and_lane(proof_report: dict[str, Any], *, authority_commit_expected: str) -> dict[str, str]:
    selected = proof_report.get("selected_candidate_evidence", {})
    if not isinstance(selected, dict):
        raise HPEClosureVerificationError("selected_candidate_invalid", "selected_candidate_evidence must be an object")
    if selected.get("provider_called") is not False:
        raise HPEClosureVerificationError("authority_invariant_failed", "provider calls are not allowed in the proof lane")
    if selected.get("provider_authorized") is not False:
        raise HPEClosureVerificationError("authority_invariant_failed", "provider authorization is not allowed in the proof lane")
    if selected.get("side_effects_performed") not in ([], None):
        raise HPEClosureVerificationError("authority_invariant_failed", "proof lane side effects must be empty")
    if proof_report.get("provider_call_performed") is not False:
        raise HPEClosureVerificationError("authority_invariant_failed", "proof report must record provider_call_performed=false")
    if proof_report.get("provider_authorized") is not False:
        raise HPEClosureVerificationError("authority_invariant_failed", "proof report must record provider_authorized=false")
    if proof_report.get("side_effects_performed") not in ([], None):
        raise HPEClosureVerificationError("authority_invariant_failed", "proof report side effects must be empty")

    authority_commit = str(proof_report.get("authority_commit") or "")
    if authority_commit != authority_commit_expected:
        raise HPEClosureVerificationError("authority_commit_mismatch", "proof authority_commit does not match the expected head")
    if str(selected.get("authority_commit") or authority_commit) != authority_commit_expected:
        raise HPEClosureVerificationError("authority_commit_mismatch", "selected candidate authority_commit does not match the expected head")

    lane_type = str(proof_report.get("lane_type") or "")
    if lane_type not in closure_schema.LANE_VALUES:
        raise HPEClosureVerificationError("lane_type_invalid", "proof lane_type is invalid")
    controlled_result = proof_report.get("controlled_proof_result", {})
    if not isinstance(controlled_result, dict):
        raise HPEClosureVerificationError("controlled_proof_invalid", "controlled_proof_result must be an object")
    if controlled_result.get("authority_commit") not in (authority_commit_expected, None):
        raise HPEClosureVerificationError("authority_commit_mismatch", "controlled proof result authority_commit does not match the expected head")
    if controlled_result.get("side_effects_performed") not in ([], None):
        raise HPEClosureVerificationError("controlled_proof_invalid", "controlled proof result side effects must be empty")
    if controlled_result.get("provider_call_performed") is not False or controlled_result.get("provider_authorized") is not False:
        raise HPEClosureVerificationError("controlled_proof_invalid", "controlled proof result must remain provider-free")
    if lane_type == "controlled_proof" and controlled_result.get("ordinary_lane_readiness") != "not_applicable":
        raise HPEClosureVerificationError("controlled_proof_invalid", "controlled proof must not self-certify ordinary lane readiness")
    return {"lane_type": lane_type, "authority_commit": authority_commit}


def _derive_mandatory_condition_results(
    proof_report: dict[str, Any],
    *,
    authority_commit_expected: str,
    proof_report_path: Path,
    proof_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    lane_info = _validate_authority_and_lane(proof_report, authority_commit_expected=authority_commit_expected)
    _validate_failure_indicators_qa_only(proof_report)
    _validate_prompt_influence_evidence(proof_report)
    _validate_artifact_hashes(proof_report)

    semantic_config = proof_report.get("semantic_qa_configuration", {})
    semantic_evidence = proof_report.get("semantic_qa_evidence", {})
    lifecycle_evidence = proof_report.get("lifecycle_report_evidence", {})
    integrity_evidence = proof_report.get("integrity_qa_evidence", {})
    if not isinstance(semantic_config, dict) or not isinstance(semantic_evidence, dict) or not isinstance(lifecycle_evidence, dict):
        raise HPEClosureVerificationError("evidence_invalid", "semantic or lifecycle evidence is malformed")
    if not isinstance(integrity_evidence, dict):
        raise HPEClosureVerificationError("evidence_invalid", "integrity evidence is malformed")

    condition_results: dict[str, Any] = {condition_id: "not_verified" for condition_id in closure_schema.MANDATORY_CONDITION_IDS}
    condition_results["connected_path_runtime_verification"] = "verified"
    condition_results["supported_prompt_influence_verification"] = "verified"
    condition_results["failure_indicator_qa_only_verification"] = "verified"
    condition_results["authority_invariance_verification"] = "verified"
    condition_results["artifact_integrity_verification"] = "verified"
    lane_applicability = closure_schema.lane_condition_applicability(lane_info["lane_type"])
    if lane_applicability["provider_free_controlled_proof"]:
        condition_results["provider_free_controlled_proof"] = "verified"
    else:
        condition_results["provider_free_controlled_proof"] = closure_schema.condition_result("not_applicable")

    live_review = bool(semantic_config.get("live_presence_semantic_review"))
    if lane_applicability["controlled_live_semantic_proof_receipt"]:
        if live_review:
            if semantic_evidence.get("semantic_result_provenance") is None:
                raise HPEClosureVerificationError("semantic_receipt_missing", "live semantic proof receipt is missing")
            condition_results["controlled_live_semantic_proof_receipt"] = "verified"
        else:
            manual_semantic = _load_optional_sidecar_artifact(
                proof_report_path=proof_report_path,
                proof_report=proof_report,
                prefix="lena_hpe_manual_semantic_review",
            )
            if manual_semantic is not None:
                manual_path, manual_artifact = manual_semantic
                normalized_manual = closure_evidence.validate_manual_semantic_review_artifact(manual_artifact)
                manual_identity = _proof_identity_section(proof_identity, "manual_semantic_review")
                expected_candidate_path = _proof_path_text(manual_identity.get("candidate_artifact_path"))
                expected_reviewed_image_path = _proof_path_text(manual_identity.get("reviewed_image_path"))
                expected_prompt_sha = _proof_text_value(manual_identity.get("prompt_sha256"))
                expected_receipt_path = _proof_path_text(manual_identity.get("execution_receipt_artifact_path"))
                expected_receipt_sha = _proof_text_value(manual_identity.get("execution_receipt_artifact_sha256"))
                expected_provider_job_id = _proof_text_value(manual_identity.get("provider_job_id"))
                expected_slot_id = _proof_text_value(manual_identity.get("slot_id"))
                expected_authority_commit = _proof_text_value(manual_identity.get("authority_commit"))
                if expected_candidate_path and _normalised_repo_path(normalized_manual["candidate_artifact_path"]) != _normalised_repo_path(expected_candidate_path):
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review candidate path does not match the proof context")
                if expected_reviewed_image_path and _normalised_repo_path(normalized_manual["reviewed_image_path"]) != _normalised_repo_path(expected_reviewed_image_path):
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review image path does not match the proof context")
                if expected_prompt_sha and normalized_manual["prompt_sha256"] != expected_prompt_sha:
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review prompt sha256 does not match the proof context")
                if expected_receipt_path and _normalised_repo_path(normalized_manual["execution_receipt_artifact_path"]) != _normalised_repo_path(expected_receipt_path):
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review receipt path does not match the proof context")
                if expected_receipt_sha and normalized_manual["execution_receipt_artifact_sha256"] != expected_receipt_sha:
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review receipt sha256 does not match the proof context")
                if expected_provider_job_id and normalized_manual.get("provider_job_id") != expected_provider_job_id:
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review provider job id does not match the proof context")
                if expected_slot_id and str(proof_report.get("selected_candidate_slot_id") or proof_report.get("slot_id") or "") != expected_slot_id:
                    raise HPEClosureVerificationError("manual_semantic_review_mismatch", "manual semantic review slot does not match the proof context")
                if normalized_manual["disposition"] == "accepted_for_hpe_closure":
                    if normalized_manual["candidate_artifact_sha256"] != str(proof_report.get("selected_candidate_artifact_sha256") or ""):
                        raise HPEClosureVerificationError(
                            "manual_semantic_review_mismatch",
                            "manual semantic review candidate sha256 does not match the proof report",
                        )
                    if normalized_manual["reviewed_image_sha256"] != str(proof_report.get("image_sha256") or ""):
                        raise HPEClosureVerificationError(
                            "manual_semantic_review_mismatch",
                            "manual semantic review image sha256 does not match the proof report",
                        )
                    if normalized_manual["authority_commit_final"] != expected_authority_commit or normalized_manual["authority_commit_expected"] != expected_authority_commit:
                        raise HPEClosureVerificationError(
                            "manual_semantic_review_mismatch",
                            "manual semantic review authority commit does not match the proof authority",
                        )
                    if normalized_manual.get("evidence_source") != closure_evidence.MANUAL_SEMANTIC_EVIDENCE_SOURCE:
                        raise HPEClosureVerificationError(
                            "manual_semantic_review_mismatch",
                            "manual semantic review evidence source does not match the required label",
                        )
                    condition_results["controlled_live_semantic_proof_receipt"] = "verified"
                    semantic_evidence["semantic_review_source"] = normalized_manual["evidence_source"]
                    semantic_evidence["manual_semantic_review_artifact_path"] = str(manual_path)
                else:
                    condition_results["controlled_live_semantic_proof_receipt"] = "not_verified"
            else:
                condition_results["controlled_live_semantic_proof_receipt"] = "not_verified"
    else:
        condition_results["controlled_live_semantic_proof_receipt"] = closure_schema.condition_result("not_applicable")

    if lane_applicability["ordinary_lane_proof"]:
        if lane_info["lane_type"] == "ordinary_lane":
            ordinary_semantic = _load_optional_sidecar_artifact(
                proof_report_path=proof_report_path,
                proof_report=proof_report,
                prefix="lena_hpe_ordinary_lane_proof",
            )
            if ordinary_semantic is None:
                condition_results["ordinary_lane_proof"] = "not_verified"
            else:
                ordinary_path, ordinary_artifact = ordinary_semantic
                normalized_ordinary = closure_evidence.validate_ordinary_lane_proof_artifact(ordinary_artifact)
                ordinary_identity = _proof_identity_section(proof_identity, "ordinary_lane_proof")
                if _normalised_repo_path(normalized_ordinary["candidate_artifact_path"]) != _normalised_repo_path(ordinary_identity.get("candidate_artifact_path")):
                    raise HPEClosureVerificationError("ordinary_lane_proof_mismatch", "ordinary lane proof candidate path does not match the proof context")
                _assert_expected_value(
                    normalized_ordinary["candidate_artifact_sha256"],
                    ordinary_identity.get("candidate_artifact_sha256"),
                    code="ordinary_lane_proof_mismatch",
                    detail="ordinary lane proof candidate sha256 does not match the proof context",
                )
                if _normalised_repo_path(normalized_ordinary["reviewed_image_path"]) != _normalised_repo_path(ordinary_identity.get("reviewed_image_path")):
                    raise HPEClosureVerificationError("ordinary_lane_proof_mismatch", "ordinary lane proof image path does not match the proof context")
                _assert_expected_value(
                    normalized_ordinary["reviewed_image_sha256"],
                    ordinary_identity.get("reviewed_image_sha256"),
                    code="ordinary_lane_proof_mismatch",
                    detail="ordinary lane proof image sha256 does not match the proof context",
                )
                _assert_expected_value(
                    normalized_ordinary["prompt_sha256"],
                    ordinary_identity.get("prompt_sha256"),
                    code="ordinary_lane_proof_mismatch",
                    detail="ordinary lane proof prompt sha256 does not match the proof context",
                )
                _assert_expected_value(
                    normalized_ordinary["authority_commit_final"],
                    ordinary_identity.get("authority_commit"),
                    code="ordinary_lane_proof_mismatch",
                    detail="ordinary lane proof authority commit does not match the proof context",
                )
                if normalized_ordinary["slot_id"] != str(ordinary_identity.get("slot_id") or proof_report.get("selected_candidate_slot_id") or proof_report.get("slot_id") or ""):
                    raise HPEClosureVerificationError("ordinary_lane_proof_mismatch", "ordinary lane proof slot does not match the proof context")
                condition_results["ordinary_lane_proof"] = "verified" if normalized_ordinary["disposition"] == "accepted_for_hpe_closure" else "not_verified"
                if condition_results["ordinary_lane_proof"] == "verified":
                    proof_report.setdefault("authority_boundary_evidence", {})["ordinary_lane_proof_artifact_path"] = str(ordinary_path)
        else:
            condition_results["ordinary_lane_proof"] = closure_schema.condition_result("not_applicable")
    else:
        condition_results["ordinary_lane_proof"] = closure_schema.condition_result("not_applicable")

    human_review = _load_optional_sidecar_artifact(
        proof_report_path=proof_report_path,
        proof_report=proof_report,
        prefix="lena_hpe_human_evidence_review",
    )
    if human_review is not None:
        human_path, human_artifact = human_review
        normalized_human = closure_evidence.validate_human_evidence_review_artifact(human_artifact)
        human_identity = _proof_identity_section(proof_identity, "human_review")
        expected_candidate_path = _proof_path_text(human_identity.get("candidate_artifact_path"))
        expected_reviewed_image_path = _proof_path_text(human_identity.get("reviewed_image_path"))
        expected_handoff_path = _proof_path_text(human_identity.get("handoff_artifact_path"))
        expected_handoff_sha = _proof_text_value(human_identity.get("handoff_artifact_sha256"))
        expected_receipt_path = _proof_path_text(human_identity.get("execution_receipt_artifact_path"))
        expected_receipt_sha = _proof_text_value(human_identity.get("execution_receipt_artifact_sha256"))
        expected_provider_job_id = _proof_text_value(human_identity.get("provider_job_id"))
        expected_slot_id = _proof_text_value(human_identity.get("slot_id"))
        expected_prompt_sha = _proof_text_value(human_identity.get("prompt_sha256"))
        expected_authority_commit = _proof_text_value(human_identity.get("authority_commit"))
        if expected_candidate_path and _normalised_repo_path(normalized_human["candidate_artifact_path"]) != _normalised_repo_path(expected_candidate_path):
            raise HPEClosureVerificationError("human_review_mismatch", "human review candidate path does not match the proof context")
        if expected_reviewed_image_path and _normalised_repo_path(normalized_human["reviewed_image_path"]) != _normalised_repo_path(expected_reviewed_image_path):
            raise HPEClosureVerificationError("human_review_mismatch", "human review image path does not match the proof context")
        if expected_handoff_path and _normalised_repo_path(normalized_human["handoff_artifact_path"]) != _normalised_repo_path(expected_handoff_path):
            raise HPEClosureVerificationError("human_review_mismatch", "human review handoff path does not match the proof context")
        if expected_handoff_sha and normalized_human["handoff_artifact_sha256"] != expected_handoff_sha:
            raise HPEClosureVerificationError("human_review_mismatch", "human review handoff sha256 does not match the proof context")
        if expected_receipt_path and _normalised_repo_path(normalized_human["execution_receipt_artifact_path"]) != _normalised_repo_path(expected_receipt_path):
            raise HPEClosureVerificationError("human_review_mismatch", "human review receipt path does not match the proof context")
        if expected_receipt_sha and normalized_human["execution_receipt_artifact_sha256"] != expected_receipt_sha:
            raise HPEClosureVerificationError("human_review_mismatch", "human review receipt sha256 does not match the proof context")
        if expected_provider_job_id and normalized_human["provider_job_id"] != expected_provider_job_id:
            raise HPEClosureVerificationError("human_review_mismatch", "human review provider job id does not match the proof context")
        if expected_slot_id and str(proof_report.get("selected_candidate_slot_id") or proof_report.get("slot_id") or "") != expected_slot_id:
            raise HPEClosureVerificationError("human_review_mismatch", "human review slot does not match the proof context")
        if expected_prompt_sha and str(proof_report.get("prompt_package", {}).get("image_prompt_sha256") or "") != expected_prompt_sha:
            raise HPEClosureVerificationError("human_review_mismatch", "human review prompt sha256 does not match the proof context")
        if normalized_human["candidate_artifact_sha256"] != str(proof_report.get("selected_candidate_artifact_sha256") or ""):
            raise HPEClosureVerificationError("human_review_mismatch", "human review candidate sha256 does not match the proof report")
        if normalized_human["reviewed_image_sha256"] != str(proof_report.get("image_sha256") or ""):
            raise HPEClosureVerificationError("human_review_mismatch", "human review image sha256 does not match the proof report")
        if normalized_human["authority_commit_expected"] != expected_authority_commit or normalized_human["authority_commit_final"] != expected_authority_commit:
            raise HPEClosureVerificationError("human_review_mismatch", "human review authority commit does not match the proof context")
        if normalized_human["disposition"] == "accepted_for_hpe_closure":
            condition_results["human_evidence_review"] = "verified"
            proof_report.setdefault("authority_boundary_evidence", {})["human_evidence_review_artifact_path"] = str(human_path)
        else:
            condition_results["human_evidence_review"] = "not_verified"
    else:
        condition_results["human_evidence_review"] = "not_verified"

    final_ci = _load_optional_sidecar_artifact(
        proof_report_path=proof_report_path,
        proof_report=proof_report,
        prefix="lena_hpe_final_ci_confirmation",
    )
    if final_ci is not None:
        _, final_ci_artifact = final_ci
        final_ci_identity = _proof_identity_section(proof_identity, "final_ci")
        normalized_ci = closure_evidence.validate_final_ci_confirmation_artifact(
            final_ci_artifact,
            expected_repository=str(final_ci_identity.get("repository") or ""),
            expected_pr_number=int(final_ci_identity.get("pr_number")) if final_ci_identity.get("pr_number") is not None else None,
            expected_reviewed_head_sha=str(final_ci_identity.get("reviewed_head_sha") or ""),
            expected_merge_commit_sha=str(final_ci_identity.get("merge_commit_sha") or ""),
            expected_authority_commit=str(final_ci_identity.get("authority_commit") or ""),
        )
        if all(entry["conclusion"] == "pass" for entry in normalized_ci["required_checks"]):
            condition_results["final_ci_confirmation"] = "verified"
        else:
            condition_results["final_ci_confirmation"] = "not_verified"
    else:
        condition_results["final_ci_confirmation"] = "not_verified"

    condition_results["authority_commit_binding"] = "verified"
    return condition_results


def _build_closure_report(
    proof_report: dict[str, Any],
    *,
    authority_commit_expected: str,
    authority_commit_final: str,
    base_commit_sha: str,
    proof_report_path: Path,
    proof_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    mandatory_condition_results = _derive_mandatory_condition_results(
        proof_report,
        authority_commit_expected=authority_commit_expected,
        proof_report_path=proof_report_path,
        proof_identity=proof_identity,
    )
    blocking_findings: list[dict[str, Any]] = []
    if proof_report.get("qa_artifact", {}).get("recommendation") == "integrity_failure":
        blocking_findings.append({"code": "integrity_failure", "detail": "QA artifact recommended integrity failure"})
    if proof_report.get("qa_artifact", {}).get("semantic_status") == "error":
        blocking_findings.append({"code": "semantic_error", "detail": "semantic proof produced an error"})
    return closure_schema.build_closure_verification_report(
        current_commit_sha=authority_commit_expected,
        authority_commit_expected=authority_commit_expected,
        authority_commit_final=authority_commit_final,
        base_commit_sha=base_commit_sha,
        execution_timestamp_utc=_utcnow_iso(),
        branch=str(proof_report.get("branch") or ""),
        lane_type=str(proof_report.get("lane_type") or ""),
        selected_slot_id=str(proof_report.get("selected_candidate_slot_id") or proof_report.get("slot_id") or ""),
        selected_candidate_id=str(proof_report.get("selected_candidate_id") or ""),
        hpe_plan_fingerprint_sha256=str(proof_report.get("hpe_plan_fingerprint_sha256") or ""),
        candidate_ranking_evidence=proof_report.get("candidate_ranking_evidence", {}),
        selected_candidate_evidence=proof_report.get("selected_candidate_evidence", {}),
        prompt_plan_evidence=proof_report.get("prompt_plan_evidence", {}),
        final_prompt_influence_evidence=proof_report.get("final_prompt_influence_evidence", []),
        integrity_qa_evidence=proof_report.get("integrity_qa_evidence", {}),
        semantic_qa_configuration=proof_report.get("semantic_qa_configuration", {}),
        semantic_qa_evidence=proof_report.get("semantic_qa_evidence", {}),
        lifecycle_report_evidence=proof_report.get("lifecycle_report_evidence", {}),
        authority_boundary_evidence=proof_report.get("authority_boundary_evidence", {}),
        required_artifact_paths=proof_report.get("required_artifact_paths", {}),
        mandatory_condition_results=mandatory_condition_results,
        blocking_findings=blocking_findings,
    )


def verify_closure_report(
    *,
    output_root: Path,
    authority_commit_expected: str,
    require_clean_authority: bool = True,
    dry_run: bool,
    proof_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start_head = _git_rev_parse("HEAD")
    if start_head != authority_commit_expected:
        raise HPEClosureVerificationError("authority_commit_mismatch", "expected authority commit does not match the current HEAD")
    if require_clean_authority:
        try:
            selector.verify_authority_inputs_clean()
        except selector.GateError as exc:
            raise HPEClosureVerificationError(exc.code, exc.detail) from exc

    proof_report_path = _locate_proof_report(output_root)
    proof_report = _load_json_object(proof_report_path)
    if proof_report.get("report_type") != "human_presence_engine_controlled_proof":
        raise HPEClosureVerificationError("proof_report_invalid", "proof report type mismatch")
    if proof_report.get("authority_commit") != authority_commit_expected:
        raise HPEClosureVerificationError("authority_commit_mismatch", "proof authority_commit does not match the expected head")

    base_commit_sha = _resolve_base_commit_sha()
    closure_report = _build_closure_report(
        proof_report,
        authority_commit_expected=authority_commit_expected,
        authority_commit_final=_git_rev_parse("HEAD"),
        base_commit_sha=base_commit_sha,
        proof_report_path=proof_report_path,
        proof_identity=proof_identity,
    )

    if not dry_run:
        closure_path = _closure_report_path(output_root, proof_report)
        _write_json_atomic(closure_path, closure_report)

    final_head = _git_rev_parse("HEAD")
    if final_head != start_head:
        raise HPEClosureVerificationError("authority_commit_moved", "repository HEAD moved during closure verification")

    return closure_report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a deterministic HPE closure proof report.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--authority-commit-expected", required=True)
    parser.add_argument("--require-clean-authority", action="store_true", default=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        report = verify_closure_report(
            output_root=args.output_root,
            authority_commit_expected=args.authority_commit_expected,
            require_clean_authority=args.require_clean_authority,
            dry_run=args.dry_run,
        )
    except (HPEClosureVerificationError, closure_schema.HumanPresenceEngineClosureError) as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1

    print(json.dumps({"ok": report["closure_status"] == "verified", "closure_report": report}, indent=2))
    return 0 if report["closure_status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
