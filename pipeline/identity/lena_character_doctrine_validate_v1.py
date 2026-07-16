from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DOCTRINE_PATH = ROOT / "pipeline" / "identity" / "lena_character_doctrine_v1.json"

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _is_valid_git_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_GIT_SHA_RE.match(value))

REQUIRED_DEFINING_QUALITIES = (
    "warm",
    "playful",
    "confident",
    "flirtatious",
    "naturally_sensual",
    "expressive",
    "approachable",
    "directly_connected_to_one_viewer",
    "physically_alive_rather_than_editorially_static",
    "strongly_consistent_in_face_body_and_personality",
)

REQUIRED_SAFETY_HARD_FAILURES = (
    "identity_collapse",
    "malformed_anatomy",
    "broken_hands",
    "impossible_garments",
    "explicit_exposure",
    "severe_temporal_instability",
    "distracting_contradictions",
    "platform_prohibited_content",
)

REQUIRED_SAFETY_OVERRIDING_RULES = (
    "sensuality_never_overrides_identity",
    "sensuality_never_overrides_anatomy",
    "sensuality_never_overrides_adult_presentation",
    "sensuality_never_overrides_exposure_limits",
    "sensuality_never_overrides_platform_safety",
    "harmless_imperfection_is_not_a_hard_failure",
    "technical_perfection_must_not_be_used_to_suppress_strong_character",
)

REQUIRED_ORIGINALITY_RULES = (
    "no_copying_another_creators_captions",
    "no_copying_another_creators_distinctive_phrasing",
    "no_copying_another_creators_trade_dress",
)

REQUIRED_TOP_LEVEL_SECTIONS = (
    "character_definition",
    "hard_identity_continuity",
    "behavioral_identity",
    "viewer_relationship",
    "movement_vocabulary",
    "wardrobe_and_sensuality",
    "environments",
    "prop_philosophy",
    "imperfection_tolerance",
    "safety_boundaries",
    "originality_boundary",
)


class CharacterDoctrineError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise CharacterDoctrineError(code, detail)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_doctrine(path: Path = DOCTRINE_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise CharacterDoctrineError(
            "doctrine_missing", f"character doctrine artifact is missing: {path}"
        )
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CharacterDoctrineError(
            "doctrine_malformed",
            f"character doctrine artifact is not valid JSON: {path}: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise CharacterDoctrineError(
            "doctrine_malformed", f"character doctrine artifact must be a JSON object: {path}"
        )
    return payload


def _validate_character_definition(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "character_definition must be a JSON object")
    qualities = section.get("defining_qualities")
    _require(
        isinstance(qualities, list) and set(qualities) == set(REQUIRED_DEFINING_QUALITIES),
        "doctrine_invalid",
        "character_definition.defining_qualities must contain exactly the required defining qualities",
    )
    _require(
        isinstance(section.get("framing"), str) and section["framing"].strip(),
        "doctrine_invalid",
        "character_definition.framing must be a non-empty string",
    )
    _require(
        isinstance(section.get("priority_if_qualities_conflict"), list)
        and section["priority_if_qualities_conflict"],
        "doctrine_invalid",
        "character_definition.priority_if_qualities_conflict must be a non-empty list",
    )


def _validate_hard_identity_continuity(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "hard_identity_continuity must be a JSON object")
    _require(
        isinstance(section.get("requirements"), list) and section["requirements"],
        "doctrine_invalid",
        "hard_identity_continuity.requirements must be a non-empty list",
    )
    _require(
        isinstance(section.get("forbidden"), list)
        and "abrupt_identity_substitution" in section["forbidden"]
        and "temporal_identity_collapse_across_a_sequence" in section["forbidden"],
        "doctrine_invalid",
        "hard_identity_continuity.forbidden must forbid abrupt substitution and temporal collapse",
    )
    _require(
        section.get("authority_reference") == "pipeline/identity/lena_visual_reference_authority_v1.json",
        "doctrine_invalid",
        "hard_identity_continuity.authority_reference must point at the identity reference authority artifact",
    )


def _validate_behavioral_identity(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "behavioral_identity must be a JSON object")
    _require(
        isinstance(section.get("traits"), list) and section["traits"],
        "doctrine_invalid",
        "behavioral_identity.traits must be a non-empty list",
    )
    _require(
        isinstance(section.get("anti_traits"), list) and section["anti_traits"],
        "doctrine_invalid",
        "behavioral_identity.anti_traits must be a non-empty list",
    )


def _validate_viewer_relationship(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "viewer_relationship must be a JSON object")
    _require(
        isinstance(section.get("mechanics"), list) and section["mechanics"],
        "doctrine_invalid",
        "viewer_relationship.mechanics must be a non-empty list",
    )
    _require(
        isinstance(section.get("prohibited"), list) and section["prohibited"],
        "doctrine_invalid",
        "viewer_relationship.prohibited must be a non-empty list",
    )


def _validate_movement_vocabulary(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "movement_vocabulary must be a JSON object")
    _require(
        isinstance(section.get("actions"), list) and section["actions"],
        "doctrine_invalid",
        "movement_vocabulary.actions must be a non-empty list",
    )


def _validate_wardrobe_and_sensuality(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "wardrobe_and_sensuality must be a JSON object")
    _require(
        isinstance(section.get("principles"), list) and section["principles"],
        "doctrine_invalid",
        "wardrobe_and_sensuality.principles must be a non-empty list",
    )
    classification = section.get("classification")
    _require(isinstance(classification, dict), "doctrine_invalid", "wardrobe_and_sensuality.classification must be a JSON object")
    required_tiers = (
        "normal_anatomy_through_fabric",
        "suggestive_but_platform_appropriate_styling",
        "explicit_exposure_or_prohibited_sexual_content",
    )
    for tier in required_tiers:
        entry = classification.get(tier)
        _require(
            isinstance(entry, dict) and "treatment" in entry and "is_a_defect" in entry,
            "doctrine_invalid",
            f"wardrobe_and_sensuality.classification.{tier} must define treatment and is_a_defect",
        )
    _require(
        classification["normal_anatomy_through_fabric"]["is_a_defect"] is False,
        "doctrine_invalid",
        "normal anatomy through fabric must not be treated as a defect",
    )
    _require(
        classification["suggestive_but_platform_appropriate_styling"]["is_a_defect"] is False,
        "doctrine_invalid",
        "suggestive but platform-appropriate styling must not be treated as a defect",
    )
    _require(
        classification["explicit_exposure_or_prohibited_sexual_content"]["is_a_defect"] is True,
        "doctrine_invalid",
        "explicit exposure or prohibited sexual content must be treated as a defect",
    )
    _require(
        section.get("overriding_rule") == (
            "Sensuality never overrides identity, anatomy, adult presentation, exposure limits, "
            "or platform safety. A high sensual-appeal reading can never excuse a hard identity, "
            "anatomy, exposure, or platform-safety failure."
        ),
        "doctrine_invalid",
        "wardrobe_and_sensuality.overriding_rule must state that sensuality never overrides identity/anatomy/adult-presentation/exposure/safety",
    )


def _validate_environments(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "environments must be a JSON object")
    _require(
        section.get("doctrine") == "ordinary_access_intimacy_not_narratively_exhaustive",
        "doctrine_invalid",
        "environments.doctrine must be ordinary_access_intimacy_not_narratively_exhaustive",
    )
    _require(
        isinstance(section.get("examples"), list) and section["examples"],
        "doctrine_invalid",
        "environments.examples must be a non-empty list",
    )


def _validate_prop_philosophy(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "prop_philosophy must be a JSON object")
    _require(
        isinstance(section.get("props_may"), list) and section["props_may"],
        "doctrine_invalid",
        "prop_philosophy.props_may must be a non-empty list",
    )
    _require(
        section.get("loose_motivation_acceptable") is True,
        "doctrine_invalid",
        "prop_philosophy.loose_motivation_acceptable must be true",
    )
    _require(
        isinstance(section.get("forbidden"), list) and section["forbidden"],
        "doctrine_invalid",
        "prop_philosophy.forbidden must be a non-empty list",
    )


def _validate_imperfection_tolerance(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "imperfection_tolerance must be a JSON object")
    _require(
        section.get("principle") == "harmless_imperfection_is_not_a_hard_failure",
        "doctrine_invalid",
        "imperfection_tolerance.principle must be harmless_imperfection_is_not_a_hard_failure",
    )
    _require(
        isinstance(section.get("do_not_reject_for"), list) and section["do_not_reject_for"],
        "doctrine_invalid",
        "imperfection_tolerance.do_not_reject_for must be a non-empty list",
    )


def _validate_safety_boundaries(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "safety_boundaries must be a JSON object")
    hard_failures = section.get("hard_failures")
    _require(
        isinstance(hard_failures, list) and set(hard_failures) == set(REQUIRED_SAFETY_HARD_FAILURES),
        "doctrine_invalid",
        "safety_boundaries.hard_failures must contain exactly the required hard-failure list",
    )
    overriding_rules = section.get("overriding_rules")
    _require(
        isinstance(overriding_rules, list)
        and set(REQUIRED_SAFETY_OVERRIDING_RULES).issubset(set(overriding_rules)),
        "doctrine_invalid",
        "safety_boundaries.overriding_rules must contain every required overriding rule",
    )


def _validate_originality_boundary(section: Any) -> None:
    _require(isinstance(section, dict), "doctrine_invalid", "originality_boundary must be a JSON object")
    rules = section.get("rules")
    _require(
        isinstance(rules, list) and set(REQUIRED_ORIGINALITY_RULES).issubset(set(rules)),
        "doctrine_invalid",
        "originality_boundary.rules must contain every required originality rule",
    )


_SECTION_VALIDATORS = {
    "character_definition": _validate_character_definition,
    "hard_identity_continuity": _validate_hard_identity_continuity,
    "behavioral_identity": _validate_behavioral_identity,
    "viewer_relationship": _validate_viewer_relationship,
    "movement_vocabulary": _validate_movement_vocabulary,
    "wardrobe_and_sensuality": _validate_wardrobe_and_sensuality,
    "environments": _validate_environments,
    "prop_philosophy": _validate_prop_philosophy,
    "imperfection_tolerance": _validate_imperfection_tolerance,
    "safety_boundaries": _validate_safety_boundaries,
    "originality_boundary": _validate_originality_boundary,
}


def _validate_doctrine(payload: dict[str, Any]) -> None:
    _require(
        payload.get("schema_version") == "lena_character_doctrine_v1",
        "doctrine_invalid",
        "unexpected character doctrine schema_version",
    )
    _require(
        payload.get("authority_id") == "lena_character_doctrine_v1",
        "doctrine_invalid",
        "unexpected character doctrine authority_id",
    )
    _require(payload.get("influencer_id") == "lena", "doctrine_invalid", "unexpected influencer_id")
    _require(
        isinstance(payload.get("version"), str) and payload["version"].strip(),
        "doctrine_invalid",
        "version must be a non-empty string",
    )
    _require(
        _is_valid_git_sha(payload.get("authored_against_repository_revision")),
        "doctrine_invalid",
        "authored_against_repository_revision must be a 40-character lowercase git commit sha",
    )
    _require(
        isinstance(payload.get("created_at_utc"), str) and payload["created_at_utc"].strip(),
        "doctrine_invalid",
        "created_at_utc must be a non-empty string",
    )

    owner = payload.get("owner")
    _require(isinstance(owner, dict), "doctrine_invalid", "owner must be a JSON object")
    _require(
        owner.get("human_signoff_required_for_change") is True,
        "doctrine_invalid",
        "owner.human_signoff_required_for_change must be true",
    )

    change_control = payload.get("change_control")
    _require(isinstance(change_control, dict), "doctrine_invalid", "change_control must be a JSON object")
    _require(
        isinstance(change_control.get("rules"), list) and change_control["rules"],
        "doctrine_invalid",
        "change_control.rules must be a non-empty list",
    )

    invalidation = payload.get("invalidation")
    _require(isinstance(invalidation, dict), "doctrine_invalid", "invalidation must be a JSON object")
    _require(
        isinstance(invalidation.get("rules"), list) and invalidation["rules"],
        "doctrine_invalid",
        "invalidation.rules must be a non-empty list",
    )

    for section_name in REQUIRED_TOP_LEVEL_SECTIONS:
        _require(
            section_name in payload, "doctrine_invalid", f"missing required section: {section_name}"
        )
        _SECTION_VALIDATORS[section_name](payload[section_name])


def load_doctrine(path: Path = DOCTRINE_PATH) -> dict[str, Any]:
    payload = _read_doctrine(path)
    _validate_doctrine(payload)
    return payload


def doctrine_sha256(path: Path = DOCTRINE_PATH) -> str:
    """The sha256 a downstream consumer should record and re-check.

    A future consumer (not wired in this change) should record this value
    alongside ``doctrine_provenance()`` at the time it reads the doctrine, and
    re-compute it before trusting a cached copy. A mismatch means the
    doctrine changed since the consumer last read it and must be re-validated
    before proceeding -- never silently accepted.
    """
    if not path.is_file():
        raise CharacterDoctrineError(
            "doctrine_missing", f"character doctrine artifact is missing: {path}"
        )
    return _sha256_bytes(path.read_bytes())


def doctrine_provenance(path: Path = DOCTRINE_PATH) -> dict[str, Any]:
    """The exact fields a downstream consumer should bind to.

    Mirrors the source-path + sha256 + version binding pattern already used
    for recommendation/candidate/reconciliation artifacts elsewhere in this
    pipeline. Not wired into any consumer by this change.

    Consumers must bind primarily to ``source_doctrine_artifact_sha256`` --
    that sha256 is the doctrine's actual immutable identity. A nonsemantic
    formatting edit to the doctrine file still changes this sha256 and must
    invalidate any cached downstream binding unless the consumer explicitly
    re-reads and regenerates it.
    ``doctrine_authored_against_repository_revision`` is provided for
    traceability only: it records what repository state the doctrine was
    designed against, and must never be treated as, or claimed to be, a
    commit that contains this doctrine artifact.
    """
    payload = load_doctrine(path)
    return {
        "source_doctrine_artifact_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "source_doctrine_artifact_sha256": doctrine_sha256(path),
        "doctrine_version": payload.get("version"),
        "doctrine_authored_against_repository_revision": payload.get(
            "authored_against_repository_revision"
        ),
    }


def doctrine_summary(path: Path = DOCTRINE_PATH) -> dict[str, Any]:
    payload = load_doctrine(path)
    return {
        "doctrine_status": "ready",
        "authority_id": payload.get("authority_id"),
        "version": payload.get("version"),
        "defining_qualities": list(payload["character_definition"]["defining_qualities"]),
    }
