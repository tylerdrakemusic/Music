"""
❤Music — Migrate heartmusic.db to SQLCipher (AES-256)

Usage:
    # Set key via env var (pulled from your external secret store):
    set HEARTMUSIC_DB_KEY=<your-encryption-key>
    C:\G\python.exe tools/migrate_to_sqlcipher.py

Prerequisites:
    pip install sqlcipher3-wheels

What this does:
    1. Reads HEARTMUSIC_DB_KEY from environment (never hardcoded)
    2. Creates a timestamped plaintext backup of the existing DB
    3. Exports the plain DB to SQL dump
    4. Re-creates as SQLCipher-encrypted DB using the key
    5. Verifies row counts match before declaring success

After migration, update src/utils/init_db.py to use sqlcipher3 (see prompt at end).
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "src" / "data" / "heartmusic.db"
BACKUP_DIR = PROJECT_ROOT / "src" / "data" / "backups"


def get_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    counts: dict[str, int] = {}
    for (tbl,) in tables:
        safe_tbl = tbl.replace("]", "]]")
        count = conn.execute(f"SELECT COUNT(*) FROM [{safe_tbl}]").fetchone()[0]
        counts[tbl] = count
    return counts


def migrate(db_path: Path, key: str) -> None:
    try:
        import sqlcipher3
    except ImportError:
        print("[ERROR] sqlcipher3 not installed. Run: pip install sqlcipher3-wheels")
        sys.exit(1)

    # Backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"heartmusic_plaintext_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"[✓] Plaintext backup: {backup_path}")

    # Count originals
    plain_conn = sqlite3.connect(str(db_path))
    plain_conn.row_factory = sqlite3.Row
    original_counts = get_table_counts(plain_conn)
    print(f"[✓] Original DB: {sum(original_counts.values())} total rows across {len(original_counts)} tables")

    dump_lines = list(plain_conn.iterdump())
    plain_conn.close()

    # Create encrypted copy
    enc_path = db_path.with_suffix(".enc.db")
    if enc_path.exists():
        enc_path.unlink()

    enc_conn = sqlcipher3.connect(str(enc_path))
    safe_key = key.replace("'", "''")
    enc_conn.execute(f"PRAGMA key='{safe_key}'")
    enc_conn.execute("PRAGMA cipher_page_size=4096")
    enc_conn.execute("PRAGMA kdf_iter=256000")
    enc_conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
    enc_conn.execute("PRAGMA journal_mode=WAL")
    enc_conn.execute("PRAGMA foreign_keys=OFF")
    enc_conn.executescript("\n".join(dump_lines))
    enc_conn.execute("PRAGMA foreign_keys=ON")
    enc_conn.commit()
    enc_conn.close()

    # Verify
    enc_conn2 = sqlcipher3.connect(str(enc_path))
    enc_conn2.execute(f"PRAGMA key='{safe_key}'")
    enc_counts = get_table_counts(enc_conn2)
    enc_conn2.close()

    mismatches = [
        t for t in original_counts
        if original_counts[t] != enc_counts.get(t, -1)
    ]
    if mismatches:
        print(f"[ERROR] Row count mismatch: {mismatches}")
        enc_path.unlink()
        sys.exit(1)

    print(f"[✓] Verified: {sum(enc_counts.values())} rows — counts match")

    db_path.unlink()
    enc_path.rename(db_path)
    print(f"[✓] {db_path.name} replaced with SQLCipher-encrypted version")
    print()
    print("=" * 60)
    print("NEXT STEP — update src/utils/init_db.py:")
    print("=" * 60)
    print("""
Replace:
    import sqlite3

    def get_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))

With:
    import os
    import sqlcipher3

    def get_connection() -> sqlcipher3.Connection:
        key = os.environ.get("HEARTMUSIC_DB_KEY", "")
        if not key:
            raise RuntimeError("HEARTMUSIC_DB_KEY not set")
        conn = sqlcipher3.connect(str(DB_PATH))
        conn.execute(f"PRAGMA key='{key}'")
        conn.execute("PRAGMA cipher_page_size=4096")
        conn.execute("PRAGMA kdf_iter=256000")
        conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
""")
    print(f"Plaintext backup retained at: {backup_path}")
    print("Delete backup after confirming everything works.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate heartmusic.db to SQLCipher")
    parser.add_argument("--key-env", default="HEARTMUSIC_DB_KEY",
                        help="Name of env var holding the encryption key")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[ERROR] Database not found: {DB_PATH}")
        sys.exit(1)

    key = os.environ.get(args.key_env, "").strip()
    if not key:
        print(f"[ERROR] {args.key_env!r} is not set.")
        sys.exit(1)

    print(f"Migrating {DB_PATH} to SQLCipher encryption...")
    migrate(DB_PATH, key)
