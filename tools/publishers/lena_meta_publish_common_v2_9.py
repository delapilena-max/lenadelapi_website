from __future__ import annotations
import hashlib, importlib, json, mimetypes, os, shutil, sys, time, uuid, urllib.parse, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "pipeline" / "influencer_nodes" / "lena"
LOCAL_CONFIG = NODE / "meta_publisher_config_v2_9.local.json"
EXAMPLE_CONFIG = NODE / "meta_publisher_config_v2_9.example.json"
ENV_MAP_FILE = NODE / "meta_env_key_map_v2_9_1.json"
ENV_ROOT_KEYS = ("LENA_AUTOPUBLISH_PRODUCTION_ROOT", "CONTENT_BOT_ROOT")
ENV_MAP_CONTRACT_ID = "lena_meta_env_key_map_v2_9_1"
ENV_MAP_SCHEMA_VERSION = "v1"
CANONICAL_PUBLISHER_SECRET_ENV_OVERRIDE = "LENA_CANONICAL_PUBLISHER_SECRET_ENV_FILE"
CANONICAL_PUBLISHER_SECRET_ENV_PATH = Path(r"C:\projects\ai\content_bot\.env")
CANONICAL_PUBLISHER_SECRET_SOURCE_AUTHORITY = "content_bot_shared_secret_env"
ENV_VAR_TO_CONFIG_KEY = {
    "INSTAGRAM_LOGIN_ACCESS_TOKEN": "instagram_login_access_token",
    "INSTAGRAM_PROFESSIONAL_ACCOUNT_ID": "instagram_professional_account_id",
    "META_GRAPH_API_VERSION": "graph_api_version",
    "LENA_MEDIA_PUBLIC_BASE_URL": "media_public_base_url",
    "LENA_MEDIA_PUBLIC_LOCAL_DIR": "media_public_local_dir",
}
GOVERNED_PUBLISHER_SECRET_ENV_KEYS = (
    "INSTAGRAM_LOGIN_ACCESS_TOKEN",
    "INSTAGRAM_PROFESSIONAL_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)
REQUIRED_INSTAGRAM_LOGIN_SCOPES = frozenset(
    {
        "instagram_business_basic",
        "instagram_business_content_publish",
    }
)
R2_SECRET_ENV_KEYS = (
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)
R2_NONSECRET_CONFIG_KEYS = (
    "r2_account_id",
    "r2_bucket_name",
    "r2_public_base_url",
)
LOCAL_MEDIA_PUBLIC_DIR_REL = Path("pipeline") / "publishing" / "lena" / "media_public"
TEST_OR_PLACEHOLDER_PUBLIC_HOSTS = {"example.invalid"}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
WEBP_RIFF_MAGIC = b"RIFF"
WEBP_WEBP_MAGIC = b"WEBP"


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

class ConfigContractError(MetaConnectorError):
    pass

class MediaHostVerificationError(MetaConnectorError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def redact(s: str) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= 8:
        return "***"
    return s[:4] + "..." + s[-4:]

def sanitize_provider_value(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            raw_key = str(key)
            if any(marker in raw_key.lower() for marker in ("token", "secret", "authorization", "access_token")):
                out[raw_key] = "***"
            elif raw_key.lower() == "message":
                out[raw_key] = "[redacted]"
            else:
                out[raw_key] = sanitize_provider_value(item)
        return out
    if isinstance(value, list):
        return [sanitize_provider_value(item) for item in value]
    if isinstance(value, str):
        parsed = urllib.parse.urlsplit(value)
        if parsed.query and any(key in urllib.parse.parse_qs(parsed.query) for key in ("access_token", "client_secret", "appsecret_proof")):
            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            safe_query = urllib.parse.urlencode([(key, "***" if key in {"access_token", "client_secret", "appsecret_proof"} else item) for key, item in query])
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, parsed.fragment))
    return value

def sanitize_exception(exc: Exception) -> dict:
    raw = str(exc)
    try:
        parsed = json.loads(raw)
        return sanitize_provider_value(parsed)
    except Exception:
        return {"error_type": type(exc).__name__}

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

def _is_placeholder(value: object) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    return any(
        marker in raw
        for marker in (
            "PASTE_",
            "YOUR_PUBLIC_MEDIA_HOST",
            "YOUR_MEDIA_ROOT",
            "PLACEHOLDER",
        )
    )


def _public_host_kind(url: str) -> str:
    host = urllib.parse.urlparse(str(url or "")).hostname or ""
    host = host.lower()
    if host in TEST_OR_PLACEHOLDER_PUBLIC_HOSTS:
        return "test_or_placeholder_host"
    if host.endswith(".r2.dev"):
        return "cloudflare_r2_development_host"
    if host:
        return "custom_or_external_https_host"
    return "missing_or_invalid_host"


def classify_public_media_base_url(cfg: dict) -> dict:
    raw = str(cfg.get("media_public_base_url") or cfg.get("r2_public_base_url") or "").strip()
    kind = _public_host_kind(raw)
    return {
        "url": raw,
        "host_kind": kind,
        "production_ready": bool(raw.lower().startswith("https://")) and kind == "custom_or_external_https_host",
        "requires_custom_domain": kind == "cloudflare_r2_development_host",
        "test_or_placeholder_host": kind == "test_or_placeholder_host",
    }


def _public_media_env_override_allowed(existing: str, env_value: str) -> bool:
    existing = str(existing or "").strip()
    env_value = str(env_value or "").strip()
    existing_is_blank_or_placeholder = (
        not existing
        or _is_placeholder(existing)
        or _public_host_kind(existing) == "test_or_placeholder_host"
    )
    if existing_is_blank_or_placeholder:
        return True
    return _public_host_kind(env_value) == "custom_or_external_https_host"


def _expected_content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _matches_magic(body: bytes, expected_content_type: str) -> bool:
    if expected_content_type == "image/png":
        return body.startswith(PNG_MAGIC)
    if expected_content_type == "image/jpeg":
        return body.startswith(JPEG_MAGIC)
    if expected_content_type == "image/webp":
        return len(body) >= 12 and body.startswith(WEBP_RIFF_MAGIC) and body[8:12] == WEBP_WEBP_MAGIC
    return bool(body)

def _default_media_public_local_dir(root: Path | None = None) -> str:
    return str(_resolve_root(root) / LOCAL_MEDIA_PUBLIC_DIR_REL)

def _load_file_config_only(root: Path | None = None) -> dict:
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
    return cfg

def load_file_config(root: Path | None = None) -> dict:
    return dict(_load_file_config_only(root))

def canonical_publisher_secret_source_path() -> Path:
    raw = os.environ.get(CANONICAL_PUBLISHER_SECRET_ENV_OVERRIDE, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return CANONICAL_PUBLISHER_SECRET_ENV_PATH

def load_canonical_publisher_secret_source(root: Path | None = None) -> dict:
    path = canonical_publisher_secret_source_path()
    if not path.is_file():
        raise ConfigContractError(f"missing canonical publisher secret source: {path}")
    raw_values = parse_dotenv(path)
    values = {
        key: raw_values[key]
        for key in GOVERNED_PUBLISHER_SECRET_ENV_KEYS
        if raw_values.get(key)
    }
    return {
        "authority": CANONICAL_PUBLISHER_SECRET_SOURCE_AUTHORITY,
        "path": str(path),
        "values": values,
        "loaded_keys": sorted(values),
        "governed_keys": list(GOVERNED_PUBLISHER_SECRET_ENV_KEYS),
    }

def populate_process_env_from_canonical_secret_source(root: Path | None = None) -> dict:
    source = load_canonical_publisher_secret_source(root)
    imported_keys = []
    for key, value in source["values"].items():
        if not os.environ.get(key):
            os.environ[key] = value
            imported_keys.append(key)
    return {
        "authority": source["authority"],
        "path": source["path"],
        "loaded_keys": source["loaded_keys"],
        "imported_keys": imported_keys,
    }

def _validated_env_map_spec(root: Path | None = None) -> dict:
    env_map_file = _env_map_path(root)
    if not env_map_file.is_file():
        raise ConfigContractError(f"missing env map contract: {env_map_file}")
    try:
        spec = json.loads(env_map_file.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ConfigContractError(f"invalid env map JSON: {env_map_file}: {exc}") from exc
    if not isinstance(spec, dict):
        raise ConfigContractError(f"env map contract must be a JSON object: {env_map_file}")
    if str(spec.get("contract_id") or "").strip() != ENV_MAP_CONTRACT_ID:
        raise ConfigContractError(
            f"env map contract_id must be {ENV_MAP_CONTRACT_ID!r}: {env_map_file}"
        )
    if str(spec.get("schema_version") or "").strip() != ENV_MAP_SCHEMA_VERSION:
        raise ConfigContractError(
            f"env map schema_version must be {ENV_MAP_SCHEMA_VERSION!r}: {env_map_file}"
        )
    if "env_file_candidates" in spec:
        raise ConfigContractError(
            f"env map must not declare env_file_candidates; the secret source is governed separately: {env_map_file}"
        )
    key_map = spec.get("key_map")
    if not isinstance(key_map, dict):
        raise ConfigContractError(f"env map key_map must be a JSON object: {env_map_file}")
    for config_key, env_keys in key_map.items():
        if not isinstance(config_key, str) or not config_key.strip():
            raise ConfigContractError(f"env map key_map keys must be non-empty strings: {env_map_file}")
        if not isinstance(env_keys, list) or not env_keys:
            raise ConfigContractError(f"env map key_map values must be non-empty lists: {env_map_file}")
        if not all(isinstance(item, str) and item.strip() for item in env_keys):
            raise ConfigContractError(f"env map key_map lists must contain only strings: {env_map_file}")
    defaults = spec.get("defaults", {})
    if defaults not in ({}, None):
        raise ConfigContractError(
            f"env map defaults must be empty or omitted; non-secret defaults belong in tracked config: {env_map_file}"
        )
    return {
        **spec,
        "key_map": {str(key).strip(): [str(item).strip() for item in value] for key, value in key_map.items()},
        "defaults": {},
    }

def _apply_effective_config(
    cfg: dict,
    discovered: dict,
    process_env: dict[str, str],
    root: Path | None = None,
) -> dict:
    resolved = dict(cfg)
    for key, value in discovered.get("values", {}).items():
        if key.startswith("_"):
            continue
        if not resolved.get(key) or _is_placeholder(resolved.get(key)):
            resolved[key] = value
    for env_key, config_key in ENV_VAR_TO_CONFIG_KEY.items():
        env_value = process_env.get(env_key)
        if not env_value:
            continue
        if config_key == "media_public_base_url" and not _public_media_env_override_allowed(resolved.get(config_key, ""), env_value):
            continue
        resolved[config_key] = env_value
    if not resolved.get("media_public_local_dir") or _is_placeholder(resolved.get("media_public_local_dir")):
        resolved["media_public_local_dir"] = _default_media_public_local_dir(root)
        resolved["_media_public_local_dir_source"] = "runtime_default"
    if not resolved.get("r2_public_base_url") or _is_placeholder(resolved.get("r2_public_base_url")):
        resolved["r2_public_base_url"] = str(resolved.get("media_public_base_url") or "").strip()
    return resolved

def _load_env_for_r2(root: Path | None = None) -> None:
    """Best-effort: populate os.environ with governed canonical secret values."""
    populate_process_env_from_canonical_secret_source(root)


def _r2_secret_presence(root: Path | None = None) -> dict[str, bool]:
    _load_env_for_r2(root)
    return {key: bool(os.environ.get(key)) for key in R2_SECRET_ENV_KEYS}


def _r2_uploader_status() -> dict:
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        importlib.import_module("pipeline.media_host.r2_uploader")
        return {"available": True, "detail": ""}
    except Exception as exc:
        return {"available": False, "detail": str(exc)}


def resolve_media_host_route(cfg: dict, root: Path | None = None) -> dict:
    base_root = _resolve_root(root)
    host = classify_public_media_base_url(cfg)
    uploader = _r2_uploader_status()
    secret_presence = _r2_secret_presence(base_root)
    r2_public_base_url = str(cfg.get("r2_public_base_url") or cfg.get("media_public_base_url") or "").strip().rstrip("/")
    media_public_base_url = str(cfg.get("media_public_base_url") or "").strip().rstrip("/")
    nonsecret_values = {
        "r2_account_id": str(cfg.get("r2_account_id") or "").strip(),
        "r2_bucket_name": str(cfg.get("r2_bucket_name") or "").strip(),
        "r2_public_base_url": r2_public_base_url,
    }
    missing_nonsecret_keys = [key for key, value in nonsecret_values.items() if not value or _is_placeholder(value)]
    missing_secret_keys = [key for key, present in secret_presence.items() if not present]
    public_base_matches = bool(media_public_base_url) and media_public_base_url == r2_public_base_url

    reason = ""
    ok = False
    if not host["url"]:
        reason = "media_public_base_url_not_configured"
    elif host["requires_custom_domain"]:
        reason = "r2_production_custom_domain_required"
    elif not host["production_ready"]:
        reason = "public_media_base_url_not_production_ready"
    elif missing_nonsecret_keys:
        reason = "r2_nonsecret_config_incomplete"
    elif not public_base_matches:
        reason = "r2_public_base_url_mismatch"
    elif missing_secret_keys:
        reason = "r2_missing_required_secret_keys"
    elif not uploader["available"]:
        reason = "r2_uploader_unavailable"
    else:
        ok = True

    return {
        "ok": ok,
        "route": "r2" if ok else "not_ready",
        "reason": reason,
        "host": host,
        "uploader_available": uploader["available"],
        "uploader_detail": uploader["detail"],
        "missing_nonsecret_keys": missing_nonsecret_keys,
        "missing_secret_keys": missing_secret_keys,
        "r2_account_id": nonsecret_values["r2_account_id"],
        "r2_bucket_name": nonsecret_values["r2_bucket_name"],
        "r2_public_base_url": r2_public_base_url,
        "media_public_base_url": media_public_base_url,
        "public_base_matches": public_base_matches,
    }


def _r2_is_configured(root: Path | None = None) -> bool:
    cfg = load_config(root)
    return resolve_media_host_route(cfg, root).get("ok", False)


def _try_r2_upload(src: Path, key: str, cfg: dict, root: Path | None = None) -> dict | None:
    """Upload src to R2 at key; return r2_uploader result or None on any error."""
    route = resolve_media_host_route(cfg, root)
    if not route["ok"]:
        return None
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from pipeline.media_host.r2_uploader import upload_file_to_r2  # type: ignore
        return upload_file_to_r2(src, key, root=_resolve_root(root))
    except Exception:
        return None


def load_env_map(root: Path | None = None) -> dict:
    return _validated_env_map_spec(root)

def discover_dotenv_values(root: Path | None = None) -> dict:
    spec = load_env_map(root)
    source = load_canonical_publisher_secret_source(root)
    found = {}
    env_values = dict(source["values"])
    key_map = spec.get("key_map", {})
    for config_key, env_keys in key_map.items():
        for env_key in env_keys:
            if env_values.get(env_key):
                found[config_key] = env_values[env_key]
                found[f"_{config_key}_source"] = env_key
                break
    return {
        "values": found,
        "sources": [source["path"]],
        "env_map_path": str(_env_map_path(root)),
        "loaded_keys": source["loaded_keys"],
        "authority": source["authority"],
    }

def load_config(root: Path | None = None) -> dict:
    base_root = _resolve_root(root)
    cfg = _load_file_config_only(base_root)
    discovered = discover_dotenv_values(base_root)
    return _apply_effective_config(cfg, discovered, dict(os.environ), base_root)

def instagram_professional_account_id(cfg: dict) -> str:
    return str(cfg.get("instagram_professional_account_id") or "").strip()

def token_for_platform(cfg: dict, platform: str) -> str:
    if platform.startswith("Instagram"):
        return str(cfg.get("instagram_login_access_token") or "").strip()
    return cfg.get("page_access_token", "")

def config_status(test_api: bool = False, root: Path | None = None) -> dict:
    base_root = _resolve_root(root)
    env_map_ok = False
    env_map_error = ""
    secret_source_ok = False
    secret_source_error = ""
    secret_source_path = str(canonical_publisher_secret_source_path())
    discovered = {"values": {}, "sources": [], "env_map_path": str(_env_map_path(base_root))}
    try:
        load_env_map(base_root)
        env_map_ok = True
    except ConfigContractError as exc:
        env_map_error = str(exc)
    try:
        secret_source = load_canonical_publisher_secret_source(base_root)
        secret_source_ok = True
        secret_source_path = secret_source["path"]
    except ConfigContractError as exc:
        secret_source_error = str(exc)
    try:
        cfg = load_config(base_root)
        discovered = discover_dotenv_values(base_root)
    except ConfigContractError:
        cfg = _load_file_config_only(base_root)
        if not cfg.get("media_public_local_dir") or _is_placeholder(cfg.get("media_public_local_dir")):
            cfg["media_public_local_dir"] = _default_media_public_local_dir(base_root)
            cfg["_media_public_local_dir_source"] = "runtime_default"
    def check(key, secret=False):
        val = str(cfg.get(key, "") or "")
        placeholder = _is_placeholder(val)
        return {"ok": bool(val) and not placeholder, "value": redact(val) if secret else val}

    media_host_route = resolve_media_host_route(cfg, base_root) if secret_source_ok and env_map_ok else {
        "ok": False,
        "route": "not_ready",
        "reason": "publisher_contract_unavailable",
        "host": classify_public_media_base_url(cfg),
        "uploader_available": False,
        "uploader_detail": "",
        "missing_nonsecret_keys": list(R2_NONSECRET_CONFIG_KEYS),
        "missing_secret_keys": list(R2_SECRET_ENV_KEYS),
        "r2_account_id": str(cfg.get("r2_account_id") or ""),
        "r2_bucket_name": str(cfg.get("r2_bucket_name") or ""),
        "r2_public_base_url": str(cfg.get("r2_public_base_url") or cfg.get("media_public_base_url") or ""),
        "media_public_base_url": str(cfg.get("media_public_base_url") or ""),
        "public_base_matches": False,
    }
    r2_ok = media_host_route["ok"]
    mode     = _auth_mode(cfg)
    checks = {
        "instagram_login_access_token": check("instagram_login_access_token", True),
        "instagram_professional_account_id": check("instagram_professional_account_id", False),
        "instagram_access_token": check("instagram_access_token", True),
        "page_access_token": check("page_access_token", True),
        "instagram_business_account_id": check("instagram_business_account_id", False),
        "facebook_page_id": check("facebook_page_id", False),
        "graph_api_version": check("graph_api_version", False),
        "media_public_base_url": check("media_public_base_url", False),
        "media_public_local_dir": check("media_public_local_dir", False),
        "r2_configured": {"ok": r2_ok, "note": "R2 env vars present — R2 upload active" if r2_ok else "R2 env vars not set"},
        "local_config_exists": {"ok": _local_config_path(base_root).exists(), "path": str(_local_config_path(base_root))},
        "dotenv_sources": {
            "ok": secret_source_ok and bool(discovered.get("sources")),
            "sources": discovered.get("sources", []),
            "loaded_keys": discovered.get("loaded_keys", []),
            "authority": discovered.get("authority", ""),
        },
        "env_map_contract": {
            "ok": env_map_ok,
            "path": str(_env_map_path(base_root)),
            "contract_id": ENV_MAP_CONTRACT_ID,
            "schema_version": ENV_MAP_SCHEMA_VERSION,
            "detail": env_map_error,
        },
        "canonical_secret_source": {
            "ok": secret_source_ok,
            "path": secret_source_path,
            "authority": CANONICAL_PUBLISHER_SECRET_SOURCE_AUTHORITY,
            "governed_keys": list(GOVERNED_PUBLISHER_SECRET_ENV_KEYS),
            "loaded_keys": discovered.get("loaded_keys", []),
            "detail": secret_source_error,
        },
    }
    checks["media_public_base_url"]["ok"] = media_host_route["ok"]
    checks["r2_uploader_available"] = {
        "ok": bool(media_host_route["uploader_available"]),
        "detail": media_host_route["uploader_detail"],
    }
    checks["media_host_route"] = {
        "ok": media_host_route["ok"],
        "route": media_host_route["route"],
        "reason": media_host_route["reason"],
        "host_kind": media_host_route["host"]["host_kind"],
        "production_ready_host": media_host_route["host"]["production_ready"],
        "missing_nonsecret_keys": media_host_route["missing_nonsecret_keys"],
        "missing_secret_keys": media_host_route["missing_secret_keys"],
        "public_base_matches": media_host_route["public_base_matches"],
    }

    media_host_ok = r2_ok
    instagram_ready = checks["instagram_professional_account_id"]["ok"] and checks["instagram_login_access_token"]["ok"] and media_host_ok
    facebook_ready = False

    api_result = None
    if test_api:
        try:
            token = cfg.get("instagram_login_access_token")
            if token:
                api_result = graph_get("/me", {"fields": "id,user_id,username,account_type"}, cfg, token_override=token, platform="Instagram Feed")
            else:
                api_result = {"ok": False, "error": "no token available"}
        except Exception as e:
            api_result = {"ok": False, "error": sanitize_exception(e)}

    return {
        "ok": env_map_ok and secret_source_ok and (instagram_ready or facebook_ready),
        "version": "v2.9.1",
        "config_path": str(_local_config_path(base_root)),
        "checks": checks,
        "readiness": {
            "auth_mode":       mode,
            "graph_base_url":  graph_base(cfg),
            "instagram_ready": instagram_ready,
            "facebook_ready":  facebook_ready,
            "media_host_ready": media_host_ok,
            "media_host_method": media_host_route["route"] if media_host_route["ok"] else "not_ready",
        },
        "api_test": api_result
    }


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect rejected", headers, fp)


def verify_hosted_media_before_container(
    media_url: str,
    *,
    expected_sha256: str,
    expected_content_type: str,
    expected_content_length: int,
    max_download_seconds: float = 20.0,
) -> dict:
    parsed = urllib.parse.urlparse(str(media_url or ""))
    if parsed.scheme.lower() != "https":
        raise MediaHostVerificationError("hosted_media_url_must_be_https")
    if _public_host_kind(media_url) == "cloudflare_r2_development_host":
        raise MediaHostVerificationError("r2_production_custom_domain_required")

    req = urllib.request.Request(
        media_url,
        headers={"User-Agent": "LenaPublisher/2.9.1 media-host-verifier"},
        method="GET",
    )
    opener = urllib.request.build_opener(NoRedirectHandler)
    started = time.time()
    try:
        with opener.open(req, timeout=max_download_seconds) as resp:
            status = getattr(resp, "status", resp.getcode())
            final_url = resp.geturl()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise MediaHostVerificationError(f"hosted_media_http_error:{exc.code}") from exc
    except Exception as exc:
        raise MediaHostVerificationError(f"hosted_media_fetch_failed:{exc}") from exc

    elapsed = time.time() - started
    if status != 200:
        raise MediaHostVerificationError(f"hosted_media_status_not_200:{status}")
    if final_url != media_url:
        raise MediaHostVerificationError("hosted_media_redirect_not_allowed")
    if elapsed > max_download_seconds:
        raise MediaHostVerificationError("hosted_media_download_too_slow")

    content_type = str(headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type != expected_content_type:
        raise MediaHostVerificationError(f"hosted_media_content_type_invalid:{content_type}")
    content_length_raw = str(headers.get("content-length") or "").strip()
    if not content_length_raw:
        raise MediaHostVerificationError("hosted_media_content_length_missing_or_zero")
    try:
        content_length = int(content_length_raw)
    except ValueError as exc:
        raise MediaHostVerificationError("hosted_media_content_length_invalid") from exc
    if content_length <= 0 or content_length != expected_content_length or content_length != len(body):
        raise MediaHostVerificationError("hosted_media_content_length_mismatch")
    if not _matches_magic(body, expected_content_type):
        raise MediaHostVerificationError("hosted_media_magic_bytes_invalid")
    actual_sha = hashlib.sha256(body).hexdigest()
    if actual_sha != expected_sha256:
        raise MediaHostVerificationError("hosted_media_sha256_mismatch")
    return {
        "ok": True,
        "media_url": media_url,
        "status": status,
        "final_url": final_url,
        "content_type": content_type,
        "content_length": content_length,
        "sha256": actual_sha,
        "download_seconds": elapsed,
        "host_kind": _public_host_kind(media_url),
    }


def preflight_token(cfg: dict, platform: str = "") -> dict:
    """Validate token resolves cleanly before touching R2 or container APIs."""
    token = token_for_platform(cfg, platform)
    if not token:
        return {"ok": False, "reason": "no_token_in_config"}
    try:
        data = graph_get("/me", {"fields": "id,user_id,username,account_type"}, cfg,
                         token_override=token, platform=platform)
        if "error" in data:
            code = data["error"].get("code", 0)
            sub  = data["error"].get("error_subcode", 0)
            if code == 190:
                return {
                    "ok": False, "reason": "token_expired",
                    "code": code, "subcode": sub,
                }
            return {
                "ok": False, "reason": "token_invalid",
                "code": code, "subcode": sub,
            }
        return {"ok": True, "me_id": str(data.get("id") or data.get("user_id") or "")}
    except Exception as exc:
        detail = sanitize_exception(exc)
        if "190" in str(detail):
            return {"ok": False, "reason": "token_expired", "detail": detail}
        return {"ok": False, "reason": "preflight_error", "detail": detail}

def _graph_error_reason(data: dict, *, default: str = "instagram_api_error") -> str:
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return default
    code = int(error.get("code", 0) or 0)
    subcode = int(error.get("error_subcode", 0) or 0)
    if code == 190:
        return "instagram_token_expired" if subcode in {463, 467, 492} else "instagram_token_invalid"
    if code in {10, 200}:
        return "instagram_business_content_publish_scope_missing"
    return default

def _checked_graph_get(path: str, params: dict, cfg: dict, *, token: str, default_reason: str) -> tuple[dict | None, dict | None]:
    try:
        data = graph_get(path, params, cfg, token_override=token, platform="Instagram Feed")
    except Exception as exc:
        detail = sanitize_exception(exc)
        parsed = detail.get("response") if isinstance(detail, dict) else None
        if isinstance(parsed, dict):
            reason = _graph_error_reason(parsed, default=default_reason)
        else:
            reason = default_reason
        return None, {"ok": False, "reason": reason, "provider_error": detail}
    if isinstance(data, dict) and "error" in data:
        return None, {"ok": False, "reason": _graph_error_reason(data, default=default_reason), "provider_error": sanitize_provider_value(data)}
    return data, None

def validate_instagram_login_readiness(
    *,
    root: Path | None = None,
    platform: str = "Instagram Feed",
    media_type: str = "photo",
) -> dict:
    """Read-only pre-generation readiness for Instagram API with Instagram Login."""
    base_root = _resolve_root(root)
    status = config_status(False, root=base_root)
    checks = status.get("checks", {})
    if not checks.get("env_map_contract", {}).get("ok"):
        return {"ok": False, "reason": "credential_map_unavailable", "status": {"env_map_contract": checks.get("env_map_contract", {})}, "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}
    if not checks.get("canonical_secret_source", {}).get("ok"):
        return {"ok": False, "reason": "canonical_secret_source_unavailable", "status": {"canonical_secret_source": checks.get("canonical_secret_source", {})}, "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}
    try:
        cfg = load_config(base_root)
    except ConfigContractError as exc:
        return {"ok": False, "reason": "publisher_config_unavailable", "detail": str(exc), "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}

    route = resolve_media_host_route(cfg, base_root)
    if not route.get("ok"):
        return {
            "ok": False,
            "reason": "media_host_not_ready",
            "media_host_route": {
                "ok": False,
                "reason": route.get("reason", ""),
                "host_kind": route.get("host", {}).get("host_kind", ""),
                "missing_nonsecret_keys": route.get("missing_nonsecret_keys", []),
                "missing_secret_keys": route.get("missing_secret_keys", []),
            },
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "instagram_container_created": False,
        }

    token = token_for_platform(cfg, platform)
    if not token:
        return {"ok": False, "reason": "instagram_login_access_token_missing", "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}
    expected_id = instagram_professional_account_id(cfg)
    if not expected_id:
        return {"ok": False, "reason": "instagram_professional_account_id_missing", "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}

    me, failure = _checked_graph_get(
        "/me",
        {"fields": "id,user_id,username,account_type"},
        cfg,
        token=token,
        default_reason="instagram_token_invalid",
    )
    if failure:
        return {**failure, "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}
    resolved_id = str(me.get("id") or me.get("user_id") or "") if isinstance(me, dict) else ""
    if resolved_id != expected_id:
        return {
            "ok": False,
            "reason": "instagram_professional_account_mismatch",
            "expected_instagram_professional_account_id": expected_id,
            "resolved_instagram_professional_account_id": resolved_id,
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "instagram_container_created": False,
        }

    debug, failure = _checked_graph_get(
        "/debug_token",
        {"input_token": token},
        cfg,
        token=token,
        default_reason="instagram_scope_validation_failed",
    )
    if failure:
        return {**failure, "provider_calls_performed": 0, "publish_calls_performed": 0, "instagram_container_created": False}
    data = debug.get("data", debug) if isinstance(debug, dict) else {}
    raw_scopes = data.get("scopes", []) if isinstance(data, dict) else []
    if not raw_scopes and isinstance(data, dict):
        granular_scopes = data.get("granular_scopes", [])
        if isinstance(granular_scopes, list):
            raw_scopes = [
                item.get("scope") if isinstance(item, dict) else item
                for item in granular_scopes
            ]
    scopes = {str(scope) for scope in raw_scopes if scope}
    missing_scopes = sorted(REQUIRED_INSTAGRAM_LOGIN_SCOPES - scopes)
    if missing_scopes:
        return {
            "ok": False,
            "reason": "instagram_business_content_publish_scope_missing" if "instagram_business_content_publish" in missing_scopes else "instagram_business_basic_scope_missing",
            "missing_scopes": missing_scopes,
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "instagram_container_created": False,
        }
    expires_at = data.get("expires_at") or data.get("expires_in") or "unknown"
    return {
        "ok": True,
        "reason": "ready",
        "platform": platform,
        "media_type": media_type,
        "auth_mode": "instagram_login",
        "graph_base_url": graph_base(cfg, platform),
        "instagram_professional_account_id": expected_id,
        "instagram_username": str(me.get("username") or "") if isinstance(me, dict) else "",
        "account_type": str(me.get("account_type") or "") if isinstance(me, dict) else "",
        "required_scopes_present": sorted(REQUIRED_INSTAGRAM_LOGIN_SCOPES),
        "token_expiry": expires_at,
        "media_host_ready": True,
        "media_host_method": route.get("route", ""),
        "media_public_base_url": route.get("media_public_base_url", ""),
        "credential_map_resolved": True,
        "provider_calls_performed": 0,
        "publish_calls_performed": 0,
        "instagram_container_created": False,
    }

validate_pregeneration_publish_readiness = validate_instagram_login_readiness


def validate_config_for(platform: str, media_type: str, root: Path | None = None) -> dict:
    status = config_status(False, root=root)
    try:
        cfg = load_config(root)
    except ConfigContractError as exc:
        detail = str(exc)
        reason = "missing_canonical_publisher_secret_source" if "canonical publisher secret source" in detail else "invalid_env_map_contract"
        return {"ok": False, "reason": reason, "detail": detail, "status": status}
    if platform.startswith("Instagram"):
        if not instagram_professional_account_id(cfg):
            return {"ok": False, "reason": "missing_instagram_professional_account_id", "status": status}
        if not cfg.get("instagram_login_access_token"):
            return {"ok": False, "reason": "missing_instagram_login_access_token", "status": status}
    elif platform.startswith("Facebook"):
        if not cfg.get("facebook_page_id"):
            return {"ok": False, "reason": "missing_facebook_page_id", "status": status}
        if not cfg.get("page_access_token"):
            return {"ok": False, "reason": "missing_page_access_token", "status": status}
    else:
        return {"ok": False, "reason": "unsupported_meta_platform", "status": status}
    media_host_route = resolve_media_host_route(cfg, root)
    if not media_host_route["ok"]:
        return {"ok": False, "reason": media_host_route["reason"] or "media_host_not_ready", "status": status, "media_host_route": media_host_route}
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
    return "instagram_login" if cfg.get("instagram_login_access_token") else "facebook_login"


def graph_base(cfg: dict, platform: str = "") -> str:
    version = cfg.get("graph_api_version") or "v23.0"
    if platform.startswith("Instagram"):
        return f"https://graph.instagram.com/{version}"
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
    route = resolve_media_host_route(cfg, ROOT)
    if not route["ok"]:
        return {
            "ok": False,
            "reason": route["reason"] or "media_host_not_ready",
            "host": route["host"],
            "missing_nonsecret_keys": route["missing_nonsecret_keys"],
            "missing_secret_keys": route["missing_secret_keys"],
        }
    date_part = datetime.now().strftime("%Y-%m-%d")
    safe_platform = "".join(c if c.isalnum() else "_" for c in platform)
    dest_name = f"{queue_id}_{safe_platform}{src.suffix.lower()}"
    object_key = f"lena/{date_part}/{dest_name}"
    expected_sha256 = sha256_file(src)
    expected_content_type = _expected_content_type(src)
    expected_content_length = src.stat().st_size

    r2 = _try_r2_upload(src, object_key, cfg, ROOT)
    if r2 and r2.get("ok"):
        try:
            verification = verify_hosted_media_before_container(
                r2["public_url"],
                expected_sha256=expected_sha256,
                expected_content_type=expected_content_type,
                expected_content_length=expected_content_length,
            )
        except MediaHostVerificationError as exc:
            return {
                "ok": False,
                "reason": "pre_container_media_verification_failed",
                "detail": str(exc),
                "media_url": r2["public_url"],
                "upload_method": "r2",
                "r2_key": r2.get("key", object_key),
            }
        return {
            "ok": True,
            "local_path": str(src),
            "media_url": r2["public_url"],
            "upload_method": "r2",
            "r2_key": r2.get("key", object_key),
            "expected_sha256": expected_sha256,
            "pre_container_media_verification": verification,
        }

    return {
        "ok": False,
        "reason": "r2_upload_failed",
        "upload_method": "r2",
        "r2_key": object_key,
    }

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
        "reason": reason, "extra": sanitize_provider_value(extra or {})
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
