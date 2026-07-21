from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from tools import lena_higgsfield_generation_approval_v1 as approval_contract  # noqa: E402
from tools.strategy import lena_audit_autonomous_generation_readiness_v1 as readiness_audit  # noqa: E402
from tools.strategy import lena_pose_provenance_v1 as pose_provenance  # noqa: E402

SCHEMA_VERSION = "lena_higgsfield_retry_handoff_v1"
REPORT_TYPE = "lena_higgsfield_retry_handoff"
RETRY_PURPOSE = "framing_mirror_vanity_contract_repair"
BACKGROUND_RETRY_PURPOSE = RETRY_PURPOSE
HAIR_CROWN_RETRY_PURPOSE = "hair_crown_forelock_contract_repair"
FINAL_ACTION = "prepare_higgsfield_retry_handoff_dry_run_for_review"
DEFAULT_OUTPUT_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "retry_handoffs"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SLOT_RE = re.compile(r"^(?P<prefix>.+)-(?P<media_type>photo|video)$")
RETRY_ACTION_TEXT = (
    "Chest-up or waist-up only. Hips, thighs, and the dress hemline never appear. Lena stands near the mirror at "
    "a 20-30 degree angle, actively checking or adjusting one gold hoop earring. No foreground phone, visible "
    "device screens, or direct posed full-torso portrait."
)

RETRY_ENVIRONMENT_TEXT = (
    "Home getting-ready vanity corner or bedroom vanity area. Visible mirror edge, never full mirror dominance. "
    "Vanity surface, a few products, chair, shoes, warm apartment light, and tasteful clutter. The composition must "
    "read as a real getting-ready vanity moment, never hotel-like."
)

RETRY_CINEMATOGRAPHY_TEXT = (
    "85mm or 50mm portrait compression, chest-up or waist-up framing only, natural skin detail, shallow depth of "
    "field, blue-hour ambient with warm lamp fill, candid apartment realism, non-studio. Hips, thighs, and the dress "
    "hemline never appear. No foreground phone, visible device screens, or direct posed full-torso portrait."
)

RETRY_TECHNICAL_APPEND = (
    " Keep the successful face, skin, red dress neckline, and clean anatomy. No fake freckles or poreless/plastic "
    "skin. Keep established Lena identity/body authority; slightly fuller is okay, not a hard gate."
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


class RetryHandoffError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _headroom_status(headroom: int) -> str:
    if headroom < readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW:
        return "blocked"
    if headroom < readiness_audit.PAYLOAD_HEADROOM_WARNING_BELOW:
        return "warning"
    return "ready"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _serialize_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RetryHandoffError("artifact_missing", f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RetryHandoffError("artifact_malformed", f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RetryHandoffError("artifact_malformed", f"{label} must be a JSON object: {path}")
    return value


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise RetryHandoffError(code, detail)


def _require_sha(raw: Any, *, code: str, label: str) -> str:
    value = str(raw or "")
    if not SHA256_RE.fullmatch(value):
        raise RetryHandoffError(code, f"{label} must be exactly 64 lowercase hexadecimal characters")
    return value


def _retry_slot_id(original_slot_id: str) -> str:
    match = SLOT_RE.fullmatch(original_slot_id)
    if not match:
        raise RetryHandoffError("slot_invalid", f"original slot_id does not end with -photo/-video: {original_slot_id}")
    return f"{match.group('prefix')}-retry01-{match.group('media_type')}"


def resolve_current_lena_soul(cli_runner=subprocess.run) -> dict[str, str]:
    completed = cli_runner(
        ["higgsfield", "soul-id", "list", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RetryHandoffError("soul_resolution_failed", str(completed.stderr or completed.stdout or "").strip())
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RetryHandoffError("soul_resolution_malformed", "higgsfield soul-id list did not return JSON") from exc
    if not isinstance(payload, list):
        raise RetryHandoffError("soul_resolution_malformed", "higgsfield soul-id list JSON must be a list")
    matches = [
        item for item in payload
        if isinstance(item, dict)
        and item.get("name") == "Lena"
        and item.get("type") == "soul_2"
        and item.get("status") == "completed"
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    ]
    if len(matches) != 1:
        raise RetryHandoffError("soul_resolution_ambiguous", f"expected exactly one completed Lena/soul_2 match, got {len(matches)}")
    item = matches[0]
    return {
        "id": item["id"],
        "name": item["name"],
        "type": item["type"],
        "status": item["status"],
    }


def retry_handoff_artifact_path(
    date_str: str,
    retry_slot_id: str,
    original_prompt_sha256: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    return output_root / date_str / f"{retry_slot_id}__{original_prompt_sha256[:12]}_retry_handoff.json"


def _load_packet(path_value: str) -> tuple[Path, dict[str, Any]]:
    path = approval_contract.resolve_repo_path(
        path_value,
        code="packet_path_missing",
        label="selected prompt input artifact path",
    )
    report = _read_json(path, label="selected prompt input artifact")
    return path, report


def _replace_sections(prompt_text: str) -> str:
    try:
        sections = pose_provenance.parse_provider_prompt_sections(prompt_text)
        sections["Environment"] = RETRY_ENVIRONMENT_TEXT
        sections["Cinematography"] = RETRY_CINEMATOGRAPHY_TEXT
        sections["Technical"] = sections["Technical"] + RETRY_TECHNICAL_APPEND
        return pose_provenance.serialize_provider_prompt_sections([
            (label, sections[label])
            for label in pose_provenance.PROVIDER_SECTION_ORDER
            if label in sections
        ])
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc


def _validate_execution_receipt(
    receipt_path: Path,
    handoff_facts: dict[str, Any],
) -> tuple[dict[str, Any], Path, dict[str, Any], Path, Path, str]:
    receipt = _read_json(receipt_path, label="generation execution receipt")
    _require(
        receipt.get("report_type") == approval_contract.RECEIPT_REPORT_TYPE,
        "receipt_report_type_mismatch",
        f"receipt report_type must be {approval_contract.RECEIPT_REPORT_TYPE!r}",
    )
    _require(
        receipt.get("schema_version") == approval_contract.RECEIPT_SCHEMA_VERSION,
        "receipt_schema_version_mismatch",
        f"receipt schema_version must be {approval_contract.RECEIPT_SCHEMA_VERSION!r}",
    )
    _require(
        receipt.get("receipt_type") == approval_contract.RECEIPT_TYPE,
        "receipt_type_mismatch",
        f"receipt receipt_type must be {approval_contract.RECEIPT_TYPE!r}",
    )
    _require(receipt.get("outcome") == "success", "receipt_not_successful", "only a successful original generation can seed this retry handoff")
    _require(
        receipt.get("handoff_artifact_path") == handoff_facts["handoff_repo_path"],
        "receipt_handoff_binding_mismatch",
        "receipt handoff_artifact_path does not match the exact reviewed handoff path",
    )
    _require(
        _require_sha(receipt.get("handoff_artifact_sha256"), code="receipt_handoff_sha_invalid", label="receipt handoff_artifact_sha256")
        == handoff_facts["handoff_sha256"],
        "receipt_handoff_sha_mismatch",
        "receipt handoff_artifact_sha256 does not match the current handoff bytes",
    )
    _require(receipt.get("date") == handoff_facts["date"], "receipt_date_binding_mismatch", "receipt date does not match the reviewed handoff")
    _require(receipt.get("slot_id") == handoff_facts["slot_id"], "receipt_slot_binding_mismatch", "receipt slot_id does not match the reviewed handoff")
    _require(
        receipt.get("prompt_sha256") == handoff_facts["prompt_sha256"],
        "receipt_prompt_sha_mismatch",
        "receipt prompt_sha256 does not match the reviewed handoff prompt sha",
    )
    _require(receipt.get("provider") == approval_contract.APPROVAL_PROVIDER, "receipt_provider_mismatch", "receipt provider is invalid")
    _require(receipt.get("executor") == approval_contract.APPROVAL_EXECUTOR, "receipt_executor_mismatch", "receipt executor is invalid")
    _require(receipt.get("model") == approval_contract.MODEL, "receipt_model_mismatch", "receipt model is invalid")
    _require(receipt.get("aspect_ratio") == approval_contract.ASPECT_RATIO, "receipt_aspect_mismatch", "receipt aspect ratio is invalid")
    _require(receipt.get("custom_reference_id") == handoff_facts["custom_reference_id"], "receipt_reference_mismatch", "receipt custom_reference_id does not match the reviewed handoff")

    output_path = Path(str(receipt.get("output_path") or "")).resolve()
    _require(output_path.is_file(), "receipt_output_missing", f"receipt output_path is missing: {output_path}")
    image_sha = _sha256_file(output_path)
    manifest_path = approval_contract.resolve_repo_path(
        str(receipt.get("actual_manifest_path") or receipt.get("expected_manifest_path") or ""),
        code="receipt_manifest_path_missing",
        label="receipt manifest path",
    )
    manifest = _read_json(manifest_path, label="generation manifest")
    _require(manifest.get("slot_id") == handoff_facts["slot_id"], "manifest_slot_binding_mismatch", "manifest slot_id does not match the reviewed handoff")
    _require(manifest.get("prompt_sha256") == handoff_facts["prompt_sha256"], "manifest_prompt_sha_mismatch", "manifest prompt_sha256 does not match the reviewed handoff")
    _require(manifest.get("saved_image_path") == str(output_path), "manifest_output_binding_mismatch", "manifest saved_image_path does not match the receipt output path")
    _require(
        manifest.get("provider_job_id") == receipt.get("provider_job_id"),
        "manifest_provider_job_binding_mismatch",
        "manifest provider_job_id does not match the execution receipt",
    )
    _require(
        manifest.get("provider_status") == receipt.get("provider_status"),
        "manifest_provider_status_binding_mismatch",
        "manifest provider_status does not match the execution receipt",
    )
    try:
        pose_provenance.validate_source_generation_pose_contract(
            manifest,
            handoff_facts["report"],
            root=ROOT,
        )
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc
    manifest_prompt = manifest.get("image_prompt")
    _require(
        isinstance(manifest_prompt, str)
        and _sha256_bytes(manifest_prompt.encode("utf-8")) == handoff_facts["prompt_sha256"],
        "manifest_prompt_text_mismatch",
        "source manifest image_prompt does not re-hash to the source handoff prompt",
    )
    return receipt, output_path, manifest, manifest_path, receipt_path, image_sha


def _build_retry_prompt(original_prompt: str, prompt_budget: int) -> tuple[str, str]:
    retry_prompt = _replace_sections(original_prompt)
    _require(len(retry_prompt) <= prompt_budget, "retry_prompt_budget_exceeded", f"retry prompt length {len(retry_prompt)} exceeds budget {prompt_budget}")
    return retry_prompt, _sha256_bytes(retry_prompt.encode("utf-8"))


def _build_hair_crown_retry_prompt(original_prompt: str, prompt_budget: int) -> tuple[str, str]:
    try:
        pose_provenance.parse_provider_prompt_sections(original_prompt)
        if HAIR_CROWN_CONSTRAINT in original_prompt:
            raise RetryHandoffError("retry_prompt_already_mutated", "original prompt already contains the hair-crown correction")
        retry_prompt = f"{original_prompt} {HAIR_CROWN_CONSTRAINT}"
        pose_provenance.parse_provider_prompt_sections(retry_prompt)
        _require(len(retry_prompt) <= prompt_budget, "retry_prompt_budget_exceeded", f"retry prompt length {len(retry_prompt)} exceeds budget {prompt_budget}")
        return retry_prompt, _sha256_bytes(retry_prompt.encode("utf-8"))
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc


def build_retry_handoff(
    *,
    handoff_artifact: Path,
    execution_receipt: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    reason_code: str | None = None,
    soul_record: dict[str, str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    handoff_facts = approval_contract.inspect_handoff_artifact(handoff_artifact)
    handoff_report = handoff_facts["report"]
    packet_path, packet_report = _load_packet(str(handoff_report.get("selected_prompt_input_artifact_path") or ""))
    packet_sha = _sha256_file(packet_path)
    _require(
        handoff_report.get("selected_prompt_input_artifact_sha256") == packet_sha,
        "handoff_packet_sha_mismatch",
        "handoff selected_prompt_input_artifact_sha256 does not match the current packet bytes",
    )
    original_prompt = str(handoff_report.get("structured_executor_inputs", {}).get("selected_prompt_text") or "")
    _require(bool(original_prompt), "handoff_prompt_missing", "handoff selected prompt text is missing")
    _require(
        _sha256_bytes(original_prompt.encode("utf-8")) == handoff_facts["prompt_sha256"],
        "handoff_prompt_sha_mismatch",
        "handoff selected prompt text does not match its recorded prompt sha",
    )
    try:
        bound_pose = pose_provenance.validate_pose_provenance(handoff_report.get("pose_provenance"))
        candidate_path = approval_contract.resolve_repo_path(
            bound_pose["selected_candidate_artifact_path"],
            code="pose_candidate_path_missing",
            label="pose selected candidate artifact path",
        )
        derived_pose = pose_provenance.build_candidate_pose_provenance(candidate_path, root=ROOT)
        pose_provenance.require_pose_bound_prompt(original_prompt, bound_pose)
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc
    _require(derived_pose == bound_pose, "pose_provenance_mismatch", "source handoff pose provenance no longer matches its candidate authority")
    prompt_budget = int(packet_report.get("compact_provider_prompt_budget") or 0)
    _require(prompt_budget > 0, "packet_prompt_budget_missing", "selected prompt packet must record a positive compact_provider_prompt_budget")
    receipt, output_path, manifest, manifest_path, receipt_path, image_sha = _validate_execution_receipt(
        execution_receipt.resolve(),
        handoff_facts,
    )
    hair_retry = reason_code == "hair_crown_forelock_artifact"
    if hair_retry:
        retry_prompt, retry_prompt_sha = _build_hair_crown_retry_prompt(original_prompt, prompt_budget)
        retry_purpose = HAIR_CROWN_RETRY_PURPOSE
        retry_constraints = {
            "correction_scope": "hair_only",
            "added_constraint": HAIR_CROWN_CONSTRAINT,
            "preserve": list(HAIR_CROWN_PRESERVES),
            "only_hair_crown_defect_may_change": True,
        }
        prompt_mutation = {
            "mode": "append_allowlisted_hair_crown_constraint",
            "mutation_type": "correct_hair_crown_forelock",
            "preserved_fields": list(HAIR_CROWN_PRESERVES),
        }
    else:
        retry_prompt, retry_prompt_sha = _build_retry_prompt(original_prompt, prompt_budget)
        retry_purpose = BACKGROUND_RETRY_PURPOSE
        retry_constraints = {
            "framing": "chest_up_or_waist_up_only",
            "exclude_regions": ["hips", "thighs", "dress_hemline"],
            "mirror_edge_required": True,
            "required_action": bound_pose["pose_text"],
            "vanity_composition_required": True,
            "visible_device_screens_forbidden": True,
            "foreground_phone_forbidden": True,
            "direct_full_torso_portrait_forbidden": True,
            "preserve_face_skin_dress_lighting_anatomy": True,
            "body_thickness_hard_gate": False,
            "mild_fullness_preference": True,
        }
        prompt_mutation = {
            "mode": "section_rewrite_preserving_subject_and_lighting_identity",
            "replaced_sections": ["Environment", "Cinematography", "Technical"],
            "preserved_sections": ["Subject", "Action", "Lighting/Style"],
        }
    try:
        pose_provenance.require_pose_bound_prompt(retry_prompt, bound_pose)
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc
    if hair_retry:
        soul = soul_record or resolve_current_lena_soul()
        _require(soul.get("name") == "Lena", "soul_name_mismatch", "retry Soul name must be Lena")
        _require(soul.get("type") == "soul_2", "soul_type_mismatch", "retry Soul type must be soul_2")
        _require(soul.get("status") == "completed", "soul_status_mismatch", "retry Soul status must be completed")
        _require(bool(str(soul.get("id") or "").strip()), "soul_id_missing", "retry Soul id is required")
        custom_reference_id = soul["id"]
        soul_name = soul["name"]
        soul_type = soul["type"]
        retry_soul_binding: dict[str, str] | None = dict(soul)
    else:
        custom_reference_id = handoff_facts["custom_reference_id"]
        soul_name = str(handoff_report.get("structured_executor_inputs", {}).get("soul_metadata", {}).get("name") or "Lena")
        soul_type = str(handoff_report.get("structured_executor_inputs", {}).get("soul_metadata", {}).get("type") or "")
        retry_soul_binding = None
    retry_prompt_length = len(retry_prompt)
    retry_prompt_headroom = prompt_budget - retry_prompt_length
    _require(
        retry_prompt_headroom >= readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW,
        "retry_prompt_headroom_too_low",
        f"retry prompt headroom {retry_prompt_headroom} is below the hard block threshold {readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW}",
    )
    retry_slot_id = _retry_slot_id(handoff_facts["slot_id"])
    artifact_path = retry_handoff_artifact_path(handoff_facts["date"], retry_slot_id, handoff_facts["prompt_sha256"], output_root)
    if artifact_path.exists():
        raise RetryHandoffError("retry_handoff_already_exists", f"retry handoff artifact already exists for this exact lineage: {artifact_path}")

    core = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "influencer_id": "lena",
        "date": handoff_facts["date"],
        "original_slot_id": handoff_facts["slot_id"],
        "retry_slot_id": retry_slot_id,
        "retry_attempt": 1,
        "retry_cap": 1,
        "retry_purpose": retry_purpose,
        "reason_code": reason_code or "background_identity_duplication",
        "source_handoff_artifact_path": handoff_facts["handoff_repo_path"],
        "source_handoff_artifact_sha256": handoff_facts["handoff_sha256"],
        "source_selected_prompt_input_artifact_path": repo_relative_path(packet_path),
        "source_selected_prompt_input_artifact_sha256": packet_sha,
        "source_pose_bound_content_packet_sha256": handoff_report["pose_bound_content_packet_sha256"],
        "source_execution_receipt_path": approval_contract.repo_relative_path(receipt_path),
        "source_execution_receipt_sha256": _sha256_file(receipt_path),
        "source_manifest_path": approval_contract.repo_relative_path(manifest_path),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "source_output_image_path": str(output_path),
        "source_output_image_sha256": image_sha,
        "source_original_prompt_sha256": handoff_facts["prompt_sha256"],
        "pose_provenance": bound_pose,
        "pose_provenance_fingerprint_sha256": bound_pose["pose_provenance_fingerprint_sha256"],
        "source_provider_job_evidence": {
            "provider_job_id": receipt.get("provider_job_id"),
            "provider_status": receipt.get("provider_status"),
            "provider_submission_may_have_occurred": receipt.get("provider_submission_may_have_occurred"),
            "subprocess_start_attempted": receipt.get("subprocess_start_attempted"),
        },
        "provider": approval_contract.APPROVAL_PROVIDER,
        "executor": approval_contract.APPROVAL_EXECUTOR,
        "model": approval_contract.MODEL,
        "aspect_ratio": approval_contract.ASPECT_RATIO,
        "custom_reference_id": custom_reference_id,
        "soul_name": soul_name,
        "soul_type": soul_type,
        "retry_soul_binding": retry_soul_binding,
        "historical_custom_reference_id": handoff_facts["custom_reference_id"],
        "retry_constraints": retry_constraints,
        "prompt_mutation": prompt_mutation,
        "retry_prompt_text": retry_prompt,
        "retry_prompt_sha256": retry_prompt_sha,
        "retry_prompt_budget": prompt_budget,
        "retry_prompt_length": retry_prompt_length,
        "retry_prompt_headroom": retry_prompt_headroom,
        "retry_prompt_headroom_status": _headroom_status(retry_prompt_headroom),
        "retry_prompt_headroom_policy": {
            "hard_block_below": readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW,
            "warning_below": readiness_audit.PAYLOAD_HEADROOM_WARNING_BELOW,
        },
        "final_action": FINAL_ACTION,
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "side_effects_performed": [],
        "exact_next_allowed_action": (
            "Separate explicit Nicolas authorization is required for one future live Higgsfield retry invocation bound to "
            f"source_handoff_sha256={handoff_facts['handoff_sha256']}, retry_slot_id={retry_slot_id}, "
            f"retry_prompt_sha256={retry_prompt_sha}. No second retry, upload, queue promotion, publishing, scheduling, "
            "analytics mutation, or provider call is authorized by this no-live retry handoff."
        ),
    }
    artifact = dict(core)
    artifact["created_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    artifact["retry_handoff_fingerprint_sha256"] = _sha256_bytes(_canonical_bytes(core))
    return artifact_path, artifact


def repo_relative_path(path: Path) -> str:
    return approval_contract.repo_relative_path(path)


def validate_retry_handoff_artifact(path: Path) -> dict[str, Any]:
    artifact_path = path.resolve()
    artifact = _read_json(artifact_path, label="retry handoff artifact")
    _require(artifact.get("report_type") == REPORT_TYPE, "wrong_report_type", f"artifact report_type must be {REPORT_TYPE!r}")
    _require(artifact.get("schema_version") == SCHEMA_VERSION, "wrong_schema_version", f"artifact schema_version must be {SCHEMA_VERSION!r}")
    _require(artifact.get("influencer_id") == "lena", "wrong_influencer", "artifact influencer_id must be 'lena'")
    _require(artifact.get("retry_attempt") == 1 and artifact.get("retry_cap") == 1, "retry_cap_invalid", "retry handoff retry attempt/cap must remain exactly 1/1")
    _require(
        artifact.get("retry_purpose") in {BACKGROUND_RETRY_PURPOSE, HAIR_CROWN_RETRY_PURPOSE},
        "retry_purpose_invalid",
        "retry_purpose is invalid",
    )
    _require(artifact.get("final_action") == FINAL_ACTION, "final_action_invalid", "final_action is invalid")
    _require(artifact.get("provider_authorized") is False, "provider_authorized_invalid", "provider_authorized must remain false")
    _require(artifact.get("provider_called") is False, "provider_called_invalid", "provider_called must remain false")
    _require(artifact.get("generation_performed") is False, "generation_performed_invalid", "generation_performed must remain false")
    _require(artifact.get("side_effects_performed") == [], "side_effects_invalid", "side_effects_performed must remain an empty list")

    expected_core = {key: value for key, value in artifact.items() if key not in {"created_at_utc", "retry_handoff_fingerprint_sha256"}}
    expected_fingerprint = _sha256_bytes(_canonical_bytes(expected_core))
    _require(
        artifact.get("retry_handoff_fingerprint_sha256") == expected_fingerprint,
        "fingerprint_mismatch",
        "retry_handoff_fingerprint_sha256 does not match the immutable body",
    )

    handoff_path = approval_contract.resolve_repo_path(
        str(artifact.get("source_handoff_artifact_path") or ""),
        code="source_handoff_path_missing",
        label="source_handoff_artifact_path",
    )
    handoff_facts = approval_contract.inspect_handoff_artifact(handoff_path)
    _require(
        artifact.get("source_handoff_artifact_path") == handoff_facts["handoff_repo_path"],
        "handoff_path_binding_mismatch",
        "source_handoff_artifact_path does not match the exact handoff repo-relative path",
    )
    _require(
        _require_sha(artifact.get("source_handoff_artifact_sha256"), code="source_handoff_sha_invalid", label="source_handoff_artifact_sha256")
        == handoff_facts["handoff_sha256"],
        "handoff_sha_mismatch",
        "source_handoff_artifact_sha256 does not match the current handoff bytes",
    )
    _require(artifact.get("date") == handoff_facts["date"], "date_binding_mismatch", "retry handoff date does not match the source handoff")
    _require(artifact.get("original_slot_id") == handoff_facts["slot_id"], "slot_binding_mismatch", "retry handoff original_slot_id does not match the source handoff")
    _require(
        artifact.get("source_original_prompt_sha256") == handoff_facts["prompt_sha256"],
        "original_prompt_sha_mismatch",
        "source_original_prompt_sha256 does not match the source handoff prompt sha",
    )
    try:
        bound_pose = pose_provenance.validate_pose_provenance(artifact.get("pose_provenance"))
        source_pose = pose_provenance.validate_pose_provenance(handoff_facts["report"].get("pose_provenance"))
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc
    _require(bound_pose == source_pose, "pose_provenance_mismatch", "retry handoff pose provenance differs from the source handoff")
    _require(
        artifact.get("source_pose_bound_content_packet_sha256")
        == handoff_facts["report"].get("pose_bound_content_packet_sha256"),
        "pose_bound_packet_sha_mismatch",
        "retry handoff source packet digest differs from the source generation handoff",
    )
    _require(
        artifact.get("pose_provenance_fingerprint_sha256") == bound_pose["pose_provenance_fingerprint_sha256"],
        "pose_provenance_fingerprint_mismatch",
        "retry pose fingerprint does not match the bound pose provenance",
    )
    if artifact.get("reason_code") == "hair_crown_forelock_artifact":
        soul = artifact.get("retry_soul_binding")
        _require(isinstance(soul, dict), "retry_soul_binding_missing", "hair retry handoff must carry retry_soul_binding")
        _require(soul.get("name") == "Lena", "soul_name_mismatch", "retry Soul name must be Lena")
        _require(soul.get("type") == "soul_2", "soul_type_mismatch", "retry Soul type must be soul_2")
        _require(soul.get("status") == "completed", "soul_status_mismatch", "retry Soul status must be completed")
        _require(artifact.get("custom_reference_id") == soul.get("id"), "custom_reference_id_mismatch", "retry handoff custom_reference_id must match retry Soul id")
        _require(artifact.get("soul_name") == soul.get("name"), "soul_name_mismatch", "retry handoff soul_name must match retry Soul binding")
        _require(artifact.get("soul_type") == soul.get("type"), "soul_type_mismatch", "retry handoff soul_type must match retry Soul binding")
    else:
        _require(artifact.get("custom_reference_id") == handoff_facts["custom_reference_id"], "custom_reference_id_mismatch", "background retry handoff must preserve the source reference id")
    _require(
        artifact.get("historical_custom_reference_id") == handoff_facts["custom_reference_id"],
        "historical_reference_mismatch",
        "retry handoff historical_custom_reference_id must preserve the source handoff reference",
    )
    _require(artifact.get("provider") == approval_contract.APPROVAL_PROVIDER, "provider_mismatch", "retry handoff provider is invalid")
    _require(artifact.get("executor") == approval_contract.APPROVAL_EXECUTOR, "executor_mismatch", "retry handoff executor is invalid")
    _require(artifact.get("model") == approval_contract.MODEL, "model_mismatch", "retry handoff model is invalid")
    _require(artifact.get("aspect_ratio") == approval_contract.ASPECT_RATIO, "aspect_mismatch", "retry handoff aspect ratio is invalid")

    packet_path, packet_report = _load_packet(str(artifact.get("source_selected_prompt_input_artifact_path") or ""))
    packet_sha = _sha256_file(packet_path)
    _require(
        artifact.get("source_selected_prompt_input_artifact_sha256") == packet_sha,
        "packet_sha_mismatch",
        "source_selected_prompt_input_artifact_sha256 does not match the current packet bytes",
    )
    prompt_budget = int(packet_report.get("compact_provider_prompt_budget") or 0)
    _require(prompt_budget > 0, "packet_prompt_budget_missing", "selected prompt packet must record a positive compact_provider_prompt_budget")

    receipt_path = approval_contract.resolve_repo_path(
        str(artifact.get("source_execution_receipt_path") or ""),
        code="source_receipt_path_missing",
        label="source_execution_receipt_path",
    )
    _require(
        artifact.get("source_execution_receipt_sha256") == _sha256_file(receipt_path),
        "receipt_sha_mismatch",
        "source_execution_receipt_sha256 does not match the current receipt bytes",
    )
    receipt, output_path, manifest, manifest_path, _, image_sha = _validate_execution_receipt(receipt_path, handoff_facts)
    _require(
        artifact.get("source_manifest_path") == approval_contract.repo_relative_path(manifest_path),
        "manifest_path_binding_mismatch",
        "source_manifest_path does not match the exact manifest repo-relative path",
    )
    _require(
        artifact.get("source_manifest_sha256") == _sha256_file(manifest_path),
        "manifest_sha_mismatch",
        "source_manifest_sha256 does not match the current manifest bytes",
    )
    _require(artifact.get("source_output_image_path") == str(output_path), "output_path_binding_mismatch", "source_output_image_path does not match the execution receipt output")
    _require(artifact.get("source_output_image_sha256") == image_sha, "output_image_sha_mismatch", "source_output_image_sha256 does not match the current output image bytes")
    _require(
        artifact.get("source_provider_job_evidence")
        == {
            "provider_job_id": receipt.get("provider_job_id"),
            "provider_status": receipt.get("provider_status"),
            "provider_submission_may_have_occurred": receipt.get("provider_submission_may_have_occurred"),
            "subprocess_start_attempted": receipt.get("subprocess_start_attempted"),
        },
        "provider_job_evidence_mismatch",
        "source_provider_job_evidence does not match the execution receipt",
    )
    _require(
        artifact.get("retry_slot_id") == _retry_slot_id(handoff_facts["slot_id"]),
        "retry_slot_id_invalid",
        "retry_slot_id does not match the canonical retry slot binding",
    )
    retry_prompt = str(artifact.get("retry_prompt_text") or "")
    _require(bool(retry_prompt), "retry_prompt_missing", "retry_prompt_text is missing")
    _require(
        artifact.get("retry_prompt_sha256") == _sha256_bytes(retry_prompt.encode("utf-8")),
        "retry_prompt_sha_mismatch",
        "retry_prompt_sha256 does not match the stored retry prompt bytes",
    )
    _require(
        artifact.get("retry_prompt_budget") == prompt_budget,
        "retry_prompt_budget_mismatch",
        "retry_prompt_budget does not match the source packet prompt budget",
    )
    _require(
        artifact.get("retry_prompt_length") == len(retry_prompt),
        "retry_prompt_length_mismatch",
        "retry_prompt_length does not match the stored retry prompt bytes",
    )
    retry_prompt_headroom = prompt_budget - len(retry_prompt)
    _require(
        artifact.get("retry_prompt_headroom") == retry_prompt_headroom,
        "retry_prompt_headroom_mismatch",
        "retry_prompt_headroom does not match the stored retry prompt bytes",
    )
    _require(
        artifact.get("retry_prompt_headroom_policy")
        == {
            "hard_block_below": readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW,
            "warning_below": readiness_audit.PAYLOAD_HEADROOM_WARNING_BELOW,
        },
        "retry_prompt_headroom_policy_mismatch",
        "retry_prompt_headroom_policy does not match the canonical readiness thresholds",
    )
    _require(
        artifact.get("retry_prompt_headroom_status") == _headroom_status(retry_prompt_headroom),
        "retry_prompt_headroom_status_mismatch",
        "retry_prompt_headroom_status does not match the canonical readiness thresholds",
    )
    _require(
        retry_prompt_headroom >= readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW,
        "retry_prompt_headroom_too_low",
        f"retry prompt headroom {retry_prompt_headroom} is below the hard block threshold {readiness_audit.PAYLOAD_HEADROOM_HARD_BLOCK_BELOW}",
    )
    if artifact.get("reason_code") == "hair_crown_forelock_artifact":
        expected_prompt, _ = _build_hair_crown_retry_prompt(
            str(handoff_facts["report"].get("structured_executor_inputs", {}).get("selected_prompt_text") or ""),
            prompt_budget,
        )
    else:
        expected_prompt, _ = _build_retry_prompt(
            str(handoff_facts["report"].get("structured_executor_inputs", {}).get("selected_prompt_text") or ""),
            prompt_budget,
        )
    _require(retry_prompt == expected_prompt, "retry_prompt_mutation_invalid", "retry_prompt_text does not match the canonical retry mutation")
    try:
        pose_provenance.require_pose_bound_prompt(retry_prompt, bound_pose)
    except pose_provenance.PoseProvenanceError as exc:
        raise RetryHandoffError(exc.code, exc.detail) from exc
    _require(len(retry_prompt) <= prompt_budget, "retry_prompt_budget_exceeded", f"retry prompt length {len(retry_prompt)} exceeds budget {prompt_budget}")
    return artifact


def load_retry_execution_source(path: Path) -> dict[str, Any]:
    return validate_retry_handoff_artifact(path)


def write_retry_handoff_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RetryHandoffError("retry_handoff_already_exists", f"refusing to overwrite an existing retry handoff artifact: {path}")
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(raw)
    try:
        temp.write_bytes(_serialize_json_bytes(artifact))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def evaluate_retry_handoff(
    *,
    handoff_artifact: Path,
    execution_receipt: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    write_artifact: bool = False,
    reason_code: str | None = None,
    soul_record: dict[str, str] | None = None,
) -> dict[str, Any]:
    path, artifact = build_retry_handoff(
        handoff_artifact=handoff_artifact,
        execution_receipt=execution_receipt,
        output_root=output_root,
        reason_code=reason_code,
        soul_record=soul_record,
    )
    state = "ready_for_executor_dry_run"
    if write_artifact:
        write_retry_handoff_artifact(path, artifact)
        state = "retry_handoff_written"
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "retry_handoff_artifact_path": str(path.resolve()),
        "retry_handoff_fingerprint_sha256": artifact["retry_handoff_fingerprint_sha256"],
        "date": artifact["date"],
        "original_slot_id": artifact["original_slot_id"],
        "retry_slot_id": artifact["retry_slot_id"],
        "retry_prompt_sha256": artifact["retry_prompt_sha256"],
        "retry_prompt_length": len(artifact["retry_prompt_text"]),
        "retry_prompt_headroom": artifact["retry_prompt_headroom"],
        "retry_prompt_headroom_status": artifact["retry_prompt_headroom_status"],
        "retry_prompt_headroom_policy": artifact["retry_prompt_headroom_policy"],
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "exact_next_allowed_action": artifact["exact_next_allowed_action"],
        "side_effects_performed": [],
    }


def _blocked_report(path: Path | None, exc: RetryHandoffError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "blocked",
        "input_path": str(path.resolve()) if path is not None else None,
        "retry_handoff_artifact_path": None,
        "validation_results": {"error_code": exc.code, "error_detail": exc.detail},
        "provider_authorized": False,
        "provider_called": False,
        "generation_performed": False,
        "side_effects_performed": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare one bounded no-live Higgsfield retry handoff artifact.")
    parser.add_argument("--handoff-artifact", required=True, type=Path)
    parser.add_argument("--execution-receipt", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--write-artifact", action="store_true")
    parser.add_argument("--reason-code")
    args = parser.parse_args()
    try:
        report = evaluate_retry_handoff(
            handoff_artifact=args.handoff_artifact,
            execution_receipt=args.execution_receipt,
            output_root=args.output_root,
            write_artifact=args.write_artifact,
            reason_code=args.reason_code,
        )
    except RetryHandoffError as exc:
        print(json.dumps(_blocked_report(args.handoff_artifact, exc), sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
