"""Tests for FR-20260428-gig-inventory-checklist.

AC9: 3 tests covering the gig_inventory table and the regenerated HTML panel.

DB isolation: all DB-dependent tests use an in-memory SQLite DB seeded via
utils.init_db._SCHEMA_SQL and _SEED_SQL — no real heartmusic.db or
HEARTMUSIC_DB_KEY required. Safe for CI runners.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

PANEL_HTML = PROJECT_ROOT / "reports" / "band_management_panel.html"

EXPECTED_ITEMS = [
    "Guitar",
    "Guitar Stand",
    "Amp",
    "Amp stand",
    "Trombone",
    "Trombone stand",
    "iPad",
    "Gig Bag",
    "Extension Chord",
    "Pedal Board",
    "Cooling Fan",
    "Wireless 1/4",
]


@pytest.fixture(scope="module")
def db_conn():
    """In-memory SQLite DB seeded with the real schema + seed data.

    Uses utils.init_db._SCHEMA_SQL and _SEED_SQL directly so the fixture
    always stays in sync with production schema without touching the real DB.
    """
    from utils.init_db import _SCHEMA_SQL, _SEED_SQL  # noqa: PLC2701

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.executescript(_SEED_SQL)
    yield conn
    conn.close()


def test_gig_inventory_table_exists_and_has_rows(db_conn) -> None:
    """gig_inventory table must exist and have at least 12 rows."""
    rows = db_conn.execute("SELECT COUNT(*) AS cnt FROM gig_inventory").fetchone()
    assert rows["cnt"] >= 12, f"Expected >= 12 rows, got {rows['cnt']}"


def test_gig_inventory_expected_items_present(db_conn) -> None:
    """All 12 seed items must be present in gig_inventory."""
    rows = db_conn.execute("SELECT item FROM gig_inventory").fetchall()
    items_in_db = {r["item"] for r in rows}
    missing = [i for i in EXPECTED_ITEMS if i not in items_in_db]
    assert not missing, f"Missing items in gig_inventory: {missing}"


def test_html_panel_contains_inventory_tab() -> None:
    """Generated HTML must contain the Gig Inventory vtab and section."""
    assert PANEL_HTML.exists(), f"Panel HTML not found: {PANEL_HTML}"
    content = PANEL_HTML.read_text(encoding="utf-8")
    assert "Gig Inventory" in content, "Missing 'Gig Inventory' text in panel HTML"
    assert "bm-inv-section" in content, "Missing inventory section id in panel HTML"
    assert "bm-print-inv-btn" in content, "Missing print inventory button in panel HTML"
