"""Tests for HPE-2C PR1: human_presence_output_qa_v1 and Lena adapter."""

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


def _write_json(path: Path, value: Any) -> str:
    data = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _raw_sha256(data)


def _write_png(path: Path) -> str:
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)
    return _raw_sha256(png_bytes)


def _make_candidate_decision(*, plan_fp: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "lena_pre_generation_candidate_gate_v1",
        "candidate_status": "selected",
        "influencer_id": "lena",
    }
    if plan_fp is not None:
        value["plan_fingerprint_sha256"] = plan_fp
    return value


def _make_manifest(*, manifest_sha: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "human_presence_output_qa_manifest_v1",
        "outputs": ["image_00.png"],
    }
    if manifest_sha is not None:
        value["manifest_sha256"] = manifest_sha
    return value


def _artifact_source_artifacts(tmp_path: Path) -> dict[str, str | None]:
    return {
        "plan_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test_plan.json",
        "candidate_decision_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test.json",
        "manifest_path": "pipeline/higgsfield_debug/2026-07-16/slot/result_manifest.json",
        "image_path": "pipeline/higgsfield_library/lena/2026-07-16/slot_00.png",
    }


def _valid_integrity_result(
    *,
    plan: dict[str, Any],
    candidate_decision: dict[str, Any],
    manifest: dict[str, Any],
    image_sha: str,
    expected_plan_fp: str | None = None,
    expected_cd_sha: str | None = None,
    expected_mf_sha: str | None = None,
    expected_img_sha: str | None = None,
) -> dict[str, Any]:
    return qa_module.evaluate_still_image_presence_integrity(
        plan=plan,
        expected_plan_fingerprint_sha256=expected_plan_fp,
        candidate_decision=candidate_decision,
        candidate_decision_sha256=_canonical_sha256(candidate_decision),
        expected_candidate_decision_sha256=expected_cd_sha,
        manifest=manifest,
        manifest_sha256=_canonical_sha256(manifest),
        expected_manifest_sha256=expected_mf_sha,
        image_sha256=image_sha,
        expected_image_sha256=expected_img_sha,
        media_type="still_image",
    )


def _build_artifact(
    *,
    integrity_result: dict[str, Any],
    source_artifacts: dict[str, str | None] | None = None,
    generated_at_utc: str = "2026-07-16T00:00:00Z",
) -> dict[str, Any]:
    return qa_module.build_presence_output_qa_artifact_v1(
        integrity_result=integrity_result,
        source_artifacts=source_artifacts or _artifact_source_artifacts(Path(".")),
        evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
        generated_at_utc=generated_at_utc,
    )


def _good_v2_artifact() -> dict[str, Any]:
    plan = _compiled_plan()
    plan_fp = ranking.plan_fingerprint_sha256(plan)
    candidate_decision = _make_candidate_decision()
    manifest = _make_manifest()
    plan_values = qa_module._still_image_plan_field_values(plan)
    integrity = _valid_integrity_result(
        plan=plan,
        candidate_decision=candidate_decision,
        manifest=manifest,
        image_sha="a" * 64,
        expected_plan_fp=plan_fp,
        expected_cd_sha=_canonical_sha256(candidate_decision),
        expected_mf_sha=_canonical_sha256(manifest),
        expected_img_sha="a" * 64,
    )
    return qa_module.build_presence_output_qa_artifact_v2(
        integrity_result=integrity,
        semantic_result=_findings_present_semantic_result(plan_values),
        source_artifacts=_artifact_source_artifacts(Path(".")),
        evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
        compiled_plan_values=plan_values,
        generated_at_utc="2026-07-16T00:00:00Z",
    )


def _findings_present_semantic_result(
    plan_values: dict[str, Any],
) -> dict[str, Any]:
    return {
        "semantic_status": "findings_present",
        "semantic_findings": [
            {
                "finding_code": "object_interaction_plan_contradiction",
                "category": "plan_contradiction",
                "plan_field_ref": "performance_actions.object_interaction",
                "plan_field_value": plan_values["performance_actions.object_interaction"],
                "observed_description": "The hand is not interacting with an object.",
                "confidence": "high",
                "image_index": 0,
                "advisory_only": False,
            }
        ],
        "semantic_result_provenance": {
            "provider": "anthropic",
            "model": "claude-sonnet-5",
            "request_binding_sha256": "a" * 64,
            "evaluated_at_utc": "2026-07-16T00:00:00Z",
            "response_schema_version": qa_module.SEMANTIC_RESPONSE_SCHEMA_VERSION,
        },
        "semantic_error": None,
    }


# ---------------------------------------------------------------------------
# Generic module tests
# ---------------------------------------------------------------------------


class TestGenericModuleSourceGuarantees:
    def test_generic_module_has_no_provider_imports(self) -> None:
        source = Path(qa_module.__file__).read_text(encoding="utf-8")
        assert not any(name in source for name in ("anthropic", "openai", "requests", "httpx"))


class TestPathSafety:
    @pytest.mark.parametrize(
        "date_str, slot_id",
        [
            ("../2026-07-16", "slot"),
            ("2026-07-16", "../slot"),
            ("..\\2026-07-16", "slot"),
            ("2026-07-16", "..\\slot"),
            ("/tmp", "slot"),
            ("2026-07-16", "/tmp"),
            ("C:\\tmp", "slot"),
            ("2026-07-16", "C:\\tmp"),
            (".", "slot"),
            ("2026-07-16", "."),
            ("", "slot"),
            ("2026-07-16", ""),
        ],
    )
    def test_path_builder_rejects_traversal_and_absolute_paths(
        self, tmp_path: Path, date_str: str, slot_id: str
    ) -> None:
        with pytest.raises(ValueError):
            disposition.presence_output_qa_artifact_path(date_str, slot_id, 0, tmp_path)

    @pytest.mark.parametrize("image_index", [-1, 100])
    def test_path_builder_rejects_negative_and_out_of_range_indexes(
        self, tmp_path: Path, image_index: int
    ) -> None:
        with pytest.raises(ValueError):
            disposition.presence_output_qa_artifact_path("2026-07-16", "slot", image_index, tmp_path)

    def test_path_builder_returns_path_under_root(self, tmp_path: Path) -> None:
        path = disposition.presence_output_qa_artifact_path("2026-07-16", "slot", 10, tmp_path)
        assert path.parent == (tmp_path / "2026-07-16" / "slot")
        assert path.name == "presence_qa_slot_10.json"


class TestIntegrityClassification:
    def test_independently_anchored_bindings_produce_valid_artifact(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        image_sha = "a" * 64
        expected_cd_sha = _canonical_sha256(candidate_decision)
        expected_mf_sha = _canonical_sha256(manifest)

        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha=image_sha,
            expected_plan_fp=plan_fp,
            expected_cd_sha=expected_cd_sha,
            expected_mf_sha=expected_mf_sha,
            expected_img_sha=image_sha,
        )
        artifact = _build_artifact(integrity_result=integrity)

        assert integrity["integrity_status"] == "valid"
        assert artifact["recommendation"] == "integrity_pass"
        assert [record["binding_status"] for record in artifact["binding_records"]] == [
            "verified",
            "verified",
            "verified",
            "verified",
        ]
        assert artifact["integrity_findings"] == []

    def test_replaced_image_does_not_yield_integrity_pass(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        expected_cd_sha = _canonical_sha256(candidate_decision)
        expected_mf_sha = _canonical_sha256(manifest)

        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="b" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=expected_cd_sha,
            expected_mf_sha=expected_mf_sha,
            expected_img_sha="c" * 64,
        )
        artifact = _build_artifact(integrity_result=integrity)

        assert integrity["integrity_status"] == "invalid"
        assert artifact["recommendation"] == "integrity_failure"
        mismatch = next(
            record for record in artifact["binding_records"] if record["binding_name"] == "generated_image"
        )
        assert mismatch["binding_status"] == "mismatch"
        assert any(finding["finding_code"] == "image_sha256_mismatch" for finding in artifact["integrity_findings"])

    def test_unrelated_image_without_independent_anchor_is_not_assessable(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="d" * 64,
            expected_plan_fp=plan_fp,
        )
        artifact = _build_artifact(integrity_result=integrity)

        assert integrity["integrity_status"] == "not_assessable"
        assert artifact["recommendation"] == "not_assessable"
        image_binding = next(
            record for record in artifact["binding_records"] if record["binding_name"] == "generated_image"
        )
        assert image_binding["binding_status"] == "not_assessable"
        assert image_binding["observed_sha256"] == "d" * 64

    def test_candidate_and_manifest_without_independent_anchors_stay_structural(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="e" * 64,
            expected_plan_fp=plan_fp,
        )

        status_map = {record["binding_name"]: record["binding_status"] for record in integrity["binding_records"]}
        assert status_map["plan"] == "verified"
        assert status_map["candidate_decision"] == "structurally_validated"
        assert status_map["manifest"] == "structurally_validated"
        assert status_map["generated_image"] == "not_assessable"
        assert integrity["integrity_status"] == "not_assessable"

    def test_plan_mismatch_is_invalid(self) -> None:
        plan = _compiled_plan()
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="f" * 64,
            expected_plan_fp="0" * 64,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="f" * 64,
        )

        assert integrity["integrity_status"] == "invalid"
        assert any(finding["finding_code"] == "plan_fingerprint_mismatch" for finding in integrity["integrity_findings"])


class TestValidation:
    def _good_artifact(self) -> dict[str, Any]:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        return _build_artifact(integrity_result=integrity)

    def test_valid_artifact_passes_validation(self) -> None:
        artifact = self._good_artifact()
        returned = qa_module.validate_presence_output_qa_artifact(artifact)
        assert returned is artifact

    def test_valid_with_findings_is_rejected(self) -> None:
        artifact = self._good_artifact()
        artifact["integrity_findings"] = artifact["integrity_findings"] + [
            {"finding_code": "extra", "dimension": "integrity", "severity": "info"}
        ]
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_invalid_without_mismatch_binding_is_rejected(self) -> None:
        artifact = self._good_artifact()
        artifact["integrity_status"] = "invalid"
        artifact["recommendation"] = "integrity_failure"
        artifact["binding_records"][0]["binding_status"] = "observed_only"
        artifact["integrity_findings"] = [
            {
                "finding_code": "plan_fingerprint_not_assessable",
                "dimension": "integrity",
                "severity": "info",
            }
        ]
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_not_assessable_without_reason_is_rejected(self) -> None:
        artifact = self._good_artifact()
        artifact["integrity_status"] = "not_assessable"
        artifact["recommendation"] = "not_assessable"
        artifact["integrity_findings"] = []
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_semantic_findings_are_rejected(self) -> None:
        artifact = self._good_artifact()
        artifact["semantic_findings"] = [{"finding_code": "visual_finding"}]
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_semantic_status_must_remain_not_evaluated(self) -> None:
        artifact = self._good_artifact()
        artifact["semantic_status"] = "evaluated"
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact_v1(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_v2_artifact_requires_semantic_fields(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        artifact = qa_module.build_presence_output_qa_artifact_v2(
            integrity_result=integrity,
            semantic_result=_findings_present_semantic_result(plan_values),
            source_artifacts=_artifact_source_artifacts(Path(".")),
            evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
            compiled_plan_values=plan_values,
            generated_at_utc="2026-07-16T00:00:00Z",
        )
        assert artifact["schema_version"] == qa_module.SCHEMA_VERSION_V2
        assert artifact["semantic_status"] == "findings_present"
        assert artifact["semantic_findings"]
        assert artifact["semantic_result_provenance"] is not None
        assert artifact["semantic_error"] is None
        payload = json.loads(json.dumps(artifact, sort_keys=True))
        assert qa_module.validate_presence_output_qa_artifact_v2(payload) is payload

    def test_v2_builder_rejects_mismatched_plan_field_value(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        semantic_result = _findings_present_semantic_result(plan_values)
        semantic_result["semantic_findings"][0]["plan_field_value"] = "wrong-value"
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.build_presence_output_qa_artifact_v2(
                integrity_result=integrity,
                semantic_result=semantic_result,
                source_artifacts=_artifact_source_artifacts(Path(".")),
                evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
                compiled_plan_values=plan_values,
                generated_at_utc="2026-07-16T00:00:00Z",
            )
        assert exc_info.value.code == "presence_output_malformed_artifact"

    @pytest.mark.parametrize(
        "plan_field_value",
        ["fully_aware", "camera-focused"],
    )
    def test_v2_finding_builds_and_validates_for_multiple_allowed_plan_values(
        self, plan_field_value: str
    ) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        plan_values["performance_actions.object_interaction"] = plan_field_value
        semantic_result = {
            "semantic_status": "findings_present",
            "semantic_findings": [
                {
                    "finding_code": "object_interaction_plan_contradiction",
                    "category": "plan_contradiction",
                    "plan_field_ref": "performance_actions.object_interaction",
                    "plan_field_value": plan_field_value,
                    "observed_description": "The object interaction is not aligned with the plan.",
                    "confidence": "high",
                    "image_index": 0,
                    "advisory_only": False,
                }
            ],
            "semantic_result_provenance": {
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "request_binding_sha256": "a" * 64,
                "evaluated_at_utc": "2026-07-16T00:00:00Z",
                "response_schema_version": qa_module.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            },
            "semantic_error": None,
        }
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        artifact = qa_module.build_presence_output_qa_artifact_v2(
            integrity_result=integrity,
            semantic_result=semantic_result,
            source_artifacts=_artifact_source_artifacts(Path(".")),
            evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
            compiled_plan_values=plan_values,
            generated_at_utc="2026-07-16T00:00:00Z",
        )
        reloaded = json.loads(json.dumps(artifact, sort_keys=True))
        assert qa_module.validate_presence_output_qa_artifact_v2(reloaded) is reloaded

    @pytest.mark.parametrize(
        "mutator",
        [
            lambda artifact: artifact["semantic_findings"].__setitem__(
                0,
                {**artifact["semantic_findings"][0], "finding_code": "unknown_code"},
            ),
            lambda artifact: artifact["semantic_findings"].__setitem__(
                0,
                {**artifact["semantic_findings"][0], "category": "invalid_category"},
            ),
            lambda artifact: artifact["semantic_findings"].__setitem__(
                0,
                {**artifact["semantic_findings"][0], "category": "presence_failure_indicator"},
            ),
            lambda artifact: artifact["semantic_findings"].__setitem__(
                0,
                {**artifact["semantic_findings"][0], "plan_field_ref": "gaze_arc.start_focus"},
            ),
            lambda artifact: artifact["semantic_findings"].__setitem__(
                0,
                {**artifact["semantic_findings"][0], "observed_description": "x" * 301},
            ),
            lambda artifact: artifact["semantic_findings"].__setitem__(
                0,
                {**artifact["semantic_findings"][0], "image_index": 1},
            ),
        ],
    )
    def test_v2_validator_rejects_invalid_semantic_finding_variants(self, mutator) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        artifact = qa_module.build_presence_output_qa_artifact_v2(
            integrity_result=integrity,
            semantic_result=_findings_present_semantic_result(plan_values),
            source_artifacts=_artifact_source_artifacts(Path(".")),
            evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
            compiled_plan_values=plan_values,
            generated_at_utc="2026-07-16T00:00:00Z",
        )
        mutator(artifact)
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact_v2(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    @pytest.mark.parametrize(
        "description",
        [
            "the anatomy is wrong",
            "the hands are wrong",
            "identity is wrong here",
            "approved for publish",
            "rejected for now",
            "publishing is paused",
            "retry the review",
        ],
    )
    def test_v2_validator_rejects_prohibited_observed_descriptions(self, description: str) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        artifact = qa_module.build_presence_output_qa_artifact_v2(
            integrity_result=integrity,
            semantic_result=_findings_present_semantic_result(plan_values),
            source_artifacts=_artifact_source_artifacts(Path(".")),
            evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
            compiled_plan_values=plan_values,
            generated_at_utc="2026-07-16T00:00:00Z",
        )
        artifact["semantic_findings"][0]["observed_description"] = description
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact_v2(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    @pytest.mark.parametrize(
        "description",
        [
            "the body pose looks good",
            "the face remains calm",
            "image quality is consistent with the plan",
            "the viewer relationship is clear",
        ],
    )
    def test_v2_validator_allows_presence_specific_language(self, description: str) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        artifact = qa_module.build_presence_output_qa_artifact_v2(
            integrity_result=integrity,
            semantic_result=_findings_present_semantic_result(plan_values),
            source_artifacts=_artifact_source_artifacts(Path(".")),
            evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
            compiled_plan_values=plan_values,
            generated_at_utc="2026-07-16T00:00:00Z",
        )
        artifact["semantic_findings"][0]["observed_description"] = description
        assert qa_module.validate_presence_output_qa_artifact_v2(artifact) is artifact

    def test_v2_validator_does_not_require_original_plan_object(self) -> None:
        plan = _compiled_plan()
        plan_fp = ranking.plan_fingerprint_sha256(plan)
        candidate_decision = _make_candidate_decision()
        manifest = _make_manifest()
        plan_values = qa_module._still_image_plan_field_values(plan)
        integrity = _valid_integrity_result(
            plan=plan,
            candidate_decision=candidate_decision,
            manifest=manifest,
            image_sha="a" * 64,
            expected_plan_fp=plan_fp,
            expected_cd_sha=_canonical_sha256(candidate_decision),
            expected_mf_sha=_canonical_sha256(manifest),
            expected_img_sha="a" * 64,
        )
        artifact = qa_module.build_presence_output_qa_artifact_v2(
            integrity_result=integrity,
            semantic_result=_findings_present_semantic_result(plan_values),
            source_artifacts=_artifact_source_artifacts(Path(".")),
            evaluator_version="hpe_2c_pr3_integrity_semantic_v1",
            compiled_plan_values=plan_values,
            generated_at_utc="2026-07-16T00:00:00Z",
        )
        serialized = json.dumps(artifact, sort_keys=True)
        reloaded = json.loads(serialized)
        assert qa_module.validate_presence_output_qa_artifact_v2(reloaded) is reloaded

    def test_malformed_binding_record_is_rejected(self) -> None:
        artifact = self._good_artifact()
        del artifact["binding_records"][0]["binding_status"]
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(artifact)
        assert exc_info.value.code == "presence_output_malformed_artifact"

    def test_invalid_sha_format_is_rejected(self) -> None:
        artifact = self._good_artifact()
        artifact["binding_records"][0]["observed_sha256"] = "not-a-sha"
        with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
            qa_module.validate_presence_output_qa_artifact(artifact)
        assert exc_info.value.code == "presence_output_invalid_sha256"


# ---------------------------------------------------------------------------
# Tools-layer adapter tests
# ---------------------------------------------------------------------------


class TestToolsLayerSourceGuarantees:
    def test_tools_layer_has_no_provider_imports(self) -> None:
        source = Path(disposition.__file__).read_text(encoding="utf-8")
        assert not any(name in source for name in ("anthropic", "openai", "requests", "httpx"))


class TestArtifactPath:
    def test_artifact_path_structure(self, tmp_path: Path) -> None:
        path = disposition.presence_output_qa_artifact_path(
            "2026-07-16", "hpe-2026-07-16-slot-00-photo", 0, tmp_path
        )
        assert path.parent == tmp_path.resolve() / "2026-07-16" / "hpe-2026-07-16-slot-00-photo"
        assert path.name == "presence_qa_hpe-2026-07-16-slot-00-photo_00.json"

    def test_artifact_path_zero_padding(self, tmp_path: Path) -> None:
        path9 = disposition.presence_output_qa_artifact_path("2026-07-16", "slot", 9, tmp_path)
        path10 = disposition.presence_output_qa_artifact_path("2026-07-16", "slot", 10, tmp_path)
        assert path9.name.endswith("_09.json")
        assert path10.name.endswith("_10.json")


class TestAtomicWrite:
    def test_atomic_write_and_read(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "test.json"
        artifact = {
            "report_type": "human_presence_output_qa",
            "schema_version": qa_module.SCHEMA_VERSION_V1,
            "medium": "still_image",
            "evaluator_version": "hpe_2c_pr3_integrity_semantic_v1",
            "generated_at_utc": "2026-07-16T00:00:00Z",
            "integrity_status": "valid",
            "integrity_findings": [],
            "semantic_status": "not_evaluated",
            "semantic_findings": [],
            "binding_records": [
                {
                    "binding_name": "plan",
                    "binding_status": "verified",
                    "observed_sha256": "a" * 64,
                    "expected_sha256": "a" * 64,
                    "verification_basis": "independent_expected_plan_fingerprint",
                    "source_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test_plan.json",
                    "details": {},
                },
                {
                    "binding_name": "candidate_decision",
                    "binding_status": "verified",
                    "observed_sha256": "b" * 64,
                    "expected_sha256": "b" * 64,
                    "verification_basis": "independent_expected_candidate_decision_sha256",
                    "source_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test.json",
                    "details": {},
                },
                {
                    "binding_name": "manifest",
                    "binding_status": "verified",
                    "observed_sha256": "c" * 64,
                    "expected_sha256": "c" * 64,
                    "verification_basis": "independent_expected_manifest_sha256",
                    "source_path": "pipeline/higgsfield_debug/2026-07-16/slot/result_manifest.json",
                    "details": {},
                },
                {
                    "binding_name": "generated_image",
                    "binding_status": "verified",
                    "observed_sha256": "d" * 64,
                    "expected_sha256": "d" * 64,
                    "verification_basis": "independent_expected_image_sha256",
                    "source_path": "pipeline/higgsfield_library/lena/2026-07-16/slot_00.png",
                    "details": {},
                },
            ],
            "source_artifacts": {
                "plan_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test_plan.json",
                "candidate_decision_path": "pipeline/strategy/lena/pre_generation_candidates/2026-07-16/test.json",
                "manifest_path": "pipeline/higgsfield_debug/2026-07-16/slot/result_manifest.json",
                "image_path": "pipeline/higgsfield_library/lena/2026-07-16/slot_00.png",
            },
            "recommendation": "integrity_pass",
        }
        written_path, written_artifact, created = disposition.write_presence_output_qa_artifact_atomic(path, artifact)
        assert written_path == path
        assert written_artifact == artifact
        assert created is True
        assert path.exists()
        reloaded = json.loads(path.read_bytes())
        assert reloaded == artifact
        repeated_path, repeated_artifact, repeated_created = disposition.write_presence_output_qa_artifact_atomic(path, artifact)
        assert repeated_path == path
        assert repeated_artifact == artifact
        assert repeated_created is False

    def test_atomic_write_leaves_no_tmp_file(self, tmp_path: Path) -> None:
        path = tmp_path / "artifact.json"
        disposition.write_presence_output_qa_artifact_atomic(path, {"x": 1})
        assert not path.with_suffix(".json.tmp").exists()


class TestRunPresenceOutputQA:
    def _setup_files(
        self, tmp_path: Path, *, include_plan_anchor: bool = False
    ) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any], dict[str, Any], str, str, str]:
        plan = _compiled_plan()
        candidate_decision = _make_candidate_decision(
            plan_fp=ranking.plan_fingerprint_sha256(plan) if include_plan_anchor else None
        )
        manifest = _make_manifest()

        cd_path = tmp_path / "candidate_decision.json"
        mf_path = tmp_path / "manifest.json"
        img_path = tmp_path / "image.png"

        cd_sha = _write_json(cd_path, candidate_decision)
        mf_sha = _write_json(mf_path, manifest)
        img_sha = _write_png(img_path)

        return cd_path, mf_path, img_path, plan, candidate_decision, manifest, cd_sha, mf_sha, img_sha

    def test_no_hpe_produces_not_assessable_without_reads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cd_path, mf_path, img_path, plan, *_ = self._setup_files(tmp_path / "files")

        def _fail(*_: Any, **__: Any) -> str:
            raise AssertionError("unexpected file read/hash in no-HPE path")

        monkeypatch.setattr(disposition, "sha256_file", _fail)
        monkeypatch.setattr(disposition, "_load_json_object", _fail)

        path_a, artifact_a = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=None,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )
        path_b, artifact_b = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=None,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )

        assert path_a == path_b
        assert artifact_a == artifact_b
        assert artifact_a["integrity_status"] == "not_assessable"
        assert artifact_a["recommendation"] == "not_assessable"
        assert all(record["binding_status"] == "not_assessable" for record in artifact_a["binding_records"])
        assert path_a.exists()

    def test_fixed_timestamp_produces_byte_identical_artifacts(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, *_ = self._setup_files(tmp_path / "files")
        out_root = tmp_path / "out"
        path_a, artifact_a = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )
        path_b, artifact_b = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=copy.deepcopy(plan),
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=out_root,
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )

        assert artifact_a == artifact_b
        assert path_a.exists()
        assert path_b.exists()
        assert artifact_a["generated_at_utc"] == "2026-07-16T00:00:00Z"

    def test_adapter_reads_plan_fingerprint_when_present(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, candidate_decision, manifest, *_ = self._setup_files(
            tmp_path / "files",
            include_plan_anchor=True,
        )
        artifact_path, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )

        plan_binding = next(record for record in artifact["binding_records"] if record["binding_name"] == "plan")
        assert plan_binding["binding_status"] == "verified"
        assert plan_binding["observed_sha256"] == ranking.plan_fingerprint_sha256(plan)
        assert artifact["integrity_status"] == "not_assessable"
        assert artifact["recommendation"] == "not_assessable"
        assert artifact_path.exists()

    def test_adapter_without_image_anchor_remains_not_assessable(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, *_ = self._setup_files(tmp_path / "files")
        _, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )

        image_binding = next(record for record in artifact["binding_records"] if record["binding_name"] == "generated_image")
        assert image_binding["binding_status"] == "not_assessable"
        assert image_binding["observed_sha256"] is not None
        assert artifact["recommendation"] == "not_assessable"

    def test_adapter_handles_slot_hcr_012_without_special_case(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, *_ = self._setup_files(tmp_path / "files")
        _, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="hcr_012",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
        )

        assert artifact["source_artifacts"]["candidate_decision_path"].endswith("candidate_decision.json")
        assert artifact["integrity_status"] == "not_assessable"
        assert artifact["recommendation"] == "not_assessable"

    def test_live_semantic_review_runs_once_for_unanchored_integrity(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, *_ = self._setup_files(tmp_path / "files")
        calls: list[dict[str, Any]] = []

        def semantic_provider(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {
                "semantic_status": "aligned",
                "semantic_findings": [],
                "semantic_result_provenance": {
                    "provider": disposition.SEMANTIC_PROVIDER_NAME,
                    "model": disposition.SEMANTIC_MODEL_NAME,
                    "request_binding_sha256": "a" * 64,
                    "evaluated_at_utc": "2026-07-16T00:00:00Z",
                    "response_schema_version": qa_module.SEMANTIC_RESPONSE_SCHEMA_VERSION,
                },
                "semantic_error": None,
            }

        _, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
            live_presence_semantic_review=True,
            semantic_provider=semantic_provider,
        )

        assert len(calls) == 1
        assert artifact["integrity_status"] == "not_assessable"
        assert artifact["semantic_status"] == "aligned"
        assert artifact["schema_version"] == qa_module.SCHEMA_VERSION_V2
        assert artifact["recommendation"] == "not_assessable"

    def test_verified_binding_mismatch_skips_semantic_provider(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, candidate_decision, *_ = self._setup_files(
            tmp_path / "files",
            include_plan_anchor=True,
        )
        candidate_decision["plan_fingerprint_sha256"] = "0" * 64
        _write_json(cd_path, candidate_decision)
        calls: list[dict[str, Any]] = []

        def semantic_provider(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {
                "semantic_status": "aligned",
                "semantic_findings": [],
                "semantic_result_provenance": None,
                "semantic_error": None,
            }

        _, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
            live_presence_semantic_review=True,
            semantic_provider=semantic_provider,
        )

        assert calls == []
        assert artifact["integrity_status"] == "invalid"
        assert artifact["semantic_status"] == "not_assessable"
        assert any(
            finding["finding_code"] == "plan_fingerprint_mismatch"
            for finding in artifact["integrity_findings"]
        )

    def test_live_semantic_review_default_path_does_not_call_provider(self, tmp_path: Path) -> None:
        cd_path, mf_path, img_path, plan, *_ = self._setup_files(tmp_path / "files")
        calls: list[dict[str, Any]] = []

        def semantic_provider(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {
                "semantic_status": "aligned",
                "semantic_findings": [],
                "semantic_result_provenance": None,
                "semantic_error": None,
            }

        _, artifact = disposition.run_presence_output_qa(
            date_str="2026-07-16",
            slot_id="test-slot-00-photo",
            image_index=0,
            plan=plan,
            candidate_decision_path=cd_path,
            manifest_path=mf_path,
            image_path=img_path,
            output_root=tmp_path / "out",
            evaluated_at_utc="2026-07-16T00:00:00Z",
            live_presence_semantic_review=False,
            semantic_provider=semantic_provider,
        )

        assert calls == []
        assert artifact["schema_version"] == qa_module.SCHEMA_VERSION_V2
        assert artifact["semantic_status"] == "not_evaluated"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda artifact: artifact["semantic_findings"][0].__setitem__("observed_description", 123),
        lambda artifact: artifact["semantic_findings"][0].__setitem__("plan_field_ref", None),
        lambda artifact: artifact["semantic_findings"][0].__setitem__("observed_description", ""),
        lambda artifact: artifact["semantic_findings"][0].__setitem__("observed_description", "x" * 301),
        lambda artifact: artifact["semantic_findings"][0].__setitem__("advisory_only", "true"),
        lambda artifact: artifact["semantic_findings"][0].__setitem__("advisory_only", 1),
    ],
)
def test_persisted_v2_validation_rejects_string_and_boolean_type_mismatches(mutator) -> None:
    artifact = _good_v2_artifact()
    mutator(artifact)
    with pytest.raises(qa_module.HumanPresenceOutputQAError) as exc_info:
        qa_module.validate_presence_output_qa_artifact_v2(artifact)
    assert exc_info.value.code == "presence_output_malformed_artifact"
