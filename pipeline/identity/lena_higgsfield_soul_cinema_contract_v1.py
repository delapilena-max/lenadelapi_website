from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

MODEL = "soul_cinema_studio"
ASPECT_RATIO = "9:16"
QUALITY = "2k"
ENHANCE_PROMPT = False
# Rotated 2026-07-23: Nicolas retrained Lena's Soul 2.0 from scratch on the
# provider account (the prior e45ec580 Soul did not visually match Lena and
# is preserved only as historical fact -- see APPROVED_CUSTOM_REFERENCE_IDS
# in pipeline/identity/lena_higgsfield_identity.py).
CUSTOM_REFERENCE_ID = "79119c27-64fc-47f8-9ff3-c174d12932aa"
REFERENCE_AUTHORITY_PATH = (
    ROOT / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json"
)
REFERENCE_BINDING_SCHEMA_VERSION = (
    "lena_higgsfield_soul_cinema_reference_binding_v1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class SoulCinemaContractError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise SoulCinemaContractError(code, detail)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _resolve_repo_file(path_value: str, *, code: str, label: str) -> Path:
    raw = str(path_value or "").strip()
    _require(bool(raw), code, f"{label} path is missing")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise SoulCinemaContractError(code, f"{label} path escapes the repository") from exc
    _require(resolved.is_file(), code, f"{label} file does not exist: {resolved}")
    return resolved


def load_generation_reference_binding() -> dict[str, Any]:
    _require(
        REFERENCE_AUTHORITY_PATH.is_file(),
        "generation_reference_authority_missing",
        f"generation reference authority does not exist: {REFERENCE_AUTHORITY_PATH}",
    )
    try:
        authority = json.loads(REFERENCE_AUTHORITY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SoulCinemaContractError(
            "generation_reference_authority_malformed",
            f"generation reference authority is unreadable: {exc}",
        ) from exc
    _require(
        isinstance(authority, dict)
        and authority.get("schema_version") == "lena_identity_reference_authority_v1",
        "generation_reference_authority_malformed",
        "generation reference authority has the wrong schema",
    )

    references = authority.get("references")
    metadata = authority.get("reference_metadata")
    _require(
        isinstance(references, list) and len(references) == 1,
        "generation_reference_ambiguous",
        "Soul Cinema generation requires exactly one authoritative source image",
    )
    _require(
        isinstance(metadata, list) and len(metadata) == 1 and isinstance(metadata[0], dict),
        "generation_reference_metadata_missing",
        "generation reference authority must describe exactly one source image",
    )
    reference = references[0]
    _require(
        isinstance(reference, dict),
        "generation_reference_malformed",
        "generation reference entry must be an object",
    )
    recorded_sha = str(reference.get("sha256") or "").strip()
    _require(
        bool(_SHA256_RE.fullmatch(recorded_sha)),
        "generation_reference_sha_invalid",
        "generation reference SHA must be lowercase SHA-256",
    )
    reference_path = _resolve_repo_file(
        str(reference.get("path") or ""),
        code="generation_reference_missing",
        label="generation reference",
    )
    _require(
        reference_path.suffix.lower() in _ALLOWED_REFERENCE_SUFFIXES,
        "generation_reference_format_unsupported",
        "generation reference must be PNG, JPEG, or WebP",
    )
    actual_sha = _sha256_file(reference_path)
    _require(
        actual_sha == recorded_sha,
        "generation_reference_sha_mismatch",
        "generation reference bytes do not match the authority artifact",
    )
    reference_set_sha = str(authority.get("reference_set_sha256") or "").strip()
    _require(
        bool(_SHA256_RE.fullmatch(reference_set_sha)),
        "generation_reference_set_sha_invalid",
        "generation reference-set SHA must be lowercase SHA-256",
    )

    authority_metadata = metadata[0]
    return {
        "schema_version": REFERENCE_BINDING_SCHEMA_VERSION,
        "model": MODEL,
        "provider_parameter": "image_references",
        "reference_count": 1,
        "authority_artifact_path": _repo_relative(REFERENCE_AUTHORITY_PATH),
        "authority_artifact_sha256": _sha256_file(REFERENCE_AUTHORITY_PATH),
        "reference_set_sha256": reference_set_sha,
        "reference_image_path": _repo_relative(reference_path),
        "reference_image_sha256": actual_sha,
        "authority_scope": str(authority_metadata.get("authority_scope") or ""),
        "reference_role": str(authority_metadata.get("role") or ""),
    }


def validate_generation_reference_binding(value: Any) -> dict[str, Any]:
    _require(
        isinstance(value, dict),
        "generation_reference_binding_missing",
        "generation reference binding is missing",
    )
    canonical = load_generation_reference_binding()
    _require(
        value == canonical,
        "generation_reference_binding_mismatch",
        "generation reference binding does not match current authoritative bytes",
    )
    return canonical


def resolve_reference_image(binding: dict[str, Any] | None = None) -> Path:
    validated = validate_generation_reference_binding(
        binding if binding is not None else load_generation_reference_binding()
    )
    return _resolve_repo_file(
        str(validated["reference_image_path"]),
        code="generation_reference_missing",
        label="generation reference",
    )
