"""
Update catalog_songs.source_file for setlist songs that have matching audio in G:\\Muzic.
Requires HEARTMUSIC_DB_KEY env var.

Usage:
    cd "f:\\❤Music"
    C:\\G\\python.exe tools\\update_audio_sources.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str((Path(__file__).parents[1] / "src").resolve()))
from utils.init_db import get_connection  # noqa: E402

# Maps DB title → relative filename in G:\\Muzic (flat)
# Confirmed present by scanning G:\\Muzic on 2026-04-25
AUDIO_MAP: dict[str, str] = {
    "I'm Alright":          "I'm Alright - Kenny Loggins.mp3",
    "Talk Me Into It":      "Talk Me Into It - Kevin Redmond.mp3",
    "Shaded Jade":          "Shaded Jade - Tamala Cameron and Gene Ngo.mp3",
    "Play That Funky Music": "Play That Funky Music - Wild Cherry.mp3",
    "On the Dark Side":     "On the Darkside - John Cafferty.mp3",
    "Celebrate":            "Celebration - Kool and The Gang.mp3",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    args = parser.parse_args()

    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=ON")

    updated = 0
    for title, filename in AUDIO_MAP.items():
        row = conn.execute(
            "SELECT id, source_file FROM catalog_songs WHERE title = ?", (title,)
        ).fetchone()
        if row is None:
            print(f"  ✗ NOT IN DB: {title!r}")
            continue
        song_id, current_sf = row
        if current_sf:
            print(f"  ~ SKIP (already set): {title!r} → {current_sf}")
            continue
        if args.dry_run:
            print(f"  [DRY] UPDATE catalog_songs SET source_file = {filename!r} WHERE id = {song_id};")
        else:
            conn.execute(
                "UPDATE catalog_songs SET source_file = ? WHERE id = ?",
                (filename, song_id),
            )
            print(f"  ✓ UPDATED: {title!r} → {filename}")
            updated += 1

    if not args.dry_run:
        conn.commit()
        print(f"\n{updated} song(s) updated.")
    else:
        print(f"\n[DRY RUN] {len(AUDIO_MAP)} rows would be evaluated.")

    conn.close()


if __name__ == "__main__":
    main()
