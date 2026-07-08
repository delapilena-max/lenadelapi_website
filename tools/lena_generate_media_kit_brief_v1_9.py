from __future__ import annotations
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
def avg(nums):
    nums = [float(x) for x in nums if str(x).strip()]
    return round(sum(nums)/len(nums), 2) if nums else 0
def main() -> int:
    schema = json.loads((NODE / "media_kit_schema_v1_9.json").read_text(encoding="utf-8-sig"))

    ai_disclosure = str(schema.get("profile_fields", {}).get("ai_disclosure") or "").strip()
    if not ai_disclosure:
        print(json.dumps({
            "ok": False,
            "error": "profile_fields.ai_disclosure is missing or empty in media_kit_schema_v1_9.json. "
                     "Per ai_disclosure_rule in that schema and disclosure_compliance_policy_v1_9.json "
                     "(ai_virtual_creator_disclosure), no media kit brief may be emitted without a concrete "
                     "AI/virtual-creator disclosure statement. Refusing to emit a brief."
        }, indent=2, ensure_ascii=False))
        return 1

    path = ROOT / schema["csv_path"]
    rows = list(csv.DictReader(path.open("r", encoding="utf-8"))) if path.exists() else []
    brief = {
        "ok": True,
        "version": "v1.9.0",
        "profile": schema["profile_fields"],
        "ai_disclosure": ai_disclosure,
        "metrics_rows": len(rows),
        "metrics_summary": {
            "avg_reach": avg([r.get("avg_reach", "") for r in rows]),
            "avg_views": avg([r.get("avg_views", "") for r in rows]),
            "avg_engagement_rate": avg([r.get("avg_engagement_rate", "") for r in rows])
        },
        "readiness_note": "Use only logged metrics in public/media-kit materials. If metrics_rows is 0, this is a structure only, not a finished media kit. ai_disclosure above must be included verbatim in any brand-facing copy of this brief."
    }
    print(json.dumps(brief, indent=2, ensure_ascii=False))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
