#!/usr/bin/env python3
"""
Expand phonetic groups using CMU Pronouncing Dictionary (ARPAbet).

Takes all line-ending words from vault_lines in heartmusic.db, looks up their
ARPAbet phoneme sequences via the `pronouncing` library, groups words by rhyme
part (last stressed vowel + everything after), and proposes new suffix groups
not already present in phonetic_groups.

Usage:
    # Review proposed additions (dry-run)
    C:\\G\\python.exe tools/expand_phonetics_cmu.py

    # Write approved proposals to phonetic_groups table
    C:\\G\\python.exe tools/expand_phonetics_cmu.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pronouncing
except ImportError:
    print("ERROR: `pronouncing` library not installed.  Run:")
    print("  C:\\G\\python.exe -m pip install pronouncing")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import get_connection  # noqa: E402

# ARPAbet vowels that can carry stress
_ARPABET_VOWELS = re.compile(r"^(AA|AE|AH|AO|AW|AY|EH|ER|EY|IH|IY|OW|OY|UH|UW)")


def _rhyme_part(phones: str) -> str | None:
    """Extract the rhyme part: last stressed vowel + everything after.

    Args:
        phones: Space-separated ARPAbet phoneme string (e.g. "HH AH0 L OW1").

    Returns:
        Lowercase rhyme-part string, or None if no stressed vowel found.
    """
    tokens = phones.split()
    # Find the last stressed vowel (ends with '1' or '2')
    last_stressed_idx = None
    for i, tok in enumerate(tokens):
        if _ARPABET_VOWELS.match(tok) and tok[-1] in ("1", "2"):
            last_stressed_idx = i

    if last_stressed_idx is None:
        return None

    rhyme_tokens = tokens[last_stressed_idx:]
    # Strip stress digits for the suffix key
    cleaned = [re.sub(r"\d", "", t).lower() for t in rhyme_tokens]
    return " ".join(cleaned)


def _existing_suffixes(conn) -> set[str]:
    """Return all individual suffix strings already stored in phonetic_groups."""
    rows = conn.execute("SELECT suffixes FROM phonetic_groups").fetchall()
    existing: set[str] = set()
    for (sfx_json,) in rows:
        try:
            for s in json.loads(sfx_json):
                existing.add(s.lower())
        except (json.JSONDecodeError, TypeError):
            pass
    return existing


def _load_line_ending_words() -> list[str]:
    """Return unique last-words from all vault_lines rows."""
    with get_connection() as conn:
        rows = conn.execute("SELECT line FROM vault_lines").fetchall()

    words: set[str] = set()
    for (line,) in rows:
        tokens = line.strip().split()
        if tokens:
            w = tokens[-1].strip(".,?!;:\"'").lower()
            if w:
                words.add(w)
    return sorted(words)


def build_proposals(words: list[str], existing_suffixes: set[str]) -> list[list[str]]:
    """Group words by CMU rhyme-part and propose new suffix groups.

    Args:
        words: List of unique line-ending words.
        existing_suffixes: Suffixes already recorded in phonetic_groups.

    Returns:
        List of proposed new groups, each group being a list of suffix strings.
    """
    # word → rhyme_part string
    rhyme_map: dict[str, str] = {}
    for word in words:
        phones_list = pronouncing.phones_for_word(word)
        if not phones_list:
            continue
        rp = _rhyme_part(phones_list[0])
        if rp:
            rhyme_map[word] = rp

    # group words by rhyme_part
    groups: dict[str, list[str]] = {}
    for word, rp in rhyme_map.items():
        groups.setdefault(rp, []).append(word)

    proposals: list[list[str]] = []
    for rp, group_words in groups.items():
        if len(group_words) < 2:
            continue
        # Only propose if none of the words are already covered
        if all(w not in existing_suffixes for w in group_words):
            proposals.append(sorted(group_words))

    return proposals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expand phonetic groups using CMU Pronouncing Dictionary"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write approved proposals to phonetic_groups table",
    )
    args = parser.parse_args()

    words = _load_line_ending_words()
    print(f"Loaded {len(words)} unique line-ending words from vault_lines")

    with get_connection() as conn:
        existing = _existing_suffixes(conn)

    proposals = build_proposals(words, existing)
    print(f"\nProposed {len(proposals)} new phonetic groups not in DB:\n")

    for i, group in enumerate(proposals):
        print(f"  [{i+1:3d}] {group}")

    if not proposals:
        print("Nothing to propose.")
        return

    if args.apply:
        with get_connection() as conn:
            added = 0
            for group in proposals:
                sfx_json = json.dumps(group, ensure_ascii=False)
                existing_row = conn.execute(
                    "SELECT id FROM phonetic_groups WHERE suffixes = ?",
                    (sfx_json,),
                ).fetchone()
                if not existing_row:
                    conn.execute(
                        "INSERT INTO phonetic_groups (suffixes) VALUES (?)",
                        (sfx_json,),
                    )
                    added += 1
            conn.commit()
        print(f"\n✓ Added {added} new phonetic groups to phonetic_groups table.")
    else:
        print("\n(Dry run — use --apply to write to DB)")


if __name__ == "__main__":
    main()
