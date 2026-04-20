"""
❤Music — Add quantum signature columns to release_signatures table

Usage:
    C:\G\python.exe tools/migrate_add_quantum_sig_columns.py

Adds 6 columns for quantum-enhanced signatures:
  - quantum_salt       : 256-bit quantum random salt (hex)
  - quantum_blake2b    : BLAKE2b-512 keyed with quantum salt
  - quantum_sha3_512   : SHA3-512 (post-quantum resistant)
  - quantum_entropy_bits : quantum bits consumed
  - quantum_source     : 'ibm_quantum_cache' | 'classical_fallback'
  - quantum_signed_at  : ISO timestamp of quantum signing
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT.parent.parent / ".env")

from utils.init_db import get_connection


COLUMNS = [
    ("quantum_salt", "TEXT"),
    ("quantum_blake2b", "TEXT"),
    ("quantum_sha3_512", "TEXT"),
    ("quantum_entropy_bits", "INTEGER"),
    ("quantum_source", "TEXT"),
    ("quantum_signed_at", "TEXT"),
]


def migrate() -> None:
    conn = get_connection()
    try:
        existing = [
            row[1] for row in conn.execute("PRAGMA table_info(release_signatures)").fetchall()
        ]
        added = []
        for col_name, col_type in COLUMNS:
            if col_name in existing:
                print(f"  Column '{col_name}' already exists — skipping.")
            else:
                conn.execute(f"ALTER TABLE release_signatures ADD COLUMN {col_name} {col_type}")
                added.append(col_name)

        # Index on quantum_blake2b for lookups
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_release_sig_qblake2b "
            "ON release_signatures(quantum_blake2b)"
        )
        conn.commit()

        if added:
            print(f"Added {len(added)} column(s): {', '.join(added)}")
        else:
            print("All quantum columns already present.")

        # Verify
        cols = conn.execute("PRAGMA table_info(release_signatures)").fetchall()
        print(f"\nTotal columns: {len(cols)}")
        for c in cols:
            marker = " ← NEW" if c[1] in added else ""
            print(f"  {c[0]:3d} | {c[1]:25s} | {c[2]}{marker}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
