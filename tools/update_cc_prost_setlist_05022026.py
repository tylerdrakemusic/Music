"""
FR-20260424-cc-prost-setlist-05022026
Update heartmusic.db with the FINAL CC Prost setlist for 2026-05-02.
Source of truth: F:\\❤Music\\catalog\\setlists\\CC Prost 05022026 (1).xlsx (sheet: CC Prost 050226)
Confirmed by Tyler 2026-04-24.

Usage:
    C:\\G\\python.exe tools/update_cc_prost_setlist_05022026.py

This script performs a FULL WIPE-AND-REPLACE of any prior CC Prost 2026-05-02 setlist data.
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
# Setlist data — 3 sets, 12 songs each + 1 throw-in
# Source: CC Prost 05022026 (1).xlsx, sheet "CC Prost 050226", confirmed 2026-04-24
# ---------------------------------------------------------------------------
SETLIST: list[tuple[int, int, str, str]] = [
    # (set_number, position, title, key)
    # SET 1
    (1,  1, "Long Train Runnin",          "Gm"),
    (1,  2, "I'm Alright",               "D"),
    (1,  3, "Bobby McGee",               "G"),
    (1,  4, "Rhiannon",                  "Am"),
    (1,  5, "Talk Me Into It",           "B"),
    (1,  6, "Reeling In the Yrs",        "A"),
    (1,  7, "Shaded Jade",               "Bm"),
    (1,  8, "I Will Survive",            "Am"),
    (1,  9, "Play That Funky M",         "Em"),
    (1, 10, "Love Sneaking Up",          "D"),
    (1, 11, "Evil Ways",                 "Gm"),
    (1, 12, "I Can't Go 4 That",         "F"),
    # SET 2
    (2,  1, "Too Much Time",             "A"),
    (2,  2, "25 or 6 to 4",              "A"),
    (2,  3, "Do It Again",               "Gm"),
    (2,  4, "Baker Street",              "D"),
    (2,  5, "Black Magic",               "Dm"),
    (2,  6, "Logical Song",              "C"),
    (2,  7, "Jacky",                     "Gm"),
    (2,  8, "Carnival",                  "F#m"),
    (2,  9, "I Feel the Earth",          "Cm"),
    (2, 10, "Disco Inferno",             "Ab"),
    (2, 11, "Heart of R&R",              "C"),
    (2, 12, "Heavy Chevy",               "C"),
    # SET 3
    (3,  1, "Call Me",                   "B"),
    (3,  2, "On the Dark Side",          "E"),
    (3,  3, "What I Like About U",       "E"),
    (3,  4, "Boots",                     "E"),
    (3,  5, "Blue on Black",             "C"),
    (3,  6, "Smooth",                    "Am"),
    (3,  7, "Pick Up the Pieces",        "Fm"),
    (3,  8, "Stop Draggin My Hrt",       "Em"),
    (3,  9, "What I Do",                 "Bm"),
    (3, 10, "Smooth Operator",           "Dm"),
    (3, 11, "Peg",                       "G"),
    (3, 12, "Roll With Changes",         "C"),
]

# Throw-in (not in a numbered set slot — tracked separately in notes)
THROW_IN = ("Celebrate", "Ab")

EXPECTED_SONG_COUNT = 36


def _normalize(s: str) -> str:
    """Normalize title for fuzzy matching."""
    import unicodedata, re
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _ensure_catalog_song(cur, title: str, key: str, band_id: int = 1) -> int:
    """Look up canonical catalog_song for this band; fall back to orphan insert.

    Lookup priority:
    1. Exact title match in band_song_arrangements (canonical, has real artist/BPM)
    2. Normalized fuzzy title match in BSA
    3. Alias table lookup (catalog_song_aliases)
    4. INSERT as orphan with artist='⚠ NOT IN CATALOG' so the UI can warn Tyler
    """
    # 1. Exact match in BSA
    cur.execute(
        """SELECT cs.id FROM catalog_songs cs
           JOIN band_song_arrangements bsa ON bsa.catalog_song_id = cs.id AND bsa.band_id = ?
           WHERE cs.title = ? LIMIT 1""",
        (band_id, title),
    )
    row = cur.fetchone()
    if row:
        return dict(row)["id"]

    # 2. Fuzzy normalized match in BSA
    norm_title = _normalize(title)
    cur.execute(
        """SELECT cs.id, cs.title FROM catalog_songs cs
           JOIN band_song_arrangements bsa ON bsa.catalog_song_id = cs.id AND bsa.band_id = ?""",
        (band_id,),
    )
    for r in cur.fetchall():
        if _normalize(dict(r)["title"]) == norm_title:
            return dict(r)["id"]

    # 3. Alias table lookup
    cur.execute(
        "SELECT catalog_song_id FROM catalog_song_aliases WHERE alias = ? LIMIT 1",
        (norm_title,),
    )
    alias_row = cur.fetchone()
    if alias_row:
        return dict(alias_row)["catalog_song_id"]

    # 4. Not in catalog — insert orphan flagged for Tyler
    cur.execute(
        "INSERT OR IGNORE INTO catalog_songs (title, artist, key_sig) VALUES (?, ?, ?)",
        (title, "⚠ NOT IN CATALOG", key),
    )
    cur.execute(
        "SELECT id FROM catalog_songs WHERE title = ? AND artist = '⚠ NOT IN CATALOG'",
        (title,),
    )
    return cur.fetchone()[0]


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
        print(f"Found existing setlist id={setlist_id} — wiping and replacing all songs.")
        cur.execute("DELETE FROM setlist_songs WHERE setlist_id = ?", (setlist_id,))
        cur.execute(
            "UPDATE setlists SET gig_date=?, venue=?, active=1, notes=? WHERE id=?",
            (GIG_DATE, VENUE,
             f"FINAL 2026-04-24 — 36 songs (12/set) + throw-in: {THROW_IN[0]} ({THROW_IN[1]}). Source: CC Prost 05022026 (1).xlsx",
             setlist_id),
        )
    else:
        cur.execute(
            "INSERT INTO setlists (name, band, gig_date, venue, active, notes) VALUES (?,?,?,?,1,?)",
            (GIG_NAME, BAND, GIG_DATE, VENUE,
             f"FINAL 2026-04-24 — 36 songs (12/set) + throw-in: {THROW_IN[0]} ({THROW_IN[1]}). Source: CC Prost 05022026 (1).xlsx"),
        )
        setlist_id = cur.lastrowid
        print(f"Created new setlist id={setlist_id}.")

    # ------------------------------------------------------------------
    # 2. Insert all 39 songs
    # ------------------------------------------------------------------
    inserted = 0
    for set_num, pos, title, key in SETLIST:
        song_id = _ensure_catalog_song(cur, title, key, band_id=band_id)
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
    print(f"Throw-in: {THROW_IN[0]} ({THROW_IN[1]}) — recorded in setlist notes.")
    assert inserted == EXPECTED_SONG_COUNT, f"Expected {EXPECTED_SONG_COUNT} songs, got {inserted}"
    print(f"PASS: {EXPECTED_SONG_COUNT} songs verified.")


if __name__ == "__main__":
    main()
