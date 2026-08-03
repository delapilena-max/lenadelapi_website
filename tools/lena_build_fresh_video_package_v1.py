from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.media_properties.lena.video import fresh_creative_generation as fresh_video


def _load_json(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build offline canonical Lena video A-N source artifacts and optionally compile them with the existing canonical compiler. No provider calls."
    )
    parser.add_argument("--video-slug", required=True)
    parser.add_argument("--governed-date", required=True)
    parser.add_argument("--user-seed", default=None)
    parser.add_argument("--history-json", type=Path, default=None)
    parser.add_argument("--created-at", default=None)
    parser.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "pipeline" / "media_properties" / "lena" / "video" / "fixtures" / "fresh_generation_examples",
    )
    parser.add_argument("--attempt-number", type=int, default=1)
    parser.add_argument("--write", action="store_true", help="Write package artifacts. Omit for dry-run summary only.")
    parser.add_argument("--compile", action="store_true", help="Run the existing canonical compiler after writing source artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    history = _load_json(args.history_json, [])
    artifacts = fresh_video.build_canonical_source_artifacts(
        governed_date=args.governed_date,
        video_slug=args.video_slug,
        user_seed=args.user_seed,
        created_at=args.created_at,
    )
    novelty = fresh_video.run_novelty_governor(artifacts, history)
    if not novelty["ok"]:
        raise SystemExit(json.dumps({"ok": False, "blocked": "novelty_rejected", "novelty": novelty}, indent=2))
    video_id = artifacts["lena_video_spec_v1"]["video_id"]
    video_root = args.out_root / args.governed_date / args.video_slug / f"attempt_{args.attempt_number:03d}"
    summary: dict[str, Any] = {
        "ok": True,
        "provider_call_performed": False,
        "generation_performed": False,
        "queue_created": False,
        "publication_performed": False,
        "video_id": video_id,
        "governed_date": args.governed_date,
        "daily_slot": "daily_video_01",
        "concept": artifacts["lena_video_spec_v1"]["concept"],
        "canonical_source_validation": fresh_video.validate_canonical_sources(artifacts),
        "written": False,
        "compiled": False,
        "counters": {
            "network_calls": 0,
            "provider_calls": 0,
            "generation_actions": 0,
            "publishing_actions": 0,
            "scheduler_actions": 0,
            "photo_lane_modifications": 0,
            "video_execution_actions": 0,
        },
    }
    if args.write:
        statuses = fresh_video.write_source_artifacts(video_root, artifacts)
        instruction_status = fresh_video.write_instruction_authority(
            args.out_root / "creative_authority" / "lena_video_creative_generator_instruction_v1.json"
        )
        summary["written"] = True
        summary["video_root"] = str(video_root)
        summary["source_write_statuses"] = statuses
        summary["instruction_authority_write_status"] = instruction_status
    if args.compile:
        if not args.write:
            raise SystemExit("--compile requires --write so the canonical compiler can load governed source files")
        plan, compiled = fresh_video.compile_canonical_video_package(video_root)
        attempt = fresh_video.build_attempt_record(
            compiled_request=compiled,
            attempt_number=args.attempt_number,
        )
        prompt_text = compiled["exact_compiled_prompt"]
        prompt_path = video_root / "exact_provider_prompt.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")
        attempt_path = video_root / "attempt_record.json"
        attempt_path.write_text(json.dumps(attempt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        summary.update(
            {
                "compiled": True,
                "plan_sha256": fresh_video.canonical_sha256(plan),
                "request_sha256": fresh_video.canonical_sha256(compiled),
                "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                "fingerprint_sha256": compiled["deterministic_compilation_fingerprint"],
                "character_element_token_first": prompt_text.startswith(fresh_video.CHARACTER_ELEMENT_TOKEN),
                "prompt_path": str(prompt_path),
                "attempt_record_path": str(attempt_path),
            }
        )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
