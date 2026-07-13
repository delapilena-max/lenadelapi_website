import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.lena_coordinate_derived_shortform_reel_v1 as coordinator


DATE = "2026-07-13"
SOURCE_SLOT = "historical-source-photo-01"
REEL_SLOT = "historical-source-photo-01-reel"
STRATEGY_FIELDS = {
    "canonical_niche",
    "strategy_pillars",
    "creative_temperature",
    "narrative_roles",
    "choice_eligible",
    "payoff_eligible",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contains_strategy_fields(value) -> bool:
    if isinstance(value, dict):
        return bool(STRATEGY_FIELDS.intersection(value)) or any(
            contains_strategy_fields(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(contains_strategy_fields(child) for child in value)
    return False


class Harness:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.tmp_path = tmp_path
        self.out_dir = tmp_path / "packets"
        self.source_path = tmp_path / "assets" / f"{SOURCE_SLOT}_seed.png"
        self.source_path.parent.mkdir(parents=True)
        self.source_path.write_bytes(b"historical-source-image")
        self.manifest_path = tmp_path / "debug" / DATE / SOURCE_SLOT / "result_manifest.json"
        self.manifest_path.parent.mkdir(parents=True)
        self.manifest_path.write_text(
            json.dumps({"slot_id": SOURCE_SLOT, "provider": "higgsfield"}), encoding="utf-8"
        )
        self.video_path = coordinator.reel_tools.resolve_story_video_path(self.source_path).resolve()
        self.provenance_path = self.video_path.with_name(self.video_path.stem + "_provenance.json")
        self.packet_path = coordinator.packet_tools.resolve_packet_output_path(DATE, REEL_SLOT, self.out_dir)
        self.draft_path = coordinator.packet_tools.resolve_queue_draft_output_path(DATE, REEL_SLOT, self.out_dir)
        self.calls = {"source": [], "compose": [], "validate": [], "derived": []}

        def resolve_source(date_str, slot_id, out_dir=None):
            self.calls["source"].append((date_str, slot_id, out_dir))
            return self.source_result()

        def compose(source_image_path, slot_id, output_path=None, force=False, manifest_path=None):
            self.calls["compose"].append(
                {
                    "source": source_image_path,
                    "slot": slot_id,
                    "output_path": output_path,
                    "force": force,
                    "manifest_path": manifest_path,
                }
            )
            self.prepare_reel()
            return {
                "output_path": str(self.video_path),
                "output_sha256": sha(self.video_path),
                "provenance_path": str(self.provenance_path),
                "selected_track_id": "local-track-01",
                "selected_track_sha256": "3" * 64,
            }

        def validate(video_path, **kwargs):
            self.calls["validate"].append((Path(video_path), kwargs))
            if not Path(video_path).exists():
                raise coordinator.reel_tools.StoryVideoError("missing Reel")
            provenance = json.loads(self.provenance_path.read_text(encoding="utf-8"))
            if provenance.get("output_sha256") != sha(Path(video_path)):
                raise coordinator.reel_tools.StoryVideoError("Reel SHA mismatch")
            return {
                "video_sha256": sha(Path(video_path)),
                "track_id": "local-track-01",
                "track_sha256": "3" * 64,
                "duration_seconds": 20.0,
                "video_codec": "h264",
                "audio_codec": "aac",
                "width": 1080,
                "height": 1920,
            }

        def resolve_derived(date_str, source_slot_id, out_dir=None, output_slot_id=None):
            self.calls["derived"].append((date_str, source_slot_id, out_dir, output_slot_id))
            return self.derived_result(output_slot_id)

        monkeypatch.setattr(coordinator.packet_tools, "resolve_packet_inputs_higgsfield", resolve_source)
        monkeypatch.setattr(coordinator.reel_tools, "build_story_video", compose)
        monkeypatch.setattr(coordinator.reel_tools, "validate_music_backed_shortform_asset", validate)
        monkeypatch.setattr(
            coordinator.packet_tools,
            "resolve_packet_inputs_higgsfield_derived_shortform",
            resolve_derived,
        )
        monkeypatch.setattr(coordinator.packet_tools, "LIVE_QUEUE_ROOT", tmp_path / "live_queue")

    def source_result(self):
        return {
            "date": DATE,
            "slot_id": SOURCE_SLOT,
            "provider": "higgsfield",
            "image_path": str(self.source_path),
            "qa_path": str(self.tmp_path / "qa" / f"{SOURCE_SLOT}_qa.json"),
            "qa_overall": "pass",
            "qa_publish_ready": True,
            "qa_publish_ready_reason": "historical QA complete",
            "lane": "ordinary city life",
            "activity": "walking",
            "pose": "natural stride",
            "visual_style": "editorial daylight",
            "avatar_nickname": "Lena",
            "image_engine": "higgsfield_text2image_soul_v2",
            "image_prompt": "historical prompt",
            "custom_reference_id": "historical-reference",
            "resolution": "1152x2048",
            "wardrobe_outfit_id": "wc_historical",
            "pose_body_language_id": None,
            "expression_gaze_id": None,
            "debug_artifacts": {
                "higgsfield_manifest_path": str(self.manifest_path),
                "provider_job_id": "historical-job",
            },
        }

    def prepare_reel(self):
        self.video_path.parent.mkdir(parents=True, exist_ok=True)
        self.video_path.write_bytes(b"local-static-reel-with-audio")
        provenance = {
            "generated_by": "tools/lena_prepare_story_video_v1.py",
            "slot_id": REEL_SLOT,
            "source_image_path": str(self.source_path.resolve()),
            "source_image_sha256": sha(self.source_path),
            "selected_track_id": "local-track-01",
            "selected_track_sha256": "3" * 64,
            "output_path": str(self.video_path.resolve()),
            "output_sha256": sha(self.video_path),
        }
        self.provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    def derived_result(self, output_slot_id=REEL_SLOT):
        return {
            "date": DATE,
            "slot_id": output_slot_id,
            "source_slot_id": SOURCE_SLOT,
            "provider": "higgsfield_derived_shortform",
            "source_provider": "higgsfield",
            "media_kind": "derived_shortform_video",
            "source_image_path": str(self.source_path.resolve()),
            "source_image_sha256": sha(self.source_path),
            "qa_path": str(self.tmp_path / "qa" / f"{SOURCE_SLOT}_qa.json"),
            "qa_overall": "pass",
            "qa_publish_ready": True,
            "qa_hook_strength": "strong",
            "qa_styling_sexy_platform_safe": "pass",
            "visual_style": "editorial daylight",
            "image_engine": "higgsfield_text2image_soul_v2",
            "image_prompt": "historical prompt",
            "custom_reference_id": "historical-reference",
            "resolution": "1152x2048",
            "avatar_nickname": "Lena",
            "debug_artifacts": {"provider_job_id": "historical-job"},
            "lane": "ordinary city life",
            "activity": "walking",
            "pose": "natural stride",
            "wardrobe_outfit_id": "wc_historical",
            "pose_body_language_id": None,
            "expression_gaze_id": None,
            "prepared_video_path": str(self.video_path.resolve()),
            "prepared_video_sha256": sha(self.video_path),
            "prepared_video_provenance_path": str(self.provenance_path.resolve()),
            "selected_track_id": "local-track-01",
            "selected_track_sha256": "3" * 64,
            "prepared_video_duration_seconds": 20.0,
            "prepared_video_codec": "h264",
            "prepared_audio_codec": "aac",
            "prepared_video_width": 1080,
            "prepared_video_height": 1920,
        }

    def run(self, *, apply_local=False, **overrides):
        return coordinator.coordinate_derived_shortform_reel(
            overrides.pop("date", DATE),
            overrides.pop("source_slot", SOURCE_SLOT),
            overrides.pop("reel_slot", REEL_SLOT),
            apply_local=apply_local,
            out_dir=overrides.pop("out_dir", self.out_dir),
            music_manifest=overrides.pop("music_manifest", None),
            **overrides,
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


def test_dry_run_is_default_and_writes_nothing(harness: Harness) -> None:
    before = sorted(path.relative_to(harness.tmp_path) for path in harness.tmp_path.rglob("*"))
    result = harness.run()
    after = sorted(path.relative_to(harness.tmp_path) for path in harness.tmp_path.rglob("*"))

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["state"] == "ready_for_local_composition"
    assert result["files_written_this_run"] == []
    assert set(result["files_would_write"]) == {
        str(harness.video_path), str(harness.provenance_path),
        str(harness.packet_path), str(harness.draft_path),
    }
    assert harness.calls["compose"] == []
    assert harness.calls["derived"] == []
    assert before == after


@pytest.mark.parametrize(
    ("source_slot", "reel_slot", "code"),
    [
        ("", REEL_SLOT, "missing_source_slot"),
        (SOURCE_SLOT, "", "missing_reel_slot"),
        (SOURCE_SLOT, SOURCE_SLOT, "reel_identity_not_distinct"),
        ("source-a,source-b", REEL_SLOT, "ambiguous_source_slot"),
    ],
)
def test_explicit_distinct_identities_are_required(harness, source_slot, reel_slot, code) -> None:
    result = harness.run(source_slot=source_slot, reel_slot=reel_slot)
    assert result["state"] == "blocked"
    assert result["blocker_codes"] == [code]
    assert harness.calls["source"] == []


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("Higgsfield manifest is missing", "missing_source_evidence"),
        ("ambiguous multiple source manifests", "ambiguous_source_evidence"),
        ("QA verdict overall='fail' (not 'pass')", "failed_qa"),
        ("QA verdict is internally inconsistent", "incomplete_qa"),
    ],
)
def test_source_and_qa_resolution_failures_hard_stop(harness, monkeypatch, message, code) -> None:
    def fail(*args, **kwargs):
        raise coordinator.packet_tools.ResolveError(message)

    monkeypatch.setattr(coordinator.packet_tools, "resolve_packet_inputs_higgsfield", fail)
    result = harness.run()
    assert result["state"] == "blocked"
    assert result["blocker_codes"] == [code]
    assert result["files_written_this_run"] == []


def test_completed_publish_ready_qa_is_required(harness, monkeypatch) -> None:
    source = harness.source_result()
    source["qa_publish_ready"] = False
    monkeypatch.setattr(coordinator.packet_tools, "resolve_packet_inputs_higgsfield", lambda *a, **k: source)
    result = harness.run()
    assert result["blocker_codes"] == ["incomplete_qa"]


def test_historical_source_without_strategy_fields_is_accepted_and_none_are_invented(harness) -> None:
    result = harness.run(apply_local=True)
    assert result["ok"] is True
    assert result["state"] == "ready_for_human_review"
    assert not contains_strategy_fields(result)
    draft = json.loads(harness.draft_path.read_text(encoding="utf-8"))
    assert not contains_strategy_fields(draft)
    assert result["source_provenance"]["lane"] == "ordinary city life"


def test_apply_local_reuses_composer_resolvers_and_packet_writers_without_force(harness, monkeypatch) -> None:
    packet_calls = []
    draft_calls = []
    real_write_packet = coordinator.packet_tools.write_packet
    real_write_draft = coordinator.packet_tools.write_queue_draft

    def write_packet(*args, **kwargs):
        packet_calls.append((args, kwargs))
        return real_write_packet(*args, **kwargs)

    def write_draft(*args, **kwargs):
        draft_calls.append((args, kwargs))
        return real_write_draft(*args, **kwargs)

    monkeypatch.setattr(coordinator.packet_tools, "write_packet", write_packet)
    monkeypatch.setattr(coordinator.packet_tools, "write_queue_draft", write_draft)
    result = harness.run(apply_local=True)

    assert result["ok"] is True
    assert len(harness.calls["compose"]) == 1
    assert harness.calls["compose"][0]["force"] is False
    assert harness.calls["compose"][0]["slot"] == REEL_SLOT
    assert harness.calls["derived"] == [(DATE, SOURCE_SLOT, harness.out_dir, REEL_SLOT)]
    assert packet_calls[0][1]["force"] is False
    assert draft_calls[0][1]["force"] is False
    assert {Path(path) for path in result["files_written_this_run"]} == {
        harness.video_path, harness.provenance_path, harness.packet_path, harness.draft_path,
    }


def test_source_reel_music_composition_and_package_provenance_survive(harness) -> None:
    result = harness.run(apply_local=True)
    draft = json.loads(harness.draft_path.read_text(encoding="utf-8"))

    assert result["source_provenance"]["source_slot_id"] == SOURCE_SLOT
    assert result["source_provenance"]["source_image_sha256"] == sha(harness.source_path)
    assert result["reel_provenance"]["reel_slot_id"] == REEL_SLOT
    assert result["reel_provenance"]["reel_sha256"] == sha(harness.video_path)
    assert result["reel_provenance"]["selected_track_id"] == "local-track-01"
    assert result["package_provenance"]["source_slot_id"] == SOURCE_SLOT
    assert result["package_provenance"]["reel_slot_id"] == REEL_SLOT
    assert result["package_provenance"]["draft_post_id"] == REEL_SLOT
    assert result["package_provenance"]["draft_slot_id"] == REEL_SLOT
    assert result["package_provenance"]["packet_sha256"] == sha(harness.packet_path)
    assert result["package_provenance"]["queue_draft_sha256"] == sha(harness.draft_path)
    assert draft["metadata"]["source_image_sha256"] == sha(harness.source_path)
    assert draft["metadata"]["prepared_video_sha256"] == sha(harness.video_path)
    assert draft["metadata"]["selected_track_sha256"] == "3" * 64


def test_matching_rerun_is_idempotent_and_does_not_rewrite(harness) -> None:
    first = harness.run(apply_local=True)
    before = {path: path.read_bytes() for path in (
        harness.video_path, harness.provenance_path, harness.packet_path, harness.draft_path
    )}
    second = harness.run(apply_local=True)

    assert first["ok"] and second["ok"]
    assert second["state"] == "ready_for_human_review"
    assert second["files_written_this_run"] == []
    assert len(harness.calls["compose"]) == 1
    assert all(path.read_bytes() == content for path, content in before.items())


def test_dry_run_reuses_matching_complete_artifacts(harness) -> None:
    assert harness.run(apply_local=True)["ok"]
    result = harness.run()
    assert result["dry_run"] is True
    assert result["state"] == "ready_for_human_review"
    assert result["files_written_this_run"] == []


@pytest.mark.parametrize(
    ("create_video", "create_provenance", "code"),
    [
        (True, False, "orphaned_reel"),
        (False, True, "orphaned_composition_provenance"),
    ],
)
def test_orphaned_reel_pair_hard_stops(harness, create_video, create_provenance, code) -> None:
    harness.prepare_reel()
    if not create_video:
        harness.video_path.unlink()
    if not create_provenance:
        harness.provenance_path.unlink()
    result = harness.run(apply_local=True)
    assert result["blocker_codes"] == [code]
    assert harness.calls["compose"] == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_image_sha256", "0" * 64, "source_hash_conflict"),
        ("slot_id", "wrong-reel", "provenance_mismatch"),
        ("source_image_path", "wrong-source.png", "provenance_mismatch"),
    ],
)
def test_composition_provenance_conflicts_hard_stop(harness, field, value, code) -> None:
    harness.prepare_reel()
    provenance = json.loads(harness.provenance_path.read_text(encoding="utf-8"))
    provenance[field] = value
    harness.provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    result = harness.run()
    assert result["blocker_codes"] == [code]


def test_reel_hash_conflict_hard_stops(harness) -> None:
    harness.prepare_reel()
    harness.video_path.write_bytes(b"conflicting-reel-bytes")
    result = harness.run()
    assert result["blocker_codes"] == ["reel_hash_conflict"]


@pytest.mark.parametrize(("artifact", "code"), [("packet", "conflicting_packet"), ("draft", "conflicting_draft")])
def test_conflicting_package_artifacts_hard_stop_without_rewrite(harness, artifact, code) -> None:
    assert harness.run(apply_local=True)["ok"]
    path = harness.packet_path if artifact == "packet" else harness.draft_path
    path.write_text("conflict", encoding="utf-8")
    before = path.read_bytes()
    result = harness.run(apply_local=True)
    assert result["blocker_codes"] == [code]
    assert path.read_bytes() == before


def test_preexisting_package_without_reel_blocks_before_composition(harness) -> None:
    harness.packet_path.parent.mkdir(parents=True)
    harness.packet_path.write_text("orphan package", encoding="utf-8")
    result = harness.run(apply_local=True)
    assert result["blocker_codes"] == ["conflicting_packet"]
    assert harness.calls["compose"] == []


def test_packet_comparison_tolerates_only_prepared_date_line(harness) -> None:
    assert harness.run(apply_local=True)["ok"]
    packet = harness.packet_path.read_text(encoding="utf-8")
    packet = coordinator.re.sub(
        r"(?m)^\*\*Prepared:\*\* .*?$",
        "**Prepared:** 1999-01-01 (auto-generated draft via `tools/lena_build_publish_packet_v1.py` -- caption/CTA/poll/pin text below are mechanical drafts, not final copy; review and edit before use).",
        packet,
    )
    harness.packet_path.write_text(packet, encoding="utf-8")
    assert harness.run()["state"] == "ready_for_human_review"

    harness.packet_path.write_text(packet.replace("## 2. QA summary", "## 2. Changed"), encoding="utf-8")
    assert harness.run()["blocker_codes"] == ["conflicting_packet"]


def test_stop_boundary_and_manual_preflight_are_explicit(harness) -> None:
    result = harness.run(apply_local=True)
    assert result["state"] in coordinator.ALLOWED_STATES
    assert result["state"] == "ready_for_human_review"
    assert result["stop_boundary"] == "ready_for_human_review"
    assert result["full_manual_preflight"] == "deferred_pending_human_approval_and_clean_export"
    draft = json.loads(harness.draft_path.read_text(encoding="utf-8"))
    assert draft["approved_for_live_publish"] is False
    assert draft["operator_review_required"] is True
    assert draft["metadata"]["queue_draft_only"] is True


def test_no_downstream_or_sensitive_state_is_created_or_mutated(harness) -> None:
    sentinels = {
        harness.tmp_path / ".env": b"SECRET=unchanged",
        harness.tmp_path / "analytics.csv": b"metrics-unchanged",
        harness.tmp_path / "learning.json": b'{"state":"unchanged"}',
        harness.tmp_path / "world_state.json": b'{"state":"unchanged"}',
    }
    for path, content in sentinels.items():
        path.write_bytes(content)
    result = harness.run(apply_local=True)
    assert result["ok"] is True
    assert all(path.read_bytes() == content for path, content in sentinels.items())
    names = {path.name.lower() for path in harness.tmp_path.rglob("*") if path.is_file()}
    assert not any("approval" in name for name in names)
    assert not any("clean" in name for name in names)
    assert not coordinator.packet_tools.LIVE_QUEUE_ROOT.exists()


def test_module_has_no_provider_network_or_downstream_imports() -> None:
    source_path = ROOT / "tools/lena_coordinate_derived_shortform_reel_v1.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden_fragments = {
        "requests", "urllib", "http", "socket", "provider", "kling", "higgsfield_api",
        "anthropic", "jamendo", "meta", "r2", "promote", "publisher", "analytics",
    }
    assert not any(fragment in name.lower() for name in imported for fragment in forbidden_fragments)


def test_cli_defaults_to_inspect_only(monkeypatch, capsys) -> None:
    captured = {}

    def coordinate(*args, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "dry_run": True,
            "state": "ready_for_local_composition",
        }

    monkeypatch.setattr(coordinator, "coordinate_derived_shortform_reel", coordinate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lena_coordinate_derived_shortform_reel_v1.py",
            "--date", DATE,
            "--source-slot", SOURCE_SLOT,
            "--reel-slot", REEL_SLOT,
        ],
    )
    assert coordinator.main() == 0
    assert captured["apply_local"] is False
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_optional_music_manifest_is_local_and_process_global_is_restored(harness) -> None:
    manifest = harness.tmp_path / "music" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"tracks": []}', encoding="utf-8")
    original = coordinator.music_pool_tools.DEFAULT_MANIFEST_PATH
    result = harness.run(apply_local=True, music_manifest=manifest)
    assert result["ok"] is True
    assert harness.calls["compose"][0]["manifest_path"] == manifest.resolve()
    assert coordinator.music_pool_tools.DEFAULT_MANIFEST_PATH == original


def test_live_queue_output_root_is_rejected_before_any_write(harness) -> None:
    result = harness.run(apply_local=True, out_dir=coordinator.packet_tools.LIVE_QUEUE_ROOT)
    assert result["blocker_codes"] == ["live_queue_path_forbidden"]
    assert harness.calls["compose"] == []


def test_source_under_live_queue_blocks_all_writes_before_composition(harness) -> None:
    live_queue = coordinator.packet_tools.LIVE_QUEUE_ROOT
    live_queue.mkdir(parents=True)
    source_path = live_queue / f"{SOURCE_SLOT}_seed.png"
    harness.source_path.replace(source_path)
    harness.source_path = source_path
    harness.video_path = coordinator.reel_tools.resolve_story_video_path(source_path).resolve()
    harness.provenance_path = harness.video_path.with_name(
        harness.video_path.stem + "_provenance.json"
    )
    harness.manifest_path.write_text(
        json.dumps(
            {
                "slot_id": SOURCE_SLOT,
                "provider": "higgsfield",
                "saved_image_path": str(source_path),
            }
        ),
        encoding="utf-8",
    )

    result = harness.run(apply_local=True)

    assert result["state"] == "blocked"
    assert result["blocker_codes"] == ["live_queue_path_forbidden"]
    assert str(harness.video_path) in result["blocker_reasons"][0]
    assert live_queue in harness.video_path.parents
    assert live_queue in harness.provenance_path.parents
    assert harness.calls["compose"] == []
    assert not harness.video_path.exists()
    assert not harness.provenance_path.exists()
    assert not harness.packet_path.exists()
    assert not harness.draft_path.exists()
