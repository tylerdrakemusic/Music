"""Regression tests for the G-parent-key / E-Aeolian CAGED layout."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402


def _shape_names(positions: list[dict]) -> list[str]:
    return [
        position["label"].split(" — ", 1)[1].split(" shape", 1)[0]
        for position in positions
    ]


def _fret_rows(position: dict) -> list[list[int]]:
    return [
        sorted(note["fret"] for note in position["notes"] if note["string"] == string)
        for string in range(6, 0, -1)
    ]


def test_g_aeolian_e_shape_positions_use_correct_g_string_and_valid_notes() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=G&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["E", "D", "C", "A", "G", "E", "D", "C", "A"]
    assert [position["root_fret"] for position in positions] == [0, 2, 7, 7, 12, 12, 14, 19, 19]
    assert [position["root_string"] for position in positions] == [
        "Low E string",
        "D string",
        "A string",
        "A string",
        "Low E string",
        "Low E string",
        "D string",
        "A string",
        "A string",
    ]
    assert [
        note["fret"]
        for note in positions[0]["notes"]
        if note["string"] == 3
    ] == [0, 2]
    assert [
        note["fret"]
        for note in positions[5]["notes"]
        if note["string"] == 3
    ] == [12, 14]
    assert [
        note["fret"]
        for note in positions[3]["notes"]
        if note["string"] == 3
    ] == [7, 9]
    assert all(
        note["midi"] % 12 != 6
        for note in positions[3]["notes"]
        if note["string"] == 3
    )
    assert _fret_rows(positions[0]) == [
        [0, 2, 3],
        [0, 2, 3],
        [0, 2, 4],
        [0, 2],
        [0, 1, 3],
        [0, 2, 3],
    ]
    open_midi = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
    e_aeolian_pitch_classes = {4, 6, 7, 9, 11, 0, 2}
    assert all(
        note["midi"] == open_midi[note["string"]] + note["fret"]
        and note["midi"] % 12 in e_aeolian_pitch_classes
        for position in positions
        for note in position["notes"]
    )


def test_g_aeolian_positions_stay_within_fretboard_through_fret_22() -> None:
    with ui.app.test_client() as client:
        positions = client.get("/api/scale-positions?key=G&mode=Aeolian").get_json()

    assert len(positions) == 9
    assert all(
        0 <= note["fret"] <= 22
        for position in positions
        for note in position["notes"]
    )
    assert all(
        {note["string"] for note in position["notes"]} == {1, 2, 3, 4, 5, 6}
        for position in positions
    )


def test_g_aeolian_d_string_rows_preserve_position_seven_and_nine_geometry() -> None:
    with ui.app.test_client() as client:
        positions = client.get("/api/scale-positions?key=G&mode=Aeolian").get_json()

    natural_minor_pitch_classes = {4, 6, 7, 9, 11, 0, 2}
    assert [
        note["fret"] for note in positions[6]["notes"] if note["string"] == 4
    ] == [14, 16, 17]
    assert [
        note["fret"] for note in positions[8]["notes"] if note["string"] == 4
    ] == [19, 21, 22]
    position_seven_d_string_notes = [
        note for note in positions[6]["notes"] if note["string"] == 4
    ]
    position_nine_d_string_notes = [
        note for note in positions[8]["notes"] if note["string"] == 4
    ]
    assert all(
        note["midi"] == 50 + note["fret"]
        and note["midi"] % 12 in natural_minor_pitch_classes
        and 0 <= note["fret"] <= 22
        for note in position_seven_d_string_notes
    )
    assert any(
        note["fret"] == 22 and note["midi"] % 12 == 0
        for note in position_nine_d_string_notes
    )
    assert all(
        note["midi"] == 50 + note["fret"]
        and note["midi"] % 12 in natural_minor_pitch_classes
        and 0 <= note["fret"] <= 22
        for note in position_nine_d_string_notes
    )


def test_g_aeolian_positions_8_and_9_preserve_translated_shape_geometry() -> None:
    with ui.app.test_client() as client:
        positions = client.get("/api/scale-positions?key=G&mode=Aeolian").get_json()

    assert [position["label"] for position in positions[-2:]] == [
        "Position 8 — C shape (19th fret)",
        "Position 9 — A shape (19th fret)",
    ]
    assert [position["root_string"] for position in positions[-2:]] == [
        "A string",
        "A string",
    ]
    assert [position["root_fret"] for position in positions[-2:]] == [19, 19]
    assert [_fret_rows(position) for position in positions[-2:]] == [
        [
            [15, 17, 19],
            [15, 17, 19],
            [16, 17, 19],
            [16, 17],
            [15, 17, 19],
            [15, 17, 19],
        ],
        [
            [19, 20, 22],
            [19, 21, 22],
            [19, 21, 22],
            [19, 21],
            [19, 20, 22],
            [19, 20, 22],
        ],
    ]
    assert all(
        note["midi"] % 12 != 6
        for note in positions[8]["notes"]
        if note["string"] == 3
    )