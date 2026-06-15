"""Reconcile legacy HeartMusic data from the alternate heartmusic.db into the canonical copy.

Usage:
    C:\G\python.exe tools/reconcile_heartmusic_db.py [--dry-run] [--alt-db <path>]

The canonical DB is `src/data/heartmusic.db`. The legacy DB is
`data/legacy_heartmusic.db` and may be populated with recovered guitar training,
studio equipment, lyrics phonetics, and sheet music data.

This script is idempotent and safe to run multiple times.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils.init_db import ALT_DB_PATH, CANONICAL_DB_PATH, get_connection, _open_with_any_key  # noqa: E402

MERGE_TABLES = [
    "studio_equipment",
    "guitar_exercises",
    "guitar_training_log",
    "vault_lines",
    "phonetic_groups",
    "vault_line_groups",
    "lyrics",
    "sheet_music",
]

UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
    "studio_equipment": ("studio_name", "category", "label", "spec_json"),
    "guitar_exercises": ("title", "artist", "song_path"),
    "guitar_training_log": ("exercise_id", "song_path", "seg_start", "seg_end", "repetition", "logged_at"),
    "vault_lines": ("line",),
    "phonetic_groups": ("suffixes",),
    "vault_line_groups": ("line_id", "group_id"),
    "lyrics": ("track_id", "body"),
    "sheet_music": ("gdrive_file_id", "source", "name", "local_path"),
}

SKIP_TABLES = {"sqlite_sequence"}


def _get_table_sql(conn: Any, table_name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row[0] if row else None


def _copy_indexes(src_conn: Any, dst_conn: Any, table_name: str) -> None:
    for row in src_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = ? AND sql IS NOT NULL",
        (table_name,),
    ).fetchall():
        if row[0]:
            dst_conn.execute(row[0])


def _row_exists(conn: Any, table: str, columns: tuple[str, ...], values: tuple[Any, ...]) -> bool:
    where = " AND ".join(f"{col} = ?" for col in columns)
    sql = f"SELECT 1 FROM {table} WHERE {where} LIMIT 1"
    return conn.execute(sql, values).fetchone() is not None


def _row_to_dict(conn: Any, table: str, row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return dict(row)
    columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return dict(zip(columns, row))


def _load_row(conn: Any, table: str, row_id: int) -> dict[str, Any] | None:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return _row_to_dict(conn, table, row) if row else None


def _build_id_map(conn: Any, table: str, key_cols: tuple[str, ...]) -> dict[tuple[Any, ...], int]:
    rows = conn.execute(f"SELECT id, {', '.join(key_cols)} FROM {table}").fetchall()
    return {
        tuple(row[col] for col in key_cols): row[0]
        for row in rows
        if all(row[col] is not None for col in key_cols)
    }


def _reconcile_table(src_conn: Any, dst_conn: Any, table: str, dry_run: bool) -> int:
    src_rows = src_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not src_rows:
        return 0

    if table == "vault_line_groups":
        return _reconcile_vault_line_groups(src_conn, dst_conn, src_rows, dry_run)

    unique_keys = UNIQUE_KEYS.get(table)
    inserted = 0

    for src_row in src_rows:
        row_dict = _row_to_dict(src_conn, table, src_row)

        if table == "sheet_music":
            if row_dict.get("gdrive_file_id") is not None:
                unique_keys = ("gdrive_file_id",)
            else:
                unique_keys = ("source", "name", "local_path")

        if unique_keys is None:
            unique_keys = tuple(col for col in row_dict if col != "id")

        key_values = tuple(row_dict[col] for col in unique_keys)
        if _row_exists(dst_conn, table, unique_keys, key_values):
            continue

        columns = [col for col in row_dict if col != "id"]
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)
        values = tuple(row_dict[col] for col in columns)
        if not dry_run:
            dst_conn.execute(
                f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
                values,
            )
        inserted += 1

    return inserted


def _reconcile_vault_line_groups(src_conn: Any, dst_conn: Any, src_rows: list[Any], dry_run: bool) -> int:
    line_map = _build_id_map(dst_conn, "vault_lines", ("line",))
    group_map = _build_id_map(dst_conn, "phonetic_groups", ("suffixes",))
    inserted = 0

    for src_row in src_rows:
        src_dict = _row_to_dict(src_conn, "vault_line_groups", src_row)
        src_line = src_conn.execute("SELECT line FROM vault_lines WHERE id = ?", (src_dict["line_id"],)).fetchone()
        src_group = src_conn.execute("SELECT suffixes FROM phonetic_groups WHERE id = ?", (src_dict["group_id"],)).fetchone()
        if not src_line or not src_group:
            continue
        line_key = (src_line[0],)
        group_key = (src_group[0],)
        dst_line_id = line_map.get(line_key)
        dst_group_id = group_map.get(group_key)
        if dst_line_id is None or dst_group_id is None:
            continue

        if _row_exists(dst_conn, "vault_line_groups", ("line_id", "group_id"), (dst_line_id, dst_group_id)):
            continue

        if not dry_run:
            dst_conn.execute(
                "INSERT INTO vault_line_groups (line_id, group_id) VALUES (?, ?)",
                (dst_line_id, dst_group_id),
            )
        inserted += 1

    return inserted


def _create_missing_table(dst_conn: Any, src_conn: Any, table: str) -> bool:
    create_sql = _get_table_sql(src_conn, table)
    if not create_sql:
        return False
    dst_conn.execute(create_sql)
    _copy_indexes(src_conn, dst_conn, table)
    return True


def _get_existing_tables(conn: Any) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile alternate heartmusic.db into canonical src/data/heartmusic.db.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the canonical DB.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without modifying the canonical DB.")
    parser.add_argument("--alt-db", type=Path, default=ALT_DB_PATH, help="Legacy heartmusic.db path to reconcile from.")
    parser.add_argument("--canonical-db", type=Path, default=CANONICAL_DB_PATH, help="Canonical heartmusic.db path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    key = os.environ.get("HEARTMUSIC_DB_KEY", "")
    if not key:
        raise RuntimeError("HEARTMUSIC_DB_KEY is required to open both canonical and alternate heartmusic.db files.")

    if not args.alt_db.exists():
        raise FileNotFoundError(f"Alternate heartmusic.db not found at {args.alt_db}")
    if not args.canonical_db.exists():
        raise FileNotFoundError(f"Canonical heartmusic.db not found at {args.canonical_db}")

    print(f"Canonical DB: {args.canonical_db}")
    print(f"Alternate DB: {args.alt_db}")
    print(f"Dry run: {not args.apply}")

    alt_conn, alt_hex_mode = _open_with_any_key(args.alt_db, key)
    try:
        if alt_hex_mode:
            print("Opened alternate DB with hex key mode.")
        else:
            print("Opened alternate DB with text key mode.")

        canonical_conn = get_connection()
        try:
            if args.canonical_db != CANONICAL_DB_PATH:
                raise RuntimeError("get_connection() currently only supports the canonical DB path.")

            existing = _get_existing_tables(canonical_conn)
            missing_tables = [t for t in MERGE_TABLES if t not in existing]
            for table in missing_tables:
                print(f"Creating missing table: {table}")
                if args.apply:
                    _create_missing_table(canonical_conn, alt_conn, table)

            summary: dict[str, int] = {}
            for table in MERGE_TABLES:
                if table not in _get_existing_tables(canonical_conn):
                    print(f"Skipping {table} because it is not available in canonical DB.")
                    continue
                if table not in _get_existing_tables(alt_conn):
                    print(f"Skipping {table} because it is not available in alternate DB.")
                    continue
                count = _reconcile_table(alt_conn, canonical_conn, table, dry_run=not args.apply)
                summary[table] = count
                print(f"{table}: {count} row(s) would be inserted." if not args.apply else f"{table}: {count} row(s) inserted.")

            if args.apply:
                canonical_conn.commit()
                print("Changes committed to canonical DB.")
            else:
                print("Dry run complete. No changes were written.")

            print("Summary:")
            for table, count in summary.items():
                print(f"  {table}: {count}")
        finally:
            canonical_conn.close()
    finally:
        alt_conn.close()


if __name__ == "__main__":
    main()
