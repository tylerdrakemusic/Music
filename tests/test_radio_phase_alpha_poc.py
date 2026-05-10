from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from radio_phase_alpha_poc import (  # noqa: E402
    extract_artist_from_stem,
    extract_title_from_stem,
    iter_tyler_catalog_audio,
    write_liquidsoap_config,
    write_liquidsoap_playlist,
)


def _make_audio_file(path: Path, name: str, size: int = 20_000) -> Path:
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x00" * size)
    return target


def test_extract_artist_from_stem_with_suffix() -> None:
    assert extract_artist_from_stem("Song Name - Tyler James Drake") == "Tyler James Drake"


def test_extract_artist_from_stem_default() -> None:
    assert extract_artist_from_stem("Song Name") == "Tyler James Drake"


def test_extract_title_from_stem_with_suffix() -> None:
    assert extract_title_from_stem("Song Name - Tyler James Drake") == "Song Name"


def test_iter_tyler_catalog_audio_filters_roots_and_size(tmp_path: Path) -> None:
    masters = tmp_path / "catalog" / "masters"
    ep = tmp_path / "catalog" / "ep"
    outside = tmp_path / "catalog" / "roughs"

    _make_audio_file(masters, "Track A.mp3")
    _make_audio_file(ep, "Track B.wav")
    _make_audio_file(outside, "Should Skip.mp3")
    small = _make_audio_file(masters, "Too Small.mp3", size=8_000)

    result = iter_tyler_catalog_audio(tmp_path)
    paths = {p.name for p in result}

    assert "Track A.mp3" in paths
    assert "Track B.wav" in paths
    assert "Should Skip.mp3" not in paths
    assert small.name not in paths


def test_write_liquidsoap_playlist_contains_annotate_metadata(tmp_path: Path) -> None:
    audio = _make_audio_file(tmp_path, "My Song - Tyler James Drake.mp3")
    playlist = tmp_path / "playlist.liqlist"
    audio_str = str(audio).replace("\\", "/")
    expected_path = f"/mnt/{audio.drive.rstrip(':').lower()}{audio_str[2:]}"

    write_liquidsoap_playlist([audio], playlist)
    content = playlist.read_text(encoding="utf-8")

    assert "annotate:title=\"My Song\"" in content
    assert "artist=\"Tyler James Drake\"" in content
    assert expected_path in content


def test_write_liquidsoap_config_uses_wsl_safe_paths(tmp_path: Path) -> None:
    playlist = Path("F:/❤Music/output/radio_phase_alpha/tyler_catalog_phase_alpha.liqlist")
    config_path = tmp_path / "tjd_radio_phase_alpha.liq"

    write_liquidsoap_config(playlist, config_path)
    content = config_path.read_text(encoding="utf-8")

    assert 'set("init.allow_root", true)' in content
    assert 'radio = mksafe(radio_tracks)' in content
    assert '/mnt/f/❤Music/output/radio_phase_alpha/tyler_catalog_phase_alpha.liqlist' in content
