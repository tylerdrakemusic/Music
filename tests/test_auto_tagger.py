"""Tests for BPM / Key auto-tagger.

Covers:
- check_integrity (mocked librosa + mutagen)
- detect() dispatch: id3 tag present → uses tag; id3 absent → librosa
- catalog_songs overwrite policy (manual entries skipped)
- _write_catalog_songs with dry_run=True makes no DB writes

FR-20260526-bpm-key-auto-tagger
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup: add repo root (for src.*) and tools/ (for auto_tagger)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
for _p in [str(_REPO_ROOT / "src"), str(_TOOLS_DIR), str(_REPO_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from services.audio_tagger import check_integrity, detect  # noqa: E402
from auto_tagger import _write_catalog_songs, _write_tracks  # noqa: E402

# Path constants — str(Path(...)) normalizes separators for the current OS
# so that DB inserts and scan_results lookups always match.
_TEST_FILE = str(Path("/music/test.mp3"))
_TEST_FILE2 = str(Path("/music/other.mp3"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_catalog_db(
    source_file: str = _TEST_FILE,
    bpm: int | None = None,
    key_sig: str | None = None,
    bpm_source: str | None = None,
) -> sqlite3.Connection:
    """Return an in-memory sqlite3 connection with a single catalog_songs row."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE catalog_songs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL DEFAULT 'Test',
            artist      TEXT NOT NULL DEFAULT 'Artist',
            key_sig     TEXT,
            bpm         INTEGER,
            bpm_source  TEXT,
            source_file TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO catalog_songs (title, artist, bpm, key_sig, bpm_source, source_file) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("Test Song", "Test Artist", bpm, key_sig, bpm_source, source_file),
    )
    conn.commit()
    return conn


def _make_tracks_db(
    file_path: str = _TEST_FILE,
    track_id: int = 1,
) -> sqlite3.Connection:
    """Return an in-memory sqlite3 connection with tracks + recordings rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE tracks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL DEFAULT 'Track',
            key_signature TEXT,
            tempo_bpm     REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE recordings (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id  INTEGER NOT NULL REFERENCES tracks(id),
            file_path TEXT
        )
        """
    )
    conn.execute("INSERT INTO tracks (id, title) VALUES (?, ?)", (track_id, "Track"))
    conn.execute(
        "INSERT INTO recordings (track_id, file_path) VALUES (?, ?)",
        (track_id, file_path),
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# check_integrity tests
# ---------------------------------------------------------------------------


class TestCheckIntegrity:
    def test_passes_when_both_succeed(self):
        with patch("librosa.load"), patch("mutagen.File"):
            assert check_integrity("fake.mp3") is True

    def test_fails_when_librosa_raises(self):
        with patch("librosa.load", side_effect=Exception("corrupt audio")):
            assert check_integrity("fake.mp3") is False

    def test_fails_when_mutagen_raises(self):
        with patch("librosa.load"), patch(
            "mutagen.File", side_effect=Exception("not a media file")
        ):
            assert check_integrity("fake.mp3") is False

    def test_passes_with_path_object(self):
        with patch("librosa.load"), patch("mutagen.File"):
            assert check_integrity(Path("fake.mp3")) is True


# ---------------------------------------------------------------------------
# detect() dispatch tests
# ---------------------------------------------------------------------------


class FakeFrame:
    """Minimal stand-in for a mutagen ID3 text frame."""

    def __init__(self, value: str) -> None:
        self._value = value

    def __str__(self) -> str:
        return self._value


class TestDetectDispatch:
    """Verify that detect() uses id3 tags when present and librosa when absent."""

    def _mp3_mock(self, tbpm: str | None = None, tkey: str | None = None):
        """Build a mock mutagen MP3 object."""
        tags = MagicMock()
        tag_map: dict = {}
        if tbpm is not None:
            tag_map["TBPM"] = FakeFrame(tbpm)
        if tkey is not None:
            tag_map["TKEY"] = FakeFrame(tkey)
        tags.get.side_effect = lambda k: tag_map.get(k)
        audio = MagicMock()
        audio.tags = tags
        return audio

    # --- ID3 tag present ---

    def test_bpm_from_id3_tag(self):
        mock_audio = self._mp3_mock(tbpm="120")
        with patch("mutagen.mp3.MP3", return_value=mock_audio):
            result = detect(Path("fake.mp3"))
        assert result["bpm"] == 120
        assert result["bpm_source"] == "id3_tag"

    def test_key_from_tkey_tag(self):
        mock_audio = self._mp3_mock(tkey="Am")
        with patch("mutagen.mp3.MP3", return_value=mock_audio):
            result = detect(Path("fake.mp3"))
        assert result["key"] == "Am"
        assert result["key_source"] == "id3_tag"

    def test_both_from_id3_no_librosa_called(self):
        """When both BPM and key are in tags, librosa.load must NOT be called."""
        mock_audio = self._mp3_mock(tbpm="128", tkey="C#m")
        with patch("mutagen.mp3.MP3", return_value=mock_audio), patch(
            "librosa.load"
        ) as mock_load:
            result = detect(Path("fake.mp3"))
        assert result["bpm"] == 128
        assert result["bpm_source"] == "id3_tag"
        assert result["key"] == "C#m"
        assert result["key_source"] == "id3_tag"
        mock_load.assert_not_called()

    # --- No ID3 tag → librosa ---

    def test_bpm_from_librosa_when_no_tag(self):
        import numpy as np

        mock_audio = self._mp3_mock()  # no tags
        with (
            patch("mutagen.mp3.MP3", return_value=mock_audio),
            patch("librosa.load", return_value=(np.zeros(22050), 22050)),
            patch(
                "librosa.beat.beat_track",
                return_value=(np.array([96.0]), np.array([])),
            ),
            patch(
                "librosa.feature.chroma_cqt",
                return_value=np.ones((12, 100)),
            ),
        ):
            result = detect(Path("fake.mp3"))

        assert result["bpm"] == 96
        assert result["bpm_source"] == "librosa"

    def test_key_from_librosa_chroma_when_no_tag(self):
        import numpy as np

        # Chroma vector strongly weighted on C → should yield "C major"
        chroma = np.zeros((12, 100))
        chroma[0, :] = 10.0  # pitch class 0 = C dominant

        mock_audio = self._mp3_mock()
        with (
            patch("mutagen.mp3.MP3", return_value=mock_audio),
            patch("librosa.load", return_value=(np.zeros(22050), 22050)),
            patch(
                "librosa.beat.beat_track",
                return_value=(np.array([120.0]), np.array([])),
            ),
            patch("librosa.feature.chroma_cqt", return_value=chroma),
        ):
            result = detect(Path("fake.mp3"))

        assert result["key_source"] == "librosa_chroma"
        assert result["key"] is not None

    def test_both_unknown_when_librosa_fails(self):
        mock_audio = self._mp3_mock()  # no tags
        with (
            patch("mutagen.mp3.MP3", return_value=mock_audio),
            patch("librosa.load", side_effect=Exception("no audio")),
        ):
            result = detect(Path("fake.mp3"))

        assert result["bpm"] is None
        assert result["key"] is None
        assert result["bpm_source"] == "unknown"
        assert result["key_source"] == "unknown"

    def test_invalid_tbpm_tag_falls_back_to_librosa(self):
        """A non-numeric TBPM value must not crash; librosa should be used instead."""
        import numpy as np

        mock_audio = self._mp3_mock(tbpm="N/A")  # invalid BPM
        with (
            patch("mutagen.mp3.MP3", return_value=mock_audio),
            patch("librosa.load", return_value=(np.zeros(22050), 22050)),
            patch(
                "librosa.beat.beat_track",
                return_value=(np.array([110.0]), np.array([])),
            ),
            patch("librosa.feature.chroma_cqt", return_value=np.ones((12, 50))),
        ):
            result = detect(Path("fake.mp3"))

        assert result["bpm"] == 110
        assert result["bpm_source"] == "librosa"


# ---------------------------------------------------------------------------
# Overwrite policy tests
# ---------------------------------------------------------------------------


class TestOverwritePolicy:
    def test_manual_rows_are_skipped(self):
        """catalog_songs rows with bpm_source='manual' must not be overwritten."""
        conn = _make_catalog_db(bpm=130, bpm_source="manual")
        scan_results = [
            {
                "path": Path(_TEST_FILE),
                "bpm": 99,
                "key": "F major",
                "db_updated": False,
                "id3_written": False,
                "error": None,
            }
        ]
        stats = _write_catalog_songs(scan_results, conn, dry_run=False)

        assert stats["skipped_manual"] == 1
        assert stats["updated"] == 0
        row = conn.execute(
            "SELECT bpm, bpm_source FROM catalog_songs"
        ).fetchone()
        assert row[0] == 130  # unchanged
        assert row[1] == "manual"  # unchanged

    def test_non_manual_rows_are_updated(self):
        """catalog_songs rows with bpm_source != 'manual' should be updated."""
        conn = _make_catalog_db(bpm=None, bpm_source="unknown")
        scan_results = [
            {
                "path": Path(_TEST_FILE),
                "bpm": 120,
                "key": "G major",
                "db_updated": False,
                "id3_written": False,
                "error": None,
            }
        ]
        stats = _write_catalog_songs(scan_results, conn, dry_run=False)

        assert stats["updated"] == 1
        assert stats["skipped_manual"] == 0
        row = conn.execute(
            "SELECT bpm, key_sig, bpm_source FROM catalog_songs"
        ).fetchone()
        assert row[0] == 120
        assert row[1] == "G major"
        assert row[2] == "auto_tagger"

    def test_no_match_on_source_file_does_nothing(self):
        """Rows without a matching source_file should not be touched."""
        conn = _make_catalog_db(source_file=_TEST_FILE2, bpm=None)
        scan_results = [
            {
                "path": Path(_TEST_FILE),
                "bpm": 120,
                "key": "C major",
                "db_updated": False,
                "id3_written": False,
                "error": None,
            }
        ]
        stats = _write_catalog_songs(scan_results, conn, dry_run=False)
        assert stats["updated"] == 0

    def test_tracks_updated_via_recordings_join(self):
        """_write_tracks updates tracks.tempo_bpm and key_signature via recordings join."""
        conn = _make_tracks_db(file_path=_TEST_FILE, track_id=1)
        scan_results = [
            {
                "path": Path(_TEST_FILE),
                "bpm": 140,
                "key": "E minor",
                "db_updated": False,
                "id3_written": False,
                "error": None,
            }
        ]
        stats = _write_tracks(scan_results, conn, dry_run=False)

        assert stats["updated"] == 1
        row = conn.execute(
            "SELECT tempo_bpm, key_signature FROM tracks WHERE id = 1"
        ).fetchone()
        assert row[0] == pytest.approx(140.0)
        assert row[1] == "E minor"


# ---------------------------------------------------------------------------
# dry_run=True makes no DB writes
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_catalog_songs_no_writes(self):
        """_write_catalog_songs with dry_run=True must return zeros and not write."""
        conn = _make_catalog_db(bpm=None, bpm_source=None)
        scan_results = [
            {
                "path": Path(_TEST_FILE),
                "bpm": 120,
                "key": "D major",
                "db_updated": False,
            }
        ]
        stats = _write_catalog_songs(scan_results, conn, dry_run=True)

        assert stats["updated"] == 0
        assert stats["skipped_manual"] == 0
        row = conn.execute("SELECT bpm FROM catalog_songs").fetchone()
        assert row[0] is None  # not modified

    def test_dry_run_tracks_no_writes(self):
        """_write_tracks with dry_run=True must return zeros and not write."""
        conn = _make_tracks_db()
        scan_results = [
            {
                "path": Path(_TEST_FILE),
                "bpm": 100,
                "key": "A major",
                "db_updated": False,
            }
        ]
        stats = _write_tracks(scan_results, conn, dry_run=True)

        assert stats["updated"] == 0
        row = conn.execute("SELECT tempo_bpm FROM tracks WHERE id = 1").fetchone()
        assert row[0] is None  # not modified

    def test_dry_run_does_not_mark_db_updated(self):
        """dry_run must not set row['db_updated'] = True."""
        conn = _make_catalog_db(bpm=None)
        row = {"path": Path(_TEST_FILE), "bpm": 120, "key": "C", "db_updated": False}
        _write_catalog_songs([row], conn, dry_run=True)
        assert row["db_updated"] is False
