"""Regression tests for the Ab major / F Aeolian trainer contract."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402


F_NATURAL_MINOR_PITCH_CLASSES = {0, 1, 3, 5, 7, 8, 10}
OPEN_MIDI = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
ROOT_STRING_NUMBER = {"Low E string": 6, "D string": 4, "A string": 5}

EXPECTED_OFFSETS = [
    [[6, 0], [6, 2], [6, 3], [5, 0], [5, 2], [5, 3], [4, 0], [4, 2], [4, 4], [3, 0], [3, 2], [2, 0], [2, 1], [2, 3], [1, 0], [1, 2], [1, 3]],
    [[6, 0], [6, 1], [6, 3], [5, 0], [5, 1], [5, 3], [4, 0], [4, 2], [4, 3], [3, 0], [3, 2], [3, 3], [2, 1], [2, 3], [1, 0], [1, 1], [1, 3]],
    [[6, -4], [6, -2], [6, 0], [5, -4], [5, -2], [5, 0], [4, -3], [4, -2], [4, 0], [3, -3], [3, -2], [2, -4], [2, -2], [2, 0], [1, -4], [1, -2], [1, 0]],
    [[6, 0], [6, 1], [6, 3], [5, 0], [5, 2], [5, 3], [4, 0], [4, 2], [4, 3], [3, 0], [3, 2], [2, 0], [2, 1], [2, 3], [1, 0], [1, 1], [1, 3]],
    [[6, 0], [5, -3], [5, -2], [5, 0], [4, -3], [4, -2], [4, 0], [3, -3], [3, -1], [2, -4], [2, -2], [2, 0], [1, -4], [1, -2], [1, 0]],
    [[6, 0], [6, 2], [6, 3], [5, 0], [5, 2], [5, 3], [4, 0], [4, 2], [4, 4], [3, 0], [3, 2], [2, 0], [2, 1], [2, 3], [1, 0], [1, 2], [1, 3]],
    [[6, 0], [6, 1], [6, 3], [5, 0], [5, 1], [5, 3], [4, 0], [4, 2], [4, 3], [3, 0], [3, 2], [3, 3], [2, 1], [2, 3], [1, 0], [1, 1], [1, 3]],
    [[6, -4], [6, -2], [6, 0], [5, -4], [5, -2], [5, 0], [4, -3], [4, -2], [4, 0], [3, -3], [3, -2], [2, -4], [2, -2], [2, 0], [1, -4], [1, -2], [1, 0]],
    [[6, 0], [6, 1], [5, 0], [5, 2], [4, 0], [4, 2], [3, 0], [3, 2], [2, 0], [2, 1], [1, 0], [1, 1]],
]
EXPECTED_REPEAT_OFFSETS = [
    [[6, 0], [6, 1], [6, 3], [5, 0], [5, 1], [5, 3], [4, 0], [4, 2], [4, 3], [3, 0], [3, 2], [3, 3], [2, 1], [2, 3], [1, 0], [1, 1], [1, 3]],
    [[6, -4], [6, -2], [6, 0], [5, -4], [5, -2], [5, 0], [4, -3], [4, -2], [4, 0], [3, -3], [3, -2], [2, -4], [2, -2], [2, 0], [1, -4], [1, -2], [1, 0]],
    [[6, 0], [6, 1], [6, 3], [5, 0], [5, 2], [5, 3], [4, 0], [4, 2], [4, 3], [3, 0], [3, 2], [2, 0], [2, 1], [2, 3], [1, 0], [1, 1], [1, 3]],
]

REPEAT_SOURCE_BASELINES = {
    6: ("D", EXPECTED_OFFSETS[1]),
    7: ("C", EXPECTED_OFFSETS[2]),
    8: ("A", EXPECTED_OFFSETS[3]),
}


def _shape_names(positions: list[dict]) -> list[str]:
    return [
        position["label"].split(" — ", 1)[1].split(" shape", 1)[0]
        for position in positions
    ]


def _get_positions() -> list[dict]:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=Ab&mode=Aeolian")

    assert response.status_code == 200
    return response.get_json()


def _offset_rows(position: dict) -> list[tuple[int, int]]:
    return sorted(
        (note["string"], note["fret"] - position["root_fret"])
        for note in position["notes"]
    )


def test_ab_aeolian_uses_confirmed_selector_and_minor_caged_order() -> None:
    positions = _get_positions()

    assert _shape_names(positions) == ["E", "D", "C", "A", "G", "E", "D", "C"]
    assert [position["root_string"] for position in positions] == [
        "Low E string", "D string", "A string", "A string", "Low E string",
        "Low E string", "D string", "A string",
    ]
    assert [position["root_fret"] for position in positions] == [1, 3, 8, 8, 13, 13, 15, 20]
    assert positions[0]["label"] == "Position 1 — E shape (1st fret)"
    assert positions[0]["instructor_phrase"] == "Start on the 1st fret of the low E string. E Shape."


def test_ab_aeolian_has_explicit_shape_geometry_and_valid_minor_notes() -> None:
    positions = _get_positions()

    assert len(positions) == 8
    for position, expected_offsets in zip(positions, EXPECTED_OFFSETS[:8]):
        notes = position["notes"]
        assert {note["string"] for note in notes} == set(range(1, 7))
        root_string = ROOT_STRING_NUMBER[position["root_string"]]
        assert (
            OPEN_MIDI[root_string] + position["root_fret"]
        ) % 12 == 5
        assert sorted(
            (note["string"], note["fret"] - position["root_fret"])
            for note in notes
        ) == sorted(tuple(offset) for offset in expected_offsets)
        assert all(
            0 <= note["fret"] <= 22
            and 0 <= note["midi"] <= 127
            and note["midi"] == OPEN_MIDI[note["string"]] + note["fret"]
            and note["midi"] % 12 in F_NATURAL_MINOR_PITCH_CLASSES
            for note in notes
        )


def test_ab_aeolian_repeats_use_actual_d_c_a_shape_geometry() -> None:
    positions = _get_positions()

    assert len(positions) == 8
    for repeat_index, (repeat, root_string, base_fret, offsets) in enumerate(zip(
        positions[6:8],
        ("D string", "A string"),
        (3, 8),
        EXPECTED_REPEAT_OFFSETS[:2],
    ), start=6):
        expected_shape, source_offsets = REPEAT_SOURCE_BASELINES[repeat_index]
        assert repeat["label"].split(" — ", 1)[1].split(" shape", 1)[0] == expected_shape
        assert repeat["root_string"] == root_string
        assert repeat["root_fret"] == base_fret + 12
        # High-fret clipping can alter the relative rows, but a fully visible
        # octave repeat is allowed to preserve the source geometry.
        assert [
            (note["string"], note["fret"], note["midi"])
            for note in repeat["notes"]
        ] == [
            (
                string,
                base_fret + delta + 12,
                OPEN_MIDI[string] + base_fret + delta + 12,
            )
            for string, delta in offsets
            if (
                0 <= base_fret + delta + 12 <= 22
                and (
                    OPEN_MIDI[string] + base_fret + delta + 12
                ) % 12 in F_NATURAL_MINOR_PITCH_CLASSES
            )
        ]


def test_f_major_remains_non_aeolian_and_dropdown_contract_is_present(monkeypatch) -> None:
    monkeypatch.setattr(ui, "ENABLE_EXERCISE_CARDS", False)
    monkeypatch.setattr(ui, "ENABLE_SCALE_LOG", False)

    with ui.app.test_client() as client:
        major = client.get("/api/scale-positions?key=Ab&mode=Ionian").get_json()
        html = client.get("/").get_data(as_text=True)

    assert major != ui.get_scale_positions("Ab", "Aeolian")
    assert '<option value="Ab">Ab major / F minor</option>' in html
    assert 'option value="Aeolian">Aeolian</option>' in html