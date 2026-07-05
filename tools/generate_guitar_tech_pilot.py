"""Guitar-tech pilot batch generator (FR-20260705-guitar-tech-persona-agent).

Selects gap songs (catalog_songs with no dedicated .hlx preset), assigns
each a guitar-legend persona via the rubric, generates a validated HX Stomp
preset, writes it into HelixFiles/, records a guitar_tone_profiles row
(status='proposed'), and appends TODO.md checklist entries.

Usage:
    C:\\G\\python.exe tools\\generate_guitar_tech_pilot.py [--dry-run]
    C:\\G\\python.exe tools\\generate_guitar_tech_pilot.py --song-id 35 --song-id 27

Requires HEARTMUSIC_DB_KEY (Windows System Environment Variable) to be set.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import utils.init_db as _init_db_module  # noqa: E402

_init_db_module.use_worktree_aware_db_path(_ROOT)

from guitar_tech.pilot_batch import build_pilot_results  # noqa: E402
from guitar_tech.todo_writer import append_todo_entries  # noqa: E402
from utils.init_db import get_connection  # noqa: E402

HELIX_DIR = _ROOT / "HelixFiles"
TODO_PATH = HELIX_DIR / "TODO.md"

# Curated pilot batch: 5 hand-selected gap songs spanning all 4 numeric
# rubric rules (slow blues, funk, hard rock, default) plus the Santana
# artist-hint rule. Confirmed as genuine gaps + correct persona assignments
# against the live catalog during FR development.
DEFAULT_SONG_IDS = [35, 27, 14, 13, 20]


def run(song_ids: list[int], *, dry_run: bool) -> int:
    """Generate, validate, and (unless dry_run) persist the pilot batch.

    Returns process exit code (0 success, 1 on any validation failure).
    """
    conn = get_connection()
    try:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='guitar_tone_profiles'"
        ).fetchone()
        if not table_exists and not dry_run:
            print(
                "ERROR: guitar_tone_profiles table does not exist. "
                "Run tools/migrate_guitar_tone_profiles.py first."
            )
            return 1

        existing_filenames = [p.name for p in HELIX_DIR.glob("*.hlx")]
        placeholders = ",".join("?" for _ in song_ids)
        rows = conn.execute(
            f"SELECT id, title, artist, key_sig, bpm FROM catalog_songs "
            f"WHERE id IN ({placeholders})",
            song_ids,
        ).fetchall()

        found_ids = {row["id"] for row in rows}
        for missing in set(song_ids) - found_ids:
            print(f"WARNING: catalog_song id={missing} not found, skipping.")

        results = build_pilot_results(rows, existing_filenames)
        skipped = found_ids - {r.song["id"] for r in results}
        for song_id in skipped:
            print(f"WARNING: catalog_song id={song_id} already has a dedicated preset, skipping.")

        print(f"\n{'Song':<32} {'Persona':<45} {'Valid':<6} Filename")
        for r in results:
            print(f"{r.song['title']:<32} {r.persona_match.label:<45} {str(r.validation.ok):<6} {r.filename}")
            for issue in r.validation.issues:
                print(f"    ISSUE [{issue.location}]: {issue.message}")

        if dry_run:
            print("\nDry run -- no files written, no DB rows inserted.")
            return 0

        failed = [r for r in results if not r.validation.ok]
        if failed:
            print(f"\n{len(failed)} preset(s) failed validation; aborting (no files/DB changes made).")
            return 1

        written_filenames = []
        for r in results:
            out_path = HELIX_DIR / r.filename
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(r.preset, f, indent=1)
            conn.execute(
                """
                INSERT INTO guitar_tone_profiles
                    (catalog_song_id, persona, rationale, hlx_filename, status)
                VALUES (?, ?, ?, ?, 'proposed')
                ON CONFLICT(catalog_song_id, persona) DO UPDATE SET
                    hlx_filename = excluded.hlx_filename,
                    rationale = excluded.rationale,
                    updated_at = datetime('now')
                """,
                (r.song["id"], r.persona_match.label, r.persona_match.rationale, r.filename),
            )
            written_filenames.append(r.filename)
            print(f"Wrote {out_path}")

        conn.commit()

        if written_filenames:
            append_todo_entries(TODO_PATH, written_filenames)
            print(f"\nAppended {len(written_filenames)} entries to {TODO_PATH}")

        return 0
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing files or DB rows"
    )
    parser.add_argument(
        "--song-id",
        type=int,
        action="append",
        dest="song_ids",
        help="Override the default pilot song ids (repeatable)",
    )
    args = parser.parse_args()
    sys.exit(run(args.song_ids or DEFAULT_SONG_IDS, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
