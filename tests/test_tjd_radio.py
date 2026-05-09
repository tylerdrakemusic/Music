"""
Unit tests for tjd_radio — filter engine, artist extraction, dedup playlist.
FR-20260509-tjd-radio-gmusic-playlist
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from radio.tjd_radio import (
    build_deduped_playlist,
    build_playlist,
    extract_artist,
    is_filtered,
)


# ---------------------------------------------------------------------------
# is_filtered
# ---------------------------------------------------------------------------
class TestIsFiltered:
    def test_pitch_shift_plus_integer(self):
        assert is_filtered("Fly Away (+2 steps)")

    def test_pitch_shift_minus_integer(self):
        assert is_filtered("Fly Away (-3 steps)")

    def test_pitch_shift_decimal(self):
        assert is_filtered("Song (+1.5 steps)")

    def test_pitch_shift_singular_step(self):
        assert is_filtered("Song (+1 step)")

    def test_backing_track(self):
        assert is_filtered("Marigold (Backing Track +2)")

    def test_rough_open_paren(self):
        assert is_filtered("Song (Rough Mix)")

    def test_rough_close_paren(self):
        assert is_filtered("Song Demo Rough)")

    def test_tuned_vox(self):
        assert is_filtered("Song (Tuned Vox)")

    def test_premaster(self):
        assert is_filtered("Song PreMaster")

    def test_premaster_case_insensitive(self):
        assert is_filtered("Song PREMASTER v2")

    def test_vox_down(self):
        assert is_filtered("Song Vox Down")

    def test_clean_title_passes(self):
        assert not is_filtered("Fly Away")

    def test_clean_title_with_artist(self):
        assert not is_filtered("Fly Away - Tyler James Drake")

    def test_clean_album_track(self):
        assert not is_filtered("01 Marigold Master")

    def test_steps_without_sign_passes(self):
        # No sign (+/-) → not a pitch-shift marker
        assert not is_filtered("Song (2 steps)")


# ---------------------------------------------------------------------------
# extract_artist
# ---------------------------------------------------------------------------
class TestExtractArtist:
    def test_with_artist_suffix(self):
        assert extract_artist("Fly Away - Tyler James Drake") == "Tyler James Drake"

    def test_cover_song(self):
        assert extract_artist("Hotel California - Eagles") == "Eagles"

    def test_no_separator_returns_tjd(self):
        assert extract_artist("Marigold") == "Tyler James Drake"

    def test_multiple_dashes_takes_first_split(self):
        # "Song Title - A - B" → "A - B" (everything after first " - ")
        assert extract_artist("Song Title - A - B") == "A - B"

    def test_strips_whitespace(self):
        assert extract_artist("Song -  Artist With Spaces  ") == " Artist With Spaces  ".strip()

    def test_empty_string_returns_tjd(self):
        assert extract_artist("") == "Tyler James Drake"


# ---------------------------------------------------------------------------
# build_deduped_playlist
# ---------------------------------------------------------------------------

def _make_fake_audio_file(tmp_path: Path, name: str, size: int = 50_000) -> Path:
    """Create a fake audio file large enough to pass the size check."""
    f = tmp_path / name
    f.write_bytes(b"\x00" * size)
    return f


class TestBuildDedupedPlaylist:
    def test_primary_wins_on_collision(self, tmp_path: Path):
        primary_dir = tmp_path / "primary"
        secondary_dir = tmp_path / "secondary"
        primary_dir.mkdir()
        secondary_dir.mkdir()

        _make_fake_audio_file(primary_dir, "Fly Away.mp3")
        _make_fake_audio_file(secondary_dir, "Fly Away.mp3")  # duplicate
        _make_fake_audio_file(secondary_dir, "Brand New Song.mp3")

        result = build_deduped_playlist(
            primary_roots=[primary_dir],
            secondary_roots=[secondary_dir],
            shuffle=False,
        )

        titles = [t["title"] for t in result]
        # "Fly Away" should appear exactly once
        assert titles.count("Fly Away") == 1
        # "Brand New Song" from secondary should be included
        assert "Brand New Song" in titles
        assert len(result) == 2

    def test_secondary_included_when_no_collision(self, tmp_path: Path):
        primary_dir = tmp_path / "primary"
        secondary_dir = tmp_path / "secondary"
        primary_dir.mkdir()
        secondary_dir.mkdir()

        _make_fake_audio_file(primary_dir, "Song A.mp3")
        _make_fake_audio_file(secondary_dir, "Song B.mp3")

        result = build_deduped_playlist(
            primary_roots=[primary_dir],
            secondary_roots=[secondary_dir],
            shuffle=False,
        )
        titles = [t["title"] for t in result]
        assert "Song A" in titles
        assert "Song B" in titles
        assert len(result) == 2

    def test_filtered_files_excluded(self, tmp_path: Path):
        primary_dir = tmp_path / "primary"
        primary_dir.mkdir()
        _make_fake_audio_file(primary_dir, "Good Song.mp3")
        _make_fake_audio_file(primary_dir, "Good Song (+2 steps).mp3")  # filtered
        _make_fake_audio_file(primary_dir, "Good Song PreMaster.mp3")   # filtered

        result = build_deduped_playlist(
            primary_roots=[primary_dir],
            secondary_roots=[],
            shuffle=False,
        )
        assert len(result) == 1
        assert result[0]["title"] == "Good Song"

    def test_artist_key_present(self, tmp_path: Path):
        primary_dir = tmp_path / "primary"
        primary_dir.mkdir()
        _make_fake_audio_file(primary_dir, "Fly Away - Tyler James Drake.mp3")

        result = build_deduped_playlist(
            primary_roots=[primary_dir],
            secondary_roots=[],
            shuffle=False,
        )
        assert len(result) == 1
        assert result[0]["artist"] == "Tyler James Drake"

    def test_missing_primary_dir_graceful(self, tmp_path: Path):
        secondary_dir = tmp_path / "secondary"
        secondary_dir.mkdir()
        _make_fake_audio_file(secondary_dir, "Song B.mp3")

        result = build_deduped_playlist(
            primary_roots=[tmp_path / "nonexistent"],
            secondary_roots=[secondary_dir],
            shuffle=False,
        )
        assert len(result) == 1
        assert result[0]["title"] == "Song B"

    def test_dedup_normalizes_case(self, tmp_path: Path):
        primary_dir = tmp_path / "primary"
        secondary_dir = tmp_path / "secondary"
        primary_dir.mkdir()
        secondary_dir.mkdir()

        # Different casing but same title
        _make_fake_audio_file(primary_dir, "Fly Away.mp3")
        _make_fake_audio_file(secondary_dir, "fly away.mp3")

        result = build_deduped_playlist(
            primary_roots=[primary_dir],
            secondary_roots=[secondary_dir],
            shuffle=False,
        )
        # Should deduplicate — only 1 track
        assert len(result) == 1
