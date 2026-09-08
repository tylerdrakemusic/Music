"""Regression tests for the Db/Aeolian and D/Aeolian minor CAGED layouts."""
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


def test_d_aeolian_uses_low_fret_caged_sequence_and_valid_geometry() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=D&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["A", "G", "E", "D", "C", "A", "G"]
    assert [position["root_string"] for position in positions] == [
        "A string",
        "Low E string",
        "Low E string",
        "D string",
        "A string",
        "A string",
        "Low E string",
    ]
    assert [position["root_fret"] for position in positions] == [2, 7, 7, 9, 14, 14, 19]
    assert positions[0]["label"] == "Position 1 — A shape (2nd fret)"
    assert min(note["fret"] for note in positions[0]["notes"]) >= 2
    assert max(note["fret"] for note in positions[0]["notes"]) <= 7
    assert positions[-1]["label"] == "Position 7 — G shape (19th fret)"
    assert all(
        1 <= note["string"] <= 6
        and 0 <= note["fret"] <= 22
        and 0 <= note["midi"] <= 127
        and note["midi"] % 12 in {11, 1, 2, 4, 6, 7, 9}
        for position in positions
        for note in position["notes"]
    )
    assert all(
        {note["string"] for note in position["notes"]} == {1, 2, 3, 4, 5, 6}
        and any(note["midi"] % 12 == 2 for note in position["notes"])
        for position in positions
    )


def test_db_aeolian_uses_bb_minor_caged_shapes_and_repeats() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=Db&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["A", "G", "E", "D", "C", "A", "G", "E"]
    assert [position["root_fret"] for position in positions] == [1, 6, 6, 8, 13, 13, 18, 18]
    assert [position["root_string"] for position in positions] == [
        "A string",
        "Low E string",
        "Low E string",
        "D string",
        "A string",
        "A string",
        "Low E string",
        "Low E string",
    ]
    assert positions[0]["label"] == "Position 1 — A shape (1st fret)"
    assert positions[0]["instructor_phrase"] == "Start on the 1st fret of the A string. A Shape."
    assert positions[4]["label"] == "Position 5 — C shape (13th fret)"
    assert positions[4]["instructor_phrase"] == "Start on the 13th fret of the A string. C Shape."
    assert positions[-1]["label"] == "Position 8 — E shape (18th fret)"
    assert len(positions) == 8
    assert all(
        0 <= note["fret"] <= 23
        and note["midi"] % 12 in {10, 0, 1, 3, 5, 6, 8}
        for position in positions
        for note in position["notes"]
    )


def test_db_aeolian_does_not_broaden_to_other_aeolian_keys() -> None:
    with ui.app.test_client() as client:
        g_aeolian = client.get("/api/scale-positions?key=G&mode=Aeolian").get_json()
        g_default = client.get("/api/scale-positions?key=G").get_json()

    assert g_aeolian != g_default


def test_eb_aeolian_transposes_the_proven_d_aeolian_layout_up_one_fret() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=Eb&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["A", "G", "E", "D", "C", "A", "G"]
    assert [position["root_fret"] for position in positions] == [3, 8, 8, 10, 15, 15, 20]
    assert [position["root_string"] for position in positions] == [
        "A string",
        "Low E string",
        "Low E string",
        "D string",
        "A string",
        "A string",
        "Low E string",
    ]
    assert all(
        0 <= note["fret"] <= 22
        and note["midi"] % 12 in {0, 2, 3, 5, 7, 8, 10}
        for position in positions
        for note in position["notes"]
    )


def test_eb_aeolian_position_four_tts_uses_the_aeolian_phrase(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def capture_phrase(phrase: str, _cache_dir: Path) -> None:
        captured["phrase"] = phrase
        return None

    monkeypatch.setattr(ui, "get_instructor_audio", capture_phrase)

    with ui.app.test_client() as client:
        response = client.get(
            "/api/instructor-audio?key=Eb&mode=Aeolian&position=4"
        )

    assert response.status_code == 204
    assert captured["phrase"] == "Start on the 10th fret of the D string. D Shape."