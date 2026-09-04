"""Regression tests for SQL identifier handling in DB reconciliation."""

import sqlite3

import pytest

from tools.reconcile_heartmusic_db import _reconcile_table, _row_exists, _row_to_dict


def test_row_exists_rejects_injected_table_identifier() -> None:
    """Dynamic table names must be validated before interpolation into SQL."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, title TEXT)")

    with pytest.raises(ValueError, match="identifier|Invalid"):
        _row_exists(conn, "tracks; DROP TABLE tracks; --", ("id",), (1,))

    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tracks'"
    ).fetchone() is not None


def test_row_to_dict_rejects_injected_table_identifier() -> None:
    """PRAGMA metadata lookup must not accept arbitrary table SQL."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, title TEXT)")

    with pytest.raises(ValueError, match="identifier|Invalid"):
        _row_to_dict(conn, "tracks) WHERE 1=1 --", (1, "Song"))


def test_row_exists_rejects_injected_column_identifier() -> None:
    """Dynamic column names must be validated before interpolation into SQL."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, title TEXT)")

    with pytest.raises(ValueError, match="identifier|Invalid"):
        _row_exists(conn, "tracks", ("id = 1 OR 1=1 --",), (1,))


def test_reconcile_table_quotes_insert_identifiers() -> None:
    """Reconciliation must quote schema-derived identifiers in INSERT SQL."""
    source = sqlite3.connect(":memory:")
    target = sqlite3.connect(":memory:")
    source.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, title TEXT)")
    target.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, title TEXT)")
    source.execute("INSERT INTO tracks (id, title) VALUES (?, ?)", (1, "Song"))

    assert _reconcile_table(source, target, "tracks", dry_run=False) == 1
    assert target.execute("SELECT title FROM tracks WHERE id = 1").fetchone() == ("Song",)