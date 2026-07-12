from __future__ import annotations

# Minimal, separate one-off Higgsfield prompt-isolation test runner -- v1.
#
# Purpose (narrow, explicit): submit EXPLICITLY approved, hand-supplied
# one-off Lena prompt variants (e.g. a wardrobe-isolation A/B/C test) under
# clearly test-scoped identities, reusing the existing Higgsfield transport
# and Lena identity/reference machinery already proven in
# pipeline/higgsfield_lena_api_executor.py.
#
# This tool NEVER imports, calls, modifies, or weakens
# pipeline/higgsfield_lena_api_executor.py's resolve_prompt_source() or its
# pack-deterministic behavior. Production pack-slot generation is completely
# untouched by this tool's existence -- this is a second, narrower door, not
# a change to the first one. It reuses only the already-proven,
# provider-agnostic-within-Higgsfield pieces: the confirmed identity/config
# constants, build_provider_argv() (unmodified), and the same
# result-parsing/download helpers -- never a second API client.
#
# HARD SAFETY GATES (v1, all enforced by construction):
#   - --dry-run is the default; --live requires the flag explicitly.
#   - At most 3 variants per invocation (MAX_VARIANTS_PER_INVOCATION).
#   - Every test_slot_id must be clearly test-scoped: must NOT match the
#     production pack-slot pattern (_PACK_SLOT_ID_PATTERN, imported, never
#     redefined), and must contain the literal substring "-test-".
#   - Every variant's source_slot_id must resolve to a real, already-existing
#     seed image on disk -- fails closed if the lineage is missing.
#   - Duplicate test_slot_id values within one invocation fail closed.
#   - An existing output (manifest, final image, OR a leftover .tmp download)
#     for a test_slot_id always fails closed -- v1 has no overwrite path at
#     all. A prior artifact must be removed manually before retrying that
#     exact test_slot_id.
#   - A failed live download cleans up only the .tmp file it itself just
#     created, in a try/finally -- it never leaves a stale .tmp behind from
#     its own failed attempt, and never touches any other file.
#   - The supplied image_prompt is never rewritten, trimmed, reconstructed,
#     or re-derived -- stored and submitted byte-for-byte as given.
#   - No queue/publish/R2/analytics/.env import anywhere in this file.
#   - Never creates an approval record, never promotes, never queues, never
#     publishes, never uploads to R2, never touches analytics or .env.
#
# Run (dry-run, default, no provider/network call):
#   python tools/lena_higgsfield_prompt_isolation_test_v1.py --date 2026-07-09 --variants-file <path.json>
#
# Run (live, up to 3 real provider calls -- needs --live explicitly):
#   python tools/lena_higgsfield_prompt_isolation_test_v1.py --date 2026-07-09 --variants-file <path.json> --live

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reused, never redefined -- the same confirmed identity/transport/parsing
# primitives pipeline/higgsfield_lena_api_executor.py already proved live.
from pipeline.higgsfield_lena_api_executor import (  # noqa: E402
    HIGGSFIELD_CLI_BINARY,
    HIGGSFIELD_IMAGE_JOB_TYPE,
    HIGGSFIELD_ASPECT_RATIO,
    HIGGSFIELD_CLI_CONFIRMED_VERSION,
    DEFAULT_LENA_CUSTOM_REFERENCE_ID,
    CONFIRMED_LENA_SOUL_NAME,
    CONFIRMED_LENA_SOUL_TYPE,
    _PACK_SLOT_ID_PATTERN,
    build_provider_argv,
    _redacted_argv_for_display,
    _canonical_result_urls,
    _find_first_str_field,
    _detect_image_extension,
    _sanitize_url,
    _download,
    ProviderCallError,
)

MAX_VARIANTS_PER_INVOCATION = 3
TEST_SCOPE_MARKER = "-test-"

# Deliberately separate from real production paths -- never collides with,
# and is never mistaken for, a real production seed image or manifest.
TEST_LIBRARY_ROOT = ROOT / "pipeline" / "higgsfield_library" / "lena"
TEST_DEBUG_ROOT = ROOT / "pipeline" / "higgsfield_debug"
TEST_SUBDIR_NAME = "prompt_isolation_tests"


class PromptIsolationTestError(Exception):
    """Raised for any hard-fail condition. Always fails closed -- no file
    is ever written and no provider call is ever made when this is raised."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_source_seed_path(date_str: str, source_slot_id: str) -> Path:
    """Real lineage check: the source_slot_id's own already-generated seed
    image must exist on disk. Tries .png/.jpg/.jpeg in that order -- never
    guesses, never invents a path that doesn't exist."""
    base = ROOT / "pipeline" / "higgsfield_library" / "lena" / date_str
    for ext in (".png", ".jpg", ".jpeg"):
        candidate = base / f"{source_slot_id}_seed{ext}"
        if candidate.exists():
            return candidate
    raise PromptIsolationTestError(
        f"source lineage missing: no {source_slot_id}_seed.(png|jpg|jpeg) found under {base}"
    )


def test_output_paths(date_str: str, test_slot_id: str) -> Dict[str, Path]:
    image_dir = TEST_LIBRARY_ROOT / date_str / TEST_SUBDIR_NAME
    manifest_dir = TEST_DEBUG_ROOT / date_str / TEST_SUBDIR_NAME / test_slot_id
    return {
        "image_dir": image_dir,
        "image_stem": f"{test_slot_id}_seed",
        "manifest_path": manifest_dir / "result_manifest.json",
    }


def _existing_output_paths(date_str: str, test_slot_id: str) -> List[Path]:
    """Any prior artifact for this test_slot_id -- a finished manifest, a
    finished image, OR a leftover .tmp download from a previous invocation
    -- counts as an existing output. v1 has no overwrite path at all: any
    of these fails closed, unconditionally. A stale .tmp is never silently
    reused or silently overwritten; it must be dealt with (removed) before
    this exact test_slot_id can be attempted again."""
    paths = test_output_paths(date_str, test_slot_id)
    found: List[Path] = []
    if paths["manifest_path"].exists():
        found.append(paths["manifest_path"])
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".bin", ".tmp"):
        candidate = paths["image_dir"] / f"{paths['image_stem']}{ext}"
        if candidate.exists():
            found.append(candidate)
    return found


def validate_test_slot_id(test_slot_id: str) -> List[str]:
    reasons: List[str] = []
    if _PACK_SLOT_ID_PATTERN.match(test_slot_id):
        reasons.append(
            f"test_slot_id {test_slot_id!r} matches the production pack-slot naming "
            "pattern -- refusing to treat a real production identity shape as a test."
        )
    if TEST_SCOPE_MARKER not in test_slot_id:
        reasons.append(
            f"test_slot_id {test_slot_id!r} does not contain the required "
            f"{TEST_SCOPE_MARKER!r} marker -- refusing an ambiguously-scoped identity."
        )
    return reasons


def validate_variant(
    date_str: str,
    variant: Dict[str, Any],
    seen_test_slot_ids: Set[str],
) -> Dict[str, Any]:
    """Never raises -- returns a dict with 'ok' plus every reason found, so
    all variants can be reported together before any provider call."""
    reasons: List[str] = []

    test_slot_id = str(variant.get("test_slot_id") or "").strip()
    source_slot_id = str(variant.get("source_slot_id") or "").strip()
    image_prompt = variant.get("image_prompt")
    wardrobe_id = variant.get("wardrobe_id")
    variant_label = variant.get("variant_label")

    if not test_slot_id:
        reasons.append("missing test_slot_id")
    else:
        reasons.extend(validate_test_slot_id(test_slot_id))
        if test_slot_id in seen_test_slot_ids:
            reasons.append(f"duplicate test_slot_id within this invocation: {test_slot_id!r}")

    source_seed_path: Optional[Path] = None
    if not source_slot_id:
        reasons.append("missing source_slot_id -- source lineage is required")
    else:
        try:
            source_seed_path = resolve_source_seed_path(date_str, source_slot_id)
        except PromptIsolationTestError as exc:
            reasons.append(str(exc))

    if not image_prompt or not isinstance(image_prompt, str):
        reasons.append("missing or non-string image_prompt")

    existing_outputs: List[Path] = []
    if test_slot_id:
        existing_outputs = _existing_output_paths(date_str, test_slot_id)
        if existing_outputs:
            reasons.append(
                f"output already exists for test_slot_id {test_slot_id!r}: "
                f"{[str(p) for p in existing_outputs]} -- v1 has no overwrite path; "
                "remove the prior artifact manually before retrying this exact test_slot_id"
            )

    return {
        "ok": not reasons,
        "reasons": reasons,
        "test_slot_id": test_slot_id,
        "source_slot_id": source_slot_id,
        "source_seed_path": str(source_seed_path) if source_seed_path else None,
        "source_seed_sha256": _sha256_file(source_seed_path) if source_seed_path else None,
        "wardrobe_id": wardrobe_id,
        "variant_label": variant_label,
        "image_prompt": image_prompt if isinstance(image_prompt, str) else None,
        "prompt_sha256": _sha256_text(image_prompt) if isinstance(image_prompt, str) else None,
        "prompt_length": len(image_prompt) if isinstance(image_prompt, str) else None,
        "existing_outputs": [str(p) for p in existing_outputs],
    }


def validate_variants(
    date_str: str, variants: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if len(variants) > MAX_VARIANTS_PER_INVOCATION:
        return {
            "ok": False,
            "reasons": [
                f"{len(variants)} variants supplied, exceeds the maximum of "
                f"{MAX_VARIANTS_PER_INVOCATION} per invocation"
            ],
            "variant_results": [],
        }

    seen: Set[str] = set()
    results: List[Dict[str, Any]] = []
    for variant in variants:
        result = validate_variant(date_str, variant, seen)
        if result["test_slot_id"]:
            seen.add(result["test_slot_id"])
        results.append(result)

    return {
        "ok": all(r["ok"] for r in results) and len(results) > 0,
        "reasons": [] if results else ["no variants supplied"],
        "variant_results": results,
    }


def print_dry_run_report(
    date_str: str,
    custom_reference_id: str,
    validation: Dict[str, Any],
) -> None:
    print("=== Higgsfield Lena prompt-isolation test -- DRY RUN (no provider/network call) ===\n")
    print(f"date                    : {date_str}")
    print(f"job_type                : {HIGGSFIELD_IMAGE_JOB_TYPE}")
    print(f"custom_reference_id     : {custom_reference_id}")
    print(f"cli soul identity       : name={CONFIRMED_LENA_SOUL_NAME!r} type={CONFIRMED_LENA_SOUL_TYPE!r}")
    print(f"aspect_ratio            : {HIGGSFIELD_ASPECT_RATIO}")
    print(f"variant count           : {len(validation['variant_results'])}")
    print(f"overall ok              : {validation['ok']}")
    if validation["reasons"]:
        print(f"invocation-level reasons: {validation['reasons']}")
    print()

    for i, result in enumerate(validation["variant_results"], start=1):
        print(f"--- variant {i} ---")
        print(f"  test_slot_id          : {result['test_slot_id']}")
        print(f"  source_slot_id        : {result['source_slot_id']}")
        print(f"  source_seed_path      : {result['source_seed_path']}")
        print(f"  source_seed_sha256    : {result['source_seed_sha256']}")
        print(f"  wardrobe_id           : {result['wardrobe_id']}")
        print(f"  variant_label         : {result['variant_label']}")
        print(f"  prompt_length         : {result['prompt_length']}")
        print(f"  prompt_sha256         : {result['prompt_sha256']}")
        print(f"  ok                    : {result['ok']}")
        if result["reasons"]:
            print(f"  reasons               : {result['reasons']}")
        if result["ok"]:
            argv = build_provider_argv(result["image_prompt"], custom_reference_id)
            paths = test_output_paths(date_str, result["test_slot_id"])
            print(f"  provider argv (redacted): {_redacted_argv_for_display(argv, result['image_prompt'])}")
            print(f"  proposed image dir    : {paths['image_dir']}")
            print(f"  proposed image stem   : {paths['image_stem']}")
            print(f"  proposed manifest path: {paths['manifest_path']}")
        print()

    print("=== RESULT: no subprocess call, no network call, no file written. Dry-run only. ===")


def submit_variant_live(
    date_str: str,
    result: Dict[str, Any],
    custom_reference_id: str,
) -> Dict[str, Any]:
    """Mirrors pipeline/higgsfield_lena_api_executor.py::run_live()'s real
    subprocess/parse/download flow exactly, parameterized by an explicit
    prompt + test_slot_id instead of a pack-resolved source -- reuses every
    transport/parsing primitive from that module, never reimplements them."""
    prompt = result["image_prompt"]
    test_slot_id = result["test_slot_id"]
    argv = build_provider_argv(prompt, custom_reference_id)

    resolved_binary = shutil.which(HIGGSFIELD_CLI_BINARY)
    if not resolved_binary:
        raise ProviderCallError(
            f"Could not resolve {HIGGSFIELD_CLI_BINARY!r} via shutil.which() -- "
            "the Higgsfield CLI does not appear to be on PATH."
        )
    resolved_argv = [resolved_binary, *argv[1:]]

    print(f"[LIVE] resolved executable: {resolved_binary}")
    print(f"[LIVE] test_slot_id       : {test_slot_id}")
    print(f"[LIVE] invoking: {_redacted_argv_for_display(resolved_argv, prompt)}")
    try:
        proc = subprocess.run(resolved_argv, capture_output=True, text=True, shell=False, check=False)
    except OSError as exc:
        raise ProviderCallError(
            f"Failed to spawn the Higgsfield CLI process ({resolved_binary!r}): {exc}"
        ) from exc

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip()[-2000:]
        raise ProviderCallError(
            f"higgsfield generate create exited {proc.returncode}. stderr (tail): {stderr_tail}"
        )

    stdout = proc.stdout or ""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProviderCallError(
            f"Failed to parse --json output as JSON: {exc}. stdout length was {len(stdout)} chars."
        ) from exc

    job_id = _find_first_str_field(parsed, ("job_id", "id"))
    status = _find_first_str_field(parsed, ("status",))
    result_urls = _canonical_result_urls(parsed)

    if not result_urls:
        raise ProviderCallError(
            "No canonical result_url found in provider response -- refusing to proceed."
        )
    if len(result_urls) > 1:
        raise ProviderCallError(
            f"Provider response contained {len(result_urls)} distinct top-level "
            "result_url values where exactly one was expected. Manual review required."
        )

    result_url = result_urls[0]
    paths = test_output_paths(date_str, test_slot_id)
    # Slot-specific temp path (never shared across variants, since
    # test_slot_id is always unique per invocation -- enforced by
    # validate_variants()'s duplicate check). Wrapped exception-safe: if
    # this exact invocation's own download or rename fails, the .tmp file
    # it itself just created is removed here, in a finally -- it never
    # leaves a stale .tmp behind from its own failed attempt. It never
    # touches any other file, and a .tmp already present from some earlier,
    # different invocation is never silently reused or removed here --
    # that case is caught upstream by validate_variant()'s existing-output
    # check (which now also treats a leftover .tmp as a collision).
    tmp_path = paths["image_dir"] / f"{paths['image_stem']}.tmp"
    downloaded = False
    try:
        image_bytes = _download(result_url, tmp_path)
        downloaded = True
        extension = _detect_image_extension(image_bytes)
        final_path = paths["image_dir"] / f"{paths['image_stem']}{extension}"
        tmp_path.replace(final_path)
    except Exception as exc:
        if not downloaded:
            raise ProviderCallError(f"Download of result image failed: {exc}") from exc
        raise ProviderCallError(f"Finalizing downloaded result image failed: {exc}") from exc
    finally:
        # Only ever removes the exact .tmp path this invocation itself may
        # have created above -- if the rename above already succeeded,
        # tmp_path no longer exists and this is a no-op.
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "job_id": job_id,
        "status": status,
        "result_urls": result_urls,
        "saved_image_path": str(final_path),
        "image_format_detected": extension,
        "output_sha256": _sha256_file(final_path),
    }


def build_test_manifest(
    date_str: str,
    result: Dict[str, Any],
    custom_reference_id: str,
    live_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    manifest = {
        "generated_by": "tools/lena_higgsfield_prompt_isolation_test_v1.py",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "higgsfield",
        "cli_version": HIGGSFIELD_CLI_CONFIRMED_VERSION,
        "job_type": HIGGSFIELD_IMAGE_JOB_TYPE,
        "date": date_str,
        "test_slot_id": result["test_slot_id"],
        "source_slot_id": result["source_slot_id"],
        "source_seed_path": result["source_seed_path"],
        "source_seed_sha256": result["source_seed_sha256"],
        "wardrobe_id": result["wardrobe_id"],
        "variant_label": result["variant_label"],
        "custom_reference_id": custom_reference_id,
        "cli_soul_name": CONFIRMED_LENA_SOUL_NAME,
        "cli_soul_type": CONFIRMED_LENA_SOUL_TYPE,
        "aspect_ratio": HIGGSFIELD_ASPECT_RATIO,
        "image_prompt": result["image_prompt"],
        "prompt_sha256": result["prompt_sha256"],
        "prompt_length": result["prompt_length"],
        "live_attempt_count": 1 if live_result else 0,
    }
    if live_result:
        manifest.update({
            "provider_job_id": live_result.get("job_id"),
            "provider_status": live_result.get("status"),
            "result_urls_sanitized": [_sanitize_url(u) for u in live_result.get("result_urls", [])],
            "result_url_count": len(live_result.get("result_urls", [])),
            "saved_image_path": live_result.get("saved_image_path"),
            "image_format_detected": live_result.get("image_format_detected"),
            "output_sha256": live_result.get("output_sha256"),
        })
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Submits up to 3 explicitly-approved, hand-supplied one-off Lena prompt "
            "isolation-test variants under clearly test-scoped identities. Reuses "
            "pipeline/higgsfield_lena_api_executor.py's transport/identity constants "
            "and helpers -- never modifies that file, never calls its pack-deterministic "
            "resolve_prompt_source(). Defaults to dry-run; --live performs real provider calls."
        )
    )
    parser.add_argument("--date", required=True, help="e.g. 2026-07-09")
    parser.add_argument(
        "--variants-file", required=True, dest="variants_file",
        help="Path to a JSON file containing a list of up to 3 variant objects, each with "
             "test_slot_id, source_slot_id, image_prompt, and optional wardrobe_id/variant_label.",
    )
    parser.add_argument(
        "--custom-reference-id", dest="custom_reference_id",
        default=DEFAULT_LENA_CUSTOM_REFERENCE_ID,
        help="Higgsfield Soul custom_reference_id (default: Lena's confirmed Soul ID)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.dry_run and args.live:
        print("[ABORT] --dry-run and --live are mutually exclusive.")
        return 1
    live = bool(args.live)

    variants_path = Path(args.variants_file)
    if not variants_path.exists():
        print(f"[ABORT] --variants-file not found: {variants_path}")
        return 1
    try:
        variants = json.loads(variants_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ABORT] --variants-file failed to parse as JSON: {exc}")
        return 1
    if not isinstance(variants, list):
        print("[ABORT] --variants-file must contain a JSON array of variant objects.")
        return 1

    validation = validate_variants(args.date, variants)
    print_dry_run_report(args.date, args.custom_reference_id, validation)

    if not live:
        return 0 if validation["ok"] else 1

    if not validation["ok"]:
        print("[ABORT] Validation failed -- refusing to make any provider call.")
        return 1

    overall_ok = True
    for result in validation["variant_results"]:
        try:
            live_result = submit_variant_live(args.date, result, args.custom_reference_id)
        except ProviderCallError as exc:
            print(f"[FAILED] {result['test_slot_id']}: {exc}")
            overall_ok = False
            continue

        manifest = build_test_manifest(args.date, result, args.custom_reference_id, live_result)
        manifest_path = test_output_paths(args.date, result["test_slot_id"])["manifest_path"]
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"[LIVE] {result['test_slot_id']} saved image     : {live_result['saved_image_path']}")
        print(f"[LIVE] {result['test_slot_id']} manifest written: {manifest_path}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
