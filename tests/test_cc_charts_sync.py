"""
Tests for FR-20260531-copper-creek-catalog-sync.

Covers:
- sync_cc_charts_catalog.SONGS_TO_ADD: 15 green-row songs from coppercreekofficial.com/charts/
- sync_cc_charts_catalog.sync(conn): inserts missing songs into catalog_songs + band_song_arrangements
- Idempotency: safe to call twice without duplicating rows
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYNC_PY = PROJECT_ROOT / "tools" / "sync_cc_charts_catalog.py"

sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_cc_charts_catalog", SYNC_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def conn():
    from utils.init_db import get_connection as _gc
    c = _gc()
    c.execute("PRAGMA foreign_keys=ON")
    yield c
    c.close()


@pytest.fixture(scope="module")
def copper_creek_band_id(conn) -> int:
    row = conn.execute("SELECT id FROM bands WHERE name=?", ("Copper Creek",)).fetchone()
    assert row is not None, "Copper Creek band must exist in bands table"
    return row[0]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestSongsToAdd:
    def setup_method(self) -> None:
        self.mod = _load_sync_module()

    def test_songs_to_add_has_sixteen_entries(self) -> None:
        assert len(self.mod.SONGS_TO_ADD) == 16

    def test_each_entry_has_required_fields(self) -> None:
        required = {"title", "artist", "key_sig", "bpm"}
        for song in self.mod.SONGS_TO_ADD:
            assert required <= set(song.keys()), f"Missing fields in {song}"

    def test_breakdown_present(self) -> None:
        titles = {s["title"] for s in self.mod.SONGS_TO_ADD}
        assert "Breakdown" in titles

    def test_chain_of_fools_present(self) -> None:
        titles = {s["title"] for s in self.mod.SONGS_TO_ADD}
        assert "Chain of Fools" in titles

    def test_something_to_talk_about_present(self) -> None:
        titles = {s["title"] for s in self.mod.SONGS_TO_ADD}
        assert "Something To Talk About" in titles

    def test_no_vetoed_songs(self) -> None:
        """Vetoed songs (Ain't It Fun, Smoke On The Water, etc.) must not appear."""
        vetoed = {"Ain't It Fun", "Smoke On The Water", "Man I Feel Like A Woman", "Lady Marmalade"}
        titles = {s["title"] for s in self.mod.SONGS_TO_ADD}
        assert not (vetoed & titles), f"Vetoed songs found: {vetoed & titles}"

    def test_no_placeholder_songs(self) -> None:
        titles = {s["title"] for s in self.mod.SONGS_TO_ADD}
        assert "TBD" not in titles


# ---------------------------------------------------------------------------
# sync() — inserts into live DB
# ---------------------------------------------------------------------------

class TestSync:
    def setup_method(self) -> None:
        self.mod = _load_sync_module()

    def test_sync_runs_without_error(self, conn, copper_creek_band_id) -> None:
        # Should not raise
        inserted, linked = self.mod.sync(conn, dry_run=False)
        assert isinstance(inserted, int)
        assert isinstance(linked, int)

    def test_sync_is_idempotent(self, conn, copper_creek_band_id) -> None:
        """Calling sync twice should insert 0 rows the second time."""
        inserted1, linked1 = self.mod.sync(conn, dry_run=False)
        inserted2, linked2 = self.mod.sync(conn, dry_run=False)
        assert inserted2 == 0, "Second sync should insert 0 new catalog rows"
        assert linked2 == 0, "Second sync should link 0 new arrangements"

    def test_all_songs_in_catalog_after_sync(self, conn) -> None:
        self.mod.sync(conn, dry_run=False)
        for song in self.mod.SONGS_TO_ADD:
            row = conn.execute(
                "SELECT id FROM catalog_songs WHERE title=? AND artist=?",
                (song["title"], song["artist"]),
            ).fetchone()
            assert row is not None, f"Song not in catalog_songs: {song['title']}"

    def test_all_songs_linked_to_copper_creek(self, conn, copper_creek_band_id) -> None:
        self.mod.sync(conn, dry_run=False)
        for song in self.mod.SONGS_TO_ADD:
            row = conn.execute(
                """SELECT bsa.id FROM band_song_arrangements bsa
                   JOIN catalog_songs cs ON cs.id = bsa.catalog_song_id
                   WHERE cs.title=? AND cs.artist=? AND bsa.band_id=?""",
                (song["title"], song["artist"], copper_creek_band_id),
            ).fetchone()
            assert row is not None, (
                f"Song not linked to Copper Creek: {song['title']}"
            )

    def test_bpm_source_is_valid(self, conn) -> None:
        """bpm_source must be a recognised source; librosa is valid for detected BPMs."""
        valid_sources = {"website", "librosa", "manual"}
        self.mod.sync(conn, dry_run=False)
        for song in self.mod.SONGS_TO_ADD:
            row = conn.execute(
                "SELECT bpm_source FROM catalog_songs WHERE title=? AND artist=?",
                (song["title"], song["artist"]),
            ).fetchone()
            if row and row[0] is not None:
                assert row[0] in valid_sources, (
                    f"Unexpected bpm_source for {song['title']!r}: {row[0]!r}"
                )
