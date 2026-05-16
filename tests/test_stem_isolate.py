"""Unit tests for stem_isolate.detect_instrument.

FR-20260516-suno-stem-isolation

Tests instrument detection logic only — no Demucs invocation required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable even when running pytest from the repo root.
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from stem_isolate import detect_instrument  # noqa: E402


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("0 Drums.wav", "drums"),
        ("9 Bass.wav", "bass"),
        ("1 Rhythm Guitar.wav", "guitar"),
        ("3 Lead Guitar.wav", "guitar"),
        ("4 Bridge Vox.wav", "vocals"),
        ("7 Lead Vox.wav", "vocals"),
        ("8 Backing Vox.wav", "vocals"),
    ],
)
def test_detect_known_instruments(filename: str, expected: str) -> None:
    assert detect_instrument(filename) == expected


def test_detect_unknown_returns_none() -> None:
    assert detect_instrument("unknown_instrument.wav") is None


def test_numeric_prefix_drums() -> None:
    """Numeric prefix '0' always maps to drums regardless of name."""
    assert detect_instrument("0 SomeName.wav") == "drums"


def test_numeric_prefix_bass() -> None:
    """Numeric prefix '9' always maps to bass regardless of name."""
    assert detect_instrument("9 SomeName.wav") == "bass"


def test_vocal_keyword() -> None:
    assert detect_instrument("Lead Vocal.wav") == "vocals"


def test_vocals_keyword() -> None:
    assert detect_instrument("Main Vocals.wav") == "vocals"


def test_case_insensitive() -> None:
    assert detect_instrument("RHYTHM GUITAR.wav") == "guitar"
    assert detect_instrument("BASS LINE.wav") == "bass"
