"""Pure phonetic suffix-matching utilities for the ❤Music Rhyme Grouper.

No quantum_rt dependency — safe for standalone web/CLI use.
Extracted from tools/group_rhymes.py (phonetic logic only).
"""

from __future__ import annotations

from typing import Optional


def build_suffix_map(phonetics: list[list[str]]) -> dict[str, int]:
    """Build a suffix → group_index mapping from phonetics data.

    Args:
        phonetics: List of rhyme groups; each group is a list of suffix strings.

    Returns:
        Dictionary mapping lowercase suffix strings to their 0-based group index.
    """
    suffix_map: dict[str, int] = {}
    for idx, group in enumerate(phonetics):
        if isinstance(group, list):
            for suffix in group:
                if isinstance(suffix, str) and suffix.strip():
                    suffix_map[suffix.strip().lower()] = idx
    return suffix_map


def get_phonetic_group(word: str, suffix_map: dict[str, int]) -> Optional[int]:
    """Find the phonetic group index for a word using suffix matching.

    Checks suffix lengths 2–9 characters.  Also handles plural forms by
    stripping a trailing 's' and re-checking.

    Args:
        word: The word to look up (punctuation stripped internally).
        suffix_map: Mapping from suffix → group index (from build_suffix_map).

    Returns:
        Group index (int) if matched, else None.
    """
    clean = word.lower().strip(".,?!;:\"'")
    for length in range(2, min(len(clean) + 1, 10)):
        suffix = clean[-length:]
        if suffix in suffix_map:
            return suffix_map[suffix]

    # Retry with singular form (strip trailing 's')
    if clean.endswith("s") and len(clean) > 1:
        singular = clean[:-1]
        for length in range(2, min(len(singular) + 1, 10)):
            suffix = singular[-length:]
            if suffix in suffix_map:
                return suffix_map[suffix]

    return None


def last_word(line: str) -> str:
    """Extract and clean the last word from a lyric line.

    Args:
        line: A lyric line string.

    Returns:
        Last word, lowercased and stripped of punctuation.  Empty string if
        the line has no words.
    """
    words = line.strip().split()
    if not words:
        return ""
    return words[-1].strip(".,?!;:\"'").lower()


def match_line_to_groups(
    line: str,
    suffix_map: dict[str, int],
) -> list[int]:
    """Return all group indices that match the last word of a lyric line.

    Args:
        line: A lyric line string.
        suffix_map: Mapping from suffix → group index.

    Returns:
        List of matching group indices (usually 0 or 1 element).
    """
    word = last_word(line)
    if not word:
        return []
    group_idx = get_phonetic_group(word, suffix_map)
    return [group_idx] if group_idx is not None else []
