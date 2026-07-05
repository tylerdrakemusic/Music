"""Tests for FR-20260705-guitar-tech-persona-agent: guitar_tone_profiles table.

Covers:
  - guitar_tone_profiles table exists with the expected columns
  - default status is 'proposed'
  - CHECK constraint rejects an invalid status value
  - UNIQUE(catalog_song_id, persona) is enforced
  - ON DELETE CASCADE removes profiles when the parent catalog_songs row is removed
"""
from __future__ import annotations

import sqlite3

import pytest

_SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS catalog_songs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    artist        TEXT NOT NULL,
    key_sig       TEXT,
    bpm           INTEGER,
    bpm_source    TEXT,
    genre         TEXT,
    tags          TEXT,
    notes         TEXT,
    source_file   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS guitar_tone_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_song_id INTEGER NOT NULL REFERENCES catalog_songs(id) ON DELETE CASCADE,
    persona         TEXT NOT NULL,
    rationale       TEXT,
    hlx_filename    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'proposed'
                    CHECK(status IN ('proposed','approved','rejected')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(catalog_song_id, persona)
);

CREATE INDEX IF NOT EXISTS idx_guitar_tone_profiles_song ON guitar_tone_profiles(catalog_song_id);
"""


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    c.execute("PRAGMA foreign_keys=ON")
    yield c
    c.close()


@pytest.fixture()
def song_id(conn):
    cur = conn.execute(
        "INSERT INTO catalog_songs (title, artist, key_sig, bpm) VALUES (?,?,?,?)",
        ("The Letter", "Joe Cocker", "Am", 96),
    )
    conn.commit()
    return cur.lastrowid


def test_table_has_expected_columns(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(guitar_tone_profiles)").fetchall()}
    assert cols == {
        "id", "catalog_song_id", "persona", "rationale",
        "hlx_filename", "status", "created_at", "updated_at",
    }


def test_default_status_is_proposed(conn, song_id):
    conn.execute(
        "INSERT INTO guitar_tone_profiles (catalog_song_id, persona, hlx_filename) VALUES (?,?,?)",
        (song_id, "Stevie Ray Vaughan", "The_Letter_Joe_Cocker.hlx"),
    )
    conn.commit()
    row = conn.execute("SELECT status FROM guitar_tone_profiles WHERE catalog_song_id=?", (song_id,)).fetchone()
    assert row["status"] == "proposed"


def test_check_constraint_rejects_invalid_status(conn, song_id):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO guitar_tone_profiles (catalog_song_id, persona, hlx_filename, status) VALUES (?,?,?,?)",
            (song_id, "Stevie Ray Vaughan", "The_Letter_Joe_Cocker.hlx", "bogus_status"),
        )


def test_unique_song_persona_enforced(conn, song_id):
    conn.execute(
        "INSERT INTO guitar_tone_profiles (catalog_song_id, persona, hlx_filename) VALUES (?,?,?)",
        (song_id, "Stevie Ray Vaughan", "The_Letter_Joe_Cocker.hlx"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO guitar_tone_profiles (catalog_song_id, persona, hlx_filename) VALUES (?,?,?)",
            (song_id, "Stevie Ray Vaughan", "Duplicate_Attempt.hlx"),
        )


def test_cascade_delete_removes_profiles(conn, song_id):
    conn.execute(
        "INSERT INTO guitar_tone_profiles (catalog_song_id, persona, hlx_filename) VALUES (?,?,?)",
        (song_id, "Stevie Ray Vaughan", "The_Letter_Joe_Cocker.hlx"),
    )
    conn.commit()
    conn.execute("DELETE FROM catalog_songs WHERE id=?", (song_id,))
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM guitar_tone_profiles WHERE catalog_song_id=?", (song_id,)).fetchone()[0]
    assert remaining == 0
