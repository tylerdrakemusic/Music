"""
One-time remediation: remap setlist_songs (setlist id=3) from orphan 'Various'
catalog_song rows to canonical catalog rows with real artist/BPM data.

Songs not found in the canonical catalog are flagged with a note and kept as-is.
Orphan 'Various' rows that are no longer referenced are deleted.
"""
import sys
import re
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils.init_db import get_connection

SETLIST_ID = 3
BAND_ID = 1


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # Build canonical title → catalog_song_id map (only songs in BSA for this band)
    canonical_rows = cur.execute(
        """SELECT cs.id, cs.title FROM catalog_songs cs
           JOIN band_song_arrangements bsa ON bsa.catalog_song_id = cs.id AND bsa.band_id = ?""",
        (BAND_ID,),
    ).fetchall()
    canon_map: dict[str, int] = {normalize(dict(r)["title"]): dict(r)["id"] for r in canonical_rows}
    print(f"Canonical catalog songs for band {BAND_ID}: {len(canon_map)}")

    # Get all setlist_songs for this setlist
    sl_songs = cur.execute(
        "SELECT id, catalog_song_id FROM setlist_songs WHERE setlist_id = ?",
        (SETLIST_ID,),
    ).fetchall()

    # Alias map for shorthand titles
    alias_map: dict[str, int] = {
        dict(r)["alias"]: dict(r)["catalog_song_id"]
        for r in cur.execute("SELECT alias, catalog_song_id FROM catalog_song_aliases").fetchall()
    }

    remapped = 0
    not_found = []
    orphan_ids: set[int] = set()

    for row in sl_songs:
        ss_id = dict(row)["id"]
        old_cs_id = dict(row)["catalog_song_id"]
        cs_row = cur.execute("SELECT title, artist FROM catalog_songs WHERE id = ?", (old_cs_id,)).fetchone()
        if not cs_row:
            continue
        cs = dict(cs_row)
        title = cs["title"]
        key = normalize(title)

        resolved_id = canon_map.get(key) or alias_map.get(key)
        if resolved_id:
            cur.execute(
                "UPDATE setlist_songs SET catalog_song_id = ? WHERE id = ?",
                (resolved_id, ss_id),
            )
            orphan_ids.add(old_cs_id)
            remapped += 1
            via = "alias" if key in alias_map and key not in canon_map else "canon"
            print(f"  Remapped [{via}]: '{title}' (orphan id={old_cs_id}) -> canonical id={resolved_id}")
        else:
            not_found.append((ss_id, old_cs_id, title))
            # Tag the orphan row so the UI can show a warning
            cur.execute(
                "UPDATE catalog_songs SET artist = '\u26a0 NOT IN CATALOG' WHERE id = ? AND artist = 'Various'",
                (old_cs_id,),
            )
            print(f"  NOT IN CATALOG: '{title}' (catalog_song_id={old_cs_id}) -- flagged for UI warning")

    conn.commit()

    # Delete orphan 'Various' rows that are no longer referenced by any setlist_song
    if orphan_ids:
        still_used = {
            dict(r)["catalog_song_id"]
            for r in cur.execute("SELECT DISTINCT catalog_song_id FROM setlist_songs").fetchall()
        }
        deletable = [i for i in orphan_ids if i not in still_used]
        if deletable:
            placeholders = ",".join("?" * len(deletable))
            cur.execute(
                f"DELETE FROM catalog_songs WHERE id IN ({placeholders}) AND artist = 'Various'",
                deletable,
            )
            print(f"\nDeleted {cur.rowcount} orphan 'Various' catalog_songs rows.")
        conn.commit()

    print(f"\nDone: {remapped} remapped, {len(not_found)} not in catalog.")
    if not_found:
        print("Songs needing catalog entry:")
        for ss_id, cs_id, title in not_found:
            print(f"  - '{title}' (catalog_song_id={cs_id})")


if __name__ == "__main__":
    main()
