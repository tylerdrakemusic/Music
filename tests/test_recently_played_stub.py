"""
BFX-20260530-recently-played-stuck-waiting

Verify that both the TJD Radio standalone player (WEB_PLAYER_HTML) and the
Music Dashboard (DASHBOARD_HTML) clear the "Waiting…" placeholder and show
"Nothing played yet" when the radio is online but history is empty.

Phase 2: icecast history must track finished tracks (the previous track is
recorded when a new one starts), so history is never populated with the
currently-playing track and no filter is needed.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from radio.tjd_radio import WEB_PLAYER_HTML
from analysis.music_dashboard import DASHBOARD_HTML


# ---------------------------------------------------------------------------
# TJD Radio standalone player — pollMeta()
# ---------------------------------------------------------------------------

class TestRadioPlayerRecentlyPlayedStub:
    """WEB_PLAYER_HTML pollMeta() must handle empty history when radio is online."""

    def test_nothing_played_yet_message_present_in_player(self):
        """Template must contain the 'Nothing played yet' fallback string."""
        assert "Nothing played yet" in WEB_PLAYER_HTML

    def test_history_else_branch_present_in_player(self):
        """pollMeta() must have an else branch after the hist.length guard."""
        # Match:  if (hist.length) { ... } else { ... }
        assert re.search(r"if\s*\(hist\.length\).*?}\s*else\s*\{", WEB_PLAYER_HTML, re.DOTALL)

    def test_waiting_placeholder_replaced_not_kept_on_online(self):
        """The static 'Waiting for tracks...' placeholder must not be the sole
        content — the else branch must overwrite it when radio is live."""
        # Confirm the else block assigns to hEl.innerHTML
        assert re.search(
            r"else\s*\{[^}]*hEl\.innerHTML\s*=",
            WEB_PLAYER_HTML,
            re.DOTALL,
        )


# ---------------------------------------------------------------------------
# Music Dashboard — pollRadio()
# ---------------------------------------------------------------------------

class TestDashboardRecentlyPlayedStub:
    """DASHBOARD_HTML pollRadio() must handle empty history when radio is online."""

    def test_nothing_played_yet_message_present_in_dashboard(self):
        """Dashboard template must contain the 'Nothing played yet' fallback."""
        assert "Nothing played yet" in DASHBOARD_HTML

    def test_history_else_branch_present_in_dashboard(self):
        """pollRadio() must have an else branch after the hist.length guard."""
        assert re.search(r"if\s*\(hist\.length\).*?}\s*else\s*\{", DASHBOARD_HTML, re.DOTALL)

    def test_waiting_placeholder_replaced_not_kept_on_online_dashboard(self):
        """The else block must assign to radioHistoryList's innerHTML."""
        assert re.search(
            r"else\s*\{[^}]*hEl\.innerHTML\s*=",
            DASHBOARD_HTML,
            re.DOTALL,
        )


# ---------------------------------------------------------------------------
# Icecast history poller — must log FINISHED tracks, not the starting track
# ---------------------------------------------------------------------------

class TestIcecastHistoryTracksFinishedNotStarted:
    """_poll_icecast_history must record the previous track when a new one is
    detected, so history never contains the currently-playing track and no
    filter pass is needed in /api/now_playing."""

    def setup_method(self):
        import radio.tjd_radio as tjd
        tjd._icecast_history.clear()
        tjd._icecast_current_title = ""
        tjd._icecast_current_artist = ""
        tjd._icecast_started_at = 0.0

    def teardown_method(self):
        import radio.tjd_radio as tjd
        tjd._icecast_history.clear()
        tjd._icecast_current_title = ""
        tjd._icecast_current_artist = ""
        tjd._icecast_started_at = 0.0

    def _run_poll_iterations(self, monkeypatch, titles: list[str]) -> None:
        """Run _poll_icecast_history for exactly len(titles) iterations."""
        import radio.tjd_radio as tjd

        title_iter = iter(titles)
        sleep_calls = [0]

        def fake_source(_url):
            return {"title": next(title_iter, titles[-1]), "artist": "Test Artist"}

        def stopper(_n):
            sleep_calls[0] += 1
            if sleep_calls[0] >= len(titles):
                raise StopIteration

        monkeypatch.setattr(tjd, "fetch_icecast_source", fake_source)
        monkeypatch.setattr(tjd, "normalize_icecast_metadata", lambda t, a: (t, a))
        monkeypatch.setattr(time, "sleep", stopper)

        with pytest.raises(StopIteration):
            tjd._poll_icecast_history()

    def test_initial_track_detection_leaves_history_empty(self, monkeypatch):
        """After the very first track is detected, history must be empty.
        Nothing has FINISHED playing yet — only the current track is known."""
        import radio.tjd_radio as tjd

        self._run_poll_iterations(monkeypatch, ["Song A"])

        assert len(tjd._icecast_history) == 0, (
            "First detected track must not be added to history — it hasn't finished"
        )
        assert tjd._icecast_current_title == "Song A"

    def test_second_track_adds_first_track_to_history(self, monkeypatch):
        """When the second track starts, the first (now finished) must be in history."""
        import radio.tjd_radio as tjd

        self._run_poll_iterations(monkeypatch, ["Song A", "Song B"])

        assert len(tjd._icecast_history) == 1
        assert tjd._icecast_history[0]["title"] == "Song A"
        assert tjd._icecast_current_title == "Song B"

    def test_history_never_contains_current_track(self, monkeypatch):
        """After three track changes, the currently-playing track must not be in history."""
        import radio.tjd_radio as tjd

        self._run_poll_iterations(monkeypatch, ["Song A", "Song B", "Song C"])

        current = tjd._icecast_current_title
        assert current == "Song C"
        assert all(h["title"] != current for h in tjd._icecast_history), (
            "Current track must never appear in history"
        )
        assert len(tjd._icecast_history) == 2
