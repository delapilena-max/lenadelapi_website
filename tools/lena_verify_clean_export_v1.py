from __future__ import annotations

# Lena clean-export verification gate -- the fail-closed check that decides
# whether a source asset's already-produced clean derivative (from
# tools/lena_scrub_media_metadata_v1.py) is eligible to become a queue
# item's publish media path.
#
# This is the ONLY new module this slice adds. It is not a new queue
# system, not a new approval system, and not a new provenance store -- it
# re-derives the clean-derivative/provenance-sidecar paths using the
# scrubber's own existing, unmodified naming convention
# (resolve_clean_output_path()) and re-verifies the scrubber's own
# existing, unmodified sidecar schema (source_sha256/output_sha256/
# verified_clean_after_scrub) by recomputing every hash from the real files
# on disk -- it never trusts the sidecar's self-reported claims alone.
#
# Required invariant (never weakened, never bypassed):
#   verified clean derivative exists
#   AND source_sha256 matches the actual source file (recomputed)
#   AND output_sha256 matches the actual derivative file (recomputed)
#   AND verified_clean_after_scrub == true (the literal boolean True, not
#       merely a truthy value)
#   AND clean derivative path != source path
#   AND media type is one the scrubber itself supports
#   -> eligible
#   otherwise -> CleanExportVerificationError. No silent repair of a
#   mismatch. No fallback to the raw source. No bypass flag exists,
#   anywhere in this module, by design.
#
# Does not scrub anything. Does not call the scrubber. Does not write or
# modify any file. Read-only, pure verification of already-existing
# artifacts on disk.

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lena_scrub_media_metadata_v1 import (  # noqa: E402
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    resolve_clean_output_path,
)


class CleanExportVerificationError(Exception):
    """Raised for any hard-fail condition. Callers must never catch this
    silently or fall back to the raw source -- the only correct response is
    to refuse whatever operation (e.g. queue promotion) depended on this
    check."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def resolve_clean_provenance_sidecar_path(clean_path: Path) -> Path:
    """Matches tools/lena_scrub_media_metadata_v1.py::_build_report()'s own
    provenance_path formula exactly (target_path.stem + "_provenance.json").
    Not importable as a standalone function from the scrubber module (the
    formula is inlined inside _build_report()), so this reproduces the
    identical convention rather than inventing a new one."""
    return clean_path.with_name(clean_path.stem + "_provenance.json")


def verify_clean_export(source_path: Path) -> Dict[str, Any]:
    """Read-only. Raises CleanExportVerificationError on any hard-fail
    condition. Returns a dict of verified facts on success. Never fabricates
    a field the scrubber's own sidecar schema doesn't actually produce --
    e.g. there is currently no "scrubber version" field in that schema, so
    none is invented here."""
    source_path = Path(source_path)

    if not source_path.exists():
        raise CleanExportVerificationError(f"source asset does not exist: {source_path}")

    ext = source_path.suffix.lower()
    if ext not in IMAGE_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
        raise CleanExportVerificationError(
            f"unsupported media type for clean-export verification: {ext!r} (source: {source_path})"
        )

    clean_path = resolve_clean_output_path(source_path)
    if clean_path.resolve() == source_path.resolve():
        raise CleanExportVerificationError(
            "clean derivative path resolved to the same path as the source -- refusing"
        )
    if not clean_path.exists():
        raise CleanExportVerificationError(
            f"clean derivative does not exist: {clean_path} -- run "
            "tools/lena_scrub_media_metadata_v1.py against this source first"
        )

    sidecar_path = resolve_clean_provenance_sidecar_path(clean_path)
    if not sidecar_path.exists():
        raise CleanExportVerificationError(f"clean-export provenance sidecar does not exist: {sidecar_path}")

    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise CleanExportVerificationError(
            f"clean-export provenance sidecar failed to parse: {sidecar_path}: {exc}"
        ) from exc
    if not isinstance(sidecar, dict):
        raise CleanExportVerificationError(f"clean-export provenance sidecar is not a JSON object: {sidecar_path}")

    actual_source_sha256 = _sha256_file(source_path)
    sidecar_source_sha256 = sidecar.get("source_sha256")
    if sidecar_source_sha256 != actual_source_sha256:
        raise CleanExportVerificationError(
            f"clean-export sidecar source_sha256 {sidecar_source_sha256!r} does not match the "
            f"recomputed source hash {actual_source_sha256!r} -- refusing, no silent repair"
        )

    actual_output_sha256 = _sha256_file(clean_path)
    sidecar_output_sha256 = sidecar.get("output_sha256")
    if sidecar_output_sha256 != actual_output_sha256:
        raise CleanExportVerificationError(
            f"clean-export sidecar output_sha256 {sidecar_output_sha256!r} does not match the "
            f"recomputed derivative hash {actual_output_sha256!r} -- refusing, no silent repair"
        )

    if sidecar.get("verified_clean_after_scrub") is not True:
        raise CleanExportVerificationError(
            "clean-export sidecar verified_clean_after_scrub is "
            f"{sidecar.get('verified_clean_after_scrub')!r}, expected the literal boolean true"
        )

    return {
        "source_path": str(source_path),
        "source_sha256": actual_source_sha256,
        "clean_derivative_path": str(clean_path),
        "clean_derivative_sha256": actual_output_sha256,
        "clean_provenance_sidecar_path": str(sidecar_path),
        "verified_clean_after_scrub": True,
        "generated_by": sidecar.get("generated_by"),
        "created_at_utc": sidecar.get("created_at_utc"),
        "kind": sidecar.get("kind"),
    }
