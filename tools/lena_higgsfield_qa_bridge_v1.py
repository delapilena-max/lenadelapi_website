from __future__ import annotations

# Higgsfield-native QA bridge for Lena photo renders -- the smallest link
# between a real Higgsfield executor artifact and the existing, provider-
# agnostic QA contract (pipeline/qa/lena_photo_qa.py).
#
# Mirrors tools/lena_review_proof_render_v1.py's shape and read-only
# discipline exactly, but reads Higgsfield's real artifact shape instead of
# Kling's workorder-manifest shape:
#   pipeline/higgsfield_debug/<date>/<slot_id>/result_manifest.json
#   (the saved_image_path field inside it, not a separate workorder lookup)
#
# Reuses pipeline/qa/lena_photo_qa.py's schema/scaffold/validator wholesale --
# does not define a second QA schema, does not duplicate validation logic.
# The only new thing here is an adapter that reshapes a Higgsfield
# result_manifest.json into the slot-shaped dict lena_photo_qa.py's
# Kling-era functions expect (slot_id / media_type / metadata.wardrobe_
# outfit_id / metadata.environment_id).
#
# Read-only except for creating an "unreviewed" QA scaffold if one doesn't
# already exist (same non-clobber behavior as lena_review_proof_render_v1.py --
# pipeline.qa.lena_photo_qa.save_qa_template() never overwrites an existing
# QA file unless force=True is passed explicitly). Does not call any
# generation, publish, or queue surface. No pipeline.env_loader import --
# nothing Higgsfield-related lives in .env (see pipeline/higgsfield_lena_api_
# executor.py's own doctrine note).
#
# Fails clearly (raises, non-zero exit) if the manifest or the referenced
# image artifact cannot be resolved -- never invents missing metadata.
#
# Run (prints the review bundle, creates an unreviewed scaffold if missing):
#   python tools/lena_higgsfield_qa_bridge_v1.py --date 2026-07-09 --slot-id readypack0709-pack008-07-photo

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.qa import lena_photo_qa  # noqa: E402

HIGGSFIELD_DEBUG_ROOT = ROOT / "pipeline" / "higgsfield_debug"


class ResolveError(Exception):
    """Raised for any hard-fail condition in manifest/image resolution. Never
    caught silently -- main() reports it and exits non-zero. This module
    never invents missing metadata to paper over a resolution failure."""


def _manifest_path(date_str: str, slot_id: str) -> Path:
    return HIGGSFIELD_DEBUG_ROOT / date_str / slot_id / "result_manifest.json"


def _load_manifest(date_str: str, slot_id: str) -> Dict[str, Any]:
    path = _manifest_path(date_str, slot_id)
    if not path.exists():
        raise ResolveError(f"no Higgsfield result_manifest.json for this slot: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ResolveError(f"failed to parse {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ResolveError(f"{path} did not contain a JSON object")
    return manifest


def _resolve_image_path(manifest: Dict[str, Any]) -> Path:
    raw = manifest.get("saved_image_path")
    if not raw:
        raise ResolveError("manifest has no saved_image_path -- cannot resolve the image artifact")
    image_path = Path(str(raw))
    if not image_path.exists():
        raise ResolveError(f"manifest's saved_image_path does not exist on disk: {image_path}")
    return image_path


def _read_json_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _slot_adapter(manifest: Dict[str, Any], date_str: str) -> Dict[str, Any]:
    """Reshapes a Higgsfield result_manifest.json into the slot-shaped dict
    lena_photo_qa.build_qa_template()/save_qa_template() expect
    (slot_id / media_type / metadata.wardrobe_outfit_id / metadata.
    environment_id). Higgsfield's manifest has no environment_id field at
    all (it has 'lane' instead) -- left explicitly None rather than
    invented, and reported as a known gap, not silently backfilled."""
    return {
        "slot_id": manifest.get("slot_id"),
        "media_type": "photo",
        "metadata": {
            "wardrobe_outfit_id": manifest.get("wardrobe_outfit_id"),
            "wardrobe_outfit_name": manifest.get("wardrobe_outfit_name"),
            "wardrobe_silhouette_class": manifest.get("wardrobe_silhouette_class"),
            "environment_id": None,  # not present in the Higgsfield manifest shape -- known gap, see module docstring
            "lane": manifest.get("lane"),
        },
    }


def build_higgsfield_review_bundle(date_str: str, slot_id: str, force_scaffold: bool = False) -> Dict[str, Any]:
    manifest = _load_manifest(date_str, slot_id)
    if manifest.get("slot_id") != slot_id:
        raise ResolveError(
            f"manifest slot_id {manifest.get('slot_id')!r} does not match requested {slot_id!r}"
        )
    image_path = _resolve_image_path(manifest)
    slot_adapter = _slot_adapter(manifest, date_str)

    qa_path = lena_photo_qa.save_qa_template(slot_adapter, date_str, force=force_scaffold)
    qa_result = _read_json_if_exists(qa_path)

    return {
        "slot_id": slot_id,
        "date": date_str,
        "provider": manifest.get("provider"),
        "job_type": manifest.get("job_type"),
        "custom_reference_id": manifest.get("custom_reference_id"),
        "prompt_sha256": manifest.get("prompt_sha256"),
        "prompt_length": manifest.get("prompt_length"),
        "image_prompt": manifest.get("image_prompt"),
        "pose_body_language_id": manifest.get("pose_body_language_id"),
        "pose_body_language_label": manifest.get("pose_body_language_label"),
        "pose_text": manifest.get("pose_text"),
        "expression_gaze_id": manifest.get("expression_gaze_id"),
        "expression_text": manifest.get("expression_text"),
        "wardrobe_outfit_id": manifest.get("wardrobe_outfit_id"),
        "wardrobe_outfit_name": manifest.get("wardrobe_outfit_name"),
        "wardrobe_silhouette_class": manifest.get("wardrobe_silhouette_class"),
        "effective_wardrobe_silhouette_class": manifest.get("effective_wardrobe_silhouette_class"),
        "lane": manifest.get("lane"),
        "text_surface_risk_terms_found": manifest.get("text_surface_risk_terms_found"),
        "hard_exclude_reasons": manifest.get("hard_exclude_reasons"),
        "provider_job_id": manifest.get("provider_job_id"),
        "provider_status": manifest.get("provider_status"),
        "artifacts": {
            "manifest_path": str(_manifest_path(date_str, slot_id)),
            "generated_image_path": str(image_path),
            "generated_image_exists": True,
            "qa_result_path": str(qa_path),
            "qa_overall_status": (qa_result or {}).get("overall"),
        },
        "known_gaps": [
            "environment_id is not present in the Higgsfield manifest shape (manifest has 'lane' instead) -- "
            "left as None in the QA scaffold's metadata, not invented.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="e.g. 2026-07-09")
    parser.add_argument("--slot-id", required=True, dest="slot_id")
    parser.add_argument(
        "--force-scaffold", action="store_true", dest="force_scaffold",
        help="overwrite an existing QA file with a fresh unreviewed scaffold (default: never overwrite)",
    )
    args = parser.parse_args()

    try:
        bundle = build_higgsfield_review_bundle(args.date, args.slot_id, force_scaffold=args.force_scaffold)
    except ResolveError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({"ok": True, **bundle}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
