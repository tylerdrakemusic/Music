"""
Seed heartmusic.db with catalog_songs + setlist from setlist_with_bpm.json.
Idempotent — safe to re-run; uses INSERT OR IGNORE on unique title+artist pairs.

Usage:
    C:\G\python.exe f:\❤Music\catalog\setlists\seed_catalog.py

To update BPM after adding new audio to G:\Muzic:
    1. Run detect_bpm.py   (regenerates setlist_with_bpm.json)
    2. Run this script     (upserts changed BPM values)
"""
import json
import os
import sys
from pathlib import Path

# Allow importing from ❤Music src
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from utils.init_db import get_connection  # noqa: E402

JSON_PATH = Path(__file__).parent / "setlist_with_bpm.json"

SETLIST_NAME = "Copper Creek Prost 5/2/26"
SETLIST_GIG_DATE = "2026-05-02"
SETLIST_VENUE = "Prost"
BAND = "Copper Creek"


def get_or_create_band(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM bands WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO bands (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def main() -> None:
    songs = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=ON")

    band_id = get_or_create_band(conn, BAND)

    # ── 1. Upsert catalog_songs ───────────────────────────────────────────────
    for s in songs:
        bpm_source = "librosa" if s["bpm"] is not None else "unknown"
        existing = conn.execute(
            "SELECT id FROM catalog_songs WHERE title=? AND artist=?",
            (s["title"], s["artist"]),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE catalog_songs
                   SET key_sig=?, bpm=?, bpm_source=?, source_file=?, updated_at=datetime('now')
                   WHERE id=?""",
                (s["key"], s["bpm"], bpm_source, s["bpm_source_file"], existing[0]),
            )
            catalog_id = existing[0]
        else:
            cur = conn.execute(
                """INSERT INTO catalog_songs (title, artist, key_sig, bpm, bpm_source, source_file)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (s["title"], s["artist"], s["key"], s["bpm"], bpm_source, s["bpm_source_file"]),
            )
            catalog_id = cur.lastrowid

        s["_catalog_id"] = catalog_id

        # Upsert band arrangement defaults
        conn.execute(
            """INSERT INTO band_song_arrangements (band_id, catalog_song_id, default_key, default_bpm)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(band_id, catalog_song_id) DO UPDATE
               SET default_key=excluded.default_key, default_bpm=excluded.default_bpm""",
            (band_id, catalog_id, s["key"], s["bpm"]),
        )

    # ── 2. Ensure setlist row exists ─────────────────────────────────────────
    row = conn.execute(
        "SELECT id FROM setlists WHERE name=? AND band_id=?", (SETLIST_NAME, band_id)
    ).fetchone()

    if row:
        setlist_id = row[0]
        conn.execute("UPDATE setlists SET active=0 WHERE band_id=?", (band_id,))
        conn.execute("UPDATE setlists SET active=1 WHERE id=?", (setlist_id,))
    else:
        conn.execute("UPDATE setlists SET active=0 WHERE band_id=?", (band_id,))
        cur = conn.execute(
            """INSERT INTO setlists (name, band_id, band, gig_date, venue, active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (SETLIST_NAME, band_id, BAND, SETLIST_GIG_DATE, SETLIST_VENUE),
        )
        setlist_id = cur.lastrowid

    # ── 3. Upsert setlist_songs ──────────────────────────────────────────────
    for s in songs:
        conn.execute(
            """INSERT INTO setlist_songs (setlist_id, catalog_song_id, set_number, position)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(setlist_id, set_number, position) DO UPDATE
               SET catalog_song_id=excluded.catalog_song_id""",
            (setlist_id, s["_catalog_id"], s["set"], s["order"]),
        )

    conn.commit()
    conn.close()

    total = len(songs)
    with_bpm = sum(1 for s in songs if s["bpm"] is not None)
    print(f"Seeded {total} catalog songs ({with_bpm} with BPM).")
    print(f"Setlist '{SETLIST_NAME}' id={setlist_id} marked active.")


if __name__ == "__main__":
    main()
