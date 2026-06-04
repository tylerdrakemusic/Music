"""
Tests for FR-20260425-guitar-trainer-metronome.

Covers:
  - /click/<filename> route: serves WAV files from click/ directory
  - /click/<filename> route: rejects path traversal and non-.wav files
  - HTML: metronome panel element exists
  - HTML: beat-row dots are rendered
  - HTML: BPM input, time-signature select, tap button, play button present
  - HTML: metronome JS references first.wav (accent) and click.wav (beats)
  - HTML: Web Audio API scheduler pattern is present
  - click/ directory: required WAV files exist on disk
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths & imports
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAINER_PY = PROJECT_ROOT / "src" / "training" / "musician_training_ui.py"
CLICK_DIR = PROJECT_ROOT / "click"

# WAV files are gitignored (*.wav in .gitignore) — they exist locally but not on CI.
# Tests that depend on the actual files are skipped when the files are absent.
_click_wav_present = (CLICK_DIR / "click.wav").exists()
_first_wav_present = (CLICK_DIR / "first.wav").exists()
requires_click_wav = pytest.mark.skipif(
    not _click_wav_present,
    reason="click/click.wav not present (gitignored WAV — run locally)",
)
requires_first_wav = pytest.mark.skipif(
    not _first_wav_present,
    reason="click/first.wav not present (gitignored WAV — run locally)",
)
requires_both_wavs = pytest.mark.skipif(
    not (_click_wav_present and _first_wav_present),
    reason="click WAV files not present (gitignored — run locally)",
)

import sqlite3

sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui
import training.musician_training_ui as ui_mod


# ---------------------------------------------------------------------------
# In-memory DB helpers (same pattern as test_guitar_trainer_db.py)
# ---------------------------------------------------------------------------

class _NoClose:
    """Proxy that swallows close() so shared in-memory connections stay open."""

    def __init__(self, real_conn: sqlite3.Connection) -> None:
        self._real = real_conn

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self._real, name)

    def close(self) -> None:  # noqa: D401
        pass

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS guitar_exercises (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            artist      TEXT NOT NULL DEFAULT '',
            song_path   TEXT NOT NULL DEFAULT '',
            segments    TEXT NOT NULL DEFAULT '[]',
            gradient    INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS guitar_training_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            exercise_id INTEGER REFERENCES guitar_exercises(id) ON DELETE SET NULL,
            song_path   TEXT NOT NULL DEFAULT '',
            seg_start   TEXT NOT NULL DEFAULT '',
            seg_end     TEXT NOT NULL DEFAULT '',
            repetition  INTEGER NOT NULL DEFAULT 1,
            logged_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    return conn


@pytest.fixture
def client(monkeypatch):
    real_conn = _make_mem_conn()
    monkeypatch.setattr(ui_mod, "get_connection", lambda: _NoClose(real_conn))
    ui.app.config["TESTING"] = True
    with ui.app.test_client() as c:
        yield c
    real_conn.close()


@pytest.fixture
def html(client) -> str:
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.data.decode("utf-8")


@pytest.fixture(scope="module")
def trainer_src() -> str:
    return TRAINER_PY.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# WAV files on disk
# ---------------------------------------------------------------------------

@requires_click_wav
def test_click_wav_exists() -> None:
    """click/click.wav must exist for metronome subdivisions."""
    assert (CLICK_DIR / "click.wav").exists(), "click/click.wav not found"


@requires_first_wav
def test_first_wav_exists() -> None:
    """click/first.wav must exist for beat-1 accent."""
    assert (CLICK_DIR / "first.wav").exists(), "click/first.wav not found"


# ---------------------------------------------------------------------------
# /click/<filename> route
# ---------------------------------------------------------------------------

def test_click_route_rejects_non_wav(client) -> None:
    """/click/ route must reject files that are not .wav (403)."""
    resp = client.get("/click/evil.py")
    assert resp.status_code == 403


def test_click_route_rejects_path_traversal(client) -> None:
    """/click/ route must reject path traversal attempts (403)."""
    resp = client.get("/click/../src/training/musician_training_ui.py")
    # Flask will normalise the path; result is either 403 or 404, never 200
    assert resp.status_code in (403, 404)


@requires_click_wav
def test_click_route_serves_click_wav(client) -> None:
    """/click/click.wav must return 200 with audio/wav content-type."""
    resp = client.get("/click/click.wav")
    assert resp.status_code == 200
    assert "audio" in resp.content_type or "octet" in resp.content_type


@requires_first_wav
def test_click_route_serves_first_wav(client) -> None:
    """/click/first.wav must return 200."""
    resp = client.get("/click/first.wav")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# HTML structure — metronome panel
# ---------------------------------------------------------------------------

def test_metronome_panel_exists(html: str) -> None:
    """Metronome panel element must be present in the rendered HTML."""
    assert 'id="metro-panel"' in html, "metronome panel (id=metro-panel) not found"


def test_bpm_input_exists(html: str) -> None:
    """BPM input field must be present."""
    assert 'id="metro-bpm"' in html


def test_tap_button_exists(html: str) -> None:
    """Tap tempo button must call metroTap()."""
    assert "metroTap()" in html


def test_play_button_exists(html: str) -> None:
    """Play/stop toggle button must be present and call metroToggle()."""
    assert 'id="metro-play-btn"' in html
    assert "metroToggle()" in html


def test_time_signature_select_exists(html: str) -> None:
    """Time-signature selector must offer 4/4, 3/4, 6/8."""
    assert 'id="metro-sig"' in html
    assert "4/4" in html
    assert "3/4" in html
    assert "6/8" in html


def test_beat_row_exists(html: str) -> None:
    """Beat-indicator dot row must be present."""
    assert 'id="metro-beat-row"' in html


# ---------------------------------------------------------------------------
# JavaScript — scheduler & WAV references
# ---------------------------------------------------------------------------

def test_metronome_js_uses_first_wav(trainer_src: str) -> None:
    """JS must load first.wav as the accent click."""
    assert "first.wav" in trainer_src


def test_metronome_js_uses_click_wav(trainer_src: str) -> None:
    """JS must load click.wav for non-accent beats."""
    assert "click.wav" in trainer_src


def test_metronome_js_has_web_audio_scheduler(trainer_src: str) -> None:
    """Metronome must use Web Audio API AudioContext for drift-free timing."""
    assert "AudioContext" in trainer_src


def test_metronome_js_has_tap_tempo(trainer_src: str) -> None:
    """Tap tempo function must be implemented."""
    assert "metroTap" in trainer_src


def test_metronome_js_scheduler_uses_setinterval(trainer_src: str) -> None:
    """Metronome scheduler must use setInterval for look-ahead timing loop."""
    assert "setInterval" in trainer_src


def test_metronome_js_stop_cancels_scheduled_sources(trainer_src: str) -> None:
    """Metronome stop() must cancel scheduled AudioBufferSourceNodes."""
    assert "scheduledSources" in trainer_src
    assert "src.stop()" in trainer_src or "src.stop (" in trainer_src
    assert "scheduledSources.length = 0" in trainer_src


def test_metronome_js_stop_clears_dot_timeouts(trainer_src: str) -> None:
    """Metronome stop() must clear pending dot update timeouts."""
    assert "scheduledDotHandles" in trainer_src
    assert "clearTimeout" in trainer_src
    assert "scheduledDotHandles.length = 0" in trainer_src
