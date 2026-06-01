"""❤Music — Practice streak and consistency stats.

FR-20260525-practice-streak-badge
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils.init_db import get_connection  # noqa: E402


def get_practice_stats() -> dict:
    """Return practice streak, weekly minutes, and last practice date.

    Returns:
        {
            "streak_days": int,          # current consecutive-day streak (UTC)
            "week_minutes": int,         # total duration_minutes in current ISO week (Mon-Sun)
            "last_practiced": str|None,  # ISO date YYYY-MM-DD of most recent entry, or None
        }
    """
    try:
        conn = get_connection()

        # All distinct calendar dates (UTC) that have at least one entry in either table
        rows = conn.execute(
            """
            SELECT date(logged_at) AS practice_date
            FROM guitar_training_log
            UNION
            SELECT date(logged_at) AS practice_date
            FROM scale_practice_log
            ORDER BY practice_date DESC
            """
        ).fetchall()

        dates_iso = [row[0] for row in rows if row[0]]

        # Streak calculation
        today = datetime.now(timezone.utc).date()
        streak = 0
        if dates_iso:
            date_set = set(dates_iso)
            # Start from today; if today has no entry, try yesterday
            cursor = today
            if cursor.isoformat() not in date_set:
                cursor = today - timedelta(days=1)
            # Walk backward while consecutive days exist
            if cursor.isoformat() in date_set:
                while cursor.isoformat() in date_set:
                    streak += 1
                    cursor -= timedelta(days=1)

        # Weekly minutes (current ISO week: Monday 00:00 UTC through now)
        today_weekday = today.weekday()  # 0=Monday, 6=Sunday
        week_start = today - timedelta(days=today_weekday)
        week_start_str = week_start.isoformat()

        week_row = conn.execute(
            """
            SELECT COALESCE(SUM(duration_minutes), 0)
            FROM (
                SELECT duration_minutes FROM guitar_training_log
                WHERE date(logged_at) >= ?
                UNION ALL
                SELECT duration_minutes FROM scale_practice_log
                WHERE date(logged_at) >= ?
            )
            """,
            (week_start_str, week_start_str),
        ).fetchone()
        week_minutes = int(week_row[0]) if week_row and week_row[0] is not None else 0

        # Last practiced — MAX(logged_at) across both tables
        last_row = conn.execute(
            """
            SELECT MAX(logged_at)
            FROM (
                SELECT logged_at FROM guitar_training_log
                UNION ALL
                SELECT logged_at FROM scale_practice_log
            )
            """
        ).fetchone()
        last_practiced: str | None = None
        if last_row and last_row[0]:
            try:
                last_practiced = str(last_row[0])[:10]  # YYYY-MM-DD
            except Exception:  # nosec B110
                pass

        conn.close()
        return {
            "streak_days": streak,
            "week_minutes": week_minutes,
            "last_practiced": last_practiced,
        }
    except Exception:
        return {
            "streak_days": 0,
            "week_minutes": 0,
            "last_practiced": None,
        }
