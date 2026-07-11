from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = ROOT / "pipeline"
DEFAULT_CONFIG_PATH = PIPELINE_DIR / "config" / "posting_config.json"
CLASSIFICATIONS = (
    "claimed_pre_unlink_duplicate",
    "claimed_no_local_publish_evidence",
    "published_locally_confirmed",
    "published_move_without_receipt",
    "failed_local_record_external_state_unknown",
    "manual_review_required",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def _resolve_under_pipeline(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path.resolve()
    return (PIPELINE_DIR / path).resolve()


def _load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG_PATH
    payload = _read_json(cfg_path, {})
    return payload if isinstance(payload, dict) else {}


def _first_non_empty(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _extract_post_id(data: Dict[str, Any], post_file: Path) -> str:
    for key in ("post_id", "id", "episode_id", "content_id", "request_id", "slug"):
        value = data.get(key)
        if value:
            return str(value)
    return post_file.stem


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _age_seconds(path: Path) -> float:
    return max(0.0, datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)


def _normalize_success_receipt(payload: Dict[str, Any]) -> bool:
    publish_response = payload.get("publish_response")
    if not isinstance(publish_response, dict):
        return False
    if publish_response.get("ok") is not True:
        return False
    if str(publish_response.get("backend") or "").strip().lower() in {"local", "noop", "receipt"}:
        return False

    direct_media_id = _first_non_empty(payload.get("instagram_media_id"))
    if direct_media_id:
        return True

    result = publish_response.get("result")
    if not isinstance(result, dict):
        return False
    instagram_result = result.get("instagram_result")
    if not isinstance(instagram_result, dict):
        return False
    if _first_non_empty(instagram_result.get("instagram_media_id")):
        return True
    published_response = instagram_result.get("published_response")
    if isinstance(published_response, dict) and _first_non_empty(published_response.get("id")):
        return True
    return False


@dataclass
class InFlightClaimInspector:
    queue_dir: Path
    in_flight_dir: Path
    published_dir: Path
    failed_dir: Path

    @classmethod
    def from_root(cls, root: Optional[Path] = None, config: Optional[Dict[str, Any]] = None) -> "InFlightClaimInspector":
        repo_root = (root or ROOT).resolve()
        pipeline_dir = repo_root / "pipeline"
        cfg = dict(config or _load_config(pipeline_dir / "config" / "posting_config.json"))

        def _resolve(path_value: str, default_value: str) -> Path:
            raw = str(cfg.get(path_value, default_value))
            candidate = Path(raw)
            if candidate.is_absolute():
                return candidate.resolve()
            return (pipeline_dir / candidate).resolve()

        queue_dir = _resolve("queue_dir", "queue")
        return cls(
            queue_dir=queue_dir,
            in_flight_dir=_resolve("in_flight_dir", "queue/in_flight"),
            published_dir=_resolve("published_dir", "queue/published"),
            failed_dir=_resolve("failed_dir", "queue/failed"),
        )

    def _matching_identifiers(self, in_flight_path: Path, payload: Dict[str, Any]) -> List[str]:
        identifiers: List[str] = []
        for candidate in (
            in_flight_path.stem,
            _extract_post_id(payload, in_flight_path),
            str(payload.get("slot_id") or "").strip() or None,
        ):
            if candidate and candidate not in identifiers:
                identifiers.append(candidate)
        return identifiers

    def _existing_paths(self, directory: Path, patterns: Iterable[str]) -> List[Path]:
        seen: set[str] = set()
        matches: List[Path] = []
        for pattern in patterns:
            for path in sorted(directory.glob(pattern)):
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                matches.append(path.resolve())
        return matches

    def _matching_live_queue_paths(self, identifiers: Iterable[str]) -> List[Path]:
        return self._existing_paths(self.queue_dir, [f"{identifier}.json" for identifier in identifiers])

    def _matching_published_paths(self, identifiers: Iterable[str]) -> List[Path]:
        return self._existing_paths(self.published_dir, [f"{identifier}.json" for identifier in identifiers])

    def _matching_failed_paths(self, identifiers: Iterable[str]) -> List[Path]:
        return self._existing_paths(self.failed_dir, [f"{identifier}*.json" for identifier in identifiers])

    def _receipt_payload_for_published(self, published_path: Path) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
        receipt_path = published_path.with_suffix(published_path.suffix + ".receipt.json")
        if not receipt_path.exists():
            return None, None
        payload = _read_json(receipt_path, {})
        if not isinstance(payload, dict):
            return receipt_path.resolve(), None
        return receipt_path.resolve(), payload

    def _classify(self, in_flight_path: Path) -> Dict[str, Any]:
        payload = _read_json(in_flight_path, {})
        if not isinstance(payload, dict):
            payload = {}

        identifiers = self._matching_identifiers(in_flight_path, payload)
        live_queue_paths = self._matching_live_queue_paths(identifiers)
        published_paths = self._matching_published_paths(identifiers)
        failed_paths = self._matching_failed_paths(identifiers)

        adjacent_receipts: List[Dict[str, Any]] = []
        for published_path in published_paths:
            receipt_path, receipt_payload = self._receipt_payload_for_published(published_path)
            if receipt_path is not None:
                adjacent_receipts.append(
                    {
                        "path": str(receipt_path),
                        "payload": receipt_payload,
                        "successful_publish_evidence": bool(isinstance(receipt_payload, dict) and _normalize_success_receipt(receipt_payload)),
                    }
                )

        successful_receipts = [item for item in adjacent_receipts if item["successful_publish_evidence"]]
        has_published = bool(published_paths)
        has_receipt = bool(adjacent_receipts)
        has_failed = bool(failed_paths)
        has_live_queue = bool(live_queue_paths)

        conflicting = (
            len(published_paths) > 1
            or len(failed_paths) > 1
            or (has_receipt and not has_published)
            or (has_published and has_failed)
            or any(item["payload"] is None for item in adjacent_receipts)
        )

        if conflicting:
            classification = "manual_review_required"
        elif has_published and successful_receipts:
            classification = "published_locally_confirmed"
        elif has_published and not has_receipt:
            classification = "published_move_without_receipt"
        elif has_failed and not successful_receipts:
            classification = "failed_local_record_external_state_unknown"
        elif has_live_queue and not successful_receipts:
            classification = "claimed_pre_unlink_duplicate"
        elif not has_published and not successful_receipts and not has_failed:
            classification = "claimed_no_local_publish_evidence"
        else:
            classification = "manual_review_required"

        if classification not in CLASSIFICATIONS:
            raise ValueError(f"unexpected classification: {classification}")

        return {
            "classification": classification,
            "post_id": _extract_post_id(payload, in_flight_path),
            "slot_id": _first_non_empty(str(payload.get("slot_id") or "").strip() or None),
            "queue_filename_stem": in_flight_path.stem,
            "in_flight_path": str(in_flight_path.resolve()),
            "in_flight_mtime_utc": _iso_from_mtime(in_flight_path),
            "in_flight_age_seconds": _age_seconds(in_flight_path),
            "evidence": {
                "live_queue_paths": [str(path) for path in live_queue_paths],
                "published_paths": [str(path) for path in published_paths],
                "published_receipts": adjacent_receipts,
                "failed_paths": [str(path) for path in failed_paths],
            },
        }

    def inspect(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        if self.in_flight_dir.exists():
            for path in sorted(self.in_flight_dir.glob("*.json")):
                items.append(self._classify(path.resolve()))

        counts: Dict[str, int] = {name: 0 for name in CLASSIFICATIONS}
        for item in items:
            counts[item["classification"]] += 1

        return {
            "ok": True,
            "timestamp_utc": _utc_now(),
            "directories": {
                "queue_dir": str(self.queue_dir),
                "in_flight_dir": str(self.in_flight_dir),
                "published_dir": str(self.published_dir),
                "failed_dir": str(self.failed_dir),
            },
            "counts": counts,
            "items": items,
        }


def inspect_in_flight_publish_claims(root: Optional[Path] = None, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return InFlightClaimInspector.from_root(root=root, config=config).inspect()


if __name__ == "__main__":
    result = inspect_in_flight_publish_claims()
    print(json.dumps(result, ensure_ascii=False, indent=2))
