from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.video import lena_video_creative_generation_v1 as fresh_video


def _load_json(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an offline fresh Lena video creative JSON + compiled prompt package. No provider calls."
    )
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--governed-date", required=True)
    parser.add_argument("--daily-slot", required=True)
    parser.add_argument("--user-seed", default=None)
    parser.add_argument("--business-intent", default=None)
    parser.add_argument("--history-json", type=Path, default=None)
    parser.add_argument("--policy-json", type=Path, default=None)
    parser.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "pipeline" / "video" / "lena" / "examples",
    )
    parser.add_argument("--attempt-number", type=int, default=1)
    parser.add_argument("--write", action="store_true", help="Write package artifacts. Omit for dry-run summary only.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    history = _load_json(args.history_json, [])
    policy = _load_json(args.policy_json, {"duration_seconds": 8, "resolution": "720p", "aspect_ratio": "9:16", "audio_enabled": True})
    spec = fresh_video.build_provisional_video_json(
        video_id=args.video_id,
        governed_date=args.governed_date,
        daily_slot=args.daily_slot,
        user_seed=args.user_seed,
        current_video_policy=policy,
        current_business_intent=args.business_intent,
        recent_content_history=history,
    )
    novelty = fresh_video.run_novelty_governor(spec, history)
    if not novelty["ok"]:
        raise SystemExit(json.dumps({"ok": False, "blocked": "novelty_rejected", "novelty": novelty}, indent=2))
    compiled = fresh_video.compile_provider_request(spec, attempt_id=f"{args.video_id}-attempt-{args.attempt_number:03d}")
    summary: dict[str, Any] = {
        "ok": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "queue_created": False,
        "publication_performed": False,
        "video_id": args.video_id,
        "governed_date": args.governed_date,
        "daily_slot": args.daily_slot,
        "concept": spec["concept"],
        "prompt_sha256": compiled["prompt_sha256"],
        "request_sha256": compiled["request_sha256"],
        "plan_sha256": compiled["plan_sha256"],
        "fingerprint_sha256": compiled["fingerprint_sha256"],
        "character_element_token_first": compiled["prompt_transport_proof"]["character_element_token_first"],
        "written": False,
    }
    if args.write:
        written = fresh_video.write_video_package(args.out_root, spec, attempt_number=args.attempt_number)
        summary["written"] = True
        summary.update(written)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
