"""
nodes/tts_guard.py

Small utility to:
- Count characters for a text payload.
- Maintain a simple monthly quota counter (file-backed).
- Cache generated voice files by text hash to avoid duplicate Azure calls.
- Refuse synthesis when the monthly quota would be exceeded.
"""

from __future__ import annotations
from pathlib import Path
import hashlib
import yaml
import datetime
import logging

logger = logging.getLogger(__name__)

class TTSGuard:
    def __init__(self,
                 quota_per_month: int = 500_000,
                 counter_file: str | Path = "data/tts_counter.yaml",
                 cache_dir: str | Path = "assets/audio/cache"):
        self.quota_per_month = int(quota_per_month)
        self.counter_file = Path(counter_file)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._data = self._load_counter()

    def _load_counter(self) -> dict:
        if not self.counter_file.exists():
            return {"month": self._current_month_str(), "used": 0}
        try:
            with self.counter_file.open("r", encoding="utf8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            logger.exception("Failed to read TTS counter file; resetting.")
            data = {}
        if data.get("month") != self._current_month_str():
            data = {"month": self._current_month_str(), "used": 0}
            self._save_counter(data)
        return {"month": data.get("month", self._current_month_str()), "used": int(data.get("used", 0))}

    def _save_counter(self, data: dict | None = None) -> None:
        d = data if data is not None else self._data
        self.counter_file.parent.mkdir(parents=True, exist_ok=True)
        with self.counter_file.open("w", encoding="utf8") as f:
            yaml.safe_dump(d, f)

    def _current_month_str(self) -> str:
        now = datetime.datetime.utcnow()
        return f"{now.year:04d}-{now.month:02d}"

    def chars_in_text(self, text: str) -> int:
        return len(text or "")

    def _hash_text(self, text: str) -> str:
        h = hashlib.sha1(text.encode("utf8")).hexdigest()
        return h

    def cache_path_for(self, text: str) -> Path:
        return self.cache_dir / f"voice-{self._hash_text(text)}.mp3"

    def is_cached(self, text: str) -> bool:
        return self.cache_path_for(text).exists()

    def request_synthesis(self, text: str) -> tuple[bool, str]:
        if not text or not text.strip():
            return False, "empty_text"

        if self._data.get("month") != self._current_month_str():
            self._data = {"month": self._current_month_str(), "used": 0}
            self._save_counter(self._data)

        if self.is_cached(text):
            return True, "cached"

        chars = self.chars_in_text(text)
        projected = self._data["used"] + chars
        if projected > self.quota_per_month:
            return False, f"quota_exceeded ({self._data['used']}/{self.quota_per_month} used, +{chars} would exceed)"
        self._data["used"] = projected
        self._save_counter(self._data)
        return True, "ok"

    def record_synthesis_failure(self, text: str) -> None:
        chars = self.chars_in_text(text)
        self._data["used"] = max(0, self._data.get("used", 0) - chars)
        self._save_counter(self._data)

    def reset_monthly_counter(self) -> None:
        self._data = {"month": self._current_month_str(), "used": 0}
        self._save_counter(self._data)

    def get_usage(self) -> dict:
        return {"month": self._data.get("month"), "used": int(self._data.get("used", 0)), "quota": int(self.quota_per_month)}
