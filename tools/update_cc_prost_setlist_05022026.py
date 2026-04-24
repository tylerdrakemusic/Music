"""
FR-20260424-cc-prost-setlist-05022026
Update heartmusic.db with the revised CC Prost setlist for 2026-05-02.

Usage:
    HEARTMUSIC_DB_KEY=<key> C:\\G\\python.exe tools/update_cc_prost_setlist_05022026.py

This script is IDEMPOTENT — safe to re-run. It upserts the gig setlist,
replacing any pre-existing data for Copper Creek Prost 2026-05-02.
"""
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.init_db import get_connection

GIG_NAME = "Copper Creek Prost 2026-05-02"
GIG_DATE = "2026-05-02"
VENUE = "Copper Creek Brewery"
BAND = "Copper Creek"

# ---------------------------------------------------------------------------
# Setlist data — 3 sets, 13 songs each
# ---------------------------------------------------------------------------
SETLIST: list[tuple[int, int, str, str]] = [
    # (set_number, position, title, key)
    # SET 1
    (1,  1, "Long Train Runnin",          "Gm"),
    (1,  2, "Too Much Time",              "A"),
    (1,  3, "Im Alright",                "D"),
    (1,  4, "Bobby McGee",               "G"),
    (1,  5, "Rhiannon",                  "Am"),
    (1,  6, "Gold On Ceiling",           "G"),
    (1,  7, "Call Me",                   "B"),
    (1,  8, "Shaded Jade",               "Bm"),
    (1,  9, "Reeling In the Yrs",        "A"),
    (1, 10, "I Will Survive",            "Am"),
    (1, 11, "Love Sneaking Up",          "D"),
    (1, 12, "Boots",                     "E"),
    (1, 13, "I Can't Go 4 That",         "F"),
    # SET 2
    (2,  1, "25 or 6 to 4",              "A"),
    (2,  2, "What You Need",             "F#"),
    (2,  3, "Do It Again",               "Gm"),
    (2,  4, "Baker Street",              "D"),
    (2,  5, "Celebrate",                 "Ab"),
    (2,  6, "Disco Inferno",             "Ab"),
    (2,  7, "Black Magic",               "Dm"),
    (2,  8, "Logical Song",              "C"),
    (2,  9, "Jacky",                     "Gm"),
    (2, 10, "Carnival",                  "F#m"),
    (2, 11, "I Feel the Earth",          "Cm"),
    (2, 12, "Heart of R&R",              "C"),
    (2, 13, "Heavy Chevy",               "C"),
    # SET 3
    (3,  1, "Pick Up the Pieces",        "Fm"),
    (3,  2, "Play That Funky M",         "Em"),
    (3,  3, "On the Dark Side",          "E"),
    (3,  4, "What I Like About U",       "E"),
    (3,  5, "Smooth Operator",           "Dm"),
    (3,  6, "Smooth",                    "Am"),
    (3,  7, "What I Do",                 "Bm"),
    (3,  8, "Stop Draggin My Hrt",       "Em"),
    (3,  9, "The Letter",                "Bbm"),
    (3, 10, "Blue on Black",             "C"),
    (3, 11, "Evil Ways",                 "Gm"),
    (3, 12, "Peg",                       "G"),
    (3, 13, "Roll With Changes",         "C"),
]


def _ensure_catalog_song(cur, title: str, key: str) -> int:
    """INSERT OR IGNORE a catalog_songs row; return its id."""
    cur.execute(
        "INSERT OR IGNORE INTO catalog_songs (title, artist, key_sig) VALUES (?, ?, ?)",
        (title, "Various", key),
    )
    cur.execute(
        "SELECT id FROM catalog_songs WHERE title = ? AND artist = 'Various'",
        (title,),
    )
    rows = cur.fetchall()
    # Return the first match (there may be multiple artists — we take the one we just upserted)
    return rows[0][0]


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # 1. Upsert the setlist header (replace pre-existing CC Prost gig)
    # ------------------------------------------------------------------
    cur.execute(
        "SELECT id FROM setlists WHERE name = ? AND band = ?",
        (GIG_NAME, BAND),
    )
    existing = cur.fetchone()

    if existing:
        setlist_id = existing[0]
        print(f"Found existing setlist id={setlist_id} — replacing all songs.")
        cur.execute("DELETE FROM setlist_songs WHERE setlist_id = ?", (setlist_id,))
        cur.execute(
            "UPDATE setlists SET gig_date=?, venue=?, active=1, notes='Revised 2026-04-24 via FR-20260424-cc-prost-setlist-05022026' WHERE id=?",
            (GIG_DATE, VENUE, setlist_id),
        )
    else:
        cur.execute(
            "INSERT INTO setlists (name, band, gig_date, venue, active, notes) VALUES (?,?,?,?,1,?)",
            (GIG_NAME, BAND, GIG_DATE, VENUE, "Created 2026-04-24 via FR-20260424-cc-prost-setlist-05022026"),
        )
        setlist_id = cur.lastrowid
        print(f"Created new setlist id={setlist_id}.")

    # ------------------------------------------------------------------
    # 2. Insert all 39 songs
    # ------------------------------------------------------------------
    inserted = 0
    for set_num, pos, title, key in SETLIST:
        song_id = _ensure_catalog_song(cur, title, key)
        cur.execute(
            """INSERT INTO setlist_songs
               (setlist_id, catalog_song_id, set_number, position, key_override)
               VALUES (?, ?, ?, ?, ?)""",
            (setlist_id, song_id, set_num, pos, key),
        )
        inserted += 1

    conn.commit()
    conn.close()

    print(f"Done. {inserted} songs written for setlist id={setlist_id} ({GIG_NAME}).")
    assert inserted == 39, f"Expected 39 songs, got {inserted}"
    print("PASS: 39 songs verified.")


if __name__ == "__main__":
    main()
