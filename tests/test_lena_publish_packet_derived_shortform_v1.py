import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.lena_build_publish_packet_v1 as packet_mod

import pipeline.qa.lena_photo_qa as lena_photo_qa
import tools.lena_music_pool_v1 as music_pool_mod

import lena_higgsfield_qa_bridge_v1 as qa_bridge_mod


REAL_SOURCE = ROOT / "pipeline/higgsfield_library/lena/2026-07-09/readypack0709-pack007-00-photo_seed.png"
REAL_VIDEO = ROOT / "pipeline/higgsfield_library/lena/2026-07-09/readypack0709-pack007-00-photo_story.mp4"
REAL_MUSIC_MANIFEST = ROOT / "assets/royaltyfree audio/manifest.json"
REAL_TRACK_ID = "royaltyfree_010"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def derived_resolved(tmp_path: Path) -> dict:
    source_path = tmp_path / "source.png"
    video_path = tmp_path / "source_story.mp4"
    provenance_path = tmp_path / "source_story_provenance.json"
    source_path.write_bytes(b"source-image")
    video_path.write_bytes(b"prepared-video")
    provenance_path.write_text("{}", encoding="utf-8")
    return {
        "date": "2026-07-13",
        "slot_id": "reel-candidate-01",
        "source_slot_id": "source-photo-01",
        "provider": "higgsfield_derived_shortform",
        "source_provider": "higgsfield",
        "media_kind": "derived_shortform_video",
        "source_image_path": str(source_path),
        "source_image_sha256": "1" * 64,
        "qa_path": str(tmp_path / "source-photo-01_qa.json"),
        "qa_overall": "pass",
        "qa_publish_ready": True,
        "visual_style": "editorial rooftop",
        "image_engine": "higgsfield-soul",
        "image_prompt": "source image prompt",
        "custom_reference_id": "reference-01",
        "resolution": "1152x2048",
        "avatar_nickname": "Lena",
        "debug_artifacts": {"provider_job_id": "higgsfield-job-01"},
        "lane": "fashion reel",
        "activity": "editorial portrait",
        "pose": "standing",
        "wardrobe_outfit_id": "wc_001",
        "pose_body_language_id": "pose_001",
        "expression_gaze_id": "gaze_001",
        "prepared_video_path": str(video_path),
        "prepared_video_sha256": "2" * 64,
        "prepared_video_provenance_path": str(provenance_path),
        "selected_track_id": "royaltyfree_001",
        "selected_track_sha256": "3" * 64,
        "prepared_video_duration_seconds": 20.0,
        "prepared_video_codec": "h264",
        "prepared_audio_codec": "aac",
        "prepared_video_width": 1080,
        "prepared_video_height": 1920,
        "source_asset_path": str(video_path),
        "source_asset_sha256": "2" * 64,
        "clean_export_derivative_sha256": "4" * 64,
        "clean_export_sidecar_path": str(tmp_path / "source_story_clean_provenance.json"),
        "clean_export_verified": True,
        "clean_export_generated_by": "tools/lena_scrub_media_metadata_v1.py",
        "clean_export_created_at_utc": "2026-07-13T12:00:00+00:00",
        "files_written_this_run": [],
    }


def test_derived_packet_identifies_media_kind_and_provenance(derived_resolved: dict) -> None:
    markdown = packet_mod.build_packet_markdown(derived_resolved)

    assert "**Media kind:** `derived_shortform_video`" in markdown
    assert derived_resolved["source_image_path"] in markdown
    assert derived_resolved["source_image_sha256"] in markdown
    assert derived_resolved["prepared_video_path"] in markdown
    assert derived_resolved["prepared_video_sha256"] in markdown
    assert derived_resolved["selected_track_id"] in markdown
    assert derived_resolved["selected_track_sha256"] in markdown
    assert derived_resolved["prepared_video_provenance_path"] in markdown


def test_derived_draft_has_first_class_reel_shape_and_full_provenance(
    derived_resolved: dict,
) -> None:
    packet_path = Path("derived_packet.md")
    draft = packet_mod.build_queue_draft(derived_resolved, packet_path)
    metadata = draft["metadata"]

    assert draft["post_id"] == "reel-candidate-01"
    assert draft["slot_id"] == "reel-candidate-01"
    assert draft["media_path"] == derived_resolved["prepared_video_path"]
    assert draft["media_type"] == "reel"
    assert draft["approved_for_live_publish"] is False
    assert draft["operator_review_required"] is True
    assert metadata["queue_draft_only"] is True
    assert metadata["provider"] == "higgsfield_derived_shortform"
    assert metadata["source_provider"] == "higgsfield"
    assert metadata["source_slot_id"] == "source-photo-01"
    assert metadata["source_image_path"] == derived_resolved["source_image_path"]
    assert metadata["source_image_sha256"] == derived_resolved["source_image_sha256"]
    assert metadata["prepared_video_sha256"] == derived_resolved["prepared_video_sha256"]
    assert metadata["prepared_shortform_provenance_path"] == derived_resolved["prepared_video_provenance_path"]
    assert metadata["selected_track_id"] == derived_resolved["selected_track_id"]
    assert metadata["selected_track_sha256"] == derived_resolved["selected_track_sha256"]
    assert metadata["duration_seconds"] == 20.0
    assert metadata["video_codec"] == "h264"
    assert metadata["audio_codec"] == "aac"
    assert metadata["width"] == 1080
    assert metadata["height"] == 1920
    assert metadata["aspect_ratio"] == "9:16"


def test_caller_supplied_clean_export_evidence_is_not_trusted_or_persisted(
    derived_resolved: dict,
) -> None:
    derived_resolved.update(
        {
            "clean_export_source_path": "fake-source.png",
            "clean_export_source_sha256": "5" * 64,
            "clean_export_output_path": "fake-clean.mp4",
            "clean_export_output_sha256": "6" * 64,
        }
    )
    draft = packet_mod.build_queue_draft(derived_resolved, Path("derived_packet.md"))
    metadata = draft["metadata"]

    for key in (
        "source_asset_path",
        "source_asset_sha256",
        "clean_export_derivative_sha256",
        "clean_export_sidecar_path",
        "clean_export_verified",
        "clean_export_generated_by",
        "clean_export_created_at_utc",
        "clean_export_source_path",
        "clean_export_source_sha256",
        "clean_export_output_path",
        "clean_export_output_sha256",
    ):
        assert key not in metadata
    assert draft["approved_for_live_publish"] is False
    assert draft["operator_review_required"] is True
    assert metadata["queue_draft_only"] is True


def test_cli_selects_derived_shortform_with_distinct_source_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    derived_resolved: dict,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []

    def fake_resolver(date_str, source_slot_id, out_dir=None, output_slot_id=None):
        calls.append((date_str, source_slot_id, out_dir, output_slot_id))
        return dict(derived_resolved)

    packet_path = tmp_path / "packet.md"
    monkeypatch.setattr(packet_mod, "resolve_packet_inputs_higgsfield_derived_shortform", fake_resolver)
    monkeypatch.setattr(packet_mod, "write_packet", lambda resolved, out_dir, force: packet_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lena_build_publish_packet_v1.py",
            "--date",
            "2026-07-13",
            "--slot",
            "reel-candidate-01",
            "--source-slot",
            "source-photo-01",
            "--provider",
            "higgsfield_derived_shortform",
            "--out-dir",
            str(tmp_path),
        ],
    )

    assert packet_mod.main() == 0
    assert calls == [("2026-07-13", "source-photo-01", tmp_path, "reel-candidate-01")]
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["resolved"]["media_kind"] == "derived_shortform_video"


def test_derived_draft_write_stays_outside_live_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    derived_resolved: dict,
) -> None:
    live_queue = tmp_path / "live_queue"
    out_dir = tmp_path / "package_output"
    monkeypatch.setattr(packet_mod, "LIVE_QUEUE_ROOT", live_queue)

    output_path = packet_mod.write_queue_draft(
        derived_resolved,
        out_dir / "packet.md",
        out_dir,
        force=False,
    )

    assert output_path.parent == out_dir / derived_resolved["date"]
    assert json.loads(output_path.read_text(encoding="utf-8"))["approved_for_live_publish"] is False
    assert not live_queue.exists()


def test_real_resolver_to_draft_to_write_preserves_provenance_without_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    date_str = "2026-07-13"
    source_slot_id = "source-photo-real-chain-01"
    reel_slot_id = "derived-reel-real-chain-01"
    asset_dir = tmp_path / "assets"
    source_path = asset_dir / f"{source_slot_id}_seed.png"
    video_path = asset_dir / f"{source_slot_id}_story.mp4"
    track_path = asset_dir / "music" / "approved-track.mp3"
    asset_dir.mkdir(parents=True)
    track_path.parent.mkdir(parents=True)
    shutil.copy2(REAL_SOURCE, source_path)
    shutil.copy2(REAL_VIDEO, video_path)

    real_music_manifest = json.loads(REAL_MUSIC_MANIFEST.read_text(encoding="utf-8"))
    real_track = next(track for track in real_music_manifest["tracks"] if track["track_id"] == REAL_TRACK_ID)
    shutil.copy2(Path(real_track["local_path"]), track_path)
    scratch_track = dict(real_track)
    scratch_track["local_path"] = str(track_path)
    scratch_track["sha256"] = _sha256(track_path)
    music_manifest_path = asset_dir / "music" / "manifest.json"
    music_manifest_path.write_text(json.dumps({"tracks": [scratch_track]}, indent=2), encoding="utf-8")

    composition_provenance_path = video_path.with_name(video_path.stem + "_provenance.json")
    composition_provenance = {
        "generated_by": "tools/lena_prepare_story_video_v1.py",
        "slot_id": reel_slot_id,
        "source_image_path": str(source_path.resolve()),
        "source_image_sha256": _sha256(source_path),
        "selected_track_id": scratch_track["track_id"],
        "selected_track_sha256": scratch_track["sha256"],
        "output_path": str(video_path.resolve()),
        "output_sha256": _sha256(video_path),
    }
    composition_provenance_path.write_text(
        json.dumps(composition_provenance, indent=2), encoding="utf-8"
    )

    debug_root = tmp_path / "higgsfield_debug"
    manifest_dir = debug_root / date_str / source_slot_id
    manifest_dir.mkdir(parents=True)
    manifest = {
        "slot_id": source_slot_id,
        "provider": "higgsfield",
        "job_type": "text2image_soul_v2",
        "cli_soul_name": "Lena",
        "custom_reference_id": "scratch-reference-id",
        "image_prompt": "scratch source prompt",
        "saved_image_path": str(source_path),
        "lane": "scratch fashion lane",
        "pose_text": "standing editorial pose",
        "provider_job_id": "scratch-provider-job-id",
        "provider_status": "succeed",
        "wardrobe_outfit_id": "wc_scratch",
    }
    (manifest_dir / "result_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    asset_review_root = tmp_path / "asset_review" / "lena"
    qa_path = asset_review_root / date_str / f"{source_slot_id}_qa.json"
    qa_path.parent.mkdir(parents=True)
    status_fields = (
        "identity_fidelity",
        "face_realism_anti_generic_drift",
        "skin_realism_no_invented_marks",
        "wardrobe_class_fidelity",
        "public_scene_clothing_continuity",
        "outerwear_underlayer_correctness",
        "body_shape_continuity",
        "hands_anatomy_sanity",
        "environment_realism_scene_coherence",
        "caption_scene_coherence",
    )
    qa = {
        "schema_version": "2",
        "slot_id": source_slot_id,
        "date": date_str,
        "media_type": "photo",
        "reviewed_by": "scratch-test",
        "checklist": {
            field: {"status": "pass", "notes": "scratch fixture"}
            for field in status_fields
        },
        "production_scoring": {
            "hook_strength": {"score": "strong", "notes": "scratch fixture"},
            "styling_sexy_platform_safe": {"status": "pass", "notes": "scratch fixture"},
            "outfit_variety_vs_recent_posts": {
                "status": "not_yet_measured",
                "notes": "scratch fixture",
            },
            "scene_variety_vs_recent_posts": {
                "status": "not_yet_measured",
                "notes": "scratch fixture",
            },
        },
        "overall": "pass",
        "failure_reasons": [],
        "publish_ready": True,
        "publish_ready_reason": "scratch fixture",
    }
    qa_path.write_text(json.dumps(qa, indent=2), encoding="utf-8")

    live_queue = tmp_path / "live_queue"
    package_root = tmp_path / "publish_packets"
    monkeypatch.setattr(qa_bridge_mod, "HIGGSFIELD_DEBUG_ROOT", debug_root)
    monkeypatch.setattr(lena_photo_qa, "ASSET_REVIEW_ROOT", asset_review_root)
    monkeypatch.setattr(music_pool_mod, "DEFAULT_MANIFEST_PATH", music_manifest_path)
    monkeypatch.setattr(packet_mod, "LIVE_QUEUE_ROOT", live_queue)

    resolved = packet_mod.resolve_packet_inputs_higgsfield_derived_shortform(
        date_str,
        source_slot_id,
        package_root,
        output_slot_id=reel_slot_id,
    )
    packet_path = package_root / date_str / f"{reel_slot_id}_publish_packet.md"
    draft = packet_mod.build_queue_draft(resolved, packet_path)
    draft_path = packet_mod.write_queue_draft(
        resolved,
        packet_path,
        package_root,
        force=False,
    )
    written = json.loads(draft_path.read_text(encoding="utf-8"))

    assert resolved["media_kind"] == "derived_shortform_video"
    assert resolved["slot_id"] == reel_slot_id
    assert resolved["source_slot_id"] == source_slot_id
    assert resolved["source_image_path"] == str(source_path)
    assert resolved["source_image_sha256"] == _sha256(source_path)
    assert resolved["prepared_video_path"] == str(video_path.resolve())
    assert resolved["prepared_video_sha256"] == _sha256(video_path)
    assert resolved["prepared_video_provenance_path"] == str(composition_provenance_path)
    assert resolved["selected_track_id"] == scratch_track["track_id"]
    assert resolved["selected_track_sha256"] == scratch_track["sha256"]
    assert written == draft
    assert written["post_id"] == reel_slot_id
    assert written["slot_id"] == reel_slot_id
    assert written["media_path"] == str(video_path.resolve())
    assert written["media_type"] == "reel"
    assert written["metadata"]["source_slot_id"] == source_slot_id
    assert written["metadata"]["source_image_path"] == str(source_path)
    assert written["metadata"]["source_image_sha256"] == _sha256(source_path)
    assert written["metadata"]["prepared_video_sha256"] == _sha256(video_path)
    assert written["metadata"]["prepared_shortform_provenance_path"] == str(composition_provenance_path)
    assert written["metadata"]["selected_track_id"] == scratch_track["track_id"]
    assert written["metadata"]["selected_track_sha256"] == scratch_track["sha256"]
    assert written["metadata"]["queue_draft_only"] is True
    assert written["operator_review_required"] is True
    assert written["approved_for_live_publish"] is False
    assert not live_queue.exists()
    assert not list(package_root.rglob("*approval*.json"))
