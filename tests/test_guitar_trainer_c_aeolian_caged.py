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


def test_c_aeolian_uses_five_minor_caged_shapes_with_valid_geometry() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=C&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions) == ["C", "A", "G", "E", "D"]

    expected_pcs = {0, 2, 4, 5, 7, 9, 11}
    for position in positions:
        assert 0 <= position["root_fret"] <= 24
        assert any(note["midi"] % 12 == 9 for note in position["notes"])
        strings = {note["string"] for note in position["notes"]}
        assert strings == {1, 2, 3, 4, 5, 6}
        for note in position["notes"]:
            assert 1 <= note["string"] <= 6
            assert 0 <= note["fret"] <= 24
            assert 0 <= note["midi"] <= 127
            assert note["midi"] % 12 in expected_pcs


def test_c_aeolian_does_not_change_major_c_or_non_c_aeolian_layouts() -> None:
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
    assert g_aeolian == g_default