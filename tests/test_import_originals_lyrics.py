"""Tests for tools/import_originals_lyrics.py — FR-20260502-import-originals-lyrics.

Covers:
  * parse_title_from_filename across the real originals filenames
  * fuzzy_match_track exact / fuzzy / unmatched
  * is_people_pdf positive + negative cases
  * extract_txt and extract_docx round-trip
  * extract_pdf via mocked pypdf
  * plan_lyrics: dry-run plan is correct + idempotency on re-run
  * apply_lyrics inserts and re-running with same paths inserts nothing
  * apply_moves relocates People*.pdf and is idempotent
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load module under test
# ---------------------------------------------------------------------------
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
_spec = importlib.util.spec_from_file_location(
    "import_originals_lyrics", TOOLS_DIR / "import_originals_lyrics.py"
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["import_originals_lyrics"] = mod
_spec.loader.exec_module(mod)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(track_titles: list[str]) -> sqlite3.Connection:
    """Mirror the live heartmusic.db lyrics+tracks shape (sans SQLCipher)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE lyrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            version_label TEXT DEFAULT 'v1',
            content TEXT,
            file_path TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    for t in track_titles:
        conn.execute("INSERT INTO tracks(title) VALUES (?)", (t,))
    conn.commit()
    return conn


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    import docx
    doc = docx.Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(str(path))


# ---------------------------------------------------------------------------
# parse_title_from_filename
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Abbeys Song_Tyler James Drake_Key_Bm.docx", "Abbeys Song"),
    ("Bitten_Tyler James Drake.docx", "Bitten"),
    ("Fly Away_Tyler James Drake_Key_C.docx", "Fly Away"),
    ("Fly Away_Tyler James Drake_LyricsOnly.docx", "Fly Away"),
    ("Lighthouse_Tyler James Drake_Key_Em.docx", "Lighthouse"),
    ("Lighthouse_Tyler James Drake_Key_Em_Lyrics_Only.docx", "Lighthouse"),
    ("Same Thing_Tyler James Drake.docx", "Same Thing"),
    ("You Already Know_Tyler James Drake_Key_E Major.docx", "You Already Know"),
    ("You Already Know - Rough 1-19-2026_Tyler James Drake_Key_E Major.docx",
     "You Already Know"),
    ("Fly Away.pdf", "Fly Away"),
    ("Same Thing.pdf", "Same Thing"),
])
def test_parse_title_from_filename(name, expected):
    assert mod.parse_title_from_filename(Path(name)) == expected


# ---------------------------------------------------------------------------
# is_people_pdf
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("People.pdf", True),
    ("People Bass.pdf", True),
    ("People Tab.pdf", True),
    ("people.pdf", True),
    ("Peoples.pdf", False),
    ("People's Song.pdf", False),
    ("Fly Away.pdf", False),
    ("People.docx", False),
])
def test_is_people_pdf(name, expected):
    assert mod.is_people_pdf(Path(name)) is expected


# ---------------------------------------------------------------------------
# fuzzy_match_track
# ---------------------------------------------------------------------------

def test_fuzzy_match_exact():
    tracks = [(1, "Abbey's Song"), (2, "Bitten"), (3, "Fly Away")]
    tid, title, ratio = mod.fuzzy_match_track("Abbey's Song", tracks)
    assert tid == 1 and title == "Abbey's Song" and ratio == 1.0


def test_fuzzy_match_compact_handles_apostrophe():
    """`Abbeys Song` (no apostrophe) should still match `Abbey's Song`."""
    tracks = [(1, "Abbey's Song"), (2, "Bitten")]
    tid, title, ratio = mod.fuzzy_match_track("Abbeys Song", tracks)
    assert tid == 1 and title == "Abbey's Song"
    assert ratio >= 0.9


def test_fuzzy_match_substring_threshold():
    """`Fly` (3 chars) should NOT match `Fly Away` — too short."""
    tracks = [(1, "Fly Away")]
    tid, _, _ = mod.fuzzy_match_track("Fly", tracks)
    assert tid is None


def test_fuzzy_match_no_track_returns_none():
    tracks = [(1, "Bitten")]
    tid, title, _ = mod.fuzzy_match_track("Whole", tracks)
    assert tid is None and title is None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extract_txt(tmp_path):
    p = tmp_path / "song.txt"
    p.write_text("verse 1\nverse 2\n", encoding="utf-8")
    assert mod.extract_txt(p) == "verse 1\nverse 2"


def test_extract_docx(tmp_path):
    p = tmp_path / "song.docx"
    _write_docx(p, ["First line", "Second line", "Third line"])
    out = mod.extract_docx(p)
    assert "First line" in out and "Third line" in out


def test_extract_pdf_uses_pypdf(tmp_path):
    p = tmp_path / "song.pdf"
    p.write_bytes(b"%PDF-FAKE")  # content not actually parsed; pypdf is mocked
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "page text"
    fake_reader = MagicMock(pages=[fake_page, fake_page])
    with patch.object(mod, "extract_pdf", wraps=mod.extract_pdf):
        with patch("pypdf.PdfReader", return_value=fake_reader) as ctor:
            out = mod.extract_pdf(p)
    ctor.assert_called_once()
    assert "page text" in out


# ---------------------------------------------------------------------------
# plan_lyrics + dry-run / apply / idempotency
# ---------------------------------------------------------------------------

def _setup_filesystem(tmp_path: Path) -> tuple[Path, Path, Path]:
    originals = tmp_path / "originals"
    covers    = tmp_path / "covers"
    lyrics    = tmp_path / "lyrics"
    originals.mkdir()
    lyrics.mkdir()
    # DOCX files (one matched, one with disambiguation pair)
    _write_docx(originals / "Abbeys Song_Tyler James Drake_Key_Bm.docx",
                ["Abbey verse 1", "chorus"])
    _write_docx(originals / "Lighthouse_Tyler James Drake_Key_Em.docx",
                ["Light verse"])
    _write_docx(originals / "Lighthouse_Tyler James Drake_Key_Em_Lyrics_Only.docx",
                ["Light lyrics-only"])
    # People PDFs (must move, not import)
    (originals / "People.pdf").write_bytes(b"%PDF-")
    (originals / "People Bass.pdf").write_bytes(b"%PDF-")
    (originals / "People Tab.pdf").write_bytes(b"%PDF-")
    # TXT lyrics
    (lyrics / "Abbey's Song.txt").write_text("txt verse", encoding="utf-8")
    (lyrics / "Whole.txt").write_text("unmatched txt", encoding="utf-8")
    return originals, covers, lyrics


def test_dry_run_plans_writes_nothing(tmp_path):
    originals, covers, lyrics = _setup_filesystem(tmp_path)
    conn = _make_db(["Abbey's Song", "Lighthouse"])
    tracks = mod.load_tracks(conn)
    paths, labels = mod.load_existing_lyrics(conn)
    plans = mod.plan_lyrics(originals, lyrics, tracks, paths, labels)
    moves = mod.plan_moves(originals, covers)

    # 3 docx + 3 people-pdf-skips + 2 txt = 8 plan entries
    assert len(plans) == 8
    importable = [p for p in plans if p.skip_reason is None]
    # Lighthouse appears twice → second gets a slug suffix
    light_labels = [p.version_label for p in importable
                    if p.matched_title == "Lighthouse"]
    assert "originals_docx" in light_labels
    assert any(lbl.startswith("originals_docx_") for lbl in light_labels)

    # People PDFs are skipped from the lyrics plan
    people = [p for p in plans if p.skip_reason == "people_pdf"]
    assert len(people) == 3

    # 3 People moves planned
    assert len(moves) == 3
    assert all(m.skip_reason is None for m in moves)

    # Nothing written
    assert conn.execute("SELECT COUNT(*) FROM lyrics").fetchone()[0] == 0
    assert (originals / "People.pdf").exists()
    assert not covers.exists()


def test_apply_inserts_and_is_idempotent(tmp_path):
    originals, covers, lyrics = _setup_filesystem(tmp_path)
    conn = _make_db(["Abbey's Song", "Lighthouse"])
    tracks = mod.load_tracks(conn)
    paths, labels = mod.load_existing_lyrics(conn)
    plans = mod.plan_lyrics(originals, lyrics, tracks, paths, labels)
    moves = mod.plan_moves(originals, covers)

    written = mod.apply_lyrics(conn, plans)
    conn.commit()
    move_log = mod.apply_moves(moves, covers)

    # 2 docx + 1 disambiguated docx + 2 txt = 5 inserts
    assert written == 5
    assert conn.execute("SELECT COUNT(*) FROM lyrics").fetchone()[0] == 5
    # People PDFs moved
    assert (covers / "People.pdf").exists()
    assert not (originals / "People.pdf").exists()
    assert all(line.startswith("MOVED ") for line in move_log)

    # Re-run: paths exist already + files moved — 0 inserts, all moves idempotent
    paths2, labels2 = mod.load_existing_lyrics(conn)
    plans2 = mod.plan_lyrics(originals, lyrics, tracks, paths2, labels2)
    moves2 = mod.plan_moves(originals, covers)
    written2 = mod.apply_lyrics(conn, plans2)
    conn.commit()
    move_log2 = mod.apply_moves(moves2, covers)

    assert written2 == 0
    assert conn.execute("SELECT COUNT(*) FROM lyrics").fetchone()[0] == 5
    assert all("already_at_dst" in line or "DELETED" in line
               for line in move_log2) or move_log2 == []


def test_unmatched_txt_inserts_with_null_track_id(tmp_path):
    originals, covers, lyrics = _setup_filesystem(tmp_path)
    conn = _make_db(["Abbey's Song", "Lighthouse"])
    tracks = mod.load_tracks(conn)
    paths, labels = mod.load_existing_lyrics(conn)
    plans = mod.plan_lyrics(originals, lyrics, tracks, paths, labels)
    mod.apply_lyrics(conn, plans)
    conn.commit()
    rows = conn.execute(
        "SELECT track_id, version_label, file_path FROM lyrics "
        "WHERE file_path LIKE ?",
        (f"%Whole.txt",),
    ).fetchall()
    assert len(rows) == 1
    track_id, label, _ = rows[0]
    assert track_id is None
    assert label == "originals_txt"


def test_apply_moves_idempotent_when_target_exists(tmp_path):
    originals = tmp_path / "originals"
    covers    = tmp_path / "covers"
    originals.mkdir()
    covers.mkdir()
    # File already at destination → src absent → SKIP
    (covers / "People.pdf").write_bytes(b"%PDF-")
    moves = mod.plan_moves(originals, covers)
    log = mod.apply_moves(moves, covers)
    assert any("already_at_dst" in line or "SKIP" in line for line in log)
    assert (covers / "People.pdf").exists()
