"""
❤Music — Guitar Scale Data
Template-based CAGED+ position loader.
FR-20260524-scale-data-sqlite-migration — migrated from hardcoded Python to
SQLite-backed template generation. Supports C major, G major, F major.

Public API (unchanged):
    SCALE_POSITIONS : dict[str, list[CagedPosition]]
    CAGED_POSITIONS : list[CagedPosition]   (C major alias)
    MIDI_TO_FREQ    : dict[int, float]
    get_scale_sequence(position_idx, key='C') -> list[int]
"""
from __future__ import annotations

import json
import math
from typing import TypedDict


class ScaleNote(TypedDict):
    string: int   # 1 = high e, 6 = low E
    fret: int     # 0-24
    midi: int     # 0-127


class CagedPosition(TypedDict):
    label: str
    root_string: str
    root_fret: int
    instructor_phrase: str
    notes: list[ScaleNote]


# ---------------------------------------------------------------------------
# Standard tuning open-string MIDI notes (string 1=high e … 6=low E)
# ---------------------------------------------------------------------------
_OPEN_MIDI: dict[int, int] = {
    1: 64,   # high e (E4)
    2: 59,   # B3
    3: 55,   # G3
    4: 50,   # D3
    5: 45,   # A2
    6: 40,   # low E (E2)
}

# ---------------------------------------------------------------------------
# Shape templates.
# Each entry: shape_name → (root_string_int, [[string, fret_delta], ...])
# root_string_int: the guitar string (1-6) where root_fret is anchored.
# fret_delta: added to root_fret to produce each note's absolute fret number.
# Verified against every original hardcoded note in scale_data_legacy.py.
# ---------------------------------------------------------------------------
_TEMPLATES: dict[str, tuple[int, list[list[int]]]] = {
    "C_shape": (5, [
        [6, -3], [6, -2], [6,  0],
        [5, -3], [5, -1], [5,  0],   # root on string 5 at root_fret
        [4, -3], [4, -1], [4,  0],
        [3, -3], [3, -1],
        [2, -3], [2, -2], [2,  0],
        [1, -3], [1, -2], [1,  0],
    ]),
    "A_shape": (5, [
        [6,  0], [6,  2], [6,  4],
        [5,  0], [5,  2], [5,  4],   # root on string 5 at root_fret
        [4,  0], [4,  2], [4,  4],
        [3,  1], [3,  2],
        [2,  0], [2,  2], [2,  3],
        [1,  0], [1,  2], [1,  4], [1,  5],
    ]),
    "G_shape": (6, [
        [6,  0],                      # root on string 6 at root_fret
        [5, -3], [5, -1], [5,  0],
        [4, -3], [4, -1], [4,  1],
        [3, -3], [3, -1],
        [2, -3], [2, -2], [2,  0],
        [1, -3], [1, -1], [1,  0],
    ]),
    "E_shape": (6, [
        [6,  0], [6,  2], [6,  4],   # root on string 6 at root_fret
        [5,  0], [5,  2], [5,  4],
        [4,  1], [4,  2], [4,  4],
        [3,  1], [3,  2],
        [2,  0], [2,  2], [2,  4],
        [1,  0], [1,  2], [1,  4],
    ]),
    "D_shape": (6, [
        [6,  0], [6,  2], [6,  4], [6,  5],   # root on string 6 at root_fret
        [5,  2], [5,  4], [5,  6],
        [4,  2], [4,  4], [4,  6],
        [3,  2], [3,  4], [3,  6],
        [2,  4], [2,  5],
        [1,  2], [1,  4], [1,  5],
    ]),
    "rock": (5, [
        [6, -2], [6,  0], [6,  2],
        [5, -1], [5,  0], [5,  2],   # root on string 5 at root_fret
        [4, -1], [4,  0], [4,  2],
        [3, -1], [3,  1],
        [2, -2], [2,  0], [2,  2],
        [1, -2], [1,  0], [1,  2],
    ]),
    "river": (6, [
        [6,  0], [6,  2],             # root on string 6 at root_fret
        [5, -1], [5,  0], [5,  2],
        [4, -1], [4,  1], [4,  2],
        [3, -1], [3,  1], [3,  2],
        [2,  0], [2,  2],
        [1, -1], [1,  0], [1,  2],
    ]),
    # Open D-string anchor; string 6 omitted (muted — no D below open D string).
    # Notes are the standard D_shape pattern shifted -2 frets to land at open position.
    "D_shape_open": (4, [
        [5,  0], [5,  2], [5,  4],   # A:  open A(5th),  B(6th),  C#(7th)
        [4,  0], [4,  2], [4,  4],   # D:  open D(root), E(2nd),  F#(3rd)
        [3,  0], [3,  2], [3,  4],   # G:  open G(4th),  A(5th),  B(6th)
        [2,  2], [2,  3],             # B:  C#(7th),      D(root)
        [1,  0], [1,  2], [1,  3],   # e:  open E(2nd),  F#(3rd), G(4th)
    ]),
}

# ---------------------------------------------------------------------------
# Position definitions.
# Each row: (shape_name, root_fret, label, root_string_name, instructor_phrase)
# root_fret: fret on the template's anchor string used for computation.
# root_string_name: human-readable display field (returned in CagedPosition).
# ---------------------------------------------------------------------------
_POSITION_DATA: dict[str, list[tuple[str, int, str, str, str]]] = {
    "C": [
        ("C_shape", 3,  "Position 1 — C shape (open)",             "A string",     "Start on the 3rd fret of the A string — C major C shape."),
        ("rock",    3,  "Position 2 — 石 Rock shape (1st fret)",    "A string",     "Start on the 3rd fret of the A string for C major 石 Rock shape."),
        ("A_shape", 3,  "Position 3 — A shape (3rd fret)",          "A string",     "Start on the 3rd fret of the A string — C major A shape."),
        ("G_shape", 8,  "Position 4 — G shape (8th fret)",          "Low E string", "Start on the 8th fret of the low E string — C major G shape."),
        ("river",   8,  "Position 5 — 川 River shape (8th fret)",   "Low E string", "Start on the 8th fret of the low E string — C major 川 River shape."),
        ("E_shape", 8,  "Position 6 — E shape (8th fret)",          "Low E string", "Start on the 8th fret of the low E string — C major E shape."),
        ("D_shape", 8,  "Position 7 — D shape (10th fret)",         "Low E string", "Start on the 8th fret of the E string — C major D shape."),
        ("C_shape", 15, "Position 8 — C shape (15th fret)",         "A string",     "Start on the 15th fret of the A string — C major C shape one octave up."),
        ("rock",    15, "Position 9 — 石 Rock shape (13th fret)",   "A string",     "Start on the 15th fret of the A string for C major 石 Rock shape (high octave)."),
        ("A_shape", 15, "Position 10 — A shape (15th fret)",        "A string",     "Start on the 15th fret of the A string — C major A shape one octave up."),
        ("G_shape", 20, "Position 11 — G shape (20th fret)",        "Low E string", "Start on the 20th fret of the low E string — C major G shape one octave up."),
        ("river",   20, "Position 12 — 川 River shape (20th fret)", "Low E string", "Start on the 20th fret of the low E string — C major 川 River shape (high octave)."),
    ],
    "G": [
        ("G_shape", 3,  "Position 1 — G shape (open)",              "Low E string", "Start on the 3rd fret of the low E string — G major G shape."),
        ("river",   3,  "Position 2 — 川 River shape (3rd fret)",   "Low E string", "Start on the 3rd fret of the low E string — G major 川 River shape."),
        ("E_shape", 3,  "Position 3 — E shape (3rd fret)",          "Low E string", "Start on the 3rd fret of the low E string — G major E shape."),
        ("D_shape", 3,  "Position 4 — D shape (5th fret)",          "Low E string", "Start on the 3rd fret of the low E string — G major D shape."),
        ("C_shape", 10, "Position 5 — C shape (7th fret)",          "A string",     "Start on the 10th fret of the A string — G major C shape."),
        ("rock",    10, "Position 6 — 石 Rock shape (8th fret)",    "A string",     "Start on the 10th fret of the A string for G major 石 Rock shape."),
        ("A_shape", 10, "Position 7 — A shape (10th fret)",         "A string",     "Start on the 10th fret of the A string — G major A shape."),
        ("G_shape", 15, "Position 8 — G shape (15th fret)",         "Low E string", "Start on the 15th fret of the low E string — G major G shape one octave up."),
        ("river",   15, "Position 9 — 川 River shape (15th fret)",  "Low E string", "Start on the 15th fret of the low E string — G major 川 River shape (high octave)."),
        ("E_shape", 15, "Position 10 — E shape (15th fret)",        "Low E string", "Start on the 15th fret of the low E string — G major E shape (high octave)."),
        ("D_shape", 15, "Position 11 — D shape (17th fret)",        "Low E string", "Start on the 15th fret of the low E string — G major D shape one octave up."),
    ],
    "F": [
        ("river",   1,  "Position 1 — 川 River shape (1st fret)",   "Low E string", "Start on the 1st fret of the low E string — F major 川 River shape."),
        ("E_shape", 1,  "Position 2 — E shape (1st fret)",          "Low E string", "Start on the 1st fret of the low E string — F major E shape."),
        ("D_shape", 1,  "Position 3 — D shape (1st fret)",          "Low E string", "Start on the 1st fret of the low E string — F major D shape."),
        ("C_shape", 8,  "Position 4 — C shape (8th fret)",          "A string",     "Start on the 8th fret of the A string — F major C shape."),
        ("rock",    8,  "Position 5 — 石 Rock shape (8th fret)",    "A string",     "Start on the 8th fret of the A string for F major 石 Rock shape."),
        ("A_shape", 8,  "Position 6 — A shape (8th fret)",          "A string",     "Start on the 8th fret of the A string — F major A shape."),
        ("G_shape", 13, "Position 7 — G shape (13th fret)",         "Low E string", "Start on the 13th fret of the low E string — F major G shape."),
        ("river",   13, "Position 8 — 川 River shape (13th fret)",  "Low E string", "Start on the 13th fret of the low E string — F major 川 River shape (high octave)."),
        ("E_shape", 13, "Position 9 — E shape (13th fret)",         "Low E string", "Start on the 13th fret of the low E string — F major E shape (high octave)."),
        ("D_shape", 13, "Position 10 — D shape (13th fret)",        "Low E string", "Start on the 13th fret of the low E string — F major D shape (high octave)."),
        ("C_shape", 20, "Position 11 — C shape (20th fret)",        "A string",     "Start on the 20th fret of the A string — F major C shape (high octave)."),
        ("rock",    20, "Position 12 — 石 Rock shape (20th fret)",  "A string",     "Start on the 20th fret of the A string for F major 石 Rock shape (high octave)."),
    ],
    # FR-20260524-guitar-trainer-d-bb-major
    "D": [
        ("D_shape_open", 0, "Position 1 — D shape (open)",              "D string",     "Open strings — start on the open D string — D major open D shape."),
        ("C_shape", 5,  "Position 2 — C shape (5th fret)",           "A string",     "Start on the 5th fret of the A string — D major C shape."),
        ("rock",    5,  "Position 3 — 石 Rock shape (5th fret)",     "A string",     "Start on the 5th fret of the A string for D major 石 Rock shape."),
        ("A_shape", 5,  "Position 4 — A shape (5th fret)",           "A string",     "Start on the 5th fret of the A string — D major A shape."),
        ("G_shape", 10, "Position 5 — G shape (10th fret)",          "Low E string", "Start on the 10th fret of the low E string — D major G shape."),
        ("river",   10, "Position 6 — 川 River shape (10th fret)",   "Low E string", "Start on the 10th fret of the low E string — D major 川 River shape."),
        ("E_shape", 10, "Position 7 — E shape (10th fret)",          "Low E string", "Start on the 10th fret of the low E string — D major E shape."),
        ("D_shape", 10, "Position 8 — D shape (10th fret)",          "Low E string", "Start on the 10th fret of the low E string — D major D shape."),
        ("C_shape", 17, "Position 9 — C shape (17th fret)",          "A string",     "Start on the 17th fret of the A string — D major C shape one octave up."),
        ("rock",    17, "Position 10 — 石 Rock shape (17th fret)",   "A string",     "Start on the 17th fret of the A string for D major 石 Rock shape (high octave)."),
        ("A_shape", 17, "Position 11 — A shape (17th fret)",         "A string",     "Start on the 17th fret of the A string — D major A shape one octave up."),
    ],
    "E": [
        ("E_shape",  0,  "Position 1 — E shape (open)",             "Low E string", "Start on the open low E string — E major E shape."),
        ("D_shape",  0,  "Position 2 — D shape (open)",             "Low E string", "Start on the open low E string — E major D shape."),
        ("C_shape",  7,  "Position 3 — C shape (7th fret)",          "A string",     "Start on the 7th fret of the A string — E major C shape."),
        ("rock",     7,  "Position 4 — 石 Rock shape (7th fret)",     "A string",     "Start on the 7th fret of the A string for E major 石 Rock shape."),
        ("A_shape",  7,  "Position 5 — A shape (7th fret)",          "A string",     "Start on the 7th fret of the A string — E major A shape."),
        ("G_shape", 12,  "Position 6 — G shape (12th fret)",         "Low E string", "Start on the 12th fret of the low E string — E major G shape."),
        ("river",   12,  "Position 7 — 川 River shape (12th fret)",   "Low E string", "Start on the 12th fret of the low E string — E major 川 River shape."),
        ("E_shape", 12,  "Position 8 — E shape (12th fret)",         "Low E string", "Start on the 12th fret of the low E string — E major E shape one octave up."),
        ("D_shape", 12,  "Position 9 — D shape (12th fret)",         "Low E string", "Start on the 12th fret of the low E string — E major D shape one octave up."),
        ("C_shape", 19,  "Position 10 — C shape (19th fret)",         "A string",     "Start on the 19th fret of the A string — E major C shape one octave up."),
        ("rock",    19,  "Position 11 — 石 Rock shape (19th fret)",    "A string",     "Start on the 19th fret of the A string for E major 石 Rock shape (high octave)."),
    ],
    "F#": [
        ("E_shape",  2,  "Position 1 — E shape (2nd fret)",           "Low E string", "Start on the 2nd fret of the low E string — F# major E shape."),
        ("D_shape",  2,  "Position 2 — D shape (2nd fret)",           "Low E string", "Start on the 2nd fret of the low E string — F# major D shape."),
        ("C_shape",  9,  "Position 3 — C shape (9th fret)",           "A string",     "Start on the 9th fret of the A string — F# major C shape."),
        ("rock",     9,  "Position 4 — 石 Rock shape (9th fret)",      "A string",     "Start on the 9th fret of the A string for F# major 石 Rock shape."),
        ("A_shape",  9,  "Position 5 — A shape (9th fret)",           "A string",     "Start on the 9th fret of the A string — F# major A shape."),
        ("G_shape", 14,  "Position 6 — G shape (14th fret)",          "Low E string", "Start on the 14th fret of the low E string — F# major G shape."),
        ("river",   14,  "Position 7 — 川 River shape (14th fret)",     "Low E string", "Start on the 14th fret of the low E string — F# major 川 River shape."),
        ("E_shape", 14,  "Position 8 — E shape (14th fret)",           "Low E string", "Start on the 14th fret of the low E string — F# major E shape."),
        ("D_shape", 14,  "Position 9 — D shape (14th fret)",           "Low E string", "Start on the 14th fret of the low E string — F# major D shape."),
        ("C_shape", 21,  "Position 10 — C shape (21st fret)",         "A string",     "Start on the 21st fret of the A string — F# major C shape one octave up."),
        ("rock",    21,  "Position 11 — 石 Rock shape (21st fret)",    "A string",     "Start on the 21st fret of the A string for F# major 石 Rock shape (high octave)."),
    ],
    "Bb": [
        ("A_shape", 1,  "Position 1 — A shape (1st fret)",           "A string",     "Start on the 1st fret of the A string — B-flat major A shape."),
        ("G_shape", 6,  "Position 2 — G shape (6th fret)",           "Low E string", "Start on the 6th fret of the low E string — B-flat major G shape."),
        ("river",   6,  "Position 3 — 川 River shape (6th fret)",    "Low E string", "Start on the 6th fret of the low E string — B-flat major 川 River shape."),
        ("E_shape", 6,  "Position 4 — E shape (6th fret)",           "Low E string", "Start on the 6th fret of the low E string — B-flat major E shape."),
        ("D_shape", 6,  "Position 5 — D shape (6th fret)",           "Low E string", "Start on the 6th fret of the low E string — B-flat major D shape."),
        ("C_shape", 13, "Position 6 — C shape (13th fret)",          "A string",     "Start on the 13th fret of the A string — B-flat major C shape."),
        ("rock",    13, "Position 7 — 石 Rock shape (13th fret)",    "A string",     "Start on the 13th fret of the A string for B-flat major 石 Rock shape."),
        ("A_shape", 13, "Position 8 — A shape (13th fret)",          "A string",     "Start on the 13th fret of the A string — B-flat major A shape one octave up."),
        ("G_shape", 18, "Position 9 — G shape (18th fret)",          "Low E string", "Start on the 18th fret of the low E string — B-flat major G shape one octave up."),
        ("river",   18, "Position 10 — 川 River shape (18th fret)",  "Low E string", "Start on the 18th fret of the low E string — B-flat major 川 River shape (high octave)."),
        ("E_shape", 18, "Position 11 — E shape (18th fret)",         "Low E string", "Start on the 18th fret of the low E string — B-flat major E shape (high octave)."),
    ],
    # FR-20260525-guitar-trainer-b-eb-major
    "B": [
        ("rock",         2,  "Position 1 — 石 Rock shape (2nd fret)",    "A string",     "Start on the 2nd fret of the A string for B major 石 Rock shape."),
        ("A_shape",      2,  "Position 2 — A shape (2nd fret)",          "A string",     "Start on the 2nd fret of the A string — B major A shape."),
        ("G_shape",      7,  "Position 3 — G shape (7th fret)",          "Low E string", "Start on the 7th fret of the low E string — B major G shape."),
        ("river",        7,  "Position 4 — 川 River shape (7th fret)",   "Low E string", "Start on the 7th fret of the low E string — B major 川 River shape."),
        ("E_shape",      7,  "Position 5 — E shape (7th fret)",          "Low E string", "Start on the 7th fret of the low E string — B major E shape."),
        ("D_shape",      7,  "Position 6 — D shape (7th fret)",          "Low E string", "Start on the 7th fret of the low E string — B major D shape."),
        ("C_shape",      14, "Position 7 — C shape (14th fret)",         "A string",     "Start on the 14th fret of the A string — B major C shape."),
        ("rock",         14, "Position 8 — 石 Rock shape (14th fret)",   "A string",     "Start on the 14th fret of the A string for B major 石 Rock shape (high octave)."),
        ("A_shape",      14, "Position 9 — A shape (14th fret)",         "A string",     "Start on the 14th fret of the A string — B major A shape one octave up."),
        ("G_shape",      19, "Position 10 — G shape (19th fret)",        "Low E string", "Start on the 19th fret of the low E string — B major G shape one octave up."),
        ("river",        19, "Position 11 — 川 River shape (19th fret)", "Low E string", "Start on the 19th fret of the low E string — B major 川 River shape (high octave)."),
    ],
    "Eb": [
        ("D_shape_open", 1,  "Position 1 — D shape (1st fret)",          "D string",     "Start on the 1st fret of the D string — E-flat major D shape."),
        ("C_shape",      6,  "Position 2 — C shape (6th fret)",          "A string",     "Start on the 6th fret of the A string — E-flat major C shape."),
        ("rock",         6,  "Position 3 — 石 Rock shape (6th fret)",    "A string",     "Start on the 6th fret of the A string for E-flat major 石 Rock shape."),
        ("A_shape",      6,  "Position 4 — A shape (6th fret)",          "A string",     "Start on the 6th fret of the A string — E-flat major A shape."),
        ("G_shape",      11, "Position 5 — G shape (11th fret)",         "Low E string", "Start on the 11th fret of the low E string — E-flat major G shape."),
        ("river",        11, "Position 6 — 川 River shape (11th fret)",  "Low E string", "Start on the 11th fret of the low E string — E-flat major 川 River shape."),
        ("E_shape",      11, "Position 7 — E shape (11th fret)",         "Low E string", "Start on the 11th fret of the low E string — E-flat major E shape."),
        ("D_shape",      11, "Position 8 — D shape (11th fret)",         "Low E string", "Start on the 11th fret of the low E string — E-flat major D shape."),
        ("C_shape",      18, "Position 9 — C shape (18th fret)",         "A string",     "Start on the 18th fret of the A string — E-flat major C shape one octave up."),
        ("rock",         18, "Position 10 — 石 Rock shape (18th fret)",  "A string",     "Start on the 18th fret of the A string for E-flat major 石 Rock shape (high octave)."),
    ],
    # FR-20260531-guitar-trainer-a-major
    "A": [
        ("A_shape",  0,  "Position 1 — A shape (open)",               "A string",     "Start on the open A string — A major A shape."),
        ("G_shape",  5,  "Position 2 — G shape (5th fret)",           "Low E string", "Start on the 5th fret of the low E string — A major G shape."),
        ("river",    5,  "Position 3 — 川 River shape (5th fret)",    "Low E string", "Start on the 5th fret of the low E string — A major 川 River shape."),
        ("E_shape",  5,  "Position 4 — E shape (5th fret)",           "Low E string", "Start on the 5th fret of the low E string — A major E shape."),
        ("D_shape",  5,  "Position 5 — D shape (5th fret)",           "Low E string", "Start on the 5th fret of the low E string — A major D shape."),
        ("C_shape",  12, "Position 6 — C shape (12th fret)",          "A string",     "Start on the 12th fret of the A string — A major C shape."),
        ("rock",     12, "Position 7 — 石 Rock shape (12th fret)",    "A string",     "Start on the 12th fret of the A string for A major 石 Rock shape."),
        ("A_shape",  12, "Position 8 — A shape (12th fret)",          "A string",     "Start on the 12th fret of the A string — A major A shape one octave up."),
        ("G_shape",  17, "Position 9 — G shape (17th fret)",          "Low E string", "Start on the 17th fret of the low E string — A major G shape one octave up."),
        ("river",    17, "Position 10 — 川 River shape (17th fret)",  "Low E string", "Start on the 17th fret of the low E string — A major 川 River shape (high octave)."),
        ("E_shape",  17, "Position 11 — E shape (17th fret)",         "Low E string", "Start on the 17th fret of the low E string — A major E shape (high octave)."),
    ],
}


# ---------------------------------------------------------------------------
# Core generation: build SCALE_POSITIONS from _TEMPLATES + _POSITION_DATA
# ---------------------------------------------------------------------------

def _generate_from_templates() -> dict[str, list[CagedPosition]]:
    """Build SCALE_POSITIONS entirely from the in-process template tables.

    Used as the primary data source (and as DB-free fallback for CI/tests).
    """
    result: dict[str, list[CagedPosition]] = {}
    for key_name, rows in _POSITION_DATA.items():
        positions: list[CagedPosition] = []
        for shape_name, root_fret, label, root_string_name, phrase in rows:
            _, offsets = _TEMPLATES[shape_name]
            notes: list[ScaleNote] = [
                ScaleNote(
                    string=s,
                    fret=root_fret + delta,
                    midi=_OPEN_MIDI[s] + root_fret + delta,
                )
                for s, delta in offsets
            ]
            positions.append(
                CagedPosition(
                    label=label,
                    root_string=root_string_name,
                    root_fret=root_fret,
                    instructor_phrase=phrase,
                    notes=notes,
                )
            )
        result[key_name] = positions
    return result


def _build_from_conn(conn) -> dict[str, list[CagedPosition]]:
    """Load SCALE_POSITIONS from a SQLite connection (heartmusic.db).

    Falls back to _generate_from_templates() if tables are not yet seeded.
    """
    templates: dict[str, list[list[int]]] = {}
    try:
        for row in conn.execute(
            "SELECT shape_name, note_offsets FROM guitar_scale_templates"
        ):
            templates[row[0]] = json.loads(row[1])
    except Exception:
        return _generate_from_templates()

    if not templates:
        return _generate_from_templates()

    rows = conn.execute(
        "SELECT key_name, shape_name, root_fret, label, root_string_name, "
        "instructor_phrase "
        "FROM guitar_scale_positions "
        "ORDER BY key_name, position_order"
    ).fetchall()

    if not rows:
        return _generate_from_templates()

    result: dict[str, list[CagedPosition]] = {}
    for row in rows:
        key_name, shape_name, root_fret, label, rsn, phrase = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )
        offsets = templates[shape_name]
        notes: list[ScaleNote] = [
            ScaleNote(
                string=s,
                fret=root_fret + delta,
                midi=_OPEN_MIDI[s] + root_fret + delta,
            )
            for s, delta in offsets
        ]
        result.setdefault(key_name, []).append(
            CagedPosition(
                label=label,
                root_string=rsn,
                root_fret=root_fret,
                instructor_phrase=phrase,
                notes=notes,
            )
        )
    return result


def _load() -> dict[str, list[CagedPosition]]:
    """Load SCALE_POSITIONS — templates as baseline, DB overlays where seeded.

    Using templates as the baseline ensures keys added to _POSITION_DATA are
    always available even before seed_scale_data.py has been re-run.
    """
    base = _generate_from_templates()
    try:
        from utils.init_db import get_connection  # noqa: PLC0415
        conn = get_connection()
        db_result = _build_from_conn(conn)
        if db_result:
            base.update(db_result)
    except Exception:  # nosec B110
        pass
    return base


# ---------------------------------------------------------------------------
# Module-level singletons (populated once at import time)
# ---------------------------------------------------------------------------
SCALE_POSITIONS: dict[str, list[CagedPosition]] = _load()

# A# is enharmonically identical to Bb — expose as a transparent alias
SCALE_POSITIONS["A#"] = SCALE_POSITIONS["Bb"]

# D# is enharmonically identical to Eb — expose as a transparent alias
SCALE_POSITIONS["D#"] = SCALE_POSITIONS["Eb"]

# Backward-compat alias — C major positions
CAGED_POSITIONS: list[CagedPosition] = SCALE_POSITIONS["C"]

# MIDI → frequency mapping (equal temperament, A4 = 440 Hz)
MIDI_TO_FREQ: dict[int, float] = {
    midi: round(440.0 * math.pow(2.0, (midi - 69) / 12.0), 4)
    for midi in range(128)
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_scale_sequence(position_idx: int, key: str = "C") -> list[int]:
    """Return ascending + descending MIDI sequence for a scale position (0-indexed)."""
    positions = SCALE_POSITIONS.get(key)
    if positions is None:
        raise ValueError(f"Unknown key {key!r}; available: {list(SCALE_POSITIONS)}")
    if not 0 <= position_idx < len(positions):
        raise ValueError(
            f"position_idx must be 0-{len(positions) - 1}, got {position_idx}"
        )
    notes = positions[position_idx]["notes"]
    seen: set[int] = set()
    asc: list[int] = []
    for midi in sorted(n["midi"] for n in notes):
        if midi not in seen:
            seen.add(midi)
            asc.append(midi)
    desc = list(reversed(asc[:-1]))
    return asc + desc
