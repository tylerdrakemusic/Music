"""Regression guards for retiring the Music Ollama surfaces."""

from pathlib import Path


MUSIC_ROOT = Path(__file__).resolve().parents[1]


def test_music_runtime_and_ui_have_no_ollama_path() -> None:
    surfaces = (
        MUSIC_ROOT / "src" / "analysis" / "music_dashboard.py",
        MUSIC_ROOT / "src" / "analysis" / "templates" / "rhymes.html",
    )

    for surface in surfaces:
        assert "ollama" not in surface.read_text(encoding="utf-8").lower()


def test_music_has_no_ollama_integration_or_fallback_test() -> None:
    integration_paths = tuple(
        MUSIC_ROOT.glob("src/**/ollama*")
    )
    test_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (MUSIC_ROOT / "tests").glob("test_*.py")
        if path.name != Path(__file__).name
    )

    assert not integration_paths
    assert "ollama" not in test_text