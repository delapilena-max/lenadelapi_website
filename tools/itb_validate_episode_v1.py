from __future__ import annotations

from pathlib import Path

from pipeline.media_properties.interstitial_travel_bureau.contracts import ITBContractError
from pipeline.media_properties.interstitial_travel_bureau.validation import validate_episode_root
from tools.itb_cli_support_v1 import JsonArgumentParser, emit, emit_contract_error, help_report


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="python -m tools.itb_validate_episode_v1", description="Validate one complete ITB episode authority root.")
    parser.add_argument("--episode-root", type=Path, help="Directory containing governed episode JSON artifacts.")
    parser.add_argument("--validate-only", action="store_true", help="Explicitly confirms this command performs no writes.")
    return parser


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
        if args.json_help:
            return emit(help_report(parser, parser.prog))
        if args.episode_root is None:
            parser.error("--episode-root is required")
        return emit(validate_episode_root(args.episode_root))
    except ITBContractError as exc:
        return emit_contract_error("itb_episode_validation_v1", exc)


if __name__ == "__main__":
    raise SystemExit(main())
