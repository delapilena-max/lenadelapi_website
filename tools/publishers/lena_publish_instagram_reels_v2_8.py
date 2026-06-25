from __future__ import annotations
import argparse, json
from pathlib import Path
from lena_meta_publish_common_v2_9 import (
    validate_config_for, preflight_token, ensure_public_media,
    graph_post, wait_for_container, permalink, success, fail,
    check_final_publish_approval,
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True)
    args = ap.parse_args()
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8-sig"))
    platform = "Instagram Reels"

    gate = check_final_publish_approval(payload)
    if not gate.get("ok"):
        print(json.dumps(fail(platform, payload, gate["reason"]), indent=2))
        return 1

    if payload.get("media_type") != "video":
        print(json.dumps(fail(platform, payload, "instagram_reels_connector_expects_video"), indent=2)); return 1
    valid = validate_config_for(platform, "video")
    if not valid.get("ok"):
        print(json.dumps(fail(platform, payload, valid.get("reason","config_invalid"), valid), indent=2)); return 1
    cfg = valid["config"]
    tok = preflight_token(cfg, platform)
    if not tok.get("ok"):
        print(json.dumps(fail(platform, payload,
            tok.get("reason", "token_check_failed"), tok), indent=2))
        return 1
    media = ensure_public_media(payload.get("asset_path",""), payload.get("queue_id",""), platform, cfg)
    if not media.get("ok"):
        print(json.dumps(fail(platform, payload, media.get("reason","media_public_url_failed"), media), indent=2)); return 1
    try:
        ig_id = cfg["instagram_business_account_id"]
        container = graph_post(f"/{ig_id}/media", {
            "media_type": "REELS",
            "video_url": media["media_url"],
            "caption": payload.get("caption",""),
            "share_to_feed": "true" if cfg.get("ig_share_reels_to_feed", True) else "false"
        }, cfg, platform=platform)
        creation_id = container.get("id")
        if not creation_id:
            print(json.dumps(fail(platform, payload, "ig_reel_container_missing_id", container), indent=2)); return 1
        ready = wait_for_container(creation_id, cfg, platform=platform, timeout_seconds=1200)
        if not ready.get("ok"):
            print(json.dumps(fail(platform, payload, "ig_reel_container_not_ready", ready), indent=2)); return 1
        published = graph_post(f"/{ig_id}/media_publish", {"creation_id": creation_id}, cfg, platform=platform)
        media_id = published.get("id","")
        print(json.dumps(success(platform, payload, media_id, permalink(media_id, cfg, platform=platform), {"container": container, "published": published, "media": media}), indent=2))
        return 0
    except Exception as e:
        print(json.dumps(fail(platform, payload, "instagram_reels_publish_error", {"error": str(e)}), indent=2)); return 1
if __name__ == "__main__":
    raise SystemExit(main())
