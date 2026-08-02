from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.voice.lena_elevenlabs_voice_contract_v1 import VoiceContractError

API_ROOT = "https://api.elevenlabs.io/v1"


class ElevenLabsExecutionError(RuntimeError):
    pass


def _load_packet(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "lena_elevenlabs_voice_packet_v1":
        raise ElevenLabsExecutionError("unsupported voice packet schema")
    if payload.get("provider") != "elevenlabs" or payload.get("character_id") != "lena":
        raise ElevenLabsExecutionError("voice packet is not a governed Lena ElevenLabs packet")
    if payload.get("generation_order") != "audio_before_video" or payload.get("timestamps_required") is not True:
        raise ElevenLabsExecutionError("voice continuity requirements are missing")
    return payload


def _extension(output_format: str) -> str:
    return ".mp3" if output_format.startswith("mp3_") else ".pcm"


def execute(packet_path: Path, output_dir: Path, *, live: bool = False, timeout_seconds: int = 90) -> dict[str, Any]:
    packet = _load_packet(packet_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    shot_id = packet["shot_id"]
    output_format = packet["output_format"]
    audio_path = output_dir / f"{shot_id}{_extension(output_format)}"
    alignment_path = output_dir / f"{shot_id}_alignment.json"
    manifest_path = output_dir / f"{shot_id}_voice_result.json"

    result: dict[str, Any] = {
        "schema_version": "lena_elevenlabs_voice_result_v1",
        "shot_id": shot_id,
        "slot_id": packet.get("slot_id"),
        "provider": "elevenlabs",
        "live": live,
        "request_sha256": packet["request_sha256"],
        "audio_path": str(audio_path),
        "alignment_path": str(alignment_path),
        "provider_call_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not live:
        result["status"] = "dry_run_ready"
        manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    api_key_env = packet["api_key_env"]
    voice_id_env = packet["voice_id_env"]
    api_key = os.environ.get(api_key_env, "").strip()
    voice_id = os.environ.get(voice_id_env, "").strip()
    if not api_key or not voice_id:
        raise ElevenLabsExecutionError(f"live execution requires {api_key_env} and {voice_id_env}")

    url = f"{API_ROOT}/text-to-speech/{voice_id}/with-timestamps?output_format={output_format}"
    body = json.dumps(packet["request_payload"], ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "xi-api-key": api_key},
    )
    result["provider_call_count"] = 1
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise ElevenLabsExecutionError(f"ElevenLabs request failed: {type(exc).__name__}") from exc

    audio_base64 = response_payload.get("audio_base64")
    alignment = response_payload.get("alignment") or response_payload.get("normalized_alignment")
    if not isinstance(audio_base64, str) or not audio_base64:
        raise ElevenLabsExecutionError("ElevenLabs response did not contain audio_base64")
    if not isinstance(alignment, dict):
        raise ElevenLabsExecutionError("ElevenLabs response did not contain alignment timestamps")

    audio_bytes = base64.b64decode(audio_base64, validate=True)
    audio_path.write_bytes(audio_bytes)
    alignment_path.write_text(json.dumps(alignment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result.update({
        "status": "completed",
        "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(),
        "audio_size_bytes": len(audio_bytes),
    })
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Safety-gated ElevenLabs executor for Lena voice packets")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Perform exactly one paid provider call")
    args = parser.parse_args()
    try:
        result = execute(args.packet, args.output_dir, live=args.live)
    except (ElevenLabsExecutionError, VoiceContractError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
