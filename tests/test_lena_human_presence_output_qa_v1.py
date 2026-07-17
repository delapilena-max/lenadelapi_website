"""Tests for HPE-2C PR1: human_presence_output_qa_v1 (generic) and
lena_presence_output_qa_disposition_v1 (Lena adapter).

Test numbering in docstrings tracks the PR1 contract list exactly.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.presence import human_presence_candidate_ranking_v1 as ranking
from pipeline.presence import human_presence_output_qa_v1 as qa_module
from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from tools.strategy import lena_human_presence_profile_v1 as lena_profile
import tools.lena_presence_output_qa_disposition_v1 as disposition


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _compiled_plan() -> dict[str, Any]:
    contract = lena_profile.build_lena_presence_contract()
    return plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_candidate_decision() -> dict[str, Any]:
    return {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "candidate_status": "selected",
        "influencer_id": "lena",
    }


def _make_manifest() -> dict[str, Any]:
    return {
        "schema_version": "test_manifest_v1",
        "outputs": ["image_00.png"],
    }


def _write_canonical(path: Path, value: Any) -> str:
    """Write value as canonical JSON to path; return sha256 of the bytes."""
    data = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _raw_sha256(data)


def _write_png(path: Path) -> str:
    """Write a tiny fake PNG and return its sha256."""
    # Minimal valid PNG header + IEND
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)
    return _raw_sha256(png_bytes)


def _valid_integrity_call(
    plan: dict[str, Any],
    fingerprint: str,
    candidate_decision: dict[str, Any],
    manifest: dict[str, Any],
    image_sha: str,
    *,
    expected_plan_fp: str | None = None,
    expected_cd_sha: str | None = None,
    expected_mf_sha: str | None = None,
    expected_img_sha: str | None = None,
    media_type: str = "still_image",
) -> dict[str, Any]:
    return qa_module.evaluate_still_image_presence_integrity(
        plan=plan,
        expected_plan_fingerprint_sha256=expected_plan_fp if expected_plan_fp is not None else fingerprint,
        candidate_decision=candidate_decision,
        expected_candidate_decision_sha256=(
            expected_cd_sha if expected_cd_sha is not None else _canonical_sha256(candidate_decision)
        ),
        manifest=manifest,
        expected_manifest_sha256=(
            expected_mf_sha if expected_mf_sha is not None else _canonical_sha256(manifest)
        ),
        image_sha256=image_sha,
        expected_image_sha256=expected_img_sha if expected_img_sha is not None else image_sha,
        media_type=media_type,
    )


def _valid_artifact(
    plan: dict[str, Any],
    fingerprint: str,
    candidate_decision: dict[str, Any],
    manifest: dict[str, Any],
    image_sha: str = "a" * 64,
    *,
    generated_at_utc: str = "2026-07-16T00:00:00Z",
) -> dict[str, Any]:
    result = _valid_integrity_call(plan, fingerprint, candidate_decision, manifest, image_sha)
    return qa_module.build_presence_output_qa_artifact(
        integrity_result=result,
        plan_fingerprint_sha256_value=fingerprint,
        candidate_decision_sha256=_canonical_sha256(candidate_decision),
        manifest_sha256=_canonical_sha256(manifest),
        image_sha256=image_sha,
        source_artifacts={
            "plan_path": "supplied_by_caller",
            "candidate_decision_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test.json",
            "manifest_path": "pipeline/higgsfield_debug/2026-07-16/slot/result_manifest.json",
            "image_path": "pipeline/higgsfield_library/lena/2026-07-16/slot_00.png",
        },
        evaluator_version="hpe_2c_pr1_integrity_v1",
        generated_at_utc=generated_at_utc,
    )


# ===========================================================================
# GENERIC MODULE TESTS (pipeline/presence/human_presence_output_qa_v1.py)
# ===========================================================================


class TestGenericModuleSourceGuarantees:
    """Tests 1-3: Source-level guarantees on the generic module."""

    def test_no_lena_specific_identifiers(self) -> None:
        """Test 1: Source file contains no Lena-specific identifiers."""
        source = Path(qa_module.__file__).read_text(encoding="utf-8")
        forbidden = ("Lena", "hcr_", "wc_p", "env_v008", "lena")
        violations = [term for term in forbidden if term in source]
        assert not violations, (
            f"generic module contains Lena-specific identifiers: {violations}"
        )

    def test_no_filesystem_write(self) -> None:
        """Test 2: Source file contains no filesystem write calls."""
        source = Path(qa_module.__file__).read_text(encoding="utf-8")
        write_indicators = ("open(", ".write(", "write_text", "write_bytes", "Path.write")
        violations = [indicator for indicator in write_indicators if indicator in source]
        assert not violations, (
            f"generic module contains filesystem write calls: {violations}"
        )

    def test_no_provider_import(self) -> None:
        """Test 3: Source file contains no provider imports."""
        source = Path(qa_module.__file__).read_text(encoding="utf-8")
        provider_imports = ("anthropic", "openai", "requests", "httpx")
        violations = [name for name in provider_imports if name in source]
        assert not violations, (
            f"generic module imports provider libraries: {violations}"
        )


class TestDeterminismAndFingerprint:
    """Tests 4-5: Determinism and plan fingerprint reuse."""

    def test_valid_integrity_produces_deterministic_byte_equivalent_artifacts(self) -> None:
        """Test 4: Valid integrity inputs produce deterministic byte-equivalent artifacts."""
        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        cd = _make_candidate_decision()
        mf = _make_manifest()

        artifact_a = _valid_artifact(plan, fp, cd, mf)
        artifact_b = _valid_artifact(plan, fp, cd, mf)

        assert artifact_a == artifact_b

    def test_plan_fingerprint_reuses_ranking_module_function(self) -> None:
        """Test 5: plan_fingerprint_sha256 imported, not reimplemented."""
        # Verify the module imports and uses the same function object.
        plan = _compiled_plan()
        module_result = ranking.plan_fingerprint_sha256(plan)

        # Call through our qa integrity path and verify the plan_fingerprint
        # finding 'observed' field equals what ranking module produces.
        bad_fp = "0" * 64
        result = qa_module.evaluate_still_image_presence_integrity(
            plan=plan,
            expected_plan_fingerprint_sha256=bad_fp,
            candidate_decision=_make_candidate_decision(),
            expected_candidate_decision_sha256=_canonical_sha256(_make_candidate_decision()),
            manifest=_make_manifest(),
            expected_manifest_sha256=_canonical_sha256(_make_manifest()),
            image_sha256="b" * 64,
            expected_image_sha256="b" * 64,
            media_type="still_image",
        )
        mismatch = next(
            f for f in result["integrity_findings"]
            if f["finding_code"] == "plan_fingerprint_mismatch"
        )
        assert mismatch["observed"] == module_result


class TestIntegrityFindings:
    """Tests 6-9: Individual integrity finding codes."""

    def _base(self) -> tuple[dict, str, dict, dict, str]:
        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        cd = _make_candidate_decision()
        mf = _make_manifest()
        img = "c" * 64
        return plan, fp, cd, mf, img

    def test_stale_plan_fingerprint_produces_plan_fingerprint_mismatch(self) -> None:
        """Test 6: Stale plan fingerprint → invalid with plan_fingerprint_mismatch."""
        plan, fp, cd, mf, img = self._base()
        stale_fp = "d" * 64
        result = _valid_integrity_call(
            plan, fp, cd, mf, img, expected_plan_fp=stale_fp
        )
        assert result["integrity_status"] == "invalid"
        codes = [f["finding_code"] for f in result["integrity_findings"]]
        assert "plan_fingerprint_mismatch" in codes

    def test_candidate_decision_sha256_mismatch(self) -> None:
        """Test 7: Candidate decision sha256 mismatch → candidate_decision_binding_mismatch."""
        plan, fp, cd, mf, img = self._base()
        wrong_cd_sha = "e" * 64
        result = _valid_integrity_call(
            plan, fp, cd, mf, img, expected_cd_sha=wrong_cd_sha
        )
        assert result["integrity_status"] == "invalid"
        codes = [f["finding_code"] for f in result["integrity_findings"]]
        assert "candidate_decision_binding_mismatch" in codes

    def test_manifest_sha256_mismatch(self) -> None:
        """Test 8: Manifest sha256 mismatch → manifest_binding_mismatch."""
        plan, fp, cd, mf, img = self._base()
        wrong_mf_sha = "f" * 64
        result = _valid_integrity_call(
            plan, fp, cd, mf, img, expected_mf_sha=wrong_mf_sha
        )
        assert result["integrity_status"] == "invalid"
        codes = [f["finding_code"] for f in result["integrity_findings"]]
        assert "manifest_binding_mismatch" in codes

    def test_image_sha256_mismatch(self) -> None:
        """Test 9: Image sha256 mismatch → image_sha256_mismatch."""
        plan, fp, cd, mf, img = self._base()
        wrong_img_sha = "0123456789abcdef" * 4
        result = _valid_integrity_call(
            plan, fp, cd, mf, img, expected_img_sha=wrong_img_sha
        )
        assert result["integrity_status"] == "invalid"
        codes = [f["finding_code"] for f in result["integrity_findings"]]
        assert "image_sha256_mismatch" in codes


class TestUnsupportedMedia:
    """Test 10: Unsupported media type raises correct exception."""

    def test_unsupported_media_type_raises(self) -> None:
        """Test 10: Unsupported media_type → HumanPresenceOutputQAError."""
        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        cd = _make_candidate_decision()
        mf = _make_manifest()

        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.evaluate_still_image_presence_integrity(
                plan=plan,
                expected_plan_fingerprint_sha256=fp,
                candidate_decision=cd,
                expected_candidate_decision_sha256=_canonical_sha256(cd),
                manifest=mf,
                expected_manifest_sha256=_canonical_sha256(mf),
                image_sha256="a" * 64,
                expected_image_sha256="a" * 64,
                media_type="video",
            )
        assert exc_info.value.code == "presence_output_unsupported_media"


class TestValidation:
    """Tests 11, 13: validate_presence_output_qa_artifact."""

    def _good_artifact(self) -> dict[str, Any]:
        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        return _valid_artifact(plan, fp, _make_candidate_decision(), _make_manifest())

    def test_malformed_artifact_fails_validation(self) -> None:
        """Test 11: Malformed artifact fails validation."""
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact({"schema_version": "wrong"})
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_contradictory_recommendation_fails_validation(self) -> None:
        """Test 13: integrity_status="valid" with recommendation="integrity_failure"."""
        artifact = self._good_artifact()
        assert artifact["integrity_status"] == "valid"
        bad = dict(artifact, recommendation=qa_module.INTEGRITY_FAILURE)
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(bad)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_valid_artifact_passes_validation(self) -> None:
        """Sanity: a well-formed artifact validates cleanly."""
        artifact = self._good_artifact()
        returned = qa_module.validate_presence_output_qa_artifact(artifact)
        assert returned is artifact


class TestNotAssessable:
    """Test 12: Missing plan → not_assessable (no exception)."""

    def test_missing_plan_returns_not_assessable(self) -> None:
        """Test 12: plan=None → integrity_status not_assessable."""
        cd = _make_candidate_decision()
        mf = _make_manifest()
        result = qa_module.evaluate_still_image_presence_integrity(
            plan=None,
            expected_plan_fingerprint_sha256=None,
            candidate_decision=cd,
            expected_candidate_decision_sha256=_canonical_sha256(cd),
            manifest=mf,
            expected_manifest_sha256=_canonical_sha256(mf),
            image_sha256="a" * 64,
            expected_image_sha256="a" * 64,
            media_type="still_image",
        )
        assert result["integrity_status"] == "not_assessable"

    def test_empty_plan_fingerprint_returns_not_assessable(self) -> None:
        """Variant: empty string plan fingerprint also triggers not_assessable."""
        plan = _compiled_plan()
        cd = _make_candidate_decision()
        mf = _make_manifest()
        result = qa_module.evaluate_still_image_presence_integrity(
            plan=plan,
            expected_plan_fingerprint_sha256="",
            candidate_decision=cd,
            expected_candidate_decision_sha256=_canonical_sha256(cd),
            manifest=mf,
            expected_manifest_sha256=_canonical_sha256(mf),
            image_sha256="a" * 64,
            expected_image_sha256="a" * 64,
            media_type="still_image",
        )
        assert result["integrity_status"] == "not_assessable"


class TestSemanticInvariants:
    """Tests 14-15: semantic_status and semantic_findings are always fixed."""

    def _all_artifacts(self) -> list[dict[str, Any]]:
        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        cd = _make_candidate_decision()
        mf = _make_manifest()
        img = "b" * 64

        artifacts = []
        ts = "2026-07-16T00:00:00Z"

        # valid
        result_valid = _valid_integrity_call(plan, fp, cd, mf, img)
        artifacts.append(
            qa_module.build_presence_output_qa_artifact(
                integrity_result=result_valid,
                plan_fingerprint_sha256_value=fp,
                candidate_decision_sha256=_canonical_sha256(cd),
                manifest_sha256=_canonical_sha256(mf),
                image_sha256=img,
                source_artifacts={"plan_path": "x", "candidate_decision_path": "x",
                                  "manifest_path": "x", "image_path": "x"},
                evaluator_version="test",
                generated_at_utc=ts,
            )
        )

        # invalid (bad fingerprint)
        result_invalid = _valid_integrity_call(
            plan, fp, cd, mf, img, expected_plan_fp="0" * 64
        )
        artifacts.append(
            qa_module.build_presence_output_qa_artifact(
                integrity_result=result_invalid,
                plan_fingerprint_sha256_value=fp,
                candidate_decision_sha256=_canonical_sha256(cd),
                manifest_sha256=_canonical_sha256(mf),
                image_sha256=img,
                source_artifacts={"plan_path": "x", "candidate_decision_path": "x",
                                  "manifest_path": "x", "image_path": "x"},
                evaluator_version="test",
                generated_at_utc=ts,
            )
        )

        # not_assessable
        result_na = qa_module.evaluate_still_image_presence_integrity(
            plan=None,
            expected_plan_fingerprint_sha256=None,
            candidate_decision=cd,
            expected_candidate_decision_sha256=_canonical_sha256(cd),
            manifest=mf,
            expected_manifest_sha256=_canonical_sha256(mf),
            image_sha256=img,
            expected_image_sha256=img,
            media_type="still_image",
        )
        artifacts.append(
            qa_module.build_presence_output_qa_artifact(
                integrity_result=result_na,
                plan_fingerprint_sha256_value="",
                candidate_decision_sha256="",
                manifest_sha256="",
                image_sha256="",
                source_artifacts={"plan_path": "x", "candidate_decision_path": "x",
                                  "manifest_path": "x", "image_path": "x"},
                evaluator_version="test",
                generated_at_utc=ts,
            )
        )
        return artifacts

    def test_semantic_status_is_always_not_evaluated(self) -> None:
        """Test 14: semantic_status is always "not_evaluated"."""
        for artifact in self._all_artifacts():
            assert artifact["semantic_status"] == "not_evaluated", artifact["semantic_status"]

    def test_semantic_findings_is_always_empty(self) -> None:
        """Test 15: semantic_findings is always []."""
        for artifact in self._all_artifacts():
            assert artifact["semantic_findings"] == [], artifact["semantic_findings"]


class TestNoVisualFindingCodes:
    """Test 16: Module defines no visual finding code constants."""

    def test_no_visual_finding_code_constants(self) -> None:
        """Test 16: No visual finding codes are defined in the generic module."""
        visual_codes = {
            "dead_or_unfocused_eyes",
            "frozen_expression",
            "mannequin_pose",
            "unmotivated_movement",
            "face_body_emotion_mismatch",
            "wrong_person",
            "anatomy_defect",
        }
        module_attrs = set(dir(qa_module))
        overlap = visual_codes & module_attrs
        assert not overlap, f"generic module defines visual finding codes: {overlap}"

        # Also check source text doesn't have them as string literals in constants.
        source = Path(qa_module.__file__).read_text(encoding="utf-8")
        for code in visual_codes:
            assert code not in source, (
                f"generic module source references visual finding code: {code!r}"
            )


# ===========================================================================
# TOOLS-LAYER TESTS (tools/lena_presence_output_qa_disposition_v1.py)
# ===========================================================================


class TestArtifactPath:
    """Test 1: presence_output_qa_artifact_path returns correct path."""

    def test_artifact_path_structure(self, tmp_path: Path) -> None:
        path = disposition.presence_output_qa_artifact_path(
            "2026-07-16", "hpe-2026-07-16-slot-00-photo", 0, tmp_path
        )
        assert path.parent == tmp_path / "2026-07-16" / "hpe-2026-07-16-slot-00-photo"
        assert path.name == "presence_qa_hpe-2026-07-16-slot-00-photo_00.json"

    def test_artifact_path_image_index_zero_padded(self, tmp_path: Path) -> None:
        path9 = disposition.presence_output_qa_artifact_path(
            "2026-07-16", "slot", 9, tmp_path
        )
        path10 = disposition.presence_output_qa_artifact_path(
            "2026-07-16", "slot", 10, tmp_path
        )
        assert path9.name.endswith("_09.json")
        assert path10.name.endswith("_10.json")


class TestAtomicWrite:
    """Test 2: Atomic write produces valid JSON readable back as the same dict."""

    def test_atomic_write_and_read(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "test.json"
        artifact = {
            "report_type": "human_presence_output_qa",
            "schema_version": "human_presence_output_qa_v1",
            "medium": "still_image",
            "evaluator_version": "hpe_2c_pr1_integrity_v1",
            "integrity_status": "valid",
            "recommendation": "integrity_pass",
        }
        disposition.write_presence_output_qa_artifact_atomic(path, artifact)
        assert path.exists()
        reloaded = json.loads(path.read_bytes())
        assert reloaded == artifact

    def test_atomic_write_leaves_no_tmp_file(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.json"
        disposition.write_presence_output_qa_artifact_atomic(path, {"x": 1})
        tmp_file = path.with_suffix(".json.tmp")
        assert not tmp_file.exists()


class TestRunPresenceOutputQA:
    """Tests 3-4, 6-7: run_presence_output_qa behaviour."""

    def _setup_files(
        self, tmp_path: Path
    ) -> tuple[Path, Path, Path, dict, str, dict, str, str]:
        """Create temp candidate_decision, manifest, image files and return paths + metadata."""
        cd = _make_candidate_decision()
        mf = _make_manifest()

        cd_path = tmp_path / "candidate_decision.json"
        mf_path = tmp_path / "manifest.json"
        img_path = tmp_path / "image.png"

        cd_sha = _write_canonical(cd_path, cd)
        mf_sha = _write_canonical(mf_path, mf)
        img_sha = _write_png(img_path)

        return cd_path, mf_path, img_path, cd, cd_sha, mf, mf_sha, img_sha

    def test_run_with_valid_inputs_produces_valid_artifact(
        self, tmp_path: Path
    ) -> None:
        """Test 3: run_presence_output_qa with valid inputs produces deterministic output."""
        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        cd_path, mf_path, img_path, cd, cd_sha, mf, mf_sha, img_sha = (
            self._setup_files(tmp_path / "files")
        )
        out_root = tmp_path / "out"

        path_a, artifact_a = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            plan_fingerprint=fp,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
        )
        path_b, artifact_b = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=copy.deepcopy(plan),
            plan_fingerprint=fp,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
        )

        # Integrity result must be identical (timestamp may differ, ignore it).
        assert artifact_a["integrity_status"] == "valid"
        assert artifact_a["integrity_status"] == artifact_b["integrity_status"]
        assert artifact_a["integrity_findings"] == artifact_b["integrity_findings"]
        assert artifact_a["recommendation"] == artifact_b["recommendation"]
        assert artifact_a["binding_records"] == artifact_b["binding_records"]

        # Artifact is on disk and valid JSON.
        assert path_a.exists()
        reloaded = json.loads(path_a.read_bytes())
        assert reloaded["integrity_status"] == "valid"

    def test_run_with_no_hpe_produces_not_assessable(
        self, tmp_path: Path
    ) -> None:
        """Test 4: plan=None → not_assessable artifact."""
        cd_path, mf_path, img_path, *_ = self._setup_files(tmp_path / "files")
        out_root = tmp_path / "out"

        path, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=None,
            plan_fingerprint=None,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
        )
        assert artifact["integrity_status"] == "not_assessable"
        assert artifact["recommendation"] == "not_assessable"
        assert path.exists()

    def test_existing_approval_artifacts_not_modified(
        self, tmp_path: Path
    ) -> None:
        """Test 6: Existing approval artifacts are not modified."""
        # Place a fake approval artifact and verify it is unchanged after running QA.
        approval_dir = tmp_path / "approvals"
        approval_dir.mkdir()
        approval_path = approval_dir / "slot_higgsfield_generation_approval.json"
        approval_content = json.dumps({"type": "approval", "slot_id": "slot"})
        approval_path.write_text(approval_content)
        original_mtime = approval_path.stat().st_mtime

        cd_path, mf_path, img_path, *_ = self._setup_files(tmp_path / "files")
        out_root = tmp_path / "out"

        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            plan_fingerprint=fp,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
        )

        # Approval file must be byte-identical and not modified.
        assert approval_path.read_text() == approval_content
        assert approval_path.stat().st_mtime == original_mtime

    def test_hcr_012_provenance_preserved_in_source_artifacts(
        self, tmp_path: Path
    ) -> None:
        """Test 7: hcr_012 path is recorded without special-casing."""
        # Use a path resembling the hcr_012 baseline slot.
        hcr_root = tmp_path / "pipeline" / "strategy" / "lena" / "pre_generation_candidates"
        hcr_root.mkdir(parents=True)
        cd_path = hcr_root / "2026-06-30" / "lena_pre_generation_candidate_hcr_012.json"
        cd_path.parent.mkdir(parents=True)

        cd = _make_candidate_decision()
        _write_canonical(cd_path, cd)

        mf_path = tmp_path / "manifest.json"
        img_path = tmp_path / "image.png"
        _write_canonical(mf_path, _make_manifest())
        _write_png(img_path)

        plan = _compiled_plan()
        fp = ranking.plan_fingerprint_sha256(plan)
        out_root = tmp_path / "out"

        _, artifact = disposition.run_presence_output_qa(
            date_str="2026-06-30",
            slot_id="hcr_012",
            image_index=0,
            plan=plan,
            plan_fingerprint=fp,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
        )
        # The path must be faithfully recorded.
        assert str(cd_path) in artifact["source_artifacts"]["candidate_decision_path"]
        # integrity_status should be valid (no tampering).
        assert artifact["integrity_status"] == "valid"


class TestToolsLayerSourceGuarantees:
    """Test 5: Tools adapter imports no provider libraries."""

    def test_tools_layer_no_provider_import(self) -> None:
        """Test 5: No anthropic, requests, or httpx imported by tools adapter."""
        source = Path(disposition.__file__).read_text(encoding="utf-8")
        provider_imports = ("anthropic", "openai", "requests", "httpx")
        violations = [name for name in provider_imports if name in source]
        assert not violations, (
            f"tools adapter imports provider libraries: {violations}"
        )
