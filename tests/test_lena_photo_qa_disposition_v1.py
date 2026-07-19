from __future__ import annotations

import base64
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
from tests.fixtures.lena_retry_lineage import build_retry_lineage
from tests.test_lena_bounded_live_cycle_v1 import _build_bundle as build_live_cycle_bundle
from tests.test_lena_bounded_live_cycle_v1 import _patch_clock as patch_live_cycle_clock
from tests.test_lena_bounded_live_cycle_v1 import _patch_roots as patch_live_cycle_roots
from tools import lena_photo_qa_disposition_v1 as disposition
from tools import lena_standing_autonomy_policy_v1 as standing_autonomy
from tools.strategy import lena_build_generation_reconciliation_v1 as reconciliation_builder
from tools.strategy import lena_reconciliation_contract_v1 as reconciliation_contract
from tools.strategy import lena_execute_selected_candidate_v1 as handoff
from tools.strategy import lena_execute_retry_decision_v1 as retry_handoff
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _write_png(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1, 1), "white").save(path)
    return _sha(path)


def _json_sha_without_keys(path: Path, excluded_keys: set[str]) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in excluded_keys:
        payload.pop(key, None)
    return hashlib.sha256((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8")).hexdigest()


def _json_sha_without_keys_payload(payload: dict, excluded_keys: set[str]) -> str:
    value = json.loads(json.dumps(payload, indent=2, ensure_ascii=True))
    for key in excluded_keys:
        value.pop(key, None)
    return hashlib.sha256((json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")).hexdigest()


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


RETRY_DATE = "2026-07-13"
RETRY_SLOT = "lenagate2026071325ca9e1d-pack000-01-retry01-photo"
RETRY_IMAGE_SHA = "aa25ba41d0a50f0261933f8f53bbe58d8183f0df37769c1a09655ad6c08de45c"
RETRY_DECISION = ROOT / "pipeline" / "strategy" / "lena" / "retry_decisions" / RETRY_DATE / (
    f"{RETRY_SLOT}__128799286987_retry_decision.json"
)
RETRY_MANIFEST = ROOT / "pipeline" / "higgsfield_debug" / RETRY_DATE / RETRY_SLOT / "result_manifest.json"
RETRY_IMAGE = ROOT / "pipeline" / "higgsfield_library" / "lena" / RETRY_DATE / f"{RETRY_SLOT}_seed.png"
RETRY_IDENTITY = ROOT / "pipeline" / "higgsfield_debug" / RETRY_DATE / RETRY_SLOT / "identity_verification.json"
REFERENCE_AUTHORITY = ROOT / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json"
MODEL_AUTHORITY = ROOT / "pipeline" / "identity" / "lena_visual_model_authority_v1.json"
REFERENCE_IMAGE = ROOT / "pipeline" / "higgsfield_library" / "lena" / "2026-07-09" / "prompt_isolation_tests" / "readypack0709-pack004-08-wardrobe-test-c_seed.png"


@pytest.fixture()
def retry_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    original_disposition_path = disposition.disposition_artifact_path
    original_validate_decision = disposition._validate_decision
    original_inspect_image = disposition._inspect_image
    original_validate_manifest = disposition._validate_manifest
    lineage = build_retry_lineage(tmp_path, monkeypatch)
    monkeypatch.setattr(disposition, "disposition_artifact_path", original_disposition_path)
    monkeypatch.setattr(disposition, "_validate_decision", original_validate_decision)
    monkeypatch.setattr(disposition, "_inspect_image", original_inspect_image)
    monkeypatch.setattr(disposition, "_validate_manifest", original_validate_manifest)
    reference_path = lineage["reference_path"]
    reference_set_sha = hashlib.sha256(
        selector._canonical_bytes(
            {
                "authority_id": "synthetic_test_reference_authority",
                "references": [{"path": str(reference_path.resolve()), "sha256": _sha(reference_path)}],
            }
        )
    ).hexdigest()

    def synthetic_reference_authority(specs, authority_path, authority_sha, authority_commit):
        supplied = list(specs)
        if authority_path != lineage["reference_authority_artifact"].resolve() or authority_sha != "1" * 64:
            raise disposition.BoundaryError("identity_evidence_invalid", "synthetic authority evidence rejected")
        if supplied != [(reference_path, _sha(reference_path))]:
            raise disposition.BoundaryError("identity_evidence_invalid", "synthetic authority rejected reference set")
        return (
            [
                {
                    "path": str(reference_path.resolve()),
                    "sha256": _sha(reference_path),
                    "format": "PNG",
                    "width": 64,
                    "height": 64,
                }
            ],
            reference_set_sha,
            {
                "authority_id": "synthetic_test_reference_authority",
                "authority_artifact_path": str(lineage["reference_authority_artifact"]),
                "authority_artifact_sha256": "1" * 64,
                "authority_commit": "a" * 40,
            },
        )

    monkeypatch.setattr(disposition, "_validate_references", synthetic_reference_authority)
    monkeypatch.setattr(
        identity,
        "identity_verification_evidence_path",
        lambda date, slot: lineage["identity_evidence_path"],
    )
    monkeypatch.setattr(
        disposition,
        "_validate_model_authority",
        lambda *args: {
            "path": str(lineage["model_authority_artifact"]),
            "sha256": "2" * 64,
            "provider": "anthropic",
            "approved_model": "exact-test-model",
        },
    )
    monkeypatch.setattr(
        disposition,
        "_load_canonical_rubric",
        lambda commit: {
            "authority_commit": commit,
            "required_semantic_dimensions": {
                "identity": ["face"],
                "character_fit": ["confident"],
            },
        },
    )
    monkeypatch.setattr(disposition, "_validate_manifest_bank_context", lambda manifest, candidate, commit: None)
    lineage["reference_set_sha"] = reference_set_sha
    return lineage


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


def _production_dual_binding_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> dict[str, Path | dict | str]:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    handoff_path = Path(bundle["handoff_path"])
    auth_path = Path(bundle["auth_path"])
    image_path = Path(bundle["image_path"])
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (identity.EXPECTED_WIDTH, identity.EXPECTED_HEIGHT), "white").save(image_path)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    prompt_source = json.loads(
        (ROOT / "pipeline" / "strategy" / "lena" / "next_actions" / "2026-07-17" / "lena_next_live_image_handoff_2026-07-17.json").read_text(encoding="utf-8")
    )
    selected_prompt_text = str(prompt_source["structured_executor_inputs"]["selected_prompt_text"])
    canonical_pose_text = "weight shifted onto one hip, stance easy and unforced"
    canonical_expression = disposition.lena_prompt_brain._higgsfield_safe_expression_text(
        "",
        {
            "label": "closed_mouth_smile_direct",
            "text": "closed-mouth smile, soft direct eye contact, slight head tilt",
        },
    )
    wardrobe_catalog = json.loads(
        (ROOT / "pipeline" / "prompt_banks" / "lena" / "lena_wardrobe_catalog_v1.json").read_text(encoding="utf-8")
    )
    wardrobe_prompt = next(item["prompt"] for item in wardrobe_catalog["outfits"] if item["outfit_id"] == "wc_p050")
    reference_authority_commit = disposition.subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    provider_prompt_text = (
        f"{selected_prompt_text} Pose: {canonical_pose_text}. "
        f"Expression: {canonical_expression['text']}. Wardrobe: {wardrobe_prompt}"
    )
    provider_prompt_sha = hashlib.sha256(provider_prompt_text.encode("utf-8")).hexdigest()
    auth["influencer_id"] = "lena"
    auth["authority_commit"] = reference_authority_commit
    date_str = str(auth["date"])
    candidate_source = dict(bundle["candidate"])
    candidate_source["authority_commit"] = reference_authority_commit
    candidate_source.update({
        "pose_body_language_id": "pose_p001",
        "pose_body_language_label": "weight_shift_one_hip",
        "pose": "weight_shift_one_hip",
        "pose_text": canonical_pose_text,
        "expression_text": canonical_expression["text"],
        "expression_gaze_id": "exp_g001",
        "expression_gaze_label": "closed_mouth_smile_direct",
        "wardrobe_outfit_id": "wc_p050",
        "wardrobe_outfit_name": "Dusty Rose Off-Shoulder Knit Top + Stone-Wash Straight Jeans",
        "wardrobe_silhouette_class": "fitted_top_and_jeans",
        "effective_wardrobe_silhouette_class": "fitted_top_and_jeans",
        "visual_style": "fitted_top_and_jeans",
        "image_format_detected": ".png",
    })
    candidate_source["prompt_sha256"] = provider_prompt_sha
    candidate_path = Path(bundle["candidate_path"])
    resolved_candidate_path = str(candidate_path.resolve())
    authorities = selector.load_authorities()
    recent = selector.load_recent_content()
    prompt_candidates, prompt_meta = selector.build_prompt_candidates(date_str, str(candidate_source["authority_commit"])[:8])
    rejected_candidates = []
    candidate_body = dict(candidate_source)
    candidate_file_core = selector._decision_core(
        str(candidate_source["authority_commit"]),
        date_str,
        authorities,
        candidate_source,
        rejected_candidates,
        recent,
        prompt_meta,
    )
    candidate_file = dict(candidate_file_core)
    candidate_file["generated_at_utc"] = "2026-07-19T00:00:00Z"
    candidate_file["decision_fingerprint_sha256"] = hashlib.sha256(selector._canonical_bytes(candidate_file_core)).hexdigest()
    _write_json(candidate_path, candidate_file)
    candidate_sha = _sha(candidate_path)
    handoff["repo_executor_path"] = "pipeline/higgsfield_lena_api_executor.py"
    handoff["created_at"] = "2026-07-19T00:00:00Z"
    handoff["influencer_id"] = "lena"
    handoff["selected_candidate_sha256"] = candidate_sha
    handoff["source_selected_candidate_artifact_path"] = resolved_candidate_path
    handoff["source_selected_candidate_artifact_sha256"] = candidate_sha
    selected_candidate = dict(candidate_body)
    selected_candidate["influencer_id"] = "lena"
    selected_candidate["artifact_path"] = resolved_candidate_path
    selected_candidate["artifact_sha256"] = candidate_sha
    selected_candidate["schema_version"] = "lena_pre_generation_candidate_gate_v1"
    selected_candidate["candidate_status"] = "selected"
    handoff["selected_candidate"] = selected_candidate
    selected_prompt_input = dict(handoff["selected_prompt_input"])
    selected_prompt_input["slot_id"] = str(handoff["selected_slot_id"])
    selected_prompt_input["selected_candidate_artifact_path"] = resolved_candidate_path
    selected_prompt_input["selected_candidate_artifact_sha256"] = candidate_sha
    selected_prompt_input["prompt_text"] = provider_prompt_text
    selected_prompt_input["selected_prompt_text"] = provider_prompt_text
    selected_prompt_input["prompt_sha256"] = provider_prompt_sha
    handoff["selected_prompt_input"] = selected_prompt_input
    structured_executor_inputs = dict(handoff["structured_executor_inputs"])
    structured_executor_inputs["slot_id"] = str(handoff["selected_slot_id"])
    structured_executor_inputs["handoff_artifact_path"] = handoff_path.relative_to(tmp_path).as_posix()
    structured_executor_inputs["selected_candidate_artifact_path"] = resolved_candidate_path
    structured_executor_inputs["selected_candidate_artifact_sha256"] = candidate_sha
    structured_executor_inputs["selected_prompt_text"] = provider_prompt_text
    structured_executor_inputs["selected_prompt_sha256"] = provider_prompt_sha
    structured_executor_inputs["soul_metadata"] = {
        "name": "Lena",
        "type": "Soul 2.0",
        "custom_reference_id": str(auth["custom_reference_id"]),
        "identity_is_prompt_instruction": False,
    }
    handoff["structured_executor_inputs"] = structured_executor_inputs
    learning_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_post_outcome_learning_state_{date_str}.json"
    recommendation_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_next_generation_step_{date_str}.json"
    candidate_selection_binding = dict(handoff["candidate_selection_binding"])
    candidate_selection_binding["selected_candidate_artifact_path"] = resolved_candidate_path
    candidate_selection_binding["selected_candidate_artifact_sha256"] = candidate_sha
    candidate_selection_binding["candidate_prompt_sha256"] = provider_prompt_sha
    handoff["candidate_selection_binding"] = candidate_selection_binding
    binding_linkage = dict(handoff["binding_linkage"])
    binding_linkage["selected_candidate_artifact_path"] = resolved_candidate_path
    binding_linkage["selected_candidate_artifact_sha256"] = candidate_sha
    binding_linkage["recommendation_artifact_sha256"] = _sha(recommendation_path)
    handoff["binding_linkage"] = binding_linkage
    handoff["expected_handoff_artifact_path"] = handoff_path.relative_to(tmp_path).as_posix()
    monkeypatch.setattr(reconciliation_builder, "ROOT", tmp_path)
    monkeypatch.setattr(reconciliation_contract, "ROOT", tmp_path)
    learning = json.loads(learning_path.read_text(encoding="utf-8"))
    learning["learning_status"] = "current"
    learning["learning_required_follow_up_action"] = "build_next_live_image_handoff"
    _write_json(learning_path, learning)
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
    recommendation["learning_status"] = "current"
    _write_json(recommendation_path, recommendation)
    binding_linkage["recommendation_artifact_sha256"] = _sha(recommendation_path)
    reconciliation_path = tmp_path / "pipeline" / "strategy" / "lena" / "reconciliations" / date_str / "lena_generation_reconciliation_fixture.json"
    reconciliation_report = {
        "report_type": "lena_generation_reconciliation",
        "schema_version": "lena_generation_reconciliation_v1",
        "date": date_str,
        "generated_at": "2026-07-19T00:00:00Z",
        "source_revision": candidate_body["authority_commit"][:8],
        "source_revision_commit": candidate_body["authority_commit"],
        "source_artifacts": {
            "learning": {
                "source_artifact_path": str(learning_path.relative_to(tmp_path)).replace("\\", "/"),
                "source_artifact_present": True,
                "source_artifact_sha256": _sha(learning_path),
                "source_report_type": learning["report_type"],
                "source_schema_version": learning["version"],
                "source_date": date_str,
            },
            "recommendation": {
                "source_artifact_path": str(recommendation_path.relative_to(tmp_path)).replace("\\", "/"),
                "source_artifact_present": True,
                "source_artifact_sha256": _sha(recommendation_path),
                "source_report_type": recommendation["report_type"],
                "source_schema_version": recommendation["version"],
                "source_date": date_str,
            },
            "selected_candidate": {
                "source_artifact_path": str(candidate_path.relative_to(tmp_path)).replace("\\", "/"),
                "source_artifact_present": True,
                "source_artifact_sha256": candidate_sha,
                "source_report_type": candidate_file["schema_version"],
                "source_schema_version": candidate_file["schema_version"],
                "source_date": date_str,
            },
        },
        "learning_status": learning["learning_status"],
        "recommendation_recipe_id": candidate_body["recipe_id"],
        "recommendation_outfit_id": "wc_p059",
        "recommendation_environment_id": "env_p001",
        "recommendation_action_type": "build_next_live_image_handoff",
        "recommendation_learning_signal_used": "queue_boosts",
        "selected_candidate_id": candidate_body["candidate_id"],
        "selected_candidate_recipe_id": candidate_body["recipe_id"],
        "selected_candidate_slot_id": candidate_body["slot_id"],
        "selected_candidate_hook_id": candidate_body["hook_id"],
        "selected_candidate_prompt_sha256": candidate_body["prompt_sha256"],
        "selected_candidate_authority_commit": candidate_body["authority_commit"],
        "selected_candidate_schema_version": "lena_pre_generation_candidate_gate_v1",
        "selected_candidate_status": "selected",
        "ranking_evidence": {
            "learning_status": learning["learning_status"],
            "learning_required_follow_up_action": learning["learning_required_follow_up_action"],
            "preferred_recipe_ids": [candidate_body["recipe_id"]],
            "recommended_recipe_rank_index": 0,
            "selected_candidate_recipe_rank_index": 0,
            "recommended_recipe_is_preferred": True,
            "selected_candidate_recipe_is_preferred": True,
        },
        "compatibility_evidence": {
            "recipe_match": True,
            "selected_candidate_status": "selected",
            "selected_candidate_body_present": True,
            "recommended_recipe_id": candidate_body["recipe_id"],
            "recommended_outfit_id": "wc_p059",
            "recommended_environment_id": "env_p001",
            "selected_candidate_recipe_id": candidate_body["recipe_id"],
            "selected_candidate_slot_id": candidate_body["slot_id"],
            "selected_candidate_id": candidate_body["candidate_id"],
            "selected_candidate_hook_id": candidate_body["hook_id"],
            "selected_candidate_prompt_sha256": candidate_body["prompt_sha256"],
            "selected_candidate_authority_commit": candidate_body["authority_commit"],
            "selected_candidate_schema_version": "lena_pre_generation_candidate_gate_v1",
            "recommendation_learning_signal_used": "queue_boosts",
        },
        "blocking_reasons": [],
        "divergence_status": "aligned",
        "resolution_policy": "selected_candidate_authoritative",
        "reconciliation_status": "reconciled",
        "operator_review_required": False,
        "final_reconciled_candidate_id": candidate_body["candidate_id"],
        "final_reconciled_candidate_recipe_id": candidate_body["recipe_id"],
        "final_reconciled_candidate_slot_id": candidate_body["slot_id"],
        "final_reconciled_candidate_hook_id": candidate_body["hook_id"],
        "final_reconciled_candidate_prompt_sha256": candidate_body["prompt_sha256"],
        "final_reconciled_candidate_artifact_path": str(candidate_path.relative_to(tmp_path)).replace("\\", "/"),
        "final_reconciled_candidate_artifact_sha256": candidate_sha,
        "exact_next_allowed_action": "build_next_live_image_handoff",
        "next_allowed_action": {
            "action": "build_next_live_image_handoff",
            "status": "reconciled",
        },
        "dirty_workspace_dependency": False,
        "shadow_mode_only": True,
        "provider_call_performed": False,
        "approval_consumed": False,
        "claims_written": False,
        "receipts_written": False,
        "queue_mutated": False,
        "publish_performed": False,
    }
    _write_json(reconciliation_path, reconciliation_report)
    reconciliation_sha = _sha(reconciliation_path)
    handoff["source_learning_artifact_path"] = str(learning_path.relative_to(tmp_path)).replace("\\", "/")
    handoff["source_learning_artifact_sha256"] = _sha(learning_path)
    handoff["source_recommendation_artifact_path"] = str(recommendation_path.relative_to(tmp_path)).replace("\\", "/")
    handoff["source_recommendation_artifact_sha256"] = _sha(recommendation_path)
    queue_path = tmp_path / "pipeline" / "strategy" / "lena" / "next_actions" / date_str / f"lena_autonomous_generation_queue_dryrun_{date_str}.json"
    handoff["source_queue_dry_run_artifact_path"] = str(queue_path.relative_to(tmp_path)).replace("\\", "/")
    handoff["source_queue_dry_run_artifact_sha256"] = _sha(queue_path)
    handoff["source_reconciliation_artifact_path"] = str(reconciliation_path)
    handoff["source_reconciliation_artifact_sha256"] = reconciliation_sha
    handoff["prompt_sha256"] = provider_prompt_sha
    handoff["prompt_text"] = provider_prompt_text
    handoff["provider_execution_binding"]["provider_prompt_sha256"] = provider_prompt_sha
    handoff["structured_executor_inputs"]["selected_prompt_text"] = provider_prompt_text
    handoff["structured_executor_inputs"]["selected_prompt_sha256"] = provider_prompt_sha
    reference_manifest_path = (
        ROOT
        / "pipeline"
        / "higgsfield_debug"
        / "2026-07-09"
        / "prompt_isolation_tests"
        / "readypack0709-pack004-08-wardrobe-test-c"
        / "result_manifest.json"
    )
    reference_manifest = {
        "provider": "higgsfield",
        "provider_job_id": "ada3a4da-84ba-4f59-adce-0b31f51706a3",
        "provider_status": "completed",
        "job_type": identity.EXPECTED_JOB_TYPE,
        "custom_reference_id": str(auth["custom_reference_id"]),
    }
    _write_json(reference_manifest_path, reference_manifest)
    request.addfinalizer(lambda: reference_manifest_path.unlink() if reference_manifest_path.exists() else None)
    reference_authority_path = tmp_path / "pipeline" / "identity" / "lena_visual_reference_authority_v1.json"
    reference_image_path = REFERENCE_IMAGE
    reference_manifest_sha = _sha(reference_manifest_path)
    reference_manifest_oid = "616f2d524153abbd3bb73fdcaf29530af83c0334"
    synthetic_reference_authority = {
        "schema_version": "lena_identity_reference_authority_v1",
        "influencer_id": "lena",
        "authority_id": "lena_visual_reference_authority_v1",
        "authority_commit": reference_authority_commit,
        "created_at_utc": "2026-07-19T00:00:00Z",
        "reference_set_sha256": hashlib.sha256(
            selector._canonical_bytes(
                {
                    "authority_id": "lena_visual_reference_authority_v1",
                    "references": [
                        {
                            "path": REFERENCE_IMAGE.relative_to(ROOT).as_posix(),
                            "sha256": _sha(REFERENCE_IMAGE),
                        }
                    ],
                }
            )
        ).hexdigest(),
        "references": [
            {
                "path": REFERENCE_IMAGE.relative_to(ROOT).as_posix(),
                "sha256": _sha(REFERENCE_IMAGE),
            }
        ],
        "reference_metadata": [
            {
                "role": "canonical_face_hair_and_full_body",
                "format": "PNG",
                "width": 1152,
                "height": 2048,
                "provider": "higgsfield",
                "provider_job_id": "ada3a4da-84ba-4f59-adce-0b31f51706a3",
                "job_type": "text2image_soul_v2",
                "custom_reference_id": "90a293d7-f3af-4377-8751-3304a27b6f31",
                "provenance_manifest": "pipeline/higgsfield_debug/2026-07-09/prompt_isolation_tests/readypack0709-pack004-08-wardrobe-test-c/result_manifest.json",
                "provenance_manifest_sha256": reference_manifest_sha,
                "provenance_manifest_git_blob_oid": reference_manifest_oid,
                "authority_scope": "identity_continuity_not_style",
                "authoritative_traits": [
                    "face_continuity",
                    "hair_continuity",
                    "apparent_age",
                    "skin_and_freckle_continuity",
                    "body_silhouette_continuity",
                    "overall_lena_identity_continuity",
                ],
                "non_authoritative_traits": [
                    "night_lighting",
                    "makeup",
                    "wardrobe",
                    "pose",
                    "scene",
                    "background",
                    "glamour_intensity",
                ],
            }
        ],
    }
    _write_json(reference_authority_path, synthetic_reference_authority)
    reference_authority_bytes = reference_authority_path.read_bytes()
    reference_image_bytes = reference_image_path.read_bytes()
    reference_manifest_bytes = reference_manifest_path.read_bytes()
    original_git_show_bytes = disposition._git_show_bytes
    original_git_blob_oid = disposition._git_blob_oid

    def synthetic_git_show_bytes(commit: str, path: Path) -> bytes:
        resolved = Path(path).resolve()
        if resolved == reference_authority_path.resolve():
            return reference_authority_bytes
        if resolved == reference_image_path.resolve():
            return reference_image_bytes
        if resolved == reference_manifest_path.resolve():
            return reference_manifest_bytes
        return original_git_show_bytes(commit, path)

    def synthetic_git_blob_oid(commit: str, path: Path) -> str:
        if Path(path).resolve() == reference_manifest_path.resolve():
            return reference_manifest_oid
        return original_git_blob_oid(commit, path)

    monkeypatch.setattr(disposition, "_git_show_bytes", synthetic_git_show_bytes)
    monkeypatch.setattr(disposition, "_git_blob_oid", synthetic_git_blob_oid)
    _write_json(handoff_path, handoff)
    handoff_sha = _sha(handoff_path)
    auth["consumed"] = True
    auth["authorization_consumed"] = True
    auth["consumed_at_utc"] = "2026-07-19T00:00:00Z"
    auth["authorization_state_before"] = {"single_use": True, "consumed": False, "consumed_at_utc": None}
    auth["authorization_state_after"] = {"single_use": True, "consumed": True, "consumed_at_utc": "2026-07-19T00:00:00Z"}
    auth["candidate_artifact_path"] = resolved_candidate_path
    auth["candidate_artifact_sha256"] = candidate_sha
    auth["prompt_sha256"] = provider_prompt_sha
    auth["provider_execution_binding"]["provider_prompt_sha256"] = provider_prompt_sha
    auth["generation_handoff_artifact_sha256"] = handoff_sha
    auth.pop("authorization_artifact_sha256", None)
    _write_json(auth_path, auth)
    auth["authorization_artifact_sha256"] = standing_autonomy._sha256_json_without_keys(auth_path, {"authorization_artifact_sha256"})
    _write_json(auth_path, auth)
    prompt_text = provider_prompt_text
    provider_binding = dict(handoff["provider_execution_binding"])
    date_str = str(auth["date"])
    slot_id = str(auth["slot_id"])
    manifest_path = tmp_path / "pipeline" / "higgsfield_debug" / date_str / slot_id / "result_manifest.json"
    manifest = {
        "report_type": "lena_higgsfield_result_manifest",
        "schema_version": "v1",
        "provider": "higgsfield",
        "job_type": identity.EXPECTED_JOB_TYPE,
        "date": date_str,
        "slot_id": slot_id,
        "lane": provider_binding["provider_lane"],
        "prompt_sha256": provider_prompt_sha,
        "image_prompt": prompt_text,
        "pose_body_language_id": "pose_p001",
        "pose_body_language_label": "weight_shift_one_hip",
        "pose_text": canonical_pose_text,
        "expression_text": canonical_expression["text"],
        "expression_safe_fallback_used": False,
        "expression_safe_fallback_reason": None,
        "expression_scene_conflict_terms": [],
        "expression_gaze_id": "exp_g001",
        "expression_gaze_label": "closed_mouth_smile_direct",
        "wardrobe_outfit_id": "wc_p050",
        "wardrobe_outfit_name": "Dusty Rose Off-Shoulder Knit Top + Stone-Wash Straight Jeans",
        "wardrobe_silhouette_class": "fitted_top_and_jeans",
        "effective_wardrobe_silhouette_class": "fitted_top_and_jeans",
        "custom_reference_id": str(auth["custom_reference_id"]),
        "cli_soul_name": identity.EXPECTED_SOUL_NAME,
        "cli_soul_type": identity.EXPECTED_SOUL_TYPE,
        "provider_job_id": "job-123",
        "provider_status": "completed",
        "saved_image_path": str(image_path),
        "live_attempt_count": 1,
        "retry_count": 0,
        "image_format_detected": ".png",
    }
    _write_json(manifest_path, manifest)
    evidence_path = identity.identity_verification_evidence_path(date_str, slot_id)
    evidence = {
        "schema_version": identity.SCHEMA_VERSION,
        "verified_at_utc": "2026-07-19T00:00:00Z",
        "provider": "higgsfield",
        "date": date_str,
        "slot_id": slot_id,
        "provider_job_id": "job-123",
        "provider_job_status": "completed",
        "job_type": identity.EXPECTED_JOB_TYPE,
        "custom_reference_id": str(auth["custom_reference_id"]),
        "soul_name": identity.EXPECTED_SOUL_NAME,
        "soul_type": identity.EXPECTED_SOUL_TYPE,
        "prompt_sha256": candidate_body["prompt_sha256"],
        "width": identity.EXPECTED_WIDTH,
        "height": identity.EXPECTED_HEIGHT,
        "local_image_path": str(image_path),
        "local_image_sha256": _sha(image_path),
        "local_image_sha256_provenance": "fixture local hash",
        "verification_result": "pass",
        "checks_passed": ["fixture"],
    }
    _write_json(evidence_path, evidence)
    return {
        "auth_path": auth_path,
        "manifest_path": manifest_path,
        "evidence_path": evidence_path,
        "image_path": image_path,
        "reference_authority_path": reference_authority_path,
        "reference_authority_sha": _sha(reference_authority_path),
        "reference_image_path": REFERENCE_IMAGE,
        "reference_image_sha": _sha(REFERENCE_IMAGE),
        "provider_lane": provider_binding["provider_lane"],
        "provider_prompt_sha256": provider_binding["provider_prompt_sha256"],
        "date": date_str,
        "slot_id": slot_id,
    }


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "argv", ["lena_photo_qa_disposition_v1.py", *argv])
    exit_code = disposition.main()
    report = json.loads(capsys.readouterr().out)
    return exit_code, report


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


def test_retry_lineage_reaches_no_provider_qa_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    retry_lineage: dict,
) -> None:
    monkeypatch.setattr(
        disposition,
        "_validate_manifest_bank_context",
        lambda manifest, candidate, commit: None,
    )
    result = disposition.evaluate_photo_qa_disposition(
        decision_path=retry_lineage["retry_decision_path"],
        manifest_path=retry_lineage["retry_manifest_path"],
        image_path=retry_lineage["image_path"],
        expected_image_sha256=retry_lineage["retry_image_sha"],
        identity_evidence_path=retry_lineage["identity_evidence_path"],
        reference_specs=[(retry_lineage["reference_path"], _sha(retry_lineage["reference_path"]))],
        reference_authority_artifact=retry_lineage["reference_authority_artifact"],
        reference_authority_sha256=retry_lineage["reference_authority_sha256"],
        failure_memory_loader=lambda: {
            "pattern_counts": {},
            "soft_flagged_patterns": [],
            "hard_excluded_patterns": [],
            "contributing_records": [],
            "skipped": [],
        },
    )
    assert result["reason_codes"] == ["visual_review_unavailable"]
    assert result["provider_called"] is False
    assert result["qa_inputs"]["decision_kind"] == "retry_decision"
    assert result["decision_fingerprint_sha256"] == retry_lineage["retry_decision"]["retry_decision_fingerprint_sha256"]
    assert result["generation_provenance"]["manifest_path"] == str(retry_lineage["retry_manifest_path"].resolve())


def test_original_selected_candidate_no_provider_behavior_is_unchanged(harness) -> None:
    result = _evaluate(harness)
    assert result["reason_codes"] == ["visual_review_unavailable"]
    assert result["provider_called"] is False
    assert result["qa_inputs"]["decision_kind"] == "selected_candidate"


def test_authorization_bound_manifest_uses_provider_binding(harness, tmp_path: Path) -> None:
    decision = dict(harness["decision"])
    candidate = dict(decision["candidate"])
    candidate["lane"] = "mirror outfit check"
    provider_prompt = (
        "Scene: standing naturally. Wardrobe: fixture outfit. "
        "Expression: calm expression. Provider lane: fit_check_mirror_getting_ready."
    )
    provider_prompt_sha = hashlib.sha256(provider_prompt.encode("utf-8")).hexdigest()
    manifest = dict(harness["manifest"])
    manifest["lane"] = "fit_check_mirror_getting_ready"
    manifest["prompt_sha256"] = provider_prompt_sha
    manifest["image_prompt"] = provider_prompt
    manifest_path = tmp_path / "provider-bound-manifest.json"
    _write_json(manifest_path, manifest)
    image = disposition._inspect_image(harness["image_path"], generated=True)
    provider_binding = {
        "provider_lane": "fit_check_mirror_getting_ready",
        "provider_prompt_sha256": provider_prompt_sha,
        "slot_id": harness["slot"],
    }

    result = disposition._validate_manifest(
        manifest_path,
        decision,
        candidate,
        image,
        "authorization_bound_handoff",
        provider_binding=provider_binding,
    )

    assert result["lane"] == "fit_check_mirror_getting_ready"
    assert result["prompt_sha256"] == provider_prompt_sha


def test_consumed_authorization_with_valid_dual_binding_reaches_qa_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    bundle = _production_dual_binding_fixture(tmp_path, monkeypatch, request)
    result = disposition.evaluate_photo_qa_disposition(
        decision_path=Path(bundle["auth_path"]),
        manifest_path=Path(bundle["manifest_path"]),
        image_path=Path(bundle["image_path"]),
        identity_evidence_path=Path(bundle["evidence_path"]),
        reference_specs=[(Path(bundle["reference_image_path"]), str(bundle["reference_image_sha"]))],
        reference_authority_artifact=Path(bundle["reference_authority_path"]),
        reference_authority_sha256=str(bundle["reference_authority_sha"]),
        expected_image_sha256=_sha(Path(bundle["image_path"])),
    )

    assert result["qa_inputs"]["decision_kind"] == "authorization_bound_handoff"
    assert result["provider_called"] is False
    assert result["generation_provenance"]["provider_execution_binding"]["provider_prompt_sha256"] == bundle["provider_prompt_sha256"]
    assert result["generation_provenance"]["provider_execution_binding"]["provider_lane"] == bundle["provider_lane"]
    assert result["generation_provenance"]["provider_job_id"] == "job-123"
    assert result["generation_provenance"]["manifest_path"] == str(Path(bundle["manifest_path"]).resolve())
    assert result["identity_reference_provenance"]["references"][0]["path"] == str(Path(bundle["reference_image_path"]).resolve())
    assert result["reason_codes"] == ["visual_review_unavailable"]


def test_consumed_authorization_with_invalid_linkage_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    bundle = _production_dual_binding_fixture(tmp_path, monkeypatch, request)
    auth_path = Path(bundle["auth_path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth.pop("candidate_selection_binding", None)
    auth.pop("authorization_artifact_sha256", None)
    _write_json(auth_path, auth)
    auth["authorization_artifact_sha256"] = standing_autonomy._sha256_json_without_keys(auth_path, {"authorization_artifact_sha256"})
    _write_json(auth_path, auth)

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        disposition.evaluate_photo_qa_disposition(
            decision_path=auth_path,
            manifest_path=Path(bundle["manifest_path"]),
            image_path=Path(bundle["image_path"]),
            identity_evidence_path=Path(bundle["evidence_path"]),
            reference_specs=[(Path(bundle["reference_image_path"]), str(bundle["reference_image_sha"]))],
            reference_authority_artifact=Path(bundle["reference_authority_path"]),
            reference_authority_sha256=str(bundle["reference_authority_sha"]),
            expected_image_sha256=_sha(Path(bundle["image_path"])),
        )

    assert exc_info.value.code == "authorization_candidate_selection_binding_missing"


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


def test_background_identity_duplication_is_deterministic_hard_failure(harness) -> None:
    result = _evaluate(harness, _failed("no_background_identity_duplication", "wrong_person_or_identity_collapse"))
    assert result["disposition"] == "hard_stop"
    assert result["reason_codes"] == ["wrong_person_or_identity_collapse"]
    assert result["hard_stop_reason"] == "wrong_person_or_identity_collapse"


def test_clean_background_identity_observation_can_proceed_normally(harness) -> None:
    observations = _all_pass()
    observations["observations"]["no_background_identity_duplication"] = {
        "status": "pass",
        "reason_codes": [],
        "notes": "background people are non-recognizable and clearly distinct from Lena",
    }
    result = _evaluate(harness, observations)
    assert result["disposition"] == "accept"
    assert result["reason_codes"] == []


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


def test_main_normalizes_uppercase_expected_image_sha_before_validation(harness, capsys) -> None:
    uppercase_sha = _sha(harness["image_path"]).upper()
    exit_code, report = _run_main(
        harness["monkeypatch"],
        [
            "--decision-artifact", str(harness["decision_path"]),
            "--manifest", str(harness["manifest_path"]),
            "--image", str(harness["image_path"]),
            "--expected-image-sha256", uppercase_sha,
            "--identity-evidence", str(harness["evidence_path"]),
            "--identity-reference-authority-artifact", str(harness["kwargs"]["reference_authority_artifact"]),
            "--identity-reference-authority-sha256", harness["kwargs"]["reference_authority_sha256"],
            "--identity-reference", f"{harness['reference_path']}::{_sha(harness['reference_path'])}",
        ],
        capsys,
    )
    assert exit_code == 1
    assert report["artifact"]["reason_codes"] == ["visual_review_unavailable"]
    assert report["artifact"]["image_sha256"] == _sha(harness["image_path"])
    assert report["artifact_write"] == {"requested": False, "written": False, "path": None}


def test_main_write_artifact_preserves_original_blocked_reason(harness, capsys) -> None:
    exit_code, report = _run_main(
        harness["monkeypatch"],
        [
            "--decision-artifact", str(harness["decision_path"]),
            "--manifest", str(harness["manifest_path"]),
            "--image", str(harness["image_path"]),
            "--expected-image-sha256", "0" * 64,
            "--identity-evidence", str(harness["evidence_path"]),
            "--identity-reference-authority-artifact", str(harness["kwargs"]["reference_authority_artifact"]),
            "--identity-reference-authority-sha256", harness["kwargs"]["reference_authority_sha256"],
            "--identity-reference", f"{harness['reference_path']}::{_sha(harness['reference_path'])}",
            "--write-artifact",
        ],
        capsys,
    )
    assert exit_code == 1
    assert report["artifact"]["reason_codes"] == ["image_hash_mismatch"]
    assert report["artifact"]["qa_inputs"]["binding_error"].startswith(
        "generated image SHA does not match explicit expected SHA"
    )
    assert report["artifact_write"] == {"requested": True, "written": False, "path": None}


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


def test_real_anthropic_adapter_includes_generated_and_reference_images_without_path_leak(
    harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls = []

    class FakeMessages:
        def create(self, **kwargs):
            provider_calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_visual_observations",
                        input=_all_pass(),
                    )
                ]
            )

    def fake_anthropic(**kwargs):
        return SimpleNamespace(messages=FakeMessages())

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=fake_anthropic))

    result = disposition.evaluate_photo_qa_disposition(
        decision_path=harness["decision_path"],
        manifest_path=harness["manifest_path"],
        image_path=harness["image_path"],
        identity_evidence_path=harness["evidence_path"],
        reference_specs=[(harness["reference_path"], _sha(harness["reference_path"]))],
        reference_authority_artifact=harness["kwargs"]["reference_authority_artifact"],
        reference_authority_sha256=harness["kwargs"]["reference_authority_sha256"],
        expected_image_sha256=_sha(harness["image_path"]),
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        visual_model_authority_artifact=harness["tmp_path"] / "model_authority.json",
        visual_model_authority_sha256="2" * 64,
        expected_decision_fingerprint=harness["decision"]["decision_fingerprint_sha256"],
        expected_reference_set_sha256=harness["reference_set_sha"],
        failure_memory_loader=lambda: harness["memory"],
    )

    assert result["disposition"] == "accept"
    assert len(provider_calls) == 1
    content = provider_calls[0]["messages"][0]["content"]
    text_payload = json.dumps(content, sort_keys=True)
    assert str(harness["image_path"].resolve()) not in text_payload
    assert str(harness["reference_path"].resolve()) not in text_payload
    image_blocks = [block for block in content if block["type"] == "image"]
    assert len(image_blocks) == 2
    assert base64.b64decode(image_blocks[0]["source"]["data"]) == harness["image_path"].read_bytes()
    assert base64.b64decode(image_blocks[1]["source"]["data"]) == harness["reference_path"].read_bytes()
    text_blocks = [block["text"] for block in content if block["type"] == "text"]
    assert any("generated_candidate" in text for text in text_blocks)
    assert any("identity_reference_1" in text for text in text_blocks)


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
    image_sha = _write_png(image_path)
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
        "image": {"path": str(image_path), "sha256": image_sha, "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    assert disposition.call_anthropic_visual_review(request) == observations
    assert client_options == [{"max_retries": 0}]
    assert len(provider_calls) == 1
    assert provider_calls[0]["model"] == disposition.APPROVED_VISUAL_MODEL
    tool = provider_calls[0]["tools"][0]
    assert tool["name"] == "submit_visual_observations"
    assert tool["input_schema"]["required"] == ["observations"]
    assert "schema_version" in tool["input_schema"]["properties"]


def test_anthropic_adapter_binds_schema_version_when_provider_omits_it(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "bound.png"
    image_sha = _write_png(image_path)
    observations = {"observations": _all_pass()["observations"]}

    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use", name="submit_visual_observations", input=observations,
            )])

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **kwargs: SimpleNamespace(messages=FakeMessages())))
    request = {
        "image": {"path": str(image_path), "sha256": image_sha, "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    result = disposition.call_anthropic_visual_review(request)
    assert result["schema_version"] == disposition.VISUAL_SCHEMA_VERSION
    assert result["observations"] == observations["observations"]


def test_anthropic_adapter_rejects_conflicting_echoed_schema_version_with_redacted_diagnostics(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "bound.png"
    image_sha = _write_png(image_path)
    payload = {"schema_version": "wrong_schema", "observations": _all_pass()["observations"]}

    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use", name="submit_visual_observations", input=payload,
            )])

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **kwargs: SimpleNamespace(messages=FakeMessages())))
    request = {
        "image": {"path": str(image_path), "sha256": image_sha, "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    with pytest.raises(disposition.BoundaryError, match="conflicting schema_version") as excinfo:
        disposition.call_anthropic_visual_review(request)
    text = str(excinfo.value)
    assert '"schema_version_matches_expected": false' in text
    assert "bound image bytes" not in text


def test_anthropic_adapter_non_dict_payload_reports_only_redacted_diagnostics(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "bound.png"
    image_sha = _write_png(image_path)

    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(
                type="tool_use", name="submit_visual_observations", input=["not", "a", "dict"],
            )])

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **kwargs: SimpleNamespace(messages=FakeMessages())))
    request = {
        "image": {"path": str(image_path), "sha256": image_sha, "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    with pytest.raises(disposition.BoundaryError, match="malformed structured observation payload") as excinfo:
        disposition.call_anthropic_visual_review(request)
    text = str(excinfo.value)
    assert '"input_type": "list"' in text
    assert "bound image bytes" not in text


def test_validator_still_rejects_missing_schema_version_outside_adapter() -> None:
    with pytest.raises(disposition.BoundaryError, match="missing or invalid schema_version"):
        disposition.validate_visual_observations({"observations": _all_pass()["observations"]})


def test_missing_duplicate_identity_observation_fails_closed() -> None:
    payload = _all_pass()
    payload["observations"].pop("no_background_identity_duplication")
    with pytest.raises(disposition.BoundaryError, match="exactly every required observation key"):
        disposition.validate_visual_observations(payload)


def test_malformed_duplicate_identity_observation_fails_closed() -> None:
    payload = _all_pass()
    payload["observations"]["no_background_identity_duplication"] = {
        "status": "fail",
        "reason_codes": ["recoverable_identity_drift"],
        "notes": "invalid reason for this observation",
    }
    with pytest.raises(disposition.BoundaryError, match="incompatible reason code"):
        disposition.validate_visual_observations(payload)


def test_anthropic_adapter_malformed_response_fails_without_retry(tmp_path, monkeypatch) -> None:
    image_path = tmp_path / "bound.png"
    image_sha = _write_png(image_path)
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
        "image": {"path": str(image_path), "sha256": image_sha, "format": "PNG"},
        "identity_references": [],
        "visual_model": disposition.APPROVED_VISUAL_MODEL,
    }
    with pytest.raises(disposition.BoundaryError, match="exactly one structured tool block"):
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


def test_legacy_pose_text_with_only_trailing_period_passes_committed_authority_check() -> None:
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    manifest["pose_text"] += "."
    disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


@pytest.mark.parametrize("value", [
    "weight shifted onto one hip, stance easy and unforced!",
    "Weight shifted onto one hip, stance easy and unforced",
    "weight shifted onto one hip, stance easy and unforced..",
    "weight shifted onto one hip, stance easy and unforced ",
])
def test_pose_text_only_allows_exact_legacy_trailing_period(value) -> None:
    manifest, candidate = _real_manifest_context("exp_g001", "standing naturally")
    manifest["pose_text"] = value
    with pytest.raises(disposition.BoundaryError, match="manifest pose ID, label, and text"):
        disposition._validate_manifest_bank_context(manifest, candidate, "HEAD")


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
    assert "no_background_identity_duplication" in request["required_observation_keys"]
    assert "background person" in request["instruction"].lower()
    assert "second lena-like identity" in json.dumps(request["scene_context"]).lower()


def test_tampered_retry_decision_fingerprint_fails_before_provider_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    retry_lineage: dict,
) -> None:
    tampered = tmp_path / retry_lineage["retry_decision_path"].name
    artifact = json.loads(retry_lineage["retry_decision_path"].read_text(encoding="utf-8-sig"))
    artifact["retry_decision_fingerprint_sha256"] = "0" * 64
    _write_json(tampered, artifact)
    calls: list[dict] = []
    monkeypatch.setattr(disposition, "call_anthropic_visual_review", lambda request: calls.append(request) or _all_pass())
    result = disposition.evaluate_photo_qa_disposition(
        decision_path=tampered,
        manifest_path=retry_lineage["retry_manifest_path"],
        image_path=retry_lineage["image_path"],
        expected_image_sha256=retry_lineage["retry_image_sha"],
        identity_evidence_path=retry_lineage["identity_evidence_path"],
        reference_specs=[(retry_lineage["reference_path"], _sha(retry_lineage["reference_path"]))],
        reference_authority_artifact=retry_lineage["reference_authority_artifact"],
        reference_authority_sha256=retry_lineage["reference_authority_sha256"],
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        visual_model_authority_artifact=retry_lineage["model_authority_artifact"],
        visual_model_authority_sha256=retry_lineage["model_authority_sha256"],
        expected_decision_fingerprint="0" * 64,
        expected_reference_set_sha256=retry_lineage["reference_set_sha"],
    )
    assert calls == []
    assert result["reason_codes"] == ["decision_binding_mismatch"]


def test_tampered_retry_manifest_fails_before_provider_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    retry_lineage: dict,
) -> None:
    tampered = tmp_path / "result_manifest.json"
    manifest = json.loads(retry_lineage["retry_manifest_path"].read_text(encoding="utf-8-sig"))
    manifest["retry_execution_contract"]["retry_decision_fingerprint_sha256"] = "0" * 64
    _write_json(tampered, manifest)
    calls: list[dict] = []
    monkeypatch.setattr(disposition, "call_anthropic_visual_review", lambda request: calls.append(request) or _all_pass())
    result = disposition.evaluate_photo_qa_disposition(
        decision_path=retry_lineage["retry_decision_path"],
        manifest_path=tampered,
        image_path=retry_lineage["image_path"],
        expected_image_sha256=retry_lineage["retry_image_sha"],
        identity_evidence_path=retry_lineage["identity_evidence_path"],
        reference_specs=[(retry_lineage["reference_path"], _sha(retry_lineage["reference_path"]))],
        reference_authority_artifact=retry_lineage["reference_authority_artifact"],
        reference_authority_sha256=retry_lineage["reference_authority_sha256"],
        live_visual_review=True,
        visual_provider="anthropic",
        visual_model="exact-test-model",
        visual_model_authority_artifact=retry_lineage["model_authority_artifact"],
        visual_model_authority_sha256=retry_lineage["model_authority_sha256"],
        expected_decision_fingerprint=retry_lineage["retry_decision"]["retry_decision_fingerprint_sha256"],
        expected_reference_set_sha256=retry_lineage["reference_set_sha"],
    )
    assert calls == []
    assert result["reason_codes"] == ["provenance_mismatch"]


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


def test_legacy_trailing_period_tolerance_still_requires_exact_pose_id_and_label(monkeypatch) -> None:
    pose_bank = {"combos": [{"pose_body_language_id": "pose_p001", "label": "pose_label", "text": "pose text"}]}
    expression_bank = {"combos": [{"expression_gaze_id": "exp_g001", "label": "gaze_label"}]}
    wardrobe_catalog = {"outfits": [{"outfit_id": "wc_001", "name": "Canonical Outfit", "prompt": "canonical wardrobe prompt"}]}
    values = {
        disposition.POSE_BANK_PATH: json.dumps(pose_bank).encode(),
        disposition.EXPRESSION_BANK_PATH: json.dumps(expression_bank).encode(),
        disposition.WARDROBE_CATALOG_PATH: json.dumps(wardrobe_catalog).encode(),
        disposition.PROMPT_BRAIN_PATH: disposition.PROMPT_BRAIN_PATH.read_bytes(),
    }
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda commit, path: values[path])
    manifest = {
        "pose_body_language_id": "pose_p001",
        "pose_body_language_label": "wrong-label",
        "pose_text": "pose text.",
        "expression_gaze_id": "exp_g001",
        "expression_gaze_label": "gaze_label",
        "expression_text": "expression text",
        "expression_safe_fallback_used": False,
        "expression_safe_fallback_reason": None,
        "expression_scene_conflict_terms": [],
        "wardrobe_outfit_id": "wc_001",
        "wardrobe_outfit_name": "Canonical Outfit",
        "image_prompt": "Expression: expression text. Wardrobe: canonical wardrobe prompt.",
    }
    with pytest.raises(disposition.BoundaryError, match="manifest pose ID, label, and text"):
        disposition._validate_manifest_bank_context(manifest, {"activity": "standing naturally"}, "a" * 40)


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
