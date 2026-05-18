"""
❤Music — Guitar Scale Data
CAGED positions for C major scale on standard-tuned 6-string guitar.
FR-20260517-guitar-trainer-scale-exercises
"""
from __future__ import annotations

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


def _note(string: int, fret: int) -> ScaleNote:
    return ScaleNote(string=string, fret=fret, midi=_OPEN_MIDI[string] + fret)


# ---------------------------------------------------------------------------
# All 5 CAGED positions for C major scale
# Standard C major scale intervals: W W H W W W H (C D E F G A B C)
# Notes: C D E F G A B  (midi: 60 62 64 65 67 69 71)
# ---------------------------------------------------------------------------

# Helper: check if a midi pitch class is in C major (no sharps/flats)
_C_MAJOR_PCS = {0, 2, 4, 5, 7, 9, 11}  # C D E F G A B


def _in_c_major(midi: int) -> bool:
    return (midi % 12) in _C_MAJOR_PCS


# Position 1 — C shape (open position, spans frets 0-3)
# Root: C on B string fret 1 (midi 60)
_pos1_candidates: list[ScaleNote] = []
for s in range(1, 7):
    for f in range(0, 4):
        n = _note(s, f)
        if _in_c_major(n["midi"]) and 40 <= n["midi"] <= 76:
            _pos1_candidates.append(n)
_pos1_notes = sorted(_pos1_candidates, key=lambda n: (n["midi"], n["string"]))
# Deduplicate by midi (keep lowest string number = most standard fingering)
_seen: set[int] = set()
_pos1_dedup: list[ScaleNote] = []
for n in sorted(_pos1_candidates, key=lambda x: (x["midi"], x["string"])):
    if n["midi"] not in _seen:
        _seen.add(n["midi"])
        _pos1_dedup.append(n)

# Position 2 — A shape (root on A string fret 3, spans frets 2-5)
_pos2_candidates: list[ScaleNote] = []
for s in range(1, 7):
    for f in range(2, 6):
        n = _note(s, f)
        if _in_c_major(n["midi"]) and 45 <= n["midi"] <= 79:
            _pos2_candidates.append(n)
_seen2: set[int] = set()
_pos2_dedup: list[ScaleNote] = []
for n in sorted(_pos2_candidates, key=lambda x: (x["midi"], x["string"])):
    if n["midi"] not in _seen2:
        _seen2.add(n["midi"])
        _pos2_dedup.append(n)

# Position 3 — G shape (root on low E string fret 8 / high e fret 8, spans frets 5-8)
_pos3_candidates: list[ScaleNote] = []
for s in range(1, 7):
    for f in range(5, 9):
        n = _note(s, f)
        if _in_c_major(n["midi"]) and 50 <= n["midi"] <= 84:
            _pos3_candidates.append(n)
_seen3: set[int] = set()
_pos3_dedup: list[ScaleNote] = []
for n in sorted(_pos3_candidates, key=lambda x: (x["midi"], x["string"])):
    if n["midi"] not in _seen3:
        _seen3.add(n["midi"])
        _pos3_dedup.append(n)

# Position 4 — E shape (root on D string fret 10, spans frets 7-10)
_pos4_candidates: list[ScaleNote] = []
for s in range(1, 7):
    for f in range(7, 11):
        n = _note(s, f)
        if _in_c_major(n["midi"]) and 55 <= n["midi"] <= 88:
            _pos4_candidates.append(n)
_seen4: set[int] = set()
_pos4_dedup: list[ScaleNote] = []
for n in sorted(_pos4_candidates, key=lambda x: (x["midi"], x["string"])):
    if n["midi"] not in _seen4:
        _seen4.add(n["midi"])
        _pos4_dedup.append(n)

# Position 5 — D shape (root on G string fret 12, spans frets 10-13)
_pos5_candidates: list[ScaleNote] = []
for s in range(1, 7):
    for f in range(10, 14):
        n = _note(s, f)
        if _in_c_major(n["midi"]) and 60 <= n["midi"] <= 93:
            _pos5_candidates.append(n)
_seen5: set[int] = set()
_pos5_dedup: list[ScaleNote] = []
for n in sorted(_pos5_candidates, key=lambda x: (x["midi"], x["string"])):
    if n["midi"] not in _seen5:
        _seen5.add(n["midi"])
        _pos5_dedup.append(n)


CAGED_POSITIONS: list[CagedPosition] = [
    CagedPosition(
        label="Position 1 — C shape (open)",
        root_string="B string",
        root_fret=1,
        instructor_phrase="Start on the 1st fret of the B string — C major open position.",
        notes=_pos1_dedup,
    ),
    CagedPosition(
        label="Position 2 — A shape (3rd fret)",
        root_string="A string",
        root_fret=3,
        instructor_phrase="Start on the 3rd fret of the A string — C major A shape.",
        notes=_pos2_dedup,
    ),
    CagedPosition(
        label="Position 3 — G shape (8th fret)",
        root_string="Low E string",
        root_fret=8,
        instructor_phrase="Start on the 8th fret of the low E string — C major G shape.",
        notes=_pos3_dedup,
    ),
    CagedPosition(
        label="Position 4 — E shape (10th fret)",
        root_string="D string",
        root_fret=10,
        instructor_phrase="Start on the 10th fret of the D string — C major E shape.",
        notes=_pos4_dedup,
    ),
    CagedPosition(
        label="Position 5 — D shape (12th fret)",
        root_string="G string",
        root_fret=12,
        instructor_phrase="Start on the 12th fret of the G string — C major D shape.",
        notes=_pos5_dedup,
    ),
]


# ---------------------------------------------------------------------------
# MIDI → frequency (equal temperament)
# ---------------------------------------------------------------------------
MIDI_TO_FREQ: dict[int, float] = {
    midi: round(440.0 * math.pow(2.0, (midi - 69) / 12.0), 4)
    for midi in range(128)
}


def get_scale_sequence(position_idx: int) -> list[int]:
    """Return ascending + descending MIDI note sequence for a CAGED position (0-indexed).

    Sequence: ascending from lowest to highest note, then descending back to lowest.
    """
    if not 0 <= position_idx < len(CAGED_POSITIONS):
        raise ValueError(f"position_idx must be 0-{len(CAGED_POSITIONS) - 1}, got {position_idx}")
    notes = CAGED_POSITIONS[position_idx]["notes"]
    midis_asc = sorted(n["midi"] for n in notes)
    # Remove duplicate midi values
    seen: set[int] = set()
    asc: list[int] = []
    for m in midis_asc:
        if m not in seen:
            seen.add(m)
            asc.append(m)
    desc = list(reversed(asc[:-1]))  # descend back to lowest (don't repeat top)
    return asc + desc
