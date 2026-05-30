"""Ingest sheet music from Google Drive into the local catalog + heartmusic.db.

Scans the entire Google Drive for PDF, DOCX, and Google Docs files, downloads
them into catalog/sheet_music/<category>/ with standardized names, and records
metadata in the sheet_music table.  Google Docs are exported as .docx.

Idempotent — rows with matching gdrive_file_id (or existing local file) are
skipped on re-run.

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
_WORKSPACE_SRC = Path(r"f:\⊕Workspace\.worktrees\fr-gdrive-integration\src")
if str(_WORKSPACE_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_SRC))

_WORKTREE_SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_WORKTREE_SRC))

from integrations.gdrive import GDriveClient  # noqa: E402
from utils.init_db import get_connection  # noqa: E402

# ---------------------------------------------------------------------------
# Resolve music root — when running from a worktree, use HEARTMUSIC_DB_PATH
# env var to find the real project root (db lives at <root>/data/heartmusic.db)
# ---------------------------------------------------------------------------
import os as _os  # noqa: E402

_DB_PATH_ENV = _os.environ.get("HEARTMUSIC_DB_PATH", "")
if _DB_PATH_ENV:
    # DB is at <music_root>/data/heartmusic.db → parents[1] = music root
    _MUSIC_ROOT = Path(_DB_PATH_ENV).resolve().parents[1]
else:
    _MUSIC_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# MIME types to scan
# ---------------------------------------------------------------------------
_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_GDOC_MIME = "application/vnd.google-apps.document"
_SCAN_MIMES = [_PDF_MIME, _DOCX_MIME, _GDOC_MIME]

# Google Docs are exported as .docx
_GDOC_EXPORT_MIME = _DOCX_MIME
_GDOC_EXPORT_EXT = ".docx"

# ---------------------------------------------------------------------------
# Filename standardizer — extract key from Drive naming conventions
# ---------------------------------------------------------------------------

# Matches "in Gm", "in E", "in Bm", "in C#m", "in Ab" at end of stem
_KEY_IN_RE = re.compile(
    r"\s+in\s+([A-G][b#]?(?:m(?:in(?:or)?)?|maj(?:or)?)?)\s*$",
    re.IGNORECASE,
)
# Matches existing "(Key Gm)", "(Gm)", or "(in Gm)" parenthetical anywhere
_KEY_PAREN_RE = re.compile(
    r"\s*\((?:[Kk]ey\s+|in\s+)?([A-G][b#]?(?:m(?:in(?:or)?)?|maj(?:or)?)?)\)",
    re.IGNORECASE,
)
# Matches "_Key_Gm", "_Key_G", "_Key_F_Sharp", "_Key_F_Sharpm", "_Key_Ab"
_KEY_UNDERSCORE_RE = re.compile(
    r"_[Kk]ey_([A-G](?:_?[Ss]harp|_?[Ff]lat|[b#])?m?)",
    re.IGNORECASE,
)


def _normalize_underscores(stem: str) -> str:
    """Convert underscore naming to spaced: 'Song_Artist_Key_Gm' → 'Song Artist'."""
    # Remove _Key_X suffix first (handled separately)
    clean = _KEY_UNDERSCORE_RE.sub("", stem)
    # Replace underscores with spaces, collapse multiple spaces
    clean = clean.replace("_", " ").strip()
    return re.sub(r"  +", " ", clean)


def _standardize_name(stem: str, ext: str) -> tuple[str, str]:
    """Return (standardized_filename_with_ext, key_descriptor).

    Converts Drive naming conventions to catalog standard:
      "Carol of the Bells in Gm"       → "Carol of the Bells (Key Gm).pdf"
      "Girl On Fire (Key E)"            → "Girl On Fire (Key E).pdf"
      "Beaches_Beabadoobee_Key_Dm"      → "Beaches Beabadoobee (Key Dm).docx"
      "The Beatles - Blackbird (in E)"  → "The Beatles - Blackbird (Key E).docx"
    """
    # Extract key from _Key_X underscore pattern first
    key = ""
    um = _KEY_UNDERSCORE_RE.search(stem)
    if um:
        key = um.group(1).replace("_", "").replace("flat", "b").replace("sharp", "#").replace("Flat", "b").replace("Sharp", "#").replace("Sharpm", "#m")
        stem = _normalize_underscores(stem)

    # Already has a (Key X), (X), or (in X) paren
    if not key:
        m = _KEY_PAREN_RE.search(stem)
        if m:
            key = m.group(1)
            stem = _KEY_PAREN_RE.sub("", stem).strip()

    # Has "in Gm" suffix → convert
    if not key:
        m = _KEY_IN_RE.search(stem)
        if m:
            key = m.group(1)
            stem = _KEY_IN_RE.sub("", stem).strip()

    if key:
        return f"{stem} (Key {key}){ext}", key
    return f"{stem}{ext}", ""


# ---------------------------------------------------------------------------
# Filename parser — artist/title split (same as backfill_local_sheet_music.py)
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(r"^(.+?) - (.+?)(?:\s*\((.+?)\))?$")
_TYLER_ARTIST = "Tyler James Drake"

# Known Tyler originals — root-level Drive files that are originals, not covers
_TYLER_ORIGINALS = {
    "fly away", "bitten", "marigolds", "lighthouse", "invisible",
    "same thing", "you already know", "abbey's song", "abbeys song",
    "what i do", "let it fade",
}


def _parse_filename(stem: str) -> tuple[str, str, str]:
    """Return (artist, title, key_descriptor) from a standardized stem."""
    m = _FILENAME_RE.match(stem)
    if m:
        part1 = m.group(1)
        part2 = m.group(2)
        descriptor = m.group(3) or ""
        if part1 == _TYLER_ARTIST:
            return part1, part2, descriptor
        return part2, part1, descriptor
    return "", stem, ""


# ---------------------------------------------------------------------------
# Category inference from Drive folder path
# ---------------------------------------------------------------------------


def _infer_category(folder_path: str, title: str = "") -> str:
    """Infer sheet music category from the Drive folder path or title."""
    lower = folder_path.lower()
    if "originals" in lower:
        return "originals"
    if "templates" in lower:
        return "templates"
    # Check known Tyler originals by title even if in root/misc folder
    if title.lower().strip() in _TYLER_ORIGINALS:
        return "originals"
    # Charts, recital folders, root files → covers
    return "covers"


# ---------------------------------------------------------------------------
# Local destination path
# ---------------------------------------------------------------------------

_SHEET_MUSIC_ROOT = _MUSIC_ROOT / "catalog" / "sheet_music"


def _dest_path(category: str, filename: str, file_id: str = "") -> Path:
    """Return a collision-safe local Path for this file.

    If the target filename already exists (different Drive file), appends
    the first 8 chars of the file_id to disambiguate.
    """
    base = _SHEET_MUSIC_ROOT / category / filename
    if not base.exists() or not file_id:
        return base
    stem = Path(filename).stem
    ext = Path(filename).suffix
    return _SHEET_MUSIC_ROOT / category / f"{stem} [{file_id[:8]}]{ext}"


# ---------------------------------------------------------------------------
# Main ingest function
# ---------------------------------------------------------------------------


def ingest(conn=None, dry_run: bool = False) -> tuple[int, int, int]:
    """Scan Google Drive, download files, insert metadata into sheet_music.

    Downloads PDF/DOCX files directly; exports Google Docs as .docx.
    Filenames are auto-standardized (key extracted from "in Gm" patterns).

    Args:
        conn: Optional SQLite connection (plain sqlite3, for tests).
              If None, uses get_connection() (encrypted heartmusic.db).
        dry_run: If True, list files and print planned actions without
                 downloading or writing to DB.

    Returns:
        Tuple of (inserted, skipped, total_on_drive).
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    client = GDriveClient()
    print(f"[ingest_sheet_music_gdrive] Scanning Drive for {_SCAN_MIMES} …")
    drive_files = client.list_files(mime_types=_SCAN_MIMES)
    total = len(drive_files)
    print(f"[ingest_sheet_music_gdrive] Found {total} files on Drive.")

    inserted = 0
    skipped = 0

    try:
        for f in drive_files:
            gdrive_file_id = f["id"]
            mime = f["mimeType"]

            # Idempotency check — skip if already in DB
            existing = conn.execute(
                "SELECT id FROM sheet_music WHERE gdrive_file_id = ?",
                (gdrive_file_id,),
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # Determine output extension
            if mime == _GDOC_MIME:
                out_ext = _GDOC_EXPORT_EXT
            else:
                out_ext = Path(f["name"]).suffix.lower() or ".pdf"

            # Standardize filename (extract key from Drive naming)
            raw_stem = Path(f["name"]).stem
            std_name, key_descriptor = _standardize_name(raw_stem, out_ext)

            folder_path = client.get_folder_path(
                gdrive_file_id, f.get("parents", [])
            )
            artist, title, _ = _parse_filename(Path(std_name).stem)
            category = _infer_category(folder_path, title)
            file_size = int(f.get("size", 0) or 0)
            modified_at = f.get("modifiedTime", "")

            dest = _dest_path(category, std_name, gdrive_file_id)
            local_path = str(dest.relative_to(_MUSIC_ROOT)).replace("\\", "/")

            if dry_run:
                status = "(exists)" if dest.exists() else ""
                print(f"  DRY-RUN  {folder_path}/{f['name']}  →  {local_path} {status}")
                inserted += 1
                continue

            # Download / export (skip if file already present locally)
            if dest.exists():
                print(f"  = EXISTS  {dest.name}  (skipping download)")
            elif mime == _GDOC_MIME:
                client.export_file(gdrive_file_id, dest, _GDOC_EXPORT_MIME)
            else:
                client.download_file(gdrive_file_id, dest)

            conn.execute(
                """
                INSERT INTO sheet_music
                    (source, name, file_ext, category, artist, title,
                     key_descriptor, local_path, gdrive_file_id,
                     gdrive_folder_path, file_size_bytes,
                     gdrive_modified_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "gdrive",
                    std_name,
                    out_ext,
                    category,
                    artist,
                    title,
                    key_descriptor,
                    local_path,
                    gdrive_file_id,
                    folder_path,
                    file_size,
                    modified_at,
                    None,  # deleted_at
                ),
            )
            print(f"  + {std_name}  [{category}]")
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
    import argparse

    parser = argparse.ArgumentParser(description="Ingest sheet music from Google Drive")
    parser.add_argument("--dry-run", action="store_true", help="List actions without downloading")
    args = parser.parse_args()
    ingest(dry_run=args.dry_run)

