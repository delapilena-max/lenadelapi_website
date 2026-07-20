from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Optional

from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.influencer_nodes.lena import autonomy_ladder  # noqa: E402
from pipeline.identity import lena_higgsfield_identity as identity  # noqa: E402
from pipeline.prompting import lena_prompt_brain  # noqa: E402
from pipeline.qa import lena_higgsfield_failure_memory as failure_memory  # noqa: E402
from pipeline.qa import lena_photo_qa  # noqa: E402
from tools import lena_higgsfield_generation_approval_v1 as approval  # noqa: E402
from tools import lena_standing_autonomy_policy_v1 as standing_autonomy  # noqa: E402
from tools.lena_structured_visual_tool_v1 import (  # noqa: E402
    StructuredVisualImage,
    StructuredVisualToolError,
    call_anthropic_structured_visual_tool,
)
from tools import lena_higgsfield_qa_bridge_v1 as qa_bridge  # noqa: E402
from tools.strategy import lena_execute_selected_candidate_v1 as handoff  # noqa: E402
from tools.strategy import lena_execute_retry_decision_v1 as retry_handoff  # noqa: E402
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector  # noqa: E402


SCHEMA_VERSION = "lena_photo_qa_disposition_v1"
VISUAL_SCHEMA_VERSION = "lena_visual_observations_v1"
REFERENCE_AUTHORITY_SCHEMA_VERSION = "lena_identity_reference_authority_v1"
MODEL_AUTHORITY_SCHEMA_VERSION = "lena_visual_model_authority_v1"
MODEL_AUTHORITY_ID = "lena_visual_model_authority_v1"
APPROVED_VISUAL_PROVIDER = "anthropic"
APPROVED_VISUAL_MODEL = "claude-sonnet-5"
MODEL_AUTHORITY_KEYS = {
    "schema_version", "influencer_id", "authority_id", "provider", "approved_model",
}
OUTPUT_ROOT = ROOT / "pipeline" / "asset_review" / "lena"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}
ALLOWED_OBSERVATION_STATUSES = {"pass", "fail", "unreviewed"}
POSE_BANK_PATH = ROOT / "pipeline/prompt_banks/lena/lena_pose_body_language_bank_v1.json"
EXPRESSION_BANK_PATH = ROOT / "pipeline/prompt_banks/lena/lena_expression_gaze_bank_v1.json"
WARDROBE_CATALOG_PATH = ROOT / "pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json"
PROMPT_BRAIN_PATH = ROOT / "pipeline/prompting/lena_prompt_brain.py"
CURRENT_LENA_SOUL_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
LENA_REFERENCE_MANIFEST_PATH = (
    "pipeline/higgsfield_debug/2026-07-09/prompt_isolation_tests/"
    "readypack0709-pack004-08-wardrobe-test-c/result_manifest.json"
)

HARD_STOP_CODES = {
    "provenance_mismatch",
    "decision_binding_mismatch",
    "image_hash_mismatch",
    "identity_evidence_invalid",
    "wrong_person_or_identity_collapse",
    "unsafe_pornographic_presentation",
    "prohibited_scene",
    "failure_memory_pattern_hard_excluded",
    "corrupt_or_untrusted_evidence",
    "visual_review_unavailable",
}

RETRYABLE_CODES = {
    "recoverable_identity_drift",
    "required_action_missed",
    "gaze_missed",
    "posture_missed",
    "prop_interaction_failed",
    "required_visual_evidence_missing",
    "hand_or_anatomy_defect",
    "reflection_or_contact_error",
    "wardrobe_realization_failed",
    "environment_incoherent",
    "composition_below_standard",
    "lighting_below_standard",
    "overprocessed_result",
    "visual_clutter",
    "character_fit_miss",
}

OBSERVATION_KEYS = (
    "face_continuity",
    "hair_continuity",
    "apparent_age",
    "skin_continuity",
    "body_silhouette_continuity",
    "distinctive_marks",
    "lena_reference_soul_consistency",
    "no_background_identity_duplication",
    "required_action",
    "gaze",
    "posture",
    "prop_interaction",
    "required_visual_evidence",
    "environment_plausibility",
    "wardrobe_consistency",
    "anatomy",
    "hands_fingers_limbs",
    "reflections",
    "object_contact",
    "impossible_geometry_body_distortion",
    "composition",
    "lighting",
    "premium_visual_discipline",
    "natural_asymmetry",
    "overprocessed_appearance",
    "visual_clutter",
    "canonical_lena_personality",
    "no_needy_desperate_framing",
    "no_fake_rich_signaling",
    "no_melodrama",
    "no_audience_controlled_identity",
    "platform_safe_framing",
    "no_pornographic_presentation",
    "no_unsafe_exposure",
    "no_excessive_sexual_signal_stacking",
    "contextual_swimwear",
    "dimensions",
    "file_integrity",
    "format",
    "visible_artifacts",
    "downstream_compatibility",
)
LOCAL_TECHNICAL_KEYS = ("dimensions", "file_integrity", "format", "downstream_compatibility")
VISUAL_OBSERVATION_KEYS = tuple(key for key in OBSERVATION_KEYS if key not in LOCAL_TECHNICAL_KEYS)

ALLOWED_REASON_CODES_BY_OBSERVATION = {
    "face_continuity": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "hair_continuity": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "apparent_age": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "skin_continuity": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "body_silhouette_continuity": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "distinctive_marks": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "lena_reference_soul_consistency": {"recoverable_identity_drift", "wrong_person_or_identity_collapse"},
    "no_background_identity_duplication": {"wrong_person_or_identity_collapse"},
    "required_action": {"required_action_missed"},
    "gaze": {"gaze_missed"},
    "posture": {"posture_missed"},
    "prop_interaction": {"prop_interaction_failed", "reflection_or_contact_error"},
    "required_visual_evidence": {"required_visual_evidence_missing"},
    "environment_plausibility": {"environment_incoherent", "prohibited_scene"},
    "wardrobe_consistency": {"wardrobe_realization_failed"},
    "anatomy": {"hand_or_anatomy_defect"},
    "hands_fingers_limbs": {"hand_or_anatomy_defect"},
    "reflections": {"reflection_or_contact_error"},
    "object_contact": {"reflection_or_contact_error"},
    "impossible_geometry_body_distortion": {"hand_or_anatomy_defect"},
    "composition": {"composition_below_standard"},
    "lighting": {"lighting_below_standard"},
    "premium_visual_discipline": {"composition_below_standard"},
    "natural_asymmetry": {"overprocessed_result"},
    "overprocessed_appearance": {"overprocessed_result"},
    "visual_clutter": {"visual_clutter"},
    "canonical_lena_personality": {"character_fit_miss"},
    "no_needy_desperate_framing": {"character_fit_miss"},
    "no_fake_rich_signaling": {"character_fit_miss"},
    "no_melodrama": {"character_fit_miss"},
    "no_audience_controlled_identity": {"character_fit_miss", "prohibited_scene"},
    "platform_safe_framing": {"unsafe_pornographic_presentation"},
    "no_pornographic_presentation": {"unsafe_pornographic_presentation"},
    "no_unsafe_exposure": {"unsafe_pornographic_presentation"},
    "no_excessive_sexual_signal_stacking": {"unsafe_pornographic_presentation", "character_fit_miss"},
    "contextual_swimwear": {"unsafe_pornographic_presentation", "wardrobe_realization_failed"},
    "visible_artifacts": {"composition_below_standard", "hand_or_anatomy_defect", "reflection_or_contact_error"},
}
assert set(ALLOWED_REASON_CODES_BY_OBSERVATION) == set(VISUAL_OBSERVATION_KEYS)


class BoundaryError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class CollisionError(BoundaryError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_bytes(value: Any) -> bytes:
    return selector._canonical_bytes(value)


def _read_json_object(path: Path, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise BoundaryError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryError(code, f"could not parse {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BoundaryError(code, f"{label} must contain a JSON object: {path}")
    return value


def _inspect_image(path: Path, *, generated: bool) -> dict[str, Any]:
    if not path.is_file():
        raise BoundaryError("corrupt_or_untrusted_evidence", f"image does not exist: {path}")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise BoundaryError("corrupt_or_untrusted_evidence", f"image is corrupt or unreadable: {path}: {exc}") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise BoundaryError("corrupt_or_untrusted_evidence", f"unsupported image format {image_format!r}: {path}")
    if width <= 0 or height <= 0:
        raise BoundaryError("corrupt_or_untrusted_evidence", f"invalid image dimensions {width}x{height}: {path}")
    if generated and (width != identity.EXPECTED_WIDTH or height != identity.EXPECTED_HEIGHT):
        raise BoundaryError(
            "corrupt_or_untrusted_evidence",
            f"generated image dimensions {width}x{height} do not match approved Higgsfield dimensions "
            f"{identity.EXPECTED_WIDTH}x{identity.EXPECTED_HEIGHT}",
        )
    return {
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "format": image_format,
        "width": width,
        "height": height,
    }


def parse_reference_spec(value: str) -> tuple[Path, str]:
    if "::" not in value:
        raise BoundaryError(
            "identity_evidence_invalid",
            "identity reference must use PATH::SHA256 so authority is explicit and hash-bound",
        )
    raw_path, expected_sha = value.rsplit("::", 1)
    if not raw_path or not SHA256_RE.fullmatch(expected_sha):
        raise BoundaryError("identity_evidence_invalid", f"invalid identity-reference specification: {value!r}")
    return Path(raw_path), expected_sha


def _git_show_bytes(commit: str, path: Path) -> bytes:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise BoundaryError("identity_evidence_invalid", f"authority artifact must be inside the repository: {path}") from exc
    try:
        return handoff._git_bytes("show", f"{commit}:{relative}")
    except handoff.ConsumerError as exc:
        raise BoundaryError("identity_evidence_invalid", f"authority artifact is not committed at {commit}: {relative}") from exc


def _git_blob_oid(commit: str, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise BoundaryError("identity_evidence_invalid", f"authority input must be inside the repository: {path}") from exc
    result = subprocess.run(
        ["git", "rev-parse", f"{commit}:{relative}"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    oid = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise BoundaryError("identity_evidence_invalid", f"authority input is not committed at {commit}: {relative}")
    return oid


def _require_crlf_lf_equivalent(path: Path, committed: bytes) -> None:
    if not path.is_file():
        raise BoundaryError("identity_evidence_invalid", f"authority input does not exist locally: {path}")
    local = path.read_bytes()
    if committed.replace(b"\r\n", b"\n") != local.replace(b"\r\n", b"\n"):
        raise BoundaryError("identity_evidence_invalid", f"local authority input differs from committed content: {path}")


def _exact_lexical_repo_path(raw: str, label: str) -> Path:
    if not raw or "\\" in raw:
        raise BoundaryError("identity_evidence_invalid", f"{label} must use one canonical repository-relative path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts) or relative.as_posix() != raw:
        raise BoundaryError("identity_evidence_invalid", f"{label} must use one canonical repository-relative path")
    lexical = ROOT.resolve().joinpath(*relative.parts)
    try:
        resolved = lexical.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BoundaryError("identity_evidence_invalid", f"{label} does not exist: {raw}") from exc
    if resolved != lexical:
        raise BoundaryError("identity_evidence_invalid", f"{label} may not use a symlink or path alias")
    return lexical


def _committed_json_authority(
    path: Path, expected_sha: str, commit: str, schema: str, *, require_self_commit: bool = True,
    exact_keys: Optional[set[str]] = None,
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(str(expected_sha)):
        raise BoundaryError("identity_evidence_invalid", "authority artifact requires an explicit SHA-256")
    committed = _git_show_bytes(commit, path)
    if _sha256_bytes(committed) != expected_sha:
        raise BoundaryError("identity_evidence_invalid", "authority artifact SHA-256 does not match committed bytes")
    _require_crlf_lf_equivalent(path, committed)
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(committed.decode("utf-8-sig"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise BoundaryError("identity_evidence_invalid", "authority artifact is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        raise BoundaryError("identity_evidence_invalid", f"authority artifact must use schema {schema}")
    if value.get("influencer_id") != "lena":
        raise BoundaryError("identity_evidence_invalid", "authority artifact influencer/commit binding is invalid")
    if require_self_commit and value.get("authority_commit") != commit:
        raise BoundaryError("identity_evidence_invalid", "authority artifact influencer/commit binding is invalid")
    if exact_keys is not None and set(value) != exact_keys:
        raise BoundaryError("identity_evidence_invalid", "authority artifact fields do not match the exact schema")
    return value


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}", ancestor) or not re.fullmatch(r"[0-9a-f]{40}", descendant):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT, capture_output=True, check=False,
    )
    return result.returncode == 0


def _validate_reference_metadata(authority: dict[str, Any], authority_commit: str) -> None:
    metadata = authority.get("reference_metadata")
    if not isinstance(metadata, list) or len(metadata) != 1 or not isinstance(metadata[0], dict):
        raise BoundaryError("identity_evidence_invalid", "trusted reference authority metadata is incomplete")
    item = metadata[0]
    required = {
        "role": "canonical_face_hair_and_full_body",
        "format": "PNG",
        "width": 1152,
        "height": 2048,
        "provider": "higgsfield",
        "provider_job_id": "ada3a4da-84ba-4f59-adce-0b31f51706a3",
        "job_type": "text2image_soul_v2",
        "custom_reference_id": CURRENT_LENA_SOUL_ID,
        "authority_scope": "identity_continuity_not_style",
    }
    if any(item.get(key) != value for key, value in required.items()):
        raise BoundaryError("identity_evidence_invalid", "trusted reference authority metadata is invalid")
    manifest_raw = item.get("provenance_manifest")
    manifest_sha = item.get("provenance_manifest_sha256")
    manifest_oid = item.get("provenance_manifest_git_blob_oid")
    if (
        manifest_raw != LENA_REFERENCE_MANIFEST_PATH or not SHA256_RE.fullmatch(str(manifest_sha))
        or not isinstance(manifest_oid, str) or not re.fullmatch(r"[0-9a-f]{40}", manifest_oid)
    ):
        raise BoundaryError("identity_evidence_invalid", "reference provenance manifest binding is incomplete")
    manifest_path = _exact_lexical_repo_path(manifest_raw, "reference provenance manifest")
    committed = _git_show_bytes(authority_commit, manifest_path)
    if _sha256_bytes(committed) != manifest_sha or _git_blob_oid(authority_commit, manifest_path) != manifest_oid:
        raise BoundaryError("identity_evidence_invalid", "reference provenance manifest committed-byte binding is invalid")
    _require_crlf_lf_equivalent(manifest_path, committed)
    try:
        manifest = json.loads(committed.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryError("identity_evidence_invalid", "reference provenance manifest is invalid JSON") from exc
    expected_manifest = {
        "provider": required["provider"], "provider_job_id": required["provider_job_id"],
        "provider_status": "completed", "job_type": required["job_type"],
        "custom_reference_id": required["custom_reference_id"],
    }
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise BoundaryError("identity_evidence_invalid", "reference provenance manifest identity binding is invalid")


def _validate_references(
    specs: Iterable[tuple[Path, str]], authority_path: Path, authority_sha: str, authority_commit: str
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    authority = _committed_json_authority(
        authority_path, authority_sha, authority_commit, REFERENCE_AUTHORITY_SCHEMA_VERSION,
        require_self_commit=False,
    )
    reference_commit = authority.get("authority_commit")
    if not isinstance(reference_commit, str) or not _git_is_ancestor(reference_commit, authority_commit):
        raise BoundaryError("identity_evidence_invalid", "reference authority commit must be an ancestor of the consuming commit")
    authority_id = authority.get("authority_id")
    allowed = authority.get("references")
    declared_set_sha = authority.get("reference_set_sha256")
    if not isinstance(authority_id, str) or not authority_id.strip() or not isinstance(allowed, list):
        raise BoundaryError("identity_evidence_invalid", "trusted reference authority is incomplete")
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, expected_sha in specs:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise BoundaryError("identity_evidence_invalid", f"identity reference must be repository-contained: {path}") from exc
        committed_reference = _git_show_bytes(reference_commit, resolved)
        if _sha256_bytes(committed_reference) != expected_sha:
            raise BoundaryError("identity_evidence_invalid", f"identity reference is not hash-identical to committed authority bytes: {relative}")
        inspected = _inspect_image(resolved, generated=False)
        if inspected["sha256"] != expected_sha:
            raise BoundaryError(
                "identity_evidence_invalid",
                f"identity-reference hash mismatch for {path}: expected {expected_sha}, got {inspected['sha256']}",
            )
        if inspected["sha256"] in seen:
            raise BoundaryError("identity_evidence_invalid", "duplicate identity-reference content is ambiguous")
        seen.add(inspected["sha256"])
        inspected["authority_relative_path"] = relative
        references.append(inspected)
    if not references:
        raise BoundaryError("identity_evidence_invalid", "at least one explicit hash-bound identity reference is required")
    reference_set_sha = _sha256_bytes(
        _canonical_bytes(
            {
                "authority_id": authority_id.strip(),
                "references": [{"path": item["authority_relative_path"], "sha256": item["sha256"]} for item in references],
            }
        )
    )
    actual = [{"path": item["authority_relative_path"], "sha256": item["sha256"]} for item in references]
    if allowed != actual or declared_set_sha != reference_set_sha:
        raise BoundaryError("identity_evidence_invalid", "reference set is not exactly authorized by the committed authority artifact")
    _validate_reference_metadata(authority, reference_commit)
    return references, reference_set_sha, {
        "authority_id": authority_id,
        "authority_artifact_path": str(authority_path.resolve()),
        "authority_artifact_sha256": authority_sha,
        "authority_commit": reference_commit,
        "authority_artifact_commit": authority_commit,
    }


def _validate_model_authority(path: Path, expected_sha: str, commit: str, provider: str, model: str) -> dict[str, Any]:
    authority = _committed_json_authority(
        path, expected_sha, commit, MODEL_AUTHORITY_SCHEMA_VERSION,
        require_self_commit=False, exact_keys=MODEL_AUTHORITY_KEYS,
    )
    if authority.get("authority_id") != MODEL_AUTHORITY_ID:
        raise BoundaryError("visual_review_unavailable", "visual model authority ID is invalid")
    if provider != APPROVED_VISUAL_PROVIDER or authority.get("provider") != APPROVED_VISUAL_PROVIDER:
        raise BoundaryError("visual_review_unavailable", "visual review provider must be independently approved as anthropic")
    approved_model = authority.get("approved_model")
    if approved_model != APPROVED_VISUAL_MODEL or model != APPROVED_VISUAL_MODEL or approved_model != model:
        raise BoundaryError("visual_review_unavailable", "requested visual model does not exactly match committed model authority")
    return {"path": str(path.resolve()), "sha256": expected_sha, "provider": provider, "approved_model": approved_model}


def _validate_selected_decision(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        artifact = handoff._read_artifact(path)
        candidate = handoff._validate_shape(artifact)
        handoff._validate_fingerprint(artifact)
        handoff._validate_authority(artifact)
    except handoff.ConsumerError as exc:
        raise BoundaryError("decision_binding_mismatch", f"{exc.code}: {exc.detail}") from exc
    return artifact, candidate


def _retry_candidate_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": f"{artifact['retry_slot_id']}::{artifact['recipe_id']}::{artifact['hook_id']}::retry01",
        "slot_id": artifact["retry_slot_id"],
        "lane": artifact["lane"],
        "activity": artifact.get("pose") or "",
        "recipe_id": artifact["recipe_id"],
        "hook_id": artifact["hook_id"],
        "hook_text": artifact.get("hook_text"),
        "caption_seed": artifact.get("caption_seed"),
        "pose": artifact.get("pose"),
        "pose_body_language_id": artifact.get("pose_body_language_id"),
        "wardrobe_outfit_id": artifact.get("wardrobe_outfit_id"),
        "visual_style": artifact.get("visual_style"),
        "camera_text": artifact.get("camera_text"),
        "lighting_text": artifact.get("lighting_text"),
        "prompt_sha256": artifact["retry_prompt_sha256"],
    }


def _validate_retry_decision(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        artifact = retry_handoff._validate_retry_decision_artifact(path)
        correction_path = Path(str(artifact.get("source_retry_plan_correction_artifact_path") or "")).resolve()
        _, _, _, original_decision, _, _, _ = retry_handoff._validate_correction_artifact(correction_path)
    except retry_handoff.RetryDecisionError as exc:
        raise BoundaryError("decision_binding_mismatch", f"{exc.code}: {exc.detail}") from exc
    artifact = dict(artifact)
    artifact["authority_commit"] = original_decision["authority_commit"]
    candidate = _retry_candidate_from_artifact(artifact)
    return artifact, candidate


def _validate_decision(path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    try:
        artifact = handoff._read_artifact(path)
    except handoff.ConsumerError as exc:
        raise BoundaryError("decision_binding_mismatch", f"{exc.code}: {exc.detail}") from exc
    schema_version = artifact.get("schema_version")
    if schema_version == selector.SCHEMA_VERSION:
        decision, candidate = _validate_selected_decision(path)
        return decision, candidate, "selected_candidate"
    if schema_version == retry_handoff.SCHEMA_VERSION:
        decision, candidate = _validate_retry_decision(path)
        return decision, candidate, "retry_decision"
    raise BoundaryError("decision_binding_mismatch", "wrong_schema_version: artifact is not a Lena pre-generation candidate decision or retry decision")


def _resolve_generation_binding_context(
    decision_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, Any] | None]:
    try:
        artifact = handoff._read_artifact(decision_path)
    except handoff.ConsumerError as exc:
        raise BoundaryError("decision_binding_mismatch", f"{exc.code}: {exc.detail}") from exc
    report_type = artifact.get("report_type")
    if report_type == standing_autonomy.AUTH_REPORT_TYPE:
        auth = standing_autonomy.validate_cycle_authorization_artifact(
            decision_path,
            allow_consumed=True,
            require_not_expired=False,
        )
        handoff_facts = approval.inspect_handoff_artifact(
            Path(str(auth["artifact"]["generation_handoff_artifact_path"]))
        )
        decision, candidate = _validate_selected_decision(Path(handoff_facts["selected_candidate_path"]))
        standing_autonomy.validate_cycle_authorization_artifact(
            decision_path,
            handoff_report=handoff_facts["report"],
            allow_consumed=True,
            require_not_expired=False,
        )
        return decision, candidate, "authorization_bound_handoff", handoff_facts
    decision, candidate, decision_kind = _validate_decision(decision_path)
    return decision, candidate, decision_kind, None


def _validate_manifest(
    path: Path,
    decision: dict[str, Any],
    candidate: dict[str, Any],
    image: dict[str, Any],
    decision_kind: str,
    *,
    provider_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _read_json_object(path, "provenance_mismatch", "Higgsfield result manifest")
    provider_binding = provider_binding if isinstance(provider_binding, dict) else {}
    expected_lane = str(provider_binding.get("provider_lane") or candidate["lane"])
    expected_prompt_sha256 = str(provider_binding.get("provider_prompt_sha256") or candidate["prompt_sha256"])
    expected_slot_id = str(provider_binding.get("slot_id") or candidate["slot_id"])
    expected = {
        "provider": "higgsfield",
        "date": decision["as_of_date"],
        "slot_id": expected_slot_id,
        "lane": expected_lane,
        "prompt_sha256": expected_prompt_sha256,
    }
    mismatches = [f"{key}: expected {value!r}, got {manifest.get(key)!r}" for key, value in expected.items() if manifest.get(key) != value]
    if mismatches:
        raise BoundaryError("provenance_mismatch", "manifest binding mismatch: " + "; ".join(mismatches))
    prompt = manifest.get("image_prompt")
    if not isinstance(prompt, str) or _sha256_bytes(prompt.encode("utf-8")) != expected_prompt_sha256:
        raise BoundaryError("provenance_mismatch", "manifest prompt text does not re-hash to the selected prompt SHA")
    try:
        bridge_image = qa_bridge._resolve_image_path(manifest).resolve()
    except qa_bridge.ResolveError as exc:
        raise BoundaryError("provenance_mismatch", str(exc)) from exc
    if bridge_image != Path(image["path"]):
        raise BoundaryError("provenance_mismatch", "manifest saved_image_path does not match the explicit generated image")
    if manifest.get("provider_status") != "completed":
        raise BoundaryError("provenance_mismatch", "manifest provider_status must be completed")
    required_text = (
        "job_type", "custom_reference_id", "cli_soul_name", "cli_soul_type", "provider_job_id",
        "pose_body_language_id", "pose_body_language_label", "pose_text", "expression_gaze_id", "expression_gaze_label",
        "expression_text", "wardrobe_outfit_id", "wardrobe_outfit_name",
        "wardrobe_silhouette_class", "effective_wardrobe_silhouette_class", "image_format_detected",
    )
    for key in required_text:
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise BoundaryError("provenance_mismatch", f"manifest is missing required generation provenance: {key}")
    if type(manifest.get("expression_safe_fallback_used")) is not bool:
        raise BoundaryError("provenance_mismatch", "manifest expression_safe_fallback_used must be a boolean")
    if "expression_safe_fallback_reason" not in manifest:
        raise BoundaryError("provenance_mismatch", "manifest is missing expression_safe_fallback_reason")
    conflict_terms = manifest.get("expression_scene_conflict_terms")
    if not isinstance(conflict_terms, list) or any(not isinstance(item, str) or not item for item in conflict_terms):
        raise BoundaryError("provenance_mismatch", "manifest expression_scene_conflict_terms must be a list of nonempty strings")
    retry_count = manifest.get("retry_count")
    if type(retry_count) is not int:
        raise BoundaryError("provenance_mismatch", "manifest retry_count must be an integer")
    exact_context = {
        "job_type": identity.EXPECTED_JOB_TYPE,
        "cli_soul_name": identity.EXPECTED_SOUL_NAME,
        "cli_soul_type": identity.EXPECTED_SOUL_TYPE,
        "pose_body_language_id": candidate.get("pose_body_language_id"),
        "pose_body_language_label": candidate.get("pose"),
        "wardrobe_outfit_id": candidate.get("wardrobe_outfit_id"),
        "effective_wardrobe_silhouette_class": candidate.get("visual_style"),
        "live_attempt_count": 1,
        "image_format_detected": {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image["format"]],
    }
    for key in ("live_attempt_count", "retry_count"):
        if type(manifest.get(key)) is not int:
            raise BoundaryError("provenance_mismatch", f"manifest {key} must be an integer")
    if decision_kind in {"selected_candidate", "authorization_bound_handoff"}:
        exact_context["retry_count"] = 0
    else:
        retry_contract = manifest.get("retry_execution_contract")
        if not isinstance(retry_contract, dict):
            raise BoundaryError("provenance_mismatch", "retry manifest must carry retry_execution_contract")
        expected_retry_contract = {
            "schema_version": retry_handoff.RETRY_EXECUTION_CONTRACT_SCHEMA_VERSION,
            "retry_decision_fingerprint_sha256": decision["retry_decision_fingerprint_sha256"],
            "retry_attempt": decision["retry_attempt"],
            "retry_cap": decision["retry_cap"],
            "original_slot_id": decision["original_slot_id"],
            "retry_slot_id": decision["retry_slot_id"],
            "original_prompt_sha256": decision["original_prompt_sha256"],
            "retry_prompt_sha256": decision["retry_prompt_sha256"],
            "background_identity_constraint": decision["prompt_mutation"]["added_constraint"],
            "source_original_decision_fingerprint_sha256": decision["source_original_decision_fingerprint_sha256"],
            "source_original_manifest_path": decision["source_original_manifest_path"],
            "source_original_manifest_sha256": decision["source_original_manifest_sha256"],
            "source_original_provider_job_evidence": decision["source_original_provider_job_evidence"],
            "source_valid_human_rejection_artifact_path": decision["source_valid_human_rejection_artifact_path"],
            "source_valid_human_rejection_artifact_sha256": decision["source_valid_human_rejection_artifact_sha256"],
            "source_invalid_retry_plan_artifact_path": decision["source_invalid_retry_plan_artifact_path"],
            "source_invalid_retry_plan_artifact_sha256": decision["source_invalid_retry_plan_artifact_sha256"],
            "source_retry_plan_correction_artifact_path": decision["source_retry_plan_correction_artifact_path"],
            "source_retry_plan_correction_artifact_sha256": decision["source_retry_plan_correction_artifact_sha256"],
        }
        if retry_contract != expected_retry_contract:
            raise BoundaryError("provenance_mismatch", "retry manifest retry_execution_contract does not match the retry decision lineage exactly")
        # Existing executor manifests write retry_count=0 even for bounded retries; bind to the real on-disk contract rather than inventing a new meaning.
        exact_context["retry_count"] = 0
    mismatches = [f"{key}: expected {value!r}, got {manifest.get(key)!r}" for key, value in exact_context.items() if manifest.get(key) != value]
    if mismatches:
        raise BoundaryError("provenance_mismatch", "manifest generation context mismatch: " + "; ".join(mismatches))
    prompt_context = manifest["image_prompt"]
    embedded_context = {
        "pose_text": manifest["pose_text"],
        "expression_text": manifest["expression_text"],
    }
    absent = [key for key, value in embedded_context.items() if value.casefold() not in prompt_context.casefold()]
    if absent:
        raise BoundaryError("provenance_mismatch", "manifest context is not bound to image_prompt: " + ", ".join(absent))
    _validate_manifest_bank_context(manifest, candidate, decision["authority_commit"])
    return manifest


def _validate_manifest_bank_context(
    manifest: dict[str, Any], candidate: dict[str, Any], authority_commit: str
) -> None:
    try:
        pose_bank = json.loads(_git_show_bytes(authority_commit, POSE_BANK_PATH).decode("utf-8-sig"))
        expression_bank = json.loads(_git_show_bytes(authority_commit, EXPRESSION_BANK_PATH).decode("utf-8-sig"))
        wardrobe_catalog = json.loads(_git_show_bytes(authority_commit, WARDROBE_CATALOG_PATH).decode("utf-8-sig"))
        committed_prompt_brain = _git_show_bytes(authority_commit, PROMPT_BRAIN_PATH)
    except (UnicodeError, json.JSONDecodeError, BoundaryError) as exc:
        raise BoundaryError("provenance_mismatch", f"canonical generation context could not be loaded: {exc}") from exc
    try:
        _require_crlf_lf_equivalent(PROMPT_BRAIN_PATH, committed_prompt_brain)
    except BoundaryError as exc:
        raise BoundaryError(
            "provenance_mismatch",
            "loaded expression fallback implementation differs from committed authority",
        ) from exc
    pose_by_id = {
        item.get("pose_body_language_id"): item
        for item in pose_bank.get("combos", [])
        if isinstance(item, dict)
    }
    expression_by_id = {
        item.get("expression_gaze_id"): item
        for item in expression_bank.get("combos", [])
        if isinstance(item, dict)
    }
    wardrobe_by_id: dict[str, dict[str, Any]] = {}
    for item in wardrobe_catalog.get("outfits", []):
        if not isinstance(item, dict) or not isinstance(item.get("outfit_id"), str):
            continue
        if item["outfit_id"] in wardrobe_by_id:
            raise BoundaryError("provenance_mismatch", f"duplicate committed wardrobe outfit ID: {item['outfit_id']}")
        wardrobe_by_id[item["outfit_id"]] = item
    pose = pose_by_id.get(manifest["pose_body_language_id"])
    expression = expression_by_id.get(manifest["expression_gaze_id"])
    canonical_pose_text = str(pose.get("text") or "") if pose else ""
    legacy_pose_text = canonical_pose_text + "." if canonical_pose_text and not canonical_pose_text.endswith(".") else None
    pose_text_matches = manifest.get("pose_text") == canonical_pose_text or (
        legacy_pose_text is not None and manifest.get("pose_text") == legacy_pose_text
    )
    if not pose or pose.get("label") != manifest["pose_body_language_label"] or not pose_text_matches:
        raise BoundaryError("provenance_mismatch", "manifest pose ID, label, and text do not match committed pose authority")
    if not expression or expression.get("label") != manifest["expression_gaze_label"]:
        raise BoundaryError("provenance_mismatch", "manifest expression ID and label do not match committed expression authority")
    expected_expression = lena_prompt_brain._higgsfield_safe_expression_text(
        str(candidate.get("activity") or ""), expression
    )
    expression_exact = {
        "expression_text": expected_expression["text"],
        "expression_safe_fallback_used": expected_expression["fallback_used"],
        "expression_safe_fallback_reason": expected_expression["fallback_reason"],
        "expression_scene_conflict_terms": expected_expression["conflict_terms"],
    }
    mismatches = [
        f"{key}: expected {value!r}, got {manifest.get(key)!r}"
        for key, value in expression_exact.items()
        if manifest.get(key) != value
    ]
    if mismatches:
        raise BoundaryError("provenance_mismatch", "manifest expression fallback provenance mismatch: " + "; ".join(mismatches))
    wardrobe = wardrobe_by_id.get(manifest["wardrobe_outfit_id"])
    if not wardrobe or wardrobe.get("name") != manifest["wardrobe_outfit_name"]:
        raise BoundaryError("provenance_mismatch", "manifest wardrobe ID and name do not match committed wardrobe authority")
    wardrobe_prompt = wardrobe.get("prompt")
    if not isinstance(wardrobe_prompt, str) or not wardrobe_prompt.strip() or wardrobe_prompt.casefold() not in manifest["image_prompt"].casefold():
        raise BoundaryError("provenance_mismatch", "generated prompt does not contain the committed wardrobe prompt for the selected outfit")


def _validate_identity_evidence(
    path: Path,
    decision: dict[str, Any],
    candidate: dict[str, Any],
    manifest: dict[str, Any],
    image: dict[str, Any],
) -> dict[str, Any]:
    expected_path = identity.identity_verification_evidence_path(
        decision["as_of_date"], candidate["slot_id"]
    ).resolve()
    if path.resolve() != expected_path:
        raise BoundaryError(
            "identity_evidence_invalid",
            f"identity evidence must be the slot-bound canonical path {expected_path}, got {path.resolve()}",
        )
    evidence = _read_json_object(path, "identity_evidence_invalid", "identity-verification evidence")
    if evidence.get("local_image_sha256") != image["sha256"]:
        raise BoundaryError(
            "image_hash_mismatch",
            "identity evidence local_image_sha256 does not match the current generated image bytes",
        )
    meta = {
        "provider_job_id": manifest.get("provider_job_id"),
        "custom_reference_id": manifest.get("custom_reference_id"),
        "image_prompt": manifest.get("image_prompt"),
    }
    reasons = identity.validate_local_identity_evidence(
        decision["as_of_date"], candidate["slot_id"], Path(image["path"]), meta
    )
    if reasons:
        raise BoundaryError("identity_evidence_invalid", "; ".join(reasons))
    exact = {
        "date": decision["as_of_date"],
        "slot_id": candidate["slot_id"],
        "provider_job_id": manifest["provider_job_id"],
        "job_type": manifest["job_type"],
        "custom_reference_id": manifest["custom_reference_id"],
        "prompt_sha256": candidate["prompt_sha256"],
        "local_image_sha256": image["sha256"],
    }
    mismatches = [f"{key}: expected {value!r}, got {evidence.get(key)!r}" for key, value in exact.items() if evidence.get(key) != value]
    if Path(str(evidence.get("local_image_path") or "")).resolve() != Path(image["path"]):
        mismatches.append("local_image_path does not match generated image")
    if mismatches:
        raise BoundaryError("identity_evidence_invalid", "identity evidence binding mismatch: " + "; ".join(mismatches))
    return evidence


def _failure_memory_evidence(
    manifest: dict[str, Any], loader: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    memory = loader()
    lane = manifest.get("lane")
    pose = manifest.get("pose_body_language_id")
    if not isinstance(lane, str) or not lane or not isinstance(pose, str) or not pose:
        raise BoundaryError("provenance_mismatch", "lane and pose_body_language_id are required before failure-memory lookup")
    key = (lane, pose)
    hard = {tuple(item) for item in memory.get("hard_excluded_patterns", []) if isinstance(item, (list, tuple)) and len(item) == 2}
    soft = {tuple(item) for item in memory.get("soft_flagged_patterns", []) if isinstance(item, (list, tuple)) and len(item) == 2}
    return {
        "pattern_key": list(key),
        "soft_flagged": key in soft,
        "hard_excluded": key in hard,
        "pattern_counts": (memory.get("pattern_counts") or {}).get(f"{key[0]}::{key[1]}", {"pass": 0, "fail": 0}),
        "semantics": "read-only aggregate; no reason-specific retry count inferred",
    }


def validate_visual_observations(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != VISUAL_SCHEMA_VERSION:
        raise BoundaryError("visual_review_unavailable", "visual review has a missing or invalid schema_version")
    if "disposition" in value:
        raise BoundaryError("visual_review_unavailable", "visual reviewer must report observations, not a disposition")
    observations = value.get("observations")
    if not isinstance(observations, dict) or set(observations) != set(VISUAL_OBSERVATION_KEYS):
        raise BoundaryError("visual_review_unavailable", "visual review must contain exactly every required observation key")
    normalized: dict[str, Any] = {}
    for key in VISUAL_OBSERVATION_KEYS:
        entry = observations[key]
        if not isinstance(entry, dict) or set(entry) != {"status", "reason_codes", "notes"}:
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} has a malformed shape")
        status = entry.get("status")
        reasons = entry.get("reason_codes")
        notes = entry.get("notes")
        if status not in ALLOWED_OBSERVATION_STATUSES or not isinstance(reasons, list) or not isinstance(notes, str) or not notes.strip():
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} has invalid values")
        if any(not isinstance(code, str) or code not in HARD_STOP_CODES | RETRYABLE_CODES for code in reasons):
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} has an unknown reason code")
        if any(code not in ALLOWED_REASON_CODES_BY_OBSERVATION[key] for code in reasons):
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} has an incompatible reason code")
        if len(reasons) != len(set(reasons)):
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} has duplicate reason codes")
        if (status == "fail") != bool(reasons):
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} status/reason_codes are ambiguous")
        if status == "unreviewed" and reasons:
            raise BoundaryError("visual_review_unavailable", f"observation {key!r} cannot attach reasons to unreviewed")
        normalized[key] = {"status": status, "reason_codes": sorted(reasons), "notes": notes.strip()}
    return normalized


def _all_unreviewed_observations(note: str) -> dict[str, Any]:
    return {
        "schema_version": VISUAL_SCHEMA_VERSION,
        "observations": {
            key: {"status": "unreviewed", "reason_codes": [], "notes": note}
            for key in VISUAL_OBSERVATION_KEYS
        },
    }


def deterministic_disposition(
    observations: dict[str, Any], memory_evidence: dict[str, Any]
) -> tuple[str, list[str], bool, Optional[str], str, str]:
    reason_codes = {
        code
        for entry in observations.values()
        for code in entry.get("reason_codes", [])
    }
    if memory_evidence.get("hard_excluded"):
        reason_codes.add("failure_memory_pattern_hard_excluded")
    if not memory_evidence.get("hard_excluded") and any(
        entry.get("status") == "unreviewed" for entry in observations.values()
    ):
        reason_codes.add("visual_review_unavailable")
    hard = sorted(reason_codes & HARD_STOP_CODES)
    retryable = sorted(reason_codes & RETRYABLE_CODES)
    if hard:
        return "hard_stop", sorted(reason_codes), False, hard[0], "blocked", "human_review_or_new_candidate_required"
    if retryable:
        return "retryable_failure", retryable, True, None, "high", "separate_retry_or_repair_decision_required"
    if any(entry["status"] != "pass" for entry in observations.values()):
        return "hard_stop", ["visual_review_unavailable"], False, "visual_review_unavailable", "blocked", "human_visual_review_required"
    return "accept", [], False, None, "high", "existing_downstream_qa_and_human_review_gates_only"


def _load_canonical_rubric(authority_commit: str) -> dict[str, Any]:
    paths = {
        "persona": ROOT / "pipeline/influencer_nodes/lena/persona.json",
        "strategy": ROOT / "pipeline/influencer_nodes/lena/lena_content_strategy_v1.json",
        "photo_qa_definitions": ROOT / "pipeline/qa/lena_photo_qa.py",
        "visual_qa_rules": ROOT / "pipeline/agents/lena/70_visual_qa/RULES.md",
    }
    try:
        raw = {name: _git_show_bytes(authority_commit, path) for name, path in paths.items()}
        persona = json.loads(raw["persona"].decode("utf-8-sig"))
        strategy = json.loads(raw["strategy"].decode("utf-8-sig"))
        rules = raw["visual_qa_rules"].decode("utf-8-sig")
    except (UnicodeError, json.JSONDecodeError, BoundaryError) as exc:
        raise BoundaryError("corrupt_or_untrusted_evidence", f"canonical semantic rubric could not be loaded: {exc}") from exc
    if not isinstance(persona, dict) or not isinstance(strategy, dict) or not rules.strip():
        raise BoundaryError("corrupt_or_untrusted_evidence", "canonical semantic rubric sources are incomplete")
    if paths["photo_qa_definitions"].read_bytes() != raw["photo_qa_definitions"]:
        raise BoundaryError("corrupt_or_untrusted_evidence", "loaded photo-QA definitions differ from committed authority")
    return {
        "authority_commit": authority_commit,
        "source_sha256": {name: _sha256_bytes(value) for name, value in raw.items()},
        "persona": persona,
        "content_strategy": strategy,
        "photo_qa_definitions": {
            "checklist_fields": [list(item) for item in lena_photo_qa.QA_CHECKLIST_FIELDS],
            "production_scoring_fields": [list(item) for item in lena_photo_qa.PRODUCTION_SCORING_FIELDS],
            "hard_gating_checklist_keys": list(lena_photo_qa.HARD_GATING_CHECKLIST_KEYS),
        },
        "visual_qa_rules": rules,
        "required_semantic_dimensions": {
            "identity": ["face", "hair", "apparent age", "skin", "body silhouette", "Lena reference consistency"],
            "background_identity_duplication": ["recognizable background person must not read as Lena or a second Lena-like identity"],
            "scene_coherence": ["action", "gaze", "posture", "prop interaction", "required visual evidence", "environment", "wardrobe"],
            "physical_realism": ["anatomy", "hands and fingers", "limbs", "reflections", "object contact", "impossible geometry", "body distortion"],
            "aesthetic_quality": ["composition", "lighting", "premium visual discipline", "natural asymmetry", "overprocessing", "clutter"],
            "character_fit": ["confident", "playful", "self-aware", "teasing", "adventurous", "slightly impulsive", "emotionally self-possessed"],
            "reject_character_traits": ["needy", "desperate for validation", "melodramatic", "fake-rich signaling", "generic thirst-trap framing", "audience-controlled identity"],
            "sexuality_and_safety": ["platform-safe", "not pornographic", "no unsafe exposure", "no sexual-signal stacking", "contextual swimwear", "high heat cannot substitute for narrative relevance"],
            "production_usability": ["visible artifacts", "downstream compatibility", "unacceptable defects"],
        },
    }


def _review_request(
    decision: dict[str, Any],
    candidate: dict[str, Any],
    manifest: dict[str, Any],
    image: dict[str, Any],
    references: list[dict[str, Any]],
    authority_id: str,
    reference_set_sha: str,
    provider: str,
    model: str,
    rubric: dict[str, Any],
    model_authority: dict[str, Any],
) -> dict[str, Any]:
    active_fingerprint = (
        decision["decision_fingerprint_sha256"]
        if "decision_fingerprint_sha256" in decision
        else decision["retry_decision_fingerprint_sha256"]
    )
    return {
        "schema_version": "lena_visual_review_request_v1",
        "influencer_id": "lena",
        "decision_fingerprint_sha256": active_fingerprint,
        "candidate_id": candidate["candidate_id"],
        "slot_id": candidate["slot_id"],
        "lane": candidate["lane"],
        "prompt_sha256": candidate["prompt_sha256"],
        "image": image,
        "identity_reference_authority_id": authority_id,
        "identity_reference_set_sha256": reference_set_sha,
        "identity_references": references,
        "prompt_context": manifest["image_prompt"],
        "scene_context": {
            "lane": manifest.get("lane"),
            "pose_text": manifest.get("pose_text"),
            "pose_body_language_id": manifest.get("pose_body_language_id"),
            "expression_gaze_id": manifest.get("expression_gaze_id"),
            "expression_gaze_label": manifest.get("expression_gaze_label"),
            "expression_text": manifest.get("expression_text"),
            "wardrobe_outfit_id": manifest.get("wardrobe_outfit_id"),
            "wardrobe_outfit_name": manifest.get("wardrobe_outfit_name"),
            "wardrobe_silhouette_class": manifest.get("wardrobe_silhouette_class"),
            "effective_wardrobe_silhouette_class": manifest.get("effective_wardrobe_silhouette_class"),
            "background_identity_constraint": (
                "Recognizable Lena identity must not appear on any secondary or background person. "
                "Any background person must be non-recognizable, clearly distinct from Lena, or both, and must never read as a second Lena-like identity."
            ),
        },
        "canonical_semantic_rubric": rubric,
        "canonical_semantic_rubric_sha256": _sha256_bytes(_canonical_bytes(rubric)),
        "visual_model_authority": model_authority,
        "required_observation_keys": list(VISUAL_OBSERVATION_KEYS),
        "allowed_reason_codes": sorted(HARD_STOP_CODES | RETRYABLE_CODES),
        "visual_provider": provider,
        "visual_model": model,
        "instruction": (
            "Report structured observations only. Do not choose a disposition. "
            "You must explicitly judge whether any secondary or background person carries a recognizable Lena-like identity; "
            "if yes, fail no_background_identity_duplication with wrong_person_or_identity_collapse."
        ),
    }


def _visual_request_payload(request: dict[str, Any]) -> dict[str, Any]:
    image = request["image"]
    identity_references = request["identity_references"]
    payload = {key: value for key, value in request.items() if key not in {"image", "identity_references"}}
    payload["image"] = {
        "sha256": image["sha256"],
        "format": image["format"],
    }
    if "width" in image:
        payload["image"]["width"] = image["width"]
    if "height" in image:
        payload["image"]["height"] = image["height"]
    payload["identity_references"] = [
        {
            key: value
            for key, value in {
                "sha256": ref["sha256"],
                "format": ref["format"],
                "width": ref.get("width"),
                "height": ref.get("height"),
            }.items()
            if value is not None
        }
        for ref in identity_references
    ]
    return payload


def _visual_request_images(request: dict[str, Any]) -> list[StructuredVisualImage]:
    images = [
        StructuredVisualImage(
            path=Path(request["image"]["path"]),
            sha256=str(request["image"]["sha256"]),
            role="generated_candidate",
        )
    ]
    for index, reference in enumerate(request["identity_references"], start=1):
        images.append(
            StructuredVisualImage(
                path=Path(reference["path"]),
                sha256=str(reference["sha256"]),
                role=f"identity_reference_{index}",
            )
        )
    return images


def _redacted_tool_input_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"input_type": type(value).__name__}
    diagnostics: dict[str, Any] = {"keys": sorted(value.keys())}
    observations = value.get("observations")
    if isinstance(observations, dict):
        diagnostics["observation_keys"] = sorted(observations.keys())
        diagnostics["observation_entry_types"] = {
            key: type(item).__name__
            for key, item in observations.items()
        }
    else:
        diagnostics["observations_type"] = type(observations).__name__
    if "schema_version" in value:
        diagnostics["schema_version_type"] = type(value.get("schema_version")).__name__
        diagnostics["schema_version_matches_expected"] = value.get("schema_version") == VISUAL_SCHEMA_VERSION
    return diagnostics


def call_anthropic_visual_review(request: dict[str, Any]) -> dict[str, Any]:
    """One bounded call. Lazy import; no retries, fallback, or second candidate."""
    properties = {
        key: {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": sorted(ALLOWED_OBSERVATION_STATUSES)},
                "reason_codes": {"type": "array", "items": {"type": "string", "enum": sorted(HARD_STOP_CODES | RETRYABLE_CODES)}},
                "notes": {"type": "string"},
            },
            "required": ["status", "reason_codes", "notes"],
            "additionalProperties": False,
        }
        for key in VISUAL_OBSERVATION_KEYS
    }
    try:
        visual_request = _visual_request_payload(request)
        payload = call_anthropic_structured_visual_tool(
            images=_visual_request_images(request),
            system_prompt="Return structured observations only; local code assigns disposition.",
            user_text=json.dumps(visual_request, sort_keys=True, ensure_ascii=False),
            tool_name="submit_visual_observations",
            tool_schema={
                "type": "object",
                "properties": {
                    "schema_version": {"type": "string", "enum": [VISUAL_SCHEMA_VERSION]},
                    "observations": {
                        "type": "object",
                        "properties": properties,
                        "required": list(VISUAL_OBSERVATION_KEYS),
                        "additionalProperties": False,
                    },
                },
                "required": ["observations"],
                "additionalProperties": False,
            },
            provider=APPROVED_VISUAL_PROVIDER,
            model=str(request["visual_model"]),
            timeout_seconds=30.0,
            max_tokens=4096,
        )
    except StructuredVisualToolError as exc:
        raise BoundaryError(exc.code, exc.detail) from exc
    if not isinstance(payload, dict):
        diagnostics = _redacted_tool_input_diagnostics(payload)
        raise BoundaryError(
            "visual_review_unavailable",
            "visual provider returned a malformed structured observation payload: "
            + json.dumps(diagnostics, sort_keys=True),
        )
    echoed_schema = payload.get("schema_version")
    if echoed_schema is not None and echoed_schema != VISUAL_SCHEMA_VERSION:
        diagnostics = _redacted_tool_input_diagnostics(payload)
        raise BoundaryError(
            "visual_review_unavailable",
            "visual provider returned a conflicting schema_version: "
            + json.dumps(diagnostics, sort_keys=True),
        )
    return {"schema_version": VISUAL_SCHEMA_VERSION, **payload}


def _read_bound_image_bytes(item: dict[str, Any]) -> bytes:
    image_bytes = Path(item["path"]).read_bytes()
    actual_sha = _sha256_bytes(image_bytes)
    if actual_sha != item.get("sha256"):
        raise BoundaryError(
            "image_hash_mismatch",
            f"image bytes changed after validation and before visual upload: {item.get('path')}",
        )
    return image_bytes


def _blocked_artifact(code: str, detail: str, *, provider_called: bool = False) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "influencer_id": "lena",
        "generated_at_utc": _utc_now(),
        "authority_commit": None,
        "decision_artifact_path": None,
        "decision_fingerprint_sha256": None,
        "candidate_id": None,
        "slot_id": None,
        "lane": None,
        "recipe_id": None,
        "hook_id": None,
        "prompt_sha256": None,
        "image_path": None,
        "image_sha256": None,
        "generation_provenance": {},
        "identity_reference_provenance": {},
        "qa_inputs": {"binding_error": detail},
        "qa_checks": {},
        "reason_codes": [code],
        "disposition": "hard_stop",
        "retry_eligible": False,
        "hard_stop_reason": code,
        "confidence": "blocked",
        "reviewer_type": "local_binding_validator",
        "visual_judgment_source": None,
        "provider_called": provider_called,
        "side_effects_performed": [],
        "exact_next_allowed_action": "correct_input_evidence_or_request_human_review",
    }


def evaluate_photo_qa_disposition(
    *,
    decision_path: Path,
    manifest_path: Path,
    image_path: Path,
    identity_evidence_path: Path,
    reference_specs: Iterable[tuple[Path, str]],
    reference_authority_artifact: Path,
    reference_authority_sha256: str,
    expected_image_sha256: str,
    live_visual_review: bool = False,
    visual_provider: Optional[str] = None,
    visual_model: Optional[str] = None,
    visual_model_authority_artifact: Optional[Path] = None,
    visual_model_authority_sha256: Optional[str] = None,
    expected_decision_fingerprint: Optional[str] = None,
    expected_reference_set_sha256: Optional[str] = None,
    failure_memory_loader: Callable[[], dict[str, Any]] = failure_memory.compute_higgsfield_failure_memory,
) -> dict[str, Any]:
    provider_called = False
    try:
        autonomy_ladder.assert_allowed(
            "lena_photo_qa_disposition_v1",
            level=2,
            action="QA disposition",
        )
        if not isinstance(reference_authority_artifact, Path) or not SHA256_RE.fullmatch(str(reference_authority_sha256)):
            raise BoundaryError("identity_evidence_invalid", "committed identity-reference authority path and SHA-256 are required")
        decision, candidate, decision_kind, binding_context = _resolve_generation_binding_context(decision_path.resolve())
        provider_binding = None
        if binding_context is not None:
            provider_binding = binding_context.get("provider_execution_binding")
        image = _inspect_image(image_path.resolve(), generated=True)
        if not SHA256_RE.fullmatch(str(expected_image_sha256)) or image["sha256"] != expected_image_sha256:
            raise BoundaryError(
                "image_hash_mismatch",
                f"generated image SHA does not match explicit expected SHA: expected {expected_image_sha256}, got {image['sha256']}",
            )
        manifest = _validate_manifest(
            manifest_path.resolve(),
            decision,
            candidate,
            image,
            decision_kind,
            provider_binding=provider_binding,
        )
        identity_evidence = _validate_identity_evidence(
            identity_evidence_path.resolve(), decision, candidate, manifest, image
        )
        active_fingerprint = decision.get("decision_fingerprint_sha256") or decision.get("retry_decision_fingerprint_sha256")
        if not active_fingerprint:
            raise BoundaryError("identity_evidence_invalid", "decision fingerprint is missing from the bound authorization context")
        references, reference_set_sha, reference_authority = _validate_references(
            reference_specs, reference_authority_artifact.resolve(), reference_authority_sha256, decision["authority_commit"]
        )
        memory_evidence = _failure_memory_evidence(manifest, failure_memory_loader)

        visual_observations: Optional[dict[str, Any]] = None

        if memory_evidence["hard_excluded"]:
            visual_observations = _all_unreviewed_observations(
                "visual review skipped because the current lane/pose pattern is already hard-excluded"
            )
        elif live_visual_review:
            if visual_model_authority_artifact is None or visual_model_authority_sha256 is None:
                raise BoundaryError("visual_review_unavailable", "live visual review requires committed approved-model authority")
            model_authority = _validate_model_authority(
                visual_model_authority_artifact.resolve(), visual_model_authority_sha256,
                decision["authority_commit"], str(visual_provider or ""), str(visual_model or ""),
            )
            bindings = {
                "decision fingerprint": (expected_decision_fingerprint, active_fingerprint),
                "image SHA": (expected_image_sha256, image["sha256"]),
                "reference-set SHA": (expected_reference_set_sha256, reference_set_sha),
            }
            mismatches = [name for name, (expected, actual) in bindings.items() if expected != actual]
            if mismatches:
                raise BoundaryError("decision_binding_mismatch", "live visual-review binding mismatch: " + ", ".join(mismatches))
            rubric = _load_canonical_rubric(decision["authority_commit"])
            request = _review_request(
                decision, candidate, manifest, image, references, reference_authority["authority_id"],
                reference_set_sha, str(visual_provider), str(visual_model), rubric, model_authority,
            )
            provider_called = True
            try:
                visual_observations = call_anthropic_visual_review(request)
            except BoundaryError:
                raise
            except Exception as exc:
                raise BoundaryError("visual_review_unavailable", f"visual provider call failed: {exc}") from exc

        if visual_observations is None:
            visual_observations = _all_unreviewed_observations(
                "no semantic visual review occurred; default local validation cannot judge pixels"
            )
        observations = validate_visual_observations(visual_observations)
        observations.update(
            {
                "dimensions": {"status": "pass", "reason_codes": [], "notes": f"locally measured {image['width']}x{image['height']}"},
                "file_integrity": {"status": "pass", "reason_codes": [], "notes": "Pillow verify and reopen succeeded"},
                "format": {"status": "pass", "reason_codes": [], "notes": f"locally detected supported format {image['format']}"},
                "downstream_compatibility": {"status": "pass", "reason_codes": [], "notes": "approved Higgsfield dimensions and supported still-image format"},
            }
        )
        disposition, reasons, retry_eligible, hard_reason, confidence, next_action = deterministic_disposition(
            observations, memory_evidence
        )
        reviewer_type = "bounded_visual_provider" if provider_called else "local_validation_only"
        visual_source = {
            "reviewer_type": reviewer_type,
            "provider": visual_provider if provider_called else None,
            "model": visual_model if provider_called else None,
            "observation_schema_version": VISUAL_SCHEMA_VERSION,
            "observations_sha256": _sha256_bytes(_canonical_bytes(visual_observations)),
            "request_binding_sha256": _sha256_bytes(
                _canonical_bytes(
                    {
                        "decision_fingerprint_sha256": active_fingerprint,
                        "image_sha256": image["sha256"],
                        "reference_set_sha256": reference_set_sha,
                    }
                )
            ),
        }
        # The existing schema remains authoritative and unchanged; this record
        # records which canonical keys are downstream-gating without writing it.
        qa_template = lena_photo_qa.build_qa_template(
            {"slot_id": candidate["slot_id"], "media_type": "photo", "metadata": {}},
            decision["as_of_date"],
        )
        qa_template_valid, qa_template_errors = lena_photo_qa.validate_qa_result(qa_template)
        if not qa_template_valid:
            raise BoundaryError(
                "corrupt_or_untrusted_evidence",
                "existing canonical QA template failed its own validator: " + "; ".join(qa_template_errors),
            )
        canonical_qa_contract = {
            "schema_version": lena_photo_qa.SCHEMA_VERSION,
            "checklist_keys": list(lena_photo_qa.QA_CHECKLIST_KEYS),
            "hard_gating_checklist_keys": list(lena_photo_qa.HARD_GATING_CHECKLIST_KEYS),
            "validator": "pipeline.qa.lena_photo_qa.validate_qa_result",
            "fresh_unreviewed_template_valid": True,
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "influencer_id": "lena",
            "generated_at_utc": _utc_now(),
            "authority_commit": decision["authority_commit"],
            "decision_artifact_path": str(decision_path.resolve()),
            "decision_fingerprint_sha256": active_fingerprint,
            "binding_mode": "authorization_bound_handoff" if binding_context is not None else "selected_candidate",
            "candidate_id": candidate["candidate_id"],
            "slot_id": candidate["slot_id"],
            "lane": candidate["lane"],
            "recipe_id": candidate["recipe_id"],
            "hook_id": candidate["hook_id"],
            "prompt_sha256": candidate["prompt_sha256"],
            "image_path": image["path"],
            "image_sha256": image["sha256"],
            "provider_execution_binding": provider_binding,
            "generation_provenance": {
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": _sha256_file(manifest_path),
                "date": decision["as_of_date"],
                "binding_mode": "authorization_bound_handoff" if binding_context is not None else "selected_candidate",
                "field_sources": {
                    "candidate_and_authority": str(decision_path.resolve()),
                    "provider_generation": str(manifest_path.resolve()),
                    "local_image_hash_and_identity": str(identity_evidence_path.resolve()),
                },
                "provider": manifest["provider"],
                "job_type": manifest["job_type"],
                "provider_job_id": manifest["provider_job_id"],
                "provider_status": manifest["provider_status"],
                "custom_reference_id": manifest["custom_reference_id"],
                "soul_name": manifest["cli_soul_name"],
                "soul_type": manifest["cli_soul_type"],
                "provider_execution_binding": provider_binding,
            },
            "identity_reference_provenance": {
                **reference_authority,
                "reference_set_sha256": reference_set_sha,
                "references": references,
                "authority_semantics": "exact committed authority artifact and reference-set binding",
            },
            "qa_inputs": {
                "identity_evidence_path": str(identity_evidence_path.resolve()),
                "identity_evidence_sha256": _sha256_file(identity_evidence_path),
                "identity_verification_result": identity_evidence.get("verification_result"),
                "decision_kind": decision_kind,
                "failure_memory": memory_evidence,
                "canonical_qa_contract": canonical_qa_contract,
            },
            "qa_checks": observations,
            "reason_codes": reasons,
            "disposition": disposition,
            "retry_eligible": retry_eligible,
            "hard_stop_reason": hard_reason,
            "confidence": confidence,
            "reviewer_type": reviewer_type,
            "visual_judgment_source": visual_source,
            "provider_called": provider_called,
            "side_effects_performed": [],
            "exact_next_allowed_action": next_action,
        }
    except autonomy_ladder.AutonomyLadderError as exc:
        return _blocked_artifact(exc.code, exc.detail, provider_called=provider_called)
    except BoundaryError as exc:
        return _blocked_artifact(exc.code, exc.detail, provider_called=provider_called)


def disposition_artifact_path(artifact: dict[str, Any], output_root: Path = OUTPUT_ROOT) -> Path:
    slot_id = artifact.get("slot_id")
    image_sha = artifact.get("image_sha256")
    date_str = str(artifact.get("generation_provenance", {}).get("date") or "")
    if not slot_id or not SHA256_RE.fullmatch(str(image_sha)) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise BoundaryError("corrupt_or_untrusted_evidence", "cannot derive disposition path from an unbound artifact")
    return output_root / date_str / f"{slot_id}__{image_sha}_qa_disposition.json"


def write_disposition_artifact(
    artifact: dict[str, Any], output_root: Path = OUTPUT_ROOT
) -> tuple[Path, dict[str, Any], bool]:
    path = disposition_artifact_path(artifact, output_root)
    if path.exists():
        existing = _read_json_object(path, "corrupt_or_untrusted_evidence", "existing QA disposition")
        stable = lambda value: {key: item for key, item in value.items() if key != "generated_at_utc"}
        if _canonical_bytes(stable(existing)) == _canonical_bytes(stable(artifact)):
            return path, existing, False
        raise CollisionError(
            "corrupt_or_untrusted_evidence",
            f"conflicting QA disposition already exists; refusing overwrite: {path}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, artifact, True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bind and disposition one generated Lena still without downstream action.")
    parser.add_argument("--decision-artifact", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--expected-image-sha256", required=True)
    parser.add_argument("--identity-evidence", type=Path, required=True)
    parser.add_argument("--identity-reference-authority-artifact", type=Path, required=True)
    parser.add_argument("--identity-reference-authority-sha256", required=True)
    parser.add_argument("--identity-reference", action="append", default=[], metavar="PATH::SHA256")
    parser.add_argument("--write-artifact", action="store_true")
    parser.add_argument("--live-visual-review", action="store_true")
    parser.add_argument("--visual-provider")
    parser.add_argument("--visual-model")
    parser.add_argument("--visual-model-authority-artifact", type=Path)
    parser.add_argument("--visual-model-authority-sha256")
    parser.add_argument("--expected-decision-fingerprint")
    parser.add_argument("--expected-reference-set-sha256")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        specs = [parse_reference_spec(value) for value in args.identity_reference]
        expected_image_sha256 = str(args.expected_image_sha256).lower()
        artifact = evaluate_photo_qa_disposition(
            decision_path=args.decision_artifact,
            manifest_path=args.manifest,
            image_path=args.image,
            expected_image_sha256=expected_image_sha256,
            identity_evidence_path=args.identity_evidence,
            reference_specs=specs,
            reference_authority_artifact=args.identity_reference_authority_artifact,
            reference_authority_sha256=args.identity_reference_authority_sha256,
            live_visual_review=args.live_visual_review,
            visual_provider=args.visual_provider,
            visual_model=args.visual_model,
            visual_model_authority_artifact=args.visual_model_authority_artifact,
            visual_model_authority_sha256=args.visual_model_authority_sha256,
            expected_decision_fingerprint=args.expected_decision_fingerprint,
            expected_reference_set_sha256=args.expected_reference_set_sha256,
        )
        report: dict[str, Any] = {"artifact": artifact, "artifact_write": {"requested": args.write_artifact, "written": False, "path": None}}
        if args.write_artifact:
            try:
                path, artifact, created = write_disposition_artifact(artifact)
            except BoundaryError:
                if artifact.get("qa_inputs", {}).get("binding_error"):
                    path = None
                    created = False
                else:
                    raise
            else:
                report["artifact"] = artifact
            report["artifact_write"] = {"requested": True, "written": created, "path": str(path) if path else None}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if artifact["disposition"] != "hard_stop" else 1
    except BoundaryError as exc:
        print(json.dumps({"artifact": _blocked_artifact(exc.code, exc.detail), "artifact_write": {"requested": args.write_artifact, "written": False, "path": None}}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
