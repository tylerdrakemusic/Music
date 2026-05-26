"""
seed_scale_data.py — One-time migration: populate guitar scale tables in heartmusic.db.

FR-20260524-scale-data-sqlite-migration

Run from f:\\❤Music:
    $env:PYTHONUTF8="1"; C:\\G\\python.exe tools/seed_scale_data.py

Idempotent — uses INSERT OR IGNORE throughout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make src/ importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.init_db import get_connection, init_db  # noqa: E402

# ---------------------------------------------------------------------------
# Template definitions
# Each entry: shape_name → (root_string_int, [[string, fret_delta], ...])
# root_string_int: the guitar string (1=high-e, 6=low-E) used as the root anchor.
# fret_delta: added to the stored root_fret to produce each note's fret number.
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
    "D_shape_open": (4, [
        [5,  0], [5,  2], [5,  4],
        [4,  0], [4,  2], [4,  4],
        [3,  0], [3,  2], [3,  4],
        [2,  2], [2,  3],
        [1,  0], [1,  2], [1,  3],
    ]),
}

# ---------------------------------------------------------------------------
# Position definitions
# Each row: (shape_name, root_fret, label, root_string_name, instructor_phrase)
# ---------------------------------------------------------------------------
_POSITIONS: dict[str, list[tuple[str, int, str, str, str]]] = {
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
        ("G_shape", 3,  "Position 1 — G shape (open)",             "Low E string", "Start on the 3rd fret of the low E string — G major G shape."),
        ("river",   3,  "Position 2 — 川 River shape (3rd fret)",  "Low E string", "Start on the 3rd fret of the low E string — G major 川 River shape."),
        ("E_shape", 3,  "Position 3 — E shape (3rd fret)",         "Low E string", "Start on the 3rd fret of the low E string — G major E shape."),
        ("D_shape", 3,  "Position 4 — D shape (5th fret)",         "Low E string", "Start on the 3rd fret of the low E string — G major D shape."),
        ("C_shape", 10, "Position 5 — C shape (7th fret)",         "A string",     "Start on the 10th fret of the A string — G major C shape."),
        ("rock",    10, "Position 6 — 石 Rock shape (8th fret)",   "A string",     "Start on the 10th fret of the A string for G major 石 Rock shape."),
        ("A_shape", 10, "Position 7 — A shape (10th fret)",        "A string",     "Start on the 10th fret of the A string — G major A shape."),
        ("G_shape", 15, "Position 8 — G shape (15th fret)",        "Low E string", "Start on the 15th fret of the low E string — G major G shape one octave up."),
        ("river",   15, "Position 9 — 川 River shape (15th fret)", "Low E string", "Start on the 15th fret of the low E string — G major 川 River shape (high octave)."),
        ("E_shape", 15, "Position 10 — E shape (15th fret)",       "Low E string", "Start on the 15th fret of the low E string — G major E shape (high octave)."),
        ("D_shape", 15, "Position 11 — D shape (17th fret)",       "Low E string", "Start on the 15th fret of the low E string — G major D shape one octave up."),
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
    "Bb": [
        ("A_shape", 1,  "Position 1 — A shape (1st fret)",           "A string",     "Start on the 1st fret of the A string — Ay-Sharp major A shape."),
        ("G_shape", 6,  "Position 2 — G shape (6th fret)",           "Low E string", "Start on the 6th fret of the low E string — Ay-Sharp major G shape."),
        ("river",   6,  "Position 3 — 川 River shape (6th fret)",    "Low E string", "Start on the 6th fret of the low E string — Ay-Sharp major 川 River shape."),
        ("E_shape", 6,  "Position 4 — E shape (6th fret)",           "Low E string", "Start on the 6th fret of the low E string — Ay-Sharp major E shape."),
        ("D_shape", 6,  "Position 5 — D shape (6th fret)",           "Low E string", "Start on the 6th fret of the low E string — Ay-Sharp major D shape."),
        ("C_shape", 13, "Position 6 — C shape (13th fret)",          "A string",     "Start on the 13th fret of the A string — Ay-Sharp major C shape."),
        ("rock",    13, "Position 7 — 石 Rock shape (13th fret)",    "A string",     "Start on the 13th fret of the A string for Ay-Sharp major 石 Rock shape."),
        ("A_shape", 13, "Position 8 — A shape (13th fret)",          "A string",     "Start on the 13th fret of the A string — Ay-Sharp major A shape one octave up."),
        ("G_shape", 18, "Position 9 — G shape (18th fret)",          "Low E string", "Start on the 18th fret of the low E string — Ay-Sharp major G shape one octave up."),
        ("river",   18, "Position 10 — 川 River shape (18th fret)",  "Low E string", "Start on the 18th fret of the low E string — Ay-Sharp major 川 River shape (high octave)."),
        ("E_shape", 18, "Position 11 — E shape (18th fret)",         "Low E string", "Start on the 18th fret of the low E string — Ay-Sharp major E shape (high octave)."),
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
        ("D_shape_open", 1,  "Position 1 — D shape (1st fret)",          "D string",     "Start on the 1st fret of the D string — D-Sharp major D shape."),
        ("C_shape",      6,  "Position 2 — C shape (6th fret)",          "A string",     "Start on the 6th fret of the A string — D-Sharp major C shape."),
        ("rock",         6,  "Position 3 — 石 Rock shape (6th fret)",    "A string",     "Start on the 6th fret of the A string for D-Sharp major 石 Rock shape."),
        ("A_shape",      6,  "Position 4 — A shape (6th fret)",          "A string",     "Start on the 6th fret of the A string — D-Sharp major A shape."),
        ("G_shape",      11, "Position 5 — G shape (11th fret)",         "Low E string", "Start on the 11th fret of the low E string — D-Sharp major G shape."),
        ("river",        11, "Position 6 — 川 River shape (11th fret)",  "Low E string", "Start on the 11th fret of the low E string — D-Sharp major 川 River shape."),
        ("E_shape",      11, "Position 7 — E shape (11th fret)",         "Low E string", "Start on the 11th fret of the low E string — D-Sharp major E shape."),
        ("D_shape",      11, "Position 8 — D shape (11th fret)",         "Low E string", "Start on the 11th fret of the low E string — D-Sharp major D shape."),
        ("C_shape",      18, "Position 9 — C shape (18th fret)",         "A string",     "Start on the 18th fret of the A string — D-Sharp major C shape one octave up."),
        ("rock",         18, "Position 10 — 石 Rock shape (18th fret)",  "A string",     "Start on the 18th fret of the A string for D-Sharp major 石 Rock shape (high octave)."),
    ],
}

# Expected pitch-class sets for quick verification
_PITCH_CLASSES: dict[str, set[int]] = {
    "C":  {0, 2, 4, 5, 7, 9, 11},   # C D E F G A B
    "G":  {7, 9, 11, 0, 2, 4, 6},   # G A B C D E F#
    "F":  {5, 7, 9, 10, 0, 2, 4},   # F G A Bb C D E
    "D":  {2, 4, 6, 7, 9, 11, 1},   # D E F# G A B C#
    "Bb": {10, 0, 2, 3, 5, 7, 9},   # Bb C D Eb F G A
    "B":  {11, 1, 3, 4, 6, 8, 10},  # B C# D# E F# G# A#
    "Eb": {3, 5, 7, 8, 10, 0, 2},   # Eb F G Ab Bb C D
}

_OPEN_MIDI: dict[int, int] = {
    1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40,
}


def _verify_positions(key_name: str) -> None:
    """Verify that every generated note for key_name has the correct pitch class."""
    expected_pc = _PITCH_CLASSES[key_name]
    positions = _POSITIONS[key_name]
    for order, (shape_name, root_fret, label, _, _) in enumerate(positions):
        _, offsets = _TEMPLATES[shape_name]
        for s, delta in offsets:
            fret = root_fret + delta
            midi = _OPEN_MIDI[s] + fret
            pc = midi % 12
            if pc not in expected_pc:
                raise AssertionError(
                    f"Key={key_name} pos={order+1} ({label}): "
                    f"string={s} fret={fret} midi={midi} pc={pc} "
                    f"not in {expected_pc}"
                )


def seed(conn) -> None:
    """Insert templates and positions idempotently."""
    # Ensure schema exists (run against live DB)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS guitar_scale_templates (
            shape_name   TEXT NOT NULL PRIMARY KEY,
            root_string  INTEGER NOT NULL,
            note_offsets TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS guitar_scale_positions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name          TEXT    NOT NULL,
            position_order    INTEGER NOT NULL,
            shape_name        TEXT    NOT NULL REFERENCES guitar_scale_templates(shape_name),
            label             TEXT    NOT NULL,
            root_string_name  TEXT    NOT NULL,
            root_fret         INTEGER NOT NULL,
            instructor_phrase TEXT    NOT NULL,
            UNIQUE (key_name, position_order)
        );
        """
    )

    # Seed templates
    for shape_name, (root_string, offsets) in _TEMPLATES.items():
        conn.execute(
            "INSERT OR IGNORE INTO guitar_scale_templates "
            "(shape_name, root_string, note_offsets) VALUES (?, ?, ?)",
            (shape_name, root_string, json.dumps(offsets)),
        )

    # Seed positions
    for key_name, positions in _POSITIONS.items():
        for order, (shape_name, root_fret, label, rsn, phrase) in enumerate(positions):
            conn.execute(
                "INSERT OR IGNORE INTO guitar_scale_positions "
                "(key_name, position_order, shape_name, label, root_string_name, "
                "root_fret, instructor_phrase) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key_name, order, shape_name, label, rsn, root_fret, phrase),
            )

    conn.commit()


def main() -> None:
    print("Verifying template integrity before seeding …")
    for key_name in _POSITIONS:
        _verify_positions(key_name)
        print(f"  {key_name}: {len(_POSITIONS[key_name])} positions — pitch-class OK")

    print("\nOpening heartmusic.db …")
    # Ensure schema tables exist
    init_db(seed=False)
    conn = get_connection()

    try:
        seed(conn)
    finally:
        conn.close()

    # Verification: read back from DB
    conn2 = get_connection()
    try:
        tmpl_count = conn2.execute(
            "SELECT COUNT(*) FROM guitar_scale_templates"
        ).fetchone()[0]
        pos_count = conn2.execute(
            "SELECT COUNT(*) FROM guitar_scale_positions"
        ).fetchone()[0]
        per_key = conn2.execute(
            "SELECT key_name, COUNT(*) FROM guitar_scale_positions GROUP BY key_name"
        ).fetchall()
    finally:
        conn2.close()

    print(f"\nSeeded {tmpl_count} templates, {pos_count} positions total.")
    for row in per_key:
        print(f"  {row[0]}: {row[1]} positions")

    print("\nDone. heartmusic.db is ready for scale_data.py.")


if __name__ == "__main__":
    main()
