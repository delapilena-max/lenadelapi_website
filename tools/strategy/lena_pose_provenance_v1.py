from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "lena_pose_provenance_binding_v1"
AUTHORITY_SOURCE = "selected_candidate_canonical_pose"
POSE_AUTHORITY_REPO_PATH = "pipeline/prompt_banks/lena/lena_pose_body_language_bank_v1.json"
RECIPE_SUBJECT_POSE_SEMANTICS = "non_authoritative_recipe_context_only"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class PoseProvenanceError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise PoseProvenanceError(code, detail)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _normalize_line_endings(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n")


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PoseProvenanceError(
            "pose_candidate_path_outside_repo",
            f"selected candidate artifact must remain inside the repository: {path}",
        ) from exc


def _git_show_bytes(root: Path, commit: str, repo_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{repo_path}"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PoseProvenanceError(
            "pose_authority_unavailable",
            f"could not read {repo_path} at {commit}: {detail}",
        )
    return completed.stdout


def validate_pose_provenance(
    value: Any,
    *,
    expected_candidate_path: str | None = None,
    expected_candidate_sha256: str | None = None,
    expected_authority_commit: str | None = None,
) -> dict[str, Any]:
    _require(isinstance(value, dict), "pose_provenance_missing", "pose provenance must be a JSON object")
    required_text = (
        "schema_version",
        "authority_source",
        "selected_candidate_artifact_path",
        "selected_candidate_artifact_sha256",
        "selected_candidate_authority_commit",
        "pose_authority_artifact_path",
        "pose_authority_artifact_sha256",
        "pose_body_language_id",
        "pose_body_language_label",
        "pose_text",
        "pose_text_sha256",
        "recipe_subject_pose_semantics",
        "pose_provenance_fingerprint_sha256",
    )
    for key in required_text:
        _require(
            isinstance(value.get(key), str) and bool(value[key].strip()),
            "pose_provenance_incomplete",
            f"pose provenance field {key} is required",
        )
    _require(value["schema_version"] == SCHEMA_VERSION, "pose_provenance_schema_mismatch", "pose provenance schema is invalid")
    _require(value["authority_source"] == AUTHORITY_SOURCE, "pose_authority_source_mismatch", "pose authority source is invalid")
    _require(value["pose_authority_artifact_path"] == POSE_AUTHORITY_REPO_PATH, "pose_authority_path_mismatch", "pose authority path is invalid")
    _require(value["recipe_subject_pose_semantics"] == RECIPE_SUBJECT_POSE_SEMANTICS, "recipe_pose_semantics_mismatch", "recipe subject_pose must remain explicitly non-authoritative")
    for key in (
        "selected_candidate_artifact_sha256",
        "pose_authority_artifact_sha256",
        "pose_text_sha256",
        "pose_provenance_fingerprint_sha256",
    ):
        _require(bool(SHA256_RE.fullmatch(value[key])), "pose_provenance_sha_invalid", f"{key} must be a lowercase SHA-256")
    _require(bool(COMMIT_RE.fullmatch(value["selected_candidate_authority_commit"])), "pose_authority_commit_invalid", "selected candidate authority commit must be a full commit SHA")
    _require(
        value["pose_text_sha256"] == _sha256_bytes(value["pose_text"].encode("utf-8")),
        "pose_text_sha_mismatch",
        "pose_text_sha256 does not match canonical pose text",
    )
    core = {key: item for key, item in value.items() if key != "pose_provenance_fingerprint_sha256"}
    _require(
        value["pose_provenance_fingerprint_sha256"] == _sha256_bytes(_canonical_bytes(core)),
        "pose_provenance_fingerprint_mismatch",
        "pose provenance fingerprint does not match its immutable body",
    )
    if expected_candidate_path is not None:
        _require(value["selected_candidate_artifact_path"] == expected_candidate_path, "pose_candidate_path_mismatch", "pose provenance candidate path does not match the handoff binding")
    if expected_candidate_sha256 is not None:
        _require(value["selected_candidate_artifact_sha256"] == expected_candidate_sha256, "pose_candidate_sha_mismatch", "pose provenance candidate SHA does not match the handoff binding")
    if expected_authority_commit is not None:
        _require(value["selected_candidate_authority_commit"] == expected_authority_commit, "pose_authority_commit_mismatch", "pose provenance authority commit does not match the selected candidate")
    return dict(value)


def build_candidate_pose_provenance(candidate_path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    candidate_path = candidate_path.resolve()
    candidate_repo_path = _repo_relative(candidate_path, root)
    try:
        candidate_bytes = candidate_path.read_bytes()
        artifact = json.loads(candidate_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PoseProvenanceError("pose_candidate_unreadable", f"could not read selected candidate artifact: {exc}") from exc
    _require(isinstance(artifact, dict), "pose_candidate_invalid", "selected candidate artifact must contain a JSON object")
    _require(artifact.get("candidate_status") == "selected", "pose_candidate_not_selected", "pose authority requires a selected candidate")
    candidate = artifact.get("candidate")
    _require(isinstance(candidate, dict), "pose_candidate_invalid", "selected candidate artifact must contain candidate data")
    authority_commit = str(artifact.get("authority_commit") or "").strip()
    _require(bool(COMMIT_RE.fullmatch(authority_commit)), "pose_authority_commit_invalid", "selected candidate must bind a full authority_commit")

    pose_id = str(candidate.get("pose_body_language_id") or "").strip()
    candidate_label = str(candidate.get("pose_body_language_label") or candidate.get("pose") or "").strip()
    _require(bool(pose_id), "pose_identity_missing", "selected candidate is missing pose_body_language_id")
    _require(bool(candidate_label), "pose_label_missing", "selected candidate is missing its canonical pose label")

    authority_bytes = _git_show_bytes(root, authority_commit, POSE_AUTHORITY_REPO_PATH)
    local_authority_path = root / POSE_AUTHORITY_REPO_PATH
    _require(local_authority_path.is_file(), "pose_authority_missing", f"pose authority is missing: {local_authority_path}")
    _require(
        _normalize_line_endings(local_authority_path.read_bytes()) == _normalize_line_endings(authority_bytes),
        "pose_authority_worktree_drift",
        "local pose authority differs from the selected candidate authority commit beyond CRLF/LF materialization",
    )
    try:
        authority = json.loads(authority_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PoseProvenanceError("pose_authority_invalid", f"pose authority is invalid JSON: {exc}") from exc
    matches = [
        item for item in authority.get("combos", [])
        if isinstance(item, dict) and item.get("pose_body_language_id") == pose_id
    ]
    _require(len(matches) == 1, "pose_identity_not_authoritative", f"pose ID {pose_id!r} must resolve exactly once in canonical authority")
    entry = matches[0]
    canonical_label = str(entry.get("label") or "").strip()
    canonical_text = str(entry.get("text") or "").strip()
    _require(bool(canonical_label and canonical_text), "pose_authority_incomplete", "canonical pose entry must contain label and text")
    _require(candidate_label == canonical_label, "pose_label_mismatch", "selected candidate pose label disagrees with canonical authority")
    if candidate.get("pose_text") is not None:
        _require(str(candidate.get("pose_text") or "").strip() == canonical_text, "pose_text_mismatch", "selected candidate pose text disagrees with canonical authority")

    core = {
        "schema_version": SCHEMA_VERSION,
        "authority_source": AUTHORITY_SOURCE,
        "selected_candidate_artifact_path": candidate_repo_path,
        "selected_candidate_artifact_sha256": _sha256_bytes(candidate_bytes),
        "selected_candidate_authority_commit": authority_commit,
        "pose_authority_artifact_path": POSE_AUTHORITY_REPO_PATH,
        "pose_authority_artifact_sha256": _sha256_bytes(authority_bytes),
        "pose_body_language_id": pose_id,
        "pose_body_language_label": canonical_label,
        "pose_text": canonical_text,
        "pose_text_sha256": _sha256_bytes(canonical_text.encode("utf-8")),
        "recipe_subject_pose_semantics": RECIPE_SUBJECT_POSE_SEMANTICS,
    }
    value = {**core, "pose_provenance_fingerprint_sha256": _sha256_bytes(_canonical_bytes(core))}
    return validate_pose_provenance(value)


def require_pose_bound_prompt(prompt: str, provenance: Any) -> None:
    binding = validate_pose_provenance(provenance)
    canonical_text = binding["pose_text"]
    action_match = re.search(
        r"\[Action\]:\s*(.*?)(?=\s+\[(?:Environment|Cinematography|Lighting/Style|Technical)\]:|$)",
        prompt,
        flags=re.DOTALL,
    )
    if action_match is not None:
        actual = action_match.group(1).strip()
        _require(actual == canonical_text, "provider_action_pose_mismatch", "provider Action must equal the selected candidate canonical pose text exactly")
        return
    pose_match = re.search(r"(?:^|\s)Pose:\s*(.*?)(?=\s+(?:Expression|Camera|Lighting|Mood):|$)", prompt, flags=re.DOTALL)
    _require(pose_match is not None, "provider_pose_section_missing", "provider prompt is missing a canonical Action or Pose section")
    actual = pose_match.group(1).strip().removesuffix(".")
    _require(actual == canonical_text, "provider_action_pose_mismatch", "provider Pose must equal the selected candidate canonical pose text exactly")
