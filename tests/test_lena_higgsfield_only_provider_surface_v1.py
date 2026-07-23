from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RETIRED_PROVIDER_FILES = (
    "pipeline/config/lena_kling_contract.json",
    "pipeline/identity/lena_identity.py",
    "pipeline/prompt_banks/lena/kling_omni_daily_scene_bank_v1.json",
    "pipeline/workorders/lena/README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md",
    "tools/generation/lena_apply_bodylock_to_daily_batch_v1.py",
    "tools/generation/lena_run_daily_bodylock_live_v1.py",
    "tools/generation/lena_run_daily_kling_omni_live_v1.py",
    "tools/strategy/lena_build_kling_payload_dryrun_v1.py",
    "tools/strategy/lena_submit_kling_payload_v1.py",
    "tools/run_lena_provider_only_daily_v1_5_2.py",
    "tools/wire_lena_v1_5_openart_seedance_provider.py",
    "tools/lena_daily_orchestrator_v1.py",
    "tools/lena_publish_packet_director_generate_v2_4.py",
    "tools/lena_influencer_node_v1_3.py",
    "tools/run_lena_generate_daily.ps1",
)

RETIRED_LIVE_TOKENS = (
    "api.klingai.com",
    "kling.ai/app",
    "kling_ak",
    "kling_sk",
    "kling_access_key",
    "kling_secret_key",
    "kling_apilena_api_executor",
    "kling_workorders",
    "kling_library",
    "kling_results",
    "kling_payload",
    "kling_contract",
    "kling_video",
    "kling_omni",
    "bodylock",
    "fromelementid",
    "elementversion",
    "openart",
    "seedance",
)


def test_retired_provider_entrypoints_are_absent() -> None:
    assert not [
        relative_path
        for relative_path in RETIRED_PROVIDER_FILES
        if (ROOT / relative_path).exists()
    ]


def test_active_provider_code_contains_no_retired_live_surface() -> None:
    roots = (
        ROOT / "pipeline" / "config",
        ROOT / "pipeline" / "identity",
        ROOT / "pipeline" / "prompting",
        ROOT / "tools",
    )
    candidates = [
        path
        for base in roots
        for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".json", ".md"}
    ]
    scheduler = ROOT / "setup_lena_3photo_scheduler_v1.ps1"
    if scheduler.exists():
        candidates.append(scheduler)

    violations: list[str] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8-sig").lower()
        for token in RETIRED_LIVE_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)}: {token}")

    assert violations == []


def test_generation_policy_is_higgsfield_only_and_video_is_disabled() -> None:
    policy = json.loads(
        (ROOT / "pipeline" / "config" / "lena_generation_policy.json").read_text(
            encoding="utf-8-sig"
        )
    )
    generation = policy["generation"]
    assert generation["image_engine"] == "higgsfield_text2image_soul_v2"
    assert generation["video_engine"] is None
    assert generation["video_generation_enabled"] is False
    assert policy["content_mix"]["daily_target"]["videos"] == 0
