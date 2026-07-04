"""TDD tests for src/utils/bpm_lookup.py
FR-20260703-music-bpm-autolookup

Covers automated BPM lookup via the GetSongBPM API:
  - successful lookup returns a BpmResult
  - no-match response returns None
  - HTTP error status returns None
  - network timeout returns None
  - missing API key returns None without raising

All HTTP calls are fully mocked — zero real network access.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils import bpm_lookup  # noqa: E402


@pytest.fixture(autouse=True)
def _dummy_api_key(monkeypatch):
    """Provide a dummy (non-real) API key for every test via env var."""
    monkeypatch.setenv("GETSONGBPM_API_KEY", "test-key")


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class TestLookupBpmSuccess:
    def test_returns_bpm_result_on_successful_match(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.return_value = _FakeResponse(
            status_code=200,
            json_data={"search": [{"title": "Josie", "tempo": "102"}]},
        )

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is not None
        assert result.bpm == 102.0
        assert result.title == "Josie"
        mock_get.assert_called_once()

    def test_passes_title_and_artist_in_lookup_params(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.return_value = _FakeResponse(
            status_code=200,
            json_data={"search": [{"title": "Dreams", "tempo": "120"}]},
        )

        bpm_lookup.lookup_bpm("Dreams", "Fleetwood Mac")

        _, kwargs = mock_get.call_args
        assert "Dreams" in kwargs["params"]["lookup"]
        assert "Fleetwood Mac" in kwargs["params"]["lookup"]
        assert kwargs["params"]["api_key"] == "test-key"

    def test_sends_browser_like_headers_to_avoid_cloudflare_block(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.return_value = _FakeResponse(
            status_code=200,
            json_data={"search": [{"title": "Josie", "tempo": "102"}]},
        )

        bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        _, kwargs = mock_get.call_args
        headers = kwargs["headers"]
        assert "python-requests" not in headers["User-Agent"]
        assert "Mozilla" in headers["User-Agent"]
        assert headers["Accept"] == "application/json, text/plain, */*"


class TestLookupBpmNoMatch:
    def test_returns_none_on_empty_search_results(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.return_value = _FakeResponse(status_code=200, json_data={"search": []})

        result = bpm_lookup.lookup_bpm("Some Obscure Song", "Unknown Artist")

        assert result is None

    def test_returns_none_when_tempo_missing_from_match(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.return_value = _FakeResponse(
            status_code=200,
            json_data={"search": [{"title": "Josie"}]},
        )

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is None


class TestLookupBpmErrors:
    def test_returns_none_on_http_error_status(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.return_value = _FakeResponse(status_code=500, json_data={})

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is None

    def test_returns_none_on_timeout(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.side_effect = requests.Timeout("connection timed out")

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is None

    def test_returns_none_on_request_exception(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        mock_get.side_effect = requests.ConnectionError("dns failure")

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is None

    def test_returns_none_on_malformed_json(self, mocker):
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")
        bad_response = _FakeResponse(status_code=200)
        bad_response.json = lambda: (_ for _ in ()).throw(ValueError("bad json"))
        mock_get.return_value = bad_response

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is None


class TestLookupBpmMissingApiKey:
    def test_returns_none_when_api_key_env_var_unset(self, monkeypatch, mocker):
        monkeypatch.delenv("GETSONGBPM_API_KEY", raising=False)
        mock_get = mocker.patch("utils.bpm_lookup.requests.get")

        result = bpm_lookup.lookup_bpm("Josie", "Steely Dan")

        assert result is None
        mock_get.assert_not_called()
