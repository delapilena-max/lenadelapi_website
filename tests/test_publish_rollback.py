# tests/test_publish_rollback.py
import json
import shutil
from pathlib import Path
import pytest
from nodes import life_engine

OUTBOX = Path("pipeline/outbox/ai_lady")
PUBLISHED = Path("pipeline/published/ai_lady")
LAST_POST = Path("nodes/ai_lady_instagram/last_post.json")
HISTORY = Path("nodes/ai_lady_instagram/history.json")

def setup_module(module):
    OUTBOX.mkdir(parents=True, exist_ok=True)
    PUBLISHED.mkdir(parents=True, exist_ok=True)
    (OUTBOX / "test.jpg").write_text("dummy", encoding="utf-8")
    # ensure clean history/last_post
    if LAST_POST.exists(): LAST_POST.unlink()
    if HISTORY.exists(): HISTORY.unlink()

def teardown_module(module):
    shutil.rmtree(OUTBOX, ignore_errors=True)
    shutil.rmtree(PUBLISHED, ignore_errors=True)
    if LAST_POST.exists(): LAST_POST.unlink()
    if HISTORY.exists(): HISTORY.unlink()

def test_publish_success():
    # run engine; should publish file and write last_post
    result = life_engine.create_post_media(str(OUTBOX))
    assert result != ""
    assert PUBLISHED.exists()
    assert any(PUBLISHED.iterdir())
    assert LAST_POST.exists()
    data = json.loads(LAST_POST.read_text(encoding="utf-8"))
    assert "last_post_ts" in data

def test_rollback_on_history_failure(tmp_path, monkeypatch):
    # prepare a fresh outbox file
    f = OUTBOX / "test2.jpg"
    f.write_text("dummy2", encoding="utf-8")
    # simulate history write failure by making HISTORY a directory
    if HISTORY.exists(): 
        if HISTORY.is_file(): HISTORY.unlink()
        else: shutil.rmtree(HISTORY, ignore_errors=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    try:
        # run engine; it should catch the history update error and rollback the moved file
        res = life_engine.create_post_media(str(OUTBOX))
        # after failure, file should either be back in outbox or not present in published
        published_files = list(PUBLISHED.glob("test2.jpg"))
        outbox_files = list(OUTBOX.glob("test2.jpg"))
        assert (len(published_files) == 0) or (len(outbox_files) == 1)
    finally:
        # cleanup
        if HISTORY.is_dir(): shutil.rmtree(HISTORY)
        if (OUTBOX / "test2.jpg").exists(): (OUTBOX / "test2.jpg").unlink()
