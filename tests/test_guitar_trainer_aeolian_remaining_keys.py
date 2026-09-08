"""Focused tests for the remaining natural-minor CAGED layouts."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402
from training.scale_data import get_scale_positions  # noqa: E402


CANONICAL_KEYS = ["Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
KEY_PITCH_CLASSES = {
    "Db": 1,
    "D": 2,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "Ab": 8,
    "A": 9,
    "Bb": 10,
    "B": 11,
}


def _query_key(key: str) -> str:
    return key.replace("#", "%23")


def _shape_names(positions: list[dict]) -> list[str]:
    return [
        position["label"].split(" — ", 1)[1].split(" shape", 1)[0]
        for position in positions
    ]


def _physical_order(positions: list[dict]) -> list[dict]:
    """Order positions by lowest occupied fret, preserving construction ties."""
    return [
        position
        for _, position in sorted(
            enumerate(positions),
            key=lambda item: (
                min(note["fret"] for note in item[1]["notes"]),
                item[0],
            ),
        )
    ]


def test_bb_aeolian_positions_follow_ascending_neck_order() -> None:
    positions = get_scale_positions("Bb", "Aeolian")

    assert _shape_names(positions)[:5] == ["A", "G", "E", "D", "C"]
    assert positions[0]["root_fret"] == 10
    assert positions[0]["label"] == "Position 1 — A shape (10th fret)"
    reference = get_scale_positions("C", "Aeolian")[0]
    assert positions[0]["notes"] == [
        {
            "string": note["string"],
            "fret": note["fret"] + 10,
            "midi": {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}[note["string"]]
            + note["fret"] + 10,
        }
        for note in reference["notes"]
    ]
    assert (
        min(note["fret"] for note in positions[0]["notes"]),
        max(note["fret"] for note in positions[0]["notes"]),
    ) == (10, 13)
    assert {
        note["midi"] % 12
        for note in positions[0]["notes"]
    } <= {0, 2, 3, 5, 7, 9, 10}

    effective_starts = [
        min(note["fret"] for note in position["notes"])
        for position in positions
    ]
    assert effective_starts == sorted(effective_starts)


def test_b_aeolian_positions_follow_actual_physical_neck_order() -> None:
    positions = get_scale_positions("B", "Aeolian")

    assert _shape_names(positions[:5]) == ["C", "A", "G", "E", "D"]
    spans = [
        (
            min(note["fret"] for note in position["notes"]),
            max(note["fret"] for note in position["notes"]),
        )
        for position in positions[:5]
    ]
    assert spans == [(7, 11), (11, 14), (12, 16), (16, 20), (18, 21)]
    assert [start for start, _ in spans] == sorted(start for start, _ in spans)


def test_b_aeolian_uses_natural_minor_pitch_membership() -> None:
    positions = get_scale_positions("B", "Aeolian")
    pitch_classes = {
        note["midi"] % 12
        for position in positions
        for note in position["notes"]
    }

    assert pitch_classes == {1, 3, 4, 6, 8, 10, 11}
    assert any(
        note["midi"] % 12 == 8
        for position in positions
        for note in position["notes"]
    )
    assert all(
        note["midi"] % 12 != 9
        for position in positions
        for note in position["notes"]
    )


def test_db_aeolian_uses_universal_minor_caged_sequence() -> None:
    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=Db&mode=Aeolian")

    assert response.status_code == 200
    positions = response.get_json()
    assert _shape_names(positions)[:5] == ["A", "G", "E", "D", "C"]


def test_instructor_audio_uses_bb_aeolian_position_phrase(monkeypatch) -> None:
    requested_phrases: list[str] = []

    def capture_phrase(phrase: str, cache_dir: Path) -> None:
        requested_phrases.append(phrase)
        return None

    monkeypatch.setattr(ui, "get_instructor_audio", capture_phrase)

    with ui.app.test_client() as client:
        response = client.get(
            "/api/instructor-audio?key=Bb&position=1&mode=Aeolian"
        )

    assert response.status_code == 204
    assert requested_phrases == ["Start on the 10th fret of the A string. A Shape."]
    assert "major" not in requested_phrases[0].lower()


def test_enharmonic_aeolian_aliases_reuse_canonical_layouts() -> None:
    with ui.app.test_client() as client:
        canonical = client.get("/api/scale-positions?key=Db&mode=Aeolian").get_json()
        alias = client.get("/api/scale-positions?key=C%23&mode=Aeolian").get_json()

    assert alias == canonical


def test_every_canonical_aeolian_layout_translates_reference_geometry() -> None:
    reference = get_scale_positions("C", "Aeolian")
    reference_indices = (0, 1, 2, 3, 4)

    with ui.app.test_client() as client:
        for key in CANONICAL_KEYS:
            positions = client.get(
                f"/api/scale-positions?key={_query_key(key)}&mode=Aeolian"
            ).get_json()
            shift = (KEY_PITCH_CLASSES[key] - 9) % 12
            expected_positions = []
            indices = (4, 0, 1, 2, 3) if key == "E" else reference_indices
            base_positions = [reference[index] for index in indices]
            for expected in base_positions:
                fret_shift = -8 if key == "E" and expected is reference[4] else KEY_PITCH_CLASSES[key]
                midi_shift = shift
                if any(
                    note["fret"] + fret_shift >= 23
                    for note in expected["notes"]
                ):
                    fret_shift -= 12
                expected_positions.append((expected, fret_shift, midi_shift))

            for expected in base_positions:
                repeated_fret_shift = (-8 if key == "E" and expected is reference[4] else KEY_PITCH_CLASSES[key]) + 12
                repeated_midi_shift = shift + 12
                if not any(
                    note["fret"] + repeated_fret_shift >= 23
                    for note in expected["notes"]
                ):
                    expected_positions.append(
                        (expected, repeated_fret_shift, repeated_midi_shift)
                    )

            expected_positions = [
                item
                for _, item in sorted(
                    enumerate(expected_positions),
                    key=lambda item: (
                        min(
                            note["fret"] + item[1][1]
                            for note in item[1][0]["notes"]
                        ),
                        item[0],
                    ),
                )
            ]

            assert len(positions) == len(expected_positions)
            for position, (expected, fret_shift, midi_shift) in zip(
                positions, expected_positions
            ):
                shape_name = expected["label"].split(" — ", 1)[1].split(" shape", 1)[0]
                assert position["label"].split(" — ", 1)[1].split(" shape", 1)[0] == shape_name
                assert position["root_string"] == expected["root_string"]
                assert position["root_fret"] == expected["root_fret"] + fret_shift
                assert position["notes"] == [
                    {
                        "string": note["string"],
                        "fret": note["fret"] + fret_shift,
                        "midi": {
                            1: 64,
                            2: 59,
                            3: 55,
                            4: 50,
                            5: 45,
                            6: 40,
                        }[note["string"]] + note["fret"] + fret_shift,
                    }
                    for note in expected["notes"]
                ]


def test_every_canonical_aeolian_layout_has_valid_notes_repeats_and_tts() -> None:
    natural_minor_intervals = (0, 2, 3, 5, 7, 8, 10)

    with ui.app.test_client() as client:
        for key in CANONICAL_KEYS:
            positions = client.get(
                f"/api/scale-positions?key={_query_key(key)}&mode=Aeolian"
            ).get_json()
            relative_minor_root = (KEY_PITCH_CLASSES[key] - 3) % 12
            expected_pitch_classes = {
                (relative_minor_root + interval) % 12
                for interval in natural_minor_intervals
            }
            assert positions == _physical_order(positions)
            assert all(
                note["fret"] < 23
                for position in positions
                for note in position["notes"]
            )
            for position in positions:
                assert {note["string"] for note in position["notes"]} == {1, 2, 3, 4, 5, 6}
                assert all(
                    note["midi"] % 12 in expected_pitch_classes
                    for note in position["notes"]
                )
                assert any(
                    note["midi"] % 12 == KEY_PITCH_CLASSES[key]
                    for note in position["notes"]
                )
                shape_name = _shape_names([position])[0]
                assert position["instructor_phrase"].endswith(f"{shape_name} Shape.")


def test_aeolian_canonical_keys_and_aliases_never_emit_fret_23() -> None:
    aliases = {"C#": "Db", "D#": "Eb", "A#": "Bb"}

    with ui.app.test_client() as client:
        for key in [*CANONICAL_KEYS, *aliases]:
            positions = client.get(
                f"/api/scale-positions?key={_query_key(key)}&mode=Aeolian"
            ).get_json()

            assert all(
                note["fret"] <= 22
                for position in positions
                for note in position["notes"]
            ), key


def test_aeolian_aliases_all_match_canonical_layouts() -> None:
    aliases = {"C#": "Db", "D#": "Eb", "A#": "Bb"}

    with ui.app.test_client() as client:
        for alias, canonical in aliases.items():
            expected = client.get(
                f"/api/scale-positions?key={canonical}&mode=Aeolian"
            ).get_json()
            actual = client.get(
                f"/api/scale-positions?key={alias.replace('#', '%23')}&mode=Aeolian"
            ).get_json()
            assert actual == expected


def test_non_aeolian_layouts_remain_unchanged() -> None:
    with ui.app.test_client() as client:
        for key in CANONICAL_KEYS:
            assert client.get(f"/api/scale-positions?key={_query_key(key)}").get_json() == get_scale_positions(key)