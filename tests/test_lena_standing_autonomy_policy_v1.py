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
