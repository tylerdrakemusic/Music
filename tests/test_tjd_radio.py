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
    RadioBroadcastV2,
    RadioBroadcast,
    build_deduped_playlist,
    build_playlist,
    canonical_radio_roots,
    compute_recent_variance,
    extract_artist,
    is_filtered,
    normalize_icecast_metadata,
    prioritized_radio_roots,
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


class TestCanonicalRadioRoots:
    def test_includes_masters_and_ep_when_present(self, tmp_path: Path):
        masters = tmp_path / "catalog" / "masters"
        ep = tmp_path / "catalog" / "ep"
        masters.mkdir(parents=True)
        ep.mkdir(parents=True)

        result = canonical_radio_roots(tmp_path)

        assert result == [masters, ep]

    def test_skips_missing_roots(self, tmp_path: Path):
        masters = tmp_path / "catalog" / "masters"
        masters.mkdir(parents=True)

        result = canonical_radio_roots(tmp_path)

        assert result == [masters]


class TestPrioritizedRadioRoots:
    def test_muzic_primary_and_catalog_fallback(self, tmp_path: Path):
        muzic = tmp_path / "Muzic"
        masters = tmp_path / "catalog" / "masters"
        ep = tmp_path / "catalog" / "ep"
        muzic.mkdir(parents=True)
        masters.mkdir(parents=True)
        ep.mkdir(parents=True)

        primary, fallback = prioritized_radio_roots(tmp_path, muzic_root=muzic)

        assert primary == [muzic]
        assert fallback == [masters, ep]

    def test_empty_primary_when_muzic_missing(self, tmp_path: Path):
        masters = tmp_path / "catalog" / "masters"
        masters.mkdir(parents=True)

        primary, fallback = prioritized_radio_roots(tmp_path, muzic_root=tmp_path / "Muzic")

        assert primary == []
        assert fallback == [masters]


class TestNormalizeIcecastMetadata:
    def test_splits_combined_song_field(self):
        title, artist = normalize_icecast_metadata("Tyler James Drake - Abbey Master", "")

        assert title == "Abbey Master"
        assert artist == "Tyler James Drake"

    def test_preserves_explicit_artist(self):
        title, artist = normalize_icecast_metadata("Abbey Master", "Tyler James Drake")

        assert title == "Abbey Master"
        assert artist == "Tyler James Drake"


# ---------------------------------------------------------------------------
# _build_ffmpeg_cmd crossfade fix (fade_out must start at end of track)
# ---------------------------------------------------------------------------
class TestBuildFfmpegCmd:
    """Verify the crossfade fade-out filter uses the correct start time."""

    def _make_broadcast(self) -> RadioBroadcastV2:
        return RadioBroadcastV2(playlist=[], bitrate=192, crossfade_sec=0.0)

    def test_fade_out_start_uses_duration(self):
        b = self._make_broadcast()
        cmd = b._build_ffmpeg_cmd("song.mp3", fade_out=2.0, duration=180.0)
        af_idx = cmd.index("-af")
        filters = cmd[af_idx + 1]
        # st should be 178s (180 - 2), NOT 0
        assert "st=178.000" in filters
        assert "t=out" in filters

    def test_fade_out_not_added_without_duration(self):
        """If duration is 0 (ffprobe unavailable), fade_out is skipped — no silent track."""
        b = self._make_broadcast()
        cmd = b._build_ffmpeg_cmd("song.mp3", fade_out=2.0, duration=0.0)
        assert "-af" not in cmd  # no filter added when duration unknown

    def test_fade_in_unaffected(self):
        b = self._make_broadcast()
        cmd = b._build_ffmpeg_cmd("song.mp3", fade_in=2.0, duration=0.0)
        af_idx = cmd.index("-af")
        filters = cmd[af_idx + 1]
        assert "t=in" in filters
        assert "st=0" in filters

    def test_fade_out_clamps_to_zero(self):
        """Track shorter than crossfade duration → st clamped to 0."""
        b = self._make_broadcast()
        cmd = b._build_ffmpeg_cmd("short.mp3", fade_out=5.0, duration=3.0)
        af_idx = cmd.index("-af")
        filters = cmd[af_idx + 1]
        assert "st=0.000" in filters


def _mk_track(name: str) -> dict:
    return {
        "path": f"/{name}.mp3",
        "title": name,
        "album": "test",
        "artist": "Tyler James Drake",
        "format": "mp3",
    }


class TestNoRepeatAcrossShuffleBoundary:
    def test_v1_avoids_immediate_repeat_after_loop(self, monkeypatch: pytest.MonkeyPatch):
        playlist = [_mk_track("A"), _mk_track("B"), _mk_track("C")]
        b = RadioBroadcast(playlist=playlist, prefer_quantum_variance=False)

        # Force reshuffle to place C at the front, then verify guard swaps it away.
        def fake_shuffle(items: list[dict]) -> None:
            items[:] = [items[2], items[0], items[1]]

        monkeypatch.setattr("radio.tjd_radio.random.shuffle", fake_shuffle)
        monkeypatch.setattr("radio.tjd_radio.random.randrange", lambda a, b: 1)

        assert b._next_track()["title"] == "A"
        assert b._next_track()["title"] == "B"
        assert b._next_track()["title"] == "C"

        next_track = b._next_track()
        assert next_track["title"] != "C"

    def test_v2_avoids_immediate_repeat_after_loop(self, monkeypatch: pytest.MonkeyPatch):
        playlist = [_mk_track("A"), _mk_track("B"), _mk_track("C")]
        b = RadioBroadcastV2(playlist=playlist, prefer_quantum_variance=False)

        def fake_shuffle(items: list[dict]) -> None:
            items[:] = [items[2], items[0], items[1]]

        monkeypatch.setattr("radio.tjd_radio.random.shuffle", fake_shuffle)
        monkeypatch.setattr("radio.tjd_radio.random.randrange", lambda a, b: 1)

        assert b._next_track()["title"] == "A"
        assert b._next_track()["title"] == "B"
        assert b._next_track()["title"] == "C"

        next_track = b._next_track()
        assert next_track["title"] != "C"


class TestQuantumShuffleWiring:
    """BFX-20260531-radio-quantum-shuffle — prefer_quantum flows through build functions."""

    def test_build_playlist_passes_prefer_quantum_true_to_shuffle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """build_playlist(prefer_quantum=True) must call _shuffle_tracks_with_variance with prefer_quantum=True."""
        d = tmp_path / "tracks"
        d.mkdir()
        _make_fake_audio_file(d, "Zebra Song.mp3")
        _make_fake_audio_file(d, "Apple Song.mp3")

        calls: list[bool] = []

        import radio.tjd_radio as tjd

        orig = tjd._shuffle_tracks_with_variance

        def spy(tracks, prefer_quantum=True):
            calls.append(prefer_quantum)
            return orig(tracks, prefer_quantum=prefer_quantum)

        monkeypatch.setattr(tjd, "_shuffle_tracks_with_variance", spy)

        from radio.tjd_radio import build_playlist
        build_playlist([d], shuffle=True, prefer_quantum=True)

        assert calls, "shuffle was not called"
        assert calls[0] is True, f"Expected prefer_quantum=True, got {calls[0]}"

    def test_build_playlist_passes_prefer_quantum_false_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """build_playlist default still uses prefer_quantum=False (backward-compat)."""
        d = tmp_path / "tracks"
        d.mkdir()
        _make_fake_audio_file(d, "Alpha.mp3")

        calls: list[bool] = []

        import radio.tjd_radio as tjd

        orig = tjd._shuffle_tracks_with_variance

        def spy(tracks, prefer_quantum=True):
            calls.append(prefer_quantum)
            return orig(tracks, prefer_quantum=prefer_quantum)

        monkeypatch.setattr(tjd, "_shuffle_tracks_with_variance", spy)

        from radio.tjd_radio import build_playlist
        build_playlist([d], shuffle=True)

        assert calls, "shuffle was not called"
        assert calls[0] is False, f"Expected prefer_quantum=False by default, got {calls[0]}"

    def test_build_deduped_playlist_passes_prefer_quantum_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """build_deduped_playlist(prefer_quantum=True) must call shuffle with prefer_quantum=True."""
        primary = tmp_path / "primary"
        primary.mkdir()
        _make_fake_audio_file(primary, "Zebra Song.mp3")
        _make_fake_audio_file(primary, "Apple Song.mp3")

        calls: list[bool] = []

        import radio.tjd_radio as tjd

        orig = tjd._shuffle_tracks_with_variance

        def spy(tracks, prefer_quantum=True):
            calls.append(prefer_quantum)
            return orig(tracks, prefer_quantum=prefer_quantum)

        monkeypatch.setattr(tjd, "_shuffle_tracks_with_variance", spy)

        from radio.tjd_radio import build_deduped_playlist
        build_deduped_playlist(primary_roots=[primary], secondary_roots=[], prefer_quantum=True)

        assert any(c is True for c in calls), (
            f"Expected at least one shuffle call with prefer_quantum=True, got: {calls}"
        )

    def test_build_deduped_playlist_uses_quantum_shuffle_when_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """When prefer_quantum=True and quuffle is available, quuffle must be called."""
        primary = tmp_path / "primary"
        primary.mkdir()
        for name in ("Apple.mp3", "Mango.mp3", "Zebra.mp3"):
            _make_fake_audio_file(primary, name)

        quuffle_calls: list[int] = []

        import radio.tjd_radio as tjd

        monkeypatch.setattr(tjd, "HAS_QUANTUM_ENTROPY", True)

        real_quuffle = tjd.quuffle

        def spy_quuffle(lst):
            quuffle_calls.append(len(lst))
            import random
            random.shuffle(lst)  # use classical as stand-in so list is valid

        monkeypatch.setattr(tjd, "quuffle", spy_quuffle)

        from radio.tjd_radio import build_deduped_playlist
        build_deduped_playlist(primary_roots=[primary], secondary_roots=[], prefer_quantum=True)

        assert quuffle_calls, "quuffle was never called despite prefer_quantum=True and HAS_QUANTUM_ENTROPY=True"


class TestVarianceMetrics:
    def test_compute_recent_variance_detects_repeats(self):
        history = [
            {"title": "A"},
            {"title": "A"},
            {"title": "B"},
            {"title": "C"},
        ]
        metrics = compute_recent_variance(history)

        assert metrics["window_size"] == 4
        assert metrics["unique_titles"] == 3
        assert metrics["repeat_rate"] == pytest.approx(1 / 3, rel=1e-6)
        assert metrics["entropy_bits"] > 0


# ---------------------------------------------------------------------------
# /api/now_playing — Icecast offline / online behaviour
# BFX-20260531-radio-stuck-starting
# ---------------------------------------------------------------------------
class TestNowPlayingIcecastOffline:
    """Tests for graceful offline behaviour when Icecast is unreachable."""

    def _get_app(self):
        import radio.tjd_radio as tjd
        return tjd.app

    def test_now_playing_icecast_offline_returns_status_offline(self, monkeypatch):
        """When fetch_icecast_source returns {}, response must include status='offline'
        and title='Icecast offline' — never 'Starting...'."""
        import radio.tjd_radio as tjd

        monkeypatch.setattr(tjd, "active_backend", "icecast")
        monkeypatch.setattr(tjd, "fetch_icecast_source", lambda url: {})
        monkeypatch.setattr(tjd, "playlist_snapshot", [])
        monkeypatch.setattr(tjd, "_icecast_started_at", None)
        monkeypatch.setattr(tjd, "_icecast_history", [])

        with self._get_app().test_client() as client:
            resp = client.get("/api/now_playing")
            data = resp.get_json()

        assert data["status"] == "offline"
        assert data["title"] == "Icecast offline"
        assert data["title"] != "Starting..."

    def test_now_playing_icecast_online_returns_track_title(self, monkeypatch):
        """When fetch_icecast_source returns a populated source, title must be the track
        title and status must NOT be 'offline'."""
        import radio.tjd_radio as tjd

        monkeypatch.setattr(tjd, "active_backend", "icecast")
        monkeypatch.setattr(
            tjd,
            "fetch_icecast_source",
            lambda url: {"title": "Song A", "listeners": 1},
        )
        monkeypatch.setattr(tjd, "playlist_snapshot", [])
        monkeypatch.setattr(tjd, "_icecast_started_at", None)
        monkeypatch.setattr(tjd, "_icecast_history", [])

        with self._get_app().test_client() as client:
            resp = client.get("/api/now_playing")
            data = resp.get_json()

        assert data["title"] == "Song A"
        assert data.get("status") != "offline"
