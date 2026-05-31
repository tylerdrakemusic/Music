"""
One-time migration: introduce bands + band_song_arrangements tables,
seed Copper Creek from existing data, add mock band "The Groove Unit" for UI testing.

Safe to re-run (all inserts are idempotent).

Usage:
    C:\G\python.exe f:\❤Music\catalog\setlists\migrate_bands.py [--teardown-mock]

Flags:
    --teardown-mock   Remove The Groove Unit and its data only
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from utils.init_db import get_connection  # noqa: E402


# ── Shared songs The Groove Unit plays in different keys ─────────────────────
# Format: (catalog title, catalog artist, groove_key, groove_bpm)
GROOVE_UNIT_SONGS = [
    ("Superstition",          "Stevie Wonder",   "Em",  100),
    ("Play That Funky Music", "Wild Cherry",     "Dm",   98),
    ("Celebrate",             "Kool & the Gang", "Bb",  122),
    ("Hot Stuff",             "Donna Summer",    "Gm",  112),
    ("Dreams",                "Fleetwood Mac",   "F",    88),
]

GROOVE_SETLIST = {
    "name":     "The Groove Unit — The Tap Room 5/10/26",
    "gig_date": "2026-05-10",
    "venue":    "The Tap Room",
    "songs": [
        # (title, artist, set, position, key_override)
        ("Dreams",                "Fleetwood Mac",   1, 1, None),
        ("Superstition",          "Stevie Wonder",   1, 2, None),
        ("Play That Funky Music", "Wild Cherry",     1, 3, None),
        ("Hot Stuff",             "Donna Summer",    2, 1, None),
        ("Celebrate",             "Kool & the Gang", 2, 2, None),
    ],
}


def migrate(conn) -> None:
    """Apply schema additions (idempotent via CREATE TABLE IF NOT EXISTS + ALTER OR IGNORE)."""
    # bands table — already in init_db.py schema, but run here for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bands (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            genre      TEXT,
            active     INTEGER NOT NULL DEFAULT 1,
            notes      TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS band_song_arrangements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            band_id         INTEGER NOT NULL REFERENCES bands(id) ON DELETE CASCADE,
            catalog_song_id INTEGER NOT NULL REFERENCES catalog_songs(id) ON DELETE CASCADE,
            default_key     TEXT,
            default_bpm     INTEGER,
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(band_id, catalog_song_id)
        )
    """)
    # Add band_id FK column to setlists if not already there
    cols = [r[1] for r in conn.execute("PRAGMA table_info(setlists)").fetchall()]
    if "band_id" not in cols:
        conn.execute("ALTER TABLE setlists ADD COLUMN band_id INTEGER REFERENCES bands(id)")
    conn.commit()
    print("Schema migration applied.")


def seed_copper_creek(conn) -> int:
    """Ensure Copper Creek band row exists; backfill setlists.band_id."""
    conn.execute(
        "INSERT OR IGNORE INTO bands (name, genre, notes) VALUES (?, ?, ?)",
        ("Copper Creek", "Rock / Pop / Country", "Tyler's primary band"),
    )
    band_id = conn.execute("SELECT id FROM bands WHERE name='Copper Creek'").fetchone()[0]

    # Backfill all existing Copper Creek setlists
    conn.execute(
        "UPDATE setlists SET band_id=? WHERE (band='Copper Creek' OR band IS NULL) AND band_id IS NULL",
        (band_id,),
    )

    # Seed arrangements from existing catalog songs (use catalog key/bpm as defaults)
    songs = conn.execute(
        """SELECT cs.id, cs.key_sig, cs.bpm
           FROM catalog_songs cs
           JOIN setlist_songs ss ON ss.catalog_song_id = cs.id
           JOIN setlists sl ON sl.id = ss.setlist_id
           WHERE sl.band_id = ?""",
        (band_id,),
    ).fetchall()
    for song_id, key, bpm in songs:
        conn.execute(
            """INSERT OR IGNORE INTO band_song_arrangements (band_id, catalog_song_id, default_key, default_bpm)
               VALUES (?, ?, ?, ?)""",
            (band_id, song_id, key, bpm),
        )
    conn.commit()
    print(f"Copper Creek band_id={band_id}, {len(songs)} arrangements seeded.")
    return band_id


def seed_groove_unit(conn) -> int:
    """Seed mock 'The Groove Unit' band, its arrangements, and one setlist."""
    conn.execute(
        "INSERT OR IGNORE INTO bands (name, genre, notes) VALUES (?, ?, ?)",
        ("The Groove Unit", "Funk / R&B / Soul", "Mock band for multi-band UI testing"),
    )
    band_id = conn.execute("SELECT id FROM bands WHERE name='The Groove Unit'").fetchone()[0]

    for title, artist, key, bpm in GROOVE_UNIT_SONGS:
        song_row = conn.execute(
            "SELECT id FROM catalog_songs WHERE title=? AND artist=?", (title, artist)
        ).fetchone()
        if not song_row:
            print(f"  WARNING: song not found in catalog: '{title}' by {artist} — skipping")
            continue
        conn.execute(
            """INSERT OR IGNORE INTO band_song_arrangements
               (band_id, catalog_song_id, default_key, default_bpm, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (band_id, song_row[0], key, bpm, "The Groove Unit arrangement"),
        )

    # Setlist
    sl = conn.execute(
        "SELECT id FROM setlists WHERE name=? AND band_id=?",
        (GROOVE_SETLIST["name"], band_id),
    ).fetchone()
    if not sl:
        cur = conn.execute(
            "INSERT INTO setlists (name, band_id, band, gig_date, venue, active) VALUES (?,?,?,?,?,0)",
            (GROOVE_SETLIST["name"], band_id, "The Groove Unit",
             GROOVE_SETLIST["gig_date"], GROOVE_SETLIST["venue"]),
        )
        setlist_id = cur.lastrowid
    else:
        setlist_id = sl[0]

    for title, artist, set_num, pos, key_ov in GROOVE_SETLIST["songs"]:
        song_row = conn.execute(
            "SELECT id FROM catalog_songs WHERE title=? AND artist=?", (title, artist)
        ).fetchone()
        if not song_row:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO setlist_songs (setlist_id, catalog_song_id, set_number, position, key_override)
               VALUES (?,?,?,?,?)""",
            (setlist_id, song_row[0], set_num, pos, key_ov),
        )

    conn.commit()
    print(f"The Groove Unit band_id={band_id}, setlist_id={setlist_id} seeded.")
    return band_id


def teardown_mock(conn) -> None:
    """Remove The Groove Unit and all its data (CASCADE handles arrangements + setlists)."""
    row = conn.execute("SELECT id FROM bands WHERE name='The Groove Unit'").fetchone()
    if not row:
        print("The Groove Unit not found — nothing to tear down.")
        return
    band_id = row[0]
    # Remove setlist_songs for groove unit setlists
    conn.execute(
        "DELETE FROM setlist_songs WHERE setlist_id IN (SELECT id FROM setlists WHERE band_id=?)",
        (band_id,),
    )
    conn.execute("DELETE FROM setlists WHERE band_id=?", (band_id,))
    conn.execute("DELETE FROM band_song_arrangements WHERE band_id=?", (band_id,))
    conn.execute("DELETE FROM bands WHERE id=?", (band_id,))
    conn.commit()
    print(f"Tore down The Groove Unit (band_id={band_id}) and all its data.")


def main() -> None:
    teardown = "--teardown-mock" in sys.argv
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=ON")

    if teardown:
        teardown_mock(conn)
    else:
        migrate(conn)
        seed_copper_creek(conn)
        seed_groove_unit(conn)

        # Summary
        bands = conn.execute("SELECT id, name, active FROM bands").fetchall()
        print("\nBands in DB:")
        for b in bands:
            count = conn.execute(
                "SELECT COUNT(*) FROM band_song_arrangements WHERE band_id=?", (b[0],)
            ).fetchone()[0]
            print(f"  [{b[0]}] {b[1]} (active={b[2]}) — {count} arrangements")

    conn.close()


if __name__ == "__main__":
    main()
