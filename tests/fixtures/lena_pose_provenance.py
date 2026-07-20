from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.strategy import lena_pose_provenance_v1 as pose_provenance


POSE_ID = "pose_p001"
POSE_LABEL = "weight_shift_one_hip"
POSE_TEXT = "weight shifted onto one hip, stance easy and unforced"


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


def candidate_pose_provenance(candidate_path: Path, *, root: Path) -> dict[str, Any]:
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    return static_pose_provenance(
        candidate_path=candidate_path.resolve().relative_to(root.resolve()).as_posix(),
        candidate_sha256=_sha256(candidate_path.read_bytes()),
        authority_commit=payload["authority_commit"],
    )


def canonical_prompt() -> str:
    return (
        "[Subject]: Lena in a controlled fashion portrait with a calm expression. "
        "[Action]: " + POSE_TEXT + " "
        "[Environment]: realistic interior. "
        "[Cinematography]: chest-up editorial framing. "
        "[Lighting/Style]: natural low-light skin texture. "
        "[Technical]: 35mm lens, natural grain."
    )


def bind_packet(packet: dict[str, Any], *, pose_binding: dict[str, Any]) -> dict[str, Any]:
    bound = copy.deepcopy(packet)
    prompt = str(bound.get("compact_provider_prompt_preview") or canonical_prompt())
    bound["compact_provider_prompt_preview"] = prompt
    bound["compact_provider_prompt_chars"] = len(prompt)
    bound["compact_provider_prompt_sha256"] = _sha256(prompt.encode("utf-8"))
    bound["pose_provenance"] = copy.deepcopy(pose_binding)
    bound["generation_pose_contract"] = {
        "status": "bound",
        "authority_source": pose_provenance.AUTHORITY_SOURCE,
        "recipe_subject_pose_semantics": pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS,
    }
    bound.setdefault("high_caliber_source_sections", {})["subject_pose_semantics"] = (
        pose_provenance.RECIPE_SUBJECT_POSE_SEMANTICS
    )
    bound["high_caliber_source_sections"]["provider_action_pose"] = pose_binding["pose_text"]
    return bound
