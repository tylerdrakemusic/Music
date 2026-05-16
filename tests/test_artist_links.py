"""Tests for FR-20260515-artist-links-pill-music-dashboard.

AC coverage:
 - artist_links table exists in schema and accepts all valid rows
 - migrate_links.py: JSON parses cleanly and collect_rows() produces valid rows
 - GET /api/links returns 200 JSON list
 - POST /api/links inserts and returns 201 with new row
 - PUT  /api/links/<id> updates and returns updated row
 - DELETE /api/links/<id> removes row, second call returns 404
 - Existing routes (/, /api/tracks, /api/albums) still return 200

DB isolation: all DB-dependent tests use an in-memory SQLite DB seeded from
utils.init_db._SCHEMA_SQL — no real heartmusic.db or HEARTMUSIC_DB_KEY needed.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import _SCHEMA_SQL, _SEED_SQL  # noqa: PLC2701


# ── In-memory DB fixture ──────────────────────────────────────────────────────

def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.executescript(_SEED_SQL)
    return conn


class _PersistentConn:
    """Wrap a sqlite3.Connection so close() is a no-op and it works as a context manager."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass  # keep alive across requests

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


@pytest.fixture(scope="module")
def mem_conn():
    conn = _make_mem_conn()
    yield conn
    conn.close()


@pytest.fixture()
def client(mem_conn):
    """Flask test client backed by an in-memory DB."""
    import analysis.music_dashboard as dash_mod
    from analysis.music_dashboard import app

    persistent = _PersistentConn(mem_conn)

    @contextmanager
    def _fake_get_connection():
        yield persistent

    app.config["TESTING"] = True
    with patch.object(dash_mod, "get_connection", _fake_get_connection):
        with app.test_client() as c:
            yield c


# ── Schema tests ──────────────────────────────────────────────────────────────

def test_artist_links_table_exists(mem_conn) -> None:
    """artist_links table must exist in the schema."""
    row = mem_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='artist_links'"
    ).fetchone()
    assert row is not None, "artist_links table not found in schema"


def test_artist_links_insert_and_query(mem_conn) -> None:
    """Should be able to insert a row and read it back."""
    mem_conn.execute(
        """INSERT INTO artist_links (category, platform, label, url, status)
           VALUES ('distribution', 'Spotify', 'Artist page', 'https://spotify.test', 'confirmed')"""
    )
    mem_conn.commit()
    row = mem_conn.execute(
        "SELECT * FROM artist_links WHERE platform='Spotify'"
    ).fetchone()
    assert row is not None
    assert row["category"] == "distribution"
    assert row["status"] == "confirmed"


def test_artist_links_check_constraint(mem_conn) -> None:
    """CHECK constraint on category must reject invalid values."""
    with pytest.raises(Exception):
        mem_conn.execute(
            "INSERT INTO artist_links (category, platform, label) VALUES ('INVALID', 'X', 'Y')"
        )
        mem_conn.commit()


# ── Migration logic tests (no DB write) ──────────────────────────────────────

def test_migrate_links_json_loads() -> None:
    """load_data() must parse linkTyler.json without error."""
    import utils.migrate_links as ml

    data = ml.load_data()
    assert isinstance(data, dict), "load_data() must return a dict"
    # At least one of the expected top-level keys must be present
    assert "emails" in data or "distribution_platforms" in data


def test_collect_rows_produces_valid_rows() -> None:
    """collect_rows() must produce rows with required fields and valid enum values."""
    import utils.migrate_links as ml

    data = ml.load_data()
    rows = ml.collect_rows(data)

    assert len(rows) > 0, "No rows produced by collect_rows()"

    valid_cats = {"email", "social", "payment", "distribution"}
    valid_statuses = {"confirmed", "pending", "broken"}

    for row in rows:
        assert row["category"] in valid_cats,    f"Bad category: {row['category']}"
        assert row["status"] in valid_statuses,  f"Bad status: {row['status']}"
        assert row["platform"],                  "platform must not be empty"
        assert row["label"],                     "label must not be empty"


def test_collect_rows_pending_detection() -> None:
    """Rows with placeholder URLs must have status='pending'."""
    import utils.migrate_links as ml

    data = ml.load_data()
    rows = ml.collect_rows(data)

    pending = [r for r in rows if r["status"] == "pending"]
    assert pending, "Expected at least one pending row (placeholder URLs in source JSON)"

    for r in pending:
        text = " ".join(filter(None, [
            r.get("url") or "", r.get("embed_html") or "", r.get("label") or "",
        ])).lower()
        needles = ("yourartistid", "yourtrackid", "yourprofile2", "pending")
        assert any(n in text for n in needles), (
            f"Pending row doesn't contain a known pending pattern: {r}"
        )


# ── API tests (Flask client) ──────────────────────────────────────────────────

def test_get_links_returns_200(client) -> None:
    res = client.get("/api/links")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_post_links_inserts_and_returns_201(client) -> None:
    payload = {
        "category": "distribution",
        "platform": "TestPlatform",
        "label": "Test Artist Page",
        "url": "https://example.com/test",
        "status": "confirmed",
    }
    res = client.post("/api/links", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["platform"] == "TestPlatform"
    assert data["label"] == "Test Artist Page"
    assert data["id"] is not None


def test_post_links_rejects_missing_required(client) -> None:
    res = client.post("/api/links", json={"platform": "X"})
    assert res.status_code == 400


def test_put_links_updates_row(client) -> None:
    # Create
    res = client.post("/api/links", json={
        "category": "social",
        "platform": "EditTest",
        "label": "Original Label",
        "url": "https://example.com/edit",
        "status": "confirmed",
    })
    assert res.status_code == 201
    link_id = res.get_json()["id"]

    # Update
    res = client.put(f"/api/links/{link_id}", json={"label": "Updated Label", "status": "pending"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["label"] == "Updated Label"
    assert data["status"] == "pending"


def test_delete_links_removes_row(client) -> None:
    # Create
    res = client.post("/api/links", json={
        "category": "payment",
        "platform": "DelTest",
        "label": "Delete Me",
        "url": "https://example.com/del",
        "status": "confirmed",
    })
    assert res.status_code == 201
    link_id = res.get_json()["id"]

    # Delete
    res = client.delete(f"/api/links/{link_id}")
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    # Second delete → 404
    res = client.delete(f"/api/links/{link_id}")
    assert res.status_code == 404


def test_existing_routes_still_return_200(client) -> None:
    """Regression guard: existing dashboard routes must not be broken."""
    assert client.get("/").status_code == 200
    assert client.get("/api/tracks").status_code == 200
    assert client.get("/api/albums").status_code == 200
