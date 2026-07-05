"""
Tests for FR-20260629-guitar-trainer-lydian-mode.

Validates the consolidated, data-driven MODE_SPEC (single source of truth for
per-mode coloring / legend / TTS / accent) and full Lydian support:
  - Lydian root offset (5) and staff intervals (raised 4th)
  - Dedicated 'sharp_fourth' degree type with a distinct color
  - TTS instructor phrase "root of the Lydian scale" + opt-in raised-4th callout
  - Behavior-preserving root offsets / intervals for the 6 existing modes
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from training.scale_data import SCALE_POSITIONS  # noqa: E402

# Source of truth under test (created by this FR).
from training.mode_spec import (  # noqa: E402
    MODE_SPEC,
    DEGREE_COLORS,
    build_mode_phrase,
    legend_items,
)

# Expected values mirror the pre-consolidation JS tables (behavior-preserving).
_EXPECTED_ROOT_OFFSETS = {
    "Ionian": 0,
    "Dorian": 2,
    "Phrygian": 4,
    "Lydian": 5,
    "Mixolydian": 7,
    "Aeolian": 9,
    "Locrian": 11,
}
_EXPECTED_INTERVALS = {
    "Ionian": (0, 2, 4, 5, 7, 9, 11, 12),
    "Dorian": (0, 2, 3, 5, 7, 9, 10, 12),
    "Phrygian": (0, 1, 3, 5, 7, 8, 10, 12),
    "Lydian": (0, 2, 4, 6, 7, 9, 11, 12),
    "Mixolydian": (0, 2, 4, 5, 7, 9, 10, 12),
    "Aeolian": (0, 2, 3, 5, 7, 8, 10, 12),
    "Locrian": (0, 1, 3, 5, 6, 8, 10, 12),
}


# ---------------------------------------------------------------------------
# MODE_SPEC structure + behavior-preservation
# ---------------------------------------------------------------------------

def test_mode_spec_has_all_seven_modes() -> None:
    assert set(MODE_SPEC.keys()) == set(_EXPECTED_ROOT_OFFSETS.keys())


@pytest.mark.parametrize("mode,offset", _EXPECTED_ROOT_OFFSETS.items())
def test_mode_spec_root_offsets(mode: str, offset: int) -> None:
    assert MODE_SPEC[mode]["root_offset"] == offset


@pytest.mark.parametrize("mode,intervals", _EXPECTED_INTERVALS.items())
def test_mode_spec_intervals(mode: str, intervals: tuple) -> None:
    assert tuple(MODE_SPEC[mode]["intervals"]) == intervals


# ---------------------------------------------------------------------------
# Lydian-specific
# ---------------------------------------------------------------------------

def test_lydian_sharp_fourth_degree_type() -> None:
    degrees = MODE_SPEC["Lydian"]["degrees"]
    # The raised 4th is interval 6 from the tonic and gets its own dedicated type.
    assert degrees[6]["type"] == "sharp_fourth"
    # Root / major 3rd / 5th keep the standard palette types.
    assert degrees[0]["type"] == "root"
    assert degrees[4]["type"] == "third"
    assert degrees[7]["type"] == "fifth"


def test_sharp_fourth_color_is_distinct() -> None:
    c = DEGREE_COLORS["sharp_fourth"]
    assert c.startswith("#")
    # Must not collide with any other Lydian-visible degree color.
    assert c not in {
        DEGREE_COLORS["root"],
        DEGREE_COLORS["third"],
        DEGREE_COLORS["fifth"],
        DEGREE_COLORS["other"],
    }


def test_lydian_characteristic_is_raised_fourth() -> None:
    ch = MODE_SPEC["Lydian"]["characteristic"]
    assert ch is not None
    assert ch["interval"] == 6
    assert "fourth" in ch["name"].lower()
    assert ch.get("callout")  # non-empty spoken callout text


def test_lydian_legend_includes_sharp_four() -> None:
    items = legend_items("Lydian")
    labels = [label for _color, label in items]
    colors = [color for color, _label in items]
    assert any("4" in lbl for lbl in labels)  # a ♯4 entry exists
    assert DEGREE_COLORS["sharp_fourth"] in colors


# ---------------------------------------------------------------------------
# TTS instructor phrase (consolidated, single source of truth)
# ---------------------------------------------------------------------------

def test_build_phrase_lydian_names_mode_without_callout() -> None:
    pos = SCALE_POSITIONS["C"][0]
    phrase = build_mode_phrase(pos, "Lydian", key="C", include_callout=False)
    assert "root of the Lydian scale" in phrase
    # No nagging callout on ordinary position changes.
    assert "raised fourth" not in phrase.lower()


def test_build_phrase_lydian_callout_on_mode_switch() -> None:
    pos = SCALE_POSITIONS["C"][0]
    phrase = build_mode_phrase(pos, "Lydian", key="C", include_callout=True)
    assert "root of the Lydian scale" in phrase
    assert "raised fourth" in phrase.lower()


def test_build_phrase_dorian_unchanged() -> None:
    pos = SCALE_POSITIONS["C"][0]
    phrase = build_mode_phrase(pos, "Dorian", key="C", include_callout=False)
    assert "root of the Dorian scale" in phrase


# ---------------------------------------------------------------------------
# Lydian tonic lands on the low E string in the open D-shape (FR follow-up).
# The D-shape open position originally muted string 6 (no D below the open D
# string), but the Lydian tonic is the 4th degree and sits on the low E string
# within the position — the scale should start from that lowest root.
# ---------------------------------------------------------------------------

def test_d_lydian_position1_includes_low_e_root() -> None:
    """D major Lydian (tonic G) position 1 must include G on the low E string, fret 3."""
    pos = SCALE_POSITIONS["D"][0]
    low_e = [n for n in pos["notes"] if n["string"] == 6]
    assert low_e, "D position 1 must include low E string notes"
    # G2 = midi 43 on the low E string is fret 3.
    assert any(n["fret"] == 3 and n["midi"] == 43 for n in low_e), (
        f"expected G (midi 43) on low E fret 3, got {sorted(n['fret'] for n in low_e)}"
    )


def test_eb_lydian_position1_includes_low_e_root() -> None:
    """Eb major Lydian (tonic Ab) position 1 must include Ab on the low E string, fret 4."""
    pos = SCALE_POSITIONS["Eb"][0]
    low_e = [n for n in pos["notes"] if n["string"] == 6]
    assert low_e, "Eb position 1 must include low E string notes"
    # Ab2 = midi 44 on the low E string is fret 4.
    assert any(n["fret"] == 4 and n["midi"] == 44 for n in low_e), (
        f"expected Ab (midi 44) on low E fret 4, got {sorted(n['fret'] for n in low_e)}"
    )


def test_d_lydian_phrase_starts_on_low_e_fret_3() -> None:
    """The spoken Lydian phrase for D must start on the low E string at fret 3."""
    pos = SCALE_POSITIONS["D"][0]
    phrase = build_mode_phrase(pos, "Lydian", key="D", include_callout=False)
    assert "root of the Lydian scale" in phrase
    assert "low E string at fret 3" in phrase, phrase


def test_eb_lydian_phrase_starts_on_low_e_fret_4() -> None:
    """The spoken Lydian phrase for Eb must start on the low E string at fret 4."""
    pos = SCALE_POSITIONS["Eb"][0]
    phrase = build_mode_phrase(pos, "Lydian", key="Eb", include_callout=False)
    assert "root of the Lydian scale" in phrase
    assert "low E string at fret 4" in phrase, phrase


def test_d_eb_position1_low_e_notes_stay_in_scale() -> None:
    """Added low E notes must remain within the parent major scale."""
    d_pcs = {2, 4, 6, 7, 9, 11, 1}    # D major
    eb_pcs = {3, 5, 7, 8, 10, 0, 2}   # Eb major
    for n in SCALE_POSITIONS["D"][0]["notes"]:
        if n["string"] == 6:
            assert n["midi"] % 12 in d_pcs
    for n in SCALE_POSITIONS["Eb"][0]["notes"]:
        if n["string"] == 6:
            assert n["midi"] % 12 in eb_pcs


# ---------------------------------------------------------------------------
# Mixolydian ♭7 highlight (FR-20260703-guitar-trainer-mixolydian-fix)
# ---------------------------------------------------------------------------

def test_mixolydian_flat_seventh_degree_type() -> None:
    degrees = MODE_SPEC["Mixolydian"]["degrees"]
    assert degrees[10]["type"] == "flat_seventh"
    assert degrees[10]["label"] == "♭7"
    # Root / third / fifth keep the standard palette types.
    assert degrees[0]["type"] == "root"
    assert degrees[4]["type"] == "third"
    assert degrees[7]["type"] == "fifth"


def test_mixolydian_accents_include_flat_seventh() -> None:
    assert 10 in MODE_SPEC["Mixolydian"]["accents"]


def test_mixolydian_characteristic_is_flattened_seventh() -> None:
    ch = MODE_SPEC["Mixolydian"]["characteristic"]
    assert ch is not None
    assert ch["interval"] == 10
    assert "seventh" in ch["name"].lower()
    assert ch.get("callout")


def test_mixolydian_major_sixth_not_colored() -> None:
    """Interval 9 (major 6th) must stay uncolored/gray per Tyler's instruction."""
    assert 9 not in MODE_SPEC["Mixolydian"]["degrees"]


def test_flat_seventh_palette_entries_exist_and_distinct() -> None:
    assert "flat_seventh" in DEGREE_COLORS
    color = DEGREE_COLORS["flat_seventh"]
    assert color.startswith("#")
    other_colors = {v for k, v in DEGREE_COLORS.items() if k != "flat_seventh"}
    assert color not in other_colors

    from training.mode_spec import DEGREE_TEXT, DEGREE_STROKE
    assert "flat_seventh" in DEGREE_TEXT
    assert "flat_seventh" in DEGREE_STROKE

