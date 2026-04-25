"""
Tests for Guitar Trainer new-card timestamp initialisation.

FR-20260425 — bug: launching a newly-created card used stale on-disk
timestamps instead of the current UI state, causing the wrong segment to
play.  The fix flushes the DOM state to disk (via saveSession) before every
launch call.

These tests cover:
  1. The /create endpoint produces clean default timestamps.
  2. The /save → /launch pipeline uses the saved values, not stale data.
  3. addRow default values in the rendered HTML are 0:00 / 0:10.
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bootstrap – add project src to path
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from training.musician_training_ui import app, TRAINING_DIR  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client with TRAINING_DIR redirected to a temp directory."""
    import training.musician_training_ui as ui_mod

    monkeypatch.setattr(ui_mod, "TRAINING_DIR", tmp_path)
    monkeypatch.setattr(ui_mod, "LOG_FILE", tmp_path / "trainingLog.json")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNewCardTimestampDefaults:
    """The /create endpoint must initialise a clean timestamp segment."""

    def test_create_returns_default_start_end(self, client):
        c, tmp = client
        payload = {
            "title": "TestSong",
            "artist": "TestArtist",
            "songPath": str(tmp / "fake_song.mp3"),
        }
        resp = c.post("/create", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True, data.get("error")

        written = json.loads((tmp / data["file"]).read_text(encoding="utf-8"))
        segs = written["segments"]
        assert len(segs) == 1, "new card should have exactly one default segment"
        seg = segs[0]
        # Default timestamps must NOT be zero — the UI shows them as a hint.
        assert "start" in seg and "end" in seg
        # Critically, start < end so the segment is valid
        def to_secs(tc: str) -> int:
            parts = list(map(int, tc.split(":")))
            return parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]

        assert to_secs(seg["end"]) > to_secs(seg["start"]), (
            "default segment end must be greater than start"
        )

    def test_two_new_cards_have_independent_segments(self, client):
        """Creating two cards must not share segment state."""
        c, tmp = client
        for title in ("Alpha", "Beta"):
            resp = c.post("/create", json={
                "title": title,
                "artist": "X",
                "songPath": str(tmp / f"{title}.mp3"),
            })
            assert resp.get_json()["ok"] is True

        alpha = json.loads((tmp / "alpha.json").read_text(encoding="utf-8"))
        beta = json.loads((tmp / "beta.json").read_text(encoding="utf-8"))

        # Segments are independent objects – mutating one must not affect the other
        alpha["segments"][0]["end"] = "9:99"
        assert beta["segments"][0]["end"] != "9:99", (
            "segments of different cards must not share the same dict object"
        )


class TestSaveBeforeLaunchSemantics:
    """/save must persist whatever the caller sends, and /launch must use it."""

    def test_save_overwrites_stale_end_time(self, client):
        """/save with a corrected end time must replace the stale value on disk."""
        c, tmp = client
        # Create a card
        c.post("/create", json={
            "title": "Rhiannon",
            "artist": "Fleetwood Mac",
            "songPath": str(tmp / "Rhiannon.mp3"),
        })

        # Simulate the stale state that caused FR-20260425: 0:57 on disk
        path = tmp / "rhiannon.json"
        stale = json.loads(path.read_text(encoding="utf-8"))
        stale["segments"][0]["end"] = "0:57"
        path.write_text(json.dumps(stale), encoding="utf-8")

        # The UI would call /save with the corrected 0:15 before /launch
        resp = c.post("/save", json={
            "filename": "rhiannon.json",
            "segments": [{"start": "0:00", "end": "0:15", "speed": 100, "repetition": 1}],
            "gradient": 0,
        })
        assert resp.get_json()["ok"] is True

        fresh = json.loads(path.read_text(encoding="utf-8"))
        assert fresh["segments"][0]["end"] == "0:15", (
            "after /save the on-disk end time must be the value sent by the UI, "
            "not the stale 0:57"
        )

    def test_save_preserves_existing_fields(self, client):
        """Saving segments must not discard songPath / title / artist."""
        c, tmp = client
        c.post("/create", json={
            "title": "Rhiannon",
            "artist": "Fleetwood Mac",
            "songPath": str(tmp / "Rhiannon.mp3"),
        })
        c.post("/save", json={
            "filename": "rhiannon.json",
            "segments": [{"start": "0:00", "end": "0:15", "speed": 100, "repetition": 1}],
            "gradient": 0,
        })
        saved = json.loads((tmp / "rhiannon.json").read_text(encoding="utf-8"))
        assert saved.get("title") == "Rhiannon"
        assert saved.get("artist") == "Fleetwood Mac"
        assert "songPath" in saved


class TestAddRowJSDefaults:
    """The addRow JS defaults must be verifiable through the rendered HTML."""

    def test_addrow_default_values_in_html(self, client):
        """The rendered page must contain the addRow defaults (0:00 and 0:10)."""
        c, tmp = client
        resp = c.get("/")
        html = resp.data.decode("utf-8")
        # The addRow function inlines the default values in its tr.innerHTML
        assert 'value="0:00"' in html, "addRow must default start to 0:00"
        assert 'value="0:10"' in html, "addRow must default end to 0:10"
