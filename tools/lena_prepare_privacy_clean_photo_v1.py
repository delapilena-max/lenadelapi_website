from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


SCHEMA_VERSION = "lena_privacy_clean_photo_v1"
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
PNG_FORBIDDEN_CHUNKS = {"tEXt", "zTXt", "iTXt", "eXIf"}
WEBP_FORBIDDEN_CHUNKS = {"EXIF", "XMP ", "ICCP"}
SUSPICIOUS_TERMS = (
    b"c2pa",
    b"xmp",
    b"iptc",
    b"credential",
    b"provenance",
    b"digitalsourcetype",
    b"trainedalgorithmicmedia",
    b"higgsfield",
    b"generativeai",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PrivacyCleanPhotoError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PrivacyCleanPhotoError("clean_export_report_exists", f"refusing to overwrite clean-export report: {path}")
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(raw)
    try:
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _png_chunks(data: bytes) -> list[str]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PrivacyCleanPhotoError("clean_export_format_invalid", "PNG signature is invalid")
    chunks: list[str] = []
    cursor = 8
    while cursor + 12 <= len(data):
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        end = cursor + 12 + length
        if end > len(data):
            raise PrivacyCleanPhotoError("clean_export_format_invalid", "PNG chunk extends past end of file")
        chunk_type = data[cursor + 4 : cursor + 8].decode("ascii", errors="replace")
        chunks.append(chunk_type)
        cursor = end
        if chunk_type == "IEND":
            break
    return chunks


def _png_chunk_records(data: bytes) -> list[tuple[str, bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PrivacyCleanPhotoError("clean_export_format_invalid", "PNG signature is invalid")
    chunks: list[tuple[str, bytes]] = []
    cursor = 8
    while cursor + 12 <= len(data):
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        end = cursor + 12 + length
        if end > len(data):
            raise PrivacyCleanPhotoError("clean_export_format_invalid", "PNG chunk extends past end of file")
        chunk_type = data[cursor + 4 : cursor + 8].decode("ascii", errors="replace")
        payload = data[cursor + 8 : cursor + 8 + length]
        chunks.append((chunk_type, payload))
        cursor = end
        if chunk_type == "IEND":
            break
    return chunks


def _webp_chunks(data: bytes) -> list[str]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise PrivacyCleanPhotoError("clean_export_format_invalid", "WEBP signature is invalid")
    chunks: list[str] = []
    cursor = 12
    while cursor + 8 <= len(data):
        chunk_type = data[cursor : cursor + 4].decode("ascii", errors="replace")
        length = struct.unpack("<I", data[cursor + 4 : cursor + 8])[0]
        chunks.append(chunk_type)
        cursor += 8 + length + (length % 2)
    return chunks


def inspect_embedded_metadata(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    lower = data.lower()
    extension = path.suffix.lower()
    forbidden_chunks: list[str] = []
    suspicious_scan = lower
    if extension == ".png":
        records = _png_chunk_records(data)
        forbidden_chunks = sorted({chunk_type for chunk_type, _ in records if chunk_type in PNG_FORBIDDEN_CHUNKS})
        # PNG image data lives in critical chunks such as IDAT. Scanning the
        # full compressed byte stream for ASCII metadata terms can false-positive
        # on ordinary pixel data, so restrict term checks to ancillary payloads.
        ancillary_payloads = [payload.lower() for chunk_type, payload in records if chunk_type and chunk_type[0].islower()]
        suspicious_scan = b"\n".join(ancillary_payloads)
    elif extension == ".webp":
        forbidden_chunks = sorted(set(_webp_chunks(data)) & WEBP_FORBIDDEN_CHUNKS)
    elif extension in {".jpg", ".jpeg"}:
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise PrivacyCleanPhotoError("clean_export_format_invalid", "JPEG markers are invalid")
        if b"exif\x00\x00" in lower or b"http://ns.adobe.com/xap/1.0/" in lower:
            forbidden_chunks.append("APP1_METADATA")
        if b"photoshop 3.0" in lower:
            forbidden_chunks.append("APP13_METADATA")
    else:
        raise PrivacyCleanPhotoError("clean_export_extension_unsupported", f"unsupported image extension: {extension}")
    with Image.open(path) as image:
        image.verify()
    suspicious_terms = [term.decode("ascii") for term in SUSPICIOUS_TERMS if term in suspicious_scan]
    return {
        "forbidden_metadata_chunks": forbidden_chunks,
        "suspicious_metadata_terms": suspicious_terms,
        "clean": not forbidden_chunks and not suspicious_terms,
    }


def prepare_privacy_clean_photo(
    source_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    source_image_sha256: str,
    lineage: dict[str, str],
) -> dict[str, Any]:
    source_path = source_path.resolve(strict=True)
    output_path = output_path.resolve()
    report_path = report_path.resolve()
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise PrivacyCleanPhotoError("clean_export_extension_unsupported", f"unsupported image extension: {source_path.suffix}")
    if output_path == source_path:
        raise PrivacyCleanPhotoError("clean_export_source_overwrite", "privacy-clean output must not overwrite the provider original")
    if output_path.exists() or report_path.exists():
        raise PrivacyCleanPhotoError("clean_export_output_exists", "privacy-clean output or report already exists")
    actual_source_sha = _sha256_file(source_path)
    if actual_source_sha != source_image_sha256:
        raise PrivacyCleanPhotoError("clean_export_source_sha_mismatch", "provider original SHA-256 does not match the bound generation result")
    required_lineage = {
        "candidate_artifact_sha256",
        "prompt_sha256",
        "packet_sha256",
        "handoff_sha256",
        "approval_sha256",
        "execution_receipt_sha256",
        "manifest_sha256",
        "qa_sha256",
    }
    if set(lineage) != required_lineage or any(not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in lineage.values()):
        raise PrivacyCleanPhotoError("clean_export_lineage_incomplete", "clean export requires the complete generation and QA SHA lineage")

    with Image.open(source_path) as source:
        source.load()
        source_size = source.size
        source_mode = source.mode
        pixels = source.copy()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.stem}.{os.getpid()}.tmp{output_path.suffix}")
    try:
        extension = output_path.suffix.lower()
        if extension == ".png":
            pixels.save(temp_path, format="PNG", optimize=False)
        elif extension in {".jpg", ".jpeg"}:
            if pixels.mode not in {"RGB", "L"}:
                pixels = pixels.convert("RGB")
            pixels.save(temp_path, format="JPEG", quality=95, optimize=False, progressive=False)
        elif extension == ".webp":
            pixels.save(temp_path, format="WEBP", quality=95, method=6)
        else:
            raise PrivacyCleanPhotoError("clean_export_extension_mismatch", "output extension is unsupported")
        if _sha256_file(source_path) != actual_source_sha:
            raise PrivacyCleanPhotoError("clean_export_source_changed", "provider original changed while the derivative was prepared")
        inspection = inspect_embedded_metadata(temp_path)
        if not inspection["clean"]:
            raise PrivacyCleanPhotoError("clean_export_verification_failed", "privacy-clean derivative still contains disallowed metadata")
        with Image.open(temp_path) as derivative:
            derivative.load()
            if derivative.size != source_size:
                raise PrivacyCleanPhotoError("clean_export_dimensions_changed", "privacy-clean derivative dimensions differ from the provider original")
        os.replace(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)

    output_sha = _sha256_file(output_path)
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_path": str(source_path),
        "source_sha256": actual_source_sha,
        "source_mode": source_mode,
        "source_dimensions": list(source_size),
        "output_path": str(output_path),
        "output_sha256": output_sha,
        "metadata_inspection": inspect_embedded_metadata(output_path),
        "verified_clean": True,
        "source_preserved": True,
        "lineage": dict(lineage),
    }
    _atomic_json(report_path, report)
    return {**report, "report_path": str(report_path), "report_sha256": _sha256_file(report_path)}


def validate_privacy_clean_report(report_path: Path, *, expected_output_path: Path | None = None) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrivacyCleanPhotoError("clean_export_report_invalid", f"privacy-clean report is invalid: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION or report.get("verified_clean") is not True:
        raise PrivacyCleanPhotoError("clean_export_report_invalid", "privacy-clean report contract is invalid")
    lineage = report.get("lineage")
    required_lineage = {
        "candidate_artifact_sha256", "prompt_sha256", "packet_sha256", "handoff_sha256",
        "approval_sha256", "execution_receipt_sha256", "manifest_sha256", "qa_sha256",
    }
    if not isinstance(lineage, dict) or set(lineage) != required_lineage or any(
        not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in lineage.values()
    ):
        raise PrivacyCleanPhotoError("clean_export_lineage_incomplete", "privacy-clean report lineage is incomplete or invalid")
    source_path = Path(str(report.get("source_path") or "")).resolve(strict=True)
    output_path = Path(str(report.get("output_path") or "")).resolve(strict=True)
    if expected_output_path is not None and output_path != expected_output_path.resolve():
        raise PrivacyCleanPhotoError("clean_export_output_path_mismatch", "privacy-clean report is bound to a different output path")
    if source_path == output_path:
        raise PrivacyCleanPhotoError("clean_export_source_overwrite", "privacy-clean report aliases the provider original")
    if _sha256_file(source_path) != report.get("source_sha256") or _sha256_file(output_path) != report.get("output_sha256"):
        raise PrivacyCleanPhotoError("clean_export_sha_mismatch", "privacy-clean report does not match current source/output bytes")
    inspection = inspect_embedded_metadata(output_path)
    if not inspection["clean"] or inspection != report.get("metadata_inspection"):
        raise PrivacyCleanPhotoError("clean_export_verification_failed", "privacy-clean derivative no longer matches its metadata inspection")
    return report
