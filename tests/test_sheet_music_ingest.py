"""Tests for sheet music DB migration + local backfill — FR-20260530-gdrive-integration.

TDD: written before implementation.  Fails on first run (ImportError),
passes after production code is created.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow imports from the worktree's src/ (for scripts)
_WORKTREE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WORKTREE_ROOT / "src"))

# ---------------------------------------------------------------------------
# Resolve ⊕Workspace src/ — try production path first, fall back to the peer
# worktree (same branch name) so tests work both pre-merge and post-merge.
# ---------------------------------------------------------------------------
_BRANCH_NAME = _WORKTREE_ROOT.name  # e.g. "fr-gdrive-integration"
_WORKSPACE_SRC_CANDIDATES = [
    Path(r"f:\⊕Workspace\src"),  # post-merge / production
    Path(r"f:\⊕Workspace\.worktrees") / _BRANCH_NAME / "src",  # pre-merge worktree
]
_WORKSPACE_SRC = next(
    (p for p in _WORKSPACE_SRC_CANDIDATES if (p / "integrations" / "gdrive").exists()),
    _WORKSPACE_SRC_CANDIDATES[0],  # fallback: will get ImportError if neither exists
)
if str(_WORKSPACE_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_SRC))

# ---------------------------------------------------------------------------
# Regex parser (same pattern used by both backfill & gdrive ingest scripts)
# Defined here so tests are self-contained without importing prod code first.
# ---------------------------------------------------------------------------

FILENAME_PATTERN = re.compile(r"^(.+?) - (.+?)(?:\s*\((.+?)\))?$")

# The catalog uses two conventions:
#   Originals:  "Tyler James Drake - Song Title (Key X)"
#   Covers:     "Song Title - Artist (Descriptor)"
# Detect by checking whether the part before " - " is the Tyler artist name.
_TYLER_ARTIST = "Tyler James Drake"


def _parse_filename(stem: str) -> tuple[str, str, str]:
    """Returns (artist, title, key_descriptor) from a filename stem.

    Handles both catalog naming conventions:
    - TJD originals: "Tyler James Drake - Title (Descriptor)" → group1=artist
    - Covers: "Title - Artist (Descriptor)" → group2=artist
    """
    m = FILENAME_PATTERN.match(stem)
    if m:
        part1 = m.group(1)
        part2 = m.group(2)
        descriptor = m.group(3) or ""
        if part1 == _TYLER_ARTIST:
            return part1, part2, descriptor  # originals: artist first
        return part2, part1, descriptor  # covers: title first → swap
    return "", stem, ""


# ---------------------------------------------------------------------------
# test_filename_parser
# ---------------------------------------------------------------------------


class TestFilenameParser:
    """Verify the shared filename parsing regex against real catalog names."""

    def test_cover_with_key(self):
        artist, title, key = _parse_filename("Ain't It Fun - Paramore (Key E)")
        assert artist == "Paramore"
        assert title == "Ain't It Fun"
        assert key == "Key E"

    def test_original_no_key(self):
        artist, title, key = _parse_filename("Tyler James Drake - Fly Away")
        assert artist == "Tyler James Drake"
        assert title == "Fly Away"
        assert key == ""

    def test_cover_no_key(self):
        artist, title, key = _parse_filename("Dreams - Fleetwood Mac")
        assert artist == "Fleetwood Mac"
        assert title == "Dreams"
        assert key == ""

    def test_cover_chords_descriptor(self):
        artist, title, key = _parse_filename("Girl On Fire - Alicia Keys")
        assert artist == "Alicia Keys"
        assert title == "Girl On Fire"
        assert key == ""

    def test_original_with_key_minor(self):
        artist, title, key = _parse_filename(
            "Tyler James Drake - Invisible (Key A Minor)"
        )
        assert artist == "Tyler James Drake"
        assert title == "Invisible"
        assert key == "Key A Minor"

    def test_no_dash_fallback(self):
        """Files without the 'Artist - Title' pattern fall back to title-only."""
        artist, title, key = _parse_filename("SomeUntitledFile")
        assert artist == ""
        assert title == "SomeUntitledFile"
        assert key == ""


# ---------------------------------------------------------------------------
# Helpers: create a minimal in-memory SQLite DB with the sheet_music table
# ---------------------------------------------------------------------------


def _make_test_db(path: str) -> sqlite3.Connection:
    """Create a plain SQLite DB (not encrypted) for testing."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT,
            category TEXT,
            artist_id INTEGER,
            track_id INTEGER,
            album_id INTEGER,
            file_name TEXT,
            file_ext TEXT,
            file_size_bytes INTEGER,
            indexed_at TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS sheet_music (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL CHECK(source IN ('local','gdrive')),
            name TEXT NOT NULL,
            file_ext TEXT,
            category TEXT,
            artist TEXT,
            title TEXT,
            key_descriptor TEXT,
            local_path TEXT,
            gdrive_file_id TEXT UNIQUE,
            gdrive_folder_path TEXT,
            file_size_bytes INTEGER,
            gdrive_modified_at TEXT,
            ingested_at TEXT DEFAULT (datetime('now')),
            deleted_at TEXT,
            catalog_index_id INTEGER REFERENCES catalog_index(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sheet_music_source ON sheet_music(source);
        CREATE INDEX IF NOT EXISTS idx_sheet_music_gdrive_file_id ON sheet_music(gdrive_file_id);
        """
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# test_backfill_local_idempotent
# ---------------------------------------------------------------------------


def test_backfill_local_idempotent(tmp_path):
    """Running backfill twice on the same local files produces no duplicates."""
    from scripts.backfill_local_sheet_music import backfill  # noqa: PLC0415

    # Create a tiny fake sheet_music directory structure
    covers_dir = tmp_path / "catalog" / "sheet_music" / "covers"
    covers_dir.mkdir(parents=True)
    (covers_dir / "Paramore - Ain't It Fun (Key E).pdf").touch()
    (covers_dir / "Fleetwood Mac - Dreams.pdf").touch()

    originals_dir = tmp_path / "catalog" / "sheet_music" / "originals"
    originals_dir.mkdir(parents=True)
    (originals_dir / "Tyler James Drake - Fly Away.docx").touch()

    # Use a plain SQLite DB for the test (not encrypted)
    db_path = tmp_path / "test.db"
    conn = _make_test_db(str(db_path))
    conn.close()

    # First run
    backfill(sheet_music_root=tmp_path / "catalog" / "sheet_music", db_path=str(db_path))
    conn = sqlite3.connect(str(db_path))
    count_after_first = conn.execute("SELECT COUNT(*) FROM sheet_music").fetchone()[0]
    conn.close()

    # Second run — must be idempotent
    backfill(sheet_music_root=tmp_path / "catalog" / "sheet_music", db_path=str(db_path))
    conn = sqlite3.connect(str(db_path))
    count_after_second = conn.execute("SELECT COUNT(*) FROM sheet_music").fetchone()[0]
    conn.close()

    assert count_after_first == 3
    assert count_after_second == count_after_first, "Backfill must be idempotent"


# ---------------------------------------------------------------------------
# test_gdrive_client_missing_env_var (mirror of ⊕Workspace test)
# ---------------------------------------------------------------------------


def test_gdrive_client_missing_env_var():
    """GDriveClient() raises EnvironmentError when GDRIVE_SA_KEY is absent."""
    # _WORKSPACE_SRC already on sys.path (module-level setup above)
    if str(_WORKSPACE_SRC) not in sys.path:
        sys.path.insert(0, str(_WORKSPACE_SRC))

    env_without_key = {k: v for k, v in os.environ.items() if k != "GDRIVE_SA_KEY"}
    with patch.dict("os.environ", env_without_key, clear=True):
        from integrations.gdrive import GDriveClient  # noqa: PLC0415

        with pytest.raises(EnvironmentError, match="GDRIVE_SA_KEY"):
            GDriveClient()


# ---------------------------------------------------------------------------
# test_gdrive_client_list_files_mocked (mirror of ⊕Workspace test)
# ---------------------------------------------------------------------------

_FAKE_SA_KEY = base64.b64encode(
    json.dumps(
        {
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "abc",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "1234",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    ).encode()
).decode()


def test_gdrive_client_list_files_mocked():
    """list_files() aggregates pages and returns expected dicts (mirror test)."""
    if str(_WORKSPACE_SRC) not in sys.path:
        sys.path.insert(0, str(_WORKSPACE_SRC))

    page1 = {
        "files": [
            {
                "id": "file1",
                "name": "Song A.pdf",
                "mimeType": "application/pdf",
                "size": "12345",
                "modifiedTime": "2025-01-01T00:00:00.000Z",
                "parents": ["folder1"],
            }
        ],
        "nextPageToken": "tok_abc",
    }
    page2 = {
        "files": [
            {
                "id": "file2",
                "name": "Song B.pdf",
                "mimeType": "application/pdf",
                "size": "67890",
                "modifiedTime": "2025-02-01T00:00:00.000Z",
                "parents": ["folder2"],
            }
        ]
    }

    mock_list = MagicMock()
    mock_list.execute.side_effect = [page1, page2]
    mock_files = MagicMock()
    mock_files.list.return_value = mock_list
    mock_service = MagicMock()
    mock_service.files.return_value = mock_files

    with patch.dict("os.environ", {"GDRIVE_SA_KEY": _FAKE_SA_KEY}):
        with patch("integrations.gdrive.client._load_credentials", return_value=MagicMock()):
            with patch("integrations.gdrive.client.build_service", return_value=mock_service):
                from integrations.gdrive import GDriveClient  # noqa: PLC0415

                client = GDriveClient()
                results = client.list_files(mime_types=["application/pdf"])

    assert len(results) == 2
    assert results[0]["id"] == "file1"
    assert results[1]["id"] == "file2"
