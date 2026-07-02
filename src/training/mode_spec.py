"""
❤Music — Guitar trainer mode specification (single source of truth).

FR-20260629-guitar-trainer-lydian-mode

Consolidates the previously-scattered per-mode logic (fretboard coloring,
staff coloring, legend, TTS instructor phrase, audio accent) into one
data-driven table. The Flask view injects MODE_SPEC + the palette into the
page as JSON so the browser renders from the same data Python tests assert on,
eliminating the old duplicated `buildModePhrase` (Python + JS) drift.

Public API:
    MODE_SPEC      : dict[str, dict]   — per-mode spec (offset, intervals, degrees, …)
    DEGREE_COLORS  : dict[str, str]    — degree type → fill hex
    DEGREE_TEXT    : dict[str, str]    — degree type → label text color
    DEGREE_STROKE  : dict[str, str]    — degree type → stroke color
    legend_items(mode)                 — [(color, label), …] for the legend
    build_mode_phrase(pos, mode, key, include_callout=False) -> str
"""
from __future__ import annotations

import re
from typing import Optional, TypedDict


# ---------------------------------------------------------------------------
# Palette — degree type → colors. Mirrors the legacy DOT_FILL/DOT_TEXT/DOT_STROKE
# tables, plus the new dedicated `sharp_fourth` type for the Lydian raised 4th.
# ---------------------------------------------------------------------------
DEGREE_COLORS: dict[str, str] = {
    "root": "#ff0080",
    "minor_second": "#8338ec",
    "third": "#fb5607",
    "minor_third": "#fb5607",
    "sharp_fourth": "#b15dff",   # NEW — Lydian ♯4 (bright violet, distinct)
    "fifth": "#00e5cc",
    "major_sixth": "#ffd166",
    "leading": "#00b4d8",
    "other": "#555555",
}
DEGREE_TEXT: dict[str, str] = {
    "root": "#ffffff",
    "minor_second": "#ffffff",
    "third": "#ffffff",
    "minor_third": "#ffffff",
    "sharp_fourth": "#ffffff",
    "fifth": "#000000",
    "major_sixth": "#000000",
    "leading": "#ffffff",
    "other": "#ffffff",
}
DEGREE_STROKE: dict[str, str] = {
    "root": "#000000",
    "minor_second": "#000000",
    "third": "#000000",
    "minor_third": "#000000",
    "sharp_fourth": "#000000",
    "fifth": "#000000",
    "major_sixth": "#000000",
    "leading": "#000000",
    "other": "#333333",
}


class Characteristic(TypedDict):
    interval: int
    name: str
    callout: str


class ModeSpec(TypedDict):
    root_offset: int
    intervals: tuple[int, ...]
    tts_label: str
    degrees: dict[int, dict[str, str]]
    accents: tuple[int, ...]
    characteristic: Optional[Characteristic]


def _deg(type_: str, label: str) -> dict[str, str]:
    return {"type": type_, "label": label}


# ---------------------------------------------------------------------------
# MODE_SPEC — one row per mode. `degrees` maps an interval (semitones above the
# mode tonic) to its colored degree type + legend label. Intervals not listed
# render as the neutral `other` color. `accents` lists intervals that get the
# triangle timbre during scale playback.
# ---------------------------------------------------------------------------
MODE_SPEC: dict[str, ModeSpec] = {
    "Ionian": {
        "root_offset": 0,
        "intervals": (0, 2, 4, 5, 7, 9, 11, 12),
        "tts_label": "Ionian",
        "degrees": {0: _deg("root", "Root"), 4: _deg("third", "3rd"), 7: _deg("fifth", "5th")},
        "accents": (),
        "characteristic": None,
    },
    "Dorian": {
        "root_offset": 2,
        "intervals": (0, 2, 3, 5, 7, 9, 10, 12),
        "tts_label": "Dorian",
        "degrees": {
            0: _deg("root", "Root"),
            3: _deg("minor_third", "♭3"),
            7: _deg("fifth", "5th"),
            9: _deg("major_sixth", "6th"),
        },
        "accents": (0, 3, 9),
        "characteristic": None,
    },
    "Phrygian": {
        "root_offset": 4,
        "intervals": (0, 1, 3, 5, 7, 8, 10, 12),
        "tts_label": "Phrygian",
        "degrees": {
            0: _deg("root", "Root"),
            1: _deg("minor_second", "♭2"),
            3: _deg("minor_third", "♭3"),
            7: _deg("fifth", "5th"),
        },
        "accents": (0, 1, 3),
        "characteristic": None,
    },
    "Lydian": {
        "root_offset": 5,
        "intervals": (0, 2, 4, 6, 7, 9, 11, 12),
        "tts_label": "Lydian",
        "degrees": {
            0: _deg("root", "Root"),
            4: _deg("third", "3rd"),
            6: _deg("sharp_fourth", "♯4"),
            7: _deg("fifth", "5th"),
        },
        "accents": (0, 6),
        "characteristic": {
            "interval": 6,
            "name": "raised fourth",
            "callout": "listen for the raised fourth, the Lydian sound",
        },
    },
    "Mixolydian": {
        "root_offset": 7,
        "intervals": (0, 2, 4, 5, 7, 9, 10, 12),
        "tts_label": "Mixolydian",
        "degrees": {0: _deg("root", "Root"), 4: _deg("third", "3rd"), 7: _deg("fifth", "5th")},
        "accents": (),
        "characteristic": None,
    },
    "Aeolian": {
        "root_offset": 9,
        "intervals": (0, 2, 3, 5, 7, 8, 10, 12),
        "tts_label": "Aeolian",
        "degrees": {
            0: _deg("root", "Root"),
            3: _deg("minor_third", "♭3"),
            7: _deg("fifth", "5th"),
            10: _deg("leading", "♭7"),
        },
        "accents": (),
        "characteristic": None,
    },
    "Locrian": {
        "root_offset": 11,
        "intervals": (0, 1, 3, 5, 6, 8, 10, 12),
        "tts_label": "Locrian",
        "degrees": {0: _deg("root", "Root"), 4: _deg("third", "3rd"), 7: _deg("fifth", "5th")},
        "accents": (),
        "characteristic": None,
    },
}


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------
def legend_items(mode: str) -> list[tuple[str, str]]:
    """Return [(color_hex, label), …] for the given mode's colored degrees."""
    spec = MODE_SPEC.get(mode) or MODE_SPEC["Ionian"]
    items: list[tuple[str, str]] = []
    for interval in sorted(spec["degrees"]):
        deg = spec["degrees"][interval]
        items.append((DEGREE_COLORS[deg["type"]], deg["label"]))
    return items


# ---------------------------------------------------------------------------
# TTS instructor phrase (consolidated — replaces the duplicated buildModePhrase)
# ---------------------------------------------------------------------------
_KEY_PC: dict[str, int] = {
    "C": 0, "Db": 1, "C#": 1, "D": 2, "Eb": 3, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "Ab": 8, "G#": 8, "A": 9, "Bb": 10, "A#": 10, "B": 11,
}
_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb"}
_STRING_NAMES = {1: "high e", 2: "B", 3: "G", 4: "D", 5: "A", 6: "low E"}


def mode_root_pitch_class(key: str, mode: str) -> int:
    """Pitch class (0-11) of the mode tonic for the given parent key."""
    spec = MODE_SPEC.get(mode) or MODE_SPEC["Ionian"]
    return (_KEY_PC.get(key, 0) + spec["root_offset"]) % 12


def _spoken_note_name(pc: int, key: str) -> str:
    raw = _FLAT_NAMES[pc] if key in _FLAT_KEYS else _SHARP_NAMES[pc]
    name = re.sub(r"^([A-G])#$", r"\1 sharp", raw)
    name = re.sub(r"^([A-G])b$", r"\1 flat", name)
    return name


def build_mode_phrase(
    pos: dict,
    mode: str,
    key: str = "C",
    include_callout: bool = False,
) -> str:
    """Build the spoken instructor phrase for a mode/position.

    When *include_callout* is True and the mode defines a characteristic tone
    (e.g. the Lydian ♯4), a short reminder is appended. The caller passes
    include_callout=True only on a mode switch, so it isn't a nagging reminder
    on every position change.
    """
    spec = MODE_SPEC.get(mode) or MODE_SPEC["Ionian"]
    root_pc = mode_root_pitch_class(key, mode)
    tonic_name = _spoken_note_name(root_pc, key)

    # Shape name from the position label (strip "Position N — ", trailing "(...)" / "shape").
    shape_name = pos.get("label", "")
    shape_name = re.sub(r"^Position \d+ — ", "", shape_name)
    shape_name = re.sub(r"\s*\([^)]*\)$", "", shape_name)
    shape_name = re.sub(r"\s*shape\s*$", "", shape_name, flags=re.IGNORECASE).strip()
    shape_name = re.sub(r"([A-G])#", r"\1 sharp", shape_name)
    shape_name = re.sub(r"([A-G])b", r"\1 flat", shape_name)

    # Locate the lowest tonic note in this position for the spoken location.
    tonic = None
    for note in pos.get("notes", []):
        if note.get("midi", -1) % 12 == root_pc:
            if tonic is None or note.get("midi", 0) < tonic.get("midi", 0):
                tonic = note
    tonic_location = ""
    if tonic is not None:
        string_name = _STRING_NAMES.get(tonic.get("string", 0), "unknown")
        if tonic.get("fret", 0) == 0:
            tonic_location = f"on the open {string_name} string"
        else:
            tonic_location = f"on the {string_name} string at fret {tonic.get('fret', 0)}"

    root_label = "tonic root" if mode == "Ionian" else f"root of the {spec['tts_label']} scale"
    phrase = f"Start on the {root_label} {tonic_name}"
    if tonic_location:
        phrase += f", {tonic_location}"
    if shape_name:
        phrase += f" and go up and down the {shape_name} shape."

    if include_callout and spec["characteristic"]:
        phrase += f" — {spec['characteristic']['callout']}."

    return phrase.strip()
