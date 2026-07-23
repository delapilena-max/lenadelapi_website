from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.strategy import lena_pose_provenance_v1 as pose_provenance
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder


_AUTHORITATIVE_PACKET_REBUILD = packet_builder.rebuild_packet_from_authoritative_sources


POSE_ID = "pose_p001"
POSE_LABEL = "weight_shift_one_hip"
POSE_TEXT = "weight shifted onto one hip, stance easy and unforced"
EXPRESSION_ID = "exp_g001"
EXPRESSION_LABEL = "closed_mouth_smile_direct"
EXPRESSION_TEXT = "closed-mouth smile, soft direct eye contact, slight head tilt"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def static_pose_provenance(
    *,
    candidate_path: str = "pipeline/strategy/lena/pre_generation_candidates/fixture.json",
    candidate_sha256: str = "1" * 64,
    authority_commit: str = "a" * 40,
) -> dict[str, Any]:
    core = {
        "schema_version": pose_provenance.SCHEMA_VERSION,
        "authority_source": pose_provenance.AUTHORITY_SOURCE,
        "selected_candidate_artifact_path": candidate_path,
        "selected_candidate_artifact_sha256": candidate_sha256,
        "selected_candidate_authority_commit": authority_commit,
        "pose_authority_artifact_path": pose_provenance.POSE_AUTHORITY_REPO_PATH,
        "pose_authority_artifact_sha256": "2" * 64,
        "pose_body_language_id": POSE_ID,
        "pose_body_language_label": POSE_LABEL,
        "pose_text": POSE_TEXT,
        "pose_text_sha256": _sha256(POSE_TEXT.encode("utf-8")),
        "recipe_subject_pose_semantics": pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS,
    }
    fingerprint = _sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    return {**core, "pose_provenance_fingerprint_sha256": fingerprint}


def candidate_pose_provenance(candidate_path: Path, *, root: Path, **kwargs) -> dict[str, Any]:
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    return static_pose_provenance(
        candidate_path=candidate_path.resolve().relative_to(root.resolve()).as_posix(),
        candidate_sha256=_sha256(candidate_path.read_bytes()),
        authority_commit=payload["authority_commit"],
    )


def candidate_expression_provenance(
    candidate_path: Path,
    *,
    root: Path,
    **kwargs,
) -> dict[str, Any]:
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    return static_expression_provenance(
        candidate_path=candidate_path.resolve().relative_to(root.resolve()).as_posix(),
        candidate_sha256=_sha256(candidate_path.read_bytes()),
        authority_commit=payload["authority_commit"],
    )


def static_expression_provenance(
    *,
    candidate_path: str = "pipeline/strategy/lena/pre_generation_candidates/fixture.json",
    candidate_sha256: str = "1" * 64,
    authority_commit: str = "a" * 40,
) -> dict[str, Any]:
    core = {
        "schema_version": pose_provenance.EXPRESSION_SCHEMA_VERSION,
        "authority_source": pose_provenance.EXPRESSION_AUTHORITY_SOURCE,
        "selected_candidate_artifact_path": candidate_path,
        "selected_candidate_artifact_sha256": candidate_sha256,
        "selected_candidate_authority_commit": authority_commit,
        "expression_authority_artifact_path": pose_provenance.EXPRESSION_AUTHORITY_REPO_PATH,
        "expression_authority_artifact_sha256": "3" * 64,
        "expression_derivation_artifact_path": pose_provenance.EXPRESSION_DERIVATION_REPO_PATH,
        "expression_derivation_artifact_sha256": "4" * 64,
        "expression_gaze_id": EXPRESSION_ID,
        "expression_gaze_label": EXPRESSION_LABEL,
        "expression_canonical_text": EXPRESSION_TEXT,
        "expression_canonical_text_sha256": _sha256(EXPRESSION_TEXT.encode("utf-8")),
        "expression_text": EXPRESSION_TEXT,
        "expression_text_sha256": _sha256(EXPRESSION_TEXT.encode("utf-8")),
        "expression_safe_fallback_used": False,
        "expression_safe_fallback_reason": None,
        "expression_scene_conflict_terms": [],
        "expression_derivation_scene_action": "standing in a controlled studio portrait",
    }
    fingerprint = _sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    return {**core, "expression_provenance_fingerprint_sha256": fingerprint}


def canonical_prompt() -> str:
    return pose_provenance.serialize_provider_prompt_sections([
        ("Subject", "Lena in a controlled fashion portrait with a calm expression."),
        ("Action", POSE_TEXT),
        ("Expression", EXPRESSION_TEXT),
        ("Environment", "realistic interior."),
        ("Cinematography", "chest-up editorial framing."),
        ("Lighting/Style", "natural low-light skin texture."),
        ("Technical", "35mm lens, natural grain."),
    ])


def bind_packet(
    packet: dict[str, Any],
    *,
    pose_binding: dict[str, Any],
    expression_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expression_binding = expression_binding or static_expression_provenance(
        candidate_path=pose_binding["selected_candidate_artifact_path"],
        candidate_sha256=pose_binding["selected_candidate_artifact_sha256"],
        authority_commit=pose_binding["selected_candidate_authority_commit"],
    )
    bound = copy.deepcopy(packet)
    raw_prompt = str(bound.get("compact_provider_prompt_preview") or canonical_prompt())
    sections = pose_provenance.parse_provider_prompt_sections(raw_prompt)
    sections["Action"] = pose_binding["pose_text"]
    sections["Expression"] = expression_binding["expression_text"]
    prompt = pose_provenance.serialize_provider_prompt_sections(
        [(label, sections[label]) for label in pose_provenance.PROVIDER_SECTION_ORDER if label in sections]
    )
    bound["compact_provider_prompt_preview"] = prompt
    bound["compact_provider_prompt_chars"] = len(prompt)
    bound["compact_provider_prompt_sha256"] = _sha256(prompt.encode("utf-8"))
    bound["pose_provenance"] = copy.deepcopy(pose_binding)
    bound["expression_provenance"] = copy.deepcopy(expression_binding)
    bound["generation_pose_contract"] = {
        "status": "bound",
        "authority_source": pose_provenance.AUTHORITY_SOURCE,
        "recipe_subject_pose_semantics": pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS,
    }
    bound.setdefault("high_caliber_source_sections", {})["subject_pose_semantics"] = (
        pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS
    )
    bound["high_caliber_source_sections"]["provider_action_pose"] = pose_binding["pose_text"]
    bound["high_caliber_source_sections"]["provider_expression"] = expression_binding[
        "expression_text"
    ]
    bound["generation_expression_contract"] = {
        "status": "bound",
        "authority_source": pose_provenance.EXPRESSION_AUTHORITY_SOURCE,
    }
    bound.setdefault("provider_prompt_contract", {}).update({
        "prompt_chars": len(prompt),
        "pose_binding_status": "bound",
        "pose_authority_source": pose_provenance.AUTHORITY_SOURCE,
        "expression_binding_status": "bound",
        "expression_authority_source": pose_provenance.EXPRESSION_AUTHORITY_SOURCE,
    })
    return bound


def authoritatively_bind_packet(
    packet: dict[str, Any],
    *,
    pose_binding: dict[str, Any],
    expression_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expression_binding = expression_binding or static_expression_provenance(
        candidate_path=pose_binding["selected_candidate_artifact_path"],
        candidate_sha256=pose_binding["selected_candidate_artifact_sha256"],
        authority_commit=pose_binding["selected_candidate_authority_commit"],
    )
    return _AUTHORITATIVE_PACKET_REBUILD(
        copy.deepcopy(packet),
        pose_binding=pose_binding,
        expression_binding=expression_binding,
    )
