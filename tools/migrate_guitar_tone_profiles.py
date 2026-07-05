"""One-time migration: introduce the guitar_tone_profiles table
(FR-20260705-guitar-tech-persona-agent).

Safe to re-run (CREATE TABLE IF NOT EXISTS).

Usage:
    C:\\G\\python.exe f:\\❤Music\\tools\\migrate_guitar_tone_profiles.py
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_ROOT / "src"))
import utils.init_db as _init_db_module  # noqa: E402

_init_db_module.use_worktree_aware_db_path(_ROOT)

from utils.init_db import get_connection  # noqa: E402


def migrate(conn) -> None:
    """Create guitar_tone_profiles (idempotent via CREATE TABLE IF NOT EXISTS)."""
    conn.execute("""
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
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_guitar_tone_profiles_song "
        "ON guitar_tone_profiles(catalog_song_id)"
    )
    conn.commit()
    print("guitar_tone_profiles migration applied.")


def main() -> None:
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    conn.close()


if __name__ == "__main__":
    main()
