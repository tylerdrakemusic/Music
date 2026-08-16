"""Focused contract tests for the Copper Creek Wide Open setlist."""

from tools.update_cc_wide_open_setlist_08232026 import (
    EXPECTED_SONG_COUNT,
    SETLIST,
    SETLIST_NOTES,
)


def test_wide_open_source_order_keys_and_notes_are_preserved() -> None:
    assert EXPECTED_SONG_COUNT == 33
    assert len(SETLIST) == EXPECTED_SONG_COUNT
    assert [(row[0], row[1]) for row in SETLIST[:16]] == [(1, position) for position in range(1, 17)]
    assert [(row[0], row[1]) for row in SETLIST[16:]] == [(2, position) for position in range(1, 18)]
    assert [row[2] for row in SETLIST[:3]] == ["Long Train Runnin", "I'm Alright", "Bobby McGee"]
    assert SETLIST[0][3] == "Gm"
    assert SETLIST[16][2:] == ("Pick Up the Pieces", "Fm")
    assert SETLIST[-1][2:] == ("Roll With Changes", "C")
    assert "Passenger" in SETLIST_NOTES
    assert "Dm" in SETLIST_NOTES
    assert "T Call" in SETLIST_NOTES
    assert "Celebrate" in SETLIST_NOTES
    assert "Ab" in SETLIST_NOTES
    assert "throw in" in SETLIST_NOTES
