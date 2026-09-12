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
OPEN_MIDI = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
G_NATURAL_MINOR_PITCH_CLASSES = {0, 2, 3, 5, 7, 9, 10}


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

    expected = [
        ("E", "Low E string", 3),
        ("D", "D string", 5),
        ("C", "A string", 10),
        ("A", "A string", 10),
        ("G", "Low E string", 15),
        ("E", "Low E string", 15),
        ("D", "D string", 17),
        ("C", "A string", 22),
    ]

    assert list(zip(
        _shape_names(positions),
        [position["root_string"] for position in positions],
        [position["root_fret"] for position in positions],
    )) == expected
    assert [position["label"] for position in positions] == [
        "Position 1 — E shape (3rd fret)",
        "Position 2 — D shape (5th fret)",
        "Position 3 — C shape (10th fret)",
        "Position 4 — A shape (10th fret)",
        "Position 5 — G shape (15th fret)",
        "Position 6 — E shape (15th fret)",
        "Position 7 — D shape (17th fret)",
        "Position 8 — C shape (22nd fret)",
    ]
    assert [position["instructor_phrase"] for position in positions] == [
        "Start on the 3rd fret of the low E string. E Shape.",
        "Start on the 5th fret of the D string. D Shape.",
        "Start on the 10th fret of the A string. C Shape.",
        "Start on the 10th fret of the A string. A Shape.",
        "Start on the 15th fret of the low E string. G Shape.",
        "Start on the 15th fret of the low E string. E Shape.",
        "Start on the 17th fret of the D string. D Shape.",
        "Start on the 22nd fret of the A string. C Shape.",
    ]

    for position in positions:
        notes = position["notes"]
        root_string = {"Low E string": 6, "D string": 4, "A string": 5}[
            position["root_string"]
        ]
        assert {note["string"] for note in notes} == set(range(1, 7))
        assert (OPEN_MIDI[root_string] + position["root_fret"]) % 12 == 7
        assert any(note["midi"] % 12 == 7 for note in notes)
        assert all(
            0 <= note["fret"] <= 22
            and note["midi"] == OPEN_MIDI[note["string"]] + note["fret"]
            and note["midi"] % 12 in G_NATURAL_MINOR_PITCH_CLASSES
            for note in notes
        )


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


def test_f_sharp_aeolian_uses_minor_caged_order_and_valid_geometry() -> None:
    positions = get_scale_positions("F#", "Aeolian")
    natural_minor_pitch_classes = {1, 3, 5, 6, 8, 10, 11}

    assert _shape_names(positions) == ["D", "C", "A", "G", "E", "D", "C", "A"]
    assert [position["root_string"] for position in positions] == [
        "D string",
        "A string",
        "A string",
        "Low E string",
        "Low E string",
        "D string",
        "A string",
        "A string",
    ]
    assert [position["root_fret"] for position in positions] == [
        1,
        6,
        6,
        11,
        11,
        13,
        18,
        18,
    ]
    assert [position["label"] for position in positions] == [
        "Position 1 — D shape (1st fret)",
        "Position 2 — C shape (6th fret)",
        "Position 3 — A shape (6th fret)",
        "Position 4 — G shape (11th fret)",
        "Position 5 — E shape (11th fret)",
        "Position 6 — D shape (13th fret)",
        "Position 7 — C shape (18th fret)",
        "Position 8 — A shape (18th fret)",
    ]
    assert positions[0]["instructor_phrase"] == (
        "Start on the 1st fret of the D string. D Shape."
    )
    assert positions[-1]["instructor_phrase"] == (
        "Start on the 18th fret of the A string. A Shape."
    )
    assert all(
        0 <= note["fret"] <= 22
        and 0 <= note["midi"] <= 127
        and note["midi"] % 12 in natural_minor_pitch_classes
        for position in positions
        for note in position["notes"]
    )
    assert all(
        {note["string"] for note in position["notes"]} == {1, 2, 3, 4, 5, 6}
        and any(note["midi"] % 12 == 6 for note in position["notes"])
        and position["instructor_phrase"].endswith(
            f"{_shape_names([position])[0]} Shape."
        )
        for position in positions
    )
    assert all(
        max(note["fret"] for note in position["notes"]) <= 22
        for position in positions
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
    assert requested_phrases == ["Start on the 3rd fret of the low E string. E Shape."]
    assert "major" not in requested_phrases[0].lower()


def test_bb_aeolian_api_and_relative_minor_selector_match_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(ui, "ENABLE_EXERCISE_CARDS", False)
    monkeypatch.setattr(ui, "ENABLE_SCALE_LOG", False)

    with ui.app.test_client() as client:
        response = client.get("/api/scale-positions?key=Bb&mode=Aeolian")
        html = client.get("/").get_data(as_text=True)

    assert response.status_code == 200
    assert response.get_json() == get_scale_positions("Bb", "Aeolian")
    assert '<option value="Bb">Bb major / G minor</option>' in html


def test_bb_aeolian_change_preserves_other_scale_families_and_keys(
    monkeypatch,
) -> None:
    monkeypatch.setattr(ui, "PENTA_CAGED_ENABLED", False)

    with ui.app.test_client() as client:
        bb_default = client.get("/api/scale-positions?key=Bb").get_json()
        bb_ionian = client.get(
            "/api/scale-positions?key=Bb&mode=Ionian"
        ).get_json()
        bb_minor_pentatonic = client.get(
            "/api/scale-positions?key=Bb&family=minor_pentatonic"
        ).get_json()
        g_aeolian = client.get(
            "/api/scale-positions?key=G&mode=Aeolian"
        ).get_json()

    assert bb_default == bb_ionian == get_scale_positions("Bb", "Ionian")
    assert [
        {key: value for key, value in position.items() if key != "group"}
        for position in bb_minor_pentatonic
    ] == ui.BOX_PENTA_POSITIONS["Bb"]["minor_pentatonic"]
    assert [position["root_fret"] for position in g_aeolian] == [
        0, 2, 7, 7, 12, 12, 14, 19, 19
    ]


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
            if key == "F":
                assert _shape_names(positions) == ["D", "C", "A", "G", "E", "D", "C", "A", "G"]
                continue
            if key == "G":
                assert _shape_names(positions) == ["E", "D", "C", "A", "G", "E", "D", "C", "A"]
                assert [position["root_fret"] for position in positions] == [0, 2, 7, 7, 12, 12, 14, 19, 19]
                continue
            if key == "Ab":
                assert _shape_names(positions) == ["E", "D", "C", "A", "G", "E", "D", "C"]
                assert [position["root_fret"] for position in positions] == [1, 3, 8, 8, 13, 13, 15, 20]
                continue
            if key == "A":
                assert _shape_names(positions) == ["E", "D", "C", "A", "G", "E", "D", "C"]
                assert [position["root_fret"] for position in positions] == [2, 4, 9, 9, 14, 14, 16, 21]
                continue
            if key == "Bb":
                assert _shape_names(positions) == ["E", "D", "C", "A", "G", "E", "D", "C"]
                assert [position["root_fret"] for position in positions] == [3, 5, 10, 10, 15, 15, 17, 22]
                continue
            shift = (KEY_PITCH_CLASSES[key] - 9) % 12
            expected_positions = []
            indices = (
                (4, 0, 1, 2, 3)
                if key == "E"
                else (3, 4, 0, 1, 2)
                if key == "F#"
                else reference_indices
            )
            base_positions = [reference[index] for index in indices]
            if key == "F#":
                expected_positions = [
                    (reference[index], fret_shift, shift)
                    for index, fret_shift in (
                        (3, -6),
                        (4, -6),
                        (0, 6),
                        (1, 6),
                        (2, 6),
                        (3, 6),
                        (4, 6),
                        (0, 18),
                    )
                ]
            else:
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

            if key != "F#":
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


def test_g_aeolian_preserves_position_seven_and_nine_d_string_rows() -> None:
    positions = get_scale_positions("G", "Aeolian")

    assert [
        note["fret"] for note in positions[6]["notes"] if note["string"] == 4
    ] == [14, 16, 17]
    assert [
        note["fret"] for note in positions[8]["notes"] if note["string"] == 4
    ] == [19, 21, 22]


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
            if key == "F#":
                assert _shape_names(positions[:5]) == ["D", "C", "A", "G", "E"]
            elif key != "Ab":
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
                expected_root_pitch = 5 if key == "Ab" else KEY_PITCH_CLASSES[key]
                assert any(
                    note["midi"] % 12 == expected_root_pitch
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
            if alias == "D#":
                assert actual != expected
                assert actual[0]["label"] == "Position 1 — C shape (6th fret)"
                assert actual[0]["root_string"] == "A string"
                assert actual[0]["root_fret"] == 6
            else:
                assert actual == expected


def test_non_aeolian_layouts_remain_unchanged() -> None:
    with ui.app.test_client() as client:
        for key in CANONICAL_KEYS:
            assert client.get(f"/api/scale-positions?key={_query_key(key)}").get_json() == get_scale_positions(key)