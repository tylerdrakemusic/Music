"""Database connection utility for ❤Music — encrypted heartmusic.db.

Usage:
    # Connect only
    from utils.init_db import get_connection

    # Initialize schema (idempotent, safe to re-run)
    C:\\G\\python.exe src/utils/init_db.py
"""
import os
from pathlib import Path

import sqlcipher3

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "heartmusic.db"

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS albums (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL DEFAULT 'Tyler James Drake',
    year        INTEGER,
    status      TEXT NOT NULL DEFAULT 'in_progress'
                CHECK(status IN ('in_progress','mastered','released','archived')),
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id      INTEGER REFERENCES albums(id),
    track_number  INTEGER,
    title         TEXT NOT NULL,
    key_signature TEXT,
    tempo_bpm     REAL,
    genre         TEXT,
    status        TEXT NOT NULL DEFAULT 'in_progress'
                  CHECK(status IN ('in_progress','mastered','released','archived')),
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recordings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER NOT NULL REFERENCES tracks(id),
    file_path   TEXT,
    version     TEXT,
    source      TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lyrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER NOT NULL REFERENCES tracks(id),
    body        TEXT,
    version     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalog_index (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER REFERENCES tracks(id),
    file_path   TEXT NOT NULL,
    file_format TEXT,
    catalog_type TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS releases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id            INTEGER REFERENCES albums(id),
    distributor         TEXT,
    release_date        TEXT,
    upc                 TEXT,
    spotify_confirmed   INTEGER DEFAULT 0,
    apple_confirmed     INTEGER DEFAULT 0,
    amazon_confirmed    INTEGER DEFAULT 0,
    youtube_confirmed   INTEGER DEFAULT 0,
    deezer_confirmed    INTEGER DEFAULT 0,
    pandora_confirmed   INTEGER DEFAULT 0,
    iheart_confirmed    INTEGER DEFAULT 0,
    bandcamp_confirmed  INTEGER DEFAULT 0,
    audius_confirmed    INTEGER DEFAULT 0,
    platform_urls       TEXT,
    soundexchange_id    TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS release_signatures (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id            INTEGER REFERENCES recordings(id),
    track_id                INTEGER REFERENCES tracks(id),
    file_path               TEXT,
    file_size_bytes         INTEGER,
    file_format             TEXT,
    md5                     TEXT,
    sha256                  TEXT UNIQUE,
    container               TEXT,
    codec                   TEXT,
    sample_rate_hz          INTEGER,
    channels                INTEGER,
    bits_per_sample         INTEGER,
    bitrate_kbps            REAL,
    duration_sec            REAL,
    entropy_header          REAL,
    entropy_mid             REAL,
    boundary_crossings      INTEGER,
    crossing_rate_pct       REAL,
    byte_freq_top10         TEXT,
    source_platform         TEXT,
    provenance_id           TEXT,
    provenance_url          TEXT,
    created_timestamp       TEXT,
    provenance_comment      TEXT,
    pipeline                TEXT,
    pipeline_notes          TEXT,
    blake2s                 TEXT,
    sha512                  TEXT,
    sha512_224              TEXT,
    sha512_256              TEXT,
    shake_128               TEXT,
    shake_256               TEXT,
    whirlpool               TEXT,
    quantum_salt            TEXT,
    quantum_blake2b         TEXT,
    quantum_sha3_512        TEXT,
    quantum_entropy_bits    INTEGER,
    quantum_source          TEXT,
    quantum_signed_at       TEXT,
    chacha20_poly1305_seal  TEXT,
    aesgcm_seal             TEXT,
    aead_nonce              TEXT,
    aead_aad                TEXT,
    sig_version             TEXT,
    analyzed_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_recordings_track ON recordings(track_id);
CREATE INDEX IF NOT EXISTS idx_lyrics_track ON lyrics(track_id);
CREATE INDEX IF NOT EXISTS idx_catalog_track ON catalog_index(track_id);
CREATE INDEX IF NOT EXISTS idx_sigs_track ON release_signatures(track_id);
CREATE INDEX IF NOT EXISTS idx_sigs_sha256 ON release_signatures(sha256);
"""

_SEED_SQL = """
INSERT OR IGNORE INTO albums (id, title, year, status) VALUES
    (1, 'EP', 2024, 'released'),
    (2, 'Bloom', 2025, 'mastered');

INSERT OR IGNORE INTO tracks (id, album_id, track_number, title, status) VALUES
    (1,  1, 1, 'What I do',       'released'),
    (2,  1, 2, 'Marigold',        'released'),
    (3,  1, 3, 'Get Out',         'released'),
    (4,  2, 1, 'Abbey''s Song',   'mastered'),
    (5,  2, 2, 'Bitten',          'mastered'),
    (6,  2, 3, 'Fly Away',        'mastered'),
    (7,  2, 4, 'Lighthouse',      'mastered'),
    (8,  2, 5, 'Same Thing',      'mastered'),
    (9,  2, 6, 'You Already Know','mastered'),
    (10, 2, 7, 'Is It Real',      'mastered');
"""


def _apply_cipher_pragmas(conn: sqlcipher3.Connection) -> None:
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")


def _try_open_with_key(conn: sqlcipher3.Connection, key: str, *, use_hex: bool) -> bool:
    if use_hex:
        key_hex = key.encode().hex()
        conn.execute(f"PRAGMA key=\"x'{key_hex}'\"")
    else:
        safe_key = key.replace("'", "''")
        conn.execute(f"PRAGMA key='{safe_key}'")

    _apply_cipher_pragmas(conn)

    try:
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True
    except sqlcipher3.DatabaseError:
        return False


def get_connection() -> sqlcipher3.Connection:
    """Return a sqlcipher3 connection to heartmusic.db."""
    key = os.environ.get("HEARTMUSIC_DB_KEY", "")
    if not key:
        raise RuntimeError("HEARTMUSIC_DB_KEY not set")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlcipher3.connect(str(DB_PATH))

    opened = _try_open_with_key(conn, key, use_hex=True)
    if not opened:
        opened = _try_open_with_key(conn, key, use_hex=False)
    if not opened:
        conn.close()
        raise RuntimeError("Failed to decrypt heartmusic.db with HEARTMUSIC_DB_KEY")

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlcipher3.Row
    return conn


def init_db(*, seed: bool = True) -> None:
    """Create all tables and optionally seed with catalog data. Safe to re-run."""
    conn = get_connection()
    conn.executescript(_SCHEMA_SQL)
    if seed:
        conn.executescript(_SEED_SQL)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    seed = "--no-seed" not in sys.argv
    init_db(seed=seed)
    print(f"heartmusic.db initialized at {DB_PATH}")
    if seed:
        print("  Albums and tracks seeded from catalog.")
