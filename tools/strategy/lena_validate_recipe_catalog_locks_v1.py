"""
Lena Recipe Catalog Lock Validation v1

Manual dry-run only. Not CI-wired.
Validates that active Lena recipes are locked to real wardrobe + environment
catalog entries so the content packet builder does not drift into STYLE_BANK
fallback behavior.

Run:
  python tools/strategy/lena_validate_recipe_catalog_locks_v1.py

Exit 0 = all pass. Exit 1 = any failure.

Does NOT: call Kling, read .env, generate, upload, publish, queue, schedule.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPE_BANK = ROOT / "pipeline/prompt_banks/lena/lena_high_caliber_prompt_recipe_bank_v1.json"
WARDROBE = ROOT / "pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json"
ENV_CATALOG = ROOT / "pipeline/prompt_banks/lena/lena_environment_catalog_v1.json"

_passed = 0
_failed = 0


def run(label, fn):
    global _passed, _failed
    try:
        fn()
        print(f"  PASS  {label}")
        _passed += 1
    except AssertionError as exc:
        print(f"  FAIL  {label}")
        print(f"        {exc}")
        _failed += 1
    except Exception as exc:
        print(f"  ERROR {label}")
        print(f"        {type(exc).__name__}: {exc}")
        _failed += 1


print("=" * 64)
print("  Lena Recipe Catalog Lock Validation v1")
print("=" * 64)

recipes = json.loads(RECIPE_BANK.read_text(encoding="utf-8"))["recipes"]
wardrobe = json.loads(WARDROBE.read_text(encoding="utf-8"))["outfits"]
envs = json.loads(ENV_CATALOG.read_text(encoding="utf-8"))["environments"]

wardrobe_by_id = {o["outfit_id"]: o for o in wardrobe}
env_by_id = {e["environment_id"]: e for e in envs}

active_recipes = [r for r in recipes if r.get("production_status") != "test_only"]
test_only_recipes = [r for r in recipes if r.get("production_status") == "test_only"]


run(
    "TC01  recipe bank JSON valid and parseable",
    lambda: (lambda _: None)(recipes[0]["id"]),
)
run(
    "TC02  wardrobe catalog JSON valid and parseable",
    lambda: (lambda _: None)(wardrobe[0]["outfit_id"]),
)
run(
    "TC03  environment catalog JSON valid and parseable",
    lambda: (lambda _: None)(envs[0]["environment_id"]),
)


def tc04():
    missing = [r["id"] for r in active_recipes if not r.get("wardrobe_outfit_id")]
    assert not missing, (
        "Active recipes missing wardrobe_outfit_id:\n  " + "\n  ".join(missing)
    )


run("TC04  all active recipes have wardrobe_outfit_id", tc04)


def tc05():
    missing = [r["id"] for r in active_recipes if not r.get("environment_id")]
    assert not missing, (
        "Active recipes missing environment_id:\n  " + "\n  ".join(missing)
    )


run("TC05  all active recipes have environment_id", tc05)


def tc06():
    missing = []
    for r in active_recipes:
        oid = r["wardrobe_outfit_id"]
        if oid not in wardrobe_by_id:
            missing.append(f"{r['id']}: unknown outfit '{oid}'")
    assert not missing, "Unknown wardrobe_outfit_id values:\n  " + "\n  ".join(missing)


run("TC06  all active recipe outfit IDs exist in wardrobe catalog", tc06)


def tc07():
    bad = []
    for r in active_recipes:
        oid = r["wardrobe_outfit_id"]
        entry = wardrobe_by_id[oid]
        status = entry.get("status", "")
        if status == "rejected":
            bad.append(f"{r['id']}: outfit '{oid}' is rejected")
        if status == "high_risk" and not r.get("wardrobe_allow_high_risk", False):
            bad.append(
                f"{r['id']}: outfit '{oid}' is high_risk but wardrobe_allow_high_risk is false"
            )
    assert not bad, "Active recipes point at unsafe outfits:\n  " + "\n  ".join(bad)


run("TC07  active recipe outfits are not rejected and respect risk flags", tc07)


def tc08():
    missing = []
    for r in active_recipes:
        eid = r["environment_id"]
        if eid not in env_by_id:
            missing.append(f"{r['id']}: unknown environment '{eid}'")
    assert not missing, "Unknown environment_id values:\n  " + "\n  ".join(missing)


run("TC08  all active recipe environment IDs exist in environment catalog", tc08)


def tc09():
    bad = []
    for r in active_recipes:
        eid = r["environment_id"]
        entry = env_by_id[eid]
        allowed = set(entry.get("allowed_recipe_types", []))
        scene_type = r.get("scene_type")
        content_pillar = r.get("content_pillar")
        if scene_type not in allowed and content_pillar not in allowed:
            bad.append(
                f"{r['id']}: env '{eid}' does not allow scene_type '{scene_type}' "
                f"or content_pillar '{content_pillar}'"
            )
    assert not bad, "Active recipes point at mismatched environments:\n  " + "\n  ".join(bad)


run("TC09  active recipe environments allow the recipe lane", tc09)


def tc10():
    bad = []
    for r in active_recipes:
        oid = r["wardrobe_outfit_id"]
        eid = r["environment_id"]
        if not oid or not eid:
            bad.append(r["id"])
    assert not bad, (
        "These active recipes can still drift into STYLE_BANK fallback:\n  "
        + "\n  ".join(bad)
    )


run("TC10  active recipes cannot drift into STYLE_BANK fallback", tc10)


def tc11():
    missing = [r["id"] for r in active_recipes if r.get("proof_priority") is None]
    assert not missing, (
        "Active recipes missing proof_priority:\n  " + "\n  ".join(missing)
    )


run("TC11  all active recipes declare proof_priority", tc11)


def tc12():
    bad = []
    seen = {}
    for r in active_recipes:
        value = r["proof_priority"]
        if not isinstance(value, int) or value < 1:
            bad.append(f"{r['id']}: invalid proof_priority '{value}'")
            continue
        seen.setdefault(value, []).append(r["id"])
    dupes = [
        f"{priority}: {ids}"
        for priority, ids in sorted(seen.items())
        if len(ids) > 1
    ]
    if dupes:
        bad.extend(f"duplicate proof_priority {item}" for item in dupes)
    assert not bad, "Invalid proof_priority values:\n  " + "\n  ".join(bad)


run("TC12  proof_priority values are positive integers and unique", tc12)


def tc13():
    ordered = sorted(
        active_recipes,
        key=lambda r: (r["proof_priority"], r["id"]),
    )
    print(
        "          active recipe order:",
        [f"{r['proof_priority']}:{r['id']}" for r in ordered],
    )
    print("          active lock count:", len(active_recipes))


run("TC13  report active proof-priority order", tc13)


def tc14():
    assert test_only_recipes, "Expected at least one test_only recipe to remain as a non-production lane"
    print("          test_only recipes:", [r["id"] for r in test_only_recipes])


run("TC14  test_only recipe lanes remain explicitly separated", tc14)

total_tests = _passed + _failed
print("=" * 64)
print(f"  Results: {_passed} passed  /  {_failed} failed  /  {total_tests} total")
print(f"  Active recipes: {len(active_recipes)}  |  Test-only recipes: {len(test_only_recipes)}")
print("=" * 64)
print()
if _failed:
    print("  RECIPE CATALOG LOCK VALIDATION: FAILED")
    print()
    print("  NO API call.  NO generation.  NO upload.")
    print("  NO publish.   NO queue.       NO schedule.")
    sys.exit(1)
else:
    print("  RECIPE CATALOG LOCK VALIDATION: PASSED")
    print()
    print("  NO API call.  NO generation.  NO upload.")
    print("  NO publish.   NO queue.       NO schedule.")
    sys.exit(0)
