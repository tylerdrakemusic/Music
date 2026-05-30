"""
BFX-20260530-recently-played-stuck-waiting

Verify that both the TJD Radio standalone player (WEB_PLAYER_HTML) and the
Music Dashboard (DASHBOARD_HTML) clear the "Waiting…" placeholder and show
"Nothing played yet" when the radio is online but history is empty.
"""
from __future__ import annotations

import re
import sys
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
