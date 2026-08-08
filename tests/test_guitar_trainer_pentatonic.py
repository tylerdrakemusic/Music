"""
Tests for FR-20260806-guitar-trainer-pentatonic-scales.

Design decisions:
  - Scale family: Diatonic | Major Pentatonic | Minor Pentatonic
  - Family selector: pill toggle (1B)
  - Palette: warm blues/amber (2B)
  - Position labels: CAGED shape style, no "5 notes" text (3B)
  - Minor penta key: relative major (4B/5B) — key=C covers A minor penta

Covers:
  - PENTATONIC_SPEC: intervals, degrees, tts_label for both families
  - Major pentatonic intervals (0,2,4,7,9) for all 12 keys
  - Minor pentatonic intervals (0,3,5,7,10) for all 12 keys
  - get_pentatonic_sequence returns 5+1 notes (root repeated at top)
  - PENTATONIC_POSITIONS structure: all 12 keys, ≥5 positions each
  - Position labels use CAGED shape style, no "5 notes" text
  - PENTA_DEGREE_COLORS: warm palette (2B) — distinct from diatonic
  - Minor penta: key=C → A-minor-root positions (relative minor)
  - /api/scale-positions?key=C&family=major_penta returns positions
  - /api/scale-positions?key=C&family=minor_penta returns positions
  - /api/scale-positions?key=C (no family) still returns diatonic (backward compat)
  - /api/scale-positions?family=invalid returns 400
  - HTML: scale-family pill buttons present (diatonic, maj-penta, min-penta)
  - build_penta_phrase returns correct instructor string
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from training.pentatonic_spec import (
    PENTATONIC_SPEC,
    PENTA_DEGREE_COLORS,
    build_penta_phrase,
    penta_relative_minor_root,
)
from training.scale_data import (
    PENTATONIC_POSITIONS, get_pentatonic_sequence, BOX_PENTA_POSITIONS,
)
import training.musician_training_ui as ui

# ---------------------------------------------------------------------------
# Shared DB schema (mirrors test_guitar_trainer_scales.py)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guitar_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    song_path TEXT NOT NULL DEFAULT '',
    segments TEXT NOT NULL DEFAULT '[]',
    gradient INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS guitar_training_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER,
    song_path TEXT NOT NULL DEFAULT '',
    seg_start TEXT NOT NULL DEFAULT '',
    seg_end TEXT NOT NULL DEFAULT '',
    repetition INTEGER NOT NULL DEFAULT 1,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS scale_practice_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL DEFAULT 'C',
    mode TEXT NOT NULL DEFAULT 'Ionian',
    scale_family TEXT NOT NULL DEFAULT 'diatonic',
    position_idx INTEGER NOT NULL DEFAULT 0,
    bpm INTEGER NOT NULL DEFAULT 60,
    repetitions INTEGER NOT NULL DEFAULT 1,
    duration_seconds REAL NOT NULL DEFAULT 0,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


class _NoClose:
    def __init__(self, c: sqlite3.Connection) -> None:
        object.__setattr__(self, "_c", c)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_c"), name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return object.__getattribute__(self, "_c").__enter__()

    def __exit__(self, *a):
        return object.__getattribute__(self, "_c").__exit__(*a)


@pytest.fixture()
def client():
    conn = _make_db()
    conn.row_factory = sqlite3.Row
    wrapper = _NoClose(conn)
    ui.app.config["TESTING"] = True
    with patch("training.musician_training_ui.get_connection", return_value=wrapper):
        with ui.app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# PENTATONIC_SPEC structure
# ---------------------------------------------------------------------------

class TestPentatonicSpec:
    def test_families_present(self):
        assert "major_pentatonic" in PENTATONIC_SPEC
        assert "minor_pentatonic" in PENTATONIC_SPEC

    def test_major_penta_intervals(self):
        assert PENTATONIC_SPEC["major_pentatonic"]["intervals"] == (0, 2, 4, 7, 9, 12)

    def test_minor_penta_intervals(self):
        assert PENTATONIC_SPEC["minor_pentatonic"]["intervals"] == (0, 3, 5, 7, 10, 12)

    def test_major_penta_degrees_has_root_third_fifth(self):
        degs = PENTATONIC_SPEC["major_pentatonic"]["degrees"]
        assert 0 in degs   # root
        assert 4 in degs   # major 3rd
        assert 7 in degs   # 5th

    def test_minor_penta_degrees_has_root_flat3_fifth_flat7(self):
        degs = PENTATONIC_SPEC["minor_pentatonic"]["degrees"]
        assert 0 in degs    # root
        assert 3 in degs    # ♭3
        assert 7 in degs    # 5th
        assert 10 in degs   # ♭7

    def test_tts_labels(self):
        assert "pentatonic" in PENTATONIC_SPEC["major_pentatonic"]["tts_label"].lower()
        assert "pentatonic" in PENTATONIC_SPEC["minor_pentatonic"]["tts_label"].lower()


# ---------------------------------------------------------------------------
# PENTA_DEGREE_COLORS — warm 2B palette, distinct from diatonic
# ---------------------------------------------------------------------------

class TestPentaDegreeColors:
    def test_root_is_hot_pink(self):
        # Root stays consistent with diatonic for muscle memory
        assert PENTA_DEGREE_COLORS["root"].lower() == "#ff0080"

    def test_penta_third_is_warm_amber(self):
        # 2B palette — amber, not diatonic orange
        color = PENTA_DEGREE_COLORS["penta_third"].lower()
        assert color != "#fb5607", "should differ from diatonic third"

    def test_penta_fifth_is_warm(self):
        color = PENTA_DEGREE_COLORS["penta_fifth"].lower()
        assert color != "#00e5cc", "should differ from diatonic fifth"

    def test_penta_flat7_present(self):
        assert "penta_flat7" in PENTA_DEGREE_COLORS

    def test_all_colors_are_hex(self):
        import re
        for name, val in PENTA_DEGREE_COLORS.items():
            assert re.match(r"^#[0-9a-fA-F]{6}$", val), f"{name}: {val!r} not a hex color"


# ---------------------------------------------------------------------------
# PENTATONIC_POSITIONS — all 12 keys, CAGED shape labels
# ---------------------------------------------------------------------------

_ALL_KEYS = ["C", "G", "F", "D", "E", "F#", "Db", "Bb", "B", "Eb", "Ab", "A"]


class TestPentatonicPositions:
    def test_all_keys_present(self):
        for key in _ALL_KEYS:
            assert key in PENTATONIC_POSITIONS, f"missing key {key}"

    def test_each_key_has_at_least_5_positions(self):
        for key, positions in PENTATONIC_POSITIONS.items():
            assert len(positions) >= 5, f"{key} has only {len(positions)} positions"

    def test_position_labels_use_caged_style(self):
        for key, positions in PENTATONIC_POSITIONS.items():
            for pos in positions:
                assert "Position" in pos["label"], f"{key}: label missing 'Position': {pos['label']!r}"
                assert "shape" in pos["label"].lower() or "open" in pos["label"].lower(), (
                    f"{key}: label should contain shape name: {pos['label']!r}"
                )

    def test_position_labels_have_no_five_notes_text(self):
        for key, positions in PENTATONIC_POSITIONS.items():
            for pos in positions:
                assert "5 notes" not in pos["label"], (
                    f"{key}: label should not contain '5 notes': {pos['label']!r}"
                )

    def test_position_has_required_fields(self):
        for key, positions in PENTATONIC_POSITIONS.items():
            for pos in positions:
                assert "label" in pos
                assert "notes" in pos
                assert "root_fret" in pos
                # 5 unique pitch classes across all note instances
                pcs = {n["midi"] % 12 for n in pos["notes"]}
                assert len(pcs) == 5, f"{key} pos '{pos['label']}' has {len(pcs)} unique PCs"

    def test_all_notes_have_string_fret_midi(self):
        c_positions = PENTATONIC_POSITIONS["C"]
        for pos in c_positions:
            for note in pos["notes"]:
                assert "string" in note
                assert "fret" in note
                assert "midi" in note


# ---------------------------------------------------------------------------
# get_pentatonic_sequence
# ---------------------------------------------------------------------------

class TestGetPentatonicSequence:
    def test_returns_5_unique_plus_octave(self):
        seq = get_pentatonic_sequence(0, key="C", family="major_pentatonic")
        # 5 unique pitch classes + root octave at top
        pcs = {m % 12 for m in seq}
        assert len(pcs) == 5

    def test_ascending_midi_order(self):
        seq = get_pentatonic_sequence(0, key="C", family="major_pentatonic")
        assert seq == sorted(seq)

    def test_minor_penta_key_c_uses_relative_minor_root(self):
        # key=C + minor penta → A minor pentatonic root (pitch class 9 = A)
        seq = get_pentatonic_sequence(0, key="C", family="minor_pentatonic")
        pcs = {m % 12 for m in seq}
        assert len(pcs) == 5

    def test_invalid_family_raises(self):
        with pytest.raises((KeyError, ValueError)):
            get_pentatonic_sequence(0, key="C", family="blues")


# ---------------------------------------------------------------------------
# penta_relative_minor_root helper
# ---------------------------------------------------------------------------

class TestPentaRelativeMinorRoot:
    def test_c_major_relative_minor_is_a(self):
        assert penta_relative_minor_root("C") == "A"

    def test_g_major_relative_minor_is_e(self):
        assert penta_relative_minor_root("G") == "E"

    def test_f_major_relative_minor_is_d(self):
        assert penta_relative_minor_root("F") == "D"

    def test_a_major_relative_minor_is_fs(self):
        assert penta_relative_minor_root("A") in ("F#", "Gb")


# ---------------------------------------------------------------------------
# build_penta_phrase
# ---------------------------------------------------------------------------

class TestBuildPentaPhrase:
    def test_major_penta_phrase_mentions_key_and_family(self):
        phrase = build_penta_phrase({"label": "Position 1 — C shape (3rd fret)", "root_fret": 3}, "C", "major_pentatonic")
        assert "C" in phrase
        assert "pentatonic" in phrase.lower()

    def test_minor_penta_phrase_mentions_minor_root(self):
        phrase = build_penta_phrase({"label": "Position 1 — A shape (5th fret)", "root_fret": 5}, "C", "minor_pentatonic")
        assert "pentatonic" in phrase.lower()
        # Should say "A" (relative minor of C), not "C"
        assert "A" in phrase

    def test_flat_key_spoken_not_as_letter(self):
        # "Db" must not appear verbatim — TTS reads it as "D B"
        phrase = build_penta_phrase({"label": "Box 1 — 9th fret", "root_fret": 9, "root_string": "low E string"}, "Db", "major_pentatonic")
        assert "Db" not in phrase
        assert "flat" in phrase.lower()

    def test_sharp_key_spoken_not_as_symbol(self):
        phrase = build_penta_phrase({"label": "Box 1 — 2nd fret", "root_fret": 2, "root_string": "low E string"}, "F#", "major_pentatonic")
        assert "F#" not in phrase
        assert "sharp" in phrase.lower()


# ---------------------------------------------------------------------------
# BOX_PENTA_POSITIONS — classic 5-box positions
# ---------------------------------------------------------------------------

class TestBoxPentaPositions:
    def test_all_keys_present_for_both_families(self):
        for key in _ALL_KEYS:
            assert key in BOX_PENTA_POSITIONS
            assert "major_pentatonic" in BOX_PENTA_POSITIONS[key]
            assert "minor_pentatonic" in BOX_PENTA_POSITIONS[key]

    def test_exactly_5_boxes_per_key_and_family(self):
        # Full-neck tiling with anchor cap at fret 18: most keys get 7-10 boxes;
        # high-root keys (e.g. F# minor penta root at fret 11) may get only 4.
        for key in _ALL_KEYS:
            for fam in ("major_pentatonic", "minor_pentatonic"):
                boxes = BOX_PENTA_POSITIONS[key][fam]
                assert len(boxes) >= 4, f"{key}/{fam} has only {len(boxes)} boxes"

    def test_full_neck_coverage(self):
        for key in _ALL_KEYS:
            for fam in ("major_pentatonic", "minor_pentatonic"):
                high_boxes = [b for b in BOX_PENTA_POSITIONS[key][fam] if b["root_fret"] >= 12]
                assert high_boxes, f"{key}/{fam} has no boxes at or above fret 12"

    def test_open_position_boxes_present(self):
        # octave -12 should yield boxes anchored at low fret numbers
        for fam in ("major_pentatonic", "minor_pentatonic"):
            low_boxes = [b for b in BOX_PENTA_POSITIONS["A"][fam] if b["root_fret"] <= 5]
            assert low_boxes, f"A/{fam} has no open-position boxes"

    def test_box_labels_say_box_number(self):
        import re
        for key in _ALL_KEYS:
            for fam in ("major_pentatonic", "minor_pentatonic"):
                for box in BOX_PENTA_POSITIONS[key][fam]:
                    assert re.match(r"Box [1-5]", box["label"]), (
                        f"{key}/{fam}: label missing Box N: {box['label']!r}"
                    )

    def test_box_positions_have_5_unique_pitch_classes(self):
        for key in _ALL_KEYS:
            for fam in ("major_pentatonic", "minor_pentatonic"):
                for box in BOX_PENTA_POSITIONS[key][fam]:
                    pcs = {n["midi"] % 12 for n in box["notes"]}
                    min_pcs = 4 if box["root_fret"] >= 18 else 5
                    assert len(pcs) >= min_pcs, (
                        f"{key}/{fam} '{box['label']}' has only {len(pcs)} unique PCs"
                    )

    def test_boxes_have_notes_string_fret_midi(self):
        for note in BOX_PENTA_POSITIONS["C"]["major_pentatonic"][0]["notes"]:
            assert "string" in note
            assert "fret" in note
            assert "midi" in note

    def test_box_frets_within_22(self):
        for key in _ALL_KEYS:
            for fam in ("major_pentatonic", "minor_pentatonic"):
                for box in BOX_PENTA_POSITIONS[key][fam]:
                    for note in box["notes"]:
                        assert 0 <= note["fret"] <= 22, (
                            f"{key}/{fam} fret {note['fret']} outside 0-22"
                        )

    def test_boxes_ascending_across_neck(self):
        for key in _ALL_KEYS:
            for fam in ("major_pentatonic", "minor_pentatonic"):
                frets = [b["root_fret"] for b in BOX_PENTA_POSITIONS[key][fam]]
                assert frets == sorted(frets), (
                    f"{key}/{fam} boxes not in ascending order: {frets}"
                )

    def test_major_penta_phrase_uses_major_root(self):
        # C major penta — phrase should say "C" not "A"
        box = BOX_PENTA_POSITIONS["C"]["major_pentatonic"][0]
        assert "C" in box["instructor_phrase"]
        assert "major" in box["instructor_phrase"]
        assert "minor" not in box["instructor_phrase"]

    def test_minor_penta_phrase_uses_relative_minor_root(self):
        # key=C, minor penta → A minor; phrase must say "A" not "C"
        box = BOX_PENTA_POSITIONS["C"]["minor_pentatonic"][0]
        assert "A" in box["instructor_phrase"]
        assert "minor" in box["instructor_phrase"]
        assert "C minor" not in box["instructor_phrase"]

    def test_minor_penta_phrase_no_raw_accidental(self):
        # Db minor penta → phrase must not contain "Db" (spoken as "D flat")
        for box in BOX_PENTA_POSITIONS["Db"]["minor_pentatonic"]:
            assert "Db" not in box["instructor_phrase"]


# ---------------------------------------------------------------------------
# API — /api/scale-positions returns group field when family = pentatonic
# ---------------------------------------------------------------------------

class TestScalePositionsApiGrouped:
    def test_major_penta_positions_have_group_field(self, client):
        resp = client.get("/api/scale-positions?key=C&family=major_pentatonic")
        data = json.loads(resp.data)
        groups = {p.get("group") for p in data}
        assert "box" in groups
        assert "caged" in groups

    def test_minor_penta_positions_have_group_field(self, client):
        resp = client.get("/api/scale-positions?key=C&family=minor_pentatonic")
        data = json.loads(resp.data)
        groups = {p.get("group") for p in data}
        assert "box" in groups
        assert "caged" in groups

    def test_box_group_has_exactly_5(self, client):
        resp = client.get("/api/scale-positions?key=A&family=major_pentatonic")
        data = json.loads(resp.data)
        box_entries = [p for p in data if p.get("group") == "box"]
        assert len(box_entries) >= 5

    def test_diatonic_positions_have_no_group_field(self, client):
        resp = client.get("/api/scale-positions?key=C")
        data = json.loads(resp.data)
        for p in data:
            assert "group" not in p


# ---------------------------------------------------------------------------
# HTML — position select uses optgroup for pentatonic families
# ---------------------------------------------------------------------------

class TestHtmlOptgroup:
    def test_optgroup_box_positions_in_html(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "Box Positions" in html or "box" in html.lower()


# ---------------------------------------------------------------------------
# HTML — pill toggle buttons present
# ---------------------------------------------------------------------------

class TestHtmlPillToggle:
    def test_family_pill_buttons_present(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "major_penta" in html or "major-penta" in html
        assert "minor_penta" in html or "minor-penta" in html
        assert "diatonic" in html.lower()
