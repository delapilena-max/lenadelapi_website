from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipeline.qa import lena_photo_qa
from tools import lena_higgsfield_generation_approval_v1 as approval
from tools.strategy import lena_build_content_packet_dryrun_v1 as packet_builder


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
DEFAULT_APPROVAL_ROOT = ROOT / "pipeline" / "approvals" / "lena" / "generation"
DEFAULT_CANDIDATE_ROOT = ROOT / "pipeline" / "strategy" / "lena" / "pre_generation_candidates"
DEFAULT_REPORTS_ROOT = ROOT / "pipeline" / "autonomy" / "lena" / "dry_run_cycles"
DEFAULT_MANIFEST_ROOT = ROOT / "pipeline" / "higgsfield_debug"
DEFAULT_IMAGE_ROOT = ROOT / "pipeline" / "higgsfield_library" / "lena"
DEFAULT_QA_ROOT = ROOT / "pipeline" / "asset_review" / "lena" / "hpe_closure" / "presence_output_qa"
DEFAULT_PACKET_ROOT = Path(packet_builder.OUTPUT_BASE)

AUTONOMOUS_STAGES = (
    "approved_candidate_resolution",
    "generation_result_intake",
    "caption_package_creation",
)
MANUAL_STAGES = (
    "image_qa_validation",
)


class LenaGenerationQaPackageDryRunError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_stamp() -> str:
    return datetime.now().strftime("%H%M%S")


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise LenaGenerationQaPackageDryRunError(code, detail)


def _ensure_path_within_root(
    path: Path,
    root: Path,
    *,
    code: str,
    label: str,
    must_exist: bool,
) -> Path:
    root_resolved = root.resolve(strict=False)
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(root_resolved):
        raise LenaGenerationQaPackageDryRunError(
            code,
            f"resolved {label} escapes declared root: {resolved} (root: {root_resolved})",
        )
    if must_exist and not resolved.exists():
        raise LenaGenerationQaPackageDryRunError(code, f"{label} does not exist: {resolved}")
    return resolved


def _read_json_object(path: Path, *, code: str, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise LenaGenerationQaPackageDryRunError(code, f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LenaGenerationQaPackageDryRunError(code, f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LenaGenerationQaPackageDryRunError(code, f"{label} must be a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise LenaGenerationQaPackageDryRunError("artifact_already_exists", f"refusing to overwrite existing artifact: {path}")
    temp_path = path.with_name(f"{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _validate_iso_date(raw_date: str) -> str:
    try:
        return date.fromisoformat(raw_date).isoformat()
    except ValueError as exc:
        raise LenaGenerationQaPackageDryRunError("invalid_date", f"invalid --date value {raw_date!r}: expected YYYY-MM-DD") from exc


def _report_path(day: str, stamp: str, report_root: Path = DEFAULT_REPORTS_ROOT) -> Path:
    return report_root / day / f"lena_generation_qa_package_dry_run_{day}_{stamp}.json"


def _ensure_report_path_within_root(path: Path, report_root: Path = DEFAULT_REPORTS_ROOT) -> None:
    _ensure_path_within_root(
        path,
        report_root,
        code="report_path_escape",
        label="report output path",
        must_exist=False,
    )


def _manifest_path(manifest_root: Path, date_str: str, slot_id: str) -> Path:
    return manifest_root / date_str / slot_id / "lena_hpe_output_qa_manifest.json"


def _qa_path(qa_root: Path, date_str: str, slot_id: str) -> Path:
    return qa_root / date_str / slot_id / f"presence_qa_{slot_id}_00.json"


def _packet_output_path(packet_root: Path, date_str: str, recipe_id: str) -> Path:
    return packet_root / date_str / f"lena_content_packet_dryrun_{date_str}_{recipe_id}.json"


def resolve_approved_candidate(approval_artifact: Path) -> dict[str, Any]:
    approval_artifact = _ensure_path_within_root(
        approval_artifact,
        DEFAULT_APPROVAL_ROOT,
        code="approval_path_escape",
        label="approval artifact",
        must_exist=True,
    )
    try:
        approval_result = approval.validate_generation_approval_artifact(approval_artifact, require_not_expired=True)
    except approval.HiggsfieldGenerationApprovalError as exc:
        raise LenaGenerationQaPackageDryRunError(exc.code, exc.detail) from exc
    except SystemExit as exc:
        raise LenaGenerationQaPackageDryRunError("approval_validation_failed", str(exc)) from exc
    handoff_facts = approval_result["handoff_facts"]
    candidate = dict(handoff_facts["selected_candidate"])
    _require(bool(candidate.get("candidate_id")), "candidate_missing", "selected candidate is missing")
    candidate_path = _ensure_path_within_root(
        Path(str(handoff_facts["selected_candidate_path"])),
        DEFAULT_CANDIDATE_ROOT,
        code="candidate_path_escape",
        label="candidate artifact",
        must_exist=True,
    )
    selected_candidate_sha256 = str(handoff_facts["selected_candidate_sha256"])
    actual_candidate_sha256 = _sha256_file(candidate_path)
    _require(
        actual_candidate_sha256 == selected_candidate_sha256,
        "candidate_sha_mismatch",
        "selected candidate file SHA-256 does not match selected_candidate_sha256",
    )
    return {
        "approval_result": approval_result,
        "approval_path": approval_artifact.resolve(),
        "approval_sha256": _sha256_file(approval_artifact),
        "candidate": candidate,
        "candidate_path": candidate_path,
        "candidate_sha256": actual_candidate_sha256,
        "selected_candidate_sha256": selected_candidate_sha256,
        "date": str(handoff_facts["date"]),
        "slot_id": str(handoff_facts["slot_id"]),
        "prompt_sha256": str(handoff_facts["prompt_sha256"]),
        "authority_commit": str(candidate.get("authority_commit") or ""),
        "media_type": str(handoff_facts.get("slot_media_type") or "photo"),
        "handoff_path": Path(str(handoff_facts["handoff_path"])).resolve(),
        "handoff_sha256": str(handoff_facts["handoff_sha256"]),
    }


def intake_generation_result(
    *,
    manifest_path: Path,
    image_root: Path,
    expected_date: str,
    expected_slot_id: str,
    expected_prompt_sha256: str,
    expected_candidate_id: str,
    expected_candidate_sha256: str,
    expected_recipe_id: str,
    expected_authority_commit: str,
    expected_media_type: str,
) -> dict[str, Any]:
    manifest_path = _ensure_path_within_root(
        manifest_path,
        DEFAULT_MANIFEST_ROOT,
        code="manifest_path_escape",
        label="generation result manifest",
        must_exist=True,
    )
    manifest = _read_json_object(manifest_path, code="manifest_missing_or_invalid", label="generation result manifest")
    schema_version = str(manifest.get("schema_version") or "")
    outputs = manifest.get("outputs")
    if schema_version != "human_presence_output_qa_manifest_v1":
        raise LenaGenerationQaPackageDryRunError("manifest_schema_mismatch", "generation result manifest schema_version is invalid")
    _require(isinstance(outputs, list) and outputs, "manifest_outputs_missing", "generation result manifest outputs must be a non-empty list")
    expected_image_name = f"{expected_slot_id}_seed.png"
    _require(
        expected_image_name in {str(item) for item in outputs},
        "manifest_output_binding_mismatch",
        "generation result manifest outputs do not include the expected image filename",
    )
    expected_image_root = _ensure_path_within_root(
        image_root,
        DEFAULT_IMAGE_ROOT,
        code="image_root_escape",
        label="generated image root",
        must_exist=False,
    )
    image_path = expected_image_root / expected_date / expected_image_name
    image_path = _ensure_path_within_root(
        image_path,
        expected_image_root,
        code="generated_image_path_escape",
        label="generated image path",
        must_exist=True,
    )
    image_sha256 = _sha256_file(image_path)

    binding_report: dict[str, Any] = {
        "prompt_binding_verified": False,
        "verified_bindings": {
            "candidate_id": expected_candidate_id,
            "candidate_sha256": expected_candidate_sha256,
            "slot_id": expected_slot_id,
            "recipe_id": expected_recipe_id,
            "media_type": expected_media_type,
            "image_sha256": image_sha256,
        },
        "asserted_bindings": {
            "prompt_sha256": expected_prompt_sha256,
            "authority_commit": expected_authority_commit,
            "provider_job_id": None,
        },
        "unverified_bindings": [
            "generation_result_prompt_binding",
            "provider_job_id",
        ],
    }

    optional_binding_checks = {
        "prompt_sha256": expected_prompt_sha256,
        "authority_commit": expected_authority_commit,
        "candidate_id": expected_candidate_id,
        "slot_id": expected_slot_id,
        "recipe_id": expected_recipe_id,
        "media_type": expected_media_type,
        "candidate_sha256": expected_candidate_sha256,
        "image_sha256": image_sha256,
    }
    for field, expected in optional_binding_checks.items():
        if field not in manifest:
            continue
        observed = str(manifest.get(field) or "")
        _require(
            observed == str(expected),
            f"{field}_binding_mismatch",
            f"generation result manifest {field} does not match the expected binding",
        )
        binding_report["verified_bindings"][field] = observed
        if field == "prompt_sha256":
            binding_report["prompt_binding_verified"] = True
            binding_report["asserted_bindings"].pop("prompt_sha256", None)
            binding_report["unverified_bindings"] = [
                item for item in binding_report["unverified_bindings"] if item != "generation_result_prompt_binding"
            ]
        if field == "authority_commit":
            binding_report["asserted_bindings"].pop("authority_commit", None)
    provider_job_id = manifest.get("provider_job_id")
    if provider_job_id not in (None, ""):
        binding_report["verified_bindings"]["provider_job_id"] = str(provider_job_id)
        binding_report["asserted_bindings"].pop("provider_job_id", None)
        binding_report["unverified_bindings"] = [
            item for item in binding_report["unverified_bindings"] if item != "provider_job_id"
        ]
    return {
        "manifest_path": manifest_path.resolve(),
        "manifest_sha256": _sha256_file(manifest_path),
        "manifest": manifest,
        "image_path": image_path.resolve(),
        "image_sha256": image_sha256,
        "expected_slot_id": expected_slot_id,
        "expected_prompt_sha256": expected_prompt_sha256,
        "binding_report": binding_report,
    }


def validate_photo_qa_artifact(
    *,
    qa_artifact_path: Path,
    expected_slot_id: str,
    expected_date: str,
) -> dict[str, Any]:
    qa_artifact_path = _ensure_path_within_root(
        qa_artifact_path,
        DEFAULT_QA_ROOT,
        code="qa_path_escape",
        label="photo QA artifact",
        must_exist=True,
    )
    artifact = _read_json_object(qa_artifact_path, code="qa_artifact_missing_or_invalid", label="photo QA artifact")
    _require(str(artifact.get("slot_id") or "") == expected_slot_id, "qa_slot_mismatch", "photo QA artifact slot_id does not match the approval lineage")
    _require(str(artifact.get("date") or "") == expected_date, "qa_date_mismatch", "photo QA artifact date does not match the approval lineage")
    valid, errors = lena_photo_qa.validate_qa_result(artifact)
    _require(valid, "qa_validation_failed", "; ".join(errors))
    styling = artifact.get("production_scoring", {}).get("styling_sexy_platform_safe", {})
    _require(
        isinstance(styling, dict) and styling.get("status") == "pass",
        "qa_safety_failed",
        "photo QA artifact must keep styling_sexy_platform_safe passing",
    )
    _require(str(artifact.get("overall") or "") == "pass", "qa_not_passed", "photo QA artifact must pass before packaging")
    return {
        "qa_artifact_path": qa_artifact_path.resolve(),
        "qa_artifact_sha256": _sha256_file(qa_artifact_path),
        "qa_artifact": artifact,
        "validation_passed": True,
    }


def _select_recipe_and_hook(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    recipe_bank = packet_builder.load_json(Path(packet_builder.RECIPE_BANK))
    hook_bank = packet_builder.load_json(Path(packet_builder.HOOK_BANK))
    recipe_id = str(candidate.get("recipe_id") or "")
    hook_id = str(candidate.get("hook_id") or "")
    recipe = next((item for item in recipe_bank["recipes"] if item.get("id") == recipe_id), None)
    hook = next((item for item in hook_bank["hooks"] if item.get("id") == hook_id), None)
    if recipe is None:
        raise LenaGenerationQaPackageDryRunError("recipe_missing", f"recipe {recipe_id!r} not found")
    if hook is None:
        raise LenaGenerationQaPackageDryRunError("hook_missing", f"hook {hook_id!r} not found")
    return recipe, hook


def build_caption_package(
    *,
    approval_context: dict[str, Any],
    qa_context: dict[str, Any],
    packet_root: Path = DEFAULT_PACKET_ROOT,
) -> dict[str, Any]:
    candidate = approval_context["candidate"]
    recipe, hook = _select_recipe_and_hook(candidate)
    try:
        packet = packet_builder.build_packet(
            recipe,
            hook,
            "approval-bound dry-run package",
            approval_context["date"],
        )
    except SystemExit as exc:
        raise LenaGenerationQaPackageDryRunError("packet_build_failed", str(exc)) from exc
    packet_path = _packet_output_path(packet_root, approval_context["date"], candidate["recipe_id"])
    packet_path = _ensure_path_within_root(
        packet_path,
        packet_root,
        code="packet_path_escape",
        label="packet output path",
        must_exist=False,
    )
    _require(not packet_path.exists(), "packet_already_exists", f"refusing to overwrite existing package artifact: {packet_path}")
    try:
        flags, errors = packet_builder.validate_packet(packet, str(packet_path))
    except SystemExit as exc:
        raise LenaGenerationQaPackageDryRunError("packet_validation_failed", str(exc)) from exc
    _require(flags["all_checks_passed"], "packet_validation_failed", "; ".join(errors))
    _write_json_atomic(packet_path, packet)
    packet_sha256 = _sha256_file(packet_path)
    return {
        "packet_path": packet_path.resolve(),
        "packet_sha256": packet_sha256,
        "packet": packet,
        "validation_flags": flags,
    }


def _self_command(args: argparse.Namespace) -> str:
    cmd = [PY, str(Path(__file__).resolve()), "--date", args.date, "--approval-artifact", str(args.approval_artifact), "--qa-artifact", str(args.qa_artifact)]
    if args.manifest_artifact:
        cmd.extend(["--manifest-artifact", str(args.manifest_artifact)])
    return subprocess.list2cmdline(cmd)


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    args.date = _validate_iso_date(args.date)
    started_at = now_iso()
    stamp = now_stamp()
    output_path = _report_path(args.date, stamp, args.report_root)
    _ensure_report_path_within_root(output_path, args.report_root)
    if output_path.exists():
        raise LenaGenerationQaPackageDryRunError("report_already_exists", f"dry-run cycle report already exists: {output_path}")

    stages: list[dict[str, Any]] = []
    lineage: dict[str, Any] = {
        "verified_lineage": {},
        "asserted_lineage": {},
        "unverified_bindings": [],
        "prompt_binding_verified": False,
    }
    current_stage = "approved_candidate_resolution"
    try:
        approval_context = resolve_approved_candidate(args.approval_artifact)
        lineage["verified_lineage"].update(
            {
                "approval_artifact_path": str(approval_context["approval_path"]),
                "approval_artifact_sha256": approval_context["approval_sha256"],
                "candidate_artifact_path": str(approval_context["candidate_path"]),
                "candidate_artifact_sha256_expected": approval_context["selected_candidate_sha256"],
                "candidate_artifact_sha256_actual": approval_context["candidate_sha256"],
                "candidate_id": approval_context["candidate"]["candidate_id"],
                "slot_id": approval_context["slot_id"],
                "recipe_id": approval_context["candidate"]["recipe_id"],
                "media_type": approval_context["media_type"],
            }
        )
        lineage["asserted_lineage"].update(
            {
                "prompt_sha256": approval_context["prompt_sha256"],
                "authority_commit": approval_context["authority_commit"],
                "provider_job_id": None,
            }
        )
        lineage["unverified_bindings"].extend(["generation_result_prompt_binding", "provider_job_id"])
        stages.append(
            {
                "stage": "approved_candidate_resolution",
                "status": "pass",
                "mode": "autonomous",
                "approval_artifact": str(approval_context["approval_path"]),
                "approval_sha256": approval_context["approval_sha256"],
                "candidate_path": str(approval_context["candidate_path"]),
                "candidate_sha256": approval_context["candidate_sha256"],
                "slot_id": approval_context["slot_id"],
                "recipe_id": approval_context["candidate"]["recipe_id"],
                "prompt_sha256": approval_context["prompt_sha256"],
            }
        )

        current_stage = "generation_result_intake"
        manifest_path = args.manifest_artifact or _manifest_path(args.manifest_root, approval_context["date"], approval_context["slot_id"])
        generation_context = intake_generation_result(
            manifest_path=manifest_path,
            image_root=args.image_root,
            expected_date=approval_context["date"],
            expected_slot_id=approval_context["slot_id"],
            expected_prompt_sha256=approval_context["prompt_sha256"],
            expected_candidate_id=approval_context["candidate"]["candidate_id"],
            expected_candidate_sha256=approval_context["candidate_sha256"],
            expected_recipe_id=approval_context["candidate"]["recipe_id"],
            expected_authority_commit=approval_context["authority_commit"],
            expected_media_type=approval_context["media_type"],
        )
        lineage["verified_lineage"].update(
            {
                "manifest_artifact_path": str(generation_context["manifest_path"]),
                "manifest_artifact_sha256": generation_context["manifest_sha256"],
                "image_artifact_path": str(generation_context["image_path"]),
                "image_artifact_sha256": generation_context["image_sha256"],
            }
        )
        binding_report = generation_context["binding_report"]
        lineage["prompt_binding_verified"] = bool(binding_report["prompt_binding_verified"])
        if binding_report["prompt_binding_verified"]:
            lineage["verified_lineage"]["prompt_sha256"] = binding_report["verified_bindings"]["prompt_sha256"]
            lineage["asserted_lineage"].pop("prompt_sha256", None)
            lineage["unverified_bindings"] = [item for item in lineage["unverified_bindings"] if item != "generation_result_prompt_binding"]
        if binding_report["verified_bindings"].get("authority_commit"):
            lineage["verified_lineage"]["authority_commit"] = binding_report["verified_bindings"]["authority_commit"]
            lineage["asserted_lineage"].pop("authority_commit", None)
        if binding_report["verified_bindings"].get("provider_job_id"):
            lineage["verified_lineage"]["provider_job_id"] = binding_report["verified_bindings"]["provider_job_id"]
            lineage["asserted_lineage"].pop("provider_job_id", None)
        stages.append(
            {
                "stage": "generation_result_intake",
                "status": "pass",
                "mode": "autonomous",
                "manifest_path": str(generation_context["manifest_path"]),
                "manifest_sha256": generation_context["manifest_sha256"],
                "image_path": str(generation_context["image_path"]),
                "image_sha256": generation_context["image_sha256"],
                "provider_calls_performed": 0,
                "publish_calls_performed": 0,
            }
        )

        current_stage = "image_qa_validation"
        qa_context = validate_photo_qa_artifact(
            qa_artifact_path=args.qa_artifact,
            expected_slot_id=approval_context["slot_id"],
            expected_date=approval_context["date"],
        )
        qa_context_binding = {
            "qa_artifact_path": str(qa_context["qa_artifact_path"]),
            "qa_artifact_sha256": qa_context["qa_artifact_sha256"],
        }
        lineage["verified_lineage"].update(qa_context_binding)
        stages.append(
            {
                "stage": "image_qa_validation",
                "status": "pass",
                "mode": "manual_or_fixture_bound",
                "qa_artifact_path": str(qa_context["qa_artifact_path"]),
                "qa_artifact_sha256": qa_context["qa_artifact_sha256"],
                "qa_overall": qa_context["qa_artifact"].get("overall"),
                "styling_sexy_platform_safe": qa_context["qa_artifact"].get("production_scoring", {}).get("styling_sexy_platform_safe", {}).get("status"),
            }
        )

        current_stage = "caption_package_creation"
        packet_context = build_caption_package(
            approval_context=approval_context,
            qa_context=qa_context,
            packet_root=args.packet_root,
        )
        lineage["verified_lineage"].update(
            {
                "packet_artifact_path": str(packet_context["packet_path"]),
                "packet_artifact_sha256": packet_context["packet_sha256"],
            }
        )
        stages.append(
            {
                "stage": "caption_package_creation",
                "status": "pass",
                "mode": "autonomous",
                "packet_path": str(packet_context["packet_path"]),
                "packet_sha256": packet_context["packet_sha256"],
                "caption_draft": packet_context["packet"].get("caption_draft", ""),
                "compact_provider_prompt_sha256": packet_context["packet"].get("compact_provider_prompt_sha256", ""),
            }
        )

        return {
            "ok": True,
            "version": "v1",
            "report_type": "lena_generation_qa_package_dry_run_cycle",
            "date": args.date,
            "started_at": started_at,
            "finished_at": now_iso(),
            "dry_run_command": _self_command(args),
            "report_path": str(output_path),
            "publishing_authorized": False,
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "retries_performed": 0,
            "prompt_binding_verified": lineage["prompt_binding_verified"],
            "verified_lineage": lineage["verified_lineage"],
            "asserted_lineage": lineage["asserted_lineage"],
            "unverified_bindings": lineage["unverified_bindings"],
            "approval_artifact": str(approval_context["approval_path"]),
            "approval_sha256": approval_context["approval_sha256"],
            "candidate_path": str(approval_context["candidate_path"]),
            "candidate_sha256": approval_context["candidate_sha256"],
            "candidate_sha256_expected": approval_context["selected_candidate_sha256"],
            "candidate_id": approval_context["candidate"]["candidate_id"],
            "slot_id": approval_context["slot_id"],
            "prompt_sha256": approval_context["prompt_sha256"],
            "manifest_path": str(generation_context["manifest_path"]),
            "manifest_sha256": generation_context["manifest_sha256"],
            "image_path": str(generation_context["image_path"]),
            "image_sha256": generation_context["image_sha256"],
            "qa_artifact": str(qa_context["qa_artifact_path"]),
            "qa_artifact_sha256": qa_context["qa_artifact_sha256"],
            "packet_path": str(packet_context["packet_path"]),
            "packet_sha256": packet_context["packet_sha256"],
            "safeguards": {
                "provider_calls_performed": 0,
                "publish_calls_performed": 0,
                "publishing_authorized": False,
                "retries_performed": 0,
                "retry_cap": 0,
                "hard_spend_cap_usd": 0,
                "duplicate_rejection": "report_path_must_not_exist_and_packet_path_must_not_exist",
                "kill_switch": "no_live_command_paths",
                "fail_closed_stage_handling": True,
                "receipt_creation": "wrapper_report_json",
                "recurring_scheduler": False,
            },
            "autonomous_stages": list(AUTONOMOUS_STAGES),
            "manual_stages": list(MANUAL_STAGES),
            "stages": stages,
            "audited_paths": {
                "approval_artifact": str(approval_context["approval_path"]),
                "generation_result_manifest": str(generation_context["manifest_path"]),
                "qa_artifact": str(qa_context["qa_artifact_path"]),
                "packet_artifact": str(packet_context["packet_path"]),
            },
        }
    except LenaGenerationQaPackageDryRunError as exc:
        return {
            "ok": False,
            "version": "v1",
            "report_type": "lena_generation_qa_package_dry_run_cycle",
            "date": args.date,
            "started_at": started_at,
            "finished_at": now_iso(),
            "dry_run_command": _self_command(args),
            "report_path": str(output_path),
            "failed_stage": current_stage,
            "error": {"code": exc.code, "detail": exc.detail},
            "publishing_authorized": False,
            "provider_calls_performed": 0,
            "publish_calls_performed": 0,
            "retries_performed": 0,
            "prompt_binding_verified": lineage["prompt_binding_verified"],
            "verified_lineage": lineage["verified_lineage"],
            "asserted_lineage": lineage["asserted_lineage"],
            "unverified_bindings": lineage["unverified_bindings"],
            "safeguards": {
                "provider_calls_performed": 0,
                "publish_calls_performed": 0,
                "publishing_authorized": False,
                "retries_performed": 0,
                "retry_cap": 0,
                "hard_spend_cap_usd": 0,
                "duplicate_rejection": "report_path_must_not_exist_and_packet_path_must_not_exist",
                "kill_switch": "no_live_command_paths",
                "fail_closed_stage_handling": True,
                "receipt_creation": "wrapper_report_json",
                "recurring_scheduler": False,
            },
            "autonomous_stages": list(AUTONOMOUS_STAGES),
            "manual_stages": list(MANUAL_STAGES),
            "stages": stages,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Lena generation -> QA -> package dry-run wrapper.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--approval-artifact", type=Path, required=True)
    parser.add_argument("--qa-artifact", type=Path, required=True)
    parser.add_argument("--manifest-artifact", type=Path)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    parser.add_argument("--manifest-root", type=Path, default=DEFAULT_MANIFEST_ROOT)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--qa-root", type=Path, default=DEFAULT_QA_ROOT)
    parser.add_argument("--packet-root", type=Path, default=DEFAULT_PACKET_ROOT)
    args = parser.parse_args()

    report = run_cycle(args)
    report_path = Path(report["report_path"])
    _ensure_report_path_within_root(report_path, args.report_root)
    _write_json_atomic(report_path, report)
    print(json.dumps({"ok": report["ok"], "report_path": str(report_path), "failed_stage": report.get("failed_stage", "")}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
