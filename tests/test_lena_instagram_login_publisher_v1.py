from __future__ import annotations

from pathlib import Path

import tools.publishers.lena_meta_publish_common_v2_9 as publish_common


SECRET = "IGAA_SECRET_TOKEN_SHOULD_NOT_APPEAR"
IG_ID = "17841409711154047"


def _status() -> dict:
    return {
        "checks": {
            "env_map_contract": {"ok": True},
            "canonical_secret_source": {"ok": True},
        }
    }


def _cfg(token: str = SECRET, ig_id: str = IG_ID) -> dict:
    return {
        "auth_mode": "instagram_login",
        "graph_api_version": "v25.0",
        "instagram_login_access_token": token,
        "instagram_professional_account_id": ig_id,
        "media_public_base_url": "https://media.nicnodes.us",
        "r2_public_base_url": "https://media.nicnodes.us",
    }


def _ready_media_route() -> dict:
    return {
        "ok": True,
        "route": "r2",
        "media_public_base_url": "https://media.nicnodes.us",
        "host": {"host_kind": "custom_or_external_https_host", "production_ready": True},
        "missing_nonsecret_keys": [],
        "missing_secret_keys": [],
    }


def test_instagram_login_readiness_uses_graph_instagram_and_no_page_discovery(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(publish_common, "config_status", lambda test_api=False, root=None: _status())
    monkeypatch.setattr(publish_common, "load_config", lambda root=None: _cfg())
    monkeypatch.setattr(publish_common, "resolve_media_host_route", lambda cfg, root=None: _ready_media_route())

    def fake_graph_get(path, params, cfg, token_override=None, platform=""):
        calls.append((publish_common.graph_base(cfg, platform) + path, path))
        assert token_override == SECRET
        if path == "/me":
            return {"id": IG_ID, "username": "lena", "account_type": "BUSINESS"}
        if path == "/debug_token":
            return {"data": {"scopes": ["instagram_business_basic", "instagram_business_content_publish"], "expires_at": 9999999999}}
        raise AssertionError(f"unexpected graph path: {path}")

    monkeypatch.setattr(publish_common, "graph_get", fake_graph_get)

    report = publish_common.validate_instagram_login_readiness(root=Path("unused"))

    assert report["ok"] is True
    assert report["graph_base_url"] == "https://graph.instagram.com/v25.0"
    assert all(url.startswith("https://graph.instagram.com/v25.0/") for url, _ in calls)
    assert not any(path == "/me/accounts" for _, path in calls)
    assert SECRET not in str(report)
    assert report["instagram_container_created"] is False
    assert report["publish_calls_performed"] == 0


def test_missing_instagram_login_token_blocks_without_graph_calls(monkeypatch) -> None:
    monkeypatch.setattr(publish_common, "config_status", lambda test_api=False, root=None: _status())
    monkeypatch.setattr(publish_common, "load_config", lambda root=None: _cfg(token=""))
    monkeypatch.setattr(publish_common, "resolve_media_host_route", lambda cfg, root=None: _ready_media_route())

    def fail_graph(*args, **kwargs):
        raise AssertionError("missing token must block before graph calls")

    monkeypatch.setattr(publish_common, "graph_get", fail_graph)

    report = publish_common.validate_instagram_login_readiness(root=Path("unused"))

    assert report["ok"] is False
    assert report["reason"] == "instagram_login_access_token_missing"
    assert report["instagram_container_created"] is False
    assert report["publish_calls_performed"] == 0


def test_invalid_instagram_login_token_is_sanitized(monkeypatch) -> None:
    monkeypatch.setattr(publish_common, "config_status", lambda test_api=False, root=None: _status())
    monkeypatch.setattr(publish_common, "load_config", lambda root=None: _cfg())
    monkeypatch.setattr(publish_common, "resolve_media_host_route", lambda cfg, root=None: _ready_media_route())

    def fake_graph_get(path, params, cfg, token_override=None, platform=""):
        assert path == "/me"
        return {"error": {"code": 190, "message": f"bad token {SECRET}"}}

    monkeypatch.setattr(publish_common, "graph_get", fake_graph_get)

    report = publish_common.validate_instagram_login_readiness(root=Path("unused"))

    assert report["ok"] is False
    assert report["reason"] == "instagram_token_invalid"
    assert SECRET not in str(report)
    assert report["instagram_container_created"] is False


def test_missing_content_publish_scope_blocks_before_generation(monkeypatch) -> None:
    monkeypatch.setattr(publish_common, "config_status", lambda test_api=False, root=None: _status())
    monkeypatch.setattr(publish_common, "load_config", lambda root=None: _cfg())
    monkeypatch.setattr(publish_common, "resolve_media_host_route", lambda cfg, root=None: _ready_media_route())

    def fake_graph_get(path, params, cfg, token_override=None, platform=""):
        if path == "/me":
            return {"id": IG_ID, "username": "lena", "account_type": "BUSINESS"}
        if path == "/debug_token":
            return {"data": {"scopes": ["instagram_business_basic"]}}
        raise AssertionError(f"unexpected graph path: {path}")

    monkeypatch.setattr(publish_common, "graph_get", fake_graph_get)

    report = publish_common.validate_instagram_login_readiness(root=Path("unused"))

    assert report["ok"] is False
    assert report["reason"] == "instagram_business_content_publish_scope_missing"
    assert report["instagram_container_created"] is False
    assert report["publish_calls_performed"] == 0


def test_graph_base_for_active_instagram_route_never_uses_facebook_host() -> None:
    cfg = _cfg()
    assert publish_common.graph_base(cfg, "Instagram Feed") == "https://graph.instagram.com/v25.0"
    assert publish_common.graph_base(cfg, "Instagram Reels") == "https://graph.instagram.com/v25.0"
