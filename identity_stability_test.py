#!/usr/bin/env python3
"""
identity_stability_test.py  —  run_001
Identity-stability inspector for AI reference anchors.
Nic / nodes/ai_lady project

Usage:
    python identity_stability_test.py

Requires:
    pip install opencv-python-headless Pillow numpy

Files needed in nodes/ai_lady/:
    ref_face.png
    ref_face_backup2.png
"""

import cv2
import json
import pathlib
import sys
import textwrap
import datetime
import numpy as np
from collections import Counter
from PIL import Image, ImageEnhance, ImageFilter

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
SCRIPT_DIR   = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR / "nodes" / "ai_lady"

REFS = {
    "primary_neutral_A": PROJECT_ROOT / "ref_face.png",
    "primary_neutral_B": PROJECT_ROOT / "ref_face.png",
    "backup_A":          PROJECT_ROOT / "ref_face_backup2.png",
    "backup_B":          PROJECT_ROOT / "ref_face_backup2.png",
    "backup_C":          PROJECT_ROOT / "ref_face_backup2.png",
}

OUT_DIR        = PROJECT_ROOT / "tests" / "run_001"
PREVIEW_SIZE   = (384, 512)
PASS_THRESHOLD = 60

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def to_python_type(obj):
    """Recursively convert numpy scalars to native Python types for JSON."""
    if isinstance(obj, dict):
        return {k: to_python_type(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_python_type(v) for v in obj]
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.bool_):    return bool(obj)
    return obj


def load_bgr(path):
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Cannot load image: {path}")
    return img


def bgr_to_pil(bgr):
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def pil_to_bgr(pil):
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def detect_faces(gray):
    clf = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = clf.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(60, 60))
    return list(faces) if len(faces) else []


def detect_eyes(gray, face_roi):
    x, y, w, h = face_roi
    upper = gray[y:y + h // 2, x:x + w]
    clf   = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    eyes  = clf.detectMultiScale(upper, scaleFactor=1.05, minNeighbors=3, minSize=(15, 15))
    return list(eyes) if len(eyes) else []


def symmetry_score(gray, face):
    x, y, w, h = face
    roi     = gray[y:y + h, x:x + w].astype(np.float32)
    flipped = cv2.flip(roi, 1)
    return round(100.0 - (cv2.absdiff(roi, flipped).mean() / 255.0 * 100.0), 1)


def lighting_score(bgr, face):
    x, y, w, h = face
    g = cv2.cvtColor(bgr[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY).astype(np.float32)
    return {
        "mean_brightness":    round(float(g.mean()), 1),
        "std_brightness":     round(float(g.std()), 1),
        "highlight_clip_pct": round(float((g > 245).mean() * 100), 2),
        "shadow_clip_pct":    round(float((g < 10).mean() * 100), 2),
    }


def artifact_score(bgr, face):
    x, y, w, h = face
    g = cv2.cvtColor(bgr[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    return {"laplacian_var": round(float(cv2.Laplacian(g, cv2.CV_64F).var()), 1)}


def ear_hair_check(bgr, face):
    x, y, w, h = face
    W = bgr.shape[1]
    left   = bgr[y:y + h, max(0, x - 20):x]
    right  = bgr[y:y + h, x + w:min(W, x + w + 20)]
    centre = bgr[y:y + h, x + w // 4:x + 3 * w // 4]
    lv     = float(left.std())   if left.size   else 0.0
    rv     = float(right.std())  if right.size  else 0.0
    cv_    = float(centre.std())
    ratio  = round((lv + rv) / (2 * cv_ + 1e-6), 2)
    return {"edge_to_centre_variance_ratio": ratio, "edge_flag": ratio > 1.5}


# ──────────────────────────────────────────────
# VARIANT FACTORY
# ──────────────────────────────────────────────

def make_variant(bgr, variant):
    pil  = bgr_to_pil(bgr)
    w, h = pil.size

    if variant == "primary_neutral_A":
        m   = int(min(w, h) * 0.08)
        pil = pil.crop((m, m, w - m, h - m))

    elif variant == "primary_neutral_B":
        pil = ImageEnhance.Brightness(pil).enhance(1.12)
        pil = ImageEnhance.Sharpness(pil).enhance(1.15)

    elif variant == "backup_A":
        pil = ImageEnhance.Contrast(pil).enhance(1.08)

    elif variant == "backup_B":
        pil = ImageEnhance.Contrast(pil).enhance(1.15)
        pil = ImageEnhance.Sharpness(pil).enhance(1.10)

    elif variant == "backup_C":
        arr = np.array(pil, dtype=np.float32)
        arr[:, :, 0] = np.clip(arr[:, :, 0] * 1.08, 0, 255)
        arr[:, :, 2] = np.clip(arr[:, :, 2] * 0.92, 0, 255)
        pil = Image.fromarray(arr.astype(np.uint8))
        pil = ImageEnhance.Brightness(pil).enhance(1.05)

    pil = pil.resize(PREVIEW_SIZE, Image.LANCZOS)
    return pil_to_bgr(np.array(pil))


# ──────────────────────────────────────────────
# ANNOTATION
# ──────────────────────────────────────────────

def annotate_preview(bgr, faces, label, passed, score):
    out    = bgr.copy()
    colour = (0, 220, 80) if passed else (0, 60, 230)
    for (x, y, w, h) in faces:
        cv2.rectangle(out, (x, y), (x + w, y + h), colour, 2)
    badge = (30, 180, 30) if passed else (30, 30, 200)
    cv2.rectangle(out, (0, 0), (210, 28), badge, -1)
    cv2.putText(out, f"{'PASS' if passed else 'FAIL'}  {score}/100",
                (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, label, (5, out.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
    return out


# ──────────────────────────────────────────────
# SCORING
# ──────────────────────────────────────────────

PREVIEW_META = [
    ("preview1", "primary_neutral_A", "Primary — neutral tight crop"),
    ("preview2", "primary_neutral_B", "Primary — brightness+sharpen"),
    ("preview3", "backup_A",          "Backup — baseline contrast"),
    ("preview4", "backup_B",          "Backup — contrast+sharpen boost"),
    ("preview5", "backup_C",          "Backup — warm grade"),
]


def score_preview(m):
    score, issues = 100, []

    if not m["face_detected"]:
        score -= 30; issues.append("No face detected")

    n = m.get("num_eyes", 0)
    if n < 2:
        score -= 20; issues.append(f"Only {n} eye(s) detected (expected 2)")

    if m.get("eye_y_delta_pct", 0) > 10:
        score -= 10; issues.append(f"Eye Y-misalignment: {m['eye_y_delta_pct']:.1f}%")

    if m.get("symmetry_score", 100) < 68:
        score -= 10; issues.append(f"Low bilateral symmetry: {m['symmetry_score']}")

    mb = m.get("mean_brightness", 128)
    if mb < 80:
        score -= 8; issues.append(f"Under-exposed (brightness {mb})")
    elif mb > 195:
        score -= 8; issues.append(f"Over-exposed (brightness {mb})")

    if m.get("highlight_clip_pct", 0) > 2.0:
        score -= 6; issues.append(f"Highlight clipping: {m['highlight_clip_pct']}%")

    if m.get("shadow_clip_pct", 0) > 3.0:
        score -= 6; issues.append(f"Shadow crushing: {m['shadow_clip_pct']}%")

    lv = m.get("laplacian_var", 150)
    if lv < 30:
        score -= 8; issues.append(f"Too blurry (Laplacian={lv})")
    elif lv > 600:
        score -= 8; issues.append(f"Artifacts/noise (Laplacian={lv})")

    if m.get("edge_flag", False):
        score -= 5; issues.append("Hair/ear edge anomaly")

    return max(0, score), issues


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def analyse(ref_path, variant, label):
    bgr_var = make_variant(load_bgr(ref_path), variant)
    gray    = cv2.cvtColor(bgr_var, cv2.COLOR_BGR2GRAY)
    faces   = detect_faces(gray)
    m       = {"face_detected": len(faces) > 0}

    if faces:
        face = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]
        x, y, w, h = face
        eyes = detect_eyes(gray, face)
        m["num_eyes"] = len(eyes)
        if len(eyes) >= 2:
            ey = [e[1] + e[3] // 2 for e in eyes[:2]]
            m["eye_y_delta_pct"] = round(abs(ey[0] - ey[1]) / h * 100, 1)
        else:
            m["eye_y_delta_pct"] = 0
        m["symmetry_score"] = symmetry_score(gray, face)
        m.update(lighting_score(bgr_var, face))
        m.update(artifact_score(bgr_var, face))
        m.update(ear_hair_check(bgr_var, face))
        score, issues = score_preview(m)
        passed    = score >= PASS_THRESHOLD
        annotated = annotate_preview(bgr_var, [face], label, passed, score)
    else:
        score, issues = score_preview(m)
        passed    = False
        annotated = bgr_var.copy()
        cv2.putText(annotated, f"FAIL {score}/100 — no face", (5, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 220), 1)

    return annotated, m, score, issues, passed


def run_tests():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[run_001] Output → {OUT_DIR}\n")

    results      = []
    failed_badly = []

    for (fname, variant, label) in PREVIEW_META:
        ref_path = REFS[variant]
        print(f"  → {fname} | {label}")

        if not ref_path.exists():
            print(f"     ⚠  Missing: {ref_path.name}")
            results.append({"preview": fname, "variant": variant, "label": label,
                            "passed": False, "score": 0,
                            "issues": [f"Reference file missing: {ref_path.name}"], "metrics": {}})
            continue  # config problem — don't trigger rescue

        annotated, metrics, score, issues, passed = analyse(ref_path, variant, label)
        cv2.imwrite(str(OUT_DIR / f"{fname}.png"), annotated)
        print(f"     score={score}/100  passed={passed}  issues={issues}")

        results.append({"preview": fname, "variant": variant, "label": label,
                        "passed": passed, "score": score, "issues": issues, "metrics": metrics})

        if score < 40:
            failed_badly.append(fname)

    # ── Auto-rescue ──────────────────────────────────────────────────────────
    backup_rescue = None
    if failed_badly:
        print(f"\n[run_001] ⚡ Rescue triggered for: {failed_badly}")
        rp = PROJECT_ROOT / "ref_face_backup2.png"
        if rp.exists():
            annotated, metrics, score, issues, passed = analyse(rp, "backup_A", "Rescue — backup anchor")
            cv2.imwrite(str(OUT_DIR / "preview_rescue.png"), annotated)
            backup_rescue = {"preview": "preview_rescue", "variant": "backup_A",
                             "label": "Rescue — backup anchor",
                             "passed": passed, "score": score, "issues": issues, "metrics": metrics}
            results.append(backup_rescue)
            print(f"     rescue score={score}/100  passed={passed}")

    # ── Report ───────────────────────────────────────────────────────────────
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_score = sorted(results, key=lambda r: r["score"], reverse=True)
    best3, worst2 = by_score[:3], by_score[-2:]

    lines = ["=" * 62,
             "  IDENTITY STABILITY TEST — run_001",
             f"  Project: nodes/ai_lady     Timestamp: {ts}",
             "=" * 62, "",
             "PREVIEW RESULTS", "-" * 40]

    for r in results:
        tag = "✓ PASS" if r["passed"] else "✗ FAIL"
        lines.append(f"  {r['preview']:<18} {tag}  {r['score']:>3}/100  — {r['label']}")
        for i in r["issues"]:
            lines.append(f"              ↳ {i}")

    lines += ["", "BEST 3",  "-" * 40] + [f"  {r['preview']}  ({r['score']}/100)  {r['label']}" for r in best3]
    lines += ["", "WORST 2", "-" * 40] + [f"  {r['preview']}  ({r['score']}/100)  {r['label']}" for r in worst2]

    all_issues   = [i for r in results for i in r["issues"]]
    issue_counts = Counter(all_issues)
    lines += ["", "COMMON FAILURE MODES", "-" * 40]
    if issue_counts:
        for iss, cnt in issue_counts.most_common(6):
            lines.append(f"  [{cnt}x]  {iss}")
    else:
        lines.append("  None — clean run.")

    recs = []
    if sum(1 for r in results if r.get("metrics",{}).get("num_eyes", 2) < 2):
        recs.append("EYES: Tighten crop to ≥60% face fill. Add CodeFormer/GFPGAN at strength 0.5.")
    if sum(1 for r in results if r.get("metrics",{}).get("symmetry_score", 100) < 68):
        recs.append("SYMMETRY: Flip-augment ref, sharpen +15%, re-centre crop.")
    if sum(1 for r in results if r.get("metrics",{}).get("laplacian_var", 150) < 50):
        recs.append("BLUR: Sharpen ref +20–25%. Increase pipeline denoise +0.05.")
    if sum(1 for r in results if r.get("metrics",{}).get("mean_brightness", 128) < 80):
        recs.append("UNDEREXPOSED: Gamma +15% on ref, or CFG +0.5 + 'bright lighting' prompt.")
    if sum(1 for r in results if r.get("metrics",{}).get("mean_brightness", 128) > 195):
        recs.append("OVEREXPOSED: Brightness −12%, white point capped at 235.")
    if sum(1 for r in results if r.get("metrics",{}).get("highlight_clip_pct", 0) > 2):
        recs.append("CLIPPING: −8% brightness on ref, white point 240.")
    if sum(1 for r in results if r.get("metrics",{}).get("shadow_clip_pct", 0) > 3):
        recs.append("SHADOW CRUSH: Lift black point to 10 in Levels.")
    if sum(1 for r in results if r.get("metrics",{}).get("edge_flag", False)):
        recs.append("EDGES: Crop 5–8% L/R to remove stray hair, or inpaint background first.")
    if not recs:
        recs.append("All references solid. Proceed to full-res run.")

    lines += ["", "RECOMMENDED FIXES", "-" * 40]
    for i, rec in enumerate(recs, 1):
        for j, chunk in enumerate(textwrap.wrap(rec, 58)):
            lines.append(f"  {i}. {chunk}" if j == 0 else f"     {chunk}")

    pass_count = sum(1 for r in results if r["passed"] and r["preview"] != "preview_rescue")
    core       = [r for r in results if r["preview"] != "preview_rescue"]
    avg_score  = round(sum(r["score"] for r in core) / max(1, len(core)), 1)

    if pass_count == 5:
        one_liner = "✅ All 5 passed — references stable. Proceed to full-res generation."
    elif pass_count >= 3:
        one_liner = f"⚠️  {pass_count}/5 passed (avg {avg_score}/100). Apply fixes above, then re-run."
    else:
        one_liner = f"🔴 {pass_count}/5 passed (avg {avg_score}/100). Use backup anchor; rework primary ref."

    lines += ["", "NEXT STEP", "-" * 40]
    for chunk in textwrap.wrap(one_liner, 60):
        lines.append(f"  {chunk}")
    lines += ["", "=" * 62]

    report = "\n".join(lines)
    (OUT_DIR / "report_run_001.txt").write_text(report, encoding="utf-8")
    print(f"\n[run_001] Report saved.")

    summary = {
        "run_id": "run_001", "timestamp": ts,
        "pass_threshold": PASS_THRESHOLD,
        "total_previews": len(core),
        "pass_count": pass_count,
        "avg_score": avg_score,
        "rescue_triggered": backup_rescue is not None,
        "previews": [
            {"file": r["preview"] + ".png", "label": r["label"],
             "passed": r["passed"], "score": r["score"], "issues": r["issues"],
             "key_metrics": {k: r["metrics"][k] for k in
                             ["num_eyes","symmetry_score","mean_brightness","laplacian_var","edge_flag"]
                             if k in r.get("metrics", {})}}
            for r in results
        ],
        "one_liner": one_liner,
    }

    (OUT_DIR / "report_run_001_summary.json").write_text(
        json.dumps(to_python_type(summary), indent=2), encoding="utf-8")
    print("[run_001] JSON saved.")
    print("\n" + report)
    return summary


if __name__ == "__main__":
    print("=" * 62)
    print("  Identity Stability Test  —  run_001  —  nodes/ai_lady")
    print("=" * 62 + "\n")
    try:
        run_tests()
        print("\nDone. Files in:", OUT_DIR)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
