"""Install the confirmed Copper Creek Wide Open setlist for 2026-08-23."""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import get_connection  # noqa: E402

GIG_NAME = "Copper Creek Wide Open 8/23/26"
GIG_DATE = "2026-08-23"
VENUE = "Wide Open"
BAND = "Copper Creek"
AUDIO_ROOT = Path(r"G:\Muzic")
EXPECTED_SONG_COUNT = 33
PASSENGER_TITLE = "Passenger"
PASSENGER_ARTIST = "Siouxsie & the Banshees"
PASSENGER_KEY = "Dm"
PASSENGER_BPM = 140
PASSENGER_AUDIO_FILE = "The Passenger - Souxie & the Banshees .mp3"
PASSENGER_SHEET_NAME = "Siouxsie & the Banshees - The Passenger.docx"
SETLIST_NOTES = (
    "Source: CC Wide Open 08232026 2-Set.xlsx and PDF; "
    "Passenger Dm (T Call); Celebrate Ab (throw in). "
    "Passenger is catalog-only because the setlist schema has no optional/transition row type."
)

# (set number, position, source title, confirmed key)
SETLIST: list[tuple[int, int, str, str]] = [
    (1, 1, "Long Train Runnin", "Gm"),
    (1, 2, "I'm Alright", "D"),
    (1, 3, "Bobby McGee", "G"),
    (1, 4, "Gold On Ceiling", "G"),
    (1, 5, "Jacky", "Gm"),
    (1, 6, "Smooth", "Am"),
    (1, 7, "I Will Survive", "Am"),
    (1, 8, "Disco Inferno", "Ab"),
    (1, 9, "Play That Funky Music", "Em"),
    (1, 10, "Love Sneaking Up", "D"),
    (1, 11, "Smooth Operator", "Dm"),
    (1, 12, "Baker Street", "D"),
    (1, 13, "Evil Ways", "Gm"),
    (1, 14, "Peg", "G"),
    (1, 15, "I Can't Go 4 That", "F"),
    (1, 16, "Mony Mony", "F"),
    (2, 1, "Pick Up the Pieces", "Fm"),
    (2, 2, "25 or 6 to 4", "A"),
    (2, 3, "Too Much Time", "A"),
    (2, 4, "Shaded Jade", "Bm"),
    (2, 5, "Black Magic", "Dm"),
    (2, 6, "Gimme Gimme Gimme", "Dm"),
    (2, 7, "Do It Again", "Gm"),
    (2, 8, "On the Dark Side", "E"),
    (2, 9, "What I Like About U", "E"),
    (2, 10, "I Feel the Earth", "Cm"),
    (2, 11, "Boots", "E"),
    (2, 12, "Blue on Black", "C"),
    (2, 13, "Carnival", "F#m"),
    (2, 14, "Call Me", "B"),
    (2, 15, "Heart of R&R", "C"),
    (2, 16, "Heavy Chevy", "C"),
    (2, 17, "Roll With Changes", "C"),
]

ALIASES = {
    "bobby mcgee": "Me and Bobby McGee",
    "gold on ceiling": "Gold on the Ceiling",
    "love sneaking up": "Love Sneakin' Up on You",
    "i cant go 4 that": "I Can't Go for That",
    "too much time": "Too Much Time on My Hands",
    "black magic": "Black Magic Woman",
    "gimme gimme gimme": "Gimme! Gimme! Gimme!",
    "what i like about u": "What I Like About You",
    "i feel the earth": "I Feel the Earth Move",
    "boots": "These Boots Are Made for Walkin'",
    "heart of rr": "Heart of Rock & Roll",
    "roll with changes": "Roll with the Changes",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", value.lower()).strip()


def _canonical_title(source_title: str) -> str:
    return ALIASES.get(_normalize(source_title), source_title)


def _find_catalog_song(conn, source_title: str):
    title = _canonical_title(source_title)
    row = conn.execute(
        "SELECT id, title, source_file FROM catalog_songs WHERE title=? LIMIT 1",
        (title,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"No canonical catalog row for Wide Open song: {source_title}")
    return row


def _sheet_music_files(title: str) -> list[Path]:
    target = _normalize(title)
    matches = []
    for path in (PROJECT_ROOT / "catalog" / "sheet_music").rglob("*"):
        if path.is_file() and target in _normalize(path.stem):
            matches.append(path)
    return matches


def reconcile_passenger_catalog(conn, band_id: int) -> int:
    """Ensure Passenger has one canonical catalog, arrangement, and sheet row."""
    rows = conn.execute(
        "SELECT id FROM catalog_songs WHERE title=? AND artist=?",
        (PASSENGER_TITLE, PASSENGER_ARTIST),
    ).fetchall()
    if len(rows) > 1:
        raise RuntimeError("Duplicate canonical Passenger catalog rows found")

    if rows:
        catalog_id = rows[0][0]
        conn.execute(
            """UPDATE catalog_songs
                    SET key_sig=?, bpm=?, source_file=?, updated_at=datetime('now')
               WHERE id=?""",
                (PASSENGER_KEY, PASSENGER_BPM, PASSENGER_AUDIO_FILE, catalog_id),
        )
    else:
        cursor = conn.execute(
            """INSERT INTO catalog_songs
                   (title, artist, key_sig, bpm, source_file)
               VALUES (?, ?, ?, ?, ?)""",
            (PASSENGER_TITLE, PASSENGER_ARTIST, PASSENGER_KEY, PASSENGER_BPM, PASSENGER_AUDIO_FILE),
        )
        catalog_id = cursor.lastrowid

    conn.execute(
        """INSERT INTO band_song_arrangements
               (band_id, catalog_song_id, default_key, default_bpm)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(band_id, catalog_song_id) DO UPDATE
           SET default_key=excluded.default_key, default_bpm=excluded.default_bpm""",
        (band_id, catalog_id, PASSENGER_KEY, PASSENGER_BPM),
    )
    sheet_row = conn.execute(
        "SELECT id FROM sheet_music WHERE source='local' AND name=? LIMIT 1",
        (PASSENGER_SHEET_NAME,),
    ).fetchone()
    if sheet_row is None:
        conn.execute(
            """INSERT INTO sheet_music
                   (source, name, file_ext, category, artist, title, local_path, deleted_at)
               VALUES ('local', ?, '.docx', 'covers', ?, ?, ?, NULL)""",
            (
                PASSENGER_SHEET_NAME,
                PASSENGER_ARTIST,
                PASSENGER_TITLE,
                f"catalog/sheet_music/covers/{PASSENGER_SHEET_NAME}",
            ),
        )
    conn.execute(
        """UPDATE sheet_music
           SET deleted_at=NULL, artist=?, title=?, local_path=?
           WHERE name=? AND source='local'""",
        (
            PASSENGER_ARTIST,
            PASSENGER_TITLE,
            f"catalog/sheet_music/covers/{PASSENGER_SHEET_NAME}",
            PASSENGER_SHEET_NAME,
        ),
    )
    return catalog_id


def _validate_media(conn) -> list[tuple[int, int, int, str]]:
    resolved = []
    missing = []
    for set_number, position, source_title, key in SETLIST:
        row = _find_catalog_song(conn, source_title)
        audio = AUDIO_ROOT / row[2] if row[2] else None
        sheets = _sheet_music_files(row[1])
        if audio is None or not audio.is_file():
            missing.append(f"{source_title}: audio {audio}")
        if not sheets:
            missing.append(f"{source_title}: sheet music")
        resolved.append((set_number, position, row[0], key))
    if missing:
        raise RuntimeError("Wide Open media validation failed:\n" + "\n".join(missing))
    return resolved


def update() -> tuple[int, int]:
    conn = get_connection()
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        band = conn.execute("SELECT id FROM bands WHERE name=?", (BAND,)).fetchone()
        if band is None:
            raise RuntimeError(f"Band not found: {BAND}")
        band_id = band[0]
        reconcile_passenger_catalog(conn, band_id)
        resolved = _validate_media(conn)

        for _, _, catalog_id, key in resolved:
            arrangement = conn.execute(
                "SELECT id FROM band_song_arrangements WHERE band_id=? AND catalog_song_id=?",
                (band_id, catalog_id),
            ).fetchone()
            if arrangement is None:
                conn.execute(
                    "INSERT INTO band_song_arrangements (band_id,catalog_song_id,default_key) VALUES (?,?,?)",
                    (band_id, catalog_id, key),
                )

        existing = conn.execute(
            "SELECT id FROM setlists WHERE name=? AND band_id=?",
            (GIG_NAME, band_id),
        ).fetchone()
        if existing:
            setlist_id = existing[0]
            conn.execute("DELETE FROM setlist_songs WHERE setlist_id=?", (setlist_id,))
            conn.execute(
                "UPDATE setlists SET gig_date=?,venue=?,active=1,notes=? WHERE id=?",
                (GIG_DATE, VENUE, SETLIST_NOTES, setlist_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO setlists (name,band,gig_date,venue,active,notes,band_id) VALUES (?,?,?,?,1,?,?)",
                (GIG_NAME, BAND, GIG_DATE, VENUE, SETLIST_NOTES, band_id),
            )
            setlist_id = cursor.lastrowid

        for set_number, position, catalog_id, key in resolved:
            conn.execute(
                "INSERT INTO setlist_songs (setlist_id,catalog_song_id,set_number,position,key_override) VALUES (?,?,?,?,?)",
                (setlist_id, catalog_id, set_number, position, key),
            )

        conn.execute(
            "UPDATE setlists SET active=0 WHERE band_id=? AND id<>?",
            (band_id, setlist_id),
        )
        conn.commit()
        return setlist_id, len(resolved)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    setlist_id, count = update()
    print(f"PASS: activated {count} Wide Open songs in setlist {setlist_id}")
