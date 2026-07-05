"""Catalog Duplicate Audio File Detector (FR-20260527-catalog-dedup-scan).

Detects release_signatures rows that share a sha256 hash, scores each by
provenance richness, designates the highest-scoring (oldest on tie) row as
canonical, and records all (canonical, duplicate) pairs in duplicate_groups.

Usage:
    python tools/dedup_scan.py           # scan mode
    python tools/dedup_scan.py --report  # view duplicates on record
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import utils.init_db as _init_db_module  # noqa: E402

_init_db_module.use_worktree_aware_db_path(_ROOT)

from utils.init_db import get_connection  # noqa: E402

_PROVENANCE_FIELDS = (
    "provenance_id",
    "quantum_signed_at",
    "pipeline",
    "chacha20_poly1305_seal",
    "aesgcm_seal",
    "provenance_url",
)


def provenance_score(row) -> int:
    """Return count of non-null values among the 6 provenance fields (0-6)."""
    return sum(1 for f in _PROVENANCE_FIELDS if row[f] is not None)


def run_scan(conn) -> tuple[int, int]:
    """Scan release_signatures for sha256 collisions; write duplicate_groups.

    Returns:
        (group_count, pair_count) — number of collision groups and total pairs.
    """
    cur = conn.cursor()

    collisions = cur.execute(
        "SELECT sha256 FROM release_signatures GROUP BY sha256 HAVING COUNT(*) > 1"
    ).fetchall()

    group_count = len(collisions)
    pair_count = 0

    for row in collisions:
        sha256_val = row[0]

        sigs = cur.execute(
            """SELECT id,
                      provenance_id,
                      quantum_signed_at,
                      pipeline,
                      chacha20_poly1305_seal,
                      aesgcm_seal,
                      provenance_url,
                      analyzed_at
               FROM release_signatures
               WHERE sha256 = ?
               ORDER BY id""",
            (sha256_val,),
        ).fetchall()

        # Score all rows; ties broken by analyzed_at ASC (oldest = canonical)
        scored = [
            (provenance_score(sig), sig["analyzed_at"], sig["id"])
            for sig in sigs
        ]
        scored.sort(key=lambda x: (-x[0], x[1]))

        canonical_id = scored[0][2]
        canonical_score = scored[0][0]

        # Full idempotency: wipe existing entries for this sha256, then re-insert
        cur.execute("DELETE FROM duplicate_groups WHERE sha256 = ?", (sha256_val,))

        for dup_score, _analyzed_at, dup_id in scored[1:]:
            cur.execute(
                """INSERT OR IGNORE INTO duplicate_groups
                       (sha256, canonical_sig_id, duplicate_sig_id,
                        provenance_score_canonical, provenance_score_duplicate)
                   VALUES (?, ?, ?, ?, ?)""",
                (sha256_val, canonical_id, dup_id, canonical_score, dup_score),
            )
            pair_count += 1

    conn.commit()
    return group_count, pair_count


def run_report(conn) -> None:
    """Print a formatted table of all recorded duplicate groups."""
    rows = conn.execute(
        """SELECT dg.sha256,
                  c.file_path  AS canonical_path,
                  d.file_path  AS duplicate_path,
                  dg.provenance_score_canonical,
                  dg.provenance_score_duplicate,
                  dg.detected_at
           FROM duplicate_groups dg
           JOIN release_signatures c ON c.id = dg.canonical_sig_id
           JOIN release_signatures d ON d.id = dg.duplicate_sig_id
           ORDER BY dg.sha256, dg.duplicate_sig_id"""
    ).fetchall()

    if not rows:
        print("No duplicates on record. Run without --report to scan.")
        return

    table_data = [
        (
            row["sha256"][:12],
            (row["canonical_path"] or "(null)"),
            (row["duplicate_path"] or "(null)"),
            row["provenance_score_canonical"],
            row["provenance_score_duplicate"],
            row["detected_at"],
        )
        for row in rows
    ]
    headers = ["sha256[:12]", "canonical_path", "duplicate_path", "c_score", "d_score", "detected_at"]

    try:
        from tabulate import tabulate  # type: ignore
        print(tabulate(table_data, headers=headers, tablefmt="simple"))
    except ImportError:
        col_widths = [12, 45, 45, 7, 7, 20]
        fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
        print(fmt.format(*headers))
        print("  ".join("-" * w for w in col_widths))
        for row_data in table_data:
            print(fmt.format(
                row_data[0],
                row_data[1][:45],
                row_data[2][:45],
                str(row_data[3]),
                str(row_data[4]),
                row_data[5] or "",
            ))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Catalog duplicate audio file detector"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Show duplicate_groups report instead of scanning",
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        if args.report:
            run_report(conn)
        else:
            group_count, pair_count = run_scan(conn)
            print(
                f"Scan complete. {group_count} duplicate group(s) found. "
                f"{pair_count} pair(s) written."
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
