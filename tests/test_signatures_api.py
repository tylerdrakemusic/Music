"""
Tests for BFX FR-20260530-release-signatures-broken

Covers:
  1. api_signatures returns JSON 500 when get_connection raises RuntimeError
  2. api_signatures returns JSON list of rows when DB is accessible
  3. loadSignatures JS error path: the embedded HTML contains a try/catch
     around the fetch call (static code inspection)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import analysis.music_dashboard as dashboard_mod
from analysis.music_dashboard import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Fix 1 — Python: api_signatures JSON error on RuntimeError
# ---------------------------------------------------------------------------

class TestApiSignaturesErrorHandling:
    def test_returns_json_500_when_db_key_missing(self, client):
        """When get_connection raises RuntimeError, endpoint must return
        JSON (not HTML) with status 500."""
        with patch.object(
            dashboard_mod,
            "get_connection",
            side_effect=RuntimeError("HEARTMUSIC_DB_KEY not set"),
        ):
            res = client.get("/api/signatures")

        assert res.status_code == 500
        data = json.loads(res.data)
        assert "error" in data

    def test_returns_json_500_on_generic_exception(self, client):
        """Any unexpected exception from get_connection must produce JSON 500."""
        with patch.object(
            dashboard_mod,
            "get_connection",
            side_effect=Exception("DB locked"),
        ):
            res = client.get("/api/signatures")

        assert res.status_code == 500
        data = json.loads(res.data)
        assert "error" in data

    def test_content_type_is_json_on_error(self, client):
        """Content-Type must be application/json on error response."""
        with patch.object(
            dashboard_mod,
            "get_connection",
            side_effect=RuntimeError("HEARTMUSIC_DB_KEY not set"),
        ):
            res = client.get("/api/signatures")

        assert "application/json" in res.content_type

    def test_returns_list_on_success(self, client):
        """When DB is accessible and returns rows, endpoint returns JSON list."""
        fake_row = {
            "id": 1,
            "track_id": 42,
            "track_title": "Test Track",
            "album_title": "Test Album",
        }

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = [fake_row]

        with patch.object(dashboard_mod, "get_connection", return_value=mock_conn):
            res = client.get("/api/signatures")

        assert res.status_code == 200
        data = json.loads(res.data)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == 1


# ---------------------------------------------------------------------------
# Fix 2 — JS: loadSignatures has try/catch (static inspection)
# ---------------------------------------------------------------------------

class TestLoadSignaturesJSErrorHandling:
    def test_load_signatures_has_try_catch(self):
        """The DASHBOARD_HTML must contain a try/catch block inside
        loadSignatures() so errors don't propagate unhandled."""
        html = dashboard_mod.DASHBOARD_HTML
        # Find loadSignatures function body
        start = html.find("async function loadSignatures(")
        assert start != -1, "loadSignatures function not found in DASHBOARD_HTML"
        # Find the end of that function (next top-level function or large closing brace)
        # We search for try { within a reasonable window after the function start
        window = html[start : start + 800]
        assert "try {" in window or "try{" in window, (
            "loadSignatures() must contain a try/catch block"
        )

    def test_load_signatures_has_catch(self):
        """The DASHBOARD_HTML must contain a catch block inside loadSignatures()."""
        html = dashboard_mod.DASHBOARD_HTML
        start = html.find("async function loadSignatures(")
        assert start != -1
        window = html[start : start + 800]
        assert "catch" in window, "loadSignatures() must contain a catch handler"

    def test_load_signatures_error_state_message(self):
        """The catch block must set a user-visible error message in sigGrid."""
        html = dashboard_mod.DASHBOARD_HTML
        start = html.find("async function loadSignatures(")
        assert start != -1
        window = html[start : start + 1000]
        assert "sigGrid" in window, (
            "catch block must reference sigGrid to show an error message to the user"
        )
