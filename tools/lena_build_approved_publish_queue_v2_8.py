from __future__ import annotations
import argparse, csv, hashlib, json, re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"

QUEUE_FIELDS = [
    "queue_id","date","created_at","slot_id","platform","media_type","lane","asset_status","asset_path",
    "caption","short_caption","pinned_comment","story_prompt","post_poll","keyword_notes",
    "public_text_score","public_text_decision","publish_state","publish_mode","connector_path",
    "post_url","posted_at","failure_reason","notes"
]

def load_policy():
    return json.loads((NODE / "approved_queue_auto_publisher_policy_v2_8.json").read_text(encoding="utf-8-sig"))

def load_packets(day):
    path = ROOT / "pipeline" / "publish_packets" / "lena" / day / "lena_publish_packets_v2_4.json"
    if not path.exists():
        return None, []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return path, data.get("packets", [])

def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None

def extract_poll_from_markdown(day):
    path = ROOT / "pipeline" / "bond_funnel" / "lena" / day / "LENA_BOND_FUNNEL_POLL_PLAN.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    out = {}
    # Split at lines that look like "2026-06-12-03-video — fitness"
    pattern = re.compile(r"(?m)^(\d{4}-\d{2}-\d{2}-\d{2}-(?:photo|video))\s+—\s+.*$")
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        slot = m.group(1).strip()
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start:end]
        item = {}
        for label, key in [
            ("Post poll", "post_poll"),
            ("Story poll", "story_poll"),
            ("Question box", "question_box"),
            ("Pinned comment", "pinned_comment"),
            ("Comment reply seed", "comment_reply_seed"),
            ("Tomorrow loop", "tomorrow_loop")
        ]:
            lm = re.search(rf"(?is){re.escape(label)}\s*\n(.+?)(?=\n(?:Post poll|Story poll|Question box|Follow-up story|Pinned comment|Comment reply seed|Tomorrow loop|Public text score)|\Z)", block)
            if lm:
                item[key] = " ".join(lm.group(1).strip().split())
        out[slot] = item
    return out

def load_bond(day):
    out = {}
    path = ROOT / "pipeline" / "bond_funnel" / "lena" / day / "lena_bond_funnel_poll_plan_v2_5.json"
    data = read_json(path)
    if data:
        for item in data.get("items", []):
            if item.get("slot_id"):
                out[item.get("slot_id")] = item
    # Markdown is the most human-readable truth and preserves options even if JSON schema shifts.
    md = extract_poll_from_markdown(day)
    for slot, item in md.items():
        out.setdefault(slot, {}).update({k: v for k, v in item.items() if v})
    return out

def canon_platforms(text, policy):
    allowed = {p.lower(): p for p in policy.get("allowed_platforms", [])}
    if not text:
        return []
    out = []
    for raw in text.replace(";", ",").split(","):
        p = raw.strip()
        if not p:
            continue
        c = allowed.get(p.lower(), p)
        if c not in out:
            out.append(c)
    return out

def platform_allowed_for_media(platform, media_type, policy):
    allowed_media = policy.get("platform_media_rules", {}).get(platform)
    if not allowed_media:
        return True
    return media_type in allowed_media

def platforms_for_packet(packet, explicit_platforms, policy):
    mt = packet.get("media_type") or "photo"
    if explicit_platforms:
        return [p for p in explicit_platforms if platform_allowed_for_media(p, mt, policy)]
    return policy.get("default_platforms_by_media_type", {}).get(mt, [])

def queue_id(day, slot_id, platform):
    return "q_" + hashlib.sha1(f"{day}|{slot_id}|{platform}".encode("utf-8")).hexdigest()[:14]

def safe_packet(packet, policy):
    score = packet.get("public_text_score", {}).get("score", 0)
    decision = packet.get("public_text_score", {}).get("decision", "")
    asset_path = packet.get("asset_path") or ""
    reasons = []
    if packet.get("asset_status") != policy.get("require_asset_status", "approved"):
        reasons.append("asset_status_not_approved")
    if score < int(policy.get("minimum_public_text_score", 85)) or decision != "APPROVED":
        reasons.append("public_text_not_approved")
    if policy.get("require_asset_file_exists", True) and (not asset_path or not Path(asset_path).exists()):
        reasons.append("asset_file_missing")
    if policy.get("require_public_action_locked", True) and packet.get("public_action_locked") is not True:
        reasons.append("public_action_locked_missing")
    if policy.get("require_manual_approval_required", True) and packet.get("manual_approval_required") is not True:
        reasons.append("manual_approval_flag_missing")
    return len(reasons) == 0, reasons

def poll_text(obj):
    if not obj:
        return ""
    if isinstance(obj, str):
        return " ".join(obj.strip().split())
    if isinstance(obj, dict):
        # Support many possible schema shapes.
        q = obj.get("question") or obj.get("prompt") or obj.get("label") or obj.get("text") or ""
        options = []
        for k in ["options", "choices", "answers"]:
            val = obj.get(k)
            if isinstance(val, list):
                options += [str(x).strip() for x in val if str(x).strip()]
            elif isinstance(val, dict):
                options += [str(x).strip() for x in val.values() if str(x).strip()]
        for k in ["option_a","option_b","choice_a","choice_b","a","b","left","right","answer_a","answer_b","option_1","option_2"]:
            if obj.get(k):
                options.append(str(obj.get(k)).strip())
        seen, clean = set(), []
        for o in options:
            if o and o.lower() not in seen:
                clean.append(o)
                seen.add(o.lower())
        if q and clean:
            return f"{q} — {' / '.join(clean[:2])}"
        if q:
            return q
        if clean:
            return " / ".join(clean[:2])
    return " ".join(str(obj).strip().split())

def read_existing_queue(path):
    if not path.exists():
        return []
    try:
        return list(csv.DictReader(path.open("r", encoding="utf-8")))
    except Exception:
        return []

def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
        wr.writeheader()
        wr.writerows([{k: r.get(k, "") for k in QUEUE_FIELDS} for r in rows])

def write_md(path, rows, rejected, skipped):
    day = rows[0]["date"] if rows else date.today().isoformat()
    lines = [
        f"# Lena Approved Publish Queue v2.8.2 — {day}",
        "",
        "Only approved packets are queued. Dry-run does not mutate queue state. Auto-DMs, auto-replies, and outreach remain locked.",
        "",
        f"Queued items: **{len(rows)}**",
        f"Rejected packets: **{len(rejected)}**",
        f"Skipped platform/media combos: **{len(skipped)}**",
        ""
    ]
    for r in rows:
        lines += [
            f"## {r['queue_id']} — {r['platform']} — {r['slot_id']}",
            "",
            f"- State: `{r['publish_state']}`",
            f"- Media: `{r['media_type']}`",
            f"- Lane: `{r['lane']}`",
            f"- Asset: `{r['asset_path']}`",
            f"- Connector: `{r['connector_path']}`",
            "",
            "### Caption",
            r["caption"],
            "",
            "### Post poll",
            r["post_poll"],
            "",
            "### Story prompt",
            r["story_prompt"],
            "",
            "### Human Review Checklist",
            "- [ ] Caption has no more than 3 hashtags.",
            "- [ ] In public/street/coffee/campus/café/errands/park/sidewalk scenes, "
            "wardrobe reads as real outerwear — not bra, lingerie, underwear, bikini, or bra-like top.",
            "- [ ] Facial skin reads as natural with real texture — "
            "not poreless, plastic, airbrushed, or mannequin-like.",
            ""
        ]
    if skipped:
        lines += ["# Skipped Platform/Media Combos", ""]
        for s in skipped:
            lines += [f"- `{s['slot_id']}` {s['media_type']} skipped `{s['platform']}`: {s['reason']}", ""]
    if rejected:
        lines += ["# Rejected / Not Queued", ""]
        for item in rejected:
            lines += [f"- `{item.get('slot_id')}`: {', '.join(item.get('reasons', []))}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--platforms", default="")
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    policy = load_policy()
    explicit_platforms = canon_platforms(args.platforms, policy)
    packet_path, packets = load_packets(args.date)
    bond = load_bond(args.date)

    outdir = ROOT / "pipeline" / "publishing" / "lena" / "approved_queue" / args.date
    csv_path = outdir / "lena_approved_publish_queue_v2_8.csv"
    json_path = outdir / "lena_approved_publish_queue_v2_8.json"
    md_path = outdir / "LENA_APPROVED_PUBLISH_QUEUE.md"

    existing = read_existing_queue(csv_path)
    existing_by_id = {r.get("queue_id"): r for r in existing}
    rows, rejected, skipped = [], [], []
    now = datetime.now().isoformat(timespec="seconds")
    connectors = policy.get("platform_connectors", {})

    # Only preserve actual posted rows. Everything else rebuilds to queued.
    for r in existing:
        if r.get("publish_state") == "posted":
            rows.append(r)

    for p in packets:
        ok, reasons = safe_packet(p, policy)
        if not ok:
            rejected.append({"slot_id": p.get("slot_id"), "reasons": reasons})
            continue

        platforms = platforms_for_packet(p, explicit_platforms, policy)
        for platform in explicit_platforms:
            if platform not in platforms:
                skipped.append({"slot_id": p.get("slot_id"), "media_type": p.get("media_type"), "platform": platform, "reason": "platform_not_allowed_for_media_type"})

        bf = bond.get(p.get("slot_id"), {})
        for platform in platforms:
            qid = queue_id(args.date, p.get("slot_id", ""), platform)
            old = existing_by_id.get(qid, {})
            if old.get("publish_state") == "posted":
                continue

            post_poll = poll_text(bf.get("post_poll")) or poll_text(p.get("post_poll"))
            story_prompt = poll_text(bf.get("story_poll")) or poll_text(p.get("story_prompt"))

            rows.append({
                "queue_id": qid,
                "date": args.date,
                "created_at": old.get("created_at") or now,
                "slot_id": p.get("slot_id", ""),
                "platform": platform,
                "media_type": p.get("media_type", ""),
                "lane": p.get("resolved_lane_key") or p.get("lane", ""),
                "asset_status": p.get("asset_status", ""),
                "asset_path": p.get("asset_path", ""),
                "caption": p.get("caption", ""),
                "short_caption": p.get("short_caption", ""),
                "pinned_comment": p.get("pinned_comment", ""),
                "story_prompt": story_prompt,
                "post_poll": post_poll,
                "keyword_notes": ", ".join(p.get("hashtags_keywords", []) or []),
                "public_text_score": p.get("public_text_score", {}).get("score", ""),
                "public_text_decision": p.get("public_text_score", {}).get("decision", ""),
                "publish_state": "queued",
                "publish_mode": policy.get("publish_mode", "connector_required"),
                "connector_path": connectors.get(platform, ""),
                "post_url": old.get("post_url", ""),
                "posted_at": old.get("posted_at", ""),
                "failure_reason": "",
                "notes": "Approved queue item. Public posting allowed only through platform connector. No replies, DMs, or outreach."
            })

    write_csv(csv_path, rows)
    report = {
        "ok": True,
        "version": "v2.8.2",
        "date": args.date,
        "packet_source": str(packet_path) if packet_path else "",
        "explicit_platforms": explicit_platforms,
        "queue_count": len(rows),
        "rejected_count": len(rejected),
        "skipped_count": len(skipped),
        "csv": str(csv_path),
        "json": str(json_path),
        "markdown": str(md_path),
        "items": rows,
        "rejected": rejected,
        "skipped": skipped
    }
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(md_path, rows, rejected, skipped)
    print(json.dumps({k: report[k] for k in ["ok","version","date","queue_count","rejected_count","skipped_count","csv","markdown"]}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
