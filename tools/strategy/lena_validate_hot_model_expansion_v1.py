"""
Lena Hot Model Expansion Validation v1

Manual dry-run only. Not CI-wired.
Validates wardrobe catalog expansion + environment catalog.

Run: python tools/strategy/lena_validate_hot_model_expansion_v1.py
Exit 0 = all pass.  Exit 1 = any failure.

Does NOT: call Kling, read .env, generate, upload, publish, queue, schedule.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WARDROBE = ROOT / "pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json"
ENV_CATALOG = ROOT / "pipeline/prompt_banks/lena/lena_environment_catalog_v1.json"

FORBIDDEN_OUTFIT = [
    "hoodie","jogger","joggers","grocery","shopping","basket","cart",
    "produce","fruit aisle","nothing underneath","lingerie","underwear",
]
FORBIDDEN_BODY = [
    "full bust","hip curve","fuller thighs","proportions","skin tone","face","hair",
]
FORBIDDEN_ENV = [
    "grocery","shopping","produce","basket","cart","hotel room",
    "hotel bedroom","readable logo","readable text",
]

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
print("  Lena Hot Model Expansion Validation v1")
print("=" * 64)

wardrobe = json.loads(WARDROBE.read_text(encoding="utf-8"))
env_catalog = json.loads(ENV_CATALOG.read_text(encoding="utf-8"))
outfits = wardrobe["outfits"]
envs = env_catalog["environments"]
new_outfits = [o for o in outfits if o.get("outfit_id","").startswith("wc_p")]

run("TC01  wardrobe JSON valid and parseable",
    lambda: (lambda _: None)(outfits[0]["outfit_id"]))

run("TC02  environment catalog JSON valid and parseable",
    lambda: (lambda _: None)(envs[0]["environment_id"]))

def tc03():
    total = len(outfits)
    assert total >= 120, f"total outfits {total} < 120 minimum"
run("TC03  total wardrobe count >= 120", tc03)

def tc04():
    n = len(new_outfits)
    assert n > 0, "No new production wardrobe entries (wc_p*) found"
    assert n >= 69, f"Only {n} new entries; expected >= 69 to reach 120 total"
run("TC04  new production wardrobe entries exist (>= 69 wc_p* entries)", tc04)

def tc05():
    total = len(envs)
    assert total >= 80, f"environment count {total} < 80 minimum"
run("TC05  environment count >= 80", tc05)

def tc06():
    bad = []
    for o in new_outfits:
        prompt = o.get("prompt","").lower()
        for term in FORBIDDEN_OUTFIT:
            if term.lower() in prompt:
                bad.append(f"{o['outfit_id']}: forbidden term '{term}'")
    assert not bad, "Forbidden outfit prompt terms found:\n  " + "\n  ".join(bad)
run("TC06  no forbidden outfit prompt terms", tc06)

def tc07():
    bad = []
    for o in new_outfits:
        prompt = o.get("prompt","").lower()
        for term in FORBIDDEN_BODY:
            if term.lower() in prompt:
                bad.append(f"{o['outfit_id']}: body/identity term '{term}'")
    assert not bad, "Forbidden body/identity terms found:\n  " + "\n  ".join(bad)
run("TC07  no body/identity terms in outfit prompts", tc07)

def tc08():
    bad = []
    for e in envs:
        fragment = (e.get("prompt_fragment","") + " " + e.get("background_detail","")).lower()
        for term in FORBIDDEN_ENV:
            if term.lower() in fragment:
                bad.append(f"{e['environment_id']}: forbidden env term '{term}'")
    assert not bad, "Forbidden environment terms found:\n  " + "\n  ".join(bad)
run("TC08  no forbidden environment terms", tc08)

def tc09():
    ids = [o["outfit_id"] for o in outfits]
    dupes = [i for i in ids if ids.count(i) > 1]
    assert not dupes, f"Duplicate outfit IDs: {list(set(dupes))}"
run("TC09  all outfit IDs unique", tc09)

def tc10():
    ids = [e["environment_id"] for e in envs]
    dupes = [i for i in ids if ids.count(i) > 1]
    assert not dupes, f"Duplicate environment IDs: {list(set(dupes))}"
run("TC10  all environment IDs unique", tc10)

REQUIRED_OUTFIT = ["outfit_id","name","style_lane","production_lane","scene_fit",
                   "season","occasion","coverage_level","body_visibility",
                   "risk_tags","prompt","avoid_terms","status","notes"]
REQUIRED_ENV = ["environment_id","name","production_lane","allowed_recipe_types",
                "camera_position","framing","lighting","background_detail",
                "realism_details","props_allowed","props_blocked","mood",
                "risk_tags","prompt_fragment","status","notes"]

def tc11():
    bad = []
    for o in new_outfits:
        for f in REQUIRED_OUTFIT:
            if f not in o:
                bad.append(f"{o.get('outfit_id','?')}: missing '{f}'")
    assert not bad, "Missing required outfit fields:\n  " + "\n  ".join(bad)
run("TC11  required outfit fields present on new entries", tc11)

def tc12():
    bad = []
    for e in envs:
        for f in REQUIRED_ENV:
            if f not in e:
                bad.append(f"{e.get('environment_id','?')}: missing '{f}'")
    assert not bad, "Missing required environment fields:\n  " + "\n  ".join(bad)
run("TC12  required environment fields present on all entries", tc12)

def tc13():
    bad = []
    for o in new_outfits:
        s = o.get("status","")
        if s not in ("untested","high_risk"):
            bad.append(f"{o['outfit_id']}: status={s!r} (must be untested or high_risk)")
    assert not bad, "New outfits with invalid status:\n  " + "\n  ".join(bad)
run("TC13  all new outfit entries are untested or high_risk (not approved)", tc13)

def tc14():
    bad = []
    for e in envs:
        s = e.get("status","")
        if s not in ("untested","high_risk"):
            bad.append(f"{e['environment_id']}: status={s!r} (must be untested or high_risk)")
    assert not bad, "Environments with invalid status:\n  " + "\n  ".join(bad)
run("TC14  all environment entries are untested or high_risk (not approved)", tc14)

def tc15():
    lanes = {}
    for o in new_outfits:
        pl = o.get("production_lane","MISSING")
        lanes[pl] = lanes.get(pl,0) + 1
    assert "going_out" in lanes, "No going_out entries in new outfits"
    assert "street_glam" in lanes, "No street_glam entries"
    assert "mirror_fitcheck" in lanes, "No mirror_fitcheck entries"
    assert "beauty_selfie_vanity" in lanes, "No beauty_selfie_vanity entries"
    print(f"          production_lane counts: {dict(sorted(lanes.items()))}")
run("TC15  new outfits cover all required production_lane values", tc15)

def tc16():
    lanes = {}
    for e in envs:
        pl = e.get("production_lane","MISSING")
        lanes[pl] = lanes.get(pl,0) + 1
    assert "mirror_fitcheck" in lanes, "No mirror_fitcheck environments"
    assert "going_out" in lanes, "No going_out environments"
    assert "street_glam" in lanes, "No street_glam environments"
    assert "rooftop_night_city" in lanes, "No rooftop_night_city environments"
    assert "editorial_flash" in lanes, "No editorial_flash environments"
    assert "car_elevator" in lanes, "No car_elevator environments"
    assert "beauty_selfie_vanity" in lanes, "No beauty_selfie_vanity environments"
    assert "gym_glam" in lanes, "No gym_glam environments"
    assert "apartment_elevated" in lanes, "No apartment_elevated environments"
    print(f"          environment production_lane counts: {dict(sorted(lanes.items()))}")
run("TC16  environment catalog covers all required production_lane values", tc16)

total_tests = _passed + _failed
print("=" * 64)
print(f"  Results: {_passed} passed  /  {_failed} failed  /  {total_tests} total")
print(f"  Wardrobe total: {len(outfits)}  |  New (wc_p*): {len(new_outfits)}")
print(f"  Environment total: {len(envs)}")
print("=" * 64)
print()
if _failed:
    print("  HOT MODEL EXPANSION VALIDATION: FAILED")
    print()
    print("  NO API call.  NO generation.  NO upload.")
    print("  NO publish.   NO queue.       NO schedule.")
    sys.exit(1)
else:
    print("  HOT MODEL EXPANSION VALIDATION: PASSED")
    print()
    print("  NO API call.  NO generation.  NO upload.")
    print("  NO publish.   NO queue.       NO schedule.")
    sys.exit(0)
