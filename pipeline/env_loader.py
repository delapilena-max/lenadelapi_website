from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


_LOADED = False


def _candidate_paths(root: Path | None = None) -> Iterable[Path]:
    base = root or Path.cwd()
    yield base / ".env"
    yield base / ".env.local"
    yield base / ".env.disabled"
    yield base / "pipeline" / "config" / ".env"


def load_env(root: Path | None = None, override: bool = False) -> dict:
    """
    Lightweight dotenv loader for local pipeline runtime.

    - Does not print secret values.
    - Does not require python-dotenv.
    - Loads .env, .env.local, .env.disabled, or pipeline/config/.env.
    - Existing environment variables win unless override=True.
    """
    global _LOADED

    loaded = {}

    for env_path in _candidate_paths(root):
        if not env_path.exists():
            continue

        for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()

            if not line:
                continue
            if line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if not key:
                continue

            if override or key not in os.environ:
                os.environ[key] = value
                loaded[key] = env_path.name

        _LOADED = True

    return loaded


def load_env_once(root: Path | None = None, override: bool = False) -> dict:
    global _LOADED

    if _LOADED:
        return {}

    return load_env(root=root, override=override)


def require_env(*names: str) -> None:
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise EnvironmentError(
            "Missing required environment variables: " + ", ".join(missing)
        )
