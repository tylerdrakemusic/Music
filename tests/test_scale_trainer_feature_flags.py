"""Tests for FR-20260808-scale-trainer-flyio-deploy — env-var feature flags
that structurally remove routes from Flask's url_map (not in-handler checks).

Covers:
 1. test_default_flags_all_routes_present_and_index_renders_everything
    — ENABLE_EXERCISE_CARDS/ENABLE_SCALE_LOG unset (default true/true): all
    routes present in app.url_map; GET / includes the streak badge and the
    Exercises tab button.
 2. test_exercise_cards_disabled_removes_routes_and_hides_tab
    — ENABLE_EXERCISE_CARDS=false: /save, /launch, /create, /delete,
    /catalog, /art, /api/sessions, /api/log absent from url_map and 404;
    GET / hides the Exercises tab button and defaults to the Scales tab.
 3. test_scale_log_disabled_removes_route_and_hides_streak_badge
    — ENABLE_SCALE_LOG=false: /api/scale-log absent from url_map and 404;
    GET / omits the streak-badge markup.
 4. test_both_flags_disabled_keeps_always_on_routes_and_skips_stats_call
    — both flags false: /, /health, /api/scale-positions,
    /api/instructor-audio all still work; get_practice_stats() is not called.
 5. test_both_flags_disabled_click_route_still_serves_existing_file
    — /click/<file> (always-on) still works with both flags false.
 6. test_exercise_cards_disabled_skips_session_and_log_db_calls
    — ENABLE_EXERCISE_CARDS=false: index() must not call _list_sessions()/
    _load_log() (same tables as the now-404 /api/sessions and /api/log
    routes) -- a cloud deploy with no DB driver installed would otherwise
    500 on every request to '/' (caught via Docker build+run validation).

Item 5 from the FR spec (zero regression on the pre-existing suite) is
verified by running the full `pytest` suite, not a unit test here.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.ci_unavailable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLICK_DIR = PROJECT_ROOT / "click"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402

# click/*.wav is gitignored — present locally, absent on a fresh checkout.
_click_wav_present = (CLICK_DIR / "click.wav").exists()
requires_click_wav = pytest.mark.skipif(
    not _click_wav_present,
    reason="click/click.wav not present (gitignored WAV — run locally)",
)

_FLAG_VARS = ("ENABLE_EXERCISE_CARDS", "ENABLE_SCALE_LOG")

# Same in-memory schema pattern as test_guitar_trainer_scales.py / test_guitar_trainer_db.py
_SCHEMA = """
CREATE TABLE IF NOT EXISTS guitar_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    song_path TEXT NOT NULL DEFAULT '',
    segments TEXT NOT NULL DEFAULT '[]',
    gradient INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS guitar_training_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER,
    song_path TEXT NOT NULL DEFAULT '',
    seg_start TEXT NOT NULL DEFAULT '',
    seg_end TEXT NOT NULL DEFAULT '',
    repetition INTEGER NOT NULL DEFAULT 1,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    key TEXT,
    position INTEGER,
    exercise_name TEXT,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS scale_practice_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL DEFAULT 'C',
    mode TEXT NOT NULL DEFAULT 'Ionian',
    scale TEXT NOT NULL DEFAULT 'C_major',
    position INTEGER NOT NULL DEFAULT 1,
    bpm INTEGER NOT NULL DEFAULT 60,
    reps INTEGER NOT NULL DEFAULT 1,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class _NoClose:
    """Wrap a sqlite3.Connection so close() is a no-op — allows reuse in tests."""

    def __init__(self, c: sqlite3.Connection) -> None:
        object.__setattr__(self, "_c", c)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_c"), name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return object.__getattribute__(self, "_c").__enter__()

    def __exit__(self, *a):
        return object.__getattribute__(self, "_c").__exit__(*a)


def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


@contextmanager
def _app_with_flags(exercise_cards: str | None, scale_log: str | None):
    """Reload musician_training_ui under the given flag env vars.

    Flask registers routes at module-load time, so the only way to get a
    fresh app/url_map per flag combination is to set the env vars and
    reload the module. Always restores the original env vars and reloads
    back to the ambient state on exit, so later tests (and other test
    files that import training.musician_training_ui) see the standard app.
    """
    saved = {k: os.environ.get(k) for k in _FLAG_VARS}
    try:
        for k, v in zip(_FLAG_VARS, (exercise_cards, scale_log)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(ui)
        yield ui
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(ui)


@contextmanager
def _client_with_flags(exercise_cards: str | None, scale_log: str | None):
    """_app_with_flags, plus an in-memory DB and a ready Flask test client."""
    with _app_with_flags(exercise_cards, scale_log) as mod:
        conn = _make_mem_conn()
        wrapper = _NoClose(conn)
        mod.app.config["TESTING"] = True
        try:
            with patch.object(mod, "get_connection", return_value=wrapper):
                with mod.app.test_client() as c:
                    yield c
        finally:
            conn.close()


# ── 1. Default flags (both unset == true) — zero-regression baseline ─────

def test_default_flags_all_routes_present_and_index_renders_everything():
    with _client_with_flags(None, None) as client:
        rules = {r.rule for r in client.application.url_map.iter_rules()}
        for path in (
            "/save", "/launch", "/create", "/delete", "/catalog", "/art",
            "/api/sessions", "/api/log", "/api/scale-log",
        ):
            assert path in rules, f"{path} missing from url_map with default flags"

        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "streak-badge" in html
        assert "🔥" in html
        assert "tab-btn-exercises" in html
        assert "🎸 Exercises" in html


# ── 2. ENABLE_EXERCISE_CARDS=false ────────────────────────────────────────

def test_exercise_cards_disabled_removes_routes_and_hides_tab():
    with _client_with_flags("false", None) as client:
        rules = {r.rule for r in client.application.url_map.iter_rules()}
        for path in (
            "/save", "/launch", "/create", "/delete", "/catalog", "/art",
            "/api/sessions", "/api/log",
        ):
            assert path not in rules, f"{path} should be absent from url_map"
        # scale-log stays registered — only the exercise-cards flag is false here
        assert "/api/scale-log" in rules

        for path, method in (
            ("/save", "post"), ("/launch", "post"), ("/create", "post"),
            ("/delete", "post"), ("/catalog", "get"), ("/art", "get"),
            ("/api/sessions", "get"), ("/api/log", "get"),
        ):
            resp = getattr(client, method)(path)
            assert resp.status_code == 404, f"{path} should 404, got {resp.status_code}"

        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Check the rendered HTML attribute (double-quoted), not the bare id
        # string — the JS switchTab() function still references
        # getElementById('tab-btn-exercises') defensively (null-checked) even
        # when the button doesn't exist, so a bare substring check would
        # false-positive on that JS reference.
        assert 'id="tab-btn-exercises"' not in html
        assert "🎸 Exercises" not in html
        # Scales tab becomes the default-active tab
        assert 'class="tab-btn active" id="tab-btn-scales"' in html
        assert 'id="tab-scales" class="tab-panel">' in html


# ── 3. ENABLE_SCALE_LOG=false ─────────────────────────────────────────────

def test_scale_log_disabled_removes_route_and_hides_streak_badge():
    with _client_with_flags(None, "false") as client:
        rules = {r.rule for r in client.application.url_map.iter_rules()}
        assert "/api/scale-log" not in rules
        # exercise-cards routes stay registered — only the scale-log flag is false here
        assert "/save" in rules

        assert client.get("/api/scale-log").status_code == 404
        assert client.post("/api/scale-log").status_code == 404

        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "streak-badge" not in html
        assert "🔥" not in html
        # FR-20260808 follow-up: the log widget itself must also be hidden,
        # not just gated on the backend -- it was previously visible but dead
        # (POSTs 404'd silently) when only the route was disabled. Check the
        # actual HTML attribute, not the bare id string -- the JS still
        # references 'scale-log-tbody' via getElementById(...) regardless.
        assert "Scale Practice Log" not in html
        assert 'id="scale-log-tbody"' not in html


# ── 4. Both flags false ───────────────────────────────────────────────────

def test_both_flags_disabled_keeps_always_on_routes_and_skips_stats_call():
    with _client_with_flags("false", "false") as client:
        rules = {r.rule for r in client.application.url_map.iter_rules()}
        for path in ("/", "/health", "/click/<path:filename>",
                     "/api/scale-positions", "/api/instructor-audio"):
            assert path in rules, f"{path} (always-on) missing from url_map"

        with patch.object(ui, "get_practice_stats") as mock_stats:
            resp = client.get("/")
            assert resp.status_code == 200
            mock_stats.assert_not_called()

        assert client.get("/health").status_code == 200
        assert client.get("/api/scale-positions?key=C").status_code == 200

        resp = client.get("/api/instructor-audio?key=C&position=1")
        assert resp.status_code in (200, 204)


@requires_click_wav
def test_both_flags_disabled_click_route_still_serves_existing_file():
    with _client_with_flags("false", "false") as client:
        resp = client.get("/click/click.wav")
        assert resp.status_code == 200


# ── 6. index() must not query exercise-cards tables when disabled ────────

def test_exercise_cards_disabled_skips_session_and_log_db_calls():
    """/api/sessions and /api/log are gated behind ENABLE_EXERCISE_CARDS, so
    index() must not query the same tables via _list_sessions()/_load_log()
    when the flag is off -- a cloud deploy with no DB driver installed would
    otherwise 500 on every request to '/' (caught via Docker build+run
    validation, not by the mocked-connection tests above).
    """
    with _client_with_flags("false", None) as client:
        with patch.object(ui, "_list_sessions") as mock_sessions, \
                patch.object(ui, "_load_log") as mock_log:
            resp = client.get("/")
            assert resp.status_code == 200
            mock_sessions.assert_not_called()
            mock_log.assert_not_called()

