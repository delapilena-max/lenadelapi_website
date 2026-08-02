from __future__ import annotations

from pathlib import Path

from pipeline.media_properties.lena.video.compiler import compile_video
from pipeline.media_properties.lena.video.contracts import (
    Issue,
    LenaVideoContractError,
    atomic_write_json,
    canonical_sha256,
    zero_activity_counters,
)
from tools.lena_video_cli_support_v1 import (
    JsonArgumentParser,
    emit,
    emit_contract_error,
    emit_filesystem_error,
    help_report,
)


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        prog="python -m tools.lena_video_compile_higgsfield_v1",
        description=(
            "Deterministically compile validated Lena video JSON into a "
            "provider-neutral plan and execution-disabled Higgsfield request."
        ),
    )
    parser.add_argument(
        "--video-root",
        type=Path,
        help="Directory containing the nine governed source artifacts.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Explicit existing output directory. Omit for an in-memory no-write compile.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Compile and validate in memory without writing output.",
    )
    return parser


def _safe_output_directory(output: Path) -> Path:
    source = output.absolute()
    is_junction = getattr(source, "is_junction", lambda: False)
    if source.is_symlink() or is_junction():
        raise LenaVideoContractError(
            Issue(
                code="output_directory_unsafe",
                stage="write",
                message="Output must be an existing real directory, not a symlink or junction.",
                source_file=str(output),
            )
        )
    resolved = source.resolve(strict=True)
    if not resolved.is_dir():
        raise LenaVideoContractError(
            Issue(
                code="output_directory_unsafe",
                stage="write",
                message="Output must be an existing real directory.",
                source_file=str(output),
            )
        )
    return resolved


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
        if args.json_help:
            return emit(help_report(parser, parser.prog))
        if args.video_root is None:
            parser.error("--video-root is required")
        plan, compiled = compile_video(args.video_root)
        writes: list[dict[str, str]] = []
        if args.output is not None and not args.validate_only:
            output = _safe_output_directory(args.output)
            for filename, value in (
                ("lena_video_generation_plan_v1.json", plan),
                ("lena_higgsfield_compiled_request_v1.json", compiled),
            ):
                path = output / filename
                writes.append(
                    {"path": str(path), "result": atomic_write_json(path, value)}
                )
        return emit(
            {
                "ok": True,
                "report_type": "lena_video_higgsfield_compilation_v1",
                "validate_only": bool(args.validate_only),
                "write_requested": args.output is not None,
                "writes": writes,
                "generation_plan_sha256": canonical_sha256(plan),
                "compiled_request_sha256": canonical_sha256(compiled),
                "deterministic_compilation_fingerprint": compiled[
                    "deterministic_compilation_fingerprint"
                ],
                "character_element_token": compiled["character_element_token"],
                "prompt_char_count": compiled["prompt_char_count"],
                "prompt_char_budget": compiled["prompt_char_budget"],
                "prompt_char_headroom": (
                    compiled["prompt_char_budget"] - compiled["prompt_char_count"]
                ),
                "duration_ms": compiled["duration_ms"],
                "resolution": compiled["resolution"],
                "aspect_ratio": compiled["aspect_ratio"],
                "cost_ceiling_credits": compiled["cost_ceiling_credits"],
                "attempt_authority": compiled["attempt_authority"],
                "execution_authorized": compiled["execution_authorized"],
                "counters": zero_activity_counters(),
            }
        )
    except LenaVideoContractError as exc:
        return emit_contract_error("lena_video_higgsfield_compilation_v1", exc)
    except OSError as exc:
        return emit_filesystem_error("lena_video_higgsfield_compilation_v1", exc)


if __name__ == "__main__":
    raise SystemExit(main())
