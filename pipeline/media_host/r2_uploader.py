from __future__ import annotations

import mimetypes
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().strip('"').strip("'")


def _require_value(name: str, value: Optional[str]) -> str:
    cleaned = _clean(value)
    if not cleaned:
        raise RuntimeError(f"Missing required R2 setting: {name}")
    return cleaned


def load_r2_config(root: Path | None = None) -> dict:
    from tools.publishers import lena_meta_publish_common_v2_9 as publish_common

    base_root = publish_common._resolve_root(root)
    publish_common.populate_process_env_from_canonical_secret_source(base_root)
    cfg = publish_common.load_config(base_root)

    account_id = _require_value("r2_account_id", cfg.get("r2_account_id") or os.environ.get("R2_ACCOUNT_ID"))
    bucket = _require_value("r2_bucket_name", cfg.get("r2_bucket_name") or os.environ.get("R2_BUCKET_NAME"))
    access_key = _require_value("R2_ACCESS_KEY_ID", os.environ.get("R2_ACCESS_KEY_ID"))
    secret_key = _require_value("R2_SECRET_ACCESS_KEY", os.environ.get("R2_SECRET_ACCESS_KEY"))
    public_base_url = _require_value(
        "r2_public_base_url",
        cfg.get("r2_public_base_url") or cfg.get("media_public_base_url") or os.environ.get("R2_PUBLIC_BASE_URL"),
    ).rstrip("/")
    region = _clean(os.environ.get("R2_REGION")) or "auto"

    return {
        "account_id": account_id,
        "bucket": bucket,
        "access_key": access_key,
        "secret_key": secret_key,
        "public_base_url": public_base_url,
        "region": region,
        "endpoint_url": f"https://{account_id}.r2.cloudflarestorage.com",
    }


def make_r2_client(root: Path | None = None):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("boto3_not_installed") from exc

    cfg = load_r2_config(root)
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name=cfg["region"],
        config=Config(signature_version="s3v4"),
    )


def upload_file_to_r2(local_path: str | Path, key: str, *, root: Path | None = None) -> dict:
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    normalized_key = key.replace("\\", "/").lstrip("/")
    cfg = load_r2_config(root)
    client = make_r2_client(root)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    with path.open("rb") as handle:
        client.upload_fileobj(
            handle,
            cfg["bucket"],
            normalized_key,
            ExtraArgs={"ContentType": content_type},
        )

    encoded_key = urllib.parse.quote(normalized_key, safe="/-_.~")
    public_url = f"{cfg['public_base_url']}/{encoded_key}"
    return {
        "ok": True,
        "bucket": cfg["bucket"],
        "key": normalized_key,
        "local_path": str(path),
        "content_type": content_type,
        "public_url": public_url,
        "endpoint_url": cfg["endpoint_url"],
    }
