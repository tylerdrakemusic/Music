"""Tests for Rhyme Grouper hook-worthy line support."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import analysis.music_dashboard as dash_mod
from analysis.music_dashboard import app


def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class _PersistentConn:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    conn = _make_mem_conn()
    yield conn
    conn.close()


@pytest.fixture()
def client(mem_conn: sqlite3.Connection):
    persistent = _PersistentConn(mem_conn)

    @contextmanager
    def _fake_get_connection():
        yield persistent

    app.config["TESTING"] = True
    with patch.object(dash_mod, "get_connection", _fake_get_connection):
        with app.test_client() as c:
            yield c


def test_post_line_marks_hook(client):
    res = client.post(
        "/rhymes/lines",
        json={"line": "Hold the high note", "is_hook": True},
    )

    assert res.status_code == 201
    data = res.get_json()
    assert data["line"] == "Hold the high note"
    assert data["is_hook"] is True


def test_toggle_hook_flag_updates_line(client):
    post_res = client.post(
        "/rhymes/lines",
        json={"line": "Open up the chorus", "is_hook": False},
    )
    assert post_res.status_code == 201
    line_id = post_res.get_json()["id"]

    put_res = client.put(f"/rhymes/lines/{line_id}", json={"is_hook": True})
    assert put_res.status_code == 200
    updated = put_res.get_json()
    assert updated["is_hook"] is True

    revert_res = client.put(f"/rhymes/lines/{line_id}", json={"is_hook": False})
    assert revert_res.status_code == 200
    reverted = revert_res.get_json()
    assert reverted["is_hook"] is False


def test_stats_includes_hook_count(client):
    client.post("/rhymes/lines", json={"line": "First hook line", "is_hook": True})
    client.post("/rhymes/lines", json={"line": "Second line", "is_hook": False})

    res = client.get("/rhymes/stats")
    assert res.status_code == 200
    stats = res.get_json()
    assert stats["hook_lines"] == 1
    assert stats["total_lines"] >= 2


def test_hook_candidate_auto_tags_unhooked_lines(client, monkeypatch):
    client.post("/rhymes/lines", json={"line": "Strong chorus lifts the night", "is_hook": False})
    client.post("/rhymes/lines", json={"line": "Soft bridge whispers out", "is_hook": False})

    class FakeOllama:
        def __init__(self, *args, **kwargs):
            pass

        def ensure_model_available(self, model=None):
            return True

        def generate(self, prompt, timeout=None, model=None):
            return "Strong chorus lifts the night\n"

    monkeypatch.setattr(dash_mod, "_OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(dash_mod, "_OllamaClient", FakeOllama, raising=False)

    res = client.post("/rhymes/hook-candidates")
    assert res.status_code == 200
    data = res.get_json()
    assert data["marked_ids"]
    assert "Strong chorus lifts the night" in data["marked_lines"]

    stats = client.get("/rhymes/stats").get_json()
    assert stats["hook_lines"] == 1


def test_ollama_fallback_uses_available_model(client, monkeypatch):
    class FallbackOllama:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")

        def list_models(self):
            return [
                {"name": "llama3.3:70b"},
                {"name": "llama3:70b"},
                {"name": "llama3.1:8b"},
            ]

        def generate(self, prompt, timeout=None):
            if self.model == "llama3.3:70b":
                raise Exception("model 'llama3.3:70b' not found")
            if self.model == "llama3:70b":
                raise Exception("model 'llama3:70b' not found")
            return "Fallback success"

    monkeypatch.setattr(dash_mod, "_OllamaClient", FallbackOllama, raising=False)

    result = dash_mod._generate_with_ollama_fallback("Test prompt", timeout=5.0)
    assert result == "Fallback success"


def test_ollama_timeout_falls_back_to_smaller_model(client, monkeypatch):
    class FallbackOllama:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")

        def list_models(self):
            return [
                {"name": "llama3.3:70b"},
                {"name": "llama3:70b"},
                {"name": "llama3.1:8b"},
            ]

        def generate(self, prompt, timeout=None):
            if self.model == "llama3.3:70b":
                raise Exception("timed out waiting for response")
            if self.model == "llama3:70b":
                raise Exception("model 'llama3:70b' not found")
            return "Timeout fallback success"

    monkeypatch.setattr(dash_mod, "_OllamaClient", FallbackOllama, raising=False)

    result = dash_mod._generate_with_ollama_fallback("Test prompt", timeout=5.0)
    assert result == "Timeout fallback success"


def test_hook_candidate_returns_503_when_ollama_unavailable(client, monkeypatch):
    client.post("/rhymes/lines", json={"line": "Lost in the verse", "is_hook": False})
    monkeypatch.setattr(dash_mod, "_OLLAMA_AVAILABLE", False)

    res = client.post("/rhymes/hook-candidates")
    assert res.status_code == 503
    data = res.get_json()
    assert data["error"] == "Ollama not available"


def test_fallback_uses_fast_timeout_on_non_final_attempts_when_no_timeout_given(monkeypatch):
    """A hung/broken primary model must not block the whole request behind the
    full generation timeout — only the final fallback candidate gets the full
    (unbounded) timeout budget."""
    seen_timeouts: list[float | None] = []

    class SlowThenFastOllama:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")

        def list_models(self):
            return [
                {"name": "llama3.3:70b"},
                {"name": "llama3:70b"},
                {"name": "llama3.1:8b"},
            ]

        def generate(self, prompt, timeout=None):
            seen_timeouts.append(timeout)
            if self.model in ("llama3.3:70b", "llama3:70b"):
                raise Exception("Cannot reach Ollama at http://127.0.0.1:11434: timed out")
            return "Fast fallback success"

    monkeypatch.setattr(dash_mod, "_OllamaClient", SlowThenFastOllama, raising=False)

    result = dash_mod._generate_with_ollama_fallback("Test prompt")

    assert result == "Fast fallback success"
    # Non-final attempts (llama3.3:70b, llama3:70b) must use a bounded fast-fail
    # timeout, not None (unbounded).
    assert seen_timeouts[0] is not None and seen_timeouts[0] <= 30.0
    assert seen_timeouts[1] is not None and seen_timeouts[1] <= 30.0
    # Final attempt (llama3.1:8b) keeps the caller's original timeout (None = full budget).
    assert seen_timeouts[2] is None


def test_fallback_respects_explicit_timeout_for_all_attempts(monkeypatch):
    """When the caller passes an explicit timeout, every attempt should use it
    unchanged — the fast-fail default only applies when timeout is None."""
    seen_timeouts: list[float | None] = []

    class ExplicitTimeoutOllama:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")

        def list_models(self):
            return [{"name": "llama3.3:70b"}, {"name": "llama3.1:8b"}]

        def generate(self, prompt, timeout=None):
            seen_timeouts.append(timeout)
            if self.model == "llama3.3:70b":
                raise Exception("timed out waiting for response")
            return "Explicit timeout success"

    monkeypatch.setattr(dash_mod, "_OllamaClient", ExplicitTimeoutOllama, raising=False)

    result = dash_mod._generate_with_ollama_fallback("Test prompt", timeout=42.0)

    assert result == "Explicit timeout success"
    assert seen_timeouts == [42.0, 42.0]
