"""
Tests for FR-20260425-band-mgmt-playback-sheets.

Covers:
- export_catalog.py: _audio_url helper and audio_url field in exports
- portal.html: audio column, sheet-music column visibility, JS structure
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci_unavailable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT  = Path(__file__).resolve().parents[1]
EXPORT_PY     = PROJECT_ROOT / "catalog" / "setlists" / "export_catalog.py"
PORTAL_HTML   = PROJECT_ROOT / "reports" / "band_management_panel.html"

# ---------------------------------------------------------------------------
# Load export_catalog module without executing main()
# ---------------------------------------------------------------------------
def _load_export_module():
    spec = importlib.util.spec_from_file_location("export_catalog", EXPORT_PY)
    mod  = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# export_catalog.py — _audio_url helper
# ---------------------------------------------------------------------------

class TestAudioUrlHelper:
    def setup_method(self) -> None:
        self.mod = _load_export_module()

    def test_none_source_returns_none(self) -> None:
        assert self.mod._audio_url(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert self.mod._audio_url("") is None

    def test_mp3_produces_file_uri(self) -> None:
        result = self.mod._audio_url("Long Train Runnin' - The Doobie Brothers.mp3")
        assert result is not None
        assert result.startswith("file:///")
        assert "Muzic" in result
        assert "Long%20Train%20Runnin" in result or "Long Train Runnin" in result

    def test_wav_produces_file_uri(self) -> None:
        result = self.mod._audio_url("Rhiannon - Fleetwood Mac (in Bm).wav")
        assert result is not None
        assert result.startswith("file:///")

    def test_uri_contains_g_drive(self) -> None:
        result = self.mod._audio_url("song.mp3")
        assert result is not None
        # Should point to G:/Muzic or G:\\Muzic depending on OS normalisation
        assert "G" in result or "g" in result


# ---------------------------------------------------------------------------
# export_catalog.py — DB integration (requires heartmusic.db)
# ---------------------------------------------------------------------------
_DB_PRESENT = (
    (PROJECT_ROOT / "src" / "data" / "heartmusic.db").exists()
    and bool(os.environ.get("HEARTMUSIC_DB_KEY"))
)
requires_db = pytest.mark.skipif(
    not _DB_PRESENT,
    reason="heartmusic.db not present or HEARTMUSIC_DB_KEY not set (CI)",
)


@requires_db
def test_catalog_songs_have_audio_url_field() -> None:
    mod = _load_export_module()
    conn = mod.get_connection()
    conn.execute("PRAGMA foreign_keys=ON")
    sm_index = mod.build_sheet_music_index()
    # Use band_id=1 (Copper Creek) which is always present
    songs = mod.export_catalog_for_band(conn, 1, sm_index)
    conn.close()
    assert songs, "Expected at least one catalog song"
    for s in songs:
        assert "audio_url" in s, f"Missing audio_url on song: {s['title']}"
        # audio_url is either None (no source_file) or a file:/// URI
        if s["audio_url"] is not None:
            assert s["audio_url"].startswith("file:///")


@requires_db
def test_setlist_songs_have_audio_url_field() -> None:
    mod = _load_export_module()
    conn = mod.get_connection()
    conn.execute("PRAGMA foreign_keys=ON")
    _meta, songs = mod.export_active_setlist_for_band(conn, 1)
    conn.close()
    if not songs:
        pytest.skip("No active setlist for band_id=1")
    for s in songs:
        assert "audio_url" in s, f"Missing audio_url on setlist song: {s['title']}"
        if s["audio_url"] is not None:
            assert s["audio_url"].startswith("file:///")


# ---------------------------------------------------------------------------
# portal.html — structural checks
# ---------------------------------------------------------------------------
_PORTAL_PRESENT = PORTAL_HTML.exists()
requires_portal = pytest.mark.skipif(not _PORTAL_PRESENT, reason="portal.html not found")


@pytest.fixture(scope="module")
def portal_html() -> str:
    return PORTAL_HTML.read_text(encoding="utf-8")


@requires_portal
def test_audio_column_header_present(portal_html: str) -> None:
    # Column ID is registered in the JS column definition (rendered dynamically via buildHeader)
    assert 'bm-th-audio' in portal_html


@requires_portal
def test_sheet_music_column_no_longer_hidden_in_header(portal_html: str) -> None:
    # The old code had style="display:none" on bm-th-sheet.
    # New code shows it in both views via JS — header should not have inline hide.
    assert 'id="bm-th-sheet" style="display:none"' not in portal_html


@requires_portal
def test_audio_element_present(portal_html: str) -> None:
    assert 'id="bm-audio"' in portal_html


@requires_portal
def test_bm_play_btn_css_present(portal_html: str) -> None:
    assert ".bm-play-btn" in portal_html


@requires_portal
def test_bm_progress_css_present(portal_html: str) -> None:
    assert ".bm-progress" in portal_html


@requires_portal
def test_bmPlayRow_defined(portal_html: str) -> None:
    # Defined as window.bmPlayRow = function(...) for IIFE-scoped compatibility
    assert "bmPlayRow" in portal_html


@requires_portal
def test_bmSeek_defined(portal_html: str) -> None:
    # Defined as window.bmSeek = function(...) for IIFE-scoped compatibility
    assert "bmSeek" in portal_html


@requires_portal
def test_audio_cell_uses_data_attribute(portal_html: str) -> None:
    assert "data-audio-url" in portal_html


@requires_portal
def test_audio_cell_uses_bmPlayRow_onclick(portal_html: str) -> None:
    assert 'onclick="bmPlayRow(this)"' in portal_html


@requires_portal
def test_setlist_colspan_updated(portal_html: str) -> None:
    # Set-header row must span 8 columns (2 new columns added)
    assert 'colspan="8"' in portal_html


@requires_portal
def test_setlist_enriches_sheet_music_from_catalog(portal_html: str) -> None:
    # applyData setlist block must build catalogMap and enrich sheet_music
    assert "catalogMap" in portal_html
    assert "cat.sheet_music" in portal_html


@requires_portal
def test_setlist_enriches_audio_url_from_catalog(portal_html: str) -> None:
    assert "cat.audio_url" in portal_html


@requires_portal
def test_audio_timeupdate_listener_wired(portal_html: str) -> None:
    assert "timeupdate" in portal_html


@requires_portal
def test_audio_ended_listener_wired(portal_html: str) -> None:
    assert "ended" in portal_html


@requires_portal
def test_bm_inline_contains_audio_url_field(portal_html: str) -> None:
    # After export_catalog.py runs, BM_INLINE data should contain audio_url keys
    assert '"audio_url"' in portal_html
