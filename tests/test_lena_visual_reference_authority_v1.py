from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from tools import lena_photo_qa_disposition_v1 as disposition
from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "pipeline/identity/lena_visual_reference_authority_v1.json"
REFERENCE_PATH = ROOT / "pipeline/higgsfield_library/lena/2026-07-09/prompt_isolation_tests/readypack0709-pack004-08-wardrobe-test-c_seed.png"
MANIFEST_PATH = ROOT / "pipeline/higgsfield_debug/2026-07-09/prompt_isolation_tests/readypack0709-pack004-08-wardrobe-test-c/result_manifest.json"
REFERENCE_SHA = "7649a7ab360832390eac0e5f06ed7bb4f21d941f31e57201ef6721c00a313ffb"
MANIFEST_BLOB_SHA = "25c1635ff4504fe5e3c58420fcc15fb19aa1a4943d0fc841f332b6208d445b00"
MANIFEST_LOCAL_SHA = "d8db9d4783ef14b41af23d2d75494e627dd26680831ec51ec82b6346eb3dfd8e"
MANIFEST_BLOB_OID = "616f2d524153abbd3bb73fdcaf29530af83c0334"
SET_SHA = "f75b124c7738ee858375bfd45bd46ad5427e29b0e10ac819f289af648627b3d8"
REFERENCE_COMMIT = "2dd04f2b1c187af47ad29e4bd816752e04dcba7d"
CURRENT_SOUL = "90a293d7-f3af-4377-8751-3304a27b6f31"
WRONG_SOUL = "90a293d7-f3af-4377-8751-3304b687e3c1"
STALE_SOUL = "1f1200e4-1cc9-4504-ac1c-3304b687e3c1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def authority() -> dict:
    return json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))


def test_exact_authority_contract(authority) -> None:
    assert authority["schema_version"] == disposition.REFERENCE_AUTHORITY_SCHEMA_VERSION
    assert authority["influencer_id"] == "lena"
    assert authority["authority_id"] == "lena_visual_reference_authority_v1"
    assert authority["authority_commit"] == REFERENCE_COMMIT
    assert authority["references"] == [{"path": REFERENCE_PATH.relative_to(ROOT).as_posix(), "sha256": REFERENCE_SHA}]
    assert authority["reference_set_sha256"] == SET_SHA


def test_reference_bytes_dimensions_and_format_are_exact(authority) -> None:
    assert _sha(REFERENCE_PATH) == REFERENCE_SHA
    with Image.open(REFERENCE_PATH) as image:
        assert image.size == (1152, 2048)
        assert image.format == "PNG"
    metadata = authority["reference_metadata"][0]
    assert (metadata["width"], metadata["height"], metadata["format"]) == (1152, 2048, "PNG")


def test_current_identity_and_provider_provenance_are_exact(authority) -> None:
    metadata = authority["reference_metadata"][0]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert _sha(MANIFEST_PATH) == MANIFEST_LOCAL_SHA
    assert metadata["provenance_manifest_sha256"] == MANIFEST_BLOB_SHA
    assert metadata["provenance_manifest_git_blob_oid"] == MANIFEST_BLOB_OID
    assert metadata["provenance_manifest"] == MANIFEST_PATH.relative_to(ROOT).as_posix()
    assert metadata["custom_reference_id"] == manifest["custom_reference_id"] == CURRENT_SOUL
    assert WRONG_SOUL not in json.dumps(authority)
    assert STALE_SOUL not in json.dumps(authority)
    assert metadata["provider_job_id"] == manifest["provider_job_id"] == "ada3a4da-84ba-4f59-adce-0b31f51706a3"
    assert manifest["provider_status"] == "completed"
    assert manifest["output_sha256"] == REFERENCE_SHA


def test_identity_scope_does_not_authorize_style(authority) -> None:
    metadata = authority["reference_metadata"][0]
    assert metadata["authority_scope"] == "identity_continuity_not_style"
    assert set(metadata["non_authoritative_traits"]) == {
        "night_lighting", "makeup", "wardrobe", "pose", "scene", "background", "glamour_intensity",
    }


def test_reference_set_sha_uses_production_canonical_encoding(authority) -> None:
    value = {"authority_id": authority["authority_id"], "references": authority["references"]}
    assert hashlib.sha256(selector._canonical_bytes(value)).hexdigest() == SET_SHA


def test_png_exists_as_exact_raw_commit_bytes() -> None:
    relative = REFERENCE_PATH.relative_to(ROOT).as_posix()
    committed = subprocess.run(
        ["git", "show", f"{REFERENCE_COMMIT}:{relative}"], cwd=ROOT, check=True, capture_output=True,
    ).stdout
    assert hashlib.sha256(committed).hexdigest() == REFERENCE_SHA
    assert committed == REFERENCE_PATH.read_bytes()


def test_manifest_uses_exact_committed_blob_and_git_clean_checkout_equivalence() -> None:
    committed = disposition._git_show_bytes(REFERENCE_COMMIT, MANIFEST_PATH)
    assert hashlib.sha256(committed).hexdigest() == MANIFEST_BLOB_SHA
    assert disposition._git_blob_oid(REFERENCE_COMMIT, MANIFEST_PATH) == MANIFEST_BLOB_OID
    disposition._require_crlf_lf_equivalent(MANIFEST_PATH, committed)
    assert hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest() == MANIFEST_LOCAL_SHA


def test_reference_commit_is_real_and_ancestor_of_head() -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", REFERENCE_COMMIT, "HEAD"], cwd=ROOT, check=False,
    )
    assert result.returncode == 0


def test_corrected_two_commit_validator_accepts_exact_contract(authority, monkeypatch) -> None:
    authority_bytes = AUTHORITY_PATH.read_bytes()
    consumer = "f" * 40
    original_show = disposition._git_show_bytes

    def git_show(commit: str, path: Path) -> bytes:
        if path.resolve() == AUTHORITY_PATH.resolve():
            assert commit == consumer
            return authority_bytes
        return original_show(commit, path)

    monkeypatch.setattr(disposition, "_git_show_bytes", git_show)
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda ancestor, descendant: (ancestor, descendant) == (REFERENCE_COMMIT, consumer))
    refs, set_sha, provenance = disposition._validate_references(
        [(REFERENCE_PATH, REFERENCE_SHA)], AUTHORITY_PATH, hashlib.sha256(authority_bytes).hexdigest(), consumer,
    )
    assert refs[0]["sha256"] == REFERENCE_SHA
    assert set_sha == SET_SHA
    assert provenance["authority_commit"] == REFERENCE_COMMIT
    assert provenance["authority_artifact_commit"] == consumer


def test_non_ancestor_reference_commit_rejects(authority, monkeypatch) -> None:
    authority_bytes = AUTHORITY_PATH.read_bytes()
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda commit, path: authority_bytes)
    monkeypatch.setattr(disposition, "_require_crlf_lf_equivalent", lambda *args: None)
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda *args: False)
    with pytest.raises(disposition.BoundaryError, match="ancestor"):
        disposition._validate_references(
            [(REFERENCE_PATH, REFERENCE_SHA)], AUTHORITY_PATH, hashlib.sha256(authority_bytes).hexdigest(), "f" * 40,
        )


def test_missing_reference_commit_bytes_rejects(monkeypatch) -> None:
    authority_bytes = AUTHORITY_PATH.read_bytes()
    monkeypatch.setattr(disposition, "_git_is_ancestor", lambda *args: True)
    monkeypatch.setattr(disposition, "_require_crlf_lf_equivalent", lambda *args: None)
    monkeypatch.setattr(
        disposition, "_git_show_bytes",
        lambda commit, path: authority_bytes if path.resolve() == AUTHORITY_PATH.resolve() else (_ for _ in ()).throw(
            disposition.BoundaryError("identity_evidence_invalid", "not committed")
        ),
    )
    with pytest.raises(disposition.BoundaryError, match="not committed"):
        disposition._validate_references(
            [(REFERENCE_PATH, REFERENCE_SHA)], AUTHORITY_PATH, hashlib.sha256(authority_bytes).hexdigest(), "f" * 40,
        )


def test_dirty_authority_artifact_rejects(tmp_path, monkeypatch) -> None:
    local = tmp_path / "authority.json"
    local.write_bytes(b"dirty")
    committed = AUTHORITY_PATH.read_bytes()
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: committed)
    monkeypatch.setattr(disposition, "_require_crlf_lf_equivalent", lambda *args: (_ for _ in ()).throw(
        disposition.BoundaryError("identity_evidence_invalid", "local authority input differs")
    ))
    with pytest.raises(disposition.BoundaryError, match="local authority input differs"):
        disposition._committed_json_authority(
            local, hashlib.sha256(committed).hexdigest(), "f" * 40,
            disposition.REFERENCE_AUTHORITY_SCHEMA_VERSION, require_self_commit=False,
        )


@pytest.mark.parametrize("local", [b'{\n  "value": 1\n}\n', b'{\r\n  "value": 1\r\n}\r\n'])
def test_manifest_accepts_only_lf_or_crlf_checkout_equivalence(tmp_path, local) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(local)
    disposition._require_crlf_lf_equivalent(path, b'{\n  "value": 1\n}\n')


@pytest.mark.parametrize(
    "local",
    [
        b'{"uuid":"changed"}\n',
        b'{ "value": 1}\n',
        b'{"value": 1 }\n',
        b'{"value": 1}\t\n',
        b'{"added":true,"value":1}\n',
        b'{"b":2,"a":1}\n',
    ],
)
def test_manifest_rejects_every_non_line_ending_byte_change(tmp_path, local) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(local)
    with pytest.raises(disposition.BoundaryError, match="differs from committed content"):
        disposition._require_crlf_lf_equivalent(path, b'{"value":1}\n')


def test_mutable_git_filter_state_cannot_affect_manifest_qualification(tmp_path, monkeypatch) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b'{\r\n  "value": 1\r\n}\r\n')

    def hostile_git(*args, **kwargs):
        raise AssertionError("mutable Git attributes/config must not participate")

    monkeypatch.setattr(disposition.subprocess, "run", hostile_git)
    disposition._require_crlf_lf_equivalent(path, b'{\n  "value": 1\n}\n')


def test_exact_lexical_manifest_path_passes() -> None:
    assert disposition._exact_lexical_repo_path(
        MANIFEST_PATH.relative_to(ROOT).as_posix(), "manifest"
    ) == MANIFEST_PATH


@pytest.mark.parametrize("raw", ["../manifest.json", "./manifest.json", "/manifest.json", "folder\\manifest.json"])
def test_manifest_traversal_and_noncanonical_paths_reject(raw) -> None:
    with pytest.raises(disposition.BoundaryError, match="canonical repository-relative path"):
        disposition._exact_lexical_repo_path(raw, "manifest")


def test_alternate_manifest_path_rejects_before_content_lookup(authority) -> None:
    changed = deepcopy(authority)
    changed["reference_metadata"][0]["provenance_manifest"] = (
        "pipeline/higgsfield_debug/2026-07-09/prompt_isolation_tests/alternate/result_manifest.json"
    )
    with pytest.raises(disposition.BoundaryError, match="binding is incomplete"):
        disposition._validate_reference_metadata(changed, REFERENCE_COMMIT)


def test_repo_contained_manifest_symlink_to_identical_bytes_rejects(tmp_path, monkeypatch) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"{}\n")
    link = tmp_path / "manifest.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    monkeypatch.setattr(disposition, "ROOT", tmp_path)
    with pytest.raises(disposition.BoundaryError, match="symlink or path alias"):
        disposition._exact_lexical_repo_path("manifest.json", "manifest")


def test_missing_manifest_rejects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(disposition, "ROOT", tmp_path)
    with pytest.raises(disposition.BoundaryError, match="does not exist"):
        disposition._exact_lexical_repo_path("manifest.json", "manifest")


@pytest.mark.parametrize("invalid_soul", [WRONG_SOUL, STALE_SOUL])
def test_wrong_or_stale_soul_metadata_rejects(authority, invalid_soul) -> None:
    changed = deepcopy(authority)
    changed["reference_metadata"][0]["custom_reference_id"] = invalid_soul
    with pytest.raises(disposition.BoundaryError, match="metadata is invalid"):
        disposition._validate_reference_metadata(changed, REFERENCE_COMMIT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("custom_reference_id", WRONG_SOUL),
        ("provider_job_id", "different-job"),
        ("prompt_sha256", "0" * 64),
        ("image_prompt", "changed prompt"),
        ("provider_status", "failed"),
    ],
)
def test_semantic_manifest_changes_reject_before_checkout_equivalence(authority, monkeypatch, field, value) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest[field] = value
    changed = json.dumps(manifest, sort_keys=True).encode()
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: changed)
    with pytest.raises(disposition.BoundaryError, match="committed-byte binding"):
        disposition._validate_reference_metadata(authority, REFERENCE_COMMIT)


def test_dirty_manifest_checkout_rejects(authority, monkeypatch) -> None:
    committed = disposition._git_show_bytes(REFERENCE_COMMIT, MANIFEST_PATH)
    monkeypatch.setattr(disposition, "_git_show_bytes", lambda *args: committed)
    monkeypatch.setattr(disposition, "_git_blob_oid", lambda *args: MANIFEST_BLOB_OID)
    monkeypatch.setattr(disposition, "_require_crlf_lf_equivalent", lambda *args: (_ for _ in ()).throw(
        disposition.BoundaryError("identity_evidence_invalid", "local authority input differs")
    ))
    with pytest.raises(disposition.BoundaryError, match="local authority input differs"):
        disposition._validate_reference_metadata(authority, REFERENCE_COMMIT)
