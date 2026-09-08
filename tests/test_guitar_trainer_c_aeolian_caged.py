"""Regression tests for the C/Aeolian minor CAGED layout."""
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


def test_c_aeolian_repeats_minor_caged_shapes_with_valid_geometry() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=C&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["A", "G", "E", "D", "C", "A", "G", "E", "D"]
    assert positions[0]["root_string"] == "A string"
    assert positions[0]["root_fret"] == 0
    assert positions[0]["label"] == "Position 1 — A shape (open)"
    assert [position["instructor_phrase"] for position in positions] == [
        "Start on the open A string. A Shape.",
        "Start on the 5th fret of the low E string. G Shape.",
        "Start on the 5th fret of the low E string. E Shape.",
        "Start on the 7th fret of the D string. D Shape.",
        "Start on the 12th fret of the A string. C Shape.",
        "Start on the 12th fret of the A string. A Shape.",
        "Start on the 17th fret of the low E string. G Shape.",
        "Start on the 17th fret of the low E string. E Shape.",
        "Start on the 19th fret of the D string. D Shape.",
    ]
    assert positions[1]["label"] == "Position 2 — G shape (5th fret)"
    assert positions[1]["root_string"] == "Low E string"
    assert positions[1]["root_fret"] == 5
    assert any(
        note["string"] == 5 and note["fret"] == 2
        for note in positions[1]["notes"]
    )
    assert positions[2]["label"] == "Position 3 — E shape (5th fret)"
    assert positions[2]["root_string"] == "Low E string"
    assert positions[2]["root_fret"] == 5
    assert {
        string: sorted(note["fret"] for note in positions[2]["notes"] if note["string"] == string)
        for string in range(1, 7)
    } == {
        1: [5, 7, 8],
        2: [5, 6, 8],
        3: [5, 7],
        4: [5, 7, 9],
        5: [5, 7, 8],
        6: [5, 7, 8],
    }
    assert positions[3]["label"] == "Position 4 — D shape (7th fret)"
    assert positions[3]["root_string"] == "D string"
    assert positions[3]["root_fret"] == 7
    assert {
        string: sorted(note["fret"] for note in positions[3]["notes"] if note["string"] == string)
        for string in range(1, 7)
    } == {
        1: [7, 8, 10],
        2: [8, 10],
        3: [7, 9, 10],
        4: [7, 9, 10],
        5: [7, 8, 10],
        6: [7, 8, 10],
    }
    assert positions[4]["label"] == "Position 5 — C shape (12th fret)"
    assert positions[4]["root_string"] == "A string"
    assert positions[4]["root_fret"] == 12
    assert {
        string: sorted(note["fret"] for note in positions[4]["notes"] if note["string"] == string)
        for string in range(1, 7)
    } == {
        1: [8, 10, 12],
        2: [8, 10, 12],
        3: [9, 10],
        4: [9, 10, 12],
        5: [8, 10, 12],
        6: [8, 10, 12],
    }
    assert [position["root_fret"] for position in positions[5:]] == [12, 17, 17, 19]
    assert [position["root_string"] for position in positions[5:]] == [
        "A string",
        "Low E string",
        "Low E string",
        "D string",
    ]
    assert all(
        note["fret"] <= 23
        for position in positions
        for note in position["notes"]
    )

    expected_pcs = {0, 2, 4, 5, 7, 9, 11}
    for position in positions:
        assert 0 <= position["root_fret"] <= 23
        assert any(note["midi"] % 12 == 9 for note in position["notes"])
        strings = {note["string"] for note in position["notes"]}
        assert strings == {1, 2, 3, 4, 5, 6}
        for note in position["notes"]:
            assert 1 <= note["string"] <= 6
            assert 0 <= note["fret"] <= 23
            assert 0 <= note["midi"] <= 127
            assert note["midi"] % 12 in expected_pcs


def test_c_aeolian_does_not_change_major_c_and_g_aeolian_is_distinct() -> None:
    with ui.app.test_client() as client:
        major_c = client.get("/api/scale-positions?key=C").get_json()
        explicit_ionian_c = client.get(
            "/api/scale-positions?key=C&mode=Ionian"
        ).get_json()
        g_aeolian = client.get(
            "/api/scale-positions?key=G&mode=Aeolian"
        ).get_json()
        g_default = client.get("/api/scale-positions?key=G").get_json()

    assert major_c == explicit_ionian_c
    assert g_default == ui.SCALE_POSITIONS["G"]
    assert g_aeolian != g_default


def test_e_aeolian_uses_c_shaped_caged_position_on_c_sharp_fret_four() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=E&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions[:5]) == ["C", "A", "G", "E", "D"]
    assert [position["root_fret"] for position in positions[:5]] == [4, 4, 9, 9, 11]
    assert [position["root_string"] for position in positions[:5]] == [
        "A string",
        "A string",
        "Low E string",
        "Low E string",
        "D string",
    ]
    assert positions[0]["root_string"] == "A string"
    assert positions[0]["root_fret"] == 4
    assert positions[0]["label"] == "Position 1 — C shape (4th fret)"
    assert any(
        note["string"] == 5 and note["fret"] == 4 and note["midi"] % 12 == 1
        for note in positions[0]["notes"]
    )
    assert [position["label"] for position in positions[:5]] == [
        "Position 1 — C shape (4th fret)",
        "Position 2 — A shape (4th fret)",
        "Position 3 — G shape (9th fret)",
        "Position 4 — E shape (9th fret)",
        "Position 5 — D shape (11th fret)",
    ]
    assert [position["instructor_phrase"] for position in positions[:5]] == [
        "Start on the 4th fret of the A string. C Shape.",
        "Start on the 4th fret of the A string. A Shape.",
        "Start on the 9th fret of the low E string. G Shape.",
        "Start on the 9th fret of the low E string. E Shape.",
        "Start on the 11th fret of the D string. D Shape.",
    ]
    expected_pcs = {1, 3, 4, 6, 8, 9, 11}
    assert all(
        {note["string"] for note in position["notes"]} == {1, 2, 3, 4, 5, 6}
        and all(0 <= note["fret"] <= 22 for note in position["notes"])
        and all(0 <= note["midi"] <= 127 for note in position["notes"])
        and all(note["midi"] % 12 in expected_pcs for note in position["notes"])
        for position in positions
    )
    assert [position["root_fret"] for position in positions[5:]] == [16, 16, 21]