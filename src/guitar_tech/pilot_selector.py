"""Gap detector for HX Stomp presets (FR-20260705-guitar-tech-persona-agent).

Finds catalog_songs that do not yet have a dedicated .hlx preset in
HelixFiles/, using a token-based fuzzy match between (title, artist) and
existing preset filenames.

Matching heuristic (best-effort; results are always human-reviewable via
the guitar_tone_profiles.status='proposed' workflow downstream):
  - Tokenize both the song's title/artist and each filename (stem), splitting
    on underscores/spaces/punctuation and CamelCase boundaries, lowercasing,
    and dropping common stopwords + single-character tokens.
  - title_only_ratio = fraction of the song's TITLE tokens present in the
    filename. A ratio >= TITLE_ONLY_THRESHOLD is a confident match (handles
    the common case where the filename omits the artist entirely, e.g.
    "Change The World.hlx").
  - combined_ratio = fraction of the song's TITLE+ARTIST tokens present in
    the filename. A ratio >= COMBINED_THRESHOLD is a confident match
    (handles filenames that spell out both title and artist, e.g.
    "Rhiannon_Fleetwood_Mac.hlx").
  - A song is considered to already have a dedicated preset if EITHER ratio
    clears its threshold against ANY existing filename.

Known limitation: very short/generic titles (e.g. "Call Me") can produce a
false-positive match against an unrelated filename that happens to share
those words (e.g. a different artist's cover, "Call_Me_Shinedown.hlx" vs.
Blondie's "Call Me"). This is a best-effort heuristic for surfacing pilot
candidates, not a guarantee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

_STOPWORDS = {"a", "an", "the", "and", "of", "to", "in", "on", "for", "is", "at", "by"}

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")

TITLE_ONLY_THRESHOLD = 0.8
COMBINED_THRESHOLD = 0.6


def tokenize(text: str | None) -> set[str]:
    """Normalize text into a stopword-filtered token set for fuzzy matching."""
    if not text:
        return set()
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    spaced = _NON_ALNUM.sub(" ", spaced)
    words = [w.lower() for w in spaced.split() if len(w) > 1]
    return {w for w in words if w not in _STOPWORDS}


def _ratio(needle: set[str], haystack: set[str]) -> float:
    if not needle:
        return 0.0
    return len(needle & haystack) / len(needle)


def has_dedicated_preset(title: str, artist: str, existing_filenames: Iterable[str]) -> bool:
    """Return True if any existing filename appears to already cover this song."""
    title_tokens = tokenize(title)
    combined_tokens = title_tokens | tokenize(artist)
    for filename in existing_filenames:
        file_tokens = tokenize(Path(filename).stem)
        if _ratio(title_tokens, file_tokens) >= TITLE_ONLY_THRESHOLD:
            return True
        if _ratio(combined_tokens, file_tokens) >= COMBINED_THRESHOLD:
            return True
    return False


@dataclass(frozen=True)
class GapSong:
    """A catalog_songs row with no dedicated .hlx preset found."""

    id: int
    title: str
    artist: str
    key_sig: str | None
    bpm: int | None


def find_gap_songs(songs: Iterable[Mapping], existing_filenames: Iterable[str]) -> list[GapSong]:
    """Return catalog songs (as GapSong) with no dedicated preset match.

    `songs` is an iterable of mappings (dict or sqlite3.Row with
    row_factory=sqlite3.Row) exposing id/title/artist/key_sig/bpm keys.
    """
    existing = list(existing_filenames)
    gaps: list[GapSong] = []
    for song in songs:
        if has_dedicated_preset(song["title"], song["artist"], existing):
            continue
        gaps.append(
            GapSong(
                id=song["id"],
                title=song["title"],
                artist=song["artist"],
                key_sig=song["key_sig"],
                bpm=song["bpm"],
            )
        )
    return gaps
