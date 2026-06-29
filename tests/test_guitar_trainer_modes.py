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
