"""Regression tests for the F major / D Aeolian trainer contract."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402


MINOR_PITCH_CLASSES = {0, 2, 4, 5, 7, 9, 10}
OPEN_MIDI = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}


def _shape_names(positions: list[dict]) -> list[str]:
    return [
        position["label"].split(" — ", 1)[1].split(" shape", 1)[0]
        for position in positions
    ]


def test_f_aeolian_uses_open_d_shape_then_minor_caged_order() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=F&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["D", "C", "A", "G", "E", "D", "C", "A", "G"]
    assert [position["root_string"] for position in positions] == [
        "D string", "A string", "A string", "Low E string", "Low E string",
        "D string", "A string", "A string", "Low E string",
    ]
    assert [position["root_fret"] for position in positions] == [0, 5, 5, 10, 10, 12, 17, 17, 22]
    assert positions[0]["label"] == "Position 1 — D shape (open)"
    assert positions[0]["instructor_phrase"] == "Start on the open D string. D Shape."
    assert positions[1]["label"] == "Position 2 — C shape (5th fret)"
    assert positions[2]["label"] == "Position 3 — A shape (5th fret)"
    assert positions[3]["instructor_phrase"] == (
        "Start on the 10th fret of the low E string. G Shape."
    )


def test_f_aeolian_has_d_roots_all_strings_and_valid_minor_geometry() -> None:
    with ui.app.test_client() as client:
        positions = client.get("/api/scale-positions?key=F&mode=Aeolian").get_json()

    assert len(positions) == 9
    for position in positions:
        notes = position["notes"]
        assert {note["string"] for note in notes} == set(range(1, 7))
        assert any(note["midi"] % 12 == 2 for note in notes)
        assert all(
            0 <= note["fret"] <= 22
            and 0 <= note["midi"] <= 127
            and note["midi"] == OPEN_MIDI[note["string"]] + note["fret"]
            and note["midi"] % 12 in MINOR_PITCH_CLASSES
            for note in notes
        )


def test_f_aeolian_preserves_valid_octave_repeats() -> None:
    with ui.app.test_client() as client:
        positions = client.get("/api/scale-positions?key=F&mode=Aeolian").get_json()

    for first, repeat in zip(positions[:4], positions[5:]):
        assert repeat["label"].split(" — ", 1)[1].split(" shape", 1)[0] == (
            first["label"].split(" — ", 1)[1].split(" shape", 1)[0]
        )
        assert repeat["root_fret"] == first["root_fret"] + 12
        assert [
            (note["string"], note["fret"], note["midi"])
            for note in repeat["notes"]
        ] == [
            (note["string"], note["fret"] + 12, note["midi"] + 12)
            for note in first["notes"]
        ]


def test_f_major_remains_non_aeolian_and_dropdown_contract_is_present() -> None:
    with ui.app.test_client() as client:
        major = client.get("/api/scale-positions?key=F&mode=Ionian").get_json()
        html = client.get("/").get_data(as_text=True)

    assert major != ui.get_scale_positions("F", "Aeolian")
    assert '<option value="F">F major / D minor</option>' in html
    assert 'option value="Aeolian">Aeolian</option>' in html