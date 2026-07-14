from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import pipeline.qa.lena_photo_qa as lena_photo_qa
import tools.lena_build_publish_packet_v1 as packet_mod
from tools import lena_photo_qa_disposition_v1 as disposition
from tools.lena_build_publish_packet_v1 import (
    build_queue_draft,
    resolve_packet_inputs_higgsfield,
    ResolveError,
    write_packet,
    write_queue_draft,
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


def _write_accepted_disposition(asset_review_root: Path, date_str: str, slot_id: str, image_sha: str) -> Path:
    artifact = {
        "schema_version": disposition.SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slot_id": slot_id,
        "image_sha256": image_sha,
        "generation_provenance": {"date": date_str},
        "reason_codes": [],
        "disposition": "accept",
        "reviewer_type": "bounded_visual_provider",
        "side_effects_performed": [],
        "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
    }
    out_path = asset_review_root / date_str / f"{slot_id}__{image_sha}_qa_disposition.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return out_path


def _write_generated_image(path: Path, color: str = "white") -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1152, 2048), color=color).save(path, format="PNG")
    return path


def _bridge_artifact(
    repo_root: Path,
    date_str: str,
    slot_id: str,
    image_path: Path,
    *,
    decision_path: Path,
    manifest_path: Path,
    identity_evidence_path: Path,
    authority_path: Path,
    reference_path: Path,
    decision_kind: str = "selected_candidate",
) -> dict:
    image_sha = disposition._sha256_file(image_path)
    manifest_sha = disposition._sha256_file(manifest_path)
    identity_sha = disposition._sha256_file(identity_evidence_path)
    authority_sha = "1" * 64
    reference_sha = "2" * 64
    reference_set_sha = "3" * 64
    decision_fingerprint = "4" * 64
    visual_observations = {
        "schema_version": disposition.VISUAL_SCHEMA_VERSION,
        "observations": {
            key: {"status": "pass", "reason_codes": [], "notes": f"{key} passed"}
            for key in disposition.VISUAL_OBSERVATION_KEYS
        },
    }
    observations_sha = disposition._sha256_bytes(disposition._canonical_bytes(visual_observations))
    request_binding_sha = disposition._sha256_bytes(
        disposition._canonical_bytes(
            {
                "decision_fingerprint_sha256": decision_fingerprint,
                "image_sha256": image_sha,
                "reference_set_sha256": reference_set_sha,
            }
        )
    )
    qa_checks = {
        **visual_observations["observations"],
        "dimensions": {"status": "pass", "reason_codes": [], "notes": "locally measured 1152x2048"},
        "file_integrity": {"status": "pass", "reason_codes": [], "notes": "Pillow verify and reopen succeeded"},
        "format": {"status": "pass", "reason_codes": [], "notes": "locally detected supported format PNG"},
        "downstream_compatibility": {"status": "pass", "reason_codes": [], "notes": "approved Higgsfield dimensions and supported still-image format"},
    }
    return {
        "schema_version": disposition.SCHEMA_VERSION,
        "influencer_id": "lena",
        "generated_at_utc": "2026-07-14T04:16:35Z",
        "authority_commit": "a" * 40,
        "decision_artifact_path": str(decision_path),
        "decision_fingerprint_sha256": decision_fingerprint,
        "candidate_id": f"{slot_id}::hcr_006::cbn_004",
        "slot_id": slot_id,
        "lane": "night out",
        "recipe_id": "hcr_006",
        "hook_id": "cbn_004",
        "hook_text": "Tried To Dress Down. Failed.",
        "caption_seed": "caught me on the way in",
        "prompt_sha256": "5" * 64,
        "image_path": str(image_path),
        "image_sha256": image_sha,
        "generation_provenance": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha,
            "date": date_str,
            "field_sources": {
                "candidate_and_authority": str(decision_path),
                "provider_generation": str(manifest_path),
                "local_image_hash_and_identity": str(identity_evidence_path),
            },
            "provider": "higgsfield",
            "job_type": "text2image_soul_v2",
            "provider_job_id": "job-123",
            "provider_status": "completed",
            "custom_reference_id": "ref-123",
            "soul_name": "Lena",
            "soul_type": "soul_2",
        },
        "identity_reference_provenance": {
            "authority_id": "lena_identity_reference_authority_v1",
            "authority_artifact_path": str(authority_path),
            "authority_artifact_sha256": authority_sha,
            "authority_commit": "b" * 40,
            "authority_artifact_commit": "a" * 40,
            "reference_set_sha256": reference_set_sha,
            "references": [
                {
                    "path": str(reference_path),
                    "sha256": reference_sha,
                    "format": "PNG",
                    "width": 1152,
                    "height": 2048,
                    "authority_relative_path": "pipeline/higgsfield_library/lena/reference.png",
                }
            ],
            "authority_semantics": "exact committed authority artifact and reference-set binding",
        },
        "qa_inputs": {
            "identity_evidence_path": str(identity_evidence_path),
            "identity_evidence_sha256": identity_sha,
            "identity_verification_result": "pass",
            "decision_kind": decision_kind,
        },
        "qa_checks": qa_checks,
        "reason_codes": [],
        "disposition": "accept",
        "retry_eligible": False,
        "hard_stop_reason": None,
        "confidence": "high",
        "reviewer_type": "bounded_visual_provider",
        "visual_judgment_source": {
            "reviewer_type": "bounded_visual_provider",
            "provider": disposition.APPROVED_VISUAL_PROVIDER,
            "model": disposition.APPROVED_VISUAL_MODEL,
            "observation_schema_version": disposition.VISUAL_SCHEMA_VERSION,
            "observations_sha256": observations_sha,
            "request_binding_sha256": request_binding_sha,
        },
        "provider_called": True,
        "side_effects_performed": [],
        "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
    }


def _bridge_context(tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch):
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(packet_mod, "ROOT", repo_root)
    date_str = "2026-07-13"
    slot_id = "lenagate-bridge-photo"
    image_path = _write_generated_image(repo_root / "tmp" / "bridge-tests" / f"{slot_id}.png")
    manifest_path = repo_root / "tmp" / "bridge-tests" / f"{slot_id}_manifest.json"
    decision_path = repo_root / "tmp" / "bridge-tests" / f"{slot_id}_decision.json"
    identity_evidence_path = repo_root / "tmp" / "bridge-tests" / f"{slot_id}_identity.json"
    authority_path = repo_root / "tmp" / "bridge-tests" / f"{slot_id}_authority.json"
    reference_path = repo_root / "tmp" / "bridge-tests" / f"{slot_id}_reference.png"
    _write_generated_image(reference_path, color="gray")
    for path, value in (
        (manifest_path, {"manifest": True}),
        (decision_path, {"decision": True}),
        (identity_evidence_path, {"identity": True}),
        (authority_path, {"authority": True}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    _write_higgsfield_manifest(isolated_roots["debug_root"], date_str, slot_id, image_path)
    artifact = _bridge_artifact(
        repo_root,
        date_str,
        slot_id,
        image_path,
        decision_path=decision_path,
        manifest_path=manifest_path,
        identity_evidence_path=identity_evidence_path,
        authority_path=authority_path,
        reference_path=reference_path,
    )
    disposition_path = isolated_roots["asset_review_root"] / date_str / f"{slot_id}__{artifact['image_sha256']}_qa_disposition.json"
    disposition_path.parent.mkdir(parents=True, exist_ok=True)
    disposition_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    decision = {
        "authority_commit": artifact["authority_commit"],
        "decision_fingerprint_sha256": artifact["decision_fingerprint_sha256"],
        "as_of_date": date_str,
    }
    candidate = {
        "candidate_id": artifact["candidate_id"],
        "slot_id": slot_id,
        "lane": artifact["lane"],
        "recipe_id": artifact["recipe_id"],
        "hook_id": artifact["hook_id"],
        "hook_text": artifact["hook_text"],
        "caption_seed": artifact["caption_seed"],
        "prompt_sha256": artifact["prompt_sha256"],
    }
    manifest = {
        "provider": artifact["generation_provenance"]["provider"],
        "job_type": artifact["generation_provenance"]["job_type"],
        "provider_job_id": artifact["generation_provenance"]["provider_job_id"],
        "provider_status": artifact["generation_provenance"]["provider_status"],
        "custom_reference_id": artifact["generation_provenance"]["custom_reference_id"],
        "cli_soul_name": artifact["generation_provenance"]["soul_name"],
        "cli_soul_type": artifact["generation_provenance"]["soul_type"],
    }
    identity = {"verification_result": "pass"}
    validated_refs = artifact["identity_reference_provenance"]["references"]
    reference_authority = {
        "authority_id": artifact["identity_reference_provenance"]["authority_id"],
        "authority_commit": artifact["identity_reference_provenance"]["authority_commit"],
    }

    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (decision, candidate, artifact["qa_inputs"]["decision_kind"]),
    )
    monkeypatch.setattr(packet_mod.lena_photo_qa_disposition, "_validate_manifest", lambda path, d, c, i, k: manifest)
    monkeypatch.setattr(packet_mod.lena_photo_qa_disposition, "_validate_identity_evidence", lambda path, d, c, m, i: identity)
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_references",
        lambda specs, authority_path, authority_sha, authority_commit: (
            validated_refs,
            artifact["identity_reference_provenance"]["reference_set_sha256"],
            reference_authority,
        ),
    )
    return {
        "date": date_str,
        "slot": slot_id,
        "image_path": image_path,
        "manifest_path": manifest_path,
        "decision_path": decision_path,
        "identity_evidence_path": identity_evidence_path,
        "authority_path": authority_path,
        "reference_path": reference_path,
        "artifact": artifact,
        "disposition_path": disposition_path,
    }


def _retry_decision(ctx: dict, *, fingerprint: str | None = None, retry_slot_id: str | None = None) -> dict:
    return {
        "authority_commit": ctx["artifact"]["authority_commit"],
        "as_of_date": ctx["date"],
        "retry_decision_fingerprint_sha256": fingerprint or ctx["artifact"]["decision_fingerprint_sha256"],
        "retry_attempt": 1,
        "retry_cap": 1,
        "original_slot_id": "lenagate-original-photo",
        "retry_slot_id": retry_slot_id or ctx["slot"],
        "original_prompt_sha256": "6" * 64,
        "retry_prompt_sha256": ctx["artifact"]["prompt_sha256"],
        "prompt_mutation": {"added_constraint": "Background identity safety"},
        "hook_text": ctx["artifact"]["hook_text"],
        "caption_seed": ctx["artifact"]["caption_seed"],
        "source_original_decision_fingerprint_sha256": "7" * 64,
        "source_original_manifest_path": str(ctx["manifest_path"]),
        "source_original_manifest_sha256": disposition._sha256_file(ctx["manifest_path"]),
        "source_original_provider_job_evidence": {
            "provider": "higgsfield",
            "provider_job_id": "job-123",
            "provider_status": "completed",
        },
        "source_valid_human_rejection_artifact_path": str(ctx["decision_path"]),
        "source_valid_human_rejection_artifact_sha256": disposition._sha256_file(ctx["decision_path"]),
        "source_retry_plan_correction_artifact_path": str(ctx["authority_path"]),
        "source_retry_plan_correction_artifact_sha256": disposition._sha256_file(ctx["authority_path"]),
    }


def _retry_candidate(ctx: dict) -> dict:
    return {
        "candidate_id": ctx["artifact"]["candidate_id"],
        "slot_id": ctx["slot"],
        "lane": ctx["artifact"]["lane"],
        "recipe_id": ctx["artifact"]["recipe_id"],
        "hook_id": ctx["artifact"]["hook_id"],
        "hook_text": ctx["artifact"]["hook_text"],
        "caption_seed": ctx["artifact"]["caption_seed"],
        "prompt_sha256": ctx["artifact"]["prompt_sha256"],
    }


def _bridge_manifest(ctx: dict) -> dict:
    return {
        "provider": ctx["artifact"]["generation_provenance"]["provider"],
        "job_type": ctx["artifact"]["generation_provenance"]["job_type"],
        "provider_job_id": ctx["artifact"]["generation_provenance"]["provider_job_id"],
        "provider_status": ctx["artifact"]["generation_provenance"]["provider_status"],
        "custom_reference_id": ctx["artifact"]["generation_provenance"]["custom_reference_id"],
        "cli_soul_name": ctx["artifact"]["generation_provenance"]["soul_name"],
        "cli_soul_type": ctx["artifact"]["generation_provenance"]["soul_type"],
    }


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
        "lane": "night out",
        "pose_text": pose_text,
        "provider_job_id": "test-provider-job-id",
        "provider_status": "succeed",
        "wardrobe_outfit_id": "wc_p017",
        "wardrobe_outfit_name": "Deep Plum Satin Slip Skirt + Black Scoop Top",
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
    assert draft["metadata"]["activity"] == "night out"
    assert draft["metadata"]["provider_job_id"] == "test-provider-job-id"
    assert draft["media_type"] == "photo"


def test_higgsfield_resolution_bridges_exactly_one_accepted_disposition_when_legacy_qa_missing(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)

    resolved = resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])

    assert resolved["qa_path"] == str(ctx["disposition_path"])
    assert resolved["qa_overall"] == "pass"
    assert resolved["qa_publish_ready"] is True
    assert resolved["qa_publish_ready_reason"] == "accepted lena_photo_qa_disposition_v1 artifact"


def test_higgsfield_resolution_bridges_accepted_retry_disposition(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["qa_inputs"]["decision_kind"] = "retry_decision"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (_retry_decision(ctx), _retry_candidate(ctx), "retry_decision"),
    )
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_manifest",
        lambda path, d, c, i, k: _bridge_manifest(ctx) if k == "retry_decision" else pytest.fail("wrong decision_kind"),
    )

    resolved = resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])

    assert resolved["qa_path"] == str(ctx["disposition_path"])
    assert resolved["qa_overall"] == "pass"
    assert resolved["qa_publish_ready"] is True


def test_higgsfield_resolution_rejects_image_tampering_sha_mismatch(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    _write_generated_image(ctx["image_path"], color="black")

    with pytest.raises(ResolveError, match="generated image bytes do not match QA disposition binding"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_manifest_mismatch(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["generation_provenance"]["provider_job_id"] = "wrong-job"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match="generation_provenance.provider_job_id"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_decision_mismatch(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["decision_fingerprint_sha256"] = "9" * 64
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match="decision_fingerprint_sha256"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_retry_decision_kind_mismatch(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["qa_inputs"]["decision_kind"] = "selected_candidate"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (_retry_decision(ctx), _retry_candidate(ctx), "retry_decision"),
    )

    with pytest.raises(ResolveError, match="qa_inputs.decision_kind"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_selected_disposition_builds_packet_and_queue_draft_end_to_end(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    out_dir = tmp_path / "packet_out"

    resolved = resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"], out_dir)
    packet_path = write_packet(resolved, out_dir, force=False)
    draft_path = write_queue_draft(resolved, packet_path, out_dir, force=False)

    assert packet_path.exists()
    assert draft_path.exists()
    packet_text = packet_path.read_text(encoding="utf-8")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert f"# Lena Publish Packet -- {ctx['slot']}" in packet_text
    assert "accepted lena_photo_qa_disposition_v1 artifact" in packet_text
    assert "**Option A (hook-first)**" in packet_text
    assert "> Tried To Dress Down. Failed." in packet_text
    assert "**Option B (seed-grounded)**" in packet_text
    assert "> Caught me on the way in." in packet_text
    assert "**Option C (scene/outfit-grounded)**" in packet_text
    assert "> Low lights, late plans, and an outfit that refused to blend in." in packet_text
    assert draft["caption"] == packet_mod.QUEUE_DRAFT_CAPTION_PLACEHOLDER
    assert draft["slot_id"] == ctx["slot"]
    assert draft["metadata"]["qa_path"] == str(ctx["disposition_path"])
    assert draft["metadata"]["source_slot_id"] == ctx["slot"]


def test_higgsfield_retry_disposition_builds_packet_and_queue_draft_end_to_end(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    out_dir = tmp_path / "packet_out"
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["qa_inputs"]["decision_kind"] = "retry_decision"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (_retry_decision(ctx), _retry_candidate(ctx), "retry_decision"),
    )
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_manifest",
        lambda path, d, c, i, k: _bridge_manifest(ctx) if k == "retry_decision" else pytest.fail("wrong decision_kind"),
    )

    resolved = resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"], out_dir)
    packet_path = write_packet(resolved, out_dir, force=False)
    draft_path = write_queue_draft(resolved, packet_path, out_dir, force=False)

    assert packet_path.exists()
    assert draft_path.exists()
    packet_text = packet_path.read_text(encoding="utf-8")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert "**Option A (hook-first)**" in packet_text
    assert "> Tried To Dress Down. Failed." in packet_text
    assert "**Option B (seed-grounded)**" in packet_text
    assert "> Caught me on the way in." in packet_text
    assert "**Option C (scene/outfit-grounded)**" in packet_text
    assert "> Low lights, late plans, and an outfit that refused to blend in." in packet_text
    assert draft["caption"] == packet_mod.QUEUE_DRAFT_CAPTION_PLACEHOLDER
    assert draft["slot_id"] == ctx["slot"]
    assert draft["metadata"]["qa_path"] == str(ctx["disposition_path"])
    assert draft["metadata"]["source_slot_id"] == ctx["slot"]


def test_higgsfield_resolution_rejects_retry_decision_missing_active_fingerprint(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["qa_inputs"]["decision_kind"] = "retry_decision"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")
    decision = _retry_decision(ctx)
    del decision["retry_decision_fingerprint_sha256"]
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (decision, _retry_candidate(ctx), "retry_decision"),
    )

    with pytest.raises(ResolveError, match="retry decision retry_decision_fingerprint_sha256"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_retry_lineage_slot_mismatch(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["qa_inputs"]["decision_kind"] = "retry_decision"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (_retry_decision(ctx, retry_slot_id="wrong-retry-slot"), _retry_candidate(ctx), "retry_decision"),
    )

    with pytest.raises(ResolveError, match="retry decision retry_slot_id .* does not match candidate slot_id"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_missing_caption_seed_for_semantic_disposition(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    monkeypatch.setattr(
        packet_mod.lena_photo_qa_disposition,
        "_validate_decision",
        lambda path: (
            {
                "authority_commit": ctx["artifact"]["authority_commit"],
                "decision_fingerprint_sha256": ctx["artifact"]["decision_fingerprint_sha256"],
                "as_of_date": ctx["date"],
            },
            {
                "candidate_id": ctx["artifact"]["candidate_id"],
                "slot_id": ctx["slot"],
                "lane": ctx["artifact"]["lane"],
                "recipe_id": ctx["artifact"]["recipe_id"],
                "hook_id": ctx["artifact"]["hook_id"],
                "hook_text": ctx["artifact"]["hook_text"],
                "caption_seed": "",
                "prompt_sha256": ctx["artifact"]["prompt_sha256"],
            },
            "selected_candidate",
        ),
    )

    with pytest.raises(ResolveError, match="decision caption_seed must be a non-empty string"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_wrong_reviewer_or_provider_state(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["provider_called"] = False
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match="reviewer/provider state is invalid"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_incomplete_observations(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    del value["qa_checks"]["face_continuity"]
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match="exactly every required QA check key"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_path_escape(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    escaped = tmp_path / "outside-decision.json"
    escaped.write_text("{}", encoding="utf-8")
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["decision_artifact_path"] = str(escaped)
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match="decision artifact path must be repository-contained"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_ambiguous_disposition_bridge(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    second = dict(ctx["artifact"])
    second["image_sha256"] = "c" * 64
    second_path = isolated_roots["asset_review_root"] / ctx["date"] / f"{ctx['slot']}__{'c' * 64}_qa_disposition.json"
    second_path.write_text(json.dumps(second, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match="multiple QA disposition artifacts exist"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_rejects_nonaccepted_disposition_bridge(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["disposition"] = "hard_stop"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    with pytest.raises(ResolveError, match=r"disposition='hard_stop'"):
        resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])


def test_higgsfield_resolution_prefers_unchanged_legacy_qa_over_disposition(
    tmp_path: Path, isolated_roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _bridge_context(tmp_path, isolated_roots, monkeypatch)
    _write_qa_pass(isolated_roots["asset_review_root"], ctx["date"], ctx["slot"])
    value = json.loads(ctx["disposition_path"].read_text(encoding="utf-8"))
    value["disposition"] = "hard_stop"
    ctx["disposition_path"].write_text(json.dumps(value, indent=2), encoding="utf-8")

    resolved = resolve_packet_inputs_higgsfield(ctx["date"], ctx["slot"])

    assert resolved["qa_path"].endswith(f"{ctx['slot']}_qa.json")
    assert resolved["qa_overall"] == "pass"


# 16/17/18. No network call, no publish, no real queue item mutated --
# structural guarantee: this module imports no requests/publisher/
# queue-processing surface (tools/lena_build_publish_packet_v1.py's own
# header docstring states this explicitly), and every test above operates
# purely on tmp_path fixtures, never pipeline/queue/ or any real repo path.
