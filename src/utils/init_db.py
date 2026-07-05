"""Database connection utility for ❤Music — encrypted heartmusic.db.

Usage:
    # Connect only
    from utils.init_db import get_connection

    # Initialize schema (idempotent, safe to re-run)
    C:\\G\\python.exe src/utils/init_db.py
"""
import os
import sys
from pathlib import Path

# sqlcipher3 is imported lazily inside get_connection() so that test suites
# running on environments without the native SQLCipher library (e.g. CI) can
# still import this module and monkeypatch get_connection without crashing.

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "src" / "data" / "heartmusic.db"
LEGACY_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "legacy_heartmusic.db"
ALT_DB_PATH = LEGACY_DB_PATH
CANONICAL_DB_PATH = DEFAULT_DB_PATH
_ENV_DB_PATH = os.environ.get("HEARTMUSIC_DB_PATH", "").strip()
if _ENV_DB_PATH:
    DB_PATH = Path(_ENV_DB_PATH)
else:
    DB_PATH = DEFAULT_DB_PATH if DEFAULT_DB_PATH.exists() else LEGACY_DB_PATH

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

-- ── Catalog songs (covers, originals, any song the band performs) ──────────
CREATE TABLE IF NOT EXISTS catalog_songs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    artist        TEXT NOT NULL,
    key_sig       TEXT,
    bpm           INTEGER,
    bpm_source    TEXT,          -- e.g. 'librosa', 'manual', 'unknown'
    genre         TEXT,
    tags          TEXT,          -- JSON array e.g. '["rock","cover"]'
    notes         TEXT,
    source_file   TEXT,          -- path to the reference audio in G:\Muzic
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Setlists ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS setlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,          -- e.g. 'Copper Creek Prost 5/2/26'
    band        TEXT NOT NULL DEFAULT 'Copper Creek',
    gig_date    TEXT,                   -- ISO date YYYY-MM-DD
    venue       TEXT,
    active      INTEGER NOT NULL DEFAULT 0,  -- 1 = current active gigging setlist
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Setlist songs (ordered junction) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS setlist_songs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    setlist_id      INTEGER NOT NULL REFERENCES setlists(id) ON DELETE CASCADE,
    catalog_song_id INTEGER NOT NULL REFERENCES catalog_songs(id),
    set_number      INTEGER NOT NULL,   -- 1, 2, 3...
    position        INTEGER NOT NULL,   -- position within the set
    key_override    TEXT,               -- band's key if different from catalog
    bpm_override    INTEGER,
    notes           TEXT,
    UNIQUE(setlist_id, set_number, position)
);

CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_recordings_track ON recordings(track_id);
CREATE INDEX IF NOT EXISTS idx_lyrics_track ON lyrics(track_id);
CREATE INDEX IF NOT EXISTS idx_catalog_track ON catalog_index(track_id);
CREATE INDEX IF NOT EXISTS idx_sigs_track ON release_signatures(track_id);
CREATE INDEX IF NOT EXISTS idx_sigs_sha256 ON release_signatures(sha256);
CREATE INDEX IF NOT EXISTS idx_catalog_songs_artist ON catalog_songs(artist);
CREATE INDEX IF NOT EXISTS idx_setlist_songs_setlist ON setlist_songs(setlist_id);
CREATE INDEX IF NOT EXISTS idx_setlist_songs_catalog ON setlist_songs(catalog_song_id);

-- ── Bands ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bands (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    genre      TEXT,
    active     INTEGER NOT NULL DEFAULT 1,
    notes      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Per-band arrangement defaults for a song ─────────────────────────────
CREATE TABLE IF NOT EXISTS band_song_arrangements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    band_id         INTEGER NOT NULL REFERENCES bands(id) ON DELETE CASCADE,
    catalog_song_id INTEGER NOT NULL REFERENCES catalog_songs(id) ON DELETE CASCADE,
    default_key     TEXT,
    default_bpm     INTEGER,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(band_id, catalog_song_id)
);

CREATE INDEX IF NOT EXISTS idx_arrangements_band ON band_song_arrangements(band_id);
CREATE INDEX IF NOT EXISTS idx_arrangements_song ON band_song_arrangements(catalog_song_id);

-- ── Setlist title aliases ─────────────────────────────────────────────────
-- Maps shorthand / abbreviated titles used in setlist imports → canonical
-- catalog_song_id. Allows sloppy input ("Bobby McGee", "Boots") to resolve
-- without manual remapping every time.
CREATE TABLE IF NOT EXISTS catalog_song_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alias           TEXT NOT NULL UNIQUE,   -- normalized lower-case alias
    catalog_song_id INTEGER NOT NULL REFERENCES catalog_songs(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_aliases_song ON catalog_song_aliases(catalog_song_id);

-- Guitar Trainer: exercise cards (FR-20260425-guitar-trainer-db-migration)
CREATE TABLE IF NOT EXISTS guitar_exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL DEFAULT '',
    song_path   TEXT NOT NULL DEFAULT '',
    segments    TEXT NOT NULL DEFAULT '[]',  -- JSON array blob
    gradient    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Guitar Trainer: practice log (append-only)
CREATE TABLE IF NOT EXISTS guitar_training_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id      INTEGER REFERENCES guitar_exercises(id) ON DELETE SET NULL,
    song_path        TEXT NOT NULL DEFAULT '',
    seg_start        TEXT NOT NULL DEFAULT '',
    seg_end          TEXT NOT NULL DEFAULT '',
    repetition       INTEGER NOT NULL DEFAULT 1,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    key              TEXT,
    position         INTEGER,
    exercise_name    TEXT,
    logged_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Scale & Arpeggio practice log (FR-20260517-guitar-trainer-scale-exercises)
CREATE TABLE IF NOT EXISTS scale_practice_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    key              TEXT NOT NULL DEFAULT 'C',   -- musical key (FR-20260522-guitar-trainer-multi-key)
    mode             TEXT NOT NULL DEFAULT 'Ionian',
    scale            TEXT NOT NULL DEFAULT 'C_major',
    position         INTEGER NOT NULL DEFAULT 1,
    bpm              INTEGER NOT NULL DEFAULT 60,
    reps             INTEGER NOT NULL DEFAULT 1,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    logged_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Gig Inventory ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gig_inventory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item       TEXT NOT NULL,
    category   TEXT DEFAULT 'General',
    sort_order INTEGER DEFAULT 0
);

-- ── Artist Links (FR-20260515-artist-links-pill-music-dashboard) ─────────────
CREATE TABLE IF NOT EXISTS artist_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL CHECK(category IN ('email','social','payment','distribution')),
    platform    TEXT NOT NULL,
    label       TEXT NOT NULL,
    url         TEXT,
    embed_html  TEXT,
    song_title  TEXT,
    status      TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed','pending','broken')),
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_artist_links_category ON artist_links(category);
CREATE INDEX IF NOT EXISTS idx_artist_links_platform ON artist_links(platform);

-- ── Guitar Scale Templates (FR-20260524-scale-data-sqlite-migration) ──────
-- Stores the 7 CAGED+ shape templates as compact JSON offset arrays.
-- note_offsets: JSON [[string_num, fret_delta_from_root_fret], ...]
-- root_string: the string (1-6) on which root_fret is anchored for computation
CREATE TABLE IF NOT EXISTS guitar_scale_templates (
    shape_name   TEXT NOT NULL PRIMARY KEY,
    root_string  INTEGER NOT NULL,
    note_offsets TEXT NOT NULL
);

-- ── Guitar Scale Positions (FR-20260524-scale-data-sqlite-migration) ───────
-- Per-key position metadata referencing a shape template.
-- root_fret: fret on the template's root_string used to compute all note frets.
CREATE TABLE IF NOT EXISTS guitar_scale_positions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name          TEXT    NOT NULL,
    position_order    INTEGER NOT NULL,
    shape_name        TEXT    NOT NULL REFERENCES guitar_scale_templates(shape_name),
    label             TEXT    NOT NULL,
    root_string_name  TEXT    NOT NULL,
    root_fret         INTEGER NOT NULL,
    instructor_phrase TEXT    NOT NULL,
    UNIQUE (key_name, position_order)
);

-- ── Duplicate audio file groups (FR-20260527-catalog-dedup-scan) ──────────
-- One row per (canonical, duplicate) sig pair sharing the same sha256.
CREATE TABLE IF NOT EXISTS duplicate_groups (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256                     TEXT NOT NULL,
    canonical_sig_id           INTEGER REFERENCES release_signatures(id),
    duplicate_sig_id           INTEGER REFERENCES release_signatures(id),
    provenance_score_canonical INTEGER,
    provenance_score_duplicate INTEGER,
    detected_at                TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(sha256, duplicate_sig_id)
);

CREATE INDEX IF NOT EXISTS idx_dup_groups_sha256 ON duplicate_groups(sha256);

-- ── Guitar tone profiles (FR-20260705-guitar-tech-persona-agent) ──────────
-- Persona-matched HX Stomp tone recipes generated for catalog songs.
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

INSERT OR IGNORE INTO gig_inventory (id, item, category, sort_order) VALUES
    (1,  'Guitar',           'Guitar',        1),
    (2,  'Guitar Stand',     'Guitar',        2),
    (3,  'Amp',              'Amplification', 3),
    (4,  'Amp stand',        'Amplification', 4),
    (5,  'Trombone',         'Horn',          5),
    (6,  'Trombone stand',   'Horn',          6),
    (7,  'iPad',             'Accessories',   7),
    (8,  'Gig Bag',          'Accessories',   8),
    (10, 'Extension Chord',  'Accessories',   9),
    (11, 'Cooling Fan',      'Accessories',   11),
    (12, 'Wireless 1/4',     'Accessories',   12),
    (13, 'Pedal Board',      'Accessories',   10);
"""


def _apply_cipher_pragmas(conn) -> None:
    conn.execute("PRAGMA cipher_page_size=4096")
    conn.execute("PRAGMA kdf_iter=256000")
    conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")

_LEGACY_INSPECTION_TABLES = (
    "studio_equipment",
    "guitar_exercises",
    "guitar_training_log",
    "vault_lines",
    "phonetic_groups",
    "sheet_music",
)
_LEGACY_WARNING_PRINTED = False


def _try_open_with_key(conn, key: str, *, use_hex: bool) -> bool:
    if use_hex:
        key_hex = key.encode().hex()
        conn.execute(f"PRAGMA key=\"x'{key_hex}'\"")  # nosec B608 – PRAGMA can't be parameterized; key_hex is hex-encoded
    else:
        safe_key = key.replace("'", "''")
        conn.execute(f"PRAGMA key='{safe_key}'")  # nosec B608 – PRAGMA can't be parameterized; key is quote-escaped

    _apply_cipher_pragmas(conn)

    try:
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True
    except Exception:
        return False


def _open_with_any_key(path: Path, key: str):
    import sqlcipher3

    for use_hex in (False, True):
        conn = sqlcipher3.connect(str(path))
        if _try_open_with_key(conn, key, use_hex=use_hex):
            return conn, use_hex
        conn.close()
    raise RuntimeError(f"Failed to decrypt heartmusic.db at {path} with HEARTMUSIC_DB_KEY.")


def _table_has_rows(conn, table: str) -> bool:
    try:
        return bool(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone())
    except Exception:
        return False


def _warn_legacy_populated(conn) -> None:
    global _LEGACY_WARNING_PRINTED
    if _LEGACY_WARNING_PRINTED:
        return
    if not LEGACY_DB_PATH.exists() or _ENV_DB_PATH:
        return

    try:
        legacy_conn, _ = _open_with_any_key(LEGACY_DB_PATH, os.environ.get("HEARTMUSIC_DB_KEY", ""))
    except Exception:
        return

    mismatch = []
    try:
        for table in _LEGACY_INSPECTION_TABLES:
            if not _table_has_rows(conn, table) and _table_has_rows(legacy_conn, table):
                mismatch.append(table)
    finally:
        legacy_conn.close()

    if mismatch:
        print(
            f"WARNING: Canonical heartmusic.db at {CANONICAL_DB_PATH} appears empty for {', '.join(mismatch)} while legacy heartmusic.db at {LEGACY_DB_PATH} contains data. "
            "Run tools/reconcile_heartmusic_db.py --apply to merge legacy data into the canonical DB, or set HEARTMUSIC_DB_PATH to the legacy DB if that is intentionally the active dataset.",
            file=sys.stderr,
        )
        _LEGACY_WARNING_PRINTED = True


def get_connection(*, create_if_missing: bool = False):
    """Return a sqlcipher3 connection to heartmusic.db."""
    import sqlcipher3  # noqa: PLC0415 — lazy import; native lib not available on CI
    key = os.environ.get("HEARTMUSIC_DB_KEY", "")
    if not key:
        raise RuntimeError(
            "HEARTMUSIC_DB_KEY not set. "
            "Set HEARTMUSIC_DB_KEY in User or Machine environment before starting the Guitar Trainer or Studio Panel."
        )

    if not DB_PATH.exists() and not create_if_missing:
        raise RuntimeError(
            f"heartmusic.db not found at {DB_PATH}. "
            "Run src/utils/init_db.py to create it or set HEARTMUSIC_DB_PATH to an existing DB."
        )

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlcipher3.connect(str(DB_PATH))

    opened = _try_open_with_key(conn, key, use_hex=False)
    if not opened:
        opened = _try_open_with_key(conn, key, use_hex=True)
    if not opened:
        conn.close()
        raise RuntimeError(
            "Failed to decrypt heartmusic.db with HEARTMUSIC_DB_KEY. "
            "Verify the key value and ensure the same key is used by all Music services."
        )

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    import sqlcipher3 as _sc3  # noqa: PLC0415
    conn.row_factory = _sc3.Row

    if DB_PATH == CANONICAL_DB_PATH and LEGACY_DB_PATH.exists() and not _ENV_DB_PATH:
        try:
            _warn_legacy_populated(conn)
        except Exception:
            pass

    return conn


def init_db(*, seed: bool = True) -> None:
    """Create all tables and optionally seed with catalog data. Safe to re-run."""
    conn = get_connection(create_if_missing=True)
    conn.executescript(_SCHEMA_SQL)
    # FR-20260522: add 'key' column to scale_practice_log for existing DBs
    try:
        conn.execute(
            "ALTER TABLE scale_practice_log ADD COLUMN key TEXT NOT NULL DEFAULT 'C'"
        )
        conn.commit()
    except Exception:  # nosec B110
        pass  # column already exists
    # FR-20260525: add duration/context columns to guitar_training_log
    for _col_sql in [
        "ALTER TABLE guitar_training_log ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE guitar_training_log ADD COLUMN key TEXT",
        "ALTER TABLE guitar_training_log ADD COLUMN position INTEGER",
        "ALTER TABLE guitar_training_log ADD COLUMN exercise_name TEXT",
    ]:
        try:
            conn.execute(_col_sql)
            conn.commit()
        except Exception:  # nosec B110
            pass  # column already exists
    # FR-20260613: add mode to scale_practice_log for mode selector support
    try:
        conn.execute(
            "ALTER TABLE scale_practice_log ADD COLUMN mode TEXT NOT NULL DEFAULT 'Ionian'"
        )
        conn.commit()
    except Exception:  # nosec B110
        pass  # column already exists
    # FR-20260525: add duration_minutes to scale_practice_log
    try:
        conn.execute(
            "ALTER TABLE scale_practice_log ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except Exception:  # nosec B110
        pass  # column already exists
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
