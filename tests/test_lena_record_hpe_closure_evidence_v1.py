from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_closure_evidence_v1 as closure_evidence
from tools import lena_record_hpe_closure_evidence_v1 as record


def _tiny_png(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.write_bytes(png_bytes)
    return hashlib.sha256(png_bytes).hexdigest()


def _write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_record_main(payload_path: Path, output_root: Path, kind: str) -> dict:
    exit_code = record.main(["--payload", str(payload_path), "--output-root", str(output_root), kind])
    assert exit_code == 0
    outputs = list(output_root.rglob("*.json"))
    assert len(outputs) == 1
    return json.loads(outputs[0].read_text(encoding="utf-8"))


def test_human_review_recorder_forwards_authority_commits_and_validates(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.png"
    candidate = tmp_path / "candidate.json"
    handoff = tmp_path / "handoff.json"
    receipt = tmp_path / "receipt.json"
    reviewed_sha = _tiny_png(reviewed)
    candidate_sha = _write_text(candidate, "candidate\n")
    handoff_sha = _write_text(handoff, "handoff\n")
    receipt_sha = _write_text(receipt, "receipt\n")

    payload = {
        "date_str": "2026-07-17",
        "slot_id": "slot-00",
        "image_index": 0,
        "reviewer_operator_id": "nicolas",
        "reviewed_image_path": str(reviewed),
        "reviewed_image_sha256": reviewed_sha,
        "candidate_artifact_path": str(candidate),
        "candidate_artifact_sha256": candidate_sha,
        "handoff_artifact_path": str(handoff),
        "handoff_artifact_sha256": handoff_sha,
        "execution_receipt_artifact_path": str(receipt),
        "execution_receipt_artifact_sha256": receipt_sha,
        "provider_job_id": "job-123",
        "authority_commit_expected": "a" * 40,
        "authority_commit_final": "a" * 40,
        "disposition": "accepted_for_hpe_closure",
        "findings": [],
        "confirmation_statement": closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT,
    }
    payload_path = tmp_path / "human.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    artifact = _run_record_main(payload_path, tmp_path / "out", "human-review")
    normalized = closure_evidence.validate_human_evidence_review_artifact(artifact)

    assert normalized["authority_commit_expected"] == "a" * 40
    assert normalized["authority_commit_final"] == "a" * 40
    assert normalized["publishing_authorized"] is False


@pytest.mark.parametrize("field", ["authority_commit_expected", "authority_commit_final"])
def test_human_review_recorder_fails_cleanly_when_authority_commit_is_missing(
    tmp_path: Path,
    field: str,
) -> None:
    reviewed = tmp_path / "reviewed.png"
    candidate = tmp_path / "candidate.json"
    handoff = tmp_path / "handoff.json"
    receipt = tmp_path / "receipt.json"
    reviewed_sha = _tiny_png(reviewed)
    candidate_sha = _write_text(candidate, "candidate\n")
    handoff_sha = _write_text(handoff, "handoff\n")
    receipt_sha = _write_text(receipt, "receipt\n")

    payload = {
        "date_str": "2026-07-17",
        "slot_id": "slot-00",
        "image_index": 0,
        "reviewer_operator_id": "nicolas",
        "reviewed_image_path": str(reviewed),
        "reviewed_image_sha256": reviewed_sha,
        "candidate_artifact_path": str(candidate),
        "candidate_artifact_sha256": candidate_sha,
        "handoff_artifact_path": str(handoff),
        "handoff_artifact_sha256": handoff_sha,
        "execution_receipt_artifact_path": str(receipt),
        "execution_receipt_artifact_sha256": receipt_sha,
        "provider_job_id": "job-123",
        "disposition": "accepted_for_hpe_closure",
        "findings": [],
        "confirmation_statement": closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT,
    }
    payload.pop(field, None)
    payload_path = tmp_path / "human-missing.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    exit_code = record.main(["--payload", str(payload_path), "--output-root", str(tmp_path / "out"), "human-review"])
    assert exit_code == 1


def test_manual_semantic_recorder_forwards_provider_job_id_and_validates(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.png"
    prompt = tmp_path / "prompt.txt"
    candidate = tmp_path / "candidate.json"
    receipt = tmp_path / "receipt.json"
    reviewed_sha = _tiny_png(reviewed)
    prompt_sha = _write_text(prompt, "prompt\n")
    candidate_sha = _write_text(candidate, "candidate\n")
    receipt_sha = _write_text(receipt, "receipt\n")

    payload = {
        "date_str": "2026-07-17",
        "slot_id": "slot-00",
        "image_index": 0,
        "reviewer_operator_id": "nicolas",
        "reviewed_image_path": str(reviewed),
        "reviewed_image_sha256": reviewed_sha,
        "prompt_artifact_path": str(prompt),
        "prompt_sha256": prompt_sha,
        "candidate_artifact_path": str(candidate),
        "candidate_artifact_sha256": candidate_sha,
        "execution_receipt_artifact_path": str(receipt),
        "execution_receipt_artifact_sha256": receipt_sha,
        "provider_job_id": "job-123",
        "authority_commit_expected": "b" * 40,
        "authority_commit_final": "b" * 40,
        "disposition": "accepted_for_hpe_closure",
        "assessment": [
            {"aspect_id": aspect, "status": "verified", "detail": "observed and acceptable"}
            for aspect in closure_evidence.MANUAL_SEMANTIC_ASPECT_IDS
        ],
        "findings": [],
        "confirmation_statement": closure_evidence.MANUAL_SEMANTIC_CONFIRMATION_STATEMENT,
    }
    payload_path = tmp_path / "manual.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    artifact = _run_record_main(payload_path, tmp_path / "out", "manual-semantic-review")
    normalized = closure_evidence.validate_manual_semantic_review_artifact(artifact)

    assert normalized["provider_job_id"] == "job-123"
    assert normalized["publishing_authorized"] is False


def test_manual_semantic_recorder_fails_cleanly_when_provider_job_id_is_missing(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.png"
    prompt = tmp_path / "prompt.txt"
    candidate = tmp_path / "candidate.json"
    receipt = tmp_path / "receipt.json"
    reviewed_sha = _tiny_png(reviewed)
    prompt_sha = _write_text(prompt, "prompt\n")
    candidate_sha = _write_text(candidate, "candidate\n")
    receipt_sha = _write_text(receipt, "receipt\n")

    payload = {
        "date_str": "2026-07-17",
        "slot_id": "slot-00",
        "image_index": 0,
        "reviewer_operator_id": "nicolas",
        "reviewed_image_path": str(reviewed),
        "reviewed_image_sha256": reviewed_sha,
        "prompt_artifact_path": str(prompt),
        "prompt_sha256": prompt_sha,
        "candidate_artifact_path": str(candidate),
        "candidate_artifact_sha256": candidate_sha,
        "execution_receipt_artifact_path": str(receipt),
        "execution_receipt_artifact_sha256": receipt_sha,
        "authority_commit_expected": "b" * 40,
        "authority_commit_final": "b" * 40,
        "disposition": "accepted_for_hpe_closure",
        "assessment": [
            {"aspect_id": aspect, "status": "verified", "detail": "observed and acceptable"}
            for aspect in closure_evidence.MANUAL_SEMANTIC_ASPECT_IDS
        ],
        "findings": [],
        "confirmation_statement": closure_evidence.MANUAL_SEMANTIC_CONFIRMATION_STATEMENT,
    }
    payload_path = tmp_path / "manual-missing.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    exit_code = record.main(["--payload", str(payload_path), "--output-root", str(tmp_path / "out"), "manual-semantic-review"])
    assert exit_code == 1


def test_recorder_refuses_to_overwrite_existing_artifact(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.png"
    candidate = tmp_path / "candidate.json"
    handoff = tmp_path / "handoff.json"
    receipt = tmp_path / "receipt.json"
    reviewed_sha = _tiny_png(reviewed)
    candidate_sha = _write_text(candidate, "candidate\n")
    handoff_sha = _write_text(handoff, "handoff\n")
    receipt_sha = _write_text(receipt, "receipt\n")

    payload = {
        "date_str": "2026-07-17",
        "slot_id": "slot-00",
        "image_index": 0,
        "reviewer_operator_id": "nicolas",
        "reviewed_image_path": str(reviewed),
        "reviewed_image_sha256": reviewed_sha,
        "candidate_artifact_path": str(candidate),
        "candidate_artifact_sha256": candidate_sha,
        "handoff_artifact_path": str(handoff),
        "handoff_artifact_sha256": handoff_sha,
        "execution_receipt_artifact_path": str(receipt),
        "execution_receipt_artifact_sha256": receipt_sha,
        "provider_job_id": "job-123",
        "authority_commit_expected": "a" * 40,
        "authority_commit_final": "a" * 40,
        "disposition": "accepted_for_hpe_closure",
        "findings": [],
        "confirmation_statement": closure_evidence.HUMAN_REVIEW_CONFIRMATION_STATEMENT,
    }
    payload_path = tmp_path / "human.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    out = tmp_path / "out"
    _run_record_main(payload_path, out, "human-review")
    first_sha = hashlib.sha256((out / "2026-07-17" / "slot-00" / "lena_hpe_human_evidence_review_slot-00_00.json").read_bytes()).hexdigest()

    exit_code = record.main(["--payload", str(payload_path), "--output-root", str(out), "human-review"])
    assert exit_code == 1
    second_sha = hashlib.sha256((out / "2026-07-17" / "slot-00" / "lena_hpe_human_evidence_review_slot-00_00.json").read_bytes()).hexdigest()
    assert second_sha == first_sha
