from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from pipeline import higgsfield_lena_api_executor as executor
from tools import lena_higgsfield_generation_approval_v1 as approval_mod
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_mod


DATE = "2026-07-14"
ORIGINAL_SLOT = "higgsfield-20260714-hcr_011-photo"
RETRY_SLOT = "higgsfield-20260714-hcr_011-retry01-photo"
CUSTOM_REFERENCE_ID = "90a293d7-f3af-4377-8751-3304a27b6f31"
ORIGINAL_PROMPT = (
    "[Subject]: Lena (Magdalena Delapi). Identity is fixed: preserve her approved adult slim-thick hourglass body and face. "
    "Do not reinterpret her as a different person. Do not slim her into petite, narrow-hipped proportions. Keep full natural "
    "lifted bust, defined waist, and wide hips. Hair stays reference-true warm medium-brown with visible honey/caramel highlights "
    "and lighter face-framing pieces. Wardrobe and accessories: Cherry red fitted square-neck mini dress visible from neckline "
    "through upper torso only. Gold hoop earrings. [Action]: Waist-up or chest-up only. Lena stands near the mirror at a 20-30 "
    "degree angle toward the mirror or window. Mirror-selfie phone visibility is acceptable if the phone sits low enough to keep "
    "her face readable. [Environment]: Home getting-ready corner or bedroom vanity area. Mirror edge visible, not full mirror "
    "dominance. Dresser or small vanity surface, a few products, clothes draped on a chair, shoes near the mirror, warm apartment "
    "light, and ordinary home clutter kept tasteful. Lived-in and elevated, never hotel-like. [Cinematography]: 85mm portrait "
    "compression or 50mm close lifestyle portrait, waist-up framing, real phone-camera skin detail, shallow depth of field, "
    "blue-hour ambient mixed with warm lamp fill, candid apartment realism, non-studio. [Lighting/Style]: Face-first available "
    "light only. Cool blue-hour window light shapes one side of the face while an ordinary warm bedside lamp lifts the shadow side "
    "just enough to keep pores, under-eye texture, and lip texture alive. No beauty-dish polish, no ring light, no glam campaign "
    "finish. [Technical]: Photorealistic high-resolution image with visible pores, fine facial texture, natural under-eye retention, "
    "imperfect lip texture, tiny tone variation, stray hair strands, realistic catchlights, and scene-true shadow falloff. Face "
    "detail comes from the Lena character element; keep the facial surface faithful to the approved references. Hands remain "
    "anatomically correct with five fingers, believable knuckles, clean thumb placement, and relaxed wrists."
)
PROMPT_SHA = hashlib.sha256(ORIGINAL_PROMPT.encode("utf-8")).hexdigest()
SELECTED_CANDIDATE_REPO_PATH = Path(
    f"pipeline/strategy/lena/pre_generation_candidates/{DATE}/lena_pre_generation_candidate_selected.json"
)


def _selected_candidate_payload() -> dict:
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "candidate_status": "selected",
        "generated_at_utc": "2026-07-14T12:00:00+00:00",
        "candidate": {
            "candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
            "slot_id": ORIGINAL_SLOT,
            "recipe_id": "hcr_011",
            "prompt_sha256": PROMPT_SHA,
        },
    }


def _selected_candidate_sha() -> str:
    return hashlib.sha256(
        json.dumps(_selected_candidate_payload(), indent=2).replace("\n", os.linesep).encode("utf-8")
    ).hexdigest()


def _patch_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        approval_mod,
        "DEFAULT_APPROVAL_ROOT",
        tmp_path / "pipeline" / "approvals" / "lena" / "generation",
    )
    monkeypatch.setattr(retry_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        retry_mod,
        "DEFAULT_OUTPUT_ROOT",
        tmp_path / "pipeline" / "strategy" / "lena" / "retry_handoffs",
    )


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _seed_bound_retry_source(tmp_path: Path) -> dict[str, Path]:
    handoff_repo_path = Path("pipeline/strategy/lena/next_actions") / DATE / f"lena_next_live_image_handoff_{DATE}.json"
    packet_repo_path = Path("pipeline/strategy/lena/content_packets") / DATE / f"lena_content_packet_dryrun_{DATE}_hcr_011.json"
    selected_candidate_repo_path = SELECTED_CANDIDATE_REPO_PATH
    handoff_path = tmp_path / handoff_repo_path
    packet_path = tmp_path / packet_repo_path
    selected_candidate_path = tmp_path / selected_candidate_repo_path
    packet_report = {
        "report_type": "lena_content_packet_dryrun",
        "generated_date": DATE,
        "recipe_id": "hcr_011",
        "compact_provider_prompt_preview": ORIGINAL_PROMPT,
        "compact_provider_prompt_sha256": PROMPT_SHA,
        "compact_provider_prompt_budget": 2499,
        "provider_prompt_contract": {
            "provider_route": "higgsfield_forward_no_live",
            "live_authority": False,
        },
    }
    _write_json(packet_path, packet_report)
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    selected_candidate_path.parent.mkdir(parents=True, exist_ok=True)
    selected_candidate_path.write_text(json.dumps(_selected_candidate_payload(), indent=2) + "\n", encoding="utf-8")
    selected_candidate_sha = hashlib.sha256(selected_candidate_path.read_bytes()).hexdigest()
    handoff_report = {
        "report_type": "lena_next_live_image_handoff",
        "schema_version": "v1",
        "created_at": "2026-07-15T05:00:00+00:00",
        "execution_owner": "claude",
        "provider": "higgsfield",
        "executor_type": "higgsfield_cli",
        "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
        "packet_state": "packet_valid_for_claude_review",
        "dry_run_executor_contract_state": "ready",
        "live_execution_state": "blocked",
        "live_execution_authorized": False,
        "generation_approval_required": True,
        "manual_operator_approval_required": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "publish_authorized": False,
        "manual_publish_review_required": True,
        "date": DATE,
        "selected_slot_id": ORIGINAL_SLOT,
        "selected_recipe_id": "hcr_011",
        "expected_handoff_artifact_path": handoff_repo_path.as_posix(),
        "source_selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
        "source_selected_candidate_artifact_sha256": selected_candidate_sha,
        "selected_candidate": {
            "artifact_path": selected_candidate_repo_path.as_posix(),
            "artifact_sha256": selected_candidate_sha,
            "candidate_id": f"{ORIGINAL_SLOT}::hcr_011::cbn_004",
            "slot_id": ORIGINAL_SLOT,
            "recipe_id": "hcr_011",
            "prompt_sha256": PROMPT_SHA,
            "schema_version": "lena_pre_generation_candidate_gate_v1",
            "candidate_status": "selected",
        },
        "selected_prompt_input_artifact_path": packet_repo_path.as_posix(),
        "selected_prompt_input_artifact_sha256": packet_sha,
        "selected_prompt_input": {
            "prompt_sha256": PROMPT_SHA,
            "prompt_text": ORIGINAL_PROMPT,
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
        },
        "structured_executor_inputs": {
            "provider": "higgsfield",
            "executor_type": "higgsfield_cli",
            "repo_executor_path": "pipeline/higgsfield_lena_api_executor.py",
            "model": "text2image_soul_v2",
            "aspect_ratio": "9:16",
            "negative_prompt_enabled": False,
            "live_execution_authorized": False,
            "date": DATE,
            "slot_id": ORIGINAL_SLOT,
            "handoff_artifact_path": handoff_repo_path.as_posix(),
            "soul_metadata": {
                "name": "Lena",
                "type": "Soul 2.0",
                "custom_reference_id": CUSTOM_REFERENCE_ID,
                "identity_is_prompt_instruction": False,
            },
            "selected_prompt_sha256": PROMPT_SHA,
            "selected_prompt_text": ORIGINAL_PROMPT,
            "selected_candidate_artifact_path": selected_candidate_repo_path.as_posix(),
            "selected_candidate_artifact_sha256": selected_candidate_sha,
        },
    }
    _write_json(handoff_path, handoff_report)
    handoff_sha = hashlib.sha256(handoff_path.read_bytes()).hexdigest()

    image_path = tmp_path / "pipeline" / "higgsfield_library" / "lena" / DATE / f"{ORIGINAL_SLOT}_seed.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nretry-proof-image")

    manifest_repo_path = Path("pipeline/higgsfield_debug") / DATE / ORIGINAL_SLOT / "result_manifest.json"
    manifest_path = tmp_path / manifest_repo_path
    manifest_report = {
        "provider": "higgsfield",
        "slot_id": ORIGINAL_SLOT,
        "prompt_sha256": PROMPT_SHA,
        "saved_image_path": str(image_path),
        "provider_job_id": "job-123",
        "provider_status": "completed",
    }
    _write_json(manifest_path, manifest_report)

    receipt_repo_path = Path("pipeline/approvals/lena/generation") / DATE / f"{ORIGINAL_SLOT}_higgsfield_generation_execution_receipt.json"
    receipt_path = tmp_path / receipt_repo_path
    receipt_report = {
        "report_type": "lena_higgsfield_generation_execution_receipt",
        "schema_version": "v1",
        "receipt_type": "higgsfield_single_generation_execution_receipt",
        "handoff_artifact_path": handoff_repo_path.as_posix(),
        "handoff_artifact_sha256": handoff_sha,
        "date": DATE,
        "slot_id": ORIGINAL_SLOT,
        "prompt_sha256": PROMPT_SHA,
        "outcome": "success",
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "provider_submission_may_have_occurred": True,
        "subprocess_start_attempted": True,
        "output_path": str(image_path),
        "actual_manifest_path": manifest_repo_path.as_posix(),
        "provider": "Higgsfield",
        "executor": "Higgsfield CLI repo adapter",
        "model": "text2image_soul_v2",
        "aspect_ratio": "9:16",
        "custom_reference_id": CUSTOM_REFERENCE_ID,
    }
    _write_json(receipt_path, receipt_report)
    return {
        "handoff_path": handoff_path,
        "receipt_path": receipt_path,
        "packet_path": packet_path,
        "manifest_path": manifest_path,
        "image_path": image_path,
    }


def test_build_and_validate_retry_handoff_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)

    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=True,
    )
    artifact_path = Path(report["retry_handoff_artifact_path"])
    assert report["state"] == "retry_handoff_written"
    assert artifact_path.is_file()
    assert report["original_slot_id"] == ORIGINAL_SLOT
    assert report["retry_slot_id"] == RETRY_SLOT
    assert report["retry_prompt_headroom_status"] == "ready"

    artifact = retry_mod.validate_retry_handoff_artifact(artifact_path)
    prompt = artifact["retry_prompt_text"]
    assert artifact["retry_prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert "Mirror-selfie phone visibility is acceptable" not in prompt
    assert "No foreground phone, visible device screens, or direct posed full-torso portrait." in prompt
    assert "Chest-up or waist-up only." in prompt
    assert "hips, thighs, and the dress hemline never appear" in prompt
    assert "actively checking or adjusting one gold hoop earring" in prompt
    assert "must read as a real getting-ready vanity moment" in prompt
    assert "No fake freckles or poreless/plastic skin." in prompt
    assert "slightly fuller is okay, not a hard gate" in prompt
    assert len(prompt) <= 2429
    assert artifact["retry_prompt_budget"] == 2499
    assert artifact["retry_prompt_length"] == len(prompt)
    assert artifact["retry_prompt_headroom"] == 2499 - len(prompt)
    assert artifact["retry_prompt_headroom"] >= 70
    assert artifact["retry_prompt_headroom_policy"] == {"hard_block_below": 30, "warning_below": 70}
    assert artifact["retry_prompt_headroom_status"] == "ready"


def test_retry_handoff_fails_closed_on_receipt_prompt_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["prompt_sha256"] = "0" * 64
    seeded["receipt_path"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
        )
    assert excinfo.value.code == "receipt_prompt_sha_mismatch"


def test_retry_handoff_warns_but_allows_when_headroom_is_under_70(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    packet = json.loads(seeded["packet_path"].read_text(encoding="utf-8"))
    packet["compact_provider_prompt_budget"] = len(retry_mod._replace_sections(ORIGINAL_PROMPT)) + 50
    seeded["packet_path"].write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    handoff = json.loads(seeded["handoff_path"].read_text(encoding="utf-8"))
    handoff["selected_prompt_input_artifact_sha256"] = hashlib.sha256(seeded["packet_path"].read_bytes()).hexdigest()
    seeded["handoff_path"].write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["handoff_artifact_sha256"] = hashlib.sha256(seeded["handoff_path"].read_bytes()).hexdigest()
    seeded["receipt_path"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=False,
    )
    assert report["retry_prompt_headroom"] == 50
    assert report["retry_prompt_headroom_status"] == "warning"
    assert report["retry_prompt_headroom_policy"] == {"hard_block_below": 30, "warning_below": 70}


def test_retry_handoff_fails_closed_when_headroom_is_under_30(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    packet = json.loads(seeded["packet_path"].read_text(encoding="utf-8"))
    packet["compact_provider_prompt_budget"] = len(retry_mod._replace_sections(ORIGINAL_PROMPT)) + 29
    seeded["packet_path"].write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    handoff = json.loads(seeded["handoff_path"].read_text(encoding="utf-8"))
    handoff["selected_prompt_input_artifact_sha256"] = hashlib.sha256(seeded["packet_path"].read_bytes()).hexdigest()
    seeded["handoff_path"].write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    receipt = json.loads(seeded["receipt_path"].read_text(encoding="utf-8"))
    receipt["handoff_artifact_sha256"] = hashlib.sha256(seeded["handoff_path"].read_bytes()).hexdigest()
    seeded["receipt_path"].write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(retry_mod.RetryHandoffError) as excinfo:
        retry_mod.build_retry_handoff(
            handoff_artifact=seeded["handoff_path"],
            execution_receipt=seeded["receipt_path"],
            output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        )
    assert excinfo.value.code == "retry_prompt_headroom_too_low"


def test_executor_accepts_new_retry_handoff_artifact_in_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_roots(tmp_path, monkeypatch)
    seeded = _seed_bound_retry_source(tmp_path)
    report = retry_mod.evaluate_retry_handoff(
        handoff_artifact=seeded["handoff_path"],
        execution_receipt=seeded["receipt_path"],
        output_root=retry_mod.DEFAULT_OUTPUT_ROOT,
        write_artifact=True,
    )
    artifact_path = Path(report["retry_handoff_artifact_path"])

    def fake_validate_handoff_packet(path: Path):
        source = {
            "resolver": "content_packet_dryrun",
            "slot_prefix": "hcr_011",
            "pack_count": 1,
            "pack_variety_warnings": [],
            "image": {
                "slot_id": ORIGINAL_SLOT,
                "lane": "fit_check_mirror_getting_ready",
                "image_prompt": ORIGINAL_PROMPT,
            },
        }
        return ({}, source, {}, {"ok": True, "prompt_matches_expected": None, "hard_exclude_reasons": [], "all_reasons": []})

    monkeypatch.setattr(executor, "_validate_handoff_packet", fake_validate_handoff_packet)
    monkeypatch.setattr(
        executor,
        "validate_candidate",
        lambda source, expected: {"ok": True, "prompt_matches_expected": None, "hard_exclude_reasons": [], "all_reasons": []},
    )
    monkeypatch.setattr(sys, "argv", ["executor", "--retry-decision-artifact", str(artifact_path)])
    assert executor.main() == 0
    stdout = capsys.readouterr().out
    assert "=== Higgsfield Lena executor -- DRY RUN (no provider/network call) ===" in stdout
    assert f"slot_id                 : {RETRY_SLOT}" in stdout
    assert "validation ok           : True" in stdout
    assert "no subprocess call, no network call, no file written" in stdout
