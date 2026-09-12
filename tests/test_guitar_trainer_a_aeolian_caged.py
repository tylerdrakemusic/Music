"""Regression tests for the A major / F# natural-minor CAGED layout."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402


OPEN_MIDI = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
F_SHARP_NATURAL_MINOR = {1, 2, 4, 6, 8, 9, 11}


def test_a_aeolian_uses_f_sharp_minor_caged_order_through_22nd_fret() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=A&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert [position["label"] for position in positions] == [
        "Position 1 — E shape (2nd fret)",
        "Position 2 — D shape (4th fret)",
        "Position 3 — C shape (9th fret)",
        "Position 4 — A shape (9th fret)",
        "Position 5 — G shape (14th fret)",
        "Position 6 — E shape (14th fret)",
        "Position 7 — D shape (16th fret)",
        "Position 8 — C shape (21st fret)",
    ]
    assert [position["root_string"] for position in positions] == [
        "Low E string",
        "D string",
        "A string",
        "A string",
        "Low E string",
        "Low E string",
        "D string",
        "A string",
    ]
    assert [position["root_fret"] for position in positions] == [
        2, 4, 9, 9, 14, 14, 16, 21
    ]
    assert positions[0]["instructor_phrase"] == (
        "Start on the 2nd fret of the low E string. E Shape."
    )
    assert positions[-1]["instructor_phrase"] == (
        "Start on the 21st fret of the A string. C Shape."
    )

    for position in positions:
        assert {note["string"] for note in position["notes"]} == set(range(1, 7))
        assert any(note["midi"] % 12 == 6 for note in position["notes"])
        assert all(
            0 <= note["fret"] <= 22
            and note["midi"] == OPEN_MIDI[note["string"]] + note["fret"]
            and note["midi"] % 12 in F_SHARP_NATURAL_MINOR
            for note in position["notes"]
        )


def test_a_ionian_remains_identical_with_explicit_mode() -> None:
    with ui.app.test_client() as client:
        default_positions = client.get("/api/scale-positions?key=A").get_json()
        ionian_positions = client.get(
            "/api/scale-positions?key=A&mode=Ionian"
        ).get_json()

    assert ionian_positions == default_positions
