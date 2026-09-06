"""Tests for independent terminal playback settings per exercise row."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAINER_PY = PROJECT_ROOT / "src" / "training" / "musician_training_ui.py"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import training.musician_training_ui as ui
import focused_musician_training as runner


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
"""


class _NoClose:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self._connection.__enter__()

    def __exit__(self, *args):
        return self._connection.__exit__(*args)


@pytest.fixture()
def client():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA)
    segments = [
        {"start": "0:03", "end": "0:09", "speed": 75, "repetition": 2, "gradient": 5},
        {"start": "1:10", "end": "1:22", "speed": 125, "repetition": 3},
    ]
    connection.execute(
        "INSERT INTO guitar_exercises (title, song_path, segments, gradient) VALUES (?, ?, ?, ?)",
        ("Isolation", "C:/music/isolation.mp3", json.dumps(segments), 7),
    )
    connection.commit()
    ui.app.config["TESTING"] = True
    with patch.object(ui, "get_connection", return_value=_NoClose(connection)):
        with ui.app.test_client() as test_client:
            yield test_client, connection
    connection.close()


def test_playback_plan_resets_gradient_for_each_row():
    segments = [
        {"start": "0:03", "end": "0:09", "speed": 75, "repetition": 2, "gradient": 5},
        {"start": "1:10", "end": "1:22", "speed": 125, "repetition": 3, "gradient": 2},
    ]

    plan = runner.build_playback_plan(segments, default_gradient=7)

    assert [(item["start"], item["end"], item["ramped_speed"], item["repetition"]) for item in plan] == [
        (3, 9, 75.0, 1),
        (3, 9, 80.0, 1),
        (70, 82, 125.0, 1),
        (70, 82, 127.0, 1),
        (70, 82, 129.0, 1),
    ]
    assert [item["ramped_speed"] for item in plan] == [75.0, 80.0, 125.0, 127.0, 129.0]


def test_playback_plan_uses_default_gradient_for_legacy_rows():
    plan = runner.build_playback_plan(
        [{"start": "0:00", "end": "0:05", "speed": 100, "repetition": 2}],
        default_gradient=4,
    )

    assert [item["ramped_speed"] for item in plan] == [100.0, 104.0]


def test_exercise_segment_table_contains_new_gradient_column() -> None:
    source = TRAINER_PY.read_text(encoding="utf-8")
    assert ".exercise-segments" in source
    assert ".exercise-segments{width:100%;table-layout:fixed" in source
    assert ".exercise-segments input{min-width:0" in source
    assert "#sessions-grid table{width:100%;table-layout:fixed}" in source
    assert "<th>Gradient</th>" in source
    assert 'data-field="gradient"' in source

def test_save_preserves_row_playback_settings(client):
    test_client, connection = client
    segments = [
        {"start": "0:11", "end": "0:19", "speed": 82, "repetition": 4, "gradient": 3},
        {"start": "2:01", "end": "2:17", "speed": 118, "repetition": 1, "gradient": 0},
    ]

    response = test_client.post("/save", json={"id": 1, "segments": segments, "gradient": 9})

    assert response.get_json()["ok"] is True
    saved = connection.execute("SELECT segments FROM guitar_exercises WHERE id=1").fetchone()
    assert json.loads(saved["segments"]) == segments


def test_launch_payload_contains_saved_row_playback_settings(client, tmp_path):
    test_client, _ = client
    training_dir = tmp_path / "training"
    training_dir.mkdir()
    with patch.object(ui, "TRAINING_DIR", training_dir), patch.object(ui.subprocess, "Popen") as popen:
        response = test_client.post("/launch", json={"id": 1})

    assert response.get_json()["ok"] is True
    payload = json.loads((training_dir / "_run_1.json").read_text(encoding="utf-8"))
    assert payload["gradient"] == 7
    assert payload["segments"] == [
        {"start": "0:03", "end": "0:09", "speed": 75, "repetition": 2, "gradient": 5},
        {"start": "1:10", "end": "1:22", "speed": 125, "repetition": 3},
    ]
    popen.assert_called_once()