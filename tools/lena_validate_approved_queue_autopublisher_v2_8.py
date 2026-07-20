from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"

FILES = [
    "approved_queue_auto_publisher_manifest_v2_8.json",
    "approved_queue_auto_publisher_policy_v2_8.json",
]

TOOLS = [
    "tools/lena_build_approved_publish_queue_v2_8.py",
    "tools/lena_autopublish_approved_queue_v2_8.py",
]

BATCH_GATES = [
    "RUN_LENA_PUBLISH_MORNING_SLOT.bat",
    "RUN_LENA_PUBLISH_AFTERNOON_SLOT.bat",
    "RUN_LENA_PUBLISH_EVENING_SLOT.bat",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(report: dict, ok: bool, section: str, label: str, detail: str = "") -> None:
    report.setdefault(section, []).append({"ok": ok, "check": label, "detail": detail})
    report["ok"] = report["ok"] and ok


def main() -> int:
    report = {
        "ok": True,
        "version": "v2.8.4",
        "files": {},
        "tools": {},
        "batch_gates": {},
        "policy_checks": [],
    }

    loaded: dict[str, dict] = {}
    for fname in FILES:
        path = NODE / fname
        try:
            data = load_json(path)
            loaded[fname] = data
            report["files"][fname] = {"ok": True, "version": data.get("version"), "path": str(path)}
        except Exception as exc:
            report["ok"] = False
            report["files"][fname] = {"ok": False, "error": str(exc), "path": str(path)}

    for tool in TOOLS:
        path = ROOT / tool
        ok = path.exists()
        report["tools"][tool] = {"ok": ok, "path": str(path)}
        report["ok"] = report["ok"] and ok

    for batch in BATCH_GATES:
        path = ROOT / batch
        ok = path.exists()
        text = path.read_text(encoding="utf-8", errors="ignore") if ok else ""
        report["batch_gates"][batch] = {
            "ok": ok
            and "pause" not in text.lower()
            and "--scheduled-autonomous" in text
            and "--slot-keyword" in text
            and "lenadelapi_website_hpe2" not in text.lower()
            and ("LENA_AUTOPUBLISH_PRODUCTION_ROOT" in text or "CONTENT_BOT_ROOT" in text)
            and ("LENA_AUTOPUBLISH_PYTHON_EXE" in text or "CONTENT_BOT_PYTHON_EXE" in text),
            "path": str(path),
            "has_pause": "pause" in text.lower(),
            "has_scheduled_autonomous": "--scheduled-autonomous" in text,
            "has_slot_keyword": "--slot-keyword" in text,
            "has_manual_live_flags": "--i-understand-this-can-publish" in text,
            "has_hardcoded_temp_root": "lenadelapi_website_hpe2" in text.lower(),
            "has_root_env_contract": "LENA_AUTOPUBLISH_PRODUCTION_ROOT" in text or "CONTENT_BOT_ROOT" in text,
            "has_python_env_contract": "LENA_AUTOPUBLISH_PYTHON_EXE" in text or "CONTENT_BOT_PYTHON_EXE" in text,
        }
        report["ok"] = report["ok"] and report["batch_gates"][batch]["ok"]

    policy = loaded.get("approved_queue_auto_publisher_policy_v2_8.json")
    manifest = loaded.get("approved_queue_auto_publisher_manifest_v2_8.json")
    if policy:
        check(report, policy.get("policy_id") == "lena_approved_queue_auto_publisher_policy_v2_8", "policy_checks", "policy id matches")
        check(report, policy.get("policy_version") == "v2.8.0", "policy_checks", "policy version matches")
        check(report, policy.get("autonomous_mode") == "scheduled_autonomous", "policy_checks", "policy names separate autonomous mode")
        check(report, policy.get("autonomous_enabled") is False, "policy_checks", "autonomous mode disabled by default")
        check(report, policy.get("autonomous_enabled_by_default") is False, "policy_checks", "autonomous mode disabled by default flag")
        check(report, int(policy.get("hard_item_limit_per_invocation", 0)) == 1, "policy_checks", "hard item limit is one")
        check(report, set(policy.get("approved_slots", [])) == {"morning", "afternoon", "evening"}, "policy_checks", "approved slots are morning afternoon evening")
        check(report, policy.get("manual_live_mode_unchanged") is True, "policy_checks", "manual live mode unchanged")
        check(report, policy.get("publish_mode") == "explicit_live_connector_required", "policy_checks", "manual-live publish mode preserved")
        check(report, policy.get("allow_replies") is False and policy.get("allow_dms") is False and policy.get("allow_outreach") is False, "policy_checks", "replies dms outreach remain blocked")
    if manifest:
        boundary = manifest.get("boundary", {})
        check(report, boundary.get("auto_queue_building") is True, "policy_checks", "manifest allows queue building")
        check(report, boundary.get("auto_publish_queue") is False, "policy_checks", "manifest keeps autonomous publishing guarded")
        check(report, boundary.get("autonomous_enabled_by_default") is False, "policy_checks", "manifest disabled by default")
        check(report, boundary.get("manual_live_mode_unchanged") is True, "policy_checks", "manifest preserves manual live")
        safety = manifest.get("safety", {})
        check(report, safety.get("duplicate_prevention") is True, "policy_checks", "duplicate prevention retained")
        check(report, safety.get("already_posted_skip") is True, "policy_checks", "already-posted skip retained")
        check(report, safety.get("bounded_retries") is True, "policy_checks", "bounded retries retained")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
