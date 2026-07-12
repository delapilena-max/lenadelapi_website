from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
POLICY_PATH = NODE / "meta_feedback_ingestion_policy_v1.json"
SCORING_MODEL = NODE / "post_metric_scoring_model_v1_6_1.json"

PUBLISHERS = ROOT / "tools" / "publishers"
if str(PUBLISHERS) not in sys.path:
    sys.path.insert(0, str(PUBLISHERS))

from lena_meta_publish_common_v2_9 import MetaConnectorError, config_status, graph_get, load_config


REPLY_TOOL = ROOT / "tools" / "lena_generate_comment_replies_v1_6.py"
REFRESH_FEEDBACK = ROOT / "tools" / "lena_refresh_post_feedback_loop_v1.py"
BUILD_INTERACTION_QUEUE = ROOT / "tools" / "lena_build_interaction_review_queue_v1.py"

POST_FIELDS = [
    "date","posted_at","platform","slot_id","asset_path","media_type","lane","growth_bucket",
    "hook_category","post_url","audio_name","caption","pinned_comment","post_poll","story_poll",
    "music_selected","manual_publish_approved","notes"
]

METRIC_FIELDS = [
    "date","slot_id","platform","media_type","growth_bucket","lane","hook_category","post_url",
    "audio_name","reach","likes","saves","shares","comments","follows","profile_visits",
    "completion_rate","replay_rate","score","classification","notes"
]

ENG_FIELDS = [
    "date", "platform", "post_id", "post_url", "signal_type", "signal_class",
    "comment_text", "draft_reply", "action_taken", "notes"
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


def read_csv_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def stable_union_fields(existing_fields: list[str], required_fields: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for field in existing_fields + required_fields:
        if not field or field in seen:
            continue
        seen.add(field)
        ordered.append(field)
    return ordered


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in fields} for row in rows])


def load_policy() -> dict:
    return read_json(POLICY_PATH)


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {
            "version": "v1",
            "updated_at": "",
            "processed_comment_ids": {},
            "last_metrics_pull_by_post_key": {},
            "last_comment_pull_by_post_key": {},
            "last_report_path": "",
        }
    try:
        return read_json(state_path)
    except Exception:
        return {
            "version": "v1",
            "updated_at": "",
            "processed_comment_ids": {},
            "last_metrics_pull_by_post_key": {},
            "last_comment_pull_by_post_key": {},
            "last_report_path": "",
        }


def write_state(state_path: Path, state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    write_json(state_path, state)


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except Exception:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def post_key(row: dict) -> str:
    return f"{row.get('date','')}|{row.get('slot_id','')}|{row.get('platform','')}"


def parse_post_id(notes: str) -> str:
    import re
    match = re.search(r"\bpost_id:([^\s|]+)", notes or "")
    return match.group(1).strip() if match else ""


def numeric(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def score_model() -> dict:
    if SCORING_MODEL.exists():
        return read_json(SCORING_MODEL)
    return {"weights": {}, "classification": {"winner": 75, "strong": 50, "neutral": 25}}


def scoring_required_fields(model: dict | None = None) -> set[str]:
    active_model = model or score_model()
    weights = active_model.get("weights", {})
    required = {field for field, weight in weights.items() if numeric(weight) > 0}
    # score_row() always uses reach as the denominator for weighted engagement rates.
    required.add("reach")
    return required


def metric_success(value) -> dict:
    return {"ok": True, "value": numeric(value)}


def metric_failure(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# Stable, truthful reason (2026-07-12): `follows` is not referenced by any
# real Graph API call this tool makes for either platform -- its absence
# from metric_results would otherwise be a silent, ambiguous gap rather
# than an honest, explicit "this tool doesn't ask for this metric" fact.
NOT_REQUESTED_BY_TOOL = "not_requested_by_tool"


def metric_result_value(result: dict) -> float | None:
    if isinstance(result, dict) and result.get("ok"):
        return numeric(result.get("value"))
    return None


def format_metric_value(field: str, value: float) -> str:
    if field in {"completion_rate", "replay_rate"}:
        return str(float(value))
    return str(int(value))


def merge_metric_field(existing_value, fetched_result: dict, field: str, is_new_row: bool) -> str:
    value = metric_result_value(fetched_result)
    if value is not None:
        return format_metric_value(field, value)
    if is_new_row:
        return ""
    return "" if existing_value is None else str(existing_value)


def row_has_unknown_scoring_inputs(row: dict, model: dict | None = None) -> bool:
    for field in scoring_required_fields(model):
        if str(row.get(field, "")).strip() == "":
            return True
    return False


def apply_fetched_metrics(row: dict, fetched: dict, is_new_row: bool) -> dict:
    metric_results = fetched.get("metric_results", {})
    for field in (
        "reach",
        "likes",
        "saves",
        "shares",
        "comments",
        "profile_visits",
        "completion_rate",
        "replay_rate",
    ):
        row[field] = merge_metric_field(row.get(field, ""), metric_results.get(field, {}), field, is_new_row)

    if row_has_unknown_scoring_inputs(row):
        row["score"] = ""
        row["classification"] = "pending"
    else:
        row["score"], row["classification"] = score_row(row)
    return row


def build_metrics_report_entry(row: dict, fetched: dict) -> dict:
    """Pure function, no I/O -- shapes the per-post `metrics` block written
    into the refresh report JSON. Extracted (2026-07-12) so the report's
    per-field fetch truth is independently testable without invoking
    main(). Preserves every field the report already carried (`ok`,
    `reach`/`likes`/`comments`/`shares`/`saves`, `classification`, `score`)
    byte-for-byte, and additively carries forward the real, already-computed
    `metric_results` (from fetch_instagram_metrics()/fetch_facebook_metrics(),
    tagged ok/value or ok/reason via metric_success()/metric_failure()) that
    was previously discarded before the report was written. Never
    recomputes or reinterprets any fetch outcome -- pure passthrough."""
    return {
        "ok": True,
        "reach": row["reach"],
        "likes": row["likes"],
        "comments": row["comments"],
        "shares": row["shares"],
        "saves": row["saves"],
        "classification": row["classification"],
        "score": row["score"],
        "metric_results": fetched.get("metric_results", {}),
    }


def score_row(row: dict) -> tuple[float, str]:
    model = score_model()
    weights = model.get("weights", {})
    thresholds = model.get("classification", {})
    reach = max(numeric(row.get("reach")), 1.0)
    raw = 0.0
    raw += (numeric(row.get("shares")) / reach) * 1000 * weights.get("shares", 4)
    raw += (numeric(row.get("saves")) / reach) * 1000 * weights.get("saves", 3)
    raw += (numeric(row.get("comments")) / reach) * 1000 * weights.get("comments", 2.5)
    raw += (numeric(row.get("follows")) / reach) * 1000 * weights.get("follows", 5)
    raw += (numeric(row.get("profile_visits")) / reach) * 1000 * weights.get("profile_visits", 2)
    raw += (numeric(row.get("likes")) / reach) * 1000 * weights.get("likes", 1)
    raw += numeric(row.get("completion_rate")) * weights.get("completion_rate", 25)
    raw += numeric(row.get("replay_rate")) * weights.get("replay_rate", 20)
    score = round(min(raw, 100), 2)
    if score >= thresholds.get("winner", 75):
        classification = "winner"
    elif score >= thresholds.get("strong", 50):
        classification = "strong"
    elif score >= thresholds.get("neutral", 25):
        classification = "neutral"
    else:
        classification = "weak"
    return score, classification


def try_parse_json(text: str):
    raw = (text or "").strip()
    if not raw or (not raw.startswith("{") and not raw.startswith("[")):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def reply_draft(comment_text: str, row: dict) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPLY_TOOL),
            "--comment",
            comment_text,
            "--lane",
            row.get("lane", ""),
            "--post-context",
            row.get("caption", ""),
            "--audio-name",
            row.get("audio_name", ""),
            "--count",
            "1",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    parsed = try_parse_json(proc.stdout) if proc.returncode == 0 else None
    signal_class = "general"
    draft_reply = ""
    if isinstance(parsed, dict):
        signal_class = parsed.get("class", "general")
        replies = parsed.get("replies", [])
        if replies:
            draft_reply = replies[0].get("reply", "")
    return {
        "ok": proc.returncode == 0,
        "signal_class": signal_class,
        "draft_reply": draft_reply,
    }


def refresh_feedback_loop(day: str, queue_limit: int) -> dict:
    proc = subprocess.run(
        [sys.executable, str(REFRESH_FEEDBACK), "--date", day, "--queue-limit", str(queue_limit)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "summary": try_parse_json(proc.stdout),
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
    }


def build_interaction_queue(day: str, queue_limit: int) -> dict:
    proc = subprocess.run(
        [sys.executable, str(BUILD_INTERACTION_QUEUE), "--date", day, "--limit", str(queue_limit)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "summary": try_parse_json(proc.stdout),
        "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-12:],
        "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-12:],
    }


def instagram_login_cfg(cfg: dict) -> dict:
    out = dict(cfg)
    out["auth_mode"] = "instagram_login"
    return out


def metric_row_index(rows: list[dict], post_row: dict) -> int:
    for idx, row in enumerate(rows):
        if (
            row.get("date", "") == post_row.get("date", "")
            and row.get("slot_id", "") == post_row.get("slot_id", "")
            and row.get("platform", "") == post_row.get("platform", "")
        ):
            return idx
    return -1


def platform_family(platform: str) -> str:
    value = (platform or "").strip().lower()
    if value.startswith("instagram"):
        return "instagram"
    if value.startswith("facebook"):
        return "facebook"
    return ""


def graph_platform(platform: str) -> str:
    family = platform_family(platform)
    if family == "instagram":
        return "Instagram Feed"
    if family == "facebook":
        return "Facebook Page"
    return platform


def extract_insight_value(payload: dict, metric_name: str) -> dict:
    if not isinstance(payload, dict):
        return metric_failure("invalid_payload")
    for entry in payload.get("data", []):
        if entry.get("name") != metric_name:
            continue
        values = entry.get("values") or []
        if values:
            return metric_success(values[0].get("value"))
        return metric_failure("missing_values")
    return metric_failure("metric_unavailable")


def fetch_instagram_metrics(post_id: str, cfg: dict, policy: dict) -> dict:
    platform = "Instagram Feed"
    ig_cfg = instagram_login_cfg(cfg)
    summary = None
    resolved_post_id = post_id
    try:
        summary = graph_get(f"/{post_id}", {"fields": policy["base_fields"]}, ig_cfg, platform=platform)
    except Exception:
        summary = resolve_instagram_media_via_business_account(post_id, "", cfg, policy)
        resolved_post_id = summary.get("id", post_id) if isinstance(summary, dict) else post_id
    if not isinstance(summary, dict):
        raise RuntimeError("instagram_media_summary_unavailable")
    out = {
        "source_permalink": summary.get("permalink", ""),
        "raw_summary": summary,
        "resolved_post_id": resolved_post_id,
        "metric_results": {
            "likes": metric_success(summary.get("like_count")),
            "comments": metric_success(summary.get("comments_count")),
            "reach": metric_failure("insight_unavailable"),
            "saves": metric_failure("insight_unavailable"),
            "shares": metric_failure("insight_unavailable"),
            "follows": metric_failure(NOT_REQUESTED_BY_TOOL),
            "profile_visits": metric_failure("metric_unavailable"),
            "completion_rate": metric_failure("metric_unavailable"),
            "replay_rate": metric_failure("metric_unavailable"),
        },
        "insight_metrics": {},
    }
    for metric in policy.get("insight_metrics", []):
        try:
            try:
                data = graph_get(f"/{resolved_post_id}/insights", {"metric": metric}, ig_cfg, platform=platform)
            except Exception:
                data = graph_get(f"/{resolved_post_id}/insights", {"metric": metric}, cfg, platform=platform)
            result = extract_insight_value(data, metric)
            out["insight_metrics"][metric] = result
        except Exception as exc:
            result = metric_failure(f"error:{exc}")
            out["insight_metrics"][metric] = result
        if metric == "reach":
            out["metric_results"]["reach"] = result
        elif metric == "saved":
            out["metric_results"]["saves"] = result
        elif metric == "shares":
            out["metric_results"]["shares"] = result
    return out


def fetch_facebook_metrics(post_id: str, cfg: dict, policy: dict) -> dict:
    platform = "Facebook Page"
    summary = graph_get(f"/{post_id}", {"fields": policy["base_fields"]}, cfg, platform=platform)
    reactions = ((summary.get("reactions") or {}).get("summary") or {}).get("total_count", 0)
    comments = ((summary.get("comments") or {}).get("summary") or {}).get("total_count", 0)
    shares = (summary.get("shares") or {}).get("count", 0)
    out = {
        "source_permalink": summary.get("permalink_url", ""),
        "raw_summary": summary,
        "metric_results": {
            "likes": metric_success(reactions),
            "comments": metric_success(comments),
            "shares": metric_success(shares),
            "reach": metric_failure("insight_unavailable"),
            "saves": metric_failure("metric_unavailable"),
            "follows": metric_failure(NOT_REQUESTED_BY_TOOL),
            "profile_visits": metric_failure("metric_unavailable"),
            "completion_rate": metric_failure("metric_unavailable"),
            "replay_rate": metric_failure("metric_unavailable"),
        },
        "insight_metrics": {},
    }
    for metric in policy.get("insight_metrics", []):
        try:
            data = graph_get(f"/{post_id}/insights", {"metric": metric}, cfg, platform=platform)
            result = extract_insight_value(data, metric)
            out["insight_metrics"][metric] = result
        except Exception as exc:
            result = metric_failure(f"error:{exc}")
            out["insight_metrics"][metric] = result
        if metric == "post_impressions_unique":
            out["metric_results"]["reach"] = result
        elif metric == "post_impressions":
            if not out["metric_results"]["reach"].get("ok"):
                out["metric_results"]["reach"] = result
    return out


def resolve_instagram_media_via_business_account(post_id: str, post_url: str, cfg: dict, policy: dict) -> dict:
    ig_business_id = str(cfg.get("instagram_business_account_id", "")).strip()
    if not ig_business_id:
        return {}
    listing = graph_get(
        f"/{ig_business_id}/media",
        {"fields": policy["base_fields"], "limit": "25"},
        cfg,
        platform="Instagram Feed",
    )
    for item in listing.get("data", []):
        if item.get("id", "") == post_id:
            return item
        if post_url and item.get("permalink", "") == post_url:
            return item
    return {}


def fetch_comments(post_id: str, post_url: str, platform: str, cfg: dict, policy: dict, comments_limit: int) -> list[dict]:
    family = platform_family(platform)
    chosen_cfg = cfg
    resolved_post_id = post_id
    if family == "instagram":
        fields = policy["instagram"]["comment_fields"]
        chosen_cfg = instagram_login_cfg(cfg)
    elif family == "facebook":
        fields = policy["facebook"]["comment_fields"]
    else:
        return []

    payload = None
    if family == "instagram":
        try:
            payload = graph_get(
                f"/{post_id}/comments",
                {"fields": fields, "limit": str(comments_limit)},
                chosen_cfg,
                platform=graph_platform(platform),
            )
        except Exception:
            media = resolve_instagram_media_via_business_account(post_id, post_url, cfg, policy["instagram"])
            resolved_post_id = media.get("id", post_id)
            try:
                payload = graph_get(
                    f"/{resolved_post_id}/comments",
                    {"fields": fields, "limit": str(comments_limit)},
                    cfg,
                    platform=graph_platform(platform),
                )
            except Exception:
                ig_business_id = str(cfg.get("instagram_business_account_id", "")).strip()
                if not ig_business_id:
                    raise
                embed_fields = f"id,permalink,comments{{{fields}}}"
                media_listing = graph_get(
                    f"/{ig_business_id}/media",
                    {"fields": embed_fields, "limit": "25"},
                    cfg,
                    platform=graph_platform(platform),
                )
                payload = {"data": []}
                for item in media_listing.get("data", []):
                    if item.get("id", "") == resolved_post_id:
                        payload = item.get("comments") or {"data": []}
                        break
    else:
        payload = graph_get(
            f"/{post_id}/comments",
            {"fields": fields, "limit": str(comments_limit)},
            chosen_cfg,
            platform=graph_platform(platform),
        )

    comments = []
    for row in payload.get("data", []):
        if family == "instagram":
            text = row.get("text", "")
            username = row.get("username", "")
            timestamp = row.get("timestamp", "")
        else:
            text = row.get("message", "")
            author = row.get("from") or {}
            username = author.get("name", "")
            timestamp = row.get("created_time", "")
        comments.append(
            {
                "id": row.get("id", ""),
                "text": text,
                "username": username,
                "timestamp": timestamp,
                "raw": row,
            }
        )
    return comments


def meta_ready_for(platform: str, status: dict) -> bool:
    readiness = status.get("readiness", {})
    family = platform_family(platform)
    if family == "instagram":
        return bool(readiness.get("instagram_ready"))
    if family == "facebook":
        return bool(readiness.get("facebook_ready"))
    return False


def _post_log_key(row: dict) -> tuple:
    return (row.get("date", ""), row.get("slot_id", ""), row.get("platform", ""))


def resolve_structured_post_id(post_row: dict, metric_index: dict) -> str:
    """Structured identity precedence (2026-07-11): prefers the real
    instagram_media_id already attached to this post's metrics row (via
    tools/lena_sync_architecture_a_receipts_to_metrics_v1.py, itself
    sourced from a real Architecture A publish receipt -- never a
    fabricated value) over the historical free-text 'post_id:<id>' notes
    convention. Falls back to the legacy notes regex ONLY when no
    structured value exists for this (date, slot_id, platform) key --
    historical rows that only ever had the notes convention keep working
    exactly as before, unweakened."""
    metric_row = metric_index.get(_post_log_key(post_row))
    if metric_row:
        structured = (metric_row.get("instagram_media_id") or "").strip()
        if structured:
            return structured
    return parse_post_id(post_row.get("notes", ""))


def metrics_row_actionable_post_id(metric_row: dict) -> str:
    structured = (metric_row.get("instagram_media_id") or "").strip()
    return structured


def build_metrics_candidate_row(metric_row: dict) -> dict:
    return {
        "date": metric_row.get("date", ""),
        "posted_at": "",
        "platform": metric_row.get("platform", ""),
        "slot_id": metric_row.get("slot_id", ""),
        "asset_path": "",
        "media_type": metric_row.get("media_type", ""),
        "lane": metric_row.get("lane", ""),
        "growth_bucket": metric_row.get("growth_bucket", ""),
        "hook_category": metric_row.get("hook_category", ""),
        "post_url": metric_row.get("post_url", "") or metric_row.get("permalink", ""),
        "audio_name": metric_row.get("audio_name", ""),
        "caption": "",
        "pinned_comment": "",
        "post_poll": "",
        "story_poll": "",
        "music_selected": "",
        "manual_publish_approved": "",
        "notes": metric_row.get("notes", ""),
        "_post_id": metrics_row_actionable_post_id(metric_row),
    }


def candidate_posts(post_rows: list[dict], metric_rows: list[dict], days_back: int, max_posts: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=days_back)
    metric_index = {_post_log_key(row): row for row in metric_rows}
    candidates_by_key: dict[tuple, dict] = {}

    def register_candidate(row: dict) -> None:
        key = _post_log_key(row)
        existing = candidates_by_key.get(key)
        if existing is None:
            candidates_by_key[key] = row
            return

        # Prefer the richer manual-log row when both sources describe the
        # same canonical post identity. Preserve the already-resolved
        # canonical platform post ID either way.
        merged = dict(existing)
        merged["_post_id"] = row.get("_post_id", "") or existing.get("_post_id", "")
        for field in (
            "posted_at",
            "asset_path",
            "caption",
            "pinned_comment",
            "post_poll",
            "story_poll",
            "music_selected",
            "manual_publish_approved",
            "notes",
        ):
            if row.get(field):
                merged[field] = row[field]
        for field in (
            "media_type",
            "lane",
            "growth_bucket",
            "hook_category",
            "post_url",
            "audio_name",
        ):
            if not merged.get(field) and row.get(field):
                merged[field] = row[field]
        if row.get("posted_at"):
            merged["posted_at"] = row["posted_at"]
        candidates_by_key[key] = merged

    for row in post_rows:
        family = platform_family(row.get("platform", ""))
        if not family:
            continue
        row_date = parse_date(row.get("date", ""))
        if row_date and row_date < cutoff:
            continue
        post_id = resolve_structured_post_id(row, metric_index)
        if not post_id:
            continue
        register_candidate(dict(row, _post_id=post_id))

    for row in metric_rows:
        family = platform_family(row.get("platform", ""))
        if not family:
            continue
        row_date = parse_date(row.get("date", ""))
        if row_date and row_date < cutoff:
            continue
        post_id = metrics_row_actionable_post_id(row)
        if not post_id:
            continue
        register_candidate(build_metrics_candidate_row(row))

    candidates = list(candidates_by_key.values())
    candidates.sort(key=lambda row: (row.get("date", ""), row.get("posted_at", "")), reverse=True)
    return candidates[:max_posts]


def append_note(base: str, token: str) -> str:
    base = (base or "").strip()
    if token in base:
        return base
    if not base:
        return token
    return f"{base} | {token}"


def main() -> int:
    policy = load_policy()
    parser = argparse.ArgumentParser(
        description="Pull Meta post metrics and comment signals into Lena analytics."
    )
    defaults = policy.get("defaults", {})
    parser.add_argument("--days-back", type=int, default=int(defaults.get("days_back", 14)))
    parser.add_argument("--max-posts", type=int, default=int(defaults.get("max_posts_per_run", 12)))
    parser.add_argument("--comments-limit", type=int, default=int(defaults.get("comments_limit_per_post", 25)))
    parser.add_argument("--queue-limit", type=int, default=int(defaults.get("feedback_queue_limit", 6)))
    parser.add_argument("--skip-comments", action="store_true")
    parser.add_argument("--skip-metrics", action="store_true")
    parser.add_argument("--skip-feedback-refresh", action="store_true")
    args = parser.parse_args()

    state_path = ROOT / Path(policy["state_path"])
    report_root = ROOT / Path(policy["report_dir"])
    post_log_path = ROOT / Path(policy["manual_post_log_path"])
    metrics_path = ROOT / Path(policy["post_metrics_path"])
    engagement_path = ROOT / Path(policy["engagement_log_path"])

    state = load_state(state_path)
    cfg = load_config()
    status = config_status(False)

    post_rows = read_csv(post_log_path)
    metric_fields = stable_union_fields(read_csv_header(metrics_path), METRIC_FIELDS)
    metric_rows = read_csv(metrics_path)
    engagement_rows = read_csv(engagement_path)
    candidates = candidate_posts(post_rows, metric_rows, args.days_back, args.max_posts)

    processed_comment_ids = state.setdefault("processed_comment_ids", {})
    last_metrics_pull = state.setdefault("last_metrics_pull_by_post_key", {})
    last_comment_pull = state.setdefault("last_comment_pull_by_post_key", {})

    metrics_updated = 0
    comments_logged = 0
    changed_dates: set[str] = set()
    post_reports = []

    for post_row in candidates:
        platform = post_row.get("platform", "")
        if not meta_ready_for(platform, status):
            post_reports.append({
                "post_key": post_key(post_row),
                "platform": platform,
                "post_id": post_row.get("_post_id", ""),
                "skipped": True,
                "reason": "meta_config_not_ready_for_platform",
            })
            continue

        key = post_key(post_row)
        metrics_report = {}
        comments_report = {"logged_count": 0, "new_comment_ids": []}

        if not args.skip_metrics:
            try:
                family = platform_family(platform)
                if family == "instagram":
                    fetched = fetch_instagram_metrics(post_row["_post_id"], cfg, policy["instagram"])
                else:
                    fetched = fetch_facebook_metrics(post_row["_post_id"], cfg, policy["facebook"])

                idx = metric_row_index(metric_rows, post_row)
                is_new_row = idx < 0
                if idx >= 0:
                    row = dict(metric_rows[idx])
                else:
                    row = {
                        "date": post_row.get("date", ""),
                        "slot_id": post_row.get("slot_id", ""),
                        "platform": platform,
                        "media_type": post_row.get("media_type", ""),
                        "growth_bucket": post_row.get("growth_bucket", ""),
                        "lane": post_row.get("lane", ""),
                        "hook_category": post_row.get("hook_category", ""),
                        "post_url": post_row.get("post_url", ""),
                        "audio_name": post_row.get("audio_name", ""),
                    }

                row["post_url"] = post_row.get("post_url", "") or fetched.get("source_permalink", "") or row.get("post_url", "")
                row["audio_name"] = post_row.get("audio_name", "") or row.get("audio_name", "")
                row["growth_bucket"] = post_row.get("growth_bucket", "") or row.get("growth_bucket", "")
                row["lane"] = post_row.get("lane", "") or row.get("lane", "")
                row["hook_category"] = post_row.get("hook_category", "") or row.get("hook_category", "")
                row = apply_fetched_metrics(row, fetched, is_new_row=is_new_row)
                row["notes"] = append_note(row.get("notes", ""), f"auto_meta_metrics_refresh:{datetime.now().strftime('%Y-%m-%d')}")

                if idx >= 0:
                    metric_rows[idx] = row
                else:
                    metric_rows.append({field: row.get(field, "") for field in metric_fields})
                metrics_updated += 1
                changed_dates.add(post_row.get("date", ""))
                last_metrics_pull[key] = utc_now_iso()
                metrics_report = build_metrics_report_entry(row, fetched)
            except Exception as exc:
                metrics_report = {"ok": False, "error": str(exc)}

        if not args.skip_comments:
            try:
                comments = fetch_comments(post_row["_post_id"], post_row.get("post_url", ""), platform, cfg, policy, args.comments_limit)
                seen = set(processed_comment_ids.get(key, []))
                for comment in comments:
                    comment_id = comment.get("id", "")
                    text = comment.get("text", "")
                    if not comment_id or not text or comment_id in seen:
                        continue
                    draft = reply_draft(text, post_row)
                    engagement_rows.append(
                        {
                            "date": post_row.get("date", ""),
                            "platform": platform,
                            "post_id": post_row.get("_post_id", ""),
                            "post_url": post_row.get("post_url", ""),
                            "signal_type": "comment",
                            "signal_class": draft["signal_class"],
                            "comment_text": text,
                            "draft_reply": draft["draft_reply"],
                            "action_taken": "pending_review",
                            "notes": f"comment_id:{comment_id} user:{comment.get('username','')}",
                        }
                    )
                    comments_logged += 1
                    comments_report["logged_count"] += 1
                    comments_report["new_comment_ids"].append(comment_id)
                    seen.add(comment_id)
                processed_comment_ids[key] = sorted(seen)
                last_comment_pull[key] = utc_now_iso()
                comments_report["ok"] = True
                comments_report["fetched_count"] = len(comments)
                if comments_report["logged_count"]:
                    changed_dates.add(post_row.get("date", ""))
            except Exception as exc:
                comments_report = {"ok": False, "error": str(exc)}

        post_reports.append(
            {
                "post_key": key,
                "platform": platform,
                "post_id": post_row.get("_post_id", ""),
                "slot_id": post_row.get("slot_id", ""),
                "metrics": metrics_report,
                "comments": comments_report,
            }
        )

    write_csv(metrics_path, metric_fields, metric_rows)
    write_csv(engagement_path, ENG_FIELDS, engagement_rows)

    refresh_runs = []
    interaction_queue_runs = []
    if not args.skip_feedback_refresh and policy.get("refresh_feedback_loop_after_ingest", True):
        for day in sorted(day for day in changed_dates if day):
            refresh_runs.append(refresh_feedback_loop(day, args.queue_limit))
            interaction_queue_runs.append(build_interaction_queue(day, args.queue_limit))

    stamp = datetime.now().strftime("%H%M%S")
    out_dir = report_root / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"lena_meta_feedback_refresh_{stamp}.json"
    report = {
        "ok": True,
        "version": "v1.0.0",
        "generated_at": utc_now_iso(),
        "args": vars(args),
        "config_readiness": status.get("readiness", {}),
        "candidate_post_count": len(candidates),
        "metrics_updated": metrics_updated,
        "comments_logged": comments_logged,
        "changed_dates": sorted(changed_dates),
        "posts": post_reports,
        "feedback_refresh_runs": refresh_runs,
        "interaction_queue_runs": interaction_queue_runs,
        "state_path": str(state_path),
        "report_path": str(report_path),
    }
    write_json(report_path, report)
    state["last_report_path"] = str(report_path)
    write_state(state_path, state)

    print(
        json.dumps(
            {
                "ok": True,
                "version": "v1.0.0",
                "candidate_post_count": len(candidates),
                "metrics_updated": metrics_updated,
                "comments_logged": comments_logged,
                "changed_dates": sorted(changed_dates),
                "report_path": str(report_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
