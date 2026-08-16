"""Focused contract tests for the Copper Creek Wide Open setlist."""

import json
from pathlib import Path

from tools.update_cc_wide_open_setlist_08232026 import (
    EXPECTED_SONG_COUNT,
    PASSENGER_ARTIST,
    PASSENGER_AUDIO_FILE,
    PASSENGER_KEY,
    PASSENGER_SHEET_NAME,
    PASSENGER_TITLE,
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


def test_passenger_reconciliation_source_is_catalog_only() -> None:
    assert (PASSENGER_TITLE, PASSENGER_ARTIST) == (
        "Passenger",
        "Siouxsie & the Banshees",
    )
    assert PASSENGER_KEY == "Dm"
    assert PASSENGER_AUDIO_FILE == "The Passenger - Souxie & the Banshees .mp3"
    assert PASSENGER_SHEET_NAME == "Siouxsie & the Banshees - The Passenger.docx"
    assert not any(row[2] == PASSENGER_TITLE for row in SETLIST)


def test_passenger_catalog_export_has_bpm_and_repo_sheet_link() -> None:
    project_root = Path(__file__).resolve().parents[1]
    export = json.loads(
        (project_root / "catalog" / "setlists" / "catalog_export.json").read_text(
            encoding="utf-8"
        )
    )
    passenger = next(song for song in export["songs"] if song["title"] == PASSENGER_TITLE)

    assert passenger["bpm"] == 140
    assert passenger["sheet_music"] == [
        "catalog/sheet_music/covers/Siouxsie & the Banshees - The Passenger.docx"
    ]
    assert (project_root / passenger["sheet_music"][0]).is_file()
