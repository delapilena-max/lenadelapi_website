import shutil
from pathlib import Path

SRC = Path("nodes/ai_lady")
DST = Path("assets/face_reference")

REFS = [
    "ref_face.png",
    "ref_face_backup2.png",
]

DST.mkdir(parents=True, exist_ok=True)

print("[sync_refs] Copying validated refs → assets/face_reference/\n")
ok = 0
for name in REFS:
    src = SRC / name
    if src.exists():
        shutil.copy2(src, DST / name)
        print(f"  ✓  {name}")
        ok += 1
    else:
        print(f"  ✗  MISSING: {name}")

print(f"\n[sync_refs] Done. {ok}/{len(REFS)} refs synced.")
