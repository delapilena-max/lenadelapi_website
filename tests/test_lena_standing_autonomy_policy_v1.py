from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.test_lena_bounded_live_cycle_v1 import _build_bundle as build_live_cycle_bundle
from tests.test_lena_bounded_live_cycle_v1 import _patch_clock as patch_live_cycle_clock
from tests.test_lena_bounded_live_cycle_v1 import _patch_roots as patch_live_cycle_roots
from tools import lena_standing_autonomy_policy_v1 as standing_autonomy
from tools import lena_validate_autonomous_qa_mode_v1 as autonomous_qa_validator
from tools import lena_photo_qa_disposition_v1 as photo_qa


def _json_sha_without_keys(path: Path, excluded_keys: set[str]) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in excluded_keys:
        payload.pop(key, None)
    return standing_autonomy._sha256_bytes((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))


def _json_sha_without_keys_payload(payload: dict, excluded_keys: set[str]) -> str:
    value = json.loads(json.dumps(payload, indent=2, ensure_ascii=True))
    for key in excluded_keys:
        value.pop(key, None)
    return standing_autonomy._sha256_bytes((json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))


def _write_auth(auth_path: Path, auth: dict) -> None:
    auth["authorization_artifact_sha256"] = _json_sha_without_keys_payload(auth, {"authorization_artifact_sha256"})
    auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _expired_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(standing_autonomy, "_now_utc", lambda: datetime(2026, 7, 18, 3, 0, 0, tzinfo=timezone.utc))


def test_validate_cycle_authorization_artifact_rejects_consumed_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["consumed"] = True
    auth["authorization_consumed"] = True
    auth["consumed_at_utc"] = "2026-07-19T00:00:00Z"
    auth["authorization_state_before"] = {"single_use": True, "consumed": False, "consumed_at_utc": None}
    auth["authorization_state_after"] = {"single_use": True, "consumed": True, "consumed_at_utc": "2026-07-19T00:00:00Z"}
    auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    auth["authorization_artifact_sha256"] = _json_sha_without_keys(auth_path, {"authorization_artifact_sha256"})
    auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(auth_path)

    assert exc_info.value.code == "authorization_already_consumed"


def test_validate_cycle_authorization_artifact_accepts_consumed_in_read_only_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    pre_consumption_sha = standing_autonomy._sha256_file(auth_path)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["consumed"] = True
    auth["authorization_consumed"] = True
    auth["consumed_at_utc"] = "2026-07-19T00:00:00Z"
    auth["authorization_state_before"] = {"single_use": True, "consumed": False, "consumed_at_utc": None}
    auth["authorization_state_after"] = {"single_use": True, "consumed": True, "consumed_at_utc": "2026-07-19T00:00:00Z"}
    auth["cycle_authorization_sha256"] = pre_consumption_sha
    auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    handoff_report = json.loads(Path(bundle["handoff_path"]).read_text(encoding="utf-8"))
    result = standing_autonomy.validate_cycle_authorization_artifact(auth_path, allow_consumed=True, handoff_report=handoff_report)

    assert result["artifact"]["consumed"] is True
    assert result["artifact"]["authorization_consumed"] is True
    assert result["artifact"]["provider_execution_binding"]["provider_prompt_sha256"] == result["artifact"]["prompt_sha256"]
    assert result["artifact"]["candidate_selection_binding"]["candidate_id"] == result["artifact"]["candidate_selection_binding"]["candidate_id"]


def test_validate_cycle_authorization_artifact_rejects_consumed_without_cycle_authorization_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["consumed"] = True
    auth["authorization_consumed"] = True
    auth["consumed_at_utc"] = "2026-07-19T00:00:00Z"
    auth["authorization_state_before"] = {"single_use": True, "consumed": False, "consumed_at_utc": None}
    auth["authorization_state_after"] = {"single_use": True, "consumed": True, "consumed_at_utc": "2026-07-19T00:00:00Z"}
    auth.pop("cycle_authorization_sha256", None)
    auth["authorization_artifact_sha256"] = _json_sha_without_keys_payload(auth, {"authorization_artifact_sha256"})
    auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    handoff_report = json.loads(Path(bundle["handoff_path"]).read_text(encoding="utf-8"))

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(
            auth_path,
            allow_consumed=True,
            handoff_report=handoff_report,
        )

    assert exc_info.value.code == "authorization_sha_mismatch"


def test_default_validation_rejects_expired_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    _expired_now(monkeypatch)

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(auth_path)

    assert exc_info.value.code == "authorization_expired"


def test_default_validation_accepts_current_authorization_timing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)

    result = standing_autonomy.validate_cycle_authorization_artifact(Path(bundle["auth_path"]))

    assert result["artifact"]["slot_id"]


def test_historical_mode_accepts_expired_unconsumed_authorization_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    _expired_now(monkeypatch)

    result = standing_autonomy.validate_cycle_authorization_artifact(
        auth_path,
        allow_consumed=True,
        require_not_expired=False,
    )

    assert result["artifact"]["consumed"] is False
    assert result["artifact"]["authorization_consumed"] is False
    assert result["artifact"]["consumed_at_utc"] is None


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda auth, bundle: auth.__setitem__("issued_at_utc", "not-a-date"), "authorization_issued_at_invalid"),
        (lambda auth, bundle: auth.__setitem__("expires_at_utc", auth["issued_at_utc"]), "authorization_expiry_order_invalid"),
        (lambda auth, bundle: auth.__setitem__("authorization_artifact_sha256", "0" * 64), "authorization_sha_mismatch"),
        (lambda auth, bundle: auth.__setitem__("generation_handoff_artifact_sha256", "0" * 64), "handoff_sha_mismatch"),
        (lambda auth, bundle: auth.__setitem__("candidate_artifact_sha256", "0" * 64), "authorization_candidate_sha_mismatch"),
        (lambda auth, bundle: auth.__setitem__("provider", "Other"), "provider_mismatch"),
        (lambda auth, bundle: auth.__setitem__("policy_id", "wrong"), "policy_id_mismatch"),
    ],
)
def test_historical_mode_keeps_non_expiry_validation_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    expected_code: str,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    auth_path = Path(bundle["auth_path"])
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    mutate(auth, bundle)
    if expected_code != "authorization_sha_mismatch":
        _write_auth(auth_path, auth)
    else:
        auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    _expired_now(monkeypatch)
    policy_result = standing_autonomy.validate_policy_artifact(Path(bundle["policy_path"]))
    handoff_report = json.loads(Path(bundle["handoff_path"]).read_text(encoding="utf-8"))

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(
            auth_path,
            policy_result=policy_result,
            handoff_report=handoff_report,
            allow_consumed=True,
            require_not_expired=False,
        )

    assert exc_info.value.code == expected_code


def test_authorization_bound_photo_qa_context_allows_historical_expired_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    _expired_now(monkeypatch)
    handoff_report = json.loads(Path(bundle["handoff_path"]).read_text(encoding="utf-8"))
    monkeypatch.setattr(
        photo_qa.approval,
        "inspect_handoff_artifact",
        lambda _path, *, selected_candidate_freshness_mode=None: {
            "report": handoff_report,
            "selected_candidate_path": str(Path(bundle["candidate_path"]).resolve()),
        },
    )
    monkeypatch.setattr(
        photo_qa,
        "_validate_selected_decision",
        lambda _path, *, freshness_mode=photo_qa.handoff.FRESHNESS_MODE_CURRENT: (
            {"as_of_date": handoff_report["date"]},
            dict(bundle["candidate"]),
        ),
    )

    decision, candidate, decision_kind, binding_context = photo_qa._resolve_generation_binding_context(
        Path(bundle["auth_path"]).resolve()
    )

    assert decision_kind == "authorization_bound_handoff"
    assert candidate["slot_id"] == json.loads(Path(bundle["handoff_path"]).read_text(encoding="utf-8"))["selected_slot_id"]
    assert binding_context is not None


def test_only_authorization_bound_photo_qa_uses_historical_expiry_mode() -> None:
    matches: list[tuple[str, int]] = []
    for path in [Path("tools/lena_photo_qa_disposition_v1.py"), Path("tools/lena_bounded_live_cycle_v1.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "validate_cycle_authorization_artifact"
            ):
                continue
            for keyword in node.keywords:
                if keyword.arg == "require_not_expired" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                    matches.append((path.as_posix(), node.lineno))

    assert len(matches) == 2
    assert {path for path, _line in matches} == {"tools/lena_photo_qa_disposition_v1.py"}


# ---------------------------------------------------------------------------
# Focused tests for prompt-SHA resolution (validator seam fix)
# ---------------------------------------------------------------------------

WRONG_SHA = "a" * 64


def _load_handoff(bundle: dict) -> dict:
    import json as _json
    return _json.loads(
        (bundle["handoff_path"]).read_text(encoding="utf-8")
    )


def test_prompt_sha_resolution_current_nested_schema_accepted(
    tmp_path: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both nested SHAs present and agreeing, no top-level prompt_sha256 → passes."""
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    handoff_report = _load_handoff(bundle)
    # Remove top-level prompt_sha256 to simulate production handoff schema.
    handoff_report.pop("prompt_sha256", None)
    # Both nested locations remain: selected_prompt_input.prompt_sha256 and
    # structured_executor_inputs.selected_prompt_sha256 both equal PROMPT_SHA.
    assert handoff_report["selected_prompt_input"]["prompt_sha256"]
    assert handoff_report["structured_executor_inputs"]["selected_prompt_sha256"]

    result = standing_autonomy.validate_cycle_authorization_artifact(
        Path(bundle["auth_path"]),
        handoff_report=handoff_report,
    )

    assert result["artifact"] is not None


def test_prompt_sha_resolution_nested_sha_disagreement_fails_closed(
    tmp_path: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both nested SHAs present but disagreeing → fails closed."""
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    handoff_report = _load_handoff(bundle)
    handoff_report.pop("prompt_sha256", None)
    # Inject disagreement: nested cross-check has a different value.
    handoff_report["structured_executor_inputs"]["selected_prompt_sha256"] = WRONG_SHA

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(
            Path(bundle["auth_path"]),
            handoff_report=handoff_report,
        )

    assert exc_info.value.code == "authorization_provider_execution_prompt_sha_mismatch"


def test_prompt_sha_resolution_provider_binding_mismatch_fails_closed(
    tmp_path: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both nested SHAs agree with each other but not with auth provider binding → fails closed."""
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    handoff_report = _load_handoff(bundle)
    # Keep top-level so selected_prompt_sha_value resolves to the auth's own
    # prompt_sha256 (avoids authorization_prompt_sha_mismatch).
    # Set both nested SHAs to WRONG_SHA so they agree but mismatch provider binding.
    handoff_report["selected_prompt_input"]["prompt_sha256"] = WRONG_SHA
    handoff_report["structured_executor_inputs"]["selected_prompt_sha256"] = WRONG_SHA

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(
            Path(bundle["auth_path"]),
            handoff_report=handoff_report,
        )

    assert exc_info.value.code == "authorization_provider_execution_prompt_sha_mismatch"


def test_prompt_sha_resolution_legacy_top_level_accepted(
    tmp_path: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No nested SHAs, only legacy top-level prompt_sha256 → passes."""
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    handoff_report = _load_handoff(bundle)
    # Remove both nested locations; legacy top-level remains.
    handoff_report["selected_prompt_input"].pop("prompt_sha256", None)
    handoff_report["structured_executor_inputs"].pop("selected_prompt_sha256", None)
    assert "prompt_sha256" in handoff_report

    result = standing_autonomy.validate_cycle_authorization_artifact(
        Path(bundle["auth_path"]),
        handoff_report=handoff_report,
    )

    assert result["artifact"] is not None


def test_prompt_sha_resolution_missing_everywhere_fails_closed(
    tmp_path: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No prompt SHA in nested or top-level locations → fails closed."""
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch)
    handoff_report = _load_handoff(bundle)
    handoff_report.pop("prompt_sha256", None)
    handoff_report["selected_prompt_input"].pop("prompt_sha256", None)
    handoff_report["structured_executor_inputs"].pop("selected_prompt_sha256", None)

    with pytest.raises(standing_autonomy.StandingAutonomyPolicyError) as exc_info:
        standing_autonomy.validate_cycle_authorization_artifact(
            Path(bundle["auth_path"]),
            handoff_report=handoff_report,
        )

    assert exc_info.value.code == "authorization_provider_execution_prompt_sha_mismatch"


def test_controlled_qa_summary_reports_autonomous_local_without_external_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    bundle = build_live_cycle_bundle(tmp_path, monkeypatch, controlled=True)
    policy = json.loads(Path(bundle["policy_path"]).read_text(encoding="utf-8"))

    summary = standing_autonomy.summarize_controlled_qa_mode(policy)

    assert summary["configured_autonomous_qa_mode"] == standing_autonomy.AUTONOMOUS_QA_MODE
    assert summary["autonomous_external_visual_provider_required"] is False
    assert summary["external_visual_diagnostics_enabled"] is False
    assert summary["external_visual_diagnostic_authorization_required"] is True
    assert summary["human_review_mode"] == standing_autonomy.SUPERVISED_HUMAN_REVIEW_MODE
    assert summary["human_review_required_for_autonomous_operation"] is False
    assert summary["missing_required_local_safeguards"] == []


def test_autonomous_qa_validator_reports_expected_non_routine_external_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_live_cycle_roots(monkeypatch, tmp_path)
    patch_live_cycle_clock(monkeypatch)
    build_live_cycle_bundle(tmp_path, monkeypatch, controlled=True)

    report = autonomous_qa_validator._report()

    assert report["ok"] is True
    assert report["configured_autonomous_qa_mode"] == standing_autonomy.AUTONOMOUS_QA_MODE
    assert report["autonomous_external_visual_provider_required"] is False
    assert report["external_visual_diagnostics_enabled"] is False
    assert report["external_visual_diagnostic_authorization_required"] is True
    assert report["human_review_required_for_autonomous_operation"] is False
    assert report["missing_required_local_safeguards"] == []
