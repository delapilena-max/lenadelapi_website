from __future__ import annotations

import pytest

import tools.lena_autonomy_runtime_evidence_v1 as runtime_evidence


@pytest.mark.parametrize(
    "parts",
    [
        ("2026-07-31", "lena_autonomy_daily_schedule_2026-07-31.json"),
        ("2026-07-31", "morning_state.json"),
        ("2026-07-31", "afternoon_skip_190829_593524.json"),
        ("2026-07-31", "evening_generation_failure_190829_593524.json"),
        ("2026-07-31", "morning_generation_190829_593524.json"),
        ("2026-07-31", "morning_generation_success_190829_593524.json"),
        ("2026-07-31", "evening_poll_201430_060159.json"),
    ],
)
def test_lena_autonomy_runtime_evidence_accepts_governed_artifact_shapes(parts: tuple[str, ...]) -> None:
    if parts[1].startswith("lena_autonomy_daily_schedule_"):
        assert runtime_evidence.daily_schedule_runtime_match(parts) is True
    else:
        assert runtime_evidence.scheduler_driver_runtime_match(parts) is True


@pytest.mark.parametrize(
    "parts",
    [
        ("2026-07-31", "random.json"),
        ("2026-07-31", "morning_runtime_fix.py"),
        ("2026-07-31", "morning_runtime_fix.ps1"),
        ("2026-07-31", "morning_helper.exe"),
        ("2026-07-31", ".env"),
        ("2026-07-31", "secrets.json"),
        ("2026-07-31", "config.json"),
        ("2026-13-31", "morning_state.json"),
        ("2026-07-31", "night_state.json"),
        ("2026-07-31", "morning_generation_190829.json"),
    ],
)
def test_lena_autonomy_runtime_evidence_rejects_unapproved_shapes(parts: tuple[str, ...]) -> None:
    assert runtime_evidence.scheduler_driver_runtime_match(parts) is False


def test_lena_autonomy_runtime_root_does_not_accept_arbitrary_subtrees() -> None:
    assert runtime_evidence.autonomy_runtime_match(("scheduler_driver", "2026-07-31", "morning_state.json")) is True
    assert runtime_evidence.autonomy_runtime_match(("unsafe", "2026-07-31", "morning_state.json")) is False
