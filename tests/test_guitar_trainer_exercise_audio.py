"""Focused tests for full-file audio in guitar trainer exercise cards."""
from __future__ import annotations

import json
import sqlite3
import sys
from urllib.parse import quote
from pathlib import Path
from unittest.mock import patch

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import training.musician_training_ui as ui


_SCHEMA = """
CREATE TABLE guitar_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    song_path TEXT NOT NULL DEFAULT '',
    segments TEXT NOT NULL DEFAULT '[]',
    gradient INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE guitar_training_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER,
    song_path TEXT NOT NULL DEFAULT '',
    seg_start TEXT NOT NULL DEFAULT '',
    seg_end TEXT NOT NULL DEFAULT '',
    repetition INTEGER NOT NULL DEFAULT 1,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class _NoClose:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def close(self) -> None:
        pass


@pytest.fixture()
def client(tmp_path: Path):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA)
    audio_file = tmp_path / "practice.mp3"
    audio_file.write_bytes(b"fake-mp3")
    connection.execute(
        "INSERT INTO guitar_exercises (title, artist, song_path, segments) VALUES (?, ?, ?, ?)",
        ("Practice", "Artist", str(audio_file), json.dumps([])),
    )
    connection.commit()
    ui.app.config["TESTING"] = True
    with patch.object(ui, "get_connection", return_value=_NoClose(connection)):
        with patch.object(ui, "_ART_ALLOWED_ROOTS", (tmp_path.resolve(),)):
            with ui.app.test_client() as test_client:
                yield test_client, audio_file
    connection.close()


def test_exercise_card_renders_isolated_full_file_player(client) -> None:
    test_client, audio_file = client

    response = test_client.get("/")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'class="exercise-audio"' in html
    assert 'data-exercise-id="1"' in html
    assert f"/audio?path={quote(str(audio_file), safe='')}" in html
    assert 'id="exercise-play-1"' in html
    assert 'id="exercise-timeline-1"' in html
    assert 'id="exercise-current-1"' in html
    assert 'id="exercise-duration-1"' in html


def test_audio_route_serves_associated_file(client) -> None:
    test_client, audio_file = client

    response = test_client.get(f"/audio?path={audio_file}")

    assert response.status_code == 200
    assert response.data == b"fake-mp3"
    assert response.content_type == "audio/mpeg"


def test_audio_route_rejects_missing_and_outside_files(client, tmp_path: Path) -> None:
    test_client, _ = client
    outside = tmp_path.parent / "outside.mp3"
    outside.write_bytes(b"not-served")

    assert test_client.get(f"/audio?path={tmp_path / 'missing.mp3'}").status_code == 404
    assert test_client.get(f"/audio?path={outside}").status_code == 403


def test_exercise_player_wires_metadata_timeupdate_seek_restart_and_error() -> None:
    source = ui.HTML

    assert "loadedmetadata" in source
    assert "timeupdate" in source
    assert "audio.currentTime = Number" in source
    assert "restartExerciseAudio" in source
    assert "audio.onerror" in source
    assert "Audio unavailable" in source


def test_scale_audio_and_playback_hooks_remain_separate() -> None:
    source = ui.HTML

    assert 'id="instructor-audio"' in source
    assert "/api/instructor-audio?position=" in source
    assert "window.scaleToggle = async function()" in source
    assert "function playNote(midi, durationMs, accentType = 'normal')" in source