from __future__ import annotations

from pathlib import Path

from pipeline.media_properties.interstitial_travel_bureau.artifacts import EpisodeStore
from pipeline.media_properties.interstitial_travel_bureau.contracts import ITBContractError, zero_activity_counters
from pipeline.media_properties.interstitial_travel_bureau.novelty import evaluate_novelty
from tools.itb_cli_support_v1 import JsonArgumentParser, emit, emit_contract_error, help_report


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="python -m tools.itb_novelty_check_v1", description="Compare an ITB Creative Genome with a governed continuity ledger.")
    parser.add_argument("--episode-root", type=Path, help="Episode root containing the proposed Creative Genome.")
    parser.add_argument("--ledger", type=Path, help="Episode root containing the governed continuity ledger; defaults to episode root.")
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
        genome = EpisodeStore(args.episode_root).load("bureau_creative_genome_v1")
        ledger = EpisodeStore(args.ledger or args.episode_root).load("bureau_continuity_ledger_v1")
        report = evaluate_novelty(genome.data, ledger.data["entries"], proposed_episode_id=genome.data["episode_id"])
        report["counters"] = zero_activity_counters()
        return emit(report)
    except ITBContractError as exc:
        return emit_contract_error("itb_novelty_check_v1", exc)


if __name__ == "__main__":
    raise SystemExit(main())
