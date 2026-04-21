"""
❤Music — Add full hash suite + AEAD columns to release_signatures

Usage:
    C:\G\python.exe tools/migrate_add_full_hash_suite.py

Adds columns for the complete Tyler James Drake signature suite:
  Hash suite: blake2s, sha512, sha512_224, sha512_256, shake_128, shake_256, whirlpool
  AEAD seals: chacha20_poly1305_seal, aesgcm_seal, aead_nonce, aead_tag
  (blake2b, md5, sha256, sha3_512 already exist)
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
    # Extended hash suite
    ("blake2s", "TEXT"),
    ("sha512", "TEXT"),
    ("sha512_224", "TEXT"),
    ("sha512_256", "TEXT"),
    ("shake_128", "TEXT"),
    ("shake_256", "TEXT"),
    ("whirlpool", "TEXT"),
    # AEAD authenticated seals (ChaCha20-Poly1305 + AES-256-GCM)
    ("chacha20_poly1305_seal", "TEXT"),    # hex ciphertext of hash digest
    ("aesgcm_seal", "TEXT"),              # hex ciphertext of hash digest
    ("aead_nonce", "TEXT"),               # hex nonce shared by both AEAD ops
    ("aead_aad", "TEXT"),                 # associated data (file path + size + sha256)
    ("sig_version", "TEXT"),              # signature suite version
]


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TYPE_RE = re.compile(r"^TEXT$")


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
        existing = [
            row[1] for row in conn.execute("PRAGMA table_info(release_signatures)").fetchall()
        ]
        added = []
        for col_name, col_type in COLUMNS:
            if col_name in existing:
                print(f"  Column '{col_name}' already exists — skipping.")
            else:
                safe_col = _validate_identifier(col_name)
                safe_type = _validate_column_type(col_type)
                alter_sql = "ALTER TABLE release_signatures ADD COLUMN " + safe_col + " " + safe_type
                conn.execute(alter_sql)
                added.append(col_name)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_release_sig_sha512 "
            "ON release_signatures(sha512)"
        )
        conn.commit()

        if added:
            print(f"Added {len(added)} column(s): {', '.join(added)}")
        else:
            print("All columns already present.")

        cols = conn.execute("PRAGMA table_info(release_signatures)").fetchall()
        print(f"\nTotal columns: {len(cols)}")
        for c in cols:
            marker = " ← NEW" if c[1] in added else ""
            print(f"  {c[0]:3d} | {c[1]:30s} | {c[2]}{marker}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
