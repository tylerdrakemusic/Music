"""
Tests for tools/ingest_artwork.py — FR-20260427-originals-artwork-ingest.

Covers:
  1. Canonical name generation
  2. DB column migration (idempotent)
  3. Copy + DB update in apply mode
  4. Dry-run produces no side effects
  5. SKIP_EXACT_DUP detection
  6. MANUAL_REVIEW for unmatched file
  7. Path traversal safety: file outside allowed roots → not copied
  8. APIC embed (mock mutagen)
"""
from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
_spec = importlib.util.spec_from_file_location(
    "ingest_artwork", TOOLS_DIR / "ingest_artwork.py"
)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)  # type: ignore[union-attr]

# Short aliases
canonical_name          = ingest.canonical_name
plan_actions            = ingest.plan_actions
add_artwork_column      = ingest.add_artwork_column_if_missing
load_originals          = ingest.load_originals
embed_cover             = ingest.embed_cover


# ---------------------------------------------------------------------------
# In-memory DB helper
# ---------------------------------------------------------------------------

def _make_db(songs: list[tuple] | None = None) -> sqlite3.Connection:
    """Create an in-memory SQLite DB with a minimal catalog_songs schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE catalog_songs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            artist      TEXT NOT NULL,
            source_file TEXT,
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    if songs:
        conn.executemany(
            "INSERT INTO catalog_songs (title, artist, source_file) VALUES (?,?,?)",
            songs,
        )
        conn.commit()
    return conn


def _tiny_jpeg() -> bytes:
    """Minimal valid-ish JPEG bytes."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )


# ---------------------------------------------------------------------------
# AC1 / AC3 — canonical name generation
# ---------------------------------------------------------------------------

class TestCanonicalName:
    def test_jpg(self) -> None:
        assert canonical_name("Bloom", ".jpg") == "Bloom - Tyler James Drake.jpg"

    def test_png(self) -> None:
        assert canonical_name("Get Out", ".png") == "Get Out - Tyler James Drake.png"

    def test_webp(self) -> None:
        assert canonical_name("What I Do", ".webp") == "What I Do - Tyler James Drake.webp"

    def test_preserves_title_case(self) -> None:
        assert canonical_name("Is It Real", ".jpg") == "Is It Real - Tyler James Drake.jpg"

    def test_ext_must_include_dot(self) -> None:
        # ext without leading dot should still produce a valid (though unusual) name
        result = canonical_name("Bloom", "jpg")
        assert "Tyler James Drake" in result


# ---------------------------------------------------------------------------
# AC2 — DB column migration (idempotent)
# ---------------------------------------------------------------------------

class TestArtworkColumnMigration:
    def test_adds_column(self) -> None:
        conn = _make_db()
        cur = conn.execute("PRAGMA table_info(catalog_songs)")
        cols = {row[1] for row in cur.fetchall()}
        assert "artwork_path" not in cols

        add_artwork_column(conn)

        cur = conn.execute("PRAGMA table_info(catalog_songs)")
        cols = {row[1] for row in cur.fetchall()}
        assert "artwork_path" in cols

    def test_idempotent(self) -> None:
        """Running migration twice must not raise."""
        conn = _make_db()
        add_artwork_column(conn)
        add_artwork_column(conn)  # second call must be a no-op

    def test_artwork_path_nullable(self) -> None:
        conn = _make_db([("Bloom", "Tyler James Drake", None)])
        add_artwork_column(conn)
        row = conn.execute("SELECT artwork_path FROM catalog_songs").fetchone()
        assert row[0] is None


# ---------------------------------------------------------------------------
# AC3 — plan_actions: COPY_NEW, dry-run, apply
# ---------------------------------------------------------------------------

class TestCopyNewDryRun:
    def test_dry_run_no_files_copied(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        img = tmp / "bloom song art.jpg"
        img.write_bytes(_tiny_jpeg())

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))

        copy_actions = [a for a in actions if a.action == "COPY_NEW"]
        assert len(copy_actions) == 1
        assert copy_actions[0].dest_name == "Bloom - Tyler James Drake.jpg"

        # No files should have been copied (plan_actions is pure)
        assert not any(f.is_file() for f in originals.iterdir())

    def test_apply_copies_file_and_updates_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        img = tmp / "bloom song art.jpg"
        img.write_bytes(_tiny_jpeg())

        conn = _make_db([("Bloom", "Tyler James Drake", None)])
        add_artwork_column(conn)

        # Patch ORIGINALS_DIR and PROJECT_ROOT inside the module
        monkeypatch.setattr(ingest, "ORIGINALS_DIR", originals)
        monkeypatch.setattr(ingest, "PROJECT_ROOT", tmp_path)

        ingest.main(tmp_dir=tmp, apply=True, get_conn=lambda: conn)

        # File should be copied
        dest = originals / "Bloom - Tyler James Drake.jpg"
        assert dest.exists()

        # DB should be updated — create a new connection to the same in-memory DB
        # (conn is still open; main() no longer closes it)
        row = conn.execute(
            "SELECT artwork_path FROM catalog_songs WHERE title = 'Bloom'"
        ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert "Bloom - Tyler James Drake.jpg" in row[0]

    def test_dry_run_does_not_copy(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        img = tmp / "bloom song art.jpg"
        img.write_bytes(_tiny_jpeg())

        conn = _make_db([("Bloom", "Tyler James Drake", None)])
        add_artwork_column(conn)

        monkeypatch.setattr(ingest, "ORIGINALS_DIR", originals)
        monkeypatch.setattr(ingest, "PROJECT_ROOT", tmp_path)

        ingest.main(tmp_dir=tmp, apply=False, get_conn=lambda: conn)

        dest = originals / "Bloom - Tyler James Drake.jpg"
        assert not dest.exists()

        # DB should be unchanged (conn still open after dry-run)
        row = conn.execute(
            "SELECT artwork_path FROM catalog_songs WHERE title = 'Bloom'"
        ).fetchone()
        assert row[0] is None


# ---------------------------------------------------------------------------
# AC3 — SKIP_EXACT_DUP
# ---------------------------------------------------------------------------

class TestSkipExactDup:
    def test_exact_dup_detected(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        data = _tiny_jpeg()

        # Pre-existing file in originals with same bytes.
        existing = originals / "Bloom - Tyler James Drake.jpg"
        existing.write_bytes(data)

        # Incoming file with same bytes but different name.
        incoming = tmp / "bloom song art.jpg"
        incoming.write_bytes(data)

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))

        assert len(actions) == 1
        assert actions[0].action == "SKIP_EXACT_DUP"

    def test_different_bytes_not_skipped(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        existing = originals / "Bloom - Tyler James Drake.jpg"
        existing.write_bytes(b"old image bytes")

        incoming = tmp / "bloom song art.jpg"
        incoming.write_bytes(_tiny_jpeg())  # different bytes

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))

        assert len(actions) == 1
        assert actions[0].action != "SKIP_EXACT_DUP"


# ---------------------------------------------------------------------------
# AC5 — MANUAL_REVIEW for unmatched file
# ---------------------------------------------------------------------------

class TestManualReview:
    def test_no_catalog_match(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        img = tmp / "brand image 1.jpg"
        img.write_bytes(_tiny_jpeg())

        songs: list[dict] = []  # empty catalog
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))

        assert len(actions) == 1
        assert actions[0].action == "MANUAL_REVIEW"
        assert actions[0].src.name == "brand image 1.jpg"

    def test_no_catalog_rows_all_manual(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        for name in ("img1.jpg", "img2.png"):
            (tmp / name).write_bytes(_tiny_jpeg())

        actions = plan_actions(tmp, originals, [], allowed_roots=(tmp.resolve(),))
        assert all(a.action == "MANUAL_REVIEW" for a in actions)


# ---------------------------------------------------------------------------
# AC6 — Path traversal safety
# ---------------------------------------------------------------------------

class TestPathTraversalSafety:
    def test_file_outside_allowed_root_not_included(self, tmp_path: Path) -> None:
        # Allowed root is `allowed/`; tmp_dir is `outside/`.
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        evil = outside / "bloom song art.jpg"
        evil.write_bytes(_tiny_jpeg())

        originals = tmp_path / "originals"
        originals.mkdir()

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]

        # Pass outside/ as tmp_dir but restrict allowed_roots to allowed/
        actions = plan_actions(
            tmp_dir=outside,
            originals_dir=originals,
            originals=songs,
            allowed_roots=(allowed.resolve(),),
        )

        # File in outside/ is not under allowed/ → must not appear as COPY_NEW
        copy_actions = [a for a in actions if a.action == "COPY_NEW"]
        assert len(copy_actions) == 0

    def test_file_inside_allowed_root_is_included(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        img = tmp / "bloom song art.jpg"
        img.write_bytes(_tiny_jpeg())

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))

        assert any(a.action == "COPY_NEW" for a in actions)


# ---------------------------------------------------------------------------
# AC4 — APIC embed (mock mutagen)
# ---------------------------------------------------------------------------

class TestEmbedCover:
    def test_returns_skipped_no_file_when_audio_missing(self, tmp_path: Path) -> None:
        audio = tmp_path / "nonexistent.mp3"
        image = tmp_path / "art.jpg"
        image.write_bytes(_tiny_jpeg())

        result = embed_cover(audio, image)
        assert result == "SKIPPED_NO_FILE"

    def test_returns_skipped_no_mutagen_when_not_installed(
        self, tmp_path: Path
    ) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3 data")
        image = tmp_path / "art.jpg"
        image.write_bytes(_tiny_jpeg())

        with patch.dict(sys.modules, {"mutagen": None}):
            result = embed_cover(audio, image)
        assert result == "SKIPPED_NO_MUTAGEN"

    def test_mp3_embed_calls_id3_save(self, tmp_path: Path) -> None:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"fake mp3 data")
        image = tmp_path / "art.jpg"
        image.write_bytes(_tiny_jpeg())

        mock_tags = MagicMock()

        mock_id3_cls  = MagicMock(return_value=mock_tags)
        mock_apic_cls = MagicMock()
        mock_id3_err  = Exception

        mock_mutagen = MagicMock()
        mock_id3_mod = MagicMock()
        mock_id3_mod.ID3   = mock_id3_cls
        mock_id3_mod.APIC  = mock_apic_cls
        mock_id3_mod.error = mock_id3_err

        with patch.dict(sys.modules, {
            "mutagen":    mock_mutagen,
            "mutagen.id3": mock_id3_mod,
        }):
            result = embed_cover(audio, image)

        assert result == "EMBEDDED"
        mock_tags.save.assert_called_once_with(str(audio))

    def test_skipped_format_for_unsupported_ext(self, tmp_path: Path) -> None:
        audio = tmp_path / "song.ogg"
        audio.write_bytes(b"fake ogg data")
        image = tmp_path / "art.jpg"
        image.write_bytes(_tiny_jpeg())

        mock_mutagen = MagicMock()
        with patch.dict(sys.modules, {"mutagen": mock_mutagen}):
            result = embed_cover(audio, image)
        assert result == "SKIPPED_FORMAT"

    def test_non_image_exts_ignored_in_plan(self, tmp_path: Path) -> None:
        """Files with non-image extensions are not ingested."""
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        (tmp / "bloom.avif").write_bytes(b"avif data")
        (tmp / "bloom.pdf").write_bytes(b"pdf data")

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# AC3 — SKIP_SEMANTIC (same canonical name already exists)
# ---------------------------------------------------------------------------

class TestSkipSemantic:
    def test_semantic_dup_when_canonical_name_exists(self, tmp_path: Path) -> None:
        tmp = tmp_path / "tmp"
        tmp.mkdir()
        originals = tmp_path / "originals"
        originals.mkdir()

        # Pre-existing canonical file in originals (different bytes, same name).
        existing = originals / "Bloom - Tyler James Drake.jpg"
        existing.write_bytes(b"different bytes for existing art")

        # Incoming file.
        incoming = tmp / "bloom song art.jpg"
        incoming.write_bytes(_tiny_jpeg())

        songs = [{"id": 1, "title": "Bloom", "source_file": None, "artwork_path": None}]
        actions = plan_actions(tmp, originals, songs, allowed_roots=(tmp.resolve(),))

        assert len(actions) == 1
        assert actions[0].action == "SKIP_SEMANTIC"
