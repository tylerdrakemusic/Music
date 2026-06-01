"""Tests for FR-20260531-chord-sheet-ui — Chord Sheet tab in Music Dashboard.

AC coverage:
 1. test_songs_endpoint_lists_json_files       — GET /chord-sheet/songs
 2. test_parse_endpoint_returns_json_string    — POST /chord-sheet/parse (Ollama mock)
 3. test_parse_endpoint_ollama_unavailable_returns_503
 4. test_generate_workflow_b_creates_docx      — POST /chord-sheet/generate workflow=B
 5. test_generate_saves_json_workflow_a        — POST /chord-sheet/generate workflow=A
 6. test_download_endpoint_serves_docx         — GET /chord-sheet/download/<filename>
 7. test_merge_calls_gh_pr_merge               — POST /chord-sheet/merge
 8. test_lyrics_only_flag_produces_lyrics_only_docx
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import _SCHEMA_SQL, _SEED_SQL  # noqa: PLC2701


# ── DB helpers (needed for Flask client even though chord-sheet routes skip DB) ─

def _make_mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.executescript(_SEED_SQL)
    return conn


class _PersistentConn:
    """Wrap a sqlite3.Connection so close() is a no-op."""

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


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def mem_conn():
    conn = _make_mem_conn()
    yield conn
    conn.close()


@pytest.fixture()
def client(mem_conn):
    """Flask test client backed by an in-memory DB."""
    import analysis.music_dashboard as dash_mod
    from analysis.music_dashboard import app

    persistent = _PersistentConn(mem_conn)

    @contextmanager
    def _fake_get_connection():
        yield persistent

    app.config["TESTING"] = True
    with patch.object(dash_mod, "get_connection", _fake_get_connection):
        with app.test_client() as c:
            yield c


# ── sample song data ──────────────────────────────────────────────────────────

_SAMPLE_SONG = {
    "title": "Test Song",
    "artist": "Test Artist",
    "key": "C",
    "bpm": "120",
    "sections": [
        {
            "name": "Verse 1",
            "lines": [
                {"chords": "C G | Am F", "lyrics": "Test lyric line"},
            ],
        }
    ],
}


# ── tests ─────────────────────────────────────────────────────────────────────

def test_songs_endpoint_lists_json_files(client, tmp_path):
    """GET /chord-sheet/songs returns sorted list of .json filenames from templates dir."""
    import analysis.music_dashboard as dash_mod

    (tmp_path / "Song_A_Artist_Key_C.json").write_text("{}", encoding="utf-8")
    (tmp_path / "Song_B_Artist_Key_G.json").write_text("{}", encoding="utf-8")
    # non-json files should be ignored
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    with patch.object(dash_mod, "_CHORD_SHEET_TEMPLATES_DIR", tmp_path, create=True):
        resp = client.get("/chord-sheet/songs")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.get_json()
    assert isinstance(data, list)
    assert "Song_A_Artist_Key_C.json" in data
    assert "Song_B_Artist_Key_G.json" in data
    assert "ignore.txt" not in data


def test_parse_endpoint_returns_json_string(client):
    """POST /chord-sheet/parse returns valid JSON via mocked OllamaClient."""
    import analysis.music_dashboard as dash_mod

    mock_ollama_cls = MagicMock()
    mock_ollama_cls.return_value.generate.return_value = json.dumps(_SAMPLE_SONG)

    with patch.object(dash_mod, "_OllamaClient", mock_ollama_cls, create=True), \
         patch.object(dash_mod, "_OLLAMA_AVAILABLE", True, create=True):
        resp = client.post(
            "/chord-sheet/parse",
            json={"raw_text": "C G Am F\nTest lyric line"},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert "json_string" in data, f"Missing json_string in {data}"
    parsed = json.loads(data["json_string"])
    assert parsed["title"] == "Test Song"


def test_parse_endpoint_ollama_unavailable_returns_503(client):
    """POST /chord-sheet/parse returns 503 when Ollama is not available."""
    import analysis.music_dashboard as dash_mod

    with patch.object(dash_mod, "_OLLAMA_AVAILABLE", False, create=True):
        resp = client.post(
            "/chord-sheet/parse",
            json={"raw_text": "C G Am F"},
        )

    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}"
    data = resp.get_json()
    assert "error" in data


def test_generate_workflow_b_creates_docx(client, tmp_path):
    """POST /chord-sheet/generate workflow=B returns filename and download_url."""
    import analysis.music_dashboard as dash_mod

    json_filename = "Test_Song_Test_Artist_Key_C.json"
    (tmp_path / json_filename).write_text(json.dumps(_SAMPLE_SONG), encoding="utf-8")

    expected_docx = tmp_path / "Test_Song_Test_Artist_Key_C.docx"

    def _fake_build_docx(song_data, output_path, **kwargs):
        Path(output_path).write_bytes(b"PK fake docx")
        return Path(output_path)

    def _fake_compute_output_path(song, outdir, lyrics_only=False):
        return expected_docx

    with patch.object(dash_mod, "_CHORD_SHEET_TEMPLATES_DIR", tmp_path, create=True), \
         patch.object(dash_mod, "_CHORD_SHEET_DOCS_DIR", tmp_path, create=True), \
         patch.object(dash_mod, "_CHORD_SHEET_AVAILABLE", True, create=True), \
         patch("analysis.music_dashboard.build_docx", _fake_build_docx, create=True), \
         patch("analysis.music_dashboard.compute_output_path", _fake_compute_output_path, create=True):
        resp = client.post(
            "/chord-sheet/generate",
            json={"workflow": "B", "song_path": json_filename},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
    data = resp.get_json()
    assert "download_url" in data, f"Missing download_url in {data}"
    assert "filename" in data, f"Missing filename in {data}"


def test_generate_saves_json_workflow_a(client, tmp_path):
    """POST /chord-sheet/generate workflow=A writes JSON to song_templates dir."""
    import analysis.music_dashboard as dash_mod

    json_content = json.dumps(_SAMPLE_SONG)
    expected_docx = tmp_path / "Test_Song_Test_Artist_Key_C.docx"

    def _fake_build_docx(song_data, output_path, **kwargs):
        Path(output_path).write_bytes(b"PK fake docx")
        return Path(output_path)

    def _fake_compute_output_path(song, outdir, lyrics_only=False):
        return expected_docx

    with patch.object(dash_mod, "_CHORD_SHEET_TEMPLATES_DIR", tmp_path, create=True), \
         patch.object(dash_mod, "_CHORD_SHEET_DOCS_DIR", tmp_path, create=True), \
         patch.object(dash_mod, "_CHORD_SHEET_AVAILABLE", True, create=True), \
         patch("analysis.music_dashboard.build_docx", _fake_build_docx, create=True), \
         patch("analysis.music_dashboard.compute_output_path", _fake_compute_output_path, create=True):
        resp = client.post(
            "/chord-sheet/generate",
            json={"workflow": "A", "json_content": json_content},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
    # JSON file written to templates dir
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1, f"Expected 1 JSON file, found {written}"
    saved = json.loads(written[0].read_text(encoding="utf-8"))
    assert saved["title"] == "Test Song"


def test_download_endpoint_serves_docx(client, tmp_path):
    """GET /chord-sheet/download/<filename> serves the file if it exists."""
    import analysis.music_dashboard as dash_mod

    docx_name = "Test_Song_Test_Artist_Key_C.docx"
    (tmp_path / docx_name).write_bytes(b"PK fake docx content")

    with patch.object(dash_mod, "_CHORD_SHEET_DOCS_DIR", tmp_path, create=True):
        resp = client.get(f"/chord-sheet/download/{docx_name}")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert resp.data == b"PK fake docx content"


def test_merge_calls_gh_pr_merge(client):
    """POST /chord-sheet/merge calls 'gh pr merge' with the supplied pr_url."""
    pr_url = "https://github.com/tylerdrakemusic/Music/pull/98"
    calls: list = []

    def _fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    with patch("subprocess.run", side_effect=_fake_run):
        resp = client.post("/chord-sheet/merge", json={"pr_url": pr_url})

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
    merge_calls = [c for c in calls if "gh" in c and "pr" in c and "merge" in c]
    assert merge_calls, f"No 'gh pr merge' call found in: {calls}"
    assert any(pr_url in c for c in merge_calls), f"PR URL not found in calls: {merge_calls}"


def test_lyrics_only_flag_produces_lyrics_only_docx(client, tmp_path):
    """lyrics_only=true causes compute_output_path to be called with lyrics_only=True."""
    import analysis.music_dashboard as dash_mod

    json_filename = "Test_Song_Test_Artist_Key_C.json"
    (tmp_path / json_filename).write_text(json.dumps(_SAMPLE_SONG), encoding="utf-8")

    expected_docx = tmp_path / "Test_Song_Test_Artist_Key_C_Lyrics_Only.docx"
    received_flags: list = []

    def _fake_compute_output_path(song, outdir, lyrics_only=False):
        received_flags.append(lyrics_only)
        return expected_docx

    def _fake_build_docx(song_data, output_path, **kwargs):
        Path(output_path).write_bytes(b"PK fake docx")
        return Path(output_path)

    with patch.object(dash_mod, "_CHORD_SHEET_TEMPLATES_DIR", tmp_path, create=True), \
         patch.object(dash_mod, "_CHORD_SHEET_DOCS_DIR", tmp_path, create=True), \
         patch.object(dash_mod, "_CHORD_SHEET_AVAILABLE", True, create=True), \
         patch("analysis.music_dashboard.build_docx", _fake_build_docx, create=True), \
         patch("analysis.music_dashboard.compute_output_path", _fake_compute_output_path, create=True):
        resp = client.post(
            "/chord-sheet/generate",
            json={"workflow": "B", "song_path": json_filename, "lyrics_only": True},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
    assert received_flags == [True], f"Expected lyrics_only=True, got: {received_flags}"
    data = resp.get_json()
    assert "Lyrics_Only" in data.get("filename", ""), \
        f"Expected 'Lyrics_Only' in filename, got: {data.get('filename')}"
