from __future__ import annotations
import json, mimetypes, os, shutil, sys, time, uuid, urllib.parse, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
LOCAL_CONFIG = NODE / "meta_publisher_config_v2_9.local.json"
EXAMPLE_CONFIG = NODE / "meta_publisher_config_v2_9.example.json"
ENV_MAP_FILE = NODE / "meta_env_key_map_v2_9_1.json"
ENV_ROOT_KEYS = ("LENA_AUTOPUBLISH_PRODUCTION_ROOT", "CONTENT_BOT_ROOT")


def _resolve_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root).expanduser().resolve()
    for env_key in ENV_ROOT_KEYS:
        raw = os.environ.get(env_key, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    return ROOT


def _node_root(root: Path | None = None) -> Path:
    return _resolve_root(root) / "pipeline" / "influencer_nodes" / "lena"


def _local_config_path(root: Path | None = None) -> Path:
    return _node_root(root) / "meta_publisher_config_v2_9.local.json"


def _example_config_path(root: Path | None = None) -> Path:
    return _node_root(root) / "meta_publisher_config_v2_9.example.json"


def _env_map_path(root: Path | None = None) -> Path:
    return _node_root(root) / "meta_env_key_map_v2_9_1.json"

class MetaConnectorError(Exception):
    pass

def redact(s: str) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= 8:
        return "***"
    return s[:4] + "..." + s[-4:]

def parse_dotenv(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out

def _load_env_for_r2(root: Path | None = None) -> None:
    """Best-effort: populate os.environ with .env values so R2_* vars are visible."""
    for k, v in parse_dotenv(_resolve_root(root) / ".env").items():
        if not os.environ.get(k):
            os.environ[k] = v


def _r2_is_configured(root: Path | None = None) -> bool:
    _load_env_for_r2(root)
    return all(os.environ.get(k) for k in (
        "R2_ACCOUNT_ID", "R2_BUCKET_NAME",
        "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_BASE_URL",
    ))


def _try_r2_upload(src: Path, key: str) -> dict | None:
    """Upload src to R2 at key; return r2_uploader result or None on any error."""
    if not _r2_is_configured():
        return None
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from pipeline.media_host.r2_uploader import upload_file_to_r2  # type: ignore
        return upload_file_to_r2(src, key)
    except Exception:
        return None


def load_env_map(root: Path | None = None) -> dict:
    env_map_file = _env_map_path(root)
    if env_map_file.exists():
        return json.loads(env_map_file.read_text(encoding="utf-8-sig"))
    return {
        "env_file_candidates": [str(_resolve_root(root) / ".env")],
        "key_map": {},
        "defaults": {},
    }

def discover_dotenv_values(root: Path | None = None) -> dict:
    spec = load_env_map(root)
    found = {}
    sources = []
    env_values = dict(os.environ)
    for candidate in spec.get("env_file_candidates", []):
        p = Path(candidate)
        if not p.is_absolute():
            p = _resolve_root(root) / candidate
        vals = parse_dotenv(p)
        if vals:
            sources.append(str(p))
            env_values.update(vals)
    key_map = spec.get("key_map", {})
    for config_key, env_keys in key_map.items():
        for env_key in env_keys:
            if env_values.get(env_key):
                found[config_key] = env_values[env_key]
                found[f"_{config_key}_source"] = env_key
                break
    for k, v in spec.get("defaults", {}).items():
        found.setdefault(k, v)
    return {"values": found, "sources": sources}

def load_config(root: Path | None = None) -> dict:
    base_root = _resolve_root(root)
    local_config = _local_config_path(base_root)
    example_config = _example_config_path(base_root)
    cfg = {}
    if example_config.exists():
        try:
            cfg.update(json.loads(example_config.read_text(encoding="utf-8-sig")))
        except Exception:
            pass
    if local_config.exists():
        try:
            local = json.loads(local_config.read_text(encoding="utf-8-sig"))
            cfg.update({k: v for k, v in local.items() if v not in ("", None)})
        except Exception:
            pass

    discovered = discover_dotenv_values(base_root)
    # .env fills blanks/placeholders only; explicit local config wins.
    for k, v in discovered["values"].items():
        if k.startswith("_"):
            continue
        existing = str(cfg.get(k, "") or "")
        placeholder = "PASTE_" in existing or "YOUR_PUBLIC_MEDIA_HOST" in existing
        if not existing or placeholder:
            cfg[k] = v

    # Environment variables override last.
    env_map = {
        "META_PAGE_ACCESS_TOKEN": "page_access_token",
        "META_INSTAGRAM_ACCESS_TOKEN": "instagram_access_token",
        "META_IG_USER_ID": "instagram_business_account_id",
        "META_FACEBOOK_PAGE_ID": "facebook_page_id",
        "META_GRAPH_API_VERSION": "graph_api_version",
        "LENA_MEDIA_PUBLIC_BASE_URL": "media_public_base_url",
        "LENA_MEDIA_PUBLIC_LOCAL_DIR": "media_public_local_dir",
    }
    for env, key in env_map.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]

    # Backward compatibility: Instagram-only token can drive IG connector.
    if not cfg.get("page_access_token") and cfg.get("instagram_access_token"):
        cfg["page_access_token"] = cfg["instagram_access_token"]
        cfg["_page_access_token_alias"] = "instagram_access_token"

    return cfg

def token_for_platform(cfg: dict, platform: str) -> str:
    if _auth_mode(cfg) == "instagram_login" and platform.startswith("Instagram") and cfg.get("instagram_access_token"):
        return cfg["instagram_access_token"]
    return cfg.get("page_access_token", "")

def config_status(test_api: bool = False, root: Path | None = None) -> dict:
    cfg = load_config(root)
    discovered = discover_dotenv_values(root)
    def check(key, secret=False):
        val = str(cfg.get(key, "") or "")
        placeholder = "PASTE_" in val or "YOUR_PUBLIC_MEDIA_HOST" in val
        return {"ok": bool(val) and not placeholder, "value": redact(val) if secret else val}

    r2_ok    = _r2_is_configured(root)
    mode     = _auth_mode(cfg)
    checks = {
        "instagram_access_token": check("instagram_access_token", True),
        "page_access_token": check("page_access_token", True),
        "instagram_business_account_id": check("instagram_business_account_id", False),
        "facebook_page_id": check("facebook_page_id", False),
        "graph_api_version": check("graph_api_version", False),
        "media_public_base_url": check("media_public_base_url", False),
        "media_public_local_dir": check("media_public_local_dir", False),
        "r2_configured": {"ok": r2_ok, "note": "R2 env vars present — R2 upload active" if r2_ok else "R2 env vars not set"},
        "local_config_exists": {"ok": _local_config_path(root).exists(), "path": str(_local_config_path(root))},
        "dotenv_sources": {"ok": bool(discovered.get("sources")), "sources": discovered.get("sources", [])}
    }

    media_host_ok = checks["media_public_base_url"]["ok"] or r2_ok
    instagram_ready = checks["instagram_business_account_id"]["ok"] and (checks["instagram_access_token"]["ok"] or checks["page_access_token"]["ok"]) and media_host_ok
    facebook_ready = checks["facebook_page_id"]["ok"] and checks["page_access_token"]["ok"] and media_host_ok

    api_result = None
    if test_api:
        try:
            token = cfg.get("page_access_token") or cfg.get("instagram_access_token")
            if token:
                api_result = graph_get("/me", {"fields": "id,name"}, cfg, token_override=token)
            else:
                api_result = {"ok": False, "error": "no token available"}
        except Exception as e:
            api_result = {"ok": False, "error": str(e)}

    return {
        "ok": instagram_ready or facebook_ready,
        "version": "v2.9.1",
        "config_path": str(_local_config_path(root)),
        "checks": checks,
        "readiness": {
            "auth_mode":       mode,
            "graph_base_url":  graph_base(cfg),
            "instagram_ready": instagram_ready,
            "facebook_ready":  facebook_ready,
            "media_host_ready": (checks["media_public_base_url"]["ok"] and checks["media_public_local_dir"]["ok"]) or r2_ok,
            "media_host_method": "r2" if r2_ok else ("local_server" if checks["media_public_base_url"]["ok"] else "not_configured"),
        },
        "api_test": api_result
    }



def preflight_token(cfg: dict, platform: str = "") -> dict:
    """Validate token resolves cleanly before touching R2 or the Graph API."""
    token = token_for_platform(cfg, platform)
    if not token:
        return {"ok": False, "reason": "no_token_in_config"}
    try:
        data = graph_get("/me", {"fields": "id"}, cfg,
                         token_override=token, platform=platform)
        if "error" in data:
            code = data["error"].get("code", 0)
            sub  = data["error"].get("error_subcode", 0)
            msg  = data["error"].get("message", "unknown")
            if code == 190:
                return {
                    "ok": False, "reason": "token_expired",
                    "code": code, "subcode": sub, "message": msg,
                }
            return {
                "ok": False, "reason": "token_invalid",
                "code": code, "message": msg,
            }
        return {"ok": True, "me_id": data.get("id", "")}
    except Exception as exc:
        raw = str(exc)
        if "190" in raw:
            return {"ok": False, "reason": "token_expired", "detail": raw}
        return {"ok": False, "reason": "preflight_error", "detail": raw}


def validate_config_for(platform: str, media_type: str, root: Path | None = None) -> dict:
    status = config_status(False, root=root)
    cfg = load_config(root)
    if platform.startswith("Instagram"):
        if not cfg.get("instagram_business_account_id"):
            return {"ok": False, "reason": "missing_instagram_business_account_id", "status": status}
        if not (cfg.get("instagram_access_token") or cfg.get("page_access_token")):
            return {"ok": False, "reason": "missing_instagram_or_page_access_token", "status": status}
    elif platform.startswith("Facebook"):
        if not cfg.get("facebook_page_id"):
            return {"ok": False, "reason": "missing_facebook_page_id", "status": status}
        if not cfg.get("page_access_token"):
            return {"ok": False, "reason": "missing_page_access_token", "status": status}
    else:
        return {"ok": False, "reason": "unsupported_meta_platform", "status": status}
    if not cfg.get("media_public_base_url") or "YOUR_PUBLIC_MEDIA_HOST" in str(cfg.get("media_public_base_url")):
        if not _r2_is_configured(root):
            return {"ok": False, "reason": "missing_public_media_base_url_and_r2_not_configured", "status": status}
    return {"ok": True, "config": cfg}

def _auth_mode(cfg: dict) -> str:
    """Return 'instagram_login' or 'facebook_login'.

    Resolution order:
    1. Explicit cfg['auth_mode'] key ('instagram_login' | 'facebook_login').
    2. Auto-detect: IGAA token prefix → instagram_login; anything else → facebook_login.
    """
    explicit = str(cfg.get("auth_mode") or "").strip().lower()
    if explicit in ("instagram_login", "facebook_login"):
        return explicit
    token = str(cfg.get("instagram_access_token") or cfg.get("page_access_token") or "")
    return "instagram_login" if token.startswith("IGAA") else "facebook_login"


def graph_base(cfg: dict, platform: str = "") -> str:
    version = cfg.get("graph_api_version") or "v23.0"
    if platform.startswith("Facebook"):
        return f"https://graph.facebook.com/{version}"
    if _auth_mode(cfg) == "instagram_login":
        return f"https://graph.instagram.com/{version}"
    return f"https://graph.facebook.com/{version}"

def http_json(method: str, url: str, params: dict | None = None, timeout: int = 120) -> dict:
    params = params or {}
    data = None
    full_url = url
    headers = {"User-Agent": "LenaPublisher/2.9.1"}
    if method.upper() == "GET":
        full_url = url + ("?" + urllib.parse.urlencode(params) if params else "")
    else:
        data = urllib.parse.urlencode(params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(full_url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": False, "raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw}
        raise MetaConnectorError(json.dumps({"http_error": e.code, "url": url, "response": data}, ensure_ascii=False))
    except Exception as e:
        raise MetaConnectorError(str(e))

def graph_post(path: str, params: dict, cfg: dict, platform: str = "") -> dict:
    params = dict(params)
    params["access_token"] = token_for_platform(cfg, platform)
    return http_json("POST", graph_base(cfg, platform) + path, params)

def graph_get(path: str, params: dict, cfg: dict, token_override: str | None = None, platform: str = "") -> dict:
    params = dict(params)
    params["access_token"] = token_override or token_for_platform(cfg, platform)
    return http_json("GET", graph_base(cfg, platform) + path, params)

def exchange_page_token(cfg: dict) -> str:
    """Exchange the configured user token for a Page-scoped token via /me/accounts.

    Matches by facebook_page_id. Returns the page token string, or empty string
    if the exchange fails or the page is not found in the accounts list.
    """
    page_id = str(cfg.get("facebook_page_id", "")).strip()
    if not page_id:
        return ""
    try:
        data = http_json("GET", graph_base(cfg, "Facebook Page") + "/me/accounts", {
            "fields": "id,access_token",
            "limit": "100",
            "access_token": token_for_platform(cfg, "Facebook Page"),
        })
        for acct in data.get("data", []):
            if str(acct.get("id", "")).strip() == page_id:
                return acct.get("access_token", "")
    except Exception:
        pass
    return ""


def multipart_post(path: str, fields: dict, files: dict, cfg: dict, platform: str = "", token_override: str = "") -> dict:
    """POST multipart/form-data to the Graph API.

    fields: {name: str_value}
    files:  {name: (filename, bytes, mime_type)}

    access_token is injected automatically from token_for_platform.
    Raises MetaConnectorError on HTTP error (same contract as http_json).
    """
    boundary = uuid.uuid4().hex
    tok = token_override or token_for_platform(cfg, platform)
    url = graph_base(cfg, platform) + path

    body = b""
    for name, value in {"access_token": tok, **fields}.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")
    for name, (filename, data, mime) in files.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "LenaPublisher/2.9.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": False, "raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw}
        raise MetaConnectorError(json.dumps({"http_error": e.code, "url": url, "response": data}, ensure_ascii=False))
    except Exception as e:
        raise MetaConnectorError(str(e))

def ensure_public_media(asset_path: str, queue_id: str, platform: str, cfg: dict) -> dict:
    src = Path(asset_path)
    if not src.exists():
        return {"ok": False, "reason": "asset_file_missing", "asset_path": asset_path}
    date_part = datetime.now().strftime("%Y-%m-%d")
    safe_platform = "".join(c if c.isalnum() else "_" for c in platform)
    dest_name = f"{queue_id}_{safe_platform}{src.suffix.lower()}"

    # R2 path: upload to R2 and return the permanent public URL.
    r2 = _try_r2_upload(src, f"lena/{date_part}/{dest_name}")
    if r2 and r2.get("ok"):
        return {"ok": True, "local_path": str(src), "media_url": r2["public_url"], "upload_method": "r2"}

    # Local-server fallback: copy to media_public dir and build URL from base.
    base_url = str(cfg.get("media_public_base_url") or "").rstrip("/")
    local_dir = Path(str(cfg.get("media_public_local_dir") or ROOT / "pipeline" / "publishing" / "lena" / "media_public"))
    if not base_url or "YOUR_PUBLIC_MEDIA_HOST" in base_url:
        return {"ok": False, "reason": "media_public_base_url_not_configured"}
    dest_dir = local_dir / date_part
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / dest_name
    shutil.copy2(src, dest)
    media_url = f"{base_url}/{date_part}/{urllib.parse.quote(dest_name)}"
    return {"ok": True, "local_path": str(dest), "media_url": media_url, "upload_method": "local_server"}

def wait_for_container(creation_id: str, cfg: dict, platform: str = "", timeout_seconds: int = 900) -> dict:
    start = time.time()
    last = {}
    while time.time() - start < timeout_seconds:
        try:
            data = graph_get(f"/{creation_id}", {"fields": "status_code,status"}, cfg, platform=platform)
            last = data
            status = str(data.get("status_code") or data.get("status") or "").upper()
            if status in {"FINISHED", "PUBLISHED"}:
                return {"ok": True, "status": status, "last": last}
            if status in {"ERROR", "EXPIRED"}:
                return {"ok": False, "status": status, "last": last}
        except Exception as e:
            last = {"error": str(e)}
        time.sleep(15)
    return {"ok": False, "status": "TIMEOUT", "last": last}

def permalink(media_id: str, cfg: dict, platform: str = "") -> str:
    if not media_id:
        return ""
    try:
        data = graph_get(f"/{media_id}", {"fields": "permalink"}, cfg, platform=platform)
        return data.get("permalink", "")
    except Exception:
        return ""

def success(platform, payload, post_id, post_url="", extra=None):
    return {
        "ok": True, "posted": True, "version": "v2.9.1",
        "platform": platform, "queue_id": payload.get("queue_id"), "slot_id": payload.get("slot_id"),
        "post_id": post_id, "post_url": post_url,
        "posted_at": datetime.now().isoformat(timespec="seconds"),
        "extra": extra or {}
    }

def fail(platform, payload, reason, extra=None):
    return {
        "ok": False, "posted": False, "version": "v2.9.1",
        "platform": platform, "queue_id": payload.get("queue_id"), "slot_id": payload.get("slot_id"),
        "reason": reason, "extra": extra or {}
    }


# ── Final publish approval gate ───────────────────────────────────────────────


def _gate_resolve_path(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def check_final_publish_approval(payload: dict) -> dict:
    """Hard gate: verify publish authorization in the asset sidecar.
    The autonomous path uses standing-autonomy policy evidence; the legacy
    human-review path remains accepted for historical artifacts only.
    Call before token preflight, R2, or any Graph API call. Fails closed.
    """
    asset_raw = payload.get("asset_path", "")
    if not asset_raw:
        return {"ok": False, "reason": "gate_fail: payload missing asset_path"}

    asset_path = _gate_resolve_path(asset_raw)
    sidecar_path = asset_path.with_suffix(".status.json")

    if not sidecar_path.exists():
        return {
            "ok": False,
            "reason": "gate_fail: sidecar not found — " + sidecar_path.name,
        }

    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "reason": "gate_fail: sidecar unreadable"}

    blocked = sidecar.get("publish_blocked_reason")
    if blocked:
        return {
            "ok": False,
            "reason": "gate_fail: publish_blocked_reason=" + str(blocked),
        }

    if sidecar.get("instagram_published") is True:
        if sidecar.get("authorization_mode") != "standing_autonomy_policy":
            gate = sidecar.get("FINAL_PUBLISH_APPROVED_BY_NICOLAS")
            if not isinstance(gate, dict) or gate.get("republish_override") is not True:
                return {
                    "ok": False,
                    "reason": (
                        "gate_fail: instagram_published=true — set"
                        " FINAL_PUBLISH_APPROVED_BY_NICOLAS.republish_override=true to republish"
                    ),
                }
        elif sidecar.get("republish_override") is not True:
            return {
                "ok": False,
                "reason": (
                    "gate_fail: instagram_published=true — set republish_override=true to republish"
                ),
            }

    fails = []

    if sidecar.get("authorization_mode") == "standing_autonomy_policy":
        if sidecar.get("policy_id") in (None, ""):
            fails.append("policy_id missing or empty")
        if sidecar.get("policy_sha256") in (None, ""):
            fails.append("policy_sha256 missing or empty")
        if sidecar.get("cycle_id") in (None, ""):
            fails.append("cycle_id missing or empty")
        if sidecar.get("cycle_authorization_path") in (None, ""):
            fails.append("cycle_authorization_path missing or empty")
        if sidecar.get("cycle_authorization_sha256") in (None, ""):
            fails.append("cycle_authorization_sha256 missing or empty")
        if sidecar.get("qa_approved") is not True:
            fails.append("qa_approved != true")
        if sidecar.get("identity_verified") is not True:
            fails.append("identity_verified != true")
        if sidecar.get("duplicate_check_passed") is not True:
            fails.append("duplicate_check_passed != true")
        if sidecar.get("publish_authorized_by_policy") is not True:
            fails.append("publish_authorized_by_policy != true")
        if sidecar.get("human_per_cycle_approval_required") is not False:
            fails.append("human_per_cycle_approval_required != false")
        if sidecar.get("human_per_cycle_approval_present") is not False:
            fails.append("human_per_cycle_approval_present != false")
        if payload.get("caption", "") != sidecar.get("caption", ""):
            fails.append("caption mismatch: payload vs policy sidecar")
        if _gate_resolve_path(sidecar.get("asset_path", "")) != asset_path:
            fails.append("asset_path mismatch: payload vs policy sidecar")
        if payload.get("platform", "") != sidecar.get("target_platform", ""):
            fails.append("target_platform mismatch: payload vs policy sidecar")
    else:
        gate = sidecar.get("FINAL_PUBLISH_APPROVED_BY_NICOLAS")
        if not isinstance(gate, dict):
            return {
                "ok": False,
                "reason": (
                    "gate_fail: FINAL_PUBLISH_APPROVED_BY_NICOLAS"
                    " missing from sidecar"
                ),
            }

        if gate.get("approved") is not True:
            fails.append("approved != true")
        if gate.get("caption_visual_match_approved") is not True:
            fails.append("caption_visual_match_approved != true")
        objections = gate.get("known_visual_qa_objections")
        if objections not in (None, []):
            fails.append("known_visual_qa_objections not empty")
        if gate.get("approved_by") != "Nicolas":
            fails.append("approved_by != Nicolas")
        if not gate.get("approved_at"):
            fails.append("approved_at missing or empty")
        if payload.get("caption", "") != gate.get("caption", ""):
            fails.append("caption mismatch: payload vs gate")
        gate_asset_raw = gate.get("asset_path", "")
        if not gate_asset_raw:
            fails.append("asset_path missing from gate")
        elif _gate_resolve_path(gate_asset_raw) != asset_path:
            fails.append("asset_path mismatch: payload vs gate")
        payload_platform = payload.get("platform", "")
        gate_platform = gate.get("target_platform", "")
        if payload_platform != gate_platform:
            fails.append(
                "target_platform mismatch: payload="
                + repr(payload_platform)
                + " gate="
                + repr(gate_platform)
            )

    if fails:
        return {
            "ok": False,
            "reason": (
                "gate_fail: publish authorization checks failed: "
                + "; ".join(fails)
            ),
        }

    return {"ok": True}
