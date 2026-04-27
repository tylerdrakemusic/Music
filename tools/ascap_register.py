"""One-shot ASCAP registration data import tool.

Adds rights columns to tracks if missing, then stores ASCAP work IDs.
Run from f:\❤Music\src dir or anywhere with HEARTMUSIC_DB_KEY set.

Usage: python tools/ascap_register.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
os.chdir(Path(__file__).parent.parent / "src")

from utils.init_db import get_connection  # noqa: E402


def migrate_rights_columns(conn) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(tracks)").fetchall()]
    migrations = [
        ("isrc", "TEXT"),
        ("iswc", "TEXT"),
        ("copyright_year", "INTEGER"),
        ("copyright_holder", "TEXT"),
        ("license_type", "TEXT"),
        ("ascap_work_id", "TEXT"),
        ("pro_registered", "INTEGER DEFAULT 0"),
    ]
    for col, typedef in migrations:
        if col not in cols:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {typedef}")
            print(f"  + Added column: {col}")
        else:
            print(f"  . Already exists: {col}")
    conn.commit()


def store_ascap_work_id(conn, title_pattern: str, work_id: str, pro: int = 1) -> None:
    rows = conn.execute(
        "SELECT id, title FROM tracks WHERE lower(title) LIKE ?",
        (f"%{title_pattern.lower()}%",),
    ).fetchall()
    if not rows:
        print(f"  ! No track found matching: {title_pattern!r} — inserting stub")
        conn.execute(
            "INSERT INTO tracks (title, ascap_work_id, pro_registered, copyright_holder)"
            " VALUES (?, ?, ?, 'Tyler James Drake')",
            (title_pattern, work_id, pro),
        )
        conn.commit()
        print(f"    Inserted stub for {title_pattern!r} with ASCAP work ID {work_id}")
        return
    for row in rows:
        conn.execute(
            "UPDATE tracks SET ascap_work_id=?, pro_registered=?, copyright_holder=? WHERE id=?",
            (work_id, pro, "Tyler James Drake", row[0]),
        )
        print(f"  ✓ Updated track id={row[0]} '{row[1]}' → ASCAP work ID {work_id}")
    conn.commit()


def main() -> None:
    print("Connecting to heartmusic.db...")
    conn = get_connection()

    print("\n[1] Migrating rights columns...")
    migrate_rights_columns(conn)

    print("\n[2] Storing ASCAP registrations...")
    # All three EP tracks confirmed by Tyler — 2026-04-26
    store_ascap_work_id(conn, "What I Do", "935854248")   # https://www.ascap.com/member-access#works/935854248
    store_ascap_work_id(conn, "Marigold",  "922951232")   # https://www.ascap.com/member-access#works/922951232
    store_ascap_work_id(conn, "Get Out",   "935854254")   # https://www.ascap.com/member-access#works/935854254

    print("\n[3] Current registered tracks:")
    rows = conn.execute(
        "SELECT id, title, ascap_work_id, pro_registered FROM tracks WHERE pro_registered=1"
    ).fetchall()
    for r in rows:
        print(f"  id={r[0]} '{r[1]}' → ASCAP {r[2]}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
