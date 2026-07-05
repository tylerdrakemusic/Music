"""Tests for tools/migrate_guitar_tone_profiles.py (FR-20260705-guitar-tech-persona-agent).

Covers:
  - migrate(conn) creates the guitar_tone_profiles table
  - migrate(conn) is safe to run twice (idempotent)
  - migrated table enforces the same constraints as the schema spec
    (cascade delete, default status, unique song+persona)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT / "src"), str(_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from migrate_guitar_tone_profiles import migrate  # noqa: E402

_BASE_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS catalog_songs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    artist        TEXT NOT NULL,
    key_sig       TEXT,
    bpm           INTEGER
);
"""


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_BASE_SCHEMA)
    c.execute("PRAGMA foreign_keys=ON")
    yield c
    c.close()


def test_migrate_creates_table(conn):
    migrate(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "guitar_tone_profiles" in tables


def test_migrate_is_idempotent(conn):
    migrate(conn)
    migrate(conn)  # must not raise
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='guitar_tone_profiles'"
    ).fetchall()]
    assert len(tables) == 1


def test_migrated_table_defaults_and_cascade(conn):
    migrate(conn)
    cur = conn.execute(
        "INSERT INTO catalog_songs (title, artist, key_sig, bpm) VALUES (?,?,?,?)",
        ("The Letter", "Joe Cocker", "Am", 96),
    )
    conn.commit()
    song_id = cur.lastrowid

    conn.execute(
        "INSERT INTO guitar_tone_profiles (catalog_song_id, persona, hlx_filename) VALUES (?,?,?)",
        (song_id, "Stevie Ray Vaughan", "The_Letter_Joe_Cocker.hlx"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT status FROM guitar_tone_profiles WHERE catalog_song_id=?", (song_id,)
    ).fetchone()
    assert row["status"] == "proposed"

    conn.execute("DELETE FROM catalog_songs WHERE id=?", (song_id,))
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM guitar_tone_profiles WHERE catalog_song_id=?", (song_id,)
    ).fetchone()[0]
    assert remaining == 0
