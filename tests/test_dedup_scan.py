"""Tests for tools/dedup_scan.py (FR-20260527-catalog-dedup-scan)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT / "src"), str(_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dedup_scan import provenance_score, run_scan  # noqa: E402

# Minimal in-memory schema: sha256 is NOT UNIQUE so we can insert deliberate
# collisions for testing.  duplicate_groups matches the production definition.
_SCHEMA = """
CREATE TABLE release_signatures (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path               TEXT,
    sha256                  TEXT,
    provenance_id           TEXT,
    quantum_signed_at       TEXT,
    pipeline                TEXT,
    chacha20_poly1305_seal  TEXT,
    aesgcm_seal             TEXT,
    provenance_url          TEXT,
    analyzed_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE duplicate_groups (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256                     TEXT NOT NULL,
    canonical_sig_id           INTEGER REFERENCES release_signatures(id),
    duplicate_sig_id           INTEGER REFERENCES release_signatures(id),
    provenance_score_canonical INTEGER,
    provenance_score_duplicate INTEGER,
    detected_at                TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(sha256, duplicate_sig_id)
);
"""

_PROV_SELECT = (
    "SELECT id, provenance_id, quantum_signed_at, pipeline, "
    "chacha20_poly1305_seal, aesgcm_seal, provenance_url "
    "FROM release_signatures WHERE sha256 = ?"
)


@pytest.fixture()
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    yield conn
    conn.close()


# ── provenance_score unit tests ───────────────────────────────────────────────


def test_provenance_score_all_null(mem_db):
    mem_db.execute("INSERT INTO release_signatures (sha256) VALUES (?)", ("s_null",))
    mem_db.commit()
    row = mem_db.execute(_PROV_SELECT, ("s_null",)).fetchone()
    assert provenance_score(row) == 0


def test_provenance_score_all_filled(mem_db):
    mem_db.execute(
        """INSERT INTO release_signatures
               (sha256, provenance_id, quantum_signed_at, pipeline,
                chacha20_poly1305_seal, aesgcm_seal, provenance_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("s_full", "pid", "2026-01-01", "pipe", "seal1", "seal2", "https://example.com"),
    )
    mem_db.commit()
    row = mem_db.execute(_PROV_SELECT, ("s_full",)).fetchone()
    assert provenance_score(row) == 6


def test_provenance_score_partial(mem_db):
    mem_db.execute(
        """INSERT INTO release_signatures
               (sha256, provenance_id, quantum_signed_at, pipeline)
           VALUES (?, ?, ?, ?)""",
        ("s_partial", "pid", "2026-01-01", "pipe"),
    )
    mem_db.commit()
    row = mem_db.execute(_PROV_SELECT, ("s_partial",)).fetchone()
    assert provenance_score(row) == 3


# ── scan logic tests ──────────────────────────────────────────────────────────


def test_scan_idempotent(mem_db):
    """Running scan twice on the same data must leave exactly 1 row in duplicate_groups."""
    mem_db.executemany(
        "INSERT INTO release_signatures (sha256, analyzed_at) VALUES (?, ?)",
        [
            ("dup_hash", "2026-01-01 00:00:00"),
            ("dup_hash", "2026-01-02 00:00:00"),
            ("unique_hash", "2026-01-01 00:00:00"),
        ],
    )
    mem_db.commit()

    run_scan(mem_db)
    run_scan(mem_db)

    count = mem_db.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0]
    assert count == 1


def test_canonical_wins_by_score(mem_db):
    """Row A (score 5) should become canonical over Row B (score 2)."""
    mem_db.execute(
        """INSERT INTO release_signatures
               (sha256, provenance_id, quantum_signed_at, pipeline,
                chacha20_poly1305_seal, aesgcm_seal, analyzed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("score_test", "pid", "2026-01-01", "pipe", "seal1", "seal2", "2026-01-01 00:00:00"),
    )
    id_a = mem_db.execute("SELECT last_insert_rowid()").fetchone()[0]

    mem_db.execute(
        """INSERT INTO release_signatures
               (sha256, provenance_id, quantum_signed_at, analyzed_at)
           VALUES (?, ?, ?, ?)""",
        ("score_test", "pid2", "2026-01-02", "2026-01-02 00:00:00"),
    )
    id_b = mem_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    mem_db.commit()

    run_scan(mem_db)

    dg = mem_db.execute(
        "SELECT canonical_sig_id, duplicate_sig_id, "
        "provenance_score_canonical, provenance_score_duplicate "
        "FROM duplicate_groups"
    ).fetchone()

    assert dg["canonical_sig_id"] == id_a
    assert dg["duplicate_sig_id"] == id_b
    assert dg["provenance_score_canonical"] == 5
    assert dg["provenance_score_duplicate"] == 2
