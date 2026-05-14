#!/usr/bin/env python3
"""
Migrate lyrics vault and phonetic groups from JSON files to heartmusic.db.

Source files:
    studio_master/lyrics~Locked.json  — array of arrays of lyric line strings
    studio_master/phonetics.json      — array of arrays of suffix strings

Target tables (heartmusic.db):
    vault_lines          — individual deduplicated lyric lines
    phonetic_groups      — rhyme groups (stored as JSON suffix arrays)
    vault_line_groups    — join table linking lines to their phonetic group(s)

After successful import the source JSON files are renamed to *.bak.
processedLyrics.json is left untouched for reference.

Usage:
    C:\\G\\python.exe tools/migrate_lyrics_to_db.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src/ is on the path for init_db import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import get_connection  # noqa: E402

LYRICS_JSON = PROJECT_ROOT / "studio_master" / "lyrics~Locked.json"
PHONETICS_JSON = PROJECT_ROOT / "studio_master" / "phonetics.json"

# ── Schema DDL ────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS vault_lines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    line       TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS phonetic_groups (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    suffixes TEXT NOT NULL   -- JSON array of suffix strings
);

CREATE TABLE IF NOT EXISTS vault_line_groups (
    line_id  INTEGER REFERENCES vault_lines(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES phonetic_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (line_id, group_id)
);
"""


def _flatten_lyrics(data: list) -> list[str]:
    """Recursively flatten nested lists to a flat list of non-empty strings."""
    lines: list[str] = []

    def _rec(node: object) -> None:
        if isinstance(node, str):
            s = node.strip()
            if s:
                lines.append(s)
        elif isinstance(node, list):
            for item in node:
                _rec(item)

    _rec(data)
    return lines


def _deduplicate(lines: list[str]) -> list[str]:
    """Preserve order while removing duplicates (case-sensitive)."""
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            result.append(line)
    return result


def _build_suffix_map(phonetics: list[list[str]]) -> dict[str, int]:
    """Map each suffix (lower) to its 0-based group index."""
    from src.analysis.rhyme_utils import build_suffix_map as _bsm  # noqa: WPS433
    return _bsm(phonetics)


def _get_phonetic_group(
    word: str, suffix_map: dict[str, int]
) -> int | None:
    from src.analysis.rhyme_utils import get_phonetic_group as _gpg  # noqa: WPS433
    return _gpg(word, suffix_map)


def migrate() -> None:
    """Run the full migration and print a summary."""
    # ── Load source files ─────────────────────────────────────────────────────
    if not LYRICS_JSON.exists():
        print(f"ERROR: {LYRICS_JSON} not found (already migrated and renamed?).")
        sys.exit(1)

    if not PHONETICS_JSON.exists():
        print(f"ERROR: {PHONETICS_JSON} not found (already migrated and renamed?).")
        sys.exit(1)

    with LYRICS_JSON.open(encoding="utf-8") as fh:
        raw_lyrics = json.load(fh)

    with PHONETICS_JSON.open(encoding="utf-8") as fh:
        raw_phonetics: list[list[str]] = json.load(fh)

    all_lines = _deduplicate(_flatten_lyrics(raw_lyrics))
    print(f"Source: {len(all_lines)} unique lyric lines, "
          f"{len(raw_phonetics)} phonetic groups")

    # ── Apply schema ──────────────────────────────────────────────────────────
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    # ── Import phonetic groups ────────────────────────────────────────────────
    groups_imported = 0
    group_db_ids: list[int] = []  # index → db row id

    with get_connection() as conn:
        for group in raw_phonetics:
            suffixes_json = json.dumps(group, ensure_ascii=False)
            existing = conn.execute(
                "SELECT id FROM phonetic_groups WHERE suffixes = ?",
                (suffixes_json,),
            ).fetchone()
            if existing:
                group_db_ids.append(existing[0])
            else:
                cur = conn.execute(
                    "INSERT INTO phonetic_groups (suffixes) VALUES (?)",
                    (suffixes_json,),
                )
                group_db_ids.append(cur.lastrowid)
                groups_imported += 1
        conn.commit()

    # ── Import lyric lines ────────────────────────────────────────────────────
    lines_imported = 0
    line_db_ids: dict[str, int] = {}  # line text → db row id

    with get_connection() as conn:
        for line in all_lines:
            existing = conn.execute(
                "SELECT id FROM vault_lines WHERE line = ?", (line,)
            ).fetchone()
            if existing:
                line_db_ids[line] = existing[0]
            else:
                cur = conn.execute(
                    "INSERT INTO vault_lines (line) VALUES (?)", (line,)
                )
                line_db_ids[line] = cur.lastrowid
                lines_imported += 1
        conn.commit()

    # ── Build suffix map ──────────────────────────────────────────────────────
    suffix_map: dict[str, int] = {}  # suffix → 0-based phonetics list index
    for idx, group in enumerate(raw_phonetics):
        if isinstance(group, list):
            for suffix in group:
                if isinstance(suffix, str) and suffix.strip():
                    suffix_map[suffix.strip().lower()] = idx

    def _get_grp(word: str) -> int | None:
        w = word.lower().strip(".,?!;:\"'")
        for length in range(2, min(len(w) + 1, 10)):
            sfx = w[-length:]
            if sfx in suffix_map:
                return suffix_map[sfx]
        if w.endswith("s") and len(w) > 1:
            s2 = w[:-1]
            for length in range(2, min(len(s2) + 1, 10)):
                sfx = s2[-length:]
                if sfx in suffix_map:
                    return suffix_map[sfx]
        return None

    # ── Populate join table ───────────────────────────────────────────────────
    joins_created = 0
    with get_connection() as conn:
        for line in all_lines:
            line_id = line_db_ids[line]
            words = line.strip().split()
            if not words:
                continue
            last = words[-1].strip(".,?!;:\"'").lower()
            group_idx = _get_grp(last)
            if group_idx is None:
                continue
            group_id = group_db_ids[group_idx]
            existing = conn.execute(
                "SELECT 1 FROM vault_line_groups WHERE line_id=? AND group_id=?",
                (line_id, group_id),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO vault_line_groups (line_id, group_id) VALUES (?, ?)",
                    (line_id, group_id),
                )
                joins_created += 1
        conn.commit()

    print(f"✓ Lines imported:          {lines_imported}")
    print(f"✓ Phonetic groups imported: {groups_imported}")
    print(f"✓ Join rows created:        {joins_created}")

    # ── Rename source files ───────────────────────────────────────────────────
    LYRICS_JSON.rename(LYRICS_JSON.with_suffix(".json.bak"))
    PHONETICS_JSON.rename(PHONETICS_JSON.with_suffix(".json.bak"))
    print("✓ Source files renamed to .bak")
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
