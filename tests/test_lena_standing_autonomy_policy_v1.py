from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_lena_bounded_live_cycle_v1 import _build_bundle as build_live_cycle_bundle
from tests.test_lena_bounded_live_cycle_v1 import _patch_clock as patch_live_cycle_clock
from tests.test_lena_bounded_live_cycle_v1 import _patch_roots as patch_live_cycle_roots
from tools import lena_standing_autonomy_policy_v1 as standing_autonomy


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
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    auth["consumed"] = True
    auth["authorization_consumed"] = True
    auth["consumed_at_utc"] = "2026-07-19T00:00:00Z"
    auth["authorization_state_before"] = {"single_use": True, "consumed": False, "consumed_at_utc": None}
    auth["authorization_state_after"] = {"single_use": True, "consumed": True, "consumed_at_utc": "2026-07-19T00:00:00Z"}
    auth["authorization_artifact_sha256"] = _json_sha_without_keys_payload(auth, {"authorization_artifact_sha256"})
    auth_path.write_text(json.dumps(auth, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    handoff_report = json.loads(Path(bundle["handoff_path"]).read_text(encoding="utf-8"))
    result = standing_autonomy.validate_cycle_authorization_artifact(auth_path, allow_consumed=True, handoff_report=handoff_report)

    assert result["artifact"]["consumed"] is True
    assert result["artifact"]["authorization_consumed"] is True
    assert result["artifact"]["provider_execution_binding"]["provider_prompt_sha256"] == result["artifact"]["prompt_sha256"]
    assert result["artifact"]["candidate_selection_binding"]["candidate_id"] == result["artifact"]["candidate_selection_binding"]["candidate_id"]


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
