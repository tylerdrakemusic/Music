"""Deterministic BDD coverage for the database source of band management output."""
from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from src.band_mgmt import generate_band_mgmt_panel as panel
from utils import init_db


ROOT = Path(__file__).resolve().parents[2]
SETLIST_SOURCE = ROOT / "catalog" / "setlists"
if str(SETLIST_SOURCE) not in sys.path:
    sys.path.insert(0, str(SETLIST_SOURCE))
export_catalog = importlib.import_module("export_catalog")


@dataclass
class _PanelContext:
    output_path: Path
    connection: sqlite3.Connection | None = None
    failure: Exception | None = None
    inline_data: dict[str, object] | None = None
    html: str = ""


def _create_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE bands (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, genre TEXT, active INTEGER
        );
        CREATE TABLE catalog_songs (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT, key_sig TEXT,
            bpm INTEGER, bpm_source TEXT, genre TEXT, source_file TEXT
        );
        CREATE TABLE band_song_arrangements (
            band_id INTEGER NOT NULL, catalog_song_id INTEGER NOT NULL,
            default_key TEXT, default_bpm INTEGER
        );
        CREATE TABLE setlists (
            id INTEGER PRIMARY KEY, name TEXT, band TEXT, band_id INTEGER,
            gig_date TEXT, venue TEXT, active INTEGER
        );
        CREATE TABLE setlist_songs (
            setlist_id INTEGER, catalog_song_id INTEGER, set_number INTEGER,
            position INTEGER, key_override TEXT, bpm_override INTEGER, notes TEXT
        );
        INSERT INTO bands VALUES (1, 'Copper Creek', 'Country', 1);
        INSERT INTO bands VALUES (2, 'The Groove Unit', 'Blues', 1);
        INSERT INTO catalog_songs VALUES (
            1, 'Database Song', 'Database Artist', 'C', 110, 'manual',
            'Country', 'database-song.mp3'
        );
        INSERT INTO band_song_arrangements VALUES (1, 1, 'D', 126);
        INSERT INTO setlists VALUES (
            7, 'Database Set', 'Copper Creek', 1, '2026-10-23', 'Local Venue', 1
        );
        INSERT INTO setlist_songs VALUES (7, 1, 1, 1, 'E', 128, 'Open strong');
        """
    )
    return connection


def _read_bm_inline(html: str) -> dict[str, object]:
    marker = "const BM_INLINE = "
    start = html.index(marker) + len(marker)
    payload, _ = json.JSONDecoder().raw_decode(html[start:])
    return payload


@scenario(
    "band_mgmt_db_source.feature",
    "DB source wins over stale JSON exports while preserving BM_INLINE behavior",
)
def test_panel_uses_database_data_and_preserves_bm_inline_behavior(tmp_path: Path) -> None:
    pass


@scenario(
    "band_mgmt_db_source.feature",
    "Database failures never fall back to legacy JSON exports",
)
def test_panel_fails_without_using_json_fallback(tmp_path: Path) -> None:
    pass


@given(
    "an isolated heartmusic database contains the band catalog arrangement and active setlist",
    target_fixture="panel_context",
)
def isolated_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> _PanelContext:
    output_path = tmp_path / "band_management_panel.html"
    connection = _create_database()
    request.addfinalizer(connection.close)
    monkeypatch.setattr(init_db, "get_connection", lambda: connection)
    monkeypatch.setattr(panel, "OUTPUT_HTML", output_path)
    monkeypatch.setattr(panel, "load_inventory_data", lambda: [])
    sheet_music = tmp_path / "catalog" / "sheet_music"
    sheet_music.mkdir(parents=True)
    (sheet_music / "Database Song.pdf").write_bytes(b"isolated sheet-music fixture")
    monkeypatch.setattr(export_catalog, "SHEET_MUSIC", sheet_music)
    return _PanelContext(output_path=output_path, connection=connection)


@given("legacy JSON exports contain stale band and catalog values")
def stale_exports(
    panel_context: _PanelContext, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_path = tmp_path / "catalog_export.json"
    setlist_path = tmp_path / "setlist_active_export.json"
    catalog_path.write_text(
        json.dumps({"exported_at": "stale", "songs": [{"title": "STALE JSON SONG"}]}),
        encoding="utf-8",
    )
    setlist_path.write_text(
        json.dumps({"exported_at": "stale", "songs": [], "setlist": {"name": "STALE"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(panel, "CATALOG_JSON", catalog_path, raising=False)
    monkeypatch.setattr(panel, "SETLIST_JSON", setlist_path, raising=False)


@given("legacy JSON exports contain a recognizable fallback value", target_fixture="panel_context")
def stale_exports_for_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _PanelContext:
    catalog_path = tmp_path / "catalog_export.json"
    setlist_path = tmp_path / "setlist_active_export.json"
    catalog_path.write_text(
        json.dumps({"exported_at": "stale", "songs": [{"title": "STALE JSON FALLBACK"}]}),
        encoding="utf-8",
    )
    setlist_path.write_text(
        json.dumps({"exported_at": "stale", "songs": [], "setlist": {}}),
        encoding="utf-8",
    )
    output_path = tmp_path / "band_management_panel.html"
    monkeypatch.setattr(panel, "CATALOG_JSON", catalog_path, raising=False)
    monkeypatch.setattr(panel, "SETLIST_JSON", setlist_path, raising=False)
    monkeypatch.setattr(panel, "OUTPUT_HTML", output_path)
    monkeypatch.setattr(panel, "load_inventory_data", lambda: [])
    return _PanelContext(output_path=output_path)


@given(parsers.parse("the database {failure} occurs"))
def database_failure(
    failure: str,
    panel_context: _PanelContext,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    if failure == "open":
        def fail_to_open() -> sqlite3.Connection:
            raise sqlite3.OperationalError("database open failed")

        monkeypatch.setattr(init_db, "get_connection", fail_to_open)
        return

    connection = sqlite3.connect(":memory:")
    request.addfinalizer(connection.close)
    panel_context.connection = connection
    monkeypatch.setattr(init_db, "get_connection", lambda: connection)


@when("band management output is generated")
def generate_panel(panel_context: _PanelContext) -> None:
    try:
        panel.main()
    except Exception as exc:
        panel_context.failure = exc
    else:
        panel_context.html = panel_context.output_path.read_text(encoding="utf-8")
        panel_context.inline_data = _read_bm_inline(panel_context.html)


@then("the existing BM_INLINE shape is populated from the database")
def assert_database_payload(panel_context: _PanelContext) -> None:
    assert panel_context.failure is None, f"generation failed: {panel_context.failure}"
    assert panel_context.inline_data is not None
    payload = panel_context.inline_data
    assert isinstance(payload.get("exported_at"), str) and payload["exported_at"]
    bands = payload.get("bands")
    assert isinstance(bands, list) and len(bands) == 2
    copper_creek = next(band for band in bands if band["id"] == 1)
    assert copper_creek["name"] == "Copper Creek"
    assert copper_creek["active"] is True
    assert copper_creek["catalog"]["count"] == 1
    assert copper_creek["catalog"]["songs"][0]["title"] == "Database Song"


@then("the band selector catalog active setlist BPM sheet music and audio behavior are preserved")
def assert_panel_behavior_data(panel_context: _PanelContext) -> None:
    assert panel_context.inline_data is not None
    bands = panel_context.inline_data["bands"]
    copper_creek = next(band for band in bands if band["id"] == 1)
    groove_unit = next(band for band in bands if band["id"] == 2)
    catalog_song = copper_creek["catalog"]["songs"][0]
    setlist = copper_creek["setlist"]
    setlist_song = setlist["songs"][0]
    assert groove_unit["name"] == "The Groove Unit"
    assert catalog_song["key"] == "D" and catalog_song["bpm"] == 126
    assert catalog_song["sheet_music"] == ["catalog/sheet_music/Database Song.pdf"]
    assert catalog_song["audio_url"].startswith("file:///")
    assert setlist["setlist"]["name"] == "Database Set"
    assert setlist["count"] == 1
    assert setlist_song["key"] == "E" and setlist_song["bpm"] == 128
    assert setlist_song["audio_url"].startswith("file:///")
    assert "STALE JSON SONG" not in panel_context.html
    assert "bm-band-select" in panel_context.html


@then("generation fails clearly with a database error")
def assert_database_failure(panel_context: _PanelContext) -> None:
    assert isinstance(panel_context.failure, RuntimeError)
    message = str(panel_context.failure).lower()
    assert "heartmusic.db" in message
    assert "open" in message or "query" in message


@then("the legacy JSON value is never returned")
def assert_no_json_fallback(panel_context: _PanelContext) -> None:
    assert not panel_context.output_path.exists()
    assert "STALE JSON FALLBACK" not in panel_context.html
