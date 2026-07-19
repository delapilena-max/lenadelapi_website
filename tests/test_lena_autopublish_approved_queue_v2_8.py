from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

import tools.lena_autopublish_approved_queue_v2_8 as autopublish
import tools.lena_validate_approved_queue_autopublisher_v2_8 as validator
import tools.publishers.lena_meta_publish_common_v2_9 as publish_common


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "white").save(path)
    return path


def _patch_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(autopublish, "ROOT", tmp_path)
    monkeypatch.setattr(autopublish, "PY", "python")
    monkeypatch.setattr(autopublish, "SYNC_POSTED", tmp_path / "tools" / "lena_sync_posted_queue_to_post_log_v1.py")
    monkeypatch.setattr(autopublish, "POLICY_PATH", tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json")
    monkeypatch.setattr(autopublish, "MANIFEST_PATH", tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_manifest_v2_8.json")
    monkeypatch.setattr(autopublish, "QUEUE_ROOT", tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue")
    monkeypatch.setattr(autopublish, "CLAIM_ROOT", tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims")
    monkeypatch.setattr(autopublish, "RECEIPT_ROOT", tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts")
    monkeypatch.setattr(autopublish, "REPORT_ROOT", tmp_path / "pipeline" / "publishing" / "lena" / "dispatch_reports")
    monkeypatch.setattr(autopublish, "DISPATCH_OUTBOX", tmp_path / "pipeline" / "publishing" / "lena" / "dispatch_outbox")
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    monkeypatch.setattr(validator, "NODE", tmp_path / "pipeline" / "influencer_nodes" / "lena")
    monkeypatch.setattr(publish_common, "ROOT", tmp_path)


def _policy(tmp_path: Path, *, enabled: bool = True, authority_commit: str = "a" * 40, expires: str = "2026-12-31T23:59:59Z") -> Path:
    policy = {
        "version": "v2.9.1_auto_queue_publisher",
        "policy_id": "lena_approved_queue_auto_publisher_policy_v2_8",
        "policy_version": "v2.8.0",
        "repository_name": "delapilena-max/lenadelapi_website",
        "authority_version": "main",
        "authority_commit": authority_commit,
        "autonomous_mode": "scheduled_autonomous",
        "autonomous_enabled": enabled,
        "autonomous_enabled_by_default": False,
        "autonomous_policy_state": "disabled_by_default" if not enabled else "enabled",
        "policy_effective_at_utc": "2026-07-19T00:00:00Z",
        "policy_expires_at_utc": expires,
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
        "safety": {
            "auto_replying": False,
            "auto_dm_sending": False,
            "auto_outreach": False,
            "delete_after_publish": False,
            "duplicate_prevention": True,
            "already_posted_skip": True,
        },
        "publish_mode": "explicit_live_connector_required",
        "queue_enabled": True,
        "autopublish_enabled": False,
        "live_posting_requires_explicit_flags": True,
        "required_live_flags": ["--live", "--i-understand-this-can-publish"],
    }
    return _write_json(tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json", policy)


def _manifest(tmp_path: Path) -> Path:
    manifest = {
        "version": "v2.9.1_auto_queue_publisher",
        "name": "Lena Approved Queue Autonomous Publisher",
        "mission": "Publish exactly one bounded scheduled slot at a time with explicit autonomous policy authorization and fail-closed claim, export, and receipt handling.",
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
            "no_replies_dms_or_outreach": True,
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
    }
    return _write_json(tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_manifest_v2_8.json", manifest)


def _queue_rows(tmp_path: Path, *, rows: list[dict]) -> Path:
    path = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue" / "2026-07-19" / "lena_approved_publish_queue_v2_8.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = autopublish.QUEUE_FIELDS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in fields} for row in rows])
    return path


def _sidecar(asset_path: Path, *, policy_path: Path, caption: str, platform: str, policy_sha: str, mode: str = "standing_autonomy_policy", asset_sha: str | None = None) -> Path:
    sidecar = {
        "authorization_mode": mode,
        "policy_id": "lena_approved_queue_auto_publisher_policy_v2_8",
        "policy_sha256": policy_sha,
        "cycle_id": "cycle-1",
        "cycle_authorization_path": "pipeline/approvals/lena/bounded_live_cycles/2026-07-19/lena_bounded_live_cycle_authorization_2026-07-19.json",
        "cycle_authorization_sha256": "c" * 64,
        "qa_approved": True,
        "identity_verified": True,
        "duplicate_check_passed": True,
        "publish_authorized_by_policy": True,
        "human_per_cycle_approval_required": False,
        "human_per_cycle_approval_present": False,
        "asset_path": str(asset_path),
        "target_platform": platform,
        "caption": caption,
    }
    if asset_sha:
        sidecar["asset_sha256"] = asset_sha
    return _write_json(asset_path.with_suffix(".status.json"), sidecar)


def _connector_script(tmp_path: Path, name: str, *, ok: bool, post_id: str = "", reason: str = "connector_failed") -> Path:
    path = tmp_path / "tools" / "publishers" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if ok:
        code = """
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[sys.argv.index('--payload') + 1]).read_text(encoding='utf-8'))
print(json.dumps({
    'ok': True,
    'posted': True,
    'post_id': f"{payload['queue_id']}-post",
    'post_url': f"https://example.invalid/{payload['queue_id']}",
    'posted_at': '2026-07-19T09:30:00',
}, indent=2))
"""
    else:
        code = f"""
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[sys.argv.index('--payload') + 1]).read_text(encoding='utf-8'))
print(json.dumps({{
    'ok': False,
    'posted': False,
    'reason': {reason!r},
    'post_id': '',
    'post_url': '',
    'payload_queue_id': payload.get('queue_id', ''),
}}, indent=2))
sys.exit(1)
"""
    path.write_text(code, encoding="utf-8")
    return path


def _base_rows(tmp_path: Path, policy_sha: str) -> list[dict]:
    asset_ig = _write_png(tmp_path / "pipeline" / "higgsfield_library" / "lena" / "2026-07-19" / "morning-slot-001-instagram_seed.png")
    asset_fb = _write_png(tmp_path / "pipeline" / "higgsfield_library" / "lena" / "2026-07-19" / "morning-slot-001-facebook_seed.png")
    _sidecar(asset_ig, policy_path=tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json", caption="caption one", platform="Instagram Feed", policy_sha=policy_sha, asset_sha=_sha(asset_ig))
    _sidecar(asset_fb, policy_path=tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json", caption="caption one", platform="Facebook Page", policy_sha=policy_sha, asset_sha=_sha(asset_fb))
    return [
        {
            "queue_id": "q-instagram",
            "date": "2026-07-19",
            "created_at": "2026-07-19T08:00:00",
            "slot_id": "morning-slot-001",
            "platform": "Instagram Feed",
            "media_type": "photo",
            "lane": "mirror outfit check",
            "asset_status": "approved",
            "asset_path": str(asset_ig),
            "caption": "caption one",
            "short_caption": "",
            "pinned_comment": "",
            "story_prompt": "",
            "story_poll": "",
            "post_poll": "",
            "keyword_notes": "",
            "public_text_score": "90",
            "public_text_decision": "APPROVED",
            "publish_state": "queued",
            "publish_mode": "connector_required",
            "connector_path": "tools/publishers/lena_publish_instagram_feed_v2_8.py",
            "post_url": "",
            "posted_at": "",
            "failure_reason": "",
            "attempt_count": "0",
            "notes": "",
        },
        {
            "queue_id": "q-facebook",
            "date": "2026-07-19",
            "created_at": "2026-07-19T08:00:00",
            "slot_id": "morning-slot-001",
            "platform": "Facebook Page",
            "media_type": "photo",
            "lane": "mirror outfit check",
            "asset_status": "approved",
            "asset_path": str(asset_fb),
            "caption": "caption one",
            "short_caption": "",
            "pinned_comment": "",
            "story_prompt": "",
            "story_poll": "",
            "post_poll": "",
            "keyword_notes": "",
            "public_text_score": "90",
            "public_text_decision": "APPROVED",
            "publish_state": "queued",
            "publish_mode": "connector_required",
            "connector_path": "tools/publishers/lena_publish_facebook_page_v2_8.py",
            "post_url": "",
            "posted_at": "",
            "failure_reason": "",
            "attempt_count": "0",
            "notes": "",
        },
    ]


def _patch_git_commit(monkeypatch: pytest.MonkeyPatch, commit: str) -> None:
    monkeypatch.setattr(autopublish.subprocess, "check_output", lambda *args, **kwargs: commit)


def test_validator_accepts_disabled_contract_and_scheduler_wrappers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    _policy(tmp_path, enabled=False, authority_commit="a" * 40)
    _manifest(tmp_path)
    for tool in ["tools/lena_build_approved_publish_queue_v2_8.py", "tools/lena_autopublish_approved_queue_v2_8.py"]:
        tool_path = tmp_path / tool
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("print('ok')\n", encoding="utf-8")
    for name in ["RUN_LENA_PUBLISH_MORNING_SLOT.bat", "RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat", "RUN_LENA_PUBLISH_EVENING_SLOT.bat"]:
        (tmp_path / name).write_text("@echo off\npause\n", encoding="utf-8")
    # overwrite with the actual scheduler-safe pattern to validate the checker
    for name, slot in [("RUN_LENA_PUBLISH_MORNING_SLOT.bat", "morning"), ("RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat", "afternoon"), ("RUN_LENA_PUBLISH_EVENING_SLOT.bat", "evening")]:
        (tmp_path / name).write_text(
            "\n".join(
                [
                    "@echo off",
                    "setlocal",
                    'set "ROOT=C:\\projects\\ai\\content_bot\\lenadelapi_website_hpe2"',
                    'set "PYTHON_EXE=C:\\Python314\\python.exe"',
                    'cd /d "%ROOT%"',
                    f'"%PYTHON_EXE%" ".\\tools\\lena_autopublish_approved_queue_v2_8.py" --scheduled-autonomous --slot-keyword {slot} --limit 1',
                    "endlocal",
                ]
            ),
            encoding="utf-8",
        )
    report = json.loads((tmp_path / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json").read_text(encoding="utf-8"))
    assert report["autonomous_enabled"] is False
    assert validator.main() == 0


def test_checked_in_scheduler_wrappers_are_scheduler_safe() -> None:
    for name, slot in [
        ("RUN_LENA_PUBLISH_MORNING_SLOT.bat", "morning"),
        ("RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat", "afternoon"),
        ("RUN_LENA_PUBLISH_EVENING_SLOT.bat", "evening"),
    ]:
        text = (Path(autopublish.__file__).resolve().parents[1] / name).read_text(encoding="utf-8", errors="ignore")
        assert "pause" not in text.lower()
        assert "--scheduled-autonomous" in text
        assert f"--slot-keyword {slot}" in text
        assert "--i-understand-this-can-publish" not in text
        assert "C:\\Python314\\python.exe" in text


def test_scheduled_autonomous_policy_disabled_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=False, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert excinfo.value.code == "autonomous_policy_disabled"


def test_scheduled_autonomous_stale_policy_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="b" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert excinfo.value.code == "autonomous_policy_stale"


def test_scheduled_autonomous_dry_run_makes_zero_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    report = autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=True, policy_path=policy_path)
    assert report["dry_run"] is True
    assert report["publish_calls_performed"] == 0
    assert report["provider_calls_performed"] == 0
    assert not (tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims").exists()
    assert not (tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts").exists()


def test_scheduled_autonomous_processes_one_slot_with_partial_platform_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    instagram = _connector_script(tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=True)
    facebook = _connector_script(tmp_path, "lena_publish_facebook_page_v2_8.py", ok=False, reason="partial_platform_failure")
    rows[0]["connector_path"] = str(instagram.relative_to(tmp_path).as_posix())
    rows[1]["connector_path"] = str(facebook.relative_to(tmp_path).as_posix())
    _queue_rows(tmp_path, rows=rows)

    report = autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)

    assert report["ok"] is True
    assert report["publish_calls_performed"] == 2
    assert report["provider_calls_performed"] == 0
    assert report["posted_count"] == 1
    assert report["failed_count"] == 1
    queue_path = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue" / "2026-07-19" / "lena_approved_publish_queue_v2_8.csv"
    queue_rows = list(csv.DictReader(queue_path.open("r", encoding="utf-8")))
    assert next(row for row in queue_rows if row["platform"] == "Instagram Feed")["publish_state"] == "posted"
    assert next(row for row in queue_rows if row["platform"] == "Facebook Page")["publish_state"] in {"failed", "abandoned"}
    receipt = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts" / "2026-07-19" / "morning-slot-001" / "q-instagram_Instagram_Feed_publish_receipt.json"
    assert receipt.is_file()
    claim = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims" / "2026-07-19" / "morning-slot-001.json"
    assert claim.is_file()


def test_scheduled_autonomous_concurrent_claim_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    claim = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims" / "2026-07-19" / "morning-slot-001.json"
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_text(json.dumps({"state": "claimed", "lease_expires_at_utc": "2099-01-01T00:00:00Z"}, indent=2), encoding="utf-8")
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert excinfo.value.code == "autonomous_queue_claim_active"


def test_scheduled_autonomous_stale_claim_is_recovered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    claim = tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims" / "2026-07-19" / "morning-slot-001.json"
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_text(json.dumps({"state": "claimed", "lease_expires_at_utc": "2020-01-01T00:00:00Z"}, indent=2), encoding="utf-8")
    _connector_script(tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=True)
    _connector_script(tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True)
    report = autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert report["posted_count"] == 2
    assert json.loads(claim.read_text(encoding="utf-8"))["state"] == "completed"


def test_scheduled_autonomous_already_posted_rows_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    rows[0]["publish_state"] = "posted"
    rows[0]["posted_at"] = "2026-07-19T09:00:00"
    rows[0]["post_url"] = "https://example.invalid/already"
    _write_json(_receipt_path := tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts" / "2026-07-19" / "morning-slot-001" / "q-instagram_Instagram_Feed_publish_receipt.json", {"posted": True, "post_id": "existing"})
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    _connector_script(tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True)
    report = autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert report["publish_calls_performed"] == 1
    assert report["posted_count"] == 1
    assert report["recovered_queue_ids"] == []


def test_scheduled_autonomous_clean_export_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    sidecar_path = Path(rows[0]["asset_path"]).with_suffix(".status.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["policy_sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert excinfo.value.code == "clean_export_policy_sha256_mismatch"


def test_scheduled_autonomous_retry_exhaustion_abandons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    rows[1]["attempt_count"] = "1"
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    _connector_script(tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=False, reason="connector_failed")
    _connector_script(tmp_path, "lena_publish_facebook_page_v2_8.py", ok=False, reason="connector_failed")
    report = autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="morning", limit=1, dry_run=False, policy_path=policy_path)
    assert report["failed_count"] + report["abandoned_count"] >= 1
    queue_rows = list(csv.DictReader((tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue" / "2026-07-19" / "lena_approved_publish_queue_v2_8.csv").open("r", encoding="utf-8")))
    assert next(row for row in queue_rows if row["platform"] == "Facebook Page")["publish_state"] in {"failed", "abandoned"}


def test_scheduled_autonomous_wrong_or_missing_slot_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="midnight", limit=1, dry_run=False, policy_path=policy_path)
    assert excinfo.value.code == "autonomous_slot_invalid"


def test_scheduled_autonomous_more_than_one_eligible_slot_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    rows.append({**rows[0], "queue_id": "q-instagram-2", "slot_id": "afternoon-slot-002"})
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(day="2026-07-19", slot_keyword="slot", limit=1, dry_run=False, policy_path=policy_path)
    assert excinfo.value.code in {"autonomous_slot_invalid", "autonomous_multiple_slot_candidates", "autonomous_slot_missing"}


def test_manual_live_behavior_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=False, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    report = autopublish.run_manual_publish(
        day="2026-07-19",
        platforms="Instagram Feed,Facebook Page",
        dry_run=False,
        live=False,
        ack_publish_risk=False,
        limit=1,
        slot_keyword="morning",
        max_attempts=3,
        feedback_queue_limit=6,
    )
    assert report["ok"] is False
    assert report["error"] == "live_publish_blocked_missing_explicit_approval_flags"
