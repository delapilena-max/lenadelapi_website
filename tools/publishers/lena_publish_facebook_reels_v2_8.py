from __future__ import annotations
import argparse, json
from pathlib import Path
from lena_meta_publish_common_v2_9 import (
    validate_config_for, ensure_public_media, fail,
    check_final_publish_approval,
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True)
    args = ap.parse_args()
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8-sig"))
    platform = "Facebook Reels"

    gate = check_final_publish_approval(payload)
    if not gate.get("ok"):
        print(json.dumps(fail(platform, payload, gate["reason"]), indent=2))
        return 1

    valid = validate_config_for(platform, "video")
    if not valid.get("ok"):
        print(json.dumps(fail(platform, payload, valid.get("reason","config_invalid"), valid), indent=2))
        return 1
    cfg = valid["config"]
    media = ensure_public_media(payload.get("asset_path",""), payload.get("queue_id",""), platform, cfg)
    if not media.get("ok"):
        print(json.dumps(fail(platform, payload, media.get("reason","media_public_url_failed"), media), indent=2))
        return 1

    # Facebook Reels Publishing uses a multi-step Video API flow. This connector slot is installed
    # but intentionally does not mark posted until the dedicated reels upload flow is configured/tested.
    print(json.dumps(fail(platform, payload, "facebook_reels_live_publish_requires_v2_9_1_reels_upload_flow", {"media": media}), indent=2))
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
