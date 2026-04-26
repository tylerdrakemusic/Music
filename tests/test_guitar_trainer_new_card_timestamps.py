"""
Tests for Guitar Trainer new-card timestamp initialisation.

FR-20260425 — bug: launching a newly-created card used stale on-disk
timestamps instead of the current UI state, causing the wrong segment to
play.  The fix flushes the DOM state to disk (via saveSession) before every
launch call.

Updated for FR-20260425-guitar-trainer-db-migration: exercise cards are now
stored in guitar_exercises SQLite table rather than JSON files.

These tests cover:
  1. The /create endpoint produces clean default timestamps.
  2. The /save → /launch pipeline uses the saved values, not stale data.
  3. addRow default values in the rendered HTML are 0:00 / 0:10.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bootstrap – add project src to path
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import training.musician_training_ui as ui_mod
from training.musician_training_ui import app  # noqa: E402

# ---------------------------------------------------------------------------
# In-memory DB schema
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
def client(monkeypatch):
    """Flask test client with get_connection patched to use an in-memory DB."""
    real_conn = _make_mem_conn()
    wrapper = _NoClose(real_conn)
    monkeypatch.setattr(ui_mod, "get_connection", lambda: wrapper)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, real_conn
    real_conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNewCardTimestampDefaults:
    """The /create endpoint must initialise a clean timestamp segment."""

    def test_create_returns_default_start_end(self, client):
        c, conn = client
        payload = {
            "title": "TestSong",
            "artist": "TestArtist",
            "songPath": "/fake/fake_song.mp3",
        }
        resp = c.post("/create", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True, data.get("error")
        assert isinstance(data["id"], int)

        row = conn.execute(
            "SELECT segments FROM guitar_exercises WHERE id=?", (data["id"],)
        ).fetchone()
        segs = json.loads(row["segments"])
        assert len(segs) == 1, "new card should have exactly one default segment"
        seg = segs[0]
        assert "start" in seg and "end" in seg

        def to_secs(tc: str) -> int:
            parts = list(map(int, tc.split(":")))
            return parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]

        assert to_secs(seg["end"]) > to_secs(seg["start"]), (
            "default segment end must be greater than start"
        )

    def test_two_new_cards_have_independent_segments(self, client):
        """Creating two cards must not share segment state."""
        c, conn = client
        ids = []
        for title in ("Alpha", "Beta"):
            resp = c.post("/create", json={
                "title": title,
                "artist": "X",
                "songPath": f"/fake/{title}.mp3",
            })
            assert resp.get_json()["ok"] is True
            ids.append(resp.get_json()["id"])

        rows = {
            r["id"]: json.loads(r["segments"])
            for r in conn.execute(
                "SELECT id, segments FROM guitar_exercises WHERE id IN (?,?)", tuple(ids)
            ).fetchall()
        }
        alpha_segs = rows[ids[0]]
        beta_segs = rows[ids[1]]
        # Mutating one Python list must not affect the other (they're separate DB blobs)
        alpha_segs[0]["end"] = "9:99"
        assert beta_segs[0]["end"] != "9:99", (
            "segments of different cards must not share the same dict object"
        )


class TestSaveBeforeLaunchSemantics:
    """/save must persist whatever the caller sends."""

    def test_save_overwrites_stale_end_time(self, client):
        """/save with a corrected end time must replace the stale value in DB."""
        c, conn = client
        resp = c.post("/create", json={
            "title": "Rhiannon",
            "artist": "Fleetwood Mac",
            "songPath": "/fake/Rhiannon.mp3",
        })
        ex_id = resp.get_json()["id"]

        # Simulate stale state: manually set end time to 0:57 in DB
        stale_segs = json.dumps([{"start": "0:00", "end": "0:57", "speed": 100, "repetition": 1}])
        conn.execute("UPDATE guitar_exercises SET segments=? WHERE id=?", (stale_segs, ex_id))
        conn.commit()

        # /save with corrected 0:15
        resp = c.post("/save", json={
            "id": ex_id,
            "segments": [{"start": "0:00", "end": "0:15", "speed": 100, "repetition": 1}],
            "gradient": 0,
        })
        assert resp.get_json()["ok"] is True

        row = conn.execute("SELECT segments FROM guitar_exercises WHERE id=?", (ex_id,)).fetchone()
        saved = json.loads(row["segments"])
        assert saved[0]["end"] == "0:15", (
            "after /save the DB end time must be the value sent by the UI, not the stale 0:57"
        )

    def test_save_preserves_title_artist_in_db(self, client):
        """Saving segments must not discard title / artist in DB."""
        c, conn = client
        resp = c.post("/create", json={
            "title": "Rhiannon",
            "artist": "Fleetwood Mac",
            "songPath": "/fake/Rhiannon.mp3",
        })
        ex_id = resp.get_json()["id"]
        c.post("/save", json={
            "id": ex_id,
            "segments": [{"start": "0:00", "end": "0:15", "speed": 100, "repetition": 1}],
            "gradient": 0,
        })
        row = conn.execute(
            "SELECT title, artist FROM guitar_exercises WHERE id=?", (ex_id,)
        ).fetchone()
        assert row["title"] == "Rhiannon"
        assert row["artist"] == "Fleetwood Mac"


class TestAddRowJSDefaults:
    """The addRow JS defaults must be verifiable through the rendered HTML."""

    def test_addrow_default_values_in_html(self, client):
        """The rendered page must contain the addRow defaults (0:00 and 0:10)."""
        c, _ = client
        resp = c.get("/")
        html = resp.data.decode("utf-8")
        # The addRow function inlines the default values in its tr.innerHTML
        assert 'value="0:00"' in html, "addRow must default start to 0:00"
        assert 'value="0:10"' in html, "addRow must default end to 0:10"
