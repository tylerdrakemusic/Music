"""Tests for Rhyme Grouper hook-worthy line support."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import analysis.music_dashboard as dash_mod
from analysis.music_dashboard import app


def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class _PersistentConn:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    conn = _make_mem_conn()
    yield conn
    conn.close()


@pytest.fixture()
def client(mem_conn: sqlite3.Connection):
    persistent = _PersistentConn(mem_conn)

    @contextmanager
    def _fake_get_connection():
        yield persistent

    app.config["TESTING"] = True
    with patch.object(dash_mod, "get_connection", _fake_get_connection):
        with app.test_client() as c:
            yield c


def test_post_line_marks_hook(client):
    res = client.post(
        "/rhymes/lines",
        json={"line": "Hold the high note", "is_hook": True},
    )

    assert res.status_code == 201
    data = res.get_json()
    assert data["line"] == "Hold the high note"
    assert data["is_hook"] is True


def test_toggle_hook_flag_updates_line(client):
    post_res = client.post(
        "/rhymes/lines",
        json={"line": "Open up the chorus", "is_hook": False},
    )
    assert post_res.status_code == 201
    line_id = post_res.get_json()["id"]

    put_res = client.put(f"/rhymes/lines/{line_id}", json={"is_hook": True})
    assert put_res.status_code == 200
    updated = put_res.get_json()
    assert updated["is_hook"] is True

    revert_res = client.put(f"/rhymes/lines/{line_id}", json={"is_hook": False})
    assert revert_res.status_code == 200
    reverted = revert_res.get_json()
    assert reverted["is_hook"] is False


def test_stats_includes_hook_count(client):
    client.post("/rhymes/lines", json={"line": "First hook line", "is_hook": True})
    client.post("/rhymes/lines", json={"line": "Second line", "is_hook": False})

    res = client.get("/rhymes/stats")
    assert res.status_code == 200
    stats = res.get_json()
    assert stats["hook_lines"] == 1
    assert stats["total_lines"] >= 2
