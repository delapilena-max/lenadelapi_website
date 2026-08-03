from __future__ import annotations

from pathlib import Path

from pipeline.media_properties.lena.video.contracts import LenaVideoContractError
from pipeline.media_properties.lena.video.validation import validate_video_root
from tools.lena_video_cli_support_v1 import (
    JsonArgumentParser,
    emit,
    emit_contract_error,
    emit_filesystem_error,
    help_report,
)


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        prog="python -m tools.lena_video_validate_v1",
        description="Validate one complete local Lena video authority root.",
    )
    parser.add_argument(
        "--video-root",
        type=Path,
        help="Directory containing the fourteen governed Lena video artifacts.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Explicitly confirms this command performs no writes.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
        if args.json_help:
            return emit(help_report(parser, parser.prog))
        if args.video_root is None:
            parser.error("--video-root is required")
        report = validate_video_root(args.video_root)
        report["validate_only"] = bool(args.validate_only)
        return emit(report, exit_code=0 if report["ok"] else 2)
    except LenaVideoContractError as exc:
        return emit_contract_error("lena_video_validation_v1", exc)
    except OSError as exc:
        return emit_filesystem_error("lena_video_validation_v1", exc)


if __name__ == "__main__":
    raise SystemExit(main())
