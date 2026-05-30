"""Ingest sheet music PDF metadata from Google Drive into heartmusic.db.

Scans the entire Google Drive for PDF files, filters to sheet music by
folder path, and inserts metadata into the sheet_music table.
Idempotent — rows with matching gdrive_file_id are skipped.

Auth requires GDRIVE_SA_KEY env var (base64-encoded service account JSON).

Usage::

    C:\\G\\python.exe src/scripts/ingest_sheet_music_gdrive.py

TODO: In production, install ⊕Workspace as a proper package instead of
      using sys.path.insert().  This sys.path hack is acceptable for the
      initial spike only (FR-20260530-gdrive-integration).
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — spike: insert ⊕Workspace src/ so we can import GDriveClient.
# TODO: replace with a proper editable install or published package.
# ---------------------------------------------------------------------------
_WORKSPACE_SRC = Path(r"f:\⊕Workspace\src")
if str(_WORKSPACE_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_SRC))

_MUSIC_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_MUSIC_ROOT / "src"))

from integrations.gdrive import GDriveClient  # noqa: E402
from utils.init_db import get_connection  # noqa: E402

# ---------------------------------------------------------------------------
# Filename parser (same heuristic as backfill_local_sheet_music.py)
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(r"^(.+?) - (.+?)(?:\s*\((.+?)\))?$")
_TYLER_ARTIST = "Tyler James Drake"


def _parse_filename(stem: str) -> tuple[str, str, str]:
    """Return (artist, title, key_descriptor) from a filename stem."""
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
# Category inference from Drive folder path
# ---------------------------------------------------------------------------


def _infer_category(folder_path: str) -> str:
    """Infer sheet music category from the Drive folder path."""
    lower = folder_path.lower()
    if "sheet_music/covers" in lower or "sheet_music\\covers" in lower:
        return "covers"
    if "sheet_music/originals" in lower or "sheet_music\\originals" in lower:
        return "originals"
    if "sheet_music/templates" in lower or "sheet_music\\templates" in lower:
        return "templates"
    return "unknown"


# ---------------------------------------------------------------------------
# Main ingest function
# ---------------------------------------------------------------------------

_PDF_MIME = "application/pdf"


def ingest(conn=None) -> tuple[int, int, int]:
    """Scan Google Drive for PDF files and insert into sheet_music table.

    Args:
        conn: Optional SQLite connection (for testing with a plain DB).
            If None, uses get_connection() (encrypted heartmusic.db).

    Returns:
        Tuple of (inserted, skipped, total_on_drive).
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    client = GDriveClient()
    drive_files = client.list_files(mime_types=[_PDF_MIME])
    total = len(drive_files)

    inserted = 0
    skipped = 0

    try:
        for f in drive_files:
            gdrive_file_id = f["id"]

            # Idempotency check
            existing = conn.execute(
                "SELECT id FROM sheet_music WHERE gdrive_file_id = ?",
                (gdrive_file_id,),
            ).fetchone()
            if existing:
                skipped += 1
                continue

            name = f["name"]
            stem = Path(name).stem
            folder_path = client.get_folder_path(gdrive_file_id, f.get("parents", []))
            category = _infer_category(folder_path)
            artist, title, key_descriptor = _parse_filename(stem)
            file_size = int(f.get("size", 0) or 0)
            modified_at = f.get("modifiedTime", "")

            conn.execute(
                """
                INSERT INTO sheet_music
                    (source, name, file_ext, category, artist, title,
                     key_descriptor, gdrive_file_id, gdrive_folder_path,
                     file_size_bytes, gdrive_modified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "gdrive",
                    name,
                    ".pdf",
                    category,
                    artist,
                    title,
                    key_descriptor,
                    gdrive_file_id,
                    folder_path,
                    file_size,
                    modified_at,
                ),
            )
            inserted += 1

        conn.commit()
    finally:
        if close_conn:
            conn.close()

    print(
        f"[ingest_sheet_music_gdrive] inserted={inserted}, "
        f"skipped={skipped}, total_on_drive={total}"
    )
    return inserted, skipped, total


if __name__ == "__main__":
    ingest()
