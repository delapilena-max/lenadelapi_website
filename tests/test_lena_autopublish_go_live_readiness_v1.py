from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.lena_autopublish_go_live_readiness_v1 as readiness
import tools.publishers.lena_meta_publish_common_v2_9 as publish_common


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_env_tree(root: Path) -> None:
    _write_json(
        root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json",
        {
            "env_file_candidates": [".env"],
            "key_map": {
                "page_access_token": ["META_PAGE_ACCESS_TOKEN"],
                "instagram_access_token": ["META_INSTAGRAM_ACCESS_TOKEN"],
                "instagram_business_account_id": ["META_IG_USER_ID"],
                "facebook_page_id": ["META_FACEBOOK_PAGE_ID"],
                "graph_api_version": ["META_GRAPH_API_VERSION"],
                "media_public_base_url": ["LENA_MEDIA_PUBLIC_BASE_URL"],
                "media_public_local_dir": ["LENA_MEDIA_PUBLIC_LOCAL_DIR"],
            },
            "defaults": {},
        },
    )
    _write_json(
        root / "pipeline" / "influencer_nodes" / "lena" / "meta_publisher_config_v2_9.local.json",
        {
            "page_access_token": "PLACEHOLDER",
            "instagram_access_token": "PLACEHOLDER",
            "instagram_business_account_id": "PLACEHOLDER",
            "facebook_page_id": "PLACEHOLDER",
            "graph_api_version": "PLACEHOLDER",
            "media_public_base_url": "PLACEHOLDER",
            "media_public_local_dir": "PLACEHOLDER",
        },
    )
    _write_json(
        root / "pipeline" / "influencer_nodes" / "lena" / "meta_publisher_config_v2_9.example.json",
        {
            "page_access_token": "PASTE_PAGE_ACCESS_TOKEN",
            "instagram_access_token": "PASTE_INSTAGRAM_ACCESS_TOKEN",
            "instagram_business_account_id": "PASTE_INSTAGRAM_USER_ID",
            "facebook_page_id": "PASTE_FACEBOOK_PAGE_ID",
            "graph_api_version": "v25.0",
            "media_public_base_url": "YOUR_PUBLIC_MEDIA_HOST",
            "media_public_local_dir": "YOUR_MEDIA_ROOT",
        },
    )
    _write_text(
        root / ".env",
        "\n".join(
            [
                "META_PAGE_ACCESS_TOKEN=page-token",
                "META_INSTAGRAM_ACCESS_TOKEN=instagram-token",
                "META_IG_USER_ID=17841409711154047",
                "META_FACEBOOK_PAGE_ID=1267219163131062",
                "META_GRAPH_API_VERSION=v25.0",
                "R2_ACCOUNT_ID=acct",
                "R2_BUCKET_NAME=bucket",
                "R2_ACCESS_KEY_ID=access",
                "R2_SECRET_ACCESS_KEY=secret",
                "R2_PUBLIC_BASE_URL=https://example.invalid",
                "LENA_MEDIA_PUBLIC_BASE_URL=https://example.invalid",
                "LENA_MEDIA_PUBLIC_LOCAL_DIR=C:/media",
                "",
            ]
        ),
    )


def _write_policy_manifest(root: Path, *, authority_commit: str) -> tuple[Path, Path]:
    policy_path = root / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json"
    manifest_path = root / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_manifest_v2_8.json"
    _write_json(
        policy_path,
        {
            "version": "v2.9.1_auto_queue_publisher",
            "policy_id": "lena_approved_queue_auto_publisher_policy_v2_8",
            "policy_version": "v2.8.0",
            "repository_name": "delapilena-max/lenadelapi_website",
            "authority_version": "main",
            "authority_commit": authority_commit,
            "autonomous_mode": "scheduled_autonomous",
            "autonomous_enabled": False,
            "autonomous_enabled_by_default": False,
            "policy_effective_at_utc": "2026-07-19T00:00:00Z",
            "policy_expires_at_utc": "2026-12-31T23:59:59Z",
            "approved_slots": ["morning", "afternoon", "evening"],
            "hard_item_limit_per_invocation": 1,
            "queue_claim_lease_seconds": 1800,
            "max_attempts_per_row": 2,
            "autonomous_queue_platforms": ["Instagram Feed", "Facebook Page"],
            "manual_live_mode_unchanged": True,
            "manual_live_flags": ["--live", "--i-understand-this-can-publish"],
            "autonomous_mode_requires_distinct_policy_gate": True,
            "require_queue_build_before_first_publish_slot": True,
            "require_clean_export_revalidation": True,
            "require_atomic_queue_claim": True,
            "require_platform_receipts": True,
            "require_idempotent_post_log_sync": True,
            "allow_replies": False,
            "allow_dms": False,
            "allow_outreach": False,
        },
    )
    _write_json(
        manifest_path,
        {
            "version": "v2.9.1_auto_queue_publisher",
            "name": "Lena Approved Queue Autonomous Publisher",
            "mission": "Publish one bounded scheduled slot at a time.",
            "boundary": {
                "auto_queue_building": True,
                "auto_publish_queue": False,
                "scheduled_autonomous_mode": "separate_policy_gate_required",
                "autonomous_enabled_by_default": False,
                "autonomous_publish_requires_distinct_policy": True,
                "live_posting_requires_explicit_flags": True,
                "manual_live_mode_unchanged": True,
                "auto_replying": False,
                "auto_dm_sending": False,
                "auto_outreach": False,
            },
            "operations": {
                "queue_claim": "atomic_slot_claim",
                "slot_limit_per_invocation": 1,
                "slot_keywords": ["morning", "afternoon", "evening"],
                "require_queue_build_before_first_slot": True,
                "require_clean_export_revalidation_before_dispatch": True,
                "require_platform_receipts": True,
                "require_idempotent_post_log_sync": True,
            },
            "safety": {
                "queue_building_allowed": True,
                "duplicate_prevention": True,
                "already_posted_skip": True,
                "bounded_retries": True,
                "crash_recovery": True,
                "stale_claim_handling": True,
                "partial_platform_failure_fail_closed": True,
            },
        },
    )
    return policy_path, manifest_path


def _write_wrappers(root: Path) -> None:
    for slot in ("morning", "afternoon", "evening"):
        wrapper_path = root / f"RUN_LENA_PUBLISH_{slot.upper()}_SLOT.bat"
        _write_text(
            wrapper_path,
            "\n".join(
                [
                    "@echo off",
                    "setlocal",
                    "set \"ROOT=%LENA_AUTOPUBLISH_PRODUCTION_ROOT%\"",
                    "if not defined ROOT set \"ROOT=%CONTENT_BOT_ROOT%\"",
                    "if not defined ROOT (",
                    "  echo Missing production root environment variable: LENA_AUTOPUBLISH_PRODUCTION_ROOT or CONTENT_BOT_ROOT",
                    "  exit /b 1",
                    ")",
                    "set \"PYTHON_EXE=%LENA_AUTOPUBLISH_PYTHON_EXE%\"",
                    "if not defined PYTHON_EXE set \"PYTHON_EXE=%CONTENT_BOT_PYTHON_EXE%\"",
                    "if not defined PYTHON_EXE (",
                    "  echo Missing Python interpreter environment variable: LENA_AUTOPUBLISH_PYTHON_EXE or CONTENT_BOT_PYTHON_EXE",
                    "  exit /b 1",
                    ")",
                    "if not exist \"%PYTHON_EXE%\" (",
                    "  echo Missing Python interpreter: %PYTHON_EXE%",
                    "  exit /b 1",
                    ")",
                    "cd /d \"%ROOT%\"",
                    "\"%PYTHON_EXE%\" \".\\tools\\lena_build_approved_publish_queue_v2_8.py\"",
                    "if errorlevel 1 exit /b %errorlevel%",
                    "\"%PYTHON_EXE%\" \".\\tools\\lena_validate_approved_queue_autopublisher_v2_8.py\"",
                    "if errorlevel 1 exit /b %errorlevel%",
                    f"\"%PYTHON_EXE%\" \".\\tools\\lena_autopublish_approved_queue_v2_8.py\" --scheduled-autonomous --slot-keyword {slot} --limit 1",
                    "endlocal",
                    "",
                ]
            ),
        )


def test_publish_common_config_status_reads_explicit_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    production_root = tmp_path / "production"
    _write_env_tree(production_root)
    monkeypatch.delenv("META_PAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_IG_USER_ID", raising=False)
    monkeypatch.delenv("META_FACEBOOK_PAGE_ID", raising=False)
    monkeypatch.delenv("META_GRAPH_API_VERSION", raising=False)
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("R2_BUCKET_NAME", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("R2_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("LENA_MEDIA_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("LENA_MEDIA_PUBLIC_LOCAL_DIR", raising=False)

    status = publish_common.config_status(False, root=production_root)

    assert status["ok"] is True
    assert status["checks"]["dotenv_sources"]["ok"] is True
    assert status["checks"]["local_config_exists"]["ok"] is True
    assert status["readiness"]["instagram_ready"] is True
    assert status["readiness"]["facebook_ready"] is True
    assert status["readiness"]["media_host_ready"] is True


def test_go_live_readiness_reports_ready_from_explicit_production_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    production_root = tmp_path / "production"
    repo_root.mkdir(parents=True, exist_ok=True)
    production_root.mkdir(parents=True, exist_ok=True)
    _write_env_tree(production_root)
    _write_policy_manifest(production_root, authority_commit="a" * 40)
    _write_wrappers(repo_root)

    monkeypatch.setattr(readiness, "ROOT", repo_root)
    monkeypatch.setattr(readiness, "REPORT_ROOT", repo_root / "pipeline" / "publishing" / "lena" / "go_live_readiness")
    monkeypatch.setattr(
        readiness,
        "_git_state",
        lambda root: {
            "branch": "codex/lena-autopublish-go-live-readiness-v1",
            "head": "a" * 40,
            "origin_main": "a" * 40,
            "clean": True,
            "status_lines": [],
            "head_matches_origin_main": True,
        },
    )
    monkeypatch.setattr(
        readiness,
        "_probe_python_interpreter",
        lambda python_exe, production_root: {
            "ok": True,
            "reason": "",
            "python_exe": str(python_exe),
            "returncode": 0,
            "stdout_tail": [],
            "stderr_tail": [],
            "parsed": {"ok": True, "executable": str(python_exe), "module": "tools.publishers.lena_meta_publish_common_v2_9"},
        },
    )

    report = readiness._build_report(production_root, Path("python.exe"), "cli", "cli", "2026-07-19")

    assert report["overall_result"] == "ready_for_explicit_activation_review"
    assert report["publisher_config_ready"] is True
    assert report["environment_contract"]["ok"] is True
    assert report["policy"]["blockers"] == []
    assert report["manifest"]["blockers"] == []
    assert report["scheduler_wrappers"]["blockers"] == []
    assert report["blockers"] == []
    assert report["scheduler_specs"]["cron"][0]["slot_keyword"] == "morning"
    assert "--scheduled-autonomous" in report["scheduler_specs"]["cron"][0]["command"]
    assert "--slot-keyword morning" in report["scheduler_specs"]["cron"][0]["command"]
    assert "--limit 1" in report["scheduler_specs"]["cron"][0]["command"]
    assert report["scheduler_specs"]["windows_task_scheduler"][0]["logon_type"] == "Password_or_S4U_not_InteractiveToken"
    assert report["safe_validation_commands"][0].startswith('"python.exe" -m tools.lena_autopublish_go_live_readiness_v1')
    assert report["production_root_source"] == "cli"
    assert report["python_exe_source"] == "cli"


def test_save_report_is_conflict_safe(tmp_path: Path) -> None:
    production_root = tmp_path / "production"
    report = {
        "overall_result": "ready_for_explicit_activation_review",
        "production_root": str(production_root),
        "python_exe": "python.exe",
        "git": {"head": "a" * 40, "origin_main": "a" * 40, "clean": True},
        "operator_checklist": [],
        "safe_validation_commands": [],
        "later_enablement_commands": [],
        "blockers": [],
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
    }

    json_path, md_path = readiness.save_report(report, production_root, "2026-07-19", "20260719T010203Z")
    assert json_path.is_file()
    assert md_path.is_file()
    with pytest.raises(readiness.ReadinessError) as excinfo:
        readiness.save_report(report, production_root, "2026-07-19", "20260719T010203Z")
    assert excinfo.value.code == "artifact_already_exists"


def test_wrapper_summary_rejects_temp_worktree_hardcode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(readiness, "ROOT", repo_root)
    _write_text(repo_root / "RUN_LENA_PUBLISH_MORNING_SLOT.bat", "@echo off\nrem lenadelapi_website_hpe2\n")
    _write_text(repo_root / "RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat", "@echo off\nrem ok\n")
    _write_text(repo_root / "RUN_LENA_PUBLISH_EVENING_SLOT.bat", "@echo off\nrem ok\n")

    summary = readiness._wrapper_summary()

    assert summary["blockers"]
    assert any("temp_worktree_hardcoded" in blocker["detail"] for blocker in summary["blockers"])
    assert summary["slots"][0]["has_hardcoded_temp_root"] is True
