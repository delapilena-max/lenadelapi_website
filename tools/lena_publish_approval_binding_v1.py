from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Type

APPROVAL_CORRECTION_SCHEMA_VERSION = "lena_publish_approval_sha_binding_correction_v1"
APPROVAL_CORRECTION_ACTION = "correction_record_only_no_apply_or_promote_or_publish"
APPROVAL_CORRECTION_REASON = "approval_packet_or_draft_sha_missing_or_incorrect_only"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "publish_packets" / "lena"
MAX_HASHTAGS_PER_CAPTION = 3
REQUIRED_CAPTION_CONFIRM_PHRASE = "I approve this caption"
REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE = "I approve this for live publish"
QUEUE_DRAFT_CAPTION_PLACEHOLDER = (
    "<PLACEHOLDER -- operator must choose a final caption from the publish "
    "packet before moving this into the live queue>"
)


def _fail(error_cls: Type[Exception], message: str) -> None:
    raise error_cls(message)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_object(path: Path, label: str, error_cls: Type[Exception]) -> Dict[str, Any]:
    if not path.exists():
        _fail(error_cls, f"{label} does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        _fail(error_cls, f"{label} failed to parse: {path}: {exc}")
    if not isinstance(data, dict):
        _fail(error_cls, f"{label} did not contain a JSON object: {path}")
    return data


def _serialize_json_bytes(value: Dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _serialize_queue_draft_bytes(value: Dict[str, Any]) -> bytes:
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text.replace("\n", os.linesep).encode("utf-8")


def _count_hashtags(caption: str) -> int:
    return sum(1 for token in caption.split() if token.startswith("#"))


def _authoritative_queue_draft_sha256(
    queue_draft_path: Path,
    *,
    allow_caption_applied_queue_draft: bool,
    approved_caption: str,
    error_cls: Type[Exception],
) -> str:
    current_sha = _sha256_file(queue_draft_path)
    if not allow_caption_applied_queue_draft:
        return current_sha

    queue_draft = _read_json_object(queue_draft_path, "queue draft", error_cls)
    if queue_draft.get("caption") != approved_caption:
        return current_sha

    normalized_pre_apply = dict(queue_draft)
    normalized_pre_apply["caption"] = QUEUE_DRAFT_CAPTION_PLACEHOLDER
    return hashlib.sha256(_serialize_queue_draft_bytes(normalized_pre_apply)).hexdigest()


def resolve_approval_output_path(date_str: str, slot_id: str, out_dir: Optional[Path] = None) -> Path:
    base = out_dir if out_dir is not None else DEFAULT_APPROVAL_ROOT
    return base / date_str / f"{slot_id}_approval.json"


def resolve_approval_sha_correction_output_path(
    date_str: str, slot_id: str, out_dir: Optional[Path] = None
) -> Path:
    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)
    return approval_path.with_name(f"{slot_id}_approval_sha_binding_correction.json")


def _validate_approval_shape(
    approval: Dict[str, Any],
    date_str: str,
    slot_id: str,
    require_live_publish_authorization: bool,
    require_bound_files_exist: bool,
    error_cls: Type[Exception],
) -> Dict[str, Any]:
    if approval.get("post_id") != slot_id:
        _fail(
            error_cls,
            f"approval post_id {approval.get('post_id')!r} does not match requested slot {slot_id!r}",
        )
    if approval.get("source_date") != date_str:
        _fail(
            error_cls,
            f"approval source_date {approval.get('source_date')!r} does not match requested date {date_str!r}",
        )

    approved_caption = approval.get("approved_caption")
    if not approved_caption or not str(approved_caption).strip():
        _fail(error_cls, "approval's approved_caption is missing or empty")

    actual_hashtag_count = _count_hashtags(str(approved_caption))
    stored_hashtag_count = approval.get("hashtag_count")
    if actual_hashtag_count != stored_hashtag_count:
        _fail(
            error_cls,
            f"approval hashtag_count {stored_hashtag_count!r} does not match the actual "
            f"hashtag count ({actual_hashtag_count}) found in approved_caption",
        )
    if not (0 <= actual_hashtag_count <= MAX_HASHTAGS_PER_CAPTION):
        _fail(
            error_cls,
            f"hashtag count {actual_hashtag_count} is not between 0 and "
            f"{MAX_HASHTAGS_PER_CAPTION} inclusive",
        )

    approved_by = approval.get("approved_by")
    if not approved_by or not str(approved_by).strip():
        _fail(error_cls, "approval's approved_by is missing or empty")

    caption_statement = approval.get("caption_approval_statement")
    live_publish_statement = approval.get("live_publish_statement")
    legacy_statement = approval.get("approval_statement")
    is_legacy = caption_statement is None and live_publish_statement is None and legacy_statement is not None

    if require_live_publish_authorization:
        if is_legacy:
            if legacy_statement != REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE:
                _fail(
                    error_cls,
                    f"legacy approval_statement {legacy_statement!r} does not exactly match "
                    f"the required phrase {REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE!r}",
                )
            effective_caption_statement = legacy_statement
            effective_live_publish_statement = legacy_statement
        else:
            if caption_statement != REQUIRED_CAPTION_CONFIRM_PHRASE:
                _fail(
                    error_cls,
                    f"approval's caption_approval_statement {caption_statement!r} does not exactly match "
                    f"the required phrase {REQUIRED_CAPTION_CONFIRM_PHRASE!r}",
                )
            if live_publish_statement != REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE:
                _fail(
                    error_cls,
                    f"approval's live_publish_statement {live_publish_statement!r} does not exactly "
                    f"match the required phrase {REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE!r} -- live publish "
                    "has not been explicitly authorized; caption approval alone is not sufficient to promote",
                )
            effective_caption_statement = caption_statement
            effective_live_publish_statement = live_publish_statement
    else:
        if is_legacy:
            if legacy_statement != REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE:
                _fail(
                    error_cls,
                    "approval artifact has neither a valid caption_approval_statement nor a "
                    f"legacy approval_statement matching {REQUIRED_LIVE_PUBLISH_CONFIRM_PHRASE!r}",
                )
            effective_caption_statement = legacy_statement
            effective_live_publish_statement = legacy_statement
        else:
            if caption_statement != REQUIRED_CAPTION_CONFIRM_PHRASE:
                _fail(
                    error_cls,
                    f"approval's caption_approval_statement {caption_statement!r} does not exactly match "
                    f"the required phrase {REQUIRED_CAPTION_CONFIRM_PHRASE!r}",
                )
            effective_caption_statement = caption_statement
            effective_live_publish_statement = live_publish_statement

    if "manual_one_off_confirmed" in approval and approval.get("manual_one_off_confirmed") is not True:
        _fail(error_cls, "approval's manual_one_off_confirmed is present but not true")
    if approval.get("promotion_status") != "not_yet_promoted":
        _fail(
            error_cls,
            f"approval promotion_status {approval.get('promotion_status')!r} is not "
            "'not_yet_promoted' -- refusing to use an item that may already have "
            "been promoted or published",
        )

    publish_packet_path_text = approval.get("publish_packet_path")
    queue_draft_path_text = approval.get("queue_draft_path")
    if not isinstance(publish_packet_path_text, str) or not publish_packet_path_text:
        _fail(error_cls, "approval publish_packet_path is missing or empty")
    if not isinstance(queue_draft_path_text, str) or not queue_draft_path_text:
        _fail(error_cls, "approval queue_draft_path is missing or empty")

    publish_packet_path = Path(publish_packet_path_text)
    queue_draft_path = Path(queue_draft_path_text)
    if require_bound_files_exist:
        if not publish_packet_path.exists():
            _fail(error_cls, f"approval publish_packet_path does not exist: {publish_packet_path}")
        if not queue_draft_path.exists():
            _fail(error_cls, f"approval queue_draft_path does not exist: {queue_draft_path}")

    return {
        "approved_caption": str(approved_caption),
        "hashtag_count": actual_hashtag_count,
        "approved_by": str(approved_by),
        "approved_at_utc": approval.get("approved_at_utc"),
        "approval_statement": effective_caption_statement,
        "caption_approval_statement": effective_caption_statement,
        "live_publish_statement": effective_live_publish_statement,
        "publish_packet_path": publish_packet_path,
        "queue_draft_path": queue_draft_path,
    }


def _collect_native_sha_binding_defects(
    approval: Dict[str, Any],
    publish_packet_path: Path,
    queue_draft_path: Path,
    *,
    allow_caption_applied_queue_draft: bool,
    approved_caption: str,
) -> tuple[list[str], str, str]:
    defects: list[str] = []
    actual_packet_sha = _sha256_file(publish_packet_path)
    authoritative_draft_sha = _authoritative_queue_draft_sha256(
        queue_draft_path,
        allow_caption_applied_queue_draft=allow_caption_applied_queue_draft,
        approved_caption=approved_caption,
        error_cls=ValueError,
    )

    native_packet_sha = approval.get("publish_packet_sha256")
    native_draft_sha = approval.get("queue_draft_sha256")

    if not isinstance(native_packet_sha, str) or not native_packet_sha:
        defects.append("publish_packet_sha256_missing")
    elif not SHA256_RE.fullmatch(native_packet_sha):
        defects.append("publish_packet_sha256_malformed")
    elif native_packet_sha != actual_packet_sha:
        defects.append("publish_packet_sha256_mismatch")

    if not isinstance(native_draft_sha, str) or not native_draft_sha:
        defects.append("queue_draft_sha256_missing")
    elif not SHA256_RE.fullmatch(native_draft_sha):
        defects.append("queue_draft_sha256_malformed")
    elif native_draft_sha != authoritative_draft_sha:
        defects.append("queue_draft_sha256_mismatch")

    return defects, actual_packet_sha, authoritative_draft_sha


def _validate_correction_artifact(
    correction_path: Path,
    approval_path: Path,
    approval_sha: str,
    publish_packet_path: Path,
    publish_packet_sha: str,
    queue_draft_path: Path,
    queue_draft_sha: str,
    native_defects: list[str],
    date_str: str,
    slot_id: str,
    error_cls: Type[Exception],
) -> Dict[str, Any]:
    correction = _read_json_object(correction_path, "approval SHA-binding correction artifact", error_cls)
    if correction.get("schema_version") != APPROVAL_CORRECTION_SCHEMA_VERSION:
        _fail(error_cls, "approval SHA-binding correction artifact schema_version is invalid")
    if correction.get("influencer_id") != "lena":
        _fail(error_cls, "approval SHA-binding correction artifact influencer_id must be 'lena'")
    if correction.get("date") != date_str or correction.get("slot_id") != slot_id:
        _fail(error_cls, "approval SHA-binding correction artifact date/slot binding is invalid")
    if correction.get("supersedes_deficient_approval_for_execution_only") is not True:
        _fail(error_cls, "approval SHA-binding correction artifact must supersede the deficient approval for execution only")
    if correction.get("preserves_immutable_historical_artifacts") is not True:
        _fail(error_cls, "approval SHA-binding correction artifact must preserve immutable historical artifacts")
    if correction.get("action") != APPROVAL_CORRECTION_ACTION:
        _fail(error_cls, "approval SHA-binding correction artifact action is invalid")
    if correction.get("recovery_reason") != APPROVAL_CORRECTION_REASON:
        _fail(error_cls, "approval SHA-binding correction artifact recovery_reason is invalid")
    if correction.get("historical_artifacts_modified") != []:
        _fail(error_cls, "approval SHA-binding correction artifact must not modify historical artifacts")
    observed_defects = correction.get("observed_native_sha_binding_defects")
    if observed_defects != native_defects:
        _fail(error_cls, "approval SHA-binding correction artifact does not match the native approval SHA-binding defects")

    if correction.get("approval_artifact_path") != str(approval_path.resolve()):
        _fail(error_cls, "approval SHA-binding correction artifact approval_artifact_path does not match the authoritative approval path")
    if correction.get("approval_artifact_sha256") != approval_sha:
        _fail(error_cls, "approval SHA-binding correction artifact approval_artifact_sha256 does not match the authoritative approval bytes")
    if correction.get("publish_packet_path") != str(publish_packet_path.resolve()):
        _fail(error_cls, "approval SHA-binding correction artifact publish_packet_path does not match the authoritative packet path")
    if correction.get("publish_packet_sha256") != publish_packet_sha:
        _fail(error_cls, "approval SHA-binding correction artifact publish_packet_sha256 does not match the authoritative packet bytes")
    if correction.get("queue_draft_path") != str(queue_draft_path.resolve()):
        _fail(error_cls, "approval SHA-binding correction artifact queue_draft_path does not match the authoritative draft path")
    if correction.get("queue_draft_sha256") != queue_draft_sha:
        _fail(error_cls, "approval SHA-binding correction artifact queue_draft_sha256 does not match the authoritative draft bytes")

    return correction


def resolve_approval_execution_bindings(
    date_str: str,
    slot_id: str,
    out_dir: Optional[Path],
    *,
    require_live_publish_authorization: bool,
    allow_caption_applied_queue_draft: bool,
    error_cls: Type[Exception],
) -> Dict[str, Any]:
    approval_path = resolve_approval_output_path(date_str, slot_id, out_dir)
    approval = _read_json_object(approval_path, "approval artifact", error_cls)
    facts = _validate_approval_shape(
        approval,
        date_str,
        slot_id,
        require_live_publish_authorization=require_live_publish_authorization,
        require_bound_files_exist=True,
        error_cls=error_cls,
    )
    approval_sha = _sha256_file(approval_path)
    native_defects, packet_sha, draft_sha = _collect_native_sha_binding_defects(
        approval,
        facts["publish_packet_path"],
        facts["queue_draft_path"],
        allow_caption_applied_queue_draft=allow_caption_applied_queue_draft,
        approved_caption=facts["approved_caption"],
    )
    correction_path = resolve_approval_sha_correction_output_path(date_str, slot_id, out_dir)

    binding_source = "native"
    correction_sha: Optional[str] = None
    if native_defects:
        if not correction_path.exists():
            _fail(
                error_cls,
                "approval SHA bindings are missing or invalid and no correction artifact exists: "
                + ", ".join(native_defects),
            )
        _validate_correction_artifact(
            correction_path,
            approval_path.resolve(),
            approval_sha,
            facts["publish_packet_path"].resolve(),
            packet_sha,
            facts["queue_draft_path"].resolve(),
            draft_sha,
            native_defects,
            date_str,
            slot_id,
            error_cls,
        )
        correction_sha = _sha256_file(correction_path)
        binding_source = "corrected"
    elif correction_path.exists():
        _fail(
            error_cls,
            "approval SHA-binding correction artifact exists even though the native approval already binds the exact packet and draft bytes",
        )

    return {
        "approval_path": str(approval_path),
        "approval_sha256": approval_sha,
        "approval_binding_source": binding_source,
        "approval_correction_artifact_path": str(correction_path) if correction_path.exists() else None,
        "approval_correction_artifact_sha256": correction_sha,
        "publish_packet_path": str(facts["publish_packet_path"].resolve()),
        "publish_packet_sha256": packet_sha,
        "queue_draft_path": str(facts["queue_draft_path"].resolve()),
        "queue_draft_sha256": draft_sha,
        "approved_caption": facts["approved_caption"],
        "hashtag_count": facts["hashtag_count"],
        "approved_by": facts["approved_by"],
        "approved_at_utc": facts["approved_at_utc"],
        "approval_statement": facts["approval_statement"],
        "caption_approval_statement": facts["caption_approval_statement"],
        "live_publish_statement": facts["live_publish_statement"],
    }


def build_approval_sha_binding_correction(approval_path: Path) -> tuple[Dict[str, Any], Path]:
    approval_path = approval_path.resolve()
    approval = _read_json_object(approval_path, "existing approval artifact", ValueError)
    date_str = str(approval.get("source_date") or "")
    slot_id = str(approval.get("post_id") or "")
    if not date_str or not slot_id:
        raise ValueError("existing approval artifact source_date/post_id is incomplete")

    facts = _validate_approval_shape(
        approval,
        date_str,
        slot_id,
        require_live_publish_authorization=False,
        require_bound_files_exist=True,
        error_cls=ValueError,
    )
    native_defects, packet_sha, draft_sha = _collect_native_sha_binding_defects(
        approval,
        facts["publish_packet_path"],
        facts["queue_draft_path"],
        allow_caption_applied_queue_draft=False,
        approved_caption=facts["approved_caption"],
    )
    if not native_defects:
        raise ValueError("existing approval artifact already binds the exact publish packet and queue draft bytes")

    correction_path = resolve_approval_sha_correction_output_path(date_str, slot_id, approval_path.parents[1])
    if correction_path.exists():
        raise ValueError("approval SHA-binding correction artifact already exists for this exact approval lineage")

    approval_sha = _sha256_file(approval_path)
    correction = {
        "schema_version": APPROVAL_CORRECTION_SCHEMA_VERSION,
        "influencer_id": "lena",
        "corrected_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "date": date_str,
        "slot_id": slot_id,
        "approval_artifact_path": str(approval_path),
        "approval_artifact_sha256": approval_sha,
        "publish_packet_path": str(facts["publish_packet_path"].resolve()),
        "publish_packet_sha256": packet_sha,
        "queue_draft_path": str(facts["queue_draft_path"].resolve()),
        "queue_draft_sha256": draft_sha,
        "observed_native_sha_binding_defects": native_defects,
        "native_publish_packet_sha256": approval.get("publish_packet_sha256"),
        "native_queue_draft_sha256": approval.get("queue_draft_sha256"),
        "supersedes_deficient_approval_for_execution_only": True,
        "preserves_immutable_historical_artifacts": True,
        "action": APPROVAL_CORRECTION_ACTION,
        "recovery_reason": APPROVAL_CORRECTION_REASON,
        "historical_artifacts_modified": [],
    }
    return correction, correction_path


def write_approval_sha_binding_correction(path: Path, correction: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"refusing to overwrite an existing artifact: {path}")
    path.write_bytes(_serialize_json_bytes(correction))
