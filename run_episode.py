#!/usr/bin/env python3
"""
run_episode.py

Small CLI wrapper to build an episode with optional verbose logging.
It tries to reuse `shots` or `get_shots()` from nodes.episode_builder if available,
otherwise it will exit with a helpful error so you can adapt it to your project.
"""

import argparse
import logging
import sys

# Try to import the project's episode builder and any exported shots
try:
    from nodes.episode_builder import build_episode
except Exception as e:
    raise ImportError("Could not import build_episode from nodes.episode_builder") from e

# Prefer an exported `shots` list, then a `get_shots()` factory if present.
SHOTS = None
try:
    from nodes.episode_builder import shots as SHOTS  # type: ignore
except Exception:
    try:
        from nodes.episode_builder import get_shots  # type: ignore
        SHOTS = get_shots()
    except Exception:
        SHOTS = None


def parse_args():
    p = argparse.ArgumentParser(description="Build an episode (wrapper for nodes.episode_builder.build_episode)")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    p.add_argument("--out", default="output/episode_demo.mp4", help="Output file path")
    return p.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logging.debug("Starting run_episode.py (verbose mode enabled)")

    if SHOTS is None:
        logging.error(
            "No `shots` or `get_shots()` found in nodes.episode_builder.\n"
            "Please export a `shots` list or a `get_shots()` function from nodes/episode_builder.py\n"
            "so this wrapper can call build_episode(shots, out_path)."
        )
        sys.exit(2)

    out_path = args.out
    logging.info("Building episode → %s", out_path)

    try:
        build_episode(SHOTS, out_path)
    except Exception:
        logging.exception("Episode build failed")
        sys.exit(1)

    logging.info("Episode build finished successfully.")


if __name__ == "__main__":
    main()
