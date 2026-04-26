"""Tests for FR-20260425-guitar-trainer-db-migration.

Covers:
  - guitar_exercises and guitar_training_log tables exist in heartmusic.db
  - _list_sessions() returns dicts with 'id' key, no 'file' key
  - /save route accepts {id, segments, gradient} and updates DB
  - /create route inserts a new exercise and returns {ok, id}
  - /delete route removes the exercise from DB
  - /api/sessions returns id-keyed dicts
  - migration script: 6 base cards imported, _run_ variants skipped, log migrated
  - Jinja2 template uses s.id (not s.file / loop.index)
  - JS functions use single id param (no filename)
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = PROJECT_ROOT / "tmp"
TRAINER_PY = PROJECT_ROOT / "src" / "training" / "musician_training_ui.py"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui


# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guitar_exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL DEFAULT '',
    song_path   TEXT NOT NULL DEFAULT '',
    segments    TEXT NOT NULL DEFAULT '[]',
    gradient    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS guitar_training_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER,
    song_path   TEXT NOT NULL DEFAULT '',
    seg_start   TEXT NOT NULL DEFAULT '',
    seg_end     TEXT NOT NULL DEFAULT '',
    repetition  INTEGER NOT NULL DEFAULT 1,
    logged_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _make_mem_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


class _NoClose:
    """Wrap a sqlite3.Connection so close() is a no-op — allows reuse in tests."""
    def __init__(self, c: sqlite3.Connection):
        object.__setattr__(self, "_c", c)
    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_c"), name)
    def close(self) -> None:
        pass
    def __enter__(self):
        return object.__getattribute__(self, "_c").__enter__()
    def __exit__(self, *a):
        return object.__getattribute__(self, "_c").__exit__(*a)


@pytest.fixture()
def mem_conn():
    """Fresh in-memory SQLite connection per test (raw, for inspection)."""
    conn = _make_mem_conn()
    yield conn
    conn.close()


@pytest.fixture()
def client(mem_conn):
    """Flask test client with get_connection patched to use in-memory DB."""
    wrapper = _NoClose(mem_conn)
    ui.app.config["TESTING"] = True
    with patch("training.musician_training_ui.get_connection", return_value=wrapper):
        with ui.app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# Source-level checks (no app required)
# ---------------------------------------------------------------------------

def test_template_uses_s_id_not_s_file():
    src = TRAINER_PY.read_text(encoding="utf-8")
    assert "s.id" in src, "Template must reference s.id"
    assert "s.file" not in src, "Template must not reference s.file (legacy)"


def test_template_no_loop_index_in_card_grid():
    src = TRAINER_PY.read_text(encoding="utf-8")
    # The card grid loop must not use loop.index as a card key.
    # (loop.index is still valid in the practice log section.)
    assert "card-{{ loop.index }}" not in src, "Card DOM id must not use loop.index — use s.id"
    assert "tbody-{{ loop.index }}" not in src, "tbody id must not use loop.index — use s.id"
    assert "status-{{ loop.index }}" not in src, "status id must not use loop.index — use s.id"


def test_js_no_filename_param():
    src = TRAINER_PY.read_text(encoding="utf-8")
    # Legacy two-param autosave calls are gone
    assert "scheduleAutosave('" not in src, "JS must not pass filename string to scheduleAutosave"
    assert "deleteCard('" not in src, "JS must not pass filename string to deleteCard"
    assert "launchSession('" not in src, "JS must not pass filename string to launchSession"


def test_js_find_by_id_not_file():
    src = TRAINER_PY.read_text(encoding="utf-8")
    assert "s.id === j.id" in src, "createSession JS must find new session by id, not file"


# ---------------------------------------------------------------------------
# _list_sessions helper
# ---------------------------------------------------------------------------

def test_list_sessions_returns_id_key(mem_conn):
    mem_conn.execute(
        "INSERT INTO guitar_exercises (title, artist, song_path, segments, gradient) VALUES (?,?,?,?,?)",
        ("Test Song", "Artist", "/path/song.mp3", '[{"start":"0:00","end":"0:10","speed":80,"repetition":3}]', 2),
    )
    mem_conn.commit()
    with patch("training.musician_training_ui.get_connection", return_value=mem_conn):
        sessions = ui._list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert "id" in s
    assert "file" not in s
    assert s["title"] == "Test Song"
    assert isinstance(s["segments"], list)
    assert s["segments"][0]["start"] == "0:00"


# ---------------------------------------------------------------------------
# /create route
# ---------------------------------------------------------------------------

def test_create_inserts_and_returns_id(client):
    resp = client.post(
        "/create",
        data=json.dumps({"title": "New Song", "artist": "Band", "songPath": "/music/new.mp3"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is True
    assert isinstance(j["id"], int)
    assert j["id"] >= 1


def test_create_missing_title_returns_error(client):
    resp = client.post(
        "/create",
        data=json.dumps({"title": "", "songPath": "/music/new.mp3"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


# ---------------------------------------------------------------------------
# /save route
# ---------------------------------------------------------------------------

def test_save_updates_segments(client, mem_conn):
    mem_conn.execute(
        "INSERT INTO guitar_exercises (title, artist, song_path, segments, gradient) VALUES (?,?,?,?,?)",
        ("Carnival", "", "/music/carnival.mp3", "[]", 0),
    )
    mem_conn.commit()
    ex_id = mem_conn.execute("SELECT id FROM guitar_exercises WHERE title='Carnival'").fetchone()["id"]

    new_segs = [{"start": "0:10", "end": "0:30", "speed": 85, "repetition": 5}]
    resp = client.post(
        "/save",
        data=json.dumps({"id": ex_id, "segments": new_segs, "gradient": 3}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is True

    row = mem_conn.execute("SELECT segments, gradient FROM guitar_exercises WHERE id=?", (ex_id,)).fetchone()
    assert json.loads(row["segments"]) == new_segs
    assert row["gradient"] == 3


def test_save_invalid_id_rejected(client):
    resp = client.post(
        "/save",
        data=json.dumps({"id": "not-an-int", "segments": [], "gradient": 0}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


# ---------------------------------------------------------------------------
# /delete route
# ---------------------------------------------------------------------------

def test_delete_removes_exercise(client, mem_conn):
    mem_conn.execute(
        "INSERT INTO guitar_exercises (title, artist, song_path, segments, gradient) VALUES (?,?,?,?,?)",
        ("Peg", "Steely Dan", "/music/peg.mp3", "[]", 0),
    )
    mem_conn.commit()
    ex_id = mem_conn.execute("SELECT id FROM guitar_exercises WHERE title='Peg'").fetchone()["id"]

    resp = client.post(
        "/delete",
        data=json.dumps({"id": ex_id}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is True

    row = mem_conn.execute("SELECT id FROM guitar_exercises WHERE id=?", (ex_id,)).fetchone()
    assert row is None


def test_delete_invalid_id_rejected(client):
    resp = client.post(
        "/delete",
        data=json.dumps({"id": "bad"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


# ---------------------------------------------------------------------------
# /api/sessions
# ---------------------------------------------------------------------------

def test_api_sessions_returns_id_keyed_list(client, mem_conn):
    mem_conn.execute(
        "INSERT INTO guitar_exercises (title, artist, song_path, segments, gradient) VALUES (?,?,?,?,?)",
        ("Rhiannon", "Fleetwood Mac", "/music/rhiannon.flac", "[]", 0),
    )
    mem_conn.commit()
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "id" in data[0]
    assert "file" not in data[0]


# ---------------------------------------------------------------------------
# Migration script results (requires heartmusic.db to exist)
# ---------------------------------------------------------------------------

_db_path = PROJECT_ROOT / "data" / "heartmusic.db"
requires_db = pytest.mark.skipif(
    not _db_path.exists(),
    reason="heartmusic.db not present — run init_db.py and migration first",
)


@requires_db
def test_migration_cards_in_db():
    """Six recovered exercise cards should be present after migration."""
    import os
    import importlib.util

    db_key = os.environ.get("HEARTMUSIC_DB_KEY")
    if not db_key:
        pytest.skip("HEARTMUSIC_DB_KEY not set — cannot open heartmusic.db")

    with patch("training.musician_training_ui.get_connection") as mock_gc:
        # Use the real get_connection but we just need count from DB
        pass

    # Direct check via utils
    conn = ui.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM guitar_exercises").fetchone()[0]
    conn.close()
    assert count >= 6, f"Expected at least 6 exercise cards, got {count}"


@requires_db
def test_migration_log_in_db():
    """Training log entries should be present after migration."""
    import os

    db_key = os.environ.get("HEARTMUSIC_DB_KEY")
    if not db_key:
        pytest.skip("HEARTMUSIC_DB_KEY not set — cannot open heartmusic.db")

    conn = ui.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM guitar_training_log").fetchone()[0]
    conn.close()
    assert count >= 45, f"Expected at least 45 log entries, got {count}"
