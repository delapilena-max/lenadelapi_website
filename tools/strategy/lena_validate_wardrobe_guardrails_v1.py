"""
Lena Wardrobe Catalog Selection Guardrail Validation v1

Manual dry-run validation — not a CI gate yet.
Verifies that catalog outfit selection gates behave correctly.

Run: python tools/strategy/lena_validate_wardrobe_guardrails_v1.py
Exit 0 = all cases pass.  Exit 1 = any failure.

Does NOT:
  - call Kling or any API
  - read .env
  - write any files
  - generate images
  - mutate the recipe bank or wardrobe catalog
"""
import contextlib
import importlib.util
import random
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── Import from builder (safe: main() is __name__-gated; no I/O at import)
_spec = importlib.util.spec_from_file_location(
    "lena_build_kling_payload_dryrun_v1",
    ROOT / "tools/strategy/lena_build_kling_payload_dryrun_v1.py",
)
_builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_builder)

select_catalog_outfit = _builder.select_catalog_outfit
load_catalog = _builder.load_catalog

# ── Import from prompt brain ───────────────────────────────────────────────
from pipeline.prompting.lena_prompt_brain import (
    format_catalog_wardrobe_override,
    pick_style,
)

# ── Synthetic catalog for rejected-outfit test (no real rejected exists) ──
SYNTHETIC_CATALOG = {
    "outfits": [
        {
            "outfit_id": "wc_syn_rejected",
            "name": "Synthetic Rejected — test only, never use",
            "status": "rejected",
            "risk_tags": [],
            "prompt": "synthetic test outfit — must not reach generation",
            "avoid_terms": [],
        }
    ]
}


# ── expect_abort context manager ───────────────────────────────────────────
@contextlib.contextmanager
def expect_abort(keyword: str):
    """Assert SystemExit is raised with message containing keyword."""
    try:
        yield
    except SystemExit as e:
        msg = str(e)
        if keyword not in msg:
            raise AssertionError(
                f"SystemExit raised but missing expected keyword "
                f"'{keyword}'. Got: {msg!r}"
            ) from e
        return
    raise AssertionError(
        f"Expected SystemExit ('{keyword}') — none raised"
    )


# ── Test runner ────────────────────────────────────────────────────────────
_passed = 0
_failed = 0


def run(label: str, fn) -> None:
    global _passed, _failed
    try:
        fn()
        print(f"  PASS  {label}")
        _passed += 1
    except AssertionError as exc:
        print(f"  FAIL  {label}")
        print(f"        {exc}")
        _failed += 1
    except SystemExit as exc:
        print(f"  FAIL  {label}  [unexpected SystemExit]")
        print(f"        SystemExit: {exc}")
        _failed += 1
    except Exception as exc:
        print(f"  ERROR {label}")
        print(f"        {type(exc).__name__}: {exc}")
        _failed += 1


# ── Load real catalog once ─────────────────────────────────────────────────
real_catalog = load_catalog()

# ── Test cases ────────────────────────────────────────────────────────────
print("=" * 64)
print("  Lena Wardrobe Catalog Guardrail Validation v1")
print("=" * 64)

# TC01: approved / wc_e001 / allow_high_risk=False
def tc_01():
    outfit = select_catalog_outfit(real_catalog, "wc_e001", False)
    assert outfit["status"] == "approved", f"status={outfit['status']!r}"
    assert outfit["outfit_id"] == "wc_e001"

run("TC01  approved / wc_e001 / allow_hr=False", tc_01)

# TC02: approved / wc_e001 / allow_high_risk=True (flag must not break it)
def tc_02():
    outfit = select_catalog_outfit(real_catalog, "wc_e001", True)
    assert outfit["status"] == "approved", f"status={outfit['status']!r}"
    assert outfit["outfit_id"] == "wc_e001"

run("TC02  approved / wc_e001 / allow_hr=True", tc_02)

# TC03: nonexistent outfit_id => ABORT
def tc_03():
    with expect_abort("not in catalog"):
        select_catalog_outfit(real_catalog, "wc_BOGUS_999", False)

run("TC03  nonexistent outfit_id => ABORT 'not in catalog'", tc_03)

# TC04: rejected outfit (synthetic catalog) => ABORT
def tc_04():
    with expect_abort("status=rejected"):
        select_catalog_outfit(SYNTHETIC_CATALOG, "wc_syn_rejected", False)

run("TC04  rejected outfit (synthetic) => ABORT 'status=rejected'", tc_04)

# TC05: untested / wc_e002 / allow_hr=False => ABORT
def tc_05():
    with expect_abort("status=untested"):
        select_catalog_outfit(real_catalog, "wc_e002", False)

run("TC05  untested / wc_e002 / allow_hr=False => ABORT 'status=untested'", tc_05)

# TC06: untested / wc_e002 / allow_hr=True => ABORT (no allow flag for untested)
def tc_06():
    with expect_abort("status=untested"):
        select_catalog_outfit(real_catalog, "wc_e002", True)

run("TC06  untested / wc_e002 / allow_hr=True => ABORT 'status=untested'", tc_06)

# TC07: high_risk / wc_a001 / allow_hr=False => ABORT
def tc_07():
    with expect_abort("high_risk"):
        select_catalog_outfit(real_catalog, "wc_a001", False)

run("TC07  high_risk / wc_a001 / allow_hr=False => ABORT 'high_risk'", tc_07)

# TC08: high_risk / wc_a001 / allow_hr=True => PASS (dry-run gate only)
def tc_08():
    outfit = select_catalog_outfit(real_catalog, "wc_a001", True)
    assert outfit["status"] == "high_risk", f"status={outfit['status']!r}"
    assert len(outfit["risk_tags"]) > 0, "risk_tags must be non-empty"

run("TC08  high_risk / wc_a001 / allow_hr=True => PASS (dry-run only)", tc_08)

# TC09: no wardrobe_outfit_id in packet => STYLE_BANK fallback preserved
def tc_09():
    synthetic_packet = {"recipe_id": "hcr_001", "compact_kling_prompt_preview": "x"}
    outfit_id = synthetic_packet.get("wardrobe_outfit_id")
    assert not outfit_id, f"Expected falsy outfit_id, got: {outfit_id!r}"
    style = pick_style(random.Random(42))
    for key in ("category", "outfit", "hair", "makeup", "accessories"):
        assert key in style, f"STYLE_BANK entry missing '{key}'"
    assert "_source" not in style, "STYLE_BANK entry must not have '_source'"

run("TC09  no wardrobe_outfit_id => STYLE_BANK fallback preserved", tc_09)

# TC10: format_catalog_wardrobe_override is clothes-only; no avoid_terms injected
def tc_10():
    wc_e001 = next(
        o for o in real_catalog["outfits"] if o["outfit_id"] == "wc_e001"
    )
    output = format_catalog_wardrobe_override(wc_e001)
    assert "clothing only" in output, "Output missing 'clothing only'"
    assert "approved character element/reference images" in output, \
        "Output missing identity disclaimer"
    assert "not the outfit text" in output, "Output missing 'not the outfit text'"
    assert wc_e001["prompt"] in output, "Output must include entry['prompt']"
    for term in wc_e001["avoid_terms"]:
        assert term not in output, (
            f"avoid_term '{term}' found in output — must not be injected"
        )

run("TC10  format_catalog_wardrobe_override: clothes-only, no avoid_terms", tc_10)

# ── Summary ───────────────────────────────────────────────────────────────
print("=" * 64)
print(f"  Results: {_passed} passed  /  {_failed} failed  /  10 total")
print("=" * 64)
print()
if _failed:
    print("  GUARDRAIL VALIDATION: FAILED")
    print()
    print("  NO API call.  NO generation.  NO upload.")
    print("  NO publish.   NO queue.       NO schedule.")
    sys.exit(1)
else:
    print("  GUARDRAIL VALIDATION: PASSED")
    print()
    print("  NO API call.  NO generation.  NO upload.")
    print("  NO publish.   NO queue.       NO schedule.")
    sys.exit(0)
