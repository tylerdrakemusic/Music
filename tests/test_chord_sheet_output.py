"""TDD tests for src/utils/chord_sheet_output.py
FR-20260703-music-agentic-chord-sheets

Covers:
  - is_tyler_original           -> artist-name based cover/original detection
  - canonical_docx_name         -> "Artist - Title (variant).ext" naming convention
  - resolve_chord_sheet_paths   -> covers/originals/song_templates/process_logs path resolution
  - log_chord_sheet_run         -> JSONL process-log append
  - render_validation_html      -> side-by-side source-vs-generated accuracy report
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils import chord_sheet_output as cso  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# is_tyler_original
# ─────────────────────────────────────────────────────────────────────────────
class TestIsTylerOriginal:
    def test_tyler_james_drake_is_original(self):
        assert cso.is_tyler_original("Tyler James Drake") is True

    def test_tyler_is_original_case_insensitive(self):
        assert cso.is_tyler_original("tyler james drake") is True

    def test_abba_is_not_original(self):
        assert cso.is_tyler_original("Abba") is False

    def test_neil_diamond_is_not_original(self):
        assert cso.is_tyler_original("Neil Diamond") is False

    def test_empty_artist_is_not_original(self):
        assert cso.is_tyler_original("") is False


# ─────────────────────────────────────────────────────────────────────────────
# canonical_docx_name
# ─────────────────────────────────────────────────────────────────────────────
class TestCanonicalDocxName:
    def test_artist_title_no_variant(self):
        assert cso.canonical_docx_name("Josie", "Steely Dan") == "Steely Dan - Josie.docx"

    def test_artist_title_with_variant(self):
        result = cso.canonical_docx_name("Dreams", "Fleetwood Mac", variant="Chords Lyrics")
        assert result == "Fleetwood Mac - Dreams (Chords Lyrics).docx"

    def test_no_artist_uses_title_only(self):
        assert cso.canonical_docx_name("Tequila", "") == "Tequila.docx"


# ─────────────────────────────────────────────────────────────────────────────
# resolve_chord_sheet_paths
# ─────────────────────────────────────────────────────────────────────────────
class TestResolveChordSheetPaths:
    def test_cover_routes_to_covers_dir(self, tmp_path):
        paths = cso.resolve_chord_sheet_paths("Sweet Caroline", "Neil Diamond", project_root=tmp_path)
        assert paths.is_original is False
        assert paths.sheet_music_path.parent == tmp_path / "catalog" / "sheet_music" / "covers"
        assert paths.sheet_music_path.name == "Neil Diamond - Sweet Caroline.docx"

    def test_original_routes_to_originals_dir(self, tmp_path):
        paths = cso.resolve_chord_sheet_paths("Fly Away", "Tyler James Drake", project_root=tmp_path)
        assert paths.is_original is True
        assert paths.sheet_music_path.parent == tmp_path / "catalog" / "sheet_music" / "originals"

    def test_template_path_in_song_templates(self, tmp_path):
        paths = cso.resolve_chord_sheet_paths("Sweet Caroline", "Neil Diamond", project_root=tmp_path)
        assert paths.template_path == (
            tmp_path / "studio_master" / "song_templates" / "Neil Diamond - Sweet Caroline.json"
        )

    def test_log_path_in_process_logs_dir(self, tmp_path):
        paths = cso.resolve_chord_sheet_paths("Sweet Caroline", "Neil Diamond", project_root=tmp_path)
        assert paths.log_path.parent == tmp_path / "catalog" / "sheet_music" / "_process_logs"
        assert paths.log_path.name == "chord_sheets_runs.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# log_chord_sheet_run
# ─────────────────────────────────────────────────────────────────────────────
class TestLogChordSheetRun:
    def test_appends_jsonl_entry(self, tmp_path):
        log_path = tmp_path / "_process_logs" / "chord_sheets_runs.jsonl"
        cso.log_chord_sheet_run(log_path, {"title": "Sweet Caroline", "artist": "Neil Diamond"})
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["title"] == "Sweet Caroline"
        assert "logged_at" in entry

    def test_second_call_appends_not_overwrites(self, tmp_path):
        log_path = tmp_path / "_process_logs" / "chord_sheets_runs.jsonl"
        cso.log_chord_sheet_run(log_path, {"title": "Song A"})
        cso.log_chord_sheet_run(log_path, {"title": "Song B"})
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2


# ─────────────────────────────────────────────────────────────────────────────
# render_validation_html
# ─────────────────────────────────────────────────────────────────────────────
class TestRenderValidationHtml:
    def test_matching_lines_marked_ok(self, tmp_path):
        out = tmp_path / "report.html"
        cso.render_validation_html(
            title="Sweet Caroline",
            artist="Neil Diamond",
            source_lines=["Hello darkness", "my old friend"],
            generated_lines=["Hello darkness", "my old friend"],
            out_path=out,
        )
        html = out.read_text(encoding="utf-8")
        assert "Sweet Caroline" in html
        assert html.count('class="diff-row ok"') == 2
        assert 'class="diff-row mismatch"' not in html

    def test_mismatched_lines_flagged(self, tmp_path):
        out = tmp_path / "report.html"
        cso.render_validation_html(
            title="Sweet Caroline",
            artist="Neil Diamond",
            source_lines=["line one", "line two"],
            generated_lines=["line one", "line TWO different"],
            out_path=out,
        )
        html = out.read_text(encoding="utf-8")
        assert html.count('class="diff-row mismatch"') == 1
        assert html.count('class="diff-row ok"') == 1
