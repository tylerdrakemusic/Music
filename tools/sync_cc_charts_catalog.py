r"""
sync_cc_charts_catalog.py — FR-20260531-copper-creek-catalog-sync

Add the 15 green-row songs from coppercreekofficial.com/charts/ that are
not yet in heartmusic.db.  Idempotent — safe to re-run.

Usage:
    C:\G\python.exe f:\❤Music\tools\sync_cc_charts_catalog.py
    C:\G\python.exe f:\❤Music\tools\sync_cc_charts_catalog.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# ---------------------------------------------------------------------------
# Data — 15 active (green-row) songs missing from the catalog
# Source: coppercreekofficial.com/charts/  (scraped 2026-05-31)
# ---------------------------------------------------------------------------
SONGS_TO_ADD: list[dict] = [
    {"title": "Breakdown",            "artist": "Tom Petty",       "key_sig": "Am",  "bpm": 114, "source_file": "Breakdown - Tom Petty and the Heartbreakers.m4a"},
    {"title": "Change The World",     "artist": "Eric Clapton",    "key_sig": "A",   "bpm": 97,  "source_file": "Change the World - Eric Clapton.m4a"},
    {"title": "Josie",                "artist": "Jim Mann",        "key_sig": "E",   "bpm": 122, "source_file": "Josie - Steely Dan.mp3"},
    {"title": "Livin' On A Prayer",   "artist": "Bon Jovi",        "key_sig": "Em",  "bpm": 123, "source_file": "Livin' On a Prayer - Bon Jovi.mp3"},
    {"title": "Love Shack",           "artist": "B-52's",          "key_sig": "C",   "bpm": 134, "source_file": "Love Shack - The B-52's.mp3"},
    {"title": "Natural Woman",        "artist": "Carole King",     "key_sig": "Bb",  "bpm": 111, "source_file": "You Make Me Feel Like a Natural Woman - Carole King.mp3"},
    {"title": "Rocky Mountain Way",   "artist": "Joe Walsh",       "key_sig": "E",   "bpm": 86,  "source_file": "Rocky Mountain Way - Joe Walsh.mp3"},
    {"title": "Separate Ways",        "artist": "Journey",         "key_sig": "Em",  "bpm": 131, "source_file": "Separate Ways - Journey.mp3"},
    {"title": "Sweet Home Alabama",   "artist": "Lynyrd Skynyrd",  "key_sig": "G",   "bpm": 100, "source_file": "Sweet Home Alabama - Lynyrd Skynyrd.mp3"},
    {"title": "Tequila",              "artist": "The Champs",      "key_sig": "F",   "bpm": 90,  "source_file": "Tequila - The Champs.mp3"},
    {"title": "Thrill Is Gone",       "artist": "BB King",         "key_sig": "Bm",  "bpm": 90,  "source_file": "The Thrill Is Gone - B.B. King.mp3"},
    {"title": "Wicked Games",         "artist": "Chris Isaak",     "key_sig": "Bm",  "bpm": 112, "source_file": None},
    {"title": "Wonderful Tonight",    "artist": "Eric Clapton",    "key_sig": "G",   "bpm": 95,  "source_file": "Wonderful Tonight - Eric Clapton.mp3"},
    {"title": "You're So Vain",       "artist": "Carly Simon",     "key_sig": "Am",  "bpm": 106, "source_file": "You're So Vain - Carly Simon.mp3"},
]

BAND_NAME = "Copper Creek"


def _get_copper_creek_band_id(conn: "sqlite3.Connection") -> int:
    row = conn.execute("SELECT id FROM bands WHERE name=?", (BAND_NAME,)).fetchone()
    if row is None:
        raise RuntimeError(
            f"Band '{BAND_NAME}' not found in bands table. "
            "Run catalog/setlists/migrate_bands.py first."
        )
    return row[0]


def sync(conn: "sqlite3.Connection", *, dry_run: bool = False) -> tuple[int, int]:
    """Insert missing songs and link them to Copper Creek.

    Returns:
        (inserted_catalog_rows, linked_arrangement_rows)
    """
    band_id = _get_copper_creek_band_id(conn)
    inserted = 0
    linked = 0

    for song in SONGS_TO_ADD:
        # 1. Upsert catalog_songs
        existing = conn.execute(
            "SELECT id FROM catalog_songs WHERE title=? AND artist=?",
            (song["title"], song["artist"]),
        ).fetchone()

        if existing:
            catalog_id = existing[0]
            # Back-fill source_file if it was added without one
            if song.get("source_file") and not dry_run:
                conn.execute(
                    "UPDATE catalog_songs SET source_file=?, updated_at=datetime('now') WHERE id=? AND source_file IS NULL",
                    (song["source_file"], catalog_id),
                )
        else:
            if not dry_run:
                cur = conn.execute(
                    """INSERT INTO catalog_songs
                           (title, artist, key_sig, bpm, bpm_source, source_file)
                       VALUES (?, ?, ?, ?, 'website', ?)""",
                    (song["title"], song["artist"], song["key_sig"], song["bpm"], song.get("source_file")),
                )
                catalog_id = cur.lastrowid
            else:
                catalog_id = -1
            inserted += 1

        # 2. Link to Copper Creek in band_song_arrangements
        if catalog_id != -1:
            already_linked = conn.execute(
                """SELECT id FROM band_song_arrangements
                   WHERE band_id=? AND catalog_song_id=?""",
                (band_id, catalog_id),
            ).fetchone()

            if not already_linked:
                if not dry_run:
                    conn.execute(
                        """INSERT INTO band_song_arrangements
                               (band_id, catalog_song_id, default_key, default_bpm)
                           VALUES (?, ?, ?, ?)""",
                        (band_id, catalog_id, song["key_sig"], song["bpm"]),
                    )
                linked += 1

    if not dry_run:
        conn.commit()

    return inserted, linked


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Copper Creek charts catalog.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted without writing.")
    args = parser.parse_args()

    from utils.init_db import get_connection
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=ON")

    inserted, linked = sync(conn, dry_run=args.dry_run)
    prefix = "[DRY RUN] " if args.dry_run else ""

    print(f"{prefix}catalog_songs rows inserted : {inserted}")
    print(f"{prefix}band_song_arrangements linked: {linked}")

    if inserted == 0 and linked == 0:
        print("Already in sync — nothing to do.")
    else:
        print("Done.")

    conn.close()


if __name__ == "__main__":
    main()
