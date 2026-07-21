from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from tools.strategy import lena_provider_prompt_limits_v1 as prompt_limits


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
# Compatibility aliases; authority lives in lena_provider_prompt_limits_v1.
PROVIDER_PROMPT_MAX_CHARS = prompt_limits.PROVIDER_PROMPT_PARSER_SAFETY_MAX_CHARS
PROVIDER_SECTION_BODY_MAX_CHARS = prompt_limits.PROVIDER_SECTION_BODY_MAX_CHARS


DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


def _is_default_ignorable_for_detection(char: str) -> bool:
    codepoint = ord(char)
    return unicodedata.category(char) == "Cf" or any(
        start <= codepoint <= end for start, end in DEFAULT_IGNORABLE_RANGES
    )


def _normalize_provider_body_for_detection(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def validate_provider_body_text(
    value: Any,
    *,
    label: str,
    max_chars: int,
) -> str:
    _require(
        isinstance(value, str),
        "provider_body_type_invalid",
        f"{label} must be plain text",
    )
    _require(
        type(max_chars) is int and max_chars > 0,
        "provider_body_limit_invalid",
        f"{label} must have a positive character limit",
    )
    _require(
        len(value) <= max_chars,
        "provider_body_too_long",
        f"{label} exceeds its {max_chars}-character limit",
    )
    for char in value:
        codepoint = f"U+{ord(char):04X}"
        _require(
            not _is_default_ignorable_for_detection(char),
            "provider_body_default_ignorable_forbidden",
            f"{label} contains forbidden default-ignorable character {codepoint}",
        )
        category = unicodedata.category(char)
        _require(
            category not in {"Zl", "Zp"},
            "provider_body_line_separator_forbidden",
            f"{label} contains forbidden Unicode line or paragraph separator {codepoint}",
        )
        _require(
            not category.startswith("C"),
            "provider_body_control_forbidden",
            f"{label} contains forbidden control character {codepoint}",
        )
        _require(
            char == " " or not char.isspace(),
            "provider_body_whitespace_noncanonical",
            f"{label} contains noncanonical whitespace character {codepoint}",
        )
    _require(
        value == value.strip(" ") and "  " not in value,
        "provider_body_whitespace_noncanonical",
        f"{label} must use single ASCII spaces without surrounding whitespace",
    )
    detection_text = _normalize_provider_body_for_detection(value)
    _require(
        "[" not in detection_text and "]" not in detection_text,
        "provider_body_bracket_forbidden",
        f"{label} contains square-bracket provider syntax",
    )
    return value


def validate_provider_body_inputs(
    values: Any,
    *,
    field_limits: dict[str, int],
    aggregate_max_chars: int,
) -> dict[str, str]:
    _require(isinstance(values, dict), "provider_body_inputs_invalid", "provider body inputs must be a mapping")
    _require(
        type(aggregate_max_chars) is int and aggregate_max_chars > 0,
        "provider_body_aggregate_limit_invalid",
        "provider body aggregate limit must be positive",
    )
    bounded: dict[str, str] = {}
    for label, max_chars in field_limits.items():
        value = values.get(label, "")
        if value is None:
            value = ""
        _require(isinstance(value, str), "provider_body_type_invalid", f"{label} must be plain text")
        _require(
            type(max_chars) is int and max_chars > 0,
            "provider_body_limit_invalid",
            f"{label} must have a positive character limit",
        )
        _require(
            len(value) <= max_chars,
            "provider_body_too_long",
            f"{label} exceeds its {max_chars}-character limit",
        )
        bounded[label] = value
    aggregate_chars = sum(len(value) for value in bounded.values())
    _require(
        aggregate_chars <= aggregate_max_chars,
        "provider_body_aggregate_too_long",
        f"provider body inputs exceed their {aggregate_max_chars}-character aggregate limit",
    )
    return {
        label: validate_provider_body_text(value, label=label, max_chars=field_limits[label])
        for label, value in bounded.items()
    }


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


def _git_bytes(root: Path, *args: str, code: str = "pose_authority_unavailable") -> bytes:
    from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate

    try:
        return selected_candidate._git_bytes(*args, root=root)
    except selected_candidate.ConsumerError as exc:
        raise PoseProvenanceError(code, exc.detail) from exc


def _worktree_bytes_match_commit(root: Path, commit: str, repo_path: str, current: bytes) -> bool:
    from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate

    try:
        return selected_candidate._worktree_bytes_match_commit(
            commit,
            repo_path,
            current,
            root=root,
        )
    except selected_candidate.ConsumerError as exc:
        raise PoseProvenanceError("pose_authority_unavailable", exc.detail) from exc


def _validate_selected_candidate_issuance(
    artifact: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    from tools.strategy import lena_execute_selected_candidate_v1 as selected_candidate
    try:
        issuance = selected_candidate.validate_selected_candidate_issuance(
            artifact,
            root=root,
        )
    except selected_candidate.ConsumerError as exc:
        code = {
            "authority_commit_invalid": "pose_authority_commit_invalid",
            "authority_commit_not_ancestor": "pose_authority_commit_not_ancestor",
            "authority_provenance_invalid": "pose_authority_provenance_invalid",
            "authority_commit_hash_mismatch": "pose_authority_commit_hash_mismatch",
        }.get(exc.code, exc.code)
        if exc.code == "stale_canonical_authority":
            code = (
                "pose_authority_worktree_drift"
                if "changed" in exc.detail
                else "pose_authority_unavailable"
            )
        raise PoseProvenanceError(code, exc.detail) from exc
    return issuance["candidate"]


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
    validate_provider_body_text(
        value,
        label=label,
        max_chars=PROVIDER_SECTION_BODY_MAX_CHARS,
    )


def _allowed_provider_section_sequences() -> tuple[tuple[str, ...], tuple[str, ...]]:
    complete = tuple(PROVIDER_SECTION_ORDER)
    without_presence = tuple(
        label for label in PROVIDER_SECTION_ORDER if label != "Subject Presence"
    )
    return complete, without_presence


def serialize_provider_prompt_sections(sections: Any) -> str:
    _require(
        isinstance(sections, (list, tuple)),
        "provider_section_grammar_invalid",
        "provider sections must be an ordered sequence",
    )
    normalized_sections: list[tuple[str, str]] = []
    for item in sections:
        _require(
            isinstance(item, (list, tuple)) and len(item) == 2,
            "provider_section_grammar_invalid",
            "each provider section must contain one label and one body",
        )
        label, body = item
        _require(
            isinstance(label, str) and label in PROVIDER_SECTION_ORDER,
            "provider_section_grammar_invalid",
            "provider section label is not canonical",
        )
        body = validate_provider_body_text(
            body,
            label=f"provider section {label}",
            max_chars=PROVIDER_SECTION_BODY_MAX_CHARS,
        )
        _require(
            bool(body) and body == body.strip(),
            "provider_section_body_invalid",
            f"provider section [{label}] body must be nonempty with canonical surrounding whitespace",
        )
        normalized_sections.append((label, body))
    labels = tuple(label for label, _ in normalized_sections)
    _require(
        labels in _allowed_provider_section_sequences(),
        "provider_section_grammar_invalid",
        "provider sections must use the complete canonical sequence",
    )
    prompt = "\n".join(f"[{label}]: {body}" for label, body in normalized_sections)
    _require(
        len(prompt) <= PROVIDER_PROMPT_MAX_CHARS,
        "provider_prompt_too_long",
        f"provider prompt exceeds its {PROVIDER_PROMPT_MAX_CHARS}-character limit",
    )
    return prompt


def parse_provider_prompt_sections(prompt: str) -> dict[str, str]:
    _require(isinstance(prompt, str), "provider_prompt_missing", "provider prompt is required")
    _require(
        len(prompt) <= PROVIDER_PROMPT_MAX_CHARS,
        "provider_prompt_too_long",
        f"provider prompt exceeds its {PROVIDER_PROMPT_MAX_CHARS}-character limit",
    )
    _require(bool(prompt.strip()), "provider_prompt_missing", "provider prompt is required")
    _require(
        "\r" not in prompt.replace("\r\n", ""),
        "provider_section_grammar_invalid",
        "provider prompt may use LF or CRLF line endings only",
    )
    lines = prompt.replace("\r\n", "\n").split("\n")
    complete, without_presence = _allowed_provider_section_sequences()
    expected = complete if len(lines) == len(complete) else without_presence
    _require(
        len(lines) == len(expected),
        "provider_section_grammar_invalid",
        "provider prompt must contain exactly the complete canonical header lines",
    )
    sections: dict[str, str] = {}
    for line, label in zip(lines, expected):
        prefix = f"[{label}]: "
        _require(
            line.startswith(prefix),
            "provider_section_grammar_invalid",
            f"provider section line must begin exactly with {prefix!r}",
        )
        body = line[len(prefix):]
        body = validate_provider_body_text(
            body,
            label=f"provider section {label}",
            max_chars=PROVIDER_SECTION_BODY_MAX_CHARS,
        )
        _require(
            bool(body) and body == body.strip(),
            "provider_section_body_invalid",
            f"provider section [{label}] body must be nonempty with canonical surrounding whitespace",
        )
        sections[label] = body
    _require(
        tuple(sections) in _allowed_provider_section_sequences()
        and tuple(sections).count("Action") == 1,
        "provider_action_section_count_invalid",
        "provider prompt must contain exactly one canonical [Action] section",
    )
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


def _resolve_bound_repo_path(root: Path, raw: Any, *, label: str) -> Path:
    value = str(raw or "").strip()
    _require(bool(value), "source_pose_path_missing", f"{label} is required")
    relative = Path(value)
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "source_pose_path_invalid",
        f"{label} must be a repository-relative path",
    )
    resolved = (root / relative).resolve()
    try:
        canonical = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PoseProvenanceError(
            "source_pose_path_invalid",
            f"{label} escapes the repository",
        ) from exc
    _require(
        canonical == relative.as_posix(),
        "source_pose_path_invalid",
        f"{label} is not in canonical repository-relative form",
    )
    return resolved


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PoseProvenanceError(
            "source_pose_artifact_unreadable",
            f"could not read {label}: {path}: {exc}",
        ) from exc
    _require(
        isinstance(value, dict),
        "source_pose_artifact_invalid",
        f"{label} must contain a JSON object",
    )
    return value


def validate_source_generation_pose_contract(
    manifest: Any,
    handoff_report: Any,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder

    _require(isinstance(manifest, dict), "source_manifest_invalid", "source generation manifest must be a JSON object")
    _require(isinstance(handoff_report, dict), "source_handoff_invalid", "source generation handoff must be a JSON object")
    source_pose = validate_pose_provenance(manifest.get("pose_provenance"))
    handoff_pose, packet_digest = validate_handoff_pose_copies(handoff_report)
    _require(
        source_pose == handoff_pose,
        "manifest_pose_provenance_mismatch",
        "source manifest pose provenance does not match the source generation handoff",
    )
    for field in ("pose_body_language_id", "pose_body_language_label", "pose_text"):
        _require(
            manifest.get(field) == source_pose[field],
            "manifest_pose_provenance_mismatch",
            f"source manifest {field} does not match its nested pose provenance",
        )

    prompt = manifest.get("image_prompt")
    _require(isinstance(prompt, str) and bool(prompt), "source_manifest_prompt_missing", "source manifest image_prompt is required")
    require_pose_bound_prompt(prompt, source_pose)
    prompt_sha = _sha256_bytes(prompt.encode("utf-8"))
    selected_prompt = handoff_report.get("selected_prompt_input")
    structured = handoff_report.get("structured_executor_inputs")
    provider_binding = handoff_report.get("provider_execution_binding")
    linkage = handoff_report.get("binding_linkage")
    _require(isinstance(selected_prompt, dict), "source_handoff_invalid", "source handoff selected_prompt_input is required")
    _require(isinstance(structured, dict), "source_handoff_invalid", "source handoff structured_executor_inputs is required")
    _require(isinstance(provider_binding, dict), "source_handoff_invalid", "source handoff provider_execution_binding is required")
    _require(isinstance(linkage, dict), "source_handoff_invalid", "source handoff binding_linkage is required")
    for label, value in (
        ("manifest prompt_sha256", manifest.get("prompt_sha256")),
        ("selected_prompt_input prompt_sha256", selected_prompt.get("prompt_sha256")),
        ("structured_executor_inputs selected_prompt_sha256", structured.get("selected_prompt_sha256")),
        ("provider_execution_binding provider_prompt_sha256", provider_binding.get("provider_prompt_sha256")),
    ):
        _require(
            value == prompt_sha,
            "source_prompt_sha_mismatch",
            f"{label} does not match the source manifest prompt bytes",
        )
    for label, value in (
        ("selected_prompt_input prompt_text", selected_prompt.get("prompt_text")),
        ("structured_executor_inputs selected_prompt_text", structured.get("selected_prompt_text")),
    ):
        _require(
            value == prompt,
            "source_prompt_text_mismatch",
            f"{label} does not match the source manifest prompt bytes",
        )

    candidate_path = _resolve_bound_repo_path(
        root,
        source_pose["selected_candidate_artifact_path"],
        label="pose selected candidate artifact path",
    )
    _require(candidate_path.is_file(), "source_pose_candidate_missing", f"selected candidate artifact is missing: {candidate_path}")
    _require(
        _sha256_bytes(candidate_path.read_bytes()) == source_pose["selected_candidate_artifact_sha256"],
        "pose_candidate_sha_mismatch",
        "source pose selected candidate SHA does not match current candidate bytes",
    )
    derived_pose = build_candidate_pose_provenance(candidate_path, root=root)
    _require(
        derived_pose == source_pose,
        "manifest_pose_provenance_mismatch",
        "source manifest pose provenance does not match deterministic candidate authority",
    )

    packet_path_value = handoff_report.get("selected_prompt_input_artifact_path")
    packet_path = _resolve_bound_repo_path(
        root,
        packet_path_value,
        label="source content packet artifact path",
    )
    _require(packet_path.is_file(), "source_pose_packet_missing", f"source content packet is missing: {packet_path}")
    packet_artifact_sha = _sha256_bytes(packet_path.read_bytes())
    expected_packet_path = str(packet_path_value)
    expected_packet_sha = handoff_report.get("selected_prompt_input_artifact_sha256")
    for label, value in (
        ("manifest packet path", manifest.get("pose_bound_content_packet_artifact_path")),
        ("selected_prompt_input packet path", selected_prompt.get("artifact_path")),
        ("provider_execution_binding packet path", provider_binding.get("content_packet_artifact_path")),
        ("binding_linkage packet path", linkage.get("content_packet_artifact_path")),
    ):
        _require(value == expected_packet_path, "manifest_pose_bound_packet_mismatch", f"{label} does not match the source handoff packet path")
    for label, value in (
        ("handoff packet SHA", expected_packet_sha),
        ("manifest packet SHA", manifest.get("pose_bound_content_packet_artifact_sha256")),
        ("selected_prompt_input packet SHA", selected_prompt.get("artifact_sha256")),
        ("structured_executor_inputs packet SHA", structured.get("selected_prompt_input_artifact_sha256")),
        ("provider_execution_binding packet SHA", provider_binding.get("content_packet_artifact_sha256")),
        ("binding_linkage packet SHA", linkage.get("content_packet_artifact_sha256")),
    ):
        _require(value == packet_artifact_sha, "manifest_pose_bound_packet_mismatch", f"{label} does not match the current source packet bytes")

    packet = _read_json_object(packet_path, label="source content packet")
    rebuilt_packet = packet_builder.rebuild_packet_from_authoritative_sources(
        packet,
        pose_binding=source_pose,
    )
    rebuilt_digest = _sha256_bytes(_canonical_bytes(rebuilt_packet))
    _require(
        rebuilt_digest == packet_digest,
        "manifest_pose_bound_packet_mismatch",
        "source handoff packet digest does not match authoritative packet reconstruction",
    )
    _require(
        manifest.get("pose_bound_content_packet_sha256") == packet_digest,
        "manifest_pose_bound_packet_mismatch",
        "source manifest packet digest does not match the source handoff",
    )
    return {
        "pose_provenance": source_pose,
        "prompt": prompt,
        "prompt_sha256": prompt_sha,
        "packet_path": packet_path,
        "packet_artifact_sha256": packet_artifact_sha,
        "packet_digest_sha256": packet_digest,
        "rebuilt_packet": rebuilt_packet,
    }
