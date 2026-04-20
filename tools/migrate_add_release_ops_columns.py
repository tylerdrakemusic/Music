"""
❤Music — Add post-release ops columns to releases

Usage:
    C:\G\python.exe tools/migrate_add_release_ops_columns.py

Adds the release verification and aggregation columns used by the
post-Bloom release operations dashboard and workflow.
"""

import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT.parent.parent / ".env")

from utils.init_db import get_connection


COLUMNS = [
    ("spotify_confirmed", "INTEGER DEFAULT 0"),
    ("apple_confirmed", "INTEGER DEFAULT 0"),
    ("amazon_confirmed", "INTEGER DEFAULT 0"),
    ("youtube_confirmed", "INTEGER DEFAULT 0"),
    ("deezer_confirmed", "INTEGER DEFAULT 0"),
    ("pandora_confirmed", "INTEGER DEFAULT 0"),
    ("iheart_confirmed", "INTEGER DEFAULT 0"),
    ("bandcamp_confirmed", "INTEGER DEFAULT 0"),
    ("audius_confirmed", "INTEGER DEFAULT 0"),
    ("platform_urls", "TEXT"),
    ("soundexchange_id", "TEXT"),
]


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TYPE_RE = re.compile(r"^(TEXT|INTEGER(?:\s+DEFAULT\s+[0-9]+)?)$")


def _validate_identifier(identifier: str) -> str:
    if not _IDENT_RE.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return identifier


def _validate_column_type(column_type: str) -> str:
    normalized = " ".join(column_type.strip().split())
    if not _TYPE_RE.fullmatch(normalized):
        raise ValueError(f"Invalid SQL column type: {column_type!r}")
    return normalized


def migrate() -> None:
    conn = get_connection()
    try:
        existing = [row[1] for row in conn.execute("PRAGMA table_info(releases)").fetchall()]
        added: list[str] = []
        for col_name, col_type in COLUMNS:
            if col_name in existing:
                print(f"  Column '{col_name}' already exists — skipping.")
            else:
                safe_col = _validate_identifier(col_name)
                safe_type = _validate_column_type(col_type)
                alter_sql = "ALTER TABLE releases ADD COLUMN " + safe_col + " " + safe_type
                conn.execute(alter_sql)
                added.append(col_name)

        conn.commit()

        if added:
            print(f"Added {len(added)} release column(s): {', '.join(added)}")
        else:
            print("All release ops columns already present.")

        cols = conn.execute("PRAGMA table_info(releases)").fetchall()
        print(f"\nTotal release columns: {len(cols)}")
        for col in cols:
            marker = " ← NEW" if col[1] in added else ""
            print(f"  {col[0]:3d} | {col[1]:24s} | {col[2]}{marker}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()