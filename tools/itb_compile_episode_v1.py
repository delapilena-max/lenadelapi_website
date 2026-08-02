from __future__ import annotations

from pathlib import Path

from pipeline.media_properties.interstitial_travel_bureau.compilers import compile_episode
from pipeline.media_properties.interstitial_travel_bureau.contracts import (
    ITBContractError,
    Issue,
    atomic_write_json,
    canonical_sha256,
    zero_activity_counters,
)
from tools.itb_cli_support_v1 import JsonArgumentParser, emit, emit_contract_error, help_report


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="python -m tools.itb_compile_episode_v1", description="Deterministically compile validated ITB JSON into a neutral plan and disabled request package.")
    parser.add_argument("--episode-root", type=Path, help="Directory containing validated upstream episode artifacts.")
    parser.add_argument("--output", type=Path, help="Explicit existing output directory. Omit for an in-memory no-write compile.")
    parser.add_argument("--validate-only", action="store_true", help="Compile and validate in memory without writing output.")
    return parser


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
        if args.json_help:
            return emit(help_report(parser, parser.prog))
        if args.episode_root is None:
            parser.error("--episode-root is required")
        plan, compiled = compile_episode(args.episode_root)
        writes = []
        if args.output is not None and not args.validate_only:
            output = args.output.resolve(strict=True)
            if not output.is_dir() or output.is_symlink():
                raise ITBContractError(Issue(code="output_directory_unsafe", stage="write", message="Output must be an existing real directory.", source_file=str(args.output)))
            writes = [
                {"path": str(output / "bureau_generation_plan_v1.json"), "result": atomic_write_json(output / "bureau_generation_plan_v1.json", plan)},
                {"path": str(output / "bureau_compiled_request_v1.json"), "result": atomic_write_json(output / "bureau_compiled_request_v1.json", compiled)},
            ]
        return emit({"ok": True, "report_type": "itb_episode_compilation_v1", "validate_only": bool(args.validate_only), "write_requested": args.output is not None, "writes": writes, "generation_plan_sha256": canonical_sha256(plan), "compiled_request_sha256": canonical_sha256(compiled), "deterministic_compilation_fingerprint": compiled["deterministic_compilation_fingerprint"], "shot_count": len(compiled["shot_requests"]), "counters": zero_activity_counters()})
    except (ITBContractError, OSError) as exc:
        if isinstance(exc, ITBContractError):
            return emit_contract_error("itb_episode_compilation_v1", exc)
        return emit_contract_error("itb_episode_compilation_v1", ITBContractError(Issue(code="filesystem_error", stage="write", message="Filesystem operation failed.", actual=str(exc))))


if __name__ == "__main__":
    raise SystemExit(main())
