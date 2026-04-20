"""
❤Music — Add release_signatures table to heartmusic.db

Usage:
    C:\G\python.exe tools/migrate_add_release_signatures.py

Creates the release_signatures table for storing binary analysis
of released audio files — hashes, entropy, codec details, byte
frequency distributions, and Suno provenance metadata.

FK → recordings(id) — each signature row maps to one recording file.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT.parent.parent / ".env")

from utils.init_db import get_connection


DDL = """
CREATE TABLE IF NOT EXISTS release_signatures (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id        INTEGER REFERENCES recordings(id),
    track_id            INTEGER REFERENCES tracks(id),

    -- File identity
    file_path           TEXT NOT NULL,
    file_size_bytes     INTEGER NOT NULL,
    file_format         TEXT NOT NULL,          -- 'wav' | 'mp3' | 'flac' | 'aiff'
    md5                 TEXT NOT NULL,
    sha256              TEXT NOT NULL,

    -- Codec / container
    container           TEXT,                   -- 'RIFF/WAVE' | 'MPEG' | etc
    codec               TEXT,                   -- 'PCM' | 'MPEG1-LayerIII' | 'FLAC'
    sample_rate_hz      INTEGER,
    channels            INTEGER,
    bits_per_sample     INTEGER,                -- NULL for lossy
    bitrate_kbps        REAL,                   -- average for VBR
    duration_sec        REAL,

    -- Entropy
    entropy_header      REAL,                   -- first 64 KB
    entropy_mid         REAL,                   -- middle 64 KB
    boundary_crossings  INTEGER,                -- 0x80 crossings in first 64 KB
    crossing_rate_pct   REAL,

    -- Byte frequency (JSON: top 10 [{byte, count, pct}])
    byte_freq_top10     TEXT,

    -- Provenance (Suno / Pro Tools / etc)
    source_platform     TEXT,                   -- 'suno' | 'pro_tools' | 'manual'
    provenance_id       TEXT,                   -- Suno generation UUID, PT session ID
    provenance_url      TEXT,                   -- WOAS or embedded URL
    created_timestamp   TEXT,                   -- embedded creation timestamp
    provenance_comment  TEXT,                   -- ICMT or ID3 comment

    -- Pipeline
    pipeline            TEXT,                   -- 'pro_tools→suno' | 'suno_direct' | etc
    pipeline_notes      TEXT,

    -- Metadata
    analyzed_at         TEXT DEFAULT (datetime('now')),
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_release_sig_recording
    ON release_signatures(recording_id);
CREATE INDEX IF NOT EXISTS idx_release_sig_track
    ON release_signatures(track_id);
CREATE INDEX IF NOT EXISTS idx_release_sig_sha256
    ON release_signatures(sha256);
"""


def migrate() -> None:
    conn = get_connection()
    try:
        # Check if table already exists
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='release_signatures'"
        ).fetchone()
        if existing:
            print("release_signatures table already exists — skipping DDL.")
        else:
            conn.executescript(DDL)
            conn.commit()
            print("Created release_signatures table + indexes.")

        # Verify
        cols = conn.execute("PRAGMA table_info(release_signatures)").fetchall()
        print(f"Columns ({len(cols)}):")
        for c in cols:
            print(f"  {c[1]:25s} {c[2]}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
