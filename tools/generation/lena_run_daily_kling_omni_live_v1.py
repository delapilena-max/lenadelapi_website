import argparse, os, subprocess, sys

ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON    = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
LIVE_TEST = os.path.join(ROOT, "tools", "generation",
                         "lena_kling_omni_image_public_api_live_test_v1.py")
HERBY_ID  = 313543353069325

SLOTS = [
    {"key": "morning",   "slot_type": "morning_lifestyle_photo",         "extras": []},
    {"key": "afternoon", "slot_type": "lifestyle_photo",                  "extras": []},
    {"key": "evening",   "slot_type": "evening_candid_photo",            "extras": []},
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--execute-live", action="store_true", dest="execute_live")
    p.add_argument("--confirm-daily-three-photo-kling-omni-live",
                   action="store_true", dest="confirm_live")
    args = p.parse_args()

    d    = args.date
    dc   = d.replace("-", "")
    live = args.execute_live and args.confirm_live
    batch = f"lena_kling_omni_daily_{dc}.json"

    print(f"[lena_run_daily_kling_omni_live_v1] date  : {d}")
    print(f"[lena_run_daily_kling_omni_live_v1] batch : {batch}")
    print(f"[lena_run_daily_kling_omni_live_v1] live  : {live}")
    if live:
        print("[lena_run_daily_kling_omni_live_v1] *** LIVE MODE — CREDITS WILL BE SPENT ***")

    results = []
    for s in SLOTS:
        rid = f"kling_omni_daily_{s['key']}_{dc}"
        cmd = [PYTHON, LIVE_TEST,
               "--date", d, "--batch", batch,
               "--slot", s["slot_type"], "--result-id", rid]
        for eid in s["extras"]:
            cmd += ["--extra-element-id", str(eid)]
        if live:
            cmd += ["--execute-live", "--confirm-single-slot-official-omni-test"]
        print(f"\n[runner] slot={s['slot_type']}  live={live}")
        rc = subprocess.run(cmd, cwd=ROOT).returncode
        results.append({"slot": s["slot_type"], "rc": rc, "rid": rid})

    print("\n" + "=" * 60)
    print("  LENA DAILY KLING OMNI RUNNER — SUMMARY")
    print("=" * 60)
    for r in results:
        tag = "PASS" if r["rc"] == 0 else f"FAIL(rc={r['rc']})"
        print(f"  [{tag}] {r['slot']}")
        print(f"         result_id: {r['rid']}")
    all_ok = all(r["rc"] == 0 for r in results)
    print(f"\n  live       : {live}")
    print(f"  all_passed : {all_ok}")
    print("=" * 60)
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
