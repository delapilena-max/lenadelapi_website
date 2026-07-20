from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.influencer_nodes.lena import autonomy_ladder  # noqa: E402
from pipeline import higgsfield_lena_api_executor as executor  # noqa: E402
from tools import lena_human_rejection_gate_v1 as rejection_gate  # noqa: E402
from tools import lena_record_human_rejection_v1 as rejection_record  # noqa: E402
from tools.strategy import lena_execute_selected_candidate_v1 as selected_consumer  # noqa: E402

SCHEMA_VERSION = "lena_retry_decision_v1"
CORRECTION_SCHEMA_VERSION = "lena_bounded_retry_plan_correction_v1"
INVALID_RETRY_SCHEMA_VERSION = "lena_bounded_retry_plan_v1"
FINAL_ACTION = "prepare_higgsfield_retry_dry_run_for_review"
MUTATION_REASON = "prevent_duplicated_background_identity"
BACKGROUND_IDENTITY_CONSTRAINT = (
    "Background identity safety: do not include any recognizable background faces. "
    "Any background people must be fully blurred, obscured, turned away, or cropped so they never read "
    "as a second Lena-like identity, and any visible background identity must be clearly distinct from Lena."
)
HAIR_CROWN_CONSTRAINT = (
    "Lena's hair has realistic natural root direction and lies smoothly across the crown with a low, "
    "relaxed top silhouette and normal soft volume. No raised forelock, no vertical crown tuft, no "
    "rooster-like crest, no exaggerated crown lift, and no isolated upward-pointing clump of hair."
)
HAIR_CROWN_PRESERVES = [
    "face and Lena identity",
    "apparent age",
    "skin and freckles",
    "body and proportions",
    "hair color",
    "hair length",
    "general hair texture",
    "wardrobe",
    "environment",
    "scene",
    "pose",
    "expression",
    "gaze",
    "framing",
    "camera treatment",
    "lighting",
    "composition",
]
DEFAULT_OUTPUT_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "retry_decisions"
RETRY_EXECUTION_CONTRACT_SCHEMA_VERSION = "lena_retry_execution_contract_v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SLOT_RE = re.compile(r"^(?P<prefix>.+?)-(?P<media_type>photo|video)$")


class RetryDecisionError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _serialize_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RetryDecisionError("artifact_missing", f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RetryDecisionError("artifact_malformed", f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RetryDecisionError("artifact_malformed", f"{label} must be a JSON object: {path}")
    return value


def _require_sha256(raw: Any, label: str) -> str:
    value = str(raw or "")
    if not SHA256_RE.fullmatch(value):
        raise RetryDecisionError("sha_invalid", f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _require_exact_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256_file(path)
    if actual != _require_sha256(expected, label):
        raise RetryDecisionError("sha_mismatch", f"{label} does not match current file bytes at {path}")


def _retry_slot_id(original_slot_id: str) -> str:
    match = SLOT_RE.fullmatch(original_slot_id)
    if not match:
        raise RetryDecisionError("slot_invalid", f"original slot_id does not end with -photo/-video: {original_slot_id}")
    return f"{match.group('prefix')}-retry01-{match.group('media_type')}"


def retry_decision_artifact_path(
    date_str: str,
    retry_slot_id: str,
    original_decision_fingerprint: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    return output_root / date_str / f"{retry_slot_id}__{original_decision_fingerprint[:12]}_retry_decision.json"


def _constraint_for_mutation(mutation_type: str) -> str:
    if mutation_type == "prevent_duplicated_background_identity":
        return BACKGROUND_IDENTITY_CONSTRAINT
    if mutation_type == "correct_hair_crown_forelock":
        return HAIR_CROWN_CONSTRAINT
    raise RetryDecisionError("unknown_retry_mutation_type", f"unknown retry mutation type: {mutation_type!r}")


def _preserves_for_mutation(mutation_type: str) -> list[str]:
    if mutation_type == "prevent_duplicated_background_identity":
        return ["concept", "wardrobe", "pose", "expression", "hook", "composition"]
    if mutation_type == "correct_hair_crown_forelock":
        return list(HAIR_CROWN_PRESERVES)
    raise RetryDecisionError("unknown_retry_mutation_type", f"unknown retry mutation type: {mutation_type!r}")


def _mutate_prompt_for_retry(original_prompt: str, mutation_type: str = MUTATION_REASON) -> str:
    constraint = _constraint_for_mutation(mutation_type)
    if constraint in original_prompt:
        raise RetryDecisionError("prompt_already_mutated", "original prompt already contains the retry correction constraint")
    return f"{original_prompt} {constraint}"


def _validate_original_decision_artifact(path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    artifact = selected_consumer._read_artifact(path)
    candidate = selected_consumer._validate_shape(artifact)
    selected_consumer._validate_fingerprint(artifact)
    selected_consumer._validate_authority(artifact)

    try:
        source = executor.resolve_prompt_source(str(artifact["as_of_date"]), str(candidate["slot_id"]))
    except executor.PromptSourceError as exc:
        raise RetryDecisionError("original_prompt_missing", str(exc)) from exc
    image = source.get("image", {})
    prompt = image.get("image_prompt")
    if not isinstance(prompt, str) or not prompt:
        raise RetryDecisionError("original_prompt_missing", "original decision could not regenerate its exact prompt bytes")
    if image.get("slot_id") != candidate["slot_id"]:
        raise RetryDecisionError("slot_invalid", "executor-resolved slot does not match the original decision")
    if image.get("lane") != candidate["lane"]:
        raise RetryDecisionError("lane_mismatch", "executor-resolved lane does not match the original decision")
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != candidate["prompt_sha256"]:
        raise RetryDecisionError("prompt_sha_mismatch", "original decision prompt_sha256 does not match the regenerated executor prompt")
    validation = executor.validate_candidate(source, None)
    if validation.get("ok") is not True:
        raise RetryDecisionError("executor_candidate_invalid", json.dumps(validation.get("all_reasons", [])))
    return artifact, candidate, prompt


def _validate_correction_artifact(correction_artifact_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
    correction_path = correction_artifact_path.resolve()
    correction = _read_object(correction_path, "retry-plan correction artifact")
    if correction.get("schema_version") != CORRECTION_SCHEMA_VERSION:
        raise RetryDecisionError("wrong_schema_version", "artifact is not a Lena retry-plan correction")
    if correction.get("influencer_id") != "lena":
        raise RetryDecisionError("wrong_influencer", "retry-plan correction influencer_id must be Lena")
    if correction.get("retry_attempt") != 1 or correction.get("retry_cap") != 1:
        raise RetryDecisionError("retry_cap_invalid", "retry-plan correction retry attempt/cap must remain exactly 1/1")
    if correction.get("action") != "correction_record_only_no_provider_call":
        raise RetryDecisionError("action_invalid", "retry-plan correction action must remain correction_record_only_no_provider_call")
    if correction.get("recovery_reason") != "human_rejection_artifact_sha256_mismatch_only":
        raise RetryDecisionError("recovery_reason_invalid", "retry-plan correction recovery_reason is invalid")
    if correction.get("historical_artifacts_modified") != []:
        raise RetryDecisionError("history_mutated", "retry-plan correction must not record any historical artifact mutation")
    if correction.get("supersedes_invalid_retry_plan_for_execution_only") is not True:
        raise RetryDecisionError("supersede_flag_invalid", "retry-plan correction must supersede the invalid retry plan for execution only")
    if correction.get("preserves_immutable_historical_artifacts") is not True:
        raise RetryDecisionError("immutability_flag_invalid", "retry-plan correction must preserve immutable historical artifacts")

    valid_rejection_path = Path(str(correction.get("valid_human_rejection_artifact_path") or "")).resolve()
    invalid_retry_path = Path(str(correction.get("invalid_retry_plan_artifact_path") or "")).resolve()
    original_decision_path = Path(str(correction.get("original_decision_artifact_path") or "")).resolve()
    manifest_path = Path(str(correction.get("original_manifest_path") or "")).resolve()
    image_path = Path(str(correction.get("original_image_path") or "")).resolve()
    if not valid_rejection_path.is_file() or not invalid_retry_path.is_file() or not original_decision_path.is_file():
        raise RetryDecisionError("lineage_missing", "retry-plan correction references missing lineage artifacts")

    _require_exact_sha(valid_rejection_path, str(correction.get("valid_human_rejection_artifact_sha256") or ""), "valid_human_rejection_artifact_sha256")
    _require_exact_sha(invalid_retry_path, str(correction.get("invalid_retry_plan_artifact_sha256") or ""), "invalid_retry_plan_artifact_sha256")
    _require_exact_sha(original_decision_path, str(correction.get("original_decision_artifact_sha256") or ""), "original_decision_artifact_sha256")
    _require_exact_sha(manifest_path, str(correction.get("original_manifest_sha256") or ""), "original_manifest_sha256")
    if _sha256_file(image_path) != correction.get("original_image_sha256"):
        raise RetryDecisionError("image_sha_mismatch", "retry-plan correction original_image_sha256 does not match the current image bytes")

    rejection = _read_object(valid_rejection_path, "valid rejection artifact")
    qa_path = Path(str(rejection.get("qa_disposition_artifact_path") or "")).resolve()
    packet_path = Path(str(rejection.get("publish_packet_path") or "")).resolve()
    draft_path = Path(str(rejection.get("queue_draft_path") or "")).resolve()
    try:
        rejection_gate._validate_artifact(
            valid_rejection_path,
            date_str=str(rejection.get("date") or ""),
            slot_id=str(rejection.get("slot_id") or ""),
            image_path=image_path,
            publish_packet_path=packet_path,
            queue_draft_path=draft_path,
            qa_path=qa_path,
        )
    except rejection_gate.HumanRejectionGateError as exc:
        raise RetryDecisionError("rejection_invalid", f"valid rejection artifact failed validation: {exc}") from exc

    invalid_retry = _read_object(invalid_retry_path, "invalid retry artifact")
    if invalid_retry.get("schema_version") != INVALID_RETRY_SCHEMA_VERSION:
        raise RetryDecisionError("invalid_retry_schema", "superseded retry plan has the wrong schema_version")
    if invalid_retry.get("retry_attempt") != 1 or invalid_retry.get("retry_cap") != 1:
        raise RetryDecisionError("invalid_retry_cap", "superseded retry plan retry attempt/cap must remain exactly 1/1")
    if invalid_retry.get("action") != "plan_only_no_provider_call":
        raise RetryDecisionError("invalid_retry_action", "superseded retry plan action must remain plan_only_no_provider_call")
    contract = rejection_record.correction_contract_for_reason(
        str(rejection.get("operator_reason") or ""),
        str(rejection.get("reason_code") or "") or None,
    )
    if invalid_retry.get("next_attempt_instruction") != contract["next_attempt_instruction"]:
        raise RetryDecisionError("invalid_retry_instruction", "superseded retry plan next_attempt_instruction is invalid")
    if invalid_retry.get("mutation_type") != contract["mutation_type"]:
        raise RetryDecisionError("invalid_retry_mutation_type", "superseded retry plan mutation_type is invalid")
    if invalid_retry.get("correction_scope") != contract["correction_scope"]:
        raise RetryDecisionError("invalid_retry_correction_scope", "superseded retry plan correction_scope is invalid")
    if invalid_retry.get("human_rejection_artifact_path") != str(valid_rejection_path):
        raise RetryDecisionError("invalid_retry_binding", "superseded retry plan does not bind the same rejection artifact path")
    embedded_rejection_sha = _require_sha256(
        invalid_retry.get("human_rejection_artifact_sha256"),
        "superseded retry plan embedded human_rejection_artifact_sha256",
    )
    if embedded_rejection_sha == _sha256_file(valid_rejection_path):
        raise RetryDecisionError("invalid_retry_not_superseded", "superseded retry plan no longer demonstrates the historical rejection-SHA mismatch")
    if embedded_rejection_sha != correction.get("invalid_retry_plan_embedded_rejection_sha256"):
        raise RetryDecisionError("invalid_retry_binding", "retry-plan correction does not match the superseded retry plan's embedded rejection SHA")

    original_decision, candidate, original_prompt = _validate_original_decision_artifact(original_decision_path)
    if original_decision.get("decision_fingerprint_sha256") != correction.get("decision_fingerprint_sha256"):
        raise RetryDecisionError("decision_binding_mismatch", "retry-plan correction decision_fingerprint_sha256 does not match the original decision artifact")
    if candidate.get("prompt_sha256") != hashlib.sha256(original_prompt.encode("utf-8")).hexdigest():
        raise RetryDecisionError("prompt_sha_mismatch", "original decision prompt_sha256 does not match the regenerated prompt bytes")
    if correction.get("original_publish_packet_path") != str(packet_path):
        raise RetryDecisionError("packet_binding_mismatch", "retry-plan correction original_publish_packet_path does not match the rejection lineage")
    if correction.get("original_queue_draft_path") != str(draft_path):
        raise RetryDecisionError("draft_binding_mismatch", "retry-plan correction original_queue_draft_path does not match the rejection lineage")
    if correction.get("original_image_sha256") != rejection.get("image_sha256"):
        raise RetryDecisionError("image_binding_mismatch", "retry-plan correction original_image_sha256 does not match the authoritative rejection lineage")
    manifest = _read_object(manifest_path, "original generation manifest")
    return correction, rejection, invalid_retry, original_decision, manifest, candidate, original_prompt


def build_retry_decision(correction_artifact_path: Path, output_root: Path = DEFAULT_OUTPUT_ROOT) -> tuple[Path, dict[str, Any]]:
    correction_path = correction_artifact_path.resolve()
    correction, rejection, invalid_retry, original_decision, manifest, candidate, original_prompt = _validate_correction_artifact(correction_path)
    contract = rejection_record.correction_contract_for_reason(
        str(rejection.get("operator_reason") or ""),
        str(rejection.get("reason_code") or "") or None,
    )
    retry_slot_id = _retry_slot_id(candidate["slot_id"])
    retry_prompt = _mutate_prompt_for_retry(original_prompt, contract["mutation_type"])
    retry_prompt_sha = hashlib.sha256(retry_prompt.encode("utf-8")).hexdigest()
    path = retry_decision_artifact_path(
        str(original_decision["as_of_date"]),
        retry_slot_id,
        str(original_decision["decision_fingerprint_sha256"]),
        output_root,
    )
    if path.exists():
        raise RetryDecisionError("duplicate_retry_decision", f"retry decision already exists for this exact lineage: {path}")

    core = {
        "schema_version": SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": original_decision["as_of_date"],
        "original_slot_id": candidate["slot_id"],
        "retry_slot_id": retry_slot_id,
        "retry_attempt": 1,
        "retry_cap": 1,
        "source_retry_plan_correction_artifact_path": str(correction_path),
        "source_retry_plan_correction_artifact_sha256": _sha256_file(correction_path),
        "source_valid_human_rejection_artifact_path": str(Path(str(correction["valid_human_rejection_artifact_path"])).resolve()),
        "source_valid_human_rejection_artifact_sha256": correction["valid_human_rejection_artifact_sha256"],
        "source_invalid_retry_plan_artifact_path": str(Path(str(correction["invalid_retry_plan_artifact_path"])).resolve()),
        "source_invalid_retry_plan_artifact_sha256": correction["invalid_retry_plan_artifact_sha256"],
        "source_original_decision_artifact_path": str(Path(str(correction["original_decision_artifact_path"])).resolve()),
        "source_original_decision_artifact_sha256": correction["original_decision_artifact_sha256"],
        "source_original_decision_fingerprint_sha256": original_decision["decision_fingerprint_sha256"],
        "source_original_manifest_path": correction["original_manifest_path"],
        "source_original_manifest_sha256": correction["original_manifest_sha256"],
        "source_original_provider_job_evidence": {
            "provider": manifest.get("provider"),
            "provider_job_id": manifest.get("provider_job_id"),
            "provider_status": manifest.get("provider_status"),
            "job_type": manifest.get("job_type"),
            "custom_reference_id": manifest.get("custom_reference_id"),
        },
        "source_original_image_path": correction["original_image_path"],
        "source_original_image_sha256": correction["original_image_sha256"],
        "reason_code": contract["reason_code"],
        "mutation_type": contract["mutation_type"],
        "correction_scope": contract["correction_scope"],
        "deterministic_qa_status": contract["deterministic_qa_status_required"],
        "deterministic_qa_blocker": contract["deterministic_qa_blocker"],
        "missing_immutable_provenance": list(contract["missing_immutable_provenance"]),
        "source_qa_disposition_artifact_path": rejection["qa_disposition_artifact_path"],
        "source_qa_disposition_artifact_sha256": rejection["qa_disposition_artifact_sha256"],
        "source_publish_packet_path": rejection["publish_packet_path"],
        "source_publish_packet_sha256": rejection["publish_packet_sha256"],
        "source_queue_draft_path": rejection["queue_draft_path"],
        "source_queue_draft_sha256": rejection["queue_draft_sha256"],
        "lane": candidate["lane"],
        "recipe_id": candidate["recipe_id"],
        "hook_id": candidate["hook_id"],
        "hook_text": candidate["hook_text"],
        "caption_seed": candidate["caption_seed"],
        "wardrobe_outfit_id": candidate.get("wardrobe_outfit_id"),
        "visual_style": candidate.get("visual_style"),
        "pose_body_language_id": candidate.get("pose_body_language_id"),
        "pose": candidate.get("pose"),
        "camera_text": candidate.get("camera_text"),
        "lighting_text": candidate.get("lighting_text"),
        "original_prompt_sha256": candidate["prompt_sha256"],
        "retry_prompt_sha256": retry_prompt_sha,
        "prompt_mutation": {
            "mode": "scene_constraint_only",
            "reason": contract["mutation_type"],
            "added_constraint": _constraint_for_mutation(contract["mutation_type"]),
            "preserves": _preserves_for_mutation(contract["mutation_type"]),
        },
        "retry_prompt_text": retry_prompt,
        "final_action": FINAL_ACTION,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "side_effects_performed": [],
        "exact_next_allowed_action": (
            "Separate explicit Nicolas authorization is required for one future live Higgsfield retry invocation bound to "
            f"original_decision_fingerprint={original_decision['decision_fingerprint_sha256']}, "
            f"retry_slot_id={retry_slot_id}, "
            f"retry_prompt_sha256={retry_prompt_sha}. "
            "No second retry, fallback generation, packet/queue reuse, approval, promotion, publish, upload, analytics mutation, or historical artifact mutation is authorized."
        ),
    }
    fingerprint = _sha256_bytes(_canonical_bytes(core))
    artifact = dict(core)
    artifact["generated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    artifact["retry_decision_fingerprint_sha256"] = fingerprint
    return path, artifact


def _build_retry_source(artifact: dict[str, Any]) -> dict[str, Any]:
    source = executor.resolve_prompt_source(str(artifact["as_of_date"]), str(artifact["original_slot_id"]))
    retry_source = copy.deepcopy(source)
    retry_source["image"]["slot_id"] = artifact["retry_slot_id"]
    retry_source["image"]["image_prompt"] = artifact["retry_prompt_text"]
    retry_source["image"]["prompt_sha256"] = artifact["retry_prompt_sha256"]
    retry_source["image"]["retry_execution_contract"] = {
        "schema_version": RETRY_EXECUTION_CONTRACT_SCHEMA_VERSION,
        "retry_decision_fingerprint_sha256": artifact["retry_decision_fingerprint_sha256"],
        "retry_attempt": artifact["retry_attempt"],
        "retry_cap": artifact["retry_cap"],
        "original_slot_id": artifact["original_slot_id"],
        "retry_slot_id": artifact["retry_slot_id"],
        "original_prompt_sha256": artifact["original_prompt_sha256"],
        "retry_prompt_sha256": artifact["retry_prompt_sha256"],
        "mutation_type": artifact["mutation_type"],
        "correction_scope": artifact["correction_scope"],
        "added_constraint": artifact["prompt_mutation"]["added_constraint"],
        "source_original_decision_fingerprint_sha256": artifact["source_original_decision_fingerprint_sha256"],
        "source_original_manifest_path": artifact["source_original_manifest_path"],
        "source_original_manifest_sha256": artifact["source_original_manifest_sha256"],
        "source_original_provider_job_evidence": artifact["source_original_provider_job_evidence"],
        "source_valid_human_rejection_artifact_path": artifact["source_valid_human_rejection_artifact_path"],
        "source_valid_human_rejection_artifact_sha256": artifact["source_valid_human_rejection_artifact_sha256"],
        "source_invalid_retry_plan_artifact_path": artifact["source_invalid_retry_plan_artifact_path"],
        "source_invalid_retry_plan_artifact_sha256": artifact["source_invalid_retry_plan_artifact_sha256"],
        "source_retry_plan_correction_artifact_path": artifact["source_retry_plan_correction_artifact_path"],
        "source_retry_plan_correction_artifact_sha256": artifact["source_retry_plan_correction_artifact_sha256"],
    }
    return retry_source


def _delegate_retry_executor_dry_run(artifact: dict[str, Any]) -> dict[str, Any]:
    source = _build_retry_source(artifact)
    rendered = executor.render_dry_run_contract(
        str(artifact["as_of_date"]),
        str(artifact["retry_slot_id"]),
        source,
        executor.DEFAULT_LENA_CUSTOM_REFERENCE_ID,
    )
    stdout = rendered["stdout"]
    stdout_validation = selected_consumer._validate_executor_dry_run_stdout(
        stdout,
        str(artifact["as_of_date"]),
        str(artifact["retry_slot_id"]),
    )
    return {
        "returncode": 0 if rendered["validation"]["ok"] else 1,
        "dry_run": True,
        "live_flag_present": False,
        "validation": rendered["validation"],
        **stdout_validation,
    }


def _write_json_artifact(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RetryDecisionError("duplicate_retry_decision", f"retry decision already exists for this exact lineage: {path}")
    path.write_bytes(_serialize_json_bytes(value))


def _validate_retry_decision_artifact(path: Path) -> dict[str, Any]:
    artifact = _read_object(path, "retry decision artifact")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise RetryDecisionError("wrong_schema_version", "artifact is not a Lena retry decision")
    if artifact.get("influencer_id") != "lena":
        raise RetryDecisionError("wrong_influencer", "retry decision influencer_id must be Lena")
    if artifact.get("retry_attempt") != 1 or artifact.get("retry_cap") != 1:
        raise RetryDecisionError("retry_cap_invalid", "retry decision retry attempt/cap must remain exactly 1/1")
    if artifact.get("final_action") != FINAL_ACTION:
        raise RetryDecisionError("wrong_final_action", f"retry decision final_action must be {FINAL_ACTION!r}")
    if artifact.get("provider_authorized") is not False or artifact.get("provider_called") is not False:
        raise RetryDecisionError("unexpected_provider_state", "retry decision provider state must remain false/false")
    if artifact.get("generation_performed") is not False or artifact.get("side_effects_performed") != []:
        raise RetryDecisionError("unexpected_side_effects", "retry decision must not record generation or any side effects")
    mutation_type = str(artifact.get("mutation_type") or "")
    if artifact.get("prompt_mutation", {}).get("reason") != mutation_type:
        raise RetryDecisionError("prompt_mutation_invalid", "retry decision prompt mutation reason is invalid")
    expected_constraint = _constraint_for_mutation(mutation_type)
    retry_prompt = str(artifact.get("retry_prompt_text") or "")
    if not retry_prompt or expected_constraint not in retry_prompt:
        raise RetryDecisionError("prompt_mutation_invalid", "retry decision prompt text is missing the required correction constraint")
    if retry_prompt.count(expected_constraint) != 1:
        raise RetryDecisionError("prompt_mutation_invalid", "retry decision prompt text must contain the required correction constraint exactly once")
    if artifact.get("retry_prompt_sha256") != hashlib.sha256(retry_prompt.encode("utf-8")).hexdigest():
        raise RetryDecisionError("prompt_sha_mismatch", "retry decision retry_prompt_sha256 does not match the stored retry prompt bytes")
    if artifact.get("retry_slot_id") != _retry_slot_id(str(artifact.get("original_slot_id") or "")):
        raise RetryDecisionError("slot_invalid", "retry decision retry_slot_id does not match the canonical retry slot binding")

    expected_core = {key: value for key, value in artifact.items() if key not in {"generated_at_utc", "retry_decision_fingerprint_sha256"}}
    expected_fingerprint = _sha256_bytes(_canonical_bytes(expected_core))
    if artifact.get("retry_decision_fingerprint_sha256") != expected_fingerprint:
        raise RetryDecisionError("fingerprint_mismatch", "retry decision fingerprint does not match immutable body")

    correction_path = Path(str(artifact.get("source_retry_plan_correction_artifact_path") or "")).resolve()
    _require_exact_sha(correction_path, str(artifact.get("source_retry_plan_correction_artifact_sha256") or ""), "source_retry_plan_correction_artifact_sha256")
    correction, rejection, invalid_retry, original_decision, manifest, candidate, original_prompt = _validate_correction_artifact(correction_path)
    if artifact.get("source_original_decision_fingerprint_sha256") != original_decision.get("decision_fingerprint_sha256"):
        raise RetryDecisionError("decision_binding_mismatch", "retry decision does not bind the original decision fingerprint exactly")
    if artifact.get("original_prompt_sha256") != candidate.get("prompt_sha256"):
        raise RetryDecisionError("prompt_sha_mismatch", "retry decision does not preserve the original prompt SHA exactly")
    expected_prompt = _mutate_prompt_for_retry(original_prompt, mutation_type)
    if retry_prompt != expected_prompt:
        raise RetryDecisionError("prompt_mutation_invalid", "retry decision prompt text does not match the canonical retry mutation")
    if artifact.get("source_valid_human_rejection_artifact_path") != correction.get("valid_human_rejection_artifact_path"):
        raise RetryDecisionError("rejection_binding_mismatch", "retry decision valid rejection path binding drifted")
    if artifact.get("source_invalid_retry_plan_artifact_path") != correction.get("invalid_retry_plan_artifact_path"):
        raise RetryDecisionError("invalid_retry_binding", "retry decision superseded invalid retry plan binding drifted")
    if artifact.get("source_publish_packet_sha256") != rejection.get("publish_packet_sha256"):
        raise RetryDecisionError("packet_binding_mismatch", "retry decision publish packet SHA binding drifted")
    if artifact.get("source_queue_draft_sha256") != rejection.get("queue_draft_sha256"):
        raise RetryDecisionError("draft_binding_mismatch", "retry decision queue draft SHA binding drifted")
    if invalid_retry.get("retry_attempt") != artifact.get("retry_attempt"):
        raise RetryDecisionError("retry_cap_invalid", "retry decision retry attempt does not match the superseded invalid retry plan")
    if artifact.get("source_original_provider_job_evidence") != {
        "provider": manifest.get("provider"),
        "provider_job_id": manifest.get("provider_job_id"),
        "provider_status": manifest.get("provider_status"),
        "job_type": manifest.get("job_type"),
        "custom_reference_id": manifest.get("custom_reference_id"),
    }:
        raise RetryDecisionError("provider_lineage_mismatch", "retry decision original provider lineage drifted")
    return artifact


def load_retry_execution_source(retry_decision_artifact_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(str(retry_decision_artifact_path)).resolve()
    artifact = _validate_retry_decision_artifact(path)
    return artifact, _build_retry_source(artifact)


def evaluate_retry_correction(
    *,
    correction_artifact_path: Path | None = None,
    retry_decision_artifact_path: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    write_decision: bool = False,
    live_requested: bool = False,
) -> dict[str, Any]:
    try:
        autonomy_ladder.assert_allowed(
            "lena_execute_retry_decision_v1",
            level=1,
            action="candidate generation only",
        )
    except autonomy_ladder.AutonomyLadderError as exc:
        raise RetryDecisionError(exc.code, exc.detail) from exc

    if bool(correction_artifact_path) == bool(retry_decision_artifact_path):
        raise RetryDecisionError("argument_conflict", "exactly one of correction_artifact_path or retry_decision_artifact_path is required")

    if correction_artifact_path is not None:
        path, artifact = build_retry_decision(correction_artifact_path, output_root)
        state = "ready_for_retry_executor_dry_run"
        if write_decision:
            _write_json_artifact(path, artifact)
            state = "retry_decision_written"
    else:
        path = Path(str(retry_decision_artifact_path)).resolve()
        artifact = _validate_retry_decision_artifact(path)
        state = "ready_for_retry_executor_dry_run"

    validation_results = {
        "original_decision_validation": True,
        "correction_lineage_validation": True,
        "retry_prompt_mutation_validation": True,
        "executor_dry_run_delegated": False,
    }
    blockers: list[str] = []
    if live_requested:
        state = "ready_for_retry_live_authorization"
        blockers.append("separate_explicit_nicolas_authorization_required")
    else:
        validation_results["executor_dry_run"] = _delegate_retry_executor_dry_run(artifact)
        validation_results["executor_dry_run_delegated"] = True

    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "influencer_id": "lena",
        "retry_decision_artifact_path": str(path.resolve()),
        "retry_decision_fingerprint_sha256": artifact["retry_decision_fingerprint_sha256"],
        "original_slot_id": artifact["original_slot_id"],
        "retry_slot_id": artifact["retry_slot_id"],
        "retry_attempt": artifact["retry_attempt"],
        "retry_cap": artifact["retry_cap"],
        "lane": artifact["lane"],
        "recipe_id": artifact["recipe_id"],
        "hook_id": artifact["hook_id"],
        "original_prompt_sha256": artifact["original_prompt_sha256"],
        "retry_prompt_sha256": artifact["retry_prompt_sha256"],
        "validation_results": validation_results,
        "blockers": blockers,
        "live_requested": live_requested,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "exact_next_allowed_action": artifact["exact_next_allowed_action"],
        "side_effects_performed": [],
    }


def _blocked_report(correction_artifact_path: Path | None, retry_decision_artifact_path: Path | None, live_requested: bool, exc: RetryDecisionError) -> dict[str, Any]:
    path = correction_artifact_path or retry_decision_artifact_path or Path(".")
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "blocked",
        "influencer_id": "lena",
        "input_artifact_path": str(Path(path).resolve()),
        "retry_decision_artifact_path": None,
        "retry_decision_fingerprint_sha256": None,
        "original_slot_id": None,
        "retry_slot_id": None,
        "retry_attempt": None,
        "retry_cap": None,
        "lane": None,
        "recipe_id": None,
        "hook_id": None,
        "original_prompt_sha256": None,
        "retry_prompt_sha256": None,
        "validation_results": {"error_code": exc.code, "error_detail": exc.detail},
        "blockers": [exc.code],
        "live_requested": live_requested,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "exact_next_allowed_action": "Preserve lineage, correct the blocking artifact, or request a fresh autonomous selector decision.",
        "side_effects_performed": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one Lena retry-plan correction and build/consume one bounded retry decision.")
    parser.add_argument("--correction-artifact", type=Path)
    parser.add_argument("--retry-decision-artifact", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--write-decision", action="store_true")
    parser.add_argument("--live", action="store_true", help="Design-only: report the exact explicit authorization required for one future live retry.")
    args = parser.parse_args()
    try:
        report = evaluate_retry_correction(
            correction_artifact_path=args.correction_artifact,
            retry_decision_artifact_path=args.retry_decision_artifact,
            output_root=args.output_root,
            write_decision=args.write_decision,
            live_requested=args.live,
        )
    except RetryDecisionError as exc:
        print(json.dumps(_blocked_report(args.correction_artifact, args.retry_decision_artifact, args.live, exc), sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
