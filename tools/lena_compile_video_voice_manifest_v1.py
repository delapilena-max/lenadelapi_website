from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.voice.lena_elevenlabs_voice_contract_v1 import build_video_voice_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a Lena video JSON spec into ElevenLabs voice packets")
    parser.add_argument("--video-spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    video_spec = json.loads(args.video_spec.read_text(encoding="utf-8"))
    manifest = build_video_voice_manifest(video_spec)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for packet in manifest["voice_packets"]:
        path = args.output_dir / f"{packet['shot_id']}_voice_packet.json"
        path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = args.output_dir / "voice_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "manifest": str(manifest_path), "packet_count": manifest["voice_packet_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
