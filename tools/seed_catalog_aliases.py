"""
Migrate heartmusic.db to add catalog_song_aliases table (idempotent),
then seed it with all known setlist title abbreviations for Copper Creek.

Run once, re-run safely (INSERT OR IGNORE).
"""
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils.init_db import get_connection


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


# (alias, canonical_title)
# alias = the abbreviated / shorthand form used in setlist imports
# canonical_title = exact title in catalog_songs
KNOWN_ALIASES = [
    ("boots",                      "These Boots Are Made for Walkin'"),
    ("these boots",                "These Boots Are Made for Walkin'"),
    ("bobby mcgee",                "Me and Bobby McGee"),
    ("me and bobby mcgee",         "Me and Bobby McGee"),
    ("reeling in the yrs",         "Reelin' in the Years"),
    ("reeling in the years",       "Reelin' in the Years"),
    ("too much time",              "Too Much Time on My Hands"),
    ("roll with changes",          "Roll with the Changes"),
    ("black magic",                "Black Magic Woman"),
    ("logical song",               "The Logical Song"),
    ("i feel the earth",           "I Feel the Earth Move"),
    ("i feel the earth move",      "I Feel the Earth Move"),
    ("heart of r&r",               "Heart of Rock & Roll"),
    ("heart of rock and roll",     "Heart of Rock & Roll"),
    ("love sneaking up",           "Love Sneakin' Up on You"),
    ("what i like about u",        "What I Like About You"),
    ("what i like about you",      "What I Like About You"),
    ("stop draggin my hrt",        "Stop Draggin' My Heart Around"),
    ("stop draggin my heart",      "Stop Draggin' My Heart Around"),
    ("i cant go 4 that",           "I Can't Go for That"),
    ("i cant go for that",         "I Can't Go for That"),
    ("play that funky m",          "Play That Funky Music"),
    ("play that funky music",      "Play That Funky Music"),
    ("talk me into it",            "Talk Me Into It"),  # Kevin Redmond — already canonical
]


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # Create table if it doesn't exist yet
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS catalog_song_aliases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alias           TEXT NOT NULL UNIQUE,
            catalog_song_id INTEGER NOT NULL REFERENCES catalog_songs(id) ON DELETE CASCADE,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_aliases_song ON catalog_song_aliases(catalog_song_id);
    """)
    conn.commit()
    print("Table catalog_song_aliases ensured.")

    inserted = 0
    skipped = 0
    not_found = []

    for alias_raw, canonical_title in KNOWN_ALIASES:
        alias_norm = normalize(alias_raw)

        # Look up canonical catalog_song_id by exact title
        row = cur.execute(
            "SELECT id FROM catalog_songs WHERE title = ? LIMIT 1",
            (canonical_title,),
        ).fetchone()

        if not row:
            # Also try normalized match
            all_cs = cur.execute("SELECT id, title FROM catalog_songs").fetchall()
            match = next((dict(r)["id"] for r in all_cs if normalize(dict(r)["title"]) == normalize(canonical_title)), None)
            if not match:
                not_found.append(canonical_title)
                print(f"  SKIP (not in DB): '{canonical_title}'")
                continue
            cs_id = match
        else:
            cs_id = dict(row)["id"]

        cur.execute(
            "INSERT OR IGNORE INTO catalog_song_aliases (alias, catalog_song_id) VALUES (?, ?)",
            (alias_norm, cs_id),
        )
        if cur.rowcount:
            inserted += 1
            print(f"  + alias '{alias_norm}' -> catalog_song_id={cs_id} ({canonical_title})")
        else:
            skipped += 1

    conn.commit()
    print(f"\nDone: {inserted} inserted, {skipped} already existed, {len(not_found)} canonical titles not found in DB.")
    if not_found:
        print("Titles missing from catalog_songs (add them first):")
        for t in not_found:
            print(f"  - {t!r}")

    conn.close()


if __name__ == "__main__":
    main()
