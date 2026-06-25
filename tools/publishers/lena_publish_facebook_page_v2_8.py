from __future__ import annotations
import argparse, json, mimetypes
from pathlib import Path
from lena_meta_publish_common_v2_9 import (
    validate_config_for, ensure_public_media,
    graph_post, multipart_post, exchange_page_token, success, fail,
    check_final_publish_approval,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True)
    ap.add_argument("--published", default="true",
                    help="Pass 'false' for a non-public staged probe (default: true)")
    args = ap.parse_args()

    payload   = json.loads(Path(args.payload).read_text(encoding="utf-8-sig"))
    platform  = "Facebook Page"
    published = args.published.strip().lower()   # "true" | "false"

    gate = check_final_publish_approval(payload)
    if not gate.get("ok"):
        print(json.dumps(fail(platform, payload, gate["reason"]), indent=2))
        return 1

    valid = validate_config_for(platform, payload.get("media_type", ""))
    if not valid.get("ok"):
        print(json.dumps(fail(platform, payload, valid.get("reason", "config_invalid"), valid), indent=2))
        return 1
    cfg     = valid["config"]
    page_id = cfg["facebook_page_id"]
    mt      = payload.get("media_type")

    # Resolve Page-scoped token; fall back to whatever is in config.
    page_tok = exchange_page_token(cfg) or cfg.get("page_access_token", "")

    try:
        if mt == "photo":
            # Facebook Page rejects url= parameter; use multipart binary upload.
            asset_path = Path(payload.get("asset_path", ""))
            if not asset_path.exists():
                print(json.dumps(fail(platform, payload, "asset_file_missing",
                                      {"asset_path": str(asset_path)}), indent=2))
                return 1
            mime = mimetypes.guess_type(str(asset_path))[0] or "image/png"
            resp = multipart_post(
                f"/{page_id}/photos",
                {"caption": payload.get("caption", ""), "published": published},
                {"source": (asset_path.name, asset_path.read_bytes(), mime)},
                cfg, platform, token_override=page_tok,
            )
            post_id = resp.get("post_id") or resp.get("id", "")
            print(json.dumps(success(platform, payload, post_id, "",
                                     {"response": resp, "published": published}), indent=2))
            return 0

        elif mt == "video":
            # Video still uses public URL path (stub — full Reels flow not yet implemented).
            media = ensure_public_media(
                payload.get("asset_path", ""), payload.get("queue_id", ""), platform, cfg)
            if not media.get("ok"):
                print(json.dumps(fail(platform, payload,
                                      media.get("reason", "media_public_url_failed"), media), indent=2))
                return 1
            resp = graph_post(f"/{page_id}/videos", {
                "file_url":    media["media_url"],
                "description": payload.get("caption", ""),
                "published":   published,
            }, cfg, platform)
            post_id = resp.get("id", "")
            print(json.dumps(success(platform, payload, post_id, "",
                                     {"response": resp, "media": media}), indent=2))
            return 0

        else:
            print(json.dumps(fail(platform, payload, "unsupported_media_type_for_facebook_page"), indent=2))
            return 1

    except Exception as e:
        print(json.dumps(fail(platform, payload, "facebook_page_publish_error",
                              {"error": str(e)}), indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
