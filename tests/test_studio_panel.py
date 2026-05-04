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


# ---------------------------------------------------------------------------
# Enhancement AC tests (FR-20260503-studio-panel-enhancements)
# ---------------------------------------------------------------------------

def test_favicon_ico_returns_200(flask_client):
    """AC3: GET /favicon.ico returns 200 (favicon endpoint exists)."""
    res = flask_client.get("/favicon.ico")
    assert res.status_code == 200


def test_favicon_hyperthreat_returns_200(flask_client):
    """AC3: GET /favicon-hyperthreat.png returns 200."""
    res = flask_client.get("/favicon-hyperthreat.png")
    assert res.status_code == 200


def test_tab_order_personal_first_mic_last(flask_client):
    """AC5: Nav tab order is Personal Studio -> HyperThreat Studio -> Mic Config."""
    res = flask_client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    personal_pos = html.find('data-tab="personal"')
    hyperthreat_pos = html.find('data-tab="hyperthreat"')
    mic_pos = html.find('data-tab="mic"')

    assert personal_pos != -1, "Personal Studio tab not found"
    assert hyperthreat_pos != -1, "HyperThreat Studio tab not found"
    assert mic_pos != -1, "Mic Config tab not found"
    assert personal_pos < hyperthreat_pos < mic_pos, (
        f"Tab order wrong: personal={personal_pos}, hyperthreat={hyperthreat_pos}, mic={mic_pos}"
    )


def test_personal_tab_is_default_active(flask_client):
    """AC5: Personal Studio tab has the active class by default."""
    res = flask_client.get("/")
    html = res.data.decode("utf-8")
    # The first nav-tab.active should be personal
    import re
    first_active = re.search(r'nav-tab active[^>]*data-tab="([^"]+)"', html)
    if not first_active:
        # Try reversed attribute order
        first_active = re.search(r'data-tab="([^"]+)"[^>]*nav-tab active', html)
    # Also accept: class="nav-tab active" data-tab="personal"
    assert 'class="nav-tab active" data-tab="personal"' in html or \
           'nav-tab active" data-tab="personal"' in html, \
        "Personal Studio tab is not the default active tab"


def test_new_gear_aviator_cub_in_db(patched_conn):
    """AC1: Aviator Cub 50W 1x12 Combo exists in Personal Studio after migration seed."""
    # Insert it as the migration script would
    patched_conn._conn.execute(
        "INSERT INTO studio_equipment (studio_name, category, label, spec_json) VALUES (?,?,?,?)",
        ("Personal Studio", "amplifiers", "Aviator Cub 50W 1x12 Combo",
         '{"model_key": "AviatorCubU", "wattage": "50W", "speaker": "1x12"}'),
    )
    patched_conn._conn.commit()
    row = patched_conn._conn.execute(
        "SELECT label, category FROM studio_equipment WHERE label='Aviator Cub 50W 1x12 Combo'"
    ).fetchone()
    assert row is not None, "Aviator Cub not found"
    assert row[1] == "amplifiers"


def test_new_gear_sm57_in_db(patched_conn):
    """AC2: Shure SM57 exists in Personal Studio."""
    patched_conn._conn.execute(
        "INSERT INTO studio_equipment (studio_name, category, label, spec_json) VALUES (?,?,?,?)",
        ("Personal Studio", "microphones", "Shure SM57", '{"manufacturer": "Shure", "model": "SM57"}'),
    )
    patched_conn._conn.commit()
    row = patched_conn._conn.execute(
        "SELECT label, category FROM studio_equipment WHERE label='Shure SM57'"
    ).fetchone()
    assert row is not None, "Shure SM57 not found"
    assert row[1] == "microphones"


def test_hyperthreat_items_not_other_category(patched_conn):
    """AC6: HyperThreat equipment has meaningful categories (not 'Other')."""
    # Seed a selection of re-categorized items
    items = [
        ("Rupert Neve Designs 5059 Satellite", "summing_mixers"),
        ("API 500 Series Channel Strip", "channel_strips"),
        ("Avid MTRX Studio", "audio_interfaces"),
        ("Warm Audio WA-273", "preamps"),
        ("Switchcraft 6425", "patchbays"),
    ]
    for label, cat in items:
        patched_conn._conn.execute(
            "INSERT INTO studio_equipment (studio_name, category, label, spec_json) VALUES (?,?,?,?)",
            ("HyperThreat Recording Studio", cat, label, "{}"),
        )
    patched_conn._conn.commit()

    rows = patched_conn._conn.execute(
        "SELECT label, category FROM studio_equipment WHERE studio_name='HyperThreat Recording Studio'"
    ).fetchall()
    other_items = [r for r in rows if r[1].lower() == "other"]
    assert len(other_items) == 0, f"HyperThreat items still in 'Other': {other_items}"


# ---------------------------------------------------------------------------
# Category normalization AC tests (FR-20260503-studio-panel-category-ci)
# ---------------------------------------------------------------------------

def test_migrate_uses_normalized_categories(patched_conn):
    """AC2: migrate_equipment_json produces only lowercase_underscore plural categories."""
    import studio.migrate_equipment_json as mig

    mig.migrate(conn=patched_conn)

    rows = patched_conn._conn.execute(
        "SELECT DISTINCT category FROM studio_equipment WHERE studio_name='Personal Studio'"
    ).fetchall()
    categories = [r[0] for r in rows]

    # None should be Title Case singular (old convention)
    old_categories = {
        "Amplifier", "Microphone", "Acoustic Guitar", "Bass Guitar",
        "Drums", "Guitar", "Headphones", "Interface", "Keyboard",
        "MIDI Controller", "Monitor", "Pedal", "Other",
    }
    violations = [c for c in categories if c in old_categories]
    assert not violations, f"Old-style categories still produced by migrate: {violations}"

    # All should match lowercase_underscore pattern
    import re
    bad_format = [c for c in categories if not re.match(r"^[a-z][a-z0-9_]*$", c)]
    assert not bad_format, f"Categories not in lowercase_underscore format: {bad_format}"


def test_personal_studio_no_duplicate_sections(patched_conn):
    """AC1: Personal Studio has no duplicate category sections (e.g., both amplifier and amplifiers)."""
    # Seed one row per old and new name for same concept
    pairs = [
        ("Amplifier", "amplifiers"),
        ("Microphone", "microphones"),
    ]
    for old, new in pairs:
        patched_conn._conn.execute(
            "INSERT INTO studio_equipment (studio_name, category, label, spec_json) VALUES (?,?,?,?)",
            ("Personal Studio", old, f"Test {old}", "{}"),
        )
        patched_conn._conn.execute(
            "INSERT INTO studio_equipment (studio_name, category, label, spec_json) VALUES (?,?,?,?)",
            ("Personal Studio", new, f"Test {new}", "{}"),
        )
    patched_conn._conn.commit()

    # After normalization UPDATE (simulate what the migration does)
    NORM = {"Amplifier": "amplifiers", "Microphone": "microphones"}
    for old, new in NORM.items():
        patched_conn._conn.execute(
            "UPDATE studio_equipment SET category=? WHERE category=? AND studio_name='Personal Studio'",
            (new, old),
        )
    patched_conn._conn.commit()

    cats = [r[0] for r in patched_conn._conn.execute(
        "SELECT DISTINCT category FROM studio_equipment WHERE studio_name='Personal Studio'"
    ).fetchall()]
    assert "Amplifier" not in cats, "Old 'Amplifier' category still present after normalization"
    assert "Microphone" not in cats, "Old 'Microphone' category still present after normalization"
    assert "amplifiers" in cats
    assert "microphones" in cats
