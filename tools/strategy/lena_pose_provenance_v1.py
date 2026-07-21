from __future__ import annotations

import hashlib
import json
import os
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
PROVIDER_SECTION_ORDER = (
    "Subject",
    "Subject Presence",
    "Action",
    "Environment",
    "Cinematography",
    "Lighting/Style",
    "Technical",
)
PROVIDER_SECTION_TOKEN_RE = re.compile(
    r"\[(Subject Presence|Lighting/Style|Subject|Action|Environment|Cinematography|Technical)\]"
)


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


def _git_environment() -> dict[str, str]:
    return {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}


def _git_bytes(root: Path, *args: str, code: str = "pose_authority_unavailable") -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PoseProvenanceError(code, detail or "git authority validation failed")
    return completed.stdout


def _worktree_bytes_match_commit(root: Path, commit: str, repo_path: str, current: bytes) -> bool:
    cleaned = subprocess.run(
        ["git", "-C", str(root), "hash-object", f"--path={repo_path}", "--stdin"],
        input=current,
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    if cleaned.returncode != 0:
        raise PoseProvenanceError(
            "pose_authority_unavailable",
            f"git could not canonicalize authority input: {repo_path}",
        )
    committed_blob = _git_bytes(root, "rev-parse", f"{commit}:{repo_path}").strip()
    return cleaned.stdout.strip() == committed_blob


def _validate_selected_candidate_issuance(
    artifact: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate
    from tools.strategy import lena_pre_generation_candidate_gate_v1 as selector

    try:
        candidate = selected_candidate._validate_shape(artifact)
    except selected_candidate.ConsumerError as exc:
        raise PoseProvenanceError(exc.code, exc.detail) from exc

    stored_fingerprint = artifact.get("decision_fingerprint_sha256")
    _require(
        isinstance(stored_fingerprint, str) and bool(SHA256_RE.fullmatch(stored_fingerprint)),
        "decision_fingerprint_missing",
        "selected candidate decision fingerprint is missing or invalid",
    )
    decision_core = {
        key: value
        for key, value in artifact.items()
        if key not in {"generated_at_utc", "decision_fingerprint_sha256"}
    }
    _require(
        _sha256_bytes(selector._canonical_bytes(decision_core)) == stored_fingerprint,
        "decision_fingerprint_mismatch",
        "selected candidate decision fingerprint does not match its immutable body",
    )

    authority_commit = artifact.get("authority_commit")
    _require(
        isinstance(authority_commit, str) and bool(COMMIT_RE.fullmatch(authority_commit)),
        "pose_authority_commit_invalid",
        "selected candidate must bind a full authority_commit",
    )
    object_type = _git_bytes(
        root,
        "cat-file",
        "-t",
        authority_commit,
        code="pose_authority_commit_invalid",
    ).decode("ascii", errors="replace").strip()
    _require(
        object_type == "commit",
        "pose_authority_commit_invalid",
        "selected candidate authority_commit must identify a commit object exactly",
    )
    resolved_commit = _git_bytes(
        root,
        "rev-parse",
        "--verify",
        f"{authority_commit}^{{commit}}",
        code="pose_authority_commit_invalid",
    ).decode("ascii", errors="replace").strip()
    _require(
        resolved_commit == authority_commit,
        "pose_authority_commit_invalid",
        "selected candidate authority_commit did not resolve to the exact commit",
    )
    ancestor = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", authority_commit, "HEAD"],
        capture_output=True,
        check=False,
        env=_git_environment(),
    )
    _require(
        ancestor.returncode == 0,
        "pose_authority_commit_not_ancestor",
        "selected candidate authority_commit is unavailable or is not an ancestor of HEAD",
    )

    provenance = artifact.get("input_provenance")
    _require(
        isinstance(provenance, list),
        "pose_authority_provenance_invalid",
        "selected candidate input_provenance must be a list",
    )
    for repo_path in selector.AUTHORITY_PATHS:
        matches = [
            item
            for item in provenance
            if isinstance(item, dict) and item.get("path") == repo_path
        ]
        _require(
            len(matches) == 1,
            "pose_authority_provenance_invalid",
            f"canonical candidate authority must appear exactly once: {repo_path}",
        )
        recorded_sha = matches[0].get("sha256")
        _require(
            isinstance(recorded_sha, str) and bool(SHA256_RE.fullmatch(recorded_sha)),
            "pose_authority_provenance_invalid",
            f"canonical candidate authority has invalid SHA: {repo_path}",
        )
        authority_path = root / repo_path
        _require(
            authority_path.is_file(),
            "pose_authority_unavailable",
            f"canonical candidate authority is unavailable: {repo_path}",
        )
        current = authority_path.read_bytes()
        _require(
            _sha256_bytes(current) == recorded_sha,
            "pose_authority_worktree_drift",
            f"canonical candidate authority changed after candidate selection: {repo_path}",
        )
        _require(
            _worktree_bytes_match_commit(root, authority_commit, repo_path, current),
            "pose_authority_commit_hash_mismatch",
            f"canonical candidate authority does not match {authority_commit}: {repo_path}",
        )
    return candidate


def _git_show_bytes(root: Path, commit: str, repo_path: str) -> bytes:
    try:
        return _git_bytes(root, "show", f"{commit}:{repo_path}")
    except PoseProvenanceError as exc:
        raise PoseProvenanceError(
            "pose_authority_unavailable",
            f"could not read {repo_path} at {commit}: {exc.detail}",
        ) from exc


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
    candidate = _validate_selected_candidate_issuance(artifact, root=root)
    authority_commit = str(artifact["authority_commit"])

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


def reject_reserved_provider_section_tokens(value: str, *, label: str) -> None:
    token = PROVIDER_SECTION_TOKEN_RE.search(value)
    _require(
        token is None,
        "provider_section_token_injection",
        f"{label} contains reserved provider section token {token.group(0)!r}" if token else label,
    )


def parse_provider_prompt_sections(prompt: str) -> dict[str, str]:
    _require(isinstance(prompt, str) and bool(prompt.strip()), "provider_prompt_missing", "provider prompt is required")
    tokens = list(PROVIDER_SECTION_TOKEN_RE.finditer(prompt))
    _require(tokens, "provider_section_grammar_invalid", "provider prompt contains no canonical sections")
    labels = [match.group(1) for match in tokens]
    _require(
        labels.count("Action") == 1,
        "provider_action_section_count_invalid",
        "provider prompt must contain exactly one [Action] section",
    )
    _require(
        len(labels) == len(set(labels)),
        "provider_section_duplicate",
        "provider prompt contains a duplicate reserved section",
    )
    positions = [PROVIDER_SECTION_ORDER.index(label) for label in labels]
    _require(
        positions == sorted(positions),
        "provider_section_order_invalid",
        "provider prompt sections are not in canonical order",
    )

    sections: dict[str, str] = {}
    for index, match in enumerate(tokens):
        suffix = prompt[match.end():]
        _require(
            bool(re.match(r"\s*:", suffix)),
            "provider_section_grammar_invalid",
            f"reserved provider section [{match.group(1)}] must be followed by a colon",
        )
        body_start = match.end() + re.match(r"\s*:", suffix).end()
        body_end = tokens[index + 1].start() if index + 1 < len(tokens) else len(prompt)
        body = prompt[body_start:body_end].strip()
        _require(
            bool(body),
            "provider_section_body_missing",
            f"provider section [{match.group(1)}] must have a nonempty body",
        )
        sections[match.group(1)] = body
    return sections


def require_pose_bound_prompt(prompt: str, provenance: Any) -> None:
    binding = validate_pose_provenance(provenance)
    sections = parse_provider_prompt_sections(prompt)
    _require(
        sections["Action"] == binding["pose_text"],
        "provider_action_pose_mismatch",
        "provider Action must equal the selected candidate canonical pose text exactly",
    )


def validate_handoff_pose_copies(report: Any) -> tuple[dict[str, Any], str]:
    _require(isinstance(report, dict), "handoff_pose_contract_missing", "handoff must be a JSON object")
    binding = validate_pose_provenance(report.get("pose_provenance"))
    digest = report.get("pose_bound_content_packet_sha256")
    _require(
        isinstance(digest, str) and bool(SHA256_RE.fullmatch(digest)),
        "handoff_pose_bound_packet_sha_invalid",
        "handoff pose-bound content packet digest must be a lowercase SHA-256",
    )
    selected_prompt = report.get("selected_prompt_input")
    structured = report.get("structured_executor_inputs")
    candidate_summary = report.get("selected_candidate")
    candidate_binding = report.get("candidate_selection_binding")
    provider_binding = report.get("provider_execution_binding")
    linkage = report.get("binding_linkage")
    for label, value in (
        ("selected_prompt_input", selected_prompt),
        ("structured_executor_inputs", structured),
        ("selected_candidate", candidate_summary),
    ):
        _require(isinstance(value, dict), "handoff_pose_copy_missing", f"handoff {label} must be a JSON object")
    for label, value in (
        ("selected_prompt_input", selected_prompt),
        ("structured_executor_inputs", structured),
    ):
        _require(
            value.get("pose_provenance") == binding,
            "handoff_pose_provenance_mismatch",
            f"handoff {label} pose provenance differs from the top-level binding",
        )
        _require(
            value.get("pose_bound_content_packet_sha256") == digest,
            "handoff_pose_bound_packet_sha_mismatch",
            f"handoff {label} packet digest differs from the top-level binding",
        )
    identity_copies = [("selected_candidate", candidate_summary)]
    if isinstance(candidate_binding, dict):
        identity_copies.append(("candidate_selection_binding", candidate_binding))
    for label, value in identity_copies:
        _require(
            value.get("pose_body_language_id") == binding["pose_body_language_id"]
            and value.get("pose_body_language_label") == binding["pose_body_language_label"],
            "handoff_pose_identity_mismatch",
            f"handoff {label} pose identity differs from the top-level binding",
        )
    fingerprint_copies = [
        (label, value)
        for label, value in (
            ("candidate_selection_binding", candidate_binding),
            ("provider_execution_binding", provider_binding),
            ("binding_linkage", linkage),
        )
        if isinstance(value, dict)
    ]
    for label, value in fingerprint_copies:
        _require(
            value.get("pose_provenance_fingerprint_sha256")
            == binding["pose_provenance_fingerprint_sha256"],
            "handoff_pose_fingerprint_mismatch",
            f"handoff {label} pose fingerprint differs from the top-level binding",
        )
    if isinstance(linkage, dict):
        _require(
            linkage.get("pose_body_language_id") == binding["pose_body_language_id"],
            "handoff_pose_identity_mismatch",
            "handoff binding_linkage pose ID differs from the top-level binding",
        )
    digest_copies = [
        (label, value)
        for label, value in (
            ("provider_execution_binding", provider_binding),
            ("binding_linkage", linkage),
        )
        if isinstance(value, dict)
    ]
    for label, value in digest_copies:
        _require(
            value.get("pose_bound_content_packet_sha256") == digest,
            "handoff_pose_bound_packet_sha_mismatch",
            f"handoff {label} packet digest differs from the top-level binding",
        )
    return binding, digest
