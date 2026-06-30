from __future__ import annotations
import json
import sys

_LEGACY_FLAG = "--allow-legacy-openart-seedance"
if _LEGACY_FLAG not in sys.argv:
    print(json.dumps({
        "ok": False,
        "legacy_blocked": True,
        "script": "wire_lena_v1_5_openart_seedance_provider.py",
        "message": (
            "This script patches run_lena_generate_daily.ps1 to wire the OpenArt/Seedance "
            "provider layer, which is no longer the active Lena path. "
            "The daily generation script already routes to Kling directly. "
            "Do not run this — it would re-insert a broken legacy block."
        ),
        "use_instead": [
            "tools/lena_strategy_autonomy_run_v1.py",
            "pipeline/influencer_nodes/lena/provider_router.json",
        ],
        "override_flag_required": _LEGACY_FLAG,
    }, indent=2))
    sys.exit(1)

from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "run_lena_generate_daily.ps1"
def fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1
def main() -> int:
    if not WRAPPER.exists():
        return fail(f"missing wrapper: {WRAPPER}")
    required = [ROOT / "tools" / "lena_route_provider_v1_5.py", ROOT / "tools" / "lena_prepare_openart_seedance_workorders_v1_5.py", ROOT / "tools" / "lena_validate_provider_layer_v1_5.py"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        return fail("missing required files:\\n" + "\\n".join(missing))
    s = WRAPPER.read_text(encoding="utf-8-sig")
    if "STEP 1C5: OpenArt/Seedance provider route v1.5" in s:
        print("OK: v1.5 provider layer already wired")
        return 0
    marker = '  Write-Host "STEP 1D: credit guard v1.3"'
    if marker not in s:
        return fail("could not find STEP 1D marker")
    backup = WRAPPER.with_name(f"{WRAPPER.name}.bak_v1_5_openart_seedance_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    backup.write_text(s, encoding="utf-8")
    block_lines = [
        '  Write-Host "STEP 1C5: OpenArt/Seedance provider route v1.5"',
        '  & $Python ".\\\\tools\\\\lena_route_provider_v1_5.py" $WorkorderPath',
        '  if ($LASTEXITCODE -ne 0) {',
        '    throw "OpenArt/Seedance provider routing failed."',
        '  }',
        '',
        '  Write-Host "STEP 1C6: export OpenArt/Seedance manual workorders v1.5"',
        '  & $Python ".\\\\tools\\\\lena_prepare_openart_seedance_workorders_v1_5.py" $WorkorderPath',
        '  if ($LASTEXITCODE -ne 0) {',
        '    throw "OpenArt/Seedance manual workorder export failed."',
        '  }',
        '',
    ]
    s = s.replace(marker, "\\n".join(block_lines) + marker, 1)
    WRAPPER.write_text(s, encoding="utf-8")
    print("OK: wired v1.5 OpenArt/Seedance provider routing before credit guard")
    print(f"backup: {backup}")
    print("NOTE: legacy executor is not replaced yet. This is safe staged migration.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
