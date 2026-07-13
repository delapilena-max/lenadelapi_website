from __future__ import annotations

"""Local coordinator for Lena's static-photo-plus-music Reel lane.

The command is inspect-only by default. ``--apply-local`` may compose the
local Reel and write a publish packet plus queue-shaped draft, but this module
has no approval, clean-export, promotion, queue, upload, publish, analytics,
learning, provider, or network integration.
"""

import argparse
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.lena_build_publish_packet_v1 as packet_tools  # noqa: E402
import tools.lena_music_pool_v1 as music_pool_tools  # noqa: E402
import tools.lena_prepare_story_video_v1 as reel_tools  # noqa: E402


STOP_BOUNDARY = "ready_for_human_review"
FULL_MANUAL_PREFLIGHT = "deferred_pending_human_approval_and_clean_export"
ALLOWED_STATES = {
    "blocked",
    "ready_for_local_composition",
    "reel_prepared",
    "package_prepared",
    "ready_for_human_review",
}
STRATEGY_FIELDS = {
    "canonical_niche",
    "strategy_pillars",
    "creative_temperature",
    "narrative_roles",
    "choice_eligible",
    "payoff_eligible",
}


class CoordinatorError(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result_template(*, apply_local: bool) -> Dict[str, Any]:
    return {
        "ok": False,
        "dry_run": not apply_local,
        "state": "blocked",
        "stage_results": [],
        "blocker_codes": [],
        "blocker_reasons": [],
        "source_provenance": {},
        "reel_provenance": {},
        "package_provenance": {},
        "files_would_write": [],
        "files_written_this_run": [],
        "stop_boundary": STOP_BOUNDARY,
        "full_manual_preflight": FULL_MANUAL_PREFLIGHT,
    }


def _block(result: Dict[str, Any], code: str, reason: str) -> Dict[str, Any]:
    result["ok"] = False
    result["state"] = "blocked"
    result["blocker_codes"].append(code)
    result["blocker_reasons"].append(reason)
    result["stage_results"].append({"stage": "hard_stop", "status": "blocked", "code": code})
    return result


def _validate_identity(label: str, value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise CoordinatorError(f"missing_{label}", f"explicit {label.replace('_', ' ')} is required")
    if any(token in cleaned for token in (",", ";")):
        raise CoordinatorError(
            f"ambiguous_{label}",
            f"exactly one explicit {label.replace('_', ' ')} is required: {cleaned!r}",
        )
    return cleaned


def _classify_source_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "ambiguous" in message or "multiple" in message:
        return "ambiguous_source_evidence"
    if "overall='fail'" in message or "overall=\"fail\"" in message or "not 'pass'" in message:
        return "failed_qa"
    if "qa" in message and any(word in message for word in ("missing", "no qa", "parse", "inconsistent", "incomplete")):
        return "incomplete_qa"
    return "missing_source_evidence"


def _composition_provenance_path(video_path: Path) -> Path:
    return video_path.with_name(video_path.stem + "_provenance.json")


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CoordinatorError(f"conflicting_{label}", f"could not parse {label} at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoordinatorError(f"conflicting_{label}", f"{label} at {path} is not a JSON object")
    return value


def _load_composition_provenance(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CoordinatorError("provenance_mismatch", f"could not parse composition provenance {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CoordinatorError("provenance_mismatch", f"composition provenance {path} is not a JSON object")
    return value


def _validate_composition_binding(
    provenance: Dict[str, Any],
    *,
    source_path: Path,
    source_sha256: str,
    reel_slot: str,
    video_path: Path,
) -> None:
    checks = {
        "slot_id": (provenance.get("slot_id"), reel_slot),
        "source_image_path": (
            str(Path(str(provenance.get("source_image_path") or "")).resolve()),
            str(source_path.resolve()),
        ),
        "source_image_sha256": (provenance.get("source_image_sha256"), source_sha256),
        "output_path": (
            str(Path(str(provenance.get("output_path") or "")).resolve()),
            str(video_path.resolve()),
        ),
    }
    for field, (actual, expected) in checks.items():
        if actual != expected:
            code = "source_hash_conflict" if field == "source_image_sha256" else "provenance_mismatch"
            raise CoordinatorError(
                code,
                f"composition provenance {field} {actual!r} does not match expected {expected!r}",
            )
    actual_output_hash = _sha256_file(video_path)
    if provenance.get("output_sha256") != actual_output_hash:
        raise CoordinatorError(
            "reel_hash_conflict",
            "composition provenance output_sha256 does not match the real Reel SHA-256",
        )


def _normalize_packet_for_comparison(markdown: str) -> str:
    return re.sub(r"(?m)^\*\*Prepared:\*\* .*?$", "**Prepared:** <tolerated-date-line>", markdown)


def _assert_no_strategy_fields(value: Any, location: str) -> None:
    if isinstance(value, dict):
        unexpected = STRATEGY_FIELDS.intersection(value)
        if unexpected:
            raise CoordinatorError(
                "invented_strategy_metadata",
                f"{location} unexpectedly contains unwired strategy fields: {sorted(unexpected)}",
            )
        for key, child in value.items():
            _assert_no_strategy_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_strategy_fields(child, f"{location}[{index}]")


@contextmanager
def _local_music_manifest(path: Optional[Path]) -> Iterator[None]:
    if path is None:
        yield
        return
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise CoordinatorError("missing_music_manifest", f"local music manifest does not exist: {resolved}")
    original = music_pool_tools.DEFAULT_MANIFEST_PATH
    music_pool_tools.DEFAULT_MANIFEST_PATH = resolved
    try:
        yield
    finally:
        music_pool_tools.DEFAULT_MANIFEST_PATH = original


def _existing_packet_matches(path: Path, expected: str) -> bool:
    return _normalize_packet_for_comparison(path.read_text(encoding="utf-8")) == _normalize_packet_for_comparison(expected)


def _assert_writable_paths_are_not_live_queue(*paths: Path) -> None:
    live_queue = packet_tools.LIVE_QUEUE_ROOT.resolve()
    for path in (candidate.resolve() for candidate in paths):
        if path == live_queue or live_queue in path.parents:
            raise CoordinatorError(
                "live_queue_path_forbidden",
                f"coordinator output path may not be inside the live queue: {path}",
            )


def coordinate_derived_shortform_reel(
    date_str: str,
    source_slot: str,
    reel_slot: str,
    *,
    apply_local: bool = False,
    out_dir: Optional[Path] = None,
    music_manifest: Optional[Path] = None,
) -> Dict[str, Any]:
    result = _result_template(apply_local=apply_local)
    try:
        source_slot = _validate_identity("source_slot", source_slot)
        reel_slot = _validate_identity("reel_slot", reel_slot)
        if source_slot == reel_slot:
            raise CoordinatorError(
                "reel_identity_not_distinct",
                "the explicit Reel identity must be distinct from the source identity",
            )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date_str or "")):
            raise CoordinatorError("invalid_date", "date must use YYYY-MM-DD format")

        package_root = out_dir.resolve() if out_dir is not None else None
        try:
            source = packet_tools.resolve_packet_inputs_higgsfield(date_str, source_slot, package_root)
        except packet_tools.ResolveError as exc:
            raise CoordinatorError(_classify_source_error(exc), str(exc)) from exc
        if source.get("slot_id") != source_slot:
            raise CoordinatorError("ambiguous_source_evidence", "resolved source identity does not match the requested source slot")
        if source.get("qa_overall") != "pass":
            raise CoordinatorError("failed_qa", "source QA overall is not pass")
        if source.get("qa_publish_ready") is not True:
            raise CoordinatorError("incomplete_qa", "source QA is not completed as publish_ready=true")

        source_path = Path(str(source["image_path"])).resolve()
        if not source_path.exists() or not source_path.is_file():
            raise CoordinatorError("missing_source_evidence", f"resolved source asset does not exist: {source_path}")
        source_sha256 = _sha256_file(source_path)
        debug = source.get("debug_artifacts") or {}
        manifest_path = Path(str(debug.get("higgsfield_manifest_path") or ""))
        if not manifest_path.exists() or not manifest_path.is_file():
            raise CoordinatorError("missing_source_evidence", f"resolved Higgsfield manifest does not exist: {manifest_path}")

        result["source_provenance"] = {
            "date": date_str,
            "source_slot_id": source_slot,
            "source_image_path": str(source_path),
            "source_image_sha256": source_sha256,
            "source_manifest_path": str(manifest_path.resolve()),
            "source_manifest_sha256": _sha256_file(manifest_path),
            "qa_path": source.get("qa_path"),
            "qa_overall": source.get("qa_overall"),
            "qa_publish_ready": source.get("qa_publish_ready"),
            "provider_job_id": debug.get("provider_job_id"),
            "custom_reference_id": source.get("custom_reference_id"),
            "lane": source.get("lane"),
            "activity": source.get("activity"),
            "pose": source.get("pose"),
            "visual_style": source.get("visual_style"),
        }
        _assert_no_strategy_fields(result["source_provenance"], "source_provenance")
        result["stage_results"].append({"stage": "source_inspection", "status": "passed"})

        video_path = reel_tools.resolve_story_video_path(source_path).resolve()
        provenance_path = _composition_provenance_path(video_path)
        packet_path = packet_tools.resolve_packet_output_path(date_str, reel_slot, package_root)
        draft_path = packet_tools.resolve_queue_draft_output_path(date_str, reel_slot, package_root)
        _assert_writable_paths_are_not_live_queue(
            video_path,
            provenance_path,
            packet_path,
            draft_path,
        )

        video_exists = video_path.exists()
        provenance_exists = provenance_path.exists()
        if video_exists != provenance_exists:
            if video_exists:
                raise CoordinatorError("orphaned_reel", f"Reel exists without composition provenance: {video_path}")
            raise CoordinatorError(
                "orphaned_composition_provenance",
                f"composition provenance exists without its Reel: {provenance_path}",
            )
        if not video_exists and packet_path.exists():
            raise CoordinatorError(
                "conflicting_packet",
                f"packet exists before its required Reel/provenance pair: {packet_path}",
            )
        if not video_exists and draft_path.exists():
            raise CoordinatorError(
                "conflicting_draft",
                f"draft exists before its required Reel/provenance pair: {draft_path}",
            )

        initially_missing = []
        if not video_exists:
            initially_missing.extend([str(video_path), str(provenance_path)])
        if not packet_path.exists():
            initially_missing.append(str(packet_path))
        if not draft_path.exists():
            initially_missing.append(str(draft_path))
        result["files_would_write"] = initially_missing

        if not video_exists and not apply_local:
            result["ok"] = True
            result["state"] = "ready_for_local_composition"
            result["stage_results"].append({"stage": "reel_composition", "status": "would_prepare"})
            return result

        with _local_music_manifest(music_manifest):
            if not video_exists:
                try:
                    prepared = reel_tools.build_story_video(
                        source_path,
                        reel_slot,
                        output_path=None,
                        force=False,
                        manifest_path=music_manifest.resolve() if music_manifest is not None else None,
                    )
                except reel_tools.StoryVideoError as exc:
                    raise CoordinatorError("local_composition_failed", str(exc)) from exc
                result["files_written_this_run"].extend(
                    [str(Path(prepared["output_path"])), str(Path(prepared["provenance_path"]))]
                )
                result["stage_results"].append({"stage": "reel_composition", "status": "reel_prepared"})
            else:
                result["stage_results"].append({"stage": "reel_composition", "status": "reused"})

            if not video_path.exists() or not provenance_path.exists():
                raise CoordinatorError("local_composition_failed", "local composer did not produce the expected Reel/provenance pair")
            provenance = _load_composition_provenance(provenance_path)
            _validate_composition_binding(
                provenance,
                source_path=source_path,
                source_sha256=source_sha256,
                reel_slot=reel_slot,
                video_path=video_path,
            )
            try:
                reel_facts = reel_tools.validate_music_backed_shortform_asset(
                    video_path,
                    manifest_path=music_manifest.resolve() if music_manifest is not None else None,
                )
            except reel_tools.StoryVideoError as exc:
                raise CoordinatorError("reel_validation_failed", str(exc)) from exc

            result["reel_provenance"] = {
                "reel_slot_id": reel_slot,
                "reel_path": str(video_path),
                "reel_sha256": reel_facts["video_sha256"],
                "composition_provenance_path": str(provenance_path),
                "composition_provenance_sha256": _sha256_file(provenance_path),
                "source_image_path": str(source_path),
                "source_image_sha256": source_sha256,
                "selected_track_id": reel_facts["track_id"],
                "selected_track_sha256": reel_facts["track_sha256"],
                "duration_seconds": reel_facts["duration_seconds"],
                "video_codec": reel_facts["video_codec"],
                "audio_codec": reel_facts["audio_codec"],
                "width": reel_facts["width"],
                "height": reel_facts["height"],
            }
            result["stage_results"].append({"stage": "reel_validation", "status": "passed"})

            try:
                resolved = packet_tools.resolve_packet_inputs_higgsfield_derived_shortform(
                    date_str,
                    source_slot,
                    package_root,
                    output_slot_id=reel_slot,
                )
            except packet_tools.ResolveError as exc:
                raise CoordinatorError("derived_resolution_failed", str(exc)) from exc

        if resolved.get("slot_id") != reel_slot or resolved.get("source_slot_id") != source_slot:
            raise CoordinatorError("package_identity_conflict", "derived resolver returned mismatched source or Reel identity")
        if resolved.get("source_image_sha256") != source_sha256:
            raise CoordinatorError("source_hash_conflict", "derived resolver returned a conflicting source SHA-256")
        if resolved.get("prepared_video_sha256") != reel_facts["video_sha256"]:
            raise CoordinatorError("reel_hash_conflict", "derived resolver returned a conflicting Reel SHA-256")
        _assert_no_strategy_fields(resolved, "derived_resolver")

        expected_packet = packet_tools.build_packet_markdown(resolved)
        expected_draft = packet_tools.build_queue_draft(resolved, packet_path)
        _assert_no_strategy_fields(expected_draft, "queue_draft")
        if expected_draft.get("approved_for_live_publish") is not False:
            raise CoordinatorError("unsafe_package", "derived draft is unexpectedly approved for live publish")
        if expected_draft.get("operator_review_required") is not True:
            raise CoordinatorError("unsafe_package", "derived draft does not require operator review")
        if (expected_draft.get("metadata") or {}).get("queue_draft_only") is not True:
            raise CoordinatorError("unsafe_package", "derived draft is not queue_draft_only")

        packet_exists = packet_path.exists()
        draft_exists = draft_path.exists()
        if packet_exists and not _existing_packet_matches(packet_path, expected_packet):
            raise CoordinatorError("conflicting_packet", f"existing packet conflicts with expected content: {packet_path}")
        if draft_exists:
            existing_draft = _load_json_object(draft_path, "draft")
            if existing_draft != expected_draft:
                raise CoordinatorError("conflicting_draft", f"existing draft conflicts with expected content: {draft_path}")

        result["package_provenance"] = {
            "reel_slot_id": reel_slot,
            "source_slot_id": source_slot,
            "packet_path": str(packet_path),
            "queue_draft_path": str(draft_path),
            "packet_status": "matching_existing" if packet_exists else "missing",
            "draft_status": "matching_existing" if draft_exists else "missing",
            "packet_sha256": _sha256_file(packet_path) if packet_exists else None,
            "queue_draft_sha256": _sha256_file(draft_path) if draft_exists else None,
            "media_kind": resolved.get("media_kind"),
            "media_type": expected_draft.get("media_type"),
            "media_path": expected_draft.get("media_path"),
            "draft_post_id": expected_draft.get("post_id"),
            "draft_slot_id": expected_draft.get("slot_id"),
            "source_image_sha256": resolved.get("source_image_sha256"),
            "reel_sha256": resolved.get("prepared_video_sha256"),
            "selected_track_id": resolved.get("selected_track_id"),
            "selected_track_sha256": resolved.get("selected_track_sha256"),
            "composition_provenance_path": resolved.get("prepared_video_provenance_path"),
            "approved_for_live_publish": expected_draft.get("approved_for_live_publish"),
            "operator_review_required": expected_draft.get("operator_review_required"),
            "queue_draft_only": (expected_draft.get("metadata") or {}).get("queue_draft_only"),
        }

        if not apply_local:
            result["ok"] = True
            result["state"] = "ready_for_human_review" if packet_exists and draft_exists else "reel_prepared"
            result["stage_results"].append(
                {"stage": "package", "status": "reused" if packet_exists and draft_exists else "would_prepare"}
            )
            return result

        # Validate both existing artifacts before writing either missing one.
        if not packet_exists:
            try:
                written_packet = packet_tools.write_packet(resolved, package_root, force=False)
            except packet_tools.PacketWriteError as exc:
                raise CoordinatorError("packet_write_failed", str(exc)) from exc
            result["files_written_this_run"].append(str(written_packet))
        if not draft_exists:
            try:
                written_draft = packet_tools.write_queue_draft(
                    resolved,
                    packet_path,
                    package_root,
                    force=False,
                )
            except (
                packet_tools.QueueDraftWriteError,
                packet_tools.QueueDraftGuardError,
            ) as exc:
                raise CoordinatorError("draft_write_failed", str(exc)) from exc
            result["files_written_this_run"].append(str(written_draft))

        if not _existing_packet_matches(packet_path, expected_packet):
            raise CoordinatorError("conflicting_packet", "written packet does not match expected content")
        if _load_json_object(draft_path, "draft") != expected_draft:
            raise CoordinatorError("conflicting_draft", "written draft does not match expected content")

        result["package_provenance"]["packet_status"] = "prepared" if not packet_exists else "matching_existing"
        result["package_provenance"]["draft_status"] = "prepared" if not draft_exists else "matching_existing"
        result["package_provenance"]["packet_sha256"] = _sha256_file(packet_path)
        result["package_provenance"]["queue_draft_sha256"] = _sha256_file(draft_path)
        result["ok"] = True
        result["state"] = "ready_for_human_review"
        result["stage_results"].append({"stage": "package", "status": "package_prepared"})
        return result
    except CoordinatorError as exc:
        return _block(result, exc.code, exc.reason)
    except Exception as exc:  # Fail closed without exposing a partial success state.
        return _block(result, "unexpected_local_error", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or locally prepare one static-photo-plus-music Lena Reel. "
            "Defaults to inspect-only and always stops before human approval."
        )
    )
    parser.add_argument("--date", required=True, help="Source date in YYYY-MM-DD format")
    parser.add_argument("--source-slot", required=True, help="Explicit Higgsfield source-photo identity")
    parser.add_argument("--reel-slot", required=True, help="Explicit, distinct derived Reel identity")
    parser.add_argument("--apply-local", action="store_true", help="Allow local composition and package/draft writes")
    parser.add_argument("--out-dir", default=None, help="Optional local scratch or publish-packet root")
    parser.add_argument("--music-manifest", default=None, help="Optional local approved-music manifest")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve() if args.out_dir else None
    music_manifest = Path(args.music_manifest).resolve() if args.music_manifest else None
    result = coordinate_derived_shortform_reel(
        args.date,
        args.source_slot,
        args.reel_slot,
        apply_local=args.apply_local,
        out_dir=out_dir,
        music_manifest=music_manifest,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
