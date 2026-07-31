from __future__ import annotations

import json
import os
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


def _shared_secret_path(root: Path) -> Path:
    return root.parent / "content_bot" / ".env"


def _set_canonical_secret_source(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv(publish_common.CANONICAL_PUBLISHER_SECRET_ENV_OVERRIDE, str(path))


def _write_env_tree(root: Path) -> Path:
    _write_json(
        root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json",
        {
            "contract_id": "lena_meta_env_key_map_v2_9_1",
            "schema_version": "v1",
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
            "instagram_business_account_id": "17841409711154047",
            "facebook_page_id": "1267219163131062",
            "graph_api_version": "v25.0",
            "media_public_base_url": "https://pub.example.invalid",
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
    return _write_text(
        _shared_secret_path(root),
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


def _write_hybrid_contract_tree(root: Path, env_lines: list[str]) -> Path:
    _write_json(
        root / "pipeline" / "influencer_nodes" / "lena" / "meta_env_key_map_v2_9_1.json",
        {
            "contract_id": "lena_meta_env_key_map_v2_9_1",
            "schema_version": "v1",
            "authority": "hybrid_contract_is_canonical",
            "key_map": {
                "page_access_token": ["META_PAGE_ACCESS_TOKEN"],
                "instagram_access_token": ["META_INSTAGRAM_ACCESS_TOKEN"],
                "instagram_business_account_id": ["META_IG_USER_ID"],
                "facebook_page_id": ["META_FACEBOOK_PAGE_ID"],
                "graph_api_version": ["META_GRAPH_API_VERSION"],
                "media_public_base_url": ["LENA_MEDIA_PUBLIC_BASE_URL"],
                "media_public_local_dir": ["LENA_MEDIA_PUBLIC_LOCAL_DIR"],
            },
        },
    )
    _write_json(
        root / "pipeline" / "influencer_nodes" / "lena" / "meta_publisher_config_v2_9.local.json",
        {
            "version": "v2.9.0",
            "auth_mode": "facebook_login",
            "graph_api_version": "v25.0",
            "instagram_business_account_id": "17841409711154047",
            "facebook_page_id": "1267219163131062",
            "ig_share_reels_to_feed": True,
            "media_public_base_url": "https://pub.example.invalid",
            "dry_run": False,
        },
    )
    return _write_text(_shared_secret_path(root), "\n".join(env_lines) + "\n")


def _write_local_worktree_env(root: Path, env_lines: list[str]) -> Path:
    return _write_text(root / ".env", "\n".join(env_lines) + "\n")


def _clear_publish_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(publish_common.CANONICAL_PUBLISHER_SECRET_ENV_OVERRIDE, raising=False)
    for key in (
        "META_PAGE_ACCESS_TOKEN",
        "META_INSTAGRAM_ACCESS_TOKEN",
        "META_IG_USER_ID",
        "META_FACEBOOK_PAGE_ID",
        "META_GRAPH_API_VERSION",
        "R2_ACCOUNT_ID",
        "R2_BUCKET_NAME",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_PUBLIC_BASE_URL",
        "LENA_MEDIA_PUBLIC_BASE_URL",
        "LENA_MEDIA_PUBLIC_LOCAL_DIR",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_policy_manifest(root: Path, *, authority_commit: str, autonomous_enabled: bool = True) -> tuple[Path, Path]:
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
            "autonomous_enabled": autonomous_enabled,
            "autonomous_enabled_by_default": False,
            "autonomous_policy_state": "enabled" if autonomous_enabled else "disabled_by_default",
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


def test_publish_common_config_status_reads_explicit_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    production_root = tmp_path / "production"
    shared_secret_path = _write_env_tree(production_root)
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

    status = publish_common.config_status(False, root=production_root)

    assert status["ok"] is True
    assert status["checks"]["env_map_contract"]["ok"] is True
    assert status["checks"]["canonical_secret_source"]["ok"] is True
    assert status["checks"]["canonical_secret_source"]["path"] == str(shared_secret_path)
    assert status["checks"]["dotenv_sources"]["ok"] is True
    assert status["checks"]["dotenv_sources"]["sources"] == [str(shared_secret_path)]
    assert status["checks"]["local_config_exists"]["ok"] is True
    assert status["readiness"]["instagram_ready"] is True
    assert status["readiness"]["facebook_ready"] is True
    assert status["readiness"]["media_host_ready"] is True


def test_hybrid_local_config_counts_without_duplicate_non_secret_env_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production_root = tmp_path / "production"
    shared_secret_path = _write_hybrid_contract_tree(
        production_root,
        env_lines=[
            "META_PAGE_ACCESS_TOKEN=page-token",
            "META_IG_USER_ID=bad-from-secret-source",
            "LENA_MEDIA_PUBLIC_BASE_URL=https://should-not-override.invalid",
            "UNRELATED_SECRET_SHOULD_BE_IGNORED=ignored",
        ],
    )
    _write_local_worktree_env(production_root, ["META_PAGE_ACCESS_TOKEN=wrong-local-token"])
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

    cfg = publish_common.load_config(production_root)
    status = publish_common.config_status(False, root=production_root)
    env_report = readiness._env_presence_report(production_root, dict(os.environ), status)

    assert cfg["instagram_business_account_id"] == "17841409711154047"
    assert cfg["facebook_page_id"] == "1267219163131062"
    assert cfg["graph_api_version"] == "v25.0"
    assert cfg["media_public_base_url"] == "https://pub.example.invalid"
    assert cfg["media_public_local_dir"] == str(production_root / "pipeline" / "publishing" / "lena" / "media_public")
    assert cfg["page_access_token"] == "page-token"
    assert publish_common.discover_dotenv_values(production_root)["sources"] == [str(shared_secret_path)]
    assert status["checks"]["canonical_secret_source"]["loaded_keys"] == ["META_PAGE_ACCESS_TOKEN"]
    assert env_report["secret_source_path"] == str(shared_secret_path)
    assert env_report["secret_source_contract_ok"] is True
    assert env_report["loaded_secret_keys"] == ["META_PAGE_ACCESS_TOKEN"]
    assert status["readiness"]["instagram_ready"] is True
    assert status["readiness"]["facebook_ready"] is True
    assert status["readiness"]["media_host_ready"] is True
    assert env_report["missing"] == []
    assert env_report["required_env_vars"] == []
    assert "META_IG_USER_ID" not in env_report["missing"]
    assert "META_FACEBOOK_PAGE_ID" not in env_report["missing"]
    assert "META_GRAPH_API_VERSION" not in env_report["missing"]
    assert "LENA_MEDIA_PUBLIC_BASE_URL" not in env_report["missing"]
    assert "LENA_MEDIA_PUBLIC_LOCAL_DIR" not in env_report["missing"]
    assert "R2_ACCESS_KEY_ID" not in env_report["required_env_vars"]
    assert (production_root / ".env").read_text(encoding="utf-8") == "META_PAGE_ACCESS_TOKEN=wrong-local-token\n"


def test_readiness_only_flags_runtime_required_secret_when_hybrid_config_supplies_non_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production_root = tmp_path / "production"
    shared_secret_path = _write_hybrid_contract_tree(production_root, env_lines=[])
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

    status = publish_common.config_status(False, root=production_root)
    env_report = readiness._env_presence_report(production_root, dict(os.environ), status)

    assert status["readiness"]["instagram_ready"] is False
    assert status["readiness"]["facebook_ready"] is False
    assert status["readiness"]["media_host_ready"] is True
    assert env_report["missing"] == ["META_PAGE_ACCESS_TOKEN"]
    assert env_report["required_env_vars"] == ["META_PAGE_ACCESS_TOKEN"]


def test_missing_env_map_fails_closed_for_runtime_and_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production_root = tmp_path / "production"
    missing_shared_secret_path = _shared_secret_path(production_root)
    _write_json(
        production_root / "pipeline" / "influencer_nodes" / "lena" / "meta_publisher_config_v2_9.local.json",
        {
            "auth_mode": "facebook_login",
            "instagram_business_account_id": "17841409711154047",
            "facebook_page_id": "1267219163131062",
            "media_public_base_url": "https://pub.example.invalid",
        },
    )
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, missing_shared_secret_path)

    status = publish_common.config_status(False, root=production_root)
    validation = publish_common.validate_config_for("Instagram Feed", "image", root=production_root)
    env_report = readiness._env_presence_report(production_root, dict(os.environ), status)

    assert status["checks"]["env_map_contract"]["ok"] is False
    assert "missing env map contract" in status["checks"]["env_map_contract"]["detail"]
    assert status["checks"]["canonical_secret_source"]["ok"] is False
    assert str(missing_shared_secret_path) == status["checks"]["canonical_secret_source"]["path"]
    assert validation["ok"] is False
    assert validation["reason"] == "invalid_env_map_contract"
    assert env_report["env_map_contract_ok"] is False
    assert env_report["secret_source_contract_ok"] is False
    assert "missing canonical publisher secret source" in env_report["secret_source_error"]


def test_missing_canonical_secret_source_fails_closed_even_with_valid_translation_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production_root = tmp_path / "production"
    _write_hybrid_contract_tree(production_root, env_lines=[])
    shared_secret_path = _shared_secret_path(production_root)
    if shared_secret_path.exists():
        shared_secret_path.unlink()
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

    status = publish_common.config_status(False, root=production_root)
    validation = publish_common.validate_config_for("Facebook Page", "image", root=production_root)
    env_report = readiness._env_presence_report(production_root, dict(os.environ), status)

    assert status["checks"]["env_map_contract"]["ok"] is True
    assert status["checks"]["canonical_secret_source"]["ok"] is False
    assert status["checks"]["canonical_secret_source"]["path"] == str(shared_secret_path)
    assert validation["ok"] is False
    assert validation["reason"] == "missing_canonical_publisher_secret_source"
    assert env_report["secret_source_contract_ok"] is False
    assert env_report["secret_source_path"] == str(shared_secret_path)
    assert "missing canonical publisher secret source" in env_report["secret_source_error"]


def test_readiness_report_never_emits_raw_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    production_root = tmp_path / "production"
    secret = "page-token-super-secret"
    repo_root.mkdir(parents=True, exist_ok=True)
    production_root.mkdir(parents=True, exist_ok=True)
    shared_secret_path = _write_hybrid_contract_tree(
        production_root,
        env_lines=[
            f"META_PAGE_ACCESS_TOKEN={secret}",
        ],
    )
    _write_policy_manifest(production_root, authority_commit="a" * 40, autonomous_enabled=True)
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

    monkeypatch.setattr(readiness, "ROOT", repo_root)
    monkeypatch.setattr(readiness, "REPORT_ROOT", repo_root / "pipeline" / "publishing" / "lena" / "go_live_readiness")
    monkeypatch.setattr(
        readiness,
        "_git_state",
        lambda root: {
            "branch": "codex/lena-photo-production-main-validation-v1",
            "head": "a" * 40,
            "origin_main": "a" * 40,
            "clean": True,
            "status_lines": [],
            "head_matches_origin_main": True,
            "origin_main_ancestor_of_head": True,
            "head_ancestor_of_origin_main": True,
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
    monkeypatch.setattr(readiness, "_git_is_ancestor", lambda root, ancestor_commit, descendant_commit: True)
    monkeypatch.setattr(
        readiness,
        "_canonical_scheduler_definition",
        lambda production_root, python_exe: {
            "ok": True,
            "blockers": [],
            "register_script_path": str(production_root / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"),
            "plan": {
                "task_count": 1,
                "task_name": readiness.CANONICAL_TASK_NAME,
                "disabled_by_default": True,
                "action": {
                    "execute": "powershell.exe",
                    "arguments": f'-NoProfile -ExecutionPolicy Bypass -File "{production_root / "tools" / "lena_autonomy_scheduler_driver_run_v1.ps1"}" -RepoRoot "{production_root}" -PythonExe "{Path("python.exe")}"',
                    "working_directory": str(production_root),
                },
                "trigger": {
                    "type": "poll_every_minute",
                    "schedule_slots": ["morning", "afternoon", "evening"],
                },
            },
        },
    )
    monkeypatch.setattr(
        readiness,
        "_registered_task_deployment_status",
        lambda production_root, scheduler_definition: {
            "query_ok": True,
            "deployment_state": "canonical_driver_missing",
            "activation_required": True,
            "tasks": [],
            "canonical_task_present": False,
            "canonical_task_enabled": False,
            "canonical_task_matches_plan": False,
            "legacy_tasks_present": [],
            "stale_deployment_detected": False,
            "blockers": [],
        },
    )

    report = readiness._build_report(production_root, Path("python.exe"), "cli", "cli", "2026-07-31")
    rendered = json.dumps(report, ensure_ascii=False)

    assert secret not in rendered
    assert report["publisher_config"]["checks"]["page_access_token"]["ok"] is True
    assert report["environment_contract"]["missing"] == []
    assert report["environment_contract"]["secret_source_path"] == str(shared_secret_path)


def test_resolve_python_exe_uses_path_lookup_for_bare_cli_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_python = tmp_path / "bin" / "python.exe"
    fake_python.parent.mkdir(parents=True, exist_ok=True)
    fake_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(readiness.shutil, "which", lambda value: str(fake_python) if value == "python.exe" else None)

    python_exe, source = readiness._resolve_python_exe("python.exe")

    assert source == "cli"
    assert python_exe == fake_python.resolve()


def test_resolve_python_exe_preserves_explicit_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_python = tmp_path / "runtime" / "python.exe"
    fake_python.parent.mkdir(parents=True, exist_ok=True)
    fake_python.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    python_exe, source = readiness._resolve_python_exe(os.path.join("runtime", "python.exe"))

    assert source == "cli"
    assert python_exe == fake_python.resolve()


def test_resolve_python_exe_preserves_explicit_windows_absolute_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness.shutil, "which", lambda value: None)

    python_exe, source = readiness._resolve_python_exe(r"C:\Python314\python.exe")

    assert source == "cli"
    assert str(python_exe) == r"C:\Python314\python.exe"


def test_resolve_python_exe_missing_executable_fails_closed_in_probe(tmp_path: Path) -> None:
    production_root = tmp_path / "production"
    production_root.mkdir(parents=True, exist_ok=True)
    python_exe, source = readiness._resolve_python_exe("missing-python-executable")
    probe = readiness._probe_python_interpreter(python_exe, production_root)

    assert source == "cli"
    assert probe["ok"] is False
    assert probe["reason"] == "python_executable_missing"


def test_go_live_readiness_reports_ready_from_explicit_production_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    production_root = tmp_path / "production"
    repo_root.mkdir(parents=True, exist_ok=True)
    production_root.mkdir(parents=True, exist_ok=True)
    shared_secret_path = _write_env_tree(production_root)
    _write_policy_manifest(production_root, authority_commit="a" * 40, autonomous_enabled=True)
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

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
    monkeypatch.setattr(readiness, "_git_is_ancestor", lambda root, ancestor_commit, descendant_commit: True)
    monkeypatch.setattr(
        readiness,
        "_canonical_scheduler_definition",
        lambda production_root, python_exe: {
            "ok": True,
            "blockers": [],
            "register_script_path": str(production_root / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"),
            "plan": {
                "task_count": 1,
                "task_name": readiness.CANONICAL_TASK_NAME,
                "disabled_by_default": True,
                "action": {
                    "execute": "powershell.exe",
                    "arguments": f'-NoProfile -ExecutionPolicy Bypass -File "{production_root / "tools" / "lena_autonomy_scheduler_driver_run_v1.ps1"}" -RepoRoot "{production_root}" -PythonExe "{python_exe}"',
                    "working_directory": str(production_root),
                },
                "trigger": {
                    "type": "poll_every_minute",
                    "schedule_slots": ["morning", "afternoon", "evening"],
                },
            },
        },
    )
    monkeypatch.setattr(
        readiness,
        "_registered_task_deployment_status",
        lambda production_root, scheduler_definition: {
            "query_ok": True,
            "deployment_state": "canonical_driver_missing",
            "activation_required": True,
            "tasks": [],
            "canonical_task_present": False,
            "canonical_task_enabled": False,
            "canonical_task_matches_plan": False,
            "legacy_tasks_present": [],
            "stale_deployment_detected": False,
            "blockers": [],
        },
    )

    report = readiness._build_report(production_root, Path("python.exe"), "cli", "cli", "2026-07-19")

    assert report["overall_result"] == "ready_for_disabled_scheduler_replacement"
    assert report["publisher_config_ready"] is True
    assert report["structural_validity"]["ok"] is True
    assert report["environment_contract"]["ok"] is True
    assert report["policy"]["blockers"] == []
    assert report["manifest"]["blockers"] == []
    assert report["blockers"] == []
    assert report["scheduler_definition_readiness"]["ok"] is True
    assert report["registered_task_deployment_status"]["deployment_state"] == "canonical_driver_missing"
    assert report["activation_state"]["autonomous_enabled"] is True
    assert report["activation_state"]["activation_required"] is True
    assert report["safe_validation_commands"][0].startswith('"python.exe" -m tools.lena_autopublish_go_live_readiness_v1')
    assert report["safe_validation_commands"][0].endswith("--validate-only")
    assert report["safe_validation_commands"][1].startswith("powershell.exe -NoProfile -ExecutionPolicy Bypass -File")
    assert report["production_root_source"] == "cli"
    assert report["python_exe_source"] == "cli"
    assert report["environment_contract"]["secret_source_path"] == str(shared_secret_path)


def test_build_report_accepts_clean_branch_ahead_of_origin_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    production_root = tmp_path / "production"
    repo_root.mkdir(parents=True, exist_ok=True)
    production_root.mkdir(parents=True, exist_ok=True)
    shared_secret_path = _write_env_tree(production_root)
    _write_policy_manifest(production_root, authority_commit="a" * 40, autonomous_enabled=True)
    _clear_publish_env(monkeypatch)
    _set_canonical_secret_source(monkeypatch, shared_secret_path)

    monkeypatch.setattr(readiness, "ROOT", repo_root)
    monkeypatch.setattr(readiness, "REPORT_ROOT", repo_root / "pipeline" / "publishing" / "lena" / "go_live_readiness")
    monkeypatch.setattr(
        readiness,
        "_git_state",
        lambda root: {
            "branch": "codex/lena-photo-production-main-validation-v1",
            "head": "b" * 40,
            "origin_main": "a" * 40,
            "clean": True,
            "status_lines": [],
            "head_matches_origin_main": False,
            "origin_main_ancestor_of_head": True,
            "head_ancestor_of_origin_main": False,
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
    monkeypatch.setattr(readiness, "_git_is_ancestor", lambda root, ancestor_commit, descendant_commit: True)
    monkeypatch.setattr(
        readiness,
        "_canonical_scheduler_definition",
        lambda production_root, python_exe: {
            "ok": True,
            "blockers": [],
            "register_script_path": str(production_root / "tools" / "register_lena_autonomy_scheduler_task_v1.ps1"),
            "plan": {
                "task_count": 1,
                "task_name": readiness.CANONICAL_TASK_NAME,
                "disabled_by_default": True,
                "action": {
                    "execute": "powershell.exe",
                    "arguments": f'-NoProfile -ExecutionPolicy Bypass -File "{production_root / "tools" / "lena_autonomy_scheduler_driver_run_v1.ps1"}" -RepoRoot "{production_root}" -PythonExe "{python_exe}"',
                    "working_directory": str(production_root),
                },
                "trigger": {
                    "type": "poll_every_minute",
                    "schedule_slots": ["morning", "afternoon", "evening"],
                },
            },
        },
    )
    monkeypatch.setattr(
        readiness,
        "_registered_task_deployment_status",
        lambda production_root, scheduler_definition: {
            "query_ok": True,
            "deployment_state": "canonical_driver_missing",
            "activation_required": True,
            "tasks": [],
            "canonical_task_present": False,
            "canonical_task_enabled": False,
            "canonical_task_matches_plan": False,
            "legacy_tasks_present": [],
            "stale_deployment_detected": False,
            "blockers": [],
        },
    )

    report = readiness._build_report(production_root, Path("python.exe"), "cli", "cli", "2026-07-19")

    assert report["git"]["head_matches_origin_main"] is False
    assert report["git"]["origin_main_ancestor_of_head"] is True
    assert not any(blocker["code"] == "repository_head_mismatch" for blocker in report["blockers"])
    assert report["overall_result"] == "ready_for_disabled_scheduler_replacement"
    assert report["environment_contract"]["secret_source_path"] == str(shared_secret_path)


def test_save_report_is_conflict_safe(tmp_path: Path) -> None:
    production_root = tmp_path / "production"
    report = {
        "overall_result": "ready_for_disabled_scheduler_replacement",
        "production_root": str(production_root),
        "python_exe": "python.exe",
        "git": {"head": "a" * 40, "origin_main": "a" * 40, "clean": True},
        "structural_validity": {"ok": True},
        "activation_state": {"activation_required": True},
        "registered_task_deployment_status": {
            "deployment_state": "canonical_driver_missing",
            "canonical_task_present": False,
            "canonical_task_matches_plan": False,
            "canonical_task_enabled": False,
            "legacy_tasks_present": [],
        },
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


def test_main_validate_only_emits_json_and_writes_no_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    production_root = tmp_path / "production"
    production_root.mkdir(parents=True, exist_ok=True)
    report = {
        "overall_result": "ready_for_disabled_scheduler_replacement",
        "production_root": str(production_root),
        "python_exe": "python.exe",
        "git": {"head": "a" * 40, "origin_main": "a" * 40, "clean": True},
        "structural_validity": {"ok": True},
        "activation_state": {"activation_required": True},
        "registered_task_deployment_status": {
            "deployment_state": "canonical_driver_missing",
            "canonical_task_present": False,
            "canonical_task_matches_plan": False,
            "canonical_task_enabled": False,
            "legacy_tasks_present": [],
        },
        "operator_checklist": [],
        "safe_validation_commands": [],
        "later_enablement_commands": [],
        "blockers": [],
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
    }
    monkeypatch.setattr(readiness, "_build_report", lambda *args, **kwargs: report)

    exit_code = readiness.main(
        [
            "--production-root",
            str(production_root),
            "--python-exe",
            "python.exe",
            "--date",
            "2026-07-19",
            "--validate-only",
        ]
    )

    assert exit_code == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["overall_result"] == "ready_for_disabled_scheduler_replacement"
    assert not (production_root / "pipeline" / "publishing" / "lena" / "go_live_readiness").exists()
