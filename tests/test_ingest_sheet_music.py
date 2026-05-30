"""
TDD tests for tools/ingest_sheet_music.py
FR-20260530-sheet-music-ingest

Covers:
  - _canonical_name  → artist-first format
  - _parse_stem      → strategy A artist-first detection; strips version suffix
  - _is_tyler_original
  - main()           → Tyler originals routed to originals/, covers to covers/,
                       exact-dup skipped
  - normalize()      → renames existing files to canonical form; detects collisions
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ingest_sheet_music as sm  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# _canonical_name — artist-first format
# ─────────────────────────────────────────────────────────────────────────────
class TestCanonicalName:
    def test_artist_first(self):
        assert sm._canonical_name("Josie", "Steely Dan", "", ".docx") == "Steely Dan - Josie.docx"

    def test_no_artist_uses_title_only(self):
        assert sm._canonical_name("Tequila", "", "", ".docx") == "Tequila.docx"

    def test_with_descriptor_variant(self):
        result = sm._canonical_name("Dreams", "Fleetwood Mac", "Chords Lyrics", ".pdf")
        assert result == "Fleetwood Mac - Dreams (Chords Lyrics).pdf"

    def test_originals_with_key_variant(self):
        result = sm._canonical_name("Fly Away", "Tyler James Drake", "Key C", ".docx")
        assert result == "Tyler James Drake - Fly Away (Key C).docx"


# ─────────────────────────────────────────────────────────────────────────────
# _parse_stem
# ─────────────────────────────────────────────────────────────────────────────
class TestParseStem:
    def test_hyphenated_cover_steely_dan(self):
        title, artist, variant = sm._parse_stem("Steely-Dan-Josie (1)")
        assert title == "Josie"
        assert artist == "Steely Dan"
        assert variant == ""

    def test_underscore_title_first_with_key(self):
        """Fly-Away_Tyler-James-Drake_Key_C (7) → title-first underscore."""
        title, artist, variant = sm._parse_stem("Fly-Away_Tyler-James-Drake_Key_C (7)")
        assert title == "Fly Away"
        assert artist == "Tyler James Drake"
        assert variant == "Key C"

    def test_underscore_artist_first_old_style(self):
        """Tyler James Drake_Invisible_Key_A Minor → artist-first detection."""
        title, artist, variant = sm._parse_stem("Tyler James Drake_Invisible_Key_A Minor")
        assert title == "Invisible"
        assert artist == "Tyler James Drake"
        assert "A Minor" in variant

    def test_space_dash_existing_cover(self):
        """Existing covers: 'Dreams - Fleetwood Mac (Chords Lyrics)' parses correctly."""
        title, artist, variant = sm._parse_stem("Dreams - Fleetwood Mac (Chords Lyrics)")
        assert title == "Dreams"
        assert artist == "Fleetwood Mac"
        assert variant == "Chords Lyrics"

    def test_strips_version_number_suffix(self):
        title, artist, _ = sm._parse_stem("Santana-Smooth (5)")
        assert title == "Smooth"
        assert artist == "Santana"

    def test_tyler_drake_hyphenated_what_i_do(self):
        title, artist, _ = sm._parse_stem("Tyler-Drake-What-I-do- (6)")
        assert title == "What I Do"
        assert artist == "Tyler James Drake"


# ─────────────────────────────────────────────────────────────────────────────
# _is_tyler_original
# ─────────────────────────────────────────────────────────────────────────────
class TestIsTylerOriginal:
    def test_hyphenated_tyler_james_drake(self):
        assert sm._is_tyler_original("Fly-Away_Tyler-James-Drake_Key_C (7)") is True

    def test_hyphenated_tyler_drake_short(self):
        assert sm._is_tyler_original("Tyler-Drake-What-I-do- (6)") is True

    def test_covers_not_original(self):
        assert sm._is_tyler_original("Steely-Dan-Josie (1)") is False

    def test_existing_underscore_title_first(self):
        assert sm._is_tyler_original("Fly Away_Tyler James Drake_Key_C") is True

    def test_existing_underscore_artist_first(self):
        assert sm._is_tyler_original("Tyler James Drake_Invisible_Key_A Minor") is True

    def test_unrelated_artist_is_false(self):
        assert sm._is_tyler_original("Santana-Smooth (5)") is False


# ─────────────────────────────────────────────────────────────────────────────
# Integration: ingest routing
# ─────────────────────────────────────────────────────────────────────────────
class TestIngestRouting:
    def test_tyler_original_routed_to_originals(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (src / "Fly-Away_Tyler-James-Drake_Key_C (7).docx").write_bytes(b"PK" + b"\x01" * 50)

        sm.main(tmp_dir=src, apply=True, covers_dir=covers, originals_dir=originals)

        assert list(covers.iterdir()) == [], "Tyler original must NOT land in covers/"
        original_files = list(originals.iterdir())
        assert len(original_files) == 1
        assert original_files[0].name == "Tyler James Drake - Fly Away (Key C).docx"

    def test_cover_routed_to_covers(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (src / "Steely-Dan-Josie (1).docx").write_bytes(b"PK" + b"\x02" * 50)

        sm.main(tmp_dir=src, apply=True, covers_dir=covers, originals_dir=originals)

        cover_files = list(covers.iterdir())
        assert len(cover_files) == 1
        assert cover_files[0].name == "Steely Dan - Josie.docx"
        assert list(originals.iterdir()) == []

    def test_exact_dup_in_covers_skipped(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        content = b"PK" + b"\x03" * 50
        (covers / "Steely Dan - Josie.docx").write_bytes(content)
        (src / "Steely-Dan-Josie (2).docx").write_bytes(content)  # same bytes

        sm.main(tmp_dir=src, apply=True, covers_dir=covers, originals_dir=originals)

        assert len(list(covers.iterdir())) == 1  # no new file added

    def test_exact_dup_in_originals_skipped(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        content = b"PK" + b"\x04" * 50
        (originals / "Tyler James Drake - Fly Away (Key C).docx").write_bytes(content)
        (src / "Fly-Away_Tyler-James-Drake_Key_C (7).docx").write_bytes(content)

        sm.main(tmp_dir=src, apply=True, covers_dir=covers, originals_dir=originals)

        assert len(list(originals.iterdir())) == 1  # no new file added


# ─────────────────────────────────────────────────────────────────────────────
# normalize() — full rename pass on existing files
# ─────────────────────────────────────────────────────────────────────────────
class TestNormalize:
    def test_song_artist_order_renamed_to_artist_song(self, tmp_path):
        """'Josie - Steely Dan.docx' should be renamed to 'Steely Dan - Josie.docx'."""
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (covers / "Josie - Steely Dan.docx").write_bytes(b"PK" + b"\x05" * 50)

        renames = sm.normalize(covers_dir=covers, originals_dir=originals, apply=False)
        targets = [r["to"] for r in renames]
        assert any("Steely Dan - Josie.docx" in t for t in targets)

    def test_normalize_apply_renames_file(self, tmp_path):
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (covers / "Josie - Steely Dan.docx").write_bytes(b"PK" + b"\x06" * 50)

        sm.normalize(covers_dir=covers, originals_dir=originals, apply=True)

        assert not (covers / "Josie - Steely Dan.docx").exists()
        assert (covers / "Steely Dan - Josie.docx").exists()

    def test_already_canonical_not_renamed(self, tmp_path):
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (covers / "Steely Dan - Josie.docx").write_bytes(b"PK" + b"\x07" * 50)

        renames = sm.normalize(covers_dir=covers, originals_dir=originals, apply=False)
        froms = [r["from"] for r in renames if r["action"] == "rename"]
        assert not any("Steely Dan - Josie.docx" in f for f in froms)

    def test_normalize_underscore_original_renamed(self, tmp_path):
        """'Fly Away_Tyler James Drake_Key_C.docx' → 'Tyler James Drake - Fly Away (Key C).docx'."""
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (originals / "Fly Away_Tyler James Drake_Key_C.docx").write_bytes(b"PK" + b"\x08" * 50)

        sm.normalize(covers_dir=covers, originals_dir=originals, apply=True)

        assert not (originals / "Fly Away_Tyler James Drake_Key_C.docx").exists()
        assert (originals / "Tyler James Drake - Fly Away (Key C).docx").exists()

    def test_collision_flagged_as_manual_review(self, tmp_path):
        """Two files that normalize to the same target are flagged, not silently clobbered."""
        covers = tmp_path / "covers"; covers.mkdir()
        originals = tmp_path / "originals"; originals.mkdir()

        (originals / "Invisible_Tyler James Drake_Key_A Minor.docx").write_bytes(b"PK" + b"\xaa" * 50)
        (originals / "Tyler James Drake_Invisible_Key_A Minor.docx").write_bytes(b"PK" + b"\xbb" * 50)

        renames = sm.normalize(covers_dir=covers, originals_dir=originals, apply=False)
        actions = [r["action"] for r in renames]
        assert "manual_review_collision" in actions
