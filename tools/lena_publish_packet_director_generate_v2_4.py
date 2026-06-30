from __future__ import annotations
import argparse, csv, json, re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
ASSET_MEMORY = ROOT / "pipeline" / "content_library" / "lena" / "lena_asset_memory_v1_8.csv"

def load_policy() -> dict:
    return json.loads((NODE / "publish_packet_director_policy_v2_4.json").read_text(encoding="utf-8-sig"))

def load_asset_memory() -> list[dict]:
    if not ASSET_MEMORY.exists():
        return []
    try:
        return list(csv.DictReader(ASSET_MEMORY.open("r", encoding="utf-8")))
    except Exception:
        return []

def load_workorder(day: str, slot_id: str) -> dict:
    if not slot_id:
        return {}
    p = ROOT / "pipeline" / "provider_workorders" / "openart_seedance" / day / f"{slot_id}_provider_workorder.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}

def lane_key(*vals) -> str:
    t = " ".join(str(v or "").lower() for v in vals)
    if "coffee" in t:
        return "coffee"
    if "dinner" in t or "cook" in t or "kitchen" in t:
        return "dinner"
    if "fitness" in t or "movement" in t or "workout" in t or "reel" in t or "stretch flow" in t:
        return "fitness"
    if "outfit" in t or "fit check" in t or "body_confidence" in t:
        return "outfit"
    if "humor" in t or "pov" in t or "red flag" in t or "green flag" in t:
        return "humor"
    if "stretch" in t or "wellness" in t or "reset" in t:
        return "stretch"
    return "default"

def source_meta(src: dict) -> dict:
    meta = src.get("metadata")
    return meta if isinstance(meta, dict) else {}

def first_nonblank(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""

def infer_growth_bucket(src: dict, lane_resolved_key: str, media_type_value: str) -> str:
    meta = source_meta(src)
    value = first_nonblank(
        src.get("growth_bucket"),
        src.get("bucket"),
        src.get("content_bucket"),
        meta.get("growth_bucket"),
        meta.get("bucket"),
    )
    if value:
        return value
    if lane_resolved_key in {"fitness", "stretch"}:
        return "bond_funnel"
    if lane_resolved_key in {"coffee", "outfit", "humor", "dinner"}:
        return "engagement"
    if media_type_value == "video":
        return "bond_funnel"
    return ""

def infer_hook_category(src: dict, lane_resolved_key: str) -> str:
    meta = source_meta(src)
    overlay = src.get("overlay_brief") if isinstance(src.get("overlay_brief"), dict) else {}
    value = first_nonblank(
        src.get("hook_category"),
        src.get("hook_group"),
        src.get("overlay_hook_category"),
        overlay.get("hook_category"),
        meta.get("hook_category"),
        meta.get("hook_group"),
    )
    if value:
        return value
    mapping = {
        "fitness": "low_energy_workout",
        "stretch": "morning_reset",
        "coffee": "coffee_walk",
        "outfit": "outfit_check",
        "humor": "playful_hook",
        "dinner": "night_routine",
    }
    return mapping.get(lane_resolved_key, "")

def infer_audio_name(src: dict) -> str:
    meta = source_meta(src)
    return first_nonblank(
        src.get("audio_name"),
        src.get("selected_audio_name"),
        meta.get("audio_name"),
        meta.get("selected_audio_name"),
    )

def media_type(src: dict) -> str:
    t = str(src.get("media_type") or src.get("workorder_type") or src.get("type") or "").lower()
    return "video" if ("video" in t or "reel" in t) else "photo"

def score_public_text(text: str, blocked: list[str]) -> dict:
    warnings, score = [], 100
    for term in blocked:
        pat = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        if re.search(pat, text, flags=re.I):
            score -= 35
            warnings.append(f"blocked public term found: {term}")
    if len(text.strip()) < 40:
        score -= 10
        warnings.append("public text thin")
    score = max(0, score)
    return {"score": score, "decision": "APPROVED" if score >= 85 else "NEEDS_REVISION", "warnings": warnings}

def best_memory_match(src: dict, memory_rows: list[dict]) -> dict:
    slot = src.get("slot_id") or src.get("asset_slot_id") or ""
    asset_path = src.get("asset_path") or src.get("canonical_path") or ""
    asset_id = src.get("asset_id") or ""

    candidates = []
    for r in memory_rows:
        score = 0
        if slot and r.get("slot_id") == slot:
            score += 100
        if asset_id and r.get("asset_id") == asset_id:
            score += 80
        if asset_path and (asset_path == r.get("canonical_path") or asset_path == r.get("source_path")):
            score += 60
        if r.get("status") == "approved":
            score += 30
        if (r.get("provider") or "").lower() in {"openart", "seedance"}:
            score += 20
        if score:
            candidates.append((score, r))
    if not candidates:
        return {}
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def source_rows(day: str):
    memory_rows = load_asset_memory()

    # Prefer publish readiness once assets exist, but enrich every row from asset memory and workorder.
    pr = ROOT / "pipeline" / "publish_readiness" / "lena" / day / "publish_readiness_packet_v2_1.json"
    if pr.exists():
        try:
            data = json.loads(pr.read_text(encoding="utf-8-sig"))
            packets = data.get("packets") or []
            if packets:
                enriched = []
                for p in packets:
                    slot = p.get("slot_id") or p.get("asset_slot_id") or ""
                    mem = best_memory_match(p, memory_rows)
                    wo = load_workorder(day, slot)
                    merged = {}
                    merged.update(wo)
                    merged.update(mem)
                    merged.update(p)
                    # Preserve memory/workorder values when publish readiness has blanks/unknowns.
                    for k in ["lane", "outfit", "location", "pose_motion", "mood", "provider", "media_type", "canonical_path", "status"]:
                        if (not merged.get(k)) or str(merged.get(k)).lower() == "unknown":
                            if mem.get(k):
                                merged[k] = mem.get(k)
                            elif wo.get(k):
                                merged[k] = wo.get(k)
                    if mem.get("canonical_path"):
                        merged["asset_path"] = mem.get("canonical_path")
                    if mem.get("status"):
                        merged["asset_status"] = mem.get("status")
                    if not merged.get("slot_id"):
                        merged["slot_id"] = slot
                    merged["asset_memory_status"] = mem.get("status", "")
                    merged["asset_quality_score"] = mem.get("quality_score", "")
                    merged["asset_memory_source"] = (
                        "asset_memory_v1_8" if mem else "not_matched"
                    )
                    merged["metadata_bridge_status"] = (
                        "matched" if mem else "no_match"
                    )
                    enriched.append(merged)
                return "publish_readiness+asset_memory_bridge", enriched
        except Exception:
            pass

    # Then asset memory directly.
    if memory_rows:
        usable = [
            r for r in memory_rows
            if (r.get("status", "").lower() in {"approved", "reviewed", "imported", "unused", "posted"})
        ]
        usable_today = [r for r in usable if (r.get("date") or "") == day]
        if usable_today:
            return "asset_memory", usable_today
        if usable:
            return "asset_memory", usable

    # Fallback to OpenArt/Seedance workorders.
    wd = ROOT / "pipeline" / "provider_workorders" / "openart_seedance" / day
    rows = []
    if wd.exists():
        for f in sorted(wd.glob("*_provider_workorder.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8-sig"))
                d["_source_file"] = str(f)
                rows.append(d)
            except Exception:
                pass
    return "workorder", rows

def make_packet(src: dict, day: str, source_type: str, policy: dict) -> dict:
    slot = src.get("slot_id") or src.get("asset_id") or f"{day}-packet"
    lane = src.get("lane") or src.get("content_lane") or src.get("growth_bucket") or src.get("series_id") or ""
    pillar = src.get("pillar") or src.get("content_pillar") or ""
    pose_motion = src.get("pose_motion") or src.get("shot_description") or src.get("scene") or ""
    mood = src.get("mood") or ""
    key = lane_key(lane, pillar, pose_motion, mood, slot)
    tpl = policy["lane_templates"].get(key, policy["lane_templates"]["default"])
    mt = media_type(src)
    growth_bucket = infer_growth_bucket(src, key, mt)
    hook_category = infer_hook_category(src, key)
    audio_name = infer_audio_name(src)

    public_text = "\n".join([tpl["caption"], tpl["short_caption"], tpl["pinned_comment"], tpl["story_prompt"]])
    score = score_public_text(public_text, policy["blocked_public_terms"])

    asset_status = (
        src.get("asset_status")
        or src.get("status")
        or ("asset_missing" if source_type == "workorder" else "unknown")
    )
    asset_path = (
        src.get("asset_path")
        or src.get("canonical_path")
        or src.get("source_path")
        or ""
    )

    return {
        "version": "v2.4.3_asset_status_bridge_fix",
        "date": day,
        "slot_id": slot,
        "source_type": source_type,
        "asset_status": asset_status,
        "asset_path": asset_path,
        "asset_id": src.get("asset_id", ""),
        "media_type": mt,
        "provider": src.get("provider", ""),
        "lane": lane or key,
        "resolved_lane_key": key,
        "growth_bucket": growth_bucket,
        "hook_category": hook_category,
        "audio_name": audio_name,
        "pillar": pillar,
        "caption": tpl["caption"],
        "short_caption": tpl["short_caption"],
        "pinned_comment": tpl["pinned_comment"],
        "story_prompt": tpl["story_prompt"],
        "cover_thumbnail_note": "Use a clear frame with Lena recognizable, clean background, and strong expression." if mt == "video" else "Keep Lena’s face clear, crop natural, and background uncluttered.",
        "crop_framing_note": "9:16 center-safe crop; keep face, hands, and main action in safe area." if mt == "video" else "Use 4:5 feed-safe crop for Instagram and 9:16 story/reel crop if repurposed.",
        "platform_notes": {
            "instagram": "Warm short-to-medium caption. Use story poll/question sticker after posting.",
            "tiktok": "Short hook-first caption. Choose audio manually in-app for movement/dance.",
            "facebook": "Slightly warmer conversational caption. Good for lifestyle/trust posts."
        },
        "hashtags_keywords": tpl["keywords"],
        "approval_checklist": policy["approval_checklist"],
        "asset_memory_status": src.get("asset_memory_status", ""),
        "asset_quality_score": src.get("asset_quality_score", ""),
        "asset_memory_source": src.get("asset_memory_source", "not_matched"),
        "metadata_bridge_status": src.get("metadata_bridge_status", "no_match"),
        "public_text_score": score,
        "manual_approval_required": True,
        "public_action_locked": True,
        "notes": [
            "Publish preparation only.",
            "No auto-posting.",
            "Human final publish approval required.",
            "Asset status bridge fix v2.4.3: resolved from asset memory by asset_id/slot_id."
        ]
    }

def write_markdown(path: Path, packets: list[dict], source_type: str, day: str):
    lines = [f"# Lena Publish Packets v2.4.2 Metadata Bridge — {day}", "", f"Source: **{source_type}**", "", "Manual approval required. No auto-posting.", ""]
    if not packets:
        lines.append("No packets available yet.")
    for p in packets:
        lines += [
            f"## {p['slot_id']} — {p['media_type']}",
            "",
            f"- Asset status: `{p['asset_status']}`",
            f"- Asset path: `{p['asset_path'] or 'not attached yet'}`",
            f"- Lane: `{p.get('lane')}`",
            f"- Resolved lane key: `{p.get('resolved_lane_key')}`",
            f"- Public text score: {p['public_text_score']['score']} / {p['public_text_score']['decision']}",
            "",
            "### Caption",
            p["caption"],
            "",
            "### Short caption",
            p["short_caption"],
            "",
            "### Pinned comment",
            p["pinned_comment"],
            "",
            "### First story prompt",
            p["story_prompt"],
            "",
            "### Cover / thumbnail note",
            p["cover_thumbnail_note"],
            "",
            "### Crop / framing note",
            p["crop_framing_note"],
            "",
            "### Platform notes",
            json.dumps(p["platform_notes"], indent=2),
            "",
            "### Keyword notes",
            ", ".join(p["hashtags_keywords"]),
            "",
            "### Approval checklist"
        ]
        for c in p["approval_checklist"]:
            lines.append(f"- [ ] {c}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    policy = load_policy()
    source_type, rows = source_rows(args.date)
    packets = [make_packet(r, args.date, source_type, policy) for r in rows]

    outdir = ROOT / "pipeline" / "publish_packets" / "lena" / args.date
    outdir.mkdir(parents=True, exist_ok=True)
    jpath = outdir / "lena_publish_packets_v2_4.json"
    mpath = outdir / "LENA_PUBLISH_PACKETS.md"
    report = {
        "ok": True,
        "version": "v2.4.3_asset_status_bridge_fix",
        "date": args.date,
        "source_type": source_type,
        "packet_count": len(packets),
        "manual_approval_required": True,
        "public_action_locked": True,
        "packets": packets
    }
    jpath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(mpath, packets, source_type, args.date)
    print(json.dumps({
        "ok": True,
        "version": "v2.4.3_asset_status_bridge_fix",
        "date": args.date,
        "source_type": source_type,
        "packet_count": len(packets),
        "json": str(jpath),
        "markdown": str(mpath),
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
