"""
❤Music — Guitar Scale Data
CAGED positions for C major and G major scales on standard-tuned 6-string guitar.
FR-20260517-guitar-trainer-scale-exercises
FR-20260522-guitar-trainer-multi-key
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


def _pos(*string_fret_pairs: tuple[int, int]) -> list[ScaleNote]:
    """Build a note list from (string, fret) pairs."""
    return [_note(s, f) for s, f in string_fret_pairs]


# ---------------------------------------------------------------------------
# All 5 CAGED positions — C major scale, explicit note definitions
# String numbering: 1=high e (E4), 2=B3, 3=G3, 4=D3, 5=A2, 6=low E (E2)
# C major scale intervals: C D E F G A B  (midi pc: 0 2 4 5 7 9 11)
# Root C appears on each position: marked ★
# ---------------------------------------------------------------------------

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 1 — C shape (open, frets 0–3)  ✅ VERIFIED by Tyler — DO NOT EDIT  ║
# ║  low E: 0,1,3  A: 0,2,3  D: 0,2,3  G: 0,2  B: 0,1,3  e: 0,1,3        ║
# ║  Playback: starts on root C3★ (A fret 3), ascends to G4, descends to   ║
# ║  E2, then returns up to B2 — closed loop, no duplicate root at seam.   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: A5 fret 3 = C3★  |  B2 fret 1 = C4★
_pos1_notes = _pos(
    (6, 0), (6, 1), (6, 3),       # low E:  E2  F2  G2
    (5, 0), (5, 2), (5, 3),       # A:      A2  B2  C3★
    (4, 0), (4, 2), (4, 3),       # D:      D3  E3  F3
    (3, 0), (3, 2),               # G:      G3  A3
    (2, 0), (2, 1), (2, 3),       # B:      B3  C4★ D4
    (1, 0), (1, 1), (1, 3),       # e:      E4  F4  G4
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 2 — A shape (frets 3–8)  ✅ VERIFIED by Tyler — DO NOT EDIT  ║
# ║  low E: 3,5,7  A: 3,5,7  D: 3,5,7  G: 4,5  B: 3,5,6  e: 3,5,7,8      ║
# ║  Playback: starts on root C3★ (A fret 3), up to C5★, down to G2,       ║
# ║  returns A2→B2 — closed loop, no duplicate root at seam.               ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: A5 fret 3 = C3★  |  G3 fret 5 = C4★  |  e1 fret 8 = C5★
_pos2_notes = _pos(
    (6, 3), (6, 5), (6, 7),       # low E:  G2  A2  B2
    (5, 3), (5, 5), (5, 7),       # A:      C3★ D3  E3
    (4, 3), (4, 5), (4, 7),       # D:      F3  G3  A3
    (3, 4), (3, 5),               # G:      B3  C4★  (semitone shift at G–B break)
    (2, 3), (2, 5), (2, 6),       # B:      D4  E4  F4
    (1, 3), (1, 5), (1, 7), (1, 8),  # e:  G4  A4  B4  C5★
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 3 — G shape (frets 5–9)  ✅ VERIFIED by Tyler — DO NOT EDIT  ║
# ║  low E: 8  A: 5,7,8  D: 5,7,9  G: 5,7  B: 5,6,8  e: 5,7,8            ║
# ║  Playback: starts on root C3★ (low E fret 8), ascends to C5★,          ║
# ║  descends to D3 — closed loop, no duplicate root at seam.              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: E6 fret 8 = C3★  |  G3 fret 5 = C4★  |  e1 fret 8 = C5★
_pos3_notes = _pos(
    (6, 8),                       # low E:  C3★
    (5, 5), (5, 7), (5, 8),       # A:      D3  E3  F3
    (4, 5), (4, 7), (4, 9),       # D:      G3  A3  B3
    (3, 5), (3, 7),               # G:      C4★ D4
    (2, 5), (2, 6), (2, 8),       # B:      E4  F4  G4
    (1, 5), (1, 7), (1, 8),       # e:      A4  B4  C5★
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 4 — E shape (frets 8–12)  ✅ VERIFIED by Tyler — DO NOT EDIT  ║
# ║  low E: 8,10,12  A: 8,10,12  D: 9,10,12  G: 9,10  B: 8,10,12          ║
# ║  e: 8,10,12                                                             ║
# ║  Playback: starts on root C3★ (low E fret 8), ascends to C5★,          ║
# ║  descends to D3 — closed loop, no duplicate root at seam.              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: E6 fret 8 = C3★  |  D4 fret 10 = C4★  |  e1 fret 8 = C5★
_pos4_notes = _pos(
    (6, 8), (6, 10), (6, 12),     # low E:  C3★ D3  E3
    (5, 8), (5, 10), (5, 12),     # A:      F3  G3  A3
    (4, 9), (4, 10), (4, 12),     # D:      B3  C4★ D4
    (3, 9), (3, 10),              # G:      E4  F4
    (2, 8), (2, 10), (2, 12),     # B:      G4  A4  B4
    (1, 8), (1, 10), (1, 12),     # e:      C5★ D5  E5
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 5 — D shape (frets 8–14)  ✅ VERIFIED by Tyler — DO NOT EDIT  ║
# ║  low E: 8,10,12,13  A: 10,12,14  D: 10,12,14  G: 10,12,14              ║
# ║  B: 12,13  e: 10,12,13                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: E6 fret 8 = C3★  |  D4 fret 10 = C4★  |  B2 fret 13 = C5★
_pos5_notes = _pos(
    (6, 8), (6, 10), (6, 12), (6, 13),  # low E:  C3★ D3  E3  F3
    (5, 10), (5, 12), (5, 14),           # A:      G3  A3  B3
    (4, 10), (4, 12), (4, 14),           # D:      C4★ D4  E4
    (3, 10), (3, 12), (3, 14),           # G:      F4  G4  A4
    (2, 12), (2, 13),                    # B:      B4  C5★
    (1, 10), (1, 12), (1, 13),           # e:      D5  E5  F5
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 6 — C shape (15th fret)                                        ║
# ║  Same fingering as Position 1 shifted one octave up (+12 frets).         ║
# ║  low E: 12,13,15  A: 12,14,15  D: 12,14,15  G: 12,14                   ║
# ║  B: 12,13,15  e: 12,13,15                                               ║
# ║  Root C4★ = A string fret 15  |  Root C5★ = B string fret 13            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: A5 fret 15 = C4★  |  B2 fret 13 = C5★
_pos6_notes = _pos(
    (6, 12), (6, 13), (6, 15),    # low E:  E3  F3  G3
    (5, 12), (5, 14), (5, 15),    # A:      A3  B3  C4★
    (4, 12), (4, 14), (4, 15),    # D:      D4  E4  F4
    (3, 12), (3, 14),             # G:      G4  A4
    (2, 12), (2, 13), (2, 15),    # B:      B4  C5★ D5
    (1, 12), (1, 13), (1, 15),    # e:      E5  F5  G5
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 7 — A shape (15th fret)                                        ║
# ║  Same fingering as Position 2 shifted one octave up (+12 frets).         ║
# ║  low E: 15,17,19  A: 15,17,19  D: 15,17,19  G: 16,17                   ║
# ║  B: 15,17,18  e: 15,17,19,20                                            ║
# ║  Root C4★ = A string fret 15  |  Root C5★ = G string fret 17            ║
# ║  Root C6★ = e string fret 20                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: A5 fret 15 = C4★  |  G3 fret 17 = C5★  |  e1 fret 20 = C6★
_pos7_notes = _pos(
    (6, 15), (6, 17), (6, 19),         # low E:  G3  A3  B3
    (5, 15), (5, 17), (5, 19),         # A:      C4★ D4  E4
    (4, 15), (4, 17), (4, 19),         # D:      F4  G4  A4
    (3, 16), (3, 17),                  # G:      B4  C5★  (semitone shift at G–B break)
    (2, 15), (2, 17), (2, 18),         # B:      D5  E5  F5
    (1, 15), (1, 17), (1, 19), (1, 20),  # e:    G5  A5  B5  C6★
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Position 8 — G shape (20th fret)                                        ║
# ║  Same fingering as Position 3 shifted one octave up (+12 frets).         ║
# ║  low E: 20  A: 17,19,20  D: 17,19,21  G: 17,19                         ║
# ║  B: 17,18,20  e: 17,19,20                                               ║
# ║  Root C4★ = low E fret 20  |  Root C5★ = G string fret 17               ║
# ║  Root C6★ = e string fret 20                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Roots: E6 fret 20 = C4★  |  G3 fret 17 = C5★  |  e1 fret 20 = C6★
_pos8_notes = _pos(
    (6, 20),                       # low E:  C4★
    (5, 17), (5, 19), (5, 20),     # A:      D4  E4  F4
    (4, 17), (4, 19), (4, 21),     # D:      G4  A4  B4
    (3, 17), (3, 19),              # G:      C5★ D5
    (2, 17), (2, 18), (2, 20),     # B:      E5  F5  G5
    (1, 17), (1, 19), (1, 20),     # e:      A5  B5  C6★
)


# ---------------------------------------------------------------------------
# G major positions — G A B C D E F#  (midi pc: 7 9 11 0 2 4 6)
# Same CAGED shapes as C major, root G instead of root C.
# Derived by transposing verified C-major shapes; all pitch classes confirmed.
# String numbering: 1=high e (E4), 2=B3, 3=G3, 4=D3, 5=A2, 6=low E (E2)
# ---------------------------------------------------------------------------

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 1 — G shape (open, frets 0–3)                                    ║
# ║  low E: 3  A: 0,2,3  D: 0,2,4  G: 0,2  B: 0,1,3  e: 0,2,3            ║
# ║  Root G2★ = low E fret 3 | G3★ = G string open | G4★ = e fret 3        ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos1_notes = _pos(
    (6, 3),                       # low E:  G2★
    (5, 0), (5, 2), (5, 3),       # A:      A2  B2  C3
    (4, 0), (4, 2), (4, 4),       # D:      D3  E3  F#3
    (3, 0), (3, 2),               # G:      G3★ A3
    (2, 0), (2, 1), (2, 3),       # B:      B3  C4  D4
    (1, 0), (1, 2), (1, 3),       # e:      E4  F#4 G4★
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 2 — E shape (3rd fret)                                           ║
# ║  low E: 3,5,7  A: 3,5,7  D: 4,5,7  G: 4,5  B: 3,5,7  e: 3,5,7        ║
# ║  Root G2★ = low E fret 3 | G3★ = D fret 5 | G4★ = e fret 3            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos2_notes = _pos(
    (6, 3), (6, 5), (6, 7),       # low E:  G2★ A2  B2
    (5, 3), (5, 5), (5, 7),       # A:      C3  D3  E3
    (4, 4), (4, 5), (4, 7),       # D:      F#3 G3★ A3   (semitone shift at G-B break)
    (3, 4), (3, 5),               # G:      B3  C4
    (2, 3), (2, 5), (2, 7),       # B:      D4  E4  F#4
    (1, 3), (1, 5), (1, 7),       # e:      G4★ A4  B4
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 3 — D shape (5th fret)                                           ║
# ║  low E: 3,5,7,8  A: 5,7,9  D: 5,7,9  G: 5,7,9  B: 7,8  e: 5,7,8      ║
# ║  Root G2★ = low E fret 3 | G3★ = D fret 5 | G4★ = B fret 8            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos3_notes = _pos(
    (6, 3), (6, 5), (6, 7), (6, 8),  # low E:  G2★ A2  B2  C3
    (5, 5), (5, 7), (5, 9),           # A:      D3  E3  F#3
    (4, 5), (4, 7), (4, 9),           # D:      G3★ A3  B3
    (3, 5), (3, 7), (3, 9),           # G:      C4  D4  E4
    (2, 7), (2, 8),                   # B:      F#4 G4★
    (1, 5), (1, 7), (1, 8),           # e:      A4  B4  C5
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 4 — C shape (7th fret)                                           ║
# ║  low E: 7,8,10  A: 7,9,10  D: 7,9,10  G: 7,9  B: 7,8,10  e: 7,8,10   ║
# ║  Root G3★ = A fret 10 | G4★ = B fret 8                                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos4_notes = _pos(
    (6, 7), (6, 8), (6, 10),     # low E:  B2  C3  D3
    (5, 7), (5, 9), (5, 10),     # A:      E3  F#3 G3★
    (4, 7), (4, 9), (4, 10),     # D:      A3  B3  C4
    (3, 7), (3, 9),              # G:      D4  E4
    (2, 7), (2, 8), (2, 10),     # B:      F#4 G4★ A4
    (1, 7), (1, 8), (1, 10),     # e:      B4  C5  D5
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 5 — A shape (10th fret)                                          ║
# ║  low E: 10,12,14  A: 10,12,14  D: 10,12,14  G: 11,12  B: 10,12,13     ║
# ║  e: 10,12,14,15                                                         ║
# ║  Root G3★ = A fret 10 | G4★ = G fret 12 | G5★ = e fret 15             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos5_notes = _pos(
    (6, 10), (6, 12), (6, 14),          # low E:  D3  E3  F#3
    (5, 10), (5, 12), (5, 14),          # A:      G3★ A3  B3
    (4, 10), (4, 12), (4, 14),          # D:      C4  D4  E4
    (3, 11), (3, 12),                   # G:      F#4 G4★  (semitone shift at G-B break)
    (2, 10), (2, 12), (2, 13),          # B:      A4  B4  C5
    (1, 10), (1, 12), (1, 14), (1, 15), # e:      D5  E5  F#5 G5★
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 6 — G shape (15th fret, +12 from Pos 1)                          ║
# ║  low E: 15  A: 12,14,15  D: 12,14,16  G: 12,14  B: 12,13,15  e: 12,14,15 ║
# ║  Root G3★ = low E fret 15 | G4★ = G fret 12 | G5★ = e fret 15         ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos6_notes = _pos(
    (6, 15),                       # low E:  G3★
    (5, 12), (5, 14), (5, 15),    # A:      A3  B3  C4
    (4, 12), (4, 14), (4, 16),    # D:      E4  F#4 G4? — D3+12=D4(2), D3+14=E4(4), D3+16=F#4(6) ✓
    (3, 12), (3, 14),             # G:      G4★ A4
    (2, 12), (2, 13), (2, 15),    # B:      B4  C5  D5
    (1, 12), (1, 14), (1, 15),    # e:      E5  F#5 G5★
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 7 — E shape (15th fret, +12 from Pos 2)                          ║
# ║  low E: 15,17,19  A: 15,17,19  D: 16,17,19  G: 16,17  B: 15,17,19     ║
# ║  e: 15,17,19                                                            ║
# ║  Root G3★ = low E fret 15 | G4★ = D fret 17 | G5★ = e fret 15         ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos7_notes = _pos(
    (6, 15), (6, 17), (6, 19),    # low E:  G3★ A3  B3
    (5, 15), (5, 17), (5, 19),    # A:      C4  D4  E4
    (4, 16), (4, 17), (4, 19),    # D:      F#4 G4★ A4
    (3, 16), (3, 17),             # G:      B4  C5
    (2, 15), (2, 17), (2, 19),    # B:      D5  E5  F#5
    (1, 15), (1, 17), (1, 19),    # e:      G5★ A5  B5
)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  G Pos 8 — D shape (17th fret, +12 from Pos 3)                          ║
# ║  low E: 15,17,19,20  A: 17,19,21  D: 17,19,21  G: 17,19,21            ║
# ║  B: 19,20  e: 17,19,20                                                  ║
# ║  Root G3★ = low E fret 15 | G4★ = D fret 17 | G5★ = B fret 20         ║
# ╚══════════════════════════════════════════════════════════════════════════╝
_gpos8_notes = _pos(
    (6, 15), (6, 17), (6, 19), (6, 20),  # low E:  G3★ A3  B3  C4
    (5, 17), (5, 19), (5, 21),            # A:      D4  E4  F#4
    (4, 17), (4, 19), (4, 21),            # D:      G4★ A4  B4
    (3, 17), (3, 19), (3, 21),            # G:      C5  D5  E5
    (2, 19), (2, 20),                     # B:      F#5 G5★
    (1, 17), (1, 19), (1, 20),            # e:      A5  B5  C6
)


# ---------------------------------------------------------------------------
# SCALE_POSITIONS — multi-key dict (FR-20260522-guitar-trainer-multi-key)
# ---------------------------------------------------------------------------
SCALE_POSITIONS: dict[str, list[CagedPosition]] = {
    "C": [
        # original 8 C major positions (unchanged)
    CagedPosition(
        label="Position 1 — C shape (open)",
        root_string="A string",
        root_fret=3,
        instructor_phrase="Start on the 3rd fret of the A string — C major C shape.",
        notes=_pos1_notes,
    ),
    CagedPosition(
        label="Position 2 — A shape (3rd fret)",
        root_string="A string",
        root_fret=3,
        instructor_phrase="Start on the 3rd fret of the A string — C major A shape.",
        notes=_pos2_notes,
    ),
    CagedPosition(
        label="Position 3 — G shape (8th fret)",
        root_string="Low E string",
        root_fret=8,
        instructor_phrase="Start on the 8th fret of the low E string — C major G shape.",
        notes=_pos3_notes,
    ),
    CagedPosition(
        label="Position 4 — E shape (8th fret)",
        root_string="Low E string",
        root_fret=8,
        instructor_phrase="Start on the 8th fret of the low E string — C major E shape.",
        notes=_pos4_notes,
    ),
    CagedPosition(
        label="Position 5 — D shape (10th fret)",
        root_string="D string",
        root_fret=10,
        instructor_phrase="Start on the 8th fret of the E string — C major D shape.",
        notes=_pos5_notes,
    ),
    CagedPosition(
        label="Position 6 — C shape (15th fret)",
        root_string="A string",
        root_fret=15,
        instructor_phrase="Start on the 15th fret of the A string — C major C shape one octave up.",
        notes=_pos6_notes,
    ),
    CagedPosition(
        label="Position 7 — A shape (15th fret)",
        root_string="Low E string",
        root_fret=15,
        instructor_phrase="Start on the 15th fret of the low E string — C major A shape one octave up.",
        notes=_pos7_notes,
    ),
        CagedPosition(
            label="Position 8 — G shape (20th fret)",
            root_string="Low E string",
            root_fret=20,
            instructor_phrase="Start on the 20th fret of the low E string — C major G shape one octave up.",
            notes=_pos8_notes,
        ),
    ],
    "G": [
        CagedPosition(
            label="Position 1 — G shape (open)",
            root_string="Low E string",
            root_fret=3,
            instructor_phrase="Start on the 3rd fret of the low E string — G major G shape.",
            notes=_gpos1_notes,
        ),
        CagedPosition(
            label="Position 2 — E shape (3rd fret)",
            root_string="Low E string",
            root_fret=3,
            instructor_phrase="Start on the 3rd fret of the low E string — G major E shape.",
            notes=_gpos2_notes,
        ),
        CagedPosition(
            label="Position 3 — D shape (5th fret)",
            root_string="Low E string",
            root_fret=3,
            instructor_phrase="Start on the 3rd fret of the low E string — G major D shape.",
            notes=_gpos3_notes,
        ),
        CagedPosition(
            label="Position 4 — C shape (7th fret)",
            root_string="A string",
            root_fret=10,
            instructor_phrase="Start on the 10th fret of the A string — G major C shape.",
            notes=_gpos4_notes,
        ),
        CagedPosition(
            label="Position 5 — A shape (10th fret)",
            root_string="A string",
            root_fret=10,
            instructor_phrase="Start on the 10th fret of the A string — G major A shape.",
            notes=_gpos5_notes,
        ),
        CagedPosition(
            label="Position 6 — G shape (15th fret)",
            root_string="Low E string",
            root_fret=15,
            instructor_phrase="Start on the 15th fret of the low E string — G major G shape one octave up.",
            notes=_gpos6_notes,
        ),
        CagedPosition(
            label="Position 7 — E shape (15th fret)",
            root_string="Low E string",
            root_fret=15,
            instructor_phrase="Start on the 15th fret of the low E string — G major E shape one octave up.",
            notes=_gpos7_notes,
        ),
        CagedPosition(
            label="Position 8 — D shape (17th fret)",
            root_string="Low E string",
            root_fret=15,
            instructor_phrase="Start on the 15th fret of the low E string — G major D shape one octave up.",
            notes=_gpos8_notes,
        ),
    ],
}

# Backward-compat alias — C major positions
CAGED_POSITIONS: list[CagedPosition] = SCALE_POSITIONS["C"]


# ---------------------------------------------------------------------------
# MIDI → frequency (equal temperament)
# ---------------------------------------------------------------------------
MIDI_TO_FREQ: dict[int, float] = {
    midi: round(440.0 * math.pow(2.0, (midi - 69) / 12.0), 4)
    for midi in range(128)
}


def get_scale_sequence(position_idx: int, key: str = "C") -> list[int]:
    """Return ascending + descending MIDI note sequence for a scale position (0-indexed).

    Sequence: ascending from lowest to highest note, then descending back to lowest.
    ``key`` must be a key present in :data:`SCALE_POSITIONS` (e.g. ``'C'``, ``'G'``).
    """
    positions = SCALE_POSITIONS.get(key)
    if positions is None:
        raise ValueError(f"Unknown key {key!r}; available: {list(SCALE_POSITIONS)}")
    if not 0 <= position_idx < len(positions):
        raise ValueError(f"position_idx must be 0-{len(positions) - 1}, got {position_idx}")
    notes = positions[position_idx]["notes"]
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
