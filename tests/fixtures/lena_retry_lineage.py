from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from pipeline.identity import lena_higgsfield_identity as identity
from tests.fixtures import lena_pose_provenance as pose_fixture
from tools import lena_record_human_rejection_v1 as record
from tools.strategy import lena_execute_retry_decision_v1 as retry_consumer
from tools.strategy import lena_execute_selected_candidate_v1 as selected_consumer
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector
from tools.strategy import lena_prepare_higgsfield_retry_handoff_v1 as retry_handoff


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _legacy_rejection_sha(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _retry_execution_contract(artifact: dict) -> dict:
    return {
        "schema_version": retry_consumer.RETRY_EXECUTION_CONTRACT_SCHEMA_VERSION,
        "retry_decision_fingerprint_sha256": artifact["retry_decision_fingerprint_sha256"],
        "retry_attempt": artifact["retry_attempt"],
        "retry_cap": artifact["retry_cap"],
        "original_slot_id": artifact["original_slot_id"],
        "retry_slot_id": artifact["retry_slot_id"],
        "original_prompt_sha256": artifact["original_prompt_sha256"],
        "retry_prompt_sha256": artifact["retry_prompt_sha256"],
        "mutation_type": artifact["mutation_type"],
        "correction_scope": artifact["correction_scope"],
        "added_constraint": artifact["prompt_mutation"]["added_constraint"],
        "source_original_decision_fingerprint_sha256": artifact["source_original_decision_fingerprint_sha256"],
        "source_original_manifest_path": artifact["source_original_manifest_path"],
        "source_original_manifest_sha256": artifact["source_original_manifest_sha256"],
        "source_execution_receipt_path": artifact["source_execution_receipt_path"],
        "source_execution_receipt_sha256": artifact["source_execution_receipt_sha256"],
        "source_handoff_artifact_path": artifact["source_handoff_artifact_path"],
        "source_handoff_artifact_sha256": artifact["source_handoff_artifact_sha256"],
        "source_selected_prompt_input_artifact_path": artifact["source_selected_prompt_input_artifact_path"],
        "source_selected_prompt_input_artifact_sha256": artifact["source_selected_prompt_input_artifact_sha256"],
        "source_pose_bound_content_packet_sha256": artifact["source_pose_bound_content_packet_sha256"],
        "pose_provenance": artifact["pose_provenance"],
        "pose_provenance_fingerprint_sha256": artifact["pose_provenance_fingerprint_sha256"],
        "source_original_provider_job_evidence": artifact["source_original_provider_job_evidence"],
        "source_valid_human_rejection_artifact_path": artifact["source_valid_human_rejection_artifact_path"],
        "source_valid_human_rejection_artifact_sha256": artifact["source_valid_human_rejection_artifact_sha256"],
        "source_invalid_retry_plan_artifact_path": artifact["source_invalid_retry_plan_artifact_path"],
        "source_invalid_retry_plan_artifact_sha256": artifact["source_invalid_retry_plan_artifact_sha256"],
        "source_retry_plan_correction_artifact_path": artifact["source_retry_plan_correction_artifact_path"],
        "source_retry_plan_correction_artifact_sha256": artifact["source_retry_plan_correction_artifact_sha256"],
    }


def build_retry_lineage(tmp_path: Path, monkeypatch) -> dict:
    root = tmp_path / "repo"
    output = root / "pipeline" / "asset_review" / "lena"
    retry_output = root / "pipeline" / "strategy" / "lena" / "retry_decisions"
    date = "2026-07-13"
    slot = "lenagate2026071325ca9e1d-pack000-01-photo"
    lane = "night out"
    recipe_id = "hcr_006"
    hook_id = "cbn_004"
    root.mkdir()

    image = root / "image.png"
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "white").save(image)
    image_sha = hashlib.sha256(image.read_bytes()).hexdigest()

    prompt = "Exact synthetic selector prompt bytes."
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    candidate = {
        "candidate_id": f"{slot}::{recipe_id}::{hook_id}",
        "slot_id": slot,
        "lane": lane,
        "activity": "blue-hour street pause outside the restaurant",
        "recipe_id": recipe_id,
        "hook_id": hook_id,
        "hook_text": "I almost turned around.",
        "caption_seed": "The mirror version of me would have stayed home.",
        "pose": "weight_shift_one_hip",
        "pose_body_language_id": "pose_p001",
        "wardrobe_outfit_id": "wc_fixture",
        "visual_style": "fitted_dress",
        "camera_text": "50mm candid vertical",
        "lighting_text": "warm streetlamp spill",
        "prompt_sha256": prompt_sha,
        "exact_proposed_dry_run_command": (
            f"python pipeline/higgsfield_lena_api_executor.py --date {date} --slot-id {slot}"
        ),
    }
    decision_core = {
        "schema_version": selector.SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": date,
        "authority_commit": "a" * 40,
        "input_provenance": [],
        "candidate_status": "selected",
        "final_action": selected_consumer.ACCEPTED_FINAL_ACTION,
        "candidate": candidate,
        "exact_next_allowed_action": candidate["exact_proposed_dry_run_command"],
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    decision = dict(decision_core)
    decision["generated_at_utc"] = "2026-07-13T00:00:00Z"
    decision["decision_fingerprint_sha256"] = hashlib.sha256(
        selector._canonical_bytes(decision_core)
    ).hexdigest()
    decision_path = root / "decision.json"
    _write_json(decision_path, decision)

    pose_binding = pose_fixture.static_pose_provenance(
        candidate_path="decision.json",
        candidate_sha256=hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    )
    source_prompt = pose_fixture.canonical_prompt()
    source_prompt_sha = hashlib.sha256(source_prompt.encode("utf-8")).hexdigest()
    packet_path = root / "source_content_packet.json"
    packet = pose_fixture.authoritatively_bind_packet(
        {
            "recipe_id": "hcr_011",
            "strong_hook_id": "mf_001",
            "generated_date": date,
            "wardrobe_outfit_id": "wc_p020",
            "environment_id": "env_v008",
            "hook_selection_reason": "legacy retry source fixture",
        },
        pose_binding=pose_binding,
    )
    _write_json(packet_path, packet)
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    packet_digest = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    handoff_path = root / "source_handoff.json"
    handoff = {
        "date": date,
        "selected_slot_id": slot,
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_sha256": packet_digest,
        "selected_candidate": {
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_body_language_label": pose_binding["pose_body_language_label"],
        },
        "candidate_selection_binding": {
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_body_language_label": pose_binding["pose_body_language_label"],
            "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        },
        "selected_prompt_input_artifact_path": "source_content_packet.json",
        "selected_prompt_input_artifact_sha256": packet_sha,
        "selected_prompt_input": {
            "artifact_path": "source_content_packet.json",
            "artifact_sha256": packet_sha,
            "prompt_sha256": source_prompt_sha,
            "prompt_text": source_prompt,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": packet_digest,
        },
        "structured_executor_inputs": {
            "selected_prompt_sha256": source_prompt_sha,
            "selected_prompt_text": source_prompt,
            "selected_prompt_input_artifact_sha256": packet_sha,
            "pose_provenance": pose_binding,
            "pose_bound_content_packet_sha256": packet_digest,
        },
        "provider_execution_binding": {
            "content_packet_artifact_path": "source_content_packet.json",
            "content_packet_artifact_sha256": packet_sha,
            "provider_prompt_sha256": source_prompt_sha,
            "pose_bound_content_packet_sha256": packet_digest,
            "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        },
        "binding_linkage": {
            "content_packet_artifact_path": "source_content_packet.json",
            "content_packet_artifact_sha256": packet_sha,
            "pose_body_language_id": pose_binding["pose_body_language_id"],
            "pose_bound_content_packet_sha256": packet_digest,
            "pose_provenance_fingerprint_sha256": pose_binding["pose_provenance_fingerprint_sha256"],
        },
    }
    _write_json(handoff_path, handoff)
    handoff_sha = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
    receipt_path = root / "source_receipt.json"
    receipt = {
        "handoff_artifact_path": "source_handoff.json",
        "handoff_artifact_sha256": handoff_sha,
    }
    _write_json(receipt_path, receipt)

    manifest_path = root / "manifest.json"
    provider_job_id = "job-1"
    manifest = {
        "provider": "higgsfield",
        "date": date,
        "slot_id": slot,
        "lane": lane,
        "prompt_sha256": source_prompt_sha,
        "image_prompt": source_prompt,
        "provider_job_id": provider_job_id,
        "provider_status": "completed",
        "job_type": identity.EXPECTED_JOB_TYPE,
        "custom_reference_id": next(iter(identity.APPROVED_CUSTOM_REFERENCE_IDS)),
        "saved_image_path": str(image.resolve()),
        "pose_body_language_id": candidate["pose_body_language_id"],
        "pose_body_language_label": candidate["pose"],
        "pose_text": "weight shifted onto one hip, stance easy and unforced",
        "pose_provenance": pose_binding,
        "pose_bound_content_packet_artifact_path": "source_content_packet.json",
        "pose_bound_content_packet_artifact_sha256": packet_sha,
        "pose_bound_content_packet_sha256": packet_digest,
        "generation_execution_receipt_path": "source_receipt.json",
        "expression_gaze_id": "exp_fixture",
        "expression_gaze_label": "calm expression",
        "expression_text": "calm expression",
        "expression_safe_fallback_used": False,
        "expression_safe_fallback_reason": None,
        "expression_scene_conflict_terms": [],
        "wardrobe_outfit_id": candidate["wardrobe_outfit_id"],
        "wardrobe_outfit_name": "fixture outfit",
        "wardrobe_silhouette_class": candidate["visual_style"],
        "effective_wardrobe_silhouette_class": candidate["visual_style"],
        "cli_soul_name": identity.EXPECTED_SOUL_NAME,
        "cli_soul_type": identity.EXPECTED_SOUL_TYPE,
        "live_attempt_count": 1,
        "retry_count": 0,
        "image_format_detected": ".png",
    }
    _write_json(manifest_path, manifest)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    publish_packet = root / "pipeline" / "publish_packets" / "lena" / date / f"{slot}.md"
    publish_packet.parent.mkdir(parents=True, exist_ok=True)
    publish_packet.write_text("# packet\n", encoding="utf-8")
    queue_draft = root / "pipeline" / "publish_packets" / "lena" / date / f"{slot}.json"

    disposition_path = output / date / f"{slot}__{image_sha}_qa_disposition.json"
    disposition_artifact = {
        "schema_version": "lena_photo_qa_disposition_v1",
        "influencer_id": "lena",
        "slot_id": slot,
        "image_path": str(image.resolve()),
        "image_sha256": image_sha,
        "decision_artifact_path": str(decision_path.resolve()),
        "decision_fingerprint_sha256": decision["decision_fingerprint_sha256"],
        "prompt_sha256": source_prompt_sha,
        "disposition": "accept",
        "reviewer_type": "bounded_visual_provider",
        "provider_called": True,
        "reason_codes": [],
        "side_effects_performed": [],
        "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
        "generation_provenance": {
            "date": date,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest_sha,
            "provider_job_id": provider_job_id,
            "provider_status": "completed",
        },
    }
    _write_json(disposition_path, disposition_artifact)
    disposition_sha = hashlib.sha256(disposition_path.read_bytes()).hexdigest()

    _write_json(
        queue_draft,
        {
            "post_id": slot,
            "slot_id": slot,
            "media_path": str(image.resolve()),
            "media_type": "photo",
            "platforms": ["instagram"],
            "caption": "<PLACEHOLDER -- operator must choose a final caption from the publish packet before moving this into the live queue>",
            "approved_for_live_publish": False,
            "operator_review_required": True,
            "metadata": {
                "avatar_nickname": "Lena",
                "image_engine": "higgsfield_text2image_soul_v2",
                "image_prompt": prompt,
                "publish_packet_path": str(publish_packet.resolve()),
                "qa_path": str(disposition_path.resolve()),
                "qa_overall": "pass",
                "source_date": date,
                "source_slot_id": slot,
                "generated_by": "tools/lena_build_publish_packet_v1.py",
                "queue_draft_only": True,
            },
        },
    )

    monkeypatch.setattr(record, "ROOT", root)
    monkeypatch.setattr(record.disposition, "disposition_artifact_path", lambda artifact: disposition_path)
    monkeypatch.setattr(record.disposition, "_validate_decision", lambda path: (decision, candidate))
    monkeypatch.setattr(
        record.disposition,
        "_inspect_image",
        lambda path, generated: {"path": str(path), "sha256": image_sha},
    )
    monkeypatch.setattr(record.disposition, "_validate_manifest", lambda path, d, c, i: manifest)

    def synthetic_source(date_str: str, slot_id: str) -> dict:
        if date_str != date or slot_id != slot:
            raise retry_consumer.executor.PromptSourceError(f"synthetic source missing: {date_str} {slot_id}")
        return {
            "resolver": "synthetic_test",
            "slot_prefix": "synthetic",
            "pack_count": 1,
            "image": {
                "slot_id": slot,
                "lane": lane,
                "image_prompt": source_prompt,
                "prompt_sha256": source_prompt_sha,
                "pose_body_language_id": candidate["pose_body_language_id"],
                "pose_body_language_label": candidate["pose"],
                "pose_provenance": pose_binding,
                "pose_bound_content_packet_artifact_path": "source_content_packet.json",
                "pose_bound_content_packet_artifact_sha256": packet_sha,
                "pose_bound_content_packet_sha256": packet_digest,
                "wardrobe_outfit_id": candidate["wardrobe_outfit_id"],
                "effective_wardrobe_silhouette_class": candidate["visual_style"],
                "camera_text": candidate["camera_text"],
                "lighting_text": candidate["lighting_text"],
            },
        }

    monkeypatch.setattr(retry_consumer, "ROOT", root)
    monkeypatch.setattr(retry_handoff, "ROOT", root)
    monkeypatch.setattr(
        retry_consumer.selected_consumer,
        "validate_selected_candidate_issuance",
        lambda artifact, root=None: {
            "candidate": artifact["candidate"],
            "stored_core": selected_consumer._decision_core(artifact),
            "recomputed_fingerprint_sha256": artifact["decision_fingerprint_sha256"],
            "fresh_fingerprint_sha256": artifact["decision_fingerprint_sha256"],
            "executor_validation": {"ok": True},
        },
    )
    monkeypatch.setattr(
        retry_consumer.pose_provenance,
        "build_candidate_pose_provenance",
        lambda path, root=None: pose_binding,
    )
    monkeypatch.setattr(
        retry_consumer.generation_approval,
        "inspect_handoff_artifact",
        lambda path: {
            "handoff_repo_path": "source_handoff.json",
            "handoff_sha256": handoff_sha,
            "report": handoff,
            "date": date,
            "slot_id": slot,
            "prompt_sha256": source_prompt_sha,
            "custom_reference_id": next(iter(identity.APPROVED_CUSTOM_REFERENCE_IDS)),
        },
    )
    monkeypatch.setattr(
        retry_handoff,
        "_validate_execution_receipt",
        lambda path, facts: (receipt, image, manifest, manifest_path, receipt_path, image_sha),
    )
    monkeypatch.setattr(retry_consumer.executor, "resolve_prompt_source", synthetic_source)
    monkeypatch.setattr(
        retry_consumer.executor,
        "_validate_handoff_packet",
        lambda path: (handoff, synthetic_source(date, slot), {"ok": True}, {}),
    )
    monkeypatch.setattr(
        retry_consumer.executor,
        "validate_candidate",
        lambda source, expected_prompt_path: {
            "ok": True,
            "all_reasons": [],
            "prompt_matches_expected": True,
            "hard_exclude_reasons": [],
        },
    )

    rejection, retry_plan, rejection_path, retry_path = record.build_rejection_and_retry_plan(
        date_str=date,
        slot_id=slot,
        image_sha=image_sha,
        disposition_path=disposition_path,
        disposition_sha=disposition_sha,
        publish_packet_path=publish_packet,
        queue_draft_path=queue_draft,
        reason=record.EXACT_REASON,
        output_root=output,
    )
    record._write_pair(rejection, retry_plan, rejection_path, retry_path)

    invalid_retry = json.loads(retry_path.read_text(encoding="utf-8"))
    invalid_retry["human_rejection_artifact_sha256"] = _legacy_rejection_sha(rejection)
    _write_json(retry_path, invalid_retry)

    correction, correction_path = record.build_retry_plan_sha_correction(
        rejection_artifact_path=rejection_path,
        invalid_retry_plan_path=retry_path,
    )
    record._write_json_artifact(correction_path, correction)

    written = retry_consumer.evaluate_retry_correction(
        correction_artifact_path=correction_path,
        output_root=retry_output,
        write_decision=True,
    )
    retry_decision_path = Path(written["retry_decision_artifact_path"])
    retry_decision = json.loads(retry_decision_path.read_text(encoding="utf-8"))
    retry_image_sha = image_sha

    retry_manifest = dict(manifest)
    retry_manifest.update(
        {
            "slot_id": retry_decision["retry_slot_id"],
            "prompt_sha256": retry_decision["retry_prompt_sha256"],
            "image_prompt": retry_decision["retry_prompt_text"],
            "retry_count": 0,
            "retry_execution_contract": _retry_execution_contract(retry_decision),
        }
    )
    retry_manifest_path = root / "retry_manifest.json"
    _write_json(retry_manifest_path, retry_manifest)

    reference_path = root / "reference.png"
    Image.new("RGB", (64, 64), "gray").save(reference_path)
    reference_authority_artifact = root / "reference_authority.json"
    reference_authority_artifact.write_text("{}", encoding="utf-8")
    model_authority_artifact = root / "model_authority.json"
    model_authority_artifact.write_text("{}", encoding="utf-8")
    identity_evidence_path = root / "retry_identity_verification.json"
    _write_json(
        identity_evidence_path,
        {
            "schema_version": identity.SCHEMA_VERSION,
            "verified_at_utc": "2026-07-13T00:01:00Z",
            "provider": "higgsfield",
            "date": date,
            "slot_id": retry_decision["retry_slot_id"],
            "provider_job_id": provider_job_id,
            "provider_job_status": "completed",
            "job_type": identity.EXPECTED_JOB_TYPE,
            "custom_reference_id": manifest["custom_reference_id"],
            "soul_name": identity.EXPECTED_SOUL_NAME,
            "soul_type": identity.EXPECTED_SOUL_TYPE,
            "prompt_sha256": retry_decision["retry_prompt_sha256"],
            "width": identity.EXPECTED_WIDTH,
            "height": identity.EXPECTED_HEIGHT,
            "local_image_path": str(image.resolve()),
            "local_image_sha256": retry_image_sha,
            "local_image_sha256_provenance": "fixture local hash",
            "verification_result": "pass",
            "checks_passed": ["fixture"],
        },
    )

    return {
        "root": root,
        "date": date,
        "slot": slot,
        "lane": lane,
        "recipe_id": recipe_id,
        "hook_id": hook_id,
        "image_path": image,
        "image_sha": image_sha,
        "decision_path": decision_path,
        "manifest_path": manifest_path,
        "source_handoff_path": handoff_path,
        "source_receipt_path": receipt_path,
        "source_packet_path": packet_path,
        "retry_manifest_path": retry_manifest_path,
        "retry_decision_path": retry_decision_path,
        "retry_decision": retry_decision,
        "correction_path": correction_path,
        "rejection_path": rejection_path,
        "retry_plan_path": retry_path,
        "identity_evidence_path": identity_evidence_path,
        "reference_path": reference_path,
        "reference_authority_artifact": reference_authority_artifact,
        "reference_authority_sha256": "1" * 64,
        "model_authority_artifact": model_authority_artifact,
        "model_authority_sha256": "2" * 64,
        "retry_image_sha": retry_image_sha,
    }
