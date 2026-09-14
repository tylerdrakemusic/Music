"""
Tests for FR-20260913-music-a-major-key-signature.

Covers:
  - KEY_SIGS JS map includes A major's literal key signature (3 sharps)
  - A major is not misclassified as a flat key (would pick wrong note spellings)
  - Existing key-signature entries are unchanged (regression)

The staff renderer (drawSingleStaff) uses the same KEY_SIGS entry to draw
both the treble and bass clef signatures (sign of the count selects the
sharp/flat Y-position tables for either clef), so asserting the map entry
is correct covers both clefs.
"""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAINER_PY = PROJECT_ROOT / "src" / "training" / "musician_training_ui.py"

# Expected accidental counts (positive = sharps, negative = flats) for every
# key the trainer already supported, plus A (this FR's fix).
EXPECTED_KEY_SIGS = {
    "C": 0, "Db": -5, "D": 2, "Eb": -3, "E": 4, "F": -1, "F#": 6, "G": 1,
    "A": 3, "Ab": -4, "Bb": -2, "B": 5, "A#": -2, "D#": -3,
}


def _trainer_src() -> str:
    return TRAINER_PY.read_text(encoding="utf-8")


def _parse_key_sigs(src: str) -> dict:
    match = re.search(r"const KEY_SIGS = \{([^}]*)\};", src)
    assert match, "KEY_SIGS map not found in musician_training_ui.py"
    body = match.group(1)
    entries = {}
    for quoted_key, bare_key, value in re.findall(r"(?:'([^']+)'|(\w+))\s*:\s*(-?\d+)", body):
        entries[quoted_key or bare_key] = int(value)
    return entries


def test_a_major_has_three_sharps() -> None:
    """A major must use its literal key signature: F#, C#, G# (3 sharps)."""
    key_sigs = _parse_key_sigs(_trainer_src())
    assert key_sigs.get("A") == 3, "A major must map to +3 (three sharps)"


def test_a_is_not_a_flat_key() -> None:
    """A major must not be classified as a flat key (wrong note spellings)."""
    src = _trainer_src()
    match = re.search(r"const FLAT_KEYS\s*=\s*new Set\(\[([^\]]*)\]\)", src)
    assert match, "FLAT_KEYS set not found in musician_training_ui.py"
    flat_keys = {k.strip().strip("'\"") for k in match.group(1).split(",")}
    assert "A" not in flat_keys


def test_key_sigs_matches_expected_full_map() -> None:
    """Regression: every previously-supported key keeps its accidental count."""
    key_sigs = _parse_key_sigs(_trainer_src())
    assert key_sigs == EXPECTED_KEY_SIGS
