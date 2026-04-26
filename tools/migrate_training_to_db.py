"""Migrate recovered exercise card JSON files to guitar_exercises and guitar_training_log tables.

Run once after init_db.py creates the tables:
    $env:HEARTMUSIC_DB_KEY="..."; C:\G\python.exe f:\❤Music\tools\migrate_training_to_db.py

FR-20260425-guitar-trainer-db-migration
"""

import json
import sys
from pathlib import Path

# Ensure utils on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import get_connection  # noqa: E402

TMP_DIR = PROJECT_ROOT / "tmp"


def migrate() -> None:
    conn = get_connection()

    # ── Exercise cards ──────────────────────────────────────────────────────
    card_files = sorted(
        p for p in TMP_DIR.glob("recovered_*.json")
        if not p.name.startswith("recovered__run_")
        and p.name != "recovered_trainingLog.json"
    )
    print(f"Found {len(card_files)} exercise card(s) to migrate.")
    for p in card_files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  SKIP {p.name}: {exc}")
            continue
        title = (data.get("title") or p.stem.replace("recovered_", "").replace("_", " ").title()).strip()
        artist = (data.get("artist") or "").strip()
        song_path = (data.get("songPath") or "").strip()
        segments = json.dumps(data.get("segments", []))
        gradient = int(data.get("gradient", 0))
        # INSERT OR IGNORE so re-runs are safe
        cur = conn.execute(
            "INSERT OR IGNORE INTO guitar_exercises (title, artist, song_path, segments, gradient) "
            "VALUES (?,?,?,?,?)",
            (title, artist, song_path, segments, gradient),
        )
        status = "inserted" if cur.lastrowid else "skipped (duplicate?)"
        print(f"  {p.name}: {title} — {status}")

    conn.commit()

    # ── Training log ────────────────────────────────────────────────────────
    log_path = TMP_DIR / "recovered_trainingLog.json"
    if log_path.exists():
        try:
            log_entries = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"SKIP trainingLog: {exc}")
            log_entries = []
        print(f"\nFound {len(log_entries)} log entry(entries) to migrate.")
        for entry in log_entries:
            timestamp = entry.get("timestamp", "")
            song_path = entry.get("songPath", "")
            seg = entry.get("segment", {})
            seg_start = str(seg.get("start", ""))
            seg_end = str(seg.get("end", ""))
            repetition = int(seg.get("repetition", 1))
            conn.execute(
                "INSERT INTO guitar_training_log "
                "(exercise_id, song_path, seg_start, seg_end, repetition, logged_at) "
                "VALUES (NULL,?,?,?,?,?)",
                (song_path, seg_start, seg_end, repetition, timestamp),
            )
        conn.commit()
        print(f"  Migrated {len(log_entries)} log entries.")
    else:
        print("\nNo recovered_trainingLog.json found — skipping log migration.")

    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
