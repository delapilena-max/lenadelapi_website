from __future__ import annotations

from pathlib import Path

from pipeline.media_properties.interstitial_travel_bureau.artifacts import EpisodeStore
from pipeline.media_properties.interstitial_travel_bureau.contracts import ITBContractError, zero_activity_counters
from tools.itb_cli_support_v1 import JsonArgumentParser, emit, emit_contract_error, help_report


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="python -m tools.itb_inspect_episode_v1", description="Inspect ITB authority IDs, hashes, and dependency edges without mutation.")
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
        artifacts = EpisodeStore(args.episode_root).load_all()
        return emit({
            "ok": True,
            "report_type": "itb_episode_inspection_v1",
            "episode_root": str(args.episode_root),
            "artifacts": [
                {"artifact_type": key, "artifact_id": item.artifact_id, "sha256": item.sha256, "path": item.relative_path, "upstream_artifacts": item.data["upstream_artifacts"]}
                for key, item in artifacts.items()
            ],
            "counters": zero_activity_counters(),
        })
    except ITBContractError as exc:
        return emit_contract_error("itb_episode_inspection_v1", exc)


if __name__ == "__main__":
    raise SystemExit(main())
