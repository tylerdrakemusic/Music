"""Persona-matching rubric for the ❤Music guitar-tech tone generator.

Scores a catalog song's key_sig + bpm + artist against 8 guitar legends and
returns a `PersonaMatch` describing which legend(s) best fit the song's tone
character, plus a plain-English rationale.

Legends: Stevie Ray Vaughan, Jimi Hendrix, Prince, B.B. King, Albert King,
John Mayer, John Frusciante, Eddie Van Halen.

Rule order (first match wins):
  1. Artist hint  — direct artist -> persona association for iconic cases
                    where numeric key/bpm rules alone would miss the intent
                    (e.g. Santana's blues-rock fusion style maps to Hendrix).
  2. Slow Blues   — minor key AND bpm < 100 -> blues legends trio
                    (Stevie Ray Vaughan, Albert King, B.B. King).
  3. Funk         — minor key AND 100 <= bpm <= 112 -> funk duo
                    (Prince, John Frusciante).
  4. Hard Rock    — bpm >= 130 -> Eddie Van Halen.
  5. Default      — everything else -> John Mayer (smooth, versatile
                    blues-pop-rock lead persona; sensible catch-all).

Caveat: genre/tags are unpopulated across catalog_songs today, so this
rubric intentionally scores only on key_sig + bpm + artist, per the FR's
stated inputs. If genre/tags are populated later, this module is the place
to add a genre-aware rule ahead of the numeric bands.
"""
from __future__ import annotations

from dataclasses import dataclass

SRV = "Stevie Ray Vaughan"
HENDRIX = "Jimi Hendrix"
PRINCE = "Prince"
BB_KING = "B.B. King"
ALBERT_KING = "Albert King"
MAYER = "John Mayer"
FRUSCIANTE = "John Frusciante"
EVH = "Eddie Van Halen"

LEGENDS = [SRV, HENDRIX, PRINCE, BB_KING, ALBERT_KING, MAYER, FRUSCIANTE, EVH]

# Direct artist -> persona hints for iconic style associations that the
# numeric key/bpm rules alone would not capture. Matched as a case-insensitive
# substring against the song's artist field.
ARTIST_STYLE_HINTS: dict[str, tuple[list[str], str]] = {
    "santana": (
        [HENDRIX],
        "Santana's psychedelic blues-rock fusion style maps directly to Jimi Hendrix.",
    ),
}


@dataclass(frozen=True)
class PersonaMatch:
    """Result of scoring a song against the guitar-legend rubric."""

    personas: list[str]
    rationale: str

    @property
    def label(self) -> str:
        """Human-readable '+'-joined persona blend, e.g. 'Prince + John Frusciante'."""
        return " + ".join(self.personas)


def is_minor_key(key_sig: str | None) -> bool:
    """Return True if key_sig denotes a minor key (e.g. 'Am', 'F#m', 'Bbm')."""
    return bool(key_sig) and key_sig.strip().endswith("m")


def score_persona(*, artist: str, key_sig: str | None, bpm: int | None) -> PersonaMatch:
    """Score a song's artist/key/bpm against the 8 guitar legends.

    Args:
        artist: Catalog artist name (e.g. "Joe Cocker").
        key_sig: Catalog key signature (e.g. "Bbm"), or None if unknown.
        bpm: Catalog tempo in beats per minute, or None if unknown.

    Returns:
        A PersonaMatch with one or more blended persona names and a rationale.
    """
    artist_key = (artist or "").strip().lower()
    for hint_key, (personas, rationale) in ARTIST_STYLE_HINTS.items():
        if hint_key in artist_key:
            return PersonaMatch(list(personas), rationale)

    minor = is_minor_key(key_sig)
    bpm_val = bpm or 0

    if minor and bpm_val and bpm_val < 100:
        return PersonaMatch(
            [SRV, ALBERT_KING, BB_KING],
            f"Minor key ({key_sig}) at a slow {bpm_val} BPM reads as a slow blues "
            "ballad — blending the phrasing of Stevie Ray Vaughan, Albert King, "
            "and B.B. King.",
        )
    if minor and bpm_val and 100 <= bpm_val <= 112:
        return PersonaMatch(
            [PRINCE, FRUSCIANTE],
            f"Minor key ({key_sig}) at a mid-tempo groove ({bpm_val} BPM) reads as "
            "funk — blending Prince's rhythmic snap with John Frusciante's "
            "melodic funk voicings.",
        )
    if bpm_val and bpm_val >= 130:
        return PersonaMatch(
            [EVH],
            f"Uptempo drive ({bpm_val} BPM) calls for Eddie Van Halen's aggressive "
            "hard-rock lead voice.",
        )
    return PersonaMatch(
        [MAYER],
        "No stronger stylistic signal from key/tempo/artist — John Mayer's smooth, "
        "versatile blues-pop-rock voice is the sensible default persona.",
    )
