"""Migrate recovered exercise card JSON files to guitar_exercises and guitar_training_log tables.

Run once after init_db.py creates the tables:
    $env:HEARTMUSIC_DB_KEY="..."; C:\G\python.exe f:\❤Music\tools\migrate_training_to_db.py

FR-20260425-guitar-trainer-db-migration
FR-20260524-practice-log-broken  (added live trainingLog.json migration)
"""

import json
import sys
from pathlib import Path

# Ensure utils on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.init_db import get_connection  # noqa: E402

TMP_DIR = PROJECT_ROOT / "tmp"
LIVE_LOG_PATH = PROJECT_ROOT / "tools" / "tyJson" / "exercises" / "musicTraining" / "trainingLog.json"


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

    # ── Training log (recovered backup) ─────────────────────────────────────
    log_path = TMP_DIR / "recovered_trainingLog.json"
    if log_path.exists():
        try:
            log_entries = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"SKIP recovered_trainingLog: {exc}")
            log_entries = []
        print(f"\nFound {len(log_entries)} log entry(entries) in recovered_trainingLog.json.")
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
        print(f"  Migrated {len(log_entries)} log entries from recovered_trainingLog.json.")
    else:
        print("\nNo recovered_trainingLog.json found — skipping backup log migration.")

    # ── Live trainingLog.json (split-brain fix — FR-20260524-practice-log-broken) ──
    if LIVE_LOG_PATH.exists():
        try:
            live_entries = json.loads(LIVE_LOG_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"\nSKIP live trainingLog.json: {exc}")
            live_entries = []
        print(f"\nFound {len(live_entries)} entry(entries) in live trainingLog.json.")
        migrated = 0
        skipped = 0
        for entry in live_entries:
            timestamp = entry.get("timestamp", "")
            song_path = entry.get("songPath", "")
            seg = entry.get("segment", {})
            seg_start = str(seg.get("start", ""))
            seg_end = str(seg.get("end", ""))
            repetition = int(seg.get("repetition", 1))
            # Dedup: skip if identical row already exists
            existing = conn.execute(
                "SELECT id FROM guitar_training_log "
                "WHERE song_path=? AND seg_start=? AND seg_end=? AND logged_at=?",
                (song_path, seg_start, seg_end, timestamp),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO guitar_training_log "
                "(exercise_id, song_path, seg_start, seg_end, repetition, logged_at) "
                "VALUES (NULL,?,?,?,?,?)",
                (song_path, seg_start, seg_end, repetition, timestamp),
            )
            migrated += 1
        conn.commit()
        print(f"  Migrated {migrated} new entries, skipped {skipped} duplicates.")
        # Delete the JSON file now that all entries are safely in the DB
        LIVE_LOG_PATH.unlink()
        print(f"  Deleted {LIVE_LOG_PATH}")
    else:
        print("\nNo live trainingLog.json found — nothing to migrate.")

    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()



if __name__ == "__main__":
    migrate()
