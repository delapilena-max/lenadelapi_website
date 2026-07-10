from __future__ import annotations

# Lena approved-music pool -- eligibility filtering + deterministic track
# selection, shared by any destination-specific media-preparation tool
# (Story video today, Reel audio later).
#
# The ONLY source of truth for what tracks exist is
# assets/royaltyfree audio/manifest.json (built by a separate, earlier,
# read-only audit -- this module never writes to that manifest, never
# downloads music, never calls any provider/network surface, never invents
# a license fact). A track is eligible only when every one of these is
# independently re-verified against the real file on disk -- never trusted
# from the manifest's self-reported claim alone:
#   - commercial_use_allowed is exactly True
#   - license_type is a non-empty string
#   - license_proof_reference is a non-empty string
#   - the local file actually exists at local_path
#   - the file's real SHA-256 matches the manifest's recorded sha256
#     (catches drift/corruption/replacement since the manifest was built)
#   - ffprobe can read a real audio stream from the file
#
# Any single check failing excludes that one track (not a hard crash) --
# but if EVERY track is excluded, selection fails closed with a clear
# error, never silently returns nothing usable.
#
# Selection is deterministic, not random: sha256(slot_id) mod
# len(eligible_tracks), against the eligible list in stable track_id sort
# order. Same slot_id + same eligible-track set (same manifest content) =
# same chosen track, always. No BPM/mood semantic matching -- that data is
# null for all 15 tracks today and this module never pretends otherwise.

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_MANIFEST_PATH = ROOT / "assets" / "royaltyfree audio" / "manifest.json"


class MusicPoolError(Exception):
    """Raised when no eligible track can be selected. Never caught
    silently by callers -- there is no silent-Story/silent-Reel fallback
    anywhere in this module."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_readable_audio_stream(path: Path) -> bool:
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode != 0:
            return False
        data = json.loads(probe.stdout)
        return any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    except Exception:
        return False


def load_manifest(manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    path = manifest_path or DEFAULT_MANIFEST_PATH
    if not path.exists():
        raise MusicPoolError(f"music pool manifest does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MusicPoolError(f"music pool manifest failed to parse: {path}: {exc}") from exc


def check_track_eligibility(track: Dict[str, Any]) -> List[str]:
    """Read-only. Returns a list of human-readable reasons the track is
    NOT eligible (empty list means eligible). Never raises -- callers
    decide what to do with an ineligible track."""
    reasons: List[str] = []

    if track.get("commercial_use_allowed") is not True:
        reasons.append(f"commercial_use_allowed is {track.get('commercial_use_allowed')!r}, not True")
    if not str(track.get("license_type") or "").strip():
        reasons.append("license_type is missing/empty")
    if not str(track.get("license_proof_reference") or "").strip():
        reasons.append("license_proof_reference is missing/empty")

    local_path = Path(str(track.get("local_path") or ""))
    if not track.get("local_path") or not local_path.exists():
        reasons.append(f"local_path does not exist: {local_path}")
        return reasons  # remaining checks need the real file; can't proceed

    real_sha256 = _sha256_file(local_path)
    manifest_sha256 = track.get("sha256")
    if real_sha256 != manifest_sha256:
        reasons.append(f"real SHA-256 {real_sha256!r} does not match manifest sha256 {manifest_sha256!r}")

    if not _has_readable_audio_stream(local_path):
        reasons.append("no readable audio stream found (ffprobe)")

    return reasons


def load_eligible_tracks(manifest_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read-only. Returns eligible tracks in stable track_id sort order.
    Never raises for individual ineligible tracks -- only raises
    MusicPoolError if zero tracks end up eligible."""
    manifest = load_manifest(manifest_path)
    tracks = sorted(manifest.get("tracks", []), key=lambda t: str(t.get("track_id") or ""))

    eligible: List[Dict[str, Any]] = []
    for track in tracks:
        reasons = check_track_eligibility(track)
        if not reasons:
            eligible.append(track)

    if not eligible:
        raise MusicPoolError(
            "zero eligible tracks in the approved music pool -- refusing to select any track "
            "(fail closed, never a silent Story/Reel)"
        )
    return eligible


def select_track_deterministic(slot_id: str, manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    """Deterministic: same slot_id + same eligible-track set always
    selects the same track. Raises MusicPoolError if no eligible track
    exists. Never random, never network, never downloads."""
    if not slot_id or not slot_id.strip():
        raise MusicPoolError("slot_id must not be empty -- selection must be tied to a real identity")

    eligible = load_eligible_tracks(manifest_path)
    digest = hashlib.sha256(slot_id.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(eligible)
    return eligible[index]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Read-only music-pool eligibility audit and deterministic track selection."
    )
    parser.add_argument("--slot", default=None, help="If given, print the deterministically selected track for this slot_id.")
    parser.add_argument("--manifest", default=None, help="Override the manifest.json path.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve() if args.manifest else None

    try:
        manifest = load_manifest(manifest_path)
        report: Dict[str, Any] = {"ok": True, "track_count": len(manifest.get("tracks", [])), "eligibility": []}
        for track in sorted(manifest.get("tracks", []), key=lambda t: str(t.get("track_id") or "")):
            reasons = check_track_eligibility(track)
            report["eligibility"].append({
                "track_id": track.get("track_id"),
                "filename": track.get("filename"),
                "eligible": not reasons,
                "reasons": reasons,
            })
        report["eligible_count"] = sum(1 for e in report["eligibility"] if e["eligible"])

        if args.slot:
            selected = select_track_deterministic(args.slot, manifest_path)
            report["selected_for_slot"] = {
                "slot_id": args.slot,
                "track_id": selected.get("track_id"),
                "filename": selected.get("filename"),
                "local_path": selected.get("local_path"),
                "sha256": selected.get("sha256"),
                "duration_seconds": selected.get("duration_seconds"),
            }
    except MusicPoolError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
