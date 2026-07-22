from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SYNC_POSTED = ROOT / "tools" / "lena_sync_posted_queue_to_post_log_v1.py"
POLICY_PATH = ROOT / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_policy_v2_8.json"
MANIFEST_PATH = ROOT / "pipeline" / "influencer_nodes" / "lena" / "approved_queue_auto_publisher_manifest_v2_8.json"
QUEUE_ROOT = ROOT / "pipeline" / "publishing" / "lena" / "approved_queue"
CLAIM_ROOT = ROOT / "pipeline" / "publishing" / "lena" / "approved_queue_claims"
RECEIPT_ROOT = ROOT / "pipeline" / "publishing" / "lena" / "approved_queue_receipts"
REPORT_ROOT = ROOT / "pipeline" / "publishing" / "lena" / "dispatch_reports"
DISPATCH_OUTBOX = ROOT / "pipeline" / "publishing" / "lena" / "dispatch_outbox"
QUEUE_FIELDS = [
    "queue_id","date","created_at","slot_id","schedule_slot","platform","media_type","lane","asset_status","asset_path","asset_sha256",
    "growth_bucket","hook_category","audio_name",
    "caption","short_caption","pinned_comment","story_prompt","story_poll","post_poll","keyword_notes",
    "public_text_score","public_text_decision","publish_state","publish_mode","connector_path",
    "post_url","posted_at","failure_reason","attempt_count","notes",
    "candidate_artifact_sha256","prompt_sha256","packet_sha256","handoff_sha256","approval_sha256",
    "execution_receipt_sha256","manifest_sha256","qa_sha256","clean_export_report_path","clean_export_report_sha256"
]
AUTONOMOUS_SLOT_KEYWORDS = {"morning", "afternoon", "evening"}


class AutopublishError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise AutopublishError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutopublishError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AutopublishError(code, f"{label} must be a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise AutopublishError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _resolve_repo_path(raw: str) -> Path:
    path = Path(str(raw).replace("\\", "/").strip())
    return path if path.is_absolute() else (ROOT / path)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_policy(policy_path: Path = POLICY_PATH) -> dict[str, Any]:
    return _read_json_object(policy_path, code="autonomous_policy_missing_or_invalid", label="autonomous publish policy artifact")


def _policy_sha256(policy_path: Path) -> str:
    return _sha256_file(policy_path)


def _is_git_ancestor(repo_root: Path, ancestor_commit: str, descendant_commit: str) -> bool:
    try:
        subprocess.check_output(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                ancestor_commit,
                descendant_commit,
            ],
            cwd=str(repo_root),
            text=True,
        )
        return True
    except Exception:
        return False


def _validate_policy_artifact(policy_path: Path) -> dict[str, Any]:
    policy_path = policy_path.resolve()
    policy = load_policy(policy_path)
    if policy.get("policy_id") != "lena_approved_queue_auto_publisher_policy_v2_8":
        raise AutopublishError("autonomous_policy_id_invalid", "policy_id must match the autonomous queue publisher contract")
    if policy.get("policy_version") != "v2.8.0":
        raise AutopublishError("autonomous_policy_version_invalid", "policy_version must be v2.8.0")
    if policy.get("autonomous_mode") != "scheduled_autonomous":
        raise AutopublishError("autonomous_mode_invalid", "policy must describe the scheduled autonomous mode")
    if policy.get("manual_live_mode_unchanged") is not True:
        raise AutopublishError("manual_live_mode_changed", "manual-live behavior must remain unchanged")
    if policy.get("autonomous_enabled") is not True:
        raise AutopublishError("autonomous_policy_disabled", "autonomous mode is disabled by policy")
    if policy.get("autonomous_enabled_by_default") is not False:
        raise AutopublishError("autonomous_policy_default_enabled", "autonomous mode must be disabled by default")
    if policy.get("repository_name") != "delapilena-max/lenadelapi_website":
        raise AutopublishError("autonomous_policy_repository_invalid", "repository_name must bind the Lena repo")
    if str(policy.get("authority_version") or "").strip() != "main":
        raise AutopublishError("autonomous_policy_authority_version_invalid", "authority_version must be main")
    current_commit = ""
    try:
        current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        current_commit = ""
    if not current_commit:
        raise AutopublishError("autonomous_policy_repository_commit_unavailable", "unable to read current repository commit")
    authority_commit = str(policy.get("authority_commit") or "").strip()
    if not authority_commit:
        raise AutopublishError("autonomous_policy_authority_commit_missing", "authority_commit is required")
    if not _is_git_ancestor(ROOT, authority_commit, current_commit):
        raise AutopublishError("autonomous_policy_stale", "autonomous policy does not match current repository authority")
    approved_slots = {str(item).strip().lower() for item in policy.get("approved_slots", []) if str(item).strip()}
    if approved_slots != AUTONOMOUS_SLOT_KEYWORDS:
        raise AutopublishError("autonomous_policy_slots_invalid", "approved_slots must be morning, afternoon, and evening")
    if int(policy.get("hard_item_limit_per_invocation", 0)) != 1:
        raise AutopublishError("autonomous_policy_item_limit_invalid", "hard_item_limit_per_invocation must be one")
    if int(policy.get("queue_claim_lease_seconds", 0)) < 300:
        raise AutopublishError("autonomous_policy_claim_lease_invalid", "queue_claim_lease_seconds must be a reasonable positive lease")
    if int(policy.get("max_attempts_per_row", 0)) < 1:
        raise AutopublishError("autonomous_policy_retry_cap_invalid", "max_attempts_per_row must be positive")
    if policy.get("allow_replies") is not False or policy.get("allow_dms") is not False or policy.get("allow_outreach") is not False:
        raise AutopublishError("autonomous_policy_outreach_invalid", "replies, DMs, and outreach must remain disabled")
    if policy.get("require_queue_build_before_first_publish_slot") is not True:
        raise AutopublishError("autonomous_policy_queue_build_invalid", "queue build must be required before the first slot")
    if policy.get("require_clean_export_revalidation") is not True:
        raise AutopublishError("autonomous_policy_clean_export_invalid", "clean-export revalidation must be required")
    if policy.get("require_atomic_queue_claim") is not True:
        raise AutopublishError("autonomous_policy_claim_required_invalid", "atomic queue claim must be required")
    if policy.get("require_platform_receipts") is not True:
        raise AutopublishError("autonomous_policy_receipts_required_invalid", "platform receipts must be required")
    if policy.get("require_idempotent_post_log_sync") is not True:
        raise AutopublishError(
            "autonomous_policy_sync_required_invalid",
            "post-log sync must be required",
        )
    allowed_pf = {
        str(p) for p in policy.get("autonomous_queue_platforms", [])
    }
    if not allowed_pf:
        raise AutopublishError(
            "autonomous_policy_platforms_missing",
            "autonomous_queue_platforms must be non-empty in the policy",
        )
    expires_raw = str(
        policy.get("policy_expires_at_utc") or ""
    ).strip()
    if not expires_raw:
        raise AutopublishError(
            "autonomous_policy_expiry_missing",
            "policy_expires_at_utc is required",
        )
    try:
        _expiry = datetime.fromisoformat(
            expires_raw.replace("Z", "+00:00")
        )
    except ValueError:
        raise AutopublishError(
            "autonomous_policy_expiry_malformed",
            f"policy_expires_at_utc not valid ISO-8601: {expires_raw!r}",
        )
    if _expiry.tzinfo is None:
        raise AutopublishError(
            "autonomous_policy_expiry_malformed",
            "policy_expires_at_utc must be timezone-aware UTC",
        )
    if _expiry <= _now_utc():
        raise AutopublishError(
            "autonomous_policy_expired",
            f"policy has expired at {expires_raw}",
        )
    return {
        "path": policy_path,
        "sha256": _policy_sha256(policy_path),
        "artifact": policy,
        "authority_commit": current_commit,
    }


def _manifest_checks(manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = _read_json_object(manifest_path, code="autonomous_manifest_missing_or_invalid", label="autonomous publish manifest artifact")
    boundary = manifest.get("boundary", {})
    safety = manifest.get("safety", {})
    operations = manifest.get("operations", {})
    if boundary.get("autonomous_enabled_by_default") is not False:
        raise AutopublishError("autonomous_manifest_default_enabled", "manifest must state autonomous mode is disabled by default")
    if boundary.get("manual_live_mode_unchanged") is not True:
        raise AutopublishError("autonomous_manifest_manual_live_changed", "manual-live mode must remain unchanged")
    if boundary.get("auto_replying") is not False or boundary.get("auto_dm_sending") is not False or boundary.get("auto_outreach") is not False:
        raise AutopublishError("autonomous_manifest_outreach_invalid", "manifest must keep replies, DMs, and outreach disabled")
    if operations.get("slot_limit_per_invocation") != 1:
        raise AutopublishError("autonomous_manifest_slot_limit_invalid", "manifest must cap each invocation to one slot")
    if sorted(str(s).lower() for s in operations.get("slot_keywords", [])) != sorted(AUTONOMOUS_SLOT_KEYWORDS):
        raise AutopublishError("autonomous_manifest_slots_invalid", "manifest must document morning, afternoon, and evening slots")
    if safety.get("duplicate_prevention") is not True or safety.get("already_posted_skip") is not True or safety.get("bounded_retries") is not True:
        raise AutopublishError("autonomous_manifest_safety_invalid", "manifest must preserve duplicate prevention, already-posted skip, and bounded retries")
    return {"path": manifest_path, "sha256": _sha256_file(manifest_path), "artifact": manifest}


def _queue_path(day: str) -> Path:
    return QUEUE_ROOT / day / "lena_approved_publish_queue_v2_8.csv"


def _claim_path(day: str, slot_id: str) -> Path:
    return CLAIM_ROOT / day / f"{slot_id}.json"


def _claim_lock_path(day: str, slot_id: str) -> Path:
    return CLAIM_ROOT / day / f"{slot_id}.lock"


def _receipt_path(day: str, slot_id: str, queue_id: str, platform: str) -> Path:
    safe_platform = "".join(c if c.isalnum() or c in "-_" else "_" for c in platform)
    return RECEIPT_ROOT / day / slot_id / f"{queue_id}_{safe_platform}_publish_receipt.json"


def _load_queue(day: str) -> tuple[Path, list[dict[str, str]]]:
    path = _queue_path(day)
    if not path.exists():
        return path, []
    return path, list(csv.DictReader(path.open("r", encoding="utf-8")))


def _write_queue(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(raw)
    try:
        with temp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS)
            writer.writeheader()
            writer.writerows([{key: row.get(key, "") for key in QUEUE_FIELDS} for row in rows])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _parse_json_stdout(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("{") or raw.startswith("["):
        try:
            result = json.loads(raw)
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            pass
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line and (
            line.startswith("{") or line.startswith("[")
        ):
            try:
                result = json.loads(line)
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                pass
            break
    return None


def _connector_payload(row: dict[str, str]) -> dict[str, str]:
    return {
        "queue_id": row.get("queue_id", ""),
        "date": row.get("date", ""),
        "platform": row.get("platform", ""),
        "slot_id": row.get("slot_id", ""),
        "asset_path": row.get("asset_path", ""),
        "media_type": row.get("media_type", ""),
        "caption": row.get("caption", ""),
        "pinned_comment": row.get("pinned_comment", ""),
        "story_prompt": row.get("story_prompt", ""),
        "post_poll": row.get("post_poll", ""),
        "keyword_notes": row.get("keyword_notes", ""),
        "lane": row.get("lane", ""),
    }


def _run_connector(row: dict[str, str], *, dry_run: bool = False) -> dict[str, Any]:
    connector = row.get("connector_path") or ""
    payload = _connector_payload(row)
    outbox = DISPATCH_OUTBOX / row.get("date", "")
    outbox.mkdir(parents=True, exist_ok=True)
    safe_platform = "".join(c if c.isalnum() or c in "-_" else "_" for c in row.get("platform", "platform"))
    payload_path = outbox / f"{row.get('queue_id')}_{safe_platform}_payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if dry_run:
        return {"ok": True, "dry_run": True, "posted": False, "reason": "dry_run_preview_only_queue_not_mutated", "payload": str(payload_path)}
    if not connector:
        return {"ok": False, "posted": False, "reason": "missing_connector_path", "payload": str(payload_path)}
    connector_path = ROOT / connector
    if not connector_path.exists():
        return {"ok": False, "posted": False, "reason": f"connector_not_installed: {connector}", "payload": str(payload_path)}
    proc = subprocess.run(
        [PY, str(connector_path), "--payload", str(payload_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    parsed = _parse_json_stdout(proc.stdout)
    data: dict[str, Any]
    if parsed is not None:
        data = (
            parsed if isinstance(parsed, dict)
            else {"ok": False, "raw": proc.stdout}
        )
    elif proc.returncode == 0 and (proc.stdout or "").strip():
        data = {
            "ok": False,
            "posted": False,
            "ambiguous": True,
            "reason": "connector_result_ambiguous",
            "raw_stdout": proc.stdout[-500:],
            "stderr": proc.stderr[-500:],
        }
    else:
        data = {
            "ok": False,
            "raw_stdout": proc.stdout[-1000:],
            "stderr": proc.stderr[-1000:],
        }
    data["returncode"] = proc.returncode
    data["connector"] = connector
    data["payload"] = str(payload_path)
    if proc.returncode != 0:
        data["ok"] = False
    return data


def _read_existing_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        return list(csv.DictReader(path.open("r", encoding="utf-8")))
    except Exception:
        return []


def _find_index(rows: list[dict[str, str]], queue_id: str, platform: str) -> int:
    for idx, row in enumerate(rows):
        if row.get("queue_id", "") == queue_id and row.get("platform", "") == platform:
            return idx
    return -1


def _ensure_note(notes: str, token: str) -> str:
    base = (notes or "").strip()
    if token in base:
        return base
    return token if not base else f"{base} | {token}"


def _update_post_logs(rows: list[dict[str, str]], queue_ids: list[str], *, queue_limit: int) -> dict[str, Any]:
    post_log_path = ROOT / "pipeline" / "analytics" / "lena_manual_post_log_v2_7.csv"
    metrics_path = ROOT / "pipeline" / "analytics" / "lena_post_metrics_v1_6_1.csv"
    post_fields = [
        "date","posted_at","platform","slot_id","asset_path","media_type","lane","growth_bucket",
        "hook_category","post_url","audio_name","caption","pinned_comment","post_poll","story_poll",
        "music_selected","manual_publish_approved","notes"
    ]
    metric_fields = [
        "date","slot_id","platform","media_type","growth_bucket","lane","hook_category","post_url",
        "audio_name","reach","likes","saves","shares","comments","follows","profile_visits",
        "completion_rate","replay_rate","score","classification","notes"
    ]

    def read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        return list(csv.DictReader(path.open("r", encoding="utf-8")))

    def write_csv(path: Path, fields: list[str], rows_in: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows([{key: row.get(key, "") for key in fields} for row in rows_in])

    def canonical_from_row(row: dict[str, str]) -> dict[str, str]:
        return {
            "date": row.get("date", ""),
            "posted_at": row.get("posted_at", "") or _iso_now(),
            "platform": row.get("platform", ""),
            "slot_id": row.get("slot_id", ""),
            "asset_path": row.get("asset_path", ""),
            "media_type": row.get("media_type", ""),
            "lane": row.get("lane", ""),
            "growth_bucket": row.get("growth_bucket", ""),
            "hook_category": row.get("hook_category", ""),
            "post_url": row.get("post_url", ""),
            "audio_name": row.get("audio_name", ""),
            "caption": row.get("caption", ""),
            "pinned_comment": row.get("pinned_comment", ""),
            "post_poll": row.get("post_poll", ""),
            "story_poll": row.get("story_poll", "") or row.get("story_prompt", ""),
            "music_selected": "true" if row.get("media_type", "") == "photo" or row.get("audio_name", "") else "false",
            "manual_publish_approved": "true",
            "notes": _ensure_note("", f"auto_synced_from_queue:{row.get('queue_id', '')}"),
        }

    post_rows = read_csv(post_log_path)
    metric_rows = read_csv(metrics_path)
    updated_post_ids: list[str] = []
    for row in rows:
        if row.get("queue_id", "") not in queue_ids:
            continue
        canon = canonical_from_row(row)
        key = (canon["date"], canon["slot_id"], canon["platform"])
        post_idx = next((i for i, r in enumerate(post_rows) if (r.get("date", ""), r.get("slot_id", ""), r.get("platform", "")) == key), -1)
        if post_idx >= 0:
            target = dict(post_rows[post_idx])
            for field in post_fields:
                if canon.get(field):
                    target[field] = canon[field]
            post_rows[post_idx] = target
        else:
            post_rows.append({field: canon.get(field, "") for field in post_fields})

        metric_idx = next((i for i, r in enumerate(metric_rows) if (r.get("date", ""), r.get("slot_id", ""), r.get("platform", "")) == key), -1)
        if metric_idx >= 0:
            target = dict(metric_rows[metric_idx])
            for field in ("media_type", "growth_bucket", "lane", "hook_category", "post_url", "audio_name"):
                if canon.get(field):
                    target[field] = canon[field]
            metric_rows[metric_idx] = target
        else:
            metric_rows.append(
                {
                    "date": canon["date"],
                    "slot_id": canon["slot_id"],
                    "platform": canon["platform"],
                    "media_type": canon["media_type"],
                    "growth_bucket": canon["growth_bucket"],
                    "lane": canon["lane"],
                    "hook_category": canon["hook_category"],
                    "post_url": canon["post_url"],
                    "audio_name": canon["audio_name"],
                    "reach": 0,
                    "likes": 0,
                    "saves": 0,
                    "shares": 0,
                    "comments": 0,
                    "follows": 0,
                    "profile_visits": 0,
                    "completion_rate": 0,
                    "replay_rate": 0,
                    "score": 0,
                    "classification": "pending",
                    "notes": f"Auto-synced from posted queue {row.get('queue_id', '')}; update metrics after performance data is available.",
                }
            )
        updated_post_ids.append(row.get("queue_id", ""))

    write_csv(post_log_path, post_fields, post_rows)
    write_csv(metrics_path, metric_fields, metric_rows)
    feedback_refresh = None
    refresh_path = ROOT / "tools" / "lena_refresh_post_feedback_loop_v1.py"
    if updated_post_ids and refresh_path.exists():
        proc = subprocess.run(
            [PY, str(refresh_path), "--date", rows[0].get("date", date.today().isoformat()), "--queue-limit", str(queue_limit)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        feedback_refresh = {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
        }
    return {
        "ok": True,
        "post_log": str(post_log_path),
        "metrics_csv": str(metrics_path),
        "updated_post_ids": updated_post_ids,
        "feedback_refresh": feedback_refresh,
    }


def _read_sidecar(asset_path: Path) -> dict[str, Any]:
    sidecar = asset_path.with_suffix(".status.json")
    if not sidecar.exists():
        raise AutopublishError("clean_export_missing_sidecar", f"publish approval sidecar is missing: {sidecar}")
    return _read_json_object(sidecar, code="clean_export_sidecar_invalid", label="publish approval sidecar")


def _validate_clean_export(row: dict[str, str], policy: dict[str, Any]) -> dict[str, Any]:
    from tools.publishers.lena_meta_publish_common_v2_9 import check_final_publish_approval

    payload = _connector_payload(row)
    gate = check_final_publish_approval(payload)
    if not gate.get("ok"):
        raise AutopublishError("clean_export_gate_failed", str(gate.get("reason", "publish approval gate failed")))
    asset_path = _resolve_repo_path(row.get("asset_path", ""))
    if not asset_path.exists():
        raise AutopublishError("clean_export_asset_missing", f"asset file missing: {asset_path}")
    sidecar = _read_sidecar(asset_path)
    if sidecar.get("authorization_mode") != "standing_autonomy_policy":
        raise AutopublishError("clean_export_authorization_mode_invalid", "publish approval sidecar must use standing autonomy policy")
    if str(sidecar.get("policy_id") or "") != str(policy.get("policy_id") or ""):
        raise AutopublishError("clean_export_policy_id_mismatch", "publish approval sidecar policy_id mismatch")
    policy_path = Path(str(policy.get("_policy_path") or POLICY_PATH))
    if str(sidecar.get("policy_sha256") or "") != _policy_sha256(policy_path):
        raise AutopublishError("clean_export_policy_sha256_mismatch", "publish approval sidecar policy_sha256 mismatch")
    if sidecar.get("qa_approved") is not True or sidecar.get("identity_verified") is not True or sidecar.get("duplicate_check_passed") is not True:
        raise AutopublishError("clean_export_quality_gate_failed", "publish approval sidecar is missing required standing-autonomy QA fields")
    if sidecar.get("publish_authorized_by_policy") is not True:
        raise AutopublishError("clean_export_publish_authority_missing", "publish approval sidecar must be authorized by policy")
    if sidecar.get("human_per_cycle_approval_required") is not False or sidecar.get("human_per_cycle_approval_present") is not False:
        raise AutopublishError("clean_export_human_approval_invalid", "clean export must not require human approval")
    sidecar_asset_path = _resolve_repo_path(str(sidecar.get("asset_path") or ""))
    if sidecar_asset_path.resolve() != asset_path.resolve():
        raise AutopublishError("clean_export_asset_path_mismatch", "publish approval sidecar asset path mismatch")
    if str(sidecar.get("target_platform") or "") != str(row.get("platform") or ""):
        raise AutopublishError("clean_export_platform_mismatch", "publish approval sidecar platform mismatch")
    if str(sidecar.get("caption") or "") != str(row.get("caption") or ""):
        raise AutopublishError("clean_export_caption_mismatch", "publish approval sidecar caption mismatch")
    for sha_key in ("asset_sha256", "generated_image_sha256", "saved_image_sha256"):
        if sidecar.get(sha_key):
            actual_sha = _sha256_file(asset_path)
            if str(sidecar.get(sha_key) or "") != actual_sha:
                raise AutopublishError("clean_export_asset_sha_mismatch", f"publish approval sidecar {sha_key} mismatch")
            break
    if sidecar.get("controlled_photo_autonomy") is True:
        from tools import lena_prepare_privacy_clean_photo_v1 as clean_photo

        report_path = _resolve_repo_path(str(sidecar.get("clean_export_report_path") or ""))
        report = clean_photo.validate_privacy_clean_report(report_path, expected_output_path=asset_path)
        if str(sidecar.get("clean_export_report_sha256") or "") != _sha256_file(report_path):
            raise AutopublishError("clean_export_report_sha_mismatch", "privacy-clean report SHA-256 mismatch")
        if str(sidecar.get("asset_sha256") or "") != report.get("output_sha256"):
            raise AutopublishError("clean_export_asset_sha_mismatch", "publish sidecar is not bound to the privacy-clean derivative")
        lineage = sidecar.get("lineage")
        if not isinstance(lineage, dict) or lineage != report.get("lineage"):
            raise AutopublishError("clean_export_lineage_mismatch", "publish sidecar lineage differs from the privacy-clean report")
        row_lineage = {
            "candidate_artifact_sha256": row.get("candidate_artifact_sha256", ""),
            "prompt_sha256": row.get("prompt_sha256", ""),
            "packet_sha256": row.get("packet_sha256", ""),
            "handoff_sha256": row.get("handoff_sha256", ""),
            "approval_sha256": row.get("approval_sha256", ""),
            "execution_receipt_sha256": row.get("execution_receipt_sha256", ""),
            "manifest_sha256": row.get("manifest_sha256", ""),
            "qa_sha256": row.get("qa_sha256", ""),
        }
        if row_lineage != lineage:
            raise AutopublishError("clean_export_queue_lineage_mismatch", "queue row lineage differs from the verified clean export")
        if row.get("asset_sha256") != report.get("output_sha256"):
            raise AutopublishError("clean_export_queue_asset_sha_mismatch", "queue row SHA-256 differs from the verified clean derivative")
        if row.get("clean_export_report_path") != _repo_relative(report_path) or row.get("clean_export_report_sha256") != _sha256_file(report_path):
            raise AutopublishError("clean_export_queue_report_binding_mismatch", "queue row clean-export report binding is invalid")
    return {"sidecar": sidecar, "asset_sha256": _sha256_file(asset_path), "sidecar_sha256": _sha256_file(asset_path.with_suffix(".status.json"))}


def _slot_key_from_row(row: dict[str, str], slot_keyword: str) -> bool:
    scheduled = row.get("schedule_slot", "").strip().lower()
    return scheduled == slot_keyword.lower() if scheduled else slot_keyword.lower() in row.get("slot_id", "").lower()


def _select_autonomous_slot_rows(
    rows: list[dict[str, str]],
    slot_keyword: str,
    policy: dict[str, Any],
) -> tuple[str, list[dict[str, str]]]:
    keyword = (slot_keyword or "").strip().lower()
    if keyword not in AUTONOMOUS_SLOT_KEYWORDS:
        raise AutopublishError(
            "autonomous_slot_invalid",
            "slot_keyword must be morning, afternoon, or evening",
        )
    allowed_platforms = {
        str(item) for item in policy.get("autonomous_queue_platforms", [])
    }
    all_slot = [
        row for row in rows
        if _slot_key_from_row(row, keyword)
        and (
            not allowed_platforms
            or row.get("platform", "") in allowed_platforms
        )
    ]
    if not all_slot:
        raise AutopublishError(
            "autonomous_slot_missing",
            f"no rows found for slot_keyword={keyword!r}",
        )
    eligible = [
        row for row in all_slot
        if row.get("publish_state", "") != "posted"
    ]
    if not eligible:
        raise AutopublishError(
            "autonomous_slot_fully_posted",
            f"all rows for slot_keyword={keyword!r} are already posted",
        )
    slot_ids = {row.get("slot_id", "") for row in eligible}
    if len(slot_ids) != 1:
        raise AutopublishError(
            "autonomous_multiple_slot_candidates",
            (
                f"slot_keyword={keyword!r} matched more than one slot:"
                f" {sorted(slot_ids)!r}"
            ),
        )
    return next(iter(slot_ids)), eligible


def _claim_file_is_stale(claim: dict[str, Any], policy: dict[str, Any]) -> bool:
    try:
        expiry = datetime.fromisoformat(
            str(claim.get("lease_expires_at_utc") or "")
            .replace("Z", "+00:00")
        )
        return expiry <= _now_utc()
    except Exception:
        return True


def _lock_file_is_stale(lock_path: Path, policy: dict[str, Any]) -> bool:
    try:
        mtime = lock_path.stat().st_mtime
        lease = int(policy.get("queue_claim_lease_seconds", 1800))
        age = _now_utc().timestamp() - mtime
        return age > lease
    except Exception:
        return False


def _acquire_slot_claim(day: str, slot_id: str, rows: list[dict[str, str]], policy: dict[str, Any], slot_keyword: str) -> tuple[Path, dict[str, Any]]:
    claim_path = _claim_path(day, slot_id)
    lock_path = _claim_lock_path(day, slot_id)
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    if claim_path.exists():
        existing = _read_json_object(claim_path, code="autonomous_claim_invalid", label="autonomous queue claim")
        if not _claim_file_is_stale(existing, policy):
            raise AutopublishError("autonomous_queue_claim_active", f"slot already claimed: {slot_id}")
        try:
            claim_path.unlink()
        except OSError:
            pass
    stale_lock_recovery: dict[str, Any] | None = None
    if lock_path.exists() and not claim_path.exists():
        if not _lock_file_is_stale(lock_path, policy):
            raise AutopublishError(
                "autonomous_lock_orphaned_fresh_manual_recovery_required",
                (
                    "orphaned lock file is fresh;"
                    f" manual removal required: {lock_path}"
                ),
            )
        try:
            lock_path.unlink()
            stale_lock_recovery = {
                "recovered_stale_lock": True,
                "lock_path": str(lock_path),
            }
        except OSError as exc:
            raise AutopublishError(
                "autonomous_lock_orphaned_removal_failed",
                (
                    "stale orphaned lock could not be removed:"
                    f" {lock_path}: {exc}"
                ),
            ) from exc
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise AutopublishError(
            "autonomous_queue_claim_active",
            f"slot already claimed: {slot_id}",
        )
    try:
        os.close(fd)
        _lease_secs = int(policy.get("queue_claim_lease_seconds", 1800))
        claim = {
            "report_type": "lena_approved_queue_autonomous_claim",
            "schema_version": "v1",
            "date": day,
            "slot_id": slot_id,
            "slot_keyword": slot_keyword,
            "queue_ids": [row.get("queue_id", "") for row in rows],
            "platforms": [row.get("platform", "") for row in rows],
            "claim_id": uuid.uuid4().hex,
            "state": "claimed",
            "claimed_at_utc": _iso_now(),
            "lease_expires_at_utc": (
                _now_utc() + timedelta(seconds=_lease_secs)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "policy_id": policy.get("policy_id"),
            "policy_sha256": policy.get("_policy_sha256", ""),
            "authority_commit": policy.get("authority_commit"),
            "queue_csv": _repo_relative(_queue_path(day)),
            "queue_csv_sha256": _sha256_file(_queue_path(day)),
            "row_count": len(rows),
            "stale_lock_recovery": stale_lock_recovery,
        }
        _write_json_atomic(claim_path, claim)
        return claim_path, claim
    finally:
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass


def _update_claim_state(claim_path: Path, **updates: Any) -> dict[str, Any]:
    claim = _read_json_object(claim_path, code="autonomous_claim_invalid", label="autonomous queue claim")
    claim.update(updates)
    tmp = claim_path.with_name(f"{claim_path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(claim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(claim_path)
    return claim


def _record_receipt(day: str, slot_id: str, row: dict[str, str], connector_result: dict[str, Any], payload_path: Path) -> Path:
    receipt = {
        "report_type": "lena_approved_queue_publish_receipt",
        "schema_version": "v1",
        "date": day,
        "slot_id": slot_id,
        "queue_id": row.get("queue_id", ""),
        "platform": row.get("platform", ""),
        "media_type": row.get("media_type", ""),
        "connector_path": row.get("connector_path", ""),
        "payload_path": _repo_relative(payload_path),
        "payload_sha256": _sha256_file(payload_path),
        "captured_at_utc": _iso_now(),
        "posted": bool(connector_result.get("posted")),
        "post_id": connector_result.get("post_id", ""),
        "post_url": connector_result.get("post_url", ""),
        "provider_result": connector_result,
        "row_snapshot": {key: row.get(key, "") for key in QUEUE_FIELDS},
    }
    receipt_path = _receipt_path(day, slot_id, row.get("queue_id", ""), row.get("platform", ""))
    _write_json_atomic(receipt_path, receipt)
    return receipt_path


def _slot_receipt_exists(day: str, slot_id: str, row: dict[str, str]) -> Path | None:
    receipt_path = _receipt_path(day, slot_id, row.get("queue_id", ""), row.get("platform", ""))
    return receipt_path if receipt_path.exists() else None


def _apply_posted_row_update(row: dict[str, str], connector_result: dict[str, Any]) -> None:
    row["publish_state"] = "posted"
    row["posted_at"] = connector_result.get("posted_at") or _iso_now().replace("Z", "")
    row["post_url"] = connector_result.get("post_url", "")
    row["failure_reason"] = ""
    row["attempt_count"] = "0"
    if connector_result.get("post_id"):
        row["notes"] = _ensure_note(row.get("notes", ""), f"post_id:{connector_result['post_id']}")


def _apply_failed_row_update(row: dict[str, str], reason: str, max_attempts: int) -> None:
    attempts = int(row.get("attempt_count") or 0) + 1
    row["attempt_count"] = str(attempts)
    row["failure_reason"] = reason
    if attempts >= max_attempts:
        row["publish_state"] = "abandoned"
    elif "connector_not_installed" in reason or reason == "missing_connector_path":
        row["publish_state"] = "ready_for_connector"
    else:
        row["publish_state"] = "failed"


def _apply_ambiguous_row_update(
    row: dict[str, str], reason: str
) -> None:
    row["publish_state"] = "connector_ambiguous"
    row["failure_reason"] = reason


def _recover_from_existing_receipt(day: str, slot_id: str, row: dict[str, str], receipt_path: Path) -> dict[str, Any]:
    receipt = _read_json_object(receipt_path, code="autonomous_receipt_invalid", label="publish receipt")
    if not receipt.get("posted"):
        raise AutopublishError("autonomous_receipt_not_posted", f"receipt does not record a published row: {receipt_path}")
    _apply_posted_row_update(row, receipt)
    return {"ok": True, "recovered": True, "receipt_path": str(receipt_path), "receipt": receipt, "posted": True, "post_id": receipt.get("post_id", ""), "post_url": receipt.get("post_url", "")}


def admit_controlled_photo(
    *,
    day: str,
    slot_id: str,
    schedule_slot: str,
    platform: str,
    lane: str,
    asset_path: Path,
    asset_sha256: str,
    caption: str,
    lineage: dict[str, str],
    clean_export_report_path: Path,
    clean_export_report_sha256: str,
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    policy_result = _validate_policy_artifact(policy_path)
    policy = dict(policy_result["artifact"])
    policy["_policy_path"] = str(policy_result["path"])
    policy["_policy_sha256"] = policy_result["sha256"]
    if schedule_slot not in AUTONOMOUS_SLOT_KEYWORDS:
        raise AutopublishError("autonomous_schedule_slot_invalid", "schedule_slot must be morning, afternoon, or evening")
    if platform not in {str(item) for item in policy.get("autonomous_queue_platforms", [])}:
        raise AutopublishError("autonomous_platform_invalid", "platform is outside the autonomous queue policy")
    asset_path = asset_path.resolve(strict=True)
    if _sha256_file(asset_path) != asset_sha256:
        raise AutopublishError("autonomous_asset_sha_mismatch", "queue admission asset SHA-256 mismatch")
    required_lineage = {
        "candidate_artifact_sha256",
        "prompt_sha256",
        "packet_sha256",
        "handoff_sha256",
        "approval_sha256",
        "execution_receipt_sha256",
        "manifest_sha256",
        "qa_sha256",
    }
    if set(lineage) != required_lineage or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in lineage.values()):
        raise AutopublishError("autonomous_lineage_incomplete", "queue admission requires the complete generation and QA SHA lineage")
    connector = {
        "Instagram Feed": "tools/publishers/lena_publish_instagram_feed_v2_8.py",
        "Facebook Page": "tools/publishers/lena_publish_facebook_page_v2_8.py",
    }[platform]
    queue_id = "q_" + hashlib.sha1(f"{day}|{slot_id}|{platform}".encode("utf-8")).hexdigest()[:14]
    row = {
        "queue_id": queue_id,
        "date": day,
        "created_at": _iso_now(),
        "slot_id": slot_id,
        "schedule_slot": schedule_slot,
        "platform": platform,
        "media_type": "photo",
        "lane": lane,
        "asset_status": "approved",
        "asset_path": _repo_relative(asset_path),
        "asset_sha256": asset_sha256,
        "growth_bucket": "controlled_photo_autonomy",
        "hook_category": "",
        "audio_name": "",
        "caption": caption,
        "short_caption": caption,
        "pinned_comment": "",
        "story_prompt": "",
        "story_poll": "",
        "post_poll": "",
        "keyword_notes": "",
        "public_text_score": "100",
        "public_text_decision": "APPROVED",
        "publish_state": "queued",
        "publish_mode": str(policy.get("publish_mode") or "explicit_live_connector_required"),
        "connector_path": connector,
        "post_url": "",
        "posted_at": "",
        "failure_reason": "",
        "attempt_count": "0",
        "notes": "Controlled photo autonomy; exact clean-export and generation lineage required.",
        **lineage,
        "clean_export_report_path": _repo_relative(clean_export_report_path.resolve(strict=True)),
        "clean_export_report_sha256": clean_export_report_sha256,
    }
    _validate_clean_export(row, policy)
    queue_path, existing = _load_queue(day)
    lock_path = queue_path.with_suffix(queue_path.suffix + ".admission.lock")
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AutopublishError("autonomous_queue_admission_active", "another queue admission is active") from exc
    try:
        os.close(fd)
        queue_path, existing = _load_queue(day)
        matches = [item for item in existing if item.get("queue_id") == queue_id and item.get("platform") == platform]
        canonical_row = {key: row.get(key, "") for key in QUEUE_FIELDS}
        if matches:
            if len(matches) != 1 or {key: matches[0].get(key, "") for key in QUEUE_FIELDS} != canonical_row:
                raise AutopublishError("autonomous_queue_conflict", "existing queue row conflicts with the exact controlled-lane admission")
            return {"ok": True, "reused": True, "queue_path": str(queue_path), "queue_id": queue_id, "row": canonical_row}
        if any(item.get("slot_id") == slot_id and item.get("publish_state") != "posted" for item in existing):
            raise AutopublishError("autonomous_slot_queue_conflict", "slot already has a non-posted queue row")
        _write_queue(queue_path, [*existing, canonical_row])
    finally:
        lock_path.unlink(missing_ok=True)
    return {"ok": True, "reused": False, "queue_path": str(queue_path), "queue_id": queue_id, "row": canonical_row}


def run_scheduled_autonomous(*, day: str, slot_keyword: str, limit: int, dry_run: bool, policy_path: Path = POLICY_PATH) -> dict[str, Any]:
    policy_result = _validate_policy_artifact(policy_path)
    policy = dict(policy_result["artifact"])
    policy["_policy_path"] = str(policy_result["path"])
    policy["_policy_sha256"] = policy_result["sha256"]
    if limit not in (0, 1):
        raise AutopublishError("autonomous_limit_invalid", "scheduled autonomous mode enforces a hard limit of one slot per invocation")
    if not dry_run and int(policy.get("hard_item_limit_per_invocation", 1)) != 1:
        raise AutopublishError("autonomous_policy_item_limit_invalid", "policy hard item limit must be one")

    queue_path, rows = _load_queue(day)
    if not rows:
        raise AutopublishError(
            "approved_queue_missing",
            f"missing/empty queue: {queue_path}",
        )
    try:
        q_mtime = datetime.fromtimestamp(
            queue_path.stat().st_mtime, tz=timezone.utc
        )
        if q_mtime.date() < date.fromisoformat(day):
            raise AutopublishError(
                "approved_queue_stale",
                (
                    f"queue last modified {q_mtime.date().isoformat()},"
                    f" expected {day}; run queue builder first"
                ),
            )
    except AutopublishError:
        raise
    except Exception:
        pass
    try:
        slot_id, slot_rows = _select_autonomous_slot_rows(
            rows, slot_keyword, policy
        )
    except AutopublishError as exc:
        if exc.code == "autonomous_slot_fully_posted":
            return {
                "ok": True,
                "version": "v2.8.5",
                "date": day,
                "mode": "scheduled_autonomous",
                "dry_run": dry_run,
                "slot_keyword": slot_keyword,
                "slot_id": "",
                "queue_csv": str(queue_path),
                "policy_path": str(policy_result["path"]),
                "policy_sha256": policy_result["sha256"],
                "publish_calls_performed": 0,
                "provider_calls_performed": 0,
                "queue_mutated": False,
                "posted_count": 0,
                "failed_count": 0,
                "abandoned_count": 0,
                "ambiguous_count": 0,
                "processed": [],
                "recovered_queue_ids": [],
                "posted_queue_ids": [],
                "slot_fully_posted": True,
                "detail": exc.detail,
            }
        raise
    changed_rows = [dict(row) for row in rows]
    _allowed_pf = {
        str(p) for p in policy.get("autonomous_queue_platforms", [])
    }
    slot_changed_rows = [
        row for row in changed_rows
        if row.get("slot_id", "") == slot_id
        and (
            not _allowed_pf
            or row.get("platform", "") in _allowed_pf
        )
    ]
    claim_path: Path | None = None
    claim: dict[str, Any] | None = None
    processed: list[dict[str, Any]] = []
    posted_queue_ids: list[str] = []
    recovered_queue_ids: list[str] = []
    publish_calls = 0

    if not dry_run:
        claim_path, claim = _acquire_slot_claim(day, slot_id, slot_rows, policy, slot_keyword)

    try:
        for row in slot_changed_rows:
            if row.get("publish_state", "") == "posted":
                continue
            receipt_path = _slot_receipt_exists(day, slot_id, row)
            if receipt_path and not dry_run:
                recovery = _recover_from_existing_receipt(day, slot_id, row, receipt_path)
                recovered_queue_ids.append(row.get("queue_id", ""))
                processed.append({"queue_id": row.get("queue_id", ""), "platform": row.get("platform", ""), "slot_id": row.get("slot_id", ""), "result": recovery, "state_after": row.get("publish_state", "")})
                continue

            clean_export = _validate_clean_export(row, policy)
            if dry_run:
                processed.append({"queue_id": row.get("queue_id", ""), "platform": row.get("platform", ""), "slot_id": row.get("slot_id", ""), "result": {"ok": True, "dry_run": True, "clean_export": clean_export}, "state_after": row.get("publish_state", "")})
                continue

            result = _run_connector(row, dry_run=False)
            publish_calls += 1
            payload_path = _resolve_repo_path(str(result.get("payload", "")))
            if result.get("ok") and result.get("posted"):
                receipt_path = _record_receipt(day, slot_id, row, result, payload_path)
                _apply_posted_row_update(row, result)
                posted_queue_ids.append(row.get("queue_id", ""))
                processed.append({"queue_id": row.get("queue_id", ""), "platform": row.get("platform", ""), "slot_id": row.get("slot_id", ""), "result": {"ok": True, "posted": True, "receipt_path": str(receipt_path)}, "state_after": row.get("publish_state", "")})
            elif result.get("ambiguous"):
                _apply_ambiguous_row_update(
                    row,
                    str(result.get("reason", "connector_result_ambiguous")),
                )
                processed.append({
                    "queue_id": row.get("queue_id", ""),
                    "platform": row.get("platform", ""),
                    "slot_id": row.get("slot_id", ""),
                    "result": {
                        "ok": False,
                        "ambiguous": True,
                        "reason": result.get("reason"),
                    },
                    "state_after": row.get("publish_state", ""),
                })
            else:
                reason = str(
                    result.get(
                        "reason", "connector_failed_or_not_configured"
                    )
                )
                _apply_failed_row_update(
                    row,
                    reason,
                    int(policy.get("max_attempts_per_row", 3)),
                )
                processed.append({
                    "queue_id": row.get("queue_id", ""),
                    "platform": row.get("platform", ""),
                    "slot_id": row.get("slot_id", ""),
                    "result": {"ok": False, "reason": reason},
                    "state_after": row.get("publish_state", ""),
                })

        if not dry_run:
            _write_queue(queue_path, changed_rows)
            sync_report = _update_post_logs(changed_rows, posted_queue_ids + recovered_queue_ids, queue_limit=6)
        else:
            sync_report = {"ok": True, "skipped": True, "reason": "dry_run"}

        if claim_path and not dry_run:
            _update_claim_state(claim_path, state="completed", completed_at_utc=_iso_now(), posted_queue_ids=posted_queue_ids, recovered_queue_ids=recovered_queue_ids, publish_calls_performed=publish_calls)

        return {
            "ok": True,
            "version": "v2.8.5",
            "date": day,
            "mode": "scheduled_autonomous",
            "dry_run": dry_run,
            "slot_keyword": slot_keyword,
            "slot_id": slot_id,
            "queue_csv": str(queue_path),
            "claim_path": str(claim_path) if claim_path else "",
            "policy_path": str(policy_result["path"]),
            "policy_sha256": policy_result["sha256"],
            "publish_calls_performed": publish_calls,
            "provider_calls_performed": 0,
            "queue_mutated": not dry_run,
            "posted_count": sum(
                1 for item in processed
                if item["state_after"] == "posted"
            ),
            "failed_count": sum(
                1 for item in processed
                if item["state_after"] == "failed"
            ),
            "abandoned_count": sum(
                1 for item in processed
                if item["state_after"] == "abandoned"
            ),
            "ambiguous_count": sum(
                1 for item in processed
                if item["state_after"] == "connector_ambiguous"
            ),
            "processed": processed,
            "sync_report": sync_report,
            "recovered_queue_ids": recovered_queue_ids,
            "posted_queue_ids": posted_queue_ids,
            "clean_export_validated": True,
        }
    except Exception:
        if claim_path and not dry_run:
            try:
                _update_claim_state(claim_path, state="failed", failed_at_utc=_iso_now())
            except Exception:
                pass
        raise


def run_manual_publish(day: str, platforms: str, dry_run: bool, live: bool, ack_publish_risk: bool, limit: int, slot_keyword: str, max_attempts: int, feedback_queue_limit: int) -> dict[str, Any]:
    if not dry_run and not (live and ack_publish_risk):
        return {
            "ok": False,
            "version": "v2.8.2",
            "error": "live_publish_blocked_missing_explicit_approval_flags",
            "required_for_live": ["--live", "--i-understand-this-can-publish"],
            "safe_preview": "rerun with --dry-run",
        }

    queue_path, rows = _load_queue(day)
    if not rows:
        return {"ok": False, "version": "v2.8.1", "error": f"missing/empty queue: {queue_path}"}

    platform_filter = {p.strip().lower() for p in platforms.replace(";", ",").split(",") if p.strip()}
    results, processed = [], 0
    writable_rows = [dict(r) for r in rows]
    posted_queue_ids: list[str] = []

    for row in writable_rows:
        if row.get("publish_state") == "posted":
            continue
        if row.get("publish_state") not in ("queued", "failed", "ready_for_connector", "dry_run", ""):
            continue
        if platform_filter and row.get("platform", "").lower() not in platform_filter:
            continue
        if limit and processed >= limit:
            continue
        if slot_keyword and slot_keyword.lower() not in row.get("slot_id", "").lower():
            continue

        processed += 1
        result = _run_connector(row, dry_run=dry_run)
        now = _iso_now().replace("Z", "")

        if dry_run:
            pass
        elif result.get("ok") and result.get("posted"):
            row["publish_state"] = "posted"
            row["posted_at"] = result.get("posted_at") or now
            row["post_url"] = result.get("post_url", "")
            row["failure_reason"] = ""
            row["attempt_count"] = "0"
            if result.get("post_id"):
                row["notes"] = f"post_id:{result['post_id']}"
            posted_queue_ids.append(row.get("queue_id", ""))
        else:
            reason = result.get("reason", "connector_failed_or_not_configured")
            _apply_failed_row_update(row, str(reason), max_attempts)

        results.append({"queue_id": row.get("queue_id"), "platform": row.get("platform"), "slot_id": row.get("slot_id"), "result": result, "state_after": row.get("publish_state")})

    if not dry_run:
        _write_queue(queue_path, writable_rows)
        queue_sync = _update_post_logs(writable_rows, posted_queue_ids, queue_limit=feedback_queue_limit)
    else:
        queue_sync = {"ok": True, "skipped": True, "reason": "dry_run_preview_only_queue_not_mutated"}

    report = {
        "ok": True,
        "version": "v2.8.5",
        "date": day,
        "dry_run": dry_run,
        "queue_mutated": not dry_run,
        "processed": processed,
        "posted_count": sum(1 for r in results if r["state_after"] == "posted"),
        "ready_for_connector_count": sum(1 for r in results if r["state_after"] == "ready_for_connector"),
        "failed_count": sum(1 for r in results if r["state_after"] == "failed"),
        "queue_csv": str(queue_path),
        "queue_sync": queue_sync,
        "results": results,
        "provider_calls_performed": 0,
        "publish_calls_performed": sum(1 for r in results if r["result"].get("posted")),
    }
    report_path = REPORT_ROOT / day / f"approved_queue_autopublish_report_{datetime.now().strftime('%H%M%S')}_v2_8_4.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["report"] = str(report_path)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--platforms", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--scheduled-autonomous", action="store_true")
    ap.add_argument("--autonomous-policy", default=str(POLICY_PATH))
    ap.add_argument("--slot-keyword", default="", dest="slot_keyword")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-attempts", type=int, default=3, dest="max_attempts")
    ap.add_argument("--feedback-queue-limit", type=int, default=6)
    ap.add_argument("--i-understand-this-can-publish", action="store_true", dest="ack_publish_risk")
    args = ap.parse_args()

    if args.scheduled_autonomous and (args.live or args.ack_publish_risk):
        print(json.dumps({"ok": False, "version": "v2.8.5", "error": "autonomous_mode_must_not_reuse_manual_live_flags"}, indent=2, ensure_ascii=False))
        return 2

    try:
        if args.scheduled_autonomous:
            report = run_scheduled_autonomous(
                day=args.date,
                slot_keyword=args.slot_keyword,
                limit=args.limit or 1,
                dry_run=args.dry_run,
                policy_path=Path(args.autonomous_policy),
            )
        else:
            report = run_manual_publish(
                day=args.date,
                platforms=args.platforms,
                dry_run=args.dry_run,
                live=args.live,
                ack_publish_risk=args.ack_publish_risk,
                limit=args.limit,
                slot_keyword=args.slot_keyword,
                max_attempts=args.max_attempts,
                feedback_queue_limit=args.feedback_queue_limit,
            )
    except AutopublishError as exc:
        print(json.dumps({"ok": False, "version": "v2.8.5", "error": exc.code, "detail": exc.detail}, indent=2, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "version": "v2.8.5", "error": "unexpected_error", "detail": str(exc)}, indent=2, ensure_ascii=False))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
