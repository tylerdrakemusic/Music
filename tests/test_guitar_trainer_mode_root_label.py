"""
Tests for FR-20260806-guitar-trainer-mode-root-label.

Validates mode_root_note(key, mode) -> str, the Python source of truth for
the mode dropdown label (mirrored by JS populateModeSelect).

Coverage:
  - All 7 modes produce the correct root note for key of C
  - Flat keys return flat spellings (D♭, E♭, G♭, A♭, B♭)
  - Sharp key (F#) uses sharp spellings
  - Ionian root always equals the key root
  - Aeolian root is 9 semitones above key root (natural minor)
  - All 84 permutations (12 keys × 7 modes) return a non-empty string
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from training.mode_spec import mode_root_note  # noqa: E402


# ---------------------------------------------------------------------------
# Key of C — all 7 modes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,expected", [
    ("Ionian",      "C"),
    ("Dorian",      "D"),
    ("Phrygian",    "E"),
    ("Lydian",      "F"),
    ("Mixolydian",  "G"),
    ("Aeolian",     "A"),
    ("Locrian",     "B"),
])
def test_mode_root_c_major(mode: str, expected: str) -> None:
    assert mode_root_note("C", mode) == expected


# ---------------------------------------------------------------------------
# Flat keys — roots should use flat spellings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,mode,expected", [
    ("F",  "Dorian",    "G"),       # G is natural — no flat needed
    ("Bb", "Dorian",    "C"),       # C is natural
    ("Bb", "Phrygian",  "D"),        # Bb+4 semitones = D (natural)
    ("Eb", "Dorian",    "F"),
    ("Eb", "Mixolydian","B♭"),      # B♭, not A♯
    ("Ab", "Dorian",    "B♭"),      # B♭
    ("Ab", "Phrygian",  "C"),        # Ab+4 semitones = C (natural, no flat needed)
    ("Db", "Dorian",    "E♭"),      # E♭
    ("Gb", "Dorian",    "A♭"),      # A♭
])
def test_mode_root_flat_keys(key: str, mode: str, expected: str) -> None:
    assert mode_root_note(key, mode) == expected


# ---------------------------------------------------------------------------
# Sharp key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,expected", [
    ("Ionian",     "F♯"),
    ("Dorian",     "G♯"),
    ("Phrygian",   "A♯"),
    ("Lydian",     "B"),
    ("Mixolydian", "C♯"),
    ("Aeolian",    "D♯"),
    ("Locrian",    "F"),   # E♯ enharmonic = F (natural)
])
def test_mode_root_f_sharp(mode: str, expected: str) -> None:
    assert mode_root_note("F#", mode) == expected


# ---------------------------------------------------------------------------
# Ionian always equals key root
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,expected", [
    ("C", "C"), ("Db", "D♭"), ("D", "D"), ("Eb", "E♭"),
    ("E", "E"), ("F", "F"), ("F#", "F♯"), ("G", "G"),
    ("Ab", "A♭"), ("A", "A"), ("Bb", "B♭"), ("B", "B"),
])
def test_ionian_root_equals_key(key: str, expected: str) -> None:
    assert mode_root_note(key, "Ionian") == expected


# ---------------------------------------------------------------------------
# Aeolian root is natural minor (9 semitones above key root) — spot checks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,expected", [
    ("C",  "A"),
    ("G",  "E"),
    ("D",  "B"),
    ("F",  "D"),
    ("Bb", "G"),
])
def test_aeolian_root_is_natural_minor(key: str, expected: str) -> None:
    assert mode_root_note(key, "Aeolian") == expected


# ---------------------------------------------------------------------------
# All 84 permutations return a non-empty string
# ---------------------------------------------------------------------------

ALL_KEYS  = ["C","Db","D","Eb","E","F","F#","G","Ab","A","Bb","B"]
ALL_MODES = ["Ionian","Dorian","Phrygian","Lydian","Mixolydian","Aeolian","Locrian"]

@pytest.mark.parametrize("key", ALL_KEYS)
@pytest.mark.parametrize("mode", ALL_MODES)
def test_all_permutations_return_nonempty(key: str, mode: str) -> None:
    result = mode_root_note(key, mode)
    assert isinstance(result, str) and result.strip()
