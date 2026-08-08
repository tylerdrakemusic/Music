"""
❤Music — Pentatonic scale specification (single source of truth).

FR-20260806-guitar-trainer-pentatonic-scales

Design decisions (from prototype review):
  - 2B palette: warm blues/amber, root stays #ff0080, distinct from diatonic
  - 5B: minor pentatonic key selector = relative major (key=C → A minor penta)
  - Instructor phrases say the actual minor root, not the relative major

Public API:
    PENTATONIC_SPEC       : dict[str, dict]  — per-family intervals, degrees, tts_label
    PENTA_DEGREE_COLORS   : dict[str, str]   — degree type → hex (2B warm palette)
    PENTA_DEGREE_TEXT     : dict[str, str]   — degree type → text color
    PENTA_DEGREE_STROKE   : dict[str, str]   — degree type → stroke color
    penta_relative_minor_root(key) -> str    — relative minor root note name for key
    build_penta_phrase(pos, key, family) -> str
"""
from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# 2B warm palette — distinct from diatonic DEGREE_COLORS
# ---------------------------------------------------------------------------
PENTA_DEGREE_COLORS: dict[str, str] = {
    "root":        "#ff0080",  # stays hot-pink for muscle memory
    "penta_second": "#c5f0a4",  # sage green — major 2nd
    "penta_third":  "#ffb347",  # warm amber — major or minor 3rd
    "penta_fourth": "#ffe66d",  # gold — 4th (minor penta)
    "penta_fifth":  "#a8d8ea",  # sky blue — 5th
    "penta_sixth":  "#a8d8ea",  # same sky for major 6th
    "penta_flat7":  "#c77dff",  # violet — ♭7 (minor penta)
}

PENTA_DEGREE_TEXT: dict[str, str] = {
    "root":         "#ffffff",
    "penta_second": "#000000",
    "penta_third":  "#000000",
    "penta_fourth": "#000000",
    "penta_fifth":  "#000000",
    "penta_sixth":  "#000000",
    "penta_flat7":  "#ffffff",
}

PENTA_DEGREE_STROKE: dict[str, str] = {k: "#000000" for k in PENTA_DEGREE_COLORS}


def _deg(type_: str, label: str) -> dict[str, str]:
    return {"type": type_, "label": label}


# ---------------------------------------------------------------------------
# PENTATONIC_SPEC
# Major pentatonic: root, 2nd, 3rd, 5th, 6th (0,2,4,7,9)
# Minor pentatonic: root, ♭3, 4th, 5th, ♭7  (0,3,5,7,10)
# intervals include the octave repeat at index 5 for playback symmetry
# ---------------------------------------------------------------------------
PENTATONIC_SPEC: dict[str, dict] = {
    "major_pentatonic": {
        "intervals":  (0, 2, 4, 7, 9, 12),
        "tts_label":  "major pentatonic",
        "degrees": {
            0: _deg("root",         "Root"),
            2: _deg("penta_second", "2nd"),
            4: _deg("penta_third",  "3rd"),
            7: _deg("penta_fifth",  "5th"),
            9: _deg("penta_sixth",  "6th"),
        },
    },
    "minor_pentatonic": {
        "intervals":  (0, 3, 5, 7, 10, 12),
        "tts_label":  "minor pentatonic",
        "degrees": {
            0:  _deg("root",         "Root"),
            3:  _deg("penta_third",  "♭3"),
            5:  _deg("penta_fourth", "4th"),
            7:  _deg("penta_fifth",  "5th"),
            10: _deg("penta_flat7",  "♭7"),
        },
    },
}

# ---------------------------------------------------------------------------
# Key / pitch-class helpers (mirrors mode_spec._KEY_PC)
# ---------------------------------------------------------------------------
_KEY_PC: dict[str, int] = {
    "C": 0, "Db": 1, "C#": 1, "D": 2, "Eb": 3, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "Ab": 8, "G#": 8, "A": 9, "Bb": 10, "A#": 10, "B": 11,
}
_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_NAMES  = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_FLAT_KEYS   = {"F", "Bb", "Eb", "Ab", "Db", "Gb"}

# Relative minor offset: 9 semitones above the major tonic (or -3 mod 12)
_RELATIVE_MINOR_OFFSET = 9


def penta_relative_minor_root(key: str) -> str:
    """Return the display name of the relative natural-minor root for *key*.

    key='C' → 'A', key='G' → 'E', key='F' → 'D', etc.
    Used for 5B: minor-pentatonic key selector = relative major.
    """
    pc = (_KEY_PC.get(key, 0) + _RELATIVE_MINOR_OFFSET) % 12
    raw = _FLAT_NAMES[pc] if key in _FLAT_KEYS else _SHARP_NAMES[pc]
    return raw


def _spoken_key(key: str) -> str:
    """Convert a key symbol to a TTS-readable string (e.g. 'Db' → 'D flat')."""
    return (
        key.replace("#", " sharp")
           .replace("b", " flat")
           .strip()
    )


def build_penta_phrase(pos: dict, key: str, family: str) -> str:
    """Return a TTS instructor phrase for a pentatonic position.

    For minor pentatonic: says the relative-minor root, not the major key.
    """
    spec = PENTATONIC_SPEC.get(family)
    if spec is None:
        raise ValueError(f"Unknown pentatonic family: {family!r}")

    root_fret = pos.get("root_fret", 0)
    string_name = pos.get("root_string", "A string")
    label = pos.get("label", "")
    box_part = label.split("—")[0].strip()

    if family == "minor_pentatonic":
        minor_root = penta_relative_minor_root(key)
        spoken_root = _spoken_key(minor_root)
        return (
            f"Start on the {root_fret}th fret of the {string_name} — "
            f"{spoken_root} minor pentatonic, {box_part}."
        )
    else:
        spoken_key = _spoken_key(key)
        return (
            f"Start on the {root_fret}th fret of the {string_name} — "
            f"{spoken_key} major pentatonic, {box_part}."
        )
