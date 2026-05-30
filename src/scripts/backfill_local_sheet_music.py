"""Backfill local sheet music files into the sheet_music DB table.

Walks catalog/sheet_music/{covers,originals,templates}/ and inserts
one row per file.  Idempotent — rows with matching local_path are skipped.

Usage::

    C:\\G\\python.exe src/scripts/backfill_local_sheet_music.py

The script can also be called programmatically for testing:

    from scripts.backfill_local_sheet_music import backfill
    backfill(sheet_music_root=Path(...), db_path="path/to/test.db")
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Allow running from the ❤Music root
_MUSIC_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_MUSIC_ROOT / "src"))

# ---------------------------------------------------------------------------
# Filename parser — shared with ingest_sheet_music_gdrive.py
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(r"^(.+?) - (.+?)(?:\s*\((.+?)\))?$")

_VALID_EXTENSIONS = {".pdf", ".docx", ".jpg", ".png", ".txt"}

_VALID_CATEGORIES = {"covers", "originals", "templates"}

# The catalog uses two conventions:
#   Originals: "Tyler James Drake - Song Title (Key X)"  → artist-first
#   Covers:    "Song Title - Artist (Descriptor)"         → title-first
_TYLER_ARTIST = "Tyler James Drake"


def _parse_filename(stem: str) -> tuple[str, str, str]:
    """Return (artist, title, key_descriptor) from a filename stem.

    Handles both catalog conventions:
    - TJD originals: group1=artist, group2=title
    - Covers: group1=title, group2=artist (swapped)
    Falls back to (artist="", title=stem, key_descriptor="") if no match.
    """
    m = _FILENAME_RE.match(stem)
    if m:
        part1 = m.group(1)
        part2 = m.group(2)
        descriptor = m.group(3) or ""
        if part1 == _TYLER_ARTIST:
            return part1, part2, descriptor  # originals: artist-first
        return part2, part1, descriptor  # covers: title-first → swap
    return "", stem, ""


# ---------------------------------------------------------------------------
# Public backfill function
# ---------------------------------------------------------------------------


def backfill(
    sheet_music_root: Optional[Path] = None,
    db_path: Optional[str] = None,
) -> tuple[int, int]:
    """Insert local sheet music files into the sheet_music table.

    Args:
        sheet_music_root: Path to the sheet_music directory to walk.
            Defaults to ``<music_root>/catalog/sheet_music``.
        db_path: Path to the SQLite DB.  If None, uses heartmusic.db via
            ``get_connection()`` (encrypted).  If given, uses a plain
            unencrypted ``sqlite3.connect(db_path)`` — for tests only.

    Returns:
        Tuple of (inserted_count, skipped_count).
    """
    if sheet_music_root is None:
        sheet_music_root = _MUSIC_ROOT / "catalog" / "sheet_music"

    if db_path is not None:
        conn = sqlite3.connect(db_path)
    else:
        from utils.init_db import get_connection  # noqa: PLC0415

        conn = get_connection()

    inserted = 0
    skipped = 0

    try:
        for sub in sheet_music_root.iterdir():
            if not sub.is_dir():
                continue
            category = sub.name if sub.name in _VALID_CATEGORIES else "unknown"

            for fpath in sub.rglob("*"):
                if not fpath.is_file():
                    continue
                if fpath.suffix.lower() not in _VALID_EXTENSIONS:
                    continue

                # Build local_path relative to music root
                try:
                    local_path = str(fpath.relative_to(_MUSIC_ROOT)).replace("\\", "/")
                except ValueError:
                    local_path = str(fpath).replace("\\", "/")

                # Idempotency check
                existing = conn.execute(
                    "SELECT id FROM sheet_music WHERE local_path = ?", (local_path,)
                ).fetchone()
                if existing:
                    skipped += 1
                    continue

                stem = fpath.stem
                artist, title, key_descriptor = _parse_filename(stem)
                file_ext = fpath.suffix.lower()
                file_size = fpath.stat().st_size

                conn.execute(
                    """
                    INSERT INTO sheet_music
                        (source, name, file_ext, category, artist, title,
                         key_descriptor, local_path, file_size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "local",
                        fpath.name,
                        file_ext,
                        category,
                        artist,
                        title,
                        key_descriptor,
                        local_path,
                        file_size,
                    ),
                )
                inserted += 1

        conn.commit()
    finally:
        conn.close()

    print(
        f"[backfill_local_sheet_music] inserted={inserted}, skipped={skipped}"
    )
    return inserted, skipped


if __name__ == "__main__":
    inserted, skipped = backfill()
    print(
        f"[backfill_local_sheet_music] Done. {inserted} inserted, {skipped} skipped."
    )
