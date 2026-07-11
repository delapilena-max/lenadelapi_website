from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pipeline.qa.lena_photo_qa as lena_photo_qa
from tools.lena_build_publish_packet_v1 import (
    build_queue_draft,
    resolve_packet_inputs_higgsfield,
)

# tools/lena_build_publish_packet_v1.py imports lena_higgsfield_qa_bridge_v1
# by its bare module name (TOOLS_DIR is inserted into sys.path at that
# module's import time), not as tools.lena_higgsfield_qa_bridge_v1 -- those
# are two different sys.modules entries with independent module-level
# constants. Importing it the same (bare) way here, after the import above
# has already put TOOLS_DIR on sys.path, ensures monkeypatching
# HIGGSFIELD_DEBUG_ROOT actually affects the instance the resolver uses.
import lena_higgsfield_qa_bridge_v1 as qa_bridge_mod  # noqa: E402

# Structured creative-provenance forwarding (2026-07-11): proves
# pose_body_language_id/expression_gaze_id are read only from the real,
# authoritative Higgsfield generation manifest and survive unchanged into
# queue_draft.metadata -- never inferred from pose_text/image_prompt, never
# fabricated when genuinely absent. Fixture values mirror the real shape
# confirmed on disk at pipeline/higgsfield_debug/2026-07-09/
# readypack0709-pack003-08-photo/result_manifest.json (pose_p018/exp_g013),
# but this test never touches that real file -- everything here is written
# to an isolated tmp_path fixture root.


def _write_qa_pass(asset_review_root: Path, date_str: str, slot_id: str) -> None:
    status_fields = [
        "identity_fidelity", "face_realism_anti_generic_drift", "skin_realism_no_invented_marks",
        "wardrobe_class_fidelity", "public_scene_clothing_continuity", "outerwear_underlayer_correctness",
        "body_shape_continuity", "hands_anatomy_sanity", "environment_realism_scene_coherence",
        "caption_scene_coherence",
    ]
    qa = {
        "schema_version": "2",
        "slot_id": slot_id,
        "date": date_str,
        "media_type": "photo",
        "reviewed_by": "test-fixture",
        "reviewed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "checklist": {k: {"status": "pass", "notes": "fixture"} for k in status_fields},
        "production_scoring": {
            "hook_strength": {"score": "strong", "notes": "fixture"},
            "styling_sexy_platform_safe": {"status": "pass", "notes": "fixture"},
            "outfit_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": "fixture"},
            "scene_variety_vs_recent_posts": {"status": "not_yet_measured", "notes": "fixture"},
        },
        "overall": "pass",
        "failure_reasons": [],
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "publish_ready": True,
        "publish_ready_reason": "fixture",
    }
    out_path = asset_review_root / date_str / f"{slot_id}_qa.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(qa, indent=2), encoding="utf-8")


def _write_higgsfield_manifest(
    debug_root: Path,
    date_str: str,
    slot_id: str,
    image_path: Path,
    pose_body_language_id=None,
    expression_gaze_id=None,
    pose_text: str = "weight shift onto one hip, closed mouth smile direct",
) -> None:
    manifest = {
        "slot_id": slot_id,
        "provider": "higgsfield",
        "job_type": "text2image_soul_v2",
        "cli_soul_name": "Lena",
        "custom_reference_id": "test-custom-reference-id",
        # Deliberately mentions real pose/expression label words, to prove
        # forwarding never parses this field.
        "image_prompt": "a real test prompt: weight_shift_one_hip, closed_mouth_smile_direct",
        "saved_image_path": str(image_path),
        "lane": "test lane",
        "pose_text": pose_text,
        "provider_job_id": "test-provider-job-id",
        "provider_status": "succeed",
    }
    if pose_body_language_id is not None:
        manifest["pose_body_language_id"] = pose_body_language_id
    if expression_gaze_id is not None:
        manifest["expression_gaze_id"] = expression_gaze_id
    manifest_dir = debug_root / date_str / slot_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "result_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


@pytest.fixture
def isolated_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirects the Higgsfield manifest root and the QA module's
    asset-review root at isolated tmp_path directories -- never touches any
    real repo path. HIGGSFIELD_DEBUG_ROOT is a module-level constant read at
    call time inside tools/lena_higgsfield_qa_bridge_v1.py's own functions,
    which tools/lena_build_publish_packet_v1.py imports by reference -- so
    patching the origin module's constant is the correct isolation point."""
    debug_root = tmp_path / "higgsfield_debug"
    asset_review_root = tmp_path / "asset_review" / "lena"
    monkeypatch.setattr(qa_bridge_mod, "HIGGSFIELD_DEBUG_ROOT", debug_root)
    monkeypatch.setattr(lena_photo_qa, "ASSET_REVIEW_ROOT", asset_review_root)
    return {"debug_root": debug_root, "asset_review_root": asset_review_root}


def _make_image(path: Path) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(path, format="PNG")
    return path


# 1/2/3. pose_body_language_id and expression_gaze_id are forwarded when
# present, and the exact real-shaped proof values survive unchanged.
def test_higgsfield_resolution_forwards_exact_real_proof_values(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-09"
    slot_id = "readypack-test-pack003-08-photo"
    image_path = _make_image(tmp_path / "assets" / "seed.png")

    _write_higgsfield_manifest(
        isolated_roots["debug_root"], date_str, slot_id, image_path,
        pose_body_language_id="pose_p018", expression_gaze_id="exp_g013",
    )
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_higgsfield(date_str, slot_id)
    assert resolved["pose_body_language_id"] == "pose_p018"
    assert resolved["expression_gaze_id"] == "exp_g013"

    draft = build_queue_draft(resolved, Path("dummy_packet.md"))
    assert draft["metadata"]["pose_body_language_id"] == "pose_p018"
    assert draft["metadata"]["expression_gaze_id"] == "exp_g013"


# 4/5/8. Missing fields remain genuinely absent -- historical Higgsfield
# renders that predate these two banks build successfully with neither.
def test_higgsfield_resolution_leaves_ids_none_when_absent(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-09"
    slot_id = "readypack-test-historical-photo"
    image_path = _make_image(tmp_path / "assets" / "seed2.png")

    _write_higgsfield_manifest(isolated_roots["debug_root"], date_str, slot_id, image_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_higgsfield(date_str, slot_id)
    assert resolved["pose_body_language_id"] is None
    assert resolved["expression_gaze_id"] is None

    draft = build_queue_draft(resolved, Path("dummy_packet.md"))
    assert "pose_body_language_id" not in draft["metadata"]
    assert "expression_gaze_id" not in draft["metadata"]


# 6/7. No inference from pose_text or image_prompt, even when both contain
# real pose/expression label text.
def test_higgsfield_resolution_never_infers_ids_from_pose_text_or_prompt(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-09"
    slot_id = "readypack-test-noinfer-photo"
    image_path = _make_image(tmp_path / "assets" / "seed3.png")

    _write_higgsfield_manifest(isolated_roots["debug_root"], date_str, slot_id, image_path)
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_higgsfield(date_str, slot_id)
    assert resolved["pose"] == "weight shift onto one hip, closed mouth smile direct"
    assert "weight_shift_one_hip" in resolved["image_prompt"]
    assert resolved["pose_body_language_id"] is None
    assert resolved["expression_gaze_id"] is None


# 9/10/11/12/13. wardrobe_outfit_id, lane/activity, provider_job_id,
# source_slot_id, and output slot/post_id identity all remain unchanged by
# this slice.
def test_higgsfield_existing_identity_and_creative_fields_unchanged(tmp_path: Path, isolated_roots) -> None:
    date_str = "2026-07-09"
    slot_id = "readypack-test-identity-photo"
    image_path = _make_image(tmp_path / "assets" / "seed4.png")

    manifest_dir = isolated_roots["debug_root"] / date_str / slot_id
    _write_higgsfield_manifest(
        isolated_roots["debug_root"], date_str, slot_id, image_path,
        pose_body_language_id="pose_p018", expression_gaze_id="exp_g013",
    )
    # Add wardrobe_outfit_id directly to the manifest (real field the
    # resolver already reads, unrelated to this slice).
    manifest_path = manifest_dir / "result_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wardrobe_outfit_id"] = "wc_p006"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_qa_pass(isolated_roots["asset_review_root"], date_str, slot_id)

    resolved = resolve_packet_inputs_higgsfield(date_str, slot_id)
    draft = build_queue_draft(resolved, Path("dummy_packet.md"))

    assert draft["slot_id"] == slot_id
    assert draft["post_id"] == slot_id
    assert draft["metadata"]["source_slot_id"] == slot_id
    assert draft["metadata"]["wardrobe_outfit_id"] == "wc_p006"
    assert draft["metadata"]["activity"] == "test lane"
    assert draft["metadata"]["provider_job_id"] == "test-provider-job-id"
    assert draft["media_type"] == "photo"


# 16/17/18. No network call, no publish, no real queue item mutated --
# structural guarantee: this module imports no requests/publisher/
# queue-processing surface (tools/lena_build_publish_packet_v1.py's own
# header docstring states this explicitly), and every test above operates
# purely on tmp_path fixtures, never pipeline/queue/ or any real repo path.
