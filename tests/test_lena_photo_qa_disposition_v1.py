from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.identity import lena_higgsfield_identity as identity
from tools import lena_photo_qa_disposition_v1 as disposition
from tools.strategy import lena_execute_selected_candidate_v1 as handoff
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _all_pass() -> dict:
    return {
        "schema_version": disposition.VISUAL_SCHEMA_VERSION,
        "observations": {
            key: {"status": "pass", "reason_codes": [], "notes": f"{key} passed"}
            for key in disposition.VISUAL_OBSERVATION_KEYS
        },
    }


def _failed(key: str, reason: str) -> dict:
    value = _all_pass()
    value["observations"][key] = {"status": "fail", "reason_codes": [reason], "notes": f"observed {reason}"}
    return value


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    date_str = "2026-07-13"
    slot_id = "lenagate2026071323ce1d67-pack000-04-photo"
    lane = "morning apartment"
    recipe_id = "hcr_007"
    hook_id = "cbn_004"
    prompt = "Exact synthetic Lena prompt. Pose: standing naturally. Expression: calm expression. Wardrobe: fixture outfit."
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
    candidate = {
        "candidate_id": f"{slot_id}::{recipe_id}::{hook_id}",
        "slot_id": slot_id,
        "lane": lane,
        "activity": "standing naturally",
        "recipe_id": recipe_id,
        "hook_id": hook_id,
        "pose": "weight_shift_one_hip",
        "pose_body_language_id": "pose_p001",
        "wardrobe_outfit_id": "wc_fixture",
        "visual_style": "fitted_dress",
        "prompt_sha256": prompt_sha,
        "exact_proposed_dry_run_command": f"python pipeline/higgsfield_lena_api_executor.py --date {date_str} --slot-id {slot_id}",
    }
    core = {
        "schema_version": selector.SCHEMA_VERSION,
        "influencer_id": "lena",
        "as_of_date": date_str,
        "authority_commit": "a" * 40,
        "input_provenance": [],
        "candidate_status": "selected",
        "final_action": handoff.ACCEPTED_FINAL_ACTION,
        "candidate": candidate,
        "exact_next_allowed_action": candidate["exact_proposed_dry_run_command"],
        "provider_authorized": False,
        "side_effects_performed": [],
    }
    decision = dict(core)
    decision["generated_at_utc"] = "2026-07-13T00:00:00Z"
    decision["decision_fingerprint_sha256"] = hashlib.sha256(selector._canonical_bytes(core)).hexdigest()
    decision_path = tmp_path / "decision.json"
    _write_json(decision_path, decision)
    monkeypatch.setattr(handoff, "_validate_authority", lambda artifact: None)

    image_path = tmp_path / "generated.png"
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "white").save(image_path)
    reference_path = tmp_path / "reference.png"
    Image.new("RGB", (64, 64), "gray").save(reference_path)

    provider_job_id = "job-123"
    manifest = {
        "provider": "higgsfield",
        "job_type": identity.EXPECTED_JOB_TYPE,
        "date": date_str,
        "slot_id": slot_id,
        "lane": lane,
        "prompt_sha256": prompt_sha,
        "image_prompt": prompt,
        "pose_body_language_id": "pose_p001",
        "pose_body_language_label": "weight_shift_one_hip",
        "pose_text": "standing naturally",
        "expression_text": "calm expression",
        "expression_safe_fallback_used": False,
        "expression_safe_fallback_reason": None,
        "expression_scene_conflict_terms": [],
        "expression_gaze_id": "gaze_fixture",
        "expression_gaze_label": "camera-aware calm gaze",
        "wardrobe_outfit_id": "wc_fixture",
        "wardrobe_outfit_name": "fixture outfit",
        "wardrobe_silhouette_class": "fitted_dress",
        "effective_wardrobe_silhouette_class": "fitted_dress",
        "custom_reference_id": next(iter(identity.APPROVED_CUSTOM_REFERENCE_IDS)),
        "cli_soul_name": identity.EXPECTED_SOUL_NAME,
        "cli_soul_type": identity.EXPECTED_SOUL_TYPE,
        "provider_job_id": provider_job_id,
        "provider_status": "completed",
        "saved_image_path": str(image_path),
        "live_attempt_count": 1,
        "retry_count": 0,
        "image_format_detected": ".png",
    }
    manifest_path = tmp_path / "debug" / date_str / slot_id / "result_manifest.json"
    _write_json(manifest_path, manifest)

    evidence = {
        "schema_version": identity.SCHEMA_VERSION,
        "verified_at_utc": "2026-07-13T00:01:00Z",
        "provider": "higgsfield",
        "date": date_str,
        "slot_id": slot_id,
        "provider_job_id": provider_job_id,
        "provider_job_status": "completed",
        "job_type": identity.EXPECTED_JOB_TYPE,
        "custom_reference_id": manifest["custom_reference_id"],
        "soul_name": identity.EXPECTED_SOUL_NAME,
        "soul_type": identity.EXPECTED_SOUL_TYPE,
        "prompt_sha256": prompt_sha,
        "width": identity.EXPECTED_WIDTH,
        "height": identity.EXPECTED_HEIGHT,
        "local_image_path": str(image_path),
        "local_image_sha256": _sha(image_path),
        "local_image_sha256_provenance": "fixture local hash",
        "verification_result": "pass",
        "checks_passed": ["fixture"],
    }
    evidence_path = tmp_path / "identity_verification.json"
    _write_json(evidence_path, evidence)
    monkeypatch.setattr(identity, "identity_verification_evidence_path", lambda date, slot: evidence_path)

    memory = {
        "pattern_counts": {},
        "soft_flagged_patterns": [],
        "hard_excluded_patterns": [],
        "contributing_records": [],
        "skipped": [],
    }
    kwargs = {
        "decision_path": decision_path,
        "manifest_path": manifest_path,
        "image_path": image_path,
        "expected_image_sha256": _sha(image_path),
        "identity_evidence_path": evidence_path,
        "reference_specs": [(reference_path, _sha(reference_path))],
        "reference_authority_artifact": tmp_path / "reference_authority.json",
        "reference_authority_sha256": "1" * 64,
        "failure_memory_loader": lambda: memory,
    }
    reference_set_sha = hashlib.sha256(selector._canonical_bytes({
        "authority_id": "synthetic_test_reference_authority",
        "references": [{"path": str(reference_path.resolve()), "sha256": _sha(reference_path)}],
    })).hexdigest()
    def synthetic_reference_authority(specs, authority_path, authority_sha, authority_commit):
        supplied = list(specs)
        if authority_path != (tmp_path / "reference_authority.json").resolve() or authority_sha != "1" * 64:
            raise disposition.BoundaryError("identity_evidence_invalid", "synthetic authority evidence rejected")
        if supplied != [(reference_path, _sha(reference_path))]:
            raise disposition.BoundaryError("identity_evidence_invalid", "synthetic authority rejected reference set")
        return (
            [{"path": str(reference_path.resolve()), "sha256": _sha(reference_path), "format": "PNG", "width": 64, "height": 64}],
            reference_set_sha,
            {"authority_id": "synthetic_test_reference_authority", "authority_artifact_path": str(tmp_path / "reference_authority.json"), "authority_artifact_sha256": "1" * 64, "authority_commit": decision["authority_commit"]},
        )
    monkeypatch.setattr(disposition, "_validate_references", synthetic_reference_authority)
    monkeypatch.setattr(disposition, "_validate_model_authority", lambda *args: {
        "path": str(tmp_path / "model_authority.json"), "sha256": "2" * 64,
        "provider": "anthropic", "approved_model": "exact-test-model",
    })
    monkeypatch.setattr(disposition, "_load_canonical_rubric", lambda commit: {
        "authority_commit": commit, "required_semantic_dimensions": {"identity": ["face"], "character_fit": ["confident"], "reject_character_traits": ["fake-rich signaling", "melodramatic", "audience-controlled identity"], "sexuality_and_safety": ["no sexual-signal stacking"], "aesthetic_quality": ["premium visual discipline"]},
    })
    monkeypatch.setattr(disposition, "_validate_manifest_bank_context", lambda manifest, candidate, commit: None)
    return {
        "kwargs": kwargs,
        "decision": decision,
        "decision_path": decision_path,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "image_path": image_path,
        "reference_path": reference_path,
        "evidence": evidence,
        "evidence_path": evidence_path,
        "memory": memory,
        "tmp_path": tmp_path,
        "date": date_str,
        "slot": slot_id,
        "monkeypatch": monkeypatch,
        "reference_set_sha": reference_set_sha,
    }


def _evaluate(harness: dict, observations: dict | None = None, **updates):
    kwargs = dict(harness["kwargs"])
    kwargs.update(updates)
    reviewer = kwargs.pop("reviewer", None)
    if observations is not None:
        harness["monkeypatch"].setattr(disposition, "call_anthropic_visual_review", reviewer or (lambda request: observations))
        kwargs.update({
            "live_visual_review": True,
            "visual_provider": "anthropic",
            "visual_model": "exact-test-model",
            "visual_model_authority_artifact": harness["tmp_path"] / "model_authority.json",
            "visual_model_authority_sha256": "2" * 64,
            "expected_decision_fingerprint": harness["decision"]["decision_fingerprint_sha256"],
            "expected_reference_set_sha256": harness["reference_set_sha"],
        })
    elif reviewer is not None:
        harness["monkeypatch"].setattr(disposition, "call_anthropic_visual_review", reviewer)
    if kwargs.get("live_visual_review"):
        kwargs.setdefault("visual_model_authority_artifact", harness["tmp_path"] / "model_authority.json")
        kwargs.setdefault("visual_model_authority_sha256", "2" * 64)
    return disposition.evaluate_photo_qa_disposition(**kwargs)


def test_accept_disposition_is_bound_and_not_publish_ready(harness) -> None:
    result = _evaluate(harness, _all_pass())
    assert result["disposition"] == "accept"
    assert result["reason_codes"] == []
    assert result["retry_eligible"] is False
    assert result["provider_called"] is True
    assert result["side_effects_performed"] == []
    assert "publish_ready" not in result
    assert result["decision_fingerprint_sha256"] == harness["decision"]["decision_fingerprint_sha256"]
    assert result["image_sha256"] == _sha(harness["image_path"])


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("face_continuity", "recoverable_identity_drift"),
        ("required_action", "required_action_missed"),
        ("gaze", "gaze_missed"),
        ("posture", "posture_missed"),
        ("prop_interaction", "prop_interaction_failed"),
        ("required_visual_evidence", "required_visual_evidence_missing"),
        ("hands_fingers_limbs", "hand_or_anatomy_defect"),
        ("reflections", "reflection_or_contact_error"),
        ("wardrobe_consistency", "wardrobe_realization_failed"),
        ("environment_plausibility", "environment_incoherent"),
        ("composition", "composition_below_standard"),
        ("lighting", "lighting_below_standard"),
        ("overprocessed_appearance", "overprocessed_result"),
        ("visual_clutter", "visual_clutter"),
        ("canonical_lena_personality", "character_fit_miss"),
    ],
)
def test_each_retryable_reason_maps_deterministically(harness, key, reason) -> None:
    result = _evaluate(harness, _failed(key, reason))
    assert result["disposition"] == "retryable_failure"
    assert result["reason_codes"] == [reason]
    assert result["retry_eligible"] is True
    assert result["hard_stop_reason"] is None


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("face_continuity", "wrong_person_or_identity_collapse"),
        ("no_pornographic_presentation", "unsafe_pornographic_presentation"),
        ("environment_plausibility", "prohibited_scene"),
    ],
)
def test_semantic_hard_stop_reasons(harness, key, reason) -> None:
    result = _evaluate(harness, _failed(key, reason))
    assert result["disposition"] == "hard_stop"
    assert result["hard_stop_reason"] == reason
    assert result["retry_eligible"] is False


@pytest.mark.parametrize(
    ("retry_key", "retry_reason", "hard_key", "hard_reason"),
    [
        ("hands_fingers_limbs", "hand_or_anatomy_defect", "face_continuity", "wrong_person_or_identity_collapse"),
        ("composition", "composition_below_standard", "no_pornographic_presentation", "unsafe_pornographic_presentation"),
    ],
)
def test_hard_stop_precedes_retryable_findings(harness, retry_key, retry_reason, hard_key, hard_reason) -> None:
    observations = _failed(retry_key, retry_reason)
    observations["observations"][hard_key] = {"status": "fail", "reason_codes": [hard_reason], "notes": "hard failure"}
    result = _evaluate(harness, observations)
    assert result["disposition"] == "hard_stop"
    assert hard_reason in result["reason_codes"]
    assert retry_reason in result["reason_codes"]


def test_provenance_hard_stop_precedes_recoverable_visual_observation(harness) -> None:
    value = dict(harness["manifest"])
    value["lane"] = "swapped lane"
    _write_json(harness["manifest_path"], value)
    result = _evaluate(harness, _failed("composition", "composition_below_standard"))
    assert result["disposition"] == "hard_stop"
    assert result["reason_codes"] == ["provenance_mismatch"]


def test_malformed_decision_artifact_blocks(harness) -> None:
    harness["decision_path"].write_text("[]", encoding="utf-8")
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["decision_binding_mismatch"]


def test_altered_decision_fingerprint_blocks(harness) -> None:
    value = json.loads(harness["decision_path"].read_text())
    value["candidate"]["hook_id"] = "changed"
    _write_json(harness["decision_path"], value)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["decision_binding_mismatch"]


@pytest.mark.parametrize("field", ["candidate_id", "slot_id"])
def test_candidate_and_slot_mismatch_block(harness, field) -> None:
    value = json.loads(harness["decision_path"].read_text())
    value["candidate"][field] = "wrong"
    core = {k: v for k, v in value.items() if k not in {"generated_at_utc", "decision_fingerprint_sha256"}}
    value["decision_fingerprint_sha256"] = hashlib.sha256(selector._canonical_bytes(core)).hexdigest()
    _write_json(harness["decision_path"], value)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["decision_binding_mismatch"]


@pytest.mark.parametrize("field", ["slot_id", "lane", "prompt_sha256"])
def test_manifest_slot_lane_and_prompt_mismatch_block(harness, field) -> None:
    value = dict(harness["manifest"])
    value[field] = "0" * 64 if field == "prompt_sha256" else "wrong"
    _write_json(harness["manifest_path"], value)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["provenance_mismatch"]


def test_swapped_manifest_blocks(harness) -> None:
    swapped = harness["tmp_path"] / "swapped.json"
    value = dict(harness["manifest"])
    value["provider_job_id"] = "other-job"
    _write_json(swapped, value)
    result = _evaluate(harness, _all_pass(), manifest_path=swapped)
    assert result["reason_codes"] == ["identity_evidence_invalid"]


def test_swapped_image_blocks(harness) -> None:
    other = harness["tmp_path"] / "other.png"
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "black").save(other)
    result = _evaluate(harness, _all_pass(), image_path=other)
    assert result["reason_codes"] == ["image_hash_mismatch"]


def test_explicit_generated_image_sha_is_required_and_exact(harness) -> None:
    result = _evaluate(harness, _all_pass(), expected_image_sha256="0" * 64)
    assert result["reason_codes"] == ["image_hash_mismatch"]


def test_image_sha_mismatch_blocks(harness) -> None:
    evidence = dict(harness["evidence"])
    evidence["local_image_sha256"] = "0" * 64
    _write_json(harness["evidence_path"], evidence)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["image_hash_mismatch"]


def test_invalid_identity_evidence_blocks(harness) -> None:
    evidence = dict(harness["evidence"])
    evidence["custom_reference_id"] = "wrong"
    _write_json(harness["evidence_path"], evidence)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["identity_evidence_invalid"]


def test_identity_reference_hash_mismatch_blocks(harness) -> None:
    result = _evaluate(harness, _all_pass(), reference_specs=[(harness["reference_path"], "0" * 64)])
    assert result["reason_codes"] == ["identity_evidence_invalid"]


@pytest.mark.parametrize("artifact,sha,specs", [(None, "1" * 64, None), (Path("authority.json"), "", []), (Path("authority.json"), "1" * 64, [])])
def test_missing_reference_authority_or_reference_blocks(harness, artifact, sha, specs) -> None:
    result = _evaluate(
        harness,
        _all_pass(),
        reference_authority_artifact=artifact,
        reference_authority_sha256=sha,
        reference_specs=harness["kwargs"]["reference_specs"] if specs is None else specs,
    )
    assert result["reason_codes"] == ["identity_evidence_invalid"]


def test_corrupt_image_blocks(harness) -> None:
    harness["image_path"].write_bytes(b"not an image")
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["corrupt_or_untrusted_evidence"]


def test_invalid_dimensions_block(harness) -> None:
    Image.new("RGB", (12, 12), "white").save(harness["image_path"])
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["corrupt_or_untrusted_evidence"]


def test_invalid_format_blocks(harness) -> None:
    bmp = harness["tmp_path"] / "generated.bmp"
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "white").save(bmp)
    result = _evaluate(harness, _all_pass(), image_path=bmp)
    assert result["reason_codes"] == ["corrupt_or_untrusted_evidence"]


@pytest.mark.parametrize("mutator", [
    lambda value: {},
    lambda value: {**value, "observations": {key: item for key, item in list(value["observations"].items())[:-1]}},
    lambda value: {**value, "disposition": "accept"},
    lambda value: {**value, "observations": {**value["observations"], "face_continuity": {"status": "fail", "reason_codes": [], "notes": "ambiguous"}}},
])
def test_malformed_partial_or_ambiguous_model_output_blocks(harness, mutator) -> None:
    result = _evaluate(harness, mutator(_all_pass()))
    assert result["reason_codes"] == ["visual_review_unavailable"]
    assert result["disposition"] == "hard_stop"


def test_visual_reason_code_must_match_its_observation_dimension(harness) -> None:
    value = _failed("lighting", "lighting_below_standard")
    value["observations"]["lighting"]["reason_codes"] = ["wrong_person_or_identity_collapse"]
    result = _evaluate(harness, value)
    assert result["reason_codes"] == ["visual_review_unavailable"]


def test_unreviewed_observation_blocks_accept(harness) -> None:
    value = _all_pass()
    value["observations"]["face_continuity"] = {"status": "unreviewed", "reason_codes": [], "notes": "cannot tell"}
    result = _evaluate(harness, value)
    assert result["disposition"] == "hard_stop"
    assert result["reason_codes"] == ["visual_review_unavailable"]


def test_failure_memory_soft_flag_records_evidence_without_blocking(harness) -> None:
    harness["memory"]["soft_flagged_patterns"] = [[harness["manifest"]["lane"], harness["manifest"]["pose_body_language_id"]]]
    result = _evaluate(harness, _all_pass())
    assert result["disposition"] == "accept"
    assert result["qa_inputs"]["failure_memory"]["soft_flagged"] is True


def test_failure_memory_pass_counterexample_does_not_hard_exclude(harness) -> None:
    key = f"{harness['manifest']['lane']}::{harness['manifest']['pose_body_language_id']}"
    harness["memory"]["pattern_counts"] = {key: {"pass": 1, "fail": 2}}
    result = _evaluate(harness, _all_pass())
    assert result["disposition"] == "accept"
    assert result["qa_inputs"]["failure_memory"]["pattern_counts"] == {"pass": 1, "fail": 2}


def test_failure_memory_hard_exclusion_overrides_visual_pass(harness) -> None:
    harness["memory"]["hard_excluded_patterns"] = [[harness["manifest"]["lane"], harness["manifest"]["pose_body_language_id"]]]
    result = _evaluate(harness, _all_pass())
    assert result["disposition"] == "hard_stop"
    assert result["reason_codes"] == ["failure_memory_pattern_hard_excluded"]


def test_failure_memory_hard_exclusion_blocks_before_future_visual_call(harness) -> None:
    harness["memory"]["hard_excluded_patterns"] = [[harness["manifest"]["lane"], harness["manifest"]["pose_body_language_id"]]]
    calls = []
    result = _evaluate(
        harness,
        None,
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        expected_decision_fingerprint=harness["decision"]["decision_fingerprint_sha256"],
        expected_image_sha256=_sha(harness["image_path"]),
        expected_reference_set_sha256="unused-because-memory-blocks",
        reviewer=lambda request: calls.append(request),
    )
    assert calls == []
    assert result["reason_codes"] == ["failure_memory_pattern_hard_excluded"]


def test_supplied_observations_are_fixture_only_not_production_evidence(harness) -> None:
    parameters = inspect.signature(disposition.evaluate_photo_qa_disposition).parameters
    assert "visual_observations" not in parameters
    assert "_allow_test_observations" not in parameters
    with pytest.raises(TypeError):
        disposition.evaluate_photo_qa_disposition(**harness["kwargs"], visual_observations=_all_pass())


def test_default_makes_no_provider_call_and_does_not_accept(harness) -> None:
    calls = []
    result = _evaluate(harness, None, reviewer=lambda request: calls.append(request))
    assert calls == []
    assert result["disposition"] == "hard_stop"
    assert result["reason_codes"] == ["visual_review_unavailable"]
    assert result["provider_called"] is False
    assert result["side_effects_performed"] == []


def test_exactly_one_mocked_bound_visual_call_no_retry_or_fallback(harness) -> None:
    preflight = _evaluate(harness, _all_pass())
    reference_set_sha = preflight["identity_reference_provenance"]["reference_set_sha256"]
    calls = []

    def reviewer(request):
        calls.append(request)
        return _all_pass()

    result = _evaluate(
        harness,
        None,
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        expected_decision_fingerprint=harness["decision"]["decision_fingerprint_sha256"],
        expected_image_sha256=_sha(harness["image_path"]),
        expected_reference_set_sha256=reference_set_sha,
        reviewer=reviewer,
    )
    assert len(calls) == 1
    assert calls[0]["image"]["path"] == str(harness["image_path"].resolve())
    assert len(calls[0]["identity_references"]) == 1
    assert calls[0]["visual_provider"] == "anthropic"
    assert calls[0]["visual_model"] == "exact-test-model"
    assert result["disposition"] == "accept"
    assert result["provider_called"] is True


def test_live_binding_mismatch_blocks_before_reviewer(harness) -> None:
    calls = []
    result = _evaluate(
        harness,
        None,
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        expected_decision_fingerprint="0" * 64,
        expected_reference_set_sha256="0" * 64,
        reviewer=lambda request: calls.append(request),
    )
    assert calls == []
    assert result["reason_codes"] == ["decision_binding_mismatch"]


def test_single_provider_exception_becomes_hard_stop_without_retry(harness) -> None:
    preflight = _evaluate(harness, _all_pass())
    calls = []

    def reviewer(request):
        calls.append(request)
        raise RuntimeError("synthetic provider outage")

    result = _evaluate(
        harness,
        None,
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        expected_decision_fingerprint=harness["decision"]["decision_fingerprint_sha256"],
        expected_reference_set_sha256=preflight["identity_reference_provenance"]["reference_set_sha256"],
        reviewer=reviewer,
    )
    assert len(calls) == 1
    assert result["disposition"] == "hard_stop"
    assert result["reason_codes"] == ["visual_review_unavailable"]
    assert result["provider_called"] is True


def test_anthropic_adapter_explicitly_disables_sdk_retries(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "bound.png"
    image_bytes = b"bound image bytes"
    image_path.write_bytes(image_bytes)
    client_options = []
    provider_calls = []
    observations = _all_pass()

    class FakeMessages:
        def create(self, **kwargs):
            provider_calls.append(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use", name="submit_visual_observations", input=observations,
            )])

    def fake_anthropic(**kwargs):
        client_options.append(kwargs)
        return SimpleNamespace(messages=FakeMessages())

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=fake_anthropic))
    request = {
        "image": {"path": str(image_path), "sha256": hashlib.sha256(image_bytes).hexdigest(), "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    assert disposition.call_anthropic_visual_review(request) == observations
    assert client_options == [{"max_retries": 0}]
    assert len(provider_calls) == 1
    assert provider_calls[0]["model"] == disposition.APPROVED_VISUAL_MODEL


def test_anthropic_adapter_malformed_response_fails_without_retry(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "bound.png"
    image_bytes = b"bound image bytes"
    image_path.write_bytes(image_bytes)
    client_options = []
    provider_calls = []

    class FakeMessages:
        def create(self, **kwargs):
            provider_calls.append(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="not structured")])

    def fake_anthropic(**kwargs):
        client_options.append(kwargs)
        return SimpleNamespace(messages=FakeMessages())

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=fake_anthropic))
    request = {
        "image": {"path": str(image_path), "sha256": hashlib.sha256(image_bytes).hexdigest(), "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    with pytest.raises(disposition.BoundaryError, match="exactly one structured observation block"):
        disposition.call_anthropic_visual_review(request)
    assert client_options == [{"max_retries": 0}]
    assert len(provider_calls) == 1
    assert provider_calls[0]["model"] == disposition.APPROVED_VISUAL_MODEL


def test_output_filename_contains_full_image_sha_and_old_qa_is_untouched(harness) -> None:
    old_qa = harness["tmp_path"] / "output" / harness["date"] / f"{harness['slot']}_qa.json"
    _write_json(old_qa, {"historical": True})
    before = old_qa.read_bytes()
    result = _evaluate(harness, _all_pass())
    path = disposition.disposition_artifact_path(result, harness["tmp_path"] / "output")
    assert result["image_sha256"] in path.name
    assert path.name == f"{harness['slot']}__{result['image_sha256']}_qa_disposition.json"
    assert old_qa.read_bytes() == before


def test_deterministic_unchanged_rerun_reuses_without_rewrite(harness) -> None:
    result = _evaluate(harness, _all_pass())
    output_root = harness["tmp_path"] / "output"
    path, saved, created = disposition.write_disposition_artifact(result, output_root)
    assert created is True
    before = path.read_bytes()
    rerun = _evaluate(harness, _all_pass())
    path2, saved2, created2 = disposition.write_disposition_artifact(rerun, output_root)
    assert path2 == path
    assert created2 is False
    assert saved2 == saved
    assert path.read_bytes() == before


def test_conflicting_artifact_refuses_overwrite(harness) -> None:
    result = _evaluate(harness, _all_pass())
    output_root = harness["tmp_path"] / "output"
    path, _, _ = disposition.write_disposition_artifact(result, output_root)
    value = json.loads(path.read_text())
    value["reason_codes"] = ["visual_review_unavailable"]
    _write_json(path, value)
    before = path.read_bytes()
    with pytest.raises(disposition.CollisionError):
        disposition.write_disposition_artifact(result, output_root)
    assert path.read_bytes() == before


def test_no_downstream_or_state_side_effect_fields_exist(harness) -> None:
    result = _evaluate(harness, _all_pass())
    forbidden = {
        "queue", "approval", "publish", "upload", "analytics", "learning",
        "world_state", "env", "freeze_state", "media_generation", "publish_ready",
    }
    assert forbidden.isdisjoint(result)
    assert result["side_effects_performed"] == []


def test_reference_parser_requires_explicit_hash_binding(tmp_path) -> None:
    with pytest.raises(disposition.BoundaryError):
        disposition.parse_reference_spec(str(tmp_path / "reference.png"))


def test_cli_help_exposes_only_explicit_review_and_write_gates() -> None:
    options = disposition._parser().format_help()
    assert "--live-visual-review" in options
    assert "--write-artifact" in options
    assert "--identity-reference-authority-artifact" in options
    assert "--identity-reference-authority-sha256" in options
    assert "--identity-reference" in options
    assert "visual-observations" not in options


def test_public_api_has_no_observation_or_reviewer_injection() -> None:
    parameters = inspect.signature(disposition.evaluate_photo_qa_disposition).parameters
    assert "visual_observations" not in parameters
    assert "_allow_test_observations" not in parameters
    assert "reviewer" not in parameters


@pytest.mark.parametrize(
    "field",
    [
        "pose_body_language_id", "pose_text", "expression_gaze_id", "expression_gaze_label",
        "expression_text", "wardrobe_outfit_id", "wardrobe_outfit_name",
        "wardrobe_silhouette_class", "effective_wardrobe_silhouette_class",
        "live_attempt_count", "retry_count", "image_format_detected",
    ],
)
def test_missing_required_real_manifest_context_blocks(harness, field) -> None:
    value = dict(harness["manifest"])
    value.pop(field)
    _write_json(harness["manifest_path"], value)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["provenance_mismatch"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expression_safe_fallback_used", 1),
        ("expression_safe_fallback_used", 0),
        ("expression_safe_fallback_used", "true"),
        ("expression_safe_fallback_used", "false"),
        ("expression_safe_fallback_used", None),
        ("expression_scene_conflict_terms", None),
        ("expression_scene_conflict_terms", [1]),
    ],
)
def test_expression_fallback_manifest_types_are_strict(harness, field, value) -> None:
    manifest = dict(harness["manifest"])
    manifest[field] = value
    _write_json(harness["manifest_path"], manifest)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["provenance_mismatch"]


@pytest.mark.parametrize("field", ["pose_text", "expression_text"])
def test_manifest_context_swapped_away_from_prompt_blocks(harness, field) -> None:
    value = dict(harness["manifest"])
    value[field] = "swapped context not present in selected prompt"
    _write_json(harness["manifest_path"], value)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["provenance_mismatch"]


def test_failure_memory_never_constructs_none_pose_key() -> None:
    with pytest.raises(disposition.BoundaryError, match="pose_body_language_id"):
        disposition._failure_memory_evidence({"lane": "lane", "pose_body_language_id": None}, lambda: {})


def test_model_binding_requires_exact_independently_approved_identity(monkeypatch) -> None:
    monkeypatch.setattr(disposition, "_committed_json_authority", lambda *args, **kwargs: {
        "schema_version": disposition.MODEL_AUTHORITY_SCHEMA_VERSION,
        "influencer_id": "lena",
        "authority_id": disposition.MODEL_AUTHORITY_ID,
        "provider": "anthropic", "approved_model": disposition.APPROVED_VISUAL_MODEL,
    })
    with pytest.raises(disposition.BoundaryError):
        disposition._validate_model_authority(Path("authority.json"), "1" * 64, "a" * 40, "anthropic", "arbitrary-model")
    approved = disposition._validate_model_authority(
        Path("authority.json"), "1" * 64, "a" * 40, "anthropic", disposition.APPROVED_VISUAL_MODEL,
    )
    assert approved["approved_model"] == disposition.APPROVED_VISUAL_MODEL


@pytest.mark.parametrize("updates", [
    {"visual_model_authority_artifact": None, "visual_model_authority_sha256": None},
    {"visual_model": "arbitrary-model"},
    {"visual_provider": "other"},
])
def test_live_model_authority_failure_never_calls_provider(harness, updates) -> None:
    calls = []
    harness["monkeypatch"].setattr(disposition, "call_anthropic_visual_review", lambda request: calls.append(request))
    if updates.get("visual_model") == "arbitrary-model" or updates.get("visual_provider") == "other":
        harness["monkeypatch"].setattr(
            disposition, "_validate_model_authority",
            lambda *args: (_ for _ in ()).throw(disposition.BoundaryError("visual_review_unavailable", "model authority mismatch")),
        )
    kwargs = {
        "live_visual_review": True, "visual_provider": "anthropic", "visual_model": "exact-test-model",
        "expected_decision_fingerprint": harness["decision"]["decision_fingerprint_sha256"],
        "expected_reference_set_sha256": harness["reference_set_sha"],
        "visual_model_authority_artifact": harness["tmp_path"] / "model_authority.json",
        "visual_model_authority_sha256": "2" * 64,
    }
    kwargs.update(updates)
    result = _evaluate(harness, None, **kwargs)
    assert calls == []
    assert result["reason_codes"] == ["visual_review_unavailable"]


def test_canonical_rubric_and_exact_bindings_reach_single_mocked_call(harness) -> None:
    calls = []
    result = _evaluate(harness, _all_pass(), reviewer=lambda request: calls.append(request) or _all_pass())
    assert result["disposition"] == "accept"
    assert len(calls) == 1
    request = calls[0]
    rubric_text = json.dumps(request["canonical_semantic_rubric"]).lower()
    for term in ("identity", "confident", "fake-rich", "melodramatic", "audience-controlled", "sexual-signal stacking", "premium visual discipline"):
        assert term in rubric_text
    assert request["decision_fingerprint_sha256"] == harness["decision"]["decision_fingerprint_sha256"]
    assert request["image"]["sha256"] == _sha(harness["image_path"])
    assert request["identity_reference_set_sha256"] == harness["reference_set_sha"]
    assert request["visual_model_authority"]["approved_model"] == "exact-test-model"
    assert "disposition" not in request["required_observation_keys"]


def test_missing_canonical_rubric_fails_before_provider(harness) -> None:
    calls = []
    harness["monkeypatch"].setattr(disposition, "_load_canonical_rubric", lambda commit: (_ for _ in ()).throw(
        disposition.BoundaryError("corrupt_or_untrusted_evidence", "rubric unavailable")
    ))
    harness["monkeypatch"].setattr(disposition, "call_anthropic_visual_review", lambda request: calls.append(request))
    result = _evaluate(harness, _all_pass())
    assert calls == []
    assert result["reason_codes"] == ["corrupt_or_untrusted_evidence"]


def test_real_reference_authority_rejects_uncommitted_and_wrong_sets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(disposition, "ROOT", tmp_path)
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda *args: True)
    reference = tmp_path / "refs" / "lena.png"
    reference.parent.mkdir()
    Image.new("RGB", (32, 32), "gray").save(reference)
    ref_sha = _sha(reference)
    authority_id = "committed_lena_reference_set_v1"
    set_sha = hashlib.sha256(selector._canonical_bytes({
        "authority_id": authority_id,
        "references": [{"path": "refs/lena.png", "sha256": ref_sha}],
    })).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "provider": "higgsfield", "provider_job_id": "ada3a4da-84ba-4f59-adce-0b31f51706a3",
        "provider_status": "completed", "job_type": "text2image_soul_v2",
        "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_sha = _sha(manifest_path)
    authority = {
        "schema_version": disposition.REFERENCE_AUTHORITY_SCHEMA_VERSION,
        "influencer_id": "lena", "authority_commit": "a" * 40, "authority_id": authority_id,
        "references": [{"path": "refs/lena.png", "sha256": ref_sha}], "reference_set_sha256": set_sha,
        "reference_metadata": [{
            "role": "canonical_face_hair_and_full_body", "format": "PNG", "width": 1152, "height": 2048,
            "provider": "higgsfield", "provider_job_id": "ada3a4da-84ba-4f59-adce-0b31f51706a3",
            "job_type": "text2image_soul_v2", "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
            "authority_scope": "identity_continuity_not_style", "provenance_manifest": "manifest.json",
            "provenance_manifest_sha256": manifest_sha, "provenance_manifest_git_blob_oid": "b" * 40,
        }],
    }
    authority_bytes = json.dumps(authority, separators=(",", ":")).encode()
    authority_path = tmp_path / "authority.json"
    authority_path.write_bytes(authority_bytes)
    def git_show(commit, path):
        if path.resolve() == authority_path.resolve():
            return authority_bytes
        if path.resolve() == reference.resolve():
            return reference.read_bytes()
        if path.resolve() == manifest_path.resolve():
            return manifest_path.read_bytes()
        raise disposition.BoundaryError("identity_evidence_invalid", "not committed")
    monkeypatch.setattr(disposition, "_git_show_bytes", git_show)
    monkeypatch.setattr(disposition, "_git_blob_oid", lambda *args: "b" * 40)
    monkeypatch.setattr(disposition, "_require_crlf_lf_equivalent", lambda *args: None)
    monkeypatch.setattr(disposition, "_validate_reference_metadata", lambda *args: None)
    refs, actual_set_sha, _ = disposition._validate_references(
        [(reference, ref_sha)], authority_path, hashlib.sha256(authority_bytes).hexdigest(), "a" * 40
    )
    assert refs[0]["authority_relative_path"] == "refs/lena.png"
    assert actual_set_sha == set_sha
    with pytest.raises(disposition.BoundaryError):
        disposition._validate_references([(reference, ref_sha)], authority_path, "0" * 64, "a" * 40)
    authority["reference_set_sha256"] = "0" * 64
    bad_bytes = json.dumps(authority, separators=(",", ":")).encode()
    authority_path.write_bytes(bad_bytes)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda commit, path: bad_bytes if path.resolve() == authority_path.resolve() else reference.read_bytes())
    with pytest.raises(disposition.BoundaryError):
        disposition._validate_references([(reference, ref_sha)], authority_path, hashlib.sha256(bad_bytes).hexdigest(), "a" * 40)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("live_attempt_count", True),
        ("live_attempt_count", 1.0),
        ("retry_count", False),
        ("retry_count", 0.0),
        ("live_attempt_count", -1),
        ("retry_count", -1),
    ],
)
def test_manifest_attempt_counters_require_exact_integers(harness, field, value) -> None:
    manifest = dict(harness["manifest"])
    manifest[field] = value
    _write_json(harness["manifest_path"], manifest)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["provenance_mismatch"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pose_body_language_id", "pose_p999"),
        ("pose_body_language_label", "swapped_pose"),
        ("wardrobe_outfit_id", "wc_swapped"),
        ("effective_wardrobe_silhouette_class", "swapped_silhouette"),
    ],
)
def test_manifest_context_must_match_signed_candidate(harness, field, value) -> None:
    manifest = dict(harness["manifest"])
    manifest[field] = value
    _write_json(harness["manifest_path"], manifest)
    result = _evaluate(harness, _all_pass())
    assert result["reason_codes"] == ["provenance_mismatch"]


def test_manifest_pose_and_expression_ids_must_match_committed_banks(monkeypatch) -> None:
    pose_bank = {"combos": [{"pose_body_language_id": "pose_p001", "label": "pose_label", "text": "pose text"}]}
    expression_bank = {"combos": [{"expression_gaze_id": "exp_g001", "label": "gaze_label", "text": "expression text"}]}
    wardrobe_catalog = {"outfits": [{"outfit_id": "wc_001", "name": "Canonical Outfit", "prompt": "canonical wardrobe prompt"}]}
    values = {
        disposition.POSE_BANK_PATH: json.dumps(pose_bank).encode(),
        disposition.EXPRESSION_BANK_PATH: json.dumps(expression_bank).encode(),
        disposition.WARDROBE_CATALOG_PATH: json.dumps(wardrobe_catalog).encode(),
        disposition.PROMPT_BRAIN_PATH: disposition.PROMPT_BRAIN_PATH.read_bytes(),
    }
    monkeypatch.setattr(
        disposition,
        "_git_show_bytes",
        lambda commit, path: values[path],
    )
    manifest = {
        "pose_body_language_id": "pose_p001", "pose_body_language_label": "pose_label", "pose_text": "pose text",
        "expression_gaze_id": "exp_g001", "expression_gaze_label": "gaze_label", "expression_text": "expression text",
        "expression_safe_fallback_used": False, "expression_safe_fallback_reason": None,
        "expression_scene_conflict_terms": [], "wardrobe_outfit_id": "wc_001",
        "wardrobe_outfit_name": "Canonical Outfit", "image_prompt": "Expression: expression text. Wardrobe: canonical wardrobe prompt.",
    }
    candidate = {"activity": "standing naturally"}
    disposition._validate_manifest_bank_context(manifest, candidate, "a" * 40)
    for field, changed in (
        ("pose_body_language_id", "pose_p999"),
        ("pose_body_language_label", "wrong"),
        ("pose_text", "wrong"),
        ("expression_gaze_id", "exp_g999"),
        ("expression_gaze_label", "wrong"),
    ):
        swapped = dict(manifest)
        swapped[field] = changed
        with pytest.raises(disposition.BoundaryError, match="manifest"):
            disposition._validate_manifest_bank_context(swapped, candidate, "a" * 40)


def _real_manifest_context(expression_id: str, activity: str) -> tuple[dict, dict]:
    expression_bank = json.loads(disposition._git_show_bytes("HEAD", disposition.EXPRESSION_BANK_PATH))
    expression = next(item for item in expression_bank["combos"] if item["expression_gaze_id"] == expression_id)
    wardrobe_catalog = json.loads(disposition._git_show_bytes("HEAD", disposition.WARDROBE_CATALOG_PATH))
    wardrobe = next(item for item in wardrobe_catalog["outfits"] if item["outfit_id"] == "wc_p006")
    expected = disposition.lena_prompt_brain._higgsfield_safe_expression_text(activity, expression)
    manifest = {
        "pose_body_language_id": "pose_p001", "pose_body_language_label": "weight_shift_one_hip",
        "pose_text": "weight shifted onto one hip, stance easy and unforced",
        "expression_gaze_id": expression_id, "expression_gaze_label": expression["label"],
        "expression_text": expected["text"], "expression_safe_fallback_used": expected["fallback_used"],
        "expression_safe_fallback_reason": expected["fallback_reason"],
        "expression_scene_conflict_terms": expected["conflict_terms"],
        "wardrobe_outfit_id": wardrobe["outfit_id"], "wardrobe_outfit_name": wardrobe["name"],
        "image_prompt": f"Scene: {activity}. Wardrobe: {wardrobe['prompt']}. Expression: {expected['text']}.",
    }
    return manifest, {"activity": activity}


def test_real_canonical_normal_expression_and_wardrobe_relationship_passes() -> None:
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expression_text", "standing naturally"),
        ("expression_safe_fallback_used", True),
        ("expression_safe_fallback_reason", "invented_reason"),
        ("wardrobe_outfit_id", "wc_unknown"),
        ("wardrobe_outfit_name", "standing naturally"),
    ],
)
def test_canonical_expression_and_wardrobe_relationship_mismatches_reject(field, value) -> None:
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    manifest[field] = value
    with pytest.raises(disposition.BoundaryError, match="manifest|wardrobe|expression"):
        disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


def test_documented_pose_conflict_fallback_relationship_passes_and_rejects_contradictions() -> None:
    manifest, candidate = _real_manifest_context("exp_g008", "walking naturally")
    assert manifest["expression_safe_fallback_used"] is True
    assert manifest["expression_safe_fallback_reason"] == "pose_conflict_id"
    disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")
    for field, value in (
        ("expression_text", "arbitrary fallback"),
        ("expression_safe_fallback_reason", None),
        ("expression_safe_fallback_reason", "invented_reason"),
        ("expression_scene_conflict_terms", ["invented conflict"]),
    ):
        contradicted = dict(manifest)
        contradicted[field] = value
        with pytest.raises(disposition.BoundaryError, match="expression fallback provenance"):
            disposition._validate_manifest_bank_context(contradicted, candidate, "HEAD")


def test_fallback_text_with_false_flag_rejects() -> None:
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    manifest["expression_text"] = disposition.lena_prompt_brain.HIGGSFIELD_EXPRESSION_SAFE_FALLBACK
    manifest["image_prompt"] += f" {manifest['expression_text']}"
    with pytest.raises(disposition.BoundaryError, match="expression fallback provenance"):
        disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


def test_swapped_valid_expression_and_wardrobe_ids_reject() -> None:
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    manifest["expression_gaze_id"] = "exp_g002"
    with pytest.raises(disposition.BoundaryError, match="expression"):
        disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    manifest["wardrobe_outfit_id"] = "wc_p003"
    with pytest.raises(disposition.BoundaryError, match="wardrobe"):
        disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


def test_documented_scene_conflict_fallback_terms_are_exact() -> None:
    activity = "looking out the window"
    manifest, candidate = _real_manifest_context("exp_g001", activity)
    assert manifest["expression_safe_fallback_reason"] == "scene_gaze_conflict"
    assert manifest["expression_scene_conflict_terms"]
    disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")
    manifest["expression_scene_conflict_terms"] = ["window"]
    with pytest.raises(disposition.BoundaryError, match="expression fallback provenance"):
        disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


def test_missing_expression_fallback_provenance_fields_reject(harness) -> None:
    for field in ("expression_safe_fallback_used", "expression_safe_fallback_reason", "expression_scene_conflict_terms"):
        manifest = dict(harness["manifest"])
        manifest.pop(field)
        _write_json(harness["manifest_path"], manifest)
        result = _evaluate(harness, _all_pass())
        assert result["reason_codes"] == ["provenance_mismatch"]


def test_upload_rehash_rejects_bytes_changed_after_validation(tmp_path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"validated bytes")
    item = {"path": str(image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    assert disposition._read_bound_image_bytes(item) == b"validated bytes"
    image.write_bytes(b"replacement bytes")
    with pytest.raises(disposition.BoundaryError, match="changed after validation"):
        disposition._read_bound_image_bytes(item)


def test_reference_authority_rejects_outside_repo_before_commit_lookup(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (16, 16), "gray").save(outside)
    monkeypatch.setattr(disposition, "ROOT", repo)
    monkeypatch.setattr(disposition, "_committed_json_authority", lambda *args, **kwargs: {
        "authority_commit": "b" * 40, "authority_id": "authority", "references": [], "reference_set_sha256": "0" * 64,
    })
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda *args: True)
    with pytest.raises(disposition.BoundaryError, match="repository-contained"):
        disposition._validate_references([(outside, _sha(outside))], repo / "authority.json", "1" * 64, "a" * 40)


def test_reference_authority_rejects_untracked_and_changed_local_bytes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(disposition, "ROOT", tmp_path)
    reference = tmp_path / "reference.png"
    Image.new("RGB", (16, 16), "gray").save(reference)
    expected_sha = _sha(reference)
    monkeypatch.setattr(disposition, "_committed_json_authority", lambda *args, **kwargs: {
        "authority_commit": "b" * 40, "authority_id": "authority", "references": [{"path": "reference.png", "sha256": expected_sha}],
        "reference_set_sha256": "0" * 64,
    })
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda *args: True)
    monkeypatch.setattr(
        disposition, "_git_show_bytes",
        lambda commit, path: (_ for _ in ()).throw(disposition.BoundaryError("identity_evidence_invalid", "not committed")),
    )
    with pytest.raises(disposition.BoundaryError, match="not committed"):
        disposition._validate_references([(reference, expected_sha)], tmp_path / "authority.json", "1" * 64, "a" * 40)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda commit, path: b"different committed bytes")
    with pytest.raises(disposition.BoundaryError, match="not hash-identical"):
        disposition._validate_references([(reference, expected_sha)], tmp_path / "authority.json", "1" * 64, "a" * 40)


def test_reference_authority_rejects_symlink_escape_when_supported(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (16, 16), "gray").save(outside)
    link = repo / "linked.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    monkeypatch.setattr(disposition, "ROOT", repo)
    monkeypatch.setattr(disposition, "_committed_json_authority", lambda *args, **kwargs: {
        "authority_commit": "b" * 40, "authority_id": "authority", "references": [], "reference_set_sha256": "0" * 64,
    })
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda *args: True)
    with pytest.raises(disposition.BoundaryError, match="repository-contained"):
        disposition._validate_references([(link, _sha(outside))], repo / "authority.json", "1" * 64, "a" * 40)
