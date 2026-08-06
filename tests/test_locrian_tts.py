"""
TTS instructor phrase integration tests for Locrian mode.

FR-20260801-locrian-mode-complete
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from training.mode_spec import build_mode_phrase  # noqa: E402
from training.scale_data import SCALE_POSITIONS    # noqa: E402


def test_locrian_phrase_names_mode() -> None:
    pos = SCALE_POSITIONS["C"][0]
    phrase = build_mode_phrase(pos, "Locrian", key="C", include_callout=False)
    assert "root of the Locrian scale" in phrase


def test_locrian_no_callout_without_flag() -> None:
    pos = SCALE_POSITIONS["C"][0]
    phrase = build_mode_phrase(pos, "Locrian", key="C", include_callout=False)
    assert "flattened fifth" not in phrase.lower()


def test_locrian_callout_on_mode_switch() -> None:
    pos = SCALE_POSITIONS["C"][0]
    phrase = build_mode_phrase(pos, "Locrian", key="C", include_callout=True)
    assert "root of the Locrian scale" in phrase
    assert "flattened fifth" in phrase.lower()
    assert "flattened second" in phrase.lower()


def test_locrian_phrase_different_key() -> None:
    pos = SCALE_POSITIONS["G"][0]
    phrase = build_mode_phrase(pos, "Locrian", key="G", include_callout=False)
    assert "root of the Locrian scale" in phrase
