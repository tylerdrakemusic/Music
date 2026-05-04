"""Tests for Studio Equipment Panel — migrate script + Flask routes.

Uses an in-memory SQLite DB (monkeypatched via get_connection) for isolation.
Run: C:\\G\\python.exe -m pytest tests/test_studio_panel.py -v
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Make src importable
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_conn():
    """In-memory SQLite connection with studio_equipment table."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS studio_equipment (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            studio_name TEXT NOT NULL,
            category    TEXT NOT NULL,
            label       TEXT NOT NULL,
            spec_json   TEXT NOT NULL DEFAULT '{}',
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def patched_conn(mem_conn, monkeypatch):
    """Monkeypatch get_connection to return the in-memory connection (close-safe wrapper)."""
    import utils.init_db as init_db_mod

    class _NoClose:
        """Proxy that forwards all attribute access to the wrapped conn but ignores close()."""
        def __init__(self, conn):
            self._conn = conn

        def close(self):
            pass  # do NOT close the in-memory connection between route calls

        def __getattr__(self, name):
            return getattr(self._conn, name)

    proxy = _NoClose(mem_conn)

    def _fake_conn():
        return proxy

    monkeypatch.setattr(init_db_mod, "get_connection", _fake_conn)
    yield proxy


@pytest.fixture()
def flask_client(patched_conn):
    """Flask test client with patched DB."""
    import studio.studio_panel as panel_mod
    import utils.init_db as init_db_mod

    # Patch inside the panel module too
    panel_mod.get_connection = init_db_mod.get_connection

    panel_mod.app.config["TESTING"] = True
    with panel_mod.app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------

def test_migrate_creates_table_and_inserts_rows(patched_conn, monkeypatch):
    """Migration creates the studio_equipment table and inserts > 0 rows."""
    import studio.migrate_equipment_json as mig

    count = mig.migrate(conn=patched_conn)

    assert count > 0, "Expected at least one row inserted"
    rows = patched_conn._conn.execute("SELECT COUNT(*) FROM studio_equipment").fetchone()[0]
    assert rows == count


def test_migrate_is_idempotent(patched_conn):
    """Running migrate twice does not duplicate rows."""
    import studio.migrate_equipment_json as mig

    first = mig.migrate(conn=patched_conn)
    second = mig.migrate(conn=patched_conn)

    assert first > 0
    assert second == 0, "Second run should be a no-op (returns 0)"
    rows = patched_conn._conn.execute("SELECT COUNT(*) FROM studio_equipment").fetchone()[0]
    assert rows == first


# ---------------------------------------------------------------------------
# Flask route tests
# ---------------------------------------------------------------------------

def _seed(conn, studio="Personal Studio", category="Guitar", label="Fender Stratocaster"):
    conn._conn.execute(
        "INSERT INTO studio_equipment (studio_name, category, label, spec_json) VALUES (?,?,?,?)",
        (studio, category, label, '{"serial_number": "X123"}'),
    )
    conn._conn.commit()


def test_get_equipment_returns_list(flask_client, patched_conn):
    """GET /api/equipment returns a JSON list."""
    _seed(patched_conn)
    res = flask_client.get("/api/equipment")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["label"] == "Fender Stratocaster"


def test_post_equipment_creates_row(flask_client, patched_conn):
    """POST /api/equipment creates a new item and returns 201."""
    payload = {
        "studio_name": "Personal Studio",
        "category": "Microphone",
        "label": "Shure SM7B",
        "spec_json": '{"type": "Dynamic"}',
    }
    res = flask_client.post(
        "/api/equipment",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["label"] == "Shure SM7B"
    assert data["category"] == "Microphone"


def test_put_equipment_updates_row(flask_client, patched_conn):
    """PUT /api/equipment/<id> updates an existing item."""
    _seed(patched_conn)
    row = patched_conn._conn.execute("SELECT id FROM studio_equipment LIMIT 1").fetchone()
    item_id = row[0]

    payload = {"label": "Gibson Les Paul"}
    res = flask_client.put(
        f"/api/equipment/{item_id}",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["label"] == "Gibson Les Paul"


def test_delete_equipment_removes_row(flask_client, patched_conn):
    """DELETE /api/equipment/<id> removes the item (verified via GET)."""
    _seed(patched_conn)
    row = patched_conn._conn.execute("SELECT id FROM studio_equipment LIMIT 1").fetchone()
    item_id = row[0]

    res = flask_client.delete(f"/api/equipment/{item_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["deleted"] == item_id

    # Verify removal via GET (avoids using closed connection)
    get_res = flask_client.get("/api/equipment")
    remaining_ids = [item["id"] for item in get_res.get_json()]
    assert item_id not in remaining_ids
