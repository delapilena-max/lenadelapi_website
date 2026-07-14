from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import lena_photo_qa_disposition_v1 as disposition


AUTHORITY_PATH = ROOT / "pipeline/identity/lena_visual_model_authority_v1.json"
EXACT_AUTHORITY = {
    "schema_version": "lena_visual_model_authority_v1",
    "influencer_id": "lena",
    "authority_id": "lena_visual_model_authority_v1",
    "provider": "anthropic",
    "approved_model": "claude-sonnet-5",
}


def _authority_bytes(value: dict | None = None) -> bytes:
    return json.dumps(value or EXACT_AUTHORITY, indent=2).encode() + b"\n"


def _validate_bytes(tmp_path: Path, monkeypatch, committed: bytes, *, sha: str | None = None, commit: str = "a" * 40):
    path = tmp_path / "authority.json"
    path.write_bytes(committed)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda requested_commit, requested_path: committed)
    return disposition._validate_model_authority(
        path, sha or hashlib.sha256(committed).hexdigest(), commit, "anthropic", "claude-sonnet-5",
    )


def test_exact_five_key_authority_artifact() -> None:
    assert json.loads(AUTHORITY_PATH.read_text(encoding="utf-8")) == EXACT_AUTHORITY
    assert set(EXACT_AUTHORITY) == disposition.MODEL_AUTHORITY_KEYS


def test_exact_committed_authority_and_sha_pass(tmp_path, monkeypatch) -> None:
    committed = AUTHORITY_PATH.read_bytes()
    seen = []
    path = tmp_path / "authority.json"
    path.write_bytes(committed)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda commit, artifact: seen.append((commit, artifact)) or committed)
    result = disposition._validate_model_authority(
        path, hashlib.sha256(committed).hexdigest(), "b" * 40, "anthropic", "claude-sonnet-5",
    )
    assert seen == [("b" * 40, path)]
    assert result["approved_model"] == "claude-sonnet-5"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "wrong"), ("influencer_id", "other"), ("authority_id", "wrong"),
        ("provider", "other"), ("approved_model", "claude-opus-4-8"),
    ],
)
def test_wrong_required_value_rejects(tmp_path, monkeypatch, field, value) -> None:
    changed = dict(EXACT_AUTHORITY)
    changed[field] = value
    with pytest.raises(disposition.BoundaryError):
        _validate_bytes(tmp_path, monkeypatch, _authority_bytes(changed))


@pytest.mark.parametrize("field", list(EXACT_AUTHORITY))
def test_missing_field_rejects(tmp_path, monkeypatch, field) -> None:
    changed = dict(EXACT_AUTHORITY)
    changed.pop(field)
    with pytest.raises(disposition.BoundaryError):
        _validate_bytes(tmp_path, monkeypatch, _authority_bytes(changed))


@pytest.mark.parametrize("extra", ["created_at_utc", "authority_commit", "retry_policy"])
def test_extra_field_rejects(tmp_path, monkeypatch, extra) -> None:
    changed = dict(EXACT_AUTHORITY)
    changed[extra] = "forbidden"
    with pytest.raises(disposition.BoundaryError, match="exact schema"):
        _validate_bytes(tmp_path, monkeypatch, _authority_bytes(changed))


@pytest.mark.parametrize("committed", [b"{", b"[]", b'{"schema_version":"x","schema_version":"y"}'])
def test_malformed_non_object_and_duplicate_json_reject(tmp_path, monkeypatch, committed) -> None:
    with pytest.raises(disposition.BoundaryError):
        _validate_bytes(tmp_path, monkeypatch, committed)


def test_wrong_sha_rejects(tmp_path, monkeypatch) -> None:
    with pytest.raises(disposition.BoundaryError, match="SHA-256"):
        _validate_bytes(tmp_path, monkeypatch, _authority_bytes(), sha="0" * 64)


def test_missing_untracked_or_wrong_commit_rejects(tmp_path, monkeypatch) -> None:
    path = tmp_path / "authority.json"
    path.write_bytes(_authority_bytes())
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: (_ for _ in ()).throw(
        disposition.BoundaryError("identity_evidence_invalid", "not committed at externally bound commit")
    ))
    with pytest.raises(disposition.BoundaryError, match="not committed"):
        disposition._validate_model_authority(path, "0" * 64, "c" * 40, "anthropic", "claude-sonnet-5")


def test_dirty_modified_authority_rejects(tmp_path, monkeypatch) -> None:
    committed = _authority_bytes()
    path = tmp_path / "authority.json"
    path.write_bytes(committed + b" ")
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: committed)
    with pytest.raises(disposition.BoundaryError, match="differs from committed"):
        disposition._validate_model_authority(
            path, hashlib.sha256(committed).hexdigest(), "d" * 40, "anthropic", "claude-sonnet-5",
        )


def test_arbitrary_outside_repository_path_rejects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(disposition, "ROOT", tmp_path / "repo")
    path = tmp_path / "outside.json"
    path.write_bytes(_authority_bytes())
    with pytest.raises(disposition.BoundaryError, match="inside the repository"):
        disposition._validate_model_authority(
            path, hashlib.sha256(path.read_bytes()).hexdigest(), "e" * 40, "anthropic", "claude-sonnet-5",
        )


@pytest.mark.parametrize(
    "model",
    ["sonnet", "latest", "default", "claude-sonnet-latest", "claude-opus-4-8", "claude-haiku-4-5-20251001", "claude-fable-5"],
)
def test_aliases_and_alternate_models_reject(tmp_path, monkeypatch, model) -> None:
    committed = _authority_bytes()
    path = tmp_path / "authority.json"
    path.write_bytes(committed)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: committed)
    with pytest.raises(disposition.BoundaryError, match="exactly match"):
        disposition._validate_model_authority(
            path, hashlib.sha256(committed).hexdigest(), "f" * 40, "anthropic", model,
        )


def test_alternate_provider_rejects(tmp_path, monkeypatch) -> None:
    committed = _authority_bytes()
    path = tmp_path / "authority.json"
    path.write_bytes(committed)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: committed)
    with pytest.raises(disposition.BoundaryError, match="anthropic"):
        disposition._validate_model_authority(
            path, hashlib.sha256(committed).hexdigest(), "f" * 40, "other", "claude-sonnet-5",
        )
