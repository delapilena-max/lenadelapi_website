from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools import lena_record_human_rejection_v1 as record


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _legacy_rejection_sha(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


@pytest.fixture
def bound_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    root = tmp_path / "repo"
    output = root / "pipeline" / "asset_review" / "lena"
    date = "2026-07-13"
    slot = "slot-photo"
    root.mkdir()
    image = root / "image.png"
    image.write_bytes(b"bound-image")
    image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
    decision_path = root / "decision.json"
    decision = {"as_of_date": date, "decision_fingerprint_sha256": "d" * 64}
    _write_json(decision_path, decision)
    manifest_path = root / "manifest.json"
    manifest = {
        "provider": "higgsfield", "date": date, "slot_id": slot,
        "prompt_sha256": "p" * 64, "saved_image_path": str(image.resolve()),
        "provider_job_id": "job-1", "provider_status": "completed", "job_type": "text2image_soul_v2",
    }
    _write_json(manifest_path, manifest)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    publish_packet = root / "pipeline" / "publish_packets" / "lena" / date / f"{slot}.md"
    publish_packet.parent.mkdir(parents=True, exist_ok=True)
    publish_packet.write_text("# packet\n", encoding="utf-8")
    disposition_path = output / date / f"{slot}__{image_sha}_qa_disposition.json"
    source = {
        "schema_version": "lena_photo_qa_disposition_v1", "influencer_id": "lena",
        "slot_id": slot, "image_path": str(image.resolve()), "image_sha256": image_sha,
        "decision_artifact_path": str(decision_path.resolve()),
        "decision_fingerprint_sha256": "d" * 64, "prompt_sha256": "p" * 64,
        "disposition": "accept", "reviewer_type": "bounded_visual_provider", "provider_called": True,
        "reason_codes": [], "side_effects_performed": [],
        "exact_next_allowed_action": "existing_downstream_qa_and_human_review_gates_only",
        "generation_provenance": {
            "date": date, "manifest_path": str(manifest_path.resolve()), "manifest_sha256": manifest_sha,
            "provider_job_id": "job-1", "provider_status": "completed",
        },
    }
    _write_json(disposition_path, source)
    disposition_sha = hashlib.sha256(disposition_path.read_bytes()).hexdigest()
    queue_draft = root / "pipeline" / "publish_packets" / "lena" / date / f"{slot}.json"
    _write_json(queue_draft, {
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
            "image_prompt": "prompt",
            "publish_packet_path": str(publish_packet.resolve()),
            "qa_path": str(disposition_path.resolve()),
            "qa_overall": "pass",
            "source_date": date,
            "source_slot_id": slot,
            "generated_by": "tools/lena_build_publish_packet_v1.py",
            "queue_draft_only": True,
        },
    })
    monkeypatch.setattr(record, "ROOT", root)
    monkeypatch.setattr(record.disposition, "disposition_artifact_path", lambda artifact: disposition_path)
    monkeypatch.setattr(record.disposition, "_validate_decision", lambda path: (decision, {"slot_id": slot}))
    monkeypatch.setattr(record.disposition, "_inspect_image", lambda path, generated: {"path": str(path), "sha256": image_sha})
    monkeypatch.setattr(record.disposition, "_validate_manifest", lambda path, d, c, i: manifest)
    return {
        "root": root, "output": output, "date": date, "slot": slot, "image": image,
        "image_sha": image_sha, "decision": decision_path, "manifest": manifest_path,
        "publish_packet": publish_packet, "queue_draft": queue_draft,
        "disposition": disposition_path, "source": source,
        "disposition_sha": disposition_sha,
    }


def _build(ctx: dict):
    return record.build_rejection_and_retry_plan(
        date_str=ctx["date"], slot_id=ctx["slot"], image_sha=ctx["image_sha"],
        disposition_path=ctx["disposition"], disposition_sha=ctx["disposition_sha"],
        publish_packet_path=ctx["publish_packet"], queue_draft_path=ctx["queue_draft"],
        reason=record.EXACT_REASON, output_root=ctx["output"],
    )


def test_valid_rejection_and_retry_plan_are_bound_and_plan_only(bound_source: dict) -> None:
    rejection, retry, rejection_path, retry_path = _build(bound_source)
    assert rejection["operator_reason"] == record.EXACT_REASON
    assert rejection["classification"] == "identity_related_human_rejection"
    assert rejection["retry_attempt"] == rejection["retry_cap"] == 1
    assert rejection["publish_packet_path"] == str(bound_source["publish_packet"].resolve())
    assert rejection["publish_packet_sha256"] == hashlib.sha256(bound_source["publish_packet"].read_bytes()).hexdigest()
    assert rejection["queue_draft_path"] == str(bound_source["queue_draft"].resolve())
    assert rejection["queue_draft_sha256"] == hashlib.sha256(bound_source["queue_draft"].read_bytes()).hexdigest()
    assert retry["next_attempt_instruction"] == record.NEXT_ATTEMPT
    assert retry["action"] == "plan_only_no_provider_call"
    assert retry["original_provider_job_evidence"]["provider_job_id"] == "job-1"
    assert retry["original_publish_packet_path"] == str(bound_source["publish_packet"].resolve())
    assert retry["original_queue_draft_path"] == str(bound_source["queue_draft"].resolve())
    assert retry["human_rejection_artifact_path"] == str(rejection_path.resolve())
    assert not rejection_path.exists()
    assert not retry_path.exists()


def test_hair_crown_rejection_accepts_only_allowlisted_blocked_provenance(bound_source: dict) -> None:
    source = copy.deepcopy(bound_source["source"])
    source["disposition"] = "blocked"
    source["reviewer_type"] = "local_validation_only"
    source["provider_called"] = False
    source["reason_codes"] = ["human_visual_review_required"]
    source["exact_next_allowed_action"] = "human_visual_review_required"
    source["hard_stop_reason"] = "generation_manifest_defect"
    source["qa_inputs"] = {
        "missing_immutable_provenance": [
            "expression_gaze_id",
            "expression_gaze_label",
            "expression_text",
        ]
    }
    _write_json(bound_source["disposition"], source)
    bound_source["disposition_sha"] = hashlib.sha256(bound_source["disposition"].read_bytes()).hexdigest()

    rejection, retry, _, _ = record.build_rejection_and_retry_plan(
        date_str=bound_source["date"],
        slot_id=bound_source["slot"],
        image_sha=bound_source["image_sha"],
        disposition_path=bound_source["disposition"],
        disposition_sha=bound_source["disposition_sha"],
        publish_packet_path=bound_source["publish_packet"],
        queue_draft_path=bound_source["queue_draft"],
        reason=record.CORRECTION_CONTRACTS[record.HAIR_CROWN_REASON_CODE]["operator_reason"],
        reason_code=record.HAIR_CROWN_REASON_CODE,
        output_root=bound_source["output"],
    )

    assert rejection["reason_code"] == "hair_crown_forelock_artifact"
    assert rejection["mutation_type"] == "correct_hair_crown_forelock"
    assert rejection["correction_scope"] == "hair_only"
    assert rejection["deterministic_qa_status"] == "blocked"
    assert rejection["deterministic_qa_blocker"] == "generation_manifest_defect"
    assert retry["missing_immutable_provenance"] == [
        "expression_gaze_id",
        "expression_gaze_label",
        "expression_text",
    ]


def test_unknown_hair_reason_fails_closed(bound_source: dict) -> None:
    with pytest.raises(record.RejectionError, match="unknown rejection reason code"):
        record.build_rejection_and_retry_plan(
            date_str=bound_source["date"],
            slot_id=bound_source["slot"],
            image_sha=bound_source["image_sha"],
            disposition_path=bound_source["disposition"],
            disposition_sha=bound_source["disposition_sha"],
            publish_packet_path=bound_source["publish_packet"],
            queue_draft_path=bound_source["queue_draft"],
            reason="Hair crown contains an unwanted raised forelock or vertical tuft",
            reason_code="freeform_hair_fix",
            output_root=bound_source["output"],
        )


def test_duplicate_rejection_collision_fails_closed(bound_source: dict) -> None:
    rejection, _, rejection_path, _ = _build(bound_source)
    _write_json(rejection_path, rejection)
    with pytest.raises(record.RejectionError, match="already exists"):
        _build(bound_source)


def test_bad_image_sha_fails_closed(bound_source: dict) -> None:
    bound_source["image_sha"] = "a" * 64
    value = copy.deepcopy(bound_source["source"])
    value["image_sha256"] = bound_source["image_sha"]
    _write_json(bound_source["disposition"], value)
    bound_source["disposition_sha"] = hashlib.sha256(bound_source["disposition"].read_bytes()).hexdigest()
    with pytest.raises(record.RejectionError, match="image SHA-256"):
        _build(bound_source)


def test_mismatched_disposition_path_fails_closed(bound_source: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record.disposition, "disposition_artifact_path", lambda artifact: bound_source["root"] / "other.json")
    with pytest.raises(record.RejectionError, match="disposition path"):
        _build(bound_source)


def test_mismatched_disposition_sha_fails_closed(bound_source: dict) -> None:
    bound_source["disposition_sha"] = "b" * 64
    with pytest.raises(record.RejectionError, match="disposition SHA-256"):
        _build(bound_source)


def test_mismatched_queue_draft_publish_packet_binding_fails_closed(bound_source: dict) -> None:
    queue_draft = json.loads(bound_source["queue_draft"].read_text(encoding="utf-8"))
    queue_draft["metadata"]["publish_packet_path"] = str((bound_source["root"] / "other.md").resolve())
    _write_json(bound_source["queue_draft"], queue_draft)
    with pytest.raises(record.RejectionError, match="metadata.publish_packet_path"):
        _build(bound_source)


def test_nonmatching_queue_draft_image_sha_fails_closed(bound_source: dict) -> None:
    queue_draft = json.loads(bound_source["queue_draft"].read_text(encoding="utf-8"))
    other_image = bound_source["root"] / "other.png"
    other_image.write_bytes(b"other-bytes")
    queue_draft["media_path"] = str(other_image.resolve())
    _write_json(bound_source["queue_draft"], queue_draft)
    with pytest.raises(record.RejectionError, match="queue draft media_path"):
        _build(bound_source)


def test_retry_cap_exceeded_for_same_decision_lineage(bound_source: dict) -> None:
    prior = bound_source["output"] / "2026-07-12" / f"{bound_source['slot']}__{'f' * 64}_human_rejection.json"
    _write_json(prior, {
        "schema_version": record.SCHEMA_VERSION, "slot_id": bound_source["slot"],
        "decision_fingerprint_sha256": "d" * 64,
    })
    with pytest.raises(record.RejectionError, match="retry cap exceeded"):
        _build(bound_source)


def test_writing_does_not_modify_existing_evidence(bound_source: dict) -> None:
    protected = [
        bound_source["image"], bound_source["decision"], bound_source["manifest"],
        bound_source["disposition"], bound_source["publish_packet"], bound_source["queue_draft"],
    ]
    before = {path: path.read_bytes() for path in protected}
    rejection, retry, rejection_path, retry_path = _build(bound_source)
    record._write_pair(rejection, retry, rejection_path, retry_path)
    assert rejection_path.is_file() and retry_path.is_file()
    assert {path: path.read_bytes() for path in protected} == before


def test_written_retry_plan_embeds_exact_written_rejection_sha_with_lf_bytes(bound_source: dict) -> None:
    rejection, retry, rejection_path, retry_path = _build(bound_source)
    record._write_pair(rejection, retry, rejection_path, retry_path)

    rejection_bytes = rejection_path.read_bytes()
    written_retry = json.loads(retry_path.read_text(encoding="utf-8"))

    assert b"\r\n" not in rejection_bytes
    assert written_retry["human_rejection_artifact_sha256"] == hashlib.sha256(rejection_bytes).hexdigest()


def test_retry_plan_sha_mismatch_recovery_builds_single_correction_artifact(bound_source: dict) -> None:
    rejection, retry, rejection_path, retry_path = _build(bound_source)
    record._write_pair(rejection, retry, rejection_path, retry_path)

    invalid_retry = json.loads(retry_path.read_text(encoding="utf-8"))
    invalid_retry["human_rejection_artifact_sha256"] = _legacy_rejection_sha(rejection)
    _write_json(retry_path, invalid_retry)

    correction, correction_path = record.build_retry_plan_sha_correction(
        rejection_artifact_path=rejection_path,
        invalid_retry_plan_path=retry_path,
    )

    assert correction["schema_version"] == record.RETRY_CORRECTION_SCHEMA_VERSION
    assert correction["valid_human_rejection_artifact_path"] == str(rejection_path.resolve())
    assert correction["valid_human_rejection_artifact_sha256"] == hashlib.sha256(rejection_path.read_bytes()).hexdigest()
    assert correction["invalid_retry_plan_artifact_path"] == str(retry_path.resolve())
    assert correction["invalid_retry_plan_artifact_sha256"] == hashlib.sha256(retry_path.read_bytes()).hexdigest()
    assert correction["invalid_retry_plan_embedded_rejection_sha256"] == _legacy_rejection_sha(rejection)
    assert correction["supersedes_invalid_retry_plan_for_execution_only"] is True
    assert correction["retry_attempt"] == correction["retry_cap"] == 1
    assert correction["action"] == "correction_record_only_no_provider_call"
    assert correction_path == record.retry_plan_correction_artifact_path(
        bound_source["date"], bound_source["slot"], bound_source["image_sha"], bound_source["output"]
    )
    assert not correction_path.exists()

    record._write_json_artifact(correction_path, correction)
    with pytest.raises(record.RejectionError, match="already exists"):
        record.build_retry_plan_sha_correction(
            rejection_artifact_path=rejection_path,
            invalid_retry_plan_path=retry_path,
        )


def test_retry_plan_sha_mismatch_recovery_fails_closed_on_other_retry_defects(bound_source: dict) -> None:
    rejection, retry, rejection_path, retry_path = _build(bound_source)
    record._write_pair(rejection, retry, rejection_path, retry_path)

    invalid_retry = json.loads(retry_path.read_text(encoding="utf-8"))
    invalid_retry["human_rejection_artifact_sha256"] = _legacy_rejection_sha(rejection)
    invalid_retry["action"] = "queue_now"
    _write_json(retry_path, invalid_retry)

    with pytest.raises(record.RejectionError, match="only allowed for the demonstrated rejection-file SHA mismatch"):
        record.build_retry_plan_sha_correction(
            rejection_artifact_path=rejection_path,
            invalid_retry_plan_path=retry_path,
        )
