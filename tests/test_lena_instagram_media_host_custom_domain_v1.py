from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

import tools.publishers.lena_meta_publish_common_v2_9 as publish_common

ROOT = Path(__file__).resolve().parents[1]
PUBLISHERS_DIR = ROOT / "tools" / "publishers"
if str(PUBLISHERS_DIR) not in sys.path:
    sys.path.insert(0, str(PUBLISHERS_DIR))

import lena_publish_instagram_feed_v2_8 as instagram_feed  # type: ignore  # noqa: E402


CONFIG_PATH = ROOT / "pipeline" / "influencer_nodes" / "lena" / "meta_publisher_config_v2_9.local.json"


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "white").save(path, format="PNG")
    return path


def _production_cfg() -> dict:
    return {
        "media_public_base_url": "https://media.nicnodes.us",
        "r2_account_id": "acct",
        "r2_bucket_name": "nicnodes-media",
        "r2_public_base_url": "https://media.nicnodes.us",
    }


def test_checked_in_publisher_config_uses_production_custom_domain() -> None:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))

    assert cfg["media_public_base_url"] == "https://media.nicnodes.us"
    assert cfg["r2_bucket_name"] == "nicnodes-media"
    assert cfg["r2_public_base_url"] == "https://media.nicnodes.us"
    host = publish_common.classify_public_media_base_url(cfg)
    assert host["production_ready"] is True
    assert host["requires_custom_domain"] is False
    assert host["host_kind"] == "custom_or_external_https_host"


def test_r2_dev_public_media_host_is_not_production_ready() -> None:
    host = publish_common.classify_public_media_base_url(
        {"media_public_base_url": "https://pub-ee462a06dda9471ca44720da4c8597b5.r2.dev"}
    )

    assert host["production_ready"] is False
    assert host["requires_custom_domain"] is True
    assert host["host_kind"] == "cloudflare_r2_development_host"


def test_missing_uploader_fails_closed_before_any_local_server_fallback(tmp_path: Path, monkeypatch) -> None:
    asset = _write_png(tmp_path / "candidate.png")
    monkeypatch.setattr(publish_common, "_r2_secret_presence", lambda root=None: {"R2_ACCESS_KEY_ID": True, "R2_SECRET_ACCESS_KEY": True})
    monkeypatch.setattr(publish_common, "_r2_uploader_status", lambda: {"available": False, "detail": "missing uploader"})

    result = publish_common.ensure_public_media(str(asset), "q-test", "Instagram Feed", _production_cfg())

    assert result["ok"] is False
    assert result["reason"] == "r2_uploader_unavailable"


def test_successful_r2_upload_uses_exact_key_and_custom_domain(tmp_path: Path, monkeypatch) -> None:
    asset = _write_png(tmp_path / "candidate.png")
    expected_date = publish_common.datetime.now().strftime("%Y-%m-%d")
    expected_key = f"lena/{expected_date}/q-test_Instagram_Feed.png"

    monkeypatch.setattr(publish_common, "_r2_secret_presence", lambda root=None: {"R2_ACCESS_KEY_ID": True, "R2_SECRET_ACCESS_KEY": True})
    monkeypatch.setattr(publish_common, "_r2_uploader_status", lambda: {"available": True, "detail": ""})

    observed: dict[str, object] = {}

    def fake_upload(src: Path, key: str, cfg: dict, root=None):
        observed["key"] = key
        return {"ok": True, "public_url": f"https://media.nicnodes.us/{key}", "key": key}

    def fake_verify(media_url: str, **kwargs):
        observed["media_url"] = media_url
        observed["verify_kwargs"] = kwargs
        return {"ok": True, "media_url": media_url, "sha256": kwargs["expected_sha256"]}

    monkeypatch.setattr(publish_common, "_try_r2_upload", fake_upload)
    monkeypatch.setattr(publish_common, "verify_hosted_media_before_container", fake_verify)

    result = publish_common.ensure_public_media(str(asset), "q-test", "Instagram Feed", _production_cfg())

    assert result["ok"] is True
    assert result["upload_method"] == "r2"
    assert result["r2_key"] == expected_key
    assert observed["key"] == expected_key
    assert observed["media_url"] == f"https://media.nicnodes.us/{expected_key}"
    assert result["pre_container_media_verification"]["ok"] is True


def test_host_verification_failure_blocks_meta_call_boundary(tmp_path: Path, monkeypatch) -> None:
    payload_path = tmp_path / "payload.json"
    asset = _write_png(tmp_path / "candidate.png")
    payload_path.write_text(
        json.dumps(
            {
                "queue_id": "q-test",
                "platform": "Instagram Feed",
                "media_type": "photo",
                "asset_path": str(asset),
                "caption": "The mirror said keep it.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(instagram_feed, "check_final_publish_approval", lambda payload: {"ok": True})
    monkeypatch.setattr(instagram_feed, "validate_config_for", lambda platform, media_type: {"ok": True, "config": _production_cfg()})
    monkeypatch.setattr(instagram_feed, "preflight_token", lambda cfg, platform: {"ok": True})
    monkeypatch.setattr(
        instagram_feed,
        "ensure_public_media",
        lambda asset_path, queue_id, platform, cfg: {
            "ok": False,
            "reason": "pre_container_media_verification_failed",
            "detail": "hosted_media_http_error:403",
        },
    )

    def forbidden_graph_post(*args, **kwargs):
        raise AssertionError("Meta graph_post must not run when host verification fails")

    monkeypatch.setattr(instagram_feed, "graph_post", forbidden_graph_post)
    monkeypatch.setattr(sys, "argv", ["lena_publish_instagram_feed_v2_8.py", "--payload", str(payload_path)])

    assert instagram_feed.main() == 1
