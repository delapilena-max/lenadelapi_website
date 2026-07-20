from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

import tools.lena_autopublish_approved_queue_v2_8 as autopublish
import tools.lena_validate_approved_queue_autopublisher_v2_8 as validator
import tools.publishers.lena_meta_publish_common_v2_9 as publish_common


# ── helpers shared with the existing suite (duplicated for isolation) ─────────

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "white").save(path)
    return path


def _patch_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(autopublish, "ROOT", tmp_path)
    monkeypatch.setattr(autopublish, "PY", "python")
    monkeypatch.setattr(
        autopublish, "SYNC_POSTED",
        tmp_path / "tools" / "lena_sync_posted_queue_to_post_log_v1.py",
    )
    monkeypatch.setattr(
        autopublish, "POLICY_PATH",
        tmp_path / "pipeline" / "influencer_nodes" / "lena"
        / "approved_queue_auto_publisher_policy_v2_8.json",
    )
    monkeypatch.setattr(
        autopublish, "MANIFEST_PATH",
        tmp_path / "pipeline" / "influencer_nodes" / "lena"
        / "approved_queue_auto_publisher_manifest_v2_8.json",
    )
    monkeypatch.setattr(
        autopublish, "QUEUE_ROOT",
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue",
    )
    monkeypatch.setattr(
        autopublish, "CLAIM_ROOT",
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims",
    )
    monkeypatch.setattr(
        autopublish, "RECEIPT_ROOT",
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_receipts",
    )
    monkeypatch.setattr(
        autopublish, "REPORT_ROOT",
        tmp_path / "pipeline" / "publishing" / "lena" / "dispatch_reports",
    )
    monkeypatch.setattr(
        autopublish, "DISPATCH_OUTBOX",
        tmp_path / "pipeline" / "publishing" / "lena" / "dispatch_outbox",
    )
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    monkeypatch.setattr(
        validator, "NODE",
        tmp_path / "pipeline" / "influencer_nodes" / "lena",
    )
    monkeypatch.setattr(publish_common, "ROOT", tmp_path)


def _policy(
    tmp_path: Path,
    *,
    enabled: bool = True,
    authority_commit: str = "a" * 40,
    expires: str = "2026-12-31T23:59:59Z",
    omit_expires: bool = False,
) -> Path:
    policy: dict = {
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
    if not omit_expires:
        policy["policy_expires_at_utc"] = expires
    return _write_json(
        tmp_path / "pipeline" / "influencer_nodes" / "lena"
        / "approved_queue_auto_publisher_policy_v2_8.json",
        policy,
    )


def _manifest(tmp_path: Path) -> Path:
    manifest = {
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
    return _write_json(
        tmp_path / "pipeline" / "influencer_nodes" / "lena"
        / "approved_queue_auto_publisher_manifest_v2_8.json",
        manifest,
    )


def _queue_rows(tmp_path: Path, *, rows: list[dict]) -> Path:
    path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue"
        / "2026-07-19" / "lena_approved_publish_queue_v2_8.csv"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = autopublish.QUEUE_FIELDS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [{key: row.get(key, "") for key in fields} for row in rows]
        )
    return path


def _sidecar(
    asset_path: Path,
    *,
    policy_path: Path,
    caption: str,
    platform: str,
    policy_sha: str,
    mode: str = "standing_autonomy_policy",
    asset_sha: str | None = None,
) -> Path:
    sidecar: dict = {
        "authorization_mode": mode,
        "policy_id": "lena_approved_queue_auto_publisher_policy_v2_8",
        "policy_sha256": policy_sha,
        "cycle_id": "cycle-1",
        "cycle_authorization_path": (
            "pipeline/approvals/lena/bounded_live_cycles"
            "/2026-07-19/lena_bounded_live_cycle_authorization_2026-07-19.json"
        ),
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


def _connector_script(
    tmp_path: Path,
    name: str,
    *,
    ok: bool,
    post_id: str = "",
    reason: str = "connector_failed",
) -> Path:
    path = tmp_path / "tools" / "publishers" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if ok:
        code = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "payload = json.loads("
            "Path(sys.argv[sys.argv.index('--payload')+1])"
            ".read_text(encoding='utf-8'))\n"
            "print(json.dumps({\n"
            "    'ok': True, 'posted': True,\n"
            "    'post_id': payload['queue_id']+'-post',\n"
            "    'post_url': 'https://example.invalid/'+payload['queue_id'],\n"
            "    'posted_at': '2026-07-19T09:30:00',\n"
            "}))\n"
        )
    else:
        code = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "payload = json.loads("
            "Path(sys.argv[sys.argv.index('--payload')+1])"
            ".read_text(encoding='utf-8'))\n"
            f"print(json.dumps({{'ok':False,'posted':False,'reason':{reason!r}}}))\n"
            "sys.exit(1)\n"
        )
    path.write_text(code, encoding="utf-8")
    return path


def _base_rows(tmp_path: Path, policy_sha: str) -> list[dict]:
    asset_ig = _write_png(
        tmp_path / "pipeline" / "higgsfield_library" / "lena"
        / "2026-07-19" / "morning-slot-001-instagram_seed.png"
    )
    asset_fb = _write_png(
        tmp_path / "pipeline" / "higgsfield_library" / "lena"
        / "2026-07-19" / "morning-slot-001-facebook_seed.png"
    )
    _sidecar(
        asset_ig,
        policy_path=tmp_path / "pipeline" / "influencer_nodes" / "lena"
        / "approved_queue_auto_publisher_policy_v2_8.json",
        caption="caption one",
        platform="Instagram Feed",
        policy_sha=policy_sha,
        asset_sha=_sha(asset_ig),
    )
    _sidecar(
        asset_fb,
        policy_path=tmp_path / "pipeline" / "influencer_nodes" / "lena"
        / "approved_queue_auto_publisher_policy_v2_8.json",
        caption="caption one",
        platform="Facebook Page",
        policy_sha=policy_sha,
        asset_sha=_sha(asset_fb),
    )
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


def _patch_git_commit(
    monkeypatch: pytest.MonkeyPatch,
    commit: str,
    *,
    ancestors: set[tuple[str, str]] | None = None,
) -> None:
    ancestor_pairs = set(ancestors or {(commit, commit)})

    def fake_check_output(cmd, *args, **kwargs):
        if list(cmd[:3]) == ["git", "rev-parse", "HEAD"]:
            return commit
        if list(cmd[:3]) == ["git", "merge-base", "--is-ancestor"]:
            pair = (cmd[3], cmd[4])
            if pair in ancestor_pairs:
                return ""
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="", stderr="")
        raise AssertionError(f"unexpected git command: {cmd}")

    monkeypatch.setattr(autopublish.subprocess, "check_output", fake_check_output)


# ── Fix 1: platform filter ────────────────────────────────────────────────────

def test_scheduled_autonomous_disallowed_platform_in_slot_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TikTok row sharing morning-slot-001 must never be dispatched."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))

    tiktok_asset = _write_png(
        tmp_path / "pipeline" / "higgsfield_library" / "lena"
        / "2026-07-19" / "morning-slot-001-tiktok_seed.png"
    )
    _sidecar(
        tiktok_asset,
        policy_path=policy_path,
        caption="caption one",
        platform="TikTok",
        policy_sha=_sha(policy_path),
        asset_sha=_sha(tiktok_asset),
    )
    tiktok_connector = _connector_script(
        tmp_path, "lena_publish_tiktok_v2_8.py", ok=True,
    )
    rows.append({
        "queue_id": "q-tiktok",
        "date": "2026-07-19",
        "created_at": "2026-07-19T08:00:00",
        "slot_id": "morning-slot-001",
        "platform": "TikTok",
        "media_type": "photo",
        "lane": "mirror outfit check",
        "asset_status": "approved",
        "asset_path": str(tiktok_asset),
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
        "connector_path": str(
            tiktok_connector.relative_to(tmp_path).as_posix()
        ),
        "post_url": "",
        "posted_at": "",
        "failure_reason": "",
        "attempt_count": "0",
        "notes": "",
    })
    ig_connector = _connector_script(
        tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=True,
    )
    fb_connector = _connector_script(
        tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True,
    )
    rows[0]["connector_path"] = str(
        ig_connector.relative_to(tmp_path).as_posix()
    )
    rows[1]["connector_path"] = str(
        fb_connector.relative_to(tmp_path).as_posix()
    )
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )

    assert report["ok"] is True
    assert report["publish_calls_performed"] == 2
    assert report["posted_count"] == 2

    queue_path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue"
        / "2026-07-19" / "lena_approved_publish_queue_v2_8.csv"
    )
    rows_after = list(csv.DictReader(queue_path.open("r", encoding="utf-8")))
    tk = next(r for r in rows_after if r["platform"] == "TikTok")
    assert tk["publish_state"] == "queued", "TikTok row must remain untouched"


def test_scheduled_autonomous_claim_queue_ids_match_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """claim.queue_ids must equal the queue IDs actually processed."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    ig_c = _connector_script(
        tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=True,
    )
    fb_c = _connector_script(
        tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True,
    )
    rows[0]["connector_path"] = str(ig_c.relative_to(tmp_path).as_posix())
    rows[1]["connector_path"] = str(fb_c.relative_to(tmp_path).as_posix())
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )

    assert report["ok"] is True
    claim_path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims"
        / "2026-07-19" / "morning-slot-001.json"
    )
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    processed_ids = sorted(item["queue_id"] for item in report["processed"])
    assert sorted(claim["queue_ids"]) == processed_ids


# ── Fix 2: orphaned lock ──────────────────────────────────────────────────────

def test_scheduled_autonomous_fresh_orphan_lock_blocks_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lock file with no claim JSON and fresh mtime must block the run."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    lock_path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims"
        / "2026-07-19" / "morning-slot-001.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")

    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(
            day="2026-07-19",
            slot_keyword="morning",
            limit=1,
            dry_run=False,
            policy_path=policy_path,
        )
    assert excinfo.value.code == (
        "autonomous_lock_orphaned_fresh_manual_recovery_required"
    )


def test_scheduled_autonomous_stale_orphan_lock_is_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale orphaned lock (no claim JSON, mtime > lease) must be removed
    and the run must proceed; new claim must record stale_lock_recovery."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    ig_c = _connector_script(
        tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=True,
    )
    fb_c = _connector_script(
        tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True,
    )
    rows[0]["connector_path"] = str(ig_c.relative_to(tmp_path).as_posix())
    rows[1]["connector_path"] = str(fb_c.relative_to(tmp_path).as_posix())
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    lock_path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims"
        / "2026-07-19" / "morning-slot-001.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")
    stale_ts = time.time() - 3600  # 2× the 1800-second lease
    os.utime(lock_path, (stale_ts, stale_ts))

    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )

    assert report["ok"] is True
    assert report["posted_count"] == 2
    assert not lock_path.exists(), "stale lock file must be removed"
    claim_path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue_claims"
        / "2026-07-19" / "morning-slot-001.json"
    )
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["stale_lock_recovery"] is not None
    assert claim["stale_lock_recovery"]["recovered_stale_lock"] is True


def test_lock_file_is_stale_returns_false_when_stat_unavailable(
    tmp_path: Path,
) -> None:
    """_lock_file_is_stale must return False (fail closed) when stat fails."""
    lock_path = tmp_path / "ghost.lock"
    policy: dict = {"queue_claim_lease_seconds": 1800}
    result = autopublish._lock_file_is_stale(lock_path, policy)
    assert result is False


# ── Fix 3: policy expiry ──────────────────────────────────────────────────────

def test_scheduled_autonomous_policy_expiry_missing_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(
        tmp_path, enabled=True, authority_commit="a" * 40,
        omit_expires=True,
    )
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(
            day="2026-07-19",
            slot_keyword="morning",
            limit=1,
            dry_run=False,
            policy_path=policy_path,
        )
    assert excinfo.value.code == "autonomous_policy_expiry_missing"


def test_scheduled_autonomous_policy_expiry_malformed_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(
        tmp_path, enabled=True, authority_commit="a" * 40,
        expires="NOT-A-DATE",
    )
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(
            day="2026-07-19",
            slot_keyword="morning",
            limit=1,
            dry_run=False,
            policy_path=policy_path,
        )
    assert excinfo.value.code == "autonomous_policy_expiry_malformed"


def test_scheduled_autonomous_policy_expiry_naive_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(
        tmp_path, enabled=True, authority_commit="a" * 40,
        expires="2099-12-31T23:59:59",
    )
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(
            day="2026-07-19",
            slot_keyword="morning",
            limit=1,
            dry_run=False,
            policy_path=policy_path,
        )
    assert excinfo.value.code == "autonomous_policy_expiry_malformed"


def test_scheduled_autonomous_policy_expired_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(
        tmp_path, enabled=True, authority_commit="a" * 40,
        expires="2020-01-01T00:00:00Z",
    )
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    with pytest.raises(autopublish.AutopublishError) as excinfo:
        autopublish.run_scheduled_autonomous(
            day="2026-07-19",
            slot_keyword="morning",
            limit=1,
            dry_run=False,
            policy_path=policy_path,
        )
    assert excinfo.value.code == "autonomous_policy_expired"


def test_scheduled_autonomous_policy_valid_future_expiry_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(
        tmp_path, enabled=True, authority_commit="a" * 40,
        expires="2099-01-01T00:00:00Z",
    )
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    ig_c = _connector_script(
        tmp_path, "lena_publish_instagram_feed_v2_8.py", ok=True,
    )
    fb_c = _connector_script(
        tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True,
    )
    rows[0]["connector_path"] = str(ig_c.relative_to(tmp_path).as_posix())
    rows[1]["connector_path"] = str(fb_c.relative_to(tmp_path).as_posix())
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)
    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )
    assert report["ok"] is True
    assert report["posted_count"] == 2


# ── Fix 4: connector JSON fallback + ambiguous ────────────────────────────────

def test_connector_diagnostic_lines_then_json_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Connector that emits diagnostic lines then a JSON line is parsed
    correctly via the last-line fallback."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))

    diag = tmp_path / "tools" / "publishers" / "lena_publish_diag_v2_8.py"
    diag.parent.mkdir(parents=True, exist_ok=True)
    diag_code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "p = Path(sys.argv[sys.argv.index('--payload')+1])\n"
        "payload = json.loads(p.read_text(encoding='utf-8'))\n"
        "print('Uploading asset to CDN...')\n"
        "print('Calling Meta Graph API...')\n"
        "print(json.dumps({"
        "'ok':True,'posted':True,"
        "'post_id':payload['queue_id']+'-diag',"
        "'post_url':'https://example.invalid/diag',"
        "'posted_at':'2026-07-19T09:30:00'"
        "}))\n"
    )
    diag.write_text(diag_code, encoding="utf-8")

    fb_c = _connector_script(
        tmp_path, "lena_publish_facebook_page_v2_8.py", ok=True,
    )
    rows[0]["connector_path"] = str(diag.relative_to(tmp_path).as_posix())
    rows[1]["connector_path"] = str(fb_c.relative_to(tmp_path).as_posix())
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )

    assert report["ok"] is True
    assert report["posted_count"] == 2, (
        "diagnostic connector must parse the last JSON line"
    )


def test_connector_ambiguous_output_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Connector exits 0 with unparseable stdout → row marked
    connector_ambiguous and attempt_count must not be incremented."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))

    amb = tmp_path / "tools" / "publishers" / "lena_publish_ambiguous_v2_8.py"
    amb.parent.mkdir(parents=True, exist_ok=True)
    amb.write_text(
        "import sys\n"
        "print('Posted but response was XML not JSON: <ok/>')\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    fb_c = _connector_script(
        tmp_path, "lena_publish_facebook_page_v2_8.py", ok=False,
        reason="connector_failed",
    )
    rows[0]["connector_path"] = str(amb.relative_to(tmp_path).as_posix())
    rows[1]["connector_path"] = str(fb_c.relative_to(tmp_path).as_posix())
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )

    assert report["ok"] is True
    assert report["ambiguous_count"] == 1

    queue_path = (
        tmp_path / "pipeline" / "publishing" / "lena" / "approved_queue"
        / "2026-07-19" / "lena_approved_publish_queue_v2_8.csv"
    )
    rows_after = list(csv.DictReader(queue_path.open("r", encoding="utf-8")))
    ig_row = next(r for r in rows_after if r["platform"] == "Instagram Feed")
    assert ig_row["publish_state"] == "connector_ambiguous"
    assert ig_row["attempt_count"] == "0", (
        "attempt_count must not increment for ambiguous outcomes"
    )


# ── Note 6: fully-posted slot is an idempotent no-op ─────────────────────────

def test_scheduled_autonomous_fully_posted_slot_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When all rows for the slot are already posted, return ok=True with
    slot_fully_posted=True and zero publish calls."""
    _patch_tree(monkeypatch, tmp_path)
    policy_path = _policy(tmp_path, enabled=True, authority_commit="a" * 40)
    _manifest(tmp_path)
    rows = _base_rows(tmp_path, _sha(policy_path))
    for row in rows:
        row["publish_state"] = "posted"
        row["posted_at"] = "2026-07-19T09:00:00"
        row["post_url"] = "https://example.invalid/already"
    _queue_rows(tmp_path, rows=rows)
    _patch_git_commit(monkeypatch, "a" * 40)

    report = autopublish.run_scheduled_autonomous(
        day="2026-07-19",
        slot_keyword="morning",
        limit=1,
        dry_run=False,
        policy_path=policy_path,
    )

    assert report["ok"] is True
    assert report.get("slot_fully_posted") is True
    assert report["publish_calls_performed"] == 0
    assert report["provider_calls_performed"] == 0
    assert report["queue_mutated"] is False
