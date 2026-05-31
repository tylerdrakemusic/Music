"""DB migration: create sheet_music table in heartmusic.db.

Idempotent — safe to run multiple times.

Usage::

    C:\\G\\python.exe src/scripts/migrate_sheet_music_table.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the ❤Music root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.init_db import get_connection  # noqa: E402

_MIGRATION_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sheet_music (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL CHECK(source IN ('local','gdrive')),
    name                TEXT    NOT NULL,
    file_ext            TEXT,
    category            TEXT,
    artist              TEXT,
    title               TEXT,
    key_descriptor      TEXT,
    local_path          TEXT,
    gdrive_file_id      TEXT    UNIQUE,
    gdrive_folder_path  TEXT,
    file_size_bytes     INTEGER,
    gdrive_modified_at  TEXT,
    ingested_at         TEXT    DEFAULT (datetime('now')),
    deleted_at          TEXT,
    catalog_index_id    INTEGER REFERENCES catalog_index(id)
);

CREATE INDEX IF NOT EXISTS idx_sheet_music_source
    ON sheet_music(source);

CREATE INDEX IF NOT EXISTS idx_sheet_music_gdrive_file_id
    ON sheet_music(gdrive_file_id);
"""


def migrate() -> None:
    """Create the sheet_music table (idempotent)."""
    conn = get_connection()
    conn.executescript(_MIGRATION_SQL)
    conn.commit()
    row_count = conn.execute("SELECT COUNT(*) FROM sheet_music").fetchone()[0]
    print(f"[migrate_sheet_music_table] sheet_music table ready. Row count: {row_count}")
    conn.close()


if __name__ == "__main__":
    migrate()
