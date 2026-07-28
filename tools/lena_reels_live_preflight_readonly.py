"""
Instagram Reels LIVE preflight (READ-ONLY).

Uses the exact same asset resolution, Instagram Login route, credential env
aliases, and governed caption-bank selection as the real publisher
(tools/lena_governed_publish_pipeline_v1.py, which itself calls
pipeline/publisher/instagram_graph_adapter.py) -- via
resolve_reels_publish_context(), one shared function, not duplicated
constants. No caption text, asset path, or expected hash is hardcoded
anywhere in this file.

Verifies, in order:
  1. Source asset resolution -- the asset dir's real source .mp4 and its
     current SHA-256 (no fixed "expected" hash to compare to unless
     --expect-source-sha256 is given, e.g. to pin against a lane-autonomy
     authorization's bound source_sha256).
  2. Offline proof gate (scrub/provenance/clean-export/caption-dedup/
     credential-presence/duplicate checks) -- reused unchanged from
     lena_governed_publish_pipeline_v1.run_offline_proof_gate().
  3. Live Meta /me token validation against the SAME Instagram Login route
     (graph.instagram.com) and the SAME credential env aliases the real
     publisher (pipeline/publisher/instagram_graph_adapter.py) uses --
     reusing that module's own request/env-resolution helpers directly,
     not reimplementing them.

It NEVER uploads, queues, schedules, publishes, consumes/marks a caption
from the bank, issues/validates/revokes the standing Reels lane-autonomy
authorization, or claims a per-asset execution slot. The only network call
is a read-only GET /me for token validation (skip with
--skip-live-token-check).

Run from the machine that has network access (not a sandbox):
    cd C:\\projects\\ai\\content_bot
    python tools\\lena_reels_live_preflight_readonly.py --asset-dir <path>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.lena_governed_publish_pipeline_v1 import (  # noqa: E402
    PipelineError,
    resolve_reels_publish_context,
    run_offline_proof_gate,
)


def _tag(ok: Optional[bool]) -> str:
    if ok is None:
        return "SKIPPED"
    return "GREEN" if ok else "RED"


def check_live_login_token(context: dict[str, Any]) -> dict[str, Any]:
    """Read-only GET /me against the exact route and credential env aliases
    the real publisher (pipeline/publisher/instagram_graph_adapter.py)
    uses -- imports and calls that module's own helpers directly rather than
    reimplementing token resolution or the request, so this check can never
    silently drift from what the real publisher actually does. Local import
    so this module is importable (e.g. by tests) without requiring env/
    network setup at import time."""
    from pipeline.publisher.instagram_graph_adapter import ENV_ALIASES, _clean_token, _request_json

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for canonical, aliases in ENV_ALIASES.items():
        found = next((alias for alias in aliases if _clean_token(os.environ.get(alias))), None)
        if found:
            resolved[canonical] = found
        else:
            missing.append(canonical)
    if missing:
        return {"ok": False, "reason": "missing_credentials", "missing": missing}

    access_token = _clean_token(os.environ.get(resolved["INSTAGRAM_GRAPH_ACCESS_TOKEN"]))
    try:
        me = _request_json(
            "GET", f"{context['api_base']}/me",
            params={"access_token": access_token}, timeout=30,
        )
    except Exception as exc:
        return {"ok": False, "reason": "live_token_check_failed", "detail": str(exc)}
    return {"ok": bool(me.get("id")), "me_id": me.get("id"), "raw": me}


def run_preflight(
    asset_dir: Path,
    *,
    expect_source_sha256: Optional[str] = None,
    check_live_token: bool = True,
) -> dict[str, Any]:
    context = resolve_reels_publish_context(asset_dir)
    results: dict[str, Optional[bool]] = {}
    report: dict[str, Any] = {"context": context}

    if expect_source_sha256:
        results["1. Source SHA-256 matches expected binding"] = (
            context["source_sha256"] == expect_source_sha256
        )
    else:
        results["1. Source SHA-256 resolved"] = True

    try:
        proof = run_offline_proof_gate(Path(context["asset_dir"]), Path(context["source_path"]))
        report["proof_gate"] = proof
        results["2. Offline proof gate (scrub/provenance/dedup/credentials)"] = bool(
            proof.get("proof_gate_passed")
        )
    except PipelineError as exc:
        report["proof_gate_error"] = str(exc)
        results["2. Offline proof gate (scrub/provenance/dedup/credentials)"] = False

    if check_live_token:
        token_check = check_live_login_token(context)
        report["live_token_check"] = token_check
        results["3. Live Instagram Login /me validation"] = bool(token_check.get("ok"))
    else:
        results["3. Live Instagram Login /me validation"] = None

    report["results"] = results
    report["all_green"] = all(v for v in results.values() if v is not None)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", required=True, help="Path to the asset review directory")
    parser.add_argument("--expect-source-sha256", default=None)
    parser.add_argument("--skip-live-token-check", action="store_true")
    args = parser.parse_args()

    report = run_preflight(
        Path(args.asset_dir),
        expect_source_sha256=args.expect_source_sha256,
        check_live_token=not args.skip_live_token_check,
    )

    print("=" * 60)
    print("  INSTAGRAM REELS LIVE PREFLIGHT (READ-ONLY)")
    print("=" * 60)
    for name, ok in report["results"].items():
        print(f"{name:60s}: {_tag(ok)}")
    print("-" * 60)
    print("OVERALL:", "ALL GREEN" if report["all_green"] else "NOT ALL GREEN")
    print("[read-only] No upload, queue, schedule, publish, caption bank write, authorization")
    print("[read-only] consumption, or publish-slot claim was performed.")
    print("-" * 60)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report["all_green"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
