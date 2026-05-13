import json
import subprocess
import shlex
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


# =========================
# Data models
# =========================

@dataclass
class CameraSpec:
    type: str
    movement: str
    framing: str


@dataclass
class CharacterSpec:
    name: str
    pose: str
    expression: str
    action: str
    outfit: str


@dataclass
class EnvironmentSpec:
    location: str
    lighting: str
    props: List[str]


@dataclass
class MotionSpec:
    body: str
    hair: str
    camera: str


@dataclass
class TextOverlaySpec:
    enabled: bool
    content: str
    style: str
    placement: str


@dataclass
class AudioSpec:
    type: str
    track_id: Optional[str]


@dataclass
class Storyboard:
    scene_id: str
    duration_seconds: int
    camera: CameraSpec
    character: CharacterSpec
    environment: EnvironmentSpec
    motion: MotionSpec
    text_overlay: TextOverlaySpec
    audio: AudioSpec
    notes: Optional[str]
    tags: List[str]
    _saved_path: Optional[str] = None
    _scene_saved_path: Optional[str] = None


@dataclass
class KlingClipJob:
    job_id: str
    scene_id: str
    prompt: str
    negative_prompt: str
    duration_seconds: int
    fps: int
    width: int
    height: int
    seed: int
    ref_face_path: Optional[str]
    output_path: str
    extra: Dict[str, Any]


@dataclass
class KlingJobManifest:
    storyboard_path: str
    created_at: str
    model: str
    clips: List[KlingClipJob]


# =========================
# Prompt builder
# =========================

def build_kling_prompt(sb: Storyboard) -> str:
    """
    Build a rich Kling prompt from the storyboard.
    You can tune this text heavily for style/brand.
    """
    parts = []

    # Character and pose
    parts.append(
        f"{sb.character.name}, {sb.character.pose}, {sb.character.expression}, "
        f"{sb.character.action}, wearing {sb.character.outfit}"
    )

    # Environment
    parts.append(
        f"in a {sb.environment.location} with {sb.environment.lighting} lighting"
    )

    # Camera
    parts.append(
        f"camera: {sb.camera.framing}, {sb.camera.type}, movement: {sb.camera.movement}"
    )

    # Motion
    parts.append(
        f"motion: body {sb.motion.body}, hair {sb.motion.hair}, camera {sb.motion.camera}"
    )

    # Text overlay (if enabled)
    if sb.text_overlay.enabled and sb.text_overlay.content:
        parts.append(
            f"text overlay at {sb.text_overlay.placement}: '{sb.text_overlay.content}', style {sb.text_overlay.style}"
        )

    # Tags
    if sb.tags:
        parts.append("tags: " + ", ".join(sb.tags))

    # Notes
    if sb.notes:
        parts.append("notes: " + sb.notes)

    # Join into a single prompt
    prompt = ". ".join(parts)
    return prompt


def default_negative_prompt() -> str:
    """
    Default negative prompt for Kling.
    Tune this to your taste.
    """
    return (
        "low quality, blurry, distorted, extra limbs, deformed, bad anatomy, "
        "text artifacts, watermark, logo, oversaturated, underexposed"
    )


# =========================
# Manifest builder
# =========================

def build_kling_manifest(
    storyboard_path: Path,
    output_dir: Path,
    model: str = "kling-v3",
    fps: int = 24,
    width: int = 1080,
    height: int = 1920,
    seed: int = 123,
    ref_face_path: Optional[Path] = None,
) -> KlingJobManifest:
    """
    Read a storyboard JSON and build a Kling job manifest.
    """
    sb_data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    sb = Storyboard(
        scene_id=sb_data["scene_id"],
        duration_seconds=sb_data.get("duration_seconds", 5),
        camera=CameraSpec(**sb_data["camera"]),
        character=CharacterSpec(**sb_data["character"]),
        environment=EnvironmentSpec(**sb_data["environment"]),
        motion=MotionSpec(**sb_data["motion"]),
        text_overlay=TextOverlaySpec(**sb_data["text_overlay"]),
        audio=AudioSpec(**sb_data["audio"]),
        notes=sb_data.get("notes"),
        tags=sb_data.get("tags", []),
        _saved_path=sb_data.get("_saved_path"),
        _scene_saved_path=sb_data.get("_scene_saved_path"),
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # For now: one clip per storyboard.
    # If you want multiple angles per storyboard, you can expand this later.
    prompt = build_kling_prompt(sb)
    neg = default_negative_prompt()

    job_id = f"{sb.scene_id}_clip"
    clip_output = output_dir / f"{job_id}.mp4"

    clip_job = KlingClipJob(
        job_id=job_id,
        scene_id=sb.scene_id,
        prompt=prompt,
        negative_prompt=neg,
        duration_seconds=sb.duration_seconds,
        fps=fps,
        width=width,
        height=height,
        seed=seed,
        ref_face_path=str(ref_face_path) if ref_face_path else None,
        output_path=str(clip_output),
        extra={
            "audio_type": sb.audio.type,
            "audio_track_id": sb.audio.track_id,
            "text_overlay": asdict(sb.text_overlay),
            "tags": sb.tags,
        },
    )

    manifest = KlingJobManifest(
        storyboard_path=str(storyboard_path),
        created_at=datetime.utcnow().isoformat() + "Z",
        model=model,
        clips=[clip_job],
    )

    return manifest


# =========================
# Optional: Kling runner
# =========================

def run_kling_for_clip(
    clip: KlingClipJob,
    model: str,
    kling_command_template: Optional[str] = None,
) -> None:
    """
    Optionally call Kling via a shell command.

    kling_command_template can contain:
      {prompt}, {negative_prompt}, {duration}, {fps}, {width}, {height},
      {seed}, {ref_face}, {output}, {model}

    Example template (you will replace this with your real command):

      python kling_cli.py --model {model} --prompt "{prompt}" --negative "{negative_prompt}" \
          --seconds {duration} --fps {fps} --width {width} --height {height} \
          --seed {seed} --ref-face "{ref_face}" --out "{output}"

    If kling_command_template is None, this function does nothing.
    """
    if not kling_command_template:
        return

    cmd = kling_command_template.format(
        prompt=clip.prompt.replace('"', '\\"'),
        negative_prompt=clip.negative_prompt.replace('"', '\\"'),
        duration=clip.duration_seconds,
        fps=clip.fps,
        width=clip.width,
        height=clip.height,
        seed=clip.seed,
        ref_face=clip.ref_face_path or "",
        output=clip.output_path,
        model=model,
    )

    args = shlex.split(cmd)
    subprocess.run(args, check=False)


def save_manifest(manifest: KlingJobManifest, manifest_path: Path) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "storyboard_path": manifest.storyboard_path,
                "created_at": manifest.created_at,
                "model": manifest.model,
                "clips": [asdict(c) for c in manifest.clips],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


# =========================
# CLI entrypoint
# =========================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Kling job manifest from storyboard JSON and optionally run Kling."
    )
    parser.add_argument(
        "--storyboard",
        required=True,
        help="Path to storyboard JSON generated by pipeline.py",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to store Kling clips and manifest",
    )
    parser.add_argument(
        "--model",
        default="kling-v3",
        help="Kling model identifier",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=24,
        help="Frames per second",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1080,
        help="Video width",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1920,
        help="Video height",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Random seed",
    )
    parser.add_argument(
        "--ref-face",
        default=None,
        help="Optional reference face image path",
    )
    parser.add_argument(
        "--kling-command-template",
        default=None,
        help="Optional shell command template to actually call Kling",
    )
    parser.add_argument(
        "--manifest-out",
        default=None,
        help="Optional explicit path for the manifest JSON",
    )

    args = parser.parse_args()

    storyboard_path = Path(args.storyboard).resolve()
    output_dir = Path(args.output_dir).resolve()
    ref_face_path = Path(args.ref_face).resolve() if args.ref_face else None

    manifest = build_kling_manifest(
        storyboard_path=storyboard_path,
        output_dir=output_dir,
        model=args.model,
        fps=args.fps,
        width=args.width,
        height=args.height,
        seed=args.seed,
        ref_face_path=ref_face_path,
    )

    # Save manifest
    if args.manifest_out:
        manifest_path = Path(args.manifest_out).resolve()
    else:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        manifest_path = output_dir / f"kling_manifest_{ts}.json"

    save_manifest(manifest, manifest_path)

    # Optionally run Kling for each clip
    for clip in manifest.clips:
        run_kling_for_clip(
            clip=clip,
            model=manifest.model,
            kling_command_template=args.kling_command_template,
        )

    print(json.dumps({"manifest": str(manifest_path), "clips": [c.output_path for c in manifest.clips]}, indent=2))


if __name__ == "__main__":
    main()
    